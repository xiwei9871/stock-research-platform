from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_quality_pool_layer_v6_proposal_v1"
V5_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
GATE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_equivalence_gate_batch1_v1"
GATE_SUMMARY = GATE_DIR / "latent_manual_review_equivalence_gate_batch1_summary.json"
GATE_DECISIONS = GATE_DIR / "latent_manual_review_equivalence_gate_batch1_decisions.csv"
GATE_CORE = GATE_DIR / "latent_manual_review_equivalence_gate_batch1_core_equivalent_proposals.csv"
BACKFILL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_backfill_batch1_v1"
BACKFILL_EVIDENCE = BACKFILL_DIR / "latent_manual_review_backfill_batch1_evidence.csv"
BACKFILL_CITATIONS = BACKFILL_DIR / "latent_manual_review_backfill_batch1_page_citations.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

PROPOSAL_COLUMNS = [
    "stock_code",
    "stock_name",
    "quality_layer",
    "source_group",
    "proposal_source",
    "manual_review_status",
    "source_layer",
    "v6_proposal_status",
    "added_from",
    "evidence_count",
    "page_citation_count",
    "source_pdf_count",
    "primary_source_supported",
    "equivalence_decision",
    "hard_tech_domain",
    "supply_chain_role_hint",
    "business_relevance_hint",
    "bottleneck_or_chokepoint_hint",
    "concept_pollution_risk",
    "next_action_hint",
    "bottleneck_thesis_support",
    "remaining_evidence_gap_flags",
    "downgrade_risk_flags",
    "manual_approval_question",
    "recommended_next_action",
    "quality_pool_v6_is_proposal_only",
    "auto_added_to_quality_pool",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "notes",
]

DUPLICATE_COLUMNS = [
    "stock_code",
    "stock_name",
    "duplicate_reason",
    "v5_quality_layer",
    "v5_source_group",
    "batch1_equivalence_decision",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]

EVIDENCE_INDEX_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_file",
    "source_type",
    "source_title",
    "source_date",
    "page",
    "evidence_text",
    "evidence_claim_type",
    "citation_quality",
    "v6_proposal_status",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]


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


def _supported_if_any(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return "evidence_required"
    return "supported" if frame[column].astype(str).str.contains("supported", na=False).any() else "evidence_required"


def _first_non_empty(frame: pd.DataFrame, column: str, default: str = "") -> str:
    if frame.empty or column not in frame.columns:
        return default
    values = [str(value) for value in frame[column].tolist() if str(value).strip()]
    return values[0] if values else default


def _v5_reference_rows(v5: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in v5.sort_values("stock_code").iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "quality_layer": row.get("quality_layer", ""),
                "source_group": row.get("source_group", ""),
                "proposal_source": row.get("proposal_source", ""),
                "manual_review_status": row.get("manual_review_status", "pending_manual_approval"),
                "source_layer": row.get("quality_layer", ""),
                "v6_proposal_status": "v5_reference_preserved",
                "added_from": "quality_pool_layer_v5",
                "evidence_count": 0,
                "page_citation_count": 0,
                "source_pdf_count": 0,
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "equivalence_decision": "v5_reference",
                "hard_tech_domain": "",
                "supply_chain_role_hint": "",
                "business_relevance_hint": "",
                "bottleneck_or_chokepoint_hint": "",
                "concept_pollution_risk": "",
                "next_action_hint": row.get("recommended_next_action", ""),
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support", ""),
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "downgrade_risk_flags": row.get("downgrade_risk_flags", ""),
                "manual_approval_question": row.get("manual_approval_question", ""),
                "recommended_next_action": row.get("recommended_next_action", ""),
                "quality_pool_v6_is_proposal_only": True,
                "auto_added_to_quality_pool": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows, columns=PROPOSAL_COLUMNS)


def _duplicate_check(v5: pd.DataFrame, core: pd.DataFrame) -> pd.DataFrame:
    v5_lookup = v5.set_index("stock_code") if not v5.empty else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, row in core[core["stock_code"].isin(set(v5["stock_code"]))].sort_values("stock_code").iterrows():
        v5_row = v5_lookup.loc[row["stock_code"]]
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "duplicate_reason": "already_in_quality_pool_v5",
                "v5_quality_layer": v5_row.get("quality_layer", ""),
                "v5_source_group": v5_row.get("source_group", ""),
                "batch1_equivalence_decision": row.get("equivalence_decision", ""),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows, columns=DUPLICATE_COLUMNS)


