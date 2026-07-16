from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from stock_research.theme_decomposition import (
    ARTIFACT_VERSION as THEME_ARTIFACT_VERSION,
    NODE_FIELDS,
    NODE_REVIEW_STATUSES as THEME_NODE_REVIEW_STATUSES,
    NODE_TYPES,
    THEME_STATUSES,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("verify_industry_chain_theme_batch", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)
assert_theme_batch_ready = VERIFIER.assert_theme_batch_ready
build_theme_batch_report = VERIFIER.build_theme_batch_report
load_theme_batch_manifest = VERIFIER.load_theme_batch_manifest
main = VERIFIER.main

CANONICAL_MANIFEST = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "next_fifteen_industry_chain_themes_v1.json"
)
WAVE_D_MANIFEST = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "wave_d_five_industry_chain_themes_v1.json"
)

NEXT_FIFTEEN = {
    "ai_logic_compute_chips": "ai_logic_compute_chips_value_chain_v1",
    "optical_communications_data_center_interconnect": "optical_communications_data_center_interconnect_value_chain_v1",
    "semiconductor_materials_electronic_chemicals": "semiconductor_materials_electronic_chemicals_value_chain_v1",
    "power_semiconductors": "power_semiconductors_value_chain_v1",
    "industrial_automation_control": "industrial_automation_control_value_chain_v1",
    "semiconductor_packaging_test_advanced_packaging": "semiconductor_packaging_test_advanced_packaging_value_chain_v1",
    "cloud_data_center_infrastructure": "cloud_data_center_infrastructure_value_chain_v1",
    "new_power_system_smart_grid": "new_power_system_smart_grid_value_chain_v1",
    "core_mechanical_components": "core_mechanical_components_value_chain_v1",
    "industrial_inspection_metrology_machine_vision": "industrial_inspection_metrology_machine_vision_value_chain_v1",
    "industrial_robots": "industrial_robots_value_chain_v1",
    "power_batteries_battery_materials": "power_batteries_battery_materials_value_chain_v1",
    "intelligent_driving_smart_cockpit": "intelligent_driving_smart_cockpit_value_chain_v1",
    "automotive_electronics_chip_applications": "automotive_electronics_chip_applications_value_chain_v1",
    "commercial_space_launch": "commercial_space_launch_value_chain_v1",
}

WAVE_D = {
    "semiconductor_eda_ip_design_services": "semiconductor_eda_ip_design_services_value_chain_v1",
    "memory_chips_storage_control": "memory_chips_storage_control_value_chain_v1",
    "industrial_machine_tools_cnc": "industrial_machine_tools_cnc_value_chain_v1",
    "satellite_manufacturing_space_infrastructure": "satellite_manufacturing_space_infrastructure_value_chain_v1",
    "high_end_medical_devices": "high_end_medical_devices_value_chain_v1",
}

WAVES = {
    "wave_a": [
        "ai_logic_compute_chips",
        "optical_communications_data_center_interconnect",
        "semiconductor_materials_electronic_chemicals",
        "power_semiconductors",
        "industrial_automation_control",
    ],
    "wave_b": [
        "semiconductor_packaging_test_advanced_packaging",
        "cloud_data_center_infrastructure",
        "new_power_system_smart_grid",
        "core_mechanical_components",
        "industrial_inspection_metrology_machine_vision",
    ],
    "wave_c": [
        "industrial_robots",
        "power_batteries_battery_materials",
        "intelligent_driving_smart_cockpit",
        "automotive_electronics_chip_applications",
        "commercial_space_launch",
    ],
}

REQUIRED_SECTIONS = [
    "研究结论",
    "价值链",
    "利润池与竞争壁垒",
    "催化、验证信号与风险",
    "受益公司",
    "来源证据",
    "证据缺口与更新",
]


def test_canonical_manifest_freezes_scope_wave_order_files_and_gates():
    manifest = load_theme_batch_manifest(CANONICAL_MANIFEST)

    assert manifest["batch_id"] == "next_fifteen_industry_chain_themes_v1"
    assert manifest["target_theme_count"] == 15
    assert manifest["primary_source_types"] == [
        "company_filing",
        "official_report",
        "official_article",
    ]
    assert manifest["waves"] == WAVES
    assert {
        chain_id: metadata["theme_id"]
        for chain_id, metadata in manifest["themes"].items()
    } == NEXT_FIFTEEN
    assert {
        chain_id: metadata["artifacts"]
        for chain_id, metadata in manifest["themes"].items()
    } == {
        chain_id: {
            "theme": f"artifacts/theme_decomposition/{theme_id}.json",
            "company_mapping": (
                "artifacts/theme_decomposition/company_mappings/"
                f"{chain_id}_company_mapping_v1.json"
            ),
            "source_pack": (
                "artifacts/theme_decomposition/source_packs/"
                f"{chain_id}_source_pack_v1.json"
            ),
            "node_evidence_matrix": (
                "artifacts/theme_decomposition/source_packs/"
                f"{chain_id}_node_evidence_matrix_v1.json"
            ),
        }
        for chain_id, theme_id in NEXT_FIFTEEN.items()
    }
    gates = manifest["completion_gates"]
    assert gates["min_accepted_sources"] == 10
    assert gates["min_primary_sources"] == 4
    assert gates["min_claims"] == 10
    assert gates["min_reviewed_mappings"] == 8
    assert gates["require_node_evidence_matrix_coverage"] is True
    assert [row["name"] for row in gates["required_readable_sections"]] == REQUIRED_SECTIONS


