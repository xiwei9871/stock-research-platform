# Review Queue And Action Inbox Phase 11 Design

## Goal

Build Phase 11 of the research dashboard as an EOD Review Queue / Action Inbox that turns Phase 10 Evidence Digest output into a daily list of stocks to review.

Phase 10 answers "why is this stock interesting and where should I go next?" at the single-stock and Home row level. Phase 11 should add the missing workbench layer: one workspace where the user can scan the day's candidate set, group candidates by evidence bucket, preview source-backed facts, and jump into Stock, News, Research Reports, or Market Monitor.

The user should be able to answer:

- Which stocks should I review first today?
- Which candidates have strong, mixed, thin, or risk-heavy evidence?
- Which evidence sources support each queue item?
- Which source workspace should I open next?

## Scope

Phase 11 includes:

- Add a deterministic read-only backend Review Queue endpoint.
- Build queue items from existing local EOD data: platform top candidates and Evidence Digest.
- Add a `Review Queue` workspace to the dashboard navigation and Home quick actions.
- Render grouped queue tabs or filters for `strong`, `mixed`, `risk_heavy`, and `thin`.
- Render a right-side evidence preview for the selected queue item.
- Reuse existing cross-workspace handoff behavior for next actions.
- Add backend and frontend tests for grouping, sorting, empty/error states, and handoff behavior.

Phase 11 excludes:

- Persistent user task state such as done, snooze, assigned reviewer, notes, or review history.
- Realtime fetching, polling, websockets, or intraday updates.
- AI-generated summaries or recommendations.
- Trading, rebalancing, or portfolio execution actions.
- Batch mutation jobs or source ingestion changes.
- URL deep-link route changes.
- Cleaning unrelated dirty worktree changes.

## Product Behavior

### Review Queue Workspace

The dashboard should add a first-class `Review Queue` workspace in the left navigation. It should sit near Home and Market Monitor because it is a daily operating surface, not a data lab.

The workspace should have three regions:

- Left queue controls: trade date, score version, queue group counts, and source filters.
- Center queue table: ranked queue items with asset id, rank, score, bucket, digest title, risk flag count, source coverage, and next action count.
- Right evidence preview: selected item digest facts, risk flags, warnings, and action buttons.

The first visible group should be `strong` when available. If there are no strong items, the workspace should select the first non-empty group in this order:

1. `mixed`
2. `risk_heavy`
3. `thin`

If every group is empty, show an honest empty state with the selected date and score version.

### Queue Groups

Queue items should be grouped by Evidence Digest bucket:

- `strong`: source-backed candidates with the clearest support.
- `mixed`: candidates with some support but meaningful caveats.
- `risk_heavy`: candidates with severe or multiple risk flags.
- `thin`: candidates with weak or missing source coverage.

Group counts should be visible even when a group is not selected. Selecting a group filters the center table and preserves the selected trade date.

### Queue Item Row

Each row should show:

- rank from the platform score preview or fallback ordering;
- asset id and best available display name;
- score;
- digest bucket/title;
- compact source coverage chips, such as `News`, `Research`, `Market`, `Strategy`;
- warning/risk count;
- a primary `Review` action that opens Stock Detail.

The table should be compact and scan-friendly. It should not use a marketing-card layout.

### Evidence Preview

Selecting a row should populate the preview pane with the item's Evidence Digest:

- digest title;
- score and bucket;
- three to five facts;
- risk flags;
- warnings;
- next action buttons.

The next action buttons should reuse the Phase 10 `EvidenceDigestAction` payload and the Phase 9 cross-workspace callbacks:

- `Open Stock Detail`
- `Open News`
- `Open Research Reports`
- `Open Market Monitor`

Actions should preserve asset id, query, source ids, report ids, event keys, monitor tabs, and trade date when available.

## Recommended Approach

Use a small backend read endpoint that composes platform summary rows with the existing Evidence Digest helper.

This is the recommended approach because:

- Evidence Digest scoring already lives in the backend and is tested.
- Home currently fetches digests per visible row; Review Queue needs the same idea at a workspace level.
- The backend can provide stable grouping and sorting so the frontend remains a renderer.
- The first version stays read-only and EOD, avoiding user-state semantics before the review workflow is proven.

