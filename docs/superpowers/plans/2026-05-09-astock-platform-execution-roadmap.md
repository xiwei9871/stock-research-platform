# AStock Platform Execution Roadmap

> **For agentic workers:** This is a roadmap, not a direct implementation plan. Use it to choose the next focused plan. For implementation work, use the detailed plan files listed below with superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Convert the full A-share research platform framework into ordered, independently verifiable delivery plans.

**Architecture:** Keep the platform self-built. External projects are references for formulas, evaluation, vectorized backtesting, lifecycle boundaries, and reports, but they must not become the platform framework.

**Tech Stack:** Python, pandas, numpy, pytest, PostgreSQL, existing `stock_research` CLI and research schemas.

---

## Current Completed Baseline

- Research schemas and PIT data boundaries exist.
- Daily factor pipeline writes `factor.factor_daily`.
- Scoring pipeline writes `factor.stock_score_daily`.
- TopN report generation exists.
- Alphalens-style base evaluation helpers exist.
- Adapter boundaries exist for `alpha101`, `gtja191`, and `qlib_alpha`.
- The external wheel reference and usage boundaries are documented in `docs/astock-research-platform-v1.md`.

## Execution Tracks

### Track 1: External Factor Library Phase 1

Detailed plan:

- `docs/superpowers/plans/2026-05-09-external-factor-library-phase1.md`

Deliver:

- reusable factor operators,
- 3 Alpha101-style representative factors,
- 3 GTJA191-style representative factors,
- 4 Qlib-style representative factors,
- long-row integration with correct `source` labels,
- no scoring promotion yet.

### Track 2: Factor Evaluation Gate

Write next plan after Track 1.

Deliver:

- `forward_return_10d`, `forward_return_20d`, `forward_return_60d`,
- ICIR,
- by-year performance,
- market-state performance,
- industry and size exposure,
- factor promotion metadata,
- CLI command to evaluate and mark factors as approved for scoring.

### Track 3: Vectorized TopN Backtest Engine

Write after Track 2 starts producing approved factor sets.

Deliver:

- `src/stock_research/backtest/vectorized_engine.py`,
- daily and weekly TopN rebalance,
- transaction cost,
- turnover,
- equal weight holding,
- max holdings,
- equity curve and trade detail output.

### Track 4: Strategy Lifecycle Layer

Write after vectorized engine can run TopN candidates.

Deliver:

- `prepare_data`,
- `before_market`,
- `generate_signals`,
- `rebalance`,
- `after_market`,
- `generate_report`,
- strategy modules that call the backtest engine without changing V3 thresholds.

### Track 5: Performance And Tear Sheet Layer

Write after Track 3 has stable backtest output.

Deliver:

- cumulative return,
- annual return,
- annual volatility,
- max drawdown,
- Sharpe,
- Sortino,
- Calmar,
- win rate,
- average holding days,
- annual turnover,
- markdown and spreadsheet tear sheets.

## Global Guardrails

- Do not import Qlib as the platform framework.
- Do not import RQAlpha as the platform framework.
- Do not add broker or auto-trading integrations.
- Do not add complex machine-learning models in these tracks.
- Do not implement all Alpha101 or all GTJA191 factors.
- Do not put any factor into scoring before evaluation.
- Do not use future data.
- Do not use financial statement data before `announcement_date`.

## Completion Definition

This roadmap is complete when each track has its own detailed implementation plan, all five tracks are implemented, full tests pass, and one recent trade date can run from factor build through TopN backtest and performance report.
