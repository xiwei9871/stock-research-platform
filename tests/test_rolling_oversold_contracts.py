from datetime import date

import pytest

from stock_research.rolling_oversold.contracts import (
    REQUIRED_SNAPSHOT_COLUMNS,
    GateStatus,
    RecoveryState,
    RollingOversoldConfig,
    StockLifecycle,
    validate_snapshot_columns,
)


def test_config_preserves_anchor_and_exposes_contract_defaults():
    config = RollingOversoldConfig(anchor_start_date=date(2026, 7, 21))

    assert config.anchor_start_date == date(2026, 7, 21)
    assert config.forecast_horizons == (1, 3, 5)
    assert config.score_version == "rolling_oversold_v1"
    assert config.index_ids == (
        "SSE_COMPOSITE",
        "SZSE_COMPONENT",
        "CSI_300",
        "STAR_50",
        "BSE_50",
    )
    assert config.adjust_type == "qfq"


@pytest.mark.parametrize(
    ("kwargs", "field_name"),
    [
        ({"forecast_horizons": (1, 1, 3)}, "forecast_horizons"),
        ({"forecast_horizons": (3, 1, 5)}, "forecast_horizons"),
        ({"anchor_end_date": date(2026, 7, 20)}, "anchor_end_date"),
        ({"sector_top_n": 0}, "sector_top_n"),
        ({"stock_top_n": 0}, "stock_top_n"),
        ({"repair_trigger_return": 0.0}, "repair_trigger_return"),
        ({"residual_high_distance": 1.0}, "residual_high_distance"),
        ({"adjust_type": "invalid"}, "adjust_type"),
        ({"runtime_budget_seconds": 0}, "runtime_budget_seconds"),
    ],
)
def test_config_rejects_invalid_values(kwargs, field_name):
    with pytest.raises(ValueError, match=field_name):
        RollingOversoldConfig(anchor_start_date=date(2026, 7, 21), **kwargs)


def test_config_normalizes_optional_system_sequences_to_immutable_tuples():
    config = RollingOversoldConfig(
        anchor_start_date=date(2026, 7, 21),
        industry_systems=["sw", "citics"],
        concept_systems=["eastmoney"],
    )

    assert config.industry_systems == ("sw", "citics")
    assert config.concept_systems == ("eastmoney",)


def test_contract_enums_use_stable_values_and_include_all_design_states():
    assert GateStatus.CONFIRMED.value == "confirmed"
    assert RecoveryState.REPAIR_WITH_RESIDUAL_SPACE.value == "repair_with_residual_space"
    assert StockLifecycle.INVALIDATED.value == "invalidated"
    assert {state.value for state in GateStatus} == {"confirmed", "watch", "blocked"}
    assert {state.value for state in RecoveryState} == {
        "fresh_oversold",
        "repairing",
        "repaired",
        "structurally_weak",
        "unknown",
        "repair_with_residual_space",
    }
    assert {state.value for state in StockLifecycle} == {
        "new_oversold",
        "expected_repair",
        "confirmed_repair",
        "repair_with_residual_space",
        "invalidated",
    }


def test_snapshot_column_contract_covers_identity_scores_states_and_deltas():
    required = {
        "snapshot_id",
        "anchor_date",
        "data_cutoff_date",
        "score_version",
        "market_regime",
        "sector_id",
        "sector_name",
        "sector_score",
        "sector_rank",
        "sector_recovery_state",
        "sector_gate_status",
        "asset_id",
        "stock_score",
        "stock_rank",
        "stock_lifecycle",
        "previous_snapshot_id",
        "rank_delta",
        "lifecycle_delta",
    }

    assert required.issubset(REQUIRED_SNAPSHOT_COLUMNS)
    assert validate_snapshot_columns({"anchor_date", "asset_id"}) == sorted(
        set(REQUIRED_SNAPSHOT_COLUMNS) - {"anchor_date", "asset_id"}
    )
    missing = validate_snapshot_columns({"anchor_date", "asset_id"})
    assert "data_cutoff_date" in missing
    assert "sector_gate_status" in missing
    assert "stock_lifecycle" in missing
