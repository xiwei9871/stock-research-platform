from __future__ import annotations

import ctypes
import errno
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.atomic_json import atomic_write_json
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

STRATEGY_DEPENDENCIES = {
    "lhb_shortline": ("common", "intraday"),
    "mid_trend": ("common",),
    "midtrend_artifacts": ("common",),
    "tech_bottleneck": ("common",),
}


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
    canonical_output_dir = Path(output_root) / trade_date
    versions_dir = Path(output_root) / ".versions" / trade_date
    versions_dir.mkdir(parents=True, exist_ok=True)
    output_dir = versions_dir / f"strategy-eod-{trade_date}-{uuid.uuid4().hex}"
    output_dir.mkdir(parents=True)

    dependency_check = _normalize_dependency_check(
        dependency_checker(trade_date=trade_date, service=service)
    )

    lhb_runner = lhb_runner or build_lhb_shortline_strategy_eod
    mid_runner = mid_runner or build_mid_trend_strategy_eod
    tech_runner = tech_runner or build_tech_bottleneck_strategy_eod
    midtrend_artifact_builder = midtrend_artifact_builder or build_midtrend_daily_review_artifacts_eod

    runners = {
        "lhb_shortline": lhb_runner,
        "mid_trend": mid_runner,
        "midtrend_artifacts": midtrend_artifact_builder,
        "tech_bottleneck": tech_runner,
    }
    results: dict[str, dict[str, Any]] = {}
    for strategy_name, runner in runners.items():
        blocked_reason = strategy_blocked_reason(strategy_name, dependency_check)
        if blocked_reason:
            results[strategy_name] = {
                "status": "blocked",
                "review_rows": 0,
                "paths": {},
                "error_summary": blocked_reason,
            }
        else:
            results[strategy_name] = _run_strategy(
                runner,
                trade_date=trade_date,
                output_dir=output_dir,
                service=service,
            )

    strategy_status = {
        name: str(result.get("status") or "failed") for name, result in results.items()
    }
    strategy_errors = {
        name: str(result.get("error_summary") or result.get("reason"))
        for name, result in results.items()
        if result.get("error_summary") or result.get("reason")
    }
    review_rows = sum(
        int(result.get("review_rows", 0))
        for result in results.values()
        if result.get("status") == "success"
    )
    success_count = sum(status == "success" for status in strategy_status.values())
    aggregate_status = (
        "success"
        if success_count == len(strategy_status)
        else "partial"
        if success_count
        else "failed"
    )
    dependency_reason = _dependency_failure_reason(dependency_check)
    strategy_counts = _write_review_manifest(output_dir)
    expected_counts = {
        "lhb_shortline": 5,
        "mid_trend": 5,
        "tech_bottleneck": 5,
    }
    contract_valid = aggregate_status == "success" and strategy_counts == expected_counts
    final_status = aggregate_status if aggregate_status != "success" or contract_valid else "partial"
    if contract_valid:
        for result in results.values():
            result["paths"] = _relocate_result_paths(
                dict(result.get("paths") or {}),
                staging=output_dir,
                canonical=canonical_output_dir,
            )
    failure_output_dir = Path(output_root) / ".failures" / trade_date / output_dir.name
    persistent_output_dir = canonical_output_dir if contract_valid else failure_output_dir
    summary = {
        "trade_date": trade_date,
        "run_id": f"strategy-eod-{trade_date}-local" if contract_valid else output_dir.name,
        "output_dir": str(persistent_output_dir),
        "dependency_check": dependency_check,
        "dependency_reason": dependency_reason,
        "strategy_status": strategy_status,
        "strategy_errors": strategy_errors,
        "midtrend_artifacts": (
            results["midtrend_artifacts"].get("paths", {}) if contract_valid else {}
        ),
        "midtrend_artifact_warnings": results["midtrend_artifacts"].get("warnings", []),
        "review_rows": review_rows,
        "status": final_status,
        "publishable": contract_valid,
        "manifest_modules": [
            "strategy_lhb_shortline",
            "strategy_mid_trend",
            "strategy_tech_bottleneck",
            "review_queue_strategy_manifest",
        ],
        "score_audit": {
            "status": "success" if contract_valid else "failed",
            "strategy_counts": strategy_counts,
        },
        "error_summary": _join_errors(list(strategy_errors.values())),
    }
    staging_summary_path = output_dir / "strategy_eod_publish_summary.json"
    summary_path = persistent_output_dir / "strategy_eod_publish_summary.json"
    summary["summary_path"] = str(summary_path)

    if contract_valid:
        staging_summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _atomic_publish_directory(output_dir, canonical_output_dir)
    else:
        _persist_failure_summary(
            summary_path=summary_path,
            summary=summary,
            output_root=Path(output_root),
            trade_date=trade_date,
        )
        shutil.rmtree(output_dir, ignore_errors=True)

    upsert_strategy_daily_eod_status(
        build_status_payload(
            trade_date=trade_date,
            status=summary["status"],
            dependency_check_status=_dependency_check_status(dependency_check),
            lhb_shortline_status=strategy_status["lhb_shortline"],
            mid_trend_status=strategy_status["mid_trend"],
            tech_bottleneck_status=strategy_status["tech_bottleneck"],
            review_rows=review_rows,
            output_dir=str(summary["output_dir"]),
            summary_path=str(summary["summary_path"]),
            error_summary=summary["error_summary"],
        ),
        service=service,
    )
    return summary


