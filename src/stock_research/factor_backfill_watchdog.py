from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from stock_research.feishu_notify import send_openclaw_feishu_message


@dataclass(frozen=True)
class ProgressSnapshot:
    trade_date: str
    index: int
    total: int
    factor_rows: int

    @property
    def progress_key(self) -> tuple[str, int, int, int]:
        return (self.trade_date, self.index, self.total, self.factor_rows)


@dataclass(frozen=True)
class CompletionSnapshot:
    dates: int | None
    rows: int | None


def parse_progress_line(line: str) -> ProgressSnapshot | None:
    parts = line.strip().split("|")
    if len(parts) != 6:
        return None
    if parts[0] != "factor_daily_backfill" or parts[1] != "done":
        return None
    return ProgressSnapshot(
        trade_date=parts[2],
        index=int(parts[3]),
        total=int(parts[4]),
        factor_rows=int(parts[5]),
    )


def read_last_progress(log_path: Path) -> ProgressSnapshot | None:
    if not log_path.exists():
        return None
    last: ProgressSnapshot | None = None
    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parsed = parse_progress_line(line)
            if parsed is not None:
                last = parsed
    return last


def read_completion(log_path: Path) -> CompletionSnapshot:
    dates: int | None = None
    rows: int | None = None
    if not log_path.exists():
        return CompletionSnapshot(dates=None, rows=None)
    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.strip().split("|")
            if len(parts) != 3:
                continue
            if parts[0] != "factor_daily_backfill":
                continue
            if parts[1] == "dates":
                dates = int(parts[2])
            elif parts[1] == "rows":
                rows = int(parts[2])
    return CompletionSnapshot(dates=dates, rows=rows)


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    stat = result.stdout.strip()
    return bool(stat) and not stat.startswith("Z")


def get_cpu_percent(pid: int) -> float:
    if pid <= 0:
        return 0.0
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "%cpu="],
        check=False,
        capture_output=True,
        text=True,
    )
    text = result.stdout.strip()
    if result.returncode != 0 or not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def find_existing_backfill_pid(pattern: str) -> int | None:
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    pids = [int(item) for item in result.stdout.split() if item.strip().isdigit()]
    if not pids:
        return None
    return pids[-1]


def spawn_backfill(
    *,
    command: list[str],
    root: Path,
    log_path: Path,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = log_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        command,
        cwd=str(root),
        stdout=fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    return proc.pid


def kill_process_group(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(2)
    if process_exists(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            return


def timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z")


def write_log(log_path: Path, message: str) -> None:
    line = f"{timestamp()} {message}"
    print(line, flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def send_status_message(
    *,
    message: str,
    target: str,
    account: str,
    openclaw_bin: str,
    dry_run: bool,
    watchdog_log: Path,
) -> None:
    write_log(watchdog_log, f"watchdog_notify|{message.replace(chr(10), ' | ')}")
    if dry_run:
        return
    try:
        send_openclaw_feishu_message(
            message=message,
            target=target,
            account=account,
            openclaw_bin=openclaw_bin,
            dry_run=False,
        )
    except Exception as exc:
        write_log(watchdog_log, f"watchdog_notify_failed|{exc.__class__.__name__}|{exc}")


def build_status_message(
    *,
    title: str,
    pid: int | None,
    progress: ProgressSnapshot | None,
    unchanged_minutes: int,
    log_path: Path,
) -> str:
    progress_line = "无"
    if progress is not None:
        progress_line = (
            f"{progress.trade_date} ({progress.index}/{progress.total}, rows={progress.factor_rows})"
        )
    return (
        f"{title}\n\n"
        f"任务: Wave 4 factor_daily 全历史回填\n"
        f"pid: {pid or 0}\n"
        f"最新进度: {progress_line}\n"
        f"无推进时长: {unchanged_minutes} 分钟\n"
        f"日志: {log_path}"
    )
