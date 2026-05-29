# P6 Dashboard Branch Review

Date: 2026-05-30

## Status

P6-1 branch review is complete for the current dashboard baseline.

Branch:

- `dashboard-workbench`

Reviewed commit:

- `3938cae docs: add dashboard workbench runbook`

Worktree:

- `.worktrees/dashboard-workbench`

## Decision

Keep `dashboard-workbench` as the P6 implementation baseline.

The branch remains aligned with the P6 product boundary:

- read-only research workbench
- FastAPI read-only dashboard API
- React + Vite frontend
- Lightweight Charts chart surface
- no broker integration
- no order placement
- no TradingView external service dependency

## Changed Surface

Backend:

- `src/stock_research/dashboard/api.py`
- `src/stock_research/dashboard/app.py`
- `src/stock_research/dashboard/bars.py`
- `src/stock_research/dashboard/overview.py`
- `src/stock_research/dashboard/reports.py`
- `src/stock_research/dashboard/schemas.py`
- `src/stock_research/dashboard/scores.py`
- `src/stock_research/dashboard/watchlist.py`

Frontend:

- `dashboard/`

Integration:

- `.gitignore`
- `README.md`
- `pyproject.toml`
- `src/stock_research/cli.py`
- `docs/dashboard-workbench-runbook.md`

## Read-Only Review

The dashboard backend reads from existing platform outputs:

- `market_daily_bar`
- `market.stock_minute_bar`
- `factor.stock_score_daily`
- `watchlist.watchlist_daily_signal`
- local `reports/` artifacts

The dashboard package does not add write paths for factor, watchlist, report,
scheduler, notification, broker, order, account, or execution state.

## Dependency Review

`pyproject.toml` currently includes:

- `fastapi`
- `uvicorn`
- `httpx2`

The `httpx2` item looked suspicious during P6 scope planning, but it is not a
current merge blocker in this environment:

- `fastapi.testclient` dashboard tests pass.
- `httpx2` is installed in the shared virtual environment.
- `pip install --dry-run -e ".[dashboard,dev]"` resolves with the current
  metadata.

Keep this item on the P6 merge checklist because dependency behavior can differ
after rebase or environment rebuild.

## Generated Artifact Policy

No generated dashboard artifacts are tracked by git from this review set:

- `dashboard/node_modules/`
- `dashboard/dist/`
- `dashboard/test-results/`
- `dashboard/playwright-report/`
- Python `__pycache__/`

The branch `.gitignore` includes dashboard generated artifact rules.

## Verification

Backend dashboard test set:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_*.py -q
```

Result:

```text
27 passed, 2 warnings
```

Dashboard keyword regression:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest -k dashboard -q
```

Result:

```text
28 passed, 1189 deselected, 2 warnings
```

Dependency metadata dry run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pip install --dry-run -e ".[dashboard,dev]"
```

Result:

```text
Would install stock-research-0.1.0
```

## Open P6 Items

Continue with P6-2 frontend hardening:

- run frontend unit tests
- run `pnpm build`
- run Playwright smoke
- verify empty/loading/error states in the browser

Continue with P6-4 later:

- rebase or merge onto the latest P5 mainline
- resolve `src/stock_research/cli.py` intentionally
- keep Alpha191 work separate unless explicitly merged by its owner

## Merge Recommendation

Do not merge yet.

The dashboard branch is suitable as the P6 baseline, but merge readiness still
depends on frontend verification, mainline rebase, CLI conflict handling, and
integrated regression evidence.
