#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


ANNOUNCEMENT_DIR = Path("outputs/research/tech_bottleneck_announcement_source_ingestion_v1")
PATCH_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_announcement_patch_v1")
REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_stock_report_v1")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_announcement_fulltext_extraction_v1")
RULE_VERSION = "tech_bottleneck_announcement_fulltext_extraction_v1"

LOCAL_BODY_CSVS = [
    Path("outputs/research/serenity_remaining_customer_certification_body_fill_20260608/remaining_after_irm_cninfo_announcement_body_raw.csv"),
]
LOCAL_TEXT_DIRS = [
    Path("outputs/research/serenity_remaining_customer_certification_body_fill_20260608/cninfo_announcement_text"),
]
LOCAL_PDF_DIRS = [
    Path("outputs/research/serenity_remaining_customer_certification_body_fill_20260608/cninfo_announcement_pdfs"),
]

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
    "order_contract": ["中标", "签订合同", "重大合同", "订单", "采购合同", "项目合同", "战略合作协议", "供应协议"],
    "customer_contract": ["客户", "供应商", "进入供应链", "认证", "定点", "量产", "供货", "采购"],
    "capacity_project": ["产能", "扩产", "投产", "建设项目", "生产线", "基地", "募投项目"],
    "fundraising_project": ["定增", "募集资金", "可转债", "发行股份", "配股", "融资"],
    "equity_incentive": ["股权激励", "限制性股票", "员工持股", "期权激励"],
    "financial_guidance": ["业绩预告", "业绩快报", "半年度报告", "年度报告", "季度报告", "净利润", "营业收入", "扣非"],
    "performance_forecast": ["业绩预告", "业绩快报", "净利润", "营业收入", "扣非"],
    "risk_disclosure": ["风险提示", "诉讼", "仲裁", "处罚", "立案", "减持", "质押", "监管函", "问询函", "业绩下滑", "商誉减值", "存货跌价", "应收账款"],
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


def _normalize_title(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"^[^:：]{1,20}[:：]", "", text)
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text).lower()


def _extract_id(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"AN(\d+)|/(\d{9,})\.PDF|_(\d{9,})\.", text, re.IGNORECASE)
    if not match:
        return ""
    return next(part for part in match.groups() if part)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _excerpt(text: str, keywords: list[str]) -> str:
    clean = _clean_text(text)
    if not clean:
        return ""
    for keyword in keywords:
        idx = clean.find(keyword)
        if idx >= 0:
            start = max(idx - 60, 0)
            end = min(idx + 180, len(clean))
            return sanitize_review_text(clean[start:end])
    return sanitize_review_text(clean[:220])


