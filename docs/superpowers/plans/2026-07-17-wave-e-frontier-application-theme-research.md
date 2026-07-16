# Wave E Frontier And Application Theme Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver five evidence-backed Wave E Theme Research packages from the approved 82-chain catalog, taking the A-E wave program from 20 to 25 themes and the total priority pool from 25 to 30 themes.

**Architecture:** Extend the existing chain-to-theme registry and batch verifier, then build each theme as four synchronized research artifacts plus catalog nodes, application compositions where required, and theme links. Preserve canonical ownership by using application-role composition for satellite applications and vehicle-road-cloud, frontier-route nodes for brain-computer interfaces, fusion, and quantum technology, and the existing deterministic evidence and beneficiary classifiers for all company mappings.

**Tech Stack:** Python 3.14, JSON artifacts, FastAPI read services, pytest, React 19, TypeScript, Vitest, Vite, local authenticated application on port 5174.

---

## Scope And Accounting

```python
WAVE_E_CHAIN_THEMES = {
    "satellite_communications_navigation_remote_sensing": (
        "satellite_communications_navigation_remote_sensing_value_chain_v1"
    ),
    "intelligent_transport_vehicle_road_cloud": (
        "intelligent_transport_vehicle_road_cloud_value_chain_v1"
    ),
    "brain_computer_interfaces_neural_engineering": (
        "brain_computer_interfaces_neural_engineering_value_chain_v1"
    ),
    "controlled_nuclear_fusion": "controlled_nuclear_fusion_value_chain_v1",
    "quantum_computing_communication_measurement": (
        "quantum_computing_communication_measurement_value_chain_v1"
    ),
}
```

Accounting invariants:

```python
FOUNDATION_THEME_COUNT = 5
WAVE_A_D_THEME_COUNT = 20
CURRENT_TOTAL_THEME_COUNT = 25
WAVE_A_E_THEME_COUNT = 25
FINAL_TOTAL_THEME_COUNT = 30
CATALOG_CHAIN_COUNT = 82
```

The implementation must report both counts. `Wave A-E 25/25` and `priority pool 30/30` are different acceptance statements.

## File Map

Shared registry and verification:

- Modify `src/stock_research/industry_chain_theme_research.py`: add the Wave E registry and include it in `SELECTED_CHAIN_THEMES`.
- Modify `tests/test_industry_chain_theme_research.py`: freeze Wave E membership, 82-chain membership, A-E count, and total-pool count.
- Create `artifacts/theme_decomposition/batch_manifests/wave_e_five_industry_chain_themes_v1.json`: define the five packages and strict completion gates.
- Create `tests/test_wave_e_industry_chain_themes.py`: parameterized artifact, boundary, evidence, catalog, API, and readiness tests.
- Reuse `scripts/verify_industry_chain_theme_batch.py`: no production change is planned unless the new failing tests expose a missing generic invariant.

Per-theme research artifacts:

- Create `artifacts/theme_decomposition/<theme_id>.json`: narrative, profile, sources, claims, nodes, and value-capture assessments.
- Create `artifacts/theme_decomposition/company_mappings/<chain_id>_company_mapping_v1.json`: reviewed mappings and precise evidence items.
- Create `artifacts/theme_decomposition/source_packs/<chain_id>_source_pack_v1.json`: accepted-source registry and source-to-node support declarations.
- Create `artifacts/theme_decomposition/source_packs/<chain_id>_node_evidence_matrix_v1.json`: bidirectional node, claim, source, strength, and gap state.

Catalog projection:

- Create `artifacts/technology_industry_catalog/v1/nodes/satellite_communications_navigation_remote_sensing_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/nodes/intelligent_transport_vehicle_road_cloud_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/nodes/vehicle_road_cloud_supporting_canonical_nodes_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/nodes/brain_computer_interfaces_neural_engineering_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/nodes/controlled_nuclear_fusion_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/nodes/quantum_computing_communication_measurement_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/theme_compositions/satellite_communications_navigation_remote_sensing_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/theme_compositions/intelligent_transport_vehicle_road_cloud_v1.json`.
- Modify `artifacts/technology_industry_catalog/v1/theme_links.json`: add five one-to-many Theme Research projections.

Frontend and read-service acceptance:

- Modify `tests/test_dashboard_theme_research.py`: prove all five details, sources, claims, and company endpoints load.
- Modify `tests/test_dashboard_technology_industry_catalog.py`: prove all five catalog entries expose their deep-research summaries.
- Reuse `dashboard/tests/theme-research-route.test.tsx` and `dashboard/tests/theme-research-workspace.test.tsx`: run them without overwriting the user's existing uncommitted edits.

## Shared Artifact Rules

Every reviewed package must meet this verifier configuration:

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

Each reviewed company mapping must have three distinct evidence roles and locators:

```python
REQUIRED_MAPPING_EVIDENCE = {
    "product_or_service": {"product_relationship", "service_relationship"},
    "materiality": {"revenue_materiality"},
    "stage": {"business_stage"},
}
```

The three evidence items may reference one filing only when they use three distinct page or section locators. A policy mention, laboratory membership, patent, investment, strategic agreement, or company keyword cannot substitute for a disclosed product or service relationship.

## Task 1: Freeze Wave E Registry And Correct Count Semantics

**Files:**

- Modify: `tests/test_industry_chain_theme_research.py`
- Modify: `src/stock_research/industry_chain_theme_research.py`

- [ ] **Step 1: Write the failing Wave E registry test**

Add the import and assertions below:

