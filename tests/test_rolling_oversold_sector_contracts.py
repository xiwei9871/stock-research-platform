from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stock_research.rolling_oversold.contracts import (
    REQUIRED_SECTOR_COLUMNS,
    SectorResearchEligibility,
)
from stock_research.rolling_oversold.reporting import (
    load_rolling_oversold_snapshot,
    write_rolling_sector_oversold_report,
)
from stock_research.rolling_oversold.snapshots import (
    build_rolling_snapshot,
    write_rolling_snapshot,
)


ANCHOR = date(2026, 7, 31)
CUTOFF = date(2026, 7, 30)

_NEW_FEATURES = {
    "sector_low_date_20d": "2026-07-28",
    "sector_low_close_20d": 88.0,
    "sector_recovery_from_low_20d": 94.0 / 88.0 - 1.0,
    "sector_days_since_low_20d": 2,
    "sector_volume_ratio_5_20": 1.4,
    "sector_ma5_slope_5d": 0.02,
    "sector_ma10_slope_10d": 0.01,
    "sector_research_eligibility": "eligible",
}


def _sector_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "sector_system": "ths",
        "sector_code": "300238",
        "sector_name": "核电",
        "sector_oversold_score": 84.0,
        "sector_repairability_score": 72.0,
        "sector_direction_score": 61.0,
        "sector_recovery_state": "repairing",
        "sector_gate_status": "confirmed",
        **_NEW_FEATURES,
    }
    row.update(overrides)
    return row


def _snapshot(
    *,
    sectors: pd.DataFrame | None = None,
    market_regime: dict[str, object] | None = None,
) -> dict[str, object]:
    return build_rolling_snapshot(
        anchor_date=ANCHOR,
        data_cutoff_date=CUTOFF,
        market_regime=market_regime or {"market_regime": "risk_off"},
        sector_states=pd.DataFrame([_sector_row()]) if sectors is None else sectors,
        stock_candidates=pd.DataFrame(),
        previous_snapshot=None,
        score_version="rolling_oversold_v2",
    )


def test_sector_repair_columns_are_required_and_eligibility_is_explicit():
    assert {
        "sector_low_date_20d",
        "sector_low_close_20d",
        "sector_recovery_from_low_20d",
        "sector_days_since_low_20d",
        "sector_volume_ratio_5_20",
        "sector_ma5_slope_5d",
        "sector_ma10_slope_10d",
        "sector_research_eligibility",
    }.issubset(REQUIRED_SECTOR_COLUMNS)
    assert {item.value for item in SectorResearchEligibility} == {
        "eligible",
        "watch",
        "blocked_data",
    }


def test_snapshot_rejects_sector_frame_missing_new_canonical_column(tmp_path):
    snapshot = _snapshot()
    tampered = dict(snapshot)
    tampered["sector_states"] = snapshot["sector_states"].drop(
        columns=["sector_ma10_slope_10d"]
    )

    with pytest.raises(ValueError, match="sector.*canonical|sector_ma10_slope_10d"):
        write_rolling_snapshot(tampered, output_dir=tmp_path)


def test_blocked_data_sector_allows_empty_features_only_with_structured_gap(tmp_path):
    blocked = pd.DataFrame(
        [
            _sector_row(
                sector_oversold_score=pd.NA,
                sector_repairability_score=pd.NA,
                sector_direction_score=pd.NA,
                sector_recovery_state="unknown",
                sector_gate_status="blocked",
                sector_research_eligibility="blocked_data",
                **{
                    key: pd.NA
                    for key in _NEW_FEATURES
                    if key != "sector_research_eligibility"
                },
            )
        ]
    )
    snapshot = _snapshot(
        sectors=blocked,
        market_regime={
            "market_regime": "risk_off",
            "preflight": {
                "gaps": [
                    {
                        "dataset": "market.ths_daily_bar",
                        "asset_id": "ths:300238",
                        "start_date": "2026-07-30",
                        "end_date": "2026-07-30",
                        "expected_rows": 1,
                        "actual_rows": 0,
                        "reason": "missing_cutoff_sector_bar",
                    }
                ]
            },
        },
    )

    result = write_rolling_snapshot(snapshot, output_dir=tmp_path)
    assert result["status"] == "created"


