from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_quality_pool_layer_v7_manual_approval_ingest_v1"
DEFAULT_PACKET_DIR = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_manual_review_packet_v1"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

LEDGER_COLUMNS = [
    "stock_code",
    "stock_name",
    "candidate_source",
    "proposal_reason",
    "evidence_row_count",
    "page_citation_count",
    "primary_source_supported",
    "manual_decision",
    "normalized_decision",
    "manual_reviewer",
    "manual_comment",
    "decision_time",
    "approval_valid",
    "validation_errors",
    "validation_warnings",
    "can_enter_freeze_candidate",
    "freeze_basis_reason",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "frozen_v7_generated",
]

VALID_DECISIONS = {"", "approve", "reject", "hold", "pending"}


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _normal_decision(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "nan":
        return ""
    return text


def _load_packet(packet_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    candidates_path = packet_dir / "v7_manual_review_candidates.csv"
    template_path = packet_dir / "v7_manual_approval_template.csv"
    summary_path = packet_dir / "v7_manual_review_packet_summary.json"
    missing = [path for path in [candidates_path, template_path, summary_path] if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing v7 manual review packet inputs: " + ", ".join(str(path) for path in missing))
    return _read_csv(candidates_path), _read_csv(template_path), _read_json(summary_path)


def _prepare_approval(approval_file: Path, template: pd.DataFrame) -> pd.DataFrame:
    frame = _read_csv(approval_file)
    for column in template.columns:
        if column not in frame.columns:
            frame[column] = ""
    for column in [
        "stock_code",
        "stock_name",
        "candidate_source",
        "proposal_reason",
        "evidence_row_count",
        "page_citation_count",
        "primary_source_supported",
        "recommended_action",
        "manual_decision",
        "manual_reviewer",
        "manual_comment",
        "decision_time",
    ]:
        if column not in frame.columns:
            frame[column] = ""
    frame["normalized_decision"] = frame["manual_decision"].map(_normal_decision)
    frame.loc[frame["normalized_decision"].eq(""), "normalized_decision"] = "pending"
    return frame


def _conflict_codes(frame: pd.DataFrame) -> set[str]:
    conflicts: set[str] = set()
    for code, group in frame.groupby("stock_code"):
        decisions = set(group["normalized_decision"].astype(str)) - {"", "pending"}
        if len(decisions) > 1:
            conflicts.add(code)
    return conflicts


def _build_ledger(approval: pd.DataFrame, candidates: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    review_candidates = candidates[
        candidates["candidate_layer"].isin(
            {"v6_hold_for_review_unresolved", "standard_core_equivalent_v7_candidates"}
        )
    ].copy()
    allowed = review_candidates.set_index("stock_code").to_dict("index")
    conflict_codes = _conflict_codes(approval)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for row_number, (_, row) in enumerate(approval.iterrows(), start=2):
        code = row["stock_code"]
        decision = str(row.get("normalized_decision", "pending") or "pending")
        reviewer = str(row.get("manual_reviewer", "")).strip()
        comment = str(row.get("manual_comment", "")).strip()
        candidate = allowed.get(code, {})
        row_errors: list[str] = []
        row_warnings: list[str] = []

        if code not in allowed:
            row_errors.append("unknown_stock_code")
        if decision not in VALID_DECISIONS or decision == "":
            row_errors.append("invalid_manual_decision")
        if code in conflict_codes:
            row_errors.append("duplicate_conflicting_manual_decision")
        if decision == "approve":
            if not reviewer:
                row_errors.append("approve_missing_manual_reviewer")
            if not comment:
                row_errors.append("approve_missing_manual_comment")
        if decision == "reject" and not comment:
            row_warnings.append("reject_missing_manual_comment")
        if decision == "hold" and not comment:
            row_warnings.append("hold_missing_manual_comment")

        for error in row_errors:
            errors.append({"row": row_number, "stock_code": code, "error": error})
        for warning in row_warnings:
            warnings.append({"row": row_number, "stock_code": code, "warning": warning})

        approval_valid = len(row_errors) == 0
        can_freeze = approval_valid and decision == "approve"
        if can_freeze:
            freeze_reason = "explicit_valid_manual_approval"
        elif decision in {"reject", "hold", "pending", ""}:
            freeze_reason = f"excluded_from_freeze_due_to_{decision or 'pending'}"
        else:
            freeze_reason = "excluded_from_freeze_due_to_validation_error"

        rows.append(
            {
                "stock_code": code,
                "stock_name": row.get("stock_name", candidate.get("stock_name", "")),
                "candidate_source": row.get("candidate_source", candidate.get("candidate_source", "")),
                "proposal_reason": row.get("proposal_reason", candidate.get("proposal_reason", "")),
                "evidence_row_count": int(float(row.get("evidence_row_count") or candidate.get("evidence_row_count", 0) or 0)),
                "page_citation_count": int(float(row.get("page_citation_count") or candidate.get("page_citation_count", 0) or 0)),
                "primary_source_supported": str(row.get("primary_source_supported", candidate.get("primary_source_supported", ""))),
                "manual_decision": row.get("manual_decision", ""),
                "normalized_decision": decision,
                "manual_reviewer": reviewer,
                "manual_comment": comment,
                "decision_time": row.get("decision_time", ""),
                "approval_valid": approval_valid,
                "validation_errors": "|".join(row_errors),
                "validation_warnings": "|".join(row_warnings),
                "can_enter_freeze_candidate": can_freeze,
                "freeze_basis_reason": freeze_reason,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "frozen_v7_generated": False,
            }
        )

    return pd.DataFrame(rows, columns=LEDGER_COLUMNS), errors, warnings


def _freeze_precheck(valid_approved_count: int, has_errors: bool) -> dict[str, Any]:
    if has_errors:
        status = "blocked"
    elif valid_approved_count == 0:
        status = "no_approved_candidates"
    else:
        status = "ready_for_freeze_proposal"
    return {
        "status": status,
        "allowed_base": {
            "v5_baseline": 300,
            "explicit_valid_approved_candidates_only": valid_approved_count,
        },
        "excluded": [
            "v6_hold_without_explicit_valid_approve",
            "rejected",
            "pending",
            "invalid_approval",
        ],
        "expected_frozen_v7_count_if_next_step": 300 + valid_approved_count,
    }


def _summary(
    approval_file: Path,
    candidates: pd.DataFrame,
    ledger: pd.DataFrame,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    strategy_clean: bool,
) -> dict[str, Any]:
    decision_counts = ledger["normalized_decision"].value_counts() if not ledger.empty else pd.Series(dtype=int)
    approved = int(decision_counts.get("approve", 0))
    rejected = int(decision_counts.get("reject", 0))
    hold = int(decision_counts.get("hold", 0))
    pending = int(decision_counts.get("pending", 0))
    valid_approved = int(ledger[ledger["can_enter_freeze_candidate"].astype(bool)].shape[0])
    invalid_approved = approved - valid_approved
    v6_approved = int(
        ledger[
            ledger["candidate_source"].eq("v6_hold_for_review_unresolved")
            & ledger["can_enter_freeze_candidate"].astype(bool)
        ].shape[0]
    )
    standard_approved = int(
        ledger[
            ledger["candidate_source"].eq("standard_core_equivalent_v7_candidates")
            & ledger["can_enter_freeze_candidate"].astype(bool)
        ].shape[0]
    )
    unknown_count = sum(1 for error in errors if error["error"] == "unknown_stock_code")
    duplicate_conflict_count = len({error["stock_code"] for error in errors if error["error"] == "duplicate_conflicting_manual_decision"})
    validation_error_count = len(errors)
    freeze_precheck = _freeze_precheck(valid_approved, validation_error_count > 0)
    if validation_error_count > 0:
        acceptance = "quality_pool_layer_v7_manual_approval_ingest_blocked"
    elif valid_approved == 0:
        acceptance = "quality_pool_layer_v7_manual_approval_ingest_no_approved_candidates"
    else:
        acceptance = "quality_pool_layer_v7_manual_approval_ingest_ready_for_freeze_proposal"
    return {
        "task_name": TASK_NAME,
        "input_approval_file": str(approval_file),
        "packet_candidate_count": int(len(candidates)),
        "total_rows": int(len(ledger)),
        "approved_count": approved,
        "rejected_count": rejected,
        "hold_count": hold,
        "pending_count": pending,
        "valid_approved_count": valid_approved,
        "invalid_approved_count": invalid_approved,
        "v6_hold_approved_count": v6_approved,
        "standard_candidate_approved_count": standard_approved,
        "unknown_stock_count": int(unknown_count),
        "duplicate_conflict_count": int(duplicate_conflict_count),
        "validation_error_count": int(validation_error_count),
        "validation_warning_count": int(len(warnings)),
        "can_freeze_v7": False,
        "frozen_v7_generated": False,
        "auto_approved_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "freeze_precheck": freeze_precheck,
        "acceptance_decision": acceptance,
    }


def _summary_md(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Quality Pool Layer v7 Manual Approval Ingest v1",
            "",
            "## Scope",
            "This task ingests manual approval rows and emits an approval ledger plus freeze precheck only. It does not generate frozen v7 or connect to signal/admission/scoring/strategy.",
            "",
            "## Approval Summary",
            f"Rows: {summary['total_rows']}; approved: {summary['approved_count']}; valid approved: {summary['valid_approved_count']}; invalid approved: {summary['invalid_approved_count']}; rejected: {summary['rejected_count']}; hold: {summary['hold_count']}; pending: {summary['pending_count']}.",
            "",
            "## Freeze Precheck",
            f"Status: {summary['freeze_precheck']['status']}; expected frozen v7 count if next step: {summary['freeze_precheck']['expected_frozen_v7_count_if_next_step']}; frozen_v7_generated=false.",
            "",
            "## Acceptance Decision",
            summary["acceptance_decision"],
        ]
    )


def run(
    approval_file: str | Path | None = None,
    packet_dir: str | Path = DEFAULT_PACKET_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    packet = Path(packet_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    candidates, template, _packet_summary = _load_packet(packet)
    approval_path = Path(approval_file) if approval_file is not None else packet / "v7_manual_approval_template.csv"
    approval = _prepare_approval(approval_path, template)
    ledger, errors, warnings = _build_ledger(approval, candidates)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(approval_path, candidates, ledger, errors, warnings, strategy_clean)

    ledger.to_csv(output / "v7_manual_approval_ledger.csv", index=False)
    _write_json(output / "v7_manual_approval_ledger.json", {"summary": summary, "records": ledger.to_dict("records")})
    _write_json(output / "v7_manual_approval_ingest_summary.json", summary)
    (output / "v7_manual_approval_ingest_summary.md").write_text(_summary_md(summary), encoding="utf-8")
    _write_json(output / "v7_manual_approval_validation_errors.json", errors)
    _write_json(output / "v7_manual_approval_validation_warnings.json", warnings)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-file", default=None)
    parser.add_argument("--packet-dir", default=str(DEFAULT_PACKET_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run(approval_file=args.approval_file, packet_dir=args.packet_dir, output_dir=args.output_dir),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
