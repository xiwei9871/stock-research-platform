from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


SCHEMA_FILES = {
    "research_project_identity_v2_1": "research_project_identity_v2_1.schema.json",
    "industry_research_version_v2_1": "industry_research_version_v2_1.schema.json",
    "search_plan_v2_1": "search_plan_v2_1.schema.json",
    "evidence_artifact_v2_1": "evidence_artifact_v2_1.schema.json",
    "normalized_document_v2_1": "normalized_document_v2_1.schema.json",
    "industry_evidence_assessment_v2_1": "industry_evidence_assessment_v2_1.schema.json",
    "research_project_index_v2_1": "research_project_index_v2_1.schema.json",
}


def validate_v2_1_schema_payload(
    schema_name: str,
    payload: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
) -> None:
    try:
        schema_file = SCHEMA_FILES[schema_name]
    except KeyError as exc:
        raise ResearchProjectV2Error(
            f"Unknown layered research project schema: {schema_name}",
            code="RESEARCH_PROJECT_V2_1_SCHEMA_NOT_FOUND",
            details={"schema": schema_name},
        ) from exc

    effective_layout = LayeredResearchLayout.default() if layout is None else layout
    with (effective_layout.schema_dir / schema_file).open(
        encoding="utf-8"
    ) as handle:
        schema = json.load(handle)
    with (effective_layout.schema_dir / "definitions_v2_1.schema.json").open(
        encoding="utf-8"
    ) as handle:
        definitions = json.load(handle)

    resolver = RefResolver.from_schema(
        schema,
        store={"definitions_v2_1.schema.json": definitions},
    )
    validator = Draft202012Validator(
        schema,
        resolver=resolver,
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            tuple(str(part) for part in error.absolute_schema_path),
            str(error.validator),
            error.message,
        ),
    )
    if not errors:
        return

    first_error = errors[0]
    raise ResearchProjectV2Error(
        first_error.message,
        code="RESEARCH_PROJECT_V2_1_SCHEMA_INVALID",
        details={
            "schema": schema_name,
            "path": list(first_error.absolute_path),
        },
    )
