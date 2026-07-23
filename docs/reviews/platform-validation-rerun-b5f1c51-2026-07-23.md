# Platform Validation Rerun — b5f1c51 — 2026-07-23

Status: **NOT ACCEPTED / BLOCKED**

Frozen revision: `b5f1c5194ea8975ce1b01f76f15eb8c5960b8530`

The worktree was clean before and after the matrix. No product code or test code was changed during this rerun. The final Audit run used five workers; focused reruns used one worker to distinguish deterministic failures from load-sensitive failures.

## Matrix result

| Layer | Result | Classification |
| --- | ---: | --- |
| Mock P0 | 61 passed / 61 | Passed |
| Real read-only | 42 passed / 42 | Passed |
| Audit multi-browser | 316 passed / 328; 12 unexpected | Failed |
| Sandbox | runner exit 2 | Environment blocked: `stock_research_e2e_test` service is not defined |
| EOD 2026-07-23 | 47 passed / 49; 2 blocker failures | Failed: current candidate is incomplete |

## Authoritative evidence

- Mock JSON: `dashboard/test-results/mock/results-b5f1c51-20260723.json`
  - SHA-256: `3d69112ae4e5af96eb2677c9c64a873b1fc2c44bb4740d93d0be241281f0f6e3`
- Real JSON: `dashboard/test-results/real/results-b5f1c51-20260723.json`
  - SHA-256: `b0e4a1a02fbb59c1b01f9b261e117d4d2b3918d20c30574fad7640e182739efc`
- Audit JSON: `/tmp/stock-research-validation-b5f1c51-20260723/audit-full.json`
  - SHA-256: `1b6a61097c0fa4b923aeffed51045120664f65f14d73ed478f344f63eb0a6323`
  - Audit screenshots, traces, and videos remain under `dashboard/test-results/audit/`.
- EOD JSON: `dashboard/test-results/eod/results-b5f1c51-20260723.json`
  - SHA-256: `c0bca65ee2f68dd302d778ebd21202fc8bf5ea3202bbfd206e478f302fc52428`
- EOD acceptance manifest: `/tmp/stock-research-eod-matrix-b5f1c51-20260723/eod-browser-acceptance.json`
  - SHA-256: `2d8ef3932b90d3f7f0949fed2a48a11c093feeecc67f26e645e009e4203de99b`

## New issue ledger

### PV-RERUN-01 — Firefox Back navigation does not restore the previous workspace

Severity: **P0 functional / release blocker for Firefox**

Stable one-worker reproduction:

- Theme Research company → stock → Back remains on `/tech-bottleneck/stock/430476.BJ` instead of returning to the company list.
- Technology-bottleneck review universe → stock → Back remains on `/tech-bottleneck/stock/300760` instead of returning to the review universe.
- Global search → stock → Back remains on `/stock/300203.SZ` instead of returning home.

Chromium Mock and Real journeys pass, so this is a Firefox-specific browser-history contract failure rather than a general routing failure.

### PV-RERUN-02 — Firefox runtime evidence contracts assume Chromium network text

Severity: **P1 test/runtime compatibility**

Stable one-worker reproduction:

- An aborted request is `NS_ERROR_FAILURE` in Firefox, while the contract expects `net::ERR_FAILED`.
- Firefox does not emit the Chromium console message expected for fulfilled HTTP 503 and 599 responses.

The HTTP failures are still captured in `failedRequests`; the exact-text assertions are browser-specific and need normalization.

### PV-RERUN-03 — Firefox direct stock refresh records duplicate `NS_BINDING_ABORTED`

Severity: **P1 runtime evidence classification**

The stock page renders, but the Audit fixture treats two canceled profile requests as fatal. The cancellation classifier currently covers Chromium navigation cancellation but not Firefox `NS_BINDING_ABORTED` for this lifecycle.

### PV-RERUN-04 — Visual baselines still describe the removed technical publication UI

Severity: **P1 test maintenance**

- The home strategy region baseline expects the former 506-pixel technical layout; the approved human-readable layout is 294 pixels high.
- The review-queue visual test still searches for `aria-label="正式发布合同"`, which was intentionally removed from the human-facing page.

These are stale tests/baselines, not evidence that the approved UI regressed.

### PV-RERUN-05 — Audit full-load run is not deterministic

Severity: **P1 validation infrastructure**

The final five-worker Audit run additionally failed three Chromium journeys:

- desktop Theme Research company return;
- mobile real global search;
- mobile Market Monitor route census.

The standalone Real profile passed 42/42, and the focused one-worker Chromium rerun of the global-search and route-census failures passed 6/6. The first full Audit run failed a different set of six Chromium Real observations. These failures are load-sensitive and should not be silently retried away; Audit needs isolation, lower concurrency, or explicit API readiness coordination.

### PV-RERUN-06 — Sandbox service is unavailable

Severity: **Environment blocker**

The official runner exited 2 with:

`definition of service "stock_research_e2e_test" not found`

The safety guard worked: it did not fall back to the production database and did not execute write journeys.

### PV-RERUN-07 — 2026-07-23 EOD candidate is incomplete

Severity: **Operational release blocker**

The full EOD profile passed 47 contract/runtime tests and failed both consistency gates because the requested candidate date was `2026-07-23` while Review Queue remained at `2026-07-22`:

`eod_candidate_review_queue_trade_date_mismatch:2026-07-22:2026-07-23`

Platform readiness independently reported:

- `status=BLOCKED`;
- `candidate_trade_date=2026-07-23`;
- `display_trade_date=2026-07-22`;
- missing Tier-1 module `market_monitor`.

The fail-closed behavior is correct: the platform continues to display the last ready date instead of promoting the incomplete candidate.

## Accepted scope

The following current-head behavior is accepted by fresh evidence:

- Mock P0 navigation, authentication, failure isolation, mobile overflow, strategy publication, and strategy-specific review deep links.
- Real Chromium read-only APIs, write guards, official strategy cards, Review Queue, current stock dates, historical review isolation, dynamic stock/theme handoffs, and route census under the standalone Real profile.
- The latest approved LHB percentage contract excludes the previous `175.29%` regression.
- EOD runtime deep links remain safe, and the incomplete 2026-07-23 candidate is blocked rather than published.

## Final acceptance conclusion

The platform is **not ready for a trusted full-matrix baseline or browser-acceptance rollout** at revision `b5f1c51`.

The core Chromium product path is healthy, but acceptance remains blocked until:

1. Firefox Back/Forward restoration is fixed and rerun.
2. Firefox runtime evidence is normalized without weakening fatal-error detection.
3. Visual tests are aligned with the approved human-readable strategy UI.
4. Audit load sensitivity is removed or the matrix is isolated deterministically.
5. The isolated Sandbox database service is configured and Sandbox passes.
6. A complete EOD candidate, including `market_monitor`, passes all three required EOD gates.

No rollout switch or promotion boundary was enabled by this rerun.
