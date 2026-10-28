"""CAP-R2C P0c — platform-ready run_step liveness detection.

Regression tests for the heartbeat hang observed during the R2B.1 full
regression: ``kill -0 $step_pid`` stays true for zombie children and for
PIDs recycled by unrelated processes, so the 60s heartbeat loop can spin
forever.  The fix must (a) not change any step, schedule, or heartbeat
semantics — only liveness detection; and (b) terminate run_step promptly
once the step has really exited.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "run_platform_ready_build_cron.sh"


def _harness(body: str) -> str:
    """Bash harness that sources the real script in lib-only mode so the
    actual production functions under test are exercised — not copies."""
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        export PLATFORM_READY_LIB_ONLY=1
        export PLATFORM_READY_ROOT="{REPO}"
        export PLATFORM_READY_PYTHON="$(command -v true)"
        export PLATFORM_READY_LOG_DIR="$(mktemp -d)"
        export PLATFORM_READY_TRADE_DATE="2026-10-23"
        export PLATFORM_READY_STEP_HEARTBEAT_SECONDS=1
        source "{SCRIPT}"
        {body}
        """
    )


def _run_bash(body: str, timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", _harness(body)],
        capture_output=True, text=True, timeout=timeout)


def test_step_process_alive_detects_live_child():
    r = _run_bash(
        'sleep 30 & p=$!\n'
        'step_process_alive "$p" && echo ALIVE || echo DEAD\n'
        'kill $p 2>/dev/null || true')
    assert "ALIVE" in r.stdout, r


def test_step_process_alive_rejects_zombie():
    # A real zombie (child exited, parent never waitpid) must not count
    # as alive — kill -0 alone returns true for zombies; the stat guard
    # (or ppid guard for foreign zombies) must reject it.
    holder = subprocess.Popen(
        ["python3", "-c",
         "import os,sys,time\n"
         "pid=os.fork()\n"
         "if pid==0: os._exit(0)\n"
         "print(pid,flush=True)\n"
         "time.sleep(30)\n"],
        stdout=subprocess.PIPE, text=True)
    try:
        zombie_pid = int(holder.stdout.readline().strip())
        time.sleep(0.5)  # let the child die and become a zombie
        st = subprocess.run(["ps", "-o", "stat=", "-p", str(zombie_pid)],
                            capture_output=True, text=True).stdout.strip()
        assert st.startswith("Z"), f"expected zombie, got stat={st!r}"
        r = _run_bash(
            f'step_process_alive {zombie_pid} && echo ALIVE || echo DEAD')
        assert "DEAD" in r.stdout, r
    finally:
        holder.kill()


def test_step_process_alive_rejects_foreign_process():
    # A live process that is not our child must not count as the step —
    # this is the PID-recycle livelock guard.
    r = _run_bash(
        '( sleep 30 ) & foreign=$!\n'
        'disown $foreign 2>/dev/null || true\n'
        'step_process_alive "$foreign" && echo ALIVE || echo DEAD\n'
        'kill $foreign 2>/dev/null || true')
    # disowned but still a child of this shell → ppid guard treats it as
    # ours (it is).  Use a truly foreign pid instead: launch via nohup
    # subshell that double-forks is overkill; ppid of disowned child is
    # still our shell, so assert on a process owned by launchd (pid 1).
    r = _run_bash('step_process_alive 1 && echo ALIVE || echo DEAD')
    assert "DEAD" in r.stdout, r


def test_run_step_returns_promptly_after_step_exit():
    # The observed hang: instant-exit step still occupied the loop for
    # 14+ minutes.  With zombie/PID-reuse-safe liveness this must return
    # inside a few seconds.
    start = time.time()
    r = _run_bash('run_step fast true; echo "step_rc=$?"', timeout=20)
    elapsed = time.time() - start
    assert r.returncode == 0, r.stderr
    assert "step_rc=0" in r.stdout
    assert elapsed < 10, f"run_step took {elapsed:.1f}s — heartbeat hang"


def test_run_step_surfaces_failure_rc():
    # run_step re-enables errexit internally (production semantics), so
    # the caller must evaluate it in a conditional context.
    r = _run_bash('run_step bad false || rc=$?; echo "step_rc=$rc"',
                  timeout=20)
    assert "step_rc=1" in r.stdout
