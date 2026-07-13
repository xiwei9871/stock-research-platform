# Theme Research And Industry Catalog Dashboard Design

Date: 2026-07-13
Status: approved

## Goal

Upgrade the existing Dashboard `主题研究` entry into one combined read-only workspace named `主题研究与产业目录`. The feature remains inside the canonical AppShell served by the existing Vite application on `http://127.0.0.1:5174`; it does not create another frontend, service, or port.

## Navigation And Routes

The existing navigation item is renamed from `主题研究` to `主题研究与产业目录`. The base route remains `/theme-research` for backward compatibility.

The workspace uses two top-level views:

- `/theme-research`: theme research index and existing theme-detail routes;
- `/theme-research/catalog`: technology-industry catalog index;
- `/theme-research/catalog/:chain_id`: one industry-chain detail view.

Existing theme routes remain unchanged:

- `/theme-research/:theme_id`;
- `/theme-research/:theme_id/nodes`;
- `/theme-research/:theme_id/sources`;
- `/theme-research/:theme_id/companies`.

The workspace displays a compact segmented control for `主题研究` and `产业目录`. Browser back and forward restore the selected view and detail route.

## Industry Catalog View

The catalog index is a dense research workspace rather than a landing page. It contains:

- summary metrics for sectors, chains, detailed chains, skeleton chains, and structural completeness;
- search across sector name, chain name, aliases, and descriptions;
- sector filtering;
- an L1 sector to L2 industry-chain hierarchy;
- visible chain kind, decomposition method, review status, and expansion status.

Selecting a chain opens its detail route. The detail view shows:

- chain scope, exclusions, aliases, status, and decomposition method;
- L3 and L4 nodes in parent-child order;
- typed dependency edges when present;
- linked theme research records and mapped/unmapped theme nodes;
- an explicit empty state for skeleton chains that do not yet have L3/L4 detail.

The UI remains read-only. It does not expose editing, review writes, scoring changes, company admission, or signal actions.

## Backend Read Model

The existing FastAPI Dashboard service adds a read-only API family backed by `stock_research.technology_industry_catalog`:

- `GET /api/research/technology-industry-catalog` returns catalog summary, sectors, and chains;
- `GET /api/research/technology-industry-catalog/chains/{chain_id}` returns one chain, nodes, edges, compositions, and theme links.

The API loads the existing validated repository artifact. It does not write the database or artifact files and does not access external networks. Invalid or unknown chain identifiers return `404` with `chain_not_found`.

## Frontend Components

`ThemeResearchWorkspace` remains responsible for existing theme routes. A small parent workspace owns the top-level view switch and delegates to:

- the existing theme research component;
- a new industry catalog component.

This keeps the mature theme-research implementation intact and prevents the new catalog concerns from expanding the existing component further. Shared route constants and API types remain explicit.

## States And Responsive Behavior

Both catalog index and detail support loading, retryable error, empty-filter, and unknown-chain states. Wide tables or node lists scroll within their own region and must not create page-level horizontal overflow. Mobile presentation stacks summary controls and preserves readable chain/node rows.

## Verification

Backend tests cover the catalog list response, chain detail response, unknown chain handling, and read-only method surface. Frontend tests cover navigation rename, view switching, routing, search/filter behavior, detail rendering, empty skeleton state, and retry behavior.

The completed integration must pass targeted pytest, Dashboard Vitest, production build, and Playwright checks against the real application on port `5174` at desktop and mobile viewports.

## Boundaries

This change does not add another frontend, introduce a graph visualization, modify catalog artifacts, expand company mappings, change existing theme-research evidence policy, or merge the separate `卡脖子复盘` workspace into this page.
