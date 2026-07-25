from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
PROBE_COOLDOWN = timedelta(minutes=20)

_MODEL_SIGNATURES = (
    re.compile(r"\b429\b", re.IGNORECASE),
    re.compile(r"weekly usage quota|usage limit|rate.?limit", re.IGNORECASE),
    re.compile(r"auth_unavailable|no auth available", re.IGNORECASE),
    re.compile(r"credentials?.*cooling down", re.IGNORECASE),
    re.compile(r"personal access token owner is inactive", re.IGNORECASE),
)
_NON_MODEL_SIGNATURES = (
    re.compile(r"permission denied|file not found|no such file", re.IGNORECASE),
    re.compile(r"tool(?: execution)?.*failed|invalid input|validation error", re.IGNORECASE),
)


def classify_failure(error: str) -> str:
    text = str(error or "").strip()
    if not text:
        return "non_model"
    if any(pattern.search(text) for pattern in _NON_MODEL_SIGNATURES):
        return "non_model"
    if "all models failed" in text.lower():
        causes = [item.strip() for item in text.split("|") if item.strip()]
        if causes and all(
            any(pattern.search(cause) for pattern in _MODEL_SIGNATURES)
            for cause in causes
        ):
            return "model_unavailable"
        return "non_model"
    return (
        "model_unavailable"
        if any(pattern.search(text) for pattern in _MODEL_SIGNATURES)
        else "non_model"
    )


def is_same_shanghai_day(run_at: datetime, now: datetime) -> bool:
    return run_at.astimezone(SHANGHAI).date() == now.astimezone(SHANGHAI).date()


def run_identity(job_id: str, run: dict[str, Any]) -> str:
    return str(run.get("sessionId") or f"{job_id}:{run.get('runAtMs', 0)}")


