from __future__ import annotations

import json

from stock_research.founder_os_model_recovery_cli import (
    CommandResult,
    OpenClawClient,
    run_identity,
)


class FakeRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[str], int]] = []

    def __call__(self, argv: list[str], timeout: int) -> CommandResult:
        self.calls.append((argv, timeout))
        return self.responses.pop(0)


def json_result(payload: dict) -> CommandResult:
    return CommandResult(returncode=0, stdout=json.dumps(payload), stderr="")


def test_openclaw_client_lists_jobs_without_shell_interpolation() -> None:
    runner = FakeRunner(
        [json_result({"jobs": [{"id": "job-1", "payload": {"kind": "agentTurn"}}]})]
    )
    client = OpenClawClient(runner=runner)

    assert client.list_jobs()[0]["id"] == "job-1"
    assert runner.calls == [
        (["openclaw", "cron", "list", "--all", "--json"], 30)
    ]


def test_openclaw_client_returns_latest_finished_run() -> None:
    runner = FakeRunner(
        [
            json_result(
                {
                    "entries": [
                        {"action": "started", "ts": 30},
                        {"action": "finished", "ts": 10, "sessionId": "old"},
                        {"action": "finished", "ts": 20, "sessionId": "new"},
                    ]
                }
            )
        ]
    )
    client = OpenClawClient(runner=runner)

    assert client.latest_terminal_run("job-1")["sessionId"] == "new"


def test_run_identity_uses_session_then_timestamp_fallback() -> None:
    assert run_identity("job-1", {"sessionId": "session-1", "runAtMs": 123}) == "session-1"
    assert run_identity("job-1", {"runAtMs": 123}) == "job-1:123"


def test_run_job_does_not_raise_when_replayed_job_fails() -> None:
    runner = FakeRunner(
        [CommandResult(returncode=1, stdout="", stderr="command exited with code 1")]
    )
    client = OpenClawClient(runner=runner)

    result = client.run_job("job-1")

    assert result.returncode == 1
    assert runner.calls[0][0] == [
        "openclaw",
        "cron",
        "run",
        "--wait",
        "--wait-timeout",
        "20m",
        "job-1",
    ]


def test_send_feishu_dry_run_uses_fixed_target_and_no_shell() -> None:
    runner = FakeRunner([json_result({"ok": True})])
    client = OpenClawClient(runner=runner)

    client.send_feishu("恢复摘要", dry_run=True)

    argv = runner.calls[0][0]
    assert argv[:3] == ["openclaw", "message", "send"]
    assert ["--channel", "feishu"] == argv[3:5]
    assert "chat:oc_82dd978138a0cde5864868c5b5b8e754" in argv
    assert "--dry-run" in argv


def test_notifications_are_short_and_do_not_include_raw_error() -> None:
    client = OpenClawClient(runner=FakeRunner([]))
    raw_error = "request id: secret-provider-id"

    outage = client.render_outage_message(["morning", "signals"], "09:20", raw_error)
    recovery = client.render_recovery_message(["morning", "signals"], [])
    unresolved = client.render_unresolved_message(["morning"], "23:50")

    assert "secret-provider-id" not in outage
    assert "2 个" in outage
    assert "morning" in recovery
    assert "1 个" in unresolved
