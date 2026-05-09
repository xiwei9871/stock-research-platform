from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import manual_v1_config
from stock_research.factor_store import upsert_factor_daily
from stock_research.factors import momentum, risk, trend, volume_price


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
    WITH ranked AS (
        SELECT
            trade_date,
            asset_id,
            open,
            high,
            low,
            close,
            preclose,
            volume,
            amount,
            turnover_rate,
            trade_status,
            is_st,
            row_number() over (partition by asset_id order by trade_date desc) AS row_num
        FROM market_daily_bar
        WHERE trade_date <= %s
          AND adjust_type = %s
    )
    SELECT
        trade_date,
        asset_id,
        open,
        high,
        low,
        close,
        preclose,
        volume,
        amount,
        turnover_rate,
        trade_status,
        is_st
    FROM ranked
    WHERE row_num <= %s
    ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, adjust_type, lookback_bars])
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
    calculators = (
        momentum.compute_momentum_factors,
        trend.compute_trend_factors,
        volume_price.compute_volume_price_factors,
        risk.compute_risk_factors,
    )

    for asset_id, group in bars.groupby("asset_id", sort=False):
        frame = group.sort_values("trade_date").reset_index(drop=True)
        computed = frame.copy()
        for calculator in calculators:
            factor_frame = calculator(frame)
            for column in factor_frame.columns:
                computed[column] = factor_frame[column]

        missing_factor_names = [
            factor_name
            for factor_name in factor_groups
            if factor_name not in computed.columns
        ]
        if strict and missing_factor_names:
            missing = ", ".join(sorted(missing_factor_names))
            raise ValueError(
                f"Missing configured technical factor outputs for {asset_id}: {missing}"
            )

        matching = computed[
            computed["trade_date"].astype(str).str[:10] == normalized_trade_date
        ]
        if matching.empty:
            continue

        record = matching.iloc[-1]
        for factor_name, factor_group in factor_groups.items():
            if factor_name not in computed.columns:
                continue

            value = record.get(factor_name)
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


def build_and_store_factor_daily(
    trade_date: str,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
) -> int:
    config = manual_v1_config()
    bars = load_market_bars_for_factor_date(trade_date, lookback_bars=lookback_bars)
    factors = compute_technical_factor_rows(
        bars,
        trade_date=trade_date,
        factor_groups=config["factor_groups"],
        calc_version=config["calc_version"],
        source_data_version=config["source_data_version"],
        # Sector factors are configured now but added to the pipeline in a later task.
        strict=False,
    )
    return upsert_factor_daily(factors)
