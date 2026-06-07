from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


SHORT_RETURN_HORIZONS = [1, 3, 5]
STRONG_WINNER_RETURN_HORIZONS = [5, 10, 20, 30, 40, 60]
RETURN_HORIZONS = sorted(set(SHORT_RETURN_HORIZONS + STRONG_WINNER_RETURN_HORIZONS))
MAX_DRAWDOWN_HORIZONS = [5, 10, 20, 30, 40, 60]


def build_watchlist_diagnostics_effectiveness_detail(
    *,
    diagnostics_rows: pd.DataFrame,
    bars: pd.DataFrame,
) -> pd.DataFrame:
    if diagnostics_rows.empty:
        return diagnostics_rows.copy()

    detail = diagnostics_rows.copy()
    for horizon in RETURN_HORIZONS:
        detail[f"future_{horizon}d_return"] = pd.NA
    for horizon in MAX_DRAWDOWN_HORIZONS:
        detail[f"future_{horizon}d_max_drawdown"] = pd.NA
    detail["max_return_within_60d"] = pd.NA
    detail["hit_double_within_60d"] = False

    normalized_bars = bars.copy()
    normalized_bars["trade_date"] = pd.to_datetime(normalized_bars["trade_date"])
    normalized_bars["close"] = pd.to_numeric(normalized_bars["close"], errors="coerce")
    normalized_bars["low"] = pd.to_numeric(normalized_bars["low"], errors="coerce")
    if "high" not in normalized_bars.columns:
        normalized_bars["high"] = normalized_bars["close"]
    normalized_bars["high"] = pd.to_numeric(normalized_bars["high"], errors="coerce")
    grouped_bars = {
        str(asset_id): group.sort_values("trade_date").reset_index(drop=True)
        for asset_id, group in normalized_bars.groupby("asset_id", dropna=False)
    }

    for row_index, row in detail.iterrows():
        asset_id = str(row.get("asset_id", ""))
        asset_bars = grouped_bars.get(asset_id)
        if asset_bars is None or asset_bars.empty:
            continue

        event_date = pd.to_datetime(row.get("trade_date"))
        event_matches = asset_bars.index[asset_bars["trade_date"].eq(event_date)].tolist()
        if not event_matches:
            continue
        event_index = int(event_matches[0])
        base_close = asset_bars.loc[event_index, "close"]
        if pd.isna(base_close) or float(base_close) == 0.0:
            continue

        for horizon in RETURN_HORIZONS:
            future_index = event_index + horizon
            if future_index < len(asset_bars):
                future_close = asset_bars.loc[future_index, "close"]
                if not pd.isna(future_close):
                    detail.at[row_index, f"future_{horizon}d_return"] = float(future_close) / float(base_close) - 1.0

        for horizon in MAX_DRAWDOWN_HORIZONS:
            future_window = asset_bars.iloc[event_index + 1 : event_index + horizon + 1]
            if not future_window.empty:
                min_low = future_window["low"].min()
                if not pd.isna(min_low):
                    detail.at[row_index, f"future_{horizon}d_max_drawdown"] = min(float(min_low) / float(base_close) - 1.0, 0.0)

        strong_window = asset_bars.iloc[event_index + 1 : event_index + 61]
        if not strong_window.empty:
            max_high = strong_window["high"].max()
            if not pd.isna(max_high):
                max_return = float(max_high) / float(base_close) - 1.0
                detail.at[row_index, "max_return_within_60d"] = max_return
                detail.at[row_index, "hit_double_within_60d"] = bool(max_return >= 1.0)

    return detail


