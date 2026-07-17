# Wave F/G Catalog-First Deep Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver ten evidence-backed Wave F/G deep-research packages from exact members of the approved 82-chain catalog, expanding each selected L2 branch into canonical L3/L4 structure before Theme Research conclusions and company mappings are promoted.

**Architecture:** Extend the existing chain-to-theme registry and generic batch-verification workflow. Each selected canonical chain receives one catalog node artifact, one Theme Research artifact, one company-mapping artifact, one source pack, one node-evidence matrix, and one catalog-to-theme link. Wave-specific tests enforce exact L3/L4 ownership and require every reviewed company mapping to resolve through its Theme Research node to a canonical L4 catalog object.

**Tech Stack:** Python 3.14, JSON artifacts, pytest, FastAPI read services, React 19, TypeScript, Vitest, Vite, authenticated local application on port 5174.

---

## Scope And Accounting

```python
WAVE_F_CHAIN_THEMES = {
    "ai_foundation_models_application_software": "ai_foundation_models_application_software_value_chain_v1",
    "uav_evtol_low_altitude_economy": "uav_evtol_low_altitude_economy_value_chain_v1",
    "mobile_communications_5g_6g": "mobile_communications_5g_6g_value_chain_v1",
    "analog_mixed_signal_rf_chips": "analog_mixed_signal_rf_chips_value_chain_v1",
    "rare_earth_permanent_magnets_critical_minerals": "rare_earth_permanent_magnets_critical_minerals_value_chain_v1",
}

WAVE_G_CHAIN_THEMES = {
    "mems_intelligent_sensors": "mems_intelligent_sensors_value_chain_v1",
    "wafer_manufacturing_specialty_processes": "wafer_manufacturing_specialty_processes_value_chain_v1",
    "civil_aircraft_aero_engines": "civil_aircraft_aero_engines_value_chain_v1",
    "nuclear_power_equipment": "nuclear_power_equipment_value_chain_v1",
    "scientific_instruments": "scientific_instruments_value_chain_v1",
}
```

Accounting invariants after Wave G:

```python
FOUNDATION_THEME_COUNT = 5
WAVE_A_D_THEME_COUNT = 20
WAVE_E_THEME_COUNT = 5
WAVE_F_THEME_COUNT = 5
WAVE_G_THEME_COUNT = 5
WAVE_A_G_THEME_COUNT = 35
FINAL_SELECTED_THEME_COUNT = 40
CATALOG_CHAIN_COUNT = 82
```

`synthetic_biology_biomanufacturing` remains in the catalog but is not a Wave F/G target.

## File Map

Shared registry and batch verification:

- Modify `src/stock_research/industry_chain_theme_research.py`: add Wave F/G registries and merge them into `SELECTED_CHAIN_THEMES`.
- Modify `tests/test_industry_chain_theme_research.py`: freeze membership, canonical-chain status, catalog count, and final count semantics.
- Create `artifacts/theme_decomposition/batch_manifests/wave_f_five_industry_chain_themes_v1.json`.
- Create `artifacts/theme_decomposition/batch_manifests/wave_g_five_industry_chain_themes_v1.json`.
- Create `tests/test_wave_f_industry_chain_themes.py`.
- Create `tests/test_wave_g_industry_chain_themes.py`.
- Reuse `scripts/verify_industry_chain_theme_batch.py`; change it only if a new generic failing test proves a missing invariant.

Per selected chain:

- Create `artifacts/technology_industry_catalog/v1/nodes/<chain_id>_v1.json`.
- Create `artifacts/theme_decomposition/<theme_id>.json`.
- Create `artifacts/theme_decomposition/company_mappings/<chain_id>_company_mapping_v1.json`.
- Create `artifacts/theme_decomposition/source_packs/<chain_id>_source_pack_v1.json`.
- Create `artifacts/theme_decomposition/source_packs/<chain_id>_node_evidence_matrix_v1.json`.
- Modify `artifacts/technology_industry_catalog/v1/theme_links.json`.

Read-service and UI acceptance:

- Modify `tests/test_dashboard_theme_research.py`.
- Modify `tests/test_dashboard_technology_industry_catalog.py`.
- Test without overwriting user work: `dashboard/tests/theme-research-route.test.tsx`.
- Test without overwriting user work: `dashboard/tests/theme-research-workspace.test.tsx`.

Do not stage or overwrite the existing user-owned modifications in:

- `dashboard/src/components/ThemeResearchWorkspace.tsx`
- `dashboard/src/styles.css`
- `dashboard/tests/theme-research-workspace.test.tsx`
- `tests/test_wave_e_industry_chain_themes.py`
- `docs/superpowers/plans/2026-07-14-next-fifteen-industry-chain-theme-research.md`

## Shared Completion Gates

Both manifests use:

```json
{
  "min_accepted_sources": 10,
  "min_primary_sources": 8,
  "min_claims": 12,
  "min_reviewed_mappings": 8,
  "require_node_evidence_matrix_coverage": true,
  "require_bidirectional_evidence_contract": true,
  "require_precise_mapping_locators": true
}
```

Wave F/G tests add catalog-first gates not currently represented by the generic batch verifier:

```python
import json
from pathlib import Path

from stock_research.technology_industry_catalog import load_industry_catalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def company_mapping_path(chain_id: str) -> Path:
    return (
        REPOSITORY_ROOT
        / "artifacts/theme_decomposition/company_mappings"
        / f"{chain_id}_company_mapping_v1.json"
    )


def assert_catalog_first_contract(chain_id, theme_id, expected_l3, expected_l4):
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == chain_id]
    l3_ids = {row["node_id"] for row in chain_nodes if row["level"] == "L3"}
    l4_ids = {row["node_id"] for row in chain_nodes if row["level"] == "L4"}
    assert l3_ids == expected_l3
    assert l4_ids == expected_l4

    link = next(
        row for row in catalog["theme_links"]
        if row["chain_id"] == chain_id and row["theme_id"] == theme_id
    )
    linked_l4_by_theme_node = {
        row["theme_node_id"]: row["catalog_node_id"]
        for row in link["node_links"]
        if row["catalog_node_id"] in l4_ids
    }
    assert set(linked_l4_by_theme_node.values()) == l4_ids
    assert link["unmapped_theme_node_ids"] == []

    mapping = load_json(company_mapping_path(chain_id))
    reviewed = [
        row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    ]
    assert all(row["mapped_node_id"] in linked_l4_by_theme_node for row in reviewed)
```

