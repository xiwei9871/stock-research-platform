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

HUMANOID_SECTOR_ID = "high_end_equipment_intelligent_manufacturing"
HUMANOID_CHAIN_ID = "humanoid_robots_embodied_intelligence"
BATTERY_SECTOR_ID = "energy_technology_new_power_system"
BATTERY_CHAIN_ID = "power_batteries_battery_materials"
BATTERY_L3_ID = "battery_cell_and_management_systems"

HUMANOID_EXPECTED_CHILDREN = {
    "humanoid_embodied_ai_brain": [
        "multimodal_perception_model",
        "vision_language_action_model",
        "task_understanding_planning",
        "long_term_memory_world_model",
        "autonomous_decision_exception_handling",
        "human_robot_interaction_model",
        "edge_cloud_inference",
    ],
    "humanoid_motion_control_cerebellum": [
        "whole_body_control",
        "biped_gait_control",
        "arm_motion_planning",
        "dexterous_hand_control",
        "force_position_hybrid_control",
        "model_predictive_control",
        "reinforcement_learning_motion_policy",
        "realtime_motion_control_system",
    ],
    "humanoid_data_training_simulation": [
        "teleoperation_motion_capture",
        "embodied_training_dataset",
        "robot_data_clean_label_replay",
        "robot_simulation",
        "digital_twin",
        "synthetic_robot_data",
        "sim_to_real",
        "robot_training_evaluation_toolchain",
    ],
    "humanoid_perception": [
        "rgb_vision_module",
        "depth_camera",
        "lidar_sensor",
        "imu_sensor",
        "joint_encoder",
        "joint_torque_sensor",
        "six_axis_force_sensor",
        "tactile_sensor",
        "microphone_array",
        "robot_state_sensor",
    ],
    "humanoid_compute_control_hardware": [
        "robot_ai_compute_chip",
        "robot_ai_compute_module",
        "main_controller",
        "motion_controller",
        "realtime_mcu",
        "motor_driver",
        "sensor_signal_conditioning",
        "realtime_communication_bus",
    ],
    "humanoid_rotary_actuation": [
        "rotary_joint_assembly",
        "frameless_torque_motor",
        "harmonic_reducer",
        "rv_reducer",
        "precision_planetary_reducer",
        "joint_encoder_module",
        "joint_brake",
        "joint_bearing",
    ],
    "humanoid_linear_actuation": [
        "linear_joint_assembly",
        "planetary_roller_screw",
        "ball_screw",
        "trapezoidal_screw",
        "linear_motor",
        "screw_support_bearing",
        "linear_displacement_sensor",
    ],
    "humanoid_upper_limb_dexterous_hand": [
        "shoulder_joint_module",
        "elbow_joint_module",
        "wrist_joint_module",
        "humanoid_robotic_arm",
        "dexterous_hand_assembly",
        "finger_micro_actuator",
        "micro_reducer_transmission",
        "tendon_flexible_transmission",
        "fingertip_tactile_force_control",
    ],
    "humanoid_lower_limb_locomotion": [
        "hip_joint_module",
        "knee_joint_module",
        "ankle_joint_module",
        "leg_structure",
        "foot_buffer_structure",
        "foot_force_pressure_sensing",
        "dynamic_balance_safety_mechanism",
    ],
    "humanoid_body_structure_lightweighting": [
        "torso_load_bearing_structure",
        "lightweight_skeleton",
        "aluminum_magnesium_structure",
        "carbon_fiber_structure",
        "precision_cast_machined_parts",
        "robot_wiring_harness",
        "protective_shell_soft_cover",
        "robot_sealing_protection",
    ],
    "humanoid_energy_thermal_management": [
        "robot_battery_pack",
        "high_specific_energy_cell",
        "battery_management_system",
        "robot_power_management_dcdc",
        "autonomous_charging",
        "robot_thermal_management",
        "robot_power_budget_control",
        "emergency_power_cutoff",
    ],
    "humanoid_manufacturing_test_integration": [
        "humanoid_robot_complete_unit",
        "joint_module_assembly",
        "whole_robot_calibration",
        "motion_performance_test",
        "robot_reliability_test",
        "robot_safety_test",
        "robot_remote_operations",
        "industrial_scenario_integration",
        "service_scenario_integration",
    ],
}

