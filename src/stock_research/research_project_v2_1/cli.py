from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.discovery import (
    ImportedJsonDiscoveryProvider,
    discover_sources,
    write_discovery_batch,
)
from stock_research.research_project_v2_1.evidence import (
    write_industry_evidence_assessment,
)
from stock_research.research_project_v2_1.gates import evaluate_industry_design_gate
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import (
    list_layered_project_slugs,
    list_layered_versions,
    load_industry_version,
    load_layered_project,
)
from stock_research.research_project_v2_1.maintenance import rebuild_layered_index
from stock_research.research_project_v2_1.normalize import (
    normalize_artifact,
    write_normalized_document,
)
from stock_research.research_project_v2_1.search_plan import validate_search_plans
from stock_research.research_project_v2_1.snapshot import (
    RequestsFetchTransport,
    SystemAddressResolver,
    snapshot_candidate,
)


_SAFE_ARTIFACT_ID = re.compile(r"evidence_artifact:[a-f0-9]{24}")


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ResearchProjectV2Error(
            message,
            code="RESEARCH_PROJECT_V2_1_CLI_ARGUMENT_INVALID",
            details={"argument_error": message},
        )


def _parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="research-project-v2-1")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List layered Industry Research projects.")

    show = commands.add_parser("show", help="Show one immutable version.")
    show.add_argument("--project", required=True)
    show.add_argument("--version", required=True)

    validate = commands.add_parser("validate", help="Validate one or all versions.")
    selection = validate.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--project")
    validate.add_argument("--version")

    gate = commands.add_parser("gate", help="Evaluate an Industry gate.")
    gate.add_argument("--project", required=True)
    gate.add_argument("--version", required=True)
    gate.add_argument("--gate", choices=("industry-design",), required=True)

    search_plan = commands.add_parser(
        "search-plan", help="Print Search Plans and requirement coverage."
    )
    search_plan.add_argument("--project", required=True)
    search_plan.add_argument("--version", required=True)

    discover = commands.add_parser(
        "discover", help="Normalize imported discovery results."
    )
    discover.add_argument("--search-plan", required=True)
    discover.add_argument("--results", required=True)
    discover.add_argument("--write", action="store_true")

    snapshot = commands.add_parser(
        "snapshot", help="Fetch and snapshot one source candidate."
    )
    snapshot.add_argument("--candidate", required=True)
    snapshot.add_argument("--write", action="store_true")

    parse = commands.add_parser("parse", help="Normalize a stored evidence artifact.")
    parse.add_argument("--artifact-id", required=True)
    parse.add_argument("--write", action="store_true")

    assess = commands.add_parser(
        "assess", help="Validate an Industry Evidence Assessment."
    )
    assess.add_argument("--assessment", required=True)
    assess.add_argument("--write", action="store_true")

    audit = commands.add_parser(
        "audit", help="Audit stored Industry research evidence links."
    )
    audit.add_argument("--project", required=True)
    audit.add_argument("--version", required=True)

    rebuild = commands.add_parser(
        "rebuild-index", help="Rebuild only the v2.1 index generation."
    )
    rebuild.add_argument("--write", action="store_true")
    return parser


def _print_json(payload: object) -> None:
    def fallback(value: object) -> object:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (set, frozenset)):
            return sorted(str(item) for item in value)
        return f"<{type(value).__name__}>"

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=fallback,
        )
    )


