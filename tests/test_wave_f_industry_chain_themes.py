from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from stock_research.industry_chain_theme_research import WAVE_F_CHAIN_THEMES
from stock_research.dashboard.theme_research import list_theme_research_sources
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

F1_CHAIN_ID = "ai_foundation_models_application_software"
F1_THEME_ID = "ai_foundation_models_application_software_value_chain_v1"
F1_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{F1_THEME_ID}.json"
F1_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "ai_foundation_models_application_software_company_mapping_v1.json"
)
F1_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "ai_foundation_models_application_software_source_pack_v1.json"
)
F1_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "ai_foundation_models_application_software_node_evidence_matrix_v1.json"
)

F1_L3 = {
    "ai_model_platforms",
    "ai_application_delivery",
    "ai_commercialization_operations",
    "ai_governance_validation",
}
F1_L4 = {
    "foundation_model_training_inference_platforms",
    "model_toolchain_finetuning_rag",
    "ai_agent_orchestration_workflow",
    "enterprise_ai_application_software",
    "consumer_ai_application_services",
    "industry_solution_delivery_integration",
    "subscription_usage_licensing_monetization",
    "customer_adoption_renewal_revenue_validation",
    "data_security_model_governance_compliance",
}
F1_INITIAL_UNIVERSE = {
    "002230.SZ",
    "688111.SH",
    "600588.SH",
    "601360.SH",
    "300229.SZ",
    "300634.SZ",
    "300170.SZ",
    "300624.SZ",
    "300339.SZ",
    "300378.SZ",
}
F1_MAPPING_CONTRACTS = {
    "002230.SZ": {
        "node": "foundation_model_training_inference_platforms",
        "source": "f1_002230_ar2025",
        "revenue_relevance": "limited",
        "business_materiality": "meaningful_segment",
        "locators": {
            "product_relationship": "第11页，讯飞星火X1/X1.5及全栈模型平台",
            "revenue_materiality": "第12页，PPT创作智能体线上营收同比增长186%",
            "business_stage": "第13页，智能批阅机学校覆盖、日均作业量与续费模式",
        },
    },
    "688111.SH": {
        "node": "enterprise_ai_application_software",
        "source": "f1_688111_ar2025",
        "revenue_relevance": "undisclosed",
        "business_materiality": "meaningful_segment",
        "locators": {
            "product_relationship": "第11-12页，WPS AI助手、企业版与政务版产品",
            "revenue_materiality": "第18页，WPS 365收入但未单列AI产品收入",
            "business_stage": "第16页，WPS AI月活与Token调用量",
        },
    },
    "600588.SH": {
        "node": "enterprise_ai_application_software",
        "source": "f1_600588_ar2025",
        "revenue_relevance": "undisclosed",
        "business_materiality": "emerging_segment",
        "locators": {
            "product_relationship": "第20页，用友BIP 5、YonGPT与企业AI产品矩阵",
            "revenue_materiality": "第19页，AI相关合同签约16.7亿元但未披露确认收入",
            "business_stage": "第20页，AI产品和服务签约客户超过400家",
        },
    },
    "601360.SH": {
        "node": "consumer_ai_application_services",
        "source": "f1_601360_ar2025",
        "revenue_relevance": "undisclosed",
        "business_materiality": "emerging_segment",
        "locators": {
            "product_relationship": "第17页，纳米AI多智能体蜂群与超级搜索智能体",
            "revenue_materiality": "第15页，公司宽口径收入未单列纳米AI收入",
            "business_stage": "第17页，纳米AI产品月访问量合计超过4.5亿次",
        },
    },
    "300229.SZ": {
        "node": "model_toolchain_finetuning_rag",
        "source": "f1_300229_ar2025",
        "revenue_relevance": "undisclosed",
        "business_materiality": "emerging_segment",
        "locators": {
            "product_relationship": "第13-14页，拓天大模型、动态本体与智能体平台",
            "revenue_materiality": "第30页，新业务试用培育且尚未规模化变现",
            "business_stage": "第45页，近2000万元消保智能体项目及多行业落地",
        },
    },
    "300634.SZ": {
        "node": "ai_agent_orchestration_workflow",
        "source": "f1_300634_ar2025",
        "revenue_relevance": "undisclosed",
        "business_materiality": "emerging_segment",
        "locators": {
            "product_relationship": "第9-10页，Rich AIBox与AI智慧办公产品套件",
            "revenue_materiality": "第24页，宽口径产品线收入未单列AI收入",
            "business_stage": "第13-14页，Rich AIBox平台认证与企业级应用定位",
        },
    },
    "300170.SZ": {
        "node": "industry_solution_delivery_integration",
        "source": "f1_300170_ar2025",
        "revenue_relevance": "undisclosed",
        "business_materiality": "emerging_segment",
        "locators": {
            "product_relationship": "第15-16页，得灵、灵手、灵猿与灵炼产品服务体系",
            "revenue_materiality": "第15页，AI智能体应用收入增长但未披露金额",
            "business_stage": "第28页，AI智能体在长期客户群中的落地与留存",
        },
    },
    "300624.SZ": {
        "node": "consumer_ai_application_services",
        "source": "f1_300624_ar2025",
        "revenue_relevance": "undisclosed",
        "business_materiality": "meaningful_segment",
        "locators": {
            "product_relationship": "第11页，万兴天幕、万兴超媒与万兴剧厂产品形态",
            "revenue_materiality": "第20页，公司总收入未单列AI产品收入",
            "business_stage": "第20页，AI服务器调用量超过13亿次",
        },
    },
    "300339.SZ": {
        "node": "ai_agent_orchestration_workflow",
        "source": "f1_300339_ar2025",
        "revenue_relevance": "undisclosed",
        "business_materiality": "emerging_segment",
        "locators": {
            "product_relationship": "第12页，AgentRUNS、AIRUNS与AI测试产品",
            "revenue_materiality": "第46页，公司宽口径收入未单列AI产品收入",
            "business_stage": "第12页，AI测试智能体签约并交付多家金融机构",
        },
    },
    "300378.SZ": {
        "node": "enterprise_ai_application_software",
        "source": "f1_300378_ar2025",
        "revenue_relevance": "undisclosed",
        "business_materiality": "emerging_segment",
        "locators": {
            "product_relationship": "第14-15页，雅典娜底座与企业智能体生成套件",
            "revenue_materiality": "第26页，AI相关业务签约近2亿元但未披露确认收入",
            "business_stage": "第26页，数十个应用及多行业可复制客户案例",
        },
    },
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


def test_foundation_models_f1_catalog_first_structure_and_link_contract() -> None:
    assert_catalog_first_contract(F1_CHAIN_ID, F1_THEME_ID, F1_L3, F1_L4)
    catalog = load_industry_catalog()
    chain_nodes = [
        row for row in catalog["nodes"] if row["chain_id"] == F1_CHAIN_ID
    ]
    by_id = {row["node_id"]: row for row in chain_nodes}
    assert {row["node_kind"] for row in chain_nodes} == {"canonical"}
    assert all(not row["canonical_key"] for row in chain_nodes if row["level"] == "L3")
    l4_keys = [row["canonical_key"] for row in chain_nodes if row["level"] == "L4"]
    assert len(l4_keys) == len(set(l4_keys)) == 9
    assert all(key.startswith("ai_application:") for key in l4_keys)
    for row in chain_nodes:
        assert row["primary_path"][1] == F1_CHAIN_ID
        if row["level"] == "L4":
            assert row["parent_node_id"] in F1_L3
            assert by_id[row["parent_node_id"]]["level"] == "L3"


def test_foundation_models_f1_artifacts_are_reviewed_and_wave_is_one_of_five_ready() -> None:
    theme = load_json(F1_THEME_PATH)
    mapping = load_json(F1_MAPPING_PATH)
    source_pack = load_json(F1_SOURCE_PACK_PATH)
    matrix = load_json(F1_MATRIX_PATH)
    assert theme["artifact_version"] == "theme_decomposition_v1_6"
    assert theme["theme"]["status"] == "reviewed"
    assert theme["theme"]["theme_id"] == F1_THEME_ID
    assert {row["node_id"] for row in theme["nodes"]} == F1_L4
    assert len(source_pack["sources"]) >= 10
    assert sum(row["source_type"] in {"company_filing", "official_report", "official_article"} for row in source_pack["sources"]) >= 8
    assert len(theme["claims"]) >= 12
    reviewed = [row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"]
    assert reviewed
    assert len(reviewed) >= 8
    assert len(reviewed) == 10
    assert {row["company_code"] for row in reviewed} == F1_INITIAL_UNIVERSE
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == F1_L4

    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_f")
    rows = {row["chain_id"]: row for row in report["theme_results"]}
    assert rows[F1_CHAIN_ID]["ready"] is True
    assert rows[F1_CHAIN_ID]["counts"] == {
        "accepted_sources": 10,
        "primary_sources": 10,
        "claims": 18,
        "accepted_source_backed_claims": 18,
        "reviewed_mappings": 10,
    }
    assert report["ready_theme_count"] == 1
    assert report["not_ready_theme_count"] == 4


def test_foundation_models_f1_full_research_profile_and_boundary_ownership() -> None:
    theme = load_json(F1_THEME_PATH)
    profile = theme["research_profile"]
    assert profile["catalog_chain_id"] == F1_CHAIN_ID
    for field in (
        "industry_stage",
        "central_conflict",
        "investment_summary",
        "value_flow_summary",
        "profit_pool_summary",
        "validation_signals",
        "evidence_gap_summary",
    ):
        assert profile[field]
    text = json.dumps(theme, ensure_ascii=False)
    for boundary in (
        "AI芯片、服务器、机柜与智算基础设施不属于本链",
        "云、数据中心与电力基础设施不属于本链",
        "操作系统、数据库与通用基础软件不属于本链",
        "通用工业软件只有形成AI特定产品或服务才属于本链",
        "通用安全产品只有承担模型或AI应用治理才属于本链",
    ):
        assert boundary in text


def test_foundation_models_f1_sources_claims_matrix_and_served_sources_are_synchronized() -> None:
    theme = load_json(F1_THEME_PATH)
    mapping = load_json(F1_MAPPING_PATH)
    source_pack = load_json(F1_SOURCE_PACK_PATH)
    matrix = load_json(F1_MATRIX_PATH)
    served = list_theme_research_sources(F1_THEME_ID, read_source="artifact")

    identity_fields = (
        "source_id", "source_type", "title", "publisher", "author",
        "publish_date", "url_or_ref", "access_level", "reliability_level",
        "review_status", "notes",
    )
    identity = lambda rows: {
        row["source_id"]: tuple(
            row.get(field, row.get("url") if field == "url_or_ref" else None)
            for field in identity_fields
        )
        for row in rows
    }
    assert identity(theme["sources"]) == identity(mapping["sources"])
    assert identity(theme["sources"]) == identity(source_pack["sources"])
    assert identity(theme["sources"]) == identity(served["items"])

    accepted = {
        row["source_id"] for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    claim_source_union = {
        source_id
        for claim in theme["claims"]
        for source_id in (claim["source_id"], *claim["supporting_source_ids"])
    }
    matrix_source_union = {
        source_id
        for row in matrix["node_evidence_matrix"]
        for source_id in row["accepted_source_ids"]
    }
    assert accepted == claim_source_union == matrix_source_union

    claims = {row["claim_id"]: row for row in theme["claims"]}
    for source in source_pack["sources"]:
        expected_claims = {
            claim_id for claim_id, claim in claims.items()
            if source["source_id"] in (claim["source_id"], *claim["supporting_source_ids"])
        }
        assert set(source["supported_claim_ids"]) == expected_claims
        assert set(source["supported_node_ids"]) == {
            node_id for claim_id in expected_claims
            for node_id in claims[claim_id]["affected_theme_nodes"]
        }


def test_foundation_models_f1_reviewed_company_mapping_contracts_are_exact() -> None:
    mapping = load_json(F1_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    reviewed = {
        row["company_code"]: row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    assert reviewed
    assert len(reviewed) >= 8
    assert set(reviewed) == set(F1_MAPPING_CONTRACTS)
    for company_code, contract in F1_MAPPING_CONTRACTS.items():
        row = reviewed[company_code]
        assert row["mapped_node_id"] == contract["node"]
        assert row["revenue_relevance"] == contract["revenue_relevance"]
        assert row["business_materiality"] == contract["business_materiality"]
        items = [evidence[evidence_id] for evidence_id in row["evidence_ids"]]
        assert [item["evidence_type"] for item in items] == [
            "product_relationship", "revenue_materiality", "business_stage"
        ]
        assert len({item["excerpt_locator"] for item in items}) == 3
        for item in items:
            assert item["source_id"] == contract["source"]
            assert item["excerpt_locator"] == contract["locators"][item["evidence_type"]]
        materiality = items[1]["evidence_summary"]
        if row["revenue_relevance"] == "undisclosed":
            assert any(term in materiality for term in ("未单列", "未披露确认收入", "未披露金额"))
        else:
            assert "AI特定产品或服务收入" in materiality


def test_foundation_models_f1_rejects_compute_cloud_general_software_and_generic_security_as_direct_mapping() -> None:
    mapping = load_json(F1_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    forbidden_solo_bases = (
        "GPU适配", "服务器销售", "智算中心建设", "云资源容量",
        "数据中心机柜", "操作系统发行版", "数据库收入", "通用工业软件收入",
        "通用网络安全收入",
    )
    for row in mapping["company_mappings"]:
        if row["review_status"] != "reviewed":
            continue
        direct = evidence[row["evidence_ids"][0]]["evidence_summary"]
        assert not any(term in direct for term in forbidden_solo_bases)
        assert any(
            term in direct
            for term in ("大模型", "智能体", "AI应用", "AI办公", "AI创作", "AI测试")
        )
    boundaries = mapping["mapping_policy"]["typed_dependency_boundaries"]
    assert set(boundaries) == {
        "ai_logic_compute_chips",
        "ai_compute_infrastructure",
        "cloud_data_center_infrastructure",
        "operating_systems_databases_foundational_software",
        "generic_industrial_software",
        "generic_cybersecurity",
    }


def test_foundation_models_f1_closes_the_initial_audit_universe_without_concept_only_leakage() -> None:
    mapping = load_json(F1_MAPPING_PATH)
    reviewed = {
        row["company_code"] for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    excluded = {
        row["company_code"] for row in mapping.get("excluded_initial_candidates", [])
    }
    assert reviewed | excluded == F1_INITIAL_UNIVERSE
    assert not reviewed & excluded
    assert mapping["concept_only_candidates"] == []
    assert all(
        row["business_materiality"] not in {"concept_only", "reserve_only"}
        for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    )
