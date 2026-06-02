from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


TREND_LABEL_SET = "trend_event"
TREND_LABEL_VERSION = "v1"

TREND_SEGMENT_COLUMNS = [
    "asset_id",
    "label_set",
    "label_version",
    "trend_label",
    "start_date",
    "peak_date",
    "start_close",
    "peak_close",
    "gain",
    "duration",
    "avg_amount",
    "max_drawdown_before_peak",
]

LIFECYCLE_SAMPLE_COLUMNS = [
    "asset_id",
    "trade_date",
    "trend_label",
    "stage",
    "segment_start_date",
    "peak_date",
    "bars_since_start",
    "duration",
    "progress",
]

ENTRY_SUCCESS_COLUMNS = [
    "asset_id",
    "trade_date",
    "entry_success_20d",
    "entry_success_20d_covered",
    "entry_success_40d",
    "entry_success_40d_covered",
    "entry_success_60d",
    "entry_success_60d_covered",
]

TOP20_STAGE_HIT_COLUMNS = [
    "trend_label",
    "stage",
    "top20_rows",
    "hits",
    "hit_rate",
]

STAGE_ORDER = ["early", "early_mid", "mid", "late_mid", "late"]


@dataclass(frozen=True)
class TrendRule:
    label: str
    min_window: int
    max_window: int
    min_gain: float
    max_gain: float | None


@dataclass(frozen=True)
class EntrySuccessRule:
    name: str
    horizon: int
    profit_threshold: float
    stop_threshold: float


DEFAULT_TREND_RULES = (
    TrendRule("small_trend", 40, 80, 0.25, 0.40),
    TrendRule("mid_trend", 60, 120, 0.40, 0.80),
    TrendRule("large_trend", 1, 120, 0.80, None),
)

DEFAULT_ENTRY_SUCCESS_RULES = (
    EntrySuccessRule("entry_success_20d", 20, 0.15, -0.08),
    EntrySuccessRule("entry_success_40d", 40, 0.25, -0.12),
    EntrySuccessRule("entry_success_60d", 60, 0.35, -0.12),
)


def compute_trend_segments_for_asset(
    asset_id: str,
    bars: pd.DataFrame,
    *,
    rules: tuple[TrendRule, ...] = DEFAULT_TREND_RULES,
    min_avg_amount: float = 30_000_000.0,
) -> pd.DataFrame:
    frame = _normalize_bars(bars)
    if frame.empty:
        return pd.DataFrame(columns=TREND_SEGMENT_COLUMNS)

    rows: list[dict[str, Any]] = []
    dates = frame["trade_date"].astype(str).to_numpy()
    close_values = frame["close"].astype(float).to_numpy()
    amount_values = frame["amount"].astype(float).to_numpy()
    asset_text = str(asset_id)
    row_count = len(frame)
    for rule in rules:
        candidates: list[dict[str, Any]] = []
        for start_index in range(row_count):
            start_close = close_values[start_index]
            if np.isnan(start_close) or start_close <= 0:
                continue

            min_peak_index = start_index + rule.min_window
            max_peak_index = min(start_index + rule.max_window, row_count - 1)
            if min_peak_index > max_peak_index:
                continue

            future_close = close_values[min_peak_index : max_peak_index + 1]
            valid_future = future_close[~np.isnan(future_close)]
            if valid_future.size == 0:
                continue
            peak_offset = int(np.nanargmax(future_close))
            peak_index = min_peak_index + peak_offset
            peak_close = close_values[peak_index]

            gain = float(peak_close / start_close - 1.0)
            if gain < rule.min_gain:
                continue
            if rule.max_gain is not None and gain > rule.max_gain:
                continue

            segment_amount = amount_values[start_index : peak_index + 1]
            avg_amount = float(np.nanmean(segment_amount)) if segment_amount.size else 0.0
            if pd.isna(avg_amount) or avg_amount < min_avg_amount:
                continue

            candidates.append(
                {
                    "asset_id": asset_text,
                    "label_set": TREND_LABEL_SET,
                    "label_version": TREND_LABEL_VERSION,
                    "trend_label": rule.label,
                    "start_date": str(dates[start_index]),
                    "peak_date": str(dates[peak_index]),
                    "start_close": float(start_close),
                    "peak_close": float(peak_close),
                    "gain": float(gain),
                    "duration": int(peak_index - start_index),
                    "avg_amount": avg_amount,
                    "max_drawdown_before_peak": _max_drawdown_array(
                        close_values[start_index : peak_index + 1]
                    ),
                    "_start_index": int(start_index),
                    "_peak_index": int(peak_index),
                }
            )
        rows.extend(_deduplicate_segments(candidates, rule))

    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=TREND_SEGMENT_COLUMNS)
    return (
        result.sort_values(["start_date", "trend_label", "asset_id"])
        .drop(columns=["_start_index", "_peak_index"])
        .reset_index(drop=True)
        .reindex(columns=TREND_SEGMENT_COLUMNS)
    )


