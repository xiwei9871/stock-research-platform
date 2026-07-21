# Playwright Platform Validation Runbook

This runbook defines how to execute, preserve, classify, and promote the platform-wide Playwright-first validation baseline. It complements pytest and Vitest; it does not replace backend contracts or component tests.

## Profiles And Gates

| Profile | Purpose | Browser projects | Mutations | Required gate |
| --- | --- | --- | --- | --- |
| `mock` | Deterministic P0 routes, state, publication, auth, error isolation | Chromium desktop; tagged mobile subset | Mock-only | Every PR |
| `real` | Authoritative local APIs, DB-backed read models, publication identity | Chromium desktop | Read-only fixture rejects API writes | Before release and full audit |
| `sandbox` | Login, admin, operator decision, and other write journeys | Chromium desktop | Only isolated PostgreSQL database ending `_test` | Before release when service exists |
| `audit` | P0 + Real + accessibility + visual + cross-browser census | Chromium desktop/mobile, Firefox desktop, WebKit critical | Read-only except mocked tests | Initial audit and release audit |
| `eod` | Small daily operational acceptance | Chromium desktop | Read-only | Auto EOD Repair after data repair |

Priority tags are `@p0`, `@p1`, and `@p2`. Capability tags include `@mock`, `@real`, `@route-census`, `@critical`, `@mobile`, `@visual`, `@webkit-critical`, `@publication`, and `@runtime-contract`. The CI workflow keeps the full P0 Mock profile mandatory; affected-test selection may add tests but may not replace it.

## Freeze An Audit

Choose a new immutable audit ID; never reuse an existing directory.

```bash
revision="$(git rev-parse HEAD)"
audit_id="pv-initial-YYYYMMDD-${revision:0:7}"
audit_root="outputs/research/platform_validation/${audit_id}"
```

Before any other audit command or documentation edit, execute and preserve:

```bash
git status --porcelain=v1 --untracked-files=all
```

The command must be the first entry in `commands-manifest.json`, with start/end timestamps, exit code, and separate stdout/stderr evidence paths. An authoritative freeze requires exit 0 and empty stdout. If any tracked or untracked path is printed, stop immediately; do not run a layer or describe the audit as frozen.

The audit runner must write each action atomically in two phases:

1. before execution: `status=started`, action ID, command, cwd, start time, stdout path, and stderr path;
2. after execution: terminal status, exit code, end time, interruption detail, log sizes, and log SHA-256 values.

Signal or runner exceptions must leave a durable `interrupted` or `error` action instead of creating a manifest gap. Expected nonzero test or gate attempts remain in the manifest alongside their successful correction.

Before running any layer, save:

- full revision and clean/dirty status;
- SHA-256 of `config/platform_validation_routes.json`;
- execution timestamp, labeled audit date, and `Asia/Shanghai` timezone;
- Python, Node.js, pnpm, Playwright, Chromium, Firefox, and WebKit versions;
- PostgreSQL service name and `SELECT current_database()` result;
- Dashboard/API URLs for Real/Audit plus sandbox URLs;
- requested baseline status, initially `baseline_candidate`.
- `worktree.status=clean`, the exact status command, its exit code, evidence paths, and timestamp.

After the freeze, do not edit `src/`, Dashboard product code, tests, or Playwright configuration. Only commands, generated evidence, audit documentation, and stop-rule plans are allowed.

If a draft audit is found to have an invalid freeze or incomplete mapping, retain its output directory unchanged and mark it `superseded` in the next authoritative audit's `frozen-inputs.json` and human summary. Never relabel old results with a new revision.

## Standard Commands

The examples use ports `5374` and `8966` to avoid the interactive local Dashboard on `5174`.

Backend focused contracts:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_review_queue.py \
  tests/test_platform_validation_report.py \
  tests/test_playwright_sandbox.py \
  tests/test_run_playwright_sandbox.py \
  tests/test_config_settings.py -q
