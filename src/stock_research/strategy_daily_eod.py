from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.lhb_data import run_lhb_shortline_daily_pipeline_v1
from stock_research.mid_trend_shadow_weekly_control import run_mid_trend_shadow_weekly_control_review
from stock_research.strategy_daily_eod_store import apply_strategy_daily_eod_status_schema


DependencyChecker = Callable[..., dict[str, Any]]
StrategyRunner = Callable[..., dict[str, Any]]

_SUCCESS_DEPENDENCY_STATUSES = {"success", "partial_success"}
DEFAULT_STRATEGY_NAMES = ("lhb_shortline", "mid_trend", "tech_bottleneck")
DEFAULT_STRATEGY_RUN_ID_TEMPLATE = "strategy-eod-{trade_date}-local"
DEFAULT_SOURCE_TYPE = "strategy_manifest"
DEFAULT_REVIEW_TIER = "top5_focus"
MID_TREND_VARIANT = "top5_weekly_max2_selective_trend_holding_protection_v1"
LHB_REVIEW_COLUMNS = [
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
TECH_REVIEW_COLUMNS = [
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

_DEPENDENCY_SQL = """
SELECT daily_status, minute5_status, deps_status
FROM ops.daily_pipeline_status
WHERE trade_date = %s
ORDER BY updated_at DESC
LIMIT 1
"""


def run_strategy_daily_eod(
    trade_date: str,
    *,
    output_root: str | Path,
    dependency_checker: DependencyChecker | None = None,
    lhb_shortline_runner: StrategyRunner | None = None,
    mid_trend_runner: StrategyRunner | None = None,
    tech_bottleneck_runner: StrategyRunner | None = None,
) -> dict[str, Any]:
    apply_strategy_daily_eod_status_schema()

    output_dir = Path(output_root) / trade_date
    output_dir.mkdir(parents=True, exist_ok=True)

    dependency_checker = dependency_checker or check_strategy_daily_eod_dependencies
    strategy_runners = _resolve_strategy_runners(
        lhb_shortline_runner=lhb_shortline_runner,
        mid_trend_runner=mid_trend_runner,
        tech_bottleneck_runner=tech_bottleneck_runner,
    )

    try:
        dependency_check = dependency_checker(trade_date=trade_date)
    except Exception as exc:
        dependency_check = {
            "status": "failed",
            "reason": f"dependency_checker_exception: {exc}",
        }

    if dependency_check.get("status") != "success":
        strategy_status = _skipped_strategy_status()
    else:
        strategy_status = {}
        for name, runner in strategy_runners.items():
            try:
                strategy_status[name] = runner(
                    trade_date=trade_date,
                    output_dir=output_dir,
                    strategy_name=name,
                )
            except Exception as exc:
                strategy_status[name] = {
                    "status": "failed",
                    "reason": f"strategy_runner_exception: {exc}",
                }

    overall_status = (
        "success"
        if all(result.get("status") == "success" for result in strategy_status.values())
        and dependency_check.get("status") == "success"
        else "failed"
    )
    review_rows = sum(int(result.get("review_rows") or 0) for result in strategy_status.values())

    summary_path = output_dir / "strategy_eod_publish_summary.json"
    summary = {
        "trade_date": trade_date,
        "status": overall_status,
        "dependency_check": dependency_check,
        "strategy_status": strategy_status,
        "review_rows": review_rows,
        "output_dir": str(output_dir),
        "summary_path": str(summary_path),
    }

    try:
        _write_summary(summary_path=summary_path, summary=summary)
    except Exception as exc:
        summary["status"] = "failed"
        summary["reason"] = f"summary_write_exception: {exc}"
    return summary


def check_strategy_daily_eod_dependencies(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    with connect(service) as conn:
        rows = fetch_all(conn, _DEPENDENCY_SQL, [trade_date])

    if not rows:
        return {"status": "failed", "reason": "daily_pipeline_status missing"}

    row = rows[0]
    daily_status = str(row.get("daily_status") or "")
    minute5_status = str(row.get("minute5_status") or "")
    deps_status = str(row.get("deps_status") or "")

    if (
        daily_status in _SUCCESS_DEPENDENCY_STATUSES
        and minute5_status in _SUCCESS_DEPENDENCY_STATUSES
        and deps_status == "success"
    ):
        return {
            "status": "success",
            "daily_status": daily_status,
            "minute5_status": minute5_status,
            "deps_status": deps_status,
        }

    return {
        "status": "failed",
        "reason": (
            "daily_pipeline_status not ready: "
            f"daily_status={daily_status or 'missing'}, "
            f"minute5_status={minute5_status or 'missing'}, "
            f"deps_status={deps_status or 'missing'}"
        ),
        "daily_status": daily_status,
        "minute5_status": minute5_status,
        "deps_status": deps_status,
    }


def build_lhb_shortline_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    strategy_name: str = "lhb_shortline",
    pipeline_runner: StrategyRunner = run_lhb_shortline_daily_pipeline_v1,
    case_path: str | Path | None = None,
    lhb_features_path: str | Path | None = None,
    alignment_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_case_path = Path(case_path) if case_path is not None else _default_lhb_case_path()
    resolved_lhb_features_path = (
        Path(lhb_features_path) if lhb_features_path is not None else _default_lhb_features_path()
    )
    resolved_alignment_path = (
        Path(alignment_path) if alignment_path is not None else _default_lhb_alignment_path()
    )

    try:
        run_result = pipeline_runner(
            case_path=resolved_case_path,
            lhb_features_path=resolved_lhb_features_path,
            alignment_path=resolved_alignment_path,
            trade_date=trade_date,
            output_dir=output_dir,
        )
    except FileNotFoundError as exc:
        missing_path = exc.filename or str(exc)
        return {"status": "failed", "reason": f"source_artifact_missing: {missing_path}"}
    except Exception as exc:
        return {"status": "failed", "reason": f"pipeline_runner_exception: {exc}"}

    watchlist_path = _extract_required_path(run_result, "daily_watchlist")
    if watchlist_path is None:
        return {"status": "failed", "reason": "required_generated_file_missing: daily_watchlist"}

    try:
        source = pd.read_csv(watchlist_path, low_memory=False)
    except FileNotFoundError:
        return {"status": "failed", "reason": f"required_generated_file_missing: {watchlist_path}"}

    review = _build_empty_review(LHB_REVIEW_COLUMNS)
    if not source.empty:
        working = source.copy()
        working["asset_id"] = working.get("asset_id", working.get("ts_code", "")).astype(str)
        working["score_total"] = pd.to_numeric(working.get("auction_enhanced_score"), errors="coerce")
        working = working.sort_values(["score_total", "asset_id"], ascending=[False, True], na_position="last").head(5).copy()
        working["rank"] = range(1, len(working) + 1)
        working["source_rank"] = working["rank"]
        review = pd.DataFrame(
            {
                "trade_date": trade_date,
                "asset_id": working["asset_id"],
                "rank": working["rank"],
                "score_total": working["score_total"],
                "score_source": "auction_enhanced_score",
                "score_explanation": "真实策略输出分；无策略分字段时留空，不使用排名占位分",
                "strategy_id": "lhb_shortline",
                "strategy_name": "LHB Shortline Combo",
                "strategy_run_id": _strategy_run_id(trade_date),
                "source_type": DEFAULT_SOURCE_TYPE,
                "source_name": "strategy_lhb_shortline",
                "source_rank": working["source_rank"],
                "review_tier": DEFAULT_REVIEW_TIER,
            }
        )[LHB_REVIEW_COLUMNS]

    review_path = Path(output_dir) / "strategy_lhb_shortline_review.csv"
    _write_review(review_path, review, LHB_REVIEW_COLUMNS)
    return {"status": "success", "review_rows": int(len(review)), "paths": {"review": str(review_path)}}


def build_mid_trend_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    strategy_name: str = "mid_trend",
    weekly_control_runner: StrategyRunner = run_mid_trend_shadow_weekly_control_review,
    funnel_detail_path: str | Path | None = None,
) -> dict[str, Any]:
    try:
        resolved_funnel_detail_path = (
            Path(funnel_detail_path)
            if funnel_detail_path is not None
            else _resolve_default_mid_trend_funnel_detail_path()
        )
    except FileNotFoundError as exc:
        return {"status": "failed", "reason": f"funnel_detail_path_resolution_failed: {exc}"}

    if not resolved_funnel_detail_path.exists():
        return {"status": "failed", "reason": f"source_artifact_missing: {resolved_funnel_detail_path}"}

    funnel_detail = pd.read_csv(resolved_funnel_detail_path, low_memory=False)
    if funnel_detail.empty:
        review = _build_empty_review(LHB_REVIEW_COLUMNS)
        review_path = Path(output_dir) / "strategy_mid_trend_review.csv"
        _write_review(review_path, review, LHB_REVIEW_COLUMNS)
        return {"status": "success", "review_rows": 0, "paths": {"review": str(review_path)}}

    start_date = str(funnel_detail["trade_date"].astype(str).min())
    try:
        control_result = weekly_control_runner(
            funnel_detail_path=resolved_funnel_detail_path,
            start_date=start_date,
            end_date=trade_date,
            output_dir=output_dir,
            top_n=5,
            buffer_rank=10,
            max_weekly_replacements=2,
        )
    except Exception as exc:
        return {"status": "failed", "reason": f"weekly_control_runner_exception: {exc}"}

    positions_path = _extract_required_path(control_result, "positions")
    if positions_path is None:
        return {"status": "failed", "reason": "required_generated_file_missing: positions"}

    try:
        positions = pd.read_csv(positions_path, low_memory=False)
    except FileNotFoundError:
        return {"status": "failed", "reason": f"required_generated_file_missing: {positions_path}"}

    filtered = positions[positions.get("variant_name", "").astype(str).eq(MID_TREND_VARIANT)].copy()
    if filtered.empty:
        review = _build_empty_review(LHB_REVIEW_COLUMNS)
    else:
        filtered["rebalance_date"] = filtered["rebalance_date"].astype(str)
        latest_rebalance_date = filtered["rebalance_date"].max()
        latest_positions = filtered[filtered["rebalance_date"].eq(latest_rebalance_date)].copy().reset_index(drop=True)
        latest_positions["source_rank"] = range(1, len(latest_positions) + 1)

        score_lookup = funnel_detail.copy()
        score_lookup["trade_date"] = score_lookup["trade_date"].astype(str)
        score_lookup["asset_id"] = score_lookup["asset_id"].astype(str)
        score_lookup["mid_trend_funnel_score"] = pd.to_numeric(score_lookup.get("mid_trend_funnel_score"), errors="coerce")
        score_lookup = score_lookup[score_lookup["trade_date"].eq(trade_date)][["asset_id", "mid_trend_funnel_score"]]
        score_map = score_lookup.drop_duplicates(subset=["asset_id"], keep="last").set_index("asset_id")["mid_trend_funnel_score"]

        latest_positions["asset_id"] = latest_positions["asset_id"].astype(str)
        latest_positions["score_total"] = latest_positions["asset_id"].map(score_map)
        latest_positions["rank"] = range(1, len(latest_positions) + 1)
        review = pd.DataFrame(
            {
                "trade_date": trade_date,
                "asset_id": latest_positions["asset_id"],
                "rank": latest_positions["rank"],
                "score_total": latest_positions["score_total"],
                "score_source": "mid_trend_funnel_score",
                "score_explanation": "真实策略输出分；无策略分字段时留空，不使用排名占位分",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "strategy_run_id": _strategy_run_id(trade_date),
                "source_type": DEFAULT_SOURCE_TYPE,
                "source_name": "strategy_mid_trend",
                "source_rank": latest_positions["source_rank"],
                "review_tier": DEFAULT_REVIEW_TIER,
            }
        )[LHB_REVIEW_COLUMNS]

    review_path = Path(output_dir) / "strategy_mid_trend_review.csv"
    _write_review(review_path, review, LHB_REVIEW_COLUMNS)
    return {"status": "success", "review_rows": int(len(review)), "paths": {"review": str(review_path)}}


def build_tech_bottleneck_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    strategy_name: str = "tech_bottleneck",
    candidate_path: str | Path | None = None,
) -> dict[str, Any]:
    try:
        resolved_candidate_path = _resolve_tech_bottleneck_candidate_path(candidate_path)
    except FileNotFoundError as exc:
        return {"status": "failed", "reason": f"candidate_path_resolution_failed: {exc}"}

    if not resolved_candidate_path.exists():
        return {"status": "failed", "reason": f"source_artifact_missing: {resolved_candidate_path}"}

    candidates = pd.read_csv(resolved_candidate_path, low_memory=False)
    candidates["trade_date"] = candidates.get("trade_date", "").astype(str)
    candidates["asset_id"] = candidates.get("asset_id", "").astype(str)
    candidates["bottleneck_score"] = pd.to_numeric(candidates.get("bottleneck_score"), errors="coerce")
    candidates = candidates[candidates["trade_date"].eq(trade_date)].copy()
    candidates = candidates.sort_values(["bottleneck_score", "asset_id"], ascending=[False, True], na_position="last").head(5)

    review = _build_empty_review(TECH_REVIEW_COLUMNS)
    if not candidates.empty:
        candidates = candidates.reset_index(drop=True)
        candidates["rank"] = range(1, len(candidates) + 1)
        candidates["source_rank"] = candidates["rank"]
        candidates["score_total"] = candidates["bottleneck_score"] * 100.0
        review = pd.DataFrame(
            {
                "trade_date": trade_date,
                "asset_id": candidates["asset_id"],
                "rank": candidates["rank"],
                "bottleneck_score": candidates["bottleneck_score"],
                "score_total": candidates["score_total"],
                "score_source": "bottleneck_score",
                "score_explanation": "Tech Bottleneck point-in-time candidate snapshot score shown on a 0-100 scale",
                "strategy_id": "tech_bottleneck",
                "strategy_name": "Tech Bottleneck Discovery",
                "strategy_run_id": _strategy_run_id(trade_date),
                "source_type": DEFAULT_SOURCE_TYPE,
                "source_name": "strategy_tech_bottleneck",
                "source_rank": candidates["source_rank"],
                "review_tier": DEFAULT_REVIEW_TIER,
            }
        )[TECH_REVIEW_COLUMNS]

    review_path = Path(output_dir) / "strategy_tech_bottleneck_review.csv"
    _write_review(review_path, review, TECH_REVIEW_COLUMNS)
    return {"status": "success", "review_rows": int(len(review)), "paths": {"review": str(review_path)}}


def _missing_runner(*, strategy_name: str = "unknown", **_kwargs: Any) -> dict[str, Any]:
    return {"status": "failed", "reason": f"{strategy_name} runner not configured"}


def _resolve_strategy_runners(
    *,
    lhb_shortline_runner: StrategyRunner | None,
    mid_trend_runner: StrategyRunner | None,
    tech_bottleneck_runner: StrategyRunner | None,
) -> dict[str, StrategyRunner]:
    return {
        "lhb_shortline": lhb_shortline_runner or build_lhb_shortline_strategy_eod,
        "mid_trend": mid_trend_runner or build_mid_trend_strategy_eod,
        "tech_bottleneck": tech_bottleneck_runner or build_tech_bottleneck_strategy_eod,
    }


def _skipped_strategy_status() -> dict[str, dict[str, str]]:
    return {
        name: {"status": "skipped", "reason": "dependency_check_failed"}
        for name in DEFAULT_STRATEGY_NAMES
    }


def _write_summary(*, summary_path: Path, summary: dict[str, Any]) -> None:
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _strategy_run_id(trade_date: str) -> str:
    return DEFAULT_STRATEGY_RUN_ID_TEMPLATE.format(trade_date=trade_date)


def _build_empty_review(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _write_review(review_path: Path, review: pd.DataFrame, columns: list[str]) -> None:
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review.loc[:, columns].to_csv(review_path, index=False)


def _extract_required_path(result: dict[str, Any], key: str) -> Path | None:
    paths = result.get("paths")
    if not isinstance(paths, dict):
        return None
    value = paths.get(key)
    if not value:
        return None
    return Path(value)


def _resolve_tech_bottleneck_candidate_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return _select_latest_artifact_path("tech_bottleneck_evidence_adjusted_candidates.csv")


def _repo_root() -> Path:
    return _main_repo_root_from(Path(__file__))


def _main_repo_root_from(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    parts = resolved.parts
    if ".worktrees" in parts:
        idx = parts.index(".worktrees")
        return Path(*parts[:idx])
    return resolved.parents[2]


def _research_output_root() -> Path:
    return _repo_root() / "outputs" / "research"


def _default_lhb_case_path() -> Path:
    return _research_output_root() / "dragon_case_curated_library_failure_v2_1.csv"


def _default_lhb_features_path() -> Path:
    return _research_output_root() / "lhb_risk_feature_case_detail_v2_1.csv"


def _default_lhb_alignment_path() -> Path:
    return _research_output_root() / "dragon_case_lhb_alignment_audit_2024_2026.csv"


def _resolve_default_mid_trend_funnel_detail_path() -> Path:
    return _select_latest_artifact_path("mid_trend_watch_funnel_detail.csv")


def _select_latest_artifact_path(artifact_name: str, *, base_dir: str | Path | None = None) -> Path:
    search_root = Path(base_dir) if base_dir is not None else _research_output_root()
    candidates = sorted(search_root.rglob(artifact_name))
    if not candidates:
        raise FileNotFoundError(f"no artifact found for {artifact_name} under {search_root}")

    ranked_candidates = [
        (
            _artifact_coverage_end_date(candidate),
            candidate.stat().st_mtime,
            str(candidate),
            candidate,
        )
        for candidate in candidates
    ]
    return max(ranked_candidates)[-1]


def _artifact_coverage_end_date(path: str | Path, *, date_column: str = "trade_date") -> str:
    candidate = Path(path)
    try:
        frame = pd.read_csv(candidate, usecols=[date_column], low_memory=False)
    except ValueError:
        return ""
    if frame.empty:
        return ""

    parsed = pd.to_datetime(frame[date_column], errors="coerce")
    if parsed.empty or parsed.isna().all():
        return ""
    return parsed.max().date().isoformat()
