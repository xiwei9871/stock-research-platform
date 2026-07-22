# Strategy Publication And Human UI Contract Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore one authoritative official-strategy publication flow, remove machine audit identifiers from human pages, close the seven current Real Playwright failures, and make EOD browser acceptance detect future publication drift.

**Architecture:** `list_backtest_strategies()` becomes the official enriched publication read model for strategy APIs. Review Queue consumes validated immutable publication artifacts and resolves controlled historical paths against `SETTINGS.output_root`. Technical identity stays in APIs and automated acceptance; rendered pages expose only human metrics, dates, holdings, and a plain-language health state.

**Tech Stack:** FastAPI, Python `pathlib`, pytest, React, TypeScript, Vitest, Playwright, pnpm.

---

## File Structure

- `src/stock_research/dashboard/app.py`: authoritative strategy and display-date routes.
- `src/stock_research/dashboard/review_queue.py`: immutable publication loading and path resolution.
- `dashboard/src/components/HomeCockpit.tsx`: human Home strategy cards.
- `dashboard/src/components/BacktestLabWorkspace.tsx`: human Strategy Lab summary.
- `dashboard/src/components/ReviewQueueWorkspace.tsx`: human review summary.
- `dashboard/src/components/market-monitor/*.tsx`: stable row identity.
- `dashboard/src/components/AppShell.tsx`: Theme Research navigation restoration.
- `dashboard/tests/e2e/fixtures/test.ts`: runtime failure classification.
- `dashboard/tests/e2e/assertions/consistency.ts`: visible-metric consistency.
- `dashboard/tests/e2e/real/authoritativeSnapshot.ts`: API-only identity convergence.
- `dashboard/tests/e2e/{real,eod}/`: complete publication and route acceptance.

### Task 1: Unify Strategy Catalog Publication State

**Files:**
- Modify: `tests/test_dashboard_app.py`
- Modify: `src/stock_research/dashboard/app.py:1714-1718`

- [ ] **Step 1: Write the failing API test**

```python
def test_strategy_catalog_uses_authoritative_publication_read_model(monkeypatch):
    items = [{
        "strategy_id": "lhb_shortline",
        "status": "runnable",
        "latest_metrics": {
            "performance_as_of_date": "2026-07-21",
            "total_return_pct": 79.43,
            "contract_id": "lhb:contract",
            "publish_id": "publish-lhb",
            "artifact_version": "strategy_artifact_v1",
            "contract_status": "success",
        },
    }]
    monkeypatch.setattr(dashboard_app, "list_backtest_strategies", lambda: items)
    response = TestClient(dashboard_app.create_app()).get("/api/strategies/catalog")
    assert response.status_code == 200
    assert response.json() == {"items": items}
```

- [ ] **Step 2: Verify RED**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_app.py::test_strategy_catalog_uses_authoritative_publication_read_model -q`

Expected: FAIL because the route calls the static `list_strategy_catalog()`.

- [ ] **Step 3: Implement the minimal route change**

```python
@app.get("/api/strategies/catalog")
def strategies_catalog():
    return {"items": list_backtest_strategies()}
```

- [ ] **Step 4: Verify GREEN**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_app.py tests/test_dashboard_backtests.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard_app.py src/stock_research/dashboard/app.py
git commit -m "fix: unify strategy catalog publication state"
```

### Task 2: Load Exact Immutable Review Publications

**Files:**
- Modify: `tests/test_dashboard_review_queue.py`
- Modify: `src/stock_research/dashboard/review_queue.py:13,466-505,767-783`

- [ ] **Step 1: Write failing trusted-path tests**

```python
def test_resolve_v1_output_path_maps_controlled_relative_path(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=output_root))
    resolved = review_queue._resolve_v1_strategy_output_path(
        "outputs/research/strategy_daily_eod/2026-07-21/strategy_runs/"
        "mid_trend/publish-1/review.csv"
    )
    assert resolved == output_root / (
        "research/strategy_daily_eod/2026-07-21/strategy_runs/"
        "mid_trend/publish-1/review.csv"
    )
```

Also reject `other/...`, `outputs/../...`, empty components, and backslashes.

- [ ] **Step 2: Write the exact-cohort loader test**

Monkeypatch `load_strategy_publication_manifests()` with three official manifests and make `load_latest_data_run_manifest()` fail if called. Assert the result contains exactly 4 LHB, 5 Mid Trend, and 5 Tech Bottleneck immutable rows with nonempty publication identity fields.

- [ ] **Step 3: Verify RED**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_review_queue.py -k "controlled_relative_path or exact_cohort" -q`

Expected: FAIL because relative paths use process CWD and the loader selects the latest unrelated run.

- [ ] **Step 4: Use the exact publication loader**

```python
from stock_research.data_run_manifest import load_strategy_publication_manifests

