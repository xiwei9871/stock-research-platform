from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


REQUIRED_LIST_FIELDS = (
    "chain_context_terms",
    "product_exposure_terms",
    "technical_execution_terms",
    "commercial_validation_terms",
    "invalidation_terms",
    "global_reference_entities",
)


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

    return TechChainTaxonomy(version=str(payload.get("version", "")), chains=chains)


def _chain_from_payload(item: dict[str, Any]) -> TechChainDefinition:
    return TechChainDefinition(
        chain_id=item["chain_id"].strip(),
        display_name=item["display_name"].strip(),
        chain_context_terms=_string_list(item.get("chain_context_terms")),
        product_exposure_terms=_string_list(item.get("product_exposure_terms")),
        bottleneck_dimensions={
            str(key): _string_list(value)
            for key, value in item["bottleneck_dimensions"].items()
        },
        technical_execution_terms=_string_list(item.get("technical_execution_terms")),
        commercial_validation_terms=_string_list(item.get("commercial_validation_terms")),
        invalidation_terms=_string_list(item.get("invalidation_terms")),
        global_reference_entities=_string_list(item.get("global_reference_entities")),
    )


def _validate_taxonomy_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("taxonomy payload must be an object")
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

    dimensions = item.get("bottleneck_dimensions")
    if not isinstance(dimensions, dict):
        raise ValueError(f"chain {item['chain_id']} field bottleneck_dimensions must be a dict")
    for key, value in dimensions.items():
        if not isinstance(value, list):
            raise ValueError(
                f"chain {item['chain_id']} bottleneck_dimensions.{key} must be a list"
            )


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if str(item)]
