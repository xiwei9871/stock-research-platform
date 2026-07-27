from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_STRATEGY_RUNNERS = {
    "lhb_shortline",
    "midtrend_artifacts",
    "mid_trend",
    "tech_bottleneck",
}


def file_fingerprint(path: str | Path) -> dict[str, Any] | None:
    candidate = Path(path)
    try:
        content = candidate.read_bytes()
        stat = candidate.stat()
    except FileNotFoundError:
        return None
    return {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def build_publication_receipt(
    *,
    summary_path: str | Path,
    expected_trade_date: str,
    repair_run_id: str,
) -> dict[str, Any]:
    path = Path(summary_path).absolute()
    payload = json.loads(path.read_text(encoding="utf-8"))
    fingerprint = file_fingerprint(path)
    if fingerprint is None:
        raise FileNotFoundError(path)
    return {
        "expected_trade_date": expected_trade_date,
        "repair_run_id": repair_run_id,
        "publication_run_id": str(payload.get("run_id") or ""),
        "summary_path": str(path),
        "fingerprint": fingerprint,
        "overall_status": str(payload.get("status") or ""),
        "strategy_status": dict(payload.get("strategy_status") or {}),
    }


def validate_publication_receipt(
    receipt: Any,
    *,
    expected_trade_date: str,
    repair_run_id: str,
    expected_summary_path: str | Path,
    release_root: str | Path,
) -> dict[str, Any]:
    if not isinstance(receipt, dict) or not receipt:
        return {"status": "failed", "error_code": "publication_receipt_missing"}
    if receipt.get("expected_trade_date") != expected_trade_date:
        return {"status": "failed", "error_code": "publication_receipt_date_mismatch"}
    if receipt.get("repair_run_id") != repair_run_id:
        return {"status": "failed", "error_code": "publication_receipt_run_mismatch"}
    summary_path = Path(str(receipt.get("summary_path") or ""))
    canonical_path = Path(expected_summary_path).absolute()
    if summary_path.absolute() != canonical_path:
        return {"status": "failed", "error_code": "publication_receipt_path_mismatch"}
    try:
        resolved_summary_path = summary_path.resolve(strict=True)
        resolved_release_root = Path(release_root).resolve(strict=True)
        resolved_summary_path.relative_to(resolved_release_root)
    except (FileNotFoundError, ValueError, OSError):
        return {"status": "failed", "error_code": "publication_receipt_path_escape"}
    if resolved_summary_path != canonical_path.resolve(strict=True):
        return {"status": "failed", "error_code": "publication_receipt_path_mismatch"}
    fingerprint = file_fingerprint(summary_path)
    if fingerprint is None or fingerprint != receipt.get("fingerprint"):
        return {"status": "failed", "error_code": "publication_receipt_file_changed"}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "failed", "error_code": "publication_receipt_summary_invalid"}
    strategy_status = dict(payload.get("strategy_status") or {})
    expected_run_id = f"strategy-eod-{expected_trade_date}-local"
    if (
        payload.get("trade_date") != expected_trade_date
        or payload.get("run_id") != expected_run_id
        or payload.get("status") != "success"
        or not REQUIRED_STRATEGY_RUNNERS.issubset(strategy_status)
        or any(strategy_status.get(name) != "success" for name in REQUIRED_STRATEGY_RUNNERS)
    ):
        return {"status": "failed", "error_code": "publication_receipt_summary_mismatch"}
    if (
        receipt.get("publication_run_id") != payload.get("run_id")
        or receipt.get("overall_status") != payload.get("status")
        or receipt.get("strategy_status") != strategy_status
    ):
        return {"status": "failed", "error_code": "publication_receipt_payload_mismatch"}
    return {"status": "success", "summary": payload}
