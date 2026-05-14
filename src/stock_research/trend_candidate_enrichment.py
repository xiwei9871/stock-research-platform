from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import candidate_factor_names
from stock_research.trend_lifecycle import (
    DEFAULT_ENTRY_SUCCESS_RULES,
    ENTRY_SUCCESS_COLUMNS,
    load_trend_lifecycle_bars,
)


HORIZONS = (20, 40, 60)

SCORE_COLUMNS = [
    "trade_date",
    "asset_id",
    "candidate_score",
    "factor_count",
    "weight_sum",
]

ENRICHMENT_QUANTILE_COLUMNS = [
    "quantile",
    "rows",
    "avg_score",
    "entry_success_20d_rate",
    "entry_success_20d_lift",
    "entry_success_40d_rate",
    "entry_success_40d_lift",
    "entry_success_60d_rate",
    "entry_success_60d_lift",
]

ENRICHMENT_TOPN_COLUMNS = [
    "top_n",
    "rows",
    "avg_score",
    "entry_success_20d_rate",
    "entry_success_20d_lift",
    "entry_success_40d_rate",
    "entry_success_40d_lift",
    "entry_success_60d_rate",
    "entry_success_60d_lift",
]

ENRICHMENT_PERIOD_COLUMNS = [
    "period",
    "quantile",
    "rows",
    "avg_score",
    "entry_success_20d_rate",
    "entry_success_20d_lift",
    "entry_success_40d_rate",
    "entry_success_40d_lift",
    "entry_success_60d_rate",
    "entry_success_60d_lift",
]

ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS = [
    "period",
    "horizon",
    "factor_name",
    "factor_group",
    "success_n",
    "failure_n",
    "success_mean",
    "failure_mean",
    "success_median",
    "failure_median",
    "median_diff",
]

ENTRY_SUCCESS_FACTOR_RANK_COLUMNS = [
    "horizon",
    "factor_name",
    "factor_group",
    "direction",
    "periods",
    "mean_median_diff",
    "median_abs_diff",
    "sign_match_rate",
    "candidate_score",
    "success_median",
    "failure_median",
]

ENTRY_SUCCESS_CANDIDATE_V2_RANK_COLUMNS = [
    "horizon",
    "factor_name",
    "factor_group",
    "direction",
    "periods",
    "mean_median_diff",
    "median_abs_diff",
    "sign_match_rate",
    "candidate_score",
    "success_median",
    "failure_median",
]


def build_candidate_scores(
    factors: pd.DataFrame,
    candidate_rank: pd.DataFrame,
    *,
    max_factors: int | None = None,
    min_candidate_score: float = 0.0,
) -> pd.DataFrame:
    factor_frame = _normalize_factors(factors)
    candidates = _select_candidates(
        candidate_rank,
        max_factors=max_factors,
        min_candidate_score=min_candidate_score,
    )
    if factor_frame.empty or candidates.empty:
        return pd.DataFrame(columns=SCORE_COLUMNS)

    joined = factor_frame.merge(
        candidates[["factor_name", "direction", "candidate_weight"]],
        on="factor_name",
        how="inner",
    ).dropna(subset=["factor_value", "candidate_weight"])
    if joined.empty:
        return pd.DataFrame(columns=SCORE_COLUMNS)

    joined["rank_score"] = (
        joined.groupby(["trade_date", "factor_name"], group_keys=False)
        .apply(_directional_rank_score, include_groups=False)
        .reindex(joined.index)
    )
    joined["weighted_score"] = joined["rank_score"] * joined["candidate_weight"]
    grouped = (
        joined.groupby(["trade_date", "asset_id"], as_index=False)
        .agg(
            weighted_score_sum=("weighted_score", "sum"),
            weight_sum=("candidate_weight", "sum"),
            factor_count=("factor_name", "nunique"),
        )
    )
    grouped["candidate_score"] = grouped["weighted_score_sum"] / grouped["weight_sum"]
    return (
        grouped.reindex(columns=SCORE_COLUMNS)
        .sort_values(["trade_date", "candidate_score", "asset_id"], ascending=[True, False, True])
        .reset_index(drop=True)
    )


def build_entry_success_factor_profile(
    factors: pd.DataFrame,
    entry_success_labels: pd.DataFrame,
    *,
    horizon: int,
    period: str = "Q",
) -> pd.DataFrame:
    factor_frame = _normalize_factors(factors)
    label_frame = entry_success_labels.copy()
    if factor_frame.empty or label_frame.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS)

    success_col = f"entry_success_{int(horizon)}d"
    covered_col = f"{success_col}_covered"
    if success_col not in label_frame.columns or covered_col not in label_frame.columns:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS)
    label_frame["trade_date"] = label_frame["trade_date"].map(_iso_date)
    label_frame["asset_id"] = label_frame["asset_id"].astype(str)
    label_frame = label_frame[label_frame[covered_col].map(bool)].copy()
    if label_frame.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS)
    label_frame["success"] = label_frame[success_col].map(bool)

    joined = factor_frame.merge(
        label_frame[["trade_date", "asset_id", "success"]],
        on=["trade_date", "asset_id"],
        how="inner",
    ).dropna(subset=["factor_value"])
    if joined.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS)
    joined["period"] = pd.to_datetime(joined["trade_date"]).dt.to_period(period).astype(str)

    grouped = (
        joined.groupby(["period", "factor_name", "factor_group", "success"], as_index=False)["factor_value"]
        .agg(n="count", mean="mean", median="median")
    )
    success = grouped[grouped["success"]].rename(
        columns={"n": "success_n", "mean": "success_mean", "median": "success_median"}
    )
    failure = grouped[~grouped["success"]].rename(
        columns={"n": "failure_n", "mean": "failure_mean", "median": "failure_median"}
    )
    result = success.merge(
        failure,
        on=["period", "factor_name", "factor_group"],
        how="inner",
    )
    if result.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS)
    result["horizon"] = int(horizon)
    result["median_diff"] = result["success_median"] - result["failure_median"]
    result["success_n"] = result["success_n"].astype(int)
    result["failure_n"] = result["failure_n"].astype(int)
    return result.reindex(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS).sort_values(
        ["factor_name", "period"]
    ).reset_index(drop=True)


