# P18 Shadow Follow-up Resolution Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a review-only P18 resolution review from P17 shadow follow-up queue items.

**Architecture:** Follow the P17 artifact/read-model/dashboard pattern. P18 reads P17 artifacts, writes local resolution artifacts and independent `ops` read-model rows, then exposes the rows through read-only CLI/dashboard surfaces.

**Tech Stack:** Python, pandas, psycopg-style SQL helpers, pytest, FastAPI dashboard backend, React/Vite dashboard frontend, Vitest, Playwright.

---

## File Structure

- Create: `src/stock_research/operator_decision/shadow_follow_up_resolution.py`
- Create: `src/stock_research/operator_decision/shadow_follow_up_resolution_read_model.py`
- Create: `src/stock_research/operator_decision/p18_smoke.py`
- Create: `src/stock_research/dashboard/shadow_follow_up_resolution.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/schema.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/api/types.ts`
- Create: `dashboard/src/components/ShadowFollowUpResolutionPanel.tsx`
- Modify: `dashboard/src/App.tsx`
- Create: `tests/test_operator_shadow_follow_up_resolution.py`
- Create: `tests/test_operator_shadow_follow_up_resolution_read_model.py`
- Create: `tests/test_p18_shadow_follow_up_resolution_smoke.py`
- Create: `tests/test_dashboard_shadow_follow_up_resolution.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_dashboard_app.py`
- Modify: dashboard frontend tests
- Create: `docs/quant_system/62_p18_shadow_follow_up_resolution_review_runbook.md`
- Create: `docs/quant_system/63_p18_shadow_follow_up_resolution_review_completion.md`

## Tasks

### Task 1: P18 Artifact Contract

- [ ] Write tests in `tests/test_operator_shadow_follow_up_resolution.py` for:
  - `collect_more_evidence` maps to `stale_unresolved`
  - `open_research_ticket` maps to `research_ticket_opened`
  - `observe_shadow_group` maps to `continue_observing`
  - `deprioritized` maps to `deprioritized_closed`
  - JSON/CSV/Markdown artifacts are written
  - unsafe execution fields and unsafe safety flags are rejected
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_resolution.py -q
```

Expected: fail because `stock_research.operator_decision.shadow_follow_up_resolution` does not exist.

- [ ] Implement `shadow_follow_up_resolution.py` with:
  - `RESOLUTION_STATUSES`
  - `DEFAULT_SHADOW_FOLLOW_UP_RESOLUTION_RULES`
  - `build_shadow_follow_up_resolution`
  - `build_shadow_follow_up_resolution_from_rows`
  - `write_shadow_follow_up_resolution`
- [ ] Re-run the test command.

Expected: all P18 artifact contract tests pass.

- [ ] Commit:

```bash
git add src/stock_research/operator_decision/shadow_follow_up_resolution.py tests/test_operator_shadow_follow_up_resolution.py
git commit -m "feat: add p18 shadow follow-up resolution contract"
```

### Task 2: P18 CLI Build Command

- [ ] Add parser and dispatch tests to `tests/test_factor_cli.py` for:
  - `p18-shadow-follow-up-resolution --p17-follow-up-json --run-id --resolution-date --operator-id --output-dir`
  - output lines `p18_shadow_follow_up_resolution|status|`, `items|`, `json|`, `items_csv|`, `markdown|`
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_factor_cli.py -k 'p18_shadow_follow_up_resolution' -q
```

Expected: fail because the parser does not exist.

- [ ] Modify `src/stock_research/cli.py` to import P18 artifact helpers, add the parser, and dispatch the command.
- [ ] Re-run focused P18 CLI tests.

Expected: parser and dispatch tests pass.

- [ ] Commit:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add p18 shadow follow-up resolution cli"
```

### Task 3: P18 Read Model And Import CLI

- [ ] Write tests for:
  - loading one P18 JSON artifact into one run row and item rows
  - safety rejection
  - directory import summary with fake DB cursor helpers
  - schema DDL table and index presence
  - `p18-import-shadow-follow-up-resolution --path --service`
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_resolution_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_follow_up_resolution or p18_import_shadow_follow_up_resolution' -q
```

