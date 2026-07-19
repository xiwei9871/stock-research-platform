from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
from typing import Iterable

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.discovery import normalize_url, source_candidate_id
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2_1.snapshot import (
    DENIED_NETWORKS,
    FetchResponse,
    RequestsFetchTransport,
    SystemAddressResolver,
    evidence_artifact_id_for_event,
    snapshot_candidate,
    validate_evidence_artifact,
)


FETCHED_AT = "2026-07-18T02:00:00Z"
PROVENANCE = {
    "created_by": "snapshot-test",
    "actor_type": "automated_pipeline",
    "agent_run_id": "run:snapshot-test",
    "created_at": FETCHED_AT,
    "created_in_version": "2.1.0",
    "review_status": "unreviewed",
}


def candidate(url: str = "https://example.com/source.pdf") -> dict[str, object]:
    normalized = normalize_url(url)
    title = "Industry source"
    return {
        "candidate_id": source_candidate_id(normalized, title),
        "search_plan_id": "search_plan:test",
        "query_id": "query:test",
        "normalized_url": normalized,
        "original_url": url,
        "title": title,
        "snippet": "Industry evidence.",
        "publisher": "Example",
        "publish_date": "2026-07-18",
        "source_class": "primary",
        "rank": 1,
        "exclusion_status": "included",
        "exclusion_reasons": [],
        "dedup_key": normalized,
        "provenance": dict(PROVENANCE),
    }


class Resolver:
    def __init__(self, answers: dict[str, tuple[str, ...]] | None = None):
        self.answers = answers or {"example.com": ("93.184.216.34",)}
        self.calls: list[str] = []

    def resolve(self, hostname: str) -> tuple[str, ...]:
        self.calls.append(hostname)
        return self.answers.get(hostname, ())


class Transport:
    def __init__(self, responses: Iterable[FetchResponse | BaseException]):
        self.responses = iter(responses)
        self.calls: list[tuple[str, float]] = []

    def get(self, url: str, *, timeout_seconds: float) -> FetchResponse:
        self.calls.append((url, timeout_seconds))
        item = next(self.responses)
        if isinstance(item, BaseException):
            raise item
        return item


def response(
    body: bytes = b"%PDF fixture",
    *,
    status: int = 200,
    url: str = "https://example.com/source.pdf",
    peer_ip: str = "93.184.216.34",
    headers: dict[str, str] | None = None,
    chunks: Iterable[bytes] | None = None,
) -> FetchResponse:
    return FetchResponse(
        status,
        {"Content-Type": "application/pdf"} if headers is None else headers,
        [body] if chunks is None else chunks,
        url,
        peer_ip,
    )


def layout(tmp_path: Path) -> LayeredResearchLayout:
    return LayeredResearchLayout(tmp_path / "layered")


def error_code(call) -> str:
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        call()
    return exc_info.value.code


def test_snapshots_canonical_artifact_and_metadata(tmp_path: Path) -> None:
    item = candidate()
    result = snapshot_candidate(
        item,
        transport=Transport([response(headers={
            "Content-Type": "Application/PDF; charset=binary",
            "ETag": '"abc"',
            "Set-Cookie": "secret=1",
        })]),
        resolver=Resolver(),
        layout=layout(tmp_path),
        fetched_at=FETCHED_AT,
        provenance=PROVENANCE,
    )
    artifact = result["artifact"]
    digest = hashlib.sha256(b"%PDF fixture").hexdigest()
    assert artifact["content_sha256"] == digest
    assert artifact["raw_path"] == f"evidence/raw/{digest[:2]}/{digest}.pdf"
    assert artifact["artifact_id"] == evidence_artifact_id_for_event(artifact)
    assert artifact["response_headers"] == {
        "content-type": "Application/PDF; charset=binary",
        "etag": '"abc"',
    }
    assert item == candidate()
    wrapper = {
        "schema_version": "2.1.0",
        "artifact_kind": "evidence_artifact",
        "evidence_artifact": artifact,
    }
    validate_v2_1_schema_payload("evidence_artifact_v2_1", wrapper)
    assert Path(result["raw_path"]).read_bytes() == b"%PDF fixture"
    assert json.loads(Path(result["metadata_path"]).read_text()) == wrapper
    assert validate_evidence_artifact(artifact) == artifact
    drifted = dict(artifact, artifact_id="evidence_artifact:" + "0" * 24)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_evidence_artifact(drifted)
    assert "IMMUTABILITY" in exc_info.value.code


def test_fetch_event_artifact_fixture_matches_schema_and_identity() -> None:
    payload = json.loads(
        Path(
            "artifacts/research_projects/v2_1/fixtures/valid/fetch_event_artifact.json"
        ).read_text(encoding="utf-8")
    )
    validate_v2_1_schema_payload("evidence_artifact_v2_1", payload)
    artifact = payload["evidence_artifact"]
    assert validate_evidence_artifact(artifact) == artifact


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/a",
        "http://user@example.com/a",
        "http://example.com\\a",
        "http://example.com/%zz",
        "http://127.0.0.1/a",
        "http://[::1]/a",
        "http://169.254.1.1/a",
        "http://224.0.0.1/a",
        "http://0.0.0.0/a",
        "http://100.64.0.1/a",
        "http://[::ffff:127.0.0.1]/a",
    ],
)
def test_rejects_invalid_or_denied_candidate_urls(tmp_path: Path, url: str) -> None:
    if "example.com" in url:
        item = candidate()
        item["normalized_url"] = url
    else:
        item = candidate(url)
    assert error_code(lambda: snapshot_candidate(
        item,
        transport=Transport([]),
        resolver=Resolver(),
        layout=layout(tmp_path),
        fetched_at=FETCHED_AT,
        provenance=PROVENANCE,
    )).startswith("RESEARCH_PROJECT_V2_1_")


@pytest.mark.parametrize(
    "answers",
    [(), ("93.184.216.34", "127.0.0.1"), ("not-an-ip",), ("100.64.1.2",)],
)
def test_rejects_empty_invalid_or_any_denied_dns_answer(
    tmp_path: Path, answers: tuple[str, ...]
) -> None:
    resolver = Resolver({"example.com": answers})
    assert "FETCH" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([]), resolver=resolver,
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))


