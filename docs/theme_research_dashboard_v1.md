# Theme Research Dashboard v1

> Phase 9 update (2026-07-11): the existing read-only routes now use the PostgreSQL provider in production through `THEME_RESEARCH_READ_SOURCE=db`. API contracts and research-only guardrails are unchanged.

Updated: 2026-07-11
Phase: 7 - complete

## Purpose

The Theme Research dashboard exposes the validated P1-P6 research artifacts as a read-only operational workspace. It keeps theme and industry-chain research separate from the stock-centered tech-bottleneck review universe while allowing explicit company handoff between them.

The dashboard is not a recommendation, signal, admission, valuation, or review-decision surface.

## Navigation And Routes

The primary Dashboard navigation contains two independent entries:

```text
主题研究
卡脖子复盘
```

Theme Research routes:

```text
/theme-research
/theme-research/:theme_id
/theme-research/:theme_id/nodes
/theme-research/:theme_id/sources
/theme-research/:theme_id/companies
```

The index compares themes. Theme detail keeps one theme context while route-backed tabs switch among overview, nodes, source/claim evidence, and company mappings. Direct URLs and browser back/forward restore the same view.

## Read-only APIs

```text
GET /api/research/theme-decomposition/themes
GET /api/research/theme-decomposition/themes/{theme_id}
GET /api/research/theme-decomposition/themes/{theme_id}/nodes
GET /api/research/theme-decomposition/themes/{theme_id}/sources
GET /api/research/theme-decomposition/themes/{theme_id}/claims
GET /api/research/theme-decomposition/themes/{theme_id}/companies
```

The APIs load existing validated P1-P6 packages through `stock_research.dashboard.theme_research`. They do not independently reinterpret score policy, access external networks, or write files and databases.

Unknown themes return:

```json
{"detail": "theme_not_found"}
```

POST, PATCH, PUT, and DELETE are not registered for this API family.

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

## Current Data

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

## Verification

Backend:

```bash
rtk .venv/bin/pytest tests/test_dashboard_theme_research.py \
  tests/test_theme_research_priority.py \
  tests/test_theme_tech_bottleneck_crosswalk.py \
  tests/test_theme_company_mapping.py \
  tests/test_theme_decomposition.py -q
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

The Playwright flow covers desktop and mobile layouts, all route-backed tabs, evidence and coverage-gap states, horizontal page-overflow checks, company stock handoff, and browser-back restoration.

## Next Phase

Phase 8 introduces automated source ingestion and extraction into a human-review staging queue. It must not write AI output directly into the reviewed artifact or future production tables.
