# Stock Research Storage Cleanup Execution Plan 2026-06-12

## Goal

Reduce safe storage waste in the `stock_research` database and local research outputs without touching canonical research data.

## Hard Boundaries

Do not delete or truncate:

- `market.stock_minute_bar_*`
- `market.stock_minute_bar`
- `market_daily_bar`
- `factor.*`
- `public.feature_snapshot`
- `public.label_snapshot`
- `market.adjustment_factor`
- `market.corporate_action`
- formal LHB market-layer tables

## Safe Immediate Cleanup

Execute only when checks confirm they are raw payloads, staging scratch data, empty tables, job/audit noise, or local generated outputs:

1. Keep `raw_akshare.finance_payload` empty after the previous cleanup.
2. Vacuum/analyze `raw_akshare.finance_payload` after truncate.
3. Vacuum/analyze small staging/raw empty tables so relfilenode metadata stays clean.
4. Remove local benchmark output directories.
5. Inspect local `outputs/research` largest directories and remove only benchmark/temp/cache-like directories that are not strategy deliverables.

## Deferred Cleanup

Do not execute in this pass:

1. `staging.baostock_stock_minute_bar` historical deletion.
2. `raw_baostock.daily_bar_payload` historical deletion.
3. `staging.tushare_stock_auction_bar` historical deletion.

These need archive verification first:

- export row count by month/date range;
- archive to compressed files outside the PostgreSQL data volume;
- checksum archive files;
- delete in monthly batches;
- run `VACUUM` or `pg_repack` during maintenance window.

## Verification

Before and after:

- database size via `pg_database_size(current_database())`;
- filesystem free space via `df -h /var/lib/postgresql/data`;
- confirm protected tables are not modified by this run;
- list remaining largest cleanup candidates.

## Execution Result

Executed on 2026-06-12:

- Removed local benchmark output directory:
  - `outputs/research/benchmark_lhb_phase18c_20260611`
- Vacuumed/analyzed empty raw/staging scratch tables:
  - `raw_akshare.finance_payload`
  - `raw_akshare.enrichment_payload`
  - `raw_baostock.finance_payload`
  - `staging.eastmoney_stock_spot_snapshot`

Verified after execution:

- `raw_akshare.finance_payload`: 0 rows, 16 kB
- `raw_akshare.enrichment_payload`: 0 rows, 24 kB
- `raw_baostock.finance_payload`: 0 rows, 16 kB
- `staging.eastmoney_stock_spot_snapshot`: 0 rows, 24 kB
- database size remained about 579 GB
- PostgreSQL data volume remained at about 154 GB available

No canonical research data was deleted.

## Follow-up Execution Result

Executed again on 2026-06-12 after operator confirmation:

- Rechecked database size from PostgreSQL:
  - `stock_research`: about 579 GB
- Rechecked scratch/raw tables:
  - `raw_akshare.finance_payload`: 0 rows, 16 kB
  - `raw_akshare.enrichment_payload`: 0 rows, 24 kB
  - `raw_baostock.finance_payload`: 0 rows, 16 kB
  - `staging.eastmoney_stock_spot_snapshot`: 0 rows, 24 kB
- Ran `VACUUM (ANALYZE)` again on the four scratch/raw tables above.
- Inspected largest `outputs/research` entries.
  - No additional directory was deleted.
  - The largest entries are current research deliverables, not benchmark/temp/cache outputs.
  - The only name-based temp-like matches were `trend_discovery_template_*`, which are template research artifacts and were kept.
- Rechecked deferred large cleanup candidates without deleting them:
  - `staging.baostock_stock_minute_bar`: about 213 GB, about 286,982,650 rows
  - `raw_baostock.daily_bar_payload`: about 25 GB, about 33,433,580 rows
  - `staging.tushare_stock_auction_bar`: about 15 GB, about 9,237,413 rows

Filesystem free-space verification was completed through SSH on `192.168.3.187`.

- PostgreSQL runs inside Docker container `postgres`.
- Container path: `/var/lib/postgresql/data`
- Host Docker volume path: `/var/lib/docker/volumes/postgresql_postgres_data/_data`
- `df -h /var/lib/postgresql/data` inside the container:
  - size: 937 GB
  - used: 737 GB
  - available: 154 GB
  - usage: 83%
- `du -sh /var/lib/postgresql/data` inside the container:
  - 588 GB

No protected tables were deleted or truncated in this follow-up run.

## Safe Redundant Data Cleanup Result

Executed on 2026-06-12 after explicit operator request to delete only confirmed-unneeded data:

- Deleted local reproducible caches:
  - `cache/v3_1`
    - local generated CSV cache for v3.1 retention/backtest acceleration
    - covered 2025-01-01 to 2026-05-09
    - about 276 MB before deletion
    - can be rebuilt from database inputs by the cache build command
  - `.pytest_cache`
  - `.worktrees/*/.pytest_cache`
  - Python `__pycache__` directories under `src`, `tests`, `scripts`, and `.worktrees`
  - `dashboard/node_modules/.vite-temp`, which was empty
- Rechecked database candidates and did not delete them when not provably redundant:
  - `raw_baostock.industry_snapshot_payload`
    - kept because `sync_industry_memberships(..., use_cache=True)` reads it as the industry membership cache
  - `staging.eastmoney_stock_auction_minute_bar`
    - kept because it is current auction minute staging data for 2026-06-10 to 2026-06-12
  - `staging.xtick_stock_auction_detail`
    - kept because it is raw xtick auction detail staging data from the auction source test
  - `market.stock_auction_minute_bar`
    - kept as market-layer auction minute data
  - `market.stock_auction_detail`
    - kept as market-layer auction detail data
- Ran `VACUUM (ANALYZE)` on empty scratch/raw tables:
  - `raw_akshare.finance_payload`
  - `raw_akshare.enrichment_payload`
  - `raw_baostock.finance_payload`
  - `staging.eastmoney_stock_spot_snapshot`
- Ran `VACUUM (ANALYZE)` on small auction staging tables after review:
  - `staging.xtick_stock_auction_detail`
  - `staging.eastmoney_stock_auction_minute_bar`

Verification after cleanup:

- No `.pytest_cache` or Python `__pycache__` directories remained outside `.venv`.
- `cache/` remained as an empty directory.
- Database size remained about 579 GB.
- PostgreSQL data volume inside Docker container `postgres`:
  - size: 937 GB
  - used: 736 GB
  - available: 154 GB
  - usage: 83%
- PostgreSQL data directory apparent size remained about 588 GB.

No protected table and no unverified research deliverable was deleted.
