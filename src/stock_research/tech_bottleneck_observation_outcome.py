from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_HORIZONS = [120, 250, 500]
OUTCOME_BASE_COLUMNS = [
    "comparison_group",
    "asset_id",
    "stock_name",
    "observation_start_date",
    "source_trade_date",
    "product_family",
    "evidence_quality_score",
    "entry_date",
    "entry_close",
]


def build_observation_outcome(
    *,
    comparison_groups: pd.DataFrame,
    bars: pd.DataFrame,
    benchmark_asset_id: str | None,
    horizons: list[int] | None = None,
) -> dict[str, pd.DataFrame]:
    selected_horizons = horizons or DEFAULT_HORIZONS
    normalized_groups = _normalize_comparison_groups(comparison_groups)
    normalized_bars = _normalize_bars(bars)
    outcomes = _build_outcomes(
        comparison_groups=normalized_groups,
        bars=normalized_bars,
        benchmark_asset_id=benchmark_asset_id,
        horizons=selected_horizons,
    )
    group_summary = _build_group_summary(outcomes=outcomes, horizons=selected_horizons)
    return {"outcomes": outcomes, "group_summary": group_summary}


def run_observation_outcome_from_files(
    *,
    comparison_groups_csv: Path,
    bars_csv: Path,
    output_dir: Path,
    source_manifest_path: Path | None,
    benchmark_asset_id: str | None,
    horizons: list[int] | None = None,
) -> dict[str, Path]:
    comparison_groups = pd.read_csv(comparison_groups_csv)
    bars = pd.read_csv(bars_csv)
    selected_horizons = horizons or DEFAULT_HORIZONS
    report = build_observation_outcome(
        comparison_groups=comparison_groups,
        bars=bars,
        benchmark_asset_id=benchmark_asset_id,
        horizons=selected_horizons,
    )
    inputs = {
        "comparison_groups_csv": str(comparison_groups_csv),
        "bars_csv": str(bars_csv),
        "source_manifest_path": str(source_manifest_path) if source_manifest_path else "",
        "source_manifest": _load_json(source_manifest_path),
    }
    return write_observation_outcome_artifacts(
        report=report,
        output_dir=output_dir,
        inputs=inputs,
        benchmark_asset_id=benchmark_asset_id,
        horizons=selected_horizons,
    )


