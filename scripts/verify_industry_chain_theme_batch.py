#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

from stock_research.ai_power_source_pack import (
    AiPowerEvidenceValidationError,
    EVIDENCE_GAP_STATUSES,
    NODE_MATRIX_FIELDS,
    NODE_REVIEW_STATUSES,
    SCORE_REVIEW_STATUSES,
    VALUE_BASES,
    validate_theme_evidence_sources,
)
from stock_research.industry_chain_theme_research import classify_beneficiary
from stock_research.theme_company_mapping import (
    ThemeCompanyMappingValidationError,
    validate_theme_company_mapping_artifact,
)
from stock_research.theme_decomposition import (
    CLAIM_FIELDS,
    CLAIM_PLATFORM_USE_STATUSES,
    CLAIM_TYPES,
    EVIDENCE_STATUSES,
)


ARTIFACT_KEYS = (
    "theme",
    "company_mapping",
    "source_pack",
    "node_evidence_matrix",
)
NUMERIC_GATE_KEYS = (
    "min_accepted_sources",
    "min_primary_sources",
    "min_claims",
    "min_reviewed_mappings",
)
SUPPORTED_SCHEMA_VERSION = "industry_chain_theme_batch_v1"
MATRIX_COVERAGE_STATUSES = EVIDENCE_GAP_STATUSES
MATRIX_EXPLICIT_GAP_STATUSES = {"technical_route_only", "evidence_gap"}


def load_theme_batch_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Theme batch manifest does not exist: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in theme batch manifest {manifest_path}: {exc.msg}"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Theme batch manifest is not readable: {manifest_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Theme batch manifest must contain a JSON object: {manifest_path}")
    _validate_manifest(payload, manifest_path)
    return payload


def build_theme_batch_report(
    manifest_path: str | Path,
    wave: str | None = None,
) -> dict[str, Any]:
    resolved_manifest_path = Path(manifest_path).expanduser().resolve()
    manifest = load_theme_batch_manifest(resolved_manifest_path)
    waves = manifest["waves"]
    if wave is not None and wave not in waves:
        raise ValueError(
            f"Unknown wave {wave!r}; expected one of: {', '.join(waves)}"
        )
    selected_waves = [wave] if wave is not None else list(waves)
    artifact_base = (
        resolved_manifest_path.parent / manifest.get("artifact_base", ".")
    ).resolve()
    gates = manifest["completion_gates"]
    primary_source_types = set(manifest["primary_source_types"])

    theme_results: list[dict[str, Any]] = []
    wave_results: dict[str, dict[str, Any]] = {}
    for wave_name in selected_waves:
        current_results = [
            _build_theme_result(
                chain_id=chain_id,
                wave_name=wave_name,
                metadata=manifest["themes"][chain_id],
                artifact_base=artifact_base,
                gates=gates,
                primary_source_types=primary_source_types,
            )
            for chain_id in waves[wave_name]
        ]
        theme_results.extend(current_results)
        ready_count = sum(row["ready"] for row in current_results)
        wave_results[wave_name] = {
            "theme_count": len(current_results),
            "ready_theme_count": ready_count,
            "not_ready_theme_count": len(current_results) - ready_count,
            "ready": ready_count == len(current_results),
            "theme_ids": [row["theme_id"] for row in current_results],
        }

    ready_theme_count = sum(row["ready"] for row in theme_results)
    all_ready = ready_theme_count == len(theme_results)
    return {
        "batch_id": manifest["batch_id"],
        "target_theme_count": manifest["target_theme_count"],
        "selected_waves": selected_waves,
        "evaluated_theme_count": len(theme_results),
        "ready_theme_count": ready_theme_count,
        "not_ready_theme_count": len(theme_results) - ready_theme_count,
        "wave_results": wave_results,
        "theme_results": theme_results,
        "completion_status": "ready" if all_ready else "not_ready",
    }


