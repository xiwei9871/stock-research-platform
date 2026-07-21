from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error


DOMAIN_MATRIX_VERSION = "industry_cognition_domains_v1"
CAPABILITY_RULE_VERSION = "industry_cognition_capability_v1"
AUDIT_QUESTION_SET_VERSION = "industry_cognition_audit_questions_v1"
DOMAINS = (
    "ai_system_architecture",
    "accelerator_interconnect",
    "network_fabric",
    "dpu",
    "optical_boundary",
    "signal_integrity",
    "pcb_materials",
    "pcb_manufacturing",
    "pcb_testing",
    "yield",
    "effective_capacity",
)


def compute_domain_coverage(package: dict[str, Any]) -> list[dict[str, Any]]:
    grounded: dict[str, list[str]] = {}
    for row in package.get("evidence_grounded_mechanisms", []):
        grounded.setdefault(row.get("domain"), []).append(row.get("mechanism_id"))
    skeletons: dict[str, list[str]] = {}
    for row in package.get("unverified_mechanism_skeletons", []):
        skeletons.setdefault(row.get("domain"), []).append(row.get("skeleton_id"))
    gaps: dict[str, list[str]] = {}
    for row in package.get("evidence_gap_referrals", []):
        gaps.setdefault(row.get("domain"), []).append(row.get("gap_id"))
    conflicts: dict[str, list[str]] = {}
    for row in package.get("contradictions_and_uncertainties", []):
        if row.get("uncertainty_type") == "material_conflict":
            conflicts.setdefault(row.get("domain"), []).append(row.get("uncertainty_id"))
    output: list[dict[str, Any]] = []
    for domain in DOMAINS:
        if conflicts.get(domain):
            status = "conflicted"
        elif grounded.get(domain):
            status = "evidence_grounded"
        elif skeletons.get(domain):
            status = "unverified_skeleton_only"
        else:
            status = "not_assessable"
        output.append(
            {
                "domain": domain,
                "status": status,
                "supporting_object_ids": sorted(grounded.get(domain, [])),
                "skeleton_object_ids": sorted(skeletons.get(domain, [])),
                "blocking_gap_ids": sorted(gaps.get(domain, [])),
                "conflict_ids": sorted(conflicts.get(domain, [])),
            }
        )
    return output


def compute_capability(
    package: dict[str, Any], coverage: list[dict[str, Any]]
) -> dict[str, Any]:
    states = {row["domain"]: row["status"] for row in coverage}
    demand_domains = {
        "ai_system_architecture",
        "accelerator_interconnect",
        "network_fabric",
        "dpu",
        "optical_boundary",
    }
    demand_grounded = all(states.get(domain) == "evidence_grounded" for domain in demand_domains)
    signal_state = states.get("signal_integrity", "not_assessable")
    pcb_domains = {
        "pcb_materials",
        "pcb_manufacturing",
        "pcb_testing",
        "yield",
        "effective_capacity",
    }
    pcb_grounded = all(states.get(domain) == "evidence_grounded" for domain in pcb_domains)
    full = demand_grounded and pcb_grounded and not package.get("hypothesized_causal_edges")
    return {
        "overall_capability": (
            "full_industry_cognition" if full else "partial_industry_cognition_demand_side_only"
        ),
        "ai_system_interconnect_cognition": (
            "evidence_grounded" if demand_grounded else "partial_or_not_assessable"
        ),
        "signal_integrity_and_pcb_mechanism_cognition": signal_state,
        "pcb_material_and_manufacturing_cognition": (
            "evidence_grounded" if pcb_grounded else "not_assessable"
        ),
        "pcb_industry_bottleneck_judgment": (
            "available" if pcb_grounded else "not_available"
        ),
        "full_ai_pcb_industry_cognition": "achieved" if full else "not_achieved",
        "company_mapping_readiness": bool(full and not package.get("evidence_gap_referrals")),
        "next_required_action": "company_mapping_review" if full else "evidence_gap_review",
        "automatic_gap_acquisition_authorized": False,
    }


