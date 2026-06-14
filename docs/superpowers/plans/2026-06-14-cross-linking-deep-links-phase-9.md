# Cross-Linking Deep Links Phase 9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete reversible row-level navigation among News, Research Reports, Market Monitor, and Stock Detail.

**Architecture:** Keep `AppShell` as the only cross-workspace router. Extend the existing frontend handoff objects so source rows pass `newsId`, `reportId`, `eventKey`, `tradeDate`, and `monitorTab` into `StockWorkspace`, and Stock Detail return actions restore those source workspaces.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, existing dashboard API client and workspace components.

---

## File Structure

- Modify `dashboard/src/components/AppShell.tsx`: add market handoff state, pass rich context between workspaces, clear stale context on plain Stock navigation.
- Modify `dashboard/src/components/NewsWorkspace.tsx`: widen `onOpenAsset` callback and pass news row context from stock chips.
- Modify `dashboard/src/components/ResearchReportsWorkspace.tsx`: add `onOpenAsset` prop and stock-detail actions in list/detail.
- Modify `dashboard/src/components/MarketMonitorWorkspace.tsx`: add initial date/tab/asset props, row-level stock-detail buttons, and tab/date restoration.
- Modify `dashboard/src/components/StockWorkspace.tsx`: include `tradeDate` in `StockEntryContext` and return the full context to callbacks.
- Modify `dashboard/tests/news-workspace.test.tsx`: assert News passes row context.
- Modify `dashboard/tests/research-reports-workspace.test.tsx`: assert report list/detail open Stock Detail with report context.
- Modify `dashboard/tests/app-shell.test.tsx`: assert cross-workspace loops and stale-context prevention.
- Add or modify `dashboard/tests/market-monitor-workspace.test.tsx`: assert Market Monitor row actions and initial handoff restoration.

Do not edit backend files unless a response row lacks `asset_id`. Current `PublicNewsItem.stocks`, `ResearchReportItem`, and `EmotionStockListRow` already expose asset identifiers.

---

### Task 1: News Row Context to Stock Detail

**Files:**
- Modify: `dashboard/src/components/NewsWorkspace.tsx`
- Test: `dashboard/tests/news-workspace.test.tsx`
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write the failing NewsWorkspace unit test**

Add this assertion to the existing `opens a stock when a news item has an API stock mention` test in `dashboard/tests/news-workspace.test.tsx`.

```tsx
expect(onOpenAsset).toHaveBeenCalledWith('CN:SH:600000', {
  sourceWorkspace: 'news',
  assetId: 'CN:SH:600000',
  newsId: 'n1',
  query: '600000 浦发银行公告'
});
```

Update the second stock mention test with this expected shape:

```tsx
expect(openAsset).toHaveBeenCalledWith('CN:SH:600519', {
  sourceWorkspace: 'news',
  assetId: 'CN:SH:600519',
  newsId: 'n1',
  query: '贵州茅台经营快讯'
});
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx
```

Expected: FAIL because `onOpenAsset` currently receives only the asset id.

- [ ] **Step 3: Implement NewsWorkspace context payload**

In `dashboard/src/components/NewsWorkspace.tsx`, import the stock context type and change the props:

```tsx
import type { StockEntryContext } from './StockWorkspace';

type NewsWorkspaceProps = {
  initialQuery?: string;
  initialNewsId?: string;
  onOpenAsset?: (assetId: string, context: StockEntryContext) => void;
};
```

Update the stock chip click handler:

```tsx
const assetId = stock.asset_id || stock.ts_code;

onClick={() =>
  onOpenAsset?.(assetId, {
    sourceWorkspace: 'news',
    assetId,
    newsId: item.news_id,
    query: item.title || query || assetId
  })
}
```

Keep the existing `aria-label` text.

- [ ] **Step 4: Wire AppShell to preserve News context**

In `dashboard/src/components/AppShell.tsx`, change the News workspace callback:

```tsx
<NewsWorkspace
  key={`news:${newsHandoff.version}`}
  initialQuery={newsHandoff.query}
  initialNewsId={newsHandoff.newsId}
  onOpenAsset={(assetId, context) =>
    openStockWorkspace(assetId, {
      sourceWorkspace: 'news',
      query: context.query,
      newsId: context.newsId
    })
  }
/>
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: PASS for News tests. If AppShell tests fail from existing unrelated dirty worktree changes, capture the failing test names before changing anything.

- [ ] **Step 6: Commit Task 1**

```bash
git add dashboard/src/components/NewsWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/tests/news-workspace.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: preserve news stock handoff context"
```

Before committing, run `git diff --cached --stat` and confirm only Task 1 files are staged.

---

### Task 2: Research Reports to Stock Detail

**Files:**
- Modify: `dashboard/src/components/ResearchReportsWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Test: `dashboard/tests/research-reports-workspace.test.tsx`
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write the failing ResearchReportsWorkspace unit test**

Add a test to `dashboard/tests/research-reports-workspace.test.tsx`:

```tsx
it('opens stock detail from a report row with report context', async () => {
  const onOpenAsset = vi.fn();
  render(<ResearchReportsWorkspace onOpenAsset={onOpenAsset} />);

  await screen.findByText('贵州茅台深度报告');
  fireEvent.click(screen.getByRole('button', { name: 'Open Stock Detail for 贵州茅台' }));

  expect(onOpenAsset).toHaveBeenCalledWith('CN:SH:600519', {
    sourceWorkspace: 'researchReports',
    assetId: 'CN:SH:600519',
    eventKey: 'r1:600519.SH',
    reportId: 'r1',
    query: '贵州茅台深度报告'
  });
});
```

Add a second test for the selected report detail:

```tsx
it('opens stock detail from selected report detail with report context', async () => {
  const onOpenAsset = vi.fn();
  render(<ResearchReportsWorkspace onOpenAsset={onOpenAsset} />);

  fireEvent.click(await screen.findByRole('button', { name: 'Open report 贵州茅台深度报告' }));
  fireEvent.click(screen.getByRole('button', { name: 'Open Stock Detail for 贵州茅台' }));

  expect(onOpenAsset).toHaveBeenLastCalledWith('CN:SH:600519', {
    sourceWorkspace: 'researchReports',
    assetId: 'CN:SH:600519',
    eventKey: 'r1:600519.SH',
    reportId: 'r1',
    query: '贵州茅台深度报告'
  });
});
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
cd dashboard && npm test -- --run tests/research-reports-workspace.test.tsx
```

Expected: FAIL because `ResearchReportsWorkspace` has no `onOpenAsset` prop or stock-detail buttons.

- [ ] **Step 3: Implement report context helper and prop**

In `dashboard/src/components/ResearchReportsWorkspace.tsx`, import the type and extend props:

```tsx
import type { StockEntryContext } from './StockWorkspace';

type ResearchReportsWorkspaceProps = {
  initialQuery?: string;
  initialEventKey?: string;
  initialReportId?: string;
  onOpenAsset?: (assetId: string, context: StockEntryContext) => void;
};
```

Destructure the prop:

```tsx
export function ResearchReportsWorkspace({
  initialQuery = '',
  initialEventKey,
  initialReportId,
  onOpenAsset
}: ResearchReportsWorkspaceProps = {}) {
```

Add helper functions above the component:

```tsx
function getReportAssetId(report: ResearchReportItem) {
  return report.asset_id || report.ts_code;
}

function buildReportStockContext(report: ResearchReportItem): StockEntryContext {
  const assetId = getReportAssetId(report);
  return {
    sourceWorkspace: 'researchReports',
    assetId,
    eventKey: report.event_key,
    reportId: report.report_id,
    query: report.report_title || report.stock_name || report.ts_code || assetId
  };
}
```

- [ ] **Step 4: Add stock-detail buttons to list and detail**

In the report row render, add a button near the report metadata:

```tsx
{getReportAssetId(report) ? (
  <button
    type="button"
    className="link-chip"
    aria-label={`Open Stock Detail for ${report.stock_name || report.ts_code}`}
    onClick={(event) => {
      event.stopPropagation();
      const assetId = getReportAssetId(report);
      onOpenAsset?.(assetId, buildReportStockContext(report));
    }}
  >
    Stock Detail
  </button>
) : null}
```

In the selected report detail render, add the same action:

```tsx
{selectedReport && getReportAssetId(selectedReport) ? (
  <button
    type="button"
    className="link-chip"
    aria-label={`Open Stock Detail for ${selectedReport.stock_name || selectedReport.ts_code}`}
    onClick={() => {
      const assetId = getReportAssetId(selectedReport);
      onOpenAsset?.(assetId, buildReportStockContext(selectedReport));
    }}
  >
    Stock Detail
  </button>
) : null}
```

