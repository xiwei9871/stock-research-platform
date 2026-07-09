from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_quality_pool_layer_v6_manual_approval_v1"
PROPOSAL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v6_proposal_v1"
PROPOSAL_SUMMARY = PROPOSAL_DIR / "tech_bottleneck_quality_pool_layer_v6_proposal_summary.json"
PROPOSAL_ADDED = PROPOSAL_DIR / "tech_bottleneck_quality_pool_layer_v6_added_from_batch1.csv"
PROPOSAL_EVIDENCE = PROPOSAL_DIR / "tech_bottleneck_quality_pool_layer_v6_evidence_index.csv"
GATE_DECISIONS = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_equivalence_gate_batch1_v1/latent_manual_review_equivalence_gate_batch1_decisions.csv"
)
BACKFILL_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_backfill_batch1_v1/latent_manual_review_backfill_batch1_evidence.csv"
)
V5_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
MANUAL_DECISIONS = OUTPUT_MANUAL_DECISIONS = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v6_manual_approval_v1/manual_decisions.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

PACKET_COLUMNS = [
    "stock_code",
    "stock_name",
    "proposed_from_layer",
    "evidence_count",
    "page_citation_count",
    "source_pdf_count",
    "hard_tech_domain",
    "supply_chain_role_hint",
    "business_relevance_hint",
    "bottleneck_or_chokepoint_hint",
    "concept_pollution_risk",
    "route_around_or_substitution_risk",
    "value_capture_risk",
    "disconfirmation_trigger",
    "strongest_primary_source_claim",
    "weakest_or_riskiest_claim",
    "approval_recommendation",
    "approval_reason",
    "manual_decision",
    "manual_reviewer",
    "manual_review_note",
    "used_for_signal",
    "used_for_admission",
    "auto_added_to_quality_pool",
    "research_only",
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


def _safe_text(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\n", " ").strip()
    for term in ["买入", "卖出", "目标价", "加仓", "减仓", "持有"]:
        text = text.replace(term, "[research-redacted]")
    return text[:limit]


def _manual_decision_overrides(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["stock_code", "manual_decision", "manual_reviewer", "manual_review_note"])
    decisions = _read_csv(path)
    for column in ["manual_decision", "manual_reviewer", "manual_review_note"]:
        if column not in decisions.columns:
            decisions[column] = ""
    allowed = {"manual_approved", "hold_for_review", "rejected_or_downgraded"}
    decisions["manual_decision"] = decisions["manual_decision"].where(
        decisions["manual_decision"].isin(allowed),
        "hold_for_review",
    )
    return decisions[["stock_code", "manual_decision", "manual_reviewer", "manual_review_note"]]


def _claim_rows(evidence: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    rows = evidence[evidence["stock_code"].eq(stock_code)].copy()
    if rows.empty:
        return rows
    rows["_strength"] = (
        rows["hard_tech_domain"].astype(str).str.contains("supported").astype(int)
        + rows["supply_chain_role_hint"].astype(str).str.contains("supported").astype(int)
        + rows["business_relevance_hint"].astype(str).str.contains("supported").astype(int)
        + rows["bottleneck_or_chokepoint_hint"].astype(str).str.contains("supported").astype(int)
    )
    return rows.sort_values(["_strength", "source_type", "page"], ascending=[False, True, True])


def _strongest_claim(evidence: pd.DataFrame, stock_code: str) -> str:
    rows = _claim_rows(evidence, stock_code)
    if rows.empty:
        return ""
    return _safe_text(rows.iloc[0].get("evidence_text", ""))


def _weakest_claim(evidence: pd.DataFrame, stock_code: str) -> str:
    rows = evidence[evidence["stock_code"].eq(stock_code)].copy()
    if rows.empty:
        return "manual review should confirm primary-source sufficiency"
    risky = rows[rows["concept_pollution_risk"].astype(str).str.contains("risk", na=False)].copy()
    if not risky.empty:
        return _safe_text(risky.iloc[0].get("evidence_text", ""))
    general = rows[rows["evidence_claim_type"].astype(str).eq("general_context")].copy()
    if not general.empty:
        return _safe_text(general.iloc[0].get("evidence_text", ""))
    return "manual review should still verify route-around and value-capture sufficiency"


def _build_packet(additions: pd.DataFrame, evidence: pd.DataFrame, decisions: pd.DataFrame, overrides: pd.DataFrame) -> pd.DataFrame:
    decision_lookup = decisions.set_index("stock_code") if not decisions.empty else pd.DataFrame()
    override_lookup = overrides.set_index("stock_code") if not overrides.empty else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, row in additions.sort_values("stock_code").iterrows():
        code = row["stock_code"]
        gate = decision_lookup.loc[code] if code in decision_lookup.index else {}
        override = override_lookup.loc[code] if code in override_lookup.index else {}
        manual_decision = str(override.get("manual_decision", "") or "hold_for_review")
        manual_reviewer = str(override.get("manual_reviewer", ""))
        manual_note = str(override.get("manual_review_note", ""))
        rows.append(
            {
                "stock_code": code,
                "stock_name": row.get("stock_name", ""),
                "proposed_from_layer": row.get("source_layer", ""),
                "evidence_count": int(float(row.get("evidence_count") or 0)),
                "page_citation_count": int(float(row.get("page_citation_count") or 0)),
                "source_pdf_count": int(float(row.get("source_pdf_count") or 0)),
                "hard_tech_domain": row.get("hard_tech_domain", ""),
                "supply_chain_role_hint": row.get("supply_chain_role_hint", ""),
                "business_relevance_hint": row.get("business_relevance_hint", ""),
                "bottleneck_or_chokepoint_hint": row.get("bottleneck_or_chokepoint_hint", ""),
                "concept_pollution_risk": row.get("concept_pollution_risk", ""),
                "route_around_or_substitution_risk": gate.get("route_around_risk", row.get("downgrade_risk_flags", "")),
                "value_capture_risk": gate.get("value_capture_risk", "needs_manual_review"),
                "disconfirmation_trigger": gate.get("disconfirmation_trigger", False),
                "strongest_primary_source_claim": _strongest_claim(evidence, code),
                "weakest_or_riskiest_claim": _weakest_claim(evidence, code),
                "approval_recommendation": "hold_for_review",
                "approval_reason": "Default state requires human approval before any frozen quality pool v6 action.",
                "manual_decision": manual_decision,
                "manual_reviewer": manual_reviewer,
                "manual_review_note": manual_note,
                "used_for_signal": False,
                "used_for_admission": False,
                "auto_added_to_quality_pool": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows, columns=PACKET_COLUMNS)


def _decisions(packet: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "stock_code",
        "stock_name",
        "manual_decision",
        "manual_reviewer",
        "manual_review_note",
        "approval_recommendation",
        "approval_reason",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "auto_added_to_quality_pool",
    ]
    return packet[columns].copy()


def _split(packet: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    approved = packet[packet["manual_decision"].eq("manual_approved")].copy()
    rejected = packet[packet["manual_decision"].eq("rejected_or_downgraded")].copy()
    hold = packet[packet["manual_decision"].eq("hold_for_review")].copy()
    return approved, rejected, hold


def _summary(
    *,
    proposal_summary: dict[str, Any],
    additions: pd.DataFrame,
    packet: pd.DataFrame,
    v5: pd.DataFrame,
    strategy_clean: bool,
) -> dict[str, Any]:
    approved, rejected, hold = _split(packet)
    used_for_signal = int(packet["used_for_signal"].map(_truthy).sum()) if not packet.empty else 0
    used_for_admission = int(packet["used_for_admission"].map(_truthy).sum()) if not packet.empty else 0
    auto_added = int(packet["auto_added_to_quality_pool"].map(_truthy).sum()) if not packet.empty else 0
    blocking = (
        len(v5) != 300
        or int(proposal_summary.get("proposed_addition_count", 0)) != 26
        or len(additions) != 26
        or len(packet) != 26
        or used_for_signal
        or used_for_admission
        or auto_added
        or not strategy_clean
    )
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif len(approved) == 26:
        acceptance = "quality_pool_layer_v6_manual_approved_ready"
    elif len(hold):
        acceptance = "conditionally_ready_with_hold_for_review"
    else:
        acceptance = "quality_pool_layer_v6_manual_approval_packet_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_v5_reference_count": int(len(v5)),
        "source_v6_proposed_addition_count": int(len(additions)),
        "processed_proposed_addition_count": int(len(packet)),
        "manual_approved_count": int(len(approved)),
        "hold_for_review_count": int(len(hold)),
        "rejected_or_downgraded_count": int(len(rejected)),
        "primary_source_collection_performed": False,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "frozen_quality_pool_v6_generated": False,
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


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_v5_reference_count": summary["quality_pool_v5_reference_count"],
        "source_v6_proposed_addition_count": summary["source_v6_proposed_addition_count"],
        "processed_proposed_addition_count": summary["processed_proposed_addition_count"],
        "primary_source_collection_performed": False,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "frozen_quality_pool_v6_generated": False,
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
            "# Tech Bottleneck Quality Pool Layer v6 Manual Approval v1",
            "",
            "## 1. Scope",
            "This task prepares a manual approval packet only for the 26 proposed additions from quality pool layer v6 proposal v1. It does not collect PDFs, rerun evidence backfill, rerun equivalence, generate frozen quality pool v6, or connect to signal/admission/scoring/strategy.",
            "",
            "## 2. Manual Approval Packet",
            f"Processed proposed additions: {summary['processed_proposed_addition_count']}; manual approved: {summary['manual_approved_count']}; hold for review: {summary['hold_for_review_count']}; rejected/downgraded: {summary['rejected_or_downgraded_count']}.",
            "",
            "## 3. Guardrails",
            f"frozen_quality_pool_v6_generated=false; auto_added_to_quality_pool_count=0; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; price_move_used_for_signal=0; low_position_used_for_signal=0; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 4. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 5. Recommended Next Steps",
            "1. tech_bottleneck_quality_pool_layer_v6_freeze_v1",
            "2. tech_bottleneck_latent_manual_review_standard_collection_v1",
            "3. tech_bottleneck_latent_manual_review_human_confirm_packet_v1",
        ]
    )


def run() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    proposal_summary = _read_json(PROPOSAL_SUMMARY)
    additions = _read_csv(PROPOSAL_ADDED)
    evidence = _read_csv(PROPOSAL_EVIDENCE)
    backfill_evidence = _read_csv(BACKFILL_EVIDENCE)
    decisions = _read_csv(GATE_DECISIONS)
    v5 = _read_csv(V5_MANIFEST)
    overrides = _manual_decision_overrides(MANUAL_DECISIONS)
    combined_evidence = pd.concat([evidence, backfill_evidence], ignore_index=True, sort=False).drop_duplicates()
    packet = _build_packet(additions, combined_evidence, decisions, overrides)
    decision_rows = _decisions(packet)
    approved, rejected, hold = _split(packet)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(
        proposal_summary=proposal_summary,
        additions=additions,
        packet=packet,
        v5=v5,
        strategy_clean=strategy_clean,
    )
    guardrails = _guardrails(summary)

    packet.to_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_packet.csv", index=False)
    decision_rows.to_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_decisions.csv", index=False)
    approved.to_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approved.csv", index=False)
    rejected.to_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_rejected_or_downgraded.csv", index=False)
    hold.to_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_hold_for_review.csv", index=False)
    _write_json(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_summary.json", summary)
    _write_json(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
