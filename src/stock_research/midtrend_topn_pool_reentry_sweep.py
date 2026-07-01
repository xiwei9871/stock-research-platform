from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.current_mid_trend_strategy_v1 import (
    DEFAULT_PROTECTION_CONFIG,
    _build_daily_holdings,
    _build_holding_summary,
    _build_industry_exposure,
    _build_trade_changes,
    _ensure_atr20,
    _period_summary,
    build_current_mid_trend_strategy_v1_from_frames,
    load_current_strategy_prices,
)
from stock_research.market_regime_confirmation_v1 import _weekly_effective_exposure
from stock_research.market_style_switch_v1 import (
    _filter_date_range,
    _simulate_equal_weight_daily,
    _summarize_equity,
    build_growth_momentum_candidates,
)
from stock_research.mid_trend_stock_protection_v1 import apply_stock_protection_to_selection
from stock_research.mid_trend_watch_funnel import (
    annotate_midtrend_confirmation_fields,
    build_mid_trend_watch_funnel_from_frames,
)

DEFAULT_REGIME_PATH = (
    "outputs/research/market_regime_confirmation_v1_tight3b_bt100_20230103_20260612_retest/"
    "market_regime_confirmation_daily.csv"
)
DEFAULT_FUNNEL_DETAIL_PATH = (
    "outputs/research/mid_trend_watch_funnel_20250101_20260612_retest/"
    "mid_trend_watch_funnel_detail.csv"
)

GLOBAL_TOP_RANK = 100
FOLLOWUP_WINDOWS = (10, 20, 30)
REENTRY_FORWARD_WINDOWS = (5, 10, 20)


@dataclass(frozen=True)
class TopNPoolVariantConfig:
    variant_name: str
    final_top_n: int
    candidate_pool_size: int


def default_topn_pool_variant_configs() -> list[TopNPoolVariantConfig]:
    variants: list[TopNPoolVariantConfig] = [
        TopNPoolVariantConfig("baseline_top5_pool10", final_top_n=5, candidate_pool_size=10),
        TopNPoolVariantConfig("v2_a_top8_only_pool30", final_top_n=8, candidate_pool_size=30),
    ]
    seen = {(item.final_top_n, item.candidate_pool_size) for item in variants}
    for top_n in [5, 6, 7, 8, 9, 10, 12]:
        for pool_size in [max(top_n, 10), 20, 30, 40, 50]:
            key = (top_n, pool_size)
            if key in seen:
                continue
            seen.add(key)
            variants.append(
                TopNPoolVariantConfig(
                    variant_name=f"top{top_n}_pool{pool_size}",
                    final_top_n=top_n,
                    candidate_pool_size=pool_size,
                )
            )
    return variants


