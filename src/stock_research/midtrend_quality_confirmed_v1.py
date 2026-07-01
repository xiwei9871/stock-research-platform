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
    _run_params,
)
from stock_research.market_regime_confirmation_v1 import _weekly_effective_exposure
from stock_research.market_style_switch_v1 import (
    _filter_date_range,
    _simulate_equal_weight_daily,
    _summarize_equity,
    build_growth_momentum_candidates,
)
from stock_research.mid_trend_stock_protection_v1 import (
    StockProtectionConfig,
    apply_stock_protection_to_selection,
)
from stock_research.mid_trend_watch_funnel import build_mid_trend_watch_funnel_from_frames
from stock_research.mid_trend_watch_funnel import annotate_midtrend_confirmation_fields


DEFAULT_OUTPUT_ROOT = (
    Path(__file__).resolve().parents[2] / "outputs" / "research"
)
DEFAULT_REGIME_PATH = (
    "outputs/research/market_regime_confirmation_v1_tight3b_bt100_20230103_20260612_retest/"
    "market_regime_confirmation_daily.csv"
)
DEFAULT_FUNNEL_DETAIL_PATH = (
    "outputs/research/mid_trend_watch_funnel_20250101_20260612_retest/"
    "mid_trend_watch_funnel_detail.csv"
)


@dataclass(frozen=True)
class MidTrendQualityVariantConfig:
    variant_name: str
    top_n: int = 8
    candidate_pool_size: int = 30
    exclude_quality_weak: bool = False
    mainline_bonus: float = 0.0
    quality_strong_bonus: float = 0.0
    quality_unknown_penalty: float = 0.0
    high_elasticity_unconfirmed_penalty: float = 0.0
    incumbent_bonus: float = 0.0
    protection_config: StockProtectionConfig = DEFAULT_PROTECTION_CONFIG
    max_carry_slots: int = 0
    carry_days_limit: int = 0

    def __post_init__(self) -> None:
        presets = {
            "v2_b_top8_quality": {
                "exclude_quality_weak": True,
                "mainline_bonus": 4.0,
                "quality_strong_bonus": 4.0,
                "high_elasticity_unconfirmed_penalty": 4.0,
            },
            "v2_c_top8_quality_slowexit": {
                "exclude_quality_weak": True,
                "mainline_bonus": 4.0,
                "quality_strong_bonus": 4.0,
                "high_elasticity_unconfirmed_penalty": 4.0,
                "protection_config": StockProtectionConfig(
                    variant_name="quality_slowexit_rank50_3d",
                    atr_multiple=2.5,
                    score_break_rank=50,
                    rank_break_days=3,
                    score_decline_days=3,
                ),
            },
            "v2_d_top8_quality_slowexit_carry1": {
                "exclude_quality_weak": True,
                "mainline_bonus": 4.0,
                "quality_strong_bonus": 4.0,
                "high_elasticity_unconfirmed_penalty": 4.0,
                "protection_config": StockProtectionConfig(
                    variant_name="quality_slowexit_rank50_3d",
                    atr_multiple=2.5,
                    score_break_rank=50,
                    rank_break_days=3,
                    score_decline_days=3,
                ),
                "max_carry_slots": 1,
                "carry_days_limit": 5,
                "incumbent_bonus": 2.0,
            },
            "v2_e_top10_quality_slowexit": {
                "top_n": 10,
                "candidate_pool_size": 50,
                "exclude_quality_weak": True,
                "mainline_bonus": 4.0,
                "quality_strong_bonus": 4.0,
                "high_elasticity_unconfirmed_penalty": 4.0,
                "protection_config": StockProtectionConfig(
                    variant_name="quality_top10_rank50_3d",
                    atr_multiple=2.5,
                    score_break_rank=50,
                    rank_break_days=3,
                    score_decline_days=3,
                ),
            },
        }
        preset = presets.get(self.variant_name)
        if not preset:
            return
        for key, value in preset.items():
            current = getattr(self, key)
            if current in {0, 0.0, False} or current == DEFAULT_PROTECTION_CONFIG or (
                key == "top_n" and current == 8
            ) or (key == "candidate_pool_size" and current == 30):
                object.__setattr__(self, key, value)


