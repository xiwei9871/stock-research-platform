# News Durable Store And Cross-Linking Phase 4 Design

## 1. Goal

Upgrade dashboard news from a JSON-cache display feed into a durable backend
news layer that can support:

1. the `News` workspace;
2. stock-specific related news in `Stock Workspace`;
3. future global search across stocks, news, research reports, and generated
   reports;
4. future news analysis and daily news features.

Phase 4 remains a local research dashboard feature. It should not introduce
paid news sources, broker actions, live trading controls, or high-frequency
real-time infrastructure.

## 2. Current Context

The dashboard already has:

- `News`: visible in the dashboard and backed by `PublicNewsService`.
- Sina Finance public news adapters under `stock_research.public_news`.
- `/api/public-news` and `/api/public-news/refresh`.
- A JSON cache at `outputs/dashboard/public_news_cache.json`.
- `Stock Workspace` with public-news related rows.
- `Research Reports` backed by database tables from Phase 3.

The project also already has news database tables:

- `research.news_event_source`
- `research.news_event_mention`
- `research.news_feature_daily`

Existing historical/news source work includes:

- `akshare_stock_news_em` for recent stock-specific Eastmoney news.
- `eastmoney_individual_notice` for disclosure notices.
- `eastmoney_research_report` for institution-report style events.
- `cninfo_disclosure_announcement` for official disclosure events.

The gap is that the dashboard's public news path still treats the JSON cache as
the primary store. That is good enough for display, but too weak for analysis,
cross-linking, and stock-level investigation.

## 3. Product Boundary

Phase 4 should build the durable news foundation, not a full news-intelligence
platform.

In scope:

- Persist public news refresh results to `research.news_event_source`.
- Preserve current Sina Finance categories.
- Read News workspace rows from the database first.
- Keep JSON cache as a fallback path.
- Add stock-specific news API backed by `research.news_event_mention`.
- Link News rows to `Stock Workspace` when a stock mention exists.
- Show freshness, source status, and fallback warnings.
- Keep refresh user-triggered or modestly periodic.

Out of scope:

- Full NLP sentiment scoring.
- LLM summarization.
- Websocket or second-level real-time updates.
- Paid feeds.
- Source crawling from the browser.
- Complex entity disambiguation.
- Market Monitor real-time conversion.

## 4. Category Strategy

Keep the current dashboard category set:

- `all`
- `live`
- `focus`
- `company`
- `market`
- `macro`
- `international`
- `opinion`
- `original`
- `other`

For database rows:

- `source_channel` stores the source-native channel label when available, such
  as `7x24`, `公司`, `市场`, or `宏观`.
- `metadata.category` stores the normalized dashboard category key, such as
  `live`, `company`, or `macro`.
- API responses expose `category` from `metadata.category`, falling back to
  a normalized `source_channel` only when metadata is missing.

This keeps dashboard filters stable while preserving source provenance.

## 5. Data Model

Use the existing tables as the canonical store.

### 5.1 `research.news_event_source`

Each public news item becomes one source row:

- `source_event_id`: stable deterministic ID.
- `source_name`: source adapter name, for example `sina_finance`.
- `source_channel`: source-native channel label.
- `title`: normalized title.
- `content`: summary/body when available.
- `published_at`: source publish time.
- `collected_at`: refresh collection time.
- `language`: default `zh`.
- `url`: public article URL when available.
- `hash_key`: deterministic duplicate key.
- `source_status`: `available`, `permission_denied`, or `disabled`.
- `metadata`: raw source metadata plus normalized category and raw payload.

The existing schema does not include `event_family`. Phase 4 should not depend
on adding that column for public-news display. If source normalizers already
produce `event_family`, preserve it in `metadata.event_family` unless a later
schema migration explicitly adds a column.

### 5.2 `research.news_event_mention`

Mentions link source rows to assets:

- `source_event_id`
- `asset_id`
- `ts_code`
- `stock_name`
- `mention_role`
- `mention_confidence`
- `theme_name`
- `theme_confidence`
- `mapping_method`
- `trade_date`

