from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from stock_research.industry_chain_theme_research import WAVE_G_CHAIN_THEMES
from stock_research.technology_industry_catalog import load_industry_catalog


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "wave_g_five_industry_chain_themes_v1.json"
)
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("verify_wave_g_batch", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

WAVE_G_CASES = {
    "mems_intelligent_sensors": "mems_intelligent_sensors_value_chain_v1",
    "wafer_manufacturing_specialty_processes": (
        "wafer_manufacturing_specialty_processes_value_chain_v1"
    ),
    "civil_aircraft_aero_engines": "civil_aircraft_aero_engines_value_chain_v1",
    "nuclear_power_equipment": "nuclear_power_equipment_value_chain_v1",
    "scientific_instruments": "scientific_instruments_value_chain_v1",
}

G1_CHAIN_ID = "mems_intelligent_sensors"
G1_THEME_ID = "mems_intelligent_sensors_value_chain_v1"
G1_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{G1_THEME_ID}.json"
G1_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "mems_intelligent_sensors_company_mapping_v1.json"
)
G1_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "mems_intelligent_sensors_source_pack_v1.json"
)
G1_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "mems_intelligent_sensors_node_evidence_matrix_v1.json"
)
G1_L3 = {
    "mems_sensor_devices",
    "mems_fabrication_packaging",
    "intelligent_sensor_integration",
    "mems_commercial_validation",
}
G1_L4 = {
    "mems_inertial_accelerometer_gyroscope",
    "mems_pressure_flow_environmental_sensors",
    "mems_acoustic_microphones",
    "mems_rf_filters_resonators",
    "mems_optical_micro_mirror_lidar",
    "mems_foundry_wafer_process",
    "mems_packaging_calibration_test",
    "intelligent_sensor_fusion_modules",
    "design_win_mass_production_revenue_validation",
}
G1_INITIAL_UNIVERSE = {
    "002241.SZ", "688396.SH", "600460.SH", "300456.SZ", "688286.SH",
    "688052.SH", "300007.SZ", "300667.SZ", "603662.SH", "688582.SH",
}
G1_EXCLUDED_INITIAL = {"688052.SH", "300667.SZ", "603662.SH"}
G1_MAPPING_CONTRACTS = {
    "002241.SZ": ("mems_acoustic_microphones", "g1_002241_ar2025"),
    "688396.SH": ("mems_foundry_wafer_process", "g1_688396_ar2025"),
    "600460.SH": ("mems_foundry_wafer_process", "g1_600460_ar2025"),
    "300456.SZ": ("mems_foundry_wafer_process", "g1_300456_ar2025"),
    "688286.SH": ("mems_acoustic_microphones", "g1_688286_ar2025"),
    "300007.SZ": ("mems_pressure_flow_environmental_sensors", "g1_300007_ar2025"),
    "688582.SH": ("mems_inertial_accelerometer_gyroscope", "g1_688582_ar2025"),
    "603005.SH": ("mems_packaging_calibration_test", "g1_603005_ar2025"),
}
G1_REVENUE_ROLE_CONTRACTS = {
    "002241.SZ": "revenue_boundary",
    "688396.SH": "revenue_boundary",
    "600460.SH": "revenue_boundary",
    "300456.SZ": "revenue_materiality",
    "688286.SH": "revenue_materiality",
    "300007.SZ": "revenue_boundary",
    "688582.SH": "revenue_materiality",
    "603005.SH": "revenue_boundary",
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


def test_wave_g_manifest_freezes_research_scope() -> None:
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
        for chain_id, theme_id in WAVE_G_CASES.items()
    }

    assert manifest == {
        "schema_version": "industry_chain_theme_batch_v1",
        "batch_id": "wave_g_five_industry_chain_themes_v1",
        "target_theme_count": 5,
        "artifact_base": "../../..",
        "primary_source_types": [
            "company_filing",
            "official_report",
            "official_article",
        ],
        "completion_gates": expected_completion_gates,
        "waves": {"wave_g": list(WAVE_G_CASES)},
        "themes": expected_themes,
    }
    assert list(manifest["themes"]) == list(WAVE_G_CASES)


