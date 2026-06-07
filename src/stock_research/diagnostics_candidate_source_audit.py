from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


OUTPUT_COLUMNS = [
    "winner_id",
    "winner_type",
    "asset_id",
    "window_start",
    "window_end",
    "diagnostics_dates_in_window",
    "score_dates_in_window",
    "best_score_rank",
    "best_score_date",
    "best_score_total",
    "source_gap_reason",
]


def run_diagnostics_candidate_source_audit(
    *,
    gap_detail_path: str | Path,
    v2_detail_path: str | Path,
    output_dir: str | Path,
    score_version: str = "manual_v1",
    diagnostics_top_n: int = 50,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    gap_detail = pd.read_csv(gap_detail_path, low_memory=False)
    v2_detail = pd.read_csv(v2_detail_path, low_memory=False)
    score_rows = load_score_rows_for_gap_windows(
        gap_detail=gap_detail,
        score_version=score_version,
        service=service,
    )
    return build_diagnostics_candidate_source_audit(
        gap_detail=gap_detail,
        v2_detail=v2_detail,
        score_rows=score_rows,
        diagnostics_top_n=diagnostics_top_n,
        output_dir=output_dir,
    )


def load_score_rows_for_gap_windows(
    *,
    gap_detail: pd.DataFrame,
    score_version: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    gaps = _prepare_gap_detail(gap_detail)
    if gaps.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total", "score_version"])
    asset_ids = sorted(gaps["asset_id"].dropna().astype(str).unique())
    start = gaps["window_start_dt"].min()
    end = gaps["window_end_dt"].max()
    if not asset_ids or pd.isna(start) or pd.isna(end):
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total", "score_version"])
    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT trade_date, asset_id, rank, score_total, score_version
        FROM factor.stock_score_daily
        WHERE score_version = %s
          AND trade_date BETWEEN %s AND %s
          AND asset_id IN ({placeholders})
        ORDER BY trade_date, asset_id
    """
    params: list[Any] = [score_version, start.date().isoformat(), end.date().isoformat(), *asset_ids]
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total", "score_version"])
    return frame


def build_diagnostics_candidate_source_audit(
    *,
    gap_detail: pd.DataFrame,
    v2_detail: pd.DataFrame,
    score_rows: pd.DataFrame,
    diagnostics_top_n: int = 50,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    gaps = _prepare_gap_detail(gap_detail)
    detail = _prepare_v2_detail(v2_detail, warnings)
    scores = _prepare_score_rows(score_rows)
    audit_detail = _build_detail(gaps, detail, scores, diagnostics_top_n)
    summary = _summary(audit_detail)
    by_type = _by_type(audit_detail)
    report = _render_report(audit_detail, summary, by_type, warnings, diagnostics_top_n)

    result: dict[str, Any] = {
        "detail": audit_detail,
        "summary": summary,
        "by_type": by_type,
        "report": report,
        "warnings": warnings,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "diagnostics_candidate_source_audit_detail.csv",
            "summary": output / "diagnostics_candidate_source_audit_summary.csv",
            "by_type": output / "diagnostics_candidate_source_audit_by_type.csv",
            "report": output / "diagnostics_candidate_source_audit_report.md",
        }
        audit_detail.to_csv(paths["detail"], index=False)
        summary.to_csv(paths["summary"], index=False)
        by_type.to_csv(paths["by_type"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _prepare_gap_detail(frame: pd.DataFrame) -> pd.DataFrame:
    gaps = frame.copy()
    for column in ["winner_id", "winner_type", "asset_id", "window_start", "window_end"]:
        if column not in gaps.columns:
            gaps[column] = ""
    if "primary_gap_category" in gaps.columns:
        gaps = gaps[gaps["primary_gap_category"].eq("diagnostics_coverage_gap")].copy()
    gaps["asset_id"] = gaps["asset_id"].astype(str)
    gaps["window_start_dt"] = pd.to_datetime(gaps["window_start"], errors="coerce")
    gaps["window_end_dt"] = pd.to_datetime(gaps["window_end"], errors="coerce")
    return gaps.reset_index(drop=True)


def _prepare_v2_detail(frame: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    detail = frame.copy()
    for column in ["trade_date", "asset_id"]:
        if column not in detail.columns:
            detail[column] = ""
            warnings.append(f"missing_v2_detail_{column}")
    detail["trade_date"] = pd.to_datetime(detail["trade_date"], errors="coerce")
    detail["asset_id"] = detail["asset_id"].astype(str)
    return detail


def _prepare_score_rows(frame: pd.DataFrame) -> pd.DataFrame:
    scores = frame.copy()
    for column in ["trade_date", "asset_id", "rank", "score_total"]:
        if column not in scores.columns:
            scores[column] = pd.NA
    scores["trade_date"] = pd.to_datetime(scores["trade_date"], errors="coerce")
    scores["asset_id"] = scores["asset_id"].astype(str)
    scores["rank"] = pd.to_numeric(scores["rank"], errors="coerce")
    scores["score_total"] = pd.to_numeric(scores["score_total"], errors="coerce")
    return scores


def _build_detail(
    gaps: pd.DataFrame,
    diagnostics: pd.DataFrame,
    scores: pd.DataFrame,
    diagnostics_top_n: int,
) -> pd.DataFrame:
    diagnostics_by_asset = {asset: group for asset, group in diagnostics.groupby("asset_id", dropna=False)}
    scores_by_asset = {asset: group for asset, group in scores.groupby("asset_id", dropna=False)}
    rows = []
    for _, winner in gaps.iterrows():
        asset_id = str(winner["asset_id"])
        drows = _window_rows(diagnostics_by_asset.get(asset_id, diagnostics.iloc[0:0]), winner)
        srows = _window_rows(scores_by_asset.get(asset_id, scores.iloc[0:0]), winner)
        best = srows.sort_values(["rank", "trade_date"]).head(1)
        if best.empty:
            best_rank = pd.NA
            best_date = ""
            best_total = pd.NA
        else:
            best_row = best.iloc[0]
            best_rank = best_row.get("rank")
            best_date = _date_string(best_row.get("trade_date"))
            best_total = best_row.get("score_total")
        reason = _source_gap_reason(
            diagnostics_dates=len(set(drows["trade_date"].dropna())) if not drows.empty else 0,
            score_dates=len(set(srows["trade_date"].dropna())) if not srows.empty else 0,
            best_rank=best_rank,
            diagnostics_top_n=diagnostics_top_n,
        )
        rows.append(
            {
                "winner_id": winner.get("winner_id", ""),
                "winner_type": winner.get("winner_type", ""),
                "asset_id": asset_id,
                "window_start": winner.get("window_start", ""),
                "window_end": winner.get("window_end", ""),
                "diagnostics_dates_in_window": len(set(drows["trade_date"].dropna())) if not drows.empty else 0,
                "score_dates_in_window": len(set(srows["trade_date"].dropna())) if not srows.empty else 0,
                "best_score_rank": best_rank,
                "best_score_date": best_date,
                "best_score_total": best_total,
                "source_gap_reason": reason,
            }
        )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def _window_rows(frame: pd.DataFrame, winner: pd.Series) -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return frame.iloc[0:0]
    return frame[
        (frame["trade_date"] >= winner["window_start_dt"])
        & (frame["trade_date"] <= winner["window_end_dt"])
    ]


def _source_gap_reason(
    *,
    diagnostics_dates: int,
    score_dates: int,
    best_rank: Any,
    diagnostics_top_n: int,
) -> str:
    if diagnostics_dates > 0:
        return "diagnostics_row_exists"
    if score_dates <= 0:
        return "no_score_in_window"
    rank = _float_or_none(best_rank)
    if rank is None:
        return "score_exists_rank_missing"
    if rank > diagnostics_top_n:
        return "score_rank_below_diagnostics_topn"
    return "score_available_but_missing_diagnostics"


def _summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=["source_gap_reason", "winner_count", "winner_share", "avg_best_score_rank"])
    total = len(detail)
    grouped = detail.groupby("source_gap_reason", dropna=False)
    summary = grouped.agg(
        winner_count=("winner_id", "count"),
        avg_best_score_rank=("best_score_rank", "mean"),
        avg_score_dates=("score_dates_in_window", "mean"),
    ).reset_index()
    summary["winner_share"] = summary["winner_count"] / total
    return summary[["source_gap_reason", "winner_count", "winner_share", "avg_best_score_rank", "avg_score_dates"]]


def _by_type(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=["winner_type", "source_gap_reason", "winner_count", "avg_best_score_rank"])
    return detail.groupby(["winner_type", "source_gap_reason"], dropna=False).agg(
        winner_count=("winner_id", "count"),
        avg_best_score_rank=("best_score_rank", "mean"),
    ).reset_index()


def _render_report(
    detail: pd.DataFrame,
    summary: pd.DataFrame,
    by_type: pd.DataFrame,
    warnings: list[str],
    diagnostics_top_n: int,
) -> str:
    lines = [
        "# Diagnostics Candidate Source Audit",
        "",
        "## 1. Scope",
        "只审计 diagnostics_coverage_gap 的入口来源：窗口内是否有 stock_score_daily、最优 rank 是否落在 diagnostics topN 内、是否存在异常缺诊断行。不改 watchlist 规则。",
        "",
        "## 2. Config",
        f"- diagnostics_top_n: {diagnostics_top_n}",
        f"- audited_gap_rows: {len(detail)}",
        "",
        "## 3. Warnings",
        *([f"- {warning}" for warning in warnings] or ["- none"]),
        "",
        "## 4. Summary",
        summary.to_markdown(index=False),
        "",
        "## 5. By Winner Type",
        by_type.to_markdown(index=False),
    ]
    return "\n".join(lines) + "\n"


def _date_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
