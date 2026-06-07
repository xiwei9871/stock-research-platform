# ML4Trading Method Infrastructure Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Borrow ML4Trading's research-infrastructure methods for `stock_research` without copying notebooks, Zipline dependencies, overseas-market assumptions, or model code.

**Architecture:** This is a method-layer consolidation over existing `stock_research` capabilities. The first phase standardizes run evidence, experiment records, feature metadata, research/text signals, factor evaluation cards, and attribution outputs while preserving the platform's read-only research boundary.

**Tech Stack:** Python, pandas, existing `stock_research` modules, pytest, Markdown runbooks, JSON/CSV artifacts, existing CLI patterns.

---

## Scope Boundary

This plan migrates methods, not code.

Included:

- Standardized metadata and artifact contracts.
- Registries that describe existing research assets.
- Evaluation cards and evidence bundles that make research comparable.
- Text and report signals as structured research features.
- Attribution categories that convert mistakes and misses into reusable diagnostics.

Excluded:

- Zipline or any ML4Trading runtime dependency.
- Direct notebook migration.
- Direct Alpha101/Alpha191/overseas alpha copying without A-share validation.
- Deep learning templates in phase one.
- Broker, order, execution, cash, account, or automatic portfolio mutation.

## Existing Platform Fit

Current repository evidence shows this is a consolidation task, not a greenfield build:

- Run evidence exists in `src/stock_research/run_card.py` and `reports/run_card/`.
- Factor registry and factor evaluation already exist in `src/stock_research/factor_registry.py` and `src/stock_research/factor_eval/`.
- Research/text signal foundations exist in `src/stock_research/research_narrative.py`, `src/stock_research/news_features.py`, `src/stock_research/topn_news_enrichment.py`, and `src/stock_research/stock_report_*`.
- Attribution work exists across `src/stock_research/mid_trend_*_attribution.py` and `src/stock_research/strong_winner_topn_attribution.py`.
- Watchlist and shadow lifecycle governance already exists under `src/stock_research/watchlist/`, `src/stock_research/dashboard/`, and `docs/quant_system/`.

## Phase Order

| Phase | Module | Priority | Migration Value | Difficulty | Implementation Stance |
| --- | --- | --- | --- | --- | --- |
| 1 | Run Card / Evidence Bundle Standard | P0 | Very high | Low-medium | Extend current run-card contract first. |
| 2 | Experiment Registry | P0 | Very high | Medium | Record research intent, sample, artifacts, result, reuse status. |
| 3 | Feature Registry | P0 | Very high | Medium | Unify factor, technical, text, news, regime, and coverage metadata. |
| 4 | Research Signal Layer | P0 | Very high | Medium-high | Normalize report/news/PDF signals into reusable point-in-time features. |
| 5 | Factor Evaluation Card | P1 | High | Medium | Turn existing factor_eval outputs into a standard card. |
| 6 | Attribution Framework | P1 | High | Medium-high | Consolidate buy-error, sell-miss, drawdown, replacement, coverage, and regime mismatch attribution. |

## Target File Structure

Create these only when implementing the relevant phase:

- `src/stock_research/research_infra/__init__.py`
  - Shared namespace for method-layer contracts.
- `src/stock_research/research_infra/run_evidence.py`
  - Normalized evidence-bundle schema helpers that wrap existing `run_card.py`.
- `src/stock_research/research_infra/experiment_registry.py`
  - Experiment metadata model, validation, JSONL writer, and loader.
- `src/stock_research/research_infra/feature_registry.py`
  - Feature metadata model, leakage-risk rules, and registry export.
- `src/stock_research/research_infra/research_signals.py`
  - Signal contract for report/news/PDF/public-source features.
- `src/stock_research/research_infra/factor_cards.py`
  - Standard factor evaluation-card formatter over existing `factor_eval` output.
- `src/stock_research/research_infra/attribution_cards.py`
  - Standard attribution-card formatter for existing attribution modules.
- `docs/research-infrastructure-method-migration.md`
  - Human runbook explaining the method boundary and usage rules.
- `tests/test_research_infra_*.py`
  - Focused tests for each phase.

Do not move existing modules during phase one. Introduce wrappers and standards first, then migrate callers only after the contracts are stable.

## Task 1: Standardize Run Evidence Bundle

**Files:**

- Modify: `src/stock_research/run_card.py`
- Create: `src/stock_research/research_infra/__init__.py`
- Create: `src/stock_research/research_infra/run_evidence.py`
- Test: `tests/test_research_infra_run_evidence.py`
- Document: `docs/research-infrastructure-method-migration.md`

