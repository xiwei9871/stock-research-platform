from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from stock_research.rolling_oversold import pipeline
from stock_research.rolling_oversold.outcomes import (
    calibration_outcomes_before,
    completed_outcomes_before_anchor,
    evaluate_sector_snapshot,
    summarize_sector_rolling_evaluation,
)


ANCHOR = date(2026, 7, 31)


def _snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "rolling_oversold_sector_v2|2026-07-31",
        "anchor_date": ANCHOR.isoformat(),
        "market_regime": {"market_regime": "risk_off"},
        "sector_states": pd.DataFrame(
            [
                {
                    "sector_system": "ths",
                    "sector_code": "A",
                    "sector_name": "Sector A",
                    "sector_rank": 1,
                    "sector_recovery_state": "repairing",
                },
                {
                    "sector_system": "ths",
                    "sector_code": "B",
                    "sector_name": "Sector B",
                    "sector_rank": 6,
                    "sector_recovery_state": "fresh_oversold",
                },
            ]
        ),
        "stock_candidates": pd.DataFrame(
            [
                {
                    "asset_id": "SHARED",
                    "anchor_close": 10.0,
                    "adjusted_close_source": "qfq",
                    "sector_system": "ths",
                    "sector_code": "A",
                    "sector_name": "Sector A",
                    "sector_gate_status": "confirmed",
                    "sector_research_eligibility": "eligible",
                    "sector_recovery_state": "repairing",
                    "stock_lifecycle": "expected_repair",
                    "stock_rank": 1,
                    "sector_stock_rank": 1,
                },
                {
                    # The same asset is intentionally present in a second
                    # sector; batch outcomes must keep both observations.
                    "asset_id": "SHARED",
                    "anchor_close": 10.0,
                    "adjusted_close_source": "qfq",
                    "sector_system": "ths",
                    "sector_code": "B",
                    "sector_name": "Sector B",
                    "sector_gate_status": "watch",
                    "sector_research_eligibility": "watch",
                    "sector_recovery_state": "fresh_oversold",
                    "stock_lifecycle": "new_oversold",
                    "stock_rank": 2,
                    "sector_stock_rank": 1,
                },
            ]
        ),
    }


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "SHARED", "trade_date": "2026-08-01", "qfq_close": 10.4},
            {"asset_id": "SHARED", "trade_date": "2026-08-03", "qfq_close": 10.6},
        ]
    )


def test_sector_outcomes_use_strictly_future_sessions_and_keep_cross_sector_duplicates():
    detail = evaluate_sector_snapshot(
        _snapshot(), bars=_bars(), evaluation_cutoff=date(2026, 8, 3), horizons=(1, 3)
    )

    assert len(detail) == 4
    assert detail["asset_id"].tolist().count("SHARED") == 4
    completed = detail.loc[detail["status"].eq("complete")]
    assert (pd.to_datetime(completed["target_trade_date"]) > pd.to_datetime(completed["anchor_date"])).all()
    pending = detail.loc[detail["target_trade_date"].eq("2026-08-03")]
    assert len(pending) == 2
    assert pending["status"].eq("pending").all()
    assert set(detail["sector_code"]) == {"A", "B"}
    assert detail["sector_stock_rank"].tolist() == [1, 1, 1, 1]
    assert detail["sector_rank"].tolist() == [1, 1, 6, 6]
    assert detail.loc[detail["status"].eq("complete"), "endpoint_close"].tolist() == [10.4, 10.4]


def test_sector_summary_has_sector_and_sector_stock_rank_buckets_and_metrics():
    detail = evaluate_sector_snapshot(
        _snapshot(), bars=_bars(), evaluation_cutoff=date(2026, 8, 3), horizons=(1, 3)
    )
    summary = summarize_sector_rolling_evaluation(detail)

    assert {
        "overall",
        "sector",
        "sector_recovery_state",
        "sector_rank_bucket",
        "sector_stock_rank_bucket",
    }.issubset(set(summary["group_by"]))
    overall = summary.loc[
        summary["group_by"].eq("overall") & summary["forward_horizon_days"].eq(1)
    ].iloc[0]
    assert overall[["total_count", "complete_count", "pending_count"]].tolist() == [2, 2, 0]
    assert overall["up_ratio"] == pytest.approx(1.0)
    assert overall["mean_return"] == pytest.approx(0.04)
    assert overall["median_return"] == pytest.approx(0.04)
    assert overall["hit_3pct_rate"] == pytest.approx(1.0)
    assert overall["hit_5pct_rate"] == pytest.approx(0.0)
    assert overall["hit_7pct_rate"] == pytest.approx(0.0)
    assert "top_1" in set(
        summary.loc[summary["group_by"].eq("sector_stock_rank_bucket"), "group_value"]
    )


def test_calibration_outcomes_are_immutable_and_strictly_before_next_anchor():
    detail = evaluate_sector_snapshot(
        _snapshot(), bars=_bars(), evaluation_cutoff=date(2026, 8, 1), horizons=(1,)
    )
    before = detail.copy(deep=True)
    calibrated = completed_outcomes_before_anchor(detail, next_anchor=date(2026, 8, 3))
    assert len(calibrated) == 2
    assert calibrated["status"].eq("complete").all()
    assert (pd.to_datetime(calibrated["target_trade_date"]) < pd.Timestamp("2026-08-03")).all()
    pd.testing.assert_frame_equal(detail, before)
    pd.testing.assert_frame_equal(calibration_outcomes_before(detail, date(2026, 8, 3)), calibrated)


def test_calibration_rejects_leakage_and_incomplete_rows():
    detail = evaluate_sector_snapshot(
        _snapshot(), bars=_bars(), evaluation_cutoff=date(2026, 8, 3), horizons=(1, 3)
    )
    with pytest.raises(ValueError, match="evaluation_cutoff"):
        completed_outcomes_before_anchor(detail, next_anchor=date(2026, 8, 2))
    with pytest.raises(ValueError, match="complete"):
        completed_outcomes_before_anchor(detail, next_anchor=date(2026, 8, 4))


def test_pipeline_batch_outcome_helper_returns_detail_and_summary_without_reloading():
    result = pipeline.evaluate_sector_batch_outcomes(
        _snapshot(), bars=_bars(), evaluation_cutoff=date(2026, 8, 3), horizons=(1,)
    )
    assert set(result) == {"detail", "summary"}
    assert len(result["detail"]) == 2
    assert not result["summary"].empty
