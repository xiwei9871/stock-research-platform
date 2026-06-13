# Worktree Cleanup Audit - 2026-06-13

## Scope

This audit records the dirty worktree state before Phase 6 search relevance work.
It is intentionally read-only: no source files were reverted, staged, or
modified as part of this audit.

Current branch: `dashboard`

Current notable committed work after Phase 5:

- `911cbbf docs: add news quality gate v1 design`
- `e1dec5a docs: clarify news quality gate retention`
- `4c2bc9e docs: add news quality gate implementation plan`

The worktree still contains unrelated uncommitted changes from earlier feature
threads. Phase 6 should not start implementation until these are either
committed in coherent groups or intentionally left isolated.

## Dirty File Groups

### Group A: EOD Market Monitor And Emotion Dashboard

Files:

- `src/stock_research/dashboard/market_monitor.py`
- `tests/test_dashboard_market_monitor.py`
- `tests/test_dashboard_app.py`
- `dashboard/src/components/MarketMonitorWorkspace.tsx`
- `dashboard/tests/app-shell.test.tsx`
- `dashboard/tests/home-cockpit.test.tsx`
- `dashboard/src/api/types.ts`
- `dashboard/src/styles.css`

Observed intent:

- Add historical trade-date loading to Market Monitor.
- Add EOD market emotion payload and UI sections.
- Add stock lists for auction, limit-up, broken-limit-up, and limit-down tabs.
- Add keyboard navigation for market monitor stock tabs.
- Add defensive rendering for partial EOD payloads.

Risk:

- This group overlaps with shared dashboard types, AppShell tests, and global
  CSS. It should be committed before Phase 6 UI work or kept carefully
  unstaged during Phase 6.

Recommended validation before commit:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_market_monitor.py \
  tests/test_dashboard_app.py::test_market_monitor_eod_route_returns_payload -q

cd dashboard
npm test -- --run tests/app-shell.test.tsx tests/home-cockpit.test.tsx
```

Recommended commit:

```bash
git add \
  src/stock_research/dashboard/market_monitor.py \
  tests/test_dashboard_market_monitor.py \
  tests/test_dashboard_app.py \
  dashboard/src/components/MarketMonitorWorkspace.tsx \
  dashboard/tests/app-shell.test.tsx \
  dashboard/tests/home-cockpit.test.tsx \
  dashboard/src/api/types.ts \
  dashboard/src/styles.css
git commit -m "feat: add eod market emotion monitor"
```

Only use the above after reviewing staged diff, because `types.ts`,
`app-shell.test.tsx`, and `styles.css` also overlap with other threads.

### Group B: Backtest Lab And Result UX

Files:

- `src/stock_research/dashboard/backtests.py`
- `src/stock_research/vectorized_topn_backtest.py`
- `tests/test_dashboard_backtests.py`
- `tests/test_vectorized_topn_backtest.py`
- `dashboard/src/components/BacktestCharts.tsx`
- `dashboard/src/components/BacktestLabWorkspace.tsx`
- `dashboard/src/components/BacktestResultDetail.tsx`
- `dashboard/tests/backtest-lab-workspace.test.tsx`
- `dashboard/tests/client.test.ts`
- `dashboard/src/api/types.ts`
- `dashboard/src/styles.css`

Observed intent:

- Route default backtest runs through fresh calculation.
- Add richer backtest run parameters.
- Improve result details and chart tooltip/legend behavior.
- Relax result summary typing to support nested values.

Risk:

- This group changes API request/response types and shared client behavior.
- It should be reviewed independently from Market Monitor because both touch
  `dashboard/src/api/types.ts` and `dashboard/src/styles.css`.

Recommended validation before commit:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_backtests.py \
  tests/test_vectorized_topn_backtest.py -q

cd dashboard
npm test -- --run tests/client.test.ts tests/backtest-lab-workspace.test.tsx
npm run build
```

Recommended commit:

```bash
git add \
  src/stock_research/dashboard/backtests.py \
  src/stock_research/vectorized_topn_backtest.py \
  tests/test_dashboard_backtests.py \
  tests/test_vectorized_topn_backtest.py \
  dashboard/src/components/BacktestCharts.tsx \
  dashboard/src/components/BacktestLabWorkspace.tsx \
  dashboard/src/components/BacktestResultDetail.tsx \
  dashboard/tests/backtest-lab-workspace.test.tsx \
  dashboard/tests/client.test.ts \
  dashboard/src/api/types.ts \
  dashboard/src/styles.css
git commit -m "feat: improve backtest lab results"
```

Use patch staging if Market Monitor type/style changes are still unstaged.

### Group C: Strategy Catalog And Combo Strategies

Files:

- `src/stock_research/dashboard/strategy_catalog.py`
- `tests/test_dashboard_strategy_catalog.py`
- `src/stock_research/lhb_data.py`
- `src/stock_research/lhb_shortline_v1.py` (untracked)
- `src/stock_research/mid_trend_v1.py` (untracked)
- `src/stock_research/tech_bottleneck_v1.py` (untracked)
- `tests/test_lhb_shortline_v1.py` (untracked)
- `tests/test_mid_trend_v1.py` (untracked)
- `tests/test_tech_bottleneck_v1.py` (untracked)

Observed intent:

- Add or update runnable shortline and combo strategy modules.
- Expand LHB data/replay logic.
- Update strategy catalog evidence and default parameters.

Risk:

- `src/stock_research/lhb_data.py` has a very large diff and should not be
  mixed with dashboard UI work.
- The untracked strategy files look like complete feature files and should be
  reviewed as a dedicated strategy package.

Recommended validation before commit:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_lhb_shortline_v1.py \
  tests/test_mid_trend_v1.py \
  tests/test_tech_bottleneck_v1.py \
  tests/test_dashboard_strategy_catalog.py -q
```

Recommended commit:

```bash
git add \
  src/stock_research/dashboard/strategy_catalog.py \
  tests/test_dashboard_strategy_catalog.py \
  src/stock_research/lhb_data.py \
  src/stock_research/lhb_shortline_v1.py \
  src/stock_research/mid_trend_v1.py \
  src/stock_research/tech_bottleneck_v1.py \
  tests/test_lhb_shortline_v1.py \
  tests/test_mid_trend_v1.py \
  tests/test_tech_bottleneck_v1.py
git commit -m "feat: add combo strategy modules"
```

### Group D: News Quality Gate V1

Files:

- `docs/superpowers/specs/2026-06-13-news-quality-gate-v1-design.md`
- `docs/superpowers/plans/2026-06-13-news-quality-gate-v1.md`
- `src/stock_research/lhb_data.py`
- `tests/test_dashboard_news.py`

Observed intent:

- The design and implementation plan are already committed.
- `tests/test_dashboard_news.py` and `src/stock_research/lhb_data.py` have
  uncommitted changes. The `lhb_data.py` overlap makes this group ambiguous;
  inspect before assuming it belongs to news quality gate.

Risk:

- News quality work should not share a commit with LHB strategy internals unless
  the diff proves there is a direct dependency.

Recommended validation before commit:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_news.py -q
```

Recommended action:

- Inspect `tests/test_dashboard_news.py` diff first.
- If the change is truly news-quality specific, split it out with patch staging.
- Leave `lhb_data.py` for Group C unless a specific news-quality hunk is found.

### Group E: Legacy Plan Documents

Untracked files:

- `docs/superpowers/plans/2026-06-10-db-backed-combo-replay.md`
- `docs/superpowers/plans/2026-06-10-default-combo-backtests.md`
- `docs/superpowers/plans/2026-06-10-fresh-backtest-and-readable-results.md`
- `docs/superpowers/plans/2026-06-11-lhb-shortline-v1.md`
- `docs/superpowers/plans/2026-06-12-eod-market-emotion-dashboard-v1.md`

Observed intent:

- Historical implementation plans for work that is partially present in the
  dirty tree.

Recommended action:

Commit these as documentation before feature code if they are still relevant:

```bash
git add docs/superpowers/plans/2026-06-10-db-backed-combo-replay.md \
  docs/superpowers/plans/2026-06-10-default-combo-backtests.md \
  docs/superpowers/plans/2026-06-10-fresh-backtest-and-readable-results.md \
  docs/superpowers/plans/2026-06-11-lhb-shortline-v1.md \
  docs/superpowers/plans/2026-06-12-eod-market-emotion-dashboard-v1.md
git commit -m "docs: add historical implementation plans"
```

## Recommended Cleanup Order

1. Commit legacy plan documents if they are still useful.
2. Commit Market Monitor/EOD emotion as one reviewed slice.
3. Commit Backtest Lab improvements as one reviewed slice.
4. Commit Strategy Catalog and combo strategy modules as one reviewed slice.
5. Split or defer any news-quality code hunks after inspecting whether they are
   independent from LHB strategy internals.
6. Start Phase 6 implementation only after the shared files
   `dashboard/src/api/types.ts`, `dashboard/src/styles.css`, and
   `dashboard/tests/app-shell.test.tsx` are either clean or intentionally
   isolated with patch staging.

## Phase 6 Guardrails

- Do not use `git reset --hard` or checkout to clean this tree.
- Do not commit all dirty files together.
- Use patch staging for shared files.
- Before each cleanup commit, run the focused tests listed for that group.
- Keep Phase 6 search relevance changes separate from Market Monitor,
  Backtest, and Strategy changes.
