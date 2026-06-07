from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import fetch_all
from stock_research.mid_trend_shadow_backtest import _load_prices
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame, _hard_eligible_mid_trend_mask
from stock_research.mid_trend_shadow_weekly_optimization import _prices_for_shadow


VARIANTS = [
    "baseline_top5_weekly",
    "top5_weekly_hold_buffer_top10",
    "top5_weekly_max_2_replacements",
    "top5_weekly_trend_holding_protection_v1",
    "top5_weekly_max2_trend_holding_protection_v1",
    "top5_weekly_max2_selective_trend_holding_protection_v1",
    "top5_weekly_max2_selective_quality_sorted_protection_v1",
    "top5_weekly_max2_quality_sorted_stale_v1",
    "top5_weekly_max2_quality_sorted_risk_override_v1",
    "top5_weekly_max2_no_state_stale_repair_v1",
    "top5_weekly_max2_drawdown_throttle_v1",
    "top5_weekly_max2_rank_weight_mild_v1",
    "top5_weekly_max2_rank_weight_aggressive_v1",
    "top5_adaptive_daily_check_max2_v1",
    "top5_adaptive_daily_check_rank_weight_mild_v1",
    "top5_adaptive_hold_strong_stale_v1",
    "top5_adaptive_regime_gated_max2_v1",
    "top5_adaptive_quality_gate_v1",
    "top5_weekly_ma20_exit",
    "top5_weekly_peak_drawdown_12_exit",
    "top5_weekly_market_regime_throttle",
]
WEAK_REGIMES = {"retreat", "weak"}


