# Initial Platform Validation Audit — Authoritative Rerun 2026-07-21

## Decision And Audit Lineage

Audit `pv-initial-20260721-5fb90fd` is the authoritative initial audit. It is frozen as `baseline_candidate`, not `trusted_baseline`, with decision `stop_and_plan`.

The earlier directory `pv-initial-20260720-372f4a5` is retained unchanged as a superseded draft. It was not used as evidence for this rerun: every test layer, Playwright JSON result, copied attachment tree, coverage join, report, safety scan, and root ledger was regenerated against the new frozen revision.

No product code, Dashboard code, tests, or inventory configuration changed after the authoritative freeze. `config/platform_validation_routes.json` required no verified correction.

## Frozen Inputs And Clean-Worktree Evidence

The first entry in the authoritative command manifest is the required worktree check:

```text
git status --porcelain=v1 --untracked-files=all
exit 0
stdout: empty
stderr: empty
```

Its stdout and stderr are preserved at `inputs/raw/freeze-worktree-status.stdout.log` and `inputs/raw/freeze-worktree-status.stderr.log`. `frozen-inputs.json` records `worktree.status="clean"`, the exact command, exit code, evidence paths, and timestamp.

| Input | Frozen value |
| --- | --- |
| Revision | `5fb90fd1081269f52c4fef9668d3885ca12ed6cc` |
| Inventory SHA-256 | `620a96b51187ff76e72378b01cdbc4af4d146f7878b5fa533bd4b23bcbed537f` |
| Audit date | `2026-07-21` |
| Freeze time | `2026-07-21T07:42:10+08:00` |
| Timezone | `Asia/Shanghai` |
| Python / Node / pnpm | `3.14.4` / `v24.14.1` / `10.33.0` |
| Playwright | `1.60.0` |
| Browsers | Chromium `148.0.7778.96`; Firefox `150.0.2`; WebKit `26.4` |
| PostgreSQL | service/database `stock_research` / `stock_research` |
| Real/Audit URLs | Dashboard `http://127.0.0.1:5374`; API `http://127.0.0.1:8966` |
| Sandbox URLs | Dashboard `http://127.0.0.1:5274`; API `http://127.0.0.1:8866` |

The complete machine-readable freeze is in `outputs/research/platform_validation/pv-initial-20260721-5fb90fd/frozen-inputs.json`.

## Authoritative Command Results

| Layer | Result | Evidence summary |
| --- | --- | --- |
| Worktree freeze | exit 0 | clean; manifest first entry |
| Backend focused contracts | exit 0 | `267 passed`, 2 warnings |
| Dashboard full Vitest | exit 0 | 41 files, `526 passed` |
| Dashboard production build | exit 0 | TypeScript and Vite build passed |
| P0 Mock | exit 0 | `59 passed`, 0 failed/skipped/flaky |
| Real read-only | exit 1 | `19 passed`, `22 failed` |
| Sandbox runner | exit 2 | `_test` service definition missing; no production fallback |
| Audit matrix | exit 1 | `247 passed`, `72 failed`, 0 skipped/flaky |
| Report generator | exit 0 | Four artifacts generated with path checks |
| Report safety sentinel scan | exit 0 with matches | Synthetic bare-secret literals found; P1 reporting-security root remains open |
| Root mapping builder | exit 0 | `46/46` report issues mapped exactly once |

All commands, start/end timestamps, exit codes, stdout, and stderr are in `commands-manifest.json` and `inputs/raw/` under the authoritative audit root.

## Coverage

The inventory contains 15 reachable items and one intentionally hidden/unreachable Data Explorer item.

- Overall: 15 `partial`, 1 `not_applicable`.
- Unit: all 15 reachable items `covered` by the full Dashboard Vitest command.
- API: `review_queue` and `strategy_lab` `covered`; 13 other reachable items `partial` because the audit ran the approved focused backend set rather than every Dashboard API module.
- Playwright: 14 reachable items `partial`; `user_management` lacks a sandbox result; hidden Data Explorer is not applicable.

This coverage state independently prevents trusted-baseline promotion.

## Generated Symptom Ledger

The deterministic generator emitted 46 open symptom groups: 36 P0 and 10 P1.

- Mock: 59 expected, 0 unexpected.
- Real: 19 expected, 22 unexpected.
- Audit: 247 expected, 72 unexpected.
- Chromium desktop: 165 expected, 44 unexpected.
- Chromium mobile: 83 expected, 22 unexpected.
- Firefox desktop: 76 expected, 28 unexpected.
- WebKit critical: 1 expected, 0 unexpected.

These are symptom groups, not independent root causes.

## Exactly-Once Root Mapping

`root-cause-ledger.json` uses schema `platform_validation_root_cause_ledger_v2`. Its machine-check summary is:

```json
{
  "report_issue_total": 46,
  "mapped": 46,
  "unmapped": 0,
  "duplicates": 0,
  "unmapped_issue_ids": [],
  "duplicate_issue_ids": []
}
```

Every report `issue_id` appears in exactly one root's `symptom_issue_ids` and `supporting_issue_ids`. Every mapped root contains the sorted union of all referenced issue evidence paths in `issue_evidence`.

