from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.dragon_strategy_research import (
    _fallback_industry_diagnostics,
    assign_entry_windows_v2,
    build_dragon_diagnostics,
    load_asset_names,
    load_dragon_bars,
    load_dragon_memberships,
)
from stock_research.factor_store import load_factor_daily, load_top_scores
from stock_research.reports.market_state_report import calc_market_state, load_market_state_bars
from stock_research.reports.sector_strength_report import (
    calc_sector_strength,
    load_sector_strength_bars,
)
from stock_research.watchlist.diagnostics import build_watchlist_diagnostics
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
DEFAULT_EVENT_LOOKBACK_TRADING_DAYS = 20
RESEARCH_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "research"
CASE_EVENT_CSV_PATH = RESEARCH_OUTPUT_DIR / "dragon_case_curated_library_failure_v2_1.csv"
DRAGON_FACTOR_SNAPSHOT_CSV_PATH = RESEARCH_OUTPUT_DIR / "dragon_case_factor_snapshot_2024_2026.csv"
DRAGON_EVENT_DIAGNOSTICS_CSV_PATH = RESEARCH_OUTPUT_DIR / "dragon_case_event_diagnostics.csv"
INDUSTRY_DIAGNOSTICS_CSV_PATH = RESEARCH_OUTPUT_DIR / "industry_focus_score_v2_diagnostics.csv"
LHB_EVENT_CSV_PATH = RESEARCH_OUTPUT_DIR / "lhb_risk_feature_case_detail_v2_1.csv"


def load_industry_memberships(
    trade_date: str,
    asset_ids: list[str],
    industry_system: str,
    service: str = SETTINGS.research_service,
) -> dict[str, dict[str, Any]]:
    if not asset_ids:
        return {}

    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT
            asset_id,
            industry_code,
            industry_name,
            level
        FROM core.industry_membership
        WHERE industry_system = %s
          AND start_date <= %s
          AND (end_date IS NULL OR end_date >= %s)
          AND asset_id IN ({placeholders})
        ORDER BY asset_id, level, start_date DESC
    """
    params = [industry_system, trade_date, trade_date, *asset_ids]
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)

    memberships: dict[str, dict[str, Any]] = {}
    for row in rows:
        asset_id = str(row["asset_id"])
        if asset_id in memberships:
            continue
        memberships[asset_id] = {
            "industry_code": row.get("industry_code"),
            "industry_name": row.get("industry_name"),
            "industry_level": row.get("level"),
        }
    return memberships


def load_feature_snapshot(
    trade_date: str,
    asset_ids: list[str],
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["asset_id", "feature_name", "feature_value"])

    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT asset_id, feature_name, feature_value
        FROM feature_snapshot
        WHERE trade_date = %s
          AND feature_set = 'p0_daily'
          AND feature_version = 'v1'
          AND asset_id IN ({placeholders})
        ORDER BY asset_id, feature_name
    """
    params = [trade_date, *asset_ids]
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, params))


def build_watchlist_diagnostics_snapshot(
    *,
    trade_date: str,
    score_version: str = "manual_v1",
    top_n: int = 50,
    risk_watch_n: int = 10,
    opportunity_watch_n: int = 10,
) -> dict[str, pd.DataFrame]:
    top_scores = _load_top_score_frame(
        trade_date=trade_date,
        score_version=score_version,
        top_n=top_n,
    )
    asset_ids = _asset_ids_from_frame(top_scores)
    asset_identity = _load_asset_identity_map(asset_ids)
    top_scores = _merge_top_scores_with_asset_identity(top_scores, asset_identity)
    factor_frame = _load_watchlist_factor_frame(trade_date=trade_date, asset_ids=asset_ids)
    dragon_frame = _load_dragon_frame(trade_date=trade_date, asset_ids=asset_ids)
    lhb_frame = _load_lhb_frame(trade_date=trade_date, asset_identity=asset_identity)
    event_frame = _load_event_frame(trade_date=trade_date, asset_identity=asset_identity)
    market_frame = _load_market_frame(trade_date=trade_date, asset_ids=asset_ids)
    diagnostics = build_watchlist_diagnostics(
        trade_date=trade_date,
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=lhb_frame,
        event_frame=event_frame,
        market_frame=market_frame,
        risk_watch_n=risk_watch_n,
        opportunity_watch_n=opportunity_watch_n,
    )
    for frame in diagnostics.values():
        if frame.empty:
            frame["watchlist_id"] = pd.Series(dtype="object")
            frame["trade_date"] = pd.Series(dtype="object")
            continue
        frame["watchlist_id"] = "diagnostics"
        frame["trade_date"] = trade_date
    return diagnostics


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


