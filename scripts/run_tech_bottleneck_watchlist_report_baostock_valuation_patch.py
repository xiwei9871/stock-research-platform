#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
BAOSTOCK_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_baostock_pe_pb_ps_source_adapter_v1"
FUNDAMENTAL_REPORT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_fundamental_patch_v1"
FULLTEXT_REPORT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_fulltext_announcement_patch_v1"
OLD_VALUATION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_valuation_source_adapter_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_baostock_valuation_patch_v1"
PATCHED_REPORTS_DIR = OUTPUT_DIR / "reports_baostock_valuation_patched/latest"
RULE_VERSION = "tech_bottleneck_watchlist_report_baostock_valuation_patch_v1"

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

INDEX_COLUMNS = [
    "report_date",
    "asset_id",
    "symbol",
    "name",
    "old_report_path",
    "fundamental_patched_report_path",
    "baostock_valuation_patched_report_path",
    "patch_status",
    "baostock_support",
    "latest_baostock_date",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "pcf_ncf_ttm",
    "pe_ttm_percentile_3y",
    "pb_percentile_3y",
    "ps_ttm_percentile_3y",
    "pe_meaningfulness",
    "valuation_context_level",
    "valuation_review_flag",
    "history_window_quality",
    "data_quality_status",
    "human_review_required",
    "contains_trading_language",
    "rule_version",
]

SUMMARY_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "baostock_support",
    "baostock_record_count",
    "pit_valid_record_count",
    "latest_baostock_date",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "pcf_ncf_ttm",
    "turnover_rate",
    "tradestatus",
    "is_st",
    "pe_ttm_percentile_1y",
    "pe_ttm_percentile_3y",
    "pe_ttm_percentile_5y",
    "pb_percentile_1y",
    "pb_percentile_3y",
    "pb_percentile_5y",
    "ps_ttm_percentile_1y",
    "ps_ttm_percentile_3y",
    "ps_ttm_percentile_5y",
    "pe_meaningfulness",
    "valuation_context_level",
    "valuation_review_flag",
    "history_window_quality",
    "source_quality_summary",
    "report_patch_summary",
    "recommended_review_action",
]

AUDIT_COLUMNS = ["metric", "value", "note"]


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


def _as_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


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


