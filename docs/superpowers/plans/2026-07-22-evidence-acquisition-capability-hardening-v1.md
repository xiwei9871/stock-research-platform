# Evidence Acquisition Capability Hardening v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Diagnose Wave 1b acquisition failures and add deterministic, read-only discovery, qualification, identity, recovery, evidence-shape, and benchmark capabilities without changing formal research coverage.

**Architecture:** Add one integrated capability module and one artifact builder. Reuse frozen acquisition and normalization data, expose four read-only CLI projections, and persist five non-evidence capability artifacts with canonical hashes and upstream bindings.

**Tech Stack:** Python 3.14, argparse, pytest, JSON/JSONL, existing canonical hashing and layered layout.

---

### Task 1: Classification and planning core

**Files:**
- Create: `tests/test_research_project_v2_1_acquisition_capability.py`
- Create: `src/stock_research/research_project_v2_1/acquisition_capability.py`

- [ ] Write failing tests for landing/overview/index/full-text classification, root-cause classes, identity extraction, discovery plans, evidence-shape matching, safe alternatives, encrypted input, and duplicate collapse.
- [ ] Run tests and confirm missing-module failure.
- [ ] Implement pure deterministic functions and rerun until green.

### Task 2: Fixed benchmark and capability artifacts

**Files:**
- Create: `scripts/build_evidence_acquisition_capability_hardening_v1.py`
- Create: `artifacts/research_projects/v2_1/acquisition/capability_hardening_v1/diagnosis.json`
- Create: `artifacts/research_projects/v2_1/acquisition/capability_hardening_v1/benchmark_manifest.json`
- Create: `artifacts/research_projects/v2_1/acquisition/capability_hardening_v1/benchmark_results.json`
- Create: `artifacts/research_projects/v2_1/acquisition/capability_hardening_v1/capability_checkpoint.json`
- Create: `artifacts/research_projects/v2_1/acquisition/capability_hardening_v1/summary.md`

- [ ] Audit all 17 Wave 1b attempts.
- [ ] Run ten fixed offline benchmark cases.
- [ ] Calculate deterministic metrics and canonical hashes.
- [ ] Assert zero formal coverage change and all downstream flags false.

### Task 3: Read-only CLI

**Files:**
- Modify: `src/stock_research/research_project_v2_1/cli.py`
- Modify: `tests/test_research_project_v2_1_acquisition_capability.py`

- [ ] Add diagnose, benchmark, inspect-candidate, and plan-discovery parser routes.
- [ ] Dispatch only to persisted artifacts or pure planning functions.
- [ ] Verify every command leaves the worktree unchanged.

### Task 4: Scope and verification

**Files:**
- Create: `artifacts/research_projects/v2_1/acquisition/capability_hardening_v1_exact_allowlist.json`
- Create: `docs/research_operating_layer_v2_evidence_acquisition_capability_hardening_v1.md`

- [ ] Validate upstream hashes and frozen Wave 1/Wave 1b paths.
- [ ] Run focused, V2/R1-R2, and V1/Theme/Dashboard regressions.
- [ ] Parse JSON/JSONL, validate canonical hashes, scan scope/sensitive data, commit, and confirm a clean worktree.
