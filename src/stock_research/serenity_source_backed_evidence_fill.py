from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.stock_report_pdf_backfill import fetch_pdf_text


SOURCE_BACKED_FIELDS = [
    "revenue_exposure_bucket",
    "customer_certification_stage",
    "supplier_concentration_evidence",
]
SUPPLIER_FIELD_ALIASES = ["supplier_concentration_type", "supplier_concentration_evidence"]

FIELD_SOURCE_NEEDS = {
    "revenue_exposure_bucket": "annual report segment revenue, product revenue split, order backlog, or broker product breakdown",
    "customer_certification_stage": "customer validation, design-in, qualification, fixed-point, order, delivery, or mass-production evidence",
    "supplier_concentration_evidence": "market share, import dependency, domestic substitute scarcity, supplier count, or single/leading supplier evidence",
    "supplier_concentration_type": "market share, import dependency, domestic substitute scarcity, supplier count, or single/leading supplier evidence",
}

PRIMARY_SOURCE_TYPES = {
    "akshare_mainbiz",
    "annual_report",
    "company_announcement",
    "investor_qa",
    "broker_report",
    "research_report",
    "news",
    "structured_report_extract",
}

STRONG_TIERS = {"tier1", "primary", "primary_strong", "strong"}

REVENUE_EVIDENCE_KEYWORDS = {"收入", "业务", "分部", "产品", "核心", "占比", "利润", "放量"}
CUSTOMER_EVIDENCE_KEYWORDS = {"客户", "认证", "验证", "design-in", "design in", "定点", "订单", "交付", "量产", "出货", "放量"}
SUPPLIER_EVIDENCE_KEYWORDS = {"进口", "国产替代", "集中", "份额", "稀缺", "少数", "独供", "龙头", "瓶颈"}
PDF_REVENUE_EVIDENCE_KEYWORDS = {"营业收入", "主营业务", "产品收入", "分部收入", "订单", "放量", "出货", "产能", "业务收入"}
PDF_CUSTOMER_EVIDENCE_KEYWORDS = CUSTOMER_EVIDENCE_KEYWORDS
PDF_SUPPLIER_EVIDENCE_KEYWORDS = {
    "进口依赖",
    "国产替代",
    "供应稀缺",
    "供应商集中",
    "市场份额",
    "市占率",
    "独供",
    "龙头",
    "瓶颈",
}
ORDER_DELIVERY_KEYWORDS = {"订单", "交付", "量产", "出货", "批量", "放量", "供货"}
STRONG_ORDER_DELIVERY_KEYWORDS = {"订单", "交付", "量产", "出货", "放量", "供货"}
DESIGN_IN_STAGE_KEYWORDS = {"design-in", "design in", "定点", "导入", "指定供应商"}
CUSTOMER_VALIDATION_STAGE_KEYWORDS = {"客户认证", "客户验证", "通过认证", "通过验证", "验证通过", "合格供应商"}
CUSTOMER_NEGATIVE_CONTEXT_KEYWORDS = {"未披露", "未说明", "无客户认证", "无认证", "不涉及"}
CUSTOMER_NEGATIVE_CONTEXT_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"尚未.{0,8}(取得|通过|获得).{0,6}(客户)?(认证|验证)",
        r"未取得.{0,6}(客户)?(认证|验证)",
        r"未通过.{0,6}(客户)?(认证|验证)",
        r"尚未.{0,10}(定点|量产|供货|交付|出货|批量)",
    ]
]
CUSTOMER_UNSUBSTANTIATED_CONTEXT_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"(客户|认证|验证|订单|产能).{0,24}(以|请以).{0,24}(公告|定期报告|临时公告).{0,12}为准",
        r"具体经营信息.{0,50}(公告|定期报告|临时公告).{0,20}为准",
        r"积极争取.{0,8}(市场)?订单",
        r"(不便|无法).{0,12}(披露|透露).{0,12}(客户|订单|认证|验证)",
    ]
]
CUSTOMER_STRONG_STAGE_VALUES = {
    "order",
    "order_or_delivery",
    "customer_validation_or_delivery",
    "design_in",
    "certification",
    "certification_or_qualification_required",
}


