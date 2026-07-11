# Technology Industry Catalog Wave 3 Complete L2 Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the complete approved 82-chain L2 technology catalog with chain kinds, decomposition methods, scope, exclusions, aliases, and deterministic structural-completeness reporting.

**Architecture:** Keep L2 definitions in one versioned `chains.json` registry while detailed L3/L4 branches remain separate per-chain artifacts. Chains without detailed nodes are explicitly `skeleton`; pilot chains remain `draft`. Structural completeness is reported independently from evidence completeness and company coverage.

**Tech Stack:** JSON artifacts, Wave 1 catalog loader/CLI, pytest.

---

## File Structure

- Modify `artifacts/technology_industry_catalog/v1/chains.json`: complete L2 registry.
- Modify `src/stock_research/technology_industry_catalog.py`: completeness summary and exact alias lookup.
- Create `tests/test_technology_industry_catalog_skeleton.py`: exact registry, methods, kinds, and completeness tests.
- Create `docs/technology_industry_catalog_v1.md`: operator guide.

### Task 1: Freeze the exact L2 registry contract

**Files:**
- Create: `tests/test_technology_industry_catalog_skeleton.py`

- [ ] **Step 1: Write the failing exact-registry test**

Define:

```python
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
```

Group loaded chains by sector, preserve `order`, and assert exact equality. Also assert the flattened total is 82 and all chain IDs are unique.

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog_skeleton.py -q
```

Expected: the loaded catalog contains only pilot/supporting chains.

- [ ] **Step 3: Commit the failing contract test**

```bash
git add tests/test_technology_industry_catalog_skeleton.py
git commit -m "test: freeze technology industry l2 catalog"
```

### Task 2: Populate all approved L2 rows

**Files:**
- Modify: `artifacts/technology_industry_catalog/v1/chains.json`
- Modify: `tests/test_technology_industry_catalog_skeleton.py`

- [ ] **Step 1: Add every missing chain**

Every row includes all `CHAIN_FIELDS` and:

- `status: skeleton` if no detailed node artifact exists;
- non-empty `scope` describing included research objects;
- non-empty `exclusions` naming adjacent canonical owners;
- aliases only for stable industry synonyms;
- fixed `order` within its sector.

Use Appendix A as the exact method and chain-kind contract. The following examples explain the classification, but Appendix A is authoritative:

```python
METHOD_RULES = {
    "manufacturing_process": {
        "semiconductor_eda_ip_design_services",
        "semiconductor_manufacturing_equipment",
        "semiconductor_materials_electronic_chemicals",
        "semiconductor_packaging_test_advanced_packaging",
        "power_batteries_battery_materials",
        "solar_power",
        "small_molecule_innovative_drugs",
        "biologic_antibody_drugs",
        "advanced_metals_specialty_alloys",
    },
    "system_architecture": {
        "humanoid_robots_embodied_intelligence",
        "industrial_robots",
        "new_energy_vehicle_architecture_platforms",
        "civil_aircraft_aero_engines",
        "high_end_medical_devices",
        "medical_imaging_diagnostic_equipment",
    },
    "infrastructure_flow": {
        "new_power_system_smart_grid",
        "ai_data_center_power",
        "cloud_data_center_infrastructure",
        "mobile_communications_5g_6g",
        "intelligent_transport_vehicle_road_cloud",
        "water_treatment_resource_technology",
    },
    "technical_route": {
        "hydrogen_fuel_cells",
        "quantum_computing_communication_measurement",
        "brain_computer_interfaces_neural_engineering",
        "controlled_nuclear_fusion",
        "future_displays",
        "new_computing_routes",
    },
}
```

Assign every chain exactly one method and kind from Appendix A. Extend the test to compare the loaded `(chain_id, decomposition_method, chain_kind)` tuples against the complete 82-row matrix.

- [ ] **Step 2: Run validation and exact registry tests**

```bash
.venv/bin/python -m stock_research.cli technology-industry-catalog validate
.venv/bin/pytest tests/test_technology_industry_catalog_skeleton.py -q
```

Expected: all 82 chains load; tests pass.

- [ ] **Step 3: Commit**

```bash
git add artifacts/technology_industry_catalog/v1/chains.json tests/test_technology_industry_catalog_skeleton.py
git commit -m "data: register complete technology industry l2 catalog"
```

### Task 3: Report structural completeness independently

**Files:**
- Modify: `src/stock_research/technology_industry_catalog.py`
- Modify: `tests/test_technology_industry_catalog_skeleton.py`

- [ ] **Step 1: Write the failing summary test**

```python
def test_summary_separates_skeleton_and_detailed_chains():
    summary = summarize_industry_catalog(load_industry_catalog())

    assert summary["sector_count"] == 10
    assert summary["chain_count"] == 82
    assert summary["detailed_chain_count"] >= 3
    assert summary["skeleton_chain_count"] == 82 - summary["detailed_chain_count"]
    assert summary["structural_completeness_percent"] == round(
        summary["detailed_chain_count"] / 82 * 100,
        2,
    )
    assert "evidence_completeness_percent" not in summary
    assert "company_coverage_percent" not in summary
