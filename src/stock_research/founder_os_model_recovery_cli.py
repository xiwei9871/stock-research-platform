from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Callable


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


def run_identity(job_id: str, run: dict[str, Any]) -> str:
    return str(run.get("sessionId") or f"{job_id}:{run.get('runAtMs', 0)}")


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
