from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReadinessDecision:
    status: str
    ready_for_dashboard: bool
    ready_for_publication: bool
    blocking_reasons: list[str]
    warnings: list[str]


def classify_pipeline_readiness(
    row: dict[str, Any],
    *,
    requested_trade_date: str,
) -> ReadinessDecision:
    pipeline_status = str(row.get("pipeline_status") or "").upper()
    latest_ready_trade_date = str(row.get("latest_ready_trade_date") or "")[:10]
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    requested = str(requested_trade_date or "")[:10]
    date_matches = bool(requested and latest_ready_trade_date == requested)
    if not date_matches:
        blocking_reasons.append(f"latest_ready_trade_date={latest_ready_trade_date or 'missing'}")

    if pipeline_status == "DEGRADED_READY":
        warnings.append("pipeline_status=DEGRADED_READY")
        for key in ("daily_status", "minute5_status", "deps_status", "market_monitor_status"):
            if key not in row:
                continue
            value = str(row.get(key) or "")
            if value not in {"success", "skipped_optional"}:
                blocking_reasons.append(f"{key}={value or 'missing'}")
    elif pipeline_status == "READY":
        for key in ("daily_status", "minute5_status", "deps_status", "market_monitor_status"):
            if key not in row:
                continue
            value = str(row.get(key) or "")
            if value and value not in {"success", "skipped_optional"}:
                warnings.append(f"{key}={value}")
    else:
        blocking_reasons.append(f"pipeline_status={pipeline_status or 'missing'}")

    ready_for_dashboard = date_matches and pipeline_status in {"READY", "DEGRADED_READY"}
    ready_for_publication = pipeline_status == "READY" and not blocking_reasons
    status = "blocked" if not ready_for_dashboard else (
        "degraded_ready" if pipeline_status == "DEGRADED_READY" else "ready"
    )
    return ReadinessDecision(
        status=status,
        ready_for_dashboard=ready_for_dashboard,
        ready_for_publication=ready_for_publication,
        blocking_reasons=blocking_reasons,
        warnings=warnings,
    )
