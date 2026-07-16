# Cloud Data Center Wave B Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete `cloud_data_center_infrastructure_value_chain_v1`, add backward-compatible one-to-many theme-node catalog links, and move Wave B and the next-fifteen batch to full readiness.

**Architecture:** Keep `theme_links.json` as a list of `(theme_node_id, catalog_node_id)` pairs. Relax only the repeated-theme-node restriction, while adding pair uniqueness and single catalog-node ownership. Build the cloud research package as ten readable research nodes whose integrated stages map to twenty finer canonical L3/L4 catalog nodes.

**Tech Stack:** Python 3.14, JSON artifacts, FastAPI read models, pytest, React 19, TypeScript, Vitest, Vite.

---

## File Map

- Modify `src/stock_research/technology_industry_catalog.py`: validate one-to-many link pairs and preserve projections.
- Modify `tests/test_technology_industry_catalog.py`: positive and negative validator coverage.
- Modify `tests/test_dashboard_technology_industry_catalog.py`: cloud catalog-card and projection coverage.
- Create `artifacts/theme_decomposition/cloud_data_center_infrastructure_value_chain_v1.json`: readable ten-node theme and claims.
- Create `artifacts/theme_decomposition/company_mappings/cloud_data_center_infrastructure_company_mapping_v1.json`: company evidence and reviewed mappings.
- Create `artifacts/theme_decomposition/source_packs/cloud_data_center_infrastructure_source_pack_v1.json`: accepted primary-source package.
- Create `artifacts/theme_decomposition/source_packs/cloud_data_center_infrastructure_node_evidence_matrix_v1.json`: node/source/claim matrix.
- Modify `artifacts/technology_industry_catalog/v1/theme_links.json`: twenty canonical catalog links plus four unmapped research nodes.
- Modify `tests/test_wave_b_industry_chain_themes.py`: cloud package, semantic-boundary, mapping, and Wave B readiness tests.
- Modify `tests/test_dashboard_theme_research.py`: dashboard index/detail/company routes.
- Modify `dashboard/tests/theme-research-route.test.tsx`: frontend route acceptance if the current dynamic route test does not already cover the cloud theme.

## Task 1: Support One Research Node Mapping To Multiple Catalog Nodes

**Files:**
- Modify: `src/stock_research/technology_industry_catalog.py:1187-1227`
- Test: `tests/test_technology_industry_catalog.py:1120-1180`

- [ ] **Step 1: Write the failing positive one-to-many test**

Add this test beside the existing stable-domain-error parametrization:

```python
def test_theme_link_allows_one_theme_node_to_map_to_multiple_catalog_nodes(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    links = [
        _theme_link(
            node_links=[
                {
                    "theme_node_id": "theme_lithography",
                    "catalog_node_id": "lithography",
                },
                {
                    "theme_node_id": "theme_lithography",
                    "catalog_node_id": "duv_lithography",
                },
            ],
            unmapped_theme_node_ids=["unmapped_theme_node"],
        )
    ]
    _write_json(root / "theme_links.json", {"theme_links": links})

    catalog = load_industry_catalog(root)

    assert catalog["theme_links"][0]["node_links"] == links[0]["node_links"]
```

