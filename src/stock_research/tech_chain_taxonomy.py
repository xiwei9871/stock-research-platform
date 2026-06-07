from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


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
    chains = [_chain_from_payload(item) for item in payload.get("chains", [])]
    return TechChainTaxonomy(version=str(payload.get("version", "")), chains=chains)


def _chain_from_payload(item: dict[str, Any]) -> TechChainDefinition:
    return TechChainDefinition(
        chain_id=str(item.get("chain_id", "")),
        display_name=str(item.get("display_name", "")),
        chain_context_terms=_string_list(item.get("chain_context_terms")),
        product_exposure_terms=_string_list(item.get("product_exposure_terms")),
        bottleneck_dimensions={
            str(key): _string_list(value)
            for key, value in dict(item.get("bottleneck_dimensions") or {}).items()
        },
        technical_execution_terms=_string_list(item.get("technical_execution_terms")),
        commercial_validation_terms=_string_list(item.get("commercial_validation_terms")),
        invalidation_terms=_string_list(item.get("invalidation_terms")),
        global_reference_entities=_string_list(item.get("global_reference_entities")),
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
