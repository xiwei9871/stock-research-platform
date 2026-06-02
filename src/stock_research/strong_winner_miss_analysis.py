from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.technical_method_validation import load_validation_bars


WATCH_GROUPS = {"opportunity_watch", "high_odds_burst_watch", "risk_watch"}

STRONG_WINNER_COLUMNS = [
    "winner_id",
    "asset_id",
    "ts_code",
    "stock_name",
    "segment_start_date",
    "double_confirm_date",
    "segment_peak_date",
    "segment_low",
    "segment_start_close",
    "segment_peak_high",
    "low_to_peak_return",
    "close_to_peak_return",
    "days_to_double",
    "days_to_peak",
    "window_days",
    "winner_definition",
]

MISS_ANALYSIS_COLUMNS = STRONG_WINNER_COLUMNS + [
    "diagnostics_seen_pre_double",
    "must_watch_seen_pre_double",
    "risk_watch_seen_pre_double",
    "opportunity_seen_pre_double",
    "high_odds_seen_pre_double",
    "candidate_seen_pre_double",
    "first_diagnostics_date",
    "first_watch_date",
    "first_must_watch_date",
    "first_watch_group",
    "first_event_structure",
    "first_score_rank",
    "best_pre_double_score_rank",
    "first_diagnostic_reason",
    "first_risk_note",
    "first_opportunity_note",
    "capture_status",
    "miss_reason",
]


