# Theme To Tech Bottleneck Crosswalk v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 5's read-only, reversible crosswalk between Phase 4 theme-company mappings and the existing 378-company tech-bottleneck review universe.

**Architecture:** Store a versioned crosswalk artifact separately from both source systems. A standard-library loader derives stable IDs for existing CSV rows, verifies snapshot digests and cross-system references, resolves detailed read models, and exposes CLI commands without writing DB, CSV, overlay, or dashboard state.

**Tech Stack:** Python 3 standard library, JSON artifacts, CSV review-universe inputs, existing Phase 4 loader, pytest.

---

### Task 1: Define crosswalk contract with failing tests

**Files:**
- Create: `tests/test_theme_tech_bottleneck_crosswalk.py`

- [x] Test the production package summary: 378 universe rows, two crosswalks, two coverage gaps, four accounted P4 mappings.
- [x] Test Envicool and Kehua detailed lookups resolve the unchanged universe row, selected existing evidence, source metadata, and Phase 4 evidence.
- [x] Test Oulutong and Zhongheng are explicit `company_not_in_existing_review_universe` gaps rather than fabricated links.
- [x] Test missing mappings, wrong-company evidence, low reviewed confidence, missing evidence, incorrect gaps, and duplicate coverage are rejected with stable error codes.
- [x] Test stored file digests and expected universe count detect upstream drift.
- [x] Test forbidden admission, signal, quality-pool, and reviewer-decision fields are rejected.
- [x] Test CLI `validate`, `summary`, `show-theme`, `show-company`, and `coverage-gaps` emit structured JSON.
- [x] Run `rtk .venv/bin/pytest tests/test_theme_tech_bottleneck_crosswalk.py -q` and confirm collection fails because the module does not exist.

### Task 2: Implement stable universe indexes and loader

**Files:**
- Create: `src/stock_research/theme_tech_bottleneck_crosswalk.py`

- [x] Add repository-relative path resolution and SHA-256 snapshot verification.
- [x] Read the dataset, evidence index, and source index with `csv.DictReader`; normalize stock codes without pandas or network access.
- [x] Derive deterministic universe, evidence, and source IDs from row content.
- [x] Load Phase 4 mappings through `load_theme_company_mapping_package()` and build mapping/evidence indexes.
- [x] Validate artifact schema, enums, IDs, company/node ownership, evidence ownership, complete mapping coverage, and read-only guardrails.
- [x] Resolve detailed theme/company read models with both evidence systems and separate optional manual overlay context.
- [x] Implement summary and structured-error CLI commands.
- [x] Re-run focused tests and confirm failure is limited to the absent production artifact.

### Task 3: Create the AI-power crosswalk artifact

**Files:**
- Create: `artifacts/theme_decomposition/tech_bottleneck_crosswalks/ai_power_tech_bottleneck_crosswalk_v1.json`

- [x] Record current repository-relative input paths, SHA-256 digests, and expected count 378.
- [x] Link Envicool `002837.SZ` to `liquid_cooling` and Kehua Data `002335.SZ` to `ups`.
- [x] Select existing annual-report evidence rows that directly support each matching node and record their deterministic IDs.
- [x] Link each crosswalk to the exact Phase 4 mapping and new evidence IDs.
- [x] Record Oulutong `300870.SZ` and Zhongheng Electric `002364.SZ` as coverage gaps only.
- [x] Set all admission, signal, quality-pool, DB, CSV, and reviewer-decision write guardrails to false.
- [x] Run focused tests until green.

### Task 4: Document and verify Phase 5

**Files:**
- Create: `docs/theme_tech_bottleneck_crosswalk_v1.md`
- Modify: `docs/theme_driven_research_engine_roadmap.md`
- Modify: `docs/theme_decomposition_research_baseline_v1.md`

- [x] Document stable IDs, schema, quality gates, two links, two gaps, lookup commands, and current boundaries.
- [x] Mark Phase 5 complete while leaving Phase 6 onward unfinished.
- [x] Run P1-P5 related pytest suites.
- [x] Run all P5 CLI commands, `jq empty`, module compilation, and trailing-whitespace checks.
- [x] Hash the three authoritative input files before and after validation and confirm no changes.
- [x] Request independent read-only code review and close all high/medium findings.

### Task 5: Review hardening and frozen-snapshot recovery

**Files:**
- Modify: `src/stock_research/theme_tech_bottleneck_crosswalk.py`
- Modify: `tests/test_theme_tech_bottleneck_crosswalk.py`
- Modify: `artifacts/theme_decomposition/tech_bottleneck_crosswalks/ai_power_tech_bottleneck_crosswalk_v1.json`

- [x] Bind artifacts to the three authoritative CSV paths and validate required columns plus full stock coverage.
- [x] Close artifact schemas so unknown review/admission fields cannot enter the read model.
- [x] Match Phase 4 company code including exchange and verify company names against both systems.
- [x] Isolate `crosswalk_review_status` from the nested existing review state.
- [x] Make 96-bit evidence/source IDs independent of checkout prefix and reject source-key ambiguity.
- [x] Restore the frozen universe after an upstream generator test exposed four missing v5 rows, using the retained 378-row quality snapshot and 95 retained expansion-evidence rows.
- [x] Re-run independent review with no remaining high- or medium-risk findings.