@pytest.mark.parametrize("peer", ["127.0.0.1", "192.0.2.99", "bad-ip"])
def test_rejects_denied_mismatched_or_invalid_peer(tmp_path: Path, peer: str) -> None:
    assert "FETCH" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(peer_ip=peer)]), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    assert not (layout(tmp_path).root / "evidence").exists()


def test_relative_redirect_is_renormalized_reresolved_and_recorded(tmp_path: Path) -> None:
    resolver = Resolver({
        "example.com": ("93.184.216.34",),
        "cdn.example.com": ("93.184.216.35",),
    })
    transport = Transport([
        response(status=302, headers={"Location": "//cdn.example.com/final.pdf"}),
        response(url="https://cdn.example.com/final.pdf", peer_ip="93.184.216.35"),
    ])
    result = snapshot_candidate(
        candidate(), transport=transport, resolver=resolver, layout=layout(tmp_path),
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    assert result["artifact"]["redirect_chain"] == ["https://cdn.example.com/final.pdf"]
    assert resolver.calls == ["example.com", "cdn.example.com"]


@pytest.mark.parametrize("location", [None, "", 123])
def test_redirect_requires_one_string_location(tmp_path: Path, location: object) -> None:
    headers = {} if location is None else {"Location": location}  # type: ignore[dict-item]
    assert "REDIRECT" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(status=302, headers=headers)]),
        resolver=Resolver(), layout=layout(tmp_path), fetched_at=FETCHED_AT,
        provenance=PROVENANCE,
    ))


def test_redirect_loop_and_sixth_redirect_are_rejected(tmp_path: Path) -> None:
    loop = Transport([response(status=301, headers={"Location": "/source.pdf"})])
    assert "REDIRECT" in error_code(lambda: snapshot_candidate(
        candidate(), transport=loop, resolver=Resolver(), layout=layout(tmp_path),
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    urls = [f"https://example.com/{index}.pdf" for index in range(6)]
    redirects = [
        response(status=302, url=(candidate()["normalized_url"] if index == 0 else urls[index - 1]), headers={"Location": url})
        for index, url in enumerate(urls)
    ]
    assert "REDIRECT" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport(redirects), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))


@pytest.mark.parametrize("status", [199, 300, 304, 400, 500])
def test_rejects_non_redirect_non_2xx_status(tmp_path: Path, status: int) -> None:
    assert "STATUS" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(status=status)]), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))


def test_rejects_transport_reported_url_mismatch(tmp_path: Path) -> None:
    assert "FETCH" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(url="https://example.com/other.pdf")]),
        resolver=Resolver(), layout=layout(tmp_path), fetched_at=FETCHED_AT,
        provenance=PROVENANCE,
    ))


def test_max_bytes_stops_consuming_iterator_and_leaves_no_files(tmp_path: Path) -> None:
    consumed: list[int] = []
    def chunks():
        for index in range(3):
            consumed.append(index)
            yield b"abcd"
    assert "TOO_LARGE" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(chunks=chunks())]), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
        max_bytes=5,
    ))
    assert consumed == [0, 1]
    assert not [path for path in tmp_path.rglob("*.tmp") if path.is_file()]
    assert not list(tmp_path.rglob("*.pdf"))


@pytest.mark.parametrize("chunks", [["text"], [None]])
def test_rejects_non_bytes_chunks(tmp_path: Path, chunks: list[object]) -> None:
    assert "STREAM" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(chunks=chunks)]), resolver=Resolver(),  # type: ignore[arg-type]
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))


def test_wraps_transport_and_iterator_errors(tmp_path: Path) -> None:
    assert "TRANSPORT" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([RuntimeError("secret")]), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    def broken():
        yield b"ok"
        raise RuntimeError("secret")
    assert "STREAM" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(chunks=broken())]), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Content-Type": "image/png"},
        {"Content-Type": "application/pdf", "content-type": "text/html"},
        {"Content-Type": "application/pdf", "Content-Length": "-1"},
        {"Content-Type": "application/pdf", "Content-Length": "bogus"},
        {"Content-Type": "application/pdf", "Content-Length": "999"},
    ],
)
def test_rejects_invalid_media_headers_and_length(tmp_path: Path, headers: dict[str, str]) -> None:
    assert error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(headers=headers)]), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )).startswith("RESEARCH_PROJECT_V2_1_FETCH_")


def test_content_length_over_limit_rejects_without_consuming(tmp_path: Path) -> None:
    consumed: list[bool] = []
    def chunks():
        consumed.append(True)
        yield b"x"
    assert "TOO_LARGE" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(
            headers={"Content-Type": "application/pdf", "Content-Length": "6"},
            chunks=chunks(),
        )]), resolver=Resolver(), layout=layout(tmp_path), fetched_at=FETCHED_AT,
        provenance=PROVENANCE, max_bytes=5,
    ))
    assert consumed == []


