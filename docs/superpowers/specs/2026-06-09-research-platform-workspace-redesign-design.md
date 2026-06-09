# Research Platform Workspace Redesign Design

## 1. Goal

Redesign the stock research platform dashboard from a TopN-first debug surface
into a quant research workbench with clear product entry points:

- Home / Research Cockpit
- Data Explorer
- Factor Lab
- Backtest Lab
- Strategy Validation
- Reports

The platform remains read-only for production trading. It may run local research
calculations and backtests, but it must not expose live order, broker, promotion,
or production write controls.

## 2. Current Problem

The current home page opens directly into a research review surface:

- Left sidebar: `TopN` and `Watchlist`.
- Center: selected asset chart.
- Right inspector: score, decisions, outcomes, shadow review, reports.

This is useful for internal debugging, but it is not a good platform home page.
A user cannot immediately tell:

- What strategies exist.
- Which factors each strategy uses.
- Why a stock appears in TopN.
- What data is available for a stock.
- Where to run a backtest.
- Where to build a custom factor scoring combination.

TopN is currently sourced from `factor.stock_score_daily` with
`score_version=manual_v1` and `top_n=30`. It is a candidate pool ranking, not a
buy signal. That distinction should be visible in the UI.

## 3. Product Lessons From Quant Platforms

Mature quant platforms separate research tasks into distinct workspaces:

- QuantConnect emphasizes project, backtest, optimization, and backtest result
  review flows.
- Portfolio123 separates screening, ranking systems, factor selection, and
  backtesting.
- BigQuant organizes visual research around data, feature extraction, modeling,
  prediction, and backtest modules.
- JoinQuant separates market data, factor research, strategy research,
  historical backtest, and simulation/live layers.

The redesign should borrow the information architecture, not the live trading
surface. This local platform should stay evidence-first and read-only.

## 4. New Information Architecture

### 4.1 Home / Research Cockpit

The home page should summarize platform state and route users to the right task.

Home should show:

- Latest market data date.
- Latest factor score date.
- Stock coverage count.
- Factor coverage count.
- Available score versions.
- Available built-in strategies.
- Latest strategy validation runs.
- Quick entry buttons for Data Explorer, Factor Lab, Backtest Lab, Strategy
  Validation, and Reports.

Home should not show a raw TopN list as the primary surface. TopN may appear as a
small recent-candidate preview with a clear label: "candidate pool, not buy
signal".

### 4.2 Data Explorer

Data Explorer is the place to inspect one asset.

Required controls:

- Asset search / asset id input.
- Trade date.
- Date range.
- Adjust type.

Accepted asset id formats:

- `CN:SZ:000001`
- `000001.SZ`
- `sz.000001`

Required panels:

- Asset master metadata.
- Daily bars chart and table.
- Score and score components for selected score version.
- Factor values by factor group.
- Watchlist signals.
- Decisions and outcomes.
- LHB/events/reports if available.
- Data coverage summary.

Data Explorer should answer: "What do we know about this stock?"

### 4.3 Factor Lab

Factor Lab lets a user build a factor scoring recipe without writing code.

Required controls:

- Trade date or date range.
- Universe selector.
- Factor search and group filters.
- Factor checkboxes.
- Direction selector per factor: higher is better / lower is better.
- Weight input per factor.
- TopN count.
- Optional portfolio basket input.

Required outputs:

- Factor library table from `factor_registry.py` and database coverage.
- Score preview table: asset id, rank, total score, selected factor scores.
- Score component breakdown for selected asset.
- TopN candidate pool.
- Optional selected-portfolio scoring.

First version behavior:

- Calculate preview in memory.
- Do not write to `factor.stock_score_daily`.
- Do not create a new persisted score version.

Future reviewed behavior:

- Save named factor recipes after review.
- Run factor gate evaluation before allowing a recipe to become a score version.

### 4.4 Backtest Lab

Backtest Lab lets a user run built-in strategy backtests over a selected window.

Required controls:

- Strategy selector.
- Start date.
- End date.
- Score version.
- TopN.
- Rebalance frequency: daily / weekly.
- Transaction cost bps.
- Max positions.
- Adjust type.

First supported runnable strategy:

- `Manual V1 TopN Rotation`, backed by existing vectorized TopN backtest code.

Strategy statuses:

- `runnable`: can run parameterized local backtest now.
- `replay_only`: has validation/replay artifacts but no unified runner yet.
- `planned`: visible in strategy catalog but not runnable.

Initial statuses:

- Manual V1 TopN Rotation: runnable.
- LHB Shortline: replay_only.
- Mid Trend Shortline: replay_only.
- Tech Bottleneck Discovery: replay_only.
- Position Control Overlay: replay_only.

Required outputs:

- Summary metrics.
- Equity curve.
- Drawdown curve.
- Positions table.
- Trades table.
- Config and evidence block.

Backtest Lab should answer: "How did this built-in strategy perform over this
time range under these parameters?"

