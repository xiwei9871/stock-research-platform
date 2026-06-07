from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.tech_bottleneck_evidence_backfill import normalize_evidence_rows


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
    "snippet",
    "matched_keyword",
    "source_title",
    "source_name",
    "product",
    "product_name",
    "business_item",
    "item_name",
    "business_scope",
]

CAPACITY_TERMS = ["capacity", "产能", "扩产", "量产"]
CUSTOMER_TERMS = ["customer", "客户", "认证", "导入"]
TECHNICAL_TEXT_TERMS = ["技术壁垒", "专利", "工艺", "良率"]
TECHNICAL_TYPE_TERMS = ["technical", "patent", "barrier"]
ASSET_POOL_DECISION_PRECEDENCE = {
    "auto_approve": 0,
    "needs_product_family_mapping": 1,
    "needs_more_evidence": 2,
    "reject_or_noise": 3,
}


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

    normalized["candidate_trade_date"] = [
        _canonical_date_text(candidate_date if not _is_blank(candidate_date) else trade_date)
        for candidate_date, trade_date in zip(
            normalized["candidate_trade_date"],
            normalized["trade_date"],
            strict=True,
        )
    ]
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
            bridge_text = _joined_text(evidence_row, BRIDGE_TEXT_COLUMNS)
            typed_and_snippet_text = " ".join([evidence_type, snippet_keyword_text])

            if _contains_any(bridge_text, BRIDGE_TARGETS[family]["product_terms"]):
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
        supporting_evidence = _bridge_supporting_evidence(
            candidate_evidence,
            [*bridge_targets["product_terms"], *bridge_targets["semantic_terms"]],
        )
        supporting_source_ids = _supporting_source_ids(supporting_evidence)

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