def test_same_body_reuses_raw_while_metadata_is_per_artifact(tmp_path: Path) -> None:
    effective = layout(tmp_path)
    one = candidate()
    two = candidate("https://example.com/other.pdf")
    first = snapshot_candidate(
        one, transport=Transport([response()]), resolver=Resolver(), layout=effective,
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    second = snapshot_candidate(
        two, transport=Transport([response(url=two["normalized_url"])]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    again = snapshot_candidate(
        one, transport=Transport([response()]), resolver=Resolver(), layout=effective,
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    assert first["raw_path"] == second["raw_path"] == again["raw_path"]
    assert first["metadata_path"] != second["metadata_path"]
    assert first["artifact"] == again["artifact"]
    assert len(list(effective.evidence_raw_dir.rglob("*.pdf"))) == 1


def test_existing_raw_or_metadata_conflict_is_immutable(tmp_path: Path) -> None:
    effective = layout(tmp_path)
    digest = hashlib.sha256(b"%PDF fixture").hexdigest()
    raw = effective.evidence_raw_dir / digest[:2] / f"{digest}.pdf"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"corrupt")
    assert "IMMUTABILITY" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(), layout=effective,
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    raw.write_bytes(b"%PDF fixture")
    event = {
        "candidate_id": candidate()["candidate_id"],
        "content_sha256": digest,
        "byte_count": len(b"%PDF fixture"),
        "final_url": candidate()["normalized_url"],
        "redirect_chain": [],
        "status_code": 200,
        "response_headers": {"content-type": "application/pdf"},
        "media_type": "application/pdf",
        "fetched_at": FETCHED_AT,
        "provenance": PROVENANCE,
    }
    artifact_id = evidence_artifact_id_for_event(event)
    metadata = effective.evidence_metadata_dir / f"{artifact_id}.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(b"{}")
    assert "IMMUTABILITY" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(), layout=effective,
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))


def test_same_bytes_from_distinct_fetch_events_get_distinct_metadata(tmp_path: Path) -> None:
    effective = layout(tmp_path)
    first = snapshot_candidate(
        candidate(),
        transport=Transport([response()]),
        resolver=Resolver(),
        layout=effective,
        fetched_at="2026-07-18T02:00:00Z",
        provenance=PROVENANCE,
    )
    later_provenance = dict(
        PROVENANCE,
        agent_run_id="run:snapshot-later",
        created_at="2026-07-18T03:00:00Z",
    )
    second = snapshot_candidate(
        candidate(),
        transport=Transport([response()]),
        resolver=Resolver(),
        layout=effective,
        fetched_at="2026-07-18T03:00:00Z",
        provenance=later_provenance,
    )
    assert first["raw_path"] == second["raw_path"]
    assert first["artifact"]["content_sha256"] == second["artifact"]["content_sha256"]
    assert first["artifact"]["artifact_id"] != second["artifact"]["artifact_id"]
    assert first["metadata_path"] != second["metadata_path"]
    assert Path(first["metadata_path"]).is_file()
    assert Path(second["metadata_path"]).is_file()


@pytest.mark.parametrize("fetched_at", ["", "2026-07-18", "2026-07-18T02:00:00"])
def test_fetched_at_must_be_explicit_rfc3339(tmp_path: Path, fetched_at: str) -> None:
    assert "SNAPSHOT" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(), layout=layout(tmp_path),
        fetched_at=fetched_at, provenance=PROVENANCE,
    ))


def test_system_resolver_canonicalizes_deduplicates_and_sorts(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET6, 0, 0, "", ("2001:4860:4860::8888", 0, 0, 0)),
        (socket.AF_INET, 0, 0, "", ("8.8.8.8", 0)),
        (socket.AF_INET, 0, 0, "", ("8.8.8.8", 0)),
    ])
    assert SystemAddressResolver().resolve("example.com") == (
        "8.8.8.8", "2001:4860:4860::8888"
    )


def test_system_resolver_wraps_resolution_errors(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise socket.gaierror("private detail")
    monkeypatch.setattr(socket, "getaddrinfo", fail)
    assert "DNS" in error_code(lambda: SystemAddressResolver().resolve("example.com"))


def test_system_resolver_rejects_an_empty_answer_set(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [])
    assert "DNS_INVALID" in error_code(
        lambda: SystemAddressResolver().resolve("example.com")
    )


def test_requests_transport_disables_redirects_and_requires_real_peer(monkeypatch) -> None:
    calls = []
    class FakeRaw:
        _connection = None
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "text/plain"}
        url = "https://example.com/a"
        raw = FakeRaw()
        def iter_content(self, chunk_size):
            return iter([b"ok"])
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()
    import requests
    monkeypatch.setattr(requests, "get", fake_get)
    assert "PEER" in error_code(lambda: RequestsFetchTransport().get(
        "https://example.com/a", timeout_seconds=3.0
    ))
    assert calls[0][1]["stream"] is True
    assert calls[0][1]["allow_redirects"] is False


def test_requests_transport_stream_closes_response_after_consumption(monkeypatch) -> None:
    class Socket:
        def getpeername(self):
            return ("93.184.216.34", 443)
    class Connection:
        sock = Socket()
    class Raw:
        _connection = Connection()
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "text/plain"}
        url = "https://example.com/a"
        raw = Raw()
        closed = False
        def iter_content(self, chunk_size):
            yield b"one"
            yield b"two"
        def close(self):
            self.closed = True
    fake = FakeResponse()
    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    fetched = RequestsFetchTransport().get("https://example.com/a", timeout_seconds=3.0)
    assert tuple(fetched.chunks) == (b"one", b"two")
    assert fake.closed is True


def test_denied_network_plan_covers_required_ranges() -> None:
    assert tuple(str(network) for network in DENIED_NETWORKS) == (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4",
        "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
    )
    for address in [
        "127.0.0.1", "169.254.1.1", "224.0.0.1", "0.0.0.0", "100.64.0.1",
        "::1", "fe80::1", "ff02::1", "::", "::ffff:127.0.0.1",
    ]:
        ip = ipaddress.ip_address(address)
        assert any(
            (ip.ipv4_mapped in network if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None and network.version == 4 else ip.version == network.version and ip in network)
            for network in DENIED_NETWORKS
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: item.update(unexpected=True),
        lambda item: item.update(dedup_key="https://example.com/wrong"),
        lambda item: item.update(rank=True),
        lambda item: item.update(exclusion_status="excluded_by_policy", exclusion_reasons=["x"]),
        lambda item: item["provenance"].update(actor_type="unknown"),
        lambda item: item.update(source_class="stock_opinion"),
    ],
)
def test_requires_a_complete_canonical_included_task5_candidate(
    tmp_path: Path, mutate
) -> None:
    item = candidate()
    mutate(item)
    assert "SNAPSHOT_INVALID" in error_code(lambda: snapshot_candidate(
        item, transport=Transport([response()]), resolver=Resolver(), layout=layout(tmp_path),
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))


@pytest.mark.parametrize(
    ("media_type", "extension"),
    [
        ("application/pdf", "pdf"),
        ("text/html", "html"),
        ("text/plain", "txt"),
        ("application/json", "json"),
        ("text/csv", "csv"),
    ],
)
def test_all_supported_media_types_get_semantic_content_addressed_paths(
    tmp_path: Path, media_type: str, extension: str
) -> None:
    result = snapshot_candidate(
        candidate(),
        transport=Transport([response(body=b"body", headers={"Content-Type": media_type})]),
        resolver=Resolver(), layout=layout(tmp_path), fetched_at=FETCHED_AT,
        provenance=PROVENANCE,
    )
    digest = hashlib.sha256(b"body").hexdigest()
    assert result["artifact"]["raw_path"] == (
        f"evidence/raw/{digest[:2]}/{digest}.{extension}"
    )


