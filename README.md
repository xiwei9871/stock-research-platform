# Stock Research

This project builds the downstream research layer for the AI monitoring and stock-selection system.

Upstream source data is maintained by `/Users/xiwei/stock_tools/run_daily_backfill.sh`.

The research pipeline writes normalized assets, daily bars, quality checks, features, labels, selections, and reports into the `stock_research` PostgreSQL database.

Daily research command:

```bash
/Users/xiwei/stock_research/scripts/run_daily_research.sh
```

## Research Database Principles

The database is being extended from a daily price store into a point-in-time
stock research database. Existing `public` daily bar tables remain compatible;
new research data is added under schemas such as `core`, `finance`, `market`,
`factor`, `backtest`, `raw_akshare`, and `raw_baostock`.

Any value that changes over time must be stored with history, not only as a
current value. This includes ST status, suspension status, industry membership,
index or sector membership, share capital, and company actions.

Financial statements and financial indicators must always carry both:

- `report_period`: the accounting period, such as `2025-12-31`
- `announcement_date`: the date the data became available to the market

Backtests and factor generation must only use finance rows where
`announcement_date <= trade_date`. Using a `report_period` before its
announcement date is a future-function bug and invalidates research results.

## Top 20 Backtest

Run:

```bash
stock-research backtest-top20 \
  --start-date 2024-05-01 \
  --end-date 2026-05-07 \
  --holding-days 3,5,7,10 \
  --top-n 20
```

Outputs are written under `reports/` by default:

- Markdown research report
- equity curve CSV
- trade detail CSV
- summary CSV

Results are also persisted to PostgreSQL:

- `backtest_run`
- `backtest_trade`
- `backtest_summary`
- `backtest_equity_curve`

The report is for research validation only and does not provide trading,
position, or order instructions.

## Portfolio Account Backtest

Run:

```bash
stock-research portfolio-backtest \
  --start-date 2026-04-01 \
  --end-date 2026-05-07 \
  --initial-cash 500000 \
  --top-ks 5,10 \
  --holding-days 5,10,15,20,30
```

Outputs are written under `/Users/xiwei/stock_research/reports` by default:

- Markdown research validation report
- portfolio equity curve CSV
- portfolio trade detail CSV
- portfolio summary CSV

The portfolio account backtest is for research validation only. It does not
provide trading instructions, position instructions, order instructions, or
investment advice.

## Top20 Retention Backtest

Run:

```bash
stock-research retention-backtest --start-date 2026-01-01 --end-date 2026-05-07 --initial-cash 500000 --top-ks 5,10
```

V2 optimized retention rules:

```bash
stock-research retention-backtest --start-date 2026-01-01 --end-date 2026-05-07 --initial-cash 500000 --top-ks 5,10 --variant v2
```

Outputs are written under `/Users/xiwei/stock_research/reports` by default:

- Markdown research validation report
- retention equity curve CSV
- retention trade detail CSV
- retention summary CSV

The Top20 retention backtest is for research validation only. It does not
provide trading instructions, position instructions, order instructions, or
investment advice.
