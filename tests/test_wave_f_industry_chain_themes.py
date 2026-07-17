from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from stock_research.industry_chain_theme_research import WAVE_F_CHAIN_THEMES
from stock_research.dashboard.theme_research import (
    list_theme_research_claims,
    list_theme_research_nodes,
    list_theme_research_sources,
)
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
F1_TYPED_DEPENDENCY_EDGES = {
    (
        "foundation_model_training_inference_platforms",
        "ai_compute_accelerator_module",
        "depends_on",
    ),
    (
        "foundation_model_training_inference_platforms",
        "ai_compute_rack_scale_system",
        "depends_on",
    ),
    (
        "foundation_model_training_inference_platforms",
        "ai_compute_distributed_storage",
        "depends_on",
    ),
    (
        "foundation_model_training_inference_platforms",
        "ai_compute_high_speed_switching",
        "uses",
    ),
    (
        "foundation_model_training_inference_platforms",
        "ai_compute_cluster_scheduler",
        "uses",
    ),
    (
        "model_toolchain_finetuning_rag",
        "ai_compute_distributed_storage",
        "uses",
    ),
    (
        "model_toolchain_finetuning_rag",
        "ai_compute_cluster_scheduler",
        "uses",
    ),
}
F1_MAPPING_CONTRACTS = {
    "002230.SZ": {
        "node": "foundation_model_training_inference_platforms",
        "source": "f1_002230_ar2025",
        "revenue_relevance": "limited",
        "business_materiality": "meaningful_segment",
        "locators": {
            "product_relationship": "第11页，星辰MaaS训推一体工具与模型精调发布调用管理",
            "revenue_materiality": "第11页，大模型API及MaaS平台服务收入3.85亿元",
            "business_stage": "第11页，开发者规模、日均Tokens与API经济运营",
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
        "node": "industry_solution_delivery_integration",
        "source": "f1_300229_ar2025",
        "revenue_relevance": "material",
        "business_materiality": "meaningful_segment",
        "locators": {
            "product_relationship": "第12页，全栈认知智能产品体系与行业服务",
            "revenue_materiality": "第28页，人工智能软件产品及服务营业收入2.6258亿元",
            "business_stage": "第27页，近2000万元消保智能体项目及多行业交付",
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
            "business_stage": "第16、28页",
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

F1_COMPANY_TRANSMISSION_GAP_CONTRACTS = {
    "002230.SZ": ("MaaS/API平台", "续费率、毛利率与API/MaaS收入结构"),
    "688111.SH": ("WPS AI企业办公", "AI专项收入、付费席位与续费率"),
    "600588.SH": ("YonGPT与用友BIP", "确认收入、续费率与合同转化"),
    "601360.SH": ("纳米AI消费应用", "付费转化、客户留存与AI专项收入"),
    "300229.SZ": ("AI行业交付", "续费、复购、毛利与试用转规模"),
    "300634.SZ": ("Rich AIBox智能体编排", "AI专项收入、付费转化与续费"),
    "300170.SZ": ("得灵AI应用交付", "AI收入金额、分部结构与续费"),
    "300624.SZ": ("万兴天幕与创作Agent", "付费转化、AI专项收入与推理成本"),
    "300339.SZ": ("AI测试与AgentRUNS", "AI专项收入、续费与客户范围"),
    "300378.SZ": ("雅典娜企业智能体", "确认收入、续费率与AI业务毛利"),
}
F1_MATRIX_CALIBRATION_CONTRACTS = {
    "foundation_model_training_inference_platforms": {
        "strength": 4,
        "gap_status": "covered",
        "score_status": "supported",
        "value_bases": ["technology_barrier", "customer_certification"],
        "rationale": "科大讯飞星辰MaaS披露3.85亿元API及MaaS平台服务收入，并有开发者与Token增长；万兴天幕补充模型产品证据，平台节点具备直接收入和采用验证。",
        "next_evidence_needed": "大模型API及MaaS平台服务收入3.85亿元已披露；仍需补充平台收入结构、毛利、续费与留存、用量及单位经济。",
    },
    "model_toolchain_finetuning_rag": {
        "strength": 3,
        "gap_status": "evidence_gap",
        "score_status": "provisional",
        "value_bases": ["integration_control"],
        "rationale": "拓尔思、彩讯和汉得披露RAG、模型训练管理、知识管理及精调工具，但未披露工具链独立收入、付费客户或用量。",
        "next_evidence_needed": "补充模型工具链独立收入、付费客户、调用用量、续费和毛利。",
    },
    "ai_agent_orchestration_workflow": {
        "strength": 3,
        "gap_status": "evidence_gap",
        "score_status": "provisional",
        "value_bases": ["integration_control", "customer_certification"],
        "rationale": "多家公司披露智能体编排产品、调用或项目交付，润和仅支持Agent编排和行业交付；缺少智能体节点独立收入与续费。",
        "next_evidence_needed": "补充智能体平台独立收入、付费客户、续费、任务成功率和单位推理成本。",
    },
    "enterprise_ai_application_software": {
        "strength": 3,
        "gap_status": "evidence_gap",
        "score_status": "provisional",
        "value_bases": ["customer_certification", "integration_control"],
        "rationale": "WPS AI、YonGPT、Rich AIBox、得灵和雅典娜形成企业AI产品与采用或签约证据，但收入多为混合口径或合同额。",
        "next_evidence_needed": "补充企业AI专项确认收入、付费席位、续费、扩容和毛利。",
    },
    "consumer_ai_application_services": {
        "strength": 3,
        "gap_status": "evidence_gap",
        "score_status": "provisional",
        "value_bases": ["customer_certification"],
        "rationale": "纳米AI月访问量和万兴AI调用量证明消费端采用，未证明付费转化、产品留存或AI专项收入。",
        "next_evidence_needed": "补充付费用户、付费转化、产品留存、AI专项收入和推理单位经济。",
    },
    "industry_solution_delivery_integration": {
        "strength": 4,
        "gap_status": "covered",
        "score_status": "supported",
        "value_bases": ["integration_control", "customer_certification"],
        "rationale": "拓尔思披露26,258万元AI软件产品及服务收入和近2,000万元项目，另有多家公司AI合同及行业交付，节点具备直接收入与项目验证。",
        "next_evidence_needed": "补充各公司AI项目确认收入、验收回款、复购、项目毛利和可复制交付占比。",
    },
    "subscription_usage_licensing_monetization": {
        "strength": 4,
        "gap_status": "covered",
        "score_status": "supported",
        "value_bases": ["customer_certification"],
        "rationale": "科大讯飞披露3.85亿元API及MaaS平台服务收入，拓尔思披露AI软件产品及服务收入；合同、调用和订阅线索进一步支持变现节点。",
        "next_evidence_needed": "补充收入构成、ARR或订阅占比、续费、毛利和单位经济。",
    },
    "customer_adoption_renewal_revenue_validation": {
        "strength": 4,
        "gap_status": "evidence_gap",
        "score_status": "supported",
        "value_bases": ["customer_certification"],
        "rationale": "WPS AI月活与Token、360访问量、万兴调用、客户签约项目和两家公司直接AI收入共同验证采用与收入，但AI产品续费仍未证明。",
        "next_evidence_needed": "补充AI产品付费转化、续费或留存、扩容、回款和客户分群收入。",
    },
    "data_security_model_governance_compliance": {
        "strength": 3,
        "gap_status": "evidence_gap",
        "score_status": "provisional",
        "value_bases": ["integration_control"],
        "rationale": "金山办公审计能力、三六零安全大模型治理和鼎捷MACP与数据治理提供AI治理产品线索；润和AI测试智能体不构成治理证据，且缺少治理采用与收入。",
        "next_evidence_needed": "补充独立模型评测、内容安全、审计或合规覆盖、治理客户和AI治理收入。",
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
        "claims": 19,
        "accepted_source_backed_claims": 19,
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


def test_foundation_models_f1_iflytek_uses_three_platform_specific_evidence_roles() -> None:
    theme = load_json(F1_THEME_PATH)
    mapping = load_json(F1_MAPPING_PATH)
    source_pack = load_json(F1_SOURCE_PACK_PATH)
    row = next(
        row for row in mapping["company_mappings"]
        if row["company_code"] == "002230.SZ"
    )
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    items = [evidence[evidence_id] for evidence_id in row["evidence_ids"]]

    assert row["mapped_node_id"] == "foundation_model_training_inference_platforms"
    assert row["revenue_relevance"] == "limited"
    assert all(item["related_node_ids"] == [row["mapped_node_id"]] for item in items)
    assert "星辰MaaS" in items[0]["evidence_summary"]
    assert "模型精调" in items[0]["evidence_summary"]
    assert "大模型API及MaaS平台服务收入3.85亿元" in items[1]["evidence_summary"]
    assert "AI特定产品或服务收入" in items[1]["evidence_summary"]
    assert "开发者" in items[2]["evidence_summary"]
    assert "Tokens" in items[2]["evidence_summary"]
    assert not any(
        term in json.dumps(items, ensure_ascii=False)
        for term in ("PPT创作智能体", "智能批阅机")
    )
    claim = next(row for row in theme["claims"] if row["claim_id"] == "f1_claim_01")
    assert "3.85亿元" in claim["claim_text"]
    assert "开发者" in claim["claim_text"]
    source = next(
        row for row in source_pack["sources"]
        if row["source_id"] == "f1_002230_ar2025"
    )
    assert "3.85亿元" in source["evidence_summary"]


def test_foundation_models_f1_trs_uses_direct_ai_revenue_and_correct_printed_pages() -> None:
    theme = load_json(F1_THEME_PATH)
    mapping = load_json(F1_MAPPING_PATH)
    source_pack = load_json(F1_SOURCE_PACK_PATH)
    row = next(
        row for row in mapping["company_mappings"]
        if row["company_code"] == "300229.SZ"
    )
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    items = [evidence[evidence_id] for evidence_id in row["evidence_ids"]]

    assert row["mapped_node_id"] == "industry_solution_delivery_integration"
    assert row["revenue_relevance"] == "material"
    assert row["business_materiality"] == "meaningful_segment"
    assert all(item["related_node_ids"] == [row["mapped_node_id"]] for item in items)
    assert items[0]["excerpt_locator"] == "第12页，全栈认知智能产品体系与行业服务"
    assert items[1]["excerpt_locator"] == "第28页，人工智能软件产品及服务营业收入2.6258亿元"
    assert items[2]["excerpt_locator"] == "第27页，近2000万元消保智能体项目及多行业交付"
    assert "26,258万元" in items[1]["evidence_summary"]
    assert "AI特定产品或服务收入" in items[1]["evidence_summary"]
    assert "近2,000万元" in items[2]["evidence_summary"]
    claims = {row["claim_id"]: row for row in theme["claims"]}
    assert "26,258万元" in claims["f1_claim_10"]["claim_text"]
    assert "近2,000万元" in claims["f1_claim_10"]["claim_text"]
    assert "试用培育期" in claims["f1_claim_19"]["claim_text"]
    source = next(
        row for row in source_pack["sources"]
        if row["source_id"] == "f1_300229_ar2025"
    )
    assert "第27、28、30页" in source["evidence_locator"]
    assert {"f1_claim_10", "f1_claim_19"} <= set(source["supported_claim_ids"])


def test_foundation_models_f1_has_exact_typed_compute_dependency_edges() -> None:
    catalog = load_industry_catalog()
    nodes = {row["node_id"]: row for row in catalog["nodes"]}
    node_ids = [row["node_id"] for row in catalog["nodes"]]
    assert len(node_ids) == len(set(node_ids))
    assert not F1_L4 & {
        row["node_id"] for row in catalog["nodes"]
        if row["chain_id"] != F1_CHAIN_ID
    }

    cross_chain_edges = {
        (row["source_node_id"], row["target_node_id"], row["relationship_type"])
        for row in catalog["edges"]
        if row["source_node_id"] in F1_L4
        and nodes[row["target_node_id"]]["chain_id"] != F1_CHAIN_ID
    }
    assert cross_chain_edges == F1_TYPED_DEPENDENCY_EDGES
    assert {
        nodes[target]["chain_id"] for _, target, _ in cross_chain_edges
    } == {"ai_compute_infrastructure"}
    accelerator_edge = next(
        row for row in catalog["edges"]
        if row["edge_id"]
        == "foundation_model_platform_depends_on_ai_compute_accelerator_module"
    )
    assert (
        "accelerator-module ownership remains with ai_compute_infrastructure"
        in accelerator_edge["notes"]
    )
    assert (
        "chip ownership remains with ai_logic_compute_chips"
        in accelerator_edge["notes"]
    )
    assert (
        "chip and module ownership remains with ai_compute_infrastructure"
        not in accelerator_edge["notes"]
    )


def test_foundation_models_f1_platform_matrix_gap_uses_disclosed_revenue_boundary() -> None:
    matrix = load_json(F1_MATRIX_PATH)
    platform = next(
        row for row in matrix["node_evidence_matrix"]
        if row["node_id"] == "foundation_model_training_inference_platforms"
    )
    gap = platform["next_evidence_needed"]
    assert "大模型API及MaaS平台服务收入3.85亿元已披露" in gap
    assert "平台收入结构" in gap
    for remaining_gap in ("毛利", "续费", "单位经济"):
        assert remaining_gap in gap
    assert "补充AI专项确认收入" not in gap


def test_foundation_models_f1_runhe_supports_agents_and_delivery_not_governance() -> None:
    theme = load_json(F1_THEME_PATH)
    source_pack = load_json(F1_SOURCE_PACK_PATH)
    matrix = load_json(F1_MATRIX_PATH)
    claims = {row["claim_id"]: row for row in theme["claims"]}
    claim = claims["f1_claim_16"]
    assert claim["affected_theme_nodes"] == [
        "ai_agent_orchestration_workflow",
        "industry_solution_delivery_integration",
    ]
    runhe_source = next(
        row for row in source_pack["sources"]
        if row["source_id"] == "f1_300339_ar2025"
    )
    assert runhe_source["supported_node_ids"] == claim["affected_theme_nodes"]
    governance = next(
        row for row in matrix["node_evidence_matrix"]
        if row["node_id"] == "data_security_model_governance_compliance"
    )
    assert "f1_300339_ar2025" not in governance["accepted_source_ids"]
    assert "f1_claim_16" not in governance["supported_claim_ids"]
    governance_node = next(
        row for row in theme["nodes"]
        if row["node_id"] == "data_security_model_governance_compliance"
    )
    assert "润和软件" not in governance_node["domestic_players"]
    assert "300339.SZ" not in governance_node["related_stock_codes"]
    governance_assessment = next(
        row for row in theme["value_capture_assessments"]
        if row["node_id"] == "data_security_model_governance_compliance"
    )
    assert "f1_claim_16" not in governance_assessment["evidence_ids"]
    served_claims = {
        row["claim_id"]: row
        for row in list_theme_research_claims(
            F1_THEME_ID, read_source="artifact"
        )["items"]
    }
    assert served_claims["f1_claim_16"]["affected_theme_nodes"] == sorted(
        claim["affected_theme_nodes"]
    )


def test_foundation_models_f1_governance_boundary_scans_claims_and_matrix() -> None:
    theme = load_json(F1_THEME_PATH)
    matrix = load_json(F1_MATRIX_PATH)
    governance_node = "data_security_model_governance_compliance"
    governance_claims = {
        row["claim_id"]: row
        for row in theme["claims"]
        if governance_node in row["affected_theme_nodes"]
    }
    assert set(governance_claims) == {"f1_claim_04", "f1_claim_08", "f1_claim_18"}
    governance_terms = ("治理", "安全", "审计", "合规", "评测", "护栏")
    assert all(
        any(term in row["claim_text"] for term in governance_terms)
        for row in governance_claims.values()
    )
    governance_matrix = next(
        row for row in matrix["node_evidence_matrix"]
        if row["node_id"] == governance_node
    )
    assert set(governance_matrix["supported_claim_ids"]) == set(governance_claims)
    assert set(governance_matrix["accepted_source_ids"]) == {
        row["source_id"] for row in governance_claims.values()
    }


def test_foundation_models_f1_hande_retention_is_cross_sell_context_not_ai_renewal() -> None:
    mapping = load_json(F1_MAPPING_PATH)
    source_pack = load_json(F1_SOURCE_PACK_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    hande = next(
        row for row in mapping["company_mappings"]
        if row["company_code"] == "300170.SZ"
    )
    stage = evidence["f1_ev_300170_sz_stage"]
    assert stage["excerpt_locator"] == "第16、28页"
    assert "第16页披露AI智能体已在公司长期企业客户实际场景落地" in stage["evidence_summary"]
    assert "第28页披露的公司整体长期客户留存率超过80%" in stage["evidence_summary"]
    assert "存量客户触达和交叉销售" in stage["evidence_summary"]
    assert "不证明AI产品留存、续费或收入" in stage["evidence_summary"]
    assert stage["related_node_ids"] == ["industry_solution_delivery_integration"]
    assert "头部客户实际场景落地" in hande["relationship_summary"]
    assert "公司整体80%以上长期客户留存" in hande["relationship_summary"]
    assert "交叉销售" in hande["relationship_summary"]
    assert "不能证明AI产品续费" in hande["notes"]
    assert "AI收入金额、分部结构与续费" in hande["notes"]
    retention_items = [
        row for row in mapping["evidence_items"]
        if row["evidence_type"] in {"business_stage", "revenue_materiality"}
        and ("留存率" in row["evidence_summary"] or "80%" in row["evidence_summary"])
    ]
    assert retention_items == [stage]
    assert all(
        "不证明AI产品留存、续费或收入" in row["evidence_summary"]
        for row in retention_items
    )
    source = next(
        row for row in source_pack["sources"]
        if row["source_id"] == "f1_300170_ar2025"
    )
    assert "第16页AI智能体客户场景落地" in source["evidence_summary"]
    assert "第28页公司整体长期客户留存仅作存量触达和交叉销售背景" in source["evidence_summary"]
    assert "不代表AI产品续费、留存或收入" in source["limitations"]


def test_foundation_models_f1_matrix_calibration_is_node_specific() -> None:
    theme = load_json(F1_THEME_PATH)
    matrix = load_json(F1_MATRIX_PATH)
    rows = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}
    theme_nodes = {row["node_id"]: row for row in theme["nodes"]}
    assert set(rows) == set(F1_MATRIX_CALIBRATION_CONTRACTS)
    assert len({contract["rationale"] for contract in F1_MATRIX_CALIBRATION_CONTRACTS.values()}) == 9
    assert {contract["strength"] for contract in F1_MATRIX_CALIBRATION_CONTRACTS.values()} == {3, 4}
    for node_id, contract in F1_MATRIX_CALIBRATION_CONTRACTS.items():
        row = rows[node_id]
        assert row["evidence_strength_after"] == contract["strength"]
        assert theme_nodes[node_id]["evidence_strength"] == contract["strength"]
        assert row["evidence_gap_status"] == contract["gap_status"]
        assert row["value_capture_score_review_status"] == contract["score_status"]
        assert row["bottleneck_score_review_status"] == contract["score_status"]
        assert row["value_bases"] == contract["value_bases"]
        assert row["rationale"] == contract["rationale"]
        assert row["next_evidence_needed"] == contract["next_evidence_needed"]
        assert row["node_review_status"] == "reviewed"
    served_nodes = {
        row["node_id"]: row
        for row in list_theme_research_nodes(
            F1_THEME_ID, read_source="artifact"
        )["items"]
    }
    assert {
        node_id: row["evidence_strength"]
        for node_id, row in served_nodes.items()
    } == {
        node_id: contract["strength"]
        for node_id, contract in F1_MATRIX_CALIBRATION_CONTRACTS.items()
    }


def test_foundation_models_f1_documents_unresolved_skeleton_or_non_generic_owners() -> None:
    catalog = load_industry_catalog()
    nodes_by_chain: dict[str, set[str]] = {}
    for row in catalog["nodes"]:
        nodes_by_chain.setdefault(row["chain_id"], set()).add(row["node_id"])
    assert nodes_by_chain.get("ai_logic_compute_chips", set()) == set()
    assert nodes_by_chain.get("foundational_software_os_database", set()) == set()
    assert nodes_by_chain["industrial_software"] == {
        "industrial_energy_facility_software",
        "electrical_power_monitoring_software",
        "building_management_software",
        "power_distribution_monitoring_software",
        "thermal_control_software",
        "power_fault_prediction_software",
        "compute_energy_scheduling_software",
        "carbon_energy_cost_optimization_software",
    }
    assert nodes_by_chain["cybersecurity_data_infrastructure"] == {
        "transport_data_security_governance_family",
        "transport_data_security_governance",
    }
    assert "generic_cloud_service_platform" not in nodes_by_chain[
        "cloud_data_center_infrastructure"
    ]
    theme_text = json.dumps(load_json(F1_THEME_PATH), ensure_ascii=False)
    for owner in (
        "ai_logic_compute_chips",
        "cloud_data_center_infrastructure",
        "foundational_software_os_database",
        "industrial_software",
        "cybersecurity_data_infrastructure",
    ):
        assert owner in theme_text


def test_foundation_models_f1_company_summaries_have_distinct_transmission_and_gaps() -> None:
    mapping = load_json(F1_MAPPING_PATH)
    rows = {
        row["company_code"]: row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    assert set(rows) == set(F1_COMPANY_TRANSMISSION_GAP_CONTRACTS)
    assert len({row["relationship_summary"] for row in rows.values()}) == 10
    assert len({row["notes"] for row in rows.values()}) == 10
    for company_code, (transmission, gap) in F1_COMPANY_TRANSMISSION_GAP_CONTRACTS.items():
        assert transmission in rows[company_code]["relationship_summary"]
        assert gap in rows[company_code]["notes"]
    three_sixty = rows["601360.SH"]
    assert "月访问量4.5亿" in three_sixty["relationship_summary"]
    assert "采用" in three_sixty["relationship_summary"]
    assert "未证明" in three_sixty["notes"]
    assert three_sixty["revenue_relevance"] == "undisclosed"
    assert three_sixty["business_materiality"] == "emerging_segment"


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
