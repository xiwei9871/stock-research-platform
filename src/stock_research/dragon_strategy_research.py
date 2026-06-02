from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


DRAGON_DIAGNOSTIC_COLUMNS = [
    "trade_date",
    "industry_name",
    "industry_heat_score",
    "industry_focus_score_v2",
    "industry_rank",
    "asset_id",
    "stock_name",
    "close",
    "stock_return_3d",
    "stock_return_5d",
    "stock_return_10d",
    "stock_return_20d",
    "stock_excess_return_vs_industry_5d",
    "stock_excess_return_vs_industry_20d",
    "amount",
    "turnover_rate",
    "amount_vs_20d",
    "trend_lifecycle_stage",
    "stock_relative_strength_score",
    "breakout_strength_score",
    "turnover_amount_score",
    "industry_leadership_score",
    "lifecycle_score",
    "liquidity_score",
    "overheat_penalty",
    "follower_penalty",
    "dragon_score",
    "dragon_rank_in_industry",
    "dragon_role",
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_20d_return",
    "future_10d_max_drawdown",
    "future_20d_max_drawdown",
]

ROLE_EFFECTIVENESS_COLUMNS = [
    "role",
    "sample_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "avg_future_20d_return",
    "median_future_5d_return",
    "median_future_10d_return",
    "win_rate_5d",
    "win_rate_10d",
    "avg_future_10d_max_drawdown",
    "avg_future_20d_max_drawdown",
]

MONTHLY_SUMMARY_COLUMNS = [
    "month",
    "sample_count",
    "hot_industry_count",
    "top_industry_sample_share",
    "dragon_leader_count",
    "overheated_leader_count",
    "cooling_down_count",
    "avg_dragon_score",
    "avg_future_5d_return",
    "avg_future_10d_return",
]

YEARLY_DIAGNOSIS_COLUMNS = [
    "year",
    "dragon_role",
    "sample_count",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "avg_future_20d_return",
    "win_rate_5d",
    "win_rate_10d",
    "avg_future_10d_max_drawdown",
    "avg_future_20d_max_drawdown",
    "hot_industry_count",
    "industry_mainline_concentration",
]

V1_1_OUTPUT_FILENAMES = {
    "diagnostics": "dragon_strategy_v1_1_diagnostics.csv",
    "weak_candidate_audit": "dragon_strategy_v1_1_weak_candidate_audit.csv",
    "role_effectiveness": "dragon_strategy_v1_1_role_effectiveness.csv",
    "yearly_diagnosis": "dragon_strategy_v1_1_yearly_diagnosis.csv",
    "overheat_audit": "dragon_strategy_v1_1_overheat_audit.csv",
    "score_bucket_effectiveness": "dragon_strategy_v1_1_score_bucket_effectiveness.csv",
    "lifecycle_role_effectiveness": "dragon_strategy_v1_1_lifecycle_role_effectiveness.csv",
    "markdown_report": "dragon_strategy_v1_1_report.md",
}

V1_2_OUTPUT_FILENAMES = {
    "diagnostics": "dragon_strategy_v1_2_diagnostics.csv",
    "component_audit": "dragon_strategy_v1_2_component_audit.csv",
    "score_bucket_effectiveness": "dragon_strategy_v1_2_score_bucket_effectiveness.csv",
    "entry_window_effectiveness": "dragon_strategy_v1_2_entry_window_effectiveness.csv",
    "role_effectiveness": "dragon_strategy_v1_2_role_effectiveness.csv",
    "yearly_diagnosis": "dragon_strategy_v1_2_yearly_diagnosis.csv",
    "low_bucket_audit": "dragon_strategy_v1_2_low_bucket_audit.csv",
    "role_entry_cross_effectiveness": "dragon_strategy_v1_2_role_entry_cross_effectiveness.csv",
    "markdown_report": "dragon_strategy_v1_2_report.md",
}

V1_3_OUTPUT_FILENAMES = {
    "diagnostics": "dragon_strategy_v1_3_diagnostics.csv",
    "low_quality_split_audit": "dragon_strategy_v1_3_low_quality_split_audit.csv",
    "entry_score_audit": "dragon_strategy_v1_3_entry_score_audit.csv",
    "entry_score_bucket_effectiveness": "dragon_strategy_v1_3_entry_score_bucket_effectiveness.csv",
    "entry_window_effectiveness": "dragon_strategy_v1_3_entry_window_effectiveness.csv",
    "role_effectiveness": "dragon_strategy_v1_3_role_effectiveness.csv",
    "role_entry_cross_effectiveness": "dragon_strategy_v1_3_role_entry_cross_effectiveness.csv",
    "yearly_diagnosis": "dragon_strategy_v1_3_yearly_diagnosis.csv",
    "follower_penalty_audit": "dragon_strategy_v1_3_follower_penalty_audit.csv",
    "markdown_report": "dragon_strategy_v1_3_report.md",
}

EFFECTIVENESS_COLUMNS = [
    "sample_count",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "avg_future_20d_return",
    "median_future_5d_return",
    "median_future_10d_return",
    "median_future_20d_return",
    "win_rate_5d",
    "win_rate_10d",
    "win_rate_20d",
    "avg_future_10d_max_drawdown",
    "avg_future_20d_max_drawdown",
]

FULL_EFFECTIVENESS_COLUMNS = [
    "sample_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "avg_future_20d_return",
    "median_future_5d_return",
    "median_future_10d_return",
    "median_future_20d_return",
    "win_rate_5d",
    "win_rate_10d",
    "win_rate_20d",
    "avg_future_10d_max_drawdown",
    "avg_future_20d_max_drawdown",
]

WEAK_CANDIDATE_AUDIT_COLUMNS = [
    "year",
    "industry_name",
    "industry_rank",
    "industry_heat_score_bucket",
    "industry_focus_score_v2_bucket",
    "dragon_score_bucket",
    "stock_relative_strength_score_bucket",
    "breakout_strength_score_bucket",
    "turnover_amount_score_bucket",
    "industry_leadership_score_bucket",
    "lifecycle_score_bucket",
    "overheat_penalty_bucket",
    "follower_penalty_bucket",
    "trend_lifecycle_stage",
    *EFFECTIVENESS_COLUMNS,
]

SCORE_BUCKET_EFFECTIVENESS_COLUMNS = [
    "year",
    "score_bucket",
    *EFFECTIVENESS_COLUMNS,
]

LIFECYCLE_ROLE_EFFECTIVENESS_COLUMNS = [
    "trend_lifecycle_stage",
    "dragon_role",
    *EFFECTIVENESS_COLUMNS,
]

OVERHEAT_AUDIT_COLUMNS = [
    "rule_version",
    *EFFECTIVENESS_COLUMNS,
]

V1_2_COMPONENTS = [
    "stock_relative_strength_score",
    "breakout_strength_score",
    "turnover_amount_score",
    "industry_leadership_score",
    "lifecycle_score",
    "liquidity_score",
    "overheat_penalty",
    "follower_penalty",
    "dragon_status_score",
    "dragon_entry_score",
    "dragon_risk_score",
]

V1_2_DIAGNOSTIC_COLUMNS = [
    *DRAGON_DIAGNOSTIC_COLUMNS[:27],
    "dragon_status_score",
    "dragon_entry_score",
    "dragon_risk_score",
    "entry_window",
    *DRAGON_DIAGNOSTIC_COLUMNS[27:],
]

COMPONENT_AUDIT_COLUMNS = [
    "component_name",
    "bucket",
    "signal_type",
    *EFFECTIVENESS_COLUMNS,
]

LOW_BUCKET_AUDIT_COLUMNS = [
    "year",
    "industry_name",
    "industry_rank",
    "industry_focus_score_v2_bucket",
    "trend_lifecycle_stage",
    "dragon_role",
    "stock_relative_strength_score_bucket",
    "breakout_strength_score_bucket",
    "turnover_amount_score_bucket",
    "industry_leadership_score_bucket",
    "overheat_penalty_bucket",
    "follower_penalty_bucket",
    "amount_vs_20d_bucket",
    *EFFECTIVENESS_COLUMNS,
]

SCORE_BUCKET_V1_2_COLUMNS = [
    "year",
    "score_name",
    "score_bucket",
    *EFFECTIVENESS_COLUMNS,
]

ENTRY_WINDOW_EFFECTIVENESS_COLUMNS = [
    "entry_window",
    *FULL_EFFECTIVENESS_COLUMNS,
]

ROLE_ENTRY_CROSS_EFFECTIVENESS_COLUMNS = [
    "dragon_role",
    "entry_window",
    *EFFECTIVENESS_COLUMNS,
]

YEARLY_V1_2_DIAGNOSIS_COLUMNS = [
    "year",
    "diagnosis_type",
    "score_name",
    "score_bucket",
    "entry_window",
    "dragon_role",
    *EFFECTIVENESS_COLUMNS,
]

V1_3_DIAGNOSTIC_COLUMNS = [
    *V1_2_DIAGNOSTIC_COLUMNS[:30],
    "dragon_entry_score_v2",
    "entry_window_v2",
    *V1_2_DIAGNOSTIC_COLUMNS[30:],
]

ENTRY_SCORE_BUCKET_COLUMNS = [
    "bucket",
    *EFFECTIVENESS_COLUMNS,
]

ENTRY_SCORE_AUDIT_COLUMNS = [
    "score_name",
    "bucket",
    *EFFECTIVENESS_COLUMNS,
]

ENTRY_WINDOW_V2_EFFECTIVENESS_COLUMNS = [
    "entry_window_v2",
    *FULL_EFFECTIVENESS_COLUMNS,
]

ROLE_ENTRY_V2_CROSS_EFFECTIVENESS_COLUMNS = [
    "dragon_role",
    "entry_window_v2",
    *EFFECTIVENESS_COLUMNS,
]

LOW_QUALITY_SPLIT_AUDIT_COLUMNS = [
    "entry_window_v2",
    *FULL_EFFECTIVENESS_COLUMNS,
]

FOLLOWER_PENALTY_AUDIT_COLUMNS = [
    "follower_penalty_bucket",
    "industry_heat_score_bucket",
    "dragon_risk_score_bucket",
    "stock_relative_strength_score_bucket",
    "trend_lifecycle_stage",
    "dragon_role",
    "entry_window_v2",
    *EFFECTIVENESS_COLUMNS,
]

YEARLY_V1_3_DIAGNOSIS_COLUMNS = [
    "year",
    "diagnosis_type",
    "bucket",
    "entry_window_v2",
    "dragon_role",
    *EFFECTIVENESS_COLUMNS,
]

OUTPUT_FILENAMES = {
    "diagnostics": "dragon_strategy_v1_diagnostics.csv",
    "monthly_summary": "dragon_strategy_v1_monthly_summary.csv",
    "role_effectiveness": "dragon_strategy_v1_role_effectiveness.csv",
    "yearly_diagnosis": "dragon_strategy_v1_yearly_diagnosis.csv",
    "markdown_report": "dragon_strategy_v1_report.md",
}

DRAGON_SCORE_WEIGHTS = {
    "stock_relative_strength_score": 0.25,
    "breakout_strength_score": 0.20,
    "turnover_amount_score": 0.20,
    "industry_leadership_score": 0.15,
    "lifecycle_score": 0.10,
    "liquidity_score": 0.10,
}

LIFECYCLE_SCORE_MAP = {
    "warming_up": 0.85,
    "early": 0.85,
    "breakout": 1.0,
    "early_mid": 0.90,
    "acceleration": 0.80,
    "mid": 0.70,
    "divergence": 0.45,
    "late_mid": 0.45,
    "late": 0.30,
    "cooling_down": 0.10,
    "unknown": 0.50,
}


@dataclass(frozen=True)
class DragonResearchConfig:
    start_date: object
    end_date: object
    hot_industry_top_n: int = 6
    adjust_type: str = "hfq"
    industry_system: str = "csrc"
    industry_level: int = 1
    output_dir: str | Path = Path("/Users/xiwei/stock_research/outputs/research")
    industry_diagnostics_path: str | Path | None = None
    candidate_scores_path: str | Path | None = None
    lifecycle_samples_path: str | Path | None = None
    service: str = SETTINGS.research_service


