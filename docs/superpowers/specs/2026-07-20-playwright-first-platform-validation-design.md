# Playwright-First Platform Validation Design

**Date:** 2026-07-20

**Status:** Approved design; pending implementation plan

## Context

The platform already has broad pytest, Vitest, API-contract, and database-contract coverage, plus a small Playwright smoke suite. Those tests are valuable but do not yet provide a systematic guarantee that the final browser experience uses the correct route context, trade date, strategy publication, and displayed value.

The recent LHB regression illustrates the missing layer: the officially expected return was in the tens of percent, while the page again displayed approximately 175%. A database or API check alone cannot prove that the browser selected the correct field, unit, date, cache entry, or publication version.

The platform therefore needs one validation system with three operating modes:

1. a one-time full-platform audit that establishes a trusted baseline;
2. change-triggered validation for pull requests and affected areas;
3. a small critical browser-acceptance stage inside daily Auto EOD Repair.

The direction is **Playwright-first, not Playwright-only**. Every critical user journey must be covered by Playwright, while lower-level tests remain authoritative for calculations, database constraints, hashes, identity rules, and other invariants that a browser cannot prove reliably.

## Goals

- Inventory and validate every significant platform workspace, route, deep link, and user flow.
- Catch browser-visible calculation, unit, date, routing, context, and publication regressions before they are accepted as official.
- Use the same core consistency assertions in initial audit, pull-request validation, and daily EOD acceptance.
- Make failures reproducible and traceable to a trade date, data version, API response, and publication identity.
- Integrate browser acceptance into Auto EOD Repair without allowing browser automation to mutate or approve business results.
- Preserve the last successful official publication whenever a new publication fails a critical consistency check.

## Non-Goals

- Replace pytest, Vitest, API-contract, or database-contract tests with Playwright.
- Run the full browser matrix or every platform workspace after every daily EOD run.
- Allow Playwright to calculate, rewrite, or approve strategy returns, NAV values, signals, hashes, publication IDs, or trade dates.
- Turn minor visual changes into daily EOD blockers.
- Add unrestricted write tests against the real application database.
- Make this design a general-purpose synthetic production monitoring system. Daily execution is specifically part of Auto EOD Repair and its publication contract.

## Recommended Architecture

The validation system has six layers. A failure should be detected at the lowest layer that can prove the relevant contract, while critical end-user journeys also receive browser coverage.

| Layer | Responsibility | Typical execution |
|---|---|---|
| L0: static | Type checks, frontend build, import and configuration validity | Pull requests |
| L1: unit | Parsers, normalizers, date logic, calculation helpers, route-state helpers | Pull requests |
| L2: component and contract | React components, API schemas, database constraints, strategy identity and publication contracts | Pull requests and focused EOD checks |
| L3: Playwright Mock | Deterministic browser journeys with intercepted or fixture-backed APIs | Main pull-request browser gate |
| L4: Playwright Real | Read-only validation against real APIs, database-derived artifacts, and official publications | Initial audit, affected changes, daily critical acceptance |
| L5: Playwright Sandbox | Write flows against an isolated test database with deterministic cleanup | Initial audit and write-feature changes |

### Why this split

Playwright is authoritative for what a user can access, navigate to, and see. It is not authoritative for whether an internal calculation algorithm is mathematically correct. Conversely, database and API tests may prove that an official result is correct but cannot prove that the browser shows that official result. The layers deliberately overlap at critical publication surfaces so that both sides of the contract are checked.

## Execution Profiles

### Mock profile

The Mock profile is deterministic and suitable for pull requests:

- run the application with authentication disabled unless the test explicitly covers authentication;
- intercept APIs or use stable fixtures;
- use fixed trade dates, publication IDs, stock codes, and return values;
- test success, empty, loading, degraded, and failure states;
- exercise browser navigation without relying on external data freshness;
- simulate write requests without mutating the real database.

### Real read-only profile

The Real profile validates deployed local services and official artifacts:

- use real backend APIs and current database-derived results;
- perform no business-data writes;
- derive expected values from authoritative APIs or publication manifests before asserting page values;
- record the trade date, dataset version, and publication identity used by the test;
- fail clearly when required official data is absent rather than silently substituting fixture data.

### Sandbox write profile

The Sandbox profile validates mutating workflows:

- run against an isolated test database and isolated output directories;
- seed minimal deterministic records;
- validate create, update, review, publish-preview, rollback, and cleanup behavior as applicable;
- prove that reruns are idempotent or that cleanup restores the original state;
- never share credentials, database schemas, or artifact directories with the real profile.

## Browser and Viewport Matrix

### Pull-request gate

- Chromium desktop.
- One representative mobile viewport.

### Full-platform audit

- Chromium desktop and mobile.
- Firefox desktop.
- Selective WebKit coverage for authentication, home, global search, stock workspace, theme-research handoff, and strategy publication journeys.

### Daily Auto EOD Repair

- Chromium desktop only.
- No full cross-browser or full responsive sweep.

This matrix keeps the frequent gate fast while preserving broader compatibility evidence in the initial baseline and affected-area acceptance runs.

## Platform Coverage Inventory

The initial audit must inventory both visible navigation and deep or operational routes. The inventory is a maintained test input rather than an informal checklist.

Primary functional groups include:

- authentication, session behavior, permissions, and user administration;
- home, review queue, daily review, watchlist, decisions, and outcomes;
- market monitor, news, research reports, and generated reports;
- global search and the stock workspace, including charts, quote/profile data, evidence, themes, reports, and decision context;
- theme research, industry catalog, deep research, technology bottleneck review, and Docling report audit;
- factor laboratory, strategy laboratory, backtests, strategy validation, official publication, and publication artifacts;
- research cases, queue health, evidence snapshots, gap review, publish gates, publication preview, and external delivery;
- Data Explorer and other valid routes that are not exposed directly in the main navigation.

For every route or workspace, the inventory records:

- route pattern and required parameters;
- authentication and role requirement;
- primary APIs and expected loading dependencies;
- available empty, degraded, and error states;
- whether the route is P0, P1, or P2;
- responsible test layers and browser profiles;
- whether the route participates in daily EOD acceptance.

## Critical Playwright Journeys

Every P0 journey requires a Playwright test. Lower-level coverage alone is insufficient.

1. **Authentication and shell**: log in, reach the home page, log out, and verify unauthenticated redirects and basic permission boundaries.
2. **Global search handoff**: search for a stock, enter the stock workspace, return, and restore the search query and result context.
3. **Theme research handoff**: open a theme, select a company, enter its stock workspace, and return with the theme/company/source context intact.
4. **Technology bottleneck handoff**: enter a company from the review universe, open the stock workspace, and preserve source, current stock code, and compatibility metadata.
5. **Review queue consistency**: verify that list counts, selected record, detail data, status, and return navigation remain consistent.
6. **Strategy publication journey**: move from strategy cards to strategy details and verify trade date, status, publication ID, version, return/NAV values, and artifact links.
7. **Direct navigation and history**: open deep URLs directly, refresh them, and use browser back/forward without losing required route state.
8. **Failure isolation**: prove that one failed strategy or noncritical API does not corrupt unrelated strategies or make the entire application unusable.
9. **Mobile critical flow**: verify that core pages have no severe horizontal overflow, inaccessible controls, or blocked navigation.
10. **Cross-surface official identity**: prove that home, strategy details, review queue, and authoritative API all refer to the same official strategy publication.

## Standard Page Checks

The reusable page-test contract includes:

- direct access and initial rendering;
- stable loading completion;
- empty and degraded states;
- retryable and terminal error states;
- primary and secondary navigation;
- list filtering, sorting, pagination, and selection where present;
- form validation and safe submission behavior;
- refresh, back, forward, and state restoration;
- severe console errors and failed critical network requests;
- desktop and mobile interaction availability;
- limited accessibility checks for labels, roles, focus, and keyboard access;
- selected visual-region comparisons with dynamic content masked.

