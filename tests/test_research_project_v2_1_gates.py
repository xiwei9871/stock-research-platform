from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import shutil

import pytest

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.gates import (
    INDUSTRY_DESIGN_CHECKS,
    evaluate_industry_design_gate,
    evaluate_industry_design_gate_unverified,
)


EXPECTED_CHECKS = (
    "INDUSTRY_LAYER_CORRECT",
    "INDUSTRY_UPSTREAM_BASELINE_RESOLVED",
    "INDUSTRY_PRIMARY_QUESTION_PRESENT",
    "INDUSTRY_SCOPE_EXCLUDES_COMPANY_STOCK_RATING",
    "INDUSTRY_REQUIRED_QUESTIONS_COVERED",
    "INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS",
    "INDUSTRY_COUNTER_SEARCH_PRESENT",
    "INDUSTRY_SOURCE_CLASS_DIVERSITY",
    "INDUSTRY_VALIDATION_PLAN_PRESENT",
    "INDUSTRY_INVALIDATION_PLAN_PRESENT",
    "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS",
    "INDUSTRY_PROVENANCE_COMPLETE",
)

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "artifacts/research_projects/v2_1/projects/ai_compute_pcb_industry_bottleneck"


def _pilot() -> tuple[dict, dict]:
    return (
        json.loads((PROJECT / "project.json").read_text()),
        json.loads((PROJECT / "versions/v0.1.0.json").read_text()),
    )


def _failed_checks(identity: dict, version: dict) -> set[str]:
    result = evaluate_industry_design_gate_unverified(identity, version)
    return {check["code"] for check in result["checks"] if check["status"] == "fail"}


def test_industry_gate_exports_fixed_check_order() -> None:
    assert INDUSTRY_DESIGN_CHECKS == EXPECTED_CHECKS


def test_unverified_gate_cannot_claim_verified_provenance() -> None:
    identity, version = _pilot()

    result = evaluate_industry_design_gate_unverified(identity, version)

    assert result["gate"] == "industry_design_unverified"
    assert result["status"] == "pass"
    assert result.get("verified") is False


def test_industry_gate_does_not_mutate_input(monkeypatch) -> None:
    version = {"snapshot": {}}
    identity = {}
    before = deepcopy((identity, version))
    monkeypatch.setattr(
        "stock_research.research_project_v2_1.gates.resolve_upstream_r1_version",
        lambda reference: {},
    )
    evaluate_industry_design_gate(identity, version)
    assert (identity, version) == before


