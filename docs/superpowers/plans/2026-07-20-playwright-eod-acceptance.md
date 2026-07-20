# Playwright EOD Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate a five-to-ten-minute Chromium browser acceptance stage into Auto EOD Repair so official display advances only after critical pages agree with the candidate strategy publication.

**Architecture:** Playwright renders the real frontend and real candidate APIs through an isolated auth-disabled server, overriding only the display-date selector so the not-yet-official candidate can be inspected safely. Python classifies the browser result, performs at most one whitelisted cache repair for presentation failures, persists a browser-acceptance manifest, and lets the existing display-date gate advance only when that manifest is success or degraded.

**Tech Stack:** Python 3.12+, dataclasses, subprocess, PostgreSQL/psycopg, existing data-run manifests, Playwright Chromium, React 19, FastAPI, JSON/Markdown/HTML reports, shell cron wrapper.

---

## Dependencies

Complete `docs/superpowers/plans/2026-07-20-playwright-first-p0-gate.md` first. Complete the Real fixture portion of `docs/superpowers/plans/2026-07-20-playwright-real-audit-sandbox.md` before Task 2. The full initial audit may continue independently, but this plan must not be enabled until the P0 suite is stable.

## File Structure

- `dashboard/tests/e2e/eod/candidateDisplay.ts`: real candidate API snapshot and safe display-date override.
- `dashboard/tests/e2e/eod/eod-critical.spec.ts`: daily home, strategy, review-queue, deep-link, runtime, and no-rollback checks.
- `dashboard/tests/e2e/eod/eodReporter.ts`: deterministic browser-acceptance JSON writer.
- `src/stock_research/eod_browser_acceptance.py`: Playwright runner, result parser, severity classifier, bounded cache repair, manifest persistence, and prior-publication loader.
- `tests/test_eod_browser_acceptance.py`: command, parsing, classification, repair, manifest, and no-rollback tests.
- `src/stock_research/eod_auto_repair_report.py`: human-readable HTML report for the complete EOD chain.
- Existing EOD repair/check/model/script files: orchestration, check registration, action ordering, progress, and operator output.

### Task 1: Explicit Publish Start Time In Read Models

**Files:**
- Modify: `src/stock_research/dashboard/backtests.py`
- Modify: `tests/test_dashboard_backtests.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/tests/platform-client.test.ts`

- [ ] **Step 1: Write failing projection tests**

Prove that official strategy metrics retain the `publish_id` introduced by the P0 plan and also contain `publish_started_at`, sourced from the same data-run manifest module as contract ID and artifact version.

