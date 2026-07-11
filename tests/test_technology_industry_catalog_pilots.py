from stock_research.technology_industry_catalog import NODE_FIELDS, load_industry_catalog


SECTOR_ID = "semiconductor_electronics"
CHAIN_ID = "semiconductor_manufacturing_equipment"

EXPECTED_CHILDREN = {
    "semiconductor_lithography_patterning": [
        "iline_lithography",
        "krf_lithography",
        "arf_dry_lithography",
        "arf_immersion_lithography",
        "euv_lithography",
        "coat_develop_track",
        "electron_beam_direct_write",
        "photomask_writer",
        "photomask_inspection_repair",
    ],
    "semiconductor_etch": [
        "dielectric_etch",
        "conductor_etch",
        "silicon_etch",
        "deep_silicon_etch",
        "atomic_layer_etch",
        "wet_etch",
        "photoresist_strip_residue_removal",
    ],
    "semiconductor_deposition_epitaxy": [
        "pvd_equipment",
        "cvd_equipment",
        "pecvd_equipment",
        "lpcvd_equipment",
        "atomic_layer_deposition",
        "electrochemical_deposition",
        "silicon_epitaxy",
        "compound_semiconductor_epitaxy",
    ],
    "semiconductor_thermal_doping": [
        "oxidation_furnace",
        "diffusion_furnace",
        "rapid_thermal_processing",
        "laser_annealing",
        "ion_implantation",
        "dopant_activation_equipment",
    ],
    "semiconductor_clean_wet_process": [
        "single_wafer_clean",
        "batch_wet_clean",
        "supercritical_clean_dry",
        "wafer_brush_clean",
        "wet_chemical_processing",
    ],
    "semiconductor_cmp_planarization": [
        "cmp_equipment",
        "wafer_thinning",
        "cmp_post_clean",
        "cmp_endpoint_control",
    ],
    "semiconductor_metrology_process_control": [
        "wafer_defect_inspection",
        "pattern_defect_inspection",
        "electron_beam_inspection",
        "critical_dimension_metrology",
        "overlay_metrology",
        "film_material_metrology",
        "optical_scatterometry",
        "photomask_inspection",
        "yield_process_control_software",
    ],
    "semiconductor_wafer_handling_automation": [
        "equipment_front_end_module",
        "wafer_transfer_robot",
        "foup_wafer_carrier",
        "amhs_system",
        "wafer_tracking_mes_interface",
        "cleanroom_automation_control",
    ],
    "semiconductor_vacuum_gas_fluid_control": [
        "dry_vacuum_pump",
        "molecular_high_vacuum_pump",
        "vacuum_valve",
        "mass_flow_controller",
        "specialty_gas_delivery",
        "ultrapure_chemical_delivery",
        "rf_power_matching",
        "plasma_generator",
    ],
    "semiconductor_facility_pollution_control": [
        "exhaust_gas_treatment",
        "waste_liquid_treatment",
        "ultrapure_water_system",
        "cleanroom_system",
        "temperature_humidity_microenvironment",
        "process_cooling_system",
        "facility_monitoring_control",
    ],
}

