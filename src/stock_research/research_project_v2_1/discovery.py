from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
import errno
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Protocol
import unicodedata
from urllib.parse import parse_qsl, unquote_to_bytes, urlencode, urlsplit, urlunsplit

import idna

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


TRACKING_QUERY_KEYS = {"spm", "from", "ref", "source"}

_BATCH_FIELDS = {
    "search_plan_id",
    "executed_query_ids",
    "provider",
    "discovered_at",
    "candidates",
    "policy_excluded_results",
    "content_hash",
}
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
_SAFE_PLAN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9:_-]*")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_RFC3339 = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
_STOCK_OPINION_CLASSES = {"stock_opinion", "equity_research"}
_STOCK_OPINION_PHRASES = {
    "目标价",
    "买入评级",
    "卖出评级",
    "增持评级",
    "建议买入",
    "股票推荐",
    "最强龙头",
    "受益标的",
    "估值最低",
    "target price",
    "price target",
    "buy rating",
    "sell rating",
    "strong buy",
    "top stock picks",
    "stock pick",
    "company ranking",
}
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_RFC3986_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
_DIR_FD_CAPABLE = (
    {os.open, os.mkdir, os.link, os.unlink, os.stat}.issubset(os.supports_dir_fd)
    and os.link in os.supports_follow_symlinks
    and os.stat in os.supports_follow_symlinks
)


def _invalid(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Invalid industry source discovery: {reason}",
        code="RESEARCH_PROJECT_V2_1_DISCOVERY_INVALID",
        details={"reason": reason, **details},
    )


def _immutability_error(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Immutable discovery batch failed verification: {reason}",
        code="RESEARCH_PROJECT_V2_1_DISCOVERY_IMMUTABILITY_VIOLATION",
        details={"reason": reason, **details},
    )


def _url_invalid(url: object, reason: str) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Invalid discovery URL: {reason}",
        code="RESEARCH_PROJECT_V2_1_DISCOVERY_URL_INVALID",
        details={"url": url, "reason": reason},
    )


def _trimmed_string(value: object, *, field: str, reason: str | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(reason or f"blank {field}", field=field)
    return value.strip()


def _canonical_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"blank {field}", field=field)
    if value != value.strip():
        raise _invalid(f"non-canonical {field}", field=field)
    return value


def _strict_query_id(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _invalid("invalid query_id", query_id=value)
    return value


def _parse_datetime(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or _RFC3339.fullmatch(value) is None
    ):
        raise _invalid(f"invalid {field}", field=field)
    text = value
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid(f"invalid {field}", field=field) from exc
    if parsed.tzinfo is None:
        raise _invalid(f"invalid {field}", field=field)
    return text


def _validated_percent_component(value: str, *, component: str) -> str:
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise ValueError(f"invalid percent escape in {component}")
    try:
        unquote_to_bytes(value).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"invalid UTF-8 percent bytes in {component}") from exc
    return re.sub(
        r"%[0-9A-Fa-f]{2}", lambda match: match.group(0).upper(), value
    )


def _decode_percent_encoded_unreserved(path: str) -> str:
    def replace(match: re.Match[str]) -> str:
        character = chr(int(match.group(0)[1:], 16))
        return character if character in _RFC3986_UNRESERVED else match.group(0)

    return re.sub(r"%[0-9A-F]{2}", replace, path)


def _remove_last_path_segment(output: str) -> str:
    separator = output.rfind("/")
    return "" if separator < 0 else output[:separator]


def _remove_dot_segments(path: str) -> str:
    remaining = path
    output = ""
    while remaining:
        if remaining.startswith("../"):
            remaining = remaining[3:]
        elif remaining.startswith("./"):
            remaining = remaining[2:]
        elif remaining.startswith("/./"):
            remaining = "/" + remaining[3:]
        elif remaining == "/.":
            remaining = "/"
        elif remaining.startswith("/../"):
            remaining = "/" + remaining[4:]
            output = _remove_last_path_segment(output)
        elif remaining == "/..":
            remaining = "/"
            output = _remove_last_path_segment(output)
        elif remaining in {".", ".."}:
            remaining = ""
        else:
            separator = remaining.find("/", 1 if remaining.startswith("/") else 0)
            if separator < 0:
                output += remaining
                remaining = ""
            else:
                output += remaining[:separator]
                remaining = remaining[separator:]
    return output


