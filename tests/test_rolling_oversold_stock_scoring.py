from datetime import date

import pandas as pd
import pytest

from stock_research.rolling_oversold.contracts import RollingOversoldConfig
from stock_research.rolling_oversold.stock_scoring import (
    classify_stock_lifecycle,
    score_rolling_stock_candidates,
)


def _config() -> RollingOversoldConfig:
    return RollingOversoldConfig(anchor_start_date=date(2026, 7, 3))


def _sectors(*, gate: str = "confirmed", state: str = "repairing") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_oversold_score": 80.0,
                "sector_repairability_score": 75.0,
                "sector_direction_score": 65.0,
                "sector_recovery_state": state,
                "sector_gate_status": gate,
            }
        ]
    )


def _stocks() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "000002",
                "industry_system": " sw ",
                "industry_code": " I1 ",
                "industry_name": "Industry one",
                "anchor_return": 0.02,
                "distance_to_252d_high": 0.30,
                "oversold_depth": 0.32,
                "stock_excess_return": 0.10,
                "activity": 200.0,
                "quality": 80.0,
                "valuation": 75.0,
                "size_elasticity": 20.0,
            },
            {
                "asset_id": "000001",
                "industry_system": "sw",
                "industry_code": "I1",
                "industry_name": "Industry one",
                "anchor_return": 0.12,
                "distance_to_252d_high": 0.25,
                "oversold_depth": 0.35,
                "stock_excess_return": 0.12,
                "activity": 300.0,
                "quality": 85.0,
                "valuation": 80.0,
                "size_elasticity": 10.0,
            },
        ]
    )


def test_blocked_sector_is_excluded_while_confirmed_sector_ranks_by_actual_score():
    sectors = pd.concat(
        [
            _sectors(),
            _sectors(gate="blocked").assign(sector_code="I2", sector_name="Blocked"),
        ],
        ignore_index=True,
    )
    stocks = pd.concat(
        [
            _stocks(),
            _stocks().iloc[[0]].assign(asset_id="000003", industry_code="I2", oversold_depth=0.95),
        ],
        ignore_index=True,
    )

    result = score_rolling_stock_candidates(stocks, sectors, top_n=10, config=_config())

    assert result["asset_id"].tolist() == ["000001", "000002"]
    assert result["stock_score"].is_monotonic_decreasing
    assert result["stock_rank"].tolist() == [1, 2]
    assert set(result["score_status"]) == {"scored"}


def test_lifecycle_classifies_rebound_with_residual_space():
    assert classify_stock_lifecycle(
        anchor_return=0.12,
        distance_to_252d_high=0.25,
        sector_recovery_state="repairing",
        sector_gate_status="confirmed",
        repair_trigger_return=0.10,
        residual_high_distance=0.20,
    ) == "repair_with_residual_space"


def test_lifecycle_classifies_near_high_repaired_sector_as_confirmed_repair():
    assert classify_stock_lifecycle(
        anchor_return=0.12,
        distance_to_252d_high=0.05,
        sector_recovery_state="repaired",
        sector_gate_status="watch",
        repair_trigger_return=0.10,
        residual_high_distance=0.20,
    ) == "confirmed_repair"


def test_lifecycle_classifies_blocked_sector_as_invalidated():
    assert classify_stock_lifecycle(
        anchor_return=0.0,
        distance_to_252d_high=0.30,
        sector_recovery_state="fresh_oversold",
        sector_gate_status="blocked",
        repair_trigger_return=0.10,
        residual_high_distance=0.20,
    ) == "invalidated"


def test_lifecycle_classifies_below_trigger_fresh_oversold_as_new_oversold():
    assert classify_stock_lifecycle(
        anchor_return=0.05,
        distance_to_252d_high=0.30,
        sector_recovery_state="fresh_oversold",
        sector_gate_status="watch",
        repair_trigger_return=0.10,
        residual_high_distance=0.20,
    ) == "new_oversold"


