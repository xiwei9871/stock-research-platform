from copy import deepcopy

from stock_research.industry_chain_theme_research import (
    COMPLETED_CHAIN_THEMES,
    NEXT_FIFTEEN_CHAIN_THEMES,
    SELECTED_CHAIN_THEMES,
    build_chain_research_summary,
    classify_beneficiary,
    list_selected_chain_research,
    verify_deep_theme_coverage,
)
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_research_priority import load_theme_research_priority_package


def test_selected_chain_registry_is_frozen():
    assert COMPLETED_CHAIN_THEMES == {
        "ai_data_center_power": "ai_power_value_capture_v1",
        "semiconductor_manufacturing_equipment": "semiconductor_manufacturing_equipment_value_chain_v1",
        "humanoid_robots_embodied_intelligence": "humanoid_robotics_head_to_toe_v1",
        "ai_compute_infrastructure": "ai_compute_infrastructure_value_chain_v1",
        "new_energy_storage": "new_energy_storage_value_chain_v1",
    }
    assert NEXT_FIFTEEN_CHAIN_THEMES == {
        "ai_logic_compute_chips": "ai_logic_compute_chips_value_chain_v1",
        "optical_communications_data_center_interconnect": "optical_communications_data_center_interconnect_value_chain_v1",
        "semiconductor_materials_electronic_chemicals": "semiconductor_materials_electronic_chemicals_value_chain_v1",
        "power_semiconductors": "power_semiconductors_value_chain_v1",
        "industrial_automation_control": "industrial_automation_control_value_chain_v1",
        "semiconductor_packaging_test_advanced_packaging": "semiconductor_packaging_test_advanced_packaging_value_chain_v1",
        "cloud_data_center_infrastructure": "cloud_data_center_infrastructure_value_chain_v1",
        "new_power_system_smart_grid": "new_power_system_smart_grid_value_chain_v1",
        "core_mechanical_components": "core_mechanical_components_value_chain_v1",
        "industrial_inspection_metrology_machine_vision": "industrial_inspection_metrology_machine_vision_value_chain_v1",
        "industrial_robots": "industrial_robots_value_chain_v1",
        "power_batteries_battery_materials": "power_batteries_battery_materials_value_chain_v1",
        "intelligent_driving_smart_cockpit": "intelligent_driving_smart_cockpit_value_chain_v1",
        "automotive_electronics_chip_applications": "automotive_electronics_chip_applications_value_chain_v1",
        "commercial_space_launch": "commercial_space_launch_value_chain_v1",
    }
    assert SELECTED_CHAIN_THEMES == {
        **COMPLETED_CHAIN_THEMES,
        **NEXT_FIFTEEN_CHAIN_THEMES,
    }


def test_beneficiary_classifier_separates_reviewed_tiers_and_concept_associations():
    assert classify_beneficiary(
        _mapping(business_materiality="meaningful_segment", confidence=0.92),
        _accepted_direct_evidence(),
    ) == "core_beneficiary"
    assert classify_beneficiary(
        _mapping(business_materiality="emerging_segment", confidence=0.86),
        _accepted_direct_evidence(),
    ) == "elastic_beneficiary"
    assert classify_beneficiary(
        _mapping(
            mapping_type="material_supplier",
            business_materiality="meaningful_segment",
            bottleneck_relevance="adjacent",
            confidence=0.82,
        ),
        _accepted_direct_evidence(evidence_type="service_relationship"),
    ) == "indirect_beneficiary"
    assert classify_beneficiary(
        _mapping(review_status="draft"),
        _accepted_direct_evidence(),
    ) == "concept_association"


def test_beneficiary_classifier_requires_accepted_direct_relationship_evidence():
    evidence = _accepted_direct_evidence()
    evidence[0]["source"]["review_status"] = "needs_full_text"

    assert classify_beneficiary(_mapping(), evidence) == "concept_association"
    assert classify_beneficiary(
        _mapping(),
        _accepted_direct_evidence(evidence_type="company_mention"),
    ) == "concept_association"


