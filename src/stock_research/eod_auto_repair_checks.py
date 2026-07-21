from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.data_run_manifest import (
    load_browser_acceptance_manifests,
    load_recent_data_run_manifest,
)
from stock_research.db import connect, fetch_all
from stock_research.eod_auto_repair_models import RepairCheckResult, RepairStatus
from stock_research.eod_browser_acceptance import (
    BrowserAcceptanceError,
    validate_browser_acceptance_manifest_entry,
)


@dataclass(frozen=True)
class RepairCheck:
    name: str
    run: Callable[[], RepairCheckResult]


def evaluate_count_check(
    *,
    name: str,
    row_count: int,
    min_rows: int,
    latest_trade_date: str | None,
    trade_date: str,
    blocker: bool = True,
) -> RepairCheckResult:
    metrics = {"row_count": int(row_count), "latest_trade_date": latest_trade_date}
    if int(row_count) >= int(min_rows) and latest_trade_date == trade_date:
        return RepairCheckResult(name=name, status=RepairStatus.SUCCESS, message="ready", metrics=metrics)
    message = f"{name} not ready for {trade_date}: row_count={row_count}, latest_trade_date={latest_trade_date}"
    return RepairCheckResult(
        name=name,
        status=RepairStatus.FAILED,
        message=message,
        metrics=metrics,
        blocker=blocker,
    )


def _default_fetcher(sql: str, params: list[object]) -> list[dict[str, object]]:
    with connect(SETTINGS.research_service) as conn:
        return list(fetch_all(conn, sql, params))