Phase 4 mention mapping should be deterministic and explainable:

- exact `ts_code` or six-digit code match;
- exact stock-name match;
- optional alias match if a local alias source already exists.

It should avoid fuzzy matching that can silently create false links.

### 5.3 JSON Cache Fallback

The JSON cache remains available for resilience:

- `refresh` may still write the JSON cache after successful source fetch.
- `list` falls back to JSON cache only when DB access fails or DB has no rows.
- API warnings must identify when fallback was used.

The DB path is the canonical read/write path for dashboard behavior.

## 6. Backend Architecture

Add focused backend units instead of growing `PublicNewsService` into a large
mixed responsibility class.

### 6.1 `NewsEventStore`

Responsibility:

- Upsert news source rows.
- Query source rows with filters:
  - category
  - source
  - query text
  - start/end time
  - asset ID or ts code through mention join
  - limit/offset
- Return freshness summary:
  - total rows
  - latest published time
  - latest collected time
  - source counts
  - category counts

Dependencies:

- database connection utilities;
- existing schema;
- no dependency on React/dashboard code.

### 6.2 `PublicNewsIngestionService`

Responsibility:

- Call public adapters such as Sina Finance.
- Normalize adapter items to `news_event_source` rows.
- Upsert database rows.
- Update JSON fallback cache.
- Run mention mapping for newly received rows.
- Return counts and warnings.

This service replaces the current refresh behavior as the canonical path.

### 6.3 `DashboardNewsReadModel`

Responsibility:

- Convert DB rows to dashboard API payloads.
- Attach category, source, freshness, and stock-link fields.
- Hide database implementation details from FastAPI routes.
- Fallback to JSON cache when the DB path is unavailable.

### 6.4 `NewsMentionMapper`

Responsibility:

- Load a compact asset dictionary from `core.asset_master`.
- Map titles/content to stock mentions.
- Upsert mention rows.
- Avoid overwriting unrelated mentions.

Mapping methods:

- `ts_code_exact`
- `symbol_exact`
- `stock_name_exact`
- `source_asset` for adapters that already provide asset identity.

## 7. API Design

### 7.1 `GET /api/public-news`

Existing endpoint stays stable, but becomes DB-first.

Query parameters:

- `source`
- `category`
- `q`
- `start_time`
- `end_time`
- `asset_id`
- `ts_code`
- `limit`
- `offset`

Response:

- `items`
- `total`
- `limit`
- `offset`
- `summary`
- `warnings`

Each item includes:

- `id`
- `source`
- `source_channel`
- `category`
- `title`
- `summary`
- `url`
- `published_at`
- `collected_at`
- `stocks`
- `metadata`

### 7.2 `POST /api/public-news/refresh`

Refresh remains explicit and dashboard-safe.

Behavior:

- Fetch public news adapters.
- Upsert DB rows.
- Update fallback cache.
- Map mentions.
- Return received/stored/updated/mention counts.
- Preserve warnings without clearing existing DB rows.

### 7.3 `GET /api/assets/{asset_id}/news`

New stock-specific endpoint.

Query parameters:

- `limit`
- `lookback_days`
- `category`
- `source`

Response:

- `asset_id`
- `items`
- `summary`
- `warnings`

Summary fields:

- `news_count_1d`
- `news_count_3d`
- `news_count_7d`
- `latest_published_at`
- `source_count`
- `category_counts`

This endpoint powers the `Stock Workspace` related-news panel.

### 7.4 Future Global Search Contract

Phase 4 should keep the read model compatible with a later grouped search
endpoint, but it does not need to build the full global search UI.

Future target:

- `GET /api/search?q=...`
- grouped results:
  - assets
  - news
  - research reports
  - generated reports

Phase 4 prepares news rows and stock links for that endpoint.

## 8. Frontend UX

### 8.1 News Workspace

The News workspace should keep the current visible behavior but become clearer
about data state.

Required UI:

- category tabs using the existing category set;
- keyword search;
- source filter when more than one source exists;
- refresh action;
- last successful DB collection time;
- fallback warning when JSON cache is used;
- stock links on rows that have mentions;
- row action to open the article URL when present.

