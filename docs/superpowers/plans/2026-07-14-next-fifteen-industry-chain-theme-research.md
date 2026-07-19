# Next Fifteen Industry-Chain Themes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the next fifteen evidence-backed deep Theme Research packages, expanding the current five-theme foundation into a twenty-theme priority pool while keeping the Industry Catalog as the structural directory and the Stock Workspace as the downstream handoff.

**Architecture:** Reuse the existing `theme_decomposition_v1_6` deep-research contract, beneficiary-tier rules, catalog-to-theme adapter, and DB import path. Add one manifest that freezes the next-fifteen scope, generalize verification from the fixed five-theme script into a manifest-driven batch verifier, then ship the fifteen themes in three waves of five with identical evidence gates, route behavior, and database acceptance.

**Tech Stack:** Python 3.14, JSON artifacts, FastAPI, PostgreSQL/psycopg, pytest, React 19, TypeScript, Vitest, Testing Library, Playwright, Vite.

---

## File Map

### Shared orchestration and verification

- Create `artifacts/theme_decomposition/batch_manifests/next_fifteen_industry_chain_themes_v1.json`: canonical scope, batch order, file names, and acceptance gates.
- Create `scripts/verify_industry_chain_theme_batch.py`: manifest-driven verifier for any selected theme batch.
- Create `tests/test_verify_industry_chain_theme_batch.py`: batch-manifest and verifier coverage.
- Modify `src/stock_research/industry_chain_theme_research.py`: extend selected-chain registry from five completed themes to the twenty-theme target pool.
- Modify `tests/test_industry_chain_theme_research.py`: registry and catalog-summary coverage for the next-fifteen expansion.
- Modify `docs/five_priority_industry_chain_theme_research_v1.md`: split “completed five” from “target pool twenty”.

### Catalog and backend read models

- Modify `artifacts/technology_industry_catalog/v1/theme_links.json`: add fifteen `chain_id -> theme_id` deep-theme links.
- Modify `src/stock_research/dashboard/theme_research.py`: keep route/read-model compatibility with the expanded registry.
- Modify `tests/test_dashboard_theme_research.py`: manifest-backed route/list/detail coverage for all twenty target themes.
- Modify `tests/test_dashboard_technology_industry_catalog.py`: catalog-card and deep-link coverage for newly linked chains.

### Theme artifacts, mapping artifacts, and evidence packs

- Create 15 theme artifacts under `artifacts/theme_decomposition/`:
  - `ai_logic_compute_chips_value_chain_v1.json`
  - `optical_communications_data_center_interconnect_value_chain_v1.json`
  - `semiconductor_materials_electronic_chemicals_value_chain_v1.json`
  - `power_semiconductors_value_chain_v1.json`
  - `industrial_automation_control_value_chain_v1.json`
  - `semiconductor_packaging_test_advanced_packaging_value_chain_v1.json`
  - `cloud_data_center_infrastructure_value_chain_v1.json`
  - `new_power_system_smart_grid_value_chain_v1.json`
  - `core_mechanical_components_value_chain_v1.json`
  - `industrial_inspection_metrology_machine_vision_value_chain_v1.json`
  - `industrial_robots_value_chain_v1.json`
  - `power_batteries_battery_materials_value_chain_v1.json`
  - `intelligent_driving_smart_cockpit_value_chain_v1.json`
  - `automotive_electronics_chip_applications_value_chain_v1.json`
  - `commercial_space_launch_value_chain_v1.json`
- Create 15 company-mapping artifacts under `artifacts/theme_decomposition/company_mappings/`, one per chain id.
- Create 15 source packs and 15 node-evidence matrices under `artifacts/theme_decomposition/source_packs/`.

### Frontend and browser acceptance

- Modify `dashboard/tests/theme-research-route.test.tsx`: all new routes resolve and preserve current workspace semantics.
- Create `dashboard/tests/next-fifteen-industry-chain-deep-research.spec.ts`: browser acceptance across all three waves.

### Documentation and import runbook

- Create `docs/next_fifteen_industry_chain_theme_research_v1.md`: operator guide, wave order, and evidence policy.
- Modify `docs/theme_research_dashboard_v1.md`: list the twenty-theme target pool and explain staged rollout.

## Scope Freeze

The next fifteen themes are frozen as:

