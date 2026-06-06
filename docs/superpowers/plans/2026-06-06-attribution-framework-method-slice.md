# Attribution Framework Method Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a method-layer attribution framework that standardizes success, failure, miss, drawdown, replacement, coverage-gap, regime-mismatch, and data-quality diagnoses.

**Architecture:** Add `stock_research.research_infra.attribution_cards` as a pure contract and rendering layer. It does not modify current attribution, outcome, or review modules; existing modules can map their outputs into attribution cards later.

**Tech Stack:** Python dataclasses, pandas, pytest, Markdown docs.

---

## Scope

Included:

- `AttributionCard` contract.
- Cause category validation.
- Evidence and counterfactual validation.
- DataFrame-to-card conversion helper.
- JSON-serializable export helper.
- Markdown renderer for review packets.

Excluded:

- Strategy-rule adoption.
- Automatic promotion or rejection.
- Rewriting existing mid-trend, strong-winner, watchlist, or outcome analytics modules.
- Database migration.

## Tasks

### Task 1: Attribution Tests

**Files:**

- Test: `tests/test_research_infra_attribution_cards.py`

- [x] Write a failing test for JSON-serializable attribution card output.
- [x] Write a failing test for invalid cause category.
- [x] Write a failing test for missing evidence and counterfactual.
- [x] Write a failing test for Markdown rendering.
- [x] Write a failing test for DataFrame-to-card conversion.
- [x] Write a failing test for export helper.

### Task 2: Attribution Implementation

**Files:**

- Create: `src/stock_research/research_infra/attribution_cards.py`

- [x] Implement `AttributionCard`.
- [x] Implement `AttributionCardValidationError`.
- [x] Implement cause, outcome, and preventability validation.
- [x] Implement `build_attribution_cards_from_frame()`.
- [x] Implement `export_attribution_cards()`.
- [x] Implement `render_attribution_card_markdown()`.

### Task 3: Documentation

**Files:**

- Modify: `docs/research-infrastructure-method-migration.md`
- Create: `docs/superpowers/plans/2026-06-06-attribution-framework-method-slice.md`

- [x] Document required card fields.
- [x] Document allowed cause categories.
- [x] Document feedback loop to feature registry, experiment registry, and data-quality follow-ups.

## Verification

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_run_card.py \
  tests/test_factor_eval.py \
  tests/test_research_infra_run_evidence.py \
  tests/test_research_infra_experiment_registry.py \
  tests/test_research_infra_feature_registry.py \
  tests/test_research_infra_research_signals.py \
  tests/test_research_infra_factor_cards.py \
  tests/test_research_infra_attribution_cards.py \
  -q
```

Expected: all tests pass.
