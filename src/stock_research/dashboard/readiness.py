from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.dashboard.news import load_public_news_for_dashboard
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.research_reports import load_research_report_summary
from stock_research.dashboard.review_queue import build_review_queue


def aggregate_readiness_status(checks: list[dict[str, Any]]) -> str:
    statuses = [str(check.get("status") or "unknown") for check in checks]
    if "missing_data" in statuses:
        return "missing_data"
    if any(status in {"partial", "unknown"} for status in statuses):
        return "partial"
    return "ready"


def build_platform_readiness(score_version: str = "manual_v1") -> dict[str, Any]:
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    latest_market_date = ""

    try:
        platform_summary = load_platform_summary(score_version=score_version, top_n=5)
    except Exception as exc:
        platform_summary = {}
        warnings.append(f"platform_summary: {exc}")

    latest_market_date = str(platform_summary.get("latest_market_date") or "")
    topn_preview = list(platform_summary.get("topn_preview") or [])
    if not platform_summary:
        checks.append(
            {
                "name": "platform_summary",
                "status": "missing_data",
                "message": "platform summary unavailable",
            }
        )
    elif not latest_market_date:
        warning = "platform_summary: missing latest market date"
        checks.append(
            {
                "name": "platform_summary",
                "status": "missing_data",
                "message": warning.removeprefix("platform_summary: "),
            }
        )
        warnings.append(warning)
    elif not topn_preview:
        warning = f"platform_summary: no top scores available for {latest_market_date}"
        checks.append(
            {
                "name": "platform_summary",
                "status": "missing_data",
                "message": warning.removeprefix("platform_summary: "),
            }
        )
        warnings.append(warning)
    else:
        checks.append(
            {
                "name": "platform_summary",
                "status": "ready",
                "message": "platform summary available",
                "count": len(topn_preview),
            }
        )

    if latest_market_date:
        checks.append(_review_queue_check(latest_market_date, score_version, warnings))
        checks.append(_news_check(warnings))
        checks.append(_research_reports_check(warnings))
        checks.append(_generated_reports_check(latest_market_date, warnings))
    else:
        checks.extend(
            [
                _unknown_check("review_queue", "latest market date unavailable"),
                _unknown_check("news", "latest market date unavailable"),
                _unknown_check("research_reports", "latest market date unavailable"),
                _unknown_check("generated_reports", "latest market date unavailable"),
            ]
        )

    return {
        "mode": "eod_local",
        "status": aggregate_readiness_status(checks),
        "as_of": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "latest_market_date": latest_market_date,
        "checks": checks,
        "warnings": _dedupe(warnings),
    }


def _review_queue_check(
    latest_market_date: str,
    score_version: str,
    warnings: list[str],
) -> dict[str, Any]:
    try:
        payload = build_review_queue(
            trade_date=latest_market_date,
            score_version=score_version,
            limit=5,
            lookback_days=90,
        )
    except Exception as exc:
        warnings.append(f"review_queue: {exc}")
        return {"name": "review_queue", "status": "partial", "message": str(exc)}

    source_warnings = [str(warning) for warning in payload.get("warnings") or [] if warning]
    for warning in source_warnings:
        warnings.append(f"review_queue: {warning}")
    item_count = _review_queue_item_count(payload)
    if item_count == 0:
        if not source_warnings:
            warnings.append(f"review_queue: no review queue items available for {latest_market_date}")
        return {
            "name": "review_queue",
            "status": "partial",
            "message": "no review queue items available",
            "count": item_count,
        }
    if source_warnings:
        return {
            "name": "review_queue",
            "status": "partial",
            "message": "review queue available with warnings",
            "count": item_count,
        }
    return {
        "name": "review_queue",
        "status": "ready",
        "message": "review queue available",
        "count": item_count,
    }


def _news_check(warnings: list[str]) -> dict[str, Any]:
    try:
        payload = load_public_news_for_dashboard(limit=1, offset=0)
    except Exception as exc:
        warnings.append(f"news: {exc}")
        return {"name": "news", "status": "partial", "message": str(exc)}

    source_warnings = [str(warning) for warning in payload.get("warnings") or [] if warning]
    for warning in source_warnings:
        warnings.append(f"news: {warning}")
    items = list(payload.get("items") or [])
    if not items:
        if not source_warnings:
            warnings.append("news: no public news available")
        return {
            "name": "news",
            "status": "partial",
            "message": "no public news available",
            "count": 0,
        }
    if source_warnings:
        return {
            "name": "news",
            "status": "partial",
            "message": "public news available with warnings",
            "count": len(items),
        }
    return {
        "name": "news",
        "status": "ready",
        "message": "public news available",
        "count": len(items),
    }


def _research_reports_check(warnings: list[str]) -> dict[str, Any]:
    try:
        payload = load_research_report_summary()
    except Exception as exc:
        warnings.append(f"research_reports: {exc}")
        return {"name": "research_reports", "status": "partial", "message": str(exc)}

    total_reports = int(payload.get("total_reports") or 0)
    if total_reports == 0:
        warnings.append("research_reports: no research reports available")
        return {
            "name": "research_reports",
            "status": "partial",
            "message": "no research reports available",
            "count": total_reports,
        }
    return {
        "name": "research_reports",
        "status": "ready",
        "message": "research reports available",
        "count": total_reports,
    }


def _generated_reports_check(latest_market_date: str, warnings: list[str]) -> dict[str, Any]:
    try:
        links = load_report_links(latest_market_date)
    except Exception as exc:
        warnings.append(f"generated_reports: {exc}")
        return {"name": "generated_reports", "status": "partial", "message": str(exc)}

    if not links:
        warnings.append(f"generated_reports: no generated reports available for {latest_market_date}")
        return {
            "name": "generated_reports",
            "status": "partial",
            "message": "no generated reports available",
            "count": 0,
        }
    return {
        "name": "generated_reports",
        "status": "ready",
        "message": "generated reports available",
        "count": len(links),
    }


def _review_queue_item_count(payload: dict[str, Any]) -> int:
    count = 0
    for group in payload.get("groups") or []:
        count += len(group.get("items") or [])
    return count


def _unknown_check(name: str, message: str) -> dict[str, Any]:
    return {"name": name, "status": "unknown", "message": message}


def _dedupe(warnings: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        deduped.append(warning)
    return deduped