### 4.5 Strategy Validation

Strategy Validation remains the evidence review workspace already implemented.

It should continue to show:

- Run selector.
- Asset replay chart.
- Signals.
- Trades/replay outcomes.
- Cohort metrics.
- Portfolio risk.
- Evidence artifacts.

It should be positioned as "inspect existing strategy evidence", not "run a new
backtest".

### 4.6 Reports

Reports should aggregate local generated artifacts:

- Daily TopN reports.
- Factor evaluation reports.
- Backtest reports.
- Strategy validation artifacts.
- Run cards.

Reports should support filtering by date, report type, and strategy.

## 5. Strategy Catalog

The platform should expose a small strategy catalog on Home and Backtest Lab.

Each strategy card should show:

- Strategy name.
- Status: runnable / replay_only / planned.
- Short description.
- Factor or signal inputs.
- Default parameters.
- Latest available evidence.
- Primary action.

Initial catalog:

### Manual V1 TopN Rotation

Status: runnable.

Inputs:

- `factor.stock_score_daily`
- `score_version=manual_v1`
- market daily bars

Factor groups:

- momentum
- trend
- volume_price
- risk
- sector

Default parameters:

- topN: 20 or 30
- rebalance: weekly
- max positions: 20
- transaction cost: configurable

### LHB Shortline

Status: replay_only.

Inputs:

- LHB events
- support/follow signals
- shortline replay artifacts
- daily bars

### Mid Trend Shortline

Status: replay_only.

Inputs:

- trend protection
- drawdown diagnostics
- mid-trend portfolio artifacts
- market state/risk overlays

### Tech Bottleneck Discovery

Status: replay_only.

Inputs:

- bottleneck rank
- technical condition buckets
- candidate discovery artifacts
- portfolio-control experiments

### Position Control Overlay

Status: replay_only.

Inputs:

- exposure caps
- risk budgets
- market/drawdown state
- position snapshots

## 6. Factor Library

Factor Library should be a first-class platform concept.

Sources:

- `src/stock_research/factor_registry.py`
- `factor.factor_daily`
- `factor.stock_score_daily.score_components`
- `factor.factor_approval`

Factor groups:

- momentum
- trend
- volume_price
- risk
- sector
- quality
- value
- alpha101
- gtja191
- qlib

For each factor show:

- factor name
- group
- direction
- description
- source
- status
- availability start date
- latest available date
- coverage count
- whether it is used in `manual_v1`
- manual_v1 weight if used

Manual V1 should be displayed as a built-in factor recipe, not a hidden score.

## 7. API Shape

Add read-only dashboard APIs:

- `GET /api/platform/summary`
- `GET /api/strategies/catalog`
- `GET /api/factors/library`
- `GET /api/factors/score-preview`
- `GET /api/assets/{asset_id}/profile`
- `GET /api/backtests/strategies`
- `POST /api/backtests/run`

`POST /api/backtests/run` may run a local read-only calculation and return a
result. It must not write strategy, factor, production, broker, or scheduler
state.

Factor preview should also be read-only. It should not create new score versions
until a later reviewed workflow exists.

## 8. UX Principles

- The first screen routes the user to tasks instead of dumping internal TopN
  state.
- Every score must expose its factor recipe and component breakdown.
- Every strategy must expose its factor/signal inputs before showing results.
- Candidate pools must be labeled as candidates, not trade instructions.
- Read-only status must be visible on backtest and strategy validation surfaces.
- Data availability and date coverage should be shown before users interpret
  results.
- Use dense, professional research UI. Avoid marketing hero layouts and
  decorative visuals.

## 9. First Implementation Slice

The first implementation should not attempt to build the full platform at once.

Recommended slice:

1. Replace the current default home with Research Cockpit.
2. Move the existing research page behind `Data Explorer`.
3. Add Factor Library read model and UI table.
4. Add strategy catalog cards.
5. Add Backtest Lab shell with Manual V1 TopN Rotation runnable.
6. Keep Strategy Validation as the existing implemented workspace.

This slice gives the platform a coherent structure while reusing existing data,
factor, score, backtest, and strategy validation code.

## 10. Success Criteria

The redesign is successful when:

- A new user can tell what the platform does from Home.
- A user can inspect one stock without going through TopN.
- A user can see which factors compose `manual_v1`.
- A user can build a temporary factor scoring preview from selected factors.
- A user can run a built-in TopN backtest over a custom date range.
- A user can inspect LHB, mid-trend, tech bottleneck, and position-control
  evidence in Strategy Validation.
- Default Playwright tests cover Home, Data Explorer, Factor Lab, Backtest Lab,
  and Strategy Validation navigation.

## 11. Non-Goals

- No custom strategy code editor.
- No live trading.
- No broker integration.
- No production watchlist promotion.
- No automatic factor approval.
- No persistent user accounts.
- No cloud deployment redesign.
