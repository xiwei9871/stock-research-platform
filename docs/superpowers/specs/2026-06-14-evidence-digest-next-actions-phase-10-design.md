# Evidence Digest And Next Actions Phase 10 Design

## Goal

Add an EOD evidence digest layer that turns the dashboard's linked sources into a short, explainable view of why a stock deserves attention and where the user should go next.

Phase 7 added the EOD Market Monitor, Phase 8 made Stock Detail the evidence hub, and Phase 9 completed reversible cross-workspace links. Phase 10 should make those connected sources easier to read by summarizing the available evidence from news, research reports, market state, and strategy signals without adding realtime behavior or AI-generated prose.

The user should be able to answer:

- Why is this stock on the screen today?
- Which evidence sources support or weaken the case?
- What risk flags are visible from the current EOD data?
- Which source workspace should I open next?

## Scope

Phase 10 includes:

- Add a deterministic backend evidence digest read endpoint.
- Build digest facts from existing local data sources: asset profile, public news, research reports, EOD market monitor stock lists, score, and watchlist/strategy signal rows.
- Add a compact Evidence Digest panel to Stock Detail.
- Add digest status to Home Cockpit's Today Focus rows.
- Add source-backed next action buttons that reuse the Phase 9 cross-workspace callbacks.
- Add focused backend and frontend tests for digest scoring, risk flags, empty states, and handoff behavior.

Phase 10 excludes:

- Realtime fetching, polling, or websocket behavior.
- AI-generated summaries or LLM calls.
- A persistent user investigation queue.
- URL deep links.
- A new graph database or durable cross-link relationship table.
- Full research report text ingestion or semantic ranking.
- Changing the core strategy scoring model.
- Cleaning unrelated dirty worktree changes.

## Product Behavior

### Stock Detail

Stock Detail should show an Evidence Digest section near the top of the evidence hub or in the context rail.

The digest should include:

- A short title such as `Strong evidence`, `Mixed evidence`, `Thin evidence`, or `Risk-heavy evidence`.
- An evidence score or bucket that is explainable from source counts and market/strategy state.
- Three to five concise facts. Examples:
  - `2 high-quality news items in the last 7 days`
  - `Latest report rating: 买入 from 华泰证券`
  - `Appears in EOD limit-up list`
  - `TopN score rank 12`
- Risk flags such as:
  - `recent broken limit-up`
  - `limit-down pressure`
  - `no recent research coverage`
  - `low accepted-news coverage`
  - `signal/news evidence mismatch`
- Next actions:
  - Open News
  - Open Research Reports
  - Open Market Monitor
  - Review Stock Detail

Each next action should be a real button and should preserve the best available source context from the digest response.

### Home Cockpit

Home Cockpit's Today Focus list should show a digest badge for the visible top focus assets.

Examples:

- `Strong evidence`
- `Mixed`
- `Thin`
- `Risk-heavy`

Clicking or activating a focus row should open Stock Detail for that asset. Phase 10 should not add a new `digest` source workspace. Home should either open Stock Detail with no source context or use an existing source context only when the row came from an existing workspace source.

Home should degrade gracefully. If digest loading fails, Today Focus should still render rank, asset id, and score.

## Recommended Approach

Use a small backend read endpoint and deterministic scoring rules.

This is the recommended approach because:

- Stock Detail and Home both need the same digest facts.
- The current frontend already calls multiple independent endpoints; duplicating digest logic in each component would create inconsistent scores and risk labels.
- The backend can reuse existing local read models and tests.
- Deterministic rules are easier to trust and debug than generated prose.

## Alternatives Considered

### Frontend-Only Digest

The frontend could compute a digest from data it already fetches.

This would be faster for Stock Detail because it already loads profile, news, and research. It is weaker for Home because Home would either need to fetch per-asset detail data or show a thinner digest. It also risks inconsistent logic between pages.

### AI Narrative Summary

An LLM could create richer prose from news, reports, and market state.