- [ ] **Step 2: Run the positive test and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_technology_industry_catalog.py::test_theme_link_allows_one_theme_node_to_map_to_multiple_catalog_nodes -q
```

Expected: fail with `THEME_CATALOG_NODE_LINK_INVALID` because the current validator rejects the repeated `theme_node_id`.

- [ ] **Step 3: Replace the old duplicate-theme-node negative case with exact duplicate-pair and catalog-ownership cases**

Keep the existing cross-chain and missing-node cases. Replace the repeated-theme-node case with:

```python
(
    [
        _theme_link(
            node_links=[
                {
                    "theme_node_id": "theme_lithography",
                    "catalog_node_id": "lithography",
                },
                {
                    "theme_node_id": "theme_lithography",
                    "catalog_node_id": "lithography",
                },
            ]
        )
    ],
    "THEME_CATALOG_NODE_LINK_INVALID",
),
(
    [
        _theme_link(
            node_links=[
                {
                    "theme_node_id": "theme_lithography",
                    "catalog_node_id": "lithography",
                },
                {
                    "theme_node_id": "unmapped_theme_node",
                    "catalog_node_id": "lithography",
                },
            ],
            unmapped_theme_node_ids=[],
        )
    ],
    "THEME_CATALOG_NODE_LINK_INVALID",
),
```

Add a focused assertion that the error text contains the offending JSON path and pair.

- [ ] **Step 4: Implement pair and catalog-node uniqueness**

Replace the local `theme_node_ids` uniqueness rule with three sets:

```python
linked_theme_node_ids: set[str] = set()
seen_pairs: set[tuple[str, str]] = set()
linked_catalog_node_ids: set[str] = set()
```

Inside the loop, validate with:

```python
pair = (theme_node_id, catalog_node_id)
if (
    pair in seen_pairs
    or catalog_node_id in linked_catalog_node_ids
    or catalog_node is None
    or catalog_node.get("level") not in NODE_LEVELS
    or catalog_node.get("chain_id") != chain_id
):
    raise _theme_catalog_node_link_error(
        f"{node_link_path} invalid: {theme_node_id} -> {catalog_node_id}"
    )
seen_pairs.add(pair)
linked_catalog_node_ids.add(catalog_node_id)
linked_theme_node_ids.add(theme_node_id)
```

Return `linked_theme_node_ids` so the existing linked/unmapped coverage rule remains unchanged.

- [ ] **Step 5: Add a projection-preservation test**

Create a test theme whose `theme_lithography` node maps to `lithography` and `duv_lithography`, call `project_theme_to_catalog()`, and assert:

```python
assert [
    row["catalog_node"]["node_id"] for row in projection["node_projections"]
] == ["lithography", "duv_lithography"]
assert {
    row["theme_node"]["node_id"] for row in projection["node_projections"]
} == {"theme_lithography"}
```

- [ ] **Step 6: Run catalog tests and verify GREEN**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_technology_industry_catalog.py \
  tests/test_dashboard_technology_industry_catalog.py -q
```

Expected: all tests pass; one-to-many projection contains both catalog leaves.

- [ ] **Step 7: Commit the validator change**

```bash
rtk git add \
  src/stock_research/technology_industry_catalog.py \
  tests/test_technology_industry_catalog.py \
  tests/test_dashboard_technology_industry_catalog.py
rtk git commit -m "feat: support one-to-many theme catalog links"
```

## Task 2: Add Cloud Deep-Research RED Tests

**Files:**
- Modify: `tests/test_wave_b_industry_chain_themes.py`
- Modify: `tests/test_dashboard_theme_research.py`

- [ ] **Step 1: Add cloud artifact constants**

Add exact constants:

```python
CLOUD_CHAIN_ID = "cloud_data_center_infrastructure"
CLOUD_THEME_ID = "cloud_data_center_infrastructure_value_chain_v1"
CLOUD_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{CLOUD_THEME_ID}.json"
CLOUD_MAPPING_PATH = REPOSITORY_ROOT / "artifacts/theme_decomposition/company_mappings/cloud_data_center_infrastructure_company_mapping_v1.json"
CLOUD_SOURCE_PACK_PATH = REPOSITORY_ROOT / "artifacts/theme_decomposition/source_packs/cloud_data_center_infrastructure_source_pack_v1.json"
CLOUD_MATRIX_PATH = REPOSITORY_ROOT / "artifacts/theme_decomposition/source_packs/cloud_data_center_infrastructure_node_evidence_matrix_v1.json"
```

- [ ] **Step 2: Write the missing-four-artifacts test**