Visual regression is intentionally limited to stable, high-value regions. Dynamic dates, live numbers, chart cursors, timestamps, and other unstable content are masked. Baseline changes require manual review and never update automatically in daily EOD repair.

## Shared Consistency Model

The same model applies across Mock, Real, and Sandbox profiles.

### URL-to-page consistency

The page title, selected entity, stock code, strategy ID, theme ID, and source context must match the URL. Invalid or incomplete parameters must produce a defined error or fallback rather than silently rendering an unrelated record.

### Navigation consistency

Before and after a handoff, the target entity and source context must remain stable. Returning to the source page must restore meaningful state such as query, filter, selected record, pagination, and scroll position where the product promises it.

### Browser-history consistency

Direct navigation, refresh, back, and forward must not change the logical entity or silently drop required route context.

### List-to-detail consistency

Identifiers, status, trade date, headline metrics, and version shown in a list must match the corresponding detail page and authoritative API.

### API-to-UI consistency

Displayed values must match the documented API field after the documented formatting rule. Tests must compare typed values, not only formatted strings. Percentage conversion is explicit: the test records whether the source is a ratio or percentage and verifies the single allowed conversion.

### Page-to-page consistency

When multiple pages present the same official object, they must use the same object identity and version. A newer unofficial preview must not leak into one official surface while another retains the official publication.

### Stock-code compatibility

The platform may preserve an existing route code when a security code changes, but the compatibility mapping must be explicit. The test verifies that both current and supported legacy codes resolve to the intended company and that navigation does not break.

### Date consistency

Trade date, data date, calculation date, publication time, and displayed date must obey the documented ordering. A later pipeline run must not make an older publication appear current.

### Publication consistency

Publication ID, strategy ID, version, trade date, artifact path, content hash, and official status must agree across database/API contracts and browser surfaces. An official publication may advance but must not roll back silently.

### Write consistency

Sandbox tests verify persistence, idempotence, rollback, and cleanup. A failed write must not leave a partially official object.

## Reusable Browser Assertions

The implementation plan should introduce small, domain-focused assertion helpers rather than a large generic framework:

- `expectRouteContext`: validates route parameters, selected entity, source context, and compatibility mapping.
- `expectStateRestored`: validates query, filter, selection, pagination, and other promised return state.
- `expectApiUiConsistency`: validates authoritative typed API values against rendered values and formatting rules.
- `expectPublicationConsistency`: validates strategy/publication identity, version, date, status, artifact references, and no-rollback behavior.

Each helper returns or logs structured comparison data so a failure report contains expected and actual values without requiring manual trace inspection.

## Initial Full-Platform Audit

The first audit uses a census-first process. It must not continuously redefine the baseline while fixes are being made.

### Phase A: inventory and evidence capture

1. Freeze the application revision and audit configuration.
2. Build the route/function/API coverage inventory.
3. Run static, unit, component, and contract suites.
4. Run Mock, Real read-only, and Sandbox browser profiles.
5. Run the full browser/viewport matrix and limited visual checks.
6. Record every observed issue without beginning broad remediation.
7. Freeze the initial P0/P1/P2 issue ledger and baseline report.

### Phase B: repair and regression

1. Repair P0 issues first, then P1, then approved P2 issues.
2. Add the smallest lower-level regression test capable of proving each root invariant.
3. Add or update Playwright coverage when the issue is browser-visible or journey-related.
4. Re-run the affected layer after each repair.
5. Run the complete baseline suite after all blocking repairs.
6. Publish the trusted baseline only when acceptance criteria pass.

The frozen initial ledger preserves evidence of what the audit found; the final baseline records what is now trusted.

## Pull-Request Validation

Every pull request runs:

- relevant L0-L2 tests;
- all P0 Mock Playwright journeys on Chromium desktop;
- the critical mobile Mock subset;
- affected Real read-only tests when the change touches routing, API mapping, date semantics, official publication, or data formatting;
- affected visual checks when stable UI regions change;
- Sandbox tests when a mutating workflow changes.

