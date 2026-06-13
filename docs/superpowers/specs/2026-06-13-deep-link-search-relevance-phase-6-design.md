# Deep Link And Search Relevance Phase 6 Design

## Goal

Improve the Phase 5 global search so it behaves like a research terminal entry
point instead of a simple grouped keyword list.

Phase 6 should make search results easier to trust, rank, and act on:

- Better relevance scoring for stocks, news, research reports, and generated
  reports.
- Visible match reasons so the user can understand why a result appeared.
- Deeper handoff context so clicking a result opens the right workspace with
  the most specific local context available.
- Stable target DTOs that can later be promoted to URL deep links without
  changing search semantics again.

The implementation remains local, deterministic, read-only, and EOD-friendly.
It must not add external search services, embeddings, paid data sources, or a
new frontend router.

## Current State

Phase 5 added:

- Backend `GET /api/search?q=<query>&limit=<n>`.
- Result groups: `assets`, `news`, `research_reports`, `generated_reports`.
- A persistent top-bar `GlobalSearchBox`.
- Cross-workspace handoff to Stock, News, Research Reports, and Generated
  Reports.
- Stale frontend response protection.
- Generated report handoff with `trade_date`.

Known limitations:

- Relevance is simple and mostly source-order based.
- Result cards do not explain match reason.
- News and research report targets open the workspace with a query but do not
  select a specific row.
- Generated reports preserve query and date, but not a highlighted artifact.
- The target shape is useful but not yet a URL-level deep link contract.

## Non-Goals

- No semantic/vector search.
- No full-content research report indexing.
- No URL router migration in this phase.
- No persistent saved searches.
- No news quality gate implementation. That is covered by the separate
  `news-quality-gate-v1` spec and plan.
- No realtime market monitor or websocket behavior.

## Product Behavior

### Search Input

The existing global search input remains in the shell top bar.

Behavior:

- Minimum query length remains two trimmed characters.
- Results stay grouped by source.
- Each result displays:
  - title;
  - subtitle;
  - optional timestamp;
  - match reason;
  - optional score badge when useful for debugging or QA.
- Keyboard selection and stale response protections from Phase 5 remain.

### Relevance Priorities

Search should favor intent in this order:

1. Exact stock code, `ts_code`, or asset id.
2. Exact stock name.
3. Prefix symbol or name substring.
4. News or reports linked to the matched asset.
5. Title matches.
6. Summary/path/report-type matches.
7. Older or generic matches.

This does not merge all groups into one list; it improves ordering inside each
group and makes the reason visible.

### Deep Link Handoff

Use the existing AppShell state handoff rather than URL routes.

Targets should carry enough context for the destination workspace:

Stock:

```json
{
  "workspace": "stock",
  "asset_id": "CN:SH:600519"
}
```

News:

```json
{
  "workspace": "news",
  "news_id": "sina_finance:n1",
  "asset_id": "CN:SH:600519",
  "q": "茅台"
}
```

Research Reports:

```json
{
  "workspace": "researchReports",
  "report_id": "r1",
  "event_key": "r1:CN:SH:600519",
  "asset_id": "CN:SH:600519",
  "q": "茅台"
}
```

Generated Reports:

```json
{
  "workspace": "generatedReports",
  "path": "reports/daily_topn.md",
  "q": "topn",
  "trade_date": "2026-06-10"
}
```

The frontend should preserve these fields in handoff state. Phase 6 may select
or highlight a specific row in the destination if the workspace already has a
natural selected-row model. It should not add heavy routing just to support
highlighting.

## Backend Design

### DTO Additions

Extend each search result with:

```json
{
  "match_reason": "Exact code match",
  "match_fields": ["symbol", "asset_id"]
}
```

TypeScript and Python DTOs should tolerate absent fields during rollout, but
new results from `/api/search` should include both fields.

Field semantics:

- `match_reason`: short user-facing text, stable enough for tests.
- `match_fields`: small machine-readable list used for future badges and QA.

Examples:

- `Exact code match`
- `Stock name match`
- `Linked stock mention`
- `News title match`
- `Research report title match`
- `Broker match`
- `Generated report date match`
- `Generated report path match`

### Stock Relevance

Normalize query:

- Trim whitespace.
- Casefold latin text.
- Accept six-digit code with optional `.SH` or `.SZ`.

Ranking:

- `100`: exact `asset_id` or canonical id.
- `98`: exact `ts_code`.
- `95`: exact six-digit symbol.
- `90`: exact stock name.
- `80`: symbol prefix.
- `70`: name substring.