Use the component's existing button/list layout; do not introduce a new card style.

- [ ] **Step 5: Wire AppShell Research Reports to Stock Detail**

In `dashboard/src/components/AppShell.tsx`, pass the callback:

```tsx
<ResearchReportsWorkspace
  key={`researchReports:${researchReportsHandoff.version}`}
  initialQuery={researchReportsHandoff.query}
  initialEventKey={researchReportsHandoff.eventKey}
  initialReportId={researchReportsHandoff.reportId}
  onOpenAsset={(assetId, context) =>
    openStockWorkspace(assetId, {
      sourceWorkspace: 'researchReports',
      query: context.query,
      eventKey: context.eventKey,
      reportId: context.reportId
    })
  }
/>
```

- [ ] **Step 6: Add AppShell integration test for Research -> Stock**

In `dashboard/tests/app-shell.test.tsx`, add or extend the existing mocked-workspace routing test:

```tsx
vi.doMock('../src/components/ResearchReportsWorkspace', () => ({
  ResearchReportsWorkspace: ({ onOpenAsset }: { onOpenAsset?: (assetId: string, context: StockEntryContext) => void }) => (
    <button
      type="button"
      onClick={() =>
        onOpenAsset?.('CN:SH:600519', {
          sourceWorkspace: 'researchReports',
          assetId: 'CN:SH:600519',
          eventKey: 'r1:600519.SH',
          reportId: 'r1',
          query: '贵州茅台深度报告'
        })
      }
    >
      mocked report stock
    </button>
  )
}));
```

Assert Stock Detail receives the context:

```tsx
fireEvent.click(screen.getByRole('button', { name: 'Research Reports' }));
fireEvent.click(await screen.findByRole('button', { name: 'mocked report stock' }));

expect(await screen.findByText(/Opened from Research Reports/)).toBeInTheDocument();
expect(screen.getByText(/r1:600519.SH/)).toBeInTheDocument();
expect(screen.getByText(/r1/)).toBeInTheDocument();
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd dashboard && npm test -- --run tests/research-reports-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: PASS for Research Reports tests and the new AppShell integration.

- [ ] **Step 8: Commit Task 2**

```bash
git add dashboard/src/components/ResearchReportsWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/tests/research-reports-workspace.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: link research reports to stock detail"
```

Before committing, run `git diff --cached --stat` and confirm only Task 2 files are staged.

---

### Task 3: Market Monitor EOD Rows to Stock Detail

**Files:**
- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Test: `dashboard/tests/market-monitor-workspace.test.tsx` or `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Create the Market Monitor unit test**

Create `dashboard/tests/market-monitor-workspace.test.tsx` with this content:

```tsx
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MarketMonitorWorkspace } from '../src/components/MarketMonitorWorkspace';
import type { MarketMonitorPayload } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchMarketMonitorEod: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeMarketMonitorPayload(overrides: Partial<MarketMonitorPayload> = {}): MarketMonitorPayload {
  return {
    trade_date: '2026-06-12',
    freshness: {
      mode: 'eod',
      label: 'Last Completed Trading Day',
      is_realtime: false,
      latest_market_date: '2026-06-12',
      latest_factor_date: '2026-06-12',
      latest_score_date: '2026-06-12'
    },
    coverage: { market_assets: 5000, score_assets: 5000, factor_count: 20 },
    market_breadth: {
      advancers: 3000,
      decliners: 1800,
      limit_up: 80,
      limit_down: 12,
      advancing_ratio: 0.6,
      turnover_change_pct: 0.04,
      status: 'available'
    },
    index_snapshot: [],
    sector_strength: { strongest: [], weakest: [], status: 'available' },
    unusual_moves: [],
    watchlist_alerts: [],
    strategy_signal_summary: { topn_preview_count: 0, topn_preview: [], risk_filter_counts: {} },
    generated_reports: [],
    market_emotion: {
      summary: {
        score: 73.6,
        state: 'hot',
        risk_state: 'medium',
        style_signal_hint: 'growth_favorable',
        position_budget_hint: 'reduced',
        status: 'available'
      },
      components: [],
      breadth: { traded_count: 5207, up_count: 3610, down_count: 1492, status: 'available' },
      liquidity: { total_amount: 1280000000000, amount_ratio_5_20: 1.18, status: 'available' },
      limit_performance: { limit_up_count: 90, limit_down_count: 10, broken_limit_up_count: 55, status: 'available' },
      profit_effect: { limit_up_success_rate: 0.73, status: 'available' },
      drawdown_pressure: { strong_down_count: 55, limit_down_count: 10, status: 'available' },
      weight_performance: { status: 'pending_source' }
    },
    emotion_stock_lists: {
      auction_status: 'available',
      auction: [],
      limit_up: [],
      broken_limit_up: [],
      limit_down: []
    },
    warnings: [],
    ...overrides
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchMarketMonitorEod.mockResolvedValue(makeMarketMonitorPayload());
});

afterEach(() => {
  cleanup();
});

describe('MarketMonitorWorkspace', () => {
  it('opens stock detail from an EOD stock row with market context', async () => {
    const onOpenAsset = vi.fn();
    apiMocks.fetchMarketMonitorEod.mockResolvedValue(makeMarketMonitorPayload({
      trade_date: '2026-06-12',
      emotion_stock_lists: {
        auction_status: 'available',
        auction: [],
        limit_up: [
          {
            name: '贵州茅台',
            asset_id: 'CN:SH:600519',
            symbol: '600519',
            amount: 1200000000,
            pct_chg: 10,
            board: '白酒',
            tab: 'limit_up',
            limit_up_streak: 1
          }
        ],
        broken_limit_up: [],
        limit_down: []
      }
    }));

    render(<MarketMonitorWorkspace onOpenAsset={onOpenAsset} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open Stock Detail for 贵州茅台 from 涨停' }));

    expect(onOpenAsset).toHaveBeenCalledWith('CN:SH:600519', {
      sourceWorkspace: 'market',
      assetId: 'CN:SH:600519',
      tradeDate: '2026-06-12',
      monitorTab: 'limit_up',
      query: '贵州茅台'
    });
  });

  it('loads the initial EOD date and selects the initial stock tab', async () => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValue(makeMarketMonitorPayload({ trade_date: '2026-06-11' }));

    render(<MarketMonitorWorkspace initialTradeDate="2026-06-11" initialMonitorTab="broken_limit_up" />);

    await waitFor(() => {
      expect(apiMocks.fetchMarketMonitorEod).toHaveBeenCalledWith({ topN: 5, tradeDate: '2026-06-11' });
    });
    expect(screen.getByRole('tab', { name: /炸板/ })).toHaveAttribute('aria-selected', 'true');
  });
});
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
cd dashboard && npm test -- --run tests/market-monitor-workspace.test.tsx
```

Expected: FAIL because `MarketMonitorWorkspace` has no `onOpenAsset`, initial date, or initial tab props.

- [ ] **Step 3: Implement Market Monitor props and initial load**

In `dashboard/src/components/MarketMonitorWorkspace.tsx`, import the type:

```tsx
import type { StockEntryContext } from './StockWorkspace';
```

Add props:

```tsx
type MarketMonitorWorkspaceProps = {
  initialTradeDate?: string;
  initialMonitorTab?: StockTabKey;
  initialAssetId?: string;
  onOpenAsset?: (assetId: string, context: StockEntryContext) => void;
};

export function MarketMonitorWorkspace({
  initialTradeDate,
  initialMonitorTab = 'limit_up',
  initialAssetId,
  onOpenAsset
}: MarketMonitorWorkspaceProps = {}) {
```

Initialize state from props:

```tsx
const [tradeDateInput, setTradeDateInput] = useState(initialTradeDate ?? '');
const [activeStockTab, setActiveStockTab] = useState<StockTabKey>(initialMonitorTab);
```

Change the initial effect:

```tsx
useEffect(() => {
  isMountedRef.current = true;
  void loadMarketMonitor(initialTradeDate);

  return () => {
    isMountedRef.current = false;
    requestIdRef.current += 1;
  };
}, [loadMarketMonitor, initialTradeDate]);
```

- [ ] **Step 4: Add row-level stock-detail buttons**

In the stock table body, replace the stock name cell content with:

```tsx
<td>
  {row.asset_id ? (
    <button
      type="button"
      className={row.asset_id === initialAssetId ? 'link-chip active' : 'link-chip'}
      aria-label={`Open Stock Detail for ${row.name || row.symbol} from ${tab.label}`}
      onClick={() =>
        onOpenAsset?.(row.asset_id, {
          sourceWorkspace: 'market',
          assetId: row.asset_id,
          tradeDate: payload?.trade_date,
          monitorTab: tab.key,
          query: row.name || row.symbol || row.asset_id
        })
      }
    >
      {row.name || row.symbol}
    </button>
  ) : (
    <strong>{row.name || row.symbol}</strong>
  )}
  <span>{row.symbol}</span>
</td>
```

Keep the existing table columns and empty state.

- [ ] **Step 5: Wire AppShell Market handoff**

In `dashboard/src/components/AppShell.tsx`, add state:

```tsx
const [marketHandoff, setMarketHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
```

Extend the handoff types near the top of the file:

```tsx
type MarketMonitorTab = 'auction' | 'limit_up' | 'broken_limit_up' | 'limit_down';

type WorkspaceHandoff = {
  query: string;
  tradeDate?: string;
  newsId?: string;
  assetId?: string;
  eventKey?: string;
  reportId?: string;
  monitorTab?: MarketMonitorTab;
  path?: string;
  version: number;
};

type StockHandoff = {
  assetId?: string;
  sourceWorkspace?: StockSourceWorkspace;
  query?: string;
  matchReason?: string;
  newsId?: string;
  eventKey?: string;
  reportId?: string;
  tradeDate?: string;
  monitorTab?: MarketMonitorTab;
  version: number;
};
```

Change `openMarketMonitorWorkspaceFromStock`:

```tsx
function openMarketMonitorWorkspaceFromStock(context: StockEntryContext) {
  setMarketHandoff((current) => ({
    query: context.query ?? context.assetId ?? selectedAssetId,
    assetId: context.assetId ?? selectedAssetId,
    tradeDate: context.tradeDate,
    monitorTab: context.monitorTab,
    version: current.version + 1
  }));
  setWorkspaceMode('market');
}
```

Pass Market props:

```tsx
{workspaceMode === 'market' ? (
  <MarketMonitorWorkspace
    key={`market:${marketHandoff.version}`}
    initialTradeDate={marketHandoff.tradeDate}
    initialMonitorTab={marketHandoff.monitorTab}
    initialAssetId={marketHandoff.assetId}
    onOpenAsset={(assetId, context) =>
      openStockWorkspace(assetId, {
        sourceWorkspace: 'market',
        query: context.query,
        tradeDate: context.tradeDate,
        monitorTab: context.monitorTab
      })
    }
  />
) : null}
```

Update the StockWorkspace prop:

```tsx
onOpenMarketMonitor={openMarketMonitorWorkspaceFromStock}
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd dashboard && npm test -- --run tests/market-monitor-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: PASS for Market tests and AppShell routing.

- [ ] **Step 7: Commit Task 3**

```bash
git add dashboard/src/components/MarketMonitorWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/tests/market-monitor-workspace.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: link market monitor rows to stock detail"
```

Before committing, run `git diff --cached --stat` and confirm only Task 3 files are staged.

---

### Task 4: Stock Detail Return Context and Stale Context Guard

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Test: `dashboard/tests/stock-workspace.test.tsx`
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Extend StockEntryContext type test expectations**

In `dashboard/tests/stock-workspace.test.tsx`, add a test that renders market context:

```tsx
it('renders market entry context with trade date and monitor tab', async () => {
  render(
    <StockWorkspace
      initialAssetId="000001.SZ"
      entryContext={{
        sourceWorkspace: 'market',
        assetId: '000001.SZ',
        tradeDate: '2026-06-12',
        monitorTab: 'limit_up',
        query: '平安银行'
      }}
    />
  );

  expect(await screen.findByText(/Opened from Market Monitor/)).toBeInTheDocument();
  expect(screen.getByText(/2026-06-12/)).toBeInTheDocument();
  expect(screen.getByText(/limit_up/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Add AppShell stale-context and return tests**

In `dashboard/tests/app-shell.test.tsx`, add a mocked StockWorkspace test that triggers return actions:

```tsx
vi.doMock('../src/components/StockWorkspace', () => ({
  StockWorkspace: ({
    entryContext,
    onOpenNews,
    onOpenResearchReports,
    onOpenMarketMonitor
  }: {
    entryContext?: StockEntryContext;
    onOpenNews?: (context: StockEntryContext) => void;
    onOpenResearchReports?: (context: StockEntryContext) => void;
    onOpenMarketMonitor?: (context: StockEntryContext) => void;
  }) => (
    <div>
      <span>stock source {entryContext?.sourceWorkspace ?? 'manual'}</span>
      <span>stock news {entryContext?.newsId ?? 'none'}</span>
      <span>stock report {entryContext?.reportId ?? 'none'}</span>
      <span>stock date {entryContext?.tradeDate ?? 'none'}</span>
      <button type="button" onClick={() => onOpenNews?.(entryContext ?? {})}>return news</button>
      <button type="button" onClick={() => onOpenResearchReports?.(entryContext ?? {})}>return reports</button>
      <button type="button" onClick={() => onOpenMarketMonitor?.(entryContext ?? {})}>return market</button>
    </div>
  )
}));
```

Assert:

```tsx
expect(screen.getByText('stock source news')).toBeInTheDocument();
fireEvent.click(screen.getByRole('button', { name: 'return news' }));
expect(await screen.findByDisplayValue('贵州茅台公告')).toBeInTheDocument();

fireEvent.click(screen.getByRole('button', { name: 'Stock Workspace' }));
expect(await screen.findByText('stock source manual')).toBeInTheDocument();
expect(screen.getByText('stock news none')).toBeInTheDocument();
```

- [ ] **Step 3: Run focused failing tests**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: FAIL if `tradeDate` is missing from context rendering or Market return context is not wired.

- [ ] **Step 4: Extend StockEntryContext with trade date**

In `dashboard/src/components/StockWorkspace.tsx`, update the exported type:

```tsx
export type StockEntryContext = {
  assetId?: string;
  sourceWorkspace?: 'search' | 'news' | 'researchReports' | 'market' | 'watchlist' | 'strategy';
  query?: string;
  matchReason?: string;
  newsId?: string;
  eventKey?: string;
  reportId?: string;
  tradeDate?: string;
  monitorTab?: string;
};
```

Where the Entry Context panel renders IDs, include:

```tsx
{currentEntryContext.tradeDate ? <span>Trade Date {currentEntryContext.tradeDate}</span> : null}
{currentEntryContext.monitorTab ? <span>Monitor Tab {currentEntryContext.monitorTab}</span> : null}
```

- [ ] **Step 5: Ensure callbacks receive current context**

In `StockWorkspace`, confirm the existing buttons call:

```tsx
onOpenNews?.(currentEntryContext)
onOpenResearchReports?.(currentEntryContext)
onOpenMarketMonitor?.(currentEntryContext)
```

If any callback uses a freshly constructed partial object that omits `tradeDate`, replace it with `currentEntryContext`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: PASS for StockWorkspace and AppShell context tests.

- [ ] **Step 7: Commit Task 4**

```bash
git add dashboard/src/components/StockWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/tests/stock-workspace.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "fix: preserve stock return context"
```

Before committing, run `git diff --cached --stat` and confirm only Task 4 files are staged.

---

### Task 5: Final Verification and Worktree Hygiene

**Files:**
- Modify only files touched by Tasks 1-4 if verification exposes issues.

- [ ] **Step 1: Run full focused frontend tests**

Run:

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx tests/news-workspace.test.tsx tests/research-reports-workspace.test.tsx tests/market-monitor-workspace.test.tsx tests/stock-workspace.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd dashboard && npm run build
```

Expected: PASS with Vite build output and no TypeScript errors.

- [ ] **Step 3: Run e2e smoke tests**

Run:

```bash
cd dashboard && npm run test:e2e
```

Expected: PASS for the existing e2e suite.

- [ ] **Step 4: Inspect git state**

Run:

```bash
git status --short
git diff --cached --stat
```

Expected:

- `git diff --cached --stat` is empty.
- Existing unrelated dirty files may still appear in `git status --short`; do not stage or revert them.
- Phase 9 commits are separated from unrelated dirty worktree changes.

- [ ] **Step 5: Final review**

Use the verification-before-completion skill before claiming completion. Summarize:

- commits created for Phase 9 implementation,
- focused test results,
- build result,
- e2e result,
- any unrelated dirty worktree files left untouched.
