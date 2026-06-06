# Research Infrastructure Method Migration

This migration borrows research-infrastructure methods from ML4Trading without
copying ML4Trading code, notebooks, Zipline dependencies, model templates, or
overseas-market assumptions.

The first implementation slice standardizes two method-layer artifacts:

- Run evidence bundle: one concrete execution with inputs, outputs, warnings,
  metrics, and point-in-time context.
- Experiment registry record: one research idea with objective, hypothesis,
  sample, feature set, label, artifacts, conclusion, and reuse status.
- Feature registry record: one reusable feature definition with source,
  point-in-time rule, lookback, leakage risk, owner, and downstream usage.
- Research signal record: one point-in-time signal observation for one asset,
  date, source, and signal name.
- Factor evaluation card: one standardized review card for an evaluated factor,
  sample, universe, label, IC, quantile returns, turnover, and warnings.
- Attribution card: one comparable diagnosis for a success, failure, miss,
  drawdown, replacement, coverage gap, regime mismatch, or data-quality gap.

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

## Research Signal Layer

Use `ResearchSignalRecord` when a report, PDF, news item, announcement, or
manual review produces a signal observation for a stock on a trade date.

Required fields:

- `asset_id`
- `ts_code`
- `trade_date`
- `signal_name`
- `signal_value`
- `signal_type`
- `source_type`
- `source_id`
- `availability_timestamp`
- `confidence`
- `missingness_reason`

Allowed source types:

- `stock_report`
- `pdf`
- `public_news`
- `fallback_news`
- `announcement`
- `manual_review`

Availability rule:

- Normal records require `availability_timestamp <= trade_date 15:00`.
- Post-close review records must set `post_close_review=True`; they are
  review-only and should not be used as same-day pre-close signals.

Missingness rule:

- Missing coverage is not negative evidence.
- Missing values should use `signal_value=None` and a non-empty
  `missingness_reason`.
- Real negative evidence should keep a real signal value and leave
  `missingness_reason` empty.

Example:

```python
import pandas as pd

from stock_research.research_infra.research_signals import (
    build_research_signal_records_from_frame,
)

frame = pd.DataFrame([
    {
        "asset_id": "asset:000001.SZ",
        "ts_code": "000001.SZ",
        "trade_date": "2026-06-06",
        "research_support_score": 0.72,
        "coverage_freshness_score": None,
        "source_id": "stock_report:000001.SZ:2026-06-01",
        "availability_timestamp": "2026-06-05T15:00:00",
    }
])

records = build_research_signal_records_from_frame(
    frame,
    signal_columns=["research_support_score", "coverage_freshness_score"],
    source_type="stock_report",
    default_confidence="medium",
    missingness_reason="no_fresh_report",
)
```

## Factor Evaluation Card

Use `build_factor_evaluation_card()` when an existing `factor_eval` report needs
to become a comparable review artifact. The card wraps current factor evaluation
outputs; it does not recalculate IC, quantile returns, or turnover.

Required context:

- `sample_window`
- `universe`
- `label_definition`

Included review sections:

- `ic_summary`
- `rank_ic_summary`
- `quantile_return_summary`
- `topn_hit_summary`
- `turnover_summary`
- `regime_breakdown`
- `industry_exposure`
- `drawdown_notes`
- `warnings`

Example:

```python
from stock_research.factor_eval.report import generate_factor_eval_report
from stock_research.research_infra.factor_cards import (
    build_factor_evaluation_card,
    render_factor_evaluation_card_markdown,
)

eval_report = generate_factor_eval_report(
    factors,
    returns,
    factor_name="ret_20",
    return_col="forward_return_5d",
)

card = build_factor_evaluation_card(
    eval_report,
    sample_window={"start_date": "2026-01-01", "end_date": "2026-06-06"},
    universe={"name": "topn_candidates", "asset_count": 300},
    label_definition={"name": "forward_return_5d", "horizon_days": 5},
    warnings=["review sample excludes suspended stocks"],
)

markdown = render_factor_evaluation_card_markdown(card)
```

## Attribution Framework

Use `AttributionCard` when a review needs to explain why a case worked, failed,
missed, or degraded. Attribution cards are comparable review artifacts; they do
not change strategy rules by themselves.

Required fields:

- `case_id`
- `asset_id`
- `ts_code`
- `trade_date`
- `strategy_context`
- `failure_or_success_type`
- `primary_cause`
- `secondary_causes`
- `evidence`
- `counterfactual`
- `preventability`
- `recommended_rule_change`
- `confidence`

Allowed cause categories:

- `bad_buy`
- `missed_winner`
- `sell_too_early`
- `drawdown_control`
- `replacement_failure`
- `research_coverage_gap`
- `industry_regime_mismatch`
- `market_regime_mismatch`
- `data_quality_gap`

Every card must include evidence and a counterfactual. This prevents attribution
from becoming a label-only postmortem.

Example:

```python
from stock_research.research_infra.attribution_cards import (
    AttributionCard,
    render_attribution_card_markdown,
)

card = AttributionCard(
    case_id="case:mid-trend:000001.SZ:2026-06-06",
    asset_id="asset:000001.SZ",
    ts_code="000001.SZ",
    trade_date="2026-06-06",
    strategy_context="mid_trend_review",
    failure_or_success_type="failure",
    primary_cause="research_coverage_gap",
    secondary_causes=["market_regime_mismatch"],
    evidence={
        "research_support_score": None,
        "missingness_reason": "no_fresh_report",
    },
    counterfactual="Would require fresh coverage before promotion.",
    preventability="preventable",
    recommended_rule_change="Block promotion when coverage_freshness_score is missing.",
    confidence="medium",
)

markdown = render_attribution_card_markdown(card)
```

Feedback loop:

- Coverage-gap cards should create feature registry or research signal follow-ups.
- Regime-mismatch cards should create experiment registry follow-ups.
- Data-quality-gap cards should create data-quality remediation tasks.
- Recommended rule changes require a separate experiment before adoption.

## Difference

A run evidence bundle describes one concrete execution. An experiment registry
record describes the research question and reusable conclusion. One experiment
can have multiple run cards if it is repeated across windows, universes, or
feature sets.

A feature registry record describes how a feature should be interpreted and
controlled. It does not compute the feature.

A research signal record describes one observed signal value and its source
availability. It does not decide whether the signal is useful.

A factor evaluation card describes how an already-evaluated factor performed
under a stated sample, universe, and label. It does not compute the factor.

An attribution card describes why a reviewed case succeeded or failed under a
specific context. It does not approve rule changes or production promotion.

## First-Slice Acceptance

- Existing `write_run_card()` callers remain compatible.
- Research runs can produce stricter evidence bundles without changing current
  pipeline code.
- Experiment records can be appended and reviewed as JSONL.
- Duplicate experiment identifiers are detected when reading the registry.
- Missing evidence context and invalid reuse statuses fail fast.
- Existing factor metadata can be exported as feature records.
- Research/news signals have explicit point-in-time and leakage-risk metadata.
- Research signal records reject future availability timestamps by default.
- Missing research coverage is represented separately from negative evidence.
- Factor cards require sample, universe, and label metadata before review.
- Attribution cards require evidence and counterfactuals before review.