```python
from stock_research.industry_chain_theme_research import WAVE_E_CHAIN_THEMES


def test_wave_e_chain_registry_and_program_counts_are_frozen():
    assert WAVE_E_CHAIN_THEMES == {
        "satellite_communications_navigation_remote_sensing": "satellite_communications_navigation_remote_sensing_value_chain_v1",
        "intelligent_transport_vehicle_road_cloud": "intelligent_transport_vehicle_road_cloud_value_chain_v1",
        "brain_computer_interfaces_neural_engineering": "brain_computer_interfaces_neural_engineering_value_chain_v1",
        "controlled_nuclear_fusion": "controlled_nuclear_fusion_value_chain_v1",
        "quantum_computing_communication_measurement": "quantum_computing_communication_measurement_value_chain_v1",
    }
    assert len(NEXT_FIFTEEN_CHAIN_THEMES) + len(research.WAVE_D_CHAIN_THEMES) == 20
    assert len(WAVE_E_CHAIN_THEMES) == 5
    assert len(SELECTED_CHAIN_THEMES) == 30


def test_wave_e_uses_only_existing_application_or_frontier_chains():
    catalog = load_industry_catalog()
    chains = {row["chain_id"]: row for row in catalog["chains"]}
    assert len(chains) == 82
    assert {
        chains[chain_id]["chain_kind"] for chain_id in WAVE_E_CHAIN_THEMES
    } == {"application_theme_chain", "frontier_technology_chain"}
    assert sum(
        chains[chain_id]["chain_kind"] == "application_theme_chain"
        for chain_id in WAVE_E_CHAIN_THEMES
    ) == 2
```

- [ ] **Step 2: Run the focused test and verify the missing constant fails**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_industry_chain_theme_research.py::test_wave_e_chain_registry_and_program_counts_are_frozen
```

Expected: collection or assertion failure because `WAVE_E_CHAIN_THEMES` is not defined and the selected registry still contains 25 entries.

- [ ] **Step 3: Add the Wave E constant and extend the combined registry**

Add after `WAVE_D_CHAIN_THEMES`:

```python
WAVE_E_CHAIN_THEMES = {
    "satellite_communications_navigation_remote_sensing": "satellite_communications_navigation_remote_sensing_value_chain_v1",
    "intelligent_transport_vehicle_road_cloud": "intelligent_transport_vehicle_road_cloud_value_chain_v1",
    "brain_computer_interfaces_neural_engineering": "brain_computer_interfaces_neural_engineering_value_chain_v1",
    "controlled_nuclear_fusion": "controlled_nuclear_fusion_value_chain_v1",
    "quantum_computing_communication_measurement": "quantum_computing_communication_measurement_value_chain_v1",
}

SELECTED_CHAIN_THEMES = {
    **COMPLETED_CHAIN_THEMES,
    **NEXT_FIFTEEN_CHAIN_THEMES,
    **WAVE_D_CHAIN_THEMES,
    **WAVE_E_CHAIN_THEMES,
}
```

- [ ] **Step 4: Update the existing frozen-registry assertion**

Change the expected registry merge to:

```python
assert SELECTED_CHAIN_THEMES == {
    **COMPLETED_CHAIN_THEMES,
    **NEXT_FIFTEEN_CHAIN_THEMES,
    **research.WAVE_D_CHAIN_THEMES,
    **research.WAVE_E_CHAIN_THEMES,
}
```

Change expanded target assertions from `25` to `30` while leaving the default five foundation rows unchanged.

- [ ] **Step 5: Run the registry and catalog tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_industry_chain_theme_research.py \
  tests/test_technology_industry_catalog.py
```

Expected: all tests pass; catalog count remains 82 and the selected target registry reports 30.

- [ ] **Step 6: Commit the frozen Wave E scope**

```bash
rtk git add \
  src/stock_research/industry_chain_theme_research.py \
  tests/test_industry_chain_theme_research.py
rtk git commit -m "feat: register wave e research themes"
```

## Task 2: Add Wave E Manifest And Green Scope Tests

**Files:**

- Create: `artifacts/theme_decomposition/batch_manifests/wave_e_five_industry_chain_themes_v1.json`
- Create: `tests/test_wave_e_industry_chain_themes.py`

- [ ] **Step 1: Create the strict batch manifest**

Use this exact wave and artifact mapping:

```json
{
  "schema_version": "industry_chain_theme_batch_v1",
  "batch_id": "wave_e_five_industry_chain_themes_v1",
  "target_theme_count": 5,
  "artifact_base": "../../..",
  "primary_source_types": ["company_filing", "official_report", "official_article"],
  "completion_gates": {
    "min_accepted_sources": 10,
    "min_primary_sources": 8,
    "min_claims": 12,
    "min_reviewed_mappings": 8,
    "require_node_evidence_matrix_coverage": true,
    "require_bidirectional_evidence_contract": true,
    "require_precise_mapping_locators": true,
    "required_readable_sections": [
      {"name": "研究结论", "non_empty": ["theme:research_profile.investment_summary", "theme:research_profile.industry_stage", "theme:research_profile.central_conflict"]},
      {"name": "价值链", "non_empty": ["theme:research_profile.value_flow_summary", "theme:nodes"]},
      {"name": "利润池与竞争壁垒", "non_empty": ["theme:research_profile.profit_pool_summary"]},
      {"name": "催化、验证信号与风险", "non_empty": ["theme:research_profile.catalyst_claim_ids", "theme:research_profile.risk_claim_ids", "theme:research_profile.validation_signals"]},
      {"name": "受益公司", "non_empty": ["company_mapping:company_mappings"]},
      {"name": "来源证据", "non_empty": ["source_pack:sources"]},
      {"name": "证据缺口与更新", "non_empty": ["theme:research_profile.evidence_gap_summary", "node_evidence_matrix:node_evidence_matrix"]}
    ]
  },
  "waves": {
    "wave_e": [
      "satellite_communications_navigation_remote_sensing",
      "intelligent_transport_vehicle_road_cloud",
      "brain_computer_interfaces_neural_engineering",
      "controlled_nuclear_fusion",
      "quantum_computing_communication_measurement"
    ]
  },
  "themes": {
    "satellite_communications_navigation_remote_sensing": {
      "theme_id": "satellite_communications_navigation_remote_sensing_value_chain_v1",
      "artifacts": {
        "theme": "artifacts/theme_decomposition/satellite_communications_navigation_remote_sensing_value_chain_v1.json",
        "company_mapping": "artifacts/theme_decomposition/company_mappings/satellite_communications_navigation_remote_sensing_company_mapping_v1.json",
        "source_pack": "artifacts/theme_decomposition/source_packs/satellite_communications_navigation_remote_sensing_source_pack_v1.json",
        "node_evidence_matrix": "artifacts/theme_decomposition/source_packs/satellite_communications_navigation_remote_sensing_node_evidence_matrix_v1.json"
      }
    },
    "intelligent_transport_vehicle_road_cloud": {
      "theme_id": "intelligent_transport_vehicle_road_cloud_value_chain_v1",
      "artifacts": {
        "theme": "artifacts/theme_decomposition/intelligent_transport_vehicle_road_cloud_value_chain_v1.json",
        "company_mapping": "artifacts/theme_decomposition/company_mappings/intelligent_transport_vehicle_road_cloud_company_mapping_v1.json",
        "source_pack": "artifacts/theme_decomposition/source_packs/intelligent_transport_vehicle_road_cloud_source_pack_v1.json",
        "node_evidence_matrix": "artifacts/theme_decomposition/source_packs/intelligent_transport_vehicle_road_cloud_node_evidence_matrix_v1.json"
      }
    },
    "brain_computer_interfaces_neural_engineering": {
      "theme_id": "brain_computer_interfaces_neural_engineering_value_chain_v1",
      "artifacts": {
        "theme": "artifacts/theme_decomposition/brain_computer_interfaces_neural_engineering_value_chain_v1.json",
        "company_mapping": "artifacts/theme_decomposition/company_mappings/brain_computer_interfaces_neural_engineering_company_mapping_v1.json",
        "source_pack": "artifacts/theme_decomposition/source_packs/brain_computer_interfaces_neural_engineering_source_pack_v1.json",
        "node_evidence_matrix": "artifacts/theme_decomposition/source_packs/brain_computer_interfaces_neural_engineering_node_evidence_matrix_v1.json"
      }
    },
    "controlled_nuclear_fusion": {
      "theme_id": "controlled_nuclear_fusion_value_chain_v1",
      "artifacts": {
        "theme": "artifacts/theme_decomposition/controlled_nuclear_fusion_value_chain_v1.json",
        "company_mapping": "artifacts/theme_decomposition/company_mappings/controlled_nuclear_fusion_company_mapping_v1.json",
        "source_pack": "artifacts/theme_decomposition/source_packs/controlled_nuclear_fusion_source_pack_v1.json",
        "node_evidence_matrix": "artifacts/theme_decomposition/source_packs/controlled_nuclear_fusion_node_evidence_matrix_v1.json"
      }
    },
    "quantum_computing_communication_measurement": {
      "theme_id": "quantum_computing_communication_measurement_value_chain_v1",
      "artifacts": {
        "theme": "artifacts/theme_decomposition/quantum_computing_communication_measurement_value_chain_v1.json",
        "company_mapping": "artifacts/theme_decomposition/company_mappings/quantum_computing_communication_measurement_company_mapping_v1.json",
        "source_pack": "artifacts/theme_decomposition/source_packs/quantum_computing_communication_measurement_source_pack_v1.json",
        "node_evidence_matrix": "artifacts/theme_decomposition/source_packs/quantum_computing_communication_measurement_node_evidence_matrix_v1.json"
      }
    }
  }
}
```

- [ ] **Step 2: Add a manifest scope test that passes before artifacts exist**

Start `tests/test_wave_e_industry_chain_themes.py` with:

```python
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "artifacts/theme_decomposition/batch_manifests/wave_e_five_industry_chain_themes_v1.json"
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("verify_wave_e_batch", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

WAVE_E_CASES = {
    "satellite_communications_navigation_remote_sensing": "satellite_communications_navigation_remote_sensing_value_chain_v1",
    "intelligent_transport_vehicle_road_cloud": "intelligent_transport_vehicle_road_cloud_value_chain_v1",
    "brain_computer_interfaces_neural_engineering": "brain_computer_interfaces_neural_engineering_value_chain_v1",
    "controlled_nuclear_fusion": "controlled_nuclear_fusion_value_chain_v1",
    "quantum_computing_communication_measurement": "quantum_computing_communication_measurement_value_chain_v1",
}


def _paths(chain_id: str, theme_id: str) -> tuple[Path, Path, Path, Path]:
    return (
        REPOSITORY_ROOT / f"artifacts/theme_decomposition/{theme_id}.json",
        REPOSITORY_ROOT / f"artifacts/theme_decomposition/company_mappings/{chain_id}_company_mapping_v1.json",
        REPOSITORY_ROOT / f"artifacts/theme_decomposition/source_packs/{chain_id}_source_pack_v1.json",
        REPOSITORY_ROOT / f"artifacts/theme_decomposition/source_packs/{chain_id}_node_evidence_matrix_v1.json",
    )


def test_wave_e_manifest_freezes_exact_scope_and_artifact_paths():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["target_theme_count"] == 5
    assert manifest["waves"]["wave_e"] == list(WAVE_E_CASES)
    assert {
        chain_id: row["theme_id"]
        for chain_id, row in manifest["themes"].items()
    } == WAVE_E_CASES
    for chain_id, theme_id in WAVE_E_CASES.items():
        assert tuple(
            (REPOSITORY_ROOT / path).resolve()
            for path in manifest["themes"][chain_id]["artifacts"].values()
        ) == tuple(path.resolve() for path in _paths(chain_id, theme_id))
```

- [ ] **Step 3: Run the scope test and verify it passes without research artifacts**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py
```

Expected: pass. Artifact existence and readiness tests are introduced one theme at a time in Tasks 3-7, so each theme commit can end green.

- [ ] **Step 4: Commit the manifest and green scope test**

```bash
rtk git add \
  artifacts/theme_decomposition/batch_manifests/wave_e_five_industry_chain_themes_v1.json \
  tests/test_wave_e_industry_chain_themes.py
rtk git commit -m "test: freeze wave e research scope"
```

## Task 3: Deliver E1 Satellite Communications, Navigation, And Remote Sensing

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/satellite_communications_navigation_remote_sensing_v1.json`
- Create: `artifacts/technology_industry_catalog/v1/theme_compositions/satellite_communications_navigation_remote_sensing_v1.json`
- Create: `artifacts/theme_decomposition/satellite_communications_navigation_remote_sensing_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/satellite_communications_navigation_remote_sensing_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/satellite_communications_navigation_remote_sensing_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/satellite_communications_navigation_remote_sensing_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_e_industry_chain_themes.py`

