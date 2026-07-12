from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Iterable
from collections import Counter
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
THEME_LINK_FIELDS = {
    "theme_id",
    "chain_id",
    "node_links",
    "unmapped_theme_node_ids",
}
NODE_LINK_FIELDS = {"theme_node_id", "catalog_node_id"}
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


class IndustryCatalogCliUsageError(ValueError):
    pass


class _IndustryCatalogArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise IndustryCatalogCliUsageError(message)


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
    theme_links = (
        _load_collection(
            _package_file(root, manifest, "theme_link_file"),
            "theme_links",
        )
        if "theme_link_file" in manifest
        else []
    )
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
        "theme_links": theme_links,
    }
    _validate_catalog(catalog)
    return catalog


def summarize_industry_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    chains = catalog["chains"]
    nodes = catalog["nodes"]
    return {
        "sector_count": len(catalog["sectors"]),
        "chain_count": len(chains),
        "l3_node_count": sum(node["level"] == "L3" for node in nodes),
        "l4_node_count": sum(node["level"] == "L4" for node in nodes),
        "edge_count": len(catalog["edges"]),
        "theme_composition_count": len(catalog["theme_compositions"]),
        "chains_by_kind": _sorted_counts(chain["chain_kind"] for chain in chains),
        "chains_by_status": _sorted_counts(chain["status"] for chain in chains),
        "chains_by_sector": _sorted_counts(chain["sector_id"] for chain in chains),
        "nodes_by_status": _sorted_counts(node["status"] for node in nodes),
    }


def get_industry_chain(catalog: dict[str, Any], chain_id: str) -> dict[str, Any]:
    chain = next(
        (chain for chain in catalog["chains"] if chain["chain_id"] == chain_id),
        None,
    )
    if chain is None:
        raise IndustryCatalogValidationError(
            f"chain not found: {chain_id}",
            code="CHAIN_NOT_FOUND",
        )

    nodes = sorted(
        (node for node in catalog["nodes"] if node["chain_id"] == chain_id),
        key=lambda node: (node["level"], node["node_id"]),
    )
    node_ids = {node["node_id"] for node in nodes}
    edges = sorted(
        (
            edge
            for edge in catalog["edges"]
            if edge["source_node_id"] in node_ids
            or edge["target_node_id"] in node_ids
        ),
        key=lambda edge: edge["edge_id"],
    )
    theme_compositions = sorted(
        (
            composition
            for composition in catalog["theme_compositions"]
            if composition["chain_id"] == chain_id
        ),
        key=lambda composition: composition["composition_id"],
    )
    return {
        "chain": chain,
        "nodes": nodes,
        "edges": edges,
        "theme_compositions": theme_compositions,
    }


