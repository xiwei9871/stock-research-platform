# Strategy Publication And Human UI Contract Repair Design

## Goal

Restore one authoritative strategy-publication data flow across EOD artifacts, Dashboard APIs, review queues, and Playwright acceptance. Keep technical publication identity in backend contracts and audit evidence, while presenting only decision-useful content to human operators.

## Current Evidence

The full Real Playwright profile currently has 7 failures out of 41 tests. The strategy calculation artifacts exist and the EOD report marks three strategies ready, but publication consumption is inconsistent:

- `/api/backtests/strategies` reads the current 2026-07-21 publications.
- `/api/strategies/catalog` still exposes static historical metrics and omits current publication identity.
- Review Queue rejects relative versioned artifact paths and falls back to another source, so its rows can differ from the immutable publication files.
- EOD browser acceptance is disabled, allowing Auto EOD Repair to report the strategy and review surfaces healthy without proving browser-visible consistency.
- Machine-facing publication fields are displayed directly in Home, Strategy Lab, and Review Queue.

The remaining Real failures cover Generated Reports API behavior, duplicate Market Monitor React keys, Theme Research navigation restoration, a non-exact Daily Review landmark assertion, and expected request aborts during direct refresh.

## Product Contract

### Human-Facing Strategy Content

Home, Strategy Lab, and Review Queue will show only:

- strategy name and human-readable strategy/version label;
- cumulative return, drawdown, and latest-period return;
- performance date;
- candidate or holding count and names where relevant;
- one plain-language health state: `数据正常`, `数据更新中`, or `数据异常`;
- a concise recovery-oriented message when data is not usable.

They will not display contract IDs, publish IDs, artifact versions, manifest paths, or other internal publication identifiers.

### Machine-Facing Publication Content

The APIs may continue to carry contract ID, publish ID, artifact version, manifest path, configuration fingerprint, and publication policy. These fields are required for backend validation, Playwright consistency checks, EOD acceptance, incident evidence, and audit reports. Removing them from rendered pages must not weaken validation.

## Architecture

### Authoritative Publication Read Model

`list_backtest_strategies()` remains the authoritative enriched read model for official strategies. `/api/strategies/catalog` must use the same enriched publication state for runnable official strategies instead of returning the static catalog metrics unchanged. Static catalog metadata remains the source for names, descriptions, parameters, and diagnostic strategies.

All official strategy consumers must agree on:

- strategy ID;
- performance date;
- total return;
- contract ID;
- publish ID;
- artifact version.

Any missing or conflicting identity fails closed and produces a human-readable unavailable state rather than silently falling back to stale metrics.

### Artifact Path Resolution

New publishers continue to write absolute artifact paths. Historical paths beginning with the configured output-root directory name, such as `outputs/research/...`, are resolved only against `SETTINGS.output_root.parent`. Path traversal, alternate roots, symlinks escaping the trusted root, malformed components, and unapproved layouts remain rejected.

Review Queue must read the immutable versioned `review.csv` declared by the accepted publication. It may not substitute compatibility mirrors or database rows after an official publication declaration fails validation.

### EOD Acceptance

Daily browser acceptance will verify, for all three official strategies:

- the authoritative API cohort is complete and internally consistent;
- Review Queue rows use the same publication identity;
- the human page shows the same performance date and total return;
- no stale known-bad return such as `175.29%` appears;
- runtime console and request evidence is clean.

The execution switch and promotion boundary remain separate. Rollout must be explicit and preserve the existing fail-closed display-date behavior.

## Real Failure Closure

The repair includes all currently observed Real failures:

1. Replace stale Strategy Catalog publication metrics with the authoritative enriched read model.
2. Resolve trusted historical relative artifact paths in Review Queue and stop stale fallback behavior.
3. Make the Daily Review landmark assertion exact so the main region and toolbar are not ambiguous.
4. Give Market Monitor list rows stable unique keys even when an asset appears more than once.
5. Restore the selected Theme Research section after returning from a company stock page.
6. Classify navigation-induced request aborts during direct refresh as expected cancellation, while retaining failures for genuine HTTP/network errors.
7. Make Generated Reports overview requests supply or safely resolve the display trade date instead of failing when the date is omitted.

## Testing Strategy

Implementation uses test-driven development:

- backend tests freeze catalog/publication convergence and safe historical path resolution;
- Review Queue tests prove it reads exactly the immutable 4/5/5 strategy artifacts and fails closed on invalid declarations;
- component tests prove technical identifiers are absent and human health states remain visible;
- focused tests cover unique keys, navigation restoration, exact landmarks, request-abort classification, and overview date resolution;
- full verification requires backend affected tests, all Dashboard unit tests, production build, Mock P0, and Real Playwright 41/41;
- the EOD profile must pass with browser acceptance enabled in the isolated verification command before rollout configuration is changed.

## Error Handling And Observability

Technical validation details remain available in structured API fields, logs, Playwright artifacts, and EOD reports. Human pages translate them into a small stable vocabulary and never expose raw IDs or filesystem paths. A publication mismatch blocks promotion and current-strategy display; it does not silently reuse static catalog results.

## Scope Boundaries

This change does not alter strategy formulas, parameters, historical returns, portfolio selection rules, or research data. It changes publication consumption, validation, presentation, and acceptance only. Cross-browser full Audit promotion remains a separate final verification after the Real profile is clean.
