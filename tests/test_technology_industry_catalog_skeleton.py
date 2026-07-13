from collections import defaultdict
from collections import Counter
from copy import deepcopy
import re

import pytest

from stock_research.technology_industry_catalog import (
    CHAIN_FIELDS,
    IndustryCatalogValidationError,
    find_industry_chain,
    load_industry_catalog,
    summarize_industry_catalog,
)


EXPECTED_CHAINS_BY_SECTOR = {
    "semiconductor_electronics": [
        "semiconductor_eda_ip_design_services",
        "ai_logic_compute_chips",
        "memory_chips_storage_control",
        "analog_mixed_signal_rf_chips",
        "power_semiconductors",
        "mems_intelligent_sensors",
        "wafer_manufacturing_specialty_processes",
        "semiconductor_manufacturing_equipment",
        "semiconductor_materials_electronic_chemicals",
        "semiconductor_packaging_test_advanced_packaging",
        "pcb_passives_connectors_interconnect",
        "display_panels_optoelectronic_components",
    ],
    "next_generation_information_technology": [
        "ai_foundation_models_application_software",
        "ai_compute_infrastructure",
        "cloud_data_center_infrastructure",
        "mobile_communications_5g_6g",
        "optical_communications_data_center_interconnect",
        "network_equipment_edge_iot",
        "foundational_software_os_database",
        "industrial_software",
        "cybersecurity_data_infrastructure",
    ],
    "high_end_equipment_intelligent_manufacturing": [
        "industrial_machine_tools_cnc",
        "industrial_automation_control",
        "industrial_robots",
        "humanoid_robots_embodied_intelligence",
        "laser_equipment_additive_manufacturing",
        "scientific_instruments",
        "industrial_inspection_metrology_machine_vision",
        "core_mechanical_components",
        "process_industry_specialized_equipment",
    ],
    "energy_technology_new_power_system": [
        "new_power_system_smart_grid",
        "power_generation_energy_equipment",
        "power_electronics_power_supply_equipment",
        "ai_data_center_power",
        "solar_power",
        "wind_power",
        "power_batteries_battery_materials",
        "new_energy_storage",
        "hydrogen_fuel_cells",
        "nuclear_power_equipment",
    ],
    "advanced_materials": [
        "advanced_metals_specialty_alloys",
        "rare_earth_permanent_magnets_critical_minerals",
        "carbon_fiber_advanced_composites",
        "advanced_ceramics_specialty_glass",
        "high_performance_polymers_engineering_plastics",
        "membrane_separation_materials",
        "nanomaterials_functional_materials",
    ],
    "intelligent_vehicles_advanced_transportation": [
        "new_energy_vehicle_architecture_platforms",
        "intelligent_driving_smart_cockpit",
        "automotive_electronics_chip_applications",
        "electric_drive_chassis_by_wire_thermal_management",
        "rail_transit_equipment",
        "intelligent_transport_vehicle_road_cloud",
    ],
    "aerospace_low_altitude_ocean_technology": [
        "civil_aircraft_aero_engines",
        "commercial_space_launch",
        "satellite_manufacturing_space_infrastructure",
        "satellite_communications_navigation_remote_sensing",
        "uav_evtol_low_altitude_economy",
        "ships_offshore_deep_sea_equipment",
        "defense_electronics_special_equipment",
    ],
    "life_sciences_medical_technology": [
        "small_molecule_innovative_drugs",
        "biologic_antibody_drugs",
        "vaccines",
        "cell_gene_therapy",
        "synthetic_biology_biomanufacturing",
        "high_end_medical_devices",
        "medical_imaging_diagnostic_equipment",
        "in_vitro_diagnostics",
        "digital_health_healthcare_it",
        "agricultural_biotechnology_modern_seeds",
    ],
    "green_low_carbon_resource_recycling": [
        "air_soil_industrial_pollution_control",
        "water_treatment_resource_technology",
        "solid_waste_resource_recovery_circular_economy",
        "carbon_capture_utilization_storage",
        "industrial_energy_efficiency_management",
    ],
    "frontier_future_technology": [
        "quantum_computing_communication_measurement",
        "brain_computer_interfaces_neural_engineering",
        "controlled_nuclear_fusion",
        "future_networks_next_generation_internet",
        "spatial_computing_xr_metaverse_infrastructure",
        "future_displays",
        "new_computing_routes",
    ],
}


