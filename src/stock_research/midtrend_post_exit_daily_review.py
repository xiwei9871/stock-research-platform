from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.current_mid_trend_strategy_v1 import load_current_strategy_prices
from stock_research.midtrend_post_exit_fundamental_attribution_v1 import _date_str

ATTRIBUTION_DIR = Path("outputs/research/midtrend_post_exit_fundamental_attribution_v1_20260626")
FUNNEL_DETAIL_PATH = Path("outputs/research/mid_trend_watch_funnel_20250101_20260612_retest/mid_trend_watch_funnel_detail.csv")
PIT_DIR = Path("outputs/research/midtrend_pit_fundamental_features_20250101_20260612")


def run_midtrend_post_exit_daily_review_cli(
    *,
    trade_date: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    observation_pool = pd.read_csv(ATTRIBUTION_DIR / "post_exit_observation_pool.csv", low_memory=False)
    funnel = pd.read_csv(FUNNEL_DETAIL_PATH, low_memory=False)
    pit_path = PIT_DIR / "midtrend_pit_fundamental_features.csv"
    pit = pd.read_csv(pit_path, low_memory=False) if pit_path.exists() else pd.DataFrame()
    active_assets = observation_pool["asset_id"].dropna().astype(str).unique().tolist()
    earliest_exit = pd.to_datetime(trade_date) - pd.Timedelta(days=120)
    prices = load_current_strategy_prices(
        earliest_exit.strftime("%Y-%m-%d"),
        trade_date,
        asset_ids=active_assets,
        adjust_type="hfq",
    )
    return build_midtrend_post_exit_daily_review_from_frames(
        trade_date=trade_date,
        observation_pool=observation_pool,
        funnel=funnel,
        prices=prices,
        pit_features=pit,
        output_dir=output_dir,
    )


def build_midtrend_post_exit_daily_review_from_frames(
    *,
    trade_date: str,
    observation_pool: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    pit_features: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    obs = observation_pool.copy()
    obs["event_date"] = _date_str(obs["event_date"])
    obs["asset_id"] = obs["asset_id"].astype(str)
    obs = obs[obs["event_date"].le(trade_date)].copy()
    obs["days_since_exit"] = (pd.to_datetime(trade_date) - pd.to_datetime(obs["event_date"])).dt.days
    obs = obs[obs["days_since_exit"].between(0, 60)].copy()

    funnel = funnel.copy()
    funnel["trade_date"] = _date_str(funnel["trade_date"])
    funnel["asset_id"] = funnel["asset_id"].astype(str)
    today = funnel[funnel["trade_date"].eq(trade_date)].copy()
    keep = [
        "trade_date",
        "asset_id",
        "stock_name",
        "industry_name",
        "candidate_rank",
        "score_rank",
        "mid_trend_funnel_score",
        "mid_trend_layer",
        "mainline_status",
        "industry_mainline_score_v1",
        "stock_excess_ret_20_score",
        "max_drawdown_20_score",
        "technical_confirmed",
        "mainline_confirmed",
        "midtrend_confirmation_state",
    ]
    for column in keep:
        if column not in today.columns:
            today[column] = pd.NA
    if today["candidate_rank"].isna().all():
        today["candidate_rank"] = pd.to_numeric(today.get("score_rank"), errors="coerce")
        if today["candidate_rank"].isna().all() and "rank" in funnel.columns:
            today["candidate_rank"] = pd.to_numeric(today.get("rank"), errors="coerce")
    today = today[keep].rename(
        columns={
            "candidate_rank": "current_rank",
            "mid_trend_funnel_score": "current_score",
            "mid_trend_layer": "current_mid_trend_layer",
            "mainline_status": "current_mainline_status",
            "industry_mainline_score_v1": "current_industry_mainline_score_v1",
            "stock_excess_ret_20_score": "current_stock_excess_ret_20_score",
            "max_drawdown_20_score": "current_max_drawdown_20_score",
        }
    )

    prices = prices.copy()
    prices["trade_date"] = _date_str(prices["trade_date"])
    prices["asset_id"] = prices["asset_id"].astype(str)
    price_map = {str(asset_id): group.sort_values("trade_date").reset_index(drop=True) for asset_id, group in prices.groupby("asset_id", sort=False)}

    pit = pit_features.copy()
    if not pit.empty:
        pit["trade_date"] = _date_str(pit["trade_date"])
        pit["asset_id"] = pit["asset_id"].astype(str)
        pit = pit[pit["trade_date"].eq(trade_date)].copy()
    else:
        pit = pd.DataFrame(columns=["trade_date", "asset_id"])

    rows = []
    for row in obs.itertuples(index=False):
        rec = dict(row._asdict())
        asset_id = str(rec["asset_id"])
        rec["trade_date"] = trade_date
        rec["previous_best_rank"] = rec.get("previous_best_rank_5_10_20", np.nan)
        rec = _attach_price_path_so_far(rec, price_map.get(asset_id, pd.DataFrame()), trade_date)
        rows.append(rec)
    watch_daily = pd.DataFrame(rows)
    watch_daily = watch_daily.merge(today.drop(columns=["trade_date"]), on="asset_id", how="left", suffixes=("", "_today"))
    if not pit.empty:
        pit_keep = [
            "asset_id",
            "fundamental_quality_bucket",
            "fundamental_momentum_bucket",
            "fundamental_risk_flag",
            "revenue_growth_yoy",
            "profit_growth_yoy",
            "roe",
            "operating_cashflow_to_profit",
            "valuation_percentile",
            "pit_valid_flag",
        ]
        for column in pit_keep:
            if column not in pit.columns:
                pit[column] = pd.NA
        watch_daily = watch_daily.merge(
            pit[pit_keep],
            on="asset_id",
            how="left",
            suffixes=("", "_pit"),
        )
    else:
        for column, value in {
            "fundamental_quality_bucket": "quality_unknown",
            "fundamental_momentum_bucket": "unknown",
            "pit_valid_flag": False,
        }.items():
            watch_daily[column] = value

    watch_daily["score_delta_since_exit"] = pd.to_numeric(watch_daily["current_score"], errors="coerce") - pd.to_numeric(watch_daily["mid_trend_funnel_score_on_exit"], errors="coerce")
    watch_daily["review_priority"] = watch_daily.apply(lambda row: assign_review_priority(row)["review_priority"], axis=1)
    review_meta = watch_daily.apply(assign_review_priority, axis=1, result_type="expand")
    for column in review_meta.columns:
        watch_daily[column] = review_meta[column]
    watch_daily["path_class_so_far"] = watch_daily.apply(_path_class_so_far, axis=1)

    watch_daily.to_csv(output / "midtrend_post_exit_watch_daily.csv", index=False)
    summary_csv = _watch_summary_csv(watch_daily)
    summary_csv.to_csv(output / "midtrend_post_exit_watch_summary.csv", index=False)
    (output / "midtrend_post_exit_watch_summary.md").write_text(_watch_summary_markdown(watch_daily, summary_csv, trade_date), encoding="utf-8")
    pd.DataFrame([{"key": "trade_date", "value": trade_date}, {"key": "watch_window_days", "value": 60}]).to_csv(output / "run_params.csv", index=False)
    (output / "code_audit.md").write_text(
        "\n".join(
            [
                "# Code Audit",
                "",
                "- daily review runner: `stock_research.midtrend_post_exit_daily_review`",
                "- uses existing post-exit attribution artifact as research input",
                "- non-trading outputs only: review_priority, review_reason, suggested_review_action",
                "- PIT fundamentals joined if available; otherwise quality defaults to unknown",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "final_interpretation.md").write_text(
        _daily_final_interpretation(watch_daily, trade_date),
        encoding="utf-8",
    )
    return {"watch_daily": watch_daily, "paths": {"output_dir": str(output)}}


def assign_review_priority(row: pd.Series) -> dict[str, str]:
    layer = str(row.get("current_mid_trend_layer") or "")
    hard_damage = bool(row.get("hard_damage_flag")) if not pd.isna(row.get("hard_damage_flag")) else False
    if int(row.get("days_since_exit", 999)) > 60 or hard_damage or layer == "risk_exclusion_watch":
        return {"review_priority": "EXPIRED", "review_reason": "expired_or_risk_damaged", "suggested_review_action": "expired" if not hard_damage and layer != "risk_exclusion_watch" else "risk_damaged_do_not_review"}
    previous_best = pd.to_numeric(pd.Series([row.get("previous_best_rank")]), errors="coerce").iloc[0]
    current_rank = pd.to_numeric(pd.Series([row.get("current_rank")]), errors="coerce").iloc[0]
    if (
        (bool(row.get("was_held")) or (not pd.isna(previous_best) and previous_best <= 10))
        and not pd.isna(current_rank)
        and current_rank <= 20
        and bool(row.get("technical_confirmed"))
        and bool(row.get("mainline_confirmed"))
    ):
        return {"review_priority": "HIGH", "review_reason": "previous_leader_recovered", "suggested_review_action": "review_for_reacceleration"}
    if (not pd.isna(previous_best) and previous_best <= 20) or pd.to_numeric(pd.Series([row.get("score_delta_since_exit")]), errors="coerce").iloc[0] > 5:
        return {"review_priority": "MEDIUM", "review_reason": "partial_recovery", "suggested_review_action": "monitor_pullback"}
    return {"review_priority": "LOW", "review_reason": "not_recovered", "suggested_review_action": "ignore_until_reconfirmed"}


def _attach_price_path_so_far(record: dict[str, Any], price_frame: pd.DataFrame, trade_date: str) -> dict[str, Any]:
    if price_frame.empty:
        record["forward_return_since_exit"] = np.nan
        record["max_return_since_exit"] = np.nan
        record["max_drawdown_since_exit"] = np.nan
        return record
    event_date = str(record["event_date"])
    price_frame = price_frame[price_frame["trade_date"].between(event_date, trade_date)].copy()
    if price_frame.empty:
        record["forward_return_since_exit"] = np.nan
        record["max_return_since_exit"] = np.nan
        record["max_drawdown_since_exit"] = np.nan
        return record
    price_frame["close"] = pd.to_numeric(price_frame["close"], errors="coerce")
    entry = float(price_frame.iloc[0]["close"])
    current = float(price_frame.iloc[-1]["close"])
    if entry <= 0:
        record["forward_return_since_exit"] = np.nan
        record["max_return_since_exit"] = np.nan
        record["max_drawdown_since_exit"] = np.nan
        return record
    record["forward_return_since_exit"] = current / entry - 1.0
    record["max_return_since_exit"] = float(price_frame["close"].max() / entry - 1.0)
    record["max_drawdown_since_exit"] = float(price_frame["close"].min() / entry - 1.0)
    record["reentered_top5"] = bool(pd.to_numeric(pd.Series([record.get("current_rank")]), errors="coerce").iloc[0] <= 5) if record.get("current_rank") == record.get("current_rank") else False
    record["reentered_top10"] = bool(pd.to_numeric(pd.Series([record.get("current_rank")]), errors="coerce").iloc[0] <= 10) if record.get("current_rank") == record.get("current_rank") else False
    record["reentered_top20"] = bool(pd.to_numeric(pd.Series([record.get("current_rank")]), errors="coerce").iloc[0] <= 20) if record.get("current_rank") == record.get("current_rank") else False
    record["reconfirmed_T1_M1"] = str(record.get("midtrend_confirmation_state", "")).startswith("T1_M1")
    return record


def _path_class_so_far(row: pd.Series) -> str:
    ret = pd.to_numeric(pd.Series([row.get("forward_return_since_exit")]), errors="coerce").iloc[0]
    dd = pd.to_numeric(pd.Series([row.get("max_drawdown_since_exit")]), errors="coerce").iloc[0]
    if ret >= 0.08 and dd >= -0.05:
        return "immediate_continuation"
    if ret >= 0.12 and bool(row.get("reentered_top10")):
        return "pullback_then_reacceleration"
    if bool(row.get("reentered_top20")) and ret < 0.05:
        return "failed_rebound"
    if ret < 0:
        return "true_exit"
    return "noisy_unclear"


def _watch_summary_csv(watch_daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in ["review_priority", "path_class_so_far", "industry_name_x", "midtrend_confirmation_state", "fundamental_quality_bucket"]:
        if column not in watch_daily.columns:
            continue
        grouped = watch_daily.groupby(column, as_index=False).agg(count=("asset_id", "size"))
        grouped["summary_type"] = column
        grouped = grouped.rename(columns={column: "bucket"})
        rows.append(grouped)
    if "days_since_exit" in watch_daily.columns:
        temp = watch_daily.copy()
        temp["bucket"] = pd.cut(
            pd.to_numeric(temp["days_since_exit"], errors="coerce"),
            bins=[-np.inf, 5, 10, 20, 30, 60],
            labels=["0-5", "6-10", "11-20", "21-30", "31-60"],
        )
        grouped = temp.groupby("bucket", as_index=False).agg(count=("asset_id", "size"))
        grouped["summary_type"] = "days_since_exit_bucket"
        rows.append(grouped)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["summary_type", "bucket", "count"])


def _watch_summary_markdown(watch_daily: pd.DataFrame, summary_csv: pd.DataFrame, trade_date: str) -> str:
    high = watch_daily[watch_daily["review_priority"].astype(str).eq("HIGH")].sort_values(["current_rank", "forward_return_since_exit"], ascending=[True, False]).head(20)
    expired = watch_daily[watch_daily["review_priority"].astype(str).eq("EXPIRED")].head(20)
    lines = [
        f"# Midtrend Post-Exit Watch Summary {trade_date}",
        "",
        f"- total active watch names: {len(watch_daily)}",
        f"- HIGH: {int(watch_daily['review_priority'].astype(str).eq('HIGH').sum()) if not watch_daily.empty else 0}",
        f"- MEDIUM: {int(watch_daily['review_priority'].astype(str).eq('MEDIUM').sum()) if not watch_daily.empty else 0}",
        f"- LOW: {int(watch_daily['review_priority'].astype(str).eq('LOW').sum()) if not watch_daily.empty else 0}",
        f"- EXPIRED: {int(watch_daily['review_priority'].astype(str).eq('EXPIRED').sum()) if not watch_daily.empty else 0}",
        "",
        "## Top High Priority Names",
        high.to_markdown(index=False) if not high.empty else "none",
        "",
        "## Expired Or Risk-Damaged Today",
        expired.to_markdown(index=False) if not expired.empty else "none",
        "",
        "## Summary Buckets",
        summary_csv.to_markdown(index=False) if not summary_csv.empty else "none",
    ]
    return "\n".join(lines) + "\n"


def _daily_final_interpretation(watch_daily: pd.DataFrame, trade_date: str) -> str:
    high = int(watch_daily["review_priority"].astype(str).eq("HIGH").sum()) if not watch_daily.empty else 0
    medium = int(watch_daily["review_priority"].astype(str).eq("MEDIUM").sum()) if not watch_daily.empty else 0
    low = int(watch_daily["review_priority"].astype(str).eq("LOW").sum()) if not watch_daily.empty else 0
    expired = int(watch_daily["review_priority"].astype(str).eq("EXPIRED").sum()) if not watch_daily.empty else 0
    lines = [
        "# Final Interpretation",
        "",
        "1. Was the daily post-exit watch artifact generated successfully? yes.",
        f"2. Active watch names by priority on {trade_date}: HIGH={high}, MEDIUM={medium}, LOW={low}, EXPIRED={expired}.",
        "3. Names that reentered top10/top20 or reconfirmed T1_M1 can be reviewed directly in `midtrend_post_exit_watch_daily.csv`.",
        "4. The artifact is useful for manual review because it converts raw exit events into ranked follow-up buckets without emitting trade instructions.",
        "5. This should be added to Daily Review Lite or a dedicated dashboard page as a research/watch artifact, not as an execution signal.",
        "",
        "No trading strategy logic was changed. Re-entry remains research-only.",
    ]
    return "\n".join(lines) + "\n"
