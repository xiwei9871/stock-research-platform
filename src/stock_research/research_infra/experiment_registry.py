from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


VALID_REUSE_STATUSES = {
    "draft",
    "validated",
    "rejected",
    "monitor_only",
    "superseded",
}


class ExperimentRegistryValidationError(ValueError):
    """Raised when an experiment registry record is invalid."""


class DuplicateExperimentError(ValueError):
    """Raised when a registry contains duplicate experiment identifiers."""


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    created_at: str
    objective: str
    hypothesis: str
    sample_window: dict[str, Any]
    universe: dict[str, Any]
    feature_set_id: str
    label_id: str
    model_or_rule_version: str
    constraints: dict[str, Any]
    artifact_paths: dict[str, Any]
    conclusion: str
    reuse_status: str

    def __post_init__(self) -> None:
        if self.reuse_status not in VALID_REUSE_STATUSES:
            raise ExperimentRegistryValidationError(
                f"invalid reuse_status {self.reuse_status!r}; "
                f"expected one of {sorted(VALID_REUSE_STATUSES)}"
            )
        missing = [
            field_name
            for field_name in [
                "experiment_id",
                "created_at",
                "objective",
                "hypothesis",
                "feature_set_id",
                "label_id",
                "model_or_rule_version",
                "conclusion",
            ]
            if not str(getattr(self, field_name)).strip()
        ]
        if not self.sample_window:
            missing.append("sample_window")
        if not self.universe:
            missing.append("universe")
        if not self.artifact_paths:
            missing.append("artifact_paths")
        if missing:
            raise ExperimentRegistryValidationError(
                "missing required experiment registry fields: " + ", ".join(missing)
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExperimentRecord:
        return cls(
            experiment_id=str(payload.get("experiment_id", "")),
            created_at=str(payload.get("created_at", "")),
            objective=str(payload.get("objective", "")),
            hypothesis=str(payload.get("hypothesis", "")),
            sample_window=dict(payload.get("sample_window") or {}),
            universe=dict(payload.get("universe") or {}),
            feature_set_id=str(payload.get("feature_set_id", "")),
            label_id=str(payload.get("label_id", "")),
            model_or_rule_version=str(payload.get("model_or_rule_version", "")),
            constraints=dict(payload.get("constraints") or {}),
            artifact_paths=dict(payload.get("artifact_paths") or {}),
            conclusion=str(payload.get("conclusion", "")),
            reuse_status=str(payload.get("reuse_status", "")),
        )


def append_experiment_record(path: str | Path, record: ExperimentRecord) -> None:
    registry_path = Path(path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def read_experiment_registry(path: str | Path) -> list[ExperimentRecord]:
    registry_path = Path(path)
    if not registry_path.exists():
        return []

    records: list[ExperimentRecord] = []
    seen_ids: set[str] = set()
    lines = registry_path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        record = ExperimentRecord.from_dict(json.loads(line))
        if record.experiment_id in seen_ids:
            raise DuplicateExperimentError(
                f"duplicate experiment_id {record.experiment_id!r} at line {line_number}"
            )
        seen_ids.add(record.experiment_id)
        records.append(record)
    return records