```python
def test_cloud_data_center_four_artifacts_exist_before_validation():
    assert CLOUD_THEME_PATH.is_file()
    assert CLOUD_MAPPING_PATH.is_file()
    assert CLOUD_SOURCE_PACK_PATH.is_file()
    assert CLOUD_MATRIX_PATH.is_file()
```

- [ ] **Step 3: Write exact node and count tests**

Use this frozen node set:

```python
CLOUD_NODE_IDS = {
    "facility_systems_modular_deployment",
    "power_availability_electrical_architecture_dependency",
    "backup_power_storage_resilience_dependency",
    "thermal_liquid_cooling_systems",
    "heat_rejection_chillers_pumps_recovery",
    "water_refrigerant_environmental_constraints",
    "dcim_monitoring_energy_management",
    "design_integration_epc_commissioning",
    "facility_operations_lifecycle_services",
    "customer_deployment_utilization_validation",
}
```

Assert:

```python
theme = load_theme_package(CLOUD_THEME_PATH)
mapping = load_theme_company_mapping_package(CLOUD_MAPPING_PATH)
report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_b")
cloud_row = next(row for row in report["theme_results"] if row["chain_id"] == CLOUD_CHAIN_ID)

assert {row["node_id"] for row in theme["nodes"]} == CLOUD_NODE_IDS
assert len(theme["sources"]) == 11
assert len(theme["claims"]) == 13
assert len([row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"]) == 11
assert cloud_row["ready"] is True
assert cloud_row["accepted_source_count"] == 11
assert cloud_row["primary_source_count"] == 11
assert cloud_row["claim_count"] == 13
assert cloud_row["reviewed_mapping_count"] == 11
```

- [ ] **Step 4: Write the exact one-to-many link test**

Freeze the approved mapping as a dictionary of research node to catalog-node set:

```python
EXPECTED_CLOUD_CATALOG_LINKS = {
    "facility_systems_modular_deployment": {
        "data_center_facility_systems_services",
        "modular_data_center_system",
    },
    "thermal_liquid_cooling_systems": {
        "data_center_cold_plate",
        "immersion_cooling_system",
        "spray_cooling_system",
        "coolant_distribution_unit",
        "liquid_cooling_quick_connector",
        "liquid_cooling_pipe_system",
        "data_center_coolant",
        "liquid_cooling_leak_detection_system",
    },
    "heat_rejection_chillers_pumps_recovery": {
        "data_center_chiller",
        "liquid_cooling_pump",
        "data_center_heat_exchanger",
        "data_center_waste_heat_recovery_system",
    },
    "dcim_monitoring_energy_management": {
        "data_center_infrastructure_management_platform",
    },
    "design_integration_epc_commissioning": {
        "data_center_electrical_design_service",
        "liquid_cooling_integration_service",
        "data_center_epc_service",
        "data_center_commissioning_certification_service",
    },
    "facility_operations_lifecycle_services": {
        "data_center_facility_operations_service",
    },
}
```

Build `actual` without collapsing pairs:

```python
actual: dict[str, set[str]] = {}
for row in link["node_links"]:
    actual.setdefault(row["theme_node_id"], set()).add(row["catalog_node_id"])
assert actual == EXPECTED_CLOUD_CATALOG_LINKS
assert set(link["unmapped_theme_node_ids"]) == {
    "power_availability_electrical_architecture_dependency",
    "backup_power_storage_resilience_dependency",
    "water_refrigerant_environmental_constraints",
    "customer_deployment_utilization_validation",
}
```

- [ ] **Step 5: Write semantic-boundary tests**

Require every source-node pair to have a node-specific claim, excluding the broad value-flow and maturity-boundary claims. Require every reviewed mapping to contain product, revenue/materiality, and risk/stage evidence. Lock these statements in claims or mapping notes:

```python
assert "液冷收入未单独披露" in serialized_mapping
assert "数据中心收入未单独披露" in serialized_mapping
assert "AI数据中心" not in unsupported_revenue_attribution
assert "定点、认证、样品或项目建设不等于稳定规模收入" in serialized_theme
assert "power_electronics_power_supply_equipment" in serialized_theme
assert "new_energy_storage" in serialized_theme
assert "industrial_software" in serialized_theme
```

