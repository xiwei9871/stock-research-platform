from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.factor_pipeline import load_point_in_time_fundamentals_snapshot


PIT_CONTEXT_COLUMNS = [
    "trade_date",
    "asset_id",
    "roe",
    "roa",
    "gross_margin",
    "net_margin",
    "debt_ratio",
    "revenue_yoy",
    "np_yoy",
    "deduct_np_yoy",
    "ocf_to_np",
    "np_parent_ttm",
    "revenue_ttm",
    "equity_parent",
    "total_share",
    "float_share",
]


def run_watchlist_fundamental_pit_context_build(
    *,
    detail_path: str | Path,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    detail = pd.read_csv(detail_path, low_memory=False)
    return build_watchlist_fundamental_pit_context_from_detail(
        detail,
        output_dir=output_dir,
        service=service,
    )


def build_watchlist_fundamental_pit_context_from_detail(
    detail: pd.DataFrame,
    *,
    output_dir: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    context = _build_context(detail, service=service)
    summary = _build_summary(detail, context)
    report = _render_report(summary)
    result: dict[str, Any] = {
        "context": context,
        "summary": summary,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "context": output / "watchlist_fundamental_pit_context.csv",
            "summary": output / "watchlist_fundamental_pit_context_summary.csv",
            "report": output / "watchlist_fundamental_pit_context_report.md",
        }
        context.to_csv(paths["context"], index=False)
        summary.to_csv(paths["summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _build_context(detail: pd.DataFrame, *, service: str) -> pd.DataFrame:
    if detail.empty or not {"trade_date", "asset_id"} <= set(detail.columns):
        return pd.DataFrame(columns=PIT_CONTEXT_COLUMNS)
    frame = detail[["trade_date", "asset_id"]].drop_duplicates().copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["asset_id"] = frame["asset_id"].astype(str)
    rows: list[pd.DataFrame] = []
    for trade_date, group in frame.groupby("trade_date", sort=True):
        bars = group[["trade_date", "asset_id"]].copy()
        bars["close"] = 1.0
        snapshot = load_point_in_time_fundamentals_snapshot(
            bars,
            trade_date=trade_date,
            service=service,
        )
        if snapshot.empty:
            continue
        snapshot = snapshot.copy()
        snapshot.insert(0, "trade_date", trade_date)
        rows.append(snapshot)
    context = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=PIT_CONTEXT_COLUMNS)
    for column in PIT_CONTEXT_COLUMNS:
        if column not in context.columns:
            context[column] = pd.NA
    return context.loc[:, PIT_CONTEXT_COLUMNS]


def _build_summary(detail: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    detail_pairs = detail[["trade_date", "asset_id"]].drop_duplicates().copy() if not detail.empty else pd.DataFrame(columns=["trade_date", "asset_id"])
    if not detail_pairs.empty:
        detail_pairs["trade_date"] = detail_pairs["trade_date"].astype(str).str[:10]
        detail_pairs["asset_id"] = detail_pairs["asset_id"].astype(str)
    context_pairs = context[["trade_date", "asset_id"]].drop_duplicates().copy() if not context.empty else pd.DataFrame(columns=["trade_date", "asset_id"])
    if not context_pairs.empty:
        context_pairs["trade_date"] = context_pairs["trade_date"].astype(str).str[:10]
        context_pairs["asset_id"] = context_pairs["asset_id"].astype(str)
    merged = detail_pairs.merge(context_pairs.assign(has_pit_context=True), on=["trade_date", "asset_id"], how="left")
    merged["has_pit_context"] = merged["has_pit_context"].fillna(False)
    return pd.DataFrame(
        [
            {"metric": "detail_pairs", "value": int(len(detail_pairs))},
            {"metric": "pit_context_rows", "value": int(len(context))},
            {"metric": "pit_context_dates", "value": int(context["trade_date"].nunique()) if not context.empty else 0},
            {"metric": "pit_context_assets", "value": int(context["asset_id"].nunique()) if not context.empty else 0},
            {"metric": "detail_pairs_with_pit_context", "value": int(merged["has_pit_context"].sum())},
            {
                "metric": "detail_pairs_with_pit_context_rate",
                "value": float(merged["has_pit_context"].mean()) if len(merged) else 0.0,
            },
        ]
    )


def _render_report(summary: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# Watchlist Fundamental PIT Context",
            "",
            "## 1. 研究目标",
            "为 watchlist 诊断补充 point-in-time 最近公告基本面上下文，避免 exact factor_daily 日期缺口。",
            "",
            "## 2. Coverage",
            summary.to_markdown(index=False),
            "",
            "## 3. 说明",
            "该文件只用于研究诊断，不接策略打分；底层查询使用 announcement_date <= trade_date，避免未来函数。",
        ]
    ) + "\n"
