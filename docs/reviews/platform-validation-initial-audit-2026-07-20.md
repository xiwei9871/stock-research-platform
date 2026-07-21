# Initial Platform Validation Audit — Sealed Authoritative Rerun 2026-07-21

## Decision And Audit Lineage

Audit `pv-initial-20260721-796495a` is the sealed authoritative initial audit. It is frozen as `baseline_candidate`, not `trusted_baseline`, with decision `stop_and_plan`.

Two earlier directories remain unchanged and are superseded:

- `pv-initial-20260720-372f4a5`: draft with incomplete freeze provenance;
- `pv-initial-20260721-5fb90fd`: authoritative attempt with incomplete action-level provenance and sealing.

Neither earlier run was reused. Every discovery command, test layer, Playwright result, artifact copy, coverage declaration, report-ready transformation, report, root ledger, safety scan, permission gate, and provenance manifest was generated again from the new frozen revision.

No product code, Dashboard code, tests, or inventory configuration changed after the freeze. `config/platform_validation_routes.json` required no verified correction.

## Frozen Inputs And Runner Contract

The first manifest action was:

```text
git status --porcelain=v1 --untracked-files=all
exit 0
stdout: empty
stderr: empty
```

The audit root was created with mode `0700`; bootstrap helper files use `0600`. After bootstrap, every external command and internal artifact transformation ran through `run_command.py`.

For each action, the runner atomically wrote `status=started`, command, cwd, and start time before launching the subprocess. It then atomically sealed status, end time, exit code, interruption state, stdout/stderr sizes, and SHA-256 hashes. Nonzero expected test/gate attempts remain in the manifest instead of being erased. Signal and exception paths preserve `interrupted` or `error` state.

| Input | Frozen value |
| --- | --- |
| Revision | `796495a511646fafc8333c7aac58a3dcc0cab483` |
| Inventory SHA-256 | `620a96b51187ff76e72378b01cdbc4af4d146f7878b5fa533bd4b23bcbed537f` |
| Audit date | `2026-07-21` |
| Freeze time | `2026-07-21T08:24:03+08:00` |
| Timezone | `Asia/Shanghai` |
| Python / Node / pnpm | `3.14.4` / `v24.14.1` / `10.33.0` |
| Playwright | `1.60.0` |
| Browsers | Chromium `148.0.7778.96`; Firefox `150.0.2`; WebKit `26.4` |
| PostgreSQL | service/database `stock_research` / `stock_research` |
| Real/Audit URLs | Dashboard `http://127.0.0.1:5374`; API `http://127.0.0.1:8966` |
| Sandbox URLs | Dashboard `http://127.0.0.1:5274`; API `http://127.0.0.1:8866` |

Runtime, browser, database, revision, time, and inventory discovery each have separate recorded actions and evidence logs. The complete freeze is `outputs/research/platform_validation/pv-initial-20260721-796495a/frozen-inputs.json`.

## Test And Report Results

| Layer | Result | Evidence summary |
| --- | --- | --- |
| Backend focused contracts | exit 0 | `267 passed`, 2 warnings |
| Dashboard full Vitest | exit 0 | 41 files, `526 passed` |
| Dashboard production build | exit 0 | TypeScript and Vite build passed |
| P0 Mock | exit 0 | `59 passed`, 0 failed/skipped/flaky |
| Real read-only | exit 1 | `19 passed`, `22 failed` |
| Sandbox runner | exit 2 | `_test` service definition missing; no production fallback |
| Audit matrix | exit 1 | `247 passed`, `72 failed`, 0 skipped/flaky |
| Report generator | exit 0 | Four report artifacts plus sanitized evidence generated |
| Root mapping builder | exit 0 | `46/46` report issues mapped exactly once |

The generated symptom ledger remains 46 open groups: 36 P0 and 10 P1.

- Chromium desktop: 165 expected, 44 unexpected.
- Chromium mobile: 83 expected, 22 unexpected.
- Firefox desktop: 76 expected, 28 unexpected.
- WebKit critical: 1 expected, 0 unexpected.

## Coverage

The inventory contains 15 reachable items and one intentionally hidden/unreachable Data Explorer item.

- Overall: 15 `partial`, 1 `not_applicable`.
- Unit: all 15 reachable items `covered` by the full Dashboard Vitest command.
- API: `review_queue` and `strategy_lab` `covered`; 13 other reachable items `partial` under the approved focused backend set.
- Playwright: 14 reachable items `partial`; `user_management` lacks a sandbox result; hidden Data Explorer is not applicable.

This independently prevents trusted-baseline promotion.

## Exactly-Once Root Mapping

`root-cause-ledger.json` uses `platform_validation_root_cause_ledger_v2`:

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

Every generated `issue_id` appears in exactly one root. Each root has identical `symptom_issue_ids` and `supporting_issue_ids`, plus the sorted union of all referenced report evidence paths in `issue_evidence`.

