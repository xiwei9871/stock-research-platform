# M1-safety Regression Diff — a1c0be56 → fix/r3-m1-deployment-safety

## Code changes (vs M1 baseline)

| File | Change |
|---|---|
| `src/stock_research/financial_version_store.py` | rewritten: fingerprint no longer event identity; `finver_observation` mutable-state layer; `finver_key_chain` head pointer; advisory-lock serialized ingest; immutable events; `read_as_of` = platform-observation semantics |
| `src/stock_research/eod_v2_writer.py` | rewritten: `incomplete` status; idempotent requires full+valid coverage; NULL/mixed/foreign version detection; actual matched_rows re-read; never uses computed count as success |
| `src/stock_research/data_integrity_gate.py` | rewritten: `LEGACY_READY`/`V2_READY` split; `require_v2`; empty→BLOCKED; invalid/mixed/partial→BLOCKED/DEGRADED |
| `src/stock_research/financial_pit.py` | 1 change: `restated_selected` evidence VERIFIED → INFERRED |
| `scripts/m1_v2_write_drills.py` | rewritten: fault date now has base rows; rollback checksum proof; partial+corrupt synthesis heal test |
| `scripts/m1_finver_drills.py` | rewritten: A→B→A, dedupe, seq integrity, immutability, observation layer |
| `tests/test_r3_m1.py` | +9 tests: LEGACY/V2 gate split, empty→BLOCKED, incomplete, mixed-version block, NULL-version rewrite, fingerprint≠identity, A→B→A, observation-only dedupe, restated→INFERRED |

## Test results

- `test_r3_m1.py`: 24 passed (was 15)
- `test_financial_pit_p2.py`: 23 passed — unchanged, zero new failures
- Total: **47 passed / 0 failed / 0 skipped** (restated-key test now
  resolves on balance_sheet)

## New failure diff set

None. No previously-passing test broke; the skipped restated test was
re-pointed at balance_sheet (where multi-ann keys exist) and passes.

## Gate status delta

| Domain | M1 baseline | Now |
|---|---|---|
| prod tradeability | READY (ambiguous) | LEGACY_READY / require_v2→BLOCKED |
| prod financial_pit | DEGRADED | DEGRADED (unchanged, honest) |
| shadow tradeability | READY | V2_READY |
| combined prod | DEGRADED | DEGRADED |

The `READY → LEGACY_READY` change is a precision fix, not a
regression: production lacks v2 columns and must never be reported
v2-ready.
