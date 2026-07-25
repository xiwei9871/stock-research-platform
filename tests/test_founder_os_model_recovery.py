from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from stock_research.founder_os_model_recovery import (
    CycleResult,
    RecoveryState,
    classify_failure,
    is_same_shanghai_day,
    is_managed_job,
    load_state,
    run_supervisor_cycle,
    save_state,
)


def test_classify_failure_accepts_model_availability_causes() -> None:
    error = (
        "All models failed (2): volcengine-plan/doubao-seed-2.0-code: "
        "429 weekly usage quota | openai/gpt-5.4: 503 auth_unavailable"
    )

    assert classify_failure(error) == "model_unavailable"


def test_classify_failure_accepts_inactive_openai_token_as_recoverable() -> None:
    error = (
        "All models failed (2): doubao: 429 weekly usage quota | "
        "openai/gpt-5.4: 403 Personal access token owner is inactive"
    )

    assert classify_failure(error) == "model_unavailable"


def test_classify_failure_rejects_mixed_business_failure() -> None:
    error = (
        "All models failed (2): doubao: 429 weekly usage quota | "
        "openai/gpt-5.4: permission denied writing report"
    )

    assert classify_failure(error) == "non_model"


def test_classify_failure_rejects_empty_and_tool_failures() -> None:
    assert classify_failure("") == "non_model"
    assert classify_failure("tool execution failed") == "non_model"


def test_same_shanghai_day_handles_utc_boundary() -> None:
    now = datetime(2026, 7, 25, 0, 10, tzinfo=timezone.utc)
    run = datetime(2026, 7, 24, 16, 5, tzinfo=timezone.utc)

    assert is_same_shanghai_day(run, now) is True


def test_recovery_state_deduplicates_and_enforces_probe_cooldown() -> None:
    now = datetime(2026, 7, 25, 1, 0, tzinfo=timezone.utc)
    state = RecoveryState.for_time(now)

    state.record_failure(
        job_id="job-1",
        run_id="run-1",
        job_name="morning-brief",
        classification="model_unavailable",
        run_at=now,
    )
    state.record_failure(
        job_id="job-1",
        run_id="run-1",
        job_name="morning-brief",
        classification="model_unavailable",
        run_at=now,
    )
    state.record_probe("job-1", "run-1", now)

    assert len(state.items) == 1
    assert state.can_probe("job-1", "run-1", now + timedelta(minutes=19)) is False
    assert state.can_probe("job-1", "run-1", now + timedelta(minutes=20)) is True


def test_probe_cooldown_is_shared_across_pending_tasks() -> None:
    now = datetime(2026, 7, 25, 1, 0, tzinfo=timezone.utc)
    state = RecoveryState.for_time(now)
    state.record_failure("job-1", "run-1", "morning", "model_unavailable", now)
    state.record_failure("job-2", "run-2", "signals", "model_unavailable", now)

    state.record_probe("job-1", "run-1", now)

    assert state.can_probe("job-2", "run-2", now + timedelta(minutes=19)) is False
    assert state.can_probe("job-2", "run-2", now + timedelta(minutes=20)) is True


def test_recovery_state_marks_recovered_item_terminal() -> None:
    now = datetime(2026, 7, 25, 1, 0, tzinfo=timezone.utc)
    state = RecoveryState.for_time(now)
    state.record_failure("job-1", "run-1", "morning", "model_unavailable", now)

    state.mark_recovered("job-1", "run-1", "replay-1", now)

    assert state.pending_model_failures() == []
    assert state.items["job-1:run-1"]["status"] == "recovered"


def test_recovery_state_does_not_import_yesterday_items() -> None:
    yesterday = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    today = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    state = RecoveryState.for_time(yesterday)
    state.record_failure("job-1", "run-1", "morning", "model_unavailable", yesterday)

    next_state = state.for_new_day(today)

    assert next_state.items == {}
    assert next_state.shanghai_date == "2026-07-25"


def test_save_state_uses_atomic_replace(tmp_path, monkeypatch) -> None:
    replaced: list[tuple[os.PathLike[str] | str, os.PathLike[str] | str]] = []
    real_replace = os.replace

    def tracking_replace(source, target):
        replaced.append((source, target))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", tracking_replace)
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    path = tmp_path / "2026-07-25.json"
    state = RecoveryState.for_time(now)
    state.record_failure("job-1", "run-1", "morning", "model_unavailable", now)

    save_state(path, state)

    assert load_state(path, now=now) == state
    assert replaced == [(path.with_suffix(".json.tmp"), path)]
    assert json.loads(path.read_text(encoding="utf-8"))["shanghai_date"] == "2026-07-25"


def test_load_state_returns_fresh_state_for_missing_file(tmp_path) -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)

    state = load_state(tmp_path / "missing.json", now=now)

    assert state.shanghai_date == "2026-07-25"
    assert state.items == {}


NOW = datetime(2026, 7, 25, 1, 0, tzinfo=timezone.utc)


def agent_job(job_id: str, name: str, *, enabled: bool = True) -> dict:
    return {
        "id": job_id,
        "name": name,
        "enabled": enabled,
        "payload": {"kind": "agentTurn"},
    }


def model_failure(
    run_id: str,
    run_at: str = "2026-07-25T08:00:00+08:00",
) -> dict:
    return {
        "action": "finished",
        "status": "error",
        "sessionId": run_id,
        "runAtIso": run_at,
        "runAtMs": 1,
        "ts": 1,
        "error": (
            "All models failed (2): doubao 429 weekly usage quota | "
            "openai 503 auth_unavailable"
        ),
    }


