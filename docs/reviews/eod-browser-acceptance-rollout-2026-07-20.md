# EOD Browser Acceptance Rollout Review — 2026-07-20

Status: **BLOCKED / stop_and_plan**

Execution date: 2026-07-21, `Asia/Shanghai` (`+08:00`)

Application revision: `1ea8f2f377366c10b38a2a1eee04eaefc87354ff`

Authoritative audit sources:

- execution audit `pv-initial-20260721-ba46611`;
- security rescan `pv-initial-20260721-a2c847a-security-rescan`.

The security rescan closed the bare-secret evidence finding. It did not rerun application, browser, or sandbox layers and therefore does not clear the remaining rollout blockers.

## Decision

Regression, Mock P0, historical failure simulation, and repairable stale-cache simulation passed. Controlled candidate execution, rollout-boundary enablement, and first-live-run observation did not run.

The current shell confirmed `STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED` is false/unset and `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM` is empty. Both execution and promotion are therefore disabled. This review did not change environment variables, service configuration, deployment configuration, databases, or official output directories. Real and Sandbox profiles were not run as success evidence.

Task 7 status:

| Step | Status | Evidence or reason |
| --- | --- | --- |
| Step 1 complete focused regression | complete | Backend, Vitest, build, and Mock P0 all exited 0. |
| Step 2 historical 175.29 simulation | complete | Injected temporary fixture failed with `api_ui_mismatch` and `return_unit`; no cache clear; manifest failed; prior ready date remained; EOD exit 2. |
| Step 3 successful controlled candidate | **not complete** | Blocked by the authoritative audit roots below; no Real/EOD live browser run was started. |
| Step 4 repairable stale-cache path | complete | The default action integration fixture proves one cache clear, one identical-command rerun, final success, and two attempts; it also proves nonrepairable and missing-URL fail-safe paths. |
| Step 5 enable rollout boundary | **not complete** | Boundary intentionally remains disabled. |
| Step 6 observe first live run | **not complete** | No live rollout occurred, so duration/display/process observations cannot be claimed. |
| Step 7 evidence and rollback | complete | Recorded here and in the two operations runbooks. |
| Step 8 documentation commit | complete | The implementation, rollback commands, and verification record are updated together; the final commit SHA is reported with task handoff. |

## Fresh Regression Evidence

Run the Python commands below from either the main checkout or a linked worktree after resolving the shared main-repository virtual environment:

```bash
PYTHON_BIN="${STOCK_RESEARCH_PYTHON:-$(cd "$(git rev-parse --git-common-dir)/.." && pwd)/.venv/bin/python}"
test -x "$PYTHON_BIN"
```

`git rev-parse --git-common-dir` returns `.git` in the main checkout and the main repository's absolute `.git` path in a linked worktree, so both forms resolve the same interpreter. `STOCK_RESEARCH_PYTHON` remains the explicit override. The historical `455 passed` and corrective regression results were executed with this main repository virtual environment; this review does not claim that the linked worktree contains its own `.venv`.

### Backend focused

Exact command:

```bash
PYTHONPATH=src rtk "$PYTHON_BIN" -m pytest \
  tests/test_eod_browser_acceptance.py \
  tests/test_eod_auto_repair.py \
  tests/test_eod_auto_repair_checks.py \
  tests/test_eod_auto_repair_models.py \
  tests/test_eod_auto_repair_report.py \
  tests/test_eod_auto_repair_scripts.py \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_review_queue.py -q
```

Result: exit `0`; `455 passed`; 2 existing `py_mini_racer` deprecation warnings; duration `10.48s`.

### Corrective fail-safe regression

The original `455 passed` record above remains the historical Task 7 plan evidence. After adding the real execution kill switch, moving cache clear into the whitelisted default action path, removing the cron-level unconditional clear, and correcting rollback documentation, the commit-preparation worktree ran this expanded focused set:

```bash
PYTHONPATH=src rtk "$PYTHON_BIN" -m pytest \
  tests/test_config_settings.py \
  tests/test_eod_browser_acceptance.py \
  tests/test_eod_auto_repair.py \
  tests/test_eod_auto_repair_checks.py \
  tests/test_eod_auto_repair_models.py \
  tests/test_eod_auto_repair_report.py \
  tests/test_eod_auto_repair_scripts.py \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_review_queue.py -q
```

Result: exit `0`; `480 passed`; 2 existing `py_mini_racer` deprecation warnings. The same worktree also passed `git diff --check`, `bash -n scripts/run_eod_auto_repair_cron.sh`, and Python byte-compilation of `config.py` and `eod_auto_repair.py`.

### Local target hardening regression

The subsequent local-target correction kept the same ten-file focused set and added fail-closed coverage for literal loopback addressing, exact cache/login paths, ports and effective-port origin matching, DNS and remote-IP rejection, userinfo/query/fragment rejection, disabled environment proxies, and redirect non-forwarding for both login and cache POST requests:

```bash
PYTHONPATH=src rtk "$PYTHON_BIN" -m pytest \
  tests/test_config_settings.py \
  tests/test_eod_browser_acceptance.py \
  tests/test_eod_auto_repair.py \
  tests/test_eod_auto_repair_checks.py \
  tests/test_eod_auto_repair_models.py \
  tests/test_eod_auto_repair_report.py \
  tests/test_eod_auto_repair_scripts.py \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_review_queue.py -q
```

Result: exit `0`; `502 passed`; 2 existing `py_mini_racer` deprecation warnings; duration `14.28s`. This is a local fixture/unit regression only and does not change the `BLOCKED / stop_and_plan` rollout decision.

A final delimiter edge-case pass added explicit rejection of empty `?` and `#` components for both endpoints. Re-running the same command exited `0` with `506 passed`, the same 2 deprecation warnings, and duration `10.90s`.

### Dashboard unit

Exact command from `dashboard/`:

```bash
rtk pnpm test
```

Result: exit `0`; 41 files and `527 passed`; duration `6.55s`.

### Dashboard build

Exact command from `dashboard/`:

```bash
rtk pnpm build
```

Result: exit `0`; TypeScript and Vite build passed; 2,237 modules transformed; Vite build duration `2.31s`. The existing warning that the main minified chunk exceeds 500 kB remains informational and did not fail the build.

### Mock P0 Playwright

Exact command from `dashboard/`:

```bash
rtk pnpm test:e2e:p0
```

Result: exit `0`; `59 passed`; duration `17.5s`. This was the deterministic Mock profile only. No Real or Sandbox profile result is represented as successful rollout evidence.

## Historical 175.29 Return-Unit Simulation

Simulation identity:

| Field | Value |
| --- | --- |
| Browser run ID | `task7-return-unit-20260720` |
| EOD run ID | `task7-eod-return-unit-20260720` |
| Trade date | `2026-07-20` |
| Revision | `1ea8f2f` |
| Publish IDs | `lhb_shortline-publish-2026-07-20`, `mid_trend-publish-2026-07-20`, `tech_bottleneck-publish-2026-07-20` |
| Injected rendered value | LHB `175.29%` |
| Injected wrapper duration | `0.001906s` |
| Browser status | `failed` |
| Failure classes | `api_ui_mismatch`, `return_unit` |
| Cache clear calls | `0` |
| Browser attempts | `1` |
| Browser manifest | `failed` |
| Display gate | candidate `incomplete`; retained prior ready date `2026-07-19` |
| EOD CLI exit | `2` |

The simultaneous `api_ui_mismatch` classification records the rendered/API inconsistency. The core regression proof is the additional fixed `return_unit` class caused by the rendered `175.29%` token. Because the failure is nonrepairable, cache clearing remained at zero and there was no second browser attempt.

