# Technology Industry Catalog Wave 2 Pilot Trees Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three validated pilot trees for semiconductor manufacturing equipment, humanoid robots, and AI data-center power, including read-only links to the existing AI power and humanoid Theme Research artifacts.

**Architecture:** Canonical pilots own their L4 nodes. AI power is an application chain whose role nodes reference canonical nodes, so company mappings and evidence are never copied. Existing Theme Research artifacts remain unchanged; explicit link artifacts provide catalog projection while preserving review states.

**Tech Stack:** JSON artifacts, Python standard library, Wave 1 catalog loader, existing Theme Decomposition loader, pytest.

---

## File Structure

- Modify `artifacts/technology_industry_catalog/v1/chains.json`: pilot and supporting canonical chains.
- Create `artifacts/technology_industry_catalog/v1/nodes/semiconductor_manufacturing_equipment_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/nodes/humanoid_robots_embodied_intelligence_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/nodes/ai_data_center_power_v1.json`.
- Modify `artifacts/technology_industry_catalog/v1/edges.json`: typed pilot relationships.
- Create `artifacts/technology_industry_catalog/v1/theme_compositions/ai_data_center_power_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/theme_links.json`.
- Modify `artifacts/technology_industry_catalog/v1/manifest.json`.
- Modify `src/stock_research/technology_industry_catalog.py`: theme-link loading and projection.
- Create `tests/test_technology_industry_catalog_pilots.py`.

### Task 1: Add the semiconductor-equipment canonical pilot

**Files:**
- Modify: `artifacts/technology_industry_catalog/v1/chains.json`
- Create: `artifacts/technology_industry_catalog/v1/nodes/semiconductor_manufacturing_equipment_v1.json`
- Create: `tests/test_technology_industry_catalog_pilots.py`

- [ ] **Step 1: Write the failing tree-shape test**

```python
SEMICONDUCTOR_L3_IDS = [
    "semiconductor_lithography_patterning",
    "semiconductor_etch",
    "semiconductor_deposition_epitaxy",
    "semiconductor_thermal_doping",
    "semiconductor_clean_wet_process",
    "semiconductor_cmp_planarization",
    "semiconductor_metrology_process_control",
    "semiconductor_wafer_handling_automation",
    "semiconductor_vacuum_gas_fluid_control",
    "semiconductor_facility_pollution_control",
]

SEMICONDUCTOR_REQUIRED_L4 = {
    "iline_lithography", "krf_lithography", "arf_dry_lithography",
    "arf_immersion_lithography", "euv_lithography", "coat_develop_track",
    "dielectric_etch", "conductor_etch", "silicon_etch", "deep_silicon_etch",
    "atomic_layer_etch", "pvd_equipment", "cvd_equipment", "pecvd_equipment",
    "lpcvd_equipment", "atomic_layer_deposition", "silicon_epitaxy",
    "compound_semiconductor_epitaxy", "oxidation_furnace", "diffusion_furnace",
    "rapid_thermal_processing", "laser_annealing", "ion_implantation",
    "single_wafer_clean", "batch_wet_clean", "cmp_equipment",
    "wafer_defect_inspection", "critical_dimension_metrology",
    "overlay_metrology", "electron_beam_inspection", "wafer_transfer_robot",
    "amhs_system", "dry_vacuum_pump", "mass_flow_controller",
    "rf_power_matching", "exhaust_gas_treatment", "ultrapure_water_system",
}
```

