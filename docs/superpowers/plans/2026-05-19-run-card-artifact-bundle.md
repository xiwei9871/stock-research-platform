# Run Card Artifact Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the shared run card writer to emit `metrics.json`, `config_snapshot.json`, `warnings.md`, and `data_coverage.json`, then wire those artifacts into the simplest three workflows.

**Architecture:** Keep all artifact writing centralized in `src/stock_research/run_card.py`. Do not let each workflow invent its own bundle format. Start with `daily_pipeline.py`, `reports/daily_research_report_cli.py`, and `vectorized_topn_backtest.py` because they already write run cards and have straightforward inputs.

**Tech Stack:** Python, pytest, pathlib, json, existing stock_research workflow modules.

---

### Task 1: Add failing tests for the shared artifact bundle

**Files:**
- Modify: `tests/test_run_card.py`

- [ ] **Step 1: Write the failing test**

Add tests that require `write_run_card(...)` to create:
- `metrics.json`
- `config_snapshot.json`
- `warnings.md`
- `data_coverage.json`

And require the returned dict to include:
- `metrics_json_path`
- `config_snapshot_path`
- `warnings_md_path`
- `data_coverage_json_path`

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_card.py -q`
Expected: FAIL because the shared writer does not yet create those files or return those keys.

- [ ] **Step 3: Write minimal implementation**

No implementation in this task.

- [ ] **Step 4: Run test to verify it passes**

No implementation yet.

- [ ] **Step 5: Commit**

```bash
git add tests/test_run_card.py
git commit -m "test: define run card artifact bundle outputs"
```

### Task 2: Implement shared artifact bundle support in run_card.py

**Files:**
- Modify: `src/stock_research/run_card.py`
- Test: `tests/test_run_card.py`

- [ ] **Step 1: Write the failing test**

Extend tests to verify:
- `metrics.json` contains the metrics payload
- `config_snapshot.json` contains the config payload
- `warnings.md` renders warning bullets or a stable empty message
- `data_coverage.json` preserves coverage fields

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_card.py -q`
Expected: FAIL because artifact bundle writing is incomplete.

- [ ] **Step 3: Write minimal implementation**

Update `write_run_card(...)` to:
- always create the 4 artifact files
- return the 4 artifact paths
- optionally accept `data_coverage` and `warnings`
- keep existing `run_card.json` / `run_card.md` behavior

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_run_card.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/run_card.py tests/test_run_card.py
git commit -m "feat: add run card artifact bundle writer"
```

### Task 3: Wire daily_pipeline.py to provide bundle fields

**Files:**
- Modify: `src/stock_research/daily_pipeline.py`
- Modify: `tests/test_daily_pipeline.py`

- [ ] **Step 1: Write the failing test**

Require:
- `result["run_card"]["metrics_json_path"]` exists
- `config_snapshot_path` exists
- `warnings_md_path` exists
- `data_coverage_json_path` exists

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_daily_pipeline.py -q`
Expected: FAIL because `daily_pipeline` is not passing enough information to the shared writer yet.

- [ ] **Step 3: Write minimal implementation**

Pass:
- config snapshot fields
- summary metrics
- simple warnings list
- basic data coverage summary from `top_scores`

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_daily_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/daily_pipeline.py tests/test_daily_pipeline.py
git commit -m "feat: attach artifact bundle to daily factor pipeline"
```

### Task 4: Wire daily_research_report_cli.py to provide bundle fields

**Files:**
- Modify: `src/stock_research/reports/daily_research_report_cli.py`
- Modify: `tests/test_daily_research_report_cli.py`

- [ ] **Step 1: Write the failing test**

Require the returned `run_card` to expose the 4 artifact bundle paths and ensure they exist.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_daily_research_report_cli.py -q`
Expected: FAIL because the daily research report workflow does not yet pass coverage/warning information into the bundle.

- [ ] **Step 3: Write minimal implementation**

Pass:
- report config snapshot
- top score / sector / feature row counts
- a small coverage dict
- empty warnings by default

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_daily_research_report_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/reports/daily_research_report_cli.py tests/test_daily_research_report_cli.py
git commit -m "feat: attach artifact bundle to daily research report run cards"
```

### Task 5: Wire vectorized_topn_backtest.py helper to provide bundle fields

**Files:**
- Modify: `src/stock_research/vectorized_topn_backtest.py`
- Modify: `tests/test_vectorized_topn_backtest.py`

- [ ] **Step 1: Write the failing test**

Require `write_vectorized_topn_run_card(...)` to return the 4 artifact bundle paths and ensure they exist.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`
Expected: FAIL because the helper does not yet feed coverage/warning information into the expanded bundle.

- [ ] **Step 3: Write minimal implementation**

Pass:
- config snapshot
- summary metrics
- coverage based on equity/positions/trades rows and observed dates
- empty warnings by default

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/vectorized_topn_backtest.py tests/test_vectorized_topn_backtest.py
git commit -m "feat: attach artifact bundle to vectorized backtest run cards"
```

### Task 6: Run focused regression suite

**Files:**
- No new files beyond previous tasks

- [ ] **Step 1: Write the failing test**

No new tests.

- [ ] **Step 2: Run test to verify it fails**

No dedicated red step.

- [ ] **Step 3: Write minimal implementation**

No code here; this is verification only.

- [ ] **Step 4: Run test to verify it passes**

Run:
- `.venv/bin/pytest tests/test_run_card.py -q`
- `.venv/bin/pytest tests/test_daily_pipeline.py -q`
- `.venv/bin/pytest tests/test_daily_research_report_cli.py -q`
- `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/run_card.py src/stock_research/daily_pipeline.py src/stock_research/reports/daily_research_report_cli.py src/stock_research/vectorized_topn_backtest.py tests/test_run_card.py tests/test_daily_pipeline.py tests/test_daily_research_report_cli.py tests/test_vectorized_topn_backtest.py
git commit -m "feat: add run card artifact bundles to core workflows"
```
