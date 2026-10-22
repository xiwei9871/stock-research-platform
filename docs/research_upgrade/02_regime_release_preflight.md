# 02 — Regime Release Preflight (M0.6)

Date: 2026-10-20. Branch: `audit/tech-strategy-m0-20261019` @ `1149c763`.
Status vocabulary per gate rule: repaired-verified / designed-not-executed /
permission-blocked / remaining-gap.

## Verdict: PARTIAL — release package designed and replay-verified; **merge/deploy still blocked pending this preflight's explicit approval**

---

## A. Daily update mechanism — root cause restated (verified)

- `daily_close_pipeline.upsert_market_emotion_state_daily` calls
  `compute_market_emotion_row(trade_date)` — it writes **one row for today only**
  (`daily_close_pipeline.py:2292`, impl `:2130`). These rows are write-time snapshots:
  e.g. the `2026-06-23` row was written `2026-06-29 19:15`, `2026-07-09` written same-day
  `21:55` — before source data were final — and are **never rewritten**. 79 rows after
  `2026-06-05` in the DB diverge from a full-history rebuild for exactly this reason.
- The function itself is deterministic and correct — a fresh `2026-10-19` recomputation
  equals the full-CSV rebuild value-for-value. The defect is architectural
  (stale incremental snapshots), not algorithmic.
- The regime side was never updated daily at all: EOD replay copies the static legacy
  seed CSV (`market_regime_confirmation_daily.csv`, ends `2026-06-05`), and the simulator's
  `exposure_by_date.get(d, 1.0)` silently filled the gap with full exposure — now
  fail-closed (M0.5).

### Proposed mechanism (designed-not-executed)

Replace "append today's row" with **deterministic full rebuild + atomic publish**, per day:

1. Recompute emotion over the full history window via `run_market_emotion_state_v1_backfill`
   → staging dir.
2. Recompute regime via `build_market_regime_confirmation_from_frames` on the fresh emotion
   + market frames → staging dir.
3. Validate (checklist §D) → atomic publish: DB rows replaced in one transaction
   (delete-insert or versioned partition swap); CSV artifact written to a dated run dir and
   a `latest` symlink moved — never in-place overwrite.
4. Fail-closed: any validation failure keeps the previous published state untouched and
   fails the pipeline stage loudly (no partial publish, no `1.0` fallback).

## B. Dependency & scheduling order (verified)

| Order | Stage | Entry point / scheduler |
|---|---|---|
| 1 | Daily bars / index / limit / turnover sources | existing EOD collectors (pre-20:30) |
| 2 | Market emotion **full rebuild** | `market-emotion-state-v1-backfill` — to be invoked by daily close pipeline (replaces per-row upsert) |
| 3 | Market regime **full rebuild** | `market-regime-confirmation-v1-backtest` — consumes rebuilt emotion + market frames |
| 4 | Formal strategy EOD replay | `com.stockresearch.strategy-eod-publish` launchd **20:30** → `scripts/run_strategy_daily_eod_cron.sh` |
| 5 | Artifact sync to stock-prod | `com.stockresearch.dashboard-daily-sync` launchd **22:15** → `deploy/sync_dashboard_release.sh` |
| 6 | Readiness check | `run_platform_ready_check_cron.sh` |

Verified: local `crontab` holds only open-auction jobs; EOD runs under the two launchd
plists above; nothing on stock-prod's crontab generates regime. **Ordering requirement:**
stages 2–3 must complete before stage 4 reads `market_regime_confirmation_daily.csv`;
a single orchestrated nightly chain is preferable to trusting wall-clock gaps.

## C. Serenity C2 caller census (verified — blast radius contained)

`rg serenity_tight3b_c2` across `src/`, `scripts/`, `tests/`:

- `src/stock_research/serenity_tight3b_c2_experiment.py` — definition; `_normalize_market_exposure`
  + `_validate_market_exposure_coverage` now raise `ValueError` on missing exact rebalance
  dates or missing/NaN `target_exposure` (`:521`,`:535`, error strings `:546`,`:564`).
