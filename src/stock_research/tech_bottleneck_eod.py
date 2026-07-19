from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.data_run_manifest import build_manifest_entry, upsert_data_run_manifest
from stock_research.strategy_contracts import OFFICIAL_MAX_POSITION_WEIGHT, OFFICIAL_TRANSACTION_COST_BPS
from stock_research.strategy_publication_artifacts import write_strategy_publication_artifacts
from stock_research.tech_bottleneck_candidates import (
    TECH_BOTTLENECK_CANDIDATE_SOURCE,
    build_point_in_time_candidate_snapshots,
    read_base_candidate_source,
    write_candidate_snapshots,
)
from stock_research.tech_bottleneck_v1 import (
    TECH_BOTTLENECK_V1_ENGINE_VERSION,
    TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH,
    _extend_market_exposure,
    _load_prices,
    build_tech_bottleneck_v1_from_rank_snapshots,
)


TECH_BOTTLENECK_EOD_REBALANCE_FREQUENCY = "biweekly"
TECH_BOTTLENECK_EOD_TOP_N = 5
TECH_BOTTLENECK_EOD_TRANSACTION_COST_BPS = OFFICIAL_TRANSACTION_COST_BPS
TECH_BOTTLENECK_EOD_MAX_POSITION_WEIGHT = OFFICIAL_MAX_POSITION_WEIGHT
TECH_BOTTLENECK_EOD_ADJUST_TYPE = "hfq"
TECH_BOTTLENECK_EOD_SNAPSHOT_FILENAME = "tech_bottleneck_daily_candidates.csv"
TECH_BOTTLENECK_EOD_REVIEW_FILENAME = "strategy_tech_bottleneck_review.csv"
TECH_BOTTLENECK_EOD_EQUITY_FILENAME = "strategy_tech_bottleneck_equity.csv"
TECH_BOTTLENECK_EOD_POSITIONS_FILENAME = "strategy_tech_bottleneck_positions.csv"
TECH_BOTTLENECK_EOD_TRADES_FILENAME = "strategy_tech_bottleneck_trades.csv"


