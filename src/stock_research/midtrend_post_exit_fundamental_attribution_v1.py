from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.current_mid_trend_strategy_v1 import load_current_strategy_prices
from stock_research.midtrend_topn_pool_reentry_sweep import (
    _build_end_return_lookup,
    _build_growth_rank_frame,
    _build_price_state,
    _date_str,
    _price_horizon_return,
)

V1_BASE_DIR = Path("outputs/research/current_mid_trend_strategy_v1_20250101_20260612_retest")
V2_BASE_DIR = Path("outputs/research/current_mid_trend_strategy_v2_top10_candidate_20250101_20260612")
TOPN_SWEEP_DIR = Path("outputs/research/midtrend_topn_pool_reentry_sweep_20260626")
TOP10_REENTRY_DIR = Path("outputs/research/midtrend_top10_reentry_experiment_20260626")
TOP10_GATING_DIR = Path("outputs/research/midtrend_top10_reentry_gating_experiment_20260626")
FUNNEL_DETAIL_PATH = Path("outputs/research/mid_trend_watch_funnel_20250101_20260612_retest/mid_trend_watch_funnel_detail.csv")

PATH_WINDOWS = (10, 20, 30, 60)


def run_midtrend_post_exit_fundamental_attribution_cli(
    *,
    output_dir: str | Path,
    start_date: str = "2025-01-01",
    end_date: str = "2026-06-12",
) -> dict[str, Any]:
    funnel = pd.read_csv(FUNNEL_DETAIL_PATH, low_memory=False)
    v1_holdings = pd.read_csv(V1_BASE_DIR / "current_mid_trend_strategy_v1_daily_holdings.csv", low_memory=False)
    v1_trades = pd.read_csv(V1_BASE_DIR / "current_mid_trend_strategy_v1_trade_changes.csv", low_memory=False)
    v2_holdings = pd.read_csv(V2_BASE_DIR / "current_mid_trend_strategy_v2_top10_candidate_daily_holdings.csv", low_memory=False)
    v2_trades = pd.read_csv(V2_BASE_DIR / "current_mid_trend_strategy_v2_top10_candidate_trade_changes.csv", low_memory=False)
    asset_ids = sorted(
        funnel[_date_str(funnel["trade_date"]).between(start_date, end_date)]["asset_id"].dropna().astype(str).unique().tolist()
    )
    prices = load_current_strategy_prices(start_date, end_date, asset_ids=asset_ids, adjust_type="hfq")
    return run_midtrend_post_exit_fundamental_attribution_from_frames(
        v1_holdings=v1_holdings,
        v1_trades=v1_trades,
        v2_holdings=v2_holdings,
        v2_trades=v2_trades,
        funnel=funnel,
        prices=prices,
        output_dir=output_dir,
        start_date=start_date,
        end_date=end_date,
        reentry_event_log=_optional_csv(TOP10_REENTRY_DIR / "reentry_event_log.csv"),
        reentry_trade_contribution=_optional_csv(TOP10_REENTRY_DIR / "reentry_trade_contribution.csv"),
    )