Theme node scope:

```python
E1_NODE_IDS = {
    "satellite_capacity_service_access",
    "satellite_ground_access_terminal_integration",
    "satellite_communications_service_delivery",
    "satellite_navigation_pnt_augmentation_services",
    "remote_sensing_data_processing_distribution",
    "satellite_vertical_application_integration",
    "application_operations_utilization_pricing",
    "recurring_service_revenue_validation",
}
```

Required canonical compositions:

```python
E1_COMPOSITIONS = {
    "satellite_capacity_service_access": {"in_orbit_infrastructure_operations"},
    "satellite_ground_access_terminal_integration": {"satellite_ground_tt_c_gateway_terminal_integration"},
    "satellite_communications_service_delivery": {"satellite_service_capacity_revenue_validation"},
    "remote_sensing_data_processing_distribution": {"communication_navigation_remote_sensing_payload_hardware"},
}
```

Primary company research universe: `601698.SH` 中国卫通, `688568.SH` 中科星图, `688066.SH` 航天宏图, `300627.SZ` 华测导航, `002151.SZ` 北斗星通, `300101.SZ` 振芯科技, `002465.SZ` 海格通信, `002405.SZ` 四维图新, `600118.SH` 中国卫星. The last company is a canonical manufacturing dependency and may be indirect or concept-only unless application-service evidence exists.

- [ ] **Step 1: Add failing E1 node, composition, and ownership tests**

Assert the exact `E1_NODE_IDS`, exact composition targets, and these negative boundaries:

```python
assert all(
    row["mapped_node_id"] not in {
        "satellite_platform_bus_final_assembly",
        "satellite_batch_manufacturing_ait_test",
        "constellation_delivery_launch_in_orbit_validation",
    }
    for row in mapping["company_mappings"]
)
assert "制造" not in detail["research_profile"]["investment_summary"] or "归卫星制造链" in detail["research_profile"]["investment_summary"]
```

- [ ] **Step 2: Run the E1 tests and verify missing catalog/artifact failures**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k satellite_communications
```

Expected: failures for missing catalog nodes, composition, theme link, and four research artifacts.

- [ ] **Step 3: Create the application-role catalog nodes and compositions**

Use `node_kind: "application_role"`, empty `canonical_key`, and the composition targets above. The three service nodes owned by the application chain—navigation/PNT service, remote-sensing data distribution, and vertical application integration—must describe service delivery rather than payload or terminal manufacturing.

- [ ] **Step 4: Collect and review primary sources**

Use the latest available 2025 annual reports, exchange filings, and official product/service disclosures for the nine-company universe. Record exact PDF page locators for service/product relationship, materiality, and business stage. Add government or regulator material only for market-access, satellite application, navigation, or remote-sensing policy claims.

- [ ] **Step 5: Build the theme artifact**

Write at least 12 claims covering service-capacity access, communications delivery, PNT augmentation, remote-sensing data processing, vertical applications, utilization, pricing, recurring revenue, catalysts, risks, and the manufacturing/application boundary. Use `artifact_version: "theme_decomposition_v1_6"`, `status: "reviewed"`, `research_kind: "industry_chain_deep_research"`, and `catalog_chain_id: "satellite_communications_navigation_remote_sensing"`.

- [ ] **Step 6: Build mapping, source-pack, and matrix artifacts**

Require three role-specific evidence items per reviewed mapping. A company with payload, satellite, or terminal manufacturing evidence but no application service evidence stays indirect through a canonical reference or concept-only.

- [ ] **Step 7: Add the E1 theme link**

Map every E1 theme node to its same-name catalog application node. Use `unmapped_theme_node_ids: []`. The compositions preserve external canonical ownership and are not duplicated in the link.

- [ ] **Step 8: Run E1, catalog, and dashboard tests**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k satellite_communications \
  tests/test_technology_industry_catalog.py \
  tests/test_dashboard_theme_research.py
```

Expected: E1 is ready; existing satellite-manufacturing tests remain green.

- [ ] **Step 9: Commit E1**

```bash
rtk git add \
  artifacts/technology_industry_catalog/v1/nodes/satellite_communications_navigation_remote_sensing_v1.json \
  artifacts/technology_industry_catalog/v1/theme_compositions/satellite_communications_navigation_remote_sensing_v1.json \
  artifacts/technology_industry_catalog/v1/theme_links.json \
  artifacts/theme_decomposition/satellite_communications_navigation_remote_sensing_value_chain_v1.json \
  artifacts/theme_decomposition/company_mappings/satellite_communications_navigation_remote_sensing_company_mapping_v1.json \
  artifacts/theme_decomposition/source_packs/satellite_communications_navigation_remote_sensing_source_pack_v1.json \
  artifacts/theme_decomposition/source_packs/satellite_communications_navigation_remote_sensing_node_evidence_matrix_v1.json \
  tests/test_wave_e_industry_chain_themes.py
rtk git commit -m "data: add satellite application deep research"
```