The test must derive direct support from explicit `node_id -> claim_ids` sets, not from claim numbering or node sorting.

- [ ] **Step 6: Write dashboard index/detail/company RED tests**

Add `CLOUD_THEME_ID` to the expected theme set. Assert:

```python
client = TestClient(dashboard_app.create_app())
assert client.get(f"/api/research/theme-decomposition/themes/{CLOUD_THEME_ID}").status_code == 200
companies = client.get(f"/api/research/theme-decomposition/themes/{CLOUD_THEME_ID}/companies")
assert companies.status_code == 200
assert companies.json()["total"] == 11
```

- [ ] **Step 7: Run the tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_wave_b_industry_chain_themes.py \
  tests/test_dashboard_theme_research.py -q
```

Expected: fail because the four cloud artifacts do not exist and the dashboard index contains nineteen rather than twenty themes.

## Task 3: Build The Four Cloud Research Artifacts

**Files:**
- Create: `artifacts/theme_decomposition/cloud_data_center_infrastructure_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/cloud_data_center_infrastructure_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/cloud_data_center_infrastructure_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/cloud_data_center_infrastructure_node_evidence_matrix_v1.json`

- [ ] **Step 1: Reuse the verified primary-source set**

Use eleven 2025 annual reports, preferring sources already present and verified in `ai_power_source_pack_v1.json` where applicable:

```text
英维克 002837.SZ — liquid-cooling portfolio and broad machine-room temperature-control revenue
高澜股份 300499.SZ — data-center liquid cooling and customer validation, revenue not isolated
申菱环境 301018.SZ — data-center cooling products and broad special-air-conditioning revenue
冰轮环境 000811.SZ — data-center chillers/heat exchange inside broad refrigeration revenue
科华数据 002335.SZ — data-center products, power/facility delivery, and broad revenue boundary
润泽科技 300442.SZ — data-center construction, capacity, operations, and utilization
中恒电气 002364.SZ — data-center power and monitoring dependency, not facility-owned revenue
佳力图 603912.SH — data-center environmental-control equipment and service boundary
依米康 300249.SZ — data-center environmental systems, integration, and broad revenue
润建股份 002929.SZ — computing-center construction/operations services and order boundary
数据港 603881.SH — data-center operations and utilization/customer concentration
```

Every URL, publish date, publisher, product locator, revenue locator, and risk locator must be rechecked against the original annual report before writing the artifact. If one report cannot support a direct node claim, replace it with another primary filing rather than weakening the test.

- [ ] **Step 2: Write the theme artifact**

Use `artifact_version: cloud_data_center_infrastructure_value_chain_v1`, `status: reviewed`, the ten frozen node IDs, thirteen reviewed claims, and a research profile containing:

```json
{
  "catalog_chain_id": "cloud_data_center_infrastructure",
  "research_kind": "industry_chain_deep_research",
  "industry_stage": "AI与云工作负载提高机柜功率密度，设施交付从传统风冷机房转向液冷、模块化和全生命周期运营，但产品能力、项目交付与稳定收入必须分开验证。",
  "central_conflict": "高功率密度推动冷却与设施投资，但宽数据中心、温控、工程和运营收入容易被误当作单一液冷或AI数据中心收入。",
  "value_flow_summary": "容量与选址 -> 设施与模块化部署 -> 冷却和热排放 -> 监控管理 -> 设计集成交付 -> 调试认证 -> 运营与客户利用率",
  "profit_pool_summary": "液冷关键部件、系统集成、交付认证、客户绑定和高利用率运营形成利润池；宽口径收入和项目波动是主要证据风险。",
  "evidence_gap_summary": "液冷、AI数据中心、DCIM、调试和运维的独立收入披露不足，客户定点与项目建设不能替代稳定收入验证。"
}
```

All thirteen claims must be used by at least one readable section. Claims must cover value flow, facility/modular systems, liquid cooling, heat rejection, DCIM, design/EPC/commissioning, operations, utilization, cross-chain power/storage/software ownership, catalysts, risks, and evidence gaps.

- [ ] **Step 3: Write company mapping evidence**

Create exactly eleven reviewed mappings. Assign tiers from the annual-report evidence, with these hard boundaries:

```text
英维克、高澜股份: direct liquid-cooling product relationship; broad revenue must not be called pure liquid-cooling revenue
申菱环境、冰轮环境、佳力图、依米康: cooling/environmental equipment or integration; data-center-only revenue may be undisclosed
科华数据: facility/power/delivery dependency; do not move UPS ownership out of power electronics
润泽科技、数据港: facility operations/capacity/utilization; customer concentration and utilization risk explicit
润建股份: construction/operations service; order or project value is not recurring revenue
中恒电气: indirect electrical/monitoring dependency; canonical ownership stays outside the cloud facility chain
```

Each mapping must reference three evidence items:

```json
[
  {"evidence_type": "product_relationship"},
  {"evidence_type": "revenue_materiality"},
  {"evidence_type": "risk_or_stage"}
]
```

Use `elastic_beneficiary` for direct products with undisclosed narrow revenue, `core_beneficiary` only where the mapped facility business is a material disclosed segment, and `indirect_beneficiary` for cross-chain electrical dependencies.

- [ ] **Step 4: Write the source pack and matrix**

Use the exact supported versions required by the shared verifier. For every accepted source:

- `supported_claim_ids` must name claims actually supported by the cited pages.
- `supported_node_ids` must equal the union of nodes reached through those node-specific claims.
- Broad value-flow or maturity claims cannot be the only reason for a source-node link.

For every one of the ten matrix rows:

- use valid shared enums and score fields;
- keep `evidence_strength_after` within 0..5;
- include accepted sources and node-specific claims for reviewed nodes;
- set explicit `evidence_gap_status` for unmapped/cross-chain nodes whose independent revenue remains unavailable.

- [ ] **Step 5: Run focused artifact tests and verify GREEN**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_wave_b_industry_chain_themes.py \
  tests/test_dashboard_theme_research.py \
  tests/test_verify_industry_chain_theme_batch.py -q
```