The command reused `FakeProcess`, report writers, publication fixtures, and display-gate fixtures from the existing tests. It used `TemporaryDirectory`; its JSON, trace, and EOD paths were deleted at process exit. There is deliberately no persistent fixture artifact path and no official `outputs/` or database mutation. The durable safe summary is this review.

Exact reproducible injected command:

```bash
PYTHONPATH=src rtk "$PYTHON_BIN" - <<'PY'
from contextlib import redirect_stdout
from datetime import datetime
import io, json, runpy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from stock_research.dashboard import display_date_gate
from stock_research.eod_auto_repair import _main
import stock_research.eod_auto_repair as auto
from stock_research.eod_auto_repair_models import RepairActionResult, RepairCheckResult, RepairRunSummary, RepairStatus
from stock_research.eod_browser_acceptance import run_browser_acceptance, write_browser_acceptance_manifest

b = runpy.run_path('tests/test_eod_browser_acceptance.py')
d = runpy.run_path('tests/test_dashboard_readiness.py')
trade_date = b['TRADE_DATE']
run_id = 'task7-return-unit-20260720'
revision = '1ea8f2f'
candidates = b['_candidate_identities']()
calls, cache_clears, manifest_rows = [], [], []
with TemporaryDirectory(prefix='task7-return-unit-') as temporary:
    output = Path(temporary)
    def popen(command, **kwargs):
        calls.append(command)
        def write_failure(call_kwargs):
            path = Path(call_kwargs['env']['PLAYWRIGHT_EOD_OUTPUT_DIR']) / 'eod-browser-acceptance.json'
            b['_write_report'](path, run_id=run_id, status='failed', failures=['api_ui_mismatch: rendered LHB=175.29% expected 53.40%'], failed_gate='candidate-consistency')
            payload = json.loads(path.read_text(encoding='utf-8'))
            payload['revision'] = revision
            path.write_text(json.dumps(payload), encoding='utf-8')
        return b['FakeProcess'](kwargs, write_failure, exit_code=1)
    result = run_browser_acceptance(trade_date=trade_date, run_id=run_id, revision=revision, output_dir=output, candidate_publications=candidates, previous_publications=b['_previous_json'](), popen=popen, runtime_checker=lambda _dashboard: None, cache_clearer=lambda: cache_clears.append('cleared'))
    manifest = write_browser_acceptance_manifest(result, manifest_upsert=manifest_rows.append)
    modules = d['_display_gate_modules']('2026-07-19', run_id='prior-ready')
    modules.extend(d['_display_gate_modules'](trade_date, run_id=run_id, browser_status='failed'))
    with patch.object(display_date_gate, 'SETTINGS', SimpleNamespace(browser_acceptance_required_from=trade_date)), patch.object(display_date_gate, 'load_strategy_contracts', lambda profile='balanced': {}):
        gate = display_date_gate.select_display_date(modules, latest_market_date=trade_date, now=datetime(2026, 7, 20, 21, 0, tzinfo=display_date_gate.LOCAL_ZONE))
    summary = RepairRunSummary(trade_date=trade_date, mode='loop', final_status=RepairStatus.FAILED, actions=[RepairActionResult('dashboard_browser_acceptance', RepairStatus.FAILED, result.message)], checks_after=[RepairCheckResult('dashboard_browser_acceptance', RepairStatus.FAILED, result.message, blocker=True)], remaining_blockers=['dashboard_browser_acceptance'], run_id='task7-eod-return-unit-20260720')
    with patch.object(auto, 'build_default_action_registry', lambda **_kwargs: {}), patch.object(auto, 'run_eod_auto_repair', return_value=summary), redirect_stdout(io.StringIO()):
        assert _main(['--trade-date', trade_date, '--output-dir', str(output / 'eod'), '--mode', 'loop']) == 2
    assert result.status == RepairStatus.FAILED
    assert result.failure_classes == ('api_ui_mismatch', 'return_unit')
    assert cache_clears == [] and len(calls) == 1
    assert manifest['status'] == 'failed'
    assert gate['display_trade_date'] == '2026-07-19'
PY
```

