# Founder OS Model Recovery Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic supervisor that waits for Doubao or OpenAI to recover, reruns every same-day model-failed cron task exactly once, and replaces per-task Feishu failures with incident-level notifications.

**Architecture:** Put the testable recovery engine and OpenClaw adapter in `stock_research`, expose it through a locked shell entrypoint, and install a stable shim under `~/.openclaw/bin`. A separate configuration command exports cron definitions before disabling managed per-job failure alerts, adding the 20-minute supervisor, and converting the health guard to a command job. Daily JSON state provides deduplication and date-window enforcement.

**Tech Stack:** Python 3.14, standard-library `argparse`/`dataclasses`/`json`/`subprocess`/`zoneinfo`, Bash, OpenClaw CLI, pytest.

---

## File Map

- Create `src/stock_research/founder_os_model_recovery.py`: failure classification, Shanghai-day filtering, incident state, probe/replay orchestration, redacted notification rendering.
- Create `src/stock_research/founder_os_model_recovery_cli.py`: OpenClaw subprocess adapter, CLI commands, atomic state persistence, Feishu sending.
- Create `src/stock_research/founder_os_model_recovery_config.py`: cron export, configuration plan, apply, and rollback.
- Create `scripts/run_founder_os_model_recovery_cron.sh`: non-blocking lock and runtime entrypoint.
- Create `scripts/install_founder_os_model_recovery.sh`: install the stable shim and invoke configuration apply/rollback.
- Create `tests/test_founder_os_model_recovery.py`: pure recovery-engine tests.
- Create `tests/test_founder_os_model_recovery_cli.py`: subprocess adapter and CLI tests with fake commands.
- Create `tests/test_founder_os_model_recovery_config.py`: configuration planning and rollback tests.
- Create `tests/test_founder_os_model_recovery_scripts.py`: shell entrypoint/install contract tests.
- Create `docs/founder-os-model-recovery-runbook.md`: operations, evidence, and rollback.

### Task 1: Failure Classification and Same-Day Selection

**Files:**
- Create: `src/stock_research/founder_os_model_recovery.py`
- Test: `tests/test_founder_os_model_recovery.py`

- [ ] **Step 1: Write failing classifier and date-window tests**

```python
from datetime import datetime, timezone

from stock_research.founder_os_model_recovery import (
    classify_failure,
    is_same_shanghai_day,
)


def test_classify_failure_accepts_only_model_availability_causes():
    error = (
        "All models failed (2): volcengine-plan/doubao-seed-2.0-code: "
        "429 weekly usage quota | openai/gpt-5.4: 503 auth_unavailable"
    )
    assert classify_failure(error) == "model_unavailable"


def test_classify_failure_rejects_mixed_business_failure():
    error = (
        "All models failed (2): volcengine-plan/doubao-seed-2.0-code: "
        "429 weekly usage quota | openai/gpt-5.4: permission denied writing report"
    )
    assert classify_failure(error) == "non_model"


def test_same_shanghai_day_handles_utc_boundary():
    now = datetime(2026, 7, 25, 0, 10, tzinfo=timezone.utc)
    run = datetime(2026, 7, 24, 16, 5, tzinfo=timezone.utc)
    assert is_same_shanghai_day(run, now) is True
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_founder_os_model_recovery.py -q
```

Expected: collection fails because `stock_research.founder_os_model_recovery` does not exist.

- [ ] **Step 3: Implement the minimal classifier and timezone helpers**

```python
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
MODEL_SIGNATURES = (
    re.compile(r"\b429\b", re.IGNORECASE),
    re.compile(r"weekly usage quota|usage limit|rate.?limit", re.IGNORECASE),
    re.compile(r"auth_unavailable|no auth available", re.IGNORECASE),
    re.compile(r"credentials?.*cooling down", re.IGNORECASE),
    re.compile(r"personal access token owner is inactive", re.IGNORECASE),
)
NON_MODEL_SIGNATURES = (
    re.compile(r"permission denied|file not found|no such file", re.IGNORECASE),
    re.compile(r"tool.*failed|invalid input|validation error", re.IGNORECASE),
)


def classify_failure(error: str) -> str:
    text = str(error or "").strip()
    if not text:
        return "non_model"
    if any(pattern.search(text) for pattern in NON_MODEL_SIGNATURES):
        return "non_model"
    if "All models failed" in text:
        causes = [item.strip() for item in text.split("|")]
        return (
            "model_unavailable"
            if causes and all(any(pattern.search(item) for pattern in MODEL_SIGNATURES) for item in causes)
            else "non_model"
        )
    return "model_unavailable" if any(pattern.search(text) for pattern in MODEL_SIGNATURES) else "non_model"


def is_same_shanghai_day(run_at: datetime, now: datetime) -> bool:
    return run_at.astimezone(SHANGHAI).date() == now.astimezone(SHANGHAI).date()
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `rtk .venv/bin/pytest tests/test_founder_os_model_recovery.py -q`

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/founder_os_model_recovery.py tests/test_founder_os_model_recovery.py
rtk git commit -m "feat: classify founder os model outages"
```