def _load_top_score_frame(
    *,
    trade_date: str,
    score_version: str,
    top_n: int,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        load_top_scores(
            trade_date=trade_date,
            score_version=score_version,
            top_n=top_n,
        )
    )
    expected_columns = [
        "trade_date",
        "asset_id",
        "ts_code",
        "stock_name",
        "rank",
        "score_total",
        "score_version",
        "score_components",
    ]
    for column in expected_columns:
        if column not in frame.columns:
            frame[column] = pd.Series(dtype="object")
    return frame.loc[:, expected_columns].reset_index(drop=True)


def _load_watchlist_factor_frame(
    *,
    trade_date: str,
    asset_ids: list[str],
) -> pd.DataFrame:
    columns = ["asset_id", "amount_vs_20d", "high_to_close_drawdown", "volatility_5d"]
    if not asset_ids:
        return pd.DataFrame(columns=columns)

    feature_snapshot = load_feature_snapshot(trade_date=trade_date, asset_ids=asset_ids)
    result = _pivot_watchlist_feature_frame(feature_snapshot, columns)
    if not result.empty:
        return result

    factor_daily = load_factor_daily(trade_date=trade_date)
    if factor_daily.empty:
        return _load_stock_technical_watchlist_factor_frame(
            trade_date=trade_date,
            asset_ids=asset_ids,
            columns=columns,
        )

    factor_frame = factor_daily.copy()
    factor_frame["asset_id"] = factor_frame["asset_id"].astype(str)
    factor_frame["factor_name"] = factor_frame["factor_name"].astype(str)
    factor_frame = factor_frame[
        factor_frame["asset_id"].isin({str(asset_id) for asset_id in asset_ids})
        & factor_frame["factor_name"].isin({"amount_vs_20d", "high_to_close_drawdown", "volatility_5d"})
    ].rename(columns={"factor_name": "feature_name", "factor_value": "feature_value"})
    result = _pivot_watchlist_feature_frame(factor_frame, columns)
    if not result.empty:
        return result

    return _load_stock_technical_watchlist_factor_frame(
        trade_date=trade_date,
        asset_ids=asset_ids,
        columns=columns,
    )


def _load_stock_technical_watchlist_factor_frame(
    *,
    trade_date: str,
    asset_ids: list[str],
    columns: list[str],
) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=columns)
    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT
            asset_id,
            amount_vs_20d,
            high_to_close_drawdown,
            volatility_5d
        FROM factor.stock_technical_features_daily
        WHERE trade_date = %s
          AND adjust_type = 'qfq'
          AND source = 'technical_features'
          AND source_data_version = 'market_daily_bar:qfq'
          AND calc_version = 'v1'
          AND asset_id IN ({placeholders})
        ORDER BY asset_id
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date, *asset_ids])
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return _ensure_frame_columns(frame, columns).loc[:, columns].reset_index(drop=True)


def _load_dragon_frame(*, trade_date: str, asset_ids: list[str]) -> pd.DataFrame:
    columns = [
        "asset_id",
        "dragon_risk_score",
        "overheat_avoid",
        "crowded_late_entry",
        "entry_window",
        "entry_window_v2",
        "dragon_trade_date",
    ]
    if not asset_ids:
        return pd.DataFrame(columns=columns)

    current_day_frame = _load_current_day_dragon_frame(
        trade_date=trade_date,
        asset_ids=asset_ids,
    )
    if not current_day_frame.empty:
        return _ensure_frame_columns(current_day_frame, columns).loc[:, columns].reset_index(drop=True)

    asset_identity = _load_asset_identity_map(asset_ids)
    if asset_identity.empty:
        return pd.DataFrame(columns=columns)

    ts_codes = _ts_codes_from_frame(asset_identity)
    recent_snapshot = _load_recent_dragon_frame(
        trade_date=trade_date,
        ts_codes=ts_codes,
    )
    if recent_snapshot.empty:
        return pd.DataFrame(columns=columns)

    latest_snapshot = _latest_per_ts_code(recent_snapshot, date_column="trade_date").rename(
        columns={"trade_date": "dragon_trade_date"}
    )
    frame = asset_identity.merge(latest_snapshot, on="ts_code", how="inner", suffixes=("", "_dragon"))
    return _ensure_frame_columns(frame, columns).loc[:, columns].reset_index(drop=True)


