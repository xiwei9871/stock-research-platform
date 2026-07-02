import datetime as dt

from stock_research import baostock_minute_backfill_watchdog as watchdog


class FakeConnection:
    def __init__(self, rows_by_marker):
        self.rows_by_marker = rows_by_marker
        self.executed = []


def fake_fetch_all(conn, sql, params=None):
    conn.executed.append((sql, params))
    for marker, rows in conn.rows_by_marker.items():
        if marker in sql:
            return rows
    raise AssertionError(f"unexpected sql: {sql}")


def test_calculate_backfill_budget_uses_1_1_safety_and_reserves_today_5min():
    budget = watchdog.calculate_baostock_minute_budget(
        active_asset_count=5209,
        today_adjust_types=["raw", "qfq"],
        daily_request_limit=50000,
        safety_multiplier=1.1,
    )

    assert budget.safe_daily_request_budget == 45454
    assert budget.today_reserved_requests == 10418
    assert budget.backfill_request_budget == 35036
    assert round(budget.full_market_raw_qfq_days, 2) == 3.36


def test_budget_honors_optional_backfill_request_limit():
    budget = watchdog.calculate_baostock_minute_budget(
        active_asset_count=5209,
        today_adjust_types=["raw", "qfq"],
        daily_request_limit=50000,
        safety_multiplier=1.1,
        max_backfill_requests=20000,
    )

    assert budget.backfill_request_budget == 20000


def test_quota_ledger_allocates_and_releases_unused_requests(tmp_path):
    ledger_path = tmp_path / "quota.json"
    day = dt.date(2026, 7, 2)

    first = watchdog.allocate_daily_backfill_quota(
        ledger_path=ledger_path,
        day=day,
        backfill_request_budget=100,
        requested_requests=80,
    )
    watchdog.finalize_daily_backfill_quota(
        ledger_path=ledger_path,
        day=day,
        allocated_requests=first.allocated_requests,
        attempted_requests=30,
    )
    second = watchdog.allocate_daily_backfill_quota(
        ledger_path=ledger_path,
        day=day,
        backfill_request_budget=100,
        requested_requests=80,
    )

    assert first.allocated_requests == 80
    assert second.allocated_requests == 70
    assert second.consumed_requests == 30


def test_load_five_year_probe_summary_counts_monthly_and_daily_requests(monkeypatch):
    conn = FakeConnection(
        {
            "active_baostock_assets": [{"active_baostock_assets": 5209}],
            "distinct_open_days": [{"open_days": 1183, "first_open": "2021-07-02", "last_open": "2026-07-02"}],
            "asset_trade_days": [
                {
                    "asset_trade_days": 5777584,
                    "min_assets": 4200,
                    "max_assets": 5209,
                    "avg_assets": "4883.84",
                }
            ],
            "asset_months": [
                {
                    "months": 61,
                    "asset_months": 299227,
                    "min_assets": 4246,
                    "max_assets": 5209,
                    "avg_assets": "4905.36",
                }
            ],
        }
    )
    monkeypatch.setattr(watchdog, "fetch_all", fake_fetch_all)

    summary = watchdog.load_baostock_minute_backfill_probe_summary(
        conn,
        start_date=dt.date(2021, 7, 2),
        end_date=dt.date(2026, 7, 2),
        freq="5min",
        adjust_types=["raw", "qfq"],
    )

    assert summary["active_baostock_assets"] == 5209
    assert summary["open_days"] == 1183
    assert summary["asset_trade_days"] == 5777584
    assert summary["asset_months"] == 299227
    assert summary["daily_chunk_requests"] == 11555168
    assert summary["monthly_chunk_requests"] == 598454
    assert summary["estimated_rows"] == 554648064