Every reviewed mapping continues to require distinct, precise evidence for product/service relationship, materiality, and business stage. If a chain cannot support eight defensible reviewed mappings, retain the verified smaller set and keep the theme `draft`; do not weaken the gate or add concept mappings.

## Task 1: Close The Wave E Prerequisite

**Files:**

- Follow: `docs/superpowers/plans/2026-07-17-wave-e-frontier-application-theme-research.md`
- Verify: all Wave E artifacts and tests

- [ ] **Step 1: Capture the current Wave E status**

Run:

```bash
rtk git status --short
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  scripts/verify_industry_chain_theme_batch.py \
  --manifest artifacts/theme_decomposition/batch_manifests/wave_e_five_industry_chain_themes_v1.json \
  --wave wave_e --format markdown
```

Expected at plan start: Wave E is not yet `5/5 ready`; E3 locator corrections and E4/E5 work may remain.

- [ ] **Step 2: Finish the remaining Wave E tasks using the approved Wave E plan**

Complete the unresolved parts of Tasks 5-9 in the referenced plan. Preserve strict evidence locators and do not start Wave F while any Wave E verifier row is not ready.

- [ ] **Step 3: Run the full Wave E gate**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py \
  tests/test_industry_chain_theme_research.py \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_technology_industry_catalog.py
```

Expected: all pass.

- [ ] **Step 4: Confirm Wave E readiness**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  scripts/verify_industry_chain_theme_batch.py \
  --manifest artifacts/theme_decomposition/batch_manifests/wave_e_five_industry_chain_themes_v1.json \
  --wave wave_e --format markdown
```

Expected: `Wave E: 5/5 ready`.

## Task 2: Freeze Wave F/G Registries And Counts

**Files:**

- Modify: `tests/test_industry_chain_theme_research.py`
- Modify: `src/stock_research/industry_chain_theme_research.py`

- [ ] **Step 1: Write failing registry tests**

Add imports for `WAVE_F_CHAIN_THEMES` and `WAVE_G_CHAIN_THEMES`, then add:

```python
def test_wave_f_g_registry_and_counts_are_frozen():
    assert WAVE_F_CHAIN_THEMES == {
        "ai_foundation_models_application_software": "ai_foundation_models_application_software_value_chain_v1",
        "uav_evtol_low_altitude_economy": "uav_evtol_low_altitude_economy_value_chain_v1",
        "mobile_communications_5g_6g": "mobile_communications_5g_6g_value_chain_v1",
        "analog_mixed_signal_rf_chips": "analog_mixed_signal_rf_chips_value_chain_v1",
        "rare_earth_permanent_magnets_critical_minerals": "rare_earth_permanent_magnets_critical_minerals_value_chain_v1",
    }
    assert WAVE_G_CHAIN_THEMES == {
        "mems_intelligent_sensors": "mems_intelligent_sensors_value_chain_v1",
        "wafer_manufacturing_specialty_processes": "wafer_manufacturing_specialty_processes_value_chain_v1",
        "civil_aircraft_aero_engines": "civil_aircraft_aero_engines_value_chain_v1",
        "nuclear_power_equipment": "nuclear_power_equipment_value_chain_v1",
        "scientific_instruments": "scientific_instruments_value_chain_v1",
    }
    assert "synthetic_biology_biomanufacturing" not in WAVE_G_CHAIN_THEMES
    assert len(WAVE_F_CHAIN_THEMES) == 5
    assert len(WAVE_G_CHAIN_THEMES) == 5
    assert len(SELECTED_CHAIN_THEMES) == 40


def test_wave_f_g_use_exact_canonical_catalog_chains():
    catalog = load_industry_catalog()
    chains = {row["chain_id"]: row for row in catalog["chains"]}
    selected = set(WAVE_F_CHAIN_THEMES) | set(WAVE_G_CHAIN_THEMES)
    assert len(catalog["chains"]) == 82
    assert selected <= set(chains)
    assert {chains[chain_id]["chain_kind"] for chain_id in selected} == {
        "canonical_industry_chain"
    }
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_industry_chain_theme_research.py -k 'wave_f_g or selected_chain_registry'
```

Expected: import or assertion failure because Wave F/G constants are absent and the selected count is still 30.

- [ ] **Step 3: Add the registries and merge order**

Add the exact constants from `Scope And Accounting`, then change:

```python
SELECTED_CHAIN_THEMES = {
    **COMPLETED_CHAIN_THEMES,
    **NEXT_FIFTEEN_CHAIN_THEMES,
    **WAVE_D_CHAIN_THEMES,
    **WAVE_E_CHAIN_THEMES,
    **WAVE_F_CHAIN_THEMES,
    **WAVE_G_CHAIN_THEMES,
}
```

- [ ] **Step 4: Run focused registry and catalog tests**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_industry_chain_theme_research.py \
  tests/test_technology_industry_catalog.py
```

Expected: all pass; catalog remains 82 and selected target count becomes 40.

- [ ] **Step 5: Commit the frozen Wave F/G scope**

```bash
rtk git add src/stock_research/industry_chain_theme_research.py tests/test_industry_chain_theme_research.py
rtk git commit -m "feat: register wave f g research themes"
```

## Task 3: Add Wave F/G Manifests And Catalog-First Test Harnesses

**Files:**

- Create: `artifacts/theme_decomposition/batch_manifests/wave_f_five_industry_chain_themes_v1.json`
- Create: `artifacts/theme_decomposition/batch_manifests/wave_g_five_industry_chain_themes_v1.json`
- Create: `tests/test_wave_f_industry_chain_themes.py`
- Create: `tests/test_wave_g_industry_chain_themes.py`

- [ ] **Step 1: Create both manifests**

Use `industry_chain_theme_batch_v1`, the shared completion gates, exact wave memberships from Task 2, and these artifact paths for every chain:

```python
def manifest_entry(chain_id: str) -> dict[str, object]:
    theme_id = f"{chain_id}_value_chain_v1"
    return {
        "theme_id": theme_id,
        "artifacts": {
            "theme": f"artifacts/theme_decomposition/{theme_id}.json",
            "company_mapping": f"artifacts/theme_decomposition/company_mappings/{chain_id}_company_mapping_v1.json",
            "source_pack": f"artifacts/theme_decomposition/source_packs/{chain_id}_source_pack_v1.json",
            "node_evidence_matrix": f"artifacts/theme_decomposition/source_packs/{chain_id}_node_evidence_matrix_v1.json",
        },
    }