def test_pilot_passes_all_twelve_checks() -> None:
    identity, version = _pilot()
    result = evaluate_industry_design_gate(
        identity,
        version,
        layout=LayeredResearchLayout.default(),
    )
    assert result["status"] == "pass"
    assert [check["code"] for check in result["checks"]] == list(EXPECTED_CHECKS)
    assert {check["status"] for check in result["checks"]} == {"pass"}


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        (lambda identity, version: identity.update(research_layer="company_capture"), "INDUSTRY_LAYER_CORRECT"),
        (lambda identity, version: version["snapshot"].update(upstream_research_refs=[]), "INDUSTRY_UPSTREAM_BASELINE_RESOLVED"),
        (lambda identity, version: version["snapshot"]["search_plans"][0]["queries"].pop(2), "INDUSTRY_COUNTER_SEARCH_PRESENT"),
        (lambda identity, version: version["snapshot"]["search_plans"][0]["queries"][0].update(query_text="industry target price"), "INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS"),
        (lambda identity, version: version["snapshot"].update(company_capability_collection=[]), "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS"),
    ],
)
def test_industry_gate_reports_the_targeted_failure(mutation, expected_check) -> None:
    identity, version = _pilot()
    mutation(identity, version)
    result = evaluate_industry_design_gate_unverified(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert expected_check in failed


def test_missing_counter_does_not_cascade_into_plan_coverage() -> None:
    identity, version = _pilot()
    version["snapshot"]["search_plans"][0]["queries"] = [
        query for query in version["snapshot"]["search_plans"][0]["queries"]
        if query["query_role"] != "counter_evidence"
    ]
    result = evaluate_industry_design_gate_unverified(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert failed == {"INDUSTRY_COUNTER_SEARCH_PRESENT"}


@pytest.mark.parametrize(
    "forbidden_key",
    ["stock_recommendations", "company_rankings", "company_output_collection", "listed_company_candidates"],
)
def test_output_gate_rejects_downstream_key_variants(forbidden_key: str) -> None:
    identity, version = _pilot()
    version["snapshot"][forbidden_key] = []
    result = evaluate_industry_design_gate_unverified(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in failed


def test_output_gate_allows_company_background_reference_metadata() -> None:
    identity, version = _pilot()
    version["snapshot"]["listed_company_reference"] = {"role": "background"}
    result = evaluate_industry_design_gate_unverified(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in failed


def test_source_diversity_checks_each_query_source_contract() -> None:
    identity, version = _pilot()
    version["snapshot"]["search_plans"][0]["queries"][0]["source_classes"].pop()
    result = evaluate_industry_design_gate_unverified(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert failed == {"INDUSTRY_SOURCE_CLASS_DIVERSITY"}


def test_initial_design_provenance_must_bind_to_current_version() -> None:
    identity, version = _pilot()
    question = version["snapshot"]["questions"][0]
    question["provenance"]["created_in_version"] = "research_version:other:0.1.0"

    result = evaluate_industry_design_gate_unverified(identity, version)
    failed = [check for check in result["checks"] if check["status"] == "fail"]

    assert [check["code"] for check in failed] == ["INDUSTRY_PROVENANCE_COMPLETE"]
    assert question["question_id"] in failed[0]["details"]["mismatched_object_ids"]


def _later_version_with_lineage() -> tuple[dict, dict, dict[str, dict]]:
    identity, v1 = _pilot()
    slug = identity["project_slug"]
    v1_id = f"research_version:{slug}:0.1.0"
    v2_id = f"research_version:{slug}:0.2.0"
    v3_id = f"research_version:{slug}:0.3.0"
    v2 = deepcopy(v1)
    v2["semantic_version"] = "0.2.0"
    v2["version_id"] = v2_id
    v2["parent_version_id"] = v1_id
    for plan in v2["snapshot"]["search_plans"]:
        plan["version_id"] = v2_id
    v2["content_hash"] = content_sha256(v2, excluded_paths={("content_hash",)})
    v3 = deepcopy(v2)
    v3["semantic_version"] = "0.3.0"
    v3["version_id"] = v3_id
    v3["parent_version_id"] = v2_id
    for plan in v3["snapshot"]["search_plans"]:
        plan["version_id"] = v3_id
    v3["content_hash"] = content_sha256(v3, excluded_paths={("content_hash",)})
    identity["current_version"] = v3_id
    return identity, v3, {"0.1.0": v1, "0.2.0": v2}


def _install_gate_lineage(
    tmp_path: Path,
    identity: dict,
    current: dict,
    ancestors: dict[str, dict],
) -> LayeredResearchLayout:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    shutil.copytree(LayeredResearchLayout.default().schema_dir, layout.schema_dir)
    project = layout.project_dir(identity["project_slug"])
    (project / "versions").mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(identity, ensure_ascii=False),
        encoding="utf-8",
    )
    versions = [*ancestors.values(), current]
    rows = []
    for version in versions:
        semantic_version = version["semantic_version"]
        (project / f"versions/v{semantic_version}.json").write_text(
            json.dumps(version, ensure_ascii=False),
            encoding="utf-8",
        )
        rows.append(
            {
                "version_id": version["version_id"],
                "semantic_version": semantic_version,
                "parent_version_id": version["parent_version_id"],
                "relative_path": f"versions/v{semantic_version}.json",
                "content_hash": version["content_hash"],
                "created_at": version["created_at"],
            }
        )
    (project / "version_manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return layout


def test_provenance_allows_stable_object_from_verified_ancestor(tmp_path: Path) -> None:
    identity, version, ancestors = _later_version_with_lineage()
    layout = _install_gate_lineage(tmp_path, identity, version, ancestors)

    result = evaluate_industry_design_gate(
        identity,
        version,
        layout=layout,
    )

    assert result["status"] == "pass"


@pytest.mark.parametrize(
    ("collection", "id_field"),
    [
        ("questions", "question_id"),
        ("claims", "claim_id"),
        ("claim_relations", "relation_id"),
        ("evidence_requirements", "requirement_id"),
        ("references", "reference_id"),
        ("causal_nodes", "causal_node_id"),
        ("causal_edges", "causal_edge_id"),
        ("validation_metrics", "metric_id"),
        ("invalidation_conditions", "condition_id"),
        ("search_plans", "search_plan_id"),
    ],
)
def test_provenance_rejects_object_missing_from_declared_ancestor_collection(
    tmp_path: Path,
    collection: str,
    id_field: str,
) -> None:
    identity, version, ancestors = _later_version_with_lineage()
    object_id = version["snapshot"][collection][0][id_field]
    replacement_id = f"{object_id}:created-in-v0.3"

    def replace_exact(value):
        if isinstance(value, dict):
            return {key: replace_exact(child) for key, child in value.items()}
        if isinstance(value, list):
            return [replace_exact(child) for child in value]
        return replacement_id if value == object_id else value

    version = replace_exact(version)
    version["content_hash"] = content_sha256(
        version,
        excluded_paths={("content_hash",)},
    )
    layout = _install_gate_lineage(tmp_path, identity, version, ancestors)

    result = evaluate_industry_design_gate(identity, version, layout=layout)

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert provenance_check["status"] == "fail"
    assert replacement_id in provenance_check["details"]["mismatched_object_ids"]


@pytest.mark.parametrize(
    ("collection", "id_field"),
    [
        ("questions", "question_id"),
        ("claims", "claim_id"),
        ("claim_relations", "relation_id"),
        ("evidence_requirements", "requirement_id"),
        ("references", "reference_id"),
        ("causal_nodes", "causal_node_id"),
        ("causal_edges", "causal_edge_id"),
        ("validation_metrics", "metric_id"),
        ("invalidation_conditions", "condition_id"),
        ("search_plans", "search_plan_id"),
    ],
)
def test_provenance_rejects_ancestor_object_with_inconsistent_creation_version(
    tmp_path: Path,
    collection: str,
    id_field: str,
) -> None:
    identity, version, ancestors = _later_version_with_lineage()
    object_id = version["snapshot"][collection][0][id_field]
    ancestor_object = next(
        item
        for item in ancestors["0.1.0"]["snapshot"][collection]
        if item[id_field] == object_id
    )
    ancestor_object["provenance"]["created_in_version"] = version["parent_version_id"]
    ancestors["0.1.0"]["content_hash"] = content_sha256(
        ancestors["0.1.0"],
        excluded_paths={("content_hash",)},
    )
    layout = _install_gate_lineage(tmp_path, identity, version, ancestors)

    result = evaluate_industry_design_gate(identity, version, layout=layout)

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert provenance_check["status"] == "fail"
    assert object_id in provenance_check["details"]["mismatched_object_ids"]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("created_by", "Other Author"),
        ("actor_type", "human"),
        ("agent_run_id", "other-agent-run"),
        ("created_at", "2026-07-18T00:00:00Z"),
    ],
)
def test_provenance_rejects_ancestor_object_with_changed_immutable_creation_field(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    identity, version, ancestors = _later_version_with_lineage()
    object_id = version["snapshot"]["questions"][0]["question_id"]
    ancestor_object = ancestors["0.1.0"]["snapshot"]["questions"][0]
    ancestor_object["provenance"][field] = replacement
    ancestors["0.1.0"]["content_hash"] = content_sha256(
        ancestors["0.1.0"],
        excluded_paths={("content_hash",)},
    )
    layout = _install_gate_lineage(tmp_path, identity, version, ancestors)

    result = evaluate_industry_design_gate(identity, version, layout=layout)

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert provenance_check["status"] == "fail"
    assert object_id in provenance_check["details"]["mismatched_object_ids"]


def test_provenance_allows_ancestor_review_status_to_evolve(tmp_path: Path) -> None:
    identity, version, ancestors = _later_version_with_lineage()
    ancestors["0.1.0"]["snapshot"]["questions"][0]["provenance"]["review_status"] = (
        "reviewed"
    )
    ancestors["0.1.0"]["content_hash"] = content_sha256(
        ancestors["0.1.0"],
        excluded_paths={("content_hash",)},
    )
    layout = _install_gate_lineage(tmp_path, identity, version, ancestors)

    result = evaluate_industry_design_gate(identity, version, layout=layout)

    assert result["status"] == "pass"


@pytest.mark.parametrize("rehash", [False, True])
def test_public_gate_rejects_initial_payload_without_verified_layout(rehash: bool) -> None:
    identity, version = _pilot()
    version["change_summary"] = "unverified in-memory initial payload"
    if rehash:
        version["content_hash"] = content_sha256(
            version,
            excluded_paths={("content_hash",)},
        )

    result = evaluate_industry_design_gate(identity, version)

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert result["status"] == "fail"
    assert provenance_check["status"] == "fail"
    assert provenance_check["details"]["lineage_error"] == (
        "verified lineage storage is required"
    )


def test_provenance_rejects_in_memory_payload_that_retains_stored_hash(
    tmp_path: Path,
) -> None:
    identity, version, ancestors = _later_version_with_lineage()
    layout = _install_gate_lineage(tmp_path, identity, version, ancestors)
    version["snapshot"]["questions"][1]["question_text"] = "forged after storage verification"

    result = evaluate_industry_design_gate(identity, version, layout=layout)

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert provenance_check["status"] == "fail"
    assert provenance_check["details"]["lineage_error"] == (
        "gate version does not match verified storage"
    )


def test_provenance_verifies_initial_payload_when_layout_is_supplied(tmp_path: Path) -> None:
    identity, version = _pilot()
    layout = _install_gate_lineage(tmp_path, identity, version, {})
    version["snapshot"]["questions"][1]["question_text"] = "forged initial payload"

    result = evaluate_industry_design_gate(identity, version, layout=layout)

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert provenance_check["status"] == "fail"
    assert provenance_check["details"]["lineage_error"] == (
        "gate version does not match verified storage"
    )


@pytest.mark.parametrize("field", ["project_id", "title"])
def test_verified_gate_rejects_identity_that_does_not_match_storage(field: str) -> None:
    identity, version = _pilot()
    identity[field] = f"forged-{field}"

    result = evaluate_industry_design_gate(
        identity,
        version,
        layout=LayeredResearchLayout.default(),
    )

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert result["status"] == "fail"
    assert result["verified"] is False
    assert provenance_check["details"]["lineage_error"] == (
        "gate identity does not match verified storage"
    )


def test_provenance_rejects_later_version_masquerading_as_initial_without_layout() -> None:
    identity, version, _ancestors = _later_version_with_lineage()
    version["parent_version_id"] = None
    version["content_hash"] = content_sha256(version, excluded_paths={("content_hash",)})

    result = evaluate_industry_design_gate(identity, version)

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert provenance_check["status"] == "fail"
    assert provenance_check["details"]["lineage_error"] == (
        "verified lineage storage is required"
    )


@pytest.mark.parametrize("created_in", ["future", "cross_project", "missing", "side_branch"])
def test_provenance_rejects_versions_outside_current_ancestor_chain(
    tmp_path: Path,
    created_in: str,
) -> None:
    identity, version, ancestors = _later_version_with_lineage()
    slug = identity["project_slug"]
    if created_in == "future":
        provenance_version = f"research_version:{slug}:0.4.0"
    elif created_in == "cross_project":
        provenance_version = "research_version:other-project:0.1.0"
    elif created_in == "missing":
        provenance_version = f"research_version:{slug}:0.0.5"
    else:
        version["parent_version_id"] = f"research_version:{slug}:0.1.0"
        provenance_version = f"research_version:{slug}:0.2.0"
    version["snapshot"]["questions"][0]["provenance"]["created_in_version"] = provenance_version
    version["content_hash"] = content_sha256(version, excluded_paths={("content_hash",)})
    layout = _install_gate_lineage(tmp_path, identity, version, ancestors)

    result = evaluate_industry_design_gate(
        identity,
        version,
        layout=layout,
    )

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert provenance_check["status"] == "fail"


@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_provenance_rejects_missing_or_unverifiable_stored_ancestor(
    tmp_path: Path,
    damage: str,
) -> None:
    identity, version, ancestors = _later_version_with_lineage()
    layout = _install_gate_lineage(tmp_path, identity, version, ancestors)
    parent_path = layout.project_dir(identity["project_slug"]) / "versions/v0.2.0.json"
    if damage == "missing":
        parent_path.unlink()
    else:
        parent = json.loads(parent_path.read_text())
        parent["change_summary"] = "tampered"
        parent_path.write_text(json.dumps(parent), encoding="utf-8")

    result = evaluate_industry_design_gate(identity, version, layout=layout)

    provenance_check = next(
        check for check in result["checks"] if check["code"] == "INDUSTRY_PROVENANCE_COMPLETE"
    )
    assert provenance_check["status"] == "fail"
    assert provenance_check["details"]["lineage_error"] is not None


@pytest.mark.parametrize(
    "mutation",
    [
        lambda snapshot, claim: claim.update(validation_metric_ids=[]),
        lambda snapshot, claim: claim.update(validation_metric_ids=claim["validation_metric_ids"] * 2),
        lambda snapshot, claim: claim.update(validation_metric_ids=["metric:missing"]),
        lambda snapshot, claim: snapshot["validation_metrics"][0].update(target_id="claim:other"),
        lambda snapshot, claim: snapshot["validation_metrics"][0].update(status="complete"),
        lambda snapshot, claim: (
            claim.update(validation_metric_ids=[]),
            snapshot["validation_metrics"].append(
                {
                    **deepcopy(snapshot["validation_metrics"][0]),
                    "metric_id": "metric:unlinked:stray",
                    "target_id": claim["claim_id"],
                }
            ),
        ),
    ],
)
def test_validation_plan_follows_critical_claim_metric_links(mutation) -> None:
    identity, version = _pilot()
    snapshot = version["snapshot"]
    critical = next(claim for claim in snapshot["claims"] if claim["claim_kind"] == "primary")
    mutation(snapshot, critical)
    assert _failed_checks(identity, version) == {"INDUSTRY_VALIDATION_PLAN_PRESENT"}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda snapshot, claim: claim.update(invalidation_condition_ids=[]),
        lambda snapshot, claim: claim.update(
            invalidation_condition_ids=claim["invalidation_condition_ids"] * 2
        ),
        lambda snapshot, claim: claim.update(invalidation_condition_ids=["condition:missing"]),
        lambda snapshot, claim: snapshot["invalidation_conditions"][0].update(
            target_type="research_question"
        ),
        lambda snapshot, claim: snapshot["invalidation_conditions"][0].update(status="triggered"),
    ],
)
def test_invalidation_plan_follows_critical_claim_condition_links(mutation) -> None:
    identity, version = _pilot()
    snapshot = version["snapshot"]
    critical = next(claim for claim in snapshot["claims"] if claim["claim_kind"] == "primary")
    mutation(snapshot, critical)
    assert _failed_checks(identity, version) == {"INDUSTRY_INVALIDATION_PLAN_PRESENT"}


def test_critical_claim_requires_a_direct_evidence_requirement() -> None:
    identity, version = _pilot()
    snapshot = version["snapshot"]
    critical_id = next(
        claim["claim_id"] for claim in snapshot["claims"] if claim["claim_kind"] == "primary"
    )
    removed_ids = {
        requirement["requirement_id"]
        for requirement in snapshot["evidence_requirements"]
        if requirement["target_type"] == "research_claim" and requirement["target_id"] == critical_id
    }
    snapshot["evidence_requirements"] = [
        requirement for requirement in snapshot["evidence_requirements"]
        if requirement["requirement_id"] not in removed_ids
    ]
    snapshot["search_plans"] = [
        plan for plan in snapshot["search_plans"]
        if not removed_ids.intersection(plan["requirement_ids"])
    ]
    assert _failed_checks(identity, version) == {"INDUSTRY_REQUIRED_QUESTIONS_COVERED"}


def test_critical_claim_requirement_must_be_covered_by_a_search_plan() -> None:
    identity, version = _pilot()
    snapshot = version["snapshot"]
    claim_requirement_ids = {
        requirement["requirement_id"]
        for requirement in snapshot["evidence_requirements"]
        if requirement["target_type"] == "research_claim"
    }
    snapshot["search_plans"] = [
        plan for plan in snapshot["search_plans"]
        if not claim_requirement_ids.intersection(plan["requirement_ids"])
    ]
    assert _failed_checks(identity, version) == {"INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS"}


def test_missing_counter_and_uncovered_requirement_fail_independent_checks() -> None:
    identity, version = _pilot()
    plans = version["snapshot"]["search_plans"]
    plans[0]["queries"] = [
        query for query in plans[0]["queries"] if query["query_role"] != "counter_evidence"
    ]
    plans.pop(1)
    assert _failed_checks(identity, version) == {
        "INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS",
        "INDUSTRY_COUNTER_SEARCH_PRESENT",
    }


def test_source_mismatch_and_uncovered_requirement_fail_independent_checks() -> None:
    identity, version = _pilot()
    plans = version["snapshot"]["search_plans"]
    for query in plans[0]["queries"]:
        query["source_classes"].pop()
    plans.pop(1)
    assert _failed_checks(identity, version) == {
        "INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS",
        "INDUSTRY_SOURCE_CLASS_DIVERSITY",
    }


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "companyCapabilityCollection",
        "company_profiles",
        "stock_screen",
        "background_company_ratings",
    ],
)
def test_downstream_taxonomy_rejects_company_and_stock_output_keys(forbidden_key: str) -> None:
    identity, version = _pilot()
    version["snapshot"][forbidden_key] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


