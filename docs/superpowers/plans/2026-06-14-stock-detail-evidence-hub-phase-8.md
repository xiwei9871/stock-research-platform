# Stock Detail Evidence Hub Phase 8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Stock Workspace into a stock-level evidence hub with preserved entry context from Search, News, Research, Market Monitor, and Watchlist.

**Architecture:** Keep existing backend endpoints for v1 and implement the hub primarily in `AppShell` and `StockWorkspace`. Extend the Stock handoff contract in the shell, pass context into the Stock page, and reorganize existing profile/news/research/signal/review data into identity, summary, evidence grid, and context rail sections.

**Tech Stack:** React/TypeScript dashboard, existing dashboard API client, Vitest, Playwright, current FastAPI/Python backend only if a contract gap is discovered.

---

## File Structure

Phase 8 files expected to change:

- Modify: `dashboard/src/components/AppShell.tsx`  
  Preserve stock handoff context and pass it into `StockWorkspace`.
- Modify: `dashboard/src/components/StockWorkspace.tsx`  
  Accept stock handoff props, render the Evidence Hub layout, build context rail and timeline, keep existing request-id safety.
- Modify: `dashboard/src/styles.css`  
  Add stock-detail evidence hub styles only. Patch-stage because this file has unrelated dirty Backtest/News/Monitor CSS.
- Modify: `dashboard/tests/app-shell.test.tsx`  
  Add/adjust tests for stock handoff from Global Search, News, Watchlist, and context remount. Patch-stage because this file has unrelated dirty hunks.
- Modify: `dashboard/tests/stock-workspace.test.tsx`  
  Add/adjust tests for Evidence Hub layout, entry context, local section errors, timeline, search matches in context rail, and stale request handling.
- Modify only if needed: `dashboard/src/api/types.ts`  
  Add a small frontend-only type if the handoff contract needs one. Patch-stage because this file has unrelated Backtest hunks.

Files not to stage during Phase 8:

- Current Backtest / Strategy Validation dirty files.
- Current News quality dirty files.
- Strategy experiment files.
- Untracked old plan drafts.
- `.superpowers/brainstorm/**` visual companion artifacts.

---

### Task 1: Worktree Boundary And Stock Handoff Contract

**Files:**
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Inspect current handoff state**

Run:

```bash
git status --short
git diff -- dashboard/src/components/AppShell.tsx dashboard/tests/app-shell.test.tsx
```

Expected: `AppShell.tsx` may be clean or contain only Phase 8 edits after work begins. `app-shell.test.tsx` may contain unrelated dirty hunks from previous work; do not stage those.

- [ ] **Step 2: Add failing tests for stock entry context**

In `dashboard/tests/app-shell.test.tsx`, add tests that verify:

```tsx
it('opens stock detail from global search with search context', async () => {
  apiMocks.fetchGlobalSearch.mockResolvedValueOnce(
    makeGlobalSearchPayload(
      makeGlobalSearchResult({
        type: 'asset',
        id: 'asset:CN:SH:600519',
        title: '贵州茅台',
        subtitle: '600519.SH',
        target: { workspace: 'stock', asset_id: 'CN:SH:600519', q: '600519' },
        match_reason: 'Exact code match',
        match_fields: ['asset_id']
      }),
      '600519'
    )
  );
  apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeAssetProfile('CN:SH:600519'));

  render(<App />);

  fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '600519' } });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(250);
  });
  fireEvent.click(await screen.findByRole('option', { name: /贵州茅台 600519.SH/ }));

  expect(await screen.findByText('Opened from Search')).toBeInTheDocument();
  expect(screen.getByText('Exact code match')).toBeInTheDocument();
});
```

Also add a test for opening from News:

```tsx
it('opens stock detail from news with news context', async () => {
  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: 'Open News workspace' }));
  fireEvent.click(await screen.findByRole('button', { name: /Open .* in Stock Workspace/ }));

  expect(await screen.findByText('Opened from News')).toBeInTheDocument();
});
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx
```

Expected: new context assertions fail because `StockWorkspace` does not yet receive or render stock handoff context.

- [ ] **Step 4: Implement stock handoff in `AppShell`**

Add a stock handoff type and state:

```tsx
type StockSourceWorkspace = 'manual' | 'search' | 'news' | 'researchReports' | 'market' | 'watchlist' | 'strategy';

type StockHandoff = WorkspaceHandoff & {
  sourceWorkspace?: StockSourceWorkspace;
  matchReason?: string;
  monitorTab?: string;
};

const [stockHandoff, setStockHandoff] = useState<StockHandoff>({
  query: '',
  assetId: '000001.SZ',
  sourceWorkspace: 'manual',
  version: 0
});
```