def assert_theme_batch_ready(report: dict[str, Any]) -> None:
    if report.get("completion_status") == "ready":
        return
    failures = []
    for row in report.get("theme_results", []):
        if row.get("ready"):
            continue
        failed_checks = [
            name for name, passed in row.get("checks", {}).items() if not passed
        ]
        detail = ", ".join(failed_checks) or "unknown readiness failure"
        if row.get("errors"):
            detail = f"{detail}; {'; '.join(row['errors'])}"
        failures.append(f"{row.get('chain_id', '<unknown>')}: {detail}")
    raise AssertionError(
        "Theme batch is not ready: " + (" | ".join(failures) or "no theme results")
    )


def _validate_manifest(manifest: dict[str, Any], path: Path) -> None:
    for key in (
        "schema_version",
        "batch_id",
        "target_theme_count",
        "waves",
        "themes",
        "primary_source_types",
        "completion_gates",
    ):
        if key not in manifest:
            raise ValueError(f"Theme batch manifest {path} is missing {key!r}")
    if manifest["schema_version"] != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"Theme batch manifest {path} schema_version must be "
            f"{SUPPORTED_SCHEMA_VERSION!r}"
        )
    if not isinstance(manifest["batch_id"], str) or not manifest["batch_id"]:
        raise ValueError(f"Theme batch manifest {path} has an invalid batch_id")
    artifact_base = manifest.get("artifact_base", ".")
    if not isinstance(artifact_base, str) or not artifact_base.strip():
        raise ValueError(
            f"Theme batch manifest {path} artifact_base must be a non-empty string path"
        )
    if not isinstance(manifest["waves"], dict) or not manifest["waves"]:
        raise ValueError(f"Theme batch manifest {path} must define non-empty waves")
    if not isinstance(manifest["themes"], dict) or not manifest["themes"]:
        raise ValueError(f"Theme batch manifest {path} must define non-empty themes")

    ordered_chain_ids: list[str] = []
    for wave_name, chain_ids in manifest["waves"].items():
        if not isinstance(wave_name, str) or not wave_name:
            raise ValueError(f"Theme batch manifest {path} has an invalid wave name")
        if not isinstance(chain_ids, list) or not chain_ids:
            raise ValueError(f"Theme batch manifest {path} wave {wave_name!r} is empty")
        if not all(isinstance(chain_id, str) and chain_id for chain_id in chain_ids):
            raise ValueError(
                f"Theme batch manifest {path} wave {wave_name!r} has invalid chain IDs"
            )
        ordered_chain_ids.extend(chain_ids)
    if len(ordered_chain_ids) != len(set(ordered_chain_ids)):
        raise ValueError(f"Theme batch manifest {path} repeats a chain across waves")

    theme_ids = set(manifest["themes"])
    wave_ids = set(ordered_chain_ids)
    if theme_ids != wave_ids:
        missing = sorted(theme_ids - wave_ids)
        unknown = sorted(wave_ids - theme_ids)
        raise ValueError(
            f"Theme batch manifest {path} wave/theme scope mismatch: "
            f"not_in_waves={missing}, missing_metadata={unknown}"
        )
    target_count = manifest["target_theme_count"]
    if not isinstance(target_count, int) or isinstance(target_count, bool):
        raise ValueError(f"Theme batch manifest {path} has an invalid target_theme_count")
    if target_count != len(theme_ids):
        raise ValueError(
            f"Theme batch manifest {path} target_theme_count={target_count} "
            f"does not match themes={len(theme_ids)}"
        )

    resolved_artifact_base = (path.parent / artifact_base).resolve()
    manifest_theme_ids: set[str] = set()
    resolved_artifact_owners: dict[Path, tuple[str, str]] = {}
    for chain_id, metadata in manifest["themes"].items():
        if not isinstance(metadata, dict):
            raise ValueError(
                f"Theme batch manifest {path} theme {chain_id!r} metadata must be an object"
            )
        theme_id = metadata.get("theme_id")
        if not isinstance(theme_id, str) or not theme_id.strip():
            raise ValueError(
                f"Theme batch manifest {path} theme {chain_id!r}.theme_id "
                "must be a non-empty string"
            )
        if theme_id in manifest_theme_ids:
            raise ValueError(
                f"Theme batch manifest {path} has duplicate theme_id: {theme_id}"
            )
        manifest_theme_ids.add(theme_id)
        artifacts = metadata.get("artifacts")
        if not isinstance(artifacts, dict) or set(artifacts) != set(ARTIFACT_KEYS):
            raise ValueError(
                f"Theme batch manifest {path} theme {chain_id!r} must define artifacts "
                f"{list(ARTIFACT_KEYS)}"
            )
        for artifact_name in ARTIFACT_KEYS:
            field = f"themes.{chain_id}.artifacts.{artifact_name}"
            value = artifacts[artifact_name]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Theme batch manifest {path} {field} must be a non-empty string path"
                )
            artifact_path = Path(value)
            if artifact_path.is_absolute():
                raise ValueError(
                    f"Theme batch manifest {path} {field} must be relative to artifact_base"
                )
            if ".." in artifact_path.parts:
                raise ValueError(
                    f"Theme batch manifest {path} {field} cannot contain '..'"
                )
            if artifact_path.suffix.lower() != ".json":
                raise ValueError(
                    f"Theme batch manifest {path} {field} must name a JSON file"
                )
            resolved_path = (resolved_artifact_base / artifact_path).resolve()
            if resolved_path in resolved_artifact_owners:
                owner_chain, owner_artifact = resolved_artifact_owners[resolved_path]
                raise ValueError(
                    f"Theme batch manifest {path} {field} reuses resolved artifact path "
                    f"owned by themes.{owner_chain}.artifacts.{owner_artifact}: "
                    f"{resolved_path}"
                )
            resolved_artifact_owners[resolved_path] = (chain_id, artifact_name)

    source_types = manifest["primary_source_types"]
    if not isinstance(source_types, list) or not source_types or not all(
        isinstance(value, str) and value for value in source_types
    ):
        raise ValueError(f"Theme batch manifest {path} has invalid primary_source_types")
    gates = manifest["completion_gates"]
    if not isinstance(gates, dict):
        raise ValueError(f"Theme batch manifest {path} has invalid completion_gates")
    for key in NUMERIC_GATE_KEYS:
        value = gates.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(
                f"Theme batch manifest {path} completion gate {key!r} must be non-negative"
            )
    if not isinstance(gates.get("require_node_evidence_matrix_coverage"), bool):
        raise ValueError(
            f"Theme batch manifest {path} completion gate "
            "'require_node_evidence_matrix_coverage' must be boolean"
        )
    sections = gates.get("required_readable_sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError(
            f"Theme batch manifest {path} must define required_readable_sections"
        )
    section_names = []
    for section in sections:
        if not isinstance(section, dict) or not section.get("name"):
            raise ValueError(f"Theme batch manifest {path} has an invalid readable section")
        requirements = section.get("non_empty")
        if not isinstance(requirements, list) or not requirements or not all(
            _valid_requirement(value) for value in requirements
        ):
            raise ValueError(
                f"Theme batch manifest {path} section {section['name']!r} "
                "must define artifact:path non_empty requirements"
            )
        section_names.append(section["name"])
    if len(section_names) != len(set(section_names)):
        raise ValueError(f"Theme batch manifest {path} repeats a readable section name")