def _added_rows(core: pd.DataFrame, evidence: pd.DataFrame, citations: pd.DataFrame, duplicate_codes: set[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    non_duplicate_core = core[~core["stock_code"].isin(duplicate_codes)].copy()
    for _, row in non_duplicate_core.sort_values("stock_code").iterrows():
        stock_evidence = evidence[evidence["stock_code"].eq(row["stock_code"])].copy()
        stock_citations = citations[citations["stock_code"].eq(row["stock_code"])].copy()
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "quality_layer": "latent_manual_review_batch1_core_equivalent_quality_pool_proposal",
                "source_group": "latent_manual_review_batch1_primary_source_backfilled",
                "proposal_source": "latent_manual_review_equivalence_gate_batch1_v1",
                "manual_review_status": "pending_manual_approval",
                "source_layer": "latent_manual_review_batch1_core_equivalent_proposal",
                "v6_proposal_status": "proposed_addition_only",
                "added_from": "latent_manual_review_equivalence_gate_batch1_v1",
                "evidence_count": int(row.get("primary_source_evidence_count") or len(stock_evidence)),
                "page_citation_count": int(row.get("page_level_citation_count") or len(stock_citations)),
                "source_pdf_count": int(stock_evidence["source_file"].nunique()) if not stock_evidence.empty else 0,
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "equivalence_decision": row.get("equivalence_decision", ""),
                "hard_tech_domain": _supported_if_any(stock_evidence, "hard_tech_domain"),
                "supply_chain_role_hint": _supported_if_any(stock_evidence, "supply_chain_role_hint"),
                "business_relevance_hint": _supported_if_any(stock_evidence, "business_relevance_hint"),
                "bottleneck_or_chokepoint_hint": _supported_if_any(stock_evidence, "bottleneck_or_chokepoint_hint"),
                "concept_pollution_risk": _first_non_empty(stock_evidence, "concept_pollution_risk", row.get("concept_pollution_risk", "")),
                "next_action_hint": _first_non_empty(
                    stock_evidence,
                    "next_action_hint",
                    "manual review of v6 proposal evidence before any future quality-pool action",
                ),
                "bottleneck_thesis_support": "proposal_from_v5_equivalence_gate",
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "downgrade_risk_flags": row.get("route_around_risk", ""),
                "manual_approval_question": "Should this latent manual-review batch1 core-equivalent proposal be accepted into a future quality pool layer v6?",
                "recommended_next_action": "manual approval review only; do not auto-apply to any formal pool or strategy path",
                "quality_pool_v6_is_proposal_only": True,
                "auto_added_to_quality_pool": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": "Quality pool layer v6 proposal only; no signal, admission, scoring, or formal strategy integration.",
            }
        )
    return pd.DataFrame(rows, columns=PROPOSAL_COLUMNS)


def _evidence_index(additions: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    if additions.empty or evidence.empty:
        return pd.DataFrame(columns=EVIDENCE_INDEX_COLUMNS)
    add_codes = set(additions["stock_code"])
    rows = evidence[evidence["stock_code"].isin(add_codes)].copy()
    rows["v6_proposal_status"] = "proposed_addition_only"
    rows["research_only"] = True
    rows["used_for_signal"] = False
    rows["used_for_admission"] = False
    for column in EVIDENCE_INDEX_COLUMNS:
        if column not in rows.columns:
            rows[column] = ""
    return rows[EVIDENCE_INDEX_COLUMNS].sort_values(["stock_code", "source_type", "page"]).reset_index(drop=True)


def _summary(
    v5: pd.DataFrame,
    core: pd.DataFrame,
    duplicate: pd.DataFrame,
    additions: pd.DataFrame,
    proposal: pd.DataFrame,
    evidence_index: pd.DataFrame,
    gate_summary: dict[str, Any],
    strategy_clean: bool,
) -> dict[str, Any]:
    used_for_signal = int(proposal["used_for_signal"].map(_truthy).sum()) if not proposal.empty else 0
    used_for_admission = int(proposal["used_for_admission"].map(_truthy).sum()) if not proposal.empty else 0
    auto_added = int(proposal["auto_added_to_quality_pool"].map(_truthy).sum()) if not proposal.empty else 0
    duplicate_count = int(len(duplicate))
    expected_count = int(len(v5) + len(additions))
    blocking = (
        len(v5) != 300
        or len(core) != 26
        or int(gate_summary.get("core_equivalent_proposal_count", 0)) != 26
        or len(proposal) != expected_count
        or proposed_duplicate_stock_count(proposal) != 0
        or used_for_signal
        or used_for_admission
        or auto_added
        or not strategy_clean
    )
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif duplicate_count:
        acceptance = "conditionally_ready_with_duplicates"
    else:
        acceptance = "quality_pool_layer_v6_proposal_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_v5_reference_count": int(len(v5)),
        "source_core_equivalent_proposal_count": int(len(core)),
        "processed_core_equivalent_proposal_count": int(len(core)),
        "duplicate_stock_count": duplicate_count,
        "proposed_addition_count": int(len(additions)),
        "proposed_quality_pool_v6_count": int(len(proposal)),
        "evidence_index_row_count": int(len(evidence_index)),
        "primary_source_collection_performed": False,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "quality_pool_v6_is_proposal_only": True,
        "auto_added_to_quality_pool_count": auto_added,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": acceptance,
    }