Assert exact L3 order and the exact 69-node child contract in Appendix A.

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog_pilots.py::test_semiconductor_equipment_pilot_shape -q
```

Expected: `CHAIN_NOT_FOUND`.

- [ ] **Step 3: Add the chain and complete node artifact**

Use:

```json
{
  "chain_id": "semiconductor_manufacturing_equipment",
  "sector_id": "semiconductor_electronics",
  "chain_name": "Semiconductor Manufacturing Equipment",
  "chain_kind": "canonical_industry_chain",
  "decomposition_method": "manufacturing_process",
  "status": "draft"
}
```

Create all ten L3 groups and the exact Appendix A L4 set. Prefix canonical keys with `semiconductor_equipment:`. Keep materials and packaging/test equipment out of this tree and name them in `exclusions`.

- [ ] **Step 4: Validate and test**

```bash
.venv/bin/python -m stock_research.cli technology-industry-catalog validate
.venv/bin/pytest tests/test_technology_industry_catalog_pilots.py -q
```

Expected: validation succeeds and semiconductor tests pass.

- [ ] **Step 5: Commit**

```bash
git add artifacts/technology_industry_catalog/v1/chains.json artifacts/technology_industry_catalog/v1/nodes/semiconductor_manufacturing_equipment_v1.json tests/test_technology_industry_catalog_pilots.py
git commit -m "data: add semiconductor equipment catalog pilot"
```

### Task 2: Add the humanoid canonical pilot

**Files:**
- Modify: `artifacts/technology_industry_catalog/v1/chains.json`
- Create: `artifacts/technology_industry_catalog/v1/nodes/humanoid_robots_embodied_intelligence_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/edges.json`
- Modify: `tests/test_technology_industry_catalog_pilots.py`

- [ ] **Step 1: Write the failing humanoid test**

```python
HUMANOID_L3_IDS = [
    "humanoid_embodied_ai_brain",
    "humanoid_motion_control_cerebellum",
    "humanoid_data_training_simulation",
    "humanoid_perception",
    "humanoid_compute_control_hardware",
    "humanoid_rotary_actuation",
    "humanoid_linear_actuation",
    "humanoid_upper_limb_dexterous_hand",
    "humanoid_lower_limb_locomotion",
    "humanoid_body_structure_lightweighting",
    "humanoid_energy_thermal_management",
    "humanoid_manufacturing_test_integration",
]

HUMANOID_REQUIRED_L4 = {
    "vision_language_action_model", "task_planning", "whole_body_control",
    "biped_gait_control", "force_position_hybrid_control", "robot_simulation",
    "synthetic_robot_data", "sim_to_real", "rgb_vision_module",
    "depth_camera", "imu_sensor", "joint_encoder", "joint_torque_sensor",
    "six_axis_force_sensor", "tactile_sensor", "robot_ai_compute_module",
    "motion_controller", "motor_driver", "rotary_joint_assembly",
    "frameless_torque_motor", "harmonic_reducer", "rv_reducer",
    "precision_planetary_reducer", "linear_joint_assembly",
    "planetary_roller_screw", "ball_screw", "dexterous_hand_assembly",
    "finger_micro_actuator", "hip_joint_module", "knee_joint_module",
    "ankle_joint_module", "lightweight_skeleton", "robot_battery_pack",
    "battery_management_system", "robot_thermal_management",
    "whole_robot_calibration", "robot_reliability_test",
}
```

Assert exact L3 order and the exact 97-node child contract in Appendix A.

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog_pilots.py -q
```

Expected: humanoid chain not found.

- [ ] **Step 3: Add canonical nodes and typed use relationships**

Use chain kind `canonical_industry_chain`, method `system_architecture`, status `draft`, and canonical-key prefix `humanoid_robotics:`.

Add `uses` edges from joint modules to motors, reducers, screws, encoders, and bearings. Keep body-location modules separate from reusable components; do not duplicate a motor or reducer under each joint.

- [ ] **Step 4: Validate and test**

```bash
.venv/bin/python -m stock_research.cli technology-industry-catalog validate
.venv/bin/pytest tests/test_technology_industry_catalog_pilots.py -q
```

Expected: all tests pass and no duplicate canonical ownership is reported.

- [ ] **Step 5: Commit**

```bash
git add artifacts/technology_industry_catalog/v1/chains.json artifacts/technology_industry_catalog/v1/nodes/humanoid_robots_embodied_intelligence_v1.json artifacts/technology_industry_catalog/v1/edges.json tests/test_technology_industry_catalog_pilots.py
git commit -m "data: add humanoid robotics catalog pilot"
```

### Task 3: Add AI data-center power as an application chain

**Files:**
- Modify: `artifacts/technology_industry_catalog/v1/chains.json`
- Create: `artifacts/technology_industry_catalog/v1/nodes/ai_data_center_power_v1.json`
- Create: `artifacts/technology_industry_catalog/v1/theme_compositions/ai_data_center_power_v1.json`
- Modify: `tests/test_technology_industry_catalog_pilots.py`

- [ ] **Step 1: Write failing application-chain tests**

