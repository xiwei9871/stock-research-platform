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

SECTOR_FIELDS = {"sector_id", "sector_name", "description", "status", "order"}
CHAIN_FIELDS = {
    "chain_id",
    "sector_id",
    "chain_name",
    "chain_kind",
    "decomposition_method",
    "description",
    "scope",
    "exclusions",
    "aliases",
    "status",
    "order",
}
NODE_FIELDS = {
    "node_id",
    "chain_id",
    "parent_node_id",
    "level",
    "node_name",
    "node_kind",
    "node_type",
    "description",
    "status",
    "primary_path",
    "canonical_key",
    "canonical_node_refs",
}
EDGE_FIELDS = {
    "edge_id",
    "source_node_id",
    "target_node_id",
    "relationship_type",
    "notes",
    "source_ids",
}
COMPOSITION_FIELDS = {
    "composition_id",
    "chain_id",
    "role_node_id",
    "canonical_node_refs",
    "relationship_type",
    "notes",
}
SOURCE_FIELDS = {"source_id", "title", "publisher", "url", "source_type", "notes"}

_REQUIRED_MANIFEST_PATH_KEYS = (
    "sector_file",
    "chain_file",
    "edge_file",
    "source_file",
    "node_dir",
    "theme_composition_dir",
)


class IndustryCatalogValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


