# Five Priority Industry Chains As Deep Theme Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver five readable, evidence-backed industry-chain research packages inside the existing Theme Research workspace while keeping the Technology Industry Catalog as the structural directory.

**Architecture:** Extend the existing Theme Research artifact contract with an optional deep-research profile, then add a catalog-to-theme adapter that joins canonical taxonomy to Theme Research sources, claims, nodes, and company mappings. The catalog exposes only deep-research availability and summary metadata; full value-chain, profit-pool, catalyst/risk, beneficiary, source, and evidence-gap views remain in Theme Research. Existing ingestion, PostgreSQL review, guardrails, routes, and Stock Workspace links remain authoritative.

**Tech Stack:** Python 3.14, JSON artifacts, FastAPI, PostgreSQL/psycopg, pytest, React 19, TypeScript, Vitest, Testing Library, Playwright, Vite.

---

## File Map

### Shared contract and services

- Modify `src/stock_research/theme_decomposition.py`: accept artifact version `theme_decomposition_v1_6`, validate deep-research profiles, new claim types, and `new_energy_storage` theme type.
- Create `src/stock_research/industry_chain_theme_research.py`: selected-chain registry, catalog/theme join, coverage verifier, freshness status, and deterministic beneficiary tier classifier.
- Modify `src/stock_research/dashboard/theme_research.py`: expose catalog context, deep-research profile, beneficiary tiers, and research coverage summaries.
- Modify `src/stock_research/dashboard/app.py`: enrich catalog endpoints with deep-research summaries while preserving existing routes.
- Create `tests/test_industry_chain_theme_research.py`: unit coverage for registry, join, classifier, gates, and summaries.
- Modify `tests/test_theme_decomposition.py`: schema and migration compatibility coverage.
- Modify `tests/test_dashboard_theme_research.py`: Theme Research API contract coverage.
- Modify `tests/test_dashboard_technology_industry_catalog.py`: catalog deep-research summary coverage.

### Frontend

- Modify `dashboard/src/types/themeResearch.ts`: deep-research profile, catalog context, value-flow, beneficiary-tier, and coverage types.
- Modify `dashboard/src/types/technologyIndustryCatalog.ts`: catalog deep-research summary types.
- Modify `dashboard/src/components/ThemeResearchWorkspace.tsx`: readable conclusion, value chain, profit pools, catalyst/risk, validation signals, beneficiary filters, evidence details, and incomplete states.
- Modify `dashboard/src/components/IndustryCatalogWorkspace.tsx`: compact deep-research status/card and `进入深度研究` action.
- Modify `dashboard/src/styles.css`: focused responsive styles for new research sections.
- Modify `dashboard/tests/theme-research-route.test.tsx`: selected-theme identity and route compatibility.
- Create `dashboard/tests/industry-chain-deep-research-workspace.test.tsx`: full deep-theme component behavior.
- Modify `dashboard/tests/technology-industry-catalog-workspace.test.tsx`: catalog status/card behavior.
- Create `dashboard/tests/five-industry-chain-deep-research.spec.ts`: authenticated-style real browser acceptance.

### Theme and mapping artifacts

- Modify `artifacts/theme_decomposition/ai_power_value_capture_v1.json`.
- Modify `artifacts/theme_decomposition/humanoid_robotics_head_to_toe_v1.json`.
- Create `artifacts/theme_decomposition/semiconductor_manufacturing_equipment_value_chain_v1.json`.
- Create `artifacts/theme_decomposition/ai_compute_infrastructure_value_chain_v1.json`.
- Create `artifacts/theme_decomposition/new_energy_storage_value_chain_v1.json`.
- Modify `artifacts/theme_decomposition/company_mappings/ai_power_company_mapping_v1.json`.
- Create four matching company-mapping artifacts under `artifacts/theme_decomposition/company_mappings/`.
- Create or update source packs and node-evidence matrices under `artifacts/theme_decomposition/source_packs/` for all five themes.
- Modify `artifacts/technology_industry_catalog/v1/theme_links.json`.
- Create `artifacts/technology_industry_catalog/v1/nodes/ai_compute_infrastructure_v1.json`.
- Create `artifacts/technology_industry_catalog/v1/nodes/new_energy_storage_v1.json`.
- Modify `artifacts/technology_industry_catalog/v1/edges.json` and `sources.json` where the two new trees require referenced relationships or taxonomy sources.

### Verification and documentation