def test_wave_g_scope_uses_existing_canonical_catalog_chains() -> None:
    catalog = load_industry_catalog()
    chains_by_id = {row["chain_id"]: row for row in catalog["chains"]}

    assert len(catalog["chains"]) == 82
    assert list(WAVE_G_CASES) == [
        "mems_intelligent_sensors",
        "wafer_manufacturing_specialty_processes",
        "civil_aircraft_aero_engines",
        "nuclear_power_equipment",
        "scientific_instruments",
    ]
    assert set(WAVE_G_CASES) <= set(chains_by_id)
    assert {
        chains_by_id[chain_id]["chain_kind"] for chain_id in WAVE_G_CASES
    } == {"canonical_industry_chain"}


def test_wave_g_registry_matches_manifest() -> None:
    manifest = VERIFIER.load_theme_batch_manifest(MANIFEST_PATH)

    assert WAVE_G_CHAIN_THEMES == WAVE_G_CASES
    assert {
        chain_id: metadata["theme_id"]
        for chain_id, metadata in manifest["themes"].items()
    } == WAVE_G_CHAIN_THEMES


def test_mems_g1_catalog_first_exact_tree_and_direct_link_contract() -> None:
    assert_catalog_first_contract(G1_CHAIN_ID, G1_THEME_ID, G1_L3, G1_L4)
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == G1_CHAIN_ID]
    by_id = {row["node_id"]: row for row in chain_nodes}
    assert {row["node_kind"] for row in chain_nodes} == {"canonical"}
    assert all(not row["canonical_key"] for row in chain_nodes if row["level"] == "L3")
    l4_keys = [row["canonical_key"] for row in chain_nodes if row["level"] == "L4"]
    assert len(l4_keys) == len(set(l4_keys)) == 9
    assert all(key.startswith("mems_intelligent_sensors:") for key in l4_keys)
    for row in chain_nodes:
        assert row["primary_path"][1] == G1_CHAIN_ID
        if row["level"] == "L4":
            assert row["parent_node_id"] in G1_L3
            assert by_id[row["parent_node_id"]]["level"] == "L3"

    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == G1_THEME_ID
    )
    assert len(link["node_links"]) == 9
    assert {
        (row["theme_node_id"], row["catalog_node_id"])
        for row in link["node_links"]
    } == {(node_id, node_id) for node_id in G1_L4}


def test_mems_g1_artifacts_are_reviewed_and_meet_wave_gate() -> None:
    theme = load_json(G1_THEME_PATH)
    mapping = load_json(G1_MAPPING_PATH)
    source_pack = load_json(G1_SOURCE_PACK_PATH)
    matrix = load_json(G1_MATRIX_PATH)
    assert theme["artifact_version"] == "theme_decomposition_v1_6"
    assert mapping["evidence_contract_version"] == "mapping_evidence_roles_v2"
    assert theme["theme"]["status"] == "reviewed"
    assert {row["node_id"] for row in theme["nodes"]} == G1_L4
    assert len(source_pack["sources"]) >= 10
    assert sum(
        row["source_type"] in {"company_filing", "official_report", "official_article"}
        for row in source_pack["sources"]
    ) >= 8
    assert len(theme["claims"]) >= 12
    reviewed = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    assert len(reviewed) >= 8
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == G1_L4

    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_g")
    rows = {row["chain_id"]: row for row in report["theme_results"]}
    assert rows[G1_CHAIN_ID]["ready"] is True
    assert rows[G1_CHAIN_ID]["counts"]["accepted_sources"] >= 10
    assert rows[G1_CHAIN_ID]["counts"]["primary_sources"] >= 8
    assert rows[G1_CHAIN_ID]["counts"]["claims"] >= 12
    assert rows[G1_CHAIN_ID]["counts"]["reviewed_mappings"] >= 8


