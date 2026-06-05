from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_HORIZONS = (20, 60, 120, 250, 500)
OUTCOME_BASE_COLUMNS = [
    "run_id",
    "candidate_source",
    "asset_id",
    "stock_name",
    "trade_date",
    "candidate_state",
    "bucket",
    "tech_bottleneck_score",
    "base_strategy_rank",
    "base_strategy_score",
]


def build_historical_rescore_report(
    *,
    packets: pd.DataFrame,
    bars: pd.DataFrame,
    run_id: str,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, pd.DataFrame]:
    normalized_packets = _normalize_packets(packets)
    normalized_bars = _normalize_bars(bars)
    outcomes = _build_outcomes(
        packets=normalized_packets,
        bars=normalized_bars,
        run_id=run_id,
        horizons=horizons,
    )
    bucket_summary = _build_bucket_summary(outcomes=outcomes, horizons=horizons)
    return {"outcomes": outcomes, "bucket_summary": bucket_summary}


def render_historical_rescore_summary(
    *,
    run_id: str,
    bucket_summary: pd.DataFrame,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> str:
    lines = [
        "# tech-bottleneck historical rescore summary",
        "",
        f"- Run ID: `{run_id}`",
        "- Short-term diagnostics: 20D / 60D",
        "- Primary validation: 120D / 250D",
        "- Long-cycle observation: 500D",
        "",
        "## Buckets",
        "",
    ]
    for row in bucket_summary.to_dict("records"):
        lines.append(f"### {row['bucket']}")
        lines.append(f"- Candidates: {row['candidate_count']}")
        for horizon in horizons:
            lines.append(
                f"- {horizon}D mean return: {row.get(f'mean_return_{horizon}d')} "
                f"excess: {row.get(f'excess_return_{horizon}d')}"
            )
        lines.append("")
    return "\n".join(lines)


def write_historical_rescore_artifacts(
    *,
    report: dict[str, pd.DataFrame],
    output_dir: Path,
    run_id: str,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outcomes_path = output_dir / "outcomes.csv"
    bucket_summary_path = output_dir / "bucket_summary.csv"
    summary_path = output_dir / "summary.md"
    report["outcomes"].to_csv(outcomes_path, index=False)
    report["bucket_summary"].to_csv(bucket_summary_path, index=False)
    summary_path.write_text(
        render_historical_rescore_summary(
            run_id=run_id,
            bucket_summary=report["bucket_summary"],
            horizons=horizons,
        ),
        encoding="utf-8",
    )
    return {"outcomes": outcomes_path, "bucket_summary": bucket_summary_path, "summary": summary_path}


def run_historical_rescore_from_files(
    *,
    packets_csv: Path,
    bars_csv: Path,
    output_dir: Path,
    run_id: str,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Path]:
    packets = pd.read_csv(packets_csv)
    bars = pd.read_csv(bars_csv)
    report = build_historical_rescore_report(
        packets=packets,
        bars=bars,
        run_id=run_id,
        horizons=horizons,
    )
    return write_historical_rescore_artifacts(
        report=report,
        output_dir=output_dir,
        run_id=run_id,
        horizons=horizons,
    )


def _build_outcomes(
    *,
    packets: pd.DataFrame,
    bars: pd.DataFrame,
    run_id: str,
    horizons: tuple[int, ...],
) -> pd.DataFrame:
    if packets.empty:
        return pd.DataFrame(columns=_outcome_columns(horizons))
    bars_by_asset = {
        asset_id: frame.sort_values("trade_date").reset_index(drop=True)
        for asset_id, frame in bars.groupby("asset_id", sort=False)
    }
    rows: list[dict[str, Any]] = []
    for packet in packets.to_dict("records"):
        asset_id = str(packet.get("asset_id", ""))
        asset_bars = bars_by_asset.get(asset_id, pd.DataFrame(columns=bars.columns))
        row = {
            "run_id": run_id,
            "candidate_source": _safe_text(packet.get("candidate_source")) or "unknown",
            "asset_id": asset_id,
            "stock_name": _safe_text(packet.get("stock_name")),
            "trade_date": _iso_date(packet.get("trade_date")),
            "candidate_state": _safe_text(packet.get("candidate_state")),
            "bucket": _bucket_for_score(packet.get("tech_bottleneck_score")),
            "tech_bottleneck_score": _safe_float(packet.get("tech_bottleneck_score")),
            "base_strategy_rank": _safe_float(packet.get("base_strategy_rank")),
            "base_strategy_score": _safe_float(packet.get("base_strategy_score")),
        }
        row.update(_horizon_metrics(asset_bars, row["trade_date"], horizons))
        rows.append(row)
    return pd.DataFrame(rows, columns=_outcome_columns(horizons))


def _horizon_metrics(
    asset_bars: pd.DataFrame,
    trade_date: str,
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    frame = asset_bars[asset_bars["trade_date"] >= pd.to_datetime(trade_date)].copy()
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        for horizon in horizons:
            metrics[f"return_{horizon}d"] = pd.NA
            metrics[f"max_drawdown_{horizon}d"] = pd.NA
            metrics[f"horizon_{horizon}d_status"] = "missing_entry_bar"
        return metrics
    entry_close = float(frame.iloc[0]["close"])
    for horizon in horizons:
        if len(frame) <= horizon:
            metrics[f"return_{horizon}d"] = pd.NA
            metrics[f"max_drawdown_{horizon}d"] = pd.NA
            metrics[f"horizon_{horizon}d_status"] = "partial"
            continue
        window = frame.iloc[: horizon + 1]
        end_close = float(window.iloc[-1]["close"])
        returns = window["close"].astype(float) / entry_close - 1.0
        metrics[f"return_{horizon}d"] = round(end_close / entry_close - 1.0, 6)
        metrics[f"max_drawdown_{horizon}d"] = round(float(returns.min()), 6)
        metrics[f"horizon_{horizon}d_status"] = "complete"
    return metrics


def _build_bucket_summary(*, outcomes: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if outcomes.empty:
        return pd.DataFrame(columns=_bucket_summary_columns(horizons))
    pool_means = {
        horizon: pd.to_numeric(outcomes[f"return_{horizon}d"], errors="coerce").mean()
        for horizon in horizons
    }
    for bucket in ["high", "medium", "low"]:
        bucket_frame = outcomes[outcomes["bucket"] == bucket]
        row: dict[str, Any] = {"bucket": bucket, "candidate_count": int(len(bucket_frame))}
        for horizon in horizons:
            returns = pd.to_numeric(bucket_frame[f"return_{horizon}d"], errors="coerce")
            drawdowns = pd.to_numeric(bucket_frame[f"max_drawdown_{horizon}d"], errors="coerce")
            complete = bucket_frame[f"horizon_{horizon}d_status"].eq("complete")
            mean_return = returns.mean()
            row[f"complete_count_{horizon}d"] = int(complete.sum())
            row[f"mean_return_{horizon}d"] = _round_or_na(mean_return)
            row[f"median_return_{horizon}d"] = _round_or_na(returns.median())
            row[f"win_rate_{horizon}d"] = _round_or_na((returns > 0).mean())
            row[f"mean_max_drawdown_{horizon}d"] = _round_or_na(drawdowns.mean())
            row[f"excess_return_{horizon}d"] = _round_or_na(mean_return - pool_means[horizon])
        rows.append(row)
    return pd.DataFrame(rows, columns=_bucket_summary_columns(horizons))


def _normalize_packets(packets: pd.DataFrame) -> pd.DataFrame:
    normalized = packets.copy()
    for column in OUTCOME_BASE_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["tech_bottleneck_score"] = pd.to_numeric(normalized["tech_bottleneck_score"], errors="coerce")
    return normalized


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    normalized = bars.copy()
    for column in ["asset_id", "trade_date", "close"]:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized["asset_id"] = normalized["asset_id"].map(_safe_text)
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
    normalized = normalized.dropna(subset=["asset_id", "trade_date", "close"])
    return normalized.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def _outcome_columns(horizons: tuple[int, ...]) -> list[str]:
    columns = list(OUTCOME_BASE_COLUMNS)
    for horizon in horizons:
        columns.extend(
            [
                f"return_{horizon}d",
                f"max_drawdown_{horizon}d",
                f"horizon_{horizon}d_status",
            ]
        )
    return columns


def _bucket_summary_columns(horizons: tuple[int, ...]) -> list[str]:
    columns = ["bucket", "candidate_count"]
    for horizon in horizons:
        columns.extend(
            [
                f"complete_count_{horizon}d",
                f"mean_return_{horizon}d",
                f"median_return_{horizon}d",
                f"win_rate_{horizon}d",
                f"mean_max_drawdown_{horizon}d",
                f"excess_return_{horizon}d",
            ]
        )
    return columns


def _bucket_for_score(value: Any) -> str:
    score = _safe_float(value)
    if pd.isna(score):
        return "unknown"
    if score >= 3.5:
        return "high"
    if score >= 2.0:
        return "medium"
    return "low"


def _safe_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return float("nan")
        return float(value)
    except Exception:
        return float("nan")


def _round_or_na(value: Any) -> Any:
    try:
        if pd.isna(value):
            return pd.NA
        return round(float(value), 6)
    except Exception:
        return pd.NA


def _iso_date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()
