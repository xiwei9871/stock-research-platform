from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


DEFAULT_TOPN_THRESHOLDS = [50, 100, 200, 500]
FORWARD_HORIZONS = [5, 10, 20, 30, 40, 60]


def run_strong_winner_discovery_pool(
    *,
    start_date: str,
    end_date: str,
    score_version: str = "manual_v1",
    adjust_type: str = "qfq",
    topn_thresholds: list[int] | None = None,
    strong_winner_path: str | Path = "outputs/research/strong_winner_taxonomy_v2_2025_to_now.csv",
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    thresholds = _normalize_thresholds(topn_thresholds)
    score_rows = load_score_rows_for_discovery_pool(
        start_date=start_date,
        end_date=end_date,
        score_version=score_version,
        max_top_n=max(thresholds),
        service=service,
    )
    market_bars = load_market_bars_for_discovery_pool(
        score_rows=score_rows,
        start_date=start_date,
        adjust_type=adjust_type,
        service=service,
    )
    strong_winner_taxonomy = (
        pd.read_csv(strong_winner_path, low_memory=False)
        if strong_winner_path and Path(strong_winner_path).exists()
        else pd.DataFrame()
    )
    return build_strong_winner_discovery_pool_from_frames(
        score_rows=score_rows,
        market_bars=market_bars,
        strong_winner_taxonomy=strong_winner_taxonomy,
        topn_thresholds=thresholds,
        output_dir=output_dir,
    )


def load_score_rows_for_discovery_pool(
    *,
    start_date: str,
    end_date: str,
    score_version: str,
    max_top_n: int,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
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
          AND rank <= %s
        ORDER BY trade_date, rank, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [score_version, start_date, end_date, int(max_top_n)])
    return pd.DataFrame(rows)


def load_market_bars_for_discovery_pool(
    *,
    score_rows: pd.DataFrame,
    start_date: str,
    adjust_type: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    asset_ids = sorted({str(value) for value in score_rows.get("asset_id", pd.Series(dtype=str)).dropna().unique()})
    columns = ["trade_date", "asset_id", "close", "high", "low"]
    if not asset_ids:
        return pd.DataFrame(columns=columns)

    frames: list[pd.DataFrame] = []
    chunk_size = 500
    with connect(service) as conn:
        for offset in range(0, len(asset_ids), chunk_size):
            chunk = asset_ids[offset : offset + chunk_size]
            placeholders = ", ".join(["%s"] * len(chunk))
            sql = f"""
                SELECT trade_date::text AS trade_date, asset_id, close, high, low
                FROM market_daily_bar
                WHERE adjust_type = %s
                  AND trade_date >= %s
                  AND asset_id IN ({placeholders})
                ORDER BY asset_id, trade_date
            """
            rows = fetch_all(conn, sql, [adjust_type, start_date, *chunk])
            frames.append(pd.DataFrame(rows))
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    for column in columns:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame.loc[:, columns]


def build_strong_winner_discovery_pool_from_frames(
    *,
    score_rows: pd.DataFrame,
    market_bars: pd.DataFrame,
    strong_winner_taxonomy: pd.DataFrame | None = None,
    topn_thresholds: list[int] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    thresholds = _normalize_thresholds(topn_thresholds)
    detail = _build_detail(score_rows, market_bars, strong_winner_taxonomy, thresholds)
    pool_effectiveness = _build_pool_effectiveness(detail, thresholds)
    capture_by_type = _build_capture_by_type(detail, strong_winner_taxonomy, thresholds)
    report = _render_report(pool_effectiveness, capture_by_type, thresholds)

    result: dict[str, Any] = {
        "detail": detail,
        "pool_effectiveness": pool_effectiveness,
        "capture_by_type": capture_by_type,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "strong_winner_discovery_pool_detail.csv",
            "pool_effectiveness": output / "strong_winner_discovery_pool_effectiveness.csv",
            "capture_by_type": output / "strong_winner_discovery_pool_capture_by_type.csv",
            "report": output / "strong_winner_discovery_pool_report.md",
        }
        detail.to_csv(paths["detail"], index=False)
        pool_effectiveness.to_csv(paths["pool_effectiveness"], index=False)
        capture_by_type.to_csv(paths["capture_by_type"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _build_detail(
    score_rows: pd.DataFrame,
    market_bars: pd.DataFrame,
    strong_winner_taxonomy: pd.DataFrame | None,
    thresholds: list[int],
) -> pd.DataFrame:
    scores = _normalize_scores(score_rows)
    bars = _normalize_bars(market_bars)
    if scores.empty:
        return _empty_detail(thresholds)

    detail = scores.copy()
    max_threshold = max(thresholds)
    detail = detail[detail["rank"] <= max_threshold].copy()
    detail["score_rank"] = detail["rank"]
    detail["score_components"] = detail["score_components"].map(_parse_components)
    for threshold in thresholds:
        detail[f"score_top{threshold}_pool"] = detail["rank"] <= threshold
    detail["discovery_rank_band"] = detail["rank"].map(_rank_band)

    metrics = _forward_metrics(detail, bars)
    detail = detail.merge(metrics, on=["trade_date", "asset_id"], how="left")
    winner_hits = _winner_hits_by_candidate(detail, strong_winner_taxonomy)
    detail = detail.merge(winner_hits, on=["trade_date", "asset_id"], how="left")
    detail["winner_type_hits"] = detail["winner_type_hits"].fillna("")
    detail["strong_winner_hit"] = detail["winner_type_hits"].ne("")
    return detail


def _normalize_scores(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ["trade_date", "asset_id", "ts_code", "stock_name", "rank", "score_total", "score_components"]:
        if column not in normalized.columns:
            normalized[column] = np.nan
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["asset_id"] = normalized["asset_id"].astype(str)
    normalized["rank"] = pd.to_numeric(normalized["rank"], errors="coerce")
    normalized["score_total"] = pd.to_numeric(normalized["score_total"], errors="coerce")
    return normalized.dropna(subset=["trade_date", "asset_id", "rank"]).copy()


def _normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ["trade_date", "asset_id", "close", "high", "low"]:
        if column not in normalized.columns:
            normalized[column] = np.nan
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["asset_id"] = normalized["asset_id"].astype(str)
    for column in ["close", "high", "low"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized.dropna(subset=["trade_date", "asset_id"]).sort_values(["asset_id", "trade_date"])


def _forward_metrics(detail: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    metric_rows: list[dict[str, Any]] = []
    grouped_bars = {asset_id: group.reset_index(drop=True) for asset_id, group in bars.groupby("asset_id", sort=False)}
    for row in detail[["trade_date", "asset_id"]].to_dict("records"):
        asset_bars = grouped_bars.get(str(row["asset_id"]), pd.DataFrame())
        metric_rows.append(_candidate_forward_metrics(row["trade_date"], str(row["asset_id"]), asset_bars))
    return pd.DataFrame(metric_rows)


def _candidate_forward_metrics(trade_date: pd.Timestamp, asset_id: str, bars: pd.DataFrame) -> dict[str, Any]:
    base: dict[str, Any] = {"trade_date": trade_date, "asset_id": asset_id}
    for horizon in FORWARD_HORIZONS:
        base[f"future_{horizon}d_return"] = np.nan
    base["future_60d_max_drawdown"] = np.nan
    base["max_return_within_60d"] = np.nan
    base["hit_double_within_60d"] = False
    if bars.empty:
        return base

    current_idx = bars.index[bars["trade_date"] == trade_date]
    if len(current_idx) == 0:
        return base
    idx = int(current_idx[0])
    current_close = _safe_float(bars.loc[idx, "close"])
    if current_close is None or current_close == 0:
        return base
    future = bars.iloc[idx + 1 : idx + 61].copy()
    for horizon in FORWARD_HORIZONS:
        if len(future) >= horizon:
            close = _safe_float(future.iloc[horizon - 1]["close"])
            base[f"future_{horizon}d_return"] = close / current_close - 1 if close is not None else np.nan
    if not future.empty:
        lows = pd.to_numeric(future["low"], errors="coerce")
        highs = pd.to_numeric(future["high"], errors="coerce")
        base["future_60d_max_drawdown"] = float((lows / current_close - 1).min()) if not lows.dropna().empty else np.nan
        base["max_return_within_60d"] = float((highs / current_close - 1).max()) if not highs.dropna().empty else np.nan
        base["hit_double_within_60d"] = bool(base["max_return_within_60d"] >= 1.0)
    return base


def _winner_hits_by_candidate(detail: pd.DataFrame, taxonomy: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["trade_date", "asset_id", "winner_type_hits"]
    if taxonomy is None or taxonomy.empty or "asset_id" not in taxonomy.columns:
        return pd.DataFrame(columns=columns)
    winners = taxonomy.copy()
    for column in ["winner_type", "window_start", "window_end"]:
        if column not in winners.columns:
            winners[column] = ""
    winners["asset_id"] = winners["asset_id"].astype(str)
    winners["window_start"] = pd.to_datetime(winners["window_start"], errors="coerce")
    winners["window_end"] = pd.to_datetime(winners["window_end"], errors="coerce")
    candidates = detail[["trade_date", "asset_id"]].drop_duplicates().copy()
    merged = candidates.merge(
        winners[["asset_id", "winner_type", "window_start", "window_end"]],
        on="asset_id",
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame(columns=columns)
    active = merged[(merged["window_start"] <= merged["trade_date"]) & (merged["trade_date"] <= merged["window_end"])]
    if active.empty:
        return pd.DataFrame(columns=columns)
    hits = (
        active.groupby(["trade_date", "asset_id"], as_index=False)["winner_type"]
        .agg(lambda values: ",".join(sorted({str(value) for value in values if pd.notna(value)})))
        .rename(columns={"winner_type": "winner_type_hits"})
    )
    return hits.loc[:, columns]


def _build_pool_effectiveness(detail: pd.DataFrame, thresholds: list[int]) -> pd.DataFrame:
    rows = []
    for threshold in thresholds:
        pool_name = f"score_top{threshold}_pool"
        rows.append(_metric_row(detail[detail.get(pool_name, False)], "pool_name", pool_name))
    return pd.DataFrame(rows)


def _build_capture_by_type(
    detail: pd.DataFrame,
    taxonomy: pd.DataFrame | None,
    thresholds: list[int],
) -> pd.DataFrame:
    if taxonomy is None or taxonomy.empty or "winner_type" not in taxonomy.columns:
        return pd.DataFrame(columns=["winner_type", "pool_name", "total_winner_count", "captured_winner_count", "capture_rate"])
    winners = taxonomy.copy()
    winners["asset_id"] = winners["asset_id"].astype(str)
    winners["window_start"] = pd.to_datetime(winners.get("window_start"), errors="coerce")
    winners["window_end"] = pd.to_datetime(winners.get("window_end"), errors="coerce")
    candidate_columns = ["trade_date", "asset_id", *[f"score_top{threshold}_pool" for threshold in thresholds]]
    candidates = detail[candidate_columns].drop_duplicates().copy()
    merged = candidates.merge(
        winners[["winner_type", "asset_id", "window_start", "window_end"]],
        on="asset_id",
        how="inner",
    )
    active = (
        merged[(merged["window_start"] <= merged["trade_date"]) & (merged["trade_date"] <= merged["window_end"])]
        if not merged.empty
        else pd.DataFrame()
    )
    rows = []
    for winner_type, group in winners.groupby("winner_type", sort=True):
        total = int(group["asset_id"].nunique())
        for threshold in thresholds:
            pool_name = f"score_top{threshold}_pool"
            if active.empty:
                captured = 0
            else:
                pool_hits = active[(active["winner_type"].eq(winner_type)) & (active[pool_name].map(bool))]
                captured = int(pool_hits["asset_id"].nunique())
            rows.append(
                {
                    "winner_type": winner_type,
                    "pool_name": pool_name,
                    "total_winner_count": total,
                    "captured_winner_count": captured,
                    "capture_rate": captured / total if total else 0.0,
                }
            )
    return pd.DataFrame(rows)


def _metric_row(frame: pd.DataFrame, key_name: str, key_value: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        key_name: key_value,
        "sample_count": int(len(frame)),
        "unique_asset_count": int(frame["asset_id"].nunique()) if "asset_id" in frame.columns else 0,
        "strong_winner_hit_rate": float(frame["strong_winner_hit"].mean()) if len(frame) and "strong_winner_hit" in frame.columns else 0.0,
        "hit_double_within_60d_rate": float(frame["hit_double_within_60d"].mean()) if len(frame) and "hit_double_within_60d" in frame.columns else 0.0,
    }
    for horizon in FORWARD_HORIZONS:
        column = f"future_{horizon}d_return"
        row[f"avg_{column}"] = _mean(frame.get(column))
        row[f"win_rate_{horizon}d"] = _win_rate(frame.get(column))
    row["avg_future_60d_max_drawdown"] = _mean(frame.get("future_60d_max_drawdown"))
    row["avg_max_return_within_60d"] = _mean(frame.get("max_return_within_60d"))
    return row


def _render_report(pool_effectiveness: pd.DataFrame, capture_by_type: pd.DataFrame, thresholds: list[int]) -> str:
    lines = [
        "# Strong Winner Discovery Pool Report",
        "",
        "## 1. Scope",
        "本报告只构建 TopN 扩展影子发现池，用于诊断强票漏抓；不修改 must_watch，不生成交易建议。",
        "",
        "## 2. TopN Pools",
        f"- thresholds: {', '.join(str(value) for value in thresholds)}",
        "",
        "## 3. Pool Effectiveness",
        pool_effectiveness.to_markdown(index=False) if not pool_effectiveness.empty else "No pool rows.",
        "",
        "## 4. Strong Winner Capture by Type",
        capture_by_type.to_markdown(index=False) if not capture_by_type.empty else "No strong winner taxonomy rows.",
        "",
        "## 5. Interpretation",
        "- TopN 扩展只作为 discovery pool；后续需要用收益、回撤和强票捕获率共同判断噪音是否可接受。",
        "- 如果 Top200/Top500 明显提高强票捕获但回撤恶化，需要继续拆 high_elasticity_shadow，而不是并入低风险 must_watch。",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _normalize_thresholds(values: list[int] | None) -> list[int]:
    thresholds = sorted({int(value) for value in (values or DEFAULT_TOPN_THRESHOLDS) if int(value) > 0})
    return thresholds or DEFAULT_TOPN_THRESHOLDS


def _rank_band(rank: float) -> str:
    if pd.isna(rank):
        return "no_rank"
    rank_int = int(rank)
    if rank_int <= 50:
        return "top50"
    if rank_int <= 100:
        return "rank_51_100"
    if rank_int <= 200:
        return "rank_101_200"
    if rank_int <= 500:
        return "rank_201_500"
    return "rank_gt_500"


def _parse_components(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(value)
                return parsed if isinstance(parsed, dict) else {}
            except (ValueError, SyntaxError):
                return {}
    return {}


def _safe_float(value: Any) -> float | None:
    result = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(result) else float(result)


def _mean(series: Any) -> float:
    values = pd.to_numeric(series, errors="coerce") if series is not None else pd.Series(dtype=float)
    return float(values.mean()) if not values.dropna().empty else np.nan


def _win_rate(series: Any) -> float:
    values = pd.to_numeric(series, errors="coerce") if series is not None else pd.Series(dtype=float)
    values = values.dropna()
    return float((values > 0).mean()) if not values.empty else np.nan


def _empty_detail(thresholds: list[int]) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "ts_code",
        "stock_name",
        "rank",
        "score_rank",
        "score_total",
        "discovery_rank_band",
        "winner_type_hits",
        "strong_winner_hit",
    ]
    columns.extend(f"score_top{threshold}_pool" for threshold in thresholds)
    columns.extend(f"future_{horizon}d_return" for horizon in FORWARD_HORIZONS)
    columns.extend(["future_60d_max_drawdown", "max_return_within_60d", "hit_double_within_60d"])
    return pd.DataFrame(columns=columns)