```python
assert metrics["publish_id"] == "publish-20260720"
assert metrics["publish_started_at"] == "2026-07-20T12:30:00+00:00"
```

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_dashboard_backtests.py -q`

Expected: FAIL only for `publish_started_at`; the existing `publish_id` regression assertion remains green.

- [ ] **Step 3: Project the fields fail closed**

Read `publish_id` from module metadata and `started_at` from the manifest row. Include both in successful `latest_metrics`; include `None` in failed-contract shapes. Update `StrategyCatalogItem.latest_metrics` accordingly.

- [ ] **Step 4: Verify API typing and serialization**

Run: `rtk .venv/bin/pytest tests/test_dashboard_backtests.py tests/test_dashboard_app.py -q && cd dashboard && rtk pnpm test -- platform-client.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/backtests.py tests/test_dashboard_backtests.py dashboard/src/api/types.ts dashboard/tests/platform-client.test.ts
git commit -m "feat: expose strategy publish identity timestamps"
```

### Task 2: Candidate Display Override And EOD Browser Suite

**Files:**
- Create: `dashboard/tests/e2e/eod/candidateDisplay.ts`
- Create: `dashboard/tests/e2e/eod/eod-critical.spec.ts`
- Create: `dashboard/tests/e2e/eod/eodReporter.ts`
- Modify: `dashboard/playwright.config.ts`

- [ ] **Step 1: Write failing candidate-snapshot tests**

The helper must reject a missing trade date, missing official strategy, nonfinite return, contract mismatch, missing publish ID, performance date different from the requested date, review-queue publication mismatch, and a publish timestamp older than the previous successful publication.

- [ ] **Step 2: Verify RED**

Run: `cd dashboard && PLAYWRIGHT_EOD_TRADE_DATE=2026-07-20 rtk pnpm test:e2e:eod`

Expected: FAIL because the EOD helper and specs do not exist.

- [ ] **Step 3: Implement candidate API loading**

Load real `/api/strategies/catalog`, `/api/review-queue?trade_date=<target>`, `/api/platform/readiness`, and `/api/platform/summary`. Build:

```ts
type CandidatePublication = {
  strategyId: 'lhb_shortline' | 'mid_trend' | 'tech_bottleneck';
  tradeDate: string;
  totalReturnPct: number;
  contractId: string;
  publishId: string;
  publishStartedAt: string;
  artifactVersion: string;
};
```

Read `PLAYWRIGHT_EOD_PREVIOUS_PUBLICATIONS_JSON` and require candidate trade date to be later than the previous trade date, or candidate `publishStartedAt` to be later when rerunning the same date.

- [ ] **Step 4: Override only display selection**

Intercept readiness, platform summary, display-date, market-monitor, and review-queue requests. Fetch the real response, preserve all fields, set display/candidate/latest dates to the requested trade date where the endpoint supports them, and force the review-queue query to the requested date. Do not intercept strategy values, publication identity, stock data, or theme data.

- [ ] **Step 5: Add three daily tests**

1. `@eod @blocker-consistency`: home strategy cards exactly match candidate API values and contain no `175.29%` LHB regression.
2. `@eod @blocker-consistency`: review queue, strategy cards, contract IDs, publish IDs, artifact versions, and performance dates agree for all three strategies.
3. `@eod @blocker-runtime`: one representative current stock deep link, one theme-research deep link, and one technology-bottleneck deep link load without white screen, fatal console error, unhandled critical request, or wrong route context.

- [ ] **Step 6: Implement the reporter**

Write `eod-browser-acceptance.json` with schema version, run ID, trade date, revision, start/end timestamps, duration, status, per-test status/severity, failures, attachments, and authoritative candidate snapshot. Map failed `@warning` tests to `degraded`; any failed `@blocker-*` test maps to `failed`.

- [ ] **Step 7: Run against a controlled local date**

Run:

```bash
cd dashboard
PLAYWRIGHT_PROFILE=eod \
PLAYWRIGHT_EOD_TRADE_DATE=2026-07-20 \
PLAYWRIGHT_EOD_OUTPUT_DIR=../outputs/research/eod_auto_repair/2026-07-20/browser \
rtk pnpm test:e2e:eod
```

Expected: exit 0 only when the candidate is internally consistent; reporter JSON always exists even on failure.

- [ ] **Step 8: Commit**

```bash
git add dashboard/tests/e2e/eod dashboard/playwright.config.ts
git commit -m "test: validate eod candidate in browser"
```

### Task 3: Python Runner, Classification, And Bounded Repair

**Files:**
- Create: `src/stock_research/eod_browser_acceptance.py`
- Create: `tests/test_eod_browser_acceptance.py`

- [ ] **Step 1: Write failing runner tests**

Cover exact subprocess arguments and environment, isolated dashboard/API ports, forced non-reuse of existing servers, missing pnpm, timeout, malformed/missing report, success, degraded warnings, consistency failure, runtime failure, cache repair and single rerun, redaction, artifact paths, and prior-publication loading.

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_eod_browser_acceptance.py -q`

Expected: FAIL because the runner module is missing.

- [ ] **Step 3: Implement immutable result types**

```python
@dataclass(frozen=True)
class BrowserAcceptanceResult:
    status: RepairStatus
    trade_date: str
    run_id: str
    duration_seconds: float
    failure_classes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    artifact_paths: tuple[str, ...] = ()
    snapshot: dict[str, object] = field(default_factory=dict)
```

