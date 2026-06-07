from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_LIST_FIELDS = (
    "chain_context_terms",
    "product_exposure_terms",
    "technical_execution_terms",
    "commercial_validation_terms",
    "invalidation_terms",
    "global_reference_entities",
)

CHAIN_MAPPING_COLUMNS = [
    "asset_id",
    "stock_name",
    "trade_date",
    "primary_chain_id",
    "primary_chain_name",
    "matched_chain_ids",
    "matched_context_terms",
    "matched_product_terms",
    "chain_context_quality",
    "product_exposure_quality",
]

CHAIN_EVIDENCE_COLUMNS = [
    "asset_id",
    "stock_name",
    "trade_date",
    "chain_id",
    "chain_name",
    "evidence_type",
    "bottleneck_dimension",
    "matched_terms",
    "evidence_quality",
    "evidence_date",
    "snippet",
]

CANDIDATE_TEXT_FIELDS = [
    "stock_name",
    "industry_name",
    "product_snippet",
    "product_family",
    "bottleneck_keyword",
    "bottleneck_snippet",
    "technical_keyword",
    "technical_snippet",
    "customer_keyword",
    "customer_snippet",
    "capacity_keyword",
    "capacity_snippet",
    "catalyst_keyword",
    "catalyst_snippet",
]


@dataclass(frozen=True)
class TechChainDefinition:
    chain_id: str
    display_name: str
    chain_context_terms: list[str]
    product_exposure_terms: list[str]
    bottleneck_dimensions: dict[str, list[str]]
    technical_execution_terms: list[str]
    commercial_validation_terms: list[str]
    invalidation_terms: list[str]
    global_reference_entities: list[str]


@dataclass(frozen=True)
class TechChainTaxonomy:
    version: str
    chains: list[TechChainDefinition]

    def chain_by_id(self, chain_id: str) -> TechChainDefinition:
        for chain in self.chains:
            if chain.chain_id == chain_id:
                return chain
        raise KeyError(chain_id)


def load_taxonomy(path: Path | str) -> TechChainTaxonomy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    _validate_taxonomy_payload(payload)

    seen_chain_ids: set[str] = set()
    chains = []
    for index, item in enumerate(payload["chains"]):
        _validate_chain_payload(item, index)
        chain_id = item["chain_id"].strip()
        if chain_id in seen_chain_ids:
            raise ValueError(f"duplicate chain_id: {chain_id}")
        seen_chain_ids.add(chain_id)
        chains.append(_chain_from_payload(item))

    return TechChainTaxonomy(version=payload["version"].strip(), chains=chains)


def build_chain_mapping(
    *, candidates: pd.DataFrame, taxonomy: TechChainTaxonomy
) -> pd.DataFrame:
    normalized = _normalize_candidates(candidates)
    rows: list[dict[str, Any]] = []
    for candidate in normalized.to_dict("records"):
        text = _candidate_matching_text(candidate)
        matches = [
            _candidate_chain_match(chain, text, taxonomy_order=index)
            for index, chain in enumerate(taxonomy.chains)
        ]
        matches = [match for match in matches if match["score"] > 0]
        matches = sorted(
            matches,
            key=lambda item: (
                item["product_hits"] > 0,
                item["distinct_product_hits"] > 0,
                item["context_hits"] > 0,
                item["score"],
                -item["taxonomy_order"],
            ),
            reverse=True,
        )
        primary = matches[0] if matches else {}
        rows.append(
            {
                "asset_id": candidate["asset_id"],
                "stock_name": candidate["stock_name"],
                "trade_date": candidate["trade_date"],
                "primary_chain_id": str(primary.get("chain_id", "")),
                "primary_chain_name": str(primary.get("display_name", "")),
                "matched_chain_ids": "|".join(match["chain_id"] for match in matches),
                "matched_context_terms": "|".join(primary.get("context_terms", [])),
                "matched_product_terms": "|".join(primary.get("product_terms", [])),
                "chain_context_quality": (
                    "strong" if int(primary.get("context_hits", 0)) > 0 else "missing"
                ),
                "product_exposure_quality": (
                    "strong" if int(primary.get("product_hits", 0)) > 0 else "missing"
                ),
            }
        )
    return pd.DataFrame(rows).reindex(columns=CHAIN_MAPPING_COLUMNS)