def run_serenity_source_backed_evidence_fill(
    *,
    structured_detail_path: str | Path,
    output_dir: str | Path,
    evidence_seed_path: str | Path | None = None,
    run_id: str = "serenity_source_backed_evidence_fill",
) -> dict[str, Any]:
    structured_detail = pd.read_csv(structured_detail_path, low_memory=False)
    evidence_seed = (
        pd.read_csv(evidence_seed_path, low_memory=False)
        if evidence_seed_path is not None and Path(evidence_seed_path).exists()
        else pd.DataFrame()
    )
    return build_serenity_source_backed_evidence_fill(
        structured_detail=structured_detail,
        evidence_seed=evidence_seed,
        output_dir=output_dir,
        run_id=run_id,
    )


def build_serenity_source_backed_evidence_fill(
    *,
    structured_detail: pd.DataFrame,
    evidence_seed: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
    run_id: str = "serenity_source_backed_evidence_fill",
) -> dict[str, Any]:
    detail_input = _prepare_structured_detail(structured_detail)
    evidence = _prepare_evidence_seed(evidence_seed)
    evidence_lookup = _evidence_lookup(evidence)
    fields = _source_backed_fields(detail_input, evidence)

    long = _build_long(detail_input, evidence_lookup, fields)
    detail = _build_detail(detail_input, long, fields)
    summary = _build_summary(long)
    manual_queue = _build_manual_queue(long)
    report = _render_report(summary, manual_queue, run_id)

    paths: dict[str, str] = {}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        files = {
            "detail": output / "serenity_source_backed_evidence_detail.csv",
            "long": output / "serenity_source_backed_evidence_long.csv",
            "summary": output / "serenity_source_backed_gap_summary.csv",
            "manual_queue": output / "top_priority_manual_evidence_queue.csv",
            "report": output / "serenity_source_backed_evidence_report.md",
        }
        detail.to_csv(files["detail"], index=False)
        long.to_csv(files["long"], index=False)
        summary.to_csv(files["summary"], index=False)
        manual_queue.to_csv(files["manual_queue"], index=False)
        files["report"].write_text(report, encoding="utf-8")
        paths = {key: str(value) for key, value in files.items()}

    return {
        "detail": detail,
        "long": long,
        "summary": summary,
        "manual_queue": manual_queue,
        "report": report,
        "paths": paths,
    }


def build_report_index_evidence_seed(
    *,
    structured_detail: pd.DataFrame,
    report_index: pd.DataFrame,
) -> pd.DataFrame:
    detail = _prepare_structured_detail(structured_detail)
    reports = report_index.copy()
    for column in [
        "asset_id",
        "stock_name",
        "publish_date",
        "broker",
        "report_title",
        "content",
        "pdf_path",
        "detail_url",
    ]:
        if column not in reports.columns:
            reports[column] = ""
    reports["asset_id"] = reports["asset_id"].map(_text)
    detail_by_asset = {row["asset_id"]: row for row in detail.to_dict("records")}
    rows = []
    for report in reports.to_dict("records"):
        asset_id = _text(report.get("asset_id"))
        candidate = detail_by_asset.get(asset_id)
        if not candidate:
            continue
        report_text = " ".join(
            [
                _text(report.get("report_title")),
                _text(report.get("content")),
            ]
        )
        common = {
            "asset_id": asset_id,
            "source_type": "broker_report",
            "source_path": _text(report.get("pdf_path")) or _text(report.get("detail_url")),
            "source_date": _text(report.get("publish_date")),
            "evidence_tier": "tier1",
            "excerpt": _excerpt(report_text),
        }
        if _has_any(report_text, REVENUE_EVIDENCE_KEYWORDS):
            supports_value = _supportable_value(_text(candidate.get("revenue_exposure_bucket")))
            rows.append(
                {
                    **common,
                    "field": "revenue_exposure_bucket",
                    "supports_value": supports_value,
                    "claim": _claim(report, "研报包含产品、业务、收入、利润或放量相关表述，可用于收入暴露审计。"),
                    "evidence_tier": "tier1" if supports_value else "tier2",
                }
            )
        if _has_any(report_text, CUSTOMER_EVIDENCE_KEYWORDS):
            supports_value = _supportable_value(_text(candidate.get("customer_certification_stage")))
            rows.append(
                {
                    **common,
                    "field": "customer_certification_stage",
                    "supports_value": supports_value,
                    "claim": _claim(report, "研报包含客户、认证、订单、交付、量产或放量相关表述，可用于客户阶段审计。"),
                    "evidence_tier": "tier1" if supports_value else "tier2",
                }
            )
        supplier_field = "supplier_concentration_type" if "supplier_concentration_type" in detail.columns else "supplier_concentration_evidence"
        if _has_any(report_text, SUPPLIER_EVIDENCE_KEYWORDS):
            supports_value = _supportable_value(_text(candidate.get(supplier_field)))
            rows.append(
                {
                    **common,
                    "field": supplier_field,
                    "supports_value": supports_value,
                    "claim": _claim(report, "研报包含进口依赖、国产替代、集中度、份额、稀缺或龙头相关表述，可用于供应集中度审计。"),
                    "evidence_tier": "tier1" if supports_value else "tier2",
                }
            )
    columns = [
        "asset_id",
        "field",
        "source_type",
        "source_path",
        "source_date",
        "supports_value",
        "claim",
        "evidence_tier",
        "excerpt",
    ]
    return pd.DataFrame(rows, columns=columns)