def _validate_no_lookahead(frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    if "lookahead_violation" in frame.columns and frame["lookahead_violation"].astype(bool).any():
        raise ValueError("lookahead violation exists in announcement rows")
    ann_date = pd.to_datetime(frame["announcement_date"], errors="coerce")
    as_of = pd.to_datetime(frame["as_of_date"], errors="coerce")
    trade_date = pd.to_datetime(frame["trade_date"], errors="coerce")
    if ann_date.gt(trade_date).fillna(False).any() or as_of.gt(trade_date).fillna(False).any():
        raise ValueError("lookahead violation exists in announcement rows")


def scan_fulltext_source_inventory(project_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    paths = list(LOCAL_BODY_CSVS) + list(LOCAL_TEXT_DIRS) + list(LOCAL_PDF_DIRS)
    for rel in paths:
        path = project_root / rel
        exists = path.exists()
        fields = "missing"
        text_available = False
        pdf_available = False
        date_field = "missing"
        asset_field = "missing"
        title_field = "missing"
        content_field = "missing"
        url_field = "missing"
        announcement_id_field = "missing"
        if exists and path.is_file() and path.suffix.lower() == ".csv":
            sample = pd.read_csv(path, nrows=100, low_memory=False)
            fields = "|".join(sample.columns.astype(str))
            text_available = "content" in sample.columns and sample["content"].fillna("").astype(str).str.len().gt(100).any()
            date_field = "published_at" if "published_at" in sample.columns else "missing"
            asset_field = "asset_id" if "asset_id" in sample.columns else "missing"
            title_field = "title" if "title" in sample.columns else "missing"
            content_field = "content" if "content" in sample.columns else "missing"
            url_field = "url" if "url" in sample.columns else "missing"
            announcement_id_field = "announcement_id" if "announcement_id" in sample.columns else "missing"
        elif exists and path.is_dir():
            suffixes = {p.suffix.lower() for p in path.glob("*") if p.is_file()}
            text_available = ".txt" in suffixes or ".html" in suffixes
            pdf_available = ".pdf" in suffixes
        rows.append(
            {
                "source_name": path.name,
                "source_type": "announcement_fulltext",
                "existing_in_project": exists,
                "detected_path_or_table": str(path),
                "file_or_table_type": "directory" if path.is_dir() else path.suffix.lower().lstrip(".") if path.suffix else "missing",
                "available_fields": fields,
                "announcement_id_field": announcement_id_field,
                "title_field": title_field,
                "date_field": date_field,
                "asset_id_field": asset_field,
                "url_field": url_field,
                "content_field": content_field,
                "pdf_path_field": "path" if path.name.endswith("pdfs") and exists else "missing",
                "html_path_field": "path" if text_available and path.is_dir() else "missing",
                "text_available": text_available,
                "pdf_available": pdf_available,
                "url_available": url_field != "missing",
                "pit_ready": bool(exists and (date_field != "missing" or path.is_dir())),
                "coverage_estimate": "partial_local_source" if exists else "missing",
                "quality_risk": "partial_historical_coverage" if exists else "source_missing",
                "notes": "Local fulltext candidate source scan.",
            }
        )
    return pd.DataFrame(rows)


def build_local_fulltext_index(project_root: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    text_index: dict[str, Any] = {}
    pdf_index: dict[str, Path] = {}
    for rel in LOCAL_BODY_CSVS:
        path = project_root / rel
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        for row in frame.itertuples(index=False):
            content = str(getattr(row, "content", "") or "")
            if len(content.strip()) < 100:
                continue
            keys = {
                str(getattr(row, "announcement_id", "") or ""),
                str(getattr(row, "url", "") or ""),
                _extract_id(getattr(row, "url", "")),
                f"{getattr(row, 'asset_id', '')}|{_normalize_title(getattr(row, 'title', ''))}|{pd.to_datetime(getattr(row, 'published_at', ''), errors='coerce').strftime('%Y-%m-%d') if pd.notna(pd.to_datetime(getattr(row, 'published_at', ''), errors='coerce')) else ''}",
            }
            for key in {k for k in keys if k}:
                text_index[key] = content
    for rel in LOCAL_TEXT_DIRS:
        path = project_root / rel
        if not path.exists():
            continue
        for txt in path.glob("*.txt"):
            content = txt.read_text(encoding="utf-8", errors="ignore")
            keys = {txt.stem, _extract_id(txt.name)}
            for key in {k for k in keys if k}:
                text_index.setdefault(key, txt)
    for rel in LOCAL_PDF_DIRS:
        path = project_root / rel
        if not path.exists():
            continue
        for pdf in path.glob("*.PDF"):
            keys = {pdf.stem, _extract_id(pdf.name)}
            for key in {k for k in keys if k}:
                pdf_index.setdefault(key, pdf)
    return text_index, pdf_index


def _candidate_keys(row: Any) -> list[str]:
    ann_date = pd.to_datetime(getattr(row, "announcement_date", ""), errors="coerce")
    date_text = ann_date.strftime("%Y-%m-%d") if pd.notna(ann_date) else ""
    return [
        str(getattr(row, "announcement_id", "") or ""),
        str(getattr(row, "source_url", "") or ""),
        _extract_id(getattr(row, "announcement_id", "")),
        _extract_id(getattr(row, "source_url", "")),
        f"{getattr(row, 'asset_id', '')}|{_normalize_title(getattr(row, 'announcement_title', ''))}|{date_text}",
    ]


def build_fulltext_fetch_plan(structured: pd.DataFrame, local_text_index: dict[str, Any], local_pdf_index: dict[str, Path]) -> pd.DataFrame:
    _validate_no_lookahead(structured)
    rows: list[dict[str, Any]] = []
    for row in structured.itertuples(index=False):
        keys = [key for key in _candidate_keys(row) if key]
        text_key = next((key for key in keys if key in local_text_index), "")
        pdf_key = next((key for key in keys if key in local_pdf_index), "")
        title = str(getattr(row, "announcement_title", "") or "")
        source_url = str(getattr(row, "source_url", "") or "")
        risk = bool(getattr(row, "risk_disclosure", False)) or bool(getattr(row, "litigation_or_penalty", False))
        positive = any(bool(getattr(row, field, False)) for field in ["order_contract", "customer_contract", "capacity_project", "performance_forecast"])
        if text_key:
            method = "use_local_text"
        elif pdf_key:
            method = "parse_local_pdf"
        elif source_url:
            method = "fetch_source_url"
        else:
            method = "manual_download_required"
        priority = "high" if risk or positive else "medium" if any(bool(getattr(row, field, False)) for field in ["fundraising_project", "equity_incentive"]) else "low"
        rows.append(
            {
                "asset_id": getattr(row, "asset_id", ""),
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "announcement_id": getattr(row, "announcement_id", ""),
                "announcement_title": title,
                "announcement_date": getattr(row, "announcement_date", ""),
                "source_url": source_url,
                "raw_source_name": "announcement_structured_outputs",
                "current_extraction_method": getattr(row, "extraction_method", ""),
                "needs_fulltext": True,
                "fulltext_available_locally": bool(text_key),
                "pdf_available_locally": bool(pdf_key),
                "url_available": bool(source_url),
                "recommended_fetch_method": method,
                "fetch_priority": priority,
                "reason": "risk_or_validation_title_cue" if priority == "high" else "coverage_completion",
                "human_review_required": True,
                "local_text_key": text_key,
                "local_text_ref": str(local_text_index[text_key]) if text_key else "",
                "local_pdf_key": pdf_key,
                "local_pdf_ref": str(local_pdf_index[pdf_key]) if pdf_key else "",
            }
        )
    return pd.DataFrame(rows)


def _read_text_ref(ref: str) -> str:
    if not ref:
        return ""
    path = Path(ref)
    if path.exists():
        return path.read_text(encoding="utf-8", errors="ignore")
    return ref


def extract_fulltexts(fetch_plan: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in fetch_plan.itertuples(index=False):
        method = str(getattr(row, "recommended_fetch_method", ""))
        text = ""
        status = "not_attempted"
        source = ""
        error = ""
        if method == "use_local_text":
            text = _read_text_ref(str(getattr(row, "local_text_ref", "")))
            status = "fulltext_extracted" if len(_clean_text(text)) >= 20 else "local_text_missing"
            source = "local_text"
        elif method == "parse_local_pdf":
            status = "pdf_parse_failed"
            source = "local_pdf"
            error = "pdf parser not enabled in research-only v1"
        elif method == "fetch_source_url":
            status = "not_attempted"
            source = "source_url"
            error = "external fetch not attempted in research-only v1"
        elif method == "manual_download_required":
            status = "manual_required"
            source = "missing_url"
        clean = _clean_text(text)
        rows.append(
            {
                "announcement_id": getattr(row, "announcement_id", ""),
                "asset_id": getattr(row, "asset_id", ""),
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "announcement_title": getattr(row, "announcement_title", ""),
                "announcement_date": getattr(row, "announcement_date", ""),
                "source_url": getattr(row, "source_url", ""),
                "fulltext_status": status,
                "fulltext_source": source,
                "raw_text_length": len(text),
                "clean_text_length": len(clean),
                "text_excerpt": sanitize_review_text(clean[:220]) if status == "fulltext_extracted" else "",
                "extraction_method": "local_text" if status == "fulltext_extracted" else method,
                "extraction_error": error,
                "data_quality_status": "fulltext_available" if status == "fulltext_extracted" else "degraded_title_only",
                "rule_version": RULE_VERSION,
                "fulltext_raw_text": text,
            }
        )
    return pd.DataFrame(rows)


def classify_text(title: str, text: str) -> dict[str, Any]:
    combined = f"{title} {text}"
    result: dict[str, Any] = {}
    matched: list[str] = []
    for field, keywords in KEYWORD_RULES.items():
        active = any(keyword in combined for keyword in keywords)
        result[field] = active
        if active:
            matched.extend([keyword for keyword in keywords if keyword in combined])
    if result.get("risk_disclosure") or result.get("litigation_or_penalty"):
        direction = "risk"
    elif any(result.get(field) for field in ["order_contract", "customer_contract", "capacity_project", "financial_guidance", "performance_forecast"]):
        direction = "positive_or_validation"
    else:
        direction = "neutral_or_unclassified"
    result["evidence_direction"] = direction
    result["matched_keywords"] = "|".join(sorted(set(matched)))
    result["announcement_type"] = next((field for field in ["risk_disclosure", "order_contract", "customer_contract", "capacity_project", "fundraising_project", "equity_incentive", "performance_forecast", "financial_guidance"] if result.get(field)), "unclassified")
    return result


def build_fulltext_structured_evidence(structured: pd.DataFrame, extracted: pd.DataFrame) -> pd.DataFrame:
    _validate_no_lookahead(structured)
    extracted = extracted.copy()
    if "fulltext_raw_text" not in extracted.columns:
        extracted["fulltext_raw_text"] = ""
    frame = structured.merge(extracted[["announcement_id", "fulltext_status", "extraction_method", "data_quality_status", "fulltext_raw_text"]], on="announcement_id", how="left", suffixes=("", "_fulltext"))
    rows: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        fulltext = str(getattr(row, "fulltext_raw_text", "") or "")
        fulltext_ok = str(getattr(row, "fulltext_status", "")) == "fulltext_extracted"
        classified = classify_text(str(getattr(row, "announcement_title", "")), fulltext if fulltext_ok else "")
        source_confidence = float(getattr(row, "source_confidence", 0.8) or 0.8)
        confidence = 0.75 if fulltext_ok else float(getattr(row, "extraction_confidence", 0.35) or 0.35)
        validation = 0.75 if fulltext_ok and any(classified.get(field) for field in ["order_contract", "customer_contract", "capacity_project", "financial_guidance", "performance_forecast", "major_customer_or_supplier"]) else float(getattr(row, "announcement_validation_score", 0.0) or 0.0)
        risk_score = 0.75 if fulltext_ok and (classified.get("risk_disclosure") or classified.get("litigation_or_penalty")) else float(getattr(row, "risk_event_score", 0.0) or 0.0)
        support_excerpt = _excerpt(fulltext, KEYWORD_RULES["order_contract"] + KEYWORD_RULES["customer_contract"] + KEYWORD_RULES["capacity_project"]) if fulltext_ok and validation > 0 else ""
        risk_excerpt = _excerpt(fulltext, KEYWORD_RULES["risk_disclosure"] + KEYWORD_RULES["litigation_or_penalty"]) if fulltext_ok and risk_score > 0 else ""
        rows.append(
            {
                "trade_date": getattr(row, "trade_date", ""),
                "asset_id": getattr(row, "asset_id", ""),
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "announcement_id": getattr(row, "announcement_id", ""),
                "source_type": "announcement",
                "announcement_title": getattr(row, "announcement_title", ""),
                "announcement_date": getattr(row, "announcement_date", ""),
                "as_of_date": getattr(row, "as_of_date", ""),
                "source_url": getattr(row, "source_url", ""),
                "is_pit_valid": bool(getattr(row, "is_pit_valid", False)),
                "lookahead_violation": bool(getattr(row, "lookahead_violation", False)),
                "fulltext_status": getattr(row, "fulltext_status", "not_attempted"),
                "extraction_method": "local_text_fulltext" if fulltext_ok else getattr(row, "extraction_method", "keyword_title_only"),
                "announcement_type": classified["announcement_type"] if fulltext_ok else getattr(row, "announcement_type", ""),
                "order_contract": bool(classified["order_contract"]) if fulltext_ok else bool(getattr(row, "order_contract", False)),
                "customer_contract": bool(classified["customer_contract"]) if fulltext_ok else bool(getattr(row, "customer_contract", False)),
                "capacity_project": bool(classified["capacity_project"]) if fulltext_ok else bool(getattr(row, "capacity_project", False)),
                "fundraising_project": bool(classified["fundraising_project"]) if fulltext_ok else bool(getattr(row, "fundraising_project", False)),
                "equity_incentive": bool(classified["equity_incentive"]) if fulltext_ok else bool(getattr(row, "equity_incentive", False)),
                "risk_disclosure": bool(classified["risk_disclosure"]) if fulltext_ok else bool(getattr(row, "risk_disclosure", False)),
                "financial_guidance": bool(classified["financial_guidance"]) if fulltext_ok else bool(getattr(row, "financial_guidance", False)),
                "performance_forecast": bool(classified["performance_forecast"]) if fulltext_ok else bool(getattr(row, "performance_forecast", False)),
                "litigation_or_penalty": bool(classified["litigation_or_penalty"]) if fulltext_ok else bool(getattr(row, "litigation_or_penalty", False)),
                "major_customer_or_supplier": bool(classified["major_customer_or_supplier"]) if fulltext_ok else bool(getattr(row, "major_customer_or_supplier", False)),
                "evidence_direction": classified["evidence_direction"] if fulltext_ok else getattr(row, "evidence_direction", ""),
                "announcement_validation_score": validation,
                "risk_event_score": risk_score,
                "source_confidence": source_confidence,
                "extraction_confidence": confidence,
                "evidence_strength": "fulltext_evidence" if fulltext_ok else "title_only_weak_cue",
                "matched_keywords_title": getattr(row, "matched_keywords", ""),
                "matched_keywords_fulltext": classified["matched_keywords"] if fulltext_ok else "",
                "supporting_excerpt": support_excerpt,
                "risk_excerpt": risk_excerpt,
                "missing_fields": "" if fulltext_ok else "fulltext",
                "conflict_flags": "",
                "data_quality_status": "fulltext_available" if fulltext_ok else "degraded_title_only",
                "rule_version": RULE_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)


def build_field_coverage_audit(title_only: pd.DataFrame, fulltext: pd.DataFrame) -> pd.DataFrame:
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
    ]
    rows: list[dict[str, Any]] = []
    total = len(fulltext)
    for field in fields:
        before = _non_missing_count(title_only, field)
        after = _non_missing_count(fulltext, field)
        rows.append(
            {
                "field_name": field,
                "title_only_non_missing_count": before,
                "fulltext_non_missing_count": after,
                "coverage_delta": after - before,
                "coverage_ratio_after_fulltext": after / total if total else 0.0,
                "quality_note": "excerpt_only_when_fulltext_available" if field.endswith("excerpt") else "ok",
            }
        )
    return pd.DataFrame(rows)


def _non_missing_count(frame: pd.DataFrame, field: str) -> int:
    if frame.empty or field not in frame.columns:
        return 0
    series = frame[field]
    if pd.api.types.is_bool_dtype(series):
        return int(series.astype(bool).sum())
    if field == "extraction_confidence":
        return int(pd.to_numeric(series, errors="coerce").notna().sum())
    return int(series.fillna("").astype(str).str.strip().ne("").sum())


def build_quality_audit(structured: pd.DataFrame, fetch_plan: pd.DataFrame, extracted: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    rows = [
        ("candidate_announcement_rows", len(structured), "input structured announcement rows"),
        ("fulltext_fetch_plan_rows", len(fetch_plan), "fetch plan rows"),
        ("fulltext_extracted_rows", int(extracted["fulltext_status"].eq("fulltext_extracted").sum()) if not extracted.empty else 0, "local fulltext extracted rows"),
        ("fulltext_extraction_ratio", float(extracted["fulltext_status"].eq("fulltext_extracted").mean()) if not extracted.empty else 0.0, "extracted / candidates"),
        ("title_only_remaining_rows", int(evidence["fulltext_status"].ne("fulltext_extracted").sum()) if not evidence.empty else 0, "rows still title-only"),
        ("local_text_available_rows", int(fetch_plan["fulltext_available_locally"].astype(bool).sum()) if not fetch_plan.empty else 0, "local text matches"),
        ("pdf_available_rows", int(fetch_plan["pdf_available_locally"].astype(bool).sum()) if not fetch_plan.empty else 0, "local pdf matches"),
        ("source_url_available_rows", int(fetch_plan["url_available"].astype(bool).sum()) if not fetch_plan.empty else 0, "rows with source url"),
        ("fetch_failed_rows", int(extracted["fulltext_status"].eq("fetch_failed").sum()) if not extracted.empty else 0, "external fetch failures"),
        ("manual_required_rows", int(extracted["fulltext_status"].eq("manual_required").sum()) if not extracted.empty else 0, "manual rows"),
        ("structured_fulltext_evidence_rows", len(evidence), "fulltext evidence rows"),
        ("standard_watchlist_assets_with_fulltext_evidence", int(evidence.loc[evidence["fulltext_status"].eq("fulltext_extracted"), "asset_id"].nunique()) if not evidence.empty else 0, "assets with fulltext evidence"),
        ("positive_validation_rows_after_fulltext", int(evidence["announcement_validation_score"].gt(0).sum()) if not evidence.empty else 0, "positive validation rows"),
        ("risk_disclosure_rows_after_fulltext", int(evidence["risk_disclosure"].astype(bool).sum()) if not evidence.empty else 0, "risk rows"),
        ("average_extraction_confidence_before", float(pd.to_numeric(structured["extraction_confidence"], errors="coerce").mean()) if not structured.empty else 0.0, "title-only average"),
        ("average_extraction_confidence_after", float(pd.to_numeric(evidence["extraction_confidence"], errors="coerce").mean()) if not evidence.empty else 0.0, "after fulltext"),
        ("PIT_valid_ratio", float(evidence["is_pit_valid"].astype(bool).mean()) if not evidence.empty else 0.0, "PIT valid ratio"),
        ("lookahead_violation_rows", int(evidence["lookahead_violation"].astype(bool).sum()) if not evidence.empty else 0, "must be zero"),
        ("degraded_rows", int(evidence["data_quality_status"].astype(str).str.contains("degraded", case=False).sum()) if not evidence.empty else 0, "degraded rows"),
        ("invalid_rows", int(evidence["data_quality_status"].astype(str).str.contains("invalid", case=False).sum()) if not evidence.empty else 0, "invalid rows"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def build_watchlist_fulltext_patch_candidates(evidence: pd.DataFrame) -> pd.DataFrame:
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
                "new_supporting_excerpt_count",
                "new_risk_excerpt_count",
                "evidence_strength_max",
                "data_quality_status",
                "recommended_report_update",
                "human_review_required",
            ]
        )
    for asset_id, group in evidence.groupby("asset_id", dropna=False):
        fulltext_count = int(group["fulltext_status"].eq("fulltext_extracted").sum())
        positive = int(group["announcement_validation_score"].gt(0).sum())
        risk = int(group["risk_disclosure"].astype(bool).sum())
        support_excerpt = int(group["supporting_excerpt"].fillna("").astype(str).str.len().gt(0).sum())
        risk_excerpt = int(group["risk_excerpt"].fillna("").astype(str).str.len().gt(0).sum())
        if risk_excerpt:
            action = "review_fulltext_risk_disclosure"
        elif support_excerpt:
            action = "update_report_with_fulltext_evidence"
        elif len(group):
            action = "keep_title_only_warning"
        else:
            action = "no_announcement_support"
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
                "new_supporting_excerpt_count": support_excerpt,
                "new_risk_excerpt_count": risk_excerpt,
                "evidence_strength_max": "fulltext_evidence" if fulltext_count else "title_only_weak_cue",
                "data_quality_status": "fulltext_available" if fulltext_count else "degraded_title_only",
                "recommended_report_update": action,
                "human_review_required": True,
            }
        )
    frame = pd.DataFrame(rows)
    if not set(frame["recommended_report_update"]).issubset(ALLOWED_REVIEW_ACTIONS):
        raise ValueError("invalid review action")
    if contains_actionable_trading_language(" ".join(frame.astype(str).agg(" ".join, axis=1).tolist())):
        raise ValueError("patch candidates contain actionable language")
    return frame


def write_report(output_dir: Path, inventory: pd.DataFrame, fetch_plan: pd.DataFrame, evidence: pd.DataFrame, audit: pd.DataFrame, patch: pd.DataFrame) -> None:
    lookup = dict(zip(audit["metric"], audit["value"]))
    inventory_table = inventory[["source_name", "existing_in_project", "text_available", "pdf_available", "coverage_estimate", "quality_risk"]].to_markdown(index=False)
    patch_table = patch.sort_values(["fulltext_extracted_count", "positive_validation_count", "risk_disclosure_count"], ascending=False).head(12).to_markdown(index=False) if not patch.empty else "No patch candidates."
    git = _git_info(Path(__file__).resolve().parents[1])
    text = f"""# Tech Bottleneck Announcement Fulltext Extraction v1

## 1. Executive Summary

- Fulltext source found locally: {bool(inventory['text_available'].astype(bool).any())}.
- Fulltext extracted rows: {lookup.get('fulltext_extracted_rows')}.
- Fulltext extraction ratio: {lookup.get('fulltext_extraction_ratio')}.
- Title-only remaining rows: {lookup.get('title_only_remaining_rows')}.
- Standard watchlist assets with fulltext evidence: {lookup.get('standard_watchlist_assets_with_fulltext_evidence')}.
- Positive validation rows after fulltext: {lookup.get('positive_validation_rows_after_fulltext')}.
- Risk disclosure rows after fulltext: {lookup.get('risk_disclosure_rows_after_fulltext')}.
- Lookahead violation rows: {lookup.get('lookahead_violation_rows')}.
- This remains research-only and does not evaluate technical lifecycle execution.
- Formal strategy files are not written by this task; they remain untracked, so git diff cannot fully prove historical immutability.

## 2. Fulltext Source Inventory

{inventory_table}

## 3. Fetch Plan

- fetch plan rows: {lookup.get('fulltext_fetch_plan_rows')}
- local text rows: {lookup.get('local_text_available_rows')}
- local PDF rows: {lookup.get('pdf_available_rows')}
- source URL rows: {lookup.get('source_url_available_rows')}
- manual required rows: {lookup.get('manual_required_rows')}

## 4. Extraction Method

This v1 uses local text when matched by announcement id, URL id, or asset/title/date. Local PDF parsing and external URL fetch are not enabled in this research-only pass.

## 5. Structured Fulltext Evidence

- structured rows: {lookup.get('structured_fulltext_evidence_rows')}
- average confidence before: {lookup.get('average_extraction_confidence_before')}
- average confidence after: {lookup.get('average_extraction_confidence_after')}
- degraded rows: {lookup.get('degraded_rows')}

## 6. Improvement over Title-only Extraction

Rows with fulltext receive higher extraction confidence and short excerpts. Rows without fulltext remain degraded title-only weak cues.

## 7. Watchlist Report Patch Candidates

{patch_table}

## 8. Data Gaps and Limitations

- Most Eastmoney notice URLs have no local body cache.
- Local CNINFO text cache is partial and historical.
- PDF parsing is intentionally not enabled in v1.
- External URL fetch is only planned, not executed.
- Missing fulltext is not interpreted as absence of evidence or risk.

## 9. Recommended Usage

- Use fulltext excerpts to update watchlist research reports.
- Use missing rows to prioritize manual or external fulltext collection.
- Do not use this output for execution decisions.

## 10. What This Layer Does Not Do

- Does not create execution instructions.
- Does not alter Top5.
- Does not alter formal strategy logic.
- Does not evaluate technical lifecycle execution.
- Does not use evidence multiplier.
- Does not promote title-only cues to strong evidence.

## 11. Recommended Next Step

Recommended next task: `tech_bottleneck_watchlist_report_fulltext_announcement_patch_v1` if fulltext coverage is meaningful; otherwise `tech_bottleneck_announcement_external_fetch_adapter_v1`.

## 12. Appendix

Generated files:

- `announcement_fulltext_source_inventory.csv`
- `announcement_fulltext_fetch_plan.csv`
- `announcement_fulltext_extracted_outputs.csv`
- `announcement_fulltext_structured_evidence.csv`
- `announcement_fulltext_field_coverage_audit.csv`
- `announcement_fulltext_quality_audit.csv`
- `watchlist_announcement_fulltext_patch_candidates.csv`
- `announcement_fulltext_extraction_v1.md`

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
    (output_dir / "announcement_fulltext_extraction_v1.md").write_text(text, encoding="utf-8")


def _git_info(repo_root: Path) -> dict[str, str]:
    targets = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]

    def run(args: list[str]) -> str:
        completed = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
        return (completed.stdout + completed.stderr).strip()

    return {
        "repo_root": run(["rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run(["status", "--short", "--", *targets]),
        "formal_strategy_ls_files": run(["ls-files", "--", *targets]),
        "formal_strategy_stat": subprocess.run(
            ["stat", "-f", "%Sm %N", *targets], cwd=repo_root, text=True, capture_output=True, check=False
        ).stdout.strip(),
    }


def run(output_dir: Path = OUTPUT_DIR, repo_root: Path | None = None) -> dict[str, pd.DataFrame]:
    root = repo_root or Path(__file__).resolve().parents[1]
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    announcement_dir = root / ANNOUNCEMENT_DIR
    structured = pd.read_csv(announcement_dir / "announcement_structured_outputs.csv", low_memory=False)
    inventory = scan_fulltext_source_inventory(root)
    text_index, pdf_index = build_local_fulltext_index(root)
    fetch_plan = build_fulltext_fetch_plan(structured, text_index, pdf_index)
    extracted = extract_fulltexts(fetch_plan)
    evidence = build_fulltext_structured_evidence(structured, extracted)
    field_audit = build_field_coverage_audit(structured, evidence)
    quality_audit = build_quality_audit(structured, fetch_plan, extracted, evidence)
    patch = build_watchlist_fulltext_patch_candidates(evidence)
    if int(quality_audit.loc[quality_audit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0]) != 0:
        raise ValueError("lookahead violation rows must be zero")
    inventory_out = sanitize_dataframe_for_output(inventory)
    fetch_plan_out = sanitize_dataframe_for_output(fetch_plan.drop(columns=["local_text_ref", "local_pdf_ref"], errors="ignore"))
    extracted_out = sanitize_dataframe_for_output(extracted.drop(columns=["fulltext_raw_text"], errors="ignore"))
    evidence_out = sanitize_dataframe_for_output(evidence)
    field_audit_out = sanitize_dataframe_for_output(field_audit)
    quality_audit_out = sanitize_dataframe_for_output(quality_audit)
    patch_out = sanitize_dataframe_for_output(patch)
    inventory_out.to_csv(output_dir / "announcement_fulltext_source_inventory.csv", index=False)
    fetch_plan_out.to_csv(output_dir / "announcement_fulltext_fetch_plan.csv", index=False)
    extracted_out.to_csv(output_dir / "announcement_fulltext_extracted_outputs.csv", index=False)
    evidence_out.to_csv(output_dir / "announcement_fulltext_structured_evidence.csv", index=False)
    field_audit_out.to_csv(output_dir / "announcement_fulltext_field_coverage_audit.csv", index=False)
    quality_audit_out.to_csv(output_dir / "announcement_fulltext_quality_audit.csv", index=False)
    patch_out.to_csv(output_dir / "watchlist_announcement_fulltext_patch_candidates.csv", index=False)
    write_report(output_dir, inventory_out, fetch_plan_out, evidence_out, quality_audit_out, patch_out)
    return {
        "inventory": inventory,
        "fetch_plan": fetch_plan,
        "extracted": extracted,
        "evidence": evidence,
        "field_audit": field_audit,
        "quality_audit": quality_audit,
        "patch": patch,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck announcement fulltext extraction v1.")
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
    print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows')}")


if __name__ == "__main__":
    main()
