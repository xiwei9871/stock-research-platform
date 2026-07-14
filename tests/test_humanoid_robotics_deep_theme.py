from stock_research.industry_chain_theme_research import verify_deep_theme_coverage
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_company_mapping import load_theme_company_mapping_details
from stock_research.theme_decomposition import load_theme
from stock_research.theme_research_priority import load_theme_research_priority_package


THEME_ID = "humanoid_robotics_head_to_toe_v1"


def test_humanoid_robotics_theme_is_readable_and_evidence_backed():
    detail = load_theme(THEME_ID)

    assert detail["research_profile"]["catalog_chain_id"] == "humanoid_robots_embodied_intelligence"
    assert len(detail["nodes"]) >= 21
    assert len(detail["sources"]) >= 10
    assert len(detail["claims"]) >= 10
    assert {row["claim_type"] for row in detail["claims"]} >= {"catalyst", "risk"}
    mappings = load_theme_company_mapping_details(THEME_ID)
    assert len([row for row in mappings if row["review_status"] == "reviewed"]) >= 8
    assert all(row["evidence"] for row in mappings if row["review_status"] == "reviewed")
    assert verify_deep_theme_coverage(
        THEME_ID,
        catalog=load_industry_catalog(),
        theme_context=load_theme_research_priority_package(),
    )["ready"] is True
