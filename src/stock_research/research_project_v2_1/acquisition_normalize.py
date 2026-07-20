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
