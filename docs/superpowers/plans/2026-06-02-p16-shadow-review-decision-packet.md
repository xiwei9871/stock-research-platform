# P16 Shadow Review Decision Packet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a review-only P16 decision packet layer that consumes P15 shadow analytics reviews and records conservative group-level next-step decisions without writing production watchlist, scoring, scheduler, approval, broker, order, or trading state.

**Architecture:** P16 follows the P12-P15 artifact/read-model/dashboard pattern. It writes local JSON/CSV/Markdown decision artifacts, imports compact group decision rows into independent `ops.operator_shadow_review_decision_*` tables, and exposes a read-only dashboard summary.

**Tech Stack:** Python, pandas, argparse CLI, PostgreSQL SQL strings in `schema.py`, FastAPI dashboard API, React/Vite dashboard, Vitest, Playwright, pytest.

---

## File Structure

Create:

- `src/stock_research/operator_decision/shadow_review_decisions.py`: P16 decision contract, status mapping, artifact writer, Markdown renderer.
- `tests/test_operator_shadow_review_decisions.py`: contract, safety, mapping, and artifact tests.
- `src/stock_research/operator_decision/shadow_review_decisions_read_model.py`: P16 artifact loader and idempotent read-model importer.
- `tests/test_operator_shadow_review_decisions_read_model.py`: importer/read-model tests.
- `src/stock_research/operator_decision/p16_smoke.py`: synthetic P15-to-P16 smoke.
- `tests/test_p16_shadow_review_decisions_smoke.py`: smoke test.
- `src/stock_research/dashboard/shadow_review_decisions.py`: dashboard read-only query.
- `tests/test_dashboard_shadow_review_decisions.py`: dashboard backend query tests.
- `dashboard/src/components/ShadowReviewDecisionsPanel.tsx`: read-only P16 panel.
- `docs/quant_system/56_p16_shadow_review_decision_packet_runbook.md`: P16 runbook.
- `docs/quant_system/57_p16_shadow_review_decision_packet_completion.md`: P16 completion review.

Modify:

- `src/stock_research/cli.py`: add `p16-shadow-review-decisions` and `p16-import-shadow-review-decisions`.
- `src/stock_research/schema.py`: add `ops.operator_shadow_review_decision_run`, `ops.operator_shadow_review_decision_group`, and indexes.
- `tests/test_schema.py`: assert P16 tables/indexes.
- `tests/test_factor_cli.py`: CLI parser/dispatch tests.
- `src/stock_research/dashboard/app.py`: add `GET /api/shadow-review-decisions`.
- `tests/test_dashboard_app.py`: route test.
- `dashboard/src/api/types.ts`: add `ShadowReviewDecisionRow`.
- `dashboard/src/api/client.ts`: add `fetchShadowReviewDecisions`.
- `dashboard/src/App.tsx`: load and render P16 panel.
- `dashboard/tests/client.test.ts`: client test.
- `dashboard/tests/app-shell.test.tsx`: app panel/loading/empty tests.
- `dashboard/tests/app-smoke.spec.ts`: browser smoke route/mock/assertions.

Do not modify:

- `watchlist.watchlist_daily_signal` write paths.
- `factor.stock_score_daily` write paths.
- `factor.factor_approval` write paths.
- scheduler wrappers.
- trading/broker/order/account/position modules.
- unrelated watchlist/trend/factor/strong-winner/mid-trend dirty files in the main worktree.

---

### Task 0: P16 Scope Freeze Commit

**Files:**

- Existing: `docs/quant_system/55_p16_shadow_review_decision_packet_scope_freeze.md`
- Existing: `docs/superpowers/specs/2026-06-02-p16-shadow-review-decision-packet-design.md`

- [ ] **Step 1: Verify the scope freeze document exists**

Run:

```bash
test -s docs/quant_system/55_p16_shadow_review_decision_packet_scope_freeze.md
```

Expected: exit code `0`.

- [ ] **Step 2: Verify the design document exists**

Run:

```bash
test -s docs/superpowers/specs/2026-06-02-p16-shadow-review-decision-packet-design.md
```

Expected: exit code `0`.

- [ ] **Step 3: Confirm the design commit is present**

Run:

```bash
git log --oneline -1
```

Expected output includes:

```text
docs: add p16 shadow review decision packet design
```

---

### Task 1: Shadow Review Decision Contract

**Files:**

- Create: `src/stock_research/operator_decision/shadow_review_decisions.py`
- Create: `tests/test_operator_shadow_review_decisions.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_operator_shadow_review_decisions.py` with tests that:

- import `DECISION_STATUSES`, `build_shadow_review_decisions`, `build_shadow_review_decisions_from_rows`, and `write_shadow_review_decisions`
- create one P15 review row for each allowed P15 review status
- assert the mapping:
  - `needs_more_data` -> `request_more_data`
  - `investigate_data_quality` -> `request_more_data`
  - `research_follow_up_candidate` -> `open_research_follow_up`
  - `deprioritize_review` -> `deprioritize_shadow_group`
  - `continue_observing` -> `continue_shadow_observation`
- assert all output safety fields are conservative
- assert unsafe execution-like fields such as `order_id` are rejected
- assert JSON, CSV, and Markdown artifacts are written

Use this minimum fixture shape:

```python
def _review_group(**overrides):
    row = {
        "review_group_id": "operator_shadow_analytics_review:p15-run:abc",
        "run_id": "p15-shadow-analytics-review-2026-06-30-2026-08-29",
        "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:p14:trend-ready",
        "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
        "group_key": "trend_shadow|shadow_ready",
        "shadow_layer": "trend_shadow",
        "shadow_status": "shadow_ready",
        "sample_count": 30,
        "complete_count": 28,
        "insufficient_data_count": 2,
        "review_status": "research_follow_up_candidate",
        "review_bucket": "follow_up",
        "evidence_summary": "adequate positive evidence",
        "risk_notes": "requires separate research validation",
        "next_research_question": "Should this group be researched further?",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }
    row.update(overrides)
    return row
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_review_decisions.py -q
```

Expected: fail during collection with `ModuleNotFoundError` for `stock_research.operator_decision.shadow_review_decisions`.

- [ ] **Step 3: Implement minimal decision contract**

Create `src/stock_research/operator_decision/shadow_review_decisions.py` with:

- `DECISION_STATUSES`
- `DEFAULT_SHADOW_REVIEW_DECISION_RULES`
- `build_shadow_review_decisions_from_rows(rows, run_id, decision_date, operator_id)`
- `build_shadow_review_decisions(p15_review, run_id, decision_date, operator_id)`
- `write_shadow_review_decisions(decisions, output_dir)`
- private helpers for safety validation, mapping, IDs, JSON-safe conversion, CSV columns, and Markdown rendering

Use `hashlib.sha256(f"{run_id}|{source_p15_review_group_id}|{decision_status}".encode("utf-8")).hexdigest()[:16]` for the group digest and prefix IDs with `operator_shadow_review_decision:`.

- [ ] **Step 4: Run focused contract tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_review_decisions.py -q
```

Expected: all P16 contract tests pass.

- [ ] **Step 5: Commit contract**

Run:

```bash
git add src/stock_research/operator_decision/shadow_review_decisions.py tests/test_operator_shadow_review_decisions.py
git commit -m "feat: add p16 shadow review decision contract"
```

Expected: commit succeeds and contains only P16 contract files.

---

### Task 2: Shadow Review Decision Artifact CLI

**Files:**

- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests to `tests/test_factor_cli.py` that:

- parse `p16-shadow-review-decisions`
- require `--p15-review-json`, `--run-id`, `--decision-date`, `--operator-id`, and `--output-dir`
- monkeypatch `build_shadow_review_decisions` and `write_shadow_review_decisions`
- assert output lines:
  - `p16_shadow_review_decisions|status|`
  - `p16_shadow_review_decisions|groups|`
  - `p16_shadow_review_decisions|json|`
  - `p16_shadow_review_decisions|groups_csv|`
  - `p16_shadow_review_decisions|markdown|`

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_factor_cli.py -k 'p16_shadow_review_decisions' -q
```

