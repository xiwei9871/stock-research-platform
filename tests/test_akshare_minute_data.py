import datetime as dt

import pandas as pd

from stock_research import akshare_minute_data


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def test_akshare_sina_symbol_from_baostock_code():
    assert akshare_minute_data.akshare_sina_symbol_from_baostock_code("sh.600000") == "sh600000"
    assert akshare_minute_data.akshare_sina_symbol_from_baostock_code("sz.000001") == "sz000001"


def test_normalize_akshare_sina_minute_frame_filters_trade_date():
    frame = pd.DataFrame(
        [
            {
                "day": "2026-06-16 15:00:00",
                "open": "9.30",
                "high": "9.31",
                "low": "9.29",
                "close": "9.30",
                "volume": "100",
                "amount": "93000",
            },
            {
                "day": "2026-06-17 09:35:00",
                "open": "9.25",
                "high": "9.27",
                "low": "9.24",
                "close": "9.26",
                "volume": "200",
                "amount": "185000",
            },
        ]
    )

    rows = akshare_minute_data.normalize_akshare_sina_minute_frame(
        frame,
        asset_id="CN:SH:600000",
        baostock_code="sh.600000",
        trade_date=dt.date(2026, 6, 17),
        freq="5min",
        adjust_type="raw",
    )

    assert rows == [
        {
            "asset_id": "CN:SH:600000",
            "ts_code": "600000.SH",
            "trade_time": dt.datetime(2026, 6, 17, 9, 35),
            "trade_date": dt.date(2026, 6, 17),
            "freq": "5min",
            "adjust_type": "raw",
            "open": 9.25,
            "high": 9.27,
            "low": 9.24,
            "close": 9.26,
            "volume": 200.0,
            "amount": 185000.0,
            "source": "akshare",
        }
    ]


def test_upsert_akshare_sina_minute_rows_writes_market_source(monkeypatch):
    calls = []

    def fake_execute_many(conn, sql, rows):
        calls.append((conn, sql, list(rows)))

    monkeypatch.setattr(akshare_minute_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(akshare_minute_data, "execute_many", fake_execute_many)

    count = akshare_minute_data.upsert_akshare_sina_minute_rows(
        [
            {
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "trade_time": dt.datetime(2026, 6, 17, 9, 35),
                "trade_date": dt.date(2026, 6, 17),
                "freq": "5min",
                "adjust_type": "raw",
                "open": 9.25,
                "high": 9.27,
                "low": 9.24,
                "close": 9.26,
                "volume": 200.0,
                "amount": 185000.0,
                "source": "akshare",
            }
        ]
    )

    assert count == 1
    assert len(calls) == 1
    assert "INSERT INTO market.stock_minute_bar" in calls[0][1]
    assert "ON CONFLICT (trade_date, asset_id, trade_time, freq, adjust_type, source)" in calls[0][1]
    assert calls[0][2][0]["source"] == "akshare"


def test_query_akshare_sina_minute_rows_calls_stock_zh_a_minute(monkeypatch):
    calls = []

    class FakeAk:
        @staticmethod
        def stock_zh_a_minute(symbol, period, adjust):
            calls.append((symbol, period, adjust))
            return pd.DataFrame(
                [
                    {
                        "day": "2026-06-17 09:35:00",
                        "open": "9.25",
                        "high": "9.27",
                        "low": "9.24",
                        "close": "9.26",
                        "volume": "200",
                        "amount": "185000",
                    }
                ]
            )

    monkeypatch.setattr(akshare_minute_data, "ak", FakeAk)

    rows = akshare_minute_data.query_akshare_sina_minute_rows(
        asset_id="CN:SH:600000",
        baostock_code="sh.600000",
        trade_date=dt.date(2026, 6, 17),
        freq="5min",
        adjust_type="qfq",
    )

    assert calls == [("sh600000", "5", "qfq")]
    assert rows[0]["trade_time"] == dt.datetime(2026, 6, 17, 9, 35)


def test_run_akshare_sina_minute_backfill_writes_gap_assets(monkeypatch):
    gap_assets = [
        {"asset_id": "CN:SH:600000", "baostock_code": "sh.600000", "existing_rows": 12},
        {"asset_id": "CN:SZ:000001", "baostock_code": "sz.000001", "existing_rows": 0},
    ]
    written = []

    def fake_load_gap_assets(**kwargs):
        assert kwargs["trade_date"] == dt.date(2026, 6, 17)
        assert kwargs["expected_rows"] == 48
        return gap_assets

    def fake_query(**kwargs):
        return [
            {
                "asset_id": kwargs["asset_id"],
                "ts_code": "600000.SH",
                "trade_time": dt.datetime(2026, 6, 17, 9, 35),
                "trade_date": dt.date(2026, 6, 17),
                "freq": kwargs["freq"],
                "adjust_type": kwargs["adjust_type"],
                "open": 9.25,
                "high": 9.27,
                "low": 9.24,
                "close": 9.26,
                "volume": 200.0,
                "amount": 185000.0,
                "source": "akshare",
            }
        ]

    def fake_upsert(rows):
        written.extend(rows)
        return len(rows)

    monkeypatch.setattr(akshare_minute_data, "load_akshare_sina_gap_assets", fake_load_gap_assets)
    monkeypatch.setattr(akshare_minute_data, "query_akshare_sina_minute_rows", fake_query)
    monkeypatch.setattr(akshare_minute_data, "upsert_akshare_sina_minute_rows", fake_upsert)
    monkeypatch.setattr(akshare_minute_data.time, "sleep", lambda _: None)

    result = akshare_minute_data.run_akshare_sina_minute_backfill(
        trade_date="2026-06-17",
        freq="5min",
        adjust_types=["raw"],
        max_assets=2,
        sleep_seconds=0.0,
    )

    assert result == {
        "assets_attempted": 2,
        "adjust_attempted": 2,
        "success": 2,
        "failed": 0,
        "rows": 2,
        "skipped_empty": 0,
    }
    assert [row["asset_id"] for row in written] == ["CN:SH:600000", "CN:SZ:000001"]


def test_run_akshare_sina_minute_backfill_rejects_non_positive_workers():
    try:
        akshare_minute_data.run_akshare_sina_minute_backfill(
            trade_date="2026-06-17",
            workers=0,
        )
    except ValueError as exc:
        assert str(exc) == "workers must be positive"
    else:
        raise AssertionError("expected ValueError")
