from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

import pandas as pd

from stock_research.tech_bottleneck_evidence_backfill import normalize_evidence_rows


PRODUCT_DISCLOSURE_COLUMNS = [
    "asset_id",
    "ts_code",
    "publish_date",
    "report_period",
    "announcement_title",
    "source_document_id",
    "source_document_url",
    "disclosure_type",
    "is_supported_product_disclosure",
]


def is_supported_product_disclosure(title: object) -> bool:
    text = _safe_text(title)
    if not text:
        return False

    excluded_terms = [
        "摘要",
        "英文",
        "english",
        "取消",
        "撤销",
        "作废",
        "社会责任",
        "csr",
        "esg",
        "环境",
        "可持续",
        "问询",
        "回复",
        "回函",
        "监管函",
    ]
    lowered = text.lower()
    if any(term in lowered for term in excluded_terms):
        return False

    return "年年度报告" in text or "年半年度报告" in text


def normalize_disclosure_manifest(rows: Iterable[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    manifest = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    for column in PRODUCT_DISCLOSURE_COLUMNS:
        if column not in manifest.columns:
            manifest[column] = ""

    manifest["publish_date"] = manifest["publish_date"].map(_date_value)
    manifest["report_period"] = manifest["report_period"].map(_date_value)
    manifest["announcement_title"] = manifest["announcement_title"].map(_safe_text)
    manifest["source_document_id"] = manifest["source_document_id"].map(_safe_text)
    manifest["source_document_url"] = manifest["source_document_url"].map(_safe_text)
    manifest["disclosure_type"] = manifest["announcement_title"].map(_disclosure_type)
    manifest["is_supported_product_disclosure"] = manifest["announcement_title"].map(is_supported_product_disclosure)

    manifest = manifest[
        manifest["asset_id"].map(_safe_text).ne("")
        & manifest["ts_code"].map(_safe_text).ne("")
        & manifest["publish_date"].notna()
        & manifest["report_period"].notna()
    ].copy()

    return (
        manifest[PRODUCT_DISCLOSURE_COLUMNS]
        .sort_values(["asset_id", "ts_code", "report_period", "publish_date", "source_document_id"], kind="stable")
        .reset_index(drop=True)
    )


def build_product_evidence_rows(
    candidates: pd.DataFrame,
    disclosure_manifest: pd.DataFrame,
    main_business: pd.DataFrame,
) -> pd.DataFrame:
    normalized_candidates = _normalize_candidates(candidates)
    manifest = normalize_disclosure_manifest(disclosure_manifest)
    product_rows = _normalize_product_rows(main_business)

    manifest = manifest[manifest["is_supported_product_disclosure"]].copy()
    joined = normalized_candidates.merge(manifest, on=["asset_id", "ts_code"], how="inner")
    joined = joined.merge(product_rows, on=["asset_id", "ts_code", "report_period"], how="inner")

    evidence_rows = []
    for row in joined.to_dict("records"):
        as_of_safe = row["publish_date"] <= row["as_of_date"] and row["report_period"] <= row["as_of_date"]
        metadata = {
            "report_period": row["report_period"],
            "publish_date": row["publish_date"],
            "classify_type": row["classify_type"],
            "item_name": row["item_name"],
            "revenue": row["revenue"],
            "revenue_ratio": row["revenue_ratio"],
            "cost": row["cost"],
            "gross_profit": row["gross_profit"],
            "gross_margin": row["gross_margin"],
            "source": row["source"],
            "source_document_id": row["source_document_id"],
            "source_document_url": row["source_document_url"],
            "extraction_method": "official_manifest_join_main_business_composition",
            "extraction_confidence": "strong",
        }
        evidence_rows.append(
            {
                "asset_id": row["asset_id"],
                "stock_name": row.get("stock_name", ""),
                "candidate_trade_date": row["candidate_trade_date"],
                "as_of_date": row["as_of_date"],
                "evidence_date": row["publish_date"],
                "source_type": "official_disclosure_product_backfill",
                "source_id": row["source_document_id"],
                "source_title": row["announcement_title"],
                "source_url": row["source_document_url"],
                "evidence_type": "product_revenue_exposure",
                "evidence_snippet": _evidence_snippet(row),
                "source_confidence": "strong",
                "is_proxy": False,
                "as_of_safe": as_of_safe,
                "metadata_json": metadata,
            }
        )

    return normalize_evidence_rows(pd.DataFrame(evidence_rows))


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    normalized = candidates.copy()
    for column in ["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"]:
        if column not in normalized.columns:
            normalized[column] = ""
    normalized["ts_code"] = normalized["ts_code"].map(_safe_text)
    normalized["stock_name"] = normalized["stock_name"].map(_safe_text)
    normalized["candidate_trade_date"] = normalized["candidate_trade_date"].map(_date_value)
    normalized["as_of_date"] = normalized["as_of_date"].map(_date_value)
    normalized = normalized[
        normalized["asset_id"].map(_safe_text).ne("")
        & normalized["ts_code"].ne("")
        & normalized["candidate_trade_date"].notna()
        & normalized["as_of_date"].notna()
    ].copy()
    return normalized[["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"]]


def _normalize_product_rows(main_business: pd.DataFrame) -> pd.DataFrame:
    product_rows = main_business.copy()
    product_columns = [
        "asset_id",
        "ts_code",
        "report_period",
        "classify_type",
        "item_name",
        "revenue",
        "revenue_ratio",
        "cost",
        "gross_profit",
        "gross_margin",
        "source",
    ]
    for column in product_columns:
        if column not in product_rows.columns:
            product_rows[column] = ""
    product_rows["ts_code"] = product_rows["ts_code"].map(_safe_text)
    product_rows["report_period"] = product_rows["report_period"].map(_date_value)
    product_rows["classify_type"] = product_rows["classify_type"].map(_safe_text)
    product_rows["item_name"] = product_rows["item_name"].map(_safe_text)
    product_rows["source"] = product_rows["source"].map(_safe_text)
    product_rows = product_rows[
        product_rows["asset_id"].map(_safe_text).ne("")
        & product_rows["ts_code"].ne("")
        & product_rows["report_period"].notna()
        & product_rows["classify_type"].str.contains("产品", na=False)
    ].copy()
    return product_rows[product_columns]


def _disclosure_type(title: object) -> str:
    text = _safe_text(title)
    if "年年度报告" in text:
        return "annual"
    if "年半年度报告" in text:
        return "semiannual"
    return "other"


def _date_value(value: object) -> dt.date | None:
    if value is None or pd.isna(value) or value == "":
        return None
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp.date()


def _safe_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _evidence_snippet(row: dict[str, Any]) -> str:
    ratio = row.get("revenue_ratio")
    ratio_text = "" if ratio is None or pd.isna(ratio) else f"，收入占比{ratio}%"
    return f"{row.get('announcement_title', '')}披露{row.get('item_name', '')}{ratio_text}"