Targets stay unchanged.

### News Relevance

Use durable public news read model.

Signals:

- `title` contains query.
- `summary` contains query.
- linked stock `asset_id`, `ts_code`, or stock name matches query.
- category and source can be used as light tie-breakers, not hard filters.

Ranking:

- Linked exact asset/code match outranks plain text matches.
- Title matches outrank summary matches.
- Newer `published_at` wins ties.

Target should include `news_id`, optional `asset_id`, and `q`.

### Research Report Relevance

Use existing research report list read model.

Signals:

- `ts_code` or `asset_id` exact match.
- `stock_name` match.
- `report_title` match.
- `broker`, `analyst`, or `industry_name` match.

Ranking:

- Exact asset/code match.
- Stock name match.
- Report title match.
- Broker/analyst/industry match.
- Newer publish date wins ties.

Target should include `event_key` when available, because report ids can repeat
across assets.

### Generated Report Relevance

Use `load_report_links(trade_date)` for the latest market date by default, as
Phase 5 does.

Signals:

- title match.
- report type match.
- path match.
- trade date match.

Ranking:

- title match.
- report type match.
- path match.
- date match.

Target must include `path`, `q`, and `trade_date`.

## Frontend Design

### GlobalSearchBox

Display `match_reason` below or beside the subtitle using compact text.

Do not expand the dropdown into a large dashboard. Keep it a quick command
surface.

Rendering rules:

- Title remains the strongest visual element.
- Subtitle remains secondary context.
- Match reason is a muted one-line hint.
- Long text truncates; no layout shift from hover or keyboard highlight.

### AppShell Handoff

Continue using versioned handoff state from Phase 5.

Add optional fields to handoff objects only where needed:

- News: `newsId`, `assetId`.
- Research Reports: `eventKey`, `reportId`, `assetId`.
- Generated Reports: `path`, `tradeDate`.

If a workspace cannot yet select a specific row, it should still receive and
store the context for a later task.

### News Workspace

V1 behavior:

- Accept `initialNewsId?: string`.
- Apply `initialQuery`.
- If the matching news row is present after load/filter, visually mark it with a
  selected/highlight class.

No separate news detail page in this phase.

### Research Reports Workspace

V1 behavior:

- Accept `initialEventKey?: string` and `initialReportId?: string`.
- Apply `initialQuery`.
- After reports load, select the report matching `event_key`, falling back to
  `report_id`.

This uses the existing detail panel rather than creating a new page.

### Generated Reports Workspace

V1 behavior:

- Accept `initialPath?: string`.
- Apply `initialQuery` and `initialTradeDate`.
- After reports load, visually highlight or focus the report whose `path`
  matches `initialPath`.

If the path is absent from the loaded date, the empty state should remain clear
and not throw.

## Error Handling

- A failed group must not blank the whole search response.
- Each failed group adds a warning.
- Frontend search failure shows an inline dropdown error and leaves the current
  workspace untouched.
- Deep link handoff should degrade to query-only when specific ids are absent.
- If a specific id/path is not found after loading the destination workspace,
  show normal filtered results rather than an error modal.

## Testing

Backend:

- Stock exact code ranks above name substring.
- News linked-stock match gets a match reason.
- Research report target includes `event_key`.
- Generated report target includes `trade_date` and match reason.
- One failing group leaves other groups intact.

Frontend:

- Global search renders match reason.
- Clicking a news result passes `news_id` and query to News Workspace.
- Clicking a research report result selects the matching detail row.
- Clicking a generated report result loads the result trade date and highlights
  the matching path.
- Re-selecting the same result re-applies handoff context.
- Existing stock/news/research/generated navigation tests still pass.

Smoke:

- Mock `/api/search` should include match reason.
- Desktop smoke should still search `600519` and open Stock Workspace.

## Acceptance Criteria

- `/api/search` returns `match_reason` and `match_fields` for all new result
  items.
- Search groups remain stable: `assets`, `news`, `research_reports`,
  `generated_reports`.
- Result order inside each group is deterministic and relevance-weighted.
- Result UI shows why each result matched.
- News search results can hand off `news_id`.
- Research report results can hand off and select `event_key` when present.
- Generated report results preserve `trade_date` and `path`.
- Same-result re-selection still re-applies handoff context.
- Existing Phase 5 tests and smoke continue to pass.
- No external search service or paid data source is added.
