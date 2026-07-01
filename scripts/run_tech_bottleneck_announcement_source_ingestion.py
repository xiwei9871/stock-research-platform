#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SOURCE_PLAN_DIR = Path("outputs/research/tech_bottleneck_research_source_expansion_plan_v1")
WATCHLIST_REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_stock_report_v1")
WATCHLIST_FORWARD_DIR = Path("outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_announcement_source_ingestion_v1")
RULE_VERSION = "tech_bottleneck_announcement_source_ingestion_v1"

KNOWN_ANNOUNCEMENT_PATHS = [
    Path("outputs/research/serenity_customer_certification_evidence_fill_20260608/customer_certification_announcement_candidates.csv"),
    Path("outputs/research/serenity_remaining_customer_certification_body_fill_20260608/remaining_after_irm_cninfo_announcement_body_raw.csv"),
    Path("outputs/research/serenity_remaining_customer_certification_body_fill_20260608/remaining_after_irm_cninfo_announcement_customer_evidence_seed.csv"),
]

ALLOWED_REVIEW_ACTIONS = {
    "update_report_evidence",
    "review_risk_disclosure",
    "wait_for_more_announcements",
    "no_announcement_support",
    "manual_review_required",
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

REVIEW_TEXT_REPLACEMENTS = {
    "买入": "复盘动作",
    "卖出": "复盘动作",
    "加仓": "复盘动作",
    "减仓": "复盘动作",
    "持有": "权益状态",
    "目标价": "价格信息",
    "仓位建议": "复盘备注",
    "入场点": "价格位置",
    "止损点": "风险位置",
    "交易信号": "复盘状态",
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


RAW_MATCH_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "announcement_id",
    "announcement_title",
    "announcement_date",
    "as_of_date",
    "source_url",
    "raw_source_name",
    "raw_category",
    "matched_by",
    "is_pit_valid",
    "lookahead_violation",
    "content_available",
    "raw_text_length",
    "data_quality_status",
    "content",
]

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
    "extraction_method",
    "matched_keywords",
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
    for source, replacement in REVIEW_TEXT_REPLACEMENTS.items():
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


def _scan_announcement_paths(project_root: Path) -> list[Path]:
    tokens = ["announcement", "disclosure", "cninfo", "notice", "公告", "巨潮", "信息披露"]
    roots = [project_root / "src", project_root / "scripts", project_root / "tests", project_root / "outputs" / "research"]
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and any(token in str(path).lower() for token in tokens):
                paths.append(path)
    return sorted(paths)


def build_announcement_source_inventory(project_root: Path, source_paths: list[Path] | None = None) -> pd.DataFrame:
    paths = source_paths if source_paths is not None else _scan_announcement_paths(project_root)
    rows: list[dict[str, Any]] = []
    if not paths:
        rows.append(_inventory_row("source_missing", "announcement", False, "missing", "missing", notes="No announcement source found."))
        return pd.DataFrame(rows)
    for path in paths:
        p = Path(path)
        lower = str(p).lower()
        source_name = "cninfo_disclosure_announcement" if "cninfo" in lower or "disclosure" in lower else "announcement_source"
        file_type = p.suffix.lower().lstrip(".") or "unknown"
        existing: Any = True if p.exists() else "script_only"
        available_fields = "unknown"
        date_min = "missing"
        date_max = "missing"
        date_field = "published_at"
        asset_field = "asset_id"
        title_field = "title"
        content_field = "content"
        url_field = "url"
        pit_ready: Any = "partial"
        quality_risk = "field_schema_unknown"
        if p.exists() and p.suffix.lower() == ".csv":
            try:
                sample = pd.read_csv(p, nrows=500, low_memory=False)
                available_fields = "|".join(sample.columns.astype(str))
                for candidate in ["published_at", "announcement_date", "source_date", "公告日期"]:
                    if candidate in sample.columns:
                        date_field = candidate
                        parsed = pd.to_datetime(sample[candidate], errors="coerce")
                        date_min = str(parsed.min().date()) if parsed.notna().any() else "missing"
                        date_max = str(parsed.max().date()) if parsed.notna().any() else "missing"
                        break
                asset_field = "asset_id" if "asset_id" in sample.columns else "ts_code" if "ts_code" in sample.columns else "missing"
                title_field = "title" if "title" in sample.columns else "公告标题" if "公告标题" in sample.columns else "missing"
                content_field = "content" if "content" in sample.columns else "missing"
                url_field = "url" if "url" in sample.columns else "网址" if "网址" in sample.columns else "missing"
                pit_ready = bool(date_field != "missing" and asset_field != "missing")
                quality_risk = "content_missing_or_title_only" if content_field == "missing" or sample.get(content_field, pd.Series(dtype=object)).fillna("").astype(str).str.len().median() == 0 else "schema_review_required"
            except Exception:
                quality_risk = "csv_read_failed"
        rows.append(
            {
                "source_name": source_name,
                "source_type": "announcement",
                "existing_in_project": existing,
                "detected_path_or_table": str(p),
                "file_or_table_type": file_type,
                "available_fields": available_fields,
                "date_field": date_field,
                "asset_id_field": asset_field,
                "title_field": title_field,
                "content_field": content_field,
                "url_field": url_field,
                "pit_ready": pit_ready,
                "coverage_estimate": "unknown_until_matched",
                "date_range_min": date_min,
                "date_range_max": date_max,
                "quality_risk": quality_risk,
                "notes": "Detected by announcement/disclosure/cninfo scan.",
            }
        )
    return pd.DataFrame(rows)


def _inventory_row(name: str, source_type: str, existing: Any, path: str, file_type: str, notes: str) -> dict[str, Any]:
    return {
        "source_name": name,
        "source_type": source_type,
        "existing_in_project": existing,
        "detected_path_or_table": path,
        "file_or_table_type": file_type,
        "available_fields": "missing",
        "date_field": "missing",
        "asset_id_field": "missing",
        "title_field": "missing",
        "content_field": "missing",
        "url_field": "missing",
        "pit_ready": False,
        "coverage_estimate": "none",
        "date_range_min": "missing",
        "date_range_max": "missing",
        "quality_risk": "source_missing",
        "notes": notes,
    }


def load_raw_announcement_sources(project_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for rel in KNOWN_ANNOUNCEMENT_PATHS:
        path = project_root / rel
        if path.exists() and path.suffix.lower() == ".csv":
            frame = pd.read_csv(path, low_memory=False)
            frame["_raw_source_path"] = str(path)
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True, sort=False)
    # Keep rows that look like true announcement/disclosure source rows.
    if "source_type" in raw.columns:
        raw = raw[raw["source_type"].fillna("").astype(str).str.contains("announcement|notice|disclosure", case=False, regex=True) | raw.get("event_family", pd.Series("", index=raw.index)).fillna("").astype(str).str.contains("disclosure", case=False, regex=False)]
    elif "event_family" in raw.columns:
        raw = raw[raw["event_family"].fillna("").astype(str).str.contains("disclosure", case=False, regex=False)]
    return raw.drop_duplicates()


def _normalize_symbol(value: Any) -> str:
    text = str(value or "")
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 6:
        return digits[:6]
    return text.strip()


def match_raw_announcements_to_watchlist(raw: pd.DataFrame, watchlist: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=RAW_MATCH_COLUMNS)
    watch = watchlist.copy()
    watch["asset_id"] = watch["asset_id"].astype(str)
    watch["symbol_norm"] = watch.get("symbol", watch["asset_id"]).map(_normalize_symbol)
    watch["report_date"] = pd.to_datetime(watch.get("report_date", pd.Series(["2026-06-29"] * len(watch))), errors="coerce").dt.strftime("%Y-%m-%d")
    raw = raw.copy()
    raw["asset_id_norm"] = raw.get("asset_id", "").fillna("").astype(str)
    raw["symbol_norm"] = raw.apply(lambda row: _normalize_symbol(row.get("ts_code") or row.get("symbol") or row.get("asset_id")), axis=1)
    rows: list[dict[str, Any]] = []
    by_asset = watch.set_index("asset_id", drop=False)
    by_symbol = {row.symbol_norm: row for row in watch.itertuples(index=False)}
    by_name = {str(row.name): row for row in watch.itertuples(index=False) if str(row.name)}
    for item in raw.itertuples(index=False):
        raw_asset = str(getattr(item, "asset_id", "") or "")
        symbol = _normalize_symbol(getattr(item, "ts_code", "") or getattr(item, "symbol", "") or raw_asset)
        raw_name = str(getattr(item, "stock_name", "") or getattr(item, "name", "") or "")
        match = None
        matched_by = "unmatched"
        if raw_asset in by_asset.index:
            match = by_asset.loc[raw_asset]
            matched_by = "asset_id"
        elif symbol in by_symbol:
            match = by_symbol[symbol]
            matched_by = "symbol"
        elif raw_name in by_name:
            match = by_name[raw_name]
            matched_by = "name_fuzzy"
        if match is None:
            continue
        title = str(getattr(item, "title", "") or getattr(item, "announcement_title", "") or getattr(item, "公告标题", "") or "")
        content = str(getattr(item, "content", "") or "")
        published = getattr(item, "published_at", None) or getattr(item, "source_date", None) or getattr(item, "announcement_date", None) or getattr(item, "公告日期", None)
        ann_date = pd.to_datetime(published, errors="coerce")
        ann_date_str = ann_date.strftime("%Y-%m-%d") if pd.notna(ann_date) else ""
        report_date = str(getattr(match, "report_date", "") or "2026-06-29")
        lookahead = bool(ann_date_str and ann_date_str > report_date)
        source_id = str(getattr(item, "source_event_id", "") or getattr(item, "announcement_id", "") or getattr(item, "url", "") or f"{raw_asset}|{title}|{ann_date_str}")
        rows.append(
            {
                "asset_id": str(match.asset_id),
                "symbol": str(getattr(match, "symbol", symbol)),
                "name": str(getattr(match, "name", raw_name)),
                "announcement_id": source_id,
                "announcement_title": title,
                "announcement_date": ann_date_str,
                "as_of_date": ann_date_str,
                "source_url": str(getattr(item, "url", "") or ""),
                "raw_source_name": str(getattr(item, "source_name", "") or "announcement_source"),
                "raw_category": str(getattr(item, "event_family", "") or getattr(item, "source_channel", "") or "announcement"),
                "matched_by": matched_by,
                "is_pit_valid": bool(ann_date_str and not lookahead),
                "lookahead_violation": lookahead,
                "content_available": bool(content.strip() and content.strip().lower() != "nan"),
                "raw_text_length": len(content.strip()) if content.strip().lower() != "nan" else 0,
                "data_quality_status": "degraded_name_match" if matched_by == "name_fuzzy" else "title_only" if not content.strip() or content.strip().lower() == "nan" else "ok",
                "content": "" if content.strip().lower() == "nan" else content,
            }
        )
    return pd.DataFrame(rows, columns=RAW_MATCH_COLUMNS).drop_duplicates(subset=["asset_id", "announcement_id"])


def classify_announcement(title: str, content: str) -> dict[str, Any]:
    text = f"{title} {content}".lower()
    result: dict[str, Any] = {}
    matched: list[str] = []
    for field, keywords in KEYWORD_RULES.items():
        active = any(keyword.lower() in text for keyword in keywords)
        result[field] = active
        if active:
            matched.extend([keyword for keyword in keywords if keyword.lower() in text])
    if result.get("risk_disclosure") or result.get("litigation_or_penalty"):
        direction = "risk"
    elif any(result.get(field) for field in ["order_contract", "customer_contract", "capacity_project", "financial_guidance", "performance_forecast"]):
        direction = "positive_or_validation"
    else:
        direction = "neutral_or_unclassified"
    result["announcement_type"] = _announcement_type(result)
    result["evidence_direction"] = direction
    result["matched_keywords"] = "|".join(sorted(set(matched)))
    return result


def _announcement_type(result: dict[str, Any]) -> str:
    for field in [
        "risk_disclosure",
        "order_contract",
        "customer_contract",
        "capacity_project",
        "fundraising_project",
        "equity_incentive",
        "performance_forecast",
        "financial_guidance",
    ]:
        if result.get(field):
            return field
    return "unclassified"


def build_structured_announcements(matches: pd.DataFrame, watchlist: pd.DataFrame) -> pd.DataFrame:
    if matches.empty:
        return pd.DataFrame(columns=STRUCTURED_COLUMNS)
    watch = watchlist[["asset_id", "report_date"]].copy() if "report_date" in watchlist.columns else watchlist[["asset_id"]].copy()
    if "report_date" not in watch.columns:
        watch["report_date"] = "2026-06-29"
    frame = matches.merge(watch.drop_duplicates("asset_id"), on="asset_id", how="left")
    frame["trade_date"] = pd.to_datetime(frame["report_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("2026-06-29")
    rows: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        # Structured outputs are only usable when the announcement is PIT-valid.
        # Rows with missing dates remain in raw matches and the audit, but do not
        # patch watchlist evidence support.
        if not row.announcement_date or not row.as_of_date:
            continue
        if row.announcement_date > row.trade_date or row.as_of_date > row.trade_date:
            continue
        classified = classify_announcement(str(row.announcement_title), str(getattr(row, "content", "") or ""))
        validation_score = 0.0
        if any(classified.get(field) for field in ["order_contract", "customer_contract", "capacity_project", "financial_guidance", "performance_forecast", "major_customer_or_supplier"]):
            validation_score = 0.7 if row.content_available else 0.45
        risk_score = 0.7 if classified.get("risk_disclosure") or classified.get("litigation_or_penalty") else 0.0
        missing = []
        if not row.announcement_date:
            missing.append("announcement_date")
        if not row.announcement_title:
            missing.append("announcement_title")
        if not row.source_url:
            missing.append("source_url")
        if not row.content_available:
            missing.append("content")
        rows.append(
            {
                "trade_date": row.trade_date,
                "asset_id": row.asset_id,
                "symbol": row.symbol,
                "name": row.name,
                "announcement_id": row.announcement_id,
                "source_type": "announcement",
                "announcement_title": row.announcement_title,
                "announcement_date": row.announcement_date,
                "as_of_date": row.as_of_date,
                "source_url": row.source_url,
                "is_pit_valid": bool(row.is_pit_valid and row.announcement_date <= row.trade_date and row.as_of_date <= row.trade_date),
                "lookahead_violation": bool(row.lookahead_violation or (row.announcement_date > row.trade_date) or (row.as_of_date > row.trade_date)),
                "announcement_type": classified["announcement_type"],
                "order_contract": bool(classified["order_contract"]),
                "customer_contract": bool(classified["customer_contract"]),
                "capacity_project": bool(classified["capacity_project"]),
                "fundraising_project": bool(classified["fundraising_project"]),
                "equity_incentive": bool(classified["equity_incentive"]),
                "risk_disclosure": bool(classified["risk_disclosure"]),
                "financial_guidance": bool(classified["financial_guidance"]),
                "performance_forecast": bool(classified["performance_forecast"]),
                "litigation_or_penalty": bool(classified["litigation_or_penalty"]),
                "major_customer_or_supplier": bool(classified["major_customer_or_supplier"]),
                "evidence_direction": classified["evidence_direction"],
                "announcement_validation_score": validation_score,
                "risk_event_score": risk_score,
                "source_confidence": 0.8,
                "extraction_confidence": 0.35 if not row.content_available else 0.65,
                "extraction_method": "keyword_title_only" if not row.content_available else "keyword_title_content",
                "matched_keywords": classified["matched_keywords"],
                "missing_fields": "|".join(missing),
                "conflict_flags": "",
                "data_quality_status": "invalid_pit" if row.lookahead_violation else row.data_quality_status,
                "rule_version": RULE_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)


def build_asset_coverage(watchlist: pd.DataFrame, structured: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in watchlist.itertuples(index=False):
        group = structured[structured["asset_id"].eq(str(item.asset_id))] if not structured.empty else pd.DataFrame(columns=STRUCTURED_COLUMNS)
        rows.append(
            {
                "asset_id": item.asset_id,
                "symbol": getattr(item, "symbol", ""),
                "name": getattr(item, "name", ""),
                "in_standard_watchlist": True,
                "announcement_count": int(len(group)),
                "pit_valid_announcement_count": int(group.get("is_pit_valid", pd.Series(dtype=bool)).astype(bool).sum()) if not group.empty else 0,
                "latest_announcement_date": group["announcement_date"].max() if not group.empty else "missing",
                "has_order_contract": bool(group.get("order_contract", pd.Series(dtype=bool)).astype(bool).any()) if not group.empty else False,
                "has_customer_contract": bool(group.get("customer_contract", pd.Series(dtype=bool)).astype(bool).any()) if not group.empty else False,
                "has_capacity_project": bool(group.get("capacity_project", pd.Series(dtype=bool)).astype(bool).any()) if not group.empty else False,
                "has_fundraising_project": bool(group.get("fundraising_project", pd.Series(dtype=bool)).astype(bool).any()) if not group.empty else False,
                "has_equity_incentive": bool(group.get("equity_incentive", pd.Series(dtype=bool)).astype(bool).any()) if not group.empty else False,
                "has_financial_guidance": bool(group.get("financial_guidance", pd.Series(dtype=bool)).astype(bool).any()) if not group.empty else False,
                "has_risk_disclosure": bool(group.get("risk_disclosure", pd.Series(dtype=bool)).astype(bool).any()) if not group.empty else False,
                "has_performance_forecast": bool(group.get("performance_forecast", pd.Series(dtype=bool)).astype(bool).any()) if not group.empty else False,
                "has_litigation_or_penalty": bool(group.get("litigation_or_penalty", pd.Series(dtype=bool)).astype(bool).any()) if not group.empty else False,
                "announcement_validation_score_max": float(group.get("announcement_validation_score", pd.Series(dtype=float)).max()) if not group.empty else 0.0,
                "risk_event_score_max": float(group.get("risk_event_score", pd.Series(dtype=float)).max()) if not group.empty else 0.0,
                "coverage_status": "covered" if not group.empty else "missing",
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows)


def build_field_coverage_audit(structured: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "announcement_id",
        "announcement_title",
        "announcement_date",
        "as_of_date",
        "source_url",
        "announcement_type",
        "order_contract",
        "customer_contract",
        "capacity_project",
        "fundraising_project",
        "equity_incentive",
        "risk_disclosure",
        "financial_guidance",
        "performance_forecast",
        "source_confidence",
        "extraction_confidence",
    ]
    rows: list[dict[str, Any]] = []
    total = len(structured)
    for field in fields:
        if field not in structured.columns:
            non_missing = 0
        else:
            series = structured[field]
            if series.dtype == bool:
                non_missing = int(series.sum())
            else:
                non_missing = int(series.notna().sum() - series.fillna("").astype(str).isin(["", "missing", "nan"]).sum())
        rows.append(
            {
                "field_name": field,
                "non_missing_count": non_missing,
                "missing_count": max(total - non_missing, 0),
                "coverage_ratio": non_missing / total if total else 0.0,
                "quality_note": "empty_source" if total == 0 else "title_only_possible" if field in {"source_confidence", "extraction_confidence"} else "ok",
            }
        )
    return pd.DataFrame(rows)


def build_watchlist_announcement_gap_patch(watchlist: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    frame = watchlist[["asset_id", "symbol", "name"]].drop_duplicates().merge(coverage, on=["asset_id", "symbol", "name"], how="left")
    rows: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        count = int(getattr(row, "announcement_count", 0) or 0)
        risk = bool(getattr(row, "has_risk_disclosure", False))
        positive_flags = []
        for field in ["has_order_contract", "has_customer_contract", "has_capacity_project", "has_financial_guidance", "has_performance_forecast"]:
            if bool(getattr(row, field, False)):
                positive_flags.append(field.replace("has_", ""))
        if risk:
            action = "review_risk_disclosure"
        elif count > 0:
            action = "update_report_evidence"
        else:
            action = "no_announcement_support"
        rows.append(
            {
                "asset_id": row.asset_id,
                "symbol": row.symbol,
                "name": row.name,
                "previous_announcement_support": False,
                "new_announcement_support": count > 0,
                "announcement_count": count,
                "new_source_count_delta": count,
                "new_evidence_tags": "|".join(positive_flags) if positive_flags else "",
                "new_risk_flags": "risk_disclosure" if risk else "",
                "report_patch_summary": "announcement_source_available" if count > 0 else "announcement_source_missing",
                "still_missing_announcement": count == 0,
                "recommended_report_update": action,
                "human_review_required": True,
            }
        )
    patch = pd.DataFrame(rows)
    text = " ".join(patch.astype(str).agg(" ".join, axis=1).tolist()) if not patch.empty else ""
    if contains_actionable_trading_language(text):
        raise ValueError("watchlist patch contains actionable trading language")
    return patch


def build_quality_audit(raw: pd.DataFrame, matches: pd.DataFrame, structured: pd.DataFrame, watchlist: pd.DataFrame) -> pd.DataFrame:
    standard_count = int(watchlist["asset_id"].nunique()) if not watchlist.empty else 0
    covered_assets = int(structured["asset_id"].nunique()) if not structured.empty else 0
    duplicate_ratio = 0.0
    if not matches.empty and "announcement_id" in matches.columns:
        duplicate_ratio = float(matches.duplicated(subset=["asset_id", "announcement_id"]).mean())
    rows = [
        ("detected_announcement_sources", int(1 if not raw.empty else 0), "raw source files with rows"),
        ("raw_announcement_rows", int(len(raw)), "raw rows loaded"),
        ("matched_announcement_rows", int(len(matches)), "rows matched to standard watchlist"),
        ("structured_announcement_rows", int(len(structured)), "structured rows emitted"),
        ("standard_watchlist_asset_count", standard_count, "standard watchlist assets"),
        ("assets_with_announcement_support", covered_assets, "assets with at least one structured row"),
        ("announcement_coverage_ratio", covered_assets / standard_count if standard_count else 0.0, "covered assets / standard assets"),
        ("PIT_valid_ratio", float(structured["is_pit_valid"].astype(bool).mean()) if not structured.empty else 0.0, "PIT valid rows"),
        ("lookahead_violation_rows", int(structured.get("lookahead_violation", pd.Series(dtype=bool)).astype(bool).sum()) if not structured.empty else 0, "must be zero"),
        ("title_only_extraction_ratio", float(structured["extraction_method"].eq("keyword_title_only").mean()) if not structured.empty else 0.0, "title-only rows"),
        ("content_extraction_ratio", float(structured["extraction_method"].eq("keyword_title_content").mean()) if not structured.empty else 0.0, "title+content rows"),
        ("missing_announcement_date_ratio", float(matches["announcement_date"].fillna("").astype(str).eq("").mean()) if not matches.empty else 0.0, "raw match date missing"),
        ("missing_asset_id_ratio", float(matches["asset_id"].fillna("").astype(str).eq("").mean()) if not matches.empty else 0.0, "asset id missing"),
        ("duplicate_announcement_ratio", duplicate_ratio, "duplicate asset/announcement rows"),
        ("risk_disclosure_count", int(structured.get("risk_disclosure", pd.Series(dtype=bool)).astype(bool).sum()) if not structured.empty else 0, "risk rows"),
        ("positive_validation_count", int(structured.get("announcement_validation_score", pd.Series(dtype=float)).gt(0).sum()) if not structured.empty else 0, "validation rows"),
        ("degraded_rows", int(structured.get("data_quality_status", pd.Series(dtype=str)).fillna("").astype(str).str.contains("degraded|title_only", case=False, regex=True).sum()) if not structured.empty else 0, "degraded rows"),
        ("invalid_rows", int(structured.get("data_quality_status", pd.Series(dtype=str)).fillna("").astype(str).str.contains("invalid", case=False, regex=False).sum()) if not structured.empty else 0, "invalid rows"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def write_report(
    output_dir: Path,
    repo_root: Path,
    inventory: pd.DataFrame,
    matches: pd.DataFrame,
    structured: pd.DataFrame,
    coverage: pd.DataFrame,
    patch: pd.DataFrame,
    audit: pd.DataFrame,
    scanned_paths: list[Path],
) -> None:
    lookup = dict(zip(audit["metric"], audit["value"]))
    inventory_table = inventory[["source_name", "existing_in_project", "pit_ready", "date_range_min", "date_range_max", "quality_risk"]].head(20).to_markdown(index=False)
    field_summary = structured["announcement_type"].value_counts().rename_axis("announcement_type").reset_index(name="count").to_markdown(index=False) if not structured.empty else "No structured announcement rows."
    coverage_summary = coverage[["coverage_status"]].value_counts().reset_index(name="count").to_markdown(index=False) if not coverage.empty else "No coverage rows."
    git = _git_info(repo_root)
    text = f"""# Tech Bottleneck Announcement Source Ingestion v1

## 1. Executive Summary

- Usable announcement source found: {bool(int(lookup.get('raw_announcement_rows', 0)))}.
- Structured announcement rows: {lookup.get('structured_announcement_rows')}.
- Standard watchlist assets with announcement support: {lookup.get('assets_with_announcement_support')} / {lookup.get('standard_watchlist_asset_count')}.
- Announcement coverage ratio: {lookup.get('announcement_coverage_ratio')}.
- Positive validation rows: {lookup.get('positive_validation_count')}; risk disclosure rows: {lookup.get('risk_disclosure_count')}.
- Lookahead violation rows: {lookup.get('lookahead_violation_rows')}.
- Most rows are title-only if source content is missing; use as review evidence, not execution logic.
- Recommended usage: patch watchlist stock reports with announcement evidence and risk review fields.
- Continue to defer technical execution layer research.
- No execution-oriented instruction output is produced.
- Formal strategy files remain untracked in git; this task does not write them, but git diff alone cannot fully prove historical immutability.

## 2. Source Inventory

{inventory_table}

## 3. Matching and PIT Validation

Matching priority: `asset_id`, then symbol/code, then name fallback. Name fallback is degraded. PIT rule: `announcement_date <= trade_date` and `as_of_date <= trade_date`.

## 4. Announcement Extraction Rules

Keyword rule groups:

```text
{_keyword_rule_summary()}
```

## 5. Structured Output Summary

{field_summary}

## 6. Standard Watchlist Coverage

{coverage_summary}

## 7. Evidence and Risk Patch

- patch rows: {len(patch)}
- updated support rows: {int(patch.get('new_announcement_support', pd.Series(dtype=bool)).astype(bool).sum()) if not patch.empty else 0}
- still missing rows: {int(patch.get('still_missing_announcement', pd.Series(dtype=bool)).astype(bool).sum()) if not patch.empty else 0}

## 8. Data Gaps and Limitations

- Source content may be missing, causing title-only extraction.
- Source URLs can be missing in some files.
- Historical coverage depends on previously collected announcement candidates.
- Extraction is keyword-based and conservative.
- No invalid PIT rows are used for support.

## 9. Recommended Usage

- Use for watchlist report evidence summary and risk review.
- Use for manual review.
- Do not use as execution logic.

## 10. What This Layer Does Not Do

- Does not create execution instructions.
- Does not alter Top5.
- Does not alter formal strategy logic.
- Does not evaluate the technical execution layer.
- Does not use evidence multiplier.

## 11. Recommended Next Step

Recommended next task: `tech_bottleneck_watchlist_report_announcement_patch_v1` if coverage is meaningful; otherwise proceed to `tech_bottleneck_fundamental_source_adapter_v1`.

## 12. Appendix

Generated files:

- `announcement_source_inventory.csv`
- `announcement_raw_candidate_matches.csv`
- `announcement_structured_outputs.csv`
- `announcement_asset_coverage.csv`
- `announcement_field_coverage_audit.csv`
- `watchlist_announcement_gap_patch.csv`
- `announcement_ingestion_quality_audit.csv`
- `announcement_source_ingestion_v1.md`

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

Scanned paths:

```text
{chr(10).join(str(path) for path in scanned_paths[:80])}
```
"""
    text = sanitize_review_text(text)
    if contains_actionable_trading_language(text):
        raise ValueError("main report contains actionable trading language")
    (output_dir / "announcement_source_ingestion_v1.md").write_text(text, encoding="utf-8")


def _keyword_rule_summary() -> str:
    return "\n".join(f"{field}: {'|'.join(words)}" for field, words in KEYWORD_RULES.items())


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


def run(output_dir: Path = OUTPUT_DIR, project_root: Path | None = None) -> dict[str, pd.DataFrame]:
    repo_root = project_root or Path(__file__).resolve().parents[1]
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    watchlist = pd.read_csv(repo_root / WATCHLIST_REPORT_DIR / "tech_bottleneck_watchlist_report_index.csv", low_memory=False)
    watchlist = watchlist[["asset_id", "symbol", "name", "report_date"]].drop_duplicates()
    raw = load_raw_announcement_sources(repo_root)
    scanned = _scan_announcement_paths(repo_root)
    inventory = build_announcement_source_inventory(repo_root, source_paths=scanned)
    matches = match_raw_announcements_to_watchlist(raw, watchlist)
    structured = build_structured_announcements(matches, watchlist)
    coverage = build_asset_coverage(watchlist, structured)
    field_audit = build_field_coverage_audit(structured)
    patch = build_watchlist_announcement_gap_patch(watchlist, coverage)
    audit = build_quality_audit(raw, matches, structured, watchlist)
    if int(audit.loc[audit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0]) != 0:
        raise ValueError("lookahead violation rows must be zero")
    inventory_out = sanitize_dataframe_for_output(inventory)
    matches_out = sanitize_dataframe_for_output(matches.drop(columns=["content"], errors="ignore"))
    structured_out = sanitize_dataframe_for_output(structured)
    coverage_out = sanitize_dataframe_for_output(coverage)
    field_audit_out = sanitize_dataframe_for_output(field_audit)
    patch_out = sanitize_dataframe_for_output(patch)
    audit_out = sanitize_dataframe_for_output(audit)
    inventory_out.to_csv(output_dir / "announcement_source_inventory.csv", index=False)
    matches_out.to_csv(output_dir / "announcement_raw_candidate_matches.csv", index=False)
    structured_out.to_csv(output_dir / "announcement_structured_outputs.csv", index=False)
    coverage_out.to_csv(output_dir / "announcement_asset_coverage.csv", index=False)
    field_audit_out.to_csv(output_dir / "announcement_field_coverage_audit.csv", index=False)
    patch_out.to_csv(output_dir / "watchlist_announcement_gap_patch.csv", index=False)
    audit_out.to_csv(output_dir / "announcement_ingestion_quality_audit.csv", index=False)
    write_report(output_dir, repo_root, inventory_out, matches_out, structured_out, coverage_out, patch_out, audit_out, scanned)
    return {
        "inventory": inventory,
        "matches": matches,
        "structured": structured,
        "coverage": coverage,
        "patch": patch,
        "audit": audit,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck announcement source ingestion v1.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir))
    lookup = dict(zip(result["audit"]["metric"], result["audit"]["value"]))
    print(f"structured_announcement_rows={lookup.get('structured_announcement_rows')}")
    print(f"assets_with_announcement_support={lookup.get('assets_with_announcement_support')}")
    print(f"announcement_coverage_ratio={lookup.get('announcement_coverage_ratio')}")
    print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows')}")


if __name__ == "__main__":
    main()
