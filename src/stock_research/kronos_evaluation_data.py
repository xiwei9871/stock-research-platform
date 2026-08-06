from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from stock_research.db import connect, fetch_all
from stock_research.kronos_evaluation_types import (
    RollingSnapshot,
    canonical_json_fingerprint,
    normalize_asset_ids,
    thaw_json_value,
)


KRONOS_HISTORY_FIELDS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)
DAILY_BAR_COLUMNS = (
    "trade_date",
    "asset_id",
    *KRONOS_HISTORY_FIELDS,
    "trade_status",
    "is_st",
)
REQUIRED_FRAME_COLUMNS = ("trade_date", "asset_id", *KRONOS_HISTORY_FIELDS)
SNAPSHOT_STATUSES = frozenset(
    {"ready", "insufficient_input", "insufficient_truth", "invalid_input"}
)
_ZERO_FINGERPRINT = "0" * 64


DAILY_BARS_SQL = """
SELECT trade_date::text AS trade_date, asset_id, open, high, low, close, volume, amount, trade_status, is_st
FROM market_daily_bar
WHERE adjust_type = %s AND trade_date <= %s AND asset_id = ANY(%s)
ORDER BY asset_id, trade_date
"""

GLOBAL_TRADE_DATES_SQL = """
SELECT DISTINCT trade_date::text AS trade_date
FROM market_daily_bar
WHERE adjust_type = %s AND trade_date <= %s
ORDER BY trade_date
"""


@dataclass(frozen=True)
class _Bar:
    asset_id: str
    timestamp: str
    values: Mapping[str, float]

    def snapshot_row(self) -> dict[str, Any]:
        return {"timestamp": self.timestamp, **dict(self.values)}


def load_daily_bars(
    asset_ids: Sequence[str],
    max_date: str,
    adjust_type: str,
    service: str,
) -> pd.DataFrame:
    """Load the daily bars needed by a frozen rolling evaluation.

    The query deliberately returns only rows through ``max_date`` and binds
    the asset universe as a PostgreSQL array parameter.  The returned frame
    keeps the source columns needed for auditing while the pure builder uses
    only the six Kronos history fields.
    """

    normalized_asset_ids = normalize_asset_ids(asset_ids)
    if not normalized_asset_ids:
        raise ValueError("asset_ids must not be empty")
    normalized_max_date = _normalize_date_value(max_date, "max_date")
    normalized_adjust_type = _require_non_empty_text("adjust_type", adjust_type)
    normalized_service = _require_non_empty_text("service", service)

    with connect(normalized_service) as conn:
        rows = fetch_all(
            conn,
            DAILY_BARS_SQL,
            [normalized_adjust_type, normalized_max_date, list(normalized_asset_ids)],
        )
    return pd.DataFrame.from_records(rows, columns=DAILY_BAR_COLUMNS)


def load_global_trade_dates(
    adjust_type: str,
    max_date: str,
    service: str,
) -> list[str]:
    """Load the ordered global calendar used to select future timestamps."""

    normalized_max_date = _normalize_date_value(max_date, "max_date")
    normalized_adjust_type = _require_non_empty_text("adjust_type", adjust_type)
    normalized_service = _require_non_empty_text("service", service)

    with connect(normalized_service) as conn:
        rows = fetch_all(
            conn,
            GLOBAL_TRADE_DATES_SQL,
            [normalized_adjust_type, normalized_max_date],
        )

    dates = [_normalize_date_value(row["trade_date"], "trade_date") for row in rows]
    _require_strictly_increasing("global trade dates", dates)
    return dates


def prepare_rolling_snapshots(
    asset_ids: Sequence[str],
    max_date: str,
    adjust_type: str,
    service: str,
    input_window: int,
    forecast_horizon: int,
    *,
    origin_dates: Iterable[str] | None = None,
) -> list[RollingSnapshot]:
    """Load bars and the full-market calendar before building snapshots."""

    frame = load_daily_bars(asset_ids, max_date, adjust_type, service)
    trade_dates = load_global_trade_dates(adjust_type, max_date, service)
    return build_rolling_snapshots(
        frame,
        trade_dates,
        input_window,
        forecast_horizon,
        origin_dates=origin_dates,
    )