def build_chain_evidence_review(
    *,
    mapping: pd.DataFrame,
    evidence: pd.DataFrame | None,
    taxonomy: TechChainTaxonomy,
) -> pd.DataFrame:
    normalized_mapping = _normalize_mapping(mapping)
    normalized_evidence = _normalize_evidence(evidence)
    rows: list[dict[str, Any]] = []
    for item in normalized_mapping.to_dict("records"):
        if not item["primary_chain_id"]:
            continue
        chain = taxonomy.chain_by_id(item["primary_chain_id"])
        candidate_evidence = normalized_evidence[
            normalized_evidence["asset_id"].eq(item["asset_id"])
            & normalized_evidence["candidate_trade_date"].eq(item["trade_date"])
            & normalized_evidence["as_of_safe"]
        ].copy()
        for evidence_row in candidate_evidence.to_dict("records"):
            keyword_text = _compactible_text(evidence_row["matched_keyword"])
            full_text = _compactible_text(
                f"{evidence_row['matched_keyword']} {evidence_row['snippet']}"
            )
            text = (
                keyword_text
                if keyword_text
                and any(
                    _matched_terms(keyword_text, terms)
                    for terms in chain.bottleneck_dimensions.values()
                )
                else full_text
            )
            for dimension, terms in chain.bottleneck_dimensions.items():
                matched = _matched_terms(text, terms)
                if not matched:
                    continue
                rows.append(
                    {
                        "asset_id": item["asset_id"],
                        "stock_name": item["stock_name"],
                        "trade_date": item["trade_date"],
                        "chain_id": chain.chain_id,
                        "chain_name": chain.display_name,
                        "evidence_type": evidence_row["evidence_type"],
                        "bottleneck_dimension": dimension,
                        "matched_terms": "|".join(matched),
                        "evidence_quality": _chain_evidence_quality(
                            evidence_row, matched
                        ),
                        "evidence_date": evidence_row["evidence_date"],
                        "snippet": evidence_row["snippet"],
                    }
                )
    return pd.DataFrame(rows).reindex(columns=CHAIN_EVIDENCE_COLUMNS)


def _candidate_chain_match(
    chain: TechChainDefinition, text: str, *, taxonomy_order: int
) -> dict[str, Any]:
    context_terms = _matched_terms(text, chain.chain_context_terms)
    product_terms = _matched_terms(text, chain.product_exposure_terms)
    context_compacts = {_compactible_text(term) for term in context_terms}
    distinct_product_hits = len(
        [term for term in product_terms if _compactible_text(term) not in context_compacts]
    )
    context_hits = len(context_terms)
    product_hits = len(product_terms)
    return {
        "chain_id": chain.chain_id,
        "display_name": chain.display_name,
        "context_terms": context_terms,
        "product_terms": product_terms,
        "context_hits": context_hits,
        "product_hits": product_hits,
        "distinct_product_hits": distinct_product_hits,
        "taxonomy_order": taxonomy_order,
        "score": (
            _matched_term_length(product_terms) * 3
            + _matched_term_length(context_terms)
            + distinct_product_hits * 10
        ),
    }


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.copy()
    for column in [
        "asset_id",
        "trade_date",
        *CANDIDATE_TEXT_FIELDS,
    ]:
        if column not in frame:
            frame[column] = ""
    # Preserve string asset ids such as "000001"; CSV readers should pass dtype=str.
    frame["asset_id"] = _normalized_string_column(frame["asset_id"])
    for column in CANDIDATE_TEXT_FIELDS:
        frame[column] = _normalized_string_column(frame[column])
    frame["trade_date"] = frame["trade_date"].map(_normalize_date)
    return frame[frame["asset_id"].ne("") & frame["trade_date"].ne("")].copy()


def _normalize_mapping(mapping: pd.DataFrame) -> pd.DataFrame:
    frame = mapping.copy()
    for column in [
        "asset_id",
        "stock_name",
        "trade_date",
        "primary_chain_id",
        "product_exposure_quality",
    ]:
        if column not in frame:
            frame[column] = ""
        frame[column] = _normalized_string_column(frame[column])
    frame["trade_date"] = frame["trade_date"].map(_normalize_date)
    return frame[frame["asset_id"].ne("") & frame["trade_date"].ne("")].copy()


def _normalize_evidence(evidence: pd.DataFrame | None) -> pd.DataFrame:
    frame = evidence.copy() if evidence is not None else pd.DataFrame()
    if "trade_date" not in frame and "candidate_trade_date" in frame:
        frame = frame.rename(columns={"candidate_trade_date": "trade_date"})
    if "candidate_trade_date" not in frame and "trade_date" in frame:
        frame["candidate_trade_date"] = frame["trade_date"]
    if "snippet" not in frame and "evidence_snippet" in frame:
        frame = frame.rename(columns={"evidence_snippet": "snippet"})
    if "matched_keyword" not in frame and "term" in frame:
        frame = frame.rename(columns={"term": "matched_keyword"})
    if "evidence_type" not in frame and "evidence_bucket" in frame:
        frame = frame.rename(columns={"evidence_bucket": "evidence_type"})
    for column in [
        "asset_id",
        "stock_name",
        "candidate_trade_date",
        "evidence_date",
        "evidence_type",
        "matched_keyword",
        "snippet",
    ]:
        if column not in frame:
            frame[column] = ""
        frame[column] = _normalized_string_column(frame[column])
    if "as_of_safe" not in frame:
        frame["as_of_safe"] = True
    frame["as_of_safe"] = frame["as_of_safe"].map(_bool_value)
    frame["candidate_trade_date"] = frame["candidate_trade_date"].map(_normalize_date)
    frame["evidence_date"] = frame["evidence_date"].map(_normalize_date)
    return frame[
        frame["asset_id"].ne("") & frame["candidate_trade_date"].ne("")
    ].copy()