```

- [ ] **Step 2: Add green scope tests and reusable catalog-first helpers**

Each test module must load its manifest, assert exact membership and paths, and define `assert_catalog_first_contract` from `Shared Completion Gates`. Do not add artifact-existence assertions until the corresponding theme task.

- [ ] **Step 3: Run both new test modules**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_f_industry_chain_themes.py \
  tests/test_wave_g_industry_chain_themes.py
```

Expected: pass because only scope and manifest structure are asserted.

- [ ] **Step 4: Commit the manifests and harnesses**

```bash
rtk git add \
  artifacts/theme_decomposition/batch_manifests/wave_f_five_industry_chain_themes_v1.json \
  artifacts/theme_decomposition/batch_manifests/wave_g_five_industry_chain_themes_v1.json \
  tests/test_wave_f_industry_chain_themes.py \
  tests/test_wave_g_industry_chain_themes.py
rtk git commit -m "test: freeze wave f g research scope"
```

## Task 4: Deliver F1 AI Foundation Models And Application Software

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/ai_foundation_models_application_software_v1.json`
- Create: `artifacts/theme_decomposition/ai_foundation_models_application_software_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/ai_foundation_models_application_software_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/ai_foundation_models_application_software_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/ai_foundation_models_application_software_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_f_industry_chain_themes.py`

Exact catalog structure:

```python
F1_L3 = {
    "ai_model_platforms",
    "ai_application_delivery",
    "ai_commercialization_operations",
    "ai_governance_validation",
}
F1_L4 = {
    "foundation_model_training_inference_platforms",
    "model_toolchain_finetuning_rag",
    "ai_agent_orchestration_workflow",
    "enterprise_ai_application_software",
    "consumer_ai_application_services",
    "industry_solution_delivery_integration",
    "subscription_usage_licensing_monetization",
    "customer_adoption_renewal_revenue_validation",
    "data_security_model_governance_compliance",
}
```

Initial evidence universe: `002230.SZ` 科大讯飞, `688111.SH` 金山办公, `600588.SH` 用友网络, `601360.SH` 三六零, `300229.SZ` 拓尔思, `300634.SZ` 彩讯股份, `300170.SZ` 汉得信息, `300624.SZ` 万兴科技, `300339.SZ` 润和软件, `300378.SZ` 鼎捷数智.

- [ ] **Step 1: Add failing exact-node, L4-mapping, and compute-boundary tests**

Require `F1_L3`, `F1_L4`, same-name theme-to-L4 links, and reject mappings supported only by GPU, server, data-center, cloud-capacity, or generic software evidence.

- [ ] **Step 2: Run the F1 tests and verify missing-artifact failures**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_f_industry_chain_themes.py -k foundation_models
```

- [ ] **Step 3: Create the canonical directory nodes**

Use the four L3 parents and nine L4 objects above. Assign each L4 a unique `ai_application:<object>` canonical key and preserve OS/database, industrial-software, compute-infrastructure, and data-center ownership in descriptions and edges.

- [ ] **Step 4: Collect primary evidence and build the four research artifacts**

Use 2025 annual reports, 2026 exchange disclosures, official product documentation, customer cases, contracts, and revenue disclosures. Separate model availability, paid product, customer adoption, renewal, usage revenue, and general AI branding. Write at least 12 claims and only review companies with an operating product/service relationship.

- [ ] **Step 5: Add the theme link and run verification**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_f_industry_chain_themes.py -k foundation_models \
  tests/test_technology_industry_catalog.py \
  tests/test_dashboard_theme_research.py
```

- [ ] **Step 6: Commit F1**

```bash
rtk git add artifacts/technology_industry_catalog/v1/nodes/ai_foundation_models_application_software_v1.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/ai_foundation_models_application_software_value_chain_v1.json artifacts/theme_decomposition/company_mappings/ai_foundation_models_application_software_company_mapping_v1.json artifacts/theme_decomposition/source_packs/ai_foundation_models_application_software_source_pack_v1.json artifacts/theme_decomposition/source_packs/ai_foundation_models_application_software_node_evidence_matrix_v1.json tests/test_wave_f_industry_chain_themes.py
rtk git commit -m "data: add ai application software deep research"
```

## Task 5: Deliver F2 UAV, eVTOL, And Low-Altitude Economy

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/uav_evtol_low_altitude_economy_v1.json`
- Create: `artifacts/theme_decomposition/uav_evtol_low_altitude_economy_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/uav_evtol_low_altitude_economy_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/uav_evtol_low_altitude_economy_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/uav_evtol_low_altitude_economy_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_f_industry_chain_themes.py`

```python
F2_L3 = {
    "low_altitude_aircraft_platforms",
    "low_altitude_critical_systems",
    "low_altitude_infrastructure_operations",
    "low_altitude_certification_commercialization",
}
F2_L4 = {
    "industrial_consumer_uav_platforms",
    "evtol_aircraft_platforms",
    "flight_control_avionics_navigation",
    "electric_propulsion_power_energy_systems",
    "airframe_composites_precision_components",
    "low_altitude_communications_surveillance_navigation",
    "vertiport_airspace_management_infrastructure",
    "flight_operations_maintenance_services",
    "certification_orders_delivery_utilization_validation",
}
```

Initial evidence universe: `002085.SZ` 万丰奥威, `000099.SZ` 中信海直, `001696.SZ` 宗申动力, `688070.SH` 纵横股份, `002389.SZ` 航天彩虹, `603308.SH` 应流股份, `600580.SH` 卧龙电驱, `000801.SZ` 四川九洲, `688631.SH` 莱斯信息, `301091.SZ` 深城交.

- [ ] **Step 1: Add failing structure and false-positive tests**

Reject generic automotive motors, batteries, composites, airports, satellite systems, and commercial-space products unless the filing identifies a low-altitude aircraft, infrastructure, certification, operation, order, or delivered-system role.

