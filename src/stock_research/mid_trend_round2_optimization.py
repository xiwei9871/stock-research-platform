from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class MidTrendRound2Config:
    primary_goal: str = "hold_winners_longer"
    secondary_goal: str = "reduce_low_value_turnover"
    hard_constraints: tuple[str, ...] = (
        "max_drawdown",
        "monthly_win_rate",
        "return_drawdown_ratio",
    )


DEFAULT_MID_TREND_ROUND2_CONFIG = MidTrendRound2Config()


def build_mid_trend_round2_baseline_artifacts(
    *,
    start_date: str,
    train_end_date: str,
    end_date: str,
    output_dir: str | Path,
    baseline_payload: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    train_summary = baseline_payload["train_summary"].copy()
    train_summary["split_name"] = "train"
    test_summary = baseline_payload["test_summary"].copy()
    test_summary["split_name"] = "test"

    train_path = output / "mid_trend_round2_baseline_train_summary.csv"
    test_path = output / "mid_trend_round2_baseline_test_summary.csv"
    train_summary.to_csv(train_path, index=False)
    test_summary.to_csv(test_path, index=False)

    return {
        "config": {
            "start_date": start_date,
            "train_end_date": train_end_date,
            "end_date": end_date,
            "primary_goal": DEFAULT_MID_TREND_ROUND2_CONFIG.primary_goal,
            "secondary_goal": DEFAULT_MID_TREND_ROUND2_CONFIG.secondary_goal,
        },
        "baseline_train_summary": train_summary,
        "baseline_test_summary": test_summary,
        "paths": {
            "train_summary": str(train_path),
            "test_summary": str(test_path),
        },
    }