def _valid_requirement(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    artifact_name, separator, field_path = value.partition(":")
    return bool(
        separator
        and artifact_name in ARTIFACT_KEYS
        and field_path
        and all(field_path.split("."))
    )


def _build_theme_result(
    *,
    chain_id: str,
    wave_name: str,
    metadata: dict[str, Any],
    artifact_base: Path,
    gates: dict[str, Any],
    primary_source_types: set[str],
) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any] | None] = {}
    artifact_paths: dict[str, str] = {}
    errors: list[str] = []
    for artifact_name in ARTIFACT_KEYS:
        path = (artifact_base / metadata["artifacts"][artifact_name]).resolve()
        artifact_paths[artifact_name] = str(path)
        payload, error = _load_json_artifact(path)
        artifacts[artifact_name] = payload
        if error:
            errors.append(error)

    expected_theme_id = metadata["theme_id"]
    theme_node_ids, theme_nodes_valid, node_errors = _validate_theme_nodes(
        artifacts["theme"],
        expected_theme_id=expected_theme_id,
    )
    errors.extend(node_errors)
    (
        accepted_sources,
        known_source_ids,
        source_rows_valid,
        source_errors,
    ) = _validate_source_pack_sources(
        artifacts["source_pack"],
        theme_node_ids=theme_node_ids,
        expected_artifact_version=Path(artifact_paths["source_pack"]).stem,
    )
    errors.extend(source_errors)
    primary_sources = [
        row
        for row in accepted_sources.values()
        if row.get("source_type") in primary_source_types
    ]
    (
        accepted_source_backed_claims,
        valid_claim_ids,
        claim_rows_valid,
        claim_errors,
    ) = _validate_claims(
        artifacts["theme"],
        expected_theme_id=expected_theme_id,
        accepted_source_ids=set(accepted_sources),
        known_source_ids=known_source_ids,
        theme_node_ids=theme_node_ids,
    )
    errors.extend(claim_errors)
    reviewed_mappings, mapping_rows_valid, mapping_errors = _validate_mappings(
        artifacts["company_mapping"],
        theme_artifact=artifacts["theme"],
    )
    errors.extend(mapping_errors)
    (
        matrix_rows_valid,
        matrix_coverage,
        matrix_errors,
    ) = _validate_node_evidence_matrix(
        artifacts["node_evidence_matrix"],
        theme_node_ids=theme_node_ids,
        accepted_source_ids=set(accepted_sources),
        known_source_ids=known_source_ids,
        valid_claim_ids=valid_claim_ids,
        expected_artifact_version=Path(
            artifact_paths["node_evidence_matrix"]
        ).stem,
    )
    errors.extend(matrix_errors)
    readable_sections = {
        section["name"]: all(
            _requirement_is_non_empty(requirement, artifacts)
            for requirement in section["non_empty"]
        )
        for section in gates["required_readable_sections"]
    }
    artifact_checks = {
        f"{artifact_name}_readable": artifacts[artifact_name] is not None
        for artifact_name in ARTIFACT_KEYS
    }
    identity_checks = {
        f"{artifact_name}_theme_id": _artifact_theme_id(artifact_name, payload)
        == expected_theme_id
        for artifact_name, payload in artifacts.items()
    }
    checks = {
        **artifact_checks,
        **identity_checks,
        "source_rows_valid": source_rows_valid,
        "theme_nodes_valid": theme_nodes_valid,
        "claim_rows_valid": claim_rows_valid,
        "mapping_rows_valid": mapping_rows_valid,
        "node_evidence_matrix_rows_valid": matrix_rows_valid,
        "accepted_source_count": len(accepted_sources)
        >= gates["min_accepted_sources"],
        "primary_source_count": len(primary_sources) >= gates["min_primary_sources"],
        "claim_count": len(valid_claim_ids) >= gates["min_claims"],
        "reviewed_mapping_count": len(reviewed_mappings)
        >= gates["min_reviewed_mappings"],
        "required_sections_ready": all(readable_sections.values()),
    }
    if gates["require_node_evidence_matrix_coverage"]:
        checks["node_evidence_matrix_coverage"] = matrix_coverage
    return {
        "chain_id": chain_id,
        "theme_id": expected_theme_id,
        "wave": wave_name,
        "artifact_paths": artifact_paths,
        "counts": {
            "accepted_sources": len(accepted_sources),
            "primary_sources": len(primary_sources),
            "claims": len(valid_claim_ids),
            "accepted_source_backed_claims": len(accepted_source_backed_claims),
            "reviewed_mappings": len(reviewed_mappings),
        },
        "node_evidence_matrix_coverage": matrix_coverage,
        "readable_sections": readable_sections,
        "required_sections_ready": all(readable_sections.values()),
        "checks": checks,
        "errors": errors,
        "ready": all(checks.values()),
    }


