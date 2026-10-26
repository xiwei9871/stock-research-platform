# Deploy Record — EOD Dependency Wait-Gate Hotfix

Status: **DEPLOYED_PENDING_LIVE_VERIFICATION**
Deployed: 2026-10-26 ~16:12 (Asia/Shanghai)
Decision: user-approved minimal-change deploy ahead of 2026-10-27 first real run.

## What was deployed

Canonical checkout `/Users/xiwei/stock_research` switched to branch
`hotfix/eod-dependency-wait-gate` @ `9cd9e2c1`.

Diff vs previous canonical HEAD (`34de8b0d`):

| File | Change |
|---|---|
| `src/stock_research/strategy_daily_eod.py` | + `strategy_daily_eod_dependency_probe_exit_code` + `WAITABLE_DEPENDENCY_REASON_MARKERS` |
| `scripts/run_strategy_daily_eod_cron.sh` | probe calls the new classifier (rc 0/3/4) |
| `tests/test_strategy_daily_eod.py` | +9 probe/check tests |

No LaunchAgent changes, no data changes, no deletions. The 34de8b0d score-row
check was already in the canonical history; this hotfix adds only the probe
semantics that let it actually engage.

## Discovered pre-deploy state (differs from prior assumptions)

- Canonical worktree was moved to `data/p1d3-v2-migration` at 16:02 today
  (created from HEAD@34de8b0d). That branch was restored to `34de8b0d`
  untouched; uncommitted p1d3-v2 work (`core_data.py` mod + drill scripts)
  preserved in the worktree.
- `main` is 49 commits behind; the production-running lineage is the
  `fix/p1d3-production-preflight` family (`425041b5` + `34de8b0d`).

## Root cause recap

Cron probe only kept waiting while the sole failure reason was
`missing daily_pipeline_status` (rc=3). The new `score_topn missing` failure
exited rc=4 → `probe_stop` → CLI ran → base check failed. Fix: rc=3 iff every
`;`-separated failure is waitable; any real failure → rc=4 → CLI reports it.
Wait budget unchanged (240min); scores land ~21:06-21:15 → covered.

## Dashboard sync race — verdict: no change needed

`deploy/validate_strategy_release.py` already enforces a publish-completion
contract before any rsync (summary trade_date, publishable, review_rows=15,
manifest modules, score_audit=success, 5-row ranked CSVs). On 2026-10-23 the
remote release matched local byte-for-byte (spot-checked summary + trades CSV:
identical size/mtime). Residual: on-disk fallback can ship the last complete
date — designed last-good behavior, always a *consistent* snapshot. Post-EOD
artifact sync (`sync_dashboard_artifacts.sh`, triggered by the cron itself) is
the second layer.

## Verification done

- `pytest tests/test_strategy_daily_eod.py` — 61 passed; with
  `test_daily_close_pipeline.py` — 126 passed.
- Live read-only probe on production checkout:
  `2026-10-23` → rc=0 (ready); `2026-10-26` (status row absent) → rc=3 (waits).
- `launchctl list`: 4 agents intact
  (dashboard-daily-sync, strategy-eod-publish, platform-ready-check,
  tdx-auction-backfill-watchdog).

## Rollback

```
cd /Users/xiwei/stock_research && git checkout 34de8b0d
```

## Pending

- 2026-10-27 first real timed run: verify 20:30 EOD publishes on dependency
  readiness (not via ~22:17 repair fallback), then Ready Check + 22:15 sync
  read the same-day result.
- P2 PDF batches: remote-copy audit only, no deletion.