EXPECTED_CHAIN_CONTRACT = {
    "semiconductor_eda_ip_design_services": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "ai_logic_compute_chips": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "memory_chips_storage_control": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "analog_mixed_signal_rf_chips": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "power_semiconductors": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "mems_intelligent_sensors": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "wafer_manufacturing_specialty_processes": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "semiconductor_manufacturing_equipment": ("manufacturing_process", "canonical_industry_chain", "draft"),
    "semiconductor_materials_electronic_chemicals": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "semiconductor_packaging_test_advanced_packaging": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "pcb_passives_connectors_interconnect": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "display_panels_optoelectronic_components": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "ai_foundation_models_application_software": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "ai_compute_infrastructure": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "cloud_data_center_infrastructure": ("infrastructure_flow", "canonical_industry_chain", "skeleton"),
    "mobile_communications_5g_6g": ("infrastructure_flow", "canonical_industry_chain", "skeleton"),
    "optical_communications_data_center_interconnect": ("infrastructure_flow", "canonical_industry_chain", "skeleton"),
    "network_equipment_edge_iot": ("infrastructure_flow", "canonical_industry_chain", "skeleton"),
    "foundational_software_os_database": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "industrial_software": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "cybersecurity_data_infrastructure": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "industrial_machine_tools_cnc": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "industrial_automation_control": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "industrial_robots": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "humanoid_robots_embodied_intelligence": ("system_architecture", "canonical_industry_chain", "draft"),
    "laser_equipment_additive_manufacturing": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "scientific_instruments": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "industrial_inspection_metrology_machine_vision": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "core_mechanical_components": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "process_industry_specialized_equipment": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "new_power_system_smart_grid": ("infrastructure_flow", "canonical_industry_chain", "skeleton"),
    "power_generation_energy_equipment": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "power_electronics_power_supply_equipment": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "ai_data_center_power": ("infrastructure_flow", "application_theme_chain", "draft"),
    "solar_power": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "wind_power": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "power_batteries_battery_materials": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "new_energy_storage": ("technical_route", "canonical_industry_chain", "skeleton"),
    "hydrogen_fuel_cells": ("technical_route", "canonical_industry_chain", "skeleton"),
    "nuclear_power_equipment": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "advanced_metals_specialty_alloys": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "rare_earth_permanent_magnets_critical_minerals": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "carbon_fiber_advanced_composites": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "advanced_ceramics_specialty_glass": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "high_performance_polymers_engineering_plastics": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "membrane_separation_materials": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "nanomaterials_functional_materials": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "new_energy_vehicle_architecture_platforms": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "intelligent_driving_smart_cockpit": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "automotive_electronics_chip_applications": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "electric_drive_chassis_by_wire_thermal_management": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "rail_transit_equipment": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "intelligent_transport_vehicle_road_cloud": ("infrastructure_flow", "application_theme_chain", "skeleton"),
    "civil_aircraft_aero_engines": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "commercial_space_launch": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "satellite_manufacturing_space_infrastructure": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "satellite_communications_navigation_remote_sensing": ("infrastructure_flow", "application_theme_chain", "skeleton"),
    "uav_evtol_low_altitude_economy": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "ships_offshore_deep_sea_equipment": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "defense_electronics_special_equipment": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "small_molecule_innovative_drugs": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "biologic_antibody_drugs": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "vaccines": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "cell_gene_therapy": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "synthetic_biology_biomanufacturing": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "high_end_medical_devices": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "medical_imaging_diagnostic_equipment": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "in_vitro_diagnostics": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "digital_health_healthcare_it": ("system_architecture", "canonical_industry_chain", "skeleton"),
    "agricultural_biotechnology_modern_seeds": ("manufacturing_process", "canonical_industry_chain", "skeleton"),
    "air_soil_industrial_pollution_control": ("infrastructure_flow", "canonical_industry_chain", "skeleton"),
    "water_treatment_resource_technology": ("infrastructure_flow", "canonical_industry_chain", "skeleton"),
    "solid_waste_resource_recovery_circular_economy": ("infrastructure_flow", "canonical_industry_chain", "skeleton"),
    "carbon_capture_utilization_storage": ("technical_route", "canonical_industry_chain", "skeleton"),
    "industrial_energy_efficiency_management": ("infrastructure_flow", "canonical_industry_chain", "skeleton"),
    "quantum_computing_communication_measurement": ("technical_route", "frontier_technology_chain", "skeleton"),
    "brain_computer_interfaces_neural_engineering": ("technical_route", "frontier_technology_chain", "skeleton"),
    "controlled_nuclear_fusion": ("technical_route", "frontier_technology_chain", "skeleton"),
    "future_networks_next_generation_internet": ("technical_route", "frontier_technology_chain", "skeleton"),
    "spatial_computing_xr_metaverse_infrastructure": ("technical_route", "frontier_technology_chain", "skeleton"),
    "future_displays": ("technical_route", "frontier_technology_chain", "skeleton"),
    "new_computing_routes": ("technical_route", "frontier_technology_chain", "skeleton"),
}