Expected: tests fail because the parser and dispatch branch do not exist.

- [ ] **Step 3: Implement artifact CLI**

Modify `src/stock_research/cli.py`:

- import `build_shadow_review_decisions` and `write_shadow_review_decisions`
- add parser `p16-shadow-review-decisions`
- load the P15 JSON artifact with `json.loads(Path(args.p15_review_json).read_text(encoding="utf-8"))`
- dispatch to the builder and writer
- print the five `p16_shadow_review_decisions|...` lines

- [ ] **Step 4: Run contract and CLI tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_review_decisions.py tests/test_factor_cli.py -k 'shadow_review_decisions or p16_shadow_review_decisions' -q
```

Expected: focused P16 contract and artifact CLI tests pass.

- [ ] **Step 5: Commit artifact CLI**

Run:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add p16 shadow review decision cli"
```

Expected: commit succeeds and staged CLI diff contains only P16 parser/import/dispatch hunks.

---

### Task 3: Shadow Review Decision Read Model

**Files:**

- Create: `src/stock_research/operator_decision/shadow_review_decisions_read_model.py`
- Create: `tests/test_operator_shadow_review_decisions_read_model.py`
- Modify: `src/stock_research/schema.py`
- Modify: `tests/test_schema.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing read-model tests**

Create read-model tests that:

- load a P16 JSON artifact into one run row and one group row
- assert conservative safety fields are forced in both rows
- assert source P15 and P14 lineage fields are preserved
- assert importer upserts run and group rows idempotently
- assert directory import sorts `operator_shadow_review_decisions_*.json`

- [ ] **Step 2: Write failing schema and import CLI tests**

Modify:

- `tests/test_schema.py` to assert `ops.operator_shadow_review_decision_run`, `ops.operator_shadow_review_decision_group`, `idx_operator_shadow_review_decision_group_date`, and `idx_operator_shadow_review_decision_group_status`
- `tests/test_factor_cli.py` to cover `p16-import-shadow-review-decisions --path outputs/p16 --service stock_research_test`

- [ ] **Step 3: Run focused tests and verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_review_decisions_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_review_decision or p16_import_shadow_review_decisions' -q
```

Expected: tests fail because the read-model module, schema tables, and import CLI do not exist.

- [ ] **Step 4: Implement read model, schema, and import CLI**

Implement:

- `load_shadow_review_decision_read_model_rows(path)`
- `import_shadow_review_decisions(path, service=SETTINGS.research_service)`
- run-table upsert into `ops.operator_shadow_review_decision_run`
- group-table upsert into `ops.operator_shadow_review_decision_group`
- schema DDL and indexes
- CLI parser `p16-import-shadow-review-decisions`
- dispatch output lines:
  - `p16_import_shadow_review_decisions|imported|`
  - `p16_import_shadow_review_decisions|groups|`
  - `p16_import_shadow_review_decisions|runs|`

- [ ] **Step 5: Run focused read-model tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_review_decisions.py tests/test_operator_shadow_review_decisions_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_review_decision or p16_shadow_review_decisions or p16_import_shadow_review_decisions' -q
```

Expected: focused P16 contract/read-model/schema/CLI tests pass.

- [ ] **Step 6: Commit read model**

Run:

```bash
git add src/stock_research/operator_decision/shadow_review_decisions_read_model.py tests/test_operator_shadow_review_decisions_read_model.py src/stock_research/schema.py tests/test_schema.py src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add p16 shadow review decision read model"
```

Expected: commit succeeds and contains only P16 read-model/schema/import CLI changes.

---

### Task 4: Dashboard Read-Only Shadow Review Decisions

**Files:**

- Create: `src/stock_research/dashboard/shadow_review_decisions.py`
- Create: `tests/test_dashboard_shadow_review_decisions.py`
- Create: `dashboard/src/components/ShadowReviewDecisionsPanel.tsx`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_app.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/tests/client.test.ts`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Modify: `dashboard/tests/app-smoke.spec.ts`