def test_downstream_taxonomy_rejects_nested_camel_case_stock_recommendations() -> None:
    identity, version = _pilot()
    version["snapshot"]["nested"] = [{"stockRecommendations": []}]
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


def test_downstream_taxonomy_rejects_non_background_company_metadata() -> None:
    identity, version = _pilot()
    version["snapshot"]["company_notes"] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "background_key",
    ["background_company_references", "engineering_company_case_reference"],
)
def test_downstream_taxonomy_allows_background_company_reference_keys(background_key: str) -> None:
    identity, version = _pilot()
    version["snapshot"][background_key] = {"role": "background"}
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)


def test_downstream_taxonomy_propagates_background_context_to_non_output_metadata() -> None:
    identity, version = _pilot()
    version["snapshot"]["background_company_references"] = [
        {"company_name": "Example Co", "source_url": "https://example.com"}
    ]
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)


def test_downstream_taxonomy_does_not_hide_outputs_inside_background_context() -> None:
    identity, version = _pilot()
    version["snapshot"]["background_company_references"] = [
        {"company_profile": {"rating": "A"}}
    ]
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize("output_key", ["rating", "profile"])
def test_downstream_taxonomy_applies_background_company_subject_to_direct_outputs(
    output_key: str,
) -> None:
    identity, version = _pilot()
    version["snapshot"]["background_company_references"] = [{output_key: {}}]
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "公司评级",
        "个股推荐",
        "股票推荐",
        "股票评级",
        "发行人排名",
        "证券推荐",
        "issuer_rankings",
        "share_recommendations",
        "ｃｏｍｐａｎｙ＿ｒａｔｉｎｇ",
    ],
)
def test_downstream_taxonomy_rejects_nfkc_alias_and_chinese_outputs(
    forbidden_key: str,
) -> None:
    identity, version = _pilot()
    version["snapshot"][forbidden_key] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "allowed_key",
    [
        "listed_company_count",
        "company_policy",
        "company_employment_total",
        "stock_exchange_code",
        "background_company_notes",
    ],
)
def test_downstream_taxonomy_allows_statistics_policy_and_background_notes(
    allowed_key: str,
) -> None:
    identity, version = _pilot()
    version["snapshot"][allowed_key] = 1
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)