def build_watchlist_diagnostics_effectiveness_summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(
            columns=[
                "evaluation_layer",
                "summary_level",
                "watch_group",
                "event_structure",
                "sample_count",
                "future_1d_return_mean",
                "future_3d_return_mean",
                "future_5d_return_mean",
                "future_5d_max_drawdown_mean",
                "future_10d_return_mean",
                "future_20d_return_mean",
                "future_30d_return_mean",
                "future_40d_return_mean",
                "future_60d_return_mean",
                "future_20d_max_drawdown_mean",
                "future_30d_max_drawdown_mean",
                "future_60d_max_drawdown_mean",
                "max_return_within_60d_mean",
                "hit_double_within_60d_rate",
            ]
        )

    normalized = detail.copy()
    _ensure_numeric_columns(normalized)
    frames = []
    for evaluation_layer, metric_columns in [
        ("short_horizon", _short_horizon_metric_columns()),
        ("strong_winner_horizon", _strong_winner_metric_columns()),
    ]:
        frames.extend(
            [
                _summary_frame(
                    normalized,
                    group_columns=["watch_group"],
                    summary_level="watch_group",
                    evaluation_layer=evaluation_layer,
                    metric_columns=metric_columns,
                ),
                _summary_frame(
                    normalized[normalized["event_structure"].fillna("").ne("")],
                    group_columns=["event_structure"],
                    summary_level="event_structure",
                    evaluation_layer=evaluation_layer,
                    metric_columns=metric_columns,
                ),
            ]
        )
    return pd.concat(frames, ignore_index=True)


