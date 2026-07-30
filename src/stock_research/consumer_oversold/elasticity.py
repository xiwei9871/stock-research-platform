from __future__ import annotations

import math
from decimal import Decimal
from numbers import Real

import numpy as np
import pandas as pd

from .contracts import validate_trade_date


REQUIRED_COLUMNS = ("asset_id", "trade_date", "close", "raw_close")
RESIDUAL_PRICE_COLUMNS = [
    "asset_id",
    "latest_trade_date",
    "history_sessions",
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


def _is_missing(value: object) -> bool:
    if value is None or value is pd.NA:
        return True
    return isinstance(value, (float, np.floating)) and math.isnan(float(value))


def _finite_positive_number(value: object) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    if isinstance(value, Decimal):
        if not value.is_finite() or value <= 0:
            return None
        return float(value)
    if not isinstance(value, (Real, np.integer, np.floating)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0.0 else None


def _require_columns(bars: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in bars.columns]
    if missing:
        raise ValueError(f"bars missing required columns: {', '.join(missing)}")


def _validate_prices(frame: pd.DataFrame) -> None:
    for index, row in frame.iterrows():
        close = _finite_positive_number(row["close"])
        if close is None:
            trade_date = row["trade_date"].date().isoformat()
            raise ValueError(
                f"invalid close for asset {row['asset_id']} on {trade_date}"
            )
        frame.at[index, "close"] = close

        raw_close = row["raw_close"]
        if _is_missing(raw_close):
            frame.at[index, "raw_close"] = math.nan
            continue
        numeric_raw_close = _finite_positive_number(raw_close)
        if numeric_raw_close is None:
            trade_date = row["trade_date"].date().isoformat()
            raise ValueError(
                f"invalid raw_close for asset {row['asset_id']} on {trade_date}"
            )
        frame.at[index, "raw_close"] = numeric_raw_close

    frame["close"] = frame["close"].astype(float)
    frame["raw_close"] = frame["raw_close"].astype(float)


def _complete_window(raw_close: pd.Series, sessions: int) -> pd.Series | None:
    if len(raw_close) < sessions:
        return None
    window = raw_close.tail(sessions)
    return window if window.notna().all() else None


def _drawdown(raw_close: pd.Series, sessions: int) -> float:
    window = _complete_window(raw_close, sessions)
    if window is None:
        return math.nan
    return float(window.iloc[-1] / window.max() - 1.0)


def _position(raw_close: pd.Series, sessions: int) -> float:
    window = _complete_window(raw_close, sessions)
    if window is None:
        return math.nan
    low = float(window.min())
    high = float(window.max())
    if high == low:
        return math.nan
    return float((window.iloc[-1] - low) / (high - low))


def _distance_from_mean(raw_close: pd.Series, sessions: int) -> float:
    window = _complete_window(raw_close, sessions)
    if window is None:
        return math.nan
    return float(window.iloc[-1] / window.mean() - 1.0)


def _rebound(raw_close: pd.Series, sessions: int) -> float:
    window = _complete_window(raw_close, sessions)
    if window is None:
        return math.nan
    return float(window.iloc[-1] / window.min() - 1.0)


def compute_residual_price_features(
    bars: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Compute point-in-time residual price-deviation features by trading session."""
    cutoff = pd.Timestamp(validate_trade_date(trade_date))
    _require_columns(bars)

    frame = bars.loc[:, REQUIRED_COLUMNS].copy()
    if frame.empty:
        return pd.DataFrame(columns=RESIDUAL_PRICE_COLUMNS)

    invalid_asset = frame["asset_id"].map(
        lambda value: pd.isna(value) or not str(value).strip()
    )
    if invalid_asset.any():
        raise ValueError("asset_id must be non-empty")
    frame["asset_id"] = frame["asset_id"].map(lambda value: str(value).strip())
    input_asset_ids = sorted(frame["asset_id"].unique())

    try:
        frame["trade_date"] = pd.to_datetime(
            frame["trade_date"], errors="raise", format="mixed"
        ).dt.normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("bars trade_date contains an invalid date") from exc
    if frame["trade_date"].isna().any():
        raise ValueError("bars trade_date contains an invalid date")

    frame = frame.loc[frame["trade_date"].le(cutoff)].copy()
    duplicates = frame.duplicated(["asset_id", "trade_date"], keep=False)
    if duplicates.any():
        duplicate = frame.loc[duplicates, ["asset_id", "trade_date"]].sort_values(
            ["asset_id", "trade_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            "duplicate bar for asset "
            f"{duplicate['asset_id']} on {duplicate['trade_date'].date().isoformat()}"
        )

    _validate_prices(frame)
    frame = frame.sort_values(["asset_id", "trade_date"], kind="stable")

    rows: list[dict[str, object]] = []
    histories = {
        asset_id: history for asset_id, history in frame.groupby("asset_id", sort=False)
    }
    for asset_id in input_asset_ids:
        full_history = histories.get(asset_id)
        if full_history is None:
            rows.append(
                {
                    "asset_id": asset_id,
                    "latest_trade_date": pd.NaT,
                    "history_sessions": 0,
                    "return_1d": math.nan,
                    "drawdown_from_high_1y": math.nan,
                    "drawdown_from_high_2y": math.nan,
                    "price_position_1y": math.nan,
                    "price_position_2y": math.nan,
                    "distance_raw_ma120": math.nan,
                    "distance_raw_ma250": math.nan,
                    "rebound_from_low_60d": math.nan,
                    "rebound_from_low_120d": math.nan,
                    "residual_deviation_coverage": False,
                }
            )
            continue
        history = full_history.tail(520).reset_index(drop=True)
        close = history["close"]
        raw_close = history["raw_close"]
        position_1y = _position(raw_close, 252)
        position_2y = _position(raw_close, 504)
        raw_2y = _complete_window(raw_close, 504)
        coverage = (
            len(history) >= 504
            and len(close) >= 2
            and raw_2y is not None
            and math.isfinite(position_1y)
            and math.isfinite(position_2y)
        )
        rows.append(
            {
                "asset_id": asset_id,
                "latest_trade_date": history["trade_date"].iloc[-1],
                "history_sessions": len(history),
                "return_1d": (
                    float(close.iloc[-1] / close.iloc[-2] - 1.0)
                    if len(close) >= 2
                    else math.nan
                ),
                "drawdown_from_high_1y": _drawdown(raw_close, 252),
                "drawdown_from_high_2y": _drawdown(raw_close, 504),
                "price_position_1y": position_1y,
                "price_position_2y": position_2y,
                "distance_raw_ma120": _distance_from_mean(raw_close, 120),
                "distance_raw_ma250": _distance_from_mean(raw_close, 250),
                "rebound_from_low_60d": _rebound(raw_close, 60),
                "rebound_from_low_120d": _rebound(raw_close, 120),
                "residual_deviation_coverage": bool(coverage),
            }
        )

    return pd.DataFrame(rows, columns=RESIDUAL_PRICE_COLUMNS)
