from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from stock_research.founder_os_model_recovery import SHANGHAI, is_managed_job
from stock_research.founder_os_model_recovery_cli import CommandResult


HEALTH_GUARD_ID = "7bb1fe09-5543-4f79-8dfc-cd0fe308638d"
SUPERVISOR_NAME = "founder-os-model-recovery-supervisor"
SUPERVISOR_COMMAND = "/Users/xiwei/.openclaw/bin/founder-os-model-recovery spawn"
AUDIT_COMMAND = "/Users/xiwei/.openclaw/bin/founder-os-model-recovery audit"
DEFAULT_STATE_DIR = Path("/Users/xiwei/.openclaw/state/founder-os-model-recovery")
Runner = Callable[[list[str], int], CommandResult]


def _default_runner(argv: list[str], timeout: int) -> CommandResult:
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def build_apply_commands(jobs: list[dict[str, Any]]) -> list[list[str]]:
    commands: list[list[str]] = []
    for job in jobs:
        if is_managed_job(job):
            commands.append(
                ["openclaw", "cron", "edit", str(job["id"]), "--no-failure-alert"]
            )
    commands.append(
        [
            "openclaw",
            "cron",
            "add",
            "--name",
            SUPERVISOR_NAME,
            "--description",
            "Retry same-day Founder OS tasks after Doubao or OpenAI recovers",
            "--every",
            "20m",
            "--agent",
            "agent_jarvis",
            "--command",
            SUPERVISOR_COMMAND,
            "--command-cwd",
            "/Users/xiwei/stock_research",
            "--no-deliver",
            "--json",
        ]
    )
    commands.append(
        [
            "openclaw",
            "cron",
            "edit",
            HEALTH_GUARD_ID,
            "--command",
            AUDIT_COMMAND,
            "--command-cwd",
            "/Users/xiwei/stock_research",
            "--no-deliver",
            "--no-failure-alert",
        ]
    )
    return commands


def _append_schedule(argv: list[str], schedule: dict[str, Any]) -> None:
    if schedule["kind"] == "cron":
        argv.extend(
            ["--cron", str(schedule["expr"]), "--tz", str(schedule.get("tz") or "Asia/Shanghai")]
        )
        if int(schedule.get("staggerMs", 0)) == 0:
            argv.append("--exact")
    elif schedule["kind"] == "every":
        argv.extend(["--every", f"{int(schedule['everyMs']) // 60000}m"])
    else:
        raise ValueError(f"unsupported schedule kind: {schedule['kind']}")


def _append_payload(argv: list[str], payload: dict[str, Any]) -> None:
    if payload["kind"] == "agentTurn":
        argv.extend(["--message", str(payload["message"])])
        if payload.get("model"):
            argv.extend(["--model", str(payload["model"])])
        else:
            argv.append("--clear-model")
        if payload.get("fallbacks"):
            argv.extend(["--fallbacks", ",".join(map(str, payload["fallbacks"]))])
        else:
            argv.append("--clear-fallbacks")
        if payload.get("lightContext"):
            argv.append("--light-context")
        else:
            argv.append("--no-light-context")
        if payload.get("toolsAllow"):
            argv.extend(["--tools", ",".join(map(str, payload["toolsAllow"]))])
        else:
            argv.append("--clear-tools")
    elif payload["kind"] == "command":
        argv.extend(
            [
                "--command-argv",
                json.dumps(payload["argv"], ensure_ascii=False),
            ]
        )
        if payload.get("cwd"):
            argv.extend(["--command-cwd", str(payload["cwd"])])
        if payload.get("noOutputTimeoutSeconds") is not None:
            argv.extend(
                [
                    "--no-output-timeout-seconds",
                    str(payload["noOutputTimeoutSeconds"]),
                ]
            )
        if payload.get("outputMaxBytes") is not None:
            argv.extend(["--output-max-bytes", str(payload["outputMaxBytes"])])
    else:
        raise ValueError(f"unsupported payload kind: {payload['kind']}")
    if payload.get("timeoutSeconds") is not None:
        argv.extend(["--timeout-seconds", str(payload["timeoutSeconds"])])


