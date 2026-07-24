# Platform Runtime Unification Design

**Date:** 2026-07-24

**Status:** Approved design, pending written-spec review

## Context

The 2026-07-23 review queue incident is not a single strategy-data failure. The host currently runs different parts of the platform from different Git checkouts:

- the dashboard on port `5174` and the API on port `8765` run from the Playwright validation worktree;
- scheduled platform-ready and EOD commands invoke scripts from the main checkout;
- older LaunchAgent definitions still reference the archived `v0.1-local-eod-web` worktree;
- the main checkout also contains three unrelated modified research datasets that must not be overwritten or included in this repair.

This split allows a newer frontend and API contract to validate artifacts produced by older runtime code. On 2026-07-23 the scheduled checkout produced only legacy strategy outputs, while the served API required the formal strategy publication manifest and audit artifacts. The review queue correctly remained on the last publishable date and displayed freshness errors.

The same run also exposed two correctness defects:

1. the market-monitor build stopped after BaoStock returned `10001001 用户未登录` for an index query;
2. the outer `repair_market_monitor` action was recorded as successful even though its nested stage returned `status=failed` with zero rows.

## Goal

Establish one stable, auditable runtime checkout for the dashboard, API, scheduled platform-ready build, Auto EOD Repair, and strategy publication. Repair the two failure-handling defects, rerun the 2026-07-23 close chain, and prove that the user-facing review queue advances only when one consistent publication contract passes.

## Non-Goals

- Do not redesign strategy logic, rankings, or return calculations.
- Do not weaken the review-queue freshness or publication gates merely to remove warnings.
- Do not revive Firefox coverage; the accepted browser matrix remains Chromium-first.
- Do not modify or commit the three dirty Tech Bottleneck research dataset files in the main checkout.
- Do not make unrelated repository-wide refactors or clean up every historical worktree.
- Do not expose formal contract ids, publication ids, or artifact versions in the human-facing strategy cards.

## Selected Approach

Create a dedicated stable runtime worktree and branch from the current main checkout, then integrate the validated Playwright/strategy-publication branch into it. All live services and daily jobs will be repointed to this one checkout.

This is preferred over the alternatives:

- **Directly merge and run from the main checkout:** rejected because it contains unrelated user-owned generated-data modifications and remains an unsafe deployment root.
- **Keep the split checkouts and add compatibility shims:** rejected because it preserves the cause of the incident and makes future publication drift likely.
- **Temporarily run the older scripts to clear the warning:** rejected because legacy output does not satisfy the current formal publication contract and would only hide the mismatch.

The stable checkout is:

```text
/Users/xiwei/stock_research/.worktrees/platform-runtime-unification-20260724
```

The stable branch is:

```text
codex/platform-runtime-unification-20260724
```

## Architecture

### 1. One Runtime Root

The following consumers must resolve to the same absolute repository root and Git commit:

- Vite dashboard on port `5174`;
- dashboard API on port `8765`;
- OpenClaw platform-ready build;
- OpenClaw platform-ready check / Auto EOD Repair;
- strategy daily EOD publication;
- any loaded LaunchAgent that participates in the same daily chain.

The runtime root must be explicit in service and job definitions. Jobs must not infer it from the caller's current directory, and no live definition may reference the archived `v0.1-local-eod-web` checkout.

Each run summary must record the resolved runtime root and Git commit. This makes mixed-code execution detectable from artifacts rather than only from process inspection.

### 2. Branch Integration

The stable branch begins at main commit `3453ebd` and integrates `codex/playwright-first-platform-validation-20260720`. Conflict resolution must preserve:

- the current main branch's later data-pipeline and authentication repairs;
- the Playwright branch's formal strategy publication contract;
- latest-market-date defaults for stock workspaces;
- latest-available-review-date defaults for review pages;
- strategy-card navigation into the matching review-queue strategy;
- the Chromium-first Mock, Real, Audit, Sandbox, and EOD acceptance matrix.

Integration is complete only when tests prove the combined behavior. Commit ancestry alone is not evidence of compatibility.

### 3. BaoStock Session Recovery

BaoStock access must be isolated behind a session-aware query boundary. For retryable authentication/session failures, including `10001001 用户未登录`, the boundary will:

1. invalidate the current session;
2. perform one explicit re-login;
3. retry the failed query once;
4. return the successful rows or a truthful failed result.

The retry is bounded. A second authentication failure is not retried indefinitely and must remain a blocking market-monitor error. Non-authentication errors keep their existing retry classification; the design does not convert arbitrary network or data errors into authentication retries.

The daily chain must continue to serialize BaoStock-sensitive work where existing contracts require one worker. Session recovery does not authorize concurrent BaoStock ingestion.

### 4. Truthful Nested Status Propagation

A repair action may only be `success` when its nested builder result is publishable. The adapter must normalize nested results as follows:

| Nested result | Outer action status | Consequence |
|---|---|---|
| `success` with required rows/artifacts | `success` | Continue to recheck |
| publishable `degraded` | `degraded` | Continue with warning |
| `failed`, zero required rows, or missing required artifact | `failed` | Preserve blocker and stop dependent stages |
| exception | `failed` | Record safe exception detail and recheck |

The market-monitor adapter is the first regression target, but the normalization helper should be reusable by other repair actions. The outer status must never contradict a nested failed status.

### 5. Publication And Display Contract

Auto EOD Repair must rebuild the dependency chain in order:

```text
market data and features
  -> market monitor
  -> strategy publication
  -> review queue manifest and score audit
  -> platform readiness
  -> browser acceptance
  -> frontend display date
```

