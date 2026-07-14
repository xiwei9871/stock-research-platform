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
    assert all(
        set(metadata["artifacts"])
        == {"theme", "company_mapping", "source_pack", "node_evidence_matrix"}
        for metadata in manifest["themes"].values()
    )
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
        "nodes": [{"node_id": "node_1"}],
        "claims": [{"claim_id": f"claim_{index}"} for index in range(10)],
    }
    source_pack = {
        "theme_id": "sample_theme_v1",
        "sources": [
            {
                "source_id": f"source_{index}",
                "review_status": "accepted",
                "source_type": "company_filing" if index < 4 else "industry_report",
            }
            for index in range(10)
        ],
    }
    company_mapping = {
        "theme_id": "sample_theme_v1",
        "company_mappings": [
            {"mapping_id": f"mapping_{index}", "review_status": "reviewed"}
            for index in range(8)
        ],
    }
    matrix = {
        "theme_id": "sample_theme_v1",
        "node_evidence_matrix": [{"node_id": "node_1", "evidence_gap_status": "evidence_gap"}],
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
        payload["sources"][3]["source_type"] = "industry_report"
    elif mutation == "claims":
        payload["claims"].pop()
    else:
        payload["company_mappings"][-1]["review_status"] = "draft"
    path.write_text(json.dumps(payload), encoding="utf-8")
