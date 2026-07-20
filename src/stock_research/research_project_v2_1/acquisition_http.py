from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Callable
from urllib.parse import urlsplit

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.acquisition_contracts import (
    AcquisitionContext,
    AcquisitionProviderResult,
    build_acquisition_attempt,
)
from stock_research.research_project_v2_1.acquisition_failures import classify_acquisition_failure
from stock_research.research_project_v2_1.acquisition_storage import (
    evidence_artifact_id,
    write_acquisition_attempt,
    write_v2_3_evidence_artifact,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.snapshot import (
    AddressResolver,
    FetchTransport,
    RequestsFetchTransport,
    SystemAddressResolver,
    snapshot_candidate,
)


_Now = Callable[[], str]
_MonotonicMs = Callable[[], int]
_SNAPSHOT_CANDIDATE_FIELDS = (
    "candidate_id", "search_plan_id", "query_id", "normalized_url", "original_url",
    "title", "snippet", "publisher", "publish_date", "source_class", "rank",
    "exclusion_status", "exclusion_reasons", "dedup_key", "provenance",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _published_at(candidate: dict[str, Any]) -> str | None:
    value = candidate.get("publish_date")
    return f"{value}T00:00:00Z" if isinstance(value, str) and value else None


def _security_details(error: BaseException, requested_url: str, proxy_mode: str) -> dict[str, Any] | None:
    if not isinstance(error, ResearchProjectV2Error) or classify_acquisition_failure(error).failure_code != "security_policy_blocked":
        return None
    host = urlsplit(requested_url).hostname or "unknown"
    stage = "redirect_validation" if "REDIRECT" in error.code else "peer_validation"
    return {
        "policy_name": "public_network_only",
        "policy_stage": stage,
        "target_host": host,
        "resolved_address_class": "unknown",
        "peer_address_class": "private" if "PEER" in error.code else "unknown",
        "redirect_hop": int(error.details.get("redirect_hop", 0) or 0),
        "proxy_mode": proxy_mode,
        "blocked_reason": str(error),
    }


class DirectHttpProvider:
    def __init__(
        self,
        *,
        transport: FetchTransport | None = None,
        resolver: AddressResolver | None = None,
        now: _Now = _utc_now,
        monotonic_ms: _MonotonicMs | None = None,
        sleep: Callable[[float], None] = time.sleep,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.transport = transport
        self.resolver = resolver or SystemAddressResolver()
        self.now = now
        self.monotonic_ms = monotonic_ms or (lambda: int(time.monotonic() * 1000))
        self.sleep = sleep
        self.headers = dict(headers or {})

    def acquire(
        self,
        candidate: dict[str, Any],
        *,
        context: AcquisitionContext,
        layout: LayeredResearchLayout | None = None,
        attempted_at: str | None = None,
        proxy_mode: str = "direct",
        timeout_seconds: float = 20.0,
        max_redirects: int = 5,
        max_bytes: int = 25 * 1024 * 1024,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
    ) -> AcquisitionProviderResult:
        if proxy_mode not in {"direct", "environment_proxy", "explicit_proxy"}:
            raise ResearchProjectV2Error(
                "Proxy mode is not enabled for direct acquisition",
                code="RESEARCH_PROJECT_V2_1_ACQUISITION_PROXY_MODE_BLOCKED",
                details={"proxy_mode": proxy_mode},
            )
        if max_retries < 0 or max_retries > 5:
            raise ResearchProjectV2Error(
                "max_retries must be between zero and five",
                code="RESEARCH_PROJECT_V2_1_ACQUISITION_INVALID",
                details={"max_retries": max_retries},
            )
        effective_layout = LayeredResearchLayout.default() if layout is None else layout
        operation_started = attempted_at or self.now()
        started_ms = self.monotonic_ms()
        requested_url = candidate.get("normalized_url")
        parsed_url = urlsplit(requested_url)
        effective_port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
        blocked_stage = None
        blocked_reason = None
        if proxy_mode != "direct":
            blocked_stage = "proxy_selection"
            blocked_reason = "trusted proxy allowlist is not implemented"
        elif effective_port not in {80, 443}:
            blocked_stage = "url_validation"
            blocked_reason = "non-standard destination port is not allowed"
        if blocked_stage is not None:
            completed_at = self.now()
            built = build_acquisition_attempt(
                context=context,
                provider="direct_http",
                request_mode="fetch",
                proxy_mode=proxy_mode,
                requested_url=requested_url,
                resolved_url=None,
                attempted_at=operation_started,
                completed_at=completed_at,
                elapsed_ms=max(0, self.monotonic_ms() - started_ms),
                status="blocked",
                failure_code="security_policy_blocked",
                http_status=None,
                redirect_chain=[],
                content_type=None,
                bytes_received=0,
                retry_count=0,
                raw_artifact_id=None,
                diagnostic_summary="Acquisition was blocked by the local security policy.",
                failure_details={
                    "policy_name": "trusted_proxy_required" if proxy_mode != "direct" else "standard_web_ports_only",
                    "policy_stage": blocked_stage,
                    "target_host": urlsplit(requested_url).hostname or "unknown",
                    "resolved_address_class": "unknown",
                    "peer_address_class": "unknown",
                    "redirect_hop": 0,
                    "proxy_mode": proxy_mode,
                    "blocked_reason": blocked_reason,
                },
            )
            write_acquisition_attempt(built.payload, layout=effective_layout)
            return AcquisitionProviderResult(attempt=built.payload, artifact=None)
        transport = self.transport or RequestsFetchTransport(
            proxy_mode=proxy_mode, headers=self.headers
        )
        error: BaseException | None = None
        fetched: dict[str, Any] | None = None
        retry_count = 0
        snapshot_input = {
            field: deepcopy(candidate[field]) for field in _SNAPSHOT_CANDIDATE_FIELDS
        }
        for attempt_index in range(max_retries + 1):
            try:
                fetched = snapshot_candidate(
                    snapshot_input,
                    transport=transport,
                    resolver=self.resolver,
                    layout=effective_layout,
                    fetched_at=operation_started,
                    provenance=context.provenance,
                    timeout_seconds=timeout_seconds,
                    max_redirects=max_redirects,
                    max_bytes=max_bytes,
                )
                retry_count = attempt_index
                break
            except (KeyboardInterrupt, SystemExit, MemoryError):
                raise
            except BaseException as exc:
                error = exc
                retry_count = attempt_index
                if attempt_index >= max_retries:
                    break
                self.sleep(retry_backoff_seconds * (2**attempt_index))

        completed_at = self.now()
        elapsed_ms = max(0, self.monotonic_ms() - started_ms)
        if fetched is None:
            http_status = None
            if isinstance(error, ResearchProjectV2Error):
                raw_status = error.details.get("status_code")
                http_status = raw_status if isinstance(raw_status, int) else None
            classified = classify_acquisition_failure(error, http_status=http_status)
            built = build_acquisition_attempt(
                context=context,
                provider="direct_http",
                request_mode="fetch",
                proxy_mode=proxy_mode,
                requested_url=requested_url,
                resolved_url=None,
                attempted_at=operation_started,
                completed_at=completed_at,
                elapsed_ms=elapsed_ms,
                status=classified.result_status,
                failure_code=classified.failure_code,
                http_status=http_status,
                redirect_chain=[],
                content_type=None,
                bytes_received=0,
                retry_count=retry_count,
                raw_artifact_id=None,
                diagnostic_summary=classified.diagnostic_summary,
                failure_details=_security_details(error, requested_url, proxy_mode) if error else None,
            )
            write_acquisition_attempt(built.payload, layout=effective_layout)
            return AcquisitionProviderResult(attempt=built.payload, artifact=None)

        legacy = fetched["artifact"]
        artifact_seed = {
            "source_candidate_id": candidate.get("candidate_id"),
            "source_url": candidate.get("original_url"),
            "resolved_url": legacy["final_url"],
            "source_title": candidate.get("title"),
            "publisher": candidate.get("publisher"),
            "published_at": _published_at(candidate),
            "content_type": legacy["media_type"],
            "byte_size": legacy["byte_count"],
            "content_hash": legacy["content_sha256"],
            "raw_artifact_path": legacy["raw_path"],
        }
        artifact_id = evidence_artifact_id(artifact_seed)
        built = build_acquisition_attempt(
            context=context,
            provider="direct_http",
            request_mode="fetch",
            proxy_mode=proxy_mode,
            requested_url=requested_url,
            resolved_url=legacy["final_url"],
            attempted_at=operation_started,
            completed_at=completed_at,
            elapsed_ms=elapsed_ms,
            status="acquired",
            failure_code=None,
            http_status=legacy["status_code"],
            redirect_chain=legacy["redirect_chain"],
            content_type=legacy["media_type"],
            bytes_received=legacy["byte_count"],
            retry_count=retry_count,
            raw_artifact_id=artifact_id,
            diagnostic_summary="Direct HTTP acquisition completed.",
        )
        artifact = {
            "evidence_artifact_id": artifact_id,
            "acquisition_attempt_id": built.payload["attempt_id"],
            **artifact_seed,
            "accessed_at": completed_at,
            "normalized_artifact_ids": [],
            "provenance": deepcopy(context.provenance),
            "access_status": "acquired",
            "license_or_access_note": "Accessed from the supplied public source URL; license not independently assessed.",
        }
        write_acquisition_attempt(built.payload, layout=effective_layout)
        write_v2_3_evidence_artifact(artifact, layout=effective_layout)
        return AcquisitionProviderResult(attempt=built.payload, artifact=artifact)