def _append_delivery(argv: list[str], job: dict[str, Any]) -> None:
    delivery = job.get("delivery", {})
    if delivery.get("mode") == "announce":
        argv.extend(
            [
                "--announce",
                "--channel",
                str(delivery["channel"]),
                "--to",
                str(delivery["to"]),
            ]
        )
        if delivery.get("accountId"):
            argv.extend(["--account", str(delivery["accountId"])])
    else:
        argv.append("--no-deliver")

    alert = job.get("failureAlert")
    if not alert:
        argv.append("--no-failure-alert")
        return
    argv.extend(
        [
            "--failure-alert",
            "--failure-alert-after",
            str(alert["after"]),
            "--failure-alert-channel",
            str(alert["channel"]),
            "--failure-alert-to",
            str(alert["to"]),
            "--failure-alert-cooldown",
            f"{int(alert['cooldownMs']) // 60000}m",
            "--failure-alert-mode",
            str(alert.get("mode", "announce")),
        ]
    )
    if alert.get("accountId"):
        argv.extend(["--failure-alert-account-id", str(alert["accountId"])])


def build_restore_command(job: dict[str, Any]) -> list[str]:
    argv = [
        "openclaw",
        "cron",
        "edit",
        str(job["id"]),
        "--name",
        str(job["name"]),
    ]
    if job.get("description"):
        argv.extend(["--description", str(job["description"])])
    if job.get("agentId"):
        argv.extend(["--agent", str(job["agentId"])])
    argv.extend(["--session", str(job.get("sessionTarget", "isolated"))])
    argv.extend(["--wake", str(job.get("wakeMode", "now"))])
    _append_schedule(argv, dict(job["schedule"]))
    _append_payload(argv, dict(job["payload"]))
    _append_delivery(argv, job)
    argv.append("--enable" if job.get("enabled") else "--disable")
    return argv


def build_rollback_commands(
    live_jobs: list[dict[str, Any]],
    backup_jobs: list[dict[str, Any]],
) -> list[list[str]]:
    commands = [
        ["openclaw", "cron", "rm", str(job["id"]), "--json"]
        for job in live_jobs
        if job.get("name") == SUPERVISOR_NAME
    ]
    commands.extend(build_restore_command(job) for job in backup_jobs)
    return commands


def save_cron_backup(
    state_dir: Path,
    jobs: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> Path:
    current = (now or datetime.now(tz=SHANGHAI)).astimezone(SHANGHAI)
    state_dir.mkdir(parents=True, exist_ok=True)
    filename = f"cron-backup-{current.strftime('%Y%m%dT%H%M%S%z')}.json"
    path = state_dir / filename
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"created_at": current.isoformat(), "jobs": jobs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def _run_json(runner: Runner, argv: list[str], timeout: int = 30) -> dict[str, Any]:
    result = runner(argv, timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def _run(runner: Runner, argv: list[str], timeout: int = 30) -> None:
    result = runner(argv, timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def list_jobs(runner: Runner) -> list[dict[str, Any]]:
    payload = _run_json(
        runner,
        ["openclaw", "cron", "list", "--all", "--json"],
    )
    return list(payload.get("jobs", []))


def apply_configuration(*, runner: Runner, state_dir: Path) -> Path:
    jobs = list_jobs(runner)
    if any(job.get("name") == SUPERVISOR_NAME for job in jobs):
        raise RuntimeError("recovery supervisor already exists")
    backup_path = save_cron_backup(state_dir, jobs)
    for command in build_apply_commands(jobs):
        _run(runner, command)
    return backup_path


def rollback_configuration(*, runner: Runner, backup_path: Path) -> None:
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    live_jobs = list_jobs(runner)
    for command in build_rollback_commands(live_jobs, list(backup["jobs"])):
        _run(runner, command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "apply", "rollback"])
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    return parser


def main(argv: list[str] | None = None, *, runner: Runner = _default_runner) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "dry-run":
        jobs = list_jobs(runner)
        print(
            json.dumps(
                {
                    "managed_jobs": [
                        job["name"] for job in jobs if is_managed_job(job)
                    ],
                    "commands": [
                        shlex.join(command) for command in build_apply_commands(jobs)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "apply":
        backup_path = apply_configuration(runner=runner, state_dir=args.state_dir)
        print(json.dumps({"backup_path": str(backup_path)}, ensure_ascii=False))
        return 0
    if args.backup is None:
        raise SystemExit("rollback requires --backup")
    rollback_configuration(runner=runner, backup_path=args.backup)
    print(json.dumps({"rolled_back_from": str(args.backup)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