def test_concurrent_fresh_root_snapshots_converge(tmp_path: Path) -> None:
    effective = layout(tmp_path)
    def run(_index: int):
        return snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(run, range(16)))
    assert len({str(item["raw_path"]) for item in results}) == 1
    assert len({str(item["metadata_path"]) for item in results}) == 1
    assert not [path for path in effective.root.rglob("*.tmp") if path.is_file()]


@pytest.mark.parametrize("managed", ["raw", "metadata"])
def test_rejects_symlinked_managed_directories(tmp_path: Path, managed: str) -> None:
    effective = layout(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence = effective.root / "evidence"
    evidence.mkdir(parents=True)
    (evidence / managed).symlink_to(outside, target_is_directory=True)
    assert "STORAGE" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(), layout=effective,
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    assert not list(outside.iterdir())


def test_failed_raw_write_leaves_no_temporary_or_final_files(tmp_path: Path, monkeypatch) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    monkeypatch.setattr(module.os, "write", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("fail")))
    effective = layout(tmp_path)
    assert "STORAGE" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(), layout=effective,
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    assert not [path for path in effective.root.rglob("*") if path.is_file()]


@pytest.mark.parametrize("failure", ["peer", "headers", "too_large"])
def test_rejection_closes_a_closeable_response_stream(
    tmp_path: Path, failure: str
) -> None:
    class Chunks:
        closed = False
        def __iter__(self):
            yield b"abcdef"
        def close(self):
            self.closed = True
    chunks = Chunks()
    peer = "192.0.2.1" if failure == "peer" else "93.184.216.34"
    headers = {} if failure == "headers" else {"Content-Type": "application/pdf"}
    kwargs = {"max_bytes": 5} if failure == "too_large" else {}
    assert "FETCH" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response(
            peer_ip=peer, headers=headers, chunks=chunks,
        )]), resolver=Resolver(), layout=layout(tmp_path), fetched_at=FETCHED_AT,
        provenance=PROVENANCE, **kwargs,
    ))
    assert chunks.closed is True


def test_raw_live_verification_detects_same_inode_content_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    original = module._verify_live
    mutated = False
    def mutate_then_verify(path, held_chain, final_name, held_final, expected):
        nonlocal mutated
        if not mutated and path.parent.name == "raw":
            mutated = True
            (path / final_name).write_bytes(b"corrupt-after-first-compare")
        return original(path, held_chain, final_name, held_final, expected)
    monkeypatch.setattr(module, "_verify_live", mutate_then_verify)
    assert "STORAGE" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))


