from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import (
    read_layered_bytes,
    read_layered_canonical_json,
)
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


CONFIDENCE_ORDER = {"very_low": 0, "low": 1, "medium": 2, "high": 3}


def _error(message: str, *, code: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(message, code=code, details=details)


def load_cognition_package(
    path: Path,
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    effective = LayeredResearchLayout.default() if layout is None else layout
    try:
        relative = path.relative_to(effective.root)
    except ValueError as exc:
        raise _error(
            "Cognition package is outside the managed root",
            code="RESEARCH_PROJECT_V2_1_COGNITION_INPUT_MISSING",
            path=str(path),
        ) from exc
    payload = read_layered_canonical_json(relative, layout=effective)
    validate_v2_1_schema_payload(
        "industry_cognition_baseline_v2_5", payload, layout=effective
    )
    expected = content_sha256(payload, excluded_paths={("content_hash",)})
    if payload["content_hash"] != expected:
        raise _error(
            "Cognition package content hash mismatch",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            field="content_hash",
        )
    return payload


def validate_baseline_bindings(
    package: dict[str, Any],
    *,
    layout: LayeredResearchLayout,
) -> None:
    bindings = package.get("baseline_bindings")
    if not isinstance(bindings, dict):
        raise _error(
            "Cognition baseline bindings are missing",
            code="RESEARCH_PROJECT_V2_1_COGNITION_INPUT_MISSING",
            field="baseline_bindings",
        )
    checkpoint_ref = bindings.get("acquisition_checkpoint")
    scope_ref = bindings.get("scope_correction")
    if not isinstance(checkpoint_ref, dict) or not isinstance(scope_ref, dict):
        raise _error(
            "Cognition upstream binding is missing",
            code="RESEARCH_PROJECT_V2_1_COGNITION_INPUT_MISSING",
            field="baseline_bindings",
        )
    checkpoint_id = checkpoint_ref.get("checkpoint_id")
    checkpoint = read_layered_canonical_json(
        f"acquisition/checkpoints/{checkpoint_id}.json", layout=layout
    ).get("acquisition_checkpoint")
    if not isinstance(checkpoint, dict) or checkpoint.get("content_hash") != checkpoint_ref.get(
        "content_hash"
    ):
        raise _error(
            "Acquisition checkpoint binding drifted",
            code="RESEARCH_PROJECT_V2_1_COGNITION_UPSTREAM_DRIFT",
            field="baseline_bindings.acquisition_checkpoint",
        )
    scope_path = scope_ref.get("relative_path")
    scope = read_layered_canonical_json(str(scope_path), layout=layout)
    if scope.get("content_hash") != scope_ref.get("content_hash"):
        raise _error(
            "Scope correction binding drifted",
            code="RESEARCH_PROJECT_V2_1_COGNITION_UPSTREAM_DRIFT",
            field="baseline_bindings.scope_correction",
        )


def validate_evidence_locator(
    locator: dict[str, Any],
    *,
    layout: LayeredResearchLayout,
) -> dict[str, Any]:
    copied = deepcopy(locator)
    artifact_id = copied.get("artifact_id")
    document_id = copied.get("normalized_document_id")
    section_index = copied.get("section_index")
    section_hash = copied.get("section_hash")
    if not isinstance(artifact_id, str) or not isinstance(document_id, str):
        raise _error(
            "Evidence locator identity is invalid",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="artifact_id",
        )
    metadata_wrapper = read_layered_canonical_json(
        f"evidence/metadata_v2_3/{artifact_id}.json", layout=layout
    )
    artifact = metadata_wrapper.get("evidence_artifact")
    if not isinstance(artifact, dict) or artifact.get("evidence_artifact_id") != artifact_id:
        raise _error(
            "Evidence artifact binding is invalid",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="artifact_id",
        )
    raw_path = artifact.get("raw_artifact_path")
    raw = read_layered_bytes(str(raw_path), layout=layout, max_bytes=32 * 1024 * 1024)
    if sha256(raw).hexdigest() != artifact.get("content_hash"):
        raise _error(
            "Raw evidence content hash drifted",
            code="RESEARCH_PROJECT_V2_1_COGNITION_UPSTREAM_DRIFT",
            field="raw_artifact_path",
        )
    document_wrapper = read_layered_canonical_json(
        f"evidence/normalized/{document_id}.json", layout=layout
    )
    document = document_wrapper.get("normalized_document")
    if (
        not isinstance(document, dict)
        or document.get("document_id") != document_id
        or document.get("artifact_id") != artifact_id
    ):
        raise _error(
            "Normalized evidence does not trace to the raw artifact",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="normalized_document_id",
        )
    sections = document.get("sections")
    if not isinstance(section_index, int) or not isinstance(sections, list):
        raise _error(
            "Evidence section index is invalid",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="section_index",
        )
    try:
        section = sections[section_index]
    except IndexError as exc:
        raise _error(
            "Evidence section is missing",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="section_index",
        ) from exc
    if not isinstance(section, dict) or section.get("section_hash") != section_hash:
        raise _error(
            "Evidence section hash drifted",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="section_hash",
        )
    copied["section_id"] = section.get("section_id")
    copied["section_text"] = section.get("text")
    return copied


def canonical_package_bytes(package: dict[str, Any]) -> bytes:
    return canonical_bytes(package)