```python
NEXT_FIFTEEN_CHAIN_THEMES = {
    "ai_logic_compute_chips": "ai_logic_compute_chips_value_chain_v1",
    "optical_communications_data_center_interconnect": "optical_communications_data_center_interconnect_value_chain_v1",
    "semiconductor_materials_electronic_chemicals": "semiconductor_materials_electronic_chemicals_value_chain_v1",
    "power_semiconductors": "power_semiconductors_value_chain_v1",
    "industrial_automation_control": "industrial_automation_control_value_chain_v1",
    "semiconductor_packaging_test_advanced_packaging": "semiconductor_packaging_test_advanced_packaging_value_chain_v1",
    "cloud_data_center_infrastructure": "cloud_data_center_infrastructure_value_chain_v1",
    "new_power_system_smart_grid": "new_power_system_smart_grid_value_chain_v1",
    "core_mechanical_components": "core_mechanical_components_value_chain_v1",
    "industrial_inspection_metrology_machine_vision": "industrial_inspection_metrology_machine_vision_value_chain_v1",
    "industrial_robots": "industrial_robots_value_chain_v1",
    "power_batteries_battery_materials": "power_batteries_battery_materials_value_chain_v1",
    "intelligent_driving_smart_cockpit": "intelligent_driving_smart_cockpit_value_chain_v1",
    "automotive_electronics_chip_applications": "automotive_electronics_chip_applications_value_chain_v1",
    "commercial_space_launch": "commercial_space_launch_value_chain_v1",
}
```

Wave order is frozen as:

```python
WAVE_A = [
    "ai_logic_compute_chips",
    "optical_communications_data_center_interconnect",
    "semiconductor_materials_electronic_chemicals",
    "power_semiconductors",
    "industrial_automation_control",
]
WAVE_B = [
    "semiconductor_packaging_test_advanced_packaging",
    "cloud_data_center_infrastructure",
    "new_power_system_smart_grid",
    "core_mechanical_components",
    "industrial_inspection_metrology_machine_vision",
]
WAVE_C = [
    "industrial_robots",
    "power_batteries_battery_materials",
    "intelligent_driving_smart_cockpit",
    "automotive_electronics_chip_applications",
    "commercial_space_launch",
]
```

Every theme in all three waves must satisfy the same completion gate:

```python
MIN_ACCEPTED_SOURCES = 10
MIN_PRIMARY_SOURCES = 4
MIN_CLAIMS = 10
MIN_REVIEWED_MAPPINGS = 8
REQUIRED_SECTIONS = [
    "研究结论",
    "价值链",
    "利润池与竞争壁垒",
    "催化、验证信号与风险",
    "受益公司",
    "来源证据",
    "证据缺口与更新",
]
```

## Task 1: Freeze Scope And Generalize Batch Verification

**Files:**
- Create: `artifacts/theme_decomposition/batch_manifests/next_fifteen_industry_chain_themes_v1.json`
- Create: `scripts/verify_industry_chain_theme_batch.py`
- Create: `tests/test_verify_industry_chain_theme_batch.py`
- Modify: `src/stock_research/industry_chain_theme_research.py`
- Modify: `tests/test_industry_chain_theme_research.py`

- [ ] **Step 1: Write the failing manifest and registry tests**

Add tests that freeze the next-fifteen scope exactly:

```python
assert manifest["batch_id"] == "next_fifteen_industry_chain_themes_v1"
assert manifest["target_theme_count"] == 15
assert manifest["waves"]["wave_a"] == [
    "ai_logic_compute_chips",
    "optical_communications_data_center_interconnect",
    "semiconductor_materials_electronic_chemicals",
    "power_semiconductors",
    "industrial_automation_control",
]
assert registry["commercial_space_launch"] == "commercial_space_launch_value_chain_v1"
```

Also add verifier tests that fail when one theme drops below `10` accepted sources, `10` claims, or `8` reviewed mappings.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_industry_chain_theme_research.py \
  tests/test_verify_industry_chain_theme_batch.py -q
