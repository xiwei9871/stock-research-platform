from stock_research.industry_chain_theme_research import verify_deep_theme_coverage
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_company_mapping import load_theme_company_mapping_details
from stock_research.theme_decomposition import load_theme
from stock_research.theme_research_priority import load_theme_research_priority_package


THEME_ID = "new_energy_storage_value_chain_v1"


def test_new_energy_storage_theme_separates_equipment_integration_and_market_value():
    detail = load_theme(THEME_ID)
    required_nodes = {
        "storage_cells_materials",
        "storage_modules_packs",
        "storage_pcs",
        "storage_bms",
        "storage_ems",
        "storage_thermal_management",
        "storage_fire_protection",
        "storage_enclosure_electrical_bos",
        "storage_system_integration",
        "storage_epc_grid_connection",
        "storage_operations_maintenance",
        "storage_market_participation",
    }

    assert detail["research_profile"]["catalog_chain_id"] == "new_energy_storage"
    assert required_nodes <= {row["node_id"] for row in detail["nodes"]}
    assert len(detail["sources"]) >= 10
    assert len(detail["claims"]) >= 10
    assert {row["claim_type"] for row in detail["claims"]} >= {"catalyst", "risk"}
    assert len(load_theme_company_mapping_details(THEME_ID)) >= 8
    assert verify_deep_theme_coverage(
        THEME_ID,
        catalog=load_industry_catalog(),
        theme_context=load_theme_research_priority_package(),
    )["ready"] is True