Expected: cloud row ready with 11 accepted sources, 11 primary sources, 13 claims, and 11 reviewed mappings.

- [ ] **Step 6: Commit the cloud research artifacts**

```bash
rtk git add \
  artifacts/theme_decomposition/cloud_data_center_infrastructure_value_chain_v1.json \
  artifacts/theme_decomposition/company_mappings/cloud_data_center_infrastructure_company_mapping_v1.json \
  artifacts/theme_decomposition/source_packs/cloud_data_center_infrastructure_source_pack_v1.json \
  artifacts/theme_decomposition/source_packs/cloud_data_center_infrastructure_node_evidence_matrix_v1.json \
  tests/test_wave_b_industry_chain_themes.py \
  tests/test_dashboard_theme_research.py
rtk git commit -m "data: add cloud data center deep research"
```

## Task 4: Add The Approved Twenty Catalog Links

**Files:**
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `tests/test_dashboard_technology_industry_catalog.py`
- Modify: `tests/test_wave_b_industry_chain_themes.py`

- [ ] **Step 1: Replace the empty cloud theme link**

Write twenty `node_links` pairs from `EXPECTED_CLOUD_CATALOG_LINKS`, preserving catalog order. Set:

```json
"unmapped_theme_node_ids": [
  "power_availability_electrical_architecture_dependency",
  "backup_power_storage_resilience_dependency",
  "water_refrigerant_environmental_constraints",
  "customer_deployment_utilization_validation"
]
```

Add notes that explicitly preserve ownership of power equipment, storage, grid, and generic software on their canonical chains and explain that repeated research-node IDs represent a complete family/stage decomposition.

