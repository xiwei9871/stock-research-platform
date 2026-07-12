from collections import defaultdict
from collections import Counter
import re

from stock_research.technology_industry_catalog import CHAIN_FIELDS, load_industry_catalog


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
