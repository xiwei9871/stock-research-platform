from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
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
        attempts = item["probe_attempts"]
        if not attempts:
            return True
        return now - datetime.fromisoformat(attempts[-1]) >= PROBE_COOLDOWN

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
