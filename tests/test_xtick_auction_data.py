import datetime as dt
import gzip
import io
import json
import zipfile

import pandas as pd
import pytest

from stock_research import cli
from stock_research import xtick_auction_data
from stock_research.xtick_auction_data import (
    collect_xtick_dayupdate_bid,
    decode_xtick_response,
    ts_code_from_xtick_code,
    upsert_xtick_open_auction_detail_rows,
    xtick_auction_detail_market_row,
)


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def raw_xtick_bid_row() -> dict:
    return {
        "type": 1,
        "code": "600023",
        "time": 1780967703000,
        "price": 5.9,
        "close": 5.95,
        "jjzf": -0.84,
        "jjl": 215,
        "jje": 126850,
        "nol": 10,
        "noe": 3,
        "trend": -1,
    }


def test_decode_xtick_response_supports_plain_gzip_and_zip_json():
    payload = [{"code": "000001", "time": 1780967700000}]
    plain = json.dumps(payload).encode("utf-8")
    gzipped = gzip.compress(plain)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.json", plain)

    assert decode_xtick_response(plain) == payload
    assert decode_xtick_response(gzipped) == payload
    assert decode_xtick_response(buffer.getvalue()) == payload


def test_xtick_auction_detail_market_row_normalizes_ms_timestamp():
    row = xtick_auction_detail_market_row(raw_xtick_bid_row(), source="xtick_dayupdate_bid")

    assert row["asset_id"] == "CN:SH:600023"
    assert row["ts_code"] == "600023.SH"
    assert row["code"] == "600023"
    assert row["raw_time"] == 1780967703000
    assert row["trade_date"] == dt.date(2026, 6, 9)
    assert row["trade_time"] == dt.datetime(2026, 6, 9, 9, 15, 3)
    assert row["auction_phase"] == "open_call"
    assert row["price"] == 5.9
    assert row["jjzf"] == -0.84
    assert row["jjl"] == 215
    assert row["trend"] == -1
    assert row["source"] == "xtick_dayupdate_bid"


def test_ts_code_from_xtick_code_infers_exchange():
    assert ts_code_from_xtick_code("600023") == "600023.SH"
    assert ts_code_from_xtick_code("000001") == "000001.SZ"
    assert ts_code_from_xtick_code("300750") == "300750.SZ"
    assert ts_code_from_xtick_code("688001") == "688001.SH"
    assert ts_code_from_xtick_code("830799") == "830799.BJ"


def test_upsert_xtick_open_auction_detail_rows_writes_staging_and_market(monkeypatch):
    calls = []

    def fake_execute_many(conn, sql, rows):
        calls.append((conn, sql, list(rows)))

    monkeypatch.setattr(xtick_auction_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(xtick_auction_data, "execute_many", fake_execute_many)

    count = upsert_xtick_open_auction_detail_rows(
        [raw_xtick_bid_row()],
        source_endpoint="dayupdate",
        source="xtick_dayupdate_bid",
        params={"symbol": "shm", "tradeDate": "2026-06-09"},
    )

    assert count == 1
    assert len(calls) == 2
    assert "INSERT INTO staging.xtick_stock_auction_detail" in calls[0][1]
    assert "INSERT INTO market.stock_auction_detail" in calls[1][1]
    assert "ON CONFLICT (trade_time, asset_id, source)" in calls[1][1]
    assert calls[1][2][0]["trade_time"] == dt.datetime(2026, 6, 9, 9, 15, 3)


def test_collect_xtick_dayupdate_bid_filters_date_and_upserts(monkeypatch):
    query_calls = []
    upsert_calls = []

    def fake_query(symbol, trade_date, token=None, token_env="XTICK_TOKEN"):
        query_calls.append((symbol, trade_date, token, token_env))
        return [
            raw_xtick_bid_row(),
            {**raw_xtick_bid_row(), "time": 1780881303000},
        ]

    def fake_upsert(rows, source_endpoint, source, params):
        upsert_calls.append((rows, source_endpoint, source, params))
        return len(rows)

    monkeypatch.setattr(xtick_auction_data, "query_xtick_dayupdate_bid_rows", fake_query)
    monkeypatch.setattr(xtick_auction_data, "upsert_xtick_open_auction_detail_rows", fake_upsert)
    monkeypatch.setattr(xtick_auction_data.time, "sleep", lambda seconds: None)

    result = collect_xtick_dayupdate_bid(
        trade_date="2026-06-09",
        symbols=["shm"],
        token="token-value",
        sleep_seconds=0,
    )

    assert query_calls == [("shm", "2026-06-09", "token-value", "XTICK_TOKEN")]
    assert upsert_calls[0][0] == [raw_xtick_bid_row()]
    assert upsert_calls[0][2] == "xtick_dayupdate_bid"
    assert result["summary"]["upserted_rows"] == 1
    assert result["detail"].to_dict("records")[0]["queried_rows"] == 2


def test_xtick_auction_detail_commands_are_registered():
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "collect-xtick-auction-detail-v1",
            "--trade-date",
            "2026-06-09",
            "--symbols",
            "shm,szm",
        ]
    )

    assert args.command == "collect-xtick-auction-detail-v1"
    assert args.symbols == ["shm", "szm"]
    assert args.token_env == "XTICK_TOKEN"


def test_write_xtick_collect_report_writes_latest_files(tmp_path):
    result = {
        "detail": pd.DataFrame([{"trade_date": "2026-06-09", "symbol": "shm", "upserted_rows": 1}]),
        "summary": {
            "trade_date": "2026-06-09",
            "symbols_requested": 1,
            "symbols_failed": 0,
            "upserted_rows": 1,
        },
    }

    report = xtick_auction_data.write_xtick_auction_collect_report(
        result=result,
        output_dir=tmp_path,
        trade_date="2026-06-09",
    )

    assert report["paths"]["detail"].exists()
    assert report["paths"]["latest"].exists()
    assert "upserted_rows: 1" in report["paths"]["markdown_report"].read_text(encoding="utf-8")
