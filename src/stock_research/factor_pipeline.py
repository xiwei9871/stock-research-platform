from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import manual_v1_config
from stock_research.factor_registry import (
    get_factor_metadata,
    validate_factor_direction_mapping,
    validate_factor_group_mapping,
)
from stock_research.factor_store import upsert_factor_daily
from stock_research.factors import (
    alpha101,
    gtja191,
    momentum,
    quality,
    qlib_alpha,
    risk,
    sector,
    trend,
    value,
    volume_price,
)
from stock_research.services import finance_ttm, point_in_time_finance


FACTOR_DAILY_COLUMNS = [
    "trade_date",
    "asset_id",
    "factor_name",
    "factor_group",
    "factor_value",
    "calc_version",
    "source",
    "source_data_version",
]


def load_market_bars_for_factor_date(
    trade_date: str,
    lookback_bars: int = 130,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    WITH lookback_dates AS (
        SELECT DISTINCT trade_date
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date <= %s
        ORDER BY trade_date DESC
        LIMIT %s
    )
    SELECT
        bars.trade_date,
        bars.asset_id,
        bars.open,
        bars.high,
        bars.low,
        bars.close,
        bars.preclose,
        bars.volume,
        bars.amount,
        bars.turnover_rate,
        bars.trade_status,
        bars.is_st
    FROM market_daily_bar bars
    JOIN lookback_dates dates
      ON dates.trade_date = bars.trade_date
    WHERE bars.adjust_type = %s
    ORDER BY bars.asset_id, bars.trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, trade_date, lookback_bars, adjust_type])
    return pd.DataFrame(rows)


def enrich_bars_with_industry(
    bars: pd.DataFrame,
    trade_date: str,
    industry_system: str = "csrc",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT DISTINCT ON (asset_id)
        asset_id,
        industry_code,
        industry_name
    FROM core.industry_membership
    WHERE industry_system = %s
      AND start_date <= %s
      AND (end_date IS NULL OR end_date > %s)
    ORDER BY asset_id, start_date DESC
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [industry_system, trade_date, trade_date])
    memberships = pd.DataFrame(rows)
    result = bars.copy()
    if memberships.empty:
        result["industry_code"] = None
        result["industry_name"] = None
        return result
    return result.merge(memberships, on="asset_id", how="left")


def load_industry_bars_for_factor_date(
    trade_date: str,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    WITH lookback_dates AS (
        SELECT DISTINCT trade_date
        FROM market.industry_daily_bar
        WHERE industry_system = %s
          AND trade_date <= %s
        ORDER BY trade_date DESC
        LIMIT %s
    )
    SELECT
        bars.trade_date,
        bars.industry_code,
        bars.industry_name,
        bars.open,
        bars.high,
        bars.low,
        bars.close,
        bars.preclose,
        bars.volume,
        bars.amount
    FROM market.industry_daily_bar bars
    JOIN lookback_dates dates
      ON dates.trade_date = bars.trade_date
    WHERE bars.industry_system = %s
    ORDER BY bars.industry_code, bars.trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [industry_system, trade_date, lookback_bars, industry_system])
    return pd.DataFrame(rows)


