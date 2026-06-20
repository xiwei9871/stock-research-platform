# Daily Review v1 Design

## Goal

Build a daily 22:00 review report package that composes existing stock research platform outputs into a stable Markdown and JSON review artifact. The first phase is report-first, read-only, and manual-review oriented; it does not build a dashboard page, mutate real positions, manage cash, place orders, or create broker/order state.

## Scope

Daily Review v1 produces:

- `manifest.json`: run metadata, source readiness, warnings, and artifact paths.
- `daily_review.json`: structured review output shaped for future `review.*` read models.
- `daily_review.md`: human-readable review report.
- `operator_plan_template.json`: a manual next-day plan template with no automatic execution semantics.
- `evidence/*.json`: per-module source summaries used to render the review.

Default output layout:

```text
reports/daily_review/YYYY-MM-DD/
  manifest.json
  daily_review.json
  daily_review.md
  operator_plan_template.json
  evidence/
    market_state.json
    lhb_review.json
    mid_trend_review.json
    technical_bottleneck_review.json
```

The first phase adds a CLI entrypoint that can be run manually for a specific trade date. Scheduling, dashboard pages, weekly review, full `review.*` persistence, real account attribution, and advanced fundamental bottleneck research are intentionally out of scope.

## Architecture

Daily Review v1 is a thin report orchestration layer over existing platform modules and persisted artifacts. It should prefer existing data and reports from:

- `ops.daily_pipeline_status` and daily close pipeline outputs for data readiness.
- `market_emotion_state_v1` and `market_regime_confirmation_v1` outputs for public market state.
- Existing style/sector reports or available report artifacts for style and sector context.
- `lhb_data.py` daily LHB shortline outputs, strategy effectiveness outputs, watchlist diagnostics, and auction/intraday artifacts when available.
- `current_mid_trend_strategy_v1.py`, `mid_trend_portfolio_review.py`, and `mid_trend_position_dossier.py` outputs for trend portfolio state.
- `stock_technical_features_daily`, trend lifecycle outputs, and existing technical discovery artifacts for `technical_bottleneck_review_v1`.
- `report.report_run` for registering generated report paths.

The orchestrator should tolerate missing optional sources. If all required report scaffolding can be generated but one or more module sources are missing, the run status is `partial`, not failed. The manifest and Markdown must name missing sources and explain which conclusions have lower confidence.

## JSON Contract

`daily_review.json` is the canonical first-phase contract. It should be stable enough to map later into:

- `review.daily_review_run`
- `review.daily_strategy_item`
- `review.operator_review_decision`

Top-level shape:

```json
{
  "trade_date": "2026-06-20",
  "run_id": "daily_review_v1_20260620_2200",
  "report_type": "daily_review_v1",
  "schema_version": "daily_review_v1",
  "status": "success",
  "data_readiness": {},
  "market_review": {},
  "strategy_summaries": {
    "lhb": {},
    "mid_trend": {},
    "technical_bottleneck": {}
  },
  "strategy_items": [],
  "holding_reviews": [],
  "operator_plan": {},
  "next_day_plan": {},
  "report_paths": {},
  "warnings": []
}
```

`status` is one of:

- `success`: required and optional sources used by enabled modules are available.
- `partial`: the package was generated but one or more sources are missing or stale.
- `failed`: the package could not be generated.

`strategy_items` is the future item read model shape:

```json
{
  "trade_date": "2026-06-20",
  "strategy_id": "lhb",
  "asset_id": "CN:SH:600000",
  "ts_code": "600000.SH",
  "stock_name": "",
  "item_type": "candidate",
  "bucket": "trial_list",
  "state": "watch",
  "action": "manual_review",
  "review_priority": "P1",
  "confidence": "medium",
  "reason": {},
  "evidence": {},
  "source_refs": []
}
```

`review_priority` is one of:

- `P0`: must review before the next open.
- `P1`: important review item for the next session.
- `P2`: normal watch item.
- `P3`: low-priority context item.

Any field named `action` must use a controlled enum, not free text. First-phase values are:

- `no_action`
- `manual_review`
- `watch`
- `add_candidate`
- `hold`
- `warning`
- `reduce_review`
- `exit_review`
- `forbidden`
- `research_required`

`holding_reviews` keeps strategy ownership explicit so short-line, mid-trend, and bottleneck logic do not overwrite each other:

```json
{
  "trade_date": "2026-06-20",
  "strategy_id": "mid_trend",
  "asset_id": "CN:SZ:000001",
  "entry_reason": "",
  "holding_logic": "",
  "current_state": "healthy",
  "risk_status": "normal",
  "action": "hold",
  "exit_condition": "",
  "evidence": {}
}
```

