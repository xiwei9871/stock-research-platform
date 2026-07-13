from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame
from stock_research.mid_trend_shadow_weekly_control import _simulate_variant, _summary_row
from stock_research.mid_trend_shadow_weekly_optimization import _prices_for_shadow


MID_TREND_V1_BENCHMARK_VARIANT = "top5_weekly_max2_selective_trend_holding_protection_v1"
MID_TREND_V1_ENGINE_VERSION = "mid_trend_v1"
MID_TREND_V1_FEATURE_FUNNEL_PATH = Path(
    "/Users/xiwei/stock_research/outputs/research/"
    "mid_trend_research_overlay_after_2024q4_lookback/"
    "mid_trend_watch_funnel_detail_with_stock_report_features.csv"
)
MID_TREND_V1_OVERLAY_NAME = "report_mild_bonus"
MID_TREND_V1_BENCHMARK_START_DATE = "2025-01-01"


@dataclass(frozen=True)
class MidTrendV1Config:
    start_date: str
    end_date: str
    top_n: int = 5
    buffer_rank: int = 10
    max_weekly_replacements: int = 2
    peak_drawdown_exit: float = 0.12
    transaction_cost_bps: float = 20.0
    max_position_weight: float | None = None
    adjust_type: str = "hfq"
    score_version: str = "manual_v1"
    engine_version: str = MID_TREND_V1_ENGINE_VERSION
    benchmark_variant: str = MID_TREND_V1_BENCHMARK_VARIANT


def build_mid_trend_v1_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n: int = 5,
    buffer_rank: int = 10,
    max_weekly_replacements: int = 2,
    peak_drawdown_exit: float = 0.12,
    transaction_cost_bps: float = 20.0,
    max_position_weight: float | None = None,
    adjust_type: str = "hfq",
    score_version: str = "manual_v1",
    benchmark_variant: str = MID_TREND_V1_BENCHMARK_VARIANT,
    report_start_date: str | None = None,
) -> dict[str, Any]:
    config = MidTrendV1Config(
        start_date=start_date,
        end_date=end_date,
        top_n=int(top_n),
        buffer_rank=int(max(buffer_rank, top_n)),
        max_weekly_replacements=int(max_weekly_replacements),
        peak_drawdown_exit=float(peak_drawdown_exit),
        transaction_cost_bps=float(transaction_cost_bps),
        max_position_weight=max_position_weight,
        adjust_type=adjust_type,
        score_version=score_version,
        benchmark_variant=benchmark_variant,
    )
    primary = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=config.top_n)["top10"]
    buffer = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=config.buffer_rank)["top10"]
    scoped_prices = _prices_for_shadow(prices, pd.concat([primary, buffer], ignore_index=True))
    result = _simulate_variant(
        primary,
        buffer,
        scoped_prices,
        start_date=config.start_date,
        end_date=config.end_date,
        variant_name=config.benchmark_variant,
        top_n=config.top_n,
        buffer_rank=config.buffer_rank,
        max_weekly_replacements=config.max_weekly_replacements,
        peak_drawdown_exit=config.peak_drawdown_exit,
        transaction_cost_bps=config.transaction_cost_bps,
    )
    if report_start_date and report_start_date > config.start_date:
        result = _slice_lifecycle_result(
            result,
            requested_start_date=report_start_date,
            requested_end_date=config.end_date,
            top_n=config.top_n,
            transaction_cost_bps=config.transaction_cost_bps,
        )
    summary = dict(result["summary"])
    latest_metrics = _latest_mid_trend_metrics(
        equity_curve=result["equity_curve"],
        positions=result["positions"],
    )
    summary.update(
        {
            "engine_version": config.engine_version,
            "fresh_engine_note": "Mid Trend V1 DB lifecycle recompute via weekly control benchmark engine",
            "benchmark_variant": config.benchmark_variant,
            "overlay_name": MID_TREND_V1_OVERLAY_NAME,
            "simulation_start_date": config.start_date,
            "requested_start_date": report_start_date or config.start_date,
            "max_position_weight": config.max_position_weight,
            "adjust_type": config.adjust_type,
            "score_version": config.score_version,
            **latest_metrics,
            "data_coverage": {
                "source": str(funnel_detail.attrs.get("source", "db_base_tables")),
                "funnel_detail_rows": int(len(funnel_detail)),
                "price_rows": int(len(prices)),
                "primary_signal_rows": int(len(primary)),
                "buffer_signal_rows": int(len(buffer)),
                "stale_overlay_path": str(funnel_detail.attrs.get("stale_overlay_path") or ""),
                "stale_overlay_max_date": str(funnel_detail.attrs.get("stale_overlay_max_date") or ""),
            },
        }
    )
    config_payload = asdict(config)
    if report_start_date:
        config_payload["start_date"] = report_start_date
        config_payload["simulation_start_date"] = config.start_date
    return {
        "strategy_id": "mid_trend",
        "strategy_name": "Mid Trend Combo",
        "read_only": False,
        "source_kind": MID_TREND_V1_ENGINE_VERSION,
        "config": config_payload,
        "summary": summary,
        "equity_curve": _records(result["equity_curve"]),
        "signals": _records(primary),
        "positions": _records(result["positions"]),
        "trades": _records(result["trades"]),
    }


