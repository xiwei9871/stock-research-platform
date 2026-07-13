# Theme Company Mapping v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 4's read-only `theme -> node -> company -> evidence` mapping layer with enforceable separation between primary business, concept exposure, and reserve-stage activity.

**Architecture:** Store versioned mapping packages under a fixed artifact directory. Each package contains source records, excerpt-level evidence items, and company mappings that reference canonical theme nodes. A standard-library loader validates the common schema and evidence gates against the existing theme artifacts; no DB writes or network access occur at runtime.

**Tech Stack:** Python 3 standard library, JSON artifacts, existing `theme_decomposition_v1_5` artifacts, pytest.

---

### Task 1: Define mapping and evidence gates with tests

**Files:**
- Create: `tests/test_theme_company_mapping.py`

- [x] Write a failing sample-package test for four reviewed AI-power mappings and eight excerpt-level evidence items.
- [x] Write failing tests for missing evidence, company-mention-only evidence, non-accepted evidence sources, concept exposure promoted to reviewed, reserve-stage materiality mismatch, invalid CN company code, evidence-company/node mismatch, and duplicate mapping IDs.
- [x] Write a failing CLI test for `validate`, `summary`, and company lookup.
- [x] Run `rtk .venv/bin/pytest tests/test_theme_company_mapping.py -q` and verify collection fails because `stock_research.theme_company_mapping` does not exist.

### Task 2: Implement the read-only loader and CLI

**Files:**
- Create: `src/stock_research/theme_company_mapping.py`

- [x] Implement `load_theme_company_mapping_package()`, `summarize_theme_company_mapping_package()`, `load_theme_company_mappings()`, and `load_company_theme_mappings()`.
- [x] Validate mapping package versions, canonical theme/node references, source review state, evidence references, company-code format, confidence, business stage, revenue relevance, bottleneck relevance, and business materiality.
- [x] Require reviewed mappings to have accepted S0/S1 evidence, direct product/service relationship evidence, matching company/node scope, and confidence of at least 0.7.
- [x] Prevent concept-only exposure from becoming reviewed and require reserve-stage mappings to remain `reserve_only` with no claimed material revenue.
- [x] Add `validate`, `summary`, `show-theme`, and `show-company` CLI commands with structured JSON errors.
- [x] Re-run the focused test and verify failure is now limited to the missing mapping artifact.

### Task 3: Create the AI-power sample mapping package

**Files:**
- Create: `artifacts/theme_decomposition/company_mappings/ai_power_company_mapping_v1.json`

- [x] Add S0 accepted source records for the 2025 annual reports of Envicool, Kehua Data, Oulutong, and Zhongheng Electric from CNINFO.
- [x] Add product-relationship and revenue/materiality evidence items with report-page locators and paraphrased summaries.
- [x] Map Envicool to `liquid_cooling`, Kehua Data to `ups`, Oulutong to `server_power_supply`, and Zhongheng Electric to `hvdc_power`.
- [x] Mark exact product revenue as `undisclosed` where the filing only reports a broader segment.
- [x] Keep mappings research-only; do not add valuation, recommendation, price, or trading fields.
- [x] Run focused tests until green.

### Task 4: Document and verify Phase 4

**Files:**
- Create: `docs/theme_company_mapping_v1.md`
- Modify: `docs/theme_driven_research_engine_roadmap.md`
- Modify: `docs/theme_decomposition_research_baseline_v1.md`

- [x] Document field semantics, quality gates, four sample mappings, business-stage separation, revenue relevance rules, and current boundaries.
- [x] Mark Phase 4 complete while leaving Phase 2B and Phase 5 visibly unfinished.
- [x] Run `rtk .venv/bin/pytest tests/test_theme_company_mapping.py tests/test_decomposition_templates.py tests/test_theme_decomposition.py tests/test_ai_power_source_pack.py -q`.
- [x] Run all mapping CLI commands, validate JSON with `jq empty`, compile the module, and inspect scoped repository status.

### Task 5: Post-review hardening

**Files:**
- Modify: `src/stock_research/theme_company_mapping.py`
- Modify: `tests/test_theme_company_mapping.py`
- Modify: `docs/theme_company_mapping_v1.md`
- Modify: `docs/theme_driven_research_engine_roadmap.md`

- [x] Prevent mappings, evidence, and sources from crossing artifact ownership boundaries.
- [x] Require evidence for every mapping status and accepted revenue evidence for reviewed materiality claims.
- [x] Resolve excerpt evidence and source metadata in theme/company read models and CLI output.
- [x] Enforce concept-stage consistency and stable JSON scalar/list field types.
- [x] Allow weaker supplemental sources without letting them satisfy reviewed gates.
- [x] Complete independent code review with no remaining high- or medium-risk findings.
