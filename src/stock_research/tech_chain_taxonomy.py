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
        text = _compactible_text(
            " ".join(
                [
                    candidate["stock_name"],
                    candidate["industry_name"],
                    candidate["product_snippet"],
                ]
            )
        )
        matches = [_candidate_chain_match(chain, text) for chain in taxonomy.chains]
        matches = [match for match in matches if match["score"] > 0]
        matches = sorted(
            matches,
            key=lambda item: (
                item["product_hits"],
                item["context_hits"],
                item["score"],
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


def _candidate_chain_match(chain: TechChainDefinition, text: str) -> dict[str, Any]:
    context_terms = _matched_terms(text, chain.chain_context_terms)
    product_terms = _matched_terms(text, chain.product_exposure_terms)
    context_hits = len(context_terms)
    product_hits = len(product_terms)
    return {
        "chain_id": chain.chain_id,
        "display_name": chain.display_name,
        "context_terms": context_terms,
        "product_terms": product_terms,
        "context_hits": context_hits,
        "product_hits": product_hits,
        "score": context_hits + product_hits * 3,
    }


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.copy()
    for column in [
        "asset_id",
        "stock_name",
        "trade_date",
        "industry_name",
        "product_snippet",
    ]:
        if column not in frame:
            frame[column] = ""
    frame["asset_id"] = frame["asset_id"].astype("string").fillna("")
    frame["stock_name"] = frame["stock_name"].astype("string").fillna("")
    frame["industry_name"] = frame["industry_name"].astype("string").fillna("")
    frame["product_snippet"] = frame["product_snippet"].astype("string").fillna("")
    frame["trade_date"] = frame["trade_date"].map(_normalize_date)
    return frame[frame["asset_id"].ne("") & frame["trade_date"].ne("")].copy()


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
    return [term for term in terms if _compactible_text(term) in compact_text]


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
