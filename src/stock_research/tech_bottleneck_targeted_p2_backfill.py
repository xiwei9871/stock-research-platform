from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


TARGET_ASSET_FAMILIES = {
    "CN:SZ:002859": "semiconductor_materials_components",
    "CN:SZ:300567": "semiconductor_testing_metrology",
    "CN:SZ:300394": "optical_communication_components",
    "CN:SZ:002371": "semiconductor_equipment",
    "CN:SH:688686": "semiconductor_testing_metrology",
}

BRIDGE_TARGETS = {
    "semiconductor_materials_components": {
        "product_terms": ["载带", "离型膜", "MLCC离型膜", "半导体材料", "电子元件材料"],
        "semantic_terms": ["国产替代", "技术壁垒", "客户认证", "产能", "半导体封装"],
    },
    "semiconductor_testing_metrology": {
        "product_terms": ["半导体检测", "量测设备", "AOI", "测试设备", "面板检测", "机器视觉", "视觉检测"],
        "semantic_terms": ["国产替代", "先进封装", "技术壁垒", "客户导入", "产能", "量产", "半导体"],
    },
    "optical_communication_components": {
        "product_terms": ["光器件", "光模块", "高速光引擎", "光引擎", "CPO", "光通信器件"],
        "semantic_terms": ["国产替代", "高速率", "AI算力", "客户导入", "量产"],
    },
    "semiconductor_equipment": {
        "product_terms": ["刻蚀", "PVD", "CVD", "清洗设备", "热处理设备", "半导体设备"],
        "semantic_terms": ["国产替代", "先进制程", "技术壁垒", "客户导入", "产能"],
    },
}

NORMALIZED_QUEUE_COLUMNS = [
    "asset_id",
    "stock_name",
    "candidate_trade_date",
    "p3_decision",
    "review_priority",
    "next_evidence_need",
    "bridge_family",
]

GAP_AUDIT_COLUMNS = [
    "asset_id",
    "stock_name",
    "candidate_trade_date",
    "candidate_bridge_family",
    "product_evidence_count",
    "bottleneck_evidence_count",
    "capacity_evidence_count",
    "customer_evidence_count",
    "technical_evidence_count",
    "missing_bridge_side",
]

BRIDGE_SUGGESTION_COLUMNS = [
    "asset_id",
    "stock_name",
    "candidate_trade_date",
    "bridge_family",
    "matched_product_terms",
    "matched_semantic_terms",
    "supporting_source_ids",
    "bridge_status",
]

BRIDGE_TEXT_COLUMNS = [
    "evidence_snippet",
    "matched_keyword",
    "source_title",
    "source_name",
    "product_name",
    "business_scope",
]

CAPACITY_TERMS = ["capacity", "产能", "扩产", "量产"]
CUSTOMER_TERMS = ["customer", "客户", "认证", "导入"]
TECHNICAL_TEXT_TERMS = ["技术壁垒", "专利", "工艺", "良率"]
TECHNICAL_TYPE_TERMS = ["technical", "patent", "barrier"]


def normalize_p2_mapping_queue(queue: pd.DataFrame) -> pd.DataFrame:
    normalized = _copy_with_columns(queue, NORMALIZED_QUEUE_COLUMNS + ["trade_date"])
    if normalized.empty:
        return pd.DataFrame(columns=NORMALIZED_QUEUE_COLUMNS)

    mapping_mask = (
        normalized["review_priority"].eq("P2_mapping_review")
        | normalized["p3_decision"].eq("needs_product_family_mapping")
        | normalized["next_evidence_need"].eq("needs_product_family_mapping")
    )
    normalized = normalized[mapping_mask & normalized["asset_id"].isin(TARGET_ASSET_FAMILIES)].copy()
    if normalized.empty:
        return pd.DataFrame(columns=NORMALIZED_QUEUE_COLUMNS)

    missing_candidate_date = normalized["candidate_trade_date"].map(_is_blank)
    normalized.loc[missing_candidate_date, "candidate_trade_date"] = normalized.loc[missing_candidate_date, "trade_date"]
    normalized["candidate_trade_date"] = normalized["candidate_trade_date"].map(_safe_text)
    normalized["bridge_family"] = normalized["asset_id"].map(TARGET_ASSET_FAMILIES)

    return (
        normalized[NORMALIZED_QUEUE_COLUMNS]
        .sort_values(["asset_id", "candidate_trade_date"], kind="mergesort")
        .reset_index(drop=True)
    )