Two setup-only invocations were rejected before authoritative evidence: one omitted `PYTHONPATH=src`; another read publications from the wrong summary nesting. A third diagnostic aligned neither fixture nor application revision and correctly classified as infrastructure. All used temporary directories and left no artifact or state. Only the revision-aligned run above is accepted as the return-unit simulation.

## Repairable Stale-Cache Simulation

Simulation identity:

| Field | Value |
| --- | --- |
| Browser run ID | `task7-stale-cache-20260720` |
| EOD run ID | `task7-eod-stale-cache-20260720` |
| Trade date | `2026-07-20` |
| Revision | `1ea8f2f` |
| Publish IDs | same three explicit IDs listed above |
| Injected wrapper duration | `0.003033s` |
| Final status | `success` |
| Cache clear calls | exactly `1` |
| Browser commands | `pnpm test:e2e:eod`, then the identical command once more |
| Rerun count | exactly `1` |
| Attempt 1 | `failed`, class `stale_cache` |
| Attempt 2 | `success`, no failure class |
| Markdown report | contained both `Attempt 1` and `Attempt 2` |

The current authoritative implementation proof exercises `build_default_action_registry`, the real `run_browser_acceptance` retry decision, and the configured cache clearer through the default action boundary. It covers the repairable, nonrepairable, and missing-cache-URL branches without starting a real browser:

```bash
PYTHONPATH=src rtk "$PYTHON_BIN" -m pytest tests/test_eod_auto_repair.py -q -k 'default_browser_action_integration'
```

Result: exit `0`; `3 passed`. The fixture proves `stale_cache` performs exactly one clear and one identical `pnpm test:e2e:eod` rerun; `api_ui_mismatch` performs zero clears and zero reruns; and a repairable first failure with no `DASHBOARD_CACHE_CLEAR_URL` returns failed/infrastructure after the first attempt.

The earlier injected `FakeProcess`/temporary-directory simulation below is retained as supplemental report-rendering evidence; it did not start a real browser. Attempt JSON and trace fixture files were removed with the temporary directory. There is deliberately no persistent fixture artifact path.

Exact reproducible injected command:

```bash
PYTHONPATH=src rtk "$PYTHON_BIN" - <<'PY'
import json, runpy
from pathlib import Path
from tempfile import TemporaryDirectory

from stock_research.eod_auto_repair import _browser_result_payload
from stock_research.eod_auto_repair_models import RepairActionResult, RepairCheckResult, RepairRunSummary
from stock_research.eod_auto_repair_report import render_markdown_report
from stock_research.eod_browser_acceptance import run_browser_acceptance

h = runpy.run_path('tests/test_eod_browser_acceptance.py')
trade_date, run_id, revision = h['TRADE_DATE'], 'task7-stale-cache-20260720', '1ea8f2f'
candidates = h['_candidate_identities']()
calls, cache_clears = [], []
with TemporaryDirectory(prefix='task7-stale-cache-') as temporary:
    output = Path(temporary)
    def popen(command, **kwargs):
        attempt = len(calls) + 1
        calls.append(command)
        def write_report(call_kwargs):
            path = Path(call_kwargs['env']['PLAYWRIGHT_EOD_OUTPUT_DIR']) / 'eod-browser-acceptance.json'
            if attempt == 1:
                h['_write_report'](path, run_id=run_id, status='failed', failures=['stale_cache: old selector payload'], failed_gate='runtime-deep-links', severity='blocker-runtime')
            else:
                h['_write_report'](path, run_id=run_id)
            payload = json.loads(path.read_text(encoding='utf-8'))
            payload['revision'] = revision
            path.write_text(json.dumps(payload), encoding='utf-8')
        return h['FakeProcess'](kwargs, write_report, exit_code=1 if attempt == 1 else 0)
    result = run_browser_acceptance(trade_date=trade_date, run_id=run_id, revision=revision, output_dir=output, candidate_publications=candidates, previous_publications=h['_previous_json'](), popen=popen, runtime_checker=lambda _dashboard: None, cache_clearer=lambda: cache_clears.append('cleared'))
    action = RepairActionResult('dashboard_browser_acceptance', result.status, result.message, metrics={'run_id': run_id}, artifact_paths=list(result.artifact_paths), validation_result={'evidence': {'candidate_publications': candidates, 'parsed_result': _browser_result_payload(result)}})
    summary = RepairRunSummary(trade_date=trade_date, mode='loop', final_status=result.status, actions=[action], checks_after=[RepairCheckResult('dashboard_browser_acceptance', result.status, result.message)], run_id='task7-eod-stale-cache-20260720')
    report = render_markdown_report(summary, output)
    assert cache_clears == ['cleared']
    assert calls == [['pnpm', 'test:e2e:eod'], ['pnpm', 'test:e2e:eod']]
    assert [attempt.status.value for attempt in result.attempts] == ['failed', 'success']
    assert result.attempts[0].failure_classes == ('stale_cache',)
    assert 'Attempt 1' in report and 'Attempt 2' in report
PY
```

