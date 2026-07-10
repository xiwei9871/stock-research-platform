# EOD Auto Repair Observable Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the EOD auto-repair wrapper observable to OpenClaw throughout long runs and guarantee child/heartbeat cleanup with truthful exit status.

**Status:** Implemented and operationally verified on 2026-07-11.

**Architecture:** Keep Python repair output in the existing detail log while a Bash supervisor emits compact stdout start and heartbeat records. The wrapper owns the repair child and a separate interruptible heartbeat loop, forwards TERM/INT, reaps both processes, and returns the repair child's exit code.

**Tech Stack:** Bash, Python subprocess-based pytest, OpenClaw command cron.

---

## File Map

- Modify `scripts/run_platform_ready_check_cron.sh`: child supervision, stdout heartbeat, signal forwarding, cleanup, and exit-code preservation.
- Modify `tests/test_platform_ready_scripts.py`: observable-heartbeat, detail-log, failure-code, and termination regression coverage.
- Update `docs/superpowers/specs/2026-07-11-eod-auto-repair-supervisor-design.md`: mark implementation status after operational verification.

### Task 1: Reproduce the Missing-Stdout Heartbeat

**Files:**
- Modify: `tests/test_platform_ready_scripts.py:207-252`

- [ ] **Step 1: Change the heartbeat test to require observable stdout**

Replace the current assertion that forbids stdout heartbeats with:

```python
assert result.returncode == 0
assert "platform_ready_check|started|stage=eod_auto_repair|trade_date=2026-06-18" in result.stdout
assert "platform_ready_check|heartbeat|stage=eod_auto_repair|trade_date=2026-06-18" in result.stdout
assert "elapsed_seconds=" in result.stdout
assert "EOD自动修复完成" in result.stdout
log_text = (tmp_path / "logs" / "platform_ready_check.host.log").read_text(encoding="utf-8")
assert "child-detail-line" in log_text
```