The implementation may use path- or tag-based selection for affected tests, but all P0 Mock journeys remain mandatory. A selector must default to broader coverage when it cannot confidently classify a change.

## Daily Auto EOD Repair Integration

Daily Playwright is a final user-perspective acceptance stage inside Auto EOD Repair, not a separate full nightly test program.

The daily sequence is:

```text
data readiness
  -> EOD calculation
  -> strategy publication candidate
  -> database and API contracts
  -> Playwright critical-page acceptance
  -> whitelisted repair actions when applicable
  -> repeat the same contract and Playwright checks
  -> finalize or block the official EOD result
```

### Daily browser scope

The target duration is five to ten minutes. The Chromium-only suite verifies:

- home and principal workspaces load without a white screen;
- the latest market and strategy dates are correct;
- every official strategy card and detail page uses the accepted trade date and publication version;
- displayed return and NAV values match authoritative official APIs or manifests;
- review queue entries refer to the same official strategy versions;
- publication IDs and versions do not roll back from the previous successful official run;
- a single strategy failure remains isolated;
- representative current-day stock, theme-research, and technology-bottleneck deep links resolve correctly;
- no critical request fails and no fatal console error prevents use of a critical page;
- known high-risk metrics such as LHB returns are checked both exactly against the authoritative source and for explicit unit/format semantics.

The daily suite does not run the full browser matrix, every workspace, Sandbox writes, or the complete visual baseline.

### Candidate versus official publication

Where publication currently becomes official before browser acceptance, implementation must introduce or use an equivalent candidate/finalization boundary. Browser checks must validate a stable candidate. Only a successful critical acceptance finalizes that candidate as the new official publication. If the existing system cannot stage a candidate atomically, the implementation plan must preserve the previous official pointer until validation succeeds.

## Failure Classification

### Blocking failures

The EOD run cannot be finalized when any of the following occurs:

- trade date, return, NAV, signal summary, strategy version, or publication identity differs across authoritative data and critical UI surfaces;
- an official publication ID or version rolls back;
- a critical page cannot load or renders the wrong entity;
- an official strategy is missing;
- the review queue points at a different official version;
- a database constraint, identity hash, publication contract, or critical API contract fails;
- the browser can only pass by falling back to stale or fixture data.

### Warning failures

The EOD result may remain publishable, with an explicit warning, for:

- reviewed minor visual differences;
- a failure limited to a noncritical workspace;
- nonfatal console warnings;
- compatibility failures outside the daily Chromium scope that do not affect the official browser contract;
- slower noncritical pages that still complete within the configured test timeout and do not break a P0 journey.

Warnings are evidence, not silent passes. Repeated warnings may be promoted through a later governance change, but the daily job does not change severity dynamically.

## Automatic Repair Safety Boundary

Auto EOD Repair uses an explicit action whitelist.

Allowed automatic actions include:

- service health recovery and bounded retry;
- removal of safely rebuildable caches;
- rebuilding indexes or derived views;
- rerunning idempotent data synchronization, calculation, and publication-candidate stages;
- rerunning the exact same contract and Playwright checks after repair.

Forbidden automatic actions include:

- changing returns, NAV values, signals, or other business results;
- rewriting publication IDs, trade dates, versions, identity hashes, or official status to satisfy a test;
- bypassing database constraints or publication contracts;
- overwriting the last successful official result with an unvalidated candidate;
- updating visual baselines automatically;
- weakening an assertion or changing severity during the repair run.

If a forbidden-class inconsistency is detected, the run stops before official finalization, preserves the previous successful official publication, writes complete evidence, and reports the required operator action.

## Evidence and Reporting Contract

Every Playwright failure record contains:

- stable test ID and journey name;
- execution profile, browser, viewport, application revision, and configuration identity;
- URL, route parameters, source context, and selected entity;
- trade date, dataset version, strategy ID, publication ID, and strategy version when applicable;
- expected typed value, actual typed or rendered value, and formatting/conversion rule;
- severity and whether the failure blocks official finalization;
- screenshot, Playwright trace, critical request evidence, and relevant console errors;
- attempted automatic repair action, if any;
- revalidation result and terminal disposition.

The full audit produces:

- route and function inventory;
- coverage matrix by feature and test layer;
- frozen P0/P1/P2 issue ledger;
- initial audit report;
- final trusted-baseline report;
- links or paths to detailed evidence.

Every Auto EOD Repair run produces both machine-readable JSON and a human-readable HTML report. The report links this chain:

```text
EOD run ID
  -> trade date and dataset version
  -> calculation results
  -> publication candidate
  -> database/API contract results
  -> Playwright acceptance results
  -> repair actions
  -> repeated validation
  -> final official or blocked status
```

The trusted initial baseline is retained long term. Daily reports and failure evidence are retained for at least 90 days. Retention cleanup must not remove artifacts referenced by an unresolved incident.

## Test Organization Principles

- Organize Playwright tests by user journey or platform domain, not by React component.
- Tag tests by priority and profile, for example P0/P1/P2 and mock/real/sandbox/eod/visual.
- Keep fixtures deterministic and versioned.
- Use semantic locators and stable test IDs only where accessible roles or labels are insufficient.
- Avoid fixed sleeps; wait on observable application or network state.
- Treat unexpected critical requests and severe console errors as first-class failures.
- Keep shared helpers small and domain-specific.
- Do not hide flaky tests with unlimited retries. A retry may capture trace evidence, but repeated instability remains a test defect.

## Rollout Strategy

Implementation should proceed in bounded phases:

1. **Foundation:** profiles, projects, tags, evidence directories, common fixtures, and shared consistency assertions.
2. **P0 Mock gate:** implement deterministic critical journeys and make them the main pull-request browser gate.
3. **Real read-only acceptance:** add authoritative API/UI and publication consistency checks.
4. **Initial full audit:** complete route inventory, broad browser run, issue freeze, remediation, and trusted baseline.
5. **Sandbox writes:** cover isolated mutating workflows with cleanup and idempotence proofs.
6. **Auto EOD Repair integration:** add candidate/finalization handling, critical daily Playwright suite, severity mapping, repair/recheck loop, and reports.
7. **Operational hardening:** measure duration and flakiness, tighten evidence retention, and document operator response.

The implementation plan may split these phases into separate commits or pull requests, but all phases use the same core assertions and evidence model.

## Acceptance Criteria

- Every major route and workspace appears in the maintained inventory with an assigned test layer and priority.
- Every P0 user journey has stable Playwright coverage.
- Pull requests run deterministic Chromium desktop and critical mobile browser gates.
- Real read-only tests prove API-to-UI and publication consistency without writing business data.
- Sandbox tests prove relevant write, rollback, cleanup, and idempotence behavior in isolation.
- The initial audit freezes an issue ledger before broad repairs and finishes with a trusted baseline.
- A browser-visible return/unit regression such as the LHB 175% incident is detected before a new official EOD result is finalized.
- Every displayed official strategy result can be traced to its trade date, dataset version, publication ID, and artifact identity.
- Daily Auto EOD Repair runs the critical Chromium suite in the target five-to-ten-minute window.
- Blocking failures preserve the previous successful official publication.
- Automatic repair executes only whitelisted actions and always repeats the same checks afterward.
- Full audit, pull-request, and daily EOD modes reuse the same core consistency assertions rather than maintaining divergent definitions.
- Reports contain sufficient evidence to reproduce a failure without relying on transient browser state.

## Rollback

The validation layers can be introduced incrementally. If browser-gate integration causes operational instability, disable only the affected execution profile while retaining generated evidence and lower-level contracts. Auto EOD finalization must remain fail-safe: disabling a broken test runner must require an explicit operator decision and must never silently treat an unvalidated candidate as official.
