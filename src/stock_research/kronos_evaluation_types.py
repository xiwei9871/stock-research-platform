from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any

from stock_research.assets import asset_id_from_baostock_code


_ALLOWED_EXCHANGES = frozenset({"SH", "SZ", "BJ"})
_ALLOWED_MODELS = frozenset({"small", "base"})
_CANONICAL_ASSET_RE = re.compile(r"^CN:(SH|SZ|BJ):(\d{6})$", re.IGNORECASE)
_BAOSTOCK_ASSET_RE = re.compile(r"^(sh|sz|bj)\.(\d{6})$", re.IGNORECASE)
_EXCHANGE_SUFFIX_ASSET_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.IGNORECASE)
_BARE_ASSET_RE = re.compile(r"^\d{6}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_HISTORY_NUMERIC_FIELDS = ("open", "high", "low", "close", "volume", "amount")
DEFAULT_KRONOS_SEED = 20260806

ExchangeResolver = Callable[[str], str | Iterable[str] | None]


def canonical_json_fingerprint(value: Any) -> str:
    """Return a stable SHA-256 fingerprint for a JSON-compatible value."""

    canonical_json = json.dumps(
        _json_compatible(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


def normalize_asset_ids(
    asset_ids: Iterable[str],
    exchange_resolver: ExchangeResolver | None = None,
) -> tuple[str, ...]:
    """Normalize supported stock identifiers without performing database I/O.

    ``exchange_resolver`` is called only for a bare six-digit symbol. It may
    return one exchange string or an iterable of candidate exchange strings;
    exactly one of ``SH``, ``SZ``, or ``BJ`` must remain after normalization.
    """

    if isinstance(asset_ids, (str, bytes)):
        raise ValueError("asset_ids must be an iterable of asset ID strings")

    try:
        raw_asset_ids = tuple(asset_ids)
    except TypeError as exc:
        raise ValueError("asset_ids must be an iterable of asset ID strings") from exc

    normalized: list[str] = []
    for raw_asset_id in raw_asset_ids:
        normalized_asset_id = _normalize_asset_id(raw_asset_id, exchange_resolver)
        if normalized_asset_id in normalized:
            raise ValueError("asset_ids must be unique after normalization")
        normalized.append(normalized_asset_id)
    return tuple(normalized)


def _normalize_asset_id(
    raw_asset_id: str,
    exchange_resolver: ExchangeResolver | None,
) -> str:
    if not isinstance(raw_asset_id, str):
        raise ValueError("asset IDs must be strings")

    value = raw_asset_id.strip()
    if not value:
        raise ValueError("asset IDs must not be empty")

    match = _CANONICAL_ASSET_RE.fullmatch(value)
    if match:
        return _asset_id_from_exchange_symbol(match.group(1), match.group(2))

    match = _BAOSTOCK_ASSET_RE.fullmatch(value)
    if match:
        return _asset_id_from_exchange_symbol(match.group(1), match.group(2))

    match = _EXCHANGE_SUFFIX_ASSET_RE.fullmatch(value)
    if match:
        return _asset_id_from_exchange_symbol(match.group(2), match.group(1))

    if _BARE_ASSET_RE.fullmatch(value):
        if exchange_resolver is None:
            raise ValueError(
                f"bare six-digit asset ID {value!r} requires exchange_resolver"
            )
        exchange = _resolve_unique_exchange(value, exchange_resolver)
        return _asset_id_from_exchange_symbol(exchange, value)

    raise ValueError(f"invalid asset ID: {raw_asset_id!r}")


def _resolve_unique_exchange(symbol: str, resolver: ExchangeResolver) -> str:
    try:
        resolved = resolver(symbol)
    except Exception as exc:  # noqa: BLE001 - resolver failures are validation failures.
        raise ValueError(
            f"bare asset ID {symbol!r} did not resolve to a unique exchange"
        ) from exc

    if resolved is None:
        candidates: tuple[object, ...] = ()
    elif isinstance(resolved, str):
        candidates = (resolved,)
    else:
        try:
            candidates = tuple(resolved)
        except TypeError:
            candidates = (resolved,)

    exchanges = {
        str(candidate).strip().upper()
        for candidate in candidates
        if str(candidate).strip()
    }
    if len(exchanges) != 1 or not exchanges.issubset(_ALLOWED_EXCHANGES):
        raise ValueError(
            f"bare asset ID {symbol!r} did not resolve to a unique exchange"
        )
    return next(iter(exchanges))


def _asset_id_from_exchange_symbol(exchange: str, symbol: str) -> str:
    normalized_exchange = exchange.strip().upper()
    if normalized_exchange not in _ALLOWED_EXCHANGES:
        raise ValueError(f"unsupported exchange: {exchange!r}")
    try:
        return asset_id_from_baostock_code(
            f"{normalized_exchange.lower()}.{symbol}"
        )
    except ValueError as exc:
        raise ValueError(
            f"invalid stock code for exchange {normalized_exchange}: {symbol}"
        ) from exc


@dataclass(frozen=True)
class KronosEvaluationConfig:
    """Validated rolling-evaluation settings with one canonical default seed."""

    asset_ids: tuple[str, ...]
    start_date: str
    end_date: str
    input_window: int = 250
    roll_step: int = 1
    forecast_horizon: int = 10
    evaluation_horizons: tuple[int, ...] = (1, 3, 5, 10)
    sample_count: int = 20
    models: tuple[str, ...] = ("small", "base")
    adjust_type: str = "qfq"
    db_service: str = "stock_research"
    predict_url: str = "http://192.168.3.187:8123"
    token_env: str = "KRONOS_INTERNAL_TOKEN"
    timeout_seconds: float = 60.0
    seed: int | None = DEFAULT_KRONOS_SEED
    frequency: str = "1d"
    primary_horizon: int = 1
    include_latest_forecast: bool = False
    fallback: bool = False
    experiment_id: str = ""
    config_fingerprint: str = ""

    def __post_init__(self) -> None:
        normalized_asset_ids = normalize_asset_ids(self.asset_ids)
        if not normalized_asset_ids:
            raise ValueError("asset_ids must not be empty")
        object.__setattr__(self, "asset_ids", normalized_asset_ids)

        normalized_start_date = _normalize_date("start_date", self.start_date)
        normalized_end_date = _normalize_date("end_date", self.end_date)
        if normalized_start_date > normalized_end_date:
            raise ValueError("start_date must be on or before end_date")
        object.__setattr__(self, "start_date", normalized_start_date)
        object.__setattr__(self, "end_date", normalized_end_date)

        _require_positive_int("input_window", self.input_window)
        _require_positive_int("roll_step", self.roll_step)
        _require_int_in_range("forecast_horizon", self.forecast_horizon, 1, 10)
        object.__setattr__(
            self,
            "evaluation_horizons",
            _normalize_horizons(self.evaluation_horizons, self.forecast_horizon),
        )
        _require_int_in_range("sample_count", self.sample_count, 1, 100)
        object.__setattr__(self, "models", _normalize_models(self.models))

        for field_name in ("adjust_type", "db_service", "predict_url", "token_env"):
            object.__setattr__(
                self,
                field_name,
                _require_non_empty_string(field_name, getattr(self, field_name)),
            )

        object.__setattr__(
            self,
            "timeout_seconds",
            _normalize_timeout_seconds(self.timeout_seconds),
        )

        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("seed must be an integer or None")

        normalized_frequency = _require_non_empty_string("frequency", self.frequency)
        if normalized_frequency != "1d":
            raise ValueError("frequency must be 1d")
        object.__setattr__(self, "frequency", normalized_frequency)
        _require_int_in_range(
            "primary_horizon", self.primary_horizon, 1, self.forecast_horizon
        )
        if self.primary_horizon not in self.evaluation_horizons:
            raise ValueError("primary_horizon must be in evaluation_horizons")
        if not isinstance(self.include_latest_forecast, bool):
            raise ValueError("include_latest_forecast must be a boolean")
        if self.fallback is not False:
            raise ValueError("fallback must be false")
        if not isinstance(self.experiment_id, str):
            raise ValueError("experiment_id must be a string")
        if not isinstance(self.config_fingerprint, str):
            raise ValueError("config_fingerprint must be a string")


def _normalize_date(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO date string")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date string") from exc


def _normalize_timeout_seconds(value: object) -> float:
    """Normalize timeout values and report conversion overflow as ValueError."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("timeout_seconds must be a positive finite number")
    try:
        seconds = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds must be a positive finite number") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("timeout_seconds must be a positive finite number")
    return seconds


def _require_positive_int(field_name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_int_in_range(field_name: str, value: int, minimum: int, maximum: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")


def _normalize_horizons(
    horizons: Iterable[int],
    forecast_horizon: int,
) -> tuple[int, ...]:
    if isinstance(horizons, (str, bytes)):
        raise ValueError("evaluation_horizons must contain positive integers")
    try:
        normalized = tuple(horizons)
    except TypeError as exc:
        raise ValueError("evaluation_horizons must contain positive integers") from exc
    if not normalized or any(
        isinstance(horizon, bool)
        or not isinstance(horizon, int)
        or horizon <= 0
        or horizon > forecast_horizon
        for horizon in normalized
    ):
        raise ValueError(
            "evaluation_horizons must contain positive values no greater than "
            "forecast_horizon"
        )
    if len(set(normalized)) != len(normalized) or normalized != tuple(sorted(normalized)):
        raise ValueError("evaluation_horizons must be strictly increasing")
    return normalized


def _normalize_models(models: Iterable[str]) -> tuple[str, ...]:
    if isinstance(models, (str, bytes)):
        raise ValueError("models must contain only small or base")
    try:
        normalized = tuple(model.strip().lower() for model in models)
    except (AttributeError, TypeError) as exc:
        raise ValueError("models must contain only small or base") from exc
    if not normalized or any(model not in _ALLOWED_MODELS for model in normalized):
        raise ValueError("models must contain only small or base")
    if len(set(normalized)) != len(normalized):
        raise ValueError("models must be unique")
    return normalized


def _require_non_empty_string(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _freeze_json_value(value: Any, field_name: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must contain finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        frozen_mapping: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} object keys must be strings")
            frozen_mapping[key] = _freeze_json_value(
                item, f"{field_name}.{key}"
            )
        return MappingProxyType(frozen_mapping)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json_value(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        )
    raise ValueError(
        f"{field_name} contains unsupported JSON value type "
        f"{type(value).__name__}"
    )


def thaw_json_value(value: Any) -> Any:
    """Convert frozen snapshot JSON values into ordinary JSON-serializable data."""

    if isinstance(value, Mapping):
        return {key: thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"unsupported frozen JSON value type: {type(value).__name__}")


def _normalize_timestamp_sequence(
    field_name: str,
    timestamps: Iterable[str],
) -> tuple[str, ...]:
    if isinstance(timestamps, (str, bytes)):
        raise ValueError(f"{field_name} must be an iterable of ISO date strings")
    try:
        raw_timestamps = tuple(timestamps)
    except TypeError as exc:
        raise ValueError(
            f"{field_name} must be an iterable of ISO date strings"
        ) from exc

    normalized: list[str] = []
    for index, timestamp in enumerate(raw_timestamps):
        normalized_timestamp = _normalize_date(
            f"{field_name}[{index}]", timestamp
        )
        if normalized and normalized_timestamp <= normalized[-1]:
            raise ValueError(f"{field_name} must be strictly increasing")
        normalized.append(normalized_timestamp)
    return tuple(normalized)


def _require_finite_numeric(field_name: str, value: Any) -> None:
    if isinstance(value, (str, bytes, bool)) or value is None:
        raise ValueError(f"{field_name} must be a finite numeric value")
    try:
        numeric = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite numeric value") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be a finite numeric value")


def _normalize_snapshot_rows(
    field_name: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    required_numeric_fields: tuple[str, ...],
) -> tuple[Mapping[str, Any], ...]:
    if isinstance(rows, (str, bytes, Mapping)):
        raise ValueError(f"{field_name} must be an iterable of mapping rows")
    try:
        raw_rows = tuple(rows)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be an iterable of mapping rows") from exc

    normalized: list[Mapping[str, Any]] = []
    previous_timestamp: str | None = None
    for index, row in enumerate(raw_rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{field_name}[{index}] must be a mapping")
        if "timestamp" not in row:
            raise ValueError(f"{field_name}[{index}] missing timestamp")
        timestamp = _normalize_date(
            f"{field_name}[{index}].timestamp", row["timestamp"]
        )
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ValueError(f"{field_name} timestamps must be strictly increasing")
        previous_timestamp = timestamp

        normalized_row = dict(row)
        normalized_row["timestamp"] = timestamp
        for numeric_field in required_numeric_fields:
            if numeric_field not in row:
                raise ValueError(
                    f"{field_name}[{index}] missing required field {numeric_field}"
                )
        numeric_fields = set(required_numeric_fields).union(
            numeric_field
            for numeric_field in _HISTORY_NUMERIC_FIELDS
            if numeric_field in row
        )
        for numeric_field in numeric_fields:
            _require_finite_numeric(
                f"{field_name}[{index}].{numeric_field}", row[numeric_field]
            )
        normalized.append(_freeze_json_value(normalized_row, f"{field_name}[{index}]"))
    return tuple(normalized)


@dataclass(frozen=True)
class RollingSnapshot:
    asset_id: str
    origin_date: str
    history: tuple[Mapping[str, Any], ...]
    future_timestamps: tuple[str, ...]
    realized: tuple[Mapping[str, Any], ...]
    input_fingerprint: str
    status: str
    reason: str | None = None

    def __post_init__(self) -> None:
        normalized_asset_id = normalize_asset_ids((self.asset_id,))[0]
        object.__setattr__(self, "asset_id", normalized_asset_id)

        normalized_origin_date = _normalize_date("origin_date", self.origin_date)
        object.__setattr__(self, "origin_date", normalized_origin_date)

        normalized_history = _normalize_snapshot_rows(
            "history",
            self.history,
            required_numeric_fields=_HISTORY_NUMERIC_FIELDS,
        )
        object.__setattr__(self, "history", normalized_history)

        normalized_future_timestamps = _normalize_timestamp_sequence(
            "future_timestamps", self.future_timestamps
        )
        if any(
            timestamp <= normalized_origin_date
            for timestamp in normalized_future_timestamps
        ):
            raise ValueError("future_timestamps must be after origin_date")
        object.__setattr__(self, "future_timestamps", normalized_future_timestamps)

        normalized_realized = _normalize_snapshot_rows(
            "realized",
            self.realized,
            required_numeric_fields=(),
        )
        if len(normalized_realized) > len(normalized_future_timestamps):
            raise ValueError("realized cannot contain more rows than future_timestamps")
        if any(
            row["timestamp"] != normalized_future_timestamps[index]
            for index, row in enumerate(normalized_realized)
        ):
            raise ValueError("realized timestamps must match future_timestamps")
        object.__setattr__(self, "realized", normalized_realized)

        if any(
            row["timestamp"] > normalized_origin_date for row in normalized_history
        ):
            raise ValueError("history timestamps must not be after origin_date")

        if not isinstance(self.input_fingerprint, str) or not _FINGERPRINT_RE.fullmatch(
            self.input_fingerprint
        ):
            raise ValueError("input_fingerprint must be a 64-character hexadecimal SHA-256")
        object.__setattr__(self, "input_fingerprint", self.input_fingerprint.lower())

        status = _require_non_empty_string("status", self.status)
        object.__setattr__(self, "status", status)
        if self.reason is not None:
            if not isinstance(self.reason, str):
                raise ValueError("reason must be a string or None")
            object.__setattr__(self, "reason", self.reason.strip())

    @property
    def key(self) -> str:
        return f"{self.asset_id}|{self.origin_date}"


def snapshot_to_json_payload(snapshot: RollingSnapshot) -> dict[str, Any]:
    """Return an independent JSON-compatible payload for a frozen snapshot."""

    if not isinstance(snapshot, RollingSnapshot):
        raise TypeError("snapshot must be a RollingSnapshot")
    return thaw_json_value(
        {
            "asset_id": snapshot.asset_id,
            "origin_date": snapshot.origin_date,
            "history": snapshot.history,
            "future_timestamps": snapshot.future_timestamps,
            "realized": snapshot.realized,
            "input_fingerprint": snapshot.input_fingerprint,
            "status": snapshot.status,
            "reason": snapshot.reason,
        }
    )