def default_quality_variant_configs() -> list[MidTrendQualityVariantConfig]:
    return [
        MidTrendQualityVariantConfig(variant_name="baseline", top_n=5, candidate_pool_size=20),
        MidTrendQualityVariantConfig(variant_name="v2_a_top8_only", top_n=8, candidate_pool_size=30),
        MidTrendQualityVariantConfig(
            variant_name="v2_b_top8_quality",
            top_n=8,
            candidate_pool_size=30,
            exclude_quality_weak=True,
            mainline_bonus=4.0,
            quality_strong_bonus=4.0,
            high_elasticity_unconfirmed_penalty=4.0,
        ),
        MidTrendQualityVariantConfig(
            variant_name="v2_c_top8_quality_slowexit",
            top_n=8,
            candidate_pool_size=30,
            exclude_quality_weak=True,
            mainline_bonus=4.0,
            quality_strong_bonus=4.0,
            high_elasticity_unconfirmed_penalty=4.0,
            protection_config=StockProtectionConfig(
                variant_name="quality_slowexit_rank50_3d",
                atr_multiple=2.5,
                score_break_rank=50,
                rank_break_days=3,
                score_decline_days=3,
            ),
        ),
        MidTrendQualityVariantConfig(
            variant_name="v2_d_top8_quality_slowexit_carry1",
            top_n=8,
            candidate_pool_size=30,
            exclude_quality_weak=True,
            mainline_bonus=4.0,
            quality_strong_bonus=4.0,
            high_elasticity_unconfirmed_penalty=4.0,
            protection_config=StockProtectionConfig(
                variant_name="quality_slowexit_rank50_3d",
                atr_multiple=2.5,
                score_break_rank=50,
                rank_break_days=3,
                score_decline_days=3,
            ),
            max_carry_slots=1,
            carry_days_limit=5,
            incumbent_bonus=2.0,
        ),
        MidTrendQualityVariantConfig(
            variant_name="v2_e_top10_quality_slowexit",
            top_n=10,
            candidate_pool_size=50,
            exclude_quality_weak=True,
            mainline_bonus=4.0,
            quality_strong_bonus=4.0,
            high_elasticity_unconfirmed_penalty=4.0,
            protection_config=StockProtectionConfig(
                variant_name="quality_top10_rank50_3d",
                atr_multiple=2.5,
                score_break_rank=50,
                rank_break_days=3,
                score_decline_days=3,
            ),
        ),
    ]


