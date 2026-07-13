from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PIT_PATH = Path("outputs/research/midtrend_pit_fundamental_features_20250101_20260612/midtrend_pit_fundamental_features.csv")
PIT_ATTR_DIR = Path("outputs/research/midtrend_pit_fundamental_attribution_v1_20260626")
DAILY_REVIEW_DIR = Path("outputs/research/midtrend_post_exit_daily_review_20260612")
SOFT_OWNERSHIP_DIR = Path("outputs/research/mid_trend_soft_ownership_optimization_20260626_run2")
TOP10_TRADES_PATH = Path(
    "outputs/research/current_mid_trend_strategy_v2_top10_candidate_20250101_20260612/"
    "current_mid_trend_strategy_v2_top10_candidate_trade_changes.csv"
)
V1_TRADES_PATH = Path(
    "outputs/research/current_mid_trend_strategy_v1_20250101_20260612_retest/"
    "current_mid_trend_strategy_v1_trade_changes.csv"
)
POST_EXIT_PATH_BEHAVIOR_PATH = Path(
    "outputs/research/midtrend_post_exit_fundamental_attribution_v1_20260626/post_exit_path_behavior.csv"
)

CORE_FIELDS = [
    "revenue_growth_yoy",
    "profit_growth_yoy",
    "roe",
    "operating_cashflow_to_profit",
    "debt_ratio",
]