EXPECTED_SKELETON_APPLICATION_CANONICAL_DEFERRALS = {
    "intelligent_transport_vehicle_road_cloud": {
        "new_energy_vehicle_architecture_platforms",
        "intelligent_driving_smart_cockpit",
        "automotive_electronics_chip_applications",
        "electric_drive_chassis_by_wire_thermal_management",
        "network_equipment_edge_iot",
        "cloud_data_center_infrastructure",
    },
    "satellite_communications_navigation_remote_sensing": {
        "satellite_manufacturing_space_infrastructure",
        "network_equipment_edge_iot",
        "optical_communications_data_center_interconnect",
    },
}

REQUIRED_ALIAS_REPLACEMENTS = {
    "intelligent_transport_vehicle_road_cloud": (
        "Smart Transportation",
        "Cooperative Vehicle-Road-Cloud Services",
    ),
    "satellite_manufacturing_space_infrastructure": (
        "Satellite Industry",
        "Satellite Platform Manufacturing",
    ),
    "biologic_antibody_drugs": (
        "Biopharmaceuticals",
        "Antibody and Protein Therapeutics",
    ),
    "air_soil_industrial_pollution_control": (
        "Environmental Pollution Control",
        "Air, Soil, and Industrial Emissions Control",
    ),
}


EXISTING_CHAIN_IDS = {
    "power_semiconductors",
    "semiconductor_manufacturing_equipment",
    "pcb_passives_connectors_interconnect",
    "cloud_data_center_infrastructure",
    "industrial_software",
    "humanoid_robots_embodied_intelligence",
    "new_power_system_smart_grid",
    "power_generation_energy_equipment",
    "power_electronics_power_supply_equipment",
    "ai_data_center_power",
    "power_batteries_battery_materials",
    "new_energy_storage",
    "hydrogen_fuel_cells",
}


def _chains_by_id():
    return {
        chain["chain_id"]: chain
        for chain in load_industry_catalog()["chains"]
    }


def _normalized(value):
    return value.strip().casefold()


def test_find_industry_chain_resolves_repository_chain_id():
    catalog = load_industry_catalog()
    catalog_before = deepcopy(catalog)

    chain = find_industry_chain(catalog, "semiconductor_manufacturing_equipment")

    assert chain["chain_id"] == "semiconductor_manufacturing_equipment"
    assert chain is next(
        row
        for row in catalog["chains"]
        if row["chain_id"] == "semiconductor_manufacturing_equipment"
    )
    assert catalog == catalog_before


def test_find_industry_chain_resolves_repository_chain_name():
    catalog = load_industry_catalog()

    chain = find_industry_chain(catalog, "Semiconductor Manufacturing Equipment")

    assert chain["chain_id"] == "semiconductor_manufacturing_equipment"


