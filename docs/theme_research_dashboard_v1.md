# Theme Research And Industry Catalog Dashboard v1

> The combined workspace is part of the canonical Dashboard AppShell served by the existing Vite application at `http://127.0.0.1:5174`. It does not introduce another frontend, AppShell, or port.

Updated: 2026-07-13
Theme Research phase: 7 - complete

## Purpose

The Dashboard exposes validated Theme Research artifacts and the Technology Industry Catalog as one read-only operational workspace. Theme Research remains the evidence, claim-review, and company-mapping view. The catalog provides a technology-first L1-L4 structural taxonomy that Theme Research can link to without redefining its evidence policy.

The combined workspace is not a recommendation, signal, admission, valuation, or review-decision surface. The separate `卡脖子复盘` workspace remains stock-centered and is not merged into this navigation entry.

## Navigation And Routes

The primary Dashboard navigation contains these independent entries:

```text
主题研究与产业目录
卡脖子复盘
```

`主题研究与产业目录` opens one route-backed workspace inside the canonical `AppShell`. Its top navigation switches between `主题研究` and `产业目录` while browser back and forward preserve the selected view.

Theme Research routes remain:

```text
/theme-research
/theme-research/:theme_id
/theme-research/:theme_id/nodes
/theme-research/:theme_id/sources
/theme-research/:theme_id/companies
```

Technology Industry Catalog routes are:

```text
/theme-research/catalog
/theme-research/catalog/:chain_id
```

The theme index compares themes. Theme detail keeps one theme context while route-backed tabs switch among overview, nodes, source/claim evidence, and company mappings. The catalog index groups L2 chains by L1 sector; chain detail shows available L3/L4 structure, edges, and theme links. Direct URLs and browser history restore the same view.

## Read-only APIs

```text
GET /api/research/theme-decomposition/themes
GET /api/research/theme-decomposition/themes/{theme_id}
GET /api/research/theme-decomposition/themes/{theme_id}/nodes
GET /api/research/theme-decomposition/themes/{theme_id}/sources
GET /api/research/theme-decomposition/themes/{theme_id}/claims
GET /api/research/theme-decomposition/themes/{theme_id}/companies
```

These APIs load existing validated P1-P6 packages through `stock_research.dashboard.theme_research`. Production can use the PostgreSQL provider through `THEME_RESEARCH_READ_SOURCE=db`; API contracts and research-only guardrails remain unchanged. The read model does not independently reinterpret score policy, access external networks, or write files and databases.

Unknown themes return:

```json
{"detail": "theme_not_found"}
```

POST, PATCH, PUT, and DELETE are not registered for this API family.

### Technology Industry Catalog APIs

```text
GET /api/research/technology-industry-catalog
GET /api/research/technology-industry-catalog/chains/{chain_id}
```

The first endpoint returns catalog summary, sectors, and L2 chains. The second returns one chain with its available nodes, typed edges, compositions, and theme links. Both load the validated repository artifact through `stock_research.technology_industry_catalog`; they do not write artifacts or databases and do not access external networks.

Unknown chains return:

```json
{"detail": "chain_not_found"}
```

POST, PATCH, PUT, and DELETE are not registered for either catalog endpoint.

## Views

### Theme Index

The index shows theme status, node/source/claim/company counts, evidence gaps, deep-research nodes, and last update. Search is local and read-only.

### Overview

The overview shows compact theme metrics, the highest-priority nodes, and claim evidence-state distribution.

### Industry-chain Nodes

The node table includes value capture, bottleneck, localization gap, supply tightness, evidence strength, research priority, node review state, and recommended research action. Known v1 node identifiers receive Chinese display labels without changing artifact values.

### Sources And Claims

Sources and extracted claims are displayed in separate tables so source reliability is not confused with claim verification. S4 short-video material remains visibly marked as `仅作线索`; it is never presented as formal evidence.

### Company Mappings