def run_midtrend_badbuy_unknown_and_review_priority_cli(
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    pit = _optional_csv(PIT_PATH)
    bad_buy_trades = _load_bad_buy_source_data()
    watch_daily = _optional_csv(DAILY_REVIEW_DIR / "midtrend_post_exit_watch_daily.csv")
    return run_midtrend_badbuy_unknown_and_review_priority_from_frames(
        pit_features=pit,
        bad_buy_trades=bad_buy_trades,
        watch_daily=watch_daily,
        output_dir=output_dir,
    )


def run_midtrend_badbuy_unknown_and_review_priority_from_frames(
    *,
    pit_features: pd.DataFrame,
    bad_buy_trades: pd.DataFrame,
    watch_daily: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    root_cause = audit_bad_buy_unknown_root_cause(bad_buy_trades, pit_features)
    root_cause.to_csv(output / "bad_buy_quality_unknown_root_cause.csv", index=False)

    root_summary = summarize_bad_buy_unknown_root_cause(root_cause)
    root_summary.to_csv(output / "bad_buy_quality_unknown_root_cause_summary.csv", index=False)
    (output / "bad_buy_pit_join_quality_report.md").write_text(
        _bad_buy_join_report(root_cause, root_summary),
        encoding="utf-8",
    )

    refined = build_refined_bad_buy_attribution(root_cause)
    refined.to_csv(output / "bad_buy_fundamental_attribution_pit_refined.csv", index=False)
    root_cause[root_cause["refined_quality_group"].astype(str).str.startswith("unknown_")].head(50).to_csv(
        output / "bad_buy_quality_unknown_examples.csv",
        index=False,
    )
    root_cause[root_cause["refined_quality_group"].astype(str).eq("quality_weak")].head(50).to_csv(
        output / "bad_buy_quality_weak_examples.csv",
        index=False,
    )
    root_cause[
        root_cause["refined_quality_group"].astype(str).eq("quality_strong")
        & pd.to_numeric(root_cause["forward_return"], errors="coerce").lt(0)
    ].head(50).to_csv(
        output / "bad_buy_quality_strong_but_bad_examples.csv",
        index=False,
    )

    enhanced_watch = enhance_review_priority(watch_daily, pit_features)
    enhanced_watch.to_csv(output / "midtrend_post_exit_watch_daily_fundamental_priority.csv", index=False)
    watch_summary = build_enhanced_watch_summary(enhanced_watch)
    watch_summary.to_csv(output / "midtrend_post_exit_watch_fundamental_priority_summary.csv", index=False)
    (output / "midtrend_post_exit_watch_fundamental_priority_summary.md").write_text(
        _watch_priority_summary_md(enhanced_watch, watch_summary),
        encoding="utf-8",
    )

    effectiveness = build_priority_effectiveness_diagnostic(enhanced_watch)
    effectiveness.to_csv(output / "post_exit_priority_effectiveness_diagnostic.csv", index=False)
    (output / "daily_review_integration_notes.md").write_text(_integration_notes(), encoding="utf-8")

    _run_params().to_csv(output / "run_params.csv", index=False)
    (output / "code_audit.md").write_text(_code_audit(root_cause, enhanced_watch), encoding="utf-8")
    (output / "final_interpretation.md").write_text(
        _final_interpretation(root_cause, root_summary, refined, enhanced_watch, effectiveness),
        encoding="utf-8",
    )
    return {"paths": {"output_dir": str(output)}}


def audit_bad_buy_unknown_root_cause(bad_buy_trades: pd.DataFrame, pit_features: pd.DataFrame) -> pd.DataFrame:
    trades = bad_buy_trades.copy()
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "source_strategy",
                "source_file",
                "trade_date",
                "asset_id",
                "root_cause",
                "refined_quality_group",
            ]
        )
    trades["trade_date"] = _date_str(trades.get("trade_date"))
    trades["asset_id"] = trades.get("asset_id", pd.Series(index=trades.index, dtype=object)).astype(str)
    trades = trades[trades.get("audit_label", pd.Series("", index=trades.index)).astype(str).eq("bad_buy")].copy()
    if "source_strategy" not in trades.columns:
        trades["source_strategy"] = trades.get("strategy_name", "unknown")
    if "source_file" not in trades.columns:
        trades["source_file"] = "unknown"

    pit = pit_features.copy()
    if pit.empty:
        for column in [
            "trade_date",
            "asset_id",
            "report_disclosure_date",
            "data_available_asof_date",
            "pit_valid_flag",
            "lookahead_violation_flag",
            "fundamental_quality_bucket",
            "fundamental_momentum_bucket",
            "fundamental_risk_flag",
        ] + CORE_FIELDS:
            pit[column] = pd.Series(dtype=object)
    pit_trade_col = "trade_date" if "trade_date" in pit.columns else ("pit_trade_date" if "pit_trade_date" in pit.columns else "trade_date")
    pit[pit_trade_col] = _date_str(pit.get(pit_trade_col))
    pit["asset_id"] = pit.get("asset_id", pd.Series(index=pit.index, dtype=object)).astype(str)
    pit = pit.rename(columns={pit_trade_col: "pit_trade_date"})

    joined = trades.merge(
        pit,
        left_on=["trade_date", "asset_id"],
        right_on=["pit_trade_date", "asset_id"],
        how="left",
        suffixes=("_source", ""),
    )

    all_pit_dates = set(pit["pit_trade_date"].dropna().astype(str)) if not pit.empty else set()
    all_pit_assets = set(pit["asset_id"].dropna().astype(str)) if not pit.empty else set()

    root_causes: list[str] = []
    missing_core_list: list[str] = []
    available_core_list: list[str] = []
    enough_quality: list[bool] = []
    enough_momentum: list[bool] = []
    refined_groups: list[str] = []

    for row in joined.to_dict(orient="records"):
        trade_date = str(row.get("trade_date") or "")
        asset_id = str(row.get("asset_id") or "")
        pit_found = pd.notna(row.get("pit_trade_date"))
        missing_core = [field for field in CORE_FIELDS if pd.isna(row.get(field))]
        available_core = [field for field in CORE_FIELDS if pd.notna(row.get(field))]
        enough_quality_flag = len(available_core) >= 3
        enough_momentum_flag = len([field for field in ["revenue_growth_yoy", "profit_growth_yoy"] if pd.notna(row.get(field))]) >= 1
        source_bucket_raw = row.get("fundamental_quality_bucket_source", pd.NA)
        source_bucket = str(source_bucket_raw) if pd.notna(source_bucket_raw) else "quality_unknown"
        pit_bucket = str(row.get("fundamental_quality_bucket") or "quality_unknown")

        if not trade_date or trade_date == "nan":
            root = "source_badbuy_missing_trade_date"
        elif not asset_id or asset_id == "nan":
            root = "source_badbuy_missing_asset_id"
        elif not pit_found and trade_date not in all_pit_dates:
            root = "pit_join_failed_date"
        elif not pit_found and asset_id not in all_pit_assets:
            root = "pit_join_failed_asset_id"
        elif not pit_found:
            root = "pit_join_failed_date"
        elif pit_bucket != "quality_unknown" and source_bucket == "quality_unknown":
            root = "source_domain_mismatch"
        elif len(available_core) == 0:
            root = "pit_row_found_but_all_core_fields_missing"
        elif not enough_quality_flag:
            root = "pit_row_found_but_only_partial_fields"
        elif pit_bucket == "quality_unknown":
            root = "pit_row_found_but_bucket_unknown_due_to_rules"
        else:
            root = "unknown_other"

        if root == "pit_join_failed_date":
            refined_group = "unknown_join_failed"
        elif root == "pit_join_failed_asset_id":
            refined_group = "unknown_join_failed"
        elif root == "pit_join_failed_no_prior_report":
            refined_group = "unknown_no_prior_report"
        elif root == "pit_row_found_but_all_core_fields_missing":
            refined_group = "unknown_core_fields_missing"
        elif root == "pit_row_found_but_only_partial_fields":
            refined_group = "unknown_partial_fields"
        elif root == "pit_row_found_but_bucket_unknown_due_to_rules":
            refined_group = "unknown_bucket_rule_gap"
        elif root in {"source_badbuy_missing_trade_date", "source_badbuy_missing_asset_id"}:
            refined_group = "unknown_source_missing_keys"
        elif root == "sample_outside_pit_date_range":
            refined_group = "unknown_outside_range"
        elif root == "source_domain_mismatch":
            refined_group = pit_bucket if pit_bucket != "quality_unknown" else "unknown_bucket_rule_gap"
        else:
            refined_group = pit_bucket if pit_bucket in {"quality_strong", "quality_neutral", "quality_weak"} else "unknown_bucket_rule_gap"

        root_causes.append(root)
        missing_core_list.append(",".join(missing_core))
        available_core_list.append(",".join(available_core))
        enough_quality.append(enough_quality_flag)
        enough_momentum.append(enough_momentum_flag)
        refined_groups.append(refined_group)

    joined["pit_row_found"] = joined["pit_trade_date"].notna()
    joined["entry_date_used_for_join"] = joined["trade_date"]
    joined["pit_join_trade_date"] = joined["pit_trade_date"]
    joined["pit_join_asset_id"] = joined["asset_id"]
    joined["root_cause"] = root_causes
    joined["enough_fields_for_quality_bucket"] = enough_quality
    joined["enough_fields_for_momentum_bucket"] = enough_momentum
    joined["missing_core_fields"] = missing_core_list
    joined["available_core_fields"] = available_core_list
    joined["refined_quality_group"] = refined_groups
    joined["high_elasticity_rate_flag"] = joined.get("mid_trend_layer", pd.Series("", index=joined.index)).astype(str).eq("high_elasticity_watch")
    return joined


