# Rolling sector oversold replay validation

Date: 2026-08-01  
Window: 2026-07-21 through 2026-07-31  
Strategy: `rolling_oversold_v1`  
Adjust type: `qfq`  
Requested limits: sector top 30, stock top 20, runtime budget 3,600 seconds

## Acceptance tests and static checks

The acceptance fixture freezes loader frames at each anchor and asserts that
feature construction never sees a bar after that anchor. It also checks that
sector rows retain an explicit gate status and that a fifth-horizon outcome is
pending before five future sessions are available.

Commands and results:

```text
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_rolling_oversold_acceptance.py -q
2 passed

rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_rolling_oversold_acceptance.py \
  tests/test_rolling_oversold_pipeline.py \
  tests/test_rolling_oversold_cli.py -q
24 passed, 2 warnings

rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_pipeline.py \
  tests/test_consumer_oversold_v2_evaluation.py -q
103 passed, 2 warnings, 61.03s

rtk /Users/xiwei/stock_research/.venv/bin/python -m compileall -q \
  src/stock_research/rolling_oversold tests/test_rolling_oversold_acceptance.py
exit 0
```

The static import check found no `akshare` or `baostock` import in the rolling
pipeline. A regression found by the selected tests was fixed before this
record was finalized: a missing `anchor_close` column was converted to a
scalar `NaN` instead of an index-aligned series, causing `.loc` to fail during
price freezing.

## Database availability and frozen window

The requested command used `--service research`, but that PostgreSQL service
is not defined on this host:

```text
psycopg.OperationalError: connection is bad: definition of service "research" not found
```

The configured database service `stock_research` is reachable. Read-only
diagnostics returned:

| Dataset/check | Result |
| --- | --- |
| qfq `market_daily_bar` latest date | 2026-07-31 |
| distinct open sessions in window | 9: 07-21, 07-22, 07-23, 07-24, 07-27, 07-28, 07-29, 07-30, 07-31 |
| qfq bars in window | 46,749 rows / 5,200 assets |
| industry bars in window | 680 rows / 85 sectors |
| concept bars in window | 3,366 rows / 374 sectors |
| asset status rows in window | 41,552 rows / 5,200 assets |
| active industry membership at 2026-07-31 | 5,533 assets / 106 sector identities |
| active concept membership at 2026-07-31 | 5,558 assets / 1,219 sector identities |

The trading calendar contains two rows per open date in this window; the
replay query uses `SELECT DISTINCT trade_date`, so the nine-session list above
is the effective anchor set.

For the intended replay, the data cutoff for each successful anchor would be
the anchor itself:

| Anchor | Expected database cutoff |
| --- | --- |
| 2026-07-21 | 2026-07-21 |
| 2026-07-22 | 2026-07-22 |
| 2026-07-23 | 2026-07-23 |
| 2026-07-24 | 2026-07-24 |
| 2026-07-27 | 2026-07-27 |
| 2026-07-28 | 2026-07-28 |
| 2026-07-29 | 2026-07-29 |
| 2026-07-30 | 2026-07-30 |
| 2026-07-31 | 2026-07-31 |

These cutoff values are database diagnostics and not a claim that the live
replay produced immutable snapshots.

## Live replay attempt

The exact plan command was first run with `--service research` and failed
immediately because the service alias is missing. It was then retried against
the reachable `stock_research` service:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-replay \
  --anchor-start-date 2026-07-21 \
  --anchor-end-date 2026-07-31 \
  --output-dir artifacts/rolling_sector_oversold/replay_2026-07-21_2026-07-31_stock_research \
  --service stock_research \
  --sector-top-n 30 \
  --stock-top-n 20 \
  --score-version rolling_oversold_v1 \
  --adjust-type qfq
```

The process was allowed to run for approximately 6 minutes 58 seconds. It
emitted no anchor progress, no stage timing, no error, and created no output
artifact before it was safely interrupted (`exit 130`). Therefore this record
contains no fabricated snapshot, sector score, candidate, outcome, gap, or
7/30 focus result.

## Required validation fields

Because the live replay did not publish an anchor, the following fields remain
unavailable and must be filled by the next successful run:

| Field | Status |
| --- | --- |
| Immutable snapshot count | not produced |
| Per-anchor stage timings | not produced |
| Preflight coverage and `backfill_requests.csv` | not produced |
| Sector rows with gate/recovery status | not produced by live run (fixture verified the contract) |
| Completed/pending 1/3/5-day outcomes | not produced by live run (fixture verified delayed 5-day status) |
| 2026-07-30 technology-vs-consumer focus report | not produced |
| 3,600-second runtime target | not met/ not measurable: replay was interrupted before completion |

The 2026-07-30 focus command remains the follow-up once an immutable
`anchor=2026-07-30/version=rolling_oversold_v1` directory exists:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-report \
  --snapshot-dir artifacts/rolling_sector_oversold/replay_2026-07-21_2026-07-31/anchor=2026-07-30/version=rolling_oversold_v1 \
  --focus-patterns '芯片,半导体,CPO,算力,科技,消费' \
  --output-dir artifacts/rolling_sector_oversold/validation_2026-07-30
```

## Blocker and next run requirements

1. Add a `research` entry in `~/.pg_service.conf`, or explicitly standardize
   the operational command on the existing `stock_research` service.
2. Investigate the six-minute no-output run before claiming the 60-minute
   target. The current loader reads a very large `market_daily_bar` history
   frame for each anchor; the next run should add stage/anchor heartbeat output
   and measure query timings. If the full window remains slow, run a bounded
   diagnostic anchor first and optimize database filtering/index coverage
   before rerunning all nine anchors.
3. Keep strategy execution database-only. A missing dependency must produce
   the existing preflight/backfill artifacts and a separate backfill task; it
   must never trigger a network market-data fallback.

Until those blockers are cleared, this document is an acceptance-test and data
availability record, not a successful historical replay claim.
