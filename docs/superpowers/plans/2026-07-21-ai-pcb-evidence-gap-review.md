# AI PCB Evidence Gap Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate an offline integrated research design for the ten frozen AI PCB evidence gaps, with a deterministic report and no acquisition or downstream conclusions.

**Architecture:** Add one compact Schema 2.6.0 and one focused module that loads, validates and renders the integrated artifact. The artifact is the sole fact source; the Markdown report is a deterministic projection. Existing cognition and acquisition artifacts are immutable hash-bound inputs.

**Tech Stack:** Python 3.14, JSON Schema Draft 2020-12, canonical JSON/SHA-256 utilities, pytest, existing Research Operating Layer V2.1 layout and loader patterns.

---

### Task 1: Define the strict artifact contract

**Files:**
- Create: `artifacts/research_projects/v2_1/schema/evidence_gap_review_v2_6.schema.json`
- Modify: `src/stock_research/research_project_v2_1/schema.py`
- Create: `tests/test_research_project_v2_1_gap_review.py`
- Modify: `tests/test_research_project_v2_1_schema.py`

- [ ] Write failing tests for the artifact discriminator, required top-level fields, false authorization flags and schema registry.
- [ ] Run the focused schema tests and verify they fail because Schema 2.6.0 is absent.
- [ ] Add the compact schema and registry entry with strict top-level objects and semantic arrays.
- [ ] Run the schema tests and verify they pass.
- [ ] Commit as `feat: define evidence gap review contract`.

### Task 2: Validate immutable inputs and the ten-gap universe

**Files:**
- Create: `src/stock_research/research_project_v2_1/gap_review.py`
- Modify: `tests/test_research_project_v2_1_gap_review.py`

- [ ] Write failing tests for cognition-package hash drift, unknown gap IDs, missing gaps, duplicated gaps and invalid group assignment.
- [ ] Run the tests and verify the missing loader/validator failure.
- [ ] Implement managed-root loading, canonical hash validation, upstream package validation and exact gap-universe comparison.
- [ ] Verify fixed grouping A/B/C/D and one-group-per-gap semantics.
- [ ] Run focused tests and commit as `feat: bind gap review to cognition baseline`.

### Task 3: Enforce atomic research design and cognition ceilings

**Files:**
- Modify: `src/stock_research/research_project_v2_1/gap_review.py`
- Modify: `tests/test_research_project_v2_1_gap_review.py`

- [ ] Write failing tests for missing atomic questions, ER reuse across gaps, missing evidence types, missing denominators, missing stopping rules and missing prohibited inferences.
- [ ] Add tests rejecting future acquisition, Stage A2/Stage B authorization, unsupported availability states and structurally limited issues promised as fully resolvable.
- [ ] Implement ER registry validation, dependency validation, public-evidence ceiling rules and inference-level separation.
- [ ] Run focused tests and commit as `feat: enforce targeted research design boundaries`.

### Task 4: Add deterministic report projection

**Files:**
- Modify: `src/stock_research/research_project_v2_1/gap_review.py`
- Modify: `tests/test_research_project_v2_1_gap_review.py`

- [ ] Write failing tests for stable rendering, fixed sorting, visible research-design labels and rejection of report-added content.
- [ ] Implement a canonical Markdown renderer and byte-for-byte persisted-report validation.
- [ ] Run focused tests and commit as `feat: render evidence gap research design`.

### Task 5: Build the integrated research-design artifact

**Files:**
- Create: `artifacts/research_projects/v2_1/analysis/ai_pcb_evidence_gap_review_and_targeted_research_design_v1.json`
- Create: `artifacts/research_projects/v2_1/reports/ai_pcb_evidence_gap_review_and_targeted_research_design_v1.md`
- Modify: `tests/test_research_project_v2_1_gap_review.py`

- [ ] Write a repository-artifact test requiring all ten gaps, valid grouping, atomic ER references, no authorization and deterministic rendering.
- [ ] Build the artifact from the frozen package without changing any upstream file.
- [ ] Generate the report exclusively through the renderer.
- [ ] Run focused validation and commit as `feat: add AI PCB evidence gap research design`.

### Task 6: Lock method and exact scope

**Files:**
- Create: `docs/research_operating_layer_v2_r2b_ai_pcb_evidence_gap_review.md`
- Create: `artifacts/research_projects/v2_1/governance/evidence_gap_review_exact_allowlist.json`
- Modify: `tests/test_research_project_v2_1_r2b_scope_guard.py`

- [ ] Write a failing scope test based on commit `989b1258c54000990349692f4b07b968e8eaabd5`.
- [ ] Add the exact path allowlist and method note.
- [ ] Verify no acquisition, evidence, cognition baseline or downstream path changed.
- [ ] Commit as `docs: lock evidence gap review scope`.

### Task 7: Final verification and stop

**Files:** No new files unless a verified defect requires a tested correction.

- [ ] Verify cognition package, audit, report, acquisition checkpoint, raw and normalized artifacts are unchanged from the baseline.
- [ ] Run `tests/test_research_project_v2_1_gap_review.py`, schema and scope-guard focused tests.
- [ ] Run `tests/test_research_project_v2*.py`.
- [ ] Run Dashboard/Theme/Industry Catalog/V1 schema regression.
- [ ] Parse all JSON/JSONL, recompute artifact/report hashes and scan for partial files, secrets and scope leakage.
- [ ] Report group distribution, atomic-question and ER counts, availability/ceiling counts, structural limits, stopping rules and inference boundaries.
- [ ] Confirm future acquisition is false, no bottleneck/value migration conclusion exists, the worktree is clean, then stop.