def build_source_metadata(
    frame: pd.DataFrame,
    *,
    adjust_type: str,
    query_timestamp: str | datetime | pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Return JSON-ready provenance fields for an experiment manifest."""

    _require_frame_columns(frame, ("trade_date",))
    normalized_adjust_type = _require_non_empty_text("adjust_type", adjust_type)
    dates = [
        _normalize_date_value(value, f"frame.trade_date[{index}]")
        for index, value in enumerate(frame["trade_date"].tolist())
    ]
    if query_timestamp is None:
        normalized_query_timestamp = datetime.now(timezone.utc).isoformat()
    elif isinstance(query_timestamp, (datetime, pd.Timestamp)):
        normalized_query_timestamp = query_timestamp.isoformat()
    elif isinstance(query_timestamp, str) and query_timestamp.strip():
        normalized_query_timestamp = query_timestamp.strip()
    else:
        raise ValueError("query_timestamp must be a non-empty timestamp")

    metadata = {
        "adjust_type": normalized_adjust_type,
        "source_table": "market_daily_bar",
        "row_count": int(len(frame)),
        "min_date": min(dates) if dates else None,
        "max_date": max(dates) if dates else None,
        "query_timestamp": normalized_query_timestamp,
    }
    return thaw_json_value(metadata)


def build_rolling_snapshots(
    frame: pd.DataFrame,
    trade_dates: Iterable[str],
    input_window: int,
    forecast_horizon: int,
    *,
    origin_dates: Iterable[str] | None = None,
) -> list[RollingSnapshot]:
    """Build immutable, point-in-time rolling snapshots without future leakage.

    ``trade_dates`` is the authoritative, strictly ordered full-market
    calendar.  It is never inferred from the asset-filtered frame.  By
    default every calendar date is an origin; ``origin_dates`` can restrict
    the origins while still requiring all future timestamps to come from the
    explicit full-market calendar.
    """

    _require_positive_int("input_window", input_window)
    _require_positive_int("forecast_horizon", forecast_horizon)
    calendar = _normalize_date_sequence("trade_dates", trade_dates)
    if origin_dates is None:
        origins = calendar
    else:
        origins = _normalize_date_sequence("origin_dates", origin_dates)
        missing_origins = sorted(set(origins) - set(calendar))
        if missing_origins:
            raise ValueError(
                "origin_dates must be contained in trade_dates: "
                + ", ".join(missing_origins)
            )
    _require_frame_columns(frame, REQUIRED_FRAME_COLUMNS)
    if frame.empty:
        return []

    bars_by_asset, asset_ids = _normalize_bars(frame)
    snapshots: list[RollingSnapshot] = []

    for asset_id in sorted(asset_ids):
        bars = bars_by_asset.get(asset_id, ())
        invalid_reason = _first_invalid_reason(bars)
        valid_bars = tuple(bar for bar in bars if isinstance(bar, _Bar))
        bars_by_date = {bar.timestamp: bar for bar in valid_bars}

        for origin in origins:
            future_timestamps = tuple(
                calendar[
                    bisect_right(calendar, origin) : bisect_right(
                        calendar, origin
                    )
                    + forecast_horizon
                ]
            )

            if invalid_reason is not None:
                snapshots.append(
                    _make_snapshot(
                        asset_id=asset_id,
                        origin_date=origin,
                        history=(),
                        future_timestamps=future_timestamps,
                        realized=(),
                        status="invalid_input",
                        reason=invalid_reason,
                    )
                )
                continue

            history_bars = tuple(
                bar for bar in valid_bars if bar.timestamp <= origin
            )
            history = tuple(
                bar.snapshot_row()
                for bar in history_bars[-input_window:]
            )

            if len(history_bars) < input_window:
                snapshots.append(
                    _make_snapshot(
                        asset_id=asset_id,
                        origin_date=origin,
                        history=history,
                        future_timestamps=future_timestamps,
                        realized=(),
                        status="insufficient_input",
                        reason=(
                            f"only {len(history_bars)} history bars available; "
                            f"input_window={input_window}"
                        ),
                    )
                )
                continue

            realized_rows: list[dict[str, Any]] = []
            missing_truth: str | None = None
            for timestamp in future_timestamps:
                bar = bars_by_date.get(timestamp)
                if bar is None:
                    missing_truth = timestamp
                    break
                realized_rows.append(bar.snapshot_row())

            if (
                len(future_timestamps) < forecast_horizon
                or missing_truth is not None
            ):
                reason = (
                    f"missing real bar for future timestamp {missing_truth}"
                    if missing_truth is not None
                    else (
                        f"only {len(future_timestamps)} future timestamps available; "
                        f"forecast_horizon={forecast_horizon}"
                    )
                )
                snapshots.append(
                    _make_snapshot(
                        asset_id=asset_id,
                        origin_date=origin,
                        history=history,
                        future_timestamps=future_timestamps,
                        realized=tuple(realized_rows),
                        status="insufficient_truth",
                        reason=reason,
                    )
                )
                continue

            snapshots.append(
                _make_snapshot(
                    asset_id=asset_id,
                    origin_date=origin,
                    history=history,
                    future_timestamps=future_timestamps,
                    realized=tuple(realized_rows),
                    status="ready",
                    reason=None,
                )
            )

    return snapshots


def _make_snapshot(
    *,
    asset_id: str,
    origin_date: str,
    history: Iterable[Mapping[str, Any]],
    future_timestamps: Iterable[str],
    realized: Iterable[Mapping[str, Any]],
    status: str,
    reason: str | None,
) -> RollingSnapshot:
    if status not in SNAPSHOT_STATUSES:
        raise ValueError(f"unsupported snapshot status: {status}")

    candidate = RollingSnapshot(
        asset_id=asset_id,
        origin_date=origin_date,
        history=tuple(history),
        future_timestamps=tuple(future_timestamps),
        realized=tuple(realized),
        input_fingerprint=_ZERO_FINGERPRINT,
        status=status,
        reason=reason,
    )
    fingerprint_payload = {
        "asset_id": candidate.asset_id,
        "origin_date": candidate.origin_date,
        "history": thaw_json_value(candidate.history),
    }
    return RollingSnapshot(
        asset_id=candidate.asset_id,
        origin_date=candidate.origin_date,
        history=candidate.history,
        future_timestamps=candidate.future_timestamps,
        realized=candidate.realized,
        input_fingerprint=canonical_json_fingerprint(fingerprint_payload),
        status=status,
        reason=reason,
    )


def _normalize_bars(
    frame: pd.DataFrame,
) -> tuple[dict[str, tuple[object, ...]], set[str]]:
    bars: dict[str, list[object]] = {}
    asset_ids: set[str] = set()
    seen_dates: dict[str, set[str]] = {}
    previous_dates: dict[str, str] = {}
    invalid_reasons: dict[str, str] = {}

    for index, row in frame.iterrows():
        raw_asset_id = row["asset_id"]
        try:
            asset_id = normalize_asset_ids((raw_asset_id,))[0]
        except ValueError as exc:
            raise ValueError(f"invalid asset_id at frame row {index}: {exc}") from exc
        asset_ids.add(asset_id)
        bars.setdefault(asset_id, [])
        seen_dates.setdefault(asset_id, set())

        try:
            timestamp = _normalize_date_value(
                row["trade_date"], f"frame row {index}.trade_date"
            )
        except ValueError as exc:
            invalid_reasons.setdefault(asset_id, str(exc))
            continue
        if timestamp in seen_dates[asset_id]:
            invalid_reasons.setdefault(
                asset_id,
                f"duplicate trade_date {timestamp} for asset {asset_id}",
            )
        elif (
            asset_id in previous_dates
            and timestamp <= previous_dates[asset_id]
        ):
            invalid_reasons.setdefault(
                asset_id,
                f"trade dates for asset {asset_id} must be strictly increasing",
            )
        seen_dates[asset_id].add(timestamp)
        previous_dates[asset_id] = timestamp

        try:
            values = _normalize_history_values(row, asset_id, timestamp)
        except ValueError as exc:
            invalid_reasons.setdefault(asset_id, str(exc))
            continue
        bars[asset_id].append(_Bar(asset_id, timestamp, values))

    for asset_id, reason in invalid_reasons.items():
        bars[asset_id].append(reason)

    return (
        {asset_id: tuple(asset_bars) for asset_id, asset_bars in bars.items()},
        asset_ids,
    )


def _first_invalid_reason(bars: Sequence[object]) -> str | None:
    for bar in bars:
        if isinstance(bar, str):
            return bar
    return None


def _normalize_history_values(
    row: Mapping[str, Any],
    asset_id: str,
    timestamp: str,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for field in KRONOS_HISTORY_FIELDS:
        values[field] = _finite_float(
            row[field], f"{asset_id} {timestamp} {field}"
        )

    if values["high"] < max(values["open"], values["low"], values["close"]):
        raise ValueError(
            f"invalid OHLC relationship for {asset_id} {timestamp}: high"
        )
    if values["low"] > min(values["open"], values["high"], values["close"]):
        raise ValueError(
            f"invalid OHLC relationship for {asset_id} {timestamp}: low"
        )
    return values


def _finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, (str, bytes, bool)) or value is None:
        raise ValueError(f"{field_name} must be a finite numeric value")
    try:
        numeric = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite numeric value") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be a finite numeric value")
    return numeric


def _normalize_date_sequence(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be an iterable of ISO date strings")
    try:
        raw_values = tuple(values)
    except TypeError as exc:
        raise ValueError(
            f"{field_name} must be an iterable of ISO date strings"
        ) from exc

    normalized: list[str] = []
    for index, value in enumerate(raw_values):
        timestamp = _normalize_date_value(value, f"{field_name}[{index}]")
        if normalized and timestamp <= normalized[-1]:
            raise ValueError(f"{field_name} must be strictly increasing")
        normalized.append(timestamp)
    return tuple(normalized)


def _require_strictly_increasing(field_name: str, values: Sequence[str]) -> None:
    for previous, current in zip(values, values[1:]):
        if current <= previous:
            raise ValueError(f"{field_name} must be strictly increasing")


def _normalize_date_value(value: Any, field_name: str) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field_name} must be an ISO date")
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            raise ValueError(f"{field_name} must be an ISO date")
        return value.date().isoformat()
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO date")
    try:
        return pd.Timestamp(value.strip()).date().isoformat()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def _require_frame_columns(frame: pd.DataFrame, required: Sequence[str]) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("frame must be a pandas DataFrame")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(
            f"frame missing required columns: {', '.join(missing)}"
        )


def _require_positive_int(field_name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_non_empty_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
