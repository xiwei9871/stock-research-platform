from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


QUEUE_VERSION = 1
DEFAULT_BOOTSTRAP_LOOKBACK_DAYS = 7
DEFAULT_PENDING_DATE_LIMIT = 3


def pending_dates_path(output_root: str | Path) -> Path:
    return Path(output_root) / "research" / "eod_auto_repair" / "pending_dates.json"


def load_pending_dates(output_root: str | Path) -> dict[str, Any]:
    path = pending_dates_path(output_root)
    if not path.exists():
        return {"version": QUEUE_VERSION, "items": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": QUEUE_VERSION, "items": []}
    if not isinstance(payload, dict):
        return {"version": QUEUE_VERSION, "items": []}
    items = [_normalize_item(item) for item in payload.get("items", []) if isinstance(item, dict)]
    items = [item for item in items if item is not None]
    items.sort(key=lambda item: item["trade_date"])
    return {"version": QUEUE_VERSION, "items": items}


def select_pending_trade_dates(
    output_root: str | Path,
    *,
    current_trade_date: str,
    pending_date_limit: int = DEFAULT_PENDING_DATE_LIMIT,
    bootstrap_lookback_days: int = DEFAULT_BOOTSTRAP_LOOKBACK_DAYS,
) -> list[str]:
    current = _parse_trade_date(current_trade_date)
    state = load_pending_dates(output_root)
    items = {item["trade_date"]: item for item in state["items"]}
    _bootstrap_from_recent_summaries(
        output_root,
        current=current,
        lookback_days=bootstrap_lookback_days,
        items=items,
    )
    pending = [item for item in items.values() if _is_pending(item)]
    pending.sort(key=lambda item: item["trade_date"])
    current_text = current.isoformat()
    selected = [current_text]
    selected.extend(
        item["trade_date"]
        for item in pending
        if item["trade_date"] != current_text
    )
    selected = [current_text, *selected[1 : 1 + max(0, int(pending_date_limit))]]
    current_item = items.get(current_text)
    if current_item is None:
        items[current_text] = _new_item(current_text)
    elif not _is_pending(current_item):
        current_item["last_status"] = "pending"
        current_item["remaining_blockers"] = []
        current_item["last_error"] = ""
        current_item["updated_at"] = _now()
    _write_pending_dates(output_root, items.values())
    return selected


def record_repair_result(output_root: str | Path, summary: dict[str, Any]) -> None:
    trade_date = _parse_trade_date(str(summary.get("trade_date") or "")).isoformat()
    state = load_pending_dates(output_root)
    items = {item["trade_date"]: item for item in state["items"]}
    status = str(summary.get("final_status") or summary.get("status") or "failed").lower()
    blockers = [str(value) for value in (summary.get("remaining_blockers") or []) if str(value)]
    if status in {"success", "degraded"} and not blockers:
        items.pop(trade_date, None)
    else:
        item = items.get(trade_date) or _new_item(trade_date)
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["last_status"] = status
        item["remaining_blockers"] = blockers
        item["last_error"] = _summary_error(summary, blockers)
        item["updated_at"] = _now()
        items[trade_date] = item
    _write_pending_dates(output_root, items.values())


def _bootstrap_from_recent_summaries(
    output_root: str | Path,
    *,
    current: date,
    lookback_days: int,
    items: dict[str, dict[str, Any]],
) -> None:
    repair_root = Path(output_root) / "research" / "eod_auto_repair"
    for offset in range(1, max(0, int(lookback_days)) + 1):
        trade_date = (current - timedelta(days=offset)).isoformat()
        summary_path = repair_root / trade_date / "run_summary.json"
        if not summary_path.is_file():
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if not isinstance(summary, dict):
            continue
        status = str(summary.get("final_status") or summary.get("status") or "failed").lower()
        blockers = [str(value) for value in (summary.get("remaining_blockers") or []) if str(value)]
        if status in {"success", "degraded"} and not blockers:
            items.pop(trade_date, None)
            continue
        item = items.get(trade_date) or _new_item(trade_date)
        item["last_status"] = status
        item["remaining_blockers"] = blockers
        item["last_error"] = _summary_error(summary, blockers)
        item["updated_at"] = _now()
        items[trade_date] = item


def _is_pending(item: dict[str, Any]) -> bool:
    return bool(item.get("remaining_blockers")) or str(item.get("last_status") or "pending") not in {
        "success",
        "degraded",
    }


def _new_item(trade_date: str) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "attempts": 0,
        "last_status": "pending",
        "remaining_blockers": [],
        "last_error": "",
        "updated_at": _now(),
    }


def _normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        trade_date = _parse_trade_date(str(item.get("trade_date") or "")).isoformat()
    except ValueError:
        return None
    return {
        "trade_date": trade_date,
        "attempts": max(0, int(item.get("attempts") or 0)),
        "last_status": str(item.get("last_status") or "pending"),
        "remaining_blockers": [str(value) for value in (item.get("remaining_blockers") or []) if str(value)],
        "last_error": str(item.get("last_error") or ""),
        "updated_at": str(item.get("updated_at") or _now()),
    }


def _write_pending_dates(output_root: str | Path, items: Any) -> None:
    path = pending_dates_path(output_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [_normalize_item(item) for item in items if isinstance(item, dict)]
    payload = {
        "version": QUEUE_VERSION,
        "items": sorted(
            [item for item in normalized if item is not None],
            key=lambda item: item["trade_date"],
        ),
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parse_trade_date(value: str) -> date:
    return date.fromisoformat(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summary_error(summary: dict[str, Any], blockers: list[str]) -> str:
    return str(
        summary.get("error_summary")
        or summary.get("loop_stop_reason")
        or "; ".join(blockers)
        or ""
    )