@pytest.mark.parametrize(
    ("query", "chain_id"),
    [
        ("人形机器人", "humanoid_robots_embodied_intelligence"),
        ("AI数据中心供电", "ai_data_center_power"),
    ],
)
def test_find_industry_chain_resolves_repository_alias(query, chain_id):
    catalog = load_industry_catalog()

    chain = find_industry_chain(catalog, query)

    assert chain["chain_id"] == chain_id


def test_find_industry_chain_strips_and_casefolds_query():
    catalog = load_industry_catalog()

    chain = find_industry_chain(catalog, "  sEmIcOnDuCtOr MaNuFaCtUrInG eQuIpMeNt  ")

    assert chain["chain_id"] == "semiconductor_manufacturing_equipment"


@pytest.mark.parametrize("query", [None, 1, "", "   "])
def test_find_industry_chain_rejects_invalid_query_as_not_found(query):
    with pytest.raises(IndustryCatalogValidationError) as exc_info:
        find_industry_chain({"chains": []}, query)

    assert exc_info.value.code == "CHAIN_NOT_FOUND"


def test_find_industry_chain_rejects_unknown_query():
    with pytest.raises(IndustryCatalogValidationError) as exc_info:
        find_industry_chain(load_industry_catalog(), "unknown chain")

    assert exc_info.value.code == "CHAIN_NOT_FOUND"


def test_find_industry_chain_rejects_shared_alias():
    catalog = {
        "chains": [
            {"chain_id": "first", "chain_name": "First", "aliases": ["shared"]},
            {"chain_id": "second", "chain_name": "Second", "aliases": ["shared"]},
        ]
    }

    with pytest.raises(IndustryCatalogValidationError) as exc_info:
        find_industry_chain(catalog, "shared")

    assert exc_info.value.code == "AMBIGUOUS_CHAIN_ALIAS"


def test_find_industry_chain_rejects_duplicate_normalized_names():
    catalog = {
        "chains": [
            {"chain_id": "first", "chain_name": "Shared Name", "aliases": []},
            {
                "chain_id": "second",
                "chain_name": "  shared name  ",
                "aliases": [],
            },
        ]
    }

    with pytest.raises(IndustryCatalogValidationError) as exc_info:
        find_industry_chain(catalog, "SHARED NAME")

    assert exc_info.value.code == "AMBIGUOUS_CHAIN_NAME"
    assert str(exc_info.value) == "ambiguous chain name: SHARED NAME"


def test_find_industry_chain_id_wins_over_duplicate_normalized_names():
    catalog = {
        "chains": [
            {
                "chain_id": "first",
                "chain_name": "Duplicate Name",
                "aliases": [],
            },
            {
                "chain_id": "target-id",
                "chain_name": "  duplicate name  ",
                "aliases": [],
            },
        ]
    }

    chain = find_industry_chain(catalog, "target-id")

    assert chain["chain_id"] == "target-id"


@pytest.mark.parametrize("aliases", [42, True, {}, "scalar"])
def test_find_industry_chain_rejects_non_list_aliases_with_domain_error(aliases):
    catalog = {
        "chains": [
            {"chain_id": "first", "chain_name": "First", "aliases": aliases},
        ]
    }

    with pytest.raises(IndustryCatalogValidationError) as exc_info:
        find_industry_chain(catalog, "unknown")

    assert exc_info.value.code == "INVALID_CHAIN_ALIASES"
    assert str(exc_info.value) == "chains[0].aliases must be a list"


@pytest.mark.parametrize("alias", [None, True, {}, "   "])
def test_find_industry_chain_rejects_malformed_alias_entries_with_domain_error(alias):
    catalog = {
        "chains": [
            {"chain_id": "first", "chain_name": "First", "aliases": [alias]},
        ]
    }

    with pytest.raises(IndustryCatalogValidationError) as exc_info:
        find_industry_chain(catalog, "unknown")

    assert exc_info.value.code == "INVALID_CHAIN_ALIASES"
    assert str(exc_info.value) == "chains[0].aliases[0] must be a non-empty string"


