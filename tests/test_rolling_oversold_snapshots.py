from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.rolling_oversold import snapshots as snapshots_module
from stock_research.rolling_oversold.contracts import REQUIRED_SNAPSHOT_COLUMNS, validate_snapshot_columns
from stock_research.rolling_oversold.snapshots import (
    build_rolling_snapshot,
    write_rolling_snapshot,
)


ANCHOR = date(2026, 7, 21)
CUTOFF = date(2026, 7, 20)
VERSION = "rolling_oversold_v1"


def _market_regime() -> dict[str, object]:
    return {
        "market_regime": "risk_off",
        "market_direction_score": 31.5,
        "data_cutoff_date": CUTOFF,
    }


def _sectors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sector_system": "sw",
                "sector_code": "I2",
                "sector_name": "Industry two",
                "sector_oversold_score": 84.0,
                "sector_repairability_score": 69.0,
                "sector_direction_score": 52.0,
                "sector_recovery_state": "repairing",
                "sector_gate_status": "confirmed",
            },
            {
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_oversold_score": 78.0,
                "sector_repairability_score": 66.0,
                "sector_direction_score": 49.0,
                "sector_recovery_state": "fresh_oversold",
                "sector_gate_status": "watch",
            },
        ]
    )


def _stocks() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "000002",
                "sector_system": "sw",
                "sector_code": "I2",
                "sector_name": "Industry two",
                "sector_oversold_score": 84.0,
                "sector_repairability_score": 69.0,
                "sector_direction_score": 52.0,
                "sector_recovery_state": "repairing",
                "sector_gate_status": "confirmed",
                "stock_score": 82.0,
                "stock_rank": 2,
                "stock_lifecycle": "expected_repair",
                "anchor_close": 10.0,
                "adjusted_close_source": "qfq",
                "score_reason": "",
            },
            {
                "asset_id": "000001",
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_oversold_score": 78.0,
                "sector_repairability_score": 66.0,
                "sector_direction_score": 49.0,
                "sector_recovery_state": "fresh_oversold",
                "sector_gate_status": "watch",
                "stock_score": 91.0,
                "stock_rank": 1,
                "stock_lifecycle": "new_oversold",
                "anchor_close": 10.0,
                "adjusted_close_source": "qfq",
                "score_reason": "",
            },
        ]
    )


def _build(
    *,
    stocks: pd.DataFrame | None = None,
    sectors: pd.DataFrame | None = None,
    previous: dict[str, object] | None = None,
    anchor: date = ANCHOR,
    runtime_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return build_rolling_snapshot(
        anchor_date=anchor,
        data_cutoff_date=CUTOFF,
        market_regime=_market_regime(),
        sector_states=_sectors() if sectors is None else sectors,
        stock_candidates=_stocks() if stocks is None else stocks,
        previous_snapshot=previous,
        score_version=VERSION,
        runtime_metadata=runtime_metadata,
    )


def test_build_snapshot_assigns_exact_metadata_and_normalizes_contract_rows():
    snapshot = _build()

    assert snapshot["snapshot_id"] == "rolling_oversold_v1|2026-07-21"
    assert snapshot["anchor_date"] == "2026-07-21"
    assert snapshot["data_cutoff_date"] == "2026-07-20"
    assert snapshot["score_version"] == VERSION
    assert snapshot["previous_snapshot_id"] is None
    assert snapshot["market_regime"]["market_regime"] == "risk_off"
    assert snapshot["row_counts"] == {"sector_states": 2, "stock_candidates": 2}
    assert snapshot["stock_candidates"]["asset_id"].tolist() == ["000001", "000002"]
    assert validate_snapshot_columns(snapshot["stock_candidates"].columns) == []
    assert set(REQUIRED_SNAPSHOT_COLUMNS).issubset(snapshot["stock_candidates"].columns)


def test_build_rejects_eligible_rows_without_frozen_outcome_inputs():
    stocks = _stocks().copy(deep=True)
    stocks.loc[:, ["anchor_close", "adjusted_close_source"]] = pd.NA

    with pytest.raises(ValueError, match="eligible.*anchor_close"):
        _build(stocks=stocks)


def test_build_allows_excluded_rows_without_frozen_outcome_inputs():
    stocks = _stocks().iloc[[0]].copy(deep=True)
    stocks.loc[:, ["anchor_close", "adjusted_close_source"]] = pd.NA
    stocks.loc[:, "sector_gate_status"] = "blocked"
    stocks.loc[:, "sector_recovery_state"] = "unknown"
    sectors = _sectors().iloc[[0]].copy(deep=True)
    sectors.loc[:, "sector_gate_status"] = "blocked"
    sectors.loc[:, "sector_recovery_state"] = "unknown"
    stocks.loc[:, ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]] = pd.NA
    sectors.loc[:, ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]] = pd.NA

    snapshot = _build(stocks=stocks, sectors=sectors)

    assert pd.isna(snapshot["stock_candidates"].loc[0, "anchor_close"])