def _validate_source_pack_sources(
    payload: dict[str, Any] | None,
    *,
    theme_node_ids: set[str],
    expected_artifact_version: str,
) -> tuple[dict[str, dict[str, Any]], set[str], bool, list[str]]:
    version_errors = _validate_artifact_version(
        payload,
        expected=expected_artifact_version,
        label="source pack",
    )
    if version_errors:
        return {}, set(), False, version_errors
    rows, errors = _object_rows(payload, "sources", "source pack sources")
    if errors:
        return {}, set(), False, errors
    try:
        source_by_id = validate_theme_evidence_sources(rows, theme_node_ids)
    except AiPowerEvidenceValidationError as exc:
        return {}, set(), False, [f"source pack validation failed [{exc.code}]: {exc}"]
    accepted = {
        source_id: row
        for source_id, row in source_by_id.items()
        if row.get("review_status") == "accepted"
    }
    return accepted, set(source_by_id), True, []


def _validate_theme_nodes(
    payload: dict[str, Any] | None,
    *,
    expected_theme_id: str,
) -> tuple[set[str], bool, list[str]]:
    rows, errors = _object_rows(payload, "nodes", "theme nodes")
    node_ids: set[str] = set()
    for index, row in enumerate(rows):
        label = f"theme node[{index}]"
        node_id = row.get("node_id")
        if not _is_non_empty_string(node_id):
            errors.append(f"{label} requires non-empty node_id")
            continue
        if node_id in node_ids:
            errors.append(f"{label} duplicate node_id: {node_id}")
            continue
        if row.get("theme_id") != expected_theme_id:
            errors.append(
                f"{label}.theme_id must equal {expected_theme_id}: {row.get('theme_id')}"
            )
            continue
        node_ids.add(node_id)
    if not node_ids:
        errors.append("theme nodes must contain at least one valid node")
    return node_ids, not errors, errors


