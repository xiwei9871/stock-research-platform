from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from stock_research.founder_os_model_recovery import (
    CycleResult,
    RecoveryState,
    SHANGHAI,
    load_state,
    run_identity,
    run_supervisor_cycle,
    save_state,
)


FEISHU_ACCOUNT = "jarvis"
FEISHU_TARGET = "chat:oc_82dd978138a0cde5864868c5b5b8e754"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str], int], CommandResult]


def _default_runner(argv: list[str], timeout: int) -> CommandResult:
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


@dataclass
class OpenClawClient:
    runner: Runner = _default_runner

    def _json_command(self, argv: list[str], timeout: int) -> dict[str, Any]:
        result = self.runner(argv, timeout)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(message or f"command failed: {argv!r}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"command returned invalid JSON: {argv!r}") from exc

    def list_jobs(self) -> list[dict[str, Any]]:
        payload = self._json_command(
            ["openclaw", "cron", "list", "--all", "--json"],
            30,
        )
        return list(payload.get("jobs", []))

    def list_runs(self, job_id: str, limit: int = 10) -> list[dict[str, Any]]:
        payload = self._json_command(
            [
                "openclaw",
                "cron",
                "runs",
                "--id",
                job_id,
                "--limit",
                str(limit),
            ],
            30,
        )
        return list(payload.get("entries", []))

    def latest_terminal_run(self, job_id: str) -> dict[str, Any] | None:
        entries = [
            entry
            for entry in self.list_runs(job_id)
            if entry.get("action") == "finished"
        ]
        return max(entries, key=lambda entry: int(entry.get("ts", 0)), default=None)

    def run_job(self, job_id: str) -> CommandResult:
        return self.runner(
            [
                "openclaw",
                "cron",
                "run",
                "--wait",
                "--wait-timeout",
                "20m",
                job_id,
            ],
            1260,
        )

    def send_feishu(self, message: str, *, dry_run: bool = False) -> dict[str, Any]:
        argv = [
            "openclaw",
            "message",
            "send",
            "--channel",
            "feishu",
            "--account",
            FEISHU_ACCOUNT,
            "--target",
            FEISHU_TARGET,
            "--message",
            message,
            "--json",
        ]
        if dry_run:
            argv.append("--dry-run")
        return self._json_command(argv, 30)

    def render_outage_message(
        self,
        task_names: list[str],
        next_retry: str,
        raw_error: str = "",
    ) -> str:
        del raw_error
        return (
            "Founder OS 模型暂不可用\n"
            f"受影响任务: {len(task_names)} 个\n"
            "处理: 已进入当天自动等待与补跑队列\n"
            f"下次检查: {next_retry}\n"
            "群内不再逐条发送原始模型错误"
        )

    def render_recovery_message(
        self,
        recovered: list[str],
        non_model_failures: list[str],
    ) -> str:
        recovered_text = ", ".join(recovered) if recovered else "无"
        non_model_text = ", ".join(non_model_failures) if non_model_failures else "无"
        return (
            "Founder OS 模型恢复补跑完成\n"
            f"补跑成功: {recovered_text}\n"
            f"非模型失败: {non_model_text}"
        )

    def render_unresolved_message(self, pending: list[str], at_time: str) -> str:
        return (
            "Founder OS 当日模型任务仍待恢复\n"
            f"待补跑任务: {len(pending)} 个\n"
            f"截止检查: {at_time}\n"
            "跨日后不再自动补跑"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "audit"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("/Users/xiwei/.openclaw/state/founder-os-model-recovery"),
    )
    return parser


def audit_state(*, state: RecoveryState, now: datetime) -> int:
    if not state.last_cycle_at:
        return 1
    try:
        last_cycle = datetime.fromisoformat(state.last_cycle_at)
    except ValueError:
        return 1
    if now - last_cycle > timedelta(minutes=45):
        return 1
    for item in state.items.values():
        if item.get("status") != "replay_unknown":
            continue
        marked_at = item.get("replay_unknown_at")
        if not marked_at:
            return 1
        if now - datetime.fromisoformat(str(marked_at)) > timedelta(minutes=40):
            return 1
    return 0


def deliver_notifications(
    *,
    client: OpenClawClient,
    result: CycleResult,
    state: RecoveryState,
    now: datetime,
    dry_run: bool,
    persist_state: Callable[[RecoveryState], None],
) -> None:
    for notification in result.notifications:
        if notification == "outage":
            message = client.render_outage_message(
                result.pending,
                (now + timedelta(minutes=20)).astimezone(SHANGHAI).strftime("%H:%M"),
            )
            flag = "outage_alert_sent"
        elif notification == "recovery":
            message = client.render_recovery_message(
                result.recovered,
                result.non_model_failures,
            )
            flag = "recovery_alert_sent"
        elif notification == "unresolved":
            message = client.render_unresolved_message(
                result.pending,
                now.astimezone(SHANGHAI).strftime("%H:%M"),
            )
            flag = "unresolved_alert_sent"
        else:
            continue
        try:
            client.send_feishu(message, dry_run=dry_run)
        except Exception:
            setattr(state, flag, False)
            persist_state(state)
            raise
        persist_state(state)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(tz=SHANGHAI)
    state_path = args.state_dir / f"{now.astimezone(SHANGHAI).date().isoformat()}.json"
    try:
        state = load_state(state_path, now=now)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 1
    if args.command == "audit":
        return audit_state(state=state, now=now)

    client = OpenClawClient()
    persist = (lambda value: None) if args.dry_run else (lambda value: save_state(state_path, value))
    result = run_supervisor_cycle(
        client=client,
        state=state,
        now=now,
        persist_state=persist,
        execute_replays=not args.dry_run,
    )
    deliver_notifications(
        client=client,
        result=result,
        state=state,
        now=now,
        dry_run=args.dry_run,
        persist_state=persist,
    )
    if not args.dry_run:
        save_state(state_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