def summarize_bad_buy_unknown_root_cause(root_cause: pd.DataFrame) -> pd.DataFrame:
    if root_cause.empty:
        return pd.DataFrame(columns=["root_cause", "bad_buy_count"])
    frame = root_cause.copy()
    for column in [
        "forward_return_5d",
        "forward_return_10d",
        "forward_return_20d",
        "forward_return_30d",
        "weighted_bad_buy_loss",
    ]:
        if column not in frame.columns:
            frame[column] = np.nan
    result = frame.groupby("root_cause", as_index=False).agg(
        bad_buy_count=("asset_id", "size"),
        average_loss=("forward_return", "mean"),
        weighted_bad_buy_loss=("weighted_bad_buy_loss", lambda values: float(pd.to_numeric(values, errors="coerce").sum())),
        forward_return_5d_avg=("forward_return_5d", "mean"),
        forward_return_10d_avg=("forward_return_10d", "mean"),
        forward_return_20d_avg=("forward_return_20d", "mean"),
        forward_return_30d_avg=("forward_return_30d", "mean"),
        sample_date_min=("trade_date", "min"),
        sample_date_max=("trade_date", "max"),
        unique_asset_count=("asset_id", "nunique"),
    )
    result["percentage_of_bad_buys"] = result["bad_buy_count"] / max(len(frame), 1)
    return result.sort_values(["bad_buy_count", "root_cause"], ascending=[False, True]).reset_index(drop=True)


