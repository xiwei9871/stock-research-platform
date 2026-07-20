# Cross-Browser Runtime Evidence Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make runtime-evidence contract tests assert deterministic browser-independent signals while keeping browser-generated console text as supplemental captured evidence.

**Architecture:** Preserve `failedRequests`, `pageErrors`, `consoleErrors`, and `unhandledApiRoutes` capture. For intentional abort/5xx/599 contract cases, narrowly allowlist the known browser console string and assert the stable failed-request or unhandled-route ledger exactly; Firefox may emit a different string or no string without hiding an actual API failure.

**Tech Stack:** Playwright fixtures, TypeScript, Chromium, Firefox.

---

## File Structure

- `dashboard/tests/e2e/p0/runtime-contract.spec.ts`: removes Chromium-only console requirements from three intentional failure contracts.
- `dashboard/tests/e2e/assertions/runtime.ts`: remains the production assertion/formatter unless a focused helper is needed for exact stable evidence.
- `dashboard/tests/e2e/fixtures/test.ts`: existing runtime policy and teardown remain fail-closed.

### Task 1: Add Cross-Browser Expectations To The Contract Tests

**Files:**
- Modify: `dashboard/tests/e2e/p0/runtime-contract.spec.ts`

- [ ] **Step 1: Inject `runtimePolicy` into the three failing contracts**

Update these tests:

- `failed critical API request fails with exact evidence`
- `fulfilled critical API 5xx fails with exact evidence`
- `unhandled mock API route fails closed with exact evidence`

- [ ] **Step 2: Narrowly allowlist only the intentional console message**

Before each request, set the exact optional Chromium message:

```typescript
runtimePolicy.allowlist.consoleErrors = [
  'Failed to load resource: net::ERR_FAILED'
];
```

Use the corresponding exact 503 and 599 strings in the other two tests. Do not use regexes, wildcard patterns, or a global allowlist.

- [ ] **Step 3: Assert stable evidence exactly**

Keep the exact `failedRequests` and `unhandledApiRoutes` assertions. Call:

```typescript
expect(
  captureErrorMessage(() =>
    expectNoFatalRuntimeErrors(runtimeEvidence, runtimePolicy.allowlist)
  )
).toBe(
  'Unexpected fatal runtime evidence:\n' +
    'failedRequests:\n' +
    `- GET ${requestUrl} — HTTP 503`
);
```

For the abort case, read the single captured entry, assert method and URL exactly, and constrain `failure` to the two observed Playwright engine values:

```typescript
const [failedRequest] = runtimeEvidence.failedRequests;
expect(failedRequest).toMatchObject({ method: 'GET', url: requestUrl });
expect(['net::ERR_FAILED', 'NS_ERROR_FAILURE']).toContain(failedRequest.failure);
expect(
  captureErrorMessage(() =>
    expectNoFatalRuntimeErrors(runtimeEvidence, runtimePolicy.allowlist)
  )
).toBe(
  'Unexpected fatal runtime evidence:\n' +
    'failedRequests:\n' +
    `- GET ${requestUrl} — ${failedRequest.failure}`
);
```

Keep the raw engine failure token for diagnosis; do not globally normalize unrelated network failures and never allowlist failed requests.

- [ ] **Step 4: Verify RED on Firefox and unchanged Chromium behavior**

Run the pre-change reproduction first, then run after the test edit:

```bash
cd dashboard
PLAYWRIGHT_PROFILE=audit pnpm exec playwright test tests/e2e/p0/runtime-contract.spec.ts \
  --grep "failed critical API|fulfilled critical API 5xx|unhandled mock API" \
  --project=firefox-desktop
```

Expected before change: 3 failures. Expected after change: PASS as expected-failure contracts.

### Task 2: Protect Fail-Closed Runtime Behavior

**Files:**
- Modify: `dashboard/tests/e2e/p0/runtime-contract.spec.ts`
- No fixture change expected.

- [ ] **Step 1: Add a control proving unexpected console errors still fail**

Trigger `console.error('runtime-contract-unexpected-console')` without an allowlist and assert the existing exact failure message remains unchanged.

- [ ] **Step 2: Add a control proving unrelated 5xx remains fatal**

Allowlist the intentional 503 console string, then issue a second `/api/runtime-contract-other-error` request. Assert the second `failedRequests` entry is still reported and fails teardown.

- [ ] **Step 3: Run all runtime contracts on Chromium and Firefox**

```bash
cd dashboard
PLAYWRIGHT_PROFILE=audit pnpm exec playwright test tests/e2e/p0/runtime-contract.spec.ts \
  --project=chromium-desktop --project=firefox-desktop
```

Expected: PASS with no skipped or flaky tests.

- [ ] **Step 4: Commit the cross-browser contract**

```bash
git add dashboard/tests/e2e/p0/runtime-contract.spec.ts
git commit -m "test: normalize cross-browser runtime evidence"
```

### Task 3: Re-run The Audit Matrix

**Files:**
- No further changes expected.

- [ ] **Step 1: Run the P0 Mock gate**

```bash
cd dashboard && rtk pnpm test:e2e:p0
```

Expected: PASS.

- [ ] **Step 2: Run the Firefox P0 audit subset**

```bash
cd dashboard
PLAYWRIGHT_PROFILE=audit pnpm exec playwright test tests/e2e/p0 --project=firefox-desktop
```

Expected: PASS.

- [ ] **Step 3: Run the full Audit profile under a new audit ID**

Preserve the original 72-failure evidence. The rerun must show no runtime-contract root before a trusted baseline is considered.
