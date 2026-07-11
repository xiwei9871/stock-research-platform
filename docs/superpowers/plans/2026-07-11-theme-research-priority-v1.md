# Theme Research Priority And Human Review Queue v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 6's transparent, read-only research-priority scoring and human review queue on top of validated P1-P5 artifacts.

**Architecture:** Store weights, thresholds, materiality conversion, and guardrails in a versioned JSON policy. A standard-library calculator validates that policy, loads P1-P5 packages, computes node/company/evidence-gap rows with component-level explanations, and produces a non-persistent human review queue through CLI/read APIs.

**Tech Stack:** Python 3 standard library, JSON policy artifact, existing P1-P5 loaders, pytest.

---

### Task 1: Define scoring and queue contracts with failing tests

**Files:**
- Create: `tests/test_theme_research_priority.py`

- [x] Test all 34 nodes and all four Phase 4 company mappings are scored exactly once.
- [x] Test a high-value/high-bottleneck/low-evidence node becomes `evidence_collection_priority`.
- [x] Test a high-value/high-bottleneck/strong-evidence node becomes `deep_research_priority`.
- [x] Test company component arithmetic, materiality conversion, priority bands, stable ordering, and rationale codes.
- [x] Test a linked company and the same fixture marked as a coverage gap receive the same merit score.
- [x] Test evidence-gap output, review-queue actions, pending-human-review state, and integration status.
- [x] Test invalid weights, thresholds, materiality mappings, unknown fields, forbidden dimensions, and write-enabled guardrails are rejected.
- [x] Test CLI `validate`, `summary`, `theme-nodes`, `companies`, `evidence-gaps`, `review-queue`, and `show-company`.
- [x] Run the focused test and verify collection fails because `stock_research.theme_research_priority` does not exist.

### Task 2: Implement policy loader and deterministic calculator

**Files:**
- Create: `src/stock_research/theme_research_priority.py`

- [x] Load exactly one `theme_research_priority_policy_v1` artifact and reject open or malformed schemas.
- [x] Validate allowed dimensions, `0-1` weights summing to one, `0-100` thresholds, complete materiality mapping, and strict read-only guardrails.
- [x] Load validated theme decomposition, Phase 4 mapping, and Phase 5 crosswalk packages.
- [x] Compute node deep-research and evidence-gap scores with explicit component dictionaries.
- [x] Compute company relevance, materiality, and company research scores without using market or universe-membership factors.
- [x] Build evidence-gap rows and a deterministic pending-human-review queue.
- [x] Implement detailed read models, summary, stable sorting, and structured-error CLI commands.
- [x] Attach affected company mappings to evidence-gap rows and reject non-finite numeric inputs.
- [x] Re-run focused tests and confirm failure is limited to the absent policy artifact.

### Task 3: Create the v1 policy artifact

**Files:**
- Create: `artifacts/theme_decomposition/priority_policies/theme_research_priority_policy_v1.json`

- [x] Record the approved node, evidence-gap, and company weights.
- [x] Record priority bands, action thresholds, and materiality conversion.
- [x] Declare allowed input dimensions and forbidden market/trading dimensions.
- [x] Set all signal, admission, reviewer-decision, DB, price, and market-position guardrails to false.
- [x] Run focused tests until green and record stable summary counts.

### Task 4: Document and verify Phase 6

**Files:**
- Create: `docs/theme_research_priority_v1.md`
- Modify: `docs/theme_driven_research_engine_roadmap.md`
- Modify: `docs/theme_decomposition_research_baseline_v1.md`

- [x] Document formulas, thresholds, score interpretation, outputs, review queue, and boundaries.
- [x] Mark Phase 6 complete while leaving dashboard, ingestion, and DB phases unfinished.
- [x] Run P1-P6 related pytest suites and all P6 CLI commands.
- [x] Validate policy JSON, compile the module, and scan scoped files for trailing whitespace.
- [x] Request independent read-only code review and close all high/medium findings.
