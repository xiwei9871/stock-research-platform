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
    except OSError as exc:
        raise IndustryCatalogValidationError(
            f"unable to read package file {path}: {exc}",
            code="PACKAGE_READ_ERROR",
        ) from exc

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
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
