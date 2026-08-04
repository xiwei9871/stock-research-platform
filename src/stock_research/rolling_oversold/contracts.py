"""Stable inputs, states, and schema for rolling oversold snapshots."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from math import isfinite
from numbers import Real
import re


class GateStatus(str, Enum):
    CONFIRMED = "confirmed"
    WATCH = "watch"
    BLOCKED = "blocked"


class RecoveryState(str, Enum):
    FRESH_OVERSOLD = "fresh_oversold"
    REPAIRING = "repairing"
    REPAIRED = "repaired"
    STRUCTURALLY_WEAK = "structurally_weak"
    UNKNOWN = "unknown"


class StockLifecycle(str, Enum):
    NEW_OVERSOLD = "new_oversold"
    EXPECTED_REPAIR = "expected_repair"
    CONFIRMED_REPAIR = "confirmed_repair"
    REPAIR_WITH_RESIDUAL_SPACE = "repair_with_residual_space"
    INVALIDATED = "invalidated"


class SectorResearchEligibility(str, Enum):
    """Whether a sector has enough point-in-time evidence for research."""

    ELIGIBLE = "eligible"
    WATCH = "watch"
    BLOCKED_DATA = "blocked_data"


DEFAULT_INDEX_IDS = (
    "SSE_COMPOSITE",
    "SZSE_COMPONENT",
    "CSI_300",
    "STAR_50",
)
VALID_ADJUST_TYPES = ("raw", "qfq", "hfq")
TARGET_CONCEPT_CODE_PATTERN = re.compile(r"^[0-9]{6}$")

SECTOR_FEATURE_COLUMNS = (
    "sector_low_date_20d",
    "sector_low_close_20d",
    "sector_recovery_from_low_20d",
    "sector_days_since_low_20d",
    "sector_volume_ratio_5_20",
    "sector_ma5_slope_5d",
    "sector_ma10_slope_10d",
    "sector_research_eligibility",
)

REQUIRED_SECTOR_COLUMNS = frozenset(
    (
        "sector_system",
        "sector_code",
        "sector_name",
        "sector_oversold_score",
        "sector_repairability_score",
        "sector_direction_score",
        "sector_recovery_state",
        "sector_gate_status",
        *SECTOR_FEATURE_COLUMNS,
    )
)

REQUIRED_SNAPSHOT_COLUMNS = frozenset(
    (
        "snapshot_id",
        "anchor_date",
        "data_cutoff_date",
        "score_version",
        "market_regime",
        "sector_system",
        "sector_code",
        "sector_name",
        "sector_oversold_score",
        "sector_repairability_score",
        "sector_direction_score",
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
    # Full-sector batch publication is deliberately separate from the
    # compatibility ``stock_top_n`` setting used by the legacy mixed-universe
    # path.  Appending the field keeps positional construction of the old
    # config compatible.
    sector_output_top_n: int = 10
    # An explicit target scope is reserved for THS concept runs.  Appending
    # this field preserves all legacy positional construction semantics.
    concept_codes: Sequence[str] | None = None

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
            "concept_codes",
            _normalize_optional_concept_codes(self.concept_codes),
        )
        if self.concept_codes is not None and self.concept_systems != ("ths",):
            raise ValueError("concept_codes requires concept_systems=('ths',)")
        object.__setattr__(
            self,
            "index_ids",
            _normalize_strings("index_ids", self.index_ids),
        )

        _validate_positive_integer("sector_top_n", self.sector_top_n)
        _validate_positive_integer("stock_top_n", self.stock_top_n)
        _validate_positive_integer("sector_output_top_n", self.sector_output_top_n)
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
    return sorted(REQUIRED_SNAPSHOT_COLUMNS - present)


def validate_sector_columns(columns: Iterable[str]) -> list[str]:
    """Return required sector column names absent from *columns*, sorted."""

    present = set(columns)
    return sorted(REQUIRED_SECTOR_COLUMNS - present)


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


def _normalize_optional_concept_codes(
    values: Sequence[str] | None,
) -> tuple[str, ...] | None:
    if values is None:
        return None
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError("concept_codes must be a sequence of six-digit strings")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip() if isinstance(raw, str) else str(raw).strip()
        if not value:
            raise ValueError("concept_codes must not contain empty values")
        if not TARGET_CONCEPT_CODE_PATTERN.fullmatch(value):
            raise ValueError(f"concept_codes must contain six-digit THS codes: {value!r}")
        if value in seen:
            raise ValueError(f"concept_codes must not contain duplicates: {value}")
        seen.add(value)
        normalized.append(value)
    if not normalized:
        raise ValueError("concept_codes must not be empty")
    return tuple(normalized)


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
