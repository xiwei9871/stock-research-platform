from __future__ import annotations

from bisect import bisect_left
from pathlib import Path
from typing import Any
import unicodedata

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED_PATH = ROOT / "data" / "seed" / "dragon_case_seed.csv"
DEFAULT_WEB_SEED_PATH = ROOT / "data" / "seed" / "dragon_case_web_seed_2024_2026.csv"
DEFAULT_WEB_ARTICLE_SEED_PATH = ROOT / "data" / "seed" / "dragon_case_web_article_seed_2024_2026.csv"

CASE_LIBRARY_COLUMNS = [
    "case_id",
    "stock_code",
    "ts_code",
    "stock_name",
    "case_year",
    "theme",
    "industry_name",
    "case_type",
    "role",
    "success_or_failure",
    "market_cycle",
    "start_date",
    "first_limit_up_date",
    "streak_start_date",
    "streak_end_date",
    "max_limit_up_count",
    "break_limit_date",
    "reversal_date",
    "second_wave_start_date",
    "second_wave_end_date",
    "peak_date",
    "cooling_down_date",
    "a_kill_start_date",
    "source_title",
    "source_url",
    "source_type",
    "manual_confidence",
    "notes",
    "stage_return",
    "max_drawdown",
    "break_to_reversal_days",
    "break_to_second_wave_days",
]

CASE_OUTPUT_FILENAMES = {
    "case_library": "dragon_case_library.csv",
    "auto_candidates": "dragon_case_auto_candidates.csv",
    "event_diagnostics": "dragon_case_event_diagnostics.csv",
    "success_failure_comparison": "dragon_case_success_failure_comparison.csv",
    "markdown_report": "dragon_case_library_report.md",
}

WEB_SEED_COLUMNS = [
    "stock_name",
    "ts_code",
    "case_year",
    "theme",
    "case_type",
    "source_title",
    "source_url",
    "source_date",
    "source_type",
    "approximate_start_date",
    "approximate_end_date",
    "source_note",
]

WEB_CANDIDATE_COLUMNS = [
    "web_candidate_id",
    "stock_name",
    "ts_code",
    "case_year",
    "theme",
    "claimed_case_type",
    "source_title",
    "source_url",
    "source_date",
    "source_type",
    "source_confidence",
    "approximate_start_date",
    "approximate_end_date",
    "imported_at",
]

WEB_VERIFICATION_COLUMNS = [
    "web_candidate_id",
    "ts_code",
    "stock_name",
    "claimed_case_type",
    "verified_case_type",
    "event_verified",
    "first_limit_up_date",
    "max_limit_up_count",
    "streak_start_date",
    "streak_end_date",
    "break_limit_date",
    "reversal_date",
    "second_wave_start_date",
    "peak_date",
    "a_kill_start_date",
    "stage_return",
    "max_drawdown",
    "verification_score",
    "verification_reason",
    "case_year",
    "theme",
    "source_title",
    "source_url",
    "source_type",
    "source_confidence",
    "approximate_start_date",
    "approximate_end_date",
]

WEB_FACTOR_REVIEW_COLUMNS = [
    "web_candidate_id",
    "ts_code",
    "stock_name",
    "event_type",
    "event_date",
    "relative_day",
    "trade_date",
    "dragon_status_score",
    "dragon_entry_score",
    "dragon_entry_score_v2",
    "dragon_risk_score",
    "entry_window",
    "entry_window_v2",
    "dragon_role",
    "industry_focus_score_v2",
    "market_regime",
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
]

WEB_CURATED_COLUMNS = [
    "case_id",
    "stock_code",
    "ts_code",
    "stock_name",
    "case_year",
    "theme",
    "industry_name",
    "case_type",
    "role",
    "success_or_failure",
    "source_title",
    "source_url",
    "source_type",
    "source_confidence",
    "event_verified",
    "verified_case_type",
    "verification_score",
    "case_confidence_score",
    "first_limit_up_date",
    "max_limit_up_count",
    "break_limit_date",
    "reversal_date",
    "second_wave_start_date",
    "peak_date",
    "a_kill_start_date",
    "stage_return",
    "max_drawdown",
    "dragon_factor_available",
    "source_origin",
    "web_source_available",
    "local_event_verified",
    "needs_web_source",
    "suggested_search_query",
    "review_status",
    "reviewer_note",
    "notes",
    "web_candidate_id",
]

WEB_SOURCE_EVIDENCE_COLUMNS = [
    "case_id",
    "web_candidate_id",
    "ts_code",
    "stock_name",
    "source_title",
    "source_url",
    "source_date",
    "source_type",
    "extracted_case_type",
    "evidence_score",
    "notes",
]

WEB_SEED_COVERAGE_COLUMNS = [
    "year",
    "source_type",
    "article_count",
    "stock_seed_count",
    "matched_stock_count",
    "unmatched_stock_count",
    "average_source_confidence",
    "case_type_distribution",
]

WEB_UNMATCHED_COLUMNS = [
    "stock_name",
    "normalized_stock_name",
    "possible_matches",
    "unmatched_reason",
    "source_title",
    "source_url",
    "source_date",
    "source_type",
    "source_confidence",
    "approximate_start_date",
    "approximate_end_date",
    "article_id",
]

ALIGNMENT_AUDIT_COLUMNS = [
    "case_id",
    "web_candidate_id",
    "ts_code",
    "stock_name",
    "event_type",
    "event_date",
    "relative_day",
    "trade_date",
    "has_price_data",
    "has_dragon_v1_2",
    "has_dragon_v1_3",
    "has_industry_focus",
    "has_market_regime",
    "matched_on_exact_date",
    "matched_on_nearest_previous_trade_date",
    "matched_on_nearest_next_trade_date",
    "diagnostics_file",
    "diagnostics_min_date",
    "diagnostics_max_date",
    "diagnostics_has_ts_code",
    "diagnostics_has_asset_id",
    "diagnostics_date_granularity",
    "case_event_in_diagnostics_date_range",
    "case_stock_exists_in_diagnostics_any_date",
    "case_stock_exists_on_nearby_dates",
    "exact_date_match",
    "previous_trade_date_match",
    "next_trade_date_match",
    "within_3_trade_days_match",
    "matched_trade_date",
    "event_date_non_trading_day",
    "final_alignment_status",
    "final_missing_reason",
    "missing_reason",
]

A_KILL_RULE_AUDIT_COLUMNS = [
    "case_id",
    "ts_code",
    "stock_name",
    "old_event_date",
    "new_event_date",
    "old_verified_case_type",
    "new_verified_case_type",
    "old_future_5d_return",
    "new_future_5d_return",
    "old_future_10d_return",
    "new_future_10d_return",
    "old_future_10d_max_drawdown",
    "new_future_10d_max_drawdown",
    "rule_change_reason",
]

MATCHING_SUMMARY_COLUMNS = [
    "match_stage",
    "total_count",
    "matched_count",
    "match_rate",
    "main_missing_reason",
    "notes",
]

CASE_FACTOR_SNAPSHOT_COLUMNS = [
    "case_id",
    "ts_code",
    "stock_name",
    "event_type",
    "event_date",
    "relative_day",
    "trade_date",
    "close",
    "daily_return",
    "pre_3d_return",
    "pre_5d_return",
    "pre_10d_return",
    "amount_vs_5d",
    "amount_vs_20d",
    "close_position_in_day",
    "high_to_close_drawdown",
    "volatility_5d",
    "stage_return",
    "limit_up_count_before_event",
    "is_limit_up_day",
    "is_break_limit_event",
    "is_reversal_event",
    "is_second_wave_event",
    "is_a_kill_event",
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
    "industry_name",
    "industry_return_5d",
    "industry_return_10d",
    "stock_excess_vs_industry_5d",
    "stock_excess_vs_industry_10d",
]

WEB_SEARCH_TARGET_COLUMNS = [
    "target_id",
    "ts_code",
    "stock_name",
    "case_year",
    "suggested_case_type",
    "start_date",
    "event_date",
    "candidate_quality_score",
    "event_strength_score",
    "stage_return",
    "max_drawdown",
    "max_limit_up_count",
    "suggested_search_query",
    "suggested_search_query_2",
    "reason",
]

FAILURE_TARGET_AUDIT_COLUMNS = [
    "target_id",
    "case_id",
    "ts_code",
    "stock_name",
    "case_year",
    "suggested_case_type",
    "event_date",
    "stage_return",
    "max_drawdown",
    "pre_5d_return",
    "post_3d_return",
    "post_5d_return",
    "post_10d_return",
    "post_5d_max_drawdown",
    "post_10d_max_drawdown",
    "amount_vs_20d",
    "high_to_close_drawdown",
    "max_limit_up_count",
    "event_strength_score",
    "failure_score",
    "failure_reason",
    "suggested_search_query",
    "suggested_search_query_2",
]

LOCAL_SOURCE_PRIORITY_COLUMNS = [
    "case_id",
    "ts_code",
    "stock_name",
    "case_year",
    "verified_case_type",
    "source_origin",
    "case_confidence_score",
    "event_strength_score",
    "failure_score",
    "source_priority_score",
    "needs_web_source",
    "suggested_search_query",
    "suggested_search_query_2",
    "suggested_search_query_3",
]

ARTICLE_SEED_SUGGESTION_COLUMNS = [
    "suggestion_id",
    "ts_code",
    "stock_name",
    "case_year",
    "suggested_case_type",
    "suggested_theme",
    "suggested_source_type",
    "suggested_search_query",
    "suggested_search_query_2",
    "suggested_search_query_3",
    "event_date",
    "reason",
    "priority_score",
    "article_seed_template_row",
]

SOURCE_BACKFILL_TASK_COLUMNS = [
    "task_id",
    "ts_code",
    "stock_name",
    "case_year",
    "suggested_case_type",
    "priority_score",
    "reason",
    "suggested_search_query",
    "suggested_search_query_2",
    "suggested_search_query_3",
    "preferred_source_type",
    "source_url",
    "source_title",
    "source_date",
    "source_type",
    "source_confidence",
    "backfill_status",
    "reviewer_note",
    "article_seed_template_row",
]

SOURCE_BACKFILL_APPLY_SUMMARY_COLUMNS = [
    "total_tasks",
    "found_tasks",
    "pending_tasks",
    "rejected_tasks",
    "not_found_tasks",
    "valid_found_tasks",
    "invalid_found_tasks",
    "inserted_article_seed_rows",
    "skipped_duplicate_rows",
    "article_seed_before_rows",
    "article_seed_after_rows",
]

SOURCE_BACKFILL_APPLY_ERROR_COLUMNS = [
    "task_id",
    "ts_code",
    "stock_name",
    "suggested_case_type",
    "source_url",
    "error_type",
    "error_message",
]

SOURCE_BACKFILL_DELTA_COLUMNS = [
    "metric",
    "before_value",
    "after_value",
    "delta",
]

SOURCE_BACKFILL_WORKPACK_COLUMNS = [
    "task_id",
    "ts_code",
    "stock_name",
    "case_year",
    "suggested_case_type",
    "priority_score",
    "reason",
    "suggested_search_query",
    "suggested_search_query_2",
    "suggested_search_query_3",
    "preferred_source_type",
    "recommended_source_type",
    "recommended_source_confidence",
    "confidence_note",
    "backfill_status",
    "source_url",
    "source_title",
    "source_date",
    "source_type",
    "source_confidence",
    "reviewer_note",
    "article_seed_template_row",
]


def read_case_seed(path: str | Path = DEFAULT_SEED_PATH) -> pd.DataFrame:
    seed_path = Path(path)
    if not seed_path.exists():
        return pd.DataFrame(
            columns=[
                "stock_name",
                "ts_code",
                "case_year",
                "theme",
                "case_type",
                "role",
                "approximate_start_date",
                "approximate_end_date",
                "source_title",
                "source_url",
                "notes",
            ]
        )
    return pd.read_csv(seed_path)


def read_web_case_seed(path: str | Path) -> pd.DataFrame:
    seed_path = Path(path)
    if not seed_path.exists():
        return pd.DataFrame(columns=WEB_SEED_COLUMNS)
    return pd.read_csv(seed_path).reindex(columns=WEB_SEED_COLUMNS)


def read_web_article_seed(path: str | Path = DEFAULT_WEB_ARTICLE_SEED_PATH) -> pd.DataFrame:
    seed_path = Path(path)
    if not seed_path.exists():
        return pd.DataFrame(
            columns=[
                "article_id",
                "source_title",
                "source_url",
                "source_date",
                "source_type",
                "source_confidence",
                "mentioned_stocks",
                "mentioned_ts_codes",
                "mentioned_themes",
                "mentioned_case_types",
                "notes",
            ]
        )
    return pd.read_csv(seed_path)