## Controlled Rollout Blockers

The authoritative initial audit pair requires rollout to stop:

1. Dashboard authentication is configured disabled, but `/api/auth/me` returns `401`; Real shell journeys cannot establish the documented disabled-auth contract.
2. The official strategy catalog does not consistently expose complete publication identity and current performance date for all three official strategies.
3. Firefox Back/Forward history assertions need an explicit asynchronous wait contract.
4. Runtime-evidence contract tests still encode Chromium-specific console assumptions instead of browser-independent request/page evidence.
5. Sandbox cannot resolve the libpq service `stock_research_e2e_test`; production fallback is prohibited.

The security rescan closed the earlier bare-secret reporting root with zero potential real credentials and zero scan errors. That closure is retained, but it does not change the blockers above.

Next remediation plans:

- [Auth-disabled Dashboard shell contract](../superpowers/plans/2026-07-21-auth-disabled-dashboard-shell-contract.md)
- [Official strategy publication catalog](../superpowers/plans/2026-07-21-official-strategy-publication-catalog.md)
- [Firefox history consistency waits](../superpowers/plans/2026-07-21-firefox-history-consistency-waits.md)
- [Cross-browser runtime evidence contract](../superpowers/plans/2026-07-21-cross-browser-runtime-evidence-contract.md)
- [Real/Audit/Sandbox isolation and service bootstrap](../superpowers/plans/2026-07-20-playwright-real-audit-sandbox.md)

## Boundary And Rollback

Execution state during review: `disabled` (false/unset `STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED`). Boundary state during review: `disabled` (empty `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM`). Neither value was written to EOD, scheduler, or Dashboard service configuration.

If a later candidate rollout must be rolled back, the executable one-shot command is:

```bash
STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED=false STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM= rtk scripts/run_eod_auto_repair_cron.sh YYYY-MM-DD
```

For persistent rollback:

1. set `STOCK_RESEARCH_EOD_BROWSER_ACCEPTANCE_ENABLED=false` and clear `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM` in the actual external scheduler environment;
2. clear `STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM` in the Dashboard service environment and restart that service with the process manager that actually owns it;
3. restart the EOD scheduler process only if it caches environment values; this repository does not provide a managed scheduler unit, so no scheduler service name is asserted here;
4. preserve the last ready display date and all existing JSON, Markdown, HTML, manifest, trace, screenshot, and runtime-evidence files;
5. verify the display gate remains on the prior ready date and that no failed or unvalidated candidate is marked official.

This rollback does not delete evidence and does not rewrite the failed candidate as successful.

## Documentation Verification

Both injected command blocks above were executed directly from this Markdown file after editing and exited `0`. Final documentation verification also requires:

```bash
rtk git diff --check
```

The implementation, focused tests, cron wrapper, two operations runbooks, and this review are the authorized tracked changes for this Task 7 correction.
