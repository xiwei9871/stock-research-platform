from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.industry_focus_score import (
    FIXED_FOCUS_INDUSTRIES,
    SUMMARY_COLUMNS,
    _iso_date,
    _month_chunks,
    build_industry_scores,
    filter_scores_to_focus_industries,
    load_industry_memberships,
    load_prices,
    load_stock_scores,
    rank_by_date,
    select_dynamic_hysteresis_focus,
    select_dynamic_topk_focus,
    select_fixed_focus,
    summarize_variant_result,
)
from stock_research.performance_metrics import calc_performance_metrics
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    run_vectorized_topn_backtest,
)


V2_WEIGHTS = {
    "trend_persistence_score": 0.25,
    "amount_share_score": 0.20,
    "candidate_density_score": 0.20,
    "breadth_expansion_score": 0.15,
    "leader_to_middle_expansion_score": 0.10,
    "risk_adjusted_strength_score": 0.10,
}

V2_DIAGNOSTIC_COLUMNS = [
    "rebalance_month",
    "rebalance_date",
    "industry_name",
    "v1_score",
    "industry_focus_score_v2",
    "trend_persistence_score",
    "amount_share_score",
    "candidate_density_score",
    "breadth_expansion_score",
    "leader_to_middle_expansion_score",
    "risk_adjusted_strength_score",
    "overheat_penalty",
    "concentration_penalty",
    "selected_by_v1_topk",
    "selected_by_v1_lagged_exit",
    "selected_by_v2_topk",
    "future_20d_return",
    "future_20d_rank",
    "future_20d_excess_return",
    "future_20d_max_drawdown",
    "industry_amount_share_5d",
    "industry_amount_share_20d",
    "industry_amount_share_change_5d_vs_20d",
    "top20_stock_count",
    "top50_stock_count",
    "top100_stock_count",
    "top20_density",
    "top50_density",
    "top100_density",
    "industry_member_count",
    "industry_return_concentration_top3",
    "overheat_flag",
    "diagnosis_tag",
]


def expand_interval_memberships(
    asset_dates: pd.DataFrame,
    membership_intervals: pd.DataFrame,
) -> pd.DataFrame:
    if asset_dates.empty or membership_intervals.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "industry_name"])
    dates = asset_dates.copy()
    intervals = membership_intervals.copy()
    dates["trade_date"] = dates["trade_date"].map(_iso_date)
    dates["asset_id"] = dates["asset_id"].astype(str)
    intervals["asset_id"] = intervals["asset_id"].astype(str)
    intervals["start_date"] = intervals["start_date"].map(_iso_date)
    intervals["end_date"] = intervals["end_date"].map(
        lambda value: None if pd.isna(value) else _iso_date(value)
    )
    joined = dates.merge(intervals, on="asset_id", how="inner")
    active = joined[
        (joined["start_date"] <= joined["trade_date"])
        & (joined["end_date"].isna() | (joined["end_date"] >= joined["trade_date"]))
    ].copy()
    return active.sort_values(["trade_date", "asset_id"])[
        ["trade_date", "asset_id", "industry_name"]
    ].reset_index(drop=True)