def check_lhb_features(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    sql = """
        SELECT count(*) AS row_count,
               count(DISTINCT ts_code) AS asset_count,
               max(trade_date)::text AS latest_trade_date
        FROM factor.lhb_event_features_daily
        WHERE trade_date = %s
    """
    rows = fetcher(sql, [trade_date])
    row = dict(rows[0]) if rows else {}
    result = evaluate_count_check(
        name="lhb_features",
        row_count=int(row.get("row_count") or 0),
        min_rows=1,
        latest_trade_date=str(row.get("latest_trade_date") or ""),
        trade_date=trade_date,
    )
    return RepairCheckResult(
        name=result.name,
        status=result.status,
        message=result.message,
        metrics={**result.metrics, "asset_count": int(row.get("asset_count") or 0)},
        blocker=result.blocker,
    )


def _fetch_one(fetcher: Callable[[str, list[object]], list[dict[str, object]]], sql: str, params: list[object]) -> dict[str, object]:
    rows = fetcher(sql, params)
    return dict(rows[0]) if rows else {}


def _date_text_after(value: str, trade_date: str) -> bool:
    normalized = str(value or "")[:10]
    return bool(normalized and normalized > trade_date)


def check_daily_bars(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    sql = """
        SELECT expected_count,
               actual_count,
               jsonb_array_length(missing_symbols) AS missing_count,
               jsonb_array_length(abnormal_symbols) AS abnormal_count
        FROM ops.daily_pipeline_quality
        WHERE trade_date = %s
          AND dataset_name = 'daily_bar'
        ORDER BY updated_at DESC
        LIMIT 1
    """
    row = _fetch_one(fetcher, sql, [trade_date])
    actual = int(row.get("actual_count") or 0)
    expected = int(row.get("expected_count") or 0)
    missing = int(row.get("missing_count") or 0)
    abnormal = int(row.get("abnormal_count") or 0)
    gap_ratio = (missing + abnormal) / expected if expected else 1.0
    metrics = {
        "actual_count": actual,
        "expected_count": expected,
        "missing_count": missing,
        "abnormal_count": abnormal,
        "gap_ratio": round(gap_ratio, 6),
    }
    if expected > 0 and actual > 0 and gap_ratio <= 0.01:
        status = RepairStatus.DEGRADED if missing or abnormal else RepairStatus.SUCCESS
        return RepairCheckResult("daily_bars", status, "ready", metrics)
    return RepairCheckResult("daily_bars", RepairStatus.FAILED, "daily quality failed", metrics, blocker=True)


def check_minute5_bars(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    sql = """
        SELECT
               max(expected_count) FILTER (WHERE dataset_name = 'minute5_bar') AS raw_expected_count,
               max(actual_count) FILTER (WHERE dataset_name = 'minute5_bar') AS raw_actual_count,
               max(jsonb_array_length(missing_symbols)) FILTER (WHERE dataset_name = 'minute5_bar') AS raw_missing_count,
               max(jsonb_array_length(abnormal_symbols)) FILTER (WHERE dataset_name = 'minute5_bar') AS raw_abnormal_count,
               max(expected_count) FILTER (WHERE dataset_name = 'minute5_qfq_bar') AS qfq_expected_count,
               max(actual_count) FILTER (WHERE dataset_name = 'minute5_qfq_bar') AS qfq_actual_count,
               max(jsonb_array_length(missing_symbols)) FILTER (WHERE dataset_name = 'minute5_qfq_bar') AS qfq_missing_count,
               max(jsonb_array_length(abnormal_symbols)) FILTER (WHERE dataset_name = 'minute5_qfq_bar') AS qfq_abnormal_count
        FROM ops.daily_pipeline_quality
        WHERE trade_date = %s
          AND dataset_name IN ('minute5_bar', 'minute5_qfq_bar')
    """
    row = _fetch_one(fetcher, sql, [trade_date])
    raw_actual = int(row.get("raw_actual_count") or 0)
    raw_expected = int(row.get("raw_expected_count") or 0)
    raw_missing = int(row.get("raw_missing_count") or 0)
    raw_abnormal = int(row.get("raw_abnormal_count") or 0)
    qfq_actual = int(row.get("qfq_actual_count") or 0)
    qfq_expected = int(row.get("qfq_expected_count") or 0)
    qfq_missing = int(row.get("qfq_missing_count") or 0)
    qfq_abnormal = int(row.get("qfq_abnormal_count") or 0)
    raw_gap_ratio = (
        (raw_missing + raw_abnormal) / raw_expected if raw_expected else 1.0
    )
    qfq_gap_ratio = (
        (qfq_missing + qfq_abnormal) / qfq_expected if qfq_expected else 1.0
    )
    metrics = {
        "raw_actual_count": raw_actual,
        "raw_expected_count": raw_expected,
        "raw_missing_count": raw_missing,
        "raw_abnormal_count": raw_abnormal,
        "raw_gap_ratio": round(raw_gap_ratio, 6),
        "qfq_actual_count": qfq_actual,
        "qfq_expected_count": qfq_expected,
        "qfq_missing_count": qfq_missing,
        "qfq_abnormal_count": qfq_abnormal,
        "qfq_gap_ratio": round(qfq_gap_ratio, 6),
    }
    if (
        raw_expected > 0
        and raw_actual > 0
        and raw_gap_ratio <= 0.01
        and qfq_expected > 0
        and qfq_actual > 0
        and qfq_gap_ratio <= 0.01
    ):
        status = (
            RepairStatus.DEGRADED
            if raw_missing or raw_abnormal or qfq_missing or qfq_abnormal
            else RepairStatus.SUCCESS
        )
        return RepairCheckResult("minute5_bars", status, "ready", metrics)
    return RepairCheckResult("minute5_bars", RepairStatus.FAILED, "minute5 quality failed", metrics, blocker=True)


def check_lhb_source(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    sql = """
        SELECT
            (SELECT count(*)::int FROM market.lhb_top_list_daily WHERE trade_date = %s) AS top_list_rows,
            (SELECT count(*)::int FROM market.lhb_top_inst_daily WHERE trade_date = %s) AS top_inst_rows,
            (SELECT max(trade_date)::text FROM market.lhb_top_list_daily WHERE trade_date <= %s) AS top_list_latest,
            (SELECT max(trade_date)::text FROM market.lhb_top_inst_daily WHERE trade_date <= %s) AS top_inst_latest
    """
    row = _fetch_one(fetcher, sql, [trade_date, trade_date, trade_date, trade_date])
    top_list_rows = int(row.get("top_list_rows") or 0)
    top_inst_rows = int(row.get("top_inst_rows") or 0)
    metrics = {
        "top_list_rows": top_list_rows,
        "top_inst_rows": top_inst_rows,
        "top_list_latest": str(row.get("top_list_latest") or ""),
        "top_inst_latest": str(row.get("top_inst_latest") or ""),
    }
    if top_list_rows > 0 and metrics["top_list_latest"] == trade_date:
        return RepairCheckResult("lhb_source", RepairStatus.SUCCESS, "ready", metrics)
    return RepairCheckResult("lhb_source", RepairStatus.FAILED, "lhb source stale or empty", metrics, blocker=True)


def check_technical_features(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    sql = """
        SELECT count(*)::int AS row_count,
               count(DISTINCT asset_id)::int AS asset_count,
               max(trade_date)::text AS latest_trade_date
        FROM factor.stock_technical_features_daily
        WHERE trade_date = %s
          AND adjust_type = 'hfq'
    """
    row = _fetch_one(fetcher, sql, [trade_date])
    result = evaluate_count_check(
        name="technical_features",
        row_count=int(row.get("row_count") or 0),
        min_rows=1,
        latest_trade_date=str(row.get("latest_trade_date") or ""),
        trade_date=trade_date,
    )
    return RepairCheckResult(result.name, result.status, result.message, {**result.metrics, "asset_count": int(row.get("asset_count") or 0)}, result.blocker)


def check_factor_daily(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    from stock_research.factor_config import manual_v1_config

    calc_version = str(manual_v1_config().get("calc_version") or "v1")
    sql = """
        SELECT count(*)::int AS row_count,
               count(DISTINCT asset_id)::int AS asset_count,
               count(DISTINCT factor_name)::int AS factor_count,
               max(trade_date)::text AS latest_trade_date
        FROM factor.factor_daily
        WHERE trade_date = %s
          AND calc_version = %s
    """
    row = _fetch_one(fetcher, sql, [trade_date, calc_version])
    result = evaluate_count_check(
        name="factor_daily",
        row_count=int(row.get("row_count") or 0),
        min_rows=1,
        latest_trade_date=str(row.get("latest_trade_date") or ""),
        trade_date=trade_date,
    )
    return RepairCheckResult(
        result.name,
        result.status,
        result.message,
        {
            **result.metrics,
            "asset_count": int(row.get("asset_count") or 0),
            "factor_count": int(row.get("factor_count") or 0),
            "calc_version": calc_version,
        },
        result.blocker,
    )


def check_score_topn(trade_date: str, *, fetcher=_default_fetcher, score_version: str = "manual_v1") -> RepairCheckResult:
    sql = """
        SELECT count(*)::int AS row_count,
               count(DISTINCT asset_id)::int AS asset_count,
               max(trade_date)::text AS latest_trade_date,
               count(*) FILTER (WHERE COALESCE(score_total, 0) <> 0)::int AS nonzero_rows
        FROM factor.stock_score_daily
        WHERE trade_date = %s
          AND score_version = %s
    """
    row = _fetch_one(fetcher, sql, [trade_date, score_version])
    result = evaluate_count_check(
        name="score_topn",
        row_count=int(row.get("row_count") or 0),
        min_rows=1,
        latest_trade_date=str(row.get("latest_trade_date") or ""),
        trade_date=trade_date,
    )
    nonzero = int(row.get("nonzero_rows") or 0)
    status = result.status if nonzero > 0 else RepairStatus.FAILED
    message = result.message if nonzero > 0 else "score rows are missing or all zero"
    return RepairCheckResult(
        result.name,
        status,
        message,
        {**result.metrics, "asset_count": int(row.get("asset_count") or 0), "nonzero_rows": nonzero},
        status == RepairStatus.FAILED,
    )


def check_watchlist(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    sql = """
        SELECT
            count(*) FILTER (WHERE watchlist_id = 'default')::int AS default_rows,
            count(*) FILTER (WHERE watchlist_id = 'diagnostics')::int AS diagnostics_rows
        FROM watchlist.watchlist_daily_signal
        WHERE trade_date = %s
    """
    row = _fetch_one(fetcher, sql, [trade_date])
    default_rows = int(row.get("default_rows") or 0)
    diagnostics_rows = int(row.get("diagnostics_rows") or 0)
    metrics = {"default_rows": default_rows, "diagnostics_rows": diagnostics_rows}
    if default_rows > 0 and diagnostics_rows > 0:
        return RepairCheckResult("watchlist", RepairStatus.SUCCESS, "ready", metrics)
    return RepairCheckResult("watchlist", RepairStatus.FAILED, "watchlist missing", metrics, blocker=True)


def check_market_monitor(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    sql = """
        SELECT
            (SELECT count(*)::int FROM research.market_emotion_state_daily WHERE trade_date = %s) AS emotion_rows,
            (SELECT count(*)::int FROM market.index_daily_bar WHERE trade_date = %s) AS index_rows,
            (SELECT count(*)::int FROM market.industry_daily_bar WHERE trade_date = %s AND industry_system = 'csrc') AS industry_rows
    """
    row = _fetch_one(fetcher, sql, [trade_date, trade_date, trade_date])
    metrics = {
        "emotion_rows": int(row.get("emotion_rows") or 0),
        "index_rows": int(row.get("index_rows") or 0),
        "industry_rows": int(row.get("industry_rows") or 0),
    }
    if metrics["emotion_rows"] > 0 and metrics["index_rows"] >= 5 and metrics["industry_rows"] > 0:
        return RepairCheckResult("market_monitor", RepairStatus.SUCCESS, "ready", metrics)
    return RepairCheckResult("market_monitor", RepairStatus.FAILED, "market monitor incomplete", metrics, blocker=True)


def check_strategy_publish(
    trade_date: str,
    *,
    manifest_loader=load_recent_data_run_manifest,
) -> RepairCheckResult:
    required = {
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
        "review_queue_strategy_manifest",
    }
    rows = [dict(row) for row in manifest_loader(trade_date=trade_date)]
    latest = {row.get("module"): row for row in rows if row.get("module") in required}
    missing = sorted(module for module in required if module not in latest)
    failed = sorted(
        module
        for module, row in latest.items()
        if row.get("status") != "success" or str(row.get("latest_trade_date") or "") != trade_date
    )
    strategy_ready = sum(
        1
        for module in ("strategy_lhb_shortline", "strategy_mid_trend", "strategy_tech_bottleneck")
        if module in latest
        and latest[module].get("status") == "success"
        and str(latest[module].get("latest_trade_date") or "") == trade_date
    )
    review_rows = int((latest.get("review_queue_strategy_manifest") or {}).get("row_count") or 0)
    stale_performance = _stale_strategy_performance_modules(latest, trade_date)
    metrics = {
        "strategy_ready": f"{strategy_ready}/3",
        "review_rows": review_rows,
        "missing_modules": missing,
        "failed_modules": failed,
        "stale_performance_modules": stale_performance,
    }
    if not missing and not failed and review_rows > 0:
        if stale_performance:
            return RepairCheckResult("strategy_publish", RepairStatus.DEGRADED, "strategy performance stale", metrics)
        return RepairCheckResult("strategy_publish", RepairStatus.SUCCESS, "ready", metrics)
    return RepairCheckResult("strategy_publish", RepairStatus.FAILED, "strategy publish incomplete", metrics, blocker=True)


def _browser_acceptance_failure(message: str, metrics: dict[str, object] | None = None) -> RepairCheckResult:
    return RepairCheckResult(
        "dashboard_browser_acceptance",
        RepairStatus.FAILED,
        message,
        metrics=dict(metrics or {}),
        blocker=True,
    )


def _browser_manifest_business_time(row: dict[str, object]) -> datetime:
    run_id = row.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("browser acceptance manifest run_id missing")
    for field in ("ended_at", "updated_at", "created_at"):
        raw_timestamp = row.get(field)
        if isinstance(raw_timestamp, datetime):
            parsed = raw_timestamp
        elif isinstance(raw_timestamp, str) and raw_timestamp:
            try:
                parsed = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            except ValueError:
                continue
        else:
            continue
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            continue
        return parsed.astimezone(timezone.utc)
    raise ValueError("browser acceptance manifest timestamp missing or invalid")


def check_dashboard_browser_acceptance(
    trade_date: str,
    *,
    manifest_loader=load_browser_acceptance_manifests,
) -> RepairCheckResult:
    try:
        rows = [
            dict(row)
            for row in manifest_loader(trade_date=trade_date)
            if row.get("module") == "dashboard_browser_acceptance"
            and row.get("source") == "eod_browser_acceptance"
        ]
    except Exception as exc:  # noqa: BLE001 - check failures must remain observable.
        return _browser_acceptance_failure(f"browser acceptance manifest load failed: {exc}")
    if not rows:
        return _browser_acceptance_failure("browser acceptance manifest missing")
    try:
        ranked = sorted(
            ((_browser_manifest_business_time(row), row) for row in rows),
            key=lambda item: item[0],
            reverse=True,
        )
    except (TypeError, ValueError) as exc:
        return _browser_acceptance_failure(f"browser acceptance manifest malformed: {exc}")
    latest_time, latest = ranked[0]
    if sum(1 for business_time, _row in ranked if business_time == latest_time) != 1:
        return _browser_acceptance_failure("browser acceptance latest manifest ambiguous")

    status = latest.get("status")
    if status not in {"success", "degraded"}:
        return _browser_acceptance_failure(
            "browser acceptance failed",
            {"run_id": str(latest.get("run_id") or ""), "status": status},
        )
    try:
        metrics = validate_browser_acceptance_manifest_entry(
            latest,
            expected_trade_date=trade_date,
        )
    except BrowserAcceptanceError as exc:
        return _browser_acceptance_failure(
            f"browser acceptance manifest malformed: {exc}"
        )
    if status == "success":
        return RepairCheckResult(
            "dashboard_browser_acceptance",
            RepairStatus.SUCCESS,
            "ready",
            metrics,
        )
    return RepairCheckResult(
        "dashboard_browser_acceptance",
        RepairStatus.DEGRADED,
        "browser acceptance publishable with warnings",
        metrics,
    )


def _stale_strategy_performance_modules(
    latest: dict[str, dict[str, object]],
    trade_date: str,
) -> list[str]:
    stale: list[str] = []
    for module_name in ("strategy_lhb_shortline", "strategy_mid_trend", "strategy_tech_bottleneck"):
        module = latest.get(module_name) or {}
        metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
        summary = metadata.get("summary") if isinstance(metadata.get("summary"), dict) else {}
        performance_date = str(
            summary.get("performance_effective_date")
            or summary.get("actual_end_date")
            or summary.get("equity_latest_date")
            or summary.get("end_date")
            or ""
        )
        if performance_date and performance_date < trade_date:
            stale.append(f"{module_name}:{performance_date}")
    return stale


def check_review_queue(trade_date: str, *, output_root: str | Path = "outputs") -> RepairCheckResult:
    path = Path(output_root) / "research" / "strategy_daily_eod" / trade_date / "review_queue_strategy_manifest.csv"
    if not path.exists():
        return RepairCheckResult("review_queue", RepairStatus.FAILED, f"missing {path}", {"path": str(path)}, blocker=True)
    frame = pd.read_csv(path)
    rows = frame.to_dict("records")
    score_check = evaluate_strategy_review_scores(rows, trade_date=trade_date)
    groups = []
    for strategy_id, group in frame.groupby("strategy_id", sort=True):
        groups.append(
            {
                "bucket": f"strategy:{strategy_id}",
                "count": len(group),
                "items": [{"asset_id": str(asset_id)} for asset_id in group["asset_id"].astype(str).tolist()],
            }
        )
    group_check = evaluate_review_queue_groups({"trade_date": trade_date, "groups": groups}, trade_date=trade_date)
    metrics = {"row_count": len(frame), "path": str(path), **group_check.metrics, **score_check.metrics}
    if score_check.status == RepairStatus.SUCCESS and group_check.status == RepairStatus.SUCCESS:
        return RepairCheckResult("review_queue", RepairStatus.SUCCESS, "ready", metrics)
    return RepairCheckResult("review_queue", RepairStatus.FAILED, f"{score_check.message}; {group_check.message}", metrics, blocker=True)


def check_strategy_score_audit(
    trade_date: str,
    *,
    summary_loader: Callable[[str], dict[str, Any]] | None = None,
) -> RepairCheckResult:
    if summary_loader is None:
        from stock_research.strategy_eod_publish import load_strategy_score_audit_summary

        summary_loader = lambda trade_date: load_strategy_score_audit_summary(trade_date=trade_date)
    try:
        summary = dict(summary_loader(trade_date))
    except FileNotFoundError as exc:
        return RepairCheckResult(
            "strategy_score_audit",
            RepairStatus.FAILED,
            str(exc),
            {"missing": True},
            blocker=True,
        )
    anomaly_counts = {
        str(key): int(value or 0)
        for key, value in dict(summary.get("anomaly_counts_by_type") or {}).items()
    }
    anomaly_row_count = int(summary.get("anomaly_row_count") or 0)
    metrics = {
        "status": str(summary.get("status") or ""),
        "trade_date": str(summary.get("trade_date") or ""),
        "anomaly_row_count": anomaly_row_count,
        "anomaly_counts_by_type": anomaly_counts,
    }
    if metrics["trade_date"] and metrics["trade_date"] != trade_date:
        return RepairCheckResult("strategy_score_audit", RepairStatus.FAILED, "strategy score audit stale", metrics, blocker=True)
    if anomaly_row_count > 0:
        return RepairCheckResult("strategy_score_audit", RepairStatus.FAILED, "strategy score audit anomalies", metrics, blocker=True)
    return RepairCheckResult("strategy_score_audit", RepairStatus.SUCCESS, "ready", metrics)


def _manifest_module_check(
    trade_date: str,
    *,
    module: str,
    name: str,
    min_rows: int = 1,
    manifest_loader=load_recent_data_run_manifest,
    blocker: bool = True,
) -> RepairCheckResult:
    rows = [dict(row) for row in manifest_loader(trade_date=trade_date)]
    candidates = [row for row in rows if row.get("module") == module]
    row = candidates[0] if candidates else {}
    row_count = int(row.get("row_count") or 0)
    latest_trade_date = str(row.get("latest_trade_date") or "")
    status_text = str(row.get("status") or "")
    metrics = {"module": module, "status": status_text, "row_count": row_count, "latest_trade_date": latest_trade_date}
    if status_text == "success" and row_count >= min_rows and latest_trade_date == trade_date:
        return RepairCheckResult(name, RepairStatus.SUCCESS, "ready", metrics)
    return RepairCheckResult(name, RepairStatus.FAILED, f"{module} incomplete", metrics, blocker=blocker)


def check_reports(trade_date: str, *, manifest_loader=load_recent_data_run_manifest) -> RepairCheckResult:
    generated = _manifest_module_check(
        trade_date,
        module="generated_reports",
        name="reports",
        manifest_loader=manifest_loader,
        blocker=False,
    )
    research = _manifest_module_check(
        trade_date,
        module="research_reports",
        name="reports",
        min_rows=1,
        manifest_loader=manifest_loader,
        blocker=False,
    )
    metrics = {"generated_reports": generated.metrics, "research_reports": research.metrics}
    if generated.status == RepairStatus.SUCCESS:
        status = RepairStatus.SUCCESS if research.status == RepairStatus.SUCCESS else RepairStatus.DEGRADED
        return RepairCheckResult("reports", status, "ready", metrics)
    return RepairCheckResult("reports", RepairStatus.FAILED, "generated reports missing", metrics, blocker=False)


def check_review_evidence_snapshots(trade_date: str, *, manifest_loader=load_recent_data_run_manifest) -> RepairCheckResult:
    return _manifest_module_check(
        trade_date,
        module="review_evidence_snapshots",
        name="review_evidence_snapshots",
        manifest_loader=manifest_loader,
        blocker=False,
    )


def check_ops_health(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    sql = """
        SELECT pipeline_status,
               latest_ready_trade_date::text AS latest_ready_trade_date
        FROM ops.daily_pipeline_status
        WHERE trade_date = %s
        ORDER BY updated_at DESC
        LIMIT 1
    """
    row = _fetch_one(fetcher, sql, [trade_date])
    pipeline_status = str(row.get("pipeline_status") or "")
    latest_ready = str(row.get("latest_ready_trade_date") or "")
    metrics = {"pipeline_status": pipeline_status, "latest_ready_trade_date": latest_ready}
    if latest_ready == trade_date and pipeline_status in {"READY", "ready", "success"}:
        return RepairCheckResult("ops_health", RepairStatus.SUCCESS, "ready", metrics)
    if latest_ready == trade_date and pipeline_status in {"DEGRADED_READY", "degraded_ready"}:
        return RepairCheckResult("ops_health", RepairStatus.DEGRADED, "degraded ready", metrics)
    return RepairCheckResult("ops_health", RepairStatus.FAILED, "ops health not ready", metrics, blocker=True)


def check_dashboard_surface_freshness(
    trade_date: str,
    *,
    readiness_loader: Callable[[str], dict[str, Any]] | None = None,
    ops_snapshot_loader: Callable[[str], dict[str, Any]] | None = None,
    score_audit_loader: Callable[[str], dict[str, Any]] | None = None,
    strategies_loader: Callable[[], list[dict[str, Any]]] | None = None,
) -> RepairCheckResult:
    if readiness_loader is None:
        from stock_research.dashboard.readiness import build_platform_readiness

        readiness_loader = lambda trade_date: build_platform_readiness()
    if ops_snapshot_loader is None:
        from datetime import date

        from stock_research.dashboard.ops_snapshot import build_internal_ops_snapshot

        ops_snapshot_loader = lambda trade_date: build_internal_ops_snapshot(trade_date=date.fromisoformat(trade_date))
    if score_audit_loader is None:
        from stock_research.dashboard.strategy_score_audit import load_strategy_score_audit_payload

        score_audit_loader = lambda trade_date: load_strategy_score_audit_payload(trade_date=trade_date)
    if strategies_loader is None:
        from stock_research.dashboard.backtests import list_backtest_strategies

        strategies_loader = list_backtest_strategies

    issues: list[str] = []
    degraded_issues: list[str] = []
    readiness = dict(readiness_loader(trade_date))
    readiness_status = str(readiness.get("status") or "")
    readiness_latest_trade_date = str(readiness.get("latest_trade_date") or "")
    readiness_latest_market_date = str(readiness.get("latest_market_date") or "")
    readiness_advanced_past_trade_date = _date_text_after(
        readiness_latest_trade_date,
        trade_date,
    ) or _date_text_after(readiness_latest_market_date, trade_date)
    for key in ("display_trade_date", "latest_trade_date", "latest_market_date"):
        value = str(readiness.get(key) or "")
        if value and value != trade_date:
            issue = f"readiness:{key}={value}"
            if (
                readiness_advanced_past_trade_date
                or (
                    key == "display_trade_date"
                    and readiness_status in {"OK", "PARTIAL", "ready", "degraded_ready"}
                    and readiness_latest_trade_date == trade_date
                    and readiness_latest_market_date == trade_date
                )
            ):
                degraded_issues.append(issue)
            else:
                issues.append(issue)
    for group in list(readiness.get("health_groups") or []):
        if not isinstance(group, dict):
            continue
        for item in list(group.get("items") or []):
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "")
            if status in {"missing_data", "unknown", "stale"}:
                issue = f"readiness:{item.get('key')}:{status}"
                if readiness_advanced_past_trade_date:
                    degraded_issues.append(issue)
                else:
                    issues.append(issue)

    ops_snapshot = dict(ops_snapshot_loader(trade_date))
    run_window = ops_snapshot.get("run_window") if isinstance(ops_snapshot.get("run_window"), dict) else {}
    for key in ("requested_trade_date", "status_trade_date"):
        value = str(run_window.get(key) or "")
        if value and value != trade_date:
            issues.append(f"ops_snapshot:{key}={value}")
    ops_readiness = ops_snapshot.get("readiness") if isinstance(ops_snapshot.get("readiness"), dict) else {}
    if str(ops_readiness.get("ready_status") or "") not in {"ready", "degraded_ready"}:
        issues.append(f"ops_snapshot:ready_status={ops_readiness.get('ready_status')}")
    blocking_issue_count = int(ops_readiness.get("blocking_issue_count") or 0)
    if blocking_issue_count > 0:
        degraded_issues.append(f"ops_snapshot:blocking_issue_count={blocking_issue_count}")

    score_audit = dict(score_audit_loader(trade_date))
    anomaly_row_count = int(score_audit.get("anomaly_row_count") or 0)
    if anomaly_row_count > 0:
        issues.append(f"strategy_score_audit:anomaly_row_count={anomaly_row_count}")

    for strategy in strategies_loader():
        strategy_id = str(strategy.get("strategy_id") or "")
        metrics = strategy.get("latest_metrics") if isinstance(strategy.get("latest_metrics"), dict) else {}
        signal_date = str(metrics.get("signal_as_of_date") or metrics.get("as_of_date") or "")
        if signal_date and signal_date != trade_date:
            issues.append(f"backtests:{strategy_id}:signal_as_of_date={signal_date}")
        if str(metrics.get("performance_status") or "") == "stale":
            issues.append(f"backtests:{strategy_id}:performance_stale:{metrics.get('performance_as_of_date') or metrics.get('as_of_date')}")

    metrics = {
        "issues": issues,
        "degraded_issues": degraded_issues,
        "issue_count": len(issues),
        "degraded_issue_count": len(degraded_issues),
    }
    if issues:
        return RepairCheckResult("dashboard_surface_freshness", RepairStatus.FAILED, "dashboard surface stale", metrics, blocker=True)
    if degraded_issues:
        return RepairCheckResult("dashboard_surface_freshness", RepairStatus.DEGRADED, "dashboard surface degraded", metrics)
    return RepairCheckResult("dashboard_surface_freshness", RepairStatus.SUCCESS, "ready", metrics)


def evaluate_review_queue_groups(payload: dict[str, object], *, trade_date: str) -> RepairCheckResult:
    payload_trade_date = str(payload.get("trade_date") or "")
    groups = list(payload.get("groups") or [])
    by_bucket = {str(group.get("bucket") or ""): dict(group) for group in groups if isinstance(group, dict)}
    required = ["strategy:lhb_shortline", "strategy:mid_trend", "strategy:tech_bottleneck"]
    missing = [bucket for bucket in required if bucket not in by_bucket]
    counts = {bucket: int((by_bucket.get(bucket) or {}).get("count") or 0) for bucket in required}
    assets = {
        bucket: [str(item.get("asset_id") or "") for item in (by_bucket.get(bucket) or {}).get("items", [])]
        for bucket in required
    }
    failures = []
    if payload_trade_date != trade_date:
        failures.append(f"trade_date={payload_trade_date}")
    if missing:
        failures.append(f"missing={missing}")
    if counts.get("strategy:tech_bottleneck", 0) < 1:
        failures.append("tech_bottleneck count is zero")
    if assets.get("strategy:lhb_shortline") and assets.get("strategy:lhb_shortline") == assets.get("strategy:mid_trend"):
        failures.append("lhb_shortline and mid_trend assets are identical")
    metrics = {"counts": counts, "missing": missing}
    if failures:
        return RepairCheckResult("review_queue_groups", RepairStatus.FAILED, "; ".join(failures), metrics, blocker=True)
    return RepairCheckResult("review_queue_groups", RepairStatus.SUCCESS, "ready", metrics)


def evaluate_strategy_review_scores(rows: list[dict[str, object]], *, trade_date: str) -> RepairCheckResult:
    null_rows = [
        row
        for row in rows
        if str(row.get("trade_date") or trade_date) == trade_date
        and str(row.get("strategy_id") or "") in {"lhb_shortline", "mid_trend", "tech_bottleneck"}
        and row.get("score_total") in {None, ""}
    ]
    metrics = {"row_count": len(rows), "null_score_rows": len(null_rows)}
    if null_rows:
        return RepairCheckResult("strategy_review_scores", RepairStatus.FAILED, "strategy review has null scores", metrics, blocker=True)
    return RepairCheckResult("strategy_review_scores", RepairStatus.SUCCESS, "ready", metrics)


def _not_implemented_check(name: str) -> RepairCheck:
    return RepairCheck(
        name=name,
        run=lambda: RepairCheckResult(name=name, status=RepairStatus.SKIPPED, message="check runner not wired"),
    )


def build_check_plan(trade_date: str) -> list[RepairCheck]:
    return [
        RepairCheck("daily_bars", lambda: check_daily_bars(trade_date)),
        RepairCheck("minute5_bars", lambda: check_minute5_bars(trade_date)),
        RepairCheck("lhb_source", lambda: check_lhb_source(trade_date)),
        RepairCheck("lhb_features", lambda: check_lhb_features(trade_date)),
        RepairCheck("technical_features", lambda: check_technical_features(trade_date)),
        RepairCheck("factor_daily", lambda: check_factor_daily(trade_date)),
        RepairCheck("score_topn", lambda: check_score_topn(trade_date)),
        RepairCheck("watchlist", lambda: check_watchlist(trade_date)),
        RepairCheck("market_monitor", lambda: check_market_monitor(trade_date)),
        RepairCheck("strategy_publish", lambda: check_strategy_publish(trade_date)),
        RepairCheck("review_queue", lambda: check_review_queue(trade_date)),
        RepairCheck("strategy_score_audit", lambda: check_strategy_score_audit(trade_date)),
        RepairCheck("reports", lambda: check_reports(trade_date)),
        RepairCheck("review_evidence_snapshots", lambda: check_review_evidence_snapshots(trade_date)),
        RepairCheck("dashboard_browser_acceptance", lambda: check_dashboard_browser_acceptance(trade_date)),
        RepairCheck("dashboard_surface_freshness", lambda: check_dashboard_surface_freshness(trade_date)),
        RepairCheck("ops_health", lambda: check_ops_health(trade_date)),
    ]