def proposed_duplicate_stock_count(proposal: pd.DataFrame) -> int:
    if proposal.empty:
        return 0
    return int(len(proposal) - proposal["stock_code"].nunique())


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_v5_reference_count": summary["quality_pool_v5_reference_count"],
        "source_core_equivalent_proposal_count": summary["source_core_equivalent_proposal_count"],
        "processed_core_equivalent_proposal_count": summary["processed_core_equivalent_proposal_count"],
        "duplicate_stock_count": summary["duplicate_stock_count"],
        "proposed_addition_count": summary["proposed_addition_count"],
        "proposed_quality_pool_v6_count": summary["proposed_quality_pool_v6_count"],
        "primary_source_collection_performed": False,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "quality_pool_v6_is_proposal_only": True,
        "auto_added_to_quality_pool_count": summary["auto_added_to_quality_pool_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def _report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Quality Pool Layer v6 Proposal v1",
            "",
            "## 1. Scope",
            "This task generates a research-only quality pool / manual review quality layer v6 proposal from quality pool v5 plus latent manual-review batch1 core-equivalent proposals. It does not create a confirmed core pool, formal strategy pool, signal input, admission input, or scoring input.",
            "",
            "## 2. Input Baseline",
            f"Quality pool v5 reference count: {summary['quality_pool_v5_reference_count']}; source core-equivalent proposals: {summary['source_core_equivalent_proposal_count']}.",
            "",
            "## 3. Proposal Results",
            f"Duplicate stocks: {summary['duplicate_stock_count']}; proposed additions: {summary['proposed_addition_count']}; proposed quality pool v6 count: {summary['proposed_quality_pool_v6_count']}; evidence index rows: {summary['evidence_index_row_count']}.",
            "",
            "## 4. Guardrails",
            f"quality_pool_v6_is_proposal_only=true; auto_added_to_quality_pool_count=0; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; price_move_used_for_signal=0; low_position_used_for_signal=0; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_quality_pool_layer_v6_manual_approval_v1",
            "2. tech_bottleneck_latent_manual_review_standard_collection_v1",
            "3. tech_bottleneck_latent_manual_review_human_confirm_packet_v1",
        ]
    )


def run() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v5 = _read_csv(V5_MANIFEST)
    gate_summary = _read_json(GATE_SUMMARY)
    core = _read_csv(GATE_CORE)
    evidence = _read_csv(BACKFILL_EVIDENCE)
    citations = _read_csv(BACKFILL_CITATIONS)

    duplicate = _duplicate_check(v5, core)
    additions = _added_rows(core, evidence, citations, set(duplicate["stock_code"]))
    v5_rows = _v5_reference_rows(v5)
    proposal = pd.concat([v5_rows, additions], ignore_index=True, sort=False)[PROPOSAL_COLUMNS].sort_values(
        ["v6_proposal_status", "quality_layer", "stock_code"]
    )
    evidence_index = _evidence_index(additions, evidence)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(v5, core, duplicate, additions, proposal, evidence_index, gate_summary, strategy_clean)
    guardrails = _guardrails(summary)

    proposal.to_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_proposal.csv", index=False)
    additions.to_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_added_from_batch1.csv", index=False)
    duplicate.to_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_duplicate_check.csv", index=False)
    evidence_index.to_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_evidence_index.csv", index=False)
    _write_json(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_proposal_summary.json", summary)
    _write_json(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_proposal_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
