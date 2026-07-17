from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.diff import diff_versions
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.gates import evaluate_gate
from stock_research.research_project_v2.layout import ResearchProjectLayout
from stock_research.research_project_v2.loader import (
    list_project_slugs,
    list_versions,
    load_project,
    load_version,
    validate_schema_payload,
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

    rebuild = subparsers.add_parser(
        "rebuild-index",
        help="Maintainer: rebuild manifests and the deterministic project index.",
    )
    rebuild.add_argument(
        "--write",
        action="store_true",
        help="Maintainer: apply planned version hashes, manifest appends, and index.",
    )
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


def _semver_key(version: str) -> tuple[int, int, int]:
    return tuple(map(int, version.split(".")))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _manifest_rows(path: Path, project_slug: str) -> tuple[bytes, list[dict[str, Any]]]:
    prefix = path.read_bytes() if path.is_file() else b""
    rows: list[dict[str, Any]] = []
    seen_versions: set[str] = set()
    seen_ids: set[str] = set()
    for line_number, line in enumerate(prefix.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ResearchProjectV2Error(
                "Immutable research project version failed verification: invalid manifest JSON",
                code="RESEARCH_PROJECT_IMMUTABILITY_VIOLATION",
                details={"project": project_slug, "reason": f"manifest row {line_number}"},
            ) from exc
        semantic_version = row.get("semantic_version") if isinstance(row, dict) else None
        version_id = row.get("version_id") if isinstance(row, dict) else None
        if semantic_version in seen_versions or version_id in seen_ids:
            raise ResearchProjectV2Error(
                "Immutable research project version failed verification: duplicate manifest row",
                code="RESEARCH_PROJECT_IMMUTABILITY_VIOLATION",
                details={"project": project_slug, "reason": "duplicate manifest version"},
            )
        if not isinstance(semantic_version, str) or not isinstance(version_id, str):
            raise ResearchProjectV2Error(
                "Immutable research project version failed verification: invalid manifest row",
                code="RESEARCH_PROJECT_IMMUTABILITY_VIOLATION",
                details={"project": project_slug, "reason": f"manifest row {line_number}"},
            )
        seen_versions.add(semantic_version)
        seen_ids.add(version_id)
        rows.append(row)
    return prefix, rows


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _rebuild_index(
    args: argparse.Namespace, layout: ResearchProjectLayout
) -> dict[str, object]:
    project_slugs = list_project_slugs(layout=layout)
    if not project_slugs:
        raise ResearchProjectV2Error(
            "Research projects not found",
            code="RESEARCH_PROJECT_NOT_FOUND",
            details={"artifact": "projects"},
        )

    planned_versions: list[dict[str, Any]] = []
    planned_manifests: list[tuple[Path, bytes]] = []
    index_rows: list[dict[str, Any]] = []
    timestamps: list[str] = []
    for slug in project_slugs:
        identity = load_project(slug, layout=layout)
        timestamps.append(identity["created_at"])
        project_dir = layout.project_dir(slug)
        manifest_path = project_dir / "version_manifest.jsonl"
        prefix, rows = _manifest_rows(manifest_path, slug)
        manifested = {row["semantic_version"] for row in rows}
        version_paths = sorted(
            (project_dir / "versions").glob("v*.json"),
            key=lambda path: _semver_key(path.stem[1:]),
        )
        discovered = [path.stem[1:] for path in version_paths]
        if len(discovered) != len(set(discovered)):
            raise ResearchProjectV2Error(
                "Immutable research project version failed verification: duplicate version",
                code="RESEARCH_PROJECT_IMMUTABILITY_VIOLATION",
                details={"project": slug, "reason": "duplicate version"},
            )
        missing_files = sorted(manifested - set(discovered), key=_semver_key)
        if missing_files:
            raise ResearchProjectV2Error(
                "Immutable research project version failed verification: manifested version missing",
                code="RESEARCH_PROJECT_IMMUTABILITY_VIOLATION",
                details={"project": slug, "reason": "manifested version missing", "versions": missing_files},
            )

        append_rows: list[dict[str, Any]] = []
        for semantic_version, version_path in zip(discovered, version_paths):
            if semantic_version in manifested:
                version = load_version(slug, semantic_version, layout=layout)
            else:
                try:
                    version = json.loads(version_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ResearchProjectV2Error(
                        "Research project payload does not match the research_version_v2 schema",
                        code="RESEARCH_PROJECT_SCHEMA_INVALID",
                        details={"project": slug, "version": semantic_version},
                    ) from exc
                if not isinstance(version, dict):
                    raise ResearchProjectV2Error(
                        "Research project payload does not match the research_version_v2 schema",
                        code="RESEARCH_PROJECT_SCHEMA_INVALID",
                        details={"project": slug, "version": semantic_version},
                    )
                calculated_hash = content_sha256(version, excluded_paths={("content_hash",)})
                candidate = dict(version)
                candidate["content_hash"] = calculated_hash
                validate_schema_payload("research_version_v2", candidate)
                validate_version_semantics(candidate)
                if version.get("content_hash") not in {"0" * 64, calculated_hash}:
                    raise ResearchProjectV2Error(
                        "Immutable research project version failed verification: content hash mismatch",
                        code="RESEARCH_PROJECT_IMMUTABILITY_VIOLATION",
                        details={"project": slug, "version": semantic_version, "reason": "content hash mismatch"},
                    )
                version = candidate
                planned_versions.append(
                    {"path": version_path, "payload": version, "project": slug, "semantic_version": semantic_version}
                )
                append_rows.append(
                    {
                        "version_id": version["version_id"],
                        "semantic_version": semantic_version,
                        "parent_version_id": version["parent_version_id"],
                        "relative_path": f"versions/v{semantic_version}.json",
                        "content_hash": calculated_hash,
                        "created_at": version["created_at"],
                    }
                )
            timestamps.append(version["created_at"])

        if append_rows:
            suffix = b"".join(
                (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
                for row in sorted(append_rows, key=lambda row: _semver_key(row["semantic_version"]))
            )
            planned_manifests.append((manifest_path, prefix + suffix))
        index_rows.append(
            {
                "project_id": identity["project_id"],
                "project_slug": slug,
                "title": identity["title"],
                "current_lifecycle_state": identity["current_lifecycle_state"],
                "current_version": identity["current_version"],
                "latest_reviewed_version": identity["latest_reviewed_version"],
                "latest_published_version": identity["latest_published_version"],
                "relative_path": f"projects/{slug}/project.json",
            }
        )

    index = {
        "artifact_version": "2.0.0",
        "generated_at": max(timestamps),
        "projects": index_rows,
    }
    validate_schema_payload("research_project_index_v2", index)
    if args.write:
        for item in planned_versions:
            _atomic_write(item["path"], _json_bytes(item["payload"]))
        for path, data in planned_manifests:
            _atomic_write(path, data)
        index_bytes = _json_bytes(index)
        if not layout.index_path.is_file() or layout.index_path.read_bytes() != index_bytes:
            _atomic_write(layout.index_path, index_bytes)
    return {
        "status": "written" if args.write else "planned",
        "projects": project_slugs,
        "versions": [
            f"{item['project']}@{item['semantic_version']}" for item in planned_versions
        ],
        "index": str(layout.index_path.relative_to(layout.root)),
    }


def _execute(args: argparse.Namespace, layout: ResearchProjectLayout) -> tuple[object, int]:
    if args.command == "rebuild-index":
        return _rebuild_index(args, layout), 0
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
