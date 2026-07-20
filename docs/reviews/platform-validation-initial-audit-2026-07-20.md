# Initial Platform Validation Audit — 2026-07-20

## Decision

Audit `pv-initial-20260720-372f4a5` is frozen as `baseline_candidate`, not `trusted_baseline`. The stop rule is active because two independent P0 product roots remain open. Two additional P0 roots are in the Playwright consistency/runtime infrastructure, one P1 security root is in report evidence sanitization, and the isolated sandbox PostgreSQL service is unavailable.

No product code, Dashboard code, tests, or inventory configuration changed after the input freeze. `config/platform_validation_routes.json` required no verified correction.

## Frozen Inputs

| Input | Frozen value |
| --- | --- |
| Revision | `372f4a59ac7d07955e3b9c2517bbe77b49ba37ca` |
| Inventory SHA-256 | `620a96b51187ff76e72378b01cdbc4af4d146f7878b5fa533bd4b23bcbed537f` |
| Audit label date | `2026-07-20` |
| Execution start | `2026-07-21T07:01:18+08:00` |
| Timezone | `Asia/Shanghai` |
| Python / Node / pnpm | `3.14.4` / `v24.14.1` / `10.33.0` |
| Playwright | `1.60.0` |
| Browsers | Chromium `148.0.7778.96`; Firefox `150.0.2`; WebKit `26.4` |
| PostgreSQL | service/database `stock_research` / `stock_research` |
| Real/Audit URLs | Dashboard `http://127.0.0.1:5374`; API `http://127.0.0.1:8966` |
| Sandbox URLs | Dashboard `http://127.0.0.1:5274`; API `http://127.0.0.1:8866` |

The complete machine-readable freeze is in `outputs/research/platform_validation/pv-initial-20260720-372f4a5/frozen-inputs.json`.

## Command Results

| Layer | Result | Evidence summary |
| --- | --- | --- |
| Backend focused contracts | exit 0 | `267 passed`, 2 warnings |
| Dashboard full Vitest | exit 0 | 41 files, `526 passed` |
| Dashboard production build | exit 0 | TypeScript and Vite build passed |
| P0 Mock | exit 0 | `59 passed`, 0 failed/skipped/flaky |
| Real read-only | exit 1 | `19 passed`, `22 failed` |
| Sandbox runner | exit 2 | `_test` service definition missing; no production fallback |
| Audit matrix | exit 1 | `247 passed`, `72 failed`, 0 skipped/flaky |
| Report generator, raw paths | exit 1 | Expected fail-closed rejection: attachment paths escaped the copied JSON directory |
| Report generator, report-ready paths | exit 0 | Four artifacts generated with path checks; content safety scan followed |
| Report safety sentinel scan | exit 0 with matches | Synthetic bare-secret literals found; P1 reporting-security root opened |

The first report attempt is retained because it demonstrates the evidence path security guard. Original JSON stayed under `inputs/raw/`; report-ready copies and copied attachment trees were placed under `inputs/report-ready/` before the successful report build.

## Coverage

The inventory contains 15 reachable items and one intentionally hidden/unreachable Data Explorer item.

- Overall: 15 `partial`, 1 `not_applicable`.
- Unit: all 15 reachable items `covered` by the full Dashboard Vitest command.
- API: `review_queue` and `strategy_lab` `covered`; 13 other reachable items `partial` because this audit intentionally ran the focused backend set rather than every Dashboard API module.
- Playwright: 14 reachable items `partial`; `user_management` is missing its sandbox result; hidden Data Explorer is not applicable.

This coverage state independently prevents trusted-baseline promotion.

## Generated Symptom Ledger

The deterministic generator emitted 46 open symptom groups: 36 P0 and 10 P1. Browser/profile totals were:

- Mock: 59 expected, 0 unexpected.
- Real: 19 expected, 22 unexpected.
- Audit: 247 expected, 72 unexpected.
- Chromium desktop: 165 expected, 44 unexpected.
- Chromium mobile: 83 expected, 22 unexpected.
- Firefox desktop: 76 expected, 28 unexpected.
- WebKit critical: 1 expected, 0 unexpected.

These counts are evidence groups, not independent root causes. The human classification below merges repeated route, viewport, and browser symptoms.

## Root-Cause Classification

### PV-ROOT-P0-AUTH-DISABLED-ME — P0 product

