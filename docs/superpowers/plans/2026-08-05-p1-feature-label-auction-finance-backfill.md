# P1 data-completeness backfill plan — 2026-08-05

## Scope

Continue the previously audited P1 items through the existing cutoff of 2026-08-03. Do not include the 2026-08-04 current-day issue. Preserve existing data and use the repository's idempotent backfill commands.

## Execution order

1. **Auction bars**
   - Backfill missing `open_call` and `close_call` dates after the current coverage boundary.
   - Verify per-date row coverage, nulls, and latest date.
2. **Daily feature snapshots**
   - Backfill `feature_snapshot` through the cutoff with the existing P0 feature command.
   - Verify dates, asset coverage, and duplicate keys.
3. **Forward labels**
   - Derive only through the latest date for which the requested forward horizons have source bars.
   - Verify each horizon's latest date and duplicate/null keys.
4. **Daily technical features**
   - Use the gap checker first, then backfill missing `hfq` dates in bounded windows.
   - Verify gap counts and key uniqueness.
5. **5-minute qfq intraday features**
   - Backfill dates after the existing qfq boundary through 2026-08-03, subject to minute-bar availability.
   - Verify per-date coverage and source-date alignment.
6. **Finance three-statement gaps**
   - Recompute the exact missing balance/cash-flow joins.
   - Use an existing source/loader for targeted periods if available; otherwise report the precise blocker without fabricating rows.

## Checkpoints

- Every mutating command must be followed by a fresh SQL/CLI verification.
- No completion claim is made for a component until its post-write verification passes.
- Any source/rate-limit blocker is recorded with the exact remaining gap.