def _validate_claims(
    payload: dict[str, Any] | None,
    *,
    expected_theme_id: str,
    accepted_source_ids: set[str],
    known_source_ids: set[str],
    theme_node_ids: set[str],
) -> tuple[dict[str, dict[str, Any]], set[str], bool, list[str]]:
    rows, errors = _object_rows(payload, "claims", "theme claims")
    valid_claims: dict[str, dict[str, Any]] = {}
    schema_valid_claims: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        label = f"claim[{index}]"
        missing_fields = sorted(CLAIM_FIELDS - set(row))
        row_errors = [f"{label}.{field} is required" for field in missing_fields]
        claim_id = row.get("claim_id")
        if not _is_non_empty_string(claim_id):
            row_errors.append(f"{label} requires non-empty claim_id")
            errors.extend(row_errors)
            continue
        if claim_id in seen_ids:
            errors.append(f"{label} duplicate claim_id: {claim_id}")
            valid_claims.pop(claim_id, None)
            schema_valid_claims.pop(claim_id, None)
            continue
        seen_ids.add(claim_id)
        if row.get("theme_id") != expected_theme_id:
            row_errors.append(
                f"{label}.theme_id must equal {expected_theme_id}: {row.get('theme_id')}"
            )
        source_id = row.get("source_id")
        if not _is_non_empty_string(source_id) or source_id not in known_source_ids:
            row_errors.append(
                f"{label}.source_id must reference a known source: {source_id}"
            )
        for field in ("claim_text", "claim_type"):
            if not _is_non_empty_string(row.get(field)):
                row_errors.append(f"{label}.{field} must be a non-empty string")
        if row.get("claim_type") not in CLAIM_TYPES:
            row_errors.append(f"{label}.claim_type is invalid: {row.get('claim_type')}")
        if row.get("evidence_status") not in EVIDENCE_STATUSES:
            row_errors.append(
                f"{label}.evidence_status is invalid: {row.get('evidence_status')}"
            )
        if row.get("platform_use_status") not in CLAIM_PLATFORM_USE_STATUSES:
            row_errors.append(
                f"{label}.platform_use_status is invalid: "
                f"{row.get('platform_use_status')}"
            )
        confidence = row.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0 <= float(confidence) <= 1
        ):
            row_errors.append(f"{label}.confidence must be a finite number from 0 to 1")
        supporting_source_ids = row.get("supporting_source_ids")
        if not _is_string_list(supporting_source_ids, allow_empty=True):
            row_errors.append(f"{label}.supporting_source_ids must be a string list")
            supporting_source_ids = []
        elif len(supporting_source_ids) != len(set(supporting_source_ids)):
            row_errors.append(f"{label}.supporting_source_ids contains duplicates")
        else:
            unknown_supporting_sources = set(supporting_source_ids) - known_source_ids
            if unknown_supporting_sources:
                row_errors.append(
                    f"{label}.supporting_source_ids references unknown sources: "
                    f"{sorted(unknown_supporting_sources)}"
                )
        affected_nodes = row.get("affected_theme_nodes")
        if not _is_string_list(affected_nodes, allow_empty=False):
            row_errors.append(f"{label}.affected_theme_nodes must be a non-empty string list")
        elif not set(affected_nodes) <= theme_node_ids:
            row_errors.append(
                f"{label}.affected_theme_nodes references nodes outside the theme: "
                f"{sorted(set(affected_nodes) - theme_node_ids)}"
            )
        if row_errors:
            errors.extend(row_errors)
            continue
        schema_valid_claims[claim_id] = row
        claim_source_ids = {source_id, *supporting_source_ids}
        if claim_source_ids & accepted_source_ids:
            valid_claims[claim_id] = row
        if (
            row.get("platform_use_status") == "reviewed"
            and not (claim_source_ids & accepted_source_ids)
        ):
            errors.append(f"{label} reviewed claim requires accepted source: {source_id}")
    return valid_claims, set(schema_valid_claims), not errors, errors


