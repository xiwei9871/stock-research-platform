# Theme Research Dashboard v1 Design

Date: 2026-07-11
Phase: 7 - Read-only Dashboard

## Purpose

Expose the reviewed state produced by Theme-driven Research Engine Phases 1-6 inside the existing Stock Research Platform dashboard. The dashboard is a research inspection surface, not a signal, admission, recommendation, or review-decision write surface.

The page answers four operational questions:

1. Which themes and industry-chain nodes currently exist?
2. Which nodes have strong value-capture or bottleneck characteristics?
3. Which claims and sources support those assessments, and where are the evidence gaps?
4. Which companies map to each node, and how do those mappings relate to the existing tech-bottleneck review universe?

## Product Structure

Phase 7 adds a separate primary navigation item named `主题研究`. It remains distinct from `卡脖子复盘` because the two workspaces use different units of analysis:

- Theme Research: theme -> node -> claim/source -> company mapping.
- Tech Bottleneck Review: stock -> evidence -> reviewer state and decision history.

The two workspaces are connected by explicit links. Theme-company rows may open the existing stock workspace and tech-bottleneck context. Phase 7 does not duplicate or modify tech-bottleneck review state.

## Routes

The frontend uses a hybrid structure: a theme index plus a persistent theme-detail workspace with route-backed tabs.

```text
/theme-research
/theme-research/:theme_id
/theme-research/:theme_id/nodes
/theme-research/:theme_id/sources
/theme-research/:theme_id/companies
```

Route behavior:

- `/theme-research` displays the cross-theme index.
- `/theme-research/:theme_id` displays the theme overview.
- Child routes select a detail tab without discarding the selected theme.
- Browser back/forward and direct URL entry restore the correct workspace and tab.
- Unknown themes display a readable not-found state without leaving the dashboard shell.

## Backend Architecture

Create a focused read-model module at `src/stock_research/dashboard/theme_research.py`. It loads the validated P1-P6 packages through their existing loaders and joins them in memory. It does not parse artifact JSON independently and does not write files or a database.

The module exposes these public read functions:

```text
list_theme_research_themes()
get_theme_research_theme(theme_id)
list_theme_research_nodes(theme_id)
list_theme_research_sources(theme_id)
list_theme_research_claims(theme_id)
list_theme_research_companies(theme_id)
```

All rows retain the P1-P6 `research_only`, `used_for_signal`, and `used_for_admission` invariants. Company rows include a deterministic tech-bottleneck stock path, but the crosswalk status never changes merit scores.

## API Contract

Add GET-only routes:

```text
GET /api/research/theme-decomposition/themes
GET /api/research/theme-decomposition/themes/{theme_id}
GET /api/research/theme-decomposition/themes/{theme_id}/nodes
GET /api/research/theme-decomposition/themes/{theme_id}/sources
GET /api/research/theme-decomposition/themes/{theme_id}/claims
GET /api/research/theme-decomposition/themes/{theme_id}/companies
```

Collection responses use:

```json
{
  "total": 2,
  "items": []
}
```

The theme index includes:

```text
theme_id
theme_name
theme_type
summary
status
last_updated
node_count
source_count
claim_count
company_count
evidence_gap_count
deep_research_node_count
review_queue_count
research_only
used_for_signal
used_for_admission
```

Theme detail includes the theme row, aggregate status distributions, top node priorities, evidence gaps, company priority summary, source reliability distribution, claim evidence-status distribution, and queue action distribution.

Node rows join the original theme node with its Phase 6 priority fields. Source rows include source review state and the claims they support. Claim rows preserve claim evidence and platform-use states. Company rows join Phase 4 mapping, Phase 6 priority, P5 integration state, and the existing-review context.

Unknown `theme_id` values return HTTP 404 with `theme_not_found`.

## Frontend Architecture

Add a feature-local API module, types, and one workspace component:

```text
dashboard/src/api/themeResearch.ts
dashboard/src/types/themeResearch.ts
dashboard/src/components/ThemeResearchWorkspace.tsx
```

`AppShell` owns top-level route recognition and navigation, matching the current dashboard architecture. `ThemeResearchWorkspace` owns theme selection and detail-tab navigation beneath `/theme-research`.

