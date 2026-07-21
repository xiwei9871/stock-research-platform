from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol
import tempfile
from pathlib import Path

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import read_layered_bytes
from stock_research.research_project_v2_1.normalize import normalize_text, write_normalized_document
from stock_research.research_project_v2_1.parsers import ParserLimits, parse_document_bytes
from stock_research.research_project_v2_1.parsers import ParsedDocument, ParsedSection
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2_1.snapshot import _publish_bytes


class NormalizationAdapter(Protocol):
    name: str
    version: str
    configuration: dict[str, Any]

    def normalize(self, data: bytes, *, content_type: str): ...


class DeterministicNormalizationAdapter:
    name = "deterministic"
    version = "1.0.0"
    configuration = {"mode": "deterministic"}

    def normalize(self, data: bytes, *, content_type: str):
        effective_type = "text/plain" if content_type == "text/markdown" else content_type
        if effective_type == "application/vnd.docling+json":
            raise ValueError("Docling JSON requires the optional Docling adapter")
        return parse_document_bytes(data, media_type=effective_type, limits=ParserLimits())


class DoclingNormalizationAdapter:
    name = "docling"
    configuration = {
        "mode": "docling",
        "use_ocr": False,
        "table_mode": "preserve",
    }

    def __init__(self, *, parser=None, version: str = "unknown") -> None:
        self.parser = parser
        self.version = version

    def normalize(self, data: bytes, *, content_type: str) -> ParsedDocument:
        parser = self.parser
        if parser is None:
            from stock_research.data_to_brief_docling_parser_poc import parse_with_docling

            parser = parse_with_docling
        suffix = {
            "application/pdf": ".pdf",
            "text/html": ".html",
        }.get(content_type, ".bin")
        path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(data)
                handle.flush()
                path = Path(handle.name)
            result = parser(path)
        finally:
            if path is not None:
                path.unlink(missing_ok=True)
        if not isinstance(result, dict) or result.get("status") != "parsed":
            raise ValueError("Docling normalization failed")
        markdown = result.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError("Docling emitted empty markdown")
        return ParsedDocument(
            parser="docling",
            media_type="text/markdown",
            title=None,
            sections=(
                ParsedSection(
                    heading=None,
                    locator="docling:markdown:0001",
                    text=markdown,
                ),
            ),
        )


@dataclass(frozen=True)
class NormalizationOutcome:
    status: str
    raw_artifact_id: str
    document: dict[str, Any] | None
    parser: str
    parser_version: str
    parser_configuration: dict[str, Any]
    normalized_at: str
    failure_code: str | None
    diagnostic_summary: str


def _read_raw(artifact: dict[str, Any], layout: LayeredResearchLayout) -> bytes:
    data = read_layered_bytes(
        artifact["raw_artifact_path"],
        layout=layout,
        max_bytes=artifact["byte_size"],
    )
    if len(data) != artifact["byte_size"] or sha256(data).hexdigest() != artifact["content_hash"]:
        raise ResearchProjectV2Error(
            "Raw acquisition artifact failed integrity verification",
            code="RESEARCH_PROJECT_V2_1_ACQUISITION_CHECKSUM_FAILURE",
            details={"artifact_id": artifact["evidence_artifact_id"]},
        )
    return data


def normalize_acquired_artifact(
    artifact: dict[str, Any],
    *,
    adapter: NormalizationAdapter,
    layout: LayeredResearchLayout | None = None,
    parsed_at: str,
    provenance: dict[str, Any],
) -> NormalizationOutcome:
    effective = LayeredResearchLayout.default() if layout is None else layout
    try:
        data = _read_raw(artifact, effective)
        parsed = adapter.normalize(data, content_type=artifact["content_type"])
        sections = []
        for index, section in enumerate(parsed.sections, start=1):
            heading = normalize_text(section.heading) if section.heading is not None else None
            text = normalize_text(section.text)
            core = {"heading": heading, "locator": section.locator, "text": text}
            sections.append(
                {
                    "section_id": f"section:{artifact['evidence_artifact_id']}:{index:04d}",
                    **core,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "section_hash": content_sha256(core),
                }
            )
        document_core = {
            "artifact_id": artifact["evidence_artifact_id"],
            "parser": parsed.parser,
            "parser_version": adapter.version,
            "media_type": parsed.media_type,
            "title": normalize_text(parsed.title) if parsed.title is not None else artifact["source_title"],
            "sections": sections,
            "warnings": [],
            "parsed_at": parsed_at,
            "provenance": deepcopy(provenance),
        }
        document_hash = content_sha256(document_core)
        identity = sha256(
            f"{artifact['evidence_artifact_id']}\n{document_hash}".encode("utf-8")
        ).hexdigest()[:24]
        document = {
            "document_id": f"normalized_document:{identity}",
            **document_core,
            "document_hash": document_hash,
        }
        write_normalized_document(document, layout=effective)
        return NormalizationOutcome(
            status="normalized",
            raw_artifact_id=artifact["evidence_artifact_id"],
            document=document,
            parser=parsed.parser,
            parser_version=adapter.version,
            parser_configuration=deepcopy(adapter.configuration),
            normalized_at=parsed_at,
            failure_code=None,
            diagnostic_summary="Normalization completed.",
        )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except BaseException as exc:
        code = (
            "checksum_failure"
            if isinstance(exc, ResearchProjectV2Error)
            and exc.code == "RESEARCH_PROJECT_V2_1_ACQUISITION_CHECKSUM_FAILURE"
            else "unsupported_format"
        )
        return NormalizationOutcome(
            status="failed",
            raw_artifact_id=artifact["evidence_artifact_id"],
            document=None,
            parser=adapter.name,
            parser_version=adapter.version,
            parser_configuration=deepcopy(adapter.configuration),
            normalized_at=parsed_at,
            failure_code=code,
            diagnostic_summary=f"Normalization failed: {type(exc).__name__}.",
        )


