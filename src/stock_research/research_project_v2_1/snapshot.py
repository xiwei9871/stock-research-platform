from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
import errno
from hashlib import sha256
import ipaddress
import os
from pathlib import Path
import re
import secrets
import socket
import stat
from typing import Any, Iterable, Mapping, Protocol
import unicodedata
from urllib.parse import urljoin, urlsplit

from stock_research.research_project_v2.canonical import canonical_bytes
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.discovery import normalize_url, source_candidate_id
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


DENIED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MEDIA_EXTENSIONS = {
    "application/pdf": "pdf",
    "text/html": "html",
    "text/plain": "txt",
    "application/json": "json",
    "text/csv": "csv",
}
_SAVED_HEADERS = {
    "content-type",
    "content-length",
    "content-disposition",
    "etag",
    "last-modified",
    "cache-control",
    "expires",
    "date",
}
_RFC3339 = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
_CANDIDATE_FIELDS = {
    "candidate_id",
    "search_plan_id",
    "query_id",
    "normalized_url",
    "original_url",
    "title",
    "snippet",
    "publisher",
    "publish_date",
    "source_class",
    "rank",
    "exclusion_status",
    "exclusion_reasons",
    "dedup_key",
    "provenance",
}
_PROVENANCE_FIELDS = {
    "created_by",
    "actor_type",
    "agent_run_id",
    "created_at",
    "created_in_version",
    "review_status",
}
_ACTOR_TYPES = {"human", "codex", "automated_pipeline", "imported"}
_REVIEW_STATUSES = {"unreviewed", "pending_review", "reviewed", "rejected"}
_CONTROL_FLOW_EXCEPTIONS = (KeyboardInterrupt, SystemExit, MemoryError)
_STOCK_OPINION_CLASSES = {"stock_opinion", "equity_research"}
_STOCK_OPINION_PHRASES = {
    "目标价", "买入评级", "卖出评级", "增持评级", "建议买入", "股票推荐",
    "最强龙头", "受益标的", "估值最低", "target price", "price target",
    "buy rating", "sell rating", "strong buy", "top stock picks", "stock pick",
    "company ranking",
}
_DIR_FD_CAPABLE = (
    {os.open, os.mkdir, os.link, os.unlink, os.stat}.issubset(os.supports_dir_fd)
    and os.link in os.supports_follow_symlinks
    and os.stat in os.supports_follow_symlinks
)


@dataclass(frozen=True)
class FetchResponse:
    status_code: int
    headers: Mapping[str, str]
    chunks: Iterable[bytes]
    url: str
    peer_ip: str


class FetchTransport(Protocol):
    def get(self, url: str, *, timeout_seconds: float) -> FetchResponse: ...


class AddressResolver(Protocol):
    def resolve(self, hostname: str) -> tuple[str, ...]: ...


def _error(kind: str, reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Evidence snapshot failed: {reason}",
        code=f"RESEARCH_PROJECT_V2_1_{kind}",
        details={"reason": reason, **details},
    )


def _snapshot_invalid(reason: str, **details: object) -> ResearchProjectV2Error:
    return _error("SNAPSHOT_INVALID", reason, **details)


def _storage_error(reason: str, **details: object) -> ResearchProjectV2Error:
    return _error("SNAPSHOT_STORAGE_ERROR", reason, **details)


def _storage_failed(reason: str, **details: object) -> ResearchProjectV2Error:
    return _error("SNAPSHOT_STORAGE_FAILED", reason, **details)


def _immutability(reason: str, **details: object) -> ResearchProjectV2Error:
    return _error("SNAPSHOT_IMMUTABILITY_VIOLATION", reason, **details)


