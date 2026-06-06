# Research Signal Layer Method Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a method-layer research signal contract for point-in-time report, PDF, news, announcement, and manual-review signal observations.

**Architecture:** Add `stock_research.research_infra.research_signals` as a pure contract and conversion-helper module. It does not depend on uncommitted news/report source modules and does not compute signals; it normalizes already-produced frame columns into auditable signal records.

**Tech Stack:** Python dataclasses, pandas, pytest, Markdown docs.

---

## Scope

Included:

- `ResearchSignalRecord` contract.
- Source type and signal type validation.
- Availability timestamp leakage guard.
- Explicit `post_close_review` escape hatch for review-only after-close records.
- DataFrame-to-record conversion helper.
- JSON-serializable export helper.

Excluded:

- News/report ingestion.
- LLM extraction.
- Feature calculation.
- Database migration.
- Same-day trading or execution use.

## Tasks

### Task 1: Research Signal Tests

**Files:**

- Test: `tests/test_research_infra_research_signals.py`

- [x] Write a failing test for JSON-serializable signal records.
- [x] Write a failing test that rejects future availability timestamps.
- [x] Write a failing test that allows explicit post-close review.
- [x] Write a failing test for DataFrame conversion and missingness handling.
- [x] Write a failing test for exported signal rows.

### Task 2: Research Signal Implementation

**Files:**

- Create: `src/stock_research/research_infra/research_signals.py`

- [x] Implement `ResearchSignalRecord`.
- [x] Implement `ResearchSignalValidationError`.
- [x] Implement availability timestamp validation.
- [x] Implement `build_research_signal_records_from_frame()`.
- [x] Implement `export_research_signal_records()`.

### Task 3: Documentation

**Files:**

- Modify: `docs/research-infrastructure-method-migration.md`
- Create: `docs/superpowers/plans/2026-06-06-research-signal-layer-method-slice.md`

- [x] Document required fields and source types.
- [x] Document post-close review rule.
- [x] Document missingness semantics.

## Verification

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_run_card.py \
  tests/test_research_infra_run_evidence.py \
  tests/test_research_infra_experiment_registry.py \
  tests/test_research_infra_feature_registry.py \
  tests/test_research_infra_research_signals.py \
  -q
```

Expected: all tests pass.
