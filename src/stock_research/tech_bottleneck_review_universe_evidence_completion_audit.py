from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_review_universe_evidence_completion_audit_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME

V5_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
V7_PROPOSAL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_quality_pool_layer_v7_proposal_v1/tech_bottleneck_quality_pool_layer_v7_proposal.csv"
)
V7_INGEST_LEDGER = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_quality_pool_layer_v7_manual_approval_ingest_v1/v7_manual_approval_ledger.csv"
)

FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

AUDIT_COLUMNS = [
    "stock_code",
    "stock_name",
    "review_universe_source",
    "current_layer_status",
    "manual_approval_status",
    "evidence_count",
    "page_citation_count",
    "source_pdf_count",
    "primary_source_supported",
    "hard_tech_domain",
    "supply_chain_role_hint",
    "business_relevance_hint",
    "bottleneck_or_chokepoint_hint",
    "concept_pollution_risk",
    "route_around_or_substitution_risk",
    "value_capture_risk",
    "disconfirmation_trigger",
    "next_primary_source_to_check",
    "evidence_completion_status",
    "frontend_ready",
    "recommended_next_action",
    "used_for_signal",
    "used_for_admission",
    "auto_added_to_quality_pool",
]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _int_value(value: Any) -> int:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _field(value: Any, default: str = "evidence_required") -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _v5_rows(v5: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in v5.sort_values("stock_code").iterrows():
        primary_supported = _truthy(row.get("primary_source_supported"))
        next_action = _field(row.get("recommended_next_action"), "review evidence package before frontend use")
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "review_universe_source": "v5_existing",
                "current_layer_status": row.get("quality_layer", "quality_pool_v5_reference"),
                "manual_approval_status": row.get("manual_review_status", "pending_manual_approval"),
                "evidence_count": 0,
                "page_citation_count": 0,
                "source_pdf_count": 0,
                "primary_source_supported": primary_supported,
                "hard_tech_domain": _field(row.get("bottleneck_thesis_support"), "evidence_required"),
                "supply_chain_role_hint": "evidence_required",
                "business_relevance_hint": "evidence_required",
                "bottleneck_or_chokepoint_hint": _field(row.get("bottleneck_thesis_support"), "evidence_required"),
                "concept_pollution_risk": _field(row.get("downgrade_risk_flags"), "not_available"),
                "route_around_or_substitution_risk": _field(row.get("remaining_evidence_gap_flags"), "not_available"),
                "value_capture_risk": "evidence_required",
                "disconfirmation_trigger": False,
                "next_primary_source_to_check": next_action,
                "recommended_next_action": "audit evidence package and normalize page-level evidence before workspace review",
                "used_for_signal": False,
                "used_for_admission": False,
                "auto_added_to_quality_pool": False,
            }
        )
    return rows


def _proposal_rows(v7: pd.DataFrame, ledger: pd.DataFrame, candidate_source: str, review_source: str) -> list[dict[str, Any]]:
    codes = set(ledger.loc[ledger["candidate_source"].eq(candidate_source), "stock_code"].tolist())
    subset = v7[v7["stock_code"].isin(codes)].copy()
    ledger_by_code = ledger.set_index("stock_code").to_dict("index")
    rows: list[dict[str, Any]] = []
    for _, row in subset.sort_values("stock_code").iterrows():
        ledger_row = ledger_by_code.get(row["stock_code"], {})
        manual_status = ledger_row.get("normalized_decision", "") or row.get("manual_review_status", "pending")
        if review_source == "v6_hold_from_high_priority":
            manual_status = "hold_for_review"
        elif review_source == "v7_pending_from_standard":
            manual_status = "pending"
        evidence_count = _int_value(row.get("evidence_count") or ledger_row.get("evidence_row_count"))
        page_count = _int_value(row.get("page_citation_count") or ledger_row.get("page_citation_count"))
        source_pdf_count = _int_value(row.get("source_pdf_count"))
        next_action = _field(row.get("next_action_hint") or row.get("recommended_next_action"), "manual review before any freeze")
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "review_universe_source": review_source,
                "current_layer_status": row.get("v7_proposal_status", row.get("quality_layer", "")),
                "manual_approval_status": manual_status,
                "evidence_count": evidence_count,
                "page_citation_count": page_count,
                "source_pdf_count": source_pdf_count,
                "primary_source_supported": _truthy(row.get("primary_source_supported") or ledger_row.get("primary_source_supported")),
                "hard_tech_domain": _field(row.get("hard_tech_domain")),
                "supply_chain_role_hint": _field(row.get("supply_chain_role_hint")),
                "business_relevance_hint": _field(row.get("business_relevance_hint")),
                "bottleneck_or_chokepoint_hint": _field(row.get("bottleneck_or_chokepoint_hint")),
                "concept_pollution_risk": _field(row.get("concept_pollution_risk"), "not_available"),
                "route_around_or_substitution_risk": _field(row.get("remaining_evidence_gap_flags"), "not_available"),
                "value_capture_risk": "needs_manual_review",
                "disconfirmation_trigger": "risk" in str(row.get("concept_pollution_risk", "")).lower(),
                "next_primary_source_to_check": next_action,
                "recommended_next_action": "manual review evidence package; do not freeze or route to signal",
                "used_for_signal": False,
                "used_for_admission": False,
                "auto_added_to_quality_pool": False,
            }
        )
    return rows