## Task 4: Deliver E2 Intelligent Transport Vehicle-Road-Cloud

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/vehicle_road_cloud_supporting_canonical_nodes_v1.json`
- Create: `artifacts/technology_industry_catalog/v1/nodes/intelligent_transport_vehicle_road_cloud_v1.json`
- Create: `artifacts/technology_industry_catalog/v1/theme_compositions/intelligent_transport_vehicle_road_cloud_v1.json`
- Create: `artifacts/theme_decomposition/intelligent_transport_vehicle_road_cloud_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/intelligent_transport_vehicle_road_cloud_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/intelligent_transport_vehicle_road_cloud_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/intelligent_transport_vehicle_road_cloud_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_e_industry_chain_themes.py`

Theme node scope:

```python
E2_NODE_IDS = {
    "vehicle_data_control_interface_role",
    "roadside_perception_signal_control_role",
    "v2x_connectivity_edge_network_role",
    "transport_cloud_data_governance_role",
    "cooperative_driving_traffic_control_applications",
    "fleet_dispatch_mobility_operations",
    "project_integration_delivery_operations",
    "pilot_utilization_renewal_revenue_validation",
}
```

Supporting canonical nodes:

```python
E2_SUPPORTING_CANONICAL_NODES = {
    "vehicle_data_control_interface",
    "roadside_perception_signal_control_infrastructure",
    "v2x_edge_network_infrastructure",
    "transport_cloud_data_platform",
    "transport_data_security_governance",
}
```

Assign the supporting nodes to their existing approved chains: automotive electronics, network equipment/edge IoT, cloud data-center infrastructure, and cybersecurity/data infrastructure. Do not add a chain.

Primary company research universe: `002373.SZ` 千方科技, `300552.SZ` 万集科技, `002869.SZ` 金溢科技, `300098.SZ` 高新兴, `301339.SZ` 通行宝, `300212.SZ` 易华录, `300020.SZ` 银江技术, `002405.SZ` 四维图新, `300496.SZ` 中科创达. Vehicle-component vendors stay canonical dependencies unless they disclose application-specific platform, integration, or operation revenue.

- [ ] **Step 1: Add failing E2 exact-scope and negative-ownership tests**

Assert exact nodes and compositions, and reject mappings whose only evidence is a generic camera, radar, vehicle chip, server, switch, or cloud facility product.

```python
GENERIC_ONLY_NODES = {
    "vehicle_hardware",
    "roadside_hardware",
    "network_hardware",
    "cloud_facility_hardware",
}
assert not ({row["mapped_node_id"] for row in mapping["company_mappings"]} & GENERIC_ONLY_NODES)
```

- [ ] **Step 2: Run the E2 tests and verify the intended failures**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k vehicle_road_cloud
```

Expected: missing supporting nodes, composition, theme link, and artifact failures.

- [ ] **Step 3: Create supporting canonical nodes and application roles**

Use `node_kind: "canonical"` for the five support nodes and `node_kind: "application_role"` for E2 nodes. Every canonical L4 node must own a unique non-empty `canonical_key`; every application role must have an empty `canonical_key` and a matching composition entry where it depends on a support node.

- [ ] **Step 4: Collect company and project evidence**

Use 2025 annual reports and exchange disclosures. For project claims, distinguish framework inclusion, pilot designation, awarded project, delivered system, accepted project, operation/maintenance contract, and recognized revenue. Record project-specific evidence only when the company disclosure names its role or delivered system.

- [ ] **Step 5: Build all four research artifacts**

Write at least 12 claims and eight reviewed mappings across infrastructure, integration, platform, traffic control, fleet/mobility operations, and recurring service economics. The central conflict must state that pilot approval and infrastructure budget do not prove utilization, renewal, or recurring revenue.

- [ ] **Step 6: Add the theme link and composition coverage**

Map all eight E2 theme nodes to same-name application nodes. Verify all role nodes with `canonical_node_refs` have exactly one matching composition record.

- [ ] **Step 7: Run E2 and catalog validation**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k vehicle_road_cloud \
  tests/test_technology_industry_catalog.py \
  tests/test_industry_chain_theme_research.py
```

Expected: E2 is ready and the catalog remains exactly 82 chains.

- [ ] **Step 8: Commit E2**

```bash
rtk git add \
  artifacts/technology_industry_catalog/v1/nodes/vehicle_road_cloud_supporting_canonical_nodes_v1.json \
  artifacts/technology_industry_catalog/v1/nodes/intelligent_transport_vehicle_road_cloud_v1.json \
  artifacts/technology_industry_catalog/v1/theme_compositions/intelligent_transport_vehicle_road_cloud_v1.json \
  artifacts/technology_industry_catalog/v1/theme_links.json \
  artifacts/theme_decomposition/intelligent_transport_vehicle_road_cloud_value_chain_v1.json \
  artifacts/theme_decomposition/company_mappings/intelligent_transport_vehicle_road_cloud_company_mapping_v1.json \
  artifacts/theme_decomposition/source_packs/intelligent_transport_vehicle_road_cloud_source_pack_v1.json \
  artifacts/theme_decomposition/source_packs/intelligent_transport_vehicle_road_cloud_node_evidence_matrix_v1.json \
  tests/test_wave_e_industry_chain_themes.py
rtk git commit -m "data: add vehicle road cloud deep research"
```

## Task 5: Deliver E3 Brain-Computer Interfaces And Neural Engineering

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/brain_computer_interfaces_neural_engineering_v1.json`
- Create: `artifacts/theme_decomposition/brain_computer_interfaces_neural_engineering_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/brain_computer_interfaces_neural_engineering_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/brain_computer_interfaces_neural_engineering_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/brain_computer_interfaces_neural_engineering_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_e_industry_chain_themes.py`

Exact frontier-route scope:

```python
E3_NODE_IDS = {
    "invasive_minimally_invasive_noninvasive_routes",
    "neural_electrodes_sensors_biocompatible_interfaces",
    "bci_signal_acquisition_processing_chips",
    "neural_decoding_encoding_software_platforms",
    "neurostimulation_closed_loop_feedback",
    "implantable_bci_device_systems",
    "noninvasive_bci_device_systems",
    "surgical_clinical_registration_validation",
    "rehabilitation_industrial_consumer_revenue_validation",
}
```

All catalog nodes use `node_kind: "frontier_route"`, empty `canonical_key`, and L3/L4 parent relationships that separate technical route, component, device, validation, and application stages.

Primary company research universe: `688626.SH` 翔宇医疗, `688580.SH` 伟思医疗, `688273.SH` 麦澜德, `301293.SZ` 三博脑科, `300430.SZ` 诚益通, `002173.SZ` 创新医疗, `300793.SZ` 佳禾智能, `300007.SZ` 汉威科技, `300760.SZ` 迈瑞医疗, `300015.SZ` 爱尔眼科. The last two are boundary candidates and cannot be reviewed beneficiaries without a specific neural-interface product, service, clinical, or equipment relationship.

- [ ] **Step 1: Add failing route, stage, and policy-boundary tests**

Require exact node scope and assert the readable output contains these distinctions:

