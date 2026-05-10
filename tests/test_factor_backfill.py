from stock_research.factor_backfill import build_trade_date_range
from stock_research import factor_backfill


def test_build_trade_date_range_returns_inclusive_daily_strings():
    assert build_trade_date_range("2026-05-01", "2026-05-03") == [
        "2026-05-01",
        "2026-05-02",
        "2026-05-03",
    ]


def test_backfill_factor_daily_range_runs_each_date(monkeypatch):
    calls = []

    monkeypatch.setattr(
        factor_backfill,
        "build_and_store_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 10,
    )

    result = factor_backfill.backfill_factor_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-02",
        lookback_bars=130,
        industry_system="csrc",
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-02"]
    assert list(result["factor_rows"]) == [10, 10]
    assert calls[0]["trade_date"] == "2026-05-01"
    assert calls[1]["trade_date"] == "2026-05-02"