Replace `openStockWorkspace(assetId: string)` with:

```tsx
function openStockWorkspace(assetId: string, context: Partial<StockHandoff> = {}) {
  setSelectedAssetId(assetId);
  setStockHandoff((current) => ({
    query: context.query ?? '',
    assetId,
    sourceWorkspace: context.sourceWorkspace ?? 'manual',
    tradeDate: context.tradeDate,
    newsId: context.newsId,
    eventKey: context.eventKey,
    reportId: context.reportId,
    monitorTab: context.monitorTab,
    matchReason: context.matchReason,
    version: current.version + 1
  }));
  setWorkspaceMode('stock');
}
```

When handling global search stock results:

```tsx
openStockWorkspace(target.asset_id, {
  sourceWorkspace: 'search',
  query: target.q ?? result.title,
  matchReason: result.match_reason
});
```

Pass to StockWorkspace:

```tsx
<StockWorkspace
  key={`stock:${stockHandoff.version}`}
  initialAssetId={stockHandoff.assetId ?? selectedAssetId}
  entryContext={stockHandoff}
/>
```

Update News and Watchlist callbacks:

```tsx
onOpenAsset={(assetId) => openStockWorkspace(assetId, { sourceWorkspace: 'news', query: newsHandoff.query, newsId: newsHandoff.newsId })}
```

```tsx
<WatchlistWorkspace onOpenAsset={(assetId) => openStockWorkspace(assetId, { sourceWorkspace: 'watchlist' })} />
```

- [ ] **Step 5: Add minimal StockWorkspace prop handling**

In `StockWorkspace.tsx`, add prop typing so Task 1 tests can pass:

```tsx
export type StockEntryContext = {
  sourceWorkspace?: 'manual' | 'search' | 'news' | 'researchReports' | 'market' | 'watchlist' | 'strategy';
  query?: string;
  tradeDate?: string;
  newsId?: string;
  eventKey?: string;
  reportId?: string;
  monitorTab?: string;
  matchReason?: string;
};

type StockWorkspaceProps = {
  initialAssetId?: string;
  entryContext?: StockEntryContext;
};
```

Render a temporary but user-visible context line near the top:

```tsx
<p className="stock-entry-context">
  Opened from {labelForEntryContext(entryContext?.sourceWorkspace)}
  {entryContext?.matchReason ? ` · ${entryContext.matchReason}` : ''}
</p>
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx tests/stock-workspace.test.tsx
```

Expected: tests pass.

- [ ] **Step 7: Commit**

Patch-stage only Phase 8 hunks:

```bash
git add dashboard/src/components/AppShell.tsx dashboard/src/components/StockWorkspace.tsx
git add -p dashboard/tests/app-shell.test.tsx
git add -p dashboard/tests/stock-workspace.test.tsx
git diff --cached --stat
git commit -m "feat: preserve stock detail entry context"
```

---

### Task 2: Evidence Hub Layout In StockWorkspace

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Add failing Evidence Hub layout test**

In `dashboard/tests/stock-workspace.test.tsx`, update or add:

```tsx
it('renders the stock detail evidence hub sections', async () => {
  render(<StockWorkspace initialAssetId="000001.SZ" entryContext={{ sourceWorkspace: 'search', matchReason: 'Exact code match' }} />);

  expect(await screen.findByRole('heading', { name: /平安银行 000001.SZ/ })).toBeInTheDocument();
  expect(screen.getByText('Opened from Search')).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Stock identity' })).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Stock evidence summary' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Price & Events' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Market Monitor State' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Strategy Signal' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Research Coverage' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Evidence Timeline' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx
```

Expected: fails because section names/layout are not yet in the component.

- [ ] **Step 3: Implement layout helpers**

In `StockWorkspace.tsx`, add helper functions:

```tsx
function labelForEntryContext(source: StockEntryContext['sourceWorkspace'] = 'manual') {
  const labels: Record<NonNullable<StockEntryContext['sourceWorkspace']>, string> = {
    manual: 'Manual Load',
    search: 'Search',
    news: 'News',
    researchReports: 'Research Reports',
    market: 'Market Monitor',
    watchlist: 'Watchlist',
    strategy: 'Strategy Evidence'
  };
  return labels[source] ?? 'Manual Load';
}

function primarySignal(profile: AssetProfile | null) {
  return profile?.signals[0] ?? null;
}

function researchSummary(reports: AssetResearchReportResponse | null) {
  return reports?.summary ?? null;
}
```

- [ ] **Step 4: Reorganize JSX into Evidence Hub**

Keep existing calls and data state. Replace the long unstructured layout with:

```tsx
<section className="stock-detail-shell" aria-label="Stock detail evidence hub">
  <section className="stock-identity-band" aria-label="Stock identity">...</section>
  <section className="stock-detail-layout">
    <div className="stock-detail-main">
      <section className="workspace-band" aria-label="Price and event chart">...</section>
      <section className="stock-evidence-summary" aria-label="Stock evidence summary">...</section>
      <section className="stock-evidence-grid">...</section>
    </div>
    <aside className="stock-context-rail" aria-label="Stock context rail">...</aside>
  </section>
</section>
```

Use headings:

- `Price & Events`
- `Market Monitor State`
- `Strategy Signal`
- `Research Coverage`
- `Related News`
- `Research Reports`
- `Factor / Score Breakdown`
- `Review / Outcomes`
- `Evidence Timeline`
- `Search Matches`

For v1, Market Monitor State can display:

```tsx
<p className="muted">EOD monitor stock-list context will appear here when opened from Market Monitor.</p>
```

Do not add new API calls in this task.

- [ ] **Step 5: Keep existing behavior intact**

Ensure old visible content remains:

- `Score 82.4`
- factor group/name values
- news title
- primary signal
- evidence path
- research report title and `90d reports 4`

- [ ] **Step 6: Run tests**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx
```

Expected: stock workspace tests pass.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git diff --cached --stat
git commit -m "feat: reshape stock detail evidence hub"
```

---

### Task 3: Context Rail Actions And Evidence Timeline

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/tests/stock-workspace.test.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Add failing tests for actions and timeline**

In `stock-workspace.test.tsx`, add:

```tsx
it('renders context rail actions and timeline entries', async () => {
  render(<StockWorkspace initialAssetId="000001.SZ" entryContext={{ sourceWorkspace: 'news', newsId: 'news-1' }} />);

  expect(await screen.findByText('Opened from News')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open News workspace' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open Research Reports workspace' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open Market Monitor workspace' })).toBeInTheDocument();
  expect(screen.getByText('news-1')).toBeInTheDocument();
  expect(screen.getByText('平安银行相关新闻')).toBeInTheDocument();
  expect(screen.getByText('平安银行深度报告')).toBeInTheDocument();
  expect(screen.getByText('watch')).toBeInTheDocument();
});
```

In `app-shell.test.tsx`, verify action callbacks navigate:

```tsx
it('opens related workspaces from stock detail actions', async () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Open Stock Workspace workspace' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Open News workspace' }));
  expect(await screen.findByRole('heading', { name: 'News' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: action callback tests fail because StockWorkspace does not yet accept navigation callbacks.

- [ ] **Step 3: Add navigation callback props**

In `StockWorkspace.tsx`:

```tsx
type StockWorkspaceProps = {
  initialAssetId?: string;
  entryContext?: StockEntryContext;
  onOpenNews?: (context: StockEntryContext) => void;
  onOpenResearchReports?: (context: StockEntryContext) => void;
  onOpenMarketMonitor?: (context: StockEntryContext) => void;
};
```

Render action buttons:

```tsx
<button type="button" onClick={() => onOpenNews?.(entryContext ?? {})}>Open News workspace</button>
<button type="button" onClick={() => onOpenResearchReports?.(entryContext ?? {})}>Open Research Reports workspace</button>
<button type="button" onClick={() => onOpenMarketMonitor?.(entryContext ?? {})}>Open Market Monitor workspace</button>
```

Build timeline entries from existing data:

```tsx
const timelineEntries = [
  ...(visibleAssetNews?.items ?? []).map((item) => ({ key: `news:${item.news_id}`, label: item.title, date: item.published_at.slice(0, 10), type: 'News' })),
  ...(visibleResearchReports?.items ?? []).map((report) => ({ key: `research:${report.event_key}`, label: report.report_title, date: formatValue(report.publish_date ?? report.report_date), type: 'Research' })),
  ...profile.decisions.map((decision) => ({ key: `decision:${decision.event_id}`, label: decision.decision_label, date: decision.review_date, type: 'Review' }))
];
```

- [ ] **Step 4: Wire AppShell actions**

Pass callbacks:

```tsx
<StockWorkspace
  key={`stock:${stockHandoff.version}`}
  initialAssetId={stockHandoff.assetId ?? selectedAssetId}
  entryContext={stockHandoff}
  onOpenNews={() => {
    setNewsHandoff((current) => ({ query: stockHandoff.query ?? stockHandoff.assetId ?? '', assetId: stockHandoff.assetId, version: current.version + 1 }));
    setWorkspaceMode('news');
  }}
  onOpenResearchReports={() => {
    setResearchReportsHandoff((current) => ({ query: stockHandoff.assetId ?? '', assetId: stockHandoff.assetId, version: current.version + 1 }));
    setWorkspaceMode('researchReports');
  }}
  onOpenMarketMonitor={() => setWorkspaceMode('market')}
