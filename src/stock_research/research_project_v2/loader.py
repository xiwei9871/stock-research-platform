import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.layout import ResearchProjectLayout


SCHEMA_FILES = {
    "identity": "research_project_identity_v2.schema.json",
    "version": "research_version_v2.schema.json",
    "event": "research_event_v2.schema.json",
    "index": "research_project_index_v2.schema.json",
}


@lru_cache(maxsize=None)
def _schema_bundle(schema_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        schema_file = SCHEMA_FILES[schema_name]
    except KeyError as exc:
        raise ResearchProjectV2Error(
            f"Unknown research project schema: {schema_name}",
            code="RESEARCH_PROJECT_SCHEMA_NOT_FOUND",
            details={"schema": schema_name},
        ) from exc

    schema_dir = ResearchProjectLayout.default().schema_dir
    with (schema_dir / schema_file).open(encoding="utf-8") as handle:
        schema = json.load(handle)
    with (schema_dir / "definitions_v2.schema.json").open(encoding="utf-8") as handle:
        definitions = json.load(handle)
    return schema, definitions


def validate_schema_payload(schema_name: str, payload: dict[str, Any]) -> None:
    schema, definitions = _schema_bundle(schema_name)
    resolver = RefResolver.from_schema(
        schema,
        store={"definitions_v2.schema.json": definitions},
    )
    validator = Draft202012Validator(
        schema,
        resolver=resolver,
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return

    first_error = errors[0]
    path = ".".join(str(part) for part in first_error.absolute_path)
    raise ResearchProjectV2Error(
        f"Research project payload does not match the {schema_name} schema",
        code="RESEARCH_PROJECT_SCHEMA_INVALID",
        details={"path": path, "schema": schema_name},
    )