modules = list(load_strategy_publication_manifests(trade_date=trade_date))
```

Do not replace an invalid declared official publication with compatibility mirrors or database rows.

- [ ] **Step 5: Resolve only the configured historical root**

```python
if not declared.is_absolute():
    raw = str(value or "")
    parts = raw.split("/")
    if (
        "\\" in raw
        or any(part in {"", ".", ".."} for part in parts)
        or parts[0] != current_output_root.name
    ):
        return Path()
    declared = current_output_root.parent.joinpath(*parts)
```

Retain trusted-root, symlink, regular-file, layout, identity, and hash checks.

- [ ] **Step 6: Verify GREEN**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_review_queue.py tests/test_dashboard_default_display_dates.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_dashboard_review_queue.py src/stock_research/dashboard/review_queue.py
git commit -m "fix: load immutable strategy review publications"
```

### Task 3: Remove Technical Publication Fields From Human Pages

**Files:**
- Modify: `dashboard/tests/home-cockpit.test.tsx`
- Modify: `dashboard/tests/backtest-lab-workspace.test.tsx`
- Modify: `dashboard/tests/review-queue-workspace.test.tsx`
- Modify: `dashboard/src/components/HomeCockpit.tsx:1738-1762`
- Modify: `dashboard/src/components/BacktestLabWorkspace.tsx:480-525`
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx:395-430`

- [ ] **Step 1: Write failing human-contract tests**

```tsx
expect(screen.queryByText('正式合同')).not.toBeInTheDocument();
expect(screen.queryByText('发布编号')).not.toBeInTheDocument();
expect(screen.queryByText('产物版本')).not.toBeInTheDocument();
expect(screen.queryByText('lhb_shortline:balanced:contract')).not.toBeInTheDocument();
expect(screen.getByText('数据正常')).toBeVisible();
expect(screen.getByTestId('strategy-performance-date')).toHaveTextContent('2026-07-21');
```

For a mismatch, expect `数据异常` and `最新策略数据暂不可用，请稍后复查`, never raw `contract_reason`.

- [ ] **Step 2: Verify RED**

Run from `dashboard/`: `rtk pnpm test -- --run tests/home-cockpit.test.tsx tests/backtest-lab-workspace.test.tsx tests/review-queue-workspace.test.tsx`

Expected: FAIL because technical grids are visible.

- [ ] **Step 3: Implement the human health vocabulary**

```ts
function publicationHealth(status?: string | null) {
  if (status === 'success') return { label: '数据正常', detail: '策略数据已完成更新' };
  if (!status) return { label: '数据更新中', detail: '等待最新策略数据' };
  return { label: '数据异常', detail: '最新策略数据暂不可用，请稍后复查' };
}
```

Render only health, performance date, returns, candidate/holding counts, and human evidence. Keep `data-strategy-id`, `strategy-performance-date`, and `strategy-total-return` for visible acceptance.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command again. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/HomeCockpit.tsx dashboard/src/components/BacktestLabWorkspace.tsx dashboard/src/components/ReviewQueueWorkspace.tsx dashboard/tests/home-cockpit.test.tsx dashboard/tests/backtest-lab-workspace.test.tsx dashboard/tests/review-queue-workspace.test.tsx
git commit -m "fix: simplify human strategy publication UI"
```

### Task 4: Keep Identity Validation In APIs And Automated Acceptance

**Files:**
- Modify: `dashboard/tests/e2e/assertions/consistency.ts`
- Modify: `dashboard/tests/e2e/p0/consistency-contract.spec.ts`
- Modify: `dashboard/tests/e2e/real/critical-journeys.spec.ts`
- Modify: `dashboard/tests/e2e/eod/eod-critical.spec.ts`

- [ ] **Step 1: Freeze the new visible assertion**

```ts
type StrategyPresentationSnapshot = {
  cardCount: number;
  cardVisible: boolean;
  strategyId: string;
  tradeDate: StableField;
  totalReturn: StableField;
};
```

P0 tests must accept matching date/return without DOM contract IDs and reject stale date, stale return, missing card, duplicate field, and hidden field.

- [ ] **Step 2: Verify RED**

Run from `dashboard/`: `PLAYWRIGHT_PROFILE=mock pnpm exec playwright test tests/e2e/p0/consistency-contract.spec.ts`

Expected: FAIL until the helper stops requiring contract and publish DOM fields.

- [ ] **Step 3: Implement API-first identity and visible-metric checks**

`loadAuthoritativeSnapshot()` continues comparing contract ID, publish ID, artifact version, date, and return across Catalog and Review Queue. Home/EOD page assertions compare only strategy ID, visible date, visible return, and health state.

- [ ] **Step 4: Verify focused publication journeys**

