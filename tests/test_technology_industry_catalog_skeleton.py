from collections import defaultdict

from stock_research.technology_industry_catalog import load_industry_catalog


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


def test_repository_catalog_matches_frozen_l2_registry():
    catalog = load_industry_catalog()
    chains_by_sector = defaultdict(list)
    for chain in catalog["chains"]:
        chains_by_sector[chain["sector_id"]].append(chain)

    actual_chains_by_sector = {
        sector_id: [
            chain["chain_id"]
            for chain in sorted(chains, key=lambda chain: (chain["order"], chain["chain_id"]))
        ]
        for sector_id, chains in chains_by_sector.items()
    }
    actual_chain_ids = [
        chain_id
        for chain_ids in actual_chains_by_sector.values()
        for chain_id in chain_ids
    ]

    assert len(actual_chain_ids) == 82
    assert len(actual_chain_ids) == len(set(actual_chain_ids))
    assert set(actual_chains_by_sector) == set(EXPECTED_CHAINS_BY_SECTOR)
    assert actual_chains_by_sector == EXPECTED_CHAINS_BY_SECTOR