```

Dashboard unit and build:

```bash
cd dashboard
rtk pnpm test -- --run
rtk pnpm build
```

P0 Mock:

```bash
cd dashboard
PLAYWRIGHT_DASHBOARD_PORT=5374 \
PLAYWRIGHT_JSON_OUTPUT_NAME="$audit_root/inputs/raw/playwright-mock-p0.json" \
pnpm test:e2e:p0
```

Real read-only:

```bash
cd dashboard
PLAYWRIGHT_DASHBOARD_PORT=5374 \
PLAYWRIGHT_API_PORT=8966 \
PLAYWRIGHT_JSON_OUTPUT_NAME="$audit_root/inputs/raw/playwright-real-readonly.json" \
pnpm test:e2e:real
```

Sandbox:

```bash
/Users/xiwei/stock_research/.venv/bin/python scripts/run_playwright_sandbox.py
```

The sandbox runner must resolve `stock_research_e2e_test`, connect, and verify `current_database()` ends in `_test`. Missing service is exit 2 and an environment blocker. A non-test database is a hard refusal. Never set `PLAYWRIGHT_SANDBOX_SERVICE=stock_research`.

Full Audit:

```bash
cd dashboard
PLAYWRIGHT_DASHBOARD_PORT=5374 \
PLAYWRIGHT_API_PORT=8966 \
PLAYWRIGHT_JSON_OUTPUT_NAME="$audit_root/inputs/raw/playwright-audit-matrix.json" \
pnpm test:e2e:audit
```

Use distinct JSON names and profile artifact directories. After every Playwright command, copy the matching `dashboard/test-results/<profile>` and `dashboard/playwright-report/<profile>` trees into that audit's `inputs/raw/` before a later command can overwrite them.

Every copy and transformation is a separately recorded runner action. This includes raw artifact copies, report-ready evidence copies, coverage JSON generation, attachment-path rebasing, report generation, root-ledger generation, safety scanning, permission normalization, artifact-manifest generation, and sealed verification. Do not use an unrecorded `cp`, ad hoc script, or reused prior-audit result.

## Report Inputs And Coverage

Create `platform_validation_coverage_results_v1` JSON. Every declared `unit` or `api` status must cite an evidence file relative to the coverage JSON. Use `covered` only when the command exercises the inventory item, `partial` when the command provides relevant but incomplete evidence, and `missing` when no accepted command covers it.

Playwright JSON attachment paths must resolve inside the result JSON's directory. Preserve the original JSON under `inputs/raw/`; if absolute Playwright paths point back to the checkout, create a report-ready copy plus a copied evidence tree under `inputs/report-ready/`. Do not rewrite or delete the raw result.

Generate a candidate report with explicitly labeled inputs:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  scripts/build_platform_validation_report.py \
  config/platform_validation_routes.json \
  --playwright-results "mock=$audit_root/inputs/report-ready/playwright-mock-p0.json" \
  --playwright-results "real=$audit_root/inputs/report-ready/playwright-real-readonly.json" \
  --playwright-results "audit=$audit_root/inputs/report-ready/playwright-audit-matrix.json" \
  --coverage-results "$audit_root/inputs/coverage-results.json" \
  --output-dir "$audit_root/report" \
  --audit-id "$audit_id" \
  --revision "$revision" \
  --audit-date YYYY-MM-DD \
  --baseline-status baseline_candidate
```

Expected report files:

- `route_inventory.json`
- `coverage_matrix.json`
- `issue_ledger.json`
- `audit_report.html`

Sandbox has no Playwright JSON when its service is unavailable. Keep the runner command and stderr as environment-blocker evidence; do not invent an empty result file or silently omit the blocker from the human summary.

## Classification And Stop Rule

The generated ledger groups deterministic test evidence but may still contain many symptoms for one root. Maintain a human root-cause ledger with:

- one severity for each open root;
- classification: product, test infrastructure, or environment;
- exact reproduction command;
- expected and actual behavior;
- owner area;
- all supporting generated issue IDs and evidence paths;
- follow-up plan path for each P0/P1 root.

The machine-readable root ledger must map every generated report `issue_id` exactly once. Store each root's sorted `symptom_issue_ids`, identical `supporting_issue_ids`, and the union of every referenced issue's report evidence paths. Its summary must include `report_issue_total`, `mapped`, `unmapped`, and `duplicates`; authoritative output requires `mapped=report_issue_total`, `unmapped=0`, and `duplicates=0`.

