from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from stock_research.dashboard import tech_bottleneck_review_decisions as decisions


DEFAULT_OUTPUT_DIR = Path("outputs/research/tech_bottleneck_review_universe_operator_smoke_and_audit_v1")


def run_smoke(
    *,
    dry_run: bool = True,
    write_test_decision: bool = False,
    stock_code: str = "",
    decision: str = "",
    comment: str = "",
    evidence_checked: bool = False,
    write_token: str = "",
    output_dir: Path | str = DEFAULT_OUTPUT_DIR / "dry_run",
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    before_hash = _file_sha256(decisions.DATASET_PATH)
    summary_before = decisions.build_decision_summary()
    result: dict[str, Any] = {
        "task_name": "tech_bottleneck_review_universe_operator_smoke_and_audit_v1",
        "dry_run": dry_run,
        "write_test_decision": write_test_decision,
        "write_performed": False,
        "frontend_dataset_count": len(decisions.review_universe_stock_codes()),
        "summary_before": summary_before,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "frozen_v7_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "frontend_dataset_hash_before": before_hash,
    }

    if write_test_decision and not dry_run:
        block_reason = _write_precheck(write_token=write_token, comment=comment, evidence_checked=evidence_checked)
        if block_reason:
            result.update(
                {
                    "acceptance_decision": block_reason,
                    "summary_after": decisions.build_decision_summary(),
                    "frontend_dataset_hash_after": _file_sha256(decisions.DATASET_PATH),
                }
            )
            _write_smoke_outputs(output_path, result)
            return result
        response = decisions.record_manual_decision(
            {
                "stock_code": stock_code,
                "stock_name": "",
                "reviewer_decision": decision,
                "reviewer": "operator",
                "review_comment": comment,
                "rubric_flags": {"operator_smoke": True},
                "evidence_checked": evidence_checked,
                "source_context": {"from": "operator_smoke"},
            }
        )
        result.update(
            {
                "write_performed": True,
                "written_stock_code": response["stock_code"],
                "written_decision": response["reviewer_decision"],
            }
        )

    summary_after = decisions.build_decision_summary()
    result.update(
        {
            "summary_after": summary_after,
            "frontend_dataset_hash_after": _file_sha256(decisions.DATASET_PATH),
            "acceptance_decision": "operator_smoke_ready",
        }
    )
    _write_smoke_outputs(output_path, result)
    return result


def run_audit(*, output_dir: Path | str = DEFAULT_OUTPUT_DIR / "audit") -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    ledger = decisions.load_ledger()
    overlay = decisions.load_current_overlay()
    valid_decisions = decisions.ALLOWED_REVIEWER_DECISIONS
    decision_counts = Counter(item.get("reviewer_decision", "") for item in overlay.values())
    ledger_stock_counts = Counter(item.get("stock_code", "") for item in ledger)
    total_history_duplicates = sum(max(0, count - 1) for count in ledger_stock_counts.values())
    known_stock_codes = decisions.review_universe_stock_codes()
    audit = {
        "task_name": "tech_bottleneck_review_universe_operator_smoke_and_audit_v1",
        "total_review_universe_count": len(known_stock_codes),
        "ledger_entry_count": len(ledger),
        "unique_reviewed_stock_count": len({item.get("stock_code", "") for item in ledger}),
        "current_overlay_count": len(overlay),
        "keep_count": decision_counts.get("keep", 0),
        "hold_count": decision_counts.get("hold", 0),
        "need_more_evidence_count": decision_counts.get("need_more_evidence", 0),
        "downgrade_count": decision_counts.get("downgrade", 0),
        "reject_count": decision_counts.get("reject", 0),
        "latest_reviewed_at": max((str(item.get("recorded_at") or "") for item in ledger), default=""),
        "duplicate_decision_history_count": total_history_duplicates,
        "correction_supersede_count": total_history_duplicates,
        "invalid_decision_count": sum(1 for item in ledger if item.get("reviewer_decision") not in valid_decisions),
        "unknown_stock_code_count": sum(1 for item in ledger if item.get("stock_code") not in known_stock_codes),
        "missing_comment_count": sum(1 for item in ledger if not item.get("review_comment")),
        "missing_evidence_checked_count": sum(1 for item in ledger if item.get("evidence_checked") is not True),
        "keep_without_evidence_checked_count": sum(
            1 for item in ledger if item.get("reviewer_decision") == "keep" and item.get("evidence_checked") is not True
        ),
        "frontend_dataset_hash": _file_sha256(decisions.DATASET_PATH),
        "frozen_v7_generated": False,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "strategy_diff_empty": _strategy_diff_empty(),
        "acceptance_decision": "operator_smoke_audit_ready",
    }
    _write_json(output_path / "manual_decision_overlay_audit.json", audit)
    (output_path / "manual_decision_overlay_audit.md").write_text(_audit_markdown(audit), encoding="utf-8")
    _write_current_overlay_csv(output_path / "manual_decision_current_overlay.csv", overlay)
    return audit


def _write_precheck(*, write_token: str, comment: str, evidence_checked: bool) -> str:
    guard_enabled = os.environ.get("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "false").strip().lower() in {"1", "true", "yes", "on"}
    expected = os.environ.get("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "").strip()
    if guard_enabled and (not write_token or write_token != expected):
        return "blocked_due_to_missing_write_token" if not write_token else "blocked_due_to_invalid_write_token"
    if not comment.strip():
        return "blocked_due_to_missing_comment"
    if not evidence_checked:
        return "blocked_due_to_missing_evidence_checked"
    return ""


def _write_smoke_outputs(output_path: Path, result: dict[str, Any]) -> None:
    _write_json(output_path / "operator_smoke_summary.json", result)
    (output_path / "operator_smoke_summary.md").write_text(_smoke_markdown(result), encoding="utf-8")


def _write_current_overlay_csv(path: Path, overlay: dict[str, dict[str, Any]]) -> None:
    fieldnames = [
        "stock_code",
        "stock_name",
        "reviewer_decision",
        "reviewer",
        "review_comment",
        "evidence_checked",
        "recorded_at",
        "decision_source",
        "used_for_signal",
        "used_for_admission",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in overlay.values():
            writer.writerow({field: item.get(field, "") for field in fieldnames})


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strategy_diff_empty() -> bool | str:
    return "unknown"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _smoke_markdown(result: dict[str, Any]) -> str:
    summary_after = result.get("summary_after") or {}
    return "\n".join(
        [
            "# Tech Bottleneck Review Universe Operator Smoke v1",
            "",
            f"- dry_run: {result.get('dry_run')}",
            f"- write_performed: {result.get('write_performed')}",
            f"- frontend_dataset_count: {result.get('frontend_dataset_count')}",
            f"- reviewed_count: {summary_after.get('reviewed_count')}",
            f"- pending_count: {summary_after.get('pending_count')}",
            f"- frozen_v7_generated: {result.get('frozen_v7_generated')}",
            f"- used_for_signal_count: {result.get('used_for_signal_count')}",
            f"- used_for_admission_count: {result.get('used_for_admission_count')}",
            f"- acceptance_decision: {result.get('acceptance_decision')}",
            "",
        ]
    )


def _audit_markdown(audit: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Review Universe Decision Overlay Audit v1",
            "",
            f"- total_review_universe_count: {audit['total_review_universe_count']}",
            f"- ledger_entry_count: {audit['ledger_entry_count']}",
            f"- current_overlay_count: {audit['current_overlay_count']}",
            f"- correction_supersede_count: {audit['correction_supersede_count']}",
            f"- invalid_decision_count: {audit['invalid_decision_count']}",
            f"- unknown_stock_code_count: {audit['unknown_stock_code_count']}",
            f"- frozen_v7_generated: {audit['frozen_v7_generated']}",
            f"- used_for_signal_count: {audit['used_for_signal_count']}",
            f"- used_for_admission_count: {audit['used_for_admission_count']}",
            f"- acceptance_decision: {audit['acceptance_decision']}",
            "",
        ]
    )
