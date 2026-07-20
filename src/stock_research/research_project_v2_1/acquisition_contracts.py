from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2.errors import ResearchProjectV2Error


@dataclass(frozen=True)
class AcquisitionContext:
    project_id: str
    research_version_context: str
    requirement_id: str | None
    candidate_id: str | None
    provenance: dict[str, Any]


@dataclass(frozen=True)
class BuiltAcquisitionAttempt:
    payload: dict[str, Any]
    build_args: dict[str, Any]


@dataclass(frozen=True)
class AcquisitionProviderResult:
    attempt: dict[str, Any]
    artifact: dict[str, Any] | None
    normalized_document: dict[str, Any] | None = None


class AcquisitionProvider(Protocol):
    def acquire(self, *args: Any, **kwargs: Any) -> AcquisitionProviderResult: ...


class UnavailableSearchDiscoveryProvider:
    """Explicit unavailable adapter; it never fabricates discovery candidates."""

    status = "unavailable"
    failure_code = "search_provider_error"

    def search(self, query: dict[str, Any]) -> list[Any]:
        raise ResearchProjectV2Error(
            "Search discovery provider is unavailable",
            code="RESEARCH_PROJECT_V2_1_ACQUISITION_PROVIDER_UNAVAILABLE",
            details={
                "provider": "search_discovery",
                "query_id": query.get("query_id"),
                "failure_code": self.failure_code,
            },
        )


def _attempt_identity(core: dict[str, Any]) -> tuple[str, str]:
    digest = content_sha256(core)
    identity = sha256(canonical_bytes(core)).hexdigest()[:24]
    return f"acquisition_attempt:{identity}", digest


def build_acquisition_attempt(
    *,
    context: AcquisitionContext,
    provider: str,
    request_mode: str,
    proxy_mode: str,
    requested_url: str | None,
    resolved_url: str | None,
    attempted_at: str,
    completed_at: str,
    elapsed_ms: int,
    status: str,
    failure_code: str | None,
    http_status: int | None,
    redirect_chain: list[str],
    content_type: str | None,
    bytes_received: int,
    retry_count: int,
    raw_artifact_id: str | None,
    diagnostic_summary: str,
    failure_details: dict[str, Any] | None = None,
) -> BuiltAcquisitionAttempt:
    build_args = {
        "context": context,
        "provider": provider,
        "request_mode": request_mode,
        "proxy_mode": proxy_mode,
        "requested_url": requested_url,
        "resolved_url": resolved_url,
        "attempted_at": attempted_at,
        "completed_at": completed_at,
        "elapsed_ms": elapsed_ms,
        "status": status,
        "failure_code": failure_code,
        "http_status": http_status,
        "redirect_chain": list(redirect_chain),
        "content_type": content_type,
        "bytes_received": bytes_received,
        "retry_count": retry_count,
        "raw_artifact_id": raw_artifact_id,
        "diagnostic_summary": diagnostic_summary,
        "failure_details": deepcopy(failure_details),
    }
    core = {
        "project_id": context.project_id,
        "research_version_context": context.research_version_context,
        "requirement_id": context.requirement_id,
        "candidate_id": context.candidate_id,
        "provider": provider,
        "request_mode": request_mode,
        "proxy_mode": proxy_mode,
        "requested_url": requested_url,
        "resolved_url": resolved_url,
        "attempted_at": attempted_at,
        "completed_at": completed_at,
        "elapsed_ms": elapsed_ms,
        "status": status,
        "failure_code": failure_code,
        "http_status": http_status,
        "redirect_chain": list(redirect_chain),
        "content_type": content_type,
        "bytes_received": bytes_received,
        "retry_count": retry_count,
        "raw_artifact_id": raw_artifact_id,
        "diagnostic_summary": diagnostic_summary,
        "failure_details": deepcopy(failure_details),
        "provenance": deepcopy(context.provenance),
    }
    attempt_id, digest = _attempt_identity(core)
    payload = {"attempt_id": attempt_id, **core, "content_hash": digest}
    validate_v2_1_schema_payload(
        "acquisition_attempt_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "acquisition_attempt",
            "acquisition_attempt": payload,
        },
    )
    return BuiltAcquisitionAttempt(payload=payload, build_args=build_args)


def validate_acquisition_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(payload)
    validate_v2_1_schema_payload(
        "acquisition_attempt_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "acquisition_attempt",
            "acquisition_attempt": copied,
        },
    )
    core = {
        key: value
        for key, value in copied.items()
        if key not in {"attempt_id", "content_hash"}
    }
    expected_id, expected_hash = _attempt_identity(core)
    if copied["attempt_id"] != expected_id or copied["content_hash"] != expected_hash:
        raise ResearchProjectV2Error(
            "Acquisition attempt identity mismatch",
            code="RESEARCH_PROJECT_V2_1_ACQUISITION_IMMUTABILITY_VIOLATION",
            details={"attempt_id": copied.get("attempt_id")},
        )
    return copied