def run_mid_trend_v1_backtest_for_dashboard(payload: dict[str, Any]) -> dict[str, Any]:
    config = MidTrendV1Config(
        start_date=str(payload["start_date"]),
        end_date=str(payload["end_date"]),
        top_n=int(payload.get("top_n") or 5),
        buffer_rank=max(10, int(payload.get("top_n") or 5)),
        transaction_cost_bps=float(payload.get("transaction_cost_bps") or 20.0),
        max_position_weight=_optional_float(payload.get("max_position_weight")),
        adjust_type=str(payload.get("adjust_type") or "hfq"),
        score_version=str(payload.get("score_version") or "manual_v1"),
        benchmark_variant=str(payload.get("benchmark_variant") or MID_TREND_V1_BENCHMARK_VARIANT),
    )
    simulation_start_date = _simulation_start_date(config)
    load_config = (
        MidTrendV1Config(**{**asdict(config), "start_date": simulation_start_date})
        if simulation_start_date != config.start_date
        else config
    )
    frames = load_mid_trend_v1_frames(load_config)
    return build_mid_trend_v1_from_frames(
        funnel_detail=frames["funnel_detail"],
        prices=frames["prices"],
        start_date=simulation_start_date,
        end_date=config.end_date,
        top_n=config.top_n,
        buffer_rank=config.buffer_rank,
        max_weekly_replacements=config.max_weekly_replacements,
        peak_drawdown_exit=config.peak_drawdown_exit,
        transaction_cost_bps=config.transaction_cost_bps,
        max_position_weight=config.max_position_weight,
        adjust_type=config.adjust_type,
        score_version=config.score_version,
        benchmark_variant=config.benchmark_variant,
        report_start_date=config.start_date,
    )


def _simulation_start_date(config: MidTrendV1Config) -> str:
    if MID_TREND_V1_FEATURE_FUNNEL_PATH.exists() and config.start_date > MID_TREND_V1_BENCHMARK_START_DATE:
        return MID_TREND_V1_BENCHMARK_START_DATE
    return config.start_date


def load_mid_trend_v1_frames(config: MidTrendV1Config, *, service: str = SETTINGS.research_service) -> dict[str, pd.DataFrame]:
    funnel_detail = load_mid_trend_v1_funnel_detail(config, service=service)
    asset_ids = _asset_ids_from_funnel(funnel_detail) or _load_candidate_asset_ids(config, service=service)
    return {
        "funnel_detail": funnel_detail,
        "prices": load_mid_trend_v1_prices(config, asset_ids=asset_ids, service=service),
    }