## Alternatives Considered

### Frontend-Only Queue

The frontend could call `fetchPlatformSummary`, then call `fetchEvidenceDigest` for each row and group locally.

This is acceptable for a small Home widget but weak for a workspace. It duplicates grouping and sorting rules, increases client orchestration, and makes backend tests less meaningful.

### Persistent Investigation Queue

The queue could save item statuses like `new`, `reviewed`, `snoozed`, and `dismissed`.

This will likely be useful later, but it introduces user workflow state, schema design, migration concerns, and conflict semantics. Phase 11 should first prove the daily read-only queue.

### Portfolio Review Workspace

The queue could focus on current holdings and rebalance decisions.

That is a different product surface. It depends on durable portfolio/position state and should not be conflated with the EOD candidate review queue.

### Data Coverage Dashboard

The queue could focus on missing source coverage and adapter health.

Coverage diagnostics are useful, but they are operational tooling. Phase 11 should prioritize the end-user review workflow and show missing coverage only as item warnings.

## Backend Architecture

Add a backend module:

- `src/stock_research/dashboard/review_queue.py`

Expose an endpoint:

- `GET /api/review-queue`

Suggested query parameters:

- `trade_date` optional; defaults to latest completed market date from platform summary.
- `score_version` optional; defaults to `manual_v1`.
- `limit` optional; defaults to 20 and should be bounded to prevent accidental large fan-out.
- `lookback_days` optional; defaults to 90 for digest source windows.

The endpoint should:

1. Load platform summary with at least `limit` top candidate rows.
2. Select an anchor trade date deterministically.
3. Build an Evidence Digest for each candidate using that trade date, score version, and lookback window.
4. Create queue items from the score row plus digest.
5. Group items by digest bucket.
6. Sort groups deterministically.
7. Return warnings for partial source failures while preserving usable rows.

Do not add a batch Evidence Digest endpoint as a public contract in Phase 11. The queue endpoint can compose multiple digests internally because it owns the queue read model.

## Response Contract

Suggested response:

```json
{
  "trade_date": "2026-06-08",
  "score_version": "manual_v1",
  "generated_at": "2026-06-14T19:30:00+08:00",
  "groups": [
    {
      "bucket": "strong",
      "label": "High Conviction",
      "count": 2,
      "items": [
        {
          "queue_id": "2026-06-08:manual_v1:000001.SZ",
          "asset_id": "000001.SZ",
          "canonical_asset_id": "000001.SZ",
          "display_name": "平安银行",
          "rank": 3,
          "score": 82.4,
          "digest_title": "Strong evidence",
          "bucket": "strong",
          "source_kinds": ["strategy", "news", "research"],
          "risk_count": 0,
          "warning_count": 0,
          "next_action_count": 4,
          "digest": {
            "asset_id": "000001.SZ",
            "canonical_asset_id": "000001.SZ",
            "trade_date": "2026-06-08",
            "title": "Strong evidence",
            "score": 82,
            "bucket": "strong",
            "facts": [],
            "risk_flags": [],
            "source_refs": {},
            "next_actions": [],
            "warnings": []
          }
        }
      ]
    }
  ],
  "warnings": []
}
```

Field rules:

- `queue_id` is deterministic and stable for the selected trade date, score version, and asset.
- `groups` always includes all four buckets in display order, even when a bucket has zero items.
- `items` can be empty.
- `source_kinds` is derived from digest facts and should not claim a source kind unless a digest fact exists for it.
- `risk_count`, `warning_count`, and `next_action_count` are derived counts for table rendering.
- `digest` embeds the full Phase 10 digest so the frontend does not refetch per row.

## Sorting And Limits

Default ordering:

1. Bucket display order: `strong`, `mixed`, `risk_heavy`, `thin`.
2. Within each group, lower score rank first when present.
3. Then higher digest score.
4. Then asset id for deterministic ties.

`limit` should be bounded to a small EOD review size. Recommended v1 maximum is 50. The frontend should request 20 by default.