def compute_technical_factor_rows(
    bars: pd.DataFrame,
    trade_date: str,
    factor_groups: dict[str, str],
    calc_version: str,
    source_data_version: str,
    *,
    strict: bool = True,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if bars.empty:
        return pd.DataFrame(columns=FACTOR_DAILY_COLUMNS)

    normalized_trade_date = str(trade_date)[:10]
    supported_factor_names = set(_latest_technical_factor_names())
    missing_factor_names = [
        factor_name
        for factor_name in factor_groups
        if factor_name not in supported_factor_names
    ]
    if strict and missing_factor_names:
        missing = ", ".join(sorted(missing_factor_names))
        raise ValueError(f"Missing configured technical factor outputs: {missing}")

    for asset_id, group in bars.groupby("asset_id", sort=False):
        frame = group.sort_values("trade_date").reset_index(drop=True)
        matching_indexes = frame.index[
            frame["trade_date"].astype(str).str[:10] == normalized_trade_date
        ].tolist()
        if not matching_indexes:
            continue

        history = frame.iloc[: matching_indexes[-1] + 1].copy()
        values = _latest_technical_factor_values(history)
        for factor_name, factor_group in factor_groups.items():
            if factor_name not in values:
                continue

            value = values[factor_name]
            if pd.isna(value):
                continue

            rows.append(
                {
                    "trade_date": normalized_trade_date,
                    "asset_id": str(asset_id),
                    "factor_name": factor_name,
                    "factor_group": factor_group,
                    "factor_value": float(value),
                    "calc_version": calc_version,
                    "source": "custom",
                    "source_data_version": source_data_version,
                }
            )

    return pd.DataFrame(rows, columns=FACTOR_DAILY_COLUMNS)


def _latest_technical_factor_names() -> tuple[str, ...]:
    return (
        "ret_5",
        "ret_10",
        "ret_20",
        "ret_60",
        "ret_120",
        "absolute_momentum_5",
        "absolute_momentum_10",
        "absolute_momentum_20",
        "absolute_momentum_60",
        "absolute_momentum_120",
        "momentum_20_5",
        "momentum_60_5",
        "ma20",
        "ma60",
        "close_above_ma20",
        "close_above_ma60",
        "ma20_slope",
        "ma60_slope",
        "ma_alignment",
        "new_high_20",
        "new_high_60",
        "trend_slope_20",
        "trend_r2_20",
        "amount_ratio_5_20",
        "amount_vs_20d",
        "volume_ratio_5_20",
        "turnover_ratio_5_20",
        "price_volume_corr_10",
        "obv",
        "obv_trend_20",
        "volume_breakout",
        "amount_breakout",
        "volatility_5d",
        "volatility_20",
        "max_drawdown_20",
        "atr_14",
        "atr_pct",
        "high_to_close_drawdown",
        "distance_ma20",
        "distance_ma60",
        "upper_shadow_ratio",
        "large_volume_down_day",
    )


def _latest_technical_factor_values(frame: pd.DataFrame) -> dict[str, float | bool]:
    close = pd.to_numeric(frame.get("close"), errors="coerce")
    high = pd.to_numeric(frame.get("high"), errors="coerce")
    low = pd.to_numeric(frame.get("low"), errors="coerce")
    open_ = pd.to_numeric(frame.get("open"), errors="coerce")
    preclose = pd.to_numeric(frame.get("preclose"), errors="coerce").fillna(close.shift(1))
    volume = pd.to_numeric(frame.get("volume"), errors="coerce")
    amount = pd.to_numeric(frame.get("amount"), errors="coerce")
    turnover = pd.to_numeric(frame.get("turnover_rate"), errors="coerce")

    ret_5 = _latest_return(close, 5)
    ret_10 = _latest_return(close, 10)
    ret_20 = _latest_return(close, 20)
    ret_60 = _latest_return(close, 60)
    ret_120 = _latest_return(close, 120)
    ma20 = _latest_mean(close, 20)
    ma60 = _latest_mean(close, 60)
    latest_close = _latest(close)
    latest_high = _latest(high)
    latest_low = _latest(low)
    latest_open = _latest(open_)
    latest_preclose = _latest(preclose)

    true_range = pd.concat(
        [
            high - low,
            (high - preclose).abs(),
            (low - preclose).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_14 = _latest_mean(true_range, 14)
    upper_shadow = latest_high - max(latest_open, latest_close)
    full_range = latest_high - latest_low
    price_direction = close.diff().fillna(0.0).map(
        lambda value: 1.0 if value > 0 else -1.0 if value < 0 else 0.0
    )
    obv_series = (price_direction * volume.fillna(0.0)).cumsum()
    obv = _latest(obv_series)
    amount_mean_20 = _latest_mean(amount, 20)
    amount_vs_20d = _safe_ratio(_latest(amount), amount_mean_20)
    high_to_close_drawdown = _safe_ratio(latest_high - latest_close, latest_high)

    return {
        "ret_5": ret_5,
        "ret_10": ret_10,
        "ret_20": ret_20,
        "ret_60": ret_60,
        "ret_120": ret_120,
        "absolute_momentum_5": ret_5,
        "absolute_momentum_10": ret_10,
        "absolute_momentum_20": ret_20,
        "absolute_momentum_60": ret_60,
        "absolute_momentum_120": ret_120,
        "momentum_20_5": ret_20 - ret_5 if not pd.isna(ret_20) and not pd.isna(ret_5) else np.nan,
        "momentum_60_5": ret_60 - ret_5 if not pd.isna(ret_60) and not pd.isna(ret_5) else np.nan,
        "ma20": ma20,
        "ma60": ma60,
        "close_above_ma20": latest_close > ma20,
        "close_above_ma60": latest_close > ma60,
        "ma20_slope": ma20 - _window_mean_before_tail(close, 20, 5),
        "ma60_slope": ma60 - _window_mean_before_tail(close, 60, 5),
        "ma_alignment": latest_close > ma20 and ma20 > ma60 if not pd.isna(ma20) and not pd.isna(ma60) else np.nan,
        "new_high_20": latest_close >= _latest_max(close, 20),
        "new_high_60": latest_close >= _latest_max(close, 60),
        "trend_slope_20": _latest_rolling_slope(close, 20),
        "trend_r2_20": _latest_rolling_r2(close, 20),
        "amount_ratio_5_20": _safe_ratio(_latest_mean(amount, 5), amount_mean_20),
        "amount_vs_20d": amount_vs_20d,
        "volume_ratio_5_20": _safe_ratio(_latest_mean(volume, 5), _latest_mean(volume, 20)),
        "turnover_ratio_5_20": _safe_ratio(_latest_mean(turnover, 5), _latest_mean(turnover, 20)),
        "price_volume_corr_10": _latest_corr(close, volume, 10),
        "obv": obv,
        "obv_trend_20": obv - _lag_value(obv_series, 20),
        "volume_breakout": _safe_ge(_latest(volume), _latest_max(volume, 20)),
        "amount_breakout": _safe_ge(_latest(amount), _latest_max(amount, 20)),
        "volatility_5d": _latest_volatility(close, 5),
        "volatility_20": _latest_volatility(close, 20),
        "max_drawdown_20": _latest_max_drawdown(close, 20),
        "atr_14": atr_14,
        "atr_pct": _safe_ratio(atr_14, latest_close),
        "high_to_close_drawdown": high_to_close_drawdown,
        "distance_ma20": _safe_ratio(latest_close, ma20) - 1.0,
        "distance_ma60": _safe_ratio(latest_close, ma60) - 1.0,
        "upper_shadow_ratio": _safe_ratio(upper_shadow, full_range),
        "large_volume_down_day": (
            latest_close < latest_preclose
            and _latest(amount) > amount_mean_20 * 1.5
            if not pd.isna(latest_preclose) and not pd.isna(amount_mean_20)
            else np.nan
        ),
    }


def _latest(series: pd.Series) -> float:
    if series.empty:
        return np.nan
    return float(series.iloc[-1]) if not pd.isna(series.iloc[-1]) else np.nan


def _lag_value(series: pd.Series, period: int) -> float:
    if len(series) <= period:
        return np.nan
    value = series.iloc[-1 - period]
    return float(value) if not pd.isna(value) else np.nan


def _latest_return(series: pd.Series, window: int) -> float:
    if len(series) <= window:
        return np.nan
    current = _latest(series)
    previous = series.iloc[-1 - window]
    return _safe_ratio(current, previous) - 1.0


def _latest_mean(series: pd.Series, window: int) -> float:
    if len(series) < window:
        return np.nan
    window_values = pd.to_numeric(series.tail(window), errors="coerce")
    if window_values.isna().any():
        return np.nan
    return float(window_values.mean())


def _window_mean_before_tail(series: pd.Series, window: int, lag: int) -> float:
    if len(series) < window + lag:
        return np.nan
    window_values = pd.to_numeric(series.iloc[-window - lag : -lag], errors="coerce")
    if window_values.isna().any():
        return np.nan
    return float(window_values.mean())


def _latest_max(series: pd.Series, window: int) -> float:
    if len(series) < window:
        return np.nan
    window_values = pd.to_numeric(series.tail(window), errors="coerce")
    if window_values.isna().any():
        return np.nan
    return float(window_values.max())


def _latest_corr(left: pd.Series, right: pd.Series, window: int) -> float:
    if len(left) < window or len(right) < window:
        return np.nan
    left_window = pd.to_numeric(left.tail(window), errors="coerce")
    right_window = pd.to_numeric(right.tail(window), errors="coerce")
    if left_window.isna().any() or right_window.isna().any():
        return np.nan
    result = left_window.corr(right_window)
    return float(result) if not pd.isna(result) else np.nan


def _latest_volatility(close: pd.Series, window: int) -> float:
    if len(close) <= window:
        return np.nan
    returns = pd.to_numeric(close, errors="coerce").pct_change().tail(window)
    if returns.isna().any():
        return np.nan
    return float(returns.std())


def _latest_max_drawdown(close: pd.Series, window: int) -> float:
    if len(close) < window:
        return np.nan
    clean = pd.to_numeric(close.tail(window), errors="coerce")
    if clean.isna().any():
        return np.nan
    drawdown = clean / clean.cummax() - 1.0
    return float(drawdown.min())


def _latest_rolling_slope(series: pd.Series, window: int) -> float:
    if len(series) < window:
        return np.nan
    values = pd.to_numeric(series.tail(window), errors="coerce").to_numpy(dtype="float64")
    if np.isnan(values).any():
        return np.nan
    x = np.arange(window, dtype="float64")
    return float(np.polyfit(x, values, 1)[0])


def _latest_rolling_r2(series: pd.Series, window: int) -> float:
    if len(series) < window:
        return np.nan
    values = pd.to_numeric(series.tail(window), errors="coerce").to_numpy(dtype="float64")
    if np.isnan(values).any():
        return np.nan
    y_mean = float(values.mean())
    total = float(((values - y_mean) ** 2).sum())
    if total == 0.0:
        return np.nan
    x = np.arange(window, dtype="float64")
    coefficients = np.polyfit(x, values, 1)
    fitted = coefficients[0] * x + coefficients[1]
    residual = float(((values - fitted) ** 2).sum())
    return float(1.0 - residual / total)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return np.nan
    return float(numerator) / float(denominator)


def _safe_ge(left: float, right: float) -> bool | float:
    if pd.isna(left) or pd.isna(right):
        return np.nan
    return float(left) >= float(right)


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None and not pd.isna(value):
            return value
    return None


def load_point_in_time_fundamentals_snapshot(
    bars: pd.DataFrame,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    columns = [
        "asset_id",
        "close",
        "roe",
        "roa",
        "gross_margin",
        "net_margin",
        "debt_ratio",
        "revenue_yoy",
        "np_yoy",
        "deduct_np_yoy",
        "ocf_to_np",
        "np_parent_ttm",
        "revenue_ttm",
        "equity_parent",
        "total_share",
        "float_share",
    ]
    if bars.empty:
        return pd.DataFrame(columns=columns)

    normalized_trade_date = str(trade_date)[:10]
    current_day_bars = bars[
        bars["trade_date"].astype(str).str[:10] == normalized_trade_date
    ].copy()
    if current_day_bars.empty:
        return pd.DataFrame(columns=columns)

    universe = (
        current_day_bars[["asset_id", "close"]]
        .drop_duplicates(subset=["asset_id"], keep="last")
        .reset_index(drop=True)
        .copy()
    )
    asset_ids = [str(asset_id) for asset_id in universe["asset_id"].tolist()]
    snapshot_rows: list[dict[str, Any]] = []
    with connect(service) as conn:
        indicators = (
            point_in_time_finance.get_latest_indicator_rows(conn, asset_ids, normalized_trade_date)
            or {}
        )
        balance_sheets = (
            point_in_time_finance.get_latest_balance_sheet_rows(
                conn, asset_ids, normalized_trade_date
            )
            or {}
        )
        cash_flows = (
            point_in_time_finance.get_latest_cash_flow_rows(conn, asset_ids, normalized_trade_date)
            or {}
        )
        share_capital_events = (
            point_in_time_finance.get_latest_share_capital_event_rows(
                conn, asset_ids, normalized_trade_date
            )
            or {}
        )
        income_ttm = (
            finance_ttm.load_income_ttm_rows(
                conn,
                asset_ids,
                normalized_trade_date,
                value_columns=["np_parent", "revenue"],
            )
            or {}
        )
    for asset_id, close in universe[["asset_id", "close"]].itertuples(index=False, name=None):
        normalized_asset_id = str(asset_id)
        indicator = indicators.get(normalized_asset_id, {})
        balance_sheet = balance_sheets.get(normalized_asset_id, {})
        cash_flow = cash_flows.get(normalized_asset_id, {})
        share_capital_event = share_capital_events.get(normalized_asset_id, {})
        ttm_row = income_ttm.get(normalized_asset_id, {})
        snapshot_rows.append(
            {
                "asset_id": normalized_asset_id,
                "close": close,
                "roe": indicator.get("roe"),
                "roa": indicator.get("roa"),
                "gross_margin": indicator.get("gross_margin"),
                "net_margin": indicator.get("net_margin"),
                "debt_ratio": indicator.get("debt_ratio"),
                "revenue_yoy": indicator.get("revenue_yoy"),
                "np_yoy": indicator.get("np_yoy"),
                "deduct_np_yoy": indicator.get("deduct_np_yoy"),
                "ocf_to_np": _coalesce(indicator.get("ocf_to_np"), cash_flow.get("ocf_to_np")),
                "np_parent_ttm": ttm_row.get("np_parent_ttm"),
                "revenue_ttm": ttm_row.get("revenue_ttm"),
                "equity_parent": _coalesce(
                    balance_sheet.get("equity_parent"),
                    balance_sheet.get("total_equity"),
                ),
                "total_share": share_capital_event.get("total_share"),
                "float_share": share_capital_event.get("float_share"),
            }
        )
    return pd.DataFrame(snapshot_rows, columns=columns)


def _melt_factor_frame(
    frame: pd.DataFrame,
    trade_date: str,
    factor_group: str,
    factor_names: list[str],
    calc_version: str,
    source_data_version: str,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=FACTOR_DAILY_COLUMNS)

    available_names = [name for name in factor_names if name in frame.columns]
    if not available_names:
        return pd.DataFrame(columns=FACTOR_DAILY_COLUMNS)

    melted = frame.melt(
        id_vars=["asset_id"],
        value_vars=available_names,
        var_name="factor_name",
        value_name="factor_value",
    )
    melted["factor_value"] = pd.to_numeric(melted["factor_value"], errors="coerce")
    melted = melted.dropna(subset=["factor_value"]).copy()
    if melted.empty:
        return pd.DataFrame(columns=FACTOR_DAILY_COLUMNS)

    melted["trade_date"] = str(trade_date)[:10]
    melted["factor_group"] = factor_group
    melted["calc_version"] = calc_version
    melted["source"] = "fundamental"
    melted["source_data_version"] = source_data_version
    return melted[FACTOR_DAILY_COLUMNS]


def build_quality_factor_rows(
    snapshot: pd.DataFrame,
    trade_date: str,
    calc_version: str,
    source_data_version: str,
) -> pd.DataFrame:
    if snapshot.empty:
        return pd.DataFrame(columns=FACTOR_DAILY_COLUMNS)
    quality_snapshot = snapshot.copy()
    for column in ["roe", "roa", "gross_margin", "net_margin", "debt_ratio", "ocf_to_np"]:
        if column not in quality_snapshot.columns:
            quality_snapshot[column] = np.nan
    factors = quality.compute_quality_factors(quality_snapshot)
    return _melt_factor_frame(
        factors,
        trade_date=trade_date,
        factor_group="quality",
        factor_names=["roe", "roa", "gross_margin", "net_margin", "debt_ratio", "ocf_to_np"],
        calc_version=calc_version,
        source_data_version=source_data_version,
    )


def build_value_factor_rows(
    snapshot: pd.DataFrame,
    trade_date: str,
    calc_version: str,
    source_data_version: str,
) -> pd.DataFrame:
    if snapshot.empty:
        return pd.DataFrame(columns=FACTOR_DAILY_COLUMNS)

    value_snapshot = snapshot.copy()
    for column in ["np_parent_ttm", "revenue_ttm", "equity_parent"]:
        if column not in value_snapshot.columns:
            value_snapshot[column] = np.nan
    for column in ["total_share", "float_share"]:
        if column not in value_snapshot.columns:
            value_snapshot[column] = np.nan

    prices = value_snapshot[["asset_id", "close"]].copy()
    finance = value_snapshot[["asset_id", "np_parent_ttm", "revenue_ttm", "equity_parent"]].copy()
    shares = value_snapshot[["asset_id", "total_share", "float_share"]].copy()
    shares["total_share"] = pd.to_numeric(shares["total_share"], errors="coerce")
    shares["float_share"] = pd.to_numeric(shares["float_share"], errors="coerce")
    factors = value.compute_value_factors(prices, finance, shares)
    for column in ["pe_ttm", "ps_ttm", "pb"]:
        if column in factors.columns:
            factors.loc[pd.to_numeric(factors[column], errors="coerce") <= 0, column] = np.nan
    return _melt_factor_frame(
        factors,
        trade_date=trade_date,
        factor_group="value",
        factor_names=["pe_ttm", "ps_ttm", "pb"],
        calc_version=calc_version,
        source_data_version=source_data_version,
    )


def compute_sector_factor_rows(
    stock_bars: pd.DataFrame,
    industry_bars: pd.DataFrame,
    trade_date: str,
    factor_groups: dict[str, str],
    calc_version: str,
    source_data_version: str,
) -> pd.DataFrame:
    sector_factors = {
        name: group for name, group in factor_groups.items() if group == "sector"
    }
    if not sector_factors or stock_bars.empty or industry_bars.empty:
        return pd.DataFrame(columns=FACTOR_DAILY_COLUMNS)

    normalized_trade_date = str(trade_date)[:10]
    computed = sector.compute_sector_factors(stock_bars, industry_bars, ret_window=20)
    latest = computed[computed["trade_date"].astype(str).str[:10] == normalized_trade_date]
    rows: list[dict[str, Any]] = []
    for _, record in latest.iterrows():
        for factor_name, factor_group in sector_factors.items():
            if factor_name not in computed.columns:
                continue
            value = record.get(factor_name)
            if pd.isna(value):
                continue
            rows.append(
                {
                    "trade_date": normalized_trade_date,
                    "asset_id": str(record["asset_id"]),
                    "factor_name": factor_name,
                    "factor_group": factor_group,
                    "factor_value": float(value),
                    "calc_version": calc_version,
                    "source": "custom",
                    "source_data_version": source_data_version,
                }
            )
    return pd.DataFrame(rows, columns=FACTOR_DAILY_COLUMNS)


def compute_external_factor_rows(
    bars: pd.DataFrame,
    trade_date: str,
    factor_groups: dict[str, str],
    calc_version: str,
    source_data_version: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if bars.empty:
        return pd.DataFrame(columns=FACTOR_DAILY_COLUMNS)

    normalized_trade_date = str(trade_date)[:10]
    external_groups = {
        source: {
            name: group
            for name, group in factor_groups.items()
            if group == source
        }
        for source in _external_factor_sources()
    }

    for group_name, (calculator, source) in _external_factor_sources().items():
        names = external_groups[group_name]
        if not names:
            continue
        computed = calculator(bars)
        latest = computed[computed["trade_date"].astype(str).str[:10] == normalized_trade_date]
        for _, record in latest.iterrows():
            for factor_name, factor_group in names.items():
                if factor_name not in computed.columns:
                    continue
                value = record.get(factor_name)
                if pd.isna(value):
                    continue
                rows.append(
                    {
                        "trade_date": normalized_trade_date,
                        "asset_id": str(record["asset_id"]),
                        "factor_name": factor_name,
                        "factor_group": factor_group,
                        "factor_value": float(value),
                        "calc_version": calc_version,
                        "source": source,
                        "source_data_version": source_data_version,
                    }
                )
    return pd.DataFrame(rows, columns=FACTOR_DAILY_COLUMNS)


def _external_factor_sources() -> dict[str, tuple[Any, str]]:
    return {
        "alpha101": (alpha101.compute_alpha101_factors, "alpha101"),
        "gtja191": (gtja191.compute_gtja191_factors, "gtja191"),
        "qlib": (qlib_alpha.compute_qlib_alpha_factors, "qlib"),
    }


def _validate_emitted_factor_rows(factors: pd.DataFrame) -> None:
    if list(factors.columns) != FACTOR_DAILY_COLUMNS:
        raise ValueError(
            f"factor daily rows must match FACTOR_DAILY_COLUMNS: {list(factors.columns)}"
        )

    if factors.empty:
        return

    mismatches: list[str] = []
    for record in factors[["factor_name", "factor_group"]].drop_duplicates().to_dict("records"):
        factor_name = str(record["factor_name"])
        factor_group = str(record["factor_group"])
        metadata = get_factor_metadata(factor_name)
        if metadata.factor_group != factor_group:
            mismatches.append(
                f"{factor_name}: expected group {metadata.factor_group}, got {factor_group}"
            )
    if mismatches:
        raise ValueError("emitted factor group mismatch: " + "; ".join(mismatches))


def build_and_store_factor_daily(
    trade_date: str,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
) -> int:
    config = manual_v1_config()
    validate_factor_group_mapping(config["factor_groups"])
    validate_factor_direction_mapping(config["factor_directions"])
    bars = load_market_bars_for_factor_date(trade_date, lookback_bars=lookback_bars)
    enriched_bars = enrich_bars_with_industry(
        bars,
        trade_date=trade_date,
        industry_system=industry_system,
    )
    industry_bars = load_industry_bars_for_factor_date(
        trade_date,
        lookback_bars=lookback_bars,
        industry_system=industry_system,
    )
    technical_factors = compute_technical_factor_rows(
        bars,
        trade_date=trade_date,
        factor_groups=config["factor_groups"],
        calc_version=config["calc_version"],
        source_data_version=config["source_data_version"],
        strict=False,
    )
    sector_factors = compute_sector_factor_rows(
        enriched_bars,
        industry_bars,
        trade_date=trade_date,
        factor_groups=config["factor_groups"],
        calc_version=config["calc_version"],
        source_data_version=config["source_data_version"],
    )
    external_factors = compute_external_factor_rows(
        bars,
        trade_date=trade_date,
        factor_groups=config["factor_groups"],
        calc_version=config["calc_version"],
        source_data_version=config["source_data_version"],
    )
    fundamentals = load_point_in_time_fundamentals_snapshot(bars, trade_date=trade_date)
    quality_factors = build_quality_factor_rows(
        fundamentals,
        trade_date=trade_date,
        calc_version=config["calc_version"],
        source_data_version="pit_finance_v1",
    )
    value_factors = build_value_factor_rows(
        fundamentals,
        trade_date=trade_date,
        calc_version=config["calc_version"],
        source_data_version="pit_finance_v1",
    )
    factors = pd.concat(
        [
            technical_factors,
            sector_factors,
            external_factors,
            quality_factors,
            value_factors,
        ],
        ignore_index=True,
    )
    _validate_emitted_factor_rows(factors)
    return upsert_factor_daily(factors)
