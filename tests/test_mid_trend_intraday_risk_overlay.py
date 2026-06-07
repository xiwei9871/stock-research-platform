import pandas as pd

from stock_research.mid_trend_intraday_risk_overlay import (
    apply_intraday_risk_filter_to_shadow_candidates,
)


def test_apply_intraday_risk_filter_to_shadow_candidates_reranks_risky_names() -> None:
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "shadow_top10_rank": 1},
            {"trade_date": "2026-01-05", "asset_id": "B", "shadow_top10_rank": 2},
            {"trade_date": "2026-01-05", "asset_id": "C", "shadow_top10_rank": 3},
            {"trade_date": "2026-01-05", "asset_id": "D", "shadow_top10_rank": 4},
            {"trade_date": "2026-01-05", "asset_id": "E", "shadow_top10_rank": 5},
            {"trade_date": "2026-01-05", "asset_id": "F", "shadow_top10_rank": 6},
        ]
    )
    states = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "midtrend_risk_level": "high"},
            {"trade_date": "2026-01-05", "asset_id": "B", "midtrend_risk_level": "watch"},
            {"trade_date": "2026-01-05", "asset_id": "C", "midtrend_risk_level": "none"},
            {"trade_date": "2026-01-05", "asset_id": "D", "midtrend_risk_level": "none"},
            {"trade_date": "2026-01-05", "asset_id": "E", "midtrend_risk_level": "none"},
            {"trade_date": "2026-01-05", "asset_id": "F", "midtrend_risk_level": "none"},
        ]
    )

    filtered = apply_intraday_risk_filter_to_shadow_candidates(
        candidates,
        states,
        watch_rank_penalty=3.0,
        high_rank_penalty=8.0,
    )

    assert filtered["asset_id"].tolist()[:5] == ["C", "D", "B", "E", "F"]
    assert filtered.loc[filtered["asset_id"].eq("A"), "intraday_risk_adjusted_rank"].iloc[0] == 9.0
    assert filtered.loc[filtered["asset_id"].eq("B"), "midtrend_risk_level"].iloc[0] == "watch"
