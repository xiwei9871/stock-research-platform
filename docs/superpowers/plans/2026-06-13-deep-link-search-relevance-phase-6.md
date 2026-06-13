# Deep Link And Search Relevance Phase 6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make global search behave like a research-terminal entry point by adding deterministic relevance, visible match reasons, and specific cross-workspace deep-link handoff.

**Architecture:** Keep the Phase 5 grouped `/api/search` contract and AppShell state handoff. Add optional DTO fields for match explanation and target context, then teach News, Research Reports, and Generated Reports workspaces to select or highlight the specific result when the target data is available.

**Tech Stack:** Python dashboard service, pytest, React, TypeScript, Vitest, Testing Library, existing dashboard CSS.

---

## Worktree Guard

This worktree already contains unrelated modified and untracked files from earlier dashboard, strategy, and market-monitor work. Do not clean, revert, or bulk-stage the worktree while implementing this plan.

Use these commands before every commit:

```bash
git status --short
git diff -- dashboard/src/api/types.ts dashboard/src/components/GlobalSearchBox.tsx dashboard/src/components/AppShell.tsx dashboard/src/components/NewsWorkspace.tsx dashboard/src/components/ResearchReportsWorkspace.tsx dashboard/src/components/ReportsWorkspace.tsx dashboard/src/components/ReportPanel.tsx dashboard/src/components/GeneratedReportsWorkspace.tsx src/stock_research/dashboard/search.py tests/test_dashboard_search.py dashboard/tests/global-search-box.test.tsx dashboard/tests/app-shell.test.tsx dashboard/tests/news-workspace.test.tsx dashboard/tests/research-reports-workspace.test.tsx
```

Stage only Phase 6 files and hunks:

```bash
git add -p src/stock_research/dashboard/search.py tests/test_dashboard_search.py
git add -p dashboard/src/api/types.ts dashboard/src/components/GlobalSearchBox.tsx dashboard/src/components/AppShell.tsx dashboard/src/components/NewsWorkspace.tsx dashboard/src/components/ResearchReportsWorkspace.tsx dashboard/src/components/ReportsWorkspace.tsx dashboard/src/components/ReportPanel.tsx dashboard/src/components/GeneratedReportsWorkspace.tsx
git add -p dashboard/tests/global-search-box.test.tsx dashboard/tests/app-shell.test.tsx dashboard/tests/news-workspace.test.tsx dashboard/tests/research-reports-workspace.test.tsx
git diff --cached --stat
```

If a file contains unrelated dirty changes, keep them in the worktree and stage only the Phase 6 hunk.

## File Map

- `src/stock_research/dashboard/search.py`: backend search result construction, relevance scoring, match reasons, and target fields.
- `tests/test_dashboard_search.py`: backend relevance and target-contract tests.
- `dashboard/src/api/types.ts`: TypeScript DTO additions for match reason, match fields, event key, and handoff target context.
- `dashboard/src/components/GlobalSearchBox.tsx`: compact match reason rendering in the search dropdown.
- `dashboard/src/components/AppShell.tsx`: versioned handoff state with news id, research event key/report id, generated report path/date.
- `dashboard/src/components/NewsWorkspace.tsx`: accept `initialNewsId` and mark the matching visible news row.
- `dashboard/src/components/ResearchReportsWorkspace.tsx`: accept `initialEventKey`/`initialReportId` and select the matching loaded report.
- `dashboard/src/components/GeneratedReportsWorkspace.tsx`: pass `initialPath` to the generic reports workspace.
- `dashboard/src/components/ReportsWorkspace.tsx`: hold generated report path handoff and pass selected path to the report list.
- `dashboard/src/components/ReportPanel.tsx`: mark the selected generated report path.
- `dashboard/src/styles.css`: add compact, non-layout-shifting styles for match reason and selected rows if existing classes are not enough.
- `dashboard/tests/global-search-box.test.tsx`: match reason rendering test.
- `dashboard/tests/app-shell.test.tsx`: cross-workspace handoff tests.
- `dashboard/tests/news-workspace.test.tsx`: news and generated report highlighting tests.
- `dashboard/tests/research-reports-workspace.test.tsx`: research report deep-link selection test.

## Task 1: Backend Search Relevance Metadata

**Files:**
- Modify: `src/stock_research/dashboard/search.py`
- Test: `tests/test_dashboard_search.py`

- [ ] **Step 1: Add failing backend contract tests**

Append these tests to `tests/test_dashboard_search.py`. Reuse the existing monkeypatch patterns in that file; keep them near the current global search tests.

