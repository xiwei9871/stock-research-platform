# Playwright Real Audit And Sandbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real read-only, isolated write-sandbox, cross-browser, visual, inventory, and reporting capabilities, then execute the first frozen full-platform audit.

**Architecture:** Reuse the P0 fixtures and assertions from the preceding plan. Real tests call authoritative local APIs but reject all mutating requests; Sandbox tests run only against a PostgreSQL service whose database name ends in `_test`; the audit report joins a maintained route inventory with Playwright JSON results and a frozen issue ledger.

**Tech Stack:** Python 3.12+, PostgreSQL/psycopg, FastAPI, React 19, TypeScript, Playwright, Vitest, pytest, HTML/JSON reporting.

---

## Dependencies

Complete `docs/superpowers/plans/2026-07-20-playwright-first-p0-gate.md` first. This plan assumes the profile-aware Playwright config, route model, runtime fixture, and shared consistency assertions already exist.

## File Structure

- `config/platform_validation_routes.json`: maintained platform route/workspace/API inventory and assigned test layers.
- `src/stock_research/platform_validation_report.py`: inventory validation, Playwright-result ingestion, severity aggregation, coverage matrix, issue ledger, and HTML/JSON report generation.
- `scripts/build_platform_validation_report.py`: report CLI.
- `dashboard/tests/e2e/real/*.spec.ts`: read-only browser acceptance against real APIs and artifacts.
- `dashboard/tests/e2e/sandbox/*.spec.ts`: authenticated write workflows against an isolated test database.
- `dashboard/tests/e2e/visual/*.spec.ts`: selected stable-region screenshot assertions.
- `scripts/run_playwright_sandbox.py`: sandbox database guard, seed, service lifecycle, Playwright execution, and cleanup.
- `docs/ops/playwright-platform-validation.md`: execution and incident runbook.

### Task 1: Configurable Database Service And Sandbox Refusal Guard

**Files:**
- Modify: `src/stock_research/config.py`
- Create: `tests/test_config_settings.py`
- Create: `src/stock_research/playwright_sandbox.py`
- Create: `tests/test_playwright_sandbox.py`

- [ ] **Step 1: Write failing configuration tests**

```python
def test_settings_reads_research_service_from_environment(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_SERVICE", "stock_research_e2e_test")
    assert Settings().research_service == "stock_research_e2e_test"

def test_sandbox_rejects_non_test_database():
    with pytest.raises(RuntimeError, match="refusing non-test database"):
        assert_sandbox_database("stock_research")
```

Also test that an empty environment value retains `stock_research`, and that `stock_research_e2e_test` is accepted.

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_config_settings.py tests/test_playwright_sandbox.py -q`

Expected: FAIL because `Settings.research_service` is constant and the guard module does not exist.

- [ ] **Step 3: Implement the environment override**

Use a `default_factory` that reads `STOCK_RESEARCH_SERVICE`, strips whitespace, and falls back to `stock_research`. Do not change `hfq_service` or `qfq_service`.

- [ ] **Step 4: Implement the database identity guard**

`load_sandbox_database_name(service)` connects with `service=<name>` and executes `SELECT current_database()`. `assert_sandbox_database` accepts only names ending in `_test`; service-name text alone is not sufficient.

- [ ] **Step 5: Run focused and configuration regressions**

Run: `rtk .venv/bin/pytest tests/test_config_settings.py tests/test_playwright_sandbox.py tests/test_dashboard_auth_required.py tests/test_strategy_publication_store.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/config.py src/stock_research/playwright_sandbox.py tests/test_config_settings.py tests/test_playwright_sandbox.py
git commit -m "test: guard playwright sandbox database"
```

### Task 2: Maintained Platform Inventory

**Files:**
- Create: `config/platform_validation_routes.json`
- Create: `src/stock_research/platform_validation_report.py`
- Create: `tests/test_platform_validation_report.py`

- [ ] **Step 1: Write failing inventory-contract tests**

Validate unique IDs, unique canonical routes, valid `P0|P1|P2` priority, at least one assigned layer, a named Playwright profile for each P0 item, explicit auth/write flags, and an EOD flag only on read-only entries.

```python
assert inventory["schema_version"] == "platform_validation_inventory_v1"
assert {item["id"] for item in inventory["items"]} >= {
    "home", "review_queue", "daily_review", "market_monitor", "news",
    "research_reports", "stock_workspace", "watchlist", "theme_research",
    "docling_audit", "tech_bottleneck_review", "factor_lab",
    "strategy_lab", "generated_reports", "user_management", "data_explorer",
}
```

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_platform_validation_report.py -q`