def test_build_normalizes_mixed_case_gate_and_lifecycle_statuses_for_exclusions():
    blocked_stocks = _stocks().iloc[[0]].copy(deep=True)
    blocked_stocks.loc[:, "sector_gate_status"] = "  BLOCKED "
    blocked_stocks.loc[:, "sector_recovery_state"] = " UNKNOWN "
    blocked_sectors = _sectors().iloc[[0]].copy(deep=True)
    blocked_sectors.loc[:, "sector_gate_status"] = " BLOCKED "
    blocked_sectors.loc[:, "sector_recovery_state"] = " UNKNOWN "
    blocked_stocks.loc[:, ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]] = pd.NA
    blocked_sectors.loc[:, ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]] = pd.NA

    blocked = _build(stocks=blocked_stocks, sectors=blocked_sectors)

    assert blocked["stock_candidates"].loc[0, "sector_gate_status"] == "blocked"
    assert blocked["stock_candidates"].loc[0, "sector_recovery_state"] == "unknown"


def test_snapshot_revisions_link_ranks_and_keep_absent_asset_as_invalidated_row():
    previous = _build(stocks=_stocks().assign(stock_rank=[3, 2]))
    current_stocks = _stocks().iloc[[1]].copy()
    current_stocks.loc[:, "asset_id"] = "000003"
    current_stocks.loc[:, "stock_rank"] = 1
    current_stocks.loc[:, "stock_lifecycle"] = "expected_repair"
    current = _build(stocks=current_stocks, previous=previous)

    new_row = current["stock_candidates"].loc[
        current["stock_candidates"]["asset_id"].eq("000003")
    ].iloc[0]
    assert new_row["previous_snapshot_id"] == previous["snapshot_id"]
    assert pd.isna(new_row["rank_delta"])
    assert new_row["lifecycle_delta"] == "absent->expected_repair"

    removed = current["stock_candidates"].loc[
        current["stock_candidates"]["asset_id"].eq("000001")
    ].iloc[0]
    assert removed["stock_lifecycle"] == "invalidated"
    assert removed["lifecycle_delta"] == "new_oversold->invalidated"
    assert pd.isna(removed["stock_rank"])
    assert removed["score_reason"] == "sector_gate_or_data_change"


def test_snapshot_build_preserves_invalidated_historical_sector_context_when_sector_changes(tmp_path):
    previous = _build()
    current_sectors = _sectors().copy()
    current_sectors.loc[
        current_sectors["sector_code"].eq("I1"),
        [
            "sector_oversold_score",
            "sector_repairability_score",
            "sector_direction_score",
            "sector_recovery_state",
            "sector_gate_status",
        ],
    ] = [91.0, 73.0, 61.0, "repairing", "confirmed"]

    current = _build(
        stocks=_stocks().iloc[[0]].copy(),
        sectors=current_sectors,
        previous=previous,
    )

    invalidated = current["stock_candidates"].loc[
        current["stock_candidates"]["asset_id"].eq("000001")
    ].iloc[0]
    current_sector = current["sector_states"].loc[
        current["sector_states"]["sector_code"].eq("I1")
    ].iloc[0]
    assert invalidated["stock_lifecycle"] == "invalidated"
    assert invalidated["sector_oversold_score"] == 78.0
    assert current_sector["sector_oversold_score"] == 91.0
    assert write_rolling_snapshot(current, output_dir=tmp_path)["status"] == "created"