def build_candidate_density(stock_scores: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    scores = _normalize_scores(stock_scores)
    members = _normalize_daily_memberships(memberships)
    columns = [
        "trade_date",
        "industry_name",
        "industry_member_count",
        "top20_stock_count",
        "top50_stock_count",
        "top100_stock_count",
        "top20_density",
        "top50_density",
        "top100_density",
    ]
    if scores.empty or members.empty:
        return pd.DataFrame(columns=columns)
    base = members.groupby(["trade_date", "industry_name"], as_index=False).agg(
        industry_member_count=("asset_id", "nunique")
    )
    joined = scores.merge(
        members[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    joined["score_rank"] = joined.groupby("trade_date")["score_total"].rank(
        method="first",
        ascending=False,
    )
    for limit in (20, 50, 100):
        joined[f"in_top{limit}"] = joined["score_rank"] <= limit
    counts = joined.groupby(["trade_date", "industry_name"], as_index=False).agg(
        top20_stock_count=("in_top20", "sum"),
        top50_stock_count=("in_top50", "sum"),
        top100_stock_count=("in_top100", "sum"),
    )
    result = base.merge(counts, on=["trade_date", "industry_name"], how="left")
    for col in ["top20_stock_count", "top50_stock_count", "top100_stock_count"]:
        result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0).astype(int)
    denom = result["industry_member_count"].replace(0, pd.NA)
    result["top20_density"] = result["top20_stock_count"] / denom
    result["top50_density"] = result["top50_stock_count"] / denom
    result["top100_density"] = result["top100_stock_count"] / denom
    return result[columns]


def add_overheat_penalty(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    rank_specs = [
        ("industry_ret_5d", "ret_5d_heat_rank"),
        ("industry_amount_share_change_5d_vs_20d", "amount_share_spike_rank"),
        ("industry_amount_share_5d_percentile_60d", "amount_share_percentile_rank"),
        ("industry_distance_ma20", "distance_ma20_rank"),
    ]
    for value_col, output_col in rank_specs:
        if value_col not in result.columns:
            result[value_col] = 0.0
        result = rank_by_date(result, value_col=value_col, output_col=output_col, ascending=True)
    result["overheat_penalty"] = (
        0.35 * result["ret_5d_heat_rank"]
        + 0.30 * result["amount_share_spike_rank"]
        + 0.20 * result["amount_share_percentile_rank"]
        + 0.15 * result["distance_ma20_rank"]
    ).fillna(0.0)
    result["overheat_flag"] = result["overheat_penalty"] >= 0.75
    return result


def build_return_concentration(stock_returns: pd.DataFrame) -> pd.DataFrame:
    if stock_returns.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "industry_name",
                "industry_return_concentration_top3",
                "concentration_penalty",
            ]
        )
    frame = stock_returns.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["ret_20d"] = pd.to_numeric(frame["ret_20d"], errors="coerce").fillna(0.0)
    rows: list[dict[str, Any]] = []
    for (trade_date, industry_name), group in frame.groupby(["trade_date", "industry_name"]):
        positive = group[group["ret_20d"] > 0]["ret_20d"].sort_values(ascending=False)
        total = float(positive.sum())
        top3 = float(positive.head(3).sum())
        concentration = top3 / total if total > 0 else 0.0
        rows.append(
            {
                "trade_date": trade_date,
                "industry_name": industry_name,
                "industry_return_concentration_top3": concentration,
                "concentration_penalty": max(0.0, concentration - 0.35),
            }
        )
    return pd.DataFrame(rows)


def build_industry_focus_score_v2(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["trend_persistence_score"] = _rank_component(
        result,
        [
            "industry_ret_5d",
            "industry_ret_10d",
            "industry_ret_20d",
            "industry_excess_ret_5d",
            "industry_excess_ret_10d",
            "industry_excess_ret_20d",
            "top_rank_days_20d",
        ],
    )
    result["amount_share_score"] = _rank_component(
        result,
        [
            "industry_amount_share_5d",
            "industry_amount_share_20d",
            "industry_amount_share_change_5d_vs_20d",
            "industry_amount_share_5d_percentile_60d",
        ],
    )
    result["candidate_density_score"] = _rank_component(
        result,
        ["top20_density", "top50_density", "top100_density"],
    )
    result["breadth_expansion_score"] = _rank_component(
        result,
        ["up_ratio_20d", "excess_up_ratio_20d", "top100_stock_count"],
    )
    result["leader_to_middle_expansion_score"] = _leader_middle_score(result)
    result["risk_adjusted_strength_score"] = _risk_adjusted_score(result)
    result = add_overheat_penalty(result)
    if "concentration_penalty" not in result.columns:
        result["concentration_penalty"] = 0.0
    total = 0.0
    for col, weight in V2_WEIGHTS.items():
        total = total + weight * pd.to_numeric(result[col], errors="coerce").fillna(0.0)
    result["industry_focus_score_v2"] = (
        total
        - pd.to_numeric(result["overheat_penalty"], errors="coerce").fillna(0.0)
        - pd.to_numeric(result["concentration_penalty"], errors="coerce").fillna(0.0)
    )
    return result


def run_industry_focus_v2_diagnostics(
    *,
    start_date: object,
    end_date: object,
    min_industry_stocks: int = 20,
    output_dir: str | Path = Path("/Users/xiwei/stock_research/outputs/research"),
    industry_system: str = "csrc",
    industry_level: int = 1,
    adjust_type: str = "hfq",
    dynamic_top_k: int = 4,
    short_window: int = 5,
    medium_window: int = 10,
    long_window: int = 20,
    forward_window: int = 20,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    prices, memberships, stock_scores = load_research_inputs(
        start_date=start,
        end_date=end,
        lookback_days=120,
        forward_days=45,
        industry_system=industry_system,
        industry_level=industry_level,
        adjust_type=adjust_type,
        service=service,
    )
    panel = build_industry_diagnostic_panel(
        prices=prices,
        memberships=memberships,
        stock_scores=stock_scores,
        min_industry_stocks=min_industry_stocks,
        short_window=short_window,
        medium_window=medium_window,
        long_window=long_window,
        forward_window=forward_window,
    )
    panel = panel[(panel["trade_date"] >= start) & (panel["trade_date"] <= end)].copy()
    v1 = build_industry_scores(
        prices=prices,
        memberships=memberships,
        stock_scores=stock_scores,
        min_industry_stocks=min_industry_stocks,
        short_window=long_window,
        long_window=60,
    )
    v1 = v1[(v1["trade_date"] >= start) & (v1["trade_date"] <= end)].copy()
    v1 = v1.rename(columns={"industry_focus_score": "v1_score"})
    merged = panel.merge(
        v1[["trade_date", "industry_name", "v1_score"]],
        on=["trade_date", "industry_name"],
        how="left",
    )
    topk = select_dynamic_topk_focus(
        v1.rename(columns={"v1_score": "industry_focus_score"}),
        top_k=dynamic_top_k,
    )
    lagged = select_dynamic_hysteresis_focus(
        v1.rename(columns={"v1_score": "industry_focus_score"})
    )
    merged = _add_selection_flags(merged, topk, "selected_by_v1_topk")
    merged = _add_selection_flags(merged, lagged, "selected_by_v1_lagged_exit")
    scored = build_industry_focus_score_v2(merged)
    v2_topk = _select_v2_topk(scored, top_k=dynamic_top_k)
    scored = _add_selection_flags(scored, v2_topk, "selected_by_v2_topk")
    scored = add_diagnosis_tags(scored)
    scored["rebalance_date"] = scored["trade_date"]
    scored["rebalance_month"] = pd.to_datetime(scored["rebalance_date"]).dt.to_period("M").astype(str)
    scored["future_20d_return"] = scored["industry_forward_20d_return"]
    scored["future_20d_excess_return"] = scored["industry_forward_20d_excess_return"]
    scored["future_20d_rank"] = scored["industry_forward_20d_rank"]
    scored["future_20d_max_drawdown"] = scored["industry_forward_20d_max_drawdown"]
    v2_diag = scored.reindex(columns=V2_DIAGNOSTIC_COLUMNS).sort_values(
        ["rebalance_date", "industry_focus_score_v2"],
        ascending=[True, False],
    )
    v1_attr = _v1_failure_attribution(scored)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "v1_failure_attribution": str(output / "industry_v1_failure_attribution.csv"),
        "v2_diagnostics": str(output / "industry_focus_score_v2_diagnostics.csv"),
    }
    v1_attr.to_csv(paths["v1_failure_attribution"], index=False)
    v2_diag.to_csv(paths["v2_diagnostics"], index=False)
    return {"paths": paths, "v1_failure_attribution": v1_attr, "v2_diagnostics": v2_diag}


def run_industry_focus_v2_backtest(
    *,
    start_date: object,
    end_date: object,
    diagnostics_path: str | Path,
    top_n: int = 20,
    transaction_cost_bps: float = 20.0,
    output_dir: str | Path = Path("/Users/xiwei/stock_research/outputs/research"),
    industry_system: str = "csrc",
    industry_level: int = 1,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    diagnostics = pd.read_csv(diagnostics_path)
    prices, memberships, stock_scores = load_research_inputs(
        start_date=start,
        end_date=end,
        lookback_days=0,
        forward_days=0,
        industry_system=industry_system,
        industry_level=industry_level,
        adjust_type=adjust_type,
        service=service,
    )
    scores = _normalize_scores(stock_scores)
    fixed_focus = select_fixed_focus(trade_dates=sorted(scores["trade_date"].unique().tolist()))
    v1_focus = diagnostics.rename(
        columns={"rebalance_date": "trade_date", "v1_score": "industry_focus_score"}
    )
    v1_topk = v1_focus[v1_focus["selected_by_v1_topk"]][
        ["trade_date", "industry_name", "industry_focus_score"]
    ]
    v1_lagged = v1_focus[v1_focus["selected_by_v1_lagged_exit"]][
        ["trade_date", "industry_name", "industry_focus_score"]
    ]
    v2_topk = diagnostics[diagnostics["selected_by_v2_topk"]].rename(
        columns={"rebalance_date": "trade_date", "industry_focus_score_v2": "industry_focus_score"}
    )[["trade_date", "industry_name", "industry_focus_score"]]

    variant_scores = {
        "base_top20": scores,
        "fixed_focus_pool_top20": filter_scores_to_focus_industries(scores, memberships, fixed_focus),
        "v1_dynamic_topk": filter_scores_to_focus_industries(scores, memberships, v1_topk),
        "v1_dynamic_lagged_exit": filter_scores_to_focus_industries(scores, memberships, v1_lagged),
        "v2_hard_topk": filter_scores_to_focus_industries(scores, memberships, v2_topk),
        "v2_soft_weight": build_v2_soft_weight_scores(scores, memberships, diagnostics),
        "v2_risk_filter": build_v2_risk_filter_scores(scores, memberships, diagnostics),
    }
    summary_rows: list[dict[str, Any]] = []
    annual_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []
    results = {}
    for variant, variant_score in variant_scores.items():
        result = run_vectorized_topn_backtest(
            variant_score,
            prices[["trade_date", "asset_id", "close"]],
            VectorizedTopNConfig(
                start_date=start,
                end_date=end,
                top_n=top_n,
                rebalance_frequency="daily",
                transaction_cost_bps=transaction_cost_bps,
            ),
        )
        results[variant] = result
        metrics = calc_performance_metrics(result.equity_curve, result.positions)
        annual = _period_metrics(result.equity_curve, variant=variant, period="Y")
        monthly = _period_metrics(result.equity_curve, variant=variant, period="M")
        annual_rows.extend(annual.to_dict("records"))
        monthly_rows.extend(monthly.to_dict("records"))
        row = summarize_variant_result(
            variant=variant,
            transaction_cost_bps=transaction_cost_bps,
            score_rows=len(variant_score),
            position_rows=len(result.positions),
            trade_rows=len(result.trades),
            result_summary=metrics,
        )
        row.update(_industry_exposure_metrics(result.positions, memberships))
        row["monthly_win_rate"] = (
            float((monthly["period_return"] > 0).mean()) if not monthly.empty else None
        )
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows)
    annual_metrics = pd.DataFrame(annual_rows)
    monthly_metrics = pd.DataFrame(monthly_rows)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": str(output / "industry_focus_score_v2_backtest_summary.csv"),
        "annual_metrics": str(output / "industry_focus_score_v2_backtest_annual_metrics.csv"),
        "monthly_metrics": str(output / "industry_focus_score_v2_backtest_monthly_metrics.csv"),
    }
    summary.to_csv(paths["summary"], index=False)
    annual_metrics.to_csv(paths["annual_metrics"], index=False)
    monthly_metrics.to_csv(paths["monthly_metrics"], index=False)
    return {
        "paths": paths,
        "summary": summary,
        "annual_metrics": annual_metrics,
        "monthly_metrics": monthly_metrics,
        "results": results,
    }


def load_research_inputs(
    *,
    start_date: str,
    end_date: str,
    lookback_days: int,
    forward_days: int,
    industry_system: str,
    industry_level: int,
    adjust_type: str,
    service: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    price_start = (pd.Timestamp(start_date) - pd.Timedelta(days=lookback_days)).date().isoformat()
    price_end = (pd.Timestamp(end_date) + pd.Timedelta(days=forward_days)).date().isoformat()
    prices = load_prices(start_date=price_start, end_date=price_end, adjust_type=adjust_type, service=service)
    memberships = load_industry_memberships(
        start_date=price_start,
        end_date=price_end,
        industry_system=industry_system,
        industry_level=industry_level,
        service=service,
    )
    stock_scores = load_stock_scores(start_date=start_date, end_date=end_date, service=service)
    return prices, memberships, stock_scores


def load_industry_membership_intervals(
    *,
    industry_system: str = "csrc",
    industry_level: int = 1,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT asset_id, industry_name, start_date, end_date
    FROM core.industry_membership
    WHERE industry_system = %s
      AND level = %s
    ORDER BY asset_id, start_date
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [industry_system, industry_level]))


def build_industry_diagnostic_panel(
    *,
    prices: pd.DataFrame,
    memberships: pd.DataFrame,
    stock_scores: pd.DataFrame,
    min_industry_stocks: int,
    short_window: int = 5,
    medium_window: int = 10,
    long_window: int = 20,
    forward_window: int = 20,
) -> pd.DataFrame:
    merged = _merge_price_membership(prices, memberships)
    if merged.empty:
        return pd.DataFrame()
    stock_metrics = _stock_metrics(
        merged,
        short_window=short_window,
        medium_window=medium_window,
        long_window=long_window,
        forward_window=forward_window,
    )
    industry = _industry_metrics(stock_metrics, min_industry_stocks=min_industry_stocks)
    density = build_candidate_density(stock_scores, memberships)
    concentration = build_return_concentration(
        stock_metrics[["trade_date", "industry_name", "asset_id", "ret_20d"]]
    )
    result = industry.merge(density, on=["trade_date", "industry_name"], how="left")
    result = result.merge(concentration, on=["trade_date", "industry_name"], how="left")
    for col in [
        "top20_stock_count",
        "top50_stock_count",
        "top100_stock_count",
        "top20_density",
        "top50_density",
        "top100_density",
        "industry_member_count",
        "industry_return_concentration_top3",
        "concentration_penalty",
    ]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0.0)
    result["industry_forward_20d_rank"] = result.groupby("trade_date")[
        "industry_forward_20d_return"
    ].rank(method="average", ascending=False)
    return result


