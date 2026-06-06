# Feature Registry Method Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a method-layer feature registry that records source, point-in-time, lookback, leakage risk, ownership, and downstream usage for factor and research/news signal features.

**Architecture:** Add `stock_research.research_infra.feature_registry` without changing current feature calculation modules. The registry reads committed factor metadata from `stock_research.factor_registry` and manually registers first research/news signal records until their source modules are merged.

**Tech Stack:** Python dataclasses, existing factor metadata, pytest, Markdown docs.

---

## Scope

Included:

- Feature metadata contract.
- Category and leakage-risk validation.
- Export helpers for JSON-serializable registry records.
- Existing factor metadata as registry records.
- First research/news signal records: `research_support_score`, `coverage_freshness_score`, `public_news_sentiment_score`.

Excluded:

- Feature calculation.
- Database migration.
- Automatic discovery from uncommitted news/report modules.
- Production eligibility decisions.

## Tasks

### Task 1: Feature Registry Tests

**Files:**

- Test: `tests/test_research_infra_feature_registry.py`

- [x] Write a failing test for exporting existing factor metadata.
- [x] Write a failing test for research/news signal records.
- [x] Write a failing test for JSON-serializable sorted export.
- [x] Write a failing test for missing point-in-time rule and invalid leakage risk.

### Task 2: Feature Registry Implementation

**Files:**

- Create: `src/stock_research/research_infra/feature_registry.py`

- [x] Implement `FeatureRecord`.
- [x] Implement `FeatureRegistryValidationError`.
- [x] Implement `get_feature_record()`, `list_feature_records()`, and `export_feature_registry()`.
- [x] Convert existing `factor_registry` metadata into feature records.
- [x] Add manual method-layer records for first research/news signals.

### Task 3: Documentation

**Files:**

- Modify: `docs/research-infrastructure-method-migration.md`
- Create: `docs/superpowers/plans/2026-06-06-feature-registry-method-slice.md`

- [x] Document Feature Registry purpose.
- [x] Document categories and leakage-risk values.
- [x] Document that registry records describe features but do not compute them.

## Verification

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_run_card.py \
  tests/test_research_infra_run_evidence.py \
  tests/test_research_infra_experiment_registry.py \
  tests/test_research_infra_feature_registry.py \
  -q
```

Expected: all tests pass.