This is not appropriate for Phase 10. The platform is still building source coverage and deterministic UI behavior. AI summarization would add latency, cost, hallucination risk, prompt/version management, and a new trust problem before the source-backed digest contract is stable.

### Investigation Queue

A queue would let users save candidates for later review.

That is useful, but it introduces user state and workflow semantics. Phase 10 should first clarify why a candidate is worth reviewing before adding saved workflow state.

## Architecture

Add a backend digest boundary:

- Python endpoint: `GET /api/evidence-digest`
- TypeScript client: `fetchEvidenceDigest`
- TypeScript DTOs: `EvidenceDigestResponse`, `EvidenceDigestBucket`, `EvidenceDigestAction`, `EvidenceDigestRiskFlag`

The endpoint should accept:

- `asset_id` required
- `trade_date` optional, defaulting to the latest completed market date available to the dashboard
- `lookback_days` optional, defaulting to 90 for research and 7 for news where needed

The response should be read-only and deterministic.

`StockWorkspace` should call the endpoint for the selected asset and trade date and render the digest panel.

`HomeCockpit` should fetch lightweight digest data for its visible Today Focus rows. To keep Phase 10 small, Home should call the same endpoint for the top five assets in parallel. Do not add a batch endpoint in Phase 10.

## Digest Response Contract

Suggested response:

```json
{
  "asset_id": "000001.SZ",
  "canonical_asset_id": "000001.SZ",
  "trade_date": "2026-06-12",
  "title": "Mixed evidence",
  "score": 62,
  "bucket": "mixed",
  "facts": [
    {
      "kind": "news",
      "label": "2 accepted news items in 7d",
      "severity": "neutral",
      "source_ref": { "workspace": "news", "news_id": "n1", "asset_id": "000001.SZ" }
    }
  ],
  "risk_flags": [
    {
      "key": "thin_research",
      "label": "No recent research coverage",
      "severity": "warning"
    }
  ],
  "source_refs": {
    "news_id": "n1",
    "report_id": "r1",
    "event_key": "r1:000001.SZ",
    "monitor_tab": "limit_up"
  },
  "next_actions": [
    {
      "key": "open_news",
      "label": "Open News",
      "workspace": "news",
      "asset_id": "000001.SZ",
      "news_id": "n1",
      "query": "000001.SZ"
    }
  ],
  "warnings": []
}
```

Field rules:

- `score` is an integer from 0 to 100.
- `bucket` is one of `strong`, `mixed`, `thin`, `risk_heavy`.
- `facts` are concise and source-backed. They must not pretend to interpret report text beyond available structured fields.
- `risk_flags` are deterministic rule outputs.
- `source_refs` holds best available source identifiers for Phase 9 handoff.
- `next_actions` are frontend instructions, not backend navigation.
- `warnings` describe missing source data or fallback behavior.

## Deterministic Scoring

Phase 10 should use simple additive rules. Exact weights can be tuned during planning, but they should be stable and tested.

Recommended v1 scoring:

- News coverage:
  - accepted news in 7d: up to 15 points
  - high quality score or accepted durable source: up to 5 points
- Research coverage:
  - recent report in 90d: up to 15 points
  - rating or target price present: up to 5 points
- Market monitor:
  - appears in limit-up or auction list: up to 15 points
  - appears in broken-limit-up or limit-down list: risk flag and score penalty
- Strategy signal:
  - top score rank or watchlist signal: up to 20 points
  - risk tags: risk flag and score penalty
- Data completeness:
  - enough source coverage: up to 10 points
  - missing major source categories: risk flags

Bucket rules:

- `strong`: score >= 75 and no severe risk flags.
- `mixed`: score >= 45 with at least two source categories.
- `risk_heavy`: any severe market risk flag or multiple warning flags.
- `thin`: insufficient supporting evidence or score < 45.

## Backend Data Flow

The endpoint should reuse existing dashboard read functions where possible.

Inputs:

- asset id normalization used by Stock Detail and asset search.
- latest market date used by dashboard summary or market monitor.

Source reads:

- asset profile or score row for score/rank/signals.
- public news durable store filtered by asset id and recent window.
- research reports filtered by asset id or ts code.
- EOD market monitor stock lists for the requested date.

Output assembly:

1. Normalize asset id and resolve canonical asset id.
2. Load available evidence sources independently.
3. Convert each source into facts and candidate source refs.
4. Apply scoring and risk rules.
5. Build next actions from the best source refs.
6. Return warnings for missing or unavailable sources without failing the entire digest where possible.

## Frontend Design

### API Client

Add `fetchEvidenceDigest(assetId, options)` to `dashboard/src/api/client.ts`.

Add DTOs to `dashboard/src/api/types.ts`.

### StockWorkspace

Add local digest state:

- `evidenceDigest`
- `isEvidenceDigestLoading`
- `evidenceDigestError`

Use the existing stale request id pattern. A digest response for an old asset must not overwrite the current asset.

Render an Evidence Digest panel with:

- title and score/bucket badge;
- facts;
- risk flags;
- next action buttons.

Next action buttons should call existing callbacks:

- `onOpenNews`
- `onOpenResearchReports`
- `onOpenMarketMonitor`

The callbacks should use the digest source refs when available and fall back to the current stock context.

### HomeCockpit

Home should request digests for the top five `summary.topn_preview` assets after platform summary loads.

Render a compact digest badge in each Today Focus row.

If a digest is unavailable:

- show `Digest unavailable` only when there is an error for that row;
- otherwise keep the existing row layout.

Home should not block the whole page on digest fetches.

## Error Handling

Backend:

- If one source fails or has no data, return the digest with a warning when possible.
- If the asset cannot be resolved, return an HTTP error with a clear message.
- If market monitor data is unavailable for the requested date, omit market facts and include a warning.

Frontend:

- Stock Detail profile load remains independent from digest load.
- Digest failure should show a local error in the digest panel, not blank the stock page.
- Home digest failures should be row-local or silent with a small unavailable label.
- Stale digest responses must not overwrite current asset state.

## Accessibility

Evidence Digest should use:

- a heading such as `Evidence Digest`;
- visible text for score, bucket, facts, and risk flags;
- buttons for next actions, with labels like `Open digest news evidence`;
- no click-only rows.

The digest badge in Home should be text, not color-only.

## Testing

Backend tests should cover:

- strong digest when news, research, market, and strategy evidence are present;
- thin digest when source coverage is low;
- risk-heavy digest when market risk lists or risk tags are present;
- partial-source warning behavior;
- next action source refs for news, research, and market monitor.

Frontend tests should cover:

- `StockWorkspace` renders digest title, facts, risk flags, score/bucket, and next action buttons.
- Digest action buttons call existing workspace callbacks with source refs.
- Digest loading and error states are local to the digest panel.
- Stale digest response does not overwrite a newer stock.
- `HomeCockpit` shows digest badges for Today Focus rows.
- `HomeCockpit` still renders when digest calls fail.

Verification should include:

- backend pytest for the evidence digest endpoint and scoring helper;
- focused dashboard tests for StockWorkspace and HomeCockpit;
- `cd dashboard && npm run build`;
- `cd dashboard && npm run test:e2e`.

## Success Criteria

Phase 10 is complete when:

- A local EOD evidence digest endpoint returns deterministic, source-backed facts, risk flags, score/bucket, source refs, next actions, and warnings.
- Stock Detail shows the digest without breaking existing profile/news/research/market context behavior.
- Home Cockpit Today Focus rows show digest status without blocking the page.
- Next action buttons reuse Phase 9 handoff behavior.
- No realtime, AI generation, user queue, URL routing, or graph-store behavior is introduced.
- Focused backend/frontend tests, dashboard build, and e2e checks pass.
- Changes are committed separately from unrelated dirty worktree files.