Root schema rules:

- `severity`: only `P0`, `P1`, `P2`, or `null`;
- `classification`: only `product`, `test_infrastructure`, or `environment`;
- uncertain/candidate state belongs in `confirmation_status`, never `classification`;
- environment blockers use `severity=null` plus `blocker_kind` and `disposition`;
- reporting-security roots remain `classification=test_infrastructure` and add `security_category`.

If any P0 or P1 product issue remains, stop. Do not repair during the frozen audit, do not mark `trusted_baseline`, and do not overwrite the audit. Create one focused plan per independent root and rerun under a new audit ID after fixes merge.

Promote to `trusted_baseline` only when:

- no P0/P1 product issue remains;
- accepted P2 issues have explicit disposition and evidence;
- every required inventory layer/profile has traceable covered evidence;
- sandbox is either executed successfully or has an explicitly approved environmental disposition;
- the report CLI accepts `--baseline-status trusted_baseline` without relaxation.

## Evidence Security And Retention

- Never archive cookies, passwords, authorization headers, CSRF tokens, API keys, or raw request headers.
- Keep report ingestion fail-closed on path traversal, symlinks, unsafe archives, oversized JSON, and secret-shaped text.
- Before tests, run a scanner self-test that requires four credential-bearing review fixtures to classify as potential real credentials and a synthetic fixture to remain synthetic. Scan `inputs/raw`, copied artifact/report trees, `inputs/report-ready`, the generated report/evidence, recursive JSON/JSONL keys and header name/value pairs, and text members inside ZIP traces. Classify findings as known synthetic sentinels, known noncredential framework code, potential real credentials, or scan errors. Framework classification may use only a fixed token-hash allowlist bound to the discovered Playwright version; path-level framework whitelists are prohibited. Potential real credentials or scan errors block sealing; expected synthetic sentinels keep the candidate untrusted and support the R5 ledger.
- Generated audit directories stay under ignored `outputs/research/platform_validation/`; do not `git add` them.
- Retain daily EOD evidence for 90 days, then delete by whole audit directory after confirming it is not a release/trusted baseline or linked incident.
- Retain initial audits, trusted baselines, release audits, and incident evidence long term.
- Restrict local evidence permissions to the operator account; never publish traces or screenshots without a security scan.

Create the audit root with mode `0700` under `umask 077`. Normalize all directories to `0700` and all files to `0600`. The final permission gate must record `world_readable=0` and `world_traversable=0`; any nonstandard mode blocks sealing.

After all core actions are terminal, freeze the live runner log into immutable `core-commands-manifest.json`. Generate `artifact-manifest.json` only after core artifacts, safety outputs, root mapping, the core permission gate, and that snapshot are complete. Record every core file's relative path, type, size, mode, and SHA-256; record every directory's mode, file count, total size, and deterministic tree SHA-256. Exclude the live core/post-seal manifests, the artifact manifest and final seal, temporary files, and the documented post-seal `verification/**` chain.

Record subsequent verification, documentation, Git, and final read-only permission-stat actions in `post-seal-commands-manifest.json`. Bind the immutable core-command SHA-256, artifact-manifest SHA-256, artifact tree SHA-256, mapping, scan, and core permission results in `seal.json`.

After generating the artifact manifest, do not modify core artifacts. Recompute the complete file and directory manifest into `verification/sealed-verification.json`; require zero file/directory mismatches and a repeated world-permission count of zero.

## Daily EOD Use

Auto EOD Repair should run the small `eod` acceptance after repair succeeds. Daily execution is not a substitute for this full audit: it validates critical read-only routes, trade-date coherence, official publication identity, and runtime cleanliness, while the full Audit profile remains the release and regression census.

## Current Authoritative Initial Audit

The sealed authoritative initial audit is `pv-initial-20260721-ba46611` at revision `ba4661144d3a3a12e1934b720d75dd97e04d6e85`.

The earlier `pv-initial-20260720-372f4a5`, `pv-initial-20260721-5fb90fd`, and `pv-initial-20260721-796495a` directories are retained unchanged as superseded attempts. Their results must not be used as evidence for the current revision.