def _load_current_day_dragon_frame(
    *,
    trade_date: str,
    asset_ids: list[str],
) -> pd.DataFrame:
    columns = [
        "asset_id",
        "dragon_risk_score",
        "overheat_avoid",
        "crowded_late_entry",
        "entry_window",
        "entry_window_v2",
        "dragon_trade_date",
    ]
    if not asset_ids:
        return pd.DataFrame(columns=columns)

    bars = load_dragon_bars(start_date=trade_date, end_date=trade_date)
    if bars.empty:
        return pd.DataFrame(columns=columns)
    memberships = load_dragon_memberships(start_date=trade_date, end_date=trade_date)
    if memberships.empty:
        return pd.DataFrame(columns=columns)

    if INDUSTRY_DIAGNOSTICS_CSV_PATH.exists():
        industry = pd.read_csv(INDUSTRY_DIAGNOSTICS_CSV_PATH, low_memory=False)
    else:
        industry = _fallback_industry_diagnostics(bars, memberships)
    if industry.empty:
        return pd.DataFrame(columns=columns)

    stock_names = load_asset_names()
    diagnostics = build_dragon_diagnostics(
        bars=bars,
        memberships=memberships,
        industry_diagnostics=industry,
        stock_names=stock_names,
        lifecycle_samples=None,
        candidate_scores=None,
        start_date=trade_date,
        end_date=trade_date,
    )
    if diagnostics.empty and INDUSTRY_DIAGNOSTICS_CSV_PATH.exists():
        diagnostics = build_dragon_diagnostics(
            bars=bars,
            memberships=memberships,
            industry_diagnostics=_fallback_industry_diagnostics(bars, memberships),
            stock_names=stock_names,
            lifecycle_samples=None,
            candidate_scores=None,
            start_date=trade_date,
            end_date=trade_date,
        )
    if diagnostics.empty:
        return pd.DataFrame(columns=columns)

    diagnostics = assign_entry_windows_v2(diagnostics)

    diagnostics = diagnostics[diagnostics["asset_id"].astype(str).isin({str(asset_id) for asset_id in asset_ids})].copy()
    if diagnostics.empty:
        return pd.DataFrame(columns=columns)

    diagnostics["dragon_trade_date"] = diagnostics["trade_date"].astype(str)
    diagnostics["overheat_avoid"] = diagnostics.apply(
        lambda row: _dragon_window_matches(row, "overheat_avoid"),
        axis=1,
    )
    diagnostics["crowded_late_entry"] = diagnostics.apply(
        lambda row: _dragon_window_matches(row, "crowded_late_entry"),
        axis=1,
    )
    return _ensure_frame_columns(diagnostics, columns).loc[:, columns].reset_index(drop=True)


def _load_lhb_frame(*, trade_date: str, asset_identity: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "asset_id",
        "lhb_risk_score",
        "lhb_negative_net_buy",
        "lhb_institution_selling",
        "lhb_high_pump_risk",
        "lhb_after_event_attention",
        "lhb_risk_level",
        "lhb_event_date",
    ]
    if asset_identity.empty:
        return pd.DataFrame(columns=columns)

    ts_codes = _ts_codes_from_frame(asset_identity)
    recent_events = _load_recent_lhb_event_frame(trade_date=trade_date, ts_codes=ts_codes)
    if recent_events.empty:
        return pd.DataFrame(columns=columns)

    latest_events = _latest_per_ts_code(recent_events, date_column="event_date").rename(
        columns={"event_date": "lhb_event_date"}
    )
    frame = asset_identity.merge(latest_events, on="ts_code", how="inner", suffixes=("", "_event"))
    return _ensure_frame_columns(frame, columns).loc[:, columns].reset_index(drop=True)


