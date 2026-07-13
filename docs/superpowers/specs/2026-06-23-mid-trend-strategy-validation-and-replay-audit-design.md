# Mid Trend Strategy Validation And Replay Audit Design

## 1. Objective

Define a two-stage validation workflow for the `mid trend` strategy family over the period from `2025-01-01` to the current date.

The workflow has two sequential goals:

1. automatically identify the best and most reliable **currently runnable complete mid-trend portfolio strategy version**;
2. run a detailed **trade replay audit** on that best version to identify selection errors, rebalance errors, and portfolio-control errors.

This work is intended to answer two questions in order:

- among the current `mid trend` strategy versions, which one is the best base version to continue researching?
- after choosing that base version, where exactly does its simulated trade behavior go wrong?

This workflow is not a live execution workflow. It is a research-validation and audit workflow on simulated trades only.

## 2. Scope

### In scope

- backtest period: `2025-01-01` through the current date;
- only `mid trend` strategy-family variants that can produce complete portfolio outputs;
- simulated holdings, simulated trades, simulated equity curves, and their derived diagnostics;
- cross-version ranking using five agreed top-level metrics;
- detailed replay audit for the single best version.

### Out of scope

- real trade records;
- live execution integration;
- direct parameter optimization before baseline selection;
- ad hoc manual stock-by-stock review without reproducible audit outputs;
- pure research-support modules that do not represent complete portfolio strategies.

## 3. Core Decision Order

The workflow must follow this order strictly:

1. collect candidate `mid trend` strategy versions automatically;
2. filter them down to **complete portfolio strategies** only;
3. compare those complete strategies using the agreed five metrics;
4. choose the single best baseline strategy;
5. only then run detailed trade replay audit on that selected baseline;
6. only after the replay audit is complete should any strategy optimization work begin.

The system must not begin deep audit on multiple versions in parallel by default. The goal is first to select the best mother version, then to inspect it deeply.

## 4. Candidate Collection Policy

### 4.1 Auto-collection rule

Candidate collection should scan existing `mid trend` modules and include only strategy entries that satisfy all of the following:

1. have a clear executable entrypoint such as `run_*` or `build_*_from_frames`;
2. produce complete strategy outputs;
3. represent a portfolio strategy rather than a diagnostic helper;
4. can be evaluated over the same date range on a comparable basis.

### 4.2 Complete portfolio strategy definition

A version is considered a complete portfolio strategy only if it can produce, directly or via a stable wrapper, all of the following:

- `holdings`;
- `trades`;
- `equity` or `equity_curve`;
- `summary`.

If any of these are missing, the module may still be used as supporting evidence, but it does not enter the main strategy comparison pool.

### 4.3 Non-candidate classes

The following kinds of modules are not treated as baseline strategy candidates unless they can be lifted into a complete portfolio strategy result with no ambiguity:

- shadow / watch / scan modules;
- review-only modules;
- issue-attribution modules;
- replacement / protection / risk overlays when presented only as partial components;
- candidate-funnel research tools;
- markdown / report generators.

### 4.4 Expected classification

At a minimum, the collection stage should distinguish these groups:

1. complete portfolio strategy versions;
2. protection or rebalance variants attached to a complete strategy;
3. shadow or observation-pool backtests;
4. review / attribution / audit-only modules.

Only group 1 and fully materialized group 2 variants may participate in the final “best version” ranking.

## 5. Comparison Metrics

The strategy comparison stage must use exactly the following five metrics as the top-level ranking basis:

1. `total_return`
2. `max_drawdown`
3. `return_drawdown_ratio`
4. `monthly_win_rate`
5. `turnover_penalized_stability`

### 5.1 Metric intent

`total_return`
- measures directional performance.

`max_drawdown`
- measures capital-path risk and failure severity.

`return_drawdown_ratio`
- measures efficiency of return generation relative to drawdown.

`monthly_win_rate`
- measures consistency over time rather than single-period luck.

`turnover_penalized_stability`
- rewards strategies that achieve acceptable performance with lower churn and steadier holding behavior.

### 5.2 Ranking policy

Ranking must not be based on `total_return` alone.

The recommended decision order is:

1. eliminate versions with clearly unacceptable drawdown behavior;
2. among the remaining versions, prioritize stronger `return_drawdown_ratio`;
3. use `monthly_win_rate` to distinguish stable from unstable winners;
4. use `turnover_penalized_stability` to prefer lower-friction, more reliable versions when returns are similar.

The selected best version should therefore be the best **research baseline**, not merely the highest-return outlier.

## 6. Replay Audit Target

Once the best version is selected, the replay audit stage should focus only on that version.

The replay audit must reconstruct the simulated decision chain day by day:

