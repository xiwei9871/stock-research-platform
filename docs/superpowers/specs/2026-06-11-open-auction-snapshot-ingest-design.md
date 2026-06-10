# Open Auction Snapshot Ingest Design

## Goal

Replace full-market use of AKShare `stock_zh_a_hist_pre_min_em` with a production-safe opening auction data model:

- final 09:25 auction result comes from Tushare or another paid final-result source;
- 09:15-09:25 process data comes from full-market AKShare `stock_zh_a_spot_em` snapshots collected during the live auction window;
- `stock_zh_a_hist_pre_min_em` remains available only for small watchlist diagnostics.

## Source Policy

Use three clearly separated source roles.

1. Final result source: Tushare `stk_auction_o`, existing `market.stock_auction_bar`, source `tushare`.
2. Live process source: AKShare `stock_zh_a_spot_em`, new snapshot tables, source `eastmoney_spot_snapshot`.
3. Small-pool fallback source: AKShare `stock_zh_a_hist_pre_min_em`, existing `market.stock_auction_minute_bar`, source `eastmoney_pre_min`.

The process source must not overwrite final result rows. The 09:25 process snapshot is a check and feature input, not the authoritative 09:25 auction result.

## Snapshot Schedule

Collect six full-market snapshots per trading morning:

- target label `09:15`, trigger at `09:15:05`
- target label `09:17`, trigger at `09:17:05`
- target label `09:19`, trigger at `09:19:05`
- target label `09:21`, trigger at `09:21:05`
- target label `09:23`, trigger at `09:23:05`
- target label `09:25`, trigger at `09:25:10`

The five-second delay avoids reading before Eastmoney finishes publishing the snapshot. The 09:25 trigger uses ten seconds because the final auction transition is more sensitive.

## Data Model

Create a separate snapshot pair instead of reusing `stock_auction_minute_bar`.

Staging table: `staging.eastmoney_stock_spot_snapshot`

- `source_endpoint`
- `request_params`
- `raw_symbol`
- `ts_code`
- `trade_date`
- `snapshot_time`
- `target_time`
- price and turnover fields copied from `spot_em`
- raw `payload`
- `payload_hash`

Market table: `market.stock_open_auction_snapshot`

- `asset_id`
- `ts_code`
- `trade_date`
- `snapshot_time`
- `target_time`
- `auction_phase = open_call`
- `latest`
- `open`
- `prev_close`
- `high`
- `low`
- `volume`
- `amount`
- `volume_ratio`
- `turnover_rate`
- `source = eastmoney_spot_snapshot`

Primary key: `(trade_date, asset_id, target_time, source)`.

The key uses `target_time`, not exact `snapshot_time`, so reruns for the same target slot update the slot rather than duplicating rows.

## Normalization

Normalize symbols from AKShare `stock_zh_a_spot_em`:

- six-digit codes beginning with `6` map to `.SH`;
- codes beginning with `0` or `3` map to `.SZ`;
- codes beginning with `4`, `8`, or `9` map to `.BJ`;
- unknown formats raise a `ValueError` and are reported as skipped rows.

Persist raw payloads in staging so source changes can be audited without guessing.

## CLI And Operations

Add a new CLI command:

```bash
.venv/bin/python -m stock_research.cli collect-open-auction-spot-snapshot-v1 \
  --trade-date 2026-06-11 \
  --target-time 09:17 \
  --output-dir outputs/research/open_auction_spot_snapshot
```

Add a helper command to print cron entries:

```bash
.venv/bin/python -m stock_research.cli open-auction-spot-snapshot-cron-entry
```

Add a shell wrapper:

```bash
scripts/run_open_auction_spot_snapshot.sh 09:17 2026-06-11
```

The wrapper should default to today's date when the date argument is omitted.

## Reporting

Each run writes:

- detail CSV with row counts, skipped rows, and error text;
- markdown report with `trade_date`, `target_time`, `snapshot_time`, `queried_rows`, `upserted_rows`, and `skipped_rows`;
- latest detail/report links for operator checks.

## Existing AKShare Minute Collector

Keep `collect-open-auction-minute-v1` but update the runbook to state:

- it is not the full-market production source;
- it is for small watchlists and diagnostics;
- it should not be used for historical full-market backfill.

## Testing

Use test-first coverage for:

- `spot_em` row normalization and symbol to `ts_code` conversion;
- staging and market upsert SQL;
- collector calls `stock_zh_a_spot_em` once per target time and writes all market rows;
- CLI parser accepts the new collection and cron commands;
- schema contains the new tables, source checks, primary keys, and indexes;
- cron generator emits the six requested trigger times.