def test_selected_chain_summaries_report_existing_and_missing_theme_packages():
    catalog = load_industry_catalog()
    context = load_theme_research_priority_package()

    rows = list_selected_chain_research(catalog=catalog, theme_context=context)
    expanded_rows = list_selected_chain_research(
        catalog=catalog,
        theme_context=context,
        include_unfinished_targets=True,
    )
    by_chain = {row["chain_id"]: row for row in expanded_rows}

    assert len(rows) == 5
    assert len(expanded_rows) == 20
    assert by_chain["ai_data_center_power"]["theme_id"] == "ai_power_value_capture_v1"
    assert by_chain["ai_data_center_power"]["research_status"] == "reviewed"
    assert by_chain["humanoid_robots_embodied_intelligence"]["research_status"] == "reviewed"
    assert by_chain["semiconductor_manufacturing_equipment"]["research_status"] == "reviewed"
    assert by_chain["ai_compute_infrastructure"]["research_status"] == "reviewed"
    assert by_chain["new_energy_storage"]["research_status"] == "reviewed"
    assert by_chain["ai_logic_compute_chips"]["research_status"] == "reviewed"
    assert by_chain["optical_communications_data_center_interconnect"][
        "research_status"
    ] == "reviewed"
    assert by_chain["semiconductor_materials_electronic_chemicals"][
        "research_status"
    ] == "reviewed"
    assert by_chain["ai_compute_infrastructure"]["theme_route"].endswith(
        "/ai_compute_infrastructure_value_chain_v1"
    )
    implemented_theme_ids = {
        row["theme_id"] for row in context["theme_package"]["themes"]
    }
    assert {
        chain_id
        for chain_id, theme_id in NEXT_FIFTEEN_CHAIN_THEMES.items()
        if by_chain[chain_id]["research_status"] == "not_started"
    } == {
        chain_id
        for chain_id, theme_id in NEXT_FIFTEEN_CHAIN_THEMES.items()
        if theme_id not in implemented_theme_ids
    }


def test_nonselected_chain_has_no_deep_research_summary():
    assert build_chain_research_summary(
        "industrial_software",
        catalog=load_industry_catalog(),
        theme_context=load_theme_research_priority_package(),
    ) is None


def test_coverage_verifier_requires_all_review_gates():
    context = _ready_theme_context()
    catalog = {
        "chains": [{"chain_id": "new_energy_storage", "chain_name": "New Energy Storage"}],
        "nodes": [
            {"node_id": "storage_l3", "chain_id": "new_energy_storage", "level": "L3"},
            {"node_id": "storage_l4", "chain_id": "new_energy_storage", "level": "L4"},
        ],
        "theme_links": [
            {
                "theme_id": "new_energy_storage_value_chain_v1",
                "chain_id": "new_energy_storage",
                "node_links": [
                    {"theme_node_id": "storage_l3", "catalog_node_id": "storage_l3"},
                    {"theme_node_id": "storage_l4", "catalog_node_id": "storage_l4"},
                ],
                "unmapped_theme_node_ids": [],
            }
        ],
    }

    result = verify_deep_theme_coverage(
        "new_energy_storage_value_chain_v1",
        catalog=catalog,
        theme_context=context,
    )

    assert result["ready"] is True
    assert all(result["checks"].values())

    broken = deepcopy(context)
    broken["theme_package"]["sources"] = broken["theme_package"]["sources"][:9]
    result = verify_deep_theme_coverage(
        "new_energy_storage_value_chain_v1",
        catalog=catalog,
        theme_context=broken,
    )
    assert result["ready"] is False
    assert result["checks"]["accepted_source_count"] is False


def test_coverage_verifier_accounts_for_theme_nodes_without_requiring_entire_catalog():
    context = _ready_theme_context()
    context["theme_package"]["nodes"].append(
        {
            "theme_id": "new_energy_storage_value_chain_v1",
            "node_id": "storage_theme_gap",
        }
    )
    context["theme_package"]["claims"][-2]["platform_use_status"] = "draft"
    context["theme_package"]["claims"][-1]["platform_use_status"] = "draft"
    catalog = {
        "chains": [{"chain_id": "new_energy_storage", "chain_name": "New Energy Storage"}],
        "nodes": [
            {"node_id": "storage_l3", "chain_id": "new_energy_storage", "level": "L3"},
            {"node_id": "storage_l4", "chain_id": "new_energy_storage", "level": "L4"},
            {"node_id": "unrelated_l3", "chain_id": "new_energy_storage", "level": "L3"},
            {"node_id": "unrelated_l4", "chain_id": "new_energy_storage", "level": "L4"},
        ],
        "theme_links": [
            {
                "theme_id": "new_energy_storage_value_chain_v1",
                "chain_id": "new_energy_storage",
                "node_links": [
                    {"theme_node_id": "storage_l3", "catalog_node_id": "storage_l3"},
                    {"theme_node_id": "storage_l4", "catalog_node_id": "storage_l4"},
                ],
                "unmapped_theme_node_ids": ["storage_theme_gap"],
            }
        ],
    }

    result = verify_deep_theme_coverage(
        "new_energy_storage_value_chain_v1",
        catalog=catalog,
        theme_context=context,
    )

    assert result["ready"] is True
    assert result["checks"]["all_theme_nodes_accounted_for"] is True
    assert result["checks"]["structured_claim_count"] is True
    assert result["counts"]["structured_claims"] == 10
    assert result["counts"]["reviewed_claims"] == 8


