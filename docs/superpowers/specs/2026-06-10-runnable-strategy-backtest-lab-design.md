# Runnable Strategy Backtest Lab Design

## Goal

Make every strategy in the Backtest Lab catalog runnable and comparable in the dashboard:

- Manual V1 TopN Rotation
- LHB Shortline
- Mid Trend Shortline
- Tech Bottleneck Discovery
- Position Control Overlay

The first release is a research-grade comparison layer. It should let a user choose a strategy, date range, TopN, rebalance frequency, transaction cost, and max positions, then receive the same result shape for every strategy: summary metrics, equity curve, positions, and trades.

## Non-Goals

This does not turn the strategies into live trading systems. The first release will not support custom strategy code, order routing, intraday fills, human approval workflow, or production portfolio writes. Strategy Validation remains the place to inspect evidence and replay artifacts; Backtest Lab becomes the place to run standardized comparative portfolio simulations.

## Current Problem

`manual_v1_topn_rotation` is the only runnable strategy because the backend hard-codes it as the only accepted strategy id. Other strategies are listed as `replay_only`, so the frontend disables `Run Backtest`.

This is correct for the current implementation but no longer matches the desired product direction. We need a proper strategy adapter layer instead of changing status flags directly.

## Design

### Strategy Score Adapter Layer

Add a backend adapter layer that converts each strategy into a normalized daily score frame:

```text
trade_date
asset_id
rank
score_total
score_components
strategy_id
eligibility
eligibility_reason
exposure_scale
```

The existing vectorized TopN engine already accepts a score frame with `trade_date`, `asset_id`, `rank`, and `score_total`. The adapter layer will generate those required fields for every strategy and keep additional metadata for later display.

### Strategy Definitions

#### Manual V1 TopN Rotation

Use the current implementation unchanged:

- Source: `factor.stock_score_daily`
- Filter: selected `score_version`, default `manual_v1`
- Ranking: existing `rank`
- Score: existing `score_total`
- Exposure: 1.0

#### LHB Shortline

Create a daily candidate score from LHB event features and shortline-friendly technical context:

- Primary sources:
  - `factor.lhb_event_features_daily`
  - `factor.stock_technical_features_daily`
  - `market_daily_bar`
  - optional `factor.stock_score_daily` as a fallback quality/tie-break score
- Eligibility:
  - include rows with `on_lhb = true` or recent LHB signal within the configured lookback
  - exclude rows with explicit one-day pump risk above the default risk threshold
- Score:
  - positive weight for `lhb_net_buy_ratio`
  - positive weight for `lhb_net_buy_amount`
  - positive weight for reversal/support patterns
  - negative weight for pump-risk and weak liquidity
- Default behavior:
  - daily or weekly TopN rotation, equal-weighted positions
  - same execution constraints as the existing TopN engine

If the LHB feature table has no data for a selected range, return a clear backend error: `no LHB strategy scores found for selected range`.

#### Mid Trend Shortline

Create a daily candidate score from trend and risk factors:

- Primary sources:
  - `factor.stock_score_daily.score_components`
  - `factor.factor_daily`
  - `factor.stock_technical_features_daily`
  - optional watchlist funnel outputs when available
- Eligibility:
  - prefer assets with positive trend score and no risk exclusion
  - exclude clearly weak trend or high drawdown candidates when those factors exist
- Score:
  - positive weight for trend strength, trend fit, moving-average slope, and medium-horizon momentum
  - negative weight for volatility, drawdown, and overheat risk
  - fallback to `manual_v1` score when a component is missing

The first release should be deterministic and documented rather than overly optimized.

#### Tech Bottleneck Discovery

Create a daily candidate score from bottleneck-style technical strength:

- Primary sources:
  - `factor.stock_score_daily.score_components`
  - `factor.factor_daily`
  - `factor.stock_technical_features_daily`
  - existing bottleneck experiment logic where safely reusable
- Eligibility:
  - include assets with sufficient technical feature coverage
  - exclude rows with missing price data
- Score:
  - positive weight for trend, volume-price confirmation, price position, and bottleneck/continuation signals
  - negative weight for sharp drawdown and overheat risk

This adapter should avoid reading CSV artifacts in the dashboard path. It should query database-backed factor and feature tables.

#### Position Control Overlay

Expose Position Control as a runnable comparative strategy by applying risk scaling to a base score stream:

- Base source: default `manual_v1` TopN scores in release one
- Overlay sources:
  - `factor.stock_technical_features_daily`
  - `market_daily_bar`
  - available risk factors from `factor.factor_daily` or `score_components`