- candidate pool;
- target holdings;
- previous holdings;
- intended rebalance actions;
- simulated resulting holdings;
- forward performance of each trade decision.

The replay audit should avoid direct strategy-parameter changes at this stage. The goal is first to convert vague dissatisfaction into precise and reproducible failure categories.

## 7. Replay Audit Labels

The audit must classify observed trade issues into the following categories:

- `bad_buy`
- `bad_sell`
- `missed_rebalance`
- `over_rebalance`
- `position_switch_error`

### 7.1 Bad buy

A buy that enters the simulated portfolio correctly according to the strategy, but subsequently performs poorly over the review window.

This category indicates probable problems in:

- candidate quality;
- entry timing;
- buy-side filtering.

### 7.2 Bad sell

A sell that is followed by meaningful continued upside without a strong ex-ante exit justification.

This category indicates probable problems in:

- exit rules;
- protection logic;
- replacement logic.

### 7.3 Missed rebalance

A rebalance action that should have occurred according to the target-holdings transition but did not occur in the simulated realized holdings sequence.

This category indicates probable problems in:

- rebalance execution logic;
- constraint handling;
- reconciliation between target and realized holdings.

### 7.4 Over rebalance

Excessive portfolio turnover that does not improve outcomes and may worsen them.

This category indicates probable problems in:

- noisy replacement logic;
- excessive sensitivity in hold/sell thresholds;
- insufficient persistence rules.

### 7.5 Position switch error

A portfolio-level error where the strategy reallocates capital incorrectly across the book, even if individual names may not all be wrong.

This category indicates probable problems in:

- regime logic;
- portfolio concentration control;
- exposure transition logic;
- replacement ordering.

## 8. Replay Audit Data Model

The replay audit should output at least these four structured artifacts:

### 8.1 `daily_target_snapshot`

One daily snapshot capturing:

- candidate pool;
- target holdings;
- ranks and scores;
- current hold / new entry / drop status.

### 8.2 `daily_rebalance_actions`

One daily action table capturing:

- `buy`;
- `sell`;
- `keep`;
- `replace`;
- replaced-by relationships where applicable.

### 8.3 `trade_audit_detail`

One per-trade audit table capturing:

- buy / sell dates;
- entry rationale fields;
- exit rationale fields;
- forward returns at `+5d`, `+10d`, `+20d`;
- maximum drawdown after entry;
- post-sell continuation strength;
- final audit label.

### 8.4 `monthly_issue_summary`

A monthly aggregation of:

- issue counts by label;
- worst trades by impact;
- concentration of problems by layer, regime, score bucket, or rule state.

## 9. Audit Flow

The replay audit should proceed in this order:

1. reconstruct daily holdings and target-holdings history;
2. derive trade ledger from holdings transitions where needed;
3. identify the worst buy decisions;
4. identify the worst sell decisions;
5. analyze turnover and replacement behavior at portfolio level;
6. only then infer whether the root issue is more likely in selection, rebalancing, or portfolio control.

This order is important because it avoids premature claims about strategy-definition problems before the trade path has been reconstructed.

## 10. Root-Cause Interpretation Rules

The final report should use these interpretation rules:

- if poor outcomes cluster around names that were valid targets at entry but subsequently fail quickly, suspect selection or entry-quality issues;
- if strong names are repeatedly sold too early and continue higher, suspect exit or protection logic;
- if target holdings and realized holdings diverge materially, suspect execution or rebalance logic;
- if turnover is persistently high without better outcomes, suspect over-rebalance behavior;
- if losses are driven by poor capital switching rather than individual-name quality, suspect portfolio-level control logic.

The replay audit should separate **what happened** from **why it probably happened**. Raw trade evidence comes first; interpretation follows after.

## 11. Final Deliverables

The end-to-end validation workflow should produce:

1. a candidate inventory of auto-collected `mid trend` strategy versions;
2. a strategy comparison table with the agreed five metrics;
3. a clear declaration of the single best baseline strategy;
4. a replay-audit packet for that selected strategy;
5. a final conclusion that states:
   - which version is the best current baseline;
   - whether the main issues are selection-side, rebalance-side, or portfolio-control-side;
   - what class of optimization should be attempted next.

## 12. Success Criteria

This design is successful only if, after implementation, it can answer all of the following with reproducible evidence:

1. Which currently available `mid trend` portfolio version is the best and most reliable baseline from `2025-01-01` to the present?
2. Which trade behaviors most damaged that chosen baseline?
3. Are the dominant problems caused by poor stock selection, poor rebalancing, or poor portfolio control?
4. What optimization path should be prioritized next, based on evidence rather than intuition?
