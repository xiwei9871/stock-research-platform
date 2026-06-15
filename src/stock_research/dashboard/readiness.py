from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.config import SETTINGS
from stock_research.data_run_manifest import (
    load_latest_data_run_manifest,
    summarize_manifest_modules,
)
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
    if any(status in {"BLOCKED", "missing_data"} for status in statuses):
        return "BLOCKED"
    if any(status in {"PARTIAL", "partial", "unknown"} for status in statuses):
        return "PARTIAL"
    return "OK"


def build_platform_readiness(score_version: str = "manual_v1") -> dict[str, Any]:
    warnings: list[str] = []

    try:
        platform_summary = load_platform_summary(score_version=score_version, top_n=5)
    except Exception:
        platform_summary = {}
        warnings.append(UNAVAILABLE_WARNINGS["platform_summary"])

    latest_market_date = str(platform_summary.get("latest_market_date") or "")
    topn_preview = list(platform_summary.get("topn_preview") or [])

    manifest_modules = _load_manifest_modules()
    if manifest_modules:
        return _build_manifest_readiness(
            manifest_modules=manifest_modules,
            latest_market_date=latest_market_date,
            topn_preview=topn_preview,
            warnings=warnings,
        )

    checks: list[dict[str, Any]] = []
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
        "run_id": "",
        "latest_trade_date": latest_market_date,
        "latest_market_date": latest_market_date,
        "source": "lightweight_probe",
        "summary_path": "",
        "tiers": _tiers_from_status(aggregate_readiness_status(checks)),
        "modules": [],
        "checks": checks,
        "warnings": _dedupe(warnings),
        "errors": [],
        "missing_data": _missing_from_checks(checks),
        "partial_data": _partial_from_checks(checks),
        "next_actions": _next_actions(
            aggregate_readiness_status(checks),
            _missing_from_checks(checks),
            _partial_from_checks(checks),
        ),
        "dashboard_url": "http://127.0.0.1:5174",
    }


def _load_manifest_modules() -> list[dict[str, Any]]:
    try:
        return load_latest_data_run_manifest()
    except Exception:
        return []


def _build_manifest_readiness(
    *,
    manifest_modules: list[dict[str, Any]],
    latest_market_date: str,
    topn_preview: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    summary = summarize_manifest_modules(manifest_modules)
    missing_data = list(summary["missing_data"])
    partial_data = list(summary["partial_data"])
    errors = list(summary["errors"])
    checks = _manifest_checks(manifest_modules, latest_market_date, topn_preview)

    if not latest_market_date:
        missing_data.append("platform_summary")
        warnings.append(UNAVAILABLE_WARNINGS["platform_summary"])
    if not topn_preview:
        missing_data.extend(["score_topn", "review_queue"])
        warnings.extend([UNAVAILABLE_WARNINGS["topn_preview"], UNAVAILABLE_WARNINGS["review_queue"]])

    status = "BLOCKED" if missing_data else summary["status"]
    run_id = str(manifest_modules[0].get("run_id") or "") if manifest_modules else ""
    latest_trade_date = latest_market_date or _latest_trade_date_from_manifest(manifest_modules)
    return {
        "mode": "eod_local",
        "status": status,
        "as_of": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "run_id": run_id,
        "latest_trade_date": latest_trade_date,
        "latest_market_date": latest_trade_date,
        "source": "data_run_manifest",
        "summary_path": _summary_path_from_manifest(manifest_modules),
        "tiers": [
            {"tier": "tier1", "status": "BLOCKED" if missing_data else summary["tier1_status"]},
            {"tier": "tier2", "status": summary["tier2_status"]},
            {"tier": "tier3", "status": summary["tier3_status"]},
        ],
        "modules": manifest_modules,
        "checks": checks,
        "warnings": _dedupe([*summary["warnings"], *warnings]),
        "errors": _dedupe(errors),
        "missing_data": _dedupe(missing_data),
        "partial_data": _dedupe(partial_data),
        "next_actions": _next_actions(status, missing_data, partial_data),
        "dashboard_url": "http://127.0.0.1:5174",
    }


def _manifest_checks(
    modules: list[dict[str, Any]],
    latest_market_date: str,
    topn_preview: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_module = {str(item.get("module") or ""): item for item in modules}
    checks = [
        _check(
            "platform_summary",
            "ready" if latest_market_date and topn_preview else "missing_data",
            "Platform summary available" if latest_market_date and topn_preview else UNAVAILABLE_WARNINGS["platform_summary"],
        )
    ]
    review = by_module.get("review_queue")
    checks.append(
        _check(
            "review_queue",
            "ready" if review and review.get("status") == "success" and topn_preview else "partial",
            "Review Queue available" if review and review.get("status") == "success" and topn_preview else UNAVAILABLE_WARNINGS["review_queue"],
        )
    )
    for key, module in [
        ("news", "news"),
        ("research_reports", "research_reports"),
        ("generated_reports", "generated_reports"),
    ]:
        item = by_module.get(module)
        status = str(item.get("status") if item else "skipped")
        checks.append(
            _check(
                key,
                "ready" if status == "success" else "partial",
                f"{CHECK_LABELS[key]} available" if status == "success" else UNAVAILABLE_WARNINGS[key],
            )
        )
    return checks


def _tiers_from_status(status: str) -> list[dict[str, str]]:
    tier1 = "BLOCKED" if status == "BLOCKED" else "OK"
    optional = "PARTIAL" if status == "PARTIAL" else "OK"
    return [
        {"tier": "tier1", "status": tier1},
        {"tier": "tier2", "status": optional},
        {"tier": "tier3", "status": optional},
    ]


def _missing_from_checks(checks: list[dict[str, Any]]) -> list[str]:
    return [str(check["key"]) for check in checks if check.get("status") == "missing_data"]


def _partial_from_checks(checks: list[dict[str, Any]]) -> list[str]:
    return [str(check["key"]) for check in checks if check.get("status") in {"partial", "unknown"}]


def _next_actions(status: str, missing_data: list[str], partial_data: list[str]) -> list[str]:
    if status == "BLOCKED":
        return [f"Resolve Tier 1 missing data: {', '.join(_dedupe(missing_data))}"]
    if status == "PARTIAL":
        return [f"Review partial auxiliary data: {', '.join(_dedupe(partial_data))}"]
    return []


def _latest_trade_date_from_manifest(modules: list[dict[str, Any]]) -> str:
    dates = [str(item.get("latest_trade_date") or item.get("trade_date") or "") for item in modules]
    return max([value for value in dates if value], default="")


def _summary_path_from_manifest(modules: list[dict[str, Any]]) -> str:
    for item in modules:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        value = metadata.get("summary_path")
        if value:
            return str(value)
    return ""


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
