from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import time
from typing import Any, Callable

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.acquisition_contracts import (
    AcquisitionContext,
    AcquisitionProviderResult,
    build_acquisition_attempt,
)
from stock_research.research_project_v2_1.acquisition_storage import (
    evidence_artifact_id,
    publish_raw_bytes,
    write_acquisition_attempt,
    write_v2_3_evidence_artifact,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2_1.snapshot import _publish_bytes


_SUPPORTED = {
    "application/pdf",
    "text/html",
    "text/plain",
    "text/markdown",
    "application/json",
    "text/csv",
    "application/vnd.docling+json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_identity(core: dict[str, Any]) -> tuple[str, str]:
    digest = content_sha256(core)
    return f"manual_import_request:{sha256(canonical_bytes(core)).hexdigest()[:24]}", digest


def build_manual_import_request(
    *,
    project_id: str,
    research_version_context: str,
    requirement_id: str | None,
    candidate_id: str | None,
    local_path: str,
    source_title: str,
    publisher: str | None,
    original_url: str | None,
    source_note: str | None,
    publication_date: str | None,
    imported_at: str,
    imported_by: str,
    actor_type: str,
    declared_mime_type: str,
    access_or_license_note: str,
    locator_metadata: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    complete = bool(publisher and (original_url or source_note) and publication_date)
    core = {
        "project_id": project_id,
        "research_version_context": research_version_context,
        "requirement_id": requirement_id,
        "candidate_id": candidate_id,
        "local_path": local_path,
        "source_title": source_title,
        "publisher": publisher,
        "original_url": original_url,
        "source_note": source_note,
        "publication_date": publication_date,
        "imported_at": imported_at,
        "imported_by": imported_by,
        "actor_type": actor_type,
        "declared_mime_type": declared_mime_type,
        "access_or_license_note": access_or_license_note,
        "locator_metadata": deepcopy(locator_metadata),
        "metadata_status": "complete" if complete else "incomplete_metadata",
        "provenance": deepcopy(provenance),
    }
    request_id, digest = _request_identity(core)
    payload = {"import_request_id": request_id, **core, "content_hash": digest}
    validate_manual_import_request(payload)
    return payload


def validate_manual_import_request(payload: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(payload)
    validate_v2_1_schema_payload(
        "manual_import_request_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "manual_import_request",
            "manual_import_request": copied,
        },
    )
    core = {
        key: value
        for key, value in copied.items()
        if key not in {"import_request_id", "content_hash"}
    }
    expected_id, expected_hash = _request_identity(core)
    if copied["import_request_id"] != expected_id or copied["content_hash"] != expected_hash:
        raise ResearchProjectV2Error(
            "Manual import request identity mismatch",
            code="RESEARCH_PROJECT_V2_1_ACQUISITION_IMMUTABILITY_VIOLATION",
            details={"import_request_id": copied.get("import_request_id")},
        )
    return copied


def _validate_content(data: bytes, mime_type: str) -> bool:
    if mime_type == "application/pdf":
        return data.startswith(b"%PDF-")
    if mime_type == "text/html":
        try:
            text = data.decode("utf-8", errors="strict").lstrip().casefold()
        except UnicodeError:
            return False
        return text.startswith("<!doctype html") or text.startswith("<html")
    if mime_type in {"text/plain", "text/markdown"}:
        try:
            data.decode("utf-8", errors="strict")
        except UnicodeError:
            return False
        return True
    if mime_type in {"application/json", "application/vnd.docling+json"}:
        try:
            json.loads(data.decode("utf-8", errors="strict"))
        except (UnicodeError, json.JSONDecodeError):
            return False
        return True
    if mime_type == "text/csv":
        try:
            rows = list(csv.reader(io.StringIO(data.decode("utf-8", errors="strict"))))
        except (UnicodeError, csv.Error):
            return False
        return bool(rows)
    return False


class LocalFileProvider:
    def __init__(
        self,
        *,
        now: Callable[[], str] = _utc_now,
        monotonic_ms: Callable[[], int] | None = None,
    ) -> None:
        self.now = now
        self.monotonic_ms = monotonic_ms or (lambda: int(time.monotonic() * 1000))

    def acquire(
        self,
        import_request: dict[str, Any],
        *,
        layout: LayeredResearchLayout | None = None,
        max_bytes: int = 25 * 1024 * 1024,
    ) -> AcquisitionProviderResult:
        effective = LayeredResearchLayout.default() if layout is None else layout
        request = validate_manual_import_request(import_request)
        wrapper = {
            "schema_version": "2.3.0",
            "artifact_kind": "manual_import_request",
            "manual_import_request": request,
        }
        _publish_bytes(
            effective.acquisition_import_requests_dir,
            f"{request['import_request_id']}.json",
            canonical_bytes(wrapper),
        )
        context = AcquisitionContext(
            project_id=request["project_id"],
            research_version_context=request["research_version_context"],
            requirement_id=request["requirement_id"],
            candidate_id=request["candidate_id"],
            provenance=request["provenance"],
        )
        started = request["imported_at"]
        started_ms = self.monotonic_ms()
        source = Path(request["local_path"])
        failure_code: str | None = None
        summary = "Local import completed."
        data: bytes | None = None
        if source.is_symlink():
            failure_code = "security_policy_blocked"
            summary = "Symlink inputs are not accepted by the local import provider."
        elif not source.is_file():
            failure_code = "manually_unavailable"
            summary = "The local import file is unavailable."
        elif request["declared_mime_type"] not in _SUPPORTED:
            failure_code = "unsupported_format"
            summary = "The declared local import format is unsupported."
        else:
            try:
                with source.open("rb") as handle:
                    data = handle.read(max_bytes + 1)
            except OSError:
                failure_code = "manually_unavailable"
                summary = "The local import file could not be read."
            if data is not None and len(data) > max_bytes:
                failure_code = "unsupported_format"
                summary = "The local import file exceeds the maximum size."
                data = None
            if data is not None and not _validate_content(data, request["declared_mime_type"]):
                failure_code = "invalid_mime_type"
                summary = "The local file content does not match the declared MIME type."
                data = None

        completed = self.now()
        elapsed = max(0, self.monotonic_ms() - started_ms)
        if data is None:
            failure_details = None
            status = "failed"
            if failure_code == "security_policy_blocked":
                status = "blocked"
                failure_details = {
                    "policy_name": "local_regular_file_only",
                    "policy_stage": "local_path_validation",
                    "target_host": "local_file",
                    "resolved_address_class": "unknown",
                    "peer_address_class": "unknown",
                    "redirect_hop": 0,
                    "proxy_mode": "local_file",
                    "blocked_reason": summary,
                }
            built = build_acquisition_attempt(
                context=context,
                provider="local_file",
                request_mode="import",
                proxy_mode="local_file",
                requested_url=request["original_url"],
                resolved_url=None,
                attempted_at=started,
                completed_at=completed,
                elapsed_ms=elapsed,
                status=status,
                failure_code=failure_code,
                http_status=None,
                redirect_chain=[],
                content_type=request["declared_mime_type"],
                bytes_received=0,
                retry_count=0,
                raw_artifact_id=None,
                diagnostic_summary=summary,
                failure_details=failure_details,
            )
            write_acquisition_attempt(built.payload, layout=effective)
            return AcquisitionProviderResult(attempt=built.payload, artifact=None)

        raw = publish_raw_bytes(
            data, content_type=request["declared_mime_type"], layout=effective
        )
        published_at = (
            f"{request['publication_date']}T00:00:00Z"
            if request["publication_date"]
            else None
        )
        artifact_seed = {
            "source_candidate_id": request["candidate_id"],
            "source_url": request["original_url"],
            "resolved_url": request["original_url"],
            "source_title": request["source_title"],
            "publisher": request["publisher"],
            "published_at": published_at,
            "content_type": raw.content_type,
            "byte_size": raw.byte_size,
            "content_hash": raw.content_hash,
            "raw_artifact_path": raw.relative_path,
        }
        artifact_id = evidence_artifact_id(artifact_seed)
        built = build_acquisition_attempt(
            context=context,
            provider="local_file",
            request_mode="import",
            proxy_mode="local_file",
            requested_url=request["original_url"],
            resolved_url=request["original_url"],
            attempted_at=started,
            completed_at=completed,
            elapsed_ms=elapsed,
            status="acquired",
            failure_code=None,
            http_status=None,
            redirect_chain=[],
            content_type=raw.content_type,
            bytes_received=raw.byte_size,
            retry_count=0,
            raw_artifact_id=artifact_id,
            diagnostic_summary=summary,
        )
        artifact = {
            "evidence_artifact_id": artifact_id,
            "acquisition_attempt_id": built.payload["attempt_id"],
            **artifact_seed,
            "accessed_at": completed,
            "normalized_artifact_ids": [],
            "provenance": deepcopy(request["provenance"]),
            "access_status": (
                "acquired"
                if request["metadata_status"] == "complete"
                else "incomplete_metadata"
            ),
            "license_or_access_note": request["access_or_license_note"],
        }
        write_acquisition_attempt(built.payload, layout=effective)
        write_v2_3_evidence_artifact(artifact, layout=effective)
        return AcquisitionProviderResult(attempt=built.payload, artifact=artifact)
