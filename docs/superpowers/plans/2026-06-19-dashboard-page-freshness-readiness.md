# Dashboard Page Freshness And Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every dashboard page default to the latest displayable trading date, remove misleading stale/empty states, and make Home readiness reflect real usable data.

**Architecture:** Add one shared frontend source of truth for the platform display date, then route default page dates through it instead of hard-coded `2026-06-08`. Fix backend readiness checks to use the same concrete data endpoints that the pages use. Keep UI changes narrow: no strategy logic changes, no data schema changes unless a test proves a field is missing.

**Tech Stack:** React + TypeScript dashboard, FastAPI backend under `src/stock_research/dashboard`, pytest, Vitest/React Testing Library, local backend `127.0.0.1:8765`, frontend `127.0.0.1:5174`.

---

## File Map

- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/src/components/AppShell.tsx`
  - Owns top-level workspace routing and can pass the platform display date into page workspaces.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/src/components/StockWorkspace.tsx`
  - Replace hard-coded default stock review date and chart end date with latest display date.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/src/components/WatchlistWorkspace.tsx`
  - Replace hard-coded default watchlist date and preserve manual date edits.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/src/components/DataExplorerWorkspace.tsx`
  - Replace hard-coded default factor/profile date and chart end date.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/src/components/ReportsWorkspace.tsx`
  - Replace hard-coded generated-report date.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/src/components/FactorLabWorkspace.tsx`
  - Replace hard-coded factor lab date.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/src/components/BacktestLabWorkspace.tsx`
  - Replace hard-coded default backtest end date.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/src/components/MarketMonitorWorkspace.tsx`
  - Improve empty stock-list and pending-source display.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/dashboard/readiness.py`
  - Fix readiness checks for Review Queue, News, Research Reports, Generated Reports, and snapshots.
- Test: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/tests/test_dashboard_readiness.py`
- Test: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/tests/app-shell.test.tsx`
- Test: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/tests/home-cockpit.test.tsx`
- Test: add or modify `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard/tests/page-default-dates.test.tsx`

---

### Task 1: Add A Shared Latest Display Date Contract

**Files:**
- Modify: `dashboard/src/components/AppShell.tsx`
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing test**

Add a test that mocks `/api/platform/display-date` or the existing API client call and verifies workspaces receive `2026-06-18`, not `2026-06-08`.

```tsx
it('passes platform display date to date-sensitive workspaces', async () => {
  mockPlatformDisplayDate({ display_trade_date: '2026-06-18' });
  render(<AppShell />);
  await userEvent.click(screen.getByText('观察池'));
  expect(await screen.findByLabelText('trade date')).toHaveValue('2026-06-18');
});
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- app-shell.test.tsx
```

Expected: FAIL because the page still uses `2026-06-08`.

- [ ] **Step 3: Implement shared date passing**

In `AppShell.tsx`, load platform display date once, keep it in state, and pass it as `initialTradeDate` or `defaultTradeDate` to date-sensitive pages.

Use this behavior:

```ts
const latestDisplayDate =
  platformDisplayDate?.display_trade_date ??
  platformSummary?.latest_market_date ??
  '';
```

Do not override a date supplied from a review-queue handoff. Handoff context remains higher priority than global default.

- [ ] **Step 4: Run test and verify pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- app-shell.test.tsx
```

Expected: PASS.

---

### Task 2: Remove Hard-Coded `2026-06-08` Defaults From Pages

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/src/components/WatchlistWorkspace.tsx`
- Modify: `dashboard/src/components/DataExplorerWorkspace.tsx`
- Modify: `dashboard/src/components/ReportsWorkspace.tsx`
- Modify: `dashboard/src/components/FactorLabWorkspace.tsx`
- Modify: `dashboard/src/components/BacktestLabWorkspace.tsx`
- Test: `dashboard/tests/page-default-dates.test.tsx`

- [ ] **Step 1: Write failing tests**

Create tests that render each page with `initialTradeDate="2026-06-18"` or `defaultTradeDate="2026-06-18"` and assert visible date inputs use that value.

```tsx
it('uses supplied latest trade date in WatchlistWorkspace', () => {
  render(<WatchlistWorkspace defaultTradeDate="2026-06-18" />);
  expect(screen.getByLabelText('trade date')).toHaveValue('2026-06-18');
});

it('uses supplied latest trade date in ReportsWorkspace', () => {
  render(<ReportsWorkspace initialTradeDate="2026-06-18" />);
  expect(screen.getByLabelText('report trade date')).toHaveValue('2026-06-18');
});
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- page-default-dates.test.tsx
```

Expected: FAIL for pages that do not yet accept a default-date prop.

- [ ] **Step 3: Add explicit default-date props**

Apply this pattern:

```tsx
type WatchlistWorkspaceProps = {
  onOpenAsset?: (assetId: string) => void;
  defaultTradeDate?: string;
};

export function WatchlistWorkspace({ onOpenAsset, defaultTradeDate = '' }: WatchlistWorkspaceProps) {
  const [tradeDate, setTradeDate] = useState(defaultTradeDate);
}
```