```python
AI_POWER_L3_IDS = [
    "ai_power_load_capacity_planning",
    "ai_power_energy_supply_resilience",
    "ai_power_grid_access_substation",
    "ai_power_backup_power",
    "ai_power_ups_conversion",
    "ai_power_hvdc_dc_architecture",
    "ai_power_room_rack_distribution",
    "ai_power_server_board_power",
    "ai_power_liquid_cooling_thermal",
    "ai_power_energy_management_software",
    "ai_power_design_epc_operations",
]

AI_POWER_REQUIRED_ROLES = {
    "ai_power_transformer_role", "ai_power_switchgear_role",
    "ai_power_modular_ups_role", "ai_power_800vdc_role",
    "ai_power_busway_role", "ai_power_server_psu_role",
    "ai_power_sic_role", "ai_power_gan_role",
    "ai_power_cold_plate_role", "ai_power_cdu_role",
    "ai_power_dcim_role", "ai_power_data_center_epc_role",
}
```

Assert the exact 80 application-role nodes in Appendix A. Every L4 role has `node_kind == "application_role"`, empty `canonical_key`, and non-empty `canonical_node_refs`. The load/capacity-planning L3 intentionally has no L4 product node because its entries are metrics rather than canonical products. Assert the composition has no company mappings.

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog_pilots.py -q
```

Expected: AI power chain not found.

- [ ] **Step 3: Add resolved canonical reference stubs**

Use only final approved L2 IDs for supporting canonical ownership. Add minimal skeleton L3/L4 targets as follows:

| Canonical L4 target | Owning L2 chain |
|---|---|
| power transformer, switchgear, relay protection | `new_power_system_smart_grid` |
| modular UPS, server PSU, rectifier, inverter | `power_electronics_power_supply_equipment` |
| SiC and GaN power devices | `power_semiconductors` |
| copper busway, cable, high-current connector | `pcb_passives_connectors_interconnect` |
| cold plate, CDU, chiller, DCIM, data-center EPC | `cloud_data_center_infrastructure` |

Each target is a canonical L4 node with one primary path and `status: skeleton`. Do not add scores, companies, or evidence.

Create one resolved canonical target for every Appendix A application role, using these ownership rules:

- energy supply, generation, microgrid, and backup-generation targets: `power_generation_energy_equipment`;
- transformers, switchgear, substations, relay protection, power quality, DC breakers, and grid connection: `new_power_system_smart_grid`;
- UPS, rectifier/inverter, HVDC, DC bus, PDU, power shelf, server PSU, AC-DC, DC-DC, VRM, and power-control targets: `power_electronics_power_supply_equipment`;
- battery and flywheel backup targets: `new_energy_storage`;
- fuel-cell backup: `hydrogen_fuel_cells`;
- MOSFET, SiC, and GaN targets: `power_semiconductors`;
- cables, busbars, connectors, copper links, magnetics, and capacitors: `pcb_passives_connectors_interconnect`;
- cooling equipment, cooling integration, DCIM, modular data centers, commissioning, EPC, and facilities operations: `cloud_data_center_infrastructure`;
- EPMS and compute-energy scheduling software: `industrial_software`.

The composition artifact is the exact role-to-target map. Tests must assert that all 80 roles have at least one resolved target and that no target belongs to an application chain.

- [ ] **Step 4: Add application roles and compositions**

Use chain kind `application_theme_chain`, method `infrastructure_flow`, status `draft`. Composition rows use:

```json
{
  "composition_id": "ai_power_transformer_composition",
  "chain_id": "ai_data_center_power",
  "role_node_id": "ai_power_transformer_role",
  "canonical_node_refs": ["power_transformer"],
  "relationship_type": "depends_on",
  "notes": "Company mappings remain on the canonical transformer node."
}
```

- [ ] **Step 5: Validate and test**

```bash
.venv/bin/python -m stock_research.cli technology-industry-catalog validate
.venv/bin/pytest tests/test_technology_industry_catalog_pilots.py -q
```

Expected: all references resolve; tests pass.

- [ ] **Step 6: Commit**

```bash
git add artifacts/technology_industry_catalog/v1 tests/test_technology_industry_catalog_pilots.py
git commit -m "data: add ai data center power catalog pilot"
```

### Task 4: Link existing Theme Research artifacts without mutation

**Files:**
- Create: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `artifacts/technology_industry_catalog/v1/manifest.json`
- Modify: `src/stock_research/technology_industry_catalog.py`
- Modify: `tests/test_technology_industry_catalog_pilots.py`

- [ ] **Step 1: Write failing projection tests**

```python
def test_existing_theme_links_preserve_review_state():
    catalog = load_industry_catalog()

    ai_projection = project_theme_to_catalog(
        "ai_power_value_capture_v1", catalog=catalog
    )
    robot_projection = project_theme_to_catalog(
        "humanoid_robotics_head_to_toe_v1", catalog=catalog
    )

    assert ai_projection["chain_id"] == "ai_data_center_power"
    assert ai_projection["theme_status"] == "reviewed"
    assert robot_projection["chain_id"] == "humanoid_robots_embodied_intelligence"
    assert robot_projection["theme_status"] == "draft"
