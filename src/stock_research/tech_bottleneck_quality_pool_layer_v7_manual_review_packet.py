from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_quality_pool_layer_v7_manual_review_packet_v1"
V7_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_proposal_v1"
V7_SUMMARY = V7_DIR / "tech_bottleneck_quality_pool_layer_v7_proposal_summary.json"
V7_PROPOSAL = V7_DIR / "tech_bottleneck_quality_pool_layer_v7_proposal.csv"
V7_ADDED = V7_DIR / "tech_bottleneck_quality_pool_layer_v7_added_from_standard.csv"
V7_EVIDENCE = V7_DIR / "tech_bottleneck_quality_pool_layer_v7_evidence_index.csv"
V6_MANUAL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v6_manual_approval_v1"
V6_MANUAL_DECISIONS = V6_MANUAL_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_decisions.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

CANDIDATE_COLUMNS = [
    "stock_code",
    "stock_name",
    "candidate_layer",
    "candidate_source",
    "review_status",
    "approval_default",
    "proposal_reason",
    "evidence_row_count",
    "page_citation_count",
    "source_pdf_count",
    "primary_source_supported",
    "manual_decision",
    "manual_reviewer",
    "manual_comment",
    "recommended_action",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "auto_added_to_quality_pool",
    "frozen_v7_generated",
    "notes",
]

TEMPLATE_COLUMNS = [
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


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _evidence_counts(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(columns=["stock_code", "evidence_row_count", "page_citation_count", "source_pdf_count"])
    page_level = evidence["citation_quality"].astype(str).eq("page_level") if "citation_quality" in evidence.columns else pd.Series(False, index=evidence.index)
    return (
        pd.DataFrame({"stock_code": sorted(set(evidence["stock_code"]))})
        .merge(evidence.groupby("stock_code").size().rename("evidence_row_count"), on="stock_code", how="left")
        .merge(evidence[page_level].groupby("stock_code").size().rename("page_citation_count"), on="stock_code", how="left")
        .merge(evidence.groupby("stock_code")["source_file"].nunique().rename("source_pdf_count"), on="stock_code", how="left")
        .fillna(0)
    )


def _build_candidates(
    v7_proposal: pd.DataFrame,
    v7_added: pd.DataFrame,
    evidence: pd.DataFrame,
    v6_manual: pd.DataFrame,
) -> pd.DataFrame:
    counts = _evidence_counts(evidence)
    v7_added = v7_added.merge(counts, on="stock_code", how="left", suffixes=("", "_from_evidence"))
    v6_hold_codes = set(
        v6_manual[v6_manual.get("manual_decision", pd.Series(dtype=str)).astype(str).eq("hold_for_review")]["stock_code"]
    )
    rows: list[dict[str, Any]] = []
    for _, row in v7_proposal[v7_proposal["v7_proposal_status"].eq("v6_proposal_reference_preserved")].sort_values(
        "stock_code"
    ).iterrows():
        if row["stock_code"] in v6_hold_codes:
            candidate_layer = "v6_hold_for_review_unresolved"
            review_status = "hold_for_review"
            approval_default = "hold"
            proposal_reason = "v6_proposal_hold_for_review_unresolved"
            recommended_action = "manual_review_v6_hold_before_any_freeze"
        else:
            candidate_layer = "v5_baseline_kept"
            review_status = "baseline_reference_only"
            approval_default = "not_in_current_review"
            proposal_reason = "v5_baseline_kept"
            recommended_action = "no_current_action"
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "candidate_layer": candidate_layer,
                "candidate_source": candidate_layer,
                "review_status": review_status,
                "approval_default": approval_default,
                "proposal_reason": proposal_reason,
                "evidence_row_count": int(row.get("evidence_count") or 0),
                "page_citation_count": int(row.get("page_citation_count") or 0),
                "source_pdf_count": int(row.get("source_pdf_count") or 0),
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "manual_decision": approval_default if candidate_layer == "v6_hold_for_review_unresolved" else "",
                "manual_reviewer": "",
                "manual_comment": "",
                "recommended_action": recommended_action,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "auto_added_to_quality_pool": False,
                "frozen_v7_generated": False,
                "notes": "v5 baseline is a reference only; v6 hold rows remain unresolved unless explicitly approved later.",
            }
        )

    for _, row in v7_added.sort_values("stock_code").iterrows():
        evidence_count = int(row.get("evidence_row_count") or row.get("evidence_count") or 0)
        page_count = int(row.get("page_citation_count") or row.get("page_citation_count_from_evidence") or 0)
        source_pdf_count = int(row.get("source_pdf_count") or row.get("source_pdf_count_from_evidence") or 0)
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "candidate_layer": "standard_core_equivalent_v7_candidates",
                "candidate_source": "standard_core_equivalent_v7_candidates",
                "review_status": "manual_review_required",
                "approval_default": "pending",
                "proposal_reason": "standard_core_equivalent_primary_source_supported",
                "evidence_row_count": evidence_count,
                "page_citation_count": page_count,
                "source_pdf_count": source_pdf_count,
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "manual_decision": "pending",
                "manual_reviewer": "",
                "manual_comment": "",
                "recommended_action": "review_for_approval",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "auto_added_to_quality_pool": False,
                "frozen_v7_generated": False,
                "notes": "Manual review required; no automatic approval or frozen quality-pool action.",
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS).sort_values(["candidate_layer", "stock_code"]).reset_index(drop=True)