def test_coverage_verifier_allows_catalog_skeletons_when_theme_nodes_are_accounted_for():
    context = _ready_theme_context()
    theme_id = "new_energy_storage_value_chain_v1"
    theme_node_ids = {
        row["node_id"]
        for row in context["theme_package"]["nodes"]
        if row["theme_id"] == theme_id
    }
    catalog = {
        "chains": [{"chain_id": "new_energy_storage", "chain_name": "New Energy Storage"}],
        "nodes": [],
        "theme_links": [
            {
                "theme_id": theme_id,
                "chain_id": "new_energy_storage",
                "node_links": [],
                "unmapped_theme_node_ids": sorted(theme_node_ids),
            }
        ],
    }

    result = verify_deep_theme_coverage(
        theme_id,
        catalog=catalog,
        theme_context=context,
    )

    assert result["ready"] is True
    assert result["checks"]["all_theme_nodes_accounted_for"] is True
    assert result["checks"]["catalog_l3_linked"] is True
    assert result["checks"]["catalog_l4_linked"] is True
    assert result["counts"]["l3_nodes"] == 0
    assert result["counts"]["l4_nodes"] == 0


def test_coverage_verifier_still_requires_links_for_populated_catalog_levels():
    context = _ready_theme_context()
    theme_id = "new_energy_storage_value_chain_v1"
    theme_node_ids = {
        row["node_id"]
        for row in context["theme_package"]["nodes"]
        if row["theme_id"] == theme_id
    }
    catalog = {
        "chains": [{"chain_id": "new_energy_storage", "chain_name": "New Energy Storage"}],
        "nodes": [
            {"node_id": "storage_l3", "chain_id": "new_energy_storage", "level": "L3"},
            {"node_id": "storage_l4", "chain_id": "new_energy_storage", "level": "L4"},
        ],
        "theme_links": [
            {
                "theme_id": theme_id,
                "chain_id": "new_energy_storage",
                "node_links": [],
                "unmapped_theme_node_ids": sorted(theme_node_ids),
            }
        ],
    }

    result = verify_deep_theme_coverage(
        theme_id,
        catalog=catalog,
        theme_context=context,
    )

    assert result["ready"] is False
    assert result["checks"]["all_theme_nodes_accounted_for"] is True
    assert result["checks"]["catalog_l3_linked"] is False
    assert result["checks"]["catalog_l4_linked"] is False


def _mapping(**overrides):
    row = {
        "mapping_id": "mapping_1",
        "theme_id": "theme_1",
        "company_code": "000001.SZ",
        "mapping_type": "direct_product",
        "business_stage": "primary_business",
        "confidence": 0.9,
        "revenue_relevance": "meaningful",
        "bottleneck_relevance": "core",
        "business_materiality": "meaningful_segment",
        "review_status": "reviewed",
    }
    row.update(overrides)
    return row


def _accepted_direct_evidence(*, evidence_type="product_relationship"):
    return [
        {
            "evidence_id": "evidence_1",
            "evidence_type": evidence_type,
            "source": {
                "source_id": "source_1",
                "reliability_level": "S0",
                "review_status": "accepted",
            },
        }
    ]


def _ready_theme_context():
    theme_id = "new_energy_storage_value_chain_v1"
    sources = [
        {
            "source_id": f"source_{index}",
            "source_type": "company_filing" if index < 4 else "official_report",
            "reliability_level": "S0" if index < 4 else "S1",
            "review_status": "accepted",
        }
        for index in range(10)
    ]
    claims = [
        {
            "claim_id": f"claim_{index}",
            "theme_id": theme_id,
            "source_id": sources[index % len(sources)]["source_id"],
            "supporting_source_ids": [],
            "platform_use_status": "reviewed",
        }
        for index in range(10)
    ]
    nodes = [
        {"theme_id": theme_id, "node_id": "storage_l3"},
        {"theme_id": theme_id, "node_id": "storage_l4"},
    ]
    mappings = [
        {
            **_mapping(mapping_id=f"mapping_{index}", company_code=f"00000{index}.SZ"),
            "theme_id": theme_id,
        }
        for index in range(8)
    ]
    evidence_items = [
        {
            "evidence_id": f"evidence_{index}",
            "evidence_type": "product_relationship",
            "source_id": sources[index % 4]["source_id"],
        }
        for index in range(8)
    ]
    for index, mapping in enumerate(mappings):
        mapping["evidence_ids"] = [evidence_items[index]["evidence_id"]]
    return {
        "theme_package": {
            "themes": [
                {
                    "theme_id": theme_id,
                    "theme_name": "New Energy Storage",
                    "status": "reviewed",
                    "last_updated": "2026-07-14",
                }
            ],
            "nodes": nodes,
            "sources": sources,
            "claims": claims,
            "research_profiles": [
                {
                    "theme_id": theme_id,
                    "catalog_chain_id": "new_energy_storage",
                }
            ],
        },
        "mapping_package": {
            "company_mappings": mappings,
            "evidence_items": evidence_items,
            "sources": sources,
        },
        "node_priorities": [],
        "company_priorities": [],
        "evidence_gap_priorities": [],
        "review_queue": [],
    }
