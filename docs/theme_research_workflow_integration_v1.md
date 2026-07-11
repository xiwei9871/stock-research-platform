# Theme Research Workflow Integration v1

## Status

Phase 10 integrates reviewed Theme Research context into Daily Review, Watchlist, and Stock Workspace. The independent Theme Research dashboard remains the full-detail research surface; the existing tech-bottleneck review dashboard remains a separate workflow.

## Shared Context

All consumers use `stock_research.dashboard.theme_research_context`. A company mapping enters workflow context only when:

- the mapping is reviewed;
- the mapped node is reviewed;
- mapping evidence exists;
- mapping evidence resolves to accepted sources.

Unreviewed candidates return `evidence_gap`; companies without candidates return `not_mapped`; dependency failures return `unavailable` inside existing workflow payloads.

Every payload includes:

```text
research_only=true
used_for_signal=false
used_for_admission=false
```

Theme context never changes Watchlist priority, signal score, signal tags, risk tags, admission, strategy output, or operator decisions.

## API

```text
GET /api/assets/:asset_id/theme-research-context
GET /api/research/theme-decomposition/updates?since=YYYY-MM-DD&limit=100
```

The asset endpoint returns reviewed theme, node, company mapping, node scores, mapping evidence, accepted sources, reviewed claims, exclusions, and guardrails.

The updates endpoint merges accepted/reviewed source, claim, node, and theme review events with reviewed company-mapping revisions. Lead-only, draft, blocked, and rejected transitions are excluded.

Invalid `since` or a limit outside `1-500` returns HTTP 400. A company without a mapping returns HTTP 200 with `status=not_mapped`.

## Daily Review

Daily Review contains a `theme_research` section and a structured `theme_research` digest. Persisted historical Daily Review artifacts are enriched at read time, so old registered runs can use current reviewed research context without rewriting the historical report artifact.

If Theme Research is unavailable, Daily Review remains available with a partial Theme Research section and one concise warning.

## Watchlist

Each watchlist item includes `theme_research_context`. Batch enrichment loads the Theme Research package once and preserves row order and every existing signal field. The frontend shows one compact theme/node summary or an explicit evidence-gap, not-mapped, or unavailable state.

## Stock Workspace

Asset profiles include `theme_research_context`. Stock Workspace renders:

- theme and independent dashboard link;
- mapped industry-chain node;
- value-capture, bottleneck, and evidence-strength scores;
- product or service relationship;
- mapping evidence and reviewed-claim counts;
- conservative driver assessment.

The component states that the context does not participate in scoring, signals, or admission.

## Phase 2B Boundary

The humanoid-robotics baseline remains a structural sample and explicit evidence gap. Its public source pack, claim review, and node evidence matrix are not complete, so it cannot produce reviewed workflow company context. Phase 8 ingestion and human review must be used when that evidence work resumes.

## Verification

Run the authoritative P1-P10 verifier:

```bash
scripts/verify_theme_research_p1_p10.sh
```

The verifier checks loaders, review gates, AI power source pack, templates, company mappings, tech-bottleneck crosswalk, priority queues, dashboard guardrails, human-gated ingestion, PostgreSQL schema and parity, runtime privileges, rollback evidence, and all three Phase 10 consumers.

Phase 2B is reported as `declared_evidence_gap`; therefore the accepted overall result is:

```text
complete_with_declared_evidence_gap
```