Expected: FAIL because inventory and validator are missing.

- [ ] **Step 3: Add the complete inventory**

Each item contains `id`, `label`, `route`, `entry_kind`, `priority`, `auth`, `write_mode`, `primary_apis`, `layers`, `profiles`, `daily_eod`, and `owner`. Represent state-only workspaces with their new canonical paths from the P0 plan. Mark Data Explorer as `hidden` and record whether it is reachable or intentionally disabled; do not invent a main-navigation entry.

- [ ] **Step 4: Implement strict loading and coverage aggregation**

Add `load_inventory`, `validate_inventory`, and `build_coverage_matrix`. Invalid fields raise `ValueError` with the item ID and field name. Coverage status is one of `covered`, `partial`, `missing`, or `not_applicable`.

- [ ] **Step 5: Run focused tests**

Run: `rtk .venv/bin/pytest tests/test_platform_validation_report.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add config/platform_validation_routes.json src/stock_research/platform_validation_report.py tests/test_platform_validation_report.py
git commit -m "test: inventory platform validation surfaces"
```

### Task 3: Real Read-Only Fixture And Authoritative Snapshot

**Files:**
- Create: `dashboard/tests/e2e/real/test.ts`
- Create: `dashboard/tests/e2e/real/authoritativeSnapshot.ts`
- Create: `dashboard/tests/e2e/real/read-only-contract.spec.ts`

- [ ] **Step 1: Write failing read-only contract tests**

The control test performs GET requests successfully. Separate `test.fail` cases attempt POST, PATCH, PUT, and DELETE and must fail before the request reaches the server.

- [ ] **Step 2: Verify RED**

Run: `cd dashboard && PLAYWRIGHT_REAL_BASE_URL=http://127.0.0.1:5174 rtk pnpm test:e2e:real --grep @read-only-contract`

Expected: write attempts are not yet blocked by a profile fixture.

- [ ] **Step 3: Implement the Real fixture**

Reject any method outside `GET`, `HEAD`, and `OPTIONS` for `/api/**`. Attach request/response headers including `X-Request-ID`; redact cookies and authorization values. Extend the shared runtime fixture rather than creating a second console/request collector.

- [ ] **Step 4: Implement authoritative snapshot loading**

Required shape:

```ts
type AuthoritativeSnapshot = {
  displayTradeDate: string;
  candidateTradeDate: string;
  strategies: Array<{
    strategyId: string;
    tradeDate: string;
    totalReturnPct: number;
    contractId: string;
    publishId: string;
    artifactVersion: string;
  }>;
};
```

Load `/api/platform/display-date`, `/api/strategies/catalog`, and `/api/review-queue?trade_date=<display date>`. Fail closed if any official strategy lacks contract ID, publish ID, artifact version, performance date, or finite return.

- [ ] **Step 5: Run the contract**

Run: `cd dashboard && rtk pnpm test:e2e:real --grep @read-only-contract`

Expected: GET control passes and all mutating cases fail locally with `real_profile_write_forbidden`.

- [ ] **Step 6: Commit**

```bash
git add dashboard/tests/e2e/real
git commit -m "test: add real read-only playwright profile"
```

### Task 4: Real Critical Journeys And Route Census

**Files:**
- Create: `dashboard/tests/e2e/real/critical-journeys.spec.ts`
- Create: `dashboard/tests/e2e/real/route-census.spec.ts`
- Modify: `config/platform_validation_routes.json`

- [ ] **Step 1: Write failing Real acceptance tests**

Cover home strategy cards, review queue, global search to stock, theme-research company handoff, technology-bottleneck handoff, direct refresh, and back/forward using current real data. Derive entity IDs from API responses instead of hard-coding a stock that may disappear.

- [ ] **Step 2: Write the route census**

For every inventory item assigned to the Real profile, navigate directly, wait for its declared landmark, record status, primary API responses, console/page errors, and screenshot on failure. The census test does not click mutating controls.

- [ ] **Step 3: Verify RED against the local platform**

Run: `cd dashboard && rtk pnpm test:e2e:real`

Expected: initial failures become audit evidence; do not weaken assertions to obtain green.