- Create `scripts/verify_five_industry_chain_themes.py`: deterministic five-theme completion verifier.
- Create `tests/test_verify_five_industry_chain_themes.py`: verifier acceptance and failure coverage.
- Create `docs/five_priority_industry_chain_theme_research_v1.md`: operator/user guide and research methodology.
- Modify `docs/theme_research_dashboard_v1.md` and `docs/technology_industry_catalog_v1.md`.

## Task 1: Extend The Theme Artifact Contract

**Files:**
- Modify: `tests/test_theme_decomposition.py`
- Modify: `src/stock_research/theme_decomposition.py`
- Create: `docs/theme_decomposition_artifact_schema_v1_6_migration.md`

- [ ] **Step 1: Write failing tests for the v1.6 deep-research profile**

Add a fixture artifact with:

```python
"artifact_version": "theme_decomposition_v1_6",
"research_profile": {
    "catalog_chain_id": "new_energy_storage",
    "research_kind": "industry_chain_deep_research",
    "industry_stage": "commercial_scaling",
    "central_conflict": "System economics depend on cells, power conversion, safety, and market utilization together.",
    "investment_summary": "Storage value is captured across equipment and system-operation layers rather than by capacity alone.",
    "value_flow_summary": "cells -> packs -> PCS/BMS/EMS -> integration/EPC -> grid service",
    "profit_pool_summary": "Qualification, power electronics, control software, integration, and operation are separately assessed.",
    "catalyst_claim_ids": ["storage_catalyst_1"],
    "risk_claim_ids": ["storage_risk_1"],
    "validation_signals": ["system tender prices", "utilization hours"],
    "evidence_gap_summary": "Revenue exposure requires company-level filings."
}
```

Assert v1.5 artifacts remain valid, `catalyst` and `risk` claim types are accepted, and invalid/missing deep-profile fields fail with stable error codes.

- [ ] **Step 2: Run the schema tests and verify failure**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_theme_decomposition.py -q
```

Expected: the v1.6 fixture fails because the artifact version, profile, claim types, and energy-storage theme type are unsupported.

- [ ] **Step 3: Implement the minimal compatible schema extension**

Add:

```python
SUPPORTED_ARTIFACT_VERSIONS = {
    "theme_decomposition_v1_5",
    "theme_decomposition_v1_6",
}
RESEARCH_KINDS = {"industry_chain_deep_research"}
RESEARCH_PROFILE_FIELDS = {
    "catalog_chain_id",
    "research_kind",
    "industry_stage",
    "central_conflict",
    "investment_summary",
    "value_flow_summary",
    "profit_pool_summary",
    "catalyst_claim_ids",
    "risk_claim_ids",
    "validation_signals",
    "evidence_gap_summary",
}
```

Extend `THEME_TYPES` with `new_energy_storage`, extend `CLAIM_TYPES` with `catalyst` and `risk`, validate profile claim references after claims are indexed, and include `research_profiles` in the loaded package keyed by `theme_id`.

- [ ] **Step 4: Run schema regression tests**

Run the focused schema test above and `rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_theme_research_import.py tests/test_theme_research_db_models.py -q`.

Expected: all focused tests pass without changing v1.5 behavior.

- [ ] **Step 5: Document and commit the contract**

Document the v1.5-to-v1.6 compatibility rule and commit:

```bash
rtk git add src/stock_research/theme_decomposition.py tests/test_theme_decomposition.py docs/theme_decomposition_artifact_schema_v1_6_migration.md
rtk git commit -m "feat: add deep industry theme artifact contract"
```

## Task 2: Add The Catalog-to-Theme Adapter And Beneficiary Classifier

**Files:**
- Create: `src/stock_research/industry_chain_theme_research.py`
- Create: `tests/test_industry_chain_theme_research.py`

- [ ] **Step 1: Write failing registry and classifier tests**

Freeze this registry:

```python
SELECTED_CHAIN_THEMES = {
    "ai_data_center_power": "ai_power_value_capture_v1",
    "semiconductor_manufacturing_equipment": "semiconductor_manufacturing_equipment_value_chain_v1",
    "humanoid_robots_embodied_intelligence": "humanoid_robotics_head_to_toe_v1",
    "ai_compute_infrastructure": "ai_compute_infrastructure_value_chain_v1",
    "new_energy_storage": "new_energy_storage_value_chain_v1",
}
```

Test `classify_beneficiary(mapping, evidence_items)` with these outcomes:

```python
assert reviewed_core == "core_beneficiary"
assert reviewed_emerging_direct == "elastic_beneficiary"
assert reviewed_adjacent_supplier == "indirect_beneficiary"
assert draft_or_concept_only == "concept_association"
```

Also test missing accepted direct-relationship evidence always yields `concept_association`.

- [ ] **Step 2: Write failing coverage-gate tests**

Assert a reviewed theme requires:

- all L3 catalog nodes mapped;
- every investment-relevant L4 mapped or listed as a gap;
- at least ten accepted sources and four primary/first-party sources;
- at least ten claims with accepted source references;
- at least eight reviewed company mappings when possible;
- no concept association inside the reviewed-beneficiary collection.

- [ ] **Step 3: Run tests and verify module-import failure**

Run `rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_industry_chain_theme_research.py -q`.

- [ ] **Step 4: Implement registry, join, freshness, classifier, and verifier**

Expose:

```python
def classify_beneficiary(mapping, evidence_items) -> str: ...
def build_chain_research_summary(chain_id, *, catalog, theme_context) -> dict: ...
def build_theme_catalog_context(theme_id, *, catalog) -> dict: ...
def verify_deep_theme_coverage(theme_id, *, catalog, theme_context) -> dict: ...
def list_selected_chain_research(*, catalog, theme_context) -> list[dict]: ...
```

Use deterministic thresholds and return explicit `researching`, `reviewed`, `needs_update`, and `not_started` states. Do not query market prices or trading signals.

- [ ] **Step 5: Run tests and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_industry_chain_theme_research.py -q
rtk git add src/stock_research/industry_chain_theme_research.py tests/test_industry_chain_theme_research.py
rtk git commit -m "feat: link industry catalog to deep theme research"
```