def normalize_url(url: str) -> str:
    """Return a deterministic HTTP(S) URL without tracking parameters."""
    if not isinstance(url, str) or not url.strip():
        raise _url_invalid(url, "blank URL")
    raw = url
    try:
        if any(
            character == "\\"
            or character.isspace()
            or unicodedata.category(character) == "Cc"
            for character in raw
        ):
            raise ValueError("URL contains forbidden whitespace or control characters")
        scheme_separator = raw.find("://")
        if scheme_separator >= 0:
            authority = re.split(r"[/\?#]", raw[scheme_separator + 3 :], maxsplit=1)[0]
            authority_host = authority.rsplit("@", 1)[-1]
            if authority_host.endswith(":"):
                raise ValueError("empty port")
        parsed = urlsplit(raw)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError("unsupported scheme")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("userinfo is forbidden")
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("missing host")
        port = parsed.port

        if ":" in hostname:
            if "%" in hostname:
                raise ValueError("scoped IPv6 hosts are forbidden")
            address = ipaddress.ip_address(hostname)
            if not isinstance(address, ipaddress.IPv6Address):
                raise ValueError("invalid IPv6 host")
            host = f"[{address.compressed}]"
        else:
            dns_input = hostname[:-1] if hostname.endswith(".") else hostname
            if not dns_input:
                raise ValueError("invalid host")
            ascii_host = idna.encode(
                dns_input,
                uts46=True,
                transitional=False,
                std3_rules=True,
            ).decode("ascii").lower()
            if all(character.isdigit() or character == "." for character in ascii_host):
                host = str(ipaddress.IPv4Address(ascii_host))
            else:
                if len(ascii_host) > 253:
                    raise ValueError("DNS host exceeds 253 characters")
                labels = ascii_host.split(".")
                if any(
                    _DNS_LABEL.fullmatch(label) is None
                    for label in labels
                ):
                    raise ValueError("invalid DNS label")
                host = ascii_host

        if port is not None and not (
            (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        ):
            host = f"{host}:{port}"

        path = _remove_dot_segments(
            _decode_percent_encoded_unreserved(
                _validated_percent_component(parsed.path or "/", component="path")
            )
        )
        canonical_query = _validated_percent_component(parsed.query, component="query")
        query_pairs = [
            (key, value)
            for key, value in parse_qsl(
                canonical_query,
                keep_blank_values=True,
                encoding="utf-8",
                errors="strict",
            )
            if not (
                key.casefold().startswith("utm_")
                or key.casefold() in TRACKING_QUERY_KEYS
            )
        ]
        query_pairs.sort(key=lambda pair: (pair[0], pair[1]))
        return urlunsplit((scheme, host, path, urlencode(query_pairs), ""))
    except (UnicodeError, ValueError) as exc:
        reason = str(exc).strip() or "malformed URL"
        raise _url_invalid(url, reason) from exc


def source_candidate_id(normalized_url: str, title: str) -> str:
    normalized = _trimmed_string(normalized_url, field="normalized_url")
    trimmed_title = _trimmed_string(title, field="title")
    digest = sha256(f"{normalized}\n{trimmed_title}".encode("utf-8")).hexdigest()
    return f"source_candidate:{digest[:24]}"


@dataclass(frozen=True)
class DiscoveryResult:
    url: str
    title: str
    snippet: str
    publisher: str | None
    publish_date: str | None
    source_class: str
    query_id: str
    rank: int


class DiscoveryProvider(Protocol):
    def search(self, query: dict[str, Any]) -> list[DiscoveryResult]: ...


class ImportedJsonDiscoveryProvider:
    """Offline provider backed by an explicitly supplied JSON result export."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            raw_results = payload["results"]
            if not isinstance(raw_results, list):
                raise TypeError("results is not a list")
            grouped: dict[str, list[DiscoveryResult]] = {}
            for raw in raw_results:
                if not isinstance(raw, dict):
                    raise TypeError("result is not an object")
                item = DiscoveryResult(**raw)
                grouped.setdefault(item.query_id, []).append(item)
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise _invalid(
                "invalid imported discovery JSON", path=str(self.path)
            ) from exc
        self.results_by_query = {
            query_id: list(results) for query_id, results in grouped.items()
        }

    def search(self, query: dict[str, Any]) -> list[DiscoveryResult]:
        query_id = _strict_query_id(query.get("query_id"))
        return list(self.results_by_query.get(query_id, []))


class DirectUrlDiscoveryProvider:
    """Convert direct URL query specs into results without network access."""

    def __init__(self, specs_by_query: dict[str, list[object]]) -> None:
        if not isinstance(specs_by_query, dict):
            raise _invalid("invalid direct URL specs")
        self.specs_by_query = deepcopy(specs_by_query)

    def search(self, query: dict[str, Any]) -> list[DiscoveryResult]:
        query_id = _strict_query_id(query.get("query_id"))
        raw_specs = self.specs_by_query.get(query_id, [])
        if not isinstance(raw_specs, list):
            raise _invalid("invalid direct URL specs", query_id=query_id)
        results: list[DiscoveryResult] = []
        for rank, spec in enumerate(raw_specs, start=1):
            if isinstance(spec, DiscoveryResult):
                if spec.query_id != query_id:
                    raise _invalid(
                        "mismatched query_id",
                        query_id=spec.query_id,
                        expected_query_id=query_id,
                    )
                results.append(spec)
                continue
            if isinstance(spec, str):
                values: dict[str, object] = {
                    "url": spec,
                    "title": spec,
                    "snippet": "",
                    "publisher": None,
                    "publish_date": None,
                    "source_class": "direct_url",
                }
            elif isinstance(spec, dict):
                values = dict(spec)
            else:
                raise _invalid("invalid direct URL spec", rank=rank)
            try:
                results.append(
                    DiscoveryResult(
                        url=values["url"],
                        title=values.get("title", values["url"]),
                        snippet=values.get("snippet", ""),
                        publisher=values.get("publisher"),
                        publish_date=values.get("publish_date"),
                        source_class=values.get("source_class", "direct_url"),
                        query_id=query_id,
                        rank=rank,
                    )
                )
            except KeyError as exc:
                raise _invalid("invalid direct URL spec", rank=rank) from exc
        return results


def _normalized_tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(
        "".join(character if character.isalnum() else " " for character in normalized).split()
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    text_tokens = _normalized_tokens(text)
    phrase_tokens = _normalized_tokens(phrase)
    if any("\u3400" <= char <= "\u9fff" for char in phrase):
        return "".join(phrase_tokens) in "".join(text_tokens)
    width = len(phrase_tokens)
    return width > 0 and any(
        text_tokens[index : index + width] == phrase_tokens
        for index in range(len(text_tokens) - width + 1)
    )


def _policy_reasons(
    source_class: str, *, title: str, snippet: str
) -> list[str]:
    reasons: list[str] = []
    normalized_class = unicodedata.normalize("NFKC", source_class).casefold().strip()
    if normalized_class in _STOCK_OPINION_CLASSES:
        reasons.append(f"forbidden source_class: {normalized_class}")
    combined = f"{title}\n{snippet}"
    for phrase in sorted(_STOCK_OPINION_PHRASES, key=str.casefold):
        if _contains_phrase(combined, phrase):
            reasons.append(f"stock-opinion phrase: {phrase}")
    return reasons


def _validate_provenance(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _PROVENANCE_FIELDS:
        raise _invalid("invalid provenance", field="provenance")
    _canonical_nonempty(value.get("created_by"), field="provenance.created_by")
    if value.get("actor_type") not in _ACTOR_TYPES:
        raise _invalid("invalid provenance", field="provenance.actor_type")
    if value.get("agent_run_id") is not None:
        _canonical_nonempty(
            value.get("agent_run_id"), field="provenance.agent_run_id"
        )
    _parse_datetime(value.get("created_at"), field="provenance.created_at")
    _canonical_nonempty(
        value.get("created_in_version"), field="provenance.created_in_version"
    )
    if value.get("review_status") not in _REVIEW_STATUSES:
        raise _invalid("invalid provenance", field="provenance.review_status")


def _validated_result(
    item: object,
    *,
    known_query_ids: set[str],
    expected_query_id: str,
) -> tuple[DiscoveryResult, str, str, str, str | None, str | None, str]:
    if not isinstance(item, DiscoveryResult):
        raise _invalid("invalid provider result type")
    query_id = _strict_query_id(item.query_id)
    if query_id not in known_query_ids:
        raise _invalid("unknown query_id", query_id=query_id)
    if query_id != expected_query_id:
        raise _invalid(
            "mismatched query_id", query_id=query_id, expected_query_id=expected_query_id
        )
    if isinstance(item.rank, bool) or not isinstance(item.rank, int) or item.rank <= 0:
        raise _invalid("invalid rank", query_id=query_id)
    title = _canonical_nonempty(item.title, field="title")
    original_url = _canonical_nonempty(item.url, field="URL")
    source_class = _canonical_nonempty(item.source_class, field="source_class")
    if not isinstance(item.snippet, str):
        raise _invalid("invalid snippet", query_id=query_id)
    if item.snippet != item.snippet.strip():
        raise _invalid("non-canonical snippet", query_id=query_id)
    snippet = item.snippet
    if item.publisher is not None and not isinstance(item.publisher, str):
        raise _invalid("invalid publisher", query_id=query_id)
    if isinstance(item.publisher, str):
        publisher = _canonical_nonempty(item.publisher, field="publisher")
    else:
        publisher = None
    publish_date = item.publish_date
    if publish_date is not None:
        if not isinstance(publish_date, str):
            raise _invalid("invalid publish_date", query_id=query_id)
        try:
            parsed_date = date.fromisoformat(publish_date)
        except ValueError as exc:
            raise _invalid("invalid publish_date", query_id=query_id) from exc
        if parsed_date.isoformat() != publish_date:
            raise _invalid("invalid publish_date", query_id=query_id)
    return item, original_url, title, snippet, publisher, publish_date, source_class


def _candidate_from_result(
    validated: tuple[DiscoveryResult, str, str, str, str | None, str | None, str],
    *,
    search_plan_id: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    item, original_url, title, snippet, publisher, publish_date, source_class = validated
    normalized_url = normalize_url(original_url)
    reasons = _policy_reasons(source_class, title=title, snippet=snippet)
    return {
        "candidate_id": source_candidate_id(normalized_url, title),
        "search_plan_id": search_plan_id,
        "query_id": item.query_id,
        "normalized_url": normalized_url,
        "original_url": original_url,
        "title": title,
        "snippet": snippet,
        "publisher": publisher,
        "publish_date": publish_date,
        "source_class": source_class,
        "rank": item.rank,
        "exclusion_status": "excluded_by_policy" if reasons else "included",
        "exclusion_reasons": reasons,
        "dedup_key": normalized_url,
        "provenance": deepcopy(provenance),
    }


def _deduplicate(
    candidates: list[dict[str, Any]], priorities: dict[str, int]
) -> list[dict[str, Any]]:
    aliases_by_url: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        aliases_by_url.setdefault(candidate["normalized_url"], []).append(candidate)
    winners: list[dict[str, Any]] = []
    for aliases in aliases_by_url.values():
        included = [
            candidate
            for candidate in aliases
            if candidate["exclusion_status"] == "included"
        ]
        eligible = included or aliases
        winners.append(
            min(
                eligible,
                key=lambda candidate: (
                    priorities[candidate["query_id"]],
                    candidate["rank"],
                    candidate["candidate_id"],
                    candidate["title"],
                ),
            )
        )
    return sorted(
        winners,
        key=lambda candidate: (
            priorities[candidate["query_id"]],
            candidate["normalized_url"],
            candidate["candidate_id"],
        ),
    )


def _validated_plan(search_plan: object) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    if not isinstance(search_plan, dict):
        raise _invalid("invalid search plan")
    plan_id = _canonical_nonempty(
        search_plan.get("search_plan_id"), field="search_plan_id"
    )
    queries = search_plan.get("queries")
    if not isinstance(queries, list) or not queries:
        raise _invalid("invalid queries", field="queries")
    normalized_queries: list[dict[str, Any]] = []
    priorities: dict[str, int] = {}
    used_priorities: set[int] = set()
    for raw_query in queries:
        if not isinstance(raw_query, dict):
            raise _invalid("invalid query", field="queries")
        query_id = _strict_query_id(raw_query.get("query_id"))
        priority = raw_query.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority <= 0:
            raise _invalid("invalid query priority", query_id=query_id)
        if query_id in priorities:
            raise _invalid("duplicate query_id", query_id=query_id)
        if priority in used_priorities:
            raise _invalid("duplicate query priority", priority=priority)
        priorities[query_id] = priority
        used_priorities.add(priority)
        normalized_queries.append(deepcopy(raw_query))
    normalized_queries.sort(key=lambda query: (priorities[query["query_id"]], query["query_id"]))
    return plan_id, normalized_queries, priorities


def _validate_search_plan_schema(search_plan: object) -> None:
    if not isinstance(search_plan, dict):
        raise ResearchProjectV2Error(
            "Invalid discovery search plan",
            code="RESEARCH_PROJECT_V2_1_DISCOVERY_PLAN_INVALID",
            details={"path": ["search_plan"]},
        )
    try:
        validate_v2_1_schema_payload(
            "search_plan_v2_1",
            {
                "schema_version": "2.1.0",
                "artifact_kind": "search_plan",
                "search_plan": deepcopy(search_plan),
            },
        )
    except ResearchProjectV2Error as exc:
        raw_path = exc.details.get("path", ["search_plan"])
        path = list(raw_path) if isinstance(raw_path, list) else ["search_plan"]
        fields = re.findall(r"'([^']+)'", str(exc))
        if fields and fields[0] not in path:
            path.append(fields[0])
        raise ResearchProjectV2Error(
            "Invalid discovery search plan",
            code="RESEARCH_PROJECT_V2_1_DISCOVERY_PLAN_INVALID",
            details={"path": path},
        ) from exc


def discover_sources(
    search_plan: dict[str, Any],
    provider: DiscoveryProvider,
    *,
    provider_name: str,
    discovered_at: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Execute an offline discovery provider and build one canonical batch."""
    _validate_search_plan_schema(search_plan)
    plan_id, queries, priorities = _validated_plan(search_plan)
    normalized_provider = _canonical_nonempty(provider_name, field="provider")
    normalized_time = _parse_datetime(discovered_at, field="discovered_at")
    _validate_provenance(provenance)
    known_query_ids = set(priorities)
    discovered: list[dict[str, Any]] = []
    executed: list[str] = []
    for query in queries:
        query_id = query["query_id"]
        try:
            raw_results = provider.search(deepcopy(query))
        except ResearchProjectV2Error:
            raise
        except (MemoryError, KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise ResearchProjectV2Error(
                "Discovery provider failed",
                code="RESEARCH_PROJECT_V2_1_DISCOVERY_PROVIDER_FAILED",
                details={
                    "provider": normalized_provider,
                    "query_id": query_id,
                    "exception_type": type(exc).__name__,
                },
            ) from exc
        if not isinstance(raw_results, list):
            raise _invalid("invalid provider response type", query_id=query_id)
        executed.append(query_id)
        query_candidates: list[dict[str, Any]] = []
        for raw_result in raw_results:
            validated_result = _validated_result(
                raw_result,
                known_query_ids=known_query_ids,
                expected_query_id=query_id,
            )
            source_class = validated_result[-1]
            candidate = _candidate_from_result(
                validated_result,
                search_plan_id=plan_id,
                provenance=provenance,
            )
            if (
                candidate["exclusion_status"] == "included"
                and source_class not in query["source_classes"]
            ):
                raise _invalid(
                    "source_class not allowed for query",
                    query_id=query_id,
                    source_class=source_class,
                )
            query_candidates.append(candidate)
        query_candidates.sort(
            key=lambda candidate: (
                candidate["rank"],
                candidate["normalized_url"],
                candidate["candidate_id"],
                candidate["title"],
            )
        )
        discovered.extend(query_candidates[: search_plan["result_limit_per_query"]])

    winners = _deduplicate(discovered, priorities)

    batch: dict[str, Any] = {
        "search_plan_id": plan_id,
        "executed_query_ids": executed,
        "provider": normalized_provider,
        "discovered_at": normalized_time,
        "candidates": [
            candidate
            for candidate in winners
            if candidate["exclusion_status"] == "included"
        ],
        "policy_excluded_results": [
            candidate
            for candidate in winners
            if candidate["exclusion_status"] == "excluded_by_policy"
        ],
        "content_hash": "",
    }
    batch["content_hash"] = content_sha256(batch, excluded_paths={("content_hash",)})
    _validate_batch(batch)
    return batch


def _validate_candidate(candidate: object, *, expected_status: str) -> None:
    if not isinstance(candidate, dict) or set(candidate) != _CANDIDATE_FIELDS:
        raise _invalid("invalid candidate shape")
    for field in (
        "candidate_id",
        "search_plan_id",
        "query_id",
        "original_url",
        "title",
        "source_class",
        "dedup_key",
    ):
        _canonical_nonempty(candidate.get(field), field=field)
    normalized_url = normalize_url(candidate.get("normalized_url"))
    if candidate["normalized_url"] != normalized_url:
        raise _invalid("non-canonical normalized_url")
    if candidate["dedup_key"] != normalized_url:
        raise _invalid("invalid dedup_key")
    if normalize_url(candidate["original_url"]) != normalized_url:
        raise _invalid("original_url does not match normalized_url")
    if candidate["candidate_id"] != source_candidate_id(normalized_url, candidate["title"]):
        raise _invalid("invalid candidate_id")
    if not isinstance(candidate.get("snippet"), str):
        raise _invalid("invalid snippet")
    if candidate["snippet"] != candidate["snippet"].strip():
        raise _invalid("non-canonical snippet")
    if candidate.get("publisher") is not None and not isinstance(
        candidate.get("publisher"), str
    ):
        raise _invalid("invalid publisher")
    if isinstance(candidate.get("publisher"), str):
        _canonical_nonempty(candidate["publisher"], field="publisher")
    publish_date = candidate.get("publish_date")
    if publish_date is not None:
        if not isinstance(publish_date, str):
            raise _invalid("invalid publish_date")
        try:
            if date.fromisoformat(publish_date).isoformat() != publish_date:
                raise ValueError
        except ValueError as exc:
            raise _invalid("invalid publish_date") from exc
    rank = candidate.get("rank")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
        raise _invalid("invalid rank")
    if candidate.get("exclusion_status") != expected_status:
        raise _invalid("invalid exclusion_status")
    reasons = candidate.get("exclusion_reasons")
    if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
        raise _invalid("invalid exclusion_reasons")
    if expected_status == "included" and reasons:
        raise _invalid("included candidate has exclusion reasons")
    if expected_status == "excluded_by_policy" and not reasons:
        raise _invalid("excluded candidate lacks exclusion reasons")
    expected_reasons = _policy_reasons(
        candidate["source_class"],
        title=candidate["title"],
        snippet=candidate["snippet"],
    )
    if reasons != expected_reasons:
        raise _invalid("invalid exclusion_reasons")
    _validate_provenance(candidate.get("provenance"))


def _validate_batch(batch: object) -> dict[str, Any]:
    if not isinstance(batch, dict) or set(batch) != _BATCH_FIELDS:
        raise _invalid("invalid batch shape")
    _canonical_nonempty(batch.get("search_plan_id"), field="search_plan_id")
    _canonical_nonempty(batch.get("provider"), field="provider")
    _parse_datetime(batch.get("discovered_at"), field="discovered_at")
    executed = batch.get("executed_query_ids")
    if (
        not isinstance(executed, list)
        or not executed
        or not all(
            isinstance(item, str) and item and item == item.strip()
            for item in executed
        )
        or len(set(executed)) != len(executed)
    ):
        raise _invalid("invalid executed_query_ids")
    candidates = batch.get("candidates")
    excluded = batch.get("policy_excluded_results")
    if not isinstance(candidates, list) or not isinstance(excluded, list):
        raise _invalid("invalid candidate lists")
    for candidate in candidates:
        _validate_candidate(candidate, expected_status="included")
    for candidate in excluded:
        _validate_candidate(candidate, expected_status="excluded_by_policy")
    plan_id = batch["search_plan_id"]
    query_positions = {query_id: index for index, query_id in enumerate(executed)}
    for candidate in candidates + excluded:
        if candidate["search_plan_id"] != plan_id:
            raise _invalid("candidate search_plan_id mismatch")
        if candidate["query_id"] not in query_positions:
            raise _invalid("candidate query_id was not executed")
    for candidate_list in (candidates, excluded):
        expected_order = sorted(
            candidate_list,
            key=lambda candidate: (
                query_positions[candidate["query_id"]],
                candidate["normalized_url"],
                candidate["candidate_id"],
            ),
        )
        if candidate_list != expected_order:
            raise _invalid("non-canonical candidate order")
    all_keys = [candidate["normalized_url"] for candidate in candidates + excluded]
    if len(all_keys) != len(set(all_keys)):
        raise _invalid("duplicate normalized_url")
    embedded_hash = batch.get("content_hash")
    if not isinstance(embedded_hash, str) or _SHA256.fullmatch(embedded_hash) is None:
        raise _invalid("invalid content_hash")
    calculated = content_sha256(batch, excluded_paths={("content_hash",)})
    if embedded_hash != calculated:
        raise _immutability_error(
            "content_hash mismatch", expected=calculated, actual=embedded_hash
        )
    return batch


def _require_secure_dir_fd_storage() -> None:
    if (
        not getattr(os, "O_NOFOLLOW", 0)
        or not getattr(os, "O_DIRECTORY", 0)
        or not _DIR_FD_CAPABLE
    ):
        raise _invalid("secure dir-fd storage unavailable")


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _open_or_create_directory(parent_fd: int, name: str) -> int:
    created = False
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise _invalid("unsafe managed path", component=name) from exc
    if created:
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            raise _invalid("discovery batch write failed", component=name) from exc
    try:
        child_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
        if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
            os.close(child_fd)
            raise OSError(errno.ENOTDIR, "managed component is not a directory")
        return child_fd
    except OSError as exc:
        raise _invalid("unsafe managed path", component=name) from exc


def _open_absolute_directory(path: Path) -> tuple[list[int], list[str]]:
    if not path.is_absolute():
        raise _invalid("managed discovery path must be absolute", path=str(path))
    try:
        directory_fds = [os.open("/", _directory_flags())]
    except OSError as exc:
        raise _invalid("unsafe managed path", path="/") from exc
    component_names: list[str] = []
    try:
        for component in path.parts[1:]:
            if component in {"", ".", ".."}:
                raise _invalid("unsafe managed path", component=component)
            child_fd = _open_or_create_directory(directory_fds[-1], component)
            directory_fds.append(child_fd)
            component_names.append(component)
        return directory_fds, component_names
    except BaseException:
        for descriptor in reversed(directory_fds):
            os.close(descriptor)
        raise


def _entry_matches_directory(parent_fd: int, name: str, directory_fd: int) -> bool:
    try:
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    opened = os.fstat(directory_fd)
    return (
        stat.S_ISDIR(entry.st_mode)
        and entry.st_dev == opened.st_dev
        and entry.st_ino == opened.st_ino
    )


def _directory_chain_is_bound(
    directory_fds: list[int], component_names: list[str]
) -> bool:
    return len(directory_fds) == len(component_names) + 1 and all(
        _entry_matches_directory(
            directory_fds[index],
            name,
            directory_fds[index + 1],
        )
        for index, name in enumerate(component_names)
    )


def _read_regular_file_at(directory_fd: int, name: str) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise _invalid("unsafe managed path", target=name) from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise _invalid("unsafe managed path", target=name)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def _final_entry_is_regular_at(directory_fd: int, name: str) -> bool:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError:
        return False
    try:
        opened = os.fstat(descriptor)
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        return (
            stat.S_ISREG(opened.st_mode)
            and stat.S_ISREG(entry.st_mode)
            and opened.st_dev == entry.st_dev
            and opened.st_ino == entry.st_ino
        )
    except OSError:
        return False
    finally:
        os.close(descriptor)


def _read_descriptor_bytes(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _open_verified_final_at(
    directory_fd: int,
    name: str,
    expected: bytes,
    expected_inode: os.stat_result | None,
) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        opened = os.fstat(descriptor)
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(entry.st_mode)
            or opened.st_dev != entry.st_dev
            or opened.st_ino != entry.st_ino
            or (
                expected_inode is not None
                and not _same_inode(opened, expected_inode)
            )
            or _read_descriptor_bytes(descriptor) != expected
        ):
            raise OSError(errno.EIO, "final discovery artifact binding mismatch")
        return descriptor, opened
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise _invalid("unsafe managed path", target=name) from exc


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _verify_live_final_binding(
    directory_fds: list[int],
    component_names: list[str],
    plan_id: str,
    batch_fd: int,
    final_name: str,
    held_final: os.stat_result,
    expected: bytes,
) -> bool:
    live_fds: list[int] = []
    live_final_fd: int | None = None
    try:
        live_fds.append(os.open("/", _directory_flags()))
        if not _same_inode(os.fstat(live_fds[0]), os.fstat(directory_fds[0])):
            return False
        for index, component in enumerate(component_names, start=1):
            live_fds.append(
                os.open(component, _directory_flags(), dir_fd=live_fds[-1])
            )
            if not _same_inode(
                os.fstat(live_fds[-1]), os.fstat(directory_fds[index])
            ):
                return False
        live_fds.append(os.open(plan_id, _directory_flags(), dir_fd=live_fds[-1]))
        if not _same_inode(os.fstat(live_fds[-1]), os.fstat(batch_fd)):
            return False
        live_final_fd = os.open(
            final_name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=live_fds[-1],
        )
        live_final = os.fstat(live_final_fd)
        return (
            stat.S_ISREG(live_final.st_mode)
            and _same_inode(live_final, held_final)
            and _read_descriptor_bytes(live_final_fd) == expected
        )
    except OSError:
        return False
    finally:
        if live_final_fd is not None:
            os.close(live_final_fd)
        for descriptor in reversed(live_fds):
            os.close(descriptor)


def _unlink_and_sync(directory_fd: int, name: str) -> bool:
    try:
        os.unlink(name, dir_fd=directory_fd)
    except FileNotFoundError:
        return False
    os.fsync(directory_fd)
    return True


def _create_temp_file(directory_fd: int, final_name: str) -> tuple[int, str]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    for _ in range(128):
        name = f".{final_name}.{secrets.token_hex(16)}.tmp"
        try:
            return os.open(name, flags, 0o600, dir_fd=directory_fd), name
        except FileExistsError:
            continue
        except OSError as exc:
            raise _invalid("discovery batch write failed", target=name) from exc
    raise _invalid("discovery batch write failed", reason_detail="temp collision")


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short discovery batch write")
        offset += written
    os.fsync(descriptor)


def _complete_directory_binding_is_valid(
    directory_fds: list[int],
    component_names: list[str],
    discovery_fd: int,
    plan_id: str,
    batch_fd: int,
) -> bool:
    return (
        _directory_chain_is_bound(directory_fds, component_names)
        and _entry_matches_directory(discovery_fd, plan_id, batch_fd)
    )


def write_discovery_batch(
    batch: dict[str, Any], *, layout: LayeredResearchLayout | None = None
) -> Path:
    """Write an immutable batch without deleting a final name once published.

    A failure after the hard-link publication may leave a complete canonical
    final artifact. Cleanup is limited to the private temporary name so a
    concurrent replacement can never be deleted by a non-atomic stat/unlink.
    """
    raw_plan_id = batch.get("search_plan_id") if isinstance(batch, dict) else None
    if not isinstance(raw_plan_id, str) or _SAFE_PLAN_ID.fullmatch(raw_plan_id) is None:
        raise _invalid("unsafe search_plan_id", search_plan_id=raw_plan_id)
    validated = _validate_batch(batch)
    plan_id = validated["search_plan_id"]
    effective_layout = LayeredResearchLayout.default() if layout is None else layout
    discovery_dir = effective_layout.evidence_discovery_dir
    if not discovery_dir.is_absolute():
        raise _invalid(
            "managed discovery path must be absolute", path=str(discovery_dir)
        )
    _require_secure_dir_fd_storage()
    batch_dir = discovery_dir / plan_id
    final_name = f"{validated['content_hash']}.json"
    target = batch_dir / final_name
    data = canonical_bytes(validated)
    directory_fds: list[int] = []
    component_names: list[str] = []
    discovery_fd: int | None = None
    batch_fd: int | None = None
    temporary_fd: int | None = None
    temporary_name: str | None = None
    temporary_stat: os.stat_result | None = None
    final_created = False
    created_final_stat: os.stat_result | None = None
    held_final_fd: int | None = None
    try:
        directory_fds, component_names = _open_absolute_directory(discovery_dir)
        discovery_fd = directory_fds[-1]
        batch_fd = _open_or_create_directory(discovery_fd, plan_id)
        if not _complete_directory_binding_is_valid(
            directory_fds, component_names, discovery_fd, plan_id, batch_fd
        ):
            raise _invalid("unsafe managed path", path=str(batch_dir))
        temporary_fd, temporary_name = _create_temp_file(batch_fd, final_name)
        _write_all(temporary_fd, data)
        temporary_stat = os.fstat(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = None
        try:
            os.link(
                temporary_name,
                final_name,
                src_dir_fd=batch_fd,
                dst_dir_fd=batch_fd,
                follow_symlinks=False,
            )
            final_created = True
            created_final_stat = temporary_stat
            os.fsync(batch_fd)
        except FileExistsError:
            existing = _read_regular_file_at(batch_fd, final_name)
            if existing != data:
                raise _immutability_error(
                    "immutable batch path conflict", path=str(target)
                )
        except OSError as exc:
            raise _invalid("discovery batch write failed", path=str(target)) from exc
        if not _complete_directory_binding_is_valid(
            directory_fds, component_names, discovery_fd, plan_id, batch_fd
        ):
            raise _invalid("unsafe managed path", path=str(batch_dir))
        os.fsync(batch_fd)
        verified = _read_regular_file_at(batch_fd, final_name)
        if verified != data:
            raise _immutability_error(
                "immutable batch path conflict", path=str(target)
            )
        _unlink_and_sync(batch_fd, temporary_name)
        temporary_name = None
        if not _final_entry_is_regular_at(batch_fd, final_name):
            raise _invalid("unsafe managed path", path=str(target))
        try:
            held_final_fd, held_final_stat = _open_verified_final_at(
                batch_fd,
                final_name,
                data,
                created_final_stat if final_created else None,
            )
        except ResearchProjectV2Error:
            raise
        if not _verify_live_final_binding(
            directory_fds,
            component_names,
            plan_id,
            batch_fd,
            final_name,
            held_final_stat,
            data,
        ):
            raise _invalid("unsafe managed path", path=str(target))
        return target
    finally:
        if held_final_fd is not None:
            os.close(held_final_fd)
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_name is not None and batch_fd is not None:
            try:
                _unlink_and_sync(batch_fd, temporary_name)
            except FileNotFoundError:
                pass
        if batch_fd is not None:
            os.close(batch_fd)
        for descriptor in reversed(directory_fds):
            os.close(descriptor)