@pytest.mark.parametrize("query", ["target-id", "Target Name"])
def test_find_industry_chain_preserves_direct_lookup_before_alias_validation(query):
    catalog = {
        "chains": [
            {"chain_id": "first", "chain_name": "First", "aliases": 42},
            {"chain_id": "target-id", "chain_name": "Target Name", "aliases": []},
        ]
    }

    chain = find_industry_chain(catalog, query)

    assert chain["chain_id"] == "target-id"


@pytest.mark.parametrize(
    "query",
    [
        "机器人",
        "人形 机器人",
        "人形机器人!",
    ],
)
def test_find_industry_chain_does_not_normalize_substrings_or_punctuation(query):
    with pytest.raises(IndustryCatalogValidationError) as exc_info:
        find_industry_chain(load_industry_catalog(), query)

    assert exc_info.value.code == "CHAIN_NOT_FOUND"


@pytest.mark.parametrize(
    ("query", "expected_chain_id"),
    [("shared-id", "shared-id"), ("shared name", "shared-id")],
)
def test_find_industry_chain_prioritizes_ids_and_names_over_aliases(
    query,
    expected_chain_id,
):
    catalog = {
        "chains": [
            {
                "chain_id": "alias_owner",
                "chain_name": "Alias Owner",
                "aliases": ["shared-id", "shared name"],
            },
            {
                "chain_id": "shared-id",
                "chain_name": "Shared Name",
                "aliases": [],
            },
        ]
    }

    chain = find_industry_chain(catalog, query)

    assert chain["chain_id"] == expected_chain_id



def test_repository_catalog_matches_frozen_l2_registry():
    catalog = load_industry_catalog()
    expected_serialized_order = [
        (sector_id, order, chain_id)
        for sector_id, chain_ids in EXPECTED_CHAINS_BY_SECTOR.items()
        for order, chain_id in enumerate(chain_ids, start=1)
    ]
    actual_serialized_order = [
        (chain["sector_id"], chain["order"], chain["chain_id"])
        for chain in catalog["chains"]
    ]

    assert actual_serialized_order == expected_serialized_order
    assert len(actual_serialized_order) == 82
    assert len({chain_id for _, _, chain_id in actual_serialized_order}) == 82


def test_green_sector_registry_and_order_are_exact():
    chains_by_id = _chains_by_id()

    actual = [
        (chains_by_id[chain_id]["order"], chain_id)
        for chain_id in EXPECTED_CHAINS_BY_SECTOR[
            "green_low_carbon_resource_recycling"
        ]
    ]

    assert actual == [
        (1, "air_soil_industrial_pollution_control"),
        (2, "water_treatment_resource_technology"),
        (3, "solid_waste_resource_recovery_circular_economy"),
        (4, "carbon_capture_utilization_storage"),
        (5, "industrial_energy_efficiency_management"),
    ]


def test_every_chain_matches_the_approved_metadata_contract():
    chains_by_id = _chains_by_id()
    actual_contract = {
        chain_id: (
            chain["decomposition_method"],
            chain["chain_kind"],
            chain["status"],
        )
        for chain_id, chain in chains_by_id.items()
    }

    assert actual_contract == EXPECTED_CHAIN_CONTRACT
    assert all(set(chain) == CHAIN_FIELDS for chain in chains_by_id.values())


def test_catalog_summary_reports_structural_completeness_from_loaded_nodes():
    catalog = load_industry_catalog()
    summary = summarize_industry_catalog(catalog)
    node_levels_by_chain = defaultdict(set)
    for node in catalog["nodes"]:
        node_levels_by_chain[node["chain_id"]].add(node["level"])
    expected_unexpanded_chain_ids = sorted(
        chain["chain_id"]
        for chain in catalog["chains"]
        if not {"L3", "L4"} <= node_levels_by_chain[chain["chain_id"]]
    )

    assert summary["sector_count"] == 10
    assert summary["chain_count"] == 82
    assert summary["chains_by_decomposition_method"] == {
        "infrastructure_flow": 12,
        "manufacturing_process": 28,
        "system_architecture": 32,
        "technical_route": 10,
    }
    assert summary["detailed_chain_count"] == 13
    assert summary["skeleton_chain_count"] == 69
    assert summary["detailed_chain_count"] + summary["skeleton_chain_count"] == 82
    assert summary["structural_completeness_percent"] == 15.85
    assert summary["unexpanded_chain_ids"] == expected_unexpanded_chain_ids
    assert "evidence_completeness_percent" not in summary
    assert "company_coverage_percent" not in summary


