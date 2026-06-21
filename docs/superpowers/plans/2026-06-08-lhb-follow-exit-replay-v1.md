# LHB Follow Exit Replay V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a historical replay report that studies which LHB short-term setups can be followed and which should be avoided or exited.

**Architecture:** Reuse `build_lhb_risk_feature_diagnostics` to create event-level LHB detail, then add a replay classifier that assigns `lhb_replay_action` and `lhb_replay_reason` without changing live risk scores. Output a detail CSV, grouped effectiveness CSV, and Markdown report. Add a CLI wrapper.

**Tech Stack:** Python, pandas, argparse, pytest.

---

### Task 1: Replay Classifier

**Files:**
- Modify: `tests/test_lhb_data.py`
- Modify: `src/stock_research/lhb_data.py`

- [ ] **Step 1: Write failing tests**

Add tests for:

```python
def test_build_lhb_follow_exit_replay_classifies_follow_exit_and_avoid(tmp_path):
    result = lhb_data.build_lhb_follow_exit_replay_v1(...)
    detail = result["replay_detail"].set_index("case_id")
    assert detail.loc["c_success", "lhb_replay_action"] == "follow_candidate"
    assert detail.loc["c_failed_wave", "lhb_replay_action"] == "exit_confirmation"
    assert detail.loc["c_a_kill", "lhb_replay_action"] == "avoid_withdrawal"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_lhb_data.py::test_build_lhb_follow_exit_replay_classifies_follow_exit_and_avoid -q
```

Expected: FAIL because `build_lhb_follow_exit_replay_v1` is missing.

- [ ] **Step 3: Implement classifier and outputs**

Add:

- `LHB_FOLLOW_EXIT_REPLAY_COLUMNS`
- `build_lhb_follow_exit_replay_v1(...)`
- `_classify_lhb_follow_exit_row(...)`
- `_build_lhb_follow_exit_effectiveness(...)`
- `_lhb_follow_exit_markdown(...)`

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_lhb_data.py::test_build_lhb_follow_exit_replay_classifies_follow_exit_and_avoid -q
```

Expected: PASS.

### Task 2: CLI

**Files:**
- Modify: `tests/test_lhb_data.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/lhb_data.py`

- [ ] **Step 1: Write failing CLI test**

Verify:

```bash
stock-research lhb-follow-exit-replay-v1 --case-path cases.csv --lhb-features-path features.csv --alignment-path alignment.csv --output-dir out
```

- [ ] **Step 2: Implement parser and dispatch**

Add `run_lhb_follow_exit_replay_v1(...)`, parser args, import, and print output paths.

- [ ] **Step 3: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_lhb_data.py -k "lhb_follow_exit_replay" -q
```

Expected: PASS.

### Task 3: Verification

**Files:**
- All modified files.

- [ ] Run:

```bash
.venv/bin/pytest tests/test_lhb_data.py tests/test_watchlist_diagnostics.py tests/test_risk_watch_split.py -q
```

Expected: PASS.
