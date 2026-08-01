"""Deterministic, immutable artifacts for rolling sector-oversold snapshots."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

import pandas as pd

from .contracts import validate_snapshot_columns


_STOCK_CONTEXT_COLUMNS = (
    "sector_system",
    "sector_code",
    "sector_name",
    "sector_oversold_score",
    "sector_repairability_score",
    "sector_direction_score",
    "sector_recovery_state",
    "sector_gate_status",
)
_STOCK_INPUT_COLUMNS = (
    *_STOCK_CONTEXT_COLUMNS,
    "asset_id",
    "stock_score",
    "stock_rank",
    "stock_lifecycle",
)
_STOCK_METADATA_COLUMNS = (
    "snapshot_id",
    "anchor_date",
    "data_cutoff_date",
    "score_version",
    "market_regime",
    "previous_snapshot_id",
    "rank_delta",
    "lifecycle_delta",
)
_STOCK_COLUMNS = (
    "snapshot_id",
    "anchor_date",
    "data_cutoff_date",
    "score_version",
    "market_regime",
    *_STOCK_CONTEXT_COLUMNS,
    "asset_id",
    "stock_score",
    "stock_rank",
    "stock_lifecycle",
    "anchor_close",
    "adjusted_close_source",
    "previous_snapshot_id",
    "rank_delta",
    "lifecycle_delta",
    "score_status",
    "score_reason",
)
_OUTCOME_PRICE_SOURCES = frozenset(("raw", "qfq", "hfq"))
_SECTOR_INPUT_COLUMNS = _STOCK_CONTEXT_COLUMNS
_SECTOR_CONTEXT_VALUE_COLUMNS = _STOCK_CONTEXT_COLUMNS[2:]
_SECTOR_COLUMNS = (
    *_SECTOR_INPUT_COLUMNS,
    "sector_rank",
    "previous_snapshot_id",
    "sector_rank_delta",
    "sector_recovery_state_delta",
    "sector_revision_status",
)
_BACKFILL_COLUMNS = (
    "dataset",
    "asset_id",
    "start_date",
    "end_date",
    "expected_rows",
    "actual_rows",
    "reason",
)
_ARTIFACT_NAMES = (
    "market_regime.csv",
    "sector_states.csv",
    "stock_candidates.csv",
    "preflight.json",
    "backfill_requests.csv",
)
def build_rolling_snapshot(
    *,
    anchor_date: date,
    data_cutoff_date: date,
    market_regime: dict[str, object],
    sector_states: pd.DataFrame,
    stock_candidates: pd.DataFrame,
    previous_snapshot: dict[str, object] | None,
    score_version: str,
    runtime_metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build a normalized snapshot; same inputs are byte-stable."""

    _validate_date("anchor_date", anchor_date)
    _validate_date("data_cutoff_date", data_cutoff_date)
    if data_cutoff_date > anchor_date:
        raise ValueError("data_cutoff_date must not follow anchor_date")
    if not isinstance(score_version, str) or not score_version.strip():
        raise ValueError("score_version must be a non-empty string")
    if "/" in score_version or "\\" in score_version:
        raise ValueError("score_version must not contain a path separator")
    if not isinstance(market_regime, dict):
        raise TypeError("market_regime must be a dictionary")
    if not isinstance(sector_states, pd.DataFrame) or not isinstance(stock_candidates, pd.DataFrame):
        raise TypeError("sector_states and stock_candidates must be pandas DataFrames")

    regime = _normalize_mapping(market_regime)
    embedded_runtime_metadata = regime.pop("runtime_metadata", None)
    if runtime_metadata is None:
        runtime_metadata = embedded_runtime_metadata
    runtime = _normalize_runtime_metadata(runtime_metadata)
    market_state = regime.get("market_regime")
    if not isinstance(market_state, str) or not market_state.strip():
        raise ValueError("market_regime must include a non-empty market_regime value")
    regime["market_regime"] = market_state.strip()
    snapshot_id = f"{score_version}|{anchor_date.isoformat()}"
    previous_id, previous_stocks, previous_sectors = _previous_rows(previous_snapshot)

    sectors = _normalize_sector_rows(sector_states)
    stocks = _normalize_stock_rows(stock_candidates)
    stocks = _apply_stock_metadata(
        stocks,
        snapshot_id=snapshot_id,
        anchor_date=anchor_date,
        data_cutoff_date=data_cutoff_date,
        score_version=score_version,
        market_state=regime["market_regime"],
        previous_snapshot_id=previous_id,
    )
    sectors = _apply_sector_revisions(sectors, previous_sectors, previous_id)
    stocks = _apply_stock_revisions(
        stocks,
        previous_stocks,
        previous_id,
        snapshot_id=snapshot_id,
        anchor_date=anchor_date,
        data_cutoff_date=data_cutoff_date,
        score_version=score_version,
        market_state=regime["market_regime"],
    )
    _validate_stock_sector_context(stocks, sectors, previous_snapshot_id=previous_id)

    preflight = _normalize_preflight(regime.pop("preflight", None))
    backfill_requests = _normalize_backfill(regime.pop("backfill_requests", None))
    return {
        "snapshot_id": snapshot_id,
        "anchor_date": anchor_date.isoformat(),
        "data_cutoff_date": data_cutoff_date.isoformat(),
        "score_version": score_version,
        "market_regime": regime,
        "sector_states": sectors,
        "stock_candidates": stocks,
        "previous_snapshot_id": previous_id,
        "row_counts": {"sector_states": int(len(sectors)), "stock_candidates": int(len(stocks))},
        "preflight": preflight,
        "backfill_requests": backfill_requests,
        "runtime_metadata": runtime,
    }