- [ ] **Step 2: Run the intended failing test**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_f_industry_chain_themes.py -k low_altitude
```

- [ ] **Step 3: Build the catalog tree and typed dependencies**

Create the exact L3/L4 nodes. Use typed edges for generic motors, batteries, chips, composites, communications, and airport facilities owned by other chains; do not copy those components into this tree.

- [ ] **Step 4: Build evidence-backed research artifacts**

Separate prototype, type-certificate application, type certificate, production certificate, signed order, delivery, operation, route utilization, and recognized revenue. Policy designation or demonstration-zone membership cannot prove company benefit.

- [ ] **Step 5: Run F2 regressions and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_f_industry_chain_themes.py -k low_altitude tests/test_wave_d_industry_chain_themes.py -k satellite tests/test_technology_industry_catalog.py
rtk git add artifacts/technology_industry_catalog/v1/nodes/uav_evtol_low_altitude_economy_v1.json artifacts/technology_industry_catalog/v1/edges.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/uav_evtol_low_altitude_economy_value_chain_v1.json artifacts/theme_decomposition/company_mappings/uav_evtol_low_altitude_economy_company_mapping_v1.json artifacts/theme_decomposition/source_packs/uav_evtol_low_altitude_economy_source_pack_v1.json artifacts/theme_decomposition/source_packs/uav_evtol_low_altitude_economy_node_evidence_matrix_v1.json tests/test_wave_f_industry_chain_themes.py
rtk git commit -m "data: add low altitude economy deep research"
```

## Task 6: Deliver F3 Mobile Communications 5G And 6G

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/mobile_communications_5g_6g_v1.json`
- Create: `artifacts/theme_decomposition/mobile_communications_5g_6g_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/mobile_communications_5g_6g_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/mobile_communications_5g_6g_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/mobile_communications_5g_6g_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_f_industry_chain_themes.py`

```python
F3_L3 = {
    "mobile_radio_access",
    "mobile_core_transport",
    "mobile_devices_test_ecosystem",
    "mobile_standards_deployment_economics",
}
F3_L4 = {
    "5g_advanced_radio_access_network",
    "6g_air_interface_candidate_technologies",
    "base_station_rf_frontend_antennas",
    "mobile_core_network_cloud_native",
    "mobile_backhaul_fronthaul_timing",
    "carrier_network_test_measurement",
    "mobile_terminals_modules_private_networks",
    "spectrum_standards_trials_deployment",
    "operator_capex_orders_revenue_validation",
}
```

Initial evidence universe: `000063.SZ` 中兴通讯, `600941.SH` 中国移动, `600050.SH` 中国联通, `601728.SH` 中国电信, `600498.SH` 烽火通信, `688387.SH` 信科移动, `002792.SZ` 通宇通讯, `002446.SZ` 盛路通信, `688182.SH` 灿勤科技, `688375.SH` 国博电子.

- [ ] **Step 1: Add failing route, ownership, and 6G-stage tests**

Require separate 5G-A and 6G nodes. Reject satellite-network evidence, generic optical modules, generic RF chips, research-paper participation, or standards membership as current 6G revenue.

- [ ] **Step 2: Run the failing test**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_f_industry_chain_themes.py -k mobile_communications
```

- [ ] **Step 3: Build nodes, edges, and research artifacts**

F3 owns deployed mobile-network systems and operator economics. F4 owns analog/RF chip products; optical communication and satellite communication retain their existing ownership. Claims must separate standard research, trial equipment, operator capital expenditure, commercial deployment, order delivery, and revenue.

- [ ] **Step 4: Run F3 regressions and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_f_industry_chain_themes.py -k mobile_communications tests/test_wave_e_industry_chain_themes.py -k satellite_communications tests/test_technology_industry_catalog.py
rtk git add artifacts/technology_industry_catalog/v1/nodes/mobile_communications_5g_6g_v1.json artifacts/technology_industry_catalog/v1/edges.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/mobile_communications_5g_6g_value_chain_v1.json artifacts/theme_decomposition/company_mappings/mobile_communications_5g_6g_company_mapping_v1.json artifacts/theme_decomposition/source_packs/mobile_communications_5g_6g_source_pack_v1.json artifacts/theme_decomposition/source_packs/mobile_communications_5g_6g_node_evidence_matrix_v1.json tests/test_wave_f_industry_chain_themes.py
rtk git commit -m "data: add mobile communications deep research"
```

## Task 7: Deliver F4 Analog, Mixed-Signal, And RF Chips

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/analog_mixed_signal_rf_chips_v1.json`
- Create: `artifacts/theme_decomposition/analog_mixed_signal_rf_chips_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/analog_mixed_signal_rf_chips_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/analog_mixed_signal_rf_chips_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/analog_mixed_signal_rf_chips_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_f_industry_chain_themes.py`

```python
F4_L3 = {
    "analog_signal_chain",
    "mixed_signal_interface_timing",
    "rf_integrated_circuits",
    "analog_qualification_commercialization",
}
F4_L4 = {
    "precision_signal_chain_amplifiers",
    "data_converters_adc_dac",
    "interface_isolation_driver_chips",
    "power_management_analog_chips",
    "timing_clock_mixed_signal_chips",
    "rf_front_end_pa_lna_switch",
    "rf_transceiver_mixed_signal_chips",
    "automotive_industrial_grade_analog",
    "design_win_customer_qualification_revenue_validation",
}
```

Initial evidence universe: `300661.SZ` 圣邦股份, `688536.SH` 思瑞浦, `688052.SH` 纳芯微, `688798.SH` 艾为电子, `688381.SH` 帝奥微, `300782.SZ` 卓胜微, `688153.SH` 唯捷创芯, `688270.SH` 臻镭科技, `001270.SZ` 铖昌科技, `688325.SH` 赛微微电.

- [ ] **Step 1: Add failing product-family and boundary tests**

Reject MEMS sensor devices, discrete power-switching devices, base stations, packaged modules without owned chip products, and generic semiconductor foundry evidence.

- [ ] **Step 2: Run the failing test**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_f_industry_chain_themes.py -k analog_mixed
```

- [ ] **Step 3: Build catalog and research artifacts**

Use product-family disclosures, end-market qualification, design wins, production ramps, product revenue, gross margin, and inventory evidence. A product roadmap or tape-out alone remains `reserve_only` or `concept_only`.

- [ ] **Step 4: Run semiconductor boundary regressions and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_f_industry_chain_themes.py -k analog_mixed tests/test_wave_a_industry_chain_themes.py -k power_semiconductors tests/test_technology_industry_catalog.py
rtk git add artifacts/technology_industry_catalog/v1/nodes/analog_mixed_signal_rf_chips_v1.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/analog_mixed_signal_rf_chips_value_chain_v1.json artifacts/theme_decomposition/company_mappings/analog_mixed_signal_rf_chips_company_mapping_v1.json artifacts/theme_decomposition/source_packs/analog_mixed_signal_rf_chips_source_pack_v1.json artifacts/theme_decomposition/source_packs/analog_mixed_signal_rf_chips_node_evidence_matrix_v1.json tests/test_wave_f_industry_chain_themes.py
rtk git commit -m "data: add analog mixed signal rf chip research"
```

