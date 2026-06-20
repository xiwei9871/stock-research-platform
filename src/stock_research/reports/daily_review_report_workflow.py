from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from stock_research.report_run_store import record_report_run
from stock_research.reports.daily_review_contract import normalize_action, normalize_review_priority


REPORT_TYPE = "daily_review_v1"
SCHEMA_VERSION = "daily_review_v1"


def build_daily_review(
    *,
    trade_date: str,
    run_id: str,
    data_readiness: dict[str, Any] | None,
    market_review: dict[str, Any] | None,
    lhb_review: dict[str, Any] | None,
    mid_trend_review: dict[str, Any] | None,
    technical_bottleneck_review: dict[str, Any] | None,
    holding_reviews: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    readiness_payload = deepcopy(data_readiness or {})
    market_payload = _normalize_contract_fields(deepcopy(market_review or {}))
    lhb_payload = _normalize_contract_fields(deepcopy(lhb_review or {}))
    mid_trend_payload = _normalize_contract_fields(deepcopy(mid_trend_review or {}))
    technical_payload = _normalize_contract_fields(deepcopy(technical_bottleneck_review or {}))
    holding_payload = [
        _normalize_contract_fields(deepcopy(item))
        for item in (holding_reviews or [])
    ]

    warnings = _collect_readiness_warnings(readiness_payload)
    review = {
        "trade_date": trade_date,
        "run_id": run_id,
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "status": _derive_status(readiness_payload),
        "data_readiness": readiness_payload,
        "market_review": market_payload,
        "lhb_review": lhb_payload,
        "mid_trend_review": mid_trend_payload,
        "technical_bottleneck_review": technical_payload,
        "strategy_summaries": {
            "lhb": _build_lhb_summary(lhb_payload),
            "mid_trend": _build_mid_trend_summary(mid_trend_payload),
            "technical_bottleneck": _build_technical_summary(technical_payload),
        },
        "strategy_items": _build_strategy_items(
            trade_date=trade_date,
            lhb_review=lhb_payload,
            mid_trend_review=mid_trend_payload,
            technical_bottleneck_review=technical_payload,
        ),
        "holding_reviews": _normalize_holding_reviews(holding_payload, trade_date=trade_date),
        "operator_plan": _build_operator_plan(
            market_review=market_payload,
            lhb_review=lhb_payload,
            trade_date=trade_date,
        ),
        "next_day_plan": {},
        "report_paths": {},
        "warnings": warnings,
    }
    review["next_day_plan"] = _build_next_day_plan(review)
    return review


def write_daily_review_package(
    review: dict[str, Any],
    output_root: str | Path,
    record_run: bool = False,
) -> dict[str, str | dict[str, str]]:
    package_root = Path(output_root) / str(review["trade_date"])
    evidence_root = package_root / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)

    report_paths: dict[str, str | dict[str, str]] = {
        "package_root": str(package_root),
        "json_path": str(package_root / "daily_review.json"),
        "markdown_path": str(package_root / "daily_review.md"),
        "manifest_path": str(package_root / "manifest.json"),
        "operator_plan_template_path": str(package_root / "operator_plan_template.json"),
        "evidence_paths": {
            "market_state": str(evidence_root / "market_state.json"),
            "lhb_review": str(evidence_root / "lhb_review.json"),
            "mid_trend_review": str(evidence_root / "mid_trend_review.json"),
            "technical_bottleneck_review": str(evidence_root / "technical_bottleneck_review.json"),
        },
    }
    review["report_paths"] = report_paths

    _write_json(
        report_paths["json_path"],
        review,
    )
    _write_text(
        report_paths["markdown_path"],
        _render_daily_review_markdown(review),
    )
    _write_json(
        report_paths["manifest_path"],
        _build_manifest(review),
    )
    _write_json(
        report_paths["operator_plan_template_path"],
        _build_operator_plan_template(review),
    )

    evidence_paths = report_paths["evidence_paths"]
    assert isinstance(evidence_paths, dict)
    _write_json(evidence_paths["market_state"], review["market_review"])
    _write_json(evidence_paths["lhb_review"], review["lhb_review"])
    _write_json(evidence_paths["mid_trend_review"], review["mid_trend_review"])
    _write_json(
        evidence_paths["technical_bottleneck_review"],
        review["technical_bottleneck_review"],
    )

    if record_run:
        record_report_run(
            trade_date=review["trade_date"],
            report_type=REPORT_TYPE,
            report_paths=report_paths,
            status=review["status"],
            metadata=_build_record_run_metadata(review),
        )

    return report_paths