def test_write_rejects_root_invalidation_with_conflicting_sector_context(tmp_path):
    snapshot = _build()
    tampered = dict(snapshot)
    tampered["stock_candidates"] = snapshot["stock_candidates"].copy(deep=True)
    tampered["stock_candidates"].loc[:, "stock_lifecycle"] = "invalidated"
    tampered["stock_candidates"].loc[:, "stock_rank"] = pd.NA
    tampered["stock_candidates"].loc[:, "score_reason"] = "sector_gate_or_data_change"
    tampered["stock_candidates"].loc[:, "lifecycle_delta"] = "new_oversold->invalidated"
    tampered["stock_candidates"].loc[:, "sector_name"] = "Tampered sector name"

    with pytest.raises(ValueError, match="sector context conflicts.*sector_name"):
        write_rolling_snapshot(tampered, output_dir=tmp_path)


def test_build_rejects_active_stock_rows_with_conflicting_sector_context():
    stocks = _stocks().copy()
    stocks.loc[:, "sector_name"] = "Tampered sector name"

    with pytest.raises(ValueError, match="sector context conflicts.*sector_name"):
        _build(stocks=stocks)


def test_build_rejects_ranked_invalidated_stock_with_conflicting_sector_context():
    stocks = _stocks().copy()
    stocks.loc[:, "stock_lifecycle"] = "invalidated"
    stocks.loc[:, "sector_name"] = "Tampered sector name"

    with pytest.raises(ValueError, match="sector context conflicts.*sector_name"):
        _build(stocks=stocks)


def test_snapshot_revisions_compute_previous_rank_minus_current_rank():
    previous = _build(stocks=_stocks().assign(stock_rank=[3, 2]))
    current = _build(stocks=_stocks().iloc[[0]].assign(stock_rank=1), previous=previous)

    row = current["stock_candidates"].loc[
        current["stock_candidates"]["asset_id"].eq("000002")
    ].iloc[0]
    assert row["rank_delta"] == 2
    assert row["lifecycle_delta"] == "expected_repair->expected_repair"


def test_snapshot_build_is_permutation_invariant_and_does_not_mutate_frames():
    stocks = _stocks()
    sectors = _sectors()
    stocks_before = stocks.copy(deep=True)
    sectors_before = sectors.copy(deep=True)

    first = _build(stocks=stocks, sectors=sectors)
    second = _build(
        stocks=stocks.sample(frac=1.0, random_state=9).reset_index(drop=True),
        sectors=sectors.sample(frac=1.0, random_state=11).reset_index(drop=True),
    )

    pd.testing.assert_frame_equal(first["stock_candidates"], second["stock_candidates"])
    pd.testing.assert_frame_equal(first["sector_states"], second["sector_states"])
    pd.testing.assert_frame_equal(stocks, stocks_before)
    pd.testing.assert_frame_equal(sectors, sectors_before)