Rows should remain dense and scan-first. Do not convert the page into large
decorative cards.

### 8.2 Stock Workspace

Replace keyword-only related news with DB-linked related news.

Panel behavior:

- Load `/api/assets/{asset_id}/news`.
- Show latest related rows with title, time, category, source, and URL action.
- Show compact counts for 1d/3d/7d.
- Guard against stale responses when switching stocks.
- If no DB-linked news exists, show an empty state and do not fallback to broad
  keyword matches without labeling it.

### 8.3 Cross-Linking

News rows with stock mentions should support:

- opening the selected stock in `Stock Workspace`;
- showing one or more mentioned stocks as compact chips;
- preserving the current News filters when navigating back.

Full global search can remain a later phase, but the row payloads should already
contain the fields it will need.

## 9. Refresh And Freshness Rules

Phase 4 follows the EOD/low-pressure operating model:

- No websocket.
- No aggressive polling.
- Manual refresh remains available.
- Optional modest auto-refresh may call the existing refresh endpoint no more
  often than the existing News page behavior.
- Refresh failures must not delete or hide existing DB rows.
- UI displays last successful `collected_at`.

If DB latest news is stale, show a small warning rather than blanking the page.

## 10. Error Handling

Backend:

- Adapter failures return warnings and preserve existing data.
- DB failures fall back to JSON cache when possible.
- Invalid filters return empty lists with warnings, not server errors.
- Mention mapping failures should not fail source ingestion.

Frontend:

- Display warnings in the page status area.
- Keep previous rows visible while refresh is in progress.
- Show loading state without layout shift.
- Show explicit fallback/stale labels.

## 11. Testing

Backend tests:

- normalizes public news items into DB rows;
- upserts duplicate rows idempotently;
- preserves `metadata.category`;
- lists news by category, source, query, and date;
- joins mentions for asset-specific news;
- falls back to JSON cache when DB read path is unavailable;
- refresh returns counts and warnings without clearing old rows.

Frontend tests:

- News workspace renders DB-backed rows and freshness;
- category filter calls the expected API parameters;
- refresh keeps existing rows on warning;
- stock chips open `Stock Workspace`;
- Stock Workspace fetches asset news and ignores stale responses.

Verification:

- backend pytest for dashboard news routes and store behavior;
- frontend unit tests for client and components;
- `npm run build`;
- Playwright smoke check on localhost.

## 12. Migration Notes

This phase should not require a destructive migration.

If a local database lacks the news tables, run the existing schema initializer.
If normalizers emit fields not present in the table, such as `event_family`,
store them inside `metadata` instead of changing the schema unless a dedicated
migration is explicitly planned.

Existing JSON cache files should remain valid. The dashboard can use them as
fallback data while the database store is empty or unreachable.

## 13. Implementation Sequence

Recommended sequence:

1. Add backend DB store and API tests.
2. Add ingestion normalization from `PublicNewsItem` to DB rows.
3. Add mention mapper using deterministic asset matching.
4. Change `/api/public-news` and `/api/public-news/refresh` to DB-first.
5. Add `/api/assets/{asset_id}/news`.
6. Update frontend client/types.
7. Update News workspace freshness, warnings, and stock links.
8. Update Stock Workspace related-news panel.
9. Run local browser smoke verification.

The implementation should keep commits small enough to review:

- backend store/read model;
- refresh ingestion and mention mapping;
- frontend News workspace;
- Stock Workspace integration;
- verification fixes.

## 14. Acceptance Criteria

Phase 4 is complete when:

- refreshing public news writes rows to `research.news_event_source`;
- `/api/public-news` returns DB-backed rows with category, source, freshness,
  and warnings;
- `/api/assets/{asset_id}/news` returns mention-linked stock news;
- News workspace still supports the existing category workflow;
- Stock Workspace shows DB-linked related news for a selected stock;
- JSON cache fallback still works and is visibly labeled;
- tests and local build pass;
- localhost smoke test confirms News and Stock Workspace are reachable.

