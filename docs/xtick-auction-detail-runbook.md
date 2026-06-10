# XTick Auction Detail Runbook

## Purpose

Collect XTick open call auction detail rows for the 09:15-09:25 window.

This source is different from the existing auction result bar:

- `market.stock_auction_bar`: final open/close auction result bars.
- `market.stock_auction_minute_bar`: AKShare/Eastmoney 1-minute open auction process bars.
- `market.stock_auction_detail`: XTick irregular auction detail events with millisecond timestamps.

## Source Choice

Prefer `/doc/hot/dayupdate` with `dataType=bid` for historical all-market backfill. It returns compressed market-segment batches and avoids per-stock API calls.

Use `/doc/hot/biddetail` only for ad-hoc single-stock inspection.

## Account Window

The tested account can access API data from `2026-05-10` onward. Dates before that return a permission error from XTick.

## Environment

Set the token outside the repository:

```bash
export XTICK_TOKEN="..."
```

Do not write the token into scripts, docs, logs, or committed config files.

## Manual Collection

Collect selected market segments:

```bash
cd /Users/xiwei/stock_research
XTICK_TOKEN="$XTICK_TOKEN" .venv/bin/python -m stock_research.cli collect-xtick-auction-detail-v1 \
  --trade-date 2026-06-09 \
  --symbols shm,szm \
  --sleep-seconds 1
```

Default symbols are:

- `szm`: Shenzhen main board
- `shm`: Shanghai main board
- `cyb`: ChiNext
- `kcb`: STAR Market
- `bj`: Beijing Stock Exchange

## Outputs

Collection reports are written to:

```text
outputs/research/xtick_auction_detail_collect/
```

Database rows are upserted into:

- `staging.xtick_stock_auction_detail`
- `market.stock_auction_detail`
