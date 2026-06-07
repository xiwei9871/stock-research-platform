from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


DEFAULT_TOPN_THRESHOLDS = [50, 100, 200, 500]

ATTRIBUTION_COLUMNS = [
    "winner_id",
    "asset_id",
    "ts_code",
    "stock_name",
    "segment_start_date",
    "double_confirm_date",
    "low_to_peak_return",
    "capture_status",
    "miss_reason",
    "has_score_pre_double",
    "best_pre_double_rank",
    "best_score_date",
    "best_score_total",
    "topn_attribution",
    "max_threshold_captured",
    "weakest_components",
]


def run_strong_winner_topn_attribution(
    *,
    miss_analysis_path: str | Path,
    score_version: str = "manual_v1",
    topn_thresholds: list[int] | None = None,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    miss_analysis = pd.read_csv(miss_analysis_path)
    score_rows = load_score_rows_for_miss_analysis(
        miss_analysis,
        score_version=score_version,
        service=service,
    )
    return build_strong_winner_topn_attribution_from_frames(
        miss_analysis=miss_analysis,
        score_rows=score_rows,
        topn_thresholds=topn_thresholds or DEFAULT_TOPN_THRESHOLDS,
        output_dir=output_dir,
    )


def load_score_rows_for_miss_analysis(
    miss_analysis: pd.DataFrame,
    *,
    score_version: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    columns = ["trade_date", "asset_id", "rank", "score_total", "score_version", "score_components"]
    if miss_analysis.empty or "asset_id" not in miss_analysis.columns:
        return pd.DataFrame(columns=columns)

    asset_ids = sorted({str(value) for value in miss_analysis["asset_id"].dropna().unique()})
    start_date = str(pd.to_datetime(miss_analysis["segment_start_date"], errors="coerce").min().date())
    end_date = str(pd.to_datetime(miss_analysis["double_confirm_date"], errors="coerce").max().date())
    if not asset_ids or start_date == "NaT" or end_date == "NaT":
        return pd.DataFrame(columns=columns)

    frames: list[pd.DataFrame] = []
    chunk_size = 500
    with connect(service) as conn:
        for offset in range(0, len(asset_ids), chunk_size):
            chunk = asset_ids[offset : offset + chunk_size]
            placeholders = ", ".join(["%s"] * len(chunk))
            sql = f"""
                SELECT
                    trade_date::text AS trade_date,
                    asset_id,
                    rank,
                    score_total,
                    score_version,
                    score_components
                FROM factor.stock_score_daily
                WHERE score_version = %s
                  AND trade_date BETWEEN %s AND %s
                  AND asset_id IN ({placeholders})
                ORDER BY asset_id, trade_date
            """
            rows = fetch_all(conn, sql, [score_version, start_date, end_date, *chunk])
            frames.append(pd.DataFrame(rows))

    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    for column in columns:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame.loc[:, columns]


def build_strong_winner_topn_attribution_from_frames(
    *,
    miss_analysis: pd.DataFrame,
    score_rows: pd.DataFrame,
    topn_thresholds: list[int] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    thresholds = sorted({int(value) for value in (topn_thresholds or DEFAULT_TOPN_THRESHOLDS) if int(value) > 0})
    analysis = _normalize_miss_analysis(miss_analysis)
    scores = _normalize_score_rows(score_rows)

    attribution_internal = _build_attribution(analysis, scores, thresholds)
    threshold_sensitivity = _build_threshold_sensitivity(analysis, attribution_internal, thresholds)
    component_gap = _build_component_gap(analysis, attribution_internal, scores)
    attribution = attribution_internal.drop(columns=["_best_score_components"], errors="ignore")
    report = _render_report(attribution, threshold_sensitivity, component_gap)

    result: dict[str, Any] = {
        "attribution": attribution,
        "threshold_sensitivity": threshold_sensitivity,
        "component_gap": component_gap,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "attribution": output / "strong_winner_topn_source_attribution.csv",
            "threshold_sensitivity": output / "strong_winner_topn_threshold_sensitivity.csv",
            "component_gap": output / "strong_winner_score_component_gap.csv",
            "report": output / "strong_winner_topn_source_attribution_report.md",
        }
        attribution.to_csv(paths["attribution"], index=False)
        threshold_sensitivity.to_csv(paths["threshold_sensitivity"], index=False)
        component_gap.to_csv(paths["component_gap"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _normalize_miss_analysis(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in [
        "winner_id",
        "asset_id",
        "ts_code",
        "stock_name",
        "segment_start_date",
        "double_confirm_date",
        "capture_status",
        "miss_reason",
    ]:
        if column not in normalized.columns:
            normalized[column] = ""
    normalized["asset_id"] = normalized["asset_id"].astype(str)
    normalized["segment_start_date"] = pd.to_datetime(normalized["segment_start_date"], errors="coerce")
    normalized["double_confirm_date"] = pd.to_datetime(normalized["double_confirm_date"], errors="coerce")
    return normalized


def _normalize_score_rows(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ["trade_date", "asset_id", "rank", "score_total", "score_components"]:
        if column not in normalized.columns:
            normalized[column] = np.nan
    normalized["asset_id"] = normalized["asset_id"].astype(str)
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["rank"] = pd.to_numeric(normalized["rank"], errors="coerce")
    normalized["score_total"] = pd.to_numeric(normalized["score_total"], errors="coerce")
    return normalized


def _build_attribution(
    analysis: pd.DataFrame,
    scores: pd.DataFrame,
    thresholds: list[int],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped_scores = {asset_id: group for asset_id, group in scores.groupby("asset_id", sort=False)}
    for row in analysis.to_dict("records"):
        asset_scores = grouped_scores.get(str(row.get("asset_id")), pd.DataFrame())
        pre_scores = _pre_double_scores(asset_scores, row)
        best = _best_rank_row(pre_scores)
        best_rank = _number_or_nan(best.get("rank")) if best else np.nan
        best_score_total = _number_or_nan(best.get("score_total")) if best else np.nan
        topn_attribution = _classify_topn_attribution(best_rank)
        max_threshold = _max_threshold_captured(best_rank, thresholds)
        output_row = {column: row.get(column, "") for column in ATTRIBUTION_COLUMNS if column in row}
        output_row.update(
            {
                "has_score_pre_double": bool(best),
                "best_pre_double_rank": best_rank,
                "best_score_date": _date_string(best.get("trade_date")) if best else "",
                "best_score_total": best_score_total,
                "topn_attribution": topn_attribution,
                "max_threshold_captured": max_threshold,
                "weakest_components": _weakest_components(best.get("score_components") if best else {}),
                "_best_score_components": best.get("score_components") if best else {},
            }
        )
        rows.append(output_row)
    attribution = pd.DataFrame(rows)
    if attribution.empty:
        return pd.DataFrame(columns=[*ATTRIBUTION_COLUMNS, "_best_score_components"])
    for column in ATTRIBUTION_COLUMNS:
        if column not in attribution.columns:
            attribution[column] = ""
    if "_best_score_components" not in attribution.columns:
        attribution["_best_score_components"] = {}
    return attribution.loc[:, [*ATTRIBUTION_COLUMNS, "_best_score_components"]]


def _build_threshold_sensitivity(
    analysis: pd.DataFrame,
    attribution: pd.DataFrame,
    thresholds: list[int],
) -> pd.DataFrame:
    target = attribution[attribution["miss_reason"].fillna("") == "not_in_topn_diagnostics"].copy()
    total_targets = len(target)
    total_winners = len(analysis)
    captured_pre_double = int((analysis["capture_status"].fillna("") == "captured_pre_double").sum())
    rows: list[dict[str, Any]] = []
    ranks = pd.to_numeric(target["best_pre_double_rank"], errors="coerce") if not target.empty else pd.Series(dtype=float)
    for top_n in thresholds:
        additional = int((ranks <= top_n).sum())
        rows.append(
            {
                "top_n": int(top_n),
                "not_in_topn_target_count": int(total_targets),
                "additional_captured_count": additional,
                "additional_capture_rate_of_not_in_topn": additional / total_targets if total_targets else 0.0,
                "cumulative_capture_count": captured_pre_double + additional,
                "cumulative_capture_rate_all_winners": (captured_pre_double + additional) / total_winners if total_winners else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _build_component_gap(
    analysis: pd.DataFrame,
    attribution: pd.DataFrame,
    scores: pd.DataFrame,
) -> pd.DataFrame:
    target_components = _best_components_by_group(
        attribution[attribution["miss_reason"].fillna("") == "not_in_topn_diagnostics"],
    )
    captured_rows = analysis[analysis["capture_status"].fillna("") == "captured_pre_double"]
    captured_attribution = _build_attribution(captured_rows, scores, [50])
    captured_components = _best_components_by_group(captured_attribution)

    components = sorted(set(target_components.columns) | set(captured_components.columns))
    rows: list[dict[str, Any]] = []
    for component in components:
        miss_series = pd.to_numeric(target_components.get(component), errors="coerce")
        captured_series = pd.to_numeric(captured_components.get(component), errors="coerce")
        miss_avg = float(miss_series.mean()) if not miss_series.dropna().empty else np.nan
        captured_avg = float(captured_series.mean()) if not captured_series.dropna().empty else np.nan
        rows.append(
            {
                "component": component,
                "miss_avg": miss_avg,
                "captured_avg": captured_avg,
                "miss_minus_captured": miss_avg - captured_avg if np.isfinite(miss_avg) and np.isfinite(captured_avg) else np.nan,
                "miss_sample_count": int(miss_series.notna().sum()),
                "captured_sample_count": int(captured_series.notna().sum()),
            }
        )
    gap = pd.DataFrame(rows)
    if gap.empty:
        return pd.DataFrame(
            columns=[
                "component",
                "miss_avg",
                "captured_avg",
                "miss_minus_captured",
                "miss_sample_count",
                "captured_sample_count",
            ]
        )
    return gap.sort_values(["miss_minus_captured", "component"], na_position="last").reset_index(drop=True)


def _best_components_by_group(attribution: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for raw in attribution.get("_best_score_components", pd.Series(dtype=object)).to_list():
        parsed = _parse_components(raw)
        numeric = {key: float(value) for key, value in parsed.items() if _is_number(value)}
        if numeric:
            rows.append(numeric)
    return pd.DataFrame(rows)


def _pre_double_scores(asset_scores: pd.DataFrame, row: dict[str, Any]) -> pd.DataFrame:
    if asset_scores.empty:
        return asset_scores
    start = row.get("segment_start_date")
    end = row.get("double_confirm_date")
    return asset_scores[(asset_scores["trade_date"] >= start) & (asset_scores["trade_date"] < end)].copy()


def _best_rank_row(pre_scores: pd.DataFrame) -> dict[str, Any] | None:
    if pre_scores.empty:
        return None
    ranked = pre_scores.dropna(subset=["rank"]).sort_values(["rank", "trade_date"], ascending=[True, True])
    if ranked.empty:
        return None
    return ranked.iloc[0].to_dict()


def _classify_topn_attribution(best_rank: float) -> str:
    if not np.isfinite(best_rank):
        return "no_score_pre_double"
    if best_rank <= 50:
        return "would_enter_top50"
    if best_rank <= 100:
        return "near_miss_51_100"
    if best_rank <= 200:
        return "near_miss_101_200"
    if best_rank <= 500:
        return "rank_201_500"
    return "rank_gt_500"


def _max_threshold_captured(best_rank: float, thresholds: list[int]) -> int | str:
    if not np.isfinite(best_rank):
        return ""
    for threshold in thresholds:
        if best_rank <= threshold:
            return int(threshold)
    return ""


def _weakest_components(raw_components: Any, *, limit: int = 3) -> str:
    parsed = _parse_components(raw_components)
    numeric = [(key, float(value)) for key, value in parsed.items() if _is_number(value)]
    numeric.sort(key=lambda item: (item[1], item[0]))
    return ";".join(f"{key}={value:.2f}" for key, value in numeric[:limit])


def _parse_components(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return {}
    if isinstance(raw, str):
        if raw.strip() == "":
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _number_or_nan(value: Any) -> float:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(number) if pd.notna(number) else np.nan


def _is_number(value: Any) -> bool:
    try:
        return np.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _date_string(value: Any) -> str:
    date = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(date) else str(date.date())


def _render_report(
    attribution: pd.DataFrame,
    threshold_sensitivity: pd.DataFrame,
    component_gap: pd.DataFrame,
) -> str:
    target = attribution[attribution["miss_reason"].fillna("") == "not_in_topn_diagnostics"]
    counts = target["topn_attribution"].value_counts().to_dict() if not target.empty else {}
    lines = [
        "# Strong Winner TopN Source Attribution v1",
        "",
        "## 1. 研究目标",
        "本报告只诊断强票在翻倍前为什么未进入 watchlist TopN，不接策略打分、不生成交易建议。",
        "",
        "## 2. TopN 归因分布",
    ]
    if counts:
        for label, count in counts.items():
            lines.append(f"- {label}: {count}")
    else:
        lines.append("- 无 not_in_topn_diagnostics 样本。")
    lines.extend(["", "## 3. TopN 阈值敏感性"])
    for row in threshold_sensitivity.to_dict("records"):
        lines.append(
            f"- Top{int(row['top_n'])}: 额外捕获 {int(row['additional_captured_count'])}，"
            f"全样本累计捕获率 {row['cumulative_capture_rate_all_winners']:.2%}"
        )
    lines.extend(["", "## 4. Score Component Gap"])
    if component_gap.empty:
        lines.append("- 无可比较 score_components。")
    else:
        for row in component_gap.head(10).to_dict("records"):
            delta = row.get("miss_minus_captured")
            delta_text = "NA" if pd.isna(delta) else f"{delta:.2f}"
            lines.append(f"- {row['component']}: miss-captured={delta_text}")
    lines.extend(
        [
            "",
            "## 5. 结论",
            "优先看 near_miss 与 component gap，再决定是扩大 TopN、修分项权重，还是补全得分覆盖。",
        ]
    )
    return "\n".join(lines) + "\n"