## Task 3: Enrich Backend Read Models And APIs

**Files:**
- Modify: `src/stock_research/dashboard/theme_research.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_theme_research.py`
- Modify: `tests/test_dashboard_technology_industry_catalog.py`

- [ ] **Step 1: Write failing Theme Research API tests**

Assert theme list/detail includes:

```python
assert item["research_kind"] == "industry_chain_deep_research"
assert item["catalog_context"]["chain_id"] == "ai_data_center_power"
assert detail["research_profile"]["value_flow_summary"]
assert detail["beneficiary_summary"]["by_tier"]["core_beneficiary"] >= 1
```

Company rows must expose `beneficiary_tier` and resolved mapping evidence.

- [ ] **Step 2: Write failing catalog API tests**

Assert exactly five chain rows have a `deep_research` object. The AI-power row must include its route, status, source count, reviewed-company count, evidence-gap count, and last update date. A nonselected chain must return `deep_research: null`.

- [ ] **Step 3: Run tests and verify contract failures**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_theme_research.py tests/test_dashboard_technology_industry_catalog.py -q
```

- [ ] **Step 4: Implement read-model composition**

Join catalog and Theme Research only in read services. Add profile, catalog context, beneficiary counts/tiers, mapping evidence, and coverage status. Preserve all existing keys and routes.

- [ ] **Step 5: Run tests and commit**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_theme_research.py tests/test_dashboard_technology_industry_catalog.py -q
rtk git add src/stock_research/dashboard/theme_research.py src/stock_research/dashboard/app.py tests/test_dashboard_theme_research.py tests/test_dashboard_technology_industry_catalog.py
rtk git commit -m "feat: expose deep industry research read models"
```

## Task 4: Build The Shared Deep-Research Frontend

