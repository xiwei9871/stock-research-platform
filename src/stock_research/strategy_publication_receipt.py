from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


REQUIRED_STRATEGY_RUNNERS = {
    "lhb_shortline",
    "midtrend_artifacts",
    "mid_trend",
    "tech_bottleneck",
}
EXPECTED_STRATEGY_COUNTS = {
    "lhb_shortline": 5,
    "mid_trend": 5,
    "tech_bottleneck": 5,
}
RECEIPT_CONTRACT_FIELDS = {
    "publishable",
    "review_rows",
    "strategy_counts",
    "score_audit_status",
}


def file_fingerprint(path: str | Path) -> dict[str, Any] | None:
    try:
        snapshot = _read_summary_snapshot(Path(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return None
    return dict(snapshot["fingerprint"])


def _read_summary_snapshot(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise ValueError("strategy publication summary changed during receipt snapshot")
    content = b"".join(chunks)
    if len(content) != after.st_size:
        raise ValueError("strategy publication summary size changed during receipt snapshot")
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("strategy publication summary must be an object")
    return {
        "payload": payload,
        "fingerprint": {
            "device": after.st_dev,
            "inode": after.st_ino,
            "mtime_ns": after.st_mtime_ns,
            "size": after.st_size,
            "sha256": hashlib.sha256(content).hexdigest(),
        },
    }


def build_publication_receipt(
    *,
    summary_path: str | Path,
    expected_trade_date: str,
    repair_run_id: str,
) -> dict[str, Any]:
    path = Path(summary_path).absolute()
    snapshot = _read_summary_snapshot(path)
    payload = snapshot["payload"]
    fingerprint = snapshot["fingerprint"]
    score_audit = dict(payload.get("score_audit") or {})
    return {
        "expected_trade_date": expected_trade_date,
        "repair_run_id": repair_run_id,
        "publication_run_id": str(payload.get("run_id") or ""),
        "summary_path": str(path),
        "fingerprint": fingerprint,
        "overall_status": str(payload.get("status") or ""),
        "strategy_status": dict(payload.get("strategy_status") or {}),
        "publishable": payload.get("publishable"),
        "review_rows": payload.get("review_rows"),
        "strategy_counts": dict(score_audit.get("strategy_counts") or {}),
        "score_audit_status": str(score_audit.get("status") or ""),
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
    if not RECEIPT_CONTRACT_FIELDS.issubset(receipt):
        return {"status": "failed", "error_code": "publication_receipt_missing_contract"}
    try:
        snapshot = _read_summary_snapshot(summary_path)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return {"status": "failed", "error_code": "publication_receipt_summary_invalid"}
    if snapshot["fingerprint"] != receipt.get("fingerprint"):
        return {"status": "failed", "error_code": "publication_receipt_file_changed"}
    payload = snapshot["payload"]
    strategy_status = dict(payload.get("strategy_status") or {})
    score_audit = dict(payload.get("score_audit") or {})
    strategy_counts = dict(score_audit.get("strategy_counts") or {})
    expected_run_id = f"strategy-eod-{expected_trade_date}-local"
    if (
        payload.get("trade_date") != expected_trade_date
        or payload.get("run_id") != expected_run_id
        or payload.get("status") != "success"
        or payload.get("publishable") is not True
        or payload.get("review_rows") != 15
        or strategy_counts != EXPECTED_STRATEGY_COUNTS
        or score_audit.get("status") != "success"
        or not REQUIRED_STRATEGY_RUNNERS.issubset(strategy_status)
        or any(strategy_status.get(name) != "success" for name in REQUIRED_STRATEGY_RUNNERS)
    ):
        return {"status": "failed", "error_code": "publication_receipt_summary_mismatch"}
    if (
        receipt.get("publication_run_id") != payload.get("run_id")
        or receipt.get("overall_status") != payload.get("status")
        or receipt.get("strategy_status") != strategy_status
        or receipt.get("publishable") is not True
        or receipt.get("review_rows") != 15
        or receipt.get("strategy_counts") != EXPECTED_STRATEGY_COUNTS
        or receipt.get("score_audit_status") != "success"
    ):
        return {"status": "failed", "error_code": "publication_receipt_payload_mismatch"}
    return {"status": "success", "summary": payload}
