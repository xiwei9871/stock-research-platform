from __future__ import annotations

from hashlib import sha256
import unicodedata
from typing import Any

from stock_research.research_project_v2.errors import ResearchProjectV2Error


RENDERER_VERSION = "industry_cognition_markdown_v1"
REPORT_TITLE = "AI PCB 研究认知基线 v1：AI 系统互连需求侧证据与 PCB 技术缺口"


def _sorted(rows: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    def identity(row: dict[str, Any]) -> str:
        for key in keys:
            value = row.get(key)
            if isinstance(value, str):
                return value
        return ""

    return sorted(rows, key=identity)


def _values(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value or "")


def _evidence_lines(links: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for link in sorted(links, key=lambda row: str(row.get("section_hash", ""))):
        if not link.get("artifact_id"):
            continue
        output.append(
            "Evidence: "
            f"{link['artifact_id']} / {link.get('normalized_document_id')} / "
            f"section {link.get('section_index')} / hash {str(link.get('section_hash'))[:12]}..."
        )
    return output


def render_cognition_report(package: dict[str, Any]) -> bytes:
    framing = package.get("research_framing", {})
    lines = [
        f"# {REPORT_TITLE}",
        "",
        "## 1. 研究问题与边界",
        "",
        f"- Topic: {framing.get('topic', '')}",
        f"- Objective: {framing.get('objective', '')}",
        f"- Model scope: {framing.get('model_scope', '')}",
        f"- Included: {_values(framing.get('included_scope', []))}",
        f"- Excluded: {_values(framing.get('excluded_scope', []))}",
        f"- Limitations: {_values(framing.get('limitations', []))}",
        "",
        "## 2. Evidence-grounded claims",
        "",
    ]
    for claim in _sorted(package.get("claim_assessment_ledger", []), "claim_id"):
        grounded = claim.get("grounding_status") == "grounded"
        label = "[GROUNDED]" if grounded else "[OPEN / NOT GROUNDED]"
        lines.extend(
            [
                f"### {label} [claim: {claim.get('claim_id')} ]",
                "",
                str(claim.get("claim_text", "")),
                "",
                f"- Type: {claim.get('claim_type')}",
                f"- Status: {claim.get('assessment_status')}",
                f"- Confidence: {claim.get('assessment_confidence')}",
                f"- Limitations: {_values(claim.get('limitations', []))}",
            ]
        )
        lines.extend(_evidence_lines(claim.get("evidence_links", [])))
        lines.append("")
    lines.extend(["## 3. Evidence-grounded technical mechanisms", ""])
    for mechanism in _sorted(
        package.get("evidence_grounded_mechanisms", []), "mechanism_id"
    ):
        lines.extend(
            [
                f"### [GROUNDED] {mechanism.get('mechanism_id')}: {mechanism.get('name', '')}",
                "",
                str(mechanism.get("summary", mechanism.get("problem_being_solved", ""))),
                "",
            ]
        )
        for step in mechanism.get("explanation_steps", []):
            lines.append(
                f"- {step.get('statement')} [claims: {_values(step.get('supporting_claim_ids', []))}]"
            )
        lines.extend(
            [
                f"- Tradeoffs: {_values(mechanism.get('tradeoffs', []))}",
                f"- Scope: {mechanism.get('applicable_scope', '')}",
                f"- Confidence: {mechanism.get('confidence', '')}",
                "",
            ]
        )
    lines.extend(["## 4. Grounded causal analysis", ""])
    for edge in _sorted(package.get("grounded_causal_edges", []), "edge_id"):
        lines.extend(
            [
                f"### [GROUNDED] {edge.get('edge_id')}",
                "",
                f"{edge.get('from_node')} → {edge.get('to_node')}",
                "",
                f"- Mechanism: {edge.get('mechanism_id')}",
                f"- Necessary conditions: {_values(edge.get('necessary_conditions', []))}",
                f"- Alternatives: {_values(edge.get('alternative_explanations', []))}",
                f"- Failure conditions: {_values(edge.get('failure_conditions', []))}",
                "",
            ]
        )
    lines.extend(["## 5. Technology route comparisons", ""])
    for route in _sorted(package.get("technology_route_comparisons", []), "comparison_id"):
        lines.extend(
            [
                f"### {route.get('comparison_id')}: {route.get('title', '')}",
                "",
                str(route.get("current_evidence_tendency", "")),
                "",
                f"- Tradeoffs: {_values(route.get('tradeoffs', []))}",
                f"- Unresolved: {_values(route.get('unresolved_questions', []))}",
                "",
            ]
        )
    lines.extend(["## 6. Limited system bottleneck judgments", ""])
    for judgment in _sorted(
        package.get("limited_system_bottleneck_judgments", []), "bottleneck_id"
    ):
        lines.extend(
            [
                f"### [LIMITED JUDGMENT] {judgment.get('bottleneck_id')}",
                "",
                str(judgment.get("why_it_is_a_bottleneck", "")),
                "",
                f"- Status: {judgment.get('status')}",
                f"- Counterarguments: {_values(judgment.get('counterarguments', []))}",
                f"- Invalidation: {_values(judgment.get('invalidation_conditions', []))}",
                "",
            ]
        )
    lines.extend(["## 7. Unverified mechanism skeletons", ""])
    for skeleton in _sorted(
        package.get("unverified_mechanism_skeletons", []), "skeleton_id"
    ):
        lines.extend(
            [
                f"### [SKELETON — NOT VERIFIED] {skeleton.get('skeleton_id')}",
                "",
                str(skeleton.get("research_question", "")),
                "",
                f"- Candidate variables: {_values(skeleton.get('candidate_variables', []))}",
                f"- Required evidence: {_values(skeleton.get('required_evidence_types', []))}",
                f"- Gap IDs: {_values(skeleton.get('evidence_gap_ids', []))}",
                "",
            ]
        )
    lines.extend(["## 8. Hypothesized causal edges and value questions", ""])
    for edge in _sorted(package.get("hypothesized_causal_edges", []), "edge_id"):
        lines.append(
            f"- [HYPOTHESIS] {edge.get('edge_id')}: {edge.get('from_node')} → {edge.get('to_node')} | gaps: {_values(edge.get('evidence_gap_ids', []))}"
        )
    for hypothesis in _sorted(package.get("value_change_hypotheses", []), "hypothesis_id"):
        lines.append(
            f"- [VALUE QUESTION] {hypothesis.get('hypothesis_id')}: {hypothesis.get('hypothesis_text', '')} | status: {hypothesis.get('status')}"
        )
    lines.extend(["", "## 9. Evidence gaps", ""])
    for gap in _sorted(package.get("evidence_gap_referrals", []), "gap_id"):
        lines.extend(
            [
                f"### [EVIDENCE GAP] {gap.get('gap_id')}",
                "",
                str(gap.get("blocked_question", "")),
                "",
                f"- Why insufficient: {gap.get('why_insufficient', '')}",
                f"- Required evidence: {_values(gap.get('required_evidence_types', []))}",
                "",
            ]
        )
    lines.extend(["## 10. Contradictions and uncertainty", ""])
    for item in _sorted(
        package.get("contradictions_and_uncertainties", []), "uncertainty_id"
    ):
        lines.append(
            f"- [UNCERTAINTY] {item.get('uncertainty_id')}: {item.get('summary', '')}"
        )
    lines.extend(["", "## 11. Verification and falsification", ""])
    for item in _sorted(
        package.get("verification_and_falsification", []), "verification_id"
    ):
        lines.append(
            f"- {item.get('verification_id')}: {item.get('metric', '')}; invalidation: {_values(item.get('invalidation_conditions', []))}"
        )
    lines.extend(
        [
            "",
            "## 12. Current bounded conclusion",
            "",
            str(framing.get("bounded_conclusion", "")),
        ]
    )
    normalized = unicodedata.normalize("NFC", "\n".join(lines).replace("\r\n", "\n"))
    return (normalized.rstrip("\n") + "\n").encode("utf-8")


def canonical_render_hash(package: dict[str, Any]) -> str:
    return sha256(render_cognition_report(package)).hexdigest()


def validate_persisted_report(
    package: dict[str, Any], report_bytes: bytes
) -> None:
    expected = render_cognition_report(package)
    if report_bytes != expected:
        raise ResearchProjectV2Error(
            "Persisted cognition report differs from the canonical projection",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            details={
                "field": "report",
                "expected_hash": sha256(expected).hexdigest(),
                "actual_hash": sha256(report_bytes).hexdigest(),
            },
        )