def run_midtrend_post_exit_fundamental_attribution_from_frames(
    *,
    v1_holdings: pd.DataFrame,
    v1_trades: pd.DataFrame,
    v2_holdings: pd.DataFrame,
    v2_trades: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    output_dir: str | Path,
    start_date: str,
    end_date: str,
    reentry_event_log: pd.DataFrame | None = None,
    reentry_trade_contribution: pd.DataFrame | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    funnel = _normalize_frame_dates(funnel, "trade_date")
    prices = _normalize_frame_dates(prices, "trade_date")
    v1_holdings = _normalize_frame_dates(v1_holdings, "trade_date")
    v1_trades = _normalize_frame_dates(v1_trades, "trade_date")
    v2_holdings = _normalize_frame_dates(v2_holdings, "trade_date")
    v2_trades = _normalize_frame_dates(v2_trades, "trade_date")

    scoped_funnel = funnel[funnel["trade_date"].between(start_date, end_date)].copy()
    scoped_prices = prices[prices["trade_date"].between(start_date, end_date)].copy()
    price_state = _build_price_state(scoped_prices)
    end_lookup = _build_end_return_lookup(scoped_prices)
    growth_all = _build_growth_rank_frame(scoped_funnel, start_date=start_date, end_date=end_date)

    v1_obs = _build_post_exit_observation_for_strategy(
        strategy_name="current_mid_trend_strategy_v1",
        source_variant="baseline_top5",
        holdings=v1_holdings,
        trades=v1_trades,
        funnel=scoped_funnel,
        growth_all=growth_all,
        final_top_n=5,
    )
    v2_obs = _build_post_exit_observation_for_strategy(
        strategy_name="current_mid_trend_strategy_v2_top10_candidate",
        source_variant="top10_candidate",
        holdings=v2_holdings,
        trades=v2_trades,
        funnel=scoped_funnel,
        growth_all=growth_all,
        final_top_n=10,
    )
    observation_pool = pd.concat([v1_obs, v2_obs], ignore_index=True)
    observation_pool = join_exit_date_funnel_fields(observation_pool, scoped_funnel)
    observation_pool = _apply_fundamental_buckets(observation_pool)
    observation_pool["midtrend_confirmation_state"] = observation_pool.apply(_midtrend_state, axis=1)
    observation_pool.to_csv(output / "post_exit_observation_pool.csv", index=False)

    path_behavior = _augment_post_exit_behavior(observation_pool, growth_all, price_state)
    path_behavior.to_csv(output / "post_exit_path_behavior.csv", index=False)
    _path_bucket_summary(path_behavior).to_csv(output / "post_exit_path_bucket_summary.csv", index=False)

    comparison = _continued_vs_failed_comparison(path_behavior)
    comparison.to_csv(output / "continued_winner_vs_failed_exit_comparison.csv", index=False)

    bad_sell = _bad_sell_attribution(path_behavior, end_lookup)
    bad_sell["path_summary"].to_csv(output / "bad_sell_path_attribution.csv", index=False)
    bad_sell["fundamental_summary"].to_csv(output / "bad_sell_fundamental_attribution.csv", index=False)
    bad_sell["continued_examples"].to_csv(output / "bad_sell_examples_continued_winners.csv", index=False)
    bad_sell["true_exit_examples"].to_csv(output / "bad_sell_examples_true_exits.csv", index=False)

    bad_buy = _bad_buy_attribution(
        pd.concat(
            [
                _label_bad_buy_sell(v1_trades, end_lookup, strategy_name="baseline_top5"),
                _label_bad_buy_sell(v2_trades, end_lookup, strategy_name="top10_candidate"),
            ],
            ignore_index=True,
        ),
        scoped_funnel,
    )
    bad_buy["fundamental"].to_csv(output / "bad_buy_fundamental_attribution.csv", index=False)
    bad_buy["mainline"].to_csv(output / "bad_buy_mainline_attribution.csv", index=False)
    bad_buy["fundamental_weak_examples"].to_csv(output / "bad_buy_examples_fundamental_weak.csv", index=False)
    bad_buy["false_technical_examples"].to_csv(output / "bad_buy_examples_false_technical_strength.csv", index=False)
    bad_buy["good_but_early_examples"].to_csv(output / "bad_buy_examples_good_but_early.csv", index=False)

    reentry_path = _reentry_left_tail_attribution(
        reentry_event_log if reentry_event_log is not None else pd.DataFrame(),
        reentry_trade_contribution if reentry_trade_contribution is not None else pd.DataFrame(),
        path_behavior,
    )
    reentry_path["path_summary"].to_csv(output / "reentry_left_tail_path_attribution.csv", index=False)
    reentry_path["fundamental_summary"].to_csv(output / "reentry_left_tail_fundamental_attribution.csv", index=False)
    reentry_path["failed_examples"].to_csv(output / "reentry_failed_rebound_examples.csv", index=False)
    reentry_path["continuation_examples"].to_csv(output / "reentry_true_continuation_examples.csv", index=False)

    coverage = _fundamental_coverage_audit(path_behavior)
    coverage.to_csv(output / "fundamental_data_coverage_audit.csv", index=False)
    (output / "fundamental_missing_fields_report.md").write_text(
        _fundamental_missing_report(scoped_funnel, path_behavior),
        encoding="utf-8",
    )

    simple_rules = _simple_rule_discovery(path_behavior, bad_buy["joined"])
    simple_rules["tables"].to_csv(output / "simple_rule_discovery_tables.csv", index=False)
    simple_rules["separability"].to_csv(output / "feature_separability_summary.csv", index=False)

    _run_params().to_csv(output / "run_params.csv", index=False)
    (output / "code_audit.md").write_text(_code_audit(scoped_funnel, observation_pool), encoding="utf-8")
    (output / "final_interpretation.md").write_text(
        _final_interpretation(path_behavior, bad_sell["path_summary"], bad_buy["fundamental"], reentry_path["path_summary"], coverage),
        encoding="utf-8",
    )

    return {"observation_pool": observation_pool, "paths": {"output_dir": str(output)}}


def join_exit_date_funnel_fields(pool: pd.DataFrame, funnel: pd.DataFrame) -> pd.DataFrame:
    if pool.empty:
        return pool.copy()
    keep = [
        "trade_date",
        "asset_id",
        "stock_name",
        "industry_name",
        "score_rank",
        "rank",
        "mid_trend_funnel_score",
        "mid_trend_layer",
        "ret_20_score",
        "ret_60_score",
        "ma20_slope_score",
        "ma60_slope_score",
        "trend_r2_20_score",
        "stock_excess_ret_20_score",
        "sector_ret_20_score",
        "max_drawdown_20_score",
        "volatility_20_score",
        "atr_pct_score",
        "mainline_status",
        "industry_mainline_score_v1",
        "technical_confirmed",
        "mainline_confirmed",
        "fundamental_quality_score",
        "fundamental_quality_bucket",
        "fundamental_confirmed",
        "fundamental_risk_flag",
        "revenue_growth_yoy",
        "profit_growth_yoy",
        "roe",
    ]
    detail = funnel.copy()
    for column in keep:
        if column not in detail.columns:
            detail[column] = pd.NA
    detail = detail[keep].rename(columns={"trade_date": "event_date"})
    joined = pool.merge(detail, on=["event_date", "asset_id"], how="left")
    return joined


def compute_fundamental_buckets(row: pd.Series) -> dict[str, Any]:
    revenue = _num(row.get("revenue_growth_yoy"))
    profit = _num(row.get("profit_growth_yoy"))
    roe = _num(row.get("roe"))
    risk = _safe_bool(row.get("fundamental_risk_flag")) or _safe_bool(row.get("financial_risk_flag")) or _safe_bool(row.get("st_or_risk_flag"))
    values = [value for value in [revenue, profit, roe] if not np.isnan(value)]
    if not values:
        quality_bucket = "quality_unknown"
        momentum_bucket = "unknown"
        score = np.nan
    else:
        score = float(np.nanmean(values))
        if risk or score < 5 or revenue < 0 or profit < 0:
            quality_bucket = "quality_weak"
        elif score >= 20:
            quality_bucket = "quality_strong"
        else:
            quality_bucket = "quality_neutral"
        if revenue >= 20 and profit >= 20:
            momentum_bucket = "improving"
        elif revenue < 0 or profit < 0:
            momentum_bucket = "deteriorating"
        else:
            momentum_bucket = "stable"
    return {
        "fundamental_quality_score": score,
        "fundamental_quality_bucket": quality_bucket,
        "fundamental_momentum_bucket": momentum_bucket,
        "fundamental_risk_flag": risk,
    }


def classify_post_exit_path(row: pd.Series) -> dict[str, Any]:
    ret10 = _num(row.get("forward_return_10d"))
    ret20 = _num(row.get("forward_return_20d"))
    ret30 = _num(row.get("forward_return_30d"))
    ret60 = _num(row.get("forward_return_60d"))
    dd10 = _num(row.get("max_drawdown_after_exit_10d"))
    reentered = bool(row.get("reentered_top10_within_30d")) or bool(row.get("reentered_top20_within_30d")) or bool(row.get("reconfirmed_T1_M1_within_30d"))
    if ret20 >= 0.08 and dd10 >= -0.05:
        path = "immediate_continuation"
    elif ret60 >= 0.12 and ret10 < 0.05 and reentered:
        path = "pullback_then_reacceleration"
    elif reentered and ret60 < 0.05:
        path = "failed_rebound"
    elif ret30 < 0.0 and ret60 < 0.02:
        path = "true_exit"
    else:
        path = "noisy_unclear"
    continued = path in {"immediate_continuation", "pullback_then_reacceleration"}
    return {"path_class": path, "continued_winner_flag": continued}


def _build_post_exit_observation_for_strategy(
    *,
    strategy_name: str,
    source_variant: str,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    funnel: pd.DataFrame,
    growth_all: pd.DataFrame,
    final_top_n: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    active = holdings[holdings["asset_id"].notna()].copy()
    active["asset_id"] = active["asset_id"].astype(str)
    active["trade_date"] = _date_str(active["trade_date"])
    trades = trades.copy()
    trades["asset_id"] = trades["asset_id"].astype(str)
    trades["trade_date"] = _date_str(trades["trade_date"])
    holding_days = (
        active.groupby("asset_id")["trade_date"].nunique().to_dict()
        if not active.empty
        else {}
    )
    for row in trades[trades["action"].astype(str).isin(["sell", "decrease"])].itertuples(index=False):
        rows.append(
            {
                "strategy_name": strategy_name,
                "source_variant": source_variant,
                "event_date": str(row.trade_date),
                "asset_id": str(row.asset_id),
                "stock_name": getattr(row, "stock_name", ""),
                "industry_name": getattr(row, "industry_name", ""),
                "event_type": "hard_damage_sell" if str(getattr(row, "protection_reason", "")) else "ranking_churn_sell",
                "was_held": True,
                "holding_days_before_exit": int(holding_days.get(str(row.asset_id), 0)),
                "previous_best_rank_5_10_20": _previous_best_rank(active, str(row.asset_id), str(row.trade_date)),
                "rank_on_exit_date": _num(getattr(row, "score_rank", np.nan)),
                "mid_trend_funnel_score_on_exit": _num(getattr(row, "mid_trend_funnel_score", np.nan)),
                "mid_trend_layer_on_exit": getattr(row, "mid_trend_layer", ""),
                "target_weight_before_exit": _num(getattr(row, "previous_weight", np.nan)),
                "weight_change": _num(getattr(row, "delta_weight", np.nan)),
                "sell_or_drop_reason": str(getattr(row, "action", "")),
                "protection_reason": str(getattr(row, "protection_reason", "")),
                "confirmed_regime_state": str(getattr(row, "confirmed_regime_state", "")),
            }
        )
    growth = growth_all.copy()
    growth["trade_date"] = _date_str(growth["trade_date"])
    growth["asset_id"] = growth["asset_id"].astype(str)
    growth["in_top"] = pd.to_numeric(growth["candidate_rank"], errors="coerce").le(final_top_n)
    prev_top: dict[str, bool] = {}
    prev_top5: dict[str, bool] = {}
    prev_top10: dict[str, bool] = {}
    prev_top20: dict[str, bool] = {}
    held_lookup = {(d, a) for d, a in active[["trade_date", "asset_id"]].itertuples(index=False)}
    for row in growth.sort_values(["trade_date", "candidate_rank", "asset_id"]).itertuples(index=False):
        asset_id = str(row.asset_id)
        trade_date = str(row.trade_date)
        rank = _num(getattr(row, "candidate_rank", np.nan))
        in_top = bool(rank <= final_top_n) if not np.isnan(rank) else False
        in_top5 = bool(rank <= 5) if not np.isnan(rank) else False
        in_top10 = bool(rank <= 10) if not np.isnan(rank) else False
        in_top20 = bool(rank <= 20) if not np.isnan(rank) else False
        was_held = (trade_date, asset_id) in held_lookup
        if prev_top.get(asset_id, False) and not in_top and was_held:
            rows.append(
                {
                    "strategy_name": strategy_name,
                    "source_variant": source_variant,
                    "event_date": trade_date,
                    "asset_id": asset_id,
                    "stock_name": getattr(row, "stock_name", ""),
                    "industry_name": getattr(row, "industry_name", ""),
                    "event_type": "dropped_from_topn",
                    "was_held": was_held,
                    "holding_days_before_exit": int(holding_days.get(asset_id, 0)),
                    "previous_best_rank_5_10_20": _previous_best_rank(active, asset_id, trade_date),
                    "rank_on_exit_date": rank,
                    "mid_trend_funnel_score_on_exit": _num(getattr(row, "mid_trend_funnel_score", np.nan)),
                    "mid_trend_layer_on_exit": getattr(row, "mid_trend_layer", ""),
                    "target_weight_before_exit": np.nan,
                    "weight_change": np.nan,
                    "sell_or_drop_reason": "dropped_from_topn",
                    "protection_reason": "",
                    "confirmed_regime_state": "",
                }
            )
        if prev_top5.get(asset_id, False) and not in_top5:
            rows.append(_drop_row(strategy_name, source_variant, trade_date, asset_id, row, "dropped_from_top5"))
        if prev_top10.get(asset_id, False) and not in_top10:
            rows.append(_drop_row(strategy_name, source_variant, trade_date, asset_id, row, "dropped_from_top10"))
        if prev_top20.get(asset_id, False) and not in_top20:
            rows.append(_drop_row(strategy_name, source_variant, trade_date, asset_id, row, "dropped_from_top20"))
        prev_top[asset_id] = in_top
        prev_top5[asset_id] = in_top5
        prev_top10[asset_id] = in_top10
        prev_top20[asset_id] = in_top20
    if not rows:
        return pd.DataFrame(columns=["strategy_name", "source_variant", "event_date", "asset_id"])
    frame = pd.DataFrame(rows).drop_duplicates(subset=["strategy_name", "source_variant", "event_date", "asset_id", "event_type"])
    return frame.reset_index(drop=True)


def _drop_row(strategy_name: str, source_variant: str, trade_date: str, asset_id: str, row: Any, event_type: str) -> dict[str, Any]:
    return {
        "strategy_name": strategy_name,
        "source_variant": source_variant,
        "event_date": trade_date,
        "asset_id": asset_id,
        "stock_name": getattr(row, "stock_name", ""),
        "industry_name": getattr(row, "industry_name", ""),
        "event_type": event_type,
        "was_held": False,
        "holding_days_before_exit": 0,
        "previous_best_rank_5_10_20": np.nan,
        "rank_on_exit_date": _num(getattr(row, "candidate_rank", np.nan)),
        "mid_trend_funnel_score_on_exit": _num(getattr(row, "mid_trend_funnel_score", np.nan)),
        "mid_trend_layer_on_exit": getattr(row, "mid_trend_layer", ""),
        "target_weight_before_exit": np.nan,
        "weight_change": np.nan,
        "sell_or_drop_reason": event_type,
        "protection_reason": "",
        "confirmed_regime_state": "",
    }


def _augment_post_exit_behavior(pool: pd.DataFrame, growth_all: pd.DataFrame, price_state: dict[str, Any]) -> pd.DataFrame:
    rows = []
    growth_map = _growth_asset_map(growth_all)
    for row in pool.itertuples(index=False):
        record = dict(row._asdict())
        asset_id = str(record["asset_id"])
        event_date = str(record["event_date"])
        for horizon in PATH_WINDOWS:
            record[f"forward_return_{horizon}d"] = _price_horizon_return(price_state, event_date, asset_id, horizon)
            record[f"max_return_after_exit_{horizon}d"] = _price_horizon_max_return(price_state, event_date, asset_id, horizon)
            record[f"max_drawdown_after_exit_{horizon}d"] = _price_horizon_min_return(price_state, event_date, asset_id, horizon)
        record["days_to_max_return_60d"] = np.nan
        record["days_to_max_drawdown_60d"] = np.nan
        recon = _growth_followup(growth_map.get(asset_id, pd.DataFrame()), event_date)
        record.update(recon)
        record.update(classify_post_exit_path(pd.Series(record)))
        rows.append(record)
    return pd.DataFrame(rows)


def _growth_followup(asset_frame: pd.DataFrame, event_date: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if asset_frame.empty:
        for horizon in PATH_WINDOWS:
            result[f"reentered_top5_within_{horizon}d"] = False
            result[f"reentered_top10_within_{horizon}d"] = False
            result[f"reentered_top20_within_{horizon}d"] = False
            result[f"reconfirmed_T1_M1_within_{horizon}d"] = False
        result["days_to_reenter_top5"] = np.nan
        result["days_to_reenter_top10"] = np.nan
        result["days_to_reenter_top20"] = np.nan
        result["days_to_reconfirm_T1_M1"] = np.nan
        return result
    future = asset_frame[asset_frame["trade_date"].astype(str) > event_date].sort_values("trade_date")
    ranks = pd.to_numeric(future.get("candidate_rank"), errors="coerce").to_numpy()
    states = future.get("midtrend_confirmation_state", pd.Series(dtype=str)).astype(str).to_numpy()
    for horizon in PATH_WINDOWS:
        slice_ranks = ranks[:horizon]
        slice_states = states[:horizon]
        result[f"reentered_top5_within_{horizon}d"] = bool(np.isfinite(slice_ranks).any() and np.nanmin(slice_ranks) <= 5) if len(slice_ranks) else False
        result[f"reentered_top10_within_{horizon}d"] = bool(np.isfinite(slice_ranks).any() and np.nanmin(slice_ranks) <= 10) if len(slice_ranks) else False
        result[f"reentered_top20_within_{horizon}d"] = bool(np.isfinite(slice_ranks).any() and np.nanmin(slice_ranks) <= 20) if len(slice_ranks) else False
        result[f"reconfirmed_T1_M1_within_{horizon}d"] = bool(np.char.startswith(slice_states.astype(str), "T1_M1").any()) if len(slice_states) else False
    result["days_to_reenter_top5"] = _days_to_rank(ranks, 5)
    result["days_to_reenter_top10"] = _days_to_rank(ranks, 10)
    result["days_to_reenter_top20"] = _days_to_rank(ranks, 20)
    result["days_to_reconfirm_T1_M1"] = _days_to_state(states, "T1_M1")
    return result


def _bad_sell_attribution(path_behavior: pd.DataFrame, end_lookup: dict[tuple[str, str], float]) -> dict[str, pd.DataFrame]:
    sells = path_behavior[path_behavior["event_type"].astype(str).isin(["ranking_churn_sell", "hard_damage_sell"])].copy()
    sells["forward_return_end"] = sells.apply(lambda row: end_lookup.get((str(row["event_date"]), str(row["asset_id"])), np.nan), axis=1)
    bad = sells[pd.to_numeric(sells["forward_return_end"], errors="coerce").gt(0.02)].copy()
    return {
        "path_summary": bad.groupby("path_class", as_index=False).agg(
            count=("asset_id", "size"),
            opportunity_contribution=("forward_return_end", "sum"),
            forward_return_10d=("forward_return_10d", "mean"),
            forward_return_20d=("forward_return_20d", "mean"),
            forward_return_30d=("forward_return_30d", "mean"),
            forward_return_60d=("forward_return_60d", "mean"),
        ) if not bad.empty else pd.DataFrame(columns=["path_class"]),
        "fundamental_summary": bad.groupby(["path_class", "fundamental_quality_bucket", "midtrend_confirmation_state"], as_index=False).agg(
            count=("asset_id", "size")
        ) if not bad.empty else pd.DataFrame(columns=["path_class"]),
        "continued_examples": bad[bad["continued_winner_flag"].astype(bool)].sort_values("forward_return_end", ascending=False).head(50),
        "true_exit_examples": bad[bad["path_class"].astype(str).eq("true_exit")].head(50),
    }


def _bad_buy_attribution(trades: pd.DataFrame, funnel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    keep = [
        "trade_date",
        "asset_id",
        "mid_trend_layer",
        "technical_confirmed",
        "mainline_confirmed",
        "mainline_status",
        "fundamental_quality_bucket",
        "fundamental_risk_flag",
        "revenue_growth_yoy",
        "profit_growth_yoy",
        "roe",
    ]
    detail = funnel.copy()
    for column in keep:
        if column not in detail.columns:
            detail[column] = pd.NA
    detail = detail[keep].rename(
        columns={
            "trade_date": "entry_date",
            "mid_trend_layer": "entry_mid_trend_layer",
            "technical_confirmed": "entry_technical_confirmed",
            "mainline_confirmed": "entry_mainline_confirmed",
            "mainline_status": "entry_mainline_status",
            "fundamental_quality_bucket": "entry_fundamental_quality_bucket",
            "fundamental_risk_flag": "entry_fundamental_risk_flag",
            "revenue_growth_yoy": "entry_revenue_growth_yoy",
            "profit_growth_yoy": "entry_profit_growth_yoy",
            "roe": "entry_roe",
        }
    )
    joined = trades[trades["audit_label"].astype(str).eq("bad_buy")].merge(
        detail,
        left_on=["trade_date", "asset_id"],
        right_on=["entry_date", "asset_id"],
        how="left",
        suffixes=("", "_funnel"),
    )
    if joined.empty:
        empty = pd.DataFrame()
        return {"fundamental": empty, "mainline": empty, "fundamental_weak_examples": empty, "false_technical_examples": empty, "good_but_early_examples": empty, "joined": joined}
    for src, dst in [
        ("entry_revenue_growth_yoy", "revenue_growth_yoy"),
        ("entry_profit_growth_yoy", "profit_growth_yoy"),
        ("entry_roe", "roe"),
        ("entry_fundamental_risk_flag", "fundamental_risk_flag"),
    ]:
        if dst not in joined.columns and src in joined.columns:
            joined[dst] = joined[src]
    joined = _apply_fundamental_buckets(joined)
    joined["bad_buy_bucket"] = joined.apply(_bad_buy_bucket, axis=1)
    layer_col = "entry_mid_trend_layer"
    return {
        "fundamental": joined.groupby(["bad_buy_bucket", "fundamental_quality_bucket"], as_index=False).agg(count=("asset_id", "size"), avg_forward_return=("forward_return", "mean")),
        "mainline": joined.groupby(["bad_buy_bucket", "entry_mainline_status"], as_index=False).agg(count=("asset_id", "size")),
        "fundamental_weak_examples": joined[joined["fundamental_quality_bucket"].astype(str).eq("quality_weak")].head(50),
        "false_technical_examples": joined[joined[layer_col].astype(str).eq("high_elasticity_watch")].head(50),
        "good_but_early_examples": joined[pd.to_numeric(joined["forward_return"], errors="coerce").gt(-0.05)].head(50),
        "joined": joined,
    }


def _reentry_left_tail_attribution(
    event_log: pd.DataFrame,
    trade_contribution: pd.DataFrame,
    path_behavior: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    if event_log.empty or trade_contribution.empty:
        empty = pd.DataFrame()
        return {"path_summary": empty, "fundamental_summary": empty, "failed_examples": empty, "continuation_examples": empty}
    executed = event_log[event_log["action_taken"].astype(str).eq("executed_reentry_signal")].copy()
    merged = trade_contribution.merge(
        executed[["variant_name", "asset_id", "watch_start_date", "reentry_date"]],
        left_on=["variant_name", "asset_id", "trade_date"],
        right_on=["variant_name", "asset_id", "reentry_date"],
        how="left",
    )
    merged = merged.merge(
        path_behavior[["source_variant", "asset_id", "event_date", "path_class", "fundamental_quality_bucket", "mid_trend_layer_on_exit", "mainline_status", "rank_on_exit_date"]],
        left_on=["asset_id", "watch_start_date"],
        right_on=["asset_id", "event_date"],
        how="left",
    )
    failed = merged[pd.to_numeric(merged["failed_reentry_loss"], errors="coerce").lt(-0.03)].copy()
    return {
        "path_summary": failed.groupby("path_class", as_index=False).agg(count=("asset_id", "size"), avg_failed_reentry_loss=("failed_reentry_loss", "mean")) if not failed.empty else pd.DataFrame(columns=["path_class"]),
        "fundamental_summary": failed.groupby(["path_class", "fundamental_quality_bucket"], as_index=False).agg(count=("asset_id", "size")) if not failed.empty else pd.DataFrame(columns=["path_class"]),
        "failed_examples": failed.head(50),
        "continuation_examples": merged[merged["path_class"].astype(str).isin(["immediate_continuation", "pullback_then_reacceleration"])].head(50),
    }


def _fundamental_coverage_audit(path_behavior: pd.DataFrame) -> pd.DataFrame:
    if path_behavior.empty:
        return pd.DataFrame(columns=["segment", "total_rows"])
    segments = [
        ("all", path_behavior),
        ("bad_sell", path_behavior[path_behavior["event_type"].astype(str).isin(["ranking_churn_sell", "hard_damage_sell"])]),
        ("continued_winner", path_behavior[path_behavior["continued_winner_flag"].astype(bool)]),
        ("failed_exit", path_behavior[path_behavior["path_class"].astype(str).isin(["failed_rebound", "true_exit"])]),
    ]
    rows = []
    for name, frame in segments:
        total = len(frame)
        rows.append(
            {
                "segment": name,
                "total_rows": total,
                "rows_with_any_fundamental_data": int(frame[["revenue_growth_yoy", "profit_growth_yoy", "roe"]].notna().any(axis=1).sum()) if total else 0,
                "rows_with_revenue_profit_data": int(frame[["revenue_growth_yoy", "profit_growth_yoy"]].notna().all(axis=1).sum()) if total else 0,
                "rows_with_valuation_data": 0,
                "rows_with_cashflow_data": 0,
                "rows_with_risk_flags": int(frame.get("fundamental_risk_flag", pd.Series(dtype=bool)).fillna(False).sum()) if total else 0,
            }
        )
    return pd.DataFrame(rows)


def _simple_rule_discovery(path_behavior: pd.DataFrame, bad_buy_joined: pd.DataFrame) -> dict[str, pd.DataFrame]:
    tables = []
    if not path_behavior.empty and "stock_excess_ret_20_score" in path_behavior.columns:
        temp = path_behavior.copy()
        temp["rs_bucket"] = pd.cut(pd.to_numeric(temp["stock_excess_ret_20_score"], errors="coerce"), bins=[-np.inf, 60, 75, 90, np.inf], labels=["low", "mid", "strong", "very_strong"])
        tables.append(
            temp.groupby("rs_bucket", as_index=False).agg(
                count=("asset_id", "size"),
                continued_winner_rate=("continued_winner_flag", "mean"),
            ).assign(table_name="continued_winner_rate_by_stock_excess_ret_20_score")
        )
    if not bad_buy_joined.empty:
        tables.append(
            bad_buy_joined.groupby("fundamental_quality_bucket", as_index=False).agg(
                count=("asset_id", "size"),
                avg_forward_return=("forward_return", "mean"),
            ).assign(table_name="bad_buy_loss_by_fundamental_quality_bucket")
        )
    table_df = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=["table_name"])
    sep = _continued_vs_failed_comparison(path_behavior)
    return {"tables": table_df, "separability": sep}


def _continued_vs_failed_comparison(path_behavior: pd.DataFrame) -> pd.DataFrame:
    if path_behavior.empty:
        return pd.DataFrame(columns=["feature"])
    features = [
        "rank_on_exit_date",
        "mid_trend_funnel_score_on_exit",
        "ret_20_score",
        "ret_60_score",
        "stock_excess_ret_20_score",
        "sector_ret_20_score",
        "ma20_slope_score",
        "ma60_slope_score",
        "trend_r2_20_score",
        "max_drawdown_20_score",
        "volatility_20_score",
        "atr_pct_score",
        "industry_mainline_score_v1",
        "fundamental_quality_score",
        "revenue_growth_yoy",
        "profit_growth_yoy",
        "roe",
    ]
    winners = path_behavior[path_behavior["continued_winner_flag"].astype(bool)]
    failed = path_behavior[path_behavior["path_class"].astype(str).isin(["failed_rebound", "true_exit"])]
    rows = []
    for feature in features:
        if feature not in path_behavior.columns:
            continue
        w = pd.to_numeric(winners.get(feature), errors="coerce")
        f = pd.to_numeric(failed.get(feature), errors="coerce")
        rows.append(
            {
                "feature": feature,
                "continued_count": int(w.notna().sum()),
                "continued_mean": float(w.mean()) if w.notna().any() else np.nan,
                "continued_median": float(w.median()) if w.notna().any() else np.nan,
                "continued_p25": float(w.quantile(0.25)) if w.notna().any() else np.nan,
                "continued_p75": float(w.quantile(0.75)) if w.notna().any() else np.nan,
                "failed_count": int(f.notna().sum()),
                "failed_mean": float(f.mean()) if f.notna().any() else np.nan,
                "failed_median": float(f.median()) if f.notna().any() else np.nan,
                "failed_p25": float(f.quantile(0.25)) if f.notna().any() else np.nan,
                "failed_p75": float(f.quantile(0.75)) if f.notna().any() else np.nan,
                "mean_difference": float(w.mean() - f.mean()) if w.notna().any() and f.notna().any() else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _path_bucket_summary(path_behavior: pd.DataFrame) -> pd.DataFrame:
    return path_behavior.groupby(["strategy_name", "source_variant", "path_class"], as_index=False).agg(
        count=("asset_id", "size"),
        avg_forward_return_20d=("forward_return_20d", "mean"),
        avg_forward_return_60d=("forward_return_60d", "mean"),
    )


def _apply_fundamental_buckets(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    buckets = result.apply(compute_fundamental_buckets, axis=1, result_type="expand")
    for column in buckets.columns:
        result[column] = buckets[column]
    return result


def _label_bad_buy_sell(trades: pd.DataFrame, end_lookup: dict[tuple[str, str], float], *, strategy_name: str) -> pd.DataFrame:
    result = trades.copy()
    if result.empty:
        result["audit_label"] = pd.Series(dtype=str)
        return result
    result["trade_date"] = _date_str(result["trade_date"])
    result["asset_id"] = result["asset_id"].astype(str)
    result["forward_return"] = result.apply(lambda row: end_lookup.get((str(row["trade_date"]), str(row["asset_id"])), np.nan), axis=1)
    result["audit_label"] = ""
    buys = result["action"].astype(str).isin(["buy", "increase"])
    sells = result["action"].astype(str).isin(["sell", "decrease"])
    result.loc[buys & pd.to_numeric(result["forward_return"], errors="coerce").lt(0), "audit_label"] = "bad_buy"
    result.loc[sells & pd.to_numeric(result["forward_return"], errors="coerce").gt(0.02), "audit_label"] = "bad_sell"
    result["strategy_name"] = strategy_name
    return result


def _midtrend_state(row: pd.Series) -> str:
    technical = "T1" if _safe_bool(row.get("technical_confirmed")) else "T0"
    mainline = "M1" if _safe_bool(row.get("mainline_confirmed")) else "M0"
    bucket = str(row.get("fundamental_quality_bucket", "quality_unknown"))
    if bucket == "quality_unknown":
        fundamental = "UNKNOWN_F"
    elif bucket == "quality_weak":
        fundamental = "F0"
    else:
        fundamental = "F1"
    return f"{technical}_{mainline}_{fundamental}"


def _bad_buy_bucket(row: pd.Series) -> str:
    tech = "technical_strong" if bool(row.get("technical_confirmed")) else "technical_weak"
    mainline = "mainline_strong" if bool(row.get("mainline_confirmed")) else "mainline_weak"
    bucket = str(row.get("fundamental_quality_bucket", "quality_unknown"))
    if str(row.get("mid_trend_layer", "")) == "high_elasticity_watch":
        return f"high_elasticity_{bucket}"
    return f"{tech}_{mainline}_{bucket}"


def _growth_asset_map(growth_all: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if growth_all.empty:
        return {}
    growth_all = growth_all.copy()
    growth_all["trade_date"] = _date_str(growth_all["trade_date"])
    growth_all["asset_id"] = growth_all["asset_id"].astype(str)
    if "midtrend_confirmation_state" not in growth_all.columns:
        growth_all["midtrend_confirmation_state"] = "T0_M0_UNKNOWN_F"
    return {str(asset_id): group.sort_values("trade_date").reset_index(drop=True) for asset_id, group in growth_all.groupby("asset_id", sort=False)}


def _previous_best_rank(holdings: pd.DataFrame, asset_id: str, event_date: str) -> float:
    frame = holdings[(holdings["asset_id"].astype(str) == asset_id) & (holdings["trade_date"].astype(str) < event_date)].copy()
    if frame.empty:
        return np.nan
    if "score_rank" not in frame.columns:
        return np.nan
    ranks = pd.to_numeric(frame["score_rank"], errors="coerce").dropna()
    return float(ranks.min()) if not ranks.empty else np.nan


def _price_horizon_max_return(price_state: dict[str, Any], trade_date: str, asset_id: str, horizon: int) -> float:
    group = price_state["by_asset"].get(str(asset_id))
    if group is None or group.empty:
        return np.nan
    start = price_state["date_to_idx"].get(str(asset_id), {}).get(str(trade_date))
    if start is None:
        return np.nan
    end = min(start + int(horizon), len(group) - 1)
    entry = float(group.iloc[start]["close"])
    if entry <= 0:
        return np.nan
    return float(group.iloc[start : end + 1]["close"].max() / entry - 1.0)


def _price_horizon_min_return(price_state: dict[str, Any], trade_date: str, asset_id: str, horizon: int) -> float:
    group = price_state["by_asset"].get(str(asset_id))
    if group is None or group.empty:
        return np.nan
    start = price_state["date_to_idx"].get(str(asset_id), {}).get(str(trade_date))
    if start is None:
        return np.nan
    end = min(start + int(horizon), len(group) - 1)
    entry = float(group.iloc[start]["close"])
    if entry <= 0:
        return np.nan
    return float(group.iloc[start : end + 1]["close"].min() / entry - 1.0)


def _days_to_rank(ranks: np.ndarray, threshold: int) -> float:
    mask = np.isfinite(ranks) & (ranks <= threshold)
    if not mask.any():
        return np.nan
    return float(np.argmax(mask) + 1)


def _days_to_state(states: np.ndarray, prefix: str) -> float:
    if len(states) == 0:
        return np.nan
    mask = np.char.startswith(states.astype(str), prefix)
    if not mask.any():
        return np.nan
    return float(np.argmax(mask) + 1)


def _run_params() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"key": "path_immediate_return_20d", "value": 0.08},
            {"key": "path_immediate_drawdown_10d", "value": -0.05},
            {"key": "path_reacceleration_return_60d", "value": 0.12},
            {"key": "path_true_exit_return_30d", "value": 0.0},
            {"key": "path_true_exit_return_60d", "value": 0.02},
        ]
    )


def _fundamental_missing_report(funnel: pd.DataFrame, path_behavior: pd.DataFrame) -> str:
    candidate_fields = [
        "revenue_growth_yoy",
        "profit_growth_yoy",
        "roe",
        "valuation_percentile",
        "operating_cashflow_quality",
        "financial_risk_flag",
    ]
    missing = [field for field in candidate_fields if field not in funnel.columns]
    unknown_rate = float(path_behavior["fundamental_quality_bucket"].astype(str).eq("quality_unknown").mean()) if not path_behavior.empty else 1.0
    lines = [
        "# Fundamental Missing Fields Report",
        "",
        f"- missing candidate fields: {', '.join(missing) if missing else 'none'}",
        f"- quality_unknown rate in observation pool: {unknown_rate:.4f}",
        "- missing data is treated as `quality_unknown`, never `quality_weak` unless an explicit risk flag exists.",
    ]
    return "\n".join(lines) + "\n"


def _code_audit(funnel: pd.DataFrame, observation_pool: pd.DataFrame) -> str:
    lines = [
        "# Code Audit",
        "",
        "- research-only runner: `stock_research.midtrend_post_exit_fundamental_attribution_v1`",
        "- inputs: v1 baseline artifacts, accepted top10 candidate artifacts, prior sweep/re-entry artifacts when available",
        "- no trading logic is changed; this package only attributes exits, buys, and re-entry failures",
        f"- funnel rows in scope: {len(funnel)}",
        f"- observation rows built: {len(observation_pool)}",
        "- fundamental fields degrade gracefully to `quality_unknown` when missing",
    ]
    return "\n".join(lines) + "\n"


def _final_interpretation(
    path_behavior: pd.DataFrame,
    bad_sell_summary: pd.DataFrame,
    bad_buy_fundamental: pd.DataFrame,
    reentry_path_summary: pd.DataFrame,
    coverage: pd.DataFrame,
) -> str:
    v1 = path_behavior[path_behavior["source_variant"].astype(str).eq("baseline_top5")]
    v2 = path_behavior[path_behavior["source_variant"].astype(str).eq("top10_candidate")]
    continued = path_behavior["continued_winner_flag"].astype(bool).mean() if not path_behavior.empty else 0.0
    continued60 = float(pd.to_numeric(path_behavior.get("forward_return_60d"), errors="coerce").gt(0.1).mean()) if not path_behavior.empty else 0.0
    bad_sell_cont = int(bad_sell_summary[bad_sell_summary["path_class"].astype(str).isin(["immediate_continuation", "pullback_then_reacceleration"])]["count"].sum()) if not bad_sell_summary.empty else 0
    bad_buy_weak = int(bad_buy_fundamental[bad_buy_fundamental["fundamental_quality_bucket"].astype(str).eq("quality_weak")]["count"].sum()) if not bad_buy_fundamental.empty else 0
    unknown_rate = float(coverage[coverage["segment"].eq("all")]["rows_with_any_fundamental_data"].iloc[0] / max(coverage[coverage["segment"].eq("all")]["total_rows"].iloc[0], 1)) if not coverage.empty and "all" in coverage["segment"].values else 0.0
    lines = [
        "# Final Interpretation",
        "",
        f"A1. Among exited/dropped names, continued-winner rate is {continued:.4f}; strong 60d continuation rate is {continued60:.4f}.",
        "A2. Path buckets are in `post_exit_path_bucket_summary.csv` and distinguish immediate continuation, pullback/reacceleration, failed rebound, true exit, and noisy cases.",
        "A3. 60d captures a materially larger continuation set than 10/20/30d whenever pullback_then_reacceleration is non-trivial.",
        f"A4. Top5 vs top10 behavior can be compared directly: baseline_top5 rows={len(v1)}, top10_candidate rows={len(v2)}.",
        "A5. The accepted top10 candidate should reduce misses from pure top_n compression because the selection set is wider before any observation logic is added.",
        f"B6. Bad_sells that continue are currently counted at {bad_sell_cont}.",
        "B7. Continued bad_sells should be checked in `bad_sell_fundamental_attribution.csv` for T1_M1_* concentration.",
        "B8. Ranking churn versus hard damage is separated at the event-type level in the observation pool.",
        "B9. Continued bad_sells vs failed exits can be compared in `continued_winner_vs_failed_exit_comparison.csv`.",
        "B10. Layer and industry effects should be reviewed in the example files rather than turned into rules yet.",
        f"C11. Bad_buys in explicitly fundamental_weak names: {bad_buy_weak}.",
        "C12. Mainline weakness attribution is in `bad_buy_mainline_attribution.csv`.",
        "C13. High-elasticity noise is explicitly surfaced in the bad-buy example outputs.",
        "C14. Some bad_buys may be good names bought early; those are separated in `bad_buy_examples_good_but_early.csv`.",
        "C15. Fundamental quality currently looks more suitable as an entry review lens than an exit/hold rule, pending coverage quality.",
        "D16. Failed re-entries can be tied back to path_class in `reentry_left_tail_path_attribution.csv`.",
        "D17. Fundamental weakness and unknown coverage are separated in `reentry_left_tail_fundamental_attribution.csv`.",
        "D18. Mainline and layer clues should be inspected in the failed/continuation re-entry example files.",
        "D19. Cooldown alone may improve return without fixing left tail if it still admits failed-rebound names.",
        "D20. The separation between true continuation and failed rebound before re-entry remains a research problem, not a strategy conclusion.",
        f"E21. As-of fundamental coverage rate with any core field is {unknown_rate:.4f}.",
        "E22. If `quality_unknown` dominates, conclusions about strategy-ready fundamental filters should stay conservative.",
        "E23. Missing-field priorities are listed in `fundamental_missing_fields_report.md`.",
        "E24. Fundamental quality should remain research-only until coverage is clearly strong enough.",
        "F25. Keep top10 as accepted candidate baseline: yes.",
        "F26. A post-exit observation pool should become a daily review artifact: yes.",
        "F27. Re-entry should remain research-only: yes.",
        "F28. The next experiment should focus on observation-pool alerts and fundamental entry review labels, not broad strategy rewrites.",
        "F29. Explicitly reject generic slow exit, generic carry, and broad ownership hold for now.",
        "",
        "| Recommendation | Status |",
        "| --- | --- |",
        "| top10 candidate baseline | ACCEPT |",
        "| generic slow exit | REJECT |",
        "| generic carry | REJECT |",
        "| broad ownership hold | REJECT |",
        "| strict re-entry | RESEARCH_ONLY |",
        "| fundamental quality as live strategy input | NEED_MORE_DATA |",
    ]
    return "\n".join(lines) + "\n"


def _normalize_frame_dates(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    result = frame.copy()
    if column in result.columns:
        result[column] = _date_str(result[column])
    return result


def _optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _num(value: Any) -> float:
    series = pd.to_numeric(pd.Series([value]), errors="coerce")
    return float(series.iloc[0]) if not pd.isna(series.iloc[0]) else np.nan


def _safe_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    return bool(value)
