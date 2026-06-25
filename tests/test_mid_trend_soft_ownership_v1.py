from pathlib import Path

import pandas as pd

from stock_research.mid_trend_soft_ownership_v1 import (
    DEFAULT_SOFT_OWNERSHIP_END_DATE,
    DEFAULT_SOFT_OWNERSHIP_START_DATE,
    MidTrendSoftOwnershipConfig,
    default_soft_ownership_configs,
)


def test_default_window_is_fixed_full_experiment_window() -> None:
    assert DEFAULT_SOFT_OWNERSHIP_START_DATE == "2025-01-01"
    assert DEFAULT_SOFT_OWNERSHIP_END_DATE == "2026-06-12"


def test_default_soft_ownership_configs_expose_required_variants() -> None:
    configs = default_soft_ownership_configs()
    assert set(configs) == {
        "baseline",
        "entry_soft_weight_v1",
        "ownership_hold_v1",
        "partial_exit_v1",
        "combined_soft_ownership_v1",
    }
    assert configs["baseline"].variant_name == "baseline"
    assert configs["combined_soft_ownership_v1"].start_date == "2025-01-01"
