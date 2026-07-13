# LHB Auction Data Ingest Design

## Goal

Add a dedicated auction data layer for LHB short-line research, focused on opening and closing call auctions. This phase does not backfill ordinary post-09:30 1min bars.

## Source

Use Tushare as the primary source:

- `stk_auction_o` for opening call auction.
- `stk_auction_c` for closing call auction.

The token is read from `TUSHARE_TOKEN` or passed at runtime by the caller. Tokens are not stored in code, reports, or output files.

## Data Model

Create a normalized `market.stock_auction_bar` table keyed by `trade_date`, `asset_id`, `auction_phase`, and `source`.

Auction phases:

- `open_call`
- `close_call`

Persist the standard OHLCV-style auction fields returned by Tushare:

- `open`, `high`, `low`, `close`
- `volume`
- `amount`
- `vwap`

Keep a staging table for raw Tushare payloads and request parameters, matching the existing minute-data ingestion pattern.

## Scope

Phase17 initial scope:

- Tushare query wrapper.
- Row normalization.
- Staging and market upsert.
- CLI command for direct sync by `ts_code`, date range, and phase.

Out of scope for this phase:

- Full LHB candidate universe planning.
- Auction feature generation.
- Entry/exit rule changes.
- Ordinary 1min minute-bar ingestion.

## Testing

Use test-first coverage for:

- Tushare auction row normalization.
- Staging payload preservation and hash.
- Upsert writes both staging and market SQL.
- Query wrapper maps `open_call` and `close_call` to the correct Tushare endpoints.
- CLI accepts auction sync arguments.
