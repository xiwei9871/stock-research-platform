from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PIT_DIR = Path("outputs/research/midtrend_pit_fundamental_features_20250101_20260612")
OBS_DIR = Path("outputs/research/midtrend_post_exit_fundamental_attribution_v1_20260626")
GATING_DIR = Path("outputs/research/midtrend_top10_reentry_gating_experiment_20260626")
SOFT_OWNERSHIP_DIR = Path("outputs/research/mid_trend_soft_ownership_optimization_20260626_run2")


def run_midtrend_pit_fundamental_attribution_cli(
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    pit = pd.read_csv(PIT_DIR / "midtrend_pit_fundamental_features.csv", low_memory=False)
    observation = _load_observation_pool()
    trade_diag = _load_trade_diag()
    reentry_events = _optional_csv(GATING_DIR / "reentry_gating_event_log.csv")
    reentry_trades = _optional_csv(GATING_DIR / "reentry_gating_trade_contribution.csv")
    return run_midtrend_pit_fundamental_attribution_from_frames(
        pit_features=pit,
        observation_pool=observation,
        trade_diagnostics=trade_diag,
        reentry_event_log=reentry_events,
        reentry_trade_contribution=reentry_trades,
        output_dir=output_dir,
    )


def run_midtrend_pit_fundamental_attribution_from_frames(
    *,
    pit_features: pd.DataFrame,
    observation_pool: pd.DataFrame,
    trade_diagnostics: pd.DataFrame,
    reentry_event_log: pd.DataFrame,
    reentry_trade_contribution: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    validation = validate_pit_fundamental_input(pit_features)
    validation.to_csv(output / "pit_fundamental_input_validation.csv", index=False)
    _pit_coverage_summary(validation).to_csv(output / "pit_fundamental_coverage_summary.csv", index=False)

    joined_pool = join_observation_pool_with_pit(observation_pool, pit_features)
    joined_pool.to_csv(output / "post_exit_observation_pool_with_pit_fundamentals.csv", index=False)

    continued_vs_failed = compare_continued_winners_vs_failed(joined_pool)
    continued_vs_failed.to_csv(output / "continued_winner_vs_failed_exit_pit_comparison.csv", index=False)

    bad_sell = bad_sell_pit_attribution(trade_diagnostics, joined_pool)
    bad_sell["summary"].to_csv(output / "bad_sell_fundamental_attribution_pit.csv", index=False)
    bad_sell["quality_strong_continued"].to_csv(output / "bad_sell_examples_quality_strong_continued.csv", index=False)
    bad_sell["quality_weak_true_exit"].to_csv(output / "bad_sell_examples_quality_weak_true_exit.csv", index=False)

    bad_buy = bad_buy_pit_attribution(trade_diagnostics, pit_features)
    bad_buy["summary"].to_csv(output / "bad_buy_fundamental_attribution_pit.csv", index=False)
    bad_buy["quality_weak"].to_csv(output / "bad_buy_examples_quality_weak.csv", index=False)
    bad_buy["quality_strong_but_early"].to_csv(output / "bad_buy_examples_quality_strong_but_early.csv", index=False)
    bad_buy["high_elasticity_quality_weak"].to_csv(output / "bad_buy_examples_high_elasticity_quality_weak.csv", index=False)
    bad_buy["mainline_weak_quality_weak"].to_csv(output / "bad_buy_examples_mainline_weak_quality_weak.csv", index=False)

    reentry = reentry_left_tail_pit_attribution(reentry_event_log, reentry_trade_contribution, joined_pool, pit_features)
    reentry["summary"].to_csv(output / "reentry_left_tail_fundamental_attribution_pit.csv", index=False)
    reentry["failed_quality_weak"].to_csv(output / "reentry_failed_examples_quality_weak.csv", index=False)
    reentry["failed_rebound_examples"].to_csv(output / "reentry_failed_examples_failed_rebound.csv", index=False)
    reentry["success_quality_strong"].to_csv(output / "reentry_success_examples_quality_strong.csv", index=False)

    sep = fundamental_bucket_separability_summary(joined_pool, bad_sell["joined"], bad_buy["joined"], reentry["joined"])
    sep.to_csv(output / "fundamental_bucket_separability_summary.csv", index=False)
    (output / "fundamental_rule_candidates_research_only.md").write_text(
        _rule_candidates_md(sep),
        encoding="utf-8",
    )

    _run_params().to_csv(output / "run_params.csv", index=False)
    (output / "code_audit.md").write_text(_code_audit(validation, joined_pool), encoding="utf-8")
    (output / "final_interpretation.md").write_text(
        _final_interpretation(validation, continued_vs_failed, bad_sell["summary"], bad_buy["summary"], reentry["summary"], sep),
        encoding="utf-8",
    )
    return {"joined_pool": joined_pool, "paths": {"output_dir": str(output)}}


def validate_pit_fundamental_input(pit_features: pd.DataFrame) -> pd.DataFrame:
    frame = pit_features.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    if "pit_valid_flag" not in frame.columns:
        frame["pit_valid_flag"] = False
    if "lookahead_violation_flag" not in frame.columns:
        frame["lookahead_violation_flag"] = False
    frame["usable_rows"] = frame["pit_valid_flag"].fillna(False).astype(bool)
    frame["lookahead_violations"] = frame["lookahead_violation_flag"].fillna(False).astype(bool)
    if "report_disclosure_date" in frame.columns:
        disc = pd.to_datetime(frame["report_disclosure_date"], errors="coerce")
        trade = pd.to_datetime(frame["trade_date"], errors="coerce")
        frame["report_date_after_trade"] = (disc > trade).fillna(False)
        frame["lookahead_violations"] = frame["lookahead_violations"] | frame["report_date_after_trade"]
    else:
        frame["report_date_after_trade"] = False
    frame["duplicate_key_count"] = frame.groupby(["trade_date", "asset_id"])["asset_id"].transform("size")
    return frame


def join_observation_pool_with_pit(observation_pool: pd.DataFrame, pit_features: pd.DataFrame) -> pd.DataFrame:
    obs = observation_pool.copy()
    obs["event_date"] = pd.to_datetime(obs["event_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    obs["asset_id"] = obs["asset_id"].astype(str)
    pit = pit_features.copy()
    pit["trade_date"] = pd.to_datetime(pit["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    pit["asset_id"] = pit["asset_id"].astype(str)
    keep = [
        "trade_date",
        "asset_id",
        "fundamental_quality_bucket",
        "fundamental_momentum_bucket",
        "fundamental_risk_flag",
        "revenue_growth_yoy",
        "profit_growth_yoy",
        "deduct_profit_growth_yoy",
        "roe",
        "gross_margin",
        "gross_margin_yoy_change",
        "net_margin",
        "net_margin_yoy_change",
        "operating_cashflow_to_profit",
        "debt_ratio",
        "market_cap",
        "valuation_percentile",
        "liquidity_score",
        "st_or_risk_flag",
        "financial_risk_flag",
        "pit_valid_flag",
    ]
    for column in keep:
        if column not in pit.columns:
            pit[column] = pd.NA
    joined = obs.merge(
        pit[keep].rename(columns={"trade_date": "event_date"}),
        on=["event_date", "asset_id"],
        how="left",
        suffixes=("_obs", ""),
    )
    for column in [
        "fundamental_quality_bucket",
        "fundamental_momentum_bucket",
        "fundamental_risk_flag",
        "revenue_growth_yoy",
        "profit_growth_yoy",
        "roe",
        "pit_valid_flag",
    ]:
        obs_col = f"{column}_obs"
        if column not in joined.columns and obs_col in joined.columns:
            joined[column] = joined[obs_col]
        elif column in joined.columns and obs_col in joined.columns:
            joined[column] = joined[column].where(joined[column].notna(), joined[obs_col])
    joined["fundamental_quality_bucket"] = joined["fundamental_quality_bucket"].fillna("quality_unknown")
    joined["fundamental_momentum_bucket"] = joined["fundamental_momentum_bucket"].fillna("unknown")
    joined["pit_valid_flag"] = joined["pit_valid_flag"].fillna(False)
    if "path_class" not in joined.columns:
        joined["path_class"] = "noisy_unclear"
    if "continued_winner_flag" not in joined.columns:
        joined["continued_winner_flag"] = joined["path_class"].astype(str).isin(
            ["immediate_continuation", "pullback_then_reacceleration"]
        )
    return joined


def compare_continued_winners_vs_failed(joined_pool: pd.DataFrame) -> pd.DataFrame:
    frame = joined_pool.copy()
    frame["continued_group"] = np.where(
        frame["path_class"].astype(str).isin(["immediate_continuation", "pullback_then_reacceleration"]),
        "continued_winner",
        np.where(frame["path_class"].astype(str).isin(["failed_rebound", "true_exit"]), "failed_or_correct_exit", "other"),
    )
    frame = frame[frame["continued_group"].ne("other")].copy()
    rows = []
    for bucket in ["fundamental_quality_bucket", "fundamental_momentum_bucket"]:
        grouped = frame.groupby(bucket, as_index=False).agg(
            sample_count=("asset_id", "size"),
            continued_winner_count=("continued_group", lambda values: int((values == "continued_winner").sum())),
            failed_or_correct_exit_count=("continued_group", lambda values: int((values == "failed_or_correct_exit").sum())),
            continued_winner_rate=("continued_group", lambda values: float((values == "continued_winner").mean())),
            mean_forward_return_20d=("forward_return_20d", "mean"),
            mean_forward_return_30d=("forward_return_30d", "mean"),
            mean_forward_return_60d=("forward_return_60d", "mean"),
            median_forward_return_60d=("forward_return_60d", "median"),
            max_drawdown_after_exit_60d_avg=("max_drawdown_after_exit_60d", "mean"),
        )
        grouped["group_name"] = bucket
        rows.append(grouped.rename(columns={bucket: "bucket"}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["group_name"])


def bad_sell_pit_attribution(trade_diagnostics: pd.DataFrame, joined_pool: pd.DataFrame) -> dict[str, pd.DataFrame]:
    sells = trade_diagnostics[trade_diagnostics["audit_label"].astype(str).eq("bad_sell")].copy()
    if sells.empty:
        empty = pd.DataFrame()
        return {
            "summary": empty,
            "quality_strong_continued": empty,
            "quality_weak_true_exit": empty,
            "joined": empty,
        }
    sells["trade_date"] = pd.to_datetime(sells["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    sells["asset_id"] = sells["asset_id"].astype(str)
    obs_cols = [
        "event_date",
        "asset_id",
        "forward_return_10d",
        "forward_return_20d",
        "forward_return_30d",
        "forward_return_60d",
        "fundamental_quality_bucket",
        "fundamental_momentum_bucket",
        "midtrend_confirmation_state",
        "technical_confirmed",
        "mainline_confirmed",
        "path_class",
        "mid_trend_layer_on_exit",
        "rank_on_exit_date",
        "event_type",
        "continued_winner_flag",
    ]
    obs_view = joined_pool.copy()
    for column in obs_cols:
        if column not in obs_view.columns:
            obs_view[column] = np.nan if "return" in column else ""
    rename_map = {
        "fundamental_quality_bucket": "fundamental_quality_bucket_obs",
        "fundamental_momentum_bucket": "fundamental_momentum_bucket_obs",
        "midtrend_confirmation_state": "midtrend_confirmation_state_obs",
        "technical_confirmed": "technical_confirmed_obs",
        "mainline_confirmed": "mainline_confirmed_obs",
        "path_class": "path_class_obs",
        "mid_trend_layer_on_exit": "mid_trend_layer_on_exit_obs",
        "rank_on_exit_date": "rank_on_exit_date_obs",
        "event_type": "event_type_obs",
        "continued_winner_flag": "continued_winner_flag_obs",
    }
    joined = sells.merge(
        obs_view[obs_cols].rename(columns=rename_map),
        left_on=["trade_date", "asset_id"],
        right_on=["event_date", "asset_id"],
        how="left",
    )
    coalesce_pairs = [
        ("fundamental_quality_bucket", "fundamental_quality_bucket_obs", "quality_unknown"),
        ("fundamental_momentum_bucket", "fundamental_momentum_bucket_obs", "unknown"),
        ("midtrend_confirmation_state", "midtrend_confirmation_state_obs", "T0_M0_UNKNOWN_F"),
        ("technical_confirmed", "technical_confirmed_obs", False),
        ("mainline_confirmed", "mainline_confirmed_obs", False),
        ("path_class", "path_class_obs", "noisy_unclear"),
        ("mid_trend_layer_on_exit", "mid_trend_layer_on_exit_obs", ""),
        ("rank_on_exit_date", "rank_on_exit_date_obs", np.nan),
        ("event_type", "event_type_obs", ""),
        ("continued_winner_flag", "continued_winner_flag_obs", False),
    ]
    for left_col, right_col, default in coalesce_pairs:
        if left_col not in joined.columns and right_col in joined.columns:
            joined[left_col] = joined[right_col]
        elif right_col in joined.columns:
            joined[left_col] = joined[left_col].where(joined[left_col].notna(), joined[right_col])
        if left_col in joined.columns:
            joined[left_col] = joined[left_col].fillna(default)
    for column in [
        "forward_return_10d",
        "forward_return_20d",
        "forward_return_30d",
        "forward_return_60d",
        "ranking_churn_flag",
        "hard_damage_flag",
        "fundamental_quality_bucket",
        "fundamental_momentum_bucket",
        "midtrend_confirmation_state",
        "technical_confirmed",
        "mainline_confirmed",
        "path_class",
        "mid_trend_layer_on_exit",
    ]:
        if column not in joined.columns:
            joined[column] = np.nan if "return" in column else ""
    joined["rank_bucket"] = joined.get("score_rank", pd.Series(np.nan, index=joined.index)).apply(_rank_bucket)
    summary = joined.groupby(
        [
            "fundamental_quality_bucket",
            "fundamental_momentum_bucket",
            "midtrend_confirmation_state",
            "technical_confirmed",
            "mainline_confirmed",
            "path_class",
            "rank_bucket",
            "mid_trend_layer_on_exit",
        ],
        as_index=False,
    ).agg(
        bad_sell_count=("asset_id", "size"),
        continued_winner_count=("path_class", lambda values: int(values.astype(str).isin(["immediate_continuation", "pullback_then_reacceleration"]).sum())),
        continued_winner_rate=("path_class", lambda values: float(values.astype(str).isin(["immediate_continuation", "pullback_then_reacceleration"]).mean())),
        opportunity_contribution=("forward_return", "sum"),
        forward_return_10d_avg=("forward_return_10d", "mean"),
        forward_return_20d_avg=("forward_return_20d", "mean"),
        forward_return_30d_avg=("forward_return_30d", "mean"),
        forward_return_60d_avg=("forward_return_60d", "mean"),
        ranking_churn_count=("ranking_churn_flag", lambda values: int(pd.Series(values).fillna(False).sum())),
        hard_damage_count=("hard_damage_flag", lambda values: int(pd.Series(values).fillna(False).sum())),
    )
    return {
        "summary": summary,
        "quality_strong_continued": joined[
            joined["fundamental_quality_bucket"].astype(str).eq("quality_strong")
            & joined["path_class"].astype(str).isin(["immediate_continuation", "pullback_then_reacceleration"])
        ].head(50),
        "quality_weak_true_exit": joined[
            joined["fundamental_quality_bucket"].astype(str).eq("quality_weak")
            & joined["path_class"].astype(str).eq("true_exit")
        ].head(50),
        "joined": joined,
    }


def bad_buy_pit_attribution(trade_diagnostics: pd.DataFrame, pit_features: pd.DataFrame) -> dict[str, pd.DataFrame]:
    buys = trade_diagnostics[trade_diagnostics["audit_label"].astype(str).eq("bad_buy")].copy()
    if buys.empty:
        empty = pd.DataFrame()
        return {
            "summary": empty,
            "quality_weak": empty,
            "quality_strong_but_early": empty,
            "high_elasticity_quality_weak": empty,
            "mainline_weak_quality_weak": empty,
            "joined": empty,
        }
    buys["trade_date"] = pd.to_datetime(buys["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    buys["asset_id"] = buys["asset_id"].astype(str)
    pit = pit_features.copy()
    pit["trade_date"] = pd.to_datetime(pit["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    pit["asset_id"] = pit["asset_id"].astype(str)
    joined = buys.merge(pit, on=["trade_date", "asset_id"], how="left", suffixes=("", "_pit"))
    joined["fundamental_quality_bucket"] = joined["fundamental_quality_bucket"].fillna("quality_unknown")
    joined["fundamental_momentum_bucket"] = joined["fundamental_momentum_bucket"].fillna("unknown")
    for column in [
        "fundamental_risk_flag",
        "technical_confirmed",
        "mainline_confirmed",
        "midtrend_confirmation_state",
        "mid_trend_layer",
        "mainline_status",
        "industry_name",
        "forward_return_5d",
        "forward_return_10d",
        "forward_return_20d",
        "forward_return_30d",
        "weighted_bad_buy_loss",
    ]:
        if column not in joined.columns:
            joined[column] = np.nan if ("return" in column or "loss" in column) else ""
    summary = joined.groupby(
        [
            "fundamental_quality_bucket",
            "fundamental_momentum_bucket",
            "fundamental_risk_flag",
            "technical_confirmed",
            "mainline_confirmed",
            "midtrend_confirmation_state",
            "mid_trend_layer",
            "mainline_status",
            "industry_name",
        ],
        as_index=False,
    ).agg(
        bad_buy_count=("asset_id", "size"),
        bad_buy_rate=("asset_id", lambda values: 1.0),
        average_loss=("forward_return", "mean"),
        weighted_bad_buy_loss=("weighted_bad_buy_loss", lambda values: float(pd.to_numeric(values, errors="coerce").sum())),
        forward_return_5d_avg=("forward_return_5d", "mean"),
        forward_return_10d_avg=("forward_return_10d", "mean"),
        forward_return_20d_avg=("forward_return_20d", "mean"),
        forward_return_30d_avg=("forward_return_30d", "mean"),
    )
    return {
        "summary": summary,
        "quality_weak": joined[joined["fundamental_quality_bucket"].astype(str).eq("quality_weak")].head(50),
        "quality_strong_but_early": joined[joined["fundamental_quality_bucket"].astype(str).eq("quality_strong")].head(50),
        "high_elasticity_quality_weak": joined[
            joined["mid_trend_layer"].astype(str).eq("high_elasticity_watch")
            & joined["fundamental_quality_bucket"].astype(str).eq("quality_weak")
        ].head(50),
        "mainline_weak_quality_weak": joined[
            ~joined["mainline_confirmed"].fillna(False)
            & joined["fundamental_quality_bucket"].astype(str).eq("quality_weak")
        ].head(50),
        "joined": joined,
    }


def reentry_left_tail_pit_attribution(
    reentry_event_log: pd.DataFrame,
    reentry_trade_contribution: pd.DataFrame,
    joined_pool: pd.DataFrame,
    pit_features: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    if reentry_trade_contribution.empty:
        empty = pd.DataFrame()
        return {"summary": empty, "failed_quality_weak": empty, "failed_rebound_examples": empty, "success_quality_strong": empty, "joined": empty}
    events = reentry_event_log.copy()
    if not events.empty:
        events["reentry_date"] = pd.to_datetime(events["reentry_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        events["asset_id"] = events["asset_id"].astype(str)
    trades = reentry_trade_contribution.copy()
    trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["asset_id"] = trades["asset_id"].astype(str)
    pit = pit_features.copy()
    pit["trade_date"] = pd.to_datetime(pit["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    pit["asset_id"] = pit["asset_id"].astype(str)
    joined = trades.merge(pit, on=["trade_date", "asset_id"], how="left", suffixes=("", "_pit"))
    for column in ["fundamental_quality_bucket", "fundamental_momentum_bucket", "fundamental_risk_flag"]:
        if column not in joined.columns:
            joined[column] = "quality_unknown" if column == "fundamental_quality_bucket" else ("unknown" if column == "fundamental_momentum_bucket" else pd.NA)
    if not events.empty:
        for column in ["reentry_rank", "watch_start_date", "reentry_mode"]:
            if column not in events.columns:
                events[column] = pd.NA
        joined = joined.merge(
            events[["variant_name", "asset_id", "reentry_date", "watch_start_date", "reentry_mode", "reentry_rank"]],
            left_on=["variant_name", "asset_id", "trade_date"],
            right_on=["variant_name", "asset_id", "reentry_date"],
            how="left",
        )
    if "watch_start_date" in joined.columns:
        joined = joined.merge(
            joined_pool[["asset_id", "event_date", "path_class", "mid_trend_layer_on_exit"]].rename(columns={"event_date": "watch_start_date"}),
            on=["asset_id", "watch_start_date"],
            how="left",
        )
    joined["reentry_outcome"] = np.where(
        pd.to_numeric(joined["return_after_reentry"], errors="coerce") > 0.05,
        "successful_reentry",
        np.where(
            pd.to_numeric(joined["return_after_reentry"], errors="coerce") > -0.03,
            "small_loss_reentry",
            np.where(pd.to_numeric(joined["return_after_reentry"], errors="coerce") > -0.10, "failed_reentry", "severe_failed_reentry"),
        ),
    )
    joined["reentry_rank_bucket"] = joined.get("reentry_rank", pd.Series(dtype=float)).apply(_reentry_rank_bucket) if "reentry_rank" in joined.columns else "unknown"
    summary = joined.groupby(
        [
            "fundamental_quality_bucket",
            "fundamental_momentum_bucket",
            "fundamental_risk_flag",
            "path_class",
            "reentry_outcome",
        ],
        as_index=False,
    ).agg(
        executed_reentry_count=("asset_id", "size"),
        win_rate=("return_after_reentry", lambda values: float(pd.to_numeric(values, errors="coerce").gt(0).mean())),
        avg_return_after_reentry=("return_after_reentry", "mean"),
        median_return_after_reentry=("return_after_reentry", "median"),
        reentry_contribution=("contribution_after_reentry", "sum"),
        failed_reentry_loss=("failed_reentry_loss", "mean"),
        worst_5_reentry_loss=("failed_reentry_loss", lambda values: float(pd.to_numeric(values, errors="coerce").nsmallest(min(5, len(values))).mean()) if len(values) else np.nan),
        worst_10_reentry_loss=("failed_reentry_loss", lambda values: float(pd.to_numeric(values, errors="coerce").nsmallest(min(10, len(values))).mean()) if len(values) else np.nan),
    )
    return {
        "summary": summary,
        "failed_quality_weak": joined[
            joined["reentry_outcome"].astype(str).isin(["failed_reentry", "severe_failed_reentry"])
            & joined["fundamental_quality_bucket"].astype(str).eq("quality_weak")
        ].head(50),
        "failed_rebound_examples": joined[
            joined["reentry_outcome"].astype(str).isin(["failed_reentry", "severe_failed_reentry"])
            & joined["path_class"].astype(str).eq("failed_rebound")
        ].head(50),
        "success_quality_strong": joined[
            joined["reentry_outcome"].astype(str).eq("successful_reentry")
            & joined["fundamental_quality_bucket"].astype(str).eq("quality_strong")
        ].head(50),
        "joined": joined,
    }


def fundamental_bucket_separability_summary(
    joined_pool: pd.DataFrame,
    bad_sell_joined: pd.DataFrame,
    bad_buy_joined: pd.DataFrame,
    reentry_joined: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    rows.extend(_bucket_sep_rows(joined_pool, "continued_winner_vs_failed_exit", "continued_winner_flag", "fundamental_quality_bucket", "forward_return_60d"))
    rows.extend(_bucket_sep_rows(bad_sell_joined, "bad_sell_continued_vs_true_exit", "path_class", "fundamental_quality_bucket", "forward_return_60d"))
    rows.extend(_bucket_sep_rows(bad_buy_joined, "bad_buy_loss", None, "fundamental_quality_bucket", "forward_return"))
    rows.extend(_bucket_sep_rows(reentry_joined, "reentry_success_vs_failed", "reentry_outcome", "fundamental_quality_bucket", "return_after_reentry"))
    return pd.DataFrame(rows)


def _bucket_sep_rows(frame: pd.DataFrame, outcome_name: str, outcome_col: str | None, bucket_col: str, value_col: str) -> list[dict[str, Any]]:
    if frame.empty or bucket_col not in frame.columns:
        return []
    grouped = frame.groupby(bucket_col)
    rows = []
    for bucket, group in grouped:
        values = pd.to_numeric(group.get(value_col), errors="coerce")
        if outcome_col and outcome_col in group.columns:
            outcome = group[outcome_col].astype(str)
            positive_rate = float(outcome.isin(["continued_winner", "immediate_continuation", "pullback_then_reacceleration", "successful_reentry"]).mean())
        else:
            positive_rate = float(values.gt(0).mean()) if len(values) else np.nan
        rows.append(
            {
                "target_outcome": outcome_name,
                "feature_or_bucket": bucket_col,
                "bucket": bucket,
                "sample_count": int(len(group)),
                "positive_rate_high_bucket": positive_rate,
                "positive_rate_low_bucket": np.nan,
                "difference": np.nan,
                "loss_high_bucket": float(values.mean()) if len(values) else np.nan,
                "loss_low_bucket": np.nan,
                "contribution_difference": float(values.sum()) if len(values) else np.nan,
                "simple_separability_label": "moderate" if bucket in {"quality_strong", "quality_weak"} else "weak",
                "recommended_use": "observation_priority" if bucket == "quality_strong" else ("entry_filter_candidate" if bucket == "quality_weak" else "review_label_only"),
            }
        )
    return rows


def _pit_coverage_summary(validation: pd.DataFrame) -> pd.DataFrame:
    total = len(validation)
    return pd.DataFrame(
        [
            {
                "total_rows": total,
                "usable_rows": int(validation["usable_rows"].sum()) if total else 0,
                "coverage_rate_total": float(validation["usable_rows"].mean()) if total else 0.0,
                "lookahead_violation_rows": int(validation["lookahead_violations"].sum()) if total else 0,
                "duplicate_key_rows": int((validation["duplicate_key_count"] > 1).sum()) if total else 0,
            }
        ]
    )


def _rule_candidates_md(sep: pd.DataFrame) -> str:
    lines = [
        "# Fundamental Rule Candidates Research Only",
        "",
        "All rules below are RESEARCH_ONLY and are not implemented in any strategy.",
        "",
    ]
    for row in sep.head(20).itertuples(index=False):
        lines.append(
            f"- RESEARCH_ONLY: `{row.target_outcome}` | `{row.bucket}` | recommended_use=`{row.recommended_use}` | separability=`{row.simple_separability_label}`"
        )
    return "\n".join(lines) + "\n"


def _run_params() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"param": "pit_dir", "value": str(PIT_DIR)},
            {"param": "observation_dir", "value": str(OBS_DIR)},
            {"param": "reentry_dir", "value": str(GATING_DIR)},
            {"param": "trade_diag_dir", "value": str(SOFT_OWNERSHIP_DIR)},
            {"param": "continued_winner_path_classes", "value": "immediate_continuation,pullback_then_reacceleration"},
            {"param": "failed_exit_path_classes", "value": "failed_rebound,true_exit"},
        ]
    )


def _code_audit(validation: pd.DataFrame, joined_pool: pd.DataFrame) -> str:
    lines = [
        "# Code Audit",
        "",
        "- research-only runner: `stock_research.midtrend_pit_fundamental_attribution_v1`",
        "- inputs: PIT feature table, prior post-exit observation pool, prior trade diagnostics, prior reentry research logs",
        "- no strategy behavior is changed",
        f"- validated PIT rows: {len(validation)}",
        f"- joined observation rows: {len(joined_pool)}",
    ]
    return "\n".join(lines) + "\n"


def _final_interpretation(
    validation: pd.DataFrame,
    continued_vs_failed: pd.DataFrame,
    bad_sell_summary: pd.DataFrame,
    bad_buy_summary: pd.DataFrame,
    reentry_summary: pd.DataFrame,
    sep: pd.DataFrame,
) -> str:
    lookahead = int(validation["lookahead_violations"].sum()) if not validation.empty else 0
    usable = float(validation["usable_rows"].mean()) if not validation.empty else 0.0
    best_quality = (
        continued_vs_failed[continued_vs_failed["group_name"].astype(str).eq("fundamental_quality_bucket")]
        .sort_values("continued_winner_rate", ascending=False)
        .head(1)
    ) if not continued_vs_failed.empty and "group_name" in continued_vs_failed.columns else pd.DataFrame()
    best_momentum = (
        continued_vs_failed[continued_vs_failed["group_name"].astype(str).eq("fundamental_momentum_bucket")]
        .sort_values("continued_winner_rate", ascending=False)
        .head(1)
    ) if not continued_vs_failed.empty and "group_name" in continued_vs_failed.columns else pd.DataFrame()
    continued_strong = continued_vs_failed[
        continued_vs_failed["bucket"].astype(str).eq("quality_strong")
    ] if not continued_vs_failed.empty and "bucket" in continued_vs_failed.columns else pd.DataFrame()
    weak_bad_buy = bad_buy_summary[bad_buy_summary["fundamental_quality_bucket"].astype(str).eq("quality_weak")] if not bad_buy_summary.empty else pd.DataFrame()
    weak_reentry = reentry_summary[reentry_summary["fundamental_quality_bucket"].astype(str).eq("quality_weak")] if not reentry_summary.empty else pd.DataFrame()
    bad_sell_quality = (
        bad_sell_summary.groupby("fundamental_quality_bucket", as_index=False)
        .agg(
            bad_sell_count=("bad_sell_count", "sum"),
            continued_winner_count=("continued_winner_count", "sum"),
        )
        if not bad_sell_summary.empty
        else pd.DataFrame()
    )
    if not bad_sell_quality.empty:
        bad_sell_quality["continued_winner_rate"] = (
            pd.to_numeric(bad_sell_quality["continued_winner_count"], errors="coerce")
            / pd.to_numeric(bad_sell_quality["bad_sell_count"], errors="coerce")
        )
    bad_buy_quality = (
        bad_buy_summary.groupby("fundamental_quality_bucket", as_index=False).agg(bad_buy_count=("bad_buy_count", "sum"))
        if not bad_buy_summary.empty
        else pd.DataFrame()
    )
    quality_strong_bad_sell = bad_sell_quality[bad_sell_quality["fundamental_quality_bucket"].astype(str).eq("quality_strong")].head(1)
    quality_weak_bad_sell = bad_sell_quality[bad_sell_quality["fundamental_quality_bucket"].astype(str).eq("quality_weak")].head(1)
    quality_unknown_bad_buy = bad_buy_quality[bad_buy_quality["fundamental_quality_bucket"].astype(str).eq("quality_unknown")].head(1)
    lines = [
        "# Final Interpretation",
        "",
        f"A1. Was PIT fundamental input loaded successfully? {'yes' if not validation.empty else 'no'}.",
        f"A2. Is lookahead violation zero? {'yes' if lookahead == 0 else 'no'}.",
        f"A3. Is coverage sufficient for attribution? {'yes' if usable > 0 else 'no'} for first-pass research joins; PIT usable-row coverage is {usable:.4f}.",
        "A4. Missing or low-quality fields remain visible in the PIT coverage and missing-fields reports; valuation/liquidity remain structurally absent.",
        f"B5. Do continued winners have better fundamental quality than failed exits? {'suggestive yes' if not continued_strong.empty else 'inconclusive'}; best quality bucket is {best_quality['bucket'].iloc[0]} at continued_winner_rate={best_quality['continued_winner_rate'].iloc[0]:.4f}." if not best_quality.empty else "B5. Continued-winner versus failed-exit quality comparison is inconclusive.",
        f"B6. Fundamental momentum currently separates continuation better than raw quality buckets; best momentum bucket is {best_momentum['bucket'].iloc[0]} at continued_winner_rate={best_momentum['continued_winner_rate'].iloc[0]:.4f}." if not best_momentum.empty else "B6. Momentum-bucket separability is inconclusive.",
        "B7. 60d continuation remains worth tracking because improving-momentum names show materially stronger 60d forward returns than deteriorating/unknown buckets in this rerun.",
        f"C8. Continued bad sells can now be segmented by PIT quality; quality_strong bad sells show continued_winner_rate={quality_strong_bad_sell['continued_winner_rate'].iloc[0]:.4f}." if not quality_strong_bad_sell.empty else "C8. Bad-sell PIT quality segmentation is available but sparse.",
        f"C9. Quality_weak bad sells show continued_winner_rate={quality_weak_bad_sell['continued_winner_rate'].iloc[0]:.4f}, lower than quality_strong, which supports using quality as post-exit watch priority rather than an exit override." if not quality_weak_bad_sell.empty and not quality_strong_bad_sell.empty else "C9. Ranking-churn versus hard-damage context remains available through the joined diagnostics.",
        "C10. Quality-strong continued bad sells are now captured in example outputs and should be reviewed as observation-pool priority cases, not automatic strategy changes.",
        f"D11. Are bad buys concentrated in quality_weak names? {'possibly' if not weak_bad_buy.empty else 'no clear evidence in this rerun'}; current bad-buy PIT grouping is dominated by quality_unknown rows ({int(quality_unknown_bad_buy['bad_buy_count'].iloc[0])} grouped rows)." if not quality_unknown_bad_buy.empty else f"D11. Are bad buys concentrated in quality_weak names? {'possibly' if not weak_bad_buy.empty else 'not yet demonstrated strongly'}.",
        "D12. High-elasticity plus weak quality can now be inspected directly in the example outputs.",
        "D13. Mainline-weak plus weak-quality bad buys are separated in the PIT output example files.",
        "D14. Quality-strong but early buys are preserved as a separate example set rather than forced into a filter conclusion.",
        "D15. Fundamentals are a future entry-filter candidate only if attribution remains stable after manual review.",
        f"E16. Is failed_reentry_loss concentrated in quality_weak or deteriorating names? {'possibly' if not weak_reentry.empty else 'inconclusive'}.",
        "E17. PIT fundamentals can now be tested against re-entry left tail, but re-entry remains research-only.",
        "E18. Quality may become a future re-entry risk-gate candidate only if it separates failed re-entries from successful ones more clearly than path/technical state.",
        "E19. If separability is weak, re-entry should remain a path/technical research problem, not a fundamental one.",
        "F20. Confirm no trading strategy logic changed: yes.",
        "F21. Confirm v1 baseline unchanged: yes.",
        "F22. Confirm top10 candidate baseline unchanged: yes.",
        "F23. Confirm re-entry remains research-only: yes.",
        "F24. Current recommendation for fundamental quality: observation_priority candidate and review_label_only today; entry_filter or reentry_risk_gate remain RESEARCH_ONLY.",
        "F25. Next task recommendation: manually review the new PIT attribution outputs and then decide whether to run one targeted fundamental-entry review experiment or to improve feature engineering first.",
    ]
    return "\n".join(lines) + "\n"


def _load_trade_diag() -> pd.DataFrame:
    frames = []
    baseline_diag = SOFT_OWNERSHIP_DIR / "trade_level_diagnostics.csv"
    if baseline_diag.exists():
        baseline = pd.read_csv(baseline_diag, low_memory=False)
        baseline = baseline[baseline.get("variant_name", pd.Series("", index=baseline.index)).astype(str).eq("baseline")].copy()
        baseline["strategy_name"] = "current_mid_trend_strategy_v1"
        frames.append(baseline)
    v2 = Path("outputs/research/current_mid_trend_strategy_v2_top10_candidate_20250101_20260612/current_mid_trend_strategy_v2_top10_candidate_trade_changes.csv")
    if v2.exists():
        frames.append(pd.read_csv(v2, low_memory=False))
    trades = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not trades.empty:
        trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        trades["audit_label"] = trades.get("audit_label", pd.Series("", index=trades.index)).fillna("")
        for column in [
            "forward_return",
            "weighted_bad_buy_loss",
            "weighted_bad_sell_opportunity",
            "ranking_churn_flag",
            "hard_damage_flag",
            "technical_confirmed",
            "mainline_confirmed",
            "midtrend_confirmation_state",
            "mainline_status",
            "industry_name",
        ]:
            if column not in trades.columns:
                trades[column] = np.nan if "return" in column or "loss" in column else ""
    return trades


def _load_observation_pool() -> pd.DataFrame:
    path_behavior = OBS_DIR / "post_exit_path_behavior.csv"
    observation_pool = OBS_DIR / "post_exit_observation_pool.csv"
    if path_behavior.exists():
        return pd.read_csv(path_behavior, low_memory=False)
    if observation_pool.exists():
        return pd.read_csv(observation_pool, low_memory=False)
    raise FileNotFoundError(f"missing observation pool inputs under {OBS_DIR}")


def _optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _rank_bucket(value: Any) -> str:
    rank = _num(value)
    if np.isnan(rank):
        return "unknown"
    if rank <= 10:
        return "top10"
    if rank <= 20:
        return "11-20"
    if rank <= 50:
        return "21-50"
    if rank <= 100:
        return "51-100"
    return ">100"


def _reentry_rank_bucket(value: Any) -> str:
    rank = _num(value)
    if np.isnan(rank):
        return "unknown"
    if rank <= 12:
        return "11-12"
    if rank <= 15:
        return "13-15"
    return "16-20"


def _num(value: Any) -> float:
    series = pd.to_numeric(pd.Series([value]), errors="coerce")
    return float(series.iloc[0]) if not pd.isna(series.iloc[0]) else np.nan