def _load_event_frame(*, trade_date: str, asset_identity: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "asset_id",
        "event_structure",
        "failure_flag",
        "case_event_type",
        "case_event_date",
        "case_confidence",
    ]
    if asset_identity.empty:
        return pd.DataFrame(columns=columns)

    ts_codes = _ts_codes_from_frame(asset_identity)
    recent_events = _load_recent_case_event_frame(trade_date=trade_date, ts_codes=ts_codes)
    if recent_events.empty:
        return pd.DataFrame(columns=columns)

    latest_events = _latest_per_ts_code(recent_events, date_column="event_date").rename(
        columns={
            "event_type": "case_event_type",
            "event_date": "case_event_date",
            "confidence": "case_confidence",
        }
    )
    latest_events["event_structure"] = latest_events.apply(
        lambda row: _map_case_event_structure(
            row.get("verified_case_type_v2_1"),
            row.get("success_or_failure"),
        ),
        axis=1,
    )
    latest_events["failure_flag"] = (
        latest_events["success_or_failure"].astype(str).str.strip().str.lower().eq("failure")
    )
    frame = asset_identity.merge(latest_events, on="ts_code", how="inner", suffixes=("", "_event"))
    return _ensure_frame_columns(frame, columns).loc[:, columns].reset_index(drop=True)


