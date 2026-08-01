from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any, Iterable


DB_ONLY = "db_only"
DEFAULT_RUNTIME_BUDGET_SECONDS = 3600.0


@dataclass(frozen=True)
class DataGap:
    """One database coverage gap that must be handled by a separate backfill."""

    dataset: str
    asset_id: str
    start_date: str | None
    end_date: str | None
    expected_rows: int
    actual_rows: int
    reason: str

    def __post_init__(self) -> None:
        if not str(self.dataset).strip():
            raise ValueError("data gap dataset must be non-empty")
        if not str(self.asset_id).strip():
            raise ValueError("data gap asset_id must be non-empty")
        if type(self.expected_rows) is not int or self.expected_rows < 0:
            raise ValueError("data gap expected_rows must be a non-negative integer")
        if type(self.actual_rows) is not int or self.actual_rows < 0:
            raise ValueError("data gap actual_rows must be a non-negative integer")
        if not str(self.reason).strip():
            raise ValueError("data gap reason must be non-empty")


class StrategyRuntimeTimeout(RuntimeError):
    """Raised when a strategy reaches its configured wall-clock budget."""


@dataclass
class StrategyRuntimeBudget:
    timeout_seconds: float = DEFAULT_RUNTIME_BUDGET_SECONDS
    started_at: float | None = None
    stage_timings_seconds: dict[str, float] = field(default_factory=dict)
    _stage_started_at: dict[str, float] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.timeout_seconds, bool) or self.timeout_seconds <= 0:
            raise ValueError("runtime timeout_seconds must be positive")

    def start(self) -> float:
        if self.started_at is None:
            self.started_at = monotonic()
        return self.started_at

    def begin_stage(self, stage: str) -> None:
        name = _stage_name(stage)
        self.start()
        self.checkpoint(name)
        self._stage_started_at[name] = monotonic()

    def end_stage(self, stage: str) -> float:
        name = _stage_name(stage)
        started = self._stage_started_at.pop(name, None)
        if started is None:
            raise ValueError(f"runtime stage {name} was not started")
        elapsed = max(0.0, monotonic() - started)
        self.stage_timings_seconds[name] = elapsed
        self.checkpoint(name)
        return elapsed

    def checkpoint(self, stage: str) -> float:
        name = _stage_name(stage)
        started = self.start()
        elapsed = max(0.0, monotonic() - started)
        if elapsed > float(self.timeout_seconds):
            raise StrategyRuntimeTimeout(
                f"strategy runtime budget exceeded at {name}: "
                f"{elapsed:.3f}s > {float(self.timeout_seconds):.3f}s"
            )
        return elapsed

    def metadata(self) -> dict[str, Any]:
        started = self.start()
        now = monotonic()
        elapsed = max(0.0, now - started)
        timings = dict(self.stage_timings_seconds)
        for stage, stage_started in self._stage_started_at.items():
            timings[stage] = max(0.0, now - stage_started)
        return {
            "runtime_budget_seconds": float(self.timeout_seconds),
            "runtime_seconds": elapsed,
            "stage_timings_seconds": {
                key: float(value)
                for key, value in sorted(timings.items())
            },
        }


def assert_db_only_source(source: str | None) -> None:
    marker = str(source or "").strip().casefold()
    if marker not in {"", DB_ONLY, "database", "database_only"}:
        raise ValueError(
            f"strategy data policy {DB_ONLY} rejects external source: {source}"
        )


def write_backfill_request(
    output_dir: str | Path,
    *,
    strategy: str,
    trade_date: str,
    ranking_version: str,
    gaps: Iterable[DataGap],
    status: str = "blocked_missing_data",
) -> Path:
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    normalized_gaps = sorted(
        (gap if isinstance(gap, DataGap) else DataGap(**gap) for gap in gaps),
        key=lambda gap: (
            gap.dataset,
            gap.asset_id,
            gap.start_date or "",
            gap.end_date or "",
            gap.reason,
        ),
    )
    payload = {
        "strategy": str(strategy),
        "trade_date": str(trade_date),
        "ranking_version": str(ranking_version),
        "data_source_policy": DB_ONLY,
        "status": str(status),
        "gap_count": len(normalized_gaps),
        "gaps": [asdict(gap) for gap in normalized_gaps],
    }
    path = destination / "consumer_oversold_backfill_request.json"
    temporary = destination / f".{path.name}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return path


def _stage_name(stage: str) -> str:
    name = str(stage).strip()
    if not name:
        raise ValueError("runtime stage must be non-empty")
    return name