def _canonical_ip(value: object, *, kind: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if not isinstance(value, str) or value != value.strip():
        raise _error(kind, "invalid IP address", address=value)
    try:
        return ipaddress.ip_address(value)
    except ValueError as exc:
        raise _error(kind, "invalid IP address", address=value) from exc


def _is_denied(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return _is_denied(address.ipv4_mapped)
    return (
        not address.is_global
        or address.is_private
        or address.is_reserved
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or bool(getattr(address, "is_site_local", False))
        or any(
            address.version == network.version and address in network
            for network in DENIED_NETWORKS
        )
    )


class SystemAddressResolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        try:
            answers = socket.getaddrinfo(
                hostname,
                None,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise _error("FETCH_DNS_ERROR", "address resolution failed", hostname=hostname) from exc
        values: set[str] = set()
        for answer in answers:
            try:
                values.add(ipaddress.ip_address(answer[4][0]).compressed)
            except (IndexError, TypeError, ValueError) as exc:
                raise _error(
                    "FETCH_DNS_INVALID", "resolver returned an invalid address", hostname=hostname
                ) from exc
        if not values:
            raise _error(
                "FETCH_DNS_INVALID", "resolver returned no addresses", hostname=hostname
            )
        return tuple(sorted(values, key=lambda item: (ipaddress.ip_address(item).version, ipaddress.ip_address(item).packed)))


def _peer_from_requests_response(response: object) -> str:
    raw = getattr(response, "raw", None)
    for connection_name in ("_connection", "connection"):
        connection = getattr(raw, connection_name, None)
        sock = getattr(connection, "sock", None)
        if sock is None:
            continue
        try:
            peer = sock.getpeername()
        except OSError:
            continue
        if isinstance(peer, tuple) and peer and isinstance(peer[0], str):
            return peer[0]
    raise _error(
        "FETCH_PEER_UNAVAILABLE",
        "transport could not determine the connected peer IP",
    )


class RequestsFetchTransport:
    def get(self, url: str, *, timeout_seconds: float) -> FetchResponse:
        try:
            import requests

            response = requests.get(
                url,
                timeout=timeout_seconds,
                stream=True,
                allow_redirects=False,
                headers={"Accept-Encoding": "identity"},
            )
        except _CONTROL_FLOW_EXCEPTIONS:
            raise
        except Exception as exc:
            raise _error("FETCH_TRANSPORT_ERROR", "HTTP request failed", url=url) from exc
        try:
            peer_ip = _peer_from_requests_response(response)
        except BaseException:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise
        status_code = response.status_code
        headers = dict(response.headers)
        content_encodings = [
            value.strip().lower()
            for key, value in headers.items()
            if key.lower() == "content-encoding" and isinstance(value, str)
        ]
        encoded = any(
            value not in {"", "identity"} for value in content_encodings
        )
        headers = {
            key: value
            for key, value in headers.items()
            if key.lower() != "content-encoding"
            and not (
                encoded and key.lower() in {"content-length", "etag"}
            )
        }
        response_url = response.url
        if status_code in _REDIRECT_STATUSES or not 200 <= status_code <= 299:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            chunks: Iterable[bytes] = ()
        else:
            chunks = _RequestsChunkStream(response)
        return FetchResponse(
            status_code=status_code,
            headers=headers,
            chunks=chunks,
            url=response_url,
            peer_ip=peer_ip,
        )


class _RequestsChunkStream:
    def __init__(self, response: object) -> None:
        self._response = response
        self._closed = False

    def __iter__(self) -> Iterable[bytes]:
        try:
            yield from self._response.iter_content(chunk_size=64 * 1024)
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self._response, "close", None)
        if callable(close):
            close()


def _approved_addresses(url: str, resolver: AddressResolver) -> frozenset[str]:
    hostname = urlsplit(url).hostname
    if hostname is None:
        raise _error("FETCH_DNS_INVALID", "URL has no hostname", url=url)
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            raw_answers = resolver.resolve(hostname)
        except ResearchProjectV2Error:
            raise
        except _CONTROL_FLOW_EXCEPTIONS:
            raise
        except Exception as exc:
            raise _error("FETCH_DNS_ERROR", "address resolution failed", hostname=hostname) from exc
        if not isinstance(raw_answers, tuple) or not raw_answers:
            raise _error("FETCH_DNS_INVALID", "resolver returned no addresses", hostname=hostname)
        addresses = [_canonical_ip(value, kind="FETCH_DNS_INVALID") for value in raw_answers]
    else:
        addresses = [literal]
    if any(_is_denied(address) for address in addresses):
        raise _error("FETCH_DNS_DENIED", "hostname resolves to a denied network", hostname=hostname)
    return frozenset(address.compressed for address in addresses)


def _validate_peer(peer_ip: object, approved: frozenset[str]) -> None:
    peer = _canonical_ip(peer_ip, kind="FETCH_PEER_INVALID")
    if _is_denied(peer):
        raise _error("FETCH_PEER_DENIED", "connected peer is in a denied network")
    if peer.compressed not in approved:
        raise _error(
            "FETCH_PEER_MISMATCH",
            "connected peer was not in the approved DNS answer set",
        )


def _headers(headers: object) -> tuple[dict[str, str], str, int | None]:
    if not isinstance(headers, Mapping):
        raise _error("FETCH_HEADERS_INVALID", "response headers are not a mapping")
    lowered: dict[str, str] = {}
    saved: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise _error("FETCH_HEADERS_INVALID", "response header is not a string")
        canonical = key.lower()
        if canonical in lowered:
            raise _error("FETCH_HEADERS_INVALID", "duplicate response header", header=canonical)
        lowered[canonical] = value
        if canonical in _SAVED_HEADERS:
            saved[canonical] = value
    content_type = lowered.get("content-type")
    if content_type is None or not content_type.strip():
        raise _error("FETCH_MEDIA_TYPE_INVALID", "missing Content-Type")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in _MEDIA_EXTENSIONS:
        raise _error("FETCH_MEDIA_TYPE_UNSUPPORTED", "unsupported Content-Type", media_type=media_type)
    declared_length: int | None = None
    if "content-length" in lowered:
        raw_length = lowered["content-length"]
        if not re.fullmatch(r"0|[1-9][0-9]*", raw_length):
            raise _error("FETCH_CONTENT_LENGTH_INVALID", "invalid Content-Length")
        declared_length = int(raw_length)
    return saved, media_type, declared_length


def _close_chunks(response: FetchResponse) -> None:
    close = getattr(response.chunks, "close", None)
    if callable(close):
        try:
            close()
        except _CONTROL_FLOW_EXCEPTIONS:
            raise
        except Exception:
            pass


def _parse_fetched_at(value: object) -> str:
    if not isinstance(value, str) or value != value.strip() or _RFC3339.fullmatch(value) is None:
        raise _snapshot_invalid("invalid fetched_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _snapshot_invalid("invalid fetched_at") from exc
    if parsed.tzinfo is None:
        raise _snapshot_invalid("invalid fetched_at")
    return value


def _canonical_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _snapshot_invalid("candidate field is not canonical", field=field)
    return value


def _validate_provenance(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _PROVENANCE_FIELDS:
        raise _snapshot_invalid("provenance has an invalid shape", field=field)
    _canonical_nonempty(value.get("created_by"), field=f"{field}.created_by")
    if value.get("actor_type") not in _ACTOR_TYPES:
        raise _snapshot_invalid("provenance has an invalid actor_type", field=field)
    if value.get("agent_run_id") is not None:
        _canonical_nonempty(value.get("agent_run_id"), field=f"{field}.agent_run_id")
    _parse_fetched_at(value.get("created_at"))
    _canonical_nonempty(
        value.get("created_in_version"), field=f"{field}.created_in_version"
    )
    if value.get("review_status") not in _REVIEW_STATUSES:
        raise _snapshot_invalid("provenance has an invalid review_status", field=field)
    return deepcopy(value)


def _normalized_tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(
        "".join(
            character if character.isalnum() else " " for character in normalized
        ).split()
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    text_tokens = _normalized_tokens(text)
    phrase_tokens = _normalized_tokens(phrase)
    if any("\u3400" <= character <= "\u9fff" for character in phrase):
        return "".join(phrase_tokens) in "".join(text_tokens)
    width = len(phrase_tokens)
    return width > 0 and any(
        text_tokens[index : index + width] == phrase_tokens
        for index in range(len(text_tokens) - width + 1)
    )


def _validate_candidate(candidate: object) -> dict[str, Any]:
    if not isinstance(candidate, dict) or set(candidate) != _CANDIDATE_FIELDS:
        raise _snapshot_invalid("candidate has an invalid shape")
    copied = deepcopy(candidate)
    try:
        candidate_id = copied["candidate_id"]
        normalized = copied["normalized_url"]
        original = copied["original_url"]
        title = copied["title"]
        exclusion_status = copied["exclusion_status"]
    except KeyError as exc:
        raise _snapshot_invalid("candidate is missing a required field", field=str(exc)) from exc
    if exclusion_status != "included":
        raise _snapshot_invalid("candidate is not included")
    for field in (
        "candidate_id",
        "search_plan_id",
        "query_id",
        "normalized_url",
        "original_url",
        "title",
        "source_class",
        "dedup_key",
    ):
        _canonical_nonempty(copied.get(field), field=field)
    if not isinstance(copied.get("snippet"), str) or copied["snippet"] != copied["snippet"].strip():
        raise _snapshot_invalid("candidate snippet is not canonical")
    if copied.get("publisher") is not None:
        _canonical_nonempty(copied.get("publisher"), field="publisher")
    publish_date = copied.get("publish_date")
    if publish_date is not None:
        if not isinstance(publish_date, str):
            raise _snapshot_invalid("candidate publish_date is invalid")
        try:
            if date.fromisoformat(publish_date).isoformat() != publish_date:
                raise ValueError
        except ValueError as exc:
            raise _snapshot_invalid("candidate publish_date is invalid") from exc
    rank = copied.get("rank")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
        raise _snapshot_invalid("candidate rank is invalid")
    if copied.get("exclusion_reasons") != []:
        raise _snapshot_invalid("included candidate has exclusion reasons")
    normalized_class = unicodedata.normalize(
        "NFKC", copied["source_class"]
    ).casefold().strip()
    combined = f"{copied['title']}\n{copied['snippet']}"
    if normalized_class in _STOCK_OPINION_CLASSES or any(
        _contains_phrase(combined, phrase) for phrase in _STOCK_OPINION_PHRASES
    ):
        raise _snapshot_invalid("candidate violates the industry-source policy")
    _validate_provenance(copied.get("provenance"), field="candidate.provenance")
    try:
        canonical = normalize_url(normalized)
        canonical_original = normalize_url(original)
    except ResearchProjectV2Error as exc:
        raise _snapshot_invalid("candidate URL is invalid") from exc
    if normalized != canonical or canonical_original != canonical:
        raise _snapshot_invalid("candidate URL is not canonical")
    if copied["dedup_key"] != canonical:
        raise _snapshot_invalid("candidate dedup_key is invalid")
    if not isinstance(title, str) or candidate_id != source_candidate_id(canonical, title):
        raise _snapshot_invalid("candidate_id is invalid")
    return copied


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _require_storage_capability() -> None:
    if not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0) or not _DIR_FD_CAPABLE:
        raise _storage_error("secure dir-fd storage unavailable")


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _open_or_create_dir(parent_fd: int, name: str) -> int:
    created = False
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise _storage_error("unsafe managed path", component=name) from exc
    if created:
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            raise _storage_error("directory sync failed", component=name) from exc
    try:
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(errno.ENOTDIR, "not a directory")
        return descriptor
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise _storage_error("unsafe managed path", component=name) from exc


def _open_dir_chain(path: Path) -> tuple[list[int], list[str]]:
    if not path.is_absolute():
        raise _storage_error("managed path must be absolute", path=str(path))
    fds: list[int] = []
    names: list[str] = []
    try:
        fds.append(os.open("/", _directory_flags()))
        for name in path.parts[1:]:
            if name in {"", ".", ".."}:
                raise _storage_error("unsafe managed path", component=name)
            fds.append(_open_or_create_dir(fds[-1], name))
            names.append(name)
        return fds, names
    except BaseException:
        for descriptor in reversed(fds):
            os.close(descriptor)
        raise


def _chain_bound(fds: list[int], names: list[str]) -> bool:
    if len(fds) != len(names) + 1:
        return False
    try:
        return all(
            stat.S_ISDIR((entry := os.stat(name, dir_fd=fds[index], follow_symlinks=False)).st_mode)
            and _same_inode(entry, os.fstat(fds[index + 1]))
            for index, name in enumerate(names)
        )
    except OSError:
        return False


def _create_temp(directory_fd: int, stem: str) -> tuple[int, str]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    for _ in range(128):
        name = f".{stem}.{secrets.token_hex(16)}.tmp"
        try:
            return os.open(name, flags, 0o600, dir_fd=directory_fd), name
        except FileExistsError:
            continue
        except OSError as exc:
            raise _storage_error("temporary file creation failed") from exc
    raise _storage_error("temporary file name collision")


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short write")
        offset += written


def _read_all(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    result: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(result)
        result.append(chunk)


def _descriptors_equal(left: int, right: int) -> bool:
    os.lseek(left, 0, os.SEEK_SET)
    os.lseek(right, 0, os.SEEK_SET)
    while True:
        left_chunk = os.read(left, 1024 * 1024)
        right_chunk = os.read(right, 1024 * 1024)
        if left_chunk != right_chunk:
            return False
        if not left_chunk:
            return True


def _descriptor_sha256(descriptor: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = sha256()
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _open_regular(directory_fd: int, name: str) -> tuple[int, os.stat_result]:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=directory_fd)
        opened = os.fstat(descriptor)
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(entry.st_mode) or not _same_inode(opened, entry):
            raise OSError(errno.EIO, "regular file binding mismatch")
        return descriptor, opened
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise _storage_error("unsafe managed file", target=name) from exc


def _unlink_temp_if_bound(directory_fd: int, name: str, expected: os.stat_result) -> None:
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISREG(entry.st_mode) and _same_inode(entry, expected):
            os.unlink(name, dir_fd=directory_fd)
            os.fsync(directory_fd)
    except FileNotFoundError:
        pass


def _rollback_created_final(
    directory_fd: int, name: str, expected: os.stat_result
) -> tuple[str, str | None]:
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return "skipped", "final name already absent"
    except OSError as exc:
        return "failed", type(exc).__name__
    if not stat.S_ISREG(entry.st_mode) or not _same_inode(entry, expected):
        return "skipped", "final name no longer matches created inode"
    try:
        os.unlink(name, dir_fd=directory_fd)
        os.fsync(directory_fd)
        return "removed", None
    except OSError as exc:
        return "failed", type(exc).__name__


def _rollback_created_final_via_live_path(
    directory: Path,
    expected_directory: os.stat_result,
    name: str,
    expected_final: os.stat_result,
) -> tuple[str, str | None, list[BaseException]]:
    descriptors: list[int] = []
    cleanup_errors: list[BaseException] = []
    outcome = "failed"
    detail: str | None = "live rollback path was not opened"
    try:
        descriptors.append(os.open("/", _directory_flags()))
        for component in directory.parts[1:]:
            descriptors.append(
                os.open(component, _directory_flags(), dir_fd=descriptors[-1])
            )
        live_directory = os.fstat(descriptors[-1])
        if not stat.S_ISDIR(live_directory.st_mode) or not _same_inode(
            live_directory, expected_directory
        ):
            outcome = "skipped"
            detail = "live final directory no longer matches created directory"
        else:
            outcome, detail = _rollback_created_final(
                descriptors[-1], name, expected_final
            )
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.ENOTDIR, errno.ELOOP}:
            outcome = "skipped"
            detail = "live final directory is absent or rebound"
        else:
            outcome = "failed"
            detail = type(exc).__name__
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_errors.append(exc)
    return outcome, detail, cleanup_errors


def _record_rollback(
    error: BaseException, outcome: str, detail: str | None
) -> None:
    if isinstance(error, ResearchProjectV2Error):
        error.details["rollback"] = outcome
        if detail is not None:
            error.details["rollback_detail"] = detail
    else:
        error.add_note(
            f"raw publication rollback {outcome}"
            + (f": {detail}" if detail is not None else "")
        )


def _stable_cleanup_error(reason: str, error: BaseException) -> BaseException:
    if isinstance(error, ResearchProjectV2Error):
        return error
    if isinstance(error, _CONTROL_FLOW_EXCEPTIONS) or not isinstance(error, Exception):
        return error
    wrapped = _storage_failed(reason, exception_type=type(error).__name__)
    wrapped.__cause__ = error
    return wrapped


def _verify_live(
    path: Path,
    held_chain: list[int],
    final_name: str,
    held_final: os.stat_result,
    expected: bytes | int | tuple[str, str] | None,
) -> bool:
    live: list[int] = []
    final_fd: int | None = None
    try:
        live.append(os.open("/", _directory_flags()))
        if not _same_inode(os.fstat(live[0]), os.fstat(held_chain[0])):
            return False
        for index, name in enumerate(path.parts[1:], start=1):
            live.append(os.open(name, _directory_flags(), dir_fd=live[-1]))
            if not _same_inode(os.fstat(live[-1]), os.fstat(held_chain[index])):
                return False
        final_fd, opened = _open_regular(live[-1], final_name)
        content_matches = (
            True
            if expected is None
            else _descriptor_sha256(final_fd) == expected[1]
            if isinstance(expected, tuple) and expected[0] == "sha256"
            else _descriptors_equal(final_fd, expected)
            if isinstance(expected, int)
            else _read_all(final_fd) == expected
        )
        return _same_inode(opened, held_final) and content_matches
    except (OSError, ResearchProjectV2Error):
        return False
    finally:
        if final_fd is not None:
            os.close(final_fd)
        for descriptor in reversed(live):
            os.close(descriptor)


@dataclass
class _RawTemp:
    chain: list[int]
    names: list[str]
    directory_fd: int
    fd: int
    name: str
    inode: os.stat_result | None = None

    def cleanup(self) -> None:
        cleanup_errors: list[BaseException] = []
        try:
            if self.inode is None:
                self.inode = os.fstat(self.fd)
            _unlink_temp_if_bound(self.directory_fd, self.name, self.inode)
        except BaseException as exc:
            cleanup_errors.append(exc)
        try:
            os.close(self.fd)
        except OSError as exc:
            cleanup_errors.append(exc)
        for descriptor in reversed(self.chain):
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            error = _stable_cleanup_error(
                "raw temporary cleanup failed", cleanup_errors[0]
            )
            for additional in cleanup_errors[1:]:
                error.add_note(
                    f"additional cleanup failure: {type(additional).__name__}"
                )
            raise error


def _new_raw_temp(layout: LayeredResearchLayout) -> _RawTemp:
    chain: list[int] = []
    try:
        chain, names = _open_dir_chain(layout.evidence_raw_dir / ".tmp")
        if not _chain_bound(chain, names):
            raise _storage_error("unsafe raw temporary directory")
        fd, name = _create_temp(chain[-1], "snapshot")
        return _RawTemp(chain, names, chain[-1], fd, name)
    except BaseException as primary_error:
        for descriptor in reversed(chain):
            try:
                os.close(descriptor)
            except OSError as cleanup_error:
                primary_error.add_note(
                    "additional cleanup failure: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
        raise


def _publish_raw(temp: _RawTemp, *, layout: LayeredResearchLayout, digest: str, extension: str) -> Path:
    final_dir = layout.evidence_raw_dir / digest[:2]
    final_name = f"{digest}.{extension}"
    target = final_dir / final_name
    chain: list[int] = []
    held_fd: int | None = None
    created = False
    final_directory_stat: os.stat_result | None = None
    result: Path | None = None
    primary_error: BaseException | None = None
    cleanup_errors: list[BaseException] = []
    try:
        chain, names = _open_dir_chain(final_dir)
        final_directory_stat = os.fstat(chain[-1])
        if not _chain_bound(chain, names) or not _chain_bound(temp.chain, temp.names):
            raise _storage_error("unsafe raw directory binding")
        temp.inode = os.fstat(temp.fd)
        entry = os.stat(temp.name, dir_fd=temp.directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(temp.inode.st_mode) or not _same_inode(temp.inode, entry):
            raise _storage_error("raw temporary binding changed")
        try:
            os.link(temp.name, final_name, src_dir_fd=temp.directory_fd, dst_dir_fd=chain[-1], follow_symlinks=False)
            created = True
            os.fsync(chain[-1])
        except FileExistsError:
            pass
        except OSError as exc:
            raise _storage_error("raw publication failed", path=str(target)) from exc
        held_fd, held = _open_regular(chain[-1], final_name)
        if created and not _same_inode(held, temp.inode):
            raise _storage_error("published raw inode changed", path=str(target))
        if os.fstat(held_fd).st_size != temp.inode.st_size:
            raise _immutability("raw content-address conflict", path=str(target))
        os.lseek(temp.fd, 0, os.SEEK_SET)
        os.lseek(held_fd, 0, os.SEEK_SET)
        while True:
            expected = os.read(temp.fd, 1024 * 1024)
            actual = os.read(held_fd, 1024 * 1024)
            if actual != expected:
                raise _immutability("raw content-address conflict", path=str(target))
            if not expected:
                break
        if not _chain_bound(chain, names) or not _verify_live(
            final_dir, chain, final_name, held, ("sha256", digest)
        ):
            raise _storage_error("raw final binding changed", path=str(target))
        result = target
    except BaseException as exc:
        if isinstance(exc, (ResearchProjectV2Error, *_CONTROL_FLOW_EXCEPTIONS)) or not isinstance(exc, Exception):
            primary_error = exc
        else:
            primary_error = _storage_error(
                "raw publication failed", path=str(target)
            )
            primary_error.__cause__ = exc

    final_directory_fd = chain[-1] if chain else None
    rollback_fd: int | None = None
    if created and final_directory_fd is not None:
        try:
            rollback_fd = os.dup(final_directory_fd)
            if not stat.S_ISDIR(os.fstat(rollback_fd).st_mode):
                raise OSError(errno.ENOTDIR, "rollback descriptor is not a directory")
        except OSError as exc:
            cleanup_errors.append(exc)
            if rollback_fd is not None:
                try:
                    os.close(rollback_fd)
                except OSError as close_exc:
                    cleanup_errors.append(close_exc)
                rollback_fd = None

    if held_fd is not None:
        try:
            os.close(held_fd)
        except OSError as exc:
            cleanup_errors.append(exc)

    for descriptor in reversed(chain[:-1]):
        try:
            os.close(descriptor)
        except OSError as exc:
            cleanup_errors.append(exc)

    if primary_error is None and cleanup_errors:
        primary_error = _stable_cleanup_error(
            "raw publisher cleanup failed", cleanup_errors[0]
        )

    rollback_recorded = False
    if (
        primary_error is not None
        and created
        and temp.inode is not None
        and final_directory_fd is not None
    ):
        outcome, detail = _rollback_created_final(
            rollback_fd if rollback_fd is not None else final_directory_fd,
            final_name,
            temp.inode,
        )
        _record_rollback(primary_error, outcome, detail)
        rollback_recorded = True

    if final_directory_fd is not None:
        try:
            os.close(final_directory_fd)
        except OSError as exc:
            cleanup_errors.append(exc)
            if primary_error is None:
                primary_error = _stable_cleanup_error(
                    "raw publisher cleanup failed", exc
                )
            if created and temp.inode is not None and not rollback_recorded:
                outcome, detail = _rollback_created_final(
                    rollback_fd if rollback_fd is not None else final_directory_fd,
                    final_name,
                    temp.inode,
                )
                _record_rollback(primary_error, outcome, detail)
                rollback_recorded = True

    if rollback_fd is not None:
        try:
            os.close(rollback_fd)
        except OSError as exc:
            cleanup_errors.append(exc)
            if primary_error is None:
                primary_error = _stable_cleanup_error(
                    "raw publisher cleanup failed", exc
                )
            if (
                created
                and temp.inode is not None
                and final_directory_stat is not None
                and not rollback_recorded
            ):
                outcome, detail, recovery_errors = (
                    _rollback_created_final_via_live_path(
                        final_dir,
                        final_directory_stat,
                        final_name,
                        temp.inode,
                    )
                )
                cleanup_errors.extend(recovery_errors)
                _record_rollback(primary_error, outcome, detail)
                rollback_recorded = True

    if primary_error is not None:
        for index, cleanup_error in enumerate(cleanup_errors):
            if index == 0 and primary_error.__cause__ is cleanup_error:
                continue
            primary_error.add_note(
                "additional cleanup failure: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        raise primary_error

    assert result is not None
    return result


def _publish_bytes(directory: Path, final_name: str, data: bytes) -> Path:
    target = directory / final_name
    chain: list[int] = []
    temp_fd: int | None = None
    temp_name: str | None = None
    temp_inode: os.stat_result | None = None
    held_fd: int | None = None
    primary_error: BaseException | None = None
    try:
        chain, names = _open_dir_chain(directory)
        if not _chain_bound(chain, names):
            raise _storage_error("unsafe metadata directory binding")
        temp_fd, temp_name = _create_temp(chain[-1], final_name)
        try:
            _write_all(temp_fd, data)
            os.fsync(temp_fd)
        except OSError as exc:
            raise _storage_error("metadata write failed", path=str(target)) from exc
        temp_inode = os.fstat(temp_fd)
        try:
            os.link(temp_name, final_name, src_dir_fd=chain[-1], dst_dir_fd=chain[-1], follow_symlinks=False)
            os.fsync(chain[-1])
            created = True
        except FileExistsError:
            created = False
        except OSError as exc:
            raise _storage_error("metadata publication failed", path=str(target)) from exc
        held_fd, held = _open_regular(chain[-1], final_name)
        if created and not _same_inode(held, temp_inode):
            raise _storage_error("published metadata inode changed", path=str(target))
        try:
            existing_data = _read_all(held_fd)
        except OSError as exc:
            raise _storage_error(
                "metadata read failed", path=str(target)
            ) from exc
        if existing_data != data:
            raise _immutability("metadata path conflict", path=str(target))
        try:
            _unlink_temp_if_bound(chain[-1], temp_name, temp_inode)
        except OSError as exc:
            raise _storage_failed("metadata temporary cleanup failed") from exc
        temp_name = None
        if not _chain_bound(chain, names) or not _verify_live(directory, chain, final_name, held, data):
            raise _storage_error("metadata final binding changed", path=str(target))
        return target
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        cleanup_errors: list[BaseException] = []
        if held_fd is not None:
            try:
                os.close(held_fd)
            except OSError as exc:
                cleanup_errors.append(exc)
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except OSError as exc:
                cleanup_errors.append(exc)
        if temp_name is not None and temp_inode is not None and chain:
            try:
                _unlink_temp_if_bound(chain[-1], temp_name, temp_inode)
            except BaseException as exc:
                cleanup_errors.append(exc)
        for descriptor in reversed(chain):
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            cleanup = _stable_cleanup_error(
                "metadata temporary cleanup failed", cleanup_errors[0]
            )
            if primary_error is not None:
                primary_error.add_note(
                    "cleanup failure preserved: "
                    f"{getattr(cleanup, 'code', type(cleanup).__name__)}"
                )
            else:
                raise cleanup


def snapshot_candidate(
    candidate: dict[str, Any],
    *,
    transport: FetchTransport,
    resolver: AddressResolver,
    layout: LayeredResearchLayout | None = None,
    fetched_at: str,
    provenance: dict[str, Any],
    timeout_seconds: float = 20.0,
    max_redirects: int = 5,
    max_bytes: int = 25 * 1024 * 1024,
) -> dict[str, Any]:
    """Fetch and immutably snapshot one included industry source candidate."""
    copied = _validate_candidate(candidate)
    fetched_at = _parse_fetched_at(fetched_at)
    provenance = _validate_provenance(provenance, field="provenance")
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise _snapshot_invalid("timeout_seconds must be positive")
    if not isinstance(max_redirects, int) or isinstance(max_redirects, bool) or max_redirects < 0:
        raise _snapshot_invalid("max_redirects must be non-negative")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
        raise _snapshot_invalid("max_bytes must be non-negative")
    _require_storage_capability()

    current = copied["normalized_url"]
    visited = {current}
    redirect_chain: list[str] = []
    final_response: FetchResponse | None = None
    saved_headers: dict[str, str] = {}
    media_type = ""
    declared_length: int | None = None
    while True:
        approved = _approved_addresses(current, resolver)
        try:
            response = transport.get(current, timeout_seconds=float(timeout_seconds))
        except ResearchProjectV2Error:
            raise
        except _CONTROL_FLOW_EXCEPTIONS:
            raise
        except Exception as exc:
            raise _error("FETCH_TRANSPORT_ERROR", "HTTP request failed", url=current) from exc
        if not isinstance(response, FetchResponse):
            raise _error("FETCH_TRANSPORT_ERROR", "transport returned an invalid response")
        try:
            try:
                response_url = normalize_url(response.url)
            except ResearchProjectV2Error as exc:
                raise _error("FETCH_TRANSPORT_ERROR", "transport reported an invalid URL") from exc
            if response_url != current or response.url != current:
                raise _error("FETCH_TRANSPORT_ERROR", "transport-reported URL does not match request")
            _validate_peer(response.peer_ip, approved)
            if response.status_code in _REDIRECT_STATUSES:
                location_values = [
                    value for key, value in response.headers.items()
                    if isinstance(key, str) and key.lower() == "location"
                ] if isinstance(response.headers, Mapping) else []
                if len(location_values) != 1 or not isinstance(location_values[0], str) or not location_values[0]:
                    raise _error("FETCH_REDIRECT_INVALID", "redirect requires one non-empty Location")
                if len(redirect_chain) >= max_redirects:
                    raise _error("FETCH_REDIRECT_LIMIT", "redirect limit exceeded")
                try:
                    target = normalize_url(urljoin(current, location_values[0]))
                except ResearchProjectV2Error as exc:
                    raise _error("FETCH_REDIRECT_INVALID", "redirect target is invalid") from exc
                if target in visited:
                    raise _error("FETCH_REDIRECT_LOOP", "redirect loop detected")
                visited.add(target)
                redirect_chain.append(target)
                current = target
                _close_chunks(response)
                continue
            if not isinstance(response.status_code, int) or isinstance(response.status_code, bool) or not 200 <= response.status_code <= 299:
                raise _error("FETCH_STATUS_INVALID", "HTTP status is not successful", status_code=response.status_code)
            saved_headers, media_type, declared_length = _headers(response.headers)
            if declared_length is not None and declared_length > max_bytes:
                raise _error("FETCH_TOO_LARGE", "Content-Length exceeds maximum", max_bytes=max_bytes)
            final_response = response
            break
        except BaseException:
            _close_chunks(response)
            raise

    assert final_response is not None
    effective_layout = LayeredResearchLayout.default() if layout is None else layout
    raw_temp: _RawTemp | None = None
    digest = sha256()
    byte_count = 0
    primary_error: BaseException | None = None
    try:
        raw_temp = _new_raw_temp(effective_layout)
        try:
            for chunk in final_response.chunks:
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise _error("FETCH_STREAM_ERROR", "response chunk is not bytes-like")
                data = bytes(chunk)
                if not data:
                    continue
                byte_count += len(data)
                if byte_count > max_bytes:
                    raise _error("FETCH_TOO_LARGE", "response body exceeds maximum", max_bytes=max_bytes)
                digest.update(data)
                try:
                    _write_all(raw_temp.fd, data)
                except OSError as exc:
                    raise _storage_error("raw temporary write failed") from exc
        except ResearchProjectV2Error:
            raise
        except _CONTROL_FLOW_EXCEPTIONS:
            raise
        except Exception as exc:
            raise _error("FETCH_STREAM_ERROR", "response stream failed") from exc
        if declared_length is not None and declared_length != byte_count:
            raise _error(
                "FETCH_CONTENT_LENGTH_INVALID",
                "Content-Length does not match response body",
                declared_length=declared_length,
                byte_count=byte_count,
            )
        try:
            os.fsync(raw_temp.fd)
        except OSError as exc:
            raise _storage_error("raw temporary sync failed") from exc
        content_digest = digest.hexdigest()
        extension = _MEDIA_EXTENSIONS[media_type]
        raw_relative = f"evidence/raw/{content_digest[:2]}/{content_digest}.{extension}"
        artifact_digest = sha256(
            f"{copied['candidate_id']}\n{content_digest}".encode("utf-8")
        ).hexdigest()
        artifact = {
            "artifact_id": f"evidence_artifact:{artifact_digest[:24]}",
            "candidate_id": copied["candidate_id"],
            "evidence_channel": "industry",
            "original_url": copied["original_url"],
            "final_url": current,
            "redirect_chain": redirect_chain,
            "status_code": final_response.status_code,
            "response_headers": saved_headers,
            "media_type": media_type,
            "byte_count": byte_count,
            "content_sha256": content_digest,
            "fetched_at": fetched_at,
            "raw_path": raw_relative,
            "provenance": deepcopy(provenance),
        }
        wrapper = {
            "schema_version": "2.1.0",
            "artifact_kind": "evidence_artifact",
            "evidence_artifact": artifact,
        }
        validate_v2_1_schema_payload("evidence_artifact_v2_1", wrapper)
        raw_target = _publish_raw(
            raw_temp,
            layout=effective_layout,
            digest=content_digest,
            extension=extension,
        )
        metadata_target = _publish_bytes(
            effective_layout.evidence_metadata_dir,
            f"{artifact['artifact_id']}.json",
            canonical_bytes(wrapper),
        )
        return {
            "artifact": deepcopy(artifact),
            "raw_path": raw_target,
            "metadata_path": metadata_target,
        }
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        _close_chunks(final_response)
        if raw_temp is not None:
            try:
                raw_temp.cleanup()
            except BaseException as cleanup_error:
                if primary_error is not None:
                    primary_error.add_note(
                        "cleanup failure preserved: "
                        f"{getattr(cleanup_error, 'code', type(cleanup_error).__name__)}"
                    )
                else:
                    raise
