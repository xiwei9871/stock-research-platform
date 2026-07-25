from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from stock_research.founder_os_model_recovery import (
    RecoveryState,
    classify_failure,
    is_same_shanghai_day,
    load_state,
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
