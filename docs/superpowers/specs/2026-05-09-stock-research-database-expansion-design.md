# Stock Research Database Expansion Design

Date: 2026-05-09

## Goal

Upgrade the current A-share research database from a daily price database into a
point-in-time stock research database that can support V3 strategy research:
trend and momentum, sector confirmation, market state, fundamental quality,
valuation, and risk filtering.

The first phase builds database structure and service interfaces. It does not
replace the current `public.market_daily_bar` pipeline and does not implement a
full data crawler.

## Current State

The project currently has:

- Upstream PostgreSQL source databases:
  - `stock_hfq`
  - `stock_qfq`
- Downstream research database:
  - `stock_research`
- Existing normalized daily bar table:
  - `public.market_daily_bar`
- Existing asset table:
  - `public.asset_master`

The latest A-share daily bars are complete for the current沪深 universe. The
database lacks financial statements, point-in-time fundamentals, industry and
sector history, index and industry bars, stock status history, and corporate
action data.

## Design Principles

1. Do not break existing daily bar and backtest workflows.
2. Store raw source payloads separately from standardized research tables.
3. Keep source-specific ingestion replaceable.
4. Store history for every field that can change over time.
5. Financial statement data must include both `report_period` and
   `announcement_date`.
6. Backtests and factor generation must only use financial data where
   `announcement_date <= trade_date`.
7. Industry membership must be queried by historical effective date, not current
   membership.
8. Derived valuation and factor results must be auditable and recalculable.

## PostgreSQL Schemas

Create these schemas in `stock_research`:

```text
raw_akshare
raw_baostock
core
finance
market
factor
backtest
```

The existing `public` tables remain in place during phase 1.

## Phase 1 Tables

### `core.asset_master`

Canonical stock identity table.

Columns:

```text
asset_id text primary key
ts_code text
baostock_code text
akshare_code text
symbol text not null
name text not null
exchange text not null
board text
list_date date
delist_date date
is_active boolean not null
is_beijing boolean not null
is_star boolean not null
is_chinext boolean not null
region text
source text not null
updated_at timestamptz not null
```

Dynamic fields such as ST status, suspension status, industry, market cap, PE,
and PB do not belong here except as optional current display fields in future
views.

### `core.asset_status_daily`

Daily tradability and risk status.

Columns:

```text
trade_date date not null
asset_id text not null
is_trade boolean not null
is_st boolean not null
is_suspended boolean not null
is_limit_up boolean
is_limit_down boolean
limit_up_price numeric
limit_down_price numeric
source text not null
updated_at timestamptz not null
primary key (trade_date, asset_id)
```

Used for ST filtering, suspension filtering, limit-up and limit-down handling,
and realistic execution checks.

### `core.industry_membership`

Historical industry and sector membership.

Columns:

```text
asset_id text not null
industry_system text not null
industry_code text not null
industry_name text not null
level integer not null
start_date date not null
end_date date
source text not null
updated_at timestamptz not null
primary key (asset_id, industry_system, industry_code, level, start_date)
```

Query rule:

```sql
start_date <= trade_date
AND (end_date IS NULL OR trade_date < end_date)
```

### `market.index_daily_bar`

Daily index bars for market state and benchmark comparison.

Columns:

```text
index_id text not null
trade_date date not null
open numeric
high numeric
low numeric
close numeric
preclose numeric
volume numeric
amount numeric
source text not null
updated_at timestamptz not null
primary key (index_id, trade_date)
```

Initial targets include broad and style indexes such as沪深300, 中证500,
中证1000, 创业板指, 科创50, 上证指数, 深证成指.

### `market.industry_daily_bar`

Daily industry or sector bars for V3 sector trend confirmation.

Columns:

```text
industry_system text not null
industry_code text not null
industry_name text not null
trade_date date not null
open numeric
high numeric
low numeric
close numeric
preclose numeric
volume numeric
amount numeric
source text not null
updated_at timestamptz not null
primary key (industry_system, industry_code, trade_date)
```

### `finance.income_statement`

Standardized income statement.

Columns:

```text
asset_id text not null
report_period date not null
report_type text not null
announcement_date date not null
revenue numeric
operating_profit numeric
total_profit numeric
net_profit numeric
np_parent numeric
np_parent_deducted numeric
eps_basic numeric
source text not null
updated_at timestamptz not null
primary key (asset_id, report_period, report_type, announcement_date, source)
```

### `finance.balance_sheet`

Standardized balance sheet.

Columns:

```text
asset_id text not null
report_period date not null
report_type text not null
announcement_date date not null
total_assets numeric
total_liabilities numeric
total_equity numeric
monetary_funds numeric
accounts_receivable numeric
inventory numeric
goodwill numeric
source text not null
updated_at timestamptz not null
primary key (asset_id, report_period, report_type, announcement_date, source)
```

### `finance.cash_flow`

Standardized cash flow statement.

Columns:

```text
asset_id text not null
report_period date not null
report_type text not null
announcement_date date not null
net_operate_cash_flow numeric
net_invest_cash_flow numeric
net_finance_cash_flow numeric
capex numeric
free_cash_flow numeric
source text not null
updated_at timestamptz not null
primary key (asset_id, report_period, report_type, announcement_date, source)
```

### `finance.indicator_quarter`

Quarterly financial indicators. Some fields may be loaded from data providers;
others may be calculated from standardized statements.

Columns:

```text
asset_id text not null
report_period date not null
announcement_date date not null
roe numeric
roa numeric
gross_margin numeric
net_margin numeric
debt_ratio numeric
revenue_yoy numeric
np_yoy numeric
deduct_np_yoy numeric
ocf_to_np numeric
asset_turnover numeric
current_ratio numeric
quick_ratio numeric
source text not null
calc_version text not null
updated_at timestamptz not null
primary key (asset_id, report_period, announcement_date, source, calc_version)
```

### `finance.share_capital_event`

Historical share capital events.

Columns:

```text
asset_id text not null
event_date date not null
announcement_date date
total_share numeric
float_share numeric
free_float_share numeric
reason text
source text not null
updated_at timestamptz not null
primary key (asset_id, event_date, source)
```

This supports recalculating market cap and valuation factors from price, share
capital, and financial statement data.

### `raw_akshare.finance_payload`

Raw AKShare payload audit table.

Columns:

```text
id bigserial primary key
source_endpoint text not null
request_params jsonb not null
asset_id text
payload jsonb not null
fetched_at timestamptz not null
payload_hash text not null
```

### `raw_baostock.finance_payload`

Raw Baostock payload audit table.

Columns:

```text
id bigserial primary key
source_endpoint text not null
request_params jsonb not null
asset_id text
payload jsonb not null
fetched_at timestamptz not null
payload_hash text not null
```

## Service Interfaces

### `services.point_in_time_finance`

Responsibilities:

- Return the latest financial statement or indicator available on a given
  `trade_date`.
- Enforce `announcement_date <= trade_date`.
- Prefer standardized tables over raw payloads.
- Expose deterministic query behavior for factor generation and backtests.

Example API shape:

```python
get_latest_indicator(asset_id: str, trade_date: str) -> dict | None
get_latest_income_statement(asset_id: str, trade_date: str) -> dict | None
```

### `services.industry_membership_service`

Responsibilities:

- Return industry membership on a historical date.
- Support multiple industry systems.
- Avoid current-membership lookahead.

Example API shape:

```python
get_membership(asset_id: str, trade_date: str, industry_system: str) -> dict | None
```

### `services.asset_status_service`

Responsibilities:

- Return daily status for a stock.
- Provide filters for ST, suspension, limit-up, limit-down, and recent IPOs.
- Support realistic execution filters for backtests.

Example API shape:

```python
get_status(asset_id: str, trade_date: str) -> dict | None
is_tradable(asset_id: str, trade_date: str) -> bool
```

## Loader Interfaces

Phase 1 adds loader module boundaries but does not require complete crawlers:

```text
loaders/akshare_finance_loader.py
loaders/baostock_finance_loader.py
```

Loader responsibilities:

- Fetch source data.
- Store raw payload first.
- Normalize into standardized tables.
- Use idempotent upserts.
- Record source endpoint, parameters, and fetch time.

## Indexing Strategy

Core point-in-time queries need these indexes:

```sql
CREATE INDEX ON finance.indicator_quarter (asset_id, announcement_date DESC);
CREATE INDEX ON finance.income_statement (asset_id, announcement_date DESC);
CREATE INDEX ON finance.balance_sheet (asset_id, announcement_date DESC);
CREATE INDEX ON finance.cash_flow (asset_id, announcement_date DESC);
CREATE INDEX ON core.industry_membership (asset_id, industry_system, start_date, end_date);
CREATE INDEX ON core.asset_status_daily (trade_date, asset_id);
CREATE INDEX ON market.index_daily_bar (trade_date, index_id);
CREATE INDEX ON market.industry_daily_bar (trade_date, industry_system, industry_code);
```

## Non-Goals For Phase 1

- Do not migrate existing `public.market_daily_bar`.
- Do not rewrite existing backtests.
- Do not implement all AKShare or Baostock endpoints.
- Do not ingest announcement full text.
- Do not add northbound, margin trading, dragon-tiger list, shareholder count,
  or unlocking data.
- Do not build valuation factors until share capital and financial statements
  have usable coverage.

## Acceptance Criteria

1. Schema creation is repeatable.
2. Existing tests and current research pipeline still work.
3. New tables can be created without dropping or mutating current public tables.
4. Point-in-time finance service cannot return data with
   `announcement_date > trade_date`.
5. Industry membership queries use historical membership windows.
6. Loader interfaces persist raw payloads before normalized rows.
7. Documentation explains the future-function avoidance rule clearly.

