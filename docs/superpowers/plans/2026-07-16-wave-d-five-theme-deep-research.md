# Wave D Five-Theme Deep Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Execute one theme at a time, with a review checkpoint after each theme.

**Goal:** Deliver five evidence-backed Wave D themes and expand the completed priority pool from twenty to twenty-five themes.

**Architecture:** Add a Wave D manifest extension, enforce shared reverse-edge and precise-locator audits, then build five coordinated theme packages. Keep canonical Industry Catalog ownership separate from the readable Theme Research aggregation layer and preserve one-to-many theme-node projections.

**Tech Stack:** Python 3.14, JSON artifacts, FastAPI, pytest, React 19, TypeScript, Vitest, Vite.

## Scope

```python
WAVE_D = [
    "semiconductor_eda_ip_design_services",
    "memory_chips_storage_control",
    "industrial_machine_tools_cnc",
    "satellite_manufacturing_space_infrastructure",
    "high_end_medical_devices",
]
```

Theme IDs:

```python
WAVE_D_CHAIN_THEMES = {
    "semiconductor_eda_ip_design_services": "semiconductor_eda_ip_design_services_value_chain_v1",
    "memory_chips_storage_control": "memory_chips_storage_control_value_chain_v1",
    "industrial_machine_tools_cnc": "industrial_machine_tools_cnc_value_chain_v1",
    "satellite_manufacturing_space_infrastructure": "satellite_manufacturing_space_infrastructure_value_chain_v1",
    "high_end_medical_devices": "high_end_medical_devices_value_chain_v1",
}
```

## Task 1: Freeze Wave D And Upgrade Shared Quality Gates

**Files:**

- Create `artifacts/theme_decomposition/batch_manifests/wave_d_five_industry_chain_themes_v1.json`
- Modify `scripts/verify_industry_chain_theme_batch.py`
- Modify `tests/test_verify_industry_chain_theme_batch.py`
- Modify `src/stock_research/industry_chain_theme_research.py`
- Modify `tests/test_industry_chain_theme_research.py`

- [ ] Add failing tests for exact Wave D scope and the 25-theme combined registry.
- [ ] Add shared reverse audit: every source-claim-node edge must be declared by the source's supported nodes.
- [ ] Add shared bidirectional source/claim/node/matrix equality checks.
- [ ] Add shared mapping-evidence audit for three distinct role-specific locators with explicit page numbers.
- [ ] Verify an intentionally broad source-to-all-nodes claim fails.
- [ ] Verify a repeated composite locator fails.
- [ ] Commit as `feat: add wave d research quality gates`.

## Task 2: Build D1 Semiconductor EDA, IP, And Design Services

**Files:** four theme artifacts plus Wave D tests and catalog links.

- [ ] Freeze 8-12 readable research nodes and the one-to-many canonical mapping.
- [ ] Collect at least 10 accepted sources, including at least 8 official filings or official sources.
- [ ] Separate EDA subscriptions, IP licensing/royalty, design-service revenue and chip-product revenue.
- [ ] Add at least 12 claims and 8 reviewed company mappings.
- [ ] Run Wave D focused tests, catalog tests and route tests.
- [ ] Request spec review, fix all Critical/Important findings, then request data-quality review.
- [ ] Commit as `data: add semiconductor eda ip deep research`.

## Task 3: Build D2 Memory Chips, Storage, And Controllers

- [ ] Freeze research nodes for memory architecture, controllers, enterprise storage, integration and cycle validation.
- [ ] Prevent HBM concept claims from becoming reviewed beneficiaries without direct product/customer evidence.
- [ ] Separate memory-wafer, module, controller and system revenue.
- [ ] Meet the same source, claim, mapping and locator gates.
- [ ] Review and commit as `data: add memory storage controller deep research`.

## Task 4: Build D3 Industrial Machine Tools And CNC

- [ ] Freeze nodes for CNC, servo/feedback, machine body, spindle/components, multi-axis processing and installed-base service.
- [ ] Separate orders, delivery, acceptance and recognized revenue.
- [ ] Preserve industrial automation and core-component canonical ownership where appropriate.
- [ ] Meet the same source, claim, mapping and locator gates.
- [ ] Review and commit as `data: add industrial machine tool deep research`.

## Task 5: Build D4 Satellite Manufacturing And Space Infrastructure

- [ ] Freeze nodes for platform, payload, onboard systems, ground infrastructure, batch manufacturing and in-orbit validation.
- [ ] Keep launch-vehicle ownership on `commercial_space_launch`.
- [ ] Separate constellation plans, contracts, launched satellites, delivered satellites and recurring service revenue.
- [ ] Meet the same source, claim, mapping and locator gates.
- [ ] Review and commit as `data: add satellite manufacturing deep research`.

## Task 6: Build D5 High-End Medical Devices

- [ ] Freeze nodes for device platform, core components, consumables, registration/access, installed base and service revenue.
- [ ] Separate registration, trial, tender, installed base, procedure volume and recognized revenue.
- [ ] Keep medical-imaging-specific ownership on its canonical chain where applicable.
- [ ] Meet the same source, claim, mapping and locator gates.
- [ ] Review and commit as `data: add high end medical device deep research`.

## Task 7: Wave D And Combined Acceptance

- [ ] Run backend theme, mapping, catalog, dashboard and verifier suites.
- [ ] Verify Wave D `5/5 ready` and combined priority pool `25/25 ready`.
- [ ] Run frontend route/workspace tests and Vite build.
- [ ] Inspect `/theme-research` and all five Wave D detail/company routes on port 5174.
- [ ] Verify company row click opens `/tech-bottleneck/stock/<code>?source=theme_research`.
- [ ] Verify catalog deep links preserve all one-to-many pairs.
- [ ] Run `git diff --check` and confirm only user-owned pre-existing changes remain unstaged.
- [ ] Request final Wave D spec, quality and regression reviews with zero Critical/Important findings.
- [ ] Commit final test-only adjustments as `test: complete wave d acceptance`.

## Required Verification Commands

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest -q \
  tests/test_wave_d_industry_chain_themes.py \
  tests/test_verify_industry_chain_theme_batch.py \
  tests/test_dashboard_theme_research.py \
  tests/test_dashboard_technology_industry_catalog.py \
  tests/test_technology_industry_catalog.py \
  tests/test_theme_decomposition.py \
  tests/test_theme_company_mapping.py

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  scripts/verify_industry_chain_theme_batch.py \
  --manifest artifacts/theme_decomposition/batch_manifests/wave_d_five_industry_chain_themes_v1.json \
  --wave wave_d --format markdown

rtk pnpm --dir dashboard test -- theme-research-route.test.tsx theme-research-workspace.test.tsx
rtk pnpm --dir dashboard build
```

