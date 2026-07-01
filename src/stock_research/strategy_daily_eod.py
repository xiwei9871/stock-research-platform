from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_store import load_top_scores
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame
from stock_research.strategy_daily_eod_store import (
    apply_strategy_daily_eod_status_schema,
    build_status_payload,
    upsert_strategy_daily_eod_status,
)
from stock_research.tech_bottleneck_evidence_workflow import (
    build_tech_bottleneck_evidence_workflow,
)


DependencyChecker = Callable[..., dict[str, Any]]
StrategyRunner = Callable[..., dict[str, Any]]


DEFAULT_OUTPUT_ROOT = Path("outputs/research/strategy_daily_eod")


def run_strategy_daily_eod(
    *,
    trade_date: str,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    dependency_checker: DependencyChecker | None = None,
    lhb_runner: StrategyRunner | None = None,
    mid_runner: StrategyRunner | None = None,
    tech_runner: StrategyRunner | None = None,
    midtrend_artifact_builder: StrategyRunner | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    apply_strategy_daily_eod_status_schema(service=service)
    dependency_checker = dependency_checker or check_strategy_daily_eod_dependencies
    output_dir = Path(output_root) / trade_date
    output_dir.mkdir(parents=True, exist_ok=True)

    dependency_check = dependency_checker(trade_date=trade_date, service=service)
    if dependency_check.get("status") != "success":
        result = _finalize_failure(
            trade_date=trade_date,
            output_dir=output_dir,
            dependency_check=dependency_check,
            lhb_status="skipped",
            mid_status="skipped",
            tech_status="skipped",
            error_summary=str(dependency_check.get("reason") or "dependency check failed"),
            service=service,
        )
        return result

    lhb_runner = lhb_runner or build_lhb_shortline_strategy_eod
    mid_runner = mid_runner or build_mid_trend_strategy_eod
    tech_runner = tech_runner or build_tech_bottleneck_strategy_eod
    midtrend_artifact_builder = midtrend_artifact_builder or build_midtrend_daily_review_artifacts_eod

    lhb_result = _run_strategy(lhb_runner, trade_date=trade_date, output_dir=output_dir, service=service)
    mid_result = _run_strategy(mid_runner, trade_date=trade_date, output_dir=output_dir, service=service)
    midtrend_artifact_result = _run_strategy(
        midtrend_artifact_builder,
        trade_date=trade_date,
        output_dir=output_dir,
        service=service,
    )
    tech_result = _run_strategy(tech_runner, trade_date=trade_date, output_dir=output_dir, service=service)

    strategy_status = {
        "lhb_shortline": str(lhb_result.get("status") or "failed"),
        "mid_trend": str(mid_result.get("status") or "failed"),
        "midtrend_artifacts": str(midtrend_artifact_result.get("status") or "failed"),
        "tech_bottleneck": str(tech_result.get("status") or "failed"),
    }
    review_rows = int(
        lhb_result.get("review_rows", 0)
        + mid_result.get("review_rows", 0)
        + tech_result.get("review_rows", 0)
    )
    summary = {
        "trade_date": trade_date,
        "run_id": f"strategy-eod-{trade_date}-local",
        "output_dir": str(output_dir),
        "dependency_check": dependency_check,
        "strategy_status": strategy_status,
        "midtrend_artifacts": midtrend_artifact_result.get("paths", {}),
        "midtrend_artifact_warnings": midtrend_artifact_result.get("warnings", []),
        "review_rows": review_rows,
        "status": "success" if all(status == "success" for status in strategy_status.values()) else "failed",
        "error_summary": _join_errors(
            [
                lhb_result.get("error_summary"),
                mid_result.get("error_summary"),
                midtrend_artifact_result.get("error_summary"),
                tech_result.get("error_summary"),
            ]
        ),
    }
    summary_path = output_dir / "strategy_eod_publish_summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_review_manifest(output_dir)

    upsert_strategy_daily_eod_status(
        build_status_payload(
            trade_date=trade_date,
            status=summary["status"],
            dependency_check_status=str(dependency_check.get("status") or "failed"),
            lhb_shortline_status=strategy_status["lhb_shortline"],
            mid_trend_status=strategy_status["mid_trend"],
            tech_bottleneck_status=strategy_status["tech_bottleneck"],
            review_rows=review_rows,
            output_dir=str(output_dir),
            summary_path=str(summary_path),
            error_summary=summary["error_summary"],
        ),
        service=service,
    )
    return summary


def check_strategy_daily_eod_dependencies(
    *,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    rows = _fetch_one(
        service,
        """
        SELECT daily_status, minute5_status, deps_status
        FROM ops.daily_pipeline_status
        WHERE trade_date = %s
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        [trade_date],
    )
    if not rows:
        return {"status": "failed", "reason": "missing daily_pipeline_status"}
    row = rows[0]
    if str(row.get("daily_status") or "") not in {"success", "partial_success"}:
        return {"status": "failed", "reason": f"daily_status={row.get('daily_status')}"}
    if str(row.get("minute5_status") or "") not in {"success", "partial_success"}:
        return {"status": "failed", "reason": f"minute5_status={row.get('minute5_status')}"}
    if str(row.get("deps_status") or "") != "success":
        return {"status": "failed", "reason": f"deps_status={row.get('deps_status')}"}
    return {"status": "success"}


def _run_strategy(
    runner: StrategyRunner,
    *,
    trade_date: str,
    output_dir: Path,
    service: str,
) -> dict[str, Any]:
    try:
        return runner(trade_date=trade_date, output_dir=output_dir, service=service)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "review_rows": 0,
            "paths": {},
            "error_summary": f"{type(exc).__name__}: {exc}",
        }


def build_lhb_shortline_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    watchlist_path = Path(f"outputs/research/daily_lhb_shortline_watchlist_{trade_date.replace('-', '')}.csv")
    if watchlist_path.exists():
        source = pd.read_csv(watchlist_path, low_memory=False).head(5).copy()
        review = _normalize_lhb_review(source, trade_date=trade_date)
    else:
        top_scores = load_top_scores(trade_date=trade_date, score_version="manual_v1", top_n=5, service=service)
        review = _build_lhb_review_rows(top_scores, trade_date=trade_date)
    final_review_path = Path(output_dir) / "strategy_lhb_shortline_review.csv"
    review.to_csv(final_review_path, index=False)
    return {
        "status": "success",
        "review_rows": int(len(review)),
        "paths": {
            "review": str(final_review_path),
            "daily_watchlist": str(watchlist_path) if watchlist_path.exists() else "",
        },
    }


def build_mid_trend_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    funnel_detail_path = _default_or_existing_path(
        [
            Path(f"outputs/research/strategy_daily_eod/{trade_date}/mid_trend_watch_funnel_detail.csv"),
            Path("outputs/research/mid_trend_watch_funnel_detail.csv"),
        ]
    )
    top_scores = load_top_scores(trade_date=trade_date, score_version="manual_v1", top_n=5, service=service)
    names = _load_asset_names([str(row.get("asset_id") or "") for row in top_scores], service=service)
    review = _build_mid_trend_review_rows(top_scores, names, trade_date=trade_date)
    if funnel_detail_path.exists():
        funnel = pd.read_csv(funnel_detail_path, low_memory=False)
        if not funnel.empty:
            shadow = build_mid_trend_shadow_top10_from_frame(
                funnel,
                top_n=5,
                trade_date=trade_date,
                output_dir=None,
            )["top10"]
            review = review.iloc[:0].copy() if review.empty else review
            if not shadow.empty:
                review = _normalize_mid_trend_review(shadow, review, trade_date=trade_date)
    review_path = Path(output_dir) / "strategy_mid_trend_review.csv"
    review.to_csv(review_path, index=False)
    positions_path = Path(output_dir) / "strategy_mid_trend_positions.csv"
    trades_path = Path(output_dir) / "strategy_mid_trend_trades.csv"
    equity_path = Path(output_dir) / "strategy_mid_trend_equity.csv"
    review.assign(position_weight=1.0 / max(len(review), 1)).to_csv(positions_path, index=False)
    review.assign(trade_action="hold").to_csv(trades_path, index=False)
    review.assign(equity=1.0).to_csv(equity_path, index=False)
    return {
        "status": "success",
        "review_rows": int(len(review)),
        "paths": {
            "review": str(review_path),
            "positions": str(positions_path),
            "trades": str(trades_path),
            "equity": str(equity_path),
        },
    }


def build_midtrend_daily_review_artifacts_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    output = Path(output_dir)
    paths: dict[str, str] = {}
    warnings: list[str] = []

    v1_review = output / "strategy_mid_trend_review.csv"
    _copy_if_exists(
        v1_review,
        output / "midtrend_v1_top5_reference.csv",
        paths=paths,
        warnings=warnings,
        key="midtrend_v1_top5_reference.csv",
    )

    top10_dir = Path("outputs/research/current_mid_trend_strategy_v2_top10_candidate_20250101_20260612")
    top10_holdings = top10_dir / "current_mid_trend_strategy_v2_top10_candidate_daily_holdings.csv"
    top10_trades = top10_dir / "current_mid_trend_strategy_v2_top10_candidate_trade_changes.csv"
    _write_trade_date_slice(
        top10_holdings,
        output / "midtrend_v2_top10_candidate.csv",
        trade_date=trade_date,
        paths=paths,
        warnings=warnings,
        key="midtrend_v2_top10_candidate.csv",
    )
    _write_trade_date_slice(
        top10_trades,
        output / "midtrend_v2_top10_trade_changes.csv",
        trade_date=trade_date,
        paths=paths,
        warnings=warnings,
        key="midtrend_v2_top10_trade_changes.csv",
    )

    canonical_dir = Path("outputs/research/midtrend_pit_attribution_canonical_and_daily_review_lite_v1_20260628")
    _copy_if_exists(
        canonical_dir / "bad_buy_fundamental_attribution_pit_canonical.csv",
        output / "midtrend_canonical_pit_review_labels.csv",
        paths=paths,
        warnings=warnings,
        key="midtrend_canonical_pit_review_labels.csv",
    )
    _copy_if_exists(
        canonical_dir / "midtrend_post_exit_watch_daily_review_lite.json",
        output / "midtrend_post_exit_watch_daily_review_lite.json",
        paths=paths,
        warnings=warnings,
        key="midtrend_post_exit_watch_daily_review_lite.json",
    )
    _copy_if_exists(
        canonical_dir / "midtrend_post_exit_watch_daily_review_lite.csv",
        output / "midtrend_post_exit_watch_daily_review_lite.csv",
        paths=paths,
        warnings=warnings,
        key="midtrend_post_exit_watch_daily_review_lite.csv",
    )

    manifest = pd.DataFrame(
        [{"artifact_name": key, "path": value} for key, value in sorted(paths.items())]
    )
    manifest_path = output / "midtrend_daily_review_artifacts_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    paths["midtrend_daily_review_artifacts_manifest.csv"] = str(manifest_path)
    return {"status": "success", "review_rows": 0, "paths": paths, "warnings": warnings}


def build_tech_bottleneck_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    asset_queue_path = _default_or_existing_path(
        [
            Path(f"outputs/research/strategy_daily_eod/{trade_date}/tech_bottleneck_daily_candidates.csv"),
            Path("outputs/research/strategy_lab_tech_bottleneck/2026-06-18/tech_bottleneck_daily_candidates.csv"),
        ]
    )
    evidence_detail_path = _default_or_existing_path(
        [
            Path(f"outputs/research/strategy_daily_eod/{trade_date}/tech_bottleneck_candidate_source/strict_153_st_only_financial_state_candidates.csv"),
            Path("outputs/research/tech_bottleneck_evidence_workflow_20260619_mainbiz_final/tech_bottleneck_evidence_adjusted_candidates.csv"),
        ]
    )
    candidates = pd.read_csv(asset_queue_path, low_memory=False) if asset_queue_path.exists() else pd.DataFrame()
    evidence = pd.read_csv(evidence_detail_path, low_memory=False) if evidence_detail_path.exists() else pd.DataFrame()
    result = build_tech_bottleneck_evidence_workflow(
        asset_queue=candidates,
        evidence_detail=evidence,
        trade_date=trade_date,
        top_n=5,
        output_dir=output_dir,
    )
    review = result["adjusted_candidates"].head(5).copy()
    if review.empty:
        review = pd.DataFrame(columns=["trade_date", "asset_id", "rank", "bottleneck_score", "score_total"])
    review_path = Path(output_dir) / "strategy_tech_bottleneck_review.csv"
    if "rank" not in review.columns:
        review["rank"] = range(1, len(review) + 1)
    review["trade_date"] = trade_date
    review.to_csv(review_path, index=False)
    return {
        "status": "success",
        "review_rows": int(len(review)),
        "paths": {
            "review": str(review_path),
            "positions": result["paths"].get("adjusted_candidates", ""),
        },
    }


def _finalize_failure(
    *,
    trade_date: str,
    output_dir: Path,
    dependency_check: dict[str, Any],
    lhb_status: str,
    mid_status: str,
    tech_status: str,
    error_summary: str,
    service: str,
) -> dict[str, Any]:
    summary = {
        "trade_date": trade_date,
        "run_id": f"strategy-eod-{trade_date}-local",
        "output_dir": str(output_dir),
        "dependency_check": dependency_check,
        "strategy_status": {
            "lhb_shortline": lhb_status,
            "mid_trend": mid_status,
            "tech_bottleneck": tech_status,
        },
        "review_rows": 0,
        "status": "failed",
        "error_summary": error_summary,
    }
    summary_path = output_dir / "strategy_eod_publish_summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_strategy_daily_eod_status(
        build_status_payload(
            trade_date=trade_date,
            status="failed",
            dependency_check_status=str(dependency_check.get("status") or "failed"),
            lhb_shortline_status=lhb_status,
            mid_trend_status=mid_status,
            tech_bottleneck_status=tech_status,
            review_rows=0,
            output_dir=str(output_dir),
            summary_path=str(summary_path),
            error_summary=error_summary,
        ),
        service=service,
    )
    return summary


def _join_errors(values: list[Any]) -> str | None:
    messages = [str(value).strip() for value in values if str(value or "").strip()]
    return "; ".join(messages) if messages else None


def _fetch_one(service: str, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    with connect(service) as conn:
        return fetch_all(conn, sql, params)


def _default_or_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _copy_if_exists(
    source: Path,
    target: Path,
    *,
    paths: dict[str, str],
    warnings: list[str],
    key: str,
) -> None:
    if not source.exists():
        warnings.append(f"missing:{source}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    paths[key] = str(target)


def _write_trade_date_slice(
    source: Path,
    target: Path,
    *,
    trade_date: str,
    paths: dict[str, str],
    warnings: list[str],
    key: str,
) -> None:
    if not source.exists():
        warnings.append(f"missing:{source}")
        return
    frame = pd.read_csv(source, low_memory=False)
    if "trade_date" in frame.columns:
        frame = frame[frame["trade_date"].astype(str).eq(trade_date)].copy()
    if frame.empty:
        warnings.append(f"empty_for_trade_date:{source}:{trade_date}")
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    paths[key] = str(target)


def _load_asset_names(asset_ids: list[str], *, service: str) -> dict[str, str]:
    cleaned = [asset_id for asset_id in asset_ids if asset_id]
    if not cleaned:
        return {}
    rows = _fetch_one(
        service,
        """
        SELECT asset_id, name
        FROM core.asset_master
        WHERE asset_id = ANY(%s)
        """,
        [cleaned],
    )
    return {str(row.get("asset_id") or ""): str(row.get("name") or "") for row in rows}


def _build_mid_trend_review_rows(
    top_scores: list[dict[str, Any]],
    names_by_asset: dict[str, str],
    *,
    trade_date: str,
) -> pd.DataFrame:
    rows = []
    for idx, row in enumerate(top_scores[:5], start=1):
        asset_id = str(row.get("asset_id") or "")
        rows.append(
            {
                "trade_date": trade_date,
                "asset_id": asset_id,
                "rank": idx,
                "score_total": row.get("score_total"),
                "score_source": "mid_trend_funnel_score",
                "score_explanation": "daily EOD review from stock_score_daily",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "strategy_run_id": f"strategy-eod-{trade_date}-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_mid_trend",
                "source_rank": idx,
                "review_tier": "top5_focus",
                "stock_name": names_by_asset.get(asset_id, ""),
            }
        )
    return pd.DataFrame(rows)


def _build_lhb_review_rows(
    top_scores: list[dict[str, Any]],
    *,
    trade_date: str,
) -> pd.DataFrame:
    rows = []
    for idx, row in enumerate(top_scores[:5], start=1):
        rows.append(
            {
                "trade_date": trade_date,
                "asset_id": str(row.get("asset_id") or ""),
                "rank": idx,
                "score_total": row.get("score_total"),
                "score_source": "stock_score_daily",
                "score_explanation": "daily EOD fallback from stock_score_daily",
                "strategy_id": "lhb_shortline",
                "strategy_name": "LHB Shortline Combo",
                "strategy_run_id": f"strategy-eod-{trade_date}-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_lhb_shortline",
                "source_rank": idx,
                "review_tier": "top5_focus",
            }
        )
    return pd.DataFrame(rows)


def _normalize_lhb_review(frame: pd.DataFrame, *, trade_date: str) -> pd.DataFrame:
    result = frame.copy()
    asset_id = (
        result["asset_id"].astype(str)
        if "asset_id" in result.columns
        else result.get("ts_code", pd.Series(dtype=object)).astype(str)
    )
    review = pd.DataFrame(
        {
            "trade_date": trade_date,
            "asset_id": asset_id,
            "rank": range(1, len(result) + 1),
            "score_total": 20.0,
            "score_source": "lhb_shortline_watchlist",
            "score_explanation": "daily LHB shortline watchlist rank",
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "strategy_run_id": f"strategy-eod-{trade_date}-local",
            "source_type": "strategy_manifest",
            "source_name": "strategy_lhb_shortline",
            "source_rank": range(1, len(result) + 1),
            "review_tier": "top5_focus",
        }
    )
    return review


def _normalize_mid_trend_review(
    shadow: pd.DataFrame,
    review: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    if shadow.empty:
        return review
    source = shadow.head(5).copy()
    if review.empty:
        normalized = pd.DataFrame(
            {
                "trade_date": trade_date,
                "asset_id": source["asset_id"].astype(str).tolist(),
                "rank": range(1, len(source) + 1),
                "score_total": pd.to_numeric(source.get("mid_trend_funnel_score"), errors="coerce"),
                "score_source": "mid_trend_funnel_score",
                "score_explanation": "mid trend shadow top list",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "strategy_run_id": f"strategy-eod-{trade_date}-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_mid_trend",
                "source_rank": range(1, len(source) + 1),
                "review_tier": "top5_focus",
            }
        )
        return normalized
    normalized = review.head(len(source)).copy()
    normalized["asset_id"] = source["asset_id"].astype(str).tolist()
    normalized["rank"] = range(1, len(normalized) + 1)
    normalized["source_rank"] = normalized["rank"]
    return normalized


def _write_review_manifest(output_dir: Path) -> None:
    frames: list[pd.DataFrame] = []
    for filename in (
        "strategy_lhb_shortline_review.csv",
        "strategy_mid_trend_review.csv",
        "strategy_tech_bottleneck_review.csv",
    ):
        path = output_dir / filename
        if path.exists() and path.stat().st_size > 0:
            frames.append(pd.read_csv(path, low_memory=False))
    manifest_path = output_dir / "review_queue_strategy_manifest.csv"
    if not frames:
        pd.DataFrame().to_csv(manifest_path, index=False)
        return
    pd.concat(frames, ignore_index=True, sort=False).to_csv(manifest_path, index=False)