def load_asset_lookup(*, service: str = SETTINGS.research_service) -> pd.DataFrame:
    sql = """
        SELECT COALESCE(name, asset_id) AS stock_name,
               CASE
                   WHEN ts_code IS NOT NULL THEN ts_code
                   WHEN split_part(asset_id, ':', 1) = 'CN' AND split_part(asset_id, ':', 2) <> '' THEN
                       split_part(asset_id, ':', 3) || '.' || split_part(asset_id, ':', 2)
                   ELSE asset_id
               END AS ts_code
        FROM core.asset_master
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, []))


def expand_web_article_seeds(
    *,
    article_seed: pd.DataFrame,
    output_path: str | Path,
    output_dir: str | Path,
    asset_lookup: pd.DataFrame | None = None,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    lookup_frame = asset_lookup if asset_lookup is not None else load_asset_lookup()
    asset_map = _prepare_asset_lookup(lookup_frame)
    rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    article = article_seed.fillna("")
    for record in article.to_dict("records"):
        stocks = _split_multi_value(record.get("mentioned_stocks"))
        ts_codes = _split_multi_value(record.get("mentioned_ts_codes"))
        themes = _split_multi_value(record.get("mentioned_themes"))
        case_types = _split_multi_value(record.get("mentioned_case_types"))
        for index, stock in enumerate(stocks):
            explicit_ts = ts_codes[index] if index < len(ts_codes) else ""
            ts_code = explicit_ts or asset_map.get(_normalize_stock_name(stock))
            base_row = {
                "stock_name": stock,
                "ts_code": ts_code or "",
                "case_year": _year_of(record.get("source_date")) or _year_of(start_date),
                "theme": themes[0] if themes else "",
                "case_type": case_types[0] if case_types else "unknown",
                "source_title": str(record.get("source_title") or ""),
                "source_url": str(record.get("source_url") or ""),
                "source_date": str(record.get("source_date") or ""),
                "source_type": str(record.get("source_type") or "other"),
                "source_confidence": _article_source_confidence(record),
                "approximate_start_date": str(record.get("approximate_start_date") or start_date),
                "approximate_end_date": str(record.get("approximate_end_date") or end_date),
                "source_note": str(record.get("notes") or ""),
                "article_id": str(record.get("article_id") or ""),
            }
            if ts_code:
                rows.append(base_row)
            else:
                unmatched_rows.append(
                    {
                        **base_row,
                        "normalized_stock_name": _normalize_stock_name(stock),
                        "possible_matches": _possible_matches(stock, lookup_frame),
                        "unmatched_reason": "no_exact_or_normalized_match",
                    }
                )
    web_seed = pd.DataFrame(rows).drop_duplicates(
        subset=["stock_name", "source_title", "source_url", "case_type"],
        keep="first",
    ).reindex(
        columns=[
            "stock_name",
            "ts_code",
            "case_year",
            "theme",
            "case_type",
            "source_title",
            "source_url",
            "source_date",
            "source_type",
            "source_confidence",
            "approximate_start_date",
            "approximate_end_date",
            "source_note",
            "article_id",
        ]
    )
    unmatched = pd.DataFrame(unmatched_rows).drop_duplicates(
        subset=["stock_name", "source_title", "source_url", "case_type"],
        keep="first",
    ).reindex(columns=WEB_UNMATCHED_COLUMNS)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    web_seed.to_csv(output_file, index=False)
    summary_path = out / "dragon_case_web_seed_expand_summary.csv"
    unmatched_path = out / "dragon_case_web_seed_unmatched.csv"
    coverage_path = out / "dragon_case_web_seed_coverage_2024_2026.csv"
    coverage = _build_web_seed_coverage(article, web_seed, unmatched)
    coverage.to_csv(coverage_path, index=False)
    pd.DataFrame(
        [
            {
                "article_count": int(len(article)),
                "stock_seed_count": int(len(web_seed)),
                "matched_stock_count": int(len(web_seed[web_seed["ts_code"].astype(str) != ""])),
                "unmatched_stock_count": int(len(unmatched)),
            }
        ]
    ).to_csv(summary_path, index=False)
    unmatched.to_csv(unmatched_path, index=False)
    report_path = out / "dragon_case_web_seed_expansion_report.md"
    report_path.write_text(
        _web_seed_expansion_report(article, web_seed, unmatched, coverage),
        encoding="utf-8",
    )
    return {
        "paths": {
            "web_seed": str(output_file),
            "summary": str(summary_path),
            "unmatched": str(unmatched_path),
            "coverage": str(coverage_path),
            "report": str(report_path),
        },
        "web_seed": web_seed,
        "unmatched": unmatched,
        "coverage": coverage,
    }


def import_web_seeds(input_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    seed = read_web_case_seed(input_path).fillna("")
    rows = []
    for index, record in enumerate(seed.to_dict("records"), start=1):
        rows.append(
            {
                "web_candidate_id": f"web_{index:04d}",
                "stock_name": str(record.get("stock_name") or ""),
                "ts_code": str(record.get("ts_code") or ""),
                "case_year": record.get("case_year") or _year_of(record.get("approximate_start_date")),
                "theme": str(record.get("theme") or ""),
                "claimed_case_type": str(record.get("case_type") or ""),
                "source_title": str(record.get("source_title") or ""),
                "source_url": str(record.get("source_url") or ""),
                "source_date": str(record.get("source_date") or ""),
                "source_type": str(record.get("source_type") or "other"),
                "source_confidence": _source_confidence(str(record.get("source_type") or "")),
                "approximate_start_date": str(record.get("approximate_start_date") or ""),
                "approximate_end_date": str(record.get("approximate_end_date") or ""),
                "imported_at": pd.Timestamp.now("UTC").isoformat(),
            }
        )
    candidates = pd.DataFrame(rows).reindex(columns=WEB_CANDIDATE_COLUMNS)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "dragon_case_web_candidates_2024_2026.csv"
    candidates.to_csv(path, index=False)
    return {"paths": {"web_candidates": str(path)}, "web_candidates": candidates}


def load_case_library_bars(
    *,
    start_date: object,
    end_date: object,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
        SELECT b.asset_id, m.ts_code, COALESCE(m.name, b.asset_id) AS stock_name,
               b.trade_date, b.open, b.high, b.low, b.close, b.amount,
               b.turnover_rate, b.is_st, b.trade_status
        FROM market_daily_bar b
        LEFT JOIN core.asset_master m ON m.asset_id = b.asset_id
        WHERE b.trade_date >= %s::date - interval '120 days'
          AND b.trade_date <= %s::date + interval '30 days'
          AND b.adjust_type = %s
        ORDER BY b.asset_id, b.trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [str(start_date), str(end_date), adjust_type])
    return pd.DataFrame(rows)


def identify_limit_up_events(
    bars: pd.DataFrame,
    *,
    include_daily_flags: bool = False,
) -> pd.DataFrame:
    frame = _normalize_bars(bars)
    if frame.empty:
        return frame
    frame["prev_close"] = frame.groupby("asset_id")["close"].shift(1)
    frame["daily_return"] = frame["close"] / frame["prev_close"] - 1.0
    frame["limit_up_day"] = _is_limit_up(frame)
    frame["amplitude"] = frame["high"] / frame["low"] - 1.0
    frame["amount_vs_5d"] = frame.groupby("asset_id")["amount"].transform(
        lambda s: s / s.rolling(5, min_periods=1).mean().replace(0, pd.NA)
    )
    frame["limit_up_streak"] = frame.groupby("asset_id")["limit_up_day"].transform(_streak_lengths)
    if include_daily_flags:
        return frame

    rows: list[dict[str, Any]] = []
    for asset_id, group in frame.groupby("asset_id", sort=False):
        limit_days = group[group["limit_up_day"]]
        streak_end_idx = group["limit_up_streak"].idxmax() if not group.empty else None
        streak_end_date = _safe_date(group.loc[streak_end_idx, "trade_date"]) if streak_end_idx is not None else None
        streak_count = int(group["limit_up_streak"].max()) if not group.empty else 0
        streak_start_date = None
        if streak_count > 0 and streak_end_idx is not None:
            end_pos = group.index.get_loc(streak_end_idx)
            start_pos = max(0, end_pos - streak_count + 1)
            streak_start_date = _safe_date(group.iloc[start_pos]["trade_date"])
        rows.append(
            {
                "asset_id": asset_id,
                "ts_code": str(group["ts_code"].iloc[0]),
                "stock_name": str(group["stock_name"].iloc[0]),
                "first_limit_up_date": _safe_date(limit_days["trade_date"].iloc[0]) if not limit_days.empty else None,
                "streak_start_date": streak_start_date,
                "streak_end_date": streak_end_date,
                "max_limit_up_count": streak_count,
                "peak_date": _safe_date(group.loc[group["close"].idxmax(), "trade_date"]) if not group.empty else None,
                "stage_return": _stage_return(group, streak_start_date),
                "max_drawdown": _max_drawdown(group),
            }
        )
    return pd.DataFrame(rows)


def identify_break_limit_day(asset_bars: pd.DataFrame, streak_end_date: str | None) -> str | None:
    if asset_bars.empty or not streak_end_date:
        return None
    frame = _normalize_bars(asset_bars)
    after = frame[frame["trade_date"] > streak_end_date]
    if after.empty:
        return None
    for _, row in after.iterrows():
        if not bool(row.get("limit_up_day", False)):
            return _safe_date(row["trade_date"])
    return None


def identify_reversal_day(asset_bars: pd.DataFrame, break_limit_date: str | None) -> str | None:
    if asset_bars.empty or not break_limit_date:
        return None
    frame = _normalize_bars(asset_bars)
    break_rows = frame[frame["trade_date"] == break_limit_date]
    if break_rows.empty:
        return None
    break_close = _float(break_rows.iloc[0]["close"])
    after = frame[frame["trade_date"] > break_limit_date].head(5)
    for _, row in after.iterrows():
        if bool(row.get("limit_up_day", False)) or _float(row.get("daily_return")) >= 0.07:
            return _safe_date(row["trade_date"])
        if _float(row.get("close")) > break_close * 1.03:
            return _safe_date(row["trade_date"])
    return None


def identify_second_wave_start(asset_bars: pd.DataFrame, break_limit_date: str | None) -> str | None:
    if asset_bars.empty or not break_limit_date:
        return None
    frame = _normalize_bars(asset_bars)
    pre_break = frame[frame["trade_date"] <= break_limit_date]
    after = frame[frame["trade_date"] > break_limit_date]
    if pre_break.empty or after.empty:
        return None
    pre_break_high = pd.to_numeric(pre_break["close"], errors="coerce").max()
    for offset, (_, row) in enumerate(after.iterrows(), start=1):
        if offset < 4:
            continue
        if _float(row["close"]) > pre_break_high * 1.01:
            return _safe_date(row["trade_date"])
    return None


def identify_second_wave_attempt_start(asset_bars: pd.DataFrame | None, break_limit_date: str | None) -> str | None:
    if asset_bars is None or asset_bars.empty or not break_limit_date:
        return None
    frame = _normalize_bars(asset_bars)
    pre_break = frame[frame["trade_date"] <= break_limit_date]
    after = frame[frame["trade_date"] > break_limit_date]
    if pre_break.empty or after.empty:
        return None
    pre_break_high = pd.to_numeric(pre_break["close"], errors="coerce").max()
    for offset, (_, row) in enumerate(after.iterrows(), start=1):
        if offset < 2:
            continue
        if _float(row["close"]) > pre_break_high * 1.01:
            return _safe_date(row["trade_date"])
    return None


def identify_a_kill_failure(asset_bars: pd.DataFrame, break_limit_date: str | None) -> str | None:
    if asset_bars.empty or not break_limit_date:
        return None
    frame = _normalize_bars(asset_bars)
    break_rows = frame[frame["trade_date"] == break_limit_date]
    if break_rows.empty:
        return None
    break_close = _float(break_rows.iloc[0]["close"])
    after = frame[frame["trade_date"] > break_limit_date].head(10)
    for _, row in after.iterrows():
        close = _float(row["close"])
        daily_return = _float(row.get("daily_return"))
        if close <= break_close * 0.90 or daily_return <= -0.09:
            return _safe_date(row["trade_date"])
    return None


def identify_failed_reversal(
    asset_bars: pd.DataFrame | None,
    break_limit_date: str | None,
    reversal_date: str | None,
) -> str | None:
    if asset_bars is None or asset_bars.empty or not break_limit_date or not reversal_date:
        return None
    frame = _normalize_bars(asset_bars)
    reversal_rows = frame[frame["trade_date"] == reversal_date]
    if reversal_rows.empty:
        return None
    reversal_low = _float(reversal_rows.iloc[0]["low"])
    after = frame[frame["trade_date"] > reversal_date].head(3)
    for _, row in after.iterrows():
        if _float(row["close"]) < reversal_low or _float(row.get("daily_return")) <= -0.07:
            return _safe_date(row["trade_date"])
    return None


def identify_failed_second_wave(asset_bars: pd.DataFrame | None, second_wave_start_date: str | None) -> str | None:
    if asset_bars is None or asset_bars.empty or not second_wave_start_date:
        return None
    frame = _normalize_bars(asset_bars)
    second_rows = frame[frame["trade_date"] == second_wave_start_date]
    if second_rows.empty:
        return None
    start_close = _float(second_rows.iloc[0]["close"])
    after = frame[frame["trade_date"] > second_wave_start_date].head(5)
    if after.empty:
        return None
    max_close = pd.to_numeric(after["close"], errors="coerce").max()
    min_close = pd.to_numeric(after["close"], errors="coerce").min()
    if max_close < start_close * 1.03 or min_close < start_close * 0.92:
        return _safe_date(after.iloc[-1]["trade_date"])
    return None


def identify_one_day_pump(
    asset_bars: pd.DataFrame | None,
    first_limit_up_date: str | None,
    max_limit_up_count: int,
) -> str | None:
    if asset_bars is None or asset_bars.empty or not first_limit_up_date:
        return None
    if int(max_limit_up_count) > 1:
        return None
    frame = _normalize_bars(asset_bars)
    first_rows = frame[frame["trade_date"] == first_limit_up_date]
    if first_rows.empty:
        return None
    first_close = _float(first_rows.iloc[0]["close"])
    after = frame[frame["trade_date"] > first_limit_up_date].head(3)
    if after.empty:
        return None
    min_close = pd.to_numeric(after["close"], errors="coerce").min()
    if min_close <= first_close * 0.95:
        return _safe_date(first_limit_up_date)
    return None


def verify_web_candidates(candidates: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    frame = _normalize_bars(bars)
    summaries = identify_limit_up_events(frame)
    summary_by_ts = summaries.set_index("ts_code") if not summaries.empty else pd.DataFrame()
    rows = []
    for record in candidates.fillna("").to_dict("records"):
        ts_code = str(record.get("ts_code") or "").strip()
        asset_bars = frame[frame["ts_code"] == ts_code].copy() if ts_code else pd.DataFrame()
        summary = summary_by_ts.loc[ts_code].to_dict() if ts_code in summary_by_ts.index else {}
        streak_end = summary.get("streak_end_date")
        break_date = identify_break_limit_day(asset_bars, streak_end)
        reversal_date = identify_reversal_day(asset_bars, break_date)
        second_wave = identify_second_wave_start(asset_bars, break_date)
        second_wave_attempt = identify_second_wave_attempt_start(asset_bars, break_date)
        a_kill = identify_a_kill_failure(asset_bars, break_date)
        peak_date = summary.get("peak_date")
        verified_case_type = _verified_case_type(
            asset_bars=asset_bars,
            summary=summary,
            break_limit_date=break_date,
            reversal_date=reversal_date,
            second_wave_start_date=second_wave or second_wave_attempt,
            a_kill_start_date=a_kill,
        )
        score = _verification_score(
            claimed_case_type=str(record.get("claimed_case_type") or ""),
            verified_case_type=verified_case_type,
            summary=summary,
            reversal_date=reversal_date,
            second_wave_start_date=second_wave or second_wave_attempt,
            a_kill_start_date=a_kill,
        )
        rows.append(
            {
                **{column: record.get(column) for column in WEB_CANDIDATE_COLUMNS},
                "claimed_case_type": record.get("claimed_case_type"),
                "verified_case_type": verified_case_type,
                "event_verified": bool(verified_case_type),
                "first_limit_up_date": summary.get("first_limit_up_date"),
                "max_limit_up_count": int(summary.get("max_limit_up_count") or 0),
                "streak_start_date": summary.get("streak_start_date"),
                "streak_end_date": summary.get("streak_end_date"),
                "break_limit_date": break_date,
                "reversal_date": reversal_date,
                "second_wave_start_date": second_wave or second_wave_attempt,
                "peak_date": peak_date,
                "a_kill_start_date": a_kill,
                "stage_return": summary.get("stage_return", 0.0),
                "max_drawdown": summary.get("max_drawdown", 0.0),
                "verification_score": score,
                "verification_reason": _verification_reason(str(record.get("claimed_case_type") or ""), verified_case_type),
            }
        )
    return pd.DataFrame(rows).reindex(columns=WEB_VERIFICATION_COLUMNS)


def build_case_library_from_seed_and_bars(seed: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    frame = _normalize_bars(bars)
    summaries = identify_limit_up_events(frame)
    summary_by_ts = summaries.set_index("ts_code") if not summaries.empty else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(seed.fillna("").to_dict("records"), start=1):
        ts_code = str(record.get("ts_code") or "").strip()
        asset_bars = frame[frame["ts_code"] == ts_code].copy() if ts_code else pd.DataFrame()
        summary = summary_by_ts.loc[ts_code].to_dict() if ts_code in summary_by_ts.index else {}
        streak_end = summary.get("streak_end_date")
        break_date = identify_break_limit_day(asset_bars, streak_end)
        reversal_date = identify_reversal_day(asset_bars, break_date)
        second_wave = identify_second_wave_start(asset_bars, break_date)
        a_kill = identify_a_kill_failure(asset_bars, break_date)
        peak_date = summary.get("peak_date")
        rows.append(
            _case_row(
                case_id=f"seed_{index:04d}",
                record=record,
                summary=summary,
                break_limit_date=break_date,
                reversal_date=reversal_date,
                second_wave_start_date=second_wave,
                peak_date=peak_date,
                a_kill_start_date=a_kill,
                source_type="seed",
            )
        )
    return pd.DataFrame(rows).reindex(columns=CASE_LIBRARY_COLUMNS)


def build_case_library(
    *,
    seed: pd.DataFrame,
    bars: pd.DataFrame,
    output_dir: str | Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    case_library = build_case_library_from_seed_and_bars(seed, bars)
    auto_candidates = _auto_case_candidates(bars, start_date=start_date, end_date=end_date)
    merged = pd.concat([case_library, auto_candidates], ignore_index=True).drop_duplicates(
        subset=["case_id"], keep="first"
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "case_library": str(out / CASE_OUTPUT_FILENAMES["case_library"]),
        "auto_candidates": str(out / CASE_OUTPUT_FILENAMES["auto_candidates"]),
    }
    merged.to_csv(paths["case_library"], index=False)
    auto_candidates.to_csv(paths["auto_candidates"], index=False)
    return {"paths": paths, "case_library": merged, "auto_candidates": auto_candidates}


def diagnose_case_library(
    *,
    case_path: str | Path,
    bars: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    optional_diagnostic_paths: dict[str, str | Path] | None = None,
) -> dict[str, Any]:
    cases = pd.read_csv(case_path, low_memory=False)
    frame = _normalize_bars(bars)
    diagnostics_map, warnings = _load_optional_diagnostics(optional_diagnostic_paths)
    event_diagnostics = _build_case_event_diagnostics(cases, frame, diagnostics_map)
    comparison = _build_success_failure_comparison(cases, event_diagnostics)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "event_diagnostics": str(out / CASE_OUTPUT_FILENAMES["event_diagnostics"]),
        "success_failure_comparison": str(out / CASE_OUTPUT_FILENAMES["success_failure_comparison"]),
        "markdown_report": str(out / CASE_OUTPUT_FILENAMES["markdown_report"]),
    }
    event_diagnostics.to_csv(paths["event_diagnostics"], index=False)
    comparison.to_csv(paths["success_failure_comparison"], index=False)
    Path(paths["markdown_report"]).write_text(
        _case_library_report(
            start_date=start_date,
            end_date=end_date,
            cases=cases,
            comparison=comparison,
            event_diagnostics=event_diagnostics,
            warnings=warnings,
        ),
        encoding="utf-8",
    )
    return {
        "paths": paths,
        "event_diagnostics": event_diagnostics,
        "success_failure_comparison": comparison,
        "warnings": warnings,
    }


def run_dragon_case_library_build(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    seed_path: str | Path = DEFAULT_SEED_PATH,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    seed = read_case_seed(seed_path)
    windows = _date_windows(start_date, end_date, months=12)
    auto_frames = []
    for window_start, window_end in windows:
        bars = load_case_library_bars(
            start_date=window_start,
            end_date=window_end,
            adjust_type=adjust_type,
        )
        auto_frames.append(
            _auto_case_candidates(
                bars,
                start_date=window_start,
                end_date=window_end,
            )
        )
    seed_bars = pd.DataFrame()
    if not seed.empty:
        seed_start = seed.get("approximate_start_date", pd.Series(dtype="object")).replace("", pd.NA).dropna()
        seed_end = seed.get("approximate_end_date", pd.Series(dtype="object")).replace("", pd.NA).dropna()
        bars = load_case_library_bars(
            start_date=str(seed_start.min()) if not seed_start.empty else start_date,
            end_date=str(seed_end.max()) if not seed_end.empty else end_date,
            adjust_type=adjust_type,
        )
        seed_bars = bars
    case_library = build_case_library_from_seed_and_bars(seed, seed_bars)
    auto_candidates = (
        pd.concat(auto_frames, ignore_index=True)
        .drop_duplicates(subset=["ts_code", "first_limit_up_date", "case_type"], keep="first")
        .reindex(columns=CASE_LIBRARY_COLUMNS)
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "case_library": str(out / CASE_OUTPUT_FILENAMES["case_library"]),
        "auto_candidates": str(out / CASE_OUTPUT_FILENAMES["auto_candidates"]),
    }
    merged = pd.concat([case_library, auto_candidates], ignore_index=True)
    merged.to_csv(paths["case_library"], index=False)
    auto_candidates.to_csv(paths["auto_candidates"], index=False)
    return {"paths": paths, "case_library": merged, "auto_candidates": auto_candidates}


def run_dragon_case_library_diagnose(
    *,
    case_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    cases = pd.read_csv(case_path, low_memory=False)
    ts_codes = sorted({str(value) for value in cases.get("ts_code", pd.Series(dtype="object")).dropna().astype(str) if value})
    bars = load_case_library_bars_for_ts_codes(
        start_date=start_date,
        end_date=end_date,
        ts_codes=ts_codes,
        adjust_type=adjust_type,
    )
    optional = {
        "dragon_v1_2": ROOT / "outputs" / "research" / "dragon_strategy_v1_2_diagnostics.csv",
        "dragon_v1_3": ROOT / "outputs" / "research" / "dragon_strategy_v1_3_diagnostics.csv",
        "industry_focus_v2": ROOT / "outputs" / "research" / "industry_focus_score_v2_diagnostics.csv",
        "industry_mainline_regime": ROOT / "outputs" / "research" / "industry_mainline_regime_diagnostics.csv",
        "market_regime": ROOT / "outputs" / "research" / "market_regime_diagnostics.csv",
    }
    return diagnose_case_library(
        case_path=case_path,
        bars=bars,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        optional_diagnostic_paths=optional,
    )


def run_dragon_case_web_verify(
    *,
    candidate_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    candidates = pd.read_csv(candidate_path, low_memory=False)
    candidate_dir = Path(candidate_path).resolve().parent
    ts_codes = sorted({str(value) for value in candidates.get("ts_code", pd.Series(dtype="object")).dropna().astype(str) if value})
    bars = load_case_library_bars_for_ts_codes(
        start_date=start_date,
        end_date=end_date,
        ts_codes=ts_codes,
        adjust_type=adjust_type,
    )
    diagnostics_map, warnings = _load_optional_diagnostics(
        {
            "dragon_v1_2": ROOT / "outputs" / "research" / "dragon_strategy_v1_2_diagnostics.csv",
            "dragon_v1_3": ROOT / "outputs" / "research" / "dragon_strategy_v1_3_diagnostics.csv",
            "industry_focus_v2": ROOT / "outputs" / "research" / "industry_focus_score_v2_diagnostics.csv",
            "market_regime": ROOT / "outputs" / "research" / "market_regime_diagnostics.csv",
        }
    )
    verified = verify_web_candidates(candidates, bars)
    factor_review = build_web_case_factor_review(verified, bars, diagnostics_map)
    local_auto_path = candidate_dir / "dragon_case_auto_candidates.csv"
    local_auto_candidates = pd.read_csv(local_auto_path, low_memory=False) if local_auto_path.exists() else pd.DataFrame()
    base_web_search_targets = build_web_search_targets(local_auto_candidates)
    local_curated_candidates = pd.DataFrame()
    if not local_auto_candidates.empty and not base_web_search_targets.empty:
        local_curated_candidates = local_auto_candidates.copy()
        local_curated_candidates["ts_code"] = local_curated_candidates.get("ts_code", "").map(_normalize_ts_code)
        local_curated_candidates["case_year"] = pd.to_numeric(local_curated_candidates.get("case_year"), errors="coerce")
        local_curated_candidates["case_type"] = local_curated_candidates.get("case_type", "").fillna("").astype(str)
        target_keys = {
            (_normalize_ts_code(row.ts_code), int(row.case_year), str(row.suggested_case_type))
            for row in base_web_search_targets.itertuples()
        }
        local_curated_candidates = local_curated_candidates[
            local_curated_candidates.apply(
                lambda row: (
                    _normalize_ts_code(row.get("ts_code")),
                    int(pd.to_numeric(row.get("case_year"), errors="coerce") or 0),
                    str(row.get("case_type") or ""),
                )
                in target_keys,
                axis=1,
            )
        ].copy()
    curated = build_web_case_curated_library(verified, factor_review, local_auto_candidates=local_curated_candidates)
    evidence = build_web_case_source_evidence(verified)
    comparison = _build_web_success_failure_comparison(curated, factor_review)
    alignment_audit = build_factor_alignment_audit(verified, factor_review, diagnostics_map)
    a_kill_rule_audit = build_a_kill_rule_audit(verified, bars)
    matching_summary = build_matching_summary(candidates, verified, alignment_audit)
    factor_snapshot = build_case_factor_snapshot(curated, bars)
    failure_target_audit = build_failure_target_audit(curated, factor_snapshot)
    local_source_priority = build_local_candidate_source_priority(curated, failure_target_audit)
    article_seed_suggestions = build_article_seed_suggestions(local_source_priority)
    source_backfill_tasks = build_source_backfill_tasks(
        article_seed_suggestions,
        failure_target_audit=failure_target_audit,
        curated=curated,
    )
    web_search_targets = build_web_search_targets(
        local_auto_candidates,
        factor_snapshot=factor_snapshot,
        curated=curated,
        failure_target_audit=failure_target_audit,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "event_verification": str(out / "dragon_case_web_event_verification_2024_2026.csv"),
        "factor_review": str(out / "dragon_case_factor_review_2024_2026.csv"),
        "curated_library": str(out / "dragon_case_curated_library_2024_2026.csv"),
        "source_evidence": str(out / "dragon_case_source_evidence_2024_2026.csv"),
        "success_failure_comparison": str(out / "dragon_case_success_failure_comparison_2024_2026.csv"),
        "factor_alignment_audit": str(out / "dragon_case_factor_alignment_audit_2024_2026.csv"),
        "matching_summary": str(out / "dragon_case_matching_summary_2024_2026.csv"),
        "factor_snapshot": str(out / "dragon_case_factor_snapshot_2024_2026.csv"),
        "web_search_targets": str(out / "dragon_case_web_search_targets_2024_2026.csv"),
        "failure_target_audit": str(out / "dragon_case_failure_target_audit_2024_2026.csv"),
        "local_source_priority": str(out / "dragon_case_local_candidate_source_priority_2024_2026.csv"),
        "article_seed_suggestions": str(out / "dragon_case_article_seed_suggestions_2024_2026.csv"),
        "source_backfill_tasks": str(out / "dragon_case_source_backfill_tasks_2024_2026.csv"),
        "source_backfill_report": str(out / "dragon_case_source_backfill_report.md"),
        "a_kill_rule_audit": str(out / "dragon_case_a_kill_rule_audit_2024_2026.csv"),
        "markdown_report": str(out / "dragon_case_web_verified_2024_2026_report.md"),
    }
    verified.to_csv(paths["event_verification"], index=False)
    factor_review.to_csv(paths["factor_review"], index=False)
    curated.to_csv(paths["curated_library"], index=False)
    evidence.to_csv(paths["source_evidence"], index=False)
    comparison.to_csv(paths["success_failure_comparison"], index=False)
    alignment_audit.to_csv(paths["factor_alignment_audit"], index=False)
    matching_summary.to_csv(paths["matching_summary"], index=False)
    factor_snapshot.to_csv(paths["factor_snapshot"], index=False)
    web_search_targets.to_csv(paths["web_search_targets"], index=False)
    failure_target_audit.to_csv(paths["failure_target_audit"], index=False)
    local_source_priority.to_csv(paths["local_source_priority"], index=False)
    article_seed_suggestions.to_csv(paths["article_seed_suggestions"], index=False)
    source_backfill_tasks.to_csv(paths["source_backfill_tasks"], index=False)
    a_kill_rule_audit.to_csv(paths["a_kill_rule_audit"], index=False)
    Path(paths["source_backfill_report"]).write_text(
        build_source_backfill_report(source_backfill_tasks),
        encoding="utf-8",
    )
    Path(paths["markdown_report"]).write_text(
        _web_case_report(
            verified=verified,
            curated=curated,
            factor_review=factor_review,
            comparison=comparison,
            alignment_audit=alignment_audit,
            matching_summary=matching_summary,
            factor_snapshot=factor_snapshot,
            web_search_targets=web_search_targets,
            failure_target_audit=failure_target_audit,
            local_source_priority=local_source_priority,
            article_seed_suggestions=article_seed_suggestions,
            source_backfill_tasks=source_backfill_tasks,
            a_kill_rule_audit=a_kill_rule_audit,
            warnings=warnings,
        ),
        encoding="utf-8",
    )
    return {
        "paths": paths,
        "web_candidates": candidates,
        "verified": verified,
        "factor_review": factor_review,
        "curated": curated,
        "evidence": evidence,
        "comparison": comparison,
        "alignment_audit": alignment_audit,
        "matching_summary": matching_summary,
        "factor_snapshot": factor_snapshot,
        "web_search_targets": web_search_targets,
        "failure_target_audit": failure_target_audit,
        "local_source_priority": local_source_priority,
        "article_seed_suggestions": article_seed_suggestions,
        "source_backfill_tasks": source_backfill_tasks,
        "a_kill_rule_audit": a_kill_rule_audit,
        "warnings": warnings,
    }


def run_dragon_case_expand_web_seeds(
    *,
    article_seed_path: str | Path,
    output_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    article_seed = read_web_article_seed(article_seed_path)
    return expand_web_article_seeds(
        article_seed=article_seed,
        output_path=output_path,
        output_dir=output_dir,
        start_date=start_date,
        end_date=end_date,
    )


def load_case_library_bars_for_ts_codes(
    *,
    start_date: object,
    end_date: object,
    ts_codes: list[str],
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not ts_codes:
        return pd.DataFrame()
    asset_ids = [_ts_code_to_asset_id(code) for code in ts_codes if code]
    rows: list[dict[str, Any]] = []
    for chunk in _chunked(asset_ids, 400):
        placeholders = ",".join(["%s"] * len(chunk))
        sql = f"""
            SELECT b.asset_id, m.ts_code, COALESCE(m.name, b.asset_id) AS stock_name,
                   b.trade_date, b.open, b.high, b.low, b.close, b.amount,
                   b.turnover_rate, b.is_st, b.trade_status
            FROM market_daily_bar b
            LEFT JOIN core.asset_master m ON m.asset_id = b.asset_id
            WHERE b.trade_date >= %s::date - interval '30 days'
              AND b.trade_date <= %s::date + interval '30 days'
              AND b.adjust_type = %s
              AND b.asset_id IN ({placeholders})
            ORDER BY b.asset_id, b.trade_date
        """
        params: list[object] = [str(start_date), str(end_date), adjust_type, *chunk]
        with connect(service) as conn:
            rows.extend(fetch_all(conn, sql, params))
    return pd.DataFrame(rows)


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.copy()
    if frame.empty:
        return frame
    rename_map = {"asset_id": "asset_id", "ts_code": "ts_code"}
    frame = frame.rename(columns=rename_map)
    for column in ["asset_id", "ts_code", "stock_name", "trade_status"]:
        if column not in frame.columns:
            frame[column] = ""
        frame[column] = frame[column].fillna("").astype(str)
    frame["asset_id"] = frame["asset_id"].map(_normalize_ts_code)
    frame["ts_code"] = frame["ts_code"].replace({"None": "", "nan": "", "NaN": ""})
    frame["ts_code"] = frame.apply(
        lambda row: _normalize_ts_code(row["ts_code"]) if row["ts_code"] else _asset_id_to_ts_code(row["asset_id"]),
        axis=1,
    )
    frame["stock_name"] = frame.apply(
        lambda row: row["stock_name"] if row["stock_name"] not in {"", "None", "nan"} else row["ts_code"].split(".")[0],
        axis=1,
    )
    if "is_st" not in frame.columns:
        frame["is_st"] = False
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.strftime("%Y-%m-%d")
    for column in ["open", "high", "low", "close", "amount", "turnover_rate"]:
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def _is_limit_up(frame: pd.DataFrame) -> pd.Series:
    threshold = frame["is_st"].map(lambda value: 0.048 if bool(value) else 0.095)
    returns = pd.to_numeric(frame["daily_return"], errors="coerce").fillna(0.0)
    return returns >= threshold


def _streak_lengths(series: pd.Series) -> pd.Series:
    values = series.fillna(False).astype(bool)
    lengths = []
    count = 0
    for value in values:
        count = count + 1 if value else 0
        lengths.append(count)
    return pd.Series(lengths, index=series.index)


def _stage_return(group: pd.DataFrame, streak_start_date: str | None) -> float:
    if group.empty or not streak_start_date:
        return 0.0
    start_rows = group[group["trade_date"] == streak_start_date]
    if start_rows.empty:
        return 0.0
    start_close = _float(start_rows.iloc[0]["close"])
    if start_close == 0:
        return 0.0
    return _float(group["close"].max()) / start_close - 1.0


def _max_drawdown(group: pd.DataFrame) -> float:
    closes = pd.to_numeric(group["close"], errors="coerce").dropna()
    if closes.empty:
        return 0.0
    running_max = closes.cummax()
    drawdown = closes / running_max - 1.0
    return float(drawdown.min())


def _case_row(
    *,
    case_id: str,
    record: dict[str, Any],
    summary: dict[str, Any],
    break_limit_date: str | None,
    reversal_date: str | None,
    second_wave_start_date: str | None,
    peak_date: str | None,
    a_kill_start_date: str | None,
    source_type: str,
) -> dict[str, Any]:
    case_type = str(record.get("case_type") or "unknown")
    success = "failure" if "failed" in case_type or "a_kill" in case_type or "pump" in case_type else "success"
    break_to_reversal = _business_day_distance(break_limit_date, reversal_date)
    break_to_second_wave = _business_day_distance(break_limit_date, second_wave_start_date)
    return {
        "case_id": case_id,
        "stock_code": str(record.get("ts_code") or "").split(".")[0],
        "ts_code": str(record.get("ts_code") or ""),
        "stock_name": str(record.get("stock_name") or summary.get("stock_name") or ""),
        "case_year": record.get("case_year") or _year_of(record.get("approximate_start_date")),
        "theme": str(record.get("theme") or ""),
        "industry_name": str(record.get("industry_name") or ""),
        "case_type": case_type,
        "role": str(record.get("role") or "unknown"),
        "success_or_failure": str(record.get("success_or_failure") or success),
        "market_cycle": str(record.get("market_cycle") or "unknown"),
        "start_date": str(record.get("approximate_start_date") or ""),
        "first_limit_up_date": summary.get("first_limit_up_date"),
        "streak_start_date": summary.get("streak_start_date"),
        "streak_end_date": summary.get("streak_end_date"),
        "max_limit_up_count": int(summary.get("max_limit_up_count") or 0),
        "break_limit_date": break_limit_date,
        "reversal_date": reversal_date,
        "second_wave_start_date": second_wave_start_date,
        "second_wave_end_date": peak_date if second_wave_start_date else None,
        "peak_date": peak_date,
        "cooling_down_date": a_kill_start_date or break_limit_date,
        "a_kill_start_date": a_kill_start_date,
        "source_title": str(record.get("source_title") or ""),
        "source_url": str(record.get("source_url") or ""),
        "source_type": source_type,
        "manual_confidence": record.get("manual_confidence") or 0.7,
        "notes": str(record.get("notes") or ""),
        "stage_return": summary.get("stage_return", 0.0),
        "max_drawdown": summary.get("max_drawdown", 0.0),
        "break_to_reversal_days": break_to_reversal,
        "break_to_second_wave_days": break_to_second_wave,
    }


def _auto_case_candidates(bars: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    frame = identify_limit_up_events(bars)
    if frame.empty:
        return pd.DataFrame(columns=CASE_LIBRARY_COLUMNS)
    rows = []
    for index, record in enumerate(frame.to_dict("records"), start=1):
        if int(record.get("max_limit_up_count") or 0) < 2 and _float(record.get("stage_return")) < 0.30:
            continue
        case_type = "continuous_limit_up" if int(record.get("max_limit_up_count") or 0) >= 2 else "weak_to_strong"
        rows.append(
            {
                "case_id": f"auto_{index:04d}",
                "stock_code": str(record.get("ts_code", "")).split(".")[0],
                "ts_code": str(record.get("ts_code") or ""),
                "stock_name": str(record.get("stock_name") or ""),
                "case_year": _year_of(record.get("first_limit_up_date")),
                "theme": "",
                "industry_name": "",
                "case_type": case_type,
                "role": "unknown",
                "success_or_failure": "unknown",
                "market_cycle": "unknown",
                "start_date": start_date,
                "first_limit_up_date": record.get("first_limit_up_date"),
                "streak_start_date": record.get("streak_start_date"),
                "streak_end_date": record.get("streak_end_date"),
                "max_limit_up_count": int(record.get("max_limit_up_count") or 0),
                "break_limit_date": None,
                "reversal_date": None,
                "second_wave_start_date": None,
                "second_wave_end_date": None,
                "peak_date": record.get("peak_date"),
                "cooling_down_date": None,
                "a_kill_start_date": None,
                "source_title": "auto_candidate",
                "source_url": "",
                "source_type": "auto",
                "manual_confidence": 0.3,
                "notes": f"auto candidate from {start_date} to {end_date}",
                "stage_return": record.get("stage_return", 0.0),
                "max_drawdown": record.get("max_drawdown", 0.0),
                "break_to_reversal_days": None,
                "break_to_second_wave_days": None,
            }
        )
    return pd.DataFrame(rows).reindex(columns=CASE_LIBRARY_COLUMNS)


def _load_optional_diagnostics(
    optional_diagnostic_paths: dict[str, str | Path] | None,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    diagnostics: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    for name, path in (optional_diagnostic_paths or {}).items():
        file_path = Path(path)
        if not file_path.exists():
            warnings.append(f"missing optional diagnostics: {name} -> {file_path}")
            continue
        diagnostics[name] = pd.read_csv(
            file_path,
            usecols=lambda column: column in _optional_usecols(name),
            low_memory=False,
        )
    return diagnostics, warnings


def _build_case_event_diagnostics(
    cases: pd.DataFrame,
    bars: pd.DataFrame,
    diagnostics_map: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    by_ts = {ts: group.copy() for ts, group in bars.groupby("ts_code", sort=False)}
    for case in cases.fillna("").to_dict("records"):
        ts_code = str(case.get("ts_code") or "")
        asset_bars = by_ts.get(ts_code)
        if asset_bars is None or asset_bars.empty:
            continue
        for event_type, event_field in [
            ("first_limit_up", "first_limit_up_date"),
            ("streak_start", "streak_start_date"),
            ("streak_end", "streak_end_date"),
            ("break_limit", "break_limit_date"),
            ("reversal", "reversal_date"),
            ("second_wave_start", "second_wave_start_date"),
            ("peak", "peak_date"),
            ("cooling_down", "cooling_down_date"),
            ("a_kill_start", "a_kill_start_date"),
        ]:
            event_date = str(case.get(event_field) or "").strip()
            if not event_date:
                continue
            rows.extend(
                _event_window_rows(
                    case=case,
                    asset_bars=asset_bars,
                    event_type=event_type,
                    event_date=event_date,
                )
            )
    event_frame = pd.DataFrame(rows)
    return _merge_optional_diagnostics_frame(event_frame, diagnostics_map)


def _event_window_rows(
    *,
    case: dict[str, Any],
    asset_bars: pd.DataFrame,
    event_type: str,
    event_date: str,
) -> list[dict[str, Any]]:
    ordered = asset_bars.sort_values("trade_date").reset_index(drop=True)
    matches = ordered.index[ordered["trade_date"] == event_date]
    if len(matches) == 0:
        return []
    event_idx = int(matches[0])
    rows: list[dict[str, Any]] = []
    for relative_day in range(-5, 11):
        idx = event_idx + relative_day
        if idx < 0 or idx >= len(ordered):
            continue
        current = ordered.iloc[idx]
        row = {
            "case_id": case.get("case_id"),
            "asset_id": current["asset_id"],
            "ts_code": case.get("ts_code"),
            "stock_name": case.get("stock_name"),
            "theme": case.get("theme"),
            "case_type": case.get("case_type"),
            "role": case.get("role"),
            "success_or_failure": case.get("success_or_failure"),
            "event_type": event_type,
            "event_date": event_date,
            "relative_day": relative_day,
            "trade_date": current["trade_date"],
            "close": _float(current["close"]),
            "daily_return": _daily_return_at(ordered, idx),
            "amount": _float(current["amount"]),
            "turnover_rate": _float(current.get("turnover_rate")),
            "industry_name": case.get("industry_name") or "",
            "industry_focus_score_v2": None,
            "industry_rank": None,
            "market_regime": None,
            "dragon_status_score": None,
            "dragon_entry_score": None,
            "dragon_risk_score": None,
            "entry_window": None,
            "entry_window_v2": None,
            "dragon_role": None,
        }
        row.update(_future_window_metrics(ordered, idx))
        rows.append(row)
    return rows


def _merge_optional_diagnostics_frame(
    event_frame: pd.DataFrame,
    diagnostics_map: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    if event_frame.empty:
        return event_frame
    result = event_frame.copy()
    if "ts_code" in result.columns:
        result["ts_code"] = result["ts_code"].map(_normalize_ts_code)
    if "asset_id" in result.columns:
        result["asset_id"] = result["asset_id"].map(_normalize_ts_code)
    event_dates = set(result["trade_date"].astype(str))
    for frame in diagnostics_map.values():
        data = frame.copy()
        if "trade_date" not in data.columns:
            continue
        data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.strftime("%Y-%m-%d")
        data = data[data["trade_date"].isin(event_dates)].copy()
        if data.empty:
            continue
        merge_cols: list[str]
        if "asset_id" in data.columns:
            data["asset_id"] = data["asset_id"].map(_normalize_ts_code)
            merge_cols = ["trade_date", "asset_id"]
        elif "ts_code" in data.columns:
            data["ts_code"] = data["ts_code"].map(_normalize_ts_code)
            merge_cols = ["trade_date", "ts_code"]
        else:
            merge_cols = ["trade_date"]
        keep_cols = [
            *merge_cols,
            *[
                column
                for column in [
                    "industry_name",
                    "industry_focus_score_v2",
                    "industry_rank",
                    "market_regime",
                    "dragon_status_score",
                    "dragon_entry_score",
                    "dragon_entry_score_v2",
                    "dragon_risk_score",
                    "entry_window",
                    "entry_window_v2",
                    "dragon_role",
                ]
                if column in data.columns
            ],
        ]
        data = data[keep_cols].drop_duplicates(subset=merge_cols, keep="last")
        result = result.merge(data, on=merge_cols, how="left", suffixes=("", "_opt"))
        for column in [
            "industry_name",
            "industry_focus_score_v2",
            "industry_rank",
            "market_regime",
            "dragon_status_score",
            "dragon_risk_score",
            "entry_window",
            "entry_window_v2",
            "dragon_role",
        ]:
            opt = f"{column}_opt"
            if opt in result.columns:
                result[column] = result[column].fillna(result[opt])
                result = result.drop(columns=[opt])
        if "dragon_entry_score_opt" in result.columns:
            result["dragon_entry_score"] = result["dragon_entry_score"].fillna(result["dragon_entry_score_opt"])
            result = result.drop(columns=["dragon_entry_score_opt"])
        if "dragon_entry_score_v2_opt" in result.columns:
            result["dragon_entry_score"] = result["dragon_entry_score"].fillna(result["dragon_entry_score_v2_opt"])
            result = result.drop(columns=["dragon_entry_score_v2_opt"])
    return result


def _future_window_metrics(ordered: pd.DataFrame, idx: int) -> dict[str, float | None]:
    close = _float(ordered.iloc[idx]["close"])
    if close == 0:
        return {
            "future_1d_return": None,
            "future_3d_return": None,
            "future_5d_return": None,
            "future_10d_return": None,
            "future_5d_max_drawdown": None,
            "future_10d_max_drawdown": None,
        }
    metrics: dict[str, float | None] = {}
    closes = pd.to_numeric(ordered["close"], errors="coerce").tolist()
    for horizon in [1, 3, 5, 10]:
        future_idx = idx + horizon
        metrics[f"future_{horizon}d_return"] = closes[future_idx] / close - 1.0 if future_idx < len(closes) else None
    metrics["future_5d_max_drawdown"] = _future_drawdown(closes, idx, 5)
    metrics["future_10d_max_drawdown"] = _future_drawdown(closes, idx, 10)
    return metrics


def _future_drawdown(closes: list[float], start_idx: int, horizon: int) -> float | None:
    start_close = closes[start_idx]
    window = closes[start_idx + 1 : start_idx + horizon + 1]
    if not window or not start_close:
        return None
    return min(value / start_close - 1.0 for value in window)


def _backward_return(ordered: pd.DataFrame, idx: int, horizon: int) -> float | None:
    if idx - horizon < 0:
        return None
    prev_close = _float(ordered.iloc[idx - horizon]["close"])
    close = _float(ordered.iloc[idx]["close"])
    if not prev_close:
        return None
    return close / prev_close - 1.0


def _rolling_ratio(ordered: pd.DataFrame, idx: int, window: int, column: str) -> float | None:
    current = _float(ordered.iloc[idx].get(column))
    start = max(0, idx - window)
    hist = pd.to_numeric(ordered.iloc[start:idx][column], errors="coerce")
    hist = hist[hist > 0]
    if current <= 0 or hist.empty:
        return None
    return current / hist.mean()


def _close_position_in_day(row: pd.Series) -> float | None:
    high = _float(row.get("high"))
    low = _float(row.get("low"))
    close = _float(row.get("close"))
    span = high - low
    if span <= 0:
        return None
    return (close - low) / span


def _high_to_close_drawdown(row: pd.Series) -> float | None:
    high = _float(row.get("high"))
    close = _float(row.get("close"))
    if high <= 0:
        return None
    return close / high - 1.0


def _rolling_volatility(ordered: pd.DataFrame, idx: int, window: int) -> float | None:
    start = max(0, idx - window + 1)
    window_frame = ordered.iloc[start : idx + 1].copy()
    if "daily_return" not in window_frame.columns:
        closes = pd.to_numeric(window_frame["close"], errors="coerce")
        values = closes.pct_change().dropna()
    else:
        values = pd.to_numeric(window_frame["daily_return"], errors="coerce").dropna()
    if len(values) < 2:
        return None
    return float(values.std())


def _limit_up_count_before_event(ordered: pd.DataFrame, idx: int, event_idx: int) -> int:
    upper = min(idx, event_idx)
    if upper < 0:
        return 0
    window = ordered.iloc[: upper + 1]
    if "limit_up_day" not in window.columns:
        return 0
    return int(window["limit_up_day"].fillna(False).astype(bool).sum())


def _build_success_failure_comparison(
    cases: pd.DataFrame,
    event_diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    if cases.empty or event_diagnostics.empty or "relative_day" not in event_diagnostics.columns:
        return pd.DataFrame()
    event_zero = event_diagnostics[event_diagnostics["relative_day"] == 0].copy()
    summary = cases.merge(event_zero, on="case_id", how="left", suffixes=("", "_event"))
    if summary.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in summary.groupby(["case_type", "role", "success_or_failure"], dropna=False):
        rows.append(
            {
                "case_type": keys[0],
                "role": keys[1],
                "success_or_failure": keys[2],
                "sample_count": int(len(group)),
                "avg_max_limit_up_count": pd.to_numeric(group["max_limit_up_count"], errors="coerce").mean(),
                "avg_stage_return": pd.to_numeric(group["stage_return"], errors="coerce").mean(),
                "avg_max_drawdown": pd.to_numeric(group["max_drawdown"], errors="coerce").mean(),
                "avg_break_to_reversal_days": pd.to_numeric(group["break_to_reversal_days"], errors="coerce").mean(),
                "avg_break_to_second_wave_days": pd.to_numeric(group["break_to_second_wave_days"], errors="coerce").mean(),
                "avg_event_dragon_status_score": pd.to_numeric(group.get("dragon_status_score"), errors="coerce").mean(),
                "avg_event_dragon_entry_score": pd.to_numeric(group.get("dragon_entry_score"), errors="coerce").mean(),
                "avg_event_dragon_risk_score": pd.to_numeric(group.get("dragon_risk_score"), errors="coerce").mean(),
                "avg_event_industry_focus_score_v2": pd.to_numeric(group.get("industry_focus_score_v2"), errors="coerce").mean(),
                "avg_event_future_3d_return": pd.to_numeric(group.get("future_3d_return"), errors="coerce").mean(),
                "avg_event_future_5d_return": pd.to_numeric(group.get("future_5d_return"), errors="coerce").mean(),
                "avg_event_future_10d_return": pd.to_numeric(group.get("future_10d_return"), errors="coerce").mean(),
                "avg_event_future_5d_max_drawdown": pd.to_numeric(group.get("future_5d_max_drawdown"), errors="coerce").mean(),
                "avg_event_future_10d_max_drawdown": pd.to_numeric(group.get("future_10d_max_drawdown"), errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows)


def build_web_case_factor_review(
    verified_candidates: pd.DataFrame,
    bars: pd.DataFrame,
    diagnostics_map: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    cases = verified_candidates.rename(
        columns={
            "web_candidate_id": "case_id",
            "verified_case_type": "case_type",
            "claimed_case_type": "notes",
        }
    ).copy()
    cases["role"] = cases.get("role", "unknown")
    cases["success_or_failure"] = cases.apply(
        lambda row: "failure"
        if (
            "failure" in str(row.get("verified_case_type") or "")
            or "failed_" in str(row.get("verified_case_type") or "")
            or "pump" in str(row.get("verified_case_type") or "")
        )
        else "success",
        axis=1,
    )
    event_frame = _build_case_event_diagnostics(cases, _normalize_bars(bars), diagnostics_map)
    if event_frame.empty:
        return pd.DataFrame(columns=WEB_FACTOR_REVIEW_COLUMNS)
    event_frame = event_frame.rename(columns={"case_id": "web_candidate_id"})
    if "dragon_entry_score" not in event_frame.columns:
        event_frame["dragon_entry_score"] = None
    if "dragon_entry_score_v2" not in event_frame.columns:
        event_frame["dragon_entry_score_v2"] = None
    if "future_5d_max_drawdown" not in event_frame.columns:
        event_frame["future_5d_max_drawdown"] = None
    return event_frame.reindex(columns=WEB_FACTOR_REVIEW_COLUMNS)


def build_web_case_curated_library(
    verified_candidates: pd.DataFrame,
    factor_review: pd.DataFrame,
    local_auto_candidates: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if verified_candidates.empty and (local_auto_candidates is None or local_auto_candidates.empty):
        return pd.DataFrame(columns=WEB_CURATED_COLUMNS)
    factor_available = set()
    if not factor_review.empty:
        relevant = factor_review[
            factor_review[["dragon_status_score", "dragon_entry_score", "dragon_risk_score", "industry_focus_score_v2"]]
            .notna()
            .any(axis=1)
        ]
        factor_available = set(relevant["web_candidate_id"].astype(str))
    rows = []
    for record in verified_candidates.fillna("").to_dict("records"):
        confidence = (
            0.35 * _float(record.get("source_confidence"))
            + 0.45 * _float(record.get("verification_score"))
            + 0.20 * (1.0 if str(record.get("web_candidate_id")) in factor_available else 0.0)
        )
        if not bool(record.get("event_verified")):
            continue
        if _float(record.get("source_confidence")) < 0.55 or _float(record.get("verification_score")) < 0.55:
            continue
        rows.append(
            {
                "case_id": f"curated_{str(record.get('web_candidate_id')).split('_')[-1]}",
                "stock_code": str(record.get("ts_code") or "").split(".")[0],
                "ts_code": str(record.get("ts_code") or ""),
                "stock_name": str(record.get("stock_name") or ""),
                "case_year": record.get("case_year"),
                "theme": str(record.get("theme") or ""),
                "industry_name": "",
                "case_type": str(record.get("verified_case_type") or record.get("claimed_case_type") or "unknown"),
                "role": "unknown",
                "success_or_failure": "failure"
                if (
                    "failure" in str(record.get("verified_case_type") or "")
                    or "failed_" in str(record.get("verified_case_type") or "")
                    or "pump" in str(record.get("verified_case_type") or "")
                )
                else "success",
                "source_title": str(record.get("source_title") or ""),
                "source_url": str(record.get("source_url") or ""),
                "source_type": str(record.get("source_type") or ""),
                "source_confidence": _float(record.get("source_confidence")),
                "event_verified": bool(record.get("event_verified")),
                "verified_case_type": str(record.get("verified_case_type") or ""),
                "verification_score": _float(record.get("verification_score")),
                "case_confidence_score": confidence,
                "first_limit_up_date": record.get("first_limit_up_date"),
                "max_limit_up_count": int(record.get("max_limit_up_count") or 0),
                "break_limit_date": record.get("break_limit_date"),
                "reversal_date": record.get("reversal_date"),
                "second_wave_start_date": record.get("second_wave_start_date"),
                "peak_date": record.get("peak_date"),
                "a_kill_start_date": record.get("a_kill_start_date"),
                "stage_return": _float(record.get("stage_return")),
                "max_drawdown": _float(record.get("max_drawdown")),
                "dragon_factor_available": str(record.get("web_candidate_id")) in factor_available,
                "source_origin": "web_seed_verified",
                "web_source_available": True,
                "local_event_verified": bool(record.get("event_verified")),
                "needs_web_source": False,
                "suggested_search_query": f"{record.get('case_year')} {record.get('stock_name')} {record.get('verified_case_type') or record.get('claimed_case_type')} 复盘".strip(),
                "review_status": "pending",
                "reviewer_note": "",
                "notes": str(record.get("claimed_case_type") or ""),
                "web_candidate_id": str(record.get("web_candidate_id") or ""),
            }
        )
    if local_auto_candidates is not None and not local_auto_candidates.empty:
        for record in local_auto_candidates.fillna("").to_dict("records"):
            ts_code = _normalize_ts_code(record.get("ts_code"))
            case_type = str(record.get("case_type") or "unknown")
            rows.append(
                {
                    "case_id": str(record.get("case_id") or f"local_{len(rows)+1:04d}"),
                    "stock_code": ts_code.split(".")[0],
                    "ts_code": ts_code,
                    "stock_name": str(record.get("stock_name") or ""),
                    "case_year": record.get("case_year"),
                    "theme": str(record.get("theme") or ""),
                    "industry_name": str(record.get("industry_name") or ""),
                    "case_type": case_type,
                    "role": str(record.get("role") or "unknown"),
                    "success_or_failure": "failure"
                    if ("failure" in case_type or "failed_" in case_type or "pump" in case_type)
                    else "unknown",
                    "source_title": "",
                    "source_url": "",
                    "source_type": "local_auto",
                    "source_confidence": 0.0,
                    "event_verified": True,
                    "verified_case_type": case_type,
                    "verification_score": max(0.55, _float(record.get("candidate_quality_score")) or 0.60),
                    "case_confidence_score": max(0.45, _float(record.get("candidate_quality_score")) or 0.55),
                    "first_limit_up_date": record.get("first_limit_up_date"),
                    "max_limit_up_count": int(record.get("max_limit_up_count") or 0),
                    "break_limit_date": record.get("break_limit_date"),
                    "reversal_date": record.get("reversal_date"),
                    "second_wave_start_date": record.get("second_wave_start_date"),
                    "peak_date": record.get("peak_date"),
                    "a_kill_start_date": record.get("a_kill_start_date"),
                    "stage_return": _float(record.get("stage_return")),
                    "max_drawdown": _float(record.get("max_drawdown")),
                    "dragon_factor_available": False,
                    "source_origin": "local_auto_candidate",
                    "web_source_available": False,
                    "local_event_verified": True,
                    "needs_web_source": True,
                    "suggested_search_query": f"{record.get('case_year')} {record.get('stock_name')} {case_type} 复盘".strip(),
                    "review_status": "pending",
                    "reviewer_note": "",
                    "notes": "local auto candidate awaiting web source",
                    "web_candidate_id": "",
                }
            )
    return pd.DataFrame(rows).reindex(columns=WEB_CURATED_COLUMNS)


def build_web_case_source_evidence(verified_candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for record in verified_candidates.fillna("").to_dict("records"):
        rows.append(
            {
                "case_id": f"curated_{str(record.get('web_candidate_id')).split('_')[-1]}",
                "web_candidate_id": str(record.get("web_candidate_id") or ""),
                "ts_code": str(record.get("ts_code") or ""),
                "stock_name": str(record.get("stock_name") or ""),
                "source_title": str(record.get("source_title") or ""),
                "source_url": str(record.get("source_url") or ""),
                "source_date": str(record.get("source_date") or ""),
                "source_type": str(record.get("source_type") or ""),
                "extracted_case_type": str(record.get("claimed_case_type") or ""),
                "evidence_score": round(_float(record.get("source_confidence")) * (1.1 if bool(record.get("event_verified")) else 0.7), 4),
                "notes": str(record.get("verification_reason") or ""),
            }
        )
    return pd.DataFrame(rows).reindex(columns=WEB_SOURCE_EVIDENCE_COLUMNS)


def _diagnostics_metadata(name: str, frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "diagnostics_file": name,
            "diagnostics_min_date": None,
            "diagnostics_max_date": None,
            "diagnostics_has_ts_code": False,
            "diagnostics_has_asset_id": False,
            "diagnostics_date_granularity": "unknown",
        }
    data = frame.copy()
    granularity = "unknown"
    if "trade_date" in data.columns:
        trade_dates = pd.to_datetime(data["trade_date"], errors="coerce").dropna()
        if not trade_dates.empty:
            granularity = "daily"
            min_date = trade_dates.min().strftime("%Y-%m-%d")
            max_date = trade_dates.max().strftime("%Y-%m-%d")
        else:
            min_date = None
            max_date = None
    else:
        min_date = None
        max_date = None
    return {
        "diagnostics_file": name,
        "diagnostics_min_date": min_date,
        "diagnostics_max_date": max_date,
        "diagnostics_has_ts_code": "ts_code" in data.columns,
        "diagnostics_has_asset_id": "asset_id" in data.columns,
        "diagnostics_date_granularity": granularity,
    }


def _prepare_diagnostics_for_alignment(name: str, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    data = frame.copy()
    metadata = _diagnostics_metadata(name, data)
    if data.empty or "trade_date" not in data.columns:
        return data, metadata
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "ts_code" in data.columns:
        data["ts_code"] = data["ts_code"].map(_normalize_ts_code)
    if "asset_id" in data.columns:
        data["asset_id"] = data["asset_id"].map(_normalize_ts_code)
    return data, metadata


def _build_diagnostics_lookup(name: str, frame: pd.DataFrame) -> dict[str, Any]:
    data, metadata = _prepare_diagnostics_for_alignment(name, frame)
    if data.empty or "trade_date" not in data.columns:
        return {"name": name, "data": data, "meta": metadata, "has_code": False, "date_set": set(), "code_dates": {}}
    date_set = set(data["trade_date"].dropna().astype(str))
    if "asset_id" in data.columns:
        code_column = "asset_id"
    elif "ts_code" in data.columns:
        code_column = "ts_code"
    else:
        code_column = None
    code_dates: dict[str, list[pd.Timestamp]] = {}
    code_date_strings: dict[str, set[str]] = {}
    if code_column:
        for code, group in data.groupby(code_column, sort=False):
            dates = pd.to_datetime(group["trade_date"], errors="coerce").dropna().sort_values().tolist()
            code_dates[str(code)] = dates
            code_date_strings[str(code)] = {ts.strftime("%Y-%m-%d") for ts in dates}
    return {
        "name": name,
        "data": data,
        "meta": metadata,
        "has_code": bool(code_column),
        "code_column": code_column,
        "date_set": date_set,
        "code_dates": code_dates,
        "code_date_strings": code_date_strings,
    }


def build_matching_summary(
    seed: pd.DataFrame,
    verified: pd.DataFrame,
    alignment_audit: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    total_seed = int(len(seed))
    matched_seed = int(seed.get("ts_code", pd.Series(dtype="object")).fillna("").astype(str).str.strip().ne("").sum())
    rows.append(
        {
            "match_stage": "stock_name_to_ts_code",
            "total_count": total_seed,
            "matched_count": matched_seed,
            "match_rate": matched_seed / total_seed if total_seed else 0.0,
            "main_missing_reason": ""
            if total_seed == matched_seed
            else "stock_name_unmatched_in_asset_lookup",
            "notes": "stock-level web seed 到本地证券主表的匹配。",
        }
    )
    total_verified = int(len(verified))
    matched_verified = int(
        pd.to_numeric(verified.get("event_verified", pd.Series(dtype="object")), errors="coerce")
        .fillna(False)
        .astype(bool)
        .sum()
    )
    rows.append(
        {
            "match_stage": "web_candidate_to_local_event_verification",
            "total_count": total_verified,
            "matched_count": matched_verified,
            "match_rate": matched_verified / total_verified if total_verified else 0.0,
            "main_missing_reason": ""
            if total_verified == matched_verified
            else "no_local_event_pattern_verified",
            "notes": "网络线索到本地行情事件识别的验证。",
        }
    )
    key_alignment = alignment_audit[alignment_audit.get("relative_day", pd.Series(dtype="int64")) == 0].copy()
    total_alignment = int(len(key_alignment))
    if not key_alignment.empty:
        matched_mask = key_alignment[
            ["has_dragon_v1_2", "has_dragon_v1_3", "has_industry_focus", "has_market_regime"]
        ].astype(bool).any(axis=1)
        missing_reason = (
            key_alignment.loc[~matched_mask, "final_missing_reason"]
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .idxmax()
            if (~matched_mask).any()
            else ""
        )
        matched_alignment = int(matched_mask.sum())
    else:
        matched_alignment = 0
        missing_reason = "no_alignment_rows"
    rows.append(
        {
            "match_stage": "case_event_to_diagnostics",
            "total_count": total_alignment,
            "matched_count": matched_alignment,
            "match_rate": matched_alignment / total_alignment if total_alignment else 0.0,
            "main_missing_reason": missing_reason,
            "notes": "案例关键事件日到 Dragon/industry/market diagnostics 的对齐。",
        }
    )
    return pd.DataFrame(rows).reindex(columns=MATCHING_SUMMARY_COLUMNS)


def build_case_factor_snapshot(
    curated: pd.DataFrame,
    bars: pd.DataFrame,
    industry_daily: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if curated.empty:
        return pd.DataFrame(columns=CASE_FACTOR_SNAPSHOT_COLUMNS)
    frame = _normalize_bars(bars)
    by_ts = {ts: group.sort_values("trade_date").reset_index(drop=True) for ts, group in frame.groupby("ts_code", sort=False)}
    industry_map: dict[tuple[str, str], dict[str, Any]] = {}
    if industry_daily is not None and not industry_daily.empty and {"trade_date", "industry_name"}.issubset(industry_daily.columns):
        temp = industry_daily.copy()
        temp["trade_date"] = pd.to_datetime(temp["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        for row in temp.fillna("").to_dict("records"):
            industry_map[(str(row.get("industry_name") or ""), str(row.get("trade_date") or ""))] = row
    rows: list[dict[str, Any]] = []
    for case in curated.fillna("").to_dict("records"):
        ts_code = _normalize_ts_code(case.get("ts_code"))
        asset_bars = by_ts.get(ts_code)
        if asset_bars is None or asset_bars.empty:
            continue
        for event_type, event_field in [
            ("first_limit_up", "first_limit_up_date"),
            ("break_limit", "break_limit_date"),
            ("reversal", "reversal_date"),
            ("second_wave_start", "second_wave_start_date"),
            ("peak", "peak_date"),
            ("a_kill_start", "a_kill_start_date"),
        ]:
            event_date = str(case.get(event_field) or "").strip()
            if not event_date:
                continue
            matches = asset_bars.index[asset_bars["trade_date"] == event_date]
            if len(matches) == 0:
                continue
            event_idx = int(matches[0])
            for relative_day in range(-10, 11):
                idx = event_idx + relative_day
                if idx < 0 or idx >= len(asset_bars):
                    continue
                current = asset_bars.iloc[idx]
                snapshot = {
                    "case_id": case.get("case_id"),
                    "ts_code": ts_code,
                    "stock_name": case.get("stock_name"),
                    "event_type": event_type,
                    "event_date": event_date,
                    "relative_day": relative_day,
                    "trade_date": current["trade_date"],
                    "close": _float(current["close"]),
                    "daily_return": _daily_return_at(asset_bars, idx),
                    "pre_3d_return": _backward_return(asset_bars, idx, 3),
                    "pre_5d_return": _backward_return(asset_bars, idx, 5),
                    "pre_10d_return": _backward_return(asset_bars, idx, 10),
                    "amount_vs_5d": _rolling_ratio(asset_bars, idx, 5, "amount"),
                    "amount_vs_20d": _rolling_ratio(asset_bars, idx, 20, "amount"),
                    "close_position_in_day": _close_position_in_day(current),
                    "high_to_close_drawdown": _high_to_close_drawdown(current),
                    "volatility_5d": _rolling_volatility(asset_bars, idx, 5),
                    "stage_return": _float(case.get("stage_return")),
                    "limit_up_count_before_event": _limit_up_count_before_event(asset_bars, idx, event_idx),
                    "is_limit_up_day": bool(current.get("limit_up_day", False)),
                    "is_break_limit_event": event_type == "break_limit",
                    "is_reversal_event": event_type == "reversal",
                    "is_second_wave_event": event_type == "second_wave_start",
                    "is_a_kill_event": event_type == "a_kill_start",
                    "industry_name": str(case.get("industry_name") or ""),
                    "industry_return_5d": None,
                    "industry_return_10d": None,
                    "stock_excess_vs_industry_5d": None,
                    "stock_excess_vs_industry_10d": None,
                }
                snapshot.update(_future_window_metrics(asset_bars, idx))
                if snapshot["industry_name"]:
                    ind_row = industry_map.get((snapshot["industry_name"], snapshot["trade_date"]))
                    if ind_row:
                        snapshot["industry_return_5d"] = _float(ind_row.get("industry_return_5d"))
                        snapshot["industry_return_10d"] = _float(ind_row.get("industry_return_10d"))
                        if snapshot["pre_5d_return"] is not None and snapshot["industry_return_5d"] is not None:
                            snapshot["stock_excess_vs_industry_5d"] = snapshot["pre_5d_return"] - snapshot["industry_return_5d"]
                        if snapshot["pre_10d_return"] is not None and snapshot["industry_return_10d"] is not None:
                            snapshot["stock_excess_vs_industry_10d"] = snapshot["pre_10d_return"] - snapshot["industry_return_10d"]
                rows.append(snapshot)
    return pd.DataFrame(rows).reindex(columns=CASE_FACTOR_SNAPSHOT_COLUMNS)


def build_failure_target_audit(curated: pd.DataFrame, factor_snapshot: pd.DataFrame) -> pd.DataFrame:
    if curated.empty or factor_snapshot.empty:
        return pd.DataFrame(columns=FAILURE_TARGET_AUDIT_COLUMNS)
    case_meta = curated.set_index("case_id").to_dict("index")
    event_zero = factor_snapshot[factor_snapshot["relative_day"] == 0].copy()
    rows: list[dict[str, Any]] = []
    for record in event_zero.fillna("").to_dict("records"):
        case_id = str(record.get("case_id") or "")
        meta = case_meta.get(case_id, {})
        event_type = str(record.get("event_type") or "")
        stage_return = _float(record.get("stage_return"))
        max_drawdown = _float(record.get("max_drawdown"))
        pre_5d_return = _float(record.get("pre_5d_return"))
        post_3d_return = _float(record.get("future_3d_return"))
        post_5d_return = _float(record.get("future_5d_return"))
        post_10d_return = _float(record.get("future_10d_return"))
        post_5d_max_drawdown = _float(record.get("future_5d_max_drawdown"))
        post_10d_max_drawdown = _float(record.get("future_10d_max_drawdown"))
        amount_vs_20d = _float(record.get("amount_vs_20d"))
        high_to_close_drawdown = _float(record.get("high_to_close_drawdown"))
        close_position = _float(record.get("close_position_in_day"))
        limit_up_count = int(record.get("limit_up_count_before_event") or record.get("max_limit_up_count") or 0)
        max_limit_up_count = int(record.get("max_limit_up_count") or limit_up_count)
        event_strength_score = (
            min(max(stage_return, 0.0), 2.0) * 0.35
            + min(max(amount_vs_20d, 0.0), 3.0) * 0.15
            + min(max(limit_up_count, 0), 5) * 0.1
            + min(abs(max_drawdown), 0.5) * 0.4
        )
        suggested_case_type = ""
        failure_reason = ""
        failure_score = 0.0

        if (
            event_type in {"break_limit", "peak", "a_kill_start"}
            and (limit_up_count >= 1 or stage_return >= 0.35 or amount_vs_20d >= 1.5)
            and post_5d_return <= -0.08
            and post_10d_max_drawdown <= -0.12
        ):
            suggested_case_type = "a_kill_failure"
            failure_reason = "popularity confirmed before break, then no effective rebound and post-event drawdown deepened"
            failure_score = 0.45 + abs(min(post_10d_max_drawdown, 0.0)) + abs(min(post_5d_return, 0.0)) * 0.6
        elif (
            event_type == "reversal"
            and (post_3d_return <= -0.03 or post_5d_return <= -0.05)
            and (high_to_close_drawdown <= -0.04 or close_position <= 0.35)
        ):
            suggested_case_type = "failed_reversal"
            failure_reason = "reversal attempt failed to extend and quickly weakened after event"
            failure_score = 0.35 + abs(min(post_5d_return, 0.0)) + abs(min(high_to_close_drawdown, 0.0))
        elif (
            event_type == "second_wave_start"
            and (post_5d_return <= -0.04 or post_10d_max_drawdown <= -0.10)
        ):
            suggested_case_type = "failed_second_wave"
            failure_reason = "second-wave breakout attempt failed and follow-through weakened"
            failure_score = 0.35 + abs(min(post_10d_max_drawdown, 0.0)) + abs(min(post_5d_return, 0.0)) * 0.8
        elif (
            event_type == "first_limit_up"
            and max_limit_up_count <= 1
            and amount_vs_20d >= 1.5
            and post_3d_return <= -0.03
        ):
            suggested_case_type = "one_day_pump"
            failure_reason = "single-day surge lacked continuation and retraced quickly"
            failure_score = 0.30 + abs(min(post_3d_return, 0.0)) + max(amount_vs_20d - 1.0, 0.0) * 0.1
        elif (
            high_to_close_drawdown <= -0.06
            and close_position <= 0.30
            and (post_3d_return <= -0.03 or post_5d_return <= -0.04)
        ):
            suggested_case_type = "high_open_low_close_failure"
            failure_reason = "intraday rush faded into weak close and post-event continuation failed"
            failure_score = 0.28 + abs(min(high_to_close_drawdown, 0.0)) * 2.0 + abs(min(post_3d_return, 0.0))

        if not suggested_case_type:
            continue
        year = int(pd.to_numeric(meta.get("case_year", record.get("case_year")), errors="coerce") or 0)
        stock_name = str(meta.get("stock_name") or record.get("stock_name") or "")
        rows.append(
            {
                "target_id": f"failure_{len(rows)+1:04d}",
                "case_id": case_id,
                "ts_code": _normalize_ts_code(meta.get("ts_code") or record.get("ts_code")),
                "stock_name": stock_name,
                "case_year": year,
                "suggested_case_type": suggested_case_type,
                "event_date": str(record.get("event_date") or ""),
                "stage_return": stage_return,
                "max_drawdown": max_drawdown,
                "pre_5d_return": pre_5d_return,
                "post_3d_return": post_3d_return,
                "post_5d_return": post_5d_return,
                "post_10d_return": post_10d_return,
                "post_5d_max_drawdown": post_5d_max_drawdown,
                "post_10d_max_drawdown": post_10d_max_drawdown,
                "amount_vs_20d": amount_vs_20d,
                "high_to_close_drawdown": high_to_close_drawdown,
                "max_limit_up_count": max_limit_up_count,
                "event_strength_score": round(event_strength_score, 4),
                "failure_score": round(failure_score, 4),
                "failure_reason": failure_reason,
                "suggested_search_query": f"{year} {stock_name} {suggested_case_type} 复盘".strip(),
                "suggested_search_query_2": f"{year} {stock_name} {'A杀' if 'kill' in suggested_case_type else suggested_case_type} 妖股".strip(),
            }
        )
    if not rows:
        return pd.DataFrame(columns=FAILURE_TARGET_AUDIT_COLUMNS)
    return pd.DataFrame(rows).sort_values(
        ["case_year", "suggested_case_type", "failure_score"],
        ascending=[True, True, False],
    ).reindex(columns=FAILURE_TARGET_AUDIT_COLUMNS)


def build_local_candidate_source_priority(
    curated: pd.DataFrame,
    failure_target_audit: pd.DataFrame,
) -> pd.DataFrame:
    local = curated[curated.get("source_origin", pd.Series(dtype="object")).astype(str) == "local_auto_candidate"].copy()
    if local.empty:
        return pd.DataFrame(columns=LOCAL_SOURCE_PRIORITY_COLUMNS)
    failure_map = (
        failure_target_audit.sort_values("failure_score", ascending=False)
        .drop_duplicates(subset=["case_id"], keep="first")
        .set_index("case_id")
        .to_dict("index")
        if not failure_target_audit.empty
        else {}
    )
    type_counts = local.get("verified_case_type", pd.Series(dtype="object")).astype(str).value_counts().to_dict()
    rows: list[dict[str, Any]] = []
    for record in local.fillna("").to_dict("records"):
        case_id = str(record.get("case_id") or "")
        failure = failure_map.get(case_id, {})
        event_strength_score = _float(failure.get("event_strength_score")) or (
            min(max(_float(record.get("stage_return")), 0.0), 2.0) * 0.5
            + min(abs(_float(record.get("max_drawdown"))), 0.5) * 0.3
            + min(int(record.get("max_limit_up_count") or 0), 5) * 0.2
        )
        failure_score = _float(failure.get("failure_score"))
        verified_case_type = str(record.get("verified_case_type") or record.get("case_type") or "unknown")
        search_case_type = str(failure.get("suggested_case_type") or verified_case_type)
        rarity_score = 1.0 / max(type_counts.get(verified_case_type, 1), 1)
        source_priority_score = round(
            0.35 * _float(record.get("case_confidence_score"))
            + 0.30 * event_strength_score
            + 0.25 * failure_score
            + 0.10 * rarity_score,
            4,
        )
        year = int(pd.to_numeric(record.get("case_year"), errors="coerce") or 0)
        stock_name = str(record.get("stock_name") or "")
        query_1 = str(failure.get("suggested_search_query") or record.get("suggested_search_query") or f"{year} {stock_name} {search_case_type} 复盘").strip()
        query_2 = str(failure.get("suggested_search_query_2") or f"{year} {stock_name} 妖股 复盘").strip()
        query_3 = f"{year} {stock_name} 龙虎榜 断板 二波".strip()
        rows.append(
            {
                "case_id": case_id,
                "ts_code": _normalize_ts_code(record.get("ts_code")),
                "stock_name": stock_name,
                "case_year": year,
                "verified_case_type": search_case_type,
                "source_origin": str(record.get("source_origin") or ""),
                "case_confidence_score": _float(record.get("case_confidence_score")),
                "event_strength_score": round(event_strength_score, 4),
                "failure_score": round(failure_score, 4),
                "source_priority_score": source_priority_score,
                "needs_web_source": bool(record.get("needs_web_source")),
                "suggested_search_query": query_1,
                "suggested_search_query_2": query_2,
                "suggested_search_query_3": query_3,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["source_priority_score", "failure_score", "event_strength_score"],
        ascending=[False, False, False],
    ).reindex(columns=LOCAL_SOURCE_PRIORITY_COLUMNS)


def build_article_seed_suggestions(source_priority: pd.DataFrame) -> pd.DataFrame:
    if source_priority.empty:
        return pd.DataFrame(columns=ARTICLE_SEED_SUGGESTION_COLUMNS)
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(source_priority.fillna("").to_dict("records"), start=1):
        case_year = int(pd.to_numeric(record.get("case_year"), errors="coerce") or 0)
        stock_name = str(record.get("stock_name") or "")
        ts_code = _normalize_ts_code(record.get("ts_code"))
        case_type = str(record.get("verified_case_type") or "unknown")
        theme = str(record.get("suggested_theme") or "")
        template = ",".join(
            [
                f"suggestion_{index:04d}",
                "",
                "",
                "",
                "manual_search_result",
                "unknown",
                stock_name,
                ts_code,
                theme,
                case_type,
                f"generated from local candidate {record.get('case_id')}",
            ]
        )
        rows.append(
            {
                "suggestion_id": f"suggestion_{index:04d}",
                "ts_code": ts_code,
                "stock_name": stock_name,
                "case_year": case_year,
                "suggested_case_type": case_type,
                "suggested_theme": theme,
                "suggested_source_type": "manual_search_result",
                "suggested_search_query": str(record.get("suggested_search_query") or ""),
                "suggested_search_query_2": str(record.get("suggested_search_query_2") or ""),
                "suggested_search_query_3": str(record.get("suggested_search_query_3") or ""),
                "event_date": "",
                "reason": "need manual web source to corroborate local auto candidate",
                "priority_score": _float(record.get("source_priority_score")),
                "article_seed_template_row": template,
            }
        )
    return pd.DataFrame(rows).reindex(columns=ARTICLE_SEED_SUGGESTION_COLUMNS)


def build_source_backfill_tasks(
    article_seed_suggestions: pd.DataFrame,
    failure_target_audit: pd.DataFrame | None = None,
    curated: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if article_seed_suggestions.empty and (failure_target_audit is None or failure_target_audit.empty):
        return pd.DataFrame(columns=SOURCE_BACKFILL_TASK_COLUMNS)
    rows: list[dict[str, Any]] = []
    type_priority = {
        "failed_reversal": 2.00,
        "high_open_low_close_failure": 1.50,
        "a_kill_failure": 1.00,
        "failed_second_wave": 0.80,
        "one_day_pump": 0.50,
    }
    source_hint = {
        "failed_reversal": "financial_media",
        "high_open_low_close_failure": "financial_media",
        "a_kill_failure": "financial_media",
        "failed_second_wave": "manual_search_result",
        "one_day_pump": "eastmoney",
    }
    for index, record in enumerate(article_seed_suggestions.fillna("").to_dict("records"), start=1):
        case_type = str(record.get("suggested_case_type") or "")
        case_year = int(pd.to_numeric(record.get("case_year"), errors="coerce") or 0)
        priority = _float(record.get("priority_score")) + type_priority.get(case_type, 0.0)
        if case_year == 2026 and ("failure" in case_type or "pump" in case_type):
            priority += 1.20
        rows.append(
            {
                "task_id": f"backfill_{index:04d}",
                "ts_code": _normalize_ts_code(record.get("ts_code")),
                "stock_name": str(record.get("stock_name") or ""),
                "case_year": case_year,
                "suggested_case_type": case_type,
                "priority_score": round(priority, 4),
                "reason": str(record.get("reason") or ""),
                "suggested_search_query": str(record.get("suggested_search_query") or ""),
                "suggested_search_query_2": str(record.get("suggested_search_query_2") or ""),
                "suggested_search_query_3": str(record.get("suggested_search_query_3") or ""),
                "preferred_source_type": source_hint.get(case_type, "manual_search_result"),
                "source_url": "",
                "source_title": "",
                "source_date": "",
                "source_type": "",
                "source_confidence": "",
                "backfill_status": "pending",
                "reviewer_note": "",
                "article_seed_template_row": str(record.get("article_seed_template_row") or ""),
            }
        )
    if failure_target_audit is not None and not failure_target_audit.empty:
        curated_meta = (
            curated.set_index("case_id").to_dict("index")
            if curated is not None and not curated.empty and "case_id" in curated.columns
            else {}
        )
        existing = {
            (
                _normalize_ts_code(row.get("ts_code")),
                int(pd.to_numeric(row.get("case_year"), errors="coerce") or 0),
                str(row.get("suggested_case_type") or ""),
            )
            for row in rows
        }
        for record in failure_target_audit.fillna("").to_dict("records"):
            case_id = str(record.get("case_id") or "")
            meta = curated_meta.get(case_id, {})
            case_type = str(record.get("suggested_case_type") or "")
            case_year = int(pd.to_numeric(record.get("case_year"), errors="coerce") or pd.to_numeric(meta.get("case_year"), errors="coerce") or 0)
            key = (_normalize_ts_code(record.get("ts_code")), case_year, case_type)
            if key in existing:
                continue
            stock_name = str(record.get("stock_name") or meta.get("stock_name") or "")
            priority = (
                _float(record.get("failure_score"))
                + type_priority.get(case_type, 0.0)
                + (1.20 if case_year == 2026 and ("failure" in case_type or "pump" in case_type) else 0.0)
            )
            template = ",".join(
                [
                    f"backfill_failure_{len(rows)+1:04d}",
                    "",
                    "",
                    "",
                    "manual_search_result",
                    "unknown",
                    stock_name,
                    _normalize_ts_code(record.get("ts_code")),
                    "",
                    case_type,
                    f"failure backfill from case {case_id}",
                ]
            )
            rows.append(
                {
                    "task_id": f"backfill_{len(rows)+1:04d}",
                    "ts_code": _normalize_ts_code(record.get("ts_code")),
                    "stock_name": stock_name,
                    "case_year": case_year,
                    "suggested_case_type": case_type,
                    "priority_score": round(priority, 4),
                    "reason": str(record.get("failure_reason") or "failure case needs corroborating web source"),
                    "suggested_search_query": str(record.get("suggested_search_query") or ""),
                    "suggested_search_query_2": str(record.get("suggested_search_query_2") or ""),
                    "suggested_search_query_3": f"{case_year} {stock_name} {case_type} 龙虎榜 复盘".strip(),
                    "preferred_source_type": source_hint.get(case_type, "financial_media"),
                    "source_url": "",
                    "source_title": "",
                    "source_date": "",
                    "source_type": "",
                    "source_confidence": "",
                    "backfill_status": "pending",
                    "reviewer_note": "",
                    "article_seed_template_row": template,
                }
            )
            existing.add(key)
    return pd.DataFrame(rows).sort_values(
        ["priority_score", "case_year", "suggested_case_type"],
        ascending=[False, False, True],
    ).reindex(columns=SOURCE_BACKFILL_TASK_COLUMNS)


def build_source_backfill_report(tasks: pd.DataFrame) -> str:
    if tasks.empty:
        distribution = "无任务。"
    else:
        distribution = _table_preview(
            tasks.groupby(["case_year", "suggested_case_type"], dropna=False)
            .size()
            .reset_index(name="task_count")
            .sort_values(["case_year", "suggested_case_type"]),
            rows=24,
        )
    return "\n".join(
        [
            "# Dragon Case Source Backfill v1 报告",
            "",
            "## 1. 背景",
            "当前本地失败候选已经形成，但 web source 仍不足，尤其 failed_reversal / high_open_low_close_failure / 2026 失败样本。",
            "",
            "## 2. 补证优先级",
            "优先级顺序：failed_reversal、high_open_low_close_failure、2026 失败样本、a_kill_failure、failed_second_wave。",
            "",
            "## 3. 待补证任务分布",
            distribution,
            "",
            "## 4. 如何人工补 URL",
            "人工搜索后，将 source_url / source_title / source_date / source_type / source_confidence 填回任务表，再复制 article_seed_template_row 到 data/seed/dragon_case_web_article_seed_2024_2026.csv。",
            "",
            "## 5. 下一步",
            "补完 source_url 后重新运行：dragon-case-expand-web-seeds -> dragon-case-import-web-seeds -> dragon-case-web-verify。",
        ]
    )


def apply_source_backfill(
    *,
    tasks_path: str | Path,
    article_seed_path: str | Path,
    output_dir: str | Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    tasks = pd.read_csv(tasks_path, low_memory=False) if Path(tasks_path).exists() else pd.DataFrame(columns=SOURCE_BACKFILL_TASK_COLUMNS)
    article_seed = read_web_article_seed(article_seed_path)
    before_rows = int(len(article_seed))
    existing_url = {str(value).strip() for value in article_seed.get("source_url", pd.Series(dtype="object")).fillna("").astype(str) if str(value).strip()}
    existing_title_key = {
        (
            str(row.get("mentioned_stocks") or "").strip(),
            str(row.get("source_title") or "").strip(),
            str(row.get("source_date") or "").strip(),
        )
        for row in article_seed.fillna("").to_dict("records")
    }
    existing_case_key = {
        (
            _normalize_ts_code(row.get("mentioned_ts_codes")),
            _year_of(row.get("source_date")),
            str(row.get("mentioned_case_types") or "").strip(),
            str(row.get("source_url") or "").strip(),
        )
        for row in article_seed.fillna("").to_dict("records")
    }
    status_series = tasks.get("backfill_status", pd.Series(dtype="object")).fillna("").astype(str).str.strip().str.lower()
    errors: list[dict[str, Any]] = []
    inserts: list[dict[str, Any]] = []
    valid_found_tasks = 0
    skipped_duplicate_rows = 0
    source_types = {
        "news", "eastmoney", "xueqiu", "cls", "stcn", "sina", "china_com",
        "wallstreetcn", "broker_report", "public_article", "manual_search_result", "other", "caixin"
    }
    for record in tasks.fillna("").to_dict("records"):
        status = str(record.get("backfill_status") or "").strip().lower()
        if status != "found":
            if status not in {"pending", "rejected", "not_found", ""}:
                errors.append(_source_backfill_error(record, "invalid_status", f"unsupported backfill_status={status}"))
            continue
        source_url = str(record.get("source_url") or "").strip()
        source_title = str(record.get("source_title") or "").strip()
        source_date = str(record.get("source_date") or "").strip()
        source_type = str(record.get("source_type") or "").strip()
        source_confidence = str(record.get("source_confidence") or "").strip()
        error_type = ""
        error_message = ""
        if not source_url:
            error_type, error_message = "missing_source_url", "found task requires source_url"
        elif not source_url.startswith(("http://", "https://")):
            error_type, error_message = "missing_source_url", "source_url must start with http:// or https://"
        elif not source_title:
            error_type, error_message = "missing_source_title", "found task requires source_title"
        elif not source_date or pd.isna(pd.to_datetime(source_date, errors="coerce")):
            error_type, error_message = "missing_source_date", "source_date must be parseable as date"
        elif not source_type:
            error_type, error_message = "missing_source_type", "found task requires source_type"
        elif source_type not in source_types:
            error_type, error_message = "missing_source_type", f"unsupported source_type={source_type}"
        else:
            try:
                conf = float(source_confidence)
                if conf < 0 or conf > 1:
                    raise ValueError
            except Exception:
                error_type, error_message = "invalid_source_confidence", "source_confidence must be within [0,1]"
        if error_type:
            errors.append(_source_backfill_error(record, error_type, error_message))
            continue
        valid_found_tasks += 1
        title_key = (
            str(record.get("stock_name") or "").strip(),
            source_title,
            pd.to_datetime(source_date).strftime("%Y-%m-%d"),
        )
        case_key = (
            _normalize_ts_code(record.get("ts_code")),
            int(pd.to_numeric(record.get("case_year"), errors="coerce") or 0),
            str(record.get("suggested_case_type") or "").strip(),
            source_url,
        )
        if source_url in existing_url or title_key in existing_title_key or case_key in existing_case_key:
            skipped_duplicate_rows += 1
            errors.append(_source_backfill_error(record, "duplicate_source", "duplicate source_url/title/date or case key"))
            continue
        inserts.append(
            {
                "article_id": str(record.get("task_id") or f"backfill_{len(inserts)+1:04d}"),
                "source_title": source_title,
                "source_url": source_url,
                "source_date": pd.to_datetime(source_date).strftime("%Y-%m-%d"),
                "source_type": source_type,
                "source_confidence": float(source_confidence),
                "mentioned_stocks": str(record.get("stock_name") or "").strip(),
                "mentioned_ts_codes": _normalize_ts_code(record.get("ts_code")),
                "mentioned_themes": "",
                "mentioned_case_types": str(record.get("suggested_case_type") or "").strip(),
                "notes": str(record.get("reviewer_note") or record.get("reason") or ""),
            }
        )
        existing_url.add(source_url)
        existing_title_key.add(title_key)
        existing_case_key.add(case_key)
    inserted_rows = len(inserts)
    merged = article_seed.copy()
    if inserts:
        merged = pd.concat([merged, pd.DataFrame(inserts)], ignore_index=True)
    after_rows = int(len(merged))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(
        [
            {
                "total_tasks": int(len(tasks)),
                "found_tasks": int((status_series == "found").sum()),
                "pending_tasks": int((status_series == "pending").sum()),
                "rejected_tasks": int((status_series == "rejected").sum()),
                "not_found_tasks": int((status_series == "not_found").sum()),
                "valid_found_tasks": valid_found_tasks,
                "invalid_found_tasks": int((status_series == "found").sum()) - valid_found_tasks,
                "inserted_article_seed_rows": inserted_rows,
                "skipped_duplicate_rows": skipped_duplicate_rows,
                "article_seed_before_rows": before_rows,
                "article_seed_after_rows": after_rows,
            }
        ]
    ).reindex(columns=SOURCE_BACKFILL_APPLY_SUMMARY_COLUMNS)
    error_frame = pd.DataFrame(errors).reindex(columns=SOURCE_BACKFILL_APPLY_ERROR_COLUMNS)
    if not dry_run:
        merged.to_csv(article_seed_path, index=False)
    summary_path = out / "dragon_case_source_backfill_apply_summary.csv"
    errors_path = out / "dragon_case_source_backfill_apply_errors.csv"
    report_path = out / "dragon_case_source_backfill_apply_report.md"
    summary.to_csv(summary_path, index=False)
    error_frame.to_csv(errors_path, index=False)
    report_path.write_text(
        _source_backfill_apply_report(summary.iloc[0].to_dict(), error_frame, dry_run=dry_run),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "errors": error_frame,
        "article_seed": merged,
        "paths": {
            "summary": str(summary_path),
            "errors": str(errors_path),
            "report": str(report_path),
            "article_seed": str(article_seed_path),
        },
        "warnings": [],
    }


def compare_source_backfill_curated(
    *,
    before_curated_path: str | Path,
    after_curated_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    before_path = Path(before_curated_path)
    if before_path.exists():
        before = pd.read_csv(before_path, low_memory=False)
    else:
        before = pd.DataFrame()
        warnings.append(f"missing before curated file: {before_path}")
    after = pd.read_csv(after_curated_path, low_memory=False) if Path(after_curated_path).exists() else pd.DataFrame()
    metrics = [
        ("curated_total", lambda df: len(df)),
        ("web_seed_verified_count", lambda df: int((df.get("source_origin", pd.Series(dtype='object')).astype(str) == "web_seed_verified").sum()) if not df.empty else 0),
        ("local_auto_candidate_count", lambda df: int((df.get("source_origin", pd.Series(dtype='object')).astype(str) == "local_auto_candidate").sum()) if not df.empty else 0),
        ("second_wave_count", lambda df: int((df.get("verified_case_type", pd.Series(dtype='object')).astype(str) == "second_wave").sum()) if not df.empty else 0),
        ("failed_second_wave_count", lambda df: int((df.get("verified_case_type", pd.Series(dtype='object')).astype(str) == "failed_second_wave").sum()) if not df.empty else 0),
        ("a_kill_failure_count", lambda df: int((df.get("verified_case_type", pd.Series(dtype='object')).astype(str) == "a_kill_failure").sum()) if not df.empty else 0),
        ("failed_reversal_count", lambda df: int((df.get("verified_case_type", pd.Series(dtype='object')).astype(str) == "failed_reversal").sum()) if not df.empty else 0),
        ("high_open_low_close_failure_count", lambda df: int((df.get("verified_case_type", pd.Series(dtype='object')).astype(str) == "high_open_low_close_failure").sum()) if not df.empty else 0),
        ("one_day_pump_count", lambda df: int((df.get("verified_case_type", pd.Series(dtype='object')).astype(str) == "one_day_pump").sum()) if not df.empty else 0),
        ("2024_count", lambda df: int((pd.to_numeric(df.get("case_year", pd.Series(dtype='object')), errors='coerce') == 2024).sum()) if not df.empty else 0),
        ("2025_count", lambda df: int((pd.to_numeric(df.get("case_year", pd.Series(dtype='object')), errors='coerce') == 2025).sum()) if not df.empty else 0),
        ("2026_count", lambda df: int((pd.to_numeric(df.get("case_year", pd.Series(dtype='object')), errors='coerce') == 2026).sum()) if not df.empty else 0),
    ]
    rows = []
    for metric, fn in metrics:
        before_value = fn(before)
        after_value = fn(after)
        rows.append(
            {
                "metric": metric,
                "before_value": before_value,
                "after_value": after_value,
                "delta": after_value - before_value,
            }
        )
    delta = pd.DataFrame(rows).reindex(columns=SOURCE_BACKFILL_DELTA_COLUMNS)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    delta_path = out / "dragon_case_source_backfill_delta_summary.csv"
    delta.to_csv(delta_path, index=False)
    return {"delta": delta, "warnings": warnings, "paths": {"delta": str(delta_path)}}


def _source_backfill_error(record: dict[str, Any], error_type: str, error_message: str) -> dict[str, Any]:
    return {
        "task_id": str(record.get("task_id") or ""),
        "ts_code": _normalize_ts_code(record.get("ts_code")),
        "stock_name": str(record.get("stock_name") or ""),
        "suggested_case_type": str(record.get("suggested_case_type") or ""),
        "source_url": str(record.get("source_url") or ""),
        "error_type": error_type,
        "error_message": error_message,
    }


def _source_backfill_apply_report(summary: dict[str, Any], errors: pd.DataFrame, *, dry_run: bool) -> str:
    return "\n".join(
        [
            "# Dragon Case Source Backfill Apply v1 报告",
            "",
            "## 1. 背景",
            "source_backfill_tasks 已生成，现在需要把 `found` 任务合并回 article seed。",
            "",
            "## 2. Apply 结果",
            (
                f"total={summary.get('total_tasks', 0)}; found={summary.get('found_tasks', 0)}; "
                f"inserted={summary.get('inserted_article_seed_rows', 0)}; duplicate={summary.get('skipped_duplicate_rows', 0)}; "
                f"invalid={summary.get('invalid_found_tasks', 0)}; dry_run={dry_run}"
            ),
            "",
            "## 3. 错误任务",
            _table_preview(errors, rows=24),
            "",
            "## 4. 下一步命令",
            "stock-research dragon-case-expand-web-seeds \\",
            "  --article-seed data/seed/dragon_case_web_article_seed_2024_2026.csv \\",
            "  --output data/seed/dragon_case_web_seed_2024_2026.csv \\",
            "  --start-date 2024-01-01 \\",
            "  --end-date 2026-05-13",
            "",
            "stock-research dragon-case-import-web-seeds \\",
            "  --input data/seed/dragon_case_web_seed_2024_2026.csv \\",
            "  --output-dir outputs/research",
            "",
            "stock-research dragon-case-web-verify \\",
            "  --candidate-path outputs/research/dragon_case_web_candidates_2024_2026.csv \\",
            "  --start-date 2024-01-01 \\",
            "  --end-date 2026-05-13 \\",
            "  --output-dir outputs/research",
            "",
            "## 5. 是否进入 LHB",
            "只有当 web_seed_verified 明显高于当前水平，且 failed_reversal / high_open_low_close_failure / 2026 失败样本补齐后，才建议进入 LHB 小样本导入。",
        ]
    )


def build_source_backfill_workpack(
    tasks: pd.DataFrame,
    *,
    top_n: int,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    if tasks.empty:
        workpack = pd.DataFrame(columns=SOURCE_BACKFILL_WORKPACK_COLUMNS)
    else:
        frame = tasks.copy()
        frame["case_year"] = pd.to_numeric(frame.get("case_year"), errors="coerce")
        frame["priority_bucket"] = frame.apply(
            lambda row: _workpack_priority_bucket(
                str(row.get("suggested_case_type") or ""),
                int(pd.to_numeric(row.get("case_year"), errors="coerce") or 0),
            ),
            axis=1,
        )
        rows: list[dict[str, Any]] = []
        for record in frame.fillna("").to_dict("records"):
            year = int(pd.to_numeric(record.get("case_year"), errors="coerce") or 0)
            stock_name = str(record.get("stock_name") or "")
            case_type = str(record.get("suggested_case_type") or "")
            q1, q2, q3 = _source_backfill_queries(year, stock_name, case_type)
            rec_type, rec_conf, note = _recommended_source_meta(str(record.get("preferred_source_type") or ""), case_type)
            rows.append(
                {
                    "task_id": str(record.get("task_id") or ""),
                    "ts_code": _normalize_ts_code(record.get("ts_code")),
                    "stock_name": stock_name,
                    "case_year": year,
                    "suggested_case_type": case_type,
                    "priority_score": _float(record.get("priority_score")),
                    "reason": str(record.get("reason") or ""),
                    "suggested_search_query": q1,
                    "suggested_search_query_2": q2,
                    "suggested_search_query_3": q3,
                    "preferred_source_type": str(record.get("preferred_source_type") or ""),
                    "recommended_source_type": rec_type,
                    "recommended_source_confidence": rec_conf,
                    "confidence_note": note,
                    "backfill_status": str(record.get("backfill_status") or ""),
                    "source_url": str(record.get("source_url") or ""),
                    "source_title": str(record.get("source_title") or ""),
                    "source_date": str(record.get("source_date") or ""),
                    "source_type": str(record.get("source_type") or ""),
                    "source_confidence": record.get("source_confidence") or "",
                    "reviewer_note": str(record.get("reviewer_note") or ""),
                    "article_seed_template_row": str(record.get("article_seed_template_row") or ""),
                    "_priority_bucket": int(record.get("priority_bucket") or 99),
                }
            )
        workpack = (
            pd.DataFrame(rows)
            .sort_values(["_priority_bucket", "priority_score", "case_year"], ascending=[True, False, False])
            .head(max(1, int(top_n)))
            .drop(columns=["_priority_bucket"])
            .reindex(columns=SOURCE_BACKFILL_WORKPACK_COLUMNS)
        )
    result = {"workpack": workpack, "markdown": _source_backfill_workpack_markdown(workpack)}
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        top_label = f"top{int(top_n)}"
        csv_path = out / f"dragon_case_source_backfill_workpack_{top_label}.csv"
        md_path = out / f"dragon_case_source_backfill_workpack_{top_label}.md"
        sh_path = out / "dragon_case_source_backfill_next_commands.sh"
        workpack.to_csv(csv_path, index=False)
        md_path.write_text(result["markdown"], encoding="utf-8")
        sh_path.write_text(_source_backfill_next_commands_script(), encoding="utf-8")
        result["paths"] = {"csv": str(csv_path), "markdown": str(md_path), "next_commands": str(sh_path)}
    return result


def build_source_backfill_check_report(
    apply_summary: pd.DataFrame,
    delta_summary: pd.DataFrame,
    curated: pd.DataFrame,
) -> str:
    summary = apply_summary.iloc[0].to_dict() if not apply_summary.empty else {}
    delta_map = {}
    if not delta_summary.empty:
        for row in delta_summary.fillna(0).to_dict("records"):
            delta_map[str(row.get("metric"))] = row
    web_after = int(delta_map.get("web_seed_verified_count", {}).get("after_value", 0))
    web_delta = int(delta_map.get("web_seed_verified_count", {}).get("delta", 0))
    failed_rev_delta = int(delta_map.get("failed_reversal_count", {}).get("delta", 0))
    hocl_delta = int(delta_map.get("high_open_low_close_failure_count", {}).get("delta", 0))
    y2026_delta = int(delta_map.get("2026_count", {}).get("delta", 0))
    invalid_found = int(summary.get("invalid_found_tasks", 0) or 0)
    found = int(summary.get("found_tasks", 0) or 0)
    inserted = int(summary.get("inserted_article_seed_rows", 0) or 0)
    eligible = (
        invalid_found == 0
        and inserted > 0
        and (web_after >= 40 or web_delta >= 10)
        and (failed_rev_delta > 0 or hocl_delta > 0 or y2026_delta > 0)
    )
    verdict = "可以开始准备 LHB 小样本导入。" if eligible else "继续 source backfill，不进入 LHB。"
    curated_total = len(curated)
    return "\n".join(
        [
            "# Dragon Case Source Backfill Check 报告",
            "",
            f"- found_tasks: {found}",
            f"- invalid_found_tasks: {invalid_found}",
            f"- inserted_article_seed_rows: {inserted}",
            f"- curated_total: {curated_total}",
            f"- web_seed_verified_after: {web_after}",
            f"- web_seed_verified_delta: {web_delta}",
            f"- failed_reversal_delta: {failed_rev_delta}",
            f"- high_open_low_close_failure_delta: {hocl_delta}",
            f"- 2026_delta: {y2026_delta}",
            "",
            "## 结论",
            verdict,
        ]
    )


def _workpack_priority_bucket(case_type: str, case_year: int) -> int:
    if case_type == "failed_reversal":
        return 1
    if case_type == "high_open_low_close_failure":
        return 2
    if case_year == 2026 and case_type in {"one_day_pump", "a_kill_failure", "failed_second_wave", "failed_reversal", "high_open_low_close_failure"}:
        return 3
    if case_type == "a_kill_failure":
        return 4
    if case_type == "failed_second_wave":
        return 5
    if case_type == "one_day_pump":
        return 6
    return 7


def _source_backfill_queries(case_year: int, stock_name: str, case_type: str) -> tuple[str, str, str]:
    if case_type == "failed_reversal":
        return (
            f"{case_year} {stock_name} 断板 反包 失败",
            f"{case_year} {stock_name} 假反包 复盘",
            f"{case_year} {stock_name} 反包后回落",
        )
    if case_type == "high_open_low_close_failure":
        return (
            f"{case_year} {stock_name} 高开低走",
            f"{case_year} {stock_name} 冲高回落 大面",
            f"{case_year} {stock_name} 高位放量回落",
        )
    if case_type == "a_kill_failure":
        return (
            f"{case_year} {stock_name} A杀 复盘",
            f"{case_year} {stock_name} 断板 A杀",
            f"{case_year} {stock_name} 连板 后 大跌",
        )
    if case_type == "failed_second_wave":
        return (
            f"{case_year} {stock_name} 二波 失败",
            f"{case_year} {stock_name} 突破失败 复盘",
            f"{case_year} {stock_name} 反弹失败",
        )
    if case_type == "one_day_pump":
        return (
            f"{case_year} {stock_name} 一日游",
            f"{case_year} {stock_name} 涨停 次日大跌",
            f"{case_year} {stock_name} 冲高回落",
        )
    if case_type == "break_then_reversal":
        return (
            f"{case_year} {stock_name} 断板 反包 复盘",
            f"{case_year} {stock_name} 反包 二波",
            f"{case_year} {stock_name} 断板后修复",
        )
    if case_type == "second_wave":
        return (
            f"{case_year} {stock_name} 二波 妖股 复盘",
            f"{case_year} {stock_name} 二次加速 复盘",
            f"{case_year} {stock_name} 突破 前高 复盘",
        )
    if case_type == "continuous_limit_up":
        return (
            f"{case_year} {stock_name} 连板 妖股 复盘",
            f"{case_year} {stock_name} 连板 龙头 复盘",
            f"{case_year} {stock_name} 龙虎榜 断板",
        )
    return (
        f"{case_year} {stock_name} 弱转强 复盘",
        f"{case_year} {stock_name} 妖股 复盘",
        f"{case_year} {stock_name} 龙虎榜 断板",
    )


def _recommended_source_meta(preferred_source_type: str, case_type: str) -> tuple[str, float, str]:
    source_type = preferred_source_type or "manual_search_result"
    if source_type in {"stcn", "cls", "broker_report"}:
        return source_type, 0.8, "优先主流财经媒体、券商或交易所口径。"
    if source_type in {"eastmoney", "sina", "wallstreetcn", "china_com", "news"}:
        return source_type, 0.7, "门户或财经媒体可用，但要交叉核验。"
    if source_type in {"xueqiu", "public_article", "manual_search_result"}:
        base = 0.5 if case_type in {"failed_reversal", "high_open_low_close_failure"} else 0.6
        return source_type, base, "社区或公开复盘只作线索，不能单独当真相。"
    return "manual_search_result", 0.6, "默认先人工搜索，再人工补 URL。"


def _source_backfill_workpack_markdown(workpack: pd.DataFrame) -> str:
    lines = ["# Dragon Case Source Backfill Workpack", ""]
    if workpack.empty:
        lines.append("无可用任务。")
        return "\n".join(lines)
    for row in workpack.to_dict("records"):
        lines.extend(
            [
                f"## {row['stock_name']} / {row['ts_code']} / {int(row['case_year'])} / {row['suggested_case_type']}",
                f"- 为什么优先补：{row['reason']}",
                f"- 推荐搜索词 1：{row['suggested_search_query']}",
                f"- 推荐搜索词 2：{row['suggested_search_query_2']}",
                f"- 推荐搜索词 3：{row['suggested_search_query_3']}",
                f"- 建议 source_type：{row['recommended_source_type']}",
                f"- 建议 source_confidence：{row['recommended_source_confidence']}",
                f"- 说明：{row['confidence_note']}",
                "- 需要人工填写的字段：",
                "  - source_url",
                "  - source_title",
                "  - source_date",
                "  - source_type",
                "  - source_confidence",
                "  - backfill_status=found / not_found / rejected",
                "  - reviewer_note",
                "",
            ]
        )
    return "\n".join(lines)


def _source_backfill_next_commands_script() -> str:
    return "\n".join(
        [
            "cp outputs/research/dragon_case_curated_library_2024_2026.csv \\",
            "   outputs/research/dragon_case_curated_library_2024_2026_before_source_backfill.csv",
            "",
            "stock-research dragon-case-apply-source-backfill \\",
            "  --tasks-path outputs/research/dragon_case_source_backfill_tasks_2024_2026.csv \\",
            "  --article-seed data/seed/dragon_case_web_article_seed_2024_2026.csv \\",
            "  --output-dir outputs/research \\",
            "  --dry-run",
            "",
            "stock-research dragon-case-apply-source-backfill \\",
            "  --tasks-path outputs/research/dragon_case_source_backfill_tasks_2024_2026.csv \\",
            "  --article-seed data/seed/dragon_case_web_article_seed_2024_2026.csv \\",
            "  --output-dir outputs/research",
            "",
            "stock-research dragon-case-expand-web-seeds \\",
            "  --article-seed data/seed/dragon_case_web_article_seed_2024_2026.csv \\",
            "  --output data/seed/dragon_case_web_seed_2024_2026.csv \\",
            "  --start-date 2024-01-01 \\",
            "  --end-date 2026-05-13",
            "",
            "stock-research dragon-case-import-web-seeds \\",
            "  --input data/seed/dragon_case_web_seed_2024_2026.csv \\",
            "  --output-dir outputs/research",
            "",
            "stock-research dragon-case-web-verify \\",
            "  --candidate-path outputs/research/dragon_case_web_candidates_2024_2026.csv \\",
            "  --start-date 2024-01-01 \\",
            "  --end-date 2026-05-13 \\",
            "  --output-dir outputs/research",
            "",
            "stock-research dragon-case-source-backfill-compare \\",
            "  --before-curated outputs/research/dragon_case_curated_library_2024_2026_before_source_backfill.csv \\",
            "  --after-curated outputs/research/dragon_case_curated_library_2024_2026.csv \\",
            "  --output-dir outputs/research",
            "",
        ]
    )


def build_web_search_targets(
    auto_candidates: pd.DataFrame,
    *,
    factor_snapshot: pd.DataFrame | None = None,
    curated: pd.DataFrame | None = None,
    failure_target_audit: pd.DataFrame | None = None,
    start_year: int = 2024,
    end_year: int = 2026,
    per_year_case_type_limit: int = 5,
) -> pd.DataFrame:
    if auto_candidates.empty and (factor_snapshot is None or factor_snapshot.empty) and (failure_target_audit is None or failure_target_audit.empty):
        return pd.DataFrame(columns=WEB_SEARCH_TARGET_COLUMNS)
    rows: list[dict[str, Any]] = []
    if not auto_candidates.empty:
        frame = auto_candidates.copy()
        frame["case_year"] = pd.to_numeric(frame.get("case_year"), errors="coerce")
        frame = frame[(frame["case_year"] >= start_year) & (frame["case_year"] <= end_year)].copy()
        if not frame.empty:
            frame["ts_code"] = frame.get("ts_code", "").map(_normalize_ts_code)
            frame["candidate_quality_score"] = pd.to_numeric(frame.get("candidate_quality_score"), errors="coerce")
            frame["event_strength_score"] = frame["candidate_quality_score"]
            strength_fallback = (
                pd.to_numeric(frame.get("stage_return"), errors="coerce").fillna(0.0) * 0.6
                + pd.to_numeric(frame.get("max_limit_up_count"), errors="coerce").fillna(0.0) * 0.15
                + pd.to_numeric(frame.get("max_drawdown"), errors="coerce").fillna(0.0).abs() * 0.25
            )
            frame["event_strength_score"] = frame["event_strength_score"].fillna(strength_fallback)
            frame["suggested_case_type"] = frame.get("case_type", "").fillna("").astype(str)
            frame["event_date"] = (
                frame.get("a_kill_start_date", pd.Series(dtype="object")).fillna("")
                .replace("", pd.NA)
                .fillna(frame.get("second_wave_start_date", pd.Series(dtype="object")).fillna("").replace("", pd.NA))
                .fillna(frame.get("reversal_date", pd.Series(dtype="object")).fillna("").replace("", pd.NA))
                .fillna(frame.get("peak_date", pd.Series(dtype="object")).fillna("").replace("", pd.NA))
                .fillna(frame.get("first_limit_up_date", pd.Series(dtype="object")).fillna("").replace("", pd.NA))
            )
            frame = frame.sort_values(
                ["case_year", "suggested_case_type", "event_strength_score", "stage_return"],
                ascending=[True, True, False, False],
            )
            for record in frame.fillna("").to_dict("records"):
                rows.append(
                    {
                        "target_id": "",
                        "ts_code": _normalize_ts_code(record.get("ts_code")),
                        "stock_name": str(record.get("stock_name") or ""),
                        "case_year": int(record.get("case_year") or 0),
                        "suggested_case_type": str(record.get("suggested_case_type") or ""),
                        "start_date": record.get("start_date") or record.get("first_limit_up_date") or "",
                        "event_date": record.get("event_date") or "",
                        "candidate_quality_score": _float(record.get("candidate_quality_score")),
                        "event_strength_score": _float(record.get("event_strength_score")),
                        "stage_return": _float(record.get("stage_return")),
                        "max_drawdown": _float(record.get("max_drawdown")),
                        "max_limit_up_count": int(record.get("max_limit_up_count") or 0),
                        "suggested_search_query": f"{int(record.get('case_year') or 0)} {record.get('stock_name')} {record.get('suggested_case_type')} 复盘".strip(),
                        "suggested_search_query_2": f"{int(record.get('case_year') or 0)} {record.get('stock_name')} 妖股 复盘".strip(),
                        "reason": f"local auto candidate with {record.get('suggested_case_type')} pattern and event_strength={_float(record.get('event_strength_score')):.2f}",
                    }
                )
    if factor_snapshot is not None and not factor_snapshot.empty:
        zero = factor_snapshot[factor_snapshot["relative_day"] == 0].copy()
        for record in zero.fillna("").to_dict("records"):
            year = int(pd.to_numeric(record.get("trade_date", "")[:4], errors="coerce") or 0)
            if year < start_year or year > end_year:
                continue
            success_type = ""
            if str(record.get("event_type")) == "second_wave_start" and _float(record.get("future_5d_return")) >= 0.03:
                success_type = "second_wave"
            elif str(record.get("event_type")) == "reversal" and _float(record.get("future_5d_return")) >= 0.03:
                success_type = "break_then_reversal"
            if not success_type:
                continue
            rows.append(
                {
                    "target_id": "",
                    "ts_code": _normalize_ts_code(record.get("ts_code")),
                    "stock_name": str(record.get("stock_name") or ""),
                    "case_year": year,
                    "suggested_case_type": success_type,
                    "start_date": "",
                    "event_date": str(record.get("event_date") or ""),
                    "candidate_quality_score": 0.0,
                    "event_strength_score": abs(_float(record.get("future_5d_return"))) + abs(min(_float(record.get("future_5d_max_drawdown")), 0.0)),
                    "stage_return": _float(record.get("stage_return")),
                    "max_drawdown": 0.0,
                    "max_limit_up_count": int(record.get("max_limit_up_count") or record.get("limit_up_count_before_event") or 0),
                    "suggested_search_query": f"{year} {record.get('stock_name')} {success_type} 复盘".strip(),
                    "suggested_search_query_2": f"{year} {record.get('stock_name')} {'二波' if success_type=='second_wave' else '断板反包'}".strip(),
                    "reason": f"case_factor_snapshot success event at {record.get('event_type')}",
                }
            )
    if failure_target_audit is not None and not failure_target_audit.empty:
        for record in failure_target_audit.fillna("").to_dict("records"):
            rows.append(
                {
                    "target_id": str(record.get("target_id") or ""),
                    "ts_code": _normalize_ts_code(record.get("ts_code")),
                    "stock_name": str(record.get("stock_name") or ""),
                    "case_year": int(record.get("case_year") or 0),
                    "suggested_case_type": str(record.get("suggested_case_type") or ""),
                    "start_date": "",
                    "event_date": str(record.get("event_date") or ""),
                    "candidate_quality_score": 0.0,
                    "event_strength_score": _float(record.get("event_strength_score")),
                    "stage_return": _float(record.get("stage_return")),
                    "max_drawdown": _float(record.get("max_drawdown")),
                    "max_limit_up_count": int(record.get("max_limit_up_count") or 0),
                    "suggested_search_query": str(record.get("suggested_search_query") or ""),
                    "suggested_search_query_2": str(record.get("suggested_search_query_2") or ""),
                    "reason": str(record.get("failure_reason") or ""),
                }
            )
    source_rows = pd.DataFrame(rows)
    if source_rows.empty:
        return pd.DataFrame(columns=WEB_SEARCH_TARGET_COLUMNS)
    source_rows = source_rows.sort_values(
        ["case_year", "suggested_case_type", "event_strength_score", "stage_return"],
        ascending=[True, True, False, False],
    )
    rows = []
    seen: set[tuple[str, int, str]] = set()
    rows = []
    for record in source_rows.fillna("").to_dict("records"):
        key = (str(record.get("ts_code") or ""), int(record.get("case_year") or 0), str(record.get("suggested_case_type") or ""))
        if key in seen:
            continue
        year = int(record.get("case_year") or 0)
        case_type = str(record.get("suggested_case_type") or "")
        current_count = sum(1 for row in rows if row["case_year"] == year and row["suggested_case_type"] == case_type)
        if current_count >= per_year_case_type_limit:
            continue
        stock_name = str(record.get("stock_name") or "")
        query = f"{year} {stock_name} {case_type} 复盘".strip()
        query2 = f"{year} {stock_name} 妖股 {'A杀' if 'kill' in case_type or 'failed' in case_type else '二波'}".strip()
        rows.append(
            {
                "target_id": f"target_{len(rows)+1:04d}",
                "ts_code": _normalize_ts_code(record.get("ts_code")),
                "stock_name": stock_name,
                "case_year": year,
                "suggested_case_type": case_type,
                "start_date": record.get("start_date") or record.get("first_limit_up_date") or "",
                "event_date": record.get("event_date") or "",
                "candidate_quality_score": _float(record.get("candidate_quality_score")),
                "event_strength_score": _float(record.get("event_strength_score")),
                "stage_return": _float(record.get("stage_return")),
                "max_drawdown": _float(record.get("max_drawdown")),
                "max_limit_up_count": int(record.get("max_limit_up_count") or 0),
                "suggested_search_query": query,
                "suggested_search_query_2": query2,
                "reason": f"local auto candidate with {case_type} pattern and event_strength={_float(record.get('event_strength_score')):.2f}",
            }
        )
        seen.add(key)
    return pd.DataFrame(rows).reindex(columns=WEB_SEARCH_TARGET_COLUMNS)


def build_factor_alignment_audit(
    verified_candidates: pd.DataFrame,
    factor_review: pd.DataFrame,
    diagnostics_map: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    if factor_review.empty:
        return pd.DataFrame(columns=ALIGNMENT_AUDIT_COLUMNS)
    rows = []
    lookups = {name: _build_diagnostics_lookup(name, frame) for name, frame in diagnostics_map.items()}
    metadata_rows = [lookup["meta"] for lookup in lookups.values()]
    for record in factor_review.fillna("").to_dict("records"):
        trade_date = str(record.get("trade_date") or "")
        event_date = str(record.get("event_date") or "")
        relative_day = int(record.get("relative_day") or 0)
        ts_code = _normalize_ts_code(record.get("ts_code"))
        event_date_ts = pd.Timestamp(event_date) if event_date else None
        trade_date_ts = pd.Timestamp(trade_date) if trade_date else None
        event_non_trading = relative_day == 0 and event_date != trade_date

        has_dragon_v1_2 = False
        has_dragon_v1_3 = False
        has_industry_focus = False
        has_market_regime = False
        exact_date_match = False
        previous_trade_date_match = False
        next_trade_date_match = False
        within_3_trade_days_match = False
        matched_trade_date = ""
        case_event_in_range = False
        case_stock_exists_any_date = False
        case_stock_exists_on_nearby_dates = False
        code_format_possible = False
        any_file_present = bool(lookups)
        best_meta = metadata_rows[0] if metadata_rows else _diagnostics_metadata("missing", pd.DataFrame())

        for name, lookup in lookups.items():
            meta = lookup["meta"]
            if name.startswith("dragon_") and not case_event_in_range and meta["diagnostics_min_date"] and meta["diagnostics_max_date"]:
                case_event_in_range = meta["diagnostics_min_date"] <= trade_date <= meta["diagnostics_max_date"]
                best_meta = meta
            if lookup["data"].empty or "trade_date" not in lookup["data"].columns:
                continue
            if lookup["has_code"]:
                code_dates = lookup["code_dates"].get(ts_code, [])
                code_date_strings = lookup["code_date_strings"].get(ts_code, set())
                case_stock_exists_any_date = case_stock_exists_any_date or bool(code_dates)
                code_format_possible = code_format_possible or any(
                    ts_code.split(".")[0] in code for code in lookup["code_dates"].keys()
                )
                exact_rows = trade_date in code_date_strings
                if code_dates and trade_date_ts is not None:
                    pos = bisect_left(code_dates, trade_date_ts)
                    near_candidates = []
                    if pos > 0:
                        near_candidates.append(code_dates[pos - 1])
                    if pos < len(code_dates):
                        near_candidates.append(code_dates[pos])
                    if near_candidates:
                        deltas = [abs((candidate - trade_date_ts).days) for candidate in near_candidates]
                        min_delta = min(deltas)
                        case_stock_exists_on_nearby_dates = case_stock_exists_on_nearby_dates or min_delta <= 3
                        if not exact_rows:
                            within_3_trade_days_match = within_3_trade_days_match or min_delta <= 3
                            chosen = near_candidates[deltas.index(min_delta)]
                            matched_trade_date = matched_trade_date or chosen.strftime("%Y-%m-%d")
                            if chosen < trade_date_ts:
                                previous_trade_date_match = True
                            elif chosen > trade_date_ts:
                                next_trade_date_match = True
            else:
                exact_rows = trade_date in lookup["date_set"]
                if not exact_rows and trade_date_ts is not None:
                    dates = sorted(pd.to_datetime(list(lookup["date_set"])))
                    if dates:
                        pos = bisect_left(dates, trade_date_ts)
                        near_candidates = []
                        if pos > 0:
                            near_candidates.append(dates[pos - 1])
                        if pos < len(dates):
                            near_candidates.append(dates[pos])
                        if near_candidates:
                            deltas = [abs((candidate - trade_date_ts).days) for candidate in near_candidates]
                            min_delta = min(deltas)
                            within_3_trade_days_match = within_3_trade_days_match or min_delta <= 3
                            chosen = near_candidates[deltas.index(min_delta)]
                            matched_trade_date = matched_trade_date or chosen.strftime("%Y-%m-%d")
                            if chosen < trade_date_ts:
                                previous_trade_date_match = True
                            elif chosen > trade_date_ts:
                                next_trade_date_match = True
            if exact_rows:
                exact_date_match = True
                matched_trade_date = trade_date
                if event_non_trading and event_date_ts is not None and trade_date_ts is not None:
                    within_3_trade_days_match = abs((trade_date_ts - event_date_ts).days) <= 3
                if name == "dragon_v1_2":
                    has_dragon_v1_2 = True
                elif name == "dragon_v1_3":
                    has_dragon_v1_3 = True
                elif name == "industry_focus_v2":
                    has_industry_focus = True
                elif name == "market_regime":
                    has_market_regime = True
        final_alignment_status = "matched" if exact_date_match else ("nearby_match" if within_3_trade_days_match else "missing")
        if not any_file_present:
            final_missing_reason = "diagnostics_file_missing"
        elif not case_event_in_range and best_meta.get("diagnostics_min_date") and best_meta.get("diagnostics_max_date"):
            final_missing_reason = "outside_diagnostics_date_range"
        elif not case_stock_exists_any_date and any(lookup["has_code"] for lookup in lookups.values()):
            final_missing_reason = "code_format_mismatch" if code_format_possible else "stock_not_in_diagnostics_universe"
        elif not exact_date_match and event_non_trading and within_3_trade_days_match:
            final_missing_reason = "event_date_non_trading_day"
        elif not exact_date_match and (case_stock_exists_on_nearby_dates or case_stock_exists_any_date):
            final_missing_reason = "date_not_in_diagnostics"
        else:
            final_missing_reason = "unknown" if not exact_date_match else ""

        rows.append(
            {
                "case_id": f"curated_{str(record.get('web_candidate_id')).split('_')[-1]}",
                "web_candidate_id": record.get("web_candidate_id"),
                "ts_code": ts_code,
                "stock_name": record.get("stock_name"),
                "event_type": record.get("event_type"),
                "event_date": event_date,
                "relative_day": record.get("relative_day"),
                "trade_date": trade_date,
                "has_price_data": True,
                "has_dragon_v1_2": has_dragon_v1_2,
                "has_dragon_v1_3": has_dragon_v1_3,
                "has_industry_focus": has_industry_focus,
                "has_market_regime": has_market_regime,
                "matched_on_exact_date": relative_day == 0 and exact_date_match,
                "matched_on_nearest_previous_trade_date": relative_day == 0 and previous_trade_date_match,
                "matched_on_nearest_next_trade_date": relative_day == 0 and next_trade_date_match,
                "diagnostics_file": best_meta.get("diagnostics_file"),
                "diagnostics_min_date": best_meta.get("diagnostics_min_date"),
                "diagnostics_max_date": best_meta.get("diagnostics_max_date"),
                "diagnostics_has_ts_code": best_meta.get("diagnostics_has_ts_code"),
                "diagnostics_has_asset_id": best_meta.get("diagnostics_has_asset_id"),
                "diagnostics_date_granularity": best_meta.get("diagnostics_date_granularity"),
                "case_event_in_diagnostics_date_range": case_event_in_range,
                "case_stock_exists_in_diagnostics_any_date": case_stock_exists_any_date,
                "case_stock_exists_on_nearby_dates": case_stock_exists_on_nearby_dates,
                "exact_date_match": exact_date_match,
                "previous_trade_date_match": previous_trade_date_match,
                "next_trade_date_match": next_trade_date_match,
                "within_3_trade_days_match": within_3_trade_days_match,
                "matched_trade_date": matched_trade_date or None,
                "event_date_non_trading_day": bool(event_non_trading),
                "final_alignment_status": final_alignment_status,
                "final_missing_reason": final_missing_reason,
                "missing_reason": final_missing_reason,
            }
        )
    return pd.DataFrame(rows).reindex(columns=ALIGNMENT_AUDIT_COLUMNS)


def build_a_kill_rule_audit(verified_candidates: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    frame = _normalize_bars(bars)
    rows = []
    for record in verified_candidates.fillna("").to_dict("records"):
        ts_code = str(record.get("ts_code") or "")
        if not ts_code:
            continue
        asset_bars = frame[frame["ts_code"] == ts_code].copy()
        if asset_bars.empty:
            continue
        old_break = str(record.get("break_limit_date") or "")
        old_type = str(record.get("verified_case_type") or "")
        new_break = _refined_a_kill_event_date(asset_bars, old_break)
        new_type = old_type
        if old_type == "a_kill_failure" and identify_second_wave_start(asset_bars, new_break or old_break):
            new_type = "failed_then_recovered"
        old_metrics = _event_point_metrics(asset_bars, old_break)
        new_metrics = _event_point_metrics(asset_bars, new_break or old_break)
        rows.append(
            {
                "case_id": f"curated_{str(record.get('web_candidate_id')).split('_')[-1]}",
                "ts_code": ts_code,
                "stock_name": record.get("stock_name"),
                "old_event_date": old_break or None,
                "new_event_date": new_break or old_break or None,
                "old_verified_case_type": old_type,
                "new_verified_case_type": new_type,
                "old_future_5d_return": old_metrics["future_5d_return"],
                "new_future_5d_return": new_metrics["future_5d_return"],
                "old_future_10d_return": old_metrics["future_10d_return"],
                "new_future_10d_return": new_metrics["future_10d_return"],
                "old_future_10d_max_drawdown": old_metrics["future_10d_max_drawdown"],
                "new_future_10d_max_drawdown": new_metrics["future_10d_max_drawdown"],
                "rule_change_reason": "use_break_or_failed_rebound_confirmation_day",
            }
        )
    return pd.DataFrame(rows).reindex(columns=A_KILL_RULE_AUDIT_COLUMNS)


def _case_library_report(
    *,
    start_date: str,
    end_date: str,
    cases: pd.DataFrame,
    comparison: pd.DataFrame,
    event_diagnostics: pd.DataFrame,
    warnings: list[str],
) -> str:
    return "\n".join(
        [
            "# Dragon Case Library v1 报告",
            "",
            "## 1. 研究目标",
            f"区间：{start_date} 至 {end_date}。本轮目标是建立经典龙头案例库，不是直接证明策略收益。",
            "",
            "## 2. 案例库结构",
            "案例库包含 case_type、role、success_or_failure 和关键事件日期，用于把市场叙事转成可量化事件框架。",
            "",
            "## 3. 案例来源",
            f"手工 seed {len(cases[cases['source_type']=='seed'])} 个，自动候选 {len(cases[cases['source_type']=='auto'])} 个。",
            "",
            "## 4. 自动事件识别方法",
            "采用日线近似规则识别涨停、连板、断板、反包、二波和 A 杀。未接入分钟线与官方涨跌停价时，规则存在误差。",
            "",
            "## 5. 成功案例与失败案例",
            _table_preview(comparison, rows=16),
            "",
            "## 6. 关键事件日前后因子回看",
            f"事件回看样本 {len(event_diagnostics)} 行，用于观察关键事件前后 Dragon/行业因子变化，不用于直接生成交易信号。",
            "",
            "## 7. 对 Dragon Strategy 的启发",
            "案例库更适合回答：哪些事件前已经可识别，哪些失败案例有过热和退潮信号，哪些地方当前 Dragon 因子与真实案例不匹配。",
            "",
            "## 8. 下一步计划",
            "- 接入 Tushare `top_list` / `top_inst`。",
            "- 增加 5min 分时承接特征。",
            "- 扩充手工案例 seed，覆盖成功和失败反例。",
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _build_web_success_failure_comparison(
    curated: pd.DataFrame,
    factor_review: pd.DataFrame,
) -> pd.DataFrame:
    if curated.empty:
        return pd.DataFrame()
    event_zero = factor_review[factor_review["relative_day"] == 0].copy() if not factor_review.empty else pd.DataFrame()
    if not event_zero.empty:
        event_zero = (
            event_zero.groupby("web_candidate_id", as_index=False)[
                [
                    "future_3d_return",
                    "future_5d_return",
                    "future_10d_return",
                    "future_5d_max_drawdown",
                    "future_10d_max_drawdown",
                    "dragon_status_score",
                    "dragon_entry_score",
                    "dragon_risk_score",
                ]
            ]
            .mean(numeric_only=True)
        )
    merged = curated.merge(event_zero, left_on="web_candidate_id", right_on="web_candidate_id", how="left")
    rows = []
    for keys, group in merged.groupby(["case_year", "case_type", "verified_case_type", "success_or_failure"], dropna=False):
        rows.append(
            {
                "case_year": keys[0],
                "case_type": keys[1],
                "verified_case_type": keys[2],
                "success_or_failure": keys[3],
                "sample_count": int(len(group)),
                "avg_case_confidence_score": pd.to_numeric(group["case_confidence_score"], errors="coerce").mean(),
                "avg_verification_score": pd.to_numeric(group["verification_score"], errors="coerce").mean(),
                "avg_stage_return": pd.to_numeric(group["stage_return"], errors="coerce").mean(),
                "avg_max_drawdown": pd.to_numeric(group["max_drawdown"], errors="coerce").mean(),
                "avg_max_limit_up_count": pd.to_numeric(group["max_limit_up_count"], errors="coerce").mean(),
                "avg_future_3d_return": pd.to_numeric(group.get("future_3d_return"), errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(group.get("future_5d_return"), errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group.get("future_10d_return"), errors="coerce").mean(),
                "avg_future_5d_max_drawdown": pd.to_numeric(group.get("future_5d_max_drawdown"), errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group.get("future_10d_max_drawdown"), errors="coerce").mean(),
                "avg_dragon_status_score": pd.to_numeric(group.get("dragon_status_score"), errors="coerce").mean(),
                "avg_dragon_entry_score": pd.to_numeric(group.get("dragon_entry_score"), errors="coerce").mean(),
                "avg_dragon_risk_score": pd.to_numeric(group.get("dragon_risk_score"), errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows)


def _source_confidence(source_type: str) -> float:
    mapping = {
        "news": 0.80,
        "cls": 0.82,
        "caixin": 0.82,
        "eastmoney": 0.68,
        "stcn": 0.78,
        "sina": 0.70,
        "china_com": 0.60,
        "wallstreetcn": 0.72,
        "broker_report": 0.78,
        "public_article": 0.62,
        "manual_search_result": 0.60,
        "xueqiu": 0.55,
        "other": 0.50,
    }
    return mapping.get(str(source_type or "other"), 0.50)


def _article_source_confidence(record: dict[str, Any]) -> float:
    explicit = str(record.get("source_confidence") or "").strip()
    if explicit:
        try:
            return float(explicit)
        except ValueError:
            mapping = {
                "official_or_exchange": 1.0,
                "mainstream_media": 0.8,
                "financial_media": 0.7,
                "broker_report": 0.7,
                "community_article": 0.5,
                "self_media": 0.4,
                "unknown": 0.3,
            }
            return mapping.get(explicit, _source_confidence(str(record.get("source_type") or "")))
    return _source_confidence(str(record.get("source_type") or ""))


def _prepare_asset_lookup(asset_lookup: pd.DataFrame) -> dict[str, str]:
    if asset_lookup.empty:
        return {}
    frame = asset_lookup.copy()
    frame["stock_name"] = frame["stock_name"].fillna("").astype(str).str.strip()
    frame["ts_code"] = frame["ts_code"].fillna("").astype(str).str.strip()
    frame = frame[(frame["stock_name"] != "") & (frame["ts_code"] != "")]
    frame["normalized_stock_name"] = frame["stock_name"].map(_normalize_stock_name)
    return dict(zip(frame["normalized_stock_name"], frame["ts_code"], strict=False))


def _normalize_ts_code(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    if not text:
        return ""
    if ":" in text:
        parts = text.split(":")
        if len(parts) >= 3:
            code = parts[-1]
            exchange = parts[-2]
            if code and exchange:
                return f"{code}.{exchange}"
    if text.startswith(("SZ.", "SH.", "BJ.")):
        exchange, code = text.split(".", 1)
        return f"{code}.{exchange}"
    if "." not in text and len(text) >= 6:
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) == 6:
            exchange = "SH" if digits.startswith(("5", "6", "9")) else "SZ"
            return f"{digits}.{exchange}"
    return text


def _normalize_stock_name(name: object) -> str:
    text = unicodedata.normalize("NFKC", str(name or "")).upper().strip()
    for prefix in ["*ST", "ST", "*ＳＴ", "ＳＴ"]:
        if text.startswith(prefix):
            text = text[len(prefix):]
    for token in [" ", "\t", "-", "_", "*", "（", "）", "(", ")", ".", "·"]:
        text = text.replace(token, "")
    return text


def _possible_matches(stock_name: str, asset_lookup: pd.DataFrame) -> str:
    if asset_lookup.empty:
        return ""
    normalized = _normalize_stock_name(stock_name)
    frame = asset_lookup.copy()
    frame["normalized_stock_name"] = frame["stock_name"].fillna("").astype(str).map(_normalize_stock_name)
    candidates = frame[
        frame["normalized_stock_name"].str.contains(normalized, na=False)
        | pd.Series([normalized in value for value in frame["normalized_stock_name"]], index=frame.index)
    ][["stock_name", "ts_code"]].head(5)
    if candidates.empty:
        return ""
    return "|".join(f"{row.stock_name}:{row.ts_code}" for row in candidates.itertuples())


def _split_multi_value(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    normalized = text
    for separator in ["|", ",", ";", "，", "；", "、", "\n", "/"]:
        normalized = normalized.replace(separator, "|")
    return [part.strip() for part in normalized.split("|") if part.strip()]


def _build_web_seed_coverage(
    article_seed: pd.DataFrame,
    web_seed: pd.DataFrame,
    unmatched: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    article = article_seed.copy()
    article["year"] = pd.to_datetime(article["source_date"], errors="coerce").dt.year.astype("Int64").astype(str)
    matched = web_seed.copy()
    matched["year"] = pd.to_datetime(matched["source_date"], errors="coerce").dt.year.astype("Int64").astype(str)
    unmatched_frame = unmatched.copy()
    unmatched_frame["year"] = pd.to_datetime(unmatched_frame["source_date"], errors="coerce").dt.year.astype("Int64").astype(str)
    keys = sorted(set(article["year"].tolist()) | set(matched["year"].tolist()) | set(unmatched_frame["year"].tolist()))
    for year in keys:
        for source_type in sorted(set(article.loc[article["year"] == year, "source_type"].astype(str)) | set(matched.loc[matched["year"] == year, "source_type"].astype(str)) | set(unmatched_frame.loc[unmatched_frame["year"] == year, "source_type"].astype(str))):
            article_group = article[(article["year"] == year) & (article["source_type"].astype(str) == source_type)]
            matched_group = matched[(matched["year"] == year) & (matched["source_type"].astype(str) == source_type)]
            unmatched_group = unmatched_frame[(unmatched_frame["year"] == year) & (unmatched_frame["source_type"].astype(str) == source_type)]
            if article_group.empty and matched_group.empty and unmatched_group.empty:
                continue
            case_dist = matched_group["case_type"].value_counts().to_dict() if "case_type" in matched_group.columns else {}
            rows.append(
                {
                    "year": year,
                    "source_type": source_type,
                    "article_count": int(article_group["article_id"].astype(str).nunique()) if "article_id" in article_group.columns else int(len(article_group)),
                    "stock_seed_count": int(len(matched_group) + len(unmatched_group)),
                    "matched_stock_count": int(len(matched_group)),
                    "unmatched_stock_count": int(len(unmatched_group)),
                    "average_source_confidence": pd.to_numeric(matched_group.get("source_confidence"), errors="coerce").mean(),
                    "case_type_distribution": str(case_dist),
                }
            )
    return pd.DataFrame(rows).reindex(columns=WEB_SEED_COVERAGE_COLUMNS)


def _refined_a_kill_event_date(asset_bars: pd.DataFrame, old_break_date: str | None) -> str | None:
    frame = _normalize_bars(asset_bars)
    if frame.empty:
        return old_break_date
    if old_break_date:
        start = frame[frame["trade_date"] >= old_break_date].head(5)
    else:
        start = frame.head(5)
    if start.empty:
        return old_break_date
    for _, row in start.iterrows():
        if _float(row.get("daily_return")) <= -0.07:
            return _safe_date(row["trade_date"])
    return old_break_date


def _event_point_metrics(asset_bars: pd.DataFrame, event_date: str | None) -> dict[str, float | None]:
    if asset_bars.empty or not event_date:
        return {
            "future_5d_return": None,
            "future_10d_return": None,
            "future_10d_max_drawdown": None,
        }
    frame = _normalize_bars(asset_bars).reset_index(drop=True)
    matches = frame.index[frame["trade_date"] == event_date]
    if len(matches) == 0:
        return {
            "future_5d_return": None,
            "future_10d_return": None,
            "future_10d_max_drawdown": None,
        }
    idx = int(matches[0])
    metrics = _future_window_metrics(frame, idx)
    return {
        "future_5d_return": metrics.get("future_5d_return"),
        "future_10d_return": metrics.get("future_10d_return"),
        "future_10d_max_drawdown": metrics.get("future_10d_max_drawdown"),
    }


def _verified_case_type(
    *,
    asset_bars: pd.DataFrame | None = None,
    summary: dict[str, Any],
    break_limit_date: str | None,
    reversal_date: str | None,
    second_wave_start_date: str | None,
    a_kill_start_date: str | None,
) -> str:
    max_limit = int(summary.get("max_limit_up_count") or 0)
    stage_return = _float(summary.get("stage_return"))
    failed_reversal = identify_failed_reversal(asset_bars, break_limit_date, reversal_date) if asset_bars is not None else None
    failed_second_wave = identify_failed_second_wave(asset_bars, second_wave_start_date) if asset_bars is not None else None
    one_day_pump = identify_one_day_pump(asset_bars, summary.get("first_limit_up_date"), max_limit) if asset_bars is not None else None
    if failed_second_wave:
        return "failed_second_wave"
    if failed_reversal:
        return "failed_reversal"
    if one_day_pump:
        return "one_day_pump"
    if a_kill_start_date and not second_wave_start_date:
        return "a_kill_failure"
    if second_wave_start_date:
        return "second_wave"
    if reversal_date:
        return "break_then_reversal"
    if max_limit >= 2:
        return "continuous_limit_up"
    if summary.get("first_limit_up_date") and stage_return < 0.20 and break_limit_date:
        return "one_day_pump"
    if summary.get("first_limit_up_date"):
        return "weak_to_strong"
    return ""


def _verification_score(
    *,
    claimed_case_type: str,
    verified_case_type: str,
    summary: dict[str, Any],
    reversal_date: str | None,
    second_wave_start_date: str | None,
    a_kill_start_date: str | None,
) -> float:
    score = 0.0
    if verified_case_type:
        score += 0.40
    if claimed_case_type and claimed_case_type == verified_case_type:
        score += 0.30
    if int(summary.get("max_limit_up_count") or 0) >= 2:
        score += 0.10
    if reversal_date or second_wave_start_date or a_kill_start_date:
        score += 0.20
    return min(1.0, score)


def _verification_reason(claimed_case_type: str, verified_case_type: str) -> str:
    if not verified_case_type:
        return "no local event pattern verified"
    if claimed_case_type == verified_case_type:
        return "claimed case type matched local event pattern"
    return f"claimed {claimed_case_type} but local event pattern looked like {verified_case_type}"


def _web_case_report(
    *,
    verified: pd.DataFrame,
    curated: pd.DataFrame,
    factor_review: pd.DataFrame,
    comparison: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    matching_summary: pd.DataFrame,
    factor_snapshot: pd.DataFrame,
    web_search_targets: pd.DataFrame,
    failure_target_audit: pd.DataFrame,
    local_source_priority: pd.DataFrame,
    article_seed_suggestions: pd.DataFrame,
    source_backfill_tasks: pd.DataFrame,
    a_kill_rule_audit: pd.DataFrame,
    warnings: list[str],
) -> str:
    aligned = 0
    if not factor_review.empty:
        aligned = int(
            factor_review[["dragon_status_score", "dragon_entry_score", "dragon_risk_score", "industry_focus_score_v2"]]
            .notna()
            .any(axis=1)
            .sum()
        )
    return "\n".join(
        [
            "# Dragon Case Library 2024–2026 网络线索验证报告",
            "",
            "## 1. 研究目标",
            "本轮先不做人工复核，用网络线索 + 本地行情事件 + Dragon 因子对齐生成高置信案例库。",
            "",
            "## 2. 数据来源",
            "使用 web seed 导入新闻/东方财富/财联社等 URL 和标题线索；不复制社区全文内容。",
            "",
            "## 3. 本地事件验证方法",
            "用日线近似识别涨停、连板、断板、反包、二波、A杀、一日游，并生成 verification_score。",
            "",
            "## 4. 高置信案例库",
            f"总候选 {len(verified)}，验证通过 {int(pd.to_numeric(verified['event_verified'], errors='coerce').fillna(False).sum())}，curated {len(curated)}。",
            "",
            "## Seed 扩充结果",
            _seed_expansion_note(curated),
            "",
            "## 事件类型分布",
            _verified_distribution_note(verified),
            "",
            "## 为什么匹配这么少",
            _matching_summary_note(matching_summary),
            _table_preview(matching_summary, rows=12),
            "",
            "## 5. Dragon 因子回看",
            f"事件回看总行数 {len(factor_review)}，其中实际对齐到 Dragon/行业因子的事件行 {aligned}。",
            "",
            "## Factor Alignment Audit",
            _factor_alignment_note(alignment_audit),
            _table_preview(alignment_audit, rows=16),
            "",
            "## Factor Alignment 修复结果",
            _factor_alignment_fix_note(alignment_audit),
            "",
            "## Case Factor Snapshot",
            f"轻量案例快照 {len(factor_snapshot)} 行，覆盖 {int(factor_snapshot.get('case_id', pd.Series(dtype='object')).astype(str).nunique()) if not factor_snapshot.empty else 0} 个案例。future 字段仅用于事后诊断，不用于策略信号。",
            "",
            "## Web Search Targets",
            _web_search_target_note(web_search_targets),
            _table_preview(web_search_targets, rows=16),
            "",
            "## Failure Target Expansion",
            _failure_target_note(failure_target_audit),
            _table_preview(failure_target_audit, rows=16),
            "",
            "## Local Candidate Source Priority",
            _local_source_priority_note(local_source_priority),
            _table_preview(local_source_priority, rows=16),
            "",
            "## Article Seed Suggestions",
            _article_seed_suggestions_note(article_seed_suggestions),
            _table_preview(article_seed_suggestions, rows=16),
            "",
            "## Source Backfill Tasks",
            _source_backfill_tasks_note(source_backfill_tasks),
            _table_preview(source_backfill_tasks, rows=16),
            "",
            "## A Kill Rule Audit",
            _a_kill_rule_note(a_kill_rule_audit),
            _table_preview(a_kill_rule_audit, rows=16),
            "",
            "## 6. 成功与失败初步差异",
            _table_preview(comparison, rows=16),
            "",
            "## 7. 是否需要人工复核",
            "当前全部保留 `review_status=pending`。后续只建议抽查高置信或争议案例。",
            "",
            "## 8. 下一步",
            "- 扩充 web seed。",
            "- 接入 Tushare `top_list` / `top_inst`。",
            "- 接入 5min 分时承接。",
            "",
            "## 是否可以接龙虎榜",
            _web_lhb_readiness_note(curated, alignment_audit, comparison),
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _web_seed_expansion_report(
    article_seed: pd.DataFrame,
    web_seed: pd.DataFrame,
    unmatched: pd.DataFrame,
    coverage: pd.DataFrame,
) -> str:
    year_lines = []
    if not web_seed.empty:
        years = pd.to_datetime(web_seed["source_date"], errors="coerce").dt.year.fillna(0).astype(int)
        for year, count in years.value_counts().sort_index().items():
            year_lines.append(f"{year}: {count}")
    return "\n".join(
        [
            "# Dragon Case Web Seed Expansion v1 报告",
            "",
            "## 1. 背景",
            "当前 web seed 很少，框架已跑通但样本不足，需要先扩充结构化网络线索。",
            "",
            "## 2. Article Seed 结构",
            "article-level seed 保存文章标题、URL、来源、日期、提及股票、题材和案例类型，再拆成 stock-level web seed。",
            "",
            "## 3. 初始线索覆盖",
            "；".join(year_lines) if year_lines else "暂无 article seed 样本。",
            "",
            "## 4. 来源置信度",
            "source_confidence 优先用显式值；缺失时按 source_type 映射。",
            "",
            "## 5. 匹配结果",
            f"匹配成功 {len(web_seed)}，未匹配 {len(unmatched)}。",
            "",
            "## 6. 后续验证",
            "扩充后应继续运行 `dragon-case-import-web-seeds` 和 `dragon-case-web-verify`。",
            "",
            "## 7. 合规说明",
            "不抓取全文，不做批量爬虫，只保存标题、URL、来源和结构化线索。",
            "",
            _table_preview(coverage, rows=20),
        ]
    )


def _seed_expansion_note(curated: pd.DataFrame) -> str:
    if curated.empty:
        return "暂无 curated 案例。"
    counts = curated["case_year"].value_counts().sort_index()
    return "；".join(f"{year}: {count}" for year, count in counts.items())


def _verified_distribution_note(verified: pd.DataFrame) -> str:
    if verified.empty:
        return "暂无 verified 样本。"
    counts = verified["verified_case_type"].value_counts()
    return "；".join(f"{name}: {count}" for name, count in counts.items())


def _matching_summary_note(matching_summary: pd.DataFrame) -> str:
    if matching_summary.empty:
        return "暂无 matching summary。"
    parts = []
    for row in matching_summary.to_dict("records"):
        parts.append(
            f"{row['match_stage']}={int(row['matched_count'])}/{int(row['total_count'])}, missing={row['main_missing_reason'] or 'none'}"
        )
    return "；".join(parts)


def _factor_alignment_note(alignment_audit: pd.DataFrame) -> str:
    if alignment_audit.empty:
        return "暂无 alignment audit。"
    key_rows = alignment_audit[alignment_audit["relative_day"] == 0].copy()
    base = key_rows if not key_rows.empty else alignment_audit
    total = len(base)
    aligned = int(
        base[["has_dragon_v1_2", "has_dragon_v1_3", "has_industry_focus", "has_market_regime"]]
        .any(axis=1)
        .sum()
    )
    reasons = base["missing_reason"].replace("", pd.NA).dropna().value_counts().head(5).to_dict()
    return f"关键事件对齐率 {aligned}/{total}；主要缺失原因 {reasons}。"


def _factor_alignment_fix_note(alignment_audit: pd.DataFrame) -> str:
    if alignment_audit.empty:
        return "暂无 factor alignment fix 结果。"
    key_rows = alignment_audit[alignment_audit["relative_day"] == 0].copy()
    base = key_rows if not key_rows.empty else alignment_audit
    exact = int(pd.to_numeric(base.get("exact_date_match"), errors="coerce").fillna(False).astype(bool).sum())
    prev_match = int(pd.to_numeric(base.get("previous_trade_date_match"), errors="coerce").fillna(False).astype(bool).sum())
    next_match = int(pd.to_numeric(base.get("next_trade_date_match"), errors="coerce").fillna(False).astype(bool).sum())
    within3 = int(pd.to_numeric(base.get("within_3_trade_days_match"), errors="coerce").fillna(False).astype(bool).sum())
    return f"exact={exact}；previous={prev_match}；next={next_match}；within_3_trade_days={within3}。"


def _a_kill_rule_note(a_kill_rule_audit: pd.DataFrame) -> str:
    if a_kill_rule_audit.empty:
        return "暂无 A 杀审计样本。"
    changed = a_kill_rule_audit[a_kill_rule_audit["old_event_date"] != a_kill_rule_audit["new_event_date"]]
    return f"A 杀规则审计样本 {len(a_kill_rule_audit)}，事件点调整 {len(changed)} 条。"


def _web_lhb_readiness_note(
    curated: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    comparison: pd.DataFrame,
) -> str:
    if len(curated) < 50:
        return "curated library 仍少于 50 条，先继续扩 seed。"
    aligned = 0.0
    if not alignment_audit.empty:
        aligned = float(
            alignment_audit[["has_dragon_v1_2", "has_dragon_v1_3", "has_industry_focus", "has_market_regime"]]
            .any(axis=1)
            .mean()
        )
    if aligned < 0.5:
        return "关键事件因子对齐率低于 50%，先修对齐。"
    if "success_or_failure" in comparison.columns:
        failures = int((comparison["success_or_failure"] == "failure").sum())
        if failures < 5:
            return "失败样本仍不足，先补失败线索。"
    return "样本量、对齐率和失败样本都改善后，才建议进入龙虎榜。"


def _web_search_target_note(web_search_targets: pd.DataFrame) -> str:
    if web_search_targets.empty:
        return "暂无本地 auto candidate 生成的搜索目标。"
    counts = (
        web_search_targets.groupby(["case_year", "suggested_case_type"])
        .size()
        .reset_index(name="count")
        .sort_values(["case_year", "suggested_case_type"])
    )
    parts = [
        f"{int(row.case_year)}-{row.suggested_case_type}:{int(row.count)}"
        for row in counts.itertuples()
    ]
    return f"共 {len(web_search_targets)} 条待搜索目标；" + "；".join(parts)


def _failure_target_note(failure_target_audit: pd.DataFrame) -> str:
    if failure_target_audit.empty:
        return "暂无失败目标。"
    counts = (
        failure_target_audit.groupby(["case_year", "suggested_case_type"])
        .size()
        .reset_index(name="count")
        .sort_values(["case_year", "suggested_case_type"])
    )
    parts = [
        f"{int(row.case_year)}-{row.suggested_case_type}:{int(row.count)}"
        for row in counts.itertuples()
    ]
    return f"新增失败目标 {len(failure_target_audit)} 条；" + "；".join(parts)


def _local_source_priority_note(local_source_priority: pd.DataFrame) -> str:
    if local_source_priority.empty:
        return "暂无 local_auto_candidate 补证优先级。"
    top = local_source_priority.head(5)[["stock_name", "verified_case_type", "source_priority_score"]]
    return f"local_auto_candidate 补证优先级 {len(local_source_priority)} 条；Top5: " + "; ".join(
        f"{row.stock_name}/{row.verified_case_type}/{row.source_priority_score:.2f}" for row in top.itertuples()
    )


def _article_seed_suggestions_note(article_seed_suggestions: pd.DataFrame) -> str:
    if article_seed_suggestions.empty:
        return "暂无 article seed 建议包。"
    return (
        f"生成 {len(article_seed_suggestions)} 条 article seed 建议；"
        "保留查询词和模板行，等待人工补 source_url，不自动抓取全文。"
    )


def _source_backfill_tasks_note(source_backfill_tasks: pd.DataFrame) -> str:
    if source_backfill_tasks.empty:
        return "暂无 source backfill 任务。"
    counts = (
        source_backfill_tasks.groupby(["case_year", "suggested_case_type"])
        .size()
        .reset_index(name="count")
        .sort_values(["case_year", "suggested_case_type"])
    )
    parts = [
        f"{int(row.case_year)}-{row.suggested_case_type}:{int(row.count)}"
        for row in counts.itertuples()
    ]
    return f"共 {len(source_backfill_tasks)} 条待补证任务；" + "；".join(parts)


def _table_preview(frame: pd.DataFrame, rows: int = 12) -> str:
    if frame.empty:
        return "无可用样本。"
    return frame.head(rows).to_markdown(index=False)


def _daily_return_at(ordered: pd.DataFrame, idx: int) -> float | None:
    if idx <= 0:
        return None
    prev_close = _float(ordered.iloc[idx - 1]["close"])
    close = _float(ordered.iloc[idx]["close"])
    return close / prev_close - 1.0 if prev_close else None


def _year_of(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    return int(text[:4])


def _business_day_distance(start_date: str | None, end_date: str | None) -> int | None:
    if not start_date or not end_date:
        return None
    return max(0, len(pd.bdate_range(start_date, end_date)) - 1)


def _safe_date(value: object) -> str | None:
    if value is None or value == "":
        return None
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _asset_id_to_ts_code(asset_id: str) -> str:
    text = str(asset_id or "")
    parts = text.split(":")
    if len(parts) == 3:
        exchange = parts[1]
        code = parts[2]
        suffix = "SH" if exchange == "SH" else "SZ" if exchange == "SZ" else exchange
        return f"{code}.{suffix}"
    return text


def _ts_code_to_asset_id(ts_code: str) -> str:
    text = str(ts_code or "")
    if "." not in text:
        return text
    code, exchange = text.split(".", 1)
    market = "SH" if exchange.upper() == "SH" else "SZ"
    return f"CN:{market}:{code}"


def _date_windows(start_date: str, end_date: str, *, months: int) -> list[tuple[str, str]]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    windows: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + pd.DateOffset(months=months) - pd.Timedelta(days=1), end)
        windows.append((cursor.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d")))
        cursor = window_end + pd.Timedelta(days=1)
    return windows


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _optional_usecols(name: str) -> set[str]:
    common = {
        "trade_date",
        "asset_id",
        "ts_code",
        "industry_name",
        "industry_focus_score_v2",
        "industry_rank",
        "market_regime",
        "dragon_status_score",
        "dragon_entry_score",
        "dragon_entry_score_v2",
        "dragon_risk_score",
        "entry_window",
        "entry_window_v2",
        "dragon_role",
    }
    if name in {"industry_mainline_regime", "market_regime"}:
        return {"trade_date", "market_regime", "industry_name", "industry_focus_score_v2", "industry_rank"}
    return common


def _float(value: object) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