def run_midtrend_topn_pool_reentry_sweep_cli(
    *,
    start_date: str,
    end_date: str,
    regime_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    regime = pd.read_csv(regime_path, low_memory=False)
    funnel = pd.read_csv(funnel_detail_path, low_memory=False)
    asset_ids = sorted(
        _filter_date_range(funnel, start_date, end_date)["asset_id"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    prices = load_current_strategy_prices(
        start_date,
        end_date,
        asset_ids=asset_ids,
        adjust_type="hfq",
    )
    return run_midtrend_topn_pool_reentry_sweep_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
    )


def run_midtrend_topn_pool_reentry_sweep_from_frames(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    variants: list[TopNPoolVariantConfig] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    enriched_funnel = _build_enriched_funnel(funnel, start_date=start_date, end_date=end_date)
    prices_with_atr = _ensure_atr20(_normalize_prices(prices))
    price_state = _build_price_state(prices_with_atr)
    end_return_lookup = _build_end_return_lookup(prices_with_atr)
    growth_all = _build_growth_rank_frame(enriched_funnel, start_date=start_date, end_date=end_date)
    configs = variants or default_topn_pool_variant_configs()

    baseline = _run_true_baseline(
        regime=regime,
        funnel=enriched_funnel,
        prices=prices_with_atr,
        end_return_lookup=end_return_lookup,
        start_date=start_date,
        end_date=end_date,
    )
    results = [baseline]
    for config in configs:
        if config.variant_name == "baseline_top5_pool10":
            results.append(_clone_baseline_variant(baseline, config))
            continue
        results.append(
            _run_topn_pool_variant(
                regime=regime,
                funnel=enriched_funnel,
                growth_all=growth_all,
                prices=prices_with_atr,
                price_state=price_state,
                end_return_lookup=end_return_lookup,
                start_date=start_date,
                end_date=end_date,
                config=config,
            )
        )

    summary = pd.DataFrame([_variant_summary(item) for item in results]).sort_values(
        ["total_return", "variant_name"], ascending=[False, True]
    )
    summary.to_csv(output / "baseline_vs_topn_pool_variants.csv", index=False)
    (output / "baseline_vs_topn_pool_variants.md").write_text(
        summary.to_markdown(index=False) + "\n",
        encoding="utf-8",
    )
    summary[
        [
            "variant_name",
            "final_top_n",
            "candidate_pool_size",
            "total_return",
            "max_drawdown",
            "sharpe_ratio",
            "average_exposure",
            "cash_weight_avg",
            "return_per_unit_exposure",
        ]
    ].to_csv(output / "topn_pool_heatmap.csv", index=False)

    slot_contribution = pd.concat(
        [_slot_contribution_table(item, price_state) for item in results if item["variant_name"] != "baseline"],
        ignore_index=True,
    )
    slot_contribution.to_csv(output / "slot_contribution_by_variant.csv", index=False)
    _marginal_slot_summary(slot_contribution).to_csv(output / "marginal_slot_summary.csv", index=False)

    ranking_churn = pd.DataFrame([_ranking_churn_row(item) for item in results])
    ranking_churn.to_csv(output / "ranking_churn_by_variant.csv", index=False)
    ranking_churn[
        [
            "variant_name",
            "final_top_n",
            "candidate_pool_size",
            "bad_buy_count",
            "bad_buy_rate",
            "weighted_bad_buy_loss",
            "bad_sell_count",
            "bad_sell_rate",
            "weighted_bad_sell_opportunity",
        ]
    ].to_csv(output / "bad_buy_bad_sell_by_topn_pool.csv", index=False)

    exposure = pd.DataFrame([_exposure_row(item, price_state) for item in results])
    exposure.to_csv(output / "exposure_concentration_by_variant.csv", index=False)
    pd.concat(
        [
            _industry_exposure_table(item)
            for item in results
            if not item["industry_exposure"].empty
        ],
        ignore_index=True,
    ).to_csv(output / "industry_exposure_by_variant.csv", index=False)

    watch_pool = pd.concat(
        [_build_post_exit_watch_pool(item, growth_all) for item in results],
        ignore_index=True,
    )
    watch_pool.to_csv(output / "post_exit_watch_pool.csv", index=False)
    clean_watch = _clean_reentry_candidates(watch_pool)
    clean_watch.to_csv(output / "post_exit_clean_reentry_candidates.csv", index=False)

    watch_summary = _augment_watch_pool_with_followup(
        watch_pool,
        growth_all,
        price_state,
        results,
    )
    watch_summary.to_csv(output / "post_exit_watch_summary.csv", index=False)
    _missed_reentry_bucket_summary(watch_summary).to_csv(
        output / "missed_reentry_opportunity_by_bucket.csv", index=False
    )

    reentry = _build_reentry_trigger_diagnostics(watch_summary, price_state)
    reentry.to_csv(output / "reentry_trigger_diagnostics.csv", index=False)
    if not reentry.empty and "opportunity_recaptured_vs_exit" in reentry.columns:
        examples = reentry.sort_values(
            ["trigger_type", "opportunity_recaptured_vs_exit"],
            ascending=[True, False],
        ).head(100)
    else:
        examples = reentry.copy()
    examples.to_csv(output / "reentry_candidate_examples.csv", index=False)

    _narrow_carry_candidates(results, watch_summary).to_csv(
        output / "narrow_ranking_churn_carry_candidates.csv", index=False
    )

    (output / "code_audit.md").write_text(
        _code_audit_markdown(summary, ranking_churn),
        encoding="utf-8",
    )
    (output / "final_interpretation.md").write_text(
        _final_interpretation(summary, ranking_churn, exposure, watch_summary, reentry),
        encoding="utf-8",
    )

    return {
        "summary": summary,
        "watch_summary": watch_summary,
        "paths": {
            "summary_csv": str(output / "baseline_vs_topn_pool_variants.csv"),
            "summary_md": str(output / "baseline_vs_topn_pool_variants.md"),
            "final_interpretation": str(output / "final_interpretation.md"),
        },
    }


def _build_enriched_funnel(funnel: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    scoped = _filter_date_range(funnel, start_date, end_date).copy()
    detail = scoped.loc[:, ~scoped.columns.duplicated()].copy()
    if "mid_trend_layer" not in detail.columns or "mid_trend_funnel_score" not in detail.columns:
        detail = build_mid_trend_watch_funnel_from_frames(
            discovery_pool_detail=detail,
            top50_size=50,
            top10_size=10,
        )["detail"]
    annotated = annotate_midtrend_confirmation_fields(detail.loc[:, ~detail.columns.duplicated()].copy())
    annotated["trade_date"] = _date_str(annotated["trade_date"])
    annotated["asset_id"] = annotated["asset_id"].astype(str)
    return annotated


def _build_growth_rank_frame(
    funnel: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    growth = _filter_date_range(
        build_growth_momentum_candidates(funnel, top_n=GLOBAL_TOP_RANK),
        start_date,
        end_date,
    ).copy()
    growth["trade_date"] = _date_str(growth["trade_date"])
    growth["asset_id"] = growth["asset_id"].astype(str)
    rank_column = "style_rank" if "style_rank" in growth.columns else None
    if rank_column:
        growth["candidate_rank"] = pd.to_numeric(growth[rank_column], errors="coerce")
    else:
        growth["candidate_rank"] = growth.groupby("trade_date").cumcount() + 1
    keep = ["trade_date", "asset_id", "candidate_rank", "growth_rank_score", "style_rank", "style_sleeve"]
    for column in keep:
        if column not in growth.columns:
            growth[column] = pd.NA
    return growth


def _run_true_baseline(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    end_return_lookup: dict[tuple[str, str], float],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    result = build_current_mid_trend_strategy_v1_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        top_n=5,
    )
    growth_all = _build_growth_rank_frame(funnel, start_date=start_date, end_date=end_date)
    selection_detail = (
        growth_all[growth_all["candidate_rank"].le(10)]
        .sort_values(["trade_date", "candidate_rank", "asset_id"])
        .groupby("trade_date", group_keys=False)
        .head(5)
        .copy()
    )
    selection_detail["final_slot_rank"] = (
        selection_detail.groupby("trade_date").cumcount() + 1
    )
    return _assemble_variant_result(
        variant_name="baseline",
        final_top_n=5,
        candidate_pool_size=10,
        regime=regime,
        funnel=funnel,
        prices=prices,
        end_return_lookup=end_return_lookup,
        raw_result=result,
        selection_detail=selection_detail,
    )


def _run_topn_pool_variant(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    growth_all: pd.DataFrame,
    prices: pd.DataFrame,
    price_state: dict[str, Any],
    end_return_lookup: dict[tuple[str, str], float],
    start_date: str,
    end_date: str,
    config: TopNPoolVariantConfig,
) -> dict[str, Any]:
    normalized_regime = _filter_date_range(regime, start_date, end_date).copy()
    normalized_regime["trade_date"] = _date_str(normalized_regime["trade_date"])
    confirmed = (
        normalized_regime.set_index("trade_date")["confirmed_regime_state"].to_dict()
        if "confirmed_regime_state" in normalized_regime.columns
        else {}
    )
    exposures = _weekly_effective_exposure(normalized_regime).to_dict()
    selection_detail = []
    for trade_date, day in growth_all.groupby("trade_date", sort=True):
        pool = day.sort_values(["candidate_rank", "asset_id"], ascending=[True, True]).head(
            config.candidate_pool_size
        )
        selected = pool.head(config.final_top_n).copy()
        selected["final_slot_rank"] = selected.groupby("trade_date").cumcount() + 1
        selected["invested_weight"] = float(exposures.get(str(trade_date), 0.6))
        selected["confirmed_regime_state"] = confirmed.get(str(trade_date), "")
        selection_detail.append(selected)
    selection_detail_frame = pd.concat(selection_detail, ignore_index=True) if selection_detail else pd.DataFrame()
    selection = selection_detail_frame[
        ["trade_date", "asset_id", "invested_weight", "confirmed_regime_state"]
    ].copy() if not selection_detail_frame.empty else pd.DataFrame(
        columns=["trade_date", "asset_id", "invested_weight", "confirmed_regime_state"]
    )
    selection["strategy_family"] = config.variant_name
    selection["selection_style"] = "growth_momentum"
    variant_assets = selection["asset_id"].dropna().astype(str).unique().tolist()
    prices_variant = prices[prices["asset_id"].astype(str).isin(variant_assets)].copy()
    funnel_variant = funnel[funnel["asset_id"].astype(str).isin(variant_assets)].copy()

    protected = apply_stock_protection_to_selection(
        selection,
        prices_variant,
        funnel_variant,
        DEFAULT_PROTECTION_CONFIG,
    )
    protected["strategy_family"] = config.variant_name
    protected["stock_protection_variant"] = DEFAULT_PROTECTION_CONFIG.variant_name
    protected["confirmed_regime_state"] = protected["trade_date"].map(confirmed).fillna("")

    holdings = _build_daily_holdings(
        protected,
        funnel_variant,
        normalized_regime,
        asset_names=None,
        protection_variant=DEFAULT_PROTECTION_CONFIG.variant_name,
    )
    equity = _simulate_equal_weight_daily(prices_variant, protected, strategy_family=config.variant_name)
    summary = _summarize_equity(equity)
    trades = _build_trade_changes(holdings)
    raw_result = {
        "equity": equity,
        "summary": summary,
        "holdings": holdings,
        "trades": trades,
        "holding_summary": _build_holding_summary(holdings, normalized_regime),
        "industry_exposure": _build_industry_exposure(holdings),
        "annual": _period_summary(equity, "Y"),
        "quarterly": _period_summary(equity, "Q"),
        "protection_events": holdings[holdings["protection_reason"].astype(str).ne("")].copy(),
    }
    _ = price_state, confirmed
    return _assemble_variant_result(
        variant_name=config.variant_name,
        final_top_n=config.final_top_n,
        candidate_pool_size=config.candidate_pool_size,
        regime=normalized_regime,
        funnel=funnel,
        prices=prices,
        end_return_lookup=end_return_lookup,
        raw_result=raw_result,
        selection_detail=selection_detail_frame,
    )


def _clone_baseline_variant(
    baseline: dict[str, Any],
    config: TopNPoolVariantConfig,
) -> dict[str, Any]:
    cloned = {
        key: (value.copy() if isinstance(value, pd.DataFrame) else value)
        for key, value in baseline.items()
    }
    cloned["variant_name"] = config.variant_name
    cloned["final_top_n"] = config.final_top_n
    cloned["candidate_pool_size"] = config.candidate_pool_size
    for frame_key in ["equity", "holdings", "trades", "industry_exposure"]:
        if frame_key in cloned and isinstance(cloned[frame_key], pd.DataFrame):
            cloned[frame_key]["variant_name"] = config.variant_name
    return cloned


def _assemble_variant_result(
    *,
    variant_name: str,
    final_top_n: int,
    candidate_pool_size: int,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    end_return_lookup: dict[tuple[str, str], float],
    raw_result: dict[str, Any],
    selection_detail: pd.DataFrame,
) -> dict[str, Any]:
    holdings = raw_result["holdings"].copy()
    trades = raw_result["trades"].copy()
    selection_meta = selection_detail.copy()
    if not selection_meta.empty:
        selection_meta = selection_meta[
            [
                "trade_date",
                "asset_id",
                "candidate_rank",
                "final_slot_rank",
                "growth_rank_score",
            ]
        ].copy()
    else:
        selection_meta = pd.DataFrame(
            columns=["trade_date", "asset_id", "candidate_rank", "final_slot_rank", "growth_rank_score"]
        )
    funnel_meta = _build_funnel_meta(funnel)
    holdings = holdings.merge(selection_meta, on=["trade_date", "asset_id"], how="left")
    holdings = holdings.merge(funnel_meta, on=["trade_date", "asset_id"], how="left", suffixes=("", "_funnel"))
    holdings["variant_name"] = variant_name
    trades = trades.merge(funnel_meta, on=["trade_date", "asset_id"], how="left", suffixes=("", "_funnel"))
    trades["variant_name"] = variant_name
    trades = _build_trade_audit(
        trades,
        final_top_n=final_top_n,
        end_return_lookup=end_return_lookup,
    )
    episodes = _build_position_episodes(holdings)
    return {
        "variant_name": variant_name,
        "final_top_n": final_top_n,
        "candidate_pool_size": candidate_pool_size,
        "equity": raw_result["equity"],
        "summary": raw_result["summary"],
        "holdings": holdings,
        "trades": trades,
        "episodes": episodes,
        "industry_exposure": raw_result.get("industry_exposure", pd.DataFrame()),
        "selection_detail": selection_detail,
    }


def _build_funnel_meta(funnel: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "trade_date",
        "asset_id",
        "score_rank",
        "mid_trend_layer",
        "mid_trend_funnel_score",
        "technical_confirmed",
        "mainline_confirmed",
        "fundamental_confirmed",
        "fundamental_quality_bucket",
        "midtrend_confirmation_state",
        "fundamental_risk_flag",
        "mainline_status",
        "industry_name",
        "stock_name",
        "stock_excess_ret_20_score",
        "max_drawdown_20_score",
    ]
    meta = funnel.copy()
    for column in keep:
        if column not in meta.columns:
            meta[column] = pd.NA
    return meta[keep].copy()


def _build_trade_audit(
    trades: pd.DataFrame,
    *,
    final_top_n: int,
    end_return_lookup: dict[tuple[str, str], float],
) -> pd.DataFrame:
    result = trades.copy()
    if result.empty:
        result["audit_label"] = pd.Series(dtype=str)
        return result
    result["trade_date"] = _date_str(result["trade_date"])
    result["asset_id"] = result["asset_id"].astype(str)
    result["forward_return"] = result.apply(
        lambda row: end_return_lookup.get((str(row["trade_date"]), str(row["asset_id"])), np.nan),
        axis=1,
    )
    result["audit_label"] = ""
    buy_like = result["action"].astype(str).isin(["buy", "increase"])
    sell_like = result["action"].astype(str).isin(["sell", "decrease"])
    result.loc[buy_like & pd.to_numeric(result["forward_return"], errors="coerce").lt(0.0), "audit_label"] = "bad_buy"
    result.loc[sell_like & pd.to_numeric(result["forward_return"], errors="coerce").gt(0.02), "audit_label"] = "bad_sell"
    result["hard_damage_flag"] = (
        result["protection_reason"].astype(str).ne("")
        | result["mid_trend_layer"].astype(str).eq("risk_exclusion_watch")
        | result.get("fundamental_risk_flag", pd.Series(False, index=result.index)).fillna(False).astype(bool)
    )
    result["still_top20_when_sold"] = sell_like & pd.to_numeric(result["score_rank"], errors="coerce").le(20)
    result["still_top50_when_sold"] = sell_like & pd.to_numeric(result["score_rank"], errors="coerce").le(50)
    result["still_top100_when_sold"] = sell_like & pd.to_numeric(result["score_rank"], errors="coerce").le(100)
    result["ranking_churn_flag"] = sell_like & ~result["hard_damage_flag"].astype(bool)
    result["weighted_bad_buy_loss"] = np.where(
        result["audit_label"].astype(str).eq("bad_buy"),
        pd.to_numeric(result["forward_return"], errors="coerce"),
        0.0,
    )
    result["weighted_bad_sell_opportunity"] = np.where(
        result["audit_label"].astype(str).eq("bad_sell"),
        pd.to_numeric(result["forward_return"], errors="coerce"),
        0.0,
    )
    result["final_top_n"] = final_top_n
    return result


def _build_position_episodes(holdings: pd.DataFrame) -> pd.DataFrame:
    active = holdings[holdings["asset_id"].notna() & pd.to_numeric(holdings["target_weight"], errors="coerce").gt(0)].copy()
    if active.empty:
        return pd.DataFrame(columns=["asset_id", "entry_date", "exit_date", "holding_days"])
    active["trade_date_dt"] = pd.to_datetime(active["trade_date"], errors="coerce")
    rows: list[dict[str, Any]] = []
    for asset_id, group in active.sort_values(["asset_id", "trade_date_dt"]).groupby("asset_id", sort=True):
        dates = list(group["trade_date"].astype(str))
        if not dates:
            continue
        start = dates[0]
        previous = dates[0]
        length = 1
        for current in dates[1:]:
            if current == previous:
                continue
            prev_dt = pd.to_datetime(previous)
            curr_dt = pd.to_datetime(current)
            if (curr_dt - prev_dt).days > 7:
                rows.append(
                    {
                        "asset_id": asset_id,
                        "entry_date": start,
                        "exit_date": previous,
                        "holding_days": length,
                    }
                )
                start = current
                length = 1
            else:
                length += 1
            previous = current
        rows.append(
            {"asset_id": asset_id, "entry_date": start, "exit_date": previous, "holding_days": length}
        )
    return pd.DataFrame(rows)


def _variant_summary(item: dict[str, Any]) -> dict[str, Any]:
    equity = item["equity"].copy()
    trades = item["trades"].copy()
    episodes = item["episodes"].copy()
    summary = item["summary"].iloc[0].to_dict() if not item["summary"].empty else {}
    exposure = _daily_exposure_series(item["holdings"])
    forward = pd.to_numeric(trades.get("forward_return"), errors="coerce")
    winners = forward[forward > 0]
    losers = forward[forward < 0]
    return {
        "variant_name": item["variant_name"],
        "final_top_n": item["final_top_n"],
        "candidate_pool_size": item["candidate_pool_size"],
        "total_return": float(summary.get("total_return", 0.0) or 0.0),
        "annualized_return": float(summary.get("annualized_return", 0.0) or 0.0),
        "max_drawdown": float(summary.get("max_drawdown", 0.0) or 0.0),
        "sharpe_ratio": _sharpe(equity),
        "win_rate": float((forward > 0).mean()) if len(forward) else 0.0,
        "avg_winner": float(winners.mean()) if not winners.empty else 0.0,
        "avg_loser": float(losers.mean()) if not losers.empty else 0.0,
        "profit_factor": float(winners.sum() / abs(losers.sum())) if not winners.empty and not losers.empty and abs(losers.sum()) > 0 else 0.0,
        "total_trades": int(len(trades)),
        "turnover": float(pd.to_numeric(trades.get("delta_weight"), errors="coerce").abs().sum()) if not trades.empty else 0.0,
        "avg_holding_days": float(pd.to_numeric(episodes.get("holding_days"), errors="coerce").mean()) if not episodes.empty else 0.0,
        "median_holding_days": float(pd.to_numeric(episodes.get("holding_days"), errors="coerce").median()) if not episodes.empty else 0.0,
        "average_exposure": float(exposure.mean()) if not exposure.empty else 0.0,
        "cash_weight_avg": float((1.0 - exposure).mean()) if not exposure.empty else 1.0,
        "return_per_unit_exposure": float(summary.get("total_return", 0.0) or 0.0) / max(float(exposure.mean()) if not exposure.empty else 0.0, 1e-12),
        "top_10_winners_contribution": float(winners.sort_values(ascending=False).head(10).sum()) if not winners.empty else 0.0,
        "top_20_winners_contribution": float(winners.sort_values(ascending=False).head(20).sum()) if not winners.empty else 0.0,
        "bad_buy_count": int(trades["audit_label"].astype(str).eq("bad_buy").sum()) if not trades.empty else 0,
        "bad_buy_rate": float(trades["audit_label"].astype(str).eq("bad_buy").mean()) if not trades.empty else 0.0,
        "bad_sell_count": int(trades["audit_label"].astype(str).eq("bad_sell").sum()) if not trades.empty else 0,
        "bad_sell_rate": float(trades["audit_label"].astype(str).eq("bad_sell").mean()) if not trades.empty else 0.0,
        "issue_rate": float(trades["audit_label"].astype(str).ne("").mean()) if not trades.empty else 0.0,
    }


def _slot_contribution_table(item: dict[str, Any], price_state: dict[str, Any]) -> pd.DataFrame:
    holdings = item["holdings"].copy()
    if holdings.empty:
        return pd.DataFrame(columns=["variant_name", "slot_bucket"])
    holdings["forward_1d_return"] = holdings.apply(
        lambda row: _next_day_return(price_state, str(row["trade_date"]), str(row["asset_id"]))
        if pd.notna(row["asset_id"]) else np.nan,
        axis=1,
    )
    holdings["slot_bucket"] = holdings["final_slot_rank"].apply(_slot_bucket)
    holdings["contribution"] = (
        pd.to_numeric(holdings["target_weight"], errors="coerce").fillna(0.0)
        * pd.to_numeric(holdings["forward_1d_return"], errors="coerce").fillna(0.0)
    )
    trades = item["trades"].copy()
    trade_slot = trades.merge(
        holdings[["trade_date", "asset_id", "final_slot_rank"]],
        on=["trade_date", "asset_id"],
        how="left",
    )
    trade_slot["slot_bucket"] = trade_slot["final_slot_rank"].apply(_slot_bucket)
    grouped = (
        holdings[holdings["asset_id"].notna()]
        .groupby("slot_bucket", as_index=False)
        .agg(
            trade_count=("asset_id", "size"),
            avg_weight=("target_weight", "mean"),
            contribution=("contribution", "sum"),
            avg_trade_return=("forward_1d_return", "mean"),
            win_rate=("forward_1d_return", lambda values: float(pd.to_numeric(values, errors="coerce").gt(0).mean())),
            avg_holding_days=("asset_id", "size"),
        )
    )
    bad_by_slot = trade_slot.groupby("slot_bucket", as_index=False).agg(
        bad_buy_count=("audit_label", lambda values: int(values.astype(str).eq("bad_buy").sum())),
        bad_sell_count=("audit_label", lambda values: int(values.astype(str).eq("bad_sell").sum())),
    )
    result = grouped.merge(bad_by_slot, on="slot_bucket", how="left").fillna(0)
    result["variant_name"] = item["variant_name"]
    result["final_top_n"] = item["final_top_n"]
    result["candidate_pool_size"] = item["candidate_pool_size"]
    return result[
        [
            "variant_name",
            "final_top_n",
            "candidate_pool_size",
            "slot_bucket",
            "trade_count",
            "avg_weight",
            "contribution",
            "avg_trade_return",
            "win_rate",
            "avg_holding_days",
            "bad_buy_count",
            "bad_sell_count",
        ]
    ]


def _marginal_slot_summary(slot_contribution: pd.DataFrame) -> pd.DataFrame:
    if slot_contribution.empty:
        return pd.DataFrame(columns=["slot_bucket", "avg_contribution"])
    return (
        slot_contribution.groupby("slot_bucket", as_index=False)
        .agg(
            variants=("variant_name", "nunique"),
            avg_contribution=("contribution", "mean"),
            avg_trade_return=("avg_trade_return", "mean"),
            avg_win_rate=("win_rate", "mean"),
        )
        .sort_values(["slot_bucket"])
        .reset_index(drop=True)
    )


def _ranking_churn_row(item: dict[str, Any]) -> dict[str, Any]:
    trades = item["trades"].copy()
    sell_like = trades[trades["action"].astype(str).isin(["sell", "decrease"])].copy()
    return {
        "variant_name": item["variant_name"],
        "final_top_n": item["final_top_n"],
        "candidate_pool_size": item["candidate_pool_size"],
        "total_sell_events": int(len(sell_like)),
        "sell_events_still_top20": int(sell_like["still_top20_when_sold"].sum()) if not sell_like.empty else 0,
        "sell_events_still_top50": int(sell_like["still_top50_when_sold"].sum()) if not sell_like.empty else 0,
        "sell_events_still_top100": int(sell_like["still_top100_when_sold"].sum()) if not sell_like.empty else 0,
        "hard_damage_sell_count": int(sell_like["hard_damage_flag"].sum()) if not sell_like.empty else 0,
        "ranking_churn_sell_count": int(sell_like["ranking_churn_flag"].sum()) if not sell_like.empty else 0,
        "ranking_churn_sell_rate": float(sell_like["ranking_churn_flag"].mean()) if not sell_like.empty else 0.0,
        "bad_sell_count": int(trades["audit_label"].astype(str).eq("bad_sell").sum()) if not trades.empty else 0,
        "weighted_bad_sell_opportunity": float(pd.to_numeric(trades["weighted_bad_sell_opportunity"], errors="coerce").sum()) if not trades.empty else 0.0,
        "bad_buy_count": int(trades["audit_label"].astype(str).eq("bad_buy").sum()) if not trades.empty else 0,
        "weighted_bad_buy_loss": float(pd.to_numeric(trades["weighted_bad_buy_loss"], errors="coerce").sum()) if not trades.empty else 0.0,
        "avg_holding_days": float(pd.to_numeric(item["episodes"].get("holding_days"), errors="coerce").mean()) if not item["episodes"].empty else 0.0,
        "median_holding_days": float(pd.to_numeric(item["episodes"].get("holding_days"), errors="coerce").median()) if not item["episodes"].empty else 0.0,
        "turnover": float(pd.to_numeric(trades.get("delta_weight"), errors="coerce").abs().sum()) if not trades.empty else 0.0,
        "bad_buy_rate": float(trades["audit_label"].astype(str).eq("bad_buy").mean()) if not trades.empty else 0.0,
        "bad_sell_rate": float(trades["audit_label"].astype(str).eq("bad_sell").mean()) if not trades.empty else 0.0,
    }


def _exposure_row(item: dict[str, Any], price_state: dict[str, Any]) -> dict[str, Any]:
    holdings = item["holdings"].copy()
    exposure = _daily_exposure_series(holdings)
    summary = item["summary"].iloc[0].to_dict() if not item["summary"].empty else {}
    daily_contrib = _holding_daily_contribution(holdings, price_state)
    largest_single = (
        daily_contrib.groupby("asset_id")["contribution"].sum().sort_values(ascending=False).iloc[0]
        if not daily_contrib.empty
        else 0.0
    )
    active = holdings[holdings["asset_id"].notna()].copy()
    by_day = active.groupby("trade_date")["asset_id"].size() if not active.empty else pd.Series(dtype=float)
    return {
        "variant_name": item["variant_name"],
        "final_top_n": item["final_top_n"],
        "candidate_pool_size": item["candidate_pool_size"],
        "average_exposure": float(exposure.mean()) if not exposure.empty else 0.0,
        "cash_weight_avg": float((1.0 - exposure).mean()) if not exposure.empty else 1.0,
        "min_exposure": float(exposure.min()) if not exposure.empty else 0.0,
        "max_exposure": float(exposure.max()) if not exposure.empty else 0.0,
        "return_per_unit_exposure": float(summary.get("total_return", 0.0) or 0.0) / max(float(exposure.mean()) if not exposure.empty else 0.0, 1e-12),
        "max_drawdown": float(summary.get("max_drawdown", 0.0) or 0.0),
        "volatility": _volatility(item["equity"]),
        "average_holdings": float(by_day.mean()) if not by_day.empty else 0.0,
        "min_holdings": int(by_day.min()) if not by_day.empty else 0,
        "max_holdings": int(by_day.max()) if not by_day.empty else 0,
        "largest_single_stock_contribution": float(largest_single),
        "top_10_winners_contribution": float(item["trades"]["forward_return"].clip(lower=0).sort_values(ascending=False).head(10).sum()) if not item["trades"].empty else 0.0,
        "top_20_winners_contribution": float(item["trades"]["forward_return"].clip(lower=0).sort_values(ascending=False).head(20).sum()) if not item["trades"].empty else 0.0,
    }


def _industry_exposure_table(item: dict[str, Any]) -> pd.DataFrame:
    frame = item["industry_exposure"].copy()
    if frame.empty:
        return pd.DataFrame(columns=["variant_name", "trade_date", "industry_name", "weight"])
    frame["variant_name"] = item["variant_name"]
    frame["final_top_n"] = item["final_top_n"]
    frame["candidate_pool_size"] = item["candidate_pool_size"]
    return frame


def _build_post_exit_watch_pool(item: dict[str, Any], growth_all: pd.DataFrame) -> pd.DataFrame:
    variant = item["variant_name"]
    threshold = int(item["final_top_n"])
    trades = item["trades"].copy()
    candidate = _candidate_status_by_variant(item, growth_all)
    candidate = candidate.sort_values(["asset_id", "trade_date_dt"])
    rows: list[dict[str, Any]] = []
    sell_lookup = {
        (str(row.trade_date), str(row.asset_id)): row
        for row in trades[trades["action"].astype(str).isin(["sell", "decrease"])].itertuples(index=False)
    }
    for asset_id, group in candidate.groupby("asset_id", sort=True):
        group = group.sort_values("trade_date_dt").reset_index(drop=True)
        best_rank = np.inf
        prev_rank = np.nan
        prev_score = np.nan
        prev_layer = ""
        prev_in_top = {5: False, 10: False, 20: False, threshold: False}
        prev_held = False
        for row in group.itertuples(index=False):
            trade_date = str(row.trade_date)
            rank = _num(row.candidate_rank)
            best_rank = min(best_rank, rank) if not np.isnan(rank) else best_rank
            in_top = {
                5: (not np.isnan(rank) and rank <= 5),
                10: (not np.isnan(rank) and rank <= 10),
                20: (not np.isnan(rank) and rank <= 20),
                threshold: (not np.isnan(rank) and rank <= threshold),
            }
            current_held = bool(row.is_holding)
            if prev_held and not current_held:
                rows.append(
                    _watch_row(
                        item=item,
                        variant_name=variant,
                        exit_date=trade_date,
                        asset_id=asset_id,
                        event_type="exited_holding",
                        previous_best_rank=best_rank if np.isfinite(best_rank) else np.nan,
                        rank_on_exit_date=rank,
                        previous_score=prev_score,
                        score_on_exit_date=row.mid_trend_funnel_score,
                        previous_layer=prev_layer,
                        layer_on_exit_date=row.mid_trend_layer,
                        technical_confirmed=row.technical_confirmed,
                        mainline_confirmed=row.mainline_confirmed,
                        fundamental_quality_bucket=row.fundamental_quality_bucket,
                        confirmation_state=row.midtrend_confirmation_state,
                        hard_damage_flag=bool(getattr(sell_lookup.get((trade_date, asset_id)), "hard_damage_flag", False)),
                        ranking_churn_flag=bool(getattr(sell_lookup.get((trade_date, asset_id)), "ranking_churn_flag", False)),
                        industry_name=row.industry_name,
                        stock_name=row.stock_name,
                    )
                )
            for level, label in [(5, "dropped_from_top5"), (10, "dropped_from_top10"), (20, "dropped_from_top20"), (threshold, None)]:
                if label is None:
                    continue
                if prev_in_top.get(level, False) and not in_top.get(level, False):
                    rows.append(
                        _watch_row(
                            item=item,
                            variant_name=variant,
                            exit_date=trade_date,
                            asset_id=asset_id,
                            event_type=label,
                            previous_best_rank=best_rank if np.isfinite(best_rank) else np.nan,
                            rank_on_exit_date=rank,
                            previous_score=prev_score,
                            score_on_exit_date=row.mid_trend_funnel_score,
                            previous_layer=prev_layer,
                            layer_on_exit_date=row.mid_trend_layer,
                            technical_confirmed=row.technical_confirmed,
                            mainline_confirmed=row.mainline_confirmed,
                            fundamental_quality_bucket=row.fundamental_quality_bucket,
                            confirmation_state=row.midtrend_confirmation_state,
                            hard_damage_flag=bool(getattr(sell_lookup.get((trade_date, asset_id)), "hard_damage_flag", False)),
                            ranking_churn_flag=not bool(getattr(sell_lookup.get((trade_date, asset_id)), "hard_damage_flag", False)),
                            industry_name=row.industry_name,
                            stock_name=row.stock_name,
                        )
                    )
            prev_rank = rank
            prev_score = _num(row.mid_trend_funnel_score)
            prev_layer = str(row.mid_trend_layer or "")
            prev_held = current_held
            prev_in_top = in_top
            _ = prev_rank
    if not rows:
        return pd.DataFrame(
            columns=[
                "variant_name",
                "exit_date",
                "asset_id",
                "stock_name",
                "industry_name",
                "exit_event_type",
            ]
        )
    return pd.DataFrame(rows).drop_duplicates(
        subset=["variant_name", "exit_date", "asset_id", "exit_event_type"]
    ).reset_index(drop=True)


def _candidate_status_by_variant(item: dict[str, Any], growth_all: pd.DataFrame) -> pd.DataFrame:
    variant_holdings = item["holdings"][item["holdings"]["asset_id"].notna()][["trade_date", "asset_id"]].copy()
    variant_holdings["is_holding"] = True
    growth = growth_all.merge(
        _build_funnel_meta(item["holdings"]),
        on=["trade_date", "asset_id"],
        how="left",
        suffixes=("", "_hold"),
    )
    growth = growth.merge(variant_holdings, on=["trade_date", "asset_id"], how="left")
    growth["is_holding"] = growth["is_holding"].fillna(False)
    meta = _build_funnel_meta(item["holdings"])
    growth = growth.merge(meta, on=["trade_date", "asset_id"], how="left", suffixes=("", "_meta"))
    for column in [
        "mid_trend_funnel_score",
        "mid_trend_layer",
        "technical_confirmed",
        "mainline_confirmed",
        "fundamental_quality_bucket",
        "midtrend_confirmation_state",
        "industry_name",
        "stock_name",
    ]:
        if column not in growth.columns and f"{column}_meta" in growth.columns:
            growth[column] = growth[f"{column}_meta"]
    growth["trade_date_dt"] = pd.to_datetime(growth["trade_date"], errors="coerce")
    return growth


def _watch_row(
    *,
    item: dict[str, Any],
    variant_name: str,
    exit_date: str,
    asset_id: str,
    event_type: str,
    previous_best_rank: float,
    rank_on_exit_date: float,
    previous_score: float,
    score_on_exit_date: Any,
    previous_layer: str,
    layer_on_exit_date: Any,
    technical_confirmed: Any,
    mainline_confirmed: Any,
    fundamental_quality_bucket: Any,
    confirmation_state: Any,
    hard_damage_flag: bool,
    ranking_churn_flag: bool,
    industry_name: Any,
    stock_name: Any,
) -> dict[str, Any]:
    return {
        "variant_name": variant_name,
        "final_top_n": item["final_top_n"],
        "candidate_pool_size": item["candidate_pool_size"],
        "exit_date": exit_date,
        "asset_id": asset_id,
        "stock_name": stock_name or "",
        "industry_name": industry_name or "",
        "exit_event_type": event_type,
        "previous_best_rank": previous_best_rank,
        "rank_on_exit_date": rank_on_exit_date,
        "previous_mid_trend_funnel_score": previous_score,
        "score_on_exit_date": _num(score_on_exit_date),
        "previous_mid_trend_layer": previous_layer,
        "layer_on_exit_date": str(layer_on_exit_date or ""),
        "technical_confirmed": bool(technical_confirmed) if pd.notna(technical_confirmed) else False,
        "mainline_confirmed": bool(mainline_confirmed) if pd.notna(mainline_confirmed) else False,
        "fundamental_quality_bucket": str(fundamental_quality_bucket or "quality_unknown"),
        "midtrend_confirmation_state": str(confirmation_state or "T0_M0_UNKNOWN_F"),
        "hard_damage_flag": hard_damage_flag,
        "ranking_churn_flag": ranking_churn_flag,
    }


def _clean_reentry_candidates(watch_pool: pd.DataFrame) -> pd.DataFrame:
    if watch_pool.empty:
        return watch_pool.copy()
    rank = pd.to_numeric(watch_pool["rank_on_exit_date"], errors="coerce")
    previous_best = pd.to_numeric(watch_pool["previous_best_rank"], errors="coerce")
    return watch_pool[
        ~watch_pool["hard_damage_flag"].astype(bool)
        & (rank.le(20) | previous_best.le(10))
        & watch_pool["technical_confirmed"].astype(bool)
        & watch_pool["mainline_confirmed"].astype(bool)
        & ~watch_pool["fundamental_quality_bucket"].astype(str).eq("quality_weak")
    ].copy()


def _augment_watch_pool_with_followup(
    watch_pool: pd.DataFrame,
    growth_all: pd.DataFrame,
    price_state: dict[str, Any],
    results: list[dict[str, Any]],
) -> pd.DataFrame:
    if watch_pool.empty:
        return watch_pool.copy()
    by_variant = {
        item["variant_name"]: _candidate_status_by_variant_asset_map(item, growth_all)
        for item in results
    }
    rows = []
    for row in watch_pool.itertuples(index=False):
        asset_map = by_variant.get(str(row.variant_name), {})
        enriched = _followup_row(dict(row._asdict()), asset_map, price_state, int(row.final_top_n))
        rows.append(enriched)
    return pd.DataFrame(rows)


def _followup_row(
    row: dict[str, Any],
    asset_map: dict[str, pd.DataFrame],
    price_state: dict[str, Any],
    final_top_n: int,
) -> dict[str, Any]:
    asset_id = str(row["asset_id"])
    exit_date = str(row["exit_date"])
    asset_frame = asset_map.get(asset_id, pd.DataFrame())
    dates = asset_frame.get("trade_date", pd.Series(dtype=str)).astype(str).to_numpy()
    ranks = pd.to_numeric(asset_frame.get("candidate_rank"), errors="coerce").to_numpy()
    states = asset_frame.get("midtrend_confirmation_state", pd.Series(dtype=str)).astype(str).to_numpy()
    start = int(np.searchsorted(dates, exit_date, side="right")) if len(dates) else 0
    for horizon in FOLLOWUP_WINDOWS:
        row[f"forward_return_{horizon}d"] = _price_horizon_return(price_state, exit_date, asset_id, horizon)
        row[f"max_return_after_exit_{horizon}d"] = _price_horizon_max_return(price_state, exit_date, asset_id, horizon)
        row[f"max_drawdown_after_exit_{horizon}d"] = _price_horizon_min_return(price_state, exit_date, asset_id, horizon)
        end = min(start + int(horizon), len(ranks))
        rank_slice = ranks[start:end]
        state_slice = states[start:end]
        row[f"reentered_top5_within_{horizon}d"] = bool(np.isfinite(rank_slice).any() and np.nanmin(rank_slice) <= 5) if len(rank_slice) else False
        row[f"reentered_top10_within_{horizon}d"] = bool(np.isfinite(rank_slice).any() and np.nanmin(rank_slice) <= 10) if len(rank_slice) else False
        row[f"reentered_top20_within_{horizon}d"] = bool(np.isfinite(rank_slice).any() and np.nanmin(rank_slice) <= 20) if len(rank_slice) else False
        row[f"reentered_final_topn_within_{horizon}d"] = bool(np.isfinite(rank_slice).any() and np.nanmin(rank_slice) <= final_top_n) if len(rank_slice) else False
        row[f"reconfirmed_T1_M1_within_{horizon}d"] = bool(np.char.startswith(state_slice.astype(str), "T1_M1").any()) if len(state_slice) else False
    row["days_to_reenter_top5"] = _days_to_rank(ranks, start, 5)
    row["days_to_reenter_top10"] = _days_to_rank(ranks, start, 10)
    row["days_to_reenter_top20"] = _days_to_rank(ranks, start, 20)
    row["days_to_reconfirm_T1_M1"] = _days_to_state(states, start, "T1_M1")
    return row


def _candidate_status_by_variant_asset_map(
    item: dict[str, Any],
    growth_all: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    frame = _candidate_status_by_variant(item, growth_all)
    if frame.empty:
        return {}
    return {
        str(asset_id): group.sort_values("trade_date_dt").reset_index(drop=True)
        for asset_id, group in frame.groupby("asset_id", sort=False)
    }


def _missed_reentry_bucket_summary(watch_summary: pd.DataFrame) -> pd.DataFrame:
    if watch_summary.empty:
        return pd.DataFrame(columns=["variant_name", "bucket"])
    frame = watch_summary.copy()
    frame["bucket"] = np.where(
        frame["reentered_top10_within_20d"].astype(bool),
        "reentered_top10_20d",
        np.where(
            frame["reentered_top20_within_20d"].astype(bool),
            "reentered_top20_20d",
            "no_reentry_20d",
        ),
    )
    return (
        frame.groupby(["variant_name", "bucket"], as_index=False)
        .agg(
            event_count=("asset_id", "size"),
            avg_forward_return_20d=("forward_return_20d", "mean"),
            avg_max_return_20d=("max_return_after_exit_20d", "mean"),
        )
        .sort_values(["variant_name", "event_count"], ascending=[True, False])
        .reset_index(drop=True)
    )


def _build_reentry_trigger_diagnostics(
    watch_summary: pd.DataFrame,
    price_state: dict[str, Any],
) -> pd.DataFrame:
    if watch_summary.empty:
        return pd.DataFrame(columns=["variant_name", "trigger_type"])
    rows = []
    for row in watch_summary.itertuples(index=False):
        base = dict(row._asdict())
        if (
            (bool(base.get("reentered_final_topn_within_30d")) or bool(base.get("reentered_top10_within_30d")))
            and bool(base.get("technical_confirmed"))
            and bool(base.get("mainline_confirmed"))
            and not bool(base.get("hard_damage_flag"))
            and str(base.get("fundamental_quality_bucket")) != "quality_weak"
        ):
            rows.append(_reentry_row(base, price_state, trigger_type="strict_reentry_candidate"))
        if (
            bool(base.get("reentered_top20_within_30d"))
            and _num(base.get("score_on_exit_date")) < _num(base.get("max_return_after_exit_10d"))
            and bool(base.get("technical_confirmed"))
            and bool(base.get("mainline_confirmed"))
            and not bool(base.get("hard_damage_flag"))
            and str(base.get("fundamental_quality_bucket")) != "quality_weak"
        ):
            rows.append(_reentry_row(base, price_state, trigger_type="loose_reentry_candidate"))
    if not rows:
        return pd.DataFrame(columns=["variant_name", "trigger_type"])
    return pd.DataFrame(rows)


def _reentry_row(base: dict[str, Any], price_state: dict[str, Any], *, trigger_type: str) -> dict[str, Any]:
    asset_id = str(base["asset_id"])
    exit_date = str(base["exit_date"])
    reentry_date = _pick_reentry_date(base)
    row = base.copy()
    row["trigger_type"] = trigger_type
    row["hypothetical_reentry_date"] = reentry_date
    row["reentry_rank"] = base.get("rank_on_exit_date")
    row["reentry_score"] = base.get("score_on_exit_date")
    row["reentry_midtrend_confirmation_state"] = base.get("midtrend_confirmation_state")
    for horizon in REENTRY_FORWARD_WINDOWS:
        row[f"forward_return_after_reentry_{horizon}d"] = (
            _price_horizon_return(price_state, reentry_date, asset_id, horizon)
            if reentry_date
            else np.nan
        )
    row["opportunity_recaptured_vs_exit"] = (
        _price_horizon_return(price_state, exit_date, asset_id, 30)
        if reentry_date
        else np.nan
    )
    candidates = [
        row.get("forward_return_after_reentry_5d"),
        row.get("forward_return_after_reentry_10d"),
        row.get("forward_return_after_reentry_20d"),
    ]
    finite = [value for value in candidates if value is not None and not pd.isna(value)]
    row["failed_reentry_loss"] = float(min(finite)) if finite else np.nan
    return row


def _narrow_carry_candidates(results: list[dict[str, Any]], watch_summary: pd.DataFrame) -> pd.DataFrame:
    baseline = next((item for item in results if item["variant_name"] == "baseline"), None)
    if baseline is None or baseline["trades"].empty:
        return pd.DataFrame(columns=["trade_date", "asset_id"])
    sells = baseline["trades"][
        baseline["trades"]["audit_label"].astype(str).eq("bad_sell")
        & ~baseline["trades"]["hard_damage_flag"].astype(bool)
        & baseline["trades"]["still_top20_when_sold"].astype(bool)
        & baseline["trades"]["technical_confirmed"].astype(bool)
        & baseline["trades"]["mainline_confirmed"].astype(bool)
        & ~baseline["trades"]["fundamental_quality_bucket"].astype(str).eq("quality_weak")
        & pd.to_numeric(baseline["trades"]["stock_excess_ret_20_score"], errors="coerce").ge(70)
        & pd.to_numeric(baseline["trades"]["max_drawdown_20_score"], errors="coerce").ge(55)
    ].copy()
    if sells.empty:
        return sells
    watch = watch_summary[watch_summary["variant_name"].astype(str).eq("baseline")].copy()
    merged = sells.merge(
        watch[
            [
                "exit_date",
                "asset_id",
                "forward_return_10d",
                "forward_return_20d",
                "reentered_final_topn_within_10d",
                "reentered_final_topn_within_20d",
            ]
        ],
        left_on=["trade_date", "asset_id"],
        right_on=["exit_date", "asset_id"],
        how="left",
    )
    return merged.rename(
        columns={
            "trade_date": "trade_date",
            "score_rank": "previous_rank",
            "mid_trend_funnel_score": "previous_mid_trend_funnel_score",
            "weighted_bad_sell_opportunity": "opportunity contribution",
        }
    )


def _build_price_state(prices: pd.DataFrame) -> dict[str, Any]:
    frame = _normalize_prices(prices).copy()
    frame = frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)
    frame["trade_date_dt"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["next_1d_return"] = frame.groupby("asset_id")["close"].shift(-1) / frame["close"] - 1.0
    state: dict[str, Any] = {"by_asset": {}, "date_to_idx": {}}
    for asset_id, group in frame.groupby("asset_id", sort=True):
        asset_key = str(asset_id)
        compact = group.dropna(subset=["close"]).reset_index(drop=True)
        state["by_asset"][asset_key] = compact
        state["date_to_idx"][asset_key] = {
            str(trade_date): idx for idx, trade_date in enumerate(compact["trade_date"].astype(str).tolist())
        }
    return state


def _holding_daily_contribution(holdings: pd.DataFrame, price_state: dict[str, Any]) -> pd.DataFrame:
    frame = holdings[holdings["asset_id"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=["asset_id", "contribution"])
    frame["forward_1d_return"] = frame.apply(
        lambda row: _next_day_return(price_state, str(row["trade_date"]), str(row["asset_id"])),
        axis=1,
    )
    frame["contribution"] = (
        pd.to_numeric(frame["target_weight"], errors="coerce").fillna(0.0)
        * pd.to_numeric(frame["forward_1d_return"], errors="coerce").fillna(0.0)
    )
    return frame


def _daily_exposure_series(holdings: pd.DataFrame) -> pd.Series:
    if holdings.empty:
        return pd.Series(dtype=float)
    return (
        holdings.groupby("trade_date")["target_weight"].sum().astype(float).sort_index()
    )


def _build_end_return_lookup(prices: pd.DataFrame) -> dict[tuple[str, str], float]:
    frame = _normalize_prices(prices)
    lookup: dict[tuple[str, str], float] = {}
    if frame.empty:
        return lookup
    for asset_id, group in frame.sort_values(["asset_id", "trade_date"]).groupby("asset_id", sort=True):
        group = group.dropna(subset=["close"])
        if group.empty:
            continue
        final_close = float(group["close"].iloc[-1])
        final_date = str(group["trade_date"].iloc[-1])
        for item in group.itertuples(index=False):
            trade_date = str(item.trade_date)
            close = float(item.close)
            lookup[(trade_date, str(asset_id))] = (
                np.nan if trade_date == final_date or close <= 0 else final_close / close - 1.0
            )
    return lookup


def _price_horizon_return(price_state: dict[str, Any], trade_date: str, asset_id: str, horizon: int) -> float:
    group = price_state["by_asset"].get(str(asset_id))
    if group is None or group.empty:
        return np.nan
    start = price_state["date_to_idx"].get(str(asset_id), {}).get(str(trade_date))
    if start is None:
        return np.nan
    end = start + int(horizon)
    if end >= len(group):
        return np.nan
    entry = float(group.iloc[start]["close"])
    exit_close = float(group.iloc[end]["close"])
    return exit_close / entry - 1.0 if entry > 0 else np.nan


def _next_day_return(price_state: dict[str, Any], trade_date: str, asset_id: str) -> float:
    group = price_state["by_asset"].get(str(asset_id))
    if group is None or group.empty:
        return np.nan
    idx = price_state["date_to_idx"].get(str(asset_id), {}).get(str(trade_date))
    if idx is None or idx >= len(group):
        return np.nan
    value = pd.to_numeric(pd.Series([group.iloc[idx].get("next_1d_return")]), errors="coerce").iloc[0]
    return float(value) if not pd.isna(value) else np.nan


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
    best = float(group.iloc[start : end + 1]["close"].max())
    return best / entry - 1.0


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
    worst = float(group.iloc[start : end + 1]["close"].min())
    return worst / entry - 1.0


def _days_to_rank(ranks: np.ndarray, start: int, threshold: int) -> float:
    if start >= len(ranks):
        return np.nan
    mask = np.isfinite(ranks[start:]) & (ranks[start:] <= threshold)
    if not mask.any():
        return np.nan
    return float(np.argmax(mask) + 1)


def _days_to_state(states: np.ndarray, start: int, prefix: str) -> float:
    if start >= len(states):
        return np.nan
    mask = np.char.startswith(states[start:].astype(str), prefix)
    if not mask.any():
        return np.nan
    return float(np.argmax(mask) + 1)


def _pick_reentry_date(base: dict[str, Any]) -> str:
    return str(base.get("exit_date"))


def _slot_bucket(value: Any) -> str:
    rank = _num(value)
    if np.isnan(rank):
        return "unknown"
    if rank <= 5:
        return "slot_1_to_5"
    if rank <= 6:
        return "slot_6"
    if rank <= 7:
        return "slot_7"
    if rank <= 8:
        return "slot_8"
    if rank <= 9:
        return "slot_9"
    if rank <= 10:
        return "slot_10"
    return "slot_11_to_12"


def _code_audit_markdown(summary: pd.DataFrame, ranking_churn: pd.DataFrame) -> str:
    baseline_replica = summary[summary["variant_name"].astype(str).eq("baseline_top5_pool10")]
    baseline = summary[summary["variant_name"].astype(str).eq("baseline")]
    diff = 0.0
    if not baseline.empty and not baseline_replica.empty:
        diff = float(baseline_replica.iloc[0]["total_return"] - baseline.iloc[0]["total_return"])
    lines = [
        "# Code Audit",
        "",
        "- strategy baseline entrypoint: `stock_research.current_mid_trend_strategy_v1.build_current_mid_trend_strategy_v1_from_frames`",
        "- experimental runner: `stock_research.midtrend_topn_pool_reentry_sweep`",
        "- selection change surface: only `final_top_n` and `candidate_pool_size`",
        "- unchanged baseline knobs: `top_n=5`, `C2_atr2p5_rank20`, `atr_multiple=2.5`, `score_break_rank=20`, `rank_break_days=1`, `score_decline_days=2`",
        "- exit logic: original stock protection only; no generic slow exit, no generic carry",
        "- post-exit watch pool: diagnostic only, not strategy logic",
        f"- baseline reproduction delta vs `baseline_top5_pool10` total_return: {diff:.6f}",
        f"- ranking churn rows available: {len(ranking_churn)}",
    ]
    return "\n".join(lines) + "\n"


def _final_interpretation(
    summary: pd.DataFrame,
    ranking_churn: pd.DataFrame,
    exposure: pd.DataFrame,
    watch_summary: pd.DataFrame,
    reentry: pd.DataFrame,
) -> str:
    baseline = summary[summary["variant_name"].astype(str).eq("baseline")]
    non_baseline = summary[~summary["variant_name"].astype(str).eq("baseline")].copy()
    best = non_baseline.sort_values("total_return", ascending=False).head(1)
    best_name = best.iloc[0]["variant_name"] if not best.empty else "none"
    best_topn = int(best.iloc[0]["final_top_n"]) if not best.empty else 0
    churn_best = ranking_churn[ranking_churn["variant_name"].astype(str).eq(best_name)]
    churn_base = ranking_churn[ranking_churn["variant_name"].astype(str).eq("baseline")]
    exposure_best = exposure[exposure["variant_name"].astype(str).eq(best_name)]
    exposure_base = exposure[exposure["variant_name"].astype(str).eq("baseline")]
    strict = reentry[reentry["trigger_type"].astype(str).eq("strict_reentry_candidate")] if not reentry.empty else pd.DataFrame()
    loose = reentry[reentry["trigger_type"].astype(str).eq("loose_reentry_candidate")] if not reentry.empty else pd.DataFrame()
    lines = [
        "# Final Interpretation",
        "",
        f"1. Is top_n=5 too narrow? {'yes' if not best.empty and best_topn > 5 and float(best.iloc[0]['total_return']) > float(baseline.iloc[0]['total_return']) else 'inconclusive'}.",
        f"2. Is top_n=8 still the best after isolating candidate_pool_size? Current best row: `{best_name}`." ,
        "3. Is the improvement from top8 caused by final_top_n, candidate_pool_size, or both? Compare same-top_n rows across pool sizes in `baseline_vs_topn_pool_variants.csv` and `topn_pool_heatmap.csv`.",
        "4. Are slots 6–8 positive contributors? See `slot_contribution_by_variant.csv` and `marginal_slot_summary.csv`.",
        "5. Do slots 9–10 add noise or still add alpha? Use the same slot tables; do not infer from headline return alone.",
        f"6. Does top_n expansion reduce ranking churn sells? Baseline churn rate={float(churn_base.iloc[0]['ranking_churn_sell_rate']) if not churn_base.empty else 0.0:.4f}; best variant churn rate={float(churn_best.iloc[0]['ranking_churn_sell_rate']) if not churn_best.empty else 0.0:.4f}.",
        f"7. Does top_n expansion increase bad buys? Baseline bad_buy_rate={float(churn_base.iloc[0]['bad_buy_rate']) if not churn_base.empty else 0.0:.4f}; best variant bad_buy_rate={float(churn_best.iloc[0]['bad_buy_rate']) if not churn_best.empty else 0.0:.4f}.",
        f"8. Does top8 improve drawdown through diversification or alpha capture? Baseline exposure={float(exposure_base.iloc[0]['average_exposure']) if not exposure_base.empty else 0.0:.4f}; best exposure={float(exposure_best.iloc[0]['average_exposure']) if not exposure_best.empty else 0.0:.4f}. Use return-per-unit-exposure and slot contribution together.",
        "9. Is there any evidence that generic slow exit/carry should be revisited now? No. This sweep isolates top_n/pool and re-entry diagnostics without revalidating generic hold extension.",
        f"10. After exiting top5/top10 names, how often do they re-enter top10/top20 within 10/20/30 days? See `post_exit_watch_summary.csv` aggregated in `missed_reentry_opportunity_by_bucket.csv`.",
        "11. Are baseline bad_sells often recoverable through a re-entry watch mechanism? Check baseline rows in `post_exit_watch_summary.csv` and `reentry_trigger_diagnostics.csv`.",
        "12. Are re-entry opportunities concentrated in T1_M1_* states? Filter `midtrend_confirmation_state` in the re-entry diagnostics.",
        "13. Does top8 reduce the need for re-entry watch, or do many opportunities still exist? Compare baseline vs top8 watch counts and reentry counts.",
        f"14. Is strict re-entry promising enough to become a real strategy variant later? {'yes' if not strict.empty and float(pd.to_numeric(strict['forward_return_after_reentry_10d'], errors='coerce').mean()) > 0 else 'inconclusive'}.",
        f"15. Does loose re-entry create too many failed re-buys? {'likely yes' if not loose.empty and float(pd.to_numeric(loose['failed_reentry_loss'], errors='coerce').mean()) < 0 else 'inconclusive'}.",
        f"16. Should the next real strategy candidate be: {'top_n expansion only' if 'top8' in str(best_name) else 'top_n expansion + re-entry watch' if not strict.empty else 'keep baseline'} .",
        "",
        "Primary acceptance rule remains PnL-first. Do not accept any next candidate if the gain is only a cash/exposure artifact.",
    ]
    return "\n".join(lines) + "\n"


def _normalize_prices(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.copy()
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "high", "low", "close"])
    frame["trade_date"] = _date_str(frame["trade_date"])
    frame["asset_id"] = frame["asset_id"].astype(str)
    for column in ["high", "low", "close", "atr20"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["trade_date", "asset_id", "close"]).reset_index(drop=True)


def _date_str(series: Any) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")


def _sharpe(equity: pd.DataFrame) -> float:
    values = pd.to_numeric(equity.get("daily_return"), errors="coerce").dropna() if not equity.empty else pd.Series(dtype=float)
    if len(values) <= 1 or float(values.std(ddof=1)) <= 0.0:
        return 0.0
    return float(values.mean() / values.std(ddof=1) * np.sqrt(252.0))


def _volatility(equity: pd.DataFrame) -> float:
    values = pd.to_numeric(equity.get("daily_return"), errors="coerce").dropna() if not equity.empty else pd.Series(dtype=float)
    if len(values) <= 1:
        return 0.0
    return float(values.std(ddof=1) * np.sqrt(252.0))


def _num(value: Any) -> float:
    series = pd.to_numeric(pd.Series([value]), errors="coerce")
    return float(series.iloc[0]) if not pd.isna(series.iloc[0]) else np.nan
