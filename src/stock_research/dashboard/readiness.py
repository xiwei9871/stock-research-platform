from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.config import SETTINGS
from stock_research.data_run_manifest import (
    load_recent_data_run_manifest,
    summarize_manifest_modules,
)

load_latest_data_run_manifest = load_recent_data_run_manifest
from stock_research.dashboard.display_date_gate import (
    browser_acceptance_boundary_enabled,
    select_display_date,
)
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import DEFAULT_REPORTS_DIR
from stock_research.db import connect, fetch_all


REPORT_SUFFIXES = {".html", ".md", ".json", ".csv"}


CHECK_LABELS = {
    "data_run_manifest": "Data Run Manifest",
    "platform_summary": "Platform Summary",
    "review_queue": "Review Queue",
    "market_monitor": "Market Monitor",
    "news": "News",
    "news_features": "News Features",
    "news_enrichment": "News Enrichment",
    "research_reports": "Research Reports",
    "generated_reports": "Generated Reports",
    "review_evidence_snapshots": "Review/Evidence Snapshots",
}

UNAVAILABLE_WARNINGS = {
    "platform_summary": "Platform summary unavailable",
    "topn_preview": "TopN preview unavailable",
    "review_queue": "Review Queue unavailable",
    "market_monitor": "Market Monitor unavailable",
    "news": "News unavailable",
    "news_features": "News Features unavailable",
    "news_enrichment": "News Enrichment unavailable",
    "research_reports": "Research Reports unavailable",
    "generated_reports": "Generated Reports unavailable",
    "review_evidence_snapshots": "Review/Evidence Snapshots unavailable",
}

MARKET_MONITOR_SOURCE_COUNT_SQL = """
        SELECT
            (
                SELECT count(*)::int
                FROM market.industry_daily_bar
                WHERE trade_date = %s
                  AND industry_system = 'csrc'
            ) AS industry_rows,
            (
                SELECT count(*)::int
                FROM market.index_daily_bar
                WHERE trade_date = %s
            ) AS index_rows,
            (
                SELECT count(*)::int
                FROM market_daily_bar
                WHERE trade_date = %s
                  AND adjust_type = 'qfq'
            ) AS market_daily_rows
        """


def aggregate_readiness_status(checks: list[dict[str, Any]]) -> str:
    statuses = [str(check.get("status") or "unknown") for check in checks]
    if any(status in {"BLOCKED", "missing_data"} for status in statuses):
        return "BLOCKED"
    if any(status in {"PARTIAL", "partial", "unknown"} for status in statuses):
        return "PARTIAL"
    return "OK"


