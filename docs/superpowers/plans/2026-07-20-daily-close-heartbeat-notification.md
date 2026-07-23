# Daily Close Heartbeat Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep daily-close heartbeat diagnostics out of Feishu while preserving compact final notifications, then run auto EOD repair for 2026-07-20 with exclusive BaoStock access.

**Architecture:** Route wrapper lifecycle and heartbeat lines to the existing per-run detail log, leaving stdout for the final Chinese summary only. Increase the OpenClaw command job's no-output timeout to match its six-hour execution timeout, then stop the overlapping finalize retry and run the locked auto EOD repair entrypoint.

**Tech Stack:** Bash, pytest, OpenClaw cron CLI, Python EOD repair pipeline, PostgreSQL-backed pipeline status.

---

### Task 1: Specify human-only stdout behavior

**Files:**
- Modify: `tests/test_daily_close_scripts.py:148`
- Test: `tests/test_daily_close_scripts.py`

- [ ] **Step 1: Replace the existing heartbeat stdout assertions with the desired behavior**

Rename the test and use these assertions after the command completes:

```python
def test_daily_close_minute5_wrapper_keeps_heartbeat_in_detail_log_only(tmp_path: Path) -> None:
    # existing fake Python and subprocess setup stays unchanged
    assert result.returncode == 0
    assert "daily_close_pipeline|started|stage=minute5" not in result.stdout
    assert "daily_close_pipeline|heartbeat|stage=minute5" not in result.stdout
    assert "股票日终阶段完成" in result.stdout
    detail_log = next(log_dir.glob("daily_close_pipeline_minute5_*.log"))
    detail_text = detail_log.read_text(encoding="utf-8")
    assert "daily_close_pipeline|started|stage=minute5" in detail_text
    assert "daily_close_pipeline|heartbeat|stage=minute5" in detail_text
    assert "completed|50|total|100" in detail_text
    assert '"status":"success"' in detail_text
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_daily_close_scripts.py::test_daily_close_minute5_wrapper_keeps_heartbeat_in_detail_log_only -q
```

Expected: FAIL because `started` and `heartbeat` still appear in stdout.

### Task 2: Route lifecycle diagnostics to the detail log

**Files:**
- Modify: `scripts/run_daily_close_pipeline_cron.sh:85`
- Test: `tests/test_daily_close_scripts.py`

- [ ] **Step 1: Move the started line to the detail log**

Replace:

```bash
echo "daily_close_pipeline|started|stage=${STAGE}|trade_date=${TRADE_DATE:-auto}|detail_log=${DETAIL_LOG}"
```

with:

```bash
echo "daily_close_pipeline|started|stage=${STAGE}|trade_date=${TRADE_DATE:-auto}|detail_log=${DETAIL_LOG}" >>"$DETAIL_LOG"
```

- [ ] **Step 2: Move heartbeat lines to the detail log**

Replace the heartbeat `echo` in the background loop with:

```bash
echo "daily_close_pipeline|heartbeat|stage=${STAGE}|trade_date=${TRADE_DATE:-auto}|elapsed_seconds=$((now_epoch-started_epoch))|last_progress=${last_progress:-waiting}" >>"$DETAIL_LOG"
```

- [ ] **Step 3: Run the focused test and verify GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_daily_close_scripts.py::test_daily_close_minute5_wrapper_keeps_heartbeat_in_detail_log_only -q
```

Expected: `1 passed`.

- [ ] **Step 4: Run the full wrapper test file**

Run:

```bash
rtk .venv/bin/pytest tests/test_daily_close_scripts.py -q
```

Expected: all tests pass.

### Task 3: Prevent OpenClaw no-output termination

**Files:**
- External configuration: OpenClaw cron job `3a2a36e5-c6da-46b3-aa5d-34b22bf4b2ff`

- [ ] **Step 1: Raise the no-output timeout to the command timeout**

Run:

```bash
rtk openclaw cron edit 3a2a36e5-c6da-46b3-aa5d-34b22bf4b2ff --no-output-timeout-seconds 21600
```

Expected: command succeeds and retains the existing schedule, command, Feishu destination, and failure alert.

- [ ] **Step 2: Verify the updated cron configuration**

Run:

```bash
rtk openclaw cron get 3a2a36e5-c6da-46b3-aa5d-34b22bf4b2ff
```

Expected fields:

```json
{
  "payload": {
    "noOutputTimeoutSeconds": 21600,
    "timeoutSeconds": 21600
  },
  "delivery": {
    "mode": "announce",
    "channel": "feishu"
  }
}
```

### Task 4: Hand repair ownership to auto EOD repair

**Files:**
- Existing runner: `scripts/run_eod_auto_repair_cron.sh`
- Outputs: `outputs/research/eod_auto_repair/2026-07-20/run_summary.json`
- Outputs: `outputs/research/eod_auto_repair/2026-07-20/run_report.md`
- Log: `logs/eod_auto_repair/2026-07-20.log`

- [ ] **Step 1: Stop the overlapping daily-close finalize retry**

Identify the wrapper and child with:

```bash
rtk proxy ps -axo pid,ppid,etime,state,command | rtk rg 'run_daily_close_finalize|scripts.daily_pipeline --stage retry_failed'
```

Send TERM to the retry child first, wait for the wrapper to exit, and verify neither process remains.

- [ ] **Step 2: Run auto EOD repair for the affected trade date**

Run:

```bash
rtk scripts/run_eod_auto_repair_cron.sh 2026-07-20
```

Expected: the lock is acquired, repair actions execute serially, and the command produces the summary and report artifacts.

- [ ] **Step 3: Verify repair artifacts and platform state**

Run:

```bash
rtk .venv/bin/python -m json.tool outputs/research/eod_auto_repair/2026-07-20/run_summary.json
rtk tail -n 120 logs/eod_auto_repair/2026-07-20.log
rtk .venv/bin/python -m stock_research.platform_ready --trade-date 2026-07-20 --json-output outputs/research/platform_ready_2026-07-20_post_repair.json
```

Expected: report actual action statuses; claim READY only if the fresh platform-ready command says READY.

### Task 5: Final regression and handoff

**Files:**
- Modify: `scripts/run_daily_close_pipeline_cron.sh`
- Modify: `tests/test_daily_close_scripts.py`

- [ ] **Step 1: Check the scoped diff**

Run:

```bash
rtk git diff --check -- scripts/run_daily_close_pipeline_cron.sh tests/test_daily_close_scripts.py
rtk git diff -- scripts/run_daily_close_pipeline_cron.sh tests/test_daily_close_scripts.py
```

Expected: only stdout routing and its regression test changed.

- [ ] **Step 2: Report evidence**

Report the focused/full test results, OpenClaw timeout value, repair outcome, platform-ready status, remaining gaps, and the fact that the 2022 historical backfill remains paused.
