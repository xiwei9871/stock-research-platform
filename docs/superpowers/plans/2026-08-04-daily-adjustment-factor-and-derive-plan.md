# Daily Adjustment Factor and QFQ/HFQ Derivation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or equivalent inline execution) to run the verification checkpoints below.

**Goal:** Populate complete daily adjustment factors from the canonical raw daily bars and derive qfq/hfq daily bars without modifying raw rows.

**Architecture:** Treat `market_daily_bar` raw rows as the price/volume base. Build per-asset, per-date adjustment factors from the existing adjusted source rows where available, validate factor coverage and continuity, then write qfq/hfq rows with explicit derivation provenance and idempotent upserts. Existing qfq/hfq rows are replaced only for dates whose derived values are validated.

**Tech Stack:** PostgreSQL (`service=stock_research`), Python/psycopg, existing `market.adjustment_factor` and `market.corporate_action` tables, `public.market_daily_bar`.

---

### Task 1: Inspect schemas and current coverage

**Files:**
- Read: `src/stock_research/schema.py`
- Read: `src/stock_research/daily_close_pipeline.py`
- Read: `src/stock_research/corporate_actions.py`

- [ ] Verify columns, constraints, source labels, and current factor/qfq/hfq counts in PostgreSQL.
- [ ] Confirm raw rows are the only price base and record current qfq/hfq row counts before writes.

### Task 2: Rebuild adjustment factors from raw and adjusted bars

**Files:**
- Read: `src/stock_research/corporate_actions.py`
- Modify only database rows in: `market.adjustment_factor`

- [ ] For each asset/date with raw, qfq, and hfq closes, calculate `qfq_factor=qfq_close/raw_close` and `hfq_factor=hfq_close/raw_close`.
- [ ] Upsert factors with an explicit source version and preserve raw-derived provenance.
- [ ] Audit factor coverage, nulls, nonpositive factors, and discontinuity outliers before deriving bars.

### Task 3: Derive qfq and hfq bars from raw

**Files:**
- Read: `src/stock_research/daily_close_pipeline.py`
- Read: `src/stock_research/corporate_actions.py`
- Modify only database rows in: `public.market_daily_bar`

- [ ] For every raw bar with a validated factor, multiply price fields (`open`, `high`, `low`, `close`, `preclose`) by the factor.
- [ ] Preserve raw volume/amount/status/ST fields and recompute percent change from derived close/preclose when possible.
- [ ] Upsert qfq/hfq rows with source `derived:raw_adjustment_factor_v1`, leaving raw rows untouched.
- [ ] Do not create adjusted rows when a factor is missing or invalid; report those gaps explicitly.

### Task 4: Verify results

**Files:**
- No source-code changes required.

- [ ] Confirm raw row count and values are unchanged.
- [ ] Confirm qfq/hfq date/asset coverage matches raw wherever factors exist.
- [ ] Confirm qfq/hfq prices equal raw multiplied by stored factors within numeric tolerance.
- [ ] Confirm no null prices, invalid factors, or duplicate primary keys were introduced.
