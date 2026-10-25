# P1d.2 E — Storage Migration Readiness (design + isolated tests only)

Status: READY FOR REVIEW — **not executed**. Production `asset_status_daily`
(17.29M rows) is untouched. Formal migration requires separate user
authorization.

## Recommended shape: v2 columns in-place

```sql
ALTER TABLE core.asset_status_daily
  ADD COLUMN IF NOT EXISTS is_limit_up_v2   boolean,
  ADD COLUMN IF NOT EXISTS is_limit_down_v2 boolean,
  ADD COLUMN IF NOT EXISTS limit_state_v2   smallint,   -- 0 not_computed, 1 verified, 2 rule_unknown, 3 data_insufficient
  ADD COLUMN IF NOT EXISTS limit_rule_id_v2 text,
  ADD COLUMN IF NOT EXISTS limit_flags_version text DEFAULT 'pit_rules_v1';
```

Rationale over a new table: same PK (asset_id, trade_date), same write path
in `core_data.py`, no join fan-out for readers, trivial per-batch rollback
(`UPDATE ... SET *_v2 = NULL WHERE batch_id = ...`).

## Forbidden fallback (explicit)

`COALESCE(is_limit_up_v2, is_limit_up_v1)` is **prohibited**: `v2 IS NULL`
may mean rule_unknown/data_insufficient, not "not yet computed". Readers
must branch on `limit_state_v2`, not NULL-ness. Only a `limit_state_v2 = 1`
(verified) row may gate execution; any other state fails closed.

## Compatible read layer

`tradeability_at()` already returns rule-resolved flags with
`stored_flag_disagrees_with_effective_rule`; during migration it reads v2
when `limit_state_v2=1`, else computes from the rule engine — never from v1
alone. Loaders (P1d.2-B) continue reading v1 until cutover is authorized.

## Batch plan

1. `p1d1_shadow` schema proved the write shape: 369,681-row sample, unique
   PKs, idempotent re-run (0 diff on second pass).
2. Backfill in ~250k-row batches keyed by trade_date range; each batch is a
   single transaction with `ON CONFLICT DO UPDATE` of v2 columns only.
3. Per-batch verification: row count match, board/status unchanged, v2↔v1
   diff report attached to the batch log.
4. Estimated cost: recompute reads `market_daily_bar` raw + status rows
   (indexed); ~17.3M rows ≈ hours of sequential IO, no locks on writers
   since v2 columns are additive. Schedule outside EOD windows.
5. Idempotency: v2 write is deterministic from (rule set, status, raw bars);
   re-running a batch yields zero changes — verified on the shadow schema.

## Rollback

- Per-batch: `UPDATE core.asset_status_daily SET is_limit_up_v2=NULL,
  is_limit_down_v2=NULL, limit_state_v2=0 WHERE <batch predicate>`.
- Global: `ALTER TABLE ... DROP COLUMN` — v1 untouched throughout.
- Cutover flag flips readers, not data — flip back = instant revert.

## Open items before authorization

- `core_data.py` writer change: replace static thresholds with rule-engine
  flags at insert time (new rows correct from day one).
- Decide EOD incremental semantics: nightly writer computes v2 for new
  dates only; historical rows filled by the batch job.
- Beijing ST rule still `verified=False` — those rows get
  `limit_state_v2=2` until official text is verified.
- 1990-12-19 anomalous ST status rows (4 assets) need upstream status repair,
  separate from flag migration.