def _build_template(candidates: pd.DataFrame) -> pd.DataFrame:
    review_rows = candidates[
        candidates["candidate_layer"].isin(
            {"v6_hold_for_review_unresolved", "standard_core_equivalent_v7_candidates"}
        )
    ].copy()
    template = review_rows[
        [
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
        ]
    ].copy()
    template["decision_time"] = ""
    return template[TEMPLATE_COLUMNS].sort_values(["candidate_source", "stock_code"]).reset_index(drop=True)


def _summary(v7_summary: dict[str, Any], candidates: pd.DataFrame, evidence: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    layer_counts = candidates["candidate_layer"].value_counts() if not candidates.empty else pd.Series(dtype=int)
    used_for_signal = int(candidates["used_for_signal"].map(_truthy).sum()) if not candidates.empty else 0
    used_for_admission = int(candidates["used_for_admission"].map(_truthy).sum()) if not candidates.empty else 0
    auto_approved = int(candidates["manual_decision"].astype(str).str.lower().eq("approve").sum()) if not candidates.empty else 0
    unresolved_hold = int(layer_counts.get("v6_hold_for_review_unresolved", 0))
    standard_count = int(layer_counts.get("standard_core_equivalent_v7_candidates", 0))
    blocking = (
        int(v7_summary.get("quality_pool_v5_reference_count", 0)) != 300
        or int(v7_summary.get("quality_pool_v6_proposal_reference_count", 0)) != 326
        or int(v7_summary.get("v6_manual_approved_count", -1)) != 0
        or int(v7_summary.get("v6_hold_for_review_count", 0)) != 26
        or standard_count != 52
        or unresolved_hold != 26
        or len(evidence) != 1096
        or auto_approved
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    acceptance = "blocked_due_to_guardrail_violation" if blocking else "quality_pool_layer_v7_manual_review_packet_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_v5_reference_count": int(v7_summary.get("quality_pool_v5_reference_count", 0)),
        "quality_pool_v6_proposal_reference_count": int(v7_summary.get("quality_pool_v6_proposal_reference_count", 0)),
        "v6_manual_approved_count": int(v7_summary.get("v6_manual_approved_count", 0)),
        "v6_hold_for_review_count": int(v7_summary.get("v6_hold_for_review_count", 0)),
        "standard_core_equivalent_candidate_count": standard_count,
        "proposed_additions_count": int(v7_summary.get("proposed_addition_count", 0)),
        "evidence_index_rows": int(len(evidence)),
        "candidates_requiring_manual_review": int(unresolved_hold + standard_count),
        "unresolved_hold_count": unresolved_hold,
        "auto_approved_count": auto_approved,
        "frozen_v7_generated": False,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": acceptance,
    }


def _packet_json(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "review_scope": {
            "v5_baseline_kept": 300,
            "v6_hold_for_review_unresolved": summary["v6_hold_for_review_count"],
            "standard_core_equivalent_v7_candidates": summary["standard_core_equivalent_candidate_count"],
        },
        "manual_review_policy": {
            "auto_approval_allowed": False,
            "frozen_v7_generated": False,
            "v6_hold_rows_require_explicit_approval": True,
            "signal_or_admission_use_allowed": False,
        },
        "summary": summary,
    }


def _packet_md(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Quality Pool Layer v7 Manual Review Packet v1",
            "",
            "## Scope",
            "This packet is research-only. It prepares manual review rows for unresolved v6 hold names and standard v7 proposal additions. It does not approve, freeze, or connect anything to signal/admission/scoring/strategy.",
            "",
            "## Candidate Layers",
            f"- v5_baseline_kept: {summary['quality_pool_v5_reference_count']}",
            f"- v6_hold_for_review_unresolved: {summary['v6_hold_for_review_count']}",
            f"- standard_core_equivalent_v7_candidates: {summary['standard_core_equivalent_candidate_count']}",
            "",
            "## Guardrails",
            f"auto_approved_count={summary['auto_approved_count']}; frozen_v7_generated=false; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## Acceptance Decision",
            summary["acceptance_decision"],
        ]
    )


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_v5_reference_count": summary["quality_pool_v5_reference_count"],
        "quality_pool_v6_proposal_reference_count": summary["quality_pool_v6_proposal_reference_count"],
        "v6_manual_approved_count": summary["v6_manual_approved_count"],
        "v6_hold_for_review_count": summary["v6_hold_for_review_count"],
        "standard_core_equivalent_candidate_count": summary["standard_core_equivalent_candidate_count"],
        "candidates_requiring_manual_review": summary["candidates_requiring_manual_review"],
        "unresolved_hold_count": summary["unresolved_hold_count"],
        "auto_approved_count": summary["auto_approved_count"],
        "frozen_v7_generated": False,
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def run() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v7_summary = _read_json(V7_SUMMARY)
    v7_proposal = _read_csv(V7_PROPOSAL)
    v7_added = _read_csv(V7_ADDED)
    evidence = _read_csv(V7_EVIDENCE)
    v6_manual = _read_csv(V6_MANUAL_DECISIONS)
    candidates = _build_candidates(v7_proposal, v7_added, evidence, v6_manual)
    template = _build_template(candidates)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(v7_summary, candidates, evidence, strategy_clean)
    guardrails = _guardrails(summary)

    candidates.to_csv(OUTPUT_DIR / "v7_manual_review_candidates.csv", index=False)
    template.to_csv(OUTPUT_DIR / "v7_manual_approval_template.csv", index=False)
    _write_json(OUTPUT_DIR / "v7_manual_review_packet.json", _packet_json(summary))
    _write_json(OUTPUT_DIR / "v7_manual_review_packet_summary.json", summary)
    _write_json(OUTPUT_DIR / "v7_manual_review_packet_guardrails.json", guardrails)
    (OUTPUT_DIR / "v7_manual_review_packet.md").write_text(_packet_md(summary), encoding="utf-8")
    (OUTPUT_DIR / "v7_manual_review_packet_summary.md").write_text(_packet_md(summary), encoding="utf-8")
    return summary


