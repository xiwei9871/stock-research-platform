# 03 — Freshness Gate Shadow Implementation (M0.7 / P0-1)

Date: 2026-10-20. Branch: `audit/tech-strategy-m0-20261019`.
Status: **repaired-verified (module + tests + live sweep) / shadow-mode only** —
no EOD behavior changed, no enforcement, no scheduler, no manifest write.

## What exists now

- Module `src/stock_research/data_freshness_gate.py` (committed `dbac43ec` by user
  session; extended this session):
  - `InputSpec` registry: name / category / kind / table / date_column /
    coverage_column / min_daily_rows / consumers / window /
    degradation_contract.
  - `expected_trade_date_for_window`: `post_close` = last open day ≤ as_of;
    `intraday` = as_of itself when it's an open day (09:15/09:40 collections
    legitimately target today).
  - `missing_trading_days`: mid-window gap detection (not just `MAX`).
  - `evaluate_input_status`: READY / DEGRADED / BLOCKED / NOT_EVALUATED —
    `required_daily` unhealthy → BLOCKED; `optional_enhancement`/`conditional`
    unhealthy → DEGRADED (visible, non-blocking); `static_frozen` →
    existence/version check only; `unused` → NOT_EVALUATED.
  - `run_freshness_sweep` + `DEFAULT_INPUT_SPECS` (16 registered inputs) —
    reproducible read-only sweep; writes CSV report when asked.
- Tests `tests/test_data_freshness_gate.py`: **13 passed** — covers weekend
  skipping, intraday window, mid-range gap detection, required→BLOCKED,
  low-coverage→BLOCKED, optional→DEGRADED, static-frozen semantics,
  newer-than-expected intraday input → READY, true-latest reporting.
- Live shadow report: `outputs/research/data_freshness_health_20261020.csv`
  (as_of 2026-10-19, post_close).

## Live sweep result (2026-10-19, regenerated with corrected latest dates)

| Status | Inputs |
|---|---|
| READY (10) | market_daily_bar, stock_minute_bar, asset_status_daily, stock_score_daily, stock_technical_features_daily, lhb_top_list_daily, lhb_event_features_daily, index_daily_bar, industry_daily_bar, market_emotion_state_daily, stock_auction_minute_bar(EM, intraday window) |
| DEGRADED (4) | stock_auction_bar(open_call) latest **2026-09-07**; stock_intraday_features_daily latest **2026-08-03**; industry_intraday_features_daily **2026-08-03**; adjustment_factor **2026-08-27** (conditional) |
| NOT_EVALUATED (1) | corporate_action (no registered consumer) |

## Bugs fixed this session (test-first)

1. `actual_latest_date` was queried `WHERE date=expected` → stale tables reported
   `None` instead of their true newest date. Now a global `max()` is fetched
   separately; `2026-09-07`/`2026-08-03`/`2026-08-27` surface correctly.
2. `stale` used `latest != expected` — an intraday input already holding a NEWER
   session (10-20 minute bars at a 10-19 post-close check) was falsely DEGRADED.
   Now `latest < expected` is the stale condition (test:
   `test_intraday_input_newer_than_expected_is_ready_not_stale`).
3. Added `run_freshness_sweep` + input registry — the first CSV had been
   produced ad-hoc; sweep is now reproducible.
4. Registry column fixes: `lhb_top_list/lhb_event_features` → `ts_code`,
   `index_daily_bar` → `index_id`, `industry_daily_bar` → `industry_code`,
   `corporate_action` → `date_column="event_date"`.

## Known limitations (honest)

- The gate checks **presence + freshness + coverage**, not content correctness.
  Example: `market_emotion_state_daily` shows READY for 10-19 even though the
  M0.5 audit proved some historical rows are write-time snapshots with divergent
  values — content integrity needs the regime release's prefix-stability check,
  not this gate.
- `missing_trade_dates` is evaluated over a 15-day lookback window; the true
  staleness depth is carried by `actual_latest_date` (e.g. 8-03).
- File/static-artifact inputs (`kind="file"`) are spec'd but the file checker
  is not wired into the sweep yet (midtrend dirs, funnel CSV, watchlist CSV).
- No per-strategy blocking is wired — Shadow Mode reports only, by design.

## Round-2 additions (M0.8)

- `InputSpec.where` — per-spec SQL scoping (e.g. `auction_phase='close_call'`,
  `score_version='manual_v1'`); applied to all presence/coverage/max queries.
- `close_call` now monitored as its own input → latest **2026-06-09** surfaces
  separately from open_call **2026-09-07** (previously masked by phase-agnostic
  MAX). Registry is now 17 inputs; sweep: **11 READY / 5 DEGRADED / 1 NOT_EVALUATED**.
- `scripts/run_freshness_gate_shadow.sh` — daily-ready runner emitting CSV+JSON
  to `outputs/research/freshness_gate_shadow/`; executed manually for
  2026-10-19 (`{READY:11, DEGRADED:5, NOT_EVALUATED:1}`). **Not yet in cron** —
  the only remaining step for daily Shadow Mode is approving this zero-risk job.

## Pending (needs approval to integrate)

- Wire `run_freshness_sweep` into a daily cron emitting the report post-close.
- Manifest/readiness fields: `input_date, coverage, source_version,
  fallback_used, degradation_reason, health_status` per input.
- Per-consumer enforcement: only after N clean shadow days, promote
  `required_daily` BLOCKED → publish block; `optional` stays DEGRADED-visible.
