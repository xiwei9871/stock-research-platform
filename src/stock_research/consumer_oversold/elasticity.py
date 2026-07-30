from __future__ import annotations

import math
from decimal import Decimal, DecimalException

import numpy as np
import pandas as pd

from .contracts import validate_trade_date


REQUIRED_COLUMNS = ("asset_id", "trade_date", "close")
STOCK_CHARACTER_REQUIRED_COLUMNS = (
    "asset_id",
    "stock_code",
    "trade_date",
    "close",
    "pct_chg",
    "is_st",
)
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
STOCK_CHARACTER_COLUMNS = [
    "asset_id",
    "history_sessions",
    "limit_up_count_2y",
    "up_7pct_count_2y",
    "up_5pct_count_2y",
    "mean_abs_return_2y",
    "return_volatility_2y",
    "upside_tail_volatility_2y",
    "max_limit_up_streak_2y",
    "positive_after_big_up_1d_rate",
    "positive_after_big_up_3d_rate",
    "positive_after_big_up_5d_rate",
    "stock_character_coverage",
]


def _require_columns(bars: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in bars.columns]
    if missing:
        raise ValueError(f"bars missing required columns: {', '.join(missing)}")


def _require_stock_character_columns(bars: pd.DataFrame) -> None:
    missing = [
        column for column in STOCK_CHARACTER_REQUIRED_COLUMNS if column not in bars.columns
    ]
    if missing:
        raise ValueError(f"bars missing required columns: {', '.join(missing)}")


def _is_missing_scalar(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (DecimalException, TypeError, ValueError):
        return False


def _strict_float(value: object, *, field_name: str, allow_missing: bool) -> float:
    if _is_missing_scalar(value):
        if allow_missing:
            return math.nan
        raise ValueError(f"{field_name} must be a finite number")
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, STRICT_NUMERIC_TYPES):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(converted):
        raise ValueError(f"{field_name} must be a finite number")
    return converted


def _normalized_identifier(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string; got {value!r}")
    return value.strip()


def _normalized_stock_code(value: object) -> str:
    code = _normalized_identifier(value, field_name="stock_code")
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        raise ValueError(
            f"stock_code must contain six ASCII digits; got {value!r}"
        )
    return code


def is_limit_up_day(
    stock_code: str,
    is_st: object,
    pct_chg: object,
    *,
    trade_date: str,
) -> bool:
    """Return whether a daily percentage change reaches its current board limit."""
    validate_trade_date(trade_date)
    code = _normalized_stock_code(stock_code)
    if not isinstance(is_st, (bool, np.bool_)):
        raise ValueError("is_st must be a boolean")
    change = _strict_float(pct_chg, field_name="pct_chg", allow_missing=True)
    if math.isnan(change):
        return False
    if bool(is_st):
        threshold = 4.8
    elif code.startswith(("4", "8", "920")):
        threshold = 29.8
    elif code.startswith(("300", "301", "688", "689")):
        threshold = 19.8
    else:
        threshold = 9.8
    return change >= threshold


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


def _maximum_true_streak(flags: list[bool]) -> int:
    maximum = 0
    current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        maximum = max(maximum, current)
    return maximum


def _positive_forward_rate(
    close: pd.Series,
    event_positions: list[int],
    horizon: int,
) -> float:
    outcomes = [
        float(close.iloc[position + horizon] / close.iloc[position] - 1.0) > 0.0
        for position in event_positions
        if position + horizon < len(close)
    ]
    return float(np.mean(outcomes)) if outcomes else math.nan


def compute_stock_character_features(
    bars: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Measure two-year upside behavior from point-in-time HFQ bars."""
    cutoff = pd.Timestamp(validate_trade_date(trade_date))
    _require_stock_character_columns(bars)

    frame = bars.loc[:, STOCK_CHARACTER_REQUIRED_COLUMNS].copy()
    if frame.empty:
        return pd.DataFrame(columns=STOCK_CHARACTER_COLUMNS)

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
        return pd.DataFrame(columns=STOCK_CHARACTER_COLUMNS)

    frame["asset_id"] = frame["asset_id"].map(
        lambda value: _normalized_identifier(value, field_name="asset_id")
    )
    frame["stock_code"] = frame["stock_code"].map(_normalized_stock_code)

    duplicates = frame.duplicated(["asset_id", "trade_date"], keep=False)
    if duplicates.any():
        duplicate = frame.loc[duplicates, ["asset_id", "trade_date"]].sort_values(
            ["asset_id", "trade_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            "duplicate bar for asset "
            f"{duplicate['asset_id']} on {duplicate['trade_date'].date().isoformat()}"
        )

    close_values: list[float] = []
    pct_values: list[float] = []
    status_values: list[bool] = []
    for row in frame.itertuples(index=False):
        try:
            close = _strict_float(row.close, field_name="close", allow_missing=False)
            if close <= 0.0:
                raise ValueError("close must be positive")
            pct = _strict_float(row.pct_chg, field_name="pct_chg", allow_missing=True)
            if not isinstance(row.is_st, (bool, np.bool_)):
                raise ValueError("is_st must be a boolean")
        except ValueError as exc:
            raise ValueError(
                f"invalid {exc} for asset {row.asset_id} "
                f"on {row.trade_date.date().isoformat()}"
            ) from exc
        close_values.append(close)
        pct_values.append(pct)
        status_values.append(bool(row.is_st))
    frame["close"] = close_values
    frame["pct_chg"] = pct_values
    frame["is_st"] = status_values
    frame = frame.sort_values(["asset_id", "trade_date"], kind="stable")

    rows: list[dict[str, object]] = []
    for asset_id, full_history in frame.groupby("asset_id", sort=True):
        history = full_history.tail(504).reset_index(drop=True)
        valid_pct = history["pct_chg"].notna()
        returns = history.loc[valid_pct, "pct_chg"].to_numpy(dtype=float) / 100.0
        positive_returns = returns[returns > 0.0]
        limit_flags = [
            is_limit_up_day(
                row.stock_code,
                row.is_st,
                row.pct_chg,
                trade_date=row.trade_date.date().isoformat(),
            )
            for row in history.itertuples(index=False)
        ]
        event_positions = [
            position
            for position, value in enumerate(history["pct_chg"].tolist())
            if not math.isnan(value) and value >= 7.0
        ]
        close = history["close"]
        rows.append(
            {
                "asset_id": asset_id,
                "history_sessions": len(history),
                "limit_up_count_2y": int(sum(limit_flags)),
                "up_7pct_count_2y": int((history["pct_chg"] >= 7.0).sum()),
                "up_5pct_count_2y": int((history["pct_chg"] >= 5.0).sum()),
                "mean_abs_return_2y": (
                    float(np.mean(np.abs(returns))) if len(returns) else math.nan
                ),
                "return_volatility_2y": (
                    float(np.std(returns, ddof=0)) if len(returns) else math.nan
                ),
                "upside_tail_volatility_2y": (
                    float(np.std(positive_returns, ddof=0))
                    if len(positive_returns)
                    else math.nan
                ),
                "max_limit_up_streak_2y": _maximum_true_streak(limit_flags),
                "positive_after_big_up_1d_rate": _positive_forward_rate(
                    close, event_positions, 1
                ),
                "positive_after_big_up_3d_rate": _positive_forward_rate(
                    close, event_positions, 3
                ),
                "positive_after_big_up_5d_rate": _positive_forward_rate(
                    close, event_positions, 5
                ),
                "stock_character_coverage": bool(len(returns) >= 400 and len(close) >= 2),
            }
        )

    return pd.DataFrame(rows, columns=STOCK_CHARACTER_COLUMNS)