HUMANOID_EXPECTED_L4_NODE_TYPES = {
    "multimodal_perception_model": "ai_model",
    "vision_language_action_model": "ai_model",
    "task_understanding_planning": "ai_model",
    "long_term_memory_world_model": "ai_model",
    "autonomous_decision_exception_handling": "control_software",
    "human_robot_interaction_model": "ai_model",
    "edge_cloud_inference": "inference_system",
    "whole_body_control": "motion_control_software",
    "biped_gait_control": "motion_control_software",
    "arm_motion_planning": "motion_control_software",
    "dexterous_hand_control": "motion_control_software",
    "force_position_hybrid_control": "motion_control_software",
    "model_predictive_control": "motion_control_software",
    "reinforcement_learning_motion_policy": "motion_control_model",
    "realtime_motion_control_system": "realtime_control_software",
    "teleoperation_motion_capture": "data_acquisition_system",
    "embodied_training_dataset": "dataset",
    "robot_data_clean_label_replay": "data_toolchain",
    "robot_simulation": "simulation_software",
    "digital_twin": "simulation_software",
    "synthetic_robot_data": "dataset",
    "sim_to_real": "training_method",
    "robot_training_evaluation_toolchain": "software_toolchain",
    "rgb_vision_module": "sensor_module",
    "depth_camera": "sensor",
    "lidar_sensor": "sensor",
    "imu_sensor": "sensor",
    "joint_encoder": "sensor",
    "joint_torque_sensor": "sensor",
    "six_axis_force_sensor": "sensor",
    "tactile_sensor": "sensor",
    "microphone_array": "sensor_module",
    "robot_state_sensor": "sensor",
    "robot_ai_compute_chip": "compute_component",
    "robot_ai_compute_module": "compute_module",
    "main_controller": "controller",
    "motion_controller": "controller",
    "realtime_mcu": "control_component",
    "motor_driver": "power_electronics_component",
    "sensor_signal_conditioning": "electronic_subsystem",
    "realtime_communication_bus": "communication_subsystem",
    "rotary_joint_assembly": "actuation_assembly",
    "frameless_torque_motor": "actuation_component",
    "harmonic_reducer": "transmission_component",
    "rv_reducer": "transmission_component",
    "precision_planetary_reducer": "transmission_component",
    "joint_encoder_module": "sensor_module",
    "joint_brake": "safety_component",
    "joint_bearing": "mechanical_component",
    "linear_joint_assembly": "actuation_assembly",
    "planetary_roller_screw": "transmission_component",
    "ball_screw": "transmission_component",
    "trapezoidal_screw": "transmission_component",
    "linear_motor": "actuation_component",
    "screw_support_bearing": "mechanical_component",
    "linear_displacement_sensor": "sensor",
    "shoulder_joint_module": "body_joint_module",
    "elbow_joint_module": "body_joint_module",
    "wrist_joint_module": "body_joint_module",
    "humanoid_robotic_arm": "limb_assembly",
    "dexterous_hand_assembly": "end_effector_assembly",
    "finger_micro_actuator": "actuation_component",
    "micro_reducer_transmission": "transmission_component",
    "tendon_flexible_transmission": "transmission_component",
    "fingertip_tactile_force_control": "sensing_control_subsystem",
    "hip_joint_module": "body_joint_module",
    "knee_joint_module": "body_joint_module",
    "ankle_joint_module": "body_joint_module",
    "leg_structure": "limb_structure",
    "foot_buffer_structure": "mechanical_structure",
    "foot_force_pressure_sensing": "sensor_module",
    "dynamic_balance_safety_mechanism": "safety_subsystem",
    "torso_load_bearing_structure": "mechanical_structure",
    "lightweight_skeleton": "mechanical_structure",
    "aluminum_magnesium_structure": "structural_component",
    "carbon_fiber_structure": "structural_component",
    "precision_cast_machined_parts": "mechanical_component",
    "robot_wiring_harness": "electrical_component",
    "protective_shell_soft_cover": "protective_component",
    "robot_sealing_protection": "protective_subsystem",
    "robot_battery_pack": "energy_system",
    "high_specific_energy_cell": "energy_integration_requirement",
    "battery_management_system": "power_control_requirement",
    "robot_power_management_dcdc": "power_electronics_subsystem",
    "autonomous_charging": "charging_system",
    "robot_thermal_management": "thermal_management_system",
    "robot_power_budget_control": "power_control_software",
    "emergency_power_cutoff": "safety_subsystem",
    "humanoid_robot_complete_unit": "complete_robot",
    "joint_module_assembly": "manufacturing_process",
    "whole_robot_calibration": "manufacturing_process",
    "motion_performance_test": "test_process",
    "robot_reliability_test": "test_process",
    "robot_safety_test": "test_process",
    "robot_remote_operations": "operations_service",
    "industrial_scenario_integration": "integration_service",
    "service_scenario_integration": "integration_service",
}