```

Define a detailed chain as one containing at least one valid L3 and one valid L4 node, regardless of its status label.

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog_skeleton.py -q
```

Expected: completeness keys missing.

- [ ] **Step 3: Implement completeness fields**

Add:

```text
chains_by_decomposition_method
detailed_chain_count
skeleton_chain_count
structural_completeness_percent
unexpanded_chain_ids
```

Sort all IDs and round percentage to two decimals. Do not add evidence or company coverage values.

- [ ] **Step 4: Run tests and commit**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog.py tests/test_technology_industry_catalog_pilots.py tests/test_technology_industry_catalog_skeleton.py -q
git add src/stock_research/technology_industry_catalog.py tests/test_technology_industry_catalog_skeleton.py
git commit -m "feat: report industry catalog completeness"
```

Expected: all catalog tests pass.

### Task 4: Add exact alias lookup

**Files:**
- Modify: `src/stock_research/technology_industry_catalog.py`
- Modify: `tests/test_technology_industry_catalog_skeleton.py`

- [ ] **Step 1: Write failing lookup tests**

```python
def test_find_chain_resolves_id_name_and_unique_alias():
    catalog = load_industry_catalog()

    assert find_industry_chain(
        catalog, "semiconductor_manufacturing_equipment"
    )["chain_id"] == "semiconductor_manufacturing_equipment"
    assert find_industry_chain(
        catalog, "人形机器人"
    )["chain_id"] == "humanoid_robots_embodied_intelligence"
    assert find_industry_chain(
        catalog, "AI数据中心供电"
    )["chain_id"] == "ai_data_center_power"
```

Add a temporary-package test where two chains share one alias and assert `AMBIGUOUS_CHAIN_ALIAS`. Assert unknown input raises `CHAIN_NOT_FOUND`.

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog_skeleton.py -q
```

Expected: lookup function missing.

- [ ] **Step 3: Implement exact normalized lookup**

Add `find_industry_chain(catalog, query)`. Normalize only with whitespace trim and `casefold()`. Resolve in order: exact ID, exact name, unique exact alias. Do not use substring or fuzzy matching.

- [ ] **Step 4: Run tests and commit**

```bash
.venv/bin/pytest tests/test_technology_industry_catalog_skeleton.py -q
git add src/stock_research/technology_industry_catalog.py tests/test_technology_industry_catalog_skeleton.py
git commit -m "feat: add exact industry chain alias lookup"
```

Expected: tests pass.

### Task 5: Add the operator guide

**Files:**
- Create: `docs/technology_industry_catalog_v1.md`

- [ ] **Step 1: Write the guide**

Cover:

1. purpose and relationship to Theme Research and Tech Bottleneck;
2. L1-L4 semantics;
3. three chain kinds;
4. unique ownership and typed edges;
5. ten-sector and 82-chain counts;
6. three pilots;
7. structural, evidence, and company completeness as separate concepts;
8. CLI commands;
9. how to add an L2 skeleton;
10. how to expand L3/L4 without duplicate nodes;
11. read-only boundary and absence of DB/dashboard writes.

Document:

```bash
.venv/bin/python -m stock_research.cli technology-industry-catalog validate
.venv/bin/python -m stock_research.cli technology-industry-catalog summary
.venv/bin/python -m stock_research.cli technology-industry-catalog show --chain ai_data_center_power
```

- [ ] **Step 2: Check and commit**

```bash
git diff --check
.venv/bin/python -m stock_research.cli technology-industry-catalog validate
git add docs/technology_industry_catalog_v1.md
git commit -m "docs: add technology industry catalog guide"
```

Expected: no whitespace errors; catalog validation succeeds.

### Task 6: Final Wave 3 verification

**Files:**
- Verify only.

- [ ] **Step 1: Run compatibility tests**