- [ ] **Step 4: Fix only fixture or inventory defects**

If a route is intentionally unavailable, mark it `not_applicable` with an explicit reason in the inventory. Product defects remain failures for the frozen issue ledger and are not repaired inside this task.

- [ ] **Step 5: Re-run and save JSON results**

Run: `cd dashboard && PLAYWRIGHT_JSON_OUTPUT_NAME=test-results/real/results.json rtk pnpm test:e2e:real`

Expected: command may remain nonzero when product defects exist, but `results.json` and traces must be complete.

- [ ] **Step 6: Commit test and inventory corrections**

```bash
git add dashboard/tests/e2e/real/critical-journeys.spec.ts dashboard/tests/e2e/real/route-census.spec.ts config/platform_validation_routes.json
git commit -m "test: census real dashboard routes"
```

### Task 5: Isolated Sandbox Seed, Write Tests, And Cleanup

**Files:**
- Modify: `src/stock_research/playwright_sandbox.py`
- Modify: `tests/test_playwright_sandbox.py`
- Create: `scripts/run_playwright_sandbox.py`
- Create: `tests/test_run_playwright_sandbox.py`
- Create: `dashboard/tests/e2e/sandbox/auth-admin.spec.ts`
- Create: `dashboard/tests/e2e/sandbox/operator-decision.spec.ts`

- [ ] **Step 1: Write failing seed/cleanup tests**

Use an injected connection to prove deterministic seed IDs prefixed by an audit run ID, cleanup order, rollback after an exception, and refusal when the database name is not `_test`.

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_playwright_sandbox.py tests/test_run_playwright_sandbox.py -q`

Expected: FAIL because seed and runner functions are missing.

- [ ] **Step 3: Implement sandbox lifecycle**

The runner:

1. verifies the database name;
2. applies the dashboard auth schema and required operator tables;
3. creates `e2e_<run_id>_admin` and `e2e_<run_id>_user`;
4. inserts one review session, evidence-linked operator decision, and required read fixtures;
5. starts auth-required, write-guarded API and Vite servers with the test service;
6. executes `pnpm test:e2e:sandbox`;
7. deletes sessions, auth audit rows, users, operator events, and review sessions for the run ID in a `finally` block;
8. returns the Playwright exit code after cleanup.

- [ ] **Step 4: Add write journeys**

`auth-admin.spec.ts` logs in as admin, creates a user, disables/enables it, resets its password, logs out, and verifies the new password. `operator-decision.spec.ts` edits notes/follow-up fields, refreshes the page, verifies persistence, and proves no auto-trade control exists.

- [ ] **Step 5: Run against a dedicated database**

Run:

```bash
PLAYWRIGHT_SANDBOX_SERVICE=stock_research_e2e_test \
rtk .venv/bin/python scripts/run_playwright_sandbox.py
```

Expected: PASS and a final database query returns zero rows whose username, event ID, or review session ID contains the run ID.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/playwright_sandbox.py tests/test_playwright_sandbox.py scripts/run_playwright_sandbox.py tests/test_run_playwright_sandbox.py dashboard/tests/e2e/sandbox
git commit -m "test: add isolated dashboard write sandbox"
```

### Task 6: Cross-Browser, Visual Regions, And Accessibility

**Files:**
- Create: `dashboard/tests/e2e/visual/key-regions.spec.ts`
- Create: `dashboard/tests/e2e/audit/accessibility.spec.ts`
- Modify: `dashboard/playwright.config.ts`

- [ ] **Step 1: Add stable region screenshot tests**

Cover login panel, home strategy-performance region, selected review-queue formal-contract region, stock source-context region, theme-research header/tabs, and technology-bottleneck summary. Mask dates, live values, generated timestamps, chart canvases, and cursor overlays.

- [ ] **Step 2: Add accessibility checks**

Assert one main landmark, unique heading hierarchy for the page title, accessible names for navigation and primary controls, visible keyboard focus, and no focus trap in search/results and modal-like readers. Do not introduce an additional accessibility package in this phase.

- [ ] **Step 3: Run Chromium and approve the initial snapshots manually**

Run: `cd dashboard && PLAYWRIGHT_PROFILE=audit rtk pnpm exec playwright test tests/e2e/visual/key-regions.spec.ts --project=chromium-desktop --update-snapshots`

Expected: snapshots are created only after manual inspection.