def run_mid_trend_shadow_weekly_control_review(
    *,
    funnel_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    top_n: int = 5,
    buffer_rank: int = 10,
    max_weekly_replacements: int = 2,
    peak_drawdown_exit: float = 0.12,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    funnel_detail = _attach_st_status_flags(
        funnel_detail,
        start_date=start_date,
        end_date=end_date,
        service=service,
    )
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    return build_mid_trend_shadow_weekly_control_review_from_frames(
        funnel_detail=funnel_detail,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        peak_drawdown_exit=peak_drawdown_exit,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
    )


def build_mid_trend_shadow_weekly_control_review_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    top_n: int = 5,
    buffer_rank: int = 10,
    max_weekly_replacements: int = 2,
    peak_drawdown_exit: float = 0.12,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    hard_exclusions = _hard_exclusions_by_date(funnel_detail)
    primary_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=top_n)["top10"]
    buffer_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=max(top_n, buffer_rank))["top10"]
    scoped_prices = _prices_for_shadow(prices, pd.concat([primary_signals, buffer_signals], ignore_index=True))
    results = [
        _simulate_variant(
            primary_signals,
            buffer_signals,
            scoped_prices,
            start_date=start_date,
            end_date=end_date,
            variant_name=variant_name,
            top_n=top_n,
            buffer_rank=buffer_rank,
            max_weekly_replacements=max_weekly_replacements,
            peak_drawdown_exit=peak_drawdown_exit,
            transaction_cost_bps=transaction_cost_bps,
            hard_exclusions=hard_exclusions,
        )
        for variant_name in VARIANTS
    ]
    equity_curve = pd.concat([item["equity_curve"] for item in results], ignore_index=True)
    positions = pd.concat([item["positions"] for item in results], ignore_index=True)
    trades = pd.concat([item["trades"] for item in results], ignore_index=True)
    summary = pd.DataFrame([item["summary"] for item in results])
    report = _render_report(summary)

    result: dict[str, Any] = {
        "summary": summary,
        "equity_curve": equity_curve,
        "positions": positions,
        "trades": trades,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": output / "mid_trend_shadow_weekly_control_summary.csv",
            "equity_curve": output / "mid_trend_shadow_weekly_control_equity.csv",
            "positions": output / "mid_trend_shadow_weekly_control_positions.csv",
            "trades": output / "mid_trend_shadow_weekly_control_trades.csv",
            "report": output / "mid_trend_shadow_weekly_control_report.md",
        }
        summary.to_csv(paths["summary"], index=False)
        equity_curve.to_csv(paths["equity_curve"], index=False)
        positions.to_csv(paths["positions"], index=False)
        trades.to_csv(paths["trades"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _simulate_variant(
    primary_signals: pd.DataFrame,
    buffer_signals: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    variant_name: str,
    top_n: int,
    buffer_rank: int,
    max_weekly_replacements: int,
    peak_drawdown_exit: float,
    transaction_cost_bps: float,
    protection_score_gap: float = 10.0,
    protection_mainline_gap: float = 0.10,
    protection_trend_r2_min: float = 80.0,
    protection_ret20_min: float = 70.0,
    protection_mainline_min: float = 0.45,
    protection_drawdown_min: float = 55.0,
    drawdown_throttle_threshold: float = -0.08,
    drawdown_throttle_invested_weight: float = 0.6,
    drawdown_throttle_max_replacements: int = 1,
    hard_exclusions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    signals = _normalize_signals(primary_signals, start_date, end_date)
    buffer = _normalize_signals(buffer_signals, start_date, end_date)
    hard_exclusions_by_date = _normalize_hard_exclusions(hard_exclusions, start_date, end_date)
    close = _close_matrix(prices, start_date, end_date)
    if close.empty:
        return _empty_variant_result(variant_name, start_date, end_date)

    ma20 = close.rolling(20, min_periods=20).mean()
    weekly_dates = set(_weekly_signal_dates(signals, list(close.index)))
    signal_dates = set(signals["trade_date"].astype(str)) if not signals.empty else set()
    current_weights: dict[str, float] = {}
    peak_close: dict[str, float] = {}
    equity = 1.0
    high_water = 1.0
    equity_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    cost_rate = float(transaction_cost_bps) / 10000.0
    active_week_key: tuple[int, int] | None = None
    adaptive_replacements_used = 0

    for index, trade_date in enumerate(close.index):
        iso = pd.Timestamp(trade_date).isocalendar()
        week_key = (int(iso.year), int(iso.week))
        if week_key != active_week_key:
            active_week_key = week_key
            adaptive_replacements_used = 0

        if index > 0 and current_weights:
            prev_date = close.index[index - 1]
            returns = close.loc[trade_date] / close.loc[prev_date] - 1.0
            gross_return = float(sum(current_weights.get(asset, 0.0) * returns.get(asset, 0.0) for asset in current_weights))
            equity *= 1.0 + gross_return
        else:
            gross_return = 0.0

        turnover = 0.0
        hard_exits = _hard_excluded_assets_for_date(
            hard_exclusions_by_date,
            trade_date=trade_date,
            current_assets=current_weights.keys(),
        )
        if hard_exits:
            target = {asset: weight for asset, weight in current_weights.items() if asset not in hard_exits}
            turnover += _rebalance_turnover(current_weights, target)
            trade_rows.extend(_trade_rows(variant_name, trade_date, current_weights, target, "hard_exclusion_exit", cost_rate))
            current_weights = target

        exits = _exit_assets(
            variant_name=variant_name,
            trade_date=trade_date,
            current_weights=current_weights,
            close=close,
            ma20=ma20,
            peak_close=peak_close,
            peak_drawdown_exit=peak_drawdown_exit,
        )
        if exits:
            target = {asset: weight for asset, weight in current_weights.items() if asset not in exits}
            turnover += _rebalance_turnover(current_weights, target)
            trade_rows.extend(_trade_rows(variant_name, trade_date, current_weights, target, "risk_exit", cost_rate))
            current_weights = target

        throttle_triggered = False
        rebalance_due = trade_date in weekly_dates
        if _is_adaptive_variant(variant_name):
            adaptive_due = (
                trade_date in signal_dates
                and (not current_weights or adaptive_replacements_used < int(max_weekly_replacements))
                and _adaptive_rebalance_due(
                    signals,
                    buffer,
                    trade_date=trade_date,
                    current_assets=list(current_weights),
                    top_n=top_n,
                    buffer_rank=buffer_rank,
                )
            )
            if variant_name == "top5_adaptive_regime_gated_max2_v1" and current_weights:
                daily_allowed = _adaptive_regime_allows_daily_check(signals, trade_date=trade_date)
                rebalance_due = (trade_date in weekly_dates) or (adaptive_due and daily_allowed)
            else:
                rebalance_due = adaptive_due
        if rebalance_due:
            target_variant_name = _target_variant_name(variant_name)
            effective_max_weekly_replacements = max_weekly_replacements
            drawdown_before_rebalance = equity / high_water - 1.0 if high_water else 0.0
            forced_invested_weight: float | None = None
            if (
                variant_name == "top5_weekly_max2_drawdown_throttle_v1"
                and drawdown_before_rebalance <= float(drawdown_throttle_threshold)
            ):
                effective_max_weekly_replacements = int(drawdown_throttle_max_replacements)
                forced_invested_weight = float(drawdown_throttle_invested_weight)
                throttle_triggered = True
            max_replacements_for_rebalance = effective_max_weekly_replacements
            if _is_adaptive_variant(variant_name) and current_weights:
                max_replacements_for_rebalance = max(
                    0,
                    int(max_weekly_replacements) - int(adaptive_replacements_used),
                )
            target_assets, invested_weight = _target_assets_for_variant(
                signals,
                buffer_signals=buffer,
                trade_date=trade_date,
                variant_name=target_variant_name,
                current_assets=list(current_weights),
                top_n=top_n,
                buffer_rank=buffer_rank,
                max_weekly_replacements=max_replacements_for_rebalance,
                protection_score_gap=protection_score_gap,
                protection_mainline_gap=protection_mainline_gap,
                protection_trend_r2_min=protection_trend_r2_min,
                protection_ret20_min=protection_ret20_min,
                protection_mainline_min=protection_mainline_min,
                protection_drawdown_min=protection_drawdown_min,
            )
            if forced_invested_weight is not None:
                invested_weight = forced_invested_weight
            target = _weights_for_variant(variant_name, target_assets, invested_weight=invested_weight)
            if _is_adaptive_variant(variant_name) and current_weights:
                adaptive_replacements_used += len(set(current_weights) - set(target))
            turnover += _rebalance_turnover(current_weights, target)
            trade_reason = "adaptive_rebalance" if _is_adaptive_variant(variant_name) else "weekly_rebalance"
            trade_rows.extend(_trade_rows(variant_name, trade_date, current_weights, target, trade_reason, cost_rate))
            current_weights = target
            position_rows.extend(
                {
                    "variant_name": variant_name,
                    "rebalance_date": trade_date,
                    "asset_id": asset,
                    "weight": weight,
                }
                for asset, weight in current_weights.items()
            )

        if current_weights:
            current_close = close.loc[trade_date]
            for asset in current_weights:
                value = current_close.get(asset)
                if pd.notna(value):
                    peak_close[asset] = max(float(value), float(peak_close.get(asset, value)))

        transaction_cost = turnover * cost_rate
        equity *= 1.0 - transaction_cost
        high_water = max(high_water, equity)
        equity_rows.append(
            {
                "variant_name": variant_name,
                "date": trade_date,
                "gross_return": gross_return,
                "turnover": turnover,
                "transaction_cost": transaction_cost,
                "net_return": gross_return - transaction_cost,
                "equity": equity,
                "drawdown": equity / high_water - 1.0 if high_water else 0.0,
                "holdings_count": len(current_weights),
                "invested_weight": float(sum(current_weights.values())) if current_weights else 0.0,
                "drawdown_throttle_triggered": throttle_triggered if rebalance_due else False,
            }
        )

    equity_curve = pd.DataFrame(equity_rows)
    positions = pd.DataFrame(position_rows)
    trades = pd.DataFrame(trade_rows)
    return {
        "equity_curve": equity_curve,
        "positions": positions,
        "trades": trades,
        "summary": _summary_row(
            variant_name,
            equity_curve,
            positions=positions,
            trades=trades,
            start_date=start_date,
            end_date=end_date,
            top_n=top_n,
            transaction_cost_bps=transaction_cost_bps,
        ),
    }


def _normalize_signals(frame: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "shadow_top10_rank", "market_regime"])
    signals = frame.copy()
    signals["trade_date"] = pd.to_datetime(signals["trade_date"], errors="coerce").dt.date.astype(str)
    signals["asset_id"] = signals["asset_id"].astype(str)
    signals["shadow_top10_rank"] = pd.to_numeric(signals["shadow_top10_rank"], errors="coerce")
    if "market_regime" not in signals.columns:
        signals["market_regime"] = "unknown"
    mask = signals["trade_date"].between(start_date, end_date)
    return signals[mask].dropna(subset=["trade_date", "asset_id", "shadow_top10_rank"]).copy()


def _attach_st_status_flags(
    funnel_detail: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    service: str,
) -> pd.DataFrame:
    if funnel_detail.empty:
        return funnel_detail
    try:
        asset_ids = sorted(funnel_detail["asset_id"].dropna().astype(str).unique().tolist())
        from stock_research.db import connect

        with connect(service) as conn:
            rows = fetch_all(
                conn,
                """
                SELECT trade_date::text AS trade_date, asset_id, is_st
                FROM core.asset_status_daily
                WHERE trade_date BETWEEN %s AND %s
                  AND asset_id = ANY(%s)
                """,
                [start_date, end_date, asset_ids],
            )
    except Exception:
        return funnel_detail
    if not rows:
        return funnel_detail
    status = pd.DataFrame(rows)
    frame = funnel_detail.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    status["trade_date"] = pd.to_datetime(status["trade_date"], errors="coerce").dt.date.astype(str)
    status["asset_id"] = status["asset_id"].astype(str)
    merged = frame.merge(status, on=["trade_date", "asset_id"], how="left", suffixes=("", "_status"))
    if "is_st_status" in merged.columns:
        if "is_st" in merged.columns:
            merged["is_st"] = merged["is_st"].fillna(merged["is_st_status"])
        else:
            merged["is_st"] = merged["is_st_status"]
        merged = merged.drop(columns=["is_st_status"])
    return merged


def _hard_exclusions_by_date(funnel_detail: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_date", "asset_id"]
    if funnel_detail.empty:
        return pd.DataFrame(columns=columns)
    frame = funnel_detail.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    excluded = frame[~_hard_eligible_mid_trend_mask(frame)].copy()
    return excluded[columns].dropna().drop_duplicates().reset_index(drop=True)


def _normalize_hard_exclusions(
    hard_exclusions: pd.DataFrame | None,
    start_date: str,
    end_date: str,
) -> dict[str, set[str]]:
    if hard_exclusions is None or hard_exclusions.empty:
        return {}
    frame = hard_exclusions.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame = frame[frame["trade_date"].between(start_date, end_date)].dropna(subset=["trade_date", "asset_id"])
    return {
        str(trade_date): set(group["asset_id"].astype(str))
        for trade_date, group in frame.groupby("trade_date", sort=False)
    }


def _hard_excluded_assets_for_date(
    hard_exclusions_by_date: dict[str, set[str]],
    *,
    trade_date: str,
    current_assets: Any,
) -> set[str]:
    excluded = hard_exclusions_by_date.get(str(trade_date), set())
    if not excluded:
        return set()
    return set(current_assets) & excluded


def _close_matrix(prices: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    frame = prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame[frame["trade_date"].between(start_date, end_date)].dropna(subset=["trade_date", "asset_id", "close"])
    return frame.pivot_table(index="trade_date", columns="asset_id", values="close", aggfunc="last").sort_index()


def _weekly_signal_dates(signals: pd.DataFrame, trading_dates: list[str]) -> list[str]:
    if signals.empty:
        return []
    signal_dates = set(signals["trade_date"].astype(str))
    available = [trade_date for trade_date in trading_dates if trade_date in signal_dates]
    weekly: list[str] = []
    seen_weeks: set[tuple[int, int]] = set()
    for trade_date in available:
        iso = pd.Timestamp(trade_date).isocalendar()
        key = (int(iso.year), int(iso.week))
        if key not in seen_weeks:
            weekly.append(trade_date)
            seen_weeks.add(key)
    return weekly


def _target_assets_for_variant(
    signals: pd.DataFrame,
    *,
    buffer_signals: pd.DataFrame,
    trade_date: str,
    variant_name: str,
    current_assets: list[str],
    top_n: int,
    buffer_rank: int,
    max_weekly_replacements: int,
    protection_score_gap: float = 10.0,
    protection_mainline_gap: float = 0.10,
    protection_trend_r2_min: float = 80.0,
    protection_ret20_min: float = 70.0,
    protection_mainline_min: float = 0.45,
    protection_drawdown_min: float = 55.0,
) -> tuple[list[str], float]:
    day = signals[signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
    ordered = day["asset_id"].astype(str).tolist()
    top_assets = ordered[:top_n]
    if variant_name == "top5_weekly_market_regime_throttle" and _regime_for_day(day) in WEAK_REGIMES:
        return top_assets[: max(1, top_n - 2)], min(1.0, max(1, top_n - 2) / top_n)
    if variant_name == "top5_weekly_hold_buffer_top10":
        buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
        buffer_ordered = buffer_day["asset_id"].astype(str).tolist()
        buffer_assets = set(buffer_ordered[:buffer_rank])
        kept = [asset for asset in current_assets if asset in buffer_assets]
        return _fill_to_top_n(kept, ordered + buffer_ordered, top_n), 1.0
    if variant_name == "top5_weekly_trend_holding_protection_v1":
        buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
        strong_holdings = _strong_pullback_holdings(
            buffer_day,
            current_assets,
            desired=set(top_assets),
            trend_r2_min=protection_trend_r2_min,
            ret20_min=protection_ret20_min,
            mainline_min=protection_mainline_min,
            drawdown_min=protection_drawdown_min,
        )
        return _fill_to_top_n(strong_holdings, ordered + buffer_day["asset_id"].astype(str).tolist(), top_n), 1.0
    if variant_name == "top5_weekly_max2_trend_holding_protection_v1" and current_assets:
        buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
        desired = set(top_assets)
        keep = [asset for asset in current_assets if asset in desired]
        stale = [asset for asset in current_assets if asset not in desired]
        protected = _strong_pullback_holdings(
            buffer_day,
            current_assets,
            desired=desired,
            trend_r2_min=protection_trend_r2_min,
            ret20_min=protection_ret20_min,
            mainline_min=protection_mainline_min,
            drawdown_min=protection_drawdown_min,
        )
        unprotected_stale = [asset for asset in stale if asset not in set(protected)]
        stale_to_keep_count = max(0, len(stale) - int(max_weekly_replacements))
        stale_keep = _fill_to_top_n(protected, unprotected_stale, stale_to_keep_count)
        return _fill_to_top_n(keep + stale_keep, ordered, top_n), 1.0
    if variant_name == "top5_adaptive_hold_strong_stale_v1" and current_assets:
        buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
        desired = set(top_assets)
        keep = [asset for asset in current_assets if asset in desired]
        stale = [asset for asset in current_assets if asset not in desired]
        protected = _strong_pullback_holdings(
            buffer_day,
            current_assets,
            desired=desired,
            trend_r2_min=protection_trend_r2_min,
            ret20_min=protection_ret20_min,
            mainline_min=protection_mainline_min,
            drawdown_min=protection_drawdown_min,
        )
        unprotected_stale = [asset for asset in stale if asset not in set(protected)]
        stale_to_keep_count = max(len(protected), max(0, len(stale) - int(max_weekly_replacements)))
        stale_keep = _fill_to_top_n(protected, unprotected_stale, stale_to_keep_count)
        return _fill_to_top_n(keep + stale_keep, ordered, top_n), 1.0
    if variant_name == "top5_adaptive_quality_gate_v1" and current_assets:
        day = _apply_adaptive_quality_gate(day, current_assets=current_assets)
        ordered = day["asset_id"].astype(str).tolist()
        top_assets = ordered[:top_n]
        desired = set(top_assets)
        keep = [asset for asset in current_assets if asset in desired]
        stale = [asset for asset in current_assets if asset not in desired]
        allowed_keep_stale = stale[max_weekly_replacements:]
        return _fill_to_top_n(keep + allowed_keep_stale, ordered, top_n), 1.0
    if variant_name == "top5_weekly_max2_selective_trend_holding_protection_v1" and current_assets:
        buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
        desired = set(top_assets)
        keep = [asset for asset in current_assets if asset in desired]
        stale = [asset for asset in current_assets if asset not in desired]
        protected = _selective_strong_pullback_holdings(
            buffer_day,
            day,
            current_assets,
            desired=desired,
            score_gap_min=protection_score_gap,
            mainline_gap_min=protection_mainline_gap,
            trend_r2_min=protection_trend_r2_min,
            ret20_min=protection_ret20_min,
            mainline_min=protection_mainline_min,
            drawdown_min=protection_drawdown_min,
        )
        stale_to_keep_count = max(0, len(stale) - int(max_weekly_replacements))
        baseline_stale_keep = stale[int(max_weekly_replacements) :]
        stale_keep = _fill_to_top_n(protected, baseline_stale_keep + stale, stale_to_keep_count)
        return _fill_to_top_n(keep + stale_keep, ordered, top_n), 1.0
    if variant_name == "top5_weekly_max2_selective_quality_sorted_protection_v1" and current_assets:
        buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
        desired = set(top_assets)
        keep = [asset for asset in current_assets if asset in desired]
        stale = [asset for asset in current_assets if asset not in desired]
        protected = _selective_strong_pullback_holdings(
            buffer_day,
            day,
            current_assets,
            desired=desired,
            score_gap_min=protection_score_gap,
            mainline_gap_min=protection_mainline_gap,
            trend_r2_min=protection_trend_r2_min,
            ret20_min=protection_ret20_min,
            mainline_min=protection_mainline_min,
            drawdown_min=protection_drawdown_min,
        )
        stale_to_keep_count = max(0, len(stale) - int(max_weekly_replacements))
        quality_fill = [asset for asset in _quality_sorted_stale(buffer_day, stale, buffer_rank=buffer_rank) if asset not in set(protected)]
        stale_keep = _fill_to_top_n(protected, quality_fill, stale_to_keep_count)
        return _fill_to_top_n(keep + stale_keep, ordered, top_n), 1.0
    if variant_name == "top5_weekly_max2_quality_sorted_stale_v1" and current_assets:
        buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
        desired = set(top_assets)
        keep = [asset for asset in current_assets if asset in desired]
        stale = [asset for asset in current_assets if asset not in desired]
        stale_to_keep_count = max(0, len(stale) - int(max_weekly_replacements))
        stale_keep = _quality_sorted_stale(buffer_day, stale, buffer_rank=buffer_rank)[:stale_to_keep_count]
        return _fill_to_top_n(keep + stale_keep, ordered, top_n), 1.0
    if variant_name == "top5_weekly_max2_quality_sorted_risk_override_v1" and current_assets:
        buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
        desired = set(top_assets)
        keep = [asset for asset in current_assets if asset in desired]
        stale = [asset for asset in current_assets if asset not in desired]
        broken = set(_broken_stale_assets(buffer_day, stale, buffer_rank=buffer_rank))
        replacement_limit = int(max_weekly_replacements)
        if len(broken) >= 3:
            replacement_limit = max(replacement_limit, len(broken))
        stale_to_keep_count = max(0, len(stale) - replacement_limit)
        sorted_stale = [asset for asset in _quality_sorted_stale(buffer_day, stale, buffer_rank=buffer_rank) if asset not in broken]
        stale_keep = sorted_stale[:stale_to_keep_count]
        return _fill_to_top_n(keep + stale_keep, ordered, top_n), 1.0
    if variant_name == "top5_weekly_max2_no_state_stale_repair_v1" and current_assets:
        buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
        desired = set(top_assets)
        keep = [asset for asset in current_assets if asset in desired]
        stale = [asset for asset in current_assets if asset not in desired]
        stale_to_keep_count = max(0, len(stale) - int(max_weekly_replacements))
        baseline_keep = stale[int(max_weekly_replacements) :]
        stale_keep = _repair_no_state_stale_keep(
            buffer_day,
            stale,
            baseline_keep,
            keep_count=stale_to_keep_count,
            buffer_rank=buffer_rank,
        )
        return _fill_to_top_n(keep + stale_keep, ordered, top_n), 1.0
    if _is_max_replacement_variant(variant_name) and current_assets:
        desired = set(top_assets)
        keep = [asset for asset in current_assets if asset in desired]
        stale = [asset for asset in current_assets if asset not in desired]
        allowed_keep_stale = stale[max_weekly_replacements:]
        return _fill_to_top_n(keep + allowed_keep_stale, ordered, top_n), 1.0
    return top_assets, 1.0


def _strong_pullback_holdings(
    buffer_day: pd.DataFrame,
    current_assets: list[str],
    *,
    desired: set[str],
    trend_r2_min: float = 80.0,
    ret20_min: float = 70.0,
    mainline_min: float = 0.45,
    drawdown_min: float = 55.0,
) -> list[str]:
    if buffer_day.empty or not current_assets:
        return []
    frame = buffer_day.copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame = frame[frame["asset_id"].isin(set(current_assets) - desired)]
    if frame.empty:
        return []
    for column in [
        "trend_r2_20_score",
        "ret_20_score",
        "industry_mainline_score_v1",
        "max_drawdown_20_score",
    ]:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    mask = (
        frame["trend_r2_20_score"].ge(float(trend_r2_min))
        & frame["ret_20_score"].ge(float(ret20_min))
        & frame["industry_mainline_score_v1"].ge(float(mainline_min))
        & frame["max_drawdown_20_score"].ge(float(drawdown_min))
    )
    protected = frame[mask].sort_values("shadow_top10_rank")["asset_id"].astype(str).tolist()
    return [asset for asset in current_assets if asset in set(protected)]


def _selective_strong_pullback_holdings(
    buffer_day: pd.DataFrame,
    primary_day: pd.DataFrame,
    current_assets: list[str],
    *,
    desired: set[str],
    score_gap_min: float = 10.0,
    mainline_gap_min: float = 0.10,
    trend_r2_min: float = 80.0,
    ret20_min: float = 70.0,
    mainline_min: float = 0.45,
    drawdown_min: float = 55.0,
) -> list[str]:
    protected = _strong_pullback_holdings(
        buffer_day,
        current_assets,
        desired=desired,
        trend_r2_min=trend_r2_min,
        ret20_min=ret20_min,
        mainline_min=mainline_min,
        drawdown_min=drawdown_min,
    )
    if not protected:
        return []
    replacement_pool = primary_day[~primary_day["asset_id"].astype(str).isin(set(current_assets))].copy()
    if replacement_pool.empty:
        return protected
    for column in ["mid_trend_funnel_score", "industry_mainline_score_v1"]:
        replacement_pool[column] = pd.to_numeric(replacement_pool.get(column), errors="coerce")
    best_new_score = pd.to_numeric(replacement_pool["mid_trend_funnel_score"], errors="coerce").max()
    best_new_mainline = pd.to_numeric(replacement_pool["industry_mainline_score_v1"], errors="coerce").max()
    if pd.isna(best_new_score) and pd.isna(best_new_mainline):
        return protected

    frame = buffer_day.copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame = frame[frame["asset_id"].isin(protected)]
    frame["mid_trend_funnel_score"] = pd.to_numeric(frame.get("mid_trend_funnel_score"), errors="coerce")
    frame["industry_mainline_score_v1"] = pd.to_numeric(frame.get("industry_mainline_score_v1"), errors="coerce")
    selective: list[str] = []
    for asset in protected:
        row = frame[frame["asset_id"].eq(asset)]
        if row.empty:
            selective.append(asset)
            continue
        old_score = row.iloc[0].get("mid_trend_funnel_score")
        old_mainline = row.iloc[0].get("industry_mainline_score_v1")
        score_gap = float(best_new_score - old_score) if pd.notna(best_new_score) and pd.notna(old_score) else 0.0
        mainline_gap = (
            float(best_new_mainline - old_mainline)
            if pd.notna(best_new_mainline) and pd.notna(old_mainline)
            else 0.0
        )
        if score_gap >= float(score_gap_min) and mainline_gap >= float(mainline_gap_min):
            continue
        selective.append(asset)
    return selective


def _quality_sorted_stale(buffer_day: pd.DataFrame, stale: list[str], *, buffer_rank: int) -> list[str]:
    if not stale:
        return []
    frame = _stale_quality_frame(buffer_day, stale, buffer_rank=buffer_rank)
    frame = frame.sort_values(["quality_score", "original_order"], ascending=[False, True])
    return frame["asset_id"].astype(str).tolist()


def _repair_no_state_stale_keep(
    buffer_day: pd.DataFrame,
    stale: list[str],
    baseline_keep: list[str],
    *,
    keep_count: int,
    buffer_rank: int,
) -> list[str]:
    if keep_count <= 0 or not baseline_keep:
        return []
    frame = _stale_quality_frame(buffer_day, stale, buffer_rank=buffer_rank)
    has_state = set(frame[frame["has_current_state"]]["asset_id"].astype(str))
    repaired = [asset for asset in baseline_keep if asset in has_state]
    if len(repaired) >= keep_count:
        return repaired[:keep_count]
    candidates = [
        asset
        for asset in _quality_sorted_stale(buffer_day, stale, buffer_rank=buffer_rank)
        if asset in has_state and asset not in set(repaired)
    ]
    repaired = _fill_to_top_n(repaired, candidates, keep_count)
    if len(repaired) < keep_count:
        repaired = _fill_to_top_n(repaired, baseline_keep, keep_count)
    return repaired


def _broken_stale_assets(buffer_day: pd.DataFrame, stale: list[str], *, buffer_rank: int) -> list[str]:
    if not stale:
        return []
    frame = _stale_quality_frame(buffer_day, stale, buffer_rank=buffer_rank)
    known = frame["has_current_state"]
    broken = known & (
        frame["trend_r2_20_score"].lt(70)
        | frame["ret_20_score"].lt(60)
        | frame["max_drawdown_20_score"].lt(45)
        | frame["industry_mainline_score_v1"].lt(0.35)
        | (frame["shadow_top10_rank"].gt(buffer_rank) & frame["quality_score"].lt(70))
    )
    return frame[broken]["asset_id"].astype(str).tolist()


def _stale_quality_frame(buffer_day: pd.DataFrame, stale: list[str], *, buffer_rank: int) -> pd.DataFrame:
    source = pd.DataFrame(columns=["asset_id"]) if buffer_day.empty else buffer_day.copy()
    if not source.empty:
        source["asset_id"] = source["asset_id"].astype(str)
        source = source[source["asset_id"].isin(stale)].copy()
    rows = []
    for order, asset in enumerate(stale):
        match = source[source["asset_id"].eq(asset)]
        if match.empty:
            rows.append(
                {
                    "asset_id": asset,
                    "original_order": order,
                    "has_current_state": False,
                    "shadow_top10_rank": np.nan,
                    "mid_trend_funnel_score": np.nan,
                    "trend_r2_20_score": np.nan,
                    "ret_20_score": np.nan,
                    "industry_mainline_score_v1": np.nan,
                    "max_drawdown_20_score": np.nan,
                    "quality_score": 50.0,
                }
            )
            continue
        row = match.iloc[0]
        rank = _numeric_value(row.get("shadow_top10_rank"))
        funnel = _numeric_value(row.get("mid_trend_funnel_score"))
        trend = _numeric_value(row.get("trend_r2_20_score"))
        ret20 = _numeric_value(row.get("ret_20_score"))
        mainline = _numeric_value(row.get("industry_mainline_score_v1"))
        drawdown = _numeric_value(row.get("max_drawdown_20_score"))
        quality = (
            0.35 * _default_quality_component(funnel)
            + 0.25 * _default_quality_component(trend)
            + 0.20 * _default_quality_component(ret20)
            + 0.10 * _default_quality_component(drawdown)
            + 0.10 * _default_quality_component(mainline * 100 if pd.notna(mainline) else np.nan)
        )
        if pd.notna(rank) and rank > buffer_rank:
            quality -= 20.0
        rows.append(
            {
                "asset_id": asset,
                "original_order": order,
                "has_current_state": True,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": funnel,
                "trend_r2_20_score": trend,
                "ret_20_score": ret20,
                "industry_mainline_score_v1": mainline,
                "max_drawdown_20_score": drawdown,
                "quality_score": quality,
            }
        )
    return pd.DataFrame(rows)


def _numeric_value(value: Any) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0])


def _default_quality_component(value: float) -> float:
    return float(value) if pd.notna(value) else 50.0


def _is_max_replacement_variant(variant_name: str) -> bool:
    return (
        variant_name == "top5_weekly_max_2_replacements"
        or "max_replacements" in variant_name
        or variant_name.startswith("top5_weekly_max2_rank_weight")
    )


def _target_variant_name(variant_name: str) -> str:
    if variant_name in {
        "top5_weekly_max2_drawdown_throttle_v1",
        "top5_weekly_max2_rank_weight_mild_v1",
        "top5_weekly_max2_rank_weight_aggressive_v1",
        "top5_adaptive_daily_check_max2_v1",
        "top5_adaptive_daily_check_rank_weight_mild_v1",
        "top5_adaptive_regime_gated_max2_v1",
    }:
        return "top5_weekly_max_2_replacements"
    if variant_name in {"top5_adaptive_hold_strong_stale_v1", "top5_adaptive_quality_gate_v1"}:
        return variant_name
    return variant_name


def _is_adaptive_variant(variant_name: str) -> bool:
    return variant_name.startswith("top5_adaptive_")


def _adaptive_regime_allows_daily_check(signals: pd.DataFrame, *, trade_date: str) -> bool:
    day = signals[signals["trade_date"].eq(trade_date)]
    if day.empty:
        return True
    blocked = {"rotation", "retreat", "weak", "high_rotation"}
    for column in ["market_regime", "mainline_context", "mainline_status"]:
        if column not in day.columns:
            continue
        values = day[column].dropna().astype(str).str.lower()
        if values.isin(blocked).any() or values.str.contains("retreat|rotation|weak", regex=True).any():
            return False
    return True


def _apply_adaptive_quality_gate(day: pd.DataFrame, *, current_assets: list[str]) -> pd.DataFrame:
    if day.empty or not current_assets:
        return day
    frame = day.copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    current = set(current_assets)
    is_current = frame["asset_id"].isin(current)
    quality = pd.Series(True, index=frame.index)
    if "industry_mainline_score_v1" in frame.columns:
        quality &= pd.to_numeric(frame["industry_mainline_score_v1"], errors="coerce").ge(0.45).fillna(True)
    if "trend_r2_20_score" in frame.columns:
        quality &= pd.to_numeric(frame["trend_r2_20_score"], errors="coerce").ge(65).fillna(True)
    if "ret_20_score" in frame.columns:
        quality &= pd.to_numeric(frame["ret_20_score"], errors="coerce").ge(60).fillna(True)
    if "max_drawdown_20_score" in frame.columns:
        quality &= pd.to_numeric(frame["max_drawdown_20_score"], errors="coerce").ge(45).fillna(True)
    if "volatility_20_score" in frame.columns:
        quality &= pd.to_numeric(frame["volatility_20_score"], errors="coerce").le(90).fillna(True)
    return frame[is_current | quality].sort_values("shadow_top10_rank")


def _adaptive_rebalance_due(
    signals: pd.DataFrame,
    buffer_signals: pd.DataFrame,
    *,
    trade_date: str,
    current_assets: list[str],
    top_n: int,
    buffer_rank: int,
    score_gap_min: float = 6.0,
    weak_trend_min: float = 65.0,
    weak_ret20_min: float = 60.0,
) -> bool:
    day = signals[signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank").copy()
    if day.empty:
        return False
    if not current_assets:
        return True

    day["asset_id"] = day["asset_id"].astype(str)
    desired = day["asset_id"].astype(str).head(top_n).tolist()
    current_set = set(current_assets)
    new_candidates = [asset for asset in desired if asset not in current_set]
    if not new_candidates:
        return False

    buffer_day = buffer_signals[buffer_signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank").copy()
    if buffer_day.empty:
        buffer_day = day.copy()
    buffer_day["asset_id"] = buffer_day["asset_id"].astype(str)

    stale_frame = buffer_day[buffer_day["asset_id"].isin(current_set - set(desired))].copy()
    if stale_frame.empty:
        return True
    for column in ["shadow_top10_rank", "mid_trend_funnel_score", "trend_r2_20_score", "ret_20_score"]:
        stale_frame[column] = pd.to_numeric(stale_frame.get(column), errors="coerce")

    if (
        stale_frame["shadow_top10_rank"].gt(buffer_rank).any()
        or stale_frame["trend_r2_20_score"].lt(float(weak_trend_min)).any()
        or stale_frame["ret_20_score"].lt(float(weak_ret20_min)).any()
    ):
        return True

    new_frame = day[day["asset_id"].isin(new_candidates)].copy()
    new_frame["mid_trend_funnel_score"] = pd.to_numeric(new_frame.get("mid_trend_funnel_score"), errors="coerce")
    best_new_score = new_frame["mid_trend_funnel_score"].max()
    weakest_old_score = stale_frame["mid_trend_funnel_score"].min()
    if pd.notna(best_new_score) and pd.notna(weakest_old_score):
        return float(best_new_score - weakest_old_score) >= float(score_gap_min)
    return False


def _fill_to_top_n(kept: list[str], ordered: list[str], top_n: int) -> list[str]:
    result: list[str] = []
    for asset in kept + ordered:
        if asset not in result:
            result.append(asset)
        if len(result) >= top_n:
            break
    return result


def _regime_for_day(day: pd.DataFrame) -> str:
    if day.empty:
        return "unknown"
    values = day["market_regime"].dropna().astype(str)
    return values.iloc[0] if not values.empty else "unknown"


def _equal_weights(assets: list[str], *, invested_weight: float) -> dict[str, float]:
    if not assets:
        return {}
    weight = float(invested_weight) / len(assets)
    return {asset: weight for asset in assets}


def _weights_for_variant(variant_name: str, assets: list[str], *, invested_weight: float) -> dict[str, float]:
    if not assets:
        return {}
    if variant_name in {"top5_weekly_max2_rank_weight_mild_v1", "top5_adaptive_daily_check_rank_weight_mild_v1"}:
        return _rank_weights(assets, [0.24, 0.22, 0.20, 0.18, 0.16], invested_weight=invested_weight)
    if variant_name == "top5_weekly_max2_rank_weight_aggressive_v1":
        return _rank_weights(assets, [0.30, 0.25, 0.20, 0.15, 0.10], invested_weight=invested_weight)
    return _equal_weights(assets, invested_weight=invested_weight)


def _rank_weights(assets: list[str], base_weights: list[float], *, invested_weight: float) -> dict[str, float]:
    raw = base_weights[: len(assets)]
    total = float(sum(raw))
    if total <= 0:
        return _equal_weights(assets, invested_weight=invested_weight)
    scaled = [round(float(invested_weight) * weight / total, 10) for weight in raw]
    return {asset: weight for asset, weight in zip(assets, scaled, strict=False)}


def _exit_assets(
    *,
    variant_name: str,
    trade_date: str,
    current_weights: dict[str, float],
    close: pd.DataFrame,
    ma20: pd.DataFrame,
    peak_close: dict[str, float],
    peak_drawdown_exit: float,
) -> set[str]:
    if variant_name not in {"top5_weekly_ma20_exit", "top5_weekly_peak_drawdown_12_exit"}:
        return set()
    exits: set[str] = set()
    for asset in current_weights:
        current_close = close.loc[trade_date].get(asset)
        if pd.isna(current_close):
            continue
        if variant_name == "top5_weekly_ma20_exit":
            ma_value = ma20.loc[trade_date].get(asset)
            if pd.notna(ma_value) and float(current_close) < float(ma_value):
                exits.add(asset)
        if variant_name == "top5_weekly_peak_drawdown_12_exit":
            peak = float(peak_close.get(asset, current_close))
            if peak > 0 and float(current_close) / peak - 1.0 <= -float(peak_drawdown_exit):
                exits.add(asset)
    return exits


def _rebalance_turnover(previous: dict[str, float], target: dict[str, float]) -> float:
    assets = set(previous) | set(target)
    return float(sum(abs(float(target.get(asset, 0.0)) - float(previous.get(asset, 0.0))) for asset in assets))


def _trade_rows(
    variant_name: str,
    trade_date: str,
    previous: dict[str, float],
    target: dict[str, float],
    reason: str,
    cost_rate: float,
) -> list[dict[str, Any]]:
    rows = []
    for asset in sorted(set(previous) | set(target)):
        prev = float(previous.get(asset, 0.0))
        nxt = float(target.get(asset, 0.0))
        if abs(nxt - prev) < 1e-12:
            continue
        rows.append(
            {
                "variant_name": variant_name,
                "trade_date": trade_date,
                "asset_id": asset,
                "side": "buy" if nxt > prev else "sell",
                "previous_weight": prev,
                "target_weight": nxt,
                "delta_weight": nxt - prev,
                "turnover_contribution": abs(nxt - prev),
                "transaction_cost": abs(nxt - prev) * cost_rate,
                "reason": reason,
            }
        )
    return rows


def _summary_row(
    variant_name: str,
    equity: pd.DataFrame,
    *,
    positions: pd.DataFrame,
    trades: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n: int,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    if equity.empty:
        return {
            "variant_name": variant_name,
            "start_date": start_date,
            "end_date": end_date,
            "top_n": top_n,
            "transaction_cost_bps": transaction_cost_bps,
            "periods": 0,
            "final_equity": np.nan,
            "total_return": np.nan,
            "annualized_return": np.nan,
            "annualized_volatility": np.nan,
            "sharpe_ratio": np.nan,
            "max_drawdown": np.nan,
            "calmar_ratio": np.nan,
            "daily_win_rate": np.nan,
            "average_turnover": np.nan,
            "total_transaction_cost": np.nan,
            "position_rows": 0,
            "trade_rows": 0,
        }
    returns = pd.to_numeric(equity["net_return"], errors="coerce").dropna()
    periods = int(len(equity))
    total_return = float(equity.iloc[-1]["equity"]) - 1.0
    ann_return = (1.0 + total_return) ** (252.0 / periods) - 1.0 if total_return > -1 and periods else np.nan
    ann_vol = float(returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 else np.nan
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 and returns.std(ddof=1) else np.nan
    max_drawdown = float(pd.to_numeric(equity["drawdown"], errors="coerce").min())
    trigger_count = (
        int(equity["drawdown_throttle_triggered"].fillna(False).astype(bool).sum())
        if "drawdown_throttle_triggered" in equity.columns
        else 0
    )
    average_invested_weight = (
        float(pd.to_numeric(equity["invested_weight"], errors="coerce").mean())
        if "invested_weight" in equity.columns
        else np.nan
    )
    return {
        "variant_name": variant_name,
        "start_date": start_date,
        "end_date": end_date,
        "actual_start_date": str(equity.iloc[0]["date"]),
        "actual_end_date": str(equity.iloc[-1]["date"]),
        "top_n": top_n,
        "transaction_cost_bps": transaction_cost_bps,
        "periods": periods,
        "final_equity": float(equity.iloc[-1]["equity"]),
        "total_return": total_return,
        "annualized_return": ann_return,
        "annualized_volatility": ann_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "calmar_ratio": ann_return / abs(max_drawdown) if max_drawdown < 0 else np.nan,
        "daily_win_rate": float((returns > 0).mean()) if not returns.empty else np.nan,
        "average_turnover": float(pd.to_numeric(equity["turnover"], errors="coerce").mean()),
        "total_transaction_cost": float(pd.to_numeric(equity["transaction_cost"], errors="coerce").sum()),
        "drawdown_throttle_trigger_count": trigger_count,
        "average_invested_weight": average_invested_weight,
        "position_rows": int(len(positions)),
        "trade_rows": int(len(trades)),
    }


def _empty_variant_result(variant_name: str, start_date: str, end_date: str) -> dict[str, Any]:
    return {
        "equity_curve": pd.DataFrame(),
        "positions": pd.DataFrame(),
        "trades": pd.DataFrame(),
        "summary": _summary_row(
            variant_name,
            pd.DataFrame(),
            positions=pd.DataFrame(),
            trades=pd.DataFrame(),
            start_date=start_date,
            end_date=end_date,
            top_n=5,
            transaction_cost_bps=0.0,
        ),
    }


def _render_report(summary: pd.DataFrame) -> str:
    lines = [
        "# Mid Trend Shadow Weekly Control v1",
        "",
        "## 1. Scope",
        "周频 shadow Top5 的回撤控制和调仓规则诊断；不生成交易建议，不接实盘。",
        "",
        "## 2. Variant Summary",
        summary.to_markdown(index=False) if not summary.empty else "No summary rows.",
        "",
        "## 3. Guardrail",
        "优先比较最大回撤、Calmar、换手和交易成本；收益提升不是唯一目标。",
    ]
    return "\n".join(lines).rstrip() + "\n"