def test_mems_g1_company_three_role_evidence_and_initial_universe_closure() -> None:
    mapping = load_json(G1_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    reviewed = {
        row["company_code"]: row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    excluded = {
        row["company_code"]: row for row in mapping["excluded_initial_candidates"]
    }
    assert set(reviewed) == set(G1_MAPPING_CONTRACTS)
    assert set(excluded) == G1_EXCLUDED_INITIAL
    assert (set(reviewed) & G1_INITIAL_UNIVERSE) | set(excluded) == G1_INITIAL_UNIVERSE
    assert not set(reviewed) & set(excluded)
    assert reviewed.keys() - G1_INITIAL_UNIVERSE == {"603005.SH"}
    assert "补充" in reviewed["603005.SH"]["notes"]
    for company_code, (node_id, source_id) in G1_MAPPING_CONTRACTS.items():
        row = reviewed[company_code]
        assert row["mapped_node_id"] == node_id
        items = [evidence[evidence_id] for evidence_id in row["evidence_ids"]]
        assert [item["evidence_type"] for item in items] == [
            "product_relationship",
            G1_REVENUE_ROLE_CONTRACTS[company_code],
            "business_stage",
        ]
        assert len({item["excerpt_locator"] for item in items}) == 3
        assert all(item["source_id"] == source_id for item in items)
        assert all(item["related_node_ids"] == [node_id] for item in items)
    assert mapping["concept_only_candidates"] == []


def test_mems_g1_commercial_validation_company_names_and_codes_are_one_to_one() -> None:
    theme = load_json(G1_THEME_PATH)
    commercial = next(
        row for row in theme["nodes"]
        if row["node_id"] == "design_win_mass_production_revenue_validation"
    )
    expected = {
        "002241.SZ": "歌尔股份",
        "688396.SH": "华润微",
        "600460.SH": "士兰微",
        "300456.SZ": "赛微电子",
        "688286.SH": "敏芯股份",
        "688582.SH": "芯动联科",
        "603005.SH": "晶方科技",
    }
    assert len(commercial["related_stock_codes"]) == len(commercial["domestic_players"])
    assert dict(zip(commercial["related_stock_codes"], commercial["domestic_players"])) == expected


def test_mems_g1_source_identity_claim_union_and_matrix_are_direct() -> None:
    theme = load_json(G1_THEME_PATH)
    mapping = load_json(G1_MAPPING_PATH)
    source_pack = load_json(G1_SOURCE_PACK_PATH)
    matrix = load_json(G1_MATRIX_PATH)
    identity_fields = (
        "source_id", "source_type", "title", "publisher", "author",
        "publish_date", "url_or_ref", "access_level", "reliability_level",
        "review_status", "notes",
    )
    identity = lambda rows: {
        row["source_id"]: tuple(
            row.get(field, row.get("url") if field == "url_or_ref" else None)
            for field in identity_fields
        ) for row in rows
    }
    assert identity(theme["sources"]) == identity(mapping["sources"])
    assert identity(theme["sources"]) == identity(source_pack["sources"])
    assert all(row["author"] == row["publisher"] and row["author"] for row in theme["sources"])

    claims = {row["claim_id"]: row for row in theme["claims"]}
    accepted = {
        row["source_id"] for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    claim_union = {
        source_id for claim in claims.values()
        for source_id in (claim["source_id"], *claim["supporting_source_ids"])
    }
    matrix_union = {
        source_id for row in matrix["node_evidence_matrix"]
        for source_id in row["accepted_source_ids"]
    }
    assert accepted == claim_union == matrix_union
    for row in matrix["node_evidence_matrix"]:
        node_claims = {
            claim_id for claim_id, claim in claims.items()
            if row["node_id"] in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == node_claims
        assert set(row["accepted_source_ids"]) == {
            claims[claim_id]["source_id"] for claim_id in node_claims
        }
    for source in source_pack["sources"]:
        source_claims = {
            claim_id for claim_id, claim in claims.items()
            if source["source_id"] in (claim["source_id"], *claim["supporting_source_ids"])
        }
        assert set(source["supported_claim_ids"]) == source_claims
        assert set(source["supported_node_ids"]) == {
            node_id for claim_id in source_claims
            for node_id in claims[claim_id]["affected_theme_nodes"]
        }
    bichuang = next(
        row for row in source_pack["sources"]
        if row["source_id"] == "g1_300667_ar2025"
    )
    assert bichuang["review_status"] == "rejected"
    assert bichuang["supported_claim_ids"] == []
    assert bichuang["supported_node_ids"] == []


def test_mems_g1_lifecycle_and_neighbor_chain_boundaries_are_explicit() -> None:
    theme = load_json(G1_THEME_PATH)
    mapping = load_json(G1_MAPPING_PATH)
    text = json.dumps({"theme": theme, "policy": mapping["mapping_policy"]}, ensure_ascii=False)
    for stage in ("研究", "样品", "design win", "量产", "订单", "收入"):
        assert stage in text
    for boundary in (
        "专利或实验室原型只作research lead",
        "产线机器视觉与工业检测系统保持工业检测链所有权",
        "人形机器人专用集成保持人形机器人链所有权",
        "纯模拟芯片与非MEMS传感器不得映射",
        "通用封测与generic foundry不得映射",
        "G2拥有晶圆制造特色工艺，G1仅拥有MEMS专用工艺",
        "混合口径公司总营收不作为节点收入",
    ):
        assert boundary in text
    excluded_by_code = {
        row["company_code"]: row["reason"]
        for row in mapping["excluded_initial_candidates"]
    }
    assert "模拟" in excluded_by_code["688052.SH"]
    assert "非MEMS" in excluded_by_code["603662.SH"]
    assert "自有MEMS" in excluded_by_code["300667.SZ"]


def test_mems_g1_has_no_unproven_cross_chain_edges() -> None:
    catalog = load_industry_catalog()
    nodes = {row["node_id"]: row for row in catalog["nodes"]}
    cross_chain_edges = {
        (row["source_node_id"], row["target_node_id"], row["relationship_type"])
        for row in catalog["edges"]
        if row["source_node_id"] in G1_L4
        and nodes[row["target_node_id"]]["chain_id"] != G1_CHAIN_ID
    }
    assert cross_chain_edges == set()


def test_mems_g1_matrix_calibrates_unmapped_nodes_and_evidence_gaps() -> None:
    theme = load_json(G1_THEME_PATH)
    matrix = load_json(G1_MATRIX_PATH)
    nodes = {row["node_id"]: row for row in theme["nodes"]}
    rows = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}
    assert set(rows) == G1_L4
    assert len({row["rationale"] for row in rows.values()}) == 9
    assert all(row["next_evidence_needed"] for row in rows.values())
    for node_id, row in rows.items():
        assert nodes[node_id]["evidence_strength"] == row["evidence_strength_after"]
    for empty_node in ("mems_rf_filters_resonators", "mems_optical_micro_mirror_lidar"):
        assert rows[empty_node]["accepted_source_ids"] == []
        assert rows[empty_node]["supported_claim_ids"] == []
        assert rows[empty_node]["evidence_gap_status"] == "evidence_gap"
        assert rows[empty_node]["node_review_status"] == "needs_evidence"
        assert nodes[empty_node]["related_stock_codes"] == []
        assert nodes[empty_node]["domestic_players"] == []
    fusion = rows["intelligent_sensor_fusion_modules"]
    assert fusion["evidence_strength_after"] <= 2
    assert fusion["node_review_status"] == "needs_evidence"
    assert fusion["evidence_gap_status"] == "evidence_gap"
    assert fusion["accepted_source_ids"] == []
    assert fusion["supported_claim_ids"] == []
    assert "直接MEMS通道+融合模组量产/收入" in fusion["next_evidence_needed"]
    assert nodes["intelligent_sensor_fusion_modules"]["node_review_status"] == "needs_evidence"
    assert nodes["intelligent_sensor_fusion_modules"]["evidence_strength"] <= 2
    assert nodes["intelligent_sensor_fusion_modules"]["related_stock_codes"] == []
    assert nodes["intelligent_sensor_fusion_modules"]["domestic_players"] == []
    claims = {row["claim_id"]: row for row in theme["claims"]}
    assert "g1_claim_09" not in claims
    assert not any(
        "intelligent_sensor_fusion_modules" in row["affected_theme_nodes"]
        for row in claims.values()
    )
