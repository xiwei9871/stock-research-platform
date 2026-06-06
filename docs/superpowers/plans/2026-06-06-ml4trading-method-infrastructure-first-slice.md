# ML4Trading Method Infrastructure First Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first method-layer migration slice: stricter run evidence bundles and a JSONL experiment registry.

**Architecture:** Add a `stock_research.research_infra` namespace that wraps existing platform artifacts instead of moving current pipelines. `run_evidence.py` delegates to the existing `run_card.py`; `experiment_registry.py` stores research intent and conclusion as reviewable JSONL.

**Tech Stack:** Python, existing `stock_research.run_card`, pytest, JSONL, Markdown docs.

---

## Scope

Included:

- `Run Evidence Bundle` wrapper over existing run-card output.
- `Experiment Registry` JSONL model and helpers.
- Documentation that states this is method migration, not ML4Trading code migration.

Excluded:

- Zipline, notebooks, model templates, overseas alpha copying, and broker/execution state.
- Feature registry, research signal layer, factor cards, and attribution cards; those are later phases.

## Tasks

### Task 1: Run Evidence Bundle

**Files:**

- Create: `src/stock_research/research_infra/__init__.py`
- Create: `src/stock_research/research_infra/run_evidence.py`
- Test: `tests/test_research_infra_run_evidence.py`

- [x] Write a failing test for complete evidence-bundle artifact output.
- [x] Write a failing test for missing required research context.
- [x] Implement `EvidenceBundleValidationError`.
- [x] Implement `write_evidence_bundle()` as a wrapper around `write_run_card()`.
- [x] Verify focused tests pass.

### Task 2: Experiment Registry

**Files:**

- Create: `src/stock_research/research_infra/experiment_registry.py`
- Test: `tests/test_research_infra_experiment_registry.py`

- [x] Write a failing test for JSONL write/read round trip.
- [x] Write a failing test for invalid `reuse_status`.
- [x] Write a failing test for duplicate `experiment_id` detection.
- [x] Implement `ExperimentRecord`.
- [x] Implement append and read helpers.
- [x] Verify focused tests pass.

### Task 3: Documentation

**Files:**

- Create: `docs/research-infrastructure-method-migration.md`
- Create: `docs/superpowers/plans/2026-06-06-ml4trading-method-infrastructure-first-slice.md`

- [x] Document method boundary.
- [x] Document run evidence bundle usage.
- [x] Document experiment registry usage.
- [x] Include a mid-trend review example.

## Verification

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_run_card.py \
  tests/test_research_infra_run_evidence.py \
  tests/test_research_infra_experiment_registry.py \
  -q
```

Expected: all tests pass.