def _read_json(path: str, *, purpose: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchProjectV2Error(
            f"Unable to read {purpose} JSON",
            code="RESEARCH_PROJECT_V2_1_CLI_INPUT_INVALID",
            details={"path": path, "purpose": purpose, "reason": type(exc).__name__},
        ) from exc
    if not isinstance(payload, dict):
        raise ResearchProjectV2Error(
            f"{purpose} JSON must contain an object",
            code="RESEARCH_PROJECT_V2_1_CLI_INPUT_INVALID",
            details={"path": path, "purpose": purpose},
        )
    return payload


def _version_summary(identity: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    snapshot = version["snapshot"]
    return {
        "project_id": identity["project_id"],
        "project_slug": identity["project_slug"],
        "title": identity["title"],
        "research_layer": snapshot["research_layer"],
        "version_id": version["version_id"],
        "semantic_version": version["semantic_version"],
        "creation_stage": version["creation_stage"],
        "project_lifecycle_state": snapshot["project_lifecycle_state"],
        "evidence_stage": snapshot["evidence_stage"],
        "conclusion_status": snapshot["conclusion_status"],
        "investment_status": snapshot["investment_status"],
    }


def _list(layout: LayeredResearchLayout) -> dict[str, Any]:
    rows = []
    for slug in list_layered_project_slugs(layout=layout):
        identity = load_layered_project(slug, layout=layout)
        version = load_industry_version(slug, layout=layout)
        rows.append(_version_summary(identity, version))
    return {"projects": rows}


def _validate(args: argparse.Namespace, layout: LayeredResearchLayout) -> dict[str, Any]:
    if args.version and not args.project:
        raise ResearchProjectV2Error(
            "--version requires --project",
            code="RESEARCH_PROJECT_V2_1_CLI_ARGUMENT_INVALID",
            details={"argument": "--version"},
        )
    targets: list[tuple[str, str]] = []
    if args.project:
        versions = (
            [args.version]
            if args.version
            else list_layered_versions(args.project, layout=layout)
        )
        targets.extend((args.project, version) for version in versions)
    else:
        for slug in list_layered_project_slugs(layout=layout):
            targets.extend(
                (slug, version)
                for version in list_layered_versions(slug, layout=layout)
            )
    if not targets:
        raise ResearchProjectV2Error(
            "Layered research project version not found",
            code="RESEARCH_PROJECT_V2_1_VERSION_NOT_FOUND",
            details={},
        )
    validated = []
    for slug, semantic_version in targets:
        identity = load_layered_project(slug, layout=layout)
        version = load_industry_version(slug, semantic_version, layout=layout)
        validated.append(_version_summary(identity, version))
    return {"status": "pass", "validated": validated}


def _gate(args: argparse.Namespace, layout: LayeredResearchLayout) -> dict[str, Any]:
    identity = load_layered_project(args.project, layout=layout)
    version = load_industry_version(args.project, args.version, layout=layout)
    result = evaluate_industry_design_gate(identity, version, layout=layout)
    return {
        **result,
        "verified_scope": "stored_project_version_and_lineage_only",
        "outcome_field": "status",
    }


def _search_plan(args: argparse.Namespace, layout: LayeredResearchLayout) -> dict[str, Any]:
    version = load_industry_version(args.project, args.version, layout=layout)
    snapshot = version["snapshot"]
    requirements = snapshot["evidence_requirements"]
    plans = snapshot["search_plans"]
    validate_search_plans(requirements, plans)
    covered = sorted({item for plan in plans for item in plan["requirement_ids"]})
    required = sorted(row["requirement_id"] for row in requirements)
    return {
        "status": "pass",
        "project_slug": args.project,
        "semantic_version": args.version,
        "search_plans": deepcopy(plans),
        "coverage": {
            "requirement_ids": required,
            "covered_requirement_ids": covered,
            "uncovered_requirement_ids": sorted(set(required) - set(covered)),
        },
    }


def _unwrap(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, payload)
    if not isinstance(value, dict):
        raise ResearchProjectV2Error(
            f"{key} must be an object",
            code="RESEARCH_PROJECT_V2_1_CLI_INPUT_INVALID",
            details={"field": key},
        )
    return value


def _discover(plan_path: str, results_path: str) -> dict[str, Any]:
    plan_payload = _read_json(plan_path, purpose="Search Plan")
    plan = _unwrap(plan_payload, "search_plan")
    results = _read_json(results_path, purpose="discovery results")
    provenance = plan.get("provenance")
    discovered_at = results.get("discovered_at") or (
        provenance.get("created_at") if isinstance(provenance, dict) else None
    )
    if not isinstance(discovered_at, str) or not isinstance(provenance, dict):
        raise ResearchProjectV2Error(
            "Discovery input requires deterministic discovered_at and provenance",
            code="RESEARCH_PROJECT_V2_1_DISCOVERY_INPUT_INVALID",
            details={"search_plan": plan_path, "results": results_path},
        )
    return discover_sources(
        plan,
        ImportedJsonDiscoveryProvider(results_path),
        provider_name=str(results.get("provider", "imported_json")),
        discovered_at=discovered_at,
        provenance=provenance,
    )


def _temporary_layout() -> tuple[tempfile.TemporaryDirectory[str], LayeredResearchLayout]:
    temporary = tempfile.TemporaryDirectory(prefix="research-project-v2-1-preview-")
    root = Path(temporary.name) / "v2_1"
    root.mkdir(mode=0o700)
    return temporary, LayeredResearchLayout(root)


def _snapshot(args: argparse.Namespace) -> dict[str, Any]:
    candidate = _unwrap(
        _read_json(args.candidate, purpose="source candidate"),
        "source_candidate",
    )
    provenance = candidate.get("provenance")
    fetched_at = provenance.get("created_at") if isinstance(provenance, dict) else None
    if not isinstance(fetched_at, str) or not isinstance(provenance, dict):
        raise ResearchProjectV2Error(
            "Candidate requires deterministic provenance.created_at",
            code="RESEARCH_PROJECT_V2_1_SNAPSHOT_INVALID",
            details={"path": args.candidate},
        )
    temporary: tempfile.TemporaryDirectory[str] | None = None
    layout = LayeredResearchLayout.default()
    if not args.write:
        temporary, layout = _temporary_layout()
    try:
        result = snapshot_candidate(
            candidate,
            transport=RequestsFetchTransport(),
            resolver=SystemAddressResolver(),
            layout=layout,
            fetched_at=fetched_at,
            provenance=provenance,
        )
        return {
            "status": "pass",
            "written": bool(args.write),
            "artifact": result["artifact"],
            "raw_path": str(result["raw_path"]) if args.write else None,
            "metadata_path": str(result["metadata_path"]) if args.write else None,
        }
    finally:
        if temporary is not None:
            temporary.cleanup()


def _artifact_from_metadata(
    artifact_id: str, layout: LayeredResearchLayout
) -> dict[str, Any]:
    if _SAFE_ARTIFACT_ID.fullmatch(artifact_id) is None:
        raise ResearchProjectV2Error(
            "Evidence artifact not found",
            code="RESEARCH_PROJECT_V2_1_ARTIFACT_NOT_FOUND",
            details={"artifact_id": artifact_id},
        )
    path = layout.evidence_metadata_dir / f"{artifact_id}.json"
    if path.is_symlink():
        raise ResearchProjectV2Error(
            "Unsafe evidence artifact metadata path",
            code="RESEARCH_PROJECT_V2_1_PATH_VIOLATION",
            details={"artifact_id": artifact_id, "path": str(path)},
        )
    if not path.is_file():
        raise ResearchProjectV2Error(
            "Evidence artifact not found",
            code="RESEARCH_PROJECT_V2_1_ARTIFACT_NOT_FOUND",
            details={"artifact_id": artifact_id},
        )
    payload = _read_json(str(path), purpose="evidence artifact metadata")
    artifact = _unwrap(payload, "evidence_artifact")
    if artifact.get("artifact_id") != artifact_id:
        raise ResearchProjectV2Error(
            "Evidence artifact metadata identity mismatch",
            code="RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION",
            details={"artifact_id": artifact_id},
        )
    return artifact


def _parse(args: argparse.Namespace, layout: LayeredResearchLayout) -> dict[str, Any]:
    artifact = _artifact_from_metadata(args.artifact_id, layout)
    provenance = artifact["provenance"]
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at=artifact["fetched_at"],
        provenance=provenance,
    )
    path = write_normalized_document(document, layout=layout) if args.write else None
    return {
        "status": "pass",
        "written": bool(args.write),
        "path": str(path) if path is not None else None,
        "normalized_document": document,
    }


def _assessment(args: argparse.Namespace) -> dict[str, Any]:
    assessment = _unwrap(
        _read_json(args.assessment, purpose="Industry Evidence Assessment"),
        "industry_evidence_assessment",
    )
    temporary: tempfile.TemporaryDirectory[str] | None = None
    layout = LayeredResearchLayout.default()
    if not args.write:
        temporary, layout = _temporary_layout()
    try:
        path = write_industry_evidence_assessment(assessment, layout=layout)
        return {
            "status": "pass",
            "written": bool(args.write),
            "path": str(path) if args.write else None,
            "industry_evidence_assessment": assessment,
        }
    finally:
        if temporary is not None:
            temporary.cleanup()


def _audit(args: argparse.Namespace, layout: LayeredResearchLayout) -> dict[str, Any]:
    identity = load_layered_project(args.project, layout=layout)
    version = load_industry_version(args.project, args.version, layout=layout)
    snapshot = version["snapshot"]
    findings: list[dict[str, Any]] = []
    try:
        validate_search_plans(snapshot["evidence_requirements"], snapshot["search_plans"])
    except ResearchProjectV2Error as exc:
        findings.append({"code": exc.code, "message": str(exc), "details": exc.details})
    artifacts = {row["artifact_id"]: row for row in snapshot["evidence_artifacts"]}
    documents = {row["document_id"]: row for row in snapshot["normalized_documents"]}
    for artifact_id, artifact in sorted(artifacts.items()):
        raw_path = artifact.get("raw_path")
        raw_parts = Path(raw_path).parts if isinstance(raw_path, str) else ()
        if not raw_parts or Path(raw_path).is_absolute() or ".." in raw_parts:
            findings.append(
                {"code": "RAW_ARTIFACT_PATH_INVALID", "artifact_id": artifact_id}
            )
        else:
            stored_raw = layout.root / raw_path
            if stored_raw.is_symlink() or not stored_raw.is_file():
                findings.append(
                    {"code": "RAW_ARTIFACT_NOT_FOUND", "artifact_id": artifact_id}
                )
            else:
                actual_hash = hashlib.sha256(stored_raw.read_bytes()).hexdigest()
                if actual_hash != artifact.get("content_sha256"):
                    findings.append(
                        {
                            "code": "RAW_ARTIFACT_HASH_MISMATCH",
                            "artifact_id": artifact_id,
                        }
                    )
        metadata_path = layout.evidence_metadata_dir / f"{artifact_id}.json"
        if metadata_path.is_symlink() or not metadata_path.is_file():
            findings.append(
                {"code": "ARTIFACT_METADATA_NOT_FOUND", "artifact_id": artifact_id}
            )
    for document_id, document in sorted(documents.items()):
        document_path = layout.evidence_normalized_dir / f"{document_id}.json"
        if document_path.is_symlink() or not document_path.is_file():
            findings.append(
                {
                    "code": "NORMALIZED_DOCUMENT_NOT_FOUND",
                    "document_id": document_id,
                }
            )
        if document.get("artifact_id") not in artifacts:
            findings.append(
                {"code": "DOCUMENT_ARTIFACT_NOT_FOUND", "document_id": document_id}
            )
    for assessment in snapshot["industry_evidence_assessments"]:
        artifact = artifacts.get(assessment.get("artifact_id"))
        document = documents.get(assessment.get("normalized_document_id"))
        if artifact is None:
            findings.append(
                {
                    "code": "ARTIFACT_NOT_FOUND",
                    "assessment_id": assessment.get("assessment_id"),
                }
            )
        if document is None:
            findings.append(
                {
                    "code": "DOCUMENT_NOT_FOUND",
                    "assessment_id": assessment.get("assessment_id"),
                }
            )
        elif assessment.get("locator") not in {
            row.get("locator") for row in document.get("sections", [])
        }:
            findings.append(
                {
                    "code": "LOCATOR_NOT_FOUND",
                    "assessment_id": assessment.get("assessment_id"),
                }
            )
        assessment_path = (
            layout.evidence_assessments_dir
            / f"{assessment.get('assessment_id')}.json"
        )
        if assessment_path.is_symlink() or not assessment_path.is_file():
            findings.append(
                {
                    "code": "ASSESSMENT_NOT_FOUND",
                    "assessment_id": assessment.get("assessment_id"),
                }
            )
    gate = evaluate_industry_design_gate(identity, version, layout=layout)
    if gate["status"] == "fail":
        findings.append({"code": "INDUSTRY_DESIGN_GATE_FAILED"})
    return {
        "status": "fail" if findings else "pass",
        "project_slug": args.project,
        "semantic_version": args.version,
        "verified": gate["verified"],
        "verified_scope": "stored_project_version_and_lineage_only",
        "findings": sorted(findings, key=lambda row: json.dumps(row, sort_keys=True)),
    }


def _dispatch(args: argparse.Namespace, layout: LayeredResearchLayout) -> dict[str, Any]:
    if args.command == "list":
        return _list(layout)
    if args.command == "show":
        return load_industry_version(args.project, args.version, layout=layout)
    if args.command == "validate":
        return _validate(args, layout)
    if args.command == "gate":
        return _gate(args, layout)
    if args.command == "search-plan":
        return _search_plan(args, layout)
    if args.command == "discover":
        batch = _discover(args.search_plan, args.results)
        path = write_discovery_batch(batch) if args.write else None
        return {
            "status": "pass",
            "written": bool(args.write),
            "path": str(path) if path else None,
            "batch": batch,
        }
    if args.command == "snapshot":
        return _snapshot(args)
    if args.command == "parse":
        return _parse(args, layout)
    if args.command == "assess":
        return _assessment(args)
    if args.command == "audit":
        return _audit(args, layout)
    if args.command == "rebuild-index":
        return {"status": "pass", **rebuild_layered_index(args.write, layout=layout)}
    raise AssertionError(f"Unhandled command: {args.command}")


def _error_payload(error: ResearchProjectV2Error) -> dict[str, Any]:
    return {"error": {"code": error.code, "message": str(error), "details": error.details}}


def _exit_for_domain_error(error: ResearchProjectV2Error) -> int:
    code = error.code.upper()
    if any(
        token in code
        for token in ("IMMUTABILITY", "HASH", "MANIFEST", "STORAGE", "PATH")
    ):
        return 5
    if any(token in code for token in ("NOT_FOUND", "MISSING")):
        return 6
    if any(token in code for token in ("DISCOVERY", "FETCH", "SNAPSHOT", "NETWORK", "DNS")):
        return 8
    if any(token in code for token in ("PARSER", "PARSE", "NORMALIZE")):
        return 9
    if "GATE" in code:
        return 4
    if any(token in code for token in ("AUDIT", "SEARCH_PLAN", "COVERAGE")):
        return 3
    return 2


def run_research_project_v2_1_cli(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        payload = _dispatch(args, LayeredResearchLayout.default())
        _print_json(payload)
        if args.command == "gate" and payload.get("status") == "fail":
            return 4
        if args.command == "audit" and payload.get("status") == "fail":
            return 3
        return 0
    except ResearchProjectV2Error as exc:
        _print_json(_error_payload(exc))
        return _exit_for_domain_error(exc)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        error = ResearchProjectV2Error(
            "Unexpected layered research runtime error",
            code="RESEARCH_PROJECT_V2_1_RUNTIME_ERROR",
            details={"exception_type": type(exc).__name__},
        )
        _print_json(_error_payload(error))
        return 10


__all__ = ["run_research_project_v2_1_cli"]
