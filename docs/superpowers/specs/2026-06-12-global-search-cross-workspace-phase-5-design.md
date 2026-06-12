# Global Search And Cross-Workspace Entry Phase 5 Design

## 1. Goal

Build Phase 5 of the research dashboard as an API-backed global search and
cross-workspace entry layer.

The dashboard now has separate durable surfaces for stocks, news, research
reports, generated reports, watchlists, market monitor, factor lab, and strategy
lab. Phase 5 should make those surfaces feel like one research workstation:
the user can type a stock code, stock name, news keyword, research report term,
or local report keyword in the persistent top bar and jump directly into the
right workspace.

The first version is read-only and local. It must not add paid data adapters,
semantic embeddings, external search services, or trading actions.

## 2. Existing Context

The V2 dashboard design defines global search as the main cross-workspace
connector. Phases already implemented the needed base surfaces:

- Phase 1: navigation shell, Home cockpit, EOD Market Monitor, Generated
  Reports naming, UI density refresh.
- Phase 2: Stock Workspace and Watchlist queue with selected-stock navigation.
- Phase 3: Research Reports read model and stock-level report panels.
- Phase 4: durable DB-backed News store, stock mention mapping, News links, and
  Stock Workspace related news.

Phase 5 should use these existing read models instead of inventing a parallel
index.

## 3. Product Boundary

Included:

- A backend `/api/search` endpoint.
- Grouped search results for:
  - stocks;
  - news;
  - research reports;
  - generated local reports.
- A persistent top-bar search control in the dashboard shell.
- Click behavior that opens the relevant workspace and carries enough target
  context to make the destination useful.
- Keyboard-friendly result navigation for common use.
- Tests for backend grouping, client URL shape, shell behavior, and navigation.

Excluded:

- Embedding/vector search.
- Full-text database indexes or search ranking infrastructure beyond simple SQL
  and deterministic scoring.
- News detail pages.
- Research report full-content rendering.
- Strategy run and factor search in the first cut.
- Server-side persistence of recent searches.

The first version should be useful with the data already stored locally. It can
be extended later without changing the basic result contract.

## 4. Backend API

Add:

`GET /api/search?q=<query>&limit=<n>`

Parameters:

- `q`: required non-empty query after trimming. If the cleaned query has fewer
  than two characters, return empty groups without hitting expensive read
  paths.
- `limit`: optional, default 5, bounded to a small value per group, for example
  10.

Response:

```json
{
  "query": "600519",
  "groups": [
    {
      "key": "assets",
      "label": "Stocks",
      "items": [
        {
          "id": "asset:CN:SH:600519",
          "type": "asset",
          "title": "贵州茅台",
          "subtitle": "600519.SH / SH",
          "timestamp": "",
          "target": {
            "workspace": "stock",
            "asset_id": "CN:SH:600519"
          },
          "score": 100,
          "metadata": {
            "symbol": "600519",
            "exchange": "SH"
          }
        }
      ]
    }
  ],
  "warnings": []
}
```

All result items use one stable shape:

- `id`: stable unique row id within the search response.
- `type`: `asset`, `news`, `research_report`, or `generated_report`.
- `title`: primary visible label.
- `subtitle`: compact context.
- `timestamp`: ISO-like date/time string when available, otherwise empty.
- `target`: route instruction for the frontend.
- `score`: deterministic numeric relevance score.
- `metadata`: small source-specific payload for badges and future extension.

## 5. Search Groups

### 5.1 Stocks

Use the existing asset search/read path if available. Match:

- exact six-digit code;
- `ts_code`;
- `asset_id`;
- stock name substring.

Ranking:

1. exact `asset_id` or `ts_code`;
2. exact six-digit symbol;
3. prefix symbol;
4. name substring.

Target:

```json
{ "workspace": "stock", "asset_id": "CN:SH:600519" }
```

The frontend opens Stock Workspace and sets the selected asset.

### 5.2 News

Use the Phase 4 dashboard news read model. Match `q` against title and summary,
with current DB-first plus JSON fallback behavior preserved. Return newest
matching rows first, with mentioned stocks in metadata.

Target:

```json
{
  "workspace": "news",
  "news_id": "sina_finance:...",
  "asset_id": "CN:SH:600519"
}
```