def test_downstream_taxonomy_rejects_stock_notes_only_outside_background() -> None:
    identity, version = _pilot()
    version["snapshot"]["stock_notes"] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)

    identity, version = _pilot()
    version["snapshot"]["background_stock_notes"] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "公司推荐",
        "个股评级",
        "公司排名",
        "个股排名",
        "企业画像",
        "发行人筛选",
        "证券估值",
        "股票观察名单",
    ],
)
def test_downstream_taxonomy_rejects_chinese_subject_action_matrix(
    forbidden_key: str,
) -> None:
    identity, version = _pilot()
    version["snapshot"][forbidden_key] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "allowed_key",
    [
        "上市公司数量",
        "公司政策背景",
        "公司就业总量",
        "股票交易所代码",
        "工程公司案例参考",
    ],
)
def test_downstream_taxonomy_allows_chinese_statistics_and_background_fields(
    allowed_key: str,
) -> None:
    identity, version = _pilot()
    version["snapshot"][allowed_key] = 1
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "nested_output",
    [
        {"公司背景参考": {"评级": []}},
        {"工程公司案例参考": {"画像": {}}},
        {"股票背景资料": {"推荐": []}},
    ],
)
def test_downstream_taxonomy_propagates_chinese_subject_to_nested_action(
    nested_output: dict,
) -> None:
    identity, version = _pilot()
    version["snapshot"]["nested"] = nested_output
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "nested_output",
    [
        {"公司": {"评级": []}},
        {"股票": {"推荐": []}},
        {"company": {"rating": []}},
        {"stock": {"recommendation": []}},
    ],
)
def test_downstream_taxonomy_always_propagates_path_subjects(
    nested_output: dict,
) -> None:
    identity, version = _pilot()
    version["snapshot"]["nested"] = nested_output
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


def test_downstream_taxonomy_background_only_exempts_legal_metadata() -> None:
    identity, version = _pilot()
    version["snapshot"]["nested"] = {
        "公司背景参考": {"notes": [], "公司名称": "Example Co", "source_url": "https://example.com"}
    }
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "company_recommendations",
        "issuer_recommendations",
        "company_valuations",
        "issuer_watchlist",
        "companyRecommendations",
        "issuerWatchlist",
    ],
)
def test_downstream_taxonomy_rejects_english_subject_action_matrix(
    forbidden_key: str,
) -> None:
    identity, version = _pilot()
    version["snapshot"][forbidden_key] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "nested_output",
    [
        {"company": {"recommendations": []}},
        {"issuer": {"valuation": []}},
    ],
)
def test_downstream_taxonomy_rejects_nested_english_subject_actions(
    nested_output: dict,
) -> None:
    identity, version = _pilot()
    version["snapshot"]["nested"] = nested_output
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)
