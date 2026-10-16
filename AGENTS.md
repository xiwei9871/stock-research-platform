# Project Guidance For Codex

Keep context lean. Do not scan the whole repository unless the task requires it.
Use `rtk` for noisy shell commands when compressed output is sufficient.
Prefer targeted reads over full-file reads.

## Repo Map
- `src/stock_research/`: Python application and CLI code
- `tests/`: pytest suite for backend, scripts, and dashboard APIs
- `dashboard/`: Vite/React frontend with `pnpm`
- `scripts/`: cron wrappers, watchdogs, and batch utilities
- `docs/`: runbooks, design notes, and task-specific references
- `config/`: runtime configuration inputs

## Common Checks
- backend tests: `.venv/bin/pytest`
- focused backend test: `.venv/bin/pytest tests/test_<name>.py -q`
- dashboard tests: `cd dashboard && pnpm test`
- dashboard build: `cd dashboard && pnpm build`

## Token Discipline
- Prefer `rtk git status`, `rtk git diff`, `rtk git show`, `rtk rg`, `rtk pytest`, `rtk pnpm test`, and `rtk docker logs`.
- Use raw commands only when exact uncompressed output matters.
- Summarize failures instead of pasting large logs.

## Done Means
- Changes stay within the requested scope.
- Relevant tests or builds are run, or blockers are reported precisely.
- Summaries cite modified files and verification commands.

## Canonical Layout (2026-09-17 consolidation)
- `/Users/xiwei/stock_research` on branch `main` is the single canonical checkout.
  All crontab and launchd jobs point here. Do not create or use parallel
  release/runtime checkouts for scheduled work.
- `main` was rebased onto `release/theme-research-reports-20260801` (2944a750),
  the commit that actually ran production, and force-pushed to origin on
  2026-09-17. The pre-consolidation remote history is preserved at
  `backup/main-pre-consolidation-20260917`.
- Historical checkouts live under `/Users/xiwei/stock_research_archive/`
  (still registered git worktrees; branches preserved).
- Internal dashboard: retired 2026-10-15. The launchd jobs
  `com.stockresearch.dashboard-local-api` (127.0.0.1:8765) and
  `dashboard-local-frontend` (5174) were booted out and their plists moved to
  `~/Library/LaunchAgents/.disabled/`. Cache-clear URLs are optional now:
  `DASHBOARD_CACHE_CLEAR_URL` empty → skipped (finalize + eod_auto_repair).
- External site https://stock.manqiaotechnology.com runs on stock-prod
  (192.168.3.185) as docker compose project `stock_research_dashboard`,
  querying the same Postgres at 192.168.3.187.

## External Sync
- `deploy/sync_dashboard_release.sh` (launchd 22:15): full deploy — code,
  frontend build, all `outputs/research/strategy_daily_eod/` artifacts,
  `reports/`, docling artifacts, remote docker rebuild, release gate.
- `deploy/sync_dashboard_artifacts.sh`: artifact-only mirror + external
  review-queue verification. Triggered automatically on success by
  `scripts/run_strategy_daily_eod_cron.sh` and `run_eod_auto_repair_cron.sh`;
  safe to run manually.
- Manifest `artifact_path` may carry either local (`/Users/xiwei/...`) or
  container (`/app/...`) roots; both are trusted in
  `dashboard/review_queue.py` `LEGACY_STRATEGY_OUTPUT_ROOTS`.

## Data Source Constraints
- Baostock minute5 fetch is single-worker only: `max_workers_baostock_minute5`
  stays `1` and `build_retry_failed_source_plan` must keep planning baostock
  sources with `workers=1`. Do not parallelize baostock sessions — concurrent
  logins/fetches cause `10002007` connection failures. Prefer one sequential
  baostock downloader at a time host-wide.
- Baostock rejects logins in its evening settlement window (~17:00-19:00
  observed). `run_minute5_stage` and `run_retry_failed_stage` absorb this via
  `login_baostock_with_retry_window`: retryable refusals sleep
  `MINUTE5_BAOSTOCK_LOGIN_RETRY_SECONDS` (default 600) until
  `MINUTE5_BAOSTOCK_LOGIN_MAX_WAIT_SECONDS` (default 10800) elapses, then fail.
  Non-retryable login errors still fail fast.
- The finalize cron shortens that window for `retry_failed` via
  `FINALIZE_RETRY_FAILED_BAOSTOCK_WAIT_SECONDS` (default 900): the 21:00 pass
  is a fast attempt only — the 22:00 repair job (180min budget) carries the
  real repair on bad baostock nights.
