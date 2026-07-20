from __future__ import annotations

from pathlib import Path

import requests

from stock_research.research_project_v2_1.acquisition_contracts import AcquisitionContext
from stock_research.research_project_v2_1.acquisition_http import DirectHttpProvider
from stock_research.research_project_v2_1.acquisition_storage import read_acquisition_attempt
from stock_research.research_project_v2_1.discovery import normalize_url, source_candidate_id
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.snapshot import FetchResponse, RequestsFetchTransport


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "run:http-provider-test",
    "created_at": "2026-07-20T08:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "unreviewed",
}


class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        return ("93.184.216.34",)


class SequenceTransport:
    def __init__(self, events):
        self.events = list(events)
        self.calls = 0

    def get(self, url: str, *, timeout_seconds: float) -> FetchResponse:
        self.calls += 1
        event = self.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event


def candidate() -> dict:
    url = normalize_url("https://example.com/source.pdf")
    title = "Official Architecture PDF"
    return {
        "candidate_id": source_candidate_id(url, title),
        "search_plan_id": "search_plan:r2b_er01",
        "query_id": "query:r2b_er01:architecture",
        "normalized_url": url,
        "original_url": url,
        "title": title,
        "snippet": "",
        "publisher": "Example Standards Body",
        "publish_date": "2026-07-01",
        "source_class": "technical_standard",
        "rank": 1,
        "exclusion_status": "included",
        "exclusion_reasons": [],
        "dedup_key": url,
        "provenance": PROVENANCE,
    }


def context() -> AcquisitionContext:
    return AcquisitionContext(
        project_id="research_project:ai_compute_pcb_industry_bottleneck",
        research_version_context="research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        requirement_id="requirement:ai_compute_pcb_industry_bottleneck:r2b_er01",
        candidate_id=candidate()["candidate_id"],
        provenance=PROVENANCE,
    )


def response(body: bytes = b"%PDF-1.4\nfixture") -> FetchResponse:
    return FetchResponse(
        status_code=200,
        headers={"Content-Type": "application/pdf", "Content-Length": str(len(body))},
        chunks=[body],
        url="https://example.com/source.pdf",
        peer_ip="93.184.216.34",
    )


def error_response(status_code: int) -> FetchResponse:
    return FetchResponse(
        status_code=status_code,
        headers={"Content-Type": "text/html"},
        chunks=(),
        url="https://example.com/source.pdf",
        peer_ip="93.184.216.34",
    )


def test_requests_transport_uses_explicit_session_proxy_mode() -> None:
    direct = RequestsFetchTransport(proxy_mode="direct")
    environment = RequestsFetchTransport(proxy_mode="environment_proxy")
    assert direct.session.trust_env is False
    assert environment.session is None
    assert environment.trust_env is True
    assert requests.Session().trust_env is True


def test_direct_provider_acquires_raw_artifact_and_attempt(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    provider = DirectHttpProvider(
        transport=SequenceTransport([response()]),
        resolver=Resolver(),
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 25]).__next__,
    )
    result = provider.acquire(
        candidate(),
        context=context(),
        layout=layout,
        attempted_at="2026-07-20T08:00:00Z",
        max_retries=0,
    )
    assert result.attempt["status"] == "acquired"
    assert result.attempt["proxy_mode"] == "direct"
    assert result.artifact is not None
    assert result.artifact["access_status"] == "acquired"
    assert (layout.root / result.artifact["raw_artifact_path"]).read_bytes().startswith(b"%PDF")
    assert read_acquisition_attempt(result.attempt["attempt_id"], layout=layout) == result.attempt


def test_direct_provider_accepts_v2_2_candidate_acquisition_metadata(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    v2_2_candidate = candidate()
    v2_2_candidate.update(
        {
            "acquisition_batch_id": "acquisition_batch:fixture",
            "acquisition_status": "not_attempted",
            "accessed_at": None,
            "failure_reason": None,
        }
    )
    provider = DirectHttpProvider(
        transport=SequenceTransport([response()]),
        resolver=Resolver(),
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 1]).__next__,
    )
    result = provider.acquire(
        v2_2_candidate,
        context=context(),
        layout=layout,
        attempted_at="2026-07-20T08:00:00Z",
        max_retries=0,
    )
    assert result.attempt["status"] == "acquired"