**Files:**
- Modify: `dashboard/src/types/themeResearch.ts`
- Modify: `dashboard/src/types/technologyIndustryCatalog.ts`
- Modify: `dashboard/src/components/ThemeResearchWorkspace.tsx`
- Modify: `dashboard/src/components/IndustryCatalogWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Create: `dashboard/tests/industry-chain-deep-research-workspace.test.tsx`
- Modify: `dashboard/tests/theme-research-route.test.tsx`
- Modify: `dashboard/tests/technology-industry-catalog-workspace.test.tsx`

- [ ] **Step 1: Write failing component tests**

The deep theme test must assert visible sections named:

```text
研究结论
价值链
利润池与竞争壁垒
催化、验证信号与风险
受益公司
来源证据
证据缺口与更新
```

It must assert beneficiary tier filters separate core, elastic, indirect, and concept associations, and clicking a company opens Stock Workspace.

- [ ] **Step 2: Write failing catalog navigation tests**

Assert selected chains show `研究中` or `已审核`, metrics, and a unique `进入深度研究` action. Nonselected chains remain structural catalog pages without a blank research panel.

- [ ] **Step 3: Run tests and verify failure**

```bash
rtk pnpm --dir dashboard exec vitest run tests/industry-chain-deep-research-workspace.test.tsx tests/theme-research-route.test.tsx tests/technology-industry-catalog-workspace.test.tsx
```

- [ ] **Step 4: Implement types and readable sections**

Keep existing tabs and add deep-theme overview sections to the overview route. Use semantic regions, scoped responsive tables/cards, explicit missing-evidence states, and no page-level horizontal overflow.

- [ ] **Step 5: Run focused tests and build**

```bash
rtk pnpm --dir dashboard exec vitest run tests/industry-chain-deep-research-workspace.test.tsx tests/theme-research-route.test.tsx tests/technology-industry-catalog-workspace.test.tsx
rtk pnpm --dir dashboard build
```

- [ ] **Step 6: Commit the shared UI**

```bash
rtk git add dashboard/src/types/themeResearch.ts dashboard/src/types/technologyIndustryCatalog.ts dashboard/src/components/ThemeResearchWorkspace.tsx dashboard/src/components/IndustryCatalogWorkspace.tsx dashboard/src/styles.css dashboard/tests/industry-chain-deep-research-workspace.test.tsx dashboard/tests/theme-research-route.test.tsx dashboard/tests/technology-industry-catalog-workspace.test.tsx
rtk git commit -m "feat: render readable deep industry theme research"
```

## Task 5: Upgrade AI Data Center Power As The Reference Theme

**Files:**
- Modify: `artifacts/theme_decomposition/ai_power_value_capture_v1.json`
- Modify: `artifacts/theme_decomposition/company_mappings/ai_power_company_mapping_v1.json`
- Modify: `artifacts/theme_decomposition/source_packs/ai_power_source_pack_v1.json`
- Modify: `artifacts/theme_decomposition/source_packs/ai_power_claim_review_v1.json`
- Modify: `artifacts/theme_decomposition/source_packs/ai_power_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Create: `tests/test_ai_power_deep_theme.py`

- [ ] **Step 1: Freeze the reference-theme acceptance test**

Require eleven readable infrastructure stages, at least ten accepted sources, ten claims, eight evidence-backed reviewed company mappings when supported, visible concept-only separation, and complete catalog/theme node-link coverage or explicit gaps.

- [ ] **Step 2: Run the test and confirm current coverage fails**

Current expected gaps: eight claims and four reviewed mappings.

- [ ] **Step 3: Add the v1.6 research profile and narrative claims**

Cover capacity planning, energy supply/resilience, grid/substation, backup power, UPS/DC conversion, HVDC, room/rack distribution, server-board power, liquid cooling, EMS, and design/EPC/operations.

- [ ] **Step 4: Revalidate and extend company evidence**

Keep the existing reviewed mappings for 英维克、科华数据、欧陆通、中恒电气. Research leads for additional mapping include 科士达、申菱环境、高澜股份、伊戈尔 and other candidates only when company-primary product/business evidence and materiality evidence pass the mapping validator. Unsupported candidates remain concept associations.

- [ ] **Step 5: Validate and commit**

Run the AI-power test, theme decomposition tests, company mapping tests, and catalog-link tests, then commit `data: complete AI power deep theme research`.

## Task 6: Build Semiconductor Manufacturing Equipment

**Files:**
- Create: `artifacts/theme_decomposition/semiconductor_manufacturing_equipment_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/semiconductor_manufacturing_equipment_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/semiconductor_manufacturing_equipment_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/semiconductor_manufacturing_equipment_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Create: `tests/test_semiconductor_equipment_deep_theme.py`

- [ ] **Step 1: Write acceptance tests for the ten L3 process families**

Require lithography/patterning, etch, thin film/epitaxy, thermal/doping, clean/wet, CMP, inspection/metrology/process control, wafer handling/automation, vacuum/gas/fluid control, and facilities/pollution control.

- [ ] **Step 2: Build the theme artifact from canonical catalog nodes**

Add sourced value-capture, bottleneck, localization, supply, and evidence assessments. Preserve canonical node ownership through explicit links.

- [ ] **Step 3: Build the evidence-backed company map**

Research candidates include 北方华创、中微公司、盛美上海、拓荆科技、华海清科、芯源微、精测电子、长川科技、京仪装备、至纯科技、新莱应材、富创精密. Classify each as direct tool, component/subsystem, material, or facility supplier and require source evidence.

- [ ] **Step 4: Validate gates and commit**

Run the theme, mapping, adapter, catalog, and focused dashboard tests. Commit `data: add semiconductor equipment deep theme research`.

## Task 7: Complete Humanoid Robots And Embodied Intelligence

**Files:**
- Modify: `artifacts/theme_decomposition/humanoid_robotics_head_to_toe_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/humanoid_robotics_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/humanoid_robotics_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/humanoid_robotics_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Create: `tests/test_humanoid_robotics_deep_theme.py`