def run_strong_winner_miss_analysis(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    window_days: int = 60,
    threshold: float = 1.0,
    diagnostics_dir: str | Path,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    bars = load_validation_bars(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    bars = enrich_bars_with_asset_identity(bars, service=service)
    diagnostics_rows = load_watchlist_diagnostics_rows(
        diagnostics_dir,
        start_date=start_date,
        end_date=end_date,
        must_watch=False,
    )
    must_watch_rows = load_watchlist_diagnostics_rows(
        diagnostics_dir,
        start_date=start_date,
        end_date=end_date,
        must_watch=True,
    )
    return build_strong_winner_miss_analysis_from_frames(
        bars=bars,
        diagnostics_rows=diagnostics_rows,
        must_watch_rows=must_watch_rows,
        start_date=start_date,
        end_date=end_date,
        window_days=window_days,
        threshold=threshold,
        output_dir=output_dir,
    )


def enrich_bars_with_asset_identity(
    bars: pd.DataFrame,
    *,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if bars.empty or "asset_id" not in bars.columns:
        return bars.copy()
    asset_ids = sorted({str(value) for value in bars["asset_id"].dropna().unique()})
    identity = load_asset_identity(asset_ids, service=service)
    if identity.empty:
        return bars.copy()
    enriched = bars.drop(columns=[column for column in ["stock_name"] if column in bars.columns], errors="ignore").merge(
        identity,
        on="asset_id",
        how="left",
        suffixes=("", "_identity"),
    )
    if "ts_code_identity" in enriched.columns:
        enriched["ts_code"] = enriched["ts_code"].fillna(enriched["ts_code_identity"]) if "ts_code" in enriched.columns else enriched["ts_code_identity"]
        enriched = enriched.drop(columns=["ts_code_identity"])
    return enriched


def load_asset_identity(
    asset_ids: list[str],
    *,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    columns = ["asset_id", "ts_code", "stock_name"]
    if not asset_ids:
        return pd.DataFrame(columns=columns)
    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT asset_id, ts_code, name AS stock_name
        FROM core.asset_master
        WHERE asset_id IN ({placeholders})
        ORDER BY asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, asset_ids)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame.loc[:, columns].drop_duplicates("asset_id", keep="first")


def scan_strong_winner_60d(
    bars: pd.DataFrame,
    *,
    window_days: int = 60,
    threshold: float = 1.0,
) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame(columns=STRONG_WINNER_COLUMNS)

    rows: list[dict[str, Any]] = []
    normalized = bars.copy()
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    for asset_id, group in normalized.sort_values(["asset_id", "trade_date"]).groupby("asset_id", sort=False):
        asset = group.reset_index(drop=True).copy()
        lows = pd.to_numeric(asset["low"], errors="coerce").to_numpy(dtype=float)
        highs = pd.to_numeric(asset["high"], errors="coerce").to_numpy(dtype=float)
        closes = pd.to_numeric(asset["close"], errors="coerce").to_numpy(dtype=float)
        dates = asset["trade_date"].to_list()
        candidates: list[dict[str, Any]] = []
        for start_index in range(len(asset)):
            segment_low = lows[start_index]
            if not np.isfinite(segment_low) or segment_low <= 0:
                continue
            end_index = min(len(asset), start_index + window_days + 1)
            future_highs = highs[start_index:end_index]
            if future_highs.size == 0 or np.all(np.isnan(future_highs)):
                continue
            target_high = segment_low * (1.0 + threshold)
            hit_offsets = np.flatnonzero(future_highs >= target_high)
            if hit_offsets.size == 0:
                continue
            peak_offset = int(np.nanargmax(future_highs))
            peak_index = start_index + peak_offset
            confirm_index = start_index + int(hit_offsets[0])
            peak_high = highs[peak_index]
            start_close = closes[start_index]
            candidates.append(
                {
                    "asset_id": str(asset_id),
                    "ts_code": _first_nonempty(asset.get("ts_code")),
                    "stock_name": _first_nonempty(asset.get("stock_name")),
                    "segment_start_date": _date_string(dates[start_index]),
                    "double_confirm_date": _date_string(dates[confirm_index]),
                    "segment_peak_date": _date_string(dates[peak_index]),
                    "segment_low": float(segment_low),
                    "segment_start_close": float(start_close) if np.isfinite(start_close) else np.nan,
                    "segment_peak_high": float(peak_high),
                    "low_to_peak_return": float(peak_high / segment_low - 1.0),
                    "close_to_peak_return": float(peak_high / start_close - 1.0) if np.isfinite(start_close) and start_close > 0 else np.nan,
                    "days_to_double": int(confirm_index - start_index),
                    "days_to_peak": int(peak_index - start_index),
                    "window_days": int(window_days),
                    "winner_definition": f"low_to_high_return>={threshold:.2f}_within_{window_days}_trading_days",
                }
            )
        if candidates:
            chosen = sorted(candidates, key=lambda row: (row["double_confirm_date"], -row["low_to_peak_return"]))[0]
            rows.append(chosen)

    winners = pd.DataFrame(rows)
    if winners.empty:
        return pd.DataFrame(columns=STRONG_WINNER_COLUMNS)
    winners = winners.sort_values(["double_confirm_date", "asset_id"]).reset_index(drop=True)
    winners.insert(0, "winner_id", [f"SW60D-{index + 1:04d}" for index in range(len(winners))])
    return winners.reindex(columns=STRONG_WINNER_COLUMNS)


def build_strong_winner_miss_analysis_from_frames(
    *,
    bars: pd.DataFrame,
    diagnostics_rows: pd.DataFrame,
    must_watch_rows: pd.DataFrame,
    start_date: str,
    end_date: str,
    window_days: int = 60,
    threshold: float = 1.0,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    winners = scan_strong_winner_60d(bars, window_days=window_days, threshold=threshold)
    diagnostics = _normalize_diagnostics(diagnostics_rows)
    must_watch = _normalize_diagnostics(must_watch_rows)
    analysis = build_miss_analysis(
        strong_winners=winners,
        diagnostics_rows=diagnostics,
        must_watch_rows=must_watch,
    )
    summary = build_miss_summary(analysis, diagnostics)
    report = render_strong_winner_miss_report(
        start_date=start_date,
        end_date=end_date,
        window_days=window_days,
        threshold=threshold,
        summary=summary,
        analysis=analysis,
    )

    result: dict[str, Any] = {
        "strong_winners": winners,
        "miss_analysis": analysis,
        "summary": summary,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "strong_winners": output / "strong_winner_60d_2025_to_now.csv",
            "miss_analysis": output / "strong_winner_miss_analysis_2025_to_now.csv",
            "summary": output / "strong_winner_miss_summary_2025_to_now.csv",
            "report": output / "strong_winner_miss_analysis_report.md",
        }
        winners.to_csv(paths["strong_winners"], index=False)
        analysis.to_csv(paths["miss_analysis"], index=False)
        summary.to_csv(paths["summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = paths
    return result


def build_miss_analysis(
    *,
    strong_winners: pd.DataFrame,
    diagnostics_rows: pd.DataFrame,
    must_watch_rows: pd.DataFrame,
) -> pd.DataFrame:
    if strong_winners.empty:
        return pd.DataFrame(columns=MISS_ANALYSIS_COLUMNS)

    diagnostics_date_min = _min_date(diagnostics_rows)
    diagnostics_date_max = _max_date(diagnostics_rows)
    diagnostics_dates = _date_set(diagnostics_rows)
    rows = []
    for winner in strong_winners.to_dict("records"):
        asset_id = str(winner.get("asset_id"))
        start = pd.to_datetime(winner.get("segment_start_date"))
        confirm = pd.to_datetime(winner.get("double_confirm_date"))
        peak = pd.to_datetime(winner.get("segment_peak_date"))
        full_asset = _window_rows(diagnostics_rows, asset_id=asset_id, start=start, end=peak)
        pre_full = full_asset[pd.to_datetime(full_asset["trade_date"]) < confirm].copy() if not full_asset.empty else full_asset
        must_asset = _window_rows(must_watch_rows, asset_id=asset_id, start=start, end=peak)
        pre_must = must_asset[pd.to_datetime(must_asset["trade_date"]) < confirm].copy() if not must_asset.empty else must_asset

        watch_pre = pre_full[pre_full["watch_group"].isin(WATCH_GROUPS)].sort_values(["trade_date", "score_rank"])
        first_watch = watch_pre.iloc[0] if not watch_pre.empty else None
        first_must = pre_must.sort_values(["trade_date", "score_rank"]).iloc[0] if not pre_must.empty else None
        first_diag = pre_full.sort_values(["trade_date", "score_rank"]).iloc[0] if not pre_full.empty else None
        best_rank = pd.to_numeric(pre_full.get("score_rank"), errors="coerce").min() if not pre_full.empty and "score_rank" in pre_full else np.nan
        capture_status, miss_reason = _classify_capture(
            pre_full=pre_full,
            pre_must=pre_must,
            watch_pre=watch_pre,
            must_asset=must_asset,
            confirm=confirm,
            diagnostics_date_min=diagnostics_date_min,
            diagnostics_date_max=diagnostics_date_max,
            diagnostics_dates=diagnostics_dates,
            start=start,
        )
        identity_row = first_watch if first_watch is not None else first_diag
        row = dict(winner)
        if not row.get("stock_name") and identity_row is not None:
            row["stock_name"] = identity_row.get("stock_name")
        row.update(
            {
                "diagnostics_seen_pre_double": bool(not pre_full.empty),
                "must_watch_seen_pre_double": bool(not pre_must.empty),
                "risk_watch_seen_pre_double": bool((pre_full["watch_group"] == "risk_watch").any()) if not pre_full.empty else False,
                "opportunity_seen_pre_double": bool((pre_full["watch_group"] == "opportunity_watch").any()) if not pre_full.empty else False,
                "high_odds_seen_pre_double": bool((pre_full["watch_group"] == "high_odds_burst_watch").any()) if not pre_full.empty else False,
                "candidate_seen_pre_double": bool((pre_full["watch_group"] == "candidate").any()) if not pre_full.empty else False,
                "first_diagnostics_date": _row_value(first_diag, "trade_date"),
                "first_watch_date": _row_value(first_watch, "trade_date"),
                "first_must_watch_date": _row_value(first_must, "trade_date"),
                "first_watch_group": _row_value(first_watch, "watch_group"),
                "first_event_structure": _row_value(first_watch, "event_structure") or _row_value(first_diag, "event_structure"),
                "first_score_rank": _row_value(first_watch, "score_rank"),
                "best_pre_double_score_rank": best_rank,
                "first_diagnostic_reason": _row_value(first_watch, "diagnostic_reason") or _row_value(first_diag, "diagnostic_reason"),
                "first_risk_note": _row_value(first_watch, "risk_note") or _row_value(first_diag, "risk_note"),
                "first_opportunity_note": _row_value(first_watch, "opportunity_note") or _row_value(first_diag, "opportunity_note"),
                "capture_status": capture_status,
                "miss_reason": miss_reason,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=MISS_ANALYSIS_COLUMNS)


def build_miss_summary(analysis: pd.DataFrame, diagnostics_rows: pd.DataFrame) -> pd.DataFrame:
    if analysis.empty:
        return pd.DataFrame(
            [
                {"metric": "strong_winner_count", "value": 0},
                {"metric": "diagnostics_date_count", "value": int(diagnostics_rows["trade_date"].nunique()) if "trade_date" in diagnostics_rows else 0},
            ]
        )
    total = len(analysis)
    rows = [
        {"metric": "strong_winner_count", "value": int(total)},
        {"metric": "captured_pre_double_count", "value": int((analysis["capture_status"] == "captured_pre_double").sum())},
        {"metric": "risk_watch_pre_double_count", "value": int((analysis["capture_status"] == "risk_watch_pre_double").sum())},
        {"metric": "in_diagnostics_not_watch_count", "value": int((analysis["capture_status"] == "in_diagnostics_not_watch").sum())},
        {"metric": "captured_after_double_count", "value": int((analysis["capture_status"] == "captured_after_double").sum())},
        {"metric": "missed_count", "value": int((analysis["capture_status"] == "missed").sum())},
        {"metric": "capture_rate_pre_double", "value": float((analysis["capture_status"] == "captured_pre_double").mean())},
        {"metric": "risk_false_positive_count", "value": int((analysis["miss_reason"] == "risk_rule_false_positive").sum())},
        {"metric": "diagnostics_date_count", "value": int(diagnostics_rows["trade_date"].nunique()) if "trade_date" in diagnostics_rows else 0},
    ]
    reason_counts = analysis["miss_reason"].fillna("").replace("", "none").value_counts()
    rows.extend({"metric": f"miss_reason:{reason}", "value": int(value)} for reason, value in reason_counts.items())
    group_counts = analysis["first_watch_group"].fillna("").replace("", "none").value_counts()
    rows.extend({"metric": f"first_watch_group:{group}", "value": int(value)} for group, value in group_counts.items())
    return pd.DataFrame(rows)


def load_watchlist_diagnostics_rows(
    diagnostics_dir: str | Path,
    *,
    start_date: str,
    end_date: str,
    must_watch: bool,
) -> pd.DataFrame:
    path = Path(diagnostics_dir)
    prefix = "watchlist_diagnostics_must_watch_" if must_watch else "watchlist_diagnostics_"
    files = sorted(
        file
        for file in path.glob(f"{prefix}*_diagnostics_v1.csv")
        if must_watch or not file.name.startswith("watchlist_diagnostics_must_watch_")
    )
    frames = []
    for file in files:
        frame = pd.read_csv(file)
        if "trade_date" not in frame:
            continue
        dates = pd.to_datetime(frame["trade_date"], errors="coerce")
        frame = frame[(dates >= pd.to_datetime(start_date)) & (dates <= pd.to_datetime(end_date))]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def render_strong_winner_miss_report(
    *,
    start_date: str,
    end_date: str,
    window_days: int,
    threshold: float,
    summary: pd.DataFrame,
    analysis: pd.DataFrame,
) -> str:
    top_missed = analysis[analysis["capture_status"].ne("captured_pre_double")].head(30) if not analysis.empty else pd.DataFrame()
    by_status = analysis["capture_status"].value_counts().reset_index() if not analysis.empty else pd.DataFrame(columns=["capture_status", "count"])
    by_status.columns = ["capture_status", "count"]
    return "\n".join(
        [
            "# Strong Winner Miss Analysis v1",
            "",
            "## 1. Definition",
            f"- Window: {window_days} trading days",
            f"- Strong winner: low-to-future-high return >= {threshold:.0%}",
            f"- Date range: {start_date}..{end_date}",
            "- This is post-event attribution only. It is not a live signal and does not enter strategy scoring.",
            "",
            "## 2. Summary",
            summary.to_markdown(index=False) if not summary.empty else "No summary rows.",
            "",
            "## 3. Capture Status",
            by_status.to_markdown(index=False) if not by_status.empty else "No capture rows.",
            "",
            "## 4. Missed / Late / Risk-Watch Examples",
            top_missed[
                [
                    "asset_id",
                    "ts_code",
                    "stock_name",
                    "segment_start_date",
                    "double_confirm_date",
                    "low_to_peak_return",
                    "capture_status",
                    "miss_reason",
                    "first_watch_group",
                    "best_pre_double_score_rank",
                ]
            ].to_markdown(index=False)
            if not top_missed.empty
            else "No missed rows.",
            "",
            "## 5. How To Read This",
            "- `captured_pre_double`: watchlist caught the stock before it first doubled.",
            "- `risk_watch_pre_double`: the system saw it before doubling but treated it as risk.",
            "- `in_diagnostics_not_watch`: it entered top diagnostics but was not selected into a watch group.",
            "- `missed`: no useful pre-double diagnostics/watchlist capture was found.",
        ]
    ) + "\n"


def _normalize_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "ts_code",
        "stock_name",
        "score_rank",
        "watch_group",
        "event_structure",
        "diagnostic_reason",
        "risk_note",
        "opportunity_note",
    ]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result["asset_id"] = result["asset_id"].astype(str)
    result["score_rank"] = pd.to_numeric(result["score_rank"], errors="coerce")
    result["watch_group"] = result["watch_group"].fillna("").astype(str)
    return result.loc[:, columns]


def _classify_capture(
    *,
    pre_full: pd.DataFrame,
    pre_must: pd.DataFrame,
    watch_pre: pd.DataFrame,
    must_asset: pd.DataFrame,
    confirm: pd.Timestamp,
    diagnostics_date_min: pd.Timestamp | None,
    diagnostics_date_max: pd.Timestamp | None,
    diagnostics_dates: set[pd.Timestamp],
    start: pd.Timestamp,
) -> tuple[str, str]:
    if not pre_must.empty and bool(pre_must["watch_group"].isin({"opportunity_watch", "high_odds_burst_watch"}).any()):
        return "captured_pre_double", ""
    if not pre_must.empty:
        return "risk_watch_pre_double", "risk_rule_false_positive"
    if not watch_pre.empty and bool((watch_pre["watch_group"] == "risk_watch").any()):
        return "risk_watch_pre_double", "risk_rule_false_positive"
    if not watch_pre.empty:
        return "captured_pre_double", ""
    if not pre_full.empty:
        return "in_diagnostics_not_watch", "watch_group_candidate_only"
    post_confirm_must = must_asset[pd.to_datetime(must_asset["trade_date"], errors="coerce") >= confirm] if not must_asset.empty else must_asset
    if not post_confirm_must.empty:
        return "captured_after_double", "late_capture_after_double"
    covered_pre_double_dates = [
        date for date in diagnostics_dates
        if date >= start.normalize() and date < confirm.normalize()
    ]
    if (
        diagnostics_date_min is None
        or diagnostics_date_max is None
        or diagnostics_date_max < start
        or diagnostics_date_min > confirm
        or not covered_pre_double_dates
    ):
        return "missed", "outside_diagnostics_date_range"
    return "missed", "not_in_topn_diagnostics"


def _window_rows(frame: pd.DataFrame, *, asset_id: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    dates = pd.to_datetime(frame["trade_date"], errors="coerce")
    rows = frame[(frame["asset_id"].astype(str) == asset_id) & (dates >= start) & (dates <= end)].copy()
    return rows.sort_values(["trade_date", "score_rank"], na_position="last").reset_index(drop=True)


def _row_value(row: pd.Series | None, column: str) -> Any:
    if row is None:
        return ""
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    if column == "trade_date":
        return _date_string(value)
    return value


def _min_date(frame: pd.DataFrame) -> pd.Timestamp | None:
    if frame.empty or "trade_date" not in frame:
        return None
    value = pd.to_datetime(frame["trade_date"], errors="coerce").min()
    return None if pd.isna(value) else value


def _max_date(frame: pd.DataFrame) -> pd.Timestamp | None:
    if frame.empty or "trade_date" not in frame:
        return None
    value = pd.to_datetime(frame["trade_date"], errors="coerce").max()
    return None if pd.isna(value) else value


def _date_set(frame: pd.DataFrame) -> set[pd.Timestamp]:
    if frame.empty or "trade_date" not in frame:
        return set()
    values = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    return {pd.Timestamp(value).normalize() for value in values}


def _first_nonempty(series: pd.Series | None) -> str:
    if series is None:
        return ""
    for value in series:
        if not pd.isna(value) and str(value).strip():
            return str(value).strip()
    return ""


def _date_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(pd.to_datetime(value).date())