def compute_trend_segments(
    bars: pd.DataFrame,
    *,
    rules: tuple[TrendRule, ...] = DEFAULT_TREND_RULES,
    min_avg_amount: float = 30_000_000.0,
) -> pd.DataFrame:
    if bars.empty or "asset_id" not in bars.columns:
        return pd.DataFrame(columns=TREND_SEGMENT_COLUMNS)
    frames = [
        compute_trend_segments_for_asset(
            str(asset_id),
            group,
            rules=rules,
            min_avg_amount=min_avg_amount,
        )
        for asset_id, group in bars.groupby("asset_id", sort=False)
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=TREND_SEGMENT_COLUMNS)
    return pd.concat(frames, ignore_index=True).reindex(columns=TREND_SEGMENT_COLUMNS)


def build_lifecycle_samples(
    segments: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    start_date: object | None = None,
    end_date: object | None = None,
) -> pd.DataFrame:
    if segments.empty or bars.empty:
        return pd.DataFrame(columns=LIFECYCLE_SAMPLE_COLUMNS)

    normalized_bars = _normalize_bars(bars)
    rows: list[dict[str, Any]] = []
    start_filter = _iso_date(start_date) if start_date is not None else None
    end_filter = _iso_date(end_date) if end_date is not None else None
    bars_by_asset: dict[str, pd.DataFrame] = {}
    date_index_by_asset: dict[str, dict[str, int]] = {}
    for asset_id, group in normalized_bars.groupby("asset_id", sort=False):
        asset_text = str(asset_id)
        asset_frame = group.reset_index(drop=True)
        bars_by_asset[asset_text] = asset_frame
        date_index_by_asset[asset_text] = {
            str(trade_date): int(index)
            for index, trade_date in enumerate(asset_frame["trade_date"].astype(str))
        }

    for segment in segments.to_dict("records"):
        asset_id = str(segment["asset_id"])
        asset_bars = bars_by_asset.get(asset_id)
        if asset_bars is None or asset_bars.empty:
            continue
        date_index = date_index_by_asset.get(asset_id, {})
        start_index = date_index.get(str(segment["start_date"]))
        peak_index = date_index.get(str(segment["peak_date"]))
        if start_index is None or peak_index is None:
            continue
        if peak_index < start_index:
            continue
        duration = max(peak_index - start_index, 1)

        for index in range(start_index, peak_index + 1):
            trade_date = str(asset_bars.loc[index, "trade_date"])
            if start_filter is not None and trade_date < start_filter:
                continue
            if end_filter is not None and trade_date > end_filter:
                continue
            bars_since_start = index - start_index
            progress = bars_since_start / duration
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date,
                    "trend_label": str(segment["trend_label"]),
                    "stage": stage_for_progress(progress),
                    "segment_start_date": str(segment["start_date"]),
                    "peak_date": str(segment["peak_date"]),
                    "bars_since_start": int(bars_since_start),
                    "duration": int(peak_index - start_index),
                    "progress": float(progress),
                }
            )

    if not rows:
        return pd.DataFrame(columns=LIFECYCLE_SAMPLE_COLUMNS)
    return pd.DataFrame(rows).reindex(columns=LIFECYCLE_SAMPLE_COLUMNS)


def stage_for_progress(progress: float) -> str:
    value = max(0.0, min(float(progress), 1.0))
    if value <= 0.20:
        return "early"
    if value <= 0.40:
        return "early_mid"
    if value <= 0.60:
        return "mid"
    if value <= 0.80:
        return "late_mid"
    return "late"


