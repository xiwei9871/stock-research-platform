from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any
import unicodedata

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.cognition import validate_cognition_package
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import (
    read_layered_bytes,
    read_layered_canonical_json,
)


FIXED_GAP_GROUPS = {
    "GAP-SIGNAL": "group_a_signal_transmission",
    "GAP-LOSS": "group_a_signal_transmission",
    "GAP-LAYERS": "group_a_signal_transmission",
    "GAP-LAMINATE": "group_b_material_capability",
    "GAP-BACKDRILL": "group_c_manufacturing_testing",
    "GAP-LAMINATION": "group_c_manufacturing_testing",
    "GAP-THERMAL": "group_c_manufacturing_testing",
    "GAP-TEST": "group_c_manufacturing_testing",
    "GAP-YIELD": "group_c_manufacturing_testing",
    "GAP-CAPACITY": "group_d_bottleneck_effective_capacity",
}
PUBLIC_AVAILABILITY = {
    "likely_publicly_available",
    "partially_publicly_available",
    "unlikely_publicly_available",
    "structurally_limited",
    "unknown",
}
PUBLIC_EVIDENCE_CEILINGS = {
    "technical_understanding_only",
    "engineering_difficulty_only",
    "manufacturing_capability_bounded",
    "structurally_limited",
    "unknown",
}
COGNITION_LEVELS_BY_GROUP = {
    "group_a_signal_transmission": {"technical_understanding"},
    "group_b_material_capability": {"technical_understanding"},
    "group_c_manufacturing_testing": {
        "technical_understanding",
        "manufacturing_difficulty",
        "manufacturing_capability_bounded",
    },
    "group_d_bottleneck_effective_capacity": {
        "technical_understanding",
        "manufacturing_difficulty",
        "manufacturing_capability_bounded",
        "effective_capacity_bounded",
    },
}
GAP_REQUIRED_FIELDS = (
    "original_gap_description",
    "current_grounded_knowledge",
    "current_unknowns",
    "atomic_research_questions",
    "new_evidence_requirement_ids",
    "required_atomic_facts",
    "required_evidence_types",
    "suggested_source_classes",
    "suggested_search_concepts",
    "source_independence_requirements",
    "freshness_requirements",
    "scope_and_generation_requirements",
    "comparison_denominator",
    "minimum_sufficiency_conditions",
    "contradiction_search_requirements",
    "stop_conditions",
    "non_derivable_conclusions",
    "priority",
    "priority_reason",
)
ER_REQUIRED_FIELDS = (
    "research_question",
    "claim_scope",
    "required_fact_types",
    "required_source_classes",
    "freshness_rule",
    "comparison_scope",
    "denominator_rule",
    "sufficiency_rule",
    "contradiction_rule",
    "stop_rule",
    "maximum_supported_cognition_level",
    "prohibited_inferences",
)