def _normalize_contract_fields(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "action":
                normalized[key] = normalize_action(item)
            elif key == "review_priority":
                normalized[key] = normalize_review_priority(item)
            else:
                normalized[key] = _normalize_contract_fields(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_contract_fields(item) for item in value]
    return value


def _normalize_holding_reviews(
    holding_reviews: list[dict[str, Any]],
    *,
    trade_date: str,
) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for item in holding_reviews:
        row = dict(item)
        row["trade_date"] = row.get("trade_date") or trade_date
        row["action"] = normalize_action(row.get("action"))
        normalized_rows.append(row)
    return normalized_rows


def _collect_readiness_warnings(data_readiness: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for source_name, details in data_readiness.items():
        status = str(details.get("status") or "").strip().lower()
        freshness = details.get("freshness") or {}
        is_fresh = freshness.get("is_fresh", True)
        if status == "missing":
            warnings.append(f"source_missing:{source_name}")
        elif status == "stale" or (status == "ready" and is_fresh is False):
            warnings.append(f"source_stale:{source_name}")
    return warnings


def _derive_status(data_readiness: dict[str, Any]) -> str:
    for details in data_readiness.values():
        status = str(details.get("status") or "").strip().lower()
        freshness = details.get("freshness") or {}
        if status not in {"", "ready"}:
            return "partial"
        if freshness and freshness.get("is_fresh") is False:
            return "partial"
    return "success"


def _build_lhb_summary(lhb_review: dict[str, Any]) -> dict[str, Any]:
    return {
        "conclusion": lhb_review.get("short_market_state", "manual_review"),
        "short_allowed": bool(lhb_review.get("short_allowed")),
        "watch_count": len(lhb_review.get("lhb_watchlist") or []),
        "forbidden_actions": list(lhb_review.get("forbidden_actions") or []),
    }


def _build_mid_trend_summary(mid_trend_review: dict[str, Any]) -> dict[str, Any]:
    return {
        "conclusion": mid_trend_review.get("rebalance_suggestion", "manual_review"),
        "portfolio_health": mid_trend_review.get("portfolio_health", "unknown"),
        "holding_count": len(mid_trend_review.get("holding_health_list") or []),
    }


def _build_technical_summary(technical_bottleneck_review: dict[str, Any]) -> dict[str, Any]:
    return {
        "conclusion": technical_bottleneck_review.get("migration_summary", "manual_review"),
        "upgraded_count": len(technical_bottleneck_review.get("upgraded_items") or []),
        "research_required_count": len(
            technical_bottleneck_review.get("research_required_items") or []
        ),
    }


def _build_strategy_items(
    *,
    trade_date: str,
    lhb_review: dict[str, Any],
    mid_trend_review: dict[str, Any],
    technical_bottleneck_review: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.extend(
        _build_rows_from_candidates(
            trade_date=trade_date,
            strategy_id="lhb",
            item_type="candidate",
            rows=lhb_review.get("lhb_watchlist") or [],
        )
    )
    items.extend(
        _build_rows_from_candidates(
            trade_date=trade_date,
            strategy_id="mid_trend",
            item_type="candidate_add",
            rows=mid_trend_review.get("candidate_adds") or [],
            action_default="add_candidate",
        )
    )
    items.extend(
        _build_rows_from_candidates(
            trade_date=trade_date,
            strategy_id="mid_trend",
            item_type="candidate_reduce",
            rows=mid_trend_review.get("candidate_reduces") or [],
            action_default="reduce_review",
        )
    )
    items.extend(
        _build_rows_from_candidates(
            trade_date=trade_date,
            strategy_id="mid_trend",
            item_type="candidate_exit",
            rows=mid_trend_review.get("candidate_exits") or [],
            action_default="exit_review",
        )
    )
    items.extend(
        _build_rows_from_candidates(
            trade_date=trade_date,
            strategy_id="technical_bottleneck",
            item_type="upgrade",
            rows=technical_bottleneck_review.get("upgraded_items") or [],
            action_default="watch",
        )
    )
    items.extend(
        _build_rows_from_candidates(
            trade_date=trade_date,
            strategy_id="technical_bottleneck",
            item_type="research_required",
            rows=technical_bottleneck_review.get("research_required_items") or [],
            action_default="research_required",
        )
    )
    return items


def _build_rows_from_candidates(
    *,
    trade_date: str,
    strategy_id: str,
    item_type: str,
    rows: list[dict[str, Any]],
    action_default: str = "manual_review",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "trade_date": trade_date,
            "strategy_id": strategy_id,
            "asset_id": row.get("asset_id", ""),
            "ts_code": row.get("ts_code", ""),
            "stock_name": row.get("stock_name", ""),
            "item_type": item_type,
            "bucket": row.get("bucket", ""),
            "state": row.get("state", "watch"),
            "action": normalize_action(row.get("action"), default=action_default),
            "review_priority": normalize_review_priority(row.get("review_priority")),
            "confidence": row.get("confidence", "medium"),
            "reason": row.get("reason", {}),
            "evidence": row.get("evidence", {}),
            "source_refs": row.get("source_refs", []),
        }
        items.append(item)
    return items


def _build_operator_plan(
    *,
    market_review: dict[str, Any],
    lhb_review: dict[str, Any],
    trade_date: str,
) -> dict[str, Any]:
    must_check_before_open = [
        item["asset_id"]
        for item in _build_rows_from_candidates(
            trade_date=trade_date,
            strategy_id="lhb",
            item_type="candidate",
            rows=lhb_review.get("lhb_watchlist") or [],
        )
        if item["review_priority"] == "P0"
    ]
    return {
        "mode": "manual_review_only",
        "overall_position_bias": market_review.get("target_exposure", ""),
        "must_check_before_open": must_check_before_open,
        "forbidden_actions": list(lhb_review.get("forbidden_actions") or []),
        "manual_decisions": [],
    }


def _build_next_day_plan(review: dict[str, Any]) -> dict[str, Any]:
    p0_items = [
        item["asset_id"]
        for item in review["strategy_items"]
        if item.get("review_priority") == "P0"
    ]
    return {
        "must_review_items": p0_items,
        "forbidden_actions": list(review["operator_plan"].get("forbidden_actions") or []),
        "data_warnings": list(review.get("warnings") or []),
    }


def _build_manifest(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": review["trade_date"],
        "run_id": review["run_id"],
        "report_type": review["report_type"],
        "schema_version": review["schema_version"],
        "status": review["status"],
        "warnings": review["warnings"],
        "report_paths": review["report_paths"],
        "data_readiness": review["data_readiness"],
    }


def _build_operator_plan_template(review: dict[str, Any]) -> dict[str, Any]:
    operator_plan = review["operator_plan"]
    return {
        "trade_date": review["trade_date"],
        "created_from_run_id": review["run_id"],
        "decision_status": "pending",
        "operator_id": "",
        "overall_position_bias": operator_plan.get("overall_position_bias", ""),
        "must_check_before_open": list(operator_plan.get("must_check_before_open") or []),
        "forbidden_actions": list(operator_plan.get("forbidden_actions") or []),
        "manual_decisions": [],
    }


def _build_record_run_metadata(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": review["schema_version"],
        "warnings": list(review["warnings"]),
        "data_readiness_summary": {
            source_name: details.get("status")
            for source_name, details in review["data_readiness"].items()
        },
        "source_counts": {
            "data_readiness": len(review["data_readiness"]),
            "strategy_items": len(review["strategy_items"]),
            "holding_reviews": len(review["holding_reviews"]),
        },
    }


def _render_daily_review_markdown(review: dict[str, Any]) -> str:
    market_review = review["market_review"]
    lhb_review = review["lhb_review"]
    mid_trend_review = review["mid_trend_review"]
    technical_review = review["technical_bottleneck_review"]
    p0_items = [
        item["asset_id"]
        for item in review["strategy_items"]
        if item.get("review_priority") == "P0"
    ]
    forbidden_actions = list(review["operator_plan"].get("forbidden_actions") or [])

    lines = [
        f"# {review['trade_date']} Daily Review",
        "",
        "## Executive Summary",
        "",
        f"- Data status: {review['status']}",
        f"- Market status: {market_review.get('target_exposure', 'unknown')}",
        f"- LHB conclusion: {review['strategy_summaries']['lhb'].get('conclusion', 'manual_review')}",
        f"- Mid Trend conclusion: {review['strategy_summaries']['mid_trend'].get('conclusion', 'manual_review')}",
        (
            "- Technical Bottleneck conclusion: "
            f"{review['strategy_summaries']['technical_bottleneck'].get('conclusion', 'manual_review')}"
        ),
        f"- P0 must-review: {', '.join(p0_items) if p0_items else 'none'}",
        f"- Forbidden actions: {', '.join(forbidden_actions) if forbidden_actions else 'none'}",
        "",
        "## Data Readiness",
        "",
    ]

    for source_name, details in review["data_readiness"].items():
        lines.append(f"- `{source_name}`: {details.get('status', 'unknown')} - {details.get('summary', '')}")

    lines.extend(
        [
            "",
            "## Market Review",
            "",
            f"- Emotion state: {market_review.get('emotion_state', 'unknown')}",
            f"- Risk state: {market_review.get('risk_state', 'unknown')}",
            f"- Trend environment: {market_review.get('trend_environment', 'unknown')}",
            f"- Comment: {market_review.get('market_comment', '')}",
            "",
            "## LHB Short-line Review",
            "",
            f"- Short allowed: {lhb_review.get('short_allowed', False)}",
            f"- Market state: {lhb_review.get('short_market_state', 'manual_review')}",
            f"- Emotion phase: {lhb_review.get('emotion_phase', 'unknown')}",
            f"- Watchlist count: {len(lhb_review.get('lhb_watchlist') or [])}",
            "",
            "## Mid Trend Review",
            "",
            f"- Portfolio health: {mid_trend_review.get('portfolio_health', 'unknown')}",
            f"- Rebalance suggestion: {mid_trend_review.get('rebalance_suggestion', 'manual_review')}",
            f"- TopN relation: {mid_trend_review.get('topn_relation', '')}",
            "",
            "## Technical Bottleneck Review",
            "",
            f"- Migration summary: {technical_review.get('migration_summary', 'manual_review')}",
            f"- Upgraded items: {len(technical_review.get('upgraded_items') or [])}",
            (
                "- Research required items: "
                f"{len(technical_review.get('research_required_items') or [])}"
            ),
            "",
            "## Holding Review",
            "",
        ]
    )

    if review["holding_reviews"]:
        for row in review["holding_reviews"]:
            lines.append(
                "- "
                f"{row.get('strategy_id', '')} / {row.get('asset_id', '')}: "
                f"{row.get('action', 'manual_review')} ({row.get('current_state', 'unknown')})"
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Operator Plan",
            "",
            f"- Mode: {review['operator_plan'].get('mode', 'manual_review_only')}",
            f"- Overall position bias: {review['operator_plan'].get('overall_position_bias', '')}",
            (
                "- Must check before open: "
                f"{', '.join(review['operator_plan'].get('must_check_before_open') or []) or 'none'}"
            ),
            f"- Forbidden actions: {', '.join(forbidden_actions) if forbidden_actions else 'none'}",
            "",
            "## Next-day Checklist",
            "",
            (
                "- Must review items: "
                f"{', '.join(review['next_day_plan'].get('must_review_items') or []) or 'none'}"
            ),
            (
                "- Data warnings: "
                f"{', '.join(review['next_day_plan'].get('data_warnings') or []) or 'none'}"
            ),
            "",
            "## Warnings and Missing Data",
            "",
        ]
    )

    if review["warnings"]:
        for warning in review["warnings"]:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")

    return "\n".join(lines).rstrip() + "\n"


def _write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
