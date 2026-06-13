# News Quality Gate V1 Design

## Goal

Build a conservative news ingestion and filtering layer for the dashboard News tab. The system should collect public financial news on a 30-minute cadence, admit only high-quality candidates, persist at most three accepted items per refresh window, and show those same accepted items in the News tab.

The default optimization target is short-term trading relevance: theme catalysts, market emotion, policy shocks, sector supply-demand changes, listed-company events, and risk events.

## Non-Goals

- Do not ingest every Sina headline into the default News tab or downstream news-chain sentiment inputs.
- Do not present low-score news just to fill three slots.
- Do not rely on a large language model for V1 ranking.
- Do not claim continuous 24-hour collection unless a backend scheduler is running.
- Do not replace the existing durable news store; extend it with quality metadata and server-side selection.

## Data Flow

1. A backend news collector runs every 30 minutes.
2. Each run fetches a candidate pool from existing public sources, initially Sina Finance 7x24 plus finance homepage categories.
3. Candidates pass through a quality gate before they are eligible for dashboard display.
4. Only the top three accepted candidates are upserted into the news store with quality score and relevance reasons.
5. Rejected candidates are not stored as default news-chain inputs; the run keeps aggregate rejection counters for audit.
6. `/api/public-news` serves filtered results from the backend, not a client-side slice of the latest 200 rows.
7. The News tab defaults to the same accepted Top 3 items that were persisted.

## Quality Gate

Hard rejection removes candidates before scoring:

- Missing title or URL.
- Duplicate URL, duplicate source event ID, or near-duplicate title in the current run.
- Stale item outside the accepted freshness window, default 24 hours for display.
- Navigation, topic, marketing, live-page boilerplate, or low-information titles.
- Generic commentary without a named policy, sector, asset, commodity, macro data point, company, or market mechanism.

Scoring produces a 0-100 quality score:

- Freshness: newer items score higher; stale items decay quickly.
- Source/category quality: 7x24, company, market, macro, and focus categories are favored; opinion and generic other categories are penalized.
- Trading relevance: policy, regulation, production cuts, price moves, orders, M&A, earnings, buybacks, sanctions, tariffs, financing, defaults, and market liquidity receive positive weight.
- Asset or sector specificity: mapped stock, explicit sector, commodity, index, or policy theme increases score.
- Risk relevance: fraud, investigation, downgrade, debt pressure, accident, export control, and major negative events are kept when market-relevant.
- Duplicate and low-signal penalties reduce repeated or vague items.

Default admission threshold is `quality_score >= 70`. If fewer than three candidates meet the threshold, the run stores and returns fewer than three items. The UI states that no additional high-quality news passed the gate. The system must not keep lower-quality candidates as hidden downstream sentiment inputs.

## Server-Side Filtering

The backend should accept query parameters for:

- category
- q
- start_time and end_time
- asset_id or ts_code
- minimum quality score
- source
- limit and offset

Filtering and sorting happen in the backend. The frontend should no longer fetch 200 rows and filter locally for normal News tab interactions.

Default sort order is:

1. quality score descending
2. published time descending
3. collected time descending

## Scheduler

Add a backend collector that can be started with the dashboard process or as a separate command. V1 should use a conservative 30-minute interval.

Scheduler behavior:

- Run immediately on startup unless disabled.
- Then run every 30 minutes.
- Use an in-process lock to prevent overlapping refreshes.
- Keep the last successful refresh timestamp and last error available to the API.
- Store only the top three admitted high-quality items for default display and downstream news-chain sentiment inputs, while preserving aggregate counters to audit rejected candidates.

## Frontend

The News tab should show:

- The stored Top 3 accepted news items by default.
- Latest collection time and next scheduled collection time.
- Quality score and short reasons, such as `policy`, `semiconductor`, `mapped_stock`, `risk_event`.
- Server-side filters for category, search, and stock links.
- A clear empty state: `本轮无高质量新闻`.

Manual Refresh remains available, but it must use the same quality gate and should not bypass filtering.

## Error Handling

- If the source fetch fails, keep the previous accepted items visible and show a warning.
- If DB writes fail, use the existing JSON fallback only as a degraded mode.
- If no candidates pass the threshold, return an empty accepted list with counters, not low-quality filler.
- If the scheduler is disabled, the UI should say the collector is not running.

## Testing

Backend tests should cover:

- Hard rejection rules.
- Score calculation for high-value and low-value examples.
- At most three persisted accepted items per run.
- No filler when fewer than three pass.
- Server-side filters.
- Scheduler lock and refresh metadata.

Frontend tests should cover:

- Default Top 3 rendering.
- Empty high-quality state.
- Server-side filter calls.
- Quality score and reasons display.
- Refresh failure preserving previous rows.

## Acceptance Criteria

- News refresh cadence is 30 minutes.
- Each refresh run persists at most three accepted items.
- Default News tab renders those same persisted accepted items.
- Each displayed item has a quality score and reasons.
- Low-quality candidates are rejected before default display.
- Search and category filters are served by the backend.
- Manual and scheduled refresh use the same quality gate.