## Frontend Architecture

Add TypeScript DTOs:

- `ReviewQueueResponse`
- `ReviewQueueGroup`
- `ReviewQueueItem`

Add API client:

- `fetchReviewQueue(options)`

Add component:

- `dashboard/src/components/ReviewQueueWorkspace.tsx`

Modify:

- `dashboard/src/components/AppShell.tsx`
- `dashboard/src/components/HomeCockpit.tsx`
- related tests and e2e mocked responses.

`AppShell` should add a workspace mode named `reviewQueue` and pass callbacks so the queue can open existing workspaces:

- `onOpenStock(assetId, context)`
- `onOpenNews(context)`
- `onOpenResearchReports(context)`
- `onOpenMarketMonitor(context)`

The new workspace should not own cross-page state shape. It should adapt digest actions into the same handoff contexts already used by `StockWorkspace`.

## UI Behavior

Initial loading:

- Show a local loading state inside Review Queue.
- Keep the rest of the app shell usable.

Success:

- Select the first non-empty group in bucket display order.
- Select the first item in that group.
- Render group counts and the queue table.
- Render preview for the selected item.

Group selection:

- Update table rows and preview.
- If the selected group has rows, select its first row.
- If it has no rows, show an empty group state and clear the preview.

Row selection:

- Highlight the row.
- Update the preview pane.
- Do not navigate until the user activates an action.

Error:

- Show a local error state with a retry button.
- Do not break global navigation or other workspaces.

Empty:

- Show the selected trade date, score version, and a short empty message.
- Do not render fake candidates.

## Data Flow

```text
AppShell
  -> ReviewQueueWorkspace
    -> fetchReviewQueue({ tradeDate?, scoreVersion?, limit, lookbackDays })
      -> GET /api/review-queue
        -> load_platform_summary(top_n=limit)
        -> build_evidence_digest(asset_id, trade_date, score_version, lookback_days)
        -> group/sort/return queue DTO
    -> user selects row
    -> user clicks digest action
      -> AppShell handoff
      -> Stock / News / Research Reports / Market Monitor
```

## Error Handling

Backend:

- If platform summary is unavailable, return a valid response with empty groups and a warning when possible.
- If one digest fails, include a thin fallback item with a warning for that asset rather than failing the whole queue.
- If all candidates fail, return empty groups and warnings.
- Bound `limit` and `lookback_days`.

Frontend:

- Treat endpoint failure as a workspace-local error.
- Treat empty groups as normal.
- Treat item warnings as preview content.
- Do not trigger per-row refetches in v1.

## Testing

Backend tests should cover:

- response includes all bucket groups;
- strong/mixed/risk-heavy/thin grouping;
- deterministic queue id and sorting;
- digest failure degrades to an item warning;
- endpoint forwards query parameters and bounds limit.

Frontend tests should cover:

- API client serializes `tradeDate`, `scoreVersion`, `limit`, and `lookbackDays`;
- AppShell navigation includes Review Queue;
- Review Queue loads and renders group counts;
- selecting a group updates rows and preview;
- selecting a row updates preview;
- next action buttons call the correct AppShell handoff callbacks;
- local error and empty states.

E2E mocked flow should include:

- opening Review Queue from nav or Home quick action;
- seeing grouped queue content;
- opening Stock Detail from a queue row or preview action.

## Non-Goals And Guardrails

Phase 11 should not:

- write review state to the database;
- add new source ingestion behavior;
- introduce realtime update semantics;
- infer recommendations beyond deterministic digest fields;
- hide source gaps;
- stage unrelated dirty worktree changes.

## Completion Criteria

Phase 11 is complete when:

- `/api/review-queue` returns a deterministic EOD queue with grouped digest-backed items.
- Dashboard navigation includes `Review Queue`.
- The Review Queue workspace renders groups, rows, preview, warnings, and actions.
- Queue actions reuse existing cross-workspace handoff behavior.
- Backend focused tests pass.
- Frontend focused tests pass.
- Dashboard build passes.
- Existing mocked e2e flow is updated and passes.
- Phase 11 commits are separated from unrelated dirty worktree changes.