Implement `run_browser_acceptance`, `parse_browser_acceptance_report`, `load_previous_official_publications`, and `classify_browser_failures`.

- [ ] **Step 4: Implement the repair whitelist**

Only failure classes `presentation_runtime`, `critical_request_transport`, and `stale_cache` may invoke the injected `cache_clearer`. Run the same Playwright command once more after cache clear. Classes `api_ui_mismatch`, `publication_identity`, `date_regression`, `return_unit`, `contract_mismatch`, and `publish_rollback` never trigger automatic data or identity changes.

- [ ] **Step 5: Enforce execution bounds**

Default timeout is 600 seconds. Set `PLAYWRIGHT_DASHBOARD_PORT=5176`, `PLAYWRIGHT_API_PORT=8768`, and `PLAYWRIGHT_REUSE_EXISTING=false` by default so EOD acceptance cannot attach to the user's interactive server on 5174. Missing Node/pnpm/browser runtime is an infrastructure blocker. Capture stdout/stderr to files under the EOD output directory and include only a redacted tail in the result message.

- [ ] **Step 6: Run focused tests**

Run: `rtk .venv/bin/pytest tests/test_eod_browser_acceptance.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/eod_browser_acceptance.py tests/test_eod_browser_acceptance.py
git commit -m "feat: run eod browser acceptance safely"
```

### Task 4: Browser Acceptance Manifest And Display Gate

**Files:**
- Modify: `src/stock_research/config.py`
- Modify: `tests/test_config_settings.py`
- Modify: `src/stock_research/eod_browser_acceptance.py`
- Modify: `tests/test_eod_browser_acceptance.py`
- Modify: `src/stock_research/dashboard/display_date_gate.py`
- Modify: `tests/test_dashboard_readiness.py`
- Modify: `tests/test_dashboard_review_queue.py`

- [ ] **Step 1: Write failing rollout-gate tests**

Test dates before and after `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM`. Before the boundary, existing required modules are sufficient. On or after the boundary, missing/failed browser acceptance blocks display, while success or degraded acceptance permits display.

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_config_settings.py tests/test_dashboard_readiness.py tests/test_dashboard_review_queue.py tests/test_eod_browser_acceptance.py -q`

Expected: FAIL because the rollout boundary and manifest module are absent.

- [ ] **Step 3: Add the rollout setting**

Add `browser_acceptance_required_from: str` from `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM`, defaulting to empty. Validate nonempty values with `date.fromisoformat` at the use boundary; invalid values fail closed with a clear configuration error.

- [ ] **Step 4: Persist acceptance manifests**

`write_browser_acceptance_manifest` writes module `dashboard_browser_acceptance`, source `eod_browser_acceptance`, tier `tier1`, and status `success`, `degraded`, or `failed`. Metadata includes report schema/version, application revision, browser project, duration, failure classes, warnings, candidate snapshot, and artifact paths. Browser code never writes the manifest.

- [ ] **Step 5: Extend display readiness**

Replace the constant review-module lookup with `required_review_modules(trade_date)`. Add `dashboard_browser_acceptance` only when `trade_date >= browser_acceptance_required_from`. `_module_ready_for_display` accepts `success` and `degraded` for this module; `failed` or missing blocks the candidate and preserves the prior ready display date.

- [ ] **Step 6: Run focused tests**

Run: `rtk .venv/bin/pytest tests/test_config_settings.py tests/test_dashboard_readiness.py tests/test_dashboard_review_queue.py tests/test_eod_browser_acceptance.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/config.py tests/test_config_settings.py src/stock_research/eod_browser_acceptance.py tests/test_eod_browser_acceptance.py src/stock_research/dashboard/display_date_gate.py tests/test_dashboard_readiness.py tests/test_dashboard_review_queue.py
git commit -m "feat: gate display on browser acceptance"
```

### Task 5: EOD Check And Orchestrator Integration

**Files:**
- Modify: `src/stock_research/eod_auto_repair_checks.py`
- Modify: `tests/test_eod_auto_repair_checks.py`
- Modify: `src/stock_research/eod_auto_repair.py`
- Modify: `tests/test_eod_auto_repair.py`
- Modify: `src/stock_research/eod_auto_repair_models.py`
- Modify: `tests/test_eod_auto_repair_models.py`

- [ ] **Step 1: Write failing check and order tests**

Prove the order `strategy_publish -> dashboard_browser_acceptance -> dashboard_surface_freshness -> ops_health`, browser execution is skipped when upstream blockers remain, failed consistency blocks final status, degraded browser warnings remain publishable, and the browser action is attempted at most once per EOD run.

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_eod_auto_repair_checks.py tests/test_eod_auto_repair.py tests/test_eod_auto_repair_models.py -q`