HUMANOID_EXPECTED_L3_NODE_TYPES = {
    node_id: (
        "lifecycle_value_chain_family"
        if node_id == "humanoid_manufacturing_test_integration"
        else "system_architecture_family"
    )
    for node_id in HUMANOID_EXPECTED_CHILDREN
}

HUMANOID_EXPECTED_CANONICAL_REFS = {
    "high_specific_energy_cell": ["battery_high_specific_energy_cell"],
    "battery_management_system": ["battery_management_system_platform"],
}

HUMANOID_EXPECTED_EDGES = {
    ("rotary_joint_assembly", "frameless_torque_motor"),
    ("rotary_joint_assembly", "harmonic_reducer"),
    ("rotary_joint_assembly", "rv_reducer"),
    ("rotary_joint_assembly", "precision_planetary_reducer"),
    ("rotary_joint_assembly", "joint_encoder_module"),
    ("rotary_joint_assembly", "joint_brake"),
    ("rotary_joint_assembly", "joint_bearing"),
    ("linear_joint_assembly", "planetary_roller_screw"),
    ("linear_joint_assembly", "ball_screw"),
    ("linear_joint_assembly", "trapezoidal_screw"),
    ("linear_joint_assembly", "linear_motor"),
    ("linear_joint_assembly", "screw_support_bearing"),
    ("linear_joint_assembly", "linear_displacement_sensor"),
    ("shoulder_joint_module", "rotary_joint_assembly"),
    ("elbow_joint_module", "rotary_joint_assembly"),
    ("wrist_joint_module", "rotary_joint_assembly"),
    ("hip_joint_module", "rotary_joint_assembly"),
    ("hip_joint_module", "linear_joint_assembly"),
    ("knee_joint_module", "rotary_joint_assembly"),
    ("knee_joint_module", "linear_joint_assembly"),
    ("ankle_joint_module", "rotary_joint_assembly"),
    ("ankle_joint_module", "linear_joint_assembly"),
    ("dexterous_hand_assembly", "finger_micro_actuator"),
    ("dexterous_hand_assembly", "micro_reducer_transmission"),
    ("dexterous_hand_assembly", "tendon_flexible_transmission"),
    ("dexterous_hand_assembly", "fingertip_tactile_force_control"),
    ("robot_battery_pack", "battery_high_specific_energy_cell"),
    ("robot_battery_pack", "battery_management_system_platform"),
}