If a news result has a stock mention, the UI may show an `Open Stock` affordance.
Clicking the row itself opens News with the query preserved; clicking the stock
chip opens Stock Workspace.

### 5.3 Research Reports

Use the Phase 3 research report list read model. Match `q` against:

- stock code/name;
- report title;
- broker;
- analyst;
- industry name.

Target:

```json
{
  "workspace": "research_reports",
  "report_id": "r1",
  "asset_id": "CN:SH:600519",
  "q": "茅台"
}
```

The frontend opens Research Reports with the query filled. If the workspace has
a selected-detail affordance, it can select the matching report in a later
iteration.

### 5.4 Generated Reports

Use the existing generated report links read model. Match `q` against:

- report title;
- report type;
- path;
- trade date.

Target:

```json
{
  "workspace": "generated_reports",
  "path": "reports/daily_topn.md",
  "q": "topn"
}
```

The first cut can open Generated Reports with the query filled or open the
artifact link when the result target has a path.

## 6. Frontend Experience

Add a compact search control to the persistent shell top bar.

Behavior:

- Placeholder: `Search stocks, news, reports`.
- Do not search for empty input or one-character input.
- Debounce keystrokes modestly, for example 200-300 ms.
- Keep the dropdown open while the input is focused.
- Show grouped results in this order:
  1. Stocks
  2. News
  3. Research Reports
  4. Generated Reports
- Show a compact empty state only after a valid query returns no items.
- Show warnings in a subdued row at the bottom of the dropdown.
- Do not clear the current workspace on search failure.

Keyboard behavior:

- `ArrowDown` and `ArrowUp` move across visible result rows.
- `Enter` opens the highlighted result.
- `Escape` closes the dropdown.

Click behavior:

- Stock: set selected asset and open Stock Workspace.
- News: open News and preserve the search query. If the result has stock chips,
  stock chip click opens Stock Workspace.
- Research report: open Research Reports with query set.
- Generated report: open Generated Reports with query set. If direct artifact
  links already work safely, keep the row link available.

## 7. State And Navigation

`AppShell` should own cross-workspace context:

- selected workspace;
- selected asset id;
- optional initial query for News;
- optional initial query for Research Reports;
- optional initial query for Generated Reports.

Workspaces should accept these initial query props without introducing global
state libraries. Existing request guards should remain in place.

The global search component should not duplicate workspace-specific business
logic. It should call `fetchGlobalSearch`, render grouped result rows, and emit
`onOpenResult(result)`.

## 8. Error Handling

Backend:

- If one group fails, return other groups and add a warning.
- If all groups fail, return empty groups plus warnings.
- Never let an optional generated-report or news fallback failure make asset
  search unusable.

Frontend:

- Search failure shows one compact error row in the dropdown.
- Existing workspace content remains visible.
- Stale search responses must be ignored when a newer query returns first.
- Clearing the input closes results and cancels visible loading state.

## 9. Testing

Backend tests:

- `load_global_search` returns grouped stock/news/research/generated results.
- Short queries return empty groups.
- One failing group does not fail the whole response.
- Route forwards `q` and bounded `limit`.

Frontend tests:

- Client builds `/api/search?q=...&limit=...`.
- Top-bar search renders grouped results.
- Selecting a stock opens Stock Workspace with the selected asset.
- Selecting news/research/generated report results opens the correct workspace
  and carries the query.
- Stale search responses are ignored.
- Shell still exposes all existing workspaces.

Verification:

- Focused backend pytest for search and app route.
- Focused frontend Vitest for client and shell search behavior.
- Dashboard build.
- Playwright smoke with mocked search response.
- Local smoke on `http://127.0.0.1` for `/api/search?q=600519&limit=3`.

## 10. Rollout

Recommended implementation order:

1. Backend global search read model and route.
2. Frontend API types and client method.
3. Shell state and top-bar search UI.
4. Workspace initial-query props and result navigation.
5. Focused tests and local smoke.

## 11. Acceptance Criteria

Phase 5 is complete when:

- `/api/search` returns grouped local results without requiring external network
  calls.
- The dashboard top bar can search and navigate to Stock Workspace, News,
  Research Reports, and Generated Reports.
- Search failures do not blank the current workspace.
- Existing Phase 1-4 workspaces remain reachable.
- Focused backend/frontend tests, build, and browser smoke pass.