EXPECTED_L4_NODE_TYPES = {
    "iline_lithography": "equipment",
    "krf_lithography": "equipment",
    "arf_dry_lithography": "equipment",
    "arf_immersion_lithography": "equipment",
    "euv_lithography": "equipment",
    "coat_develop_track": "equipment",
    "electron_beam_direct_write": "equipment",
    "photomask_writer": "equipment",
    "photomask_inspection_repair": "equipment",
    "dielectric_etch": "equipment",
    "conductor_etch": "equipment",
    "silicon_etch": "equipment",
    "deep_silicon_etch": "equipment",
    "atomic_layer_etch": "equipment",
    "wet_etch": "equipment",
    "photoresist_strip_residue_removal": "equipment",
    "pvd_equipment": "equipment",
    "cvd_equipment": "equipment",
    "pecvd_equipment": "equipment",
    "lpcvd_equipment": "equipment",
    "atomic_layer_deposition": "equipment",
    "electrochemical_deposition": "equipment",
    "silicon_epitaxy": "equipment",
    "compound_semiconductor_epitaxy": "equipment",
    "oxidation_furnace": "equipment",
    "diffusion_furnace": "equipment",
    "rapid_thermal_processing": "equipment",
    "laser_annealing": "equipment",
    "ion_implantation": "equipment",
    "dopant_activation_equipment": "equipment",
    "single_wafer_clean": "equipment",
    "batch_wet_clean": "equipment",
    "supercritical_clean_dry": "equipment",
    "wafer_brush_clean": "equipment",
    "wet_chemical_processing": "equipment",
    "cmp_equipment": "equipment",
    "wafer_thinning": "equipment",
    "cmp_post_clean": "equipment",
    "cmp_endpoint_control": "equipment_subsystem",
    "wafer_defect_inspection": "equipment",
    "pattern_defect_inspection": "equipment",
    "electron_beam_inspection": "equipment",
    "critical_dimension_metrology": "equipment",
    "overlay_metrology": "equipment",
    "film_material_metrology": "equipment",
    "optical_scatterometry": "equipment",
    "photomask_inspection": "equipment",
    "yield_process_control_software": "process_control_software",
    "equipment_front_end_module": "equipment_subsystem",
    "wafer_transfer_robot": "equipment_subsystem",
    "foup_wafer_carrier": "equipment_subsystem",
    "amhs_system": "factory_system",
    "wafer_tracking_mes_interface": "process_control_software",
    "cleanroom_automation_control": "factory_system",
    "dry_vacuum_pump": "equipment_subsystem",
    "molecular_high_vacuum_pump": "equipment_subsystem",
    "vacuum_valve": "equipment_subsystem",
    "mass_flow_controller": "equipment_subsystem",
    "specialty_gas_delivery": "factory_system",
    "ultrapure_chemical_delivery": "factory_system",
    "rf_power_matching": "equipment_subsystem",
    "plasma_generator": "equipment_subsystem",
    "exhaust_gas_treatment": "factory_system",
    "waste_liquid_treatment": "factory_system",
    "ultrapure_water_system": "factory_system",
    "cleanroom_system": "factory_system",
    "temperature_humidity_microenvironment": "factory_system",
    "process_cooling_system": "factory_system",
    "facility_monitoring_control": "factory_system",
}


def test_semiconductor_manufacturing_equipment_chain_metadata():
    catalog = load_industry_catalog()
    chain = next(row for row in catalog["chains"] if row["chain_id"] == CHAIN_ID)

    assert chain == {
        "chain_id": CHAIN_ID,
        "sector_id": SECTOR_ID,
        "chain_name": "Semiconductor Manufacturing Equipment",
        "chain_kind": "canonical_industry_chain",
        "decomposition_method": "manufacturing_process",
        "description": (
            "Equipment and factory systems used to execute, control, and support "
            "front-end semiconductor wafer manufacturing."
        ),
        "scope": (
            "Covers wafer-fabrication process equipment, inspection and metrology, "
            "wafer automation, vacuum and process delivery, and fab utility systems."
        ),
        "exclusions": [
            "Semiconductor materials are owned by the semiconductor materials chain.",
            (
                "Semiconductor packaging and test equipment are owned by the packaging "
                "and test chain, except wafer_thinning is temporarily canonical here "
                "and may be referenced by advanced packaging."
            ),
        ],
        "aliases": [
            "Semiconductor Equipment",
            "Wafer Fab Equipment",
            "半导体制造设备",
        ],
        "status": "draft",
        "order": 8,
    }