Expected: FAIL because the new check/action are unregistered.

- [ ] **Step 3: Add the manifest-backed check**

`check_dashboard_browser_acceptance(trade_date)` loads the latest acceptance manifest for the exact date. Success and degraded map to matching `RepairStatus`; missing, failed, malformed, wrong-date, or wrong-schema records are blockers.

- [ ] **Step 4: Register the action safely**

Add `dashboard_browser_acceptance` to the presentation stage and loop order before surface freshness and ops health. The default action calls `run_browser_acceptance`, writes its manifest, and returns a `RepairActionResult` with the browser report paths and parsed result in `validation_result`.

- [ ] **Step 5: Prevent unsafe repeated attempts**

Add a per-run action-failure limit map with `dashboard_browser_acceptance: 1`; its internal runner already performs the single allowed cache-repair retry. A failed consistency result stops before downstream finalization and is not attempted again in a later loop cycle.

- [ ] **Step 6: Record browser evidence in the run summary**

Keep the canonical result in checks/actions rather than adding a duplicate top-level state object. Add convenience `browser_acceptance` output in `RepairRunSummary.to_dict()` by selecting the final browser check and action, so operators can find it without traversing arrays.

- [ ] **Step 7: Run focused tests**

Run: `rtk .venv/bin/pytest tests/test_eod_auto_repair_checks.py tests/test_eod_auto_repair.py tests/test_eod_auto_repair_models.py tests/test_eod_browser_acceptance.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/stock_research/eod_auto_repair_checks.py tests/test_eod_auto_repair_checks.py src/stock_research/eod_auto_repair.py tests/test_eod_auto_repair.py src/stock_research/eod_auto_repair_models.py tests/test_eod_auto_repair_models.py
git commit -m "feat: integrate browser acceptance into eod repair"
```

### Task 6: HTML Report, Cron Output, And Retention

**Files:**
- Create: `src/stock_research/eod_auto_repair_report.py`
- Create: `tests/test_eod_auto_repair_report.py`
- Modify: `src/stock_research/eod_auto_repair.py`
- Modify: `tests/test_eod_auto_repair.py`
- Modify: `scripts/run_eod_auto_repair_cron.sh`
- Modify: `tests/test_eod_auto_repair_scripts.py`

- [ ] **Step 1: Write failing HTML and shell tests**

