"""Stable inputs, states, and schema for rolling oversold snapshots."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from math import isfinite
from numbers import Real


class GateStatus(str, Enum):
    CONFIRMED = "confirmed"
    WATCH = "watch"
    BLOCKED = "blocked"


class RecoveryState(str, Enum):
    FRESH_OVERSOLD = "fresh_oversold"
    REPAIRING = "repairing"
    REPAIRED = "repaired"
    REPAIR_WITH_RESIDUAL_SPACE = "repair_with_residual_space"
    STRUCTURALLY_WEAK = "structurally_weak"
    UNKNOWN = "unknown"


class StockLifecycle(str, Enum):
    NEW_OVERSOLD = "new_oversold"
    EXPECTED_REPAIR = "expected_repair"
    CONFIRMED_REPAIR = "confirmed_repair"
    REPAIR_WITH_RESIDUAL_SPACE = "repair_with_residual_space"
    INVALIDATED = "invalidated"


DEFAULT_INDEX_IDS = (
    "SSE_COMPOSITE",
    "SZSE_COMPONENT",
    "CSI_300",
    "STAR_50",
    "BSE_50",
)
VALID_ADJUST_TYPES = ("raw", "qfq", "hfq")

REQUIRED_SNAPSHOT_COLUMNS = (
    "snapshot_id",
    "anchor_date",
    "data_cutoff_date",
    "score_version",
    "market_regime",
    "sector_system",
    "sector_id",
    "sector_name",
    "sector_score",
    "sector_rank",
    "sector_recovery_state",
    "sector_gate_status",
    "asset_id",
    "stock_score",
    "stock_rank",
    "stock_lifecycle",
    "previous_snapshot_id",
    "rank_delta",
    "lifecycle_delta",
)


@dataclass(frozen=True)
class RollingOversoldConfig:
    """Validated configuration shared by rolling oversold job stages."""

    anchor_start_date: date
    anchor_end_date: date | None = None
    forecast_horizons: Sequence[int] = (1, 3, 5)
    industry_systems: Sequence[str] | None = None
    concept_systems: Sequence[str] | None = None
    index_ids: Sequence[str] = DEFAULT_INDEX_IDS
    sector_top_n: int = 30
    stock_top_n: int = 20
    repair_trigger_return: float = 0.10
    residual_high_distance: float = 0.20
    score_version: str = "rolling_oversold_v1"
    adjust_type: str = "qfq"
    runtime_budget_seconds: int = 3600

    def __post_init__(self) -> None:
        _validate_date("anchor_start_date", self.anchor_start_date)
        if self.anchor_end_date is not None:
            _validate_date("anchor_end_date", self.anchor_end_date)
            if self.anchor_end_date < self.anchor_start_date:
                raise ValueError("anchor_end_date must not precede anchor_start_date")

        horizons = _normalize_positive_integers("forecast_horizons", self.forecast_horizons)
        if horizons != tuple(sorted(horizons)) or len(set(horizons)) != len(horizons):
            raise ValueError("forecast_horizons must be unique and sorted ascending")
        object.__setattr__(self, "forecast_horizons", horizons)

        object.__setattr__(
            self,
            "industry_systems",
            _normalize_optional_strings("industry_systems", self.industry_systems),
        )
        object.__setattr__(
            self,
            "concept_systems",
            _normalize_optional_strings("concept_systems", self.concept_systems),
        )
        object.__setattr__(
            self,
            "index_ids",
            _normalize_strings("index_ids", self.index_ids),
        )

        _validate_positive_integer("sector_top_n", self.sector_top_n)
        _validate_positive_integer("stock_top_n", self.stock_top_n)
        _validate_open_unit_interval("repair_trigger_return", self.repair_trigger_return)
        _validate_open_unit_interval("residual_high_distance", self.residual_high_distance)
        if not isinstance(self.score_version, str) or not self.score_version.strip():
            raise ValueError("score_version must be a non-empty string")
        if self.adjust_type not in VALID_ADJUST_TYPES:
            allowed = ", ".join(VALID_ADJUST_TYPES)
            raise ValueError(f"adjust_type must be one of {allowed}")
        _validate_positive_integer("runtime_budget_seconds", self.runtime_budget_seconds)


def validate_snapshot_columns(columns: Iterable[str]) -> list[str]:
    """Return required snapshot column names absent from *columns*, sorted."""

    present = set(columns)
    return sorted(set(REQUIRED_SNAPSHOT_COLUMNS) - present)


def _validate_date(field_name: str, value: object) -> None:
    if not isinstance(value, date):
        raise ValueError(f"{field_name} must be a date")


def _normalize_positive_integers(field_name: str, values: Sequence[int]) -> tuple[int, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be a sequence of positive integers")
    normalized = tuple(values)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    for value in normalized:
        _validate_positive_integer(field_name, value)
    return normalized


def _normalize_optional_strings(
    field_name: str, values: Sequence[str] | None
) -> tuple[str, ...] | None:
    return None if values is None else _normalize_strings(field_name, values)


def _normalize_strings(field_name: str, values: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be a sequence of strings")
    normalized = tuple(values)
    if not normalized or any(not isinstance(value, str) or not value.strip() for value in normalized):
        raise ValueError(f"{field_name} must contain non-empty strings")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _validate_positive_integer(field_name: str, value: object) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _validate_open_unit_interval(field_name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not isfinite(value)
        or not 0.0 < value < 1.0
    ):
        raise ValueError(f"{field_name} must be between 0 and 1, exclusive")