def test_semiconductor_manufacturing_equipment_exact_taxonomy_and_contract():
    catalog = load_industry_catalog()
    nodes = [row for row in catalog["nodes"] if row["chain_id"] == CHAIN_ID]
    l3_nodes = [row for row in nodes if row["level"] == "L3"]
    l4_nodes = [row for row in nodes if row["level"] == "L4"]

    assert len(l3_nodes) == 10
    assert len(l4_nodes) == 69
    assert [row["node_id"] for row in l3_nodes] == list(EXPECTED_CHILDREN)
    assert {
        parent_id: [
            row["node_id"]
            for row in l4_nodes
            if row["parent_node_id"] == parent_id
        ]
        for parent_id in EXPECTED_CHILDREN
    } == EXPECTED_CHILDREN
    assert {row["node_id"]: row["node_type"] for row in l4_nodes} == (
        EXPECTED_L4_NODE_TYPES
    )

    for node in nodes:
        assert set(node) == NODE_FIELDS
        assert node["node_kind"] == "canonical"
        assert node["status"] == "draft"
        assert node["canonical_node_refs"] == []
        assert node["node_name"] != node["node_id"]
        assert node["description"]

    for node in l3_nodes:
        assert node["parent_node_id"] is None
        assert node["node_type"] == "manufacturing_process_family"
        assert node["canonical_key"] == ""
        assert node["primary_path"] == [SECTOR_ID, CHAIN_ID, node["node_id"]]

    for node in l4_nodes:
        assert node["canonical_key"] == f"semiconductor_equipment:{node['node_id']}"
        assert node["primary_path"] == [
            SECTOR_ID,
            CHAIN_ID,
            node["parent_node_id"],
            node["node_id"],
        ]


def test_semiconductor_manufacturing_equipment_representative_nodes_are_research_usable():
    catalog = load_industry_catalog()
    nodes = {
        row["node_id"]: row
        for row in catalog["nodes"]
        if row["chain_id"] == CHAIN_ID
    }

    assert nodes["semiconductor_lithography_patterning"]["node_name"] == (
        "Lithography and Patterning"
    )
    assert nodes["euv_lithography"]["node_name"] == "EUV Lithography Equipment"
    assert nodes["euv_lithography"]["description"] == (
        "Extreme-ultraviolet exposure systems for advanced-node patterning."
    )
    assert nodes["mass_flow_controller"]["node_name"] == "Mass Flow Controllers"
    assert nodes["photomask_inspection_repair"]["node_name"] == (
        "Photomask Repair Equipment"
    )
    assert nodes["photomask_inspection_repair"]["description"] == (
        "Repair systems for correcting defects on semiconductor photomasks; "
        "photomask inspection is owned by photomask_inspection under metrology."
    )
    assert nodes["cvd_equipment"]["node_name"] == "General Thermal CVD Equipment"
    assert nodes["cvd_equipment"]["description"] == (
        "General thermal CVD systems for routes not represented by PECVD, LPCVD, "
        "ALD, or other separately enumerated deposition nodes."
    )
    assert nodes["wafer_defect_inspection"]["node_name"] == (
        "Bare-Wafer Defect Inspection Equipment"
    )
    assert nodes["wafer_defect_inspection"]["description"] == (
        "Optical inspection systems for particles and defects on unpatterned or bare "
        "wafers; patterned-wafer inspection is owned by pattern_defect_inspection."
    )
    assert nodes["wafer_thinning"]["description"] == (
        "Grinding and polishing systems that reduce wafer thickness; temporarily owned "
        "here as the canonical node and referenced by advanced packaging."
    )
    assert nodes["molecular_high_vacuum_pump"]["node_name"] == (
        "Turbomolecular High-Vacuum Pumps"
    )
    assert nodes["molecular_high_vacuum_pump"]["description"] == (
        "Turbomolecular pumps that generate high and ultra-high vacuum conditions in "
        "semiconductor process equipment."
    )
    assert nodes["yield_process_control_software"]["description"] == (
        "Software that analyzes fab data to monitor yield and control process excursions."
    )
    assert nodes["ultrapure_water_system"]["node_name"] == "Ultrapure Water Systems"
