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


def _assert_bidirectional_source_and_matrix_links() -> None:
    theme = _read_json(THEME_PATH)
    source_pack = _read_json(SOURCE_PACK_PATH)
    matrix = _read_json(MATRIX_PATH)
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
    assert set(matrix_by_node) == NODE_IDS
    assert len(matrix_by_node) == len(NODE_IDS)
    for node_id, row in matrix_by_node.items():
        expected_claim_ids = {
            claim["claim_id"]
            for claim in theme["claims"]
            if node_id in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == expected_claim_ids
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
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
    assert report["wave_results"]["wave_c"]["ready"] is False
    assert report["wave_results"]["wave_c"]["ready_theme_count"] == 1
    assert report["wave_results"]["wave_c"]["not_ready_theme_count"] == 4
    assert {chain_id for chain_id, row in rows.items() if row["ready"]} == (
        _implemented_wave_chain_ids("wave_c")
    )


def test_industrial_robots_evidence_mapping_and_source_identity_are_exact():
    _assert_bidirectional_source_and_matrix_links()
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
