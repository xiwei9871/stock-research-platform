# Platform Validation Remediation — 2026-07-23

## Scope

This remediation starts from report commit `7bec249` and implements the approved Playwright-first layered policy:

- Chromium is the formal blocking browser.
- Firefox/WebKit compatibility is preserved as a separate advisory result.
- Mock, Real, Audit, Sandbox, and eligible EOD remain independent fail-closed layers.
- Human-facing visual contracts exclude formal contract IDs, publication IDs, and artifact versions.

Validation timestamp: `2026-07-23 17:17:05 +0800`.

## Changes Completed

1. Added the `compat` Playwright profile and moved Firefox/WebKit out of blocking Audit.
2. Reduced Audit to Chromium accessibility and approved visual tests; it no longer reruns Mock and Real.
3. Replaced the obsolete Review Queue formal-contract snapshot with the reader-facing strategy-state snapshot and refreshed the approved Home strategy baseline.
4. Provisioned the local `stock_research_e2e_test` PostgreSQL database/service and applied the repository schema without storing credentials in the repository.
5. Made Sandbox loopback readiness bypass environment proxies.
6. Fixed the real-browser password reset input crash caused by reading `event.currentTarget` inside a deferred state updater.
7. Stabilized the Sandbox operator-decision locator across edited text and waited for outstanding panel requests before reload.
8. Made Sandbox process cleanup tolerate completed processes and macOS process-group permission behavior without converting a passing suite into exit 1.
9. Fixed a Dashboard unit-test timing race by awaiting the asynchronously rendered market-monitor tab.
10. Documented the difference between intraday/deferred candidate state and an eligible post-close EOD failure.

## Required Gate Results

| Layer | Result | Evidence |
| --- | --- | --- |
| Dashboard unit | PASS | `556 passed` |
| Dashboard build | PASS | TypeScript and Vite build exit 0 |
| Mock P0 | PASS | `61 passed` |
| Real | PASS | `42 passed` |
| Chromium Audit | PASS | `16 passed` |
| Sandbox focused backend | PASS | `62 passed` |
| Sandbox browser lifecycle | PASS | `2 passed`, runner exit 0, ports released |
| EOD backend contracts | PASS | `273 passed` |
| EOD browser acceptance for 2026-07-23 | DEFERRED | No scheduled `2026-07-23` Auto EOD Repair output existed at 17:17; the earlier daytime candidate remained correctly blocked on incomplete Tier-1 data |

The required non-EOD release regression layers are green. The final daily publication decision for `2026-07-23` must still come from the scheduled Auto EOD Repair run; this remediation does not promote an incomplete candidate.

## Advisory Compatibility Result

`pnpm test:e2e:compat` completed with `101 passed / 7 failed`. WebKit critical login coverage passed. All seven failures are Firefox-only and non-blocking under the approved browser policy:

1. Three Back/Forward history restoration failures: theme-company handoff, technology-bottleneck handoff, and global-search stock handoff.
2. Three runtime-evidence representation differences: Firefox reports `NS_ERROR_FAILURE` instead of Chromium's `net::ERR_FAILED`, and does not emit Chromium's exact console text for synthetic HTTP 503/599 responses.
3. One direct stock refresh cancellation difference: Firefox reports duplicate `NS_BINDING_ABORTED` profile requests.

These remain visible compatibility issues; they are not hidden or relabeled as passing. They do not block strategy calculation or publication on the operational Chromium browser.

## Final Acceptance State

- Chromium release validation: ready.
- Sandbox isolation and write journeys: ready.
- Firefox/WebKit compatibility: advisory issues remain, with seven Firefox failures and no WebKit critical failure.
- `2026-07-23` EOD publication: pending the scheduled Auto EOD Repair result; keep the prior completed display date until that gate passes.