- [ ] **Step 1: Write failing backend dashboard tests**

Tests should assert:

- missing P16 tables return `[]`
- returned rows force conservative safety flags
- `GET /api/shadow-review-decisions` returns `{ "items": [...] }`
- no route mutates production tables

- [ ] **Step 2: Write failing frontend tests**

Tests should assert:

- client calls `/api/shadow-review-decisions`
- app renders loading, empty, and populated P16 decision states
- rendered text includes decision status and required next action
- forbidden labels such as `Promote`, `Trade`, `Order`, `Write Watchlist`, `Mutate Score`, and `Scheduler` do not appear in the P16 panel

- [ ] **Step 3: Run dashboard tests and verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_shadow_review_decisions.py tests/test_dashboard_app.py -k 'shadow_review_decision or dashboard' -q
cd dashboard && pnpm test
```

Expected: tests fail because the P16 dashboard backend/client/panel do not exist.

- [ ] **Step 4: Implement dashboard backend and frontend**

Implement:

- `load_shadow_review_decision_summary(start_date, end_date, limit, service)`
- FastAPI route `/api/shadow-review-decisions`
- TypeScript type `ShadowReviewDecisionRow`
- client function `fetchShadowReviewDecisions`
- `ShadowReviewDecisionsPanel`
- app state, load call, and render wiring

The panel must be read-only and must not add edit, promote, write, score,
scheduler, trade, broker, or order controls.

- [ ] **Step 5: Run dashboard verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_shadow_review_decisions.py tests/test_dashboard_app.py -k 'shadow_review_decision or dashboard' -q
cd dashboard && pnpm test
cd dashboard && pnpm build
cd dashboard && pnpm test:e2e
```

Expected: backend dashboard tests, Vitest, Vite build, and Playwright smoke pass.

- [ ] **Step 6: Commit dashboard**

Run:

```bash
git add src/stock_research/dashboard/shadow_review_decisions.py tests/test_dashboard_shadow_review_decisions.py src/stock_research/dashboard/app.py tests/test_dashboard_app.py dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/App.tsx dashboard/src/components/ShadowReviewDecisionsPanel.tsx dashboard/tests/client.test.ts dashboard/tests/app-shell.test.tsx dashboard/tests/app-smoke.spec.ts
git commit -m "feat: add p16 shadow review decision dashboard"
```

Expected: commit succeeds and contains only P16 dashboard changes.

---

### Task 5: Smoke, Runbook, Completion Review

**Files:**

- Create: `src/stock_research/operator_decision/p16_smoke.py`
- Create: `tests/test_p16_shadow_review_decisions_smoke.py`
- Create: `docs/quant_system/56_p16_shadow_review_decision_packet_runbook.md`
- Create: `docs/quant_system/57_p16_shadow_review_decision_packet_completion.md`

- [ ] **Step 1: Write failing smoke test**

Create a smoke test that:

- calls `build_p15_shadow_analytics_review_smoke(tmp_path)`
- loads the generated P15 review artifact
- builds P16 decision artifacts
- imports P16 read-model rows using fake cursor helpers
- asserts one decision group row exists
- asserts `manual_review_required is True`
- asserts `auto_trade_enabled`, `production_watchlist_enabled`, and `production_write_enabled` are `False`

- [ ] **Step 2: Run smoke test and verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_p16_shadow_review_decisions_smoke.py -q
```

Expected: fail because `stock_research.operator_decision.p16_smoke` does not exist.

- [ ] **Step 3: Implement P16 smoke**

Create `src/stock_research/operator_decision/p16_smoke.py` with:

- `build_p16_shadow_review_decisions_smoke(output_dir)`
- call to `build_p15_shadow_analytics_review_smoke(output_dir)`
- build P16 decisions with run ID `p16-smoke-shadow-review-decisions-2026-08-29`
- write P16 artifacts under `output_dir / "p16"`
- load P16 read-model rows
- return artifact paths, group counts, decision statuses, decision buckets, source run IDs, and safety flags

- [ ] **Step 4: Run smoke tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_p16_shadow_review_decisions_smoke.py tests/test_p15_shadow_analytics_review_smoke.py -q
```

