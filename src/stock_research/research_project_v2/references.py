from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Callable

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
THEME_ARTIFACT_DIR = REPOSITORY_ROOT / "artifacts/theme_decomposition"
COMPANY_MAPPING_DIR = THEME_ARTIFACT_DIR / "company_mappings"
INDUSTRY_CATALOG_DIR = REPOSITORY_ROOT / "artifacts/technology_industry_catalog/v1"

_UNRESOLVABLE = "RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE"
_HASH_FIELDS_REQUIRED = "RESEARCH_PROJECT_REFERENCE_HASH_FIELDS_REQUIRED"
_DEPRECATED_STATES = {"deprecated", "archived", "superseded", "retired"}


@dataclass(frozen=True)
class ResolvedReference:
    namespace: str
    object_type: str
    object_id: str
    version: str | None
    payload: dict[str, Any]
    deprecated: bool = False


Resolver = Callable[[dict[str, Any]], ResolvedReference | None]


def _error(code: str, message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(message, code=code, details=details)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise _error(_UNRESOLVABLE, f"Expected JSON object in {path}")
    return payload


def _is_deprecated(*objects: dict[str, Any]) -> bool:
    for obj in objects:
        for field in ("status", "lifecycle_status", "review_status"):
            value = obj.get(field)
            if isinstance(value, str) and value.casefold() in _DEPRECATED_STATES:
                return True
    return False


def _add_entry(
    index: dict[tuple[str, str], list[ResolvedReference]],
    *,
    namespace: str,
    object_type: str,
    id_field: str,
    payload: object,
    version: object,
    artifact: dict[str, Any],
) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get(id_field), str):
        return
    object_id = payload[id_field]
    index.setdefault((object_type, object_id), []).append(
        ResolvedReference(
            namespace=namespace,
            object_type=object_type,
            object_id=object_id,
            version=version if isinstance(version, str) else None,
            payload=payload,
            deprecated=_is_deprecated(payload, artifact, artifact.get("theme", {})),
        )
    )


@lru_cache(maxsize=1)
def _theme_index() -> dict[tuple[str, str], tuple[ResolvedReference, ...]]:
    index: dict[tuple[str, str], list[ResolvedReference]] = {}
    for path in sorted(THEME_ARTIFACT_DIR.glob("*.json")):
        artifact = _read_json(path)
        theme = artifact.get("theme")
        version = artifact.get("artifact_version")
        if not isinstance(theme, dict) or not isinstance(version, str):
            continue
        _add_entry(
            index,
            namespace="theme_research_v1",
            object_type="v1_theme",
            id_field="theme_id",
            payload=theme,
            version=version,
            artifact=artifact,
        )
        for collection, object_type, id_field in (
            ("nodes", "v1_theme_node", "node_id"),
            ("sources", "v1_source", "source_id"),
            ("claims", "v1_claim", "claim_id"),
        ):
            values = artifact.get(collection, [])
            if not isinstance(values, list):
                continue
            for payload in values:
                _add_entry(
                    index,
                    namespace="theme_research_v1",
                    object_type=object_type,
                    id_field=id_field,
                    payload=payload,
                    version=version,
                    artifact=artifact,
                )

    for path in sorted(COMPANY_MAPPING_DIR.glob("*.json")):
        artifact = _read_json(path)
        version = artifact.get("artifact_version")
        mappings = artifact.get("company_mappings", [])
        if not isinstance(version, str) or not isinstance(mappings, list):
            continue
        for payload in mappings:
            _add_entry(
                index,
                namespace="theme_research_v1",
                object_type="v1_company_mapping",
                id_field="mapping_id",
                payload=payload,
                version=version,
                artifact=artifact,
            )
    return {key: tuple(entries) for key, entries in index.items()}


