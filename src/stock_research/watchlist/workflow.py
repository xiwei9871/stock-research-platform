from __future__ import annotations

import pandas as pd

from stock_research.factor_store import load_top_scores
from stock_research.reports.daily_research_report_cli import (
    load_feature_snapshot,
    load_industry_memberships,
)
from stock_research.reports.market_state_report import calc_market_state, load_market_state_bars
from stock_research.reports.sector_strength_report import (
    calc_sector_strength,
    load_sector_strength_bars,
)
from stock_research.watchlist.signals import build_watchlist_signal_rows
from stock_research.watchlist.store import (
    load_watchlist_daily_signals,
    load_watchlist_items,
    store_watchlist_daily_signals,
)


DEFAULT_INDEX_ID = "CSI300"
DEFAULT_INDUSTRY_SYSTEM = "csrc"
DEFAULT_MARKET_LOOKBACK_DAYS = 90
DEFAULT_SECTOR_LOOKBACK_DAYS = 60


def build_watchlist_snapshot(
    *,
    trade_date: str,
    watchlist_id: str,
    score_version: str = "manual_v1",
    top_n: int = 30,
    output_version: str = "v1",
) -> pd.DataFrame:
    watchlist_items = load_watchlist_items(watchlist_id, active_only=True)
    top_scores = load_top_scores(
        trade_date=trade_date,
        score_version=score_version,
        top_n=top_n,
    )
    asset_ids = sorted(
        {
            str(row.get("asset_id"))
            for row in watchlist_items.to_dict("records")
            if row.get("asset_id")
        }
        | {str(row.get("asset_id")) for row in top_scores if row.get("asset_id")}
    )
    feature_snapshot = load_feature_snapshot(trade_date=trade_date, asset_ids=asset_ids)
    industry_map = load_industry_memberships(
        trade_date=trade_date,
        asset_ids=asset_ids,
        industry_system=DEFAULT_INDUSTRY_SYSTEM,
    )
    market_state = _load_market_state(
        trade_date=trade_date,
        index_id=DEFAULT_INDEX_ID,
        lookback_days=DEFAULT_MARKET_LOOKBACK_DAYS,
    )
    sector_strength = _load_sector_strength(
        trade_date=trade_date,
        industry_system=DEFAULT_INDUSTRY_SYSTEM,
        lookback_days=DEFAULT_SECTOR_LOOKBACK_DAYS,
        top_n=top_n,
    )

    frame = build_watchlist_signal_rows(
        watchlist_items=watchlist_items,
        top_scores=top_scores,
        feature_snapshot=feature_snapshot,
        market_state=market_state,
        sector_strength=sector_strength,
        industry_map=industry_map,
        output_version=output_version,
    )
    frame = frame.copy()
    frame["watchlist_id"] = watchlist_id
    frame["trade_date"] = trade_date
    store_watchlist_daily_signals(frame)
    return frame


def explain_watchlist_asset(
    *,
    trade_date: str,
    watchlist_id: str,
    asset_id: str,
) -> dict[str, object]:
    frame = load_watchlist_daily_signals(watchlist_id, trade_date=trade_date)
    if frame.empty:
        raise ValueError(f"no watchlist signals found for {watchlist_id!r} on {trade_date}")

    match = frame[frame["asset_id"] == asset_id]
    if match.empty:
        raise ValueError(f"no watchlist signal found for asset {asset_id!r}")
    return match.iloc[0].to_dict()


def _load_market_state(
    *,
    trade_date: str,
    index_id: str = DEFAULT_INDEX_ID,
    lookback_days: int = DEFAULT_MARKET_LOOKBACK_DAYS,
) -> dict[str, object]:
    start_date = (pd.Timestamp(trade_date) - pd.Timedelta(days=lookback_days)).date().isoformat()
    bars = load_market_state_bars(start_date=start_date, end_date=trade_date, index_id=index_id)
    return calc_market_state(bars, trade_date=trade_date, index_id=index_id)


def _load_sector_strength(
    *,
    trade_date: str,
    industry_system: str = DEFAULT_INDUSTRY_SYSTEM,
    lookback_days: int = DEFAULT_SECTOR_LOOKBACK_DAYS,
    top_n: int = 30,
) -> pd.DataFrame:
    start_date = (pd.Timestamp(trade_date) - pd.Timedelta(days=lookback_days)).date().isoformat()
    bars = load_sector_strength_bars(
        start_date=start_date,
        end_date=trade_date,
        industry_system=industry_system,
    )
    return calc_sector_strength(bars, trade_date=trade_date, top_n=top_n)
