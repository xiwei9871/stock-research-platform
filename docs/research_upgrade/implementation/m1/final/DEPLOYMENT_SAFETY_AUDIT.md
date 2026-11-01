# M1 Deployment Safety Audit — fixes & re-verification

Baseline `a1c0be56` → `fix/r3-m1-deployment-safety`.
Scope: the four P0 gaps from independent review. No scope expansion.

## P0-1 — V2 EOD integrity & gate

| Gap | Fix |
|---|---|
| `READY` could mean legacy or v2 | `evaluate_tradeability` now returns `LEGACY_READY` (v1 healthy, v2 absent) vs `V2_READY` (v2 cols + 100% single-version valid coverage). `require_v2=True` forces BLOCKED when unmet. |
| partial writes could report success | `emit_eod_v2_flags` status set: `blocked` / `incomplete` / `idempotent` / `written`. Success only when `matched_rows == base_rows AND invalid_rows == 0`. Missing keys and invalid-field rows → `incomplete`; caller contract documented: never mark EOD success or advance frontier on `incomplete`. |
| idempotent retry only checked version tag | Idempotence now requires done==base AND `_validity_report` clean (state ∈ {0,1,2,3}, flags non-null, rule_id non-empty). Partial/invalid under same version → rewrite pass, never a false `idempotent`. |
| version consistency | Grouped read covers `<NULL>` versions, foreign versions (conflict → blocked), and expected version. |
| empty / invalid states → READY | Empty table → BLOCKED. badst/badflag/badrule > 0 → BLOCKED. Mixed versions → DEGRADED. Partial coverage → DEGRADED. |
| computed count vs actual writes | `matched_rows`/`state_dist` re-SELECTed from the table after write; `computed_keys` reported separately and never used as the success count. |

## P0-2 — fault-injection drill

Old timeout test fired on a date with no base rows — proved nothing.
New `EOD_FAILURE_DRILLS.json` (all PASS):

- 2026-10-23 now carries copied base rows; `statement_timeout=1ms`
  aborts mid-UPDATE → rollback → pre/post checksums identical → retry
  completes `written`.
- Partial coverage (40 rows NULL-version) + 10 corrupted rows
  (state=3+NULL flags+empty rule) under the version → re-emit heals to
  100% valid coverage; never false-reports success.
- `RULE_UNKNOWN`/`DATA_INSUFFICIENT` rows are never coerced to
  non-limit booleans (`unknown_fail_closed`).

## P0-3 — financial version chain

`financial_version_store` rewritten:

- Event identity = `version_event_id` / `(key, version_seq)` —
  fingerprint is only a change detector. A→B→A yields 3 events.
- `finver_observation` table holds every sighting
  (raw_payload_id/hash/seen_at/change_class); committed events are
  immutable — repeat fetches never touch event rows (D7).
- `finver_key_chain` tracks n_versions + head pointer under a
  transaction-scoped advisory lock — concurrent same-key ingests
  serialize; no seq collisions or orphan events (event+chain in the
  same txn).
- `read_as_of` documented: `first_seen_at` = platform observation time,
  never market first-publication.

## P0-4 — evidence grades

`financial_pit_at`: `restated_selected` → INFERRED (earliest-surviving
≠ proven initial). `historical_version_missing` → UNKNOWN.
`verified_public` status now carries INFERRED or UNKNOWN — nothing in
the statement tables alone can produce VERIFIED.

## Verification

- `pytest tests/test_r3_m1.py tests/test_financial_pit_p2.py`
  → 47 passed / 0 failed
- `m1_v2_write_drills.py` → 10/10 PASS (`EOD_FAILURE_DRILLS.json`)
- `m1_finver_drills.py` → 7/7 PASS (`FINVER_EVENT_CHAIN_TESTS.json`),
  real multi-version chains re-reproduced
- `INTEGRITY_GATE_RECHECK.json`: prod default DEGRADED /
  prod require_v2 BLOCKED / shadow require_v2 tradeability V2_READY

Boundaries kept: zero production writes/DDL, no EOD wiring, canonical
and P1d.3 worktrees untouched, no merge to main.
