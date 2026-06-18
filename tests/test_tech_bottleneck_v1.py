from __future__ import annotations

import pandas as pd
import pytest

from stock_research.tech_bottleneck_candidates import (
    TECH_BOTTLENECK_CANDIDATE_COLUMNS,
    TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION,
)
from stock_research.tech_bottleneck_v1 import (
    TECH_BOTTLENECK_V1_ENGINE_VERSION,
    TECH_BOTTLENECK_V1_PROTECTION_NAME,
    build_tech_bottleneck_v1_from_rank_snapshots,
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
    assert summary["position_rows"] == len(result["positions"])
    assert summary["trade_rows"] == len(result["trades"])
    assert {"trade_date", "equity", "drawdown"}.issubset(result["equity_curve"][0])


def test_tech_bottleneck_v1_from_rank_snapshots_labels_point_in_time_source() -> None:
    result = build_tech_bottleneck_v1_from_rank_snapshots(
        candidate_snapshots=_rank_snapshots(),
        prices=_prices(),
        market_exposure=_market_exposure(),
        start_date="2025-01-01",
        end_date="2025-01-08",
        top_n=2,
        rebalance_frequency="weekly",
        transaction_cost_bps=20,
    )

    summary = result["summary"]
    assert summary["data_coverage"]["source"] == "point_in_time_daily_candidates"
    assert summary["data_coverage"]["candidate_snapshot_latest_date"] == "2025-01-08"
    assert summary["data_coverage"]["candidate_snapshot_rows"] == len(_rank_snapshots())
    assert result["trades"]


def test_tech_bottleneck_v1_requires_snapshot_rows_for_requested_range() -> None:
    with pytest.raises(ValueError, match="Tech Bottleneck candidate snapshots are missing"):
        build_tech_bottleneck_v1_from_rank_snapshots(
            candidate_snapshots=pd.DataFrame(),
            prices=_prices(),
            market_exposure=_market_exposure(),
            start_date="2025-01-01",
            end_date="2025-01-08",
            top_n=2,
            rebalance_frequency="weekly",
            transaction_cost_bps=20,
        )


@pytest.mark.parametrize(
    "column",
    ["candidate_as_of_date", "data_as_of_date", "filter_decision", "engine_version", "run_id"],
)
def test_tech_bottleneck_v1_rejects_invalid_snapshot_schema(column: str) -> None:
    snapshots = _rank_snapshots().drop(columns=[column])

    with pytest.raises(ValueError, match="candidate snapshot missing columns"):
        build_tech_bottleneck_v1_from_rank_snapshots(
            candidate_snapshots=snapshots,
            prices=_prices(),
            market_exposure=_market_exposure(),
            start_date="2025-01-01",
            end_date="2025-01-08",
            top_n=2,
            rebalance_frequency="weekly",
            transaction_cost_bps=20,
        )


def _duplicate_first_day_rank(frame: pd.DataFrame) -> None:
    frame.loc[frame["trade_date"] == "2025-01-01", "bottleneck_rank"] = 2


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda frame: frame.__setitem__("data_as_of_date", "2025-01-01"),
            "data_as_of_date must equal trade_date",
        ),
        (
            lambda frame: frame.__setitem__("filter_decision", "hold"),
            "filter_decision must be pass",
        ),
        (
            lambda frame: frame.__setitem__("engine_version", "wrong_engine"),
            "engine_version must equal",
        ),
        (
            lambda frame: frame.__setitem__("run_id", ""),
            "run_id must be non-empty",
        ),
        (
            _duplicate_first_day_rank,
            "duplicate bottleneck_rank",
        ),
    ],
)
def test_tech_bottleneck_v1_rejects_invalid_snapshot_values(mutate, message: str) -> None:
    snapshots = _rank_snapshots()
    mutate(snapshots)

    with pytest.raises(ValueError, match=message):
        build_tech_bottleneck_v1_from_rank_snapshots(
            candidate_snapshots=snapshots,
            prices=_prices(),
            market_exposure=_market_exposure(),
            start_date="2025-01-01",
            end_date="2025-01-08",
            top_n=2,
            rebalance_frequency="weekly",
            transaction_cost_bps=20,
        )


