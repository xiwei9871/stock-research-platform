from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RepairStatus(str, Enum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class RepairCheckResult:
    name: str
    status: RepairStatus
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    blocker: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "metrics": self.metrics,
            "blocker": self.blocker,
        }


@dataclass(frozen=True)
class RepairActionResult:
    name: str
    status: RepairStatus
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "metrics": self.metrics,
            "artifact_paths": self.artifact_paths,
        }


@dataclass(frozen=True)
class RepairStageResult:
    name: str
    checks_before: list[RepairCheckResult] = field(default_factory=list)
    actions: list[RepairActionResult] = field(default_factory=list)
    checks_after: list[RepairCheckResult] = field(default_factory=list)
    remaining_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "checks_before": [check.to_dict() for check in self.checks_before],
            "actions": [action.to_dict() for action in self.actions],
            "checks_after": [check.to_dict() for check in self.checks_after],
            "remaining_blockers": self.remaining_blockers,
        }


@dataclass(frozen=True)
class RepairRunSummary:
    trade_date: str
    mode: str
    final_status: RepairStatus
    checks_before: list[RepairCheckResult] = field(default_factory=list)
    actions: list[RepairActionResult] = field(default_factory=list)
    checks_after: list[RepairCheckResult] = field(default_factory=list)
    stages: list[RepairStageResult] = field(default_factory=list)
    remaining_blockers: list[str] = field(default_factory=list)
    remaining_non_blockers: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "mode": self.mode,
            "final_status": self.final_status.value,
            "checks_before": [check.to_dict() for check in self.checks_before],
            "actions": [action.to_dict() for action in self.actions],
            "checks_after": [check.to_dict() for check in self.checks_after],
            "stages": [stage.to_dict() for stage in self.stages],
            "remaining_blockers": self.remaining_blockers,
            "remaining_non_blockers": self.remaining_non_blockers,
            "next_actions": self.next_actions,
        }
