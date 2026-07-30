from __future__ import annotations

import math
from decimal import Decimal, DecimalException

import numpy as np
import pandas as pd

from .contracts import ConsumerOversoldConfig, validate_trade_date


REQUIRED_COLUMNS = ("asset_id", "trade_date", "close")
STOCK_CHARACTER_REQUIRED_COLUMNS = (
    "asset_id",
    "stock_code",
    "trade_date",
    "close",
    "pct_chg",
    "is_st",
)
MARKET_CAPACITY_BAR_COLUMNS = (
    "asset_id",
    "trade_date",
    "raw_close",
    "amount",
    "turnover_rate",
)
MARKET_CAPACITY_SHARE_COLUMNS = (
    "asset_id",
    "total_share",
    "float_share",
    "free_float_share",
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
    "distance_hfq_ma120",
    "distance_hfq_ma250",
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
MARKET_CAPACITY_COLUMNS = [
    "asset_id",
    "latest_trade_date",
    "history_sessions",
    "current_total_market_cap",
    "current_float_market_cap",
    "log_current_float_market_cap",
    "market_cap_source",
    "average_amount_20d",
    "average_turnover_rate_20d",
    "amount_to_float_cap_20d",
    "market_capacity_coverage",
]
RESIDUAL_ELASTICITY_FIELDS = (
    "drawdown_from_high_1y",
    "drawdown_from_high_2y",
    "price_position_1y",
    "price_position_2y",
    "distance_hfq_ma120",
    "distance_hfq_ma250",
    "rebound_from_low_60d",
    "rebound_from_low_120d",
    "relative_return_6m",
    "valuation_percentile",
)
STOCK_ELASTICITY_FIELDS = (
    "limit_up_count_2y",
    "up_7pct_count_2y",
    "up_5pct_count_2y",
    "upside_tail_volatility_2y",
    "positive_after_big_up_1d_rate",
    "positive_after_big_up_3d_rate",
    "positive_after_big_up_5d_rate",
)
STOCK_WINSORIZE_FIELDS = (
    "limit_up_count_2y",
    "up_7pct_count_2y",
    "up_5pct_count_2y",
    "upside_tail_volatility_2y",
)
MARKET_ELASTICITY_FIELDS = ("log_current_float_market_cap",)
CATALYST_ELASTICITY_FIELDS = (
    "catalyst_verifiability_score",
    "average_amount_20d",
    "average_turnover_rate_20d",
    "amount_to_float_cap_20d",
)
ELASTICITY_COVERAGE_FIELDS = (
    "residual_deviation_coverage",
    "stock_character_coverage",
    "market_capacity_coverage",
)
ELASTICITY_ADDED_COLUMNS = (
    "residual_deviation_component_coverage",
    "residual_deviation_score",
    "stock_character_component_coverage",
    "stock_character_score",
    "market_capacity_component_coverage",
    "market_capacity_score",
    "catalyst_liquidity_coverage",
    "catalyst_liquidity_score",
    "elasticity_coverage",
    "elasticity_score",
    "automatic_elasticity_coverage",
    "automatic_elasticity_score",
)


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


def _require_market_capacity_columns(
    bars: pd.DataFrame,
    shares: pd.DataFrame,
) -> None:
    missing_bars = [
        column for column in MARKET_CAPACITY_BAR_COLUMNS if column not in bars.columns
    ]
    if missing_bars:
        raise ValueError(f"bars missing required columns: {', '.join(missing_bars)}")
    missing_shares = [
        column
        for column in MARKET_CAPACITY_SHARE_COLUMNS
        if column not in shares.columns
    ]
    if missing_shares:
        raise ValueError(
            f"shares missing required columns: {', '.join(missing_shares)}"
        )


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
                "distance_hfq_ma120": _distance_from_mean(close, 120),
                "distance_hfq_ma250": _distance_from_mean(close, 250),
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
                    float(np.std(returns, ddof=1)) if len(returns) >= 2 else math.nan
                ),
                "upside_tail_volatility_2y": (
                    float(np.std(positive_returns, ddof=1))
                    if len(positive_returns) >= 2
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


def _market_numeric_value(
    value: object,
    *,
    field_name: str,
    asset_id: str,
    trade_date: pd.Timestamp | None = None,
    strictly_positive: bool,
) -> float:
    try:
        number = _strict_float(value, field_name=field_name, allow_missing=True)
    except ValueError as exc:
        context = f"{field_name} for asset {asset_id}"
        if trade_date is not None:
            context += f" on {trade_date.date().isoformat()}"
        raise ValueError(f"invalid {context}") from exc
    if math.isnan(number):
        return number
    invalid_range = number <= 0.0 if strictly_positive else number < 0.0
    if invalid_range:
        context = f"{field_name} for asset {asset_id}"
        if trade_date is not None:
            context += f" on {trade_date.date().isoformat()}"
        raise ValueError(f"invalid {context}")
    return number


def _finite_positive_product(left: float, right: float) -> float:
    if not math.isfinite(left) or not math.isfinite(right):
        return math.nan
    product = left * right
    return product if math.isfinite(product) and product > 0.0 else math.nan


def compute_market_capacity_features(
    bars: pd.DataFrame,
    shares: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Compute actual point-in-time market capacity from raw price and shares."""
    cutoff = pd.Timestamp(validate_trade_date(trade_date))
    _require_market_capacity_columns(bars, shares)

    frame = bars.loc[:, MARKET_CAPACITY_BAR_COLUMNS].copy()
    if frame.empty:
        return pd.DataFrame(columns=MARKET_CAPACITY_COLUMNS)
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
        return pd.DataFrame(columns=MARKET_CAPACITY_COLUMNS)

    frame["asset_id"] = frame["asset_id"].map(
        lambda value: _normalized_identifier(value, field_name="asset_id")
    )
    duplicates = frame.duplicated(["asset_id", "trade_date"], keep=False)
    if duplicates.any():
        row = frame.loc[duplicates, ["asset_id", "trade_date"]].sort_values(
            ["asset_id", "trade_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            f"duplicate bar for asset {row['asset_id']} "
            f"on {row['trade_date'].date().isoformat()}"
        )

    for field_name, strictly_positive in (
        ("raw_close", True),
        ("amount", False),
        ("turnover_rate", False),
    ):
        frame[field_name] = [
            _market_numeric_value(
                getattr(row, field_name),
                field_name=field_name,
                asset_id=row.asset_id,
                trade_date=row.trade_date,
                strictly_positive=strictly_positive,
            )
            for row in frame.itertuples(index=False)
        ]
    frame = frame.sort_values(["asset_id", "trade_date"], kind="stable")

    share_frame = shares.loc[:, MARKET_CAPACITY_SHARE_COLUMNS].copy()
    share_frame["asset_id"] = share_frame["asset_id"].map(
        lambda value: _normalized_identifier(value, field_name="asset_id")
    )
    active_asset_ids = set(frame["asset_id"])
    share_frame = share_frame.loc[
        share_frame["asset_id"].isin(active_asset_ids)
    ].copy()
    duplicate_shares = share_frame["asset_id"].duplicated(keep=False)
    if duplicate_shares.any():
        asset_id = share_frame.loc[duplicate_shares, "asset_id"].sort_values(
            kind="stable"
        ).iloc[0]
        raise ValueError(f"shares contains duplicate asset_id {asset_id}")
    for field_name in MARKET_CAPACITY_SHARE_COLUMNS[1:]:
        share_frame[field_name] = [
            _market_numeric_value(
                getattr(row, field_name),
                field_name=field_name,
                asset_id=row.asset_id,
                strictly_positive=True,
            )
            for row in share_frame.itertuples(index=False)
        ]
    shares_by_asset = share_frame.set_index("asset_id")

    rows: list[dict[str, object]] = []
    for asset_id, full_history in frame.groupby("asset_id", sort=True):
        history = full_history.tail(20).reset_index(drop=True)
        latest = history.iloc[-1]
        raw_close = float(latest["raw_close"])
        if asset_id in shares_by_asset.index:
            share_row = shares_by_asset.loc[asset_id]
            total_share = float(share_row["total_share"])
            float_share = float(share_row["float_share"])
            free_float_share = float(share_row["free_float_share"])
        else:
            total_share = math.nan
            float_share = math.nan
            free_float_share = math.nan

        current_total_market_cap = _finite_positive_product(raw_close, total_share)
        if math.isfinite(free_float_share):
            selected_float_share = free_float_share
            market_cap_source: str | None = "free_float_share"
        elif math.isfinite(float_share):
            selected_float_share = float_share
            market_cap_source = "float_share"
        elif math.isfinite(total_share):
            selected_float_share = total_share
            market_cap_source = "total_share_fallback"
        else:
            selected_float_share = math.nan
            market_cap_source = None
        current_float_market_cap = _finite_positive_product(
            raw_close, selected_float_share
        )
        log_current_float_market_cap = (
            float(math.log(current_float_market_cap))
            if math.isfinite(current_float_market_cap)
            and current_float_market_cap > 0.0
            else math.nan
        )

        amount_complete = len(history) >= 20 and history["amount"].notna().all()
        turnover_complete = (
            len(history) >= 20 and history["turnover_rate"].notna().all()
        )
        average_amount_20d = (
            float(history["amount"].mean()) if amount_complete else math.nan
        )
        average_turnover_rate_20d = (
            float(history["turnover_rate"].mean())
            if turnover_complete
            else math.nan
        )
        amount_to_float_cap_20d = (
            float(average_amount_20d / current_float_market_cap)
            if math.isfinite(average_amount_20d)
            and math.isfinite(current_float_market_cap)
            and current_float_market_cap > 0.0
            else math.nan
        )
        coverage = (
            math.isfinite(raw_close)
            and raw_close > 0.0
            and math.isfinite(current_total_market_cap)
            and current_total_market_cap > 0.0
            and math.isfinite(current_float_market_cap)
            and current_float_market_cap > 0.0
            and market_cap_source is not None
            and amount_complete
            and math.isfinite(amount_to_float_cap_20d)
            and amount_to_float_cap_20d >= 0.0
        )
        rows.append(
            {
                "asset_id": asset_id,
                "latest_trade_date": latest["trade_date"],
                "history_sessions": len(history),
                "current_total_market_cap": current_total_market_cap,
                "current_float_market_cap": current_float_market_cap,
                "log_current_float_market_cap": log_current_float_market_cap,
                "market_cap_source": market_cap_source,
                "average_amount_20d": average_amount_20d,
                "average_turnover_rate_20d": average_turnover_rate_20d,
                "amount_to_float_cap_20d": amount_to_float_cap_20d,
                "market_capacity_coverage": bool(coverage),
            }
        )

    return pd.DataFrame(rows, columns=MARKET_CAPACITY_COLUMNS)


def _cross_sectional_percentile(
    values: pd.Series,
    *,
    favorable_low: bool,
) -> pd.Series:
    result = pd.Series(math.nan, index=values.index, dtype="float64")
    valid = values.dropna()
    valid_count = len(valid)
    if valid_count == 0:
        return result
    if valid_count == 1 or valid.nunique(dropna=True) == 1:
        result.loc[valid.index] = 50.0
        return result
    ranks = valid.rank(method="average", ascending=not favorable_low)
    result.loc[valid.index] = (ranks - 1.0) / (valid_count - 1.0) * 100.0
    return result


def _component_score(
    frame: pd.DataFrame,
    fields: tuple[str, ...],
    coverage: pd.Series,
    *,
    favorable_low: bool,
    winsorize_fields: tuple[str, ...] = (),
) -> pd.Series:
    percentiles: dict[str, pd.Series] = {}
    for field in fields:
        values = frame[field].where(coverage)
        if field in winsorize_fields and values.notna().any():
            lower = float(values.quantile(0.05))
            upper = float(values.quantile(0.95))
            values = values.clip(lower=lower, upper=upper)
        percentiles[field] = _cross_sectional_percentile(
            values, favorable_low=favorable_low
        )
    scores = pd.DataFrame(percentiles, index=frame.index).mean(axis=1)
    return scores.where(coverage)


def score_rebound_elasticity(
    rows: pd.DataFrame,
    config: ConsumerOversoldConfig,
) -> pd.DataFrame:
    """Score complete repair candidates on cross-sectional rebound elasticity."""
    required = (
        "asset_id",
        *RESIDUAL_ELASTICITY_FIELDS,
        *STOCK_ELASTICITY_FIELDS,
        *MARKET_ELASTICITY_FIELDS,
        *CATALYST_ELASTICITY_FIELDS,
        *ELASTICITY_COVERAGE_FIELDS,
    )
    missing = [column for column in required if column not in rows.columns]
    if missing:
        raise ValueError(f"rows missing required columns: {', '.join(missing)}")

    frame = rows.copy()
    frame["asset_id"] = frame["asset_id"].map(
        lambda value: _normalized_identifier(value, field_name="asset_id")
    )
    duplicate = frame["asset_id"].duplicated(keep=False)
    if duplicate.any():
        asset_id = frame.loc[duplicate, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(f"rows contains duplicate asset_id {asset_id}")

    numeric_fields = (
        *RESIDUAL_ELASTICITY_FIELDS,
        *STOCK_ELASTICITY_FIELDS,
        *MARKET_ELASTICITY_FIELDS,
        *CATALYST_ELASTICITY_FIELDS,
    )
    for field in numeric_fields:
        parsed: list[float] = []
        for value, asset_id in zip(frame[field], frame["asset_id"], strict=True):
            try:
                parsed.append(
                    _strict_float(value, field_name=field, allow_missing=True)
                )
            except ValueError as exc:
                raise ValueError(f"rows asset {asset_id} field {field}: {exc}") from exc
        frame[field] = parsed
    for field in ELASTICITY_COVERAGE_FIELDS:
        parsed_coverage: list[bool] = []
        for value, asset_id in zip(frame[field], frame["asset_id"], strict=True):
            if not isinstance(value, (bool, np.bool_)):
                raise ValueError(
                    f"rows asset {asset_id} field {field} must be a strict boolean"
                )
            parsed_coverage.append(bool(value))
        frame[field] = parsed_coverage

    no_big_up = frame["stock_character_coverage"] & frame["up_7pct_count_2y"].eq(0.0)
    for field in (
        "positive_after_big_up_1d_rate",
        "positive_after_big_up_3d_rate",
        "positive_after_big_up_5d_rate",
    ):
        frame.loc[no_big_up & frame[field].isna(), field] = 0.0

    residual_coverage = frame["residual_deviation_coverage"] & frame[
        list(RESIDUAL_ELASTICITY_FIELDS)
    ].notna().all(axis=1)
    stock_coverage = frame["stock_character_coverage"] & frame[
        list(STOCK_ELASTICITY_FIELDS)
    ].notna().all(axis=1)
    market_coverage = frame["market_capacity_coverage"] & frame[
        list(MARKET_ELASTICITY_FIELDS)
    ].notna().all(axis=1)
    catalyst_coverage = frame[list(CATALYST_ELASTICITY_FIELDS)].notna().all(axis=1)

    frame["residual_deviation_component_coverage"] = residual_coverage.astype(bool)
    frame["residual_deviation_score"] = _component_score(
        frame,
        RESIDUAL_ELASTICITY_FIELDS,
        residual_coverage,
        favorable_low=True,
    )
    frame["stock_character_component_coverage"] = stock_coverage.astype(bool)
    frame["stock_character_score"] = _component_score(
        frame,
        STOCK_ELASTICITY_FIELDS,
        stock_coverage,
        favorable_low=False,
        winsorize_fields=STOCK_WINSORIZE_FIELDS,
    )
    frame["market_capacity_component_coverage"] = market_coverage.astype(bool)
    frame["market_capacity_score"] = _component_score(
        frame,
        MARKET_ELASTICITY_FIELDS,
        market_coverage,
        favorable_low=True,
    )
    frame["catalyst_liquidity_coverage"] = catalyst_coverage.astype(bool)
    frame["catalyst_liquidity_score"] = _component_score(
        frame,
        CATALYST_ELASTICITY_FIELDS,
        catalyst_coverage,
        favorable_low=False,
    )

    frame["elasticity_coverage"] = (
        residual_coverage & stock_coverage & market_coverage & catalyst_coverage
    ).astype(bool)
    frame["elasticity_score"] = (
        config.residual_deviation_weight * frame["residual_deviation_score"]
        + config.stock_character_weight * frame["stock_character_score"]
        + config.market_capacity_weight * frame["market_capacity_score"]
        + config.catalyst_liquidity_weight * frame["catalyst_liquidity_score"]
    ).where(frame["elasticity_coverage"])
    frame["automatic_elasticity_coverage"] = (
        residual_coverage & stock_coverage & market_coverage
    ).astype(bool)
    frame["automatic_elasticity_score"] = (
        0.45 * frame["residual_deviation_score"]
        + 0.30 * frame["stock_character_score"]
        + 0.25 * frame["market_capacity_score"]
    ).where(frame["automatic_elasticity_coverage"])
    return frame.sort_values("asset_id", kind="stable").reset_index(drop=True)