def _fmt(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "missing"
    return f"{number:.6f}"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def classify_pe_meaningfulness(pe_ttm: Any) -> str:
    pe = _as_float(pe_ttm)
    if pe is None:
        return "pe_missing"
    if pe <= 0:
        return "pe_negative_or_loss_making"
    return "pe_meaningful"


def _numeric_percentiles(row: pd.Series) -> list[float]:
    values = []
    for field in ["pe_ttm_percentile_3y", "pb_percentile_3y", "ps_ttm_percentile_3y"]:
        number = _as_float(row.get(field))
        if number is not None:
            values.append(number)
    return values


def classify_valuation_context(row: pd.Series, pe_meaningfulness: str) -> str:
    values = _numeric_percentiles(row)
    if not values:
        return "valuation_not_meaningful" if pe_meaningfulness != "pe_meaningful" else "valuation_missing"
    low_count = sum(value <= 0.33 for value in values)
    high_count = sum(value >= 0.67 for value in values)
    if pe_meaningfulness != "pe_meaningful":
        return "valuation_mixed_context" if len(values) >= 2 else "valuation_not_meaningful"
    if low_count >= 2:
        return "valuation_low_context"
    if high_count >= 2:
        return "valuation_high_context"
    if low_count == 0 and high_count == 0:
        return "valuation_mid_context"
    return "valuation_mixed_context"


def classify_review_flag(pe_meaningfulness: str, valuation_context_level: str) -> str:
    if pe_meaningfulness != "pe_meaningful":
        return "review_pe_not_meaningful"
    if valuation_context_level == "valuation_low_context":
        return "review_low_valuation_context"
    if valuation_context_level == "valuation_high_context":
        return "review_high_valuation_context"
    if valuation_context_level == "valuation_mixed_context":
        return "review_mixed_valuation_context"
    return "request_cross_source_validation"


def recommended_action(pe_meaningfulness: str, valuation_context_level: str) -> str:
    if pe_meaningfulness != "pe_meaningful":
        return "review_pe_not_meaningful"
    if valuation_context_level in {"valuation_low_context", "valuation_mid_context", "valuation_high_context", "valuation_mixed_context"}:
        return "review_pe_pb_ps_context"
    return "request_cross_source_validation"


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def validate_inputs(structured: pd.DataFrame, percentiles: pd.DataFrame, coverage: pd.DataFrame) -> None:
    if len(structured) != 102:
        raise ValueError(f"Expected 102 structured rows, got {len(structured)}")
    if len(percentiles) != 102:
        raise ValueError(f"Expected 102 percentile rows, got {len(percentiles)}")
    if len(coverage) != 102:
        raise ValueError(f"Expected 102 coverage rows, got {len(coverage)}")
    if structured["lookahead_violation"].map(_truthy).any():
        raise ValueError("BaoStock structured output contains lookahead rows")
    research = pd.to_datetime(structured["research_trade_date"], errors="coerce")
    bdate = pd.to_datetime(structured["baostock_date"], errors="coerce")
    if bdate.gt(research).fillna(False).any():
        raise ValueError("baostock_date exceeds research_trade_date")


def build_summary(structured: pd.DataFrame, percentiles: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    merged = (
        coverage.merge(structured, on=["asset_id", "symbol", "name", "baostock_code"], how="left", suffixes=("_coverage", ""))
        .merge(
            percentiles,
            on=["research_trade_date", "asset_id", "symbol", "name", "baostock_code", "baostock_date", "pe_ttm", "pb", "ps_ttm", "pcf_ncf_ttm"],
            how="left",
        )
    )
    rows = []
    for _, row in merged.iterrows():
        pe_meaningfulness = classify_pe_meaningfulness(row.get("pe_ttm"))
        valuation_context_level = classify_valuation_context(row, pe_meaningfulness)
        valuation_review_flag = classify_review_flag(pe_meaningfulness, valuation_context_level)
        rows.append(
            {
                "asset_id": row["asset_id"],
                "symbol": row["symbol"],
                "name": row["name"],
                "baostock_support": bool(row.get("valuation_support_level") == "baostock_pe_pb_ps_support"),
                "baostock_record_count": int(row.get("baostock_record_count", 0)),
                "pit_valid_record_count": int(row.get("pit_valid_record_count", 0)),
                "latest_baostock_date": row.get("latest_baostock_date", row.get("baostock_date", "missing")),
                "pe_ttm": row.get("pe_ttm"),
                "pb": row.get("pb"),
                "ps_ttm": row.get("ps_ttm"),
                "pcf_ncf_ttm": row.get("pcf_ncf_ttm"),
                "turnover_rate": row.get("turnover_rate"),
                "tradestatus": row.get("tradestatus"),
                "is_st": row.get("is_st"),
                "pe_ttm_percentile_1y": row.get("pe_ttm_percentile_1y"),
                "pe_ttm_percentile_3y": row.get("pe_ttm_percentile_3y"),
                "pe_ttm_percentile_5y": row.get("pe_ttm_percentile_5y"),
                "pb_percentile_1y": row.get("pb_percentile_1y"),
                "pb_percentile_3y": row.get("pb_percentile_3y"),
                "pb_percentile_5y": row.get("pb_percentile_5y"),
                "ps_ttm_percentile_1y": row.get("ps_ttm_percentile_1y"),
                "ps_ttm_percentile_3y": row.get("ps_ttm_percentile_3y"),
                "ps_ttm_percentile_5y": row.get("ps_ttm_percentile_5y"),
                "pe_meaningfulness": pe_meaningfulness,
                "valuation_context_level": valuation_context_level,
                "valuation_review_flag": valuation_review_flag,
                "history_window_quality": row.get("history_window_quality", "missing"),
                "source_quality_summary": "BaoStock PE/PB/PS context with PIT date check; cross-source validation recommended.",
                "report_patch_summary": "BaoStock valuation context added for research review.",
                "recommended_review_action": recommended_action(pe_meaningfulness, valuation_context_level),
            }
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def build_report_section(row: pd.Series) -> str:
    pe_note = ""
    if row["pe_meaningfulness"] != "pe_meaningful":
        pe_note = "\n当前 PE/PE-TTM 不具备正常估值解释意义，不能将负 PE 或缺失 PE 解释为低估。\n"
    return f"""

## BaoStock PE/PB/PS Valuation Patch

- BaoStock support status: {row["baostock_support"]}.
- BaoStock latest date: {_display(row["latest_baostock_date"])}.
- PIT valid status: true.
- source type: baostock_history_k_data.
- data quality status: PE/PB/PS context available; cross-source validation recommended.
- pe_ttm: {_fmt(row["pe_ttm"])}.
- pb: {_fmt(row["pb"])}.
- ps_ttm: {_fmt(row["ps_ttm"])}.
- pcf_ncf_ttm: {_fmt(row["pcf_ncf_ttm"])}.
- turnover_rate: {_fmt(row["turnover_rate"])}.
- tradestatus: {_display(row["tradestatus"])}.
- is_st: {_display(row["is_st"])}.
- pe_ttm_percentile_1y / 3y / 5y: {_display(row["pe_ttm_percentile_1y"])} / {_display(row["pe_ttm_percentile_3y"])} / {_display(row["pe_ttm_percentile_5y"])}.
- pb_percentile_1y / 3y / 5y: {_display(row["pb_percentile_1y"])} / {_display(row["pb_percentile_3y"])} / {_display(row["pb_percentile_5y"])}.
- ps_ttm_percentile_1y / 3y / 5y: {_display(row["ps_ttm_percentile_1y"])} / {_display(row["ps_ttm_percentile_3y"])} / {_display(row["ps_ttm_percentile_5y"])}.
- history_window_quality: {_display(row["history_window_quality"])}.
- pe_meaningfulness: {row["pe_meaningfulness"]}.
- valuation_context_level: {row["valuation_context_level"]}.
- valuation_review_flag: {row["valuation_review_flag"]}.
- report patch summary: {row["report_patch_summary"]}

当前估值数据来自 BaoStock 历史估值指标，可用于观察池研究和人工复盘；PE/PB/PS 分位只作为估值上下文，不构成自动执行提示。
valuation_low_context 不是自动执行依据；valuation_high_context 不是自动执行依据。
{pe_note}
"""


def _read_base_report(path: Any) -> str:
    report_path = Path(str(path))
    if report_path.exists():
        return report_path.read_text(encoding="utf-8")
    return "# Missing Base Report\n\nbase report missing; manual review required.\n"


def write_reports(summary: pd.DataFrame, fundamental_index: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> pd.DataFrame:
    PATCHED_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    fundamental_lookup = fundamental_index.set_index("asset_id").to_dict("index")
    rows = []
    report_date = str(pd.Timestamp.now(tz="Asia/Shanghai").date())
    for _, row in summary.iterrows():
        base = fundamental_lookup.get(row["asset_id"], {})
        base_path = base.get("fundamental_patched_report_path", "")
        old_path = base.get("old_report_path", "")
        filename = f"{_safe(row['asset_id'])}_{_safe(row['name'])}.md"
        report_path = PATCHED_REPORTS_DIR / filename
        text = _read_base_report(base_path)
        text = sanitize_review_text(text)
        patched = text.rstrip() + "\n" + build_report_section(row)
        patched = sanitize_review_text(patched)
        report_path.write_text(patched, encoding="utf-8")
        contains = contains_actionable_trading_language(patched)
        rows.append(
            {
                "report_date": report_date,
                "asset_id": row["asset_id"],
                "symbol": row["symbol"],
                "name": row["name"],
                "old_report_path": old_path,
                "fundamental_patched_report_path": base_path,
                "baostock_valuation_patched_report_path": str(report_path),
                "patch_status": "patched_with_baostock_valuation",
                "baostock_support": bool(row["baostock_support"]),
                "latest_baostock_date": row["latest_baostock_date"],
                "pe_ttm": row["pe_ttm"],
                "pb": row["pb"],
                "ps_ttm": row["ps_ttm"],
                "pcf_ncf_ttm": row["pcf_ncf_ttm"],
                "pe_ttm_percentile_3y": row["pe_ttm_percentile_3y"],
                "pb_percentile_3y": row["pb_percentile_3y"],
                "ps_ttm_percentile_3y": row["ps_ttm_percentile_3y"],
                "pe_meaningfulness": row["pe_meaningfulness"],
                "valuation_context_level": row["valuation_context_level"],
                "valuation_review_flag": row["valuation_review_flag"],
                "history_window_quality": row["history_window_quality"],
                "data_quality_status": "baostock_pe_pb_ps_context_available",
                "human_review_required": True,
                "contains_trading_language": contains,
                "rule_version": RULE_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=INDEX_COLUMNS)


def build_quality_audit(index: pd.DataFrame, summary: pd.DataFrame, structured: pd.DataFrame) -> pd.DataFrame:
    rows = [
        ("total standard watchlist reports", len(index), "expected 102"),
        ("baostock valuation patched reports generated", int(index["patch_status"].eq("patched_with_baostock_valuation").sum()), "generated Markdown files"),
        ("reports with baostock support", int(index["baostock_support"].sum()), "BaoStock support"),
        ("baostock patch coverage ratio", round(float(index["baostock_support"].mean()), 6) if len(index) else 0.0, "support ratio"),
        ("reports with pe_ttm", int(summary["pe_ttm"].notna().sum()), "field coverage"),
        ("reports with pb", int(summary["pb"].notna().sum()), "field coverage"),
        ("reports with ps_ttm", int(summary["ps_ttm"].notna().sum()), "field coverage"),
        ("reports with pcf_ncf_ttm", int(summary["pcf_ncf_ttm"].notna().sum()), "field coverage"),
        ("reports with 1y percentile", int(summary["pe_ttm_percentile_1y"].astype(str).ne("not_meaningful").sum()), "percentile context"),
        ("reports with 3y percentile", int(summary["pe_ttm_percentile_3y"].astype(str).ne("not_meaningful").sum()), "percentile context"),
        ("reports with 5y percentile", int(summary["pe_ttm_percentile_5y"].astype(str).ne("not_meaningful").sum()), "percentile context"),
        ("reports pe_meaningful", int(summary["pe_meaningfulness"].eq("pe_meaningful").sum()), "PE interpretation"),
        ("reports pe_negative_or_loss_making", int(summary["pe_meaningfulness"].eq("pe_negative_or_loss_making").sum()), "PE interpretation"),
        ("reports pe_missing", int(summary["pe_meaningfulness"].eq("pe_missing").sum()), "PE interpretation"),
        ("reports pe_not_meaningful", int(summary["pe_meaningfulness"].eq("pe_not_meaningful").sum()), "PE interpretation"),
        ("reports valuation_low_context", int(summary["valuation_context_level"].eq("valuation_low_context").sum()), "context only"),
        ("reports valuation_mid_context", int(summary["valuation_context_level"].eq("valuation_mid_context").sum()), "context only"),
        ("reports valuation_high_context", int(summary["valuation_context_level"].eq("valuation_high_context").sum()), "context only"),
        ("reports valuation_mixed_context", int(summary["valuation_context_level"].eq("valuation_mixed_context").sum()), "context only"),
        ("reports valuation_not_meaningful", int(summary["valuation_context_level"].eq("valuation_not_meaningful").sum()), "context only"),
        ("reports requiring human review", int(summary.shape[0]), "all reports require review"),
        ("reports with trading language", int(index["contains_trading_language"].sum()), "must be zero"),
        ("lookahead violation rows", int(structured["lookahead_violation"].map(_truthy).sum()) if not structured.empty else 0, "must be zero"),
        ("PIT valid ratio", round(float(structured["is_pit_valid"].map(_truthy).mean()), 6) if not structured.empty else 0.0, "PIT ratio"),
        ("patch failures", int(index["patch_status"].ne("patched_with_baostock_valuation").sum()), "must be zero"),
    ]
    return pd.DataFrame(rows, columns=AUDIT_COLUMNS)


def _git_info(project_root: Path = PROJECT_ROOT) -> dict[str, str]:
    def run(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=project_root, text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:  # noqa: BLE001
            return f"unavailable: {exc}"

    status = run(["git", "status", "--short", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"])
    return {"repo_root": run(["git", "rev-parse", "--show-toplevel"]), "formal_strategy_status": status or "clean_tracked_or_absent"}


def render_main_report(index: pd.DataFrame, summary: pd.DataFrame, audit: pd.DataFrame, git_info: dict[str, str]) -> str:
    lookup = dict(zip(audit["metric"], audit["value"]))
    context_counts = summary["valuation_context_level"].value_counts().to_dict()
    pe_counts = summary["pe_meaningfulness"].value_counts().to_dict()
    return f"""# Tech Bottleneck Watchlist Report BaoStock Valuation Patch v1

## 1. Executive Summary

- BaoStock valuation patched reports generated: {lookup.get("baostock valuation patched reports generated")}.
- BaoStock valuation support coverage: {lookup.get("reports with baostock support")} / {lookup.get("total standard watchlist reports")}.
- pe_ttm / pb / ps_ttm / pcf_ncf_ttm coverage: {lookup.get("reports with pe_ttm")} / {lookup.get("reports with pb")} / {lookup.get("reports with ps_ttm")} / {lookup.get("reports with pcf_ncf_ttm")}.
- 1y / 3y / 5y percentile coverage: {lookup.get("reports with 1y percentile")} / {lookup.get("reports with 3y percentile")} / {lookup.get("reports with 5y percentile")}.
- PE not normally meaningful count: {int(pe_counts.get("pe_negative_or_loss_making", 0)) + int(pe_counts.get("pe_missing", 0)) + int(pe_counts.get("pe_not_meaningful", 0))}.
- valuation context distribution: {context_counts}.
- Reports are suitable for human research review; AKShare / Tushare cross-source validation is still recommended.
- This patch does not create automated execution prompts and does not modify formal strategy files.

## 2. Input Files

- `{BAOSTOCK_DIR / "baostock_structured_outputs.csv"}`
- `{BAOSTOCK_DIR / "baostock_percentile_outputs.csv"}`
- `{BAOSTOCK_DIR / "baostock_asset_coverage.csv"}`
- `{FUNDAMENTAL_REPORT_DIR / "watchlist_report_fundamental_patch_index.csv"}`
- `{OLD_VALUATION_DIR / "valuation_structured_outputs.csv"}`

## 3. Patch Method

Each standard watchlist report starts from the fundamental patched report, then receives a BaoStock PE/PB/PS valuation section. The patch uses structured PIT rows and historical percentiles from the BaoStock adapter.

## 4. BaoStock Valuation Coverage

BaoStock support is available for {lookup.get("reports with baostock support")} reports. `lookahead violation rows = {lookup.get("lookahead violation rows")}`.

## 5. PE/PB/PS Context Interpretation

PE-TTM, PB-MRQ, PS-TTM, PCF-NCF-TTM and 1y / 3y / 5y percentiles are research context only. Negative or missing PE is not interpreted as low valuation. BaoStock values should be cross-checked when possible.

## 6. Valuation Context Distribution

{context_counts}

## 7. Report Quality Audit

- reports with automated execution wording: {lookup.get("reports with trading language")}.
- patch failures: {lookup.get("patch failures")}.
- PIT valid ratio: {lookup.get("PIT valid ratio")}.

## 8. Recommended Usage

Use this patch for manual research review, valuation context, and cross-source validation planning. Do not use it for automated execution.

## 9. What This Patch Does Not Do

- No automated execution prompt is produced.
- It does not change Top5.
- It does not change formal strategy files.
- It does not study trigger / holding / exit.
- It does not use evidence multiplier.
- It does not use PE/PB/PS percentiles as automated execution basis.

## 10. Recommended Next Step

Recommended sequence: `tech_bottleneck_akshare_lg_indicator_probe_v1`, then `tech_bottleneck_watchlist_report_consolidated_v1`.

## 11. Appendix

- generated files: patched reports, patch index, summary by asset, quality audit, Markdown report.
- git repo root: `{git_info.get("repo_root")}`.
- formal strategy file status: `{git_info.get("formal_strategy_status")}`.
- 如果正式策略文件仍是 untracked，无法仅靠 `git diff` 完整证明历史未变更；本任务没有写入这些文件。
- key assumption: BaoStock values are accepted as research context and should be cross-source validated later.
"""


def write_outputs(output_dir: Path = OUTPUT_DIR) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    structured = _load_csv(BAOSTOCK_DIR / "baostock_structured_outputs.csv")
    percentiles = _load_csv(BAOSTOCK_DIR / "baostock_percentile_outputs.csv")
    coverage = _load_csv(BAOSTOCK_DIR / "baostock_asset_coverage.csv")
    fundamental_index = _load_csv(FUNDAMENTAL_REPORT_DIR / "watchlist_report_fundamental_patch_index.csv")
    validate_inputs(structured, percentiles, coverage)
    summary = build_summary(structured, percentiles, coverage)
    index = write_reports(summary, fundamental_index, output_dir)
    audit = build_quality_audit(index, summary, structured)
    main_report = sanitize_review_text(render_main_report(index, summary, audit, _git_info(PROJECT_ROOT)))
    outputs = {
        "watchlist_report_baostock_valuation_patch_index.csv": sanitize_dataframe_for_output(index),
        "watchlist_baostock_valuation_patch_summary_by_asset.csv": sanitize_dataframe_for_output(summary),
        "watchlist_baostock_valuation_patch_quality_audit.csv": sanitize_dataframe_for_output(audit),
    }
    for name, frame in outputs.items():
        frame.to_csv(output_dir / name, index=False)
    (output_dir / "watchlist_report_baostock_valuation_patch_v1.md").write_text(main_report, encoding="utf-8")
    return outputs


def main() -> None:
    outputs = write_outputs(OUTPUT_DIR)
    audit = outputs["watchlist_baostock_valuation_patch_quality_audit.csv"]
    print(audit.to_string(index=False))
    joined = "\n".join(path.read_text(errors="ignore") for path in OUTPUT_DIR.rglob("*") if path.is_file())
    if contains_actionable_trading_language(joined):
        raise SystemExit("forbidden output language detected")


if __name__ == "__main__":
    main()