def test_wave_d_manifest_freezes_scope_files_and_stricter_quality_gates():
    manifest = load_theme_batch_manifest(WAVE_D_MANIFEST)

    assert manifest["batch_id"] == "wave_d_five_industry_chain_themes_v1"
    assert manifest["target_theme_count"] == 5
    assert manifest["waves"] == {"wave_d": list(WAVE_D)}
    assert {
        chain_id: metadata["theme_id"]
        for chain_id, metadata in manifest["themes"].items()
    } == WAVE_D
    assert manifest["primary_source_types"] == [
        "company_filing",
        "official_report",
        "official_article",
    ]
    assert {
        chain_id: metadata["artifacts"]
        for chain_id, metadata in manifest["themes"].items()
    } == {
        chain_id: {
            "theme": f"artifacts/theme_decomposition/{theme_id}.json",
            "company_mapping": (
                "artifacts/theme_decomposition/company_mappings/"
                f"{chain_id}_company_mapping_v1.json"
            ),
            "source_pack": (
                "artifacts/theme_decomposition/source_packs/"
                f"{chain_id}_source_pack_v1.json"
            ),
            "node_evidence_matrix": (
                "artifacts/theme_decomposition/source_packs/"
                f"{chain_id}_node_evidence_matrix_v1.json"
            ),
        }
        for chain_id, theme_id in WAVE_D.items()
    }
    gates = manifest["completion_gates"]
    assert gates["min_accepted_sources"] == 10
    assert gates["min_primary_sources"] == 8
    assert gates["min_claims"] == 12
    assert gates["min_reviewed_mappings"] == 8
    assert gates["require_node_evidence_matrix_coverage"] is True
    assert gates["require_bidirectional_evidence_contract"] is True
    assert gates["require_precise_mapping_locators"] is True
    assert [row["name"] for row in gates["required_readable_sections"]] == REQUIRED_SECTIONS


def test_ready_fixture_builds_theme_and_wave_summary(tmp_path: Path):
    manifest_path = _write_ready_batch(tmp_path)

    report = build_theme_batch_report(manifest_path)

    assert report["completion_status"] == "ready"
    assert report["ready_theme_count"] == 1
    assert report["wave_results"]["wave_a"]["ready"] is True
    theme = report["theme_results"][0]
    assert theme["counts"] == {
        "accepted_sources": 10,
        "primary_sources": 4,
        "claims": 10,
        "accepted_source_backed_claims": 10,
        "reviewed_mappings": 8,
    }
    assert theme["required_sections_ready"] is True
    assert theme["checks"]["bidirectional_evidence_contract"] is True
    assert theme["checks"]["precise_mapping_locators"] is True
    assert all(theme["readable_sections"].values())
    assert all(theme["checks"].values())
    assert_theme_batch_ready(report)


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        ("accepted_sources", "accepted_source_count"),
        ("primary_sources", "primary_source_count"),
        ("claims", "claim_count"),
        ("reviewed_mappings", "reviewed_mapping_count"),
    ],
)
def test_theme_fails_each_numeric_completion_gate(
    tmp_path: Path,
    mutation: str,
    failed_check: str,
):
    manifest_path = _write_ready_batch(tmp_path)
    _break_gate(tmp_path, mutation)

    report = build_theme_batch_report(manifest_path)

    theme = report["theme_results"][0]
    assert theme["ready"] is False
    assert theme["checks"][failed_check] is False
    assert report["wave_results"]["wave_a"]["ready"] is False
    assert report["completion_status"] == "not_ready"
    with pytest.raises(AssertionError, match="sample_chain"):
        assert_theme_batch_ready(report)