| Root | Severity | Classification | Confirmation | Mapped issues | Evidence union |
| --- | --- | --- | --- | ---: | ---: |
| `PV-ROOT-P0-AUTH-DISABLED-ME` | P0 | product | confirmed | 39 | 376 |
| `PV-ROOT-P0-STRATEGY-PUBLICATION-CATALOG` | P0 | product | confirmed | 1 | 32 |
| `PV-ROOT-P0-FIREFOX-HISTORY-SYNCHRONIZATION` | P0 | test_infrastructure | candidate pending wait contract | 3 | 12 |
| `PV-ROOT-P0-FIREFOX-RUNTIME-EVIDENCE` | P0 | test_infrastructure | confirmed | 3 | 12 |
| `PV-ROOT-P1-AUDIT-EVIDENCE-BARE-SECRET` | P1 | test_infrastructure | confirmed | 0 | 0 |
| `PV-ROOT-ENV-SANDBOX-SERVICE` | null | environment | confirmed | 0 | 0 |

Severity is restricted to `P0`, `P1`, `P2`, or `null`; classification is restricted to `product`, `test_infrastructure`, or `environment`. Candidate state uses `confirmation_status`. The environment blocker has `severity=null`, `blocker_kind`, and `disposition`. The security root has `security_category=secret_redaction`.

## Full Safety Scan

The recorded final scan covered:

- `inputs/raw`, including original JSON/logs and copied Playwright artifact/report trees;
- `inputs/report-ready` and all copied report-ready evidence;
- the generated report and `report/evidence`;
- text members inside ZIP traces.

Machine result:

| Metric | Result |
| --- | ---: |
| Text files scanned | 658 |
| ZIP members scanned | 8,246 |
| Known synthetic sentinel findings | 8,034 |
| Known noncredential Playwright bundle-code findings | 25 |
| Potential real credential findings | 0 |
| Scan errors | 0 |
| Gate | `pass_with_expected_sentinel` |

The 25 framework findings are password-like tokens inside Playwright's own `playwright-report/index.html` and `trace/sw.bundle.js`; they remain recorded as `known_noncredential_framework_code`, not silently dropped. The synthetic sentinel matches preserve R5. Any potential real credential or scan error would have blocked sealing.

## Permissions And Provenance Seal

The final permission normalization/gate recorded:

- directories: 946;
- files: 1,977;
- nonstandard directory/file modes: 0/0;
- `world_readable=0`;
- `world_traversable=0`;
- gate: `pass`.

All audit directories use `0700`; all files use `0600`.

`artifact-manifest.json` records 1,974 core files and 945 directories totaling 107,145,493 bytes. Every file entry has relative path, type, size, mode, and SHA-256. Every directory entry has mode, file count, total size, and deterministic tree SHA-256.

The manifest explicitly excludes only `commands-manifest.json`, `artifact-manifest.json`, temporary files, and the post-seal `verification/**` chain. It includes frozen inputs, helpers, raw JSON/logs, copied artifacts, coverage, report-ready inputs, report files/evidence, root ledger, safety outputs, and permission gate.

The sealed verification recomputed all manifest entries:

```json
{
  "artifact_manifest_sha256": "beb19e6e70c7f5f1d41044b6a570ce738f7b1caf0f33484f6fb03fdd22d07f8d",
  "file_mismatches": [],
  "directory_mismatches": [],
  "hash_gate": "pass",
  "permission_gate": "pass",
  "world_readable": 0,
  "world_traversable": 0
}
```

Intermediate failed scan and first seal attempts remain in `commands-manifest.json`; their corrected successors pass. Core artifacts were not modified after the final artifact manifest was generated.

## Root-Cause Disposition

The five focused plans remain authoritative:

- [Auth-disabled Dashboard shell contract](../superpowers/plans/2026-07-21-auth-disabled-dashboard-shell-contract.md)
- [Official strategy publication catalog](../superpowers/plans/2026-07-21-official-strategy-publication-catalog.md)
- [Firefox history consistency waits](../superpowers/plans/2026-07-21-firefox-history-consistency-waits.md)
- [Cross-browser runtime evidence contract](../superpowers/plans/2026-07-21-cross-browser-runtime-evidence-contract.md)
- [Audit evidence bare-secret redaction](../superpowers/plans/2026-07-21-audit-evidence-bare-secret-redaction.md)

The sandbox environment disposition remains: configure an isolated `stock_research_e2e_test` database ending `_test`; production fallback stays prohibited.

## Stop Decision

Do not mark a trusted baseline. Execute and review the five plans, configure the sandbox service, and rerun under a new audit ID. Preserve all three initial-audit directories; the first two remain superseded and the third is the sealed authoritative evidence set.

## Generated Output Locations

- Audit root: `outputs/research/platform_validation/pv-initial-20260721-796495a/`
- Commands: `commands-manifest.json`
- Frozen inputs: `frozen-inputs.json`
- Coverage: `inputs/coverage-results.json`
- Safety: `safety-scan.json`, `safety-findings.json`
- Permissions: `permission-gate.json`
- Root mapping: `root-cause-ledger.json`
- Artifact provenance: `artifact-manifest.json`
- Sealed verification: `verification/sealed-verification.json`
- Report: `report/route_inventory.json`, `report/coverage_matrix.json`, `report/issue_ledger.json`, `report/audit_report.html`

Generated outputs are ignored by Git and must not be staged or committed.
