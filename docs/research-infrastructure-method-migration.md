# Research Infrastructure Method Migration

This migration borrows research-infrastructure methods from ML4Trading without
copying ML4Trading code, notebooks, Zipline dependencies, model templates, or
overseas-market assumptions.

The first implementation slice standardizes two method-layer artifacts:

- Run evidence bundle: one concrete execution with inputs, outputs, warnings,
  metrics, and point-in-time context.
- Experiment registry record: one research idea with objective, hypothesis,
  sample, feature set, label, artifacts, conclusion, and reuse status.
- Feature registry record: one reusable feature or signal with source,
  point-in-time rule, lookback, leakage risk, owner, and downstream usage.

These artifacts are review-only. They do not create broker, order, account,
cash, position, fill, or execution state.

## Run Evidence Bundle

Use `write_evidence_bundle()` when a research run should leave an auditable
evidence package.

Required research context:

- `research_question`
- `sample_window`
- `universe`
- `feature_set`
- `label_definition`
- `input_artifacts`
- `output_artifacts`

The wrapper keeps the existing `write_run_card()` artifact layout:

- `run_card.json`
- `run_card.md`
- `config_snapshot.json`
- `metrics.json`
- `data_coverage.json`
- `warnings.md`
- `evidence/manifest.json`

Example:

```python
from stock_research.research_infra.run_evidence import write_evidence_bundle

run_card = write_evidence_bundle(
    output_dir="reports/run_card",
    run_type="mid_trend_review",
    run_id="mid-trend-review-2026-06-06",
    title="Mid Trend Review 2026-06-06",
    research_question="Which candidates deserve continued review after drawdown control?",
    sample_window={"start_date": "2026-05-01", "end_date": "2026-06-06"},
    universe={"name": "mid_trend_watchlist", "asset_count": 20},
    feature_set=["ret_20", "research_support_score"],
    label_definition={"name": "entry_success_20d", "horizon_days": 20},
    input_artifacts={"candidates": "outputs/research/candidates.csv"},
    output_artifacts={"review": "outputs/research/mid_trend_review.md"},
    metrics={"reviewed_count": 20},
    warnings=["research coverage is thin for two candidates"],
    caveats=["review-only; no execution instruction"],
    reuse_status="monitor_only",
)
```

## Experiment Registry

Use `ExperimentRecord` when the platform needs to retain the research intent
and conclusion behind one or more runs.

Allowed `reuse_status` values:

- `draft`
- `validated`
- `rejected`
- `monitor_only`
- `superseded`

The registry is JSONL so it can be reviewed and archived without a database
migration in the first slice.

Example:

```python
from stock_research.research_infra.experiment_registry import (
    ExperimentRecord,
    append_experiment_record,
)

record = ExperimentRecord(
    experiment_id="mid-trend-drawdown-control-2026-06-06",
    created_at="2026-06-06T09:30:00",
    objective="Validate drawdown-control review signal for mid-trend candidates.",
    hypothesis="Candidates with fresh research support recover better after short drawdowns.",
    sample_window={"start_date": "2026-05-01", "end_date": "2026-06-06"},
    universe={"name": "mid_trend_watchlist", "asset_count": 20},
    feature_set_id="feature-set:mid-trend-research-v1",
    label_id="label:entry-success-20d",
    model_or_rule_version="mid_trend_review_v1",
    constraints={"review_only": True, "max_turnover": "n/a"},
    artifact_paths={
        "run_card": run_card["run_card_json_path"],
        "review": "outputs/research/mid_trend_review.md",
    },
    conclusion="Keep as monitor-only until wider sample confirms stability.",
    reuse_status="monitor_only",
)
append_experiment_record("outputs/research/experiment_registry.jsonl", record)
```

## Feature Registry

Use `FeatureRecord` and registry helpers when the platform needs a unified view
of factor, technical, research coverage, news, regime, and event features.

The current slice registers two kinds of features:

- Existing committed factor metadata from `stock_research.factor_registry`.
- Method-layer research/news signal records that can be connected to concrete
  source modules after those modules are merged.

Every record must state a point-in-time rule and leakage-risk classification.
No feature should be treated as production-eligible without both fields.

Allowed categories:

- `technical`
- `factor`
- `text`
- `news`
- `industry_regime`
- `market_regime`
- `research_coverage`
- `event`

Allowed leakage-risk values:

- `low`
- `medium`
- `high`
- `blocked`

Example:

```python
from stock_research.research_infra.feature_registry import (
    export_feature_registry,
    get_feature_record,
)

ret_20 = get_feature_record("ret_20")
assert ret_20.point_in_time_rule == "uses market data available on or before trade_date"

records = export_feature_registry([
    "research_support_score",
    "coverage_freshness_score",
    "public_news_sentiment_score",
])
```

## Difference

A run evidence bundle describes one concrete execution. An experiment registry
record describes the research question and reusable conclusion. One experiment
can have multiple run cards if it is repeated across windows, universes, or
feature sets.

A feature registry record describes how a feature should be interpreted and
controlled. It does not compute the feature.

## First-Slice Acceptance

- Existing `write_run_card()` callers remain compatible.
- Research runs can produce stricter evidence bundles without changing current
  pipeline code.
- Experiment records can be appended and reviewed as JSONL.
- Duplicate experiment identifiers are detected when reading the registry.
- Missing evidence context and invalid reuse statuses fail fast.
- Existing factor metadata can be exported as feature records.
- Research/news signals have explicit point-in-time and leakage-risk metadata.
