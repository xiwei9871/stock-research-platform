from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


DEFAULT_REQUIRED_FACTORS = ["roe", "debt_ratio", "ocf_to_np", "gross_margin", "net_margin", "pb", "ps_ttm"]
OPTIONAL_GROWTH_FACTORS = ["revenue_yoy", "np_yoy"]


def run_watchlist_fundamental_coverage_audit(
    *,
    detail_path: str | Path,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    detail = pd.read_csv(detail_path, low_memory=False)
    factor_daily = load_fundamental_factor_daily_for_detail(
        detail,
        factor_names=[*DEFAULT_REQUIRED_FACTORS, *OPTIONAL_GROWTH_FACTORS],
        service=service,
    )
    return build_fundamental_coverage_audit_from_frames(
        detail=detail,
        factor_daily=factor_daily,
        required_factors=[*DEFAULT_REQUIRED_FACTORS, *OPTIONAL_GROWTH_FACTORS],
        output_dir=output_dir,
    )


def load_fundamental_factor_daily_for_detail(
    detail: pd.DataFrame,
    *,
    factor_names: list[str],
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    columns = ["trade_date", "asset_id", "factor_name", "factor_value"]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    dates = sorted({str(value) for value in detail["trade_date"].dropna().unique()})
    asset_ids = sorted({str(value) for value in detail["asset_id"].dropna().unique()})
    if not dates or not asset_ids:
        return pd.DataFrame(columns=columns)
    min_date = min(dates)
    max_date = max(dates)
    rows: list[dict[str, Any]] = []
    with connect(service) as conn:
        for offset in range(0, len(asset_ids), 500):
            chunk = asset_ids[offset : offset + 500]
            asset_placeholders = ", ".join(["%s"] * len(chunk))
            factor_placeholders = ", ".join(["%s"] * len(factor_names))
            sql = f"""
                SELECT trade_date::text AS trade_date, asset_id, factor_name, factor_value
                FROM factor.factor_daily
                WHERE trade_date BETWEEN %s AND %s
                  AND asset_id IN ({asset_placeholders})
                  AND factor_name IN ({factor_placeholders})
                ORDER BY trade_date, asset_id, factor_name
            """
            rows.extend(fetch_all(conn, sql, [min_date, max_date, *chunk, *factor_names]))
    frame = pd.DataFrame(rows)
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame.loc[:, columns]


def build_fundamental_coverage_audit_from_frames(
    *,
    detail: pd.DataFrame,
    factor_daily: pd.DataFrame,
    required_factors: list[str] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    factors = required_factors or [*DEFAULT_REQUIRED_FACTORS, *OPTIONAL_GROWTH_FACTORS]
    normalized_detail = detail.copy()
    if "trade_date" not in normalized_detail.columns:
        normalized_detail["trade_date"] = ""
    if "asset_id" not in normalized_detail.columns:
        normalized_detail["asset_id"] = ""
    normalized_detail["trade_date"] = normalized_detail["trade_date"].astype(str)
    normalized_detail["asset_id"] = normalized_detail["asset_id"].astype(str)

    normalized_factors = factor_daily.copy()
    for column in ["trade_date", "asset_id", "factor_name", "factor_value"]:
        if column not in normalized_factors.columns:
            normalized_factors[column] = pd.NA
    normalized_factors["trade_date"] = normalized_factors["trade_date"].astype(str)
    normalized_factors["asset_id"] = normalized_factors["asset_id"].astype(str)

    pair_factor_count = (
        normalized_factors.dropna(subset=["factor_name"])
        .groupby(["trade_date", "asset_id"])["factor_name"]
        .nunique()
        .reset_index(name="fundamental_factor_count")
    )
    enriched = normalized_detail[["trade_date", "asset_id"]].merge(
        pair_factor_count, on=["trade_date", "asset_id"], how="left"
    )
    enriched["fundamental_factor_count"] = enriched["fundamental_factor_count"].fillna(0).astype(int)
    enriched["has_any_fundamental"] = enriched["fundamental_factor_count"] > 0

    available_factors = sorted({str(value) for value in normalized_factors["factor_name"].dropna().unique()})
    missing_factors = [factor for factor in factors if factor not in available_factors]
    summary = pd.DataFrame(
        [
            {"metric": "detail_rows", "value": int(len(normalized_detail))},
            {"metric": "detail_dates", "value": int(normalized_detail["trade_date"].nunique())},
            {"metric": "detail_assets", "value": int(normalized_detail["asset_id"].nunique())},
            {"metric": "factor_rows", "value": int(len(normalized_factors))},
            {"metric": "factor_dates", "value": int(normalized_factors["trade_date"].nunique()) if not normalized_factors.empty else 0},
            {"metric": "factor_assets", "value": int(normalized_factors["asset_id"].nunique()) if not normalized_factors.empty else 0},
            {"metric": "rows_with_any_fundamental", "value": int(enriched["has_any_fundamental"].sum())},
            {
                "metric": "rows_with_any_fundamental_rate",
                "value": float(enriched["has_any_fundamental"].mean()) if len(enriched) else 0.0,
            },
            {"metric": "available_factors", "value": ",".join(available_factors)},
            {"metric": "missing_required_factors", "value": ",".join(missing_factors)},
        ]
    )
    date_summary = (
        enriched.groupby("trade_date", dropna=False)
        .agg(
            detail_rows=("asset_id", "size"),
            rows_with_any_fundamental=("has_any_fundamental", "sum"),
            avg_fundamental_factor_count=("fundamental_factor_count", "mean"),
        )
        .reset_index()
    )
    date_summary["rows_with_any_fundamental_rate"] = (
        date_summary["rows_with_any_fundamental"] / date_summary["detail_rows"]
    )
    report = _render_report(summary, date_summary, missing_factors)

    result: dict[str, Any] = {
        "summary": summary,
        "date_summary": date_summary,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": output / "watchlist_fundamental_coverage_audit.csv",
            "date_summary": output / "watchlist_fundamental_coverage_date_summary.csv",
            "report": output / "watchlist_fundamental_coverage_report.md",
        }
        summary.to_csv(paths["summary"], index=False)
        date_summary.to_csv(paths["date_summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _render_report(summary: pd.DataFrame, date_summary: pd.DataFrame, missing_factors: list[str]) -> str:
    metrics = summary.set_index("metric")["value"].to_dict() if not summary.empty else {}
    factor_dates = int(metrics.get("factor_dates") or 0)
    detail_dates = int(metrics.get("detail_dates") or 0)
    root_causes: list[str] = []
    if factor_dates < detail_dates:
        root_causes.append("exact_trade_date_factor_gap")
    if missing_factors:
        root_causes.append("missing_factor_names")
    if not root_causes:
        root_causes.append("no_obvious_coverage_gap")
    lines = [
        "# Watchlist Fundamental Coverage Audit",
        "",
        "## 1. Root Cause",
        *[f"- {cause}" for cause in root_causes],
        "",
        "## 2. Summary",
        summary.to_markdown(index=False),
        "",
        "## 3. Date Coverage",
        date_summary.head(30).to_markdown(index=False),
        "",
        "## 4. Interpretation",
        "如果 exact_trade_date_factor_gap 存在，context cross review 不能直接按当日 factor_daily 合并基本面；需要补全 factor_daily 或改为 point-in-time 最近公告对齐。",
    ]
    return "\n".join(lines) + "\n"
