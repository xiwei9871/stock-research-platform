# P1d.2a C — Minute Date/Version Binding Audit

## What the ledger proves vs doesn't

`r2_downstream_minute_done.json` keys are `asset|freq|source` — **asset-level
completeness**, carrying `raw_sig`/`factor_sig` versions. They say nothing
about whether a specific trading date has qualified rows. Asset-level done
+ "some minute rows exist that day" is NOT proof that the specified
source/version qfq data is complete for that date.

## Real-DB evidence (the reviewer's suspicion confirmed)

| Asset | baostock rows | akshare rows | verdict on 2026-10-22 |
|---|---|---|---|
| CN:SH:603213 | 57,552 (full history, raw+qfq) | **48 — only 2026-06-17** | akshare key cannot cover the date → `minute_date_unverified` |
| CN:SH:605077 | 66,192 | **48 — only 2026-06-17** | same |

The baostock raw/qfq rows exist but the baostock factor chain is the
terminally-gapped source for these assets — only the akshare key qualifies,
and it covers a single session.

## Implemented binding

- `LedgerMinuteQualificationProvider.set_date_checker(fn)` —
  `(asset_id, trade_date, freq, source) -> bool`.
- `load_tradeability_context` binds it to
  `EXISTS(SELECT 1 FROM market.stock_minute_bar WHERE asset_id=%s
   AND trade_date=%s AND freq=%s AND adjust_type='qfq' AND source=%s)`.
- Version string now encodes tier: `:date_rows_verified` / `:key_level` /
  `:key_level_unverified_date`; `ctx.minute_date_verified` surfaced into
  result details.
- **Naming honesty (P1d.2a closeout)**: `date_rows_verified` means
  "当日 qfq 行存在性已核验" — the required source/freq/adjust rows EXIST for
  that date. It does NOT claim full-session completeness (expected bar
  count per session is a separate coverage audit, out of scope here and
  NOT a blocker for daily-frequency rule migration).
- Traded day + unverified → `data_ready_minute=False`,
  reason `minute_date_unverified` (fail closed).

## DB assertions updated (18/18 pass)

- `factor_gap_residual` 603213@2026-10-22 → NOT ready (`minute_date_unverified`)
- `alt_source_date_rows_verified` 603213@2026-06-17 → ready, gap marker kept
- `alt_source_qualified` 605077@2026-10-22 → NOT ready
- `alt_source_date_rows_verified_605077` 605077@2026-06-17 → ready
- 15 no-done-key assets + 600153 isolation unchanged (still blocked)

## Remaining honesty note

`date_rows_verified` proves **当日 qfq 行存在性已核验**, not full-session
completeness (expected bar count per freq varies with trading hours). Full
per-date completeness requires expected-vs-actual bar-count checks —
recorded as a migration-phase enhancement, not claimed here and not a
blocker for daily-frequency rule migration.