def rank_entry_success_factors(profile: pd.DataFrame) -> pd.DataFrame:
    if profile.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_RANK_COLUMNS)
    frame = profile.copy()
    frame["median_diff"] = pd.to_numeric(frame["median_diff"], errors="coerce")
    frame = frame.dropna(subset=["median_diff"])
    if frame.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_RANK_COLUMNS)

    rows = []
    for keys, group in frame.groupby(["horizon", "factor_name", "factor_group"], sort=False):
        horizon, factor_name, factor_group = keys
        diffs = group["median_diff"].astype(float)
        mean_diff = float(diffs.mean())
        sign = _sign(mean_diff)
        if sign == 0:
            sign_match_rate = 0.0
        else:
            sign_match_rate = float((_sign_series(diffs) == sign).mean())
        rows.append(
            {
                "horizon": int(horizon),
                "factor_name": factor_name,
                "factor_group": factor_group,
                "direction": "higher" if mean_diff >= 0 else "lower",
                "periods": int(len(diffs)),
                "mean_median_diff": mean_diff,
                "median_abs_diff": float(diffs.abs().median()),
                "sign_match_rate": sign_match_rate,
                "candidate_score": float(diffs.abs().median()) * sign_match_rate,
                "success_median": float(group["success_median"].mean()),
                "failure_median": float(group["failure_median"].mean()),
            }
        )
    return pd.DataFrame(rows).reindex(columns=ENTRY_SUCCESS_FACTOR_RANK_COLUMNS).sort_values(
        ["candidate_score", "factor_name"],
        ascending=[False, True],
    ).reset_index(drop=True)


def build_entry_success_candidate_v2_rank(
    factor_rank: pd.DataFrame,
    *,
    horizon: int = 40,
    max_factors: int | None = None,
    min_candidate_score: float = 0.0,
    min_sign_match_rate: float = 0.6,
    min_periods: int = 3,
) -> pd.DataFrame:
    if factor_rank.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_CANDIDATE_V2_RANK_COLUMNS)
    frame = factor_rank.copy()
    frame["horizon"] = pd.to_numeric(frame["horizon"], errors="coerce")
    frame["candidate_score"] = pd.to_numeric(frame["candidate_score"], errors="coerce").fillna(0.0)
    frame["sign_match_rate"] = pd.to_numeric(frame["sign_match_rate"], errors="coerce").fillna(0.0)
    frame["periods"] = pd.to_numeric(frame.get("periods", 0), errors="coerce").fillna(0)
    frame = frame[
        (frame["horizon"] == int(horizon))
        & (frame["candidate_score"] > float(min_candidate_score))
        & (frame["sign_match_rate"] >= float(min_sign_match_rate))
        & (frame["periods"] >= int(min_periods))
    ].copy()
    if frame.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_CANDIDATE_V2_RANK_COLUMNS)
    frame["factor_name"] = frame["factor_name"].astype(str)
    frame["direction"] = frame.get("direction", "higher").fillna("higher").astype(str)
    frame = frame.sort_values(["candidate_score", "factor_name"], ascending=[False, True])
    if max_factors is not None:
        frame = frame.head(int(max_factors))
    return frame.reindex(columns=ENTRY_SUCCESS_CANDIDATE_V2_RANK_COLUMNS).reset_index(drop=True)


def join_entry_success(candidate_scores: pd.DataFrame, entry_success: pd.DataFrame) -> pd.DataFrame:
    scores = candidate_scores.copy()
    labels = entry_success.copy()
    if scores.empty:
        return scores
    scores["trade_date"] = scores["trade_date"].map(_iso_date)
    scores["asset_id"] = scores["asset_id"].astype(str)
    labels["trade_date"] = labels["trade_date"].map(_iso_date)
    labels["asset_id"] = labels["asset_id"].astype(str)
    for horizon in HORIZONS:
        success_col = f"entry_success_{horizon}d"
        covered_col = f"entry_success_{horizon}d_covered"
        labels[success_col] = labels[success_col].map(bool)
        labels[covered_col] = labels[covered_col].map(bool)
    return scores.merge(labels, on=["trade_date", "asset_id"], how="inner")


def build_enrichment_by_quantile(joined: pd.DataFrame, *, quantiles: int = 5) -> pd.DataFrame:
    if joined.empty:
        return pd.DataFrame(columns=ENRICHMENT_QUANTILE_COLUMNS)
    frame = joined.copy()
    frame["quantile"] = _score_quantiles_by_date(frame, quantiles)
    baseline = _baseline_rates(frame)
    rows = []
    for quantile, group in frame.dropna(subset=["quantile"]).groupby("quantile", sort=True):
        rows.append(_enrichment_row(group, baseline, {"quantile": quantile}))
    return pd.DataFrame(rows).reindex(columns=ENRICHMENT_QUANTILE_COLUMNS)


def build_enrichment_by_topn(joined: pd.DataFrame, *, top_ns: tuple[int, ...] = (20, 50, 100)) -> pd.DataFrame:
    if joined.empty:
        return pd.DataFrame(columns=ENRICHMENT_TOPN_COLUMNS)
    frame = joined.copy()
    frame["score_rank"] = frame.groupby("trade_date")["candidate_score"].rank(
        method="first",
        ascending=False,
    )
    baseline = _baseline_rates(frame)
    rows = []
    for top_n in top_ns:
        group = frame[frame["score_rank"] <= int(top_n)]
        rows.append(_enrichment_row(group, baseline, {"top_n": int(top_n)}))
    return pd.DataFrame(rows).reindex(columns=ENRICHMENT_TOPN_COLUMNS)


def build_enrichment_by_period(
    joined: pd.DataFrame,
    *,
    quantiles: int = 5,
    period: str = "Q",
) -> pd.DataFrame:
    if joined.empty:
        return pd.DataFrame(columns=ENRICHMENT_PERIOD_COLUMNS)
    frame = joined.copy()
    frame["period"] = pd.to_datetime(frame["trade_date"]).dt.to_period(period).astype(str)
    frame["quantile"] = _score_quantiles_by_date(frame, quantiles)
    top_quantile = f"Q{quantiles}"
    rows = []
    for period_value, period_frame in frame.groupby("period", sort=True):
        baseline = _baseline_rates(period_frame)
        group = period_frame[period_frame["quantile"] == top_quantile]
        rows.append(_enrichment_row(group, baseline, {"period": period_value, "quantile": top_quantile}))
    return pd.DataFrame(rows).reindex(columns=ENRICHMENT_PERIOD_COLUMNS)


