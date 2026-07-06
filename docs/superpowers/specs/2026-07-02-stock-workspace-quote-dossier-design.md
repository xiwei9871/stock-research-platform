# Stock Workspace Quote Dossier Design

## Goal

Upgrade the canonical `http://127.0.0.1:5174/` Stock Workspace into a stock-page-style dossier inspired by mainstream A-share quote pages, while preserving its existing review workflow.

## Current Context

`dashboard/src/components/StockWorkspace.tsx` already shows strategy score, evidence digest, chart, decisions, news, and research reports. The first screen is still review-first, so it does not answer the basic stock-page questions quickly: open, high, low, turnover, amount, company status, and whether valuation fields are actually available.

`src/stock_research/dashboard/asset_profile.py` currently returns `asset`, `bars`, `score`, `signals`, `decisions`, `outcomes`, `factor_values`, and `coverage`. `market_daily_bar` contains reliable OHLCV fields plus `preclose`, `turnover_rate`, and `pct_chg`, but `BarPoint` only exposes a subset. `core.asset_master` contains richer company identity fields. Market cap, float market cap, PE, PB, and strict real-time volume ratio are not yet guaranteed in the public asset profile contract.

## Design

Add two explicit sections to the stock profile response:

- `quote_snapshot`: point-in-time daily quote data for the loaded `trade_date` or latest available bar up to `end_date`.
- `company_profile`: normalized company identity data from `core.asset_master`, with a fallback to the existing public asset detail.

The frontend will promote a new `行情快照` panel to the top of Stock Workspace. It will show latest price, daily change, open, high, low, previous close, volume, amount, turnover rate, and a clearly labeled `量能/20日均额` proxy. It will also show a `规模估值` area with total market cap, float market cap, PE, and PB as unavailable when no trustworthy data source is present. The unavailable state is a feature, not a gap: it prevents fake quote-page values.

The existing strategy review summary remains, but it should become a separate `策略复盘摘要` panel below the quote snapshot. News and research reports continue to use existing APIs, but their visible lists remain part of the dossier so the page feels like a stock workspace rather than a raw audit view.

## Data Contract

`quote_snapshot` fields:

- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `preclose`
- `volume`
- `amount`
- `turnover_rate`
- `pct_chg`
- `amount_ratio_20d`
- `data_status`
- `missing_fields`

`company_profile` fields:

- `asset_id`
- `ts_code`
- `symbol`
- `name`
- `exchange`
- `board`
- `list_date`
- `is_active`
- `is_beijing`
- `is_star`
- `is_chinext`
- `region`
- `source`

`valuation_snapshot` fields:

- `total_market_cap`
- `float_market_cap`
- `pe_ttm`
- `pb`
- `volume_ratio`
- `data_status`
- `missing_fields`

For this MVP, valuation fields can be null with `data_status = "unavailable"` unless a verified internal source is explicitly wired.

## User Experience

Desktop 16:9:

- Top: stock title and controls.
- First content block: `行情快照` with dense quote metrics and `股票简况`.
- Second block: `策略复盘摘要`, preserving source strategy, rank, score, short-term performance, and news/research summary.
- Main content: decision rail + chart/evidence/news/reports as today.

Mobile portrait:

- Stack `行情快照`, `股票简况`, `策略复盘摘要`, chart, decision panel, then evidence/news/reports.

## Testing

Backend tests should verify that `build_asset_profile()` returns quote and company sections from database rows, including `turnover_rate`, `pct_chg`, `preclose`, and `amount_ratio_20d`.

Frontend tests should verify that Stock Workspace renders Chinese quote-page labels and that unavailable valuation fields render as `待接入`, not `-` or fabricated values.

## Out Of Scope

- No new external valuation data ingestion in this iteration.
- No change to strategy scoring, review queues, or market monitor logic.
- No fake market cap, PE, PB, or strict real-time volume ratio.
