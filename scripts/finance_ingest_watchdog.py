#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.ingest_jobs import reset_stale_ingest_jobs_for_service


@dataclass
class JobSnapshot:
    success: int
    pending: int
    failed: int
    running: int
    latest_running_job_id: str | None
    latest_running_updated_at: datetime | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watchdog for finance ingest loop")
    parser.add_argument("--dataset", default="baostock-finance")
    parser.add_argument("--jobs-per-round", type=int, default=100)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--sleep-seconds", type=int, default=10)
    parser.add_argument("--report-target", required=True)
    parser.add_argument("--report-account")
    parser.add_argument("--openclaw-bin")
    parser.add_argument("--check-interval-seconds", type=int, default=60)
    parser.add_argument("--checkpoint-batches", type=int, default=20)
    parser.add_argument("--stall-minutes", type=int, default=12)
    parser.add_argument("--cpu-threshold", type=float, default=1.0)
    parser.add_argument("--log-file", default=str(ROOT / "logs" / "finance-ingest-watchdog.log"))
    parser.add_argument("--loop-log-file", default=str(ROOT / "logs" / "ingest-loop-baostock-finance.log"))
    parser.add_argument("--max-checks", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z")


def log(message: str, *, path: Path) -> None:
    line = f"{timestamp()} {message}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read_snapshot(dataset: str) -> JobSnapshot:
    with connect(SETTINGS.research_service) as conn:
        counts_rows = fetch_all(
            conn,
            "SELECT status, count(*) AS count FROM ingest.batch_job WHERE dataset=%s GROUP BY status",
            [dataset],
        )
        counts = {str(row["status"]): int(row["count"]) for row in counts_rows}
        running_rows = fetch_all(
            conn,
            """
            SELECT job_id, updated_at
            FROM ingest.batch_job
            WHERE dataset=%s AND status='running'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            [dataset],
        )
    latest_job_id = None
    latest_updated_at = None
    if running_rows:
        latest_job_id = str(running_rows[0]["job_id"])
        latest_updated_at = running_rows[0]["updated_at"]
    return JobSnapshot(
        success=int(counts.get("success", 0)),
        pending=int(counts.get("pending", 0)),
        failed=int(counts.get("failed", 0)),
        running=int(counts.get("running", 0)),
        latest_running_job_id=latest_job_id,
        latest_running_updated_at=latest_updated_at,
    )


def get_cpu_percent(pid: int) -> float:
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


def process_exists(pid: int) -> bool:
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


def build_loop_command(args: argparse.Namespace) -> list[str]:
    command = [
        str(ROOT / ".venv" / "bin" / "stock-research"),
        "run-ingest-loop",
        "--dataset",
        args.dataset,
        "--jobs-per-round",
        str(args.jobs_per_round),
        "--sleep-seconds",
        str(args.sleep_seconds),
        "--workers",
        str(args.workers),
        "--report-target",
        args.report_target,
    ]
    if args.report_account:
        command.extend(["--report-account", args.report_account])
    if args.openclaw_bin:
        command.extend(["--openclaw-bin", args.openclaw_bin])
    return command


def notify(message: str, args: argparse.Namespace, watchdog_log: Path) -> None:
    log(f"watchdog_notify|{message.replace(chr(10), ' | ')}", path=watchdog_log)
    if args.dry_run:
        return
    try:
        send_openclaw_feishu_message(
            message=message,
            target=args.report_target,
            account=args.report_account or "jarvis",
            openclaw_bin=args.openclaw_bin or "openclaw",
            dry_run=args.dry_run,
        )
    except Exception as exc:
        log(f"watchdog_notify_failed|{exc.__class__.__name__}|{exc}", path=watchdog_log)


def spawn_loop(args: argparse.Namespace, watchdog_log: Path) -> int:
    command = build_loop_command(args)
    log(f"spawn_loop|{' '.join(command)}", path=watchdog_log)
    if args.dry_run:
        return 0
    loop_log = Path(args.loop_log_file)
    loop_log.parent.mkdir(parents=True, exist_ok=True)
    fh = loop_log.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    return proc.pid


def kill_process(pid: int, watchdog_log: Path) -> None:
    log(f"kill_process|pid={pid}", path=watchdog_log)
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


def maybe_restart(
    *,
    pid: int | None,
    snapshot: JobSnapshot,
    args: argparse.Namespace,
    watchdog_log: Path,
) -> int | None:
    if snapshot.pending == 0 and snapshot.running == 0:
        log("watchdog_done|pending=0|running=0", path=watchdog_log)
        notify(
            f"A股财务数据补齐完成\n\n数据集: {args.dataset}\nsuccess: {snapshot.success}\npending: {snapshot.pending}\nfailed: {snapshot.failed}\nrunning: {snapshot.running}\n\n结论: 全部任务已完成",
            args,
            watchdog_log,
        )
        return pid

    if pid is None or pid == 0 or not process_exists(pid):
        log("watchdog_restart|reason=process_missing", path=watchdog_log)
        reset = reset_stale_ingest_jobs_for_service(dataset=args.dataset, older_than_minutes=args.stall_minutes)
        log(f"watchdog_reset|count={reset}", path=watchdog_log)
        notify(
            f"A股财务数据补齐 watchdog 触发重启\n\n原因: 进程消失\n数据集: {args.dataset}\nsuccess: {snapshot.success}\npending: {snapshot.pending}\nfailed: {snapshot.failed}\nrunning: {snapshot.running}\nreset: {reset}",
            args,
            watchdog_log,
        )
        return spawn_loop(args, watchdog_log)

    cpu = get_cpu_percent(pid)
    stale_minutes = 0.0
    if snapshot.latest_running_updated_at is not None:
        stale_seconds = (datetime.now(snapshot.latest_running_updated_at.tzinfo) - snapshot.latest_running_updated_at).total_seconds()
        stale_minutes = stale_seconds / 60.0

    log(
        f"watchdog_probe|pid={pid}|cpu={cpu:.1f}|success={snapshot.success}|pending={snapshot.pending}|"
        f"running={snapshot.running}|stale_minutes={stale_minutes:.1f}|job={snapshot.latest_running_job_id}",
        path=watchdog_log,
    )

    if (
        snapshot.running > 0
        and stale_minutes >= args.stall_minutes
        and cpu <= args.cpu_threshold
    ):
        log(
            f"watchdog_restart|reason=stalled|pid={pid}|cpu={cpu:.1f}|stale_minutes={stale_minutes:.1f}|job={snapshot.latest_running_job_id}",
            path=watchdog_log,
        )
        reset = 0
        if not args.dry_run:
            reset = reset_stale_ingest_jobs_for_service(
                dataset=args.dataset,
                older_than_minutes=args.stall_minutes,
            )
            log(f"watchdog_reset|count={reset}", path=watchdog_log)
            kill_process(pid, watchdog_log)
        notify(
            f"A股财务数据补齐 watchdog 触发重启\n\n原因: 疑似卡住\npid: {pid}\ncpu: {cpu:.1f}\nstale_minutes: {stale_minutes:.1f}\njob: {snapshot.latest_running_job_id}\nsuccess: {snapshot.success}\npending: {snapshot.pending}\nreset: {reset}",
            args,
            watchdog_log,
        )
        return spawn_loop(args, watchdog_log)
    return pid


def main() -> int:
    args = parse_args()
    watchdog_log = Path(args.log_file)
    checkpoint_batches = max(1, args.checkpoint_batches)

    snapshot = read_snapshot(args.dataset)
    last_checkpoint_success = snapshot.success
    pid: int | None = None
    checks = 0

    existing = subprocess.run(
        ["pgrep", "-f", f"stock-research run-ingest-loop --dataset {args.dataset}"],
        check=False,
        capture_output=True,
        text=True,
    )
    pids = [int(item) for item in existing.stdout.split() if item.strip().isdigit()]
    if pids:
        pid = pids[-1]
        log(f"watchdog_attach|pid={pid}", path=watchdog_log)
    else:
        pid = spawn_loop(args, watchdog_log)

    while True:
        snapshot = read_snapshot(args.dataset)
        if snapshot.success - last_checkpoint_success >= checkpoint_batches:
            cpu = get_cpu_percent(pid or 0) if pid else 0.0
            delta_success = snapshot.success - last_checkpoint_success
            log(
                f"watchdog_checkpoint|delta_success={delta_success}|"
                f"success={snapshot.success}|pending={snapshot.pending}|cpu={cpu:.1f}",
                path=watchdog_log,
            )
            notify(
                f"A股财务数据补齐进度（watchdog 20批检查）\n\n数据集: {args.dataset}\n本次增量成功: {delta_success}\n当前 success: {snapshot.success}\n当前 pending: {snapshot.pending}\n当前 failed: {snapshot.failed}\n当前 running: {snapshot.running}\nCPU: {cpu:.1f}\n最近运行批次: {snapshot.latest_running_job_id or '无'}",
                args,
                watchdog_log,
            )
            last_checkpoint_success = snapshot.success

        pid = maybe_restart(pid=pid, snapshot=snapshot, args=args, watchdog_log=watchdog_log)

        if snapshot.pending == 0 and snapshot.running == 0:
            return 0

        checks += 1
        if args.max_checks is not None and checks >= args.max_checks:
            return 0
        time.sleep(args.check_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