@lru_cache(maxsize=1)
def _catalog_index() -> dict[tuple[str, str], tuple[ResolvedReference, ...]]:
    manifest = _read_json(INDUSTRY_CATALOG_DIR / "manifest.json")
    version = manifest.get("artifact_version")
    index: dict[tuple[str, str], list[ResolvedReference]] = {}

    chains_artifact = _read_json(INDUSTRY_CATALOG_DIR / "chains.json")
    chains = chains_artifact.get("chains", [])
    if isinstance(chains, list):
        for payload in chains:
            _add_entry(
                index,
                namespace="industry_catalog_v1",
                object_type="industry_catalog_chain",
                id_field="chain_id",
                payload=payload,
                version=version,
                artifact=manifest,
            )

    for path in sorted((INDUSTRY_CATALOG_DIR / "nodes").glob("*.json")):
        nodes_artifact = _read_json(path)
        nodes = nodes_artifact.get("nodes", [])
        if not isinstance(nodes, list):
            continue
        for payload in nodes:
            _add_entry(
                index,
                namespace="industry_catalog_v1",
                object_type="industry_catalog_node",
                id_field="node_id",
                payload=payload,
                version=version,
                artifact=manifest,
            )
    return {key: tuple(entries) for key, entries in index.items()}


def _resolve_from_index(
    reference: dict[str, Any],
    index: dict[tuple[str, str], tuple[ResolvedReference, ...]],
) -> ResolvedReference | None:
    requested_type = reference.get("reference_type")
    object_id = reference.get("reference_object_id")
    exact = index.get((requested_type, object_id), ())
    if len(exact) > 1:
        raise _error(
            _UNRESOLVABLE,
            f"Ambiguous reference: {requested_type}/{object_id}",
            reference_type=requested_type,
            reference_object_id=object_id,
        )
    if len(exact) == 1:
        return _copy_resolved(exact[0])

    other_types = [
        entries[0]
        for (object_type, candidate_id), entries in sorted(index.items())
        if candidate_id == object_id and object_type != requested_type and len(entries) == 1
    ]
    ambiguous_other = any(
        candidate_id == object_id and len(entries) > 1
        for (_, candidate_id), entries in index.items()
    )
    if ambiguous_other or len(other_types) > 1:
        raise _error(
            _UNRESOLVABLE,
            f"Ambiguous reference ID: {object_id}",
            reference_object_id=object_id,
        )
    if other_types:
        return _copy_resolved(other_types[0])
    return None


def _copy_resolved(resolved: ResolvedReference) -> ResolvedReference:
    return ResolvedReference(
        namespace=resolved.namespace,
        object_type=resolved.object_type,
        object_id=resolved.object_id,
        version=resolved.version,
        payload=deepcopy(resolved.payload),
        deprecated=resolved.deprecated,
    )


def resolve_theme_research_v1(
    reference: dict[str, Any],
) -> ResolvedReference | None:
    return _resolve_from_index(reference, _theme_index())


def resolve_industry_catalog_v1(
    reference: dict[str, Any],
) -> ResolvedReference | None:
    return _resolve_from_index(reference, _catalog_index())


RESOLVERS: dict[str, Resolver] = {
    "theme_research_v1": resolve_theme_research_v1,
    "industry_catalog_v1": resolve_industry_catalog_v1,
}


