"""Database-only orchestration for rolling sector-oversold snapshots.

The module deliberately coordinates supplied, point-in-time database frames.
It never falls back to a market-data provider or an ingestion entry point.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

import pandas as pd

from stock_research.db import connect, fetch_all
from stock_research.strategy_data_policy import (
    DB_ONLY,
    DataGap,
    StrategyRuntimeBudget,
    assert_db_only_source,
    write_backfill_request,
)

from .contracts import GateStatus, RollingOversoldConfig, SectorResearchEligibility, StockLifecycle
from .loaders import RollingInputs, load_rolling_inputs
from .market_regime import compute_market_regime_features
from .outcomes import evaluate_snapshot, summarize_rolling_evaluation
from .preflight import PreflightResult, run_rolling_preflight
from .reporting import (
    latest_rolling_evaluation_directory,
    load_rolling_oversold_snapshot,
)
from .sector_scoring import score_sector_states
from .snapshots import (
    build_rolling_snapshot,
    write_rolling_snapshot,
    write_sector_batch_snapshot,
)
from .stock_scoring import StockScoringDataGap, score_rolling_stock_candidates


_STAGE_NAMES = (
    "load",
    "preflight",
    "regime",
    "sector",
    "stock",
    "snapshot",
    "evaluation",
    "publication",
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


def run_one_anchor(
    *,
    anchor_date: date,
    previous_snapshot: dict[str, object] | None,
    config: RollingOversoldConfig,
    output_dir: str | Path,
    service: str,
) -> dict[str, object]:
    """Build one point-in-time snapshot and evaluate DB-known forward bars."""

    if not isinstance(anchor_date, date):
        raise TypeError("anchor_date must be a date")
    if not isinstance(config, RollingOversoldConfig):
        raise TypeError("config must be a RollingOversoldConfig")
    if config.anchor_end_date is not None and config.anchor_end_date < anchor_date:
        raise ValueError("config anchor_end_date must not precede anchor_date")
    assert_db_only_source(DB_ONLY)
    runtime = StrategyRuntimeBudget(timeout_seconds=config.runtime_budget_seconds)
    existing = _load_existing_snapshot(
        output_dir=output_dir,
        anchor_date=anchor_date,
        score_version=config.score_version,
    )
    if existing is not None:
        _assert_existing_snapshot_lineage(existing, previous_snapshot)
        _assert_existing_snapshot_adjust_type(existing, config.adjust_type)
        return _existing_snapshot_result(
            existing,
            output_dir=output_dir,
            config=config,
            service=service,
            runtime=runtime,
        )

    inputs = _timed(
        runtime,
        "load",
        lambda: load_rolling_inputs(anchor_date=anchor_date, config=config, service=service),
    )
    if not isinstance(inputs, RollingInputs) and not hasattr(inputs, "data_cutoff_date"):
        raise TypeError("load_rolling_inputs must return RollingInputs")
    cutoff = _as_date(getattr(inputs, "data_cutoff_date"), "inputs.data_cutoff_date")

    with tempfile.TemporaryDirectory(prefix="rolling-oversold-preflight-") as temporary:
        preflight = _timed(
            runtime,
            "preflight",
            lambda: run_rolling_preflight(inputs, anchor_date=anchor_date, output_dir=temporary),
        )
    if not isinstance(preflight, PreflightResult):
        raise TypeError("run_rolling_preflight must return PreflightResult")
    if preflight.blocked:
        return _blocked_result(
            anchor_date=anchor_date,
            cutoff=cutoff,
            config=config,
            output_dir=output_dir,
            preflight=preflight,
            gaps=preflight.gaps,
            runtime=runtime,
            blocked_reason="preflight",
            status=preflight.status,
        )

    market_regime = _timed(
        runtime,
        "regime",
        lambda: compute_market_regime_features(inputs, anchor_date=anchor_date),
    )
    if not isinstance(market_regime, dict):
        raise TypeError("compute_market_regime_features must return a dictionary")
    market_regime = dict(market_regime)
    market_regime["market_regime"] = str(market_regime.get("market_regime", "unknown")).strip() or "unknown"

    sector_states = _timed(
        runtime,
        "sector",
        lambda: _score_all_sector_states(inputs, market_regime=market_regime, anchor_date=anchor_date),
    )
    sector_states["market_regime"] = market_regime["market_regime"]
    gated_sectors = _gated_sector_rows(sector_states, top_n=config.sector_top_n)

    try:
        if gated_sectors.empty:
            stock_candidates = pd.DataFrame()
        else:
            stock_candidates = _timed(
                runtime,
                "stock",
                lambda: _score_gated_stock_candidates(
                    inputs,
                    sector_states=sector_states,
                    gated_sectors=gated_sectors,
                    anchor_date=anchor_date,
                    config=config,
                ),
            )
    except StockScoringDataGap as exc:
        return _blocked_result(
            anchor_date=anchor_date,
            cutoff=cutoff,
            config=config,
            output_dir=output_dir,
            preflight=preflight,
            gaps=(exc.gap,),
            runtime=runtime,
            blocked_reason="stock_scoring_data_gap",
            status="blocked_missing_data",
        )

    if gated_sectors.empty:
        # A zero-duration explicit stock stage keeps the runtime manifest's
        # contract stable while documenting that no gate permitted scoring.
        runtime.stage_timings_seconds.setdefault("stock", 0.0)
    try:
        stock_candidates = _ensure_frozen_candidate_prices(
            stock_candidates,
            stock_bars=getattr(inputs, "stock_bars", pd.DataFrame()),
            cutoff=cutoff,
            config=config,
            market_regime=market_regime["market_regime"],
        )
    except StockScoringDataGap as exc:
        return _blocked_result(
            anchor_date=anchor_date,
            cutoff=cutoff,
            config=config,
            output_dir=output_dir,
            preflight=preflight,
            gaps=(exc.gap,),
            runtime=runtime,
            blocked_reason="stock_scoring_data_gap",
            status="blocked_missing_data",
        )

    snapshot_market_regime = dict(market_regime)
    snapshot_market_regime["preflight"] = _preflight_payload(preflight)
    snapshot_market_regime["backfill_requests"] = _gaps_frame(preflight.gaps)

    # Assemble a probe snapshot first so outcome evaluation can complete before
    # the immutable manifest is published.  Its normalized rows are retained;
    # only the now-complete runtime metadata is attached before publication.
    runtime.begin_stage("snapshot")
    try:
        snapshot_probe = build_rolling_snapshot(
            anchor_date=anchor_date,
            data_cutoff_date=cutoff,
            market_regime=snapshot_market_regime,
            sector_states=sector_states,
            stock_candidates=stock_candidates,
            previous_snapshot=previous_snapshot,
            score_version=config.score_version,
            runtime_metadata=_snapshot_runtime_metadata(runtime),
        )
    finally:
        runtime.end_stage("snapshot")

    evaluation_cutoff = config.anchor_end_date or cutoff
    evaluation_artifacts: dict[str, bytes] = {}
    runtime.begin_stage("evaluation")
    try:
        evaluation_bars = _load_evaluation_bars(
            asset_ids=_snapshot_asset_ids(snapshot_probe),
            anchor_date=anchor_date,
            evaluation_cutoff=evaluation_cutoff,
            adjust_type=config.adjust_type,
            service=service,
        )
        detail = evaluate_snapshot(
            snapshot_probe,
            bars=_evaluation_bars(evaluation_bars, config.adjust_type),
            evaluation_cutoff=evaluation_cutoff,
            horizons=config.forecast_horizons,
        )
        summary = summarize_rolling_evaluation(detail)
        evaluation_artifacts = _evaluation_artifact_bytes(detail, summary)
    finally:
        runtime.end_stage("evaluation")

    snapshot = dict(snapshot_probe)
    snapshot["runtime_metadata"] = _snapshot_runtime_metadata(runtime)
    publication_metadata: dict[str, object] | None = None
    publication_stage_closed = False
    publication_metadata_started = False

    def publish_runtime_metadata() -> dict[str, object]:
        nonlocal publication_metadata, publication_stage_closed, publication_metadata_started
        runtime.checkpoint("publication")
        if not publication_stage_closed and not publication_metadata_started:
            publication_metadata_started = True
            return runtime.metadata()
        if not publication_stage_closed:
            runtime.end_stage("publication")
            publication_stage_closed = True
            runtime.checkpoint("publication")
        publication_metadata = runtime.metadata()
        return publication_metadata

    def publish_runtime_guard() -> None:
        runtime.checkpoint("publication")

    runtime.begin_stage("publication")
    try:
        write_result = write_rolling_snapshot(
            snapshot,
            output_dir=output_dir,
            additional_artifacts=evaluation_artifacts,
            runtime_metadata_supplier=publish_runtime_metadata,
            runtime_publish_guard=publish_runtime_guard,
        )
    finally:
        if not publication_stage_closed:
            try:
                runtime.end_stage("publication")
            except ValueError:
                # The supplier may have ended the stage before a budget or
                # publication error was raised.
                pass
    if publication_metadata is None:
        candidate_metadata = write_result.get("runtime_metadata")
        publication_metadata = (
            candidate_metadata if isinstance(candidate_metadata, dict) else runtime.metadata()
        )
    snapshot["runtime_metadata"] = publication_metadata
    manifest_path = Path(str(write_result["manifest_path"]))
    snapshot_dir = manifest_path.parent
    evaluation_path = snapshot_dir / "evaluation_detail.csv"
    evaluation_summary_path = snapshot_dir / "evaluation_summary.csv"

    paths = _snapshot_paths(
        snapshot_dir,
        manifest_path=manifest_path,
        evaluation_path=evaluation_path,
        evaluation_summary_path=evaluation_summary_path,
    )
    metadata = runtime.metadata()
    return {
        "blocked": False,
        "blocked_reason": "",
        "anchor_date": anchor_date.isoformat(),
        "data_cutoff_date": cutoff.isoformat(),
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot": snapshot,
        "paths": paths,
        "stock_candidate_count": int(len(snapshot["stock_candidates"])),
        "runtime_seconds": metadata["runtime_seconds"],
        "runtime_metadata": metadata,
        "future_rows_used_for_scoring": 0,
    }


def run_sector_batch(
    *,
    anchor_date: date,
    config: RollingOversoldConfig,
    output_dir: str | Path | None = None,
    service: str | None = None,
    inputs: RollingInputs | Any | None = None,
    previous_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    """Score the complete point-in-time sector universe in one batch.

    The legacy ``run_one_anchor`` path intentionally keeps its mixed-universe
    gates and one-asset snapshot contract.  This entry point is the explicit
    full-sector path: it loads once, computes one market regime and one sector
    frame, derives stock features once, then ranks independently by canonical
    ``(sector_system, sector_code)``.  A supplied ``inputs`` object is useful
    for deterministic tests and replay callers; when omitted the database
    loader is invoked exactly once.
    """

    if not isinstance(anchor_date, date):
        raise TypeError("anchor_date must be a date")
    if not isinstance(config, RollingOversoldConfig):
        raise TypeError("config must be a RollingOversoldConfig")
    if config.anchor_end_date is not None and config.anchor_end_date < anchor_date:
        raise ValueError("config anchor_end_date must not precede anchor_date")
    assert_db_only_source(DB_ONLY)
    existing = _load_existing_sector_batch_result(
        output_dir=output_dir,
        anchor_date=anchor_date,
        score_version=config.score_version,
        previous_snapshot=previous_snapshot,
    )
    if existing is not None:
        return existing
    runtime = StrategyRuntimeBudget(timeout_seconds=config.runtime_budget_seconds)

    if inputs is None:
        inputs = _timed(
            runtime,
            "load",
            lambda: load_rolling_inputs(
                anchor_date=anchor_date,
                config=config,
                service=service or "stock_research",
            ),
        )
    else:
        runtime.begin_stage("load")
        runtime.end_stage("load")
    if not isinstance(inputs, RollingInputs) and not hasattr(inputs, "data_cutoff_date"):
        raise TypeError("inputs must provide data_cutoff_date")
    cutoff = _as_date(getattr(inputs, "data_cutoff_date"), "inputs.data_cutoff_date")
    if cutoff > anchor_date:
        raise ValueError("inputs.data_cutoff_date must not follow anchor_date")

    market_regime = _timed(
        runtime,
        "regime",
        lambda: compute_market_regime_features(inputs, anchor_date=anchor_date),
    )
    if not isinstance(market_regime, dict):
        raise TypeError("compute_market_regime_features must return a dictionary")
    market_regime = dict(market_regime)
    market_regime["market_regime"] = (
        str(market_regime.get("market_regime", "unknown")).strip() or "unknown"
    )

    sector_states = _timed(
        runtime,
        "sector",
        lambda: _score_sector_batch_states(
            inputs,
            market_regime=market_regime,
            anchor_date=anchor_date,
        ),
    )
    if not isinstance(sector_states, pd.DataFrame):
        raise TypeError("sector batch scorer must return a pandas DataFrame")
    sector_states = sector_states.copy(deep=True)
    sector_states["market_regime"] = market_regime["market_regime"]
    selected_sectors = _batch_sector_selection(sector_states)
    # Snapshot validation requires every blocked-data row with null repair
    # fields to carry an auditable structured gap.  Derive those gaps from the
    # same in-memory board rather than issuing per-sector follow-up queries.
    blocked_gaps = [
        {
            "dataset": "sector_features",
            "asset_id": f"{row['sector_system']}:{row['sector_code']}",
            "sector_system": str(row["sector_system"]),
            "sector_code": str(row["sector_code"]),
            "start_date": cutoff.isoformat(),
            "end_date": cutoff.isoformat(),
            "expected_rows": 1,
            "actual_rows": 0,
            "reason": "blocked_data_sector_features",
        }
        for _, row in sector_states.iterrows()
        if str(row.get("sector_research_eligibility", "")).strip().casefold()
        == SectorResearchEligibility.BLOCKED_DATA.value
    ]
    if blocked_gaps:
        existing_preflight = market_regime.get("preflight")
        preflight = dict(existing_preflight) if isinstance(existing_preflight, dict) else {}
        existing_gaps = preflight.get("gaps")
        preflight["gaps"] = [
            *(existing_gaps if isinstance(existing_gaps, list) else []),
            *blocked_gaps,
        ]
        market_regime["preflight"] = preflight

    if selected_sectors.empty:
        runtime.stage_timings_seconds.setdefault("stock", 0.0)
        stock_candidates = pd.DataFrame()
    else:
        def score_stocks() -> pd.DataFrame:
            features = _call_batch_stock_feature_builder(
                inputs,
                anchor_date=anchor_date,
                config=config,
                sector_selection=selected_sectors,
            )
            if not isinstance(features, pd.DataFrame):
                raise TypeError("_build_stock_features must return a pandas DataFrame")
            if features.empty:
                return pd.DataFrame()
            return score_rolling_stock_candidates(
                features,
                sector_states,
                top_n=config.sector_output_top_n,
                config=config,
                sector_selection=selected_sectors,
            )

        stock_candidates = _timed(runtime, "stock", score_stocks)

    # Building the normalized probe outside publication keeps the stage timing
    # focused on the immutable write itself while retaining one canonical
    # snapshot representation for callers that do not request disk output.
    snapshot = build_rolling_snapshot(
        anchor_date=anchor_date,
        data_cutoff_date=cutoff,
        market_regime=market_regime,
        sector_states=sector_states,
        stock_candidates=stock_candidates,
        previous_snapshot=previous_snapshot,
        score_version=config.score_version,
        runtime_metadata=runtime.metadata(),
        batch_mode=True,
    )

    paths: dict[str, str] = {}
    batch_manifest: dict[str, object] = {
        "snapshot_id": snapshot["snapshot_id"],
        "anchor_date": snapshot["anchor_date"],
        "data_cutoff_date": snapshot["data_cutoff_date"],
        "score_version": snapshot["score_version"],
        "row_counts": {
            "sector_states": int(len(snapshot["sector_states"])),
            "stock_candidates": int(len(snapshot["stock_candidates"])),
            "sector_daily_board": int(len(snapshot["sector_states"])),
            "sector_stock_candidates": int(len(snapshot["stock_candidates"])),
        },
    }
    runtime.begin_stage("publication")
    publication_closed = False
    supplier_calls = 0

    def publish_runtime_metadata() -> dict[str, object]:
        nonlocal publication_closed, supplier_calls
        supplier_calls += 1
        if supplier_calls > 1 and not publication_closed:
            runtime.end_stage("publication")
            publication_closed = True
        return runtime.metadata()

    def publish_runtime_guard() -> None:
        runtime.checkpoint("publication")

    try:
        if output_dir is not None:
            write_result = write_sector_batch_snapshot(
                snapshot,
                output_dir=output_dir,
                runtime_metadata_supplier=publish_runtime_metadata,
                runtime_publish_guard=publish_runtime_guard,
            )
            manifest_path = Path(str(write_result["manifest_path"]))
            paths = {
                "manifest": str(manifest_path),
                "batch_manifest": str(manifest_path),
                "snapshot_manifest": str(manifest_path),
                "sector_states": str(manifest_path.parent / "sector_states.csv"),
                "stock_candidates": str(manifest_path.parent / "stock_candidates.csv"),
                "sector_daily_board": str(manifest_path.parent / "sector_daily_board.csv"),
                "sector_stock_candidates": str(
                    manifest_path.parent / "sector_stock_candidates.csv"
                ),
            }
            try:
                batch_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                batch_manifest = dict(batch_manifest)
        else:
            # No output directory is a pure in-memory run; still close and
            # expose a deterministic publication timing in the result.
            runtime.end_stage("publication")
            publication_closed = True
    finally:
        if not publication_closed:
            runtime.end_stage("publication")

    metadata = runtime.metadata()
    snapshot["runtime_metadata"] = metadata
    batch_manifest = dict(batch_manifest)
    batch_manifest["runtime_metadata"] = metadata
    return {
        "blocked": False,
        "blocked_reason": "",
        "anchor_date": anchor_date.isoformat(),
        "data_cutoff_date": cutoff.isoformat(),
        "sector_count": int(len(sector_states)),
        "stock_candidate_count": int(len(stock_candidates)),
        "sector_states": snapshot["sector_states"],
        "sector_board": snapshot["sector_states"],
        "sector_daily_board": snapshot["sector_states"],
        "stock_candidates": snapshot["stock_candidates"],
        "sector_stock_candidates": snapshot["stock_candidates"],
        "snapshot": snapshot,
        "batch_manifest": batch_manifest,
        "manifest": batch_manifest,
        "manifest_path": paths.get("manifest"),
        "paths": paths,
        "runtime_seconds": metadata["runtime_seconds"],
        "runtime_metadata": metadata,
    }


def _load_existing_sector_batch_result(
    *,
    output_dir: str | Path | None,
    anchor_date: date,
    score_version: str,
    previous_snapshot: dict[str, object] | None = None,
) -> dict[str, object] | None:
    """Return a previously published batch without recomputing or replacing it."""

    if output_dir is None:
        return None
    destination = (
        Path(output_dir).expanduser().resolve()
        / "rolling_sector_oversold"
        / f"anchor={anchor_date.isoformat()}"
        / f"version={score_version}"
    )
    manifest_path = destination / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    hashes = manifest.get("artifact_hashes")
    aliases = ("sector_daily_board.csv", "sector_stock_candidates.csv")
    if not isinstance(hashes, dict) or not set(aliases).issubset(hashes):
        return None
    for name in aliases:
        expected_hash = hashes.get(name)
        path = destination / name
        if not isinstance(expected_hash, str) or not expected_hash or not path.is_file():
            return None
        try:
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None
        if actual_hash != expected_hash:
            return None
    loaded = load_rolling_oversold_snapshot(destination)
    _assert_existing_snapshot_lineage(loaded, previous_snapshot)
    sectors = loaded.get("sector_states", pd.DataFrame())
    stocks = loaded.get("stock_candidates", pd.DataFrame())
    metadata = manifest.get("runtime_metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    paths = {
        "manifest": str(manifest_path),
        "batch_manifest": str(manifest_path),
        "snapshot_manifest": str(manifest_path),
        "sector_states": str(destination / "sector_states.csv"),
        "stock_candidates": str(destination / "stock_candidates.csv"),
        "sector_daily_board": str(destination / "sector_daily_board.csv"),
        "sector_stock_candidates": str(destination / "sector_stock_candidates.csv"),
    }
    snapshot = dict(loaded)
    snapshot["row_counts"] = manifest.get("row_counts", {})
    snapshot["runtime_metadata"] = metadata
    return {
        "blocked": False,
        "blocked_reason": "",
        "anchor_date": str(manifest.get("anchor_date", anchor_date.isoformat())),
        "data_cutoff_date": str(manifest.get("data_cutoff_date", "")),
        "sector_count": int(len(sectors)) if isinstance(sectors, pd.DataFrame) else 0,
        "stock_candidate_count": int(len(stocks)) if isinstance(stocks, pd.DataFrame) else 0,
        "sector_states": sectors,
        "sector_board": sectors,
        "sector_daily_board": sectors,
        "stock_candidates": stocks,
        "sector_stock_candidates": stocks,
        "snapshot": snapshot,
        "batch_manifest": dict(manifest),
        "manifest": dict(manifest),
        "manifest_path": str(manifest_path),
        "paths": paths,
        "runtime_seconds": metadata.get("runtime_seconds", 0.0),
        "runtime_metadata": metadata,
    }


def run_rolling_replay(
    *,
    config: RollingOversoldConfig,
    output_dir: str | Path,
    service: str,
) -> dict[str, object]:
    """Replay only complete, database-known sessions in ascending order."""

    if not isinstance(config, RollingOversoldConfig):
        raise TypeError("config must be a RollingOversoldConfig")
    runtime = StrategyRuntimeBudget(timeout_seconds=config.runtime_budget_seconds)
    runtime.begin_stage("load")
    try:
        sessions = sorted(_load_complete_anchor_sessions(config=config, service=service))
    finally:
        runtime.end_stage("load")

    previous_snapshot = _load_previous_snapshot(
        output_dir=output_dir,
        before_anchor=sessions[0] if sessions else config.anchor_start_date,
        score_version=config.score_version,
    )
    if sessions:
        unresolved = _unresolved_blocked_anchor(
            output_dir=output_dir,
            after_anchor=_snapshot_anchor_date(previous_snapshot),
            window_start=resolve_rolling_history_start(
                output_dir=output_dir,
                score_version=config.score_version,
                fallback=min(config.anchor_start_date, sessions[0]),
            ),
            before_anchor=sessions[0],
            score_version=config.score_version,
        )
        if unresolved is not None:
            raise ValueError(
                "cannot replay after unresolved blocked anchor "
                f"{unresolved.isoformat()}; repair it before the configured replay start"
            )
    replay_evaluation_cutoff = config.anchor_end_date or (sessions[-1] if sessions else None)
    snapshot_ids: list[str] = []
    blocked_count = 0
    all_sector_rows_have_status = True
    anchors: list[dict[str, object]] = []
    for anchor in sessions:
        anchor_config = replace(
            config,
            anchor_start_date=anchor,
            anchor_end_date=replay_evaluation_cutoff,
        )
        result = run_one_anchor(
            anchor_date=anchor,
            previous_snapshot=previous_snapshot,
            config=anchor_config,
            output_dir=output_dir,
            service=service,
        )
        anchors.append(result)
        blocked_count += int(bool(result.get("blocked")))
        runtime.checkpoint("replay")
        if result.get("blocked"):
            break
        snapshot = result.get("snapshot")
        if isinstance(snapshot, dict):
            previous_snapshot = snapshot
            snapshot_id = snapshot.get("snapshot_id")
            if isinstance(snapshot_id, str) and snapshot_id:
                snapshot_ids.append(snapshot_id)
            all_sector_rows_have_status &= _sector_rows_have_status(snapshot.get("sector_states"))

    metadata = runtime.metadata()
    return {
        "snapshot_ids": snapshot_ids,
        "anchors_processed": len(anchors),
        "blocked": blocked_count,
        "runtime_seconds": metadata["runtime_seconds"],
        "runtime_metadata": metadata,
        "future_rows_used_for_scoring": 0,
        "all_sector_rows_have_status": all_sector_rows_have_status,
        "anchors": anchors,
    }


def run_rolling_daily(
    *,
    trade_date: date,
    config: RollingOversoldConfig,
    output_dir: str | Path,
    service: str,
) -> dict[str, object]:
    """Run the latest database-complete session on or before ``trade_date``."""

    if not isinstance(trade_date, date):
        raise TypeError("trade_date must be a date")
    if not isinstance(config, RollingOversoldConfig):
        raise TypeError("config must be a RollingOversoldConfig")
    lookup_config = replace(
        config,
        anchor_start_date=date(1900, 1, 1),
        anchor_end_date=trade_date,
    )
    sessions = [
        session
        for session in _load_complete_anchor_sessions(config=lookup_config, service=service)
        if session <= trade_date
    ]
    if not sessions:
        raise ValueError("no complete rolling session exists on or before trade_date")
    selected = max(sessions)
    anchor_config = replace(config, anchor_start_date=selected, anchor_end_date=trade_date)
    previous_snapshot = _load_previous_snapshot(
        output_dir=output_dir,
        before_anchor=selected,
        score_version=config.score_version,
    )
    window_start = resolve_rolling_history_start(
        output_dir=output_dir,
        score_version=config.score_version,
        fallback=min(config.anchor_start_date, selected),
    )
    unresolved = _unresolved_blocked_anchor(
        output_dir=output_dir,
        after_anchor=_snapshot_anchor_date(previous_snapshot),
        window_start=window_start,
        before_anchor=selected,
        score_version=config.score_version,
    )
    if unresolved is not None:
        raise ValueError(
            "cannot publish rolling daily snapshot after unresolved blocked anchor "
            f"{unresolved.isoformat()}; repair it and run replay first"
        )
    result = run_one_anchor(
        anchor_date=selected,
        previous_snapshot=previous_snapshot,
        config=anchor_config,
        output_dir=output_dir,
        service=service,
    )
    return {
        **result,
        "requested_trade_date": trade_date.isoformat(),
        "selected_anchor_date": selected.isoformat(),
    }


def _load_complete_anchor_sessions(
    *, config: RollingOversoldConfig, service: str
) -> list[date]:
    """Read sessions bounded by database bars, never by a wall-clock date."""

    if not isinstance(config, RollingOversoldConfig):
        raise TypeError("config must be a RollingOversoldConfig")
    end = (
        config.anchor_end_date.isoformat()
        if config.anchor_end_date is not None
        else date.today().isoformat()
    )
    sql = """
    WITH latest_bar AS (
        SELECT MAX(trade_date) AS trade_date
        FROM market_daily_bar
        WHERE adjust_type = %s
    )
    SELECT DISTINCT calendar.trade_date
    FROM market.trading_calendar AS calendar
    CROSS JOIN latest_bar
    WHERE calendar.is_open = TRUE
      AND calendar.trade_date >= %s
      AND calendar.trade_date <= latest_bar.trade_date
      AND (%s::date IS NULL OR calendar.trade_date <= %s::date)
    ORDER BY calendar.trade_date
    """
    with connect(service) as connection:
        rows = fetch_all(
            connection,
            sql,
            [config.adjust_type, config.anchor_start_date.isoformat(), end, end],
        )
    sessions = sorted({_as_date(row.get("trade_date"), "calendar trade_date") for row in rows})
    return sessions


def _timed(runtime: StrategyRuntimeBudget, stage: str, operation: Any) -> Any:
    runtime.begin_stage(stage)
    try:
        return operation()
    finally:
        runtime.end_stage(stage)


def _score_all_sector_states(
    inputs: RollingInputs | Any,
    *,
    market_regime: dict[str, object],
    anchor_date: date,
) -> pd.DataFrame:
    industry = score_sector_states(
        getattr(inputs, "industry_bars"),
        membership=getattr(inputs, "industry_membership"),
        market_regime=market_regime,
        anchor_date=anchor_date,
    ).copy(deep=True)
    industry["__sector_family"] = "industry"
    concept = score_sector_states(
        getattr(inputs, "concept_bars"),
        membership=getattr(inputs, "concept_membership"),
        market_regime=market_regime,
        anchor_date=anchor_date,
    ).copy(deep=True)
    concept["__sector_family"] = "concept"
    return _canonicalize_sector_states(pd.concat([industry, concept], ignore_index=True, sort=False))


def _score_sector_batch_states(
    inputs: RollingInputs | Any,
    *,
    market_regime: dict[str, object],
    anchor_date: date,
) -> pd.DataFrame:
    """Score canonical industry/concept inputs with one scorer invocation."""

    bar_frames: list[pd.DataFrame] = []
    membership_frames: list[pd.DataFrame] = []
    family_by_key: dict[tuple[str, str], str] = {}
    for family, source_bars, source_membership, system, code, name in (
        (
            "industry",
            getattr(inputs, "industry_bars", pd.DataFrame()),
            getattr(inputs, "industry_membership", pd.DataFrame()),
            "industry_system",
            "industry_code",
            "industry_name",
        ),
        (
            "concept",
            getattr(inputs, "concept_bars", pd.DataFrame()),
            getattr(inputs, "concept_membership", pd.DataFrame()),
            "concept_system",
            "concept_code",
            "concept_name",
        ),
    ):
        bars = _canonical_batch_frame(
            source_bars,
            family=family,
            system=system,
            code=code,
            name=name,
            membership=False,
        )
        members = _canonical_batch_frame(
            source_membership,
            family=family,
            system=system,
            code=code,
            name=name,
            membership=True,
        )
        if not bars.empty:
            bar_frames.append(bars)
        if not members.empty:
            membership_frames.append(members)
        for frame in (bars, members):
            if frame.empty:
                continue
            for system_value, code_value in frame.loc[:, ["sector_system", "sector_code"]].itertuples(
                index=False, name=None
            ):
                if pd.notna(system_value) and pd.notna(code_value):
                    family_by_key[(str(system_value), str(code_value))] = family

    bars = (
        pd.concat(bar_frames, ignore_index=True, sort=False)
        if bar_frames
        else pd.DataFrame(
            columns=[
                "sector_system",
                "sector_code",
                "sector_name",
                "trade_date",
                "close",
                "preclose",
                "volume",
                "amount",
            ]
        )
    )
    members = (
        pd.concat(membership_frames, ignore_index=True, sort=False)
        if membership_frames
        else pd.DataFrame(
            columns=[
                "asset_id",
                "sector_system",
                "sector_code",
                "sector_name",
                "start_date",
                "end_date",
            ]
        )
    )
    scored = score_sector_states(
        bars,
        membership=members,
        market_regime=market_regime,
        anchor_date=anchor_date,
    ).copy(deep=True)
    if scored.empty:
        return _canonicalize_sector_states(scored)
    scored["__sector_family"] = [
        family_by_key.get((str(system_value), str(code_value)), "unknown")
        for system_value, code_value in scored.loc[:, ["sector_system", "sector_code"]].itertuples(
            index=False, name=None
        )
    ]
    return _canonicalize_sector_states(scored)


def _canonical_batch_frame(
    frame: object,
    *,
    family: str,
    system: str,
    code: str,
    name: str,
    membership: bool,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    result = frame.copy(deep=True)
    for canonical, source in (
        ("sector_system", system),
        ("sector_code", code),
        ("sector_name", name),
    ):
        if canonical not in result:
            result[canonical] = result.get(source, pd.NA)
        elif source in result:
            result[canonical] = result[canonical].fillna(result[source])
        result[canonical] = result[canonical].astype("string").str.strip().replace("", pd.NA)
    result["__sector_family"] = family
    required = ["sector_system", "sector_code", "sector_name"]
    if membership:
        required = ["asset_id", *required, "start_date", "end_date"]
    else:
        required.extend(["trade_date", "close", "preclose", "volume", "amount"])
    for column in required:
        if column not in result:
            result[column] = pd.NA
    return result.loc[:, required + ["__sector_family"]]


def _batch_sector_selection(sector_states: pd.DataFrame) -> pd.DataFrame:
    """Return every research-visible sector without a global top-N gate."""

    if sector_states.empty:
        return sector_states.copy(deep=True)
    eligibility = sector_states.get(
        "sector_research_eligibility", pd.Series(pd.NA, index=sector_states.index)
    )
    explicit = eligibility.notna().any()
    if explicit:
        normalized = eligibility.astype("string").str.strip().str.casefold().replace("", pd.NA)
        gate = sector_states["sector_gate_status"].astype("string").str.strip().str.casefold()
        normalized = normalized.fillna(
            gate.map(
                {
                    GateStatus.CONFIRMED.value: SectorResearchEligibility.ELIGIBLE.value,
                    GateStatus.WATCH.value: SectorResearchEligibility.WATCH.value,
                    GateStatus.BLOCKED.value: SectorResearchEligibility.BLOCKED_DATA.value,
                }
            )
        )
        selected = sector_states.loc[
            normalized.isin(
                {
                    SectorResearchEligibility.ELIGIBLE.value,
                    SectorResearchEligibility.WATCH.value,
                }
            )
        ].copy()
    else:
        selected = sector_states.loc[
            ~sector_states["sector_gate_status"].eq(GateStatus.BLOCKED.value)
        ].copy()
    return selected.reset_index(drop=True)


def _canonicalize_sector_states(states: pd.DataFrame) -> pd.DataFrame:
    """Keep every source mapping, including malformed mappings, auditable."""

    if not isinstance(states, pd.DataFrame):
        raise TypeError("sector states must be a pandas DataFrame")
    if states.empty:
        return pd.DataFrame(
            columns=[
                "sector_system",
                "sector_code",
                "sector_name",
                "sector_oversold_score",
                "sector_repairability_score",
                "sector_direction_score",
                "sector_recovery_state",
                "sector_gate_status",
                "__sector_family",
                "__source_system",
                "__source_code",
            ]
        )
    result = states.copy(deep=True).reset_index(drop=True)
    family = result.get("__sector_family", pd.Series("unknown", index=result.index))
    result["__sector_family"] = family.astype("string").fillna("unknown").str.strip().replace("", "unknown")
    for column in ("sector_system", "sector_code", "sector_name"):
        values = result.get(column, pd.Series(pd.NA, index=result.index, dtype="string"))
        result[column] = values.astype("string").str.strip().replace("", pd.NA)
    result["__source_system"] = result["sector_system"]
    result["__source_code"] = result["sector_code"]
    invalid_mapping = result["sector_system"].isna() | result["sector_code"].isna() | result["sector_name"].isna()
    if "sector_mapping_valid" in result:
        invalid_mapping |= ~result["sector_mapping_valid"].fillna(False).astype(bool)
    result.loc[result["sector_system"].isna(), "sector_system"] = (
        result.loc[result["sector_system"].isna(), "__sector_family"].astype(str)
        + ":__missing_sector_system__"
    )
    result.loc[result["sector_code"].isna(), "sector_code"] = [
        f"__missing_sector_code__:{index}"
        for index in result.index[result["sector_code"].isna()]
    ]
    result.loc[result["sector_name"].isna(), "sector_name"] = (
        "Unmapped " + result.loc[result["sector_name"].isna(), "__sector_family"].astype(str) + " sector"
    )
    for column in ("sector_recovery_state", "sector_gate_status"):
        values = result.get(column, pd.Series(pd.NA, index=result.index, dtype="string"))
        result[column] = values.astype("string").str.strip().str.casefold().replace("", pd.NA)
    if "sector_research_eligibility" in result:
        values = result["sector_research_eligibility"]
        result["sector_research_eligibility"] = (
            values.astype("string").str.strip().str.casefold().replace("", pd.NA)
        )
    result["sector_recovery_state"] = result["sector_recovery_state"].fillna("unknown")
    result["sector_gate_status"] = result["sector_gate_status"].fillna(GateStatus.BLOCKED.value)
    for column in (
        "sector_oversold_score",
        "sector_repairability_score",
        "sector_direction_score",
    ):
        result[column] = pd.to_numeric(result.get(column), errors="coerce")
    invalid_scores = result[
        ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"]
    ].isna().any(axis=1)
    result.loc[invalid_mapping | invalid_scores, "sector_gate_status"] = GateStatus.BLOCKED.value
    if (
        "sector_research_eligibility" in result
        and result["sector_research_eligibility"].notna().any()
    ):
        fallback = result["sector_gate_status"].map(
            {
                GateStatus.CONFIRMED.value: SectorResearchEligibility.ELIGIBLE.value,
                GateStatus.WATCH.value: SectorResearchEligibility.WATCH.value,
                GateStatus.BLOCKED.value: SectorResearchEligibility.BLOCKED_DATA.value,
            }
        )
        result["sector_research_eligibility"] = result[
            "sector_research_eligibility"
        ].fillna(fallback)

    duplicates = result.duplicated(["sector_system", "sector_code"], keep=False)
    if duplicates.any():
        result.loc[duplicates, "sector_system"] = (
            result.loc[duplicates, "__sector_family"].astype(str)
            + ":"
            + result.loc[duplicates, "sector_system"].astype(str)
        )
    result = result.sort_values(
        ["sector_system", "sector_code", "sector_name", "__sector_family"],
        kind="mergesort",
    ).reset_index(drop=True)
    duplicates = result.duplicated(["sector_system", "sector_code"], keep=False)
    if duplicates.any():
        result.loc[duplicates, "sector_code"] = [
            f"{code}#{position + 1}"
            for position, code in enumerate(result.loc[duplicates, "sector_code"].astype(str))
        ]
    return result


def _gated_sector_rows(sector_states: pd.DataFrame, *, top_n: int) -> pd.DataFrame:
    if sector_states.empty:
        return sector_states.copy(deep=True)
    eligibility = sector_states.get(
        "sector_research_eligibility", pd.Series(pd.NA, index=sector_states.index)
    )
    explicit_eligibility = eligibility.notna().any()
    if explicit_eligibility:
        normalized_eligibility = (
            eligibility.astype("string").str.strip().str.casefold().replace("", pd.NA)
        )
        gate = (
            sector_states["sector_gate_status"]
            .astype("string")
            .str.strip()
            .str.casefold()
        )
        normalized_eligibility = normalized_eligibility.fillna(
            gate.map(
                {
                    GateStatus.CONFIRMED.value: SectorResearchEligibility.ELIGIBLE.value,
                    GateStatus.WATCH.value: SectorResearchEligibility.WATCH.value,
                    GateStatus.BLOCKED.value: SectorResearchEligibility.BLOCKED_DATA.value,
                }
            )
        )
        gated = sector_states.loc[
            normalized_eligibility.isin(
                {
                    SectorResearchEligibility.ELIGIBLE.value,
                    SectorResearchEligibility.WATCH.value,
                }
            )
        ].copy()
    else:
        # Legacy sector frames have no explicit visibility field.  Preserve
        # the old gate behavior for those inputs.
        gated = sector_states.loc[
            ~sector_states["sector_gate_status"].eq(GateStatus.BLOCKED.value)
        ].copy()
    if gated.empty:
        return gated
    gated = gated.sort_values(
        ["sector_oversold_score", "sector_system", "sector_code"],
        ascending=[False, True, True],
        kind="mergesort",
        na_position="last",
    )
    return gated.head(top_n).reset_index(drop=True)


def _score_gated_stock_candidates(
    inputs: RollingInputs | Any,
    *,
    sector_states: pd.DataFrame,
    gated_sectors: pd.DataFrame,
    anchor_date: date,
    config: RollingOversoldConfig,
) -> pd.DataFrame:
    features = _build_stock_features(inputs, anchor_date=anchor_date, config=config)
    features = _remap_feature_sector_identity(features, sector_states)
    if features.empty:
        return pd.DataFrame()
    context = gated_sectors.loc[
        :, ["sector_system", "sector_code", "sector_oversold_score"]
    ].copy()
    joined = features.merge(context, on=["sector_system", "sector_code"], how="inner", sort=False)
    if joined.empty:
        return pd.DataFrame()
    # A stock may belong to an industry and a concept.  Keep the immutable
    # stock artifact's unique-asset contract by scoring it once against its
    # strongest permitted sector; sector_stock_rank remains local to that
    # selected sector rather than being merged into the compatibility rank.
    joined = joined.sort_values(
        ["asset_id", "sector_oversold_score", "sector_system", "sector_code"],
        ascending=[True, False, True, True],
        kind="mergesort",
    ).drop_duplicates("asset_id", keep="first")
    return score_rolling_stock_candidates(
        joined.drop(columns="sector_oversold_score", errors="ignore"),
        sector_states,
        top_n=config.stock_top_n,
        config=config,
        sector_selection=gated_sectors,
    )


def _call_batch_stock_feature_builder(
    inputs: RollingInputs | Any,
    *,
    anchor_date: date,
    config: RollingOversoldConfig,
    sector_selection: pd.DataFrame,
) -> pd.DataFrame:
    """Invoke stock feature builders with legacy monkeypatch compatibility."""

    builder = _build_stock_features
    try:
        parameters = inspect.signature(builder).parameters.values()
    except (TypeError, ValueError):
        parameters = ()
    accepts_selection = any(
        parameter.name == "sector_selection"
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
    kwargs: dict[str, object] = {
        "anchor_date": anchor_date,
        "config": config,
    }
    if accepts_selection:
        kwargs["sector_selection"] = sector_selection
    return builder(inputs, **kwargs)


def _build_stock_features(
    inputs: RollingInputs | Any,
    *,
    anchor_date: date,
    config: RollingOversoldConfig,
    sector_selection: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Derive score inputs only from frozen rolling loader frames."""

    memberships = _stock_memberships(
        inputs,
        anchor_date=anchor_date,
        sector_selection=sector_selection,
    )
    if memberships.empty:
        return pd.DataFrame()
    bars = getattr(inputs, "stock_bars", pd.DataFrame())
    if not isinstance(bars, pd.DataFrame):
        raise TypeError("stock_bars must be a pandas DataFrame")
    prepared_bars = _prepared_bars(bars, anchor_date=anchor_date)
    status = _latest_status(getattr(inputs, "stock_status", pd.DataFrame()), anchor_date=anchor_date)
    finance = _latest_pit_frame(
        getattr(inputs, "finance", pd.DataFrame()),
        date_column="announcement_date",
        cutoff=anchor_date,
    )
    valuation = _latest_pit_frame(
        getattr(inputs, "valuation", pd.DataFrame()),
        date_column="valuation_date",
        cutoff=anchor_date,
    )
    bars_by_asset = {
        str(asset_id): frame
        for asset_id, frame in prepared_bars.groupby("asset_id", sort=False)
    }
    finance_field_maps = _latest_pit_field_maps(
        getattr(inputs, "finance", pd.DataFrame()),
        fields=("roe", "total_share"),
        cutoff=anchor_date,
    )
    rows: list[dict[str, object]] = []
    for membership in memberships.to_dict(orient="records"):
        asset_id = str(membership["asset_id"])
        if _is_ineligible_status(status.get(asset_id)):
            continue
        asset_bars = bars_by_asset.get(asset_id, prepared_bars.iloc[0:0])
        if asset_bars.empty:
            _raise_stock_gap(asset_id, anchor_date, "market_daily_bar", "missing_stock_bar")
        closes = asset_bars["close"].dropna()
        amounts = asset_bars["amount"].dropna()
        if closes.empty or float(closes.iloc[-1]) <= 0:
            _raise_stock_gap(asset_id, anchor_date, "market_daily_bar", "missing_positive_anchor_close")
        if amounts.empty:
            _raise_stock_gap(asset_id, anchor_date, "market_daily_bar", "missing_activity_amount")
        finance_row = finance.get(asset_id)
        valuation_row = valuation.get(asset_id)
        roe = _finite_row_value(finance_row, "roe")
        total_share = _finite_row_value(finance_row, "total_share")
        if roe is None:
            roe = finance_field_maps.get("roe", {}).get(asset_id)
        if total_share is None:
            total_share = finance_field_maps.get("total_share", {}).get(asset_id)
        pe_ttm = _finite_row_value(valuation_row, "pe_ttm")
        valuation_multiple = _valuation_multiple(valuation_row)
        if roe is None:
            _raise_stock_gap(asset_id, anchor_date, "finance_history", "missing_roe")
        if total_share is None or total_share <= 0:
            _raise_stock_gap(asset_id, anchor_date, "finance_history", "missing_total_share")
        if valuation_multiple is None:
            _raise_stock_gap(
                asset_id, anchor_date, "valuation_history", "missing_pe_or_ps_ttm"
            )
        latest_close = float(closes.iloc[-1])
        trailing = closes.tail(252)
        low = float(trailing.tail(60).min())
        high = float(trailing.max())
        anchor_return = latest_close / low - 1.0 if low > 0 else 0.0
        distance = 1.0 - latest_close / high if high > 0 else 0.0
        return_20d = _period_return(closes, 20)
        quality = roe * 100.0 if abs(roe) <= 1.0 else roe
        rows.append(
            {
                "asset_id": asset_id,
                "sector_system": membership["sector_system"],
                "sector_code": membership["sector_code"],
                "sector_name": membership["sector_name"],
                "__sector_family": membership["__sector_family"],
                "anchor_return": anchor_return,
                "distance_to_252d_high": max(0.0, distance),
                "oversold_depth": max(0.0, distance),
                "stock_excess_return": return_20d,
                "activity": float(amounts.tail(20).mean()),
                "quality": max(0.0, min(100.0, quality)),
                "valuation": max(0.0, min(100.0, 100.0 - valuation_multiple)),
                "size_elasticity": latest_close * total_share,
                "anchor_close": latest_close,
                "adjusted_close_source": config.adjust_type,
            }
        )
    return pd.DataFrame(rows)