def rank_quality_confirmed_candidates(
    frame: pd.DataFrame,
    *,
    config: MidTrendQualityVariantConfig,
    incumbents: set[str] | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    incumbents = incumbents or set()
    result["fundamental_quality_bucket"] = result.get(
        "fundamental_quality_bucket",
        pd.Series("quality_unknown", index=result.index),
    ).fillna("quality_unknown")
    if config.exclude_quality_weak:
        result = result[~result["fundamental_quality_bucket"].eq("quality_weak")].copy()
    result["mainline_confirmed"] = result.get(
        "mainline_confirmed", pd.Series(False, index=result.index)
    ).fillna(False)
    result["selection_score"] = pd.to_numeric(
        result.get("mid_trend_funnel_score", result.get("score_total")),
        errors="coerce",
    ).fillna(0.0)
    result.loc[result["mainline_confirmed"].astype(bool), "selection_score"] += config.mainline_bonus
    result.loc[
        result["fundamental_quality_bucket"].astype(str).eq("quality_strong"),
        "selection_score",
    ] += config.quality_strong_bonus
    result.loc[
        result["fundamental_quality_bucket"].astype(str).eq("quality_unknown"),
        "selection_score",
    ] -= config.quality_unknown_penalty
    result.loc[
        result["asset_id"].astype(str).isin(incumbents),
        "selection_score",
    ] += config.incumbent_bonus
    unconfirmed_elasticity = (
        result.get("mid_trend_layer", pd.Series("", index=result.index)).astype(str).eq("high_elasticity_watch")
        & ~result["mainline_confirmed"].astype(bool)
        & ~result["fundamental_quality_bucket"].astype(str).isin(["quality_strong", "quality_neutral"])
    )
    result.loc[unconfirmed_elasticity, "selection_score"] -= config.high_elasticity_unconfirmed_penalty
    return result.sort_values(
        ["trade_date", "selection_score", "mid_trend_funnel_score", "asset_id"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)


def build_midtrend_confirmation_trade_audit(
    *,
    trade_audit: pd.DataFrame,
    funnel_detail: pd.DataFrame,
) -> pd.DataFrame:
    if trade_audit.empty:
        return pd.DataFrame()
    detail = funnel_detail.copy()
    detail["trade_date"] = pd.to_datetime(detail["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    detail["asset_id"] = detail["asset_id"].astype(str)
    keep = [
        "trade_date",
        "asset_id",
        "score_rank",
        "mid_trend_layer",
        "technical_confirmed",
        "mainline_confirmed",
        "fundamental_confirmed",
        "fundamental_quality_bucket",
        "midtrend_confirmation_state",
        "fundamental_risk_flag",
        "mainline_status",
        "industry_mainline_score_v1",
        "stock_excess_ret_20_score",
        "max_drawdown_20_score",
    ]
    for column in keep:
        if column not in detail.columns:
            detail[column] = pd.NA
    audit = trade_audit.copy()
    audit["trade_date"] = pd.to_datetime(audit["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    audit["asset_id"] = audit["asset_id"].astype(str)
    result = audit.merge(detail[keep], on=["trade_date", "asset_id"], how="left", suffixes=("", "_detail"))
    if "score_rank" not in result.columns and "score_rank_detail" in result.columns:
        result["score_rank"] = result["score_rank_detail"]
    if "mid_trend_layer" not in result.columns and "mid_trend_layer_detail" in result.columns:
        result["mid_trend_layer"] = result["mid_trend_layer_detail"]
    result["combined_confirmation_state"] = result.get("midtrend_confirmation_state", pd.Series("", index=result.index)).fillna("T0_M0_UNKNOWN_F")
    result["rank_bucket_at_trade"] = result["score_rank"].apply(_rank_bucket)
    result["hard_damage_flag"] = (
        result.get("mid_trend_layer", pd.Series("", index=result.index)).astype(str).eq("risk_exclusion_watch")
        | result.get("fundamental_risk_flag", pd.Series(False, index=result.index)).fillna(False).astype(bool)
    )
    result["exit_damage_type"] = np.where(
        result.get("action", pd.Series("", index=result.index)).astype(str).eq("sell")
        & result["hard_damage_flag"].astype(bool),
        "hard_damage_exit",
        np.where(
            result.get("action", pd.Series("", index=result.index)).astype(str).eq("sell"),
            "ranking_churn_exit",
            "",
        ),
    )
    result["winner_flag"] = pd.to_numeric(result.get("forward_return"), errors="coerce").ge(0.15)
    return result


def run_midtrend_quality_confirmed_experiment_from_frames(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    variants: list[MidTrendQualityVariantConfig] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    enriched_funnel = _build_enriched_funnel(funnel, start_date=start_date, end_date=end_date)
    prices_with_atr = _ensure_atr20(prices)
    baseline = _run_baseline(regime=regime, funnel=enriched_funnel, prices=prices_with_atr, start_date=start_date, end_date=end_date)
    configs = variants or default_quality_variant_configs()
    variant_results = [baseline]
    for config in configs:
        if config.variant_name == "baseline":
            continue
        variant_results.append(
            _run_variant(
                regime=regime,
                funnel=enriched_funnel,
                prices=prices_with_atr,
                start_date=start_date,
                end_date=end_date,
                config=config,
            )
        )

    baseline_audit = build_midtrend_confirmation_trade_audit(
        trade_audit=baseline["trade_audit"],
        funnel_detail=enriched_funnel,
    )
    _write_audit_package(output, baseline_audit)
    summary = pd.DataFrame([_variant_summary(item) for item in variant_results])
    summary.to_csv(output / "baseline_vs_quality_variants.csv", index=False)
    (output / "baseline_vs_quality_variants.md").write_text(
        summary.to_markdown(index=False) + "\n",
        encoding="utf-8",
    )
    (output / "code_audit.md").write_text(_code_audit_markdown(), encoding="utf-8")
    (output / "final_interpretation.md").write_text(
        _final_interpretation(summary, baseline_audit),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "baseline_audit": baseline_audit,
        "paths": {
            "summary_csv": str(output / "baseline_vs_quality_variants.csv"),
            "summary_md": str(output / "baseline_vs_quality_variants.md"),
            "audit_report": str(output / "midtrend_confirmation_audit_report.md"),
            "final_interpretation": str(output / "final_interpretation.md"),
        },
    }


def run_midtrend_quality_confirmed_experiment_cli(
    *,
    start_date: str,
    end_date: str,
    regime_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    from stock_research.current_mid_trend_strategy_v1 import load_current_strategy_prices

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
    return run_midtrend_quality_confirmed_experiment_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
    )


def _build_enriched_funnel(funnel: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    scoped = _filter_date_range(funnel, start_date, end_date).copy()
    detail = scoped.loc[:, ~scoped.columns.duplicated()].copy()
    if "mid_trend_layer" not in detail.columns or "mid_trend_funnel_score" not in detail.columns:
        detail = build_mid_trend_watch_funnel_from_frames(
            discovery_pool_detail=detail,
            top50_size=50,
            top10_size=10,
        )["detail"]
    return annotate_midtrend_confirmation_fields(
        detail.loc[:, ~detail.columns.duplicated()].copy()
    )


def _run_baseline(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    from stock_research.current_mid_trend_strategy_v1 import build_current_mid_trend_strategy_v1_from_frames

    result = build_current_mid_trend_strategy_v1_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        top_n=5,
    )
    trade_audit = _build_trade_audit(result["trades"], prices)
    return {
        "variant_name": "baseline",
        "equity": result["equity"],
        "summary": result["summary"],
        "holdings": result["holdings"],
        "trades": result["trades"],
        "trade_audit": trade_audit,
    }


def _run_variant(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    config: MidTrendQualityVariantConfig,
) -> dict[str, Any]:
    normalized_regime = _filter_date_range(regime, start_date, end_date)
    growth = _filter_date_range(
        build_growth_momentum_candidates(
            funnel,
            top_n=max(config.candidate_pool_size, config.top_n * 4),
        ),
        start_date,
        end_date,
    )
    exposures = _weekly_effective_exposure(normalized_regime).to_dict()
    confirmed = (
        normalized_regime.set_index("trade_date")["confirmed_regime_state"].to_dict()
        if "confirmed_regime_state" in normalized_regime.columns
        else {}
    )
    selection_rows: list[dict[str, Any]] = []
    previous_selected: set[str] = set()
    carry_days: dict[str, int] = {}
    daily_selected_assets: dict[str, set[str]] = {}
    for trade_date, day in growth.groupby("trade_date", sort=True):
        ranked = rank_quality_confirmed_candidates(day, config=config, incumbents=previous_selected)
        pool = ranked.head(config.candidate_pool_size).copy()
        base_selected = pool.head(config.top_n).copy()
        selected_assets = set(base_selected["asset_id"].astype(str))
        if config.max_carry_slots > 0:
            carry_candidates = pool[pool["asset_id"].astype(str).isin(previous_selected - selected_assets)].copy()
            carry_candidates = carry_candidates[
                carry_candidates.apply(_carry_eligible, axis=1)
            ]
            if not carry_candidates.empty:
                carry_candidates["carry_age"] = carry_candidates["asset_id"].map(carry_days).fillna(0).astype(int)
                carry_candidates = carry_candidates[carry_candidates["carry_age"] < config.carry_days_limit]
                carry_pick = carry_candidates.head(config.max_carry_slots).copy()
                base_selected = pd.concat([base_selected, carry_pick], ignore_index=True)
                selected_assets |= set(carry_pick["asset_id"].astype(str))
        daily_selected_assets[str(trade_date)] = selected_assets
        for asset_id in list(carry_days):
            if asset_id in selected_assets:
                carry_days[asset_id] = carry_days.get(asset_id, 0) + 1 if asset_id in previous_selected and asset_id not in set(pool.head(config.top_n)["asset_id"].astype(str)) else 0
            else:
                carry_days.pop(asset_id, None)
        for asset_id in selected_assets:
            carry_days.setdefault(asset_id, 0)
        invested_weight = float(exposures.get(str(trade_date), 0.6))
        for row in base_selected.sort_values(["selection_score", "asset_id"], ascending=[False, True]).to_dict("records"):
            selection_rows.append(
                {
                    "trade_date": str(trade_date),
                    "asset_id": row["asset_id"],
                    "strategy_family": config.variant_name,
                    "selection_style": "growth_momentum",
                    "invested_weight": invested_weight,
                    "confirmed_regime_state": confirmed.get(str(trade_date), ""),
                    "selection_score": row.get("selection_score", row.get("mid_trend_funnel_score", 0.0)),
                }
            )
        previous_selected = selected_assets

    selection = pd.DataFrame(selection_rows)
    protected = apply_stock_protection_to_selection(
        selection,
        prices,
        funnel,
        config.protection_config,
    )
    protected["strategy_family"] = config.variant_name
    protected["stock_protection_variant"] = config.protection_config.variant_name
    protected["confirmed_regime_state"] = protected["trade_date"].map(confirmed).fillna("")
    holdings = _build_daily_holdings(
        protected,
        funnel,
        normalized_regime,
        asset_names=None,
        protection_variant=config.protection_config.variant_name,
    )
    holdings["same_industry_selected_count"] = (
        holdings.groupby(["trade_date", "industry_name"], dropna=False)["asset_id"]
        .transform(lambda values: int(values.notna().sum()))
        .fillna(0)
        .astype(int)
    )
    equity = _simulate_equal_weight_daily(
        prices,
        protected,
        strategy_family=config.variant_name,
    )
    summary = _summarize_equity(equity)
    trades = _build_trade_changes(holdings)
    trade_audit = _build_trade_audit(trades, prices)
    holding_summary = _build_holding_summary(holdings, normalized_regime)
    annual = _period_summary(equity, "Y")
    quarterly = _period_summary(equity, "Q")
    _ = _build_industry_exposure(holdings)
    _ = holding_summary, annual, quarterly, daily_selected_assets
    return {
        "variant_name": config.variant_name,
        "equity": equity,
        "summary": summary,
        "holdings": holdings,
        "trades": trades,
        "trade_audit": trade_audit,
    }


def _carry_eligible(row: pd.Series) -> bool:
    bucket = str(row.get("fundamental_quality_bucket") or "")
    if bucket == "quality_weak":
        return False
    if str(row.get("mid_trend_layer") or "") == "risk_exclusion_watch":
        return False
    if bool(row.get("fundamental_risk_flag")):
        return False
    if not bool(row.get("technical_confirmed")):
        return False
    if not bool(row.get("mainline_confirmed")) and str(row.get("mainline_status") or "") not in {"neutral", "unknown"}:
        return False
    return (
        _num(row.get("stock_excess_ret_20_score")) >= 70.0
        and _num(row.get("max_drawdown_20_score")) >= 55.0
    )


def _build_trade_audit(trades: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    lookup = _build_forward_return_lookup(prices)
    result = trades.copy()
    result["forward_return"] = result.apply(
        lambda row: lookup.get((str(row["trade_date"]), str(row["asset_id"])), np.nan),
        axis=1,
    )
    result["audit_label"] = ""
    is_buy = result["action"].astype(str).isin(["buy", "increase"])
    is_sell = result["action"].astype(str).isin(["sell", "decrease"])
    result.loc[is_buy & pd.to_numeric(result["forward_return"], errors="coerce").lt(0.0), "audit_label"] = "bad_buy"
    result.loc[is_sell & pd.to_numeric(result["forward_return"], errors="coerce").gt(0.02), "audit_label"] = "bad_sell"
    return result


def _build_forward_return_lookup(prices: pd.DataFrame) -> dict[tuple[str, str], float]:
    if prices.empty:
        return {}
    rows: dict[tuple[str, str], float] = {}
    frame = prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    for asset_id, group in frame.sort_values(["asset_id", "trade_date"]).groupby("asset_id", sort=True):
        group = group.dropna(subset=["close"])
        if group.empty:
            continue
        final_close = float(group["close"].iloc[-1])
        last_date = str(group["trade_date"].iloc[-1])
        for item in group[["trade_date", "close"]].itertuples(index=False):
            date = str(item.trade_date)
            close = float(item.close)
            rows[(date, str(asset_id))] = np.nan if date == last_date or close <= 0 else final_close / close - 1.0
    return rows


def _write_audit_package(output: Path, audit: pd.DataFrame) -> None:
    audit.to_csv(output / "midtrend_confirmation_trade_audit.csv", index=False)
    bad_sell = audit[audit["audit_label"].astype(str).eq("bad_sell")].copy()
    bad_buy = audit[audit["audit_label"].astype(str).eq("bad_buy")].copy()
    winner = audit[audit["winner_flag"].astype(bool)].copy()
    false_hold = audit[audit.get("exit_damage_type", pd.Series(dtype=str)).astype(str).eq("ranking_churn_exit")].copy()
    _group_state(bad_sell).to_csv(output / "bad_sell_by_confirmation_state.csv", index=False)
    _group_state(bad_buy).to_csv(output / "bad_buy_by_confirmation_state.csv", index=False)
    _group_state(winner).to_csv(output / "winner_by_confirmation_state.csv", index=False)
    _group_state(false_hold).to_csv(output / "false_hold_by_confirmation_state.csv", index=False)
    bad_sell.sort_values("forward_return", ascending=False).head(50).to_csv(output / "top_bad_sell_examples.csv", index=False)
    bad_buy.sort_values("forward_return", ascending=True).head(50).to_csv(output / "top_bad_buy_examples.csv", index=False)
    winner.sort_values("forward_return", ascending=False).head(50).to_csv(output / "top_true_winner_examples.csv", index=False)
    _carry_summary(audit).to_csv(output / "suppressed_exit_or_carry_analysis.csv", index=False)
    (output / "midtrend_confirmation_audit_report.md").write_text(
        _audit_report_markdown(audit),
        encoding="utf-8",
    )


def _group_state(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["combined_confirmation_state", "sample_count", "avg_forward_return"])
    grouped = (
        frame.groupby("combined_confirmation_state", as_index=False)
        .agg(
            sample_count=("asset_id", "size"),
            avg_forward_return=("forward_return", "mean"),
        )
        .sort_values(["sample_count", "combined_confirmation_state"], ascending=[False, True])
        .reset_index(drop=True)
    )
    return grouped


def _carry_summary(audit: pd.DataFrame) -> pd.DataFrame:
    if audit.empty or "exit_damage_type" not in audit.columns:
        return pd.DataFrame(columns=["metric", "value"])
    ranking = audit[audit["exit_damage_type"].astype(str).eq("ranking_churn_exit")]
    return pd.DataFrame(
        [
            {"metric": "saved_winner_gain", "value": float(pd.to_numeric(ranking["forward_return"], errors="coerce").clip(lower=0).sum())},
            {"metric": "false_hold_loss", "value": float(pd.to_numeric(ranking["forward_return"], errors="coerce").clip(upper=0).sum())},
        ]
    )


def _variant_summary(item: dict[str, Any]) -> dict[str, Any]:
    equity = item["equity"].copy()
    trades = item["trade_audit"].copy()
    summary = item["summary"].iloc[0].to_dict() if not item["summary"].empty else {}
    exposure = pd.to_numeric(equity.get("invested_weight"), errors="coerce").fillna(0.0) if not equity.empty else pd.Series(dtype=float)
    trade_forward = pd.to_numeric(trades.get("forward_return"), errors="coerce")
    winners = trade_forward[trade_forward > 0]
    losers = trade_forward[trade_forward < 0]
    return {
        "variant_name": item["variant_name"],
        "total_return": float(summary.get("total_return", 0.0) or 0.0),
        "annualized_return": float(summary.get("annualized_return", 0.0) or 0.0),
        "max_drawdown": float(summary.get("max_drawdown", 0.0) or 0.0),
        "sharpe_ratio": _sharpe(equity),
        "win_rate": float((trade_forward > 0).mean()) if len(trade_forward) else 0.0,
        "avg_winner": float(winners.mean()) if not winners.empty else 0.0,
        "avg_loser": float(losers.mean()) if not losers.empty else 0.0,
        "profit_factor": float(winners.sum() / abs(losers.sum())) if not winners.empty and not losers.empty and abs(losers.sum()) > 0 else 0.0,
        "total_trades": int(len(trades)),
        "turnover": float(pd.to_numeric(trades.get("delta_weight"), errors="coerce").abs().sum()) if not trades.empty else 0.0,
        "avg_holding_days": 0.0,
        "median_holding_days": 0.0,
        "average_exposure": float(exposure.mean()) if not exposure.empty else 0.0,
        "cash_weight_avg": float((1.0 - exposure).mean()) if not exposure.empty else 1.0,
        "return_per_unit_exposure": float(summary.get("total_return", 0.0) or 0.0) / max(float(exposure.mean()) if not exposure.empty else 0.0, 1e-12),
        "top_10_winners_contribution": float(winners.sort_values(ascending=False).head(10).sum()) if not winners.empty else 0.0,
        "top_20_winners_contribution": float(winners.sort_values(ascending=False).head(20).sum()) if not winners.empty else 0.0,
        "bad_buy_count": int(trades["audit_label"].astype(str).eq("bad_buy").sum()) if not trades.empty else 0,
        "bad_buy_rate": float(trades["audit_label"].astype(str).eq("bad_buy").mean()) if not trades.empty else 0.0,
        "bad_sell_count": int(trades["audit_label"].astype(str).eq("bad_sell").sum()) if not trades.empty else 0,
        "bad_sell_rate": float(trades["audit_label"].astype(str).eq("bad_sell").mean()) if not trades.empty else 0.0,
        "weighted_bad_buy_loss": float(trades.loc[trades["audit_label"].astype(str).eq("bad_buy"), "forward_return"].sum()) if not trades.empty else 0.0,
        "weighted_bad_sell_opportunity": float(trades.loc[trades["audit_label"].astype(str).eq("bad_sell"), "forward_return"].sum()) if not trades.empty else 0.0,
        "false_hold_loss": 0.0,
        "saved_winner_gain": 0.0,
    }


def _sharpe(equity: pd.DataFrame) -> float:
    if equity.empty:
        return 0.0
    values = pd.to_numeric(equity.get("daily_return"), errors="coerce").dropna()
    if len(values) <= 1 or float(values.std(ddof=1)) <= 0.0:
        return 0.0
    return float(values.mean() / values.std(ddof=1) * np.sqrt(252.0))


def _audit_report_markdown(audit: pd.DataFrame) -> str:
    bad_sell = audit[audit["audit_label"].astype(str).eq("bad_sell")]
    bad_buy = audit[audit["audit_label"].astype(str).eq("bad_buy")]
    winner = audit[audit["winner_flag"].astype(bool)]
    lines = [
        "# Midtrend Confirmation Audit Report",
        "",
        "## Findings",
        f"- bad_sells concentrated in: {_top_state(bad_sell)}",
        f"- bad_buys concentrated in: {_top_state(bad_buy)}",
        f"- winners concentrated in: {_top_state(winner)}",
        f"- bad_sells still top20 or better when sold: {int(pd.to_numeric(bad_sell.get('score_rank'), errors='coerce').le(20).sum()) if not bad_sell.empty else 0}",
        f"- bad_sells by hard damage: {int(bad_sell.get('exit_damage_type', pd.Series(dtype=str)).astype(str).eq('hard_damage_exit').sum()) if not bad_sell.empty else 0}",
        f"- bad_sells by ranking churn: {int(bad_sell.get('exit_damage_type', pd.Series(dtype=str)).astype(str).eq('ranking_churn_exit').sum()) if not bad_sell.empty else 0}",
        f"- fundamental quality known rows: {int((~audit.get('fundamental_quality_bucket', pd.Series(dtype=str)).astype(str).eq('quality_unknown')).sum()) if not audit.empty else 0}",
        "",
        "## Missing Fundamental Fields",
        "- The experiment degrades missing PIT fundamental fields to `quality_unknown` and does not award a quality bonus when they are missing.",
    ]
    return "\n".join(lines) + "\n"


def _top_state(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "none"
    counts = frame["combined_confirmation_state"].astype(str).value_counts()
    return str(counts.index[0]) if not counts.empty else "none"


def _rank_bucket(value: Any) -> str:
    rank = _num(value)
    if np.isnan(rank):
        return "unknown"
    if rank <= 20:
        return "top_20"
    if rank <= 50:
        return "top_50"
    if rank <= 100:
        return "top_100"
    return "over_100"


def _num(value: Any) -> float:
    series = pd.to_numeric(pd.Series([value]), errors="coerce")
    return float(series.iloc[0]) if not pd.isna(series.iloc[0]) else np.nan


def _code_audit_markdown() -> str:
    return "\n".join(
        [
            "# Code Audit",
            "",
            "- baseline entrypoint: `build_current_mid_trend_strategy_v1_from_frames`",
            "- experimental module: `stock_research.midtrend_quality_confirmed_v1`",
            "- selection changes: candidate pool expansion, mainline bonus, quality bonus, quality_weak exclusion, optional carry slots",
            "- unchanged baseline knobs: `top_n=5`, `C2_atr2p5_rank20`, `rank_break_days=1`, `score_decline_days=2`",
            "- no bottleneck evidence fields are imported into Mid Trend logic",
        ]
    ) + "\n"


def _final_interpretation(summary: pd.DataFrame, audit: pd.DataFrame) -> str:
    lines = [
        "# Final Interpretation",
        "",
        f"1. Is top_n=5 too narrow? {'inconclusive' if summary.empty else 'compare top8/top10 against baseline in baseline_vs_quality_variants.csv'}",
        "2. Does top_n=8 or 10 improve the strategy without destroying winner concentration? See summary table.",
        "3. Is current rank_break_days=1 too fast for Mid Trend? Slow-exit variants test that directly.",
        "4. Does basic quantitative fundamental quality help separate true winners from bad buys/false holds? Only where PIT data is available; missing rows stay `quality_unknown`.",
        f"5. Are bad_sells mostly true confirmed trends sold too early, or damaged stocks? Top baseline bad_sell state: {_top_state(audit[audit['audit_label'].astype(str).eq('bad_sell')]) if not audit.empty else 'none'}",
        f"6. Are bad_buys mostly unconfirmed technical strength? Top baseline bad_buy state: {_top_state(audit[audit['audit_label'].astype(str).eq('bad_buy')]) if not audit.empty else 'none'}",
        f"7. Which variant, if any, beats baseline? {summary.sort_values('total_return', ascending=False).iloc[0]['variant_name'] if not summary.empty else 'none'}",
        "8. If no variant beats baseline, reject generic hold extension and keep narrowing toward confirmed-winner carry rather than broad ownership suppression.",
    ]
    return "\n".join(lines) + "\n"
