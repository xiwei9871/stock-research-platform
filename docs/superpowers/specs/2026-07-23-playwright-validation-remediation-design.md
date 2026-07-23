# Playwright Validation Remediation Design

## Context

The frozen `b5f1c51` validation rerun proved the core Chromium journeys, but the combined Audit command mixed release-blocking Chromium coverage with advisory Firefox/WebKit compatibility checks. It also reran Mock and Real suites inside Audit, multiplied load, and retained visual assertions for technical publication metadata that was intentionally removed from the human-facing UI. Sandbox correctly refused to run without an isolated `_test` PostgreSQL service. The daytime EOD run correctly remained blocked while the current trading date was incomplete.

## Decisions

1. Chromium desktop is the formally supported browser and remains release-blocking. Chromium mobile remains blocking where explicitly covered.
2. Firefox and WebKit form a separate `compat` profile. Compatibility failures remain visible and actionable, but do not block normal strategy calculation or publication because these browsers are not used operationally.
3. `audit` covers Chromium accessibility and visual contracts only. Mock and Real remain separate required layers and are not rerun inside Audit.
4. Visual assertions describe reader-facing strategy state. They must not restore formal-contract, publication-number, or artifact-version fields to the UI.
5. Sandbox remains fail-closed and may connect only to a database whose resolved name ends in `_test`. Missing local configuration is repaired only by creating an isolated service/database; production fallback is forbidden.
6. EOD remains fail-closed after the daily close workflow is eligible to finish. An intraday incomplete candidate is classified as deferred/blocked operational state, not as permission to publish incomplete data and not as a browser regression.

## Validation Matrix

| Layer | Browser | Role | Blocking |
| --- | --- | --- | --- |
| Mock P0 | Chromium desktop + tagged mobile | Deterministic navigation, state, publication, auth | Yes |
| Real | Chromium desktop | Authoritative read models and publication identity | Yes |
| Audit | Chromium desktop + mobile excluding visual | Accessibility and approved visual contracts | Yes |
| Sandbox | Chromium desktop | Isolated write journeys | Yes when environment is provisioned; otherwise explicit environment blocker |
| EOD | Chromium desktop | Latest completed operational acceptance | Yes after EOD eligibility |
| Compat | Firefox desktop + WebKit critical subset | Browser compatibility census | No; advisory |

## Acceptance Criteria

- The profile unit tests prove `audit` is Chromium-only and `compat` owns Firefox/WebKit.
- `pnpm test:e2e:audit` no longer includes P0 or Real directories.
- A separate `pnpm test:e2e:compat` command exists and is documented as advisory.
- Approved reader-facing visual regions have current, inspected baselines.
- The required Mock, Real, Audit, Sandbox, and eligible EOD layers retain strict failure behavior.
- Sandbox cannot connect to a non-`_test` database.
- Documentation distinguishes an intraday EOD deferral from a completed EOD gate failure.
