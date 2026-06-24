from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.config import SETTINGS
from stock_research.daily_close_pipeline import load_data_status_for_dashboard
from stock_research.daily_health import summarize_operational_health
from stock_research.db import connect, fetch_all
from stock_research.intraday_pipeline import load_intraday_status


_PENDING_STATUSES = {"pending", "skipped", "not_started"}
_ACTIVE_STATUSES = {"running", "success", "partial_success", "failed"}
_READY_PIPELINE_STATUSES = {"READY", "DEGRADED_READY"}


def build_internal_ops_snapshot(
    service: str = SETTINGS.research_service,
    trade_date: date | None = None,
) -> dict[str, Any]:
    target_date = trade_date or date.today()
    data_status = load_data_status_for_dashboard(service, current_trade_date=target_date)
    intraday = load_intraday_status(service, target_date)
    health = summarize_operational_health(trade_date=target_date.isoformat(), service=service)
    stages = load_ops_stage_details(service, target_date)
    now_text = _now_in_timezone("Asia/Shanghai")

    run_window = _build_run_window(target_date, data_status, stages, now_text)
    pipeline = _build_pipeline_summary(data_status, stages, now_text)
    health_block = _build_health_summary(health, data_status, stages, now_text)
    readiness = _build_readiness(data_status, health_block, pipeline)
    intervention = _build_intervention(run_window, pipeline, health_block, readiness)

    return {
        "run_window": run_window,
        "pipeline": pipeline,
        "health": health_block,
        "intervention": intervention,
        "readiness": readiness,
        "snapshot_preview": {
            "market_state": _market_state_preview(intraday),
            "topn_preview": [],
            "coverage_summary": {
                "pipeline_status": data_status.get("pipeline_status"),
                "failed_jobs": len(data_status.get("failed_jobs") or []),
                "warnings": data_status.get("warnings") or [],
            },
            "factor_gate_summary": {},
            "published_at": data_status.get("last_updated_at"),
        },
    }


def build_public_snapshot(
    service: str = SETTINGS.research_service,
    trade_date: date | None = None,
) -> dict[str, Any]:
    internal = build_internal_ops_snapshot(service=service, trade_date=trade_date)
    readiness = internal["readiness"]
    preview = internal["snapshot_preview"]
    status = _public_status_from_internal(internal)
    latest_ready_trade_date = readiness.get("latest_ready_trade_date")
    return {
        "trade_date": (trade_date or date.today()).isoformat(),
        "published_at": preview.get("published_at"),
        "latest_ready_trade_date": latest_ready_trade_date,
        "status": status,
        "status_text": _public_status_text(status, latest_ready_trade_date),
        "market_state": preview.get("market_state"),
        "topn_preview": preview.get("topn_preview"),
        "coverage_summary": preview.get("coverage_summary"),
        "factor_gate_summary": preview.get("factor_gate_summary"),
        "notes": [],
    }