def build_targeted_gap_audit(queue: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    normalized_queue = normalize_p2_mapping_queue(queue)
    if normalized_queue.empty:
        return pd.DataFrame(columns=GAP_AUDIT_COLUMNS)

    safe_evidence = _safe_evidence(evidence)
    rows = []
    for candidate in normalized_queue.to_dict("records"):
        family = candidate["bridge_family"]
        candidate_evidence = _candidate_evidence(safe_evidence, candidate)

        product_count = 0
        bottleneck_count = 0
        capacity_count = 0
        customer_count = 0
        technical_count = 0
        semantic_terms = BRIDGE_TARGETS[family]["semantic_terms"]

        for evidence_row in candidate_evidence.to_dict("records"):
            evidence_type = _safe_text(evidence_row.get("evidence_type")).lower()
            snippet_keyword_text = _joined_text(evidence_row, ["evidence_snippet", "matched_keyword"])
            typed_and_snippet_text = " ".join([evidence_type, snippet_keyword_text])

            if "product" in evidence_type or "revenue" in evidence_type:
                product_count += 1
            if "bottleneck" in evidence_type or _contains_any(snippet_keyword_text, semantic_terms):
                bottleneck_count += 1
            if _contains_any(typed_and_snippet_text, CAPACITY_TERMS):
                capacity_count += 1
            if _contains_any(typed_and_snippet_text, CUSTOMER_TERMS):
                customer_count += 1
            if _contains_any(evidence_type, TECHNICAL_TYPE_TERMS) or _contains_any(snippet_keyword_text, TECHNICAL_TEXT_TERMS):
                technical_count += 1

        rows.append(
            {
                "asset_id": candidate["asset_id"],
                "stock_name": candidate["stock_name"],
                "candidate_trade_date": candidate["candidate_trade_date"],
                "candidate_bridge_family": family,
                "product_evidence_count": product_count,
                "bottleneck_evidence_count": bottleneck_count,
                "capacity_evidence_count": capacity_count,
                "customer_evidence_count": customer_count,
                "technical_evidence_count": technical_count,
                "missing_bridge_side": _missing_bridge_side(
                    product_count=product_count,
                    bottleneck_count=bottleneck_count,
                    technical_count=technical_count,
                ),
            }
        )

    return pd.DataFrame(rows, columns=GAP_AUDIT_COLUMNS)


def build_bridge_suggestions(queue: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    normalized_queue = normalize_p2_mapping_queue(queue)
    if normalized_queue.empty:
        return pd.DataFrame(columns=BRIDGE_SUGGESTION_COLUMNS)

    safe_evidence = _safe_evidence(evidence)
    rows = []
    for candidate in normalized_queue.to_dict("records"):
        family = candidate["bridge_family"]
        candidate_evidence = _candidate_evidence(safe_evidence, candidate)
        bridge_targets = BRIDGE_TARGETS[family]
        matched_product_terms = _matched_terms(candidate_evidence, bridge_targets["product_terms"])
        matched_semantic_terms = _matched_terms(candidate_evidence, bridge_targets["semantic_terms"])
        supporting_source_ids = _supporting_source_ids(candidate_evidence)

        rows.append(
            {
                "asset_id": candidate["asset_id"],
                "stock_name": candidate["stock_name"],
                "candidate_trade_date": candidate["candidate_trade_date"],
                "bridge_family": family,
                "matched_product_terms": "|".join(matched_product_terms),
                "matched_semantic_terms": "|".join(matched_semantic_terms),
                "supporting_source_ids": "|".join(supporting_source_ids),
                "bridge_status": "bridgeable"
                if matched_product_terms and matched_semantic_terms
                else "needs_more_source_evidence",
            }
        )

    return pd.DataFrame(rows, columns=BRIDGE_SUGGESTION_COLUMNS)


def _copy_with_columns(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    copied = frame.copy()
    for column in columns:
        if column not in copied.columns:
            copied[column] = ""
    return copied


def _safe_evidence(evidence: pd.DataFrame) -> pd.DataFrame:
    safe_evidence = _copy_with_columns(evidence, ["asset_id", "candidate_trade_date", "trade_date", "as_of_safe"])
    if safe_evidence.empty:
        return safe_evidence

    missing_candidate_date = safe_evidence["candidate_trade_date"].map(_is_blank)
    safe_evidence.loc[missing_candidate_date, "candidate_trade_date"] = safe_evidence.loc[missing_candidate_date, "trade_date"]
    safe_evidence["candidate_trade_date"] = safe_evidence["candidate_trade_date"].map(_safe_text)
    if "as_of_safe" in evidence.columns:
        safe_evidence = safe_evidence[safe_evidence["as_of_safe"].eq(True)].copy()  # noqa: E712
    return safe_evidence


def _candidate_evidence(evidence: pd.DataFrame, candidate: dict[str, object]) -> pd.DataFrame:
    if evidence.empty:
        return evidence
    return evidence[
        evidence["asset_id"].eq(candidate["asset_id"])
        & evidence["candidate_trade_date"].eq(candidate["candidate_trade_date"])
    ].copy()


def _missing_bridge_side(*, product_count: int, bottleneck_count: int, technical_count: int) -> str:
    has_semantic_or_technical = bottleneck_count > 0 or technical_count > 0
    if product_count > 0 and has_semantic_or_technical:
        return "missing_product_family_on_semantic_evidence"
    if product_count == 0 and has_semantic_or_technical:
        return "missing_product_family_product_evidence"
    if product_count > 0:
        return "missing_product_family_semantic_evidence"
    return "missing_product_family_product_and_semantic_evidence"


def _matched_terms(evidence: pd.DataFrame, terms: Iterable[str]) -> list[str]:
    text = _joined_frame_text(evidence, BRIDGE_TEXT_COLUMNS)
    return [term for term in terms if term in text]


def _supporting_source_ids(evidence: pd.DataFrame) -> list[str]:
    if evidence.empty:
        return []

    source_column = next(
        (column for column in ["source_id", "source_document_id", "document_id", "url"] if column in evidence.columns),
        None,
    )
    if source_column is None:
        return []

    source_ids = []
    seen = set()
    for value in evidence[source_column].tolist():
        source_id = _safe_text(value)
        if source_id and source_id not in seen:
            seen.add(source_id)
            source_ids.append(source_id)
    return source_ids


def _joined_frame_text(frame: pd.DataFrame, columns: Iterable[str]) -> str:
    if frame.empty:
        return ""
    return " ".join(_joined_text(row, columns) for row in frame.to_dict("records"))


def _joined_text(row: dict[str, object], columns: Iterable[str]) -> str:
    return " ".join(_safe_text(row.get(column)) for column in columns)


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text.lower() for term in terms)


def _safe_text(value: object) -> str:
    if _is_blank(value):
        return ""
    return str(value)


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip() == ""
