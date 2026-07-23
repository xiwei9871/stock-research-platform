# Playwright Validation Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate blocking Chromium validation from advisory browser compatibility, refresh reader-facing visual contracts, verify isolated Sandbox execution, and preserve strict EOD publication gates.

**Architecture:** Keep each validation layer independently runnable and evidence-producing. Add a dedicated compatibility profile instead of weakening assertions, reduce Audit to Chromium accessibility/visual coverage, and keep database and EOD safety decisions in their existing fail-closed boundaries.

**Tech Stack:** TypeScript, Playwright, Vitest, React, Python, pytest, PostgreSQL, pnpm.

---

### Task 1: Split blocking Audit from advisory compatibility

**Files:**
- Modify: `dashboard/tests/playwright-projects.test.ts`
- Modify: `dashboard/playwright.projects.ts`
- Modify: `dashboard/package.json`
- Modify: `docs/ops/playwright-platform-validation.md`

- [ ] **Step 1: Write failing profile tests**

Add expectations that `compat` is a valid API-backed, service-worker-blocking profile; `audit` contains only Chromium desktop/mobile; and `compat` contains Firefox desktop plus WebKit critical.

- [ ] **Step 2: Verify the tests fail for the missing profile**

Run: `cd dashboard && rtk pnpm test -- tests/playwright-projects.test.ts`

Expected: FAIL because `compat` is absent and Firefox/WebKit still belong to `audit`.

- [ ] **Step 3: Implement the minimal profile split**

Add `compat` to `PLAYWRIGHT_PROFILES`, move the Firefox/WebKit projects into its branch, keep Audit Chromium-only, and classify Compat as an API-backed read-only profile.

- [ ] **Step 4: Split the package commands and runbook**

Set `test:e2e:audit` to `tests/e2e/audit tests/e2e/visual`, add `test:e2e:compat` for the cross-browser census, and document required versus advisory gates.

- [ ] **Step 5: Verify the focused tests pass**

Run: `cd dashboard && rtk pnpm test -- tests/playwright-projects.test.ts`

Expected: PASS.

### Task 2: Refresh approved reader-facing visual contracts

**Files:**
- Modify: `dashboard/tests/e2e/visual/key-regions.spec.ts`
- Modify: `dashboard/tests/e2e/visual/key-regions.spec.ts-snapshots/home-strategy-performance-chromium-desktop-darwin.png`
- Create: `dashboard/tests/e2e/visual/key-regions.spec.ts-snapshots/review-queue-strategy-state-chromium-desktop-darwin.png`
- Delete: `dashboard/tests/e2e/visual/key-regions.spec.ts-snapshots/review-queue-formal-contract-chromium-desktop-darwin.png`

- [ ] **Step 1: Replace the obsolete visual locator**

Assert the selected review evidence region contains the reader-facing `策略数据状态` grid and snapshot it as `review-queue-strategy-state.png`.

- [ ] **Step 2: Verify the visual test fails before baseline approval**

Run: `cd dashboard && PLAYWRIGHT_PROFILE=audit pnpm exec playwright test tests/e2e/visual/key-regions.spec.ts --project=chromium-desktop`

Expected: FAIL with missing or mismatched approved snapshots.

- [ ] **Step 3: Generate and inspect the intended baselines**

Run the same command with `--update-snapshots`, then inspect both changed PNGs to ensure they contain only reader-facing content and no formal contract, publication number, or artifact version.

- [ ] **Step 4: Verify visual tests pass without update mode**

Run the original visual command again.

Expected: PASS.

### Task 3: Verify isolated Sandbox infrastructure

**Files:**
- Modify only if tests expose a repository defect: `scripts/run_playwright_sandbox.py`, `src/stock_research/testing/playwright_sandbox.py`, and their focused tests
- External local configuration, only if safely possible: `~/.pg_service.conf` and isolated database `stock_research_e2e_test`

- [ ] **Step 1: Run focused Sandbox safety contracts**

Run: `rtk .venv/bin/pytest tests/test_playwright_sandbox.py tests/test_run_playwright_sandbox.py tests/test_config_settings.py -q`

Expected: PASS, including rejection of non-`_test` databases.

- [ ] **Step 2: Inspect service names without printing credentials**

List only PostgreSQL service section names and verify whether `stock_research_e2e_test` resolves.

- [ ] **Step 3: Provision only an isolated local service/database when possible**

Reuse non-secret connection topology from the existing local service, create `stock_research_e2e_test`, and refuse any action that would point Sandbox to the production database.

- [ ] **Step 4: Execute the Sandbox runner**

Run: `rtk .venv/bin/python scripts/run_playwright_sandbox.py`

Expected: PASS, or exit 2 with a precise remaining environment blocker and no production fallback.

### Task 4: Preserve EOD fail-closed semantics and document eligibility

**Files:**
- Modify: `docs/ops/playwright-platform-validation.md`
- Modify code/tests only if inspection finds the runner conflates intraday deferral with an eligible EOD failure

- [ ] **Step 1: Inspect existing cutoff/readiness behavior and tests**

Read the EOD runner, readiness policy, and focused tests for current-date incomplete candidates.

- [ ] **Step 2: Add a failing test only if a semantic gap exists**

The desired behavior is: before EOD eligibility, report deferred/blocked and keep the previous completed display date; after eligibility, missing Tier-1 data remains a blocking failure.

- [ ] **Step 3: Implement only the minimal semantic correction**

Do not convert missing `market_monitor` or other Tier-1 data into success.

- [ ] **Step 4: Run focused EOD tests**

Run the relevant pytest and Playwright EOD suites identified during inspection.

Expected: PASS, or a precise current-data blocker after cutoff.

### Task 5: Run the final matrix and update acceptance evidence

**Files:**
- Modify: `docs/reviews/platform-validation-rerun-b5f1c51-2026-07-23.md` or create a new revision-specific acceptance report

- [ ] **Step 1: Run unit tests and build**

Run Dashboard profile tests, Dashboard unit tests, Dashboard build, and focused backend Sandbox/EOD contracts.

- [ ] **Step 2: Run required Playwright layers independently**

Run Mock, Real, Audit, Sandbox, and EOD with distinct evidence outputs. Run Compat separately and label its result advisory.

- [ ] **Step 3: Produce a new issue ledger**

Separate product failures, test-infrastructure failures, environment blockers, and advisory browser compatibility issues.

- [ ] **Step 4: Record the final acceptance conclusion**

State exactly which required gates passed, which environmental blockers remain, and whether strategy calculation/publication is eligible.

- [ ] **Step 5: Commit the verified remediation**

Stage only the scoped files and commit with a message describing the Playwright gate split and validation remediation.
