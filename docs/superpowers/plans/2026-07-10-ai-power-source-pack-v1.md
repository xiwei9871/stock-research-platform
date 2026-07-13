# AI Power Source Pack v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 2A read-only AI power evidence pack with traceable source review, claim decisions, and node-level evidence gaps.

**Architecture:** Keep the Phase 1.5 theme package as the canonical decomposition skeleton. Add three independent Phase 2A JSON artifacts under a dedicated evidence-pack directory and a focused Python loader that validates their cross-references, evidence gates, and summary counts without DB or network access. Update the canonical AI theme only where accepted excerpt-level evidence justifies a source, claim, or node review-state change.

**Tech Stack:** Python 3, standard-library `json` and `pathlib`, pytest, repository JSON artifacts.

---

### Task 1: Define the evidence-pack contract with tests

**Files:**
- Create: `tests/test_ai_power_source_pack.py`

- [x] Write failing tests that require all three artifacts, stable summary counts, accepted-source locators, cross-file source/claim/node references, and rejected reviewed claims without accepted evidence.
- [x] Run `.venv/bin/pytest tests/test_ai_power_source_pack.py -q` and confirm failure because `stock_research.ai_power_source_pack` does not exist.

### Task 2: Implement the read-only loader and validators

**Files:**
- Create: `src/stock_research/ai_power_source_pack.py`

- [x] Implement `load_ai_power_evidence_pack()`, `validate_ai_power_evidence_pack()`, and `summarize_ai_power_evidence_pack()` using only the standard library.
- [x] Validate required fields, artifact versions, enum values, unique IDs, cross-file references, accepted-source evidence locators, reviewed-claim accepted evidence, and matrix coverage of every canonical AI theme node.
- [x] Add a minimal `validate` and `summary` module CLI with structured JSON errors.
- [x] Run the focused test and confirm it now fails only because the three data artifacts are absent.

### Task 3: Add the three Phase 2A artifacts

**Files:**
- Create: `artifacts/theme_decomposition/source_packs/ai_power_source_pack_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/ai_power_claim_review_v1.json`
- Create: `artifacts/theme_decomposition/source_packs/ai_power_node_evidence_matrix_v1.json`

- [x] Record reviewed official DOE, J.P. Morgan, and NVIDIA pages with section-level locators and paraphrased evidence summaries.
- [x] Keep inaccessible LBNL/IEA/OCP originals and gated broker reports as `needs_full_text`; keep video/social items as `lead_only`.
- [x] Review only claims supported by accepted sources; block blanket copper and all-equipment-beneficiary claims where the 800VDC architecture introduces contrary evidence.
- [x] Cover all 13 canonical AI power nodes in the evidence matrix and preserve unresolved value-capture/localization questions as visible evidence gaps.
- [x] Run the focused tests until green.

### Task 4: Reconcile the canonical AI theme artifact

**Files:**
- Modify: `artifacts/theme_decomposition/ai_power_value_capture_v1.json`
- Test: `tests/test_theme_decomposition.py`

- [x] Add accepted source records used by reviewed canonical claims and replace generic NVIDIA metadata with precise official URLs.
- [x] Update claims, assessments, evidence strength, and review statuses only where the source pack provides accepted traceable evidence.
- [x] Add or adjust tests for reviewed claims and reviewed nodes, then run both focused test files.

### Task 5: Document Phase 2A findings and boundaries

**Files:**
- Modify: `docs/theme_driven_research_engine_roadmap.md`
- Modify: `docs/theme_decomposition_research_baseline_v1.md`
- Create: `docs/ai_power_source_pack_v1.md`

- [x] Document source-review decisions, accepted and pending sources, reviewed and blocked claims, node evidence gaps, and the boundary that vendor technical material cannot prove market value capture or company investment conclusions.
- [x] Mark Phase 2A complete only if the validator, canonical theme loader, and tests all pass.

### Task 6: Verify the complete Phase 2A baseline

**Files:**
- Verify only.

- [x] Run `.venv/bin/pytest tests/test_ai_power_source_pack.py tests/test_theme_decomposition.py -q`.
- [x] Run `.venv/bin/python -m stock_research.ai_power_source_pack validate`.
- [x] Run `.venv/bin/python -m stock_research.ai_power_source_pack summary`.
- [x] Run `.venv/bin/python -m stock_research.theme_decomposition validate`.
- [x] Inspect JSON validity and the scoped status for accidental unrelated changes.