def write_candidate_enrichment_outputs(
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
    candidate_scores: pd.DataFrame,
    enrichment_by_quantile: pd.DataFrame,
    enrichment_by_topn: pd.DataFrame,
    enrichment_by_period: pd.DataFrame,
    diagnostics: list[str],
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    paths = {
        "candidate_scores": str(path / "candidate_scores.csv"),
        "enrichment_by_quantile": str(path / "enrichment_by_quantile.csv"),
        "enrichment_by_topn": str(path / "enrichment_by_topn.csv"),
        "enrichment_by_period": str(path / "enrichment_by_period.csv"),
        "markdown_report": str(path / "mid_trend_candidate_enrichment_report.md"),
    }
    candidate_scores.reindex(columns=SCORE_COLUMNS).to_csv(paths["candidate_scores"], index=False)
    enrichment_by_quantile.reindex(columns=ENRICHMENT_QUANTILE_COLUMNS).to_csv(
        paths["enrichment_by_quantile"],
        index=False,
    )
    enrichment_by_topn.reindex(columns=ENRICHMENT_TOPN_COLUMNS).to_csv(
        paths["enrichment_by_topn"],
        index=False,
    )
    enrichment_by_period.reindex(columns=ENRICHMENT_PERIOD_COLUMNS).to_csv(
        paths["enrichment_by_period"],
        index=False,
    )
    Path(paths["markdown_report"]).write_text(
        _markdown_report(
            start_date=str(start_date),
            end_date=str(end_date),
            enrichment_by_quantile=enrichment_by_quantile,
            enrichment_by_topn=enrichment_by_topn,
            enrichment_by_period=enrichment_by_period,
            diagnostics=diagnostics,
        ),
        encoding="utf-8",
    )
    return paths


def build_candidate_entry_success_labels(
    *,
    bars: pd.DataFrame,
    candidate_scores: pd.DataFrame,
) -> pd.DataFrame:
    if candidate_scores.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_COLUMNS)
    signals = candidate_scores[["asset_id", "trade_date"]].drop_duplicates().copy()
    signals["asset_id"] = signals["asset_id"].astype(str)
    signals["trade_date"] = signals["trade_date"].map(_iso_date)
    signals["_order"] = range(len(signals))

    normalized_bars = _normalize_bars_for_entry_success(bars)
    bars_by_asset = {
        str(asset_id): group.reset_index(drop=True)
        for asset_id, group in normalized_bars.groupby("asset_id", sort=False)
    }
    rows: list[dict[str, Any]] = []
    for asset_id, asset_signals in signals.groupby("asset_id", sort=False):
        asset_bars = bars_by_asset.get(str(asset_id))
        if asset_bars is None or asset_bars.empty:
            rows.extend(_missing_entry_rows(asset_signals))
            continue
        rows.extend(_entry_success_rows_for_asset(asset_bars, asset_signals))
    if not rows:
        return pd.DataFrame(columns=ENTRY_SUCCESS_COLUMNS)
    result = pd.DataFrame(rows).sort_values("_order").drop(columns=["_order"])
    result = result.reindex(columns=ENTRY_SUCCESS_COLUMNS)
    for column in ENTRY_SUCCESS_COLUMNS:
        if column.startswith("entry_success_"):
            result[column] = result[column].map(bool).astype(object)
    return result


def write_full_universe_enrichment_outputs(
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
    candidate_scores: pd.DataFrame,
    candidate_entry_success_labels: pd.DataFrame,
    enrichment_by_quantile: pd.DataFrame,
    enrichment_by_topn: pd.DataFrame,
    enrichment_by_period: pd.DataFrame,
    diagnostics: list[str],
) -> dict[str, str]:
    paths = write_candidate_enrichment_outputs(
        output_dir=output_dir,
        start_date=start_date,
        end_date=end_date,
        candidate_scores=candidate_scores,
        enrichment_by_quantile=enrichment_by_quantile,
        enrichment_by_topn=enrichment_by_topn,
        enrichment_by_period=enrichment_by_period,
        diagnostics=diagnostics,
    )
    path = Path(output_dir)
    paths["candidate_entry_success_labels"] = str(path / "candidate_entry_success_labels.csv")
    candidate_entry_success_labels.reindex(columns=ENTRY_SUCCESS_COLUMNS).to_csv(
        paths["candidate_entry_success_labels"],
        index=False,
    )
    return paths


