# Platform Hardening Runbook

Updated: 2026-07-21

## Scope

This runbook covers the first-wave hardening controls added after the expert review:

- Platform readiness policy separates dashboard availability from publication readiness.
- Dashboard UI shows degraded-ready states as viewable but not publishable.
- Publication write paths can fail closed with HTTP 409.
- Write/admin/replay endpoints can require `X-Dashboard-Write-Token`.
- Operator decision writes are validated at the API boundary and require evidence linkage.
- Public dashboard read models whitelist response fields and have a materialized-view extension point.
- API responses include `X-Request-ID` for troubleshooting.

## Readiness Policy

`READY` means the dashboard can be viewed and publication is allowed.

`DEGRADED_READY` means the dashboard can be viewed, but publication is blocked until the policy blocking reasons are cleared.

Any mismatched or missing latest ready trade date blocks both dashboard readiness and publication readiness.

Key modules:

- `src/stock_research/dashboard/readiness_policy.py`
- `src/stock_research/dashboard/ops_snapshot.py`
- `src/stock_research/dashboard/readiness.py`
- `src/stock_research/platform_ready.py`

## Operator Actions

`POST /api/operator-decisions` now checks platform publication readiness before writing.

Expected behavior:

- Ready platform: returns `200`.
- Degraded or blocked platform: returns `409` with `detail.error=platform_not_ready_for_publication`.
- Invalid input: returns `400` before write.

Validated fields include asset id, operator action, decision label, decision status, evidence linkage, source context, tags, and follow-up date ordering.

Operator decisions must remain manual review records:

- `manual_review_required` is forced to `true`.
- `auto_trade_enabled=true` is rejected.
- Evidence linkage must be supplied through `evidence_artifact_id`, `evidence_digest_snapshot_id`, `review_item_snapshot_id`, or the matching fields inside `source_context`.

## Write Guard

Endpoint-local write guards are disabled by default.

Enable them with:

```bash
export STOCK_RESEARCH_DASHBOARD_WRITE_GUARD=true
export STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN='<shared-token>'
```

Guarded endpoints require:

```text
X-Dashboard-Write-Token: <shared-token>
```

Guarded endpoints:

- `POST /api/operator-decisions`
- `PATCH /api/operator-decisions/{event_id}`
- `POST /api/public-news/refresh`
- `POST /api/dashboard/cache/clear`
- `POST /api/backtests/jobs`
- `POST /api/backtests/run`
- `POST /api/backtests/run-fresh`
- `POST /api/backtests/run-replay`

## Dashboard API Boundary

`GET /api/platform/summary` uses a read model whitelist. Internal fields added by service code must not pass through the API unless they are explicitly added to the read model.

`load_platform_summary()` delegates to `build_platform_summary_read_model()`. The loader first tries `ops.dashboard_platform_summary_daily`; when that read model is absent or empty, it falls back to the current base-table queries and marks `source=base_table_fallback`.

Key module:

- `src/stock_research/dashboard/read_models.py`

## Request ID

Every API response includes `X-Request-ID`.

If the caller supplies `X-Request-ID`, the API echoes it. Otherwise it generates one. Use this id in issue reports and expert review notes when comparing UI behavior with backend logs.

## Local Verification

Run focused backend smoke:

```bash
rtk .venv/bin/pytest tests/test_dashboard_app.py tests/test_dashboard_ops_snapshot.py tests/test_dashboard_api_guardrails.py tests/test_dashboard_operator_decisions.py tests/test_dashboard_read_models.py tests/test_dashboard_platform.py tests/test_strategy_daily_eod.py tests/test_schema.py -q
```

Run focused frontend smoke:

```bash
rtk pnpm vitest run tests/client.test.ts tests/operator-decision-panel.test.tsx tests/home-cockpit.test.tsx tests/app-shell.test.tsx
```

Use the dashboard working directory for the frontend command:

```bash
/Users/xiwei/stock_research/dashboard
```

Run dashboard build:

```bash
rtk pnpm build
```

## Playwright Profiles And Commands

Run Playwright commands from `dashboard/`:

```bash
rtk pnpm test:e2e:p0
rtk pnpm test:e2e
rtk pnpm test:e2e:real
rtk pnpm test:e2e:sandbox
rtk pnpm test:e2e:audit
rtk pnpm test:e2e:eod
```

Profile responsibilities:

- `mock`: mandatory deterministic P0 pull-request gate. It starts Vite only, fails closed on every unregistered `/api/**` request, runs all P0 tests on Chromium desktop, and runs the `@mobile` subset on Chromium mobile.
- `legacy`: top-level compatibility smoke. `app-smoke.spec.ts` is limited to shell/responsive coverage; broad workspace exploration remains in `platform-full-flow.spec.ts`.
- `real`: read-only journeys against the local API.
- `sandbox`: explicitly isolated write-capable journeys.
- `audit`: expanded browser and visual coverage for release audits.
- `eod`: the small Chromium acceptance subset used by Auto EOD Repair.

The P0 Mock suite is mandatory for every pull request. Future affected-test selection may add focused tests, but must not skip or replace `pnpm test:e2e:p0`.

## Browser Evidence

Playwright writes profile-separated evidence under:

- HTML report: `dashboard/playwright-report/<profile>/`
- JSON report and test artifacts: `dashboard/test-results/<profile>/`
- Per-test runtime attachment: `runtime-evidence.json`

The shared runtime fixture records console errors, page errors, failed requests, and unhandled API routes. Traces, screenshots, and videos are retained on failure. Expected failure-isolation responses require a test-local, exact allowlist; broad or global allowlists are prohibited. Tests must use the shared measured horizontal-overflow assertion instead of ad hoc viewport checks or repository-absolute screenshot paths.

## Browser Tag Policy

- `@p0`: critical user journey and required Mock gate coverage.
- `@mock`: deterministic API fixtures; all unregistered API routes return `599` and fail the test.
- `@mobile`: intentionally small mobile subset selected by the Mock mobile project.
- `@failure-isolation`: local degraded/error behavior, retry success, deep-route refresh, and mobile overflow contracts.
- Journey tags such as `@handoff`, `@publication`, and `@auth` identify the protected cross-workspace contract.
- `@webkit-critical` is reserved for the selective WebKit subset in the Audit profile.

## CI

The GitHub Actions workflow `.github/workflows/platform-smoke.yml` runs backend-focused and dashboard-focused smoke jobs on pull requests and pushes to `main` or `lhb-shortline-strategy-dev-20260609`.

The same workflow installs Playwright Chromium and runs `pnpm test:e2e:p0`. On failure it uploads `dashboard/playwright-report` and `dashboard/test-results/mock`, including the structured runtime evidence used to classify the failure.

## Playwright-First Daily Auto EOD Repair

The daily EOD loop runs browser acceptance only after the strategy publication cohort is available and upstream blockers are clear. Browser acceptance execution is fail-safe disabled unless `STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED=true`; when disabled, the browser check and action are removed before either can run. The cron entrypoint remains a single Python orchestration process:

```bash
rtk scripts/run_eod_auto_repair_cron.sh YYYY-MM-DD
```

The wrapper exports the browser evidence root to the same daily directory and does not start a second Playwright command:

```text
outputs/research/eod_auto_repair/<trade-date>/
├── run_summary.json
├── run_report.md
├── run_report.html
└── browser/
```

Operational rules:

- `run_summary.json`, Markdown, and HTML are generated from the same canonical `RepairRunSummary` and written atomically with file mode `0600`; the daily output directory is `0700`.
- The report shows the independent EOD orchestration run ID separately from the strategy publication cohort run ID.
- The final browser status comes from the final `dashboard_browser_acceptance` check. The repair action result and both attempt results are shown separately.
- Browser evidence is linked with relative, percent-encoded paths. Traces, screenshots, and JSON reports are never inlined.
- Only `stale_cache`, `presentation_runtime`, and `critical_request_transport` are eligible for one cache clear followed by one rerun of the identical `pnpm test:e2e:eod` command. All other consistency, publication-identity, date, return-unit, contract, and rollback failures are nonrepairable and never clear cache.
- A failed browser manifest blocks the candidate and preserves the last ready display date. A report or retention infrastructure failure changes the EOD result to failed and the CLI exits `2`.
- Retention removes only successful, fully evidenced, non-baseline daily directories older than 90 days. Missing, degraded, failed, symlinked, out-of-tree, initial-baseline, or incomplete evidence is retained.

The execution switch and the promotion boundary are independent and must be changed together during rollout:

- `STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED=false` (the default) omits browser acceptance from the cron/Python repair loop.
- An empty `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM` disables the Dashboard display gate boundary.

Do not enable either value until the controlled rollout checklist in [Playwright Platform Validation](playwright-platform-validation.md) is complete. When browser acceptance is enabled, `DASHBOARD_CACHE_CLEAR_URL` must target the exact local-only path `/api/dashboard/cache/clear` on a literal IPv4/IPv6 loopback address. If login credentials are configured, `DASHBOARD_AUTH_LOGIN_URL` must use the same scheme, literal address, and effective port with the exact path `/api/auth/login`. Userinfo, query strings, fragments, DNS names (including `localhost`), cross-origin login, redirects, invalid ports, and environment proxies are rejected. Any unset or unsafe URL makes a repairable cache-clear attempt fail as infrastructure rather than silently skipping it.

Rollback procedure:

1. For a one-shot safe EOD invocation, run the real kill switches together:

   ```bash
   STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED=false STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM= rtk scripts/run_eod_auto_repair_cron.sh YYYY-MM-DD
   ```

2. For persistent rollback, set `STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED=false` and clear `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM` in the actual external scheduler environment. This repository does not define a managed scheduler unit, so use the process manager that owns the deployed cron/job instead of naming an invented service.
3. Clear `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM` in the Dashboard service environment and restart that service with its actual process manager. Restart the EOD scheduler process only if its environment is cached by the scheduler.
4. Keep the last ready display date and every existing browser/report evidence directory unchanged.
5. Verify the display gate still selects the prior ready date and that no unvalidated candidate becomes official.

As of the 2026-07-21 controlled review, rollout remains `BLOCKED / stop_and_plan`; no boundary, environment, or deployment value was changed. See [EOD browser acceptance rollout review](../reviews/eod-browser-acceptance-rollout-2026-07-20.md).