def load_industry_catalog(artifact_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir is not None else CATALOG_DIR
    if not root.is_dir():
        raise IndustryCatalogValidationError(
            f"artifact_dir not found: {root}",
            code="ARTIFACT_DIR_NOT_FOUND",
        )

    manifest = _load_json_object(
        root / "manifest.json",
        missing_code="MANIFEST_NOT_FOUND",
    )
    _validate_manifest(manifest)
    _validate_artifact_version(manifest)

    sectors = _load_collection(_package_file(root, manifest, "sector_file"), "sectors")
    chains = _load_collection(_package_file(root, manifest, "chain_file"), "chains")
    edges = _load_collection(_package_file(root, manifest, "edge_file"), "edges")
    sources = _load_collection(_package_file(root, manifest, "source_file"), "sources")
    node_dir = _package_directory(root, manifest, "node_dir")
    composition_dir = _package_directory(root, manifest, "theme_composition_dir")
    nodes = [
        node
        for path in sorted(node_dir.glob("*.json"))
        for node in _load_collection(path, "nodes")
    ]
    theme_compositions = [
        composition
        for path in sorted(composition_dir.glob("*.json"))
        for composition in _load_collection(path, "theme_compositions")
    ]
    catalog = {
        **manifest,
        "artifact_dir": str(root),
        "sectors": sectors,
        "chains": chains,
        "nodes": nodes,
        "edges": edges,
        "sources": sources,
        "theme_compositions": theme_compositions,
    }
    _validate_catalog(catalog)
    return catalog


def _load_json_object(
    path: Path,
    *,
    missing_code: str = "PACKAGE_FILE_NOT_FOUND",
) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise IndustryCatalogValidationError(
            f"package file not found: {path}",
            code=missing_code,
        ) from exc
    except UnicodeDecodeError as exc:
        raise IndustryCatalogValidationError(
            f"invalid JSON in package file {path}: {exc}",
            code="INVALID_JSON",
        ) from exc
    except OSError as exc:
        raise IndustryCatalogValidationError(
            f"unable to read package file {path}: {exc}",
            code="PACKAGE_READ_ERROR",
        ) from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IndustryCatalogValidationError(
            f"invalid JSON in package file {path}: {exc}",
            code="INVALID_JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise IndustryCatalogValidationError(
            f"JSON root must be an object: {path}",
            code="INVALID_JSON_ROOT",
        )
    return payload


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if "artifact_version" not in manifest:
        raise IndustryCatalogValidationError(
            "manifest.artifact_version is required",
            code="MISSING_ARTIFACT_VERSION",
        )
    for key in _REQUIRED_MANIFEST_PATH_KEYS:
        if key not in manifest:
            raise IndustryCatalogValidationError(
                f"manifest.{key} is required",
                code="MISSING_MANIFEST_KEY",
            )
        if not isinstance(manifest[key], str) or not manifest[key]:
            raise IndustryCatalogValidationError(
                f"manifest.{key} must be a non-empty string",
                code="INVALID_MANIFEST_PATH",
            )


def _package_file(root: Path, manifest: dict[str, Any], key: str) -> Path:
    return root / manifest[key]


def _package_directory(root: Path, manifest: dict[str, Any], key: str) -> Path:
    path = root / manifest[key]
    if not path.is_dir():
        raise IndustryCatalogValidationError(
            f"package directory not found: {path}",
            code="PACKAGE_DIRECTORY_NOT_FOUND",
        )
    return path


def _load_collection(path: Path, key: str) -> list[Any]:
    payload = _load_json_object(path)
    if key not in payload:
        raise IndustryCatalogValidationError(
            f"{path} missing collection key: {key}",
            code="MISSING_COLLECTION_KEY",
        )
    collection = payload[key]
    if not isinstance(collection, list):
        raise IndustryCatalogValidationError(
            f"{path} collection {key} must be a list",
            code="INVALID_COLLECTION",
        )
    return collection


def _validate_artifact_version(catalog: dict[str, Any]) -> None:
    if catalog["artifact_version"] != CATALOG_ARTIFACT_VERSION:
        raise IndustryCatalogValidationError(
            f"unsupported artifact_version: {catalog['artifact_version']}",
            code="UNSUPPORTED_ARTIFACT_VERSION",
        )


def _validate_catalog(catalog: dict[str, Any]) -> None:
    _validate_artifact_version(catalog)
    sectors_by_id = _validate_sectors(catalog["sectors"])
    chains_by_id = _validate_chains(catalog["chains"], sectors_by_id)
    nodes_by_id = _validate_nodes(catalog["nodes"], chains_by_id)
    _validate_edges(catalog["edges"], nodes_by_id)
    _validate_theme_compositions(
        catalog["theme_compositions"],
        chains_by_id,
        nodes_by_id,
    )
    for index, source in enumerate(catalog["sources"]):
        path = f"sources[{index}]"
        _require_fields(source, SOURCE_FIELDS, path)
        _require_non_empty_string(source, "source_id", path)


def _validate_sectors(sectors: list[Any]) -> dict[str, dict[str, Any]]:
    sectors_by_id: dict[str, dict[str, Any]] = {}
    for index, sector in enumerate(sectors):
        path = f"sectors[{index}]"
        _require_fields(sector, SECTOR_FIELDS, path)
        sector_id = _require_non_empty_string(sector, "sector_id", path)
        _require_non_empty_string(sector, "sector_name", path)
        if sector_id in sectors_by_id:
            raise IndustryCatalogValidationError(
                f"{path}.sector_id duplicated: {sector_id}",
                code="DUPLICATE_SECTOR_ID",
            )
        sectors_by_id[sector_id] = sector
    return sectors_by_id


def _validate_chains(
    chains: list[Any],
    sectors_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    chains_by_id: dict[str, dict[str, Any]] = {}
    for index, chain in enumerate(chains):
        path = f"chains[{index}]"
        _require_fields(chain, CHAIN_FIELDS, path)
        chain_id = _require_non_empty_string(chain, "chain_id", path)
        _require_non_empty_string(chain, "chain_name", path)
        if chain["sector_id"] not in sectors_by_id:
            raise IndustryCatalogValidationError(
                f"{path}.sector_id references missing sector: {chain['sector_id']}",
                code="ORPHAN_CHAIN_SECTOR",
            )
        if chain["chain_kind"] not in CHAIN_KINDS:
            raise IndustryCatalogValidationError(
                f"{path}.chain_kind invalid: {chain['chain_kind']}",
                code="INVALID_CHAIN_KIND",
            )
        if chain["decomposition_method"] not in DECOMPOSITION_METHODS:
            raise IndustryCatalogValidationError(
                f"{path}.decomposition_method invalid: {chain['decomposition_method']}",
                code="INVALID_DECOMPOSITION_METHOD",
            )
        chains_by_id[chain_id] = chain
    return chains_by_id


def _validate_nodes(
    nodes: list[Any],
    chains_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if (
            isinstance(node, dict)
            and isinstance(node.get("node_id"), str)
            and node["node_id"].strip()
        ):
            nodes_by_id.setdefault(node["node_id"], node)
    seen_node_ids: set[str] = set()
    canonical_owners: set[str] = set()
    expected_kind_by_chain = {
        "canonical_industry_chain": "canonical",
        "application_theme_chain": "application_role",
        "frontier_technology_chain": "frontier_route",
    }

    for index, node in enumerate(nodes):
        path = f"nodes[{index}]"
        _require_fields(node, NODE_FIELDS, path)
        node_id = _require_non_empty_string(node, "node_id", path)
        _require_non_empty_string(node, "node_name", path)
        if node_id in seen_node_ids:
            raise IndustryCatalogValidationError(
                f"{path}.node_id duplicated: {node_id}",
                code="DUPLICATE_NODE_ID",
            )
        seen_node_ids.add(node_id)

        chain = chains_by_id.get(node["chain_id"])
        if chain is None:
            raise IndustryCatalogValidationError(
                f"{path}.chain_id references missing chain: {node['chain_id']}",
                code="ORPHAN_NODE_CHAIN",
            )
        if node["level"] not in NODE_LEVELS:
            raise IndustryCatalogValidationError(
                f"{path}.level invalid: {node['level']}",
                code="INVALID_NODE_LEVEL",
            )
        expected_kind = expected_kind_by_chain[chain["chain_kind"]]
        if node["node_kind"] != expected_kind:
            raise IndustryCatalogValidationError(
                f"{path}.node_kind must be {expected_kind} for {chain['chain_kind']}",
                code="INVALID_NODE_KIND_FOR_CHAIN",
            )
        if node["node_kind"] == "application_role" and node["canonical_key"]:
            raise IndustryCatalogValidationError(
                f"{path}.canonical_key is not allowed for application roles",
                code="INVALID_NODE_KIND_FOR_CHAIN",
            )

        if node["level"] == "L3":
            if node["parent_node_id"] is not None:
                raise IndustryCatalogValidationError(
                    f"{path}.parent_node_id must be null for L3 nodes",
                    code="ORPHAN_NODE_PARENT",
                )
        else:
            parent = nodes_by_id.get(node["parent_node_id"])
            if (
                parent is None
                or parent.get("level") != "L3"
                or parent.get("chain_id") != node["chain_id"]
            ):
                raise IndustryCatalogValidationError(
                    f"{path}.parent_node_id must reference an L3 node in the same chain",
                    code="ORPHAN_NODE_PARENT",
                )

        if node["node_kind"] == "canonical" and node["level"] == "L4":
            expected_path = [
                chain["sector_id"],
                node["chain_id"],
                node["parent_node_id"],
                node_id,
            ]
            if node["primary_path"] != expected_path:
                raise IndustryCatalogValidationError(
                    f"{path}.primary_path must equal {expected_path}",
                    code="INVALID_PRIMARY_PATH",
                )

        canonical_key = node["canonical_key"]
        if canonical_key:
            if canonical_key in canonical_owners:
                raise IndustryCatalogValidationError(
                    f"{path}.canonical_key duplicated: {canonical_key}",
                    code="DUPLICATE_CANONICAL_OWNERSHIP",
                )
            canonical_owners.add(canonical_key)

        _validate_canonical_node_refs(
            node["canonical_node_refs"],
            nodes_by_id,
            f"{path}.canonical_node_refs",
        )

    return nodes_by_id


def _validate_edges(
    edges: list[Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> None:
    for index, edge in enumerate(edges):
        path = f"edges[{index}]"
        _require_fields(edge, EDGE_FIELDS, path)
        _require_non_empty_string(edge, "edge_id", path)
        if edge["source_node_id"] not in nodes_by_id:
            raise IndustryCatalogValidationError(
                f"{path}.source_node_id references missing node: {edge['source_node_id']}",
                code="ORPHAN_EDGE_SOURCE",
            )
        if edge["target_node_id"] not in nodes_by_id:
            raise IndustryCatalogValidationError(
                f"{path}.target_node_id references missing node: {edge['target_node_id']}",
                code="ORPHAN_EDGE_TARGET",
            )


def _validate_theme_compositions(
    compositions: list[Any],
    chains_by_id: dict[str, dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> None:
    for index, composition in enumerate(compositions):
        path = f"theme_compositions[{index}]"
        _require_fields(composition, COMPOSITION_FIELDS, path)
        _require_non_empty_string(composition, "composition_id", path)
        chain = chains_by_id.get(composition["chain_id"])
        if chain is None:
            raise IndustryCatalogValidationError(
                f"{path}.chain_id references missing chain: {composition['chain_id']}",
                code="ORPHAN_COMPOSITION_CHAIN",
            )
        role = nodes_by_id.get(composition["role_node_id"])
        if role is None:
            raise IndustryCatalogValidationError(
                f"{path}.role_node_id references missing node: {composition['role_node_id']}",
                code="ORPHAN_COMPOSITION_ROLE",
            )
        if (
            chain["chain_kind"] != "application_theme_chain"
            or role.get("node_kind") != "application_role"
            or role.get("chain_id") != composition["chain_id"]
        ):
            raise IndustryCatalogValidationError(
                f"{path}.role_node_id must reference an application role in the same chain",
                code="INVALID_COMPOSITION_ROLE",
            )
        _validate_canonical_node_refs(
            composition["canonical_node_refs"],
            nodes_by_id,
            f"{path}.canonical_node_refs",
        )


def _validate_canonical_node_refs(
    references: Any,
    nodes_by_id: dict[str, dict[str, Any]],
    path: str,
) -> None:
    if not isinstance(references, list):
        raise IndustryCatalogValidationError(
            f"{path} must be a list",
            code="INVALID_CANONICAL_NODE_REFERENCE",
        )
    for node_id in references:
        node = nodes_by_id.get(node_id)
        if node is None or node.get("node_kind") != "canonical" or node.get("level") != "L4":
            raise IndustryCatalogValidationError(
                f"{path} references non-canonical L4 node: {node_id}",
                code="INVALID_CANONICAL_NODE_REFERENCE",
            )


def _require_fields(row: Any, fields: set[str], path: str) -> None:
    if not isinstance(row, dict):
        raise IndustryCatalogValidationError(
            f"{path} must be an object",
            code="MISSING_REQUIRED_FIELD",
        )
    for field in sorted(fields):
        if field not in row:
            raise IndustryCatalogValidationError(
                f"{path}.{field} is required",
                code="MISSING_REQUIRED_FIELD",
            )


def _require_non_empty_string(row: dict[str, Any], field: str, path: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise IndustryCatalogValidationError(
            f"{path}.{field} must be a non-empty string",
            code="MISSING_REQUIRED_FIELD",
        )
    return value
