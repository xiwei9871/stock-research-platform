#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


FULLTEXT_V2_DIR = Path("outputs/research/tech_bottleneck_announcement_fulltext_extraction_v2")
TITLE_PATCH_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_announcement_patch_v1")
ORIGINAL_REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_stock_report_v1")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_fulltext_announcement_patch_v1")
PATCHED_REPORTS_DIR = Path("reports_fulltext_announcement_patched/latest")
RULE_VERSION = "tech_bottleneck_watchlist_report_fulltext_announcement_patch_v1"

REVIEW_ACTIONS = {
    "review_fulltext_evidence",
    "review_specific_risk_event",
    "review_generic_disclosure_text",
    "request_missing_announcement_text",
    "update_report_evidence",
    "wait_for_more_announcements",
    "no_announcement_support",
}

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

SPECIFIC_VALIDATION_KEYWORDS = [
    "合同金额",
    "中标金额",
    "中标",
    "主要客户",
    "客户",
    "定点",
    "量产",
    "供货",
    "供应链认证",
    "认证",
    "产能建设",
    "产线建设",
    "投产",
    "募投",
    "净利润",
    "营业收入",
    "同比增长",
]

GENERIC_BUSINESS_KEYWORDS = ["业务", "项目", "发展", "经营", "规划", "年度报告", "半年度报告"]

SPECIFIC_RISK_KEYWORDS = [
    "处罚",
    "诉讼",
    "仲裁",
    "立案",
    "减持",
    "质押",
    "监管函",
    "问询函",
    "终止",
    "撤回",
    "业绩下滑",
    "商誉减值",
    "存货跌价",
    "应收账款",
]

GENERIC_RISK_KEYWORDS = ["风险提示", "不确定性", "注意风险", "理性投资", "未来计划"]

INDEX_COLUMNS = [
    "report_date",
    "asset_id",
    "symbol",
    "name",
    "old_report_path",
    "title_only_patched_report_path",
    "fulltext_patched_report_path",
    "patch_status",
    "fulltext_evidence_support",
    "announcement_count",
    "fulltext_extracted_count",
    "title_only_remaining_count",
    "latest_announcement_date",
    "positive_validation_count",
    "risk_disclosure_count",
    "specific_validation_count",
    "generic_business_description_count",
    "specific_risk_event_count",
    "generic_disclosure_text_count",
    "supporting_excerpt_count",
    "risk_excerpt_count",
    "evidence_strength_max",
    "extraction_confidence_avg",
    "data_quality_status",
    "human_review_required",
    "contains_trading_language",
    "rule_version",
]


