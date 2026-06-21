from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from stock_research.config import SETTINGS
from stock_research.db import connect


REPORT_TYPE = "daily_review_v1"
DEFAULT_FALLBACK_ROOT = Path("/Users/xiwei/stock_research/reports/daily_review")

_ARTIFACT_REGISTRY: dict[str, dict[str, Any]] = {
    "daily_review_json": {
        "label": "Daily Review JSON",
        "format": "json",
        "content_type": "application/json",
        "required": True,
        "path": ("json_path",),
    },
    "daily_review_markdown": {
        "label": "Daily Review Markdown",
        "format": "md",
        "content_type": "text/markdown",
        "required": False,
        "path": ("markdown_path",),
    },
    "manifest_json": {
        "label": "Package Manifest",
        "format": "json",
        "content_type": "application/json",
        "required": False,
        "path": ("manifest_path",),
    },
    "operator_plan_template_json": {
        "label": "Operator Plan Template",
        "format": "json",
        "content_type": "application/json",
        "required": False,
        "path": ("operator_plan_template_path",),
    },
    "market_state_json": {
        "label": "Market State Evidence",
        "format": "json",
        "content_type": "application/json",
        "required": False,
        "path": ("evidence_paths", "market_state"),
    },
    "lhb_review_json": {
        "label": "LHB Review Evidence",
        "format": "json",
        "content_type": "application/json",
        "required": False,
        "path": ("evidence_paths", "lhb_review"),
    },
    "mid_trend_review_json": {
        "label": "Mid Trend Review Evidence",
        "format": "json",
        "content_type": "application/json",
        "required": False,
        "path": ("evidence_paths", "mid_trend_review"),
    },
    "technical_bottleneck_review_json": {
        "label": "Technical Bottleneck Evidence",
        "format": "json",
        "content_type": "application/json",
        "required": False,
        "path": ("evidence_paths", "technical_bottleneck_review"),
    },
}


