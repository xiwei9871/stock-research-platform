# Run Card / Evidence Trail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared run_card artifact layer that writes stable JSON/Markdown artifacts and lets factor evaluation, backtest, and daily report workflows reference the same evidence format.

**Architecture:** Add one focused `run_card.py` module for building and writing artifact files. Keep existing database run stores (`report_run_store`, `daily_job_run_store`, `factor_eval_store`) in place and only extend the calling workflows to include run_card paths in metadata or result payloads. Start with `factor_eval_batch.py`, `vectorized_topn_backtest.py`, and `reports/daily_research_report_cli.py`.

**Tech Stack:** Python, pytest, pathlib, json, pandas.

---

### Task 1: Define failing tests for the shared run_card writer

**Files:**
- Create: `tests/test_run_card.py`

- [ ] **Step 1: Write the failing test**

```python
from stock_research import run_card


def test_write_run_card_writes_json_markdown_and_manifest(tmp_path):
    result = run_card.write_run_card(
        output_dir=tmp_path,
        run_type="factor_eval",
        run_id="run-1",
        title="Factor Eval",
        config={"factor_name": "ret_20"},
        metrics={"mean_ic": 0.03},
        artifact_paths={"report": "/tmp/report.md"},
    )
    assert (tmp_path / "run_card.json").exists()
    assert (tmp_path / "run_card.md").exists()
    assert (tmp_path / "evidence" / "manifest.json").exists()
    assert result["run_card_json"].endswith("run_card.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_card.py -q`
Expected: FAIL because `run_card` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

No implementation in this task.

- [ ] **Step 4: Run test to verify it passes**

No implementation yet.

- [ ] **Step 5: Commit**

```bash
git add tests/test_run_card.py
git commit -m "test: define shared run card artifact expectations"
```

### Task 2: Implement the shared run_card module

**Files:**
- Create: `src/stock_research/run_card.py`
- Test: `tests/test_run_card.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_build_run_card_markdown_includes_config_metrics_and_artifacts():
    payload = run_card.build_run_card_payload(
        run_type="vectorized_backtest",
        run_id="backtest-1",
        title="Vectorized Backtest",
        config={"top_n": 20},
        metrics={"total_return": 0.12},
        artifact_paths={"equity_curve": "/tmp/equity.csv"},
    )
    markdown = run_card.render_run_card_markdown(payload)
    assert "Vectorized Backtest" in markdown
    assert "top_n" in markdown
    assert "total_return" in markdown
    assert "equity_curve" in markdown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_card.py -q`
Expected: FAIL because the module and helpers do not exist.

- [ ] **Step 3: Write minimal implementation**

Implement:
- `build_run_card_payload(...)`
- `render_run_card_markdown(...)`
- `write_run_card(...)`

The writer should create:
- `run_card.json`
- `run_card.md`
- `evidence/manifest.json`

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_run_card.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/run_card.py tests/test_run_card.py
git commit -m "feat: add shared run card writer"
```

### Task 3: Wire run_card into factor evaluation batch

**Files:**
- Modify: `src/stock_research/factor_eval_batch.py`
- Modify: `tests/test_factor_eval_batch.py`

- [ ] **Step 1: Write the failing test**

Add a test that verifies:
- `run_factor_gate_batch(..., output_dir=tmp_path)` writes one run_card directory per factor
- `store_factor_eval_run(...)` receives `metrics` containing run_card path or artifact summary

```python
def test_run_factor_gate_batch_writes_run_card_artifacts(monkeypatch, tmp_path):
    ...
    result = factor_eval_batch.run_factor_gate_batch(..., output_dir=tmp_path)
    assert (tmp_path / "ret_20" / "run_card.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_factor_eval_batch.py -q`
Expected: FAIL because output_dir support and run_card writing are missing.

- [ ] **Step 3: Write minimal implementation**

Add optional `output_dir` to `run_factor_gate_batch(...)`. When present, write a per-factor run card and include its path in:
- returned row payload
- `metrics["artifacts"]`

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_factor_eval_batch.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factor_eval_batch.py tests/test_factor_eval_batch.py
git commit -m "feat: add factor eval run cards"
```

### Task 4: Wire run_card into vectorized backtest results

**Files:**
- Modify: `src/stock_research/vectorized_topn_backtest.py`
- Modify: `tests/test_vectorized_topn_backtest.py`

- [ ] **Step 1: Write the failing test**

Add a test that verifies:
- a helper like `write_vectorized_topn_run_card(...)` writes the three expected artifacts
- result summary fields are included in the run_card payload

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`
Expected: FAIL because run_card writing is not implemented.

- [ ] **Step 3: Write minimal implementation**

Add a small helper rather than changing the core simulation contract:
- `write_vectorized_topn_run_card(result, output_dir)`

This keeps the backtest engine pure and avoids unexpected file writes inside `run_vectorized_topn_backtest(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/vectorized_topn_backtest.py tests/test_vectorized_topn_backtest.py
git commit -m "feat: add vectorized backtest run cards"
```

### Task 5: Wire run_card into daily research report workflow

**Files:**
- Modify: `src/stock_research/reports/daily_research_report_cli.py`
- Modify: `tests/test_daily_research_report_cli.py`
- Modify: `src/stock_research/report_run_store.py`
- Modify: `tests/test_report_run_store.py`

- [ ] **Step 1: Write the failing test**

Add a test that verifies:
- `run_daily_research_report(..., record_run=True)` writes a run_card artifact under the reports directory
- `record_report_run(...)` receives metadata containing run_card paths

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_daily_research_report_cli.py tests/test_report_run_store.py -q`
Expected: FAIL because no shared run_card artifact is produced yet.

- [ ] **Step 3: Write minimal implementation**

After `write_daily_research_reports(...)`, create a run_card directory under the report output root and include its paths in:
- returned result payload
- `record_report_run(..., metadata=...)`

Do not alter the `report.report_run` schema.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_daily_research_report_cli.py tests/test_report_run_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/reports/daily_research_report_cli.py src/stock_research/report_run_store.py tests/test_daily_research_report_cli.py tests/test_report_run_store.py
git commit -m "feat: attach run cards to daily research reports"
```

### Task 6: Update docs and run focused regression suite

**Files:**
- Modify: `docs/quant_system/05_mvp_implementation_plan.md`
- Optional Create: `docs/quant_system/11_run_card_evidence_trail.md`

- [ ] **Step 1: Write the failing test**

No code test required beyond the focused regression suite.

- [ ] **Step 2: Run test to verify it fails**

No dedicated red test in this doc task.

- [ ] **Step 3: Write minimal implementation**

Add a short status note that P0 run_card has started landing and list the first wired workflows.

- [ ] **Step 4: Run test to verify it passes**

Run:
- `.venv/bin/pytest tests/test_run_card.py -q`
- `.venv/bin/pytest tests/test_factor_eval_batch.py -q`
- `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`
- `.venv/bin/pytest tests/test_daily_research_report_cli.py tests/test_report_run_store.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/quant_system/05_mvp_implementation_plan.md docs/quant_system/11_run_card_evidence_trail.md
git commit -m "docs: record run card evidence trail rollout"
```

### Coverage Check

This plan covers:
- shared artifact writer
- factor evaluation run cards
- vectorized backtest run cards
- daily research report run cards
- preserving existing DB run stores while enriching metadata

It intentionally does not cover:
- `ops.daily_job_run` schema redesign
- `portfolio_backtest.py` or `retention_backtest.py` run cards
- automatic evidence ingestion into PostgreSQL
- full report/backtest/eval run unification in one DB table