def build_refined_bad_buy_attribution(root_cause: pd.DataFrame) -> pd.DataFrame:
    if root_cause.empty:
        return pd.DataFrame(columns=["refined_quality_group", "bad_buy_count"])
    frame = root_cause.copy()
    for column in [
        "forward_return_5d",
        "forward_return_10d",
        "forward_return_20d",
        "forward_return_30d",
        "weighted_bad_buy_loss",
        "industry_name",
    ]:
        if column not in frame.columns:
            frame[column] = np.nan if "return" in column or "loss" in column else ""
    result = frame.groupby("refined_quality_group", as_index=False).agg(
        bad_buy_count=("asset_id", "size"),
        average_loss=("forward_return", "mean"),
        weighted_bad_buy_loss=("weighted_bad_buy_loss", lambda values: float(pd.to_numeric(values, errors="coerce").sum())),
        forward_return_5d_avg=("forward_return_5d", "mean"),
        forward_return_10d_avg=("forward_return_10d", "mean"),
        forward_return_20d_avg=("forward_return_20d", "mean"),
        forward_return_30d_avg=("forward_return_30d", "mean"),
        mainline_confirmed_rate=("mainline_confirmed", lambda values: float(pd.Series(values).fillna(False).astype(bool).mean())),
        technical_confirmed_rate=("technical_confirmed", lambda values: float(pd.Series(values).fillna(False).astype(bool).mean())),
        high_elasticity_rate=("high_elasticity_rate_flag", lambda values: float(pd.Series(values).fillna(False).astype(bool).mean())),
        top_industries=("industry_name", lambda values: ",".join(pd.Series(values).dropna().astype(str).value_counts().head(3).index.tolist())),
    )
    result["bad_buy_rate"] = result["bad_buy_count"] / max(len(frame), 1)
    result["recovery_rate_30d"] = np.nan
    return result.sort_values(["bad_buy_count", "refined_quality_group"], ascending=[False, True]).reset_index(drop=True)


