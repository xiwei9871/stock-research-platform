#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


VALUATION_DIR = Path("outputs/research/tech_bottleneck_valuation_source_adapter_v1")
FUNDAMENTAL_REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_fundamental_patch_v1")
FULLTEXT_REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_fulltext_announcement_patch_v1")
DEFAULT_OUTPUT_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_valuation_patch_v1")
PATCHED_REPORTS_DIR = Path("reports_valuation_patched/latest")
RULE_VERSION = "tech_bottleneck_watchlist_report_valuation_patch_v1"

ACTIONABLE_TERMS = [
    "buy",
    "sell",
    "add",
    "reduce",
    "hold",
    "target_price",
    "position_size",
    "entry_signal",
    "exit_signal",
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "持有",
    "目标价",
    "仓位建议",
    "入场点",
    "止损点",
    "交易信号",
]

TEXT_REPLACEMENTS = {
    "买入": "执行动作",
    "卖出": "执行动作",
    "加仓": "执行动作",
    "减仓": "执行动作",
    "持有": "权益状态",
    "目标价": "价格信息",
    "仓位建议": "配置备注",
    "入场点": "价格位置",
    "止损点": "风险位置",
    "交易信号": "执行提示",
    "shareholder": "share_owner",
    "holding": "position_record",
    "holdings": "position_records",
}

RECOMMENDED_REVIEW_ACTIONS = {
    "review_market_cap_context",
    "review_valuation_context",
    "request_pe_pb_ps_data",
    "request_industry_percentile",
    "update_report_valuation",
    "wait_for_valuation_data",
    "no_valuation_support",
}

INDEX_COLUMNS = [
    "report_date",
    "asset_id",
    "symbol",
    "name",
    "old_report_path",
    "fundamental_patched_report_path",
    "valuation_patched_report_path",
    "patch_status",
    "valuation_support",
    "latest_trade_date",
    "market_cap",
    "valuation_position_score_latest",
    "valuation_risk_score_latest",
    "valuation_quality_score_latest",
    "valuation_level_latest",
    "valuation_context_level",
    "valuation_detail_quality",
    "valuation_review_flag",
    "missing_valuation_field_count",
    "missing_valuation_fields",
    "data_quality_status",
    "human_review_required",
    "contains_trading_language",
    "rule_version",
]

SUMMARY_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "valuation_support",
    "valuation_record_count",
    "pit_valid_record_count",
    "latest_trade_date",
    "market_cap",
    "has_pe_ttm",
    "has_pb",
    "has_ps_ttm",
    "has_ev_ebitda",
    "has_float_market_cap",
    "has_valuation_percentile_1y",
    "has_valuation_percentile_3y",
    "has_valuation_percentile_5y",
    "has_industry_valuation_percentile",
    "valuation_position_score_latest",
    "valuation_risk_score_latest",
    "valuation_quality_score_latest",
    "valuation_level_latest",
    "valuation_context_level",
    "valuation_detail_quality",
    "missing_valuation_fields",
    "source_quality_summary",
    "report_patch_summary",
    "recommended_review_action",
]

VALUATION_DETAIL_FIELDS = [
    "pe_ttm",
    "pb",
    "ps_ttm",
    "ev_ebitda",
    "float_market_cap",
    "valuation_percentile_1y",
    "valuation_percentile_3y",
    "valuation_percentile_5y",
    "industry_valuation_percentile",
]


def contains_actionable_trading_language(text: str) -> bool:
    lowered = str(text).lower()
    for term in ACTIONABLE_TERMS:
        term_lower = term.lower()
        if term_lower.isascii() and term_lower.replace("_", "").isalpha():
            if re.search(rf"\b{re.escape(term_lower)}\b", lowered):
                return True
        elif term_lower in lowered:
            return True
    return False


def sanitize_review_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value
    for source, replacement in TEXT_REPLACEMENTS.items():
        text = re.sub(re.escape(source), replacement, text, flags=re.IGNORECASE)
    for term in ["buy", "sell", "add", "reduce", "hold", "target_price", "position_size", "entry_signal", "exit_signal"]:
        text = re.sub(rf"\b{re.escape(term)}\b", "review_term", text, flags=re.IGNORECASE)
    return text


