# P1d.2a — Corrected-Shadow Recheck

All four prior shadow legs re-ran after the P1d.2a patch (loader SQL,
constraint rebuild, provider date binding, shared flag function).

## Byte-identical results

| Leg | Baseline eq | Shadow eq | Diff keys | vs original |
|---|---|---|---|---|
| modern 2024-2026 cost0 | 0.374184 | 0.366983 | 63 | **IDENTICAL** (summary + CSV) |
| 2023 fullreg cost0 | 0.893454 | 0.897868 | 4 | **IDENTICAL** |
| 2023 fullreg cost15 | 0.709321 | 0.712830 | 4 | **IDENTICAL** |
| modern 2024-2026 cost15 | 0.196511 | 0.192495 | 63 | **IDENTICAL** |

Why identical is the correct outcome:

- The shadow legs inject recomputed flags and run the engine directly —
  they never went through the loader SQL that was patched.
- `dataclasses.replace()` preserves every field; the old field-by-field
  rebuild only dropped `block_missing_limit_state`, which was False in the
  default constraints used by the shadow runs anyway.
- The shadow script now delegates to the shared `compute_pit_limit_flags`
  (identical logic, single implementation) — flag recompute outputs match
  row-for-row (3,470,036 / 1,185,601 rows, same rule_unknown counts).

## New coverage under corrected_shadow loader mode

`test_loader_modes_smoke` + `test_end_to_end_corrected_shadow_gate` verify
against the real DB (2024-01-02..10):

- `legacy` returns stored flags with risk annotation;
- `corrected_shadow` returns rule-engine flags + `limit_rule_id`, no NULL
  flags, missing → `limit_state_missing`;
- `verified_v2` (columns absent pre-migration) → every row missing =
  fail-closed, no auto-activation;
- strict constraints block every missing-state bar end-to-end.