def write_entry_success_reverse_profile_outputs(
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
    factor_profile: pd.DataFrame,
    factor_rank: pd.DataFrame,
    diagnostics: list[str],
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    paths = {
        "entry_success_factor_profile": str(path / "entry_success_factor_profile.csv"),
        "entry_success_factor_rank": str(path / "entry_success_factor_rank.csv"),
        "markdown_report": str(path / "entry_success_reverse_profile_report.md"),
    }
    factor_profile.reindex(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS).to_csv(
        paths["entry_success_factor_profile"],
        index=False,
    )
    factor_rank.reindex(columns=ENTRY_SUCCESS_FACTOR_RANK_COLUMNS).to_csv(
        paths["entry_success_factor_rank"],
        index=False,
    )
    Path(paths["markdown_report"]).write_text(
        _reverse_profile_markdown_report(
            start_date=str(start_date),
            end_date=str(end_date),
            factor_rank=factor_rank,
            factor_profile=factor_profile,
            diagnostics=diagnostics,
        ),
        encoding="utf-8",
    )
    return paths


def write_entry_success_candidate_v2_outputs(
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
    horizon: int,
    candidate_rank: pd.DataFrame,
    candidate_scores: pd.DataFrame,
    candidate_entry_success_labels: pd.DataFrame,
    enrichment_by_quantile: pd.DataFrame,
    enrichment_by_topn: pd.DataFrame,
    enrichment_by_period: pd.DataFrame,
    diagnostics: list[str],
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    paths = {
        "candidate_rank": str(path / "entry_success_candidate_rank.csv"),
        "candidate_scores": str(path / "candidate_scores.csv"),
        "candidate_entry_success_labels": str(path / "candidate_entry_success_labels.csv"),
        "enrichment_by_quantile": str(path / "enrichment_by_quantile.csv"),
        "enrichment_by_topn": str(path / "enrichment_by_topn.csv"),
        "enrichment_by_period": str(path / "enrichment_by_period.csv"),
        "markdown_report": str(path / "entry_success_candidate_v2_report.md"),
    }
    candidate_rank.reindex(columns=ENTRY_SUCCESS_CANDIDATE_V2_RANK_COLUMNS).to_csv(
        paths["candidate_rank"],
        index=False,
    )
    candidate_scores.reindex(columns=SCORE_COLUMNS).to_csv(paths["candidate_scores"], index=False)
    candidate_entry_success_labels.reindex(columns=ENTRY_SUCCESS_COLUMNS).to_csv(
        paths["candidate_entry_success_labels"],
        index=False,
    )
    enrichment_by_quantile.reindex(columns=ENRICHMENT_QUANTILE_COLUMNS).to_csv(
        paths["enrichment_by_quantile"],
        index=False,
    )
    enrichment_by_topn.reindex(columns=ENRICHMENT_TOPN_COLUMNS).to_csv(
        paths["enrichment_by_topn"],
        index=False,
    )
    enrichment_by_period.reindex(columns=ENRICHMENT_PERIOD_COLUMNS).to_csv(
        paths["enrichment_by_period"],
        index=False,
    )
    Path(paths["markdown_report"]).write_text(
        _candidate_v2_markdown_report(
            start_date=str(start_date),
            end_date=str(end_date),
            horizon=int(horizon),
            candidate_rank=candidate_rank,
            enrichment_by_quantile=enrichment_by_quantile,
            enrichment_by_topn=enrichment_by_topn,
            enrichment_by_period=enrichment_by_period,
            diagnostics=diagnostics,
        ),
        encoding="utf-8",
    )
    return paths


def run_candidate_enrichment_report(
    *,
    start_date: object,
    end_date: object,
    candidate_rank_path: str | Path,
    entry_success_labels_path: str | Path,
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    max_factors: int | None = None,
    min_candidate_score: float = 0.0,
    quantiles: int = 5,
    top_ns: tuple[int, ...] = (20, 50, 100),
    period: str = "Q",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    candidate_path = Path(candidate_rank_path)
    entry_path = Path(entry_success_labels_path)
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate_rank CSV not found: {candidate_path}")
    if not entry_path.exists():
        raise FileNotFoundError(f"entry_success_labels CSV not found: {entry_path}")

    candidate_rank = pd.read_csv(candidate_path)
    entry_success = pd.read_csv(entry_path)
    selected = _select_candidates(
        candidate_rank,
        max_factors=max_factors,
        min_candidate_score=min_candidate_score,
    )
    factor_names = selected["factor_name"].astype(str).tolist()
    factors = load_candidate_factor_values_from_db(
        start_date=start,
        end_date=end,
        factor_names=factor_names,
        service=service,
    )
    candidate_scores = build_candidate_scores(
        factors,
        candidate_rank,
        max_factors=max_factors,
        min_candidate_score=min_candidate_score,
    )
    joined = join_entry_success(candidate_scores, entry_success)
    enrichment_by_quantile = build_enrichment_by_quantile(joined, quantiles=quantiles)
    enrichment_by_topn = build_enrichment_by_topn(joined, top_ns=top_ns)
    enrichment_by_period = build_enrichment_by_period(joined, quantiles=quantiles, period=period)
    diagnostics = _diagnostics(
        factor_names=factor_names,
        factors=factors,
        candidate_scores=candidate_scores,
        joined=joined,
    )
    output_dir = (
        Path(reports_dir)
        / f"mid_trend_candidate_enrichment_{start.replace('-', '')}_{end.replace('-', '')}"
    )
    paths = write_candidate_enrichment_outputs(
        output_dir=output_dir,
        start_date=start,
        end_date=end,
        candidate_scores=candidate_scores,
        enrichment_by_quantile=enrichment_by_quantile,
        enrichment_by_topn=enrichment_by_topn,
        enrichment_by_period=enrichment_by_period,
        diagnostics=diagnostics,
    )
    return {
        "paths": paths,
        "candidate_scores": candidate_scores,
        "joined": joined,
        "enrichment_by_quantile": enrichment_by_quantile,
        "enrichment_by_topn": enrichment_by_topn,
        "enrichment_by_period": enrichment_by_period,
        "diagnostics": diagnostics,
    }


def run_entry_success_reverse_profile_report(
    *,
    start_date: object,
    end_date: object,
    entry_success_labels_path: str | Path,
    factor_names: list[str] | None = None,
    horizons: tuple[int, ...] = HORIZONS,
    period: str = "Q",
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    labels_path = Path(entry_success_labels_path)
    if not labels_path.exists():
        raise FileNotFoundError(f"entry_success_labels CSV not found: {labels_path}")
    labels = pd.read_csv(labels_path)
    selected_factors = factor_names or candidate_factor_names()
    factor_profile = load_entry_success_factor_profile_from_db(
        entry_success_labels=labels,
        start_date=start,
        end_date=end,
        factor_names=selected_factors,
        horizons=horizons,
        period=period,
        service=service,
    )
    factor_rank = rank_entry_success_factors(factor_profile)
    diagnostics = _reverse_profile_diagnostics(
        entry_success_labels=labels,
        factor_profile=factor_profile,
        factor_rank=factor_rank,
        factor_names=selected_factors,
    )
    output_dir = (
        Path(reports_dir)
        / f"entry_success_reverse_profile_{start.replace('-', '')}_{end.replace('-', '')}"
    )
    paths = write_entry_success_reverse_profile_outputs(
        output_dir=output_dir,
        start_date=start,
        end_date=end,
        factor_profile=factor_profile,
        factor_rank=factor_rank,
        diagnostics=diagnostics,
    )
    return {
        "paths": paths,
        "factor_profile": factor_profile,
        "factor_rank": factor_rank,
        "diagnostics": diagnostics,
    }


def run_entry_success_candidate_v2_report(
    *,
    start_date: object,
    end_date: object,
    factor_rank_path: str | Path,
    horizon: int = 40,
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    adjust_type: str = "hfq",
    max_factors: int | None = None,
    min_candidate_score: float = 0.0,
    min_sign_match_rate: float = 0.6,
    quantiles: int = 5,
    top_ns: tuple[int, ...] = (20, 50, 100),
    period: str = "Q",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    rank_path = Path(factor_rank_path)
    if not rank_path.exists():
        raise FileNotFoundError(f"entry_success factor_rank CSV not found: {rank_path}")

    factor_rank = pd.read_csv(rank_path)
    candidate_rank = build_entry_success_candidate_v2_rank(
        factor_rank,
        horizon=int(horizon),
        max_factors=max_factors,
        min_candidate_score=min_candidate_score,
        min_sign_match_rate=min_sign_match_rate,
    )
    factor_names = candidate_rank["factor_name"].astype(str).tolist()
    factors = load_candidate_factor_values_from_db(
        start_date=start,
        end_date=end,
        factor_names=factor_names,
        service=service,
    )
    candidate_scores = build_candidate_scores(factors, candidate_rank)
    bars = load_trend_lifecycle_bars(
        start_date=start,
        end_date=end,
        adjust_type=adjust_type,
        service=service,
    )
    candidate_entry_success_labels = build_candidate_entry_success_labels(
        bars=bars,
        candidate_scores=candidate_scores,
    )
    candidate_entry_success_labels = candidate_entry_success_labels[
        (candidate_entry_success_labels["trade_date"] >= start)
        & (candidate_entry_success_labels["trade_date"] <= end)
    ].reset_index(drop=True)
    joined = join_entry_success(candidate_scores, candidate_entry_success_labels)
    enrichment_by_quantile = build_enrichment_by_quantile(joined, quantiles=quantiles)
    enrichment_by_topn = build_enrichment_by_topn(joined, top_ns=top_ns)
    enrichment_by_period = build_enrichment_by_period(joined, quantiles=quantiles, period=period)
    diagnostics = _candidate_v2_diagnostics(
        candidate_rank=candidate_rank,
        factor_names=factor_names,
        factors=factors,
        candidate_scores=candidate_scores,
        candidate_entry_success_labels=candidate_entry_success_labels,
        joined=joined,
    )
    output_dir = (
        Path(reports_dir)
        / f"entry_success_candidate_v2_h{int(horizon)}_{start.replace('-', '')}_{end.replace('-', '')}"
    )
    paths = write_entry_success_candidate_v2_outputs(
        output_dir=output_dir,
        start_date=start,
        end_date=end,
        horizon=int(horizon),
        candidate_rank=candidate_rank,
        candidate_scores=candidate_scores,
        candidate_entry_success_labels=candidate_entry_success_labels,
        enrichment_by_quantile=enrichment_by_quantile,
        enrichment_by_topn=enrichment_by_topn,
        enrichment_by_period=enrichment_by_period,
        diagnostics=diagnostics,
    )
    return {
        "paths": paths,
        "candidate_rank": candidate_rank,
        "candidate_scores": candidate_scores,
        "candidate_entry_success_labels": candidate_entry_success_labels,
        "joined": joined,
        "enrichment_by_quantile": enrichment_by_quantile,
        "enrichment_by_topn": enrichment_by_topn,
        "enrichment_by_period": enrichment_by_period,
        "diagnostics": diagnostics,
    }


def run_full_universe_candidate_enrichment_report(
    *,
    start_date: object,
    end_date: object,
    candidate_scores_path: str | Path,
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    adjust_type: str = "hfq",
    quantiles: int = 5,
    top_ns: tuple[int, ...] = (20, 50, 100),
    period: str = "Q",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    scores_path = Path(candidate_scores_path)
    if not scores_path.exists():
        raise FileNotFoundError(f"candidate_scores CSV not found: {scores_path}")

    candidate_scores = pd.read_csv(scores_path)
    bars = load_trend_lifecycle_bars(
        start_date=start,
        end_date=end,
        adjust_type=adjust_type,
        service=service,
    )
    candidate_entry_success_labels = build_candidate_entry_success_labels(
        bars=bars,
        candidate_scores=candidate_scores,
    )
    candidate_entry_success_labels = candidate_entry_success_labels[
        (candidate_entry_success_labels["trade_date"] >= start)
        & (candidate_entry_success_labels["trade_date"] <= end)
    ].reset_index(drop=True)
    joined = join_entry_success(candidate_scores, candidate_entry_success_labels)
    enrichment_by_quantile = build_enrichment_by_quantile(joined, quantiles=quantiles)
    enrichment_by_topn = build_enrichment_by_topn(joined, top_ns=top_ns)
    enrichment_by_period = build_enrichment_by_period(joined, quantiles=quantiles, period=period)
    diagnostics = _full_universe_diagnostics(
        candidate_scores=candidate_scores,
        candidate_entry_success_labels=candidate_entry_success_labels,
        joined=joined,
    )
    output_dir = (
        Path(reports_dir)
        / f"mid_trend_candidate_full_universe_{start.replace('-', '')}_{end.replace('-', '')}"
    )
    paths = write_full_universe_enrichment_outputs(
        output_dir=output_dir,
        start_date=start,
        end_date=end,
        candidate_scores=candidate_scores,
        candidate_entry_success_labels=candidate_entry_success_labels,
        enrichment_by_quantile=enrichment_by_quantile,
        enrichment_by_topn=enrichment_by_topn,
        enrichment_by_period=enrichment_by_period,
        diagnostics=diagnostics,
    )
    return {
        "paths": paths,
        "candidate_scores": candidate_scores,
        "candidate_entry_success_labels": candidate_entry_success_labels,
        "joined": joined,
        "enrichment_by_quantile": enrichment_by_quantile,
        "enrichment_by_topn": enrichment_by_topn,
        "enrichment_by_period": enrichment_by_period,
        "diagnostics": diagnostics,
    }


def load_candidate_factor_values_from_db(
    *,
    start_date: str,
    end_date: str,
    factor_names: list[str],
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not factor_names:
        return pd.DataFrame(columns=["trade_date", "asset_id", "factor_name", "factor_value"])
    sql = """
        SELECT trade_date, asset_id, factor_name, factor_value
        FROM factor.factor_daily
        WHERE trade_date BETWEEN %s AND %s
          AND factor_name = ANY(%s)
          AND factor_value IS NOT NULL
        ORDER BY trade_date, factor_name, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [start_date, end_date, factor_names])
    return pd.DataFrame(rows)


def load_entry_success_factor_profile_from_db(
    *,
    entry_success_labels: pd.DataFrame,
    start_date: str,
    end_date: str,
    factor_names: list[str],
    horizons: tuple[int, ...] = HORIZONS,
    period: str = "Q",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    labels = entry_success_labels.copy()
    labels["trade_date"] = labels["trade_date"].map(_iso_date)
    labels["asset_id"] = labels["asset_id"].astype(str)
    labels = labels[(labels["trade_date"] >= start_date) & (labels["trade_date"] <= end_date)].copy()
    if labels.empty or not factor_names:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS)
    valid_horizons = tuple(int(horizon) for horizon in horizons if int(horizon) in HORIZONS)
    if not valid_horizons:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS)
    columns = ["trade_date", "asset_id"]
    for horizon in valid_horizons:
        columns.extend([f"entry_success_{horizon}d", f"entry_success_{horizon}d_covered"])
    labels = labels[columns].drop_duplicates()

    with connect(service) as conn:
        with conn.cursor() as cur:
            column_sql = ", ".join(
                [
                    "trade_date date NOT NULL",
                    "asset_id text NOT NULL",
                    *[
                        f"entry_success_{horizon}d boolean NOT NULL, "
                        f"entry_success_{horizon}d_covered boolean NOT NULL"
                        for horizon in valid_horizons
                    ],
                ]
            )
            cur.execute(
                f"""
                CREATE TEMP TABLE tmp_entry_success_reverse_labels (
                    {column_sql}
                ) ON COMMIT DROP
                """
            )
            copy_columns = ", ".join(columns)
            with cur.copy(
                f"COPY tmp_entry_success_reverse_labels ({copy_columns}) FROM STDIN"
            ) as copy:
                for row in labels.itertuples(index=False):
                    copy.write_row(row)

            profile_rows = []
            period_expr = _period_sql(period, table_alias="l")
            for horizon in valid_horizons:
                success_col = f"entry_success_{horizon}d"
                covered_col = f"entry_success_{horizon}d_covered"
                cur.execute(
                    f"""
                    SELECT
                        {period_expr} AS period,
                        %s::int AS horizon,
                        f.factor_name,
                        max(f.factor_group) AS factor_group,
                        count(*) FILTER (WHERE l.{success_col})::int AS success_n,
                        count(*) FILTER (WHERE NOT l.{success_col})::int AS failure_n,
                        avg(f.factor_value::double precision) FILTER (WHERE l.{success_col}) AS success_mean,
                        avg(f.factor_value::double precision) FILTER (WHERE NOT l.{success_col}) AS failure_mean,
                        percentile_cont(0.5) WITHIN GROUP (
                            ORDER BY f.factor_value::double precision
                        ) FILTER (WHERE l.{success_col}) AS success_median,
                        percentile_cont(0.5) WITHIN GROUP (
                            ORDER BY f.factor_value::double precision
                        ) FILTER (WHERE NOT l.{success_col}) AS failure_median
                    FROM tmp_entry_success_reverse_labels l
                    JOIN factor.factor_daily f
                      ON f.trade_date = l.trade_date
                     AND f.asset_id = l.asset_id
                    WHERE f.factor_name = ANY(%s)
                      AND f.factor_value IS NOT NULL
                      AND l.{covered_col}
                    GROUP BY {period_expr}, f.factor_name
                    ORDER BY f.factor_name, {period_expr}
                    """,
                    [horizon, factor_names],
                )
                profile_rows.extend(cur.fetchall())
    profile = pd.DataFrame(profile_rows)
    if profile.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS)
    profile["median_diff"] = profile["success_median"] - profile["failure_median"]
    profile["success_n"] = profile["success_n"].astype(int)
    profile["failure_n"] = profile["failure_n"].astype(int)
    return profile.reindex(columns=ENTRY_SUCCESS_FACTOR_PROFILE_COLUMNS)


def _normalize_factors(factors: pd.DataFrame) -> pd.DataFrame:
    if factors.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "factor_name", "factor_value"])
    frame = factors.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["factor_name"] = frame["factor_name"].astype(str)
    frame["factor_value"] = pd.to_numeric(frame["factor_value"], errors="coerce")
    return frame


def _select_candidates(
    candidate_rank: pd.DataFrame,
    *,
    max_factors: int | None,
    min_candidate_score: float,
) -> pd.DataFrame:
    if candidate_rank.empty:
        return pd.DataFrame(columns=["factor_name", "direction", "candidate_weight"])
    frame = candidate_rank.copy()
    frame["candidate_score"] = pd.to_numeric(frame["candidate_score"], errors="coerce").fillna(0.0)
    frame = frame[frame["candidate_score"] > float(min_candidate_score)].copy()
    if frame.empty:
        return pd.DataFrame(columns=["factor_name", "direction", "candidate_weight"])
    frame = frame.sort_values(["candidate_score", "factor_name"], ascending=[False, True])
    if max_factors is not None:
        frame = frame.head(int(max_factors))
    frame["direction"] = frame.get("direction", "higher")
    frame["candidate_weight"] = frame["candidate_score"] / frame["candidate_score"].sum()
    return frame[["factor_name", "direction", "candidate_weight"]]


def _directional_rank_score(group: pd.DataFrame) -> pd.Series:
    direction = str(group["direction"].iloc[0]).lower()
    ascending = direction != "lower"
    return group["factor_value"].rank(method="average", pct=True, ascending=ascending) * 100.0


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _sign_series(values: pd.Series) -> pd.Series:
    return values.map(_sign)


def _score_quantiles_by_date(frame: pd.DataFrame, quantiles: int) -> pd.Series:
    labels = [f"Q{idx}" for idx in range(1, int(quantiles) + 1)]

    def assign(group: pd.DataFrame) -> pd.Series:
        ranked = group["candidate_score"].rank(method="first")
        bucket_count = min(int(quantiles), len(group))
        if bucket_count <= 1:
            return pd.Series([labels[-1]] * len(group), index=group.index)
        local_labels = labels[-bucket_count:]
        return pd.qcut(ranked, q=bucket_count, labels=local_labels).astype(str)

    return frame.groupby("trade_date", group_keys=False).apply(assign, include_groups=False)


def _baseline_rates(frame: pd.DataFrame) -> dict[int, float]:
    return {horizon: _success_rate(frame, horizon) for horizon in HORIZONS}


def _enrichment_row(group: pd.DataFrame, baseline: dict[int, float], keys: dict[str, Any]) -> dict[str, Any]:
    row = {
        **keys,
        "rows": int(len(group)),
        "avg_score": float(group["candidate_score"].mean()) if not group.empty else 0.0,
    }
    for horizon in HORIZONS:
        rate = _success_rate(group, horizon)
        base = baseline[horizon]
        row[f"entry_success_{horizon}d_rate"] = rate
        row[f"entry_success_{horizon}d_lift"] = rate / base if base > 0 else 0.0
    return row


def _success_rate(frame: pd.DataFrame, horizon: int) -> float:
    covered_col = f"entry_success_{horizon}d_covered"
    success_col = f"entry_success_{horizon}d"
    if frame.empty or covered_col not in frame.columns or success_col not in frame.columns:
        return 0.0
    covered = frame[frame[covered_col].map(bool)]
    if covered.empty:
        return 0.0
    return float(covered[success_col].map(bool).mean())


def _markdown_report(
    *,
    start_date: str,
    end_date: str,
    enrichment_by_quantile: pd.DataFrame,
    enrichment_by_topn: pd.DataFrame,
    enrichment_by_period: pd.DataFrame,
    diagnostics: list[str],
) -> str:
    lines = [
        "# Candidate Enrichment Validation V1",
        "",
        f"- Period: {start_date} to {end_date}",
        "- Target: validate mid_trend early/early_mid candidate factors against entry_success labels.",
        "- Scope: research diagnostics only; this is not a portfolio backtest.",
        "",
        "## Enrichment By Quantile",
        "",
        _markdown_table(enrichment_by_quantile),
        "",
        "## Enrichment By TopN",
        "",
        _markdown_table(enrichment_by_topn),
        "",
        "## Enrichment By Period",
        "",
        _markdown_table(enrichment_by_period),
        "",
        "## Data Issues",
        "",
    ]
    if diagnostics:
        lines.extend(f"- {item}" for item in diagnostics)
    else:
        lines.append("- No data issues detected by candidate enrichment diagnostics.")
    lines.extend(
        [
            "",
            "## Next Stage",
            "",
            "- If TopN and top quantile lift are stable, convert the score into a paper portfolio experiment.",
            "- Keep cost, limit-up/down execution constraints, and turnover controls out of this diagnostic layer.",
            "",
        ]
    )
    return "\n".join(lines)


def _reverse_profile_markdown_report(
    *,
    start_date: str,
    end_date: str,
    factor_rank: pd.DataFrame,
    factor_profile: pd.DataFrame,
    diagnostics: list[str],
) -> str:
    lines = [
        "# Entry Success Reverse Factor Profile V1",
        "",
        f"- Period: {start_date} to {end_date}",
        "- Target: profile factors from `entry_success=True` samples versus covered failures.",
        "- Scope: factor diagnostics only; this is not a portfolio backtest.",
        "",
        "## Factor Rank",
        "",
        _markdown_table(factor_rank.head(30)),
        "",
        "## Factor Profile Sample",
        "",
        _markdown_table(factor_profile.head(40)),
        "",
        "## Data Issues",
        "",
    ]
    if diagnostics:
        lines.extend(f"- {item}" for item in diagnostics)
    else:
        lines.append("- No data issues detected by reverse profile diagnostics.")
    lines.extend(
        [
            "",
            "## Next Stage",
            "",
            "- Use stable reverse-profile factors to design a new entry-success score.",
            "- Validate the new score out-of-sample before any portfolio backtest.",
            "",
        ]
    )
    return "\n".join(lines)


def _candidate_v2_markdown_report(
    *,
    start_date: str,
    end_date: str,
    horizon: int,
    candidate_rank: pd.DataFrame,
    enrichment_by_quantile: pd.DataFrame,
    enrichment_by_topn: pd.DataFrame,
    enrichment_by_period: pd.DataFrame,
    diagnostics: list[str],
) -> str:
    lines = [
        "# Entry Success Candidate V2",
        "",
        f"- Period: {start_date} to {end_date}",
        f"- Source: reverse-profile factor rank for entry_success_{int(horizon)}d.",
        "- Scope: full-universe label validation only; this is not a portfolio backtest.",
        "",
        "## Selected Candidate Factors",
        "",
        _markdown_table(candidate_rank),
        "",
        "## Enrichment By Quantile",
        "",
        _markdown_table(enrichment_by_quantile),
        "",
        "## Enrichment By TopN",
        "",
        _markdown_table(enrichment_by_topn),
        "",
        "## Enrichment By Period",
        "",
        _markdown_table(enrichment_by_period),
        "",
        "## Data Issues",
        "",
    ]
    if diagnostics:
        lines.extend(f"- {item}" for item in diagnostics)
    else:
        lines.append("- No data issues detected by candidate V2 diagnostics.")
    lines.extend(
        [
            "",
            "## Next Stage",
            "",
            "- If top quantile and TopN lift are stable, run a simple holding-period paper portfolio.",
            "- Keep cost, limit-up/down execution constraints, and turnover controls in the portfolio layer.",
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    return frame.to_markdown(index=False)


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _period_sql(period: str | None, *, table_alias: str) -> str:
    prefix = f"{table_alias}." if table_alias else ""
    normalized = (period or "").upper()
    if not normalized:
        return "'all'"
    if normalized == "Q":
        return f"to_char({prefix}trade_date, 'YYYY\"Q\"Q')"
    if normalized == "M":
        return f"to_char({prefix}trade_date, 'YYYY-MM')"
    if normalized in {"A", "Y"}:
        return f"to_char({prefix}trade_date, 'YYYY')"
    raise ValueError("period must be one of: Q, M, A, Y")


def _diagnostics(
    *,
    factor_names: list[str],
    factors: pd.DataFrame,
    candidate_scores: pd.DataFrame,
    joined: pd.DataFrame,
) -> list[str]:
    diagnostics = []
    if not factor_names:
        diagnostics.append("No positive candidate factors were selected.")
    loaded = set(factors.get("factor_name", pd.Series(dtype=str)).dropna().astype(str))
    missing = sorted(set(factor_names) - loaded)
    if missing:
        diagnostics.append("Missing factor rows: " + ",".join(missing))
    if candidate_scores.empty:
        diagnostics.append("No candidate scores were produced.")
    if joined.empty:
        diagnostics.append("No candidate scores matched entry_success labels.")
    elif len(joined) < len(candidate_scores):
        diagnostics.append(
            "Entry success labels matched "
            f"{len(joined)}/{len(candidate_scores)} candidate score rows; "
            "enrichment is limited to the provided signal universe."
        )
    diagnostics.append(
        "Candidate factor weights come from lifecycle diagnostics; this is in-sample research, "
        "not a production scoring or portfolio backtest."
    )
    return diagnostics


def _reverse_profile_diagnostics(
    *,
    entry_success_labels: pd.DataFrame,
    factor_profile: pd.DataFrame,
    factor_rank: pd.DataFrame,
    factor_names: list[str],
) -> list[str]:
    diagnostics = []
    if entry_success_labels.empty:
        diagnostics.append("No entry_success labels were provided.")
    missing = sorted(set(factor_names) - set(factor_profile.get("factor_name", pd.Series(dtype=str)).dropna().astype(str)))
    if missing:
        diagnostics.append("Missing factor profile rows: " + ",".join(missing))
    if factor_rank.empty:
        diagnostics.append("No entry-success factor ranking was produced.")
    diagnostics.append(
        "Reverse profile compares same-date factor values for covered entry_success labels; "
        "it does not use future data as features."
    )
    return diagnostics


def _full_universe_diagnostics(
    *,
    candidate_scores: pd.DataFrame,
    candidate_entry_success_labels: pd.DataFrame,
    joined: pd.DataFrame,
) -> list[str]:
    diagnostics = []
    if candidate_scores.empty:
        diagnostics.append("No candidate scores were provided.")
    if candidate_entry_success_labels.empty:
        diagnostics.append("No full-universe entry_success labels were produced.")
    if len(joined) < len(candidate_scores):
        diagnostics.append(
            "Entry success labels matched "
            f"{len(joined)}/{len(candidate_scores)} candidate score rows."
        )
    diagnostics.append(
        "Full-universe enrichment uses candidate_scores as the signal universe; "
        "it is still a label diagnostic, not a portfolio backtest."
    )
    return diagnostics


def _candidate_v2_diagnostics(
    *,
    candidate_rank: pd.DataFrame,
    factor_names: list[str],
    factors: pd.DataFrame,
    candidate_scores: pd.DataFrame,
    candidate_entry_success_labels: pd.DataFrame,
    joined: pd.DataFrame,
) -> list[str]:
    diagnostics = _diagnostics(
        factor_names=factor_names,
        factors=factors,
        candidate_scores=candidate_scores,
        joined=joined,
    )
    diagnostics.extend(
        _full_universe_diagnostics(
            candidate_scores=candidate_scores,
            candidate_entry_success_labels=candidate_entry_success_labels,
            joined=joined,
        )
    )
    if candidate_rank.empty:
        diagnostics.append(
            "No reverse-profile factors passed the V2 filters; lower thresholds or inspect factor_rank input."
        )
    diagnostics.append(
        "Entry Success Candidate V2 uses same-date factor values and future entry_success labels only for validation."
    )
    return diagnostics


def _normalize_bars_for_entry_success(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame(columns=["asset_id", "trade_date", "open", "high", "low", "close", "amount"])
    frame = bars.copy()
    if "asset_id" not in frame.columns:
        frame["asset_id"] = ""
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    for column in ("open", "high", "low", "close", "amount"):
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def _missing_entry_rows(asset_signals: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for signal in asset_signals.to_dict("records"):
        row = {
            "asset_id": str(signal["asset_id"]),
            "trade_date": _iso_date(signal["trade_date"]),
            "_order": int(signal["_order"]),
        }
        for rule in DEFAULT_ENTRY_SUCCESS_RULES:
            row[rule.name] = False
            row[f"{rule.name}_covered"] = False
        rows.append(row)
    return rows


def _entry_success_rows_for_asset(asset_bars: pd.DataFrame, asset_signals: pd.DataFrame) -> list[dict[str, Any]]:
    close = asset_bars["close"].to_numpy(dtype=float)
    trade_dates = asset_bars["trade_date"].astype(str).to_numpy()
    index_by_date = {trade_dates[idx]: idx for idx in range(len(trade_dates))}
    rows: list[dict[str, Any]] = []
    for signal in asset_signals.to_dict("records"):
        trade_date = _iso_date(signal["trade_date"])
        entry_index = index_by_date.get(trade_date)
        row = {
            "asset_id": str(signal["asset_id"]),
            "trade_date": trade_date,
            "_order": int(signal["_order"]),
        }
        if entry_index is None:
            for rule in DEFAULT_ENTRY_SUCCESS_RULES:
                row[rule.name] = False
                row[f"{rule.name}_covered"] = False
            rows.append(row)
            continue
        entry_close = close[entry_index]
        if np.isnan(entry_close) or entry_close <= 0:
            for rule in DEFAULT_ENTRY_SUCCESS_RULES:
                row[rule.name] = False
                row[f"{rule.name}_covered"] = False
            rows.append(row)
            continue
        for rule in DEFAULT_ENTRY_SUCCESS_RULES:
            success, covered = _vectorized_entry_success_for_index(
                close=close,
                entry_index=entry_index,
                entry_close=float(entry_close),
                horizon=int(rule.horizon),
                profit_threshold=float(rule.profit_threshold),
                stop_threshold=float(rule.stop_threshold),
            )
            row[rule.name] = bool(success)
            row[f"{rule.name}_covered"] = bool(covered)
        rows.append(row)
    return rows


def _vectorized_entry_success_for_index(
    *,
    close: np.ndarray,
    entry_index: int,
    entry_close: float,
    horizon: int,
    profit_threshold: float,
    stop_threshold: float,
) -> tuple[bool, bool]:
    end_index = entry_index + horizon
    covered = end_index < len(close)
    future = close[entry_index + 1 : min(len(close), end_index + 1)]
    if future.size == 0:
        return False, covered
    rel = future / entry_close - 1.0
    profit_hits = np.where(rel >= profit_threshold)[0]
    stop_hits = np.where(rel <= stop_threshold)[0]
    first_profit = int(profit_hits[0]) if profit_hits.size else horizon + 1
    first_stop = int(stop_hits[0]) if stop_hits.size else horizon + 1
    return first_profit < first_stop and first_profit <= horizon, covered