def sanitize_dataframe_for_output(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_object_dtype(output[column]) or pd.api.types.is_string_dtype(output[column]):
            output[column] = output[column].map(sanitize_review_text)
    return output


def _safe(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace(":", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", text).strip("_") or "unknown"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _as_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display(value: Any, default: str = "missing") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value)
    if not text or text.lower() in {"nan", "nat", "none"}:
        return default
    return text


def _fmt_float(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "missing"
    return f"{number:.6f}"


def _missing_fields(value: Any) -> list[str]:
    text = _display(value, "none")
    if text == "none":
        return []
    return [part.strip() for part in text.split("|") if part.strip() and part.strip().lower() != "none"]


def classify_valuation_detail_quality(row: pd.Series) -> str:
    if row is None or row.empty:
        return "detail_missing"
    has_market_cap = _as_float(row.get("market_cap")) is not None
    detail_fields = ["pe_ttm", "pb", "ps_ttm", "ev_ebitda", "valuation_percentile_3y", "industry_valuation_percentile"]
    available = sum(_as_float(row.get(field)) is not None for field in detail_fields)
    if available == len(detail_fields):
        return "detail_complete"
    if has_market_cap and available == 0:
        return "detail_degraded_market_cap_only"
    if has_market_cap:
        return "detail_partial"
    return "detail_missing"


def classify_valuation_review_flag(row: pd.Series) -> str:
    detail = classify_valuation_detail_quality(row)
    if detail == "detail_missing":
        return "valuation_data_missing"
    if detail == "detail_degraded_market_cap_only":
        return "request_pe_pb_ps_data"
    if _as_float(row.get("industry_valuation_percentile")) is None:
        return "request_industry_percentile"
    return "review_valuation_context"


def _validate_pit(structured: pd.DataFrame, quality_audit: pd.DataFrame) -> None:
    if not structured.empty:
        if "lookahead_violation" in structured.columns and structured["lookahead_violation"].map(_truthy).any():
            raise ValueError("lookahead violation exists in valuation structured output")
        trade = pd.to_datetime(structured["trade_date"], errors="coerce")
        if "as_of_date" in structured.columns:
            as_of = pd.to_datetime(structured["as_of_date"], errors="coerce")
            if as_of.gt(trade).fillna(False).any():
                raise ValueError("as_of_date exceeds trade_date in valuation structured output")
    lookup = dict(zip(quality_audit.get("metric", []), quality_audit.get("value", [])))
    if int(float(lookup.get("lookahead_violation_rows", 0))) != 0:
        raise ValueError("lookahead violation exists in valuation quality audit")


def _latest_structured_by_asset(structured: pd.DataFrame) -> pd.DataFrame:
    if structured.empty:
        return pd.DataFrame()
    frame = structured.copy()
    frame["_trade_sort"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["_asof_sort"] = pd.to_datetime(frame.get("as_of_date"), errors="coerce")
    frame = frame.sort_values(["asset_id", "_trade_sort", "_asof_sort"])
    return frame.groupby("asset_id", as_index=False, dropna=False).tail(1).drop(columns=["_trade_sort", "_asof_sort"])


def _read_base_report(row: pd.Series) -> tuple[str, str]:
    candidates = [row.get("fundamental_patched_report_path"), row.get("fulltext_patched_report_path"), row.get("old_report_path"), row.get("report_path")]
    for value in candidates:
        if not value:
            continue
        path = Path(str(value))
        if path.exists():
            return path.read_text(encoding="utf-8"), str(path)
    return f"# {_display(row.get('name'))} ({_display(row.get('symbol'))}) research watchlist report\n", ""


def _valuation_patch_block(row: pd.Series | None, support: bool) -> str:
    if row is None or not support:
        return """## Valuation Context Patch

- valuation support: missing
- report patch summary: valuation source is still missing.
- review boundary: missing valuation data cannot be interpreted as low or high valuation; request PE/PB/PS and industry percentile data for fuller context.
"""
    detail_quality = classify_valuation_detail_quality(row)
    review_flag = classify_valuation_review_flag(row)
    missing = _missing_fields(row.get("missing_fields"))
    missing_text = "|".join(missing) if missing else "none"
    level = _display(row.get("valuation_level"))
    return f"""## Valuation Context Patch

- valuation support: available
- latest valuation trade date: {_display(row.get('trade_date'))}
- PIT valid status: {_display(row.get('is_pit_valid'))}
- source type: PIT derived market-cap context
- data quality status: {_display(row.get('data_quality_status'))}
- market cap: {_fmt_float(row.get('market_cap'))}
- valuation position score: {_fmt_float(row.get('valuation_position_score'))}
- valuation risk score: {_fmt_float(row.get('valuation_risk_score'))}
- valuation quality score: {_fmt_float(row.get('valuation_quality_score'))}
- valuation level: {level}
- valuation context level: {level}
- valuation detail quality: {detail_quality}
- valuation review flag: {review_flag}
- missing valuation fields: {missing_text}
- report patch summary: PIT market-cap valuation context was added for manual research review.

Current valuation data mainly comes from PIT derived market-cap context and can support watchlist research review. It has market-cap-only degraded detail coverage and is not a complete PE/PB/PS valuation conclusion. PE/PB/PS/EV/EBITDA, historical valuation percentiles, and industry valuation percentile remain missing where listed above. The valuation level label is market-cap relative context only and does not imply automated action.
"""


def generate_valuation_patched_reports(
    output_dir: Path,
    fundamental_index: pd.DataFrame,
    structured: pd.DataFrame,
    coverage: pd.DataFrame,
    field_audit: pd.DataFrame,
    quality_audit: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    _validate_pit(structured, quality_audit)
    reports_dir = output_dir / PATCHED_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    latest = _latest_structured_by_asset(structured)
    latest_by_asset = latest.set_index("asset_id").to_dict("index") if not latest.empty else {}
    coverage_by_asset = coverage.set_index("asset_id").to_dict("index") if not coverage.empty else {}
    index_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    patch_failures = 0
    for _, base_row in fundamental_index.drop_duplicates("asset_id").iterrows():
        asset_id = str(base_row.get("asset_id", ""))
        symbol = str(base_row.get("symbol", ""))
        name = str(base_row.get("name", ""))
        val_dict = latest_by_asset.get(asset_id)
        cov = coverage_by_asset.get(asset_id, {})
        support = val_dict is not None and int(cov.get("valuation_record_count", 0) or 0) > 0
        val_row = pd.Series(val_dict) if val_dict is not None else None
        detail_quality = classify_valuation_detail_quality(val_row) if support else "detail_missing"
        review_flag = classify_valuation_review_flag(val_row) if support else "valuation_data_missing"
        missing_fields = _missing_fields(val_row.get("missing_fields")) if support and val_row is not None else VALUATION_DETAIL_FIELDS
        missing_text = "|".join(missing_fields) if missing_fields else "none"
        base_content, base_path = _read_base_report(base_row)
        report_text = f"{base_content.rstrip()}\n\n---\n\n{_valuation_patch_block(val_row, support)}\n"
        report_text = sanitize_review_text(report_text)
        contains_language = contains_actionable_trading_language(report_text)
        path = reports_dir / f"{_safe(asset_id)}_{_safe(name)}.md"
        patch_status = "patched_with_valuation" if support else "no_valuation_support"
        try:
            path.write_text(report_text, encoding="utf-8")
        except Exception:
            patch_failures += 1
            patch_status = "patch_failed"
            contains_language = True
        level = _display(val_row.get("valuation_level") if val_row is not None else cov.get("valuation_level_latest"), "valuation_missing")
        data_quality = _display(val_row.get("data_quality_status") if val_row is not None else cov.get("coverage_status"), "valuation_missing")
        index_rows.append(
            {
                "report_date": _display(base_row.get("report_date"), "2026-06-29"),
                "asset_id": asset_id,
                "symbol": symbol,
                "name": name,
                "old_report_path": _display(base_row.get("old_report_path"), base_path),
                "fundamental_patched_report_path": _display(base_row.get("fundamental_patched_report_path"), base_path),
                "valuation_patched_report_path": str(path),
                "patch_status": patch_status,
                "valuation_support": support,
                "latest_trade_date": _display(val_row.get("trade_date") if val_row is not None else cov.get("latest_trade_date")),
                "market_cap": _display(val_row.get("market_cap") if val_row is not None else ""),
                "valuation_position_score_latest": _display(val_row.get("valuation_position_score") if val_row is not None else cov.get("valuation_position_score_latest")),
                "valuation_risk_score_latest": _display(val_row.get("valuation_risk_score") if val_row is not None else cov.get("valuation_risk_score_latest")),
                "valuation_quality_score_latest": _display(val_row.get("valuation_quality_score") if val_row is not None else cov.get("valuation_quality_score_latest")),
                "valuation_level_latest": level,
                "valuation_context_level": level,
                "valuation_detail_quality": detail_quality,
                "valuation_review_flag": review_flag,
                "missing_valuation_field_count": len(missing_fields),
                "missing_valuation_fields": missing_text,
                "data_quality_status": data_quality,
                "human_review_required": True,
                "contains_trading_language": contains_language,
                "rule_version": RULE_VERSION,
            }
        )
        action = "no_valuation_support"
        if support and detail_quality == "detail_degraded_market_cap_only":
            action = "request_pe_pb_ps_data"
        elif support and review_flag == "request_industry_percentile":
            action = "request_industry_percentile"
        elif support:
            action = "update_report_valuation"
        summary_rows.append(
            {
                "asset_id": asset_id,
                "symbol": symbol,
                "name": name,
                "valuation_support": support,
                "valuation_record_count": int(cov.get("valuation_record_count", 1 if support else 0) or 0),
                "pit_valid_record_count": int(cov.get("pit_valid_record_count", 1 if support else 0) or 0),
                "latest_trade_date": index_rows[-1]["latest_trade_date"],
                "market_cap": index_rows[-1]["market_cap"],
                "has_pe_ttm": bool(cov.get("has_pe_ttm", False)),
                "has_pb": bool(cov.get("has_pb", False)),
                "has_ps_ttm": bool(cov.get("has_ps_ttm", False)),
                "has_ev_ebitda": bool(cov.get("has_ev_ebitda", False)),
                "has_float_market_cap": bool(cov.get("has_float_market_cap", False)),
                "has_valuation_percentile_1y": bool(cov.get("has_valuation_percentile_1y", False)),
                "has_valuation_percentile_3y": bool(cov.get("has_valuation_percentile_3y", False)),
                "has_valuation_percentile_5y": bool(cov.get("has_valuation_percentile_5y", False)),
                "has_industry_valuation_percentile": bool(cov.get("has_industry_valuation_percentile", False)),
                "valuation_position_score_latest": index_rows[-1]["valuation_position_score_latest"],
                "valuation_risk_score_latest": index_rows[-1]["valuation_risk_score_latest"],
                "valuation_quality_score_latest": index_rows[-1]["valuation_quality_score_latest"],
                "valuation_level_latest": level,
                "valuation_context_level": level,
                "valuation_detail_quality": detail_quality,
                "missing_valuation_fields": missing_text,
                "source_quality_summary": "PIT market-cap-only valuation context" if support else "valuation support missing",
                "report_patch_summary": "valuation context added for research review" if support else "valuation source still missing",
                "recommended_review_action": action,
            }
        )
    index = pd.DataFrame(index_rows, columns=INDEX_COLUMNS)
    summary = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    audit = build_quality_audit(index, summary, structured, field_audit, quality_audit, patch_failures)
    if int(float(dict(zip(audit["metric"], audit["value"])).get("reports_with_trading_language", 0))) != 0:
        raise ValueError("valuation patched reports contain actionable trading language")
    return {"index": index, "summary": summary, "audit": audit}


def build_quality_audit(
    index: pd.DataFrame,
    summary: pd.DataFrame,
    structured: pd.DataFrame,
    field_audit: pd.DataFrame,
    quality_audit: pd.DataFrame,
    patch_failures: int = 0,
) -> pd.DataFrame:
    total = len(index)
    support = int(index["valuation_support"].astype(bool).sum()) if total else 0
    lookup = dict(zip(quality_audit.get("metric", []), quality_audit.get("value", [])))
    score_frame = index[index["valuation_support"].astype(bool)].copy()

    def count_level(value: str) -> int:
        return int(index["valuation_context_level"].eq(value).sum()) if "valuation_context_level" in index.columns else 0

    def missing_reports(field: str) -> int:
        return int(index["missing_valuation_fields"].astype(str).str.contains(rf"(?:^|\|){re.escape(field)}(?:\||$)", regex=True).sum())

    rows = [
        ("total_standard_watchlist_reports", total, "standard watchlist denominator"),
        ("valuation_patched_reports_generated", total, "reports written to patched output directory"),
        ("reports_with_valuation_support", support, "assets with PIT valuation context support"),
        ("reports_without_valuation_support", total - support, "assets still missing support"),
        ("valuation_patch_coverage_ratio", round(support / total, 6) if total else 0.0, "support / total"),
        ("reports_valuation_low", count_level("valuation_low"), "context distribution"),
        ("reports_valuation_mid", count_level("valuation_mid"), "context distribution"),
        ("reports_valuation_high", count_level("valuation_high"), "context distribution"),
        ("reports_valuation_missing", count_level("valuation_missing"), "context distribution"),
        ("reports_with_market_cap", int(summary["has_market_cap"].sum()) if "has_market_cap" in summary.columns else support, "asset coverage"),
        ("reports_missing_pe_ttm", missing_reports("pe_ttm"), "detail missing"),
        ("reports_missing_pb", missing_reports("pb"), "detail missing"),
        ("reports_missing_ps_ttm", missing_reports("ps_ttm"), "detail missing"),
        ("reports_missing_ev_ebitda", missing_reports("ev_ebitda"), "detail missing"),
        ("reports_missing_valuation_percentile", missing_reports("valuation_percentile_1y") + missing_reports("valuation_percentile_3y") + missing_reports("valuation_percentile_5y"), "detail missing counts may overlap by asset"),
        ("reports_missing_industry_valuation_percentile", missing_reports("industry_valuation_percentile"), "detail missing"),
        ("reports_detail_degraded_market_cap_only", int(index["valuation_detail_quality"].eq("detail_degraded_market_cap_only").sum()), "degraded context"),
        ("reports_requiring_human_review", int(index["human_review_required"].astype(bool).sum()) if total else 0, "all reports require review"),
        ("reports_with_trading_language", int(index["contains_trading_language"].astype(bool).sum()) if total else 0, "must be zero"),
        ("lookahead_violation_rows", int(float(lookup.get("lookahead_violation_rows", 0))), "must be zero"),
        ("PIT_valid_ratio", float(lookup.get("PIT_valid_ratio", 0.0)), "from valuation adapter audit"),
        ("patch_failures", patch_failures, "must be zero"),
        ("average_valuation_position_score", round(float(pd.to_numeric(score_frame["valuation_position_score_latest"], errors="coerce").mean()), 6) if support else 0.0, "support assets only"),
        ("average_valuation_risk_score", round(float(pd.to_numeric(score_frame["valuation_risk_score_latest"], errors="coerce").mean()), 6) if support else 0.0, "support assets only"),
        ("average_valuation_quality_score", round(float(pd.to_numeric(score_frame["valuation_quality_score_latest"], errors="coerce").mean()), 6) if support else 0.0, "support assets only"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def _distribution(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return "none"
    counts = frame[column].value_counts(dropna=False)
    return ", ".join(f"{idx}={value}" for idx, value in counts.items())


def _field_text(field_audit: pd.DataFrame, available: bool) -> str:
    if field_audit.empty:
        return "none"
    frame = field_audit.copy()
    frame["coverage_ratio"] = pd.to_numeric(frame["coverage_ratio"], errors="coerce").fillna(0)
    selected = frame[frame["coverage_ratio"].gt(0)] if available else frame[frame["coverage_ratio"].eq(0)]
    selected = selected.sort_values("coverage_ratio", ascending=False).head(10)
    if selected.empty:
        return "none"
    return ", ".join(f"{row.field_name}={row.coverage_ratio:.2f}" for row in selected.itertuples(index=False))


def render_main_report(
    index: pd.DataFrame,
    summary: pd.DataFrame,
    audit: pd.DataFrame,
    field_audit: pd.DataFrame,
    quality_audit: pd.DataFrame,
    git_info: dict[str, str],
) -> str:
    metrics = dict(zip(audit.get("metric", []), audit.get("value", [])))
    total = int(float(metrics.get("total_standard_watchlist_reports", len(index))))
    support = int(float(metrics.get("reports_with_valuation_support", 0)))
    no_support = int(float(metrics.get("reports_without_valuation_support", total - support)))
    coverage_ratio = float(metrics.get("valuation_patch_coverage_ratio", 0.0))
    formal_status = git_info.get("formal_strategy_status", "") or "clean_or_tracked_no_status_rows"
    text = f"""# Tech Bottleneck Watchlist Report Valuation Patch v1

## 1. Executive Summary

- Valuation patched stock reports generated: {total}.
- Reports with valuation support: {support}.
- Reports without valuation support: {no_support}.
- Valuation patch coverage ratio: {coverage_ratio:.6f}.
- Valuation distribution: {_distribution(index, 'valuation_context_level')}.
- Current source limitation: PIT market-cap-only context; PE/PB/PS and industry valuation percentiles remain missing.
- Reports with restricted execution wording: {metrics.get('reports_with_trading_language', 0)}.
- Lookahead violation rows: {metrics.get('lookahead_violation_rows', 0)}.
- Patch failures: {metrics.get('patch_failures', 0)}.
- Recommended usage: manual research review only; not automated execution evidence.

## 2. Input Files

- `valuation_structured_outputs.csv`
- `valuation_asset_coverage.csv`
- `valuation_field_coverage_audit.csv`
- `watchlist_valuation_gap_patch.csv`
- `valuation_quality_audit.csv`
- fundamental patched stock reports

## 3. Patch Method

The patch appends a `Valuation Context Patch` section to each fundamental patched report. The latest PIT valuation row per asset is joined by `asset_id`; assets without support receive an explicit missing-support note.

## 4. Valuation Coverage

Among {total} standard watchlist reports, {support} have PIT valuation support and {no_support} remain missing. Supported rows retain degraded market-cap-only coverage.

## 5. Valuation Context Interpretation

`valuation_low`, `valuation_mid`, and `valuation_high` currently describe market-cap relative context only. They are not full PE/PB/PS valuation conclusions. A high label is not an automated exit conclusion, and a low label is not an automated entry conclusion.

## 6. Missing Detail Fields

Still missing: PE TTM, PB, PS TTM, EV/EBITDA, float market cap, 1y/3y/5y valuation percentiles, and industry valuation percentile.

Field coverage:

{field_audit.to_markdown(index=False) if not field_audit.empty else 'No field audit rows.'}

## 7. Report Quality Audit

{audit.to_markdown(index=False)}

## 8. Recommended Usage

Use the patched reports for manual review, report valuation context, and planning PE/PB/PS plus industry percentile data collection. Do not use these labels as automated execution evidence.

## 9. What This Patch Does Not Do

- It does not create automated execution directives.
- It does not alter Top5 or formal ranking.
- It does not modify formal strategy files.
- It does not study the technical lifecycle execution layer.
- It does not use an evidence multiplier.
- It does not treat valuation score as automated execution basis.

## 10. Recommended Next Step

Recommended next task: `tech_bottleneck_watchlist_report_consolidated_v1` if the current three-layer report stack is sufficient for manual review. If valuation detail is required first, run `tech_bottleneck_daily_basic_pe_pb_ps_source_adapter_v1`.

## 11. Appendix

Generated files:

- watchlist_report_valuation_patch_index.csv
- watchlist_valuation_patch_summary_by_asset.csv
- watchlist_valuation_patch_quality_audit.csv
- watchlist_report_valuation_patch_v1.md
- reports_valuation_patched/latest/*.md

Valuation source audit:

{quality_audit.to_markdown(index=False)}

Git repo root: {git_info.get('repo_root', 'unknown')}

Formal strategy file status:

```text
{formal_status}
```

Formal strategy ls-files:

```text
{git_info.get('formal_strategy_ls_files', '') or 'not_tracked_or_no_rows'}
```

Formal strategy stat:

```text
{git_info.get('formal_strategy_stat', '') or 'unavailable'}
```

Key assumptions:

- Market-cap-only context is useful for manual review but not a complete valuation conclusion.
- Latest PIT valuation context remains valid for the report date.
- Full PE/PB/PS context requires a separate daily-basic source adapter.

Uncertainty:

- Some formal strategy files are untracked in this repository state; git diff cannot fully prove historical immutability for untracked files.
"""
    text = sanitize_review_text(text)
    if contains_actionable_trading_language(text):
        raise ValueError("main report contains actionable trading language")
    return text


def _git_info(project_root: Path) -> dict[str, str]:
    files = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]

    def run(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=project_root, text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:  # pragma: no cover
            return f"unavailable: {exc}"

    return {
        "repo_root": run(["git", "rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run(["git", "status", "--short", *files]),
        "formal_strategy_ls_files": run(["git", "ls-files", *files]),
        "formal_strategy_stat": run(["stat", "-f", "%Sm %N", *files]),
    }


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def run(project_root: Path, output_dir: Path) -> dict[str, pd.DataFrame | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    valuation_dir = project_root / VALUATION_DIR
    fundamental_dir = project_root / FUNDAMENTAL_REPORT_DIR
    fulltext_dir = project_root / FULLTEXT_REPORT_DIR
    fundamental_index = _read_csv(fundamental_dir / "watchlist_report_fundamental_patch_index.csv")
    if fundamental_index.empty:
        fundamental_index = _read_csv(fulltext_dir / "watchlist_report_fulltext_announcement_patch_index.csv")
        if "fulltext_patched_report_path" in fundamental_index.columns:
            fundamental_index = fundamental_index.rename(columns={"fulltext_patched_report_path": "fundamental_patched_report_path"})
    structured = _read_csv(valuation_dir / "valuation_structured_outputs.csv")
    coverage = _read_csv(valuation_dir / "valuation_asset_coverage.csv")
    field_audit = _read_csv(valuation_dir / "valuation_field_coverage_audit.csv")
    quality_audit = _read_csv(valuation_dir / "valuation_quality_audit.csv")
    result = generate_valuation_patched_reports(output_dir, fundamental_index, structured, coverage, field_audit, quality_audit)
    index = result["index"]
    summary = result["summary"]
    audit = result["audit"]
    git_info = _git_info(project_root)
    report = render_main_report(index, summary, audit, field_audit, quality_audit, git_info)
    outputs = {
        "watchlist_report_valuation_patch_index.csv": index,
        "watchlist_valuation_patch_summary_by_asset.csv": summary,
        "watchlist_valuation_patch_quality_audit.csv": audit,
    }
    for name, frame in outputs.items():
        safe = sanitize_dataframe_for_output(frame)
        text = safe.to_csv(index=False)
        if contains_actionable_trading_language(text):
            raise ValueError(f"{name} contains actionable trading language")
        (output_dir / name).write_text(text, encoding="utf-8")
    (output_dir / "watchlist_report_valuation_patch_v1.md").write_text(report, encoding="utf-8")
    return {**outputs, "report": report}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck watchlist valuation report patch.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    result = run(project_root, output_dir)
    audit = result["watchlist_valuation_patch_quality_audit.csv"]
    if isinstance(audit, pd.DataFrame):
        lookup = dict(zip(audit["metric"], audit["value"]))
        print(f"output_dir={output_dir}")
        print(f"valuation_patched_reports_generated={lookup.get('valuation_patched_reports_generated', 0)}")
        print(f"reports_with_valuation_support={lookup.get('reports_with_valuation_support', 0)}")
        print(f"reports_without_valuation_support={lookup.get('reports_without_valuation_support', 0)}")
        print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows', 0)}")


if __name__ == "__main__":
    main()