```

Expected: failure because the manifest file, batch verifier, and expanded registry do not exist yet.

- [ ] **Step 3: Add the manifest**

Create:

```json
{
  "batch_id": "next_fifteen_industry_chain_themes_v1",
  "target_theme_count": 15,
  "waves": {
    "wave_a": [
      "ai_logic_compute_chips",
      "optical_communications_data_center_interconnect",
      "semiconductor_materials_electronic_chemicals",
      "power_semiconductors",
      "industrial_automation_control"
    ],
    "wave_b": [
      "semiconductor_packaging_test_advanced_packaging",
      "cloud_data_center_infrastructure",
      "new_power_system_smart_grid",
      "core_mechanical_components",
      "industrial_inspection_metrology_machine_vision"
    ],
    "wave_c": [
      "industrial_robots",
      "power_batteries_battery_materials",
      "intelligent_driving_smart_cockpit",
      "automotive_electronics_chip_applications",
      "commercial_space_launch"
    ]
  }
}
```

- [ ] **Step 4: Implement the manifest-driven verifier**

Expose:

```python
def load_theme_batch_manifest(path: str | Path) -> dict[str, Any]: ...
def build_theme_batch_report(manifest_path: str | Path) -> dict[str, Any]: ...
def assert_theme_batch_ready(report: dict[str, Any]) -> None: ...
```

The verifier must read the manifest, load each theme artifact plus company-mapping file, compute source/claim/mapping counts, and emit a per-wave readiness summary without touching PostgreSQL.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_industry_chain_theme_research.py \
  tests/test_verify_industry_chain_theme_batch.py -q
```

Commit:

```bash
rtk git add \
  artifacts/theme_decomposition/batch_manifests/next_fifteen_industry_chain_themes_v1.json \
  scripts/verify_industry_chain_theme_batch.py \
  tests/test_verify_industry_chain_theme_batch.py \
  src/stock_research/industry_chain_theme_research.py \
  tests/test_industry_chain_theme_research.py
rtk git commit -m "feat: add next fifteen theme batch verifier"
```

## Task 2: Wire The Fifteen Themes Into Catalog And Read Models

**Files:**
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `src/stock_research/dashboard/theme_research.py`
- Modify: `tests/test_dashboard_theme_research.py`
- Modify: `tests/test_dashboard_technology_industry_catalog.py`
- Modify: `dashboard/tests/theme-research-route.test.tsx`

- [ ] **Step 1: Write the failing catalog and route tests**

Add expectations like:

```python
assert "ai_logic_compute_chips_value_chain_v1" in {
    row["theme_id"] for row in list_theme_research_themes(read_source="artifact")["items"]
}
assert links["ai_logic_compute_chips_value_chain_v1"]["chain_id"] == "ai_logic_compute_chips"
assert links["commercial_space_launch_value_chain_v1"]["chain_id"] == "commercial_space_launch"
```

And in the frontend route test:

```ts
expect(parseThemeResearchRoute('/theme-research/ai_logic_compute_chips_value_chain_v1')).toEqual({
  themeId: 'ai_logic_compute_chips_value_chain_v1',
  tab: 'overview',
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py -q
rtk pnpm --dir dashboard exec vitest run tests/theme-research-route.test.tsx
```

Expected: failures because the fifteen theme ids are not yet linked into the backend/catalog contract.

- [ ] **Step 3: Add the fifteen theme links**

Append entries like:

```json
{
  "theme_id": "ai_logic_compute_chips_value_chain_v1",
  "chain_id": "ai_logic_compute_chips",
  "node_links": [],
  "unmapped_theme_node_ids": []
}
```

Do the same for all fifteen chains, then wire the expanded selected-chain registry so catalog summary cards can surface `研究中` or `已审核`.

- [ ] **Step 4: Keep the read model manifest-backed**

Use the manifest loader in `theme_research.py` so the artifact list, detail route, and catalog summaries all read from the same frozen scope instead of duplicating theme ids in multiple places.

- [ ] **Step 5: Run tests and commit**

Run the commands above and commit:

```bash
rtk git add \
  artifacts/technology_industry_catalog/v1/theme_links.json \
  src/stock_research/dashboard/theme_research.py \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py \
  dashboard/tests/theme-research-route.test.tsx
rtk git commit -m "feat: register next fifteen theme routes"
```

## Task 3: Build Wave A Deep Themes

**Files:**
- Create: `artifacts/theme_decomposition/ai_logic_compute_chips_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/optical_communications_data_center_interconnect_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/semiconductor_materials_electronic_chemicals_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/power_semiconductors_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/industrial_automation_control_value_chain_v1.json`
- Create matching company mapping files under `artifacts/theme_decomposition/company_mappings/`
- Create matching source packs and node matrices under `artifacts/theme_decomposition/source_packs/`
- Create: `tests/test_wave_a_industry_chain_themes.py`