def split_watchlist_diagnostics_effectiveness_summary(summary: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if summary.empty or "evaluation_layer" not in summary.columns:
        return summary.copy(), summary.copy()
    short = summary[summary["evaluation_layer"].eq("short_horizon")].reset_index(drop=True)
    strong = summary[summary["evaluation_layer"].eq("strong_winner_horizon")].reset_index(drop=True)
    return short, strong


def run_watchlist_diagnostics_effectiveness_review(
    *,
    diagnostics_dir: str | Path,
    output_dir: str | Path,
    start_date: str | None = None,
    end_date: str | None = None,
    service: str = SETTINGS.research_service,
    adjust_type: str = "qfq",
) -> dict[str, str]:
    diagnostics = _load_diagnostics_rows(diagnostics_dir)
    diagnostics = _filter_date_window(
        diagnostics,
        start_date=start_date,
        end_date=end_date,
    )
    bars = _load_market_bars_for_effectiveness(
        diagnostics_rows=diagnostics,
        service=service,
        adjust_type=adjust_type,
    )
    detail = build_watchlist_diagnostics_effectiveness_detail(
        diagnostics_rows=diagnostics,
        bars=bars,
    )
    summary = build_watchlist_diagnostics_effectiveness_summary(detail)
    short_summary, strong_summary = split_watchlist_diagnostics_effectiveness_summary(summary)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    detail_csv_path = output_path / "watchlist_diagnostics_effectiveness_detail.csv"
    summary_csv_path = output_path / "watchlist_diagnostics_effectiveness_summary.csv"
    short_horizon_summary_csv_path = output_path / "watchlist_diagnostics_short_horizon_summary.csv"
    strong_winner_horizon_summary_csv_path = output_path / "watchlist_diagnostics_strong_winner_horizon_summary.csv"
    markdown_path = output_path / "watchlist_diagnostics_effectiveness.md"
    detail.to_csv(detail_csv_path, index=False)
    summary.to_csv(summary_csv_path, index=False)
    short_summary.to_csv(short_horizon_summary_csv_path, index=False)
    strong_summary.to_csv(strong_winner_horizon_summary_csv_path, index=False)
    markdown_path.write_text(_render_markdown(summary), encoding="utf-8")
    return {
        "detail_csv_path": str(detail_csv_path),
        "summary_csv_path": str(summary_csv_path),
        "short_horizon_summary_csv_path": str(short_horizon_summary_csv_path),
        "strong_winner_horizon_summary_csv_path": str(strong_winner_horizon_summary_csv_path),
        "markdown_path": str(markdown_path),
    }


def _summary_frame(
    detail: pd.DataFrame,
    *,
    group_columns: list[str],
    summary_level: str,
    evaluation_layer: str,
    metric_columns: list[str],
) -> pd.DataFrame:
    grouped = detail.groupby(group_columns, dropna=False)
    summary = grouped[metric_columns].mean(numeric_only=True).reset_index()
    counts = grouped.size().reset_index(name="sample_count")
    summary = counts.merge(summary, on=group_columns, how="left")
    summary.insert(0, "evaluation_layer", evaluation_layer)
    summary.insert(0, "summary_level", summary_level)
    for column in ["watch_group", "event_structure"]:
        if column not in summary.columns:
            summary[column] = ""
    output_columns = ["evaluation_layer", "summary_level", "watch_group", "event_structure", "sample_count"]
    output_columns.extend(metric_columns)
    renamed = summary[output_columns].rename(columns={column: _summary_metric_name(column) for column in metric_columns})
    return renamed


def _ensure_numeric_columns(frame: pd.DataFrame) -> None:
    for column in sorted(set(_short_horizon_metric_columns() + _strong_winner_metric_columns())):
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")


def _short_horizon_metric_columns() -> list[str]:
    return [
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_5d_max_drawdown",
    ]


def _strong_winner_metric_columns() -> list[str]:
    return [
        "future_5d_return",
        "future_10d_return",
        "future_20d_return",
        "future_30d_return",
        "future_40d_return",
        "future_60d_return",
        "future_20d_max_drawdown",
        "future_30d_max_drawdown",
        "future_60d_max_drawdown",
        "max_return_within_60d",
        "hit_double_within_60d",
    ]


def _summary_metric_name(column: str) -> str:
    if column == "hit_double_within_60d":
        return "hit_double_within_60d_rate"
    return f"{column}_mean"


def _load_diagnostics_rows(diagnostics_dir: str | Path) -> pd.DataFrame:
    path = Path(diagnostics_dir)
    files = sorted(
        file
        for file in path.glob("watchlist_diagnostics_*_diagnostics_v1.csv")
        if not file.name.startswith("watchlist_diagnostics_must_watch_")
    )
    if not files:
        raise ValueError(f"no watchlist diagnostics CSV files found in {path}")
    frames = [pd.read_csv(file) for file in files]
    return pd.concat(frames, ignore_index=True)


def _filter_date_window(
    diagnostics: pd.DataFrame,
    *,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    if diagnostics.empty or (start_date is None and end_date is None):
        return diagnostics.copy()
    frame = diagnostics.copy()
    dates = pd.to_datetime(frame["trade_date"])
    if start_date is not None:
        frame = frame[dates >= pd.to_datetime(start_date)]
        dates = pd.to_datetime(frame["trade_date"])
    if end_date is not None:
        frame = frame[dates <= pd.to_datetime(end_date)]
    return frame.reset_index(drop=True)


def _load_market_bars_for_effectiveness(
    *,
    diagnostics_rows: pd.DataFrame,
    service: str,
    adjust_type: str,
) -> pd.DataFrame:
    asset_ids = sorted({str(value) for value in diagnostics_rows.get("asset_id", []) if str(value)})
    if not asset_ids:
        return pd.DataFrame(columns=["asset_id", "trade_date", "close", "low"])
    start_date = str(pd.to_datetime(diagnostics_rows["trade_date"]).min().date())
    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT asset_id, trade_date::text AS trade_date, close, high, low
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date >= %s
          AND asset_id IN ({placeholders})
        ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, *asset_ids])
    return pd.DataFrame(rows, columns=["asset_id", "trade_date", "close", "high", "low"])


def _render_markdown(summary: pd.DataFrame) -> str:
    lines = [
        "# Watchlist Diagnostics Effectiveness",
        "",
        f"- Summary rows: {len(summary)}",
        "",
    ]
    if summary.empty:
        lines.append("No rows.")
    else:
        lines.append(summary.to_markdown(index=False))
    return "\n".join(lines).rstrip() + "\n"