def build_pdf_text_industry_chain_evidence_seed(
    *,
    structured_detail: pd.DataFrame,
    report_index: pd.DataFrame,
    fetcher: Any | None = None,
) -> pd.DataFrame:
    detail = _prepare_structured_detail(structured_detail)
    reports = report_index.copy()
    for column in [
        "asset_id",
        "stock_name",
        "publish_date",
        "broker",
        "report_title",
        "pdf_path",
        "source_url",
        "detail_url",
        "source_type",
    ]:
        if column not in reports.columns:
            reports[column] = ""
    reports["asset_id"] = reports["asset_id"].map(_text)
    detail_by_asset = {row["asset_id"]: row for row in detail.to_dict("records")}
    fetch = fetcher or fetch_pdf_text
    rows = []
    for report in reports.to_dict("records"):
        asset_id = _text(report.get("asset_id"))
        candidate = detail_by_asset.get(asset_id)
        if not candidate:
            continue
        source_path = _text(report.get("pdf_path")) or _text(report.get("source_url")) or _text(report.get("detail_url"))
        if not source_path:
            continue
        try:
            pdf_text = fetch(source_path)
        except Exception:
            continue
        common = {
            "asset_id": asset_id,
            "source_type": _text(report.get("source_type")) or "broker_report",
            "source_path": source_path,
            "source_date": _text(report.get("publish_date")),
            "evidence_tier": "tier1",
        }
        for field, keywords, fallback in [
            (
                "revenue_exposure_bucket",
                PDF_REVENUE_EVIDENCE_KEYWORDS,
                "PDF全文包含产品、业务、收入、订单或放量相关表述，可用于收入暴露审计。",
            ),
            (
                "customer_certification_stage",
                PDF_CUSTOMER_EVIDENCE_KEYWORDS,
                "PDF全文包含客户、认证、订单、交付、量产或供货相关表述，可用于客户阶段审计。",
            ),
            (
                "supplier_concentration_type" if "supplier_concentration_type" in detail.columns else "supplier_concentration_evidence",
                PDF_SUPPLIER_EVIDENCE_KEYWORDS,
                "PDF全文包含国产替代、进口依赖、稀缺、集中度、份额或龙头相关表述，可用于供应链稀缺性审计。",
            ),
        ]:
            excerpt = _matching_excerpt(pdf_text, keywords)
            if not excerpt:
                continue
            supports_value = _supportable_value(_text(candidate.get(field)))
            rows.append(
                {
                    **common,
                    "field": field,
                    "supports_value": supports_value,
                    "claim": _claim(report, fallback),
                    "evidence_tier": "tier1" if supports_value else "tier2",
                    "excerpt": excerpt,
                }
            )
    columns = [
        "asset_id",
        "field",
        "source_type",
        "source_path",
        "source_date",
        "supports_value",
        "claim",
        "evidence_tier",
        "excerpt",
    ]
    return pd.DataFrame(rows, columns=columns)