- `src/stock_research/tech_bottleneck_v1.py` — formal strategy calls it; `_extend_market_exposure`
  (`:445`) appends an end-date extension row **after** validation, so it can no longer mask
  missing intermediate rebalance dates.
- `src/stock_research/cli.py` — CLI dispatch only.
- `tests/test_serenity_tight3b_c2_experiment.py` — extended to assert fail-closed on
  missing/invalid rebalance exposure (6 passed, M0.5).

No other strategies call C2; the common-code change affects only exposure-required paths
and intentionally so.

## D. Validation checklist designed for the daily mechanism (designed-not-executed)

1. **Latest-trading-day coverage**: last regime date == latest trading day in market frames.
2. **No missing rebalance dates**: exact-date membership for every strategy rebalance date
   (the fail-closed validator — already implemented and tested).
3. **No duplicate dates**; dates strictly increasing.
4. **Value domain**: `target_exposure` within legal range, non-NaN, non-null on all rows.
5. **Staleness guard**: if last regime date < last trading day ⇒ stage fails (closed),
   prior published state retained.
6. **Prefix stability**: today's rebuild must agree with yesterday's published prefix
   cell-for-cell on shared dates (catches silent source rewrites — the exact bug found here).

## E. Isolated replay evidence (repaired-verified, local only)

Workspace `outputs/research/m0_5_market_state_recovery_20261020/` + replay probes:

| Check | Result |
|---|---|
| Emotion rows sliced `…10-16` / `…10-19` / canonical | 915 / 916 / 916 |
| Emotion prefix stability (next-day rebuild preserves prior dates) | ✓ |
| Regime prefix stability | ✓ |
| Full-regime rerun idempotence (byte-identical) | ✓ sha `300cfa51…83c2` |
| Rebuilt regime reproduces strategy equity endpoint | `1.6562725546299535` (exact) |
| Old input under new validator | correctly rejected, 9 missing rebalance dates named |
| Old vs new effective exposure | 5 dates differ (old implicit `1.0` vs recomputed `0.7`) |

One caveat carried over: an intermediate comparison script reported 306 differing cells in
a differently-normalized frame pair — NOT the published paths; direct
fresh/CSV/same-date checks all show deterministic agreement. Flagged for a final sanity
re-run during preflight execution.

## F. Rollback & failure drill (designed-not-executed)

- **Versioned publish**: every publish keeps `YYYYMMDD/` run dir + manifest sha; rollback =
  repoint `latest` + restore prior DB partition from the retained export (the
  `market_emotion_state_daily` table is fully exportable in minutes).
- **Failure drill plan**: (1) truncate one source frame → expect fail-closed at §D.1;
  (2) inject a duplicate date → reject at §D.3; (3) NaN `target_exposure` → reject at §D.4;
  (4) simulate source-row rewrite → reject at §D.6; each drill asserts prior published
  state remains byte-identical. Run these in the isolated workspace before approval.

## G. Pre-deploy / post-deploy checklists

**Pre-deploy**: ① all §F drills green in isolation; ② diff of `daily_close_pipeline.py`/
`market_*`/`serenity*`/`tech_bottleneck_v1.py` limited to reviewed hunks; ③
`tests/test_tech_bottleneck_v1_market_exposure.py` + `test_serenity_tight3b_c2_experiment.py`
+ `daily_close_pipeline` tests green; ④ first live run in dry-run mode writes staging only.
**Post-deploy**: ① readiness endpoint no longer PARTIAL on regime/emotion dimensions;
② dashboard review-queue evidence digests non-PARTIAL; ③ next trading day produces a new
regime row and prefix stays stable; ④ EOD equity endpoint unchanged (`1.6562725546299535`)
on the frozen baseline inputs.

## H. What is still NOT done (needs approval)

- No merge to `main`, no production deploy, no cron/launchd edit, no DB write.
- The daily-rebuild code path itself is **designed, not yet written** — it is the only
  code change needed in this release and is small (orchestrate existing functions +
  publish/validate wrapper).

---

## I. Complete upstream dependency inventory for this release (M0.6 expanded)

