# P6 Current Verification

Date: 2026-08-04

## Outcome

The P6 dashboard workbench baseline is verified for its read-only scope. The
remaining full-suite failures are environmental or outside P6; they are recorded
explicitly instead of being treated as dashboard failures.

## Baseline

- Branch: `dashboard-workbench`
- Worktree: `.worktrees/dashboard-workbench`
- HEAD before this verification: `8939c8ca docs: add p6 completion review`
- The branch is an ancestor of both `factor-scoring-daily-pipeline` and
  `fix/review-queue-runtime-consistency`; no blind merge into a dirty worktree was
  performed.

## P6-1: Backend And Dependency Boundary

- Dashboard package remains a read-only FastAPI surface.
- Read models use daily/minute bars, factor scores, watchlist signals, and local
  report links only.
- No broker, order, account, cash, execution, scheduler-install, or notification
  live-send path is present in the dashboard package.
- Fixed the invalid development dependency spelling: `httpx2` -> `httpx`.
- Added a dependency contract test in `tests/test_dashboard_dependencies.py`.
- Editable install dry-run succeeds for `.[dashboard,dev]`.

## P6-2: Frontend Workbench

Fresh official-worktree results:

```text
pnpm test       13 passed
pnpm build      succeeded
pnpm test:e2e   2 passed
```

The UI remains a chart-centered research workbench with TopN, watchlist, score,
signal, and report inspection. It does not expose order or broker controls.

## P6-3/P6-4: Operational And Mainline Integration

- P4/P5 scheduler and notification tests remain green on the P6 baseline.
- CLI parser/dispatch tests for dashboard, P4, P5, and factor commands pass.
- Generated dashboard output directories remain untracked/ignored.
- P4/P5 execution and notification ownership remains outside the dashboard.

## P6-5: Fresh Verification

Targeted backend/CLI/P4/P5 suite, including the new dependency contract:

```text
187 passed, 2 warnings
```

Full Python regression from the official dashboard worktree:

```text
1252 passed, 6 failed, 2 warnings
```

The six failures are not P6 dashboard regressions:

1. Four minute-backfill tests are blocked by the external BaoStock response
   `10001011 黑名单用户，请与管理员联系`.
2. Two watchdog tests require `/Users/xiwei/.openclaw/cron/jobs.json`, which is
   absent in this environment.

Therefore P6 implementation verification is green for its scoped tests, while
the global regression gate is explicitly **blocked by external/pre-existing
environment conditions**.

## Merge Decision

P6 is implementation-complete and reviewable. The dependency hardening and this
verification record are ready to carry into the current integration branch. A
full-suite-green claim must wait until the BaoStock blacklist condition and the
missing cron fixture are resolved independently.
