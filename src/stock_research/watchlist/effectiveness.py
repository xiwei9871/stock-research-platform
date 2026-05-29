from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


RETURN_HORIZONS = [1, 3, 5]


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
    detail["future_5d_max_drawdown"] = pd.NA

    normalized_bars = bars.copy()
    normalized_bars["trade_date"] = pd.to_datetime(normalized_bars["trade_date"])
    normalized_bars["close"] = pd.to_numeric(normalized_bars["close"], errors="coerce")
    normalized_bars["low"] = pd.to_numeric(normalized_bars["low"], errors="coerce")
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

        future_window = asset_bars.iloc[event_index + 1 : event_index + 6]
        if not future_window.empty:
            min_low = future_window["low"].min()
            if not pd.isna(min_low):
                detail.at[row_index, "future_5d_max_drawdown"] = min(float(min_low) / float(base_close) - 1.0, 0.0)

    return detail


def build_watchlist_diagnostics_effectiveness_summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(
            columns=[
                "summary_level",
                "watch_group",
                "event_structure",
                "sample_count",
                "future_1d_return_mean",
                "future_3d_return_mean",
                "future_5d_return_mean",
                "future_5d_max_drawdown_mean",
            ]
        )

    normalized = detail.copy()
    for column in [
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_5d_max_drawdown",
    ]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    frames = [
        _summary_frame(normalized, group_columns=["watch_group"], summary_level="watch_group"),
        _summary_frame(
            normalized[normalized["event_structure"].fillna("").ne("")],
            group_columns=["event_structure"],
            summary_level="event_structure",
        ),
    ]
    return pd.concat(frames, ignore_index=True)


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

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    detail_csv_path = output_path / "watchlist_diagnostics_effectiveness_detail.csv"
    summary_csv_path = output_path / "watchlist_diagnostics_effectiveness_summary.csv"
    markdown_path = output_path / "watchlist_diagnostics_effectiveness.md"
    detail.to_csv(detail_csv_path, index=False)
    summary.to_csv(summary_csv_path, index=False)
    markdown_path.write_text(_render_markdown(summary), encoding="utf-8")
    return {
        "detail_csv_path": str(detail_csv_path),
        "summary_csv_path": str(summary_csv_path),
        "markdown_path": str(markdown_path),
    }


def _summary_frame(detail: pd.DataFrame, *, group_columns: list[str], summary_level: str) -> pd.DataFrame:
    metric_columns = [
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_5d_max_drawdown",
    ]
    grouped = detail.groupby(group_columns, dropna=False)
    summary = grouped[metric_columns].mean(numeric_only=True).reset_index()
    counts = grouped.size().reset_index(name="sample_count")
    summary = counts.merge(summary, on=group_columns, how="left")
    summary.insert(0, "summary_level", summary_level)
    for column in ["watch_group", "event_structure"]:
        if column not in summary.columns:
            summary[column] = ""
    return summary[
        [
            "summary_level",
            "watch_group",
            "event_structure",
            "sample_count",
            "future_1d_return",
            "future_3d_return",
            "future_5d_return",
            "future_5d_max_drawdown",
        ]
    ].rename(
        columns={
            "future_1d_return": "future_1d_return_mean",
            "future_3d_return": "future_3d_return_mean",
            "future_5d_return": "future_5d_return_mean",
            "future_5d_max_drawdown": "future_5d_max_drawdown_mean",
        }
    )


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
        SELECT asset_id, trade_date::text AS trade_date, close, low
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date >= %s
          AND asset_id IN ({placeholders})
        ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, *asset_ids])
    return pd.DataFrame(rows, columns=["asset_id", "trade_date", "close", "low"])


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