def _decode_pointer_token(token: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(token):
        character = token[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
            raise _error(_UNRESOLVABLE, "Invalid JSON Pointer escape")
        decoded.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)


def resolve_json_pointer(payload: Any, path: str) -> Any:
    if not isinstance(path, str) or not path.startswith("/"):
        raise _error(_UNRESOLVABLE, f"Invalid JSON Pointer: {path!r}")
    current = payload
    for raw_token in path[1:].split("/"):
        token = _decode_pointer_token(raw_token)
        if isinstance(current, dict):
            if token not in current:
                raise _error(_UNRESOLVABLE, f"JSON Pointer key not found: {path}")
            current = current[token]
        elif isinstance(current, list):
            if token == "-" or not token.isdigit():
                raise _error(_UNRESOLVABLE, f"Invalid JSON Pointer index: {path}")
            item_index = int(token)
            if item_index >= len(current):
                raise _error(_UNRESOLVABLE, f"JSON Pointer index out of range: {path}")
            current = current[item_index]
        else:
            raise _error(_UNRESOLVABLE, f"JSON Pointer cannot traverse value: {path}")
    return current


def reference_payload(
    payload: dict[str, Any], reference: dict[str, Any]
) -> Any:
    hash_scope = reference.get("hash_scope")
    if hash_scope == "entire_object":
        return payload
    if hash_scope == "selected_fields":
        hash_fields = reference.get("hash_fields")
        if not isinstance(hash_fields, list) or not hash_fields:
            raise _error(
                _HASH_FIELDS_REQUIRED,
                "selected_fields hash scope requires hash_fields",
            )
        return {path: resolve_json_pointer(payload, path) for path in hash_fields}
    if hash_scope == "metadata_only":
        return payload.get("metadata", {})
    if hash_scope == "source_content":
        raise _error(
            _UNRESOLVABLE,
            "source_content hashing requires an archived source payload",
        )
    raise _error(_UNRESOLVABLE, f"Unsupported hash scope: {hash_scope}")


def _issue(reference_id: object, status: str, **details: object) -> dict[str, Any]:
    return {"reference_id": reference_id, "status": status, **details}


def audit_references(version: dict[str, Any]) -> dict[str, Any]:
    references = version.get("references", [])
    issues: list[dict[str, Any]] = []
    resolved_count = 0
    seen: set[tuple[object, object, object, object]] = set()

    for reference in references:
        reference_id = reference.get("reference_id")
        duplicate_key = (
            reference.get("reference_namespace"),
            reference.get("reference_type"),
            reference.get("reference_object_id"),
            reference.get("reference_role"),
        )
        if duplicate_key in seen:
            issues.append(_issue(reference_id, "duplicate"))
            continue
        seen.add(duplicate_key)

        if reference.get("hash_scope") == "source_content":
            issues.append(
                _issue(
                    reference_id,
                    "unresolvable",
                    error_code=_UNRESOLVABLE,
                )
            )
            continue

        namespace = reference.get("reference_namespace")
        resolver = RESOLVERS.get(namespace)
        if resolver is None:
            issues.append(
                _issue(
                    reference_id,
                    "unresolvable",
                    error_code=_UNRESOLVABLE,
                )
            )
            continue

        try:
            resolved = resolver(reference)
            if resolved is None:
                issues.append(_issue(reference_id, "missing"))
                continue
            expected_type = reference.get("reference_type")
            if resolved.object_type != expected_type:
                issues.append(
                    _issue(
                        reference_id,
                        "type_mismatch",
                        expected_type=expected_type,
                        actual_type=resolved.object_type,
                    )
                )
                continue

            hash_scope = reference.get("hash_scope")
            scoped_payload = None
            if hash_scope is not None:
                scoped_payload = reference_payload(resolved.payload, reference)

            expected_version = reference.get("reference_version")
            if expected_version is not None and expected_version != resolved.version:
                issues.append(
                    _issue(
                        reference_id,
                        "version_mismatch",
                        expected_version=expected_version,
                        actual_version=resolved.version,
                    )
                )
                continue
            if resolved.deprecated:
                issues.append(_issue(reference_id, "deprecated"))
                continue

            expected_hash = reference.get("reference_content_hash")
            if expected_hash is not None:
                if scoped_payload is None:
                    scoped_payload = reference_payload(resolved.payload, reference)
                actual_hash = content_sha256(scoped_payload)
                if expected_hash != actual_hash:
                    issues.append(
                        _issue(
                            reference_id,
                            "hash_mismatch",
                            expected_hash=expected_hash,
                            actual_hash=actual_hash,
                            algorithm="sha256-jcs-v1",
                            hash_scope=hash_scope,
                        )
                    )
                    continue
        except ResearchProjectV2Error as exc:
            issues.append(
                _issue(reference_id, "unresolvable", error_code=exc.code)
            )
            continue
        resolved_count += 1

    return {
        "status": "pass" if not issues else "fail",
        "total": len(references),
        "resolved": resolved_count,
        "issues": issues,
    }


__all__ = [
    "RESOLVERS",
    "Resolver",
    "ResolvedReference",
    "audit_references",
    "reference_payload",
    "resolve_industry_catalog_v1",
    "resolve_json_pointer",
    "resolve_theme_research_v1",
]
