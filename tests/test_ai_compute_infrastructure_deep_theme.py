from stock_research.industry_chain_theme_research import verify_deep_theme_coverage
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_company_mapping import load_theme_company_mapping_details
from stock_research.theme_decomposition import load_theme
from stock_research.theme_research_priority import load_theme_research_priority_package


THEME_ID = "ai_compute_infrastructure_value_chain_v1"


def test_ai_compute_theme_covers_system_stack_without_owning_power_and_cooling():
    detail = load_theme(THEME_ID)
    required_nodes = {
        "compute_accelerators_boards",
        "ai_servers_racks",
        "memory_storage",
        "cluster_networking",
        "optical_interconnect",
        "orchestration_system_software",
        "data_center_deployment",
        "compute_operations",
    }

    assert detail["research_profile"]["catalog_chain_id"] == "ai_compute_infrastructure"
    assert required_nodes <= {row["node_id"] for row in detail["nodes"]}
    assert "power" not in {row["node_id"] for row in detail["nodes"]}
    assert "cooling" not in {row["node_id"] for row in detail["nodes"]}
    assert len(detail["sources"]) >= 10
    assert len(detail["claims"]) >= 10
    assert len(load_theme_company_mapping_details(THEME_ID)) >= 8
    assert verify_deep_theme_coverage(
        THEME_ID,
        catalog=load_industry_catalog(),
        theme_context=load_theme_research_priority_package(),
    )["ready"] is True
