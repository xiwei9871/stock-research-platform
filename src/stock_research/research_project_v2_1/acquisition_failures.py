from __future__ import annotations

from dataclasses import dataclass
import errno
from typing import Any

import requests

from stock_research.research_project_v2.errors import ResearchProjectV2Error


FAILURE_CODES = frozenset(
    {
        "dns_failure",
        "connection_refused",
        "connection_timeout",
        "proxy_unreachable",
        "proxy_auth_required",
        "tls_failure",
        "http_error",
        "rate_limited",
        "search_provider_error",
        "search_auth_error",
        "search_quota_exceeded",
        "robots_disallowed",
        "login_required",
        "paywalled",
        "browser_runtime_unavailable",
        "javascript_required",
        "invalid_mime_type",
        "empty_content",
        "checksum_failure",
        "unsupported_format",
        "manually_unavailable",
        "security_policy_blocked",
        "unknown_failure",
    }
)


@dataclass(frozen=True)
class FailureClassification:
    failure_code: str
    result_status: str
    diagnostic_summary: str


_SECURITY_CODES = {
    "RESEARCH_PROJECT_V2_1_FETCH_DNS_DENIED",
    "RESEARCH_PROJECT_V2_1_FETCH_PEER_DENIED",
    "RESEARCH_PROJECT_V2_1_FETCH_PEER_MISMATCH",
    "RESEARCH_PROJECT_V2_1_FETCH_REDIRECT_INVALID",
    "RESEARCH_PROJECT_V2_1_FETCH_REDIRECT_LOOP",
    "RESEARCH_PROJECT_V2_1_FETCH_REDIRECT_LIMIT",
}


def _classification(code: str, summary: str, *, blocked: bool = False) -> FailureClassification:
    return FailureClassification(code, "blocked" if blocked else "failed", summary)


def classify_acquisition_failure(
    error: BaseException | None,
    *,
    http_status: int | None = None,
    provider: str | None = None,
) -> FailureClassification:
    """Map provider errors to the stable acquisition failure taxonomy."""
    if http_status == 407:
        return _classification("proxy_auth_required", "Proxy authentication is required.")
    if http_status == 429:
        return _classification("rate_limited", "The provider rate limited the request.")
    if http_status is not None and not 200 <= http_status <= 299:
        return _classification("http_error", f"HTTP request failed with status {http_status}.")

    cause = getattr(error, "__cause__", None)
    if cause is not None and cause is not error:
        nested = classify_acquisition_failure(cause, provider=provider)
        if nested.failure_code != "unknown_failure":
            return nested

    if isinstance(error, ResearchProjectV2Error):
        code = error.code
        if code in _SECURITY_CODES:
            return _classification("security_policy_blocked", str(error), blocked=True)
        if code.startswith("RESEARCH_PROJECT_V2_1_FETCH_DNS_"):
            return _classification("dns_failure", str(error))
        if code in {
            "RESEARCH_PROJECT_V2_1_FETCH_MEDIA_TYPE_INVALID",
            "RESEARCH_PROJECT_V2_1_FETCH_MEDIA_TYPE_UNSUPPORTED",
        }:
            return _classification("invalid_mime_type", str(error))
        if code == "RESEARCH_PROJECT_V2_1_FETCH_TOO_LARGE":
            return _classification("unsupported_format", str(error))
        if code == "RESEARCH_PROJECT_V2_1_DISCOVERY_PROVIDER_FAILED":
            return _classification("search_provider_error", str(error))

    if isinstance(error, requests.exceptions.ProxyError):
        return _classification("proxy_unreachable", "The configured proxy was unreachable.")
    if isinstance(error, requests.exceptions.SSLError):
        return _classification("tls_failure", "TLS negotiation or verification failed.")
    if isinstance(error, requests.exceptions.Timeout):
        return _classification("connection_timeout", "The connection timed out.")
    if isinstance(error, requests.exceptions.ConnectionError):
        cause: Any = error
        while getattr(cause, "__cause__", None) is not None:
            cause = cause.__cause__
        if getattr(cause, "errno", None) == errno.ECONNREFUSED:
            return _classification("connection_refused", "The connection was refused.")
        return _classification("unknown_failure", "The connection failed.")

    if provider == "browser" and error is not None:
        return _classification("browser_runtime_unavailable", "Browser runtime is unavailable.")
    return _classification(
        "unknown_failure",
        "Acquisition failed without a more specific classified cause.",
    )
