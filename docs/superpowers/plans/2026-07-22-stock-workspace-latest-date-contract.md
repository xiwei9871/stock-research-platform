# Stock Workspace Latest-Date Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ordinary stock-workspace navigation load the latest platform review date and latest market data, while explicit replay changes only the review date.

**Architecture:** `AppShell` remains the single source of the platform display date and waits for it before mounting the stock workspace. `StockWorkspace` separates the editable review date from an immutable latest market-data window; handoff dates remain provenance and no longer initialize either query date. Unit tests bind request parameters, and Real Playwright binds the rendered dates during an old-date handoff.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, Playwright, Vite.

---

### Task 1: Bind ordinary navigation to the latest platform date

**Files:**
- Modify: `dashboard/tests/stock-workspace.test.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`

- [ ] **Step 1: Write the failing StockWorkspace handoff-date test**

Add a test that renders an old source date with a newer platform default and asserts the initial profile and daily-bar requests use the newer date:

```tsx
it('uses the latest platform date instead of an old source handoff date', async () => {
  render(
    <StockWorkspace
      initialAssetId="000001.SZ"
      defaultTradeDate="2026-07-21"
      entryContext={{ sourceWorkspace: 'reviewQueue', tradeDate: '2026-05-18' }}
    />
  );

  await waitFor(() =>
    expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
      '000001.SZ',
      '2026-07-21',
      '2026-01-22',
      '2026-07-21',
      'manual_v1',
      'qfq'
    )
  );
  await waitFor(() =>
    expect(apiMocks.fetchDailyBars).toHaveBeenCalledWith(
      '000001.SZ',
      undefined,
      '2026-07-21',
      { resolution: '1D', adjustType: 'qfq' }
    )
  );
  expect(screen.getByText(/结论更新 2026-07-21/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Write the failing AppShell display-date gate test**

Replace the existing expectation that an explicit stock `trade_date` mounts before readiness with an expectation that the workspace waits for the platform display date and treats the URL date only as provenance.

```tsx
it('waits for the platform date before mounting stock even when the route carries a source date', async () => {
  window.history.replaceState({}, '', '/stock/000001.SZ?source=review_queue&trade_date=2026-05-18');
  const readiness = deferred<PlatformReadiness>();
  apiMocks.fetchPlatformReadiness.mockReturnValue(readiness.promise);

  render(<AppShell currentUser={operatorUser} onLogout={vi.fn()} />);

  expect(screen.getByRole('status')).toHaveTextContent('正在解析平台展示日期');
  expect(apiMocks.fetchAssetProfile).not.toHaveBeenCalled();

  await act(async () => {
    readiness.resolve(makeReadyPlatformReadiness({ display_trade_date: '2026-07-21' }));
    await readiness.promise;
  });

  await waitFor(() =>
    expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
      '000001.SZ',
      '2026-07-21',
      '2026-01-22',
      '2026-07-21',
      'manual_v1',
      'qfq'
    )
  );
});
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
cd dashboard
pnpm vitest run tests/stock-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: the new tests fail because `entryContext.tradeDate` still initializes the workspace and the shell still mounts from the route date before display-date resolution.

- [ ] **Step 4: Implement latest-date initialization**

In `StockWorkspace`, initialize both active dates from the platform default and retain the handoff date only inside `entryContext`:

```tsx
const latestPlatformDate = defaultTradeDate || DEFAULT_TRADE_DATE;
const initialReviewTradeDate = latestPlatformDate;
const initialMarketDataEndDate = latestPlatformDate;
const initialMarketDataStartDate = offsetDate(initialMarketDataEndDate, -180);

const [tradeDate, setTradeDate] = useState(initialReviewTradeDate);
const [startDate, setStartDate] = useState(initialMarketDataStartDate);
const [endDate, setEndDate] = useState(initialMarketDataEndDate);
```

Reset and load using these values when the asset or platform date changes:

```tsx
setTradeDate(initialReviewTradeDate);
setStartDate(initialMarketDataStartDate);
setEndDate(initialMarketDataEndDate);
void loadProfile(
  initialAssetId,
  initialReviewTradeDate,
  initialMarketDataStartDate,
  initialMarketDataEndDate
);
```

