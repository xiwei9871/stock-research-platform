from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.industry_focus_score import (
    FIXED_FOCUS_INDUSTRIES,
    VectorizedTopNConfig,
    filter_scores_to_focus_industries,
    load_industry_memberships,
    load_prices,
    load_stock_scores,
    run_vectorized_topn_backtest,
    select_fixed_focus,
)


ERROR_AUDIT_COLUMNS = [
    "rebalance_month",
    "rebalance_date",
    "method",
    "industry_name",
    "selected_or_affected",
    "industry_focus_score_v2",
    "v1_score",
    "future_20d_return",
    "future_20d_rank",
    "future_20d_excess_return",
    "future_20d_max_drawdown",
    "diagnosis_tag",
    "trend_persistence_score",
    "amount_share_score",
    "candidate_density_score",
    "breadth_expansion_score",
    "leader_to_middle_expansion_score",
    "overheat_penalty",
    "concentration_penalty",
    "error_type",
]

COMPONENTS = [
    "trend_persistence_score",
    "amount_share_score",
    "candidate_density_score",
    "breadth_expansion_score",
    "leader_to_middle_expansion_score",
    "overheat_penalty",
    "concentration_penalty",
    "industry_focus_score_v2",
]


def run_fixed_industry_reconciliation(
    *,
    start_date: object,
    end_date: object,
    output_dir: str | Path = Path("/Users/xiwei/stock_research/outputs/research"),
    top_n: int = 20,
    transaction_cost_bps: float = 20.0,
    industry_system: str = "csrc",
    industry_level: int = 1,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    scores = load_stock_scores(start_date=start, end_date=end, service=service)
    prices = load_prices(start_date=start, end_date=end, adjust_type=adjust_type, service=service)
    raw_duplicate_counts = load_raw_daily_industry_membership_duplicate_counts(
        start_date=start,
        end_date=end,
        industry_system=industry_system,
        industry_level=industry_level,
        adjust_type=adjust_type,
        service=service,
    )
    dedup_memberships = _normalize_audit_memberships(load_industry_memberships(
        start_date=start,
        end_date=end,
        industry_system=industry_system,
        industry_level=industry_level,
        service=service,
    ))
    if not raw_duplicate_counts.empty:
        raw_duplicate_counts["trade_date"] = raw_duplicate_counts["trade_date"].map(_iso_date)
        raw_duplicate_counts["duplicated_membership_count"] = pd.to_numeric(
            raw_duplicate_counts["duplicated_membership_count"],
            errors="coerce",
        ).fillna(0).astype(int)
    focus = select_fixed_focus(
        trade_dates=sorted(scores["trade_date"].astype(str).unique().tolist()),
        focus_industries=FIXED_FOCUS_INDUSTRIES,
    )
    filtered = filter_scores_to_focus_industries(scores, dedup_memberships, focus)
    result = run_vectorized_topn_backtest(
        filtered,
        prices[["trade_date", "asset_id", "close"]],
        VectorizedTopNConfig(
            start_date=start,
            end_date=end,
            top_n=top_n,
            rebalance_frequency="daily",
            transaction_cost_bps=transaction_cost_bps,
        ),
    )
    duplicated = raw_duplicate_counts.set_index("trade_date")["duplicated_membership_count"]
    trading_dates = sorted(prices["trade_date"].map(_iso_date).unique().tolist())
    next_date_by_rebalance = {
        trade_date: trading_dates[index + 1]
        for index, trade_date in enumerate(trading_dates[:-1])
    }
    positions = result.positions.copy()
    positions["rebalance_date"] = positions["rebalance_date"].map(_iso_date)
    positions["return_date"] = positions["rebalance_date"].map(next_date_by_rebalance)
    industry_weights = positions.merge(
        dedup_memberships[["trade_date", "asset_id", "industry_name"]],
        left_on=["rebalance_date", "asset_id"],
        right_on=["trade_date", "asset_id"],
        how="left",
    ).groupby(["return_date", "industry_name"], as_index=False)["weight"].sum()
    top_weight = industry_weights.groupby("return_date")["weight"].max().rename("top_industry_weight")
    selected_count = positions.groupby("return_date")["asset_id"].nunique().rename("selected_stock_count")
    equity = result.equity_curve.rename(columns={"date": "rebalance_date"}).copy()
    equity["rebalance_date"] = equity["rebalance_date"].map(_iso_date)
    rows = equity.merge(selected_count, left_on="rebalance_date", right_index=True, how="left")
    rows = rows.merge(duplicated.rename("duplicated_membership_count"), left_on="rebalance_date", right_index=True, how="left")
    rows = rows.merge(top_weight, left_on="rebalance_date", right_index=True, how="left")
    rows["rebalance_month"] = pd.to_datetime(rows["rebalance_date"]).dt.to_period("M").astype(str)
    rows["portfolio_return_after_cost"] = rows["net_return"]
    rows["cumulative_return"] = rows["equity"] - 1.0
    rows["duplicated_membership_count"] = rows["duplicated_membership_count"].fillna(0).astype(int)
    rows["selected_stock_count"] = rows["selected_stock_count"].fillna(0).astype(int)
    rows["notes"] = rows["duplicated_membership_count"].map(
        lambda value: "raw_membership_duplicates_present" if value else "new_membership_logic_one_industry_per_asset_date"
    )
    reconciliation = rows[
        [
            "rebalance_month",
            "rebalance_date",
            "selected_stock_count",
            "duplicated_membership_count",
            "portfolio_return_after_cost",
            "cumulative_return",
            "drawdown",
            "top_industry_weight",
            "notes",
        ]
    ]
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "fixed_industry_backtest_reconciliation.csv"
    reconciliation.to_csv(path, index=False)
    explanation = _fixed_reconciliation_explanation(
        reconciliation,
        raw_duplicate_counts,
        dedup_memberships,
    )
    return {"paths": {"reconciliation": str(path)}, "reconciliation": reconciliation, "explanation": explanation}


def load_raw_daily_industry_membership_duplicate_counts(
    *,
    start_date: str,
    end_date: str,
    industry_system: str,
    industry_level: int,
    adjust_type: str,
    service: str,
) -> pd.DataFrame:
    sql = """
    WITH raw_memberships AS (
        SELECT b.trade_date, b.asset_id, count(*) AS membership_count
        FROM market_daily_bar b
        JOIN core.industry_membership m
          ON m.asset_id = b.asset_id
         AND m.industry_system = %s
         AND m.level = %s
         AND m.start_date <= b.trade_date
         AND (m.end_date IS NULL OR m.end_date >= b.trade_date)
        WHERE b.adjust_type = %s
          AND b.trade_date BETWEEN %s AND %s
        GROUP BY b.trade_date, b.asset_id
    )
    SELECT trade_date, count(*) AS duplicated_membership_count
    FROM raw_memberships
    WHERE membership_count > 1
    GROUP BY trade_date
    ORDER BY trade_date
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [industry_system, industry_level, adjust_type, start_date, end_date]))


def _normalize_audit_memberships(memberships: pd.DataFrame) -> pd.DataFrame:
    if memberships.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "industry_name"])
    frame = memberships.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["industry_name"] = frame["industry_name"].astype(str)
    return (
        frame.dropna(subset=["industry_name"])
        .sort_values(["trade_date", "asset_id", "industry_name"])
        .drop_duplicates(["trade_date", "asset_id"], keep="first")
        .reset_index(drop=True)
    )


def build_error_audit_monthly(diagnostics: pd.DataFrame) -> pd.DataFrame:
    diag = _normalize_diagnostics(diagnostics)
    method_specs = [
        ("v1_topk", "selected_by_v1_topk"),
        ("v1_lagged_exit", "selected_by_v1_lagged_exit"),
        ("v2_topk", "selected_by_v2_topk"),
    ]
    rows: list[dict[str, Any]] = []
    for method, flag in method_specs:
        selected = diag[diag[flag]].copy()
        for row in selected.to_dict("records"):
            for error_type in classify_error_types(row, selected_or_affected=True):
                rows.append(_audit_row(row, method, True, error_type))
    soft = diag[diag["industry_focus_score_v2"] > 0].copy()
    for row in soft.to_dict("records"):
        for error_type in classify_error_types(row, selected_or_affected=True):
            rows.append(_audit_row(row, "v2_soft_weight_positive", True, error_type))
    removed = diag[(diag["industry_focus_score_v2"] < diag.groupby("rebalance_date")["industry_focus_score_v2"].transform("quantile", 0.25)) | (diag["overheat_penalty"] > 0.85)]
    for row in removed.to_dict("records"):
        for error_type in classify_error_types(row, selected_or_affected=True):
            rows.append(_audit_row(row, "v2_risk_filter_removed", True, error_type))
    missed = diag[(~diag["selected_by_v1_topk"]) & (~diag["selected_by_v2_topk"]) & (diag["future_20d_rank"] <= 5)]
    for row in missed.to_dict("records"):
        rows.append(_audit_row(row, "missed_by_v1_v2", False, "missed_strong_industry"))
    if not rows:
        return pd.DataFrame(columns=ERROR_AUDIT_COLUMNS)
    return pd.DataFrame(rows).reindex(columns=ERROR_AUDIT_COLUMNS)


def classify_error_types(row: dict[str, Any], *, selected_or_affected: bool) -> list[str]:
    tags: list[str] = []
    future_return = _float(row.get("future_20d_return"))
    future_excess = _float(row.get("future_20d_excess_return"))
    future_rank = _float(row.get("future_20d_rank"))
    max_drawdown = _float(row.get("future_20d_max_drawdown"))
    diagnosis = str(row.get("diagnosis_tag", ""))
    if selected_or_affected and future_excess < 0:
        tags.append("selected_weak_future_return")
    if selected_or_affected and max_drawdown <= -0.15:
        tags.append("selected_high_drawdown")
    if (not selected_or_affected) and future_rank <= 5:
        tags.append("missed_strong_industry")
    if "overheat" in diagnosis and future_excess < 0:
        tags.append("chasing_after_overheat")
    if "narrow_leader_only" in diagnosis and future_excess < 0:
        tags.append("narrow_leader_trap")
    if "amount_spike_not_sustained" in diagnosis and future_excess < 0:
        tags.append("amount_spike_trap")
    if "sustained_mainline" in diagnosis and future_return > 0 and future_excess > 0:
        tags.append("true_positive_mainline")
    if "broad_strength" in diagnosis and future_excess < 0:
        tags.append("false_positive_mainline")
    return tags or ["neutral"]


def build_error_summary(error_audit: pd.DataFrame) -> pd.DataFrame:
    if error_audit.empty:
        return pd.DataFrame(columns=["error_type", "event_count"])
    return (
        error_audit.groupby("error_type", as_index=False)
        .size()
        .rename(columns={"size": "event_count"})
        .sort_values("event_count", ascending=False)
    )


def build_diagnosis_tag_effectiveness(diagnostics: pd.DataFrame) -> pd.DataFrame:
    diag = _normalize_diagnostics(diagnostics)
    if diag.empty:
        return pd.DataFrame()
    grouped = diag.groupby("diagnosis_tag")
    result = grouped.agg(
        sample_count=("industry_name", "size"),
        avg_future_20d_return=("future_20d_return", "mean"),
        median_future_20d_return=("future_20d_return", "median"),
        avg_future_20d_excess_return=("future_20d_excess_return", "mean"),
        win_rate_vs_market=("future_20d_excess_return", lambda s: float((s > 0).mean())),
        avg_future_20d_rank=("future_20d_rank", "mean"),
        avg_future_20d_max_drawdown=("future_20d_max_drawdown", "mean"),
        selected_by_v1_topk_count=("selected_by_v1_topk", "sum"),
        selected_by_v2_topk_count=("selected_by_v2_topk", "sum"),
    ).reset_index()
    return result.sort_values("sample_count", ascending=False)


def build_component_effectiveness(diagnostics: pd.DataFrame, *, buckets: int = 5) -> pd.DataFrame:
    diag = _normalize_diagnostics(diagnostics)
    rows: list[dict[str, Any]] = []
    for component in COMPONENTS:
        if component not in diag.columns:
            continue
        temp = diag.dropna(subset=[component, "future_20d_return"]).copy()
        if temp.empty:
            continue
        bucket_count = min(buckets, temp[component].nunique())
        if bucket_count <= 1:
            temp["quantile_bucket"] = 1
        else:
            temp["quantile_bucket"] = pd.qcut(
                temp[component].rank(method="first"),
                q=bucket_count,
                labels=False,
            ) + 1
        quality = _component_signal_quality(temp, component)
        grouped = temp.groupby("quantile_bucket")
        part = grouped.agg(
            sample_count=("industry_name", "size"),
            avg_future_20d_return=("future_20d_return", "mean"),
            median_future_20d_return=("future_20d_return", "median"),
            avg_future_20d_excess_return=("future_20d_excess_return", "mean"),
            win_rate_vs_market=("future_20d_excess_return", lambda s: float((s > 0).mean())),
            avg_future_20d_rank=("future_20d_rank", "mean"),
            avg_future_20d_max_drawdown=("future_20d_max_drawdown", "mean"),
        ).reset_index()
        part["component_name"] = component
        part["signal_quality"] = quality
        rows.extend(part.to_dict("records"))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)[
        [
            "component_name",
            "quantile_bucket",
            "sample_count",
            "avg_future_20d_return",
            "median_future_20d_return",
            "avg_future_20d_excess_return",
            "win_rate_vs_market",
            "avg_future_20d_rank",
            "avg_future_20d_max_drawdown",
            "signal_quality",
        ]
    ]


def run_industry_error_audit(
    *,
    diagnostics_path: str | Path,
    start_date: object,
    end_date: object,
    output_dir: str | Path = Path("/Users/xiwei/stock_research/outputs/research"),
    backtest_summary_path: str | Path | None = None,
    annual_metrics_path: str | Path | None = None,
) -> dict[str, Any]:
    diag = pd.read_csv(diagnostics_path)
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    diag = diag[(diag["rebalance_date"].astype(str) >= start) & (diag["rebalance_date"].astype(str) <= end)].copy()
    error_audit = build_error_audit_monthly(diag)
    error_summary = build_error_summary(error_audit)
    tag_effectiveness = build_diagnosis_tag_effectiveness(diag)
    component_effectiveness = build_component_effectiveness(diag)
    backtest_summary = _read_optional_csv(backtest_summary_path)
    annual_metrics = _read_optional_csv(annual_metrics_path)
    yearly = build_yearly_diagnosis(
        annual_metrics=annual_metrics,
        error_audit=error_audit,
        component_effectiveness=component_effectiveness,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "monthly": str(output / "industry_error_audit_monthly.csv"),
        "summary": str(output / "industry_error_audit_summary.csv"),
        "tag_effectiveness": str(output / "industry_diagnosis_tag_effectiveness.csv"),
        "component_effectiveness": str(output / "industry_v2_component_effectiveness.csv"),
        "yearly": str(output / "industry_factor_yearly_diagnosis.csv"),
    }
    error_audit.to_csv(paths["monthly"], index=False)
    error_summary.to_csv(paths["summary"], index=False)
    tag_effectiveness.to_csv(paths["tag_effectiveness"], index=False)
    component_effectiveness.to_csv(paths["component_effectiveness"], index=False)
    yearly.to_csv(paths["yearly"], index=False)
    report_paths = write_industry_factor_audit_report(
        output_dir=output,
        backtest_summary=backtest_summary,
        reconciliation=_read_optional_csv(output / "fixed_industry_backtest_reconciliation.csv"),
        error_summary=error_summary,
        tag_effectiveness=tag_effectiveness,
        component_effectiveness=component_effectiveness,
        yearly_diagnosis=yearly,
    )
    paths.update(report_paths)
    return {
        "paths": paths,
        "monthly": error_audit,
        "summary": error_summary,
        "tag_effectiveness": tag_effectiveness,
        "component_effectiveness": component_effectiveness,
        "yearly": yearly,
    }


def build_yearly_diagnosis(
    *,
    annual_metrics: pd.DataFrame,
    error_audit: pd.DataFrame,
    component_effectiveness: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not annual_metrics.empty:
        annual = annual_metrics.copy().rename(columns={"period": "year"})
        for row in annual.to_dict("records"):
            rows.append(row)
    if not error_audit.empty:
        temp = error_audit.copy()
        temp["year"] = pd.to_datetime(temp["rebalance_date"]).dt.year.astype(str)
        counts = temp.groupby(["year", "error_type"], as_index=False).size().rename(columns={"size": "event_count"})
        for row in counts.to_dict("records"):
            rows.append({"year": row["year"], "diagnostic_metric": row["error_type"], "event_count": row["event_count"]})
    if not component_effectiveness.empty:
        counts = component_effectiveness.groupby("signal_quality", as_index=False)["component_name"].nunique()
        for year in sorted({str(row.get("year")) for row in rows if row.get("year") is not None} or ["all"]):
            for row in counts.to_dict("records"):
                rows.append(
                    {
                        "year": year,
                        "diagnostic_metric": f"component_{row['signal_quality']}",
                        "event_count": int(row["component_name"]),
                    }
                )
    return pd.DataFrame(rows)


def write_industry_factor_audit_report(
    *,
    output_dir: str | Path,
    backtest_summary: pd.DataFrame,
    reconciliation: pd.DataFrame,
    error_summary: pd.DataFrame,
    tag_effectiveness: pd.DataFrame,
    component_effectiveness: pd.DataFrame,
    yearly_diagnosis: pd.DataFrame,
) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "industry_factor_audit_report.md"
    lines = [
        "# 行业因子失败归因审计报告",
        "",
        "## 1. 研究背景",
        "固定三板块用于解释 2026 主线，V1/V2 用于研究 point-in-time 行业识别能力。本报告只做失败归因和指标有效性检验，不做收益调参。",
        "",
        "## 2. 当前回测结论",
        _table_or_empty(backtest_summary),
        "",
        "## 3. 固定三板块结果口径复核",
        _table_or_empty(reconciliation.tail(5) if not reconciliation.empty else reconciliation),
        "",
        "## 4. V1 失败原因",
        _table_or_empty(error_summary),
        "",
        "## 5. V2 诊断能力评估",
        _table_or_empty(component_effectiveness.groupby(["component_name", "signal_quality"], as_index=False).size() if not component_effectiveness.empty else component_effectiveness),
        "",
        "## 6. 诊断标签有效性",
        _table_or_empty(tag_effectiveness),
        "",
        "## 7. 当前不建议实盘使用的原因",
        "- V2 软加权仍弱于原始 Top20。",
        "- V2 风险过滤月度胜率偏低。",
        "- V2 硬 TopK 换手过高。",
        "- 行业因子仍会在 2024/2025 放大错误暴露。",
        "",
        "## 8. 下一轮改进方向",
        "- 重新定义主线持续性。",
        "- 降低短期动量权重。",
        "- 强化扩散质量。",
        "- 把行业因子从硬过滤改为风险约束。",
        "- 引入市场环境 regime 判断。",
        "- 检查行业分类粒度是否过粗。",
        "",
        "## 年度诊断",
        _table_or_empty(yearly_diagnosis),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"markdown_report": str(path)}


def _audit_row(row: dict[str, Any], method: str, selected: bool, error_type: str) -> dict[str, Any]:
    result = {col: row.get(col) for col in ERROR_AUDIT_COLUMNS}
    result["method"] = method
    result["selected_or_affected"] = bool(selected)
    result["error_type"] = error_type
    return result


def _normalize_diagnostics(diagnostics: pd.DataFrame) -> pd.DataFrame:
    diag = diagnostics.copy()
    if "rebalance_date" not in diag.columns and "trade_date" in diag.columns:
        diag["rebalance_date"] = diag["trade_date"]
    diag["rebalance_date"] = diag["rebalance_date"].map(_iso_date)
    if "rebalance_month" not in diag.columns:
        diag["rebalance_month"] = pd.to_datetime(diag["rebalance_date"]).dt.to_period("M").astype(str)
    for col in ["selected_by_v1_topk", "selected_by_v1_lagged_exit", "selected_by_v2_topk"]:
        if col not in diag.columns:
            diag[col] = False
        diag[col] = diag[col].fillna(False).astype(bool)
    numeric_cols = [
        "future_20d_return",
        "future_20d_rank",
        "future_20d_excess_return",
        "future_20d_max_drawdown",
        *COMPONENTS,
        "v1_score",
    ]
    for col in numeric_cols:
        if col not in diag.columns:
            diag[col] = 0.0
        diag[col] = pd.to_numeric(diag[col], errors="coerce")
    if "diagnosis_tag" not in diag.columns:
        diag["diagnosis_tag"] = "neutral"
    return diag


def _component_signal_quality(temp: pd.DataFrame, component: str) -> str:
    grouped = temp.groupby(pd.qcut(temp[component].rank(method="first"), q=min(5, temp[component].nunique()), labels=False, duplicates="drop"))["future_20d_return"].mean()
    if len(grouped) < 2:
        return "weak_signal"
    low = float(grouped.iloc[0])
    high = float(grouped.iloc[-1])
    penalty = component in {"overheat_penalty", "concentration_penalty"}
    diff = high - low
    if penalty:
        if diff < -0.01:
            return "useful_signal"
        if diff > 0.01:
            return "inverted_signal"
        return "weak_signal"
    if diff > 0.01:
        return "useful_signal"
    if diff < -0.01:
        return "inverted_signal"
    return "weak_signal"


def _fixed_reconciliation_explanation(
    reconciliation: pd.DataFrame,
    raw_duplicate_counts: pd.DataFrame,
    dedup_memberships: pd.DataFrame,
) -> str:
    final_return = float(reconciliation["cumulative_return"].iloc[-1]) if not reconciliation.empty else 0.0
    duplicate_rows = int(raw_duplicate_counts["duplicated_membership_count"].sum()) if not raw_duplicate_counts.empty else 0
    return (
        f"fixed industries={list(FIXED_FOCUS_INDUSTRIES)}; "
        "start=2024-05-27/end=2026-05-12 expected when called with default dates; "
        "daily Top20 equal-weight vectorized close-to-close with 20bps cost; "
        f"new_membership_logic final cumulative return={final_return:.4%}; "
        f"raw duplicated asset-date membership count={duplicate_rows}; "
        f"dedup rows={len(dedup_memberships)}."
    )


def _read_optional_csv(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def _table_or_empty(frame: pd.DataFrame) -> str:
    return frame.to_markdown(index=False) if not frame.empty else "No data."


def _float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
