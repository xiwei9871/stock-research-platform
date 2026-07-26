# Disable Minute Staging Design

## Goal

Release the space occupied by `staging.baostock_stock_minute_bar` and prevent normal minute ingestion from recreating the same storage pressure, without changing `market.stock_minute_bar` writes or K-line reads.

## Design

- Truncate `staging.baostock_stock_minute_bar`. This removes only the archived Baostock minute payload; normalized K-lines remain in `market.stock_minute_bar`.
- Make minute staging archival opt-in through `BAOSTOCK_MINUTE_STAGING_ENABLED`.
- Default the flag to disabled. Values `1`, `true`, `yes`, and `on` enable archival; all other values leave it disabled.
- When disabled, `upsert_stock_minute_bars()` builds and writes only market rows.
- When enabled, preserve the existing transaction order: staging first, market second.

## Safety and verification

- Unit tests prove the default path issues only the market insert.
- A second unit test proves explicit opt-in retains the prior staging-plus-market behavior.
- Database verification checks the staging row count and relation size after truncation.
- A direct K-line query against `market.stock_minute_bar` verifies the query path remains available.

## Trade-offs

Disabling staging removes raw minute payload replay and staging-versus-market count validation. It does not remove normalized raw or qfq K-lines. The environment flag preserves a deliberate recovery path when raw archival is needed again.