Full consumer-dependency matrix (32 items): `docs/research_upgrade/02_data_dependency_matrix.csv`.
Recovery designs: `docs/research_upgrade/02_data_freshness_recovery_plan.md`.

The Regime release touches only the **market_daily_bar → emotion rebuild → regime rebuild
→ tech_bottleneck EOD → publish → sync** spine. Per-input freshness measured on 2026-10-20:

| # | Input | Role in release | Freshness | Gate |
|---|---|---|---|---|
| 1 | `public.market_daily_bar` | emotion + replay frames | 2026-10-19, 全市场 | required → READY |
| 2 | `market.trading_calendar` | expected-day computation | to 2027-02 | required → READY |
| 3 | `core.asset_status_daily` / `asset_master` | universe/status filter | 2026-10-19 | required → READY |
| 4 | `market_emotion_state_daily` | rebuild source rows | stale incremental snapshots (root cause fixed by full rebuild) | required → repaired-verified |
| 5 | rebuilt regime CSV (isolated) | `TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH` | 2026-10-19, sha `300cfa51…` | required → repaired-verified |
| 6 | frozen universe `serenity_bottleneck_baseline_...20260605` (148) | candidates seed | static_frozen (by design) | version+hash check |
| 7 | `factor.stock_score_daily` `manual_v1` | EOD top_scores | 2026-10-19 | required → READY |
| 8 | `ops.daily_pipeline_status` | dependency gate input | execution-only semantics | must be extended (§J) |
| 9 | `strategy_daily_eod/<date>` artifacts + publish | output spine | 2026-10-19 | required → READY |

All `required` inputs for this release are READY or repaired-verified — **no stale chain
found on the regime spine blocks this release** (see §K).

## J. Freshness & consumer-contract conditions (release gate semantics)

Per the M0.6 decision, release gates use tri-state data health, **separate from job_status**:

- **READY** — latest data date == expected trading day (`market.trading_calendar`), coverage
  ≥ threshold, no intermediate trading-day gap, and the input is actually consumed.
- **DEGRADED** — optional enhancement stale/missing; publish allowed only if the strategy's
  degradation contract permits; `fallback_used` + `degradation_reason` written to manifest.
- **BLOCKED** — required input missing/invalid/stale or coverage below threshold;
  **formal publish prohibited** regardless of job success.

Known defect this release partially depends on fixing later (not a release blocker):
`check_strategy_daily_eod_dependencies` (`strategy_daily_eod.py:1061-1103`) evaluates the
`intraday` dependency key as `minute5_status == success` only — it never inspects
`factor.stock_intraday_features_daily` (stale since 2026-08-03) or `market.stock_auction_bar`
(open_call 2026-09-07 / close_call 2026-06-09). Those tables are **optional enhancements**
for lhb_shortline backtests — under §5.2 they map to DEGRADED, visible, not release-blocking.
Their recovery is tracked in `02_data_freshness_recovery_plan.md` P0-A/P0-B.

## K. Release-blocking conditions for THIS deployment

| Condition | Status | Blocks? |
|---|---|---|
| §F failure drills pass in isolated workspace | designed, run before deploy | yes — pre-deploy |
| Formal strategy files diff limited to reviewed hunks | to verify at packaging | yes — pre-deploy |
| Focused tests green (exposure validation + serenity + pipeline) | M0.5 evidence: 2+6+4 passed | yes — pre-deploy |
| Regime daily-rebuild code written + staged | designed-not-written | yes — pre-deploy |
| Regime + fail-closed deployed **as one controlled change** (old static CSV + new validator ship together, else EOD fails closed immediately) | packaged | yes — ordering gate |
| TDX/Tushare auction + intraday recovery | **separate workstream** | **no — per instruction, does not block this release** |
| Post-deploy: readiness no longer PARTIAL on regime/emotion; next-day regime row appears; equity endpoint `1.6562725546299535` stable | verify after deploy | post-deploy |

## L. Expansion note

Sections I–K added 2026-10-20 per M0.6 scope expansion (platform-wide Data Freshness &
Consumer Contract). Sections A–H are the original preflight content unchanged.
