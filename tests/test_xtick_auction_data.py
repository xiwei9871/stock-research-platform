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
    build_xtick_auction_backfill_plan,
    build_xtick_auction_close_check,
    collect_xtick_dayupdate_bid,
    decode_xtick_response,
    load_existing_xtick_auction_coverage,
    run_xtick_auction_backfill_plan,
    ts_code_from_xtick_code,
    upsert_xtick_open_auction_detail_rows,
    write_xtick_auction_backfill_plan_report,
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

    plan_args = parser.parse_args(
        [
            "xtick-auction-backfill-plan-v1",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-10",
            "--output-dir",
            "/tmp/out",
        ]
    )
    run_args = parser.parse_args(
        [
            "xtick-auction-backfill-run-v1",
            "--plan-path",
            "/tmp/plan.csv",
            "--max-tasks",
            "2",
            "--output-dir",
            "/tmp/out",
        ]
    )

    assert plan_args.command == "xtick-auction-backfill-plan-v1"
    assert plan_args.available_start_date == "2026-05-10"
    assert plan_args.symbols == ["szm", "shm", "cyb", "kcb"]
    assert run_args.command == "xtick-auction-backfill-run-v1"
    assert run_args.max_tasks == 2


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


def test_build_xtick_auction_backfill_plan_marks_permission_gap_and_pending_tasks():
    plan = build_xtick_auction_backfill_plan(
        start_date="2026-05-09",
        end_date="2026-05-11",
        trade_dates=["2026-05-09", "2026-05-10", "2026-05-11"],
        symbols=["shm", "szm"],
        existing_coverage=pd.DataFrame(
            [
                {
                    "trade_date": "2026-05-10",
                    "symbol": "shm",
                    "existing_rows": 120000,
                    "min_time": "2026-05-10 09:15:00",
                    "max_time": "2026-05-10 09:25:00",
                }
            ]
        ),
        available_start_date="2026-05-10",
    )

    records = plan.to_dict("records")
    assert records[0]["trade_date"] == "2026-05-09"
    assert records[0]["status"] == "unavailable_by_permission"
    assert records[2]["trade_date"] == "2026-05-10"
    assert records[2]["symbol"] == "shm"
    assert records[2]["status"] == "covered"
    assert records[3]["trade_date"] == "2026-05-10"
    assert records[3]["symbol"] == "szm"
    assert records[3]["status"] == "pending"


def test_build_xtick_auction_backfill_plan_defaults_to_existing_market_segments():
    plan = build_xtick_auction_backfill_plan(
        start_date="2026-06-09",
        end_date="2026-06-09",
        trade_dates=["2026-06-09"],
        existing_coverage=pd.DataFrame(),
    )

    assert plan["symbol"].tolist() == ["szm", "shm", "cyb", "kcb"]


def test_load_existing_xtick_auction_coverage_queries_by_date_and_source(monkeypatch):
    captured = {}

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "trade_date": "2026-06-09",
                "symbol": "shm",
                "existing_rows": 58,
                "min_time": "2026-06-09 09:15:00",
                "max_time": "2026-06-09 09:25:00",
            }
        ]

    monkeypatch.setattr(xtick_auction_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(xtick_auction_data, "fetch_all", fake_fetch_all)

    coverage = load_existing_xtick_auction_coverage(
        start_date="2026-06-01",
        end_date="2026-06-30",
        source="xtick_dayupdate_bid",
    )

    assert "FROM market.stock_auction_detail" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-06-30", "xtick_dayupdate_bid"]
    assert coverage.to_dict("records")[0]["symbol"] == "shm"


def test_run_xtick_auction_backfill_plan_executes_pending_tasks_with_limit(monkeypatch):
    plan = pd.DataFrame(
        [
            {"trade_date": "2026-06-07", "symbol": "shm", "status": "pending"},
            {"trade_date": "2026-06-08", "symbol": "shm", "status": "covered"},
            {"trade_date": "2026-06-09", "symbol": "szm", "status": "pending"},
        ]
    )
    calls = []

    def fake_collect(trade_date, symbols, token=None, token_env="XTICK_TOKEN", sleep_seconds=1.0):
        calls.append((trade_date, symbols, token, token_env, sleep_seconds))
        return {
            "detail": pd.DataFrame(
                [
                    {
                        "trade_date": trade_date,
                        "symbol": symbols[0],
                        "queried_rows": 10,
                        "selected_rows": 10,
                        "upserted_rows": 10,
                        "error": "",
                    }
                ]
            ),
            "summary": {"upserted_rows": 10},
        }

    monkeypatch.setattr(xtick_auction_data, "collect_xtick_dayupdate_bid", fake_collect)

    result = run_xtick_auction_backfill_plan(
        plan=plan,
        max_tasks=1,
        token="token-value",
        sleep_seconds=0,
    )

    assert calls == [("2026-06-07", ["shm"], "token-value", "XTICK_TOKEN", 0)]
    assert result["summary"]["executed_tasks"] == 1
    assert result["summary"]["remaining_pending_tasks"] == 1
    assert result["executed"].to_dict("records")[0]["upserted_rows"] == 10


def test_write_xtick_auction_backfill_plan_report_writes_gap_summary(tmp_path):
    plan = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "symbol": "shm", "status": "unavailable_by_permission"},
            {"trade_date": "2026-06-09", "symbol": "shm", "status": "pending"},
        ]
    )

    report = write_xtick_auction_backfill_plan_report(
        plan=plan,
        output_dir=tmp_path,
        start_date="2025-01-01",
        end_date="2026-06-10",
    )

    assert report["paths"]["plan"].exists()
    assert report["summary"]["pending_tasks"] == 1
    assert report["summary"]["unavailable_tasks"] == 1
    assert "unavailable_by_permission" in report["paths"]["markdown_report"].read_text(encoding="utf-8")


def test_build_xtick_auction_close_check_compares_detail_925_with_result_bar(monkeypatch):
    captured = {}

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "trade_date": "2026-06-09",
                "ts_code": "000001.SZ",
                "detail_time": "2026-06-09 09:25:00",
                "detail_price": 11.01,
                "detail_amount": 3339333,
                "bar_open": 11.01,
                "bar_close": 11.00,
                "bar_vwap": 11.01,
                "bar_amount": 3339333,
                "price_diff": 0,
                "amount_diff": 0,
                "check_status": "match",
            }
        ]

    monkeypatch.setattr(xtick_auction_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(xtick_auction_data, "fetch_all", fake_fetch_all)

    check = build_xtick_auction_close_check(
        start_date="2026-06-09",
        end_date="2026-06-09",
        source="xtick_biddetail",
    )

    assert "09:25:00" in captured["sql"]
    assert captured["params"] == [
        "2026-06-09",
        "2026-06-09",
        "xtick_biddetail",
        "2026-06-09",
        "2026-06-09",
    ]
    assert check.to_dict("records")[0]["check_status"] == "match"
