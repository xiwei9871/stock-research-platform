# TopN Research Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the strategy lifecycle, vectorized TopN backtest, and performance tear sheet into one reusable research workflow.

**Architecture:** Add a thin orchestration module that calls `run_topn_strategy_lifecycle`, then writes a performance tear sheet from the resulting backtest. The module returns the lifecycle context, report paths, and a compact summary. This keeps CLI integration optional and avoids touching current unrelated CLI changes.

**Tech Stack:** Python, pandas, pytest, existing `strategy_lifecycle` and `performance_tearsheet`.

---

## File Structure

- Create `src/stock_research/research_workflow.py`: workflow dataclass and `run_topn_research_workflow`.
- Create `tests/test_research_workflow.py`: dependency-injected unit tests.
- Modify `docs/astock-research-platform-v1.md`: record the end-to-end research workflow.

Do not modify `src/stock_research/cli.py` in this slice because it currently has unrelated uncommitted changes in the working tree.

## Task 1: Workflow Orchestration

**Files:**
- Create: `tests/test_research_workflow.py`
- Create: `src/stock_research/research_workflow.py`

- [ ] **Step 1: Write failing workflow test**

Test behavior: `run_topn_research_workflow` calls an injected lifecycle runner, writes an injected tear sheet using the lifecycle result, and returns context, report paths, and summary.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_research_workflow.py::test_run_topn_research_workflow_runs_lifecycle_and_writes_tearsheet -q`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement minimal workflow**

Add:
- `TopNResearchWorkflowResult`
- `run_topn_research_workflow`

- [ ] **Step 4: Run workflow test**

Run: `.venv/bin/pytest tests/test_research_workflow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/research_workflow.py tests/test_research_workflow.py docs/superpowers/plans/2026-05-10-topn-research-workflow.md
git commit -m "Add TopN research workflow"
```

## Task 2: Documentation And Verification

**Files:**
- Modify: `docs/astock-research-platform-v1.md`

- [ ] **Step 1: Update platform doc**

Add a current-progress bullet saying lifecycle, vectorized backtest, and tear sheet can now be invoked through one workflow module.

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/test_research_workflow.py tests/test_strategy_lifecycle.py tests/test_performance_tearsheet.py -q`

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run: `.venv/bin/pytest -q`

Expected: PASS.

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/astock-research-platform-v1.md
git commit -m "Document TopN research workflow"
```

- [ ] **Step 5: Push**

Run: `git push`

Expected: branch pushes cleanly.

## Self-Review

- Spec coverage: connects Track 3, Track 4, and Track 5 without adding CLI scope.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: public names are `TopNResearchWorkflowResult` and `run_topn_research_workflow`.
