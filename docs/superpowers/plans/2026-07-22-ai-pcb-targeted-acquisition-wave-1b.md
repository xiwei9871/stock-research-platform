# AI PCB Targeted Evidence Acquisition Wave 1b Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire and normalize only the Wave 1b Gate-authorized A04, B01, B02, and A02 evidence candidates, then publish one fail-closed acquisition checkpoint without starting assessment.

**Architecture:** Extend the existing Wave 1 acquisition pattern with a dedicated `wave_1b` module and builder. Reuse the direct HTTP provider, immutable raw storage, legacy normalization, provenance, hash, and lineage mechanisms; add only Wave 1b-specific authorization, denominator metadata, checkpoint fields, validation, fixtures, and exact scope attribution.

**Tech Stack:** Python 3.14, pytest, JSON/JSONL, existing Research Operating Layer V2.1 acquisition modules.

---

### Task 1: Add fail-closed Wave 1b contracts

**Files:**
- Create: `tests/test_research_project_v2_1_wave_1b.py`
- Create: `src/stock_research/research_project_v2_1/wave_1b.py`

- [ ] Write failing tests for the frozen Gate hash, exact ER list, A01/A03 rejection, internal phase order, denominator metadata, and disabled downstream flags.
- [ ] Run the focused tests and verify failure because `wave_1b` does not exist.
- [ ] Implement the minimal Gate, candidate, attempt, checkpoint, and repository-bundle validators.
- [ ] Run focused tests and verify the contract tests pass.

### Task 2: Discover and screen exact-scope sources

**Files:**
- Create: `scripts/build_ai_pcb_targeted_acquisition_wave_1b.py`

- [ ] Validate the Gate, Wave 1 Assessment, and Wave 1 checkpoint hashes before discovery.
- [ ] Define candidates only for A04, B01, B02, and A02, with expected denominator fields and source limitations.
- [ ] Prefer primary standards, metrology, peer-reviewed, independent engineering, instrument-method, and second-supplier sources.
- [ ] Record ineligible or blocked leads without assigning unauthorized ER coverage.

### Task 3: Acquire, normalize, and publish the bundle

**Files:**
- Create: `artifacts/research_projects/v2_1/acquisition/wave_1b/candidates.jsonl`
- Create: `artifacts/research_projects/v2_1/acquisition/wave_1b/attempts.jsonl`
- Create: `artifacts/research_projects/v2_1/acquisition/wave_1b/normalized_associations.jsonl`
- Create: `artifacts/research_projects/v2_1/acquisition/wave_1b/evidence_inventory.json`
- Create: `artifacts/research_projects/v2_1/acquisition/wave_1b/acquisition_checkpoint.json`
- Create: `artifacts/research_projects/v2_1/acquisition/wave_1b/summary.md`

- [ ] Execute Phase 1 A04/B01/B02 using direct HTTP, direct proxy mode, provider-local `trust_env=False`, bounded redirects/time/size, and unchanged SSRF checks.
- [ ] Stop before Phase 2 if authorization, security, normalization, source-scope, or denominator readiness fails materially.
- [ ] Execute Phase 2 A02 only after Phase 1 completion.
- [ ] Preserve raw artifacts, normalize successful acquisitions, retain normalization failures, and publish append-only Wave 1b records.
- [ ] Build one checkpoint with per-ER source-class and denominator coverage, duplicate/common-origin groups, date states, security results, and all downstream flags false.

### Task 4: Scope attribution and verification

**Files:**
- Create: `artifacts/research_projects/v2_1/acquisition/wave_1b_exact_allowlist.json`
- Modify: `tests/test_research_project_v2_1_wave_1b.py`
- Create: `docs/research_operating_layer_v2_r2b_ai_pcb_targeted_acquisition_wave_1b.md`

- [ ] Validate all raw hashes and normalized lineage.
- [ ] Verify A01, A03, and every unlisted ER have zero candidate, attempt, acquired, and assessment coverage.
- [ ] Verify Gate, Wave 1 Assessment, Wave 1 checkpoint, cognition package, gap review, and Wave 1 artifacts are unchanged.
- [ ] Run focused, V2/R1-R2, and V1/Theme/Dashboard regressions.
- [ ] Parse all JSON/JSONL, audit sensitive-data and scope leakage, commit, and confirm a clean worktree.