def test_wave_selection_only_evaluates_requested_wave(tmp_path: Path):
    manifest_path = _write_ready_batch(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target_theme_count"] = 2
    manifest["waves"]["wave_b"] = ["missing_chain"]
    manifest["themes"]["missing_chain"] = {
        "theme_id": "missing_theme_v1",
        "artifacts": {
            "theme": "missing/theme.json",
            "company_mapping": "missing/mapping.json",
            "source_pack": "missing/source.json",
            "node_evidence_matrix": "missing/matrix.json",
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = build_theme_batch_report(manifest_path, wave="wave_a")

    assert report["selected_waves"] == ["wave_a"]
    assert report["evaluated_theme_count"] == 1
    assert report["completion_status"] == "ready"


def test_missing_artifact_is_a_clear_not_ready_result(tmp_path: Path):
    manifest_path = _write_ready_batch(tmp_path)
    (tmp_path / "sample_source_pack.json").unlink()

    report = build_theme_batch_report(manifest_path)

    theme = report["theme_results"][0]
    assert theme["ready"] is False
    assert theme["checks"]["source_pack_readable"] is False
    assert "sample_source_pack.json does not exist" in theme["errors"][0]


def test_manifest_loader_rejects_malformed_json(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON in theme batch manifest"):
        load_theme_batch_manifest(path)


def test_manifest_loader_rejects_wave_scope_mismatch(tmp_path: Path):
    manifest_path = _write_ready_batch(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target_theme_count"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="target_theme_count=2"):
        load_theme_batch_manifest(manifest_path)


def test_duplicate_source_ids_cannot_satisfy_source_gate(tmp_path: Path):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_source_pack.json"
    payload = _read_json(path)
    payload["sources"][-1]["source_id"] = payload["sources"][0]["source_id"]
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["counts"]["accepted_sources"] == 0
    assert theme["checks"]["source_rows_valid"] is False
    assert any("DUPLICATE_ID" in error for error in theme["errors"])


def test_invalid_source_review_status_is_an_explicit_integrity_failure(tmp_path: Path):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_source_pack.json"
    payload = _read_json(path)
    payload["sources"][-1]["review_status"] = "bogus"
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["source_rows_valid"] is False
    assert any("review_status invalid" in error for error in theme["errors"])


@pytest.mark.parametrize(
    ("artifact_name", "mutation", "failed_check", "error_fragment"),
    [
        ("source_pack", "artifact_version", "source_rows_valid", "artifact_version"),
        (
            "node_evidence_matrix",
            "artifact_version",
            "node_evidence_matrix_coverage",
            "artifact_version",
        ),
        (
            "node_evidence_matrix",
            "value_capture_score_review_status",
            "node_evidence_matrix_coverage",
            "value_capture_score_review_status",
        ),
        (
            "node_evidence_matrix",
            "bottleneck_score_review_status",
            "node_evidence_matrix_coverage",
            "bottleneck_score_review_status",
        ),
        (
            "node_evidence_matrix",
            "node_review_status",
            "node_evidence_matrix_coverage",
            "node_review_status",
        ),
        (
            "node_evidence_matrix",
            "value_bases",
            "node_evidence_matrix_coverage",
            "value_bases",
        ),
        (
            "node_evidence_matrix",
            "evidence_strength_after",
            "node_evidence_matrix_coverage",
            "evidence_strength_after",
        ),
        (
            "node_evidence_matrix",
            "missing_required_field",
            "node_evidence_matrix_coverage",
            "next_evidence_needed",
        ),
    ],
)
def test_source_pack_and_matrix_schema_mutations_fail_closed(
    tmp_path: Path,
    artifact_name: str,
    mutation: str,
    failed_check: str,
    error_fragment: str,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = {
        "source_pack": tmp_path / "sample_source_pack.json",
        "node_evidence_matrix": tmp_path / "sample_node_evidence_matrix.json",
    }[artifact_name]
    payload = _read_json(path)
    if mutation == "artifact_version":
        payload["artifact_version"] = "bogus_v0"
    elif mutation == "value_bases":
        payload["node_evidence_matrix"][0][mutation] = ["typo"]
    elif mutation == "evidence_strength_after":
        payload["node_evidence_matrix"][0][mutation] = 99
    elif mutation == "missing_required_field":
        payload["node_evidence_matrix"][0].pop("next_evidence_needed")
    else:
        payload["node_evidence_matrix"][0][mutation] = "typo"
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"][failed_check] is False
    assert any(error_fragment in error for error in theme["errors"])


@pytest.mark.parametrize(
    ("mutation", "error_fragment"),
    [
        ("artifact_version", "artifact_version"),
        ("theme_status", "theme.status"),
        ("missing_node_field", "nodes[0].description"),
        ("invalid_node_field_type", "nodes[0].node_name"),
        ("node_type", "nodes[0].node_type"),
        ("node_review_status", "nodes[0].node_review_status"),
        ("evidence_strength", "nodes[0].evidence_strength"),
        ("score", "nodes[0].bottleneck_score"),
    ],
)
def test_theme_artifact_schema_mutations_fail_closed(
    tmp_path: Path,
    mutation: str,
    error_fragment: str,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_theme.json"
    payload = _read_json(path)
    node = payload["nodes"][0]
    if mutation == "artifact_version":
        payload["artifact_version"] = "bogus_v0"
    elif mutation == "theme_status":
        payload["theme"]["status"] = next(
            value for value in ("bogus", "invalid") if value not in THEME_STATUSES
        )
    elif mutation == "missing_node_field":
        node.pop(next(field for field in ("description", "node_name") if field in NODE_FIELDS))
    elif mutation == "invalid_node_field_type":
        node["node_name"] = 123
    elif mutation == "node_type":
        node[mutation] = next(
            value for value in ("bogus", "invalid") if value not in NODE_TYPES
        )
    elif mutation == "node_review_status":
        node[mutation] = next(
            value
            for value in ("bogus", "invalid")
            if value not in THEME_NODE_REVIEW_STATUSES
        )
    else:
        node["bottleneck_score" if mutation == "score" else mutation] = 99
    _write_json(path, payload)

    report = build_theme_batch_report(manifest_path)
    theme = report["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["theme_nodes_valid"] is False
    assert report["wave_results"]["wave_a"]["ready"] is False
    assert report["completion_status"] == "not_ready"
    assert any(error_fragment in error for error in theme["errors"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reliability_level", "S4"),
        ("document_status", "metadata_only"),
        ("url", "http://example.com/source"),
    ],
)
def test_canonical_source_validator_blocks_adversarial_accepted_sources(
    tmp_path: Path,
    field: str,
    value: str,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_source_pack.json"
    payload = _read_json(path)
    payload["sources"][-1][field] = value
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["source_rows_valid"] is False
    assert theme["counts"]["accepted_sources"] == 0


@pytest.mark.parametrize(
    "mutation",
    ["missing_mapping_source_field", "missing_excerpt_locator", "cross_theme_node"],
)
def test_canonical_mapping_validator_blocks_provenance_and_ownership_errors(
    tmp_path: Path,
    mutation: str,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_company_mapping.json"
    payload = _read_json(path)
    if mutation == "missing_mapping_source_field":
        payload["sources"][-1].pop("author")
    elif mutation == "missing_excerpt_locator":
        payload["evidence_items"][-1].pop("excerpt_locator")
    else:
        payload["evidence_items"][-1]["related_node_ids"] = ["other_node"]
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["mapping_rows_valid"] is False
    assert theme["counts"]["reviewed_mappings"] == 0


def test_bidirectional_evidence_contract_rejects_broad_claim_node_attachment(
    tmp_path: Path,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_theme.json"
    payload = _read_json(path)
    payload["claims"][0]["affected_theme_nodes"] = ["node_1", "node_2"]
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["bidirectional_evidence_contract"] is False
    assert any("source-claim-node contract" in error for error in theme["errors"])


def test_bidirectional_evidence_contract_rejects_pending_source_on_wrong_matrix_node(
    tmp_path: Path,
):
    manifest_path = _write_ready_batch(tmp_path)
    source_path = tmp_path / "sample_source_pack.json"
    source_pack = _read_json(source_path)
    source_pack["sources"].append(
        {
            "source_id": "pending_source",
            "review_status": "needs_full_text",
            "source_type": "broker_report",
            "title": "Pending source",
            "publisher": "Pending publisher",
            "author": "Pending author",
            "publish_date": "2026-07-14",
            "url": "https://example.com/pending",
            "access_level": "public",
            "reliability_level": "S2",
            "document_status": "metadata_only",
            "evidence_locator": "第1页，待复核",
            "evidence_summary": "Pending evidence",
            "supported_claim_ids": ["claim_0"],
            "supported_node_ids": ["node_1"],
            "limitations": "Not accepted",
            "notes": "Pending fixture source",
        }
    )
    _write_json(source_path, source_pack)
    theme_path = tmp_path / "sample_theme.json"
    theme_payload = _read_json(theme_path)
    theme_payload["claims"][0]["supporting_source_ids"] = ["pending_source"]
    _write_json(theme_path, theme_payload)
    matrix_path = tmp_path / "sample_node_evidence_matrix.json"
    matrix_payload = _read_json(matrix_path)
    next(
        row for row in matrix_payload["node_evidence_matrix"] if row["node_id"] == "node_2"
    )["pending_source_ids"] = ["pending_source"]
    _write_json(matrix_path, matrix_payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["bidirectional_evidence_contract"] is False
    assert any("matrix pending source mismatch" in error for error in theme["errors"])


def test_precise_mapping_locator_contract_rejects_reused_composite_locator(
    tmp_path: Path,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_company_mapping.json"
    payload = _read_json(path)
    for evidence_id in payload["company_mappings"][0]["evidence_ids"]:
        evidence = next(
            row for row in payload["evidence_items"] if row["evidence_id"] == evidence_id
        )
        evidence["excerpt_locator"] = "第10页，产品、收入与风险章节"
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["precise_mapping_locators"] is False
    assert any("mapping evidence locator contract" in error for error in theme["errors"])


def test_precise_mapping_locator_contract_rejects_page_markers_without_digits(
    tmp_path: Path,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_company_mapping.json"
    payload = _read_json(path)
    invalid_locators = ["第、页，产品", "第-页，收入", "第—页，阶段"]
    for evidence_id, locator in zip(
        payload["company_mappings"][0]["evidence_ids"], invalid_locators
    ):
        next(
            row for row in payload["evidence_items"] if row["evidence_id"] == evidence_id
        )["excerpt_locator"] = locator
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["precise_mapping_locators"] is False
    assert any("lacks page number" in error for error in theme["errors"])


def test_precise_mapping_locator_contract_allows_page_numbered_section_wording(
    tmp_path: Path,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_company_mapping.json"
    payload = _read_json(path)
    stage_id = payload["company_mappings"][0]["evidence_ids"][2]
    next(
        row for row in payload["evidence_items"] if row["evidence_id"] == stage_id
    )["excerpt_locator"] = "第30页，风险章节"
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is True
    assert theme["checks"]["precise_mapping_locators"] is True


@pytest.mark.parametrize(
    "mutation", ["duplicate_id", "cross_theme", "missing_source", "invalid_type"]
)
def test_duplicate_cross_theme_or_unbacked_claims_do_not_count(
    tmp_path: Path,
    mutation: str,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_theme.json"
    payload = _read_json(path)
    if mutation == "duplicate_id":
        payload["claims"][-1]["claim_id"] = payload["claims"][0]["claim_id"]
    elif mutation == "cross_theme":
        payload["claims"][-1]["theme_id"] = "other_theme_v1"
    elif mutation == "missing_source":
        payload["claims"][-1]["source_id"] = "missing_source"
    else:
        payload["claims"][-1]["claim_type"] = "bogus"
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["counts"]["claims"] < 10
    assert theme["checks"]["claim_rows_valid"] is False
    assert any("claim" in error for error in theme["errors"])


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_field",
        "invalid_platform_status",
        "invalid_evidence_status",
        "invalid_confidence",
        "unknown_supporting_source",
        "invalid_affected_node",
    ],
)
def test_claims_must_satisfy_canonical_contract(tmp_path: Path, mutation: str):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_theme.json"
    payload = _read_json(path)
    claim = payload["claims"][-1]
    if mutation == "missing_field":
        claim.pop("confidence")
    elif mutation == "invalid_platform_status":
        claim["platform_use_status"] = "bogus"
    elif mutation == "invalid_evidence_status":
        claim["evidence_status"] = "bogus"
    elif mutation == "invalid_confidence":
        claim["confidence"] = 1.5
    elif mutation == "unknown_supporting_source":
        claim["supporting_source_ids"] = ["unknown_source"]
    else:
        claim["affected_theme_nodes"] = ["other_node"]
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["counts"]["claims"] < 10
    assert theme["checks"]["claim_rows_valid"] is False
    assert any("claim" in error for error in theme["errors"])


def test_known_nonaccepted_source_draft_claim_counts_toward_claim_gate(
    tmp_path: Path,
):
    manifest_path = _write_ready_batch(tmp_path)
    source_path = tmp_path / "sample_source_pack.json"
    source_pack = _read_json(source_path)
    source_pack["sources"].append(
        {
            "source_id": "pending_source",
            "review_status": "needs_full_text",
            "source_type": "broker_report",
            "title": "Pending source",
            "publisher": "Pending publisher",
            "author": "Pending author",
            "publish_date": "2026-07-14",
            "url": "https://example.com/pending",
            "access_level": "public",
            "reliability_level": "S2",
            "document_status": "metadata_only",
            "evidence_locator": "page pending",
            "evidence_summary": "Pending evidence",
            "supported_claim_ids": ["claim_9"],
            "supported_node_ids": ["node_2"],
            "limitations": "Not accepted",
            "notes": "Pending fixture source",
        }
    )
    source_pack["sources"][9]["supported_claim_ids"] = []
    source_pack["sources"][9]["supported_node_ids"] = []
    _write_json(source_path, source_pack)
    theme_path = tmp_path / "sample_theme.json"
    theme_payload = _read_json(theme_path)
    theme_payload["claims"][-1]["source_id"] = "pending_source"
    theme_payload["claims"][-1]["platform_use_status"] = "draft"
    _write_json(theme_path, theme_payload)
    matrix_path = tmp_path / "sample_node_evidence_matrix.json"
    matrix_payload = _read_json(matrix_path)
    node_2 = next(
        row for row in matrix_payload["node_evidence_matrix"] if row["node_id"] == "node_2"
    )
    node_2["accepted_source_ids"].remove("source_9")
    node_2["pending_source_ids"] = ["pending_source"]
    node_2["supported_claim_ids"].remove("claim_9")
    _write_json(matrix_path, matrix_payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is True
    assert theme["counts"]["claims"] == 10
    assert theme["counts"]["accepted_source_backed_claims"] == 9
    assert theme["checks"]["claim_rows_valid"] is True
    assert theme["checks"]["node_evidence_matrix_coverage"] is True


def test_reviewed_claim_on_known_nonaccepted_source_fails_integrity_but_still_counts(
    tmp_path: Path,
):
    manifest_path = _write_ready_batch(tmp_path)
    source_path = tmp_path / "sample_source_pack.json"
    source_pack = _read_json(source_path)
    source_pack["sources"][-1]["review_status"] = "needs_full_text"
    _write_json(source_path, source_pack)
    theme_path = tmp_path / "sample_theme.json"
    theme_payload = _read_json(theme_path)
    theme_payload["claims"][-1]["platform_use_status"] = "reviewed"
    _write_json(theme_path, theme_payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["counts"]["claims"] == 10
    assert theme["counts"]["accepted_source_backed_claims"] == 9
    assert theme["checks"]["claim_rows_valid"] is False
    assert any("reviewed claim requires accepted source" in error for error in theme["errors"])


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_id",
        "duplicate_relationship",
        "cross_theme",
        "evidence_free",
        "irrelevant_scope",
        "indirect_evidence",
        "raw_mapping_source",
        "raw_evidence",
        "invalid_review_status",
    ],
)
def test_invalid_reviewed_mappings_do_not_count(tmp_path: Path, mutation: str):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_company_mapping.json"
    payload = _read_json(path)
    mapping = payload["company_mappings"][-1]
    if mutation == "duplicate_id":
        mapping["mapping_id"] = payload["company_mappings"][0]["mapping_id"]
    elif mutation == "duplicate_relationship":
        mapping["company_code"] = payload["company_mappings"][0]["company_code"]
        mapping["mapped_node_id"] = payload["company_mappings"][0]["mapped_node_id"]
    elif mutation == "cross_theme":
        mapping["theme_id"] = "other_theme_v1"
    elif mutation == "evidence_free":
        mapping["evidence_ids"] = []
    elif mutation == "irrelevant_scope":
        payload["evidence_items"][-1]["related_company_codes"] = ["999999.SZ"]
    elif mutation == "indirect_evidence":
        relationship_id = mapping["evidence_ids"][0]
        next(
            row
            for row in payload["evidence_items"]
            if row["evidence_id"] == relationship_id
        )["evidence_type"] = "company_mention"
    elif mutation == "raw_mapping_source":
        payload["sources"][-1]["title"] = ""
    elif mutation == "raw_evidence":
        payload["evidence_items"][-1]["evidence_summary"] = ""
    else:
        mapping["review_status"] = "bogus"
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["counts"]["reviewed_mappings"] < 8
    assert theme["checks"]["mapping_rows_valid"] is False
    assert any("mapping" in error or "evidence" in error for error in theme["errors"])


@pytest.mark.parametrize(
    "mutation",
    [
        "concept_exposure",
        "reserve_only",
        "missing_field",
        "incompatible_materiality",
        "invalid_enum",
        "invalid_confidence",
        "invalid_company_code",
        "missing_revenue_evidence",
    ],
)
def test_reviewed_mappings_must_satisfy_canonical_beneficiary_contract(
    tmp_path: Path,
    mutation: str,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_company_mapping.json"
    payload = _read_json(path)
    mapping = payload["company_mappings"][-1]
    if mutation == "concept_exposure":
        mapping["business_stage"] = "concept_exposure"
        mapping["business_materiality"] = "concept_only"
        mapping["revenue_relevance"] = "none"
    elif mutation == "reserve_only":
        mapping["business_stage"] = "reserve_stage"
        mapping["business_materiality"] = "reserve_only"
        mapping["revenue_relevance"] = "none"
    elif mutation == "missing_field":
        mapping.pop("company_name")
    elif mutation == "incompatible_materiality":
        mapping["business_materiality"] = "concept_only"
    elif mutation == "invalid_enum":
        mapping["mapping_type"] = "bogus"
    elif mutation == "invalid_confidence":
        mapping["confidence"] = 0.4
    elif mutation == "invalid_company_code":
        mapping["company_code"] = "invalid"
    else:
        mapping["evidence_ids"] = [mapping["evidence_ids"][0]]
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["counts"]["reviewed_mappings"] < 8
    if mutation == "reserve_only":
        assert theme["checks"]["mapping_rows_valid"] is True
    else:
        assert theme["checks"]["mapping_rows_valid"] is False
    if mutation != "reserve_only":
        assert any(
            "mapping" in error or "materiality" in error
            for error in theme["errors"]
        )


@pytest.mark.parametrize(
    "mutation",
    ["missing_node", "extra_node", "duplicate_node", "unknown_source"],
)
def test_irrelevant_or_incomplete_node_matrix_never_satisfies_coverage(
    tmp_path: Path,
    mutation: str,
):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_node_evidence_matrix.json"
    payload = _read_json(path)
    if mutation == "missing_node":
        payload["node_evidence_matrix"].pop()
    elif mutation == "extra_node":
        payload["node_evidence_matrix"].append(
            {
                "node_id": "other_node",
                "accepted_source_ids": ["source_0"],
                "supported_claim_ids": ["claim_0"],
                "evidence_gap_status": "covered",
            }
        )
    elif mutation == "duplicate_node":
        payload["node_evidence_matrix"].append(
            dict(payload["node_evidence_matrix"][0])
        )
    else:
        payload["node_evidence_matrix"][0]["accepted_source_ids"] = ["unknown_source"]
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["node_evidence_matrix_coverage"] is False
    assert any("node evidence matrix" in error for error in theme["errors"])


def test_node_matrix_coverage_is_diagnostic_when_manifest_gate_is_disabled(
    tmp_path: Path,
):
    manifest_path = _write_ready_batch(tmp_path)
    manifest = _read_json(manifest_path)
    manifest["completion_gates"]["require_node_evidence_matrix_coverage"] = False
    _write_json(manifest_path, manifest)
    matrix_path = tmp_path / "sample_node_evidence_matrix.json"
    matrix = _read_json(matrix_path)
    matrix["node_evidence_matrix"].pop()
    _write_json(matrix_path, matrix)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is True
    assert theme["node_evidence_matrix_coverage"] is False
    assert "node_evidence_matrix_coverage" not in theme["checks"]
    assert any("coverage mismatch" in error for error in theme["errors"])


def test_manifest_rejects_duplicate_theme_ids(tmp_path: Path):
    manifest_path = _write_two_theme_manifest(tmp_path)
    manifest = _read_json(manifest_path)
    manifest["themes"]["second_chain"]["theme_id"] = "sample_theme_v1"
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match="duplicate theme_id"):
        load_theme_batch_manifest(manifest_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "industry_chain_theme_batch_v2", "schema_version"),
        ("artifact_base", 7, "artifact_base"),
        ("artifact_base", "", "artifact_base"),
        ("theme_id", 7, "theme_id"),
        ("theme_id", "", "theme_id"),
        ("theme_path", 7, "artifacts.theme"),
        ("theme_path", "", "artifacts.theme"),
        ("theme_path", "/tmp/theme.json", "artifacts.theme"),
        ("theme_path", "../theme.json", "artifacts.theme"),
        ("require_matrix_coverage", "yes", "require_node_evidence_matrix_coverage"),
    ],
)
def test_manifest_rejects_invalid_schema_base_theme_and_artifact_paths(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
):
    manifest_path = _write_ready_batch(tmp_path)
    manifest = _read_json(manifest_path)
    if field == "theme_id":
        manifest["themes"]["sample_chain"]["theme_id"] = value
    elif field == "theme_path":
        manifest["themes"]["sample_chain"]["artifacts"]["theme"] = value
    elif field == "require_matrix_coverage":
        manifest["completion_gates"]["require_node_evidence_matrix_coverage"] = value
    else:
        manifest[field] = value
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match=message):
        load_theme_batch_manifest(manifest_path)


def test_manifest_rejects_reused_resolved_artifact_paths(tmp_path: Path):
    manifest_path = _write_two_theme_manifest(tmp_path)
    manifest = _read_json(manifest_path)
    manifest["themes"]["second_chain"]["artifacts"]["source_pack"] = (
        manifest["themes"]["sample_chain"]["artifacts"]["source_pack"]
    )
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match="reuses resolved artifact path"):
        load_theme_batch_manifest(manifest_path)


@pytest.mark.parametrize("kind", ["missing", "malformed"])
def test_cli_reports_manifest_input_errors_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    kind: str,
):
    path = tmp_path / "manifest.json"
    if kind == "malformed":
        path.write_text("{broken", encoding="utf-8")

    exit_code = main(["--manifest", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "error:" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_cli_reports_unknown_wave_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    manifest_path = _write_ready_batch(tmp_path)

    exit_code = main(["--manifest", str(manifest_path), "--wave", "wave_z"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Unknown wave 'wave_z'" in captured.err
    assert "Traceback" not in captured.err


def test_cli_markdown_includes_failed_checks_and_artifact_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    manifest_path = _write_ready_batch(tmp_path)
    (tmp_path / "sample_source_pack.json").write_text("{broken", encoding="utf-8")

    exit_code = main(
        ["--manifest", str(manifest_path), "--wave", "wave_a", "--format", "markdown"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Failed checks:" in captured.out
    assert "Artifact errors:" in captured.out
    assert "not readable JSON" in captured.out
    assert captured.err == ""


def test_cli_emits_ready_json_and_returns_zero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    manifest_path = _write_ready_batch(tmp_path)

    exit_code = main(["--manifest", str(manifest_path), "--format", "json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["completion_status"] == "ready"
    assert captured.err == ""


def _write_ready_batch(root: Path) -> Path:
    manifest = {
        "schema_version": "industry_chain_theme_batch_v1",
        "batch_id": "sample_batch_v1",
        "target_theme_count": 1,
        "artifact_base": ".",
        "primary_source_types": ["company_filing", "official_report", "official_article"],
        "completion_gates": {
            "min_accepted_sources": 10,
            "min_primary_sources": 4,
            "min_claims": 10,
            "min_reviewed_mappings": 8,
            "require_node_evidence_matrix_coverage": True,
            "require_bidirectional_evidence_contract": True,
            "require_precise_mapping_locators": True,
            "required_readable_sections": [
                {
                    "name": "研究结论",
                    "non_empty": [
                        "theme:research_profile.investment_summary",
                        "theme:research_profile.industry_stage",
                        "theme:research_profile.central_conflict",
                    ],
                },
                {"name": "价值链", "non_empty": ["theme:research_profile.value_flow_summary", "theme:nodes"]},
                {"name": "利润池与竞争壁垒", "non_empty": ["theme:research_profile.profit_pool_summary"]},
                {
                    "name": "催化、验证信号与风险",
                    "non_empty": [
                        "theme:research_profile.catalyst_claim_ids",
                        "theme:research_profile.risk_claim_ids",
                        "theme:research_profile.validation_signals",
                    ],
                },
                {"name": "受益公司", "non_empty": ["company_mapping:company_mappings"]},
                {"name": "来源证据", "non_empty": ["source_pack:sources"]},
                {
                    "name": "证据缺口与更新",
                    "non_empty": [
                        "theme:research_profile.evidence_gap_summary",
                        "node_evidence_matrix:node_evidence_matrix",
                    ],
                },
            ],
        },
        "waves": {"wave_a": ["sample_chain"]},
        "themes": {
            "sample_chain": {
                "theme_id": "sample_theme_v1",
                "artifacts": {
                    "theme": "sample_theme.json",
                    "company_mapping": "sample_company_mapping.json",
                    "source_pack": "sample_source_pack.json",
                    "node_evidence_matrix": "sample_node_evidence_matrix.json",
                },
            }
        },
    }
    theme = {
        "artifact_version": THEME_ARTIFACT_VERSION,
        "theme": {
            "theme_id": "sample_theme_v1",
            "theme_name": "Sample Theme",
            "theme_type": "other",
            "summary": "Sample theme for verifier contract tests.",
            "status": "reviewed",
            "created_from": "manual",
            "last_updated": "2026-07-15",
        },
        "research_profile": {
            "investment_summary": "Conclusion",
            "industry_stage": "scaling",
            "central_conflict": "Conflict",
            "value_flow_summary": "Inputs to outputs",
            "profit_pool_summary": "Profit pools",
            "catalyst_claim_ids": ["claim_8"],
            "risk_claim_ids": ["claim_9"],
            "validation_signals": ["signal"],
            "evidence_gap_summary": "Known gaps",
        },
        "nodes": [
            {
                "node_id": f"node_{index}",
                "theme_id": "sample_theme_v1",
                "parent_node_id": "",
                "node_name": f"Node {index}",
                "node_type": "subsystem",
                "description": f"Sample node {index}.",
                "value_capture_score": 4,
                "bottleneck_score": 4,
                "localization_gap_score": 3,
                "supply_tightness_score": 3,
                "evidence_strength": 4,
                "node_review_status": "reviewed",
                "key_metrics": ["metric"],
                "overseas_leaders": [],
                "domestic_players": [],
                "related_stock_codes": [],
            }
            for index in range(1, 3)
        ],
        "claims": [
            {
                "claim_id": f"claim_{index}",
                "theme_id": "sample_theme_v1",
                "source_id": f"source_{index}",
                "claim_text": f"Claim {index}",
                "claim_type": "catalyst" if index == 8 else "risk" if index == 9 else "value_capture",
                "confidence": 0.8,
                "evidence_status": "verified",
                "platform_use_status": "reviewed",
                "supporting_source_ids": [],
                "affected_theme_nodes": [f"node_{index % 2 + 1}"],
            }
            for index in range(10)
        ],
    }
    source_pack = {
        "artifact_version": "sample_source_pack",
        "theme_id": "sample_theme_v1",
        "sources": [
            {
                "source_id": f"source_{index}",
                "review_status": "accepted",
                "source_type": "company_filing" if index < 4 else "broker_report",
                "title": f"Source {index}",
                "publisher": f"Publisher {index}",
                "author": f"Author {index}",
                "publish_date": "2026-07-14",
                "url": f"https://example.com/source-{index}",
                "access_level": "public",
                "reliability_level": "S0" if index < 4 else "S2",
                "document_status": "full_text_reviewed",
                "evidence_locator": f"page {index + 1}",
                "evidence_summary": f"Evidence summary {index}",
                "supported_claim_ids": [f"claim_{index}"],
                "supported_node_ids": [f"node_{index % 2 + 1}"],
                "limitations": "Fixture limitation",
                "notes": "Fixture source",
            }
            for index in range(10)
        ],
    }
    company_mapping = {
        "artifact_version": "theme_company_mapping_v1",
        "theme_id": "sample_theme_v1",
        "sources": [
            {
                "source_id": f"source_{index}",
                "source_type": "company_filing",
                "title": f"Company filing {index}",
                "publisher": f"Company {index}",
                "author": f"Author {index}",
                "publish_date": "2026-07-14",
                "url_or_ref": f"https://example.com/company-{index}",
                "access_level": "public",
                "reliability_level": "S0",
                "review_status": "accepted",
                "notes": "Fixture mapping source",
            }
            for index in range(8)
        ],
        "evidence_items": [
            evidence
            for index in range(8)
            for evidence in (
                {
                    "evidence_id": f"relationship_evidence_{index}",
                    "source_id": f"source_{index}",
                    "evidence_type": "product_relationship",
                    "excerpt_locator": f"第{index + 1}页，产品关系",
                    "evidence_summary": f"Scoped relationship {index}",
                    "related_company_codes": [f"00000{index}.SZ"],
                    "related_node_ids": [f"node_{index % 2 + 1}"],
                },
                {
                    "evidence_id": f"revenue_evidence_{index}",
                    "source_id": f"source_{index}",
                    "evidence_type": "revenue_materiality",
                    "excerpt_locator": f"第{index + 101}页，收入构成",
                    "evidence_summary": f"Revenue materiality {index}",
                    "related_company_codes": [f"00000{index}.SZ"],
                    "related_node_ids": [f"node_{index % 2 + 1}"],
                },
                {
                    "evidence_id": f"stage_evidence_{index}",
                    "source_id": f"source_{index}",
                    "evidence_type": "business_stage",
                    "excerpt_locator": f"第{index + 201}页，商业阶段与风险",
                    "evidence_summary": f"Business stage {index}",
                    "related_company_codes": [f"00000{index}.SZ"],
                    "related_node_ids": [f"node_{index % 2 + 1}"],
                },
            )
        ],
        "company_mappings": [
            {
                "mapping_id": f"mapping_{index}",
                "theme_id": "sample_theme_v1",
                "company_code": f"00000{index}.SZ",
                "company_name": f"Company {index}",
                "market": "CN",
                "mapped_node_id": f"node_{index % 2 + 1}",
                "mapping_type": "direct_product",
                "business_stage": "primary_business",
                "confidence": 0.9,
                "evidence_ids": [
                    f"relationship_evidence_{index}",
                    f"revenue_evidence_{index}",
                    f"stage_evidence_{index}",
                ],
                "revenue_relevance": "meaningful",
                "bottleneck_relevance": "core",
                "business_materiality": "meaningful_segment",
                "product_or_service": f"Product {index}",
                "relationship_summary": f"Relationship {index}",
                "review_status": "reviewed",
                "notes": "",
            }
            for index in range(8)
        ],
    }
    matrix = {
        "artifact_version": "sample_node_evidence_matrix",
        "theme_id": "sample_theme_v1",
        "node_evidence_matrix": [
            {
                "node_id": "node_1",
                "accepted_source_ids": [f"source_{index}" for index in range(0, 10, 2)],
                "pending_source_ids": [],
                "supported_claim_ids": [f"claim_{index}" for index in range(0, 10, 2)],
                "evidence_strength_before": 2,
                "evidence_strength_after": 4,
                "value_capture_score_review_status": "supported",
                "bottleneck_score_review_status": "supported",
                "value_bases": ["technology_barrier"],
                "evidence_gap_status": "covered",
                "node_review_status": "reviewed",
                "rationale": "Fixture rationale",
                "next_evidence_needed": "Fixture next evidence",
            },
            {
                "node_id": "node_2",
                "accepted_source_ids": [f"source_{index}" for index in range(1, 10, 2)],
                "pending_source_ids": [],
                "supported_claim_ids": [f"claim_{index}" for index in range(1, 10, 2)],
                "evidence_strength_before": 2,
                "evidence_strength_after": 4,
                "value_capture_score_review_status": "supported",
                "bottleneck_score_review_status": "supported",
                "value_bases": ["technology_barrier"],
                "evidence_gap_status": "covered",
                "node_review_status": "reviewed",
                "rationale": "Fixture rationale",
                "next_evidence_needed": "Fixture next evidence",
            },
        ],
    }
    for name, payload in {
        "manifest.json": manifest,
        "sample_theme.json": theme,
        "sample_source_pack.json": source_pack,
        "sample_company_mapping.json": company_mapping,
        "sample_node_evidence_matrix.json": matrix,
    }.items():
        (root / name).write_text(json.dumps(payload), encoding="utf-8")
    return root / "manifest.json"


def _write_two_theme_manifest(root: Path) -> Path:
    manifest_path = _write_ready_batch(root)
    manifest = _read_json(manifest_path)
    manifest["target_theme_count"] = 2
    manifest["waves"]["wave_b"] = ["second_chain"]
    manifest["themes"]["second_chain"] = {
        "theme_id": "second_theme_v1",
        "artifacts": {
            "theme": "second_theme.json",
            "company_mapping": "second_company_mapping.json",
            "source_pack": "second_source_pack.json",
            "node_evidence_matrix": "second_node_evidence_matrix.json",
        },
    }
    _write_json(manifest_path, manifest)
    return manifest_path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _break_gate(root: Path, mutation: str) -> None:
    paths = {
        "accepted_sources": root / "sample_source_pack.json",
        "primary_sources": root / "sample_source_pack.json",
        "claims": root / "sample_theme.json",
        "reviewed_mappings": root / "sample_company_mapping.json",
    }
    path = paths[mutation]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "accepted_sources":
        payload["sources"][-1]["review_status"] = "pending"
    elif mutation == "primary_sources":
        payload["sources"][3]["source_type"] = "broker_report"
    elif mutation == "claims":
        payload["claims"].pop()
    else:
        payload["company_mappings"][-1]["review_status"] = "draft"
    path.write_text(json.dumps(payload), encoding="utf-8")