- [ ] **Step 2: Add dashboard catalog projection assertions**

Assert the cloud chain card reports the theme ID, twenty node links, four unmapped research nodes, and that each catalog node projects to the expected research node without pair loss.

- [ ] **Step 3: Run catalog and Wave B tests**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_technology_industry_catalog.py \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_wave_b_industry_chain_themes.py -q
```

Expected: all pass; Wave B reports 5/5 ready.

- [ ] **Step 4: Commit the cloud links**

```bash
rtk git add \
  artifacts/technology_industry_catalog/v1/theme_links.json \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_wave_b_industry_chain_themes.py
rtk git commit -m "data: link cloud research to catalog nodes"
```

## Task 5: Full Batch, Frontend, And Browser Acceptance

**Files:**
- Modify only if required by a failing route assertion: `dashboard/tests/theme-research-route.test.tsx`
- No production frontend change is expected.

- [ ] **Step 1: Run backend coverage**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_wave_a_industry_chain_themes.py \
  tests/test_wave_b_industry_chain_themes.py \
  tests/test_wave_c_industry_chain_themes.py \
  tests/test_verify_industry_chain_theme_batch.py \
  tests/test_theme_decomposition.py \
  tests/test_theme_company_mapping.py \
  tests/test_industry_chain_theme_research.py \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_theme_research_context.py \
  tests/test_dashboard_theme_research_context_api.py \
  tests/test_dashboard_theme_research_db.py \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_technology_industry_catalog.py \
  tests/test_technology_industry_catalog_pilots.py \
  tests/test_technology_industry_catalog_skeleton.py
```

Expected: zero failures.

- [ ] **Step 2: Verify Wave B and the full batch**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  scripts/verify_industry_chain_theme_batch.py \
  --manifest artifacts/theme_decomposition/batch_manifests/next_fifteen_industry_chain_themes_v1.json \
  --wave wave_b --format markdown

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  scripts/verify_industry_chain_theme_batch.py \
  --manifest artifacts/theme_decomposition/batch_manifests/next_fifteen_industry_chain_themes_v1.json \
  --format markdown
```

Expected: Wave B `5/5 ready`; full batch `15/15 ready`.

- [ ] **Step 3: Run frontend tests and build**

```bash
cd dashboard
rtk pnpm test -- theme-research-route.test.tsx theme-research-workspace.test.tsx
rtk pnpm build
```

Expected: all tests pass and Vite build exits 0.

- [ ] **Step 4: Inspect the 5174 application**

Use the in-app browser to verify:

1. `/theme-research` lists the cloud theme.
2. `/theme-research/cloud_data_center_infrastructure_value_chain_v1` renders all seven readable sections.
3. The companies tab lists eleven companies and row click opens the stock workspace.
4. Industry Catalog cloud nodes deep-link to the cloud theme without losing repeated one-to-many pairs.
5. No console error appears during list, detail, company, or catalog navigation.

- [ ] **Step 5: Run final repository checks**

```bash
rtk git diff --check
rtk git status --short
```

Expected: only the user's pre-existing dashboard edits and untracked older plan remain outside the committed task scope.

- [ ] **Step 6: Request independent reviews**

Run spec review first and code/data quality review second. Fix every Critical or Important finding through a failing regression test and re-review until both reports have zero Critical and Important findings.

- [ ] **Step 7: Request Wave B final review**

The final reviewer must confirm:

- Wave B 5/5 and full batch 15/15.
- One-to-many links preserve all pairs.
- No catalog-node duplicate ownership or cross-chain link exists.
- Cloud source, claim, matrix, and mapping relationships are exact.
- Company tiers and narrow-revenue boundaries are readable and defensible.
- Waves A and C remain ready.

- [ ] **Step 8: Commit any final test-only adjustments**

Stage only task-owned files and use a scoped message such as:

```bash
rtk git commit -m "test: complete wave b cloud acceptance"
```