def _checkpoint_identity(core: dict[str, Any]) -> tuple[str, str]:
    digest = content_sha256(core)
    return f"acquisition_checkpoint:{sha256(canonical_bytes(core)).hexdigest()[:24]}", digest


def build_acquisition_checkpoint(
    *,
    project_id: str,
    research_version_context: str,
    created_at: str,
    attempts: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    normalization_outcomes: list[NormalizationOutcome],
    selected_requirement_ids: list[str] | None = None,
    candidate_ids: list[str] | None = None,
    exact_duplicate_results: list[dict[str, Any]] | None = None,
    provenance_completeness: str | None = None,
    security_violations: list[str] | None = None,
    unresolved_issues: list[str] | None = None,
    acquisition_stage: str | None = None,
    requirement_universe_ids: list[str] | None = None,
    primary_source_coverage: list[dict[str, Any]] | None = None,
    source_role_distribution: dict[str, int] | None = None,
    suspected_common_origin_groups: list[dict[str, Any]] | None = None,
    inaccessible_candidate_ids: list[str] | None = None,
    widen_like_redirect_attempt_ids: list[str] | None = None,
    unresolved_engineering_issues: list[str] | None = None,
    unresolved_acquisition_gaps: list[str] | None = None,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    attempt_ids = sorted({row["attempt_id"] for row in attempts})
    raw_ids = sorted({row["evidence_artifact_id"] for row in artifacts})
    normalized_ids = sorted(
        {
            outcome.document["document_id"]
            for outcome in normalization_outcomes
            if outcome.document is not None
        }
    )
    failed_attempts = sorted(
        {row["attempt_id"] for row in attempts if row["status"] in {"failed", "blocked", "unavailable"}}
    )
    successful_attempts = [row for row in attempts if row["status"] == "acquired"]
    blocked_attempts = [row for row in attempts if row["status"] == "blocked"]
    failed_only_attempts = [row for row in attempts if row["status"] == "failed"]
    provider_distribution: dict[str, int] = {}
    failure_distribution: dict[str, int] = {}
    proxy_mode_distribution: dict[str, int] = {}
    for row in attempts:
        provider = row["provider"]
        provider_distribution[provider] = provider_distribution.get(provider, 0) + 1
        failure_code = row.get("failure_code")
        if failure_code is not None:
            failure_distribution[failure_code] = failure_distribution.get(failure_code, 0) + 1
        proxy_mode = row["proxy_mode"]
        proxy_mode_distribution[proxy_mode] = proxy_mode_distribution.get(proxy_mode, 0) + 1
    normalization_records = [
        {
            "raw_artifact_id": outcome.raw_artifact_id,
            "normalized_document_id": (
                outcome.document["document_id"] if outcome.document is not None else None
            ),
            "status": outcome.status,
            "parser": outcome.parser,
            "parser_version": outcome.parser_version,
            "parser_configuration": deepcopy(outcome.parser_configuration),
            "normalized_at": outcome.normalized_at,
            "failure_code": outcome.failure_code,
        }
        for outcome in normalization_outcomes
    ]
    status = "pending_assessment" if raw_ids else "blocked" if failed_attempts else "partial"
    core = {
        "project_id": project_id,
        "research_version_context": research_version_context,
        "created_at": created_at,
        "attempt_ids": attempt_ids,
        "raw_artifact_ids": raw_ids,
        "normalized_document_ids": normalized_ids,
        "pending_assessment_artifact_ids": raw_ids,
        "failed_attempt_ids": failed_attempts,
        "status": status,
        "provenance": deepcopy(provenance),
        "normalization_records": normalization_records,
    }
    if selected_requirement_ids is not None:
        core["selected_requirement_ids"] = sorted(set(selected_requirement_ids))
    if candidate_ids is not None:
        core["candidate_ids"] = sorted(set(candidate_ids))
    core["successful_attempt_count"] = len(successful_attempts)
    core["failed_attempt_count"] = len(failed_attempts)
    core["provider_distribution"] = dict(sorted(provider_distribution.items()))
    core["failure_distribution"] = dict(sorted(failure_distribution.items()))
    if exact_duplicate_results is not None:
        core["exact_duplicate_results"] = deepcopy(exact_duplicate_results)
    if provenance_completeness is not None:
        core["provenance_completeness"] = provenance_completeness
    if security_violations is not None:
        core["security_violations"] = sorted(set(security_violations))
    if unresolved_issues is not None:
        core["unresolved_issues"] = sorted(set(unresolved_issues))
    if acquisition_stage is not None:
        core["acquisition_stage"] = acquisition_stage
    if requirement_universe_ids is not None:
        universe = sorted(set(requirement_universe_ids))
        attempted = sorted(
            {
                row["requirement_id"]
                for row in attempts
                if row.get("requirement_id") in set(universe)
            }
        )
        core["requirement_universe_ids"] = universe
        core["attempted_requirement_ids"] = attempted
        core["unattempted_requirement_ids"] = sorted(set(universe) - set(attempted))
    core["successful_attempt_ids"] = sorted(
        row["attempt_id"] for row in successful_attempts
    )
    core["blocked_attempt_ids"] = sorted(row["attempt_id"] for row in blocked_attempts)
    core["failed_only_attempt_ids"] = sorted(
        row["attempt_id"] for row in failed_only_attempts
    )
    core["normalization_failure_artifact_ids"] = sorted(
        {
            outcome.raw_artifact_id
            for outcome in normalization_outcomes
            if outcome.status == "failed"
        }
    )
    core["proxy_mode_distribution"] = dict(sorted(proxy_mode_distribution.items()))
    core["unknown_publication_date_artifact_ids"] = sorted(
        {
            row["evidence_artifact_id"]
            for row in artifacts
            if row.get("published_at") is None
        }
    )
    core["date_metadata_records"] = [
        {
            "artifact_id": row["evidence_artifact_id"],
            "published_at": row.get("published_at"),
            "updated_at": None,
            "accessed_at": row["accessed_at"],
            "date_status": (
                "unknown" if row.get("published_at") is None else "candidate_reported"
            ),
            "date_source": (
                None if row.get("published_at") is None else "candidate.publish_date"
            ),
            "date_confidence": (
                "unknown" if row.get("published_at") is None else "unreviewed"
            ),
        }
        for row in sorted(artifacts, key=lambda item: item["evidence_artifact_id"])
    ]
    if primary_source_coverage is not None:
        core["primary_source_coverage"] = deepcopy(primary_source_coverage)
    if source_role_distribution is not None:
        core["source_role_distribution"] = dict(sorted(source_role_distribution.items()))
    if suspected_common_origin_groups is not None:
        core["suspected_common_origin_groups"] = deepcopy(
            suspected_common_origin_groups
        )
    if inaccessible_candidate_ids is not None:
        core["inaccessible_candidate_ids"] = sorted(set(inaccessible_candidate_ids))
    if widen_like_redirect_attempt_ids is not None:
        core["widen_like_redirect_attempt_ids"] = sorted(
            set(widen_like_redirect_attempt_ids)
        )
    if unresolved_engineering_issues is not None:
        core["unresolved_engineering_issues"] = sorted(
            set(unresolved_engineering_issues)
        )
    if unresolved_acquisition_gaps is not None:
        core["unresolved_acquisition_gaps"] = sorted(
            set(unresolved_acquisition_gaps)
        )
    checkpoint_id, digest = _checkpoint_identity(core)
    checkpoint = {"checkpoint_id": checkpoint_id, **core, "content_hash": digest}
    validate_acquisition_checkpoint(checkpoint)
    return checkpoint


def validate_acquisition_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(checkpoint)
    validate_v2_1_schema_payload(
        "acquisition_checkpoint_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "acquisition_checkpoint",
            "acquisition_checkpoint": copied,
        },
    )
    core = {
        key: value
        for key, value in copied.items()
        if key not in {"checkpoint_id", "content_hash"}
    }
    expected_id, expected_hash = _checkpoint_identity(core)
    if copied["checkpoint_id"] != expected_id or copied["content_hash"] != expected_hash:
        raise ResearchProjectV2Error(
            "Acquisition checkpoint identity mismatch",
            code="RESEARCH_PROJECT_V2_1_ACQUISITION_IMMUTABILITY_VIOLATION",
            details={"checkpoint_id": copied.get("checkpoint_id")},
        )
    return copied


def write_acquisition_checkpoint(
    checkpoint: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
):
    effective = LayeredResearchLayout.default() if layout is None else layout
    validated = validate_acquisition_checkpoint(checkpoint)
    wrapper = {
        "schema_version": "2.3.0",
        "artifact_kind": "acquisition_checkpoint",
        "acquisition_checkpoint": validated,
    }
    return _publish_bytes(
        effective.acquisition_checkpoints_dir,
        f"{validated['checkpoint_id']}.json",
        canonical_bytes(wrapper),
    )