- [ ] Define a required evidence-bundle contract with these fields: `run_type`, `run_id`, `research_question`, `sample_window`, `universe`, `feature_set`, `label_definition`, `input_artifacts`, `output_artifacts`, `warnings`, `caveats`, `reuse_status`.
- [ ] Add validation that rejects missing `research_question`, missing `sample_window`, missing `universe`, and missing `output_artifacts`.
- [ ] Wrap existing `write_run_card()` instead of replacing it.
- [ ] Add a test that writes a complete evidence bundle and verifies `run_card.json`, `run_card.md`, `config_snapshot.json`, `metrics.json`, `data_coverage.json`, and `evidence/manifest.json` exist.
- [ ] Add a test that incomplete evidence raises a clear validation error.
- [ ] Update the runbook with one minimal example for daily factor research and one for mid-trend review.

Acceptance:

- Existing `write_run_card()` callers remain compatible.
- New evidence bundle can be adopted by one caller without changing unrelated workflows.
- Evidence output is deterministic enough for tests except timestamped directory names.

## Task 2: Add Experiment Registry

**Files:**

- Create: `src/stock_research/research_infra/experiment_registry.py`
- Test: `tests/test_research_infra_experiment_registry.py`
- Document: `docs/research-infrastructure-method-migration.md`

- [ ] Define an `ExperimentRecord` with: `experiment_id`, `created_at`, `objective`, `hypothesis`, `sample_window`, `universe`, `feature_set_id`, `label_id`, `model_or_rule_version`, `constraints`, `artifact_paths`, `conclusion`, `reuse_status`.
- [ ] Support `reuse_status` values: `draft`, `validated`, `rejected`, `monitor_only`, `superseded`.
- [ ] Add JSONL append and read helpers under a caller-provided path such as `outputs/research/experiment_registry.jsonl`.
- [ ] Add duplicate `experiment_id` detection when reading a registry file.
- [ ] Add tests for round-trip write/read, invalid reuse status, and duplicate detection.
- [ ] Document how this differs from a run card: experiment registry describes research intent and conclusion; run card describes one concrete execution.

Acceptance:

- A mid-trend experiment can be registered without adding a database migration.
- Registry can be reviewed as a plain JSONL artifact.

## Task 3: Add Feature Registry

**Files:**

- Create: `src/stock_research/research_infra/feature_registry.py`
- Test: `tests/test_research_infra_feature_registry.py`
- Document: `docs/research-infrastructure-method-migration.md`

- [ ] Define a `FeatureRecord` with: `feature_name`, `category`, `input_source`, `point_in_time_rule`, `lookback_window`, `leakage_risk`, `owner_module`, `downstream_usage`, `availability_start_date`, `status`.
- [ ] Support categories: `technical`, `factor`, `text`, `news`, `industry_regime`, `market_regime`, `research_coverage`, `event`.
- [ ] Support leakage risk values: `low`, `medium`, `high`, `blocked`.
- [ ] Add helper records for existing factor metadata from `src/stock_research/factor_registry.py`.
- [ ] Add manual records for existing research/text features in `research_narrative.py` and `news_features.py`.
- [ ] Add tests that registry export includes existing factor records and at least one research/text feature record.
- [ ] Document that no feature is considered production-eligible unless it has a point-in-time rule and leakage-risk classification.

Acceptance:

- Existing factor names can be listed with metadata and leakage context.
- Text/news/research coverage features are visible in the same registry as technical/factor features.

## Task 4: Normalize Research Signal Layer

**Files:**

- Create: `src/stock_research/research_infra/research_signals.py`
- Modify only after review: `src/stock_research/research_narrative.py`, `src/stock_research/news_features.py`, `src/stock_research/topn_news_enrichment.py`
- Test: `tests/test_research_infra_research_signals.py`
- Document: `docs/research-infrastructure-method-migration.md`

- [ ] Define a `ResearchSignalRecord` with: `asset_id`, `ts_code`, `trade_date`, `signal_name`, `signal_value`, `signal_type`, `source_type`, `source_id`, `availability_timestamp`, `confidence`, `missingness_reason`.
- [ ] Support source types: `stock_report`, `pdf`, `public_news`, `fallback_news`, `announcement`, `manual_review`.
- [ ] Provide conversion helpers for existing research fact sheet and news feature frames.
- [ ] Add tests for point-in-time alignment: records must not accept source timestamps after `trade_date` unless explicitly marked as post-close review.
- [ ] Add tests for missingness handling: absent reports and absent news must produce explicit `missingness_reason`, not silent zeroes.
- [ ] Document first supported signals: `research_support_score`, `coverage_freshness_score`, `risk_disclosure_score`, `consensus_strength_score`, `narrative_alignment_score`.

