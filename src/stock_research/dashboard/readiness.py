from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.config import SETTINGS
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import DEFAULT_REPORTS_DIR
from stock_research.db import connect, fetch_all


REPORT_SUFFIXES = {".html", ".md", ".json", ".csv"}


CHECK_LABELS = {
    "platform_summary": "Platform Summary",
    "review_queue": "Review Queue",
    "news": "News",
    "research_reports": "Research Reports",
    "generated_reports": "Generated Reports",
}

UNAVAILABLE_WARNINGS = {
    "platform_summary": "Platform summary unavailable",
    "topn_preview": "TopN preview unavailable",
    "review_queue": "Review Queue unavailable",
    "news": "News unavailable",
    "research_reports": "Research Reports unavailable",
    "generated_reports": "Generated Reports unavailable",
}


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
    except Exception:
        platform_summary = {}
        warnings.append(UNAVAILABLE_WARNINGS["platform_summary"])

    latest_market_date = str(platform_summary.get("latest_market_date") or "")
    topn_preview = list(platform_summary.get("topn_preview") or [])
    if not platform_summary:
        checks.append(
            _check("platform_summary", "missing_data", UNAVAILABLE_WARNINGS["platform_summary"])
        )
    elif not latest_market_date:
        checks.append(
            _check("platform_summary", "missing_data", UNAVAILABLE_WARNINGS["platform_summary"])
        )
        warnings.append(UNAVAILABLE_WARNINGS["platform_summary"])
    elif not topn_preview:
        checks.append(
            _check("platform_summary", "missing_data", UNAVAILABLE_WARNINGS["topn_preview"])
        )
        warnings.append(UNAVAILABLE_WARNINGS["topn_preview"])
    else:
        checks.append(_check("platform_summary", "ready", "Platform summary available"))

    if latest_market_date:
        checks.append(_review_queue_check(topn_preview, warnings))
        checks.append(_news_check(warnings))
        checks.append(_research_reports_check(warnings))
        checks.append(_generated_reports_check(latest_market_date, warnings))
    else:
        checks.extend(
            [
                _check("review_queue", "unknown", "Latest market date unavailable"),
                _check("news", "unknown", "Latest market date unavailable"),
                _check("research_reports", "unknown", "Latest market date unavailable"),
                _check("generated_reports", "unknown", "Latest market date unavailable"),
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


def _review_queue_check(topn_preview: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    if not topn_preview:
        warnings.append(UNAVAILABLE_WARNINGS["review_queue"])
        return _check("review_queue", "partial", UNAVAILABLE_WARNINGS["review_queue"])
    return _check("review_queue", "ready", "Review Queue available")


def _news_check(warnings: list[str]) -> dict[str, Any]:
    try:
        has_news = _has_public_news()
    except Exception:
        warnings.append(UNAVAILABLE_WARNINGS["news"])
        return _check("news", "partial", UNAVAILABLE_WARNINGS["news"])

    if not has_news:
        warnings.append(UNAVAILABLE_WARNINGS["news"])
        return _check("news", "partial", UNAVAILABLE_WARNINGS["news"])
    return _check("news", "ready", "News available")


def _research_reports_check(warnings: list[str]) -> dict[str, Any]:
    try:
        has_reports = _has_research_reports()
    except Exception:
        warnings.append(UNAVAILABLE_WARNINGS["research_reports"])
        return _check("research_reports", "partial", UNAVAILABLE_WARNINGS["research_reports"])

    if not has_reports:
        warnings.append(UNAVAILABLE_WARNINGS["research_reports"])
        return _check(
            "research_reports",
            "partial",
            UNAVAILABLE_WARNINGS["research_reports"],
        )
    return _check("research_reports", "ready", "Research Reports available")


def _generated_reports_check(latest_market_date: str, warnings: list[str]) -> dict[str, Any]:
    try:
        has_reports = _has_generated_reports(latest_market_date)
    except Exception:
        warnings.append(UNAVAILABLE_WARNINGS["generated_reports"])
        return _check("generated_reports", "partial", UNAVAILABLE_WARNINGS["generated_reports"])

    if not has_reports:
        warnings.append(UNAVAILABLE_WARNINGS["generated_reports"])
        return _check("generated_reports", "partial", UNAVAILABLE_WARNINGS["generated_reports"])
    return _check("generated_reports", "ready", "Generated Reports available")


def _has_public_news(service: str = SETTINGS.research_service) -> bool:
    with connect(service) as conn:
        return bool(fetch_all(conn, "SELECT 1 FROM research.news_event_source LIMIT 1"))


def _has_research_reports(service: str = SETTINGS.research_service) -> bool:
    with connect(service) as conn:
        return bool(fetch_all(conn, "SELECT 1 FROM research.stock_report_source LIMIT 1"))


def _has_generated_reports(
    latest_market_date: str,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> bool:
    directory = Path(reports_dir)
    if not directory.exists() or not directory.is_dir():
        return False
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in REPORT_SUFFIXES:
            continue
        if latest_market_date in path.name:
            return True
    return False


def _check(key: str, status: str, detail: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": CHECK_LABELS[key],
        "status": status,
        "detail": detail,
    }


def _dedupe(warnings: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        deduped.append(warning)
    return deduped
