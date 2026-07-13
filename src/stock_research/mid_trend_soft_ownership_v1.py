from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SOFT_OWNERSHIP_START_DATE = "2025-01-01"
DEFAULT_SOFT_OWNERSHIP_END_DATE = "2026-06-12"
REFERENCE_BASELINE_DIR = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "research"
    / "current_mid_trend_strategy_v1_20250101_20260612_retest"
)
DEFAULT_REGIME_PATH = (
    "outputs/research/market_regime_confirmation_v1_tight3b_bt100_20230103_20260612_retest/"
    "market_regime_confirmation_daily.csv"
)
DEFAULT_FUNNEL_DETAIL_PATH = (
    "outputs/research/mid_trend_watch_funnel_20250101_20260612_retest/"
    "mid_trend_watch_funnel_detail.csv"
)
META_COLUMNS = [
    "trade_date",
    "asset_id",
    "score_rank",
    "mid_trend_layer",
    "mid_trend_funnel_score",
    "confirmed_regime_state",
    "ret_20_score",
    "ret_60_score",
    "max_drawdown_20_score",
    "stock_excess_ret_20_score",
    "mainline_status",
    "industry_mainline_score_v1",
    "industry_name",
]


@dataclass(frozen=True)
class MidTrendSoftOwnershipConfig:
    variant_name: str
    start_date: str = DEFAULT_SOFT_OWNERSHIP_START_DATE
    end_date: str = DEFAULT_SOFT_OWNERSHIP_END_DATE
    top_n: int = 5
    entry_weak_rank_threshold: int = 20
    entry_extreme_rank_threshold: int = 50
    entry_weak_rank_multiplier: float = 0.7
    entry_weak_regime_multiplier: float = 0.8
    entry_weak_rank_and_regime_multiplier: float = 0.5
    entry_extreme_damage_multiplier: float = 0.1
    ownership_profit_cushion_min: float = 0.08
    ownership_top_rank_memory_threshold: int = 10
    ownership_rank_break_threshold: int = 20
    ownership_damage_rank_threshold: int = 50
    partial_exit_fraction_weak: float = 0.5
    partial_exit_fraction_damage: float = 1.0


def default_soft_ownership_configs() -> dict[str, MidTrendSoftOwnershipConfig]:
    return {
        "baseline": MidTrendSoftOwnershipConfig(variant_name="baseline"),
        "entry_soft_weight_v1": MidTrendSoftOwnershipConfig(variant_name="entry_soft_weight_v1"),
        "ownership_hold_v1": MidTrendSoftOwnershipConfig(variant_name="ownership_hold_v1"),
        "partial_exit_v1": MidTrendSoftOwnershipConfig(variant_name="partial_exit_v1"),
        "combined_soft_ownership_v1": MidTrendSoftOwnershipConfig(
            variant_name="combined_soft_ownership_v1"
        ),
    }


def compare_baseline_to_reference(
    rerun: dict[str, pd.DataFrame],
    *,
    reference_dir: str | Path = REFERENCE_BASELINE_DIR,
    equity_tolerance: float = 1e-9,
    summary_tolerance: float = 1e-9,
) -> dict[str, object]:
    reference_path = Path(reference_dir)
    equity_ref = pd.read_csv(
        reference_path / "current_mid_trend_strategy_v1_equity.csv",
        low_memory=False,
    )
    holdings_ref = pd.read_csv(
        reference_path / "current_mid_trend_strategy_v1_daily_holdings.csv",
        low_memory=False,
    )
    trades_ref = pd.read_csv(
        reference_path / "current_mid_trend_strategy_v1_trade_changes.csv",
        low_memory=False,
    )
    summary_ref = pd.read_csv(
        reference_path / "current_mid_trend_strategy_v1_summary.csv",
        low_memory=False,
    )
    rerun_equity = rerun["equity"].copy()
    rerun_summary = rerun["summary"].copy()
    merged = rerun_equity[["trade_date", "equity"]].merge(
        equity_ref[["trade_date", "equity"]],
        on="trade_date",
        how="outer",
        suffixes=("_rerun", "_reference"),
    ).sort_values("trade_date")
    merged["abs_diff"] = (
        pd.to_numeric(merged["equity_rerun"], errors="coerce")
        - pd.to_numeric(merged["equity_reference"], errors="coerce")
    ).abs()
    final_equity_diff = (
        float(rerun_equity["equity"].iloc[-1]) - float(equity_ref["equity"].iloc[-1])
        if not rerun_equity.empty and not equity_ref.empty
        else float("nan")
    )
    total_return_diff = float(rerun_summary["total_return"].iloc[0]) - float(
        summary_ref["total_return"].iloc[0]
    )
    max_drawdown_diff = float(rerun_summary["max_drawdown"].iloc[0]) - float(
        summary_ref["max_drawdown"].iloc[0]
    )
    holdings_row_diff = int(len(rerun["holdings"])) - int(len(holdings_ref))
    trades_row_diff = int(len(rerun["trades"])) - int(len(trades_ref))
    baseline_match = (
        abs(final_equity_diff) <= equity_tolerance
        and abs(total_return_diff) <= summary_tolerance
        and abs(max_drawdown_diff) <= summary_tolerance
        and holdings_row_diff == 0
        and trades_row_diff == 0
        and float(merged["abs_diff"].fillna(0.0).max()) <= equity_tolerance
    )
    return {
        "baseline_match": baseline_match,
        "holdings_row_diff": holdings_row_diff,
        "trades_row_diff": trades_row_diff,
        "final_equity_diff": final_equity_diff,
        "total_return_diff": total_return_diff,
        "max_drawdown_diff": max_drawdown_diff,
        "equity_series_max_abs_diff": float(merged["abs_diff"].fillna(0.0).max()),
        "equity_series_diff": merged,
    }


