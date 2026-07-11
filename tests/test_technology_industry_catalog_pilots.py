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
            "Semiconductor packaging and test equipment are owned by the packaging and test chain.",
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
        assert node["node_type"] in {
            "equipment",
            "equipment_subsystem",
            "factory_system",
            "process_control_software",
        }
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
    assert nodes["yield_process_control_software"]["description"] == (
        "Software that analyzes fab data to monitor yield and control process excursions."
    )
    assert nodes["ultrapure_water_system"]["node_name"] == "Ultrapure Water Systems"