The same `asset_id` may appear multiple times in `holding_reviews` when it is reviewed under different `strategy_id` values. Daily Review v1 must not merge LHB, Mid Trend, and Technical Bottleneck holding logic into a single overwritten row. The natural uniqueness key for later persistence is `(trade_date, strategy_id, asset_id, entry_reason)` or an explicit item id derived from those fields, not just `(trade_date, asset_id)`.

`operator_plan` is manual and non-executing:

```json
{
  "mode": "manual_review_only",
  "overall_position_bias": "defensive",
  "must_check_before_open": [],
  "forbidden_actions": [],
  "manual_decisions": []
}
```

Forbidden field semantics include automatic orders, broker actions, cash mutation, real position mutation, or any implication that the platform has placed or will place a trade.

## Daily Modules

### Data Readiness

The report begins with source readiness:

- daily bars
- 5-minute bars
- auction data
- LHB data
- sector/style context
- market emotion/regime
- Mid Trend artifacts
- bottleneck artifacts
- watchlist/report artifacts

Each source records:

- `status`: `ready`, `missing`, `stale`, `partial`, or `not_configured`
- `required`: boolean
- `summary`
- `freshness`: object with `latest_available_date`, `expected_date`, `is_fresh`, and optional `max_allowed_lag_days`
- `confidence_impact`: short explanation of how missing or stale data affects conclusions
- `blocking_modules`: list of review module ids affected by this source, such as `market_review`, `lhb_review`, `mid_trend_review`, or `technical_bottleneck_review`
- `source_refs`

Missing optional sources downgrade the overall run to `partial`. Missing core scaffolding needed to write the package is `failed`.

### Market Review

Purpose: decide the risk environment for all strategies.

Fields:

- `market_regime_score`
- `emotion_state`
- `risk_state`
- `trend_environment`
- `liquidity_state`
- `style_bias`
- `target_exposure`
- `market_comment`

The Markdown output should state the market status in direct review language, such as strong, neutral, weak, extremely weak, short-line warming, divergence, retreat, or cold.

### LHB Review

Purpose: decide whether short-line/LHB can be traded manually the next day.

Fields:

- `short_allowed`
- `short_market_state`
- `emotion_phase`
- `lhb_watchlist`
- `yesterday_lhb_feedback`
- `auction_focus_list`
- `allowed_list`
- `trial_list`
- `defense_list`
- `no_trade_list`

Daily conclusion uses one of:

- `attack`
- `trial`
- `defense`
- `no_trade`

The report must distinguish watch candidates from forbidden chase candidates.

### Mid Trend Review

Purpose: decide whether medium-term trend holdings remain healthy and whether manual rebalance review is needed.

Fields:

- `portfolio_health`
- `holding_health_list`
- `topn_relation`
- `top50_relation`
- `protection_events`
- `candidate_adds`
- `candidate_reduces`
- `candidate_exits`
- `rebalance_suggestion`

Daily actions are conservative: `hold`, `warning`, `reduce_review`, `exit_review`, `add_candidate`, or `no_action`. The module should avoid high-turnover daily replacement behavior.

### Technical Bottleneck Review

Purpose: monitor long-cycle technical bottleneck opportunities and status migration.

Module name: `technical_bottleneck_review_v1`.

It must not reuse `technical_feature_performance_review`, because that name refers to technical feature compute/performance review rather than strategy opportunity review.

Pool layers:

- `S0_raw_scan`
- `S1_observation`
- `S2_prepare`
- `S3_trading_candidate`
- `S4_validated_mid_trend`

Fields:

- `new_observations`
- `upgraded_items`
- `downgraded_items`
- `near_breakout_items`
- `failed_breakout_items`
- `research_required_items`
- `migration_summary`

First phase can use technical state and available research artifacts only. Deep fundamental validation is reserved for later phases.

### Holding Review And Operator Plan

Holdings and candidates remain strategy-scoped:

- `strategy_id`
- `entry_reason`
- `holding_logic`
- `exit_condition`
- `review_frequency`

The output may produce manual checklists and risk reminders, but it must not claim to execute trades.

Preferred language:

- `operator_plan`
- `execution_checklist`
- `rule_violation_check`
- `manual_decision_log`

Avoid:

- `trade_execution`
- `order_plan`
- `auto_position_action`

## Operator Plan Template

`operator_plan_template.json` is designed for human backfill after reading the report. It must preserve the source run id and a manual decision lifecycle:

```json
{
  "trade_date": "2026-06-20",
  "created_from_run_id": "daily_review_v1_20260620_2200",
  "decision_status": "pending",
  "operator_id": "",
  "overall_position_bias": "",
  "must_check_before_open": [],
  "forbidden_actions": [],
  "manual_decisions": []
}
```