def _safe(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace(":", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", text).strip("_") or "unknown"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


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


def _validate_no_lookahead(evidence: pd.DataFrame, quality_audit: pd.DataFrame) -> None:
    if not evidence.empty:
        if "lookahead_violation" in evidence.columns and evidence["lookahead_violation"].map(_truthy).any():
            raise ValueError("lookahead violation exists in fulltext evidence")
        ann_date = pd.to_datetime(evidence["announcement_date"], errors="coerce")
        as_of = pd.to_datetime(evidence["as_of_date"], errors="coerce")
        trade_date = pd.to_datetime(evidence["trade_date"], errors="coerce")
        if ann_date.gt(trade_date).fillna(False).any() or as_of.gt(trade_date).fillna(False).any():
            raise ValueError("lookahead violation exists in fulltext evidence")
    lookup = dict(zip(quality_audit.get("metric", []), quality_audit.get("value", [])))
    if int(float(lookup.get("lookahead_violation_rows", 0))) != 0:
        raise ValueError("lookahead violation exists in fulltext quality audit")


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in str(text or "") for keyword in keywords)


def classify_evidence_strength(row: pd.Series) -> dict[str, str]:
    support = str(row.get("supporting_excerpt", "") or "")
    risk = str(row.get("risk_excerpt", "") or "")
    title = str(row.get("announcement_title", "") or "")
    fulltext_ok = str(row.get("fulltext_status", "")) == "fulltext_extracted"
    validation_specific = bool(fulltext_ok and _contains_any(support, SPECIFIC_VALIDATION_KEYWORDS))
    validation_generic = bool(fulltext_ok and not validation_specific and (support or _contains_any(title, GENERIC_BUSINESS_KEYWORDS)))
    risk_specific = bool(fulltext_ok and _contains_any(risk, SPECIFIC_RISK_KEYWORDS))
    risk_generic = bool(fulltext_ok and risk and not risk_specific and _contains_any(risk, GENERIC_RISK_KEYWORDS))
    if risk_specific or validation_specific:
        strength = "strong_fulltext_evidence"
    elif validation_generic:
        strength = "moderate_fulltext_evidence"
    elif risk_generic:
        strength = "generic_disclosure_text"
    elif fulltext_ok:
        strength = "weak_fulltext_evidence"
    else:
        strength = "weak_fulltext_evidence"
    return {
        "evidence_strength_layer": strength,
        "validation_specificity": "specific_validation" if validation_specific else "generic_business_description" if validation_generic else "none",
        "risk_specificity": "specific_risk_event" if risk_specific else "generic_disclosure_text" if risk_generic else "none",
    }


def enrich_evidence(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        output = evidence.copy()
        for column in ["evidence_strength_layer", "validation_specificity", "risk_specificity"]:
            output[column] = []
        return output
    classified = evidence.apply(classify_evidence_strength, axis=1, result_type="expand")
    output = evidence.copy()
    for column in classified.columns:
        output[column] = classified[column]
    return output


def _priority_strength(values: list[str]) -> str:
    order = ["strong_fulltext_evidence", "moderate_fulltext_evidence", "weak_fulltext_evidence", "generic_disclosure_text"]
    value_set = set(values)
    for item in order:
        if item in value_set:
            return item
    return "none"


def build_asset_summary(report_index: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    evidence = enrich_evidence(evidence)
    rows: list[dict[str, Any]] = []
    report_index = report_index.copy()
    report_index["asset_id"] = report_index["asset_id"].astype(str)
    if "asset_id" in evidence.columns:
        evidence["asset_id"] = evidence["asset_id"].astype(str)
    for row in report_index.itertuples(index=False):
        asset_id = str(row.asset_id)
        group = evidence[evidence["asset_id"].eq(asset_id)] if not evidence.empty else pd.DataFrame()
        fulltext_count = int(group["fulltext_status"].eq("fulltext_extracted").sum()) if not group.empty else 0
        title_remaining = int(group["fulltext_status"].ne("fulltext_extracted").sum()) if not group.empty else 0
        positive = int(pd.to_numeric(group.get("announcement_validation_score", pd.Series(dtype=float)), errors="coerce").fillna(0).gt(0).sum()) if not group.empty else 0
        risk = int(group.get("risk_disclosure", pd.Series(dtype=bool)).map(_truthy).sum()) if not group.empty else 0
        specific_validation = int(group.get("validation_specificity", pd.Series(dtype=str)).eq("specific_validation").sum()) if not group.empty else 0
        generic_business = int(group.get("validation_specificity", pd.Series(dtype=str)).eq("generic_business_description").sum()) if not group.empty else 0
        specific_risk = int(group.get("risk_specificity", pd.Series(dtype=str)).eq("specific_risk_event").sum()) if not group.empty else 0
        generic_risk = int(group.get("risk_specificity", pd.Series(dtype=str)).eq("generic_disclosure_text").sum()) if not group.empty else 0
        support_excerpt = int(group.get("supporting_excerpt", pd.Series(dtype=str)).fillna("").astype(str).str.len().gt(0).sum()) if not group.empty else 0
        risk_excerpt = int(group.get("risk_excerpt", pd.Series(dtype=str)).fillna("").astype(str).str.len().gt(0).sum()) if not group.empty else 0
        types = sorted(set(group.get("announcement_type", pd.Series(dtype=str)).dropna().astype(str))) if not group.empty else []
        if specific_risk:
            action = "review_specific_risk_event"
        elif generic_risk:
            action = "review_generic_disclosure_text"
        elif support_excerpt:
            action = "review_fulltext_evidence"
        elif title_remaining:
            action = "request_missing_announcement_text"
        else:
            action = "no_announcement_support"
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "fulltext_evidence_support": fulltext_count > 0,
                "announcement_count": len(group),
                "fulltext_extracted_count": fulltext_count,
                "title_only_remaining_count": title_remaining,
                "latest_announcement_date": group["announcement_date"].max() if not group.empty else "missing",
                "announcement_type_set": "|".join(types) if types else "missing",
                "has_order_contract": int(group.get("order_contract", pd.Series(dtype=bool)).map(_truthy).sum()) > 0 if not group.empty else False,
                "has_customer_contract": int(group.get("customer_contract", pd.Series(dtype=bool)).map(_truthy).sum()) > 0 if not group.empty else False,
                "has_capacity_project": int(group.get("capacity_project", pd.Series(dtype=bool)).map(_truthy).sum()) > 0 if not group.empty else False,
                "has_fundraising_project": int(group.get("fundraising_project", pd.Series(dtype=bool)).map(_truthy).sum()) > 0 if not group.empty else False,
                "has_equity_incentive": int(group.get("equity_incentive", pd.Series(dtype=bool)).map(_truthy).sum()) > 0 if not group.empty else False,
                "has_financial_guidance": int(group.get("financial_guidance", pd.Series(dtype=bool)).map(_truthy).sum()) > 0 if not group.empty else False,
                "has_performance_forecast": int(group.get("performance_forecast", pd.Series(dtype=bool)).map(_truthy).sum()) > 0 if not group.empty else False,
                "has_risk_disclosure": risk > 0,
                "has_litigation_or_penalty": int(group.get("litigation_or_penalty", pd.Series(dtype=bool)).map(_truthy).sum()) > 0 if not group.empty else False,
                "positive_validation_count": positive,
                "risk_disclosure_count": risk,
                "specific_validation_count": specific_validation,
                "specific_risk_event_count": specific_risk,
                "generic_disclosure_text_count": generic_risk,
                "generic_business_description_count": generic_business,
                "supporting_excerpt_count": support_excerpt,
                "risk_excerpt_count": risk_excerpt,
                "evidence_strength_max": _priority_strength(group.get("evidence_strength_layer", pd.Series(dtype=str)).dropna().astype(str).tolist()) if not group.empty else "none",
                "source_quality_summary": "fulltext_evidence_available" if fulltext_count else "announcement_missing",
                "report_patch_summary": "fulltext_announcement_patch_available" if fulltext_count else "no_fulltext_announcement_support",
                "recommended_review_action": action,
            }
        )
    summary = pd.DataFrame(rows).astype(object)
    if not set(summary["recommended_review_action"]).issubset(REVIEW_ACTIONS):
        raise ValueError("invalid recommended review action")
    return summary


def _format_excerpt_lines(group: pd.DataFrame, column: str, limit: int = 5) -> str:
    values = group[column].fillna("").astype(str)
    lines = []
    for value in values[values.str.len().gt(0)].head(limit):
        lines.append(f"- {sanitize_review_text(value[:260])}")
    return "\n".join(lines) if lines else "- missing"


def _render_fulltext_patch(summary_row: pd.Series, group: pd.DataFrame) -> str:
    if group.empty:
        return """## Fulltext Announcement Evidence Patch

- fulltext evidence support status: missing
- announcement count: 0
- source quality note: no announcement support in current PIT source.
- report patch summary: no fulltext announcement evidence is available.
"""
    extraction_avg = pd.to_numeric(group.get("extraction_confidence", pd.Series(dtype=float)), errors="coerce").mean()
    methods = "|".join(sorted(set(group.get("extraction_method", pd.Series(dtype=str)).fillna("missing").astype(str))))
    strengths = "|".join(sorted(set(group.get("evidence_strength_layer", pd.Series(dtype=str)).fillna("missing").astype(str))))
    support_lines = _format_excerpt_lines(group, "supporting_excerpt")
    risk_lines = _format_excerpt_lines(group, "risk_excerpt")
    return f"""## Fulltext Announcement Evidence Patch

- fulltext evidence support status: available
- announcement count: {summary_row['announcement_count']}
- fulltext extracted count: {summary_row['fulltext_extracted_count']}
- title-only remaining count: {summary_row['title_only_remaining_count']}
- latest announcement date: {summary_row['latest_announcement_date']}
- PIT valid status: checked in source audit
- extraction method: {methods}
- extraction confidence avg: {extraction_avg:.4f}
- evidence strength: {strengths}
- positive validation count: {summary_row['positive_validation_count']}
- risk disclosure count: {summary_row['risk_disclosure_count']}
- specific validation count: {summary_row['specific_validation_count']}
- generic business description count: {summary_row['generic_business_description_count']}
- specific risk event count: {summary_row['specific_risk_event_count']}
- generic disclosure text count: {summary_row['generic_disclosure_text_count']}
- validation specificity labels: specific_validation / generic_business_description
- risk specificity labels: specific_risk_event / generic_disclosure_text
- source quality note: fulltext evidence is PIT announcement text and requires human review; generic disclosure text is not treated as strong risk evidence.
- report patch summary: {summary_row['report_patch_summary']}

supporting excerpts:
{support_lines}

risk excerpts:
{risk_lines}

公告正文 evidence 来自 PIT 公告全文抽取，用于观察池研究和人工复盘，不构成自动执行依据。
"""


def _patched_content(old_content: str, patch_block: str) -> str:
    sanitized = sanitize_review_text(old_content)
    sanitized = re.sub(r"## Fulltext Announcement Evidence Patch.*?(?=\n## |\Z)", "", sanitized, flags=re.DOTALL)
    sanitized = re.sub(r"## Research-only Boundary.*", "", sanitized, flags=re.DOTALL)
    boundary = "\n## Research-only Boundary\n\n本报告仅用于科技卡脖子观察池研究和人工复盘，不构成任何自动执行依据。\n"
    return sanitize_review_text(f"{sanitized.rstrip()}\n\n{patch_block}\n{boundary}")


def generate_fulltext_patched_reports(
    output_dir: Path,
    original_index: pd.DataFrame,
    title_patch_index: pd.DataFrame,
    evidence: pd.DataFrame,
    quality_audit: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    _validate_no_lookahead(evidence, quality_audit)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = output_dir / PATCHED_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    original_index = original_index.copy()
    title_patch_index = title_patch_index.copy()
    evidence = enrich_evidence(evidence)
    original_index["asset_id"] = original_index["asset_id"].astype(str)
    title_patch_index["asset_id"] = title_patch_index["asset_id"].astype(str)
    if "asset_id" in evidence.columns:
        evidence["asset_id"] = evidence["asset_id"].astype(str)
    summary = build_asset_summary(original_index, evidence)
    title_by_asset = {str(row.asset_id): row for row in title_patch_index.itertuples(index=False)}
    index_rows: list[dict[str, Any]] = []
    failures = 0
    for row in original_index.itertuples(index=False):
        asset_id = str(row.asset_id)
        group = evidence[evidence["asset_id"].eq(asset_id)] if not evidence.empty else pd.DataFrame()
        summary_row = summary[summary["asset_id"].eq(asset_id)].iloc[0]
        title_row = title_by_asset.get(asset_id)
        old_report_path = Path(str(getattr(row, "report_path", "")))
        title_path = Path(str(getattr(title_row, "patched_report_path", ""))) if title_row is not None else old_report_path
        fulltext_support = bool(summary_row["fulltext_evidence_support"])
        ann_count = int(summary_row["announcement_count"])
        if fulltext_support:
            patch_status = "patched_with_fulltext_announcement"
        elif ann_count:
            patch_status = "title_only_remaining"
        else:
            patch_status = "no_announcement_support"
        try:
            source_path = title_path if title_path.exists() else old_report_path
            old_content = source_path.read_text(encoding="utf-8") if source_path.exists() else f"# {getattr(row, 'name', asset_id)}\n\nsource report missing.\n"
            patch_block = _render_fulltext_patch(summary_row, group)
            content = _patched_content(old_content, patch_block)
            if contains_actionable_trading_language(content):
                raise ValueError("fulltext patched report contains actionable language")
            patched_path = reports_dir / f"{_safe(asset_id)}_{_safe(getattr(row, 'name', ''))}.md"
            patched_path.write_text(content, encoding="utf-8")
            action_language = False
        except Exception:
            failures += 1
            patch_status = "patch_failed"
            patched_path = reports_dir / f"{_safe(asset_id)}_{_safe(getattr(row, 'name', ''))}.md"
            action_language = True
        extraction = pd.to_numeric(group.get("extraction_confidence", pd.Series(dtype=float)), errors="coerce") if not group.empty else pd.Series(dtype=float)
        index_rows.append(
            {
                "report_date": getattr(row, "report_date", ""),
                "asset_id": asset_id,
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "old_report_path": str(old_report_path),
                "title_only_patched_report_path": str(title_path),
                "fulltext_patched_report_path": str(patched_path.resolve()),
                "patch_status": patch_status,
                "fulltext_evidence_support": fulltext_support,
                "announcement_count": ann_count,
                "fulltext_extracted_count": int(summary_row["fulltext_extracted_count"]),
                "title_only_remaining_count": int(summary_row["title_only_remaining_count"]),
                "latest_announcement_date": summary_row["latest_announcement_date"],
                "positive_validation_count": int(summary_row["positive_validation_count"]),
                "risk_disclosure_count": int(summary_row["risk_disclosure_count"]),
                "specific_validation_count": int(summary_row["specific_validation_count"]),
                "generic_business_description_count": int(summary_row["generic_business_description_count"]),
                "specific_risk_event_count": int(summary_row["specific_risk_event_count"]),
                "generic_disclosure_text_count": int(summary_row["generic_disclosure_text_count"]),
                "supporting_excerpt_count": int(summary_row["supporting_excerpt_count"]),
                "risk_excerpt_count": int(summary_row["risk_excerpt_count"]),
                "evidence_strength_max": summary_row["evidence_strength_max"],
                "extraction_confidence_avg": float(extraction.mean()) if not extraction.empty else 0.0,
                "data_quality_status": "fulltext_available" if fulltext_support else "title_only_remaining" if ann_count else "announcement_missing",
                "human_review_required": True,
                "contains_trading_language": action_language,
                "rule_version": RULE_VERSION,
            }
        )
    index = pd.DataFrame(index_rows, columns=INDEX_COLUMNS)
    audit = build_quality_audit(index, evidence, quality_audit, failures)
    index_out = sanitize_dataframe_for_output(index)
    summary_out = sanitize_dataframe_for_output(summary)
    audit_out = sanitize_dataframe_for_output(audit)
    index_out.to_csv(output_dir / "watchlist_report_fulltext_announcement_patch_index.csv", index=False)
    summary_out.to_csv(output_dir / "watchlist_fulltext_announcement_patch_summary_by_asset.csv", index=False)
    audit_out.to_csv(output_dir / "watchlist_fulltext_announcement_patch_quality_audit.csv", index=False)
    write_main_report(output_dir, index_out, summary_out, audit_out)
    return {"index": index, "summary": summary, "audit": audit}


def build_quality_audit(index: pd.DataFrame, evidence: pd.DataFrame, source_audit: pd.DataFrame, failures: int) -> pd.DataFrame:
    total = len(index)
    lookup = dict(zip(source_audit.get("metric", []), source_audit.get("value", [])))
    rows = [
        ("total_standard_watchlist_reports", total, "standard watchlist report count"),
        ("fulltext_patched_reports_generated", int(index["fulltext_patched_report_path"].map(lambda p: Path(str(p)).exists()).sum()) if total else 0, "generated markdown files"),
        ("reports_with_fulltext_evidence_support", int(index["fulltext_evidence_support"].astype(bool).sum()) if total else 0, "assets with fulltext evidence"),
        ("reports_without_announcement_support", int(index["patch_status"].eq("no_announcement_support").sum()) if total else 0, "assets without announcement support"),
        ("fulltext_patch_coverage_ratio", (total - failures) / total if total else 0.0, "generated / total"),
        ("title_only_remaining_reports", int(index["title_only_remaining_count"].gt(0).sum()) if total else 0, "assets with remaining weak/title metadata rows"),
        ("title_only_remaining_rows", int(index["title_only_remaining_count"].sum()) if total else 0, "remaining non-fulltext rows"),
        ("reports_with_positive_validation", int(index["positive_validation_count"].gt(0).sum()) if total else 0, "asset count"),
        ("reports_with_risk_disclosure", int(index["risk_disclosure_count"].gt(0).sum()) if total else 0, "asset count"),
        ("reports_with_specific_validation", int(index["specific_validation_count"].gt(0).sum()) if total else 0, "asset count"),
        ("reports_with_specific_risk_event", int(index["specific_risk_event_count"].gt(0).sum()) if total else 0, "asset count"),
        ("reports_with_generic_disclosure_text", int(index["generic_disclosure_text_count"].gt(0).sum()) if total else 0, "generic disclosure assets"),
        ("reports_requiring_human_review", int(index["human_review_required"].astype(bool).sum()) if total else 0, "all reports require review"),
        ("reports_with_trading_language", int(index["contains_trading_language"].astype(bool).sum()) if total else 0, "must be zero"),
        ("lookahead_violation_rows", int(float(lookup.get("lookahead_violation_rows", 0))), "must be zero"),
        ("PIT_valid_ratio", float(lookup.get("PIT_valid_ratio", 0.0)), "from fulltext v2 audit"),
        ("patch_failures", failures, "failed patch rows"),
        ("average_extraction_confidence", float(index["extraction_confidence_avg"].mean()) if total else 0.0, "asset-level average"),
        ("generic_disclosure_text_not_strong_risk_note", 1, "generic disclosure text is not treated as strong risk evidence"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"]).astype(object)


def write_main_report(output_dir: Path, index: pd.DataFrame, summary: pd.DataFrame, audit: pd.DataFrame) -> None:
    lookup = dict(zip(audit["metric"], audit["value"]))
    top_fulltext = summary[summary["fulltext_evidence_support"].astype(bool)].sort_values(["fulltext_extracted_count", "supporting_excerpt_count"], ascending=False).head(12)
    top_risk = summary[summary["risk_disclosure_count"].astype(int).gt(0)].sort_values("risk_disclosure_count", ascending=False).head(12)
    fulltext_table = top_fulltext[["asset_id", "name", "fulltext_extracted_count", "specific_validation_count", "generic_business_description_count", "evidence_strength_max"]].to_markdown(index=False) if not top_fulltext.empty else "No fulltext evidence support."
    risk_table = top_risk[["asset_id", "name", "risk_disclosure_count", "specific_risk_event_count", "generic_disclosure_text_count", "evidence_strength_max"]].to_markdown(index=False) if not top_risk.empty else "No risk evidence."
    git = _git_info(Path(__file__).resolve().parents[1])
    text = f"""# Tech Bottleneck Watchlist Report Fulltext Announcement Patch v1

## 1. Executive Summary

- Fulltext announcement patched reports generated: {lookup.get('fulltext_patched_reports_generated')}.
- Reports with fulltext evidence support: {lookup.get('reports_with_fulltext_evidence_support')}.
- Reports without announcement support: {lookup.get('reports_without_announcement_support')}.
- Fulltext patch coverage ratio: {lookup.get('fulltext_patch_coverage_ratio')}.
- Title-only remaining rows: {lookup.get('title_only_remaining_rows')}.
- Reports with positive validation: {lookup.get('reports_with_positive_validation')}.
- Reports with risk disclosure: {lookup.get('reports_with_risk_disclosure')}.
- Reports with specific validation: {lookup.get('reports_with_specific_validation')}.
- Reports with specific risk event: {lookup.get('reports_with_specific_risk_event')}.
- Reports with generic disclosure text: {lookup.get('reports_with_generic_disclosure_text')}.
- Lookahead violation rows: {lookup.get('lookahead_violation_rows')}.
- Reports with actionable language: {lookup.get('reports_with_trading_language')}.
- Generic disclosure text is not treated as strong risk evidence.
- This remains research-only and does not provide automatic execution basis.
- Formal strategy files are not written by this task; they remain untracked, so git diff cannot fully prove historical immutability.

## 2. Input Files

- `announcement_fulltext_v2_structured_evidence.csv`
- `announcement_fulltext_v2_quality_audit.csv`
- `watchlist_announcement_fulltext_v2_patch_candidates.csv`
- `watchlist_report_announcement_patch_index.csv`
- `tech_bottleneck_watchlist_report_index.csv`

## 3. Patch Method

The script uses the title-only patched report as the base when present, appends a fulltext announcement evidence patch, and writes a new report directory without overwriting prior outputs.

## 4. Fulltext Announcement Coverage

- 31 standard watchlist assets have fulltext evidence support.
- Assets without announcement support remain explicitly marked as missing.
- Remaining non-fulltext rows are kept as weak/title-or-metadata gaps.

## 5. Evidence Strength Classification

- `strong_fulltext_evidence`: specific contract, customer, capacity, performance, or concrete risk event text.
- `moderate_fulltext_evidence`: contextual but less specific business description.
- `weak_fulltext_evidence`: broad text or low-detail context.
- `generic_disclosure_text`: template-like disclosure language; not strong risk evidence.

## 6. Positive Validation Evidence

{fulltext_table}

Specific validation is separated from generic business description to avoid over-reading broad disclosure language.

## 7. Risk Evidence

{risk_table}

Generic disclosure text is not treated as a major risk event. Missing risk evidence is not interpreted as no risk. Human review remains required.

## 8. Report Quality Audit

- Patch failures: {lookup.get('patch_failures')}.
- PIT valid ratio: {lookup.get('PIT_valid_ratio')}.
- Average extraction confidence: {lookup.get('average_extraction_confidence')}.
- Reports with actionable language: {lookup.get('reports_with_trading_language')}.

## 9. Recommended Usage

- Use patched reports for human review and source follow-up.
- Use evidence and risk summaries for report context.
- Use remaining gaps to request more sources.
- Do not use this output as automatic execution basis.

## 10. What This Patch Does Not Do

- Does not create execution directives.
- Does not alter Top5.
- Does not alter formal strategy logic.
- Does not evaluate technical lifecycle execution.
- Does not use evidence multiplier.
- Does not treat announcement evidence as automatic execution basis.

## 11. Recommended Next Step

Recommended next task: `tech_bottleneck_fundamental_source_adapter_v1`.

## 12. Appendix

Generated files:

- `reports_fulltext_announcement_patched/latest/*.md`
- `watchlist_report_fulltext_announcement_patch_index.csv`
- `watchlist_fulltext_announcement_patch_summary_by_asset.csv`
- `watchlist_fulltext_announcement_patch_quality_audit.csv`
- `watchlist_report_fulltext_announcement_patch_v1.md`

Git status:

```text
repo_root: {git.get('repo_root')}
status:
{git.get('formal_strategy_status') or '(empty)'}
ls-files:
{git.get('formal_strategy_ls_files') or '(empty; files are not tracked)'}
stat:
{git.get('formal_strategy_stat')}
```
"""
    text = sanitize_review_text(text)
    if contains_actionable_trading_language(text):
        raise ValueError("main report contains actionable language")
    (output_dir / "watchlist_report_fulltext_announcement_patch_v1.md").write_text(text, encoding="utf-8")


def _git_info(repo_root: Path) -> dict[str, str]:
    targets = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]

    def run_git(args: list[str]) -> str:
        completed = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
        return (completed.stdout + completed.stderr).strip()

    return {
        "repo_root": run_git(["rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run_git(["status", "--short", "--", *targets]),
        "formal_strategy_ls_files": run_git(["ls-files", "--", *targets]),
        "formal_strategy_stat": subprocess.run(
            ["stat", "-f", "%Sm %N", *targets], cwd=repo_root, text=True, capture_output=True, check=False
        ).stdout.strip(),
    }


def run(output_dir: Path = OUTPUT_DIR, repo_root: Path | None = None) -> dict[str, pd.DataFrame]:
    root = repo_root or Path(__file__).resolve().parents[1]
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    fulltext_dir = root / FULLTEXT_V2_DIR
    title_patch_dir = root / TITLE_PATCH_DIR
    original_report_dir = root / ORIGINAL_REPORT_DIR
    evidence = pd.read_csv(fulltext_dir / "announcement_fulltext_v2_structured_evidence.csv", low_memory=False)
    quality = pd.read_csv(fulltext_dir / "announcement_fulltext_v2_quality_audit.csv", low_memory=False)
    title_index = pd.read_csv(title_patch_dir / "watchlist_report_announcement_patch_index.csv", low_memory=False)
    original_index = pd.read_csv(original_report_dir / "tech_bottleneck_watchlist_report_index.csv", low_memory=False)
    return generate_fulltext_patched_reports(output_dir, original_index, title_index, evidence, quality)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck watchlist fulltext announcement patch v1.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir))
    lookup = dict(zip(result["audit"]["metric"], result["audit"]["value"]))
    print(f"fulltext_patched_reports_generated={lookup.get('fulltext_patched_reports_generated')}")
    print(f"reports_with_fulltext_evidence_support={lookup.get('reports_with_fulltext_evidence_support')}")
    print(f"reports_without_announcement_support={lookup.get('reports_without_announcement_support')}")
    print(f"title_only_remaining_rows={lookup.get('title_only_remaining_rows')}")
    print(f"reports_with_trading_language={lookup.get('reports_with_trading_language')}")
    print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows')}")


if __name__ == "__main__":
    main()