- [ ] **Step 1: Write acceptance tests for all twelve L3 system families**

Require the existing head-to-toe structure and explicit rejection of unverified social supply-chain claims from reviewed beneficiaries.

- [ ] **Step 2: Upgrade the draft theme to v1.6**

Add readable system flow, profit-pool logic, catalyst/risk claims, validation signals, and explicit evidence gaps. Keep status `draft` until the review gates pass.

- [ ] **Step 3: Build evidence-backed company mappings**

Research candidates include 汇川技术、绿的谐波、双环传动、鸣志电器、柯力传感、奥比中光、三花智控、拓普集团、兆威机电、雷赛智能、中大力德、江苏雷利. Do not promote a company based only on media supply-chain lists.

- [ ] **Step 4: Validate gates and commit**

Commit `data: complete humanoid robotics deep theme research` only after schema, mapping, and deep-theme tests pass.

## Task 8: Build AI Compute Infrastructure

**Files:**
- Create: `artifacts/technology_industry_catalog/v1/nodes/ai_compute_infrastructure_v1.json`
- Create: `artifacts/theme_decomposition/ai_compute_infrastructure_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/ai_compute_infrastructure_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/ai_compute_infrastructure_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/ai_compute_infrastructure_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `artifacts/technology_industry_catalog/v1/edges.json`
- Create: `tests/test_ai_compute_infrastructure_deep_theme.py`

- [ ] **Step 1: Freeze the canonical decomposition test**

Require accelerators/compute boards, servers/racks, memory/storage, cluster networking, optical/interconnect, orchestration/system software, data-center deployment, and operations. Power/cooling must be linked dependencies rather than duplicated owned nodes.

- [ ] **Step 2: Add canonical catalog nodes and edges**

Validate IDs, hierarchy, ownership, dependency edges, and structural completeness.

- [ ] **Step 3: Build the deep theme and evidence package**

Cover utilization economics, qualification, scale, supply constraints, localization, and deployment bottlenecks.

- [ ] **Step 4: Build evidence-backed company mappings**

Research candidates include 海光信息、寒武纪、浪潮信息、中科曙光、工业富联、紫光股份、沪电股份、深南电路、中际旭创、新易盛、光迅科技 and data-center operators only where direct evidence and materiality support the mapping.

- [ ] **Step 5: Validate and commit**

Commit `data: add AI compute infrastructure deep theme research` after catalog, theme, mapping, and UI fixtures pass.

## Task 9: Build New Energy Storage

**Files:**
- Create: `artifacts/technology_industry_catalog/v1/nodes/new_energy_storage_v1.json`
- Create: `artifacts/theme_decomposition/new_energy_storage_value_chain_v1.json`
- Create: `artifacts/theme_decomposition/company_mappings/new_energy_storage_company_mapping_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/new_energy_storage_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/new_energy_storage_node_evidence_matrix_v1.json`
- Modify: `artifacts/technology_industry_catalog/v1/theme_links.json`
- Modify: `artifacts/technology_industry_catalog/v1/edges.json`
- Create: `tests/test_new_energy_storage_deep_theme.py`

- [ ] **Step 1: Freeze the canonical decomposition test**

Require cells/materials, modules/packs, PCS, BMS, EMS, thermal management, fire protection, enclosure/electrical balance of system, system integration, EPC/grid connection, operations/maintenance, and market participation.

- [ ] **Step 2: Add canonical catalog nodes and edges**

Separate battery manufacturing economics from system integration and power-market service economics.

- [ ] **Step 3: Build the deep theme and evidence package**

Cover cycle life, safety, efficiency, duration, degradation, tender pricing, utilization, ancillary services, qualification, and revenue-stack risks.

- [ ] **Step 4: Build evidence-backed company mappings**

Research candidates include 宁德时代、亿纬锂能、国轩高科、阳光电源、科华数据、盛弘股份、上能电气、科士达、南都电源、派能科技、林洋能源、金盘科技 and other candidates only when the mapping gates pass.

- [ ] **Step 5: Validate and commit**

Commit `data: add new energy storage deep theme research` after catalog, theme, mapping, and coverage tests pass.

## Task 10: Add The Five-theme Completion Verifier

**Files:**
- Create: `scripts/verify_five_industry_chain_themes.py`
- Create: `tests/test_verify_five_industry_chain_themes.py`

- [ ] **Step 1: Write failing verifier tests**

The verifier must fail independently for missing theme, missing link, incomplete L3, insufficient sources/claims, insufficient reviewed mappings, concept contamination, unmapped investment-relevant L4, and frontend/API contract mismatch.

- [ ] **Step 2: Implement deterministic JSON/Markdown output**

Return per-theme status and aggregate fields:

```python
{
    "selected_theme_count": 5,
    "catalog_link_count": 5,
    "reviewed_theme_count": ...,
    "researching_theme_count": ...,
    "theme_results": [...],
    "all_required_sections_ready": True,
    "completion_status": "ready" | "not_ready",
}
```

- [ ] **Step 3: Run tests and commit**

Commit `test: verify five deep industry chain themes`.

## Task 11: Import, Compare, And Review The Five Themes

**Files:**
- Modify only generated database state and versioned export artifacts produced by existing commands.
- Add integration assertions to `tests/integration/test_theme_research_postgres.py` when coverage is missing.

- [ ] **Step 1: Run full artifact validation and dry-run import**

Use existing Theme Research ingestion/import commands with `PYTHONPATH=src` and the integration worktree artifacts.

- [ ] **Step 2: Apply schema if required and import transactionally**

Preserve version history. Do not bypass review gates or mutate reviewed history in place.

- [ ] **Step 3: Compare artifact and DB read sources**

Run Theme Research endpoints in `compare` mode and require `comparison.status == "match"` for list, detail, nodes, sources, claims, and companies across all five themes.

- [ ] **Step 4: Export versioned snapshots and run PostgreSQL integration tests**

No theme is promoted to reviewed unless its verifier result satisfies the design gates.

- [ ] **Step 5: Commit only versioned export/test changes**

Commit `test: verify deep industry themes in PostgreSQL` when repository files change.

## Task 12: Documentation, Browser Acceptance, And 5174 Deployment

**Files:**
- Create: `docs/five_priority_industry_chain_theme_research_v1.md`
- Modify: `docs/theme_research_dashboard_v1.md`
- Modify: `docs/technology_industry_catalog_v1.md`
- Create: `dashboard/tests/five-industry-chain-deep-research.spec.ts`

- [ ] **Step 1: Document user workflow and evidence semantics**

Explain how to move from catalog to theme, read value flow and profit pools, interpret beneficiary tiers, inspect evidence, and open Stock Workspace. State clearly that the output is research-only.

- [ ] **Step 2: Write desktop and mobile Playwright acceptance**

Open all five catalog entries and Theme Research pages. Verify the seven readable sections, beneficiary separation, sources, evidence gaps, Stock Workspace links, browser back/forward behavior, and no page-level horizontal overflow at `1440x900` and `390x844`.

- [ ] **Step 3: Run complete verification**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_theme_decomposition.py tests/test_theme_research_priority.py tests/test_theme_research_import.py tests/test_dashboard_theme_research.py tests/test_dashboard_technology_industry_catalog.py tests/test_industry_chain_theme_research.py tests/test_ai_power_deep_theme.py tests/test_semiconductor_equipment_deep_theme.py tests/test_humanoid_robotics_deep_theme.py tests/test_ai_compute_infrastructure_deep_theme.py tests/test_new_energy_storage_deep_theme.py tests/test_verify_five_industry_chain_themes.py -q
rtk pnpm --dir dashboard test
rtk pnpm --dir dashboard build
rtk git diff --check
```

Run PostgreSQL integration tests when the local service is available.

- [ ] **Step 4: Run Playwright and inspect real 5174 pages**

Start backend `8765` and Vite `5174` from this integration worktree with the existing authentication settings. Run the dedicated Playwright spec against an isolated authentication-disabled test backend, then visually verify the authenticated real application.

- [ ] **Step 5: Commit documentation and acceptance**

Commit `docs: complete five deep industry chain themes`.

- [ ] **Step 6: Push and perform completion audit**

Push `integration/research-platform-validation-20260713`. Verify every acceptance item in the approved design against artifacts, APIs, tests, rendered pages, running process working directories, and the completion verifier before marking the goal complete.