### Task 2: Atomic Daily State and Deduplication

**Files:**
- Modify: `src/stock_research/founder_os_model_recovery.py`
- Modify: `tests/test_founder_os_model_recovery.py`

- [ ] **Step 1: Add failing tests for deduplication, cooldown, and date rollover**

```python
from datetime import timedelta

from stock_research.founder_os_model_recovery import RecoveryState


def test_recovery_state_deduplicates_original_run_and_enforces_cooldown():
    now = datetime(2026, 7, 25, 1, 0, tzinfo=timezone.utc)
    state = RecoveryState.for_time(now)
    state.record_failure("job-1", "run-1", "model_unavailable", now)
    state.record_probe("job-1", "run-1", now)
    assert state.can_probe("job-1", "run-1", now + timedelta(minutes=19)) is False
    assert state.can_probe("job-1", "run-1", now + timedelta(minutes=20)) is True
    state.mark_recovered("job-1", "run-1", "replay-1", now + timedelta(minutes=21))
    assert state.pending_model_failures() == []


def test_recovery_state_does_not_import_yesterday_items():
    yesterday = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    today = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    state = RecoveryState.for_time(yesterday)
    state.record_failure("job-1", "run-1", "model_unavailable", yesterday)
    assert state.for_new_day(today).items == {}
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `rtk .venv/bin/pytest tests/test_founder_os_model_recovery.py -q`

Expected: import failure for `RecoveryState`.

- [ ] **Step 3: Implement recovery state transitions**

```python
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any


PROBE_COOLDOWN = timedelta(minutes=20)


@dataclass
class RecoveryState:
    shanghai_date: str
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    outage_alert_sent: bool = False
    recovery_alert_sent: bool = False
    unresolved_alert_sent: bool = False

    @classmethod
    def for_time(cls, now: datetime) -> "RecoveryState":
        return cls(shanghai_date=now.astimezone(SHANGHAI).date().isoformat())

    def for_new_day(self, now: datetime) -> "RecoveryState":
        key = now.astimezone(SHANGHAI).date().isoformat()
        return self if key == self.shanghai_date else RecoveryState(shanghai_date=key)

    @staticmethod
    def item_key(job_id: str, run_id: str) -> str:
        return f"{job_id}:{run_id}"

    def record_failure(self, job_id: str, run_id: str, classification: str, at: datetime) -> None:
        self.items.setdefault(
            self.item_key(job_id, run_id),
            {
                "job_id": job_id,
                "original_run_id": run_id,
                "classification": classification,
                "detected_at": at.isoformat(),
                "probe_attempts": [],
                "status": "pending",
            },
        )

    def record_probe(self, job_id: str, run_id: str, at: datetime) -> None:
        self.items[self.item_key(job_id, run_id)]["probe_attempts"].append(at.isoformat())

    def can_probe(self, job_id: str, run_id: str, now: datetime) -> bool:
        item = self.items[self.item_key(job_id, run_id)]
        if item["status"] != "pending":
            return False
        attempts = item["probe_attempts"]
        if not attempts:
            return True
        return now - datetime.fromisoformat(attempts[-1]) >= PROBE_COOLDOWN

    def mark_recovered(self, job_id: str, run_id: str, replay_run_id: str, at: datetime) -> None:
        item = self.items[self.item_key(job_id, run_id)]
        item.update(status="recovered", replay_run_id=replay_run_id, recovered_at=at.isoformat())

    def pending_model_failures(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.items.values()
            if item["classification"] == "model_unavailable" and item["status"] == "pending"
        ]
```

- [ ] **Step 4: Add atomic JSON persistence tests and implementation**

Add this test:

```python
def test_save_state_uses_atomic_replace(tmp_path, monkeypatch):
    replaced = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda source, target: (replaced.append((source, target)), real_replace(source, target))[1])
    path = tmp_path / "2026-07-25.json"
    state = RecoveryState.for_time(datetime(2026, 7, 25, tzinfo=timezone.utc))
    save_state(path, state)
    assert load_state(path) == state
    assert len(replaced) == 1