def write_observation_outcome_artifacts(
    *,
    report: dict[str, pd.DataFrame],
    output_dir: Path,
    inputs: dict[str, Any],
    benchmark_asset_id: str | None,
    horizons: list[int],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outcomes_path = output_dir / "observation_outcomes.csv"
    group_summary_path = output_dir / "group_summary.csv"
    summary_path = output_dir / "summary.md"
    manifest_path = output_dir / "manifest.json"
    report["outcomes"].to_csv(outcomes_path, index=False)
    report["group_summary"].to_csv(group_summary_path, index=False)
    manifest = {
        "outcome_row_count": int(len(report["outcomes"])),
        "comparison_group_counts": report["outcomes"]["comparison_group"].value_counts().to_dict()
        if not report["outcomes"].empty
        else {},
        "benchmark_asset_id": benchmark_asset_id or "",
        "horizons": horizons,
        "inputs": inputs,
        "files": {
            "outcomes": outcomes_path.name,
            "group_summary": group_summary_path.name,
            "summary": summary_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(_render_summary(manifest, report["group_summary"], horizons), encoding="utf-8")
    return {
        "outcomes": outcomes_path,
        "group_summary": group_summary_path,
        "summary": summary_path,
        "manifest": manifest_path,
    }


def _build_outcomes(
    *,
    comparison_groups: pd.DataFrame,
    bars: pd.DataFrame,
    benchmark_asset_id: str | None,
    horizons: list[int],
) -> pd.DataFrame:
    if comparison_groups.empty:
        return pd.DataFrame(columns=_outcome_columns(horizons))
    bars_by_asset = {
        asset_id: frame.sort_values("trade_date").reset_index(drop=True)
        for asset_id, frame in bars.groupby("asset_id", sort=False)
    }
    benchmark_bars = bars_by_asset.get(benchmark_asset_id, pd.DataFrame()) if benchmark_asset_id else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for candidate in comparison_groups.to_dict("records"):
        asset_id = str(candidate["asset_id"])
        start_date = str(candidate["observation_start_date"])
        asset_bars = bars_by_asset.get(asset_id, pd.DataFrame(columns=bars.columns))
        row = {
            "comparison_group": str(candidate["comparison_group"]),
            "asset_id": asset_id,
            "stock_name": str(candidate["stock_name"]),
            "observation_start_date": start_date,
            "source_trade_date": str(candidate["source_trade_date"]),
            "product_family": str(candidate["product_family"]),
            "evidence_quality_score": int(candidate["evidence_quality_score"]),
        }
        row.update(_horizon_metrics(asset_bars, benchmark_bars, start_date, horizons))
        rows.append(row)
    return pd.DataFrame(rows, columns=_outcome_columns(horizons))


def _horizon_metrics(
    asset_bars: pd.DataFrame,
    benchmark_bars: pd.DataFrame,
    start_date: str,
    horizons: list[int],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    frame = asset_bars[asset_bars["trade_date"] >= pd.to_datetime(start_date)].sort_values("trade_date").reset_index(drop=True)
    benchmark_frame = (
        benchmark_bars[benchmark_bars["trade_date"] >= pd.to_datetime(start_date)].sort_values("trade_date").reset_index(drop=True)
        if not benchmark_bars.empty
        else pd.DataFrame()
    )
    if frame.empty:
        metrics["entry_date"] = ""
        metrics["entry_close"] = pd.NA
        for horizon in horizons:
            _set_missing_horizon(metrics, horizon, "missing_entry_bar")
        return metrics
    entry_date = frame.iloc[0]["trade_date"].strftime("%Y-%m-%d")
    entry_close = float(frame.iloc[0]["close"])
    metrics["entry_date"] = entry_date
    metrics["entry_close"] = entry_close
    for horizon in horizons:
        if len(frame) <= horizon:
            _set_missing_horizon(metrics, horizon, "partial")
            continue
        window = frame.iloc[: horizon + 1]
        horizon_return = float(window.iloc[-1]["close"]) / entry_close - 1.0
        relative_path = window["close"].astype(float) / entry_close - 1.0
        benchmark_return = _benchmark_return(benchmark_frame, horizon)
        metrics[f"return_{horizon}d"] = _round(horizon_return)
        metrics[f"benchmark_return_{horizon}d"] = _round_or_na(benchmark_return)
        metrics[f"excess_return_{horizon}d"] = _round(horizon_return - benchmark_return) if not pd.isna(benchmark_return) else pd.NA
        metrics[f"max_drawdown_{horizon}d"] = _round(float(relative_path.min()))
        metrics[f"horizon_{horizon}d_status"] = "complete"
    return metrics


def _set_missing_horizon(metrics: dict[str, Any], horizon: int, status: str) -> None:
    metrics[f"return_{horizon}d"] = pd.NA
    metrics[f"benchmark_return_{horizon}d"] = pd.NA
    metrics[f"excess_return_{horizon}d"] = pd.NA
    metrics[f"max_drawdown_{horizon}d"] = pd.NA
    metrics[f"horizon_{horizon}d_status"] = status


def _benchmark_return(benchmark_frame: pd.DataFrame, horizon: int) -> Any:
    if benchmark_frame.empty or len(benchmark_frame) <= horizon:
        return pd.NA
    entry_close = float(benchmark_frame.iloc[0]["close"])
    return float(benchmark_frame.iloc[horizon]["close"]) / entry_close - 1.0


def _build_group_summary(*, outcomes: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if outcomes.empty:
        return pd.DataFrame(columns=_group_summary_columns(horizons))
    for group_name, group in outcomes.groupby("comparison_group", sort=True):
        row: dict[str, Any] = {"comparison_group": group_name, "candidate_count": int(len(group))}
        for horizon in horizons:
            returns = pd.to_numeric(group[f"return_{horizon}d"], errors="coerce")
            excess_returns = pd.to_numeric(group[f"excess_return_{horizon}d"], errors="coerce")
            drawdowns = pd.to_numeric(group[f"max_drawdown_{horizon}d"], errors="coerce")
            complete = group[f"horizon_{horizon}d_status"].eq("complete")
            row[f"complete_count_{horizon}d"] = int(complete.sum())
            row[f"mean_return_{horizon}d"] = _round_or_na(returns.mean())
            row[f"median_return_{horizon}d"] = _round_or_na(returns.median())
            row[f"win_rate_{horizon}d"] = _round_or_na((returns > 0).mean())
            row[f"mean_excess_return_{horizon}d"] = _round_or_na(excess_returns.mean())
            row[f"mean_max_drawdown_{horizon}d"] = _round_or_na(drawdowns.mean())
        rows.append(row)
    return pd.DataFrame(rows, columns=_group_summary_columns(horizons))


def _normalize_comparison_groups(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    if "observation_start_date" not in normalized.columns and "trade_date" in normalized.columns:
        normalized = normalized.rename(columns={"trade_date": "observation_start_date"})
    if "source_trade_date" not in normalized.columns:
        normalized["source_trade_date"] = normalized.get("observation_start_date", "")
    for column in [
        "comparison_group",
        "asset_id",
        "stock_name",
        "observation_start_date",
        "source_trade_date",
        "product_family",
        "evidence_quality_score",
    ]:
        if column not in normalized.columns:
            normalized[column] = 0 if column == "evidence_quality_score" else ""
    normalized["asset_id"] = normalized["asset_id"].astype("string").fillna("")
    normalized["stock_name"] = normalized["stock_name"].astype("string").fillna("")
    normalized["comparison_group"] = normalized["comparison_group"].astype("string").fillna("")
    normalized["product_family"] = normalized["product_family"].astype("string").fillna("")
    normalized["observation_start_date"] = pd.to_datetime(normalized["observation_start_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    normalized["source_trade_date"] = pd.to_datetime(normalized["source_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    normalized["evidence_quality_score"] = pd.to_numeric(normalized["evidence_quality_score"], errors="coerce").fillna(0).astype(int)
    return normalized[
        normalized["comparison_group"].ne("") & normalized["asset_id"].ne("") & normalized["observation_start_date"].ne("")
    ].copy()


def _normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ["asset_id", "trade_date", "close"]:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized["asset_id"] = normalized["asset_id"].astype("string").fillna("")
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
    return normalized.dropna(subset=["trade_date", "close"])[normalized["asset_id"].ne("")].sort_values(["asset_id", "trade_date"])


def _outcome_columns(horizons: list[int]) -> list[str]:
    columns = list(OUTCOME_BASE_COLUMNS)
    for horizon in horizons:
        columns.extend(
            [
                f"return_{horizon}d",
                f"benchmark_return_{horizon}d",
                f"excess_return_{horizon}d",
                f"max_drawdown_{horizon}d",
                f"horizon_{horizon}d_status",
            ]
        )
    return columns


def _group_summary_columns(horizons: list[int]) -> list[str]:
    columns = ["comparison_group", "candidate_count"]
    for horizon in horizons:
        columns.extend(
            [
                f"complete_count_{horizon}d",
                f"mean_return_{horizon}d",
                f"median_return_{horizon}d",
                f"win_rate_{horizon}d",
                f"mean_excess_return_{horizon}d",
                f"mean_max_drawdown_{horizon}d",
            ]
        )
    return columns


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _render_summary(manifest: dict[str, Any], group_summary: pd.DataFrame, horizons: list[int]) -> str:
    lines = [
        "# tech-bottleneck observation outcome",
        "",
        "This is an observation outcome comparison, not a production trading backtest.",
        "",
        f"- outcome_row_count: {manifest.get('outcome_row_count', 0)}",
        f"- benchmark_asset_id: {manifest.get('benchmark_asset_id', '')}",
        f"- horizons: {'|'.join(str(horizon) for horizon in horizons)}",
        "",
        "## Group Summary",
        "",
    ]
    for row in group_summary.to_dict("records"):
        lines.append(f"### {row['comparison_group']}")
        lines.append(f"- candidates: {row['candidate_count']}")
        for horizon in horizons:
            lines.append(
                f"- {horizon}D mean: {row.get(f'mean_return_{horizon}d')} "
                f"excess: {row.get(f'mean_excess_return_{horizon}d')} "
                f"complete: {row.get(f'complete_count_{horizon}d')}"
            )
        lines.append("")
    return "\n".join(lines)


def _round(value: float) -> float:
    return round(float(value), 6)


def _round_or_na(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    return _round(float(value))
