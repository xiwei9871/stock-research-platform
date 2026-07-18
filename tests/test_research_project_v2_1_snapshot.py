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
    snapshot_candidate,
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
    artifact_id = f"evidence_artifact:{hashlib.sha256((candidate()['candidate_id'] + chr(10) + digest).encode()).hexdigest()[:24]}"
    metadata = effective.evidence_metadata_dir / f"{artifact_id}.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(b"{}")
    assert "IMMUTABILITY" in error_code(lambda: snapshot_candidate(
        candidate(), transport=Transport([response()]), resolver=Resolver(), layout=effective,
        fetched_at=FETCHED_AT, provenance=PROVENANCE,
    ))


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
