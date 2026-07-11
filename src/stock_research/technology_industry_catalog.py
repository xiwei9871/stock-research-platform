from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CATALOG_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "technology_industry_catalog" / "v1"
CATALOG_ARTIFACT_VERSION = "technology_industry_catalog_v1"

CHAIN_KINDS = {
    "canonical_industry_chain",
    "application_theme_chain",
    "frontier_technology_chain",
}
DECOMPOSITION_METHODS = {
    "manufacturing_process",
    "system_architecture",
    "infrastructure_flow",
    "technical_route",
}
NODE_LEVELS = {"L3", "L4"}
NODE_KINDS = {"canonical", "application_role", "frontier_route"}
EDGE_TYPES = {
    "depends_on",
    "enables",
    "supplies",
    "uses",
    "substitutes",
    "competes_with",
    "downstream_of",
}
CATALOG_STATUSES = {"skeleton", "draft", "reviewed", "published"}


class IndustryCatalogValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


def load_industry_catalog(artifact_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir is not None else CATALOG_DIR
    manifest = _load_json(root / "manifest.json")
    if "artifact_version" not in manifest:
        raise IndustryCatalogValidationError("manifest.artifact_version is required")

    sectors = _load_json(root / manifest["sector_file"])["sectors"]
    chains = _load_json(root / manifest["chain_file"])["chains"]
    edges = _load_json(root / manifest["edge_file"])["edges"]
    sources = _load_json(root / manifest["source_file"])["sources"]
    node_artifacts = [
        _load_json(path) for path in sorted((root / manifest["node_dir"]).glob("*.json"))
    ]
    composition_artifacts = [
        _load_json(path)
        for path in sorted((root / manifest["theme_composition_dir"]).glob("*.json"))
    ]
    catalog = {
        **manifest,
        "artifact_dir": str(root),
        "sectors": sectors,
        "chains": chains,
        "nodes": [node for artifact in node_artifacts for node in artifact["nodes"]],
        "edges": edges,
        "sources": sources,
        "theme_compositions": [
            composition
            for artifact in composition_artifacts
            for composition in artifact["theme_compositions"]
        ],
    }
    _validate_catalog(catalog)
    return catalog


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _validate_catalog(catalog: dict[str, Any]) -> None:
    if catalog["artifact_version"] != CATALOG_ARTIFACT_VERSION:
        raise IndustryCatalogValidationError(
            f"unsupported artifact_version: {catalog['artifact_version']}",
            code="UNSUPPORTED_ARTIFACT_VERSION",
        )