def build_targeted_bridge_evidence(
    *,
    queue: pd.DataFrame,
    evidence: pd.DataFrame,
    suggestions: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    normalized_queue = normalize_p2_mapping_queue(queue)
    if normalized_queue.empty:
        return normalize_evidence_rows(pd.DataFrame())

    normalized_suggestions = _copy_with_columns(suggestions, BRIDGE_SUGGESTION_COLUMNS)
    bridgeable_suggestions = normalized_suggestions[normalized_suggestions["bridge_status"].eq("bridgeable")].copy()
    if bridgeable_suggestions.empty:
        return normalize_evidence_rows(pd.DataFrame())

    safe_evidence = _safe_evidence(evidence)
    if safe_evidence.empty:
        return normalize_evidence_rows(pd.DataFrame())

    queue_candidates = {
        (candidate["asset_id"], candidate["candidate_trade_date"], candidate["bridge_family"]): candidate
        for candidate in normalized_queue.to_dict("records")
    }

    rows: list[dict[str, Any]] = []
    emitted_source_ids: set[str] = set()
    for suggestion in bridgeable_suggestions.to_dict("records"):
        asset_id = _safe_text(suggestion.get("asset_id"))
        candidate_trade_date = _canonical_date_text(suggestion.get("candidate_trade_date"))
        family = _safe_text(suggestion.get("bridge_family"))
        candidate = queue_candidates.get((asset_id, candidate_trade_date, family))
        if candidate is None or family not in BRIDGE_TARGETS:
            continue

        source_row = _bridge_source_evidence_row(
            _candidate_evidence(safe_evidence, candidate),
            family=family,
        )
        if source_row is None:
            continue

        product_terms = _matched_terms(pd.DataFrame([source_row]), BRIDGE_TARGETS[family]["product_terms"])
        semantic_terms = _matched_terms(pd.DataFrame([source_row]), BRIDGE_TARGETS[family]["semantic_terms"])
        source_id = f"{candidate['asset_id']}:{candidate['candidate_trade_date']}:{family}:bridge"
        if source_id in emitted_source_ids:
            continue
        emitted_source_ids.add(source_id)
        rows.append(
            {
                "run_id": run_id,
                "asset_id": candidate["asset_id"],
                "stock_name": candidate["stock_name"],
                "candidate_trade_date": candidate["candidate_trade_date"],
                "as_of_date": candidate["candidate_trade_date"],
                "evidence_date": _first_text(
                    source_row,
                    [
                        "evidence_date",
                        "publish_date",
                        "published_at",
                        "announcement_date",
                        "announce_date",
                        "disclosure_date",
                    ],
                ),
                "source_type": "derived_product_family_bridge",
                "source_id": source_id,
                "source_title": _first_text(source_row, ["source_title", "source_name"]),
                "source_url": _first_text(source_row, ["source_url", "url"]),
                "evidence_type": source_row.get("evidence_type"),
                "matched_keyword": f"{family}:product={_pipe_join(product_terms)};semantic={_pipe_join(semantic_terms)}",
                "evidence_snippet": _first_text(source_row, ["evidence_snippet", "snippet"]),
                "source_confidence": "medium",
                "is_proxy": True,
                "as_of_safe": True,
                "metadata_json": {
                    "bridge_family": family,
                    "bridge_reason": "product_family_semantic_bridge",
                    "supporting_source_ids": _split_pipe_text(suggestion.get("supporting_source_ids")),
                    "source_candidate_trade_date": _canonical_date_text(source_row.get("candidate_trade_date")),
                },
            }
        )

    return normalize_evidence_rows(pd.DataFrame(rows))


def combine_evidence(*, original_evidence: pd.DataFrame, bridge_evidence: pd.DataFrame) -> pd.DataFrame:
    columns = list(original_evidence.columns)
    columns.extend(column for column in bridge_evidence.columns if column not in columns)
    return pd.concat(
        [
            original_evidence.reindex(columns=columns),
            bridge_evidence.reindex(columns=columns),
        ],
        ignore_index=True,
        sort=False,
    )


def render_promotion_delta(
    *,
    before_review: pd.DataFrame,
    after_review: pd.DataFrame,
    bridge_evidence: pd.DataFrame,
) -> str:
    before = _copy_with_columns(before_review, ["asset_id", "stock_name", "p3_decision", "next_evidence_need"])
    after = _copy_with_columns(after_review, ["asset_id", "stock_name", "p3_decision", "next_evidence_need"])
    bridge = _copy_with_columns(bridge_evidence, ["metadata_json", "source_type", "evidence_type"])

    before_p2 = before[before["p3_decision"].eq("needs_product_family_mapping")].copy()
    before_p1 = before[before["p3_decision"].eq("auto_approve")].copy()

    before_p2_assets = _asset_records_by_id(before_p2)
    before_p1_asset_ids = _asset_ids(before_p1)
    after_by_asset = _asset_records_by_decision_precedence(after)
    after_p2_asset_ids = {
        asset_id
        for asset_id, row in after_by_asset.items()
        if _safe_text(row.get("p3_decision")) == "needs_product_family_mapping"
    }
    after_p1_asset_ids = {
        asset_id
        for asset_id, row in after_by_asset.items()
        if _safe_text(row.get("p3_decision")) == "auto_approve"
    }

    promoted_asset_ids = sorted(set(before_p2_assets) & after_p1_asset_ids)
    blocked_decisions = {"needs_product_family_mapping", "needs_more_evidence", "reject_or_noise"}
    blocked_assets = []
    for asset_id, before_record in before_p2_assets.items():
        after_record = after_by_asset.get(asset_id)
        if after_record is None:
            continue
        after_decision = _safe_text(after_record.get("p3_decision"))
        if after_decision not in blocked_decisions:
            continue
        next_evidence_need = _safe_text(after_record.get("next_evidence_need"))
        display_record = _fill_blank_values(after_record, before_record)
        blocked_assets.append((_asset_label(display_record), next_evidence_need or after_decision))
    blocked_assets.sort(key=lambda item: item[0])

    bridge_family_rows = _bridge_family_rows(bridge)

    lines = [
        "# Promotion Delta",
        "",
        f"P2 asset count before: {len(before_p2_assets)}",
        f"P2 asset count after: {len(after_p2_asset_ids)}",
        f"P1 asset count before: {len(before_p1_asset_ids)}",
        f"P1 asset count after: {len(after_p1_asset_ids)}",
        "",
        "## Promoted Assets",
    ]
    lines.extend(f"- {_asset_label(before_p2_assets[asset_id])}" for asset_id in promoted_asset_ids)
    if not promoted_asset_ids:
        lines.append("- None")

    lines.extend(["", "## Still Blocked Before-P2 Assets"])
    lines.extend(f"- {asset_label}: {reason}" for asset_label, reason in blocked_assets)
    if not blocked_assets:
        lines.append("- None")

    lines.extend(["", "## Added Bridge Evidence Families"])
    lines.extend(f"- {family}: {source_type}/{evidence_type}" for family, source_type, evidence_type in bridge_family_rows)
    if not bridge_family_rows:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def write_targeted_backfill_artifacts(
    *,
    output_dir: Path,
    audit: pd.DataFrame,
    suggestions: pd.DataFrame,
    bridge_evidence: pd.DataFrame,
    combined_evidence: pd.DataFrame,
    review_after: pd.DataFrame,
    promotion_delta_md: str,
    manifest: dict[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "targeted_evidence_gap_audit": output_dir / "targeted_evidence_gap_audit.csv",
        "product_family_bridge_suggestions": output_dir / "product_family_bridge_suggestions.csv",
        "targeted_backfill_evidence": output_dir / "targeted_backfill_evidence.csv",
        "combined_evidence_after_targeted_backfill": output_dir
        / "combined_evidence_after_targeted_backfill.csv",
        "quality_review_after_targeted_backfill": output_dir / "quality_review_after_targeted_backfill.csv",
        "promotion_delta": output_dir / "promotion_delta.md",
        "manifest": output_dir / "manifest.json",
    }

    audit.to_csv(paths["targeted_evidence_gap_audit"], index=False)
    suggestions.to_csv(paths["product_family_bridge_suggestions"], index=False)
    bridge_evidence.to_csv(paths["targeted_backfill_evidence"], index=False)
    combined_evidence.to_csv(paths["combined_evidence_after_targeted_backfill"], index=False)
    review_after.to_csv(paths["quality_review_after_targeted_backfill"], index=False)
    paths["promotion_delta"].write_text(promotion_delta_md, encoding="utf-8")
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return paths


def _copy_with_columns(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    copied = frame.copy()
    for column in columns:
        if column not in copied.columns:
            copied[column] = ""
    return copied


def _asset_records_by_id(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for row in _copy_with_columns(frame, ["asset_id", "stock_name"]).to_dict("records"):
        asset_id = _safe_text(row.get("asset_id"))
        if asset_id:
            records[asset_id] = row
    return dict(sorted(records.items()))


def _asset_records_by_decision_precedence(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    ranks: dict[str, int] = {}
    for row in _copy_with_columns(
        frame,
        ["asset_id", "stock_name", "p3_decision", "next_evidence_need"],
    ).to_dict("records"):
        asset_id = _safe_text(row.get("asset_id"))
        if not asset_id:
            continue

        rank = ASSET_POOL_DECISION_PRECEDENCE.get(
            _safe_text(row.get("p3_decision")),
            len(ASSET_POOL_DECISION_PRECEDENCE),
        )
        if asset_id not in records or rank < ranks[asset_id]:
            records[asset_id] = row
            ranks[asset_id] = rank
        elif rank == ranks[asset_id]:
            records[asset_id] = _fill_blank_values(records[asset_id], row)

    return dict(sorted(records.items()))


def _asset_ids(frame: pd.DataFrame) -> set[str]:
    if "asset_id" not in frame.columns:
        return set()
    return {_safe_text(asset_id) for asset_id in frame["asset_id"].tolist() if _safe_text(asset_id)}


def _asset_label(row: dict[str, object]) -> str:
    asset_id = _safe_text(row.get("asset_id"))
    stock_name = _safe_text(row.get("stock_name")) or asset_id
    return f"{stock_name} ({asset_id})" if asset_id else stock_name


def _fill_blank_values(primary: dict[str, object], fallback: dict[str, object]) -> dict[str, object]:
    merged = primary.copy()
    for key, value in fallback.items():
        if not _safe_text(merged.get(key)):
            merged[key] = value
    return merged


def _bridge_family_rows(bridge_evidence: pd.DataFrame) -> list[tuple[str, str, str]]:
    family_rows = set()
    for row in bridge_evidence.to_dict("records"):
        family = _metadata_bridge_family(row.get("metadata_json"))
        if not family:
            continue
        source_type = _safe_text(row.get("source_type")) or "unknown_source_type"
        evidence_type = _safe_text(row.get("evidence_type")) or "unknown_evidence_type"
        family_rows.add((family, source_type, evidence_type))
    return sorted(family_rows)


def _metadata_bridge_family(metadata_json: object) -> str:
    if isinstance(metadata_json, dict):
        return _safe_text(metadata_json.get("bridge_family"))

    text = _safe_text(metadata_json)
    if not text:
        return ""

    try:
        metadata = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if not isinstance(metadata, dict):
        return ""
    return _safe_text(metadata.get("bridge_family"))


def _safe_evidence(evidence: pd.DataFrame) -> pd.DataFrame:
    safe_evidence = _copy_with_columns(evidence, ["asset_id", "candidate_trade_date", "trade_date", "as_of_safe"])
    if safe_evidence.empty:
        return safe_evidence

    safe_evidence["candidate_trade_date"] = [
        _canonical_date_text(candidate_date if not _is_blank(candidate_date) else trade_date)
        for candidate_date, trade_date in zip(
            safe_evidence["candidate_trade_date"],
            safe_evidence["trade_date"],
            strict=True,
        )
    ]
    if "as_of_safe" in evidence.columns:
        safe_evidence = safe_evidence[safe_evidence["as_of_safe"].map(_is_truthy_as_of_safe)].copy()
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
    return [term for term in terms if term.lower() in text.lower()]


def _bridge_supporting_evidence(evidence: pd.DataFrame, terms: Iterable[str]) -> pd.DataFrame:
    if evidence.empty:
        return evidence

    return evidence[
        evidence.apply(lambda row: _contains_any(_joined_text(row.to_dict(), BRIDGE_TEXT_COLUMNS), terms), axis=1)
    ].copy()


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


def _bridge_source_evidence_row(evidence: pd.DataFrame, *, family: str) -> dict[str, object] | None:
    if evidence.empty:
        return None

    for row in evidence.to_dict("records"):
        text = _joined_text(row, BRIDGE_TEXT_COLUMNS)
        if _contains_any(text, BRIDGE_TARGETS[family]["product_terms"]) and _contains_any(
            text,
            BRIDGE_TARGETS[family]["semantic_terms"],
        ):
            return row
    return None


def _pipe_join(values: Iterable[str]) -> str:
    return "|".join(value for value in values if value)


def _split_pipe_text(value: object) -> list[str]:
    return [part for part in _safe_text(value).split("|") if part]


def _first_text(row: dict[str, object], columns: Iterable[str]) -> str:
    for column in columns:
        text = _safe_text(row.get(column))
        if text:
            return text
    return ""


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


def _canonical_date_text(value: object) -> str:
    if _is_blank(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = _safe_text(value).strip()
    parsed = pd.to_datetime(text, errors="coerce")
    if not pd.isna(parsed):
        return parsed.date().isoformat()
    return text


def _is_truthy_as_of_safe(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1

    text = _safe_text(value).strip().lower()
    if text in {"true", "1", "yes", "y", "t"}:
        return True
    if text in {"false", "0", "no", "n", "f", ""}:
        return False
    return False


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip() == ""