def test_blocked_data_sector_without_structured_gap_is_rejected(tmp_path):
    blocked = pd.DataFrame(
        [
            _sector_row(
                sector_oversold_score=pd.NA,
                sector_repairability_score=pd.NA,
                sector_direction_score=pd.NA,
                sector_recovery_state="unknown",
                sector_gate_status="blocked",
                sector_research_eligibility="blocked_data",
                **{
                    key: pd.NA
                    for key in _NEW_FEATURES
                    if key != "sector_research_eligibility"
                },
            )
        ]
    )
    snapshot = _snapshot(sectors=blocked)

    with pytest.raises(ValueError, match="structured data gap|gap"):
        write_rolling_snapshot(snapshot, output_dir=tmp_path)


def test_sector_features_round_trip_through_csv_manifest_and_report(tmp_path):
    snapshot = _snapshot()
    result = write_rolling_snapshot(snapshot, output_dir=tmp_path)
    artifact_dir = Path(result["manifest_path"]).parent

    loaded = load_rolling_oversold_snapshot(artifact_dir)
    sectors = loaded["sector_states"]
    assert list(sectors.loc[:, REQUIRED_SECTOR_COLUMNS].columns) == list(REQUIRED_SECTOR_COLUMNS)
    for column, value in _NEW_FEATURES.items():
        if column == "sector_research_eligibility":
            assert sectors.loc[0, column] == value
        elif column == "sector_low_date_20d":
            assert sectors.loc[0, column] == value
        else:
            assert float(sectors.loc[0, column]) == pytest.approx(float(value))

    report_path = write_rolling_sector_oversold_report(
        output_dir=tmp_path / "report", snapshot_dir=artifact_dir
    )
    report = report_path.read_text(encoding="utf-8")
    assert "sector_research_eligibility" in report
    assert "sector_low_close_20d" in report


def test_legacy_v1_inputs_are_compatibly_augmented():
    legacy = pd.DataFrame(
        [
            {
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_oversold_score": 78.0,
                "sector_repairability_score": 66.0,
                "sector_direction_score": 49.0,
                "sector_recovery_state": "fresh_oversold",
                "sector_gate_status": "watch",
            }
        ]
    )
    snapshot = _snapshot(sectors=legacy)
    assert set(REQUIRED_SECTOR_COLUMNS).issubset(snapshot["sector_states"].columns)
    assert snapshot["sector_states"].loc[0, "sector_research_eligibility"] == "watch"


def test_legacy_removed_sector_revision_keeps_v1_feature_blanks(tmp_path):
    legacy = pd.DataFrame(
        [
            {
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_oversold_score": 78.0,
                "sector_repairability_score": 66.0,
                "sector_direction_score": 49.0,
                "sector_recovery_state": "fresh_oversold",
                "sector_gate_status": "watch",
            }
        ]
    )
    previous = _snapshot(sectors=legacy)
    current = build_rolling_snapshot(
        anchor_date=ANCHOR,
        data_cutoff_date=CUTOFF,
        market_regime={"market_regime": "risk_off"},
        sector_states=pd.DataFrame([_sector_row(sector_code="300239")]),
        stock_candidates=pd.DataFrame(),
        previous_snapshot=previous,
        score_version="rolling_oversold_v2",
    )

    removed = current["sector_states"].loc[
        current["sector_states"]["sector_revision_status"].eq("removed")
    ]
    assert len(removed) == 1
    assert pd.isna(removed.iloc[0]["sector_low_close_20d"])
    assert write_rolling_snapshot(current, output_dir=tmp_path)["status"] == "created"


def test_unknown_legacy_gate_maps_to_watch_research_eligibility():
    legacy = pd.DataFrame(
        [
            {
                "sector_system": "sw",
                "sector_code": "I9",
                "sector_name": "Legacy sector",
                "sector_oversold_score": 45.0,
                "sector_repairability_score": 51.0,
                "sector_direction_score": 48.0,
                "sector_recovery_state": "unknown",
                "sector_gate_status": "legacy_gate",
            }
        ]
    )

    snapshot = _snapshot(sectors=legacy)

    assert snapshot["sector_states"].loc[0, "sector_research_eligibility"] == "watch"