def _atomic_publish_directory(staging: Path, canonical: Path) -> None:
    canonical.parent.mkdir(parents=True, exist_ok=True)
    if canonical.is_symlink():
        _atomic_symlink_publish(staging, canonical)
        _prune_version_history(staging.parent, current_target=staging)
        return
    if not canonical.exists():
        os.replace(staging, canonical)
        _fsync_directory(canonical.parent)
        return
    try:
        _atomic_exchange_directories(staging, canonical)
    except OSError as exc:
        if exc.errno not in {errno.ENOSYS, errno.EINVAL, getattr(errno, "ENOTSUP", errno.EINVAL)}:
            raise
        _atomic_symlink_publish(staging, canonical)
        _prune_version_history(staging.parent, current_target=staging)
        return
    history = staging.parent / f"history-{uuid.uuid4().hex}"
    os.replace(staging, history)
    _prune_version_history(history.parent, current_target=None)
    _fsync_directory(canonical.parent)


def _persist_failure_summary(
    *,
    summary_path: Path,
    summary: dict[str, Any],
    output_root: Path,
    trade_date: str,
) -> None:
    failure_date_root = output_root / ".failures" / trade_date
    resolved_root = output_root.resolve()
    try:
        summary_path.parent.resolve().relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError("failure summary path escapes strategy output root") from exc
    atomic_write_json(summary_path, summary)
    _prune_version_history(
        failure_date_root,
        current_target=summary_path.parent,
        retain=10,
    )


def _relocate_result_paths(
    paths: dict[str, Any],
    *,
    staging: Path,
    canonical: Path,
) -> dict[str, Any]:
    relocated: dict[str, Any] = {}
    for key, value in paths.items():
        candidate = Path(str(value))
        try:
            relative = candidate.relative_to(staging)
        except ValueError:
            relocated[key] = value
        else:
            relocated[key] = str(canonical / relative)
    return relocated


