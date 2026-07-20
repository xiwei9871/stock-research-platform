from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib.util
import ipaddress
import os
import socket
import ssl
from typing import Any
from urllib.parse import urlsplit
import urllib.request

import requests

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2_1.snapshot import _publish_bytes
from stock_research.research_project_v2_1.acquisition_browser import detect_browser_runtime
from stock_research.research_project_v2_1.acquisition_failures import classify_acquisition_failure


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
    network_statuses: dict[str, str] | None = None,
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
        "dns_status": (network_statuses or {}).get("dns", "unknown"),
        "tls_status": (network_statuses or {}).get("tls", "unknown"),
        "direct_html_status": (network_statuses or {}).get("direct_html", "not_run"),
        "direct_pdf_status": (network_statuses or {}).get("direct_pdf", "not_run"),
        "redirect_status": (network_statuses or {}).get("redirect", "not_run"),
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


def _dns_probe() -> bool:
    addresses = {
        answer[4][0]
        for answer in socket.getaddrinfo(
            "example.com", 443, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    }
    return bool(addresses) and all(ipaddress.ip_address(value).is_global for value in addresses)


def _tls_probe() -> bool:
    context = ssl.create_default_context()
    with socket.create_connection(("example.com", 443), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname="example.com") as secured:
            return bool(secured.version())


def _http_probe(url: str, expected_type: str, *, redirect: bool = False) -> bool:
    session = requests.Session()
    session.trust_env = False
    response = session.get(url, timeout=8, allow_redirects=True, stream=True)
    try:
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        return (
            response.status_code == 200
            and content_type == expected_type
            and (not redirect or bool(response.history))
        )
    finally:
        response.close()
        session.close()


def run_provider_doctor(
    *,
    generated_at: str,
    provenance: dict[str, Any],
    online: bool,
    environment: dict[str, str] | None = None,
    system_proxies: dict[str, str] | None = None,
    probes: dict[str, Any] | None = None,
    browser_probe=None,
) -> dict[str, Any]:
    runtime = detect_browser_runtime(probe=browser_probe)
    if not online:
        return build_provider_diagnostic(
            generated_at=generated_at,
            provenance=provenance,
            environment=environment,
            system_proxies=system_proxies,
            browser_runtime_status="available" if runtime.available else "unavailable",
            search_provider_status="unavailable",
            checks=[],
        )
    effective_probes = probes or {
        "dns": _dns_probe,
        "tls": _tls_probe,
        "direct_html": lambda: _http_probe("https://example.com/", "text/html"),
        "direct_pdf": lambda: _http_probe(
            "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
            "application/pdf",
        ),
        "redirect": lambda: _http_probe(
            "https://httpbingo.org/redirect/1", "application/json", redirect=True
        ),
    }
    statuses: dict[str, str] = {}
    checks: list[dict[str, Any]] = []
    for check_id in ("dns", "tls", "direct_html", "direct_pdf", "redirect"):
        try:
            passed = bool(effective_probes[check_id]())
            status = "pass" if passed else "fail"
            failure_code = None if passed else "unknown_failure"
            summary = f"{check_id} diagnostic {'passed' if passed else 'failed'}."
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except BaseException as exc:
            classified = classify_acquisition_failure(exc)
            status = "fail"
            failure_code = classified.failure_code
            summary = classified.diagnostic_summary
        statuses[check_id] = status
        checks.append(
            {
                "check_id": check_id,
                "status": status,
                "failure_code": failure_code,
                "summary": summary,
            }
        )
    return build_provider_diagnostic(
        generated_at=generated_at,
        provenance=provenance,
        environment=environment,
        system_proxies=system_proxies,
        browser_runtime_status="available" if runtime.available else "unavailable",
        search_provider_status="unavailable",
        checks=checks,
        network_statuses=statuses,
    )


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