```python
def test_load_global_search_returns_asset_match_reasons_and_relevance(monkeypatch):
    from stock_research.dashboard import search

    monkeypatch.setattr(
        search,
        "search_assets",
        lambda q, limit=5: [
            {
                "asset_id": "CN:SH:600519",
                "symbol": "600519",
                "ts_code": "600519.SH",
                "name": "贵州茅台",
                "exchange": "SH",
                "instrument_type": "stock",
            },
            {
                "asset_id": "CN:SH:600500",
                "symbol": "600500",
                "ts_code": "600500.SH",
                "name": "中化国际",
                "exchange": "SH",
                "instrument_type": "stock",
            },
        ],
    )
    monkeypatch.setattr(search, "load_public_news", lambda **kwargs: {"items": []})
    monkeypatch.setattr(search, "load_research_reports", lambda **kwargs: {"items": []})
    monkeypatch.setattr(search, "get_latest_market_date", lambda: "2026-06-12")
    monkeypatch.setattr(search, "load_report_links", lambda trade_date=None: {"reports": []})

    payload = search.load_global_search("600519", limit=5)
    assets = payload["groups"][0]["items"]

    assert assets[0]["id"] == "CN:SH:600519"
    assert assets[0]["score"] > assets[1]["score"]
    assert assets[0]["match_reason"] == "Exact code match"
    assert "symbol" in assets[0]["match_fields"]


def test_load_global_search_news_linked_stock_has_match_reason(monkeypatch):
    from stock_research.dashboard import search

    monkeypatch.setattr(search, "search_assets", lambda q, limit=5: [])
    monkeypatch.setattr(
        search,
        "load_public_news",
        lambda **kwargs: {
            "items": [
                {
                    "news_id": "sina_finance:n1",
                    "source": "sina_finance",
                    "category": "公司",
                    "title": "贵州茅台发布经营公告",
                    "summary": "公司经营保持稳定",
                    "published_at": "2026-06-12T09:30:00+08:00",
                    "url": "https://example.com/n1",
                    "stocks": [
                        {
                            "asset_id": "CN:SH:600519",
                            "symbol": "600519",
                            "ts_code": "600519.SH",
                            "name": "贵州茅台",
                        }
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(search, "load_research_reports", lambda **kwargs: {"items": []})
    monkeypatch.setattr(search, "get_latest_market_date", lambda: "2026-06-12")
    monkeypatch.setattr(search, "load_report_links", lambda trade_date=None: {"reports": []})

    payload = search.load_global_search("600519", limit=5)
    item = payload["groups"][1]["items"][0]

    assert item["target"]["news_id"] == "sina_finance:n1"
    assert item["target"]["asset_id"] == "CN:SH:600519"
    assert item["match_reason"] == "Linked stock mention"
    assert item["match_fields"] == ["linked_stock"]


def test_load_global_search_research_report_target_includes_event_key(monkeypatch):
    from stock_research.dashboard import search

    monkeypatch.setattr(search, "search_assets", lambda q, limit=5: [])
    monkeypatch.setattr(search, "load_public_news", lambda **kwargs: {"items": []})
    monkeypatch.setattr(
        search,
        "load_research_reports",
        lambda **kwargs: {
            "items": [
                {
                    "event_key": "r1:CN:SH:600519",
                    "report_id": "r1",
                    "asset_id": "CN:SH:600519",
                    "ts_code": "600519.SH",
                    "stock_name": "贵州茅台",
                    "report_title": "贵州茅台深度跟踪",
                    "broker": "中信证券",
                    "analyst": "张三",
                    "industry_name": "白酒",
                    "published_at": "2026-06-11T10:00:00+08:00",
                }
            ]
        },
    )
    monkeypatch.setattr(search, "get_latest_market_date", lambda: "2026-06-12")
    monkeypatch.setattr(search, "load_report_links", lambda trade_date=None: {"reports": []})

    payload = search.load_global_search("600519", limit=5)
    item = payload["groups"][2]["items"][0]

    assert item["target"]["event_key"] == "r1:CN:SH:600519"
    assert item["target"]["report_id"] == "r1"
    assert item["match_reason"] == "Exact code match"
    assert "ts_code" in item["match_fields"]


def test_load_global_search_generated_report_keeps_trade_date_and_match_reason(monkeypatch):
    from stock_research.dashboard import search

    monkeypatch.setattr(search, "search_assets", lambda q, limit=5: [])
    monkeypatch.setattr(search, "load_public_news", lambda **kwargs: {"items": []})
    monkeypatch.setattr(search, "load_research_reports", lambda **kwargs: {"items": []})
    monkeypatch.setattr(search, "get_latest_market_date", lambda: "2026-06-12")
    monkeypatch.setattr(
        search,
        "load_report_links",
        lambda trade_date=None: {
            "reports": [
                {
                    "title": "TopN strategy validation",
                    "path": "reports/topn-validation.md",
                    "report_type": "validation",
                    "format": "markdown",
                    "trade_date": trade_date,
                }
            ]
        },
    )

    payload = search.load_global_search("validation", limit=5)
    item = payload["groups"][3]["items"][0]

    assert item["target"]["path"] == "reports/topn-validation.md"
    assert item["target"]["trade_date"] == "2026-06-12"
    assert item["match_reason"] == "Generated report title match"
    assert item["match_fields"] == ["title"]
```

- [ ] **Step 2: Run tests and verify they fail for the expected missing fields**

```bash
pytest tests/test_dashboard_search.py -q
```