def test_raw_final_dir_fsync_failure_rolls_back_created_final(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    original_link = module.os.link
    original_fsync = module.os.fsync
    state = {"raw_final_fd": None, "failed": False}
    def link(*args, **kwargs):
        result = original_link(*args, **kwargs)
        if str(args[1]).endswith(".pdf"):
            state["raw_final_fd"] = kwargs["dst_dir_fd"]
        return result
    def fsync(descriptor):
        if descriptor == state["raw_final_fd"] and not state["failed"]:
            state["failed"] = True
            raise OSError("injected raw final-dir fsync failure")
        return original_fsync(descriptor)
    monkeypatch.setattr(module.os, "link", link)
    monkeypatch.setattr(module.os, "fsync", fsync)
    effective = layout(tmp_path)
    assert "STORAGE" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    assert not list(effective.evidence_raw_dir.rglob("*.pdf"))
    assert not [path for path in effective.root.rglob("*.tmp") if path.is_file()]


def test_raw_binding_failure_rolls_back_only_a_created_final(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    original = module._verify_live
    monkeypatch.setattr(
        module,
        "_verify_live",
        lambda path, *args: False if path.parent.name == "raw" else original(path, *args),
    )
    effective = layout(tmp_path)
    assert "STORAGE" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    assert not list(effective.evidence_raw_dir.rglob("*.pdf"))


def test_raw_binding_failure_never_deletes_reused_existing_raw(
    tmp_path: Path, monkeypatch
) -> None:
    effective = layout(tmp_path)
    first = snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    raw = Path(first["raw_path"])
    import stock_research.research_project_v2_1.snapshot as module
    original = module._verify_live
    monkeypatch.setattr(
        module,
        "_verify_live",
        lambda path, *args: False if path.parent.name == "raw" else original(path, *args),
    )
    assert "STORAGE" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    assert raw.read_bytes() == b"%PDF fixture"


def test_raw_rollback_skips_and_preserves_a_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    replacement = b"concurrent replacement"
    def replace_then_fail(path, held_chain, final_name, held_final, expected):
        if path.parent.name == "raw":
            target = path / final_name
            target.unlink()
            target.write_bytes(replacement)
            return False
        return True
    monkeypatch.setattr(module, "_verify_live", replace_then_fail)
    effective = layout(tmp_path)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.details["rollback"] == "skipped"
    assert next(effective.evidence_raw_dir.rglob("*.pdf")).read_bytes() == replacement


def test_metadata_failure_keeps_complete_published_raw(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    monkeypatch.setattr(
        module,
        "_publish_bytes",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            module._storage_error("injected metadata failure")
        ),
    )
    effective = layout(tmp_path)
    assert "STORAGE" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    raw = next(effective.evidence_raw_dir.rglob("*.pdf"))
    assert raw.read_bytes() == b"%PDF fixture"
    assert not [path for path in effective.root.rglob("*.tmp") if path.is_file()]


def _inject_raw_temp_cleanup_fsync_failure(module, monkeypatch) -> None:
    original_unlink = module.os.unlink
    original_fsync = module.os.fsync
    state = {"cleanup_fd": None, "failed": False}
    def unlink(name, *args, **kwargs):
        result = original_unlink(name, *args, **kwargs)
        if ".snapshot." in str(name):
            state["cleanup_fd"] = kwargs.get("dir_fd")
        return result
    def fsync(descriptor):
        if descriptor == state["cleanup_fd"] and not state["failed"]:
            state["failed"] = True
            raise OSError("injected cleanup fsync failure")
        return original_fsync(descriptor)
    monkeypatch.setattr(module.os, "unlink", unlink)
    monkeypatch.setattr(module.os, "fsync", fsync)


def test_cleanup_failure_does_not_mask_primary_fetch_error(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    _inject_raw_temp_cleanup_fsync_failure(module, monkeypatch)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response(body=b"abcdef")]),
            resolver=Resolver(), layout=layout(tmp_path), fetched_at=FETCHED_AT,
            provenance=PROVENANCE, max_bytes=5,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_FETCH_TOO_LARGE"
    assert any("cleanup" in note for note in getattr(exc_info.value, "__notes__", []))


def test_cleanup_only_failure_has_stable_storage_code(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    _inject_raw_temp_cleanup_fsync_failure(module, monkeypatch)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert isinstance(exc_info.value.__cause__, OSError)


def _inject_raw_publisher_close_failures(
    module,
    monkeypatch,
    *,
    raw_target: Path | None = None,
    replacement: bytes | None = None,
    fail_chain: bool = False,
):
    original_open_chain = module._open_dir_chain
    original_open_regular = module._open_regular
    original_close = module.os.close
    state = {"chain": [], "held_fd": None, "replaced": False}
    def open_chain(path):
        result = original_open_chain(path)
        if path.parent.name == "raw" and path.name != ".tmp":
            state["chain"] = list(result[0])
        return result
    def open_regular(directory_fd, name):
        result = original_open_regular(directory_fd, name)
        if state["chain"] and directory_fd == state["chain"][-1] and name.endswith(".pdf"):
            state["held_fd"] = result[0]
        return result
    def close(descriptor):
        if descriptor == state["held_fd"]:
            if replacement is not None and raw_target is not None and not state["replaced"]:
                raw_target.unlink()
                raw_target.write_bytes(replacement)
                state["replaced"] = True
            original_close(descriptor)
            raise OSError("held raw close failure")
        if fail_chain and state["chain"] and descriptor == state["chain"][0]:
            original_close(descriptor)
            raise OSError("raw chain close failure")
        return original_close(descriptor)
    monkeypatch.setattr(module, "_open_dir_chain", open_chain)
    monkeypatch.setattr(module, "_open_regular", open_regular)
    monkeypatch.setattr(module.os, "close", close)
    return state


def test_raw_primary_binding_error_survives_held_close_failure(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    original_verify = module._verify_live
    monkeypatch.setattr(
        module,
        "_verify_live",
        lambda path, *args: False
        if path.parent.name == "raw"
        else original_verify(path, *args),
    )
    _inject_raw_publisher_close_failures(module, monkeypatch)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_ERROR"
    assert any("cleanup" in note for note in getattr(exc_info.value, "__notes__", []))


def test_successful_created_raw_close_failure_rolls_back_and_is_stable(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    effective = layout(tmp_path)
    _inject_raw_publisher_close_failures(module, monkeypatch)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert isinstance(exc_info.value.__cause__, OSError)
    assert exc_info.value.details["rollback"] == "removed"
    assert not list(effective.evidence_raw_dir.rglob("*.pdf"))
    assert not [path for path in effective.root.rglob("*.tmp") if path.is_file()]


def test_reused_raw_close_failure_preserves_existing_file(
    tmp_path: Path, monkeypatch
) -> None:
    effective = layout(tmp_path)
    first = snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    raw = Path(first["raw_path"])
    import stock_research.research_project_v2_1.snapshot as module
    _inject_raw_publisher_close_failures(module, monkeypatch)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert raw.read_bytes() == b"%PDF fixture"


def test_created_raw_close_failure_preserves_replacement_on_rollback(
    tmp_path: Path, monkeypatch
) -> None:
    effective = layout(tmp_path)
    digest = hashlib.sha256(b"%PDF fixture").hexdigest()
    raw = effective.evidence_raw_dir / digest[:2] / f"{digest}.pdf"
    replacement = b"replacement during close"
    import stock_research.research_project_v2_1.snapshot as module
    _inject_raw_publisher_close_failures(
        module, monkeypatch, raw_target=raw, replacement=replacement
    )
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert exc_info.value.details["rollback"] == "skipped"
    assert raw.read_bytes() == replacement


def test_multiple_raw_close_failures_keep_first_cause_and_notes(
    tmp_path: Path, monkeypatch
) -> None:
    effective = layout(tmp_path)
    first = snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    raw = Path(first["raw_path"])
    import stock_research.research_project_v2_1.snapshot as module
    _inject_raw_publisher_close_failures(module, monkeypatch, fail_chain=True)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert "held raw close failure" in str(exc_info.value.__cause__)
    assert any("additional cleanup failure" in note for note in exc_info.value.__notes__)
    assert raw.read_bytes() == b"%PDF fixture"


def _track_raw_final_directory(module, monkeypatch):
    original_open_chain = module._open_dir_chain
    state = {"final_fd": None}
    def open_chain(path):
        result = original_open_chain(path)
        if path.parent.name == "raw" and path.name != ".tmp":
            state["final_fd"] = result[0][-1]
        return result
    monkeypatch.setattr(module, "_open_dir_chain", open_chain)
    return state


def test_original_final_dir_close_side_effect_still_rolls_back_created_raw(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    state = _track_raw_final_directory(module, monkeypatch)
    original_close = module.os.close
    failed = False
    def close(descriptor):
        nonlocal failed
        if descriptor == state["final_fd"] and not failed:
            failed = True
            original_close(descriptor)
            raise OSError("original final dir closed then raised")
        return original_close(descriptor)
    monkeypatch.setattr(module.os, "close", close)
    effective = layout(tmp_path)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert exc_info.value.details["rollback"] == "removed"
    assert not list(effective.evidence_raw_dir.rglob("*.pdf"))
    assert not [path for path in effective.root.rglob("*.tmp") if path.is_file()]


def test_rollback_fd_close_failure_is_not_masking_and_does_not_restore_raw(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    state = _track_raw_final_directory(module, monkeypatch)
    original_dup = module.os.dup
    original_close = module.os.close
    state["rollback_fd"] = None
    original_failed = False
    rollback_failed = False
    def dup(descriptor):
        duplicated = original_dup(descriptor)
        if descriptor == state["final_fd"]:
            state["rollback_fd"] = duplicated
        return duplicated
    def close(descriptor):
        nonlocal original_failed, rollback_failed
        if descriptor == state["final_fd"] and not original_failed:
            original_failed = True
            original_close(descriptor)
            raise OSError("original final close failure")
        if descriptor == state["rollback_fd"] and not rollback_failed:
            rollback_failed = True
            original_close(descriptor)
            raise OSError("rollback fd close failure")
        return original_close(descriptor)
    monkeypatch.setattr(module.os, "dup", dup)
    monkeypatch.setattr(module.os, "close", close)
    effective = layout(tmp_path)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.details["rollback"] == "removed"
    assert "original final close failure" in str(exc_info.value.__cause__)
    assert any("rollback fd close failure" in note for note in exc_info.value.__notes__)
    assert not list(effective.evidence_raw_dir.rglob("*.pdf"))


def test_rollback_fd_dup_failure_uses_original_fd_to_remove_created_raw(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    state = _track_raw_final_directory(module, monkeypatch)
    original_dup = module.os.dup
    def dup(descriptor):
        if descriptor == state["final_fd"]:
            raise OSError("rollback dup failure")
        return original_dup(descriptor)
    monkeypatch.setattr(module.os, "dup", dup)
    effective = layout(tmp_path)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert "rollback dup failure" in str(exc_info.value.__cause__)
    assert exc_info.value.details["rollback"] == "removed"
    assert not list(effective.evidence_raw_dir.rglob("*.pdf"))


def test_existing_raw_never_duplicates_rollback_fd_or_deletes_on_close_failure(
    tmp_path: Path, monkeypatch
) -> None:
    effective = layout(tmp_path)
    first = snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    raw = Path(first["raw_path"])
    import stock_research.research_project_v2_1.snapshot as module
    state = _track_raw_final_directory(module, monkeypatch)
    original_dup = module.os.dup
    original_close = module.os.close
    dup_calls = 0
    failed = False
    def dup(descriptor):
        nonlocal dup_calls
        if descriptor == state["final_fd"]:
            dup_calls += 1
        return original_dup(descriptor)
    def close(descriptor):
        nonlocal failed
        if descriptor == state["final_fd"] and not failed:
            failed = True
            original_close(descriptor)
            raise OSError("existing final close failure")
        return original_close(descriptor)
    monkeypatch.setattr(module.os, "dup", dup)
    monkeypatch.setattr(module.os, "close", close)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert dup_calls == 0
    assert raw.read_bytes() == b"%PDF fixture"


def test_rollback_fd_close_side_effect_recovers_created_raw_via_live_path(
    tmp_path: Path, monkeypatch
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    state = _track_raw_final_directory(module, monkeypatch)
    original_dup = module.os.dup
    original_close = module.os.close
    state["rollback_fd"] = None
    failed = False
    def dup(descriptor):
        duplicated = original_dup(descriptor)
        if descriptor == state["final_fd"]:
            state["rollback_fd"] = duplicated
        return duplicated
    def close(descriptor):
        nonlocal failed
        if descriptor == state["rollback_fd"] and not failed:
            failed = True
            original_close(descriptor)
            raise OSError("rollback fd closed then raised")
        return original_close(descriptor)
    monkeypatch.setattr(module.os, "dup", dup)
    monkeypatch.setattr(module.os, "close", close)
    effective = layout(tmp_path)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert exc_info.value.details["rollback"] == "removed"
    assert not list(effective.evidence_raw_dir.rglob("*.pdf"))


@pytest.mark.parametrize("mutation", ["replacement", "directory_rebind"])
def test_live_path_rollback_skips_replacement_or_rebound_directory(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    effective = layout(tmp_path)
    digest = hashlib.sha256(b"%PDF fixture").hexdigest()
    raw = effective.evidence_raw_dir / digest[:2] / f"{digest}.pdf"
    replacement = b"live path replacement"
    import stock_research.research_project_v2_1.snapshot as module
    state = _track_raw_final_directory(module, monkeypatch)
    original_dup = module.os.dup
    original_close = module.os.close
    state["rollback_fd"] = None
    failed = False
    def dup(descriptor):
        duplicated = original_dup(descriptor)
        if descriptor == state["final_fd"]:
            state["rollback_fd"] = duplicated
        return duplicated
    def close(descriptor):
        nonlocal failed
        if descriptor == state["rollback_fd"] and not failed:
            failed = True
            if mutation == "replacement":
                raw.unlink()
                raw.write_bytes(replacement)
            else:
                rebound = raw.parent.with_name(raw.parent.name + ".detached")
                raw.parent.rename(rebound)
                raw.parent.mkdir(mode=0o700)
                raw.write_bytes(replacement)
            original_close(descriptor)
            raise OSError("rollback fd closed after live mutation")
        return original_close(descriptor)
    monkeypatch.setattr(module.os, "dup", dup)
    monkeypatch.setattr(module.os, "close", close)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED"
    assert exc_info.value.details["rollback"] == "skipped"
    assert raw.read_bytes() == replacement


class _MockRequestsResponse:
    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        peer_ip: str = "93.184.216.34",
        chunks: Iterable[bytes] | None = None,
        iterator_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        class Socket:
            def getpeername(inner_self):
                return (peer_ip, 443)
        class Connection:
            sock = Socket()
        class Raw:
            _connection = Connection()
        self.status_code = 200
        self.headers = (
            {"Content-Type": "application/pdf"} if headers is None else headers
        )
        self.url = "https://example.com/source.pdf"
        self.raw = Raw()
        self.close_calls = 0
        self._chunks = list(chunks or [b"%PDF fixture"])
        self._iterator_error = iterator_error
        self._close_error = close_error
    def iter_content(self, chunk_size):
        yield from self._chunks
        if self._iterator_error is not None:
            raise self._iterator_error
    def close(self):
        self.close_calls += 1
        if self._close_error is not None:
            raise self._close_error


@pytest.mark.parametrize(
    "failure",
    ["peer", "headers", "content_length", "media", "raw_temp"],
)
def test_requests_response_closes_even_when_stream_iteration_never_starts(
    tmp_path: Path, monkeypatch, failure: str
) -> None:
    import requests
    import stock_research.research_project_v2_1.snapshot as module
    headers = {"Content-Type": "application/pdf"}
    peer = "93.184.216.34"
    kwargs = {}
    if failure == "peer":
        peer = "192.0.2.1"
    elif failure == "headers":
        headers = {}
    elif failure == "content_length":
        headers["Content-Length"] = "100"
        kwargs["max_bytes"] = 5
    elif failure == "media":
        headers["Content-Type"] = "image/png"
    fake = _MockRequestsResponse(headers=headers, peer_ip=peer)
    monkeypatch.setattr(requests, "get", lambda *args, **call_kwargs: fake)
    if failure == "raw_temp":
        monkeypatch.setattr(
            module,
            "_new_raw_temp",
            lambda *args, **call_kwargs: (_ for _ in ()).throw(
                module._storage_error("injected raw temp failure")
            ),
        )
    with pytest.raises(ResearchProjectV2Error):
        snapshot_candidate(
            candidate(), transport=RequestsFetchTransport(), resolver=Resolver(),
            layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
            **kwargs,
        )
    assert fake.close_calls >= 1


def test_requests_iterator_error_closes_response(tmp_path: Path, monkeypatch) -> None:
    import requests
    fake = _MockRequestsResponse(iterator_error=RuntimeError("iterator failed"))
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    assert "STREAM" in error_code(lambda: snapshot_candidate(
        candidate(), transport=RequestsFetchTransport(), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    assert fake.close_calls >= 1


@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate"])
def test_encoded_requests_response_snapshots_decoded_bytes_without_representation_headers(
    tmp_path: Path, monkeypatch, encoding: str
) -> None:
    import requests
    decoded = b"decoded document body"
    fake = _MockRequestsResponse(
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Encoding": encoding,
            "Content-Length": "999",
            "ETag": '"compressed-etag"',
        },
        chunks=[decoded],
    )
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs)
        return fake
    monkeypatch.setattr(requests, "get", get)
    result = snapshot_candidate(
        candidate(), transport=RequestsFetchTransport(), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    artifact = result["artifact"]
    assert artifact["byte_count"] == len(decoded)
    assert artifact["content_sha256"] == hashlib.sha256(decoded).hexdigest()
    assert artifact["response_headers"] == {
        "content-type": "text/plain; charset=utf-8"
    }
    assert calls[0]["headers"] == {"Accept-Encoding": "identity"}
    assert calls[0]["stream"] is True
    assert calls[0]["allow_redirects"] is False


@pytest.mark.parametrize("encoding", [None, "identity", " Identity "])
def test_identity_requests_response_keeps_strict_content_length(
    tmp_path: Path, monkeypatch, encoding: str | None
) -> None:
    import requests
    headers = {
        "Content-Type": "application/pdf",
        "Content-Length": "99",
        "ETag": '"identity-etag"',
    }
    if encoding is not None:
        headers["Content-Encoding"] = encoding
    fake = _MockRequestsResponse(headers=headers, chunks=[b"short"])
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    assert "CONTENT_LENGTH" in error_code(lambda: snapshot_candidate(
        candidate(), transport=RequestsFetchTransport(), resolver=Resolver(),
        layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))
    assert fake.close_calls >= 1


@pytest.mark.parametrize(
    "address",
    [
        "192.0.0.1",
        "198.18.0.1",
        "240.0.0.1",
        "2001:db8::1",
        "fec0::1",
        "::ffff:192.168.1.1",
        "::ffff:198.18.0.1",
    ],
)
def test_private_by_default_ssrf_denies_non_global_addresses(address: str) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    assert module._is_denied(ipaddress.ip_address(address)) is True


@pytest.mark.parametrize(
    "address",
    ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"],
)
def test_private_by_default_ssrf_allows_global_addresses(address: str) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    assert module._is_denied(ipaddress.ip_address(address)) is False


def test_new_raw_temp_failure_closes_opened_directories_and_response(
    tmp_path: Path, monkeypatch
) -> None:
    import requests
    import stock_research.research_project_v2_1.snapshot as module
    fake = _MockRequestsResponse()
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    original_open_chain = module._open_dir_chain
    original_close = module.os.close
    state = {"opened": set(), "closed": set()}
    def open_chain(path):
        result = original_open_chain(path)
        if path.name == ".tmp":
            state["opened"].update(result[0])
        return result
    def close(descriptor):
        state["closed"].add(descriptor)
        return original_close(descriptor)
    monkeypatch.setattr(module, "_open_dir_chain", open_chain)
    monkeypatch.setattr(module.os, "close", close)
    monkeypatch.setattr(
        module,
        "_create_temp",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            module._storage_error("injected temp creation failure")
        ),
    )
    with pytest.raises(ResearchProjectV2Error):
        snapshot_candidate(
            candidate(), transport=RequestsFetchTransport(), resolver=Resolver(),
            layout=layout(tmp_path), fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert state["opened"] <= state["closed"]
    assert fake.close_calls >= 1


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, MemoryError])
def test_raw_publisher_preserves_control_flow_base_exceptions(
    tmp_path: Path, monkeypatch, exception_type
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    monkeypatch.setattr(
        module,
        "_verify_live",
        lambda *args, **kwargs: (_ for _ in ()).throw(exception_type()),
    )
    effective = layout(tmp_path)
    with pytest.raises(exception_type):
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert not list(effective.evidence_raw_dir.rglob("*.pdf"))
    assert not [path for path in effective.root.rglob("*.tmp") if path.is_file()]


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, MemoryError])
def test_raw_temp_cleanup_preserves_control_flow_base_exceptions(
    tmp_path: Path, monkeypatch, exception_type
) -> None:
    import stock_research.research_project_v2_1.snapshot as module
    original_unlink = module._unlink_temp_if_bound
    def unlink_then_interrupt(*args, **kwargs):
        original_unlink(*args, **kwargs)
        raise exception_type()
    monkeypatch.setattr(module, "_unlink_temp_if_bound", unlink_then_interrupt)
    effective = layout(tmp_path)
    with pytest.raises(exception_type):
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert not [path for path in effective.root.rglob("*.tmp") if path.is_file()]


def test_existing_metadata_read_error_is_stable_storage_error(
    tmp_path: Path, monkeypatch
) -> None:
    effective = layout(tmp_path)
    snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(),
        layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
    )
    import stock_research.research_project_v2_1.snapshot as module
    original_read_all = module._read_all
    calls = 0
    def fail_metadata_read(descriptor):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected metadata read failure")
        return original_read_all(descriptor)
    monkeypatch.setattr(module, "_read_all", fail_metadata_read)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        snapshot_candidate(
            candidate(), transport=Transport([response()]), resolver=Resolver(),
            layout=effective, fetched_at=FETCHED_AT, provenance=PROVENANCE,
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_ERROR"
    assert isinstance(exc_info.value.__cause__, OSError)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status_code", True),
        ("status_code", "200"),
        ("status_code", 99),
        ("status_code", 600),
        ("headers", {1: "value"}),
        ("headers", {"Content-Type": 1}),
        ("headers", {"Content-Type": "text/plain", "Content-Encoding": 1}),
        ("url", ""),
        ("url", None),
        ("url", 123),
        ("url", "https://example.com/%zz"),
    ],
)
def test_requests_transport_validation_failures_close_owned_response_once(
    monkeypatch, field: str, value: object
) -> None:
    import requests
    fake = _MockRequestsResponse()
    setattr(fake, field, value)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    assert "FETCH" in error_code(lambda: RequestsFetchTransport().get(
        "https://example.com/source.pdf", timeout_seconds=3.0
    ))
    assert fake.close_calls == 1


def test_requests_transport_peer_extraction_failure_closes_once(monkeypatch) -> None:
    import requests
    fake = _MockRequestsResponse()
    fake.raw = object()
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        RequestsFetchTransport().get(
            "https://example.com/source.pdf", timeout_seconds=3.0
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_FETCH_PEER_UNAVAILABLE"
    assert fake.close_calls == 1


def test_requests_transport_rejects_duplicate_lowercase_headers_and_closes(
    monkeypatch,
) -> None:
    import requests
    from collections.abc import Mapping
    class DuplicateHeaders(Mapping):
        def __iter__(self):
            return iter(["Content-Type", "content-type"])
        def __len__(self):
            return 2
        def __getitem__(self, key):
            return "text/plain"
        def items(self):
            return [
                ("Content-Type", "text/plain"),
                ("content-type", "application/pdf"),
            ]
    fake = _MockRequestsResponse()
    fake.headers = DuplicateHeaders()
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    assert "TRANSPORT" in error_code(lambda: RequestsFetchTransport().get(
        "https://example.com/source.pdf", timeout_seconds=3.0
    ))
    assert fake.close_calls == 1


@pytest.mark.parametrize("failure", ["peer", "status"])
def test_requests_transport_close_error_does_not_mask_primary_validation_error(
    monkeypatch, failure: str
) -> None:
    import requests
    fake = _MockRequestsResponse(close_error=RuntimeError("close failed"))
    if failure == "peer":
        fake.raw = object()
    else:
        fake.status_code = True
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        RequestsFetchTransport().get(
            "https://example.com/source.pdf", timeout_seconds=3.0
        )
    expected = (
        "RESEARCH_PROJECT_V2_1_FETCH_PEER_UNAVAILABLE"
        if failure == "peer"
        else "RESEARCH_PROJECT_V2_1_FETCH_TRANSPORT_ERROR"
    )
    assert exc_info.value.code == expected
    assert any("close failed" in note for note in exc_info.value.__notes__)
    assert fake.close_calls == 1


def test_requests_transport_transfers_successful_response_to_chunk_stream(
    monkeypatch,
) -> None:
    import requests
    fake = _MockRequestsResponse()
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    fetched = RequestsFetchTransport().get(
        "https://example.com/source.pdf", timeout_seconds=3.0
    )
    assert fake.close_calls == 0
    fetched.chunks.close()
    assert fake.close_calls == 1


def test_requests_transport_close_only_failure_is_stable(monkeypatch) -> None:
    import requests
    fake = _MockRequestsResponse(close_error=RuntimeError("close-only failure"))
    fake.status_code = 404
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        RequestsFetchTransport().get(
            "https://example.com/source.pdf", timeout_seconds=3.0
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_FETCH_TRANSPORT_ERROR"
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert fake.close_calls == 1


def test_fetch_response_construction_memory_error_keeps_guard_ownership(
    monkeypatch,
) -> None:
    import requests
    import stock_research.research_project_v2_1.snapshot as module
    fake = _MockRequestsResponse()
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    monkeypatch.setattr(
        module,
        "FetchResponse",
        lambda *args, **kwargs: (_ for _ in ()).throw(MemoryError()),
    )
    with pytest.raises(MemoryError):
        RequestsFetchTransport().get(
            "https://example.com/source.pdf", timeout_seconds=3.0
        )
    assert fake.close_calls == 1


def test_fetch_response_construction_error_is_wrapped_and_closes(monkeypatch) -> None:
    import requests
    import stock_research.research_project_v2_1.snapshot as module
    fake = _MockRequestsResponse()
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    monkeypatch.setattr(
        module,
        "FetchResponse",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("construction failed")
        ),
    )
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        RequestsFetchTransport().get(
            "https://example.com/source.pdf", timeout_seconds=3.0
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_FETCH_TRANSPORT_ERROR"
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert fake.close_calls == 1


def test_fetch_response_construction_primary_is_not_masked_by_close_failure(
    monkeypatch,
) -> None:
    import requests
    import stock_research.research_project_v2_1.snapshot as module
    fake = _MockRequestsResponse(close_error=RuntimeError("close failed"))
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: fake)
    monkeypatch.setattr(
        module,
        "FetchResponse",
        lambda *args, **kwargs: (_ for _ in ()).throw(MemoryError()),
    )
    with pytest.raises(MemoryError) as exc_info:
        RequestsFetchTransport().get(
            "https://example.com/source.pdf", timeout_seconds=3.0
        )
    assert any("close failed" in note for note in exc_info.value.__notes__)
    assert fake.close_calls == 1