- [ ] **Step 4: Run the audit matrix**

Run: `cd dashboard && rtk pnpm test:e2e:audit`

Expected: Chromium desktop/mobile and Firefox cover all audit tests; WebKit runs only tests tagged `@webkit-critical`.

- [ ] **Step 5: Commit reviewed baselines**

```bash
git add dashboard/tests/e2e/visual dashboard/tests/e2e/audit dashboard/playwright.config.ts
git commit -m "test: add cross-browser visual audit"
```

### Task 7: Audit Report Generator

**Files:**
- Modify: `src/stock_research/platform_validation_report.py`
- Modify: `tests/test_platform_validation_report.py`
- Create: `scripts/build_platform_validation_report.py`

- [ ] **Step 1: Write failing report tests**

Fixture results must produce `route_inventory.json`, `coverage_matrix.json`, `issue_ledger.json`, and `audit_report.html`. Test P0/P1/P2 ordering, stable issue IDs, escaped HTML, evidence links, and distinction between `baseline_candidate` and `trusted_baseline`.

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_platform_validation_report.py -q`

Expected: report-generation tests fail because Playwright ingestion and rendering are absent.

- [ ] **Step 3: Implement Playwright JSON ingestion**

Normalize each failed test to:

```python
{
    "issue_id": "PV-P0-<stable hash>",
    "test_id": "<project>::<file>::<title>",
    "inventory_ids": ["home"],
    "severity": "P0",
    "status": "open",
    "expected": "...",
    "actual": "...",
    "evidence": ["relative/path/to/trace.zip"],
}
```

Never embed cookies, passwords, or full request headers.

- [ ] **Step 4: Render JSON and HTML**

Use the standard library `html` module and deterministic ordering. The first screen shows revision, audit ID, date, profile/browser counts, blocker counts, and whether a trusted baseline exists.

- [ ] **Step 5: Run focused tests and CLI fixture smoke**

Run: `rtk .venv/bin/pytest tests/test_platform_validation_report.py -q && rtk .venv/bin/python scripts/build_platform_validation_report.py --help`

Expected: PASS and CLI exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/platform_validation_report.py tests/test_platform_validation_report.py scripts/build_platform_validation_report.py
git commit -m "feat: report platform validation audit"
```

### Task 8: Execute And Freeze The First Audit

**Files:**
- Create: `docs/ops/playwright-platform-validation.md`
- Create: `docs/reviews/platform-validation-initial-audit-2026-07-20.md`
- Modify: `config/platform_validation_routes.json` only for verified inventory corrections.

- [ ] **Step 1: Freeze the audit inputs**

Record commit SHA, inventory hash, Playwright version, browser versions, database service, dashboard/API URLs, and audit ID. Do not edit product code after this point until the issue ledger is generated.

- [ ] **Step 2: Run all layers**

Run backend focused contracts, full dashboard Vitest, dashboard build, P0 Mock, Real read-only, Sandbox, and the Audit browser matrix. Preserve every command, exit code, JSON result, HTML report, trace, and screenshot under `outputs/research/platform_validation/<audit_id>/`.

- [ ] **Step 3: Generate and freeze the issue ledger**

Run `scripts/build_platform_validation_report.py` with the frozen inventory and all Playwright JSON result paths. Copy the human summary, not generated binaries, into `docs/reviews/platform-validation-initial-audit-2026-07-20.md`.

- [ ] **Step 4: Classify without repairing**

Confirm each open issue has exactly one P0/P1/P2 severity, reproducible command, expected/actual evidence, and an owner area. Duplicate symptoms share one root issue with multiple evidence links.

- [ ] **Step 5: Apply the stop rule**

If any P0 or P1 product issue exists, stop here and create one focused design/plan per independent root cause. Do not mark a trusted baseline. After those fixes merge, rerun this task with a new audit ID and retain the original frozen ledger.

- [ ] **Step 6: Finalize the trusted baseline when clean**

When no P0/P1 issue remains and all accepted P2 items have explicit disposition, regenerate the report with status `trusted_baseline`, retain the baseline long term, and document the 90-day daily-evidence retention rule.

- [ ] **Step 7: Commit runbook and audit summary**

```bash
git add docs/ops/playwright-platform-validation.md docs/reviews/platform-validation-initial-audit-2026-07-20.md config/platform_validation_routes.json
git commit -m "docs: freeze initial platform validation audit"
```