- [ ] **Step 1: Write the failing Wave A artifact tests**

Add a parameterized test:

```python
WAVE_A_THEMES = [
    ("ai_logic_compute_chips", "ai_logic_compute_chips_value_chain_v1"),
    ("optical_communications_data_center_interconnect", "optical_communications_data_center_interconnect_value_chain_v1"),
    ("semiconductor_materials_electronic_chemicals", "semiconductor_materials_electronic_chemicals_value_chain_v1"),
    ("power_semiconductors", "power_semiconductors_value_chain_v1"),
    ("industrial_automation_control", "industrial_automation_control_value_chain_v1"),
]

@pytest.mark.parametrize(("chain_id", "theme_id"), WAVE_A_THEMES)
def test_wave_a_theme_meets_batch_gate(chain_id, theme_id):
    report = build_theme_batch_report(MANIFEST)
    row = next(item for item in report["theme_results"] if item["theme_id"] == theme_id)
    assert row["ready"] is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_wave_a_industry_chain_themes.py -q
```

Expected: failure because no Wave A artifacts or mappings exist yet.

- [ ] **Step 3: Create the Wave A theme artifacts**

Each file must include:

```json
{
  "artifact_version": "theme_decomposition_v1_6",
  "theme": {
    "theme_id": "ai_logic_compute_chips_value_chain_v1",
    "theme_name": "AI逻辑与算力芯片：架构、制程与价值量",
    "theme_type": "ai_compute",
    "summary": "Track compute-chip value capture from architecture and process migration to packaging interfaces and domestic substitution.",
    "status": "reviewed",
    "created_from": "mixed",
    "last_updated": "2026-07-14"
  },
  "research_profile": {
    "catalog_chain_id": "ai_logic_compute_chips",
    "research_kind": "industry_chain_deep_research",
    "industry_stage": "capacity_expansion",
    "central_conflict": "领先架构与先进制造能力决定供给稀缺性和利润池位置。",
    "investment_summary": "价值量集中在高性能算力芯片、先进封装接口与关键 IP/EDA 约束。",
    "value_flow_summary": "IP/EDA -> architecture -> wafer/process -> advanced package interface -> server deployment",
    "profit_pool_summary": "架构领先、制程可得性、封装接口与平台生态共同决定利润池。",
    "catalyst_claim_ids": [],
    "risk_claim_ids": [],
    "validation_signals": [],
    "evidence_gap_summary": "国内上市公司直接收入敞口需要持续用年报与客户验证补强。"
  }
}
```

Mirror the same structure for the other four Wave A themes using their own `catalog_chain_id` and chain-specific thesis.

- [ ] **Step 4: Create Wave A company mappings and evidence packs**

For each chain, create:

```json
{
  "theme_id": "ai_logic_compute_chips_value_chain_v1",
  "mappings": [],
  "mapping_evidence_items": []
}
```

Then populate at least `8` reviewed mappings, `10` claims, `10` accepted sources, and both `source_pack` plus `node_evidence_matrix` files per theme.

- [ ] **Step 5: Run Wave A verification and commit**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_wave_a_industry_chain_themes.py \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py -q
rtk env PYTHONPATH=src:. /Users/xiwei/stock_research/.venv/bin/python \
  scripts/verify_industry_chain_theme_batch.py \
  --manifest artifacts/theme_decomposition/batch_manifests/next_fifteen_industry_chain_themes_v1.json \
  --wave wave_a --format markdown
```

Commit:

```bash
rtk git add artifacts/theme_decomposition artifacts/technology_industry_catalog/v1/theme_links.json tests/test_wave_a_industry_chain_themes.py
rtk git commit -m "data: complete wave a industry chain themes"
```

## Task 4: Build Wave B Deep Themes

**Files:**
- Create: `artifacts/theme_decomposition/semiconductor_packaging_test_advanced_packaging_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/cloud_data_center_infrastructure_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/new_power_system_smart_grid_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/core_mechanical_components_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/industrial_inspection_metrology_machine_vision_value_chain_v1.json`
- Create matching company mapping files, source packs, and node matrices
- Create: `tests/test_wave_b_industry_chain_themes.py`

- [ ] **Step 1: Write the failing Wave B tests**

Freeze:

```python
WAVE_B_THEMES = [
    "semiconductor_packaging_test_advanced_packaging_value_chain_v1",
    "cloud_data_center_infrastructure_value_chain_v1",
    "new_power_system_smart_grid_value_chain_v1",
    "core_mechanical_components_value_chain_v1",
    "industrial_inspection_metrology_machine_vision_value_chain_v1",
]
```

Assert each theme appears in the batch report and returns `ready is True`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_wave_b_industry_chain_themes.py -q
```

