from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.serenity_tight3b_c2_experiment import (
    ProtectionConfig,
    build_serenity_tight3b_c2_experiment_from_frames,
    _summary_frame,
)


TECH_BOTTLENECK_V1_ENGINE_VERSION = "tech_bottleneck_v1"
TECH_BOTTLENECK_V1_BENCHMARK_START_DATE = "2025-01-01"
TECH_BOTTLENECK_V1_PROTECTION_NAME = "rank_exit_top10_1d"
TECH_BOTTLENECK_V1_BASELINE_NAME = "strict_st_only_tight3b_rank_exit_top10"
TECH_BOTTLENECK_V1_CANDIDATES_PATH = Path(
    "/Users/xiwei/stock_research/outputs/research/"
    "serenity_bottleneck_baseline_st_only_financial_state_20250101_20260605/"
    "strict_153_st_only_financial_state_candidates.csv"
)
TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH = Path(
    "/Users/xiwei/stock_research/outputs/research/"
    "market_regime_confirmation_v1_tight3b_bt100_20230103_20260605/"
    "market_regime_confirmation_daily.csv"
)


@dataclass(frozen=True)
class TechBottleneckV1Config:
    start_date: str
    end_date: str
    top_n: int = 5
    rebalance_frequency: str = "weekly"
    transaction_cost_bps: float = 20.0
    max_position_weight: float | None = None
    adjust_type: str = "hfq"
    engine_version: str = TECH_BOTTLENECK_V1_ENGINE_VERSION


def build_tech_bottleneck_v1_from_frames(
    *,
    candidates: pd.DataFrame,
    prices: pd.DataFrame,
    market_exposure: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n: int = 5,
    rebalance_frequency: str = "weekly",
    transaction_cost_bps: float = 20.0,
    max_position_weight: float | None = None,
    adjust_type: str = "hfq",
    report_start_date: str | None = None,
) -> dict[str, Any]:
    frequency = _supported_frequency(rebalance_frequency)
    config = TechBottleneckV1Config(
        start_date=start_date,
        end_date=end_date,
        top_n=int(top_n),
        rebalance_frequency=frequency,
        transaction_cost_bps=float(transaction_cost_bps),
        max_position_weight=max_position_weight,
        adjust_type=adjust_type,
    )
    result = build_serenity_tight3b_c2_experiment_from_frames(
        candidates=candidates,
        prices=prices,
        market_exposure=market_exposure,
        start_date=config.start_date,
        end_date=config.end_date,
        universe_name="strict_153_st_only_financial_state",
        top_n_values=[config.top_n],
        rebalance_frequencies=[config.rebalance_frequency],
        protection_configs=[{"name": TECH_BOTTLENECK_V1_PROTECTION_NAME, "rank_exit": 10, "confirm_days": 1}],
        transaction_cost_bps=config.transaction_cost_bps,
        adjust_type=config.adjust_type,
    )
    run = {
        "summary": result["summary"].iloc[0].to_dict() if not result["summary"].empty else {},
        "equity": result["best_equity"],
        "positions": result["best_positions"],
        "trades": result["best_trades"],
    }
    if report_start_date and report_start_date > config.start_date:
        run = _slice_lifecycle_result(
            run,
            requested_start_date=report_start_date,
            requested_end_date=config.end_date,
            top_n=config.top_n,
            frequency=config.rebalance_frequency,
        )
    summary = _dashboard_summary(run["summary"])
    summary.update(
        {
            "engine_version": config.engine_version,
            "fresh_engine_note": "Tech Bottleneck V1 fresh recompute via accepted Serenity C2 baseline",
            "baseline_name": TECH_BOTTLENECK_V1_BASELINE_NAME,
            "simulation_start_date": config.start_date,
            "requested_start_date": report_start_date or config.start_date,
            "data_coverage": {
                "source": "accepted_baseline_feature_inputs",
                "candidate_rows": int(len(candidates)),
                "price_rows": int(len(prices)),
                "market_exposure_rows": int(len(market_exposure)),
            },
        }
    )
    config_payload = asdict(config)
    if report_start_date:
        config_payload["start_date"] = report_start_date
        config_payload["simulation_start_date"] = config.start_date
    return {
        "strategy_id": "tech_bottleneck",
        "strategy_name": "Tech Bottleneck Discovery",
        "read_only": False,
        "source_kind": TECH_BOTTLENECK_V1_ENGINE_VERSION,
        "config": config_payload,
        "summary": summary,
        "equity_curve": _records(run["equity"]),
        "positions": _records(run["positions"]),
        "trades": _records(run["trades"]),
    }


def run_tech_bottleneck_v1_backtest_for_dashboard(payload: dict[str, Any]) -> dict[str, Any]:
    requested_start_date = str(payload["start_date"])
    config = TechBottleneckV1Config(
        start_date=_simulation_start_date(requested_start_date),
        end_date=str(payload["end_date"]),
        top_n=int(payload.get("top_n") or 5),
        rebalance_frequency=_supported_frequency(str(payload.get("rebalance_frequency") or "weekly")),
        transaction_cost_bps=float(payload.get("transaction_cost_bps") or 20.0),
        max_position_weight=_optional_float(payload.get("max_position_weight")),
        adjust_type=str(payload.get("adjust_type") or "hfq"),
    )
    frames = load_tech_bottleneck_v1_frames(config)
    return build_tech_bottleneck_v1_from_frames(
        candidates=frames["candidates"],
        prices=frames["prices"],
        market_exposure=frames["market_exposure"],
        start_date=config.start_date,
        end_date=config.end_date,
        top_n=config.top_n,
        rebalance_frequency=config.rebalance_frequency,
        transaction_cost_bps=config.transaction_cost_bps,
        max_position_weight=config.max_position_weight,
        adjust_type=config.adjust_type,
        report_start_date=requested_start_date,
    )