def _validate_mappings(
    payload: dict[str, Any] | None,
    *,
    theme_artifact: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], bool, list[str]]:
    if payload is None or theme_artifact is None:
        return [], False, ["company mapping or theme artifact is unavailable"]
    try:
        validate_theme_company_mapping_artifact(payload, theme_artifact)
    except ThemeCompanyMappingValidationError as exc:
        return [], False, [f"company mapping validation failed [{exc.code}]: {exc}"]

    source_by_id = {row["source_id"]: row for row in payload["sources"]}
    evidence_by_id = {row["evidence_id"]: row for row in payload["evidence_items"]}
    reviewed_mappings = []
    for mapping in payload["company_mappings"]:
        evidence = [
            {
                **evidence_by_id[evidence_id],
                "source": source_by_id[evidence_by_id[evidence_id]["source_id"]],
            }
            for evidence_id in mapping["evidence_ids"]
        ]
        if (
            mapping["review_status"] == "reviewed"
            and classify_beneficiary(mapping, evidence) != "concept_association"
        ):
            reviewed_mappings.append(mapping)
    return reviewed_mappings, True, []


def _validate_node_evidence_matrix(
    payload: dict[str, Any] | None,
    *,
    theme_node_ids: set[str],
    accepted_source_ids: set[str],
    known_source_ids: set[str],
    valid_claim_ids: set[str],
    expected_artifact_version: str,
) -> tuple[bool, bool, list[str]]:
    version_errors = _validate_artifact_version(
        payload,
        expected=expected_artifact_version,
        label="node evidence matrix",
    )
    if version_errors:
        return False, False, version_errors
    rows, errors = _object_rows(
        payload, "node_evidence_matrix", "node evidence matrix rows"
    )
    schema_errors = list(errors)
    seen_node_ids: set[str] = set()
    for index, row in enumerate(rows):
        label = f"node evidence matrix[{index}]"
        missing_fields = sorted(NODE_MATRIX_FIELDS - set(row))
        for field in missing_fields:
            schema_errors.append(f"{label}.{field} is required")
        node_id = row.get("node_id")
        if not _is_non_empty_string(node_id):
            schema_errors.append(f"{label} requires non-empty node_id")
            continue
        if node_id in seen_node_ids:
            schema_errors.append(f"{label} duplicate node_id: {node_id}")
            continue
        seen_node_ids.add(node_id)
        if node_id not in theme_node_ids:
            schema_errors.append(f"{label}.node_id is outside this theme: {node_id}")
        accepted_ids = row.get("accepted_source_ids")
        if not _is_string_list(accepted_ids, allow_empty=True):
            schema_errors.append(f"{label}.accepted_source_ids must be a string list")
            accepted_ids = []
        elif len(accepted_ids) != len(set(accepted_ids)):
            schema_errors.append(f"{label}.accepted_source_ids contains duplicates")
        unknown_sources = set(accepted_ids) - accepted_source_ids
        if unknown_sources:
            schema_errors.append(
                f"{label}.accepted_source_ids references non-accepted sources: "
                f"{sorted(unknown_sources)}"
            )
        pending_ids = row.get("pending_source_ids")
        if not _is_string_list(pending_ids, allow_empty=True):
            schema_errors.append(f"{label}.pending_source_ids must be a string list")
            pending_ids = []
        elif len(pending_ids) != len(set(pending_ids)):
            schema_errors.append(f"{label}.pending_source_ids contains duplicates")
        unknown_pending_sources = set(pending_ids) - known_source_ids
        if unknown_pending_sources:
            schema_errors.append(
                f"{label}.pending_source_ids references unknown sources: "
                f"{sorted(unknown_pending_sources)}"
            )
        supported_claim_ids = row.get("supported_claim_ids")
        if not _is_string_list(supported_claim_ids, allow_empty=True):
            schema_errors.append(f"{label}.supported_claim_ids must be a string list")
        else:
            unknown_claims = set(supported_claim_ids) - valid_claim_ids
            if unknown_claims:
                schema_errors.append(
                    f"{label}.supported_claim_ids references invalid claims: "
                    f"{sorted(unknown_claims)}"
                )
        for field in ("evidence_strength_before", "evidence_strength_after"):
            if not _is_valid_evidence_strength(row.get(field)):
                schema_errors.append(f"{label}.{field} must be integer 0-5")
        for field in (
            "value_capture_score_review_status",
            "bottleneck_score_review_status",
        ):
            if row.get(field) not in SCORE_REVIEW_STATUSES:
                schema_errors.append(f"{label}.{field} is invalid: {row.get(field)}")
        gap_status = row.get("evidence_gap_status")
        if gap_status not in MATRIX_COVERAGE_STATUSES:
            schema_errors.append(f"{label}.evidence_gap_status is invalid: {gap_status}")
        node_review_status = row.get("node_review_status")
        if node_review_status not in NODE_REVIEW_STATUSES:
            schema_errors.append(
                f"{label}.node_review_status is invalid: {node_review_status}"
            )
        value_bases = row.get("value_bases")
        if not _is_string_list(value_bases, allow_empty=True):
            schema_errors.append(f"{label}.value_bases must be a string list")
            value_bases = []
        invalid_value_bases = set(value_bases) - VALUE_BASES
        if invalid_value_bases:
            schema_errors.append(
                f"{label}.value_bases invalid: {sorted(invalid_value_bases)}"
            )
        for field in ("rationale", "next_evidence_needed"):
            if not _is_non_empty_string(row.get(field)):
                schema_errors.append(f"{label}.{field} must be a non-empty string")
        if not accepted_ids and gap_status not in MATRIX_EXPLICIT_GAP_STATUSES:
            schema_errors.append(
                f"{label} requires accepted sources or an explicit evidence-gap status"
            )
        strength_after = row.get("evidence_strength_after")
        if (
            node_review_status == "reviewed"
            and _is_valid_evidence_strength(strength_after)
            and (strength_after < 3 or not accepted_ids)
        ):
            schema_errors.append(
                f"{label} reviewed node requires strength >= 3 and accepted source"
            )
    coverage_valid = seen_node_ids == theme_node_ids
    coverage_errors: list[str] = []
    if not coverage_valid:
        coverage_errors.append(
            "node evidence matrix coverage mismatch: "
            f"missing={sorted(theme_node_ids - seen_node_ids)}, "
            f"extra={sorted(seen_node_ids - theme_node_ids)}"
        )
    all_errors = [*schema_errors, *coverage_errors]
    return not schema_errors, coverage_valid and not schema_errors, all_errors