def build_customer_certification_evidence_seed(
    *,
    structured_detail: pd.DataFrame,
    announcements: pd.DataFrame | None = None,
    investor_qa: pd.DataFrame | None = None,
    reports: pd.DataFrame | None = None,
) -> pd.DataFrame:
    detail = _prepare_structured_detail(structured_detail)
    detail_by_asset = {row["asset_id"]: row for row in detail.to_dict("records")}
    rows: list[dict[str, str]] = []
    rows.extend(
        _customer_seed_from_frame(
            frame=announcements,
            detail_by_asset=detail_by_asset,
            source_type="company_announcement",
            text_columns=["title", "content", "summary"],
            date_columns=["published_at", "announcement_date", "trade_date"],
            path_columns=["url", "source_event_id", "source_path"],
            source_name_columns=["source_name", "source_channel"],
            fallback="公告提到客户认证、验证、定点、订单、交付、量产或出货相关信息。",
        )
    )
    rows.extend(
        _customer_seed_from_frame(
            frame=investor_qa,
            detail_by_asset=detail_by_asset,
            source_type="investor_qa",
            text_columns=["summary", "question", "answer", "content", "survey_type", "institution_names"],
            date_columns=["survey_date", "announcement_date", "published_at"],
            path_columns=["url", "source_url", "event_id"],
            source_name_columns=["source", "source_endpoint"],
            fallback="投资者调研/问答提到客户验证、订单、交付、量产或导入相关信息。",
        )
    )
    rows.extend(
        _customer_seed_from_frame(
            frame=reports,
            detail_by_asset=detail_by_asset,
            source_type="broker_report",
            text_columns=["report_title", "raw_summary", "content", "company_view", "industry_view"],
            date_columns=["publish_date", "report_date"],
            path_columns=["source_url", "pdf_path", "detail_url"],
            source_name_columns=["broker", "source_name"],
            fallback="研报提到客户认证、验证、定点、订单、交付、量产或出货相关信息。",
        )
    )
    columns = [
        "asset_id",
        "field",
        "source_type",
        "source_path",
        "source_date",
        "supports_value",
        "claim",
        "evidence_tier",
        "excerpt",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns).drop_duplicates().reset_index(drop=True)


def _prepare_structured_detail(frame: pd.DataFrame) -> pd.DataFrame:
    detail = frame.copy()
    base_columns = ["asset_id", "stock_name", "primary_chain_id", "evidence_source_provenance", "source_provenance"]
    for column in base_columns + ["revenue_exposure_bucket", "customer_certification_stage"]:
        if column not in detail.columns:
            detail[column] = ""
    if not any(column in detail.columns for column in SUPPLIER_FIELD_ALIASES):
        detail["supplier_concentration_evidence"] = ""
    detail["asset_id"] = detail["asset_id"].map(_text)
    detail["stock_name"] = detail["stock_name"].map(_text)
    detail["primary_chain_id"] = detail["primary_chain_id"].map(_text)
    return detail.reset_index(drop=True)


def _customer_seed_from_frame(
    *,
    frame: pd.DataFrame | None,
    detail_by_asset: dict[str, dict[str, Any]],
    source_type: str,
    text_columns: list[str],
    date_columns: list[str],
    path_columns: list[str],
    source_name_columns: list[str],
    fallback: str,
) -> list[dict[str, str]]:
    if frame is None or frame.empty:
        return []
    source = frame.copy()
    if "asset_id" not in source.columns:
        return []
    source["asset_id"] = source["asset_id"].map(_text)
    rows: list[dict[str, str]] = []
    for item in source.to_dict("records"):
        asset_id = _text(item.get("asset_id"))
        candidate = detail_by_asset.get(asset_id)
        if not candidate:
            continue
        text = _joined_columns(item, text_columns)
        keyword_text = _normalize_customer_keyword_text(text)
        if not _has_any(keyword_text, CUSTOMER_EVIDENCE_KEYWORDS):
            continue
        if _has_negative_customer_context(text) or _has_unsubstantiated_customer_context(text):
            continue
        supports_value = _derive_customer_stage_from_text(keyword_text) or _customer_support_value(
            candidate.get("customer_certification_stage")
        )
        if not supports_value:
            continue
        rows.append(
            {
                "asset_id": asset_id,
                "field": "customer_certification_stage",
                "source_type": source_type,
                "source_path": _first_text(item, path_columns),
                "source_date": _first_text(item, date_columns)[:10],
                "supports_value": supports_value,
                "claim": _source_claim(item, source_name_columns, fallback),
                "evidence_tier": "tier1",
                "excerpt": _excerpt(text),
            }
        )
    return rows