def _answer(
    question_id: str,
    computed_answer: str,
    status: str,
    supporting: list[str],
    blocking: list[str],
    rule: str,
) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "computed_answer": computed_answer,
        "answer_status": status,
        "supporting_object_ids": sorted(supporting),
        "blocking_object_ids": sorted(blocking),
        "calculation_rule": rule,
    }


def compute_audit(package: dict[str, Any], report_bytes: bytes) -> dict[str, Any]:
    coverage = compute_domain_coverage(package)
    capability = compute_capability(package, coverage)
    grounded_ids = [
        row.get("mechanism_id") for row in package.get("evidence_grounded_mechanisms", [])
    ]
    skeleton_ids = [
        row.get("skeleton_id") for row in package.get("unverified_mechanism_skeletons", [])
    ]
    gap_ids = [row.get("gap_id") for row in package.get("evidence_gap_referrals", [])]
    hypothesized_ids = [
        row.get("edge_id") for row in package.get("hypothesized_causal_edges", [])
    ]
    audit = {
        "schema_version": "2.5.0",
        "artifact_type": "industry_cognition_audit",
        "audit_id": "industry_cognition_audit:ai_pcb:v1",
        "package_id": package["package_id"],
        "package_content_hash": package["content_hash"],
        "report_content_hash": sha256(report_bytes).hexdigest(),
        "renderer_version": package["renderer_version"],
        "capability_rule_version": CAPABILITY_RULE_VERSION,
        "domain_matrix_version": DOMAIN_MATRIX_VERSION,
        "audit_question_set_version": AUDIT_QUESTION_SET_VERSION,
        "domain_coverage": coverage,
        "computed_capability": capability,
        "coverage_metrics": {
            "claim_count": len(package.get("claim_assessment_ledger", [])),
            "grounded_mechanism_count": len(grounded_ids),
            "skeleton_count": len(skeleton_ids),
            "grounded_causal_edge_count": len(package.get("grounded_causal_edges", [])),
            "hypothesized_causal_edge_count": len(hypothesized_ids),
            "bottleneck_judgment_count": len(
                package.get("limited_system_bottleneck_judgments", [])
            ),
            "evidence_gap_count": len(gap_ids),
        },
        "audit_answers": [
            _answer("AUD-Q01", capability["overall_capability"], "bounded", grounded_ids, gap_ids, "Grounded domain coverage minus critical gaps."),
            _answer("AUD-Q02", "unverified_mechanism_skeletons", "identified", skeleton_ids, [], "Skeleton objects never contribute grounded coverage."),
            _answer("AUD-Q03", "pcb_material_manufacturing_test_yield", "missing_evidence", [], gap_ids, "Critical PCB-domain gaps remain not assessable."),
            _answer("AUD-Q04", "hypothesized_edges_remain_unverified", "open", [], hypothesized_ids, "Hypothesized edges are physically excluded from grounded graph."),
            _answer("AUD-Q05", capability["pcb_industry_bottleneck_judgment"], "not_available", [], gap_ids, "PCB bottleneck requires grounded material/manufacturing/test/yield domains."),
            _answer("AUD-Q06", "not_eligible_for_judgment", "not_available", [], gap_ids, "Value migration requires grounded PCB mechanism and quantitative evidence."),
            _answer("AUD-Q07", "report_is_bounded_projection", "checked", grounded_ids, gap_ids, "Canonical report is regenerated only from package objects."),
            _answer("AUD-Q08", capability["next_required_action"], "required", [], gap_ids, "Highest-priority blocking gaps require human review before acquisition."),
        ],
        "violations": [],
        "warnings": sorted(
            row.get("uncertainty_id")
            for row in package.get("contradictions_and_uncertainties", [])
            if row.get("uncertainty_id")
        ),
        "content_hash": "0" * 64,
    }
    audit["content_hash"] = content_sha256(audit, excluded_paths={("content_hash",)})
    return audit


def validate_persisted_audit(
    audit: dict[str, Any], expected: dict[str, Any]
) -> None:
    if canonical_bytes(audit) != canonical_bytes(expected):
        raise ResearchProjectV2Error(
            "Persisted cognition audit differs from the deterministic audit",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            details={"field": "audit"},
        )
