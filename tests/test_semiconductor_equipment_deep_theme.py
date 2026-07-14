from stock_research.industry_chain_theme_research import verify_deep_theme_coverage
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_company_mapping import load_theme_company_mapping_details
from stock_research.theme_decomposition import load_theme
from stock_research.theme_research_priority import load_theme_research_priority_package


THEME_ID = "semiconductor_manufacturing_equipment_value_chain_v1"


def test_semiconductor_equipment_theme_covers_process_families_and_review_gates():
    detail = load_theme(THEME_ID)
    required_nodes = {
        "semiconductor_lithography_patterning",
        "semiconductor_etch",
        "semiconductor_deposition_epitaxy",
        "semiconductor_thermal_doping",
        "semiconductor_clean_wet_process",
        "semiconductor_cmp",
        "semiconductor_inspection_metrology_process_control",
        "semiconductor_wafer_handling_automation",
        "semiconductor_vacuum_gas_fluid_control",
        "semiconductor_facilities_pollution_control",
    }

    assert detail["research_profile"]["catalog_chain_id"] == "semiconductor_manufacturing_equipment"
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