def _completion_status(row: dict[str, Any]) -> tuple[str, bool, str]:
    if not row["primary_source_supported"]:
        return "insufficient_for_review", False, "collect primary-source evidence before workspace review"
    if row["evidence_count"] <= 0 or row["page_citation_count"] <= 0:
        return "needs_evidence_backfill", False, "backfill page-level evidence and source counts before frontend review"
    if row["source_pdf_count"] <= 0:
        return "needs_external_check", False, "resolve source PDF provenance before frontend review"
    role_fields = [
        row["hard_tech_domain"],
        row["supply_chain_role_hint"],
        row["business_relevance_hint"],
        row["bottleneck_or_chokepoint_hint"],
    ]
    if any(value in {"", "evidence_required", "not_available"} for value in role_fields):
        return "needs_role_confirmation", False, "confirm hard-tech domain and supply-chain role before frontend review"
    if row["evidence_count"] < 8 or row["page_citation_count"] < 8:
        return "evidence_light_but_usable", False, "usable for review but should receive more page-level evidence"
    return "frontend_ready", True, "ready for read-only workspace review"


def _build_audit(v5: pd.DataFrame, v7: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    rows = _v5_rows(v5)
    rows.extend(
        _proposal_rows(
            v7,
            ledger,
            candidate_source="v6_hold_for_review_unresolved",
            review_source="v6_hold_from_high_priority",
        )
    )
    rows.extend(
        _proposal_rows(
            v7,
            ledger,
            candidate_source="standard_core_equivalent_v7_candidates",
            review_source="v7_pending_from_standard",
        )
    )
    for row in rows:
        status, ready, action = _completion_status(row)
        row["evidence_completion_status"] = status
        row["frontend_ready"] = ready
        if row["recommended_next_action"] == "":
            row["recommended_next_action"] = action
        elif status != "frontend_ready":
            row["recommended_next_action"] = action
    return pd.DataFrame(rows, columns=AUDIT_COLUMNS).sort_values(["review_universe_source", "stock_code"]).reset_index(drop=True)


def _summary(audit: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    source_counts = audit["review_universe_source"].value_counts().to_dict()
    duplicate_stock_count = int(audit["stock_code"].duplicated().sum())
    used_for_signal_count = int(audit["used_for_signal"].astype(bool).sum())
    used_for_admission_count = int(audit["used_for_admission"].astype(bool).sum())
    auto_added_count = int(audit["auto_added_to_quality_pool"].astype(bool).sum())
    guardrail_violation = (
        source_counts.get("v5_existing", 0) != 300
        or source_counts.get("v6_hold_from_high_priority", 0) != 26
        or source_counts.get("v7_pending_from_standard", 0) != 52
        or len(audit) != 378
        or duplicate_stock_count != 0
        or used_for_signal_count != 0
        or used_for_admission_count != 0
        or auto_added_count != 0
        or not strategy_clean
    )
    if guardrail_violation:
        decision = "blocked_due_to_guardrail_violation"
    elif int((~audit["frontend_ready"].astype(bool)).sum()) > 0:
        decision = "conditionally_ready_with_evidence_gaps"
    else:
        decision = "tech_bottleneck_review_universe_evidence_completion_audit_ready"
    return {
        "task_name": TASK_NAME,
        "quality_pool_v5_reference_count": int(source_counts.get("v5_existing", 0)),
        "v7_proposal_new_candidate_count": int(
            source_counts.get("v6_hold_from_high_priority", 0) + source_counts.get("v7_pending_from_standard", 0)
        ),
        "v6_hold_from_high_priority_count": int(source_counts.get("v6_hold_from_high_priority", 0)),
        "v7_pending_from_standard_count": int(source_counts.get("v7_pending_from_standard", 0)),
        "review_universe_total_count": int(len(audit)),
        "duplicate_stock_count": duplicate_stock_count,
        "frontend_ready_count": int(audit["frontend_ready"].astype(bool).sum()),
        "evidence_gap_queue_count": int((~audit["frontend_ready"].astype(bool)).sum()),
        "evidence_completion_status_counts": {
            key: int(value) for key, value in audit["evidence_completion_status"].value_counts().sort_index().to_dict().items()
        },
        "primary_source_supported_count": int(audit["primary_source_supported"].astype(bool).sum()),
        "page_level_citation_ready_count": int((audit["page_citation_count"].astype(int) > 0).sum()),
        "primary_source_collection_performed": False,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "frozen_quality_pool_generated": False,
        "frontend_write_performed": False,
        "auto_added_to_quality_pool_count": auto_added_count,
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "acceptance_decision": decision,
    }


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    status_counts = summary["evidence_completion_status_counts"]
    lines = [
        "# Tech Bottleneck Review Universe Evidence Completion Audit v1",
        "",
        "## 1. Scope",
        "This audit builds a research-only review universe from quality pool v5 and v7 proposal additions. It does not collect PDFs, run backfill, run equivalence gates, freeze a pool, or connect to signal/admission/scoring/strategy.",
        "",
        "## 2. Review Universe",
        f"- v5_existing: {summary['quality_pool_v5_reference_count']}",
        f"- v6_hold_from_high_priority: {summary['v6_hold_from_high_priority_count']}",
        f"- v7_pending_from_standard: {summary['v7_pending_from_standard_count']}",
        f"- total: {summary['review_universe_total_count']}",
        "",
        "## 3. Evidence Completion Results",
        f"- frontend_ready: {summary['frontend_ready_count']}",
        f"- evidence_gap_queue: {summary['evidence_gap_queue_count']}",
        *[f"- {key}: {value}" for key, value in status_counts.items()],
        "",
        "## 4. Guardrails",
        f"- auto_added_to_quality_pool_count: {summary['auto_added_to_quality_pool_count']}",
        f"- used_for_signal_count: {summary['used_for_signal_count']}",
        f"- used_for_admission_count: {summary['used_for_admission_count']}",
        f"- frozen_quality_pool_generated: {str(summary['frozen_quality_pool_generated']).lower()}",
        f"- frontend_write_performed: {str(summary['frontend_write_performed']).lower()}",
        f"- strategy_file_diff_clean: {str(summary['strategy_file_diff_clean']).lower()}",
        "",
        "## 5. Acceptance Decision",
        summary["acceptance_decision"],
        "",
        "## 6. Recommended Next Steps",
        "1. tech_bottleneck_review_universe_evidence_backfill_v1",
        "2. tech_bottleneck_stock_workspace_review_panel_v1",
        "3. tech_bottleneck_review_universe_manual_review_export_v1",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    v5 = _read_csv(V5_MANIFEST)
    v7 = _read_csv(V7_PROPOSAL)
    ledger = _read_csv(V7_INGEST_LEDGER)

    audit = _build_audit(v5, v7, ledger)
    frontend_ready = audit[audit["frontend_ready"].astype(bool)].copy()
    gap_queue = audit[~audit["frontend_ready"].astype(bool)].copy()

    strategy_clean = _strategy_diff_clean()
    summary = _summary(audit, strategy_clean)
    guardrails = {
        key: summary[key]
        for key in [
            "task_name",
            "quality_pool_v5_reference_count",
            "v7_proposal_new_candidate_count",
            "review_universe_total_count",
            "duplicate_stock_count",
            "primary_source_collection_performed",
            "evidence_backfill_performed",
            "core_equivalence_performed",
            "frozen_quality_pool_generated",
            "frontend_write_performed",
            "auto_added_to_quality_pool_count",
            "used_for_signal_count",
            "used_for_admission_count",
            "price_move_used_for_signal",
            "low_position_used_for_signal",
            "strategy_file_diff_clean",
            "acceptance_decision",
        ]
    }

    audit.to_csv(output_dir / "tech_bottleneck_review_universe_v1.csv", index=False)
    audit.to_csv(output_dir / "tech_bottleneck_review_universe_evidence_completion_audit.csv", index=False)
    gap_queue.to_csv(output_dir / "tech_bottleneck_review_universe_evidence_gap_queue.csv", index=False)
    frontend_ready.to_csv(output_dir / "tech_bottleneck_review_universe_frontend_ready.csv", index=False)
    _write_json(output_dir / "tech_bottleneck_review_universe_evidence_completion_summary.json", summary)
    _write_json(output_dir / "tech_bottleneck_review_universe_evidence_completion_guardrails.json", guardrails)
    _write_report(output_dir / "tech_bottleneck_review_universe_evidence_completion_audit_v1_report.md", summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
