import os
import signal
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "scripts" / "repair_publication_lock.py"


def _wait_for(path: Path, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path}")


def _launch(lock_file: Path, command: list[str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(WRAPPER), "--lock-file", str(lock_file), "--", *command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_only_one_real_process_acquires_shared_lock(tmp_path: Path):
    marker = tmp_path / "started"
    holder = _launch(
        tmp_path / "publication.lock",
        ["bash", "-c", f"touch {marker!s}; sleep 2"],
    )
    _wait_for(marker)

    contender = subprocess.run(
        [
            sys.executable,
            str(WRAPPER),
            "--lock-file",
            str(tmp_path / "publication.lock"),
            "--",
            "bash",
            "-c",
            "exit 0",
        ],
        check=False,
    )

    assert contender.returncode == 75
    holder.terminate()
    holder.wait(timeout=5)


def test_sigkill_wrapper_keeps_lock_until_inheriting_child_exits(tmp_path: Path):
    child_pid_path = tmp_path / "child.pid"
    lock_file = tmp_path / "publication.lock"
    holder = _launch(
        lock_file,
        ["bash", "-c", f"echo $$ > {child_pid_path!s}; sleep 30"],
    )
    _wait_for(child_pid_path)
    child_pid = int(child_pid_path.read_text().strip())

    os.kill(holder.pid, signal.SIGKILL)
    holder.wait(timeout=5)
    blocked = subprocess.run(
        [sys.executable, str(WRAPPER), "--lock-file", str(lock_file), "--", "true"],
        check=False,
    )
    assert blocked.returncode == 75

    os.killpg(child_pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        released = subprocess.run(
            [sys.executable, str(WRAPPER), "--lock-file", str(lock_file), "--", "true"],
            check=False,
        )
        if released.returncode == 0:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("lock was not released after inheriting child exited")


def test_wrapper_forwards_term_to_child_process_group(tmp_path: Path):
    child_pid_path = tmp_path / "child.pid"
    terminated = tmp_path / "terminated"
    holder = _launch(
        tmp_path / "publication.lock",
        [
            "bash",
            "-c",
            f"trap 'touch {terminated!s}; exit 143' TERM; echo $$ > {child_pid_path!s}; while true; do sleep 1; done",
        ],
    )
    _wait_for(child_pid_path)

    holder.send_signal(signal.SIGTERM)
    assert holder.wait(timeout=5) == 143
    _wait_for(terminated)


def test_wrapper_returns_child_exit_code(tmp_path: Path):
    result = subprocess.run(
        [
            sys.executable,
            str(WRAPPER),
            "--lock-file",
            str(tmp_path / "publication.lock"),
            "--",
            "bash",
            "-c",
            "exit 7",
        ],
        check=False,
    )

    assert result.returncode == 7