```

Also compare source artifact hashes before and after projection to prove no mutation.

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog_pilots.py -q
```

Expected: projection function missing.

- [ ] **Step 3: Add explicit theme links**

Add links for `ai_power_value_capture_v1` and `humanoid_robotics_head_to_toe_v1`. Each `node_links` row contains `theme_node_id` and `catalog_node_id`. Record all unmatched theme nodes under `unmapped_theme_node_ids`; never infer by fuzzy display-name matching.

- [ ] **Step 4: Implement read-only projection**

Add:

```python
def project_theme_to_catalog(
    theme_id: str,
    *,
    catalog: dict[str, Any] | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    ...
```

Load through `theme_decomposition.load_theme`, preserve theme and node review states, and return a new dictionary. Raise `THEME_CATALOG_LINK_NOT_FOUND`, `THEME_CATALOG_NODE_LINK_INVALID`, `THEME_LINK_INVALID` for malformed local links, or `THEME_ARTIFACT_INVALID` for theme dependency loading or shape failures.

- [ ] **Step 5: Run regression tests and commit**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog_pilots.py tests/test_theme_decomposition.py tests/test_theme_research_phase_verifier.py -q
git add artifacts/technology_industry_catalog/v1/theme_links.json artifacts/technology_industry_catalog/v1/manifest.json src/stock_research/technology_industry_catalog.py tests/test_technology_industry_catalog_pilots.py
git commit -m "feat: link theme research to industry catalog"
```

Expected: tests pass; AI power remains reviewed and humanoid remains draft.

### Task 5: Final Wave 2 verification

**Files:**
- Verify only.

- [ ] **Step 1: Run catalog commands**

```bash
.venv/bin/python -m stock_research.cli technology-industry-catalog validate
.venv/bin/python -m stock_research.cli technology-industry-catalog show --chain semiconductor_manufacturing_equipment
.venv/bin/python -m stock_research.cli technology-industry-catalog show --chain humanoid_robots_embodied_intelligence
.venv/bin/python -m stock_research.cli technology-industry-catalog show --chain ai_data_center_power
```

Expected: all exit 0; AI power reports `application_theme_chain`.

- [ ] **Step 2: Run focused regression tests**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py tests/test_technology_industry_catalog_pilots.py tests/test_theme_decomposition.py tests/test_decomposition_templates.py tests/test_theme_research_phase_verifier.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Verify no database writes**

```bash
rg -n "INSERT|UPDATE|DELETE|theme_research_store|apply_schema" src/stock_research/technology_industry_catalog.py
```

Expected: no database write or schema-migration calls.

### Final review validation codes

Application-role ownership is enforced with stable loader codes:

- `INVALID_PRIMARY_PATH`: an application-role L4 primary path is not exactly `[sector_id, chain_id, parent_node_id, node_id]`.
- `INVALID_CANONICAL_NODE_REFERENCE`: an application-role L4 has no canonical references, or a reference is not a canonical L4 node.
- `APPLICATION_ROLE_REQUIRES_COMPOSITION`: an application-role L4 has no composition. Application L3 nodes do not require one.
- `DUPLICATE_ROLE_COMPOSITION`: more than one composition claims the same application-role L4.
- `COMPOSITION_REFERENCE_MISMATCH`: a composition chain does not match its role, the role and composition references differ ignoring order, or either reference list has duplicates.

## Appendix A: Exact Pilot L4 Contracts

These lists are the Wave 2 v1 acceptance contract. Tests must compare each L3 child set exactly; do not satisfy the count by inventing additional nodes.

### Semiconductor manufacturing equipment (69 L4 nodes)

- `semiconductor_lithography_patterning`: `iline_lithography`, `krf_lithography`, `arf_dry_lithography`, `arf_immersion_lithography`, `euv_lithography`, `coat_develop_track`, `electron_beam_direct_write`, `photomask_writer`, `photomask_inspection_repair`

- `semiconductor_etch`: `dielectric_etch`, `conductor_etch`, `silicon_etch`, `deep_silicon_etch`, `atomic_layer_etch`, `wet_etch`, `photoresist_strip_residue_removal`

- `semiconductor_deposition_epitaxy`: `pvd_equipment`, `cvd_equipment`, `pecvd_equipment`, `lpcvd_equipment`, `atomic_layer_deposition`, `electrochemical_deposition`, `silicon_epitaxy`, `compound_semiconductor_epitaxy`

- `semiconductor_thermal_doping`: `oxidation_furnace`, `diffusion_furnace`, `rapid_thermal_processing`, `laser_annealing`, `ion_implantation`, `dopant_activation_equipment`

- `semiconductor_clean_wet_process`: `single_wafer_clean`, `batch_wet_clean`, `supercritical_clean_dry`, `wafer_brush_clean`, `wet_chemical_processing`

- `semiconductor_cmp_planarization`: `cmp_equipment`, `wafer_thinning`, `cmp_post_clean`, `cmp_endpoint_control`

- `semiconductor_metrology_process_control`: `wafer_defect_inspection`, `pattern_defect_inspection`, `electron_beam_inspection`, `critical_dimension_metrology`, `overlay_metrology`, `film_material_metrology`, `optical_scatterometry`, `photomask_inspection`, `yield_process_control_software`

- `semiconductor_wafer_handling_automation`: `equipment_front_end_module`, `wafer_transfer_robot`, `foup_wafer_carrier`, `amhs_system`, `wafer_tracking_mes_interface`, `cleanroom_automation_control`

- `semiconductor_vacuum_gas_fluid_control`: `dry_vacuum_pump`, `molecular_high_vacuum_pump`, `vacuum_valve`, `mass_flow_controller`, `specialty_gas_delivery`, `ultrapure_chemical_delivery`, `rf_power_matching`, `plasma_generator`

- `semiconductor_facility_pollution_control`: `exhaust_gas_treatment`, `waste_liquid_treatment`, `ultrapure_water_system`, `cleanroom_system`, `temperature_humidity_microenvironment`, `process_cooling_system`, `facility_monitoring_control`

### Humanoid robots and embodied intelligence (97 L4 nodes)

- `humanoid_embodied_ai_brain`: `multimodal_perception_model`, `vision_language_action_model`, `task_understanding_planning`, `long_term_memory_world_model`, `autonomous_decision_exception_handling`, `human_robot_interaction_model`, `edge_cloud_inference`

- `humanoid_motion_control_cerebellum`: `whole_body_control`, `biped_gait_control`, `arm_motion_planning`, `dexterous_hand_control`, `force_position_hybrid_control`, `model_predictive_control`, `reinforcement_learning_motion_policy`, `realtime_motion_control_system`

- `humanoid_data_training_simulation`: `teleoperation_motion_capture`, `embodied_training_dataset`, `robot_data_clean_label_replay`, `robot_simulation`, `digital_twin`, `synthetic_robot_data`, `sim_to_real`, `robot_training_evaluation_toolchain`

- `humanoid_perception`: `rgb_vision_module`, `depth_camera`, `lidar_sensor`, `imu_sensor`, `joint_encoder`, `joint_torque_sensor`, `six_axis_force_sensor`, `tactile_sensor`, `microphone_array`, `robot_state_sensor`

- `humanoid_compute_control_hardware`: `robot_ai_compute_chip`, `robot_ai_compute_module`, `main_controller`, `motion_controller`, `realtime_mcu`, `motor_driver`, `sensor_signal_conditioning`, `realtime_communication_bus`

- `humanoid_rotary_actuation`: `rotary_joint_assembly`, `frameless_torque_motor`, `harmonic_reducer`, `rv_reducer`, `precision_planetary_reducer`, `joint_encoder_module`, `joint_brake`, `joint_bearing`

- `humanoid_linear_actuation`: `linear_joint_assembly`, `planetary_roller_screw`, `ball_screw`, `trapezoidal_screw`, `linear_motor`, `screw_support_bearing`, `linear_displacement_sensor`

- `humanoid_upper_limb_dexterous_hand`: `shoulder_joint_module`, `elbow_joint_module`, `wrist_joint_module`, `humanoid_robotic_arm`, `dexterous_hand_assembly`, `finger_micro_actuator`, `micro_reducer_transmission`, `tendon_flexible_transmission`, `fingertip_tactile_force_control`

- `humanoid_lower_limb_locomotion`: `hip_joint_module`, `knee_joint_module`, `ankle_joint_module`, `leg_structure`, `foot_buffer_structure`, `foot_force_pressure_sensing`, `dynamic_balance_safety_mechanism`

- `humanoid_body_structure_lightweighting`: `torso_load_bearing_structure`, `lightweight_skeleton`, `aluminum_magnesium_structure`, `carbon_fiber_structure`, `precision_cast_machined_parts`, `robot_wiring_harness`, `protective_shell_soft_cover`, `robot_sealing_protection`

- `humanoid_energy_thermal_management`: `robot_battery_pack`, `high_specific_energy_cell`, `battery_management_system`, `robot_power_management_dcdc`, `autonomous_charging`, `robot_thermal_management`, `robot_power_budget_control`, `emergency_power_cutoff`

- `humanoid_manufacturing_test_integration`: `humanoid_robot_complete_unit`, `joint_module_assembly`, `whole_robot_calibration`, `motion_performance_test`, `robot_reliability_test`, `robot_safety_test`, `robot_remote_operations`, `industrial_scenario_integration`, `service_scenario_integration`

### AI data-center power application roles (80 L4 nodes)

- `ai_power_energy_supply_resilience`: `ai_power_grid_supply_role`, `ai_power_renewable_procurement_role`, `ai_power_distributed_energy_role`, `ai_power_gas_turbine_role`, `ai_power_nuclear_supply_role`, `ai_power_microgrid_role`

- `ai_power_grid_access_substation`: `ai_power_grid_connection_role`, `ai_power_substation_role`, `ai_power_transformer_role`, `ai_power_switchgear_role`, `ai_power_relay_protection_role`, `ai_power_cable_role`, `ai_power_busbar_role`, `ai_power_power_quality_role`

- `ai_power_backup_power`: `ai_power_diesel_generator_role`, `ai_power_gas_backup_role`, `ai_power_fuel_cell_backup_role`, `ai_power_battery_backup_role`, `ai_power_flywheel_role`, `ai_power_automatic_transfer_switch_role`, `ai_power_black_start_role`

- `ai_power_ups_conversion`: `ai_power_line_frequency_ups_role`, `ai_power_high_frequency_ups_role`, `ai_power_modular_ups_role`, `ai_power_medium_voltage_ups_role`, `ai_power_static_transfer_switch_role`, `ai_power_rectifier_inverter_role`, `ai_power_ups_battery_role`

- `ai_power_hvdc_dc_architecture`: `ai_power_240_400v_hvdc_role`, `ai_power_800vdc_role`, `ai_power_central_rectifier_role`, `ai_power_dc_bus_role`, `ai_power_solid_state_transformer_role`, `ai_power_dc_breaker_role`, `ai_power_dc_protection_role`

- `ai_power_room_rack_distribution`: `ai_power_pdu_role`, `ai_power_row_distribution_role`, `ai_power_busway_role`, `ai_power_intelligent_rack_pdu_role`, `ai_power_power_shelf_role`, `ai_power_high_current_connector_role`, `ai_power_hvdc_connector_role`, `ai_power_copper_flexible_connection_role`

- `ai_power_server_board_power`: `ai_power_server_psu_role`, `ai_power_ac_dc_module_role`, `ai_power_dc_dc_module_role`, `ai_power_vrm_role`, `ai_power_multiphase_controller_role`, `ai_power_mosfet_role`, `ai_power_sic_role`, `ai_power_gan_role`, `ai_power_magnetic_component_role`, `ai_power_capacitor_role`

- `ai_power_liquid_cooling_thermal`: `ai_power_cold_plate_role`, `ai_power_immersion_cooling_role`, `ai_power_spray_cooling_role`, `ai_power_cdu_role`, `ai_power_chiller_role`, `ai_power_liquid_pump_role`, `ai_power_heat_exchanger_role`, `ai_power_quick_connector_role`, `ai_power_liquid_pipe_role`, `ai_power_coolant_role`, `ai_power_leak_detection_role`, `ai_power_waste_heat_recovery_role`

- `ai_power_energy_management_software`: `ai_power_epms_role`, `ai_power_bms_role`, `ai_power_dcim_role`, `ai_power_distribution_monitoring_role`, `ai_power_thermal_control_software_role`, `ai_power_fault_prediction_role`, `ai_power_compute_energy_scheduling_role`, `ai_power_carbon_energy_cost_role`

- `ai_power_design_epc_operations`: `ai_power_electrical_design_role`, `ai_power_modular_data_center_role`, `ai_power_prefabricated_power_module_role`, `ai_power_liquid_cooling_integration_role`, `ai_power_data_center_epc_role`, `ai_power_commissioning_certification_role`, `ai_power_facility_operations_role`