Make the stub print `child-detail-line` before sleeping so the test also proves verbose child output remains in the log.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_platform_ready_scripts.py::test_platform_ready_check_script_emits_heartbeat_while_repair_runs -q
```

Expected: FAIL because the current wrapper writes heartbeat only to `platform_ready_check.host.log` and emits no `started` record.

### Task 2: Add Signal and Cleanup Regression Coverage

**Files:**
- Modify: `tests/test_platform_ready_scripts.py`

- [ ] **Step 1: Add a termination test**

Add a stub child that records its PID, traps TERM, writes a marker, and waits:

```python
def test_platform_ready_check_script_forwards_signal_and_cleans_up(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    _prepare_fake_guard(fake_root)
    fake_python = tmp_path / "python.sh"
    child_pid = tmp_path / "child.pid"
    term_marker = tmp_path / "child.terminated"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        f"echo $$ > {child_pid!s}\n"
        f"trap 'touch {term_marker!s}; exit 143' TERM INT\n"
        "while true; do sleep 1; done\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = {
        **os.environ,
        "PLATFORM_READY_ROOT": str(fake_root),
        "PLATFORM_READY_PYTHON": str(fake_python),
        "PLATFORM_READY_TRADE_DATE": "2026-06-18",
        "PLATFORM_READY_LOG_DIR": str(tmp_path / "logs"),
        "PLATFORM_READY_CHECK_HEARTBEAT_SECONDS": "1",
    }
    process = subprocess.Popen(
        ["scripts/run_platform_ready_check_cron.sh"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(50):
        if child_pid.exists():
            break
        time.sleep(0.1)
    process.terminate()
    process.wait(timeout=5)
    assert process.returncode != 0
    assert term_marker.exists()
    pid = int(child_pid.read_text(encoding="utf-8").strip())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
```

Add `import time` and `import pytest` at the top of the test module.

- [ ] **Step 2: Run the termination test and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_platform_ready_scripts.py::test_platform_ready_check_script_forwards_term_and_cleans_up -q
```

Expected: FAIL because the current wrapper has no TERM/INT forwarding trap.

### Task 3: Implement the Observable Supervisor

**Files:**
- Modify: `scripts/run_platform_ready_check_cron.sh:30-82`

- [ ] **Step 1: Add supervisor state and idempotent cleanup**

Add after `print_summary`:

```bash
PIPELINE_PID=""
HEARTBEAT_PID=""

cleanup_heartbeat() {
  if [[ -n "$HEARTBEAT_PID" ]]; then
    kill "$HEARTBEAT_PID" 2>/dev/null || true
    wait "$HEARTBEAT_PID" 2>/dev/null || true
    HEARTBEAT_PID=""
  fi
}

forward_signal() {
  if [[ -n "$PIPELINE_PID" ]]; then
    kill -TERM "$PIPELINE_PID" 2>/dev/null || true
  fi
}

trap forward_signal TERM INT
trap cleanup_heartbeat EXIT
```

- [ ] **Step 2: Launch the repair child and emit an immediate start record**

Replace `run_with_heartbeat` with explicit child ownership:

```bash
echo "platform_ready_check|started|stage=eod_auto_repair|trade_date=${TRADE_DATE}|detail_log=${RUN_LOG}"
echo "=== eod auto repair start: $(date '+%Y-%m-%d %H:%M:%S %z') ===" >>"$RUN_LOG"

rtk "$PYTHON" -m stock_research.eod_auto_repair \
  --trade-date "$TRADE_DATE" \
  --output-dir "$REPAIR_OUTPUT_DIR" \
  --mode repair >>"$RUN_LOG" 2>&1 &
PIPELINE_PID=$!
```

- [ ] **Step 3: Add an interruptible stdout heartbeat loop**

```bash
(
  HEARTBEAT_SLEEP_PID=""
  stop_heartbeat_loop() {
    if [[ -n "$HEARTBEAT_SLEEP_PID" ]]; then
      kill "$HEARTBEAT_SLEEP_PID" 2>/dev/null || true
    fi
    exit 0
  }
  trap stop_heartbeat_loop TERM INT
  started_epoch="$(date +%s)"
  while kill -0 "$PIPELINE_PID" 2>/dev/null; do
    sleep "$HEARTBEAT_SECONDS" &
    HEARTBEAT_SLEEP_PID=$!
    wait "$HEARTBEAT_SLEEP_PID" || exit 0
    HEARTBEAT_SLEEP_PID=""
    kill -0 "$PIPELINE_PID" 2>/dev/null || break
    now_epoch="$(date +%s)"
    last_progress="$(grep -E '^(eod_auto_repair\||progress\||free_enrichment_batch\|)' "$RUN_LOG" | tail -n 1 || true)"
    echo "platform_ready_check|heartbeat|stage=eod_auto_repair|trade_date=${TRADE_DATE}|elapsed_seconds=$((now_epoch-started_epoch))|last_progress=${last_progress:-waiting}"
  done
) &
HEARTBEAT_PID=$!
```

- [ ] **Step 4: Preserve child exit status and existing summary**

```bash
set +e
wait "$PIPELINE_PID"
rc=$?
set -e
cleanup_heartbeat

echo "eod_auto_repair|summary|$REPAIR_OUTPUT_DIR/run_summary.json" >>"$RUN_LOG"
echo "eod_auto_repair|report|$REPAIR_OUTPUT_DIR/run_report.md" >>"$RUN_LOG"
echo "=== eod auto repair end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ===" >>"$RUN_LOG"
```

Keep the existing `print_summary` success/failure branch and `exit "$rc"`.

- [ ] **Step 5: Run the two regression tests and verify GREEN**

Run:

```bash
rtk .venv/bin/pytest \
  tests/test_platform_ready_scripts.py::test_platform_ready_check_script_emits_heartbeat_while_repair_runs \
  tests/test_platform_ready_scripts.py::test_platform_ready_check_script_forwards_signal_and_cleans_up \
  -q
```

Expected: `2 passed`.

### Task 4: Compatibility and Operational Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-07-11-eod-auto-repair-supervisor-design.md`

- [ ] **Step 1: Run the complete focused script suite**

```bash
rtk .venv/bin/pytest tests/test_platform_ready_scripts.py -q --disable-warnings
```

Expected: all tests pass, including proxy clearing, date resolution, failure summary, heartbeat, and termination behavior.

- [ ] **Step 2: Validate shell syntax and whitespace**

```bash
rtk bash -n scripts/run_platform_ready_check_cron.sh
rtk git diff --check
```

Expected: both commands exit zero.

- [ ] **Step 3: Run a controlled already-repaired date through the wrapper**

```bash
PLATFORM_READY_TRADE_DATE=2026-07-10 \
PLATFORM_READY_CHECK_HEARTBEAT_SECONDS=1 \
rtk scripts/run_platform_ready_check_cron.sh
```

Expected: immediate `started`, at least one stdout heartbeat if execution exceeds one second, terminal success summary, and exit zero.

- [ ] **Step 4: Trigger the actual OpenClaw job and verify delivery**

```bash
rtk openclaw cron run acd2d8d3-320c-4d16-9072-543094845a7f \
  --wait --wait-timeout 10m --timeout 600000
rtk openclaw cron get acd2d8d3-320c-4d16-9072-543094845a7f
```

Expected: run status `ok`, delivery `delivered`, `consecutiveErrors=0`, schedule remains `0 22 * * 1-5`, `noOutputTimeoutSeconds=1200`, and `timeoutSeconds=7200`.

- [ ] **Step 5: Mark the spec implemented and commit only owned files**

Update the spec status to `Implemented and operationally verified on 2026-07-11`, then commit only:

```bash
git add scripts/run_platform_ready_check_cron.sh \
  tests/test_platform_ready_scripts.py \
  docs/superpowers/specs/2026-07-11-eod-auto-repair-supervisor-design.md \
  docs/superpowers/plans/2026-07-11-eod-auto-repair-supervisor.md
git commit -m "fix: supervise long-running eod auto repair"
```