def test_write_snapshot_is_immutable_and_has_hashed_deterministic_artifacts(tmp_path):
    snapshot = _build()
    first = write_rolling_snapshot(snapshot, output_dir=tmp_path)
    manifest_path = tmp_path / "rolling_sector_oversold" / "anchor=2026-07-21" / f"version={VERSION}" / "manifest.json"
    original_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    assert first["status"] == "created"
    assert first["manifest_path"] == str(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == snapshot["snapshot_id"]
    assert manifest["row_counts"] == {"sector_states": 2, "stock_candidates": 2}
    assert set(manifest["artifact_hashes"]) == {
        "market_regime.csv",
        "sector_states.csv",
        "stock_candidates.csv",
        "preflight.json",
        "backfill_requests.csv",
    }
    for name, digest in manifest["artifact_hashes"].items():
        assert hashlib.sha256((manifest_path.parent / name).read_bytes()).hexdigest() == digest
    assert not list(manifest_path.parent.rglob("*.tmp"))

    assert write_rolling_snapshot(snapshot, output_dir=tmp_path)["status"] == "already_exists_identical"
    changed = _build(stocks=_stocks().assign(stock_score=[82.0, 92.0]))
    with pytest.raises(ValueError, match="immutable rolling snapshot"):
        write_rolling_snapshot(changed, output_dir=tmp_path)
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == original_manifest_hash


def test_write_snapshot_publishes_evaluation_sidecars_with_manifest(tmp_path):
    snapshot = _build()
    extras = {
        "evaluation_detail.csv": b"asset_id,forward_Nd_status\nA,complete\n",
        "evaluation_summary.csv": b"forward_horizon_days,complete_count\n1,1\n",
    }

    result = write_rolling_snapshot(
        snapshot,
        output_dir=tmp_path,
        additional_artifacts=extras,
    )

    artifact_dir = Path(result["manifest_path"]).parent
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert (artifact_dir / "evaluation_detail.csv").read_bytes() == extras["evaluation_detail.csv"]
    assert (artifact_dir / "evaluation_summary.csv").read_bytes() == extras["evaluation_summary.csv"]
    assert manifest["artifact_hashes"]["evaluation_detail.csv"] == hashlib.sha256(
        extras["evaluation_detail.csv"]
    ).hexdigest()
    assert manifest["artifact_hashes"]["evaluation_summary.csv"] == hashlib.sha256(
        extras["evaluation_summary.csv"]
    ).hexdigest()


def test_empty_snapshot_uses_stable_schemas_and_required_artifact_names(tmp_path):
    snapshot = _build(stocks=pd.DataFrame(), sectors=pd.DataFrame())
    assert snapshot["stock_candidates"].empty
    assert snapshot["sector_states"].empty
    assert validate_snapshot_columns(snapshot["stock_candidates"].columns) == []

    result = write_rolling_snapshot(snapshot, output_dir=tmp_path)
    assert Path(result["manifest_path"]).is_file()
    artifact_dir = tmp_path / "rolling_sector_oversold" / "anchor=2026-07-21" / f"version={VERSION}"
    assert {path.name for path in artifact_dir.iterdir()} == {
        "manifest.json",
        "market_regime.csv",
        "sector_states.csv",
        "stock_candidates.csv",
        "preflight.json",
        "backfill_requests.csv",
    }
    assert (artifact_dir / "backfill_requests.csv").read_text(encoding="utf-8") == (
        "dataset,asset_id,start_date,end_date,expected_rows,actual_rows,reason\n"
    )


def test_blocked_unknown_sector_with_missing_scores_serializes_as_blank(tmp_path):
    blocked = _sectors().iloc[[0]].copy()
    blocked.loc[:, ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]] = pd.NA
    blocked.loc[:, "sector_gate_status"] = "blocked"
    blocked.loc[:, "sector_recovery_state"] = "unknown"
    snapshot = _build(stocks=pd.DataFrame(), sectors=blocked)

    result = write_rolling_snapshot(snapshot, output_dir=tmp_path)
    sector_csv = Path(result["manifest_path"]).with_name("sector_states.csv").read_text(encoding="utf-8")
    assert "Industry two" in sector_csv
    assert ",,," in sector_csv


def test_failed_staging_write_cleans_temp_and_allows_retry(tmp_path, monkeypatch):
    snapshot = _build()
    original = snapshots_module._atomic_write_new

    def fail_once(path, contents):
        if path.name == "stock_candidates.csv":
            raise RuntimeError("injected artifact failure")
        return original(path, contents)

    monkeypatch.setattr(snapshots_module, "_atomic_write_new", fail_once)
    with pytest.raises(RuntimeError, match="injected artifact failure"):
        write_rolling_snapshot(snapshot, output_dir=tmp_path)

    destination = tmp_path / "rolling_sector_oversold" / "anchor=2026-07-21" / f"version={VERSION}"
    assert not destination.exists()
    assert not list(destination.parent.glob(f".{destination.name}.*"))

    monkeypatch.setattr(snapshots_module, "_atomic_write_new", original)
    assert write_rolling_snapshot(snapshot, output_dir=tmp_path)["status"] == "created"