def compute_entry_success_labels(
    bars: pd.DataFrame,
    signals: pd.DataFrame | None = None,
    *,
    rules: tuple[EntrySuccessRule, ...] = DEFAULT_ENTRY_SUCCESS_RULES,
) -> pd.DataFrame:
    normalized_bars = _normalize_bars(bars)
    if normalized_bars.empty:
        return pd.DataFrame(columns=ENTRY_SUCCESS_COLUMNS)

    if signals is None:
        signal_frame = normalized_bars[["asset_id", "trade_date"]].drop_duplicates()
    else:
        signal_frame = signals[["asset_id", "trade_date"]].copy()
        signal_frame["asset_id"] = signal_frame["asset_id"].astype(str)
        signal_frame["trade_date"] = signal_frame["trade_date"].map(_iso_date)

    rows = []
    bars_by_asset = {
        str(asset_id): group.reset_index(drop=True)
        for asset_id, group in normalized_bars.groupby("asset_id", sort=False)
    }
    for signal in signal_frame.drop_duplicates().to_dict("records"):
        asset_id = str(signal["asset_id"])
        trade_date = _iso_date(signal["trade_date"])
        asset_bars = bars_by_asset.get(asset_id)
        row: dict[str, Any] = {"asset_id": asset_id, "trade_date": trade_date}
        for rule in rules:
            success, covered = _entry_success_for_signal(asset_bars, trade_date, rule)
            row[rule.name] = bool(success)
            row[f"{rule.name}_covered"] = bool(covered)
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=ENTRY_SUCCESS_COLUMNS)
    result = pd.DataFrame(rows).reindex(columns=ENTRY_SUCCESS_COLUMNS)
    for rule in rules:
        for column in (rule.name, f"{rule.name}_covered"):
            if column in result.columns:
                result[column] = result[column].map(bool).astype(object)
    return result


def build_top20_stage_hit_report(
    scores: pd.DataFrame,
    lifecycle_samples: pd.DataFrame,
    *,
    top_n: int = 20,
) -> pd.DataFrame:
    if scores.empty:
        raise ValueError(
            "Top20 score input is empty; run score-factor-daily/backfill-approved-scores "
            "or pass factor.stock_score_daily rows for the requested score_version."
        )
    if lifecycle_samples.empty:
        return pd.DataFrame(columns=TOP20_STAGE_HIT_COLUMNS)

    normalized_scores = scores.copy()
    normalized_scores["trade_date"] = normalized_scores["trade_date"].map(_iso_date)
    normalized_scores["asset_id"] = normalized_scores["asset_id"].astype(str)
    normalized_scores["rank"] = pd.to_numeric(normalized_scores["rank"], errors="coerce")
    top_scores = normalized_scores[
        normalized_scores["rank"].notna() & (normalized_scores["rank"] <= int(top_n))
    ][["trade_date", "asset_id"]].drop_duplicates()
    if top_scores.empty:
        return pd.DataFrame(columns=TOP20_STAGE_HIT_COLUMNS)

    samples = lifecycle_samples.copy()
    samples["trade_date"] = samples["trade_date"].map(_iso_date)
    samples["asset_id"] = samples["asset_id"].astype(str)
    joined = top_scores.merge(
        samples[["trade_date", "asset_id", "trend_label", "stage"]].drop_duplicates(),
        on=["trade_date", "asset_id"],
        how="inner",
    )
    if joined.empty:
        return pd.DataFrame(columns=TOP20_STAGE_HIT_COLUMNS)

    total_rows = int(len(top_scores))
    grouped = (
        joined.groupby(["trend_label", "stage"], as_index=False)
        .size()
        .rename(columns={"size": "hits"})
    )
    grouped["top20_rows"] = total_rows
    grouped["hit_rate"] = grouped["hits"] / total_rows
    return grouped.reindex(columns=TOP20_STAGE_HIT_COLUMNS)


