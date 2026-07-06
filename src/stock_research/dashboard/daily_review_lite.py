from __future__ import annotations

from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.daily_review_artifacts import (
    load_daily_review_payload,
    write_daily_review_artifacts,
)
from stock_research.dashboard.market_monitor import build_market_monitor_eod
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.review_queue import build_review_queue
from stock_research.db import connect, fetch_all
from stock_research.report_run_store import apply_report_run_schema, record_report_run


SECTION_ORDER = [
    ("data_readiness", "Data Readiness"),
    ("market_review", "Market Review"),
    ("strategy_summaries", "Strategy Summaries"),
    ("holding_review", "Holding Review"),
    ("operator_plan", "Operator Plan"),
    ("next_day_checklist", "Next-day Checklist"),
    ("artifacts", "Artifacts"),
]
DAILY_REVIEW_OUTPUT_ROOT = Path(SETTINGS.reports_root) / "daily_review_lite"


def build_daily_review_lite(
    trade_date: str | None = None,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    summary = _safe_call(lambda: load_platform_summary(service=service), default={})
    selected_trade_date = str(trade_date or summary.get("latest_market_date") or "")[:10]
    if not selected_trade_date:
        return _payload(
            trade_date="",
            status="empty",
            run=_run_payload(None, source="no run selected"),
            fallback=True,
            sections=_empty_sections(),
            artifacts=[],
            warnings=["no display trade date available"],
        )

    run = _latest_registered_run(selected_trade_date, service=service)
    if run is None:
        try:
            run = _generate_and_register_run(selected_trade_date, service=service)
        except OSError:
            run = None
    if run is not None:
        loaded_payload = _load_payload_from_run(run, selected_trade_date=selected_trade_date)
        if loaded_payload is not None:
            return loaded_payload

    fallback_payload = _build_live_daily_review_payload(selected_trade_date, service=service)
    fallback_payload["run"] = _run_payload(None, source="fallback")
    fallback_payload["fallback"] = True
    fallback_payload["status"] = _overall_status(sections=fallback_payload["sections"], fallback=True)
    fallback_payload["warnings"] = ["no registered daily review run selected"]
    return fallback_payload


def _build_live_daily_review_payload(
    selected_trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    summary = _safe_call(lambda: load_platform_summary(service=service), default={})
    market = _safe_call(lambda: build_market_monitor_eod(trade_date=selected_trade_date), default={})
    queue = _safe_call(lambda: build_review_queue(trade_date=selected_trade_date, limit=10), default={})
    reports = _safe_call(lambda: load_report_links(selected_trade_date), default=[])
    artifacts = _artifact_payloads(None, reports)
    sections = _sections(
        selected_trade_date=selected_trade_date,
        summary=summary,
        market=market,
        queue=queue,
        artifacts=artifacts,
        run={},
    )
    return _payload(
        trade_date=selected_trade_date,
        status=_overall_status(sections=sections, fallback=False),
        run=_run_payload(None, source="generated"),
        fallback=False,
        sections=sections,
        artifacts=artifacts,
        warnings=[],
    )


def _generate_and_register_run(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    payload = _build_live_daily_review_payload(trade_date, service=service)
    output_dir = DAILY_REVIEW_OUTPUT_ROOT / trade_date
    paths = write_daily_review_artifacts(payload, output_dir)
    apply_report_run_schema(service=service)
    run_id = record_report_run(
        trade_date=trade_date,
        report_type="daily_review_lite",
        report_paths=paths,
        metadata={"status": payload.get("status", ""), "fallback": False},
        service=service,
    )
    return {
        "run_id": run_id,
        "trade_date": trade_date,
        "report_type": "daily_review_lite",
        "status": "completed",
        "report_paths": paths,
        "metadata": {"status": payload.get("status", ""), "fallback": False},
        "updated_at": "",
    }


def _load_payload_from_run(run: dict[str, Any], *, selected_trade_date: str) -> dict[str, Any] | None:
    report_paths = run.get("report_paths") if isinstance(run.get("report_paths"), dict) else {}
    json_path = _resolve_report_path(_json_report_path(report_paths), selected_trade_date=selected_trade_date)
    if not json_path:
        return None
    try:
        payload = load_daily_review_payload(json_path)
    except Exception:
        return None
    reports = _safe_call(lambda: load_report_links(selected_trade_date), default=[])
    payload["trade_date"] = str(payload.get("trade_date") or selected_trade_date)
    payload["run"] = _run_payload(run, source="report_run")
    payload["fallback"] = False
    payload["artifacts"] = _artifact_payloads(run, reports)
    payload["warnings"] = list(payload.get("warnings") or [])
    return payload


def _latest_registered_run(trade_date: str, *, service: str) -> dict[str, Any] | None:
    try:
        with connect(service) as conn:
            rows = fetch_all(
                conn,
                """
                SELECT
                    run_id,
                    trade_date::text AS trade_date,
                    report_type,
                    status,
                    report_paths,
                    metadata,
                    updated_at::text AS updated_at
                FROM report.report_run
                WHERE trade_date = %s
                  AND report_type IN ('daily_review_lite', 'daily_review', 'daily')
                ORDER BY
                    CASE report_type
                        WHEN 'daily_review_lite' THEN 1
                        WHEN 'daily_review' THEN 2
                        ELSE 3
                    END,
                    updated_at DESC
                LIMIT 1
                """,
                [trade_date],
            )
    except Exception:
        return None
    return dict(rows[0]) if rows else None


def _sections(
    *,
    selected_trade_date: str,
    summary: dict[str, Any],
    market: dict[str, Any],
    queue: dict[str, Any],
    artifacts: list[dict[str, Any]],
    run: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    market_items = [
        _item("复盘日", selected_trade_date),
        _item("市场日期", summary.get("latest_market_date")),
        _item("因子日期", summary.get("latest_factor_date")),
        _item("评分日期", summary.get("latest_score_date")),
    ]
    breadth = market.get("market_breadth") if isinstance(market.get("market_breadth"), dict) else {}
    market_emotion = market.get("market_emotion") if isinstance(market.get("market_emotion"), dict) else {}
    emotion_summary = market_emotion.get("summary") if isinstance(market_emotion.get("summary"), dict) else {}
    limit_performance = (
        market_emotion.get("limit_performance")
        if isinstance(market_emotion.get("limit_performance"), dict)
        else {}
    )
    market_review_items = [
        _item("市场情绪日期", market.get("trade_date") or selected_trade_date),
        _item(
            "上涨/下跌",
            _join_counts(
                _first_present(breadth, "advancers", "up_count"),
                _first_present(breadth, "decliners", "down_count"),
            ),
        ),
        _item(
            "涨停/跌停",
            _join_counts(limit_performance.get("limit_up_count"), limit_performance.get("limit_down_count")),
        ),
        _item("综合强度", _format_score(emotion_summary.get("score"))),
    ]
    groups = queue.get("groups") if isinstance(queue.get("groups"), list) else []
    strategy_items = [
        _item(
            str(group.get("label") or group.get("strategy_name") or group.get("strategy_id") or group.get("bucket") or "策略"),
            f"{group.get('count', 0)} 只",
        )
        for group in groups
    ]
    artifact_items = [_item(artifact["label"], artifact.get("url") or artifact.get("path")) for artifact in artifacts]
    return [
        _section("data_readiness", "Data Readiness", "ready" if summary else "partial", market_items),
        _section("market_review", "Market Review", "ready" if market else "partial", market_review_items),
        _section("strategy_summaries", "Strategy Summaries", "ready" if strategy_items else "empty", strategy_items),
        _section("holding_review", "Holding Review", "partial" if groups else "empty", []),
        _section("operator_plan", "Operator Plan", "ready" if run else "empty", []),
        _section("next_day_checklist", "Next-day Checklist", "ready" if run else "empty", []),
        _section("artifacts", "Artifacts", "ready" if artifact_items else "empty", artifact_items),
    ]


def _artifact_payloads(run: dict[str, Any] | None, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    report_paths = run.get("report_paths") if run and isinstance(run.get("report_paths"), dict) else {}
    for key, value in report_paths.items():
        if not value:
            continue
        resolved = _resolve_report_path(str(value), selected_trade_date=str(run.get("trade_date") or ""))
        path_text = str(resolved or value)
        artifacts.append({"key": str(key), "label": str(key).replace("_", " "), "url": path_text, "path": path_text})
    for report in reports:
        path = str(report.get("path") or "")
        if not path:
            continue
        key = f"report:{path}"
        if any(artifact["key"] == key or artifact.get("path") == path for artifact in artifacts):
            continue
        artifacts.append(
            {
                "key": key,
                "label": str(report.get("title") or path),
                "url": path,
                "path": path,
                "format": str(report.get("format") or ""),
            }
        )
    return artifacts


def _json_report_path(report_paths: dict[str, Any]) -> str:
    for key in ("json_path", "daily_review_json_path"):
        value = report_paths.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _resolve_report_path(path_text: str, *, selected_trade_date: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    if path.exists():
        return str(path)
    candidate = DAILY_REVIEW_OUTPUT_ROOT / selected_trade_date / path.name
    if candidate.exists():
        return str(candidate)
    return path_text


def _overall_status(*, sections: list[dict[str, Any]], fallback: bool) -> str:
    if not sections:
        return "empty"
    statuses = {str(section.get("status") or "") for section in sections}
    if "failed" in statuses:
        return "failed"
    if statuses == {"empty"}:
        return "empty"
    if fallback or "partial" in statuses or "empty" in statuses:
        return "partial"
    return "ready"


def _run_payload(run: dict[str, Any] | None, *, source: str) -> dict[str, Any]:
    if not run:
        return {"run_id": "", "source": source, "report_type": "daily_review_lite", "status": ""}
    return {
        "run_id": str(run.get("run_id") or ""),
        "source": source,
        "report_type": str(run.get("report_type") or ""),
        "status": str(run.get("status") or ""),
        "updated_at": str(run.get("updated_at") or ""),
    }


def _empty_sections() -> list[dict[str, Any]]:
    return [_section(key, title, "empty", []) for key, title in SECTION_ORDER]


def _section(key: str, title: str, status: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"key": key, "title": title, "status": status, "items": items}


def _item(label: str, value: Any) -> dict[str, Any]:
    return {"label": label, "value": "" if value is None else str(value)}


def _join_counts(left: Any, right: Any) -> str:
    if left is None and right is None:
        return ""
    return f"{left or 0} / {right or 0}"


def _first_present(values: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = values.get(key)
        if value is not None:
            return value
    return None


def _format_score(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return ""


def _payload(
    *,
    trade_date: str,
    status: str,
    run: dict[str, Any],
    fallback: bool,
    sections: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "status": status,
        "run": run,
        "fallback": fallback,
        "sections": sections,
        "artifacts": artifacts,
        "warnings": warnings,
    }


def _safe_call(callable_obj, *, default):
    try:
        return callable_obj()
    except Exception:
        return default