def test_runtime_metadata_round_trips_and_json_normalizes_decimal_and_nonfinite_values(tmp_path):
    snapshot = _build(
        runtime_metadata={
            "stage_timings": {"build_seconds": Decimal("1.25")},
            "nan_value": float("nan"),
            "nat_value": pd.NaT,
        }
    )
    assert snapshot["runtime_metadata"] == {
        "stage_timings": {"build_seconds": 1.25},
        "nan_value": None,
        "nat_value": None,
    }

    result = write_rolling_snapshot(snapshot, output_dir=tmp_path)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["runtime_metadata"] == snapshot["runtime_metadata"]


def test_write_revalidates_pit_and_hand_built_frame_schema(tmp_path):
    snapshot = _build()
    invalid_cutoff = dict(snapshot)
    invalid_cutoff["data_cutoff_date"] = "2026-07-22"
    with pytest.raises(ValueError, match="data_cutoff_date"):
        write_rolling_snapshot(invalid_cutoff, output_dir=tmp_path)

    invalid_frame = dict(snapshot)
    invalid_frame["stock_candidates"] = snapshot["stock_candidates"].copy(deep=True)
    invalid_frame["stock_candidates"].loc[:, "stock_score"] = "not-a-score"
    with pytest.raises(ValueError, match="stock_candidates"):
        write_rolling_snapshot(invalid_frame, output_dir=tmp_path)


def test_write_rejects_conflicting_stock_cross_artifact_metadata(tmp_path):
    snapshot = _build()

    regime_tampered = dict(snapshot)
    regime_tampered["stock_candidates"] = snapshot["stock_candidates"].copy(deep=True)
    regime_tampered["stock_candidates"].loc[:, "market_regime"] = "risk_on"
    with pytest.raises(ValueError, match="market_regime"):
        write_rolling_snapshot(regime_tampered, output_dir=tmp_path)

    linked = _build(previous=_build())
    previous_link_tampered = dict(linked)
    previous_link_tampered["stock_candidates"] = linked["stock_candidates"].copy(deep=True)
    previous_link_tampered["stock_candidates"].loc[:, "previous_snapshot_id"] = "other|2026-07-20"
    with pytest.raises(ValueError, match="previous_snapshot_id"):
        write_rolling_snapshot(previous_link_tampered, output_dir=tmp_path)


def test_write_rejects_stock_rows_without_matching_sector_state(tmp_path):
    snapshot = _build()
    tampered = dict(snapshot)
    tampered["stock_candidates"] = snapshot["stock_candidates"].copy(deep=True)
    tampered["stock_candidates"].loc[:, "sector_code"] = "missing"

    with pytest.raises(ValueError, match="missing sector state"):
        write_rolling_snapshot(tampered, output_dir=tmp_path)


@pytest.mark.parametrize(
    ("column", "tampered_value"),
    [
        ("sector_name", "Tampered sector name"),
        ("sector_oversold_score", 0.0),
        ("sector_repairability_score", 0.0),
        ("sector_direction_score", 0.0),
        ("sector_recovery_state", "unknown"),
        ("sector_gate_status", "blocked"),
    ],
)
def test_write_rejects_stock_rows_with_conflicting_sector_context(
    tmp_path, column, tampered_value
):
    snapshot = _build()
    tampered = dict(snapshot)
    tampered["stock_candidates"] = snapshot["stock_candidates"].copy(deep=True)
    tampered["stock_candidates"].loc[:, column] = tampered_value

    with pytest.raises(ValueError, match=f"sector context conflicts.*{column}"):
        write_rolling_snapshot(tampered, output_dir=tmp_path)


@pytest.mark.parametrize("previous_snapshot_id", ["", " \t "])
def test_write_rejects_blank_previous_link_for_empty_snapshot(tmp_path, previous_snapshot_id):
    snapshot = _build(stocks=pd.DataFrame(), sectors=pd.DataFrame())
    snapshot["previous_snapshot_id"] = previous_snapshot_id

    with pytest.raises(ValueError, match="previous_snapshot_id"):
        write_rolling_snapshot(snapshot, output_dir=tmp_path)