- Owner: Dashboard auth backend.
- Expected: when `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=false`, both ordinary reads and `/api/auth/me` permit the local shell.
- Actual: `/api/platform/summary=200`, but `/api/auth/me=401`; `DashboardAuthRoot` therefore renders the login gate. This one root explains most Real route-census and critical-journey failures across Chromium desktop/mobile and Firefox.
- Repro: focused `auth-disabled Real profile can enter the authenticated application shell` test.
- Plan: [Auth-disabled Dashboard shell contract](../superpowers/plans/2026-07-21-auth-disabled-dashboard-shell-contract.md).

### PV-ROOT-P0-STRATEGY-PUBLICATION-CATALOG — P0 product

- Owner: Strategy publication read model.
- Expected: every runnable official strategy exposes one catalog identity matching review queue fields: performance date, total return, contract ID, publish ID, and artifact version.
- Actual: the first fail-closed error is `lhb_shortline.latest_metrics.performance_as_of_date` missing. The static `/api/strategies/catalog` rows do not project the validated publication identity used by the review queue.
- Repro: focused `authoritative publication snapshot is complete before any product journey` test.
- Plan: [Official strategy publication catalog](../superpowers/plans/2026-07-21-official-strategy-publication-catalog.md).

### PV-ROOT-P0-FIREFOX-HISTORY-SYNCHRONIZATION — P0 test-infrastructure candidate

- Owner: Dashboard navigation and Playwright consistency assertions.
- Expected: Back returns to home/theme-company/tech-review and the assertion observes the completed same-document traversal.
- Actual: three Firefox-only tests sample the stock URL immediately after `page.goBack()`. Chromium passes; `expectRouteContext` has no retry window. A product routing failure is not yet proven.
- Plan: [Firefox history consistency waits](../superpowers/plans/2026-07-21-firefox-history-consistency-waits.md).

### PV-ROOT-P0-FIREFOX-RUNTIME-EVIDENCE — P0 test infrastructure

- Owner: Playwright runtime evidence.
- Expected: abort/5xx/599 contracts assert stable failed-request and unhandled-route evidence across engines.
- Actual: three tests require Chromium-specific `Failed to load resource` console text. Firefox still records the deterministic failure ledger but emits different or no console text.
- Plan: [Cross-browser runtime evidence contract](../superpowers/plans/2026-07-21-cross-browser-runtime-evidence-contract.md).

### PV-ROOT-P1-AUDIT-EVIDENCE-BARE-SECRET — P1 test-infrastructure security

- Owner: Platform validation reporting.
- Expected: archived evidence contains no secret-shaped literal values, including source excerpts.
- Actual: the post-generation scan found synthetic `raw-url-secret`, `raw-path-secret`, and `raw-query-secret` literals in archived `error-context.md` code frames. These are test sentinels, not real credentials, but they prove the final sanitizer misses isolated quoted literals.
- Disposition: the audit remains untrusted; no report evidence may be published externally.
- Plan: [Audit evidence bare-secret redaction](../superpowers/plans/2026-07-21-audit-evidence-bare-secret-redaction.md).

### PV-ROOT-ENV-SANDBOX-SERVICE — environment blocker

- Owner: Local PostgreSQL service configuration.
- Expected: `stock_research_e2e_test` resolves to a database ending `_test`.
- Actual: the service definition is absent; runner exits 2 before seed/server/test lifecycle. The runner did not fall back to `stock_research`, so production data remained protected.
- Disposition: configure the isolated service before rerunning; do not treat this as a product defect.

The machine-readable deduplicated ledger is `outputs/research/platform_validation/pv-initial-20260720-372f4a5/root-cause-ledger.json`.

## Stop Decision And Next Audit

Do not repair these roots inside this frozen audit and do not mark a trusted baseline. Execute the five focused plans independently with their specified tests and reviews. Configure the isolated `_test` service. Then create a new audit ID, rerun every layer, preserve this original evidence, and promote only if no P0/P1 product or validation-security issue remains and required coverage is traceable.

## Generated Output Locations

- Audit root: `outputs/research/platform_validation/pv-initial-20260720-372f4a5/`
- Commands and raw logs: `inputs/raw/` plus `commands-manifest.json`
- Report-ready JSON/evidence: `inputs/report-ready/`
- Coverage declaration: `inputs/coverage-results.json`
- Human root ledger: `root-cause-ledger.json`
- Report: `report/route_inventory.json`, `report/coverage_matrix.json`, `report/issue_ledger.json`, `report/audit_report.html`

Generated outputs total about 103 MiB and are ignored by Git. They must not be staged or committed.