The dashboard may advance to a new date only after the formal strategy manifest, strategy artifacts, score audit, readiness checks, and required browser acceptance all pass for that date.

If repair remains blocked, the UI keeps the latest publishable review date and shows a concise freshness warning. It must not manufacture current-date strategy rows from legacy outputs. Human-facing cards continue to show strategy names, performance, holdings, risks, and review entry points without internal contract/version metadata.

### 6. Scheduled Job And Service Cutover

Cutover is an atomic operational step:

1. stop the dashboard/API processes that run from the Playwright validation worktree;
2. update OpenClaw job commands to the stable runtime root;
3. update, unload, or disable relevant stale LaunchAgent definitions so they cannot invoke an archived checkout;
4. start the dashboard/API from the stable runtime root;
5. confirm process working directories and served commit identity;
6. run a check-only readiness pass before the repair run.

If any step fails, do not leave two competing schedulers or two API instances active. Roll back the service/job paths to the last known definitions and keep the review date gated.

## Data And Artifact Safety

- The existing PostgreSQL databases and output directories remain the data authority; the worktree change affects code location, not database ownership.
- Sandbox tests must use the configured isolated sandbox database and must not write to the real operational database.
- Repair actions remain idempotent for a trade date and may only overwrite deterministic outputs or upsert keyed rows.
- The three modified files under `outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/` in the main checkout remain untouched and unstaged.
- Before cutover, record current job definitions, loaded services, process ids, working directories, branch names, and commits for rollback evidence.

## Error Handling

- A failed re-login or failed retry returns a blocking failure with the BaoStock code and affected symbol/query, without logging credentials.
- A nested failed builder result propagates to the action, stage, final repair status, and operator report.
- Downstream strategy publication is skipped while market-monitor blockers remain.
- Reports and summaries are written even when repair exits nonzero.
- Scheduled wrappers preserve the child exit code and continue to emit compact human-readable terminal output.
- Browser acceptance remains fail-closed: invalid, stale, or missing acceptance evidence cannot advance the display date.

## Testing Strategy

Implementation follows test-driven development.

### Unit And Focused Backend Tests

- authentication failure triggers exactly one logout/re-login/retry sequence;
- successful retry returns the expected index rows;
- repeated authentication failure returns a blocking failure;
- non-authentication failures do not enter the auth retry loop;
- nested `failed` and zero-row market-monitor results make the outer action fail;
- nested `degraded` remains visible and publishable only when the shared contract allows it;
- run summaries include runtime root and Git commit.

### Integration Tests

- merge-compatible strategy publication produces the formal manifest, three strategy artifacts, and score audit;
- review queue chooses the latest publishable review date independently from latest market-chart dates;
- strategy cards route to the review queue with the corresponding strategy selected;
- sandbox runs prove database isolation;
- scheduled wrappers resolve the configured stable root rather than caller cwd.

### Playwright-First Matrix

Run the accepted Chromium-first matrix from the stable checkout:

- Mock: deterministic UI and navigation behavior;
- Real: live local API/data integration;
- Audit: publication evidence and date consistency;
- Sandbox: isolated write-path behavior;
- EOD: full close repair, publication, readiness, and display gate.

Firefox is not a release blocker because it is not part of the normal platform usage. Cross-browser coverage can be reconsidered separately.

## 2026-07-23 Recovery Procedure

After code and runtime cutover pass focused tests:

1. run platform-ready check mode for `2026-07-23`;
2. run Auto EOD Repair for `2026-07-23` from the stable root;
3. verify required market-monitor sources are populated;
4. verify the formal strategy publication manifest, all three strategy outputs, and score audit exist for the accepted review date;
5. run the complete Mock, Real, Audit, Sandbox, and EOD matrix;
6. inspect `/api/platform/readiness`, `/api/platform/summary`, and `/api/review-queue`;
7. verify the review queue and stock workspace in Chromium.

The repair is not considered successful merely because the command exits zero. Artifact contents, API dates, page dates, navigation targets, and publication identity must agree.

## Acceptance Criteria

- All live platform processes and daily jobs resolve to the stable runtime root and one commit.
- No active job or service references the main dirty checkout or archived `v0.1-local-eod-web` worktree.
- The main checkout's three modified Tech Bottleneck datasets are unchanged.
- BaoStock `10001001` receives one bounded re-login retry and reports a truthful blocker if recovery fails.
- No repair action reports success when its nested builder failed or produced zero required rows.
- The formal strategy manifest, LHB, Mid Trend, Tech Bottleneck, and score-audit artifacts satisfy the current publication contract.
- The stock workspace defaults to latest available market data.
- The review queue defaults to latest publishable review date unless the user explicitly selects a historical date.
- Strategy-card buttons open the review queue with the corresponding strategy selected.
- Human-facing strategy cards do not show internal contract, publication, or artifact version identifiers.
- The Chromium-first Mock, Real, Audit, Sandbox, and EOD matrix passes from the stable checkout.
- A new issue list and final acceptance report distinguish fixed items, remaining blockers, and non-blocking warnings.

## Rollback

If integration or cutover fails:

1. keep the frontend display gate on the last publishable review date;
2. restore recorded OpenClaw and service definitions;
3. restart the previously known dashboard/API checkout only if it is internally consistent;
4. leave the stable integration branch and test artifacts available for diagnosis;
5. do not delete or reset the dirty main checkout.

No database rollback is automatic. Any data rollback requires a separate evidence-based decision because repair actions are designed as deterministic upserts.