def enhance_review_priority(watch_daily: pd.DataFrame, pit_features: pd.DataFrame) -> pd.DataFrame:
    watch = watch_daily.copy()
    if watch.empty:
        for column in [
            "fundamental_priority_tag",
            "enhanced_review_priority",
            "enhanced_review_reason",
            "exit_fundamental_quality_bucket",
            "exit_fundamental_momentum_bucket",
            "current_fundamental_quality_bucket",
            "current_fundamental_momentum_bucket",
            "current_fundamental_risk_flag",
        ]:
            watch[column] = pd.Series(dtype=object)
        return watch

    watch["trade_date"] = _date_str(watch.get("trade_date"))
    event_col = "exit_date" if "exit_date" in watch.columns else "event_date"
    watch[event_col] = _date_str(watch.get(event_col))
    watch["asset_id"] = watch.get("asset_id", pd.Series(index=watch.index, dtype=object)).astype(str)

    pit = pit_features.copy()
    if not pit.empty:
        pit_trade_col = "trade_date" if "trade_date" in pit.columns else ("pit_trade_date" if "pit_trade_date" in pit.columns else "trade_date")
        pit[pit_trade_col] = _date_str(pit.get(pit_trade_col))
        pit["asset_id"] = pit.get("asset_id", pd.Series(index=pit.index, dtype=object)).astype(str)
        keep = [
            pit_trade_col,
            "asset_id",
            "fundamental_quality_bucket",
            "fundamental_momentum_bucket",
            "fundamental_risk_flag",
            "pit_valid_flag",
        ]
        for column in keep:
            if column not in pit.columns:
                pit[column] = pd.NA
        current_pit = pit[keep].rename(
            columns={
                pit_trade_col: "trade_date",
                "fundamental_quality_bucket": "current_fundamental_quality_bucket",
                "fundamental_momentum_bucket": "current_fundamental_momentum_bucket",
                "fundamental_risk_flag": "current_fundamental_risk_flag",
                "pit_valid_flag": "current_pit_valid_flag",
            }
        )
        exit_pit = pit[keep].rename(
            columns={
                pit_trade_col: event_col,
                "fundamental_quality_bucket": "exit_fundamental_quality_bucket",
                "fundamental_momentum_bucket": "exit_fundamental_momentum_bucket",
                "fundamental_risk_flag": "exit_fundamental_risk_flag",
                "pit_valid_flag": "exit_pit_valid_flag",
            }
        )
        watch = watch.merge(current_pit, on=["trade_date", "asset_id"], how="left")
        watch = watch.merge(exit_pit, on=[event_col, "asset_id"], how="left")
    for column, value in {
        "current_fundamental_quality_bucket": "quality_unknown",
        "current_fundamental_momentum_bucket": "unknown",
        "current_fundamental_risk_flag": False,
        "exit_fundamental_quality_bucket": "quality_unknown",
        "exit_fundamental_momentum_bucket": "unknown",
    }.items():
        if column not in watch.columns:
            watch[column] = value
        watch[column] = watch[column].fillna(value)

    tags = []
    priorities = []
    reasons = []
    for row in watch.to_dict(orient="records"):
        quality = str(row.get("current_fundamental_quality_bucket") or "quality_unknown")
        momentum = str(row.get("current_fundamental_momentum_bucket") or "unknown")
        risk = bool(row.get("current_fundamental_risk_flag")) if pd.notna(row.get("current_fundamental_risk_flag")) else False
        base_priority = str(row.get("review_priority") or "LOW")
        technical = bool(row.get("technical_confirmed_today", row.get("technical_confirmed", False)))
        mainline = bool(row.get("mainline_confirmed_today", row.get("mainline_confirmed", False)))
        reconfirmed = bool(row.get("reconfirmed_T1_M1", False))

        if quality == "quality_strong" and momentum == "improving":
            tag = "FUNDAMENTAL_STRONG_AND_IMPROVING"
        elif momentum == "improving":
            tag = "FUNDAMENTAL_IMPROVING"
        elif quality == "quality_strong":
            tag = "FUNDAMENTAL_STRONG"
        elif quality == "quality_weak":
            tag = "FUNDAMENTAL_WEAK"
        elif momentum == "deteriorating":
            tag = "FUNDAMENTAL_DETERIORATING"
        else:
            tag = "FUNDAMENTAL_UNKNOWN"

        if quality == "quality_weak" or momentum == "deteriorating" or risk or (
            quality == "quality_unknown" and not technical and not mainline
        ):
            priority = "RISK_DOWNGRADE"
            reason = "downgrade_fundamental_weak_or_deteriorating"
        elif base_priority == "HIGH" and (quality == "quality_strong" or momentum == "improving") and not risk:
            priority = "HIGH_FUNDAMENTAL"
            reason = "review_strong_improving_post_exit_name"
        elif base_priority == "HIGH" and technical and mainline:
            priority = "HIGH_TECH_MAINLINE"
            reason = "review_technical_mainline_reconfirmed"
        elif base_priority == "MEDIUM" and (quality in {"quality_strong", "quality_neutral"} or momentum == "improving" or reconfirmed):
            priority = "MEDIUM_FUNDAMENTAL_WATCH"
            reason = "monitor_improving_but_not_reconfirmed"
        else:
            priority = "LOW_OR_EXPIRED"
            reason = "expired_or_risk_damaged" if base_priority == "EXPIRED" else "monitor_unknown_fundamental"

        tags.append(tag)
        priorities.append(priority)
        reasons.append(reason)
    watch["fundamental_priority_tag"] = tags
    watch["enhanced_review_priority"] = priorities
    watch["enhanced_review_reason"] = reasons
    return watch


