from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


DEFAULT_HORIZONS = [20, 60, 120, 250]


def build_strict_dimension_performance_review(
    *,
    quality_review: pd.DataFrame,
    bars: pd.DataFrame,
    start_date: str,
    end_date: str,
    horizons: list[int] | None = None,
) -> dict[str, pd.DataFrame]:
    selected_horizons = horizons or DEFAULT_HORIZONS
    strict_assets = _strict_assets_from_quality_review(quality_review)
    normalized_bars = _normalize_bars(bars)
    details = _build_details(
        strict_assets=strict_assets,
        bars=normalized_bars,
        start_date=start_date,
        end_date=end_date,
        horizons=selected_horizons,
    )
    summary = _build_summary(details, selected_horizons)
    chain_summary = _build_chain_summary(details, selected_horizons)
    return {"details": details, "summary": summary, "chain_summary": chain_summary}


def run_strict_dimension_performance_from_files(
    *,
    quality_review_csv: Path,
    output_dir: Path,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    service: str = SETTINGS.research_service,
    horizons: list[int] | None = None,
) -> dict[str, Path]:
    quality_review = pd.read_csv(quality_review_csv)
    strict_assets = _strict_assets_from_quality_review(quality_review)
    bars = load_market_bars_for_assets(
        asset_ids=sorted(strict_assets["asset_id"].dropna().astype(str).unique().tolist()),
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    report = build_strict_dimension_performance_review(
        quality_review=quality_review,
        bars=bars,
        start_date=start_date,
        end_date=end_date,
        horizons=horizons,
    )
    return write_strict_dimension_performance_artifacts(
        report=report,
        output_dir=output_dir,
        inputs={
            "quality_review_csv": str(quality_review_csv),
            "start_date": start_date,
            "end_date": end_date,
            "adjust_type": adjust_type,
            "service": service,
        },
        horizons=horizons or DEFAULT_HORIZONS,
    )


def load_market_bars_for_assets(
    *,
    asset_ids: list[str],
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["asset_id", "trade_date", "open", "high", "low", "close", "trade_status"])
    sql = """
    SELECT asset_id, trade_date, open, high, low, close, trade_status
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND trade_status = '1'
      AND trade_date BETWEEN %s AND %s
      AND asset_id = ANY(%s)
    ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date, asset_ids])
    return pd.DataFrame(rows)


def write_strict_dimension_performance_artifacts(
    *,
    report: dict[str, pd.DataFrame],
    output_dir: Path,
    inputs: dict[str, Any],
    horizons: list[int],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    details_path = output_dir / "strict_153_performance_details.csv"
    summary_path = output_dir / "strict_153_performance_summary.csv"
    chain_summary_path = output_dir / "strict_153_chain_summary.csv"
    markdown_path = output_dir / "summary.md"
    manifest_path = output_dir / "manifest.json"

    report["details"].to_csv(details_path, index=False)
    report["summary"].to_csv(summary_path, index=False)
    report["chain_summary"].to_csv(chain_summary_path, index=False)
    manifest = {
        "strict_asset_count": int(len(report["details"])),
        "data_status_counts": report["details"]["data_status"].value_counts(dropna=False).to_dict()
        if not report["details"].empty
        else {},
        "horizons": horizons,
        "inputs": inputs,
        "files": {
            "details": details_path.name,
            "summary": summary_path.name,
            "chain_summary": chain_summary_path.name,
            "markdown": markdown_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(report, manifest, horizons), encoding="utf-8")
    return {
        "details": details_path,
        "summary": summary_path,
        "chain_summary": chain_summary_path,
        "markdown": markdown_path,
        "manifest": manifest_path,
    }


def _strict_assets_from_quality_review(quality_review: pd.DataFrame) -> pd.DataFrame:
    frame = quality_review.copy()
    for column in [
        "asset_id",
        "stock_name",
        "trade_date",
        "primary_chain_id",
        "primary_chain_name",
        "matched_bottleneck_dimensions",
    ]:
        if column not in frame.columns:
            frame[column] = ""
    frame["matched_bottleneck_dimensions"] = frame["matched_bottleneck_dimensions"].astype("string").fillna("")
    strict = frame[frame["matched_bottleneck_dimensions"].str.strip().ne("")].copy()
    if strict.empty:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "stock_name",
                "first_hit_date",
                "hit_count",
                "primary_chain_id",
                "primary_chain_name",
                "matched_bottleneck_dimensions",
            ]
        )
    strict["trade_date"] = pd.to_datetime(strict["trade_date"], errors="coerce")
    strict = strict.dropna(subset=["trade_date"]).sort_values(["asset_id", "trade_date"])
    grouped = strict.groupby("asset_id", sort=True)
    rows = []
    for asset_id, group in grouped:
        first = group.iloc[0]
        rows.append(
            {
                "asset_id": str(asset_id),
                "stock_name": str(first.get("stock_name", "")),
                "first_hit_date": first["trade_date"].strftime("%Y-%m-%d"),
                "hit_count": int(len(group)),
                "primary_chain_id": str(first.get("primary_chain_id", "")),
                "primary_chain_name": str(first.get("primary_chain_name", "")),
                "matched_bottleneck_dimensions": str(first.get("matched_bottleneck_dimensions", "")),
            }
        )
    return pd.DataFrame(rows)


def _build_details(
    *,
    strict_assets: pd.DataFrame,
    bars: pd.DataFrame,
    start_date: str,
    end_date: str,
    horizons: list[int],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    bars_by_asset = {
        asset_id: group.sort_values("trade_date").reset_index(drop=True)
        for asset_id, group in bars.groupby("asset_id", sort=False)
    }
    for asset in strict_assets.to_dict("records"):
        asset_id = str(asset["asset_id"])
        asset_bars = bars_by_asset.get(asset_id, pd.DataFrame(columns=bars.columns))
        row: dict[str, Any] = {
            **asset,
            "analysis_start_date": start_date,
            "analysis_end_date": end_date,
        }
        row.update(_period_metrics(asset_bars, start_date, "period"))
        row.update(_period_metrics(asset_bars, str(asset["first_hit_date"]), "since_first_hit", entry_prefix="hit"))
        for horizon in horizons:
            row.update(_horizon_metrics(asset_bars, str(asset["first_hit_date"]), horizon))
        row["data_status"] = "ok" if row.get("period_entry_date") else "missing_bars"
        rows.append(row)
    return pd.DataFrame(rows, columns=_detail_columns(horizons))


def _period_metrics(
    bars: pd.DataFrame,
    entry_date: str,
    metric_prefix: str,
    entry_prefix: str = "period",
) -> dict[str, Any]:
    frame = bars[bars["trade_date"] >= pd.to_datetime(entry_date)].sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        return {
            f"{entry_prefix}_entry_date": "",
            f"{entry_prefix}_entry_close": pd.NA,
            f"{metric_prefix}_last_date": "",
            f"{metric_prefix}_last_close": pd.NA,
            f"{metric_prefix}_return": pd.NA,
            f"{metric_prefix}_max_drawdown": pd.NA,
        }
    return {
        f"{entry_prefix}_entry_date": frame.iloc[0]["trade_date"].strftime("%Y-%m-%d"),
        f"{entry_prefix}_entry_close": _round(frame.iloc[0]["close"]),
        f"{metric_prefix}_last_date": frame.iloc[-1]["trade_date"].strftime("%Y-%m-%d"),
        f"{metric_prefix}_last_close": _round(frame.iloc[-1]["close"]),
        f"{metric_prefix}_return": _round(float(frame.iloc[-1]["close"]) / float(frame.iloc[0]["close"]) - 1.0),
        f"{metric_prefix}_max_drawdown": _round(_max_drawdown(frame["close"])),
    }


def _horizon_metrics(bars: pd.DataFrame, entry_date: str, horizon: int) -> dict[str, Any]:
    frame = bars[bars["trade_date"] >= pd.to_datetime(entry_date)].sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        return _missing_horizon(horizon, "missing_entry_bar")
    if len(frame) <= horizon:
        return _missing_horizon(horizon, "partial")
    window = frame.iloc[: horizon + 1]
    return {
        f"return_{horizon}d": _round(float(window.iloc[-1]["close"]) / float(window.iloc[0]["close"]) - 1.0),
        f"max_drawdown_{horizon}d": _round(_max_drawdown(window["close"])),
        f"horizon_{horizon}d_status": "complete",
    }


def _missing_horizon(horizon: int, status: str) -> dict[str, Any]:
    return {
        f"return_{horizon}d": pd.NA,
        f"max_drawdown_{horizon}d": pd.NA,
        f"horizon_{horizon}d_status": status,
    }


def _build_summary(details: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    row: dict[str, Any] = {"group": "strict_dimension_assets", "asset_count": int(len(details))}
    ok = details[details["data_status"].eq("ok")] if not details.empty else details
    row["ok_count"] = int(len(ok))
    for column in ["period_return", "period_max_drawdown", "since_first_hit_return", "since_first_hit_max_drawdown"]:
        values = pd.to_numeric(ok[column], errors="coerce") if column in ok.columns else pd.Series(dtype=float)
        row[f"mean_{column}"] = _round_or_na(values.mean())
        row[f"median_{column}"] = _round_or_na(values.median())
        if column.endswith("return"):
            row[f"win_rate_{column}"] = _round_or_na((values > 0).mean())
    for horizon in horizons:
        complete = ok[f"horizon_{horizon}d_status"].eq("complete") if f"horizon_{horizon}d_status" in ok.columns else pd.Series(dtype=bool)
        complete_rows = ok[complete].copy()
        returns = (
            pd.to_numeric(complete_rows[f"return_{horizon}d"], errors="coerce")
            if f"return_{horizon}d" in complete_rows.columns
            else pd.Series(dtype=float)
        )
        drawdowns = (
            pd.to_numeric(complete_rows[f"max_drawdown_{horizon}d"], errors="coerce")
            if f"max_drawdown_{horizon}d" in complete_rows.columns
            else pd.Series(dtype=float)
        )
        row[f"complete_count_{horizon}d"] = int(complete.sum())
        row[f"mean_return_{horizon}d"] = _round_or_na(returns.mean())
        row[f"median_return_{horizon}d"] = _round_or_na(returns.median())
        row[f"win_rate_{horizon}d"] = _round_or_na((returns > 0).mean())
        row[f"mean_max_drawdown_{horizon}d"] = _round_or_na(drawdowns.mean())
    return pd.DataFrame([row])


def _build_chain_summary(details: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    if details.empty:
        return pd.DataFrame(columns=["primary_chain_id", "primary_chain_name", "asset_count"])
    rows = []
    for (chain_id, chain_name), group in details.groupby(["primary_chain_id", "primary_chain_name"], dropna=False, sort=True):
        row: dict[str, Any] = {
            "primary_chain_id": chain_id,
            "primary_chain_name": chain_name,
            "asset_count": int(len(group)),
            "mean_since_first_hit_return": _round_or_na(pd.to_numeric(group["since_first_hit_return"], errors="coerce").mean()),
            "median_since_first_hit_return": _round_or_na(pd.to_numeric(group["since_first_hit_return"], errors="coerce").median()),
            "mean_since_first_hit_max_drawdown": _round_or_na(
                pd.to_numeric(group["since_first_hit_max_drawdown"], errors="coerce").mean()
            ),
        }
        for horizon in horizons:
            complete_rows = group[group[f"horizon_{horizon}d_status"].eq("complete")]
            values = pd.to_numeric(complete_rows[f"return_{horizon}d"], errors="coerce")
            row[f"complete_count_{horizon}d"] = int(len(complete_rows))
            row[f"mean_return_{horizon}d"] = _round_or_na(values.mean())
            row[f"win_rate_{horizon}d"] = _round_or_na((values > 0).mean())
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["asset_count", "primary_chain_id"], ascending=[False, True])


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    normalized = bars.copy()
    for column in ["asset_id", "trade_date", "close"]:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized["asset_id"] = normalized["asset_id"].astype("string").fillna("")
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
    return normalized.dropna(subset=["trade_date", "close"])[normalized["asset_id"].ne("")].sort_values(["asset_id", "trade_date"])


def _max_drawdown(close: pd.Series) -> float:
    values = pd.to_numeric(close, errors="coerce").dropna()
    if values.empty:
        return float("nan")
    running_peak = values.cummax()
    drawdown = values / running_peak - 1.0
    return float(drawdown.min())


def _detail_columns(horizons: list[int]) -> list[str]:
    columns = [
        "asset_id",
        "stock_name",
        "first_hit_date",
        "hit_count",
        "primary_chain_id",
        "primary_chain_name",
        "matched_bottleneck_dimensions",
        "analysis_start_date",
        "analysis_end_date",
        "period_entry_date",
        "period_entry_close",
        "period_last_date",
        "period_last_close",
        "period_return",
        "period_max_drawdown",
        "hit_entry_date",
        "hit_entry_close",
        "since_first_hit_last_date",
        "since_first_hit_last_close",
        "since_first_hit_return",
        "since_first_hit_max_drawdown",
    ]
    for horizon in horizons:
        columns.extend([f"return_{horizon}d", f"max_drawdown_{horizon}d", f"horizon_{horizon}d_status"])
    columns.append("data_status")
    return columns


def _render_markdown(report: dict[str, pd.DataFrame], manifest: dict[str, Any], horizons: list[int]) -> str:
    summary = report["summary"].iloc[0].to_dict() if not report["summary"].empty else {}
    lines = [
        "# Tech Bottleneck Strict Dimension Performance",
        "",
        "This file summarizes performance for assets with non-empty matched_bottleneck_dimensions.",
        "",
        f"- strict_asset_count: {manifest['strict_asset_count']}",
        f"- data_status_counts: {manifest['data_status_counts']}",
        f"- start_date: {manifest['inputs'].get('start_date')}",
        f"- end_date: {manifest['inputs'].get('end_date')}",
        "",
        "## Summary",
        "",
        f"- period mean return: {summary.get('mean_period_return')}",
        f"- period median return: {summary.get('median_period_return')}",
        f"- period mean max drawdown: {summary.get('mean_period_max_drawdown')}",
        f"- since first hit mean return: {summary.get('mean_since_first_hit_return')}",
        f"- since first hit median return: {summary.get('median_since_first_hit_return')}",
        f"- since first hit mean max drawdown: {summary.get('mean_since_first_hit_max_drawdown')}",
        "",
        "## Horizons",
        "",
    ]
    for horizon in horizons:
        lines.append(
            f"- {horizon}D complete: {summary.get(f'complete_count_{horizon}d')} "
            f"mean_return: {summary.get(f'mean_return_{horizon}d')} "
            f"win_rate: {summary.get(f'win_rate_{horizon}d')} "
            f"mean_max_drawdown: {summary.get(f'mean_max_drawdown_{horizon}d')}"
        )
    return "\n".join(lines)


def _round(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    return round(float(value), 6)


def _round_or_na(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    return _round(value)