def _customer_support_value(value: Any) -> str:
    text = _supportable_value(_text(value))
    if not text:
        return ""
    return text if text in CUSTOMER_STRONG_STAGE_VALUES else ""


def _derive_customer_stage_from_text(text: str) -> str:
    if _has_any(text, STRONG_ORDER_DELIVERY_KEYWORDS):
        return "order_or_delivery"
    if _has_any(text, DESIGN_IN_STAGE_KEYWORDS):
        return "design_in"
    if _has_any(text, CUSTOMER_VALIDATION_STAGE_KEYWORDS):
        return "customer_validation_or_delivery"
    if _has_any(text, ORDER_DELIVERY_KEYWORDS):
        return "order_or_delivery"
    return ""


def _normalize_customer_keyword_text(text: str) -> str:
    return re.sub(r"少量产品", "少量 产品", text)


def _has_negative_customer_context(text: str) -> bool:
    if _has_any(text, CUSTOMER_NEGATIVE_CONTEXT_KEYWORDS):
        return True
    return any(pattern.search(text) for pattern in CUSTOMER_NEGATIVE_CONTEXT_PATTERNS)


def _has_unsubstantiated_customer_context(text: str) -> bool:
    return any(pattern.search(text) for pattern in CUSTOMER_UNSUBSTANTIATED_CONTEXT_PATTERNS)


def _joined_columns(row: dict[str, Any], columns: list[str]) -> str:
    return " ".join(_text(row.get(column)) for column in columns if column in row)


def _first_text(row: dict[str, Any], columns: list[str]) -> str:
    for column in columns:
        value = _text(row.get(column))
        if value:
            return value
    return ""


def _source_claim(row: dict[str, Any], source_name_columns: list[str], fallback: str) -> str:
    source_name = _first_text(row, source_name_columns)
    title = _first_text(row, ["title", "report_title"])
    prefix = " ".join(part for part in [source_name, title] if part)
    return f"{prefix}: {fallback}" if prefix else fallback