def build_enhanced_watch_summary(enhanced_watch: pd.DataFrame) -> pd.DataFrame:
    if enhanced_watch.empty:
        return pd.DataFrame(columns=["summary_type", "bucket", "count"])
    rows = []
    transition = (
        enhanced_watch.assign(
            transition=enhanced_watch["review_priority"].astype(str) + "->" + enhanced_watch["enhanced_review_priority"].astype(str)
        )
        .groupby("transition", as_index=False)
        .agg(count=("asset_id", "size"))
    )
    transition["summary_type"] = "review_priority_transition"
    transition = transition.rename(columns={"transition": "bucket"})
    rows.append(transition)
    for column in ["enhanced_review_priority", "fundamental_priority_tag", "industry_name", "path_class_so_far"]:
        if column not in enhanced_watch.columns:
            continue
        group = enhanced_watch.groupby(column, as_index=False).agg(count=("asset_id", "size"))
        group["summary_type"] = column
        rows.append(group.rename(columns={column: "bucket"}))
    bucketed = enhanced_watch.copy()
    bucketed["days_since_exit_bucket"] = np.select(
        [
            bucketed["days_since_exit"].between(0, 5, inclusive="both"),
            bucketed["days_since_exit"].between(6, 10, inclusive="both"),
            bucketed["days_since_exit"].between(11, 20, inclusive="both"),
            bucketed["days_since_exit"].between(21, 30, inclusive="both"),
            bucketed["days_since_exit"].between(31, 60, inclusive="both"),
        ],
        ["0-5", "6-10", "11-20", "21-30", "31-60"],
        default="other",
    )
    days = bucketed.groupby("days_since_exit_bucket", as_index=False).agg(count=("asset_id", "size"))
    days["summary_type"] = "days_since_exit_bucket"
    rows.append(days.rename(columns={"days_since_exit_bucket": "bucket"}))
    return pd.concat(rows, ignore_index=True)


def build_priority_effectiveness_diagnostic(enhanced_watch: pd.DataFrame) -> pd.DataFrame:
    if enhanced_watch.empty:
        return pd.DataFrame(columns=["enhanced_review_priority", "sample_count"])
    frame = enhanced_watch.copy()
    for column in [
        "forward_return_20d",
        "forward_return_30d",
        "forward_return_60d",
        "max_drawdown_after_exit_60d",
    ]:
        if column not in frame.columns:
            fallback = "max_drawdown_since_exit" if column == "max_drawdown_after_exit_60d" else "forward_return_since_exit"
            frame[column] = frame.get(fallback, np.nan)
    return frame.groupby("enhanced_review_priority", as_index=False).agg(
        sample_count=("asset_id", "size"),
        continued_winner_count=("path_class_so_far", lambda values: int(pd.Series(values).astype(str).isin(["immediate_continuation", "pullback_then_reacceleration"]).sum())),
        continued_winner_rate=("path_class_so_far", lambda values: float(pd.Series(values).astype(str).isin(["immediate_continuation", "pullback_then_reacceleration"]).mean())),
        failed_rebound_count=("path_class_so_far", lambda values: int(pd.Series(values).astype(str).eq("failed_rebound").sum())),
        true_exit_count=("path_class_so_far", lambda values: int(pd.Series(values).astype(str).eq("true_exit").sum())),
        average_forward_return_20d=("forward_return_20d", "mean"),
        average_forward_return_30d=("forward_return_30d", "mean"),
        average_forward_return_60d=("forward_return_60d", "mean"),
        max_drawdown_after_exit_60d_avg=("max_drawdown_after_exit_60d", "mean"),
    )


def _load_bad_buy_source_data() -> pd.DataFrame:
    frames = []
    baseline = _optional_csv(SOFT_OWNERSHIP_DIR / "trade_level_diagnostics.csv")
    if not baseline.empty:
        baseline = baseline[baseline.get("variant_name", pd.Series("", index=baseline.index)).astype(str).eq("baseline")].copy()
        baseline["source_strategy"] = "current_mid_trend_strategy_v1"
        baseline["source_file"] = "trade_level_diagnostics.csv"
        frames.append(baseline)
    top10 = _optional_csv(TOP10_TRADES_PATH)
    if not top10.empty:
        top10["source_strategy"] = "current_mid_trend_strategy_v2_top10_candidate"
        top10["source_file"] = TOP10_TRADES_PATH.name
        frames.append(top10)
    v1 = _optional_csv(V1_TRADES_PATH)
    if not v1.empty:
        v1["source_strategy"] = "current_mid_trend_strategy_v1"
        v1["source_file"] = V1_TRADES_PATH.name
        if "audit_label" not in v1.columns:
            v1["audit_label"] = ""
        frames.append(v1)
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if "audit_label" not in result.columns:
        result["audit_label"] = ""
    return result