def run_tech_bottleneck_eod_from_frames(
    *,
    base_candidates: pd.DataFrame,
    prices: pd.DataFrame,
    market_exposure: pd.DataFrame,
    start_date: str,
    end_date: str,
    run_id: str,
    output_dir: str | Path,
    manifest_upsert: Callable[[dict[str, Any]], Any] = upsert_data_run_manifest,
    candidate_source_path: str | Path | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=base_candidates,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        run_id=run_id,
    )
    snapshot_path = write_candidate_snapshots(snapshots, output / TECH_BOTTLENECK_EOD_SNAPSHOT_FILENAME)
    strategy = build_tech_bottleneck_v1_from_rank_snapshots(
        candidate_snapshots=snapshots,
        prices=prices,
        market_exposure=market_exposure,
        start_date=start_date,
        end_date=end_date,
        top_n=TECH_BOTTLENECK_EOD_TOP_N,
        rebalance_frequency=TECH_BOTTLENECK_EOD_REBALANCE_FREQUENCY,
        transaction_cost_bps=TECH_BOTTLENECK_EOD_TRANSACTION_COST_BPS,
        max_position_weight=TECH_BOTTLENECK_EOD_MAX_POSITION_WEIGHT,
        adjust_type=TECH_BOTTLENECK_EOD_ADJUST_TYPE,
    )

    equity = _anchor_equity_curve_to_initial_equity(
        pd.DataFrame(strategy["equity_curve"]),
        start_date=start_date,
    )
    positions = pd.DataFrame(strategy["positions"])
    trades = pd.DataFrame(strategy["trades"])
    review = _review_rows_from_snapshots(
        snapshots=snapshots,
        trade_date=end_date,
        strategy_run_id=run_id,
    )

    candidate_ended_at = datetime.now(timezone.utc)
    latest_snapshot_date = _latest_trade_date(snapshots, fallback=end_date)
    candidate_source = str(candidate_source_path) if candidate_source_path is not None else TECH_BOTTLENECK_CANDIDATE_SOURCE
    summary = _json_ready(strategy["summary"])
    summary.setdefault("transaction_cost_bps", TECH_BOTTLENECK_EOD_TRANSACTION_COST_BPS)
    summary.setdefault("max_position_weight", TECH_BOTTLENECK_EOD_MAX_POSITION_WEIGHT)
    config = {
        "start_date": start_date,
        "end_date": end_date,
        "top_n": TECH_BOTTLENECK_EOD_TOP_N,
        "rebalance_frequency": TECH_BOTTLENECK_EOD_REBALANCE_FREQUENCY,
        "transaction_cost_bps": TECH_BOTTLENECK_EOD_TRANSACTION_COST_BPS,
        "max_position_weight": TECH_BOTTLENECK_EOD_MAX_POSITION_WEIGHT,
        "adjust_type": TECH_BOTTLENECK_EOD_ADJUST_TYPE,
        "engine_version": TECH_BOTTLENECK_V1_ENGINE_VERSION,
        "universe": summary.get("universe"),
        "protection_name": summary.get("protection_name"),
    }
    official_result = {
        "strategy_id": "tech_bottleneck",
        "strategy_name": "Tech Bottleneck Discovery",
        "source_kind": TECH_BOTTLENECK_V1_ENGINE_VERSION,
        "config": config,
        "summary": summary,
        "equity_curve": equity.to_dict("records"),
        "positions": positions.to_dict("records"),
        "trades": trades.to_dict("records"),
        "review": review.to_dict("records"),
    }
    from stock_research.dashboard.backtests import (
        attach_publication_identity,
        validate_official_strategy_result,
    )

    official_result = attach_publication_identity(official_result, profile="balanced")
    validate_official_strategy_result(official_result, profile="balanced")
    publication = write_strategy_publication_artifacts(
        output_dir=output,
        strategy_id="tech_bottleneck",
        run_id=run_id,
        started_at=started_at,
        publication_identity=official_result["publication_identity"],
        frames={
            "equity": equity,
            "positions": positions,
            "trades": trades,
            "review": review,
        },
        summary=official_result["summary"],
        config=config,
        compatibility_destinations={
            "equity": output / TECH_BOTTLENECK_EOD_EQUITY_FILENAME,
            "positions": output / TECH_BOTTLENECK_EOD_POSITIONS_FILENAME,
            "trades": output / TECH_BOTTLENECK_EOD_TRADES_FILENAME,
            "review": output / TECH_BOTTLENECK_EOD_REVIEW_FILENAME,
        },
    )
    strategy_ended_at = datetime.now(timezone.utc)
    official_output_paths = {
        key: str(path) for key, path in publication["output_paths"].items()
    }
    output_paths = {"snapshot_path": str(snapshot_path), **official_output_paths}

    candidate_metadata = {
        "candidate_snapshot_latest_date": latest_snapshot_date,
        "candidate_source": candidate_source,
        "candidate_snapshot_row_count": int(len(snapshots)),
        "output_paths": {"snapshot_path": str(snapshot_path)},
    }
    strategy_metadata = {
        "candidate_snapshot_latest_date": latest_snapshot_date,
        "candidate_source": candidate_source,
        "candidate_snapshot_row_count": int(len(snapshots)),
        "output_paths": official_output_paths,
        "summary": publication["summary"],
        "config": publication["config"],
        "publication_identity": publication["publication_identity"],
        "identity_schema_version": publication["publication_identity"].get("identity_schema_version"),
        "artifact_version": publication["artifact_version"],
        "publish_id": publication["publish_id"],
        "publication_manifest_path": str(publication["publication_manifest_path"]),
        "file_hashes": publication["file_hashes"],
    }

    candidate_entry = build_manifest_entry(
        run_id=run_id,
        run_date=date.today().isoformat(),
        trade_date=end_date,
        module="tech_bottleneck_candidates",
        source=TECH_BOTTLENECK_CANDIDATE_SOURCE,
        tier="tier1",
        status="success",
        started_at=started_at,
        ended_at=candidate_ended_at,
        row_count=int(len(snapshots)),
        asset_count=_asset_count(snapshots),
        latest_trade_date=latest_snapshot_date,
        artifact_path=snapshot_path,
        code_version=TECH_BOTTLENECK_V1_ENGINE_VERSION,
        config_version=TECH_BOTTLENECK_V1_ENGINE_VERSION,
        metadata=candidate_metadata,
    )
    strategy_entry = build_manifest_entry(
        run_id=run_id,
        run_date=date.today().isoformat(),
        trade_date=end_date,
        module="strategy_tech_bottleneck",
        source="strategy_daily_eod",
        tier="tier1",
        status="success",
        started_at=started_at,
        ended_at=strategy_ended_at,
        row_count=int(len(review)),
        asset_count=_asset_count(review),
        latest_trade_date=latest_snapshot_date,
        artifact_path=publication["output_paths"]["review_path"],
        code_version=TECH_BOTTLENECK_V1_ENGINE_VERSION,
        config_version=TECH_BOTTLENECK_V1_ENGINE_VERSION,
        metadata=strategy_metadata,
    )
    manifest_upsert(candidate_entry)
    manifest_upsert(strategy_entry)

    return {
        "candidate_rows": int(len(snapshots)),
        "review_rows": int(len(review)),
        **output_paths,
        "publication_identity": publication["publication_identity"],
        "artifact_version": publication["artifact_version"],
        "publish_id": publication["publish_id"],
        "publication_manifest_path": str(publication["publication_manifest_path"]),
        "file_hashes": publication["file_hashes"],
        "manifest_entries": [candidate_entry, strategy_entry],
    }