- [ ] **Step 3: Create the Wave B deep themes**

Use the same v1.6 skeleton with exact `catalog_chain_id` values:

```json
[
  "semiconductor_packaging_test_advanced_packaging",
  "cloud_data_center_infrastructure",
  "new_power_system_smart_grid",
  "core_mechanical_components",
  "industrial_inspection_metrology_machine_vision"
]
```

Every artifact must ship all seven readable sections and preserve `research_only: true`.

- [ ] **Step 4: Fill Wave B evidence and mappings**

For every Wave B theme, add:

```python
assert accepted_source_count >= 10
assert primary_source_count >= 4
assert claim_count >= 10
assert reviewed_mapping_count >= 8
```

The evidence matrix must mark uncovered nodes as explicit `needs_evidence` gaps instead of silently omitting them.

- [ ] **Step 5: Run verification and commit**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_wave_b_industry_chain_themes.py -q
rtk env PYTHONPATH=src:. /Users/xiwei/stock_research/.venv/bin/python \
  scripts/verify_industry_chain_theme_batch.py \
  --manifest artifacts/theme_decomposition/batch_manifests/next_fifteen_industry_chain_themes_v1.json \
  --wave wave_b --format markdown
```

Commit:

```bash
rtk git add artifacts/theme_decomposition tests/test_wave_b_industry_chain_themes.py
rtk git commit -m "data: complete wave b industry chain themes"
```

## Task 5: Build Wave C Deep Themes

**Files:**
- Create: `artifacts/theme_decomposition/industrial_robots_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/power_batteries_battery_materials_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/intelligent_driving_smart_cockpit_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/automotive_electronics_chip_applications_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/commercial_space_launch_value_chain_v1.json`
- Create matching company mapping files, source packs, and node matrices
- Create: `tests/test_wave_c_industry_chain_themes.py`

- [ ] **Step 1: Write the failing Wave C tests**

Add:

```python
WAVE_C_THEMES = [
    "industrial_robots_value_chain_v1",
    "power_batteries_battery_materials_value_chain_v1",
    "intelligent_driving_smart_cockpit_value_chain_v1",
    "automotive_electronics_chip_applications_value_chain_v1",
    "commercial_space_launch_value_chain_v1",
]
```

And assert all five are manifest-ready.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_wave_c_industry_chain_themes.py -q
```

- [ ] **Step 3: Create the Wave C deep themes**

Every Wave C artifact must include:

```json
{
  "research_profile": {
    "research_kind": "industry_chain_deep_research",
    "catalog_chain_id": "commercial_space_launch",
    "industry_stage": "commercial_scaling",
    "central_conflict": "验证节奏、供给能力与客户落地共同决定主题兑现速度。",
    "investment_summary": "价值量并不平均分配，核心零部件、系统集成和关键验证环节更容易形成利润池。",
    "value_flow_summary": "核心部件 -> 子系统 -> 整机/平台 -> 集成验证 -> 客户交付/运营",
    "profit_pool_summary": "认证门槛、系统集成、客户绑定与规模化能力共同塑造壁垒。",
    "catalyst_claim_ids": [],
    "risk_claim_ids": [],
    "validation_signals": [],
    "evidence_gap_summary": "主题推进依赖上市公司披露、客户验证和量产节奏。"
  }
}
```

- [ ] **Step 4: Fill Wave C evidence and mapping coverage**

Apply the same quantitative gate as Waves A and B. If a company only has concept-level association, it must remain `concept_association` and cannot enter the default reviewed beneficiary set.

- [ ] **Step 5: Run verification and commit**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_wave_c_industry_chain_themes.py -q
rtk env PYTHONPATH=src:. /Users/xiwei/stock_research/.venv/bin/python \
  scripts/verify_industry_chain_theme_batch.py \
  --manifest artifacts/theme_decomposition/batch_manifests/next_fifteen_industry_chain_themes_v1.json \
  --wave wave_c --format markdown