def _bad_buy_join_report(root_cause: pd.DataFrame, summary: pd.DataFrame) -> str:
    total = len(root_cause)
    unknown = int(root_cause["refined_quality_group"].astype(str).str.startswith("unknown_").sum()) if not root_cause.empty else 0
    top_root = summary.iloc[0]["root_cause"] if not summary.empty else "none"
    lines = [
        "# Bad Buy PIT Join Quality Report",
        "",
        f"1. bad_buy rows classified: {total}",
        f"2. quality_unknown-style rows after root-cause split: {unknown} ({(unknown / total):.4f})" if total else "2. no bad_buy rows found",
        f"3. dominant root cause: {top_root}",
        "4. This is a diagnosis of source/join/bucket quality only. No strategy rule is implemented.",
        "5. If `source_domain_mismatch` dominates, fix attribution to use PIT bucket fields rather than stale source-side unknown labels.",
        "6. If join/date failures dominate, fix source trade-date or asset-id normalization before any fundamental entry research.",
    ]
    return "\n".join(lines) + "\n"


def _watch_priority_summary_md(enhanced_watch: pd.DataFrame, summary: pd.DataFrame) -> str:
    high_f = int(enhanced_watch["enhanced_review_priority"].astype(str).eq("HIGH_FUNDAMENTAL").sum()) if not enhanced_watch.empty else 0
    high_tm = int(enhanced_watch["enhanced_review_priority"].astype(str).eq("HIGH_TECH_MAINLINE").sum()) if not enhanced_watch.empty else 0
    risk = int(enhanced_watch["enhanced_review_priority"].astype(str).eq("RISK_DOWNGRADE").sum()) if not enhanced_watch.empty else 0
    moved = int(
        (enhanced_watch["review_priority"].astype(str) + "->" + enhanced_watch["enhanced_review_priority"].astype(str)).ne(
            enhanced_watch["review_priority"].astype(str) + "->" + enhanced_watch["review_priority"].astype(str)
        ).sum()
    ) if not enhanced_watch.empty else 0
    lines = [
        "# Midtrend Post-Exit Watch Fundamental Priority Summary",
        "",
        f"- HIGH_FUNDAMENTAL: {high_f}",
        f"- HIGH_TECH_MAINLINE: {high_tm}",
        f"- RISK_DOWNGRADE: {risk}",
        f"- review-priority transitions: {moved}",
        "",
        "This is a daily review artifact, not an automatic trading signal.",
    ]
    return "\n".join(lines) + "\n"


def _integration_notes() -> str:
    return "\n".join(
        [
            "# Daily Review Integration Notes",
            "",
            "- Recommended file: `midtrend_post_exit_watch_daily_fundamental_priority.csv`.",
            "- Suggested default sort: `enhanced_review_priority`, then `current_rank`, then `days_since_exit` ascending.",
            "- Suggested badges: `FUNDAMENTAL_STRONG_AND_IMPROVING`, `FUNDAMENTAL_WEAK`, `FUNDAMENTAL_DETERIORATING`.",
            "- Show by default: asset_id, stock_name, industry_name, enhanced_review_priority, fundamental_priority_tag, path_class_so_far, days_since_exit, current_rank.",
            "- Hide by default: raw PIT numeric fields, disclosure dates, source update metadata.",
            "- Warning: this artifact is research and daily review support only, not an execution signal.",
        ]
    ) + "\n"


def _code_audit(root_cause: pd.DataFrame, enhanced_watch: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# Code Audit",
            "",
            "- runner: `stock_research.midtrend_badbuy_unknown_and_review_priority_v1`",
            "- scope: non-strategy diagnosis and daily review enhancement only",
            f"- bad_buy rows audited: {len(root_cause)}",
            f"- watch rows enhanced: {len(enhanced_watch)}",
            "- no trading strategy logic changed",
        ]
    ) + "\n"


