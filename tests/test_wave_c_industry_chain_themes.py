from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

from stock_research.ai_power_source_pack import validate_theme_evidence_sources
from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.theme_research import list_theme_research_companies
from stock_research.industry_chain_theme_research import verify_deep_theme_coverage
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_company_mapping import load_theme_company_mapping_package
from stock_research.theme_decomposition import CLAIM_FIELDS, load_theme_package
from stock_research.theme_research_priority import load_theme_research_priority_package


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
THEME_ID = "industrial_robots_value_chain_v1"
CHAIN_ID = "industrial_robots"
THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{THEME_ID}.json"
MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "industrial_robots_company_mapping_v1.json"
)
SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "industrial_robots_source_pack_v1.json"
)
MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "industrial_robots_node_evidence_matrix_v1.json"
)
BATTERY_THEME_ID = "power_batteries_battery_materials_value_chain_v1"
BATTERY_CHAIN_ID = "power_batteries_battery_materials"
BATTERY_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{BATTERY_THEME_ID}.json"
BATTERY_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "power_batteries_battery_materials_company_mapping_v1.json"
)
BATTERY_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "power_batteries_battery_materials_source_pack_v1.json"
)
BATTERY_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "power_batteries_battery_materials_node_evidence_matrix_v1.json"
)
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "next_fifteen_industry_chain_themes_v1.json"
)
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("wave_c_theme_verifier", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

NODE_IDS = {
    "multi_joint_robot_bodies",
    "scara_cartesian_parallel_robots",
    "collaborative_specialized_robots",
    "robot_specific_controllers_software",
    "servo_drives_motors_encoders_dependency",
    "precision_reducers_transmission_dependency",
    "vision_force_sensing_safety_dependency",
    "end_effectors_process_packages",
    "workstations_lines_system_integration",
    "industry_applications_lifecycle_services",
}
SOURCE_IDENTITIES = {
    "robot_002747_ar2025": (
        "埃斯顿2025年年度报告",
        "南京埃斯顿自动化股份有限公司",
        "2026-03-31",
        "https://static.cninfo.com.cn/finalpage/2026-03-31/1225059898.PDF",
    ),
    "robot_300124_ar2025": (
        "汇川技术2025年年度报告",
        "深圳市汇川技术股份有限公司",
        "2026-04-28",
        "https://static.cninfo.com.cn/finalpage/2026-04-28/1225208488.PDF",
    ),
    "robot_002527_ar2025": (
        "新时达2025年年度报告",
        "上海新时达电气股份有限公司",
        "2026-04-15",
        "https://static.cninfo.com.cn/finalpage/2026-04-15/1225101828.PDF",
    ),
    "robot_300024_ar2025": (
        "机器人2025年年度报告",
        "沈阳新松机器人自动化股份有限公司",
        "2026-04-24",
        "https://static.cninfo.com.cn/finalpage/2026-04-24/1225170932.PDF",
    ),
    "robot_300607_ar2025": (
        "拓斯达2025年年度报告",
        "广东拓斯达科技股份有限公司",
        "2026-03-31",
        "https://static.cninfo.com.cn/finalpage/2026-03-31/1225058061.PDF",
    ),
    "robot_688255_ar2025": (
        "凯尔达2025年年度报告",
        "杭州凯尔达焊接机器人股份有限公司",
        "2026-04-23",
        "https://static.cninfo.com.cn/finalpage/2026-04-23/1225148948.PDF",
    ),
    "robot_688090_ar2025": (
        "瑞松科技2025年年度报告",
        "广州瑞松智能科技股份有限公司",
        "2026-04-28",
        "https://static.cninfo.com.cn/finalpage/2026-04-28/1225221109.PDF",
    ),
    "robot_688165_ar2025": (
        "埃夫特2025年年度报告",
        "埃夫特智能机器人股份有限公司",
        "2026-04-15",
        "https://static.cninfo.com.cn/finalpage/2026-04-15/1225101939.PDF",
    ),
    "robot_688017_ar2025": (
        "绿的谐波2025年年度报告",
        "苏州绿的谐波传动科技股份有限公司",
        "2026-04-23",
        "https://static.cninfo.com.cn/finalpage/2026-04-23/1225149955.PDF",
    ),
    "robot_688686_ar2025": (
        "奥普特2025年年度报告",
        "广东奥普特科技股份有限公司",
        "2026-04-03",
        "https://static.cninfo.com.cn/finalpage/2026-04-03/1225078058.PDF",
    ),
}
BATTERY_NODE_IDS = {
    "resource_extraction_refining",
    "precursor_cathode_materials",
    "anode_materials",
    "separator_coating",
    "electrolyte_lithium_salts",
    "copper_aluminum_foil",
    "precision_structural_components",
    "battery_cells_management_systems",
    "battery_management_system_platforms",
    "recycling_second_life",
    "sodium_ion_solid_state_validation",
}
BATTERY_SOURCE_IDENTITIES = {
    "battery_300750_ar2025": (
        "宁德时代2025年年度报告",
        "宁德时代新能源科技股份有限公司",
        "2026-03-10",
        "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
    ),
    "battery_300014_ar2025": (
        "亿纬锂能2025年年度报告",
        "惠州亿纬锂能股份有限公司",
        "2026-03-28",
        "https://static.cninfo.com.cn/finalpage/2026-03-28/1225045391.PDF",
    ),
    "battery_002074_ar2025": (
        "国轩高科2025年年度报告",
        "国轩高科股份有限公司",
        "2026-04-29",
        "https://static.cninfo.com.cn/finalpage/2026-04-29/1225254220.pdf",
    ),
    "battery_300207_ar2025": (
        "欣旺达2025年年度报告",
        "欣旺达电子股份有限公司",
        "2026-04-24",
        "https://static.cninfo.com.cn/finalpage/2026-04-24/1225160491.PDF",
    ),
    "battery_603799_ar2025": (
        "华友钴业2025年年度报告",
        "浙江华友钴业股份有限公司",
        "2026-04-08",
        "https://static.cninfo.com.cn/finalpage/2026-04-08/1225083106.PDF",
    ),
    "battery_300919_ar2025": (
        "中伟股份2025年年度报告",
        "中伟新材料股份有限公司",
        "2026-03-31",
        "https://static.cninfo.com.cn/finalpage/2026-03-31/1225054811.PDF",
    ),
    "battery_688005_ar2025": (
        "容百科技2025年年度报告",
        "宁波容百新能源科技股份有限公司",
        "2026-04-11",
        "https://static.cninfo.com.cn/finalpage/2026-04-11/1225095564.PDF",
    ),
    "battery_603659_ar2025": (
        "璞泰来2025年年度报告",
        "上海璞泰来新能源科技集团股份有限公司",
        "2026-03-06",
        "https://static.cninfo.com.cn/finalpage/2026-03-06/1224998510.PDF",
    ),
    "battery_002812_ar2025": (
        "恩捷股份2025年年度报告",
        "云南恩捷新材料（集团）股份有限公司",
        "2026-04-23",
        "https://static.cninfo.com.cn/finalpage/2026-04-23/1225148267.PDF",
    ),
    "battery_002709_ar2025": (
        "天赐材料2025年年度报告",
        "广州天赐高新材料股份有限公司",
        "2026-03-10",
        "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002090.PDF",
    ),
    "battery_603876_ar2025": (
        "鼎胜新材2025年年度报告",
        "江苏鼎胜新能源材料股份有限公司",
        "2026-04-30",
        "https://static.cninfo.com.cn/finalpage/2026-04-30/1225255150.PDF",
    ),
    "battery_301217_ar2025": (
        "铜冠铜箔2025年年度报告",
        "安徽铜冠铜箔集团股份有限公司",
        "2026-04-18",
        "https://static.cninfo.com.cn/finalpage/2026-04-18/1225118023.PDF",
    ),
    "battery_002850_ar2025": (
        "科达利2025年年度报告",
        "深圳市科达利实业股份有限公司",
        "2026-03-28",
        "https://static.cninfo.com.cn/finalpage/2026-03-28/1225041059.PDF",
    ),
    "battery_002340_ar2025": (
        "格林美2025年年度报告",
        "格林美股份有限公司",
        "2026-04-22",
        "https://static.cninfo.com.cn/finalpage/2026-04-22/1225142250.PDF",
    ),
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _implemented_wave_chain_ids(wave: str) -> set[str]:
    manifest = _read_json(MANIFEST_PATH)
    return {
        chain_id
        for chain_id in manifest["waves"][wave]
        if all(
            (REPOSITORY_ROOT / artifact_path).is_file()
            for artifact_path in manifest["themes"][chain_id]["artifacts"].values()
        )
    }


def _assert_wave_progress_matches_manifest(report: dict, wave: str) -> None:
    manifest = _read_json(MANIFEST_PATH)
    implemented_chain_ids = _implemented_wave_chain_ids(wave)
    wave_chain_ids = manifest["waves"][wave]
    wave_result = report["wave_results"][wave]
    ready_chain_ids = {
        row["chain_id"] for row in report["theme_results"] if row["ready"]
    }

    assert wave_result["ready_theme_count"] == len(implemented_chain_ids)
    assert wave_result["not_ready_theme_count"] == (
        len(wave_chain_ids) - len(implemented_chain_ids)
    )
    assert wave_result["ready"] is (
        len(implemented_chain_ids) == len(wave_chain_ids)
    )
    assert ready_chain_ids == implemented_chain_ids


def _assert_bidirectional_source_and_matrix_links(
    *,
    theme_path: Path,
    source_pack_path: Path,
    matrix_path: Path,
    node_ids: set[str],
    require_accepted_source: bool,
) -> None:
    theme = _read_json(theme_path)
    source_pack = _read_json(source_pack_path)
    matrix = _read_json(matrix_path)
    accepted_source_ids = {
        row["source_id"]
        for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    source_by_id = {row["source_id"]: row for row in source_pack["sources"]}
    claim_by_id = {row["claim_id"]: row for row in theme["claims"]}
    matrix_by_node = {
        row["node_id"]: row for row in matrix["node_evidence_matrix"]
    }

    assert {
        source["source_id"]: set(source["supported_claim_ids"])
        for source in source_pack["sources"]
    } == {
        source["source_id"]: {
            claim["claim_id"]
            for claim in theme["claims"]
            if source["source_id"]
            in {claim["source_id"], *claim["supporting_source_ids"]}
        }
        for source in source_pack["sources"]
    }
    assert set(matrix_by_node) == node_ids
    assert len(matrix_by_node) == len(node_ids)
    for node_id, row in matrix_by_node.items():
        expected_claim_ids = {
            claim["claim_id"]
            for claim in theme["claims"]
            if node_id in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == expected_claim_ids
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        if require_accepted_source:
            assert row["accepted_source_ids"]
        else:
            assert row["accepted_source_ids"] or row["evidence_gap_status"] == "evidence_gap"
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert node_id in source["supported_node_ids"]
            assert expected_claim_ids & set(source["supported_claim_ids"])
        for claim_id in expected_claim_ids:
            claim = claim_by_id[claim_id]
            assert set(row["accepted_source_ids"]) & {
                claim["source_id"],
                *claim["supporting_source_ids"],
            }
    for source in source_pack["sources"]:
        for claim_id in source["supported_claim_ids"]:
            assert set(source["supported_node_ids"]) & set(
                claim_by_id[claim_id]["affected_theme_nodes"]
            )
        for node_id in source["supported_node_ids"]:
            assert node_id in matrix_by_node
            assert set(source["supported_claim_ids"]) & set(
                matrix_by_node[node_id]["supported_claim_ids"]
            )


def test_industrial_robots_artifacts_load_and_first_wave_c_row_is_ready():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()

    assert THEME_ID in {row["theme_id"] for row in theme_package["themes"]}
    assert THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_c")
    rows = {row["chain_id"]: row for row in report["theme_results"]}

    assert rows[CHAIN_ID]["ready"] is True
    assert all(rows[CHAIN_ID]["checks"].values())
    _assert_wave_progress_matches_manifest(report, "wave_c")


def test_industrial_robots_evidence_mapping_and_source_identity_are_exact():
    _assert_bidirectional_source_and_matrix_links(
        theme_path=THEME_PATH,
        source_pack_path=SOURCE_PACK_PATH,
        matrix_path=MATRIX_PATH,
        node_ids=NODE_IDS,
        require_accepted_source=False,
    )
    theme = _read_json(THEME_PATH)
    mapping = _read_json(MAPPING_PATH)
    source_pack = _read_json(SOURCE_PACK_PATH)
    accepted = validate_theme_evidence_sources(source_pack["sources"], NODE_IDS)
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    canonical_sources = {row["source_id"]: row for row in theme["sources"]}
    mapping_sources = {row["source_id"]: row for row in mapping["sources"]}
    pack_sources = {row["source_id"]: row for row in source_pack["sources"]}

    assert len([row for row in accepted.values() if row["review_status"] == "accepted"]) == 10
    assert all(
        row["source_type"] == "company_filing" and row["reliability_level"] == "S0"
        for row in source_pack["sources"]
    )
    assert {row["node_id"] for row in theme["nodes"]} == NODE_IDS
    assert len(theme["nodes"]) == 10
    assert len(theme["claims"]) == 14
    assert all(set(row) >= CLAIM_FIELDS for row in theme["claims"])
    assert len(reviewed_mappings) == 10
    assert len({row["company_code"] for row in reviewed_mappings}) == 10
    assert set(canonical_sources) == set(SOURCE_IDENTITIES)
    assert set(mapping_sources) == set(SOURCE_IDENTITIES)
    assert set(pack_sources) == set(SOURCE_IDENTITIES)
    for source_id, (title, publisher, publish_date, url) in SOURCE_IDENTITIES.items():
        expected = {
            "title": title,
            "publisher": publisher,
            "publish_date": publish_date,
            "url_or_ref": url,
        }
        assert {
            field: canonical_sources[source_id][field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        } == expected
        assert {
            field: mapping_sources[source_id][field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        } == expected
        assert {
            "title": pack_sources[source_id]["title"],
            "publisher": pack_sources[source_id]["publisher"],
            "publish_date": pack_sources[source_id]["publish_date"],
            "url_or_ref": pack_sources[source_id]["url"],
        } == expected
    assert set(pack_sources["robot_688017_ar2025"]["supported_node_ids"]) == {
        "precision_reducers_transmission_dependency"
    }
    assert set(pack_sources["robot_688686_ar2025"]["supported_node_ids"]) == {
        "vision_force_sensing_safety_dependency"
    }
    matrix_by_node = {
        row["node_id"]: row
        for row in _read_json(MATRIX_PATH)["node_evidence_matrix"]
    }
    assert "robot_688017_ar2025" not in matrix_by_node["multi_joint_robot_bodies"][
        "accepted_source_ids"
    ]
    assert "robot_688686_ar2025" not in matrix_by_node[
        "industry_applications_lifecycle_services"
    ]["accepted_source_ids"]


def test_industrial_robots_company_beneficiary_tiers_follow_classifier_exactly():
    expected = {
        "002747.SZ": ("core_beneficiary", "core_business", "material"),
        "002527.SZ": ("core_beneficiary", "meaningful_segment", "material"),
        "300024.SZ": ("core_beneficiary", "meaningful_segment", "material"),
        "300607.SZ": ("core_beneficiary", "meaningful_segment", "material"),
        "688255.SH": ("core_beneficiary", "core_business", "material"),
        "688165.SH": ("core_beneficiary", "core_business", "material"),
        "688090.SH": ("core_beneficiary", "core_business", "material"),
        "300124.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "688017.SH": ("indirect_beneficiary", "core_business", "material"),
        "688686.SH": ("indirect_beneficiary", "emerging_segment", "limited"),
    }
    read_model = list_theme_research_companies(THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        f"/api/research/theme-decomposition/themes/{THEME_ID}/companies"
    )

    assert response.status_code == 200
    for payload in (read_model, response.json()):
        assert payload["total"] == len(expected)
        assert {
            row["company_code"]: (
                row["beneficiary_tier"],
                row["business_materiality"],
                row["revenue_relevance"],
            )
            for row in payload["items"]
        } == expected


def test_industrial_robots_profile_catalog_cross_chain_ownership_and_gaps_are_ready():
    theme = _read_json(THEME_PATH)
    mapping = _read_json(MAPPING_PATH)
    matrix = _read_json(MATRIX_PATH)
    profile = theme["research_profile"]
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    catalog = load_industry_catalog()
    link = next(row for row in catalog["theme_links"] if row["theme_id"] == THEME_ID)
    matrix_by_node = {
        row["node_id"]: row for row in matrix["node_evidence_matrix"]
    }
    mapping_by_company = {
        row["company_code"]: row for row in mapping["company_mappings"]
    }

    assert profile["catalog_chain_id"] == CHAIN_ID
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert link["node_links"] == []
    assert set(link["unmapped_theme_node_ids"]) == NODE_IDS
    assert "L2 skeleton" in link["notes"]
    assert "不重复所有权" in link["notes"]
    for node_id in {
        "scara_cartesian_parallel_robots",
        "vision_force_sensing_safety_dependency",
        "end_effectors_process_packages",
    }:
        assert matrix_by_node[node_id]["node_review_status"] == "reviewed"
        assert matrix_by_node[node_id]["evidence_gap_status"] == "evidence_gap"
        assert matrix_by_node[node_id]["accepted_source_ids"]
        assert matrix_by_node[node_id]["supported_claim_ids"]
        assert matrix_by_node[node_id]["next_evidence_needed"]
    assert mapping_by_company["688017.SH"]["mapped_node_id"] == (
        "precision_reducers_transmission_dependency"
    )
    assert mapping_by_company["688017.SH"]["bottleneck_relevance"] == "adjacent"
    assert mapping_by_company["688686.SH"]["mapped_node_id"] == (
        "vision_force_sensing_safety_dependency"
    )
    assert mapping_by_company["688686.SH"]["bottleneck_relevance"] == "adjacent"
    assert "跨链" in mapping_by_company["688017.SH"]["notes"]
    assert "跨链" in mapping_by_company["688686.SH"]["notes"]
    result = verify_deep_theme_coverage(
        THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_industrial_robots_revenue_and_scope_boundaries_block_over_attribution():
    theme = _read_json(THEME_PATH)
    mapping = _read_json(MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    claim_text = " ".join(row["claim_text"] for row in theme["claims"])

    assert "39.97亿元" in evidence["robot_ev_002747_revenue"]["evidence_summary"]
    assert evidence["robot_ev_002747_revenue"]["excerpt_locator"] == "第16页"
    assert "本体+系统" in evidence["robot_ev_002747_revenue"]["evidence_summary"]
    assert "不可全算本体" in evidence["robot_ev_002747_revenue"]["evidence_summary"]
    assert "新兴产业" in evidence["robot_ev_300124_revenue"]["evidence_summary"]
    assert evidence["robot_ev_300124_product"]["excerpt_locator"] == "第26-27页"
    assert evidence["robot_ev_300124_revenue"]["excerpt_locator"] == "第29页"
    assert "含其他" in evidence["robot_ev_300124_revenue"]["evidence_summary"]
    assert "3亿元" in evidence["robot_ev_300607_revenue"]["evidence_summary"]
    assert "3.85亿元" in evidence["robot_ev_300607_revenue"]["evidence_summary"]
    assert "外购整机63%" in evidence["robot_ev_688255_risk"]["evidence_summary"]
    assert "6.39亿元" in evidence["robot_ev_688165_revenue"]["evidence_summary"]
    assert evidence["robot_ev_688165_revenue"]["excerpt_locator"] == "第65页"
    assert "-15.32%" in evidence["robot_ev_688165_risk"]["evidence_summary"]
    assert "2330万元" in evidence["robot_ev_688686_revenue"]["evidence_summary"]
    assert evidence["robot_ev_688686_revenue"]["excerpt_locator"] == "第21页"
    assert "不是机器视觉总收入" in evidence["robot_ev_688686_revenue"]["evidence_summary"]
    assert "机器人口径" in claim_text
    assert "并联" in claim_text and "独立收入" in claim_text
    assert "安全硬件" in claim_text and "末端执行器" in claim_text
    assert "运维软件" in claim_text and "收入缺口" in claim_text
    assert "协作" in claim_text and "早期" in claim_text
    assert "具身" in claim_text and "力传感" in claim_text
    assert "不重复所有权" in claim_text


def test_power_batteries_battery_materials_four_artifacts_exist_before_validation():
    assert BATTERY_THEME_PATH.is_file()
    assert BATTERY_MAPPING_PATH.is_file()
    assert BATTERY_SOURCE_PACK_PATH.is_file()
    assert BATTERY_MATRIX_PATH.is_file()


def test_power_batteries_artifacts_load_and_second_wave_c_row_is_ready():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()

    assert BATTERY_THEME_ID in {row["theme_id"] for row in theme_package["themes"]}
    assert BATTERY_THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert BATTERY_THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_c")
    rows = {row["chain_id"]: row for row in report["theme_results"]}

    assert rows[BATTERY_CHAIN_ID]["ready"] is True
    assert all(rows[BATTERY_CHAIN_ID]["checks"].values())
    assert rows[BATTERY_CHAIN_ID]["counts"]["reviewed_mappings"] == 14
    _assert_wave_progress_matches_manifest(report, "wave_c")


def test_power_batteries_evidence_mapping_and_source_identity_are_exact():
    _assert_bidirectional_source_and_matrix_links(
        theme_path=BATTERY_THEME_PATH,
        source_pack_path=BATTERY_SOURCE_PACK_PATH,
        matrix_path=BATTERY_MATRIX_PATH,
        node_ids=BATTERY_NODE_IDS,
        require_accepted_source=True,
    )
    theme = _read_json(BATTERY_THEME_PATH)
    mapping = _read_json(BATTERY_MAPPING_PATH)
    source_pack = _read_json(BATTERY_SOURCE_PACK_PATH)
    accepted = validate_theme_evidence_sources(
        source_pack["sources"], BATTERY_NODE_IDS
    )
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    canonical_sources = {row["source_id"]: row for row in theme["sources"]}
    mapping_sources = {row["source_id"]: row for row in mapping["sources"]}
    pack_sources = {row["source_id"]: row for row in source_pack["sources"]}

    assert len([row for row in accepted.values() if row["review_status"] == "accepted"]) == 14
    assert all(
        row["source_type"] == "company_filing" and row["reliability_level"] == "S0"
        for row in source_pack["sources"]
    )
    assert {row["node_id"] for row in theme["nodes"]} == BATTERY_NODE_IDS
    assert len(theme["nodes"]) == 11
    assert len(theme["claims"]) == 14
    assert all(set(row) >= CLAIM_FIELDS for row in theme["claims"])
    assert len(reviewed_mappings) == 14
    assert len({row["company_code"] for row in reviewed_mappings}) == 14
    assert set(canonical_sources) == set(BATTERY_SOURCE_IDENTITIES)
    assert set(mapping_sources) == set(BATTERY_SOURCE_IDENTITIES)
    assert set(pack_sources) == set(BATTERY_SOURCE_IDENTITIES)
    for source_id, (title, publisher, publish_date, url) in BATTERY_SOURCE_IDENTITIES.items():
        expected = {
            "title": title,
            "publisher": publisher,
            "publish_date": publish_date,
            "url_or_ref": url,
        }
        assert {
            field: canonical_sources[source_id][field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        } == expected
        assert {
            field: mapping_sources[source_id][field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        } == expected
        assert {
            "title": pack_sources[source_id]["title"],
            "publisher": pack_sources[source_id]["publisher"],
            "publish_date": pack_sources[source_id]["publish_date"],
            "url_or_ref": pack_sources[source_id]["url"],
        } == expected


def test_power_batteries_company_beneficiary_tiers_follow_classifier_exactly():
    expected = {
        "300750.SZ": ("core_beneficiary", "core_business", "material"),
        "300014.SZ": ("core_beneficiary", "meaningful_segment", "material"),
        "002074.SZ": ("core_beneficiary", "core_business", "material"),
        "300207.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "603799.SH": ("core_beneficiary", "core_business", "material"),
        "300919.SZ": ("core_beneficiary", "core_business", "material"),
        "688005.SH": ("core_beneficiary", "core_business", "material"),
        "603659.SH": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "002812.SZ": ("elastic_beneficiary", "core_business", "undisclosed"),
        "002709.SZ": ("elastic_beneficiary", "core_business", "undisclosed"),
        "603876.SH": ("elastic_beneficiary", "core_business", "undisclosed"),
        "301217.SZ": ("core_beneficiary", "core_business", "material"),
        "002850.SZ": ("core_beneficiary", "core_business", "material"),
        "002340.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
    }
    payload = list_theme_research_companies(BATTERY_THEME_ID)

    assert payload["total"] == len(expected)
    assert {
        row["company_code"]: (
            row["beneficiary_tier"],
            row["business_materiality"],
            row["revenue_relevance"],
        )
        for row in payload["items"]
    } == expected


def test_power_batteries_accepted_eve_source_has_mapping_evidence_and_reviewed_mapping():
    source_pack = _read_json(BATTERY_SOURCE_PACK_PATH)
    matrix = _read_json(BATTERY_MATRIX_PATH)
    mapping = _read_json(BATTERY_MAPPING_PATH)
    source = next(
        row
        for row in source_pack["sources"]
        if row["source_id"] == "battery_300014_ar2025"
    )
    consuming_nodes = {
        row["node_id"]
        for row in matrix["node_evidence_matrix"]
        if source["source_id"] in row["accepted_source_ids"]
    }
    mapping_row = next(
        row
        for row in mapping["company_mappings"]
        if row["company_code"] == "300014.SZ"
    )
    evidence = [
        row
        for row in mapping["evidence_items"]
        if row["evidence_id"] in mapping_row["evidence_ids"]
    ]

    assert source["review_status"] == "accepted"
    assert source["reliability_level"] == "S0"
    assert consuming_nodes == {
        "battery_cells_management_systems",
        "battery_management_system_platforms",
        "sodium_ion_solid_state_validation",
    }
    assert mapping_row["mapped_node_id"] == "battery_cells_management_systems"
    assert mapping_row["review_status"] == "reviewed"
    assert mapping_row["business_materiality"] == "meaningful_segment"
    assert mapping_row["revenue_relevance"] == "material"
    assert {row["evidence_type"] for row in evidence} >= {
        "product_relationship",
        "revenue_materiality",
    }
    assert {row["source_id"] for row in evidence} == {source["source_id"]}
    assert all(row["related_company_codes"] == ["300014.SZ"] for row in evidence)


def test_power_batteries_profile_catalog_boundaries_and_validation_gaps_are_ready():
    theme = _read_json(BATTERY_THEME_PATH)
    matrix = _read_json(BATTERY_MATRIX_PATH)
    profile = theme["research_profile"]
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    catalog = load_industry_catalog()
    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == BATTERY_THEME_ID
    )
    matrix_by_node = {
        row["node_id"]: row for row in matrix["node_evidence_matrix"]
    }

    assert profile["catalog_chain_id"] == BATTERY_CHAIN_ID
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert "14条reviewed映射" in profile["evidence_gap_summary"]
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert set(profile["readable_section_claim_ids"]) == {
        "conclusion",
        "value_chain",
        "profit_pool_barriers",
        "catalysts_validation_risks",
        "beneficiary_companies",
        "source_evidence",
        "evidence_gaps",
    }
    assert {
        section: set(section_claim_ids)
        for section, section_claim_ids in profile["readable_section_claim_ids"].items()
    } == {
        "conclusion": {
            "battery_claim_04_cathode_profit_risk",
            "battery_claim_09_copper_foil_margin_risk",
            "battery_claim_11_cell_scale_margin",
            "battery_claim_14_sodium_solid_validation",
        },
        "value_chain": {
            "battery_claim_01_value_flow",
            "battery_claim_02_resource_cycle",
            "battery_claim_03_precursor_cathode_routes",
            "battery_claim_08_foil_scope_split",
            "battery_claim_10_structural_components_pool",
            "battery_claim_12_bms_pack_disclosure_gap",
            "battery_claim_13_recycling_economics",
        },
        "profit_pool_barriers": {
            "battery_claim_02_resource_cycle",
            "battery_claim_03_precursor_cathode_routes",
            "battery_claim_04_cathode_profit_risk",
            "battery_claim_05_anode_scope_boundary",
            "battery_claim_06_separator_scope_boundary",
            "battery_claim_07_electrolyte_scope_boundary",
            "battery_claim_09_copper_foil_margin_risk",
            "battery_claim_10_structural_components_pool",
            "battery_claim_11_cell_scale_margin",
            "battery_claim_12_bms_pack_disclosure_gap",
            "battery_claim_13_recycling_economics",
        },
        "catalysts_validation_risks": {
            "battery_claim_02_resource_cycle",
            "battery_claim_04_cathode_profit_risk",
            "battery_claim_09_copper_foil_margin_risk",
            "battery_claim_11_cell_scale_margin",
            "battery_claim_13_recycling_economics",
            "battery_claim_14_sodium_solid_validation",
        },
        "beneficiary_companies": {
            "battery_claim_02_resource_cycle",
            "battery_claim_03_precursor_cathode_routes",
            "battery_claim_04_cathode_profit_risk",
            "battery_claim_05_anode_scope_boundary",
            "battery_claim_06_separator_scope_boundary",
            "battery_claim_07_electrolyte_scope_boundary",
            "battery_claim_09_copper_foil_margin_risk",
            "battery_claim_10_structural_components_pool",
            "battery_claim_11_cell_scale_margin",
            "battery_claim_12_bms_pack_disclosure_gap",
            "battery_claim_13_recycling_economics",
        },
        "source_evidence": claim_ids,
        "evidence_gaps": {
            "battery_claim_05_anode_scope_boundary",
            "battery_claim_06_separator_scope_boundary",
            "battery_claim_07_electrolyte_scope_boundary",
            "battery_claim_08_foil_scope_split",
            "battery_claim_12_bms_pack_disclosure_gap",
            "battery_claim_13_recycling_economics",
            "battery_claim_14_sodium_solid_validation",
        },
    }
    assert link["node_links"] == [
        {
            "theme_node_id": "battery_cells_management_systems",
            "catalog_node_id": "battery_cell_and_management_systems",
        },
        {
            "theme_node_id": "battery_management_system_platforms",
            "catalog_node_id": "battery_management_system_platform",
        },
    ]
    assert set(link["unmapped_theme_node_ids"]) == BATTERY_NODE_IDS - {
        "battery_cells_management_systems",
        "battery_management_system_platforms",
    }
    assert "高比能" in link["notes"] and "不强连" in link["notes"]
    theme_node_by_id = {row["node_id"]: row for row in theme["nodes"]}
    catalog_node_by_id = {row["node_id"]: row for row in catalog["nodes"]}
    theme_family = theme_node_by_id["battery_cells_management_systems"]
    theme_bms = theme_node_by_id["battery_management_system_platforms"]
    catalog_family = catalog_node_by_id["battery_cell_and_management_systems"]
    catalog_bms = catalog_node_by_id["battery_management_system_platform"]

    assert theme_family["parent_node_id"] == ""
    assert catalog_family["parent_node_id"] is None
    assert catalog_family["level"] == "L3"
    assert "动力电芯" in theme_family["node_name"]
    assert "电池管理系统" in theme_family["node_name"]
    assert "通用动力电芯产品" in theme_family["description"]
    assert "电池管理平台" in theme_family["description"]
    assert "generic power-battery cell products and BMS platforms" in catalog_family[
        "description"
    ]
    assert theme_bms["parent_node_id"] == theme_family["node_id"]
    assert catalog_bms["parent_node_id"] == catalog_family["node_id"]
    assert catalog_bms["level"] == "L4"
    for theme_term in ("状态估计", "均衡", "保护", "充电", "诊断", "接口"):
        assert theme_term in theme_bms["description"]
    for catalog_term in (
        "state estimation",
        "balancing",
        "protection",
        "charging",
        "diagnostics",
        "system interfaces",
    ):
        assert catalog_term in catalog_bms["description"]
    for equivalence_term in (
        "主题父节点范围=通用动力电芯产品+BMS平台",
        "目录L3范围=generic power-battery cell products and BMS platforms",
        "主题BMS子节点范围=状态估计、均衡、保护、充电、诊断与系统接口",
        "目录L4范围=state estimation, balancing, protection, charging, diagnostics and system interfaces",
        "主题父子层级与目录L3/L4父子层级一致",
        "排除Pack集成收入",
        "排除高比能电芯窄节点",
    ):
        assert equivalence_term in link["notes"]
    for node_id in {
        "anode_materials",
        "recycling_second_life",
        "sodium_ion_solid_state_validation",
    }:
        assert matrix_by_node[node_id]["evidence_gap_status"] == "evidence_gap"
        assert matrix_by_node[node_id]["next_evidence_needed"]
    claim_text = " ".join(row["claim_text"] for row in theme["claims"])
    readable_profile = " ".join(
        [
            profile["industry_stage"],
            profile["central_conflict"],
            profile["investment_summary"],
            profile["value_flow_summary"],
            profile["profit_pool_summary"],
            *profile["validation_signals"],
            profile["evidence_gap_summary"],
        ]
    )
    for keyword in (
        "价值流",
        "利润池",
        "资源",
        "正极",
        "负极",
        "隔膜",
        "电解液",
        "铜箔",
        "结构件",
        "动力电芯",
        "BMS",
        "回收",
        "钠离子",
        "固态",
        "验证期",
    ):
        assert keyword in claim_text
        assert keyword in readable_profile
    result = verify_deep_theme_coverage(
        BATTERY_THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_power_batteries_revenue_margin_and_scope_boundaries_block_over_attribution():
    theme = _read_json(BATTERY_THEME_PATH)
    mapping = _read_json(BATTERY_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    claim_text = " ".join(row["claim_text"] for row in theme["claims"])

    assert evidence["battery_ev_300750_revenue"]["excerpt_locator"] == "PDF第24-25页，第三节营业收入构成及分产品毛利率表"
    assert "3165.06亿元" in evidence["battery_ev_300750_revenue"]["evidence_summary"]
    assert "23.84%" in evidence["battery_ev_300750_revenue"]["evidence_summary"]
    assert evidence["battery_ev_300207_bms"]["excerpt_locator"] == "PDF第5、12-13页，释义、核心竞争力与电动汽车类电池业务"
    assert "未披露BMS/Pack独立收入" in evidence["battery_ev_300207_revenue"]["evidence_summary"]
    assert "-1.87亿元" in evidence["battery_ev_688005_risk"]["evidence_summary"]
    assert "6.54%" in evidence["battery_ev_688005_revenue"]["evidence_summary"]
    assert "117.93亿元" in evidence["battery_ev_603659_revenue"]["evidence_summary"]
    assert "不是纯负极收入" in evidence["battery_ev_603659_revenue"]["evidence_summary"]
    assert "122.06亿元" in evidence["battery_ev_002812_revenue"]["evidence_summary"]
    assert "含BOPP" in evidence["battery_ev_002812_revenue"]["evidence_summary"]
    assert "150.51亿元" in evidence["battery_ev_002709_revenue"]["evidence_summary"]
    assert "不是纯电解液收入" in evidence["battery_ev_002709_revenue"]["evidence_summary"]
    assert "221.81亿元" in evidence["battery_ev_603876_revenue"]["evidence_summary"]
    assert "未拆电池铝箔" in evidence["battery_ev_603876_revenue"]["evidence_summary"]
    assert evidence["battery_ev_301217_revenue"]["excerpt_locator"] == "PDF第20页，第三节分产品收入成本毛利率表"
    assert "0.19%" in evidence["battery_ev_301217_revenue"]["evidence_summary"]
    assert "147.05亿元" in evidence["battery_ev_002850_revenue"]["evidence_summary"]
    assert "动力、储能与消费" in evidence["battery_ev_002850_revenue"]["evidence_summary"]
    assert "12.52亿元" in evidence["battery_ev_002340_revenue"]["evidence_summary"]
    assert "不是循环业务总收入" in evidence["battery_ev_002340_revenue"]["evidence_summary"]
    assert "中试" in claim_text and "量产线" in claim_text
    assert "验证期" in claim_text and "成熟规模收入" in claim_text


def test_power_batteries_product_relationship_and_revenue_boundary_locators_are_distinct():
    mapping = _read_json(BATTERY_MAPPING_PATH)
    source_pack = _read_json(BATTERY_SOURCE_PACK_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    sources = {row["source_id"]: row for row in source_pack["sources"]}

    expected = {
        "battery_002709_ar2025": {
            "product_id": "battery_ev_002709_product",
            "product_locator": "PDF第11-13、17页，第三节主要业务、产品体系与核心技术",
            "revenue_id": "battery_ev_002709_revenue",
            "revenue_locator": "PDF第19页，第三节分产品收入成本毛利率及产销量表",
            "source_locator": "产品体系与核心技术见PDF第11-13、17页；宽口径收入、毛利率与产销量见PDF第19页",
        },
        "battery_603876_ar2025": {
            "product_id": "battery_ev_603876_product",
            "product_locator": "PDF第10-15页，第三节主要业务、客户结构与动力电池铝箔技术",
            "revenue_id": "battery_ev_603876_revenue",
            "revenue_locator": "PDF第16页，第三节主营业务分产品收入成本毛利率表",
            "source_locator": "动力电池铝箔产品、客户与技术见PDF第10-15页；全部铝箔宽口径收入与毛利率见PDF第16页",
        },
    }
    for source_id, locator_contract in expected.items():
        product = evidence[locator_contract["product_id"]]
        revenue = evidence[locator_contract["revenue_id"]]
        assert product["source_id"] == source_id
        assert revenue["source_id"] == source_id
        assert product["evidence_type"] == "product_relationship"
        assert revenue["evidence_type"] == "revenue_materiality"
        assert product["excerpt_locator"] == locator_contract["product_locator"]
        assert revenue["excerpt_locator"] == locator_contract["revenue_locator"]
        assert product["excerpt_locator"] != revenue["excerpt_locator"]
        assert sources[source_id]["evidence_locator"] == locator_contract[
            "source_locator"
        ]