def load_mid_trend_v1_funnel_detail(config: MidTrendV1Config, *, service: str = SETTINGS.research_service) -> pd.DataFrame:
    if MID_TREND_V1_FEATURE_FUNNEL_PATH.exists():
        frame = pd.read_csv(MID_TREND_V1_FEATURE_FUNNEL_PATH, low_memory=False)
        frame = _prepare_feature_funnel(frame, config=config)
        overlay_max_date = _max_trade_date(frame)
        if overlay_max_date and overlay_max_date >= config.end_date:
            frame.attrs["source"] = "research_overlay_feature_input"
            return frame
        fallback = _load_mid_trend_v1_funnel_detail_from_db(config, service=service)
        fallback.attrs["stale_overlay_path"] = str(MID_TREND_V1_FEATURE_FUNNEL_PATH)
        fallback.attrs["stale_overlay_max_date"] = overlay_max_date
        return fallback
    return _load_mid_trend_v1_funnel_detail_from_db(config, service=service)


def _load_mid_trend_v1_funnel_detail_from_db(
    config: MidTrendV1Config,
    *,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
        SELECT
            s.trade_date::text AS trade_date,
            s.asset_id,
            a.ts_code,
            a.name AS stock_name,
            COALESCE(ind.industry_name, 'unknown') AS industry_name,
            s.rank AS score_rank,
            s.score_total AS mid_trend_funnel_score,
            s.score_components,
            COALESCE(t.amount_vs_20d, 1.0) AS amount_vs_20d,
            COALESCE(t.high_to_close_drawdown, 0.0) AS high_to_close_drawdown,
            COALESCE(fd_trend.factor_value, 1.0) AS trend_r2_20,
            COALESCE(fd_ret.factor_value, 0.2) AS ret_20d
        FROM factor.stock_score_daily s
        LEFT JOIN core.asset_master a ON a.asset_id = s.asset_id
        LEFT JOIN LATERAL (
            SELECT industry_name
            FROM core.industry_membership m
            WHERE m.asset_id = s.asset_id
              AND m.industry_system = 'sw'
              AND m.start_date <= s.trade_date
              AND (m.end_date IS NULL OR m.end_date >= s.trade_date)
            ORDER BY m.start_date DESC
            LIMIT 1
        ) ind ON true
        LEFT JOIN factor.stock_technical_features_daily t
          ON t.trade_date = s.trade_date
         AND t.asset_id = s.asset_id
         AND t.adjust_type = %s
        LEFT JOIN factor.factor_daily fd_trend
          ON fd_trend.trade_date = s.trade_date
         AND fd_trend.asset_id = s.asset_id
         AND fd_trend.factor_name = 'trend_r2_20'
        LEFT JOIN factor.factor_daily fd_ret
          ON fd_ret.trade_date = s.trade_date
         AND fd_ret.asset_id = s.asset_id
         AND fd_ret.factor_name = 'ret_20d'
        WHERE s.score_version = %s
          AND s.trade_date BETWEEN %s AND %s
          AND s.rank <= %s
        ORDER BY s.trade_date, s.rank, s.asset_id
    """
    rank_limit = max(int(config.buffer_rank) * 8, 50)
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [config.adjust_type, config.score_version, config.start_date, config.end_date, rank_limit])
    frame = _build_funnel_detail_from_score_rows(pd.DataFrame(rows))
    frame.attrs["source"] = "db_base_tables"
    return frame


def _prepare_feature_funnel(frame: pd.DataFrame, *, config: MidTrendV1Config) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.date.astype(str)
    result = result[result["trade_date"].between(config.start_date, config.end_date)].copy()
    result["asset_id"] = result["asset_id"].astype(str)
    result["mid_trend_funnel_score"] = _report_mild_bonus_score(result)
    if "score_rank" not in result.columns and "rank" in result.columns:
        result["score_rank"] = result["rank"]
    return result


def _max_trade_date(frame: pd.DataFrame) -> str:
    if frame.empty or "trade_date" not in frame.columns:
        return ""
    dates = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    if dates.empty:
        return ""
    return str(dates.max().date())


def _report_mild_bonus_score(frame: pd.DataFrame) -> pd.Series:
    base_score = pd.to_numeric(frame.get("mid_trend_funnel_score"), errors="coerce")
    support = pd.to_numeric(frame.get("research_support_score"), errors="coerce").fillna(0.0)
    return base_score + 0.05 * support.clip(lower=0.0, upper=60.0)


def load_mid_trend_v1_prices(
    config: MidTrendV1Config,
    *,
    asset_ids: list[str],
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["trade_date", "asset_id", "close"])
    sql = """
        SELECT trade_date::text AS trade_date, asset_id, close
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
          AND asset_id = ANY(%s)
        ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [config.adjust_type, config.start_date, config.end_date, asset_ids])
    return pd.DataFrame(rows)