Expected: the new tests fail because result items do not yet include `match_reason`, `match_fields`, and research report targets do not include `event_key`.

- [ ] **Step 3: Implement relevance helpers and DTO fields**

In `src/stock_research/dashboard/search.py`, add small helpers near the existing private helper functions. Use deterministic scores and keep warnings isolated per group.

```python
def _normalise_query(value: object) -> str:
    return str(value or "").strip().casefold()


def _code_forms(value: object) -> set[str]:
    raw = _normalise_query(value)
    if not raw:
        return set()
    forms = {raw}
    if "." in raw:
        forms.add(raw.split(".", 1)[0])
    if ":" in raw:
        forms.add(raw.rsplit(":", 1)[-1])
    return {form for form in forms if form}


def _contains(value: object, query: str) -> bool:
    return bool(query and query in _normalise_query(value))


def _asset_relevance(row: dict[str, Any], query: str) -> tuple[int, str, list[str]]:
    query_forms = _code_forms(query)
    asset_id = _normalise_query(row.get("asset_id"))
    ts_code = _normalise_query(row.get("ts_code"))
    symbol = _normalise_query(row.get("symbol"))
    name = _normalise_query(row.get("name"))

    if query and query == asset_id:
        return 100, "Exact code match", ["asset_id"]
    if ts_code and (query == ts_code or ts_code in query_forms):
        return 98, "Exact code match", ["ts_code"]
    if symbol and symbol in query_forms:
        return 95, "Exact code match", ["symbol"]
    if query and query == name:
        return 90, "Stock name match", ["name"]
    if query and symbol.startswith(query):
        return 80, "Stock symbol prefix match", ["symbol"]
    if _contains(name, query):
        return 70, "Stock name match", ["name"]
    return 10, "Source result", ["source"]


def _linked_stock_matches(stocks: object, query: str) -> bool:
    if not isinstance(stocks, list):
        return False
    query_forms = _code_forms(query)
    for stock in stocks:
        if not isinstance(stock, dict):
            continue
        values = [
            stock.get("asset_id"),
            stock.get("ts_code"),
            stock.get("symbol"),
            stock.get("name"),
        ]
        normalised = [_normalise_query(value) for value in values if value]
        if any(value == query for value in normalised):
            return True
        if any(value in query_forms for value in normalised):
            return True
        if any(_contains(value, query) for value in values):
            return True
    return False


def _first_linked_asset_id(stocks: object) -> str | None:
    if not isinstance(stocks, list):
        return None
    for stock in stocks:
        if isinstance(stock, dict) and stock.get("asset_id"):
            return str(stock["asset_id"])
    return None
```

Update `_result_item` so every new backend result can carry explanation fields.

```python
def _result_item(
    *,
    item_id: str,
    result_type: str,
    title: str,
    subtitle: str,
    target: dict[str, Any],
    score: int,
    match_reason: str,
    match_fields: list[str],
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": result_type,
        "title": title,
        "subtitle": subtitle,
        "timestamp": timestamp,
        "target": target,
        "score": score,
        "match_reason": match_reason,
        "match_fields": match_fields,
        "metadata": metadata or {},
    }
```

Update each item builder to pass score, reason, and fields. The relevant details are:

```python
score, reason, fields = _asset_relevance(row, query)
return _result_item(
    item_id=asset_id,
    result_type="asset",
    title=name or symbol or asset_id,
    subtitle=subtitle,
    target={"workspace": "stock", "asset_id": asset_id},
    score=score,
    match_reason=reason,
    match_fields=fields,
    metadata={...},
)
```

```python
if _linked_stock_matches(row.get("stocks"), query):
    score, reason, fields = 88, "Linked stock mention", ["linked_stock"]
elif _contains(row.get("title"), query):
    score, reason, fields = 76, "News title match", ["title"]
elif _contains(row.get("summary"), query):
    score, reason, fields = 62, "News summary match", ["summary"]
else:
    score, reason, fields = 30, "Source result", ["source"]

target = {"workspace": "news", "news_id": news_id, "q": query}
asset_id = _first_linked_asset_id(row.get("stocks"))
if asset_id:
    target["asset_id"] = asset_id
```

```python
if _contains(row.get("asset_id"), query) or _contains(row.get("ts_code"), query):
    score, reason, fields = 90, "Exact code match", ["asset_id" if _contains(row.get("asset_id"), query) else "ts_code"]
elif _contains(row.get("stock_name"), query):
    score, reason, fields = 84, "Stock name match", ["stock_name"]
elif _contains(row.get("report_title"), query):
    score, reason, fields = 72, "Research report title match", ["report_title"]
elif _contains(row.get("broker"), query):
    score, reason, fields = 58, "Broker match", ["broker"]
elif _contains(row.get("analyst"), query):
    score, reason, fields = 54, "Analyst match", ["analyst"]
elif _contains(row.get("industry_name"), query):
    score, reason, fields = 50, "Industry match", ["industry_name"]
else:
    score, reason, fields = 30, "Source result", ["source"]

target = {"workspace": "researchReports", "report_id": report_id, "q": query}
if row.get("event_key"):
    target["event_key"] = row["event_key"]
if row.get("asset_id"):
    target["asset_id"] = row["asset_id"]
```