`decision_status` is one of:

- `pending`: generated but not reviewed by the operator.
- `confirmed`: operator reviewed and confirmed the plan.
- `skipped`: operator intentionally skipped the plan for the session.
- `invalidated`: later data or operator judgment invalidated the generated plan.

The template is a manual review artifact only. It must not imply an order, broker action, cash movement, or true position mutation.

## CLI

Add a CLI equivalent to:

```bash
python -m stock_research.reports.daily_review_report_workflow \
  --trade-date 2026-06-20 \
  --output-root reports/daily_review \
  --format markdown,json \
  --record-run
```

The main `stock-research` CLI can expose an alias in the same phase if it follows existing CLI patterns:

```bash
stock-research run-daily-review-v1 \
  --trade-date 2026-06-20 \
  --output-root reports/daily_review \
  --record-run \
  --apply-report-run-schema
```

`--trade-date auto` may be added if it can reuse existing trading calendar logic without broad new scheduling behavior. Otherwise it is deferred.

## Report Run Registration

When `--record-run` is provided, generated artifact paths are recorded in `report.report_run`:

- `report_type`: `daily_review_v1`
- `trade_date`: requested trade date
- `status`: `success`, `partial`, or `failed`
- `report_paths`: paths for Markdown, JSON, manifest, operator plan template, and evidence files
- `metadata`: schema version, data readiness summary, warnings, and source counts

`--apply-report-run-schema` should initialize `report.report_run` using the existing report run store.

## Markdown Output

The Markdown report follows this order:

1. Executive Summary
2. Data readiness
3. Market review
4. LHB short-line review
5. Mid Trend review
6. Technical Bottleneck review
7. Holding review
8. Operator plan
9. Next-day checklist
10. Warnings and missing data

The Executive Summary must lead with:

- data status
- market status
- LHB conclusion
- Mid Trend conclusion
- Technical Bottleneck conclusion
- `P0` must-review items
- forbidden actions

It should answer:

- Is the data complete enough for review?
- Is the market suitable for trading?
- Can LHB be considered tomorrow?
- Are Mid Trend holdings healthy?
- Did any bottleneck opportunity upgrade or fail?
- Which assets require manual review?
- Which actions are forbidden tomorrow?

## Error Handling

The orchestrator should use best-effort module collection:

- A failed optional module creates a readiness warning and an empty module payload.
- The run status becomes `partial` when any enabled module has missing or failed sources.
- The Markdown explicitly says which sections are lower-confidence.
- The process exits non-zero only when it cannot write the package or the requested trade date is invalid.

## Testing

First phase tests should cover:

- Building a complete `daily_review.json` from in-memory source payloads.
- Generating Markdown sections in the required order.
- Generating `partial` status when one optional source is missing.
- Ensuring operator plan text and JSON remain manual-review-only.
- Preserving multiple `holding_reviews` rows for the same `asset_id` under different `strategy_id` values.
- Rejecting or normalizing actions outside the controlled enum.
- Carrying `review_priority` values through `strategy_items` and surfacing `P0` items in the Markdown Executive Summary.
- Writing `operator_plan_template.json` with `created_from_run_id` and `decision_status`.
- Writing the package to the expected directory.
- Recording `report.report_run` through a mocked store call.
- CLI argument parsing for module entrypoint and main CLI alias if added.
- Golden fixture coverage using fixed source payloads and expected outputs:
  - `tests/fixtures/daily_review_v1/source_payloads/*.json`
  - `tests/fixtures/daily_review_v1/expected_daily_review.json`
  - `tests/fixtures/daily_review_v1/expected_daily_review.md`

Golden fixture tests should fail on unintended structure drift in `daily_review.json` or section/content drift in `daily_review.md`. Intentional contract changes must update both the spec and golden expected files in the same change.

## Future Phases

Phase 2 persists `daily_review.json` into `review.daily_review_run`, `review.daily_strategy_item`, and `review.operator_review_decision`.

Phase 3 adds a dashboard Daily Review page over the stable read model.

Phase 4 adds `weekly_review_v1` with market stage change, strategy effectiveness, LHB pattern effectiveness, Mid Trend TopN stability, Mid Trend industry exposure, protection events, bottleneck pool migration, next week plan, and rule adjustment candidates.

## Non-Goals

Daily Review v1 does not:

- Place orders.
- Mutate true account positions.
- Manage cash or broker state.
- Build dashboard pages.
- Build full weekly review.
- Add automatic scheduling.
- Perform real account performance attribution.
- Depend on complex new fundamental research for the bottleneck module.
