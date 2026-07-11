# Theme Research Workflow Integration v1 Design

## Status

Approved direction: use one read-only Theme Research Context Service shared by Daily Review, Watchlist, and the stock workspace. Theme Research remains independent from the existing tech-bottleneck review dashboard and does not alter scoring, admission, or trading behavior.

## Purpose

Phase 10 makes reviewed Theme-driven Research context available inside existing investment-research workflows. It must answer, when evidence permits:

- which reviewed theme a company maps to;
- which reviewed industry-chain node the mapping uses;
- the node's value-capture, bottleneck, localization-gap, supply-tightness, and evidence scores;
- which accepted sources and reviewed claims support the context;
- which reviewed research objects changed recently;
- whether available evidence supports a theme context, a company-specific context, both, or neither.

The service does not infer price causality, recommend a security, mutate a watchlist, alter a score, or promote unreviewed research.

## Scope And Evidence Boundary

AI power is the first fully reviewed workflow theme. The humanoid-robotics sample remains visible as a theme-level evidence gap until Phase 2B public source-pack work is complete. Phase 10 must not convert sample claims, oral claims, lead-only sources, draft mappings, or unreviewed nodes into workflow context.

Eligible workflow context requires all of the following:

- company mapping `review_status=reviewed`;
- mapped node `node_review_status=reviewed`;
- at least one mapping evidence item;
- every source exposed as supporting evidence has `review_status=accepted`;
- reviewed claims must already satisfy the Phase 1.5 evidence gate.

## Architecture

Create `stock_research.dashboard.theme_research_context` as a focused read-model service. It reads the authoritative Phase 9 database through the configured runtime PostgreSQL service and returns stable, research-only payloads.

The service exposes four operations:

1. `load_asset_theme_context(asset_id)` returns eligible theme/node/company mappings and supporting evidence for one company.
2. `enrich_watchlist_rows(rows)` attaches the same compact context to existing watchlist rows without changing their order, score, priority, or signal fields.
3. `build_daily_theme_research_digest(trade_date)` returns reviewed mapped-company coverage, evidence gaps, and recent reviewed changes suitable for Daily Review.
4. `list_theme_research_updates(since, limit)` returns reviewed source, claim, node, and company-mapping review events from Phase 9 history.

Asset identifiers are normalized into canonical A-share company codes such as `300870.SZ`. Unknown identifiers produce an empty, valid context instead of an error.

## Read Models

Every top-level payload includes:

```json
{
  "research_only": true,
  "used_for_signal": false,
  "used_for_admission": false,
  "source": "research.theme_research_*",
  "warnings": []
}
```

An asset context contains:

- `asset_id` and `company_code`;
- `status`: `reviewed_context_available`, `evidence_gap`, or `not_mapped`;
- `driver_assessment`: `theme_supported`, `company_specific_supported`, `mixed_or_uncertain`, or `insufficient_evidence`;
- `themes[]`, with theme status and direct dashboard route;
- `mappings[]`, with node scores, relationship summary, materiality, mapping confidence, evidence items, accepted sources, and reviewed claims;
- `evidence_gap_count` and explicit reasons.

`driver_assessment` describes available research support only. It never states that a market move was caused by a theme. Unless reviewed evidence clearly distinguishes the two dimensions, the value is `mixed_or_uncertain`.

## Workflow Integration

### Daily Review

Add a `theme_research` section to live and persisted Daily Review payloads. The section reports reviewed theme count, mapped company count, recent reviewed update count, and unresolved evidence-gap count. It also includes compact rows linking to Theme Research and affected stock workspaces.

If Theme Research is unavailable, Daily Review remains usable and the section is `partial` with one concise warning.

### Watchlist

Existing watchlist endpoints retain their response shape and ordering. Each item gains `theme_research_context`. No existing `signal_score`, `primary_signal`, `signal_tags`, `risk_tags`, `priority`, or `must_watch` value may change.

### Stock Workspace

The asset profile gains `theme_research_context`. The frontend renders one unframed, compact Theme Research section that shows reviewed themes, mapped nodes, core scores, materiality, evidence state, and a link to the independent Theme Research dashboard. Empty context is represented explicitly without suggesting that research coverage is complete.

### Theme Tracking

Add read-only endpoints:

- `GET /api/assets/{asset_id}/theme-research-context`
- `GET /api/research/theme-decomposition/updates?since=...&limit=...`

Existing Theme Research endpoints remain authoritative for full theme detail.

## Error Handling

- Invalid dates and limits return HTTP 400.
- A missing asset mapping returns HTTP 200 with `status=not_mapped`.
- Runtime database failures do not silently fall back to artifacts in production DB mode. Direct context endpoints return a structured service error; Daily Review uses a partial section and warning so the rest of the report remains available.
- Eligibility filters are fail-closed. Missing review or evidence fields exclude a mapping and produce a reason in diagnostics.

## P1-P10 Verification

Add a verifier that produces JSON and Markdown reports. Each phase has named requirements and authoritative checks:

- P1: both baseline artifacts load and validate;
- P1.5: source, claim, and node review gates reject prohibited promotion;
- P2: AI power source pack passes; humanoid robotics is reported as an explicit incomplete Phase 2B evidence track, never as reviewed completion;
- P3: three decomposition templates load and initialize valid artifacts;
- P4: company mappings validate and are evidence-backed;
- P5: tech-bottleneck crosswalk validates without mutating the existing universe;
- P6: priority and review queue output validates;
- P7: dashboard read models and guardrails validate;
- P8: ingestion stages into a human review queue and does not auto-publish;
- P9: database schema, package parity, runtime privileges, snapshots, and rollback checks validate;
- P10: all three workflow consumers expose the same reviewed context and preserve signal/admission invariants.

The overall result distinguishes `complete`, `complete_with_declared_evidence_gap`, and `failed`. P1-P10 acceptance permits the declared Phase 2B evidence gap only because it is excluded from reviewed workflow use and reported explicitly; it may not be mislabeled complete.

## Testing

- Python unit tests cover normalization, eligibility, payload stability, empty mappings, update filtering, Daily Review degradation, and signal invariance.
- API tests cover both new endpoints and enriched existing responses.
- PostgreSQL integration tests use the dedicated test runtime service and prove fail-closed eligibility.
- Vitest covers Daily Review, Watchlist, and Stock Workspace rendering.
- Playwright verifies the authenticated workflow from watchlist and stock workspace into Theme Research.
- The P1-P10 verifier is tested against passing, failed, and declared-gap manifests.

## Non-goals

- completing Phase 2B source research;
- automatic market-causality attribution;
- recommendations or buy/sell language;
- writing Theme Research decisions from Daily Review, Watchlist, or Stock Workspace;
- merging the Theme Research and tech-bottleneck review dashboards;
- changing existing score, strategy, watchlist, or admission logic.

