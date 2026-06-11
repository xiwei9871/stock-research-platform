# Research Reports Dashboard Phase 3 Design

## 1. Goal

Build a usable `Research Reports` workspace in the local dashboard using the
existing research-report database. The page should let the user search external
broker and institution report metadata by stock, date, broker, rating, and
source, then connect the result back to `Stock Workspace`.

This phase is a read-only dashboard feature. It must not trigger live scraping
or paid report downloads from the browser.

## 2. Current Context

The dashboard currently separates these concepts:

- `News`: public news flow, currently backed by a Sina Finance JSON cache.
- `Research Reports`: external broker and institution reports, currently a
  Phase 3 placeholder.
- `Generated Reports`: local artifacts produced by this project, currently
  still exposed as `Reports`.

The existing `Reports` page is not the broker research-report library. It reads
local generated artifacts from `/Users/xiwei/stock_research/reports` and should
remain separate from this feature.

The database already has production-shaped research-report tables:

- `research.stock_report_source`
- `research.stock_report_event`
- `research.stock_report_feature_daily`
- `research.stock_report_manual_review`
- `research.stock_report_search_task`

Current database inspection showed:

- `research.stock_report_source`: 57,418 rows
- `research.stock_report_event`: 57,418 rows
- `research.stock_report_feature_daily`: 922,509 rows
- Covered stocks: 3,367
- Latest source publish date: 2026-06-03

Known source names include:

- `cfi_ybyl`
- `eastmoney_research_report_em`
- `sohu_jlp_rating`
- `sina_report_page`
- `研报客 API`
- `慧博智能策略终端`

## 3. Product Boundary

Phase 3 should use the existing report database as the canonical read model.

In scope:

- Search and browse external research-report metadata.
- Filter by stock, date, broker, rating, source, and target-price availability.
- Open source links when available.
- Show latest reports inside `Stock Workspace`.
- Show data freshness and source coverage.

Out of scope:

- Browser-triggered scraping or adapter execution.
- Full-text paid report storage or display.
- PDF parsing improvements.
- News database migration.
- Reworking report adapters.

Adapters such as Eastmoney AkShare, Sina report pages, CFI, Yanbaoke, Hibor,
and CITICS-style authenticated sources remain offline/background ingestion
paths. The dashboard reads their stored output.

## 4. User Experience

### 4.1 Research Reports Workspace

The page should be stock-first.

Top area:

- Page title: `Research Reports`
- Compact freshness strip:
  - latest report date
  - total reports
  - covered stocks
  - source count
  - latest feature date if available

Search and filters:

- Primary search input accepts stock code, stock name, report title keyword, or
  broker keyword.
- Date range defaults to the last 90 days.
- Broker filter supports free text.
- Rating filter supports exact rating text from stored rows.
- Source filter supports stored `source_name`.
- `Has target price` toggle filters rows with `target_price IS NOT NULL`.

Main result list:

- Report date
- Stock code and stock name
- Report title
- Broker
- Rating
- Target price when available
- Source name
- Source confidence
- Source link action

The list should be dense and scan-first, not card-heavy.

Details panel:

- Opens when a row is selected.
- Shows title, broker, analyst, report date, source name, confidence, source
  URL, copyright note, raw summary, company view, industry view, risk summary,
  rating, rating change, target price, and target upside when present.
- Includes actions:
  - `Open Source`
  - `Open Stock Workspace`
  - `Copy URL`

Empty and stale states:

- Empty search results show the active filters and suggest clearing filters.
- If no reports exist in the database, the page should explain that the report
  library is empty and mention that offline ingestion needs to run.
- If latest report date is older than the latest complete market date, show a
  small freshness warning.

### 4.2 Stock Workspace Integration

Replace the Phase 3 placeholder in `Stock Workspace` with a compact research
reports panel for the selected stock.

Panel contents:

- Latest 5 to 10 reports for the stock.
- Report count over the last 30 and 90 days.
- Broker coverage count over the last 90 days.
- Latest rating.
- Latest report date.
- Latest target price when available.

Actions:

- `View all reports` opens `Research Reports` with the selected stock filter.
- Selecting a report opens the details panel or navigates to the full
  `Research Reports` page with that row selected.

The panel must guard against stale data when switching stocks. A response for a
previous stock must not overwrite the current stock.

## 5. Backend API

Add read-only dashboard API endpoints.

### 5.1 `GET /api/research-reports/summary`

Returns:

- `total_reports`
- `covered_stocks`
- `latest_publish_date`
- `latest_feature_date`
- `source_counts`
- `rating_counts`
- `broker_counts`

This endpoint supports page-level freshness and filter option previews.

### 5.2 `GET /api/research-reports`

Query parameters:

- `q`
- `asset_id`
- `ts_code`
- `broker`
- `rating`
- `source_name`
- `start_date`
- `end_date`
- `has_target_price`
- `limit`
- `offset`

Returns:

- `items`
- `total`
- `limit`
- `offset`
- `warnings`

Each item should include:

- `report_id`
- `asset_id`
- `ts_code`
- `stock_name`
- `industry_name`
- `report_title`
- `publish_date`
- `report_date`
- `broker`
- `analyst`
- `rating`
- `rating_change`
- `target_price`
- `target_upside`
- `source_type`
- `source_name`
- `source_confidence`
- `public_access`
- `copyright_note`
- `source_url`
- `raw_summary`
- `company_view`
- `industry_view`
- `risk_summary`
- `metadata`

### 5.3 `GET /api/assets/{asset_id}/research-reports`

Query parameters:

- `limit`
- `lookback_days`

Returns:

- latest reports for the asset
- summary metrics for 30-day and 90-day windows

This endpoint powers `Stock Workspace`.

## 6. Data Access

Use `research.stock_report_source` joined to `research.stock_report_event` by
`report_id`.

Use `core.asset_master` only for search enrichment and asset resolution.

Do not use `research.stock_report_feature_daily` as the primary source for the
report list. The feature table is useful for summary metrics, but current data
shows recent rows can be partial. The report list should come from source/event
rows directly.

Ordering:

- Default order is `publish_date DESC NULLS LAST`, then `updated_at DESC`.
- For stock-specific panels, order by report date descending and limit to the
  requested count.

Pagination:

- Default limit: 50
- Maximum limit: 200
- Offset-based pagination is sufficient for V1.

## 7. Copyright and Access Rules

The dashboard may show metadata, snippets, summaries, and local notes already
stored in the database. It must not expose paid full text as a normal dashboard
field.

The UI should preserve source attribution:

- source name
- broker
- source URL
- copyright note
- public access flag

Local file URLs from imported PDFs may be displayed as source references, but
the page should not imply that every user has permission to redistribute those
files.

## 8. Frontend Components

Add or update these components:

- `ResearchReportsWorkspace`
- `ResearchReportFilters`
- `ResearchReportTable`
- `ResearchReportDetailPanel`
- `StockResearchReportsPanel`

Add client API functions:

- `fetchResearchReportSummary`
- `fetchResearchReports`
- `fetchAssetResearchReports`

Add TypeScript types:

- `ResearchReportSummary`
- `ResearchReportItem`
- `ResearchReportResponse`
- `AssetResearchReportResponse`

The UI style should follow the existing Phase 2 workstation direction:

- compact rows
- restrained color
- clear typography
- stable table dimensions
- no nested cards
- no marketing-style layout

## 9. Testing

Backend tests:

- Summary endpoint returns counts and freshness fields.
- List endpoint filters by stock code/name, date range, broker, rating, source,
  and target-price availability.
- Pagination returns stable `total`, `limit`, and `offset`.
- Empty result returns an empty `items` list and no server error.
- Asset endpoint returns latest reports and summary metrics.

Frontend tests:

- `Research Reports` page loads summary and list data.
- Filters call the client with expected parameters.
- Empty state is visible for no results.
- Details panel opens from a selected row.
- Stock Workspace panel loads reports for the selected asset and ignores stale
  responses after asset changes.

Smoke tests:

- Navigation includes `Research Reports`.
- `Research Reports` route renders report rows when mocked data exists.
- `Stock Workspace` shows latest reports when mocked data exists.

## 10. Implementation Sequence

1. Add dashboard backend query module and API routes.
2. Add client API types and fetch functions.
3. Replace `ResearchReportsWorkspace` placeholder with searchable table and
   detail panel.
4. Replace `Stock Workspace` Phase 3 placeholder with latest reports panel.
5. Update tests.
6. Run backend, frontend, and smoke verification.

## 11. Open Decisions

The V1 decision is to keep adapter execution out of the dashboard. A later
phase can add a background refresh status page if ingestion orchestration
becomes a product requirement.

The news database migration remains separate. Current public news is useful for
front-end aggregation, but it is not yet a durable analysis store.