In `AppShell`, mount the stock workspace only after the platform display date resolves:

```tsx
{workspaceMode === 'stock' ? (
  displayDateResolved && displayTradeDate ? (
    <StockWorkspace
      key={`stock:${stockHandoff.version}`}
      initialAssetId={stockHandoff.assetId ?? selectedAssetId}
      defaultTradeDate={displayTradeDate}
      entryContext={stockHandoff}
      onOpenNews={openNewsWorkspaceFromStock}
      onOpenResearchReports={openResearchReportsWorkspaceFromStock}
      onOpenMarketMonitor={openMarketMonitorWorkspaceFromStock}
    />
  ) : displayDateResolved ? (
    <p className="muted" role="status">平台展示日期不可用。</p>
  ) : (
    <p className="muted" role="status">正在解析平台展示日期...</p>
  )
) : null}
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
cd dashboard
pnpm vitest run tests/stock-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: both files pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add dashboard/src/components/StockWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/tests/stock-workspace.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "fix: default stock workspace to latest dates"
```

### Task 2: Keep explicit review replay independent from market data

**Files:**
- Modify: `dashboard/tests/stock-workspace.test.tsx`
- Modify: `dashboard/src/components/StockWorkspace.tsx`

- [ ] **Step 1: Write the failing explicit-replay test**

Add a test proving that submitting a past review date changes the profile's review date while every chart request keeps the latest market-data end date:

```tsx
it('replays a historical review without rolling market data backward', async () => {
  render(<StockWorkspace initialAssetId="000001.SZ" defaultTradeDate="2026-07-21" />);
  await screen.findByRole('heading', { name: /平安银行/ });

  fireEvent.change(screen.getByLabelText('stock workspace trade date'), {
    target: { value: '2026-05-18' }
  });
  fireEvent.click(screen.getByRole('button', { name: '加载历史复盘' }));

  await waitFor(() =>
    expect(apiMocks.fetchAssetProfile).toHaveBeenLastCalledWith(
      '000001.SZ',
      '2026-05-18',
      '2026-01-22',
      '2026-07-21',
      'manual_v1',
      'qfq'
    )
  );

  for (const buttonName of ['周K', '月K', '分时']) {
    fireEvent.click(screen.getByRole('button', { name: buttonName }));
  }
  await waitFor(() => {
    const endDates = apiMocks.fetchDailyBars.mock.calls.map((call) => call[2]);
    expect(endDates.every((value) => value === '2026-07-21')).toBe(true);
  });
});
```

- [ ] **Step 2: Write the failing controls test**

Assert that the form describes historical review rather than chart replay and no longer exposes editable chart dates:

```tsx
expect(screen.getByText('历史复盘 / 切换股票')).toBeInTheDocument();
expect(screen.queryByLabelText('stock workspace start date')).not.toBeInTheDocument();
expect(screen.queryByLabelText('stock workspace end date')).not.toBeInTheDocument();
expect(screen.getByRole('button', { name: '加载历史复盘' })).toBeInTheDocument();
```

- [ ] **Step 3: Run the StockWorkspace tests and verify RED**

Run:

```bash
cd dashboard
pnpm vitest run tests/stock-workspace.test.tsx
```

Expected: failures show that chart dates are editable and the old `加载回放` contract remains.

- [ ] **Step 4: Make market-data dates immutable in the replay form**

Keep `startDate` and `endDate` internal, remove their input controls, and rename the disclosure and submit action:

```tsx
<summary>
  <span>历史复盘 / 切换股票</span>
  <small>
    {assetId} · 复盘日 {tradeDate} · 行情截至 {endDate}
  </small>
</summary>
<form className="compact-toolbar" onSubmit={handleSubmit}>
  <label>
    股票代码
    <input aria-label="stock workspace asset" value={assetId} onChange={(event) => setAssetId(event.target.value)} />
  </label>
  <label>
    复盘日期
    <input
      aria-label="stock workspace trade date"
      type="date"
      value={tradeDate}
      onChange={(event) => setTradeDate(event.target.value)}
    />
  </label>
<button type="submit">加载历史复盘</button>
</form>
```

The submit handler continues to call:

```tsx
void loadProfile(assetId, tradeDate, startDate, endDate);
```