def run_trend_lifecycle_v1_report(
    *,
    start_date: object,
    end_date: object,
    score_version: str = "manual_v1",
    top_n: int = 20,
    adjust_type: str = "hfq",
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    bars = load_trend_lifecycle_bars(
        start,
        end,
        adjust_type=adjust_type,
        service=service,
    )
    if bars.empty:
        raise ValueError(
            "No market_daily_bar rows found for trend lifecycle report. "
            f"Load bars for {start} to {end} before running this command."
        )
    scores = load_top20_scores(
        start,
        end,
        score_version=score_version,
        top_n=top_n,
        service=service,
    )
    if scores.empty:
        raise ValueError(
            "No factor.stock_score_daily rows found for trend lifecycle Top20 diagnostics. "
            f"Run score-factor-daily/backfill-approved-scores for score_version={score_version}."
        )

    segments = compute_trend_segments(bars)
    lifecycle_samples = build_lifecycle_samples(
        segments,
        bars,
        start_date=start,
        end_date=end,
    )
    signals = scores[["asset_id", "trade_date"]].drop_duplicates()
    entry_success = compute_entry_success_labels(bars, signals)
    entry_success = entry_success[
        (entry_success["trade_date"] >= start) & (entry_success["trade_date"] <= end)
    ].reset_index(drop=True)
    top20_stage_hits = build_top20_stage_hit_report(
        scores,
        lifecycle_samples,
        top_n=top_n,
    )
    diagnostics = _diagnostics(
        bars=bars,
        scores=scores,
        lifecycle_samples=lifecycle_samples,
        entry_success=entry_success,
    )
    output_dir = Path(reports_dir) / f"trend_lifecycle_v1_{start.replace('-', '')}_{end.replace('-', '')}"
    paths = write_trend_lifecycle_outputs(
        output_dir=output_dir,
        start_date=start,
        end_date=end,
        segments=segments,
        lifecycle_samples=lifecycle_samples,
        entry_success=entry_success,
        top20_stage_hits=top20_stage_hits,
        diagnostics=diagnostics,
    )
    return {
        "paths": paths,
        "segments": segments,
        "lifecycle_samples": lifecycle_samples,
        "entry_success": entry_success,
        "top20_stage_hits": top20_stage_hits,
        "diagnostics": diagnostics,
    }


def load_trend_lifecycle_bars(
    start_date: str,
    end_date: str,
    *,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
    future_buffer_days: int = 220,
) -> pd.DataFrame:
    buffered_end = (
        pd.Timestamp(end_date) + pd.Timedelta(days=int(future_buffer_days))
    ).date().isoformat()
    sql = """
    SELECT
        asset_id,
        trade_date,
        open,
        high,
        low,
        close,
        amount
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, buffered_end])
    return pd.DataFrame(rows)


def load_top20_scores(
    start_date: str,
    end_date: str,
    *,
    score_version: str = "manual_v1",
    top_n: int = 20,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date, asset_id, rank, score_total
    FROM factor.stock_score_daily
    WHERE score_version = %s
      AND trade_date BETWEEN %s AND %s
      AND rank <= %s
    ORDER BY trade_date, rank, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [score_version, start_date, end_date, int(top_n)])
    return pd.DataFrame(rows)


def write_trend_lifecycle_outputs(
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
    segments: pd.DataFrame,
    lifecycle_samples: pd.DataFrame,
    entry_success: pd.DataFrame,
    top20_stage_hits: pd.DataFrame,
    diagnostics: list[str],
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    paths = {
        "trend_segments": str(path / "trend_segments.csv"),
        "lifecycle_samples": str(path / "lifecycle_samples.csv"),
        "entry_success_labels": str(path / "entry_success_labels.csv"),
        "top20_stage_hit_report": str(path / "top20_stage_hit_report.csv"),
        "markdown_report": str(path / "trend_lifecycle_report.md"),
    }

    segments.reindex(columns=TREND_SEGMENT_COLUMNS).to_csv(paths["trend_segments"], index=False)
    lifecycle_samples.reindex(columns=LIFECYCLE_SAMPLE_COLUMNS).to_csv(
        paths["lifecycle_samples"],
        index=False,
    )
    entry_success.reindex(columns=ENTRY_SUCCESS_COLUMNS).to_csv(
        paths["entry_success_labels"],
        index=False,
    )
    top20_stage_hits.reindex(columns=TOP20_STAGE_HIT_COLUMNS).to_csv(
        paths["top20_stage_hit_report"],
        index=False,
    )
    Path(paths["markdown_report"]).write_text(
        _markdown_report(
            start_date=_iso_date(start_date),
            end_date=_iso_date(end_date),
            segments=segments,
            lifecycle_samples=lifecycle_samples,
            entry_success=entry_success,
            top20_stage_hits=top20_stage_hits,
            diagnostics=diagnostics,
        ),
        encoding="utf-8",
    )
    return paths


def _deduplicate_segments(
    candidates: list[dict[str, Any]],
    rule: TrendRule,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    if rule.label == "large_trend":
        ordered = sorted(
            candidates,
            key=lambda row: (-float(row["gain"]), int(row["_start_index"])),
        )
    else:
        ordered = sorted(
            candidates,
            key=lambda row: (int(row["_start_index"]), -float(row["gain"])),
        )

    selected: list[dict[str, Any]] = []
    for candidate in ordered:
        if any(_segments_overlap(candidate, kept) for kept in selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda row: int(row["_start_index"]))


def _segments_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return not (
        int(left["_peak_index"]) < int(right["_start_index"])
        or int(left["_start_index"]) > int(right["_peak_index"])
    )


def _entry_success_for_signal(
    asset_bars: pd.DataFrame | None,
    trade_date: str,
    rule: EntrySuccessRule,
) -> tuple[bool, bool]:
    if asset_bars is None or asset_bars.empty:
        return False, False
    matches = asset_bars.index[asset_bars["trade_date"].astype(str) == trade_date].tolist()
    if not matches:
        return False, False
    index = int(matches[-1])
    entry_close = asset_bars.loc[index, "close"]
    if _is_missing(entry_close) or float(entry_close) <= 0:
        return False, False
    future = asset_bars.iloc[index + 1 : index + rule.horizon + 1]
    covered = len(future) >= rule.horizon
    for row in future.to_dict("records"):
        close = row.get("close")
        if _is_missing(close):
            continue
        value = float(close) / float(entry_close) - 1.0
        if value <= rule.stop_threshold:
            return False, covered
        if value >= rule.profit_threshold:
            return True, covered
    return False, covered


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame(columns=["asset_id", "trade_date", "open", "high", "low", "close", "amount"])
    frame = bars.copy()
    if "asset_id" not in frame.columns:
        frame["asset_id"] = ""
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    for column in ("open", "high", "low", "close", "amount"):
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def _max_drawdown(series: pd.Series) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return 0.0
    rolling_max = clean.cummax()
    drawdown = clean / rolling_max - 1.0
    return float(drawdown.min()) if not drawdown.empty else 0.0


def _max_drawdown_array(values: np.ndarray) -> float:
    clean = values[~np.isnan(values)]
    if clean.size == 0:
        return 0.0
    rolling_max = np.maximum.accumulate(clean)
    drawdown = clean / rolling_max - 1.0
    return float(np.nanmin(drawdown)) if drawdown.size else 0.0


def _diagnostics(
    *,
    bars: pd.DataFrame,
    scores: pd.DataFrame,
    lifecycle_samples: pd.DataFrame,
    entry_success: pd.DataFrame,
) -> list[str]:
    result = []
    if lifecycle_samples.empty:
        result.append("No lifecycle samples overlapped the requested Top20 diagnostic window.")
    if entry_success.empty:
        result.append("No entry success labels were generated because Top20 score rows were empty.")
    uncovered = _entry_uncovered_counts(entry_success)
    for name, count in uncovered.items():
        if count > 0:
            result.append(f"{name} has {count} rows without a full future window.")
    if bars["amount"].isna().any():
        result.append("Some bar rows have missing amount; segment liquidity averages may exclude those values.")
    if scores.empty:
        result.append("Top20 score rows are missing; lifecycle stage hit diagnostics cannot be computed.")
    result.append(
        "Fundamental point-in-time coverage is not used in phase 1 scoring; "
        "future V2 work must use announcement-date availability."
    )
    return result


def _entry_uncovered_counts(entry_success: pd.DataFrame) -> dict[str, int]:
    counts = {}
    for rule in DEFAULT_ENTRY_SUCCESS_RULES:
        column = f"{rule.name}_covered"
        if column in entry_success.columns:
            counts[rule.name] = int((entry_success[column] == False).sum())  # noqa: E712
    return counts


def _markdown_report(
    *,
    start_date: str,
    end_date: str,
    segments: pd.DataFrame,
    lifecycle_samples: pd.DataFrame,
    entry_success: pd.DataFrame,
    top20_stage_hits: pd.DataFrame,
    diagnostics: list[str],
) -> str:
    lines = [
        "# Trend Lifecycle V1 Report",
        "",
        "This report is for research diagnostics only. It does not replace production Top20 reports.",
        "",
        "## Data Scope",
        "",
        f"- Period: {start_date} to {end_date}",
        "- Universe: assets present in `market_daily_bar` for the selected adjusted bar set.",
        "- Filters: trend segments require average amount >= 30,000,000.",
        "- Fundamental data: not used for phase 1 scoring; point-in-time availability is listed as a V2 requirement.",
        "",
        "## Trend Segments",
        "",
        _markdown_table(_segment_counts(segments)),
        "",
        "## mid_trend early / early_mid samples",
        "",
        _markdown_table(_mid_early_counts(lifecycle_samples)),
        "",
        "## Entry Success Labels",
        "",
        _markdown_table(_entry_success_summary(entry_success)),
        "",
        "## Current Top20 Lifecycle Stage Hits",
        "",
        _markdown_table(top20_stage_hits),
        "",
        _top20_bias_sentence(top20_stage_hits),
        "",
        "## Data Issues",
        "",
    ]
    if diagnostics:
        lines.extend(f"- {item}" for item in diagnostics)
    else:
        lines.append("- No data issues detected by phase 1 diagnostics.")
    lines.extend(
        [
            "",
            "## Next Stage",
            "",
            "- Evaluate early and early_mid mid_trend factor profiles.",
            "- Add point-in-time fundamental coverage audit before using financial features.",
            "- Design low-turnover holding rules only after label and lifecycle diagnostics are stable.",
            "",
        ]
    )
    return "\n".join(lines)


def _segment_counts(segments: pd.DataFrame) -> pd.DataFrame:
    if segments.empty:
        return pd.DataFrame(columns=["trend_label", "segments"])
    return (
        segments.groupby("trend_label", as_index=False)
        .size()
        .rename(columns={"size": "segments"})
    )


def _mid_early_counts(lifecycle_samples: pd.DataFrame) -> pd.DataFrame:
    if lifecycle_samples.empty:
        return pd.DataFrame(columns=["trend_label", "stage", "samples"])
    frame = lifecycle_samples[
        (lifecycle_samples["trend_label"] == "mid_trend")
        & (lifecycle_samples["stage"].isin(["early", "early_mid"]))
    ]
    if frame.empty:
        return pd.DataFrame(columns=["trend_label", "stage", "samples"])
    return (
        frame.groupby(["trend_label", "stage"], as_index=False)
        .size()
        .rename(columns={"size": "samples"})
    )


def _entry_success_summary(entry_success: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rule in DEFAULT_ENTRY_SUCCESS_RULES:
        success_column = rule.name
        covered_column = f"{rule.name}_covered"
        if success_column not in entry_success.columns:
            rows.append(
                {
                    "label": rule.name,
                    "rows": 0,
                    "covered_rows": 0,
                    "successes": 0,
                    "success_rate": None,
                }
            )
            continue
        covered = (
            entry_success[covered_column].astype(bool)
            if covered_column in entry_success.columns
            else pd.Series([True] * len(entry_success))
        )
        covered_rows = entry_success[covered]
        successes = int(covered_rows[success_column].astype(bool).sum())
        rows.append(
            {
                "label": rule.name,
                "rows": int(len(entry_success)),
                "covered_rows": int(len(covered_rows)),
                "successes": successes,
                "success_rate": successes / len(covered_rows) if len(covered_rows) else None,
            }
        )
    return pd.DataFrame(rows)


def _top20_bias_sentence(top20_stage_hits: pd.DataFrame) -> str:
    if top20_stage_hits.empty:
        return "No Current Top20 lifecycle hits were found for this window."
    stage_counts = (
        top20_stage_hits.groupby("stage", as_index=False)["hits"]
        .sum()
        .sort_values("hits", ascending=False)
    )
    dominant_stage = str(stage_counts.iloc[0]["stage"])
    return f"Dominant Current Top20 lifecycle stage: `{dominant_stage}`."


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    return frame.to_markdown(index=False)


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _is_missing(value: object) -> bool:
    return value is None or pd.isna(value)