def run_tech_bottleneck_eod(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    base_candidates_path: str | Path,
    manifest_upsert: Callable[[dict[str, Any]], Any] = upsert_data_run_manifest,
) -> dict[str, Any]:
    base_candidates = read_base_candidate_source(base_candidates_path, end_date=end_date)
    market_exposure = pd.read_csv(TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH, low_memory=False)
    market_exposure = _extend_market_exposure(market_exposure, end_date=end_date)
    asset_ids = sorted(base_candidates["asset_id"].dropna().astype(str).unique().tolist())
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type=TECH_BOTTLENECK_EOD_ADJUST_TYPE,
        asset_ids=asset_ids,
        service=SETTINGS.research_service,
    )
    run_id = f"strategy-eod-{end_date}-local"
    return run_tech_bottleneck_eod_from_frames(
        base_candidates=base_candidates,
        prices=prices,
        market_exposure=market_exposure,
        start_date=start_date,
        end_date=end_date,
        run_id=run_id,
        output_dir=output_dir,
        manifest_upsert=manifest_upsert,
        candidate_source_path=base_candidates_path,
    )


def _anchor_equity_curve_to_initial_equity(equity: pd.DataFrame, *, start_date: str) -> pd.DataFrame:
    if equity.empty or "trade_date" not in equity.columns or "equity" not in equity.columns:
        return equity
    frame = equity.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame.dropna(subset=["trade_date"]).sort_values("trade_date", kind="stable").reset_index(drop=True)
    if frame.empty:
        return equity
    first_equity = pd.to_numeric(pd.Series([frame.iloc[0].get("equity")]), errors="coerce").iloc[0]
    if pd.notna(first_equity) and abs(float(first_equity) - 1.0) < 1e-12:
        return frame

    anchor = frame.iloc[0].copy()
    anchor["trade_date"] = str(start_date)
    anchor["equity"] = 1.0
    if "drawdown" in frame.columns:
        anchor["drawdown"] = 0.0
    for column in ["gross_return", "net_return", "turnover", "transaction_cost", "actual_exposure", "holdings_count"]:
        if column in frame.columns:
            anchor[column] = 0.0
    if str(frame.iloc[0]["trade_date"]) == str(start_date):
        frame.iloc[0] = anchor
        return frame
    return pd.concat([pd.DataFrame([anchor]), frame], ignore_index=True).reindex(columns=equity.columns)


def _review_rows_from_snapshots(
    snapshots: pd.DataFrame,
    *,
    trade_date: str,
    strategy_run_id: str,
) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "rank",
        "bottleneck_score",
        "score_total",
        "score_source",
        "score_explanation",
        "strategy_id",
        "strategy_name",
        "strategy_run_id",
        "source_type",
        "source_name",
        "source_rank",
        "review_tier",
    ]
    if snapshots.empty:
        return pd.DataFrame(columns=columns)

    frame = snapshots[snapshots["trade_date"].astype(str) == str(trade_date)].copy()
    if frame.empty:
        raise ValueError(f"Tech Bottleneck review snapshot missing for trade_date {trade_date}")
    frame = frame[pd.to_numeric(frame["bottleneck_rank"], errors="coerce") <= TECH_BOTTLENECK_EOD_TOP_N].copy()
    frame["rank"] = pd.to_numeric(frame["bottleneck_rank"], errors="coerce").fillna(999).astype(int)
    frame["score_total"] = pd.to_numeric(frame["bottleneck_score"], errors="coerce").fillna(0.0) * 100.0
    frame["score_source"] = "bottleneck_score"
    frame["score_explanation"] = "Tech Bottleneck point-in-time candidate snapshot score shown on a 0-100 scale"
    frame["strategy_id"] = "tech_bottleneck"
    frame["strategy_name"] = "Tech Bottleneck Discovery"
    frame["strategy_run_id"] = strategy_run_id
    frame["source_type"] = "strategy_manifest"
    frame["source_name"] = "strategy_tech_bottleneck"
    frame["source_rank"] = frame["rank"]
    frame["review_tier"] = frame["rank"].map(lambda value: "top5_focus" if int(value) <= 5 else "top10_watch")
    return frame.sort_values(["rank", "asset_id"])[columns].reset_index(drop=True)


def _asset_count(frame: pd.DataFrame) -> int:
    if frame.empty or "asset_id" not in frame.columns:
        return 0
    return int(frame["asset_id"].dropna().astype(str).nunique())


def _latest_trade_date(frame: pd.DataFrame, *, fallback: str) -> str:
    if frame.empty or "trade_date" not in frame.columns:
        return str(fallback)
    latest = frame["trade_date"].dropna().astype(str).max()
    return str(latest) if latest else str(fallback)


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        return None if not np.isfinite(number) else number
    if isinstance(value, float):
        return None if not np.isfinite(value) else value
    return value
