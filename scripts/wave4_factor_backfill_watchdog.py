#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_research.factor_backfill_watchdog import (
    build_status_message,
    find_existing_backfill_pid,
    get_cpu_percent,
    kill_process_group,
    process_exists,
    read_completion,
    read_last_progress,
    send_status_message,
    spawn_backfill,
    write_log,
)


DEFAULT_REPORT_TARGET = "chat:oc_82dd978138a0cde5864868c5b5b8e754"
BACKFILL_PATTERN = (
    "stock_research.cli backfill-factor-daily --start-date 1991-06-24 "
    "--end-date 2026-05-11 --lookback-bars 130 --industry-system csrc"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watchdog for Wave 4 factor daily backfill")
    parser.add_argument("--report-target", default=DEFAULT_REPORT_TARGET)
    parser.add_argument("--report-account", default="jarvis")
    parser.add_argument("--openclaw-bin", default="openclaw")
    parser.add_argument("--check-interval-seconds", type=int, default=300)
    parser.add_argument("--report-interval-seconds", type=int, default=1800)
    parser.add_argument("--stall-minutes", type=int, default=30)
    parser.add_argument(
        "--progress-log-file",
        default=str(ROOT / "logs" / "full_history_completion" / "wave4-factor-daily-resume.txt"),
    )
    parser.add_argument(
        "--watchdog-log-file",
        default=str(ROOT / "logs" / "full_history_completion" / "wave4-factor-daily-watchdog.log"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def build_backfill_command() -> list[str]:
    return [
        str(ROOT / ".venv" / "bin" / "python"),
        "-m",
        "stock_research.cli",
        "backfill-factor-daily",
        "--start-date",
        "1991-06-24",
        "--end-date",
        "2026-05-11",
        "--lookback-bars",
        "130",
        "--industry-system",
        "csrc",
        "--workers",
        "4",
        "--skip-complete",
        "--progress-interval",
        "25",
        "--exact-window",
    ]


def main() -> int:
    args = parse_args()
    progress_log = Path(args.progress_log_file)
    watchdog_log = Path(args.watchdog_log_file)

    pid = find_existing_backfill_pid(BACKFILL_PATTERN)
    if pid is not None:
        write_log(watchdog_log, f"watchdog_attach|pid={pid}")
    elif not args.dry_run:
        pid = spawn_backfill(command=build_backfill_command(), root=ROOT, log_path=progress_log)
        write_log(watchdog_log, f"watchdog_spawn|pid={pid}")
        send_status_message(
            message=build_status_message(
                title="Wave 4 factor_daily watchdog 已启动新任务",
                pid=pid,
                progress=read_last_progress(progress_log),
                unchanged_minutes=0,
                log_path=progress_log,
            ),
            target=args.report_target,
            account=args.report_account,
            openclaw_bin=args.openclaw_bin,
            dry_run=args.dry_run,
            watchdog_log=watchdog_log,
        )

    last_progress_key = None
    unchanged_seconds = 0
    last_report_at = 0.0

    while True:
        completion = read_completion(progress_log)
        progress = read_last_progress(progress_log)
        progress_key = progress.progress_key if progress is not None else None

        if progress_key != last_progress_key:
            unchanged_seconds = 0
            last_progress_key = progress_key
        else:
            unchanged_seconds += args.check_interval_seconds

        if completion.dates is not None and completion.rows is not None:
            send_status_message(
                message=(
                    "Wave 4 factor_daily 回填完成\n\n"
                    f"dates: {completion.dates}\n"
                    f"rows: {completion.rows}\n"
                    f"日志: {progress_log}"
                ),
                target=args.report_target,
                account=args.report_account,
                openclaw_bin=args.openclaw_bin,
                dry_run=args.dry_run,
                watchdog_log=watchdog_log,
            )
            write_log(
                watchdog_log,
                f"watchdog_done|dates={completion.dates}|rows={completion.rows}",
            )
            return 0

        running = pid is not None and process_exists(pid)
        cpu = get_cpu_percent(pid or 0) if running else 0.0
        write_log(
            watchdog_log,
            f"watchdog_probe|pid={pid or 0}|running={int(running)}|cpu={cpu:.1f}|"
            f"progress={progress_key}|unchanged_seconds={unchanged_seconds}",
        )

        now = time.time()
        if now - last_report_at >= args.report_interval_seconds:
            send_status_message(
                message=build_status_message(
                    title="Wave 4 factor_daily watchdog 30分钟状态",
                    pid=pid,
                    progress=progress,
                    unchanged_minutes=unchanged_seconds // 60,
                    log_path=progress_log,
                ),
                target=args.report_target,
                account=args.report_account,
                openclaw_bin=args.openclaw_bin,
                dry_run=args.dry_run,
                watchdog_log=watchdog_log,
            )
            last_report_at = now

        needs_restart = False
        reason = ""
        if not running:
            needs_restart = True
            reason = "process_missing"
        elif unchanged_seconds >= args.stall_minutes * 60:
            needs_restart = True
            reason = "no_progress"

        if needs_restart:
            write_log(
                watchdog_log,
                f"watchdog_restart|reason={reason}|pid={pid or 0}|progress={progress_key}",
            )
            if pid is not None and running and not args.dry_run:
                kill_process_group(pid)
            if not args.dry_run:
                pid = spawn_backfill(command=build_backfill_command(), root=ROOT, log_path=progress_log)
            else:
                pid = 0
            unchanged_seconds = 0
            last_progress_key = progress_key
            send_status_message(
                message=build_status_message(
                    title=f"Wave 4 factor_daily watchdog 已重启任务 ({reason})",
                    pid=pid,
                    progress=progress,
                    unchanged_minutes=0,
                    log_path=progress_log,
                ),
                target=args.report_target,
                account=args.report_account,
                openclaw_bin=args.openclaw_bin,
                dry_run=args.dry_run,
                watchdog_log=watchdog_log,
            )

        time.sleep(args.check_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
