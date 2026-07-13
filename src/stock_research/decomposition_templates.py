from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from stock_research.theme_decomposition import (
    CLAIM_TYPES,
    CREATED_FROM,
    NODE_TYPES,
    SOURCE_REVIEW_STATUSES,
    THEME_STATUSES,
    THEME_TYPES,
    VALUE_BASES,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DECOMPOSITION_TEMPLATE_DIR = (
    REPOSITORY_ROOT / "artifacts" / "theme_decomposition" / "decomposition_templates"
)
TEMPLATE_ARTIFACT_VERSION = "decomposition_template_v1"
THEME_OUTPUT_SCHEMA = "theme_decomposition_v1_5"

TEMPLATE_FAMILIES = {
    "system_bottleneck",
    "head_to_toe",
    "manufacturing_process",
}
RELIABILITY_LEVELS = {"S0", "S1", "S2", "S3", "S4"}

TEMPLATE_FIELDS = {
    "template_id",
    "template_name",
    "template_family",
    "description",
    "compatible_theme_types",
    "steps",
    "required_dimensions",
    "optional_dimensions",
    "node_archetypes",
    "claim_types",
    "value_bases",
    "source_requirements",
    "initialization_defaults",
    "output_schema",
    "example_theme_ids",
}
STEP_FIELDS = {
    "step_id",
    "order",
    "title",
    "purpose",
    "required_inputs",
    "output_dimensions",
    "quality_gates",
}
NODE_ARCHETYPE_FIELDS = {
    "archetype_id",
    "parent_archetype_id",
    "label",
    "purpose",
    "allowed_node_types",
    "required_metrics",
}
SOURCE_REQUIREMENT_FIELDS = {
    "use_case",
    "minimum_reliability_level",
    "allowed_review_statuses",
}
INITIALIZATION_DEFAULT_FIELDS = {"status", "created_from"}


class DecompositionTemplateValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


def load_decomposition_template_library(
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir is not None else DECOMPOSITION_TEMPLATE_DIR
    if not root.exists():
        raise DecompositionTemplateValidationError(
            f"template directory not found: {root}",
            code="TEMPLATE_DIRECTORY_NOT_FOUND",
        )
    artifacts = [_load_json(path) for path in sorted(root.glob("*.json"))]
    if not artifacts:
        raise DecompositionTemplateValidationError(
            f"no decomposition templates found in {root}",
            code="NO_TEMPLATES_FOUND",
        )
    templates: list[dict[str, Any]] = []
    seen_template_ids: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if artifact.get("artifact_version") != TEMPLATE_ARTIFACT_VERSION:
            raise DecompositionTemplateValidationError(
                f"artifacts[{index}].artifact_version must be {TEMPLATE_ARTIFACT_VERSION}",
                code="UNSUPPORTED_TEMPLATE_ARTIFACT_VERSION",
            )
        template = artifact.get("template")
        if not isinstance(template, dict):
            raise DecompositionTemplateValidationError(
                f"artifacts[{index}].template must be object",
                code="INVALID_TEMPLATE_ROOT",
            )
        _validate_template(template, index=index)
        template_id = template["template_id"]
        if template_id in seen_template_ids:
            raise DecompositionTemplateValidationError(
                f"template_id duplicated: {template_id}",
                code="DUPLICATE_TEMPLATE_ID",
            )
        seen_template_ids.add(template_id)
        templates.append(template)
    return {
        "artifact_dir": str(root),
        "artifact_version": TEMPLATE_ARTIFACT_VERSION,
        "templates": templates,
    }


def load_decomposition_template(
    template_id: str,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    library = load_decomposition_template_library(artifact_dir)
    for template in library["templates"]:
        if template["template_id"] == template_id:
            return template
    raise DecompositionTemplateValidationError(
        f"template_id not found: {template_id}",
        code="TEMPLATE_NOT_FOUND",
    )


def summarize_decomposition_template_library(library: dict[str, Any]) -> dict[str, Any]:
    templates = library["templates"]
    by_family: dict[str, list[str]] = defaultdict(list)
    for template in templates:
        by_family[template["template_family"]].append(template["template_id"])
    return {
        "template_count": len(templates),
        "step_count": sum(len(template["steps"]) for template in templates),
        "node_archetype_count": sum(
            len(template["node_archetypes"]) for template in templates
        ),
        "example_theme_count": sum(
            len(template["example_theme_ids"]) for template in templates
        ),
        "templates_by_family": {
            family: sorted(template_ids)
            for family, template_ids in sorted(by_family.items())
        },
    }


def initialize_theme_from_template(
    *,
    template_id: str,
    theme_id: str,
    theme_name: str,
    theme_type: str,
    last_updated: str,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    template = load_decomposition_template(template_id, artifact_dir)
    if theme_type not in template["compatible_theme_types"]:
        raise DecompositionTemplateValidationError(
            f"template {template_id} is not compatible with theme_type {theme_type}",
            code="INCOMPATIBLE_THEME_TYPE",
        )
    for field, value in (
        ("theme_id", theme_id),
        ("theme_name", theme_name),
        ("last_updated", last_updated),
    ):
        if not str(value).strip():
            raise DecompositionTemplateValidationError(
                f"{field} is required",
                code="MISSING_INITIALIZATION_FIELD",
            )
    defaults = template["initialization_defaults"]
    compact_template = {
        "template_id": template["template_id"],
        "theme_type": theme_type,
        "steps": [
            f"{step['title']}: {step['purpose']}"
            for step in sorted(template["steps"], key=lambda row: row["order"])
        ],
        "required_dimensions": list(template["required_dimensions"]),
        "optional_dimensions": list(template["optional_dimensions"]),
        "output_schema": template["output_schema"],
    }
    return {
        "artifact_version": THEME_OUTPUT_SCHEMA,
        "theme": {
            "theme_id": theme_id,
            "theme_name": theme_name,
            "theme_type": theme_type,
            "summary": f"Initialized from decomposition template {template_id}.",
            "status": defaults["status"],
            "created_from": defaults["created_from"],
            "last_updated": last_updated,
        },
        "evidence_policy": {
            "accepted_source_ids": [],
            "needs_full_text_source_ids": [],
            "lead_only_source_ids": [],
            "rejected_source_ids": [],
            "oral_claim_source_ids": [],
            "not_adopted_source_ids": [],
            "policy_notes": "Initialized read-only research draft. Review gates apply before any claim or node is promoted.",
        },
        "sources": [],
        "claims": [],
        "nodes": [],
        "value_capture_assessments": [],
        "decomposition_templates": [compact_template],
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="decomposition-templates")
    parser.add_argument("--artifact-dir", default=str(DECOMPOSITION_TEMPLATE_DIR))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("summary")
    show = subparsers.add_parser("show")
    show.add_argument("--template", required=True)
    initialize = subparsers.add_parser("initialize")
    initialize.add_argument("--template", required=True)
    initialize.add_argument("--theme-id", required=True)
    initialize.add_argument("--theme-name", required=True)
    initialize.add_argument("--theme-type", required=True)
    initialize.add_argument("--last-updated", required=True)
    initialize.add_argument("--output")
    args = parser.parse_args(argv)

    try:
        if args.command in {"validate", "summary"}:
            library = load_decomposition_template_library(args.artifact_dir)
            summary = summarize_decomposition_template_library(library)
            payload = {"status": "ok", **summary} if args.command == "validate" else summary
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "show":
            template = load_decomposition_template(args.template, args.artifact_dir)
            print(json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "initialize":
            artifact = initialize_theme_from_template(
                template_id=args.template,
                theme_id=args.theme_id,
                theme_name=args.theme_name,
                theme_type=args.theme_type,
                last_updated=args.last_updated,
                artifact_dir=args.artifact_dir,
            )
            rendered = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
            if args.output:
                output_path = Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(f"{rendered}\n", encoding="utf-8")
                print(
                    json.dumps(
                        {"status": "ok", "output": str(output_path)},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            else:
                print(rendered)
            return 0
    except DecompositionTemplateValidationError as exc:
        print(
            json.dumps(
                {"status": "error", "error_code": exc.code, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    raise AssertionError(f"unhandled command: {args.command}")


def main() -> None:
    raise SystemExit(cli())


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise DecompositionTemplateValidationError(
            f"{path.name}: root must be object",
            code="INVALID_ARTIFACT_ROOT",
        )
    return payload


def _validate_template(template: dict[str, Any], *, index: int) -> None:
    path = f"templates[{index}]"
    _require_fields(template, TEMPLATE_FIELDS, path)
    _check_enum(template, "template_family", TEMPLATE_FAMILIES, path)
    if template["output_schema"] != THEME_OUTPUT_SCHEMA:
        raise DecompositionTemplateValidationError(
            f"{path}.output_schema must be {THEME_OUTPUT_SCHEMA}",
            code="INVALID_OUTPUT_SCHEMA",
        )
    compatible_theme_types = template["compatible_theme_types"]
    if not compatible_theme_types:
        raise DecompositionTemplateValidationError(
            f"{path}.compatible_theme_types must not be empty",
            code="MISSING_COMPATIBLE_THEME_TYPE",
        )
    for theme_type in compatible_theme_types:
        if theme_type not in THEME_TYPES:
            raise DecompositionTemplateValidationError(
                f"{path}.compatible_theme_types invalid: {theme_type}",
                code="INVALID_THEME_TYPE",
            )
    _validate_steps(template["steps"], path)
    _validate_node_archetypes(template["node_archetypes"], path)
    for claim_type in template["claim_types"]:
        if claim_type not in CLAIM_TYPES:
            raise DecompositionTemplateValidationError(
                f"{path}.claim_types invalid: {claim_type}",
                code="INVALID_CLAIM_TYPE",
            )
    for value_basis in template["value_bases"]:
        if value_basis not in VALUE_BASES:
            raise DecompositionTemplateValidationError(
                f"{path}.value_bases invalid: {value_basis}",
                code="INVALID_VALUE_BASIS",
            )
    _validate_source_requirements(template["source_requirements"], path)
    defaults = template["initialization_defaults"]
    _require_fields(defaults, INITIALIZATION_DEFAULT_FIELDS, f"{path}.initialization_defaults")
    _check_enum(defaults, "status", THEME_STATUSES, f"{path}.initialization_defaults")
    _check_enum(defaults, "created_from", CREATED_FROM, f"{path}.initialization_defaults")
    for field in ("required_dimensions", "optional_dimensions"):
        values = template[field]
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise DecompositionTemplateValidationError(
                f"{path}.{field} must contain non-empty strings",
                code="INVALID_DIMENSIONS",
            )


def _validate_steps(steps: list[dict[str, Any]], path: str) -> None:
    if not steps:
        raise DecompositionTemplateValidationError(
            f"{path}.steps must not be empty",
            code="MISSING_TEMPLATE_STEPS",
        )
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for index, step in enumerate(steps):
        step_path = f"{path}.steps[{index}]"
        _require_fields(step, STEP_FIELDS, step_path)
        step_id = str(step["step_id"]).strip()
        if not step_id or step_id in seen_ids:
            raise DecompositionTemplateValidationError(
                f"{step_path}.step_id missing or duplicated",
                code="DUPLICATE_STEP_ID",
            )
        seen_ids.add(step_id)
        order = step["order"]
        if not isinstance(order, int) or order < 1:
            raise DecompositionTemplateValidationError(
                f"{step_path}.order must be positive integer",
                code="INVALID_STEP_ORDER",
            )
        if order in seen_orders:
            raise DecompositionTemplateValidationError(
                f"{step_path}.order duplicated: {order}",
                code="DUPLICATE_STEP_ORDER",
            )
        seen_orders.add(order)
        if not step["quality_gates"]:
            raise DecompositionTemplateValidationError(
                f"{step_path}.quality_gates must not be empty",
                code="STEP_REQUIRES_QUALITY_GATE",
            )
        for list_field in ("required_inputs", "output_dimensions", "quality_gates"):
            if not isinstance(step[list_field], list) or not all(
                isinstance(value, str) and value.strip() for value in step[list_field]
            ):
                raise DecompositionTemplateValidationError(
                    f"{step_path}.{list_field} must contain non-empty strings",
                    code="INVALID_STEP_LIST",
                )
    if seen_orders != set(range(1, len(steps) + 1)):
        raise DecompositionTemplateValidationError(
            f"{path}.steps order must be contiguous from 1",
            code="NON_CONTIGUOUS_STEP_ORDER",
        )


def _validate_node_archetypes(archetypes: list[dict[str, Any]], path: str) -> None:
    if not archetypes:
        raise DecompositionTemplateValidationError(
            f"{path}.node_archetypes must not be empty",
            code="MISSING_NODE_ARCHETYPES",
        )
    archetype_ids: set[str] = set()
    for index, archetype in enumerate(archetypes):
        archetype_path = f"{path}.node_archetypes[{index}]"
        _require_fields(archetype, NODE_ARCHETYPE_FIELDS, archetype_path)
        archetype_id = str(archetype["archetype_id"]).strip()
        if not archetype_id or archetype_id in archetype_ids:
            raise DecompositionTemplateValidationError(
                f"{archetype_path}.archetype_id missing or duplicated",
                code="DUPLICATE_NODE_ARCHETYPE_ID",
            )
        archetype_ids.add(archetype_id)
        allowed_node_types = archetype["allowed_node_types"]
        if not allowed_node_types:
            raise DecompositionTemplateValidationError(
                f"{archetype_path}.allowed_node_types must not be empty",
                code="MISSING_NODE_TYPE",
            )
        for node_type in allowed_node_types:
            if node_type not in NODE_TYPES:
                raise DecompositionTemplateValidationError(
                    f"{archetype_path}.allowed_node_types invalid: {node_type}",
                    code="INVALID_NODE_TYPE",
                )
    for index, archetype in enumerate(archetypes):
        parent_id = str(archetype["parent_archetype_id"] or "").strip()
        if parent_id and parent_id not in archetype_ids:
            raise DecompositionTemplateValidationError(
                f"{path}.node_archetypes[{index}].parent_archetype_id missing: {parent_id}",
                code="ORPHAN_NODE_ARCHETYPE",
            )


def _validate_source_requirements(
    requirements: list[dict[str, Any]], path: str
) -> None:
    if not requirements:
        raise DecompositionTemplateValidationError(
            f"{path}.source_requirements must not be empty",
            code="MISSING_SOURCE_REQUIREMENTS",
        )
    for index, requirement in enumerate(requirements):
        requirement_path = f"{path}.source_requirements[{index}]"
        _require_fields(requirement, SOURCE_REQUIREMENT_FIELDS, requirement_path)
        if requirement["minimum_reliability_level"] not in RELIABILITY_LEVELS:
            raise DecompositionTemplateValidationError(
                f"{requirement_path}.minimum_reliability_level invalid",
                code="INVALID_RELIABILITY_LEVEL",
            )
        if not requirement["allowed_review_statuses"]:
            raise DecompositionTemplateValidationError(
                f"{requirement_path}.allowed_review_statuses must not be empty",
                code="MISSING_SOURCE_REVIEW_STATUS",
            )
        for status in requirement["allowed_review_statuses"]:
            if status not in SOURCE_REVIEW_STATUSES:
                raise DecompositionTemplateValidationError(
                    f"{requirement_path}.allowed_review_statuses invalid: {status}",
                    code="INVALID_SOURCE_REVIEW_STATUS",
                )


def _require_fields(row: dict[str, Any], fields: set[str], path: str) -> None:
    for field in sorted(fields):
        if field not in row:
            raise DecompositionTemplateValidationError(
                f"{path}.{field} is required",
                code="MISSING_REQUIRED_FIELD",
            )


def _check_enum(
    row: dict[str, Any], field: str, allowed: set[str], path: str
) -> None:
    value = row.get(field)
    if value not in allowed:
        raise DecompositionTemplateValidationError(
            f"{path}.{field} invalid: {value}",
            code="INVALID_ENUM_VALUE",
        )


if __name__ == "__main__":
    main()
