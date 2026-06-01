# P17 Shadow Decision Follow-up Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a review-only P17 follow-up queue from P16 shadow review decisions.

**Architecture:** Follow the P16 artifact/read-model/dashboard pattern. P17 reads P16 artifacts, writes local follow-up artifacts and independent `ops` read-model rows, then exposes the rows through read-only CLI/dashboard surfaces.

**Tech Stack:** Python, pandas, psycopg-style SQL helpers, pytest, FastAPI dashboard backend, React/Vite dashboard frontend, Vitest, Playwright.

---

## File Structure

- Create: `src/stock_research/operator_decision/shadow_follow_up_queue.py`
- Create: `src/stock_research/operator_decision/shadow_follow_up_queue_read_model.py`
- Create: `src/stock_research/operator_decision/p17_smoke.py`
- Create: `src/stock_research/dashboard/shadow_follow_up_queue.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/schema.py`
- Modify: `src/stock_research/dashboard/api.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `dashboard/src/api.ts`
- Create: `dashboard/src/components/ShadowFollowUpQueuePanel.tsx`
- Modify: dashboard app shell files that register inspector panels
- Create: `tests/test_operator_shadow_follow_up_queue.py`
- Create: `tests/test_operator_shadow_follow_up_queue_read_model.py`
- Create: `tests/test_p17_shadow_follow_up_queue_smoke.py`
- Create: `tests/test_dashboard_shadow_follow_up_queue.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_dashboard_app.py`
- Modify: dashboard frontend tests
- Create: `docs/quant_system/59_p17_shadow_decision_follow_up_queue_runbook.md`
- Create: `docs/quant_system/60_p17_shadow_decision_follow_up_queue_completion.md`

## Tasks

### Task 1: P17 Artifact Contract

- [ ] Write tests in `tests/test_operator_shadow_follow_up_queue.py` for:
  - `request_more_data` maps to `collect_more_evidence`
  - `open_research_follow_up` maps to `open_research_ticket`
  - JSON/CSV/Markdown artifacts are written
  - unsafe execution fields and unsafe safety flags are rejected
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_queue.py -q
```

Expected: fail because `stock_research.operator_decision.shadow_follow_up_queue` does not exist.

- [ ] Implement `shadow_follow_up_queue.py` with:
  - `FOLLOW_UP_STATUSES`
  - `DEFAULT_SHADOW_FOLLOW_UP_RULES`
  - `build_shadow_follow_up_queue`
  - `build_shadow_follow_up_queue_from_rows`
  - `write_shadow_follow_up_queue`
- [ ] Re-run the test command.

Expected: all P17 artifact contract tests pass.

- [ ] Commit:

```bash
git add src/stock_research/operator_decision/shadow_follow_up_queue.py tests/test_operator_shadow_follow_up_queue.py
git commit -m "feat: add p17 shadow follow-up queue contract"
```

### Task 2: P17 CLI Build Command

- [ ] Add parser and dispatch tests to `tests/test_factor_cli.py` for:
  - `p17-shadow-follow-up-queue --p16-decisions-json --run-id --follow-up-date --operator-id --output-dir`
  - output lines `p17_shadow_follow_up_queue|status|`, `items|`, `json|`, `items_csv|`, `markdown|`
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_factor_cli.py -k 'p17_shadow_follow_up_queue' -q
```

Expected: fail because the parser does not exist.

- [ ] Modify `src/stock_research/cli.py` to import P17 artifact helpers, add the parser, and dispatch the command.
- [ ] Re-run focused P17 CLI tests.

Expected: parser and dispatch tests pass.

- [ ] Commit:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add p17 shadow follow-up queue cli"
```

### Task 3: P17 Read Model