Acceptance:

- Existing report/news outputs can be represented as rows in a common signal layer.
- Missing research coverage is distinguishable from negative research evidence.

## Task 5: Standardize Factor Evaluation Card

**Files:**

- Create: `src/stock_research/research_infra/factor_cards.py`
- Modify only after review: `src/stock_research/factor_eval/report.py`
- Test: `tests/test_research_infra_factor_cards.py`
- Document: `docs/research-infrastructure-method-migration.md`

- [ ] Define a factor card output with: `factor_name`, `sample_window`, `universe`, `label_definition`, `ic_summary`, `rank_ic_summary`, `quantile_return_summary`, `topn_hit_summary`, `turnover_summary`, `regime_breakdown`, `industry_exposure`, `drawdown_notes`, `warnings`.
- [ ] Wrap existing `generate_factor_eval_report()` output into a JSON-serializable card.
- [ ] Add validation that the card contains sample and universe metadata.
- [ ] Add tests for a minimal factor card built from toy factor and return frames.
- [ ] Add a Markdown renderer for analyst review.

Acceptance:

- A factor is not reviewed only by raw IC or return tables.
- Every factor card states what sample, universe, horizon, and label it used.

## Task 6: Standardize Attribution Framework

**Files:**

- Create: `src/stock_research/research_infra/attribution_cards.py`
- Modify only after review: existing `src/stock_research/mid_trend_*_attribution.py` modules and `src/stock_research/strong_winner_topn_attribution.py`
- Test: `tests/test_research_infra_attribution_cards.py`
- Document: `docs/research-infrastructure-method-migration.md`

- [ ] Define an `AttributionCard` with: `case_id`, `asset_id`, `ts_code`, `trade_date`, `strategy_context`, `failure_or_success_type`, `primary_cause`, `secondary_causes`, `evidence`, `counterfactual`, `preventability`, `recommended_rule_change`, `confidence`.
- [ ] Support cause categories: `bad_buy`, `missed_winner`, `sell_too_early`, `drawdown_control`, `replacement_failure`, `research_coverage_gap`, `industry_regime_mismatch`, `market_regime_mismatch`, `data_quality_gap`.
- [ ] Add a Markdown renderer for review packets.
- [ ] Add tests for valid card creation, invalid cause category, and evidence rendering.
- [ ] Document the feedback loop: attribution cards feed feature registry updates, experiment registry follow-ups, and rule-change proposals.

Acceptance:

- Attribution output becomes comparable across mid-trend, strong-winner, TopN, and watchlist reviews.
- The framework records evidence and counterfactuals without implying automatic trade execution.

## Migration Governance

- Implement phases sequentially. Do not migrate callers in bulk.
- Each phase should end with one thin integration example and focused tests.
- Existing scripts remain source-of-truth until the new contract is verified.
- Every new registry or card must preserve point-in-time semantics.
- Any signal without availability timestamp is review-only and must be labelled as such.
- Every implementation PR should include one before/after artifact example.

## First Implementation Slice

The first concrete slice should be Task 1 plus a minimal Task 2 registry:

- Run evidence bundle wrapper.
- Experiment registry JSONL model.
- One documented example showing how a mid-trend review run produces both a run card and experiment record.

This slice is small enough to validate the migration method without touching factor evaluation, research signal extraction, or attribution modules.

## Verification Commands

Run focused backend tests after each phase:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_research_infra_run_evidence.py -q
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_research_infra_experiment_registry.py -q
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_research_infra_feature_registry.py -q
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_research_infra_research_signals.py -q
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_research_infra_factor_cards.py -q
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_research_infra_attribution_cards.py -q
```

Run the existing impacted areas before declaring the method layer stable:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_run_card.py \
  tests/test_factor_eval.py \
  tests/test_factor_config.py \
  tests/test_research_narrative.py \
  tests/test_news_features.py \
  tests/test_mid_trend_rebalance_attribution.py \
  tests/test_strong_winner_topn_attribution.py \
  -q
```

If some listed tests do not exist in the current checkout, replace them with the closest existing tests for the touched module and record the substitution in the run card warnings.

## Self-Review

- Scope coverage: The plan covers the approved boundary: methods only, no ML4Trading code migration.
- Dependency check: No Zipline, notebook-first workflow, deep-learning template pack, or broker/execution dependency is introduced.
- Point-in-time check: Every registry/card that can affect research conclusions records availability or leakage context.
- Implementation risk: The plan uses wrappers first and delays caller migration, limiting blast radius in the current dirty worktree.
