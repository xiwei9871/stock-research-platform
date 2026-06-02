# P6 Dashboard Mainline Integration Review

Date: 2026-05-30

## Status

P6-3/P6-4 mainline integration is complete on `dashboard-workbench`.

The branch was rebased onto the latest committed P5/P6 mainline:

- Mainline branch: `factor-scoring-daily-pipeline`
- Mainline head used for rebase: `c466dab docs: adjust p6 dashboard workbench plan`

## Rebase Result

Command:

```bash
git rebase factor-scoring-daily-pipeline
```

Result:

```text
Successfully rebased and updated refs/heads/dashboard-workbench.
```

No manual conflict resolution was required during rebase.

## CLI Integration

Post-rebase `src/stock_research/cli.py` includes:

- `dashboard-api`
- P4 scheduler commands
- Alpha191 pilot and expanded validation commands

The dashboard CLI addition remains narrow:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

The rebase did not remove Alpha191 command wiring.

## Integration Fix

One full-regression failure appeared after running the rebased branch from the
dashboard worktree:

```text
FileNotFoundError: [Errno 2] No such file or directory: '.venv/bin/python'
```

Root cause:

- `tests/test_p5_notify_script.py` hard-coded `.venv/bin/python`.
- The dashboard worktree does not contain its own `.venv`.
- The test should use the active pytest interpreter.

Fix:

- changed the subprocess interpreter to `sys.executable`.

This keeps the test portable across the main worktree and linked git worktrees.

## Verification

Dashboard backend and CLI targeted verification:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_*.py tests/test_factor_cli.py -q
```

Result:

```text
163 passed, 2 warnings
```

Frontend unit/build/e2e verification:

```bash
pnpm test && pnpm build && pnpm test:e2e
```

Result:

```text
Vitest: 13 passed
Vite build: built in 405ms
Playwright: 2 passed
```

P5 notify script targeted verification after integration fix:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_p5_notify_script.py -q
```

Result:

```text
2 passed
```

Full Python regression:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest -q
```

Result:

```text
1257 passed, 2 warnings
```

## Generated Artifact Check

No generated dashboard artifacts are tracked after build and e2e runs:

- `dashboard/dist/`
- `dashboard/test-results/`
- `dashboard/playwright-report/`
- `dashboard/node_modules/`

## Remaining P6 Items

Proceed to P6-5 completion review and merge decision.

Before merging into the main worktree, account for the main worktree's current
uncommitted files. They are outside this dashboard branch and were not touched by
the rebase:

- `src/stock_research/cli.py`
- `src/stock_research/strong_winner_miss_analysis.py`
- `tests/test_strong_winner_miss_analysis.py`

## Merge Recommendation

The rebased `dashboard-workbench` branch is integration-ready for P6 review.

Do not merge blindly into a dirty main worktree. Either commit/stash the unrelated
main-worktree changes first, or merge in a separate clean worktree.
