from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from stock_research.assets import asset_id_from_baostock_code


_ALLOWED_EXCHANGES = frozenset({"SH", "SZ", "BJ"})
_ALLOWED_MODELS = frozenset({"small", "base"})
_CANONICAL_ASSET_RE = re.compile(r"^CN:(SH|SZ|BJ):(\d{6})$", re.IGNORECASE)
_BAOSTOCK_ASSET_RE = re.compile(r"^(sh|sz|bj)\.(\d{6})$", re.IGNORECASE)
_EXCHANGE_SUFFIX_ASSET_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.IGNORECASE)
_BARE_ASSET_RE = re.compile(r"^\d{6}$")

ExchangeResolver = Callable[[str], str | Iterable[str] | None]


def canonical_json_fingerprint(value: Any) -> str:
    """Return a stable SHA-256 fingerprint for a JSON-compatible value."""

    canonical_json = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


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
    seed: int | None = 20260806

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

        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(float(self.timeout_seconds))
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))

        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("seed must be an integer or None")


def _normalize_date(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO date string")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date string") from exc


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


@dataclass(frozen=True)
class RollingSnapshot:
    asset_id: str
    origin_date: str
    history: tuple[dict[str, Any], ...]
    future_timestamps: tuple[str, ...]
    realized: tuple[dict[str, Any], ...]
    input_fingerprint: str
    status: str
    reason: str | None = None

    @property
    def key(self) -> str:
        return f"{self.asset_id}|{self.origin_date}"