Expected: P16/P15 smoke tests pass.

- [ ] **Step 5: Run operational smoke command**

Run:

```bash
rm -rf /tmp/stock_research_p16_smoke
/Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p16_smoke import build_p16_shadow_review_decisions_smoke
result = build_p16_shadow_review_decisions_smoke(Path('/tmp/stock_research_p16_smoke'))
print(f"p16_smoke|p15_shadow_analytics_review|{result['p15_shadow_analytics_review_json_path']}")
print(f"p16_smoke|p16_shadow_review_decisions|{result['p16_shadow_review_decisions_json_path']}")
print(f"p16_smoke|groups_csv|{result['p16_shadow_review_decisions_groups_csv_path']}")
print(f"p16_smoke|markdown|{result['p16_shadow_review_decisions_markdown_path']}")
print(f"p16_smoke|source_group_count|{result['source_group_count']}")
print(f"p16_smoke|decision_group_count|{result['decision_group_count']}")
print(f"p16_smoke|read_model_groups|{result['read_model_group_count']}")
print(f"p16_smoke|decision_statuses|{','.join(result['decision_statuses'])}")
print(f"p16_smoke|decision_buckets|{','.join(result['decision_buckets'])}")
print(f"p16_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p16_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p16_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p16_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Expected: output paths exist, one source group and one decision group are recorded, and all safety flags remain conservative.

- [ ] **Step 6: Write runbook and completion review**

Create:

- `docs/quant_system/56_p16_shadow_review_decision_packet_runbook.md`
- `docs/quant_system/57_p16_shadow_review_decision_packet_completion.md`

Include:

- P16 purpose and safety boundary
- artifact CLI command
- import CLI command
- dashboard endpoint
- synthetic smoke command and observed output from Step 5
- delivered capabilities for P16-0 through P16-5
- verification commands and exact result counts
- known non-P16 workspace dirty file note

- [ ] **Step 7: Run final P16 verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_review_decisions.py tests/test_operator_shadow_review_decisions_read_model.py tests/test_p16_shadow_review_decisions_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_review_decisions.py tests/test_dashboard_app.py -k 'shadow_review_decision or p16_shadow_review_decisions or p16_import_shadow_review_decisions or dashboard' -q
cd dashboard && pnpm test
cd dashboard && pnpm build
cd dashboard && pnpm test:e2e
git diff --check
```

Expected:

- Python P16-focused tests pass.
- Vitest passes.
- Vite build passes.
- Playwright smoke passes.
- `git diff --check` exits `0`.

- [ ] **Step 8: Commit smoke and docs**

Run:

```bash
git add src/stock_research/operator_decision/p16_smoke.py tests/test_p16_shadow_review_decisions_smoke.py docs/quant_system/56_p16_shadow_review_decision_packet_runbook.md docs/quant_system/57_p16_shadow_review_decision_packet_completion.md
git commit -m "docs: complete p16 shadow review decision governance"
```

Expected: commit succeeds and contains only P16 smoke/runbook/completion files.

---

## Final Verification Before P16 Completion Claim

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_review_decisions.py tests/test_operator_shadow_review_decisions_read_model.py tests/test_p16_shadow_review_decisions_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_review_decisions.py tests/test_dashboard_app.py -k 'shadow_review_decision or p16_shadow_review_decisions or p16_import_shadow_review_decisions or dashboard' -q
cd dashboard && pnpm test
cd dashboard && pnpm build
cd dashboard && pnpm test:e2e
git diff --check
git status --short --branch
```

Expected:

- P16 commits appear on branch `p16-shadow-review-decision-packet`.
- P16 worktree contains only P16-owned changes.
- Main worktree dirty non-P16 files remain untouched.
- No production watchlist, scoring, approval, scheduler, broker, order, account, cash, execution, or position writes are added.