def project_theme_to_catalog(
    theme_id: str,
    *,
    catalog: dict[str, Any] | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_catalog = catalog if catalog is not None else load_industry_catalog()
    if not isinstance(resolved_catalog, dict):
        raise _theme_link_invalid("catalog must be an object")
    theme_links = resolved_catalog.get("theme_links")
    if not isinstance(theme_links, list):
        raise _theme_link_invalid("catalog.theme_links must be a list")
    theme_link = next(
        (
            link
            for link in theme_links
            if isinstance(link, dict) and link.get("theme_id") == theme_id
        ),
        None,
    )
    if theme_link is None:
        raise IndustryCatalogValidationError(
            f"theme catalog link not found: {theme_id}",
            code="THEME_CATALOG_LINK_NOT_FOUND",
        )

    chains_by_id, nodes_by_id = _projection_catalog_indexes(resolved_catalog)
    chain_id = _validate_projection_theme_link(
        theme_link,
        theme_id,
        chains_by_id,
        nodes_by_id,
    )
    catalog_chain = chains_by_id[chain_id]

    from stock_research.theme_decomposition import (
        ThemeDecompositionValidationError,
        load_theme,
    )

    try:
        source_theme = load_theme(theme_id, artifact_dir=theme_artifact_dir)
    except (
        ThemeDecompositionValidationError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        OSError,
        KeyError,
        TypeError,
    ) as exc:
        raise IndustryCatalogValidationError(
            f"theme artifact invalid: {exc}",
            code="THEME_ARTIFACT_INVALID",
        ) from exc
    theme, theme_nodes = _validate_theme_detail(source_theme, theme_id)

    theme_nodes_by_id = {
        node["node_id"]: node
        for node in theme_nodes
    }
    node_projections = []
    for node_link in theme_link["node_links"]:
        source_node_id = node_link["theme_node_id"]
        catalog_node_id = node_link["catalog_node_id"]
        theme_node = theme_nodes_by_id.get(source_node_id)
        if theme_node is None:
            raise _theme_catalog_node_link_error(
                f"invalid node link: {source_node_id} -> {catalog_node_id}"
            )
        node_projections.append(
            {"theme_node": theme_node, "catalog_node": nodes_by_id[catalog_node_id]}
        )

    unmapped_theme_node_ids = theme_link["unmapped_theme_node_ids"]
    for source_node_id in unmapped_theme_node_ids:
        if source_node_id not in theme_nodes_by_id:
            raise _theme_catalog_node_link_error(
                f"invalid unmapped theme node: {source_node_id}"
            )

    return copy.deepcopy(
        {
            "theme_id": theme_id,
            "theme_status": theme["status"],
            "chain_id": chain_id,
            "catalog_chain": catalog_chain,
            "node_projections": node_projections,
            "unmapped_theme_node_ids": unmapped_theme_node_ids,
            "source_theme": source_theme,
        }
    )


def configure_industry_catalog_parser(
    parser: argparse.ArgumentParser,
    *,
    dest_prefix: str = "",
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--artifact-dir",
        dest=f"{dest_prefix}artifact_dir",
        default=str(CATALOG_DIR),
    )
    subparsers = parser.add_subparsers(
        dest=f"{dest_prefix}command",
        required=True,
    )
    subparsers.add_parser("validate")
    subparsers.add_parser("summary")
    show = subparsers.add_parser("show")
    show.add_argument("--chain", dest=f"{dest_prefix}chain", required=True)
    return parser


def _projection_catalog_indexes(
    catalog: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    catalog_chains = catalog.get("chains")
    if not isinstance(catalog_chains, list):
        raise _theme_link_invalid("catalog.chains must be a list")
    catalog_nodes = catalog.get("nodes")
    if not isinstance(catalog_nodes, list):
        raise _theme_catalog_node_link_error("catalog.nodes must be a list")
    chains_by_id = {
        chain["chain_id"]: chain
        for chain in catalog_chains
        if isinstance(chain, dict) and isinstance(chain.get("chain_id"), str)
    }
    nodes_by_id = {
        node["node_id"]: node
        for node in catalog_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    return chains_by_id, nodes_by_id


def _validate_projection_theme_link(
    theme_link: Any,
    theme_id: str,
    chains_by_id: dict[str, dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> str:
    if not isinstance(theme_link, dict):
        raise _theme_link_invalid("selected theme link must be an object")
    for field in sorted(THEME_LINK_FIELDS):
        if field not in theme_link:
            raise _theme_link_invalid(f"selected theme link.{field} is required")
    linked_theme_id = _require_reference_string(
        theme_link["theme_id"],
        "selected theme link.theme_id",
        code="THEME_LINK_INVALID",
    )
    if linked_theme_id != theme_id:
        raise _theme_link_invalid(
            f"selected theme link.theme_id does not match: {linked_theme_id}"
        )
    return _validate_theme_link_contents(
        theme_link,
        chains_by_id,
        nodes_by_id,
        "selected theme link",
        projection=True,
    )


def _validate_projection_node_link(node_link: Any, path: str) -> None:
    if not isinstance(node_link, dict):
        raise _theme_catalog_node_link_error(f"{path} must be an object")
    for field in sorted(NODE_LINK_FIELDS):
        if field not in node_link:
            raise _theme_catalog_node_link_error(f"{path}.{field} is required")


def _validate_theme_detail(
    source_theme: Any,
    theme_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(source_theme, dict):
        raise _theme_artifact_invalid("theme detail must be an object")
    theme = source_theme.get("theme")
    nodes = source_theme.get("nodes")
    if not isinstance(theme, dict) or not isinstance(nodes, list):
        raise _theme_artifact_invalid(
            "theme detail must contain theme object and nodes list"
        )
    if theme.get("theme_id") != theme_id:
        raise _theme_artifact_invalid(
            f"theme detail has unexpected theme_id: {theme.get('theme_id')}"
        )
    if not isinstance(theme.get("status"), str) or not theme["status"].strip():
        raise _theme_artifact_invalid(
            "theme detail.theme.status must be a non-empty string"
        )

    theme_nodes: list[dict[str, Any]] = []
    theme_node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        path = f"theme detail.nodes[{index}]"
        if not isinstance(node, dict):
            raise _theme_artifact_invalid(f"{path} must be an object")
        node_id = node.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise _theme_artifact_invalid(f"{path}.node_id must be a non-empty string")
        if node_id in theme_node_ids:
            raise _theme_artifact_invalid(f"{path}.node_id duplicated: {node_id}")
        theme_node_ids.add(node_id)
        theme_nodes.append(node)
    return theme, theme_nodes


def _theme_link_invalid(message: str) -> IndustryCatalogValidationError:
    return IndustryCatalogValidationError(message, code="THEME_LINK_INVALID")


def _theme_artifact_invalid(message: str) -> IndustryCatalogValidationError:
    return IndustryCatalogValidationError(message, code="THEME_ARTIFACT_INVALID")


def execute_parsed_catalog_command(
    args: argparse.Namespace,
    *,
    dest_prefix: str = "",
) -> int:
    artifact_dir = getattr(args, f"{dest_prefix}artifact_dir")
    command = getattr(args, f"{dest_prefix}command")
    try:
        catalog = load_industry_catalog(artifact_dir)
        if command == "validate":
            payload = {"status": "ok", **summarize_industry_catalog(catalog)}
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 0
        if command == "summary":
            payload = summarize_industry_catalog(catalog)
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if command == "show":
            chain = getattr(args, f"{dest_prefix}chain")
            payload = get_industry_chain(catalog, chain)
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except IndustryCatalogValidationError as exc:
        _print_cli_error(exc.code, str(exc))
        return 2
    raise AssertionError(f"unhandled command: {command}")


def cli(argv: list[str] | None = None) -> int:
    parser = configure_industry_catalog_parser(
        _IndustryCatalogArgumentParser(prog="technology-industry-catalog")
    )
    try:
        args = parser.parse_args(argv)
    except IndustryCatalogCliUsageError as exc:
        _print_cli_error("INVALID_CLI_ARGUMENTS", str(exc))
        return 2
    return execute_parsed_catalog_command(args)


def main() -> None:
    raise SystemExit(cli())


def _print_cli_error(error_code: str, message: str) -> None:
    print(
        json.dumps(
            {"status": "error", "error_code": error_code, "message": message},
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def _sorted_counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


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
    if "theme_link_file" in manifest and (
        not isinstance(manifest["theme_link_file"], str)
        or not manifest["theme_link_file"]
    ):
        raise IndustryCatalogValidationError(
            "manifest.theme_link_file must be a non-empty string",
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
    sources_by_id = _validate_sources(catalog["sources"])
    _validate_edges(catalog["edges"], nodes_by_id, sources_by_id)
    _validate_theme_compositions(
        catalog["theme_compositions"],
        chains_by_id,
        nodes_by_id,
    )
    _validate_theme_links(
        catalog["theme_links"],
        chains_by_id,
        nodes_by_id,
    )


def _validate_sectors(sectors: list[Any]) -> dict[str, dict[str, Any]]:
    sectors_by_id = _index_unique_rows(
        sectors,
        fields=SECTOR_FIELDS,
        id_field="sector_id",
        duplicate_code="DUPLICATE_SECTOR_ID",
        path="sectors",
        name_field="sector_name",
    )
    for index, sector in enumerate(sectors):
        _validate_catalog_status(sector["status"], f"sectors[{index}]")
    return sectors_by_id


def _validate_chains(
    chains: list[Any],
    sectors_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    chains_by_id = _index_unique_rows(
        chains,
        fields=CHAIN_FIELDS,
        id_field="chain_id",
        duplicate_code="DUPLICATE_CHAIN_ID",
        path="chains",
        name_field="chain_name",
    )
    for index, chain in enumerate(chains):
        path = f"chains[{index}]"
        _validate_catalog_status(chain["status"], path)
        sector_id = _require_reference_string(
            chain["sector_id"],
            f"{path}.sector_id",
            code="ORPHAN_CHAIN_SECTOR",
        )
        if sector_id not in sectors_by_id:
            raise IndustryCatalogValidationError(
                f"{path}.sector_id references missing sector: {sector_id}",
                code="ORPHAN_CHAIN_SECTOR",
            )
        if (
            not isinstance(chain["chain_kind"], str)
            or chain["chain_kind"] not in CHAIN_KINDS
        ):
            raise IndustryCatalogValidationError(
                f"{path}.chain_kind invalid: {chain['chain_kind']}",
                code="INVALID_CHAIN_KIND",
            )
        if (
            not isinstance(chain["decomposition_method"], str)
            or chain["decomposition_method"] not in DECOMPOSITION_METHODS
        ):
            raise IndustryCatalogValidationError(
                f"{path}.decomposition_method invalid: {chain['decomposition_method']}",
                code="INVALID_DECOMPOSITION_METHOD",
            )
    return chains_by_id


def _validate_nodes(
    nodes: list[Any],
    chains_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    nodes_by_id = _index_unique_rows(
        nodes,
        fields=NODE_FIELDS,
        id_field="node_id",
        duplicate_code="DUPLICATE_NODE_ID",
        path="nodes",
        name_field="node_name",
    )
    canonical_owners: set[str] = set()
    expected_kind_by_chain = {
        "canonical_industry_chain": "canonical",
        "application_theme_chain": "application_role",
        "frontier_technology_chain": "frontier_route",
    }

    for index, node in enumerate(nodes):
        path = f"nodes[{index}]"
        _validate_catalog_status(node["status"], path)
        node_id = node["node_id"]
        chain_id = _require_reference_string(
            node["chain_id"],
            f"{path}.chain_id",
            code="ORPHAN_NODE_CHAIN",
        )
        chain = chains_by_id.get(chain_id)
        if chain is None:
            raise IndustryCatalogValidationError(
                f"{path}.chain_id references missing chain: {chain_id}",
                code="ORPHAN_NODE_CHAIN",
            )
        if not isinstance(node["level"], str) or node["level"] not in NODE_LEVELS:
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
        canonical_key = node["canonical_key"]
        if not isinstance(canonical_key, str):
            raise IndustryCatalogValidationError(
                f"{path}.canonical_key must be a string",
                code="INVALID_CANONICAL_OWNERSHIP",
            )
        if node["node_kind"] == "application_role" and canonical_key:
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
            parent_node_id = _require_reference_string(
                node["parent_node_id"],
                f"{path}.parent_node_id",
                code="ORPHAN_NODE_PARENT",
            )
            parent = nodes_by_id.get(parent_node_id)
            if (
                parent is None
                or parent.get("level") != "L3"
                or parent.get("chain_id") != chain_id
            ):
                raise IndustryCatalogValidationError(
                    f"{path}.parent_node_id must reference an L3 node in the same chain",
                    code="ORPHAN_NODE_PARENT",
                )

        if (
            node["level"] == "L4"
            and node["node_kind"] in {"canonical", "application_role"}
        ):
            expected_path = [
                chain["sector_id"],
                chain_id,
                node["parent_node_id"],
                node_id,
            ]
            if node["primary_path"] != expected_path:
                raise IndustryCatalogValidationError(
                    f"{path}.primary_path must equal {expected_path}",
                    code="INVALID_PRIMARY_PATH",
                )

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
        if (
            node["node_kind"] == "application_role"
            and node["level"] == "L4"
            and not node["canonical_node_refs"]
        ):
            raise IndustryCatalogValidationError(
                f"{path}.canonical_node_refs must not be empty for application roles",
                code="INVALID_CANONICAL_NODE_REFERENCE",
            )

    return nodes_by_id


def _validate_edges(
    edges: list[Any],
    nodes_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> None:
    _index_unique_rows(
        edges,
        fields=EDGE_FIELDS,
        id_field="edge_id",
        duplicate_code="DUPLICATE_EDGE_ID",
        path="edges",
    )
    for index, edge in enumerate(edges):
        path = f"edges[{index}]"
        source_node_id = _require_reference_string(
            edge["source_node_id"],
            f"{path}.source_node_id",
            code="ORPHAN_EDGE_SOURCE",
        )
        if source_node_id not in nodes_by_id:
            raise IndustryCatalogValidationError(
                f"{path}.source_node_id references missing node: {source_node_id}",
                code="ORPHAN_EDGE_SOURCE",
            )
        target_node_id = _require_reference_string(
            edge["target_node_id"],
            f"{path}.target_node_id",
            code="ORPHAN_EDGE_TARGET",
        )
        if target_node_id not in nodes_by_id:
            raise IndustryCatalogValidationError(
                f"{path}.target_node_id references missing node: {target_node_id}",
                code="ORPHAN_EDGE_TARGET",
            )
        _validate_relationship_type(edge["relationship_type"], path)
        _validate_source_refs(edge["source_ids"], sources_by_id, f"{path}.source_ids")


def _validate_theme_compositions(
    compositions: list[Any],
    chains_by_id: dict[str, dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> None:
    _index_unique_rows(
        compositions,
        fields=COMPOSITION_FIELDS,
        id_field="composition_id",
        duplicate_code="DUPLICATE_COMPOSITION_ID",
        path="theme_compositions",
    )
    compositions_by_role_id: dict[str, dict[str, Any]] = {}
    for index, composition in enumerate(compositions):
        path = f"theme_compositions[{index}]"
        chain_id = _require_reference_string(
            composition["chain_id"],
            f"{path}.chain_id",
            code="ORPHAN_COMPOSITION_CHAIN",
        )
        chain = chains_by_id.get(chain_id)
        if chain is None:
            raise IndustryCatalogValidationError(
                f"{path}.chain_id references missing chain: {chain_id}",
                code="ORPHAN_COMPOSITION_CHAIN",
            )
        role_node_id = _require_reference_string(
            composition["role_node_id"],
            f"{path}.role_node_id",
            code="ORPHAN_COMPOSITION_ROLE",
        )
        role = nodes_by_id.get(role_node_id)
        if role is None:
            raise IndustryCatalogValidationError(
                f"{path}.role_node_id references missing node: {role_node_id}",
                code="ORPHAN_COMPOSITION_ROLE",
            )
        if role.get("chain_id") != chain_id:
            raise IndustryCatalogValidationError(
                f"{path}.chain_id must match {role_node_id}.chain_id",
                code="COMPOSITION_REFERENCE_MISMATCH",
            )
        if (
            chain["chain_kind"] != "application_theme_chain"
            or role.get("node_kind") != "application_role"
        ):
            raise IndustryCatalogValidationError(
                f"{path}.role_node_id must reference an application role",
                code="INVALID_COMPOSITION_ROLE",
            )
        _validate_relationship_type(composition["relationship_type"], path)
        _validate_canonical_node_refs(
            composition["canonical_node_refs"],
            nodes_by_id,
            f"{path}.canonical_node_refs",
        )
        if role_node_id in compositions_by_role_id:
            raise IndustryCatalogValidationError(
                f"{path}.role_node_id has multiple compositions: {role_node_id}",
                code="DUPLICATE_ROLE_COMPOSITION",
            )
        role_refs = role["canonical_node_refs"]
        composition_refs = composition["canonical_node_refs"]
        if (
            len(role_refs) != len(set(role_refs))
            or len(composition_refs) != len(set(composition_refs))
            or set(role_refs) != set(composition_refs)
        ):
            raise IndustryCatalogValidationError(
                f"{path}.canonical_node_refs must match {role_node_id}.canonical_node_refs",
                code="COMPOSITION_REFERENCE_MISMATCH",
            )
        compositions_by_role_id[role_node_id] = composition

    for node_id, node in nodes_by_id.items():
        if (
            node["node_kind"] == "application_role"
            and node["level"] == "L4"
            and node_id not in compositions_by_role_id
        ):
            raise IndustryCatalogValidationError(
                f"application role requires a composition: {node_id}",
                code="APPLICATION_ROLE_REQUIRES_COMPOSITION",
            )


def _validate_theme_links(
    theme_links: list[Any],
    chains_by_id: dict[str, dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> None:
    _index_unique_rows(
        theme_links,
        fields=THEME_LINK_FIELDS,
        id_field="theme_id",
        duplicate_code="DUPLICATE_THEME_LINK",
        path="theme_links",
    )
    for index, theme_link in enumerate(theme_links):
        path = f"theme_links[{index}]"
        _validate_theme_link_contents(
            theme_link,
            chains_by_id,
            nodes_by_id,
            path,
        )


def _validate_theme_link_contents(
    theme_link: dict[str, Any],
    chains_by_id: dict[str, dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    path: str,
    *,
    projection: bool = False,
) -> str:
    chain_id = _require_reference_string(
        theme_link["chain_id"],
        f"{path}.chain_id",
        code="THEME_LINK_CHAIN_NOT_FOUND",
    )
    if chain_id not in chains_by_id:
        raise IndustryCatalogValidationError(
            f"{path}.chain_id references missing chain: {chain_id}",
            code="THEME_LINK_CHAIN_NOT_FOUND",
        )

    linked_theme_node_ids = _validate_node_links(
        theme_link["node_links"],
        nodes_by_id,
        chain_id,
        f"{path}.node_links",
        projection=projection,
    )
    _validate_unmapped_theme_node_ids(
        theme_link["unmapped_theme_node_ids"],
        linked_theme_node_ids,
        f"{path}.unmapped_theme_node_ids",
    )
    return chain_id


def _validate_node_links(
    node_links: Any,
    nodes_by_id: dict[str, dict[str, Any]],
    chain_id: str,
    path: str,
    *,
    projection: bool = False,
) -> set[str]:
    if not isinstance(node_links, list):
        raise _theme_catalog_node_link_error(f"{path} must be a list")

    theme_node_ids: set[str] = set()
    for index, node_link in enumerate(node_links):
        node_link_path = f"{path}[{index}]"
        if projection:
            _validate_projection_node_link(node_link, node_link_path)
        else:
            _require_fields(node_link, NODE_LINK_FIELDS, node_link_path)
        theme_node_id = _require_reference_string(
            node_link["theme_node_id"],
            f"{node_link_path}.theme_node_id",
            code="THEME_CATALOG_NODE_LINK_INVALID",
        )
        catalog_node_id = _require_reference_string(
            node_link["catalog_node_id"],
            f"{node_link_path}.catalog_node_id",
            code="THEME_CATALOG_NODE_LINK_INVALID",
        )
        catalog_node = nodes_by_id.get(catalog_node_id)
        if (
            theme_node_id in theme_node_ids
            or catalog_node is None
            or catalog_node.get("level") not in NODE_LEVELS
            or catalog_node.get("chain_id") != chain_id
        ):
            raise _theme_catalog_node_link_error(
                f"{node_link_path} invalid: {theme_node_id} -> {catalog_node_id}"
            )
        theme_node_ids.add(theme_node_id)
    return theme_node_ids


def _validate_unmapped_theme_node_ids(
    unmapped_theme_node_ids: Any,
    linked_theme_node_ids: set[str],
    path: str,
) -> None:
    if not isinstance(unmapped_theme_node_ids, list):
        raise _theme_catalog_node_link_error(f"{path} must be a list")

    seen_theme_node_ids: set[str] = set()
    for index, theme_node_id in enumerate(unmapped_theme_node_ids):
        theme_node_id = _require_reference_string(
            theme_node_id,
            f"{path}[{index}]",
            code="THEME_CATALOG_NODE_LINK_INVALID",
        )
        if (
            theme_node_id in seen_theme_node_ids
            or theme_node_id in linked_theme_node_ids
        ):
            raise _theme_catalog_node_link_error(
                f"{path}[{index}] duplicates a linked or unmapped node: {theme_node_id}"
            )
        seen_theme_node_ids.add(theme_node_id)


def _theme_catalog_node_link_error(message: str) -> IndustryCatalogValidationError:
    return IndustryCatalogValidationError(
        message,
        code="THEME_CATALOG_NODE_LINK_INVALID",
    )


def _validate_sources(sources: list[Any]) -> dict[str, dict[str, Any]]:
    return _index_unique_rows(
        sources,
        fields=SOURCE_FIELDS,
        id_field="source_id",
        duplicate_code="DUPLICATE_SOURCE_ID",
        path="sources",
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
    for index, value in enumerate(references):
        node_id = _require_reference_string(
            value,
            f"{path}[{index}]",
            code="INVALID_CANONICAL_NODE_REFERENCE",
        )
        node = nodes_by_id.get(node_id)
        if (
            node is None
            or node.get("node_kind") != "canonical"
            or node.get("level") != "L4"
        ):
            raise IndustryCatalogValidationError(
                f"{path} references non-canonical L4 node: {node_id}",
                code="INVALID_CANONICAL_NODE_REFERENCE",
            )


def _validate_source_refs(
    references: Any,
    sources_by_id: dict[str, dict[str, Any]],
    path: str,
) -> None:
    if not isinstance(references, list):
        raise IndustryCatalogValidationError(
            f"{path} must be a list",
            code="INVALID_SOURCE_REFERENCE",
        )
    for index, value in enumerate(references):
        source_id = _require_reference_string(
            value,
            f"{path}[{index}]",
            code="INVALID_SOURCE_REFERENCE",
        )
        if source_id not in sources_by_id:
            raise IndustryCatalogValidationError(
                f"{path} references missing source: {source_id}",
                code="INVALID_SOURCE_REFERENCE",
            )


def _validate_relationship_type(value: Any, path: str) -> None:
    if not isinstance(value, str) or value not in EDGE_TYPES:
        raise IndustryCatalogValidationError(
            f"{path}.relationship_type invalid: {value}",
            code="INVALID_RELATIONSHIP_TYPE",
        )


def _validate_catalog_status(value: Any, path: str) -> None:
    if not isinstance(value, str) or value not in CATALOG_STATUSES:
        raise IndustryCatalogValidationError(
            f"{path}.status invalid: {value}",
            code="INVALID_CATALOG_STATUS",
        )


def _index_unique_rows(
    rows: list[Any],
    *,
    fields: set[str],
    id_field: str,
    duplicate_code: str,
    path: str,
    name_field: str | None = None,
) -> dict[str, dict[str, Any]]:
    rows_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        row_path = f"{path}[{index}]"
        _require_fields(row, fields, row_path)
        row_id = _require_non_empty_string(row, id_field, row_path)
        if name_field is not None:
            _require_non_empty_string(row, name_field, row_path)
        if row_id in rows_by_id:
            raise IndustryCatalogValidationError(
                f"{row_path}.{id_field} duplicated: {row_id}",
                code=duplicate_code,
            )
        rows_by_id[row_id] = row
    return rows_by_id


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


def _require_reference_string(value: Any, path: str, *, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IndustryCatalogValidationError(
            f"{path} must be a non-empty string",
            code=code,
        )
    return value


if __name__ == "__main__":
    main()
