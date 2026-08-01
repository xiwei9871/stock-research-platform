"""Database-only orchestration for rolling sector-oversold snapshots.

The module deliberately coordinates supplied, point-in-time database frames.
It never falls back to a market-data provider or an ingestion entry point.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
import hashlib
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

from .contracts import GateStatus, RollingOversoldConfig, StockLifecycle
from .loaders import RollingInputs, load_rolling_inputs
from .market_regime import compute_market_regime_features
from .outcomes import evaluate_snapshot, summarize_rolling_evaluation
from .preflight import PreflightResult, run_rolling_preflight
from .reporting import (
    latest_rolling_evaluation_directory,
    load_rolling_oversold_snapshot,
)
from .sector_scoring import score_sector_states
from .snapshots import build_rolling_snapshot, write_rolling_snapshot
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
    # A stock may belong to an industry and a concept.  Keep every sector row
    # in the snapshot, but score an asset once against its strongest permitted
    # sector so the immutable stock artifact retains its unique-asset contract.
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
    )


def _build_stock_features(
    inputs: RollingInputs | Any,
    *,
    anchor_date: date,
    config: RollingOversoldConfig,
) -> pd.DataFrame:
    """Derive score inputs only from frozen rolling loader frames."""

    memberships = _stock_memberships(inputs, anchor_date=anchor_date)
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
    rows: list[dict[str, object]] = []
    for membership in memberships.to_dict(orient="records"):
        asset_id = str(membership["asset_id"])
        if _is_ineligible_status(status.get(asset_id)):
            continue
        asset_bars = prepared_bars.loc[prepared_bars["asset_id"].eq(asset_id)]
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
        pe_ttm = _finite_row_value(valuation_row, "pe_ttm")
        if roe is None:
            _raise_stock_gap(asset_id, anchor_date, "finance_history", "missing_roe")
        if total_share is None or total_share <= 0:
            _raise_stock_gap(asset_id, anchor_date, "finance_history", "missing_total_share")
        if pe_ttm is None:
            _raise_stock_gap(asset_id, anchor_date, "valuation_history", "missing_pe_ttm")
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
                "valuation": max(0.0, min(100.0, 100.0 - pe_ttm)),
                "size_elasticity": latest_close * total_share,
                "anchor_close": latest_close,
                "adjusted_close_source": config.adjust_type,
            }
        )
    return pd.DataFrame(rows)


def _stock_memberships(inputs: RollingInputs | Any, *, anchor_date: date) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for family, source, system, code, name in (
        ("industry", getattr(inputs, "industry_membership", pd.DataFrame()), "industry_system", "industry_code", "industry_name"),
        ("concept", getattr(inputs, "concept_membership", pd.DataFrame()), "concept_system", "concept_code", "concept_name"),
    ):
        if not isinstance(source, pd.DataFrame) or source.empty or "asset_id" not in source:
            continue
        frame = source.copy(deep=True)
        if "start_date" in frame:
            starts = pd.to_datetime(frame["start_date"], errors="coerce")
            frame = frame.loc[starts.isna() | starts.dt.date.le(anchor_date)]
        if "end_date" in frame:
            ends = pd.to_datetime(frame["end_date"], errors="coerce")
            frame = frame.loc[ends.isna() | ends.dt.date.gt(anchor_date)]
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
    return pd.concat(frames, ignore_index=True, sort=False).sort_values(
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
    result = result.loc[result["trade_date"].notna() & result["trade_date"].dt.date.le(anchor_date)]
    return result.sort_values(["asset_id", "trade_date"], kind="mergesort").drop_duplicates(
        ["asset_id", "trade_date"], keep="last"
    )


def _latest_status(frame: object, *, anchor_date: date) -> dict[str, dict[str, object]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"asset_id", "trade_date"}.issubset(frame.columns):
        return {}
    result = frame.copy(deep=True)
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result = result.loc[result["trade_date"].notna() & result["trade_date"].dt.date.le(anchor_date)]
    result = result.sort_values(["asset_id", "trade_date"], kind="mergesort").drop_duplicates("asset_id", keep="last")
    return {str(row["asset_id"]): row for row in result.to_dict(orient="records")}


def _latest_pit_frame(frame: object, *, date_column: str, cutoff: date) -> dict[str, dict[str, object]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"asset_id", date_column}.issubset(frame.columns):
        return {}
    result = frame.copy(deep=True)
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    result[date_column] = pd.to_datetime(result[date_column], errors="coerce")
    result = result.loc[result[date_column].notna() & result[date_column].dt.date.le(cutoff)]
    result = result.sort_values(["asset_id", date_column], kind="mergesort").drop_duplicates("asset_id", keep="last")
    return {str(row["asset_id"]): row for row in result.to_dict(orient="records")}


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
    raw_anchor = pd.to_numeric(result.get("anchor_close"), errors="coerce")
    if raw_anchor is None:
        raw_anchor = pd.Series(float("nan"), index=result.index)
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
    revision = max(existing_revisions, default=0) + 1
    destination = snapshot_dir / f"evaluation_revision={revision:04d}"
    staging = Path(
        tempfile.mkdtemp(prefix=f".evaluation_revision={revision:04d}.", dir=snapshot_dir)
    )
    artifacts = _evaluation_artifact_bytes(detail, summary)
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