def test_tech_bottleneck_v1_rejects_partial_snapshot_date_coverage() -> None:
    snapshots = _rank_snapshots()
    snapshots = snapshots[snapshots["trade_date"] == "2025-01-01"].copy()

    with pytest.raises(ValueError, match="Tech Bottleneck candidate snapshots do not cover requested range"):
        build_tech_bottleneck_v1_from_rank_snapshots(
            candidate_snapshots=snapshots,
            prices=_prices(),
            market_exposure=_market_exposure(),
            start_date="2025-01-01",
            end_date="2025-01-08",
            top_n=2,
            rebalance_frequency="weekly",
            transaction_cost_bps=20,
        )


def test_tech_bottleneck_v1_rejects_interior_snapshot_date_gap() -> None:
    snapshots = _rank_snapshots()
    snapshots = snapshots[snapshots["trade_date"] != "2025-01-04"].copy()

    with pytest.raises(ValueError, match="missing trade dates 2025-01-04"):
        build_tech_bottleneck_v1_from_rank_snapshots(
            candidate_snapshots=snapshots,
            prices=_prices(),
            market_exposure=_market_exposure(),
            start_date="2025-01-01",
            end_date="2025-01-08",
            top_n=2,
            rebalance_frequency="weekly",
            transaction_cost_bps=20,
        )


def test_tech_bottleneck_v1_allows_non_trading_requested_endpoints() -> None:
    result = build_tech_bottleneck_v1_from_rank_snapshots(
        candidate_snapshots=_rank_snapshots(),
        prices=_prices(),
        market_exposure=_market_exposure(),
        start_date="2024-12-31",
        end_date="2025-01-09",
        top_n=2,
        rebalance_frequency="weekly",
        transaction_cost_bps=20,
    )

    coverage = result["summary"]["data_coverage"]
    assert coverage["candidate_snapshot_start_date"] == "2025-01-01"
    assert coverage["candidate_snapshot_latest_date"] == "2025-01-08"


def _candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01", "hit_count": 5},
            {"asset_id": "B", "stock_name": "Beta", "first_hit_date": "2025-01-01", "hit_count": 3},
            {"asset_id": "C", "stock_name": "Gamma", "first_hit_date": "2025-01-03", "hit_count": 1},
        ]
    )


def _rank_snapshots() -> pd.DataFrame:
    rows = []
    base = {
        "A": {"stock_name": "Alpha", "first_hit_date": "2025-01-01", "hit_count_as_of_date": 5, "score": 0.9},
        "B": {"stock_name": "Beta", "first_hit_date": "2025-01-01", "hit_count_as_of_date": 3, "score": 0.8},
        "C": {"stock_name": "Gamma", "first_hit_date": "2025-01-03", "hit_count_as_of_date": 1, "score": 0.7},
    }
    for trade_date in pd.date_range("2025-01-01", periods=8, freq="D"):
        day = trade_date.strftime("%Y-%m-%d")
        eligible = [
            (asset_id, details)
            for asset_id, details in base.items()
            if str(details["first_hit_date"]) <= day
        ]
        for rank, (asset_id, details) in enumerate(eligible, start=1):
            rows.append(
                {
                    "trade_date": day,
                    "asset_id": asset_id,
                    "stock_name": details["stock_name"],
                    "first_hit_date": details["first_hit_date"],
                    "candidate_as_of_date": day,
                    "hit_count_as_of_date": details["hit_count_as_of_date"],
                    "primary_chain_id": f"chain-{asset_id}",
                    "primary_chain_name": f"Chain {asset_id}",
                    "matched_bottleneck_dimensions": "cash_conversion",
                    "financial_as_of_date": details["first_hit_date"],
                    "technical_as_of_date": day,
                    "data_as_of_date": day,
                    "filter_decision": "pass",
                    "filter_reason": "",
                    "bottleneck_score": float(details["score"]) - (rank * 0.01),
                    "bottleneck_rank": rank,
                    "is_top5": rank <= 5,
                    "engine_version": TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION,
                    "run_id": "tech-bt-20250108-test",
                }
            )
    return pd.DataFrame(rows, columns=TECH_BOTTLENECK_CANDIDATE_COLUMNS)


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
