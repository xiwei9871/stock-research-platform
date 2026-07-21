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
    "industry_research_version_v2_2": "industry_research_version_v2_2.schema.json",
    "industry_evidence_assessment_v2_2": "industry_evidence_assessment_v2_2.schema.json",
    "acquisition_attempt_v2_3": "acquisition_attempt_v2_3.schema.json",
    "evidence_artifact_v2_3": "evidence_artifact_v2_3.schema.json",
    "manual_import_request_v2_3": "manual_import_request_v2_3.schema.json",
    "acquisition_checkpoint_v2_3": "acquisition_checkpoint_v2_3.schema.json",
    "provider_diagnostic_v2_3": "provider_diagnostic_v2_3.schema.json",
    "stage_a_scope_correction_v2_4": "stage_a_scope_correction_v2_4.schema.json",
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
    definitions_v2_2_path = effective_layout.schema_dir / "definitions_v2_2.schema.json"
    definitions_v2_2 = None
    if definitions_v2_2_path.exists():
        with definitions_v2_2_path.open(encoding="utf-8") as handle:
            definitions_v2_2 = json.load(handle)

    store = {"definitions_v2_1.schema.json": definitions}
    if definitions_v2_2 is not None:
        store["definitions_v2_2.schema.json"] = definitions_v2_2
    acquisition_definitions_path = (
        effective_layout.schema_dir / "definitions_acquisition_v2_3.schema.json"
    )
    if acquisition_definitions_path.exists():
        with acquisition_definitions_path.open(encoding="utf-8") as handle:
            store["definitions_acquisition_v2_3.schema.json"] = json.load(handle)
    resolver = RefResolver.from_schema(
        schema,
        store=store,
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