def build_daily_meta_lookup(funnel: pd.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    frame = funnel.copy()
    for column in META_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    frame["asset_id"] = frame["asset_id"].astype(str)
    return {
        (str(row["trade_date"]), str(row["asset_id"])): row
        for row in frame[META_COLUMNS]
        .dropna(subset=["trade_date", "asset_id"])
        .drop_duplicates(["trade_date", "asset_id"], keep="last")
        .to_dict("records")
    }


def resolve_asset_day_meta(
    meta_lookup: dict[tuple[str, str], dict[str, object]],
    *,
    trade_date: str,
    asset_id: str,
) -> dict[str, object]:
    row = dict(meta_lookup.get((str(trade_date), str(asset_id)), {}))
    if row:
        row["missing_meta_state"] = ""
        return row
    result = {column: pd.NA for column in META_COLUMNS}
    result["trade_date"] = trade_date
    result["asset_id"] = asset_id
    result["missing_meta_state"] = "missing_meta_state"
    return result


def _entry_soft_weight_rule(
    row: pd.Series,
    config: MidTrendSoftOwnershipConfig,
) -> tuple[float, str]:
    score_rank = pd.to_numeric(pd.Series([row.get("score_rank")]), errors="coerce").iloc[0]
    max_drawdown_score = pd.to_numeric(
        pd.Series([row.get("max_drawdown_20_score")]), errors="coerce"
    ).iloc[0]
    excess_score = pd.to_numeric(
        pd.Series([row.get("stock_excess_ret_20_score")]), errors="coerce"
    ).iloc[0]
    weak_rank = pd.notna(score_rank) and (
        float(score_rank) > float(config.entry_weak_rank_threshold)
        or (
            float(score_rank) > 10.0
            and str(row.get("mid_trend_layer")) == "high_elasticity_watch"
        )
    )
    weak_regime = _text(row.get("confirmed_regime_state")) in {
        "overheated",
        "trend_decay",
    }
    extreme_damage = (
        pd.notna(score_rank)
        and float(score_rank) > float(config.entry_extreme_rank_threshold)
        and weak_regime
        and (
            (pd.notna(max_drawdown_score) and float(max_drawdown_score) < 45.0)
            or (pd.notna(excess_score) and float(excess_score) < 40.0)
        )
    )
    if extreme_damage:
        return config.entry_extreme_damage_multiplier, "extreme_damage"
    if weak_rank and weak_regime:
        return (
            config.entry_weak_rank_and_regime_multiplier,
            "weak_rank_and_weak_regime",
        )
    if weak_rank:
        return config.entry_weak_rank_multiplier, "weak_rank_only"
    if weak_regime:
        return config.entry_weak_regime_multiplier, "weak_regime_only"
    return 1.0, "normal"


def apply_entry_soft_weight(
    day: pd.DataFrame,
    *,
    config: MidTrendSoftOwnershipConfig,
) -> pd.DataFrame:
    frame = day.copy()
    frame["entry_weight_multiplier"] = 1.0
    frame["entry_soft_reason"] = "normal"
    for index, row in frame.iterrows():
        multiplier, reason = _entry_soft_weight_rule(row, config)
        frame.at[index, "entry_weight_multiplier"] = multiplier
        frame.at[index, "entry_soft_reason"] = reason
    base_weight = pd.to_numeric(frame["base_target_weight"], errors="coerce").fillna(0.0)
    multiplier = pd.to_numeric(frame["entry_weight_multiplier"], errors="coerce").fillna(1.0)
    frame["adjusted_target_weight"] = (base_weight * multiplier).round(10)
    frame["released_to_cash"] = (
        base_weight - frame["adjusted_target_weight"]
    ).clip(lower=0.0).round(10)
    return frame


def evaluate_ownership_state(
    *,
    meta: dict[str, object],
    prior_best_rank: int | None,
    profit_cushion: float,
    atr_damage: bool,
    repeated_rank_break: bool,
    config: MidTrendSoftOwnershipConfig,
) -> dict[str, object]:
    score_rank = pd.to_numeric(pd.Series([meta.get("score_rank")]), errors="coerce").iloc[0]
    layer = _text(meta.get("mid_trend_layer"))
    drawdown_score = pd.to_numeric(
        pd.Series([meta.get("max_drawdown_20_score")]), errors="coerce"
    ).iloc[0]
    excess_score = pd.to_numeric(
        pd.Series([meta.get("stock_excess_ret_20_score")]), errors="coerce"
    ).iloc[0]
    no_cushion = profit_cushion <= 0.0
    confirmed_damage = bool(
        atr_damage
        or layer == "risk_exclusion_watch"
        or repeated_rank_break
        or (
            pd.notna(drawdown_score)
            and pd.notna(excess_score)
            and float(drawdown_score) < 35.0
            and float(excess_score) < 35.0
        )
        or (
            no_cushion
            and pd.notna(score_rank)
            and float(score_rank) > float(config.ownership_rank_break_threshold)
        )
    )
    if prior_best_rank is not None and prior_best_rank <= config.ownership_top_rank_memory_threshold:
        rank_memory_state = "front_rank_memory"
    elif prior_best_rank is not None and prior_best_rank <= 20:
        rank_memory_state = "secondary_rank_memory"
    else:
        rank_memory_state = "no_rank_memory"
    if profit_cushion >= config.ownership_profit_cushion_min:
        profit_cushion_state = "cushion_strong"
    elif profit_cushion > 0:
        profit_cushion_state = "cushion_small"
    else:
        profit_cushion_state = "no_cushion"
    if confirmed_damage:
        return {
            "ownership_state": "ownership_broken",
            "ownership_reason": "confirmed_damage",
            "rank_memory_state": rank_memory_state,
            "profit_cushion_state": profit_cushion_state,
            "damage_state": "confirmed_damage",
            "confirmed_damage_flag": True,
        }
    if (
        pd.notna(score_rank)
        and float(score_rank) <= 10.0
        and layer in {"stable_trend_watch", "mainline_momentum_watch"}
    ):
        state = "owned_strong"
    elif rank_memory_state == "front_rank_memory" and profit_cushion > 0:
        state = "owned_noisy_but_valid"
    else:
        state = "owned_weak"
    return {
        "ownership_state": state,
        "ownership_reason": state,
        "rank_memory_state": rank_memory_state,
        "profit_cushion_state": profit_cushion_state,
        "damage_state": "soft_damage" if state == "owned_weak" else "none",
        "confirmed_damage_flag": False,
    }


def determine_exit_action(
    *,
    variant_name: str,
    baseline_exit_signal: bool,
    ownership_state: str,
    confirmed_damage: bool,
    current_weight: float,
    reduce_fraction: float,
) -> dict[str, object]:
    if not baseline_exit_signal:
        return {
            "exit_action": "hold",
            "exit_fraction": 0.0,
            "target_weight_after_exit": current_weight,
            "whether_exit_was_suppressed_by_ownership": False,
        }
    if confirmed_damage:
        return {
            "exit_action": "full_exit",
            "exit_fraction": 1.0,
            "target_weight_after_exit": 0.0,
            "whether_exit_was_suppressed_by_ownership": False,
        }
    if variant_name == "partial_exit_v1":
        next_weight = current_weight * (1.0 - reduce_fraction)
        return {
            "exit_action": "reduce",
            "exit_fraction": reduce_fraction,
            "target_weight_after_exit": next_weight,
            "whether_exit_was_suppressed_by_ownership": False,
        }
    if variant_name in {"ownership_hold_v1", "combined_soft_ownership_v1"} and ownership_state in {
        "owned_strong",
        "owned_noisy_but_valid",
    }:
        return {
            "exit_action": "hold",
            "exit_fraction": 0.0,
            "target_weight_after_exit": current_weight,
            "whether_exit_was_suppressed_by_ownership": True,
        }
    if variant_name == "combined_soft_ownership_v1" and ownership_state == "owned_weak":
        next_weight = current_weight * (1.0 - reduce_fraction)
        return {
            "exit_action": "reduce",
            "exit_fraction": reduce_fraction,
            "target_weight_after_exit": next_weight,
            "whether_exit_was_suppressed_by_ownership": False,
        }
    return {
        "exit_action": "full_exit",
        "exit_fraction": 1.0,
        "target_weight_after_exit": 0.0,
        "whether_exit_was_suppressed_by_ownership": False,
    }


def run_mid_trend_soft_ownership_experiment(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    baseline_result: dict[str, pd.DataFrame],
    baseline_reference_check: dict[str, object],
    funnel: pd.DataFrame,
    regime: pd.DataFrame,
    prices: pd.DataFrame,
    variants: list[str],
) -> dict[str, object]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    code_audit_path = output / "code_audit.md"
    baseline_vs_variants_csv = output / "baseline_vs_variants.csv"
    baseline_vs_variants_md = output / "baseline_vs_variants.md"
    trade_level_path = output / "trade_level_diagnostics.csv"
    ownership_path = output / "ownership_event_diagnostics.csv"
    exit_path = output / "exit_event_diagnostics.csv"
    bucket_path = output / "bucket_contribution_entry_weight.csv"
    suppressed_path = output / "suppressed_exit_analysis.csv"
    baseline_diff_path = output / "baseline_diff_report.md"
    interpretation_path = output / "final_interpretation.md"

    code_audit_path.write_text(
        _build_code_audit_markdown(start_date=start_date, end_date=end_date),
        encoding="utf-8",
    )
    if not bool(baseline_reference_check["baseline_match"]):
        _write_baseline_diff_report(baseline_reference_check, baseline_diff_path)
        interpretation_path.write_text(
            "# Final Interpretation\n\nBaseline mismatch. Variant conclusions are invalid.\n",
            encoding="utf-8",
        )
        raise RuntimeError(f"Baseline reproduction mismatch; see {baseline_diff_path}")

    baseline_holdings = _normalize_holdings_frame(baseline_result.get("holdings", pd.DataFrame()))
    price_frame = _normalize_price_frame(prices)
    meta_lookup = build_daily_meta_lookup(funnel)
    baseline_artifact = _build_baseline_artifact(
        variant_name="baseline",
        holdings=baseline_holdings,
        prices=price_frame,
    )

    artifacts: list[dict[str, Any]] = [baseline_artifact]
    configs = default_soft_ownership_configs()
    for variant_name in variants:
        if variant_name == "baseline":
            continue
        config = configs.get(variant_name)
        if config is None:
            continue
        artifacts.append(
            _simulate_variant(
                variant_name=variant_name,
                config=config,
                baseline_holdings=baseline_holdings,
                meta_lookup=meta_lookup,
                prices=price_frame,
            )
        )

    summary_rows = []
    trade_rows = []
    ownership_rows = []
    exit_rows = []
    bucket_rows = []
    suppressed_rows = []
    for artifact in artifacts:
        summary_row = summarize_variant_metrics(
            artifact["variant_name"],
            equity=artifact["equity"],
            trades=artifact["trade_episodes"],
            audit_detail=artifact["audit_detail"],
        )
        if artifact["variant_name"] == "baseline":
            summary_row["baseline_match"] = True
        summary_rows.append(summary_row)
        trade_rows.append(artifact["audit_detail"])
        ownership_rows.append(artifact["ownership_events"])
        exit_rows.append(artifact["exit_events"])
        bucket_rows.append(artifact["entry_bucket"])
        suppressed_rows.append(artifact["suppressed_summary"])

    summary = pd.DataFrame(summary_rows)
    trade_level = _concat_frames(trade_rows)
    ownership_detail = _concat_frames(ownership_rows)
    exit_detail = _concat_frames(exit_rows)
    bucket_detail = _concat_frames(bucket_rows)
    suppressed_detail = _concat_frames(suppressed_rows)

    summary.to_csv(baseline_vs_variants_csv, index=False)
    baseline_vs_variants_md.write_text(summary.to_markdown(index=False) + "\n", encoding="utf-8")
    trade_level.to_csv(trade_level_path, index=False)
    ownership_detail.to_csv(ownership_path, index=False)
    exit_detail.to_csv(exit_path, index=False)
    bucket_detail.to_csv(bucket_path, index=False)
    suppressed_detail.to_csv(suppressed_path, index=False)
    interpretation_path.write_text(
        _build_final_interpretation(summary, suppressed_detail),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "paths": {
            "code_audit": str(code_audit_path),
            "baseline_vs_variants_csv": str(baseline_vs_variants_csv),
            "baseline_vs_variants_md": str(baseline_vs_variants_md),
            "trade_level_diagnostics": str(trade_level_path),
            "ownership_event_diagnostics": str(ownership_path),
            "exit_event_diagnostics": str(exit_path),
            "bucket_contribution_entry_weight": str(bucket_path),
            "suppressed_exit_analysis": str(suppressed_path),
            "baseline_diff_report": str(baseline_diff_path),
            "final_interpretation": str(interpretation_path),
        },
    }


def run_mid_trend_soft_ownership_cli(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    variants: list[str] | None = None,
    regime_path: str | Path = DEFAULT_REGIME_PATH,
    funnel_detail_path: str | Path = DEFAULT_FUNNEL_DETAIL_PATH,
    baseline_reference_dir: str | Path = REFERENCE_BASELINE_DIR,
) -> dict[str, object]:
    from stock_research.current_mid_trend_strategy_v1 import (
        load_current_strategy_prices,
        run_current_mid_trend_strategy_v1_backtest,
    )

    baseline_output_dir = Path(output_dir) / "baseline_rerun"
    baseline_result = run_current_mid_trend_strategy_v1_backtest(
        start_date=start_date,
        end_date=end_date,
        regime_path=regime_path,
        funnel_detail_path=funnel_detail_path,
        output_dir=baseline_output_dir,
        top_n=5,
        adjust_type="hfq",
    )
    baseline_reference_check = compare_baseline_to_reference(
        baseline_result,
        reference_dir=baseline_reference_dir,
    )
    regime = pd.read_csv(regime_path, low_memory=False)
    funnel = pd.read_csv(funnel_detail_path, low_memory=False)
    price_asset_ids = sorted(
        funnel.loc[
            pd.to_datetime(funnel["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").between(
                start_date,
                end_date,
            ),
            "asset_id",
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    prices = load_current_strategy_prices(
        start_date,
        end_date,
        asset_ids=price_asset_ids,
        adjust_type="hfq",
    )
    return run_mid_trend_soft_ownership_experiment(
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        baseline_result=baseline_result,
        baseline_reference_check=baseline_reference_check,
        funnel=funnel,
        regime=regime,
        prices=prices,
        variants=variants or list(default_soft_ownership_configs()),
    )


def summarize_variant_metrics(
    variant_name: str,
    *,
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    audit_detail: pd.DataFrame,
) -> dict[str, object]:
    equity_frame = equity.copy()
    exposure = pd.Series(dtype=float)
    daily_returns = pd.Series(dtype=float)
    if equity_frame.empty:
        average_exposure = 0.0
        cash_weight_avg = 1.0
        min_exposure = 0.0
        max_exposure = 0.0
        return_per_unit_exposure = 0.0
        total_return = 0.0
        annualized_return = 0.0
        max_drawdown = 0.0
        sharpe_ratio = 0.0
    else:
        exposure = pd.to_numeric(
            equity_frame.get("invested_weight", pd.Series(dtype=float)), errors="coerce"
        ).fillna(0.0)
        daily_returns = pd.to_numeric(
            equity_frame.get("daily_return", pd.Series(dtype=float)), errors="coerce"
        ).fillna(0.0)
        average_exposure = float(exposure.mean()) if not exposure.empty else 0.0
        cash_weight_avg = float((1.0 - exposure).mean()) if not exposure.empty else 1.0
        min_exposure = float(exposure.min()) if not exposure.empty else 0.0
        max_exposure = float(exposure.max()) if not exposure.empty else 0.0
        equity_curve = pd.to_numeric(equity_frame.get("equity"), errors="coerce").dropna()
        total_return = float(equity_curve.iloc[-1] - 1.0) if not equity_curve.empty else 0.0
        annualized_return = (
            (1.0 + total_return) ** (252.0 / max(len(equity_curve), 1)) - 1.0
            if total_return > -1.0
            else -1.0
        )
        if not equity_curve.empty:
            running_max = equity_curve.cummax()
            max_drawdown = float((equity_curve / running_max - 1.0).min())
        else:
            max_drawdown = 0.0
        sharpe_ratio = (
            float(daily_returns.mean() / daily_returns.std(ddof=1) * (252.0**0.5))
            if len(daily_returns) > 1 and float(daily_returns.std(ddof=1)) > 0.0
            else 0.0
        )
        return_per_unit_exposure = total_return / max(average_exposure, 1e-12)

    trade_pnl = pd.to_numeric(trades.get("pnl", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    winning_trades = trade_pnl[trade_pnl > 0]
    losing_trades = trade_pnl[trade_pnl < 0]
    trade_count = int(len(trades))
    win_rate = float((trade_pnl > 0).mean()) if trade_count else 0.0
    avg_winner = float(winning_trades.mean()) if not winning_trades.empty else 0.0
    avg_loser = float(losing_trades.mean()) if not losing_trades.empty else 0.0
    profit_factor = (
        float(winning_trades.sum() / abs(losing_trades.sum()))
        if not winning_trades.empty and not losing_trades.empty and abs(losing_trades.sum()) > 0
        else 0.0
    )
    top_10_winners_contribution = (
        float(trade_pnl.sort_values(ascending=False).head(10).sum()) if not trade_pnl.empty else 0.0
    )
    top_20_winners_contribution = (
        float(trade_pnl.sort_values(ascending=False).head(20).sum()) if not trade_pnl.empty else 0.0
    )
    left_tail_10_losers_contribution = (
        float(trade_pnl.sort_values(ascending=True).head(10).sum()) if not trade_pnl.empty else 0.0
    )
    bad_buy_count = int(
        pd.Series(audit_detail.get("audit_label", pd.Series(dtype=object)))
        .astype(str)
        .eq("bad_buy")
        .sum()
    )
    bad_sell_count = int(
        pd.Series(audit_detail.get("audit_label", pd.Series(dtype=object)))
        .astype(str)
        .eq("bad_sell")
        .sum()
    )
    issue_rate = (bad_buy_count + bad_sell_count) / max(int(len(audit_detail)), 1)
    return {
        "variant_name": variant_name,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "win_rate": win_rate,
        "avg_winner": avg_winner,
        "avg_loser": avg_loser,
        "profit_factor": profit_factor,
        "total_trades": trade_count,
        "turnover": float(pd.to_numeric(audit_detail.get("abs_delta_weight"), errors="coerce").sum())
        if not audit_detail.empty
        else float(exposure.sum()) if not exposure.empty else 0.0,
        "avg_holding_days": float(
            pd.to_numeric(trades.get("holding_days", pd.Series(dtype=float)), errors="coerce").mean()
        )
        if trade_count
        else 0.0,
        "median_holding_days": float(
            pd.to_numeric(trades.get("holding_days", pd.Series(dtype=float)), errors="coerce").median()
        )
        if trade_count
        else 0.0,
        "top_10_winners_contribution": top_10_winners_contribution,
        "top_20_winners_contribution": top_20_winners_contribution,
        "left_tail_10_losers_contribution": left_tail_10_losers_contribution,
        "bad_buy_count": bad_buy_count,
        "bad_buy_rate": bad_buy_count / max(int(len(audit_detail)), 1),
        "bad_sell_count": bad_sell_count,
        "bad_sell_rate": bad_sell_count / max(int(len(audit_detail)), 1),
        "issue_rate": issue_rate,
        "average_exposure": average_exposure,
        "cash_weight_avg": cash_weight_avg,
        "min_exposure": min_exposure,
        "max_exposure": max_exposure,
        "return_per_unit_exposure": return_per_unit_exposure,
    }


def _build_baseline_artifact(
    *,
    variant_name: str,
    holdings: pd.DataFrame,
    prices: pd.DataFrame,
) -> dict[str, Any]:
    forward_lookup = _build_forward_return_lookup(prices)
    daily_holdings = holdings.copy()
    daily_holdings["variant_name"] = variant_name
    daily_holdings["entry_weight_multiplier"] = 1.0
    daily_holdings["entry_soft_reason"] = "baseline"
    daily_holdings["ownership_state"] = "baseline"
    daily_holdings["ownership_reason"] = "baseline"
    daily_holdings["rank_memory_state"] = ""
    daily_holdings["profit_cushion_state"] = ""
    daily_holdings["damage_state"] = ""
    daily_holdings["whether_exit_was_suppressed_by_ownership"] = False
    equity = _equity_from_weights(daily_holdings, prices, variant_name=variant_name)
    trades = _build_trade_changes_from_weights(daily_holdings, variant_name=variant_name)
    audit_detail = _build_trade_audit_detail(trades, forward_lookup)
    episodes = _build_trade_episodes(daily_holdings, prices, variant_name=variant_name)
    return {
        "variant_name": variant_name,
        "holdings": daily_holdings,
        "equity": equity,
        "audit_detail": audit_detail,
        "trade_episodes": episodes,
        "ownership_events": pd.DataFrame(columns=_ownership_columns()),
        "exit_events": pd.DataFrame(columns=_exit_columns()),
        "entry_bucket": _entry_bucket_summary(episodes, variant_name=variant_name),
        "suppressed_summary": _suppressed_summary(pd.DataFrame(), variant_name=variant_name),
    }


def _simulate_variant(
    *,
    variant_name: str,
    config: MidTrendSoftOwnershipConfig,
    baseline_holdings: pd.DataFrame,
    meta_lookup: dict[tuple[str, str], dict[str, object]],
    prices: pd.DataFrame,
) -> dict[str, Any]:
    forward_lookup = _build_forward_return_lookup(prices)
    price_lookup = {
        (str(row.trade_date), str(row.asset_id)): row
        for row in prices.itertuples(index=False)
    }
    trade_dates = sorted(
        set(
            baseline_holdings["trade_date"].dropna().astype(str).unique().tolist()
        )
        & set(prices["trade_date"].dropna().astype(str).unique().tolist())
    )
    day_candidates = {
        trade_date: frame.copy()
        for trade_date, frame in baseline_holdings.groupby("trade_date", sort=True)
    }
    positions: dict[str, dict[str, Any]] = {}
    holding_rows: list[dict[str, Any]] = []
    ownership_rows: list[dict[str, Any]] = []
    exit_rows: list[dict[str, Any]] = []
    suppressed_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    previous_weights: dict[str, float] = {}

    for trade_date in trade_dates:
        baseline_day = day_candidates.get(trade_date, pd.DataFrame()).copy()
        baseline_day = baseline_day[
            baseline_day["asset_id"].notna() & pd.to_numeric(baseline_day["target_weight"], errors="coerce").gt(0.0)
        ].copy()
        baseline_day["asset_id"] = baseline_day["asset_id"].astype(str)
        baseline_asset_ids = set(baseline_day["asset_id"].tolist())
        target_rows: dict[str, dict[str, Any]] = {}
        current_asset_ids = set(positions)
        current_day_rows: list[dict[str, Any]] = []
        carry_reserved_weight = 0.0

        for row in baseline_day.to_dict("records"):
            asset_id = str(row["asset_id"])
            base_target_weight = _to_float(row.get("target_weight"))
            record = dict(row)
            record["base_target_weight"] = base_target_weight
            record["entry_weight_multiplier"] = 1.0
            record["entry_soft_reason"] = "normal"
            if asset_id not in positions and variant_name in {
                "entry_soft_weight_v1",
                "combined_soft_ownership_v1",
            }:
                entry_row = apply_entry_soft_weight(pd.DataFrame([record]), config=config).iloc[0].to_dict()
                record["entry_weight_multiplier"] = float(entry_row["entry_weight_multiplier"])
                record["entry_soft_reason"] = str(entry_row["entry_soft_reason"])
                record["target_weight"] = float(entry_row["adjusted_target_weight"])
            target_rows[asset_id] = record

        carry_assets = sorted(current_asset_ids - baseline_asset_ids)
        for asset_id in carry_assets:
            position = positions.get(asset_id)
            if position is None:
                continue
            current_weight = _to_float(previous_weights.get(asset_id))
            meta = resolve_asset_day_meta(meta_lookup, trade_date=trade_date, asset_id=asset_id)
            current_close = _current_close(price_lookup, trade_date, asset_id)
            entry_close = _to_float(position.get("entry_close"), current_close)
            highest_close = max(_to_float(position.get("highest_close"), current_close), current_close)
            position["highest_close"] = highest_close
            atr_value = _lookup_price_field(price_lookup, trade_date, asset_id, "atr20")
            atr_damage = bool(
                atr_value > 0.0 and current_close <= max(highest_close - 2.5 * atr_value, 0.0)
            )
            current_rank = _to_int(meta.get("score_rank"))
            if current_rank is not None:
                position["rank_break_streak"] = (
                    int(position.get("rank_break_streak", 0)) + 1
                    if current_rank > config.ownership_damage_rank_threshold
                    else 0
                )
                prior_best_rank = position.get("prior_best_rank")
                position["prior_best_rank"] = (
                    current_rank
                    if prior_best_rank is None
                    else min(int(prior_best_rank), current_rank)
                )
            profit_cushion = (current_close / entry_close - 1.0) if entry_close > 0 else 0.0
            ownership = evaluate_ownership_state(
                meta=meta,
                prior_best_rank=_to_int(position.get("prior_best_rank")),
                profit_cushion=profit_cushion,
                atr_damage=atr_damage,
                repeated_rank_break=int(position.get("rank_break_streak", 0)) >= 2,
                config=config,
            )
            exit_decision = determine_exit_action(
                variant_name=variant_name,
                baseline_exit_signal=True,
                ownership_state=str(ownership["ownership_state"]),
                confirmed_damage=bool(ownership["confirmed_damage_flag"]),
                current_weight=current_weight,
                reduce_fraction=config.partial_exit_fraction_weak,
            )
            target_weight = _to_float(exit_decision["target_weight_after_exit"])
            base_row = {
                "trade_date": trade_date,
                "asset_id": asset_id,
                "confirmed_regime_state": meta.get("confirmed_regime_state", ""),
                "stock_name": "",
                "industry_name": meta.get("industry_name", ""),
                "mid_trend_funnel_score": meta.get("mid_trend_funnel_score", pd.NA),
                "score_rank": meta.get("score_rank", pd.NA),
                "mid_trend_layer": meta.get("mid_trend_layer", ""),
                "mainline_status": meta.get("mainline_status", ""),
                "industry_mainline_score_v1": meta.get("industry_mainline_score_v1", pd.NA),
                "ret_20_score": meta.get("ret_20_score", pd.NA),
                "ret_60_score": meta.get("ret_60_score", pd.NA),
                "max_drawdown_20_score": meta.get("max_drawdown_20_score", pd.NA),
                "atr_pct_score": pd.NA,
                "stock_excess_ret_20_score": meta.get("stock_excess_ret_20_score", pd.NA),
                "cash_weight": pd.NA,
            }
            if target_weight > 0.0:
                carry_reserved_weight += target_weight
                _append_holding_row(
                    current_day_rows,
                    variant_name=variant_name,
                    trade_date=trade_date,
                    asset_id=asset_id,
                    source_row=base_row,
                    target_weight=target_weight,
                    ownership_state=str(ownership["ownership_state"]),
                    ownership_reason=str(ownership["ownership_reason"]),
                    rank_memory_state=str(ownership["rank_memory_state"]),
                    profit_cushion_state=str(ownership["profit_cushion_state"]),
                    damage_state=str(ownership["damage_state"]),
                    suppressed=bool(exit_decision["whether_exit_was_suppressed_by_ownership"]),
                    entry_weight_multiplier=1.0,
                    entry_soft_reason="carry",
                )
            ownership_rows.append(
                {
                    "variant_name": variant_name,
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "ownership_state": ownership["ownership_state"],
                    "ownership_reason": ownership["ownership_reason"],
                    "rank_memory_state": ownership["rank_memory_state"],
                    "profit_cushion_state": ownership["profit_cushion_state"],
                    "damage_state": ownership["damage_state"],
                    "whether_exit_was_suppressed_by_ownership": bool(
                        exit_decision["whether_exit_was_suppressed_by_ownership"]
                    ),
                    "missing_meta_state": meta.get("missing_meta_state", ""),
                }
            )
            exit_rows.append(
                {
                    "variant_name": variant_name,
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "exit_action": exit_decision["exit_action"],
                    "exit_fraction": exit_decision["exit_fraction"],
                    "exit_reason": ownership["ownership_reason"],
                    "confirmed_damage_flag": bool(ownership["confirmed_damage_flag"]),
                    "ownership_state": ownership["ownership_state"],
                    "score_rank": meta.get("score_rank", pd.NA),
                    "confirmed_regime_state": meta.get("confirmed_regime_state", ""),
                    "mid_trend_layer": meta.get("mid_trend_layer", ""),
                    "pnl_before_exit": profit_cushion,
                    "forward_return_after_exit": forward_lookup.get(
                        (trade_date, asset_id),
                        float("nan"),
                    ),
                }
            )
            if bool(exit_decision["whether_exit_was_suppressed_by_ownership"]):
                suppressed_rows.append(
                    {
                        "variant_name": variant_name,
                        "trade_date": trade_date,
                        "asset_id": asset_id,
                        "suppressed_exit_flag": True,
                        "forward_return_after_suppressed_exit": forward_lookup.get(
                            (trade_date, asset_id),
                            float("nan"),
                        ),
                    }
                )
            if target_weight <= 0.0:
                positions.pop(asset_id, None)

        remaining_budget = max(0.0, 1.0 - carry_reserved_weight)
        selected_order = sorted(
            baseline_asset_ids,
            key=lambda asset_id: (
                0 if asset_id in positions else 1,
                _to_int(target_rows[asset_id].get("score_rank")) or 999999,
                asset_id,
            ),
        )
        for asset_id in selected_order:
            record = target_rows[asset_id]
            proposed_weight = min(_to_float(record.get("target_weight")), remaining_budget)
            remaining_budget = max(0.0, remaining_budget - proposed_weight)
            if proposed_weight <= 0.0:
                if asset_id in positions:
                    positions.pop(asset_id, None)
                continue
            current_price = _current_close(price_lookup, trade_date, asset_id)
            if asset_id not in positions:
                positions[asset_id] = {
                    "entry_date": trade_date,
                    "entry_close": current_price,
                    "highest_close": current_price,
                    "prior_best_rank": _to_int(record.get("score_rank")),
                    "rank_break_streak": 1
                    if _to_int(record.get("score_rank"))
                    and _to_int(record.get("score_rank")) > config.ownership_damage_rank_threshold
                    else 0,
                }
            else:
                positions[asset_id]["highest_close"] = max(
                    _to_float(positions[asset_id].get("highest_close"), current_price),
                    current_price,
                )
                current_rank = _to_int(record.get("score_rank"))
                prior_best_rank = positions[asset_id].get("prior_best_rank")
                if current_rank is not None:
                    positions[asset_id]["prior_best_rank"] = (
                        current_rank
                        if prior_best_rank is None
                        else min(int(prior_best_rank), current_rank)
                    )
                    positions[asset_id]["rank_break_streak"] = (
                        int(positions[asset_id].get("rank_break_streak", 0)) + 1
                        if current_rank > config.ownership_damage_rank_threshold
                        else 0
                    )
            _append_holding_row(
                current_day_rows,
                variant_name=variant_name,
                trade_date=trade_date,
                asset_id=asset_id,
                source_row=record,
                target_weight=proposed_weight,
                ownership_state="entry_or_selected",
                ownership_reason="selected_in_baseline",
                rank_memory_state="",
                profit_cushion_state="",
                damage_state="",
                suppressed=False,
                entry_weight_multiplier=_to_float(record.get("entry_weight_multiplier"), 1.0),
                entry_soft_reason=_text(record.get("entry_soft_reason")) or "normal",
            )

        cash_weight = max(0.0, 1.0 - sum(_to_float(row.get("target_weight")) for row in current_day_rows))
        for row in current_day_rows:
            row["cash_weight"] = cash_weight
        current_weights = {
            row["asset_id"]: _to_float(row.get("target_weight"))
            for row in current_day_rows
            if _to_float(row.get("target_weight")) > 0.0
        }
        holding_rows.extend(current_day_rows)
        trade_rows.extend(
            _trade_rows_from_weight_delta(
                variant_name=variant_name,
                trade_date=trade_date,
                previous_weights=previous_weights,
                current_weights=current_weights,
                day_rows=current_day_rows,
            )
        )
        previous_weights = current_weights

    daily_holdings = pd.DataFrame(holding_rows)
    if not daily_holdings.empty:
        daily_holdings = daily_holdings[
            pd.to_numeric(daily_holdings["target_weight"], errors="coerce").gt(0.0)
        ].reset_index(drop=True)
    equity = _equity_from_weights(daily_holdings, prices, variant_name=variant_name)
    trade_detail = pd.DataFrame(trade_rows)
    audit_detail = _build_trade_audit_detail(trade_detail, forward_lookup)
    trade_episodes = _build_trade_episodes(daily_holdings, prices, variant_name=variant_name)
    return {
        "variant_name": variant_name,
        "holdings": daily_holdings,
        "equity": equity,
        "audit_detail": audit_detail,
        "trade_episodes": trade_episodes,
        "ownership_events": pd.DataFrame(ownership_rows, columns=_ownership_columns()),
        "exit_events": pd.DataFrame(exit_rows, columns=_exit_columns()),
        "entry_bucket": _entry_bucket_summary(trade_episodes, variant_name=variant_name),
        "suppressed_summary": _suppressed_summary(pd.DataFrame(suppressed_rows), variant_name=variant_name),
    }


def _normalize_holdings_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    result["asset_id"] = result["asset_id"].astype(str)
    result["target_weight"] = pd.to_numeric(result["target_weight"], errors="coerce").fillna(0.0)
    return result[result["asset_id"].ne("nan") & result["trade_date"].notna()].reset_index(drop=True)


def _normalize_price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    from stock_research.mid_trend_stock_protection_v1 import compute_atr20

    result = frame.copy()
    if result.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "close", "next_return", "atr20"])
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    result["asset_id"] = result["asset_id"].astype(str)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    for column in ["high", "low"]:
        if column not in result.columns:
            result[column] = result["close"]
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=["trade_date", "asset_id", "close"]).sort_values(
        ["asset_id", "trade_date"]
    )
    result["next_close"] = result.groupby("asset_id")["close"].shift(-1)
    result["next_return"] = result["next_close"] / result["close"] - 1.0
    atr = compute_atr20(result[["trade_date", "asset_id", "high", "low", "close"]])
    result = result.merge(atr, on=["trade_date", "asset_id"], how="left")
    return result.reset_index(drop=True)


def _equity_from_weights(
    holdings: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    variant_name: str,
) -> pd.DataFrame:
    if holdings.empty or prices.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "strategy_family",
                "daily_return",
                "equity",
                "invested_weight",
                "selected_holdings",
                "priced_holdings",
                "holdings",
            ]
        )
    merged = holdings[["trade_date", "asset_id", "target_weight"]].merge(
        prices[["trade_date", "asset_id", "next_return"]],
        on=["trade_date", "asset_id"],
        how="left",
    )
    merged["target_weight"] = pd.to_numeric(merged["target_weight"], errors="coerce").fillna(0.0)
    merged["next_return"] = pd.to_numeric(merged["next_return"], errors="coerce")
    merged["weighted_return"] = merged["target_weight"] * merged["next_return"].fillna(0.0)
    daily = (
        merged.groupby("trade_date", as_index=False)
        .agg(
            daily_return=("weighted_return", "sum"),
            invested_weight=("target_weight", "sum"),
            selected_holdings=("asset_id", "nunique"),
            priced_holdings=("next_return", lambda values: int(values.notna().sum())),
            holdings=("asset_id", "nunique"),
        )
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    if daily.empty:
        return pd.DataFrame()
    daily["equity"] = (1.0 + pd.to_numeric(daily["daily_return"], errors="coerce").fillna(0.0)).cumprod()
    daily["strategy_family"] = variant_name
    return daily[
        [
            "trade_date",
            "strategy_family",
            "daily_return",
            "equity",
            "invested_weight",
            "selected_holdings",
            "priced_holdings",
            "holdings",
        ]
    ]


def _build_trade_changes_from_weights(
    holdings: pd.DataFrame,
    *,
    variant_name: str,
) -> pd.DataFrame:
    if holdings.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    previous: dict[str, float] = {}
    for trade_date, day in holdings.groupby("trade_date", sort=True):
        current = {
            str(row.asset_id): float(row.target_weight)
            for row in day.itertuples(index=False)
            if float(row.target_weight) > 0.0
        }
        day_rows = {str(row.asset_id): row for row in day.itertuples(index=False)}
        for asset_id in sorted(set(previous) | set(current)):
            previous_weight = previous.get(asset_id, 0.0)
            target_weight = current.get(asset_id, 0.0)
            delta = target_weight - previous_weight
            if abs(delta) < 1e-12:
                continue
            source = day_rows.get(asset_id)
            rows.append(
                {
                    "variant_name": variant_name,
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "action": _trade_action(previous_weight, target_weight),
                    "previous_weight": previous_weight,
                    "target_weight": target_weight,
                    "delta_weight": delta,
                    "abs_delta_weight": abs(delta),
                    "score_rank": getattr(source, "score_rank", pd.NA) if source else pd.NA,
                    "mid_trend_layer": getattr(source, "mid_trend_layer", "") if source else "",
                    "confirmed_regime_state": getattr(source, "confirmed_regime_state", "") if source else "",
                    "entry_soft_reason": getattr(source, "entry_soft_reason", "") if source else "",
                    "ownership_state": getattr(source, "ownership_state", "") if source else "",
                }
            )
        previous = current
    return pd.DataFrame(rows)


def _build_trade_audit_detail(
    trades: pd.DataFrame,
    forward_lookup: dict[tuple[str, str], float],
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    for item in trades.to_dict("records"):
        action = _text(item.get("action"))
        forward_return = forward_lookup.get(
            (_text(item.get("trade_date")), _text(item.get("asset_id"))),
            float("nan"),
        )
        audit_label = ""
        if action in {"buy", "increase"} and pd.notna(forward_return) and forward_return < 0.0:
            audit_label = "bad_buy"
        if action in {"sell", "decrease"} and pd.notna(forward_return) and forward_return > 0.02:
            audit_label = "bad_sell"
        row = dict(item)
        row["forward_return"] = forward_return
        row["audit_label"] = audit_label
        rows.append(row)
    return pd.DataFrame(rows)


def _build_trade_episodes(
    holdings: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    variant_name: str,
) -> pd.DataFrame:
    if holdings.empty:
        return pd.DataFrame(
            columns=[
                "variant_name",
                "asset_id",
                "entry_date",
                "exit_date",
                "holding_days",
                "pnl",
                "max_loss",
                "entry_weight_multiplier",
                "entry_soft_reason",
            ]
        )
    merged = holdings[["trade_date", "asset_id", "target_weight", "entry_weight_multiplier", "entry_soft_reason"]].merge(
        prices[["trade_date", "asset_id", "next_return", "close"]],
        on=["trade_date", "asset_id"],
        how="left",
    )
    rows = []
    for asset_id, group in merged.sort_values(["asset_id", "trade_date"]).groupby("asset_id", sort=True):
        active = group[pd.to_numeric(group["target_weight"], errors="coerce").gt(0.0)].copy()
        if active.empty:
            continue
        entry_date = str(active["trade_date"].iloc[0])
        exit_date = str(active["trade_date"].iloc[-1])
        pnl_path = (
            pd.to_numeric(active["target_weight"], errors="coerce").fillna(0.0)
            * pd.to_numeric(active["next_return"], errors="coerce").fillna(0.0)
        )
        cumulative = pnl_path.cumsum()
        rows.append(
            {
                "variant_name": variant_name,
                "asset_id": str(asset_id),
                "entry_date": entry_date,
                "exit_date": exit_date,
                "holding_days": int(len(active)),
                "pnl": float(pnl_path.sum()),
                "max_loss": float(cumulative.min()) if not cumulative.empty else 0.0,
                "entry_weight_multiplier": float(
                    pd.to_numeric(active["entry_weight_multiplier"], errors="coerce").fillna(1.0).iloc[0]
                ),
                "entry_soft_reason": str(active["entry_soft_reason"].iloc[0] or "normal"),
            }
        )
    return pd.DataFrame(rows)


def _entry_bucket_summary(episodes: pd.DataFrame, *, variant_name: str) -> pd.DataFrame:
    if episodes.empty:
        return pd.DataFrame(
            columns=[
                "variant_name",
                "entry_soft_reason",
                "entry_weight_multiplier",
                "trade_count",
                "total_pnl",
                "avg_pnl",
                "win_rate",
                "avg_holding_days",
                "max_loss",
                "contribution_to_total_pnl",
            ]
        )
    grouped = (
        episodes.groupby(["entry_soft_reason", "entry_weight_multiplier"], as_index=False)
        .agg(
            trade_count=("asset_id", "size"),
            total_pnl=("pnl", "sum"),
            avg_pnl=("pnl", "mean"),
            win_rate=("pnl", lambda values: float((pd.Series(values) > 0).mean())),
            avg_holding_days=("holding_days", "mean"),
            max_loss=("max_loss", "min"),
        )
    )
    total_pnl = float(pd.to_numeric(grouped["total_pnl"], errors="coerce").sum())
    grouped["contribution_to_total_pnl"] = grouped["total_pnl"] / total_pnl if total_pnl else 0.0
    grouped.insert(0, "variant_name", variant_name)
    return grouped


def _suppressed_summary(detail: pd.DataFrame, *, variant_name: str) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(
            [
                {
                    "variant_name": variant_name,
                    "suppressed_exit_count": 0,
                    "suppressed_exit_avg_forward_pnl": 0.0,
                    "suppressed_exit_win_rate": 0.0,
                    "suppressed_exit_total_contribution": 0.0,
                    "false_hold_count": 0,
                    "false_hold_loss_contribution": 0.0,
                }
            ]
        )
    forward = pd.to_numeric(detail["forward_return_after_suppressed_exit"], errors="coerce")
    false_hold = forward[forward < 0.0]
    return pd.DataFrame(
        [
            {
                "variant_name": variant_name,
                "suppressed_exit_count": int(len(detail)),
                "suppressed_exit_avg_forward_pnl": float(forward.mean()) if not forward.empty else 0.0,
                "suppressed_exit_win_rate": float((forward > 0.0).mean()) if not forward.empty else 0.0,
                "suppressed_exit_total_contribution": float(forward.sum()) if not forward.empty else 0.0,
                "false_hold_count": int((forward < 0.0).sum()) if not forward.empty else 0,
                "false_hold_loss_contribution": float(false_hold.sum()) if not false_hold.empty else 0.0,
            }
        ]
    )


def _write_baseline_diff_report(report: dict[str, object], path: Path) -> None:
    diff = report.get("equity_series_diff")
    text = "# Baseline Diff Report\n\nBaseline reproduction mismatched the reference artifact.\n"
    text += f"- holdings_row_diff: {report.get('holdings_row_diff')}\n"
    text += f"- trades_row_diff: {report.get('trades_row_diff')}\n"
    text += f"- final_equity_diff: {report.get('final_equity_diff')}\n"
    text += f"- total_return_diff: {report.get('total_return_diff')}\n"
    text += f"- max_drawdown_diff: {report.get('max_drawdown_diff')}\n"
    text += f"- equity_series_max_abs_diff: {report.get('equity_series_max_abs_diff')}\n"
    if isinstance(diff, pd.DataFrame) and not diff.empty:
        text += "\n## Equity Series Diff\n"
        text += diff.to_markdown(index=False) + "\n"
    path.write_text(text, encoding="utf-8")


def _build_code_audit_markdown(*, start_date: str, end_date: str) -> str:
    lines = [
        "# Code Audit",
        "",
        f"- strategy entrypoint: `stock_research.current_mid_trend_strategy_v1.run_current_mid_trend_strategy_v1_backtest`",
        f"- backtest entrypoint: `stock-research mid-trend-soft-ownership-optimize --start-date {start_date} --end-date {end_date}`",
        "- signal fields available: `score_rank`, `mid_trend_layer`, `mid_trend_funnel_score`, `confirmed_regime_state`, `ret_20_score`, `ret_60_score`, `max_drawdown_20_score`, `stock_excess_ret_20_score`, `mainline_status`, `industry_mainline_score_v1`, `industry_name`",
        "- position state fields available: `target_weight`, `cash_weight`, `confirmed_regime_state`, `protection_reason`, `entry_weight_multiplier`, `entry_soft_reason`, `ownership_state`, `ownership_reason`",
        "- current entry logic: baseline uses protected selection equal-weight by regime exposure; experiment variants only modify target weight after baseline candidate generation",
        "- current exit logic: baseline exits when asset disappears from protected selection; variant layer can suppress, reduce, or fully exit based on ownership/damage state",
        "- current audit metrics: total/annualized return, max drawdown, sharpe ratio, exposure/cash metrics, trade episode stats, replay-style bad_buy/bad_sell labels, suppressed-exit summary",
        "- what can be safely changed: experimental target-weight adjustment, ownership suppression, partial exits, artifact generation, CLI variant selection",
        "- what must not be changed: baseline current-mid-trend strategy rules, raw data loading semantics, evaluation window defaults, baseline reference artifact, no-lookahead constraint",
    ]
    return "\n".join(lines) + "\n"


def _build_final_interpretation(summary: pd.DataFrame, suppressed: pd.DataFrame) -> str:
    baseline = summary[summary["variant_name"].astype(str).eq("baseline")]
    baseline_return = float(pd.to_numeric(baseline["total_return"], errors="coerce").iloc[0]) if not baseline.empty else 0.0
    lines = [
        "# Final Interpretation",
        "",
        "## 1. Hard Veto Failure",
        "Hard veto reduces labeled issues by removing noisy entries and delaying exits, but the prior experiments showed that this also removed large positive contribution from normal winners. The soft-ownership runner keeps PnL as the primary score and does not treat lower bad-label counts as success on their own.",
        "",
        "## 2. Variant Comparison",
    ]
    for row in summary.sort_values("variant_name").to_dict("records"):
        variant_name = _text(row.get("variant_name"))
        total_return = _to_float(row.get("total_return"))
        exposure = _to_float(row.get("average_exposure"))
        delta = total_return - baseline_return
        lines.append(
            f"- `{variant_name}`: total_return={total_return:.6f}, delta_vs_baseline={delta:.6f}, average_exposure={exposure:.6f}, cash_weight_avg={_to_float(row.get('cash_weight_avg')):.6f}"
        )
    lines.extend(
        [
            "",
            "## 3. Exposure Check",
            "Average exposure and average cash weight are reported explicitly so any return or drawdown change can be attributed to either ownership logic or a simple cash build-up. Released weight is not normalized back into other positions.",
            "",
            "## 4. Suppressed Exit Review",
        ]
    )
    if suppressed.empty:
        lines.append("No suppressed exit rows were generated.")
    else:
        for row in suppressed.to_dict("records"):
            lines.append(
                f"- `{row.get('variant_name')}`: suppressed_exit_count={row.get('suppressed_exit_count')}, suppressed_exit_total_contribution={row.get('suppressed_exit_total_contribution')}, false_hold_count={row.get('false_hold_count')}, false_hold_loss_contribution={row.get('false_hold_loss_contribution')}"
            )
    lines.extend(
        [
            "",
            "## 5. Next Step",
            "Accept only variants that improve total_return or materially improve return_per_unit_exposure without hiding the change behind higher cash. Reject any variant that lowers total_return while merely improving bad_buy/bad_sell counts.",
        ]
    )
    return "\n".join(lines) + "\n"


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if isinstance(frame, pd.DataFrame) and not frame.empty]
    return pd.concat(usable, ignore_index=True, sort=False) if usable else pd.DataFrame()


def _append_holding_row(
    rows: list[dict[str, Any]],
    *,
    variant_name: str,
    trade_date: str,
    asset_id: str,
    source_row: dict[str, Any],
    target_weight: float,
    ownership_state: str,
    ownership_reason: str,
    rank_memory_state: str,
    profit_cushion_state: str,
    damage_state: str,
    suppressed: bool,
    entry_weight_multiplier: float,
    entry_soft_reason: str,
) -> None:
    row = dict(source_row)
    row["variant_name"] = variant_name
    row["trade_date"] = trade_date
    row["asset_id"] = asset_id
    row["target_weight"] = target_weight
    row["ownership_state"] = ownership_state
    row["ownership_reason"] = ownership_reason
    row["rank_memory_state"] = rank_memory_state
    row["profit_cushion_state"] = profit_cushion_state
    row["damage_state"] = damage_state
    row["whether_exit_was_suppressed_by_ownership"] = suppressed
    row["entry_weight_multiplier"] = entry_weight_multiplier
    row["entry_soft_reason"] = entry_soft_reason
    rows.append(row)


def _trade_rows_from_weight_delta(
    *,
    variant_name: str,
    trade_date: str,
    previous_weights: dict[str, float],
    current_weights: dict[str, float],
    day_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    row_by_asset = {str(row["asset_id"]): row for row in day_rows}
    rows = []
    for asset_id in sorted(set(previous_weights) | set(current_weights)):
        previous_weight = _to_float(previous_weights.get(asset_id))
        current_weight = _to_float(current_weights.get(asset_id))
        delta = current_weight - previous_weight
        if abs(delta) < 1e-12:
            continue
        source = row_by_asset.get(asset_id, {})
        rows.append(
            {
                "variant_name": variant_name,
                "trade_date": trade_date,
                "asset_id": asset_id,
                "action": _trade_action(previous_weight, current_weight),
                "previous_weight": previous_weight,
                "target_weight": current_weight,
                "delta_weight": delta,
                "abs_delta_weight": abs(delta),
                "score_rank": source.get("score_rank", pd.NA),
                "mid_trend_layer": source.get("mid_trend_layer", ""),
                "confirmed_regime_state": source.get("confirmed_regime_state", ""),
                "entry_soft_reason": source.get("entry_soft_reason", ""),
                "ownership_state": source.get("ownership_state", ""),
            }
        )
    return rows


def _trade_action(previous_weight: float, target_weight: float) -> str:
    if previous_weight == 0.0 and target_weight > 0.0:
        return "buy"
    if previous_weight > 0.0 and target_weight == 0.0:
        return "sell"
    return "increase" if target_weight > previous_weight else "decrease"


def _current_close(price_lookup: dict[tuple[str, str], Any], trade_date: str, asset_id: str) -> float:
    return _lookup_price_field(price_lookup, trade_date, asset_id, "close")


def _lookup_price_field(
    price_lookup: dict[tuple[str, str], Any],
    trade_date: str,
    asset_id: str,
    field: str,
) -> float:
    row = price_lookup.get((trade_date, asset_id))
    if row is None:
        return 0.0
    if isinstance(row, dict):
        return _to_float(row.get(field))
    return _to_float(getattr(row, field, 0.0))


def _forward_return_to_end(prices: pd.DataFrame, asset_id: str, trade_date: str) -> float:
    asset_prices = prices[prices["asset_id"].astype(str).eq(asset_id)].copy()
    if asset_prices.empty:
        return float("nan")
    future = asset_prices[asset_prices["trade_date"].astype(str) >= trade_date].sort_values("trade_date")
    if len(future) < 2:
        return float("nan")
    entry_close = _to_float(future["close"].iloc[0])
    exit_close = _to_float(future["close"].iloc[-1])
    return exit_close / entry_close - 1.0 if entry_close > 0 else float("nan")


def _build_forward_return_lookup(prices: pd.DataFrame) -> dict[tuple[str, str], float]:
    if prices.empty:
        return {}
    rows = []
    for asset_id, group in prices.sort_values(["asset_id", "trade_date"]).groupby("asset_id", sort=True):
        final_close = _to_float(group["close"].iloc[-1])
        last_date = _text(group["trade_date"].iloc[-1])
        for item in group[["trade_date", "close"]].itertuples(index=False):
            trade_date = _text(item.trade_date)
            close = _to_float(item.close)
            if trade_date == last_date or close <= 0.0:
                forward_return = float("nan")
            else:
                forward_return = final_close / close - 1.0
            rows.append(((trade_date, str(asset_id)), forward_return))
    return dict(rows)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any) -> int | None:
    try:
        if pd.isna(value):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _ownership_columns() -> list[str]:
    return [
        "variant_name",
        "trade_date",
        "asset_id",
        "ownership_state",
        "ownership_reason",
        "rank_memory_state",
        "profit_cushion_state",
        "damage_state",
        "whether_exit_was_suppressed_by_ownership",
        "missing_meta_state",
    ]


def _exit_columns() -> list[str]:
    return [
        "variant_name",
        "trade_date",
        "asset_id",
        "exit_action",
        "exit_fraction",
        "exit_reason",
        "confirmed_damage_flag",
        "ownership_state",
        "score_rank",
        "confirmed_regime_state",
        "mid_trend_layer",
        "pnl_before_exit",
        "forward_return_after_exit",
    ]