def test_catalog_summary_requires_both_levels_regardless_of_status():
    catalog = {
        "sectors": [],
        "chains": [
            {
                "chain_id": "detailed_despite_skeleton_status",
                "chain_kind": "canonical_industry_chain",
                "decomposition_method": "manufacturing_process",
                "status": "skeleton",
                "sector_id": "sector",
            },
            {
                "chain_id": "l3_only",
                "chain_kind": "canonical_industry_chain",
                "decomposition_method": "system_architecture",
                "status": "published",
                "sector_id": "sector",
            },
            {
                "chain_id": "l4_only",
                "chain_kind": "canonical_industry_chain",
                "decomposition_method": "technical_route",
                "status": "draft",
                "sector_id": "sector",
            },
        ],
        "nodes": [
            {
                "chain_id": "detailed_despite_skeleton_status",
                "level": "L3",
                "status": "skeleton",
            },
            {
                "chain_id": "detailed_despite_skeleton_status",
                "level": "L4",
                "status": "skeleton",
            },
            {"chain_id": "l3_only", "level": "L3", "status": "published"},
            {"chain_id": "l4_only", "level": "L4", "status": "draft"},
        ],
        "edges": [],
        "theme_compositions": [],
    }

    summary = summarize_industry_catalog(catalog)

    assert summary["detailed_chain_count"] == 1
    assert summary["skeleton_chain_count"] == 2
    assert summary["structural_completeness_percent"] == 33.33
    assert summary["unexpanded_chain_ids"] == ["l3_only", "l4_only"]
    assert summarize_industry_catalog({**catalog, "chains": [], "nodes": []})[
        "structural_completeness_percent"
    ] == 0.0


def test_chain_descriptions_and_scopes_are_specific_and_not_reused():
    chains = list(_chains_by_id().values())
    descriptions = [chain["description"].strip() for chain in chains]
    scopes = [chain["scope"].strip() for chain in chains]

    assert all(len(description) >= 80 for description in descriptions)
    assert all(len(scope) >= 100 for scope in scopes)
    assert not {
        text: count
        for text, count in Counter(descriptions).items()
        if count > 1
    }
    assert not {
        text: count
        for text, count in Counter(scopes).items()
        if count > 1
    }


def test_chain_exclusions_and_aliases_are_nonempty_unique_strings():
    for chain_id, chain in _chains_by_id().items():
        for field in ("exclusions", "aliases"):
            values = chain[field]
            assert isinstance(values, list), f"{chain_id}.{field} must be a list"
            assert values, f"{chain_id}.{field} must not be empty"
            assert all(
                isinstance(value, str) and value.strip() for value in values
            ), f"{chain_id}.{field} contains an empty or non-string value"
            assert len(values) == len(set(values)), (
                f"{chain_id}.{field} contains duplicate values"
            )
        assert any(re.search(r"[\u4e00-\u9fff]", alias) for alias in chain["aliases"]), (
            f"{chain_id}.aliases must include a stable Chinese alias"
        )


def test_exclusions_never_assign_canonical_ownership_to_application_chains():
    chains_by_id = _chains_by_id()
    application_chain_ids = {
        chain_id
        for chain_id, chain in chains_by_id.items()
        if chain["chain_kind"] == "application_theme_chain"
    }

    violations = {
        chain_id: [
            application_chain_id
            for application_chain_id in application_chain_ids
            if any(
                re.search(
                    rf"\bowned by\b[^.]*\b{re.escape(application_chain_id)}\b",
                    exclusion,
                )
                for exclusion in chain["exclusions"]
            )
        ]
        for chain_id, chain in chains_by_id.items()
    }

    assert not {
        chain_id: application_chain_ids
        for chain_id, application_chain_ids in violations.items()
        if application_chain_ids
    }


