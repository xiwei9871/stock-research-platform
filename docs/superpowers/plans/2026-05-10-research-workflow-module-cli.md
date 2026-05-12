# Research Workflow Module CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runnable module entrypoint for the TopN research workflow without touching the currently dirty main `stock-research` CLI file.

**Architecture:** Create `stock_research.research_workflow_cli` with its own argparse parser and `main()`. The module builds `TopNStrategyConfig`, calls `run_topn_research_workflow`, and prints stable pipe-delimited output for automation. Users can run it with `python -m stock_research.research_workflow_cli ...`; main CLI integration remains a later cleanup after unrelated `cli.py` changes are resolved.

**Tech Stack:** Python argparse, pytest, existing `research_workflow`.

---

## File Structure

- Create `src/stock_research/research_workflow_cli.py`: module CLI parser and main function.
- Create `tests/test_research_workflow_cli.py`: parser and main behavior tests.
- Modify `docs/daily-factor-pipeline-runbook.md`: document module command.

Do not modify `src/stock_research/cli.py` in this slice because it currently has unrelated uncommitted changes in the working tree.

## Task 1: Module CLI

**Files:**
- Create: `tests/test_research_workflow_cli.py`
- Create: `src/stock_research/research_workflow_cli.py`

- [ ] **Step 1: Write failing parser and main tests**

Test behavior: parser accepts workflow args; `main()` calls injected workflow function and prints report, metrics, equity, positions, latest equity, and total return lines.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_research_workflow_cli.py -q`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement CLI module**

Add `build_parser()` and `main(workflow_runner=run_topn_research_workflow)`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_research_workflow_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/research_workflow_cli.py tests/test_research_workflow_cli.py docs/superpowers/plans/2026-05-10-research-workflow-module-cli.md
git commit -m "Add research workflow module CLI"
```

## Task 2: Documentation And Verification

**Files:**
- Modify: `docs/daily-factor-pipeline-runbook.md`

- [ ] **Step 1: Update runbook**

Add the `python -m stock_research.research_workflow_cli` command and explain that it is a temporary module entrypoint until main CLI integration.

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/test_research_workflow_cli.py tests/test_research_workflow.py -q`

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run: `.venv/bin/pytest -q`

Expected: PASS.

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/daily-factor-pipeline-runbook.md
git commit -m "Document research workflow module CLI"
```

- [ ] **Step 5: Push**

Run: `git push`

Expected: branch pushes cleanly.

## Self-Review

- Spec coverage: provides a runnable workflow entrypoint without touching dirty `cli.py`.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: public names are `build_parser` and `main`.
