# Open Auction Minute Collect Runbook

## Purpose

Collect 1-minute open call auction process bars for the 09:15-09:25 window after the auction window has completed.

The current implementation uses AKShare `stock_zh_a_hist_pre_min_em`, backed by Eastmoney pre-market minute data. This source is suitable for the current/latest trading day collection after 09:25. It is not a historical full-market replay source.

## Production Source Policy

For full-market opening auction process data, use `collect-open-auction-spot-snapshot-v1`, backed by AKShare `stock_zh_a_spot_em`.

The production snapshot schedule is:

- `09:15`
- `09:17`
- `09:19`
- `09:21`
- `09:23`
- `09:25`

Cron entries trigger on those minute marks; the wrapper captures the actual `snapshot_time` when the command runs. The 09:25 snapshot is a process snapshot and should not overwrite final auction result rows in `market.stock_auction_bar`.

The existing `collect-open-auction-minute-v1` command uses AKShare `stock_zh_a_hist_pre_min_em`. Keep it for small watchlists and diagnostics only. It is not a stable full-market historical or production backfill source.

## Database Tables

- `staging.eastmoney_stock_auction_minute_bar`
- `market.stock_auction_minute_bar`

Rows are keyed by `trade_time`, `asset_id`, `auction_phase`, `freq`, and `source`, so repeated daily retries update existing rows instead of duplicating them.

## Manual Run

```bash
cd /Users/xiwei/stock_research
OPEN_AUCTION_MINUTE_UNIVERSE_PATH=/path/to/universe.csv \
  scripts/run_open_auction_minute_collect.sh "$(date +%F)"
```

The universe CSV must include a `ts_code` column such as `600023.SH`.

## Cron

Generate the crontab lines:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.cli open-auction-minute-cron-entry \
  --universe-path /path/to/universe.csv
```

Default output:

```cron
40 9 * * 1-5 cd /Users/xiwei/stock_research && OPEN_AUCTION_MINUTE_UNIVERSE_PATH=/path/to/universe.csv OPEN_AUCTION_MINUTE_OUTPUT_DIR=outputs/research/open_auction_minute_collect scripts/run_open_auction_minute_collect.sh "$(date +\%F)" >> logs/open_auction_minute_collect.log 2>&1
10 15 * * 1-5 cd /Users/xiwei/stock_research && OPEN_AUCTION_MINUTE_UNIVERSE_PATH=/path/to/universe.csv OPEN_AUCTION_MINUTE_OUTPUT_DIR=outputs/research/open_auction_minute_collect scripts/run_open_auction_minute_collect.sh "$(date +\%F)" >> logs/open_auction_minute_collect.log 2>&1
```

Install with `crontab -e` after checking the universe path.