Only `tradeDate` and `assetId` are editable. Resolution changes continue to call `fetchDailyBars` with the immutable latest `endDate`.

- [ ] **Step 5: Update existing replay-button tests mechanically**

Replace existing test interactions with the new accessible button name:

```tsx
screen.getByRole('button', { name: '加载历史复盘' })
```

Do not change their asserted business behavior except where old chart-date inputs are explicitly removed by this contract.

- [ ] **Step 6: Run StockWorkspace tests and verify GREEN**

Run:

```bash
cd dashboard
pnpm vitest run tests/stock-workspace.test.tsx
```

Expected: all StockWorkspace tests pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "fix: separate review replay from market dates"
```

### Task 3: Add Real Playwright date-consistency coverage

**Files:**
- Modify: `dashboard/tests/e2e/real/critical-journeys.spec.ts`

- [ ] **Step 1: Write the old-handoff Real test**

Add a Real test that obtains the authoritative display date, opens a stock route carrying an old provenance date, and binds both visible surfaces to the latest date:

```ts
test('old stock handoff dates do not roll back current review or chart data', async ({ page, request }) => {
  const readiness = await apiJson(request, '/api/platform/readiness', 'stock-latest-readiness');
  const latestDate = nonEmptyString(readiness.display_trade_date, 'stock_latest_display_date_missing');

  await page.goto('/stock/CN%3ASZ%3A300760?source=review_queue&trade_date=2026-05-18');
  const review = page.getByRole('region', { name: '明日处理结论' });
  const chart = page.getByRole('region', { name: '价格走势' });

  await expect(review).toContainText(`结论更新 ${latestDate}`);
  await expect(chart).toContainText(`截至 ${latestDate}`);
  await expect(page.getByText('结论更新 2026-05-18', { exact: false })).toHaveCount(0);
});
```

Use the existing JSON parsing helpers in the file rather than introducing a second API utility.

- [ ] **Step 2: Run the focused Real test and verify it passes**

Run the existing Real harness with a title filter for the new test.

Expected: 1 passed with no console, page, request, or API runtime evidence.

- [ ] **Step 3: Commit Task 3**

```bash
git add dashboard/tests/e2e/real/critical-journeys.spec.ts
git commit -m "test: guard latest stock workspace dates"
```

### Task 4: Complete platform verification

**Files:**
- Modify only if a verification failure proves a scoped regression.

- [ ] **Step 1: Run all focused backend EOD and dashboard API tests**

```bash
PYTHONPATH=src:. /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_app.py \
  tests/test_dashboard_review_queue.py \
  tests/test_eod_browser_acceptance.py \
  tests/test_eod_auto_repair.py \
  tests/test_eod_auto_repair_checks.py -q
```

Expected: all pass.

- [ ] **Step 2: Run all dashboard unit tests**

```bash
cd dashboard
pnpm test
```

Expected: all test files and tests pass. If the known market-monitor keyboard test fails once because its asynchronous fixture has not rendered, rerun that single test to distinguish a pre-existing timing flake from a regression; do not weaken its assertions.

- [ ] **Step 3: Build the dashboard**

```bash
cd dashboard
pnpm build
```

Expected: successful TypeScript and Vite build.

- [ ] **Step 4: Run Mock P0 and full Real Playwright**

```bash
cd dashboard
pnpm test:e2e:p0
pnpm test:e2e:real
```

Expected: Mock P0 passes and full Real passes, including the new date-consistency test.

- [ ] **Step 5: Run controlled EOD browser acceptance**

Use `run_browser_acceptance` with the latest official candidate cohort, a private output directory, and isolated dashboard/API ports.

Expected: `status=success`, no failure classes, no warnings.

- [ ] **Step 6: Restart and verify the live 5174 workspace**

Restart the worktree API process, reload the existing signed-in stock tab, then verify:

- ordinary old-date handoff renders the latest review date;
- 日K、周K、月K、分时 all end on the latest market-data date;
- explicit historical review changes the review date only;
- no contract ID, publish ID, or artifact version is visible on human-facing strategy pages.

- [ ] **Step 7: Commit any scoped verification repair and report evidence**

If no new code changes are required, leave the worktree clean. Report exact test counts, the controlled EOD result, and the live dates observed.