Expected: fail because read-model/schema/import CLI support does not exist.

- [ ] Add `shadow_follow_up_resolution_read_model.py`.
- [ ] Add `ops.operator_shadow_follow_up_resolution_run`, `ops.operator_shadow_follow_up_resolution_item`, and indexes to `schema.py`.
- [ ] Wire `import_shadow_follow_up_resolution` into `src/stock_research/cli.py`.
- [ ] Re-run focused tests.

Expected: tests pass.

- [ ] Commit:

```bash
git add src/stock_research/operator_decision/shadow_follow_up_resolution_read_model.py src/stock_research/schema.py src/stock_research/cli.py tests/test_operator_shadow_follow_up_resolution_read_model.py tests/test_schema.py tests/test_factor_cli.py
git commit -m "feat: add p18 shadow follow-up resolution read model"
```

### Task 4: Dashboard Read-only Panel

- [ ] Write backend tests for missing-table and populated `/api/shadow-follow-up-resolution` responses.
- [ ] Write frontend tests for loading, empty, and populated resolution panel states.
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_shadow_follow_up_resolution.py tests/test_dashboard_app.py -k 'shadow_follow_up_resolution or dashboard' -q
cd dashboard && pnpm test -- --run
```

Expected: fail because P18 dashboard files are not wired.

- [ ] Add dashboard backend loader and route.
- [ ] Add dashboard client and panel.
- [ ] Wire the panel into the existing dashboard app shell.
- [ ] Re-run backend and frontend tests.

Expected: tests pass and no unsafe action labels are introduced.

- [ ] Commit:

```bash
git add src/stock_research/dashboard/shadow_follow_up_resolution.py src/stock_research/dashboard/app.py tests/test_dashboard_shadow_follow_up_resolution.py tests/test_dashboard_app.py dashboard/src dashboard/tests
git commit -m "feat: add p18 shadow follow-up resolution dashboard"
```

### Task 5: Smoke, Runbook, Completion Review

- [ ] Write smoke test in `tests/test_p18_shadow_follow_up_resolution_smoke.py`.
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_p18_shadow_follow_up_resolution_smoke.py -q
```

Expected: fail because `p18_smoke.py` does not exist.

- [ ] Implement `p18_smoke.py` using the P17 smoke artifact as input.
- [ ] Add runbook and completion review docs.
- [ ] Run final verification:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_resolution.py tests/test_operator_shadow_follow_up_resolution_read_model.py tests/test_p18_shadow_follow_up_resolution_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_follow_up_resolution.py tests/test_dashboard_app.py -k 'shadow_follow_up_resolution or p18_shadow_follow_up_resolution or p18_import_shadow_follow_up_resolution or dashboard' -q
cd dashboard && pnpm test
cd dashboard && pnpm build
cd dashboard && pnpm test:e2e
git diff --check
```

Expected: focused Python tests, dashboard tests, build, e2e, and whitespace checks pass.

- [ ] Commit:

```bash
git add src/stock_research/operator_decision/p18_smoke.py tests/test_p18_shadow_follow_up_resolution_smoke.py docs/quant_system/62_p18_shadow_follow_up_resolution_review_runbook.md docs/quant_system/63_p18_shadow_follow_up_resolution_review_completion.md
git commit -m "docs: complete p18 shadow follow-up resolution governance"
```

## Self-review Checklist

- Every P18 output is review-only.
- P18 writes only local artifacts and independent `ops.operator_shadow_follow_up_resolution_*` rows.
- P18 does not mutate P17 follow-up queue rows.
- P18 does not write production watchlist, scoring, factor approval, scheduler, broker, order, account, execution, cash, or position state.
- All P18 artifacts preserve P17/P16/P15/P14 lineage.
- Dashboard is read-only and has no action controls.