def build_platform_readiness(score_version: str = "manual_v1") -> dict[str, Any]:
    boundary_enabled = browser_acceptance_boundary_enabled()
    warnings: list[str] = []

    try:
        platform_summary = load_platform_summary(score_version=score_version, top_n=5)
    except Exception:
        platform_summary = {}
        warnings.append(UNAVAILABLE_WARNINGS["platform_summary"])

    latest_market_date = str(platform_summary.get("latest_market_date") or "")
    topn_preview = list(platform_summary.get("topn_preview") or [])

    manifest_error = ""
    try:
        manifest_modules = _load_manifest_modules()
    except Exception as exc:
        manifest_modules = []
        manifest_error = type(exc).__name__
    if manifest_modules:
        return _build_manifest_readiness(
            manifest_modules=manifest_modules,
            latest_market_date=latest_market_date,
            topn_preview=topn_preview,
            warnings=warnings,
        )
    if boundary_enabled:
        return _build_boundary_manifest_unavailable_readiness(
            latest_market_date=latest_market_date,
            warnings=warnings,
            manifest_error=manifest_error,
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
        market_monitor_check = _market_monitor_check(latest_market_date)
        checks.append(market_monitor_check)
        if market_monitor_check["status"] != "ready":
            warnings.append(UNAVAILABLE_WARNINGS["market_monitor"])
        checks.append(_news_check(warnings))
        checks.append(_research_reports_check(warnings))
        checks.append(_generated_reports_check(latest_market_date, warnings))
    else:
        checks.extend(
            [
                _check("review_queue", "unknown", "Latest market date unavailable"),
                _check("market_monitor", "unknown", "Latest market date unavailable"),
                _check("news", "unknown", "Latest market date unavailable"),
                _check("research_reports", "unknown", "Latest market date unavailable"),
                _check("generated_reports", "unknown", "Latest market date unavailable"),
            ]
        )

    status = aggregate_readiness_status(checks)
    return {
        "mode": "eod_local",
        "status": status,
        "policy": _policy_from_manifest_status(
            status=status,
            missing_data=_missing_from_checks(checks),
            partial_data=_partial_from_checks(checks),
            warnings=warnings,
        ),
        "as_of": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "run_id": "",
        "latest_trade_date": latest_market_date,
        "latest_market_date": latest_market_date,
        "source": "lightweight_probe",
        "summary_path": "",
        "tiers": _tiers_from_status(status),
        "modules": [],
        "checks": checks,
        "health_groups": _build_health_groups_from_checks(
            checks=checks,
            latest_market_date=latest_market_date,
        ),
        "warnings": _dedupe(warnings),
        "errors": [],
        "missing_data": _missing_from_checks(checks),
        "partial_data": _partial_from_checks(checks),
        "next_actions": _next_actions(
            status,
            _missing_from_checks(checks),
            _partial_from_checks(checks),
        ),
        "dashboard_url": "http://127.0.0.1:5174",
    }


def _load_manifest_modules() -> list[dict[str, Any]]:
    return load_latest_data_run_manifest()


def _build_boundary_manifest_unavailable_readiness(
    *,
    latest_market_date: str,
    warnings: list[str],
    manifest_error: str,
) -> dict[str, Any]:
    candidate_trade_date = latest_market_date
    display_gate = select_display_date([], latest_market_date=candidate_trade_date)
    reason = "manifest_error" if manifest_error else "manifest_missing"
    blocking_reason = f"data_run_manifest:{reason}"
    display_gate = {
        **display_gate,
        "display_trade_date": "",
        "candidate_status": reason,
        "display_status": "missing",
        "blocking_reasons": [blocking_reason],
    }
    detail = (
        f"Data run manifest unavailable: {manifest_error}"
        if manifest_error
        else "Data run manifest unavailable: no rows"
    )
    checks = [_check("data_run_manifest", "missing_data", detail)]
    missing_data = ["data_run_manifest", "display_trade_date"]
    errors = [detail] if manifest_error else []
    combined_warnings = _dedupe([*warnings, detail])
    return {
        "mode": "eod_local",
        "status": "BLOCKED",
        "policy": _policy_from_manifest_status(
            status="BLOCKED",
            missing_data=missing_data,
            partial_data=[],
            warnings=combined_warnings,
        ),
        "as_of": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "run_id": "",
        "latest_trade_date": latest_market_date,
        "latest_market_date": latest_market_date,
        "display_trade_date": "",
        "candidate_trade_date": candidate_trade_date,
        "display_gate": display_gate,
        "source": "data_run_manifest_gate",
        "summary_path": "",
        "tiers": _tiers_from_status("BLOCKED"),
        "modules": [],
        "checks": checks,
        "health_groups": _build_health_groups_from_checks(
            checks=checks,
            latest_market_date=latest_market_date,
        ),
        "warnings": combined_warnings,
        "errors": errors,
        "missing_data": missing_data,
        "partial_data": [],
        "next_actions": _next_actions("BLOCKED", missing_data, []),
        "dashboard_url": "http://127.0.0.1:5174",
    }


def _build_manifest_readiness(
    *,
    manifest_modules: list[dict[str, Any]],
    latest_market_date: str,
    topn_preview: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    latest_trade_date = latest_market_date or _latest_trade_date_from_manifest(manifest_modules)
    display_gate = select_display_date(
        manifest_modules,
        latest_market_date=latest_trade_date,
    )
    active_modules = _manifest_modules_for_trade_date(
        manifest_modules,
        trade_date=str(display_gate.get("display_trade_date") or ""),
    )
    summary = summarize_manifest_modules(active_modules)
    missing_data = list(summary["missing_data"])
    partial_data = list(summary["partial_data"])
    errors = list(summary["errors"])
    checks = _manifest_checks(active_modules, latest_market_date, topn_preview)
    health_groups = _build_manifest_health_groups(
        modules=active_modules,
        latest_market_date=latest_trade_date,
        topn_preview=topn_preview,
    )

    if not latest_market_date:
        missing_data.append("platform_summary")
        warnings.append(UNAVAILABLE_WARNINGS["platform_summary"])
    if not topn_preview:
        missing_data.extend(["score_topn", "review_queue"])
        warnings.extend([UNAVAILABLE_WARNINGS["topn_preview"], UNAVAILABLE_WARNINGS["review_queue"]])
    if not display_gate["display_trade_date"] or display_gate["display_status"] != "ready":
        missing_data.append("display_trade_date")
        display_reason = str(display_gate.get("candidate_status") or "missing")
        blocking_reasons = [str(reason) for reason in display_gate.get("blocking_reasons") or [] if str(reason)]
        if blocking_reasons:
            display_reason = f"{display_reason}: {', '.join(blocking_reasons)}"
        warnings.append(f"Display trade date unavailable: {display_reason}")

    health_blocking_missing = _health_missing_keys(
        health_groups,
        blocking_group_keys={"base_data", "strategy_execution"},
        statuses={"missing_data"},
    )
    health_partial_missing = _health_missing_keys(
        health_groups,
        blocking_group_keys={"review_chain", "content_chain"},
        statuses={"missing_data", "partial"},
    )
    missing_data.extend(health_blocking_missing)
    partial_data.extend(health_partial_missing)

    status = "BLOCKED" if missing_data else (
        "PARTIAL" if partial_data or summary["status"] == "PARTIAL" else summary["status"]
    )
    policy = _policy_from_manifest_status(
        status=status,
        missing_data=missing_data,
        partial_data=partial_data,
        warnings=warnings,
    )
    run_id = str(active_modules[0].get("run_id") or "") if active_modules else ""
    return {
        "mode": "eod_local",
        "status": status,
        "policy": policy,
        "as_of": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "run_id": run_id,
        "latest_trade_date": latest_trade_date,
        "latest_market_date": latest_trade_date,
        "display_trade_date": display_gate["display_trade_date"],
        "candidate_trade_date": display_gate["candidate_trade_date"],
        "display_gate": display_gate,
        "source": "data_run_manifest",
        "summary_path": _summary_path_from_manifest(active_modules),
        "tiers": [
            {"tier": "tier1", "status": "BLOCKED" if missing_data else summary["tier1_status"]},
            {"tier": "tier2", "status": summary["tier2_status"]},
            {"tier": "tier3", "status": summary["tier3_status"]},
        ],
        "modules": active_modules,
        "checks": checks,
        "health_groups": health_groups,
        "warnings": _dedupe([*summary["warnings"], *warnings]),
        "errors": _dedupe(errors),
        "missing_data": _dedupe(missing_data),
        "partial_data": _dedupe(partial_data),
        "next_actions": _next_actions(status, missing_data, partial_data),
        "dashboard_url": "http://127.0.0.1:5174",
    }


def _policy_from_manifest_status(
    *,
    status: str,
    missing_data: list[str],
    partial_data: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    if status == "BLOCKED":
        return {
            "status": "blocked",
            "ready_for_dashboard": False,
            "ready_for_publication": False,
            "blocking_reasons": _dedupe(missing_data),
            "warnings": _dedupe(warnings),
        }
    if status == "PARTIAL":
        return {
            "status": "degraded_ready",
            "ready_for_dashboard": True,
            "ready_for_publication": True,
            "blocking_reasons": [],
            "warnings": _dedupe([*warnings, *[f"partial_data={item}" for item in partial_data]]),
        }
    return {
        "status": "ready",
        "ready_for_dashboard": True,
        "ready_for_publication": True,
        "blocking_reasons": [],
        "warnings": _dedupe(warnings),
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
        ("news_features", "news_features"),
        ("news_enrichment", "news_enrichment"),
        ("research_reports", "research_reports"),
        ("generated_reports", "generated_reports"),
        ("review_evidence_snapshots", "review_evidence_snapshots"),
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


def _manifest_modules_for_trade_date(
    modules: list[dict[str, Any]],
    *,
    trade_date: str,
) -> list[dict[str, Any]]:
    if not trade_date:
        return modules
    filtered = [
        item
        for item in modules
        if str(item.get("trade_date") or item.get("latest_trade_date") or "") == trade_date
    ]
    return filtered or modules


def _build_manifest_health_groups(
    *,
    modules: list[dict[str, Any]],
    latest_market_date: str,
    topn_preview: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_module = {str(item.get("module") or ""): item for item in modules}
    base_items = [
        _manifest_health_item(
            by_module,
            key="daily_bars",
            label="日线",
            modules=("daily_bars",),
            fallback_ready=bool(latest_market_date),
            fallback_detail=f"最新交易日 {latest_market_date}" if latest_market_date else "日线日期不可用",
        ),
        _manifest_health_item(
            by_module,
            key="factor_features",
            label="因子",
            modules=("technical_features", "factor_daily"),
        ),
        _manifest_health_item(
            by_module,
            key="score_topn",
            label="评分",
            modules=("score_topn",),
            fallback_ready=bool(topn_preview),
            fallback_detail="TopN 评分可用" if topn_preview else "TopN 评分不可用",
        ),
        _manifest_health_item(
            by_module,
            key="market_monitor",
            label="Market Monitor",
            modules=("market_monitor",),
            fallback_ready=_market_monitor_ready(latest_market_date),
            fallback_detail=f"Market Monitor sources ready for {latest_market_date}",
            fallback_latest_trade_date=latest_market_date,
        ),
        _manifest_health_item(
            by_module,
            key="lhb_features",
            label="龙虎榜",
            modules=("lhb_features",),
        ),
    ]
    strategy_items = [
        _manifest_health_item(
            by_module,
            key="strategy_lhb_shortline",
            label="LHB",
            modules=("strategy_lhb_shortline",),
        ),
        _manifest_health_item(
            by_module,
            key="strategy_mid_trend",
            label="Mid Trend",
            modules=("strategy_mid_trend",),
        ),
        _manifest_health_item(
            by_module,
            key="strategy_tech_bottleneck",
            label="Tech Bottleneck",
            modules=("strategy_tech_bottleneck",),
        ),
    ]
    daily_status = _health_status(base_items, "daily_bars")
    score_status = _health_status(base_items, "score_topn")
    stock_workspace_ready = daily_status == "ready" and score_status == "ready"
    stock_workspace_partial = (
        not stock_workspace_ready
        and daily_status in {"ready", "partial"}
        and score_status in {"ready", "partial"}
    )
    review_items = [
        _manifest_health_item(
            by_module,
            key="review_queue",
            label="Review Queue",
            modules=("review_queue", "review_queue_strategy_manifest"),
        ),
        _manifest_health_item(
            by_module,
            key="review_evidence_snapshots",
            label="Evidence Digest",
            modules=("review_evidence_snapshots",),
        ),
        {
            "key": "stock_workspace",
            "label": "Stock Workspace",
            "status": "ready"
            if stock_workspace_ready
            else ("partial" if stock_workspace_partial else "missing_data"),
            "detail": "日线和评分可用，个股工作台可打开"
            if stock_workspace_ready
            else (
                "日线或评分处于降级状态，个股工作台可打开但需关注数据缺口"
                if stock_workspace_partial
                else "缺少日线或评分，个股工作台证据链不完整"
            ),
            "row_count": None,
            "latest_trade_date": latest_market_date,
        },
    ]
    content_items = [
        _manifest_health_item(
            by_module,
            key="news",
            label="News",
            modules=("news",),
            fallback_ready=_public_news_available(),
            fallback_detail="新闻数据可用；未写入当日日终 manifest",
            fallback_status="partial",
            fallback_latest_trade_date=latest_market_date,
        ),
        _manifest_health_item(
            by_module,
            key="news_features",
            label="News Features",
            modules=("news_features",),
        ),
        _manifest_health_item(
            by_module,
            key="news_enrichment",
            label="News Enrichment",
            modules=("news_enrichment",),
        ),
        _manifest_health_item(
            by_module,
            key="research_reports",
            label="Research Reports",
            modules=("research_reports",),
            fallback_ready=_research_reports_available(),
            fallback_detail="研报数据可用；未写入当日日终 manifest",
            fallback_status="partial",
            fallback_latest_trade_date=latest_market_date,
        ),
        _manifest_health_item(
            by_module,
            key="generated_reports",
            label="Generated Reports",
            modules=("generated_reports",),
            fallback_ready=_generated_reports_available(latest_market_date),
            fallback_detail="生成报告可用；未写入当日日终 manifest",
            fallback_status="partial",
            fallback_latest_trade_date=latest_market_date,
        ),
    ]
    return [
        _health_group("base_data", "基础数据", base_items),
        _health_group("strategy_execution", "策略执行", strategy_items),
        _health_group("review_chain", "复盘链路", review_items),
        _health_group("content_chain", "内容链路", content_items),
    ]


def _build_health_groups_from_checks(
    *,
    checks: list[dict[str, Any]],
    latest_market_date: str,
) -> list[dict[str, Any]]:
    by_check = {str(check.get("key") or ""): check for check in checks}
    platform_status = str(by_check.get("platform_summary", {}).get("status") or "missing_data")
    review_status = str(by_check.get("review_queue", {}).get("status") or "missing_data")
    return [
        _health_group(
            "base_data",
            "基础数据",
            [
                {
                    "key": "daily_bars",
                    "label": "日线",
                    "status": "ready" if platform_status == "ready" and latest_market_date else "missing_data",
                    "detail": f"最新交易日 {latest_market_date}" if latest_market_date else "日线日期不可用",
                    "row_count": None,
                    "latest_trade_date": latest_market_date,
                },
                {
                    "key": "factor_features",
                    "label": "因子",
                    "status": "unknown",
                    "detail": "轻量探针未检查因子模块",
                    "row_count": None,
                    "latest_trade_date": "",
                },
                {
                    "key": "score_topn",
                    "label": "评分",
                    "status": "ready" if platform_status == "ready" else "missing_data",
                    "detail": by_check.get("platform_summary", {}).get("detail", ""),
                    "row_count": None,
                    "latest_trade_date": latest_market_date,
                },
                {
                    "key": "lhb_features",
                    "label": "龙虎榜",
                    "status": "unknown",
                    "detail": "轻量探针未检查龙虎榜模块",
                    "row_count": None,
                    "latest_trade_date": "",
                },
            ],
        ),
        _health_group(
            "strategy_execution",
            "策略执行",
            [
                _unknown_health_item("strategy_lhb_shortline", "LHB"),
                _unknown_health_item("strategy_mid_trend", "Mid Trend"),
                _unknown_health_item("strategy_tech_bottleneck", "Tech Bottleneck"),
            ],
        ),
        _health_group(
            "review_chain",
            "复盘链路",
            [
                {
                    "key": "review_queue",
                    "label": "Review Queue",
                    "status": review_status,
                    "detail": by_check.get("review_queue", {}).get("detail", ""),
                    "row_count": None,
                    "latest_trade_date": latest_market_date,
                },
                _check_health_item(by_check, "review_evidence_snapshots", "Evidence Digest"),
                {
                    "key": "stock_workspace",
                    "label": "Stock Workspace",
                    "status": "ready" if platform_status == "ready" else "missing_data",
                    "detail": "依赖平台摘要和评分预览",
                    "row_count": None,
                    "latest_trade_date": latest_market_date,
                },
            ],
        ),
        _health_group(
            "content_chain",
            "内容链路",
            [
                _check_health_item(by_check, "news", "News"),
                _check_health_item(by_check, "research_reports", "Research Reports"),
                _check_health_item(by_check, "generated_reports", "Generated Reports"),
            ],
        ),
    ]


def _manifest_health_item(
    by_module: dict[str, dict[str, Any]],
    *,
    key: str,
    label: str,
    modules: tuple[str, ...],
    fallback_ready: bool = False,
    fallback_detail: str = "",
    fallback_status: str = "ready",
    fallback_latest_trade_date: str = "",
) -> dict[str, Any]:
    module = next((by_module[name] for name in modules if name in by_module), None)
    if module is None:
        if fallback_ready:
            return {
                "key": key,
                "label": label,
                "status": fallback_status,
                "detail": fallback_detail,
                "row_count": None,
                "latest_trade_date": fallback_latest_trade_date,
            }
        return {
            "key": key,
            "label": label,
            "status": "missing_data",
            "detail": "未找到当日真实执行产物",
            "row_count": None,
            "latest_trade_date": "",
        }
    status = _health_status_from_manifest(module)
    detail = _health_detail(module)
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "row_count": module.get("row_count"),
        "latest_trade_date": str(module.get("latest_trade_date") or module.get("trade_date") or ""),
        "module": str(module.get("module") or ""),
    }


def _public_news_available() -> bool:
    try:
        return _has_public_news()
    except Exception:
        return False


def _research_reports_available() -> bool:
    try:
        return _has_research_reports()
    except Exception:
        return False


def _generated_reports_available(latest_market_date: str) -> bool:
    if not latest_market_date:
        return False
    try:
        return _has_generated_reports(latest_market_date)
    except Exception:
        return False


def _health_status_from_manifest(module: dict[str, Any]) -> str:
    status = str(module.get("status") or "unavailable")
    if status == "success":
        return "ready"
    if status in {"partial", "skipped"}:
        return "partial"
    return "missing_data"


def _health_detail(module: dict[str, Any]) -> str:
    warning_text = "; ".join(str(item) for item in module.get("warnings") or [] if str(item))
    error = str(module.get("error_message") or "")
    if error:
        return error
    if warning_text:
        return warning_text
    row_count = module.get("row_count")
    latest_trade_date = str(module.get("latest_trade_date") or module.get("trade_date") or "")
    if row_count is not None and latest_trade_date:
        return f"{latest_trade_date}，{int(row_count)} rows"
    if latest_trade_date:
        return f"最新日期 {latest_trade_date}"
    if row_count is not None:
        return f"{int(row_count)} rows"
    return "状态已记录"


def _health_group(key: str, label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    ready_count = sum(1 for item in items if item.get("status") == "ready")
    missing_count = sum(1 for item in items if item.get("status") == "missing_data")
    status = "ready" if ready_count == len(items) else ("missing_data" if missing_count else "partial")
    return {
        "key": key,
        "label": label,
        "status": status,
        "ready_count": ready_count,
        "total_count": len(items),
        "items": items,
    }


def _health_ready(items: list[dict[str, Any]], key: str) -> bool:
    return any(item.get("key") == key and item.get("status") == "ready" for item in items)


def _health_status(items: list[dict[str, Any]], key: str) -> str:
    for item in items:
        if item.get("key") == key:
            return str(item.get("status") or "")
    return ""


def _health_missing_keys(
    health_groups: list[dict[str, Any]],
    *,
    blocking_group_keys: set[str],
    statuses: set[str],
) -> list[str]:
    keys: list[str] = []
    for group in health_groups:
        if str(group.get("key") or "") not in blocking_group_keys:
            continue
        for item in group.get("items") or []:
            if str(item.get("status") or "") in statuses:
                keys.append(str(item.get("key") or ""))
    return _dedupe(keys)


def _unknown_health_item(key: str, label: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": "unknown",
        "detail": "轻量探针未检查该模块",
        "row_count": None,
        "latest_trade_date": "",
    }


def _check_health_item(
    by_check: dict[str, dict[str, Any]],
    key: str,
    label: str,
) -> dict[str, Any]:
    check = by_check.get(key)
    if not check:
        return _unknown_health_item(key, label)
    return {
        "key": key,
        "label": label,
        "status": check.get("status", "unknown"),
        "detail": check.get("detail", ""),
        "row_count": None,
        "latest_trade_date": "",
    }


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


def _market_monitor_check(
    latest_market_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    if not latest_market_date:
        return _check("market_monitor", "unknown", "Latest market date unavailable")
    try:
        with connect(service) as conn:
            rows = fetch_all(
                conn,
                MARKET_MONITOR_SOURCE_COUNT_SQL,
                [latest_market_date, latest_market_date, latest_market_date],
            )
    except Exception:
        return _check("market_monitor", "partial", UNAVAILABLE_WARNINGS["market_monitor"])
    row = dict(rows[0]) if rows else {}
    industry_rows = int(row.get("industry_rows") or 0)
    index_rows = int(row.get("index_rows") or 0)
    market_daily_rows = int(row.get("market_daily_rows") or 0)
    if industry_rows > 0 and index_rows >= 5 and market_daily_rows > 0:
        return _check(
            "market_monitor",
            "ready",
            f"Market Monitor sources ready for {latest_market_date}",
        )
    missing = []
    if industry_rows <= 0:
        missing.append("industry_daily_bar")
    if index_rows < 5:
        missing.append("index_daily_bar>=5")
    if market_daily_rows <= 0:
        missing.append("market_daily_bar")
    return _check(
        "market_monitor",
        "partial",
        "Market Monitor missing " + ", ".join(missing),
    )


def _market_monitor_ready(latest_market_date: str) -> bool:
    return _market_monitor_check(latest_market_date)["status"] == "ready"


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