```python
if _contains(row.get("title"), query):
    score, reason, fields = 68, "Generated report title match", ["title"]
elif _contains(row.get("report_type"), query):
    score, reason, fields = 60, "Generated report type match", ["report_type"]
elif _contains(row.get("path"), query):
    score, reason, fields = 54, "Generated report path match", ["path"]
elif _contains(row.get("trade_date"), query):
    score, reason, fields = 48, "Generated report date match", ["trade_date"]
else:
    score, reason, fields = 30, "Source result", ["source"]
```

Sort each group after mapping:

```python
items = sorted(
    items,
    key=lambda item: (int(item.get("score", 0)), str(item.get("timestamp") or "")),
    reverse=True,
)
```

For groups without timestamps, the same helper remains deterministic because the timestamp key becomes an empty string. If an existing loader already returns the requested limit, still sort the returned items before slicing:

```python
items = sorted(
    items,
    key=lambda item: (int(item.get("score", 0)), str(item.get("timestamp") or "")),
    reverse=True,
)[:limit]
```

This keeps high score first and newer ISO timestamps first on ties.

- [ ] **Step 4: Run backend tests**

```bash
pytest tests/test_dashboard_search.py -q
```

Expected: all tests in `tests/test_dashboard_search.py` pass.

- [ ] **Step 5: Commit backend relevance metadata**

```bash
git add -p src/stock_research/dashboard/search.py tests/test_dashboard_search.py
git diff --cached --stat
git commit -m "feat: add global search relevance metadata"
```

