from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


SHORT_METRICS = [
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
]
TREND_METRICS = [
    "future_10d_return",
    "future_20d_return",
    "future_30d_return",
    "future_40d_return",
    "future_60d_return",
    "future_20d_max_drawdown",
    "future_30d_max_drawdown",
    "future_40d_max_drawdown",
    "future_60d_max_drawdown",
    "max_return_within_60d",
    "hit_double_within_60d",
]
SHORT_GROUP_COLUMNS = [
    "watchlist_review_layer",
    "watch_group",
    "event_structure",
    "mainline_context",
]
TREND_GROUP_COLUMNS = [
    "watchlist_review_layer",
    "watch_group",
    "event_structure",
    "mainline_context",
    "sector_strength_bucket",
    "fundamental_quality_bucket",
]


def run_dual_strategy_effectiveness_review(
    *,
    detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    detail = pd.read_csv(detail_path, low_memory=False)
    return build_dual_strategy_effectiveness_review(detail=detail, output_dir=output_dir)


def build_dual_strategy_effectiveness_review(
    *,
    detail: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    normalized = _normalize_detail(detail, warnings)

    short_rows = normalized[normalized["strategy_line_short"].eq("short_event_lhb")].copy()
    trend_rows = normalized[normalized["strategy_line_trend"].eq("trend_discovery")].copy()
    short_event_summary = _summary(
        short_rows,
        strategy_line="short_event_lhb",
        group_columns=SHORT_GROUP_COLUMNS,
        metric_columns=SHORT_METRICS,
    )
    trend_discovery_summary = _summary(
        trend_rows,
        strategy_line="trend_discovery",
        group_columns=TREND_GROUP_COLUMNS,
        metric_columns=TREND_METRICS,
    )
    comparison = _comparison_summary(normalized)
    report = _render_report(
        short_event_summary=short_event_summary,
        trend_discovery_summary=trend_discovery_summary,
        comparison=comparison,
        warnings=warnings,
    )

    result: dict[str, Any] = {
        "short_event_summary": short_event_summary,
        "trend_discovery_summary": trend_discovery_summary,
        "comparison": comparison,
        "report": report,
        "warnings": warnings,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "short_event_summary": output / "dual_strategy_short_event_effectiveness.csv",
            "trend_discovery_summary": output / "dual_strategy_trend_discovery_effectiveness.csv",
            "comparison": output / "dual_strategy_layer_comparison.csv",
            "report": output / "dual_strategy_effectiveness_report.md",
        }
        short_event_summary.to_csv(paths["short_event_summary"], index=False)
        trend_discovery_summary.to_csv(paths["trend_discovery_summary"], index=False)
        comparison.to_csv(paths["comparison"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _normalize_detail(detail: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    frame = detail.copy()
    for column in sorted(set(SHORT_GROUP_COLUMNS + TREND_GROUP_COLUMNS)):
        if column not in frame.columns:
            frame[column] = ""
    if "watchlist_review_layer" not in frame.columns:
        warnings.append("missing_watchlist_review_layer")
        frame["watchlist_review_layer"] = frame.get("watch_group", "").map(_fallback_review_layer)
    for column in sorted(set(SHORT_METRICS + TREND_METRICS)):
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "hit_double_within_60d" in frame.columns:
        frame["hit_double_within_60d"] = frame["hit_double_within_60d"].map(_bool).astype(float)

    frame["strategy_line_short"] = frame["watchlist_review_layer"].map(
        lambda value: "short_event_lhb"
        if str(value) in {"short_speculation_watch", "hard_risk_watch"}
        else "not_short_event_lhb"
    )
    frame["strategy_line_trend"] = frame["watchlist_review_layer"].map(
        lambda value: "trend_discovery" if str(value) == "mid_term_trend_watch" else "not_trend_discovery"
    )
    return frame


def _summary(
    frame: pd.DataFrame,
    *,
    strategy_line: str,
    group_columns: list[str],
    metric_columns: list[str],
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["strategy_line", *group_columns, "sample_count"])
    grouped = frame.groupby(group_columns, dropna=False)
    summary = grouped[metric_columns].mean(numeric_only=True).reset_index()
    counts = grouped.size().reset_index(name="sample_count")
    summary = counts.merge(summary, on=group_columns, how="left")
    summary.insert(0, "strategy_line", strategy_line)
    summary = summary.rename(columns={column: _metric_name(column) for column in metric_columns})
    return summary.sort_values(["sample_count"], ascending=False).reset_index(drop=True)


def _comparison_summary(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    working["dual_strategy_bucket"] = working["watchlist_review_layer"].map(
        lambda value: {
            "short_speculation_watch": "short_event_lhb",
            "hard_risk_watch": "short_event_lhb",
            "mid_term_trend_watch": "trend_discovery",
        }.get(str(value), "out_of_scope")
    )
    metrics = [
        "future_5d_return",
        "future_10d_return",
        "future_20d_return",
        "future_60d_return",
        "future_5d_max_drawdown",
        "future_60d_max_drawdown",
        "hit_double_within_60d",
    ]
    return _summary(
        working,
        strategy_line="comparison",
        group_columns=["dual_strategy_bucket", "watchlist_review_layer"],
        metric_columns=metrics,
    )


def _render_report(
    *,
    short_event_summary: pd.DataFrame,
    trend_discovery_summary: pd.DataFrame,
    comparison: pd.DataFrame,
    warnings: list[str],
) -> str:
    lines = [
        "# Dual Strategy Effectiveness Review v1",
        "",
        "## 1. Scope",
        "本报告把 1/3/5/10d 超短线事件/LHB 与 10/20/30/40/60d 趋势挖掘分开评估；不接实盘、不改 stock_score、不生成交易建议。",
        "",
        "## 2. Warnings",
    ]
    lines.extend([f"- {warning}" for warning in warnings] or ["- none"])
    lines.extend(
        [
            "",
            "## 3. Short Event / LHB Line",
            short_event_summary.head(20).to_markdown(index=False),
            "",
            "## 4. Trend Discovery Line",
            trend_discovery_summary.head(20).to_markdown(index=False),
            "",
            "## 5. Layer Comparison",
            comparison.head(20).to_markdown(index=False),
            "",
            "## 6. Interpretation Guardrail",
            "超短线只看短周期胜率、弹性和回撤；趋势线只看中长周期延续、峰值收益和回撤。两条线不能用同一套指标互相否定。",
        ]
    )
    return "\n".join(lines) + "\n"


def _fallback_review_layer(watch_group: Any) -> str:
    value = str(watch_group)
    if value in {"risk_watch", "high_odds_burst_watch"}:
        return "short_speculation_watch"
    if value in {"candidate", "opportunity_watch"}:
        return "mid_term_trend_watch"
    return "unclassified_watch"


def _metric_name(column: str) -> str:
    if column == "hit_double_within_60d":
        return "hit_double_within_60d_rate"
    return f"{column}_mean"


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
