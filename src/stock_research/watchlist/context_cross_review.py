from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


FUNDAMENTAL_FACTOR_NAMES = [
    "roe",
    "revenue_yoy",
    "np_yoy",
    "deduct_np_yoy",
    "np_parent_ttm",
    "debt_ratio",
    "ocf_to_np",
]
SHORT_METRICS = [
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_5d_max_drawdown",
]
STRONG_METRICS = [
    "future_5d_return",
    "future_10d_return",
    "future_20d_return",
    "future_30d_return",
    "future_60d_return",
    "future_20d_max_drawdown",
    "future_30d_max_drawdown",
    "future_60d_max_drawdown",
    "max_return_within_60d",
    "hit_double_within_60d",
]


def run_watchlist_context_cross_review(
    *,
    detail_path: str | Path,
    output_dir: str | Path,
    fundamental_context_path: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    detail = pd.read_csv(detail_path, low_memory=False)
    fundamentals = (
        pd.read_csv(fundamental_context_path, low_memory=False)
        if fundamental_context_path
        else load_fundamental_context_for_detail(detail, service=service)
    )
    return build_watchlist_context_cross_review_from_frames(
        detail=detail,
        fundamentals=fundamentals,
        output_dir=output_dir,
    )


def load_fundamental_context_for_detail(
    detail: pd.DataFrame,
    *,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    columns = ["trade_date", "asset_id", *FUNDAMENTAL_FACTOR_NAMES, "is_st"]
    if detail.empty or not {"trade_date", "asset_id"} <= set(detail.columns):
        return pd.DataFrame(columns=columns)
    trade_dates = sorted({str(value) for value in detail["trade_date"].dropna().unique()})
    asset_ids = sorted({str(value) for value in detail["asset_id"].dropna().unique()})
    if not trade_dates or not asset_ids:
        return pd.DataFrame(columns=columns)

    min_date = min(trade_dates)
    max_date = max(trade_dates)
    factor_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    asset_chunks = [asset_ids[index : index + 500] for index in range(0, len(asset_ids), 500)]
    with connect(service) as conn:
        for chunk in asset_chunks:
            asset_placeholders = ", ".join(["%s"] * len(chunk))
            factor_placeholders = ", ".join(["%s"] * len(FUNDAMENTAL_FACTOR_NAMES))
            factor_sql = f"""
                SELECT trade_date::text AS trade_date, asset_id, factor_name, factor_value
                FROM factor.factor_daily
                WHERE trade_date BETWEEN %s AND %s
                  AND asset_id IN ({asset_placeholders})
                  AND factor_name IN ({factor_placeholders})
                ORDER BY trade_date, asset_id, factor_name
            """
            factor_rows.extend(
                fetch_all(conn, factor_sql, [min_date, max_date, *chunk, *FUNDAMENTAL_FACTOR_NAMES])
            )
            status_sql = f"""
                SELECT trade_date::text AS trade_date, asset_id, is_st
                FROM core.asset_status_daily
                WHERE trade_date BETWEEN %s AND %s
                  AND asset_id IN ({asset_placeholders})
                ORDER BY trade_date, asset_id
            """
            status_rows.extend(fetch_all(conn, status_sql, [min_date, max_date, *chunk]))

    factors = pd.DataFrame(factor_rows)
    if factors.empty:
        pivot = pd.DataFrame(columns=["trade_date", "asset_id", *FUNDAMENTAL_FACTOR_NAMES])
    else:
        pivot = (
            factors.pivot_table(
                index=["trade_date", "asset_id"],
                columns="factor_name",
                values="factor_value",
                aggfunc="last",
            )
            .reset_index()
            .rename_axis(None, axis=1)
        )
    statuses = pd.DataFrame(status_rows)
    if statuses.empty:
        statuses = pd.DataFrame(columns=["trade_date", "asset_id", "is_st"])
    merged = pivot.merge(statuses, on=["trade_date", "asset_id"], how="outer")
    for column in columns:
        if column not in merged.columns:
            merged[column] = pd.NA
    return merged.loc[:, columns]


def build_watchlist_context_cross_review_from_frames(
    *,
    detail: pd.DataFrame,
    fundamentals: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    fundamental_frame = fundamentals if fundamentals is not None else pd.DataFrame()
    enriched = _enrich_context(detail, fundamental_frame, warnings)
    short_summary = _short_horizon_summary(enriched)
    strong_summary = _strong_horizon_summary(enriched)
    layer_summary = _layer_summary(enriched)
    industry_summary = _industry_summary(enriched)
    fundamental_summary = _fundamental_summary(enriched)
    report = _render_report(
        short_summary=short_summary,
        strong_summary=strong_summary,
        layer_summary=layer_summary,
        industry_summary=industry_summary,
        fundamental_summary=fundamental_summary,
        warnings=warnings,
    )

    result: dict[str, Any] = {
        "detail": enriched,
        "short_horizon_summary": short_summary,
        "strong_horizon_summary": strong_summary,
        "layer_summary": layer_summary,
        "industry_summary": industry_summary,
        "fundamental_summary": fundamental_summary,
        "report": report,
        "warnings": warnings,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "watchlist_context_cross_detail.csv",
            "short_horizon_summary": output / "watchlist_context_short_horizon_summary.csv",
            "strong_horizon_summary": output / "watchlist_context_strong_horizon_summary.csv",
            "layer_summary": output / "watchlist_context_layer_summary.csv",
            "industry_summary": output / "watchlist_context_industry_summary.csv",
            "fundamental_summary": output / "watchlist_context_fundamental_summary.csv",
            "report": output / "watchlist_context_cross_report.md",
        }
        enriched.to_csv(paths["detail"], index=False)
        short_summary.to_csv(paths["short_horizon_summary"], index=False)
        strong_summary.to_csv(paths["strong_horizon_summary"], index=False)
        layer_summary.to_csv(paths["layer_summary"], index=False)
        industry_summary.to_csv(paths["industry_summary"], index=False)
        fundamental_summary.to_csv(paths["fundamental_summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def classify_fundamental_context(row: pd.Series) -> dict[str, Any]:
    is_st = _bool(row.get("is_st"))
    roe = _float_or_none(row.get("roe"))
    revenue_yoy = _float_or_none(row.get("revenue_yoy"))
    np_yoy = _float_or_none(row.get("np_yoy"))
    deduct_np_yoy = _float_or_none(row.get("deduct_np_yoy"))
    np_parent_ttm = _float_or_none(row.get("np_parent_ttm"))
    debt_ratio = _float_or_none(row.get("debt_ratio"))
    available = any(
        value is not None for value in [roe, revenue_yoy, np_yoy, deduct_np_yoy, np_parent_ttm, debt_ratio]
    ) or is_st

    if not available:
        return _fundamental_classification(
            label="unknown_fundamental",
            hard_risk=False,
            time_horizon_fit="unknown",
            note="missing_point_in_time_fundamental_context",
        )
    if is_st:
        return _fundamental_classification(
            label="st_or_special_risk",
            hard_risk=True,
            time_horizon_fit="short_speculation_only",
            note="st_or_special_treatment_requires_hard_filter_review",
        )

    profit_loss = (np_parent_ttm is not None and np_parent_ttm < 0) or (roe is not None and roe < 0)
    growth_worsening = any(value is not None and value < 0 for value in [revenue_yoy, np_yoy, deduct_np_yoy])
    profit_improving = any(value is not None and value > 0 for value in [np_yoy, deduct_np_yoy])
    revenue_strong = revenue_yoy is not None and revenue_yoy >= 0.20
    profit_positive = any(value is not None and value > 0 for value in [np_yoy, deduct_np_yoy])
    profit_strong = any(value is not None and value >= 0.30 for value in [np_yoy, deduct_np_yoy])
    high_debt = debt_ratio is not None and debt_ratio >= 0.75

    if profit_loss and growth_worsening:
        return _fundamental_classification(
            label="loss_worsening",
            hard_risk=True,
            time_horizon_fit="short_speculation_only",
            note="loss_or_negative_roe_with_deteriorating_growth",
        )
    if profit_loss and profit_improving:
        return _fundamental_classification(
            label="loss_but_improving",
            hard_risk=False,
            time_horizon_fit="turnaround_watch",
            note="loss_context_but_profit_growth_is_improving",
        )
    if profit_loss:
        return _fundamental_classification(
            label="persistent_loss",
            hard_risk=True,
            time_horizon_fit="short_speculation_only",
            note="loss_context_without_clear_improvement",
        )
    if high_debt:
        return _fundamental_classification(
            label="high_debt_only",
            hard_risk=False,
            time_horizon_fit="mid_term_caution",
            note="high_debt_without_loss_or_deteriorating_profit_context",
        )
    if revenue_strong and profit_positive:
        return _fundamental_classification(
            label="expectation_growth",
            hard_risk=False,
            time_horizon_fit="mid_term_eligible",
            note="revenue_and_profit_growth_support_expectation_premium",
        )
    if profit_strong:
        return _fundamental_classification(
            label="cyclical_or_turnaround",
            hard_risk=False,
            time_horizon_fit="mid_term_eligible",
            note="profit_growth_strong_but_revenue_confirmation_is_weaker",
        )
    if growth_worsening:
        return _fundamental_classification(
            label="growth_worsening",
            hard_risk=False,
            time_horizon_fit="mid_term_caution",
            note="growth_deteriorating_without_loss_context",
        )
    return _fundamental_classification(
        label="clean_or_unknown",
        hard_risk=False,
        time_horizon_fit="mid_term_eligible",
        note="no_obvious_fundamental_hard_risk",
    )


def _fundamental_classification(
    *,
    label: str,
    hard_risk: bool,
    time_horizon_fit: str,
    note: str,
) -> dict[str, Any]:
    return {
        "fundamental_quality_bucket": label,
        "fundamental_risk_label": label,
        "fundamental_hard_risk": hard_risk,
        "fundamental_time_horizon_fit": time_horizon_fit,
        "fundamental_note": note,
    }


def _enrich_context(detail: pd.DataFrame, fundamentals: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    frame = detail.copy()
    if "mainline_flag" not in frame.columns:
        frame["mainline_flag"] = pd.NA
    frame["mainline_context"] = frame["mainline_flag"].map(lambda value: "mainline" if _bool(value) else "non_mainline")
    frame["sector_strength_bucket"] = frame.get("sector_strength_rank", pd.Series(pd.NA, index=frame.index)).map(
        _sector_strength_bucket
    )

    if fundamentals.empty:
        warnings.append("missing_fundamental_rows")
        for column in ["roe", "revenue_yoy", "np_yoy", "debt_ratio", "ocf_to_np", "is_st"]:
            frame[column] = pd.NA
    else:
        fund = fundamentals.copy()
        fund["trade_date"] = fund["trade_date"].astype(str)
        fund["asset_id"] = fund["asset_id"].astype(str)
        frame["trade_date"] = frame["trade_date"].astype(str)
        frame["asset_id"] = frame["asset_id"].astype(str)
        frame = frame.merge(fund, on=["trade_date", "asset_id"], how="left", suffixes=("", "_fundamental"))
        for column in [*FUNDAMENTAL_FACTOR_NAMES, "is_st"]:
            if column not in frame.columns:
                frame[column] = pd.NA
        if frame[FUNDAMENTAL_FACTOR_NAMES].isna().all(axis=None):
            warnings.append("missing_fundamental_rows")

    classifications = frame.apply(classify_fundamental_context, axis=1, result_type="expand")
    enriched = pd.concat([frame.reset_index(drop=True), classifications.reset_index(drop=True)], axis=1)
    enriched["watchlist_review_layer"] = enriched.apply(classify_watchlist_review_layer, axis=1)
    return enriched


def classify_watchlist_review_layer(row: pd.Series) -> str:
    watch_group = str(row.get("watch_group") or "")
    event_structure = str(row.get("event_structure") or "")
    time_horizon_fit = str(row.get("fundamental_time_horizon_fit") or "")
    mainline = _bool(row.get("mainline_flag"))

    hard_risk_events = {
        "a_kill_failure",
        "failed_second_wave",
        "failed_reversal",
        "high_open_low_close_failure",
        "one_day_pump",
    }
    lhb_negative = _bool(row.get("lhb_negative_net_buy")) or _bool(row.get("lhb_institution_selling"))
    lhb_risk_score = _float_or_none(row.get("lhb_risk_score"))
    dragon_risk_score = _float_or_none(row.get("dragon_risk_score"))
    has_hard_risk_context = (
        event_structure in hard_risk_events
        or lhb_negative
        or (lhb_risk_score is not None and lhb_risk_score >= 0.70)
        or (dragon_risk_score is not None and dragon_risk_score >= 0.80 and watch_group == "risk_watch")
    )
    if watch_group == "risk_watch" and has_hard_risk_context:
        return "hard_risk_watch"
    if watch_group == "risk_watch":
        return "short_speculation_watch"
    if time_horizon_fit == "short_speculation_only" or watch_group == "high_odds_burst_watch":
        return "short_speculation_watch"
    if mainline and time_horizon_fit in {"mid_term_eligible", "mid_term_caution", "turnaround_watch"}:
        return "mid_term_trend_watch"
    return "unclassified_watch"


def _short_horizon_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return _summary(
        frame,
        group_columns=["mainline_context", "sector_strength_bucket", "watch_group", "event_structure"],
        metric_columns=SHORT_METRICS,
    )


def _strong_horizon_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return _summary(
        frame,
        group_columns=[
            "mainline_context",
            "sector_strength_bucket",
            "fundamental_quality_bucket",
            "fundamental_time_horizon_fit",
            "fundamental_hard_risk",
            "watch_group",
            "event_structure",
        ],
        metric_columns=STRONG_METRICS,
    )


def _layer_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return _summary(
        frame,
        group_columns=[
            "watchlist_review_layer",
            "mainline_context",
            "sector_strength_bucket",
            "watch_group",
            "event_structure",
            "fundamental_quality_bucket",
        ],
        metric_columns=STRONG_METRICS,
    )


def _industry_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if "industry_name" not in frame.columns:
        frame = frame.copy()
        frame["industry_name"] = "unknown"
    return _summary(
        frame,
        group_columns=["industry_name", "mainline_context", "watch_group"],
        metric_columns=["future_20d_return", "future_60d_return", "hit_double_within_60d"],
    ).sort_values(["sample_count", "hit_double_within_60d_rate"], ascending=[False, False])


def _fundamental_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return _summary(
        frame,
        group_columns=[
            "fundamental_quality_bucket",
            "fundamental_time_horizon_fit",
            "fundamental_hard_risk",
            "mainline_context",
        ],
        metric_columns=STRONG_METRICS,
    )


def _summary(frame: pd.DataFrame, *, group_columns: list[str], metric_columns: list[str]) -> pd.DataFrame:
    working = frame.copy()
    for column in group_columns:
        if column not in working.columns:
            working[column] = ""
    for column in metric_columns:
        if column not in working.columns:
            working[column] = pd.NA
        working[column] = pd.to_numeric(working[column], errors="coerce")
    grouped = working.groupby(group_columns, dropna=False)
    summary = grouped[metric_columns].mean(numeric_only=True).reset_index()
    counts = grouped.size().reset_index(name="sample_count")
    summary = counts.merge(summary, on=group_columns, how="left")
    return summary.rename(columns={column: _metric_name(column) for column in metric_columns})


def _metric_name(column: str) -> str:
    if column == "hit_double_within_60d":
        return "hit_double_within_60d_rate"
    return f"{column}_mean"


def _sector_strength_bucket(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return "unknown_sector_rank"
    if number <= 10:
        return "top_10"
    if number <= 30:
        return "top_30"
    if number <= 60:
        return "mid"
    return "weak"


def _render_report(
    *,
    short_summary: pd.DataFrame,
    strong_summary: pd.DataFrame,
    layer_summary: pd.DataFrame,
    industry_summary: pd.DataFrame,
    fundamental_summary: pd.DataFrame,
    warnings: list[str],
) -> str:
    lines = [
        "# Watchlist Context Cross Review v1",
        "",
        "## 1. 研究目标",
        "验证不同周期下行业主线与基本面上下文的解释力；本报告不改变打分、不生成交易建议。",
        "",
        "## 2. 分层口径",
        "- 1/3/5d: 基本面只作为硬排雷背景，主要看行业主线与短线事件。",
        "- 5/10/20/30/60d: 同时看行业主线、行业强度、基本面风险标签和时间周期适配。",
        "- 高负债本身不再直接视为硬风险；持续亏损、亏损加剧、ST/特殊处理才进入硬风险或短线投机-only。",
        "",
    ]
    if warnings:
        lines.extend(["## 3. Warnings", *[f"- {warning}" for warning in warnings], ""])
    lines.extend(["## 4. Short Horizon Context", short_summary.head(20).to_markdown(index=False), ""])
    lines.extend(["## 5. Strong Winner Horizon Context", strong_summary.head(20).to_markdown(index=False), ""])
    lines.extend(["## 6. Watchlist Review Layer", layer_summary.head(20).to_markdown(index=False), ""])
    lines.extend(["## 7. Industry Context", industry_summary.head(20).to_markdown(index=False), ""])
    lines.extend(["## 8. Fundamental Context", fundamental_summary.head(20).to_markdown(index=False), ""])
    lines.extend(
        [
            "## 9. 初步结论",
            "短线层优先验证主线是否提高 1/3/5 日表现；中期强票层再判断主线 + 基本面周期适配是否解释 20/30/60 日延续；硬风险层单独跟踪失败事件和资金撤退。",
        ]
    )
    return "\n".join(lines) + "\n"


def _float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "f", "no", "n", "off", "none", "null", "nan"}:
            return False
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
    return bool(value)