## Task 8: Deliver F5 Rare Earth Magnets And Critical Minerals

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/rare_earth_permanent_magnets_critical_minerals_v1.json`
- Create: `artifacts/theme_decomposition/rare_earth_permanent_magnets_critical_minerals_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/rare_earth_permanent_magnets_critical_minerals_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/rare_earth_permanent_magnets_critical_minerals_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/rare_earth_permanent_magnets_critical_minerals_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_f_industry_chain_themes.py`

```python
F5_L3 = {
    "rare_earth_resources_separation",
    "rare_earth_metals_magnets",
    "rare_earth_recycling_supply_security",
    "rare_earth_market_revenue_validation",
}
F5_L4 = {
    "rare_earth_mining_resource_control",
    "rare_earth_beneficiation_concentrates",
    "rare_earth_separation_oxides",
    "rare_earth_metals_alloys",
    "ndfeb_magnetic_materials",
    "samarium_cobalt_specialty_magnets",
    "magnet_processing_coating_components",
    "rare_earth_recycling_secondary_resources",
    "quotas_prices_export_customer_validation",
}
```

Initial evidence universe: `600111.SH` 北方稀土, `000831.SZ` 中国稀土, `600392.SH` 盛和资源, `600549.SH` 厦门钨业, `300748.SZ` 金力永磁, `300224.SZ` 正海磁材, `600366.SH` 宁波韵升, `000970.SZ` 中科三环, `688077.SH` 大地熊, `600259.SH` 广晟有色.

- [ ] **Step 1: Add failing ownership and price-transmission tests**

Require resource, separation, magnet, recycling, and market-validation nodes. Reject generic downstream motor, robot, wind-power, EV, or consumer-electronics demand as a direct company mapping.

- [ ] **Step 2: Run the failing test**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_f_industry_chain_themes.py -k rare_earth
```

- [ ] **Step 3: Build the catalog and research artifacts**

Use quota, mining, separation, oxide/metal, magnet-capacity, customer, export-control, realized-price, cost, inventory, and revenue evidence. Separate resource-price elasticity from magnet-processing margin and customer qualification.

- [ ] **Step 4: Run F5 tests and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_f_industry_chain_themes.py -k rare_earth tests/test_technology_industry_catalog.py
rtk git add artifacts/technology_industry_catalog/v1/nodes/rare_earth_permanent_magnets_critical_minerals_v1.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/rare_earth_permanent_magnets_critical_minerals_value_chain_v1.json artifacts/theme_decomposition/company_mappings/rare_earth_permanent_magnets_critical_minerals_company_mapping_v1.json artifacts/theme_decomposition/source_packs/rare_earth_permanent_magnets_critical_minerals_source_pack_v1.json artifacts/theme_decomposition/source_packs/rare_earth_permanent_magnets_critical_minerals_node_evidence_matrix_v1.json tests/test_wave_f_industry_chain_themes.py
rtk git commit -m "data: add rare earth magnet deep research"
```

## Task 9: Wave F Checkpoint

**Files:** Verify Wave F artifacts, catalog, backend read models, and dashboard.

- [ ] **Step 1: Run Wave F and shared backend suites**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_f_industry_chain_themes.py \
  tests/test_industry_chain_theme_research.py \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_technology_industry_catalog.py \
  tests/test_theme_decomposition.py \
  tests/test_theme_company_mapping.py
```

- [ ] **Step 2: Run the Wave F verifier**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python scripts/verify_industry_chain_theme_batch.py --manifest artifacts/theme_decomposition/batch_manifests/wave_f_five_industry_chain_themes_v1.json --wave wave_f --format markdown
```

Expected: `Wave F: 5/5 ready`.

- [ ] **Step 3: Run frontend tests and build**

```bash
rtk pnpm --dir dashboard test -- theme-research-route.test.tsx theme-research-workspace.test.tsx
rtk pnpm --dir dashboard build
```

- [ ] **Step 4: Commit only checkpoint test fixes if a fresh failure required them**

Do not create a no-op commit. Stage only files changed to fix verified generic defects.

## Task 10: Deliver G1 MEMS And Intelligent Sensors

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/mems_intelligent_sensors_v1.json`
- Create: `artifacts/theme_decomposition/mems_intelligent_sensors_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/mems_intelligent_sensors_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/mems_intelligent_sensors_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/mems_intelligent_sensors_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_g_industry_chain_themes.py`

```python
G1_L3 = {"mems_sensor_devices", "mems_fabrication_packaging", "intelligent_sensor_integration", "mems_commercial_validation"}
G1_L4 = {
    "mems_inertial_accelerometer_gyroscope",
    "mems_pressure_flow_environmental_sensors",
    "mems_acoustic_microphones",
    "mems_rf_filters_resonators",
    "mems_optical_micro_mirror_lidar",
    "mems_foundry_wafer_process",
    "mems_packaging_calibration_test",
    "intelligent_sensor_fusion_modules",
    "design_win_mass_production_revenue_validation",
}
```

Initial evidence universe: `002241.SZ` 歌尔股份, `688396.SH` 华润微, `600460.SH` 士兰微, `300456.SZ` 赛微电子, `688286.SH` 敏芯股份, `688052.SH` 纳芯微, `300007.SZ` 汉威科技, `300667.SZ` 必创科技, `603662.SH` 柯力传感, `688582.SH` 芯动联科.

- [ ] **Step 1: Add failing exact-tree and application-boundary tests**

Assert `G1_L3`, `G1_L4`, same-name L4 links, and L4-resolved reviewed mappings. Reject production-line inspection systems and humanoid-specific sensor integration as owned nodes.

- [ ] **Step 2: Run the G1 test and verify missing artifacts fail**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_g_industry_chain_themes.py -k mems
```

- [ ] **Step 3: Build the nodes and four research artifacts**

Separate MEMS device products, foundry/process services, packaging/calibration, fusion modules, and commercial validation. Require product, process, design-win, mass-production, and revenue evidence; patents or lab prototypes remain research leads.

- [ ] **Step 4: Run G1 and ownership regressions**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_g_industry_chain_themes.py -k mems \
  tests/test_wave_b_industry_chain_themes.py -k industrial_inspection \
  tests/test_technology_industry_catalog.py
```

- [ ] **Step 5: Commit G1**

