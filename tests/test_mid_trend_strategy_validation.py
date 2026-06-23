from __future__ import annotations

from stock_research.mid_trend_strategy_validation import (
    discover_mid_trend_strategy_candidates,
    filter_complete_mid_trend_candidates,
)


def test_discover_mid_trend_strategy_candidates_returns_known_complete_entries() -> None:
    candidates = discover_mid_trend_strategy_candidates()

    ids = {item["strategy_id"] for item in candidates}
    assert "current_mid_trend_strategy_v1" in ids
    assert "mid_trend_shadow_backtest" in ids


def test_filter_complete_mid_trend_candidates_keeps_only_complete_portfolio_versions() -> None:
    candidates = [
        {
            "strategy_id": "current_mid_trend_strategy_v1",
            "group": "portfolio",
            "result_keys": {"holdings", "trades", "equity", "summary"},
        },
        {
            "strategy_id": "mid_trend_incomplete_portfolio",
            "group": "portfolio",
            "result_keys": {"holdings", "trades", "equity"},
        },
        {
            "strategy_id": "mid_trend_portfolio_review",
            "group": "review",
            "result_keys": {"review_rows", "portfolio_summary"},
        },
    ]

    filtered = filter_complete_mid_trend_candidates(candidates)

    assert [item["strategy_id"] for item in filtered] == ["current_mid_trend_strategy_v1"]