def test_display_chains_have_an_explicit_commercial_maturity_boundary():
    chains_by_id = _chains_by_id()
    commercial = chains_by_id["display_panels_optoelectronic_components"]
    frontier = chains_by_id["future_displays"]
    commercial_text = " ".join(
        [commercial["description"], commercial["scope"], *commercial["exclusions"]]
    ).casefold()
    frontier_text = " ".join(
        [frontier["description"], frontier["scope"], *frontier["exclusions"]]
    ).casefold()

    assert "commercial" in commercial_text
    assert "mass-production" in commercial_text
    assert "future_displays" in commercial_text
    assert "pre-commercial" in frontier_text
    assert "emerging technical routes" in frontier_text
    assert "display_panels_optoelectronic_components" in frontier_text


def test_membrane_chain_defers_battery_separators_to_battery_chain():
    chain = _chains_by_id()["membrane_separation_materials"]
    scope = chain["scope"].casefold()
    exclusions = " ".join(chain["exclusions"]).casefold()

    assert "battery separator" not in scope.replace("-", " ")
    assert "battery-separator" not in exclusions
    assert "battery separator" in exclusions
    assert "power_batteries_battery_materials" in exclusions
    assert "industrial" in scope
    assert "environmental" in scope


def test_synthetic_biology_defers_therapeutic_products_to_drug_chains():
    chain = _chains_by_id()["synthetic_biology_biomanufacturing"]
    owned_scope = " ".join([chain["description"], chain["scope"]]).casefold()
    exclusions = " ".join(chain["exclusions"]).casefold()

    assert "enabling production platforms" in owned_scope
    assert "non-pharmaceutical" in owned_scope
    assert "therapeutic drug products" in exclusions
    assert "biologic_antibody_drugs" in exclusions
    assert "small_molecule_innovative_drugs" in exclusions


def test_application_chains_defer_all_composed_and_skeleton_canonical_owners():
    catalog = load_industry_catalog()
    chains_by_id = {chain["chain_id"]: chain for chain in catalog["chains"]}
    nodes_by_id = {node["node_id"]: node for node in catalog["nodes"]}
    compositions_by_chain = defaultdict(list)
    for composition in catalog["theme_compositions"]:
        compositions_by_chain[composition["chain_id"]].append(composition)

    actual_application_ids = {
        chain_id
        for chain_id, chain in chains_by_id.items()
        if chain["chain_kind"] == "application_theme_chain"
    }
    detailed_application_ids = {
        chain_id
        for chain_id in actual_application_ids
        if compositions_by_chain[chain_id]
    }
    skeleton_application_ids = actual_application_ids - detailed_application_ids

    assert skeleton_application_ids == set(
        EXPECTED_SKELETON_APPLICATION_CANONICAL_DEFERRALS
    )
    required_owner_ids_by_chain = {
        chain_id: {
            nodes_by_id[canonical_node_id]["chain_id"]
            for composition in compositions_by_chain[chain_id]
            for canonical_node_id in composition["canonical_node_refs"]
        }
        for chain_id in detailed_application_ids
    }
    required_owner_ids_by_chain.update(
        EXPECTED_SKELETON_APPLICATION_CANONICAL_DEFERRALS
    )

    assert set(required_owner_ids_by_chain) == actual_application_ids
    assert all(
        chains_by_id[owner_id]["chain_kind"] == "canonical_industry_chain"
        for owner_ids in required_owner_ids_by_chain.values()
        for owner_id in owner_ids
    )
    missing_deferrals = {
        chain_id: sorted(
            owner_id
            for owner_id in expected_owner_ids
            if owner_id not in " ".join(chains_by_id[chain_id]["exclusions"])
        )
        for chain_id, expected_owner_ids in required_owner_ids_by_chain.items()
    }

    assert not {
        chain_id: owner_ids
        for chain_id, owner_ids in missing_deferrals.items()
        if owner_ids
    }, f"missing canonical owner deferrals: {missing_deferrals}"

    for chain_id in (
        "intelligent_transport_vehicle_road_cloud",
        "satellite_communications_navigation_remote_sensing",
    ):
        application_text = " ".join(
            [chains_by_id[chain_id]["description"], chains_by_id[chain_id]["scope"]]
        ).casefold()
        assert "cross-chain" in application_text
        assert "service" in application_text
        assert "data flow" in application_text