## Task 2: Global Search Match Reason UI

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/components/GlobalSearchBox.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/global-search-box.test.tsx`

- [ ] **Step 1: Add failing UI test for match reason rendering**

Add this test in `dashboard/tests/global-search-box.test.tsx` after the first successful render test.

```tsx
it('renders match reasons for search results', async () => {
  apiMocks.fetchGlobalSearch.mockResolvedValueOnce(
    makePayload({
      groups: [
        {
          id: 'assets',
          label: 'Assets',
          items: [
            makeResult({
              id: 'CN:SH:600519',
              title: '贵州茅台',
              subtitle: '600519.SH',
              match_reason: 'Exact code match',
              match_fields: ['symbol']
            })
          ]
        }
      ]
    })
  );

  render(<GlobalSearchBox onOpenResult={vi.fn()} />);
  await userEvent.type(screen.getByRole('searchbox'), '600519');

  expect(await screen.findByText('Exact code match')).toBeInTheDocument();
});
```

Update the `makeResult` helper in the same file to include default fields:

```tsx
match_reason: 'Exact code match',
match_fields: ['title'],
```

- [ ] **Step 2: Run the focused frontend test and verify it fails**

```bash
cd dashboard && npm test -- --run tests/global-search-box.test.tsx
```

Expected: the new test fails because `GlobalSearchBox` does not render `match_reason` yet, or TypeScript rejects the new properties.

- [ ] **Step 3: Extend TypeScript DTOs**

In `dashboard/src/api/types.ts`, extend target and result types:

```ts
export type GlobalSearchTarget = {
  workspace: string;
  asset_id?: string;
  news_id?: string;
  report_id?: string;
  event_key?: string;
  path?: string;
  q?: string;
  trade_date?: string;
};
```

```ts
export type GlobalSearchResult = {
  type: GlobalSearchResultType;
  id: string;
  title: string;
  subtitle?: string;
  metadata?: Record<string, unknown>;
  meta?: Record<string, unknown>;
  target: GlobalSearchTarget;
  score?: number;
  match_reason?: string;
  match_fields?: string[];
  asset_id?: string;
  source?: string;
  timestamp?: string;
  trade_date?: string;
  link?: string;
};
```

- [ ] **Step 4: Render the match reason compactly**

In `dashboard/src/components/GlobalSearchBox.tsx`, add a one-line reason under subtitle when present:

```tsx
{result.match_reason ? (
  <span className="global-search-option-reason">{result.match_reason}</span>
) : null}
```

Place it inside the existing option text block, after subtitle. Keep keyboard and click handlers unchanged.

In `dashboard/src/styles.css`, add:

```css
.global-search-option-reason {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted-text);
  font-size: 11px;
  line-height: 1.3;
}
```

- [ ] **Step 5: Run focused tests**

```bash
cd dashboard && npm test -- --run tests/global-search-box.test.tsx
```

Expected: all `GlobalSearchBox` tests pass.

- [ ] **Step 6: Commit match reason UI**

```bash
git add -p dashboard/src/api/types.ts dashboard/src/components/GlobalSearchBox.tsx dashboard/src/styles.css dashboard/tests/global-search-box.test.tsx
git diff --cached --stat
git commit -m "feat: show global search match reasons"
```

## Task 3: AppShell Deep-Link Handoff State

**Files:**
- Modify: `dashboard/src/components/AppShell.tsx`
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Add failing AppShell handoff tests**

In `dashboard/tests/app-shell.test.tsx`, add or update tests in the existing global search describe block.

```tsx
it('opens news search results with specific news context', async () => {
  const newsResult = makeGlobalSearchResult({
    type: 'news',
    title: '贵州茅台公告',
    target: {
      workspace: 'news',
      news_id: 'sina_finance:n1',
      asset_id: 'CN:SH:600519',
      q: '600519'
    }
  });
  apiMocks.fetchGlobalSearch.mockResolvedValueOnce(makeGlobalSearchPayload(newsResult, '600519'));
  apiMocks.fetchPublicNews.mockResolvedValueOnce({
    source: 'sina_finance',
    items: [
      {
        news_id: 'sina_finance:n1',
        source: 'sina_finance',
        category: '公司',
        title: '贵州茅台公告',
        summary: '经营更新',
        published_at: '2026-06-12T09:30:00+08:00',
        url: 'https://example.com/n1',
        stocks: []
      }
    ],
    categories: ['公司'],
    refreshed_at: '2026-06-12T09:31:00+08:00',
    count: 1,
    stored: true,
    warnings: []
  });

  render(<AppShell />);
  await userEvent.type(screen.getByRole('searchbox'), '600519');
  await userEvent.click(await screen.findByText('贵州茅台公告'));

  expect(await screen.findByRole('heading', { name: 'News' })).toBeInTheDocument();
  expect(await screen.findByLabelText('Selected news result')).toHaveTextContent('贵州茅台公告');
});
```

```tsx
it('opens generated report search results with path and trade date context', async () => {
  const generatedResult = makeGlobalSearchResult({
    type: 'generated_report',
    title: 'TopN strategy validation',
    target: {
      workspace: 'generatedReports',
      path: 'reports/topn-validation.md',
      q: 'validation',
      trade_date: '2026-06-10'
    }
  });
  apiMocks.fetchGlobalSearch.mockResolvedValueOnce(makeGlobalSearchPayload(generatedResult, 'validation'));
  apiMocks.fetchOverview.mockResolvedValueOnce({
    trade_date: '2026-06-10',
    generated_at: '2026-06-10T18:00:00+08:00',
    summary: {},
    reports: [
      {
        title: 'TopN strategy validation',
        path: 'reports/topn-validation.md',
        report_type: 'validation',
        format: 'markdown',
        size_bytes: 1024,
        modified_at: '2026-06-10T18:00:00+08:00'
      }
    ]
  });

  render(<AppShell />);
  await userEvent.type(screen.getByRole('searchbox'), 'validation');
  await userEvent.click(await screen.findByText('TopN strategy validation'));

  expect(await screen.findByRole('heading', { name: 'Generated Reports' })).toBeInTheDocument();
  expect(await screen.findByLabelText('Selected generated report')).toHaveTextContent('TopN strategy validation');
});
```

These tests intentionally depend on workspace behavior implemented in later tasks. Keep them failing until Tasks 4 and 6 are done if running the whole file early.

- [ ] **Step 2: Extend AppShell handoff type**

In `dashboard/src/components/AppShell.tsx`, replace the existing `QueryHandoff` shape with:

```tsx
type WorkspaceHandoff = {
  query: string;
  tradeDate?: string;
  newsId?: string;
  assetId?: string;
  eventKey?: string;
  reportId?: string;
  path?: string;
  version: number;
};
```

Use `WorkspaceHandoff` for news, research reports, and generated reports state.

- [ ] **Step 3: Preserve specific target context in openGlobalSearchResult**

Update the non-stock branches in `openGlobalSearchResult`:

```tsx
if (workspace === 'news') {
  setNewsHandoff((current) => ({
    query,
    newsId: result.target.news_id,
    assetId: result.target.asset_id,
    version: current.version + 1
  }));
  setActiveWorkspace('news');
  return;
}
```

```tsx
if (workspace === 'researchReports') {
  setResearchReportsHandoff((current) => ({
    query,
    eventKey: result.target.event_key,
    reportId: result.target.report_id,
    assetId: result.target.asset_id,
    version: current.version + 1
  }));
  setActiveWorkspace('researchReports');
  return;
}
```

```tsx
if (workspace === 'generatedReports') {
  setGeneratedReportsHandoff((current) => ({
    query,
    tradeDate: result.target.trade_date ?? result.trade_date,
    path: result.target.path,
    version: current.version + 1
  }));
  setActiveWorkspace('generatedReports');
  return;
}
```

Pass the fields to workspaces:

```tsx
<ResearchReportsWorkspace
  key={researchReportsHandoff.version}
  initialQuery={researchReportsHandoff.query}
  initialEventKey={researchReportsHandoff.eventKey}
  initialReportId={researchReportsHandoff.reportId}