```

Add these methods and functions:

```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "shanghai_date": self.shanghai_date,
            "items": self.items,
            "outage_alert_sent": self.outage_alert_sent,
            "recovery_alert_sent": self.recovery_alert_sent,
            "unresolved_alert_sent": self.unresolved_alert_sent,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RecoveryState":
        return cls(
            shanghai_date=str(payload["shanghai_date"]),
            items=dict(payload.get("items", {})),
            outage_alert_sent=bool(payload.get("outage_alert_sent", False)),
            recovery_alert_sent=bool(payload.get("recovery_alert_sent", False)),
            unresolved_alert_sent=bool(payload.get("unresolved_alert_sent", False)),
        )


def load_state(path: Path, *, now: datetime | None = None) -> RecoveryState:
    current = now or datetime.now(tz=SHANGHAI)
    if not path.exists():
        return RecoveryState.for_time(current)
    return RecoveryState.from_dict(json.loads(path.read_text(encoding="utf-8"))).for_new_day(current)


def save_state(path: Path, state: RecoveryState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
```

- [ ] **Step 5: Run tests and verify GREEN**

Run: `rtk .venv/bin/pytest tests/test_founder_os_model_recovery.py -q`

Expected: all state and classifier tests pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/stock_research/founder_os_model_recovery.py tests/test_founder_os_model_recovery.py
rtk git commit -m "feat: persist founder os recovery state"
```

### Task 3: OpenClaw Adapter and Redacted Notifications

**Files:**
- Create: `src/stock_research/founder_os_model_recovery_cli.py`
- Create: `tests/test_founder_os_model_recovery_cli.py`

- [ ] **Step 1: Write failing adapter tests with an injected command runner**

```python
from stock_research.founder_os_model_recovery_cli import OpenClawClient


def test_openclaw_client_lists_jobs_and_runs_without_shell_interpolation():
    calls = []

    def runner(argv, timeout):
        calls.append((argv, timeout))
        return {"jobs": [{"id": "job-1", "payload": {"kind": "agentTurn"}}]}

    client = OpenClawClient(runner=runner)
    assert client.list_jobs()[0]["id"] == "job-1"
    assert calls == [(["openclaw", "cron", "list", "--all", "--json"], 30)]


def test_notification_redacts_request_ids_and_provider_payloads():
    client = OpenClawClient(runner=lambda argv, timeout: {})
    message = client.render_outage_message(
        task_names=["morning-brief", "signals"],
        next_retry="09:20",
        raw_error="request id: secret-provider-id",
    )
    assert "secret-provider-id" not in message
    assert "2 个任务" in message
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk .venv/bin/pytest tests/test_founder_os_model_recovery_cli.py -q`

Expected: module import failure.

- [ ] **Step 3: Implement argv-only OpenClaw calls**

```python
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Callable


Runner = Callable[[list[str], int], dict[str, Any]]


def _default_runner(argv: list[str], timeout: int) -> dict[str, Any]:
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=True)
    return json.loads(completed.stdout)


@dataclass
class OpenClawClient:
    runner: Runner = _default_runner

    def list_jobs(self) -> list[dict[str, Any]]:
        return list(self.runner(["openclaw", "cron", "list", "--all", "--json"], 30)["jobs"])

    def list_runs(self, job_id: str, limit: int = 10) -> list[dict[str, Any]]:
        payload = self.runner(
            ["openclaw", "cron", "runs", "--id", job_id, "--limit", str(limit)],
            30,
        )
        return list(payload.get("entries", []))

    def run_job(self, job_id: str) -> None:
        self.runner(
            ["openclaw", "cron", "run", "--wait", "--wait-timeout", "20m", job_id],
            1260,
        )

    def send_feishu(self, message: str, *, dry_run: bool = False) -> None:
        argv = [
            "openclaw", "message", "send", "--channel", "feishu", "--account", "jarvis",
            "--target", "chat:oc_82dd978138a0cde5864868c5b5b8e754", "--message", message, "--json",
        ]
        if dry_run:
            argv.append("--dry-run")
        self.runner(argv, 30)

    def render_outage_message(self, *, task_names: list[str], next_retry: str, raw_error: str = "") -> str:
        return (
            "Founder OS 模型暂不可用\n"
            f"受影响任务: {len(task_names)} 个\n"
            "处理: 已进入自动等待与补跑队列\n"
            f"下次检查: {next_retry}\n"
            "群内不再逐条发送原始模型错误"
        )
```

- [ ] **Step 4: Add tests and methods for latest run identity**

Add this method and helper:

```python
    def latest_terminal_run(self, job_id: str) -> dict[str, Any] | None:
        entries = [entry for entry in self.list_runs(job_id) if entry.get("action") == "finished"]
        return max(entries, key=lambda entry: int(entry.get("ts", 0)), default=None)


def run_identity(job_id: str, run: dict[str, Any]) -> str:
    return str(run.get("sessionId") or f"{job_id}:{run.get('runAtMs', 0)}")
```

Test a run with `sessionId="session-1"` and another with only `runAtMs=123`; expect identities `session-1` and `job-1:123`.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `rtk .venv/bin/pytest tests/test_founder_os_model_recovery_cli.py -q`

Expected: all adapter tests pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/stock_research/founder_os_model_recovery_cli.py tests/test_founder_os_model_recovery_cli.py
rtk git commit -m "feat: add openclaw recovery adapter"
```

### Task 4: Probe and Sequential Replay Orchestration

**Files:**
- Modify: `src/stock_research/founder_os_model_recovery.py`
- Modify: `src/stock_research/founder_os_model_recovery_cli.py`
- Modify: `tests/test_founder_os_model_recovery.py`
- Modify: `tests/test_founder_os_model_recovery_cli.py`

- [ ] **Step 1: Write failing successful-probe orchestration test**

```python
NOW = datetime(2026, 7, 25, 1, 0, tzinfo=timezone.utc)


def agent_job(job_id: str, name: str) -> dict:
    return {"id": job_id, "name": name, "enabled": True, "payload": {"kind": "agentTurn"}}


def model_failure(run_id: str, run_at: str = "2026-07-25T08:00:00+08:00") -> dict:
    return {
        "action": "finished",
        "status": "error",
        "sessionId": run_id,
        "runAtIso": run_at,
        "ts": 1,
        "error": "All models failed (2): doubao 429 weekly usage quota | openai 503 auth_unavailable",
    }


def success(run_id: str) -> dict:
    return {
        "action": "finished",
        "status": "ok",
        "sessionId": run_id,
        "runAtIso": "2026-07-25T09:00:00+08:00",
        "ts": 2,
    }


class FakeClient:
    def __init__(self, *, jobs, initial_runs, replay_results):
        self.jobs = jobs
        self.current_runs = dict(initial_runs)
        self.replay_results = replay_results
        self.run_calls = []

    def list_jobs(self):
        return self.jobs

    def latest_terminal_run(self, job_id):
        return self.current_runs[job_id]

    def run_job(self, job_id):
        self.run_calls.append(job_id)
        self.current_runs[job_id] = self.replay_results[job_id]


def test_supervisor_runs_one_probe_then_replays_remaining_tasks():
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
    assert client.run_calls == ["job-1", "job-2"]
    assert result.recovered == ["morning", "signals"]
```

- [ ] **Step 2: Write failing failed-probe stop test**

```python
def test_supervisor_stops_after_probe_still_reports_model_unavailable():
    client = FakeClient(
        jobs=[agent_job("job-1", "morning"), agent_job("job-2", "signals")],
        initial_runs={"job-1": model_failure("run-1"), "job-2": model_failure("run-2")},
        replay_results={"job-1": model_failure("replay-1")},
    )
    result = run_supervisor_cycle(client=client, state=RecoveryState.for_time(NOW), now=NOW)
    assert client.run_calls == ["job-1"]
    assert result.pending == ["morning", "signals"]
```

- [ ] **Step 3: Run tests and verify RED**

Run: `rtk .venv/bin/pytest tests/test_founder_os_model_recovery.py -q`

Expected: import failure for `run_supervisor_cycle`.

- [ ] **Step 4: Implement discovery and orchestration**

Implement these public types and functions:

```python
@dataclass(frozen=True)
class CycleResult:
    recovered: list[str]
    pending: list[str]
    non_model_failures: list[str]
    notifications: list[str]


def is_managed_job(job: dict[str, Any]) -> bool:
    return (
        bool(job.get("enabled"))
        and job.get("payload", {}).get("kind") == "agentTurn"
        and job.get("name") not in {"orchestration-dashboard-sync", "founder-os-model-recovery-supervisor"}
    )


def run_supervisor_cycle(
    *,
    client: Any,
    state: RecoveryState,
    now: datetime,
    persist_state: Callable[[RecoveryState], None] = lambda state: None,
) -> CycleResult:
    jobs = {job["id"]: job for job in client.list_jobs() if is_managed_job(job)}
    non_model: list[str] = []
    for job_id, job in jobs.items():
        run = client.latest_terminal_run(job_id)
        if not run or run.get("status") != "error":
            continue
        run_at = datetime.fromisoformat(str(run["runAtIso"]))
        if not is_same_shanghai_day(run_at, now):
            continue
        identity = run_identity(job_id, run)
        classification = classify_failure(str(run.get("error", "")))
        state.record_failure(job_id, identity, classification, now)
        item = state.items[state.item_key(job_id, identity)]
        item.update(job_name=job["name"], original_run_at=run_at.isoformat())
        if classification == "non_model":
            item["status"] = "terminal_non_model"
            non_model.append(job["name"])

    pending = sorted(state.pending_model_failures(), key=lambda item: item["original_run_at"])
    notifications: list[str] = []
    if pending and not state.outage_alert_sent:
        notifications.append("outage")
        state.outage_alert_sent = True
        persist_state(state)

    eligible = [
        item for item in pending
        if state.can_probe(item["job_id"], item["original_run_id"], now)
    ]
    recovered: list[str] = []
    if eligible:
        probe = eligible[0]
        state.record_probe(probe["job_id"], probe["original_run_id"], now)
        persist_state(state)
        client.run_job(probe["job_id"])
        replay = client.latest_terminal_run(probe["job_id"])
        replay_class = "success" if replay and replay.get("status") == "ok" else classify_failure(str((replay or {}).get("error", "")))
        if replay_class == "success":
            state.mark_recovered(probe["job_id"], probe["original_run_id"], run_identity(probe["job_id"], replay), now)
            recovered.append(probe["job_name"])
            persist_state(state)
            for item in [candidate for candidate in pending if candidate is not probe]:
                state.record_probe(item["job_id"], item["original_run_id"], now)
                persist_state(state)
                client.run_job(item["job_id"])
                replay = client.latest_terminal_run(item["job_id"])
                if replay and replay.get("status") == "ok":
                    state.mark_recovered(item["job_id"], item["original_run_id"], run_identity(item["job_id"], replay), now)
                    recovered.append(item["job_name"])
                else:
                    item["status"] = "pending" if classify_failure(str((replay or {}).get("error", ""))) == "model_unavailable" else "terminal_non_model"
                persist_state(state)

    remaining = [item["job_name"] for item in state.pending_model_failures()]
    if not remaining and state.outage_alert_sent and not state.recovery_alert_sent:
        notifications.append("recovery")
        state.recovery_alert_sent = True
        persist_state(state)
    if now.astimezone(SHANGHAI).strftime("%H:%M") >= "23:50" and remaining and not state.unresolved_alert_sent:
        notifications.append("unresolved")
        state.unresolved_alert_sent = True
        persist_state(state)
    return CycleResult(recovered, remaining, sorted(set(non_model)), notifications)
```

- [ ] **Step 5: Add tests for non-model failures, date rollover, and duplicate cycles**

Assert that non-model failures are never passed to `run_job`, yesterday's failures are ignored, and invoking the cycle twice after recovery produces no additional `run_calls` or notifications.

- [ ] **Step 6: Run both test files and verify GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_founder_os_model_recovery.py tests/test_founder_os_model_recovery_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
rtk git add src/stock_research/founder_os_model_recovery.py src/stock_research/founder_os_model_recovery_cli.py tests/test_founder_os_model_recovery.py tests/test_founder_os_model_recovery_cli.py
rtk git commit -m "feat: replay recovered founder os tasks"
```

### Task 5: CLI, Locking, and End-of-Day Summary

**Files:**
- Modify: `src/stock_research/founder_os_model_recovery_cli.py`
- Create: `scripts/run_founder_os_model_recovery_cron.sh`
- Modify: `tests/test_founder_os_model_recovery_cli.py`
- Create: `tests/test_founder_os_model_recovery_scripts.py`

- [ ] **Step 1: Add failing CLI tests**

Test `run --dry-run`, `audit`, and `run --now 2026-07-25T23:50:00+08:00`. Assert dry-run uses `openclaw message send --dry-run`, audit never invokes `cron run`, and the 23:50 cycle emits at most one unresolved summary.

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk .venv/bin/pytest tests/test_founder_os_model_recovery_cli.py -q`

Expected: CLI entrypoint and audit mode assertions fail.

- [ ] **Step 3: Implement CLI commands and paths**

```python
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(tz=SHANGHAI)
    path = args.state_dir / f"{now.astimezone(SHANGHAI).date().isoformat()}.json"
    state = load_state(path, now=now)
    if args.command == "audit":
        return audit_state(state=state, now=now)
    client = OpenClawClient()
    result = run_supervisor_cycle(
        client=client,
        state=state,
        now=now,
        persist_state=lambda value: save_state(path, value),
    )
    deliver_notifications(client=client, result=result, state=state, now=now, dry_run=args.dry_run)
    save_state(path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Implement `audit_state` to return nonzero only for corrupt state, a stale supervisor heartbeat older than 45 minutes, or an item stuck in `replay_unknown` for more than 40 minutes. Pending model outages are healthy waiting state, not audit failure. `deliver_notifications` maps the `outage`, `recovery`, and `unresolved` tokens to fixed redacted Chinese templates and calls `client.send_feishu` once per token.

- [ ] **Step 4: Write the shell contract test**

```python
from pathlib import Path


def test_recovery_cron_script_uses_lock_and_repo_python():
    text = Path("scripts/run_founder_os_model_recovery_cron.sh").read_text()
    assert "founder_os_model_recovery.lock" in text
    assert "python_lockfile" in text
    assert '-m stock_research.founder_os_model_recovery_cli "$COMMAND"' in text
```

- [ ] **Step 5: Implement the locked wrapper**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_RESEARCH_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_RESEARCH_PYTHON:-$ROOT/.venv/bin/python}"
LOCK_DIR="/Users/xiwei/.openclaw/state/founder-os-model-recovery/python_lockfile"
LOG_FILE="/Users/xiwei/.openclaw/logs/founder-os-model-recovery.log"
COMMAND="${1:-run}"
[[ "$COMMAND" == "run" || "$COMMAND" == "audit" ]] || { echo "usage: $0 [run|audit]" >&2; exit 2; }

mkdir -p "$(dirname "$LOCK_DIR")" "$(dirname "$LOG_FILE")"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "model_recovery|locked" >>"$LOG_FILE"
  exit 0
fi
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

cd "$ROOT"
PYTHONPATH="$ROOT/src" "$PYTHON" -m stock_research.founder_os_model_recovery_cli "$COMMAND" >>"$LOG_FILE" 2>&1
```

- [ ] **Step 6: Run focused tests and Bash syntax validation**

```bash
rtk .venv/bin/pytest tests/test_founder_os_model_recovery_cli.py tests/test_founder_os_model_recovery_scripts.py -q
rtk bash -n scripts/run_founder_os_model_recovery_cron.sh
```

Expected: all tests pass and `bash -n` exits zero.

- [ ] **Step 7: Commit**

```bash
rtk git add src/stock_research/founder_os_model_recovery_cli.py scripts/run_founder_os_model_recovery_cron.sh tests/test_founder_os_model_recovery_cli.py tests/test_founder_os_model_recovery_scripts.py
rtk git commit -m "feat: run founder os recovery supervisor"
```

### Task 6: Cron Configuration Backup, Apply, and Rollback

**Files:**
- Create: `src/stock_research/founder_os_model_recovery_config.py`
- Create: `tests/test_founder_os_model_recovery_config.py`
- Create: `scripts/install_founder_os_model_recovery.sh`
- Modify: `tests/test_founder_os_model_recovery_scripts.py`

- [ ] **Step 1: Write failing configuration planner tests**

Use fixture jobs containing command jobs, disabled jobs, orchestration sync, managed `agentTurn` jobs, and the health guard. Assert the plan:

- exports every original definition;
- emits `cron edit <id> --no-failure-alert` only for managed `agentTurn` jobs;
- emits one `cron add` for `founder-os-model-recovery-supervisor` with `--every 20m` and a command payload;
- converts job `7bb1fe09-5543-4f79-8dfc-cd0fe308638d` to the audit command;
- never changes a job's model or fallbacks;
- emits inverse rollback commands.

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk .venv/bin/pytest tests/test_founder_os_model_recovery_config.py -q`

Expected: module import failure.

- [ ] **Step 3: Implement configuration planning**

```python
HEALTH_GUARD_ID = "7bb1fe09-5543-4f79-8dfc-cd0fe308638d"
SUPERVISOR_NAME = "founder-os-model-recovery-supervisor"
SUPERVISOR_COMMAND = "/Users/xiwei/.openclaw/bin/founder-os-model-recovery run"
AUDIT_COMMAND = "/Users/xiwei/.openclaw/bin/founder-os-model-recovery audit"


def build_apply_commands(jobs: list[dict[str, Any]]) -> list[list[str]]:
    commands = []
    for job in jobs:
        if is_managed_job(job):
            commands.append(["openclaw", "cron", "edit", job["id"], "--no-failure-alert"])
    commands.append([
        "openclaw", "cron", "add", "--name", SUPERVISOR_NAME,
        "--every", "20m", "--command", SUPERVISOR_COMMAND,
        "--command-cwd", "/Users/xiwei/stock_research", "--no-deliver",
    ])
    commands.append([
        "openclaw", "cron", "edit", HEALTH_GUARD_ID,
        "--command", AUDIT_COMMAND,
        "--command-cwd", "/Users/xiwei/stock_research", "--no-deliver", "--no-failure-alert",
    ])
    return commands
```

Apply must refuse to run when a supervisor job already exists unless `--replace` is supplied. Backup filenames use `cron-backup-YYYYMMDDTHHMMSS+0800.json` and are written atomically under the state directory.

- [ ] **Step 4: Implement rollback from backup**

Add these rollback helpers and cover them with fixture assertions:

```python
def build_restore_command(job: dict[str, Any]) -> list[str]:
    argv = ["openclaw", "cron", "edit", job["id"], "--name", job["name"]]
    schedule = job["schedule"]
    if schedule["kind"] == "cron":
        argv += ["--cron", schedule["expr"], "--tz", schedule.get("tz", "Asia/Shanghai")]
    else:
        argv += ["--every", f"{int(schedule['everyMs']) // 60000}m"]
    payload = job["payload"]
    if payload["kind"] == "agentTurn":
        argv += ["--message", payload["message"]]
        argv += ["--model", payload["model"]] if payload.get("model") else ["--clear-model"]
        argv += ["--fallbacks", ",".join(payload["fallbacks"])] if payload.get("fallbacks") else ["--clear-fallbacks"]
    else:
        argv += ["--command-argv", json.dumps(payload["argv"], ensure_ascii=False)]
        if payload.get("cwd"):
            argv += ["--command-cwd", payload["cwd"]]
    delivery = job.get("delivery", {})
    if delivery.get("mode") == "announce":
        argv += ["--announce", "--channel", delivery["channel"], "--to", delivery["to"]]
        if delivery.get("accountId"):
            argv += ["--account", delivery["accountId"]]
    else:
        argv += ["--no-deliver"]
    alert = job.get("failureAlert")
    if alert:
        argv += [
            "--failure-alert", "--failure-alert-after", str(alert["after"]),
            "--failure-alert-channel", alert["channel"],
            "--failure-alert-to", alert["to"],
            "--failure-alert-cooldown", f"{int(alert['cooldownMs']) // 60000}m",
        ]
    else:
        argv += ["--no-failure-alert"]
    return argv


def build_rollback_commands(live_jobs: list[dict[str, Any]], backup_jobs: list[dict[str, Any]]) -> list[list[str]]:
    commands = [
        ["openclaw", "cron", "rm", job["id"]]
        for job in live_jobs
        if job.get("name") == SUPERVISOR_NAME
    ]
    commands.extend(build_restore_command(job) for job in backup_jobs)
    return commands
```

- [ ] **Step 5: Implement the installer shim**

After creating `/Users/xiwei/.openclaw/bin/founder-os-model-recovery` with `ln -sfn`, use this command routing:

```bash
case "${1:-}" in
  --dry-run)
    exec env PYTHONPATH="$ROOT/src" "$PYTHON" -m stock_research.founder_os_model_recovery_config dry-run
    ;;
  --apply)
    exec env PYTHONPATH="$ROOT/src" "$PYTHON" -m stock_research.founder_os_model_recovery_config apply
    ;;
  --rollback)
    [[ $# -eq 2 ]] || { echo "usage: $0 --rollback BACKUP_JSON" >&2; exit 2; }
    exec env PYTHONPATH="$ROOT/src" "$PYTHON" -m stock_research.founder_os_model_recovery_config rollback --backup "$2"
    ;;
  *)
    echo "usage: $0 --dry-run|--apply|--rollback BACKUP_JSON" >&2
    exit 2
    ;;
esac
```

- [ ] **Step 6: Run focused tests and syntax checks**

```bash
rtk .venv/bin/pytest tests/test_founder_os_model_recovery_config.py tests/test_founder_os_model_recovery_scripts.py -q
rtk bash -n scripts/install_founder_os_model_recovery.sh scripts/run_founder_os_model_recovery_cron.sh
```

Expected: all tests pass; both scripts are syntactically valid.

- [ ] **Step 7: Commit**

```bash
rtk git add src/stock_research/founder_os_model_recovery_config.py scripts/install_founder_os_model_recovery.sh tests/test_founder_os_model_recovery_config.py tests/test_founder_os_model_recovery_scripts.py
rtk git commit -m "feat: configure founder os recovery cron"
```

### Task 7: Runbook and Full Regression

**Files:**
- Create: `docs/founder-os-model-recovery-runbook.md`
- Modify: `docs/superpowers/specs/2026-07-25-founder-os-model-recovery-supervisor-design.md` when verified OpenClaw CLI details require a factual correction; otherwise leave it unchanged.

- [ ] **Step 1: Write the runbook**

Document:

- `rtk scripts/install_founder_os_model_recovery.sh --dry-run`;
- backup location and how to inspect it;
- `--apply` and expected supervisor/health-guard cron state;
- state-file fields and log locations;
- dry-run and audit commands;
- how same-day replay works;
- why previous-day tasks are not replayed;
- rollback command with an exact backup path example;
- notification examples without provider request IDs.

- [ ] **Step 2: Run the complete focused suite**

```bash
rtk .venv/bin/pytest tests/test_founder_os_model_recovery.py tests/test_founder_os_model_recovery_cli.py tests/test_founder_os_model_recovery_config.py tests/test_founder_os_model_recovery_scripts.py -q
rtk bash -n scripts/run_founder_os_model_recovery_cron.sh scripts/install_founder_os_model_recovery.sh
rtk git diff --check
```

Expected: all tests pass, shell syntax passes, and `git diff --check` is clean.

- [ ] **Step 3: Commit**

```bash
rtk git add docs/founder-os-model-recovery-runbook.md docs/superpowers/specs/2026-07-25-founder-os-model-recovery-supervisor-design.md
rtk git commit -m "docs: add founder os recovery runbook"
```

### Task 8: Dry-run, Controlled Rollout, and Live Verification

**Files:**
- Runtime backup: files matching `/Users/xiwei/.openclaw/state/founder-os-model-recovery/cron-backup-*.json`
- Runtime state: `/Users/xiwei/.openclaw/state/founder-os-model-recovery/$(TZ=Asia/Shanghai date +%F).json`
- Runtime log: `/Users/xiwei/.openclaw/logs/founder-os-model-recovery.log`

- [ ] **Step 1: Run configuration dry-run**

```bash
rtk scripts/install_founder_os_model_recovery.sh --dry-run
```

Expected: lists only enabled `agentTurn` jobs, excludes command jobs and orchestration sync, preserves model/fallback fields, and proposes one supervisor plus the health-guard conversion.

- [ ] **Step 2: Run supervisor dry-run against live state**

```bash
rtk env PYTHONPATH=src .venv/bin/python -m stock_research.founder_os_model_recovery_cli run --dry-run
```

Expected: classifies today's model failures, produces a redacted preview, and invokes neither real cron runs nor real Feishu delivery.

- [ ] **Step 3: Apply configuration**

```bash
rtk scripts/install_founder_os_model_recovery.sh --apply
```

Expected: prints the backup path, installs the shim, disables managed individual failure alerts, adds the 20-minute supervisor, and converts the health guard.

- [ ] **Step 4: Verify live cron configuration**

```bash
rtk openclaw cron list --all --json
rtk openclaw cron get 7bb1fe09-5543-4f79-8dfc-cd0fe308638d
```

Expected: exactly one enabled supervisor command job; health guard is a command job; Doubao remains primary and OpenAI remains the only fallback for every managed agent job.

- [ ] **Step 5: Run one controlled dry-run cycle and audit**

```bash
rtk /Users/xiwei/.openclaw/bin/founder-os-model-recovery run --dry-run
rtk /Users/xiwei/.openclaw/bin/founder-os-model-recovery audit
```

Expected: dry-run sends nothing; audit exits zero; lock and heartbeat evidence appear in the operational log.

- [ ] **Step 6: Verify deterministic Feishu delivery payload**

Run the message command with `--dry-run` using the rendered outage message. Confirm the target is the Founder OS group, the account is `jarvis`, and the payload contains no request ID or raw provider error.

- [ ] **Step 7: Re-run repository verification after rollout**

```bash
rtk .venv/bin/pytest tests/test_founder_os_model_recovery.py tests/test_founder_os_model_recovery_cli.py tests/test_founder_os_model_recovery_config.py tests/test_founder_os_model_recovery_scripts.py -q
rtk git status -sb
```

Expected: tests pass and only intentional committed files are present.

- [ ] **Step 8: Commit rollout evidence**

Add a concise rollout section to `docs/founder-os-model-recovery-runbook.md` containing the backup filename, supervisor cron ID, verification commands, and results. Do not commit runtime state, logs, credentials, or Feishu payload artifacts.

```bash
rtk git add docs/founder-os-model-recovery-runbook.md
rtk git commit -m "docs: record founder os recovery rollout"
```
