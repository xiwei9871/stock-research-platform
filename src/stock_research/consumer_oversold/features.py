from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd


BAR_COLUMNS = ("asset_id", "trade_date", "close")
MEMBERSHIP_COLUMNS = ("asset_id", "consumer_subindustry")
SCORE_COLUMNS = (
    "max_drawdown_12m",
    "return_6m",
    "relative_return_6m",
    "valuation_depression_percentile",
    "distance_ma120",
    "distance_ma250",
)
PRICE_OUTPUT_COLUMNS = [
    "asset_id",
    "latest_trade_date",
    "latest_close",
    "history_bars",
    "price_history_complete",
    "return_6m",
    "return_60d",
    "max_drawdown_12m",
    "rebound_from_low_60d",
    "ma120",
    "ma250",
    "distance_ma120",
    "distance_ma250",
    "consumer_subindustry",
    "industry_peer_count",
    "industry_peer_count_60d",
    "industry_return_6m",
    "relative_return_6m",
    "industry_return_60d",
    "relative_return_60d",
    "relative_return_coverage",
    "relative_return_coverage_60d",
]


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...], name: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _window_return(close: pd.Series, bars: int) -> float:
    if len(close) < bars:
        return math.nan
    return float(close.iloc[-1] / close.iloc[-bars] - 1.0)


def _moving_average(close: pd.Series, bars: int) -> float:
    if len(close) < bars:
        return math.nan
    return float(close.tail(bars).mean())


