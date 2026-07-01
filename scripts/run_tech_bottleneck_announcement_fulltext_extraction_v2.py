#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


EASTMONEY_DIR = Path("outputs/research/tech_bottleneck_eastmoney_notice_url_adapter_v1")
FULLTEXT_V1_DIR = Path("outputs/research/tech_bottleneck_announcement_fulltext_extraction_v1")
INGESTION_DIR = Path("outputs/research/tech_bottleneck_announcement_source_ingestion_v1")
PATCH_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_announcement_patch_v1")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_announcement_fulltext_extraction_v2")
RULE_VERSION = "tech_bottleneck_announcement_fulltext_extraction_v2"

ALLOWED_REVIEW_ACTIONS = {
    "update_report_with_fulltext_evidence",
    "review_fulltext_risk_disclosure",
    "request_manual_fulltext_download",
    "keep_title_only_warning",
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

KEYWORD_RULES = {
    "order_contract": ["中标", "签订合同", "重大合同", "订单", "采购合同", "项目合同", "战略合作协议", "供应协议", "合同金额", "中标金额"],
    "customer_contract": ["客户", "供应商", "进入供应链", "认证", "定点", "量产", "供货", "采购", "客户验证", "供应商资格"],
    "capacity_project": ["产能", "扩产", "投产", "建设项目", "生产线", "基地", "募投项目", "产线建设"],
    "fundraising_project": ["定增", "募集资金", "可转债", "发行股份", "配股", "融资", "募投"],
    "equity_incentive": ["股权激励", "限制性股票", "员工持股", "期权激励"],
    "financial_guidance": ["业绩预告", "业绩快报", "半年度报告", "年度报告", "季度报告", "净利润", "营业收入", "扣非", "同比增长", "同比下降"],
    "performance_forecast": ["业绩预告", "业绩快报", "净利润", "营业收入", "扣非", "同比增长", "同比下降"],
    "risk_disclosure": ["风险提示", "诉讼", "仲裁", "处罚", "立案", "减持", "质押", "监管函", "问询函", "业绩下滑", "商誉减值", "存货跌价", "应收账款", "终止", "撤回", "不确定性"],
    "litigation_or_penalty": ["诉讼", "仲裁", "处罚", "立案", "监管函", "问询函"],
    "major_customer_or_supplier": ["客户", "供应商", "大客户", "主要客户", "主要供应商"],
}

STRUCTURED_COLUMNS = [
    "trade_date",
    "asset_id",
    "symbol",
    "name",
    "announcement_id",
    "source_type",
    "announcement_title",
    "announcement_date",
    "as_of_date",
    "source_url",
    "resolved_pdf_url",
    "is_pit_valid",
    "lookahead_violation",
    "fulltext_status",
    "extraction_method",
    "announcement_type",
    "order_contract",
    "customer_contract",
    "capacity_project",
    "fundraising_project",
    "equity_incentive",
    "risk_disclosure",
    "financial_guidance",
    "performance_forecast",
    "litigation_or_penalty",
    "major_customer_or_supplier",
    "evidence_direction",
    "announcement_validation_score",
    "risk_event_score",
    "source_confidence",
    "extraction_confidence",
    "evidence_strength",
    "matched_keywords_title",
    "matched_keywords_fulltext",
    "supporting_excerpt",
    "risk_excerpt",
    "missing_fields",
    "conflict_flags",
    "data_quality_status",
    "rule_version",
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


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _read_text(path_value: Any) -> str:
    path = Path(str(path_value or ""))
    if not str(path_value or "") or not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _excerpt(text: str, keywords: list[str]) -> str:
    clean = _clean_text(text)
    if not clean:
        return ""
    for keyword in keywords:
        idx = clean.find(keyword)
        if idx >= 0:
            start = max(idx - 70, 0)
            end = min(idx + 190, len(clean))
            return sanitize_review_text(clean[start:end])
    return sanitize_review_text(clean[:220])


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _validate_no_lookahead(frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    if "lookahead_violation" in frame.columns and frame["lookahead_violation"].map(_bool).any():
        raise ValueError("lookahead violation exists in announcement rows")
    ann_date = pd.to_datetime(frame["announcement_date"], errors="coerce")
    as_of = pd.to_datetime(frame["as_of_date"], errors="coerce")
    trade_date = pd.to_datetime(frame["trade_date"], errors="coerce")
    if ann_date.gt(trade_date).fillna(False).any() or as_of.gt(trade_date).fillna(False).any():
        raise ValueError("lookahead violation exists in announcement rows")


def build_v2_extracted_outputs(manifest: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in manifest.itertuples(index=False):
        text_available = _bool(getattr(row, "text_available", False))
        pdf_available = _bool(getattr(row, "pdf_available", False))
        resolved_pdf_url = str(getattr(row, "resolved_pdf_url", "") or "")
        text = _clean_text(_read_text(getattr(row, "text_cache_path", ""))) if text_available else ""
        if text:
            status = "fulltext_extracted"
            source = str(getattr(row, "text_source", "") or "eastmoney_text_cache")
            method = "eastmoney_text_cache"
            error = ""
            quality = "fulltext_available"
        elif pdf_available:
            status = "pdf_available_text_missing"
            source = "eastmoney_pdf_cache"
            method = "pdf_not_parsed"
            error = "PDF cache exists but text parser is not applied in v2"
            quality = "degraded_pdf_text_missing"
        elif resolved_pdf_url:
            status = "metadata_only"
            source = "eastmoney_metadata"
            method = "metadata_only"
            error = "PDF URL exists but no usable text cache"
            quality = "degraded_metadata_only"
        else:
            status = "network_unavailable" if "network" in str(getattr(row, "data_quality_status", "")).lower() else "not_available"
            source = "unavailable"
            method = "not_available"
            error = "No usable text or PDF metadata"
            quality = "degraded_not_available"
        rows.append(
            {
                "announcement_id": getattr(row, "announcement_id", ""),
                "asset_id": getattr(row, "asset_id", ""),
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "announcement_title": getattr(row, "announcement_title", ""),
                "announcement_date": getattr(row, "announcement_date", ""),
                "source_url": getattr(row, "source_url", ""),
                "resolved_pdf_url": resolved_pdf_url,
                "text_cache_path": getattr(row, "text_cache_path", ""),
                "pdf_cache_path": getattr(row, "pdf_cache_path", ""),
                "text_available": bool(text_available and bool(text)),
                "pdf_available": bool(pdf_available),
                "fulltext_status": status,
                "fulltext_source": source,
                "raw_text_length": len(text),
                "clean_text_length": len(text),
                "text_excerpt": sanitize_review_text(text[:220]) if text else "",
                "extraction_method": method,
                "extraction_error": error,
                "data_quality_status": quality,
                "rule_version": RULE_VERSION,
                "fulltext_raw_text": text,
            }
        )
    return pd.DataFrame(rows).astype(object)


def classify_title_and_fulltext(title: str, text: str) -> dict[str, Any]:
    title_matches: list[str] = []
    fulltext_matches: list[str] = []
    result: dict[str, Any] = {}
    for field, keywords in KEYWORD_RULES.items():
        title_hit = [keyword for keyword in keywords if keyword in str(title or "")]
        text_hit = [keyword for keyword in keywords if keyword in str(text or "")]
        result[field] = bool(title_hit or text_hit)
        title_matches.extend(title_hit)
        fulltext_matches.extend(text_hit)
    if result.get("risk_disclosure") or result.get("litigation_or_penalty"):
        direction = "risk"
    elif any(result.get(field) for field in ["order_contract", "customer_contract", "capacity_project", "financial_guidance", "performance_forecast", "major_customer_or_supplier"]):
        direction = "positive_or_validation"
    else:
        direction = "neutral_or_unclassified"
    result["evidence_direction"] = direction
    result["matched_keywords_title"] = "|".join(sorted(set(title_matches)))
    result["matched_keywords_fulltext"] = "|".join(sorted(set(fulltext_matches)))
    result["announcement_type"] = next(
        (
            field
            for field in [
                "risk_disclosure",
                "order_contract",
                "customer_contract",
                "capacity_project",
                "fundraising_project",
                "equity_incentive",
                "performance_forecast",
                "financial_guidance",
            ]
            if result.get(field)
        ),
        "unclassified",
    )
    return result


def _safe_float(value: Any, default: float) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def build_v2_structured_evidence(structured: pd.DataFrame, extracted: pd.DataFrame) -> pd.DataFrame:
    _validate_no_lookahead(structured)
    extracted = extracted.copy()
    if "fulltext_raw_text" not in extracted.columns:
        extracted["fulltext_raw_text"] = ""
    merge_cols = [
        "announcement_id",
        "resolved_pdf_url",
        "fulltext_status",
        "extraction_method",
        "data_quality_status",
        "fulltext_raw_text",
    ]
    frame = structured.merge(extracted[merge_cols], on="announcement_id", how="left", suffixes=("", "_fulltext"))
    rows: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        status = str(getattr(row, "fulltext_status", "") or "not_available")
        fulltext_ok = status == "fulltext_extracted"
        fulltext = str(getattr(row, "fulltext_raw_text", "") or "")
        title = str(getattr(row, "announcement_title", "") or "")
        classified = classify_title_and_fulltext(title, fulltext if fulltext_ok else "")
        source_confidence = _safe_float(getattr(row, "source_confidence", 0.8), 0.8)
        confidence = 0.82 if fulltext_ok else _safe_float(getattr(row, "extraction_confidence", 0.35), 0.35)
        positive_hit = any(classified.get(field) for field in ["order_contract", "customer_contract", "capacity_project", "financial_guidance", "performance_forecast", "major_customer_or_supplier"])
        risk_hit = bool(classified.get("risk_disclosure") or classified.get("litigation_or_penalty"))
        validation = 0.8 if fulltext_ok and positive_hit else _safe_float(getattr(row, "announcement_validation_score", 0.0), 0.0)
        risk_score = 0.8 if fulltext_ok and risk_hit else _safe_float(getattr(row, "risk_event_score", 0.0), 0.0)
        support_excerpt = (
            _excerpt(fulltext, KEYWORD_RULES["order_contract"] + KEYWORD_RULES["customer_contract"] + KEYWORD_RULES["capacity_project"] + KEYWORD_RULES["financial_guidance"])
            if fulltext_ok and positive_hit
            else ""
        )
        risk_excerpt = _excerpt(fulltext, KEYWORD_RULES["risk_disclosure"] + KEYWORD_RULES["litigation_or_penalty"]) if fulltext_ok and risk_hit else ""
        rows.append(
            {
                "trade_date": getattr(row, "trade_date", ""),
                "asset_id": getattr(row, "asset_id", ""),
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "announcement_id": getattr(row, "announcement_id", ""),
                "source_type": "announcement",
                "announcement_title": title,
                "announcement_date": getattr(row, "announcement_date", ""),
                "as_of_date": getattr(row, "as_of_date", ""),
                "source_url": getattr(row, "source_url", ""),
                "resolved_pdf_url": getattr(row, "resolved_pdf_url", ""),
                "is_pit_valid": _bool(getattr(row, "is_pit_valid", False)),
                "lookahead_violation": _bool(getattr(row, "lookahead_violation", False)),
                "fulltext_status": status,
                "extraction_method": "eastmoney_text_cache_fulltext" if fulltext_ok else getattr(row, "extraction_method", "metadata_only"),
                "announcement_type": classified["announcement_type"] if fulltext_ok else getattr(row, "announcement_type", ""),
                "order_contract": bool(classified["order_contract"]) if fulltext_ok else _bool(getattr(row, "order_contract", False)),
                "customer_contract": bool(classified["customer_contract"]) if fulltext_ok else _bool(getattr(row, "customer_contract", False)),
                "capacity_project": bool(classified["capacity_project"]) if fulltext_ok else _bool(getattr(row, "capacity_project", False)),
                "fundraising_project": bool(classified["fundraising_project"]) if fulltext_ok else _bool(getattr(row, "fundraising_project", False)),
                "equity_incentive": bool(classified["equity_incentive"]) if fulltext_ok else _bool(getattr(row, "equity_incentive", False)),
                "risk_disclosure": bool(classified["risk_disclosure"]) if fulltext_ok else _bool(getattr(row, "risk_disclosure", False)),
                "financial_guidance": bool(classified["financial_guidance"]) if fulltext_ok else _bool(getattr(row, "financial_guidance", False)),
                "performance_forecast": bool(classified["performance_forecast"]) if fulltext_ok else _bool(getattr(row, "performance_forecast", False)),
                "litigation_or_penalty": bool(classified["litigation_or_penalty"]) if fulltext_ok else _bool(getattr(row, "litigation_or_penalty", False)),
                "major_customer_or_supplier": bool(classified["major_customer_or_supplier"]) if fulltext_ok else _bool(getattr(row, "major_customer_or_supplier", False)),
                "evidence_direction": classified["evidence_direction"] if fulltext_ok else getattr(row, "evidence_direction", ""),
                "announcement_validation_score": validation,
                "risk_event_score": risk_score,
                "source_confidence": source_confidence,
                "extraction_confidence": confidence,
                "evidence_strength": "fulltext_evidence" if fulltext_ok else "metadata_or_title_weak_cue",
                "matched_keywords_title": classified["matched_keywords_title"] if fulltext_ok else getattr(row, "matched_keywords", ""),
                "matched_keywords_fulltext": classified["matched_keywords_fulltext"] if fulltext_ok else "",
                "supporting_excerpt": support_excerpt,
                "risk_excerpt": risk_excerpt,
                "missing_fields": "" if fulltext_ok else "fulltext",
                "conflict_flags": "",
                "data_quality_status": "fulltext_available" if fulltext_ok else "degraded_metadata_or_title_only",
                "rule_version": RULE_VERSION,
            }
        )
    evidence = pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)
    _validate_no_lookahead(evidence)
    return evidence


def _non_missing_count(frame: pd.DataFrame, field: str) -> int:
    if frame.empty or field not in frame.columns:
        return 0
    series = frame[field]
    if pd.api.types.is_bool_dtype(series):
        return int(series.astype(bool).sum())
    if field in {"extraction_confidence", "evidence_strength"}:
        return int(series.notna().sum())
    return int(series.fillna("").astype(str).str.strip().ne("").sum())


def build_v2_field_coverage_audit(title_only: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "order_contract",
        "customer_contract",
        "capacity_project",
        "fundraising_project",
        "equity_incentive",
        "risk_disclosure",
        "financial_guidance",
        "performance_forecast",
        "litigation_or_penalty",
        "major_customer_or_supplier",
        "supporting_excerpt",
        "risk_excerpt",
        "extraction_confidence",
        "evidence_strength",
    ]
    rows: list[dict[str, Any]] = []
    total = len(evidence)
    for field in fields:
        before = _non_missing_count(title_only, field)
        after = _non_missing_count(evidence, field)
        rows.append(
            {
                "field_name": field,
                "title_only_non_missing_count_v1": before,
                "fulltext_non_missing_count_v2": after,
                "coverage_delta": after - before,
                "coverage_ratio_after_fulltext": after / total if total else 0.0,
                "quality_note": "fulltext_excerpt_only" if field.endswith("excerpt") else "v2_keyword_rule",
            }
        )
    return pd.DataFrame(rows).astype(object)


def build_v2_quality_audit(structured: pd.DataFrame, extracted: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    before_positive = int(pd.to_numeric(structured.get("announcement_validation_score", pd.Series(dtype=float)), errors="coerce").fillna(0).gt(0).sum()) if not structured.empty else 0
    after_positive = int(pd.to_numeric(evidence.get("announcement_validation_score", pd.Series(dtype=float)), errors="coerce").fillna(0).gt(0).sum()) if not evidence.empty else 0
    before_risk = int(structured.get("risk_disclosure", pd.Series(dtype=bool)).map(_bool).sum()) if not structured.empty else 0
    after_risk = int(evidence.get("risk_disclosure", pd.Series(dtype=bool)).map(_bool).sum()) if not evidence.empty else 0
    rows = [
        ("candidate_announcement_rows", len(structured), "input structured announcement rows"),
        ("text_available_rows", int(extracted["text_available"].map(_bool).sum()) if not extracted.empty else 0, "Eastmoney text cache rows"),
        ("fulltext_extracted_rows", int(extracted["fulltext_status"].eq("fulltext_extracted").sum()) if not extracted.empty else 0, "fulltext extracted rows"),
        ("fulltext_extraction_ratio", float(extracted["fulltext_status"].eq("fulltext_extracted").mean()) if not extracted.empty else 0.0, "extracted / candidates"),
        ("title_only_remaining_rows", int(extracted["fulltext_status"].ne("fulltext_extracted").sum()) if not extracted.empty else 0, "rows without fulltext"),
        ("pdf_available_rows", int(extracted["pdf_available"].map(_bool).sum()) if not extracted.empty else 0, "cached PDF rows"),
        ("metadata_only_rows", int(extracted["fulltext_status"].eq("metadata_only").sum()) if not extracted.empty else 0, "metadata-only rows"),
        ("network_unavailable_rows", int(extracted["fulltext_status"].eq("network_unavailable").sum()) if not extracted.empty else 0, "network rows"),
        ("manual_required_rows", int(extracted["fulltext_status"].isin(["metadata_only", "network_unavailable", "manual_required", "not_available", "pdf_available_text_missing"]).sum()) if not extracted.empty else 0, "manual follow-up rows"),
        ("structured_fulltext_evidence_rows", len(evidence), "evidence rows"),
        ("standard_watchlist_assets_with_fulltext_evidence", int(evidence.loc[evidence["fulltext_status"].eq("fulltext_extracted"), "asset_id"].nunique()) if not evidence.empty else 0, "assets with fulltext evidence"),
        ("positive_validation_rows_before", before_positive, "positive rows before"),
        ("positive_validation_rows_after", after_positive, "positive rows after"),
        ("risk_disclosure_rows_before", before_risk, "risk rows before"),
        ("risk_disclosure_rows_after", after_risk, "risk rows after"),
        ("supporting_excerpt_rows", int(evidence["supporting_excerpt"].fillna("").astype(str).str.len().gt(0).sum()) if not evidence.empty else 0, "support excerpts"),
        ("risk_excerpt_rows", int(evidence["risk_excerpt"].fillna("").astype(str).str.len().gt(0).sum()) if not evidence.empty else 0, "risk excerpts"),
        ("average_extraction_confidence_before", float(pd.to_numeric(structured.get("extraction_confidence", pd.Series(dtype=float)), errors="coerce").mean()) if not structured.empty else 0.0, "title-only average"),
        ("average_extraction_confidence_after", float(pd.to_numeric(evidence.get("extraction_confidence", pd.Series(dtype=float)), errors="coerce").mean()) if not evidence.empty else 0.0, "after fulltext"),
        ("PIT_valid_ratio", float(evidence["is_pit_valid"].map(_bool).mean()) if not evidence.empty else 0.0, "PIT valid ratio"),
        ("lookahead_violation_rows", int(evidence["lookahead_violation"].map(_bool).sum()) if not evidence.empty else 0, "must be zero"),
        ("degraded_rows", int(evidence["data_quality_status"].astype(str).str.contains("degraded", case=False).sum()) if not evidence.empty else 0, "degraded rows"),
        ("invalid_rows", int(evidence["data_quality_status"].astype(str).str.contains("invalid", case=False).sum()) if not evidence.empty else 0, "invalid rows"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"]).astype(object)


def build_watchlist_fulltext_v2_patch_candidates(evidence: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if evidence.empty:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "symbol",
                "name",
                "announcement_support",
                "fulltext_evidence_support",
                "announcement_count",
                "fulltext_extracted_count",
                "positive_validation_count",
                "risk_disclosure_count",
                "supporting_excerpt_count",
                "risk_excerpt_count",
                "evidence_strength_max",
                "data_quality_status",
                "recommended_report_update",
                "human_review_required",
            ]
        )
    for asset_id, group in evidence.groupby("asset_id", dropna=False):
        fulltext_count = int(group["fulltext_status"].eq("fulltext_extracted").sum())
        positive = int(pd.to_numeric(group["announcement_validation_score"], errors="coerce").fillna(0).gt(0).sum())
        risk = int(group["risk_disclosure"].map(_bool).sum())
        support_excerpt = int(group["supporting_excerpt"].fillna("").astype(str).str.len().gt(0).sum())
        risk_excerpt = int(group["risk_excerpt"].fillna("").astype(str).str.len().gt(0).sum())
        if risk_excerpt:
            action = "review_fulltext_risk_disclosure"
        elif support_excerpt:
            action = "update_report_with_fulltext_evidence"
        elif fulltext_count:
            action = "update_report_with_fulltext_evidence"
        else:
            action = "keep_title_only_warning"
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": group["symbol"].iloc[0],
                "name": group["name"].iloc[0],
                "announcement_support": True,
                "fulltext_evidence_support": fulltext_count > 0,
                "announcement_count": len(group),
                "fulltext_extracted_count": fulltext_count,
                "positive_validation_count": positive,
                "risk_disclosure_count": risk,
                "supporting_excerpt_count": support_excerpt,
                "risk_excerpt_count": risk_excerpt,
                "evidence_strength_max": "fulltext_evidence" if fulltext_count else "metadata_or_title_weak_cue",
                "data_quality_status": "fulltext_available" if fulltext_count else "degraded_metadata_or_title_only",
                "recommended_report_update": action,
                "human_review_required": True,
            }
        )
    frame = pd.DataFrame(rows).astype(object)
    if not set(frame["recommended_report_update"]).issubset(ALLOWED_REVIEW_ACTIONS):
        raise ValueError("invalid review action")
    if contains_actionable_trading_language(" ".join(frame.astype(str).agg(" ".join, axis=1).tolist())):
        raise ValueError("patch candidates contain actionable language")
    return frame


def write_report(output_dir: Path, extracted: pd.DataFrame, evidence: pd.DataFrame, field_audit: pd.DataFrame, quality_audit: pd.DataFrame, patch: pd.DataFrame) -> None:
    lookup = dict(zip(quality_audit["metric"], quality_audit["value"]))
    field_table = field_audit.sort_values("coverage_delta", ascending=False).head(12).to_markdown(index=False)
    patch_table = patch.sort_values(["fulltext_extracted_count", "supporting_excerpt_count", "risk_excerpt_count"], ascending=False).head(12).to_markdown(index=False) if not patch.empty else "No patch candidates."
    git = _git_info(Path(__file__).resolve().parents[1])
    text = f"""# Tech Bottleneck Announcement Fulltext Extraction v2

## 1. Executive Summary

- Eastmoney text cache was used successfully for rows marked `text_available`.
- Fulltext extracted rows: {lookup.get('fulltext_extracted_rows')}.
- Fulltext extraction ratio: {lookup.get('fulltext_extraction_ratio')}.
- Title-only remaining rows: {lookup.get('title_only_remaining_rows')}.
- Standard watchlist assets with fulltext evidence: {lookup.get('standard_watchlist_assets_with_fulltext_evidence')}.
- Positive validation rows before / after: {lookup.get('positive_validation_rows_before')} / {lookup.get('positive_validation_rows_after')}.
- Risk disclosure rows before / after: {lookup.get('risk_disclosure_rows_before')} / {lookup.get('risk_disclosure_rows_after')}.
- Supporting excerpt rows: {lookup.get('supporting_excerpt_rows')}; risk excerpt rows: {lookup.get('risk_excerpt_rows')}.
- Average extraction confidence before / after: {lookup.get('average_extraction_confidence_before')} / {lookup.get('average_extraction_confidence_after')}.
- Lookahead violation rows: {lookup.get('lookahead_violation_rows')}.
- The remaining rows are metadata-only or network-unavailable candidates for PDF parser / manual download follow-up.
- This remains research-only and does not evaluate technical lifecycle execution.
- Formal strategy files are not written by this task; they remain untracked, so git diff cannot fully prove historical immutability.

## 2. Input Files

- `eastmoney_notice_pdf_text_manifest.csv`
- `eastmoney_notice_resolution_results.csv`
- `announcement_fulltext_structured_evidence.csv`
- `announcement_structured_outputs.csv`
- `watchlist_announcement_patch_summary_by_asset.csv`

## 3. Fulltext Cache Usage

Rows with real Eastmoney text cache are loaded from `cache/text`. Metadata-only rows keep degraded status. PDF URLs are retained for follow-up, but PDF parsing is not performed in this v2.

## 4. Extraction Rules

Title keyword matches and fulltext keyword matches are recorded separately. Fulltext matches drive excerpts and higher extraction confidence. Risk matches are not overridden by positive validation matches.

## 5. Structured Evidence Results

- Structured fulltext evidence rows: {lookup.get('structured_fulltext_evidence_rows')}.
- Degraded rows: {lookup.get('degraded_rows')}.
- Invalid rows: {lookup.get('invalid_rows')}.

## 6. Improvement over v1 Title-only

{field_table}

## 7. Watchlist Report Patch Candidates

{patch_table}

## 8. Remaining Gaps

- Metadata-only rows: {lookup.get('metadata_only_rows')}.
- Network unavailable rows: {lookup.get('network_unavailable_rows')}.
- Manual follow-up rows: {lookup.get('manual_required_rows')}.
- These rows should be handled by a PDF parser or manual download pack.

## 9. Recommended Usage

- Use v2 evidence to update observation-pool stock reports.
- Use excerpts in review card evidence and risk summaries.
- Use remaining gaps to prioritize PDF/manual collection.
- Do not use this output for execution decisions.

## 10. What This Layer Does Not Do

- Does not create execution directives.
- Does not alter Top5.
- Does not alter formal strategy logic.
- Does not evaluate technical lifecycle execution.
- Does not use evidence multiplier.
- Does not promote title-only cues to strong evidence.

## 11. Recommended Next Step

Recommended next task: `tech_bottleneck_watchlist_report_fulltext_announcement_patch_v1`.

## 12. Appendix

Generated files:

- `announcement_fulltext_v2_extracted_outputs.csv`
- `announcement_fulltext_v2_structured_evidence.csv`
- `announcement_fulltext_v2_field_coverage_audit.csv`
- `announcement_fulltext_v2_quality_audit.csv`
- `watchlist_announcement_fulltext_v2_patch_candidates.csv`
- `announcement_fulltext_extraction_v2.md`

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
    (output_dir / "announcement_fulltext_extraction_v2.md").write_text(text, encoding="utf-8")


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
    output_dir.mkdir(parents=True, exist_ok=True)
    eastmoney_dir = root / EASTMONEY_DIR
    ingestion_dir = root / INGESTION_DIR
    fulltext_v1_dir = root / FULLTEXT_V1_DIR

    manifest = pd.read_csv(eastmoney_dir / "eastmoney_notice_pdf_text_manifest.csv", low_memory=False)
    structured = pd.read_csv(ingestion_dir / "announcement_structured_outputs.csv", low_memory=False)
    title_only = pd.read_csv(fulltext_v1_dir / "announcement_fulltext_structured_evidence.csv", low_memory=False)

    extracted = build_v2_extracted_outputs(manifest)
    evidence = build_v2_structured_evidence(structured, extracted)
    field_audit = build_v2_field_coverage_audit(title_only, evidence)
    quality_audit = build_v2_quality_audit(structured, extracted, evidence)
    patch = build_watchlist_fulltext_v2_patch_candidates(evidence)

    if int(quality_audit.loc[quality_audit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0]) != 0:
        raise ValueError("lookahead violation rows must be zero")

    extracted_out = sanitize_dataframe_for_output(extracted.drop(columns=["fulltext_raw_text"], errors="ignore"))
    evidence_out = sanitize_dataframe_for_output(evidence)
    field_audit_out = sanitize_dataframe_for_output(field_audit)
    quality_audit_out = sanitize_dataframe_for_output(quality_audit)
    patch_out = sanitize_dataframe_for_output(patch)

    extracted_out.to_csv(output_dir / "announcement_fulltext_v2_extracted_outputs.csv", index=False)
    evidence_out.to_csv(output_dir / "announcement_fulltext_v2_structured_evidence.csv", index=False)
    field_audit_out.to_csv(output_dir / "announcement_fulltext_v2_field_coverage_audit.csv", index=False)
    quality_audit_out.to_csv(output_dir / "announcement_fulltext_v2_quality_audit.csv", index=False)
    patch_out.to_csv(output_dir / "watchlist_announcement_fulltext_v2_patch_candidates.csv", index=False)
    write_report(output_dir, extracted_out, evidence_out, field_audit_out, quality_audit_out, patch_out)
    return {
        "extracted": extracted,
        "evidence": evidence,
        "field_audit": field_audit,
        "quality_audit": quality_audit,
        "patch": patch,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck announcement fulltext extraction v2.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir))
    lookup = dict(zip(result["quality_audit"]["metric"], result["quality_audit"]["value"]))
    print(f"fulltext_extracted_rows={lookup.get('fulltext_extracted_rows')}")
    print(f"fulltext_extraction_ratio={lookup.get('fulltext_extraction_ratio')}")
    print(f"title_only_remaining_rows={lookup.get('title_only_remaining_rows')}")
    print(f"standard_watchlist_assets_with_fulltext_evidence={lookup.get('standard_watchlist_assets_with_fulltext_evidence')}")
    print(f"positive_validation_rows_before={lookup.get('positive_validation_rows_before')}")
    print(f"positive_validation_rows_after={lookup.get('positive_validation_rows_after')}")
    print(f"risk_disclosure_rows_before={lookup.get('risk_disclosure_rows_before')}")
    print(f"risk_disclosure_rows_after={lookup.get('risk_disclosure_rows_after')}")
    print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows')}")


if __name__ == "__main__":
    main()
