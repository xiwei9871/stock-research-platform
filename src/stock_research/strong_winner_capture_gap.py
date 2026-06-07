from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


V2_FINAL_COLUMN = "v2_final_baseline"
GAP_CATEGORIES = [
    "diagnostics_coverage_gap",
    "technical_gap",
    "mainline_theme_gap",
    "fundamental_gap",
    "risk_filter_gap",
    "minute_data_gap",
    "theme_sentiment_gap",
    "captured",
]


def run_strong_winner_capture_gap_analysis(
    *,
    taxonomy_path: str | Path,
    v2_detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    taxonomy = pd.read_csv(taxonomy_path, low_memory=False)
    v2_detail = pd.read_csv(v2_detail_path, low_memory=False)
    return build_strong_winner_capture_gap_analysis(
        taxonomy=taxonomy,
        v2_detail=v2_detail,
        output_dir=output_dir,
    )


def build_strong_winner_capture_gap_analysis(
    *,
    taxonomy: pd.DataFrame,
    v2_detail: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    winners = _prepare_taxonomy(taxonomy, warnings)
    detail = _prepare_detail(v2_detail, warnings)
    gap_detail = _build_gap_detail(winners, detail)
    summary = _gap_summary(gap_detail)
    by_type = _gap_by_type(gap_detail)
    sample = _gap_sample(gap_detail)
    report = _render_report(gap_detail, summary, by_type, sample, warnings)

    result: dict[str, Any] = {
        "detail": gap_detail,
        "summary": summary,
        "by_type": by_type,
        "sample": sample,
        "report": report,
        "warnings": warnings,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "strong_winner_capture_gap_detail.csv",
            "summary": output / "strong_winner_capture_gap_summary.csv",
            "by_type": output / "strong_winner_capture_gap_by_type.csv",
            "sample": output / "strong_winner_capture_gap_sample.csv",
            "report": output / "strong_winner_capture_gap_report.md",
        }
        gap_detail.to_csv(paths["detail"], index=False)
        summary.to_csv(paths["summary"], index=False)
        by_type.to_csv(paths["by_type"], index=False)
        sample.to_csv(paths["sample"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _prepare_taxonomy(taxonomy: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    frame = taxonomy.copy()
    for column in ["winner_id", "winner_type", "asset_id", "ts_code", "stock_name", "window_start", "window_end"]:
        if column not in frame.columns:
            frame[column] = ""
            warnings.append(f"missing_taxonomy_{column}")
    for column in ["max_return", "max_drawdown"]:
        if column not in frame.columns:
            frame[column] = pd.NA
            warnings.append(f"missing_taxonomy_{column}")
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["window_start_dt"] = pd.to_datetime(frame["window_start"], errors="coerce")
    frame["window_end_dt"] = pd.to_datetime(frame["window_end"], errors="coerce")
    return frame


def _prepare_detail(v2_detail: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    frame = v2_detail.copy()
    required = [
        "asset_id",
        "trade_date",
        V2_FINAL_COLUMN,
        "trend_discovery_v2_recall",
        "dual_momentum_template",
        "sector_strength_bucket",
        "mainline_context",
        "fundamental_hard_risk",
        "fundamental_quality_bucket",
        "dragon_risk_score",
        "lhb_risk_score",
    ]
    for column in required:
        if column not in frame.columns:
            frame[column] = False if column in {V2_FINAL_COLUMN, "trend_discovery_v2_recall", "dual_momentum_template", "fundamental_hard_risk"} else ""
            warnings.append(f"missing_detail_{column}")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    for column in [
        V2_FINAL_COLUMN,
        "trend_discovery_v2_recall",
        "dual_momentum_template",
        "time_series_momentum_template",
        "relative_strength_template",
        "minervini_like_template",
        "fundamental_hard_risk",
        "overheat_avoid",
        "crowded_late_entry",
        "lhb_negative_net_buy",
        "lhb_institution_selling",
    ]:
        if column not in frame.columns:
            frame[column] = False
        frame[column] = frame[column].map(_bool)
    for column in ["score_rank", "dragon_risk_score", "lhb_risk_score"]:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _build_gap_detail(winners: pd.DataFrame, detail: pd.DataFrame) -> pd.DataFrame:
    detail_by_asset = {asset_id: group.sort_values("trade_date") for asset_id, group in detail.groupby("asset_id")}
    rows = []
    for _, winner in winners.iterrows():
        asset_detail = detail_by_asset.get(str(winner["asset_id"]), detail.iloc[0:0])
        window_rows = asset_detail[
            (asset_detail["trade_date"] >= winner["window_start_dt"])
            & (asset_detail["trade_date"] <= winner["window_end_dt"])
        ]
        rows.append(_winner_gap_row(winner, window_rows))
    return pd.DataFrame(rows)


def _winner_gap_row(winner: pd.Series, rows: pd.DataFrame) -> dict[str, Any]:
    seen = not rows.empty
    captured = bool(rows[V2_FINAL_COLUMN].any()) if seen and V2_FINAL_COLUMN in rows.columns else False
    technical_gap = seen and not bool(rows["trend_discovery_v2_recall"].any())
    mainline_gap = seen and not (
        rows.get("sector_strength_bucket", pd.Series(dtype=str)).isin(["top_10", "top_30"]).any()
        or rows.get("mainline_context", pd.Series(dtype=str)).eq("mainline").any()
    )
    fundamental_gap = seen and (
        bool(rows.get("fundamental_hard_risk", pd.Series(dtype=bool)).any())
        or rows.get("fundamental_quality_bucket", pd.Series(dtype=str)).isin(["growth_worsening", "hard_risk"]).any()
    )
    risk_gap = seen and (
        pd.to_numeric(rows.get("dragon_risk_score", pd.Series(dtype=float)), errors="coerce").max(skipna=True) >= 0.7
        or pd.to_numeric(rows.get("lhb_risk_score", pd.Series(dtype=float)), errors="coerce").max(skipna=True) >= 0.7
        or bool(rows.get("overheat_avoid", pd.Series(dtype=bool)).any())
        or bool(rows.get("crowded_late_entry", pd.Series(dtype=bool)).any())
        or bool(rows.get("lhb_negative_net_buy", pd.Series(dtype=bool)).any())
        or bool(rows.get("lhb_institution_selling", pd.Series(dtype=bool)).any())
    )
    minute_data_gap = True
    theme_sentiment_gap = True
    primary = _primary_gap_category(
        captured=captured,
        seen=seen,
        technical_gap=technical_gap,
        mainline_gap=mainline_gap,
        fundamental_gap=fundamental_gap,
        risk_gap=risk_gap,
    )
    return {
        "winner_id": winner.get("winner_id", ""),
        "winner_type": winner.get("winner_type", ""),
        "asset_id": winner.get("asset_id", ""),
        "ts_code": winner.get("ts_code", ""),
        "stock_name": winner.get("stock_name", ""),
        "window_start": winner.get("window_start", ""),
        "window_end": winner.get("window_end", ""),
        "max_return": winner.get("max_return"),
        "max_drawdown": winner.get("max_drawdown"),
        "diagnostics_seen": seen,
        "captured_by_v2_final": captured,
        "technical_gap": bool(technical_gap),
        "mainline_theme_gap": bool(mainline_gap),
        "fundamental_gap": bool(fundamental_gap),
        "risk_filter_gap": bool(risk_gap),
        "minute_data_gap": minute_data_gap,
        "theme_sentiment_gap": theme_sentiment_gap,
        "primary_gap_category": primary,
        "best_score_rank": _min_numeric(rows, "score_rank"),
        "seen_days": len(rows),
    }


def _primary_gap_category(
    *,
    captured: bool,
    seen: bool,
    technical_gap: bool,
    mainline_gap: bool,
    fundamental_gap: bool,
    risk_gap: bool,
) -> str:
    if captured:
        return "captured"
    if not seen:
        return "diagnostics_coverage_gap"
    if technical_gap:
        return "technical_gap"
    if mainline_gap:
        return "mainline_theme_gap"
    if fundamental_gap:
        return "fundamental_gap"
    if risk_gap:
        return "risk_filter_gap"
    return "theme_sentiment_gap"


def _gap_summary(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(detail)
    for category in GAP_CATEGORIES:
        if category == "captured":
            mask = detail["primary_gap_category"].eq("captured")
        else:
            mask = detail[category] if category in detail.columns else detail["primary_gap_category"].eq(category)
        count = int(mask.sum())
        rows.append(
            {
                "gap_category": category,
                "winner_count": count,
                "winner_share": count / total if total else 0.0,
                "avg_max_return": pd.to_numeric(detail.loc[mask, "max_return"], errors="coerce").mean(),
                "avg_max_drawdown": pd.to_numeric(detail.loc[mask, "max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows)


def _gap_by_type(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (winner_type, category), group in detail.groupby(["winner_type", "primary_gap_category"], dropna=False):
        rows.append(
            {
                "winner_type": winner_type,
                "primary_gap_category": category,
                "winner_count": len(group),
                "avg_max_return": pd.to_numeric(group["max_return"], errors="coerce").mean(),
                "avg_max_drawdown": pd.to_numeric(group["max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows)


def _gap_sample(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return detail.copy()
    return (
        detail[detail["primary_gap_category"].ne("captured")]
        .sort_values(["max_return", "winner_type"], ascending=[False, True])
        .head(200)
        .reset_index(drop=True)
    )


def _render_report(
    detail: pd.DataFrame,
    summary: pd.DataFrame,
    by_type: pd.DataFrame,
    sample: pd.DataFrame,
    warnings: list[str],
) -> str:
    lines = [
        "# Strong Winner Capture Gap Analysis v1",
        "",
        "## 1. Scope",
        "拆解多标签强票未被 v2_final 捕捉的原因：技术、主线/题材、基本面、风险过滤、分时缺失、题材/舆情缺失；仅做诊断，不改规则。",
        "",
        "## 2. Coverage",
        f"- taxonomy_rows: {len(detail)}",
        f"- captured_rows: {int(detail['captured_by_v2_final'].sum()) if not detail.empty else 0}",
        "",
        "## 3. Warnings",
        *([f"- {warning}" for warning in warnings] or ["- none"]),
        "",
        "## 4. Gap Summary",
        summary.to_markdown(index=False),
        "",
        "## 5. Gap by Winner Type",
        by_type.to_markdown(index=False),
        "",
        "## 6. Sample",
        sample.head(50).to_markdown(index=False),
    ]
    return "\n".join(lines) + "\n"


def _min_numeric(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    value = pd.to_numeric(frame[column], errors="coerce").min(skipna=True)
    return None if pd.isna(value) else float(value)


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
