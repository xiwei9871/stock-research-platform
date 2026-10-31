# Decision register

Statuses: PROPOSED / ACTIVE / SUPERSEDED / REJECTED.
A request contradicting an ACTIVE entry must be reported and blocked
from silent implementation.

| ID | Date | Decision | Rejected alternatives | Evidence | Status |
| --- | --- | --- | --- | --- | --- |
| D01 | 2026-09-17 | `~/stock_research` on `main` is the single canonical checkout; all cron/launchd jobs point here | parallel release/runtime checkouts | AGENTS.md Canonical Layout | **ACTIVE** |
| D02 | 2026-10-15 | Internal dashboard retired; launchd api/frontend jobs booted out, plists in `.disabled/` | running stale internal dashboard | AGENTS.md | **ACTIVE** |
| D03 | always | Baostock minute5 fetch is single-worker (`max_workers_baostock_minute5=1`); one sequential baostock session host-wide | parallel baostock logins (10002007 / blacklist 10001011 incidents) | AGENTS.md Data Source Constraints | **ACTIVE** |
| D04 | always | Protected `outputs/research/*` runtime inputs must never be deleted (gitignored but production-critical) | disk cleanup touching them | AGENTS.md Untracked-Inputs | **ACTIVE** |
| D05 | always | Long-run cron wrappers emit sparse stdout heartbeats on script-global elapsed (~600s) | per-step silence (OpenClaw kill incident) | AGENTS.md stdout contract | **ACTIVE** |
| D06 | 2026-10-21 | Baostock evening settlement window ~17:00–19:00 rejects logins; retry-window helpers required, no retry storms | tight login loops | AGENTS.md | **ACTIVE** |
| D07 | this rollout | No prod deploy/rsync, service restarts, DB writes, or financial-model edits without explicit approval | "tests pass = deploy ok" | Issue #1 scope | **ACTIVE** |

Superseded history: internal dashboard (D02 superseded 2026-10-15).