```bash
rtk git add artifacts/technology_industry_catalog/v1/nodes/mems_intelligent_sensors_v1.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/mems_intelligent_sensors_value_chain_v1.json artifacts/theme_decomposition/company_mappings/mems_intelligent_sensors_company_mapping_v1.json artifacts/theme_decomposition/source_packs/mems_intelligent_sensors_source_pack_v1.json artifacts/theme_decomposition/source_packs/mems_intelligent_sensors_node_evidence_matrix_v1.json tests/test_wave_g_industry_chain_themes.py
rtk git commit -m "data: add mems intelligent sensor research"
```

## Task 11: Deliver G2 Wafer Manufacturing And Specialty Processes

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/wafer_manufacturing_specialty_processes_v1.json`
- Create: `artifacts/theme_decomposition/wafer_manufacturing_specialty_processes_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/wafer_manufacturing_specialty_processes_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/wafer_manufacturing_specialty_processes_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/wafer_manufacturing_specialty_processes_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/edges.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_g_industry_chain_themes.py`

```python
G2_L3 = {"wafer_foundry_platforms", "specialty_process_platforms", "fab_operations_economics", "foundry_customer_validation"}
G2_L4 = {
    "logic_mature_node_foundry",
    "analog_bcd_mixed_signal_process",
    "high_voltage_power_device_process",
    "rf_soi_sige_specialty_process",
    "embedded_nonvolatile_memory_process",
    "cmos_image_sensor_display_driver_process",
    "mems_sensor_specialty_foundry",
    "compound_semiconductor_specialty_foundry",
    "capacity_utilization_yield_cost_control",
    "customer_tapeout_qualification_revenue_validation",
}
```

Initial evidence universe: `688981.SH` 中芯国际, `688347.SH` 华虹公司, `688249.SH` 晶合集成, `688172.SH` 燕东微, `688396.SH` 华润微, `600460.SH` 士兰微, `688469.SH` 芯联集成, `300456.SZ` 赛微电子, `600745.SH` 闻泰科技, `300373.SZ` 扬杰科技.

- [ ] **Step 1: Add failing foundry-process and ownership tests**

Assert the exact nodes and reject mappings supported only by equipment, material, fabless-design, packaging, or IDM product evidence without a wafer-manufacturing service or owned-fab relationship.

- [ ] **Step 2: Run the G2 test and verify missing artifacts fail**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_g_industry_chain_themes.py -k wafer_manufacturing
```

- [ ] **Step 3: Build the canonical process tree, edges, and research artifacts**

Add typed edges to equipment, materials, chip-design, MEMS, analog/RF, and power-semiconductor chains. Separate process availability, customer tape-out, qualification, mass production, utilization, yield, wafer revenue, and IDM captive production.

- [ ] **Step 4: Run semiconductor ownership regressions**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_g_industry_chain_themes.py -k wafer_manufacturing \
  tests/test_wave_f_industry_chain_themes.py -k 'analog_mixed or foundation_models' \
  tests/test_technology_industry_catalog.py
```

- [ ] **Step 5: Commit G2**

```bash
rtk git add artifacts/technology_industry_catalog/v1/nodes/wafer_manufacturing_specialty_processes_v1.json artifacts/technology_industry_catalog/v1/edges.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/wafer_manufacturing_specialty_processes_value_chain_v1.json artifacts/theme_decomposition/company_mappings/wafer_manufacturing_specialty_processes_company_mapping_v1.json artifacts/theme_decomposition/source_packs/wafer_manufacturing_specialty_processes_source_pack_v1.json artifacts/theme_decomposition/source_packs/wafer_manufacturing_specialty_processes_node_evidence_matrix_v1.json tests/test_wave_g_industry_chain_themes.py
rtk git commit -m "data: add wafer specialty process research"
```

## Task 12: Deliver G3 Civil Aircraft And Aero Engines

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/civil_aircraft_aero_engines_v1.json`
- Create: `artifacts/theme_decomposition/civil_aircraft_aero_engines_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/civil_aircraft_aero_engines_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/civil_aircraft_aero_engines_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/civil_aircraft_aero_engines_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/edges.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_g_industry_chain_themes.py`

```python
G3_L3 = {"civil_aircraft_platforms", "aero_engine_systems", "aviation_components_subsystems", "aviation_certification_lifecycle"}
G3_L4 = {
    "civil_aircraft_airframe_final_assembly",
    "aero_engine_complete_machine",
    "engine_hot_section_blades_disks",
    "engine_control_fuel_systems",
    "airborne_avionics_electromechanical_systems",
    "aviation_structures_composites_fasteners",
    "landing_gear_wheels_brakes_systems",
    "airworthiness_certification_production_ramp",
    "mro_spares_installed_base_services",
}
```

Initial evidence universe: `000768.SZ` 中航西飞, `600893.SH` 航发动力, `000738.SZ` 航发控制, `600391.SH` 航发科技, `600765.SH` 中航重机, `600862.SH` 中航高科, `300696.SZ` 爱乐达, `300900.SZ` 广联航空, `688239.SH` 航宇科技, `600038.SH` 中直股份.

- [ ] **Step 1: Add failing civil-aircraft, engine, and ownership-boundary tests**

Reject military-only aircraft, commercial-space, low-altitude, UAV, and generic advanced-material evidence unless a civil-aircraft or aero-engine role is named.

- [ ] **Step 2: Run the G3 test and verify missing artifacts fail**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_g_industry_chain_themes.py -k civil_aircraft
```

- [ ] **Step 3: Build the catalog tree, typed dependencies, and research artifacts**

Distinguish supplier qualification, airworthiness certification, batch production, delivery, installed base, spare parts, MRO, and recognized revenue.

- [ ] **Step 4: Run aerospace boundary regressions**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_g_industry_chain_themes.py -k civil_aircraft \
  tests/test_wave_f_industry_chain_themes.py -k low_altitude \
  tests/test_wave_d_industry_chain_themes.py -k satellite \
  tests/test_technology_industry_catalog.py
```

- [ ] **Step 5: Commit G3**

```bash
rtk git add artifacts/technology_industry_catalog/v1/nodes/civil_aircraft_aero_engines_v1.json artifacts/technology_industry_catalog/v1/edges.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/civil_aircraft_aero_engines_value_chain_v1.json artifacts/theme_decomposition/company_mappings/civil_aircraft_aero_engines_company_mapping_v1.json artifacts/theme_decomposition/source_packs/civil_aircraft_aero_engines_source_pack_v1.json artifacts/theme_decomposition/source_packs/civil_aircraft_aero_engines_node_evidence_matrix_v1.json tests/test_wave_g_industry_chain_themes.py
rtk git commit -m "data: add civil aircraft aero engine research"
```

