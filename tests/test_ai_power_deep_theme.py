from stock_research.industry_chain_theme_research import classify_beneficiary
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_company_mapping import load_theme_company_mapping_details
from stock_research.theme_decomposition import load_theme


THEME_ID = "ai_power_value_capture_v1"


def test_ai_power_is_a_complete_readable_deep_theme_reference():
    detail = load_theme(THEME_ID)
    profile = detail["research_profile"]

    assert profile is not None
    assert profile["catalog_chain_id"] == "ai_data_center_power"
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert all(
        profile[field]
        for field in (
            "central_conflict",
            "investment_summary",
            "value_flow_summary",
            "profit_pool_summary",
            "evidence_gap_summary",
        )
    )
    assert len(profile["validation_signals"]) >= 3
    assert len(detail["nodes"]) >= 11
    assert len(detail["sources"]) >= 10
    assert len(detail["claims"]) >= 10
    assert {claim["claim_type"] for claim in detail["claims"]} >= {"catalyst", "risk"}


def test_ai_power_has_at_least_eight_evidence_backed_reviewed_company_mappings():
    mappings = load_theme_company_mapping_details(THEME_ID)
    reviewed = [
        mapping
        for mapping in mappings
        if classify_beneficiary(mapping, mapping["evidence"]) != "concept_association"
    ]

    assert len(reviewed) >= 8
    assert {
        "002837.SZ",
        "002335.SZ",
        "300870.SZ",
        "002364.SZ",
        "301018.SZ",
        "300499.SZ",
        "000811.SZ",
        "300442.SZ",
    } <= {mapping["company_code"] for mapping in reviewed}
    assert all(mapping["evidence"] for mapping in reviewed)


def test_ai_power_catalog_link_accounts_for_every_theme_node():
    detail = load_theme(THEME_ID)
    catalog = load_industry_catalog()
    link = next(row for row in catalog["theme_links"] if row["theme_id"] == THEME_ID)
    accounted_theme_nodes = {
        row["theme_node_id"] for row in link["node_links"]
    } | set(link["unmapped_theme_node_ids"])

    assert accounted_theme_nodes == {node["node_id"] for node in detail["nodes"]}