def test_broad_aliases_are_replaced_with_owner_specific_synonyms():
    chains_by_id = _chains_by_id()

    for chain_id, (removed_alias, replacement_alias) in REQUIRED_ALIAS_REPLACEMENTS.items():
        aliases = chains_by_id[chain_id]["aliases"]
        assert removed_alias not in aliases
        assert replacement_alias in aliases


def test_chain_names_are_globally_unique_after_normalization():
    names_by_normalized_value = defaultdict(list)
    for chain_id, chain in _chains_by_id().items():
        names_by_normalized_value[_normalized(chain["chain_name"])].append(chain_id)

    collisions = {
        normalized_name: sorted(chain_ids)
        for normalized_name, chain_ids in names_by_normalized_value.items()
        if len(chain_ids) > 1
    }

    assert not collisions, f"normalized chain-name collisions: {collisions}"


def test_aliases_are_globally_unique_after_normalization():
    alias_owners = defaultdict(list)
    for chain_id, chain in _chains_by_id().items():
        for alias in chain["aliases"]:
            alias_owners[_normalized(alias)].append((chain_id, alias))

    collisions = {
        normalized_alias: owners
        for normalized_alias, owners in alias_owners.items()
        if len(owners) > 1
    }

    assert not collisions, f"normalized alias collisions: {collisions}"


def test_aliases_do_not_collide_with_another_chain_name_or_id():
    chains_by_id = _chains_by_id()
    identity_owners = defaultdict(set)
    for chain_id, chain in chains_by_id.items():
        identity_owners[_normalized(chain_id)].add(chain_id)
        identity_owners[_normalized(chain["chain_name"])].add(chain_id)

    collisions = {}
    for chain_id, chain in chains_by_id.items():
        for alias in chain["aliases"]:
            other_owners = identity_owners[_normalized(alias)] - {chain_id}
            if other_owners:
                collisions[(chain_id, alias)] = sorted(other_owners)

    assert not collisions, f"aliases colliding with other chain names or IDs: {collisions}"


def test_chain_names_are_unique_within_each_sector():
    names_by_sector = defaultdict(list)
    for chain in _chains_by_id().values():
        names_by_sector[chain["sector_id"]].append(chain["chain_name"])

    duplicates = {
        sector_id: [
            name
            for name, count in Counter(names).items()
            if count > 1
        ]
        for sector_id, names in names_by_sector.items()
    }

    assert not {sector_id: names for sector_id, names in duplicates.items() if names}


def test_existing_detailed_chains_retain_approved_kinds_and_pilot_statuses():
    chains_by_id = _chains_by_id()
    approved_existing_contract = {
        chain_id: (
            EXPECTED_CHAIN_CONTRACT[chain_id][1],
            EXPECTED_CHAIN_CONTRACT[chain_id][2],
        )
        for chain_id in EXISTING_CHAIN_IDS
    }
    actual_existing_contract = {
        chain_id: (chains_by_id[chain_id]["chain_kind"], chains_by_id[chain_id]["status"])
        for chain_id in EXISTING_CHAIN_IDS
    }

    assert EXISTING_CHAIN_IDS <= set(chains_by_id)
    assert actual_existing_contract == approved_existing_contract
    assert {
        chain_id
        for chain_id, chain in chains_by_id.items()
        if chain["status"] == "draft"
    } == {
        "semiconductor_manufacturing_equipment",
        "humanoid_robots_embodied_intelligence",
        "ai_data_center_power",
    }