@dataclass
class RecoveryState:
    shanghai_date: str
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    outage_alert_sent: bool = False
    recovery_alert_sent: bool = False
    unresolved_alert_sent: bool = False
    last_cycle_at: str = ""

    @classmethod
    def for_time(cls, now: datetime) -> RecoveryState:
        return cls(shanghai_date=now.astimezone(SHANGHAI).date().isoformat())

    def for_new_day(self, now: datetime) -> RecoveryState:
        shanghai_date = now.astimezone(SHANGHAI).date().isoformat()
        if shanghai_date == self.shanghai_date:
            return self
        return RecoveryState(shanghai_date=shanghai_date)

    @staticmethod
    def item_key(job_id: str, run_id: str) -> str:
        return f"{job_id}:{run_id}"

    def record_failure(
        self,
        job_id: str,
        run_id: str,
        job_name: str,
        classification: str,
        run_at: datetime,
    ) -> None:
        self.items.setdefault(
            self.item_key(job_id, run_id),
            {
                "job_id": job_id,
                "original_run_id": run_id,
                "job_name": job_name,
                "classification": classification,
                "original_run_at": run_at.isoformat(),
                "detected_at": run_at.isoformat(),
                "probe_attempts": [],
                "status": "pending",
            },
        )

    def record_probe(self, job_id: str, run_id: str, at: datetime) -> None:
        item = self.items[self.item_key(job_id, run_id)]
        item["probe_attempts"].append(at.isoformat())

    def can_probe(self, job_id: str, run_id: str, now: datetime) -> bool:
        item = self.items[self.item_key(job_id, run_id)]
        if item["status"] != "pending":
            return False
        attempts = [
            attempt
            for candidate in self.items.values()
            for attempt in candidate.get("probe_attempts", [])
        ]
        if not attempts:
            return True
        last_probe_at = max(datetime.fromisoformat(attempt) for attempt in attempts)
        return now - last_probe_at >= PROBE_COOLDOWN

    def mark_recovered(
        self,
        job_id: str,
        run_id: str,
        replay_run_id: str,
        at: datetime,
    ) -> None:
        item = self.items[self.item_key(job_id, run_id)]
        item.update(
            status="recovered",
            replay_run_id=replay_run_id,
            recovered_at=at.isoformat(),
        )

    def pending_model_failures(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.items.values()
            if item["classification"] == "model_unavailable"
            and item["status"] == "pending"
        ]

    def known_replay_run_ids(self) -> set[str]:
        return {
            str(item[key])
            for item in self.items.values()
            for key in ("last_replay_run_id", "replay_run_id")
            if item.get(key)
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RecoveryState:
        return cls(
            shanghai_date=str(payload["shanghai_date"]),
            items=dict(payload.get("items", {})),
            outage_alert_sent=bool(payload.get("outage_alert_sent", False)),
            recovery_alert_sent=bool(payload.get("recovery_alert_sent", False)),
            unresolved_alert_sent=bool(payload.get("unresolved_alert_sent", False)),
            last_cycle_at=str(payload.get("last_cycle_at", "")),
        )


def load_state(path: Path, *, now: datetime | None = None) -> RecoveryState:
    current = now or datetime.now(tz=SHANGHAI)
    if not path.exists():
        return RecoveryState.for_time(current)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RecoveryState.from_dict(payload).for_new_day(current)


def save_state(path: Path, state: RecoveryState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


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
        and job.get("name")
        not in {
            "orchestration-dashboard-sync",
            "founder-os-model-recovery-supervisor",
        }
    )


def _mark_replay_failure(
    *,
    state: RecoveryState,
    item: dict[str, Any],
    replay: dict[str, Any] | None,
    non_model_failures: list[str],
) -> str:
    replay_id = run_identity(item["job_id"], replay or {})
    item["last_replay_run_id"] = replay_id
    classification = classify_failure(str((replay or {}).get("error", "")))
    if classification == "model_unavailable":
        item["status"] = "pending"
    else:
        item["status"] = "terminal_non_model"
        non_model_failures.append(item["job_name"])
    return classification


def run_supervisor_cycle(
    *,
    client: Any,
    state: RecoveryState,
    now: datetime,
    persist_state: Callable[[RecoveryState], None] = lambda state: None,
    execute_replays: bool = True,
) -> CycleResult:
    jobs = {job["id"]: job for job in client.list_jobs() if is_managed_job(job)}
    non_model_failures: list[str] = []
    known_replays = state.known_replay_run_ids()

    for job_id, job in jobs.items():
        run = client.latest_terminal_run(job_id)
        if not run or run.get("status") != "error":
            continue
        identity = run_identity(job_id, run)
        if identity in known_replays:
            continue
        run_at_text = str(run.get("runAtIso") or run.get("tsIso") or "")
        if not run_at_text:
            continue
        run_at = datetime.fromisoformat(run_at_text)
        if not is_same_shanghai_day(run_at, now):
            continue
        classification = classify_failure(str(run.get("error", "")))
        state.record_failure(
            job_id=job_id,
            run_id=identity,
            job_name=str(job["name"]),
            classification=classification,
            run_at=run_at,
        )
        item = state.items[state.item_key(job_id, identity)]
        if classification == "non_model":
            item["status"] = "terminal_non_model"
            non_model_failures.append(str(job["name"]))

    pending = sorted(
        state.pending_model_failures(),
        key=lambda item: str(item["original_run_at"]),
    )
    notifications: list[str] = []
    if pending and not state.outage_alert_sent:
        state.outage_alert_sent = True
        notifications.append("outage")
        persist_state(state)

    eligible = [
        item
        for item in pending
        if state.can_probe(item["job_id"], item["original_run_id"], now)
    ]
    recovered: list[str] = []

    if eligible and execute_replays:
        probe = eligible[0]
        state.record_probe(probe["job_id"], probe["original_run_id"], now)
        persist_state(state)
        client.run_job(probe["job_id"])
        replay = client.latest_terminal_run(probe["job_id"])
        if replay and replay.get("status") == "ok":
            state.mark_recovered(
                probe["job_id"],
                probe["original_run_id"],
                run_identity(probe["job_id"], replay),
                now,
            )
            recovered.append(probe["job_name"])
            persist_state(state)
            for item in [candidate for candidate in pending if candidate is not probe]:
                state.record_probe(item["job_id"], item["original_run_id"], now)
                persist_state(state)
                client.run_job(item["job_id"])
                replay = client.latest_terminal_run(item["job_id"])
                if replay and replay.get("status") == "ok":
                    state.mark_recovered(
                        item["job_id"],
                        item["original_run_id"],
                        run_identity(item["job_id"], replay),
                        now,
                    )
                    recovered.append(item["job_name"])
                    persist_state(state)
                    continue
                classification = _mark_replay_failure(
                    state=state,
                    item=item,
                    replay=replay,
                    non_model_failures=non_model_failures,
                )
                persist_state(state)
                if classification == "model_unavailable":
                    break
        else:
            _mark_replay_failure(
                state=state,
                item=probe,
                replay=replay,
                non_model_failures=non_model_failures,
            )
            persist_state(state)

    remaining = [item["job_name"] for item in state.pending_model_failures()]
    if not remaining and state.outage_alert_sent and not state.recovery_alert_sent:
        state.recovery_alert_sent = True
        notifications.append("recovery")
        persist_state(state)
    if (
        now.astimezone(SHANGHAI).strftime("%H:%M") >= "23:50"
        and remaining
        and not state.unresolved_alert_sent
    ):
        state.unresolved_alert_sent = True
        notifications.append("unresolved")
        persist_state(state)

    state.last_cycle_at = now.isoformat()
    persist_state(state)
    return CycleResult(
        recovered=recovered,
        pending=remaining,
        non_model_failures=sorted(set(non_model_failures)),
        notifications=notifications,
    )
