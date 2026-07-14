from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

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
        "reviewed_mappings": 8,
    }
    assert theme["required_sections_ready"] is True
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
    assert theme["counts"]["accepted_sources"] == 9
    assert theme["checks"]["source_rows_valid"] is False
    assert any("duplicate source_id" in error for error in theme["errors"])


def test_invalid_source_review_status_is_an_explicit_integrity_failure(tmp_path: Path):
    manifest_path = _write_ready_batch(tmp_path)
    path = tmp_path / "sample_source_pack.json"
    payload = _read_json(path)
    payload["sources"][-1]["review_status"] = "bogus"
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["checks"]["source_rows_valid"] is False
    assert any("review_status is invalid" in error for error in theme["errors"])


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


def test_known_nonaccepted_source_claim_is_retained_but_not_counted(
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
            "url": "https://example.com/pending",
            "reliability_level": "S2",
            "document_status": "metadata_only",
            "evidence_locator": "page pending",
            "evidence_summary": "Pending evidence",
            "limitations": "Not accepted",
        }
    )
    _write_json(source_path, source_pack)
    theme_path = tmp_path / "sample_theme.json"
    theme_payload = _read_json(theme_path)
    theme_payload["claims"].append(
        {
            "claim_id": "pending_claim",
            "theme_id": "sample_theme_v1",
            "source_id": "pending_source",
            "claim_text": "Pending claim",
            "claim_type": "value_capture",
            "affected_theme_nodes": ["node_1"],
        }
    )
    _write_json(theme_path, theme_payload)
    matrix_path = tmp_path / "sample_node_evidence_matrix.json"
    matrix_payload = _read_json(matrix_path)
    matrix_payload["node_evidence_matrix"][0]["supported_claim_ids"].append(
        "pending_claim"
    )
    _write_json(matrix_path, matrix_payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is True
    assert theme["counts"]["claims"] == 10
    assert theme["checks"]["claim_rows_valid"] is True
    assert theme["checks"]["node_evidence_matrix_coverage"] is True


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
        payload["evidence_items"][-1]["evidence_type"] = "company_mention"
    elif mutation == "raw_mapping_source":
        payload["sources"][-1]["title"] = ""
    elif mutation == "raw_evidence":
        payload["evidence_items"][-1]["evidence_summary"] = ""
    else:
        mapping["review_status"] = "bogus"
    _write_json(path, payload)

    theme = build_theme_batch_report(manifest_path)["theme_results"][0]

    assert theme["ready"] is False
    assert theme["counts"]["reviewed_mappings"] == 7
    assert theme["checks"]["mapping_rows_valid"] is False
    assert any("mapping" in error or "evidence" in error for error in theme["errors"])


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
        "theme": {"theme_id": "sample_theme_v1"},
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
            {"node_id": "node_1", "theme_id": "sample_theme_v1"},
            {"node_id": "node_2", "theme_id": "sample_theme_v1"},
        ],
        "claims": [
            {
                "claim_id": f"claim_{index}",
                "theme_id": "sample_theme_v1",
                "source_id": f"source_{index}",
                "claim_text": f"Claim {index}",
                "claim_type": "catalyst" if index == 8 else "risk" if index == 9 else "value_capture",
                "affected_theme_nodes": [f"node_{index % 2 + 1}"],
            }
            for index in range(10)
        ],
    }
    source_pack = {
        "theme_id": "sample_theme_v1",
        "sources": [
            {
                "source_id": f"source_{index}",
                "review_status": "accepted",
                "source_type": "company_filing" if index < 4 else "broker_report",
                "title": f"Source {index}",
                "publisher": f"Publisher {index}",
                "url": f"https://example.com/source-{index}",
                "reliability_level": "S0" if index < 4 else "S2",
                "document_status": "full_text_reviewed",
                "evidence_locator": f"page {index + 1}",
                "evidence_summary": f"Evidence summary {index}",
                "limitations": "Fixture limitation",
            }
            for index in range(10)
        ],
    }
    company_mapping = {
        "theme_id": "sample_theme_v1",
        "sources": [
            {
                "source_id": f"source_{index}",
                "source_type": "company_filing",
                "title": f"Company filing {index}",
                "publisher": f"Company {index}",
                "url_or_ref": f"https://example.com/company-{index}",
                "reliability_level": "S0",
                "review_status": "accepted",
            }
            for index in range(8)
        ],
        "evidence_items": [
            {
                "evidence_id": f"evidence_{index}",
                "source_id": f"source_{index}",
                "evidence_type": "product_relationship",
                "evidence_summary": f"Scoped relationship {index}",
                "related_company_codes": [f"00000{index}.SZ"],
                "related_node_ids": [f"node_{index % 2 + 1}"],
            }
            for index in range(8)
        ],
        "company_mappings": [
            {
                "mapping_id": f"mapping_{index}",
                "theme_id": "sample_theme_v1",
                "company_code": f"00000{index}.SZ",
                "mapped_node_id": f"node_{index % 2 + 1}",
                "confidence": 0.9,
                "evidence_ids": [f"evidence_{index}"],
                "review_status": "reviewed",
            }
            for index in range(8)
        ],
    }
    matrix = {
        "theme_id": "sample_theme_v1",
        "node_evidence_matrix": [
            {
                "node_id": "node_1",
                "accepted_source_ids": [f"source_{index}" for index in range(0, 10, 2)],
                "supported_claim_ids": [f"claim_{index}" for index in range(0, 10, 2)],
                "evidence_gap_status": "covered",
            },
            {
                "node_id": "node_2",
                "accepted_source_ids": [f"source_{index}" for index in range(1, 10, 2)],
                "supported_claim_ids": [f"claim_{index}" for index in range(1, 10, 2)],
                "evidence_gap_status": "covered",
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
