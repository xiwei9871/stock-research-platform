# Platform Hardening Runbook

Updated: 2026-07-20

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