def _load_candidate_asset_ids(config: MidTrendV1Config, *, service: str) -> list[str]:
    sql = """
        SELECT DISTINCT asset_id
        FROM factor.stock_score_daily
        WHERE score_version = %s
          AND trade_date BETWEEN %s AND %s
          AND rank <= %s
        ORDER BY asset_id
    """
    rank_limit = max(int(config.buffer_rank) * 8, 50)
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [config.score_version, config.start_date, config.end_date, rank_limit])
    return [str(row["asset_id"]) for row in rows if row.get("asset_id")]


def _asset_ids_from_funnel(funnel_detail: pd.DataFrame) -> list[str]:
    if funnel_detail.empty or "asset_id" not in funnel_detail.columns:
        return []
    return sorted(funnel_detail["asset_id"].dropna().astype(str).unique().tolist())


def _slice_lifecycle_result(
    result: dict[str, Any],
    *,
    requested_start_date: str,
    requested_end_date: str,
    top_n: int,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    equity = result["equity_curve"].copy()
    positions = result["positions"].copy()
    trades = result["trades"].copy()
    if not equity.empty:
        equity["date"] = pd.to_datetime(equity["date"], errors="coerce").dt.date.astype(str)
        equity = equity[equity["date"].between(requested_start_date, requested_end_date)].copy()
        if not equity.empty:
            base_equity = float(pd.to_numeric(equity.iloc[0]["equity"], errors="coerce"))
            if base_equity and pd.notna(base_equity):
                equity["equity"] = pd.to_numeric(equity["equity"], errors="coerce") / base_equity
                equity["drawdown"] = equity["equity"] / equity["equity"].cummax() - 1.0
                equity.iloc[0, equity.columns.get_loc("equity")] = 1.0
                equity.iloc[0, equity.columns.get_loc("drawdown")] = 0.0
    if not positions.empty:
        positions["rebalance_date"] = pd.to_datetime(positions["rebalance_date"], errors="coerce").dt.date.astype(str)
        positions = positions[positions["rebalance_date"].between(requested_start_date, requested_end_date)].copy()
    if not trades.empty:
        trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.date.astype(str)
        trades = trades[trades["trade_date"].between(requested_start_date, requested_end_date)].copy()
    variant_name = str(result["summary"].get("variant_name", MID_TREND_V1_BENCHMARK_VARIANT))
    return {
        **result,
        "equity_curve": equity.reset_index(drop=True),
        "positions": positions.reset_index(drop=True),
        "trades": trades.reset_index(drop=True),
        "summary": _summary_row(
            variant_name,
            equity.reset_index(drop=True),
            positions=positions.reset_index(drop=True),
            trades=trades.reset_index(drop=True),
            start_date=requested_start_date,
            end_date=requested_end_date,
            top_n=top_n,
            transaction_cost_bps=transaction_cost_bps,
        ),
    }


def _latest_mid_trend_metrics(
    *,
    equity_curve: pd.DataFrame,
    positions: pd.DataFrame,
) -> dict[str, Any]:
    if equity_curve.empty:
        return {
            "latest_day_return": None,
            "latest_day_drawdown": None,
            "latest_period_return": None,
            "latest_period_label": "最近调仓周期",
        }
    equity = equity_curve.copy()
    date_col = "date" if "date" in equity.columns else "trade_date"
    equity[date_col] = pd.to_datetime(equity[date_col], errors="coerce")
    equity = equity.dropna(subset=[date_col]).sort_values(date_col, kind="stable")
    latest = equity.iloc[-1]
    latest_equity = _safe_float(latest.get("equity"))
    latest_day_return = _safe_float(latest.get("net_return", latest.get("daily_return")))
    latest_day_drawdown = _safe_float(latest.get("drawdown"))
    latest_period_return = None
    if not positions.empty and "rebalance_date" in positions.columns and latest_equity is not None:
        position_dates = pd.to_datetime(positions["rebalance_date"], errors="coerce").dropna()
        if not position_dates.empty:
            latest_rebalance_date = position_dates.max()
            anchor_rows = equity[equity[date_col].le(latest_rebalance_date)]
            if not anchor_rows.empty:
                anchor_equity = _safe_float(anchor_rows.iloc[-1].get("equity"))
                if anchor_equity not in (None, 0.0):
                    latest_period_return = latest_equity / anchor_equity - 1.0
    return {
        "latest_day_return": latest_day_return,
        "latest_day_drawdown": latest_day_drawdown,
        "latest_period_return": latest_period_return,
        "latest_period_label": "最近调仓周期",
    }


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def _build_funnel_detail_from_score_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    frame = rows.copy()
    frame["score_components"] = frame.get("score_components", pd.Series([{}] * len(frame))).map(_parse_components)
    components = pd.DataFrame([_component_values(value) for value in frame["score_components"]], index=frame.index)
    frame = pd.concat([frame, components], axis=1)
    frame["score_rank"] = pd.to_numeric(frame.get("score_rank"), errors="coerce")
    frame["mid_trend_funnel_score"] = pd.to_numeric(frame.get("mid_trend_funnel_score"), errors="coerce")
    frame["trend_r2_20_score"] = _score_0_100(frame, ["trend_r2_20_score", "trend_r2_20"], default=90.0)
    frame["ret_20_score"] = _score_0_100(frame, ["ret_20_score", "ret_20d"], default=80.0)
    frame["volatility_20_score"] = _score_0_100(frame, ["volatility_20_score"], default=50.0)
    drawdown = pd.to_numeric(frame.get("high_to_close_drawdown"), errors="coerce").fillna(0.0).clip(0, 1)
    frame["max_drawdown_20_score"] = _score_0_100(frame, ["max_drawdown_20_score"], default=(100.0 - drawdown * 100.0))
    frame["market_regime"] = "mainline"
    frame["mainline_status"] = "sustained_mainline"
    frame["mainline_context"] = "mainline"
    frame["industry_mainline_score_v1"] = 0.65
    frame["mid_trend_layer"] = "stable_trend_watch"
    frame["structure_slot"] = "preferred_mainline_core"
    return frame


def _parse_components(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _component_values(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            for nested_key, nested_value in item.items():
                result.setdefault(str(nested_key), nested_value)
        else:
            result.setdefault(str(key), item)
    return result


def _score_0_100(frame: pd.DataFrame, columns: list[str], *, default: float | pd.Series) -> pd.Series:
    values = None
    for column in columns:
        if column not in frame.columns:
            continue
        candidate = pd.to_numeric(frame[column], errors="coerce")
        values = candidate if values is None else values.fillna(candidate)
    if values is None:
        values = default if isinstance(default, pd.Series) else pd.Series(float(default), index=frame.index)
    if not isinstance(values, pd.Series):
        values = pd.Series(values, index=frame.index)
    values = pd.to_numeric(values, errors="coerce")
    normalized = values.where(values.gt(1.5), values * 100.0)
    if isinstance(default, pd.Series):
        fallback = default
    else:
        fallback = pd.Series(float(default), index=frame.index)
    return normalized.fillna(fallback).clip(0, 100)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return frame.to_dict("records")