The report must show EOD run ID, trade date, data/check stages, three strategy publication identities, browser status, repair action, rerun result, final decision, and evidence links. HTML must escape untrusted error text. The cron summary must print `run_report.html` and browser evidence paths.

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_eod_auto_repair_report.py tests/test_eod_auto_repair.py tests/test_eod_auto_repair_scripts.py -q`

Expected: FAIL because the HTML writer and output lines are absent.

- [ ] **Step 3: Implement deterministic HTML**

Use only Python standard-library `html.escape` and JSON serialization. The report status banner is `official`, `blocked`, or `degraded`. Do not inline trace archives or screenshots; link to relative artifact paths.

- [ ] **Step 4: Write all three report formats together**

`_write_summary_files` produces `run_summary.json`, `run_report.md`, and `run_report.html` from the same `RepairRunSummary`. Report-writing failure must not delete JSON or Markdown already written and must be surfaced as an infrastructure issue.

- [ ] **Step 5: Update the cron wrapper**

Pass `PLAYWRIGHT_EOD_OUTPUT_DIR=$OUTPUT_DIR/browser`; preserve the Python exit code; print browser status, HTML report path, and trace path when present. Do not run a second independent Playwright command in shell.

- [ ] **Step 6: Add retention cleanup**

Implement a Python helper that removes successful daily browser/report directories older than 90 days, skips any directory whose summary is failed/blocked, and never removes the trusted initial baseline. Invoke it only after a successful report write.

- [ ] **Step 7: Run focused tests**

Run: `rtk .venv/bin/pytest tests/test_eod_auto_repair_report.py tests/test_eod_auto_repair.py tests/test_eod_auto_repair_scripts.py -q && rtk bash -n scripts/run_eod_auto_repair_cron.sh`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/stock_research/eod_auto_repair_report.py tests/test_eod_auto_repair_report.py src/stock_research/eod_auto_repair.py tests/test_eod_auto_repair.py scripts/run_eod_auto_repair_cron.sh tests/test_eod_auto_repair_scripts.py
git commit -m "feat: report eod browser acceptance"
```

### Task 7: Regression, Bootstrap, And Controlled Rollout

**Files:**
- Modify: `docs/ops/platform-hardening-runbook.md`
- Modify: `docs/ops/playwright-platform-validation.md`
- Create: `docs/reviews/eod-browser-acceptance-rollout-2026-07-20.md`

- [ ] **Step 1: Run the complete focused regression**

```bash
rtk .venv/bin/pytest \
  tests/test_eod_browser_acceptance.py \
  tests/test_eod_auto_repair.py \
  tests/test_eod_auto_repair_checks.py \
  tests/test_eod_auto_repair_models.py \
  tests/test_eod_auto_repair_report.py \
  tests/test_eod_auto_repair_scripts.py \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_review_queue.py -q
cd dashboard
rtk pnpm test
rtk pnpm build
rtk pnpm test:e2e:p0
```

Expected: all commands exit 0.

- [ ] **Step 2: Run a check-only historical simulation**

Use a copied output directory and injected fixtures to prove a 175.29% rendered LHB value produces `return_unit`, no cache repair, a failed browser manifest, prior display-date preservation, and EOD exit code 2.

- [ ] **Step 3: Run a successful controlled candidate**

Choose an already repaired trade date. Start with `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM` set to that date, run the EOD browser profile, inspect screenshots/traces/report manually, and confirm a success/degraded acceptance manifest allows the display gate to select the date.

- [ ] **Step 4: Test the repairable path**

Inject one stale-cache response, verify cache clear executes once, the same Playwright suite reruns, final acceptance succeeds, and both attempts appear in the report.

- [ ] **Step 5: Enable the rollout boundary**

Set `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM` to the next intended trading date in the EOD and dashboard service environment. Confirm both processes use the same value before the next scheduled EOD run.

- [ ] **Step 6: Observe the first live run**

Verify total duration remains within ten minutes, official display advances only after browser acceptance, prior display remains available during candidate validation, reports are delivered, and no process remains after cron exit.

- [ ] **Step 7: Document evidence and rollback**

Record exact commands, run ID, trade date, publish IDs, duration, status, repair behavior, and artifact paths. Rollback disables the rollout boundary and browser action while preserving the last successful display date and all evidence; it must never write an unvalidated candidate as official.

- [ ] **Step 8: Commit rollout evidence**

```bash
git add docs/ops/platform-hardening-runbook.md docs/ops/playwright-platform-validation.md docs/reviews/eod-browser-acceptance-rollout-2026-07-20.md
git commit -m "docs: verify eod browser acceptance rollout"
```