```

Commit:

```bash
rtk git add artifacts/theme_decomposition tests/test_wave_c_industry_chain_themes.py
rtk git commit -m "data: complete wave c industry chain themes"
```

## Task 6: Browser Acceptance, PostgreSQL Import, And Rollout Docs

**Files:**
- Create: `dashboard/tests/next-fifteen-industry-chain-deep-research.spec.ts`
- Create: `docs/next_fifteen_industry_chain_theme_research_v1.md`
- Modify: `docs/five_priority_industry_chain_theme_research_v1.md`
- Modify: `docs/theme_research_dashboard_v1.md`

- [ ] **Step 1: Write the failing acceptance test**

Cover one representative route from each wave:

```ts
[
  '/theme-research/ai_logic_compute_chips_value_chain_v1',
  '/theme-research/cloud_data_center_infrastructure_value_chain_v1',
  '/theme-research/commercial_space_launch_value_chain_v1',
]
```

For each route assert the seven required sections render and the reviewed company list can hand off into the Stock Workspace.

- [ ] **Step 2: Run the browser test and verify failure**

Run:

```bash
rtk pnpm --dir dashboard exec playwright test dashboard/tests/next-fifteen-industry-chain-deep-research.spec.ts
```

Expected: failure until the new routes, artifacts, and mappings exist.

- [ ] **Step 3: Document the twenty-theme operating model**

Write `docs/next_fifteen_industry_chain_theme_research_v1.md` with:

```markdown
1. Twenty-theme target pool
2. Three-wave order
3. Evidence gate
4. Beneficiary-tier policy
5. Database import sequence
6. Real-browser acceptance checklist
```

- [ ] **Step 4: Run full verification**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_theme_decomposition.py \
  tests/test_industry_chain_theme_research.py \
  tests/test_verify_industry_chain_theme_batch.py \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_wave_a_industry_chain_themes.py \
  tests/test_wave_b_industry_chain_themes.py \
  tests/test_wave_c_industry_chain_themes.py -q
rtk pnpm --dir dashboard exec vitest run \
  tests/theme-research-route.test.tsx \
  tests/technology-industry-catalog-workspace.test.tsx
rtk pnpm --dir dashboard exec playwright test dashboard/tests/next-fifteen-industry-chain-deep-research.spec.ts
rtk git diff --check
```

- [ ] **Step 5: Apply schema, import, compare, and commit**

Run the production-side sequence in this order:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  -m stock_research.theme_research_db_schema schema-status
```

If the result is `drifted`, apply schema first with an authenticated admin session:

```bash
cd /Users/xiwei/stock_research/.worktrees/research-platform-validation-20260713
read -s "THEME_RESEARCH_ADMIN_PASSWORD?Admin password: "
export THEME_RESEARCH_ADMIN_PASSWORD
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  -m stock_research.theme_research_db_schema apply-schema \
  --admin-username theme_research_admin
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  -m stock_research.theme_research_db_schema import \
  --execute \
  --expected-generation 4 \
  --admin-username theme_research_admin \
  --idempotency-key next-fifteen-themes-20260714
unset THEME_RESEARCH_ADMIN_PASSWORD
```

Then compare artifact and DB packages:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from stock_research.theme_research_import import normalize_artifact_package, semantic_diff
from stock_research.theme_research_store import load_database_package
a = normalize_artifact_package()
d = load_database_package()
diff = semantic_diff(d, a)
print({"status": "match" if not diff["has_changes"] else "mismatch", "summary": diff["summary"]})
PY
```

Commit:

```bash
rtk git add \
  docs/next_fifteen_industry_chain_theme_research_v1.md \
  docs/five_priority_industry_chain_theme_research_v1.md \
  docs/theme_research_dashboard_v1.md \
  dashboard/tests/next-fifteen-industry-chain-deep-research.spec.ts
rtk git commit -m "docs: plan next fifteen industry chain themes"
```

## Self-Review

- Spec coverage: this plan covers shared verifier scope freeze, catalog wiring, all fifteen theme artifacts, browser acceptance, DB import, and documentation.
- Placeholder scan: no `TODO`, `TBD`, or “similar to previous step” shortcuts remain.
- Type consistency: the manifest, theme ids, wave names, and verifier commands use one naming scheme throughout the plan.