## Task 13: Deliver G4 Nuclear Power Equipment

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/nuclear_power_equipment_v1.json`
- Create: `artifacts/theme_decomposition/nuclear_power_equipment_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/nuclear_power_equipment_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/nuclear_power_equipment_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/nuclear_power_equipment_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/edges.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_g_industry_chain_themes.py`

```python
G4_L3 = {"nuclear_island_equipment", "conventional_island_balance_plant", "nuclear_control_fuel_services", "nuclear_project_lifecycle"}
G4_L4 = {
    "reactor_pressure_vessel_steam_generator",
    "primary_pumps_nuclear_valves_piping",
    "nuclear_grade_materials_forgings_components",
    "turbine_generator_conventional_island",
    "nuclear_instrumentation_control_electrical",
    "nuclear_fuel_cycle_handling_services",
    "engineering_construction_commissioning",
    "maintenance_inspection_life_extension",
    "project_approval_orders_delivery_revenue_validation",
}
```

Initial evidence universe: `600875.SH` 东方电气, `601727.SH` 上海电气, `601106.SH` 中国一重, `603308.SH` 应流股份, `000922.SZ` 佳电股份, `002438.SZ` 江苏神通, `000777.SZ` 中核科技, `002255.SZ` 海陆重工, `603169.SH` 兰石重装, `002318.SZ` 久立特材.

- [ ] **Step 1: Add failing fission/fusion and equipment-role tests**

Require all G4 nodes and reject fusion-only projects, generic nuclear capability, policy mentions, and materials without a fission-equipment product or project relationship.

- [ ] **Step 2: Run the G4 test and verify missing artifacts fail**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_g_industry_chain_themes.py -k nuclear_power_equipment
```

- [ ] **Step 3: Build the fission-equipment tree, edges, and research artifacts**

Use project approval, procurement, order, manufacturing, delivery, acceptance, maintenance, and recognized-revenue evidence. Keep every fusion route and company claim in `controlled_nuclear_fusion`.

- [ ] **Step 4: Run fusion-boundary regressions**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_g_industry_chain_themes.py -k nuclear_power_equipment \
  tests/test_wave_e_industry_chain_themes.py -k controlled_nuclear_fusion \
  tests/test_technology_industry_catalog.py
```

- [ ] **Step 5: Commit G4**

```bash
rtk git add artifacts/technology_industry_catalog/v1/nodes/nuclear_power_equipment_v1.json artifacts/technology_industry_catalog/v1/edges.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/nuclear_power_equipment_value_chain_v1.json artifacts/theme_decomposition/company_mappings/nuclear_power_equipment_company_mapping_v1.json artifacts/theme_decomposition/source_packs/nuclear_power_equipment_source_pack_v1.json artifacts/theme_decomposition/source_packs/nuclear_power_equipment_node_evidence_matrix_v1.json tests/test_wave_g_industry_chain_themes.py
rtk git commit -m "data: add nuclear power equipment research"
```

## Task 14: Deliver G5 Scientific Instruments

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/scientific_instruments_v1.json`
- Create: `artifacts/theme_decomposition/scientific_instruments_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/scientific_instruments_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/scientific_instruments_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/scientific_instruments_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/edges.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_g_industry_chain_themes.py`

```python
G5_L3 = {"analytical_instrument_platforms", "laboratory_precision_instruments", "instrument_core_subsystems", "instrument_lifecycle_commercialization"}
G5_L4 = {
    "mass_spectrometry_instruments",
    "chromatography_separation_instruments",
    "molecular_atomic_spectroscopy_instruments",
    "electron_optical_microscopy_instruments",
    "xray_diffraction_fluorescence_instruments",
    "electrochemical_thermal_analysis_instruments",
    "general_lab_automation_sample_prep",
    "instrument_core_sources_detectors_optics",
    "scientific_instrument_software_consumables_service",
    "certification_tender_installed_base_revenue_validation",
}
```

Initial evidence universe: `300203.SZ` 聚光科技, `688056.SH` 莱伯泰科, `688622.SH` 禾信仪器, `688600.SH` 皖仪科技, `300165.SZ` 天瑞仪器, `300797.SZ` 钢研纳克, `430476.BJ` 海能技术, `688337.SH` 普源精电, `688112.SH` 鼎阳科技, `688628.SH` 优利德.

- [ ] **Step 1: Add failing instrument-category, L4-mapping, and ownership tests**

Require the exact G5 nodes. Reject production-line machine vision/metrology, medical imaging, generic laboratory consumables, and distributor-only relationships as direct instrument ownership.

- [ ] **Step 2: Run the G5 test and verify missing artifacts fail**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_wave_g_industry_chain_themes.py -k scientific_instruments
```

- [ ] **Step 3: Build the exact catalog tree, edges, and research artifacts**

Add typed dependencies on optics, detectors, electronics, vacuum, software, and consumables without duplicating their canonical ownership. Require named instruments, standards or registration where applicable, tenders, customer adoption, installed base, consumables/service, and revenue evidence.

- [ ] **Step 4: Run medical and industrial-inspection boundary regressions**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_g_industry_chain_themes.py -k scientific_instruments \
  tests/test_wave_b_industry_chain_themes.py -k industrial_inspection \
  tests/test_wave_d_industry_chain_themes.py -k high_end_medical \
  tests/test_technology_industry_catalog.py
```

- [ ] **Step 5: Commit G5**

```bash
rtk git add artifacts/technology_industry_catalog/v1/nodes/scientific_instruments_v1.json artifacts/technology_industry_catalog/v1/edges.json artifacts/technology_industry_catalog/v1/theme_links.json artifacts/theme_decomposition/scientific_instruments_value_chain_v1.json artifacts/theme_decomposition/company_mappings/scientific_instruments_company_mapping_v1.json artifacts/theme_decomposition/source_packs/scientific_instruments_source_pack_v1.json artifacts/theme_decomposition/source_packs/scientific_instruments_node_evidence_matrix_v1.json tests/test_wave_g_industry_chain_themes.py
rtk git commit -m "data: add scientific instrument deep research"
```

## Task 15: Add Wave F/G Read-Service And Navigation Acceptance

**Files:**

- Modify: `tests/test_dashboard_theme_research.py`
- Modify: `tests/test_dashboard_technology_industry_catalog.py`
- Modify: `tests/test_wave_f_industry_chain_themes.py`
- Modify: `tests/test_wave_g_industry_chain_themes.py`
- Test without editing: `dashboard/tests/theme-research-route.test.tsx`
- Test without editing: `dashboard/tests/theme-research-workspace.test.tsx`

