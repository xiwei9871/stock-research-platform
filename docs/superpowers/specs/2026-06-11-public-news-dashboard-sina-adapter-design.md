# Public News Dashboard & Sina Adapter Design

## Goal

Build a local dashboard news window backed by a public-news backend layer.

The first source is Sina Finance. The first release runs on localhost only and
serves two purposes:

1. show users a readable categorized finance news feed in the existing
   dashboard;
2. create a normalized backend foundation that can later support news analysis,
   source expansion, deduplication, and classification.

This is a public news aggregation feature, not an investment recommendation
feature and not a trading signal feature.

## Product Scope

First release includes:

- a backend public-news module;
- a Sina Finance adapter;
- local cache/storage for normalized news items;
- dashboard API endpoints;
- a dashboard news window with source/category filters, keyword search, refresh,
  and original-link navigation.

First release does not include:

- user accounts or deployment;
- paid data providers;
- full article storage or republication;
- direct investment conclusions;
- real-time push notifications;
- multi-source deduplication beyond the normalized item key;
- LLM summarization.

## Source Boundary

Sina Finance is split into two adapter paths:

1. `7x24`: use the currently available public Sina live-feed path. The existing
   AKShare `stock_info_global_sina()` function can be used as a fallback, but the
   project adapter should own normalization so the dashboard contract does not
   depend on AKShare output names.
2. Categorized finance columns: use Sina public page or public JSON endpoints
   for category list items. Prefer JSON endpoints where discoverable; fall back
   to parsing list pages when needed.

The first release only stores list-level information:

- title;
- summary or brief text when available;
- source;
- normalized category;
- source channel;
- published time;
- original URL;
- raw payload for debugging.

It must not crawl and store full article bodies in the first release.

## Category Model

The dashboard uses a stable local category set:

| Category | Meaning |
| --- | --- |
| `all` | frontend-only aggregate filter |
| `focus` | top finance headlines and major events |
| `live` | 7x24 live finance feed |
| `company` | company, listed-company, and business news |
| `market` | A shares, HK stocks, US stocks, funds, futures, FX, gold, bonds |
| `macro` | domestic macro, policy, and economic data |
| `international` | overseas markets, global economy, and geopolitics |
| `opinion` | opinion leaders, columns, commentary, and blogs |
| `original` | Sina original, special reports, and deep-dive content |
| `other` | valid finance items that cannot be mapped confidently |

The adapter keeps source-specific channel labels separately from the normalized
category. This allows future sources to map their own columns into the same
dashboard categories without changing the UI contract.

## Backend Architecture

Add a `public_news` package with small, testable boundaries:

- `models.py`: normalized item dataclass or typed dict;
- `sina_adapter.py`: source-specific fetching and parsing;
- `normalize.py`: stable IDs, timestamp parsing, category mapping, text cleanup;
- `store.py`: local cache persistence and read queries;
- `service.py`: orchestration for refresh and dashboard reads.

The module must remain separate from the existing research news-feature chain.
Later integration is allowed, but the public-news feature should not depend on
TopN, factor scoring, or trading research workflows.

## Storage

Use the repository's existing backend persistence pattern where practical.

The logical item contract is:

- `news_id`: stable local ID;
- `source`: e.g. `sina_finance`;
- `source_channel`: source-native channel name;
- `category`: normalized category;
- `title`;
- `summary`;
- `url`;
- `published_at`;
- `collected_at`;
- `raw_id`;
- `raw_payload`;
- `status`: `available`, `parse_error`, or `source_error`.

Deduplication key:

1. prefer canonical original URL when available;
2. otherwise use `source + category + title + published_at`.

Retention:

- keep at least the most recent 7 days for localhost use;
- design queries so the retention window can later become 30 days without UI
  changes.

## API Contract

Add dashboard API endpoints:

- `GET /api/public-news`
  - filters: `source`, `category`, `q`, `limit`, `offset`;
  - returns normalized items sorted by `published_at desc`.
- `POST /api/public-news/refresh`
  - refreshes Sina categories;
  - returns counts by source/category plus warnings.

The read endpoint must work even if refresh has never succeeded. It should
return an empty list plus warnings instead of failing the whole dashboard.

## Dashboard UX

Add a news window to the existing dashboard shell.

Layout:

- source selector at the top, initially `新浪财经`;
- search input;
- refresh button;
- left category rail;
- right chronological news list.

Each news row shows:

- published time;
- category badge;
- source label;
- title;
- summary when available;
- original-link action.

The UI should be read-only. It should not imply recommendation, buy/sell
judgment, or automated decisioning.

## Error Handling

The adapter should treat external source instability as normal:

- network timeout: record source warning and keep cached data;
- parse failure for one item: skip that item and record a warning;
- whole category failure: keep other categories;
- no data: display an empty-state message in the dashboard.

The dashboard must distinguish between:

- no matching results for the current filter;
- source refresh failed but cached data exists;
- source refresh failed and no cache exists.

## Testing

Backend tests:

- normalize Sina live-feed rows into the public-news contract;
- normalize categorized rows into stable categories;
- build stable IDs and deduplicate repeated rows;
- store and query cached items with filters;
- return warnings rather than raising on source failure.

Dashboard tests:

- render the news panel with fixture API data;
- filter by category;
- search by keyword;
- show empty and error states;
- verify original-link action is rendered.

The first implementation should avoid live network dependence in tests. Use
fixtures or monkeypatched fetch responses.

## Implementation Order

1. Build normalized models and parser tests.
2. Implement Sina live-feed adapter.
3. Implement Sina category-list adapter with fixtures.
4. Add local store/cache and refresh service.
5. Add dashboard API endpoints.
6. Add dashboard news panel.
7. Run backend and dashboard verification.

## Open Constraints

- The feature is localhost-only in the first release.
- External endpoints may change; source-specific selectors and response parsing
  must be isolated inside the Sina adapter.
- The first release should not store full article bodies or copy protected
  content beyond short list summaries provided by public list feeds.
