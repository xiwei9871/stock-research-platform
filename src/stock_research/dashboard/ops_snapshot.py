from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.config import SETTINGS
from stock_research.daily_health import summarize_operational_health
from stock_research.db import connect, fetch_all

try:
    from stock_research.intraday_pipeline import load_intraday_status
except ImportError:
    def load_intraday_status(service: str, run_date: date) -> dict[str, Any]:
        return {}


_PENDING_STATUSES = {"pending", "skipped", "not_started"}
_ACTIVE_STATUSES = {"running", "success", "partial_success", "failed"}
_PUBLIC_COVERAGE_SUMMARY_KEYS = ("core",)
_PUBLIC_MARKET_STATE_KEYS = ("state", "score")
_PUBLIC_TOPN_PREVIEW_KEYS = ("asset_id", "stock_name", "score_total")
_PUBLIC_FACTOR_GATE_SUMMARY_KEYS = ("approved_count",)


def build_internal_ops_snapshot(
    service: str = SETTINGS.research_service,
    trade_date: date | None = None,
) -> dict[str, Any]:
    target_date = trade_date or date.today()
    status_context = _load_pipeline_status_context(service, target_date)
    data_status = status_context["data_status"]
    intraday = load_intraday_status(service, target_date)
    health = summarize_operational_health(trade_date=target_date.isoformat(), service=service)
    stages = load_ops_stage_details(service, target_date)
    now_text = _now_in_timezone("Asia/Shanghai")

    run_window = _build_run_window(target_date, status_context, stages, now_text)
    pipeline = _build_pipeline_summary(data_status, stages, now_text, status_context)
    health_block = _build_health_summary(health, data_status, stages, now_text)
    readiness = _build_readiness(data_status, health_block, pipeline, status_context)
    intervention = _build_intervention(pipeline, health_block, readiness)

    return {
        "run_window": run_window,
        "pipeline": pipeline,
        "health": health_block,
        "intervention": intervention,
        "readiness": readiness,
        "snapshot_preview": {
            "market_state": _market_state_preview(intraday),
            "topn_preview": [],
            "coverage_summary": _internal_coverage_summary(data_status),
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
    target_date = trade_date or date.today()
    status = _public_status_from_readiness(readiness, target_date, preview)
    latest_ready_trade_date = readiness.get("latest_ready_trade_date")
    return {
        "trade_date": target_date.isoformat(),
        "published_at": preview.get("published_at"),
        "latest_ready_trade_date": latest_ready_trade_date,
        "status": status,
        "status_text": _public_status_text(status, latest_ready_trade_date),
        "market_state": _public_market_state(preview.get("market_state")),
        "topn_preview": _public_topn_preview(preview.get("topn_preview")),
        "coverage_summary": _public_coverage_summary(preview.get("coverage_summary") or {}),
        "factor_gate_summary": _public_factor_gate_summary(preview.get("factor_gate_summary")),
        "notes": [],
    }


def load_ops_stage_details(
    service: str = SETTINGS.research_service,
    trade_date: date | None = None,
) -> list[dict[str, Any]]:
    resolved_trade_date = trade_date or _latest_ops_stage_trade_date(service)
    if resolved_trade_date is None:
        return []
    sql = """
    SELECT stage, status, started_at, updated_at, error_summary
    FROM ops.daily_pipeline_job
    WHERE trade_date = %s
    ORDER BY stage, job_name, source
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [resolved_trade_date])
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


def _load_pipeline_status_context(service: str, trade_date: date) -> dict[str, Any]:
    requested_row = _fetch_pipeline_status_row(service, trade_date)
    latest_row = _fetch_latest_pipeline_status_row(service)
    active_row = requested_row or latest_row
    if active_row is None:
        data_status = {
            "latest_ready_trade_date": None,
            "current_trade_date": trade_date.isoformat(),
            "pipeline_status": "NOT_READY",
            "daily_status": "skipped",
            "minute5_status": "skipped",
            "deps_status": "skipped",
            "failed_jobs": [],
            "warnings": ["pipeline_status_not_initialized"],
            "last_updated_at": None,
        }
        return {
            "data_status": data_status,
            "requested_trade_date": trade_date.isoformat(),
            "status_trade_date": None,
            "latest_available_trade_date": None,
            "matches_requested_trade_date": False,
        }
    data_status = {
        "latest_ready_trade_date": active_row["latest_ready_trade_date"].isoformat()
        if active_row.get("latest_ready_trade_date")
        else None,
        "current_trade_date": trade_date.isoformat(),
        "pipeline_status": active_row["pipeline_status"],
        "daily_status": active_row["daily_status"],
        "minute5_status": active_row["minute5_status"],
        "deps_status": active_row["deps_status"],
        "failed_jobs": active_row["failed_jobs"] or [],
        "warnings": active_row["warnings"] or [],
        "last_updated_at": active_row["updated_at"].isoformat() if active_row.get("updated_at") else None,
    }
    return {
        "data_status": data_status,
        "requested_trade_date": trade_date.isoformat(),
        "status_trade_date": active_row["trade_date"].isoformat(),
        "latest_available_trade_date": latest_row["trade_date"].isoformat() if latest_row else active_row["trade_date"].isoformat(),
        "matches_requested_trade_date": requested_row is not None,
    }


def _build_run_window(
    trade_date: date,
    status_context: dict[str, Any],
    stages: list[dict[str, Any]],
    now_text: str,
) -> dict[str, Any]:
    data_status = status_context["data_status"]
    latest_update = data_status.get("last_updated_at")
    return {
        "requested_trade_date": status_context["requested_trade_date"],
        "trade_date": trade_date.isoformat(),
        "status_trade_date": status_context["status_trade_date"],
        "latest_available_trade_date": status_context["latest_available_trade_date"],
        "status_matches_requested_trade_date": status_context["matches_requested_trade_date"],
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
    status_context: dict[str, Any],
) -> dict[str, Any]:
    pipeline_status = str(data_status.get("pipeline_status") or "NOT_READY")
    stage_statuses = [str(item.get("status") or "") for item in stages]
    pipeline_inputs = [
        str(data_status.get("daily_status") or ""),
        str(data_status.get("minute5_status") or ""),
        str(data_status.get("deps_status") or ""),
        *stage_statuses,
    ]
    if status_context.get("matches_requested_trade_date") and pipeline_status in {"READY", "DEGRADED_READY"}:
        overall_status = "ready" if pipeline_status == "READY" else "degraded"
    elif not status_context.get("matches_requested_trade_date"):
        overall_status = "not_started" if not any(
            _normalize_status(status) in {"running", "failed", "partial_success"} for status in pipeline_inputs
        ) else "delayed"
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
    alert_count = int(health.get("alert_count") or 0)
    return {
        **health,
        "stalled": stalled,
        "last_error_summary": last_error_summary,
        "alert_count": alert_count,
        "has_alerts": str(health.get("status") or "").lower() == "alert" or alert_count > 0,
    }


def _build_readiness(
    data_status: dict[str, Any],
    health_block: dict[str, Any],
    pipeline: dict[str, Any],
    status_context: dict[str, Any],
) -> dict[str, Any]:
    pipeline_status = str(data_status.get("pipeline_status") or "NOT_READY")
    latest_ready_trade_date = data_status.get("latest_ready_trade_date")
    failed_jobs = data_status.get("failed_jobs") or []
    blocking_issue_count = len(failed_jobs)
    if health_block.get("stalled"):
        blocking_issue_count += 1
    if health_block.get("has_alerts"):
        blocking_issue_count += max(1, int(health_block.get("alert_count") or 0))
    if pipeline.get("overall_status") in {"blocked", "not_started"}:
        blocking_issue_count += 1
    ready_for_dashboard = status_context.get("matches_requested_trade_date") and pipeline_status in {"READY", "DEGRADED_READY"}
    ready_for_publication = ready_for_dashboard and blocking_issue_count == 0 and not health_block.get("has_alerts")
    if pipeline_status == "READY" and status_context.get("matches_requested_trade_date"):
        ready_status = "ready"
    elif pipeline_status == "DEGRADED_READY" and status_context.get("matches_requested_trade_date"):
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
    if health_block.get("has_alerts"):
        severity = "critical" if health_block.get("stalled") or int(health_block.get("alert_count") or 0) >= 3 else "warning"
        return {
            "needs_intervention": True,
            "severity": severity,
            "reason_code": "health_alerts",
            "reason_text": "operational health alerts require review",
            "suggested_action": "inspect health alerts and clear blockers",
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
    market_state = intraday.get("market_state")
    if isinstance(market_state, dict):
        return {
            "state": market_state.get("state"),
            "score": market_state.get("score"),
        }
    market_sentiment = intraday.get("market_sentiment") or {}
    if isinstance(market_sentiment, dict):
        return {
            "state": market_sentiment.get("sentiment_state"),
            "score": market_sentiment.get("sentiment_score"),
        }
    return {"state": None, "score": None}


def _public_status_from_readiness(
    readiness: dict[str, Any],
    trade_date: date,
    preview: dict[str, Any],
) -> str:
    latest_ready_trade_date = readiness.get("latest_ready_trade_date")
    if not latest_ready_trade_date:
        return "unavailable"
    if readiness.get("ready_for_publication") and latest_ready_trade_date == trade_date.isoformat():
        return "ready"
    if latest_ready_trade_date < trade_date.isoformat():
        return "delayed" if _public_has_release_payload(preview) else "unavailable"
    return "partial" if _public_has_release_payload(preview) else "unavailable"


def _public_status_text(status: str, latest_ready_trade_date: str | None) -> str:
    if latest_ready_trade_date:
        return f"{status} (latest ready: {latest_ready_trade_date})"
    return status


def _public_coverage_summary(coverage_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        key: coverage_summary.get(key)
        for key in _PUBLIC_COVERAGE_SUMMARY_KEYS
        if key in coverage_summary
    }


def _public_market_state(market_state: Any) -> dict[str, Any] | None:
    if not isinstance(market_state, dict):
        return None
    return {
        key: market_state.get(key)
        for key in _PUBLIC_MARKET_STATE_KEYS
        if key in market_state
    }


def _public_topn_preview(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    public_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        shaped_row = {
            key: row.get(key)
            for key in _PUBLIC_TOPN_PREVIEW_KEYS
            if key in row
        }
        if shaped_row:
            public_rows.append(shaped_row)
    return public_rows


def _public_factor_gate_summary(summary: Any) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    return {
        key: summary.get(key)
        for key in _PUBLIC_FACTOR_GATE_SUMMARY_KEYS
        if key in summary
    }


def _public_has_release_payload(preview: dict[str, Any]) -> bool:
    market_state = _public_market_state(preview.get("market_state")) or {}
    topn_preview = _public_topn_preview(preview.get("topn_preview"))
    coverage_summary = _public_coverage_summary(preview.get("coverage_summary") or {})
    factor_gate_summary = _public_factor_gate_summary(preview.get("factor_gate_summary")) or {}
    return bool(_market_state_has_signal(market_state) or topn_preview or coverage_summary or factor_gate_summary)


def _internal_coverage_summary(data_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipeline_status": data_status.get("pipeline_status"),
        "failed_jobs": len(data_status.get("failed_jobs") or []),
        "warnings": data_status.get("warnings") or [],
    }


def _fetch_pipeline_status_row(service: str, trade_date: date) -> dict[str, Any] | None:
    sql = """
    SELECT trade_date, pipeline_status, daily_status, minute5_status, deps_status,
           latest_ready_trade_date, warnings, failed_jobs, updated_at
    FROM ops.daily_pipeline_status
    WHERE trade_date = %s
    ORDER BY updated_at DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    return rows[0] if rows else None


def _fetch_latest_pipeline_status_row(service: str) -> dict[str, Any] | None:
    sql = """
    SELECT trade_date, pipeline_status, daily_status, minute5_status, deps_status,
           latest_ready_trade_date, warnings, failed_jobs, updated_at
    FROM ops.daily_pipeline_status
    ORDER BY trade_date DESC, updated_at DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    return rows[0] if rows else None


def _latest_ops_stage_trade_date(service: str) -> date | None:
    sql = """
    SELECT trade_date
    FROM ops.daily_pipeline_job
    ORDER BY trade_date DESC, updated_at DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    if not rows:
        return None
    trade_date = rows[0].get("trade_date")
    return trade_date if isinstance(trade_date, date) else None


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


def _market_state_has_signal(market_state: Any) -> bool:
    if not isinstance(market_state, dict):
        return False
    for value in market_state.values():
        if value in (None, "", [], {}):
            continue
        return True
    return False