| Root | Severity | Classification | Confirmation | Mapped issues | Evidence union |
| --- | --- | --- | --- | ---: | ---: |
| `PV-ROOT-P0-AUTH-DISABLED-ME` | P0 | product | confirmed | 39 | 376 |
| `PV-ROOT-P0-STRATEGY-PUBLICATION-CATALOG` | P0 | product | confirmed | 1 | 32 |
| `PV-ROOT-P0-FIREFOX-HISTORY-SYNCHRONIZATION` | P0 | test_infrastructure | candidate pending wait contract | 3 | 12 |
| `PV-ROOT-P0-FIREFOX-RUNTIME-EVIDENCE` | P0 | test_infrastructure | confirmed | 3 | 12 |
| `PV-ROOT-P1-AUDIT-EVIDENCE-BARE-SECRET` | P1 | test_infrastructure | confirmed | 0 | 0 |
| `PV-ROOT-ENV-SANDBOX-SERVICE` | null | environment | confirmed | 0 | 0 |

The schema restricts severity to `P0`, `P1`, `P2`, or `null`, and classification to `product`, `test_infrastructure`, or `environment`. Candidate state is represented only by `confirmation_status`. The environment blocker has `severity=null`, `blocker_kind=missing_postgresql_service`, and an explicit disposition. The reporting-security root has `security_category=secret_redaction`.

## Root-Cause Classification

### PV-ROOT-P0-AUTH-DISABLED-ME — P0 product

- Owner: Dashboard auth backend.
- Expected: with `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=false`, `/api/auth/me` returns 200 and the application shell opens.
- Actual: `/api/platform/summary=200` while `/api/auth/me=401`. This root owns the 39 remaining Real critical-journey and route-census symptom groups across P0/P1 inventories and browser projects.
- Plan: [Auth-disabled Dashboard shell contract](../superpowers/plans/2026-07-21-auth-disabled-dashboard-shell-contract.md).

### PV-ROOT-P0-STRATEGY-PUBLICATION-CATALOG — P0 product

- Owner: Strategy publication read model.
- Expected: every runnable official strategy exposes catalog identity matching review queue performance/publication fields.
- Actual: the grouped issue fails first on missing `lhb_shortline.latest_metrics.performance_as_of_date` and includes the home publication-card failures across three projects.
- Plan: [Official strategy publication catalog](../superpowers/plans/2026-07-21-official-strategy-publication-catalog.md).

### PV-ROOT-P0-FIREFOX-HISTORY-SYNCHRONIZATION — P0 test infrastructure candidate

- Owner: Dashboard navigation and Playwright consistency assertions.
- Expected: route assertions wait for Firefox same-document Back traversal.
- Actual: three Firefox-only tests sample the stock URL immediately; Chromium passes and `expectRouteContext` has no retry window.
- Confirmation status: `candidate_pending_wait_contract`; classification remains controlled `test_infrastructure`.
- Plan: [Firefox history consistency waits](../superpowers/plans/2026-07-21-firefox-history-consistency-waits.md).

### PV-ROOT-P0-FIREFOX-RUNTIME-EVIDENCE — P0 test infrastructure

- Owner: Playwright runtime evidence.
- Expected: abort/5xx/599 contracts assert stable failed-request/unhandled-route evidence across engines.
- Actual: three contracts require Chromium-specific console/network wording; Firefox records equivalent evidence differently.
- Plan: [Cross-browser runtime evidence contract](../superpowers/plans/2026-07-21-cross-browser-runtime-evidence-contract.md).

### PV-ROOT-P1-AUDIT-EVIDENCE-BARE-SECRET — P1 test infrastructure

- Owner: Platform validation reporting.
- Security category: `secret_redaction`.
- Expected: archived evidence contains no secret-shaped literal values, including source excerpts.
- Actual: the scan found synthetic `raw-url-secret`, `raw-path-secret`, and `raw-query-secret` values in archived `error-context.md`. They are test sentinels, not real credentials, but the report is not externally publishable.
- Plan: [Audit evidence bare-secret redaction](../superpowers/plans/2026-07-21-audit-evidence-bare-secret-redaction.md).

### PV-ROOT-ENV-SANDBOX-SERVICE — environment blocker

- Severity: `null`; classification: `environment`.
- Blocker kind: `missing_postgresql_service`.
- Expected: `stock_research_e2e_test` resolves to a database ending `_test`.
- Actual: the service definition is absent; runner exits 2 before setup and does not fall back to `stock_research`.
- Disposition: configure an isolated `_test` service and rerun; production fallback remains prohibited.

## Stop Decision And Next Audit

Do not mark a trusted baseline. Execute the five focused plans independently with their specified tests and reviews, configure the isolated `_test` service, and create a new audit ID after fixes merge. The authoritative audit and the superseded draft must both remain preserved; neither may be overwritten.

## Authoritative Generated Output Locations

- Audit root: `outputs/research/platform_validation/pv-initial-20260721-5fb90fd/`
- Frozen inputs: `frozen-inputs.json`
- Commands and raw logs: `commands-manifest.json`, `inputs/raw/`
- Report-ready JSON/evidence: `inputs/report-ready/`
- Coverage declaration: `inputs/coverage-results.json`
- Exactly-once root ledger: `root-cause-ledger.json`
- Report: `report/route_inventory.json`, `report/coverage_matrix.json`, `report/issue_ledger.json`, `report/audit_report.html`

Generated outputs total about 103 MiB and are ignored by Git. They must not be staged or committed.