The implementation uses the existing React, CSS, and lucide icon stack. It does not add React Router or another state-management dependency.

## Information Design

### Theme Index

The index is table-first. A restrained header identifies the workspace, followed by a compact status strip and a searchable table. Each row shows theme name/type, review status, node/source/claim/company counts, evidence gaps, deep-research nodes, and last update. Selecting a row opens its overview.

### Theme Overview

The overview keeps the theme name and status visible, then shows compact metrics and three unframed table sections:

- highest-priority nodes;
- evidence gaps requiring collection;
- mapped companies requiring research or crosswalk review.

No graph view is included in v1.

### Nodes Tab

A dense table supports status and priority-class filtering. Columns show node hierarchy, node type, value capture, bottleneck, localization gap, supply tightness, evidence strength, priority score, review status, and recommended action.

### Sources Tab

The sources tab combines source and claim inspection in one route-backed view. It has separate source and claim tables so users can distinguish provenance quality from extracted assertions. Reliability, source review status, access level, evidence status, and platform-use status remain visible.

### Companies Tab

The company table shows mapped node, mapping type, relevance, materiality, company priority, evidence strength, P5 integration status, and existing tech-bottleneck review context. A stock-link action opens:

```text
/tech-bottleneck/stock/{stock_code}?source=theme_research
```

Coverage-gap companies remain visible and are never silently admitted to the existing universe.

## Interaction And State

- Search and filters are local read-only controls.
- Route changes use `history.pushState`; `popstate` restores the active tab.
- Loading, empty, error, and not-found states are explicit.
- Data refreshes only through GET requests.
- No editable field, review-decision button, or write token is exposed.

## Visual Rules

- Match the existing quiet operational dashboard.
- Use full-width bands and dense tables, not marketing cards.
- Use compact status badges only for categorical states.
- Keep all fixed score columns stable and tabular-numeric.
- Provide horizontal table scrolling on narrow viewports.
- Preserve readable labels and avoid unexplained internal IDs as primary text.
- Use lucide icons for navigation and link actions where an icon is appropriate.

## Error Handling

- Backend validation failures surface as HTTP 500 only when validated local artifacts are internally inconsistent; responses must not expose tracebacks.
- Unknown themes return 404.
- Frontend fetch failures show an in-workspace error state and a retry action.
- A failed child collection does not display stale data from another theme.

## Testing

Backend tests cover:

- two themes are listed with stable aggregate counts;
- theme detail joins P1-P6 state correctly;
- node/source/claim/company endpoints return only the requested theme;
- company rows preserve integration context and stock links;
- unknown theme returns 404;
- all routes are GET-only and preserve research guardrails.

Frontend tests cover:

- navigation opens `/theme-research`;
- direct URLs restore overview and each tab;
- theme selection updates the URL;
- tables display review, evidence-gap, and company-integration states;
- company action opens the existing tech-bottleneck stock route;
- loading, error, empty, and not-found states are readable.

Playwright acceptance covers desktop and mobile viewports, route restoration, tab navigation, table alignment, no overlapping text, and the cross-workspace stock handoff.

## Boundaries

Phase 7 does not add:

- graph visualization;
- artifact ingestion or claim extraction;
- review decision writes;
- database tables or migrations;
- automatic company admission;
- price, valuation, signal, recommendation, or timing inputs;
- Daily Review or Watchlist integration beyond existing stock-route handoff.

Those capabilities belong to Phases 8-10.

## Acceptance Criteria

1. All six GET APIs load from validated P1-P6 artifacts without network or DB writes.
2. The Dashboard exposes an independent `主题研究` navigation entry.
3. The theme index and four route-backed detail views work with browser history and direct URLs.
4. Reviewed, draft, research-lead, blocked, evidence-gap, and coverage-gap states remain distinguishable.
5. Company mappings link to the existing tech-bottleneck stock workflow without copying its review state.
6. Backend, frontend, build, and Playwright tests pass at desktop and mobile sizes.
7. Existing tech-bottleneck and stock-workspace routes continue to work.
