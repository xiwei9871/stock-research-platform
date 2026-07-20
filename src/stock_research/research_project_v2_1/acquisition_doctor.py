from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib.util
import ipaddress
import os
from typing import Any
from urllib.parse import urlsplit
import urllib.request

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2_1.snapshot import _publish_bytes


_PROXY_KEYS = {
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
}


def _proxy_endpoint(value: str) -> tuple[str, str | None]:
    parsed = urlsplit(value if "://" in value else f"http://{value}")
    host = parsed.hostname
    if host is None:
        return "unknown", "unknown-proxy"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        endpoint_class = "unknown"
    else:
        endpoint_class = "private" if not address.is_global else "public"
    port = str(parsed.port) if parsed.port is not None else ""
    redacted_port = f"{port[:-1]}x" if port else "default"
    return endpoint_class, f"{endpoint_class}-proxy:{redacted_port}"


def _normalizers() -> list[str]:
    values = ["html", "pypdf"]
    if importlib.util.find_spec("docling") is not None:
        values.append("docling")
    return values


def build_provider_diagnostic(
    *,
    generated_at: str,
    provenance: dict[str, Any],
    environment: dict[str, str] | None = None,
    system_proxies: dict[str, str] | None = None,
    browser_runtime_status: str = "not_tested",
    search_provider_status: str = "unavailable",
    checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if environment is None else environment)
    system = dict(urllib.request.getproxies() if system_proxies is None else system_proxies)
    environment_values = [env[key] for key in _PROXY_KEYS if key in env and env[key]]
    system_values = [value for value in system.values() if value]
    classes: list[str] = []
    redacted: list[str] = []
    for value in [*environment_values, *system_values]:
        endpoint_class, endpoint = _proxy_endpoint(value)
        classes.append(endpoint_class)
        if endpoint is not None:
            redacted.append(endpoint)
    proxy_class = (
        "none"
        if not classes
        else classes[0]
        if len(set(classes)) == 1
        else "mixed"
    )
    core = {
        "generated_at": generated_at,
        "dns_status": "unknown",
        "tls_status": "unknown",
        "direct_html_status": "not_run",
        "direct_pdf_status": "not_run",
        "redirect_status": "not_run",
        "system_proxy_detected": bool(system_values),
        "environment_proxy_detected": bool(environment_values),
        "proxy_endpoint_class": proxy_class,
        "proxy_endpoint_redacted": sorted(set(redacted))[0] if redacted else None,
        "requests_trust_mode": "explicit_direct",
        "browser_runtime_status": browser_runtime_status,
        "search_provider_status": search_provider_status,
        "available_normalizers": _normalizers(),
        "security_policy_status": "enforced",
        "checks": deepcopy(checks or []),
        "provenance": deepcopy(provenance),
    }
    digest = content_sha256(core)
    diagnostic = {
        "diagnostic_id": f"provider_diagnostic:{sha256(canonical_bytes(core)).hexdigest()[:24]}",
        **core,
        "content_hash": digest,
    }
    validate_provider_diagnostic(diagnostic)
    return diagnostic


def validate_provider_diagnostic(diagnostic: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(diagnostic)
    validate_v2_1_schema_payload(
        "provider_diagnostic_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "provider_diagnostic",
            "provider_diagnostic": copied,
        },
    )
    core = {
        key: value
        for key, value in copied.items()
        if key not in {"diagnostic_id", "content_hash"}
    }
    expected_id = f"provider_diagnostic:{sha256(canonical_bytes(core)).hexdigest()[:24]}"
    if copied["diagnostic_id"] != expected_id or copied["content_hash"] != content_sha256(core):
        raise ResearchProjectV2Error(
            "Provider diagnostic identity mismatch",
            code="RESEARCH_PROJECT_V2_1_ACQUISITION_IMMUTABILITY_VIOLATION",
            details={"diagnostic_id": copied.get("diagnostic_id")},
        )
    return copied


def write_provider_diagnostic(
    diagnostic: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
):
    effective = LayeredResearchLayout.default() if layout is None else layout
    validated = validate_provider_diagnostic(diagnostic)
    wrapper = {
        "schema_version": "2.3.0",
        "artifact_kind": "provider_diagnostic",
        "provider_diagnostic": validated,
    }
    return _publish_bytes(
        effective.acquisition_diagnostics_dir,
        f"{validated['diagnostic_id']}.json",
        canonical_bytes(wrapper),
    )
