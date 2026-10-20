from __future__ import annotations

import pandas as pd
import pytest

from stock_research.tech_bottleneck_candidates import build_point_in_time_candidate_snapshots
from stock_research.tech_bottleneck_v1 import build_tech_bottleneck_v1_from_rank_snapshots


def _pit_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2026-06-01", "2026-06-19")
    asset_id = "CN:SH:600000"
    base_candidates = pd.DataFrame(
        [
            {
                "asset_id": asset_id,
                "stock_name": "Sample",
                "first_hit_date": "2026-06-01",
                "candidate_trade_date": "2026-06-01",
                "hit_count": 2,
                "financial_as_of_date": "2026-06-01",
                "technical_as_of_date": "2026-06-01",
                "filter_decision": "pass",
            }
        ]
    )
    prices = pd.DataFrame(
        [
            {
                "trade_date": trade_date.strftime("%Y-%m-%d"),
                "asset_id": asset_id,
                "open": 10.0 + index / 10,
                "high": 10.1 + index / 10,
                "low": 9.9 + index / 10,
                "close": 10.0 + index / 10,
            }
            for index, trade_date in enumerate(dates)
        ]
    )
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=base_candidates,
        prices=prices,
        start_date="2026-06-01",
        end_date="2026-06-19",
        run_id="test-market-exposure",
    )
    exposure_dates = [date.strftime("%Y-%m-%d") for date in dates if date.strftime("%Y-%m-%d") != "2026-06-15"]
    market_exposure = pd.DataFrame(
        [{"trade_date": trade_date, "target_exposure": 0.7} for trade_date in exposure_dates]
    )
    return snapshots, prices, market_exposure


def test_rejects_missing_exact_rebalance_exposure_in_pit_replay() -> None:
    snapshots, prices, market_exposure = _pit_inputs()

    with pytest.raises(
        ValueError,
        match="market exposure missing exact rebalance dates: 2026-06-15",
    ):
        build_tech_bottleneck_v1_from_rank_snapshots(
            candidate_snapshots=snapshots,
            prices=prices,
            market_exposure=market_exposure,
            start_date="2026-06-01",
            end_date="2026-06-19",
            top_n=1,
            rebalance_frequency="biweekly",
            transaction_cost_bps=10,
            max_position_weight=1.0,
            adjust_type="hfq",
        )


def test_rejects_missing_target_exposure_value_on_rebalance_date() -> None:
    snapshots, prices, market_exposure = _pit_inputs()
    market_exposure.loc[len(market_exposure)] = {
        "trade_date": "2026-06-15",
        "target_exposure": float("nan"),
    }

    with pytest.raises(
        ValueError,
        match="missing or invalid target_exposure for rebalance date: 2026-06-15",
    ):
        build_tech_bottleneck_v1_from_rank_snapshots(
            candidate_snapshots=snapshots,
            prices=prices,
            market_exposure=market_exposure,
            start_date="2026-06-01",
            end_date="2026-06-19",
            top_n=1,
            rebalance_frequency="biweekly",
            transaction_cost_bps=10,
            max_position_weight=1.0,
            adjust_type="hfq",
        )
