from pathlib import Path

import pandas as pd
import pytest

from stock_research.mid_trend_round2_optimization import (
    DEFAULT_MID_TREND_ROUND2_CONFIG,
    build_mid_trend_round2_baseline_artifacts,
)


def test_build_mid_trend_round2_baseline_artifacts_respects_fixed_train_test_split(
    tmp_path: Path,
    _baseline_payload: dict[str, pd.DataFrame],
) -> None:
    result = build_mid_trend_round2_baseline_artifacts(
        start_date="2025-01-01",
        train_end_date="2026-02-01",
        end_date="2026-06-02",
        output_dir=tmp_path,
        baseline_payload=_baseline_payload,
    )

    assert result["config"]["train_end_date"] == "2026-02-01"
    assert result["config"]["hard_constraints"] == (
        "max_drawdown",
        "monthly_win_rate",
        "return_drawdown_ratio",
    )
    pd.testing.assert_frame_equal(
        result["baseline_train_summary"],
        _baseline_payload["train_summary"],
    )
    pd.testing.assert_frame_equal(
        result["baseline_test_summary"],
        _baseline_payload["test_summary"],
    )
    pd.testing.assert_frame_equal(
        pd.read_csv(tmp_path / "mid_trend_round2_baseline_train_summary.csv"),
        _baseline_payload["train_summary"],
    )
    pd.testing.assert_frame_equal(
        pd.read_csv(tmp_path / "mid_trend_round2_baseline_test_summary.csv"),
        _baseline_payload["test_summary"],
    )
    assert (tmp_path / "mid_trend_round2_baseline_train_summary.csv").exists()
    assert (tmp_path / "mid_trend_round2_baseline_test_summary.csv").exists()


def test_default_round2_config_uses_required_optimization_goal_hierarchy() -> None:
    assert DEFAULT_MID_TREND_ROUND2_CONFIG.primary_goal == "hold_winners_longer"
    assert DEFAULT_MID_TREND_ROUND2_CONFIG.secondary_goal == "reduce_low_value_turnover"
    assert "max_drawdown" in DEFAULT_MID_TREND_ROUND2_CONFIG.hard_constraints
    assert "monthly_win_rate" in DEFAULT_MID_TREND_ROUND2_CONFIG.hard_constraints
    assert "return_drawdown_ratio" in DEFAULT_MID_TREND_ROUND2_CONFIG.hard_constraints


@pytest.fixture
def _baseline_payload() -> dict[str, pd.DataFrame]:
    return {
        "train_summary": pd.DataFrame([{"metric": "winner_loss_count", "value": 10}]),
        "test_summary": pd.DataFrame([{"metric": "winner_loss_count", "value": 7}]),
    }
