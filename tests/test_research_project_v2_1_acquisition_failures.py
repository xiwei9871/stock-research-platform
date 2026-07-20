from __future__ import annotations

import requests

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.acquisition_failures import (
    FAILURE_CODES,
    classify_acquisition_failure,
)


def test_failure_taxonomy_contains_all_approved_codes() -> None:
    assert {
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
    } <= FAILURE_CODES


def test_failure_classifier_distinguishes_network_http_and_policy_failures() -> None:
    assert classify_acquisition_failure(requests.Timeout()).failure_code == "connection_timeout"
    assert (
        classify_acquisition_failure(
            ResearchProjectV2Error(
                "blocked",
                code="RESEARCH_PROJECT_V2_1_FETCH_PEER_DENIED",
                details={},
            )
        ).failure_code
        == "security_policy_blocked"
    )
    assert classify_acquisition_failure(None, http_status=429).failure_code == "rate_limited"
    assert classify_acquisition_failure(None, http_status=404).failure_code == "http_error"


def test_failure_classifier_does_not_guess_auth_or_paywall_from_plain_403() -> None:
    classified = classify_acquisition_failure(None, http_status=403)
    assert classified.failure_code == "http_error"
    assert classified.result_status == "failed"
