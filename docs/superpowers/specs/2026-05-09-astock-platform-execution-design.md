# AStock Platform Execution Design

## Purpose

Turn the broad A-share research platform framework in `docs/astock-research-platform-v1.md` into a sequence of executable, testable plans. The platform remains self-built: external projects provide reference ideas, formulas, evaluation standards, and architecture patterns, but they do not become the runtime framework.

## Scope

The full platform is too large for a single implementation plan. It is split into independent delivery tracks:

1. External factor library phase 1: implement a small, tested subset of Alpha101-style, GTJA191-style, and Qlib-style factors as pandas/numpy functions.
2. Factor evaluation gate: expand factor evaluation and require evaluation artifacts before a new source enters scoring.
3. Vectorized TopN backtest engine: implement a project-native vectorbt-style engine for TopN rotation.
4. Strategy lifecycle layer: organize V3 research flow with RQAlpha-style lifecycle boundaries without importing RQAlpha.
5. Performance and tear sheet layer: implement empyrical/pyfolio-style metrics and reports.

## Recommended First Plan

Start with external factor library phase 1. The daily factor pipeline now works end-to-end with custom factors, so the next highest-leverage step is adding a controlled set of external-reference factors behind existing adapter boundaries:

- `src/stock_research/factors/alpha101.py`
- `src/stock_research/factors/gtja191.py`
- `src/stock_research/factors/qlib_alpha.py`

This plan should not add heavy dependencies. It should add reusable factor operators, representative factors, tests that guard against future data leakage, and integration into factor row generation with source labels.

## Architecture

External-reference factors are computed as normal pandas `DataFrame` outputs keyed by existing market bar columns. Each module exposes one public calculator:

- `compute_alpha101_factors(bars: pd.DataFrame) -> pd.DataFrame`
- `compute_gtja191_factors(bars: pd.DataFrame) -> pd.DataFrame`
- `compute_qlib_alpha_factors(bars: pd.DataFrame) -> pd.DataFrame`

`factor_pipeline.py` converts their outputs into `factor.factor_daily` rows using the same long-row shape as existing custom factors. The pipeline records `source` as `alpha101`, `gtja191`, or `qlib`, while keeping `source_data_version` as the source market data version.

## Boundaries

- Do not import Qlib, RQAlpha, vectorbt, Alphalens, pyfolio, or TA-Lib as runtime dependencies in phase 1.
- Do not implement all Alpha101 or all GTJA191 factors.
- Do not put external-reference factors into `manual_v1` scoring weights in this plan.
- Do not change V3 strategy rules.
- Do not generate buy or sell instructions.

## Success Criteria

- At least 3 Alpha101-style representative factors are implemented and tested.
- At least 3 GTJA191-style representative factors are implemented and tested.
- At least 4 Qlib-style representative factors are implemented and tested.
- Factor operators for cross-sectional rank, time-series rank, rolling correlation, rolling covariance, decay linear, delta, delay, and signed power are implemented and tested.
- The factor pipeline can build long factor rows with correct `source` labels for external-reference factors.
- Full unit tests pass.

## Follow-On Plans

After phase 1 lands, write and execute:

1. `factor-evaluation-gate`: multi-horizon forward returns, ICIR, by-year performance, industry/size exposure, factor promotion metadata.
2. `vectorized-topn-backtest`: TopN daily/weekly rebalance engine with costs, turnover, position caps, and report output.
3. `strategy-lifecycle-v3`: lifecycle functions for V3 research without changing strategy thresholds.
4. `performance-tear-sheet`: empyrical/pyfolio-style metrics and markdown/xlsx reports.

## Self-Review

No unresolved placeholders remain. The design intentionally limits implementation to the first independent delivery track and keeps later platform layers as separate plans.