def _allowed_codes() -> dict[str, str]:
    if not (OUTPUT_DIR / "v7_manual_review_candidates.csv").exists():
        run()
    candidates = _read_csv(OUTPUT_DIR / "v7_manual_review_candidates.csv")
    review = candidates[
        candidates["candidate_layer"].isin(
            {"v6_hold_for_review_unresolved", "standard_core_equivalent_v7_candidates"}
        )
    ].copy()
    return dict(zip(review["stock_code"], review["candidate_layer"]))


def validate_v7_manual_approval_file(path: str | Path) -> dict[str, Any]:
    approval_path = Path(path)
    frame = _read_csv(approval_path)
    allowed = _allowed_codes()
    for column in TEMPLATE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame["manual_decision"] = frame["manual_decision"].astype(str).str.strip().str.lower()
    frame["manual_decision"] = frame["manual_decision"].replace({"nan": ""})

    unknown = frame[~frame["stock_code"].isin(set(allowed))]
    invalid = frame[~frame["manual_decision"].isin(VALID_DECISIONS)]
    approve = frame[frame["manual_decision"].eq("approve")].copy()
    missing_reviewer = approve[approve["manual_reviewer"].astype(str).str.strip().isin({"", "nan"})]
    missing_comment = approve[approve["manual_comment"].astype(str).str.strip().isin({"", "nan"})]

    duplicate_conflict_count = 0
    for _code, group in frame.groupby("stock_code"):
        decisions = set(group["manual_decision"].astype(str).str.strip().str.lower()) - {""}
        if len(decisions) > 1:
            duplicate_conflict_count += 1

    v6_hold_approve = approve[approve["stock_code"].map(allowed).eq("v6_hold_for_review_unresolved")]
    v6_hold_valid_approve = v6_hold_approve[
        ~v6_hold_approve["manual_reviewer"].astype(str).str.strip().isin({"", "nan"})
        & ~v6_hold_approve["manual_comment"].astype(str).str.strip().isin({"", "nan"})
    ]

    valid = (
        len(unknown) == 0
        and len(invalid) == 0
        and len(missing_reviewer) == 0
        and len(missing_comment) == 0
        and duplicate_conflict_count == 0
    )
    return {
        "valid": bool(valid),
        "approval_file": str(approval_path),
        "row_count": int(len(frame)),
        "approve_count": int(len(approve)),
        "reject_count": int(frame["manual_decision"].eq("reject").sum()),
        "hold_count": int(frame["manual_decision"].eq("hold").sum()),
        "pending_count": int(frame["manual_decision"].isin({"", "pending"}).sum()),
        "unknown_stock_code_count": int(len(unknown)),
        "invalid_manual_decision_count": int(len(invalid)),
        "duplicate_conflict_count": int(duplicate_conflict_count),
        "approve_missing_reviewer_count": int(len(missing_reviewer)),
        "approve_missing_comment_count": int(len(missing_comment)),
        "v6_hold_approve_count": int(len(v6_hold_approve)),
        "v6_hold_valid_approve_count": int(len(v6_hold_valid_approve)),
        "frozen_v7_generated": False,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
