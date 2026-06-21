# Stock Research Storage Retention

Updated: 2026-06-12

## Current Finding

The largest removable storage candidate is not retry garbage. It is the raw/staging audit layer:

- `staging.baostock_stock_minute_bar`: about 213 GB
- `raw_baostock.daily_bar_payload`: about 25 GB
- `staging.tushare_stock_auction_bar`: about 15 GB

The market-layer tables are the canonical research inputs. Staging/raw tables are useful for replay, source debugging, and audit, but they do not need the same online retention window once the historical backfill is stable.

## Retention Policy

Keep online:

- `staging.baostock_stock_minute_bar`: latest 90 calendar days
- `raw_baostock.daily_bar_payload`: latest 180 calendar days
- `staging.tushare_stock_auction_bar`: latest 365 calendar days while LHB auction research is active

Archive before delete:

- Export older rows to compressed CSV or parquet outside the PostgreSQL data volume.
- Store archive metadata: table, date range, row count, checksum, exported_at.
- Verify archive row count matches the pre-delete count.

## Do Not Delete

Do not delete these without a separate research review:

- `market.stock_minute_bar_*`
- `market_daily_bar`
- `factor.*`
- `public.feature_snapshot`
- `public.label_snapshot`

These are active research/read-model tables.

## Candidate Cleanup SQL

Run only after archive verification.

```sql
-- BaoStock minute staging older than 90 days.
delete from staging.baostock_stock_minute_bar
where trade_date < current_date - interval '90 days';

-- BaoStock daily raw payload older than 180 days.
delete from raw_baostock.daily_bar_payload
where trade_date < current_date - interval '180 days';

-- Tushare auction staging older than 365 days.
delete from staging.tushare_stock_auction_bar
where trade_date < current_date - interval '365 days';
```

After large deletes, use a maintenance window:

```sql
vacuum (analyze) staging.baostock_stock_minute_bar;
vacuum (analyze) raw_baostock.daily_bar_payload;
vacuum (analyze) staging.tushare_stock_auction_bar;
```

To return space to the operating system, use `pg_repack` or `vacuum full` during a maintenance window. Plain `vacuum` makes space reusable inside PostgreSQL but usually does not shrink files on disk.

## Operational Notes

- Prefer monthly/batched deletes to avoid long transactions.
- Pause minute backfill jobs while deleting old staging rows.
- Check disk before and after:

```sql
select pg_size_pretty(pg_database_size(current_database()));
```

- Check table sizes:

```sql
select schemaname || '.' || relname as table_name,
       pg_size_pretty(pg_total_relation_size(relid)) as total_size,
       n_live_tup::bigint as estimated_rows,
       n_dead_tup::bigint as dead_rows
from pg_stat_user_tables
where schemaname in ('staging', 'raw_baostock')
order by pg_total_relation_size(relid) desc;
```