```bash
.venv/bin/pytest \
  tests/test_technology_industry_catalog.py \
  tests/test_technology_industry_catalog_pilots.py \
  tests/test_technology_industry_catalog_skeleton.py \
  tests/test_theme_decomposition.py \
  tests/test_decomposition_templates.py \
  tests/test_theme_research_phase_verifier.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Verify summary invariants**

```bash
.venv/bin/python -m stock_research.cli technology-industry-catalog summary
```

Expected:

- `sector_count: 10`;
- `chain_count: 82`;
- at least three detailed pilots;
- all other incomplete chains listed in `unexpanded_chain_ids`;
- no fabricated evidence or company coverage percentage.

- [ ] **Step 3: Verify scope isolation**

```bash
git diff --name-only HEAD~5..HEAD
```

Expected: only catalog artifacts, loader/tests, and catalog documentation changed. No production database schema or dashboard files changed.

## Appendix A: Exact L2 Method and Kind Matrix

The registry must use this exact v1 assignment. Any change requires a design-spec revision rather than an implementation-time guess.

| Chain ID | Decomposition method | Chain kind |
|---|---|---|
| `semiconductor_eda_ip_design_services` | `manufacturing_process` | `canonical_industry_chain` |
| `ai_logic_compute_chips` | `system_architecture` | `canonical_industry_chain` |
| `memory_chips_storage_control` | `manufacturing_process` | `canonical_industry_chain` |
| `analog_mixed_signal_rf_chips` | `system_architecture` | `canonical_industry_chain` |
| `power_semiconductors` | `manufacturing_process` | `canonical_industry_chain` |
| `mems_intelligent_sensors` | `manufacturing_process` | `canonical_industry_chain` |
| `wafer_manufacturing_specialty_processes` | `manufacturing_process` | `canonical_industry_chain` |
| `semiconductor_manufacturing_equipment` | `manufacturing_process` | `canonical_industry_chain` |
| `semiconductor_materials_electronic_chemicals` | `manufacturing_process` | `canonical_industry_chain` |
| `semiconductor_packaging_test_advanced_packaging` | `manufacturing_process` | `canonical_industry_chain` |
| `pcb_passives_connectors_interconnect` | `manufacturing_process` | `canonical_industry_chain` |
| `display_panels_optoelectronic_components` | `manufacturing_process` | `canonical_industry_chain` |
| `ai_foundation_models_application_software` | `system_architecture` | `canonical_industry_chain` |
| `ai_compute_infrastructure` | `system_architecture` | `canonical_industry_chain` |
| `cloud_data_center_infrastructure` | `infrastructure_flow` | `canonical_industry_chain` |
| `mobile_communications_5g_6g` | `infrastructure_flow` | `canonical_industry_chain` |
| `optical_communications_data_center_interconnect` | `infrastructure_flow` | `canonical_industry_chain` |
| `network_equipment_edge_iot` | `infrastructure_flow` | `canonical_industry_chain` |
| `foundational_software_os_database` | `system_architecture` | `canonical_industry_chain` |
| `industrial_software` | `system_architecture` | `canonical_industry_chain` |
| `cybersecurity_data_infrastructure` | `system_architecture` | `canonical_industry_chain` |
| `industrial_machine_tools_cnc` | `system_architecture` | `canonical_industry_chain` |
| `industrial_automation_control` | `system_architecture` | `canonical_industry_chain` |
| `industrial_robots` | `system_architecture` | `canonical_industry_chain` |
| `humanoid_robots_embodied_intelligence` | `system_architecture` | `canonical_industry_chain` |
| `laser_equipment_additive_manufacturing` | `manufacturing_process` | `canonical_industry_chain` |
| `scientific_instruments` | `system_architecture` | `canonical_industry_chain` |
| `industrial_inspection_metrology_machine_vision` | `system_architecture` | `canonical_industry_chain` |
| `core_mechanical_components` | `system_architecture` | `canonical_industry_chain` |
| `process_industry_specialized_equipment` | `system_architecture` | `canonical_industry_chain` |
| `new_power_system_smart_grid` | `infrastructure_flow` | `canonical_industry_chain` |
| `power_generation_energy_equipment` | `system_architecture` | `canonical_industry_chain` |
| `power_electronics_power_supply_equipment` | `system_architecture` | `canonical_industry_chain` |
| `ai_data_center_power` | `infrastructure_flow` | `application_theme_chain` |
| `solar_power` | `manufacturing_process` | `canonical_industry_chain` |
| `wind_power` | `manufacturing_process` | `canonical_industry_chain` |
| `power_batteries_battery_materials` | `manufacturing_process` | `canonical_industry_chain` |
| `new_energy_storage` | `technical_route` | `canonical_industry_chain` |
| `hydrogen_fuel_cells` | `technical_route` | `canonical_industry_chain` |
| `nuclear_power_equipment` | `system_architecture` | `canonical_industry_chain` |
| `advanced_metals_specialty_alloys` | `manufacturing_process` | `canonical_industry_chain` |
| `rare_earth_permanent_magnets_critical_minerals` | `manufacturing_process` | `canonical_industry_chain` |
| `carbon_fiber_advanced_composites` | `manufacturing_process` | `canonical_industry_chain` |
| `advanced_ceramics_specialty_glass` | `manufacturing_process` | `canonical_industry_chain` |
| `high_performance_polymers_engineering_plastics` | `manufacturing_process` | `canonical_industry_chain` |
| `membrane_separation_materials` | `manufacturing_process` | `canonical_industry_chain` |
| `nanomaterials_functional_materials` | `manufacturing_process` | `canonical_industry_chain` |
| `new_energy_vehicle_architecture_platforms` | `system_architecture` | `canonical_industry_chain` |
| `intelligent_driving_smart_cockpit` | `system_architecture` | `canonical_industry_chain` |
| `automotive_electronics_chip_applications` | `system_architecture` | `canonical_industry_chain` |
| `electric_drive_chassis_by_wire_thermal_management` | `system_architecture` | `canonical_industry_chain` |
| `rail_transit_equipment` | `system_architecture` | `canonical_industry_chain` |
| `intelligent_transport_vehicle_road_cloud` | `infrastructure_flow` | `application_theme_chain` |
| `civil_aircraft_aero_engines` | `system_architecture` | `canonical_industry_chain` |
| `commercial_space_launch` | `system_architecture` | `canonical_industry_chain` |
| `satellite_manufacturing_space_infrastructure` | `system_architecture` | `canonical_industry_chain` |
| `satellite_communications_navigation_remote_sensing` | `infrastructure_flow` | `application_theme_chain` |
| `uav_evtol_low_altitude_economy` | `system_architecture` | `canonical_industry_chain` |
| `ships_offshore_deep_sea_equipment` | `system_architecture` | `canonical_industry_chain` |
| `defense_electronics_special_equipment` | `system_architecture` | `canonical_industry_chain` |
| `small_molecule_innovative_drugs` | `manufacturing_process` | `canonical_industry_chain` |
| `biologic_antibody_drugs` | `manufacturing_process` | `canonical_industry_chain` |
| `vaccines` | `manufacturing_process` | `canonical_industry_chain` |
| `cell_gene_therapy` | `manufacturing_process` | `canonical_industry_chain` |
| `synthetic_biology_biomanufacturing` | `manufacturing_process` | `canonical_industry_chain` |
| `high_end_medical_devices` | `system_architecture` | `canonical_industry_chain` |
| `medical_imaging_diagnostic_equipment` | `system_architecture` | `canonical_industry_chain` |
| `in_vitro_diagnostics` | `manufacturing_process` | `canonical_industry_chain` |
| `digital_health_healthcare_it` | `system_architecture` | `canonical_industry_chain` |
| `agricultural_biotechnology_modern_seeds` | `manufacturing_process` | `canonical_industry_chain` |
| `air_soil_industrial_pollution_control` | `infrastructure_flow` | `canonical_industry_chain` |
| `water_treatment_resource_technology` | `infrastructure_flow` | `canonical_industry_chain` |
| `solid_waste_resource_recovery_circular_economy` | `infrastructure_flow` | `canonical_industry_chain` |
| `carbon_capture_utilization_storage` | `technical_route` | `canonical_industry_chain` |
| `industrial_energy_efficiency_management` | `infrastructure_flow` | `canonical_industry_chain` |
| `quantum_computing_communication_measurement` | `technical_route` | `frontier_technology_chain` |
| `brain_computer_interfaces_neural_engineering` | `technical_route` | `frontier_technology_chain` |
| `controlled_nuclear_fusion` | `technical_route` | `frontier_technology_chain` |
| `future_networks_next_generation_internet` | `technical_route` | `frontier_technology_chain` |
| `spatial_computing_xr_metaverse_infrastructure` | `technical_route` | `frontier_technology_chain` |
| `future_displays` | `technical_route` | `frontier_technology_chain` |
| `new_computing_routes` | `technical_route` | `frontier_technology_chain` |