def _stock_memberships(
    inputs: RollingInputs | Any,
    *,
    anchor_date: date,
    sector_selection: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for family, source, system, code, name in (
        ("industry", getattr(inputs, "industry_membership", pd.DataFrame()), "industry_system", "industry_code", "industry_name"),
        ("concept", getattr(inputs, "concept_membership", pd.DataFrame()), "concept_system", "concept_code", "concept_name"),
    ):
        if not isinstance(source, pd.DataFrame) or source.empty or "asset_id" not in source:
            continue
        frame = source.copy(deep=True)
        anchor_timestamp = pd.Timestamp(anchor_date)
        if "start_date" in frame:
            starts = pd.to_datetime(frame["start_date"], errors="coerce")
            frame = frame.loc[starts.isna() | starts.le(anchor_timestamp)]
        if "end_date" in frame:
            ends = pd.to_datetime(frame["end_date"], errors="coerce")
            frame = frame.loc[ends.isna() | ends.gt(anchor_timestamp)]
        frame = frame.assign(
            asset_id=frame["asset_id"].astype("string").str.strip(),
            sector_system=frame.get(system, pd.Series(pd.NA, index=frame.index)).astype("string").str.strip(),
            sector_code=frame.get(code, pd.Series(pd.NA, index=frame.index)).astype("string").str.strip(),
            sector_name=frame.get(name, pd.Series(pd.NA, index=frame.index)).astype("string").str.strip(),
            __sector_family=family,
        )
        frame = frame.loc[frame["asset_id"].notna() & ~frame["asset_id"].eq("")]
        frames.append(frame.loc[:, ["asset_id", "sector_system", "sector_code", "sector_name", "__sector_family"]])
    if not frames:
        return pd.DataFrame(columns=["asset_id", "sector_system", "sector_code", "sector_name", "__sector_family"])
    result = pd.concat(frames, ignore_index=True, sort=False)
    if isinstance(sector_selection, pd.DataFrame) and not sector_selection.empty:
        keys = sector_selection.loc[:, ["sector_system", "sector_code"]].drop_duplicates()
        selected_index = pd.MultiIndex.from_frame(keys)
        membership_index = pd.MultiIndex.from_frame(
            result.loc[:, ["sector_system", "sector_code"]]
        )
        result = result.loc[membership_index.isin(selected_index)].copy()
    return result.sort_values(
        ["asset_id", "__sector_family", "sector_system", "sector_code"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)


def _remap_feature_sector_identity(features: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    if features.empty or states.empty:
        return features.copy(deep=True)
    result = features.copy(deep=True)
    if "__sector_family" not in result:
        result["__sector_family"] = "industry"
    mapping = states.loc[
        :, ["__sector_family", "__source_system", "__source_code", "sector_system", "sector_code", "sector_name"]
    ].copy()
    mapping = mapping.loc[
        mapping["__source_system"].notna() & mapping["__source_code"].notna()
    ].drop_duplicates(["__sector_family", "__source_system", "__source_code"], keep="last")
    if mapping.empty:
        return result
    result = result.merge(
        mapping,
        how="left",
        left_on=["__sector_family", "sector_system", "sector_code"],
        right_on=["__sector_family", "__source_system", "__source_code"],
        suffixes=("", "_canonical"),
        sort=False,
    )
    for column in ("sector_system", "sector_code", "sector_name"):
        canonical = f"{column}_canonical"
        if canonical in result:
            result[column] = result[canonical].fillna(result[column])
    return result.drop(
        columns=[
            "__source_system",
            "__source_code",
            "sector_system_canonical",
            "sector_code_canonical",
            "sector_name_canonical",
        ],
        errors="ignore",
    )


def _prepared_bars(frame: pd.DataFrame, *, anchor_date: date) -> pd.DataFrame:
    required = {"asset_id", "trade_date", "close"}
    if not required.issubset(frame.columns):
        return pd.DataFrame(columns=["asset_id", "trade_date", "close", "amount"])
    result = frame.copy(deep=True)
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result["amount"] = pd.to_numeric(result.get("amount"), errors="coerce")
    result = result.loc[result["trade_date"].notna() & result["trade_date"].le(pd.Timestamp(anchor_date))]
    return result.sort_values(["asset_id", "trade_date"], kind="mergesort").drop_duplicates(
        ["asset_id", "trade_date"], keep="last"
    )


def _latest_status(frame: object, *, anchor_date: date) -> dict[str, dict[str, object]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"asset_id", "trade_date"}.issubset(frame.columns):
        return {}
    result = frame.copy(deep=True)
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result = result.loc[result["trade_date"].notna() & result["trade_date"].le(pd.Timestamp(anchor_date))]
    result = result.sort_values(["asset_id", "trade_date"], kind="mergesort").drop_duplicates("asset_id", keep="last")
    return {str(row["asset_id"]): row for row in result.to_dict(orient="records")}


def _latest_pit_frame(frame: object, *, date_column: str, cutoff: date) -> dict[str, dict[str, object]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"asset_id", date_column}.issubset(frame.columns):
        return {}
    result = frame.copy(deep=True)
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    result[date_column] = pd.to_datetime(result[date_column], errors="coerce")
    result = result.loc[result[date_column].notna() & result[date_column].le(pd.Timestamp(cutoff))]
    result = result.sort_values(["asset_id", date_column], kind="mergesort").drop_duplicates("asset_id", keep="last")
    return {str(row["asset_id"]): row for row in result.to_dict(orient="records")}


def _latest_pit_field(
    frame: object,
    *,
    asset_id: str,
    date_column: str,
    field: str,
    cutoff: date,
) -> float | None:
    if not isinstance(frame, pd.DataFrame):
        return None
    required = {"asset_id", date_column, field}
    if not required.issubset(frame.columns):
        return None
    result = frame.copy(deep=True)
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    result[date_column] = pd.to_datetime(result[date_column], errors="coerce")
    result[field] = pd.to_numeric(result[field], errors="coerce")
    result = result.loc[
        result["asset_id"].eq(asset_id)
        & result[date_column].notna()
        & result[date_column].le(pd.Timestamp(cutoff))
        & result[field].notna()
    ].sort_values(date_column, ascending=False, kind="mergesort")
    if result.empty:
        return None
    value = result.iloc[0][field]
    return float(value) if pd.notna(value) else None


def _latest_pit_field_maps(
    frame: object,
    *,
    fields: tuple[str, ...],
    cutoff: date,
) -> dict[str, dict[str, float]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {field: {} for field in fields}
    required = {"asset_id", "announcement_date", *fields}
    if not required.issubset(frame.columns):
        return {field: {} for field in fields}
    result = frame.loc[:, list(required)].copy()
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    result["announcement_date"] = pd.to_datetime(
        result["announcement_date"], errors="coerce"
    )
    result = result.loc[
        result["asset_id"].notna()
        & result["announcement_date"].notna()
        & result["announcement_date"].le(pd.Timestamp(cutoff))
    ].sort_values("announcement_date", ascending=False, kind="mergesort")
    maps: dict[str, dict[str, float]] = {}
    for field in fields:
        values = pd.to_numeric(result[field], errors="coerce")
        selected = result.loc[values.notna(), ["asset_id"]].copy()
        selected["value"] = values.loc[selected.index].astype(float)
        selected = selected.drop_duplicates("asset_id", keep="first")
        maps[field] = {
            str(row["asset_id"]): float(row["value"])
            for row in selected.to_dict(orient="records")
        }
    return maps


def _is_ineligible_status(row: dict[str, object] | None) -> bool:
    if row is None:
        return False
    is_trade = _optional_bool(row.get("is_trade"))
    return _optional_bool(row.get("is_st")) or _optional_bool(row.get("is_suspended")) or is_trade is False


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return bool(value)


def _finite_row_value(row: dict[str, object] | None, column: str) -> float | None:
    if row is None:
        return None
    value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _valuation_multiple(row: dict[str, object] | None) -> float | None:
    """Select PE first, then a positive PS fallback for loss-making firms."""

    pe = _finite_row_value(row, "pe_ttm")
    if pe is not None and pe > 0.0:
        return pe
    ps = _finite_row_value(row, "ps_ttm")
    if ps is not None and ps > 0.0:
        return ps
    return None


def _period_return(closes: pd.Series, periods: int) -> float:
    if len(closes) <= periods:
        return 0.0
    start = float(closes.iloc[-periods - 1])
    return float(closes.iloc[-1] / start - 1.0) if start > 0 else 0.0


def _raise_stock_gap(asset_id: str, anchor_date: date, dataset: str, reason: str) -> None:
    raise StockScoringDataGap(
        DataGap(
            dataset=dataset,
            asset_id=asset_id,
            start_date=anchor_date.isoformat(),
            end_date=anchor_date.isoformat(),
            expected_rows=1,
            actual_rows=0,
            reason=reason,
        )
    )


def _ensure_frozen_candidate_prices(
    candidates: pd.DataFrame,
    *,
    stock_bars: object,
    cutoff: date,
    config: RollingOversoldConfig,
    market_regime: str,
) -> pd.DataFrame:
    if not isinstance(candidates, pd.DataFrame):
        raise TypeError("stock candidates must be a pandas DataFrame")
    if candidates.empty:
        return candidates.copy(deep=True)
    result = candidates.copy(deep=True)
    result["market_regime"] = result.get(
        "market_regime", pd.Series(market_regime, index=result.index, dtype="string")
    ).astype("string").str.strip().replace("", pd.NA).fillna(market_regime)
    prepared = _prepared_bars(stock_bars if isinstance(stock_bars, pd.DataFrame) else pd.DataFrame(), anchor_date=cutoff)
    latest = prepared.sort_values(["asset_id", "trade_date"], kind="mergesort").drop_duplicates("asset_id", keep="last")
    closes = {
        str(row["asset_id"]): float(row["close"])
        for row in latest.to_dict(orient="records")
        if pd.notna(row["close"]) and float(row["close"]) > 0
    }
    raw_anchor_source = result.get("anchor_close")
    if raw_anchor_source is None:
        raw_anchor = pd.Series(float("nan"), index=result.index)
    else:
        raw_anchor = pd.to_numeric(raw_anchor_source, errors="coerce")
    source = result.get("adjusted_close_source", pd.Series(pd.NA, index=result.index, dtype="string"))
    source = source.astype("string").str.strip().replace("", pd.NA)
    excluded = (
        result.get("sector_gate_status", pd.Series("", index=result.index)).astype("string").str.casefold().eq(GateStatus.BLOCKED.value)
        | result.get("stock_lifecycle", pd.Series("", index=result.index)).astype("string").str.casefold().eq(StockLifecycle.INVALIDATED.value)
    )
    for index, asset_id in result["asset_id"].astype(str).items():
        if bool(excluded.loc[index]):
            continue
        if pd.isna(raw_anchor.loc[index]) or float(raw_anchor.loc[index]) <= 0:
            close = closes.get(asset_id)
            if close is None:
                _raise_stock_gap(asset_id, cutoff, "market_daily_bar", "missing_frozen_anchor_close")
            raw_anchor.loc[index] = close
        if pd.isna(source.loc[index]):
            source.loc[index] = config.adjust_type
    result["anchor_close"] = raw_anchor
    result["adjusted_close_source"] = source
    return result


def _evaluation_bars(stock_bars: object, adjust_type: str) -> pd.DataFrame:
    if not isinstance(stock_bars, pd.DataFrame):
        return pd.DataFrame(columns=["asset_id", "trade_date", f"{adjust_type}_close"])
    required = {"asset_id", "trade_date", "close"}
    if not required.issubset(stock_bars.columns):
        return pd.DataFrame(columns=["asset_id", "trade_date", f"{adjust_type}_close"])
    result = stock_bars.loc[:, ["asset_id", "trade_date", "close"]].copy(deep=True)
    return result.rename(columns={"close": f"{adjust_type}_close"})


def _evaluation_artifact_bytes(
    detail: pd.DataFrame, summary: pd.DataFrame
) -> dict[str, bytes]:
    return {
        "evaluation_detail.csv": detail.to_csv(index=False, lineterminator="\n").encode("utf-8"),
        "evaluation_summary.csv": summary.to_csv(index=False, lineterminator="\n").encode("utf-8"),
    }


def _evaluation_cutoff_from_directory(directory: Path | None) -> date | None:
    if directory is None:
        return None
    manifest_path = directory / "evaluation_manifest.json"
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            value = payload.get("evaluation_cutoff")
            if value:
                return _as_date(value, "evaluation_cutoff")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass
    detail_path = directory / "evaluation_detail.csv"
    if not detail_path.is_file() or detail_path.stat().st_size == 0:
        return None
    try:
        detail = pd.read_csv(detail_path, usecols=["evaluation_cutoff"])
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return None
    values = pd.to_datetime(detail["evaluation_cutoff"], errors="coerce").dropna()
    return values.max().date() if not values.empty else None


def _evaluation_runtime_metadata_from_directory(
    directory: Path | None,
) -> dict[str, object] | None:
    if directory is None:
        return None
    manifest_path = directory / "evaluation_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    runtime_metadata = payload.get("runtime_metadata")
    return dict(runtime_metadata) if isinstance(runtime_metadata, dict) else None


def _evaluation_has_pending_rows(directory: Path | None) -> bool:
    """Return whether the latest evaluation still has horizons awaiting bars."""

    if directory is None:
        return True
    detail_path = directory / "evaluation_detail.csv"
    if not detail_path.is_file() or detail_path.stat().st_size == 0:
        return True
    try:
        statuses = pd.read_csv(detail_path, usecols=["evaluation_status"])["evaluation_status"]
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return True
    normalized = statuses.astype("string").fillna("").str.strip().str.casefold()
    return bool(normalized.eq("pending").any())


def _evaluation_artifacts_match(directory: Path, artifacts: dict[str, bytes]) -> bool:
    return all(
        (path := directory / name).is_file() and path.read_bytes() == contents
        for name, contents in artifacts.items()
    )


def _persist_evaluation_revision(
    *,
    snapshot: dict[str, object],
    snapshot_dir: Path,
    detail: pd.DataFrame,
    summary: pd.DataFrame,
    evaluation_cutoff: date,
    runtime_metadata_supplier: Any | None = None,
    runtime_publish_guard: Any | None = None,
) -> dict[str, object]:
    existing_revisions: list[int] = []
    for revision_dir in snapshot_dir.glob("evaluation_revision=*"):
        match = revision_dir.name.removeprefix("evaluation_revision=")
        if match.isdigit():
            existing_revisions.append(int(match))
    artifacts = _evaluation_artifact_bytes(detail, summary)
    latest_directory = latest_rolling_evaluation_directory(snapshot_dir)
    if latest_directory is not None and _evaluation_artifacts_match(
        latest_directory, artifacts
    ):
        runtime_metadata = _evaluation_runtime_metadata_from_directory(latest_directory)
        if runtime_metadata is None:
            persisted = snapshot.get("manifest", {})
            persisted = persisted.get("runtime_metadata", {}) if isinstance(persisted, dict) else {}
            runtime_metadata = dict(persisted) if isinstance(persisted, dict) else {}
        return {
            "revision": _path_revision(latest_directory),
            "evaluation": latest_directory / "evaluation_detail.csv",
            "evaluation_summary": latest_directory / "evaluation_summary.csv",
            "evaluation_manifest": latest_directory / "evaluation_manifest.json",
            "runtime_metadata": runtime_metadata,
        }
    revision = max(existing_revisions, default=0) + 1
    destination = snapshot_dir / f"evaluation_revision={revision:04d}"
    staging = Path(
        tempfile.mkdtemp(prefix=f".evaluation_revision={revision:04d}.", dir=snapshot_dir)
    )
    artifact_hashes = {
        name: hashlib.sha256(contents).hexdigest()
        for name, contents in artifacts.items()
    }
    published = False
    try:
        for name, contents in artifacts.items():
            path = staging / name
            path.write_bytes(contents)
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        _fsync_directory(staging)
        runtime_metadata = (
            runtime_metadata_supplier() if runtime_metadata_supplier is not None else {}
        )
        manifest = {
            "snapshot_id": snapshot.get("snapshot_id", ""),
            "anchor_date": snapshot.get("anchor_date", ""),
            "score_version": snapshot.get("score_version", ""),
            "evaluation_cutoff": evaluation_cutoff.isoformat(),
            "revision": revision,
            "runtime_metadata": runtime_metadata,
            "artifact_hashes": artifact_hashes,
        }
        manifest_path = staging / "evaluation_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        with manifest_path.open("rb") as handle:
            os.fsync(handle.fileno())
        _fsync_directory(staging)
        if runtime_metadata_supplier is not None:
            runtime_metadata = runtime_metadata_supplier()
            manifest["runtime_metadata"] = runtime_metadata
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            with manifest_path.open("rb") as handle:
                os.fsync(handle.fileno())
            _fsync_directory(staging)
        if destination.exists():
            raise ValueError(f"evaluation revision already exists at {destination}")
        if runtime_publish_guard is not None:
            runtime_publish_guard()
        os.replace(staging, destination)
        published = True
        _fsync_directory(snapshot_dir)
        return {
            "revision": revision,
            "evaluation": destination / "evaluation_detail.csv",
            "evaluation_summary": destination / "evaluation_summary.csv",
            "evaluation_manifest": destination / "evaluation_manifest.json",
            "runtime_metadata": runtime_metadata,
        }
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _snapshot_asset_ids(snapshot: dict[str, object]) -> list[str]:
    candidates = snapshot.get("stock_candidates")
    if not isinstance(candidates, pd.DataFrame) or candidates.empty or "asset_id" not in candidates:
        return []
    selected = candidates
    if "stock_rank" in selected:
        ranks = pd.to_numeric(selected["stock_rank"], errors="coerce")
        selected = selected.loc[ranks.notna()]
    asset_ids: set[str] = set()
    for value in selected["asset_id"]:
        if pd.isna(value):
            continue
        asset_id = str(value).strip()
        if asset_id:
            asset_ids.add(asset_id)
    return sorted(asset_ids)


def _load_evaluation_bars(
    *,
    asset_ids: Iterable[str],
    anchor_date: date,
    evaluation_cutoff: date,
    adjust_type: str,
    service: str,
) -> pd.DataFrame:
    """Load only post-anchor prices used by delayed outcome evaluation."""

    selected = sorted({str(asset_id).strip() for asset_id in asset_ids if str(asset_id).strip()})
    columns = ["asset_id", "trade_date", "close"]
    if not selected or evaluation_cutoff <= anchor_date:
        return pd.DataFrame(columns=columns)
    sql = """
    SELECT asset_id, trade_date, close
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND asset_id = ANY(%s)
      AND trade_date > %s::date
      AND trade_date <= %s::date
    ORDER BY asset_id, trade_date
    """
    with connect(service) as connection:
        rows = fetch_all(
            connection,
            sql,
            [
                adjust_type,
                selected,
                anchor_date.isoformat(),
                evaluation_cutoff.isoformat(),
            ],
        )
    return pd.DataFrame(rows, columns=columns)


def _preflight_payload(
    preflight: PreflightResult,
    *,
    gaps: Iterable[DataGap] | None = None,
    blocked: bool | None = None,
    status: str | None = None,
) -> dict[str, object]:
    selected_gaps = tuple(preflight.gaps if gaps is None else gaps)
    return {
        "blocked": preflight.blocked if blocked is None else bool(blocked),
        "status": preflight.status if status is None else str(status),
        "data_cutoff_date": preflight.data_cutoff_date.isoformat(),
        "checked_datasets": list(preflight.checked_datasets),
        "coverage_rows": list(preflight.coverage_rows),
        "gaps": [asdict(gap) for gap in selected_gaps],
        "backfill_request_path": None,
    }


def _gaps_frame(gaps: Iterable[DataGap]) -> pd.DataFrame:
    return pd.DataFrame([asdict(gap) for gap in gaps], columns=_BACKFILL_COLUMNS)


def _blocked_result(
    *,
    anchor_date: date,
    cutoff: date,
    config: RollingOversoldConfig,
    output_dir: str | Path,
    preflight: PreflightResult,
    gaps: Iterable[DataGap],
    runtime: StrategyRuntimeBudget,
    blocked_reason: str,
    status: str,
) -> dict[str, object]:
    gap_tuple = tuple(gaps)
    destination = _blocked_artifact_dir(
        output_dir,
        anchor_date=anchor_date,
        score_version=config.score_version,
    )
    payload = _preflight_payload(
        preflight,
        gaps=gap_tuple,
        blocked=True,
        status=status,
    )
    payload["anchor_date"] = anchor_date.isoformat()
    payload["score_version"] = config.score_version
    artifacts = _persist_blocked_artifacts(
        destination,
        payload=payload,
        gaps=gap_tuple,
        anchor_date=anchor_date,
        score_version=config.score_version,
        status=status,
    )
    metadata = runtime.metadata()
    paths = {
        "snapshot_manifest": None,
        "market_regime": None,
        "sector_states": None,
        "stock_candidates": None,
        "evaluation": None,
        "evaluation_summary": None,
        **artifacts,
    }
    return {
        "blocked": True,
        "blocked_reason": blocked_reason,
        "status": status,
        "anchor_date": anchor_date.isoformat(),
        "data_cutoff_date": cutoff.isoformat(),
        "snapshot_id": None,
        "snapshot": None,
        "paths": paths,
        "stock_candidate_count": 0,
        "runtime_seconds": metadata["runtime_seconds"],
        "runtime_metadata": metadata,
        "future_rows_used_for_scoring": 0,
    }


def _persist_blocked_artifacts(
    destination: Path,
    *,
    payload: dict[str, object],
    gaps: tuple[DataGap, ...],
    anchor_date: date,
    score_version: str,
    status: str,
) -> dict[str, str | None]:
    destination.mkdir(parents=True, exist_ok=True)
    preflight_path = destination / "preflight.json"
    backfill_path = destination / "backfill_requests.csv"
    preflight_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    _gaps_frame(gaps).to_csv(backfill_path, index=False, lineterminator="\n")
    policy_path = write_backfill_request(
        destination,
        strategy="rolling_sector_oversold",
        trade_date=anchor_date.isoformat(),
        ranking_version=score_version,
        gaps=gaps,
        status=status,
    )
    return {
        "preflight": str(preflight_path),
        "backfill_requests": str(backfill_path),
        "backfill_policy": str(policy_path),
    }


def _snapshot_runtime_metadata(runtime: StrategyRuntimeBudget) -> dict[str, object]:
    metadata = runtime.metadata()
    timings = dict(metadata["stage_timings_seconds"])
    for stage in _STAGE_NAMES:
        timings.setdefault(stage, 0.0)
    metadata["stage_timings_seconds"] = timings
    return metadata


def _snapshot_paths(
    snapshot_dir: Path,
    *,
    manifest_path: Path,
    evaluation_path: Path,
    evaluation_summary_path: Path,
) -> dict[str, str | None]:
    return {
        "snapshot_manifest": str(manifest_path),
        "market_regime": str(snapshot_dir / "market_regime.csv"),
        "sector_states": str(snapshot_dir / "sector_states.csv"),
        "stock_candidates": str(snapshot_dir / "stock_candidates.csv"),
        "evaluation": str(evaluation_path),
        "evaluation_summary": str(evaluation_summary_path),
        "evaluation_manifest": None,
        "preflight": str(snapshot_dir / "preflight.json"),
        "backfill_requests": str(snapshot_dir / "backfill_requests.csv"),
        "backfill_policy": None,
    }


def _anchor_output_dir(output_dir: str | Path, *, anchor_date: date, score_version: str) -> Path:
    return (
        Path(output_dir).expanduser().resolve()
        / "rolling_sector_oversold"
        / f"anchor={anchor_date.isoformat()}"
        / f"version={score_version}"
    )


def _load_existing_snapshot(
    *, output_dir: str | Path, anchor_date: date, score_version: str
) -> dict[str, object] | None:
    destination = _anchor_output_dir(
        output_dir,
        anchor_date=anchor_date,
        score_version=score_version,
    )
    return load_rolling_oversold_snapshot(destination) if (destination / "manifest.json").is_file() else None


def _load_previous_snapshot(
    *, output_dir: str | Path, before_anchor: date, score_version: str
) -> dict[str, object] | None:
    """Return the nearest successful same-version snapshot before an anchor."""

    root = Path(output_dir).expanduser().resolve() / "rolling_sector_oversold"
    if not root.is_dir():
        return None
    matches: list[tuple[date, Path]] = []
    for candidate in root.glob("anchor=*"):
        if not candidate.is_dir():
            continue
        try:
            candidate_date = date.fromisoformat(candidate.name.removeprefix("anchor="))
        except ValueError:
            continue
        snapshot_dir = candidate / f"version={score_version}"
        if candidate_date < before_anchor and (snapshot_dir / "manifest.json").is_file():
            matches.append((candidate_date, snapshot_dir))
    if not matches:
        return None
    _, snapshot_dir = max(matches, key=lambda item: item[0])
    return load_rolling_oversold_snapshot(snapshot_dir)


def resolve_rolling_history_start(
    *, output_dir: str | Path, score_version: str, fallback: date
) -> date:
    """Resolve the earliest persisted anchor used for lineage-gap checks."""

    persisted = _earliest_persisted_anchor(output_dir=output_dir, score_version=score_version)
    return min(fallback, persisted) if persisted is not None else fallback


def _earliest_persisted_anchor(
    *, output_dir: str | Path, score_version: str
) -> date | None:
    root = Path(output_dir).expanduser().resolve() / "rolling_sector_oversold"
    candidates: list[date] = []
    for anchor_dir in root.glob("anchor=*") if root.is_dir() else ():
        candidate = _parse_anchor_dir(anchor_dir)
        if candidate is None:
            continue
        if (anchor_dir / f"version={score_version}" / "manifest.json").is_file():
            candidates.append(candidate)
    blocked_root = root / "blocked"
    for anchor_dir in blocked_root.glob("anchor=*") if blocked_root.is_dir() else ():
        candidate = _parse_anchor_dir(anchor_dir)
        if candidate is None:
            continue
        if (anchor_dir / f"version={score_version}" / "preflight.json").is_file():
            candidates.append(candidate)
    return min(candidates) if candidates else None


def _parse_anchor_dir(path: Path) -> date | None:
    if not path.is_dir() or not path.name.startswith("anchor="):
        return None
    try:
        return date.fromisoformat(path.name.removeprefix("anchor="))
    except ValueError:
        return None


def _snapshot_anchor_date(snapshot: dict[str, object] | None) -> date | None:
    if snapshot is None:
        return None
    value = snapshot.get("anchor_date")
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _as_date(value, "previous snapshot anchor_date")


def _unresolved_blocked_anchor(
    *,
    output_dir: str | Path,
    after_anchor: date | None,
    window_start: date | None,
    before_anchor: date,
    score_version: str,
) -> date | None:
    """Find a persisted block that would make a later daily lineage stale."""

    if after_anchor is None and window_start is None:
        return None
    blocked_root = Path(output_dir).expanduser().resolve() / "rolling_sector_oversold" / "blocked"
    if not blocked_root.is_dir():
        return None
    candidates: list[date] = []
    for candidate in blocked_root.glob("anchor=*"):
        try:
            candidate_date = date.fromisoformat(candidate.name.removeprefix("anchor="))
        except ValueError:
            continue
        if after_anchor is None:
            assert window_start is not None
            in_window = window_start <= candidate_date < before_anchor
        else:
            in_window = after_anchor < candidate_date < before_anchor
        if not in_window:
            continue
        blocked_dir = candidate / f"version={score_version}"
        successful_dir = _anchor_output_dir(
            output_dir,
            anchor_date=candidate_date,
            score_version=score_version,
        )
        if (blocked_dir / "preflight.json").is_file() and not (successful_dir / "manifest.json").is_file():
            candidates.append(candidate_date)
    return min(candidates) if candidates else None


def _assert_existing_snapshot_lineage(
    existing: dict[str, object], previous_snapshot: dict[str, object] | None
) -> None:
    expected = None
    if previous_snapshot is not None:
        candidate = previous_snapshot.get("snapshot_id")
        if not isinstance(candidate, str) or not candidate.strip():
            raise ValueError("previous_snapshot must include a non-empty snapshot_id")
        expected = candidate.strip()
    actual = existing.get("previous_snapshot_id")
    actual_id = actual.strip() if isinstance(actual, str) and actual.strip() else None
    if actual_id != expected:
        raise ValueError(
            "existing rolling snapshot predecessor does not match the requested lineage"
        )


def _assert_existing_snapshot_adjust_type(
    existing: dict[str, object], adjust_type: str
) -> None:
    candidates = existing.get("stock_candidates")
    if not isinstance(candidates, pd.DataFrame) or "adjusted_close_source" not in candidates:
        return
    sources = {
        str(value).strip()
        for value in candidates["adjusted_close_source"].dropna()
        if str(value).strip()
    }
    if sources and sources != {adjust_type}:
        found = ", ".join(sorted(sources))
        raise ValueError(
            "existing rolling snapshot adjusted close source does not match "
            f"requested adjust_type {adjust_type}: {found}"
        )


def _existing_snapshot_result(
    snapshot: dict[str, object],
    *,
    output_dir: str | Path,
    config: RollingOversoldConfig,
    service: str,
    runtime: StrategyRuntimeBudget,
) -> dict[str, object]:
    anchor = _as_date(snapshot.get("anchor_date"), "existing snapshot anchor_date")
    score_version = str(snapshot.get("score_version") or "").strip()
    if not score_version:
        raise ValueError("existing snapshot score_version must be non-empty")
    snapshot_dir = _anchor_output_dir(
        output_dir,
        anchor_date=anchor,
        score_version=score_version,
    )
    manifest_path = snapshot_dir / "manifest.json"
    latest_directory = latest_rolling_evaluation_directory(snapshot_dir)
    evaluation_cutoff = config.anchor_end_date or anchor
    latest_cutoff = _evaluation_cutoff_from_directory(latest_directory)
    needs_refresh = bool(_snapshot_asset_ids(snapshot)) and (
        latest_directory is None
        or latest_cutoff is None
        or latest_cutoff < evaluation_cutoff
        or _evaluation_has_pending_rows(latest_directory)
    )
    revision_result: dict[str, object] | None = None
    if needs_refresh:
        runtime.begin_stage("evaluation")
        try:
            evaluation_bars = _load_evaluation_bars(
                asset_ids=_snapshot_asset_ids(snapshot),
                anchor_date=anchor,
                evaluation_cutoff=evaluation_cutoff,
                adjust_type=config.adjust_type,
                service=service,
            )
            detail = evaluate_snapshot(
                snapshot,
                bars=_evaluation_bars(evaluation_bars, config.adjust_type),
                evaluation_cutoff=evaluation_cutoff,
                horizons=config.forecast_horizons,
            )
            summary = summarize_rolling_evaluation(detail)
        finally:
            runtime.end_stage("evaluation")

        publication_metadata: dict[str, object] | None = None
        publication_stage_closed = False
        publication_metadata_started = False

        def publish_revision_metadata() -> dict[str, object]:
            nonlocal publication_metadata, publication_stage_closed, publication_metadata_started
            runtime.checkpoint("publication")
            if not publication_stage_closed and not publication_metadata_started:
                publication_metadata_started = True
                return runtime.metadata()
            if not publication_stage_closed:
                runtime.end_stage("publication")
                publication_stage_closed = True
                runtime.checkpoint("publication")
            publication_metadata = runtime.metadata()
            return publication_metadata

        def publish_revision_guard() -> None:
            runtime.checkpoint("publication")

        runtime.begin_stage("publication")
        try:
            revision_result = _persist_evaluation_revision(
                snapshot=snapshot,
                snapshot_dir=snapshot_dir,
                detail=detail,
                summary=summary,
                evaluation_cutoff=evaluation_cutoff,
                runtime_metadata_supplier=publish_revision_metadata,
                runtime_publish_guard=publish_revision_guard,
            )
        finally:
            if not publication_stage_closed:
                try:
                    runtime.end_stage("publication")
                except ValueError:
                    pass

    if revision_result is not None:
        detail_path = Path(str(revision_result["evaluation"]))
        summary_path = Path(str(revision_result["evaluation_summary"]))
        evaluation_manifest_path = Path(str(revision_result["evaluation_manifest"]))
        runtime_metadata = revision_result.get("runtime_metadata", runtime.metadata())
        evaluation_revision = revision_result.get("revision")
    elif latest_directory is not None:
        detail_path = latest_directory / "evaluation_detail.csv"
        summary_path = latest_directory / "evaluation_summary.csv"
        evaluation_manifest_path = latest_directory / "evaluation_manifest.json"
        manifest = snapshot.get("manifest", {})
        persisted_metadata = manifest.get("runtime_metadata", {}) if isinstance(manifest, dict) else {}
        runtime_metadata = _evaluation_runtime_metadata_from_directory(latest_directory)
        if runtime_metadata is None:
            runtime_metadata = persisted_metadata if isinstance(persisted_metadata, dict) else {}
        evaluation_revision = _path_revision(latest_directory)
    else:
        detail_path = snapshot_dir / "evaluation_detail.csv"
        summary_path = snapshot_dir / "evaluation_summary.csv"
        evaluation_manifest_path = snapshot_dir / "evaluation_manifest.json"
        runtime_metadata = {}
        evaluation_revision = None

    manifest = snapshot.get("manifest", {})
    if not isinstance(runtime_metadata, dict):
        runtime_metadata = {}
    runtime_metadata = dict(runtime_metadata)
    runtime_metadata["snapshot_runtime_metadata"] = (
        manifest.get("runtime_metadata", {}) if isinstance(manifest, dict) else {}
    )
    candidates = snapshot.get("stock_candidates")
    count = int(len(candidates)) if isinstance(candidates, pd.DataFrame) else 0
    paths = _snapshot_paths(
        snapshot_dir,
        manifest_path=manifest_path,
        evaluation_path=detail_path,
        evaluation_summary_path=summary_path,
    )
    paths["evaluation_manifest"] = str(evaluation_manifest_path) if evaluation_manifest_path.is_file() else None
    result = {
        "blocked": False,
        "blocked_reason": "",
        "anchor_date": anchor.isoformat(),
        "data_cutoff_date": str(snapshot.get("data_cutoff_date") or ""),
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot": snapshot,
        "paths": paths,
        "stock_candidate_count": count,
        "runtime_seconds": runtime_metadata.get("runtime_seconds", 0.0),
        "runtime_metadata": runtime_metadata,
        "future_rows_used_for_scoring": 0,
    }
    if evaluation_revision is not None:
        result["evaluation_revision"] = evaluation_revision
    return result


def _path_revision(directory: Path) -> int | None:
    prefix = "evaluation_revision="
    if not directory.name.startswith(prefix):
        return None
    value = directory.name.removeprefix(prefix)
    return int(value) if value.isdigit() else None


def _blocked_artifact_dir(
    output_dir: str | Path, *, anchor_date: date, score_version: str
) -> Path:
    return (
        Path(output_dir).expanduser().resolve()
        / "rolling_sector_oversold"
        / "blocked"
        / f"anchor={anchor_date.isoformat()}"
        / f"version={score_version}"
    )


def _sector_rows_have_status(rows: object) -> bool:
    if rows is None:
        return True
    if isinstance(rows, pd.DataFrame):
        return "sector_gate_status" in rows and rows["sector_gate_status"].astype("string").str.strip().ne("").all()
    if isinstance(rows, list):
        return all(
            isinstance(row, dict) and bool(str(row.get("sector_gate_status", "")).strip())
            for row in rows
        )
    return False


def _as_date(value: object, label: str) -> date:
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"{label} must be a date")
    return parsed.date()