/>
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: tests pass.

- [ ] **Step 6: Commit**

Patch-stage mixed test file:

```bash
git add dashboard/src/components/AppShell.tsx dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git add -p dashboard/tests/app-shell.test.tsx
git diff --cached --stat
git commit -m "feat: add stock detail context actions"
```

---

### Task 4: Stock Detail Styling

**Files:**
- Modify: `dashboard/src/styles.css`
- Modify: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Add structural stability assertions**

In `stock-workspace.test.tsx`, add assertions that key wrappers exist:

```tsx
expect(screen.getByRole('region', { name: 'Stock identity' })).toHaveClass('stock-identity-band');
expect(screen.getByRole('complementary', { name: 'Stock context rail' })).toHaveClass('stock-context-rail');
```

If `aside` does not expose `complementary` in tests, use:

```tsx
expect(screen.getByLabelText('Stock context rail')).toHaveClass('stock-context-rail');
```

- [ ] **Step 2: Run tests to verify current structure**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx
```

Expected: fails if classes/roles are missing.

- [ ] **Step 3: Add stock detail styles**

In `styles.css`, add only stock detail selectors:

```css
.stock-detail-shell { display: grid; gap: 14px; }
.stock-identity-band { display: grid; grid-template-columns: minmax(220px, 1.4fr) repeat(4, minmax(120px, 1fr)); gap: 10px; }
.stock-detail-layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 14px; align-items: start; }
.stock-detail-main { display: grid; gap: 14px; min-width: 0; }
.stock-context-rail { display: grid; gap: 12px; min-width: 0; }
.stock-evidence-summary { display: grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap: 10px; }
.stock-evidence-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.stock-timeline { display: grid; gap: 6px; }
.stock-timeline-row { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 8px; min-height: 34px; }
```

Add responsive rules:

```css
@media (max-width: 980px) {
  .stock-detail-layout { grid-template-columns: 1fr; }
  .stock-context-rail { order: -1; }
  .stock-evidence-summary,
  .stock-evidence-grid,
  .stock-identity-band { grid-template-columns: 1fr; }
}
```

Adjust exact values to match existing CSS variables and style. Keep cards at 6px or existing radius. Do not add decorative gradients/orbs.

- [ ] **Step 4: Run tests and build**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx tests/app-shell.test.tsx
cd dashboard && npm run build
```

Expected: tests and build pass.

- [ ] **Step 5: Commit**

Patch-stage only stock-detail CSS:

```bash
git add dashboard/tests/stock-workspace.test.tsx
git add -p dashboard/src/styles.css
git diff --cached --stat
git commit -m "style: polish stock detail evidence hub"
```

---

### Task 5: Final Verification And Review

**Files:**
- Inspect: Phase 8 files.
- Modify only if verification reveals a bug; write failing test first.

- [ ] **Step 1: Confirm no staged changes**

Run:

```bash
git diff --cached --stat
git status --short
```

Expected: no staged changes. Dirty unrelated files may remain.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: selected tests pass.

- [ ] **Step 3: Run build**

Run:

```bash
cd dashboard && npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 4: Run e2e**

Run:

```bash
cd dashboard && npm run test:e2e
```

Expected: Playwright tests pass.

- [ ] **Step 5: Final review**

Review:

```bash
git log --oneline -10
git show --stat HEAD~4..HEAD
```

Expected: Phase 8 commits include only AppShell, StockWorkspace, stock tests, app-shell stock hunks, and stock CSS.

- [ ] **Step 6: Final report**

Report verification evidence:

```text
Phase 8 Stock Detail Evidence Hub complete.
Verification:
- npm test -- --run tests/stock-workspace.test.tsx tests/app-shell.test.tsx: passed
- npm run build: passed
- npm run test:e2e: passed
Remaining dirty worktree: unrelated Backtest, News, strategy experiment, and old plan draft changes remain unstaged.
```

---

## Self-Review

Spec coverage:

- Stock handoff context is covered by Task 1.
- Evidence Hub layout is covered by Task 2.
- Context rail actions and evidence timeline are covered by Task 3.
- Stable UI styling is covered by Task 4.
- Verification and dirty worktree boundary are covered by Task 5.

Scope check:

- The plan does not add a new backend aggregation endpoint.
- The plan preserves existing data sources and request-id safety.
- Market Monitor stock-row integration is represented as a v1 context note unless a future task adds direct monitor handoff.

Type consistency:

- `StockEntryContext` names use `sourceWorkspace`, `newsId`, `eventKey`, `reportId`, `monitorTab`, and `matchReason`, matching the design spec.
- `AppShell` handoff uses existing `WorkspaceHandoff` fields plus stock-specific optional fields.