Use a stable fallback only when no platform date is available:

```ts
const FALLBACK_TRADE_DATE = '2026-06-18';
const effectiveTradeDate = defaultTradeDate || FALLBACK_TRADE_DATE;
```

Do not leave `2026-06-08` in page-level defaults.

- [ ] **Step 4: Update chart date windows**

For `StockWorkspace` and `DataExplorerWorkspace`, derive start/end from the selected end date:

```ts
const initialEndDate = initialTradeDate || defaultTradeDate;
const initialStartDate = offsetDate(initialEndDate, -180);
```

When trade date changes through a platform default, keep chart end date aligned unless the user manually edited the chart date.

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- page-default-dates.test.tsx app-shell.test.tsx
```

Expected: PASS.

---

### Task 3: Fix Home Readiness Content Link Misclassification

**Files:**
- Modify: `src/stock_research/dashboard/readiness.py`
- Test: `tests/test_dashboard_readiness.py`

- [ ] **Step 1: Write failing backend tests**

Add tests for the concrete data state seen on 2026-06-18:

```python
def test_readiness_marks_content_ready_when_news_reports_and_generated_reports_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(readiness, "_has_public_news", lambda: True)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.load_platform_readiness()

    by_key = {item["key"]: item for item in payload["checks"]}
    assert by_key["news"]["status"] == "ready"
    assert by_key["research_reports"]["status"] == "ready"
    assert by_key["generated_reports"]["status"] == "ready"
```

Also add:

```python
def test_readiness_marks_review_queue_ready_when_strategy_manifest_exists(monkeypatch):
    monkeypatch.setattr(readiness, "_has_review_queue_for_trade_date", lambda trade_date: True)
    payload = readiness.load_platform_readiness()
    by_key = {item["key"]: item for item in payload["checks"]}
    assert by_key["review_queue"]["status"] == "ready"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src .venv/bin/python -m pytest tests/test_dashboard_readiness.py -q
```

Expected: FAIL on content readiness or review queue readiness.

- [ ] **Step 3: Implement readiness checks against real sources**

Use these rules:

- Review Queue ready if `review_queue_strategy_manifest.csv` exists for `display_trade_date` and has at least one row.
- News ready if `/api/public-news` backing table has at least one accepted item for the current day or collector status is enabled with successful recent run.
- Research Reports ready if `research_report_summary.total_reports > 0`.
- Generated Reports ready if `load_report_links(display_trade_date)` returns at least one item.
- Evidence snapshots should be `partial`, not block core readiness, if only lightweight strategy manifest exists.

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_dashboard_readiness.py -q
```

Expected: PASS.

---

### Task 4: Fix Generated Reports And Watchlist Empty States

**Files:**
- Modify: `dashboard/src/components/ReportsWorkspace.tsx`
- Modify: `dashboard/src/components/WatchlistWorkspace.tsx`
- Test: `dashboard/tests/page-default-dates.test.tsx`

- [ ] **Step 1: Write failing tests**

Add test for watchlist default-date behavior and generated report empty-state explanation:

```tsx
it('does not show empty watchlist when latest date has rows', async () => {
  mockWatchlistRows('2026-06-18', [{ asset_id: 'CN:SH:601211', stock_name: '国泰海通', priority: 1 }]);
  render(<WatchlistWorkspace defaultTradeDate="2026-06-18" />);
  expect(await screen.findByText('国泰海通')).toBeInTheDocument();
});

it('loads generated reports for latest date', async () => {
  mockOverviewReports('2026-06-18', [{ title: 'daily_topn_2026-06-18_manual_v1.md' }]);
  render(<ReportsWorkspace initialTradeDate="2026-06-18" />);
  expect(await screen.findByText('daily_topn_2026-06-18_manual_v1.md')).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement page copy**

For Watchlist empty state, show:

```text
当前日期暂无观察记录。你可以在个股工作台点击“观察”创建人工观察项；如果想看策略候选池，请切换到复盘队列。
```

For Generated Reports empty state, show:

```text
当前日期没有生成报告。若平台日期已有数据但这里为空，说明报告生成任务尚未产出该日期文件。
```

- [ ] **Step 3: Run tests**

Run:

```bash
cd dashboard
pnpm test -- page-default-dates.test.tsx
```

Expected: PASS.

---

### Task 5: Improve Market Monitor Incomplete Blocks

**Files:**
- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
- Test: `dashboard/tests/market-monitor-workspace.test.tsx` or existing closest test file

- [ ] **Step 1: Write failing tests**

Verify that `pending_source` is not rendered raw and empty stock lists are explained:

```tsx
it('does not expose raw pending_source in market monitor', async () => {
  mockMarketMonitor({ weight_performance: { status: 'pending_source' }, stock_lists: {} });
  render(<MarketMonitorWorkspace />);
  expect(await screen.findByText('权重表现数据待接入')).toBeInTheDocument();
  expect(screen.queryByText('pending_source')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Implement display copy**

Replace raw pending values:

```tsx
const weightPerformanceText =
  payload.weight_performance?.status === 'pending_source'
    ? '权重表现数据待接入'
    : formatWeightPerformance(payload.weight_performance);
```

For empty stock lists, show:

```text
当前 EOD 版本暂未写入个股明细列表；市场广度、涨跌停数量和情绪评分已可用。
```

- [ ] **Step 3: Run tests**

Run:

```bash
cd dashboard
pnpm test -- market-monitor-workspace.test.tsx
```

Expected: PASS.

---

### Task 6: Fix Stock Workspace Initial Loading And Digest Copy

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Test: `dashboard/tests/stock-workspace.test.tsx` or existing closest test file

- [ ] **Step 1: Write failing tests**

Use latest date and assert digest does not remain stuck:

```tsx
it('loads evidence digest for the latest trade date', async () => {
  mockAssetProfile({ canonical_asset_id: 'CN:SZ:000001', trade_date: '2026-06-18' });
  mockEvidenceDigest({ trade_date: '2026-06-18', title: '平安银行证据摘要' });
  render(<StockWorkspace initialTradeDate="2026-06-18" />);
  expect(await screen.findByText('平安银行证据摘要')).toBeInTheDocument();
  expect(screen.queryByText('Loading digest...')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Implement digest loading guard**

Use latest/default trade date consistently:

```ts
const effectiveTradeDate = currentEntryContext.tradeDate ?? initialTradeDate ?? defaultTradeDate;
```

When digest fails or is partial, show Chinese product text:

```text
证据摘要暂不完整
```

Do not show raw English strings such as `Thin evidence`, `No active watchlist signal`, or `No related news found` in the main UI.

- [ ] **Step 3: Verify K-line tabs still work**

Run API smoke:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
import json, urllib.request
for res in ["1D", "60m", "30m", "10m", "5m"]:
    url = f"http://127.0.0.1:8765/api/assets/000001.SZ/bars?start_date=2026-06-01&end_date=2026-06-18&adjust_type={'qfq' if res == '1D' else 'raw'}&resolution={res}"
    payload = json.load(urllib.request.urlopen(url, timeout=20))
    assert payload["items"], res
    print(res, len(payload["items"]))
PY
```

Expected: all resolutions print row counts.

---

### Task 7: Full Verification And Browser Audit

**Files:**
- No production code unless verification reveals a specific defect.

- [ ] **Step 1: Run backend tests**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src .venv/bin/python -m pytest tests/test_dashboard_readiness.py tests/test_dashboard_app.py tests/test_dashboard_schemas.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- app-shell.test.tsx home-cockpit.test.tsx page-default-dates.test.tsx
pnpm build
```

Expected: PASS and build succeeds.

- [ ] **Step 3: Browser audit**

Open `http://127.0.0.1:5174/` and check:

- Home: platform date `2026-06-18`, content chain not `0/3` if news/reports exist.
- Review Queue: LHB/Mid/Tech groups have non-zero real scores.
- Market Monitor: no raw `pending_source`, clear explanation for missing stock list.
- Stock Workspace: default date `2026-06-18`; digest does not stay `Loading digest...`; K-line tabs load.
- Watchlist: default date `2026-06-18`; rows show if API has rows.
- Data Explorer: default date and chart end date `2026-06-18`.
- Generated Reports: default date `2026-06-18`; shows `daily_topn_2026-06-18_manual_v1.md`.

- [ ] **Step 4: Sync external only after local verification**

```bash
source /Users/xiwei/.stock_research_dashboard_sync.env
export SSH_OPTS='-i /Users/xiwei/.ssh/stock_dashboard_185_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes'
./deploy/sync_dashboard_fast.sh
DASHBOARD_AUTH='mqkj:mqkj1234' TRADE_DATE=2026-06-18 START_DATE=2026-01-01 END_DATE=2026-06-18 ./deploy/check_dashboard_release.sh
```

Expected: sync completes and release check passes.

---

## Execution Order

1. Task 1: shared latest display date.
2. Task 2: remove hard-coded page dates.
3. Task 3: readiness truth fixes.
4. Task 4: reports/watchlist empty states.
5. Task 5: market monitor incomplete block polish.
6. Task 6: stock workspace latest-date digest behavior.
7. Task 7: full verification and external sync.

## Self-Review

- Spec coverage: covers every issue from the browser audit: stale defaults, readiness misclassification, generated reports empty state, watchlist empty state, market monitor pending/empty blocks, stock workspace digest loading, and verification.
- Placeholder scan: no `TBD` or unspecified task remains.
- Type consistency: frontend changes consistently use `initialTradeDate` or `defaultTradeDate`; backend readiness tests refer to existing readiness payload `checks`.
- Scope check: no strategy calculation changes included; this plan only fixes dashboard page freshness and product presentation.