- Behavior:
  - keep the same selected assets as the base TopN strategy
  - reduce effective exposure when market or candidate risk is high
  - enforce max positions and transaction cost consistently with other strategies

Because the existing vectorized engine currently equal-weights selected names, release one will model Position Control by filtering/reranking risky names and optionally reducing `max_positions`. A later release can add per-date exposure scaling to the engine.

### Backend API

Keep the existing endpoint:

```text
POST /api/backtests/run
```

Remove the hard-coded `RUNNABLE_STRATEGY_ID` check and route by `strategy_id`:

```text
strategy_id -> load_strategy_scores(...) -> run_vectorized_topn_backtest(...)
```

Add a small registry:

```python
STRATEGY_BACKTEST_REGISTRY = {
    "manual_v1_topn_rotation": ManualV1TopNAdapter(),
    "lhb_shortline": LHBShortlineAdapter(),
    "mid_trend": MidTrendAdapter(),
    "tech_bottleneck": TechBottleneckAdapter(),
    "position_control": PositionControlAdapter(),
}
```

Every adapter must return the same score frame contract and must raise an actionable error when the selected date range has no usable signals.

### Strategy Catalog

Mark all five catalog items as `runnable` after their adapters and tests exist. Add default parameters for each strategy so the UI can keep a consistent control surface:

- `top_n: 20`
- `rebalance_frequency: weekly`
- `max_positions: 20`
- `transaction_cost_bps: 10`
- `adjust_type: hfq`

The descriptions should clearly say these are research-grade standardized backtests.

### Frontend

Backtest Lab should no longer treat LHB, Mid Trend, Tech Bottleneck, and Position Control as replay-only after the backend supports them.

Add a comparison workflow:

- Keep single-strategy run behavior.
- Add a `Run Comparison` action that runs the selected date range and parameters across all runnable strategies.
- Render a comparison table with strategy name, total return, max drawdown, turnover, final equity, and holdings count.
- Keep detailed result panels for the most recently selected or clicked strategy.

The first implementation can call the existing run endpoint once per strategy from the frontend. A later backend endpoint can batch the comparison if needed.

### Error Handling

Errors should distinguish:

- invalid parameters
- unsupported strategy id
- no signal data in selected date range
- no price data in selected date range
- backend execution error

The UI should show the strategy name and reason, especially in comparison mode where one strategy may fail while others succeed.

### Testing

Backend tests:

- each adapter builds a valid score frame from small in-memory frames or mocked database rows
- `run_backtest` accepts every catalog strategy id
- unknown strategy id is rejected
- empty strategy scores return a clear error
- all returned results serialize to JSON-safe values

Frontend tests:

- every catalog strategy enables `Run Backtest`
- running LHB calls the backend with `strategy_id: lhb_shortline`
- `Run Comparison` calls every runnable catalog strategy with the same date range and risk parameters
- comparison mode renders one row per strategy
- failed comparison rows show an error without hiding successful rows

Per-strategy unit tests are required before a strategy is marked runnable:

- `ManualV1TopNAdapter` preserves existing manual score loading behavior.
- `LHBShortlineAdapter` ranks positive LHB support/follow candidates above weak or risky LHB rows.
- `MidTrendAdapter` ranks stronger trend candidates above weak trend or high-risk rows.
- `TechBottleneckAdapter` ranks bottleneck/continuation candidates above generic manual-score rows.
- `PositionControlAdapter` reduces or reranks risky base candidates instead of simply copying manual TopN output.

Playwright tests:

- open Backtest Lab
- run Manual V1 for `2026-01-01` to `2026-06-08`, TopN 20
- run LHB Shortline for the same range
- click `Run Comparison` for all runnable strategies
- verify the comparison table and at least one detailed result panel render

### Implementation Phasing

Phase 1 should implement the backend strategy adapter registry, make all strategies individually runnable, and update the catalog statuses. This is the core product fix.

Phase 2 should add comparison mode to the frontend.

Phase 3 should run Playwright against the live local API and refine UX copy for strategy assumptions and empty-data cases.

## Acceptance Criteria

- All five strategies appear as runnable in Backtest Lab.
- `Run Backtest` is enabled for every strategy when parameters are valid.
- `Run Comparison` is available and runs every runnable strategy with identical date range, TopN, rebalance, cost, max position, and adjust-type parameters.
- The backend rejects no catalog strategy as unsupported.
- Each strategy returns summary, equity curve, positions, and trades in the existing result shape.
- Each strategy adapter has its own unit tests covering score construction, ranking, and empty-data behavior.
- The user can compare all strategies over `2026-01-01` through `2026-06-08` with TopN 20.
- Tests cover backend routing, adapter output, frontend enablement, and comparison rendering.