def _load_market_frame(*, trade_date: str, asset_ids: list[str]) -> pd.DataFrame:
    columns = [
        "asset_id",
        "industry_code",
        "industry_name",
        "sector_strength_rank",
        "sector_strength_score",
        "mainline_flag",
        "market_regime",
        "market_risk_level",
        "entry_allowed",
    ]
    if not asset_ids:
        return pd.DataFrame(columns=columns)

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
        top_n=20,
    )
    sector_map: dict[str, dict[str, Any]] = {}
    if not sector_strength.empty:
        for row in sector_strength.to_dict("records"):
            industry_code = str(row.get("industry_code") or "").strip()
            if not industry_code:
                continue
            sector_map[industry_code] = {
                "sector_strength_rank": row.get("strength_rank"),
                "sector_strength_score": row.get("strength_score"),
                "mainline_flag": True,
            }

    rows: list[dict[str, Any]] = []
    for asset_id in asset_ids:
        industry = industry_map.get(str(asset_id), {})
        sector = sector_map.get(str(industry.get("industry_code") or "").strip(), {})
        rows.append(
            {
                "asset_id": str(asset_id),
                "industry_code": industry.get("industry_code"),
                "industry_name": industry.get("industry_name"),
                "sector_strength_rank": sector.get("sector_strength_rank"),
                "sector_strength_score": sector.get("sector_strength_score"),
                "mainline_flag": bool(sector.get("mainline_flag", False)),
                "market_regime": market_state.get("market_state"),
                "market_risk_level": market_state.get("risk_level"),
                "entry_allowed": market_state.get("entry_allowed"),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _load_asset_identity_map(
    asset_ids: list[str],
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    columns = ["asset_id", "ts_code", "stock_name"]
    if not asset_ids:
        return pd.DataFrame(columns=columns)

    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT asset_id, ts_code, name
        FROM core.asset_master
        WHERE asset_id IN ({placeholders})
        ORDER BY asset_id, ts_code, name
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, asset_ids)

    frame = pd.DataFrame(rows)
    if frame.empty:
        frame = pd.DataFrame({"asset_id": asset_ids})

    frame = frame.rename(columns={"name": "stock_name"})
    frame = _ensure_frame_columns(frame, columns)
    frame["ts_code"] = frame.apply(
        lambda row: row.get("ts_code") if str(row.get("ts_code") or "").strip() else _ts_code_from_asset_id(row.get("asset_id")),
        axis=1,
    )
    needs_name_backfill = frame.apply(
        lambda row: _stock_name_needs_backfill(
            current_name=row.get("stock_name"),
            asset_id=row.get("asset_id"),
            ts_code=row.get("ts_code"),
        ),
        axis=1,
    )
    if bool(needs_name_backfill.any()):
        stock_name_lookup = _load_stock_name_lookup(_ts_codes_from_frame(frame.loc[needs_name_backfill]))
        frame.loc[needs_name_backfill, "stock_name"] = frame.loc[needs_name_backfill].apply(
            lambda row: _resolve_stock_name(
                current_name=row.get("stock_name"),
                asset_id=row.get("asset_id"),
                ts_code=row.get("ts_code"),
                lookup=stock_name_lookup,
            ),
            axis=1,
        )
    frame["_has_ts_code"] = frame["ts_code"].astype(str).str.strip().ne("")
    frame["_has_stock_name"] = frame["stock_name"].astype(str).str.strip().ne("")
    frame = frame.sort_values(
        ["asset_id", "_has_ts_code", "_has_stock_name", "ts_code", "stock_name"],
        ascending=[True, False, False, True, True],
        kind="stable",
    )
    frame = frame.loc[:, columns + ["_has_ts_code", "_has_stock_name"]]
    result = frame.drop_duplicates(subset=["asset_id"], keep="first").reset_index(drop=True)
    return result.loc[:, columns]


def _load_recent_case_event_frame(
    *,
    trade_date: str,
    ts_codes: list[str],
    lookback_days: int = DEFAULT_EVENT_LOOKBACK_TRADING_DAYS,
    path: Path = CASE_EVENT_CSV_PATH,
) -> pd.DataFrame:
    columns = [
        "ts_code",
        "stock_name",
        "event_date",
        "verified_case_type_v2_1",
        "success_or_failure",
        "event_type",
        "confidence",
    ]
    frame = _read_recent_event_csv(
        path=path,
        ts_codes=ts_codes,
        trade_date=trade_date,
        lookback_days=lookback_days,
    )
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return _ensure_frame_columns(frame, columns).loc[:, columns].reset_index(drop=True)


def _load_recent_lhb_event_frame(
    *,
    trade_date: str,
    ts_codes: list[str],
    lookback_days: int = DEFAULT_EVENT_LOOKBACK_TRADING_DAYS,
    path: Path = LHB_EVENT_CSV_PATH,
) -> pd.DataFrame:
    columns = [
        "ts_code",
        "stock_name",
        "event_date",
        "lhb_risk_score",
        "lhb_negative_net_buy",
        "lhb_institution_selling",
        "lhb_high_pump_risk",
        "lhb_after_event_attention",
        "lhb_risk_level",
    ]
    frame = _read_recent_event_csv(
        path=path,
        ts_codes=ts_codes,
        trade_date=trade_date,
        lookback_days=lookback_days,
        date_column="event_date",
    )
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return _ensure_frame_columns(frame, columns).loc[:, columns].reset_index(drop=True)


def _load_recent_dragon_frame(
    *,
    trade_date: str,
    ts_codes: list[str],
    lookback_days: int = DEFAULT_EVENT_LOOKBACK_TRADING_DAYS,
) -> pd.DataFrame:
    columns = [
        "ts_code",
        "stock_name",
        "trade_date",
        "dragon_risk_score",
        "overheat_avoid",
        "crowded_late_entry",
        "entry_window",
        "entry_window_v2",
    ]
    for path in (DRAGON_FACTOR_SNAPSHOT_CSV_PATH, DRAGON_EVENT_DIAGNOSTICS_CSV_PATH):
        frame = _read_recent_event_csv(
            path=path,
            ts_codes=ts_codes,
            trade_date=trade_date,
            lookback_days=lookback_days,
            date_column="trade_date",
        )
        if frame.empty:
            continue
        frame = frame.copy()
        if "overheat_avoid" not in frame.columns:
            frame["overheat_avoid"] = _derive_dragon_window_flag(frame, "overheat_avoid")
        if "crowded_late_entry" not in frame.columns:
            frame["crowded_late_entry"] = _derive_dragon_window_flag(frame, "crowded_late_entry")
        frame = _ensure_frame_columns(frame, columns).loc[:, columns]
        if frame["dragon_risk_score"].notna().any() or frame["overheat_avoid"].any() or frame["crowded_late_entry"].any():
            return frame.reset_index(drop=True)
    return pd.DataFrame(columns=columns)


def _read_recent_event_csv(
    *,
    path: Path,
    ts_codes: list[str],
    trade_date: str,
    lookback_days: int,
    date_column: str = "event_date",
) -> pd.DataFrame:
    if not ts_codes:
        return pd.DataFrame()

    try:
        frame = pd.read_csv(path, low_memory=False)
    except FileNotFoundError:
        return pd.DataFrame()

    if frame.empty or "ts_code" not in frame.columns or date_column not in frame.columns:
        return pd.DataFrame()

    current = pd.Timestamp(trade_date).normalize()
    start = current - pd.tseries.offsets.BDay(max(lookback_days - 1, 0))
    normalized_codes = {str(code).strip().upper() for code in ts_codes if str(code).strip()}

    result = frame.copy()
    result["ts_code"] = result["ts_code"].astype(str).str.strip().str.upper()
    result[date_column] = pd.to_datetime(result[date_column], errors="coerce").dt.normalize()
    result = result[
        result["ts_code"].isin(normalized_codes)
        & result[date_column].notna()
        & (result[date_column] <= current)
        & (result[date_column] >= start)
    ].copy()
    if result.empty:
        return pd.DataFrame()
    return result.sort_values(["ts_code", date_column]).reset_index(drop=True)


def _pivot_watchlist_feature_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=columns)
    if "asset_id" not in frame.columns or "feature_name" not in frame.columns or "feature_value" not in frame.columns:
        return pd.DataFrame(columns=columns)

    working = frame.copy()
    working["asset_id"] = working["asset_id"].astype(str)
    working["feature_name"] = working["feature_name"].astype(str)
    working = working[
        working["feature_name"].isin({"amount_vs_20d", "high_to_close_drawdown", "volatility_5d"})
    ]
    if working.empty:
        return pd.DataFrame(columns=columns)

    result = (
        working.pivot_table(
            index="asset_id",
            columns="feature_name",
            values="feature_value",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(columns=None)
    )
    for column in columns:
        if column not in result.columns:
            result[column] = pd.Series(dtype="float64" if column != "asset_id" else "object")
    return result.loc[:, columns]


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
    sector_top_n = _sector_strength_top_n(bars, trade_date=trade_date, requested_top_n=top_n)
    return calc_sector_strength(bars, trade_date=trade_date, top_n=sector_top_n)


def _sector_strength_top_n(
    bars: pd.DataFrame,
    *,
    trade_date: str,
    requested_top_n: int,
) -> int:
    if bars.empty or "industry_code" not in bars.columns:
        return requested_top_n

    frame = bars.copy()
    if "trade_date" in frame.columns:
        frame["trade_date"] = frame["trade_date"].map(lambda value: pd.Timestamp(value).date().isoformat())
        frame = frame[frame["trade_date"] <= trade_date]

    current_sector_count = int(frame["industry_code"].dropna().astype(str).nunique())
    return max(requested_top_n, current_sector_count)


def _asset_ids_from_frame(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "asset_id" not in frame.columns:
        return []
    return frame["asset_id"].dropna().astype(str).drop_duplicates().tolist()


def _ts_codes_from_frame(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "ts_code" not in frame.columns:
        return []
    return frame["ts_code"].dropna().astype(str).str.strip().drop_duplicates().tolist()


def _empty_diagnostics_frame(asset_ids: list[str]) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["asset_id"])
    return pd.DataFrame({"asset_id": asset_ids})


def _ensure_frame_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.Series(dtype="object")
    return result


def _merge_top_scores_with_asset_identity(
    top_scores: pd.DataFrame,
    asset_identity: pd.DataFrame,
) -> pd.DataFrame:
    columns = list(top_scores.columns)
    if asset_identity.empty:
        return _ensure_frame_columns(top_scores, columns)

    frame = top_scores.merge(
        asset_identity,
        on="asset_id",
        how="left",
        suffixes=("", "_identity"),
    )
    for column in ("ts_code", "stock_name"):
        identity_column = f"{column}_identity"
        if identity_column in frame.columns:
            empty_mask = frame[column].isna() | frame[column].astype(str).str.strip().eq("")
            frame[column] = frame[column].where(~empty_mask, frame[identity_column])
            frame = frame.drop(columns=[identity_column])
    return _ensure_frame_columns(frame, columns).loc[:, columns].reset_index(drop=True)


def _latest_per_ts_code(frame: pd.DataFrame, *, date_column: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    tie_break_columns = [column for column in sorted(frame.columns) if column not in {"ts_code", date_column}]
    ordered = frame.sort_values(["ts_code", date_column, *tie_break_columns], kind="stable")
    return ordered.drop_duplicates(subset=["ts_code"], keep="last").reset_index(drop=True)


def _ts_code_from_asset_id(asset_id: Any) -> str:
    parts = str(asset_id or "").strip().split(":")
    if len(parts) != 3:
        return ""
    _, exchange, code = parts
    exchange = exchange.strip().upper()
    code = code.strip()
    if exchange not in {"SH", "SZ", "BJ"} or not code:
        return ""
    return f"{code}.{exchange}"


def _resolve_stock_name(
    *,
    current_name: Any,
    asset_id: Any,
    ts_code: Any,
    lookup: dict[str, str],
) -> str:
    normalized_name = str(current_name or "").strip()
    normalized_ts_code = str(ts_code or "").strip().upper()
    asset_code = str(asset_id or "").strip().split(":")[-1]
    candidate = lookup.get(normalized_ts_code, "")
    if normalized_name and normalized_name not in {asset_code, normalized_ts_code.split(".")[0]}:
        return normalized_name
    return candidate or normalized_name


def _stock_name_needs_backfill(
    *,
    current_name: Any,
    asset_id: Any,
    ts_code: Any,
) -> bool:
    normalized_name = str(current_name or "").strip()
    normalized_ts_code = str(ts_code or "").strip().upper()
    asset_code = str(asset_id or "").strip().split(":")[-1]
    return not normalized_name or normalized_name in {asset_code, normalized_ts_code.split(".")[0]}


def _load_stock_name_lookup(ts_codes: list[str]) -> dict[str, str]:
    if not ts_codes:
        return {}
    lookup: dict[str, str] = {}
    normalized_codes = {code.upper() for code in ts_codes}
    for path in (
        CASE_EVENT_CSV_PATH,
        LHB_EVENT_CSV_PATH,
        DRAGON_FACTOR_SNAPSHOT_CSV_PATH,
        DRAGON_EVENT_DIAGNOSTICS_CSV_PATH,
    ):
        try:
            frame = pd.read_csv(path, usecols=["ts_code", "stock_name"], low_memory=False)
        except Exception:
            continue
        if frame.empty:
            continue
        frame = frame.copy()
        frame["ts_code"] = frame["ts_code"].astype(str).str.strip().str.upper()
        frame["stock_name"] = frame["stock_name"].astype(str).str.strip()
        frame = frame[
            frame["ts_code"].isin(normalized_codes)
            & frame["stock_name"].ne("")
        ]
        if frame.empty:
            continue
        for row in frame.to_dict("records"):
            lookup.setdefault(str(row["ts_code"]).upper(), str(row["stock_name"]).strip())
    return lookup


def _derive_dragon_window_flag(frame: pd.DataFrame, target: str) -> pd.Series:
    values = []
    for _, row in frame.iterrows():
        candidates = [
            row.get("entry_window"),
            row.get("entry_window_v2"),
            row.get("dragon_role"),
            row.get("dragon_entry_score_v2"),
        ]
        values.append(any(str(value).strip() == target for value in candidates if pd.notna(value)))
    return pd.Series(values, index=frame.index, dtype="bool")


def _dragon_window_matches(row: pd.Series, target: str) -> bool:
    for field in ("entry_window", "entry_window_v2"):
        value = row.get(field)
        if pd.notna(value) and str(value).strip() == target:
            return True
    return False


def _map_case_event_structure(case_type: Any, success_or_failure: Any) -> str:
    normalized = str(case_type or "").strip()
    lowered = normalized.lower()
    if not normalized:
        return ""
    if lowered in {
        "a_kill_failure",
        "failed_second_wave",
        "high_open_low_close_failure",
        "one_day_pump",
        "failed_reversal",
    }:
        return normalized
    if str(success_or_failure or "").strip().lower() == "failure":
        return normalized
    mapping = {
        "second_wave": "second_wave_candidate",
        "break_then_reversal": "break_then_reversal_candidate",
        "weak_to_strong": "weak_to_strong_candidate",
        "continuous_limit_up": "trend_continuation_candidate",
        "trend_dragon": "trend_continuation_candidate",
    }
    return mapping.get(lowered, normalized)