def write_rolling_snapshot(
    snapshot: dict[str, object], *, output_dir: str | Path
) -> dict[str, object]:
    """Write one anchor directory without replacing an existing different snapshot."""

    normalized = _validate_snapshot_for_write(snapshot)
    destination = (
        Path(output_dir).expanduser().resolve()
        / "rolling_sector_oversold"
        / f"anchor={normalized['anchor_date']}"
        / f"version={normalized['score_version']}"
    )
    artifact_bytes = _artifact_bytes(normalized)
    manifest = {
        "snapshot_id": normalized["snapshot_id"],
        "anchor_date": normalized["anchor_date"],
        "data_cutoff_date": normalized["data_cutoff_date"],
        "score_version": normalized["score_version"],
        "previous_snapshot_id": normalized["previous_snapshot_id"],
        "runtime_metadata": normalized["runtime_metadata"],
        "row_counts": normalized["row_counts"],
        "artifact_hashes": {
            name: hashlib.sha256(contents).hexdigest() for name, contents in artifact_bytes.items()
        },
    }
    manifest_bytes = _json_bytes(manifest)
    manifest_path = destination / "manifest.json"

    if destination.exists():
        if _is_identical_existing_snapshot(destination, manifest, artifact_bytes):
            return {"status": "already_exists_identical", "manifest_path": str(manifest_path)}
        raise ValueError(f"immutable rolling snapshot already exists at {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    published = False
    try:
        for name in _ARTIFACT_NAMES:
            _atomic_write_new(staging / name, artifact_bytes[name])
        _atomic_write_new(staging / "manifest.json", manifest_bytes)
        _fsync_directory(staging)
        # The final path is checked immediately before publication.  A second
        # writer that wins a race is handled below without replacing its files.
        if destination.exists():
            if _is_identical_existing_snapshot(destination, manifest, artifact_bytes):
                return {"status": "already_exists_identical", "manifest_path": str(manifest_path)}
            raise ValueError(f"immutable rolling snapshot already exists at {destination}")
        os.replace(staging, destination)
        published = True
        _fsync_directory(destination.parent)
        return {"status": "created", "manifest_path": str(manifest_path)}
    except Exception:
        if destination.exists() and _is_identical_existing_snapshot(destination, manifest, artifact_bytes):
            return {"status": "already_exists_identical", "manifest_path": str(manifest_path)}
        if destination.exists():
            raise ValueError(f"immutable rolling snapshot already exists at {destination}") from None
        raise
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def _previous_rows(
    previous_snapshot: dict[str, object] | None,
) -> tuple[str | None, pd.DataFrame | None, pd.DataFrame | None]:
    if previous_snapshot is None:
        return None, None, None
    if not isinstance(previous_snapshot, dict):
        raise TypeError("previous_snapshot must be a dictionary or None")
    previous_id = previous_snapshot.get("snapshot_id")
    if not isinstance(previous_id, str) or not previous_id.strip():
        raise ValueError("previous_snapshot must include a non-empty snapshot_id")
    stocks = previous_snapshot.get("stock_candidates", pd.DataFrame())
    sectors = previous_snapshot.get("sector_states", pd.DataFrame())
    if not isinstance(stocks, pd.DataFrame) or not isinstance(sectors, pd.DataFrame):
        raise TypeError("previous snapshot rows must be pandas DataFrames")
    # Revision-only rows document an earlier removal and are not a candidate in
    # the immediately preceding snapshot.  They must not be invalidated again.
    if "stock_rank" in stocks:
        stocks = stocks.loc[stocks["stock_rank"].notna()].copy()
    if "sector_rank" in sectors:
        sectors = sectors.loc[sectors["sector_rank"].notna()].copy()
    return previous_id, _normalize_stock_rows(stocks), _normalize_sector_rows(sectors)


def _normalize_stock_rows(
    frame: pd.DataFrame, *, allow_revision_rows: bool = False
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=_STOCK_COLUMNS)
    _require_columns(frame, _STOCK_INPUT_COLUMNS, "stock_candidates")
    result = frame.copy(deep=True)
    _normalize_string_columns(result, ("asset_id", "sector_system", "sector_code", "sector_name"))
    _normalize_string_columns(result, ("stock_lifecycle", "sector_recovery_state", "sector_gate_status"))
    for column in ("stock_lifecycle", "sector_gate_status"):
        result[column] = result[column].str.casefold()
    _require_nonempty_strings(result, ("asset_id", "sector_system", "sector_code", "sector_name"), "stock_candidates")
    _require_nonempty_strings(
        result, ("stock_lifecycle", "sector_recovery_state", "sector_gate_status"), "stock_candidates"
    )
    _require_finite_numbers(
        result,
        ("stock_score",),
        "stock_candidates",
    )
    result["stock_rank"] = pd.to_numeric(result["stock_rank"], errors="coerce")
    sector_score_columns = (
        "sector_oversold_score",
        "sector_repairability_score",
        "sector_direction_score",
    )
    _require_finite_numbers(
        result,
        sector_score_columns,
        "stock_candidates",
        allow_missing=_allow_missing_sector_scores(result),
    )
    invalid_rank = (
        result["stock_rank"].isna()
        | ~result["stock_rank"].map(lambda value: math.isfinite(value) if pd.notna(value) else False)
        | (result["stock_rank"] <= 0)
        | (result["stock_rank"] % 1 != 0)
    )
    if allow_revision_rows:
        invalid_rank &= ~result["stock_lifecycle"].eq("invalidated")
    if invalid_rank.any():
        raise ValueError("stock_candidates stock_rank must contain positive integers")
    result["stock_rank"] = result["stock_rank"].astype("Int64")
    if result["asset_id"].duplicated().any():
        duplicate = result.loc[result["asset_id"].duplicated(keep=False), "asset_id"].iloc[0]
        raise ValueError(f"stock_candidates has duplicate asset_id {duplicate}")
    _normalize_outcome_price_columns(result)
    for column in _STOCK_METADATA_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    for column in ("score_status", "score_reason"):
        if column not in result:
            result[column] = ""
        result[column] = result[column].fillna("").astype("string")
    return _ordered_frame(result, _STOCK_COLUMNS, sort_columns=("stock_rank", "asset_id"))


def _normalize_outcome_price_columns(frame: pd.DataFrame) -> None:
    """Preserve frozen outcome inputs while accepting legacy snapshots without them."""

    for column in ("anchor_close", "adjusted_close_source"):
        if column not in frame:
            frame[column] = pd.NA
    anchor_supplied = frame["anchor_close"].notna()
    anchor_close = pd.to_numeric(frame["anchor_close"], errors="coerce")
    finite_anchor = anchor_close.map(
        lambda value: bool(pd.notna(value)) and math.isfinite(float(value)) and float(value) > 0
    )
    if (anchor_supplied & ~finite_anchor).any():
        raise ValueError("stock_candidates anchor_close must be a finite positive number")
    source = frame["adjusted_close_source"].astype("string").str.strip().replace("", pd.NA)
    invalid_source = source.notna() & ~source.isin(_OUTCOME_PRICE_SOURCES)
    if invalid_source.any():
        raise ValueError("stock_candidates adjusted_close_source must be one of raw, qfq, hfq")
    excluded = frame["sector_gate_status"].eq("blocked") | frame["stock_lifecycle"].eq("invalidated")
    mismatched = anchor_supplied != source.notna()
    if mismatched.any():
        raise ValueError(
            "stock_candidates anchor_close and adjusted_close_source must be supplied together"
        )
    missing_eligible = ~excluded & ~anchor_supplied
    if missing_eligible.any():
        raise ValueError(
            "eligible stock_candidates require anchor_close and adjusted_close_source"
        )
    frame["anchor_close"] = anchor_close
    frame["adjusted_close_source"] = source


def _normalize_sector_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=_SECTOR_COLUMNS)
    _require_columns(frame, _SECTOR_INPUT_COLUMNS, "sector_states")
    result = frame.copy(deep=True)
    _normalize_string_columns(
        result,
        ("sector_system", "sector_code", "sector_name", "sector_recovery_state", "sector_gate_status"),
    )
    for column in ("sector_gate_status",):
        result[column] = result[column].str.casefold()
    _require_nonempty_strings(
        result,
        ("sector_system", "sector_code", "sector_name", "sector_recovery_state", "sector_gate_status"),
        "sector_states",
    )
    _require_finite_numbers(
        result,
        ("sector_oversold_score", "sector_repairability_score", "sector_direction_score"),
        "sector_states",
        allow_missing=_allow_missing_sector_scores(result),
    )
    if result.duplicated(["sector_system", "sector_code"]).any():
        duplicate = result.loc[
            result.duplicated(["sector_system", "sector_code"], keep=False),
            ["sector_system", "sector_code"],
        ].iloc[0]
        raise ValueError(
            f"sector_states has duplicate sector {duplicate['sector_system']}/{duplicate['sector_code']}"
        )
    result = _ordered_frame(result, _SECTOR_COLUMNS, sort_columns=("sector_system", "sector_code"))
    result = result.sort_values(
        ["sector_oversold_score", "sector_system", "sector_code"],
        ascending=[False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    result["sector_rank"] = pd.Series(range(1, len(result) + 1), dtype="int64")
    return result


def _apply_stock_metadata(
    frame: pd.DataFrame,
    *,
    snapshot_id: str,
    anchor_date: date,
    data_cutoff_date: date,
    score_version: str,
    market_state: str,
    previous_snapshot_id: str | None,
) -> pd.DataFrame:
    result = frame.copy(deep=True)
    result["snapshot_id"] = snapshot_id
    result["anchor_date"] = anchor_date.isoformat()
    result["data_cutoff_date"] = data_cutoff_date.isoformat()
    result["score_version"] = score_version
    result["market_regime"] = market_state
    result["previous_snapshot_id"] = previous_snapshot_id if previous_snapshot_id else pd.NA
    result["rank_delta"] = pd.NA
    result["lifecycle_delta"] = pd.NA
    return _ordered_frame(result, _STOCK_COLUMNS, sort_columns=("stock_rank", "asset_id"))


def _apply_stock_revisions(
    current: pd.DataFrame,
    previous: pd.DataFrame | None,
    previous_snapshot_id: str | None,
    **metadata: object,
) -> pd.DataFrame:
    result = current.copy(deep=True)
    if previous is None:
        return result
    prior_by_asset = previous.set_index("asset_id", drop=False)
    current_assets = set(result["asset_id"])
    for index, row in result.iterrows():
        asset_id = row["asset_id"]
        if asset_id not in prior_by_asset.index:
            result.at[index, "lifecycle_delta"] = f"absent->{row['stock_lifecycle']}"
            continue
        old = prior_by_asset.loc[asset_id]
        result.at[index, "rank_delta"] = int(old["stock_rank"]) - int(row["stock_rank"])
        result.at[index, "lifecycle_delta"] = f"{old['stock_lifecycle']}->{row['stock_lifecycle']}"

    removed = previous.loc[~previous["asset_id"].isin(current_assets)].copy(deep=True)
    if not removed.empty:
        removed = _apply_stock_metadata(removed, previous_snapshot_id=previous_snapshot_id, **metadata)
        removed["stock_rank"] = pd.NA
        removed["rank_delta"] = pd.NA
        removed["stock_lifecycle"] = "invalidated"
        previous_lifecycles = previous.set_index("asset_id")["stock_lifecycle"]
        removed["lifecycle_delta"] = [
            f"{previous_lifecycles.loc[asset_id]}->invalidated"
            for asset_id in removed["asset_id"]
        ]
        removed["score_reason"] = "sector_gate_or_data_change"
        result = pd.concat([result, removed], ignore_index=True, sort=False)
    return _ordered_frame(result, _STOCK_COLUMNS, sort_columns=("stock_rank", "asset_id"))


def _apply_sector_revisions(
    current: pd.DataFrame, previous: pd.DataFrame | None, previous_snapshot_id: str | None
) -> pd.DataFrame:
    result = current.copy(deep=True)
    result["previous_snapshot_id"] = previous_snapshot_id if previous_snapshot_id else pd.NA
    result["sector_rank_delta"] = pd.NA
    result["sector_recovery_state_delta"] = pd.NA
    result["sector_revision_status"] = "current"
    if previous is None:
        return _ordered_frame(result, _SECTOR_COLUMNS, sort_columns=("sector_rank", "sector_system", "sector_code"))
    prior = previous.set_index(["sector_system", "sector_code"], drop=False)
    current_keys = set(zip(result["sector_system"], result["sector_code"], strict=True))
    for index, row in result.iterrows():
        key = (row["sector_system"], row["sector_code"])
        if key not in prior.index:
            result.at[index, "sector_recovery_state_delta"] = f"absent->{row['sector_recovery_state']}"
            continue
        old = prior.loc[key]
        result.at[index, "sector_rank_delta"] = int(old["sector_rank"]) - int(row["sector_rank"])
        result.at[index, "sector_recovery_state_delta"] = (
            f"{old['sector_recovery_state']}->{row['sector_recovery_state']}"
        )
    removed = previous.loc[
        ~previous.apply(lambda row: (row["sector_system"], row["sector_code"]) in current_keys, axis=1)
    ].copy(deep=True)
    if not removed.empty:
        removed["sector_rank"] = pd.NA
        removed["previous_snapshot_id"] = previous_snapshot_id
        removed["sector_rank_delta"] = pd.NA
        removed["sector_recovery_state_delta"] = removed["sector_recovery_state"].astype(str) + "->absent"
        removed["sector_revision_status"] = "removed"
        result = pd.concat([result, removed], ignore_index=True, sort=False)
    return _ordered_frame(result, _SECTOR_COLUMNS, sort_columns=("sector_rank", "sector_system", "sector_code"))


def _normalize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}


def _normalize_preflight(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("market_regime preflight must be a mapping when supplied")
    return _normalize_mapping(value)


def _normalize_backfill(value: object) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame(columns=_BACKFILL_COLUMNS)
    if not isinstance(value, pd.DataFrame):
        raise TypeError("market_regime backfill_requests must be a pandas DataFrame when supplied")
    result = value.copy(deep=True)
    _require_columns(result, _BACKFILL_COLUMNS, "backfill_requests") if not result.empty else None
    return _ordered_frame(result, _BACKFILL_COLUMNS, sort_columns=_BACKFILL_COLUMNS)


def _normalize_runtime_metadata(value: Mapping[str, object] | None) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("runtime_metadata must be a mapping when supplied")
    return _normalize_mapping(value)


def _validate_snapshot_for_write(snapshot: dict[str, object]) -> dict[str, object]:
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dictionary")
    required = {
        "snapshot_id", "anchor_date", "data_cutoff_date", "score_version", "market_regime",
        "sector_states", "stock_candidates", "previous_snapshot_id", "row_counts", "preflight",
        "backfill_requests",
    }
    missing = sorted(required - set(snapshot))
    if missing:
        raise ValueError(f"snapshot missing required keys: {', '.join(missing)}")
    anchor = _parse_iso_date(snapshot["anchor_date"], "anchor_date")
    cutoff = _parse_iso_date(snapshot["data_cutoff_date"], "data_cutoff_date")
    if cutoff > anchor:
        raise ValueError("data_cutoff_date must not follow anchor_date")
    version = snapshot["score_version"]
    if not isinstance(version, str) or not version.strip():
        raise ValueError("snapshot score_version must be a non-empty string")
    if "/" in version or "\\" in version:
        raise ValueError("snapshot score_version must not contain a path separator")
    expected_id = f"{version}|{anchor.isoformat()}"
    if snapshot["snapshot_id"] != expected_id:
        raise ValueError("snapshot_id does not match score_version and anchor_date")
    if not isinstance(snapshot["market_regime"], Mapping):
        raise TypeError("snapshot market_regime must be a mapping")
    if not isinstance(snapshot["sector_states"], pd.DataFrame) or not isinstance(
        snapshot["stock_candidates"], pd.DataFrame
    ):
        raise TypeError("snapshot sector_states and stock_candidates must be pandas DataFrames")
    if not isinstance(snapshot["backfill_requests"], pd.DataFrame):
        raise TypeError("snapshot backfill_requests must be a pandas DataFrame")
    supplied_row_counts = snapshot["row_counts"]
    if not isinstance(supplied_row_counts, Mapping):
        raise ValueError("snapshot row_counts must be a mapping")
    missing_stock = validate_snapshot_columns(snapshot["stock_candidates"].columns)
    if missing_stock:
        raise ValueError(
            "stock snapshot rows do not satisfy the required snapshot column contract: "
            + ", ".join(missing_stock)
        )
    missing_stock_schema = sorted(set(_STOCK_COLUMNS) - set(snapshot["stock_candidates"].columns))
    if missing_stock_schema:
        raise ValueError("stock snapshot rows missing canonical columns: " + ", ".join(missing_stock_schema))
    missing_sector = sorted(set(_SECTOR_INPUT_COLUMNS) - set(snapshot["sector_states"].columns))
    if missing_sector:
        raise ValueError("sector snapshot rows missing canonical columns: " + ", ".join(missing_sector))
    missing_sector_schema = sorted(set(_SECTOR_COLUMNS) - set(snapshot["sector_states"].columns))
    if missing_sector_schema:
        raise ValueError("sector snapshot rows missing canonical columns: " + ", ".join(missing_sector_schema))
    previous_id = snapshot["previous_snapshot_id"]
    if previous_id is not None:
        if not isinstance(previous_id, str) or not previous_id.strip():
            raise ValueError("snapshot previous_snapshot_id must be a non-empty string or null")
        previous_id = previous_id.strip()
    market_regime = _normalize_mapping(snapshot["market_regime"])
    market_state = market_regime.get("market_regime")
    if not isinstance(market_state, str) or not market_state.strip():
        raise ValueError("snapshot market_regime must include a non-empty market_regime value")
    market_regime["market_regime"] = market_state.strip()
    stock_rows = _validate_stock_snapshot_rows(
        snapshot["stock_candidates"],
        snapshot_id=expected_id,
        anchor_date=anchor.isoformat(),
        data_cutoff_date=cutoff.isoformat(),
        score_version=version,
        market_state=market_state.strip(),
        previous_snapshot_id=previous_id,
    )
    sector_rows = _validate_sector_snapshot_rows(
        snapshot["sector_states"], previous_snapshot_id=previous_id
    )
    _validate_stock_sector_context(
        stock_rows, sector_rows, previous_snapshot_id=previous_id
    )
    expected_row_counts = {
        "sector_states": int(len(sector_rows)),
        "stock_candidates": int(len(stock_rows)),
    }
    if dict(supplied_row_counts) != expected_row_counts:
        raise ValueError("snapshot row_counts do not match snapshot frames")
    normalized = {
        "snapshot_id": expected_id,
        "anchor_date": anchor.isoformat(),
        "data_cutoff_date": cutoff.isoformat(),
        "score_version": version,
        "market_regime": market_regime,
        "previous_snapshot_id": previous_id,
        "preflight": _normalize_preflight(snapshot["preflight"]),
        "backfill_requests": _normalize_backfill(snapshot["backfill_requests"]),
        "runtime_metadata": _normalize_runtime_metadata(snapshot.get("runtime_metadata")),
    }
    normalized["sector_states"] = _ordered_frame(
        sector_rows, _SECTOR_COLUMNS,
        sort_columns=("sector_rank", "sector_system", "sector_code"),
    )
    normalized["stock_candidates"] = _ordered_frame(
        stock_rows, _STOCK_COLUMNS,
        sort_columns=("stock_rank", "asset_id"),
    )
    normalized["row_counts"] = {
        "sector_states": expected_row_counts["sector_states"],
        "stock_candidates": expected_row_counts["stock_candidates"],
    }
    return normalized


def _validate_stock_snapshot_rows(
    frame: pd.DataFrame,
    *,
    snapshot_id: str,
    anchor_date: str,
    data_cutoff_date: str,
    score_version: str,
    market_state: str,
    previous_snapshot_id: str | None,
) -> pd.DataFrame:
    result = _normalize_stock_rows(frame, allow_revision_rows=True)
    for column, expected in (
        ("snapshot_id", snapshot_id),
        ("anchor_date", anchor_date),
        ("data_cutoff_date", data_cutoff_date),
        ("score_version", score_version),
    ):
        _require_exact_column(result, column, expected, "stock_candidates")
    _validate_stock_cross_artifact_metadata(
        result,
        market_state=market_state,
        previous_snapshot_id=previous_snapshot_id,
    )
    return result


def _validate_stock_cross_artifact_metadata(
    frame: pd.DataFrame,
    *,
    market_state: str,
    previous_snapshot_id: str | None,
) -> None:
    row_regimes = frame["market_regime"].astype("string").str.strip().replace("", pd.NA)
    missing_regime = row_regimes.isna()
    conflicting_regime = row_regimes.notna() & ~row_regimes.eq(market_state)
    if conflicting_regime.any() or missing_regime.any():
        raise ValueError("stock_candidates market_regime conflicts with snapshot market_regime")
    frame["market_regime"] = row_regimes

    row_previous = frame["previous_snapshot_id"].astype("string").str.strip().replace("", pd.NA)
    if previous_snapshot_id is None:
        conflicting_previous = row_previous.notna()
    else:
        conflicting_previous = row_previous.notna() & ~row_previous.eq(previous_snapshot_id)
        conflicting_previous |= row_previous.isna()
    if conflicting_previous.any():
        raise ValueError(
            "stock_candidates previous_snapshot_id conflicts with snapshot previous_snapshot_id"
        )
    frame["previous_snapshot_id"] = row_previous


def _validate_sector_snapshot_rows(
    frame: pd.DataFrame, *, previous_snapshot_id: str | None
) -> pd.DataFrame:
    result = frame.copy(deep=True)
    if result.empty:
        return result
    _normalize_string_columns(
        result,
        ("sector_system", "sector_code", "sector_name", "sector_recovery_state", "sector_gate_status"),
    )
    _require_nonempty_strings(
        result,
        ("sector_system", "sector_code", "sector_name", "sector_recovery_state", "sector_gate_status"),
        "sector_states",
    )
    _require_finite_numbers(
        result,
        ("sector_oversold_score", "sector_repairability_score", "sector_direction_score"),
        "sector_states",
        allow_missing=_allow_missing_sector_scores(result),
    )
    if result.duplicated(["sector_system", "sector_code"]).any():
        raise ValueError("sector_states has duplicate sector identity")
    result["sector_rank"] = pd.to_numeric(result["sector_rank"], errors="coerce")
    revision_status = result["sector_revision_status"].fillna("current").astype("string")
    invalid_rank = (
        result["sector_rank"].isna()
        | ~result["sector_rank"].map(lambda value: math.isfinite(value) if pd.notna(value) else False)
        | (result["sector_rank"] <= 0)
        | (result["sector_rank"] % 1 != 0)
    )
    invalid_rank &= ~revision_status.eq("removed")
    if invalid_rank.any():
        raise ValueError("sector_states sector_rank must contain positive integers")
    result["sector_rank"] = result["sector_rank"].astype("Int64")
    _validate_sector_cross_artifact_metadata(
        result, previous_snapshot_id=previous_snapshot_id
    )
    return result


def _validate_sector_cross_artifact_metadata(
    frame: pd.DataFrame, *, previous_snapshot_id: str | None
) -> None:
    row_previous = frame["previous_snapshot_id"].astype("string").str.strip().replace("", pd.NA)
    if previous_snapshot_id is None:
        conflicting_previous = row_previous.notna()
    else:
        conflicting_previous = row_previous.notna() & ~row_previous.eq(previous_snapshot_id)
        conflicting_previous |= row_previous.isna()
    if conflicting_previous.any():
        raise ValueError(
            "sector_states previous_snapshot_id conflicts with snapshot previous_snapshot_id"
        )
    frame["previous_snapshot_id"] = row_previous


def _validate_stock_sector_context(
    stock_rows: pd.DataFrame,
    sector_rows: pd.DataFrame,
    *,
    previous_snapshot_id: str | None,
) -> None:
    """Require stock candidates to preserve the canonical sector artifact context."""

    if stock_rows.empty:
        return
    sectors_by_identity = sector_rows.set_index(
        ["sector_system", "sector_code"], drop=False
    )
    for _, stock in stock_rows.iterrows():
        identity = (stock["sector_system"], stock["sector_code"])
        if identity not in sectors_by_identity.index:
            raise ValueError(
                "stock_candidates references missing sector state "
                f"{identity[0]}/{identity[1]}"
            )
        if _is_historical_invalidation_revision(
            stock, previous_snapshot_id=previous_snapshot_id
        ):
            continue
        sector = sectors_by_identity.loc[identity]
        conflicting_columns = [
            column
            for column in _SECTOR_CONTEXT_VALUE_COLUMNS
            if not _na_aware_equal(stock[column], sector[column])
        ]
        if conflicting_columns:
            raise ValueError(
                "stock_candidates sector context conflicts with sector_states for "
                f"{identity[0]}/{identity[1]}: {', '.join(conflicting_columns)}"
            )


def _is_historical_invalidation_revision(
    stock: pd.Series, *, previous_snapshot_id: str | None
) -> bool:
    lifecycle_delta = stock["lifecycle_delta"]
    row_previous_snapshot_id = stock["previous_snapshot_id"]
    return (
        isinstance(previous_snapshot_id, str)
        and bool(previous_snapshot_id.strip())
        and not _is_missing(row_previous_snapshot_id)
        and str(row_previous_snapshot_id).strip() == previous_snapshot_id.strip()
        and stock["stock_lifecycle"] == "invalidated"
        and _is_missing(stock["stock_rank"])
        and str(stock["score_reason"]).strip() == "sector_gate_or_data_change"
        and not _is_missing(lifecycle_delta)
        and str(lifecycle_delta).strip().endswith("->invalidated")
    )


def _na_aware_equal(left: object, right: object) -> bool:
    if _is_missing(left) or _is_missing(right):
        return _is_missing(left) and _is_missing(right)
    try:
        return bool(left == right)
    except (TypeError, ValueError):
        return False


def _require_exact_column(frame: pd.DataFrame, column: str, expected: str, label: str) -> None:
    if column not in frame:
        raise ValueError(f"{label} missing required column {column}")
    values = frame[column].astype("string")
    if values.isna().any() or not values.eq(expected).all():
        raise ValueError(f"{label} {column} does not match snapshot metadata")


def _artifact_bytes(snapshot: dict[str, object]) -> dict[str, bytes]:
    market = {
        "snapshot_id": snapshot["snapshot_id"],
        "anchor_date": snapshot["anchor_date"],
        "data_cutoff_date": snapshot["data_cutoff_date"],
        "score_version": snapshot["score_version"],
        **snapshot["market_regime"],
    }
    market_frame = pd.DataFrame([market]).reindex(columns=sorted(market))
    return {
        "market_regime.csv": _csv_bytes(market_frame),
        "sector_states.csv": _csv_bytes(snapshot["sector_states"]),
        "stock_candidates.csv": _csv_bytes(snapshot["stock_candidates"]),
        "preflight.json": _json_bytes(snapshot["preflight"]),
        "backfill_requests.csv": _csv_bytes(snapshot["backfill_requests"]),
    }


def _is_identical_existing_snapshot(
    destination: Path, manifest: dict[str, object], artifact_bytes: dict[str, bytes]
) -> bool:
    manifest_path = destination / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if existing != manifest:
        return False
    return all(
        (path := destination / name).is_file()
        and hashlib.sha256(path.read_bytes()).hexdigest() == manifest["artifact_hashes"][name]
        and hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(contents).digest()
        for name, contents in artifact_bytes.items()
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_new(path: Path, contents: bytes) -> None:
    if path.exists():
        raise ValueError(f"immutable rolling snapshot artifact already exists at {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise ValueError(f"immutable rolling snapshot artifact already exists at {path}")
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    normalized = frame.copy(deep=True)
    for column in normalized.columns:
        normalized[column] = normalized[column].map(_csv_value)
    return normalized.to_csv(
        index=False,
        lineterminator="\n",
        float_format="%.12g",
        na_rep="",
    ).encode("utf-8")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _csv_value(value: object) -> object:
    if isinstance(value, Decimal):
        return _json_value(value)
    if _is_missing(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    if isinstance(value, Mapping) or isinstance(value, (list, tuple)):
        return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        integral = value == value.to_integral_value()
        converted = int(value) if integral else float(value)
        return converted if not isinstance(converted, float) or math.isfinite(converted) else None
    if _is_missing(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return _json_value(value.item())
        except ValueError:
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _ordered_frame(
    frame: pd.DataFrame, columns: tuple[str, ...], *, sort_columns: tuple[str, ...]
) -> pd.DataFrame:
    result = frame.copy(deep=True)
    for column in columns:
        if column not in result:
            result[column] = pd.NA
    extras = sorted(column for column in result.columns if column not in columns)
    result = result.loc[:, [*columns, *extras]]
    usable_sort_columns = [column for column in sort_columns if column in result]
    if usable_sort_columns:
        result = result.sort_values(usable_sort_columns, kind="mergesort", na_position="last")
    return result.reset_index(drop=True)


def _normalize_string_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    for column in columns:
        frame[column] = frame[column].astype("string").str.strip().replace("", pd.NA)


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {', '.join(missing)}")


def _require_nonempty_strings(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    for column in columns:
        if frame[column].isna().any():
            raise ValueError(f"{label} has missing required value {column}")


def _require_finite_numbers(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    label: str,
    *,
    allow_missing: pd.Series | None = None,
) -> None:
    allowed = (
        pd.Series(False, index=frame.index)
        if allow_missing is None
        else allow_missing.reindex(frame.index, fill_value=False).fillna(False).astype(bool)
    )
    for column in columns:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        finite = numeric.map(
            lambda value: bool(pd.notna(value)) and math.isfinite(float(value))
        )
        invalid = ~finite & ~allowed
        if invalid.any():
            raise ValueError(f"{label} has non-finite required value {column}")
        frame[column] = numeric


def _allow_missing_sector_scores(frame: pd.DataFrame) -> pd.Series:
    return frame["sector_gate_status"].eq("blocked") | frame["sector_recovery_state"].eq("unknown")


def _validate_date(label: str, value: object) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{label} must be a date")


def _parse_iso_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"snapshot {label} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"snapshot {label} must be an ISO date string") from error


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