def test_write_rejects_conflicting_sector_previous_snapshot_id(tmp_path):
    linked = _build(previous=_build())
    tampered = dict(linked)
    tampered["sector_states"] = linked["sector_states"].copy(deep=True)
    tampered["sector_states"].loc[:, "previous_snapshot_id"] = "other|2026-07-20"

    with pytest.raises(ValueError, match="previous_snapshot_id"):
        write_rolling_snapshot(tampered, output_dir=tmp_path)


def test_write_allows_blocked_stock_rows_with_missing_scores_when_root_metadata_is_preserved(tmp_path):
    blocked_stocks = _stocks().iloc[[0]].copy()
    blocked_stocks.loc[:, "sector_gate_status"] = "blocked"
    blocked_stocks.loc[:, "sector_recovery_state"] = "unknown"
    blocked_stocks.loc[:, ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]] = pd.NA
    blocked_sectors = _sectors().iloc[[0]].copy()
    blocked_sectors.loc[:, "sector_gate_status"] = "blocked"
    blocked_sectors.loc[:, "sector_recovery_state"] = "unknown"
    blocked_sectors.loc[:, ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]] = pd.NA
    snapshot = _build(stocks=blocked_stocks, sectors=blocked_sectors)

    assert write_rolling_snapshot(snapshot, output_dir=tmp_path)["status"] == "created"


def test_write_rejects_blocked_rows_with_conflicting_root_metadata(tmp_path):
    blocked_stocks = _stocks().iloc[[0]].copy()
    blocked_stocks.loc[:, "sector_gate_status"] = "blocked"
    blocked_stocks.loc[:, "sector_recovery_state"] = "unknown"
    blocked_stocks.loc[:, ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]] = pd.NA
    blocked_sectors = _sectors().iloc[[0]].copy()
    blocked_sectors.loc[:, "sector_gate_status"] = "blocked"
    blocked_sectors.loc[:, "sector_recovery_state"] = "unknown"
    blocked_sectors.loc[:, ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]] = pd.NA
    snapshot = _build(stocks=blocked_stocks, sectors=blocked_sectors, previous=_build())

    regime_tampered = dict(snapshot)
    regime_tampered["stock_candidates"] = snapshot["stock_candidates"].copy(deep=True)
    regime_tampered["stock_candidates"].loc[:, "market_regime"] = "unknown"
    with pytest.raises(ValueError, match="market_regime"):
        write_rolling_snapshot(regime_tampered, output_dir=tmp_path)

    lineage_tampered = dict(snapshot)
    lineage_tampered["stock_candidates"] = snapshot["stock_candidates"].copy(deep=True)
    lineage_tampered["stock_candidates"].loc[:, "previous_snapshot_id"] = pd.NA
    with pytest.raises(ValueError, match="previous_snapshot_id"):
        write_rolling_snapshot(lineage_tampered, output_dir=tmp_path)


def test_write_rejects_invalidated_rows_with_conflicting_root_metadata(tmp_path):
    snapshot = _build(stocks=_stocks().iloc[[0]].copy(), previous=_build())
    invalidated = snapshot["stock_candidates"]["stock_lifecycle"].eq("invalidated")

    regime_tampered = dict(snapshot)
    regime_tampered["stock_candidates"] = snapshot["stock_candidates"].copy(deep=True)
    regime_tampered["stock_candidates"].loc[invalidated, "market_regime"] = "unknown"
    with pytest.raises(ValueError, match="market_regime"):
        write_rolling_snapshot(regime_tampered, output_dir=tmp_path)

    lineage_tampered = dict(snapshot)
    lineage_tampered["stock_candidates"] = snapshot["stock_candidates"].copy(deep=True)
    lineage_tampered["stock_candidates"].loc[invalidated, "previous_snapshot_id"] = pd.NA
    with pytest.raises(ValueError, match="previous_snapshot_id"):
        write_rolling_snapshot(lineage_tampered, output_dir=tmp_path)