def load_tech_bottleneck_v1_frames(
    config: TechBottleneckV1Config,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, pd.DataFrame]:
    candidates = pd.read_csv(TECH_BOTTLENECK_V1_CANDIDATES_PATH, low_memory=False)
    market_exposure = pd.read_csv(TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH, low_memory=False)
    market_exposure = _extend_market_exposure(market_exposure, end_date=config.end_date)
    asset_ids = sorted(candidates["asset_id"].dropna().astype(str).unique().tolist())
    return {
        "candidates": candidates,
        "market_exposure": market_exposure,
        "prices": _load_prices(
            start_date=config.start_date,
            end_date=config.end_date,
            adjust_type=config.adjust_type,
            asset_ids=asset_ids,
            service=service,
        ),
    }


def _simulation_start_date(requested_start_date: str) -> str:
    if requested_start_date > TECH_BOTTLENECK_V1_BENCHMARK_START_DATE:
        return TECH_BOTTLENECK_V1_BENCHMARK_START_DATE
    return requested_start_date


def _slice_lifecycle_result(
    run: dict[str, Any],
    *,
    requested_start_date: str,
    requested_end_date: str,
    top_n: int,
    frequency: str,
) -> dict[str, Any]:
    equity = run["equity"].copy()
    positions = run["positions"].copy()
    trades = run["trades"].copy()
    if not equity.empty:
        equity["trade_date"] = pd.to_datetime(equity["trade_date"], errors="coerce").dt.date.astype(str)
        equity = equity[equity["trade_date"].between(requested_start_date, requested_end_date)].copy()
        if not equity.empty:
            base_equity = float(pd.to_numeric(equity.iloc[0]["equity"], errors="coerce"))
            if base_equity and pd.notna(base_equity):
                equity["equity"] = pd.to_numeric(equity["equity"], errors="coerce") / base_equity
                equity["drawdown"] = equity["equity"] / equity["equity"].cummax() - 1.0
                equity.iloc[0, equity.columns.get_loc("equity")] = 1.0
                equity.iloc[0, equity.columns.get_loc("drawdown")] = 0.0
    if not positions.empty:
        positions["trade_date"] = pd.to_datetime(positions["trade_date"], errors="coerce").dt.date.astype(str)
        positions = positions[positions["trade_date"].between(requested_start_date, requested_end_date)].copy()
    if not trades.empty:
        trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.date.astype(str)
        trades = trades[trades["trade_date"].between(requested_start_date, requested_end_date)].copy()
    protection = ProtectionConfig(name=TECH_BOTTLENECK_V1_PROTECTION_NAME, rank_exit=10, confirm_days=1)
    summary = _summary_frame(
        universe_name=str(run["summary"].get("universe", "strict_153_st_only_financial_state")),
        frequency=frequency,
        top_n=top_n,
        protection=protection,
        start_date=requested_start_date,
        end_date=requested_end_date,
        equity=equity.reset_index(drop=True),
        positions=positions.reset_index(drop=True),
        trades=trades.reset_index(drop=True),
    ).iloc[0].to_dict()
    return {
        "summary": summary,
        "equity": equity.reset_index(drop=True),
        "positions": positions.reset_index(drop=True),
        "trades": trades.reset_index(drop=True),
    }


def _dashboard_summary(summary: dict[str, Any]) -> dict[str, Any]:
    result = dict(summary)
    total_return = result.get("total_return")
    if total_return is not None:
        result["final_equity"] = float(total_return) + 1.0
    if "sharpe" in result and "sharpe_ratio" not in result:
        result["sharpe_ratio"] = result["sharpe"]
    if "days" in result and "periods" not in result:
        result["periods"] = result["days"]
    return result


def _extend_market_exposure(market_exposure: pd.DataFrame, *, end_date: str) -> pd.DataFrame:
    if market_exposure.empty:
        return market_exposure
    frame = market_exposure.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    last = frame.dropna(subset=["trade_date"]).sort_values("trade_date").tail(1)
    if last.empty or str(last.iloc[0]["trade_date"]) >= end_date:
        return frame
    appended = last.copy()
    appended["trade_date"] = end_date
    return pd.concat([frame, appended], ignore_index=True)


def _supported_frequency(value: str) -> str:
    frequency = str(value or "weekly").strip()
    if frequency == "daily":
        return "weekly"
    if frequency not in {"weekly", "biweekly", "monthly"}:
        return "weekly"
    return frequency


def _load_prices(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str,
    asset_ids: list[str],
    service: str,
) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["trade_date", "asset_id", "open", "high", "low", "close"])
    sql = """
        SELECT trade_date::text AS trade_date, asset_id, open, high, low, close
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
          AND asset_id = ANY(%s)
        ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date, asset_ids])
    return pd.DataFrame(rows)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return frame.to_dict("records")