/>
```

```tsx
<GeneratedReportsWorkspace
  key={generatedReportsHandoff.version}
  initialQuery={generatedReportsHandoff.query}
  initialTradeDate={generatedReportsHandoff.tradeDate}
  initialPath={generatedReportsHandoff.path}
/>
```

```tsx
<NewsWorkspace
  key={newsHandoff.version}
  initialQuery={newsHandoff.query}
  initialNewsId={newsHandoff.newsId}
  onOpenAsset={openStockWorkspace}
/>
```

- [ ] **Step 4: Run typecheck-compatible focused tests after workspace tasks**

After Tasks 4, 5, and 6 are complete, run:

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx
```

Expected: AppShell search handoff tests pass.

- [ ] **Step 5: Commit AppShell handoff state**

Commit this task only after the workspace prop additions compile.

```bash
git add -p dashboard/src/components/AppShell.tsx dashboard/tests/app-shell.test.tsx
git diff --cached --stat
git commit -m "feat: preserve global search handoff context"
```

## Task 4: News Deep-Link Highlighting

**Files:**
- Modify: `dashboard/src/components/NewsWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/news-workspace.test.tsx`

- [ ] **Step 1: Add failing NewsWorkspace highlight test**

Add this test inside the `NewsWorkspace` describe block in `dashboard/tests/news-workspace.test.tsx`.

```tsx
it('marks the initial news result when it is loaded', async () => {
  apiMocks.fetchPublicNews.mockResolvedValueOnce({
    source: 'sina_finance',
    items: [
      {
        news_id: 'sina_finance:n1',
        source: 'sina_finance',
        category: '公司',
        title: '贵州茅台公告',
        summary: '经营更新',
        published_at: '2026-06-12T09:30:00+08:00',
        url: 'https://example.com/n1',
        stocks: []
      }
    ],
    categories: ['公司'],
    refreshed_at: '2026-06-12T09:31:00+08:00',
    count: 1,
    stored: true,
    warnings: []
  });

  render(<NewsWorkspace initialQuery="600519" initialNewsId="sina_finance:n1" />);

  expect(await screen.findByLabelText('Selected news result')).toHaveTextContent('贵州茅台公告');
});
```