def build_v2_soft_weight_scores(
    scores: pd.DataFrame,
    memberships: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    joined = _scores_with_industry_and_diag(scores, memberships, diagnostics)
    score_rank = joined.groupby("trade_date")["industry_focus_score_v2"].rank(pct=True)
    industry_weight = ((score_rank - 0.5) * 0.40).clip(-0.10, 0.30).fillna(0.0)
    joined["score_total"] = joined["score_total"] * (1.0 + industry_weight)
    return _normalize_scores(joined[["trade_date", "asset_id", "score_total"]])


def build_v2_risk_filter_scores(
    scores: pd.DataFrame,
    memberships: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    joined = _scores_with_industry_and_diag(scores, memberships, diagnostics)
    filtered = joined[
        (joined["industry_focus_score_v2"] >= joined.groupby("trade_date")["industry_focus_score_v2"].transform("quantile", 0.25))
        & (joined["overheat_penalty"] <= 0.85)
    ].copy()
    return _normalize_scores(filtered[["trade_date", "asset_id", "score_total"]])


def add_diagnosis_tags(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    tags = []
    for row in result.to_dict("records"):
        if row.get("overheat_flag"):
            tags.append("overheat")
        elif row.get("industry_return_concentration_top3", 0) > 0.65:
            tags.append("narrow_leader_only")
        elif row.get("industry_amount_share_change_5d_vs_20d", 0) > 0.25 and row.get("trend_persistence_score", 0) < 0.5:
            tags.append("amount_spike_not_sustained")
        elif row.get("selected_by_v1_topk") and row.get("future_20d_rank", 999) > 10:
            tags.append("possible_chasing")
        elif row.get("breadth_expansion_score", 0) > 0.7 and row.get("trend_persistence_score", 0) > 0.7:
            tags.append("sustained_mainline")
        elif row.get("breadth_expansion_score", 0) > 0.6:
            tags.append("broad_strength")
        else:
            tags.append("neutral")
    result["diagnosis_tag"] = tags
    return result


def _stock_metrics(
    frame: pd.DataFrame,
    *,
    short_window: int,
    medium_window: int,
    long_window: int,
    forward_window: int,
) -> pd.DataFrame:
    data = frame.sort_values(["asset_id", "trade_date"]).copy()
    grouped = data.groupby("asset_id", group_keys=False)
    data["ret_5d"] = grouped["close"].pct_change(short_window)
    data["ret_10d"] = grouped["close"].pct_change(medium_window)
    data["ret_20d"] = grouped["close"].pct_change(long_window)
    data["forward_20d_return"] = grouped["close"].shift(-forward_window) / data["close"] - 1.0
    data["ma20"] = grouped["close"].transform(lambda s: s.rolling(long_window, min_periods=1).mean())
    data["distance_ma20"] = data["close"] / data["ma20"].replace(0, pd.NA) - 1.0
    data["amount_5d"] = grouped["amount"].transform(lambda s: s.rolling(short_window, min_periods=1).mean())
    data["amount_20d"] = grouped["amount"].transform(lambda s: s.rolling(long_window, min_periods=1).mean())
    return data


def _industry_metrics(stock_metrics: pd.DataFrame, *, min_industry_stocks: int) -> pd.DataFrame:
    data = stock_metrics.copy()
    market = data.groupby("trade_date", as_index=False).agg(
        market_ret_5d=("ret_5d", "mean"),
        market_ret_10d=("ret_10d", "mean"),
        market_ret_20d=("ret_20d", "mean"),
        market_forward_20d=("forward_20d_return", "mean"),
        market_amount=("amount", "sum"),
    )
    data = data.merge(market, on="trade_date", how="left")
    data["excess_20d"] = data["ret_20d"] - data["market_ret_20d"]
    data["up_20d"] = data["ret_20d"] > 0
    data["excess_up_20d"] = data["excess_20d"] > 0
    data["amount_share"] = data["amount"] / data["market_amount"].replace(0, pd.NA)
    grouped = data.groupby(["trade_date", "industry_name"], as_index=False)
    result = grouped.agg(
        industry_member_count=("asset_id", "nunique"),
        industry_ret_5d=("ret_5d", "mean"),
        industry_ret_10d=("ret_10d", "mean"),
        industry_ret_20d=("ret_20d", "mean"),
        industry_forward_20d_return=("forward_20d_return", "mean"),
        industry_amount_share=("amount_share", "sum"),
        industry_distance_ma20=("distance_ma20", "mean"),
        up_ratio_20d=("up_20d", "mean"),
        excess_up_ratio_20d=("excess_up_20d", "mean"),
        industry_volatility_20d=("ret_20d", "std"),
    )
    result = result[result["industry_member_count"] >= min_industry_stocks].copy()
    result = result.merge(
        market[["trade_date", "market_ret_5d", "market_ret_10d", "market_ret_20d", "market_forward_20d"]],
        on="trade_date",
        how="left",
    )
    result["industry_excess_ret_5d"] = result["industry_ret_5d"] - result["market_ret_5d"]
    result["industry_excess_ret_10d"] = result["industry_ret_10d"] - result["market_ret_10d"]
    result["industry_excess_ret_20d"] = result["industry_ret_20d"] - result["market_ret_20d"]
    result["industry_forward_20d_excess_return"] = (
        result["industry_forward_20d_return"] - result["market_forward_20d"]
    )
    result = result.sort_values(["industry_name", "trade_date"])
    result["industry_amount_share_5d"] = result.groupby("industry_name")["industry_amount_share"].transform(
        lambda s: s.rolling(5, min_periods=1).mean()
    )
    result["industry_amount_share_20d"] = result.groupby("industry_name")["industry_amount_share"].transform(
        lambda s: s.rolling(20, min_periods=1).mean()
    )
    result["industry_amount_share_change_5d_vs_20d"] = (
        result["industry_amount_share_5d"] / result["industry_amount_share_20d"].replace(0, pd.NA) - 1.0
    )
    result["industry_amount_share_5d_percentile_60d"] = result.groupby("industry_name")[
        "industry_amount_share_5d"
    ].transform(lambda s: s.rolling(60, min_periods=1).rank(pct=True).iloc[:, 0] if False else s.expanding().rank(pct=True))
    result["top_rank_days_20d"] = _top_rank_days(result, "industry_excess_ret_20d", window=20)
    result["industry_forward_20d_max_drawdown"] = result["industry_forward_20d_return"].clip(upper=0)
    result = _leader_middle_metrics(result, data)
    return result.drop(
        columns=["market_ret_5d", "market_ret_10d", "market_ret_20d", "market_forward_20d"],
        errors="ignore",
    )


def _leader_middle_metrics(industry_frame: pd.DataFrame, stock_frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (trade_date, industry_name), group in stock_frame.groupby(["trade_date", "industry_name"]):
        ordered = group.sort_values("ret_20d", ascending=False)
        leader = ordered.head(5)["ret_20d"].mean()
        middle = ordered.iloc[5:20]["ret_20d"].mean()
        rows.append(
            {
                "trade_date": trade_date,
                "industry_name": industry_name,
                "leader_ret_20d": leader,
                "middle_ret_20d": middle,
                "leader_to_middle_ratio": leader / middle if pd.notna(middle) and abs(middle) > 1e-9 else 999.0,
            }
        )
    return industry_frame.merge(pd.DataFrame(rows), on=["trade_date", "industry_name"], how="left")


def _rank_component(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series(0.0, index=frame.index)
    weight = 1.0 / len(columns)
    temp = frame.copy()
    for col in columns:
        if col not in temp.columns:
            temp[col] = 0.0
        temp = rank_by_date(temp, value_col=col, output_col=f"{col}_component_rank", ascending=True)
        result = result + weight * pd.to_numeric(temp[f"{col}_component_rank"], errors="coerce").fillna(0.0)
    return result


def _leader_middle_score(frame: pd.DataFrame) -> pd.Series:
    temp = frame.copy()
    if "middle_ret_20d" not in temp.columns:
        temp["middle_ret_20d"] = 0.0
    if "leader_to_middle_ratio" not in temp.columns:
        temp["leader_to_middle_ratio"] = 1.0
    temp = rank_by_date(temp, value_col="middle_ret_20d", output_col="middle_ret_rank", ascending=True)
    temp["ratio_penalty"] = (pd.to_numeric(temp["leader_to_middle_ratio"], errors="coerce") - 1.0).clip(lower=0)
    temp = rank_by_date(temp, value_col="ratio_penalty", output_col="ratio_penalty_rank", ascending=False)
    return 0.70 * temp["middle_ret_rank"].fillna(0.0) + 0.30 * temp["ratio_penalty_rank"].fillna(0.0)


def _risk_adjusted_score(frame: pd.DataFrame) -> pd.Series:
    temp = frame.copy()
    if "industry_ret_20d" not in temp.columns:
        temp["industry_ret_20d"] = 0.0
    if "industry_volatility_20d" not in temp.columns:
        temp["industry_volatility_20d"] = 0.0
    temp["risk_adjusted_strength"] = temp["industry_ret_20d"] / (
        pd.to_numeric(temp["industry_volatility_20d"], errors="coerce").abs() + 1e-6
    )
    temp = rank_by_date(temp, value_col="risk_adjusted_strength", output_col="risk_adjusted_rank", ascending=True)
    return temp["risk_adjusted_rank"].fillna(0.0)


def _top_rank_days(frame: pd.DataFrame, value_col: str, *, window: int) -> pd.Series:
    ranked = rank_by_date(frame, value_col=value_col, output_col="tmp_rank", ascending=True)
    ranked["in_top_group"] = ranked["tmp_rank"] >= 0.75
    return ranked.groupby("industry_name")["in_top_group"].transform(
        lambda s: s.rolling(window, min_periods=1).sum()
    )


def _select_v2_topk(scored: pd.DataFrame, *, top_k: int) -> pd.DataFrame:
    ranked = scored.sort_values(
        ["trade_date", "industry_focus_score_v2", "industry_name"],
        ascending=[True, False, True],
    ).copy()
    ranked["focus_rank"] = ranked.groupby("trade_date").cumcount() + 1
    return ranked[ranked["focus_rank"] <= top_k][
        ["trade_date", "industry_name", "industry_focus_score_v2"]
    ].rename(columns={"industry_focus_score_v2": "industry_focus_score"})


def _add_selection_flags(frame: pd.DataFrame, selected: pd.DataFrame, flag_col: str) -> pd.DataFrame:
    result = frame.copy()
    if selected.empty:
        result[flag_col] = False
        return result
    selection = selected[["trade_date", "industry_name"]].drop_duplicates().assign(**{flag_col: True})
    result = result.merge(selection, on=["trade_date", "industry_name"], how="left")
    result[flag_col] = result[flag_col].fillna(False).astype(bool)
    return result


def _v1_failure_attribution(scored: pd.DataFrame) -> pd.DataFrame:
    result = scored.copy()
    result["trade_date"] = result["trade_date"].map(_iso_date)
    result["rebalance_date"] = result["trade_date"]
    result["rebalance_month"] = pd.to_datetime(result["trade_date"]).dt.to_period("M").astype(str)
    result["reason_tag"] = result.get("diagnosis_tag", "neutral")
    columns = [
        "rebalance_month",
        "trade_date",
        "rebalance_date",
        "industry_name",
        "selected_by_v1_topk",
        "selected_by_v1_lagged_exit",
        "v1_score",
        "industry_forward_20d_return",
        "industry_forward_20d_rank",
        "industry_forward_20d_excess_return",
        "industry_forward_20d_max_drawdown",
        "industry_amount_share_5d",
        "industry_amount_share_20d",
        "industry_amount_share_change_5d_vs_20d",
        "top20_stock_count",
        "top50_stock_count",
        "top100_stock_count",
        "top20_density",
        "top50_density",
        "top100_density",
        "industry_member_count",
        "industry_return_concentration_top3",
        "overheat_flag",
        "reason_tag",
    ]
    return result.reindex(columns=columns).sort_values(["rebalance_date", "industry_name"])


def _scores_with_industry_and_diag(
    scores: pd.DataFrame,
    memberships: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    score_frame = _normalize_scores(scores)
    members = _normalize_daily_memberships(memberships)
    diag = diagnostics.copy().rename(columns={"rebalance_date": "trade_date"})
    joined = score_frame.merge(
        members[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    return joined.merge(
        diag[["trade_date", "industry_name", "industry_focus_score_v2", "overheat_penalty"]],
        on=["trade_date", "industry_name"],
        how="left",
    )


def _industry_exposure_metrics(positions: pd.DataFrame, memberships: pd.DataFrame) -> dict[str, Any]:
    if positions.empty:
        return {
            "avg_holding_industry_count": None,
            "max_single_industry_weight": None,
            "avg_top3_industry_weight": None,
        }
    pos = positions.rename(columns={"rebalance_date": "trade_date"}).copy()
    pos["trade_date"] = pos["trade_date"].map(_iso_date)
    members = _normalize_daily_memberships(memberships)
    joined = pos.merge(members, on=["trade_date", "asset_id"], how="left")
    industry_weights = joined.groupby(["trade_date", "industry_name"], as_index=False)["weight"].sum()
    daily = industry_weights.groupby("trade_date").agg(
        industry_count=("industry_name", "nunique"),
        max_industry_weight=("weight", "max"),
        top3_industry_weight=("weight", lambda s: s.sort_values(ascending=False).head(3).sum()),
    )
    return {
        "avg_holding_industry_count": float(daily["industry_count"].mean()),
        "max_single_industry_weight": float(daily["max_industry_weight"].max()),
        "avg_top3_industry_weight": float(daily["top3_industry_weight"].mean()),
    }


def _period_metrics(equity_curve: pd.DataFrame, *, variant: str, period: str) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame(columns=["variant", "period", "period_return", "period_max_drawdown"])
    frame = equity_curve.copy()
    frame["period"] = pd.to_datetime(frame["date"]).dt.to_period(period).astype(str)
    rows = []
    for period_label, group in frame.groupby("period", sort=True):
        period_return = float((1.0 + pd.to_numeric(group["net_return"], errors="coerce").fillna(0.0)).prod() - 1.0)
        period_equity = (1.0 + pd.to_numeric(group["net_return"], errors="coerce").fillna(0.0)).cumprod()
        period_drawdown = period_equity / period_equity.cummax() - 1.0
        rows.append(
            {
                "variant": variant,
                "period": period_label,
                "period_return": period_return,
                "period_max_drawdown": float(period_drawdown.min()),
            }
        )
    return pd.DataFrame(rows)


def _normalize_scores(scores: pd.DataFrame) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total"])
    frame = scores.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["score_total"] = pd.to_numeric(frame["score_total"], errors="coerce")
    frame = frame.dropna(subset=["score_total"])
    frame = frame.sort_values(["trade_date", "score_total", "asset_id"], ascending=[True, False, True])
    frame["rank"] = frame.groupby("trade_date").cumcount() + 1
    return frame.reset_index(drop=True)


def _normalize_daily_memberships(memberships: pd.DataFrame) -> pd.DataFrame:
    if memberships.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "industry_name"])
    frame = memberships.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["industry_name"] = frame["industry_name"].astype(str)
    return (
        frame[["trade_date", "asset_id", "industry_name"]]
        .drop_duplicates()
        .sort_values(["trade_date", "asset_id", "industry_name"])
        .drop_duplicates(["trade_date", "asset_id"], keep="first")
        .reset_index(drop=True)
    )


def _merge_price_membership(prices: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    price_frame = prices.copy()
    price_frame["trade_date"] = price_frame["trade_date"].map(_iso_date)
    price_frame["asset_id"] = price_frame["asset_id"].astype(str)
    price_frame["close"] = pd.to_numeric(price_frame["close"], errors="coerce")
    price_frame["amount"] = pd.to_numeric(price_frame.get("amount", 0.0), errors="coerce")
    return price_frame.merge(
        _normalize_daily_memberships(memberships),
        on=["trade_date", "asset_id"],
        how="inner",
    ).dropna(subset=["close", "industry_name"])