def _error(message: str, *, code: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(message, code=code, details=details)


def validate_gap_universe(
    gap_reviews: list[dict[str, Any]],
    expected_groups: dict[str, str],
) -> list[str]:
    if not all(isinstance(row, dict) for row in gap_reviews):
        raise _error(
            "Gap reviews must contain objects",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
        )
    ids = [row.get("gap_id") for row in gap_reviews]
    if len(ids) != len(set(ids)):
        raise _error(
            "Gap review IDs must be unique",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
        )
    if set(ids) != set(expected_groups):
        raise _error(
            "Gap review universe differs from the frozen cognition gaps",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
            missing=sorted(set(expected_groups) - set(ids)),
            unexpected=sorted(set(ids) - set(expected_groups)),
        )
    wrong = sorted(
        gap_id
        for gap_id, expected_group in expected_groups.items()
        if next(row for row in gap_reviews if row["gap_id"] == gap_id).get("gap_group")
        != expected_group
    )
    if wrong:
        raise _error(
            "Gap review group assignment differs from the frozen design",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
            gap_ids=wrong,
        )
    return sorted(ids)


def validate_input_bindings(
    artifact: dict[str, Any],
    *,
    layout: LayeredResearchLayout,
) -> dict[str, Any]:
    bindings = artifact.get("input_bindings")
    if not isinstance(bindings, dict):
        raise _error(
            "Gap review input bindings are missing",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
        )
    package = read_layered_canonical_json(
        str(bindings.get("cognition_package_path")), layout=layout
    )
    if package.get("content_hash") != bindings.get("cognition_package_hash"):
        raise _error(
            "Cognition package binding drifted",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
            field="cognition_package_hash",
        )
    validate_cognition_package(package, layout=layout)

    audit = read_layered_canonical_json(
        str(bindings.get("cognition_audit_path")), layout=layout
    )
    if audit.get("content_hash") != bindings.get("cognition_audit_hash"):
        raise _error(
            "Cognition audit binding drifted",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
            field="cognition_audit_hash",
        )
    report = read_layered_bytes(
        str(bindings.get("cognition_report_path")), layout=layout
    )
    if sha256(report).hexdigest() != bindings.get("cognition_report_hash"):
        raise _error(
            "Cognition report binding drifted",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
            field="cognition_report_hash",
        )
    checkpoint_id = bindings.get("acquisition_checkpoint_id")
    checkpoint = read_layered_canonical_json(
        f"acquisition/checkpoints/{checkpoint_id}.json", layout=layout
    ).get("acquisition_checkpoint")
    if not isinstance(checkpoint, dict) or checkpoint.get("content_hash") != bindings.get(
        "acquisition_checkpoint_hash"
    ):
        raise _error(
            "Acquisition checkpoint binding drifted",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
            field="acquisition_checkpoint_hash",
        )
    return package


def _require_nonempty(row: dict[str, Any], fields: tuple[str, ...], *, identity: str) -> None:
    for field in fields:
        value = row.get(field)
        if value is None or value == "" or value == []:
            raise _error(
                "Research design field must be non-empty",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                identity=identity,
                field=field,
            )


def validate_research_design(artifact: dict[str, Any]) -> dict[str, int]:
    gap_reviews = artifact.get("gap_reviews")
    requirements = artifact.get("evidence_requirements")
    if not isinstance(gap_reviews, list) or not isinstance(requirements, list):
        raise _error(
            "Gap reviews and evidence requirements must be arrays",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
        )
    validate_gap_universe(gap_reviews, FIXED_GAP_GROUPS)
    expected_group_ids = set(FIXED_GAP_GROUPS.values())
    groups = artifact.get("group_definitions")
    if not isinstance(groups, list) or {
        row.get("group_id") for row in groups if isinstance(row, dict)
    } != expected_group_ids:
        raise _error(
            "Research design must declare the four frozen groups",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
        )

    er_by_id: dict[str, dict[str, Any]] = {}
    for er in requirements:
        if not isinstance(er, dict) or not isinstance(er.get("er_id"), str):
            raise _error(
                "Evidence requirement identity is invalid",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
            )
        er_id = er["er_id"]
        if er_id in er_by_id:
            raise _error(
                "Evidence requirement IDs must be unique",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                er_id=er_id,
            )
        _require_nonempty(er, ER_REQUIRED_FIELDS, identity=er_id)
        if not isinstance(er.get("minimum_independent_evidence_chains"), int) or er[
            "minimum_independent_evidence_chains"
        ] < 1:
            raise _error(
                "Evidence requirement needs an independence threshold",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                er_id=er_id,
            )
        if not isinstance(er.get("supplier_independent_source_required"), bool):
            raise _error(
                "Evidence requirement independence policy is missing",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                er_id=er_id,
            )
        er_by_id[er_id] = er

    question_ids: set[str] = set()
    used_er_ids: set[str] = set()
    gap_ids = set(FIXED_GAP_GROUPS)
    for gap in gap_reviews:
        gap_id = gap["gap_id"]
        _require_nonempty(gap, GAP_REQUIRED_FIELDS, identity=gap_id)
        if gap.get("public_evidence_availability") not in PUBLIC_AVAILABILITY:
            raise _error(
                "Public evidence availability is not an allowed design status",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                gap_id=gap_id,
            )
        if gap.get("public_evidence_ceiling") not in PUBLIC_EVIDENCE_CEILINGS:
            raise _error(
                "Public evidence ceiling is not an allowed design status",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                gap_id=gap_id,
            )
        if gap_id in {"GAP-YIELD", "GAP-CAPACITY"} and (
            gap.get("public_evidence_availability") != "structurally_limited"
            or gap.get("public_evidence_ceiling") != "structurally_limited"
        ):
            raise _error(
                "Yield and effective-capacity gaps must retain a structural public limit",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                gap_id=gap_id,
            )
        if gap.get("future_acquisition_authorized") is not False:
            raise _error(
                "Gap review cannot authorize acquisition",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_SCOPE_VIOLATION",
                gap_id=gap_id,
            )
        dependencies = gap.get("dependencies", [])
        if not isinstance(dependencies, list) or not set(dependencies) <= gap_ids - {gap_id}:
            raise _error(
                "Gap dependencies must reference other frozen gaps",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                gap_id=gap_id,
            )
        linked_er_ids = gap.get("new_evidence_requirement_ids")
        if not isinstance(linked_er_ids, list) or not linked_er_ids:
            raise _error(
                "Gap review must link atomic evidence requirements",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                gap_id=gap_id,
            )
        for er_id in linked_er_ids:
            if er_id not in er_by_id or er_id in used_er_ids or er_by_id[er_id].get(
                "gap_id"
            ) != gap_id:
                raise _error(
                    "Evidence requirement must belong to exactly one gap",
                    code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                    gap_id=gap_id,
                    er_id=er_id,
                )
            if er_by_id[er_id].get("maximum_supported_cognition_level") not in (
                COGNITION_LEVELS_BY_GROUP[gap["gap_group"]]
            ):
                raise _error(
                    "Evidence requirement exceeds its group's cognition ceiling",
                    code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_SCOPE_VIOLATION",
                    gap_id=gap_id,
                    er_id=er_id,
                )
            used_er_ids.add(er_id)
        questions = gap.get("atomic_research_questions")
        if not isinstance(questions, list) or not all(isinstance(row, dict) for row in questions):
            raise _error(
                "Atomic research questions must be objects",
                code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                gap_id=gap_id,
            )
        for question in questions:
            question_id = question.get("question_id")
            refs = question.get("evidence_requirement_ids")
            if (
                not isinstance(question_id, str)
                or question_id in question_ids
                or not question.get("question")
                or not isinstance(refs, list)
                or not refs
                or not set(refs) <= set(linked_er_ids)
            ):
                raise _error(
                    "Atomic research question is incomplete or not gap-scoped",
                    code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
                    gap_id=gap_id,
                )
            question_ids.add(question_id)
    if used_er_ids != set(er_by_id):
        raise _error(
            "Every evidence requirement must be linked by exactly one gap",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
            unlinked=sorted(set(er_by_id) - used_er_ids),
        )
    governance = artifact.get("governance")
    if not isinstance(governance, dict) or any(value is not False for value in governance.values()):
        raise _error(
            "Gap review governance must remain fully unauthorized",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_SCOPE_VIOLATION",
        )
    return {
        "gap_count": len(gap_reviews),
        "atomic_question_count": len(question_ids),
        "evidence_requirement_count": len(er_by_id),
    }


def _values(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value or "")


def render_gap_review_report(artifact: dict[str, Any]) -> bytes:
    policy = artifact.get("execution_policy", {})
    governance = artifact.get("governance", {})
    lines = [
        "# AI PCB 证据缺口审查与定向研究设计基线 v1",
        "",
        "> [RESEARCH DESIGN — NOT EVIDENCE] 本报告是集成 artifact 的确定性只读投影，不包含新增证据、瓶颈结论或价值迁移判断。",
        "",
        "## 1. Execution boundary",
        "",
        f"- Execution mode: {policy.get('execution_mode', '')}",
        f"- Network access: {policy.get('network_access')}",
        f"- New acquisition: {policy.get('new_acquisition')}",
        f"- Evidence assessment of new sources: {policy.get('evidence_assessment_of_new_sources')}",
        "",
        "## 2. Fixed research groups",
        "",
    ]
    for group in sorted(artifact.get("group_definitions", []), key=lambda row: row["group_id"]):
        lines.extend(
            [
                f"### {group.get('group_id')}: {group.get('name', '')}",
                "",
                str(group.get("purpose", "")),
                "",
            ]
        )
    lines.extend(["## 3. Gap reviews", ""])
    for gap in sorted(artifact.get("gap_reviews", []), key=lambda row: row["gap_id"]):
        lines.extend(
            [
                f"### [RESEARCH DESIGN — NOT EVIDENCE] {gap['gap_id']}",
                "",
                f"- Group: {gap.get('gap_group')}",
                f"- Original gap: {gap.get('original_gap_description')}",
                f"- Current grounded knowledge: {_values(gap.get('current_grounded_knowledge'))}",
                f"- Current unknowns: {_values(gap.get('current_unknowns'))}",
                f"- Public evidence availability: {gap.get('public_evidence_availability')}",
                f"- Public evidence ceiling: {gap.get('public_evidence_ceiling')}",
                f"- Comparison denominator: {gap.get('comparison_denominator')}",
                f"- Required evidence types: {_values(gap.get('required_evidence_types'))}",
                f"- Suggested source classes: {_values(gap.get('suggested_source_classes'))}",
                f"- Minimum sufficiency: {_values(gap.get('minimum_sufficiency_conditions'))}",
                f"- Stop conditions: {_values(gap.get('stop_conditions'))}",
                f"- Non-derivable conclusions: {_values(gap.get('non_derivable_conclusions'))}",
                f"- Priority: {gap.get('priority')} — {gap.get('priority_reason')}",
                f"- Dependencies: {_values(gap.get('dependencies'))}",
                f"- Future acquisition authorized: {gap.get('future_acquisition_authorized')}",
                "",
                "Atomic research questions:",
                "",
            ]
        )
        for question in sorted(
            gap.get("atomic_research_questions", []), key=lambda row: row["question_id"]
        ):
            lines.append(
                f"- {question['question_id']}: {question.get('question')} "
                f"[ER: {_values(question.get('evidence_requirement_ids'))}]"
            )
        lines.append("")
    lines.extend(["## 4. Atomic Evidence Requirements", ""])
    for er in sorted(artifact.get("evidence_requirements", []), key=lambda row: row["er_id"]):
        lines.extend(
            [
                f"### {er['er_id']} ({er.get('gap_id')})",
                "",
                str(er.get("research_question", "")),
                "",
                f"- Claim scope: {er.get('claim_scope')}",
                f"- Required fact types: {_values(er.get('required_fact_types'))}",
                f"- Required source classes: {_values(er.get('required_source_classes'))}",
                f"- Independent evidence chains: {er.get('minimum_independent_evidence_chains')}",
                f"- Supplier-independent source required: {er.get('supplier_independent_source_required')}",
                f"- Freshness: {er.get('freshness_rule')}",
                f"- Comparison scope: {er.get('comparison_scope')}",
                f"- Denominator: {er.get('denominator_rule')}",
                f"- Sufficiency: {er.get('sufficiency_rule')}",
                f"- Contradiction search: {er.get('contradiction_rule')}",
                f"- Stop rule: {er.get('stop_rule')}",
                f"- Maximum supported cognition level: {er.get('maximum_supported_cognition_level')}",
                f"- Prohibited inferences: {_values(er.get('prohibited_inferences'))}",
                "",
            ]
        )
    lines.extend(["## 5. Source-class boundaries", ""])
    for row in sorted(
        artifact.get("source_class_boundaries", []), key=lambda item: item["source_class"]
    ):
        lines.append(
            f"- {row['source_class']}: can support {_values(row.get('can_support'))}; "
            f"cannot support {_values(row.get('cannot_support'))}."
        )
    lines.extend(["", "## 6. Cross-level inference prohibitions", ""])
    for row in sorted(
        artifact.get("cross_level_inference_rules", []), key=lambda item: item["rule_id"]
    ):
        lines.append(
            f"- {row['rule_id']}: {row.get('from_level')} != "
            f"{row.get('prohibited_target_level')} — {row.get('reason')}"
        )
    lines.extend(["", "## 7. Stopping states", ""])
    for row in sorted(
        artifact.get("stopping_state_definitions", []), key=lambda item: item["state"]
    ):
        lines.append(f"- {row['state']}: {row.get('meaning')}")
    lines.extend(
        [
            "",
            "## 8. Governance",
            "",
            f"- Future acquisition authorized: {governance.get('future_acquisition_authorized')}",
            f"- Stage A2 authorized: {governance.get('stage_a2_authorized')}",
            f"- Stage B authorized: {governance.get('stage_b_authorized')}",
            f"- Company mapping authorized: {governance.get('company_mapping_authorized')}",
            f"- Bottleneck judgment authorized: {governance.get('bottleneck_judgment_authorized')}",
            f"- Value migration judgment authorized: {governance.get('value_migration_judgment_authorized')}",
        ]
    )
    normalized = unicodedata.normalize("NFC", "\n".join(lines).replace("\r\n", "\n"))
    return (normalized.rstrip("\n") + "\n").encode("utf-8")


def validate_persisted_gap_review_report(
    artifact: dict[str, Any], report_bytes: bytes
) -> None:
    expected = render_gap_review_report(artifact)
    if report_bytes != expected:
        raise _error(
            "Persisted gap-review report differs from deterministic projection",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
            expected_hash=sha256(expected).hexdigest(),
            actual_hash=sha256(report_bytes).hexdigest(),
        )


__all__ = [
    "FIXED_GAP_GROUPS",
    "validate_gap_universe",
    "validate_input_bindings",
    "validate_research_design",
    "render_gap_review_report",
    "validate_persisted_gap_review_report",
]
