from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
import pandas as pd

from .contracts import validate_trade_date


REQUIRED_COLUMNS = ("asset_id", "trade_date", "close")
STRICT_NUMERIC_TYPES = (int, float, np.integer, np.floating, Decimal)
RESIDUAL_PRICE_COLUMNS = [
    "asset_id",
    "latest_trade_date",
    "history_sessions",
    "price_series_source",
    "return_1d",
    "drawdown_from_high_1y",
    "drawdown_from_high_2y",
    "price_position_1y",
    "price_position_2y",
    "distance_raw_ma120",
    "distance_raw_ma250",
    "rebound_from_low_60d",
    "rebound_from_low_120d",
    "residual_deviation_coverage",
]


def _require_columns(bars: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in bars.columns]
    if missing:
        raise ValueError(f"bars missing required columns: {', '.join(missing)}")


def _validate_hfq_close(frame: pd.DataFrame) -> None:
    valid_type = frame["close"].map(
        lambda value: not isinstance(value, (bool, np.bool_))
        and isinstance(value, STRICT_NUMERIC_TYPES)
    )
    numeric_close = frame["close"].where(valid_type, np.nan).astype(float)
    invalid = (
        ~valid_type
        | numeric_close.isna()
        | ~np.isfinite(numeric_close)
        | numeric_close.le(0.0)
    )
    if invalid.any():
        row = frame.loc[invalid, ["asset_id", "trade_date"]].sort_values(
            ["asset_id", "trade_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            f"invalid close for asset {row['asset_id']} "
            f"on {row['trade_date'].date().isoformat()}"
        )
    frame["close"] = numeric_close.astype(float)


def _complete_window(close: pd.Series, sessions: int) -> pd.Series | None:
    if len(close) < sessions:
        return None
    return close.tail(sessions)


def _drawdown(close: pd.Series, sessions: int) -> float:
    window = _complete_window(close, sessions)
    if window is None:
        return math.nan
    return float(window.iloc[-1] / window.max() - 1.0)


def _position(close: pd.Series, sessions: int) -> float:
    window = _complete_window(close, sessions)
    if window is None:
        return math.nan
    low = float(window.min())
    high = float(window.max())
    if high == low:
        return math.nan
    return float((window.iloc[-1] - low) / (high - low))


def _distance_from_mean(close: pd.Series, sessions: int) -> float:
    window = _complete_window(close, sessions)
    if window is None:
        return math.nan
    return float(window.iloc[-1] / window.mean() - 1.0)


def _rebound(close: pd.Series, sessions: int) -> float:
    window = _complete_window(close, sessions)
    if window is None:
        return math.nan
    return float(window.iloc[-1] / window.min() - 1.0)


def compute_residual_price_features(
    bars: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Compute point-in-time residual deviations from the HFQ close series."""
    cutoff = pd.Timestamp(validate_trade_date(trade_date))
    _require_columns(bars)

    frame = bars.loc[:, REQUIRED_COLUMNS].copy()
    if frame.empty:
        return pd.DataFrame(columns=RESIDUAL_PRICE_COLUMNS)

    try:
        frame["trade_date"] = pd.to_datetime(
            frame["trade_date"], errors="raise", format="mixed"
        ).dt.normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("bars trade_date contains an invalid date") from exc
    if frame["trade_date"].isna().any():
        raise ValueError("bars trade_date contains an invalid date")

    frame = frame.loc[frame["trade_date"].le(cutoff)].copy()
    if frame.empty:
        return pd.DataFrame(columns=RESIDUAL_PRICE_COLUMNS)

    invalid_asset = frame["asset_id"].map(
        lambda value: pd.isna(value) or not str(value).strip()
    )
    if invalid_asset.any():
        raise ValueError("asset_id must be non-empty")
    frame["asset_id"] = frame["asset_id"].map(lambda value: str(value).strip())
    duplicates = frame.duplicated(["asset_id", "trade_date"], keep=False)
    if duplicates.any():
        duplicate = frame.loc[duplicates, ["asset_id", "trade_date"]].sort_values(
            ["asset_id", "trade_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            "duplicate bar for asset "
            f"{duplicate['asset_id']} on {duplicate['trade_date'].date().isoformat()}"
        )

    _validate_hfq_close(frame)
    frame = frame.sort_values(["asset_id", "trade_date"], kind="stable")

    rows: list[dict[str, object]] = []
    for asset_id, full_history in frame.groupby("asset_id", sort=True):
        history = full_history.tail(520).reset_index(drop=True)
        close = history["close"]
        position_1y = _position(close, 252)
        position_2y = _position(close, 504)
        coverage = (
            len(history) >= 504
            and len(close) >= 2
            and math.isfinite(position_1y)
            and math.isfinite(position_2y)
        )
        rows.append(
            {
                "asset_id": asset_id,
                "latest_trade_date": history["trade_date"].iloc[-1],
                "history_sessions": len(history),
                "price_series_source": "hfq",
                "return_1d": (
                    float(close.iloc[-1] / close.iloc[-2] - 1.0)
                    if len(close) >= 2
                    else math.nan
                ),
                "drawdown_from_high_1y": _drawdown(close, 252),
                "drawdown_from_high_2y": _drawdown(close, 504),
                "price_position_1y": position_1y,
                "price_position_2y": position_2y,
                "distance_raw_ma120": _distance_from_mean(close, 120),
                "distance_raw_ma250": _distance_from_mean(close, 250),
                "rebound_from_low_60d": _rebound(close, 60),
                "rebound_from_low_120d": _rebound(close, 120),
                "residual_deviation_coverage": bool(coverage),
            }
        )

    return pd.DataFrame(rows, columns=RESIDUAL_PRICE_COLUMNS)