def _normalized_string_column(column: pd.Series) -> pd.Series:
    return column.astype("string").fillna("").str.strip()


def _bool_value(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    return str(value).strip().casefold() in {"true", "1", "yes", "y"}


def _chain_evidence_quality(row: dict[str, Any], matched_terms: list[str]) -> str:
    text = _compactible_text(
        f"{row.get('matched_keyword', '')} {row.get('snippet', '')}"
    )
    if len(matched_terms) >= 2:
        return "strong"
    if any(
        term in text
        for term in ["良率", "认证", "量产", "客户", "交付", "产能", "扩产"]
    ):
        return "strong"
    return "medium"


def _candidate_matching_text(candidate: dict[str, Any]) -> str:
    return _compactible_text(
        " ".join(str(candidate[field]) for field in CANDIDATE_TEXT_FIELDS)
    )


def _normalize_date(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and math.isfinite(value) and int(value) == value:
        value = int(value)
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        parsed = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    else:
        parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    compact_text = _compactible_text(text)
    matched = [
        (term, _compactible_text(term))
        for term in terms
        if _compactible_text(term) in compact_text
    ]
    return [
        term
        for term, compact_term in matched
        if not any(
            compact_term != other_compact
            and compact_term in other_compact
            and len(compact_term) < len(other_compact)
            for _, other_compact in matched
        )
    ]


def _matched_term_length(terms: list[str]) -> int:
    return sum(len(_compactible_text(term)) for term in terms)


def _compactible_text(value: str) -> str:
    return "".join(str(value).casefold().split())


def _chain_from_payload(item: dict[str, Any]) -> TechChainDefinition:
    return TechChainDefinition(
        chain_id=item["chain_id"].strip(),
        display_name=item["display_name"].strip(),
        chain_context_terms=_string_list(
            item.get("chain_context_terms"), "chain_context_terms"
        ),
        product_exposure_terms=_string_list(
            item.get("product_exposure_terms"), "product_exposure_terms"
        ),
        bottleneck_dimensions={
            key.strip(): _string_list(value, "bottleneck_dimensions")
            for key, value in item["bottleneck_dimensions"].items()
        },
        technical_execution_terms=_string_list(
            item.get("technical_execution_terms"), "technical_execution_terms"
        ),
        commercial_validation_terms=_string_list(
            item.get("commercial_validation_terms"), "commercial_validation_terms"
        ),
        invalidation_terms=_string_list(
            item.get("invalidation_terms"), "invalidation_terms"
        ),
        global_reference_entities=_string_list(
            item.get("global_reference_entities"), "global_reference_entities"
        ),
    )


def _validate_taxonomy_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("taxonomy payload must be an object")
    if (
        "version" not in payload
        or not isinstance(payload["version"], str)
        or not payload["version"].strip()
    ):
        raise ValueError("version must be a non-empty string")
    if "chains" not in payload:
        raise ValueError("chains is required")
    if not isinstance(payload["chains"], list):
        raise ValueError("chains must be a list")


def _validate_chain_payload(item: Any, index: int) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"chain at index {index} must be an object")

    for field in ("chain_id", "display_name"):
        if field not in item or not isinstance(item[field], str) or not item[field].strip():
            raise ValueError(f"chain at index {index} missing required string field: {field}")

    for field in REQUIRED_LIST_FIELDS:
        if field not in item or not isinstance(item[field], list):
            raise ValueError(f"chain {item['chain_id']} field {field} must be a list")
        _string_list(item[field], field)

    dimensions = item.get("bottleneck_dimensions")
    if not isinstance(dimensions, dict):
        raise ValueError(f"chain {item['chain_id']} field bottleneck_dimensions must be a dict")
    for key, value in dimensions.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("bottleneck_dimensions keys must be non-empty strings")
        if not isinstance(value, list):
            raise ValueError(
                f"chain {item['chain_id']} bottleneck_dimensions.{key} must be a list"
            )
        _string_list(value, "bottleneck_dimensions")


def _string_list(value: Any, field: str) -> list[str]:
    entries = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} entries must be non-empty strings")
        entries.append(item.strip())
    return entries