Run from `dashboard/`:

```bash
PLAYWRIGHT_PROFILE=mock pnpm exec playwright test tests/e2e/p0/consistency-contract.spec.ts
PLAYWRIGHT_PROFILE=real PLAYWRIGHT_DASHBOARD_PORT=5374 PLAYWRIGHT_API_PORT=8966 pnpm exec playwright test tests/e2e/real/critical-journeys.spec.ts --grep "authoritative publication|home official strategy cards" --project=chromium-desktop
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/tests/e2e/assertions/consistency.ts dashboard/tests/e2e/p0/consistency-contract.spec.ts dashboard/tests/e2e/real/critical-journeys.spec.ts dashboard/tests/e2e/eod/eod-critical.spec.ts
git commit -m "test: keep publication identity in automated acceptance"
```

### Task 5: Close Daily Review, Market Monitor, And Generated Reports Failures

**Files:**
- Modify: `dashboard/tests/stock-heatmap-panel.test.tsx`
- Modify: `dashboard/tests/market-monitor-workspace.test.tsx`
- Modify: `dashboard/src/components/market-monitor/StockHeatmapPanel.tsx`
- Modify: `dashboard/src/components/market-monitor/MarketAnomalyContextPanel.tsx`
- Modify: `dashboard/tests/e2e/real/route-census.spec.ts:470-476`
- Modify: `tests/test_dashboard_app.py`
- Modify: `src/stock_research/dashboard/app.py:516-523`

- [ ] **Step 1: Write duplicate-key and optional-date tests**

Render repeated asset IDs with different group/rank context and assert `console.error` is not called. Add:

```python
def test_dashboard_overview_defaults_trade_date(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_resolve_dashboard_trade_date", lambda value: date(2026, 7, 21))
    monkeypatch.setattr(
        dashboard_app,
        "build_dashboard_overview",
        lambda trade_date, score_version, watchlist_id, top_n: {"trade_date": str(trade_date)},
    )
    response = TestClient(dashboard_app.create_app()).get("/api/dashboard/overview")
    assert response.status_code == 200
    assert response.json()["trade_date"] == "2026-07-21"
```

- [ ] **Step 2: Verify RED**

Run backend focused test and the two frontend component suites. Expected: FAIL.

- [ ] **Step 3: Implement stable keys and date resolution**

Use composite keys including group/industry and index. Change `trade_date` to `str | None = None`, resolve it with `_resolve_dashboard_trade_date()`, and pass the selected date to `build_dashboard_overview()`.

Change the route census landmark lookup to:

```ts
page.getByRole(item.landmark.role, { name: item.landmark.name, exact: true })
```

- [ ] **Step 4: Verify focused Real routes**

Run from `dashboard/`: `PLAYWRIGHT_PROFILE=real PLAYWRIGHT_DASHBOARD_PORT=5374 PLAYWRIGHT_API_PORT=8966 pnpm exec playwright test tests/e2e/real/route-census.spec.ts --grep "daily_review|market_monitor|generated_reports" --project=chromium-desktop`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/app.py tests/test_dashboard_app.py dashboard/src/components/market-monitor/StockHeatmapPanel.tsx dashboard/src/components/market-monitor/MarketAnomalyContextPanel.tsx dashboard/tests/stock-heatmap-panel.test.tsx dashboard/tests/market-monitor-workspace.test.tsx dashboard/tests/e2e/real/route-census.spec.ts
git commit -m "fix: close dashboard route census failures"
```

### Task 6: Restore Theme Research State And Ignore Only Refresh Cancellation

**Files:**
- Modify: `dashboard/tests/theme-research-route.test.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/tests/e2e/assertions/runtime.test.ts`
- Modify: `dashboard/tests/e2e/fixtures/test.ts`

- [ ] **Step 1: Write failing restoration and cancellation tests**

Start at `/theme-research/<theme>/companies`, open a company stock, dispatch Back, and assert `公司映射` is selected. Test this helper:

```ts
export function isExpectedNavigationCancellation(method: string, url: string, failure: string) {
  return method === 'GET' && url.includes('/api/assets/') && failure === 'net::ERR_ABORTED';
}
```

POST aborts, `ERR_FAILED`, HTTP 5xx, and unrelated GET aborts must remain fatal.

- [ ] **Step 2: Verify RED**

Run from `dashboard/`: `rtk pnpm test -- --run tests/theme-research-route.test.tsx tests/e2e/assertions/runtime.test.ts`

Expected: FAIL.

- [ ] **Step 3: Preserve the Theme Research deep path**

Store the source Theme Research path in history state during stock handoff. On `popstate`, restore `themeResearchPathname` from the returned `/theme-research/.../companies` URL before switching workspace.

- [ ] **Step 4: Filter only proven navigation cancellation**

Skip `onRequestFailed` recording only when `isExpectedNavigationCancellation()` returns true. Keep all other evidence fail-closed.

- [ ] **Step 5: Verify focused Real journeys**

Run from `dashboard/`: `PLAYWRIGHT_PROFILE=real PLAYWRIGHT_DASHBOARD_PORT=5374 PLAYWRIGHT_API_PORT=8966 pnpm exec playwright test tests/e2e/real/critical-journeys.spec.ts --grep "theme-research company handoff|deep link survives direct refresh" --project=chromium-desktop`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/AppShell.tsx dashboard/tests/theme-research-route.test.tsx dashboard/tests/e2e/fixtures/test.ts dashboard/tests/e2e/assertions/runtime.test.ts
git commit -m "fix: restore navigation state and ignore refresh aborts"
```