def test_direct_provider_records_timeout_and_bounded_retry(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    transport = SequenceTransport([requests.Timeout("one"), requests.Timeout("two")])
    provider = DirectHttpProvider(
        transport=transport,
        resolver=Resolver(),
        now=lambda: "2026-07-20T08:00:03Z",
        monotonic_ms=iter([0, 3000]).__next__,
        sleep=lambda _seconds: None,
    )
    result = provider.acquire(
        candidate(),
        context=context(),
        layout=layout,
        attempted_at="2026-07-20T08:00:00Z",
        max_retries=1,
        retry_backoff_seconds=0,
    )
    assert transport.calls == 2
    assert result.artifact is None
    assert result.attempt["status"] == "failed"
    assert result.attempt["failure_code"] == "connection_timeout"
    assert result.attempt["retry_count"] == 1
    assert read_acquisition_attempt(result.attempt["attempt_id"], layout=layout) == result.attempt


def test_direct_provider_retries_then_succeeds_without_provider_fallback(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    transport = SequenceTransport([requests.Timeout("one"), response()])
    provider = DirectHttpProvider(
        transport=transport,
        resolver=Resolver(),
        now=lambda: "2026-07-20T08:00:02Z",
        monotonic_ms=iter([0, 2000]).__next__,
        sleep=lambda _seconds: None,
    )
    result = provider.acquire(
        candidate(),
        context=context(),
        layout=layout,
        attempted_at="2026-07-20T08:00:00Z",
        max_retries=1,
        retry_backoff_seconds=0,
    )
    assert transport.calls == 2
    assert result.attempt["provider"] == "direct_http"
    assert result.attempt["retry_count"] == 1
    assert result.attempt["failure_code"] is None


def test_environment_proxy_mode_is_fail_closed_until_trusted_proxy_design_exists(
    tmp_path: Path,
) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    transport = SequenceTransport([response()])
    provider = DirectHttpProvider(
        transport=transport,
        resolver=Resolver(),
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 1]).__next__,
    )
    result = provider.acquire(
        candidate(),
        context=context(),
        layout=layout,
        attempted_at="2026-07-20T08:00:00Z",
        proxy_mode="environment_proxy",
        max_retries=0,
    )
    assert transport.calls == 0
    assert result.artifact is None
    assert result.attempt["status"] == "blocked"
    assert result.attempt["failure_code"] == "security_policy_blocked"
    assert result.attempt["failure_details"]["policy_stage"] == "proxy_selection"


def test_non_200_response_is_preserved_as_http_error_attempt(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    transport = SequenceTransport([error_response(404)])
    provider = DirectHttpProvider(
        transport=transport,
        resolver=Resolver(),
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 1]).__next__,
    )
    result = provider.acquire(
        candidate(), context=context(), layout=layout,
        attempted_at="2026-07-20T08:00:00Z", max_retries=2,
    )
    assert transport.calls == 1
    assert result.attempt["http_status"] == 404
    assert result.attempt["failure_code"] == "http_error"
    assert result.artifact is None


def test_empty_success_body_is_recorded_as_empty_content(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    provider = DirectHttpProvider(
        transport=SequenceTransport([response(b"")]),
        resolver=Resolver(),
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 1]).__next__,
    )
    result = provider.acquire(
        candidate(), context=context(), layout=layout,
        attempted_at="2026-07-20T08:00:00Z", max_retries=0,
    )
    assert result.attempt["failure_code"] == "empty_content"
    assert result.artifact is None


def test_explicit_proxy_and_non_standard_port_are_blocked_attempts(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    transport = SequenceTransport([response()])
    provider = DirectHttpProvider(
        transport=transport,
        resolver=Resolver(),
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 1, 2, 3]).__next__,
    )
    proxy_result = provider.acquire(
        candidate(), context=context(), layout=layout,
        attempted_at="2026-07-20T08:00:00Z", proxy_mode="explicit_proxy",
        max_retries=0,
    )
    port_candidate = candidate()
    port_candidate["normalized_url"] = "https://example.com:8443/source.pdf"
    port_candidate["original_url"] = "https://example.com:8443/source.pdf"
    port_candidate["dedup_key"] = "https://example.com:8443/source.pdf"
    port_candidate["candidate_id"] = source_candidate_id(
        port_candidate["normalized_url"], port_candidate["title"]
    )
    port_context = AcquisitionContext(
        project_id=context().project_id,
        research_version_context=context().research_version_context,
        requirement_id=context().requirement_id,
        candidate_id=port_candidate["candidate_id"],
        provenance=PROVENANCE,
    )
    port_result = provider.acquire(
        port_candidate, context=port_context, layout=layout,
        attempted_at="2026-07-20T08:00:00Z", max_retries=0,
    )
    assert proxy_result.attempt["failure_code"] == "security_policy_blocked"
    assert port_result.attempt["failure_code"] == "security_policy_blocked"
    assert transport.calls == 0
