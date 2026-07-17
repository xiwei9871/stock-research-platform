from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "wave_e_five_industry_chain_themes_v1.json"
)

WAVE_E_CASES = {
    "satellite_communications_navigation_remote_sensing": (
        "satellite_communications_navigation_remote_sensing_value_chain_v1"
    ),
    "intelligent_transport_vehicle_road_cloud": (
        "intelligent_transport_vehicle_road_cloud_value_chain_v1"
    ),
    "brain_computer_interfaces_neural_engineering": (
        "brain_computer_interfaces_neural_engineering_value_chain_v1"
    ),
    "controlled_nuclear_fusion": "controlled_nuclear_fusion_value_chain_v1",
    "quantum_computing_communication_measurement": (
        "quantum_computing_communication_measurement_value_chain_v1"
    ),
}


def _paths(chain_id: str, theme_id: str) -> dict[str, str]:
    return {
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


def test_wave_e_manifest_freezes_research_scope() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    expected_completion_gates = {
        "min_accepted_sources": 10,
        "min_primary_sources": 8,
        "min_claims": 12,
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
            {
                "name": "价值链",
                "non_empty": [
                    "theme:research_profile.value_flow_summary",
                    "theme:nodes",
                ],
            },
            {
                "name": "利润池与竞争壁垒",
                "non_empty": ["theme:research_profile.profit_pool_summary"],
            },
            {
                "name": "催化、验证信号与风险",
                "non_empty": [
                    "theme:research_profile.catalyst_claim_ids",
                    "theme:research_profile.risk_claim_ids",
                    "theme:research_profile.validation_signals",
                ],
            },
            {
                "name": "受益公司",
                "non_empty": ["company_mapping:company_mappings"],
            },
            {
                "name": "来源证据",
                "non_empty": ["source_pack:sources"],
            },
            {
                "name": "证据缺口与更新",
                "non_empty": [
                    "theme:research_profile.evidence_gap_summary",
                    "node_evidence_matrix:node_evidence_matrix",
                ],
            },
        ],
    }
    expected_themes = {
        chain_id: {
            "theme_id": theme_id,
            "artifacts": _paths(chain_id, theme_id),
        }
        for chain_id, theme_id in WAVE_E_CASES.items()
    }

    assert manifest["schema_version"] == "industry_chain_theme_batch_v1"
    assert manifest["batch_id"] == "wave_e_five_industry_chain_themes_v1"
    assert manifest["target_theme_count"] == 5
    assert manifest["artifact_base"] == "../../.."
    assert manifest["primary_source_types"] == [
        "company_filing",
        "official_report",
        "official_article",
    ]
    assert manifest["completion_gates"] == expected_completion_gates
    assert manifest["waves"] == {"wave_e": list(WAVE_E_CASES)}
    assert manifest["themes"] == expected_themes
    assert list(manifest["themes"]) == list(WAVE_E_CASES)