### Task 7: Strengthen Controlled EOD Browser Acceptance

**Files:**
- Modify: `dashboard/tests/e2e/eod/eod-critical.spec.ts`
- Modify: `tests/test_eod_browser_acceptance.py`
- Modify: `docs/ops/playwright-platform-validation.md`
- Modify: `docs/reviews/eod-browser-acceptance-rollout-2026-07-20.md`

- [ ] **Step 1: Add EOD API identity-conflict coverage**

Create a fixture where Catalog and Review Queue differ only by `publish_id`. Assert EOD fails with `publication_identity_conflict` even though no technical ID is rendered.

- [ ] **Step 2: Add the positive human-card contract**

Assert all three cards show authoritative date/return and `数据正常`, omit raw technical identifiers, and never show `175.29%`.

- [ ] **Step 3: Verify RED**

Run from `dashboard/`: `PLAYWRIGHT_PROFILE=eod pnpm exec playwright test tests/e2e/eod/eod-critical.spec.ts`

Expected: FAIL until EOD reads identity from APIs.

- [ ] **Step 4: Implement API-first EOD consistency**

Reuse the API-only authoritative snapshot. Browser assertions cover visible date, return, health, navigation, and runtime cleanliness.

- [ ] **Step 5: Run controlled enabled EOD**

Run from `dashboard/`: `STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED=true PLAYWRIGHT_PROFILE=eod PLAYWRIGHT_DASHBOARD_PORT=5374 PLAYWRIGHT_API_PORT=8966 pnpm test:e2e:eod`

Expected: PASS. Do not silently mutate an external scheduler environment.

- [ ] **Step 6: Record rollout evidence and commit**

Update the runbook and review with the exact revision and passing commands. Keep repository defaults disabled until external EOD and Dashboard environments are changed together after schema verification.

```bash
git add dashboard/tests/e2e/eod/eod-critical.spec.ts tests/test_eod_browser_acceptance.py docs/ops/playwright-platform-validation.md docs/reviews/eod-browser-acceptance-rollout-2026-07-20.md
git commit -m "test: enforce EOD strategy publication consistency"
```

### Task 8: Full Verification And Live Acceptance

**Files:**
- No product changes expected.

- [ ] **Step 1: Run backend affected tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_app.py tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py tests/test_dashboard_default_display_dates.py tests/test_eod_browser_acceptance.py tests/test_eod_auto_repair_scripts.py -q`

Expected: PASS.

- [ ] **Step 2: Run all Dashboard tests and build**

Run from `dashboard/`: `rtk pnpm test -- --run` and `rtk pnpm build`.

Expected: all unit tests and production build pass.

- [ ] **Step 3: Run Mock P0**

Run from `dashboard/`: `PLAYWRIGHT_PROFILE=mock PLAYWRIGHT_DASHBOARD_PORT=5374 pnpm test:e2e:p0`

Expected: PASS.

- [ ] **Step 4: Run full Real**

Run from `dashboard/`: `PLAYWRIGHT_PROFILE=real PLAYWRIGHT_DASHBOARD_PORT=5374 PLAYWRIGHT_API_PORT=8966 pnpm test:e2e:real`

Expected: 41/41 PASS with no console errors, failed requests, stale identities, or navigation mismatch.

- [ ] **Step 5: Run controlled EOD**

Repeat Task 7 Step 5. Expected: PASS.

- [ ] **Step 6: Verify live 5174**

Reload Home, Strategy Lab, Review Queue, Daily Review, Market Monitor, Theme Research, and Generated Reports. Confirm LHB is `+79.43%`, technical publication fields are absent, Review Queue is immutable 4/5/5, all three strategies show `数据正常` and `2026-07-21`, and runtime evidence is clean.

- [ ] **Step 7: Verify worktree hygiene**

Run: `rtk git status --short` and `rtk git diff --check`.

Expected: clean worktree after the task commits.
