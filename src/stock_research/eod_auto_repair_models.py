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
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    validation_result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "metrics": self.metrics,
            "artifact_paths": self.artifact_paths,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "exit_code": self.exit_code,
            "validation_result": self.validation_result,
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
class RepairLoopCycleResult:
    cycle_number: int
    checks_before: list[RepairCheckResult] = field(default_factory=list)
    actions: list[RepairActionResult] = field(default_factory=list)
    checks_after: list[RepairCheckResult] = field(default_factory=list)
    remaining_blockers: list[str] = field(default_factory=list)
    stop_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_number": self.cycle_number,
            "checks_before": [check.to_dict() for check in self.checks_before],
            "actions": [action.to_dict() for action in self.actions],
            "checks_after": [check.to_dict() for check in self.checks_after],
            "remaining_blockers": self.remaining_blockers,
            "stop_reason": self.stop_reason,
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
    loop_cycles: list[RepairLoopCycleResult] = field(default_factory=list)
    remaining_blockers: list[str] = field(default_factory=list)
    remaining_non_blockers: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    initial_classification: dict[str, str] = field(default_factory=dict)
    final_classification: dict[str, str] = field(default_factory=dict)
    loop_stop_reason: str = ""
    dry_run: bool = False
    max_cycles: int | None = None
    warnings: list[str] = field(default_factory=list)
    infrastructure_issues: list[str] = field(default_factory=list)
    recommended_followups: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        browser_check = next(
            (
                check
                for check in reversed(self.checks_after or self.checks_before)
                if check.name == "dashboard_browser_acceptance"
            ),
            None,
        )
        browser_action = next(
            (
                action
                for action in reversed(self.actions)
                if action.name == "dashboard_browser_acceptance"
                or action.validation_result.get("component") == "dashboard_browser_acceptance"
            ),
            None,
        )
        return {
            "trade_date": self.trade_date,
            "mode": self.mode,
            "final_status": self.final_status.value,
            "checks_before": [check.to_dict() for check in self.checks_before],
            "actions": [action.to_dict() for action in self.actions],
            "checks_after": [check.to_dict() for check in self.checks_after],
            "stages": [stage.to_dict() for stage in self.stages],
            "loop_cycles": [cycle.to_dict() for cycle in self.loop_cycles],
            "remaining_blockers": self.remaining_blockers,
            "remaining_non_blockers": self.remaining_non_blockers,
            "next_actions": self.next_actions,
            "initial_classification": self.initial_classification,
            "final_classification": self.final_classification,
            "loop_stop_reason": self.loop_stop_reason,
            "dry_run": self.dry_run,
            "max_cycles": self.max_cycles,
            "warnings": self.warnings,
            "infrastructure_issues": self.infrastructure_issues,
            "recommended_followups": self.recommended_followups,
            "browser_acceptance": {
                "check": browser_check.to_dict() if browser_check else None,
                "action": browser_action.to_dict() if browser_action else None,
            },
        }