```python
summary = detail["research_profile"]["investment_summary"]
assert "临床" in summary
assert "注册" in detail["research_profile"]["validation_signals"][-1]
assert any("政策" in row["claim_text"] and "公司收入" in row["claim_text"] for row in theme["claims"])
```

Reject reviewed mappings supported only by equity investment, laboratory cooperation, alliance membership, or prototype announcements.

- [ ] **Step 2: Run E3 tests and verify missing-artifact failures**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k brain_computer
```

- [ ] **Step 3: Create frontier-route catalog nodes and the theme link**

Map the nine research nodes to same-name frontier catalog nodes. Use no application composition file and no canonical ownership keys.

- [ ] **Step 4: Collect primary company, regulator, and clinical evidence**

Use annual reports, exchange filings, NMPA registration or public device records, official clinical registrations, hospital or company trial disclosures, and the 2025 seven-department implementation opinion. Separate approved product, registered trial, research prototype, rehabilitation product, strategic investment, and planned product.

- [ ] **Step 5: Build claims and readable research profile**

Write at least 12 claims across route differences, sensing, chips, decoding, stimulation, device systems, registration, clinical endpoints, applications, catalyst milestones, and commercialization risk. Policy targets may support the chain catalyst but never a company mapping.

- [ ] **Step 6: Build evidence-backed company mappings**

Require a disclosed company role in a BCI product, device, service, rehabilitation system, clinical program, or neural-engineering component. When the verified universe has fewer than eight companies, retain the smaller set and keep the theme `draft`; do not weaken the manifest or relabel investments as operating exposure.

- [ ] **Step 7: Run E3 and medical-boundary regressions**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k brain_computer \
  tests/test_wave_d_industry_chain_themes.py -k high_end_medical \
  tests/test_technology_industry_catalog.py
```

Expected: E3 passes only if eight reviewed mappings satisfy strict evidence; otherwise the verifier truthfully reports `researching` and implementation continues evidence collection.

- [ ] **Step 8: Commit E3 only after its verifier row is ready**

```bash
rtk git add \
  artifacts/technology_industry_catalog/v1/nodes/brain_computer_interfaces_neural_engineering_v1.json \
  artifacts/technology_industry_catalog/v1/theme_links.json \
  artifacts/theme_decomposition/brain_computer_interfaces_neural_engineering_value_chain_v1.json \
  artifacts/theme_decomposition/company_mappings/brain_computer_interfaces_neural_engineering_company_mapping_v1.json \
  artifacts/theme_decomposition/source_packs/brain_computer_interfaces_neural_engineering_source_pack_v1.json \
  artifacts/theme_decomposition/source_packs/brain_computer_interfaces_neural_engineering_node_evidence_matrix_v1.json \
  tests/test_wave_e_industry_chain_themes.py
rtk git commit -m "data: add brain computer interface deep research"
```

## Task 6: Deliver E4 Controlled Nuclear Fusion

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/controlled_nuclear_fusion_v1.json`
- Create: `artifacts/theme_decomposition/controlled_nuclear_fusion_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/controlled_nuclear_fusion_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/controlled_nuclear_fusion_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/controlled_nuclear_fusion_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_e_industry_chain_themes.py`

Exact frontier-route scope:

```python
E4_NODE_IDS = {
    "fusion_confinement_route_system_architecture",
    "superconducting_magnets_conductors_cryogenics",
    "pulsed_power_heating_current_drive_control",
    "vacuum_gas_tritium_fuel_cycle_systems",
    "first_wall_blanket_divertor_shielding_materials",
    "plasma_diagnostics_measurement_simulation_control",
    "precision_manufacturing_installation_qualification",
    "facility_integration_commissioning_operations",
    "project_order_delivery_revenue_validation",
}
```

Primary company research universe: `688776.SH` 国光电气, `000969.SZ` 安泰科技, `688122.SH` 西部超导, `600363.SH` 联创光电, `600105.SH` 永鼎股份, `002639.SZ` 雪人股份, `603011.SH` 合锻智能, `002318.SZ` 久立特材, `000962.SZ` 东方钽业, `600353.SH` 旭光电子.

- [ ] **Step 1: Add failing fusion-specific role and fission-boundary tests**

Require exact nodes and assert every reviewed mapping has a fusion-specific product, project, customer, qualification, contract, or delivery reference. Explicitly reject generic nuclear-power equipment or generic superconducting/material capacity as sufficient evidence.

```python
for row in reviewed_mappings:
    summaries = " ".join(evidence_by_id[eid]["evidence_summary"] for eid in row["evidence_ids"])
    assert any(term in summaries for term in ("聚变", "ITER", "托卡马克", "磁约束", "等离子体"))
```

- [ ] **Step 2: Run E4 tests and verify missing-artifact failures**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k controlled_nuclear_fusion
```

- [ ] **Step 3: Create frontier nodes and theme projection**

Separate confinement route, enabling systems, nuclear-facing materials, diagnostics/control, engineering delivery, and revenue validation. Do not create fission equipment nodes in this file.

- [ ] **Step 4: Collect company and project evidence**

Use 2025 annual reports, exchange filings, official company product pages, ITER or domestic scientific-facility procurement/delivery material, and customer or project-owner acceptance records. Distinguish research supply, qualified supplier, signed order, delivered equipment, accepted project, and recognized revenue.

- [ ] **Step 5: Build four synchronized artifacts**

Write at least 12 claims and eight reviewed mappings. The investment summary must identify which nodes can receive orders during the pre-commercial facility phase and which companies remain concept-only because the disclosed product is generic.

- [ ] **Step 6: Run E4, catalog, and nuclear-boundary tests**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k controlled_nuclear_fusion \
  tests/test_technology_industry_catalog.py \
  tests/test_industry_chain_theme_research.py
```

Expected: E4 verifier row is ready; `nuclear_power_equipment` remains an unmodified separate chain.

- [ ] **Step 7: Commit E4**

```bash
rtk git add \
  artifacts/technology_industry_catalog/v1/nodes/controlled_nuclear_fusion_v1.json \
  artifacts/technology_industry_catalog/v1/theme_links.json \
  artifacts/theme_decomposition/controlled_nuclear_fusion_value_chain_v1.json \
  artifacts/theme_decomposition/company_mappings/controlled_nuclear_fusion_company_mapping_v1.json \
  artifacts/theme_decomposition/source_packs/controlled_nuclear_fusion_source_pack_v1.json \
  artifacts/theme_decomposition/source_packs/controlled_nuclear_fusion_node_evidence_matrix_v1.json \
  tests/test_wave_e_industry_chain_themes.py
