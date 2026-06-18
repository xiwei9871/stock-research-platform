from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.data_run_manifest import build_manifest_entry, upsert_data_run_manifest
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
TECH_BOTTLENECK_EOD_TRANSACTION_COST_BPS = 20.0
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
        adjust_type=TECH_BOTTLENECK_EOD_ADJUST_TYPE,
    )

    paths = {
        "snapshot_path": snapshot_path,
        "review_path": output / TECH_BOTTLENECK_EOD_REVIEW_FILENAME,
        "equity_path": output / TECH_BOTTLENECK_EOD_EQUITY_FILENAME,
        "positions_path": output / TECH_BOTTLENECK_EOD_POSITIONS_FILENAME,
        "trades_path": output / TECH_BOTTLENECK_EOD_TRADES_FILENAME,
    }
    equity = pd.DataFrame(strategy["equity_curve"])
    positions = pd.DataFrame(strategy["positions"])
    trades = pd.DataFrame(strategy["trades"])
    review = _review_rows_from_snapshots(
        snapshots=snapshots,
        trade_date=end_date,
        strategy_run_id=run_id,
    )
    review.to_csv(paths["review_path"], index=False)
    equity.to_csv(paths["equity_path"], index=False)
    positions.to_csv(paths["positions_path"], index=False)
    trades.to_csv(paths["trades_path"], index=False)

    ended_at = datetime.now(timezone.utc)
    latest_snapshot_date = _latest_trade_date(snapshots, fallback=end_date)
    output_paths = {key: str(path) for key, path in paths.items()}
    candidate_source = str(candidate_source_path) if candidate_source_path is not None else TECH_BOTTLENECK_CANDIDATE_SOURCE
    summary = _json_ready(strategy["summary"])

    candidate_metadata = {
        "candidate_snapshot_latest_date": latest_snapshot_date,
        "candidate_source": candidate_source,
        "candidate_snapshot_row_count": int(len(snapshots)),
        "output_paths": output_paths,
    }
    strategy_metadata = {
        "candidate_snapshot_latest_date": latest_snapshot_date,
        "candidate_source": candidate_source,
        "candidate_snapshot_row_count": int(len(snapshots)),
        "output_paths": output_paths,
        "summary": summary,
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
        ended_at=ended_at,
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
        ended_at=ended_at,
        row_count=int(len(review)),
        asset_count=_asset_count(review),
        latest_trade_date=latest_snapshot_date,
        artifact_path=paths["review_path"],
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
        "manifest_entries": [candidate_entry, strategy_entry],
    }


def run_tech_bottleneck_eod(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    base_candidates_path: str | Path,
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
        candidate_source_path=base_candidates_path,
    )


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
