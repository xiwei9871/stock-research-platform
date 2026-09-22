from __future__ import annotations

import pandas as pd

from stock_research.tech_bottleneck_v1 import (
    TECH_BOTTLENECK_V1_ENGINE_VERSION,
    TECH_BOTTLENECK_V1_PROTECTION_NAME,
    build_tech_bottleneck_v1_from_frames,
)


def test_tech_bottleneck_v1_uses_accepted_c2_baseline() -> None:
    result = build_tech_bottleneck_v1_from_frames(
        candidates=_candidates(),
        prices=_prices(),
        market_exposure=_market_exposure(),
        start_date="2025-01-01",
        end_date="2025-01-08",
        top_n=2,
        rebalance_frequency="weekly",
        transaction_cost_bps=20,
    )

    summary = result["summary"]
    assert result["strategy_id"] == "tech_bottleneck"
    assert result["source_kind"] == TECH_BOTTLENECK_V1_ENGINE_VERSION
    assert summary["engine_version"] == TECH_BOTTLENECK_V1_ENGINE_VERSION
    assert summary["protection_name"] == TECH_BOTTLENECK_V1_PROTECTION_NAME
    assert summary["baseline_name"] == "strict_st_only_tight3b_rank_exit_top10"
    assert summary["fresh_engine_note"] == "Tech Bottleneck V1 fresh recompute via accepted Serenity C2 baseline"
    assert result["config"]["top_n"] == 2
    assert result["config"]["rebalance_frequency"] == "weekly"
    assert result["equity_curve"]
    assert result["positions"]
    assert result["trades"]
    assert {"trade_date", "equity", "drawdown"}.issubset(result["equity_curve"][0])


def _candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01", "hit_count": 5},
            {"asset_id": "B", "stock_name": "Beta", "first_hit_date": "2025-01-01", "hit_count": 3},
            {"asset_id": "C", "stock_name": "Gamma", "first_hit_date": "2025-01-03", "hit_count": 1},
        ]
    )


def _prices() -> pd.DataFrame:
    rows = []
    closes = {
        "A": [10.0, 11.0, 12.0, 11.0, 10.0, 9.0, 8.0, 8.5],
        "B": [20.0, 20.5, 21.0, 21.5, 22.0, 23.0, 24.0, 25.0],
        "C": [30.0, 30.0, 30.5, 31.0, 31.5, 32.0, 32.5, 33.0],
    }
    for index, trade_date in enumerate(pd.date_range("2025-01-01", periods=8, freq="D")):
        for asset_id, series in closes.items():
            close = series[index]
            rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "asset_id": asset_id,
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                }
            )
    return pd.DataFrame(rows)


def _market_exposure() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": trade_date.strftime("%Y-%m-%d"), "target_exposure": 0.8}
            for trade_date in pd.date_range("2025-01-01", periods=8, freq="D")
        ]
    )