def test_lifecycle_classifies_other_nonblocked_state_as_expected_repair_and_selects_it():
    assert classify_stock_lifecycle(
        anchor_return=0.05,
        distance_to_252d_high=0.30,
        sector_recovery_state="repaired",
        sector_gate_status="watch",
        repair_trigger_return=0.10,
        residual_high_distance=0.20,
    ) == "expected_repair"

    result = score_rolling_stock_candidates(
        _stocks().assign(anchor_return=0.05),
        _sectors(gate="watch", state="repaired"),
        top_n=2,
        config=_config(),
    )

    assert result["stock_lifecycle"].tolist() == ["expected_repair", "expected_repair"]


def test_missing_sector_context_names_asset_and_key_and_blocked_never_selects():
    stocks = _stocks().iloc[[0]].copy()
    stocks.loc[:, "industry_code"] = "MISSING"

    with pytest.raises(ValueError, match=r"asset 000002.*sw/MISSING"):
        score_rolling_stock_candidates(stocks, _sectors(), top_n=5, config=_config())

    blocked = _sectors(gate="blocked")
    assert score_rolling_stock_candidates(_stocks(), blocked, top_n=5, config=_config()).empty


def test_missing_matched_sector_name_or_recovery_state_fails_closed():
    missing_name = _sectors().assign(sector_name=pd.NA)
    with pytest.raises(ValueError, match=r"asset 000001.*sector_name"):
        score_rolling_stock_candidates(_stocks(), missing_name, top_n=5, config=_config())

    missing_state = _sectors().assign(sector_recovery_state=pd.NA)
    with pytest.raises(ValueError, match=r"asset 000001.*sector_recovery_state"):
        score_rolling_stock_candidates(_stocks(), missing_state, top_n=5, config=_config())


def test_residual_space_candidate_remains_selected_when_top_n_permits():
    result = score_rolling_stock_candidates(_stocks(), _sectors(), top_n=2, config=_config())

    row = result.loc[result["asset_id"].eq("000001")].iloc[0]
    assert row["stock_lifecycle"] == "repair_with_residual_space"
    assert len(result) == 2


def test_tie_order_is_input_order_invariant_and_inputs_are_unchanged():
    stocks = _stocks()
    stocks.loc[:, ["oversold_depth", "stock_excess_return", "activity", "quality", "valuation", "size_elasticity"]] = [
        0.30,
        0.05,
        100.0,
        70.0,
        70.0,
        50.0,
    ]
    stocks.loc[:, "anchor_return"] = 0.01
    stocks.loc[:, "distance_to_252d_high"] = 0.30
    sectors = _sectors()
    stocks_before = stocks.copy(deep=True)
    sectors_before = sectors.copy(deep=True)

    first = score_rolling_stock_candidates(stocks, sectors, top_n=2, config=_config())
    second = score_rolling_stock_candidates(
        stocks.sample(frac=1.0, random_state=7).reset_index(drop=True),
        sectors.sample(frac=1.0, random_state=11).reset_index(drop=True),
        top_n=2,
        config=_config(),
    )

    assert first["asset_id"].tolist() == ["000001", "000002"]
    pd.testing.assert_frame_equal(first.reset_index(drop=True), second.reset_index(drop=True))
    pd.testing.assert_frame_equal(stocks, stocks_before)
    pd.testing.assert_frame_equal(sectors, sectors_before)


def test_empty_input_has_stable_required_schema():
    result = score_rolling_stock_candidates(pd.DataFrame(), pd.DataFrame(), top_n=3, config=_config())

    assert result.empty
    assert {
        "sector_system",
        "sector_code",
        "sector_name",
        "sector_oversold_score",
        "sector_repairability_score",
        "sector_direction_score",
        "sector_recovery_state",
        "sector_gate_status",
        "asset_id",
        "stock_score",
        "stock_rank",
        "stock_lifecycle",
        "score_status",
        "score_reason",
    }.issubset(result.columns)