def non_model_failure(run_id: str) -> dict:
    run = model_failure(run_id)
    run["error"] = "permission denied writing report"
    return run


def success(run_id: str) -> dict:
    return {
        "action": "finished",
        "status": "ok",
        "sessionId": run_id,
        "runAtIso": "2026-07-25T09:00:00+08:00",
        "runAtMs": 2,
        "ts": 2,
    }


class FakeClient:
    def __init__(self, *, jobs, initial_runs, replay_results=None):
        self.jobs = jobs
        self.current_runs = dict(initial_runs)
        self.replay_results = dict(replay_results or {})
        self.run_calls: list[str] = []

    def list_jobs(self):
        return self.jobs

    def latest_terminal_run(self, job_id):
        return self.current_runs.get(job_id)

    def run_job(self, job_id):
        self.run_calls.append(job_id)
        self.current_runs[job_id] = self.replay_results[job_id]


def test_is_managed_job_excludes_commands_disabled_and_supervisor() -> None:
    assert is_managed_job(agent_job("job-1", "morning")) is True
    assert is_managed_job(agent_job("job-2", "disabled", enabled=False)) is False
    assert (
        is_managed_job(
            {
                "id": "job-3",
                "name": "command",
                "enabled": True,
                "payload": {"kind": "command"},
            }
        )
        is False
    )
    assert (
        is_managed_job(agent_job("job-4", "founder-os-model-recovery-supervisor"))
        is False
    )


def test_supervisor_runs_one_probe_then_replays_remaining_tasks() -> None:
    client = FakeClient(
        jobs=[agent_job("job-1", "morning"), agent_job("job-2", "signals")],
        initial_runs={
            "job-1": model_failure("run-1", "2026-07-25T08:00:00+08:00"),
            "job-2": model_failure("run-2", "2026-07-25T08:05:00+08:00"),
        },
        replay_results={"job-1": success("replay-1"), "job-2": success("replay-2")},
    )
    state = RecoveryState.for_time(NOW)

    result = run_supervisor_cycle(client=client, state=state, now=NOW)

    assert isinstance(result, CycleResult)
    assert client.run_calls == ["job-1", "job-2"]
    assert result.recovered == ["morning", "signals"]
    assert result.pending == []
    assert result.notifications == ["outage", "recovery"]


def test_supervisor_stops_after_probe_remains_unavailable() -> None:
    client = FakeClient(
        jobs=[agent_job("job-1", "morning"), agent_job("job-2", "signals")],
        initial_runs={"job-1": model_failure("run-1"), "job-2": model_failure("run-2")},
        replay_results={"job-1": model_failure("replay-1")},
    )

    result = run_supervisor_cycle(
        client=client,
        state=RecoveryState.for_time(NOW),
        now=NOW,
    )

    assert client.run_calls == ["job-1"]
    assert result.pending == ["morning", "signals"]
    assert result.notifications == ["outage"]


def test_supervisor_does_not_replay_non_model_or_previous_day_failures() -> None:
    client = FakeClient(
        jobs=[agent_job("job-1", "bad-file"), agent_job("job-2", "yesterday")],
        initial_runs={
            "job-1": non_model_failure("run-1"),
            "job-2": model_failure("run-2", "2026-07-24T08:00:00+08:00"),
        },
    )

    result = run_supervisor_cycle(
        client=client,
        state=RecoveryState.for_time(NOW),
        now=NOW,
    )

    assert client.run_calls == []
    assert result.non_model_failures == ["bad-file"]
    assert result.pending == []


def test_supervisor_second_cycle_does_not_replay_recovered_original_run() -> None:
    client = FakeClient(
        jobs=[agent_job("job-1", "morning")],
        initial_runs={"job-1": model_failure("run-1")},
        replay_results={"job-1": success("replay-1")},
    )
    state = RecoveryState.for_time(NOW)
    run_supervisor_cycle(client=client, state=state, now=NOW)

    second = run_supervisor_cycle(
        client=client,
        state=state,
        now=NOW + timedelta(minutes=20),
    )

    assert client.run_calls == ["job-1"]
    assert second.recovered == []
    assert second.notifications == []


def test_supervisor_sends_one_unresolved_summary_after_2350() -> None:
    now = datetime.fromisoformat("2026-07-25T23:50:00+08:00")
    client = FakeClient(
        jobs=[agent_job("job-1", "morning")],
        initial_runs={"job-1": model_failure("run-1")},
        replay_results={"job-1": model_failure("replay-1")},
    )
    state = RecoveryState.for_time(now)

    first = run_supervisor_cycle(client=client, state=state, now=now)
    second = run_supervisor_cycle(
        client=client,
        state=state,
        now=now + timedelta(minutes=5),
    )

    assert first.notifications == ["outage", "unresolved"]
    assert second.notifications == []


def test_supervisor_dry_run_discovers_but_does_not_replay() -> None:
    client = FakeClient(
        jobs=[agent_job("job-1", "morning")],
        initial_runs={"job-1": model_failure("run-1")},
        replay_results={"job-1": success("replay-1")},
    )

    result = run_supervisor_cycle(
        client=client,
        state=RecoveryState.for_time(NOW),
        now=NOW,
        execute_replays=False,
    )

    assert client.run_calls == []
    assert result.pending == ["morning"]
    assert result.notifications == ["outage"]
