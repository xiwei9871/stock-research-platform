from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Callable

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.discovery import (
    ImportedJsonDiscoveryProvider,
    discover_sources,
    write_discovery_batch,
)
from stock_research.research_project_v2_1.coverage import summarize_evidence_coverage
from stock_research.research_project_v2_1.acquisition_contracts import AcquisitionContext
from stock_research.research_project_v2_1.acquisition_doctor import (
    build_provider_diagnostic,
    write_provider_diagnostic,
)
from stock_research.research_project_v2_1.acquisition_http import DirectHttpProvider
from stock_research.research_project_v2_1.acquisition_import import LocalFileProvider
from stock_research.research_project_v2_1.acquisition_storage import read_acquisition_attempt
from stock_research.research_project_v2_1.diff import diff_industry_versions
from stock_research.research_project_v2_1.evidence import (
    validate_industry_evidence_assessment,
    write_industry_evidence_assessment,
)
from stock_research.research_project_v2_1.gates import evaluate_industry_design_gate
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import (
    list_layered_project_slugs,
    list_layered_versions,
    load_industry_version,
    load_layered_project,
    read_layered_bytes,
    read_layered_canonical_json,
)
from stock_research.research_project_v2_1.maintenance import rebuild_layered_index
from stock_research.research_project_v2_1.normalize import (
    normalize_artifact,
    validate_normalized_document,
    write_normalized_document,
)
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2_1.search_plan import validate_search_plans
from stock_research.research_project_v2_1.snapshot import (
    RequestsFetchTransport,
    SystemAddressResolver,
    snapshot_candidate,
    validate_evidence_artifact,
)


_SAFE_ARTIFACT_ID = re.compile(r"evidence_artifact:[a-f0-9]{24}")
_Clock = Callable[[], datetime]


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
    discover.add_argument("--discovered-at")
    discover.add_argument("--agent-run-id")
    discover.add_argument("--write", action="store_true")

    snapshot = commands.add_parser(
        "snapshot", help="Fetch and snapshot one source candidate."
    )
    snapshot.add_argument("--candidate", required=True)
    snapshot.add_argument("--fetched-at")
    snapshot.add_argument("--agent-run-id")
    snapshot.add_argument("--write", action="store_true")

    parse = commands.add_parser("parse", help="Normalize a stored evidence artifact.")
    parse.add_argument("--artifact-id", required=True)
    parse.add_argument("--parsed-at")
    parse.add_argument("--agent-run-id")
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

    diff = commands.add_parser("diff", help="Diff two direct layered versions by stable ID.")
    diff.add_argument("--project", required=True)
    diff.add_argument("--from", dest="from_version", required=True)
    diff.add_argument("--to", dest="to_version", required=True)

    coverage = commands.add_parser(
        "coverage", help="Summarize evidence acquisition and bottleneck coverage."
    )
    coverage.add_argument("--project", required=True)
    coverage.add_argument("--version", required=True)

    rebuild = commands.add_parser(
        "rebuild-index", help="Rebuild only the v2.1 index generation."
    )
    rebuild.add_argument("--write", action="store_true")

    acquisition = commands.add_parser(
        "acquisition", help="Run explicit acquisition providers and diagnostics."
    )
    acquisition_commands = acquisition.add_subparsers(
        dest="acquisition_command", required=True
    )
    for name in ("doctor", "smoke"):
        command = acquisition_commands.add_parser(name)
        command.add_argument("--project", required=True)
        command.add_argument("--version", required=True)
        command.add_argument("--dry-run", action="store_true")
    doctor = acquisition_commands.choices["doctor"]
    doctor.add_argument("--write", action="store_true")
    doctor.add_argument("--agent-run-id")

    fetch = acquisition_commands.add_parser("fetch")
    fetch.add_argument("--project", required=True)
    fetch.add_argument("--version", required=True)
    fetch.add_argument("--requirement")
    fetch.add_argument("--candidate", required=True)
    fetch.add_argument("--proxy-mode", choices=("direct", "environment_proxy", "explicit_proxy"), default="direct")
    fetch.add_argument("--timeout-seconds", type=float, default=20.0)
    fetch.add_argument("--max-retries", type=int, default=2)
    fetch.add_argument("--dry-run", action="store_true")
    fetch.add_argument("--agent-run-id")

    import_command = acquisition_commands.add_parser("import")
    import_command.add_argument("--project", required=True)
    import_command.add_argument("--version", required=True)
    import_command.add_argument("--request", required=True)
    import_command.add_argument("--dry-run", action="store_true")

    show_attempt = acquisition_commands.add_parser("show-attempt")
    show_attempt.add_argument("--project", required=True)
    show_attempt.add_argument("--version", required=True)
    show_attempt.add_argument("--attempt-id", required=True)
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


