from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from stock_research.industry_chain_theme_research import WAVE_F_CHAIN_THEMES
from stock_research.technology_industry_catalog import load_industry_catalog


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "wave_f_five_industry_chain_themes_v1.json"
)
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("verify_wave_f_batch", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

WAVE_F_CASES = {
    "ai_foundation_models_application_software": (
        "ai_foundation_models_application_software_value_chain_v1"
    ),
    "uav_evtol_low_altitude_economy": (
        "uav_evtol_low_altitude_economy_value_chain_v1"
    ),
    "mobile_communications_5g_6g": "mobile_communications_5g_6g_value_chain_v1",
    "analog_mixed_signal_rf_chips": "analog_mixed_signal_rf_chips_value_chain_v1",
    "rare_earth_permanent_magnets_critical_minerals": (
        "rare_earth_permanent_magnets_critical_minerals_value_chain_v1"
    ),
}

REQUIRED_READABLE_SECTIONS = [
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
]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def artifact_paths(chain_id: str, theme_id: str) -> dict[str, Path]:
    return {
        "theme": REPOSITORY_ROOT
        / f"artifacts/theme_decomposition/{theme_id}.json",
        "company_mapping": REPOSITORY_ROOT
        / "artifacts/theme_decomposition/company_mappings"
        / f"{chain_id}_company_mapping_v1.json",
        "source_pack": REPOSITORY_ROOT
        / "artifacts/theme_decomposition/source_packs"
        / f"{chain_id}_source_pack_v1.json",
        "node_evidence_matrix": REPOSITORY_ROOT
        / "artifacts/theme_decomposition/source_packs"
        / f"{chain_id}_node_evidence_matrix_v1.json",
    }


def manifest_artifact_paths(chain_id: str, theme_id: str) -> dict[str, str]:
    return {
        key: path.relative_to(REPOSITORY_ROOT).as_posix()
        for key, path in artifact_paths(chain_id, theme_id).items()
    }


def assert_catalog_first_contract(
    chain_id: str,
    theme_id: str,
    expected_l3: set[str],
    expected_l4: set[str],
) -> None:
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == chain_id]
    l3_ids = {row["node_id"] for row in chain_nodes if row["level"] == "L3"}
    l4_ids = {row["node_id"] for row in chain_nodes if row["level"] == "L4"}
    assert l3_ids == expected_l3
    assert l4_ids == expected_l4

    matching_links = [
        row for row in catalog["theme_links"] if row["theme_id"] == theme_id
    ]
    assert len(matching_links) == 1
    link = matching_links[0]
    assert link["chain_id"] == chain_id
    assert link["theme_id"] == theme_id
    assert link["unmapped_theme_node_ids"] == []

    linked_l4_by_theme_node = {
        row["theme_node_id"]: row["catalog_node_id"]
        for row in link["node_links"]
        if row["catalog_node_id"] in l4_ids
    }
    assert set(linked_l4_by_theme_node.values()) == l4_ids

    mapping = load_json(artifact_paths(chain_id, theme_id)["company_mapping"])
    reviewed_mappings = [
        row
        for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    ]
    for reviewed_mapping in reviewed_mappings:
        mapped_node_id = reviewed_mapping["mapped_node_id"]
        assert mapped_node_id in linked_l4_by_theme_node
        assert linked_l4_by_theme_node[mapped_node_id] in l4_ids


def test_wave_f_manifest_freezes_research_scope() -> None:
    manifest = VERIFIER.load_theme_batch_manifest(MANIFEST_PATH)
    expected_completion_gates = {
        "min_accepted_sources": 10,
        "min_primary_sources": 8,
        "min_claims": 12,
        "min_reviewed_mappings": 8,
        "require_node_evidence_matrix_coverage": True,
        "require_bidirectional_evidence_contract": True,
        "require_precise_mapping_locators": True,
        "required_readable_sections": REQUIRED_READABLE_SECTIONS,
    }
    expected_themes = {
        chain_id: {
            "theme_id": theme_id,
            "artifacts": manifest_artifact_paths(chain_id, theme_id),
        }
        for chain_id, theme_id in WAVE_F_CASES.items()
    }

    assert manifest == {
        "schema_version": "industry_chain_theme_batch_v1",
        "batch_id": "wave_f_five_industry_chain_themes_v1",
        "target_theme_count": 5,
        "artifact_base": "../../..",
        "primary_source_types": [
            "company_filing",
            "official_report",
            "official_article",
        ],
        "completion_gates": expected_completion_gates,
        "waves": {"wave_f": list(WAVE_F_CASES)},
        "themes": expected_themes,
    }
    assert list(manifest["themes"]) == list(WAVE_F_CASES)


def test_wave_f_scope_uses_existing_canonical_catalog_chains() -> None:
    catalog = load_industry_catalog()
    chains_by_id = {row["chain_id"]: row for row in catalog["chains"]}

    assert len(catalog["chains"]) == 82
    assert list(WAVE_F_CASES) == [
        "ai_foundation_models_application_software",
        "uav_evtol_low_altitude_economy",
        "mobile_communications_5g_6g",
        "analog_mixed_signal_rf_chips",
        "rare_earth_permanent_magnets_critical_minerals",
    ]
    assert set(WAVE_F_CASES) <= set(chains_by_id)
    assert {
        chains_by_id[chain_id]["chain_kind"] for chain_id in WAVE_F_CASES
    } == {"canonical_industry_chain"}


def test_wave_f_registry_matches_manifest() -> None:
    manifest = VERIFIER.load_theme_batch_manifest(MANIFEST_PATH)

    assert WAVE_F_CHAIN_THEMES == WAVE_F_CASES
    assert {
        chain_id: metadata["theme_id"]
        for chain_id, metadata in manifest["themes"].items()
    } == WAVE_F_CHAIN_THEMES