def compute_price_features(
    bars: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Compute point-in-time price and subindustry-relative oversold features."""
    _require_columns(bars, BAR_COLUMNS, "bars")
    _require_columns(membership, MEMBERSHIP_COLUMNS, "membership")

    try:
        cutoff = pd.Timestamp(trade_date).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid trade_date cutoff: {trade_date!r}") from exc

    frame = bars.loc[:, BAR_COLUMNS].copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    try:
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise").dt.normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("bars trade_date contains an invalid date") from exc
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

    numeric_close = pd.to_numeric(frame["close"], errors="coerce")
    invalid_close = numeric_close.isna() | ~np.isfinite(numeric_close) | numeric_close.le(0.0)
    if invalid_close.any():
        invalid = frame.loc[invalid_close, ["asset_id", "trade_date"]].sort_values(
            ["asset_id", "trade_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            "invalid close for asset "
            f"{invalid['asset_id']} on {invalid['trade_date'].date().isoformat()}"
        )
    frame["close"] = numeric_close.astype(float)
    frame = frame.sort_values(["asset_id", "trade_date"], kind="stable")

    member_frame = membership.loc[:, MEMBERSHIP_COLUMNS].copy()
    member_frame["asset_id"] = member_frame["asset_id"].astype(str)
    duplicate_members = member_frame["asset_id"].duplicated(keep=False)
    if duplicate_members.any():
        asset_id = member_frame.loc[duplicate_members, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(f"membership contains duplicate asset_id {asset_id}")
    invalid_subindustry = member_frame["consumer_subindustry"].map(
        lambda value: pd.isna(value) or not str(value).strip()
    )
    if invalid_subindustry.any():
        asset_id = member_frame.loc[invalid_subindustry, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(f"membership consumer_subindustry is empty for asset {asset_id}")
    rows: list[dict[str, object]] = []
    histories = {asset_id: history for asset_id, history in frame.groupby("asset_id", sort=False)}
    for membership_row in member_frame.sort_values("asset_id", kind="stable").itertuples(index=False):
        asset_id = membership_row.asset_id
        history = histories.get(asset_id)
        if history is None:
            close = pd.Series(dtype=float)
            latest_trade_date = pd.NaT
            latest_close = math.nan
        else:
            close = history["close"].reset_index(drop=True)
            latest_trade_date = history["trade_date"].iloc[-1]
            latest_close = float(close.iloc[-1])

        history_bars = len(close)
        return_6m = _window_return(close, 126)
        return_60d = _window_return(close, 60)
        ma120 = _moving_average(close, 120)
        ma250 = _moving_average(close, 250)
        max_drawdown_12m = (
            float(latest_close / close.tail(252).max() - 1.0)
            if history_bars >= 252
            else math.nan
        )
        rebound_from_low_60d = (
            float(latest_close / close.tail(60).min() - 1.0)
            if history_bars >= 60
            else math.nan
        )
        rows.append(
            {
                "asset_id": asset_id,
                "latest_trade_date": latest_trade_date,
                "latest_close": latest_close,
                "history_bars": history_bars,
                "price_history_complete": history_bars >= 252,
                "return_6m": return_6m,
                "return_60d": return_60d,
                "max_drawdown_12m": max_drawdown_12m,
                "rebound_from_low_60d": rebound_from_low_60d,
                "ma120": ma120,
                "ma250": ma250,
                "distance_ma120": latest_close / ma120 - 1.0 if math.isfinite(ma120) else math.nan,
                "distance_ma250": latest_close / ma250 - 1.0 if math.isfinite(ma250) else math.nan,
                "consumer_subindustry": membership_row.consumer_subindustry,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=PRICE_OUTPUT_COLUMNS)

    grouped = result.groupby("consumer_subindustry", dropna=False)
    peer_count_6m = grouped["return_6m"].transform("count")
    peer_count_60d = grouped["return_60d"].transform("count")
    result["industry_peer_count"] = peer_count_6m.astype(int)
    result["industry_peer_count_60d"] = peer_count_60d.astype(int)
    result["industry_return_6m"] = grouped["return_6m"].transform("mean")
    result["industry_return_60d"] = grouped["return_60d"].transform("mean")
    result["relative_return_6m"] = result["return_6m"] - result["industry_return_6m"]
    result["relative_return_60d"] = result["return_60d"] - result["industry_return_60d"]
    result["relative_return_coverage"] = peer_count_6m.ge(3) & result["return_6m"].notna()
    result["relative_return_coverage_60d"] = peer_count_60d.ge(3) & result["return_60d"].notna()
    result.loc[
        ~result["relative_return_coverage"],
        ["industry_return_6m", "relative_return_6m"],
    ] = np.nan
    result.loc[
        ~result["relative_return_coverage_60d"],
        ["industry_return_60d", "relative_return_60d"],
    ] = np.nan
    return result.loc[:, PRICE_OUTPUT_COLUMNS].sort_values("asset_id", kind="stable").reset_index(drop=True)


def compute_oversold_score(frame: pd.DataFrame) -> pd.Series:
    """Return the approved cross-sectional oversold score without filling gaps."""
    _require_columns(frame, SCORE_COLUMNS, "frame")
    raw_valuation = frame["valuation_depression_percentile"]
    valuation = pd.to_numeric(raw_valuation, errors="coerce").astype(float)
    invalid_valuation = raw_valuation.notna() & (
        valuation.isna() | ~np.isfinite(valuation) | ~valuation.between(0.0, 1.0)
    )
    if invalid_valuation.any():
        raise ValueError(
            "valuation_depression_percentile must be numeric, finite, and between 0 and 1"
        )

    numeric = frame.loc[:, SCORE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    numeric["valuation_depression_percentile"] = valuation
    drawdown_percentile = numeric["max_drawdown_12m"].rank(pct=True, ascending=False)
    return_6m_percentile = numeric["return_6m"].rank(pct=True, ascending=False)
    relative_return_percentile = numeric["relative_return_6m"].rank(pct=True, ascending=False)
    ma_distance = numeric[["distance_ma120", "distance_ma250"]].mean(axis=1, skipna=False)
    ma_distance_percentile = ma_distance.rank(pct=True, ascending=False)
    score = (
        30.0 * drawdown_percentile
        + 20.0 * return_6m_percentile
        + 20.0 * relative_return_percentile
        + 20.0 * valuation
        + 10.0 * ma_distance_percentile
    ).clip(0.0, 100.0)
    score.name = "oversold_score"
    return score


def _optional_number(row: Mapping[str, object] | pd.Series, field: str) -> tuple[float, bool]:
    value = row.get(field, math.nan)
    if value is None or value is pd.NA:
        return math.nan, False
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise ValueError(f"{field} must be a finite int or float")
    number = float(value)
    if math.isnan(number):
        return math.nan, False
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite int or float")
    return number, True


def compute_already_priced_features(
    price_row: Mapping[str, object] | pd.Series,
    valuation_row: Mapping[str, object] | pd.Series,
    *,
    evidence_revision_state: str = "",
) -> dict[str, object]:
    """Compute deterministic penalty flags for repair that the market already priced."""
    rebound, rebound_coverage = _optional_number(price_row, "rebound_from_low_60d")
    relative_return, relative_return_coverage = _optional_number(price_row, "relative_return_60d")
    valuation, valuation_coverage = _optional_number(valuation_row, "valuation_percentile")
    if valuation_coverage and not 0.0 <= valuation <= 1.0:
        raise ValueError("valuation_percentile must be between 0 and 1")

    rebound_trigger = rebound_coverage and rebound >= 0.25
    relative_return_trigger = relative_return_coverage and relative_return >= 0.10
    valuation_trigger = valuation_coverage and valuation >= 0.50
    evidence_revision_trigger = evidence_revision_state == "broadly_priced"
    penalty = min(
        20.0,
        6.0 * rebound_trigger
        + 4.0 * relative_return_trigger
        + 5.0 * valuation_trigger
        + 5.0 * evidence_revision_trigger,
    )
    return {
        "priced_in_penalty": penalty,
        "priced_in_rebound_trigger": bool(rebound_trigger),
        "priced_in_relative_return_trigger": bool(relative_return_trigger),
        "priced_in_valuation_trigger": bool(valuation_trigger),
        "priced_in_evidence_revision_trigger": bool(evidence_revision_trigger),
        "priced_in_rebound_coverage": rebound_coverage,
        "priced_in_relative_return_coverage": relative_return_coverage,
        "priced_in_valuation_coverage": valuation_coverage,
    }