- [ ] Write tests for:
  - loading one P17 JSON artifact into one run row and item rows
  - safety rejection
  - directory import summary with fake DB cursor helpers
  - schema DDL table and index presence
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_queue_read_model.py tests/test_schema.py -k 'shadow_follow_up' -q
```

Expected: fail because read-model/schema support does not exist.

- [ ] Add `shadow_follow_up_queue_read_model.py`.
- [ ] Add `ops.operator_shadow_follow_up_run`, `ops.operator_shadow_follow_up_item`, and indexes to `schema.py`.
- [ ] Re-run focused read-model/schema tests.

Expected: tests pass.

- [ ] Commit:

```bash
git add src/stock_research/operator_decision/shadow_follow_up_queue_read_model.py src/stock_research/schema.py tests/test_operator_shadow_follow_up_queue_read_model.py tests/test_schema.py
git commit -m "feat: add p17 shadow follow-up queue read model"
```

### Task 4: P17 Import CLI

- [ ] Add parser and dispatch tests to `tests/test_factor_cli.py` for `p17-import-shadow-follow-up-queue --path --service`.
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_factor_cli.py -k 'p17_import_shadow_follow_up_queue' -q
```

Expected: fail because the parser does not exist.

- [ ] Wire `import_shadow_follow_up_queue` into `src/stock_research/cli.py`.
- [ ] Re-run CLI import tests.

Expected: tests pass.

- [ ] Commit:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add p17 shadow follow-up import cli"
```

### Task 5: Dashboard Read-only Panel

- [ ] Write backend tests for missing-table and populated `/api/shadow-follow-up-queue` responses.
- [ ] Write frontend tests for loading, empty, and populated follow-up panel states.
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_shadow_follow_up_queue.py tests/test_dashboard_app.py -k 'shadow_follow_up_queue or dashboard' -q
cd dashboard && pnpm test -- --run
```

Expected: fail because P17 dashboard files are not wired.

- [ ] Add dashboard backend loader and route.
- [ ] Add dashboard client and panel.
- [ ] Wire the panel into the existing dashboard app shell.
- [ ] Re-run backend and frontend tests.

Expected: tests pass and no unsafe action labels are introduced.

- [ ] Commit:

```bash
git add src/stock_research/dashboard/shadow_follow_up_queue.py src/stock_research/dashboard/api.py src/stock_research/dashboard/app.py tests/test_dashboard_shadow_follow_up_queue.py tests/test_dashboard_app.py dashboard/src dashboard/tests
git commit -m "feat: add p17 shadow follow-up dashboard"
```

### Task 6: Smoke, Runbook, Completion Review

- [ ] Write smoke test in `tests/test_p17_shadow_follow_up_queue_smoke.py`.
- [ ] Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_p17_shadow_follow_up_queue_smoke.py -q
```

Expected: fail because `p17_smoke.py` does not exist.

- [ ] Implement `p17_smoke.py` using the P16 smoke artifact as input.
- [ ] Add runbook and completion review docs.
- [ ] Run final verification:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_queue.py tests/test_operator_shadow_follow_up_queue_read_model.py tests/test_p17_shadow_follow_up_queue_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_follow_up_queue.py tests/test_dashboard_app.py -k 'shadow_follow_up_queue or p17_shadow_follow_up_queue or p17_import_shadow_follow_up_queue or dashboard' -q
cd dashboard && pnpm test
cd dashboard && pnpm build
cd dashboard && pnpm test:e2e
git diff --check
```

Expected: focused Python tests, dashboard tests, build, e2e, and whitespace checks pass.

- [ ] Commit:

```bash
git add src/stock_research/operator_decision/p17_smoke.py tests/test_p17_shadow_follow_up_queue_smoke.py docs/quant_system/59_p17_shadow_decision_follow_up_queue_runbook.md docs/quant_system/60_p17_shadow_decision_follow_up_queue_completion.md
git commit -m "docs: complete p17 shadow follow-up queue governance"
```

## Self-review Checklist

- Every P17 output is review-only.
- P17 writes only local artifacts and independent `ops.operator_shadow_follow_up_*` rows.
- P17 does not write production watchlist, scoring, factor approval, scheduler, broker, order, account, execution, cash, or position state.
- All P17 artifacts preserve P16/P15/P14 lineage.
- Dashboard is read-only and has no action controls.
