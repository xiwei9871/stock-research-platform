# P1d.2a Closeout — Three Cutover Blockers Resolved

Baseline: `4ace0b18` (`fix/p1d2a-cutover-safety`)
Scope: strictly limited — no new audit sweeps.

## P0-1: apply_pit_flags missing-match fail-open → FIXED

Before: `shadow_rule_unknown.fillna(False)` after the left merge silently
converted every unmatched price row into "rule known, not at limit" —
fail-open in corrected_shadow.

Now three explicit states (`qualification_state` column on merged prices):

| State | Meaning | Order treatment |
|---|---|---|
| `verified` | matched + verified rule | computed flag values used |
| `rule_unknown` | matched, no verified rule | flags forced True, `limit_state_missing=True` |
| `qualification_missing` | NO flag record at all | same fail-closed treatment |

Synthetic coverage: `test_apply_pit_flags_three_way_state` proves an
unmatched asset can never trade in corrected_shadow.

## P0-2: verified_v2 schema calibrated

- DDL/read check/state enum now agree: required columns =
  `{is_limit_up_v2, is_limit_down_v2, limit_state_v2, limit_rule_id_v2}`.
- `is_suspended` deliberately stays **v1** — it is source PIT status, not a
  rule-derived flag; STORAGE_MIGRATION_READINESS.md documents why no
  `is_suspended_v2` exists, and the missing check still includes
  `is_suspended IS NULL`.
- v2 SQL built explicitly (not via .replace chains) → no silent divergence.
- Absent columns → all rows `limit_state_missing` — permanent-missing is
  honest "not migrated", not hidden schema mismatch.

## P0-3: real corrected_shadow end-to-end gate

`test_corrected_shadow_end_to_end_blocks_missing` (real DB,
2024-01-02..02-29, top20):

- `block_missing_limit_state=True` at both 0 and 15 bps — no
  `limit_state_missing` row executes in either leg;
- `test_corrected_shadow_ignores_stored_v1_flags` — corrected flags are
  recomputed by the engine (rule_id present), never copied from v1;
- `test_legacy_vs_corrected_diff_explainable` — corrected prices carry a
  traceable state for every row; corrected leg can only block MORE on
  missing qualification, never invent fills;
- legacy↔corrected differences map to `rule_id` / missing-state blocks.

## Wording fix

`date_verified` renamed `date_rows_verified` — explicitly "当日 qfq 行
存在性已核验" (row existence), NOT "当日完整性已验证" (full-session
completeness). Per-date bar-count coverage stays a separate audit and does
not block daily-rule migration.

## Verification

| Check | Result |
|---|---|
| Focused suite (18 files) | **387 passed / 0 failed** |
| `p1d2_db_assertions.py` | **18/18** |
| p1d2a tests | 13 (4 new for this closeout) |

Stopped after acceptance — no production migration or cutover performed.