- [ ] **Step 1: Add failing parameterized backend acceptance tests**

```python
WAVE_F_G_THEME_IDS = [*WAVE_F_CHAIN_THEMES.values(), *WAVE_G_CHAIN_THEMES.values()]

@pytest.mark.parametrize("theme_id", WAVE_F_G_THEME_IDS)
def test_wave_f_g_dashboard_read_models_are_complete(theme_id):
    detail = get_theme_research_theme(theme_id)
    claims = list_theme_research_claims(theme_id)["items"]
    companies = list_theme_research_companies(theme_id)["items"]
    assert detail["theme_id"] == theme_id
    assert detail["research_profile"]["investment_summary"]
    assert len(claims) >= 12
    assert all(row["beneficiary_tier"] != "concept_association" for row in companies)
```

Catalog assertions must prove exact `theme_id`, deep-research status, source count, reviewed-company count, and valid route for every F/G chain.

- [ ] **Step 2: Run backend acceptance tests**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q tests/test_dashboard_theme_research.py tests/test_dashboard_technology_industry_catalog.py tests/test_wave_f_industry_chain_themes.py tests/test_wave_g_industry_chain_themes.py
```

- [ ] **Step 3: Make only generic loader fixes exposed by failing tests**

Use registry iteration or artifact discovery. Do not add theme-ID branches to FastAPI or React.

- [ ] **Step 4: Run frontend tests and build**

```bash
rtk pnpm --dir dashboard test -- theme-research-route.test.tsx theme-research-workspace.test.tsx
rtk pnpm --dir dashboard build
```

Expected: no loading failure, no operation column, and row-click navigation to `/tech-bottleneck/stock/<code>?source=theme_research`.

- [ ] **Step 5: Commit only the new generic acceptance changes**

Inspect `rtk git status --short` first and exclude all pre-existing user-owned modifications.

## Task 16: Full A-G Verification And Real Port-5174 Acceptance

**Files:** Verify all registries, wave artifacts, catalog package, read services, and dashboard.

- [ ] **Step 1: Run all wave suites**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_a_industry_chain_themes.py \
  tests/test_wave_b_industry_chain_themes.py \
  tests/test_wave_c_industry_chain_themes.py \
  tests/test_wave_d_industry_chain_themes.py \
  tests/test_wave_e_industry_chain_themes.py \
  tests/test_wave_f_industry_chain_themes.py \
  tests/test_wave_g_industry_chain_themes.py
```

- [ ] **Step 2: Run shared validation suites**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_verify_industry_chain_theme_batch.py \
  tests/test_industry_chain_theme_research.py \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_technology_industry_catalog.py \
  tests/test_theme_decomposition.py \
  tests/test_theme_company_mapping.py
```

- [ ] **Step 3: Run both batch verifiers**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python scripts/verify_industry_chain_theme_batch.py --manifest artifacts/theme_decomposition/batch_manifests/wave_f_five_industry_chain_themes_v1.json --wave wave_f --format markdown
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python scripts/verify_industry_chain_theme_batch.py --manifest artifacts/theme_decomposition/batch_manifests/wave_g_five_industry_chain_themes_v1.json --wave wave_g --format markdown
```

Expected: Wave F `5/5 ready`, Wave G `5/5 ready`.

- [ ] **Step 4: Verify final counts directly**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from stock_research.industry_chain_theme_research import (
    COMPLETED_CHAIN_THEMES,
    NEXT_FIFTEEN_CHAIN_THEMES,
    SELECTED_CHAIN_THEMES,
    WAVE_D_CHAIN_THEMES,
    WAVE_E_CHAIN_THEMES,
    WAVE_F_CHAIN_THEMES,
    WAVE_G_CHAIN_THEMES,
)
assert len(COMPLETED_CHAIN_THEMES) == 5
assert len(NEXT_FIFTEEN_CHAIN_THEMES) + len(WAVE_D_CHAIN_THEMES) == 20
assert len(WAVE_E_CHAIN_THEMES) == 5
assert len(WAVE_F_CHAIN_THEMES) == 5
assert len(WAVE_G_CHAIN_THEMES) == 5
assert len(SELECTED_CHAIN_THEMES) == 40
print("verified: A-G=35, foundation=5, selected total=40")
PY
```

- [ ] **Step 5: Run frontend tests and build**

```bash
rtk pnpm --dir dashboard test -- theme-research-route.test.tsx theme-research-workspace.test.tsx
rtk pnpm --dir dashboard build
```

- [ ] **Step 6: Inspect the authenticated application on port 5174**

Verify:

- `/theme-research` lists all ten Wave F/G themes without loading errors;
- every catalog page renders its exact L3/L4 directory before the deep-research entry;
- each linked Theme Research page renders conclusion, value chain, profit pools, catalysts, risks, evidence gaps, sources, and companies;
- every reviewed company row resolves to an L4 object and opens Stock Workspace when the row is clicked;
- no operation column appears;
- F3/F4, F2/aerospace, G1/G2, G3/low-altitude/commercial-space, and G4/fusion boundaries do not duplicate ownership;
- desktop and mobile widths have no page-level horizontal overflow.

- [ ] **Step 7: Run repository hygiene checks**

```bash
rtk git diff --check
rtk git status --short
rtk git log --oneline -20
```

## Final Acceptance Checklist

- [ ] Wave E is `5/5 ready` before Wave F begins.
- [ ] Wave F is `5/5 ready` before Wave G begins.
- [ ] Wave G is `5/5 ready`.
- [ ] The catalog remains exactly 82 L2 chains.
- [ ] All ten F/G chains are exact canonical catalog members.
- [ ] G5 is `scientific_instruments`; synthetic biology is not selected.
- [ ] Every selected chain has exact, validated L3/L4 nodes.
- [ ] Every Theme Research node is accounted for by a catalog link.
- [ ] Every reviewed company mapping resolves to a linked canonical L4 object.
- [ ] Every reviewed claim and mapping has accepted, precise evidence.
- [ ] Concept-only companies are separated and never pad reviewed coverage.
- [ ] The selected registry contains 40 themes after Wave G.
- [ ] Backend, frontend, verifier, catalog, and build checks pass.
- [ ] Real port-5174 navigation and row-click behavior pass.
- [ ] Pre-existing user-owned dirty files remain unstaged and unmodified by this plan.
