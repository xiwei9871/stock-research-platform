from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

from stock_research.founder_os_model_recovery import SHANGHAI
from stock_research.founder_os_model_recovery_config import (
    HEALTH_GUARD_ID,
    SUPERVISOR_NAME,
    apply_configuration,
    build_apply_commands,
    build_restore_command,
    build_rollback_commands,
    main,
    rollback_configuration,
    save_cron_backup,
)
from stock_research.founder_os_model_recovery_cli import CommandResult


def agent_job(
    job_id: str,
    name: str,
    *,
    enabled: bool = True,
    failure_alert: bool = True,
) -> dict:
    job = {
        "id": job_id,
        "name": name,
        "enabled": enabled,
        "agentId": "agent_jarvis",
        "schedule": {"kind": "cron", "expr": "30 7 * * *", "tz": "Asia/Shanghai"},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": "run task",
            "model": "volcengine-plan/doubao-seed-2.0-code",
            "fallbacks": ["openai/gpt-5.4"],
            "timeoutSeconds": 420,
            "lightContext": True,
            "toolsAllow": ["exec", "read"],
        },
        "delivery": {
            "mode": "announce",
            "channel": "feishu",
            "to": "chat:group",
            "accountId": "jarvis",
        },
    }
    if failure_alert:
        job["failureAlert"] = {
            "after": 1,
            "channel": "feishu",
            "to": "chat:group",
            "cooldownMs": 7_200_000,
            "mode": "announce",
            "accountId": "jarvis",
        }
    return job


def command_job(job_id: str, name: str) -> dict:
    return {
        "id": job_id,
        "name": name,
        "enabled": True,
        "agentId": "agent_jarvis",
        "schedule": {"kind": "every", "everyMs": 3_600_000},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "command",
            "argv": ["sh", "-lc", "echo ok"],
            "cwd": "/tmp",
            "timeoutSeconds": 60,
        },
        "delivery": {"mode": "none"},
    }


def test_apply_plan_disables_only_managed_agent_alerts_and_preserves_models() -> None:
    jobs = [
        agent_job("agent-1", "founder-os-morning"),
        agent_job("disabled", "disabled", enabled=False),
        command_job("command-1", "stock-command"),
        agent_job("sync", "orchestration-dashboard-sync"),
        agent_job(HEALTH_GUARD_ID, "founder-os-cron-health-guard"),
    ]

    commands = build_apply_commands(jobs)

    disabled_alert_ids = [
        command[3]
        for command in commands
        if command[:3] == ["openclaw", "cron", "edit"]
        and "--no-failure-alert" in command
        and "--command" not in command
    ]
    assert disabled_alert_ids == ["agent-1", HEALTH_GUARD_ID]
    assert all("--model" not in command and "--fallbacks" not in command for command in commands)
    assert sum(SUPERVISOR_NAME in command for command in commands) == 1
    supervisor_command = next(command for command in commands if SUPERVISOR_NAME in command)
    assert supervisor_command[supervisor_command.index("--agent") : supervisor_command.index("--agent") + 2] == [
        "--agent",
        "agent_jarvis",
    ]
    assert "/Users/xiwei/.openclaw/bin/founder-os-model-recovery spawn" in supervisor_command
    health_commands = [command for command in commands if HEALTH_GUARD_ID in command and "--command" in command]
    assert len(health_commands) == 1


def test_restore_command_restores_agent_contract() -> None:
    command = build_restore_command(agent_job("agent-1", "morning"))

    assert command[:4] == ["openclaw", "cron", "edit", "agent-1"]
    assert ["--model", "volcengine-plan/doubao-seed-2.0-code"] == command[
        command.index("--model") : command.index("--model") + 2
    ]
    assert "openai/gpt-5.4" in command
    assert "--failure-alert" in command
    assert "--announce" in command
    assert "--light-context" in command
    assert "exec,read" in command


def test_restore_command_restores_command_payload_without_alert() -> None:
    command = build_restore_command(command_job("command-1", "command"))

    assert "--command-argv" in command
    assert json.dumps(["sh", "-lc", "echo ok"], ensure_ascii=False) in command
    assert "--no-deliver" in command
    assert "--no-failure-alert" in command


def test_rollback_removes_supervisor_then_restores_backup_jobs() -> None:
    live = [command_job("supervisor-id", SUPERVISOR_NAME)]
    backup = [agent_job("agent-1", "morning")]

    commands = build_rollback_commands(live, backup)

    assert commands[0] == ["openclaw", "cron", "rm", "supervisor-id", "--json"]
    assert commands[1][:4] == ["openclaw", "cron", "edit", "agent-1"]


def test_save_cron_backup_uses_atomic_replace(tmp_path, monkeypatch) -> None:
    replaced = []
    real_replace = os.replace

    def tracking_replace(source, target):
        replaced.append((source, target))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", tracking_replace)
    now = datetime(2026, 7, 25, 12, 0, tzinfo=SHANGHAI)

    path = save_cron_backup(tmp_path, [agent_job("agent-1", "morning")], now=now)

    assert path.name == "cron-backup-20260725T120000+0800.json"
    assert len(replaced) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["jobs"][0]["id"] == "agent-1"


class FakeRunner:
    def __init__(self, jobs: list[dict]) -> None:
        self.jobs = jobs
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], timeout: int) -> CommandResult:
        self.calls.append(argv)
        if argv[:5] == ["openclaw", "cron", "list", "--all", "--json"]:
            return CommandResult(0, json.dumps({"jobs": self.jobs}), "")
        return CommandResult(0, json.dumps({"ok": True}), "")


def test_apply_configuration_backs_up_before_mutating(tmp_path) -> None:
    jobs = [agent_job("agent-1", "morning"), command_job("command-1", "stock")]
    runner = FakeRunner(jobs)

    backup = apply_configuration(runner=runner, state_dir=tmp_path)

    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8"))["jobs"] == jobs
    assert runner.calls[0] == ["openclaw", "cron", "list", "--all", "--json"]
    assert any("--no-failure-alert" in call for call in runner.calls[1:])
    assert any(SUPERVISOR_NAME in call for call in runner.calls[1:])


def test_apply_configuration_refuses_existing_supervisor(tmp_path) -> None:
    runner = FakeRunner([command_job("supervisor", SUPERVISOR_NAME)])

    with pytest.raises(RuntimeError, match="already exists"):
        apply_configuration(runner=runner, state_dir=tmp_path)

    assert len(runner.calls) == 1
    assert list(tmp_path.iterdir()) == []


def test_rollback_configuration_removes_supervisor_and_restores_jobs(tmp_path) -> None:
    backup_job = agent_job("agent-1", "morning")
    backup = save_cron_backup(tmp_path, [backup_job])
    runner = FakeRunner([command_job("supervisor", SUPERVISOR_NAME)])

    rollback_configuration(runner=runner, backup_path=backup)

    assert ["openclaw", "cron", "rm", "supervisor", "--json"] in runner.calls
    assert any(call[:4] == ["openclaw", "cron", "edit", "agent-1"] for call in runner.calls)


def test_main_dry_run_lists_commands_without_mutation(capsys) -> None:
    runner = FakeRunner([agent_job("agent-1", "morning")])

    assert main(["dry-run"], runner=runner) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["managed_jobs"] == ["morning"]
    assert len(runner.calls) == 1
