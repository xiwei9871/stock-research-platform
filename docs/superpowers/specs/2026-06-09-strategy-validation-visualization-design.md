# Strategy Validation Visualization Design

## 1. Goal

Build a read-only strategy validation visualization workbench for the existing
stock research platform.

The workbench should help review and validate:

- LHB ultra-short strategy.
- Mid-trend shortline strategy.
- Tech bottleneck discovery.
- Position-control and multi-strategy exposure behavior.

The goal is not to create a trading terminal, online strategy IDE, broker
integration, or automatic order path. The dashboard should consume existing
research outputs, normalize them into stable read models, and make the evidence
visually inspectable.

## 2. Context

The repository already has a dashboard workbench:

- Python read-only API layer under `src/stock_research/dashboard/`.
- React + Vite frontend under `dashboard/`.
- Lightweight Charts adapter for daily/intraday asset bars.
- Existing panels for TopN, watchlist, scores, decisions, outcomes, shadow
  review, reports, and related dashboard tests.

The repository also already has strategy-specific research artifacts:

- LHB shortline event replay, follow/exit audits, phase 12-16 diagnostics, and
  daily watchlist outputs.
- Mid-trend drawdown, portfolio, Pareto, protection, and stability review
  outputs.
- Tech bottleneck rank/discovery outputs and portfolio-control experiments.
- Markdown, CSV, and JSON artifacts in existing `outputs/` and report paths.

This design adds a strategy validation layer on top of those artifacts. It does
not restart the dashboard or rewrite strategy logic.

## 3. External Platform Lessons

The design borrows selectively from mature quant platforms:

- QuantConnect-style backtest result objects: a run owns charts, trades,
  statistics, logs, orders, and exportable result files.
- TradingView and TradeStation-style chart-first strategy inspection: strategy
  marks on bars plus separate performance, trade, and risk tabs.
- Portfolio123-style separation of ranking, screening, factor buckets,
  simulations, and portfolio rules.
- QuantRocket-style artifact-oriented large and intraday backtests.
- BigQuant-style research pipeline provenance across data, features, model,
  prediction, and backtest modules.
- JoinQuant-style custom strategy observation metrics rendered into backtest
  charts.
- RiceQuant-style complete result tabs for overview, trades, holdings, account,
  logs, and performance.
- Eastmoney Quant / MyQuant-style run history, local workflow, performance
  review, and downloadable artifacts.

The platform should borrow the evidence model and review loop, not product
surfaces that imply live trading or order placement.

## 4. Design Options

### Option A: Directly Expand Existing Dashboard

Add strategy panels directly into the current dashboard `App.tsx`.

Pros:

- Fastest path to a demo.
- Reuses all existing frontend state and layout.

Cons:

- Increases coupling in an already broad single-page frontend.
- Makes LHB, mid-trend, bottleneck, and portfolio state hard to reason about.
- Does not create a stable strategy validation contract.

This option is not recommended except for a temporary prototype.

### Option B: Unified Validation Run + Strategy Workspace

Create a normalized strategy validation read model, then add a new Strategy
Validation workspace to the existing dashboard.

Pros:

- Preserves the existing dashboard architecture.
- Creates a stable contract for all current and future strategies.
- Allows the frontend to switch strategy, run, date, and asset without custom
  wiring for each artifact family.
- Keeps the first implementation read-only and evidence-first.

Cons:

- Requires a small normalization layer before the UI can be useful.
- Some older artifacts may need adapters or partial field mappings.

This is the recommended option.

### Option C: Separate Strategy Research App

Build a separate frontend and API for strategy research.

Pros:

- Maximum freedom for future heavy interactions, notebooks, and an online IDE.

Cons:

- Duplicates API, state, styling, testing, and deployment paths.
- Premature unless the product becomes a full strategy IDE.
- Risks drifting away from the existing read-only dashboard boundary.

This option is not recommended for the current phase.

## 5. Recommended Architecture

```text
Existing strategy artifacts
  LHB CSV/MD/JSON, mid-trend reports, bottleneck ranks, portfolio curves
        |
        v
Strategy validation normalization layer
  run, signals, trades/orders, positions/accounts, metrics, logs, artifacts
        |
        v
Read-only dashboard API
  /api/strategy-validation/*
        |
        v
React Strategy Validation workspace
  replay, cohort, portfolio risk, evidence tabs
        |
        v
Evidence links and exports
  original CSV/MD/JSON/report paths
```

The normalization layer should accept strategy-specific artifact inputs and
return JSON-safe DTOs. It should not change existing strategy outputs.

The API should remain read-only. It should not write factor, watchlist,
portfolio, scheduler, notification, broker, or strategy state.

The frontend should reuse existing chart and API patterns where practical:

- Keep `lightweight-charts` for K-line and volume views.
- Extend the chart adapter to render strategy markers.
- Keep UI dense and operator-focused rather than marketing-style.
- Keep the current dashboard workbench available.

## 6. Data Contract

Phase 1 should define a minimal normalized strategy validation contract.

### 6.1 StrategyValidationRun

Represents one strategy validation run.

Required fields:

- `run_id`
- `strategy_id`
- `strategy_name`
- `strategy_version`
- `run_type`
- `start_date`
- `end_date`
- `created_at`
- `benchmark`
- `universe`
- `data_window`
- `cost_config`
- `slippage_config`
- `risk_config`
- `position_config`
- `source_artifact_paths`
- `summary_metrics`
- `warnings`

Allowed `strategy_id` values for Phase 1:

- `lhb_shortline`
- `mid_trend`
- `tech_bottleneck`
- `position_control`

### 6.2 StrategySignal

Represents a strategy signal or observation.

Required fields:

- `run_id`
- `strategy_id`
- `asset_id`
- `stock_code`
- `stock_name`
- `signal_time`
- `trade_date`
- `signal_type`
- `signal_strength`
- `signal_bucket`
- `risk_bucket`
- `rule_id`
- `reason`
- `tags`
- `source_artifact_path`

Examples:

- LHB: support, high_elasticity, withdrawal, next_day_confirmation.
- Mid-trend: high_elasticity_watch, trend_protection, rebalance_candidate.
- Tech bottleneck: bottleneck_hit, bottleneck_rank_change, condition_bucket.
- Position control: exposure_cap, regime_budget, drawdown_pressure.

### 6.3 StrategyTrade

Represents simulated or replayed trade behavior. It is not a live order.

Required fields:

- `run_id`
- `strategy_id`
- `asset_id`
- `entry_time`
- `entry_price`
- `entry_reason`
- `exit_time`
- `exit_price`
- `exit_reason`
- `holding_days`
- `return_pct`
- `max_high_return_pct`
- `max_drawdown_pct`
- `outcome_status`
- `source_artifact_path`

The UI must label these as replay/backtest trades, not trading instructions.

### 6.4 StrategyPositionSnapshot

Represents portfolio or position-control state at a date/time.

Required fields:

- `run_id`
- `strategy_id`
- `trade_date`
- `asset_id`
- `position_weight`
- `target_weight`
- `cash_weight`
- `exposure`
- `position_cap`
- `risk_budget`
- `suppression_reason`
- `source_artifact_path`

### 6.5 StrategyMetricRow

Represents summary or cohort metrics.

Required fields:

- `run_id`
- `strategy_id`
- `metric_level`
- `group_key`
- `sample_count`
- `complete_count`
- `win_rate`
- `forward_return_mean`
- `forward_return_median`
- `max_high_return_mean`
- `max_drawdown_mean`
- `max_drawdown_worst`
- `turnover`
- `exposure_mean`
- `source_artifact_path`

`metric_level` examples:

- `strategy`
- `signal_bucket`
- `risk_bucket`
- `market_regime`
- `industry`
- `asset`
- `portfolio`

### 6.6 StrategyEvidenceArtifact

Represents original evidence linked from the UI.

Required fields:

- `run_id`
- `artifact_type`
- `title`
- `path`
- `format`
- `trade_date`
- `description`

Examples:

- CSV details.
- Markdown reports.
- JSON run summaries.
- Chart screenshots generated by tests.
- Logs.

## 7. API Design

Add a read-only API namespace:

```text
GET /api/strategy-validation/runs
GET /api/strategy-validation/runs/{run_id}
GET /api/strategy-validation/runs/{run_id}/signals
GET /api/strategy-validation/runs/{run_id}/trades
GET /api/strategy-validation/runs/{run_id}/positions
GET /api/strategy-validation/runs/{run_id}/metrics
GET /api/strategy-validation/runs/{run_id}/artifacts
GET /api/strategy-validation/runs/{run_id}/assets/{asset_id}/replay
```

Query parameters:

- `strategy_id`
- `start_date`
- `end_date`
- `asset_id`
- `signal_bucket`
- `risk_bucket`
- `metric_level`
- `limit`

The asset replay endpoint should combine:

- Daily or minute bars from existing dashboard bar loaders.
- Signals for the selected run and asset.
- Replay/backtest trades for the selected run and asset.
- Risk and follow-up markers.
- Linked evidence artifacts.

## 8. Frontend Design

Add a Strategy Validation workspace inside `dashboard/`.

### 8.1 Navigation

The workspace should provide:

- Strategy selector.
- Run selector.
- Date range display.
- Asset search or selected asset input.
- Tab control for Replay, Cohort, Portfolio Risk, and Evidence.

The existing TopN/watchlist dashboard remains available and should not be folded
into the new workspace in Phase 1.

### 8.2 Replay Tab

Purpose:

- Debug one stock through one strategy validation run.

Content:

- Daily K-line or minute K-line.
- Strategy markers for signals, entries, exits, risk events, follow-up events,
  and invalidation events.
- Side panel with signal reason, rule ID, risk bucket, outcome, and evidence
  path.
- Empty/loading/error states.

This is the first useful UI slice.

### 8.3 Cohort Tab

Purpose:

- Avoid anecdotal validation and compare groups.

Content:

- Metrics table grouped by strategy, signal bucket, risk bucket, market regime,
  industry, and asset.
- Summary cards for sample count, win rate, forward return, drawdown, and
  complete/insufficient sample counts.
- Minimal Phase 1 implementation may show only strategy-level and signal-bucket
  summaries.

### 8.4 Portfolio Risk Tab

Purpose:

- Validate position-control and multi-strategy behavior.

Content:

- Equity curve.
- Drawdown curve.
- Exposure timeline.
- Cash and turnover.
- Position cap violations or suppression reasons.
- Multi-strategy conflict notes.

Phase 1 may render a stable shell and minimal summary if position snapshots are
not yet available for every strategy.

### 8.5 Evidence Tab

Purpose:

- Keep each conclusion auditable.

Content:

- Run config.
- Data window.
- Benchmark.
- Cost, slippage, and risk settings.
- Artifact list with local paths.
- Warnings and logs.

## 9. Error Handling

The dashboard should handle:

- No runs available.
- Run exists but has no signals.
- Run exists but selected asset has no replay data.
- Bars missing for selected asset/date range.
- Artifact path missing or unreadable.
- Partial adapter support for older strategy outputs.
- Unsupported `strategy_id`.

User-facing messages should be precise and operational:

- `No strategy validation runs found.`
- `No replay rows for selected asset in this run.`
- `Bars are unavailable for selected range.`
- `Artifact path is listed but not readable.`
- `This run was loaded with partial adapter coverage.`

## 10. Testing

Backend tests:

- DTO serialization and JSON-safe output.
- Run listing from small fixture artifacts.
- Signals/trades/positions/metrics adapters from small LHB, mid-trend, and tech
  bottleneck fixture frames.
- Asset replay response shape.
- Empty and missing-artifact behavior.
- FastAPI route tests for each endpoint.

Frontend tests:

- API client type and URL tests.
- Marker conversion tests for chart data.
- Strategy Validation workspace loading state.
- Empty state for no runs.
- Replay tab with fixture bars and markers.
- Cohort tab minimal metrics table.
- Evidence tab artifact rendering.
- Playwright smoke at desktop and mobile widths with no horizontal overflow.

Verification commands should include:

```bash
.venv/bin/pytest tests/test_dashboard_*.py -q
cd dashboard && pnpm test
cd dashboard && pnpm build
cd dashboard && pnpm test:e2e
```

The implementation plan may narrow the backend pytest command to new focused
tests first, then run broader dashboard regressions before completion.

## 11. Non-Goals

Phase 1 does not include:

- Automatic trading.
- Broker integration.
- Live order tickets.
- Strategy code editor.
- Notebook execution.
- Replacing existing LHB, mid-trend, bottleneck, or portfolio-control logic.
- Writing normalized validation data back into production tables.
- Changing existing strategy artifact generation.

## 12. Phase 1 Scope

Phase 1 should deliver:

1. A normalized strategy validation schema in the dashboard/backend boundary.
2. Small artifact adapters for representative LHB, mid-trend, and tech
   bottleneck outputs.
3. Read-only Strategy Validation API endpoints.
4. Frontend Strategy Validation workspace.
5. Replay tab as the first useful screen.
6. Minimal Cohort, Portfolio Risk, and Evidence tabs.
7. Unit, route, frontend, build, and browser-smoke verification.

Phase 1 should not attempt to fully backfill every historical artifact. Partial
adapter coverage is acceptable if the UI marks it clearly.

## 13. Phase 1 Defaults And Open Questions

Default implementation decisions:

- Load validation runs from local artifact paths first. Database-backed run
  discovery can be added later if existing tables become stable sources.
- Add the smallest top-level workspace switch needed in `App.tsx`. Do not
  introduce a large dashboard routing refactor in Phase 1.
- Treat unsupported or partially mapped artifact families as partial adapter
  coverage, and show that status in the Evidence tab.
- Use fixture artifacts in tests before wiring large historical output
  directories.

These remaining questions should be answered during implementation planning:

- Which existing artifact path should be the first default run source for LHB?
- Which mid-trend artifact has the most stable asset-level signal/replay fields?
- Which tech bottleneck output should seed the first cohort metrics view?

These are data-source choices, not architecture choices. If no stable real
artifact is available for one strategy during Phase 1, the adapter should use a
small fixture and mark that strategy as fixture-backed in tests only.
