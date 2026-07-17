from __future__ import annotations

import argparse
import json
from typing import Any

from stock_research.research_project_v2.diff import diff_versions
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.gates import evaluate_gate
from stock_research.research_project_v2.layout import ResearchProjectLayout
from stock_research.research_project_v2.loader import (
    list_project_slugs,
    list_versions,
    load_project,
    load_version,
)
from stock_research.research_project_v2.references import audit_references
from stock_research.research_project_v2.semantic import validate_version_semantics
from stock_research.research_project_v2.summary import summarize_version


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-project-v2")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List current research projects.")

    show = subparsers.add_parser("show", help="Show a complete immutable version.")
    show.add_argument("--project", required=True)
    show.add_argument("--version")

    validate = subparsers.add_parser("validate", help="Validate one or all versions.")
    selection = validate.add_mutually_exclusive_group()
    selection.add_argument("--project")
    selection.add_argument("--all", action="store_true")
    validate.add_argument("--version")

    summary = subparsers.add_parser("summary", help="Summarize current versions.")
    summary.add_argument("--project")
    summary.add_argument("--version")

    audit = subparsers.add_parser("audit-references", help="Audit external references.")
    audit.add_argument("--project", required=True)
    audit.add_argument("--version")

    diff = subparsers.add_parser("diff", help="Diff a direct parent-child pair.")
    diff.add_argument("--project", required=True)
    diff.add_argument("--from", dest="from_version", required=True)
    diff.add_argument("--to", dest="to_version", required=True)

    gate = subparsers.add_parser("gate", help="Evaluate a research gate.")
    gate.add_argument("--project", required=True)
    gate.add_argument("--version", required=True)
    gate.add_argument("--gate", choices=("design", "evidence", "publication"), required=True)
    return parser


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


def _error_payload(error: ResearchProjectV2Error) -> dict[str, object]:
    return {
        "error": {
            "code": error.code,
            "message": str(error),
            "details": error.details,
        }
    }


def _exit_for_domain_error(error: ResearchProjectV2Error) -> int:
    code = error.code
    if "IMMUTABILITY" in code or "HASH" in code and "REFERENCE" not in code:
        return 5
    if code in {"RESEARCH_PROJECT_NOT_FOUND", "RESEARCH_PROJECT_VERSION_NOT_FOUND"}:
        return 6
    if code.startswith("RESEARCH_PROJECT_DIFF_"):
        return 7
    if code.startswith("RESEARCH_PROJECT_REFERENCE_"):
        return 3
    if code.startswith("RESEARCH_PROJECT_GATE_"):
        return 4
    return 2


def _identity_summary(
    identity: dict[str, Any], version: dict[str, Any]
) -> dict[str, Any]:
    return {
        "project_id": identity["project_id"],
        "project_slug": identity["project_slug"],
        "title": identity["title"],
        "current_version": identity["current_version"],
        "latest_reviewed_version": identity["latest_reviewed_version"],
        "latest_published_version": identity["latest_published_version"],
        **summarize_version(version),
    }


def _list(layout: ResearchProjectLayout) -> dict[str, object]:
    projects = []
    for slug in list_project_slugs(layout=layout):
        identity = load_project(slug, layout=layout)
        pointer = identity["current_version"]
        semantic_version = pointer.rsplit(":", 1)[-1]
        version = load_version(slug, semantic_version, layout=layout)
        projects.append(_identity_summary(identity, version))
    return {"projects": projects}


def _validate(args: argparse.Namespace, layout: ResearchProjectLayout) -> dict[str, object]:
    if args.version and not args.project:
        raise ResearchProjectV2Error(
            "--version requires --project",
            code="RESEARCH_PROJECT_SCHEMA_INVALID",
            details={"argument": "--version"},
        )
    targets: list[tuple[str, str | None]] = []
    if args.project:
        targets.append((args.project, args.version))
    else:
        project_slugs = list_project_slugs(layout=layout)
        if not project_slugs:
            raise ResearchProjectV2Error(
                "Research projects not found",
                code="RESEARCH_PROJECT_NOT_FOUND",
                details={"artifact": "projects"},
            )
        for slug in project_slugs:
            versions = list_versions(slug, layout=layout)
            if not versions:
                raise ResearchProjectV2Error(
                    f"Research project version not found: {slug}",
                    code="RESEARCH_PROJECT_VERSION_NOT_FOUND",
                    details={"project": slug, "version": None},
                )
            targets.extend((slug, version) for version in versions)

    if not targets:
        raise ResearchProjectV2Error(
            "Research projects not found",
            code="RESEARCH_PROJECT_NOT_FOUND",
            details={"artifact": "projects"},
        )

    validated = []
    for slug, version_number in targets:
        version = load_version(slug, version_number, layout=layout)
        validate_version_semantics(version)
        validated.append(summarize_version(version))
    return {"status": "pass", "validated": validated}


def _summary(args: argparse.Namespace, layout: ResearchProjectLayout) -> object:
    if args.version and not args.project:
        raise ResearchProjectV2Error(
            "--version requires --project",
            code="RESEARCH_PROJECT_SCHEMA_INVALID",
            details={"argument": "--version"},
        )
    if args.project:
        return summarize_version(load_version(args.project, args.version, layout=layout))
    return {
        "summaries": [
            summarize_version(load_version(slug, layout=layout))
            for slug in list_project_slugs(layout=layout)
        ]
    }


def _execute(args: argparse.Namespace, layout: ResearchProjectLayout) -> tuple[object, int]:
    if args.command == "list":
        return _list(layout), 0
    if args.command == "show":
        return load_version(args.project, args.version, layout=layout), 0
    if args.command == "validate":
        return _validate(args, layout), 0
    if args.command == "summary":
        return _summary(args, layout), 0
    if args.command == "audit-references":
        version = load_version(args.project, args.version, layout=layout)
        result = {
            "project_id": version["project_id"],
            "version_id": version["version_id"],
            "semantic_version": version["semantic_version"],
            **audit_references(version),
        }
        return result, 3 if result["status"] == "fail" else 0
    if args.command == "diff":
        before = load_version(args.project, args.from_version, layout=layout)
        after = load_version(args.project, args.to_version, layout=layout)
        return diff_versions(before, after), 0
    version = load_version(args.project, args.version, layout=layout)
    result = {
        "project_id": version["project_id"],
        "version_id": version["version_id"],
        "semantic_version": version["semantic_version"],
        **evaluate_gate(version, args.gate).as_dict(),
    }
    return result, 4 if result["status"] == "fail" else 0


def cli(
    argv: list[str] | None = None,
    *,
    layout: ResearchProjectLayout | None = None,
) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    selected_layout = ResearchProjectLayout.default() if layout is None else layout
    try:
        payload, exit_code = _execute(args, selected_layout)
    except ResearchProjectV2Error as error:
        _print_json(_error_payload(error))
        return _exit_for_domain_error(error)
    except Exception as error:
        _print_json(
            {
                "error": {
                    "code": "RESEARCH_PROJECT_RUNTIME_ERROR",
                    "message": str(error),
                    "details": {},
                }
            }
        )
        return 10
    _print_json(payload)
    return exit_code


def run_research_project_v2_cli(argv: list[str] | None = None) -> int:
    return cli(argv)


__all__ = ["cli", "run_research_project_v2_cli"]