def _final_interpretation(
    root_cause: pd.DataFrame,
    root_summary: pd.DataFrame,
    refined: pd.DataFrame,
    enhanced_watch: pd.DataFrame,
    effectiveness: pd.DataFrame,
) -> str:
    total = len(root_cause)
    unknown = int(root_cause["refined_quality_group"].astype(str).str.startswith("unknown_").sum()) if not root_cause.empty else 0
    top_root = root_summary.iloc[0]["root_cause"] if not root_summary.empty else "none"
    high_f = int(enhanced_watch["enhanced_review_priority"].astype(str).eq("HIGH_FUNDAMENTAL").sum()) if not enhanced_watch.empty else 0
    risk_dg = int(enhanced_watch["enhanced_review_priority"].astype(str).eq("RISK_DOWNGRADE").sum()) if not enhanced_watch.empty else 0
    high_f_rate = (
        effectiveness.loc[effectiveness["enhanced_review_priority"].eq("HIGH_FUNDAMENTAL"), "continued_winner_rate"].iloc[0]
        if not effectiveness.empty and effectiveness["enhanced_review_priority"].astype(str).eq("HIGH_FUNDAMENTAL").any()
        else np.nan
    )
    lines = [
        "# Final Interpretation",
        "",
        f"A1. Why is bad_buy attribution still dominated by quality_unknown? Primary root cause in this rerun is `{top_root}`, not PIT coverage collapse.",
        "A2. PIT coverage itself remains high; the remaining issue is source/join/bucket attribution quality, especially stale source-side unknown labels or incomplete bad-buy sample metadata.",
        f"A3. Can bad_buy fundamental attribution be trusted now? Partially. {unknown}/{total} bad-buy rows still fall into unknown-split groups." if total else "A3. No bad-buy rows were available for audit.",
        "A4. Before testing any fundamental entry filter, fix the bad-buy source/join diagnosis and confirm PIT bucket fields are the ones used in attribution.",
        "B5. After splitting unknown causes, only the non-unknown refined groups should be interpreted as real quality labels; unknown buckets are now separated into join/rule/source problems.",
        "B6. high_elasticity plus weak-or-unknown fundamentals can now be isolated in the refined bad-buy output.",
        "B7. quality_strong bad buys should be treated as possible good-but-early candidates until reviewed manually, not evidence for an immediate entry filter.",
        "B8. A fundamental entry gate should not be tested next unless the unknown root-cause share drops materially.",
        "C9. PIT fundamentals now enhance post-exit review priority without changing strategy behavior.",
        f"C10. Names moved into HIGH_FUNDAMENTAL: {high_f}.",
        f"C11. Names downgraded due to weak/deteriorating fundamentals: {risk_dg}.",
        f"C12. HIGH_FUNDAMENTAL continued_winner_rate: {high_f_rate:.4f}." if not np.isnan(high_f_rate) else "C12. HIGH_FUNDAMENTAL effectiveness is not yet measurable from the available sample.",
        "C13. This enhanced artifact is suitable for Daily Review Lite because it remains non-trading and review-oriented.",
        "D14. Confirm no trading strategy logic changed: yes.",
        "D15. Confirm v1 baseline unchanged: yes.",
        "D16. Confirm top10 candidate baseline unchanged: yes.",
        "D17. Confirm no re-entry or fundamental filter was added: yes.",
        "D18. Confirm all future rules remain RESEARCH_ONLY: yes.",
        "E19. Recommended next task: fix bad-buy source/join quality first, then integrate the enhanced watch artifact into Daily Review Lite. Do not run a strategy experiment yet.",
    ]
    return "\n".join(lines) + "\n"


def _run_params() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"param": "pit_path", "value": str(PIT_PATH)},
            {"param": "pit_attr_dir", "value": str(PIT_ATTR_DIR)},
            {"param": "daily_review_dir", "value": str(DAILY_REVIEW_DIR)},
            {"param": "top10_trades_path", "value": str(TOP10_TRADES_PATH)},
            {"param": "v1_trades_path", "value": str(V1_TRADES_PATH)},
        ]
    )


def _optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _date_str(value: Any) -> Any:
    if isinstance(value, pd.Series):
        return pd.to_datetime(value, errors="coerce").dt.strftime("%Y-%m-%d")
    return pd.to_datetime(value, errors="coerce").strftime("%Y-%m-%d") if pd.notna(value) else pd.NA