def _object_rows(
    payload: dict[str, Any] | None,
    key: str,
    label: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if payload is None:
        return [], [f"{label} are unavailable"]
    value = payload.get(key)
    if not isinstance(value, list):
        return [], [f"{label} must be a list"]
    rows = []
    errors = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        rows.append(row)
    return rows, errors


def _validate_artifact_version(
    payload: dict[str, Any] | None,
    *,
    expected: str,
    label: str,
) -> list[str]:
    if payload is None:
        return [f"{label} artifact_version is unavailable"]
    actual = payload.get("artifact_version")
    if actual != expected:
        return [
            f"{label}.artifact_version must equal {expected}: {actual}"
        ]
    return []


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_valid_evidence_strength(value: Any) -> bool:
    return bool(
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= 5
    )


def _is_string_list(value: Any, *, allow_empty: bool) -> bool:
    return bool(
        isinstance(value, list)
        and (allow_empty or value)
        and all(_is_non_empty_string(item) for item in value)
    )


def _load_json_artifact(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"{path} does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"{path} is not readable JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{path} must contain a JSON object"
    return payload, None


def _artifact_theme_id(
    artifact_name: str,
    payload: dict[str, Any] | None,
) -> str | None:
    if payload is None:
        return None
    if artifact_name == "theme":
        theme = payload.get("theme")
        return theme.get("theme_id") if isinstance(theme, dict) else None
    value = payload.get("theme_id")
    return value if isinstance(value, str) else None


def _requirement_is_non_empty(
    requirement: str,
    artifacts: dict[str, dict[str, Any] | None],
) -> bool:
    artifact_name, _, field_path = requirement.partition(":")
    value: Any = artifacts.get(artifact_name)
    for key in field_path.split("."):
        if not isinstance(value, dict) or key not in value:
            return False
        value = value[key]
    if value is None or value is False:
        return False
    if isinstance(value, (str, list, dict, tuple, set)):
        return bool(value)
    return True


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Theme batch {report['batch_id']}: {report['completion_status']}",
        "",
        f"Ready themes: {report['ready_theme_count']}/{report['evaluated_theme_count']}",
        "",
    ]
    for wave_name, wave_result in report["wave_results"].items():
        status = "ready" if wave_result["ready"] else "not_ready"
        lines.extend(
            [
                f"## {wave_name}: {status}",
                "",
                f"Ready themes: {wave_result['ready_theme_count']}/{wave_result['theme_count']}",
                "",
            ]
        )
        for row in report["theme_results"]:
            if row["wave"] != wave_name:
                continue
            counts = row["counts"]
            lines.append(
                f"- {row['chain_id']}: {'ready' if row['ready'] else 'not_ready'} "
                f"({counts['accepted_sources']} accepted sources, "
                f"{counts['primary_sources']} primary sources, {counts['claims']} claims, "
                f"{counts['reviewed_mappings']} reviewed mappings)"
            )
            if not row["ready"]:
                failed_checks = [
                    name for name, passed in row["checks"].items() if not passed
                ]
                lines.append(f"  - Failed checks: {', '.join(failed_checks)}")
                if row["errors"]:
                    lines.append(f"  - Artifact errors: {'; '.join(row['errors'])}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--wave")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        report = build_theme_batch_report(args.manifest, wave=args.wave)
    except (FileNotFoundError, ValueError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.format == "markdown":
        print(_render_markdown(report))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["completion_status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