def compute_dragon_scores(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        for column in _score_columns():
            result[column] = pd.Series(dtype="float64")
        return result

    component_columns = [*DRAGON_SCORE_WEIGHTS.keys(), "overheat_penalty", "follower_penalty"]
    if all(column in result.columns for column in component_columns):
        _ensure_numeric_columns(result, component_columns)
        raw_score = sum(
            result[column] * weight for column, weight in DRAGON_SCORE_WEIGHTS.items()
        )
        result["dragon_score"] = raw_score - result["overheat_penalty"] - result["follower_penalty"]
        return result

    _ensure_numeric_columns(
        result,
        [
            "stock_return_3d",
            "stock_return_5d",
            "stock_return_10d",
            "stock_return_20d",
            "industry_return_5d",
            "industry_return_20d",
            "market_return_5d",
            "market_return_20d",
            "stock_excess_return_vs_industry_5d",
            "stock_excess_return_vs_industry_20d",
            "amount",
            "turnover_rate",
            "amount_vs_20d",
            "outperform_industry_days_5",
            "return_rank_pct_in_industry",
            "amount_rank_pct_in_industry",
        ],
    )
    _ensure_bool_columns(result, ["new_high_20d", "new_high_60d"])
    if "trend_lifecycle_stage" not in result.columns:
        result["trend_lifecycle_stage"] = "unknown"

    result["stock_relative_strength_score"] = (
        0.20 * _scale(result["stock_return_3d"], -0.05, 0.12)
        + 0.20 * _scale(result["stock_return_5d"], -0.08, 0.18)
        + 0.20 * _scale(result["stock_return_10d"], -0.10, 0.28)
        + 0.20 * _scale(result["stock_excess_return_vs_industry_5d"], -0.06, 0.12)
        + 0.20 * _scale(result["stock_excess_return_vs_industry_20d"], -0.10, 0.25)
    )
    result["breakout_strength_score"] = (
        0.35 * result["new_high_20d"].astype(float)
        + 0.35 * result["new_high_60d"].astype(float)
        + 0.30 * _scale(result["outperform_industry_days_5"], 0.0, 5.0)
    )
    result["turnover_amount_score"] = (
        0.45 * result["amount_rank_pct_in_industry"].fillna(0.0)
        + 0.25 * _scale(result["turnover_rate"], 0.5, 12.0)
        + 0.30 * _healthy_amount_expansion_score(result["amount_vs_20d"])
    )
    result["industry_leadership_score"] = (
        0.45 * result["return_rank_pct_in_industry"].fillna(0.0)
        + 0.30 * result["amount_rank_pct_in_industry"].fillna(0.0)
        + 0.25 * _scale(result["stock_excess_return_vs_industry_20d"], -0.08, 0.20)
    )
    result["lifecycle_score"] = (
        result["trend_lifecycle_stage"]
        .fillna("unknown")
        .astype(str)
        .map(LIFECYCLE_SCORE_MAP)
        .fillna(0.50)
        .astype(float)
    )
    result["liquidity_score"] = (
        0.70 * _scale(result["amount"], 30_000_000.0, 300_000_000.0)
        + 0.30 * _scale(result["turnover_rate"], 0.5, 8.0)
    )
    result["overheat_penalty"] = (
        0.30 * _scale(result["stock_return_5d"], 0.12, 0.35)
        + 0.25 * _scale(result["stock_return_10d"], 0.20, 0.55)
        + 0.25 * _scale(result["amount_vs_20d"], 2.0, 5.0)
        + 0.20 * _scale(result["turnover_rate"], 12.0, 30.0)
    )
    result["follower_penalty"] = (
        0.30 * _scale(-result["stock_excess_return_vs_industry_5d"], 0.0, 0.08)
        + 0.30 * _scale(-result["stock_excess_return_vs_industry_20d"], 0.0, 0.16)
        + 0.20 * (1.0 - result["return_rank_pct_in_industry"].fillna(0.0))
        + 0.20 * (1.0 - result["breakout_strength_score"].fillna(0.0))
    )
    raw_score = sum(
        result[column] * weight for column, weight in DRAGON_SCORE_WEIGHTS.items()
    )
    result["dragon_score"] = raw_score - result["overheat_penalty"] - result["follower_penalty"]
    return result


def assign_dragon_roles(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        result["dragon_role"] = pd.Series(dtype="object")
        result["dragon_rank_in_industry"] = pd.Series(dtype="Int64")
        return result

    if "dragon_score" not in result.columns:
        result = compute_dragon_scores(result)
    result["trade_date"] = result["trade_date"].map(_iso_date)
    result["industry_name"] = result["industry_name"].astype(str)
    result["dragon_rank_in_industry"] = (
        result.groupby(["trade_date", "industry_name"])["dragon_score"]
        .rank(method="first", ascending=False)
        .astype("Int64")
    )
    roles = [_role_for_row(row) for row in result.to_dict("records")]
    result["dragon_role"] = roles
    return result


def effective_membership_for_dates(dates: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    date_frame = dates.copy()
    if date_frame.empty:
        result = date_frame.copy()
        result["industry_name"] = pd.Series(dtype="object")
        return result

    member_frame = memberships.copy()
    date_frame["asset_id"] = date_frame["asset_id"].astype(str)
    date_frame["trade_date"] = pd.to_datetime(date_frame["trade_date"]).astype("datetime64[ns]")
    member_frame["asset_id"] = member_frame["asset_id"].astype(str)
    member_frame["start_date"] = pd.to_datetime(
        member_frame.get("start_date", member_frame.get("effective_from")),
        errors="coerce",
    ).astype("datetime64[ns]")
    if "end_date" in member_frame.columns:
        end = member_frame["end_date"]
    else:
        end = member_frame.get("effective_to")
    member_frame["end_date"] = pd.to_datetime(end, errors="coerce").astype("datetime64[ns]")

    rows = []
    member_groups = {
        str(asset_id): group.sort_values("start_date").reset_index(drop=True)
        for asset_id, group in member_frame.groupby("asset_id", sort=False)
    }
    for asset_id, asset_dates in date_frame.groupby("asset_id", sort=False):
        members = member_groups.get(str(asset_id))
        if members is None or members.empty:
            continue
        left = asset_dates.sort_values("trade_date").reset_index(drop=True)
        right = members[["industry_name", "start_date", "end_date"]].sort_values("start_date")
        matched = pd.merge_asof(
            left,
            right,
            left_on="trade_date",
            right_on="start_date",
            direction="backward",
        )
        valid = matched[
            matched["start_date"].notna()
            & (matched["end_date"].isna() | (matched["end_date"] >= matched["trade_date"]))
        ].copy()
        if not valid.empty:
            rows.append(valid)
    if not rows:
        result = date_frame.copy()
        result["trade_date"] = result["trade_date"].dt.strftime("%Y-%m-%d")
        result["industry_name"] = pd.NA
        return result
    valid = pd.concat(rows, ignore_index=True)
    valid["trade_date"] = valid["trade_date"].dt.strftime("%Y-%m-%d")
    return valid.reset_index(drop=True)


def build_dragon_diagnostics(
    *,
    bars: pd.DataFrame,
    memberships: pd.DataFrame,
    industry_diagnostics: pd.DataFrame,
    start_date: object,
    end_date: object,
    stock_names: pd.DataFrame | None = None,
    lifecycle_samples: pd.DataFrame | None = None,
    candidate_scores: pd.DataFrame | None = None,
    hot_industry_top_n: int = 6,
) -> pd.DataFrame:
    price_frame = _normalize_bars(bars)
    if price_frame.empty:
        return pd.DataFrame(columns=DRAGON_DIAGNOSTIC_COLUMNS)
    start = _iso_date(start_date)
    end = _iso_date(end_date)

    industry = _normalize_industry_diagnostics(industry_diagnostics)
    target_dates = set(industry.loc[
        (industry["trade_date"] >= start) & (industry["trade_date"] <= end),
        "trade_date",
    ])
    if not target_dates:
        return pd.DataFrame(columns=DRAGON_DIAGNOSTIC_COLUMNS)

    features = _build_stock_features(price_frame)
    features = features[features["trade_date"].isin(target_dates)].copy()
    if features.empty:
        return pd.DataFrame(columns=DRAGON_DIAGNOSTIC_COLUMNS)
    membership_lookup = effective_membership_for_dates(
        features[["trade_date", "asset_id"]].drop_duplicates(),
        memberships,
    )
    features = features.merge(
        membership_lookup[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="left",
    )
    features = features.dropna(subset=["industry_name"])
    features = _add_industry_relative_features(features)
    features = features.merge(industry, on=["trade_date", "industry_name"], how="inner")
    features = _filter_hot_industries(features, hot_industry_top_n=hot_industry_top_n)
    if features.empty:
        return pd.DataFrame(columns=DRAGON_DIAGNOSTIC_COLUMNS)

    if stock_names is not None and not stock_names.empty:
        names = stock_names.copy()
        names["asset_id"] = names["asset_id"].astype(str)
        features = features.merge(names[["asset_id", "stock_name"]], on="asset_id", how="left")
    elif "stock_name" not in features.columns:
        features["stock_name"] = ""

    if lifecycle_samples is not None and not lifecycle_samples.empty:
        lifecycle = lifecycle_samples.copy()
        lifecycle["trade_date"] = lifecycle["trade_date"].map(_iso_date)
        lifecycle["asset_id"] = lifecycle["asset_id"].astype(str)
        stage_col = "stage" if "stage" in lifecycle.columns else "trend_lifecycle_stage"
        lifecycle = lifecycle.rename(columns={stage_col: "trend_lifecycle_stage"})
        features = features.merge(
            lifecycle[["trade_date", "asset_id", "trend_lifecycle_stage"]],
            on=["trade_date", "asset_id"],
            how="left",
        )
    if "trend_lifecycle_stage" not in features.columns:
        features["trend_lifecycle_stage"] = _fallback_lifecycle_stage(features)
    else:
        features["trend_lifecycle_stage"] = features["trend_lifecycle_stage"].fillna(
            _fallback_lifecycle_stage(features)
        )

    if candidate_scores is not None and not candidate_scores.empty:
        candidates = candidate_scores.copy()
        candidates["trade_date"] = candidates["trade_date"].map(_iso_date)
        candidates["asset_id"] = candidates["asset_id"].astype(str)
        features = features.merge(candidates, on=["trade_date", "asset_id"], how="left")

    features = features[(features["trade_date"] >= start) & (features["trade_date"] <= end)].copy()
    scored = assign_dragon_roles(compute_dragon_scores(features))
    with_future = _append_future_diagnostics(scored, price_frame)
    return (
        with_future.reindex(columns=DRAGON_DIAGNOSTIC_COLUMNS)
        .sort_values(["trade_date", "industry_rank", "dragon_rank_in_industry", "asset_id"])
        .reset_index(drop=True)
    )


def summarize_role_effectiveness(diagnostics: pd.DataFrame) -> pd.DataFrame:
    if diagnostics.empty or "dragon_role" not in diagnostics.columns:
        return pd.DataFrame(columns=ROLE_EFFECTIVENESS_COLUMNS)
    frame = diagnostics.copy()
    for column in [
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_20d_return",
        "future_10d_max_drawdown",
        "future_20d_max_drawdown",
    ]:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")

    rows = []
    for role, group in frame.groupby("dragon_role", sort=True):
        rows.append(
            {
                "role": role,
                "sample_count": int(len(group)),
                "avg_future_1d_return": group["future_1d_return"].mean(),
                "avg_future_3d_return": group["future_3d_return"].mean(),
                "avg_future_5d_return": group["future_5d_return"].mean(),
                "avg_future_10d_return": group["future_10d_return"].mean(),
                "avg_future_20d_return": group["future_20d_return"].mean(),
                "median_future_5d_return": group["future_5d_return"].median(),
                "median_future_10d_return": group["future_10d_return"].median(),
                "win_rate_5d": (group["future_5d_return"] > 0).mean(),
                "win_rate_10d": (group["future_10d_return"] > 0).mean(),
                "avg_future_10d_max_drawdown": group["future_10d_max_drawdown"].mean(),
                "avg_future_20d_max_drawdown": group["future_20d_max_drawdown"].mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=ROLE_EFFECTIVENESS_COLUMNS)


def build_weak_candidate_audit(diagnostics: pd.DataFrame, *, buckets: int = 5) -> pd.DataFrame:
    if diagnostics.empty:
        return pd.DataFrame(columns=WEAK_CANDIDATE_AUDIT_COLUMNS)
    frame = _normalize_diagnostics_frame(diagnostics)
    weak = frame[frame["dragon_role"] == "weak_candidate"].copy()
    if weak.empty:
        return pd.DataFrame(columns=WEAK_CANDIDATE_AUDIT_COLUMNS)
    weak["year"] = pd.to_datetime(weak["trade_date"]).dt.year.astype(str)
    bucket_sources = [
        "industry_heat_score",
        "industry_focus_score_v2",
        "dragon_score",
        "stock_relative_strength_score",
        "breakout_strength_score",
        "turnover_amount_score",
        "industry_leadership_score",
        "lifecycle_score",
        "overheat_penalty",
        "follower_penalty",
    ]
    for column in bucket_sources:
        weak[f"{column}_bucket"] = _bucket_by_year(weak, column, buckets=buckets)
    dimensions = [
        "industry_name",
        "industry_rank",
        *[f"{column}_bucket" for column in bucket_sources],
        "trend_lifecycle_stage",
    ]
    rows = []
    for dimension in dimensions:
        grouped = _group_effectiveness(weak, ["year", dimension])
        for record in grouped.to_dict("records"):
            row = {column: "all" for column in WEAK_CANDIDATE_AUDIT_COLUMNS}
            row["year"] = record["year"]
            row[dimension] = record[dimension]
            for column in EFFECTIVENESS_COLUMNS:
                row[column] = record[column]
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=WEAK_CANDIDATE_AUDIT_COLUMNS)


def build_score_bucket_effectiveness(
    diagnostics: pd.DataFrame,
    *,
    buckets: int = 10,
) -> pd.DataFrame:
    if diagnostics.empty:
        return pd.DataFrame(columns=SCORE_BUCKET_EFFECTIVENESS_COLUMNS)
    frame = _normalize_diagnostics_frame(diagnostics)
    frames = []
    all_frame = frame.copy()
    all_frame["year"] = "all"
    frames.append(all_frame)
    by_year = frame.copy()
    by_year["year"] = pd.to_datetime(by_year["trade_date"]).dt.year.astype(str)
    frames.append(by_year)
    combined = pd.concat(frames, ignore_index=True)
    combined["score_bucket"] = _bucket_by_year(combined, "dragon_score", buckets=buckets)
    result = _group_effectiveness(combined, ["year", "score_bucket"])
    return result.reindex(columns=SCORE_BUCKET_EFFECTIVENESS_COLUMNS)


def build_lifecycle_role_effectiveness(diagnostics: pd.DataFrame) -> pd.DataFrame:
    if diagnostics.empty:
        return pd.DataFrame(columns=LIFECYCLE_ROLE_EFFECTIVENESS_COLUMNS)
    frame = _normalize_diagnostics_frame(diagnostics)
    result = _group_effectiveness(frame, ["trend_lifecycle_stage", "dragon_role"])
    return result.reindex(columns=LIFECYCLE_ROLE_EFFECTIVENESS_COLUMNS)


def build_overheat_audit(v1_diagnostics: pd.DataFrame, v1_1_diagnostics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, frame in [
        ("v1_original", v1_diagnostics),
        ("v1_1_calibrated", v1_1_diagnostics),
    ]:
        normalized = _normalize_diagnostics_frame(frame)
        overheated = normalized[normalized["dragon_role"] == "overheated_leader"]
        stats = _effectiveness_stats(overheated)
        row = {"rule_version": label}
        row.update(stats.to_dict())
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=OVERHEAT_AUDIT_COLUMNS)


def build_dragon_v1_1_outputs_from_diagnostics(
    diagnostics: pd.DataFrame,
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
) -> dict[str, Any]:
    v1 = _normalize_diagnostics_frame(diagnostics)
    v1_1 = assign_dragon_roles(compute_dragon_scores(v1))
    v1_1 = v1_1.reindex(columns=DRAGON_DIAGNOSTIC_COLUMNS)
    role_effectiveness = summarize_role_effectiveness(v1_1)
    yearly_diagnosis = summarize_yearly(v1_1)
    weak_candidate_audit = build_weak_candidate_audit(v1_1)
    overheat_audit = build_overheat_audit(v1, v1_1)
    score_bucket_effectiveness = build_score_bucket_effectiveness(v1_1)
    lifecycle_role_effectiveness = build_lifecycle_role_effectiveness(v1_1)
    v1_role_effectiveness = summarize_role_effectiveness(v1)
    v1_vs_v1_1 = _compare_role_effectiveness(v1_role_effectiveness, role_effectiveness)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {key: str(out / filename) for key, filename in V1_1_OUTPUT_FILENAMES.items()}
    v1_1.to_csv(paths["diagnostics"], index=False)
    weak_candidate_audit.to_csv(paths["weak_candidate_audit"], index=False)
    role_effectiveness.to_csv(paths["role_effectiveness"], index=False)
    yearly_diagnosis.to_csv(paths["yearly_diagnosis"], index=False)
    overheat_audit.to_csv(paths["overheat_audit"], index=False)
    score_bucket_effectiveness.to_csv(paths["score_bucket_effectiveness"], index=False)
    lifecycle_role_effectiveness.to_csv(paths["lifecycle_role_effectiveness"], index=False)
    Path(paths["markdown_report"]).write_text(
        _markdown_report_v1_1(
            start_date=_iso_date(start_date),
            end_date=_iso_date(end_date),
            v1_role_effectiveness=v1_role_effectiveness,
            role_effectiveness=role_effectiveness,
            v1_vs_v1_1=v1_vs_v1_1,
            weak_candidate_audit=weak_candidate_audit,
            score_bucket_effectiveness=score_bucket_effectiveness,
            lifecycle_role_effectiveness=lifecycle_role_effectiveness,
            overheat_audit=overheat_audit,
        ),
        encoding="utf-8",
    )
    return {
        "paths": paths,
        "diagnostics": v1_1,
        "weak_candidate_audit": weak_candidate_audit,
        "role_effectiveness": role_effectiveness,
        "yearly_diagnosis": yearly_diagnosis,
        "overheat_audit": overheat_audit,
        "score_bucket_effectiveness": score_bucket_effectiveness,
        "lifecycle_role_effectiveness": lifecycle_role_effectiveness,
        "v1_vs_v1_1": v1_vs_v1_1,
    }


def compute_v1_2_scores(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = _normalize_diagnostics_frame(diagnostics)
    if frame.empty:
        for column in ["dragon_status_score", "dragon_entry_score", "dragon_risk_score"]:
            frame[column] = pd.Series(dtype="float64")
        return frame

    for column in V1_2_COMPONENTS:
        if column not in frame.columns:
            frame[column] = 0.0
    _ensure_numeric_columns(
        frame,
        [
            "stock_relative_strength_score",
            "breakout_strength_score",
            "turnover_amount_score",
            "industry_leadership_score",
            "lifecycle_score",
            "liquidity_score",
            "overheat_penalty",
            "follower_penalty",
            "stock_return_3d",
            "stock_return_5d",
            "stock_return_10d",
            "stock_return_20d",
            "stock_excess_return_vs_industry_5d",
            "stock_excess_return_vs_industry_20d",
            "amount_vs_20d",
            "turnover_rate",
            "industry_focus_score_v2",
            "industry_heat_score",
            "industry_rank",
            "dragon_score",
        ],
    )

    status_score = sum(
        frame[column] * weight for column, weight in DRAGON_SCORE_WEIGHTS.items()
    )
    frame["dragon_status_score"] = status_score.clip(0.0, 1.0)

    stage = frame["trend_lifecycle_stage"].fillna("unknown").astype(str)
    late_stage_risk = stage.map(
        {
            "cooling_down": 1.0,
            "divergence": 0.75,
            "late": 0.85,
            "late_mid": 0.65,
            "acceleration": 0.30,
            "breakout": 0.10,
            "warming_up": 0.05,
            "early": 0.05,
            "early_mid": 0.15,
            "mid": 0.30,
            "unknown": 0.25,
        }
    ).fillna(0.25)
    short_return_risk = (
        0.40 * _scale(frame["stock_return_5d"], 0.12, 0.35)
        + 0.35 * _scale(frame["stock_return_10d"], 0.20, 0.55)
        + 0.25 * _scale(frame["stock_return_20d"], 0.35, 0.80)
    )
    amount_pulse_risk = _scale(frame["amount_vs_20d"], 2.0, 5.0)
    turnover_risk = _scale(frame["turnover_rate"], 12.0, 30.0)
    crowded_status_risk = _scale(frame["dragon_status_score"], 0.78, 0.95)
    frame["dragon_risk_score"] = (
        0.35 * frame["overheat_penalty"]
        + 0.20 * amount_pulse_risk
        + 0.18 * short_return_risk
        + 0.10 * turnover_risk
        + 0.10 * late_stage_risk
        + 0.07 * crowded_status_risk
    ).clip(0.0, 1.0)

    entry_stage_score = stage.map(
        {
            "warming_up": 1.0,
            "early": 1.0,
            "breakout": 0.95,
            "early_mid": 0.85,
            "acceleration": 0.65,
            "mid": 0.50,
            "divergence": 0.15,
            "late_mid": 0.20,
            "late": 0.10,
            "cooling_down": 0.0,
            "unknown": 0.45,
        }
    ).fillna(0.45)
    relative_turn_score = (
        0.35 * _scale(frame["stock_return_3d"], -0.02, 0.08)
        + 0.30 * _scale(frame["stock_return_5d"], -0.03, 0.12)
        + 0.20 * _scale(frame["stock_excess_return_vs_industry_5d"], -0.02, 0.08)
        + 0.15 * _scale(frame["stock_excess_return_vs_industry_20d"], -0.08, 0.10)
    )
    status_window_score = (1.0 - (frame["dragon_status_score"] - 0.42).abs() / 0.42).clip(0.0, 1.0)
    not_extended_score = (1.0 - _scale(frame["stock_return_20d"], 0.18, 0.55)).clip(0.0, 1.0)
    healthy_amount_score = _healthy_amount_expansion_score(frame["amount_vs_20d"])
    raw_entry_score = (
        0.22 * not_extended_score
        + 0.18 * (1.0 - frame["dragon_risk_score"])
        + 0.16 * entry_stage_score
        + 0.14 * healthy_amount_score
        + 0.12 * status_window_score
        + 0.10 * relative_turn_score
        + 0.05 * frame["breakout_strength_score"]
        + 0.03 * frame["liquidity_score"]
        - 0.05 * frame["follower_penalty"]
    )
    frame["dragon_entry_score"] = raw_entry_score.clip(0.0, 1.0)
    return frame


def assign_entry_windows(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = compute_v1_2_scores(diagnostics)
    if frame.empty:
        frame["entry_window"] = pd.Series(dtype="object")
        return frame
    frame["entry_window"] = [_entry_window_for_row(row) for row in frame.to_dict("records")]
    return frame


def build_v1_2_component_audit(diagnostics: pd.DataFrame, *, buckets: int = 10) -> pd.DataFrame:
    frame = assign_entry_windows(diagnostics)
    if frame.empty:
        return pd.DataFrame(columns=COMPONENT_AUDIT_COLUMNS)
    rows = []
    for component in V1_2_COMPONENTS:
        data = frame.copy()
        data["bucket"] = _quantile_bucket(data[component], buckets)
        grouped = _group_effectiveness(data, ["bucket"])
        signal_type = _classify_component_signal(grouped)
        for record in grouped.to_dict("records"):
            row = {"component_name": component, "bucket": record["bucket"], "signal_type": signal_type}
            for column in EFFECTIVENESS_COLUMNS:
                row[column] = record[column]
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=COMPONENT_AUDIT_COLUMNS)


def build_v1_2_score_bucket_effectiveness(
    diagnostics: pd.DataFrame,
    *,
    buckets: int = 10,
) -> pd.DataFrame:
    frame = assign_entry_windows(diagnostics)
    if frame.empty:
        return pd.DataFrame(columns=SCORE_BUCKET_V1_2_COLUMNS)
    frames = []
    for score_name in ["dragon_status_score", "dragon_entry_score", "dragon_risk_score"]:
        for year_label, data in _all_and_year_frames(frame):
            bucketed = data.copy()
            bucketed["year"] = year_label
            bucketed["score_name"] = score_name
            bucketed["score_bucket"] = _bucket_by_year(bucketed, score_name, buckets=buckets)
            frames.append(bucketed)
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    result = _group_effectiveness(combined, ["year", "score_name", "score_bucket"])
    return result.reindex(columns=SCORE_BUCKET_V1_2_COLUMNS)


def build_entry_window_effectiveness(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = assign_entry_windows(diagnostics)
    result = _group_full_effectiveness(frame, ["entry_window"])
    return result.reindex(columns=ENTRY_WINDOW_EFFECTIVENESS_COLUMNS)


def build_role_entry_cross_effectiveness(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = assign_entry_windows(diagnostics)
    result = _group_effectiveness(frame, ["dragon_role", "entry_window"])
    return result.reindex(columns=ROLE_ENTRY_CROSS_EFFECTIVENESS_COLUMNS)


def build_low_bucket_audit(
    diagnostics: pd.DataFrame,
    *,
    buckets: int = 10,
    low_bucket_max: int = 2,
) -> pd.DataFrame:
    frame = assign_entry_windows(diagnostics)
    if frame.empty:
        return pd.DataFrame(columns=LOW_BUCKET_AUDIT_COLUMNS)
    data = frame.copy()
    data["year"] = pd.to_datetime(data["trade_date"]).dt.year.astype(str)
    data["dragon_score_bucket"] = _bucket_by_year(data, "dragon_score", buckets=buckets)
    low = data[pd.to_numeric(data["dragon_score_bucket"], errors="coerce") <= int(low_bucket_max)].copy()
    if low.empty:
        return pd.DataFrame(columns=LOW_BUCKET_AUDIT_COLUMNS)
    bucket_sources = [
        "industry_focus_score_v2",
        "stock_relative_strength_score",
        "breakout_strength_score",
        "turnover_amount_score",
        "industry_leadership_score",
        "overheat_penalty",
        "follower_penalty",
        "amount_vs_20d",
    ]
    for column in bucket_sources:
        low[f"{column}_bucket"] = _bucket_by_year(low, column, buckets=buckets)
    dimensions = [
        "industry_name",
        "industry_rank",
        "industry_focus_score_v2_bucket",
        "trend_lifecycle_stage",
        "dragon_role",
        "stock_relative_strength_score_bucket",
        "breakout_strength_score_bucket",
        "turnover_amount_score_bucket",
        "industry_leadership_score_bucket",
        "overheat_penalty_bucket",
        "follower_penalty_bucket",
        "amount_vs_20d_bucket",
    ]
    rows = []
    for dimension in dimensions:
        grouped = _group_effectiveness(low, ["year", dimension])
        for record in grouped.to_dict("records"):
            row = {column: "all" for column in LOW_BUCKET_AUDIT_COLUMNS}
            row["year"] = record["year"]
            row[dimension] = record[dimension]
            for column in EFFECTIVENESS_COLUMNS:
                row[column] = record[column]
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=LOW_BUCKET_AUDIT_COLUMNS)


def build_v1_2_yearly_diagnosis(diagnostics: pd.DataFrame, *, buckets: int = 10) -> pd.DataFrame:
    frame = assign_entry_windows(diagnostics)
    if frame.empty:
        return pd.DataFrame(columns=YEARLY_V1_2_DIAGNOSIS_COLUMNS)
    frame = frame.copy()
    frame["year"] = pd.to_datetime(frame["trade_date"]).dt.year.astype(str)
    rows = []
    for score_name in ["dragon_status_score", "dragon_entry_score", "dragon_risk_score"]:
        data = frame.copy()
        data["score_name"] = score_name
        data["score_bucket"] = _bucket_by_year(data, score_name, buckets=buckets)
        grouped = _group_effectiveness(data, ["year", "score_name", "score_bucket"])
        for record in grouped.to_dict("records"):
            rows.append(_yearly_v1_2_row(record, "score_bucket"))
    for grouped, diagnosis_type in [
        (_group_effectiveness(frame, ["year", "entry_window"]), "entry_window"),
        (_group_effectiveness(frame, ["year", "dragon_role", "entry_window"]), "role_entry_window"),
    ]:
        for record in grouped.to_dict("records"):
            rows.append(_yearly_v1_2_row(record, diagnosis_type))
    return pd.DataFrame(rows).reindex(columns=YEARLY_V1_2_DIAGNOSIS_COLUMNS)


def build_dragon_v1_2_outputs_from_diagnostics(
    diagnostics: pd.DataFrame,
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
) -> dict[str, Any]:
    v1_2 = assign_entry_windows(compute_v1_2_scores(diagnostics))
    v1_2 = v1_2.reindex(columns=V1_2_DIAGNOSTIC_COLUMNS)
    component_audit = build_v1_2_component_audit(v1_2)
    score_bucket_effectiveness = build_v1_2_score_bucket_effectiveness(v1_2)
    entry_window_effectiveness = build_entry_window_effectiveness(v1_2)
    role_effectiveness = summarize_role_effectiveness(v1_2)
    yearly_diagnosis = build_v1_2_yearly_diagnosis(v1_2)
    low_bucket_audit = build_low_bucket_audit(v1_2)
    role_entry_cross_effectiveness = build_role_entry_cross_effectiveness(v1_2)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {key: str(out / filename) for key, filename in V1_2_OUTPUT_FILENAMES.items()}
    v1_2.to_csv(paths["diagnostics"], index=False)
    component_audit.to_csv(paths["component_audit"], index=False)
    score_bucket_effectiveness.to_csv(paths["score_bucket_effectiveness"], index=False)
    entry_window_effectiveness.to_csv(paths["entry_window_effectiveness"], index=False)
    role_effectiveness.to_csv(paths["role_effectiveness"], index=False)
    yearly_diagnosis.to_csv(paths["yearly_diagnosis"], index=False)
    low_bucket_audit.to_csv(paths["low_bucket_audit"], index=False)
    role_entry_cross_effectiveness.to_csv(paths["role_entry_cross_effectiveness"], index=False)
    Path(paths["markdown_report"]).write_text(
        _markdown_report_v1_2(
            start_date=_iso_date(start_date),
            end_date=_iso_date(end_date),
            component_audit=component_audit,
            score_bucket_effectiveness=score_bucket_effectiveness,
            entry_window_effectiveness=entry_window_effectiveness,
            role_effectiveness=role_effectiveness,
            yearly_diagnosis=yearly_diagnosis,
            low_bucket_audit=low_bucket_audit,
            role_entry_cross_effectiveness=role_entry_cross_effectiveness,
        ),
        encoding="utf-8",
    )
    return {
        "paths": paths,
        "diagnostics": v1_2,
        "component_audit": component_audit,
        "score_bucket_effectiveness": score_bucket_effectiveness,
        "entry_window_effectiveness": entry_window_effectiveness,
        "role_effectiveness": role_effectiveness,
        "yearly_diagnosis": yearly_diagnosis,
        "low_bucket_audit": low_bucket_audit,
        "role_entry_cross_effectiveness": role_entry_cross_effectiveness,
    }


def compute_v1_3_scores(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = assign_entry_windows(compute_v1_2_scores(diagnostics))
    if frame.empty:
        frame["dragon_entry_score_v2"] = pd.Series(dtype="float64")
        return frame
    _ensure_numeric_columns(
        frame,
        [
            "industry_heat_score",
            "industry_focus_score_v2",
            "industry_rank",
            "stock_return_3d",
            "stock_return_5d",
            "stock_return_20d",
            "stock_excess_return_vs_industry_5d",
            "stock_excess_return_vs_industry_20d",
            "stock_relative_strength_score",
            "breakout_strength_score",
            "turnover_amount_score",
            "liquidity_score",
            "amount_vs_20d",
            "overheat_penalty",
            "follower_penalty",
            "dragon_status_score",
            "dragon_risk_score",
        ],
    )
    stage = frame["trend_lifecycle_stage"].fillna("unknown").astype(str)
    industry_context_score = (
        0.55 * _scale(frame[["industry_heat_score", "industry_focus_score_v2"]].max(axis=1), 0.35, 0.85)
        + 0.25 * (1.0 - _scale(frame["industry_rank"], 4.0, 12.0))
        + 0.20 * (1.0 - _scale(frame["dragon_status_score"], 0.80, 0.96))
    ).clip(0.0, 1.0)
    early_strength_improvement_score = (
        0.30 * _scale(frame["stock_return_3d"], -0.02, 0.06)
        + 0.30 * _scale(frame["stock_return_5d"], -0.03, 0.10)
        + 0.25 * _scale(frame["stock_excess_return_vs_industry_5d"], -0.03, 0.06)
        + 0.15 * (1.0 - _scale(frame["stock_return_20d"], 0.18, 0.55))
    ).clip(0.0, 1.0)
    moderate_breakout_score = (
        frame["breakout_strength_score"]
        * (1.0 - _scale(frame["dragon_risk_score"], 0.28, 0.60))
        * (1.0 - _scale(frame["stock_return_20d"], 0.30, 0.75))
    ).clip(0.0, 1.0)
    low_congestion_score = (
        0.30 * (1.0 - _scale(frame["dragon_status_score"], 0.62, 0.92))
        + 0.25 * (1.0 - _scale(frame["turnover_amount_score"], 0.70, 1.0))
        + 0.25 * _healthy_amount_expansion_score(frame["amount_vs_20d"])
        + 0.20 * (1.0 - frame["overheat_penalty"])
    ).clip(0.0, 1.0)
    risk_control_score = (
        0.60 * (1.0 - frame["dragon_risk_score"])
        + 0.25 * (1.0 - frame["overheat_penalty"])
        + 0.15 * (1.0 - _scale(frame["amount_vs_20d"], 2.0, 5.0))
    ).clip(0.0, 1.0)
    lifecycle_entry_score = stage.map(
        {
            "warming_up": 1.0,
            "early": 1.0,
            "breakout": 0.90,
            "early_mid": 0.80,
            "acceleration": 0.55,
            "mid": 0.45,
            "divergence": 0.10,
            "late_mid": 0.15,
            "late": 0.05,
            "cooling_down": 0.0,
            "unknown": 0.45,
        }
    ).fillna(0.45)
    liquidity_floor_score = _scale(frame["liquidity_score"], 0.20, 0.65)
    frame["dragon_entry_score_v2"] = (
        0.20 * industry_context_score
        + 0.20 * early_strength_improvement_score
        + 0.15 * moderate_breakout_score
        + 0.15 * low_congestion_score
        + 0.15 * risk_control_score
        + 0.10 * lifecycle_entry_score
        + 0.05 * liquidity_floor_score
        - 0.10 * frame["dragon_risk_score"]
        - 0.08 * frame["overheat_penalty"]
    ).clip(0.0, 1.0)
    return frame


def assign_entry_windows_v2(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = compute_v1_3_scores(diagnostics)
    if frame.empty:
        frame["entry_window_v2"] = pd.Series(dtype="object")
        return frame
    frame["entry_window_v2"] = [_entry_window_v2_for_row(row) for row in frame.to_dict("records")]
    return frame


def build_v1_3_low_quality_split_audit(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = assign_entry_windows_v2(diagnostics)
    if frame.empty:
        return pd.DataFrame(columns=LOW_QUALITY_SPLIT_AUDIT_COLUMNS)
    target = frame[
        frame["entry_window_v2"].isin(
            ["low_congestion_opportunity", "recovery_or_repair", "true_low_quality"]
        )
    ]
    result = _group_full_effectiveness(target, ["entry_window_v2"])
    return result.reindex(columns=LOW_QUALITY_SPLIT_AUDIT_COLUMNS)


def build_v1_3_follower_penalty_audit(
    diagnostics: pd.DataFrame,
    *,
    buckets: int = 10,
) -> pd.DataFrame:
    frame = assign_entry_windows_v2(diagnostics)
    if frame.empty:
        return pd.DataFrame(columns=FOLLOWER_PENALTY_AUDIT_COLUMNS)
    data = frame.copy()
    for column in [
        "follower_penalty",
        "industry_heat_score",
        "dragon_risk_score",
        "stock_relative_strength_score",
    ]:
        data[f"{column}_bucket"] = _quantile_bucket(data[column], buckets)
    dimensions = [
        "industry_heat_score_bucket",
        "dragon_risk_score_bucket",
        "stock_relative_strength_score_bucket",
        "trend_lifecycle_stage",
        "dragon_role",
        "entry_window_v2",
    ]
    rows = []
    for dimension in dimensions:
        grouped = _group_effectiveness(data, ["follower_penalty_bucket", dimension])
        for record in grouped.to_dict("records"):
            row = {column: "all" for column in FOLLOWER_PENALTY_AUDIT_COLUMNS}
            row["follower_penalty_bucket"] = record["follower_penalty_bucket"]
            row[dimension] = record[dimension]
            for column in EFFECTIVENESS_COLUMNS:
                row[column] = record[column]
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=FOLLOWER_PENALTY_AUDIT_COLUMNS)


def build_v1_3_entry_score_bucket_effectiveness(
    diagnostics: pd.DataFrame,
    *,
    buckets: int = 10,
) -> pd.DataFrame:
    frame = assign_entry_windows_v2(diagnostics)
    if frame.empty:
        return pd.DataFrame(columns=ENTRY_SCORE_BUCKET_COLUMNS)
    data = frame.copy()
    data["bucket"] = _quantile_bucket(data["dragon_entry_score_v2"], buckets)
    result = _group_effectiveness(data, ["bucket"])
    return result.reindex(columns=ENTRY_SCORE_BUCKET_COLUMNS)


def build_v1_3_entry_score_audit(diagnostics: pd.DataFrame, *, buckets: int = 10) -> pd.DataFrame:
    frame = assign_entry_windows_v2(diagnostics)
    rows = []
    for score_name in ["dragon_entry_score", "dragon_entry_score_v2"]:
        data = frame.copy()
        data["score_name"] = score_name
        data["bucket"] = _quantile_bucket(data[score_name], buckets)
        grouped = _group_effectiveness(data, ["score_name", "bucket"])
        rows.append(grouped)
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return result.reindex(columns=ENTRY_SCORE_AUDIT_COLUMNS)


def build_v1_3_entry_window_effectiveness(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = assign_entry_windows_v2(diagnostics)
    result = _group_full_effectiveness(frame, ["entry_window_v2"])
    return result.reindex(columns=ENTRY_WINDOW_V2_EFFECTIVENESS_COLUMNS)


def build_v1_3_role_entry_cross_effectiveness(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = assign_entry_windows_v2(diagnostics)
    result = _group_effectiveness(frame, ["dragon_role", "entry_window_v2"])
    return result.reindex(columns=ROLE_ENTRY_V2_CROSS_EFFECTIVENESS_COLUMNS)


def build_v1_3_yearly_diagnosis(diagnostics: pd.DataFrame, *, buckets: int = 10) -> pd.DataFrame:
    frame = assign_entry_windows_v2(diagnostics)
    if frame.empty:
        return pd.DataFrame(columns=YEARLY_V1_3_DIAGNOSIS_COLUMNS)
    data = frame.copy()
    data["year"] = pd.to_datetime(data["trade_date"]).dt.year.astype(str)
    data["bucket"] = _bucket_by_year(data, "dragon_entry_score_v2", buckets=buckets)
    rows = []
    for grouped, diagnosis_type in [
        (_group_effectiveness(data, ["year", "bucket"]), "entry_score_v2_bucket"),
        (_group_effectiveness(data, ["year", "entry_window_v2"]), "entry_window_v2"),
        (_group_effectiveness(data, ["year", "dragon_role", "entry_window_v2"]), "role_entry_window_v2"),
    ]:
        for record in grouped.to_dict("records"):
            row = {
                "year": record.get("year", "all"),
                "diagnosis_type": diagnosis_type,
                "bucket": record.get("bucket", "all"),
                "entry_window_v2": record.get("entry_window_v2", "all"),
                "dragon_role": record.get("dragon_role", "all"),
            }
            for column in EFFECTIVENESS_COLUMNS:
                row[column] = record.get(column, 0.0)
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=YEARLY_V1_3_DIAGNOSIS_COLUMNS)


def build_dragon_v1_3_outputs_from_diagnostics(
    diagnostics: pd.DataFrame,
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
) -> dict[str, Any]:
    v1_3 = assign_entry_windows_v2(compute_v1_3_scores(diagnostics))
    v1_3 = v1_3.reindex(columns=V1_3_DIAGNOSTIC_COLUMNS)
    low_quality_split_audit = build_v1_3_low_quality_split_audit(v1_3)
    entry_score_audit = build_v1_3_entry_score_audit(v1_3)
    entry_score_bucket_effectiveness = build_v1_3_entry_score_bucket_effectiveness(v1_3)
    entry_window_effectiveness = build_v1_3_entry_window_effectiveness(v1_3)
    role_effectiveness = summarize_role_effectiveness(v1_3)
    role_entry_cross_effectiveness = build_v1_3_role_entry_cross_effectiveness(v1_3)
    yearly_diagnosis = build_v1_3_yearly_diagnosis(v1_3)
    follower_penalty_audit = build_v1_3_follower_penalty_audit(v1_3)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {key: str(out / filename) for key, filename in V1_3_OUTPUT_FILENAMES.items()}
    v1_3.to_csv(paths["diagnostics"], index=False)
    low_quality_split_audit.to_csv(paths["low_quality_split_audit"], index=False)
    entry_score_audit.to_csv(paths["entry_score_audit"], index=False)
    entry_score_bucket_effectiveness.to_csv(paths["entry_score_bucket_effectiveness"], index=False)
    entry_window_effectiveness.to_csv(paths["entry_window_effectiveness"], index=False)
    role_effectiveness.to_csv(paths["role_effectiveness"], index=False)
    role_entry_cross_effectiveness.to_csv(paths["role_entry_cross_effectiveness"], index=False)
    yearly_diagnosis.to_csv(paths["yearly_diagnosis"], index=False)
    follower_penalty_audit.to_csv(paths["follower_penalty_audit"], index=False)
    Path(paths["markdown_report"]).write_text(
        _markdown_report_v1_3(
            start_date=_iso_date(start_date),
            end_date=_iso_date(end_date),
            low_quality_split_audit=low_quality_split_audit,
            entry_score_audit=entry_score_audit,
            entry_score_bucket_effectiveness=entry_score_bucket_effectiveness,
            entry_window_effectiveness=entry_window_effectiveness,
            role_effectiveness=role_effectiveness,
            role_entry_cross_effectiveness=role_entry_cross_effectiveness,
            yearly_diagnosis=yearly_diagnosis,
            follower_penalty_audit=follower_penalty_audit,
        ),
        encoding="utf-8",
    )
    return {
        "paths": paths,
        "diagnostics": v1_3,
        "low_quality_split_audit": low_quality_split_audit,
        "entry_score_audit": entry_score_audit,
        "entry_score_bucket_effectiveness": entry_score_bucket_effectiveness,
        "entry_window_effectiveness": entry_window_effectiveness,
        "role_effectiveness": role_effectiveness,
        "role_entry_cross_effectiveness": role_entry_cross_effectiveness,
        "yearly_diagnosis": yearly_diagnosis,
        "follower_penalty_audit": follower_penalty_audit,
    }


def summarize_monthly(diagnostics: pd.DataFrame) -> pd.DataFrame:
    if diagnostics.empty:
        return pd.DataFrame(columns=MONTHLY_SUMMARY_COLUMNS)
    frame = diagnostics.copy()
    frame["month"] = pd.to_datetime(frame["trade_date"]).dt.to_period("M").astype(str)
    rows = []
    for month, group in frame.groupby("month", sort=True):
        industry_counts = group["industry_name"].value_counts()
        rows.append(
            {
                "month": month,
                "sample_count": int(len(group)),
                "hot_industry_count": int(group["industry_name"].nunique()),
                "top_industry_sample_share": (
                    float(industry_counts.iloc[0] / len(group)) if len(group) else 0.0
                ),
                "dragon_leader_count": int((group["dragon_role"] == "dragon_leader").sum()),
                "overheated_leader_count": int(
                    (group["dragon_role"] == "overheated_leader").sum()
                ),
                "cooling_down_count": int((group["dragon_role"] == "cooling_down").sum()),
                "avg_dragon_score": pd.to_numeric(group["dragon_score"], errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(
                    group["future_5d_return"], errors="coerce"
                ).mean(),
                "avg_future_10d_return": pd.to_numeric(
                    group["future_10d_return"], errors="coerce"
                ).mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=MONTHLY_SUMMARY_COLUMNS)


def summarize_yearly(diagnostics: pd.DataFrame) -> pd.DataFrame:
    if diagnostics.empty:
        return pd.DataFrame(columns=YEARLY_DIAGNOSIS_COLUMNS)
    frame = diagnostics.copy()
    frame["year"] = pd.to_datetime(frame["trade_date"]).dt.year.astype(int)
    rows = []
    for (year, role), group in frame.groupby(["year", "dragon_role"], sort=True):
        year_frame = frame[frame["year"] == year]
        industry_counts = year_frame["industry_name"].value_counts()
        rows.append(
            {
                "year": int(year),
                "dragon_role": role,
                "sample_count": int(len(group)),
                "avg_future_5d_return": pd.to_numeric(
                    group["future_5d_return"], errors="coerce"
                ).mean(),
                "avg_future_10d_return": pd.to_numeric(
                    group["future_10d_return"], errors="coerce"
                ).mean(),
                "avg_future_20d_return": pd.to_numeric(
                    group["future_20d_return"], errors="coerce"
                ).mean(),
                "win_rate_5d": (pd.to_numeric(group["future_5d_return"], errors="coerce") > 0).mean(),
                "win_rate_10d": (
                    pd.to_numeric(group["future_10d_return"], errors="coerce") > 0
                ).mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(
                    group["future_10d_max_drawdown"], errors="coerce"
                ).mean(),
                "avg_future_20d_max_drawdown": pd.to_numeric(
                    group["future_20d_max_drawdown"], errors="coerce"
                ).mean(),
                "hot_industry_count": int(year_frame["industry_name"].nunique()),
                "industry_mainline_concentration": (
                    float(industry_counts.iloc[0] / len(year_frame)) if len(year_frame) else 0.0
                ),
            }
        )
    return pd.DataFrame(rows).reindex(columns=YEARLY_DIAGNOSIS_COLUMNS)


def write_dragon_outputs(
    *,
    diagnostics: pd.DataFrame,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    role_effectiveness = summarize_role_effectiveness(diagnostics)
    monthly_summary = summarize_monthly(diagnostics)
    yearly_diagnosis = summarize_yearly(diagnostics)
    paths = {key: str(out / filename) for key, filename in OUTPUT_FILENAMES.items()}
    diagnostics.reindex(columns=DRAGON_DIAGNOSTIC_COLUMNS).to_csv(
        paths["diagnostics"],
        index=False,
    )
    monthly_summary.to_csv(paths["monthly_summary"], index=False)
    role_effectiveness.to_csv(paths["role_effectiveness"], index=False)
    yearly_diagnosis.to_csv(paths["yearly_diagnosis"], index=False)
    Path(paths["markdown_report"]).write_text(
        _markdown_report(
            start_date=_iso_date(start_date),
            end_date=_iso_date(end_date),
            diagnostics=diagnostics,
            role_effectiveness=role_effectiveness,
            yearly_diagnosis=yearly_diagnosis,
        )
    )
    return {
        "paths": paths,
        "diagnostics": diagnostics,
        "monthly_summary": monthly_summary,
        "role_effectiveness": role_effectiveness,
        "yearly_diagnosis": yearly_diagnosis,
    }


def run_dragon_research_v1(
    *,
    start_date: object,
    end_date: object,
    output_dir: str | Path = Path("/Users/xiwei/stock_research/outputs/research"),
    hot_industry_top_n: int = 6,
    adjust_type: str = "hfq",
    industry_system: str = "csrc",
    industry_level: int = 1,
    industry_diagnostics_path: str | Path | None = None,
    candidate_scores_path: str | Path | None = None,
    lifecycle_samples_path: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    bars = load_dragon_bars(
        start_date=start,
        end_date=end,
        adjust_type=adjust_type,
        service=service,
    )
    memberships = load_dragon_memberships(
        start_date=start,
        end_date=end,
        industry_system=industry_system,
        industry_level=industry_level,
        service=service,
    )
    industry = _load_optional_csv(
        industry_diagnostics_path
        or _default_industry_diagnostics_path(output_dir)
    )
    if industry.empty:
        industry = _fallback_industry_diagnostics(bars, memberships)
    stock_names = load_asset_names(service=service)
    lifecycle = _load_optional_csv(lifecycle_samples_path)
    candidates = _load_optional_csv(candidate_scores_path)
    diagnostics = build_dragon_diagnostics(
        bars=bars,
        memberships=memberships,
        industry_diagnostics=industry,
        stock_names=stock_names,
        lifecycle_samples=lifecycle,
        candidate_scores=candidates,
        start_date=start,
        end_date=end,
        hot_industry_top_n=hot_industry_top_n,
    )
    return write_dragon_outputs(
        diagnostics=diagnostics,
        output_dir=output_dir,
        start_date=start,
        end_date=end,
    )


def load_dragon_bars(
    *,
    start_date: object,
    end_date: object,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
        SELECT asset_id, trade_date, open, high, low, close, amount, turnover_rate,
               trade_status, is_st
        FROM market_daily_bar
        WHERE trade_date >= %s::date - interval '90 days'
          AND trade_date <= %s::date + interval '30 days'
          AND adjust_type = %s
        ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [str(start_date), str(end_date), adjust_type]))


def load_dragon_memberships(
    *,
    start_date: object,
    end_date: object,
    industry_system: str = "csrc",
    industry_level: int = 1,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
        SELECT asset_id, industry_name, start_date, end_date
        FROM core.industry_membership
        WHERE start_date <= %s::date
          AND (end_date IS NULL OR end_date >= %s::date)
          AND industry_system = %s
          AND level = %s
    """
    with connect(service) as conn:
        return pd.DataFrame(
            fetch_all(
                conn,
                sql,
                [str(end_date), str(start_date), industry_system, int(industry_level)],
            )
        )


def load_asset_names(*, service: str = SETTINGS.research_service) -> pd.DataFrame:
    sql = "SELECT asset_id, name AS stock_name FROM core.asset_master"
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, []))


def _role_for_row(row: dict[str, Any]) -> str:
    rank = int(row.get("dragon_rank_in_industry") or 999999)
    overheat = _float(row.get("overheat_penalty"))
    liquidity = _float(row.get("liquidity_score"))
    excess_5d = _float(row.get("stock_excess_return_vs_industry_5d"))
    excess_20d = _float(row.get("stock_excess_return_vs_industry_20d"))
    return_5d = _float(row.get("stock_return_5d"))
    return_20d = _float(row.get("stock_return_20d"))
    amount_rank = _float(row.get("amount_rank_pct_in_industry"))
    amount_vs_20d = _float(row.get("amount_vs_20d"))
    breakout = _float(row.get("breakout_strength_score"))
    follower = _float(row.get("follower_penalty"))
    return_rank = _float(row.get("return_rank_pct_in_industry"))
    relative_strength = _float(row.get("stock_relative_strength_score"))
    leadership = _float(row.get("industry_leadership_score"))
    dragon_score = _float(row.get("dragon_score"))
    stage = str(row.get("trend_lifecycle_stage") or "unknown")

    if rank <= 8 and (
        overheat >= 0.45
        or (return_5d >= 0.25 and amount_vs_20d >= 2.8)
        or (return_20d >= 0.55 and amount_vs_20d >= 2.2)
    ) and (return_5d >= 0.10 or return_20d >= 0.25 or breakout >= 0.65):
        return "overheated_leader"
    if liquidity < 0.20:
        return "weak_candidate"
    if stage == "cooling_down" or (excess_5d < -0.04 and return_5d < 0.0):
        return "cooling_down"
    if (
        rank <= 3
        and return_rank >= 0.85
        and (excess_5d >= 0.03 or excess_20d >= 0.08)
        and leadership >= 0.70
        and liquidity >= 0.50
        and overheat < 0.42
        and return_5d < 0.25
        and amount_vs_20d < 3.0
        and stage not in {"cooling_down", "divergence", "late", "late_mid"}
    ):
        return "dragon_leader"
    if amount_rank >= 0.80 and excess_20d >= 0.0 and liquidity >= 0.60 and overheat < 0.45:
        return "core_middle"
    if (
        rank <= 12
        and return_rank >= 0.55
        and dragon_score >= 0.02
        and relative_strength >= 0.35
        and breakout >= 0.35
        and liquidity >= 0.30
        and overheat < 0.35
        and follower < 0.55
        and return_5d > 0.0
        and (excess_5d > -0.01 or excess_20d > -0.06)
        and stage not in {"cooling_down", "divergence", "late", "late_mid"}
    ):
        return "early_potential"
    if return_5d > 0.03 and excess_5d > 0.0 and excess_20d < 0.0 and follower < 0.65:
        return "laggard_catchup"
    if return_5d <= 0.0:
        return "weak_candidate"
    if follower >= 0.35:
        return "follower"
    return "weak_candidate"


def _build_stock_features(bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.sort_values(["asset_id", "trade_date"]).copy()
    grouped = frame.groupby("asset_id", group_keys=False)
    for days in (3, 5, 10, 20):
        frame[f"stock_return_{days}d"] = grouped["close"].pct_change(days)
    rolling_high_20 = grouped["close"].transform(lambda s: s.rolling(20, min_periods=1).max())
    rolling_high_60 = grouped["close"].transform(lambda s: s.rolling(60, min_periods=1).max())
    amount_20d = grouped["amount"].transform(lambda s: s.rolling(20, min_periods=1).mean())
    frame["new_high_20d"] = frame["close"] >= rolling_high_20
    frame["new_high_60d"] = frame["close"] >= rolling_high_60
    frame["amount_vs_20d"] = frame["amount"] / amount_20d.replace(0, pd.NA)
    return frame


def _add_industry_relative_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for days in (5, 20):
        result[f"industry_return_{days}d"] = result.groupby(
            ["trade_date", "industry_name"]
        )[f"stock_return_{days}d"].transform("mean")
        result[f"market_return_{days}d"] = result.groupby("trade_date")[
            f"stock_return_{days}d"
        ].transform("mean")
        result[f"stock_excess_return_vs_industry_{days}d"] = (
            result[f"stock_return_{days}d"] - result[f"industry_return_{days}d"]
        )
    result["return_rank_pct_in_industry"] = result.groupby(
        ["trade_date", "industry_name"]
    )["stock_return_20d"].rank(pct=True)
    result["amount_rank_pct_in_industry"] = result.groupby(
        ["trade_date", "industry_name"]
    )["amount"].rank(pct=True)
    result["daily_return"] = result.groupby("asset_id")["close"].pct_change()
    result["industry_daily_return"] = result.groupby(["trade_date", "industry_name"])[
        "daily_return"
    ].transform("mean")
    result["outperform_day"] = result["daily_return"] > result["industry_daily_return"]
    result["outperform_industry_days_5"] = result.groupby("asset_id")[
        "outperform_day"
    ].transform(lambda s: s.rolling(5, min_periods=1).sum())
    return result


def _append_future_diagnostics(scored: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    if scored.empty:
        return scored.copy()
    price_by_asset = {}
    for asset_id, group in bars[["asset_id", "trade_date", "close"]].groupby("asset_id", sort=False):
        ordered = group.sort_values("trade_date").reset_index(drop=True)
        price_by_asset[str(asset_id)] = {
            "dates": dict(zip(ordered["trade_date"].astype(str), range(len(ordered)), strict=False)),
            "close": pd.to_numeric(ordered["close"], errors="coerce").to_numpy(),
        }

    rows = []
    for row in scored[["asset_id", "trade_date"]].to_dict("records"):
        asset_id = str(row["asset_id"])
        trade_date = str(row["trade_date"])
        asset_prices = price_by_asset.get(asset_id)
        values = {
            "asset_id": asset_id,
            "trade_date": trade_date,
            "future_1d_return": pd.NA,
            "future_3d_return": pd.NA,
            "future_5d_return": pd.NA,
            "future_10d_return": pd.NA,
            "future_20d_return": pd.NA,
            "future_10d_max_drawdown": pd.NA,
            "future_20d_max_drawdown": pd.NA,
        }
        if asset_prices is not None:
            index = asset_prices["dates"].get(trade_date)
            closes = asset_prices["close"]
            if index is not None and index < len(closes):
                current = closes[index]
                if pd.notna(current) and current != 0:
                    for days in (1, 3, 5, 10, 20):
                        target = index + days
                        if target < len(closes) and pd.notna(closes[target]):
                            values[f"future_{days}d_return"] = float(closes[target] / current - 1.0)
                    for days in (10, 20):
                        future_window = closes[index + 1 : index + days + 1]
                        future_window = future_window[pd.notna(future_window)]
                        if len(future_window):
                            values[f"future_{days}d_max_drawdown"] = float(
                                future_window.min() / current - 1.0
                            )
        rows.append(values)
    future = pd.DataFrame(rows)
    return scored.merge(future, on=["trade_date", "asset_id"], how="left")


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()
    frame = bars.copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["trade_date"] = _date_series(frame["trade_date"])
    for column in ["open", "high", "low", "close", "amount", "turnover_rate"]:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "trade_status" not in frame.columns:
        frame["trade_status"] = "1"
    if "is_st" not in frame.columns:
        frame["is_st"] = False
    return frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def _normalize_industry_diagnostics(industry_diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = industry_diagnostics.copy()
    if frame.empty:
        return pd.DataFrame(
            columns=["trade_date", "industry_name", "industry_heat_score", "industry_focus_score_v2", "industry_rank"]
        )
    if "trade_date" not in frame.columns and "rebalance_date" in frame.columns:
        frame = frame.rename(columns={"rebalance_date": "trade_date"})
    frame["trade_date"] = _date_series(frame["trade_date"])
    frame["industry_name"] = frame["industry_name"].astype(str)
    score_source = None
    for candidate in ("industry_focus_score_v2", "mainline_score", "industry_focus_score"):
        if candidate in frame.columns:
            score_source = candidate
            break
    if score_source is None:
        frame["industry_focus_score_v2"] = 0.0
    else:
        frame["industry_focus_score_v2"] = pd.to_numeric(frame[score_source], errors="coerce").fillna(0.0)
    frame["industry_heat_score"] = frame["industry_focus_score_v2"]
    frame["industry_rank"] = frame.groupby("trade_date")["industry_heat_score"].rank(
        method="first",
        ascending=False,
    ).astype("Int64")
    return frame[["trade_date", "industry_name", "industry_heat_score", "industry_focus_score_v2", "industry_rank"]]


def _filter_hot_industries(frame: pd.DataFrame, *, hot_industry_top_n: int) -> pd.DataFrame:
    result = frame.copy()
    result["industry_rank"] = pd.to_numeric(result["industry_rank"], errors="coerce")
    return result[result["industry_rank"] <= int(hot_industry_top_n)].copy()


def _fallback_lifecycle_stage(frame: pd.DataFrame) -> pd.Series:
    ret_20 = pd.to_numeric(frame.get("stock_return_20d"), errors="coerce").fillna(0.0)
    ret_5 = pd.to_numeric(frame.get("stock_return_5d"), errors="coerce").fillna(0.0)
    over_amount = pd.to_numeric(frame.get("amount_vs_20d"), errors="coerce").fillna(1.0)
    stages = pd.Series("warming_up", index=frame.index, dtype="object")
    stages[(ret_20 > 0.18) & (ret_5 > 0.06)] = "breakout"
    stages[(ret_20 > 0.35) & (ret_5 > 0.15)] = "acceleration"
    stages[(ret_5 < -0.03) | ((ret_20 > 0.20) & (over_amount > 3.5))] = "cooling_down"
    return stages


def _fallback_industry_diagnostics(bars: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    price = _normalize_bars(bars)
    if price.empty or memberships.empty:
        return pd.DataFrame(columns=["trade_date", "industry_name", "industry_focus_score_v2"])
    dates = price[["asset_id", "trade_date"]].drop_duplicates()
    member_lookup = effective_membership_for_dates(dates, memberships)
    joined = price.merge(
        member_lookup[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    features = _build_stock_features(joined)
    grouped = (
        features.groupby(["trade_date", "industry_name"], as_index=False)
        .agg(industry_ret_20d=("stock_return_20d", "mean"), amount=("amount", "sum"))
    )
    grouped["amount_share"] = grouped["amount"] / grouped.groupby("trade_date")["amount"].transform("sum")
    grouped["industry_focus_score_v2"] = grouped.groupby("trade_date")["industry_ret_20d"].rank(pct=True).fillna(0.0)
    grouped["mainline_score"] = grouped["industry_focus_score_v2"]
    return grouped[["trade_date", "industry_name", "industry_focus_score_v2", "mainline_score"]]


def _load_optional_csv(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path)


def _default_industry_diagnostics_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "industry_focus_score_v2_diagnostics.csv"


def _markdown_report(
    *,
    start_date: str,
    end_date: str,
    diagnostics: pd.DataFrame,
    role_effectiveness: pd.DataFrame,
    yearly_diagnosis: pd.DataFrame,
) -> str:
    best_role = _best_role(role_effectiveness)
    worst_drawdown_role = _worst_drawdown_role(role_effectiveness)
    return "\n".join(
        [
            "# Dragon Strategy Research v1 诊断报告",
            "",
            "## 1. 研究目标",
            f"区间：{start_date} 至 {end_date}。本轮只做热门板块 + 龙头识别诊断，不接龙虎榜，不做实盘交易策略。",
            "",
            "## 2. 方法说明",
            "本模块复用行业热度、industry_focus_v2、日线行情、行业归属和可选 trend_lifecycle 样本。dragon_score 只使用历史可见的相对强度、突破、成交额换手、行业领导力、生命周期、流动性、过热惩罚和跟风惩罚；future return 只用于诊断。",
            "",
            "## 3. 龙头标签定义",
            "`dragon_leader` 表示热门行业内排名靠前、相对行业占优且未过热的股票；`core_middle` 表示成交额或流动性靠前、走势更稳的中军；`laggard_catchup` 表示短期补涨但 20 日相对强度不足；`follower` 表示跟随行业上涨但缺乏领先性；`overheated_leader` 表示强势但短期涨幅和量能过热；`cooling_down` 表示个股或生命周期转弱；`weak_candidate` 表示强度或流动性不足。",
            "",
            "## 4. 角色有效性检验",
            _table_preview(role_effectiveness, ROLE_EFFECTIVENESS_COLUMNS),
            "",
            "## 5. 年度差异",
            _table_preview(yearly_diagnosis, YEARLY_DIAGNOSIS_COLUMNS),
            "",
            "## 6. 当前结论",
            f"未来收益表现最好的角色：{best_role}。未来回撤最大的角色：{worst_drawdown_role}。这些结论是诊断输出，不构成交易规则。",
            "",
            "## 7. 下一步计划",
            "v1.1/v2 再接入龙虎榜作为资金确认模块，字段包括：龙虎榜上榜事件、上榜原因、净买入、买入额、卖出额、机构席位、游资席位、Top1/Top5 集中度、连续上榜、上榜后次日承接和一日游风险。",
            "",
            f"诊断样本数：{len(diagnostics)}。",
        ]
    )


def _markdown_report_v1_1(
    *,
    start_date: str,
    end_date: str,
    v1_role_effectiveness: pd.DataFrame,
    role_effectiveness: pd.DataFrame,
    v1_vs_v1_1: pd.DataFrame,
    weak_candidate_audit: pd.DataFrame,
    score_bucket_effectiveness: pd.DataFrame,
    lifecycle_role_effectiveness: pd.DataFrame,
    overheat_audit: pd.DataFrame,
) -> str:
    monotonic_note = _score_bucket_monotonic_note(score_bucket_effectiveness)
    readiness_note = _v1_1_lhb_readiness_note(role_effectiveness)
    early_row = role_effectiveness[role_effectiveness["role"] == "early_potential"]
    early_note = "样本不足"
    if not early_row.empty:
        row = early_row.iloc[0]
        early_note = (
            f"early_potential 样本 {int(row['sample_count'])}，"
            f"10日均值 {_format_pct(row['avg_future_10d_return'])}，"
            f"10日胜率 {_format_pct(row['win_rate_10d'])}。"
        )
    return "\n".join(
        [
            "# Dragon Strategy Research v1.1 角色校准报告",
            "",
            "## 1. 本轮目标",
            f"区间：{start_date} 至 {end_date}。本轮不接龙虎榜，重点修正 v1 标签区分度、拆分 weak_candidate、校准 dragon_leader 与 overheated_leader。",
            "",
            "## 2. v1 主要问题",
            "- weak_candidate 在 v1 中混入了部分早期转强样本，未来收益反而较好。",
            "- dragon_leader 均值为正但中位数偏弱，说明高位确认和噪音样本混入。",
            "- overheated_leader 样本过少，但回撤特征明显。",
            "- 2024、2025、2026 的角色有效性差异明显。",
            "",
            "## 3. weak_candidate 归因",
            "v1.1 将热门行业中相对强度开始改善、突破有苗头、不过热且流动性合格的样本拆为 early_potential。",
            _table_preview(weak_candidate_audit, WEAK_CANDIDATE_AUDIT_COLUMNS, rows=8),
            "",
            "## 4. 标签规则调整",
            "- 新增 `early_potential`：行业热门、排名不必前三，但 dragon_score、相对强度、突破、流动性达到早期启动条件，且不处于 cooling_down/divergence。",
            "- 收紧 `dragon_leader`：要求更强行业领先性、低过热、非降温/分歧阶段，并避免极端短期涨幅和爆量。",
            "- 放宽 `overheated_leader`：允许 rank 前 8 且短期涨幅、amount_vs_20d、overheat_penalty 达到高风险条件的样本进入过热标签。",
            "",
            "## 5. v1 vs v1.1 对比",
            _table_preview(v1_vs_v1_1, list(v1_vs_v1_1.columns), rows=16),
            "",
            "## 6. dragon_score 分桶有效性",
            monotonic_note,
            _table_preview(score_bucket_effectiveness, SCORE_BUCKET_EFFECTIVENESS_COLUMNS, rows=16),
            "",
            "## 7. lifecycle × role 交叉结论",
            early_note,
            _table_preview(lifecycle_role_effectiveness, LIFECYCLE_ROLE_EFFECTIVENESS_COLUMNS, rows=20),
            "",
            "## 8. 是否具备接入龙虎榜条件",
            "若 v1.1 中 dragon_leader 和 early_potential 稳定优于 follower/weak_candidate，overheated_leader 回撤更大，cooling_down 明显弱，才建议进入龙虎榜 v1.2；否则应继续修正 dragon_score 和标签。",
            readiness_note,
            "",
            "### Overheat Audit",
            _table_preview(overheat_audit, OVERHEAT_AUDIT_COLUMNS, rows=4),
            "",
            "### v1 role baseline",
            _table_preview(v1_role_effectiveness, ROLE_EFFECTIVENESS_COLUMNS, rows=10),
        ]
    )


def _markdown_report_v1_2(
    *,
    start_date: str,
    end_date: str,
    component_audit: pd.DataFrame,
    score_bucket_effectiveness: pd.DataFrame,
    entry_window_effectiveness: pd.DataFrame,
    role_effectiveness: pd.DataFrame,
    yearly_diagnosis: pd.DataFrame,
    low_bucket_audit: pd.DataFrame,
    role_entry_cross_effectiveness: pd.DataFrame,
) -> str:
    low_bucket_note = _low_bucket_note(low_bucket_audit)
    component_note = _component_signal_note(component_audit)
    entry_note = _entry_window_note(entry_window_effectiveness)
    role_entry_note = _role_entry_note(role_entry_cross_effectiveness)
    yearly_note = _yearly_v1_2_note(yearly_diagnosis)
    readiness_note = _v1_2_lhb_readiness_note(score_bucket_effectiveness, entry_window_effectiveness)
    return "\n".join(
        [
            "# Dragon Strategy Research v1.2 分数重构报告",
            "",
            "## 1. 本轮目标",
            f"区间：{start_date} 至 {end_date}。本轮不接龙虎榜，不做交易回测，优先解决 v1.1 dragon_score 不单调问题。",
            "",
            "## 2. v1.1 问题回顾",
            "- weak_candidate 拆分后仍然表现较好。",
            "- dragon_leader 平均收益为正，但中位数仍为负。",
            "- highest score bucket 未优于 lowest bucket，且高分桶回撤更深。",
            "- overheated_leader 风险识别有效，应从买点价值中拆出。",
            "",
            "## 3. 分数重构",
            "- `dragon_status_score`：识别是否已经是强势股或龙头候选，主要由相对强度、突破、成交、行业领导力、生命周期和流动性组成。",
            "- `dragon_entry_score`：识别是否处于早期/中期可介入窗口，偏好行业有效、相对转强、温和放量、不过热、status 中等偏高的样本。",
            "- `dragon_risk_score`：识别过热、拥挤、末端和降温风险，覆盖极端涨幅、爆量、换手、生命周期后段和拥挤状态。",
            "",
            "## 4. 低分桶表现好的原因",
            low_bucket_note,
            _table_preview(low_bucket_audit, LOW_BUCKET_AUDIT_COLUMNS, rows=12),
            "",
            "## 5. 组件有效性",
            component_note,
            _table_preview(component_audit, COMPONENT_AUDIT_COLUMNS, rows=36),
            "",
            "## 6. entry_window 有效性",
            entry_note,
            _table_preview(entry_window_effectiveness, ENTRY_WINDOW_EFFECTIVENESS_COLUMNS, rows=10),
            "",
            "## 7. role × entry_window 交叉结论",
            role_entry_note,
            _table_preview(role_entry_cross_effectiveness, ROLE_ENTRY_CROSS_EFFECTIVENESS_COLUMNS, rows=20),
            "",
            "## 8. 年度差异",
            yearly_note,
            _table_preview(yearly_diagnosis, YEARLY_V1_2_DIAGNOSIS_COLUMNS, rows=30),
            "",
            "## 9. 是否具备接入龙虎榜条件",
            readiness_note,
            "",
            "### v1.2 role effectiveness",
            _table_preview(role_effectiveness, ROLE_EFFECTIVENESS_COLUMNS, rows=10),
            "",
            "### v1.2 score buckets",
            _table_preview(score_bucket_effectiveness, SCORE_BUCKET_V1_2_COLUMNS, rows=36),
        ]
    )


def _markdown_report_v1_3(
    *,
    start_date: str,
    end_date: str,
    low_quality_split_audit: pd.DataFrame,
    entry_score_audit: pd.DataFrame,
    entry_score_bucket_effectiveness: pd.DataFrame,
    entry_window_effectiveness: pd.DataFrame,
    role_effectiveness: pd.DataFrame,
    role_entry_cross_effectiveness: pd.DataFrame,
    yearly_diagnosis: pd.DataFrame,
    follower_penalty_audit: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# Dragon Strategy Research v1.3 低拥挤机会与买点重构报告",
            "",
            "## 1. 本轮目标",
            f"区间：{start_date} 至 {end_date}。本轮不接龙虎榜，重点解决 low_quality_ignore 过宽和 dragon_entry_score 不单调问题。",
            "",
            "## 2. v1.2 问题回顾",
            "- status_score 是拥挤确认，不是买点价值。",
            "- risk_score 有效，可继续作为规避/降权指标。",
            "- entry_score 失败，高分桶未优于低分桶。",
            "- low_quality_ignore 表现最好，说明标签过宽。",
            "- follower_penalty 语义冲突，可能捕捉低拥挤扩散机会。",
            "",
            "## 3. low_quality_ignore 拆分",
            _low_quality_split_note(low_quality_split_audit),
            _table_preview(low_quality_split_audit, LOW_QUALITY_SPLIT_AUDIT_COLUMNS, rows=8),
            "",
            "## 4. entry_score_v2 设计",
            "`dragon_entry_score_v2` 由行业环境、早期强度改善、温和突破、低拥挤、风险控制、生命周期入口和流动性底线构成，刻意避免奖励最高拥挤强势确认。",
            "",
            "## 5. follower_penalty 重新解释",
            _follower_penalty_note(follower_penalty_audit),
            _table_preview(follower_penalty_audit, FOLLOWER_PENALTY_AUDIT_COLUMNS, rows=16),
            "",
            "## 6. entry_score_v2 分桶效果",
            _entry_score_v2_note(entry_score_bucket_effectiveness, entry_score_audit),
            _table_preview(entry_score_bucket_effectiveness, ENTRY_SCORE_BUCKET_COLUMNS, rows=12),
            "",
            "## 7. entry_window_v2 有效性",
            _entry_window_v2_note(entry_window_effectiveness),
            _table_preview(entry_window_effectiveness, ENTRY_WINDOW_V2_EFFECTIVENESS_COLUMNS, rows=12),
            "",
            "## 8. role × entry_window_v2 交叉结论",
            _role_entry_v2_note(role_entry_cross_effectiveness),
            _table_preview(role_entry_cross_effectiveness, ROLE_ENTRY_V2_CROSS_EFFECTIVENESS_COLUMNS, rows=24),
            "",
            "## 9. 年度差异",
            _yearly_v1_3_note(yearly_diagnosis),
            _table_preview(yearly_diagnosis, YEARLY_V1_3_DIAGNOSIS_COLUMNS, rows=36),
            "",
            "## 10. 是否具备接入龙虎榜条件",
            _v1_3_lhb_readiness_note(low_quality_split_audit, entry_score_bucket_effectiveness, entry_window_effectiveness),
            "",
            "### v1.3 role effectiveness",
            _table_preview(role_effectiveness, ROLE_EFFECTIVENESS_COLUMNS, rows=10),
            "",
            "### entry score audit",
            _table_preview(entry_score_audit, ENTRY_SCORE_AUDIT_COLUMNS, rows=24),
        ]
    )


def _normalize_diagnostics_frame(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = diagnostics.copy()
    if frame.empty:
        return frame
    if "trade_date" in frame.columns:
        frame["trade_date"] = _date_series(frame["trade_date"])
    if "dragon_role" not in frame.columns:
        frame["dragon_role"] = "weak_candidate"
    if "entry_window" not in frame.columns:
        frame["entry_window"] = "low_quality_ignore"
    if "entry_window_v2" not in frame.columns:
        frame["entry_window_v2"] = "true_low_quality"
    if "trend_lifecycle_stage" not in frame.columns:
        frame["trend_lifecycle_stage"] = "unknown"
    for column in [
        "industry_rank",
        "industry_heat_score",
        "industry_focus_score_v2",
        "dragon_score",
        "stock_relative_strength_score",
        "breakout_strength_score",
        "turnover_amount_score",
        "industry_leadership_score",
        "lifecycle_score",
        "overheat_penalty",
        "follower_penalty",
        "stock_return_3d",
        "stock_return_5d",
        "stock_return_10d",
        "stock_return_20d",
        "stock_excess_return_vs_industry_5d",
        "stock_excess_return_vs_industry_20d",
        "amount",
        "turnover_rate",
        "amount_vs_20d",
        "liquidity_score",
        "dragon_status_score",
        "dragon_entry_score",
        "dragon_risk_score",
        "dragon_entry_score_v2",
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_20d_return",
        "future_10d_max_drawdown",
        "future_20d_max_drawdown",
    ]:
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    if "return_rank_pct_in_industry" not in frame.columns:
        frame["return_rank_pct_in_industry"] = frame.groupby(
            ["trade_date", "industry_name"]
        )["stock_return_20d"].rank(pct=True)
    if "amount_rank_pct_in_industry" not in frame.columns:
        frame["amount_rank_pct_in_industry"] = frame.groupby(
            ["trade_date", "industry_name"]
        )["amount"].rank(pct=True)
    for column in ["return_rank_pct_in_industry", "amount_rank_pct_in_industry"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return frame


def _effectiveness_stats(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series({column: 0 for column in EFFECTIVENESS_COLUMNS})
    data = frame.copy()
    for column in [
        "future_5d_return",
        "future_10d_return",
        "future_20d_return",
        "future_10d_max_drawdown",
        "future_20d_max_drawdown",
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return pd.Series(
        {
            "sample_count": int(len(data)),
            "avg_future_5d_return": data["future_5d_return"].mean(),
            "avg_future_10d_return": data["future_10d_return"].mean(),
            "avg_future_20d_return": data["future_20d_return"].mean(),
            "median_future_5d_return": data["future_5d_return"].median(),
            "median_future_10d_return": data["future_10d_return"].median(),
            "median_future_20d_return": data["future_20d_return"].median(),
            "win_rate_5d": (data["future_5d_return"] > 0).mean(),
            "win_rate_10d": (data["future_10d_return"] > 0).mean(),
            "win_rate_20d": (data["future_20d_return"] > 0).mean(),
            "avg_future_10d_max_drawdown": data["future_10d_max_drawdown"].mean(),
            "avg_future_20d_max_drawdown": data["future_20d_max_drawdown"].mean(),
        }
    )


def _full_effectiveness_stats(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series({column: 0 for column in FULL_EFFECTIVENESS_COLUMNS})
    data = frame.copy()
    for column in [
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_20d_return",
        "future_10d_max_drawdown",
        "future_20d_max_drawdown",
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return pd.Series(
        {
            "sample_count": int(len(data)),
            "avg_future_1d_return": data["future_1d_return"].mean(),
            "avg_future_3d_return": data["future_3d_return"].mean(),
            "avg_future_5d_return": data["future_5d_return"].mean(),
            "avg_future_10d_return": data["future_10d_return"].mean(),
            "avg_future_20d_return": data["future_20d_return"].mean(),
            "median_future_5d_return": data["future_5d_return"].median(),
            "median_future_10d_return": data["future_10d_return"].median(),
            "median_future_20d_return": data["future_20d_return"].median(),
            "win_rate_5d": (data["future_5d_return"] > 0).mean(),
            "win_rate_10d": (data["future_10d_return"] > 0).mean(),
            "win_rate_20d": (data["future_20d_return"] > 0).mean(),
            "avg_future_10d_max_drawdown": data["future_10d_max_drawdown"].mean(),
            "avg_future_20d_max_drawdown": data["future_20d_max_drawdown"].mean(),
        }
    )


def _group_effectiveness(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*group_cols, *EFFECTIVENESS_COLUMNS])
    data = frame.copy()
    for column in [
        "future_5d_return",
        "future_10d_return",
        "future_20d_return",
        "future_10d_max_drawdown",
        "future_20d_max_drawdown",
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["_win_5d"] = data["future_5d_return"] > 0
    data["_win_10d"] = data["future_10d_return"] > 0
    data["_win_20d"] = data["future_20d_return"] > 0
    grouped = data.groupby(group_cols, dropna=False)
    result = grouped.agg(
        sample_count=("future_5d_return", "size"),
        avg_future_5d_return=("future_5d_return", "mean"),
        avg_future_10d_return=("future_10d_return", "mean"),
        avg_future_20d_return=("future_20d_return", "mean"),
        median_future_5d_return=("future_5d_return", "median"),
        median_future_10d_return=("future_10d_return", "median"),
        median_future_20d_return=("future_20d_return", "median"),
        win_rate_5d=("_win_5d", "mean"),
        win_rate_10d=("_win_10d", "mean"),
        win_rate_20d=("_win_20d", "mean"),
        avg_future_10d_max_drawdown=("future_10d_max_drawdown", "mean"),
        avg_future_20d_max_drawdown=("future_20d_max_drawdown", "mean"),
    )
    return result.reset_index()


def _group_full_effectiveness(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*group_cols, *FULL_EFFECTIVENESS_COLUMNS])
    data = frame.copy()
    for column in [
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_20d_return",
        "future_10d_max_drawdown",
        "future_20d_max_drawdown",
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["_win_5d"] = data["future_5d_return"] > 0
    data["_win_10d"] = data["future_10d_return"] > 0
    data["_win_20d"] = data["future_20d_return"] > 0
    grouped = data.groupby(group_cols, dropna=False)
    result = grouped.agg(
        sample_count=("future_5d_return", "size"),
        avg_future_1d_return=("future_1d_return", "mean"),
        avg_future_3d_return=("future_3d_return", "mean"),
        avg_future_5d_return=("future_5d_return", "mean"),
        avg_future_10d_return=("future_10d_return", "mean"),
        avg_future_20d_return=("future_20d_return", "mean"),
        median_future_5d_return=("future_5d_return", "median"),
        median_future_10d_return=("future_10d_return", "median"),
        median_future_20d_return=("future_20d_return", "median"),
        win_rate_5d=("_win_5d", "mean"),
        win_rate_10d=("_win_10d", "mean"),
        win_rate_20d=("_win_20d", "mean"),
        avg_future_10d_max_drawdown=("future_10d_max_drawdown", "mean"),
        avg_future_20d_max_drawdown=("future_20d_max_drawdown", "mean"),
    )
    return result.reset_index()


def _entry_window_for_row(row: dict[str, Any]) -> str:
    role = str(row.get("dragon_role") or "")
    stage = str(row.get("trend_lifecycle_stage") or "unknown")
    status = _float(row.get("dragon_status_score"))
    entry = _float(row.get("dragon_entry_score"))
    risk = _float(row.get("dragon_risk_score"))
    overheat = _float(row.get("overheat_penalty"))
    amount_vs_20d = _float(row.get("amount_vs_20d"))
    return_5d = _float(row.get("stock_return_5d"))
    excess_5d = _float(row.get("stock_excess_return_vs_industry_5d"))
    relative_strength = _float(row.get("stock_relative_strength_score"))
    breakout = _float(row.get("breakout_strength_score"))
    liquidity = _float(row.get("liquidity_score"))
    follower = _float(row.get("follower_penalty"))

    if role == "overheated_leader" or risk >= 0.62 or overheat >= 0.45:
        return "overheat_avoid"
    if stage == "cooling_down":
        return "cooling_avoid"
    if liquidity < 0.20 or (status < 0.15 and entry < 0.30) or follower >= 0.85:
        return "low_quality_ignore"
    if excess_5d < -0.04 and return_5d < 0.0:
        return "cooling_avoid"
    if status >= 0.72 and risk >= 0.38 and entry < 0.48:
        return "crowded_late_entry"
    if (
        entry >= 0.58
        and 0.15 <= status <= 0.72
        and risk < 0.35
        and relative_strength >= 0.18
        and stage in {"warming_up", "early", "breakout", "early_mid", "unknown"}
    ):
        return "early_setup"
    if (
        breakout >= 0.55
        and relative_strength >= 0.35
        and 0.75 <= amount_vs_20d <= 2.40
        and risk < 0.45
        and entry >= 0.50
        and stage != "cooling_down"
    ):
        return "breakout_entry"
    if (
        status >= 0.52
        and (return_5d >= 0.06 or relative_strength >= 0.50)
        and risk < 0.55
        and entry >= 0.48
        and stage in {"warming_up", "breakout", "acceleration", "early_mid", "mid"}
    ):
        return "acceleration_entry"
    if status >= 0.70 and risk >= 0.30:
        return "crowded_late_entry"
    if entry >= 0.52 and risk < 0.35 and stage not in {"cooling_down", "divergence", "late", "late_mid"}:
        return "early_setup"
    return "low_quality_ignore"


def _entry_window_v2_for_row(row: dict[str, Any]) -> str:
    role = str(row.get("dragon_role") or "")
    stage = str(row.get("trend_lifecycle_stage") or "unknown")
    old_window = str(row.get("entry_window") or "")
    entry_v2 = _float(row.get("dragon_entry_score_v2"))
    status = _float(row.get("dragon_status_score"))
    risk = _float(row.get("dragon_risk_score"))
    overheat = _float(row.get("overheat_penalty"))
    liquidity = _float(row.get("liquidity_score"))
    amount_vs_20d = _float(row.get("amount_vs_20d"))
    return_3d = _float(row.get("stock_return_3d"))
    return_5d = _float(row.get("stock_return_5d"))
    return_20d = _float(row.get("stock_return_20d"))
    excess_5d = _float(row.get("stock_excess_return_vs_industry_5d"))
    excess_20d = _float(row.get("stock_excess_return_vs_industry_20d"))
    relative_strength = _float(row.get("stock_relative_strength_score"))
    breakout = _float(row.get("breakout_strength_score"))
    follower = _float(row.get("follower_penalty"))
    industry_context = max(
        _float(row.get("industry_heat_score")),
        _float(row.get("industry_focus_score_v2")),
    )
    has_short_improvement = return_3d > 0.0 or return_5d > 0.0 or excess_5d > -0.01

    if role == "overheated_leader" or old_window == "overheat_avoid" or risk >= 0.62 or overheat >= 0.45:
        return "overheat_avoid"
    if stage == "cooling_down" or old_window == "cooling_avoid":
        return "cooling_avoid"
    if status >= 0.72 and risk >= 0.38 and entry_v2 < 0.55:
        return "crowded_late_entry"
    if liquidity < 0.20 or (
        industry_context < 0.35
        and relative_strength < 0.18
        and breakout < 0.20
        and not has_short_improvement
    ):
        return "true_low_quality"
    if (
        industry_context >= 0.45
        and risk < 0.35
        and overheat < 0.18
        and 0.45 <= amount_vs_20d <= 2.20
        and relative_strength >= 0.08
        and has_short_improvement
        and return_20d >= 0.0
        and (follower >= 0.30 or status < 0.55)
        and stage not in {"divergence", "late", "late_mid"}
    ):
        return "low_congestion_opportunity"
    if (
        risk < 0.34
        and overheat < 0.18
        and return_20d <= 0.08
        and has_short_improvement
        and (excess_20d <= -0.04 or return_20d <= 0.02)
        and stage not in {"divergence", "late", "late_mid"}
    ):
        return "recovery_or_repair"
    if (
        entry_v2 >= 0.62
        and breakout >= 0.50
        and relative_strength >= 0.30
        and risk < 0.45
        and 0.65 <= amount_vs_20d <= 2.40
    ):
        return "breakout_entry"
    if (
        entry_v2 >= 0.58
        and return_5d >= 0.05
        and risk < 0.50
        and stage in {"warming_up", "breakout", "acceleration", "early_mid", "mid"}
    ):
        return "acceleration_entry"
    if entry_v2 >= 0.55 and risk < 0.38 and stage not in {"divergence", "late", "late_mid"}:
        return "early_setup"
    if liquidity < 0.30 or (relative_strength < 0.15 and breakout < 0.20 and return_5d <= 0.0):
        return "true_low_quality"
    return "early_setup" if entry_v2 >= 0.50 and risk < 0.45 else "true_low_quality"


def _classify_component_signal(grouped: pd.DataFrame) -> str:
    if grouped.empty or grouped["bucket"].nunique() < 2:
        return "weak_signal"
    ordered = grouped.sort_values("bucket")
    low = ordered.iloc[0]
    high = ordered.iloc[-1]
    low_return = _float(low["avg_future_10d_return"])
    high_return = _float(high["avg_future_10d_return"])
    low_drawdown = _float(low["avg_future_20d_max_drawdown"])
    high_drawdown = _float(high["avg_future_20d_max_drawdown"])
    return_gap = high_return - low_return
    drawdown_gap = high_drawdown - low_drawdown
    if high_drawdown <= low_drawdown - 0.015:
        return "risk_signal"
    if return_gap >= 0.002 and drawdown_gap >= -0.010:
        return "useful_signal"
    if return_gap <= -0.002:
        return "inverted_signal"
    return "weak_signal"


def _all_and_year_frames(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    rows: list[tuple[str, pd.DataFrame]] = [("all", frame.copy())]
    years = pd.to_datetime(frame["trade_date"]).dt.year.astype(str)
    for year, group in frame.assign(_year=years).groupby("_year", sort=True):
        rows.append((str(year), group.drop(columns=["_year"])))
    return rows


def _yearly_v1_2_row(record: dict[str, Any], diagnosis_type: str) -> dict[str, Any]:
    row = {
        "year": record.get("year", "all"),
        "diagnosis_type": diagnosis_type,
        "score_name": record.get("score_name", "all"),
        "score_bucket": record.get("score_bucket", "all"),
        "entry_window": record.get("entry_window", "all"),
        "dragon_role": record.get("dragon_role", "all"),
    }
    for column in EFFECTIVENESS_COLUMNS:
        row[column] = record.get(column, 0.0)
    return row


def _bucket_by_year(frame: pd.DataFrame, column: str, *, buckets: int) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="Int64")
    if "year" in frame.columns:
        groups = frame["year"].astype(str)
    else:
        groups = pd.Series("all", index=frame.index)
    pieces = []
    for _, index in groups.groupby(groups).groups.items():
        values = pd.to_numeric(frame.loc[index, column], errors="coerce").fillna(0.0)
        pieces.append(_quantile_bucket(values, buckets).reindex(index))
    return pd.concat(pieces).sort_index().astype("Int64")


def _quantile_bucket(values: pd.Series, buckets: int) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    unique_count = int(numeric.nunique())
    if unique_count <= 1:
        return pd.Series(1, index=values.index)
    q = max(1, min(int(buckets), unique_count))
    return pd.qcut(numeric, q=q, labels=False, duplicates="drop").astype(int) + 1


def _compare_role_effectiveness(v1: pd.DataFrame, v1_1: pd.DataFrame) -> pd.DataFrame:
    left = v1.rename(columns={column: f"v1_{column}" for column in ROLE_EFFECTIVENESS_COLUMNS if column != "role"})
    right = v1_1.rename(columns={column: f"v1_1_{column}" for column in ROLE_EFFECTIVENESS_COLUMNS if column != "role"})
    return left.merge(right, on="role", how="outer").fillna(0.0)


def _score_bucket_monotonic_note(score_bucket_effectiveness: pd.DataFrame) -> str:
    all_rows = score_bucket_effectiveness[score_bucket_effectiveness["year"] == "all"].copy()
    if all_rows.empty:
        return "dragon_score 分桶样本不足。"
    ordered = all_rows.sort_values("score_bucket")
    returns = pd.to_numeric(ordered["avg_future_10d_return"], errors="coerce").fillna(0.0)
    is_monotonic = bool(returns.is_monotonic_increasing)
    if is_monotonic:
        return "dragon_score 10日收益分桶呈单调改善。"
    first = _float(returns.iloc[0]) if len(returns) else 0.0
    last = _float(returns.iloc[-1]) if len(returns) else 0.0
    return (
        "dragon_score 10日收益分桶未呈现稳定单调性；"
        f"最低分桶均值 {_format_pct(first)}，最高分桶均值 {_format_pct(last)}。"
    )


def _v1_1_lhb_readiness_note(role_effectiveness: pd.DataFrame) -> str:
    def metric(role: str, column: str) -> float:
        row = role_effectiveness[role_effectiveness["role"] == role]
        if row.empty:
            return 0.0
        return _float(row.iloc[0].get(column))

    leader_10d = metric("dragon_leader", "avg_future_10d_return")
    early_10d = metric("early_potential", "avg_future_10d_return")
    follower_10d = metric("follower", "avg_future_10d_return")
    weak_10d = metric("weak_candidate", "avg_future_10d_return")
    overheated_dd = metric("overheated_leader", "avg_future_20d_max_drawdown")
    weak_dd = metric("weak_candidate", "avg_future_20d_max_drawdown")
    if leader_10d > follower_10d and early_10d > weak_10d and overheated_dd < weak_dd:
        return "结论：v1.1 标签具备初步区分度，可以进入龙虎榜资金确认 v1.2。"
    return (
        "结论：暂不建议直接接入龙虎榜。当前 dragon_leader / early_potential "
        "尚未稳定优于 follower / weak_candidate，下一步应继续重构 dragon_score "
        "与生命周期过滤，再把龙虎榜作为外部确认因子接入。"
    )


def _low_bucket_note(low_bucket_audit: pd.DataFrame) -> str:
    if low_bucket_audit.empty:
        return "低分桶样本不足。"
    role_rows = low_bucket_audit[low_bucket_audit["dragon_role"] != "all"].copy()
    if role_rows.empty:
        return "低分桶主要需要结合角色和行业维度继续拆分。"
    best = role_rows.sort_values("avg_future_10d_return", ascending=False).iloc[0]
    return (
        "低 dragon_score 分桶表现较好，主要应理解为低拥挤/低过热样本仍处于行业扩散或补涨阶段，"
        f"其中 `{best['dragon_role']}` 的 10日均值最高，约 {_format_pct(best['avg_future_10d_return'])}。"
    )


def _component_signal_note(component_audit: pd.DataFrame) -> str:
    if component_audit.empty:
        return "组件样本不足。"
    signals = (
        component_audit[["component_name", "signal_type"]]
        .drop_duplicates()
        .groupby("signal_type")["component_name"]
        .apply(lambda s: ", ".join(sorted(s.astype(str))))
        .to_dict()
    )
    parts = []
    for signal_type in ["useful_signal", "risk_signal", "inverted_signal", "weak_signal"]:
        names = signals.get(signal_type)
        if names:
            parts.append(f"{signal_type}: {names}")
    return "；".join(parts) if parts else "组件暂未呈现稳定规律。"


def _entry_window_note(entry_window_effectiveness: pd.DataFrame) -> str:
    if entry_window_effectiveness.empty:
        return "entry_window 样本不足。"
    ordered = entry_window_effectiveness.sort_values("avg_future_10d_return", ascending=False)
    best = ordered.iloc[0]
    worst_dd = entry_window_effectiveness.sort_values("avg_future_20d_max_drawdown").iloc[0]
    return (
        f"10日均值最高窗口为 `{best['entry_window']}`，约 {_format_pct(best['avg_future_10d_return'])}；"
        f"20日回撤最深窗口为 `{worst_dd['entry_window']}`，约 {_format_pct(worst_dd['avg_future_20d_max_drawdown'])}。"
    )


def _role_entry_note(role_entry_cross_effectiveness: pd.DataFrame) -> str:
    if role_entry_cross_effectiveness.empty:
        return "role × entry_window 样本不足。"
    filtered = role_entry_cross_effectiveness[
        pd.to_numeric(role_entry_cross_effectiveness["sample_count"], errors="coerce") >= 100
    ]
    if filtered.empty:
        filtered = role_entry_cross_effectiveness
    best = filtered.sort_values("avg_future_10d_return", ascending=False).iloc[0]
    worst_dd = filtered.sort_values("avg_future_20d_max_drawdown").iloc[0]
    return (
        f"大样本组合中 10日均值最高为 `{best['dragon_role']} + {best['entry_window']}`，"
        f"约 {_format_pct(best['avg_future_10d_return'])}；"
        f"回撤最深为 `{worst_dd['dragon_role']} + {worst_dd['entry_window']}`，"
        f"约 {_format_pct(worst_dd['avg_future_20d_max_drawdown'])}。"
    )


def _yearly_v1_2_note(yearly_diagnosis: pd.DataFrame) -> str:
    if yearly_diagnosis.empty:
        return "年度样本不足。"
    entry_rows = yearly_diagnosis[yearly_diagnosis["diagnosis_type"] == "entry_window"].copy()
    if entry_rows.empty:
        return "年度 entry_window 样本不足。"
    best_by_year = []
    for year, group in entry_rows.groupby("year", sort=True):
        best = group.sort_values("avg_future_10d_return", ascending=False).iloc[0]
        best_by_year.append(
            f"{year}: {best['entry_window']}({_format_pct(best['avg_future_10d_return'])})"
        )
    return "年度最佳 entry_window: " + "；".join(best_by_year)


def _v1_2_lhb_readiness_note(
    score_bucket_effectiveness: pd.DataFrame,
    entry_window_effectiveness: pd.DataFrame,
) -> str:
    entry_rows = score_bucket_effectiveness[
        (score_bucket_effectiveness["year"] == "all")
        & (score_bucket_effectiveness["score_name"] == "dragon_entry_score")
    ].sort_values("score_bucket")
    risk_rows = score_bucket_effectiveness[
        (score_bucket_effectiveness["year"] == "all")
        & (score_bucket_effectiveness["score_name"] == "dragon_risk_score")
    ].sort_values("score_bucket")
    entry_monotonic = False
    risk_drawdown = False
    if len(entry_rows) >= 2:
        entry_monotonic = (
            _float(entry_rows.iloc[-1]["avg_future_10d_return"])
            > _float(entry_rows.iloc[0]["avg_future_10d_return"]) + 0.002
        )
    if len(risk_rows) >= 2:
        risk_drawdown = (
            _float(risk_rows.iloc[-1]["avg_future_20d_max_drawdown"])
            < _float(risk_rows.iloc[0]["avg_future_20d_max_drawdown"]) - 0.010
        )
    window = entry_window_effectiveness.set_index("entry_window") if not entry_window_effectiveness.empty else pd.DataFrame()
    early_ok = False
    avoid_weak = False
    if not window.empty:
        early_best = max(
            _float(window.loc[name, "avg_future_10d_return"])
            for name in ["early_setup", "breakout_entry"]
            if name in window.index
        ) if any(name in window.index for name in ["early_setup", "breakout_entry"]) else 0.0
        crowded = _float(window.loc["crowded_late_entry", "avg_future_10d_return"]) if "crowded_late_entry" in window.index else 0.0
        overheat = _float(window.loc["overheat_avoid", "avg_future_10d_return"]) if "overheat_avoid" in window.index else 0.0
        cooling = _float(window.loc["cooling_avoid", "avg_future_10d_return"]) if "cooling_avoid" in window.index else 0.0
        early_ok = early_best > crowded + 0.002
        avoid_weak = min(overheat, cooling) < early_best - 0.002
    if entry_monotonic and risk_drawdown and early_ok and avoid_weak:
        return "结论：v1.2 具备进入龙虎榜 v1.3 的初步条件，但仍应只作为资金确认研究，不直接实盘。"
    return "结论：暂不建议接入龙虎榜。需要继续修正 entry_score 单调性与窗口过滤，再进入资金确认模块。"


def _low_quality_split_note(low_quality_split_audit: pd.DataFrame) -> str:
    if low_quality_split_audit.empty:
        return "low_quality 拆分样本不足。"
    indexed = low_quality_split_audit.set_index("entry_window_v2")
    parts = []
    for name in ["low_congestion_opportunity", "recovery_or_repair", "true_low_quality"]:
        if name in indexed.index:
            row = indexed.loc[name]
            parts.append(f"{name}: 样本 {int(row['sample_count'])}，10日均值 {_format_pct(row['avg_future_10d_return'])}")
    return "；".join(parts) if parts else "low_quality 拆分后暂无目标标签样本。"


def _follower_penalty_note(follower_penalty_audit: pd.DataFrame) -> str:
    if follower_penalty_audit.empty:
        return "follower_penalty 样本不足。"
    rows = follower_penalty_audit[follower_penalty_audit["entry_window_v2"] != "all"].copy()
    if rows.empty:
        return "follower_penalty 需要结合行业热度和风险分继续解释。"
    best = rows.sort_values("avg_future_10d_return", ascending=False).iloc[0]
    return (
        "follower_penalty 不能简单当负项；在行业热、风险低、短期改善时，它更像低拥挤扩散机会信号。"
        f"当前分组中 `{best['entry_window_v2']}` 的 10日均值最高，约 {_format_pct(best['avg_future_10d_return'])}。"
    )


def _entry_score_v2_note(entry_score_bucket_effectiveness: pd.DataFrame, entry_score_audit: pd.DataFrame) -> str:
    if entry_score_bucket_effectiveness.empty:
        return "entry_score_v2 分桶样本不足。"
    ordered = entry_score_bucket_effectiveness.sort_values("bucket")
    low = ordered.iloc[0]
    high = ordered.iloc[-1]
    old_note = ""
    if not entry_score_audit.empty:
        old = entry_score_audit[entry_score_audit["score_name"] == "dragon_entry_score"].sort_values("bucket")
        if len(old) >= 2:
            old_note = (
                f"旧 entry_score 低/高分桶10日均值分别为 "
                f"{_format_pct(old.iloc[0]['avg_future_10d_return'])}/"
                f"{_format_pct(old.iloc[-1]['avg_future_10d_return'])}。"
            )
    return (
        f"entry_score_v2 低/高分桶10日均值分别为 "
        f"{_format_pct(low['avg_future_10d_return'])}/{_format_pct(high['avg_future_10d_return'])}，"
        f"20日回撤分别为 {_format_pct(low['avg_future_20d_max_drawdown'])}/"
        f"{_format_pct(high['avg_future_20d_max_drawdown'])}。"
        + old_note
    )


def _entry_window_v2_note(entry_window_effectiveness: pd.DataFrame) -> str:
    if entry_window_effectiveness.empty:
        return "entry_window_v2 样本不足。"
    best = entry_window_effectiveness.sort_values("avg_future_10d_return", ascending=False).iloc[0]
    worst_dd = entry_window_effectiveness.sort_values("avg_future_20d_max_drawdown").iloc[0]
    return (
        f"10日均值最高窗口为 `{best['entry_window_v2']}`，约 {_format_pct(best['avg_future_10d_return'])}；"
        f"20日回撤最深窗口为 `{worst_dd['entry_window_v2']}`，约 {_format_pct(worst_dd['avg_future_20d_max_drawdown'])}。"
    )


def _role_entry_v2_note(role_entry_cross_effectiveness: pd.DataFrame) -> str:
    if role_entry_cross_effectiveness.empty:
        return "role × entry_window_v2 样本不足。"
    filtered = role_entry_cross_effectiveness[
        pd.to_numeric(role_entry_cross_effectiveness["sample_count"], errors="coerce") >= 100
    ]
    if filtered.empty:
        filtered = role_entry_cross_effectiveness
    best = filtered.sort_values("avg_future_10d_return", ascending=False).iloc[0]
    worst_dd = filtered.sort_values("avg_future_20d_max_drawdown").iloc[0]
    return (
        f"大样本组合中 10日均值最高为 `{best['dragon_role']} + {best['entry_window_v2']}`，"
        f"约 {_format_pct(best['avg_future_10d_return'])}；"
        f"回撤最深为 `{worst_dd['dragon_role']} + {worst_dd['entry_window_v2']}`，"
        f"约 {_format_pct(worst_dd['avg_future_20d_max_drawdown'])}。"
    )


def _yearly_v1_3_note(yearly_diagnosis: pd.DataFrame) -> str:
    if yearly_diagnosis.empty:
        return "年度样本不足。"
    rows = yearly_diagnosis[yearly_diagnosis["diagnosis_type"] == "entry_window_v2"].copy()
    if rows.empty:
        return "年度 entry_window_v2 样本不足。"
    parts = []
    for year, group in rows.groupby("year", sort=True):
        best = group.sort_values("avg_future_10d_return", ascending=False).iloc[0]
        parts.append(f"{year}: {best['entry_window_v2']}({_format_pct(best['avg_future_10d_return'])})")
    return "年度最佳 entry_window_v2: " + "；".join(parts)


def _v1_3_lhb_readiness_note(
    low_quality_split_audit: pd.DataFrame,
    entry_score_bucket_effectiveness: pd.DataFrame,
    entry_window_effectiveness: pd.DataFrame,
) -> str:
    low_split = low_quality_split_audit.set_index("entry_window_v2") if not low_quality_split_audit.empty else pd.DataFrame()
    low_congestion_ok = False
    if not low_split.empty and {"low_congestion_opportunity", "true_low_quality"}.issubset(set(low_split.index)):
        low_congestion_ok = (
            _float(low_split.loc["low_congestion_opportunity", "avg_future_10d_return"])
            > _float(low_split.loc["true_low_quality", "avg_future_10d_return"]) + 0.002
        )
    score_ok = False
    if not entry_score_bucket_effectiveness.empty:
        ordered = entry_score_bucket_effectiveness.sort_values("bucket")
        if len(ordered) >= 2:
            score_ok = (
                _float(ordered.iloc[-1]["avg_future_10d_return"])
                >= _float(ordered.iloc[0]["avg_future_10d_return"]) - 0.002
                and _float(ordered.iloc[-1]["avg_future_20d_max_drawdown"])
                >= _float(ordered.iloc[0]["avg_future_20d_max_drawdown"]) - 0.015
            )
    avoid_ok = False
    windows = entry_window_effectiveness.set_index("entry_window_v2") if not entry_window_effectiveness.empty else pd.DataFrame()
    if not windows.empty and "overheat_avoid" in windows.index:
        avoid_ok = _float(windows.loc["overheat_avoid", "avg_future_10d_return"]) < 0.0
    if low_congestion_ok and score_ok and avoid_ok:
        return "结论：v1.3 具备进入龙虎榜 v1.4 的初步条件，但龙虎榜仍只能作为资金确认诊断。"
    return "结论：暂不建议接入龙虎榜。应继续修正 entry_score_v2 或拆分低拥挤/修复窗口。"


def _format_pct(value: object) -> str:
    return f"{_float(value) * 100:.2f}%"


def _table_preview(frame: pd.DataFrame, columns: list[str], rows: int = 12) -> str:
    if frame.empty:
        return "无可用样本。"
    return frame.reindex(columns=columns).head(rows).to_markdown(index=False)


def _best_role(role_effectiveness: pd.DataFrame) -> str:
    if role_effectiveness.empty or "avg_future_10d_return" not in role_effectiveness.columns:
        return "样本不足"
    ordered = role_effectiveness.sort_values("avg_future_10d_return", ascending=False)
    return str(ordered.iloc[0]["role"])


def _worst_drawdown_role(role_effectiveness: pd.DataFrame) -> str:
    if role_effectiveness.empty or "avg_future_20d_max_drawdown" not in role_effectiveness.columns:
        return "样本不足"
    ordered = role_effectiveness.sort_values("avg_future_20d_max_drawdown", ascending=True)
    return str(ordered.iloc[0]["role"])


def _healthy_amount_expansion_score(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(1.0)
    rising = _scale(values, 0.6, 2.0)
    blowoff_discount = _scale(values, 2.5, 5.0) * 0.35
    return (rising - blowoff_discount).clip(0.0, 1.0)


def _scale(series: pd.Series | float, low: float, high: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(low)
    if high == low:
        return pd.Series(0.0, index=values.index)
    return ((values - low) / (high - low)).clip(0.0, 1.0)


def _ensure_numeric_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _ensure_bool_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column not in frame.columns:
            frame[column] = False
        frame[column] = frame[column].fillna(False).astype(bool)


def _score_columns() -> list[str]:
    return [
        *DRAGON_SCORE_WEIGHTS.keys(),
        "overheat_penalty",
        "follower_penalty",
        "dragon_score",
    ]


def _float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _iso_date(value: object) -> str:
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.strftime("%Y-%m-%d")