def load_ops_stage_details(service: str, trade_date: date | None = None) -> list[dict[str, Any]]:
    sql = """
    SELECT stage, status, started_at, updated_at, error_summary
    FROM ops.daily_pipeline_job
    WHERE (%s IS NULL OR trade_date = %s)
    ORDER BY stage, job_name, source
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, trade_date])
    return [
        {
            "stage": row.get("stage"),
            "status": row.get("status"),
            "started_at": row.get("started_at").isoformat() if row.get("started_at") else None,
            "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
            "error_summary": row.get("error_summary"),
        }
        for row in rows
    ]


def _build_run_window(
    trade_date: date,
    data_status: dict[str, Any],
    stages: list[dict[str, Any]],
    now_text: str,
) -> dict[str, Any]:
    latest_update = data_status.get("last_updated_at")
    return {
        "trade_date": trade_date.isoformat(),
        "current_trade_date": data_status.get("current_trade_date"),
        "latest_ready_trade_date": data_status.get("latest_ready_trade_date"),
        "last_updated_at": latest_update,
        "now": now_text,
        "stage_count": len(stages),
    }


def _build_pipeline_summary(
    data_status: dict[str, Any],
    stages: list[dict[str, Any]],
    now_text: str,
) -> dict[str, Any]:
    pipeline_status = str(data_status.get("pipeline_status") or "NOT_READY")
    stage_statuses = [str(item.get("status") or "") for item in stages]
    pipeline_inputs = [
        str(data_status.get("daily_status") or ""),
        str(data_status.get("minute5_status") or ""),
        str(data_status.get("deps_status") or ""),
        *stage_statuses,
    ]
    if pipeline_status in _READY_PIPELINE_STATUSES:
        overall_status = "ready" if pipeline_status == "READY" else "degraded"
    elif all(_normalize_status(status) in _PENDING_STATUSES for status in pipeline_inputs):
        overall_status = "not_started"
    elif any(_normalize_status(status) == "failed" for status in pipeline_inputs):
        overall_status = "blocked"
    elif any(_normalize_status(status) in _ACTIVE_STATUSES for status in pipeline_inputs):
        overall_status = "delayed"
    else:
        overall_status = "delayed"

    return {
        "overall_status": overall_status,
        "pipeline_status": pipeline_status,
        "daily_status": data_status.get("daily_status"),
        "minute5_status": data_status.get("minute5_status"),
        "deps_status": data_status.get("deps_status"),
        "latest_ready_trade_date": data_status.get("latest_ready_trade_date"),
        "last_updated_at": data_status.get("last_updated_at"),
        "evaluated_at": now_text,
        "stage_statuses": stage_statuses,
    }


def _build_health_summary(
    health: dict[str, Any],
    data_status: dict[str, Any],
    stages: list[dict[str, Any]],
    now_text: str,
) -> dict[str, Any]:
    stalled = _is_stalled(stages, now_text)
    last_error_summary = health.get("last_error_summary")
    if not last_error_summary:
        last_error_summary = _latest_error_summary(stages) or _latest_failed_job_summary(data_status)
    return {
        **health,
        "stalled": stalled,
        "last_error_summary": last_error_summary,
    }


def _build_readiness(
    data_status: dict[str, Any],
    health_block: dict[str, Any],
    pipeline: dict[str, Any],
) -> dict[str, Any]:
    pipeline_status = str(data_status.get("pipeline_status") or "NOT_READY")
    latest_ready_trade_date = data_status.get("latest_ready_trade_date")
    failed_jobs = data_status.get("failed_jobs") or []
    blocking_issue_count = len(failed_jobs)
    if health_block.get("stalled"):
        blocking_issue_count += 1
    if pipeline.get("overall_status") in {"blocked", "not_started"}:
        blocking_issue_count += 1
    ready_for_dashboard = pipeline_status in _READY_PIPELINE_STATUSES
    ready_for_publication = ready_for_dashboard and blocking_issue_count == 0
    if pipeline_status == "READY":
        ready_status = "ready"
    elif pipeline_status == "DEGRADED_READY":
        ready_status = "degraded_ready"
    elif ready_for_dashboard:
        ready_status = "degraded_ready" if blocking_issue_count else "ready"
    else:
        ready_status = "not_ready"
    return {
        "latest_ready_trade_date": latest_ready_trade_date,
        "ready_status": ready_status,
        "ready_for_dashboard": ready_for_dashboard,
        "ready_for_publication": ready_for_publication,
        "blocking_issue_count": blocking_issue_count,
    }


def _build_intervention(
    run_window: dict[str, Any],
    pipeline: dict[str, Any],
    health_block: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    pipeline_status = pipeline["overall_status"]
    if pipeline_status == "not_started":
        return {
            "needs_intervention": True,
            "severity": "critical",
            "reason_code": "not_started",
            "reason_text": "the pipeline has not started yet",
            "suggested_action": "start or rerun the daily pipeline",
        }
    if pipeline_status == "blocked":
        return {
            "needs_intervention": True,
            "severity": "critical",
            "reason_code": "blocked",
            "reason_text": "the pipeline hit a blocking failure",
            "suggested_action": "investigate failed jobs",
        }
    if pipeline_status == "delayed":
        if health_block.get("stalled"):
            return {
                "needs_intervention": True,
                "severity": "critical",
                "reason_code": "stalled",
                "reason_text": "the pipeline is stalled",
                "suggested_action": "check watchdog and resume the blocked stage",
            }
        return {
            "needs_intervention": True,
            "severity": "warning",
            "reason_code": "deadline_risk",
            "reason_text": "the pipeline is progressing but still behind schedule",
            "suggested_action": "check watchdog",
        }
    if readiness.get("ready_for_publication"):
        return {
            "needs_intervention": False,
            "severity": "info",
            "reason_code": "ready",
            "reason_text": "the pipeline is ready for publication",
            "suggested_action": None,
        }
    return {
        "needs_intervention": False,
        "severity": "info",
        "reason_code": "monitor",
        "reason_text": "the pipeline is healthy enough to monitor",
        "suggested_action": None,
    }


def _market_state_preview(intraday: dict[str, Any]) -> dict[str, Any]:
    market_sentiment = intraday.get("market_sentiment") or {}
    if isinstance(market_sentiment, dict):
        return {
            "state": market_sentiment.get("sentiment_state"),
            "score": market_sentiment.get("sentiment_score"),
        }
    return {"state": None, "score": None}


def _public_status_from_internal(internal: dict[str, Any]) -> str:
    pipeline_status = str(internal.get("pipeline", {}).get("overall_status") or "unknown")
    return pipeline_status


def _public_status_text(status: str, latest_ready_trade_date: str | None) -> str:
    if latest_ready_trade_date:
        return f"{status} (latest ready: {latest_ready_trade_date})"
    return status


def _latest_error_summary(stages: list[dict[str, Any]]) -> str | None:
    for stage in reversed(stages):
        error_summary = stage.get("error_summary")
        if error_summary:
            return str(error_summary)
    return None


def _latest_failed_job_summary(data_status: dict[str, Any]) -> str | None:
    failed_jobs = data_status.get("failed_jobs") or []
    if not failed_jobs:
        return None
    first = failed_jobs[0]
    if isinstance(first, dict):
        return str(first.get("error_summary") or first.get("error") or first.get("message") or "")
    return str(first)


def _is_stalled(stages: list[dict[str, Any]], now_text: str) -> bool:
    now = _parse_iso_datetime(now_text)
    if now is None:
        return False
    for stage in stages:
        status = _normalize_status(stage.get("status"))
        if status != "running":
            continue
        updated_at = _parse_iso_datetime(stage.get("updated_at"))
        started_at = _parse_iso_datetime(stage.get("started_at"))
        reference = updated_at or started_at
        if reference is None:
            continue
        age_minutes = (now - reference).total_seconds() / 60.0
        if age_minutes >= 20:
            return True
    return False


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _now_in_timezone(tz_name: str) -> str:
    return datetime.now(ZoneInfo(tz_name)).isoformat(timespec="seconds")