rtk git commit -m "data: add controlled fusion deep research"
```

## Task 7: Deliver E5 Quantum Computing, Communication, And Measurement

**Files:**

- Create: `artifacts/technology_industry_catalog/v1/nodes/quantum_computing_communication_measurement_v1.json`
- Create: `artifacts/theme_decomposition/quantum_computing_communication_measurement_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/quantum_computing_communication_measurement_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/quantum_computing_communication_measurement_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/quantum_computing_communication_measurement_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_wave_e_industry_chain_themes.py`

Exact frontier-route scope:

```python
E5_NODE_IDS = {
    "quantum_processor_modalities_architecture",
    "quantum_control_laser_microwave_electronics",
    "cryogenic_packaging_interconnect_test",
    "quantum_software_compilation_cloud_access",
    "quantum_communication_qkd_network_services",
    "quantum_sensing_timing_navigation_metrology",
    "standards_testing_deployment_integration",
    "procurement_service_recurring_revenue_validation",
}
```

Primary company research universe: `688027.SH` 国盾量子, `000555.SZ` 神州信息, `002268.SZ` 电科网安, `600941.SH` 中国移动, `002281.SZ` 光迅科技, `300520.SZ` 科大国创, `003029.SZ` 吉大正元, `603019.SH` 中科曙光, `600120.SH` 浙江东方, `688521.SH` 芯原股份. Investment-only and post-quantum cryptography relationships are boundary candidates, not automatic quantum beneficiaries.

- [ ] **Step 1: Add failing sub-route and false-positive tests**

Require exact nodes and prove computing, communication, and measurement are separately represented. Add these exclusions:

```python
assert all(
    row["business_materiality"] != "concept_only"
    for row in reviewed_mappings
)
assert all(
    "参股" not in row["relationship_summary"] or row["review_status"] != "reviewed"
    for row in mapping["company_mappings"]
)
assert any("后量子密码" in row["claim_text"] and "量子硬件" in row["claim_text"] for row in theme["claims"])
```

- [ ] **Step 2: Run E5 tests and verify missing-artifact failures**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k quantum_computing
```

- [ ] **Step 3: Create frontier-route catalog nodes and theme links**

Use no canonical keys. Keep classical compute, conventional network equipment, generic optics, and generic cryogenic equipment in their existing chains unless the evidence names a quantum-specific delivered role.

- [ ] **Step 4: Collect sub-route-specific evidence**

Use annual reports, exchange filings, official product/service pages, carrier procurement or network deployment disclosures, standards/test material, and customer/project records. Label each evidence item as computing, communication, measurement, control/test, or software/service; do not accept a generic `量子科技` label.

- [ ] **Step 5: Build the synchronized research artifacts**

Write at least 12 claims and eight reviewed mappings. The research conclusion must separately state commercialization stage, observable procurement, and revenue evidence for computing, communication, and measurement.

- [ ] **Step 6: Run E5 and digital-infrastructure boundary tests**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_e_industry_chain_themes.py -k quantum_computing \
  tests/test_technology_industry_catalog.py \
  tests/test_dashboard_theme_research.py
```

Expected: E5 is ready and no conventional cybersecurity or network company is promoted without quantum-specific evidence.

- [ ] **Step 7: Commit E5**

```bash
rtk git add \
  artifacts/technology_industry_catalog/v1/nodes/quantum_computing_communication_measurement_v1.json \
  artifacts/technology_industry_catalog/v1/theme_links.json \
  artifacts/theme_decomposition/quantum_computing_communication_measurement_value_chain_v1.json \
  artifacts/theme_decomposition/company_mappings/quantum_computing_communication_measurement_company_mapping_v1.json \
  artifacts/theme_decomposition/source_packs/quantum_computing_communication_measurement_source_pack_v1.json \
  artifacts/theme_decomposition/source_packs/quantum_computing_communication_measurement_node_evidence_matrix_v1.json \
  tests/test_wave_e_industry_chain_themes.py
rtk git commit -m "data: add quantum technology deep research"
```

## Task 8: Add Read-Service, Catalog, And Navigation Acceptance

**Files:**

- Modify: `tests/test_dashboard_theme_research.py`
- Modify: `tests/test_dashboard_technology_industry_catalog.py`
- Modify: `tests/test_wave_e_industry_chain_themes.py`
- Test without editing: `dashboard/tests/theme-research-route.test.tsx`
- Test without editing: `dashboard/tests/theme-research-workspace.test.tsx`

- [ ] **Step 1: Add failing backend endpoint coverage**

Add a parameterized test that calls the read service for all five theme IDs:

```python
@pytest.mark.parametrize("theme_id", WAVE_E_CASES.values())
def test_wave_e_dashboard_read_models_are_complete(theme_id: str):
    detail = get_theme_research_theme(theme_id)
    claims = list_theme_research_claims(theme_id)["items"]
    companies = list_theme_research_companies(theme_id)["items"]
    assert detail["theme_id"] == theme_id
    assert detail["research_profile"]["investment_summary"]
    assert len(claims) >= 12
    assert len(companies) >= 8
    assert all(row["beneficiary_tier"] != "concept_association" for row in companies)
```

Add catalog assertions that each selected chain has its exact `theme_id`, `research_status == "reviewed"`, source count at least 10, and reviewed-company count at least 8.

- [ ] **Step 2: Run backend dashboard tests and verify any missing projection fails**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_wave_e_industry_chain_themes.py
```

- [ ] **Step 3: Make only generic read-model fixes exposed by the tests**

If a test fails because a generic loader omits Wave E, extend the existing registry-based or artifact-discovery path. Do not add theme-ID branches to FastAPI or React. The accepted implementation shape is a shared loop over `SELECTED_CHAIN_THEMES` or automatic artifact discovery.

