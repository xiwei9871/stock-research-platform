# EOD Runtime Recovery — 2026-11-02

Status: **PREPARED** — environment restored, smoke checks pass, controlled EOD run executed.
Final live acceptance = actual 2026-11-02 launchd schedule evidence.

## Root cause (verified on host, not assumed)

| Report | Evidence | Verdict |
|---|---|---|
| `.venv` deleted | `ls .venv` → absent; cron logs `No such file or directory` for `.venv/bin/python` | CONFIRMED |
| EOD `ImportError: tabulate` (pre-deletion) | `tabulate` imported but undeclared in `pyproject.toml` | CONFIRMED |
| `tushare` missing | `stock_research.cli` → `auction_data` → `ModuleNotFoundError: tushare` (also undeclared) | CONFIRMED (new finding) |
| `/Users/xiwei/watchdog` sibling src deleted | `backfill_watchdog.py` hard-requires `watchdog_runner.backfill`; dir absent | CONFIRMED (new finding) |
| TDX host script missing | script exists in repo on main; earlier 127 errors were from the absent env period / branch drift | RESOLVED by checkout |
| canonical off main | canonical sat on `chore/project-continuity-v101 @ e1ea72dd` (1 local commit, already pushed) | CONFIRMED |
| dashboard sync blocked | sync refuses dirty release root (`?? scripts/mem_watchdog.sh`) | CONFIRMED |

Last successful EOD publish: **2026-10-29**. 10-30/10-31 failed (interpreter missing).

## Fixes applied (branch `fix/eod-runtime-recovery-20261102`, base = `origin/main @ 9bd95562`)

1. Rebuilt `.venv` from `pyproject.toml` (`python3.14 -m venv` + `pip install -e .[dev,dashboard]`).
2. Declared missing runtime deps: `tabulate`, `tushare` added to `pyproject.toml`.
3. Restored `/Users/xiwei/watchdog` → symlink to `/Users/xiwei/gov-rollout/watchdog`
   (`src/watchdog_runner` exists there). `should_send_watchdog_message` absent in
   that build → local compat fallback in `backfill_watchdog.py` (notify unless
   `watchdog_action == "healthy"`).
4. canonical switched to this fix branch = `origin/main` + recovery commits
   (`9bd95562` + ops fixes). Local commit `e1ea72dd` is already pushed to
   `origin/chore/project-continuity-v101` — no work lost. Safety ref:
   `safety/canonical-pre-switch-20261101`.
5. `scripts/mem_watchdog.sh` committed (was untracked but required by the
   running `com.stockresearch.mem-watchdog` launchd job; untracked state was
   what tripped the sync dirty-root refusal).
6. New `scripts/ops_job_guard.sh` — minimal runtime protection, wired into all
   four wrappers: interpreter+import+SHA preflight; status JSON per job under
   `logs/ops/`; first failure → `ALERT_<job>_WARN`; ≥2 consecutive failures →
   `ALERT_<job>_CRITICAL`; success records `last_success_date` + artifact and
   clears alerts. No external notification channel connected (documented gap).

## Verification evidence

- Preflight OK ×4 (strategy-eod-publish, platform-ready-check,
  tdx-auction-backfill-watchdog, dashboard-release-sync) at sha `9bd95562`.
- Import probe: `stock_research.cli` OK; pandas/psycopg/tabulate/tushare/
  fastapi/uvicorn/baostock/akshare/eltdx OK (59 pkgs).
- Alert simulation (isolated `OPS_GUARD_STATE_DIR`): WARN→CRITICAL escalation
  and success-clear verified.
- Controlled EOD: `TRADE_DATE=2026-10-30 run_strategy_daily_eod_cron.sh` —
  preflight OK; fills the missing 10-30 artifact dir (no overwrite;
  `strategy_daily_eod/2026-10-30` did not exist). See
  `logs/cron/strategy_daily_eod_2026-10-30_*.log`.
- Dirty-root refusal cleared: worktree clean after committing mem_watchdog.

## Job status

| Job | Executor | Deps | Config | Controlled run |
|---|---|---|---|---|
| strategy-eod-publish | OK | OK | OK | ran 10-30 backfill (see log) |
| platform-ready-check | OK | OK | OK | preflight OK; full run = scheduled |
| tdx-auction-backfill-watchdog | OK | OK | OK | preflight OK; live run touches remote hosts — deferred |
| dashboard_release_sync | OK | OK | OK | preflight OK; full sync is a prod deploy — NOT run |

## Rollback

- Canonical restore: `git checkout chore/project-continuity-v101`
  (safety ref `safety/canonical-pre-switch-20261101` = e1ea72dd, also on origin).
- Guard is additive: removing the `source`/`ops_preflight`/`trap` lines in the
  four wrappers restores prior behavior.

## Outstanding / needs human decision

- Canonical currently runs the **fix branch** (= main + recovery commits) so
  tonight's jobs get the guard. After PR merge: `git checkout main && git pull`.
- External dashboard latest publish date: NOT_VERIFIED (sync is a prod deploy;
  not executed without authorization).
- External alerting (Feishu/email): NOT CONNECTED — local `logs/ops/ALERT_*`
  files + JSON state only.
- `should_send_watchdog_message` fallback semantics reconstructed
  (notify-on-non-healthy); original implementation was in the deleted
  `/Users/xiwei/watchdog` copy — if it differed, notify cadence may differ.
- 2026-11-02 schedule evidence = final acceptance.