- [ ] **Step 2: Run focused test and verify it fails**

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx
```

Expected: TypeScript or assertion failure because `initialNewsId` and selected markup do not exist.

- [ ] **Step 3: Add selected news prop and markup**

In `dashboard/src/components/NewsWorkspace.tsx`, extend props:

```tsx
type NewsWorkspaceProps = {
  initialQuery?: string;
  initialNewsId?: string;
  onOpenAsset?: (assetId: string) => void;
};
```

Update the component signature:

```tsx
export function NewsWorkspace({ initialQuery = '', initialNewsId, onOpenAsset }: NewsWorkspaceProps) {
```

When rendering each news item, compute selection:

```tsx
const isSelected = initialNewsId ? item.news_id === initialNewsId : false;
```

Apply stable attributes to the item wrapper:

```tsx
<article
  key={item.news_id}
  className={`news-card${isSelected ? ' news-card--selected' : ''}`}
  aria-label={isSelected ? 'Selected news result' : undefined}
  aria-current={isSelected ? 'true' : undefined}
>
```

Keep the existing visible layout and asset-opening controls unchanged.

- [ ] **Step 4: Add selected card style**

In `dashboard/src/styles.css`, add:

```css
.news-card--selected {
  border-color: var(--accent);
  box-shadow: inset 3px 0 0 var(--accent);
}
```

If the existing card selector uses another class name, apply the modifier to that existing class instead of renaming all cards.

- [ ] **Step 5: Run focused tests**

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx
```

Expected: all news workspace tests pass.

- [ ] **Step 6: Commit news highlighting**

```bash
git add -p dashboard/src/components/NewsWorkspace.tsx dashboard/src/styles.css dashboard/tests/news-workspace.test.tsx
git diff --cached --stat
git commit -m "feat: highlight deep-linked news results"
```

## Task 5: Research Report Deep-Link Selection

**Files:**
- Modify: `dashboard/src/components/ResearchReportsWorkspace.tsx`
- Test: `dashboard/tests/research-reports-workspace.test.tsx`

- [ ] **Step 1: Add failing research report selection test**

Add this test inside `describe('ResearchReportsWorkspace', ...)` in `dashboard/tests/research-reports-workspace.test.tsx`.

```tsx
it('selects the initial event key after reports load', async () => {
  apiMocks.fetchResearchReports.mockResolvedValueOnce({
    items: [
      {
        event_key: 'r-old:CN:SH:600519',
        report_id: 'r-old',
        asset_id: 'CN:SH:600519',
        ts_code: '600519.SH',
        stock_name: '贵州茅台',
        report_title: '贵州茅台旧报告',
        broker: '中信证券',
        analyst: '张三',
        industry_name: '白酒',
        published_at: '2026-06-01T10:00:00+08:00',
        rating: '买入',
        target_price: null,
        summary: '旧报告'
      },
      {
        event_key: 'r-new:CN:SH:600519',
        report_id: 'r-new',
        asset_id: 'CN:SH:600519',
        ts_code: '600519.SH',
        stock_name: '贵州茅台',
        report_title: '贵州茅台深度跟踪',
        broker: '国泰君安',
        analyst: '李四',
        industry_name: '白酒',
        published_at: '2026-06-12T10:00:00+08:00',
        rating: '增持',
        target_price: null,
        summary: '新报告'
      }
    ],
    count: 2,
    warnings: []
  });

  render(<ResearchReportsWorkspace initialQuery="茅台" initialEventKey="r-new:CN:SH:600519" />);

  expect(await screen.findByRole('heading', { name: '贵州茅台深度跟踪' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: '贵州茅台旧报告' })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run focused test and verify it fails**

```bash
cd dashboard && npm test -- --run tests/research-reports-workspace.test.tsx
```

Expected: TypeScript or assertion failure because the workspace does not accept `initialEventKey`.

- [ ] **Step 3: Add deep-link props and selection effect**

In `dashboard/src/components/ResearchReportsWorkspace.tsx`, extend props:

```tsx
type ResearchReportsWorkspaceProps = {
  initialQuery?: string;
  initialEventKey?: string;
  initialReportId?: string;
};
```

Update the component signature:

```tsx
export function ResearchReportsWorkspace({
  initialQuery = '',
  initialEventKey,
  initialReportId
}: ResearchReportsWorkspaceProps = {}) {
```

After reports load or when initial ids change, select the matching report. If the file already has an effect that preserves `selectedReport`, fold this logic into that effect so there is only one selected-report decision per payload change.

```tsx
useEffect(() => {
  if (!reports.length) {
    setSelectedReport(null);
    return;
  }

  const deepLinkedReport = reports.find((report) => (
    (initialEventKey && report.event_key === initialEventKey) ||
    (!initialEventKey && initialReportId && report.report_id === initialReportId)
  ));

  if (deepLinkedReport) {
    setSelectedReport(deepLinkedReport);
    return;
  }

  setSelectedReport((current) => {
    if (current) {
      const preserved = reports.find((report) => report.event_key === current.event_key);
      if (preserved) {
        return preserved;
      }
    }
    return reports[0] ?? null;
  });
}, [reports, initialEventKey, initialReportId]);
```

- [ ] **Step 4: Run focused tests**

```bash
cd dashboard && npm test -- --run tests/research-reports-workspace.test.tsx
```

Expected: all research report workspace tests pass.

- [ ] **Step 5: Commit research deep-link selection**

```bash
git add -p dashboard/src/components/ResearchReportsWorkspace.tsx dashboard/tests/research-reports-workspace.test.tsx
git diff --cached --stat
git commit -m "feat: select deep-linked research reports"
```

## Task 6: Generated Report Deep-Link Highlighting

**Files:**
- Modify: `dashboard/src/components/GeneratedReportsWorkspace.tsx`
- Modify: `dashboard/src/components/ReportsWorkspace.tsx`
- Modify: `dashboard/src/components/ReportPanel.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/news-workspace.test.tsx`

- [ ] **Step 1: Add failing generated report highlight test**

Add this test in the `ReportsWorkspace` describe block in `dashboard/tests/news-workspace.test.tsx`.

```tsx
it('marks the initial generated report path after reports load', async () => {
  apiMocks.fetchOverview.mockResolvedValueOnce({
    trade_date: '2026-06-10',
    generated_at: '2026-06-10T18:00:00+08:00',
    summary: {},
    reports: [
      {
        title: 'TopN strategy validation',
        path: 'reports/topn-validation.md',
        report_type: 'validation',
        format: 'markdown',
        size_bytes: 1024,
        modified_at: '2026-06-10T18:00:00+08:00'
      }
    ]
  });

  render(
    <ReportsWorkspace
      initialQuery="validation"
      initialTradeDate="2026-06-10"
      initialPath="reports/topn-validation.md"
    />
  );

  expect(await screen.findByLabelText('Selected generated report')).toHaveTextContent('TopN strategy validation');
});
```

- [ ] **Step 2: Run focused test and verify it fails**

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx
```

Expected: TypeScript or assertion failure because `initialPath` and selected report markup do not exist.

- [ ] **Step 3: Thread initialPath through generated report components**

In `dashboard/src/components/GeneratedReportsWorkspace.tsx`:

```tsx
type GeneratedReportsWorkspaceProps = {
  initialQuery?: string;
  initialTradeDate?: string;
  initialPath?: string;
};
```

```tsx
export function GeneratedReportsWorkspace({
  initialQuery,
  initialTradeDate,
  initialPath
}: GeneratedReportsWorkspaceProps = {}) {
  return (
    <ReportsWorkspace
      title="Generated Reports"
      description="Review generated research artifacts and validation outputs."
      ariaLabel="Generated Reports"
      initialQuery={initialQuery}
      initialTradeDate={initialTradeDate}
      initialPath={initialPath}
    />
  );
}
```

In `dashboard/src/components/ReportsWorkspace.tsx`, extend props:

```tsx
type ReportsWorkspaceProps = {
  title?: string;
  description?: string;
  ariaLabel?: string;
  initialQuery?: string;
  initialTradeDate?: string;
  initialPath?: string;
};
```

Pass the selected path:

```tsx
<ReportPanel reports={visibleReports} isLoading={isLoading} selectedPath={initialPath} />
```

- [ ] **Step 4: Mark the matching report in ReportPanel**

In `dashboard/src/components/ReportPanel.tsx`, extend props:

```tsx
type ReportPanelProps = {
  reports: ReportLink[];
  isLoading?: boolean;
  selectedPath?: string;
};
```

Update the signature:

```tsx
export function ReportPanel({ reports, isLoading = false, selectedPath }: ReportPanelProps) {
```

When rendering each report item, compute:

```tsx
const isSelected = selectedPath ? report.path === selectedPath : false;
```

Apply stable attributes to the report card/link wrapper:

```tsx
<article
  key={report.path}
  className={`report-card${isSelected ? ' report-card--selected' : ''}`}
  aria-label={isSelected ? 'Selected generated report' : undefined}
  aria-current={isSelected ? 'true' : undefined}
>
```

Use the existing class name if the current file uses a different report item class.

- [ ] **Step 5: Add selected generated report style**

In `dashboard/src/styles.css`, add:

```css
.report-card--selected {
  border-color: var(--accent);
  box-shadow: inset 3px 0 0 var(--accent);
}
```

- [ ] **Step 6: Run focused tests**

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx
```

Expected: all report and news workspace tests pass.

- [ ] **Step 7: Commit generated report highlighting**

```bash
git add -p dashboard/src/components/GeneratedReportsWorkspace.tsx dashboard/src/components/ReportsWorkspace.tsx dashboard/src/components/ReportPanel.tsx dashboard/src/styles.css dashboard/tests/news-workspace.test.tsx
git diff --cached --stat
git commit -m "feat: highlight deep-linked generated reports"
```

## Task 7: Integration Verification And Smoke

**Files:**
- Modify only if tests reveal stale fixtures: `dashboard/tests/app-shell.test.tsx`, `dashboard/tests/client.test.ts`, Playwright smoke mocks.

- [ ] **Step 1: Run backend search tests**

```bash
pytest tests/test_dashboard_search.py -q
```

Expected: pass.

- [ ] **Step 2: Run focused frontend tests**

```bash
cd dashboard && npm test -- --run tests/global-search-box.test.tsx tests/app-shell.test.tsx tests/news-workspace.test.tsx tests/research-reports-workspace.test.tsx tests/client.test.ts
```

Expected: pass.

- [ ] **Step 3: Run TypeScript build**

```bash
cd dashboard && npm run build
```

Expected: build completes without TypeScript errors.

- [ ] **Step 4: Run backend dashboard app tests**

```bash
pytest tests/test_dashboard_app.py tests/test_dashboard_news.py -q
```

Expected: pass.

- [ ] **Step 5: If Playwright smoke mocks fail because `/api/search` fixtures lack new optional fields, update the mock result**

Use this shape in the mock item:

```ts
{
  id: 'CN:SH:600519',
  type: 'asset',
  title: '贵州茅台',
  subtitle: '600519.SH',
  score: 95,
  match_reason: 'Exact code match',
  match_fields: ['symbol'],
  target: {
    workspace: 'stock',
    asset_id: 'CN:SH:600519'
  },
  metadata: {}
}
```

- [ ] **Step 6: Run available dashboard smoke**

Run the repo's existing smoke command. If the package exposes a named script, use it:

```bash
cd dashboard && npm run test:e2e
```

If there is no `test:e2e` script, run the existing Playwright command from `dashboard/package.json`.

Expected: search smoke still opens Stock Workspace for `600519`; no dropdown layout overlap.

- [ ] **Step 7: Commit any fixture-only integration updates**

Only commit if Step 5 changed test fixtures:

```bash
git add -p dashboard/tests dashboard/playwright.config.ts dashboard/e2e
git diff --cached --stat
git commit -m "test: update global search smoke fixtures"
```

- [ ] **Step 8: Final worktree check**

```bash
git status --short
git log --oneline -6
```

Expected: Phase 6 commits are visible. Unrelated dirty files may remain exactly as they were before this plan.

## Self-Review

- Spec coverage: Task 1 covers backend scoring, match reasons, event key, and generated report date/path targets. Task 2 covers visible match reasons. Task 3 carries target context through AppShell. Task 4 covers News `initialNewsId`. Task 5 covers Research Reports `initialEventKey`/`initialReportId`. Task 6 covers Generated Reports `initialPath`. Task 7 covers integration and smoke.
- Placeholder scan: no implementation step depends on undefined behavior or postponed decisions.
- Type consistency: the target field names are `news_id`, `asset_id`, `report_id`, `event_key`, `path`, `q`, and `trade_date`; React handoff props convert only where component prop naming is camelCase.