HUMANOID_ALTERNATIVE_ROUTE_EDGES = {
    ("rotary_joint_assembly", "harmonic_reducer"),
    ("rotary_joint_assembly", "rv_reducer"),
    ("rotary_joint_assembly", "precision_planetary_reducer"),
    ("linear_joint_assembly", "planetary_roller_screw"),
    ("linear_joint_assembly", "ball_screw"),
    ("linear_joint_assembly", "trapezoidal_screw"),
    ("linear_joint_assembly", "linear_motor"),
    ("hip_joint_module", "rotary_joint_assembly"),
    ("hip_joint_module", "linear_joint_assembly"),
    ("knee_joint_module", "rotary_joint_assembly"),
    ("knee_joint_module", "linear_joint_assembly"),
    ("ankle_joint_module", "rotary_joint_assembly"),
    ("ankle_joint_module", "linear_joint_assembly"),
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


def test_power_batteries_battery_materials_skeleton_metadata():
    catalog = load_industry_catalog()
    chain = next(
        row for row in catalog["chains"] if row["chain_id"] == BATTERY_CHAIN_ID
    )

    assert chain == {
        "chain_id": BATTERY_CHAIN_ID,
        "sector_id": BATTERY_SECTOR_ID,
        "chain_name": "Power Batteries and Battery Materials",
        "chain_kind": "canonical_industry_chain",
        "decomposition_method": "manufacturing_process",
        "description": (
            "Primary canonical ownership skeleton for power-battery cells, battery "
            "management platforms, pack and system integration, and battery materials "
            "across the manufacturing value chain."
        ),
        "scope": (
            "This skeleton establishes canonical ownership for generic high-specific-energy "
            "power-battery cells and battery management system platforms. Later expansion "
            "may add cell manufacturing, pack integration, recycling, and battery-material "
            "process families without changing application-chain ownership."
        ),
        "exclusions": [
            (
                "Humanoid-specific cell selection, BMS integration, robot battery packs, "
                "and robot power controls remain owned by "
                "humanoid_robots_embodied_intelligence."
            ),
            (
                "Stationary energy-storage systems and grid integration remain owned by "
                "their primary energy-storage and power-system chains."
            ),
            (
                "Vehicle-specific battery installation and vehicle energy management "
                "remain owned by intelligent-vehicle chains; generic battery products "
                "remain canonical here."
            ),
        ],
        "aliases": [
            "Power Battery Industry",
            "Traction Batteries and Materials",
            "动力电池与电池材料",
        ],
        "status": "skeleton",
        "order": 7,
    }


def test_power_batteries_battery_materials_skeleton_exact_taxonomy_and_ownership():
    catalog = load_industry_catalog()
    nodes = [row for row in catalog["nodes"] if row["chain_id"] == BATTERY_CHAIN_ID]

    assert [row["node_id"] for row in nodes] == [
        BATTERY_L3_ID,
        "battery_high_specific_energy_cell",
        "battery_management_system_platform",
    ]
    assert {row["node_id"]: row["node_type"] for row in nodes} == {
        BATTERY_L3_ID: "battery_system_family",
        "battery_high_specific_energy_cell": "battery_cell_product",
        "battery_management_system_platform": "battery_control_platform",
    }

    for node in nodes:
        assert set(node) == NODE_FIELDS
        assert node["node_kind"] == "canonical"
        assert node["status"] == "skeleton"
        assert node["canonical_node_refs"] == []
        assert node["description"]

    l3_node = nodes[0]
    assert l3_node["parent_node_id"] is None
    assert l3_node["canonical_key"] == ""
    assert l3_node["primary_path"] == [
        BATTERY_SECTOR_ID,
        BATTERY_CHAIN_ID,
        BATTERY_L3_ID,
    ]

    for node in nodes[1:]:
        assert node["parent_node_id"] == BATTERY_L3_ID
        assert node["level"] == "L4"
        assert node["canonical_key"] == f"battery_industry:{node['node_id']}"
        assert node["primary_path"] == [
            BATTERY_SECTOR_ID,
            BATTERY_CHAIN_ID,
            BATTERY_L3_ID,
            node["node_id"],
        ]

    assert nodes[1]["node_name"] == "High-Specific-Energy Power Battery Cells"
    assert nodes[1]["description"] == (
        "Canonical generic power-battery cell products optimized for high specific energy; "
        "owns cell technology and manufacturing independently of application-specific "
        "selection requirements."
    )
    assert nodes[2]["node_name"] == "Battery Management System Platforms"
    assert nodes[2]["description"] == (
        "Canonical generic battery management hardware and software platforms for state "
        "estimation, balancing, protection, charging, diagnostics, and system interfaces; "
        "application-specific integration requirements reference this node."
    )


def test_humanoid_robots_embodied_intelligence_chain_metadata():
    catalog = load_industry_catalog()
    chain = next(
        row for row in catalog["chains"] if row["chain_id"] == HUMANOID_CHAIN_ID
    )

    assert chain == {
        "chain_id": HUMANOID_CHAIN_ID,
        "sector_id": HUMANOID_SECTOR_ID,
        "chain_name": "Humanoid Robots and Embodied Intelligence",
        "chain_kind": "canonical_industry_chain",
        "decomposition_method": "system_architecture",
        "description": (
            "A primarily system-architecture decomposition of humanoid robots spanning "
            "embodied intelligence, control, sensing, compute, actuation, body, and energy "
            "subsystems, with one explicit supplementary lifecycle and value-chain family."
        ),
        "scope": (
            "Covers robot-specific models and software, integrated sensing and control "
            "modules, reusable electromechanical components, complete humanoid robots, "
            "and their manufacturing, test, operations, and scenario integration. Under "
            "the approved mixed-template rule, humanoid_manufacturing_test_integration "
            "supplements the primary system architecture with lifecycle coverage."
        ),
        "exclusions": [
            (
                "General-purpose AI foundation models remain owned by their primary AI "
                "chain; this chain covers robot-adapted embodied models and inference."
            ),
            (
                "General semiconductor chips remain owned by semiconductor chains; this "
                "chain covers robot-selected compute components and integrated modules."
            ),
            (
                "Generic battery cells, battery management systems, and battery materials "
                "remain owned by power_batteries_battery_materials; this chain covers "
                "humanoid-specific selection, integration, and control requirements."
            ),
            (
                "General industrial robots, machine tools, and factory automation remain "
                "owned by their primary equipment chains unless humanoid-specific."
            ),
        ],
        "aliases": [
            "Humanoid Robotics",
            "Embodied Intelligence Robots",
            "人形机器人与具身智能",
        ],
        "status": "draft",
        "order": 4,
    }


def test_humanoid_robots_embodied_intelligence_exact_taxonomy_and_contract():
    catalog = load_industry_catalog()
    nodes = [row for row in catalog["nodes"] if row["chain_id"] == HUMANOID_CHAIN_ID]
    l3_nodes = [row for row in nodes if row["level"] == "L3"]
    l4_nodes = [row for row in nodes if row["level"] == "L4"]

    assert len(l3_nodes) == 12
    assert len(l4_nodes) == 97
    assert [row["node_id"] for row in l3_nodes] == list(HUMANOID_EXPECTED_CHILDREN)
    assert {
        parent_id: [
            row["node_id"]
            for row in l4_nodes
            if row["parent_node_id"] == parent_id
        ]
        for parent_id in HUMANOID_EXPECTED_CHILDREN
    } == HUMANOID_EXPECTED_CHILDREN
    assert {row["node_id"]: row["node_type"] for row in l4_nodes} == (
        HUMANOID_EXPECTED_L4_NODE_TYPES
    )

    for node in nodes:
        assert set(node) == NODE_FIELDS
        assert node["node_kind"] == "canonical"
        assert node["status"] == "draft"
        assert node["canonical_node_refs"] == HUMANOID_EXPECTED_CANONICAL_REFS.get(
            node["node_id"], []
        )
        assert node["node_name"] != node["node_id"]
        assert node["description"]

    for node in l3_nodes:
        assert node["parent_node_id"] is None
        assert node["node_type"] == HUMANOID_EXPECTED_L3_NODE_TYPES[node["node_id"]]
        assert node["canonical_key"] == ""
        assert node["primary_path"] == [
            HUMANOID_SECTOR_ID,
            HUMANOID_CHAIN_ID,
            node["node_id"],
        ]

    for node in l4_nodes:
        assert node["canonical_key"] == f"humanoid_robotics:{node['node_id']}"
        assert node["primary_path"] == [
            HUMANOID_SECTOR_ID,
            HUMANOID_CHAIN_ID,
            node["parent_node_id"],
            node["node_id"],
        ]


def test_humanoid_robots_embodied_intelligence_exact_uses_edges():
    catalog = load_industry_catalog()
    humanoid_node_ids = {
        row["node_id"]
        for row in catalog["nodes"]
        if row["chain_id"] == HUMANOID_CHAIN_ID
    }
    edges = [
        row
        for row in catalog["edges"]
        if row["source_node_id"] in humanoid_node_ids
        or row["target_node_id"] in humanoid_node_ids
    ]

    edge_tuples = [
        (row["source_node_id"], row["target_node_id"]) for row in edges
    ]

    assert len(edges) == 28
    assert len({row["edge_id"] for row in edges}) == 28
    assert len(edge_tuples) == len(set(edge_tuples))
    assert all(
        source_node_id != target_node_id
        for source_node_id, target_node_id in edge_tuples
    )
    assert set(edge_tuples) == HUMANOID_EXPECTED_EDGES
    edges_by_tuple = {
        (row["source_node_id"], row["target_node_id"]): row for row in edges
    }
    for edge in edges:
        assert edge["relationship_type"] == "uses"
        assert edge["notes"]
        assert edge["source_ids"] == []
        edge_tuple = (edge["source_node_id"], edge["target_node_id"])
        if edge_tuple in HUMANOID_ALTERNATIVE_ROUTE_EDGES:
            assert "eligible" in edge["notes"].lower()
            assert "route" in edge["notes"].lower()

    for edge_tuple in (
        ("robot_battery_pack", "battery_high_specific_energy_cell"),
        ("robot_battery_pack", "battery_management_system_platform"),
    ):
        assert "eligible" in edges_by_tuple[edge_tuple]["notes"].lower()
        assert "primary canonical" in edges_by_tuple[edge_tuple]["notes"].lower()


def test_humanoid_robots_embodied_intelligence_representative_nodes_are_research_usable():
    catalog = load_industry_catalog()
    nodes = {
        row["node_id"]: row
        for row in catalog["nodes"]
        if row["chain_id"] == HUMANOID_CHAIN_ID
    }

    assert nodes["humanoid_embodied_ai_brain"]["node_name"] == (
        "Embodied AI Brain"
    )
    assert nodes["vision_language_action_model"]["description"] == (
        "Robot-adapted vision-language-action models that map multimodal observations "
        "and instructions to executable action representations; general foundation "
        "models remain owned by the primary AI chain."
    )
    assert nodes["robot_ai_compute_chip"]["description"] == (
        "Processors selected and configured for onboard robot AI workloads; the generic "
        "chip categories remain owned by semiconductor chains."
    )
    assert nodes["rotary_joint_assembly"]["description"] == (
        "Integrated rotary actuation assembly combining selected reusable motor, "
        "transmission, feedback, braking, and bearing components for humanoid joint "
        "modules."
    )
    assert nodes["shoulder_joint_module"]["description"] == (
        "Shoulder-specific kinematic module that integrates shared rotary joint "
        "assemblies into the humanoid upper limb."
    )
    assert nodes["frameless_torque_motor"]["description"] == (
        "Reusable frameless high-torque motor component for compact robot actuation, "
        "not duplicated by body location."
    )
    assert nodes["high_specific_energy_cell"]["node_name"] == (
        "Humanoid High-Specific-Energy Cell Selection"
    )
    assert nodes["high_specific_energy_cell"]["description"] == (
        "Humanoid-specific cell selection and integration requirements for runtime, "
        "mass, packaging, discharge, and safety; generic cell chemistry and manufacturing "
        "remain owned by power_batteries_battery_materials."
    )
    assert nodes["high_specific_energy_cell"]["canonical_key"] == (
        "humanoid_robotics:high_specific_energy_cell"
    )
    assert nodes["high_specific_energy_cell"]["canonical_node_refs"] == [
        "battery_high_specific_energy_cell"
    ]
    assert nodes["battery_management_system"]["node_name"] == (
        "Humanoid Battery Management Integration and Control"
    )
    assert nodes["battery_management_system"]["description"] == (
        "Humanoid-specific BMS integration, interfaces, limits, state estimation, and "
        "fault-control requirements; generic BMS products and technology remain owned by "
        "power_batteries_battery_materials."
    )
    assert nodes["battery_management_system"]["canonical_key"] == (
        "humanoid_robotics:battery_management_system"
    )
    assert nodes["battery_management_system"]["canonical_node_refs"] == [
        "battery_management_system_platform"
    ]
    assert nodes["robot_state_sensor"]["node_name"] == (
        "Residual Robot Operating-State Sensors"
    )
    assert nodes["robot_state_sensor"]["description"] == (
        "Residual sensors for internal robot operating states such as limits, temperature, "
        "current, or discrete health signals; excludes IMUs, joint encoders, force-torque, "
        "tactile, vision, and every other enumerated sensor node."
    )
    assert nodes["humanoid_manufacturing_test_integration"]["node_type"] == (
        "lifecycle_value_chain_family"
    )
    assert nodes["humanoid_manufacturing_test_integration"]["description"] == (
        "Supplementary lifecycle and value-chain coverage for complete humanoid products, "
        "manufacturing, calibration, testing, operations, and scenario integration under "
        "the approved mixed-template rule."
    )
    assert nodes["hip_joint_module"]["description"] == (
        "Hip-specific kinematic module that can integrate eligible rotary or linear joint "
        "assembly routes according to the humanoid architecture."
    )