def load_daily_review_lite(
    trade_date: str,
    *,
    run_id: str | None = None,
    reports_root: str | Path = DEFAULT_FALLBACK_ROOT,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    selected_package = _resolve_package(
        trade_date,
        run_id=run_id,
        reports_root=reports_root,
        service=service,
    )
    if selected_package is None:
        return {
            "trade_date": trade_date,
            "state": "empty",
            "selected_run": None,
            "summary": None,
            "warnings": [],
            "artifacts": [],
            "missing_sources": [],
            "sections": _empty_sections(),
        }

    artifact_detail, artifact_files = _artifact_health(selected_package["report_paths"])
    selected_run = {
        "run_id": selected_package["run_id"],
        "report_type": REPORT_TYPE,
        "status": selected_package["status"],
        "updated_at": selected_package.get("updated_at"),
        "source": selected_package["source"],
        "artifact_health": _artifact_health_state(artifact_detail),
        "artifact_health_detail": artifact_detail,
    }

    artifacts = [
        {
            "key": key,
            "label": spec["label"],
            "kind": spec["format"],
            "required": spec["required"],
            "available": artifact_detail[key] == "healthy",
            "filename": artifact_files[key].name if artifact_files[key] is not None else None,
            "content_type": spec["content_type"],
            "url": _artifact_url(trade_date, key, selected_package["run_id"]),
        }
        for key, spec in _ARTIFACT_REGISTRY.items()
    ]

    core_artifact = artifact_files["daily_review_json"]
    if artifact_detail["daily_review_json"] != "healthy" or core_artifact is None:
        return {
            "trade_date": trade_date,
            "state": "failed",
            "selected_run": selected_run,
            "summary": None,
            "warnings": [],
            "artifacts": artifacts,
            "missing_sources": [],
            "sections": _empty_sections(),
        }

    try:
        review = json.loads(core_artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "trade_date": trade_date,
            "state": "failed",
            "selected_run": selected_run,
            "summary": None,
            "warnings": [],
            "artifacts": artifacts,
            "missing_sources": [],
            "sections": _empty_sections(),
        }
    return _map_daily_review_lite(
        trade_date=trade_date,
        review=review,
        selected_run=selected_run,
        artifacts=artifacts,
        metadata=selected_package.get("metadata") or {},
    )


def resolve_daily_review_lite_artifact(
    trade_date: str,
    key: str,
    *,
    run_id: str | None = None,
    reports_root: str | Path = DEFAULT_FALLBACK_ROOT,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    if key not in _ARTIFACT_REGISTRY:
        raise ValueError(f"unknown artifact key: {key}")
    selected_package = _resolve_package(
        trade_date,
        run_id=run_id,
        reports_root=reports_root,
        service=service,
    )
    if selected_package is None:
        return None
    artifact_path = _artifact_path(selected_package["report_paths"], key)
    if artifact_path is None or not artifact_path.exists() or not artifact_path.is_file():
        return None
    spec = _ARTIFACT_REGISTRY[key]
    return {
        "key": key,
        "label": spec["label"],
        "kind": spec["format"],
        "content_type": spec["content_type"],
        "required": spec["required"],
        "path": str(artifact_path),
        "filename": artifact_path.name,
        "trade_date": trade_date,
        "run_id": selected_package["run_id"],
        "source": selected_package["source"],
    }


def _select_latest_daily_review_run(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT run_id, trade_date, report_type, status, report_paths, metadata, updated_at
    FROM report.report_run
    WHERE trade_date = %(trade_date)s
      AND report_type = %(report_type)s
      AND status IN ('success', 'partial', 'failed')
    ORDER BY updated_at DESC
    LIMIT 1
    """
    params = {"trade_date": trade_date, "report_type": REPORT_TYPE}
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def _select_daily_review_run_by_id(
    run_id: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT run_id, trade_date, report_type, status, report_paths, metadata, updated_at
    FROM report.report_run
    WHERE run_id = %(run_id)s
      AND report_type = %(report_type)s
      AND status IN ('success', 'partial', 'failed')
    LIMIT 1
    """
    params = {"run_id": run_id, "report_type": REPORT_TYPE}
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def _resolve_package(
    trade_date: str,
    *,
    run_id: str | None,
    reports_root: str | Path,
    service: str,
) -> dict[str, Any] | None:
    row = (
        _select_daily_review_run_by_id(run_id, service=service)
        if run_id
        else _select_latest_daily_review_run(trade_date, service=service)
    )
    if row is not None:
        if str(row.get("trade_date"))[:10] != trade_date:
            row = None
    if row is not None:
        return {
            "run_id": str(row["run_id"]),
            "status": str(row.get("status") or "partial"),
            "updated_at": _stringify_timestamp(row.get("updated_at")),
            "report_paths": _normalize_report_paths(row.get("report_paths") or {}),
            "metadata": row.get("metadata") or {},
            "source": "report_run",
        }
    return _scan_fallback_package(trade_date, reports_root=reports_root)


def _scan_fallback_package(trade_date: str, *, reports_root: str | Path) -> dict[str, Any] | None:
    package_root = Path(reports_root) / trade_date
    known_paths = {
        "package_root": str(package_root),
        "json_path": str(package_root / "daily_review.json"),
        "markdown_path": str(package_root / "daily_review.md"),
        "manifest_path": str(package_root / "manifest.json"),
        "operator_plan_template_path": str(package_root / "operator_plan_template.json"),
        "evidence_paths": {
            "market_state": str(package_root / "evidence" / "market_state.json"),
            "lhb_review": str(package_root / "evidence" / "lhb_review.json"),
            "mid_trend_review": str(package_root / "evidence" / "mid_trend_review.json"),
            "technical_bottleneck_review": str(
                package_root / "evidence" / "technical_bottleneck_review.json"
            ),
        },
    }
    if not package_root.exists():
        return None

    status = "partial"
    json_path = Path(known_paths["json_path"])
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            status = str(payload.get("status") or "partial")
        except (OSError, json.JSONDecodeError):
            status = "partial"

    return {
        "run_id": f"fallback:{trade_date}",
        "status": status,
        "updated_at": None,
        "report_paths": known_paths,
        "metadata": {},
        "source": "fallback",
    }


def _map_daily_review_lite(
    *,
    trade_date: str,
    review: dict[str, Any],
    selected_run: dict[str, Any],
    artifacts: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "state": _top_level_state(selected_run["status"]),
        "selected_run": selected_run,
        "summary": _build_summary(review, selected_run),
        "warnings": list(review.get("warnings") or []),
        "sections": _map_sections(review),
        "artifacts": artifacts,
        "missing_sources": _map_missing_sources(review, metadata),
    }


def _map_sections(review: dict[str, Any]) -> dict[str, Any]:
    warnings = list(review.get("warnings") or [])
    next_day_plan = review.get("next_day_plan") or {}
    market_review = review.get("market_review") or {}
    holding_reviews = review.get("holding_reviews") or []
    operator_plan = review.get("operator_plan") or {}
    next_day_payload = _map_next_day_checklist(review)
    return {
        "data_readiness": {
            "status": _section_status(review.get("status") or "partial"),
            "warnings": warnings,
            "sources": review.get("data_readiness") or {},
        },
        "market_review": {
            "status": _payload_status(market_review),
            "warnings": [],
            "payload": market_review,
        },
        "strategy_summaries": {
            "lhb": _map_strategy_section(review, "lhb", review.get("lhb_review") or {}),
            "mid_trend": _map_strategy_section(
                review,
                "mid_trend",
                review.get("mid_trend_review") or {},
            ),
            "technical_bottleneck": _map_strategy_section(
                review,
                "technical_bottleneck",
                review.get("technical_bottleneck_review") or {},
            ),
        },
        "holding_review": {
            "status": _payload_status(holding_reviews),
            "warnings": [],
            "items": holding_reviews,
        },
        "operator_plan": {
            "status": _payload_status(operator_plan),
            "warnings": [],
            "payload": operator_plan,
        },
        "next_day_checklist": {
            "status": (
                "partial"
                if next_day_plan.get("data_warnings")
                else _payload_status(next_day_payload.get("must_review_items") or [])
            ),
            "warnings": list(next_day_plan.get("data_warnings") or []),
            **next_day_payload,
        },
    }


def _map_strategy_section(
    review: dict[str, Any],
    strategy_id: str,
    summary: dict[str, Any],
) -> dict[str, Any]:
    strategy_summary = (review.get("strategy_summaries") or {}).get(strategy_id) or {}
    top_items = [
        _map_strategy_item(item)
        for item in (review.get("strategy_items") or [])
        if item.get("strategy_id") == strategy_id
    ]
    warnings = _strategy_warnings(review, strategy_id)
    base_status = _payload_status(strategy_summary or summary or top_items)
    return {
        "strategy_id": strategy_id,
        "status": "partial" if warnings else base_status,
        "warnings": warnings,
        "summary": strategy_summary or summary,
        "top_items": top_items,
    }


def _map_strategy_item(item: dict[str, Any]) -> dict[str, Any]:
    mapped = {
        "asset_id": item.get("asset_id"),
        "ts_code": item.get("ts_code"),
        "stock_name": item.get("stock_name"),
        "item_type": item.get("item_type"),
        "state": item.get("state"),
        "action": item.get("action"),
        "review_priority": item.get("review_priority"),
    }
    if item.get("reason"):
        mapped["reason"] = _normalize_reason_detail(item["reason"])
    return mapped


def _map_next_day_checklist(review: dict[str, Any]) -> dict[str, Any]:
    strategy_items = review.get("strategy_items") or []
    must_review_items = []
    for item in (review.get("next_day_plan") or {}).get("must_review_items") or []:
        actions = _collect_actions(strategy_items, item.get("asset_id"), item.get("strategy_ids") or [])
        review_priority = _derive_review_priority(
            strategy_items,
            item.get("asset_id"),
            item.get("strategy_ids") or [],
        )
        must_review_items.append(
            {
                "asset_id": item.get("asset_id"),
                "ts_code": item.get("ts_code"),
                "stock_name": item.get("stock_name"),
                "strategy_ids": list(item.get("strategy_ids") or []),
                "reasons": [
                    {
                        "strategy_id": reason.get("strategy_id"),
                        **_normalize_reason_entry(reason.get("reason")),
                    }
                    for reason in (item.get("reasons") or [])
                ],
                "actions": actions,
                "review_priority": review_priority,
            }
        )
    next_day_plan = review.get("next_day_plan") or {}
    return {
        "must_review_items": must_review_items,
        "forbidden_actions": list(next_day_plan.get("forbidden_actions") or []),
        "data_warnings": list(next_day_plan.get("data_warnings") or []),
    }


def _collect_actions(
    strategy_items: list[dict[str, Any]],
    asset_id: str | None,
    strategy_ids: list[str],
) -> list[str]:
    actions: list[str] = []
    for row in strategy_items:
        if row.get("asset_id") != asset_id:
            continue
        if strategy_ids and row.get("strategy_id") not in strategy_ids:
            continue
        action = row.get("action")
        if isinstance(action, str) and action and action not in actions:
            actions.append(action)
    return actions


def _derive_review_priority(
    strategy_items: list[dict[str, Any]],
    asset_id: str | None,
    strategy_ids: list[str],
) -> str | None:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    priorities = []
    for row in strategy_items:
        if row.get("asset_id") != asset_id:
            continue
        if strategy_ids and row.get("strategy_id") not in strategy_ids:
            continue
        priority = row.get("review_priority")
        if priority in order:
            priorities.append(priority)
    if not priorities:
        return None
    return min(priorities, key=lambda item: order[item])


def _map_missing_sources(review: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    missing_sources = metadata.get("missing_sources")
    if isinstance(missing_sources, list):
        return [
            {
                "source_key": item.get("source_key") or item.get("source"),
                "summary": item.get("summary"),
                "affected_sections": list(item.get("affected_sections") or []),
                "confidence_impact": item.get("confidence_impact"),
            }
            for item in missing_sources
            if isinstance(item, dict)
        ]
    mapped = []
    for source, details in (review.get("data_readiness") or {}).items():
        status = str((details or {}).get("status") or "").lower()
        if status == "missing":
            blocking_modules = list((details or {}).get("blocking_modules") or [])
            mapped.append(
                {
                    "source_key": source,
                    "summary": (details or {}).get("summary"),
                    "affected_sections": blocking_modules,
                    "confidence_impact": (details or {}).get("confidence_impact"),
                }
            )
    return mapped


def _artifact_health(report_paths: dict[str, Any]) -> tuple[dict[str, str], dict[str, Path | None]]:
    detail: dict[str, str] = {}
    files: dict[str, Path | None] = {}
    for key in _ARTIFACT_REGISTRY:
        path = _artifact_path(report_paths, key)
        files[key] = path
        detail[key] = "healthy" if path and path.exists() and path.is_file() else "missing"
    return detail, files


def _artifact_health_state(detail: dict[str, str]) -> str:
    if detail.get("daily_review_json") != "healthy":
        return "missing"
    if any(value != "healthy" for value in detail.values()):
        return "invalid"
    return "healthy"


def _artifact_path(report_paths: dict[str, Any], key: str) -> Path | None:
    current: Any = report_paths
    for part in _ARTIFACT_REGISTRY[key]["path"]:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    if not isinstance(current, str) or not current:
        return None
    return Path(current)


def _normalize_report_paths(report_paths: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(report_paths))


def _stringify_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _top_level_state(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized == "success":
        return "ready"
    if normalized == "partial":
        return "partial"
    if normalized == "failed":
        return "failed"
    return "empty"


def _section_status(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized == "success":
        return "success"
    if normalized == "partial":
        return "partial"
    return "empty"


def _empty_sections() -> dict[str, Any]:
    return {
        "data_readiness": {"status": "empty", "warnings": [], "sources": {}},
        "market_review": {"status": "empty", "warnings": [], "payload": {}},
        "strategy_summaries": {
            "lhb": {
                "strategy_id": "lhb",
                "status": "empty",
                "warnings": [],
                "summary": {},
                "top_items": [],
            },
            "mid_trend": {
                "strategy_id": "mid_trend",
                "status": "empty",
                "warnings": [],
                "summary": {},
                "top_items": [],
            },
            "technical_bottleneck": {
                "strategy_id": "technical_bottleneck",
                "status": "empty",
                "warnings": [],
                "summary": {},
                "top_items": [],
            },
        },
        "holding_review": {"status": "empty", "warnings": [], "items": []},
        "operator_plan": {"status": "empty", "warnings": [], "payload": {}},
        "next_day_checklist": {
            "status": "empty",
            "warnings": [],
            "must_review_items": [],
            "forbidden_actions": [],
            "data_warnings": [],
        },
    }


def _build_summary(review: dict[str, Any], selected_run: dict[str, Any]) -> dict[str, Any]:
    strategy_summaries = review.get("strategy_summaries") or {}
    next_day_plan = review.get("next_day_plan") or {}
    return {
        "market_status": (review.get("market_review") or {}).get("emotion_state"),
        "overall_position_bias": (review.get("operator_plan") or {}).get("overall_position_bias"),
        "lhb_conclusion": (strategy_summaries.get("lhb") or {}).get("conclusion"),
        "mid_trend_conclusion": (strategy_summaries.get("mid_trend") or {}).get("conclusion"),
        "technical_bottleneck_conclusion": (
            strategy_summaries.get("technical_bottleneck") or {}
        ).get("conclusion"),
        "must_review_asset_ids": [
            item.get("asset_id")
            for item in (next_day_plan.get("must_review_items") or [])
            if item.get("asset_id")
        ],
        "warning_count": len(review.get("warnings") or []),
    }


def _strategy_warnings(review: dict[str, Any], strategy_id: str) -> list[str]:
    mapping = {
        "lhb": {"lhb_review", "next_day_plan"},
        "mid_trend": {"mid_trend_review"},
        "technical_bottleneck": {"technical_bottleneck_review"},
    }
    targets = mapping.get(strategy_id) or set()
    warnings: list[str] = []
    for item in _map_missing_sources(review, {}):
        affected = set(item.get("affected_sections") or [])
        if affected & targets:
            summary = item.get("summary")
            if isinstance(summary, str) and summary:
                warnings.append(f"source_missing:{item['source_key']}")
    return warnings


def _artifact_url(trade_date: str, key: str, run_id: str) -> str:
    return (
        f"/api/daily-review-lite/artifacts/{trade_date}/{key}"
        f"?run_id={quote(run_id, safe='')}"
    )


def _payload_status(payload: Any) -> str:
    if isinstance(payload, dict):
        return "success" if payload else "empty"
    if isinstance(payload, list):
        return "success" if payload else "empty"
    return "success" if payload not in (None, "") else "empty"


def _normalize_reason_entry(reason: Any) -> dict[str, Any]:
    if isinstance(reason, dict):
        return {
            "summary": _reason_summary(reason),
            "detail": reason.get("detail"),
        }
    if reason is None:
        return {"summary": None, "detail": None}
    return {"summary": str(reason), "detail": None}


def _normalize_reason_detail(reason: Any) -> dict[str, Any]:
    entry = _normalize_reason_entry(reason)
    return {key: value for key, value in entry.items() if value is not None}


def _reason_summary(reason: dict[str, Any]) -> str | None:
    summary = reason.get("summary")
    if isinstance(summary, str) and summary:
        return summary
    setup = reason.get("setup")
    if isinstance(setup, str) and setup:
        return setup
    for value in reason.values():
        if isinstance(value, str) and value:
            return value
    return None