def _atomic_symlink_publish(staging: Path, canonical: Path) -> None:
    if canonical.exists() and not canonical.is_symlink():
        raise RuntimeError(
            "atomic symlink fallback requires canonical path migration; existing real directory preserved"
        )
    try:
        staging.resolve(strict=True).relative_to(staging.parent.parent.parent.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise RuntimeError("staging directory escapes version root") from exc
    temporary = canonical.with_name(f".{canonical.name}.link-{uuid.uuid4().hex}")
    relative_target = os.path.relpath(staging, canonical.parent)
    temporary.symlink_to(relative_target, target_is_directory=True)
    try:
        os.replace(temporary, canonical)
        _fsync_directory(canonical.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _prune_version_history(
    versions_root: Path,
    *,
    current_target: Path | None,
    retain: int = 3,
) -> None:
    root = versions_root.resolve(strict=True)
    current = current_target.resolve(strict=True) if current_target is not None else None
    candidates = []
    for candidate in versions_root.iterdir():
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (FileNotFoundError, ValueError, OSError):
            continue
        if current is not None and resolved == current:
            continue
        if candidate.is_dir() and not candidate.is_symlink():
            candidates.append(candidate)
    candidates.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    retained_history = max(retain - (1 if current is not None else 0), 0)
    for stale in candidates[retained_history:]:
        try:
            shutil.rmtree(stale)
        except OSError:
            continue


def _atomic_exchange_directories(left: Path, right: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    left_b = os.fsencode(left)
    right_b = os.fsencode(right)
    if sys.platform == "darwin":
        renamex_np = libc.renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(left_b, right_b, 0x00000002)  # RENAME_SWAP
    elif sys.platform.startswith("linux"):
        renameat2 = libc.renameat2
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, left_b, -100, right_b, 0x2)  # AT_FDCWD, RENAME_EXCHANGE
    else:
        raise RuntimeError("atomic directory exchange is unsupported on this platform")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def check_strategy_daily_eod_dependencies(
    *,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    rows = _fetch_one(
        service,
        """
        SELECT daily_status, minute5_status, deps_status, failed_jobs
        FROM ops.daily_pipeline_status
        WHERE trade_date = %s
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        [trade_date],
    )
    if not rows:
        failure = {"status": "failed", "reason": "missing daily_pipeline_status"}
        return {"common": failure, "intraday": failure}
    row = rows[0]
    common_failures = []
    if str(row.get("daily_status") or "") not in {"success", "partial_success"}:
        failure = f"daily_status={row.get('daily_status')}"
        detail = _failed_job_reason(row.get("failed_jobs"), stage="daily")
        common_failures.append(f"{failure}: {detail}" if detail else failure)
    if str(row.get("deps_status") or "") != "success":
        failure = f"deps_status={row.get('deps_status')}"
        detail = _failed_job_reason(row.get("failed_jobs"), stage="deps")
        common_failures.append(f"{failure}: {detail}" if detail else failure)
    common = (
        {"status": "failed", "reason": "; ".join(common_failures)}
        if common_failures
        else {"status": "success"}
    )
    if str(row.get("minute5_status") or "") in {"success", "partial_success"}:
        intraday = {"status": "success"}
    else:
        reason = _failed_job_reason(row.get("failed_jobs"), stage="minute5")
        intraday = {
            "status": "failed",
            "reason": reason or f"minute5_status={row.get('minute5_status')}",
        }
    return {"common": common, "intraday": intraday}


def _normalize_dependency_check(check: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if "common" in check or "intraday" in check:
        return {
            "common": dict(
                check.get("common")
                or {"status": "failed", "reason": "missing common dependency status"}
            ),
            "intraday": dict(
                check.get("intraday")
                or {"status": "failed", "reason": "missing intraday dependency status"}
            ),
        }
    status = str(check.get("status") or "failed")
    normalized = {"status": status}
    if check.get("reason"):
        normalized["reason"] = str(check["reason"])
    return {"common": dict(normalized), "intraday": dict(normalized)}


def strategy_blocked_reason(
    strategy_name: str,
    dependency_check: dict[str, dict[str, Any]],
) -> str | None:
    failures = []
    for dependency_name in STRATEGY_DEPENDENCIES[strategy_name]:
        dependency = dependency_check[dependency_name]
        if dependency.get("status") != "success":
            reason = str(dependency.get("reason") or "dependency check failed")
            failures.append(f"{dependency_name}: {reason}")
    return "; ".join(failures) if failures else None


def _dependency_check_status(dependency_check: dict[str, dict[str, Any]]) -> str:
    return (
        "success"
        if all(item.get("status") == "success" for item in dependency_check.values())
        else "failed"
    )


def _dependency_failure_reason(dependency_check: dict[str, dict[str, Any]]) -> str | None:
    failures = []
    for name, item in dependency_check.items():
        if item.get("status") != "success":
            failures.append(f"{name}: {item.get('reason') or 'dependency check failed'}")
    return "; ".join(failures) if failures else None


def _failed_job_reason(value: Any, *, stage: str) -> str | None:
    jobs = value
    if isinstance(jobs, str):
        try:
            jobs = json.loads(jobs)
        except json.JSONDecodeError:
            return None
    if not isinstance(jobs, list):
        return None
    for job in jobs:
        if not isinstance(job, dict) or str(job.get("stage") or "") != stage:
            continue
        provider = str(job.get("source") or job.get("provider") or "").strip()
        error = str(job.get("error_summary") or job.get("error") or "").strip()
        reason = " ".join(part for part in (provider, error) if part)
        if reason:
            return reason
    return None


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


def _write_review_manifest(output_dir: Path) -> dict[str, int]:
    frames: list[pd.DataFrame] = []
    strategy_files = {
        "lhb_shortline": "strategy_lhb_shortline_review.csv",
        "mid_trend": "strategy_mid_trend_review.csv",
        "tech_bottleneck": "strategy_tech_bottleneck_review.csv",
    }
    counts: dict[str, int] = {}
    for strategy_id, filename in strategy_files.items():
        path = output_dir / filename
        if path.exists() and path.stat().st_size > 0:
            frame = pd.read_csv(path, low_memory=False)
            frame["strategy_id"] = strategy_id
            frame["artifact_path"] = filename
            frames.append(frame)
            counts[strategy_id] = int(len(frame))
        else:
            counts[strategy_id] = 0
    legacy_manifest_path = output_dir / "strategy_daily_eod_review_manifest.csv"
    manifest_path = output_dir / "review_queue_strategy_manifest.csv"
    if not frames:
        empty = pd.DataFrame()
        empty.to_csv(legacy_manifest_path, index=False)
        empty.to_csv(manifest_path, index=False)
        return counts
    manifest = pd.concat(frames, ignore_index=True, sort=False)
    manifest.to_csv(legacy_manifest_path, index=False)
    manifest.to_csv(manifest_path, index=False)
    return counts
