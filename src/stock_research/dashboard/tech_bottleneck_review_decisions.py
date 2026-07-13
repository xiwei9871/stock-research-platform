from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


OVERLAY_DIR = Path("outputs/research/tech_bottleneck_review_universe_manual_decision_overlay_v1")
DATASET_PATH = Path(
    "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_dataset.csv"
)
LEDGER_PATH_NAME = "manual_decision_ledger.jsonl"
CURRENT_OVERLAY_NAME = "manual_decision_current_overlay.json"
SUMMARY_JSON_NAME = "manual_decision_summary.json"
SUMMARY_MD_NAME = "manual_decision_summary.md"

ALLOWED_REVIEWER_DECISIONS = {"keep", "hold", "need_more_evidence", "downgrade", "reject"}
FORBIDDEN_FIELDS = {
    "used_for_signal",
    "used_for_admission",
    "auto_trade_enabled",
    "frozen_v7",
    "used_for_signal_count",
    "used_for_admission_count",
}


def normalize_stock_code(value: Any) -> str:
    raw = str(value or "").strip().split(".")[0]
    return raw.zfill(6) if raw.isdigit() else raw.upper()


def record_manual_decision(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = validate_manual_decision_payload(payload)
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    decision_id = f"tech_bottleneck_review_decision:{cleaned['stock_code']}:{time.time_ns()}"
    item = {
        "decision_id": decision_id,
        "recorded_at": now,
        "decision_source": "manual_overlay",
        "review_status": "reviewed",
        "used_for_signal": False,
        "used_for_admission": False,
        "auto_added_to_quality_pool": False,
        "frozen_v7_generated": False,
        **cleaned,
    }
    with (OVERLAY_DIR / LEDGER_PATH_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    load_ledger.cache_clear()
    load_current_overlay.cache_clear()
    overlay = load_current_overlay()
    _write_json(OVERLAY_DIR / CURRENT_OVERLAY_NAME, overlay)
    summary = build_decision_summary()
    _write_json(OVERLAY_DIR / SUMMARY_JSON_NAME, summary)
    (OVERLAY_DIR / SUMMARY_MD_NAME).write_text(_summary_markdown(summary), encoding="utf-8")
    return {
        "status": "recorded",
        "decision_id": decision_id,
        "stock_code": item["stock_code"],
        "reviewer_decision": item["reviewer_decision"],
        "reviewed_at": now,
    }


def validate_manual_decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("manual_decision_payload_required")
    for field in FORBIDDEN_FIELDS:
        value = payload.get(field)
        if value is True or (isinstance(value, str) and value.strip().lower() == "true"):
            raise ValueError("manual_decision_forbidden_field")
    stock_code = normalize_stock_code(payload.get("stock_code"))
    if stock_code not in review_universe_stock_codes():
        raise ValueError("stock_not_in_review_universe")
    reviewer_decision = _text(payload.get("reviewer_decision"))
    if reviewer_decision not in ALLOWED_REVIEWER_DECISIONS:
        raise ValueError("invalid_reviewer_decision")
    reviewer = _text(payload.get("reviewer"))
    review_comment = _text(payload.get("review_comment"))
    evidence_checked = _bool_value(payload.get("evidence_checked"))
    if not reviewer:
        raise ValueError("reviewer_required")
    if not review_comment:
        raise ValueError("review_comment_required")
    if not evidence_checked:
        raise ValueError("evidence_checked_required")
    return {
        "stock_code": stock_code,
        "stock_name": _text(payload.get("stock_name")),
        "reviewer_decision": reviewer_decision,
        "reviewer": reviewer,
        "review_comment": review_comment,
        "rubric_flags": _clean_json_object(payload.get("rubric_flags")),
        "evidence_checked": evidence_checked,
        "source_context": _clean_source_context(payload.get("source_context")),
    }


@lru_cache(maxsize=1)
def review_universe_stock_codes() -> set[str]:
    if not DATASET_PATH.exists():
        return set()
    frame = pd.read_csv(DATASET_PATH, dtype=str, usecols=["stock_code"]).fillna("")
    return {normalize_stock_code(value) for value in frame["stock_code"].tolist()}


@lru_cache(maxsize=1)
def load_ledger() -> list[dict[str, Any]]:
    path = OVERLAY_DIR / LEDGER_PATH_NAME
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            rows.append(read_model(parsed))
    return rows


@lru_cache(maxsize=1)
def load_current_overlay() -> dict[str, dict[str, Any]]:
    overlay: dict[str, dict[str, Any]] = {}
    for item in load_ledger():
        stock_code = normalize_stock_code(item.get("stock_code"))
        if stock_code:
            overlay[stock_code] = item
    return overlay


def list_manual_decisions(stock_code: str | None = None, limit: int = 50) -> dict[str, Any]:
    rows = load_ledger()
    if stock_code:
        normalized = normalize_stock_code(stock_code)
        rows = [row for row in rows if row.get("stock_code") == normalized]
    bounded_limit = max(1, min(int(limit or 50), 200))
    latest_first = list(reversed(rows))[:bounded_limit]
    return {"total": len(rows), "limit": bounded_limit, "items": latest_first}


def build_decision_summary() -> dict[str, Any]:
    overlay = load_current_overlay()
    counts = {decision: 0 for decision in ALLOWED_REVIEWER_DECISIONS}
    last_reviewed_at = ""
    for item in overlay.values():
        decision = str(item.get("reviewer_decision") or "")
        if decision in counts:
            counts[decision] += 1
        recorded_at = str(item.get("recorded_at") or "")
        if recorded_at > last_reviewed_at:
            last_reviewed_at = recorded_at
    reviewed_count = len(overlay)
    total = len(review_universe_stock_codes())
    return {
        "total_review_universe_count": total,
        "reviewed_count": reviewed_count,
        "pending_count": max(0, total - reviewed_count),
        "keep_count": counts["keep"],
        "hold_count": counts["hold"],
        "need_more_evidence_count": counts["need_more_evidence"],
        "downgrade_count": counts["downgrade"],
        "reject_count": counts["reject"],
        "last_reviewed_at": last_reviewed_at,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "frozen_v7_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "acceptance_decision": "tech_bottleneck_review_universe_manual_decision_overlay_ready",
    }


def overlay_for_stock(stock_code: str) -> dict[str, Any] | None:
    return load_current_overlay().get(normalize_stock_code(stock_code))


def apply_overlay_to_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    overlay = overlay_for_stock(str(item.get("stock_code") or ""))
    if overlay is None:
        item.setdefault("reviewer_decision", "")
        item.setdefault("reviewer", "")
        item.setdefault("review_comment", "")
        item.setdefault("reviewed_at", "")
        item["review_status"] = "pending"
        item["decision_source"] = ""
        return item
    item.update(
        {
            "reviewer_decision": overlay.get("reviewer_decision", ""),
            "reviewer": overlay.get("reviewer", ""),
            "review_comment": overlay.get("review_comment", ""),
            "reviewed_at": overlay.get("recorded_at", ""),
            "review_status": "reviewed",
            "decision_source": "manual_overlay",
            "rubric_flags": overlay.get("rubric_flags", {}),
            "evidence_checked": overlay.get("evidence_checked", False),
        }
    )
    return item


def read_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_id": _text(row.get("decision_id")),
        "stock_code": normalize_stock_code(row.get("stock_code")),
        "stock_name": _text(row.get("stock_name")),
        "reviewer_decision": _text(row.get("reviewer_decision")),
        "reviewer": _text(row.get("reviewer")),
        "review_comment": _text(row.get("review_comment")),
        "rubric_flags": _clean_json_object(row.get("rubric_flags")),
        "evidence_checked": _bool_value(row.get("evidence_checked")),
        "source_context": _clean_source_context(row.get("source_context")),
        "recorded_at": _text(row.get("recorded_at")),
        "decision_source": "manual_overlay",
        "review_status": "reviewed",
        "used_for_signal": False,
        "used_for_admission": False,
        "auto_added_to_quality_pool": False,
        "frozen_v7_generated": False,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Review Universe Manual Decision Overlay v1",
            "",
            f"- total_review_universe_count: {summary['total_review_universe_count']}",
            f"- reviewed_count: {summary['reviewed_count']}",
            f"- pending_count: {summary['pending_count']}",
            f"- keep_count: {summary['keep_count']}",
            f"- hold_count: {summary['hold_count']}",
            f"- need_more_evidence_count: {summary['need_more_evidence_count']}",
            f"- downgrade_count: {summary['downgrade_count']}",
            f"- reject_count: {summary['reject_count']}",
            f"- frozen_v7_generated: {summary['frozen_v7_generated']}",
            f"- acceptance_decision: {summary['acceptance_decision']}",
            "",
        ]
    )


def _clean_source_context(value: Any) -> dict[str, Any]:
    source = _clean_json_object(value)
    allowed = {"from", "frontend_dataset_version", "stock_code", "page_route"}
    return {key: source[key] for key in allowed if key in source and source[key] not in ("", None)}


def _clean_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _text(value: Any) -> str:
    return str(value or "").strip()