Company rows join Phase 4 mapping evidence, Phase 6 priority, Phase 5 integration status, and existing tech-bottleneck review context. Coverage gaps remain visible and are not admitted automatically.

The company action opens:

```text
/tech-bottleneck/stock/{stock_code}?source=theme_research
```

The existing Stock Workspace owns the resulting stock view.

### Industry Catalog

The catalog index shows stable summary metrics, local search, sector filtering, and an L1 sector to L2 chain hierarchy. Each chain row exposes its chain kind, decomposition method, lifecycle status, and whether L3/L4 nodes are structurally expanded.

The chain detail view shows scope, exclusions, aliases, decomposition method, available L3/L4 nodes, typed node relationships, and linked Theme Research records. Skeleton chains without L3/L4 nodes remain visible with an explicit empty state; they are not presented as completed research.

## Guardrails

Every read model preserves:

```text
research_only = true
used_for_signal = false
used_for_admission = false
```

Phase 7 adds no:

- review-decision writes;
- DB or artifact writes;
- automatic company admission;
- price, valuation, return, momentum, timing, or recommendation inputs;
- graph visualization;
- ingestion or claim extraction.

The catalog integration also adds no:

- catalog, evidence, review, or company-mapping writes;
- automatic expansion of skeleton chains;
- inference that lifecycle status proves structural, evidence, or company coverage;
- duplicate ownership of canonical L4 research objects;
- replacement of Theme Research or `卡脖子复盘` as their respective systems of record.

## Current Data And Coverage

The current artifact set exposes:

```text
2 themes
34 nodes
20 baseline source rows, of which 17 are linked to a theme claim or assessment view
12 claims
4 company mappings
15 evidence-collection priorities
21 pending human-review queue items
```

The AI-power theme has four company mappings. The humanoid-robotics theme remains a draft structural baseline and still requires the full Phase 2B evidence pack; the Dashboard displays that incompleteness rather than treating it as reviewed.

The current Technology Industry Catalog snapshot exposes:

```text
10 L1 sectors
82 L2 chains
13 structurally detailed chains with both L3 and L4 nodes
69 unexpanded skeleton chains
15.85% structural completeness
```

This is structural coverage, not a complete industry-research catalog. The 82-chain L2 registry provides broad navigation coverage, while most branches still lack detailed L3/L4 expansion. Structural completeness does not measure source evidence, claim review, company mapping, investment relevance, or review readiness.

## Separate 卡脖子复盘 Workspace

`卡脖子复盘` remains a separate primary navigation entry and stock-centered review universe. The combined Theme Research and Industry Catalog workspace may link to an existing stock view where an explicit mapping exists, but it does not admit companies, alter review status, or redefine the `卡脖子复盘` coverage boundary.

## Verification

Backend:

```bash
rtk .venv/bin/pytest tests/test_dashboard_technology_industry_catalog.py \
  tests/test_dashboard_theme_research.py \
  tests/test_technology_industry_catalog.py \
  tests/test_technology_industry_catalog_pilots.py \
  tests/test_technology_industry_catalog_skeleton.py -q
```

Frontend:

```bash
rtk pnpm --dir dashboard test
rtk pnpm --dir dashboard build
```

Browser acceptance:

```bash
rtk pnpm --dir dashboard exec playwright test \
  tests/theme-research-full-flow.spec.ts --project=chromium
```

The existing Theme Research Playwright flow covers desktop and mobile layouts, route-backed tabs, evidence and coverage-gap states, horizontal page-overflow checks, company stock handoff, and browser-back restoration. Catalog-specific real-app acceptance is tracked separately from this styling and documentation task.

## Next Phase

Theme Research ingestion remains a separate human-review staging workflow. It must not write AI output directly into reviewed artifacts or production tables. Catalog expansion should continue branch by branch, preserving canonical ownership and reporting structural coverage without claiming the catalog is complete.
