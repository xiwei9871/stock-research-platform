# Factor Evaluation Card Method Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a method-layer factor evaluation card that wraps existing factor evaluation outputs into a consistent JSON/Markdown review artifact.

**Architecture:** Add `stock_research.research_infra.factor_cards` as a formatting and validation layer over `stock_research.factor_eval.report.generate_factor_eval_report()`. The module does not compute factors or replace existing factor evaluation code.

**Tech Stack:** Python, pandas, existing factor_eval outputs, pytest, Markdown docs.

---

## Scope

Included:

- Required sample, universe, and label metadata validation.
- JSON-serializable factor card output.
- IC, RankIC, quantile return, top-bottom spread, turnover, regime, industry, drawdown, and warning sections.
- Markdown renderer for analyst review.

Excluded:

- Factor calculation.
- New IC or return algorithms.
- Database migration.
- Production promotion logic.

## Tasks

### Task 1: Factor Card Tests

**Files:**

- Test: `tests/test_research_infra_factor_cards.py`

- [x] Write a failing test for wrapping an existing factor eval report.
- [x] Write a failing test for missing required metadata.
- [x] Write a failing test for Markdown rendering.

### Task 2: Factor Card Implementation

**Files:**

- Create: `src/stock_research/research_infra/factor_cards.py`

- [x] Implement `FactorCardValidationError`.
- [x] Implement `build_factor_evaluation_card()`.
- [x] Summarize quantile returns and top-bottom spread.
- [x] Summarize turnover.
- [x] Implement `render_factor_evaluation_card_markdown()`.

### Task 3: Documentation

**Files:**

- Modify: `docs/research-infrastructure-method-migration.md`
- Create: `docs/superpowers/plans/2026-06-06-factor-evaluation-card-method-slice.md`

- [x] Document required card context.
- [x] Document that cards wrap existing factor eval reports.
- [x] Document Markdown review usage.

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
  -q
```

Expected: all tests pass.