def _timestamp(explicit: str | None, clock: _Clock) -> str:
    if explicit is None:
        value = clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ResearchProjectV2Error(
                "Operation clock must return an aware datetime",
                code="RESEARCH_PROJECT_V2_1_CLI_INPUT_INVALID",
                details={"field": "operation_time"},
            )
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    try:
        parsed = datetime.fromisoformat(explicit.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ResearchProjectV2Error(
            "Operation time must be RFC3339",
            code="RESEARCH_PROJECT_V2_1_CLI_INPUT_INVALID",
            details={"field": "operation_time"},
        ) from exc
    if parsed.tzinfo is None or explicit != explicit.strip():
        raise ResearchProjectV2Error(
            "Operation time must be RFC3339",
            code="RESEARCH_PROJECT_V2_1_CLI_INPUT_INVALID",
            details={"field": "operation_time"},
        )
    return explicit


def _operation_provenance(
    source: object,
    *,
    command: str,
    operation_at: str,
    agent_run_id: str | None,
) -> dict[str, Any]:
    created_in_version = source.get("created_in_version") if isinstance(source, dict) else None
    if not isinstance(created_in_version, str) or not created_in_version.strip():
        raise ResearchProjectV2Error(
            "Upstream object lacks created_in_version",
            code="RESEARCH_PROJECT_V2_1_CLI_INPUT_INVALID",
            details={"field": "provenance.created_in_version"},
        )
    if agent_run_id is not None and (
        not isinstance(agent_run_id, str)
        or not agent_run_id.strip()
        or agent_run_id != agent_run_id.strip()
    ):
        raise ResearchProjectV2Error(
            "agent_run_id must be canonical",
            code="RESEARCH_PROJECT_V2_1_CLI_INPUT_INVALID",
            details={"field": "agent_run_id"},
        )
    effective_run_id = agent_run_id or (
        f"research-project-v2-1-cli:{command}:{operation_at}"
    )
    return {
        "created_by": "research-project-v2-1-cli",
        "actor_type": "automated_pipeline",
        "agent_run_id": effective_run_id,
        "created_at": operation_at,
        "created_in_version": created_in_version,
        "review_status": "unreviewed",
    }


def _discover(
    plan_path: str,
    results_path: str,
    *,
    clock: _Clock,
    agent_run_id: str | None,
    discovered_at: str | None = None,
) -> dict[str, Any]:
    plan_payload = _read_json(plan_path, purpose="Search Plan")
    plan = _unwrap(plan_payload, "search_plan")
    results = _read_json(results_path, purpose="discovery results")
    operation_at = _timestamp(
        discovered_at if discovered_at is not None else results.get("discovered_at"),
        clock,
    )
    provenance = _operation_provenance(
        plan.get("provenance"),
        command="discover",
        operation_at=operation_at,
        agent_run_id=agent_run_id,
    )
    return discover_sources(
        plan,
        ImportedJsonDiscoveryProvider(results_path),
        provider_name=str(results.get("provider", "imported_json")),
        discovered_at=operation_at,
        provenance=provenance,
    )


def _temporary_layout() -> tuple[tempfile.TemporaryDirectory[str], LayeredResearchLayout]:
    temporary = tempfile.TemporaryDirectory(prefix="research-project-v2-1-preview-")
    root = Path(temporary.name).resolve() / "v2_1"
    root.mkdir(mode=0o700)
    return temporary, LayeredResearchLayout(root)


def _snapshot(args: argparse.Namespace, *, clock: _Clock) -> dict[str, Any]:
    candidate = _unwrap(
        _read_json(args.candidate, purpose="source candidate"),
        "source_candidate",
    )
    fetched_at = _timestamp(args.fetched_at, clock)
    provenance = _operation_provenance(
        candidate.get("provenance"),
        command="snapshot",
        operation_at=fetched_at,
        agent_run_id=args.agent_run_id,
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
    relative_path = f"evidence/metadata/{artifact_id}.json"
    try:
        payload = read_layered_canonical_json(relative_path, layout=layout)
    except ResearchProjectV2Error as exc:
        if exc.code == "RESEARCH_PROJECT_V2_1_MANAGED_FILE_NOT_FOUND":
            raise ResearchProjectV2Error(
                "Evidence artifact not found or unreadable",
                code="RESEARCH_PROJECT_V2_1_ARTIFACT_NOT_FOUND",
                details={"artifact_id": artifact_id},
            ) from exc
        raise
    validate_v2_1_schema_payload("evidence_artifact_v2_1", payload, layout=layout)
    artifact = _unwrap(payload, "evidence_artifact")
    artifact = validate_evidence_artifact(artifact)
    if artifact["artifact_id"] != artifact_id:
        raise ResearchProjectV2Error(
            "Evidence artifact metadata identity mismatch",
            code="RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION",
            details={"artifact_id": artifact_id},
        )
    return artifact


def _parse(
    args: argparse.Namespace,
    layout: LayeredResearchLayout,
    *,
    clock: _Clock,
) -> dict[str, Any]:
    artifact = _artifact_from_metadata(args.artifact_id, layout)
    parsed_at = _timestamp(args.parsed_at, clock)
    provenance = _operation_provenance(
        artifact.get("provenance"),
        command="parse",
        operation_at=parsed_at,
        agent_run_id=args.agent_run_id,
    )
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at=parsed_at,
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
    verified_documents: dict[str, dict[str, Any]] = {}
    for artifact_id, artifact in sorted(artifacts.items()):
        try:
            raw = read_layered_bytes(
                artifact["raw_path"],
                layout=layout,
                max_bytes=artifact["byte_count"],
            )
            if len(raw) != artifact["byte_count"]:
                findings.append({"code": "RAW_ARTIFACT_SIZE_MISMATCH", "artifact_id": artifact_id})
            if hashlib.sha256(raw).hexdigest() != artifact["content_sha256"]:
                findings.append({"code": "RAW_ARTIFACT_HASH_MISMATCH", "artifact_id": artifact_id})
        except ResearchProjectV2Error as exc:
            findings.append(
                {
                    "code": "RAW_ARTIFACT_NOT_FOUND",
                    "artifact_id": artifact_id,
                    "error_code": exc.code,
                }
            )
        try:
            metadata = read_layered_canonical_json(
                f"evidence/metadata/{artifact_id}.json",
                layout=layout,
            )
            validate_v2_1_schema_payload(
                "evidence_artifact_v2_1", metadata, layout=layout
            )
            persisted_artifact = validate_evidence_artifact(
                metadata["evidence_artifact"]
            )
            if persisted_artifact["artifact_id"] != artifact_id:
                raise ResearchProjectV2Error(
                    "Persisted artifact path identity mismatch",
                    code="RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION",
                )
            if persisted_artifact != artifact:
                findings.append({"code": "ARTIFACT_METADATA_SNAPSHOT_DRIFT", "artifact_id": artifact_id})
        except (ResearchProjectV2Error, KeyError, TypeError) as exc:
            findings.append(
                {
                    "code": "ARTIFACT_METADATA_INVALID",
                    "artifact_id": artifact_id,
                    "error_code": getattr(exc, "code", type(exc).__name__),
                }
            )
    for document_id, document in sorted(documents.items()):
        try:
            wrapper = read_layered_canonical_json(
                f"evidence/normalized/{document_id}.json",
                layout=layout,
            )
            validate_v2_1_schema_payload(
                "normalized_document_v2_1", wrapper, layout=layout
            )
            persisted_document = validate_normalized_document(
                wrapper["normalized_document"]
            )
            if persisted_document["document_id"] != document_id:
                raise ResearchProjectV2Error(
                    "Persisted document path identity mismatch",
                    code="RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION",
                )
            verified_documents[document_id] = persisted_document
            if persisted_document != document:
                findings.append({"code": "NORMALIZED_DOCUMENT_SNAPSHOT_DRIFT", "document_id": document_id})
        except (ResearchProjectV2Error, KeyError, TypeError) as exc:
            findings.append(
                {
                    "code": "NORMALIZED_DOCUMENT_NOT_FOUND",
                    "document_id": document_id,
                    "error_code": getattr(exc, "code", type(exc).__name__),
                }
            )
        if document.get("artifact_id") not in artifacts:
            findings.append(
                {"code": "DOCUMENT_ARTIFACT_NOT_FOUND", "document_id": document_id}
            )
    for assessment in snapshot["industry_evidence_assessments"]:
        artifact = artifacts.get(assessment.get("artifact_id"))
        document = verified_documents.get(assessment.get("normalized_document_id"))
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
            findings.append(
                {
                    "code": "LOCATOR_UNVERIFIED",
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
        try:
            wrapper = read_layered_canonical_json(
                f"evidence/assessments/{assessment.get('assessment_id')}.json",
                layout=layout,
            )
            persisted_assessment = validate_industry_evidence_assessment(wrapper)
            if persisted_assessment["assessment_id"] != assessment.get(
                "assessment_id"
            ):
                raise ResearchProjectV2Error(
                    "Persisted assessment path identity mismatch",
                    code="RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION",
                )
            if persisted_assessment != assessment:
                findings.append(
                    {
                        "code": "ASSESSMENT_SNAPSHOT_DRIFT",
                        "assessment_id": assessment.get("assessment_id"),
                    }
                )
        except (ResearchProjectV2Error, KeyError, TypeError) as exc:
            findings.append(
                {
                    "code": "ASSESSMENT_NOT_FOUND",
                    "assessment_id": assessment.get("assessment_id"),
                    "error_code": getattr(exc, "code", type(exc).__name__),
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


def _acquisition_provenance(
    *, project: str, version: str, operation_at: str, agent_run_id: str | None
) -> dict[str, Any]:
    return {
        "created_by": "research-project-v2-1 acquisition",
        "actor_type": "automated_pipeline",
        "agent_run_id": agent_run_id,
        "created_at": operation_at,
        "created_in_version": f"research_version:{project}:{version}",
        "review_status": "unreviewed",
    }


def _acquisition_dispatch(
    args: argparse.Namespace,
    layout: LayeredResearchLayout,
    clock: _Clock,
) -> dict[str, Any]:
    version = load_industry_version(args.project, args.version, layout=layout)
    version_id = version["version_id"]
    if args.acquisition_command == "smoke":
        return {
            "status": "not_run",
            "reason": "online acquisition smoke requires separate Phase C approval",
        }
    if args.acquisition_command == "show-attempt":
        return {
            "status": "pass",
            "acquisition_attempt": read_acquisition_attempt(
                args.attempt_id, layout=layout
            ),
        }

    operation_at = _timestamp(None, clock)
    provenance = _acquisition_provenance(
        project=args.project,
        version=args.version,
        operation_at=operation_at,
        agent_run_id=getattr(args, "agent_run_id", None),
    )
    if args.acquisition_command == "doctor":
        diagnostic = build_provider_diagnostic(
            generated_at=operation_at,
            provenance=provenance,
            browser_runtime_status="not_tested",
            search_provider_status="unavailable",
            checks=[],
        )
        write = bool(args.write and not args.dry_run)
        path = write_provider_diagnostic(diagnostic, layout=layout) if write else None
        return {
            "status": "pass",
            "written": write,
            "path": str(path) if path is not None else None,
            "provider_diagnostic": diagnostic,
        }

    temporary: tempfile.TemporaryDirectory[str] | None = None
    effective_layout = layout
    if args.dry_run:
        temporary, effective_layout = _temporary_layout()
    try:
        if args.acquisition_command == "fetch":
            candidate = _unwrap(
                _read_json(args.candidate, purpose="source candidate"),
                "source_candidate",
            )
            candidate_provenance = candidate.get("provenance")
            context = AcquisitionContext(
                project_id=f"research_project:{args.project}",
                research_version_context=version_id,
                requirement_id=args.requirement,
                candidate_id=candidate.get("candidate_id"),
                provenance=(
                    candidate_provenance
                    if isinstance(candidate_provenance, dict)
                    else provenance
                ),
            )
            result = DirectHttpProvider().acquire(
                candidate,
                context=context,
                layout=effective_layout,
                attempted_at=operation_at,
                proxy_mode=args.proxy_mode,
                timeout_seconds=args.timeout_seconds,
                max_retries=args.max_retries,
            )
            return {
                "status": "pass",
                "written": not args.dry_run,
                "acquisition_attempt": result.attempt,
                "evidence_artifact": result.artifact,
            }
        if args.acquisition_command == "import":
            request = _unwrap(
                _read_json(args.request, purpose="manual import request"),
                "manual_import_request",
            )
            result = LocalFileProvider().acquire(request, layout=effective_layout)
            return {
                "status": "pass",
                "written": not args.dry_run,
                "acquisition_attempt": result.attempt,
                "evidence_artifact": result.artifact,
            }
    finally:
        if temporary is not None:
            temporary.cleanup()
    raise AssertionError(f"Unhandled acquisition command: {args.acquisition_command}")


def _dispatch(
    args: argparse.Namespace,
    layout: LayeredResearchLayout,
    clock: _Clock,
) -> dict[str, Any]:
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
        batch = _discover(
            args.search_plan,
            args.results,
            clock=clock,
            agent_run_id=args.agent_run_id,
            discovered_at=args.discovered_at,
        )
        path = write_discovery_batch(batch) if args.write else None
        return {
            "status": "pass",
            "written": bool(args.write),
            "path": str(path) if path else None,
            "batch": batch,
        }
    if args.command == "snapshot":
        return _snapshot(args, clock=clock)
    if args.command == "parse":
        return _parse(args, layout, clock=clock)
    if args.command == "assess":
        return _assessment(args)
    if args.command == "audit":
        return _audit(args, layout)
    if args.command == "diff":
        before = load_industry_version(args.project, args.from_version, layout=layout)
        after = load_industry_version(args.project, args.to_version, layout=layout)
        return {"status": "pass", **diff_industry_versions(before, after)}
    if args.command == "coverage":
        version = load_industry_version(args.project, args.version, layout=layout)
        return {"status": "pass", **summarize_evidence_coverage(version)}
    if args.command == "rebuild-index":
        return {"status": "pass", **rebuild_layered_index(args.write, layout=layout)}
    if args.command == "acquisition":
        return _acquisition_dispatch(args, layout, clock)
    raise AssertionError(f"Unhandled command: {args.command}")


def _error_payload(error: ResearchProjectV2Error) -> dict[str, Any]:
    return {"error": {"code": error.code, "message": str(error), "details": error.details}}


def _exit_for_domain_error(
    error: ResearchProjectV2Error,
    *,
    command: str | None,
) -> int:
    code = error.code
    not_found = {
        "RESEARCH_PROJECT_V2_1_PROJECT_NOT_FOUND",
        "RESEARCH_PROJECT_V2_1_VERSION_NOT_FOUND",
        "RESEARCH_PROJECT_V2_1_INDEX_NOT_FOUND",
        "RESEARCH_PROJECT_V2_1_ARTIFACT_NOT_FOUND",
        "RESEARCH_PROJECT_V2_1_DOCUMENT_NOT_FOUND",
        "RESEARCH_PROJECT_V2_1_MANAGED_FILE_NOT_FOUND",
    }
    integrity = {
        "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION",
        "RESEARCH_PROJECT_V2_1_DISCOVERY_IMMUTABILITY_VIOLATION",
        "RESEARCH_PROJECT_V2_1_NORMALIZE_IMMUTABILITY_VIOLATION",
        "RESEARCH_PROJECT_V2_1_SNAPSHOT_IMMUTABILITY_VIOLATION",
        "RESEARCH_PROJECT_V2_1_SNAPSHOT_PATH_VIOLATION",
        "RESEARCH_PROJECT_V2_1_DISCOVERY_PATH_VIOLATION",
        "RESEARCH_PROJECT_V2_1_NORMALIZE_PATH_VIOLATION",
        "RESEARCH_PROJECT_V2_1_EVIDENCE_PATH_VIOLATION",
        "RESEARCH_PROJECT_V2_1_PATH_VIOLATION",
        "RESEARCH_PROJECT_V2_1_STORAGE_ERROR",
    }
    parser = {
        "RESEARCH_PROJECT_V2_1_PARSE_INVALID",
        "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED",
        "RESEARCH_PROJECT_V2_1_PARSE_UNSUPPORTED_MEDIA",
        "RESEARCH_PROJECT_V2_1_NORMALIZE_INVALID",
    }
    evidence_audit = {
        "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID",
        "RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID",
        "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID",
        "RESEARCH_PROJECT_V2_1_EVIDENCE_RELATIONSHIP_INVALID",
        "RESEARCH_PROJECT_V2_1_READ_ERROR",
        "RESEARCH_PROJECT_V2_1_READ_LIMIT_EXCEEDED",
    }
    if code in not_found:
        return 6
    if code in integrity:
        return 5
    if code in {
        "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID",
        "RESEARCH_PROJECT_V2_1_SCHEMA_NOT_FOUND",
        "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID",
        "RESEARCH_PROJECT_V2_1_CLI_ARGUMENT_INVALID",
        "RESEARCH_PROJECT_V2_1_CLI_INPUT_INVALID",
    }:
        return 2
    if command == "search-plan" and code == "RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID":
        return 3
    if command == "audit" and code in evidence_audit:
        return 3
    if command == "gate":
        return 4
    if command == "parse" and code in parser:
        return 9
    if code in {
        "RESEARCH_PROJECT_V2_1_READ_ERROR",
        "RESEARCH_PROJECT_V2_1_READ_LIMIT_EXCEEDED",
        "RESEARCH_PROJECT_V2_1_EVIDENCE_STORAGE_FAILED",
        "RESEARCH_PROJECT_V2_1_DISCOVERY_STORAGE_FAILED",
        "RESEARCH_PROJECT_V2_1_NORMALIZE_STORAGE_FAILED",
        "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_ERROR",
        "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED",
    }:
        return 10
    if command == "discover" and code.startswith("RESEARCH_PROJECT_V2_1_DISCOVERY_"):
        return 8
    if command == "snapshot" and (
        code.startswith("RESEARCH_PROJECT_V2_1_FETCH_")
        or code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_INVALID"
    ):
        return 8
    return 2


def run_research_project_v2_1_cli(
    argv: list[str] | None = None,
    *,
    clock: _Clock | None = None,
) -> int:
    command: str | None = None
    try:
        args = _parser().parse_args(argv)
        command = args.command
        effective_clock = clock or (lambda: datetime.now(timezone.utc))
        payload = _dispatch(args, LayeredResearchLayout.default(), effective_clock)
        _print_json(payload)
        if args.command == "gate" and payload.get("status") == "fail":
            return 4
        if args.command == "audit" and payload.get("status") == "fail":
            return 3
        return 0
    except ResearchProjectV2Error as exc:
        _print_json(_error_payload(exc))
        return _exit_for_domain_error(exc, command=command)
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