```python
for chain_id, theme_id in SELECTED_CHAIN_THEMES.items():
    summary = build_chain_research_summary(
        chain_id,
        catalog=catalog,
        theme_context=theme_context,
    )
```

- [ ] **Step 4: Run frontend route and workspace tests**

```bash
rtk pnpm --dir dashboard test -- \
  theme-research-route.test.tsx \
  theme-research-workspace.test.tsx
```

Expected: theme list/detail routes render; company tables have no operation column; clicking a company row navigates to `/tech-bottleneck/stock/<code>?source=theme_research`.

- [ ] **Step 5: Build the dashboard**

```bash
rtk pnpm --dir dashboard build
```

Expected: TypeScript and Vite build exit successfully.

- [ ] **Step 6: Commit only new acceptance changes**

Before staging, run `rtk git status --short`. Do not stage the user's existing modifications in:

- `dashboard/src/components/ThemeResearchWorkspace.tsx`
- `dashboard/src/styles.css`
- `dashboard/tests/theme-research-workspace.test.tsx`

Stage only Wave E backend test changes and any generic loader fix required by a new failing test.

```bash
rtk git add \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_wave_e_industry_chain_themes.py
rtk git commit -m "test: add wave e dashboard acceptance"
```

## Task 9: Full Wave E Verification And Real 5174 Acceptance

**Files:**

- Verify: all Wave E artifacts, shared registries, catalog package, backend routes, and dashboard.
- Modify only when a fresh failing verification identifies a specific defect.

- [ ] **Step 1: Run all A-E wave tests together**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_a_industry_chain_themes.py \
  tests/test_wave_b_industry_chain_themes.py \
  tests/test_wave_c_industry_chain_themes.py \
  tests/test_wave_d_industry_chain_themes.py \
  tests/test_wave_e_industry_chain_themes.py
```

Expected: all wave tests pass; A-D remains 20 themes and Wave E adds five.

- [ ] **Step 2: Run shared artifact, catalog, API, and mapping suites**

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

Expected: all pass; catalog remains 82 and selected total becomes 30.

- [ ] **Step 3: Run the Wave E batch verifier**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  scripts/verify_industry_chain_theme_batch.py \
  --manifest artifacts/theme_decomposition/batch_manifests/wave_e_five_industry_chain_themes_v1.json \
  --wave wave_e --format markdown
```

Expected summary:

```text
Wave E: 5/5 ready
```

- [ ] **Step 4: Verify count semantics directly**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from stock_research.industry_chain_theme_research import (
    COMPLETED_CHAIN_THEMES,
    NEXT_FIFTEEN_CHAIN_THEMES,
    SELECTED_CHAIN_THEMES,
    WAVE_D_CHAIN_THEMES,
    WAVE_E_CHAIN_THEMES,
)
assert len(NEXT_FIFTEEN_CHAIN_THEMES) + len(WAVE_D_CHAIN_THEMES) == 20
assert len(WAVE_E_CHAIN_THEMES) == 5
assert len(COMPLETED_CHAIN_THEMES) == 5
assert len(SELECTED_CHAIN_THEMES) == 30
print("verified: A-D=20, A-E=25, foundation=5, total=30")
PY
```

- [ ] **Step 5: Run frontend tests and build**

```bash
rtk pnpm --dir dashboard test -- \
  theme-research-route.test.tsx \
  theme-research-workspace.test.tsx
rtk pnpm --dir dashboard build
```

- [ ] **Step 6: Inspect the authenticated application on port 5174**

Verify:

- `/theme-research` lists all five Wave E themes without a loading error;
- each Wave E overview renders conclusion, value flow, profit pools, catalysts, risks, and gaps;
- `/nodes`, `/sources`, and `/companies` load for every theme;
- company tables omit the operation column;
- clicking a company row opens `/tech-bottleneck/stock/<code>?source=theme_research`;
- application themes expose dependency boundaries without duplicated company rows;
- desktop and mobile widths have no page-level horizontal overflow.

- [ ] **Step 7: Run final repository hygiene checks**

```bash
rtk git diff --check
rtk git status --short
rtk git log --oneline -12
```

Expected: no whitespace errors; only the user's pre-existing unstaged files remain outside Wave E commits.

- [ ] **Step 8: Request final review before completion**

Review the implementation against:

- `docs/superpowers/specs/2026-07-17-wave-e-frontier-application-theme-research-design.md`;
- the exact five-chain manifest;
- canonical/application/frontier ownership rules;
- evidence precision and concept-association separation;
- A-D 20, A-E 25, and total-pool 30 accounting.

Resolve every Critical or Important finding and rerun the affected verification command before reporting completion.

- [ ] **Step 9: Commit verification-only corrections when present**

If verification required test or artifact corrections, stage only those exact files and commit:

```bash
rtk git commit -m "test: complete wave e acceptance"
```

If no files changed after verification, do not create an empty commit.

## Final Acceptance Checklist

- [ ] Exactly five Wave E chain IDs, all from the approved 82-chain catalog.
- [ ] Two application themes and three frontier themes.
- [ ] Wave A-D remains 20 themes.
- [ ] Wave A-E reports 25 themes.
- [ ] Foundation themes remain five.
- [ ] Total selected priority pool reports 30 themes.
- [ ] Wave E verifier reports 5/5 ready.
- [ ] Every reviewed mapping has direct product/service, materiality, and stage evidence with distinct locators.
- [ ] Concept-only companies never appear in the default beneficiary table.
- [ ] Satellite applications do not duplicate satellite manufacturing.
- [ ] Vehicle-road-cloud does not own generic vehicle, network, roadside, or cloud hardware.
- [ ] Brain-computer mappings distinguish policy, prototype, clinical validation, registration, and revenue.
- [ ] Fusion mappings contain fusion-specific project or product evidence and exclude generic fission exposure.
- [ ] Quantum mappings distinguish computing, communication, measurement, and post-quantum cryptography.
- [ ] Backend, catalog, artifact, frontend, and build verification pass.
- [ ] Real 5174 routes load and company-row navigation works.
- [ ] User-owned unstaged frontend changes remain untouched.