def _prepare_evidence_seed(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None:
        frame = pd.DataFrame()
    evidence = frame.copy()
    for column in [
        "asset_id",
        "field",
        "source_type",
        "source_path",
        "source_date",
        "claim",
        "supports_value",
        "evidence_tier",
        "excerpt",
    ]:
        if column not in evidence.columns:
            evidence[column] = ""
    evidence["asset_id"] = evidence["asset_id"].map(_text)
    evidence["field"] = evidence["field"].map(_text)
    allowed_fields = set(SOURCE_BACKED_FIELDS) | set(SUPPLIER_FIELD_ALIASES)
    evidence = evidence[evidence["asset_id"].ne("") & evidence["field"].isin(allowed_fields)].copy()
    return evidence.reset_index(drop=True)


def _source_backed_fields(detail: pd.DataFrame, evidence: pd.DataFrame) -> list[str]:
    fields = ["revenue_exposure_bucket", "customer_certification_stage"]
    if "supplier_concentration_type" in detail.columns or (
        not evidence.empty and evidence["field"].eq("supplier_concentration_type").any()
    ):
        fields.append("supplier_concentration_type")
    else:
        fields.append("supplier_concentration_evidence")
    return fields


def _evidence_lookup(evidence: pd.DataFrame) -> dict[tuple[str, str], list[dict[str, str]]]:
    lookup: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in evidence.to_dict("records"):
        asset_id = _text(row.get("asset_id"))
        field = _text(row.get("field"))
        ref = {
            "source_type": _text(row.get("source_type")),
            "source_path": _text(row.get("source_path")),
            "source_date": _text(row.get("source_date")),
            "claim": _text(row.get("claim")),
            "supports_value": _text(row.get("supports_value")),
            "evidence_tier": _text(row.get("evidence_tier")),
            "excerpt": _text(row.get("excerpt")),
        }
        lookup.setdefault((asset_id, field), []).append(ref)
        if field == "supplier_concentration_evidence":
            lookup.setdefault((asset_id, "supplier_concentration_type"), []).append(ref)
        elif field == "supplier_concentration_type":
            lookup.setdefault((asset_id, "supplier_concentration_evidence"), []).append(ref)
    return lookup


def _build_long(
    detail_input: pd.DataFrame,
    evidence_lookup: dict[tuple[str, str], list[dict[str, str]]],
    fields: list[str],
) -> pd.DataFrame:
    rows = []
    for row in detail_input.to_dict("records"):
        asset_id = _text(row.get("asset_id"))
        for field in fields:
            inferred = _text(row.get(field))
            refs = evidence_lookup.get((asset_id, field), [])
            grade = _evidence_grade(refs, row)
            backed_value = _source_backed_value(refs)
            rows.append(
                {
                    "asset_id": asset_id,
                    "stock_name": _text(row.get("stock_name")),
                    "primary_chain_id": _text(row.get("primary_chain_id")),
                    "field": field,
                    "inferred_value": inferred,
                    "source_backed_value": backed_value,
                    "evidence_grade": grade,
                    "evidence_refs": json.dumps(refs, ensure_ascii=False),
                    "evidence_ref_count": len(refs),
                    "needed_source_type": FIELD_SOURCE_NEEDS[field],
                    "evidence_limit": _evidence_limit(field, grade),
                }
            )
    columns = [
        "asset_id",
        "stock_name",
        "primary_chain_id",
        "field",
        "inferred_value",
        "source_backed_value",
        "evidence_grade",
        "evidence_refs",
        "evidence_ref_count",
        "needed_source_type",
        "evidence_limit",
    ]
    return pd.DataFrame(rows, columns=columns)


def _evidence_grade(refs: list[dict[str, str]], row: dict[str, Any]) -> str:
    primary_refs = [ref for ref in refs if _text(ref.get("source_type")).lower() in PRIMARY_SOURCE_TYPES]
    if primary_refs:
        if any(_text(ref.get("supports_value")) for ref in primary_refs) or any(
            _text(ref.get("evidence_tier")).lower() in STRONG_TIERS for ref in primary_refs
        ):
            return "primary_strong"
        return "primary_partial"
    if _has_artifact_provenance(row.get("evidence_source_provenance")) or _has_artifact_provenance(
        row.get("source_provenance")
    ):
        return "artifact_only"
    return "missing"


def _source_backed_value(refs: list[dict[str, str]]) -> str:
    for ref in refs:
        value = _text(ref.get("supports_value"))
        if value:
            return value
    return ""


def _has_artifact_provenance(value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    return (
        "local_artifact_provenance" in text
        or "source_files" in text
        or "artifact_level" in text
        or "candidate_row" in text
        or "serenity_method_evidence_fields" in text
    )


def _evidence_limit(field: str, grade: str) -> str:
    if grade == "primary_strong":
        return "source evidence supports the field value"
    if grade == "primary_partial":
        return "source evidence exists but does not directly support a normalized value"
    if grade == "artifact_only":
        return "local artifact lineage only; original source evidence still required"
    return f"missing source evidence: {FIELD_SOURCE_NEEDS[field]}"


def _build_detail(detail_input: pd.DataFrame, long: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    rows = []
    long_by_asset = {asset: group for asset, group in long.groupby("asset_id", dropna=False)}
    for row in detail_input.to_dict("records"):
        asset_id = _text(row.get("asset_id"))
        field_rows = long_by_asset.get(asset_id, long.iloc[0:0])
        output = {
            "asset_id": asset_id,
            "stock_name": _text(row.get("stock_name")),
            "primary_chain_id": _text(row.get("primary_chain_id")),
        }
        source_backed = 0
        weak = 0
        for field in fields:
            match = field_rows[field_rows["field"].eq(field)].head(1)
            if match.empty:
                grade = "missing"
                backed_value = ""
            else:
                grade = _text(match.iloc[0]["evidence_grade"])
                backed_value = _text(match.iloc[0]["source_backed_value"])
            output[f"{field}_source_backed_value"] = backed_value
            output[f"{field}_evidence_grade"] = grade
            if grade in {"primary_strong", "primary_partial"}:
                source_backed += 1
            if grade in {"artifact_only", "missing"}:
                weak += 1
        output["source_backed_field_count"] = source_backed
        output["artifact_only_or_missing_field_count"] = weak
        rows.append(output)
    return pd.DataFrame(rows)


def _build_summary(long: pd.DataFrame) -> pd.DataFrame:
    if long.empty:
        return pd.DataFrame(
            columns=[
                "field",
                "missing",
                "artifact_only",
                "primary_partial",
                "primary_strong",
                "total",
                "artifact_only_or_missing",
                "source_backed",
            ]
        )
    summary = (
        long.pivot_table(index="field", columns="evidence_grade", values="asset_id", aggfunc="count", fill_value=0)
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for column in ["missing", "artifact_only", "primary_partial", "primary_strong"]:
        if column not in summary.columns:
            summary[column] = 0
    summary["total"] = summary[["missing", "artifact_only", "primary_partial", "primary_strong"]].sum(axis=1)
    summary["artifact_only_or_missing"] = summary["missing"] + summary["artifact_only"]
    summary["source_backed"] = summary["primary_partial"] + summary["primary_strong"]
    return summary[
        [
            "field",
            "missing",
            "artifact_only",
            "primary_partial",
            "primary_strong",
            "total",
            "artifact_only_or_missing",
            "source_backed",
        ]
    ].sort_values(["artifact_only_or_missing", "field"], ascending=[False, True])


def _build_manual_queue(long: pd.DataFrame) -> pd.DataFrame:
    queue = long[long["evidence_grade"].isin(["missing", "artifact_only"])].copy()
    if queue.empty:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "stock_name",
                "field",
                "inferred_value",
                "evidence_grade",
                "needed_source_type",
                "evidence_limit",
            ]
        )
    queue["priority_rank"] = queue["evidence_grade"].map({"missing": 1, "artifact_only": 2}).fillna(9)
    queue = queue.sort_values(["priority_rank", "asset_id", "field"])
    return queue[
        [
            "asset_id",
            "stock_name",
            "field",
            "inferred_value",
            "evidence_grade",
            "needed_source_type",
            "evidence_limit",
        ]
    ].reset_index(drop=True)


def _render_report(summary: pd.DataFrame, manual_queue: pd.DataFrame, run_id: str) -> str:
    lines = [
        "# Serenity Source-Backed Evidence Fill",
        "",
        f"Run ID: `{run_id}`",
        "",
        "Scope: separates source-backed evidence from heuristic or local-artifact-only labels.",
        "",
        "## Gap Summary",
        "",
        summary.to_markdown(index=False) if not summary.empty else "No rows.",
        "",
        "## Manual Evidence Queue",
        "",
        manual_queue.head(30).to_markdown(index=False) if not manual_queue.empty else "No manual queue rows.",
        "",
    ]
    return "\n".join(lines)


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _has_any(text: str, keywords: set[str]) -> bool:
    lowered = _text(text).lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _is_positive_evidence_value(field: str, value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    weak_negative_values = {
        "not_identified",
        "concentration_not_established",
        "concept_or_indirect_exposure_review",
    }
    if text in weak_negative_values:
        return False
    if field == "customer_certification_stage" and text == "qualification_required_but_unproven":
        return False
    return True


def _excerpt(text: str, max_chars: int = 180) -> str:
    compact = " ".join(_text(text).split())
    return compact[:max_chars]


def _matching_excerpt(text: str, keywords: set[str], max_chars: int = 220) -> str:
    compact = " ".join(_text(text).split())
    if not compact:
        return ""
    lowered = compact.lower()
    matches = [
        lowered.find(keyword.lower())
        for keyword in keywords
        if keyword and lowered.find(keyword.lower()) >= 0
    ]
    if not matches:
        return ""
    start = max(0, min(matches) - 70)
    return compact[start : start + max_chars]


def _claim(report: dict[str, Any], fallback: str) -> str:
    title = _text(report.get("report_title"))
    broker = _text(report.get("broker"))
    date = _text(report.get("publish_date"))
    prefix = " ".join(part for part in [date, broker, title] if part)
    return f"{prefix}: {fallback}" if prefix else fallback


def _supportable_value(value: str) -> str:
    text = _text(value)
    unsupported = {
        "",
        "not_identified",
        "concentration_not_established",
        "not_established",
        "concept_or_indirect_exposure_review",
        "qualification_required_but_unproven",
    }
    return "" if text in unsupported else text
