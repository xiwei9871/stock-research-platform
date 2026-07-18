from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Protocol
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


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
_STOCK_OPINION_CLASSES = {"stock_opinion", "equity_research"}
_STOCK_OPINION_PHRASES = {
    "目标价",
    "买入评级",
    "卖出评级",
    "股票推荐",
    "最强龙头",
    "受益标的",
    "target price",
    "buy rating",
    "sell rating",
    "top stock",
    "stock pick",
}


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


def _trimmed_string(value: object, *, field: str, reason: str | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(reason or f"blank {field}", field=field)
    return value.strip()


def _parse_datetime(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"invalid {field}", field=field)
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid(f"invalid {field}", field=field) from exc
    if parsed.tzinfo is None:
        raise _invalid(f"invalid {field}", field=field)
    return text


def normalize_url(url: str) -> str:
    """Return a deterministic HTTP(S) URL without tracking parameters."""
    if not isinstance(url, str) or not url.strip():
        raise _invalid("invalid URL", field="url")
    raw = url.strip()
    try:
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

        try:
            ipv6 = ipaddress.IPv6Address(hostname)
        except ValueError:
            ascii_host = hostname.encode("idna").decode("ascii").lower()
            if not ascii_host or any(not label for label in ascii_host.split(".")):
                raise ValueError("invalid host")
            host = ascii_host
        else:
            host = f"[{ipv6.compressed}]"

        if port is not None and not (
            (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        ):
            host = f"{host}:{port}"

        query_pairs = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not (
                key.casefold().startswith("utm_")
                or key.casefold() in TRACKING_QUERY_KEYS
            )
        ]
        query_pairs.sort(key=lambda pair: (pair[0], pair[1]))
        path = parsed.path or "/"
        return urlunsplit((scheme, host, path, urlencode(query_pairs), ""))
    except (UnicodeError, ValueError) as exc:
        raise _invalid("invalid URL", field="url") from exc


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
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise _invalid(
                "invalid imported discovery JSON", path=str(self.path)
            ) from exc
        self.results_by_query = {
            query_id: list(results) for query_id, results in grouped.items()
        }

    def search(self, query: dict[str, Any]) -> list[DiscoveryResult]:
        query_id = query.get("query_id")
        if not isinstance(query_id, str):
            raise _invalid("invalid query_id", field="query_id")
        return list(self.results_by_query.get(query_id, []))


class DirectUrlDiscoveryProvider:
    """Convert direct URL query specs into results without network access."""

    def search(self, query: dict[str, Any]) -> list[DiscoveryResult]:
        query_id = _trimmed_string(query.get("query_id"), field="query_id")
        raw_specs = query.get("direct_urls", [])
        if not isinstance(raw_specs, list):
            raise _invalid("invalid direct_urls", field="direct_urls")
        results: list[DiscoveryResult] = []
        for rank, spec in enumerate(raw_specs, start=1):
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
    _trimmed_string(value.get("created_by"), field="provenance.created_by")
    if value.get("actor_type") not in _ACTOR_TYPES:
        raise _invalid("invalid provenance", field="provenance.actor_type")
    if value.get("agent_run_id") is not None and not isinstance(
        value.get("agent_run_id"), str
    ):
        raise _invalid("invalid provenance", field="provenance.agent_run_id")
    _parse_datetime(value.get("created_at"), field="provenance.created_at")
    _trimmed_string(
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
    query_id = _trimmed_string(item.query_id, field="query_id")
    if query_id not in known_query_ids:
        raise _invalid("unknown query_id", query_id=query_id)
    if query_id != expected_query_id:
        raise _invalid(
            "mismatched query_id", query_id=query_id, expected_query_id=expected_query_id
        )
    if isinstance(item.rank, bool) or not isinstance(item.rank, int) or item.rank <= 0:
        raise _invalid("invalid rank", query_id=query_id)
    title = _trimmed_string(item.title, field="title")
    original_url = _trimmed_string(item.url, field="url", reason="blank URL")
    source_class = _trimmed_string(item.source_class, field="source_class")
    if not isinstance(item.snippet, str):
        raise _invalid("invalid snippet", query_id=query_id)
    snippet = item.snippet.strip()
    if item.publisher is not None and not isinstance(item.publisher, str):
        raise _invalid("invalid publisher", query_id=query_id)
    publisher = item.publisher.strip() if isinstance(item.publisher, str) else None
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
        "query_id": item.query_id.strip(),
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
    winners: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate["normalized_url"]
        sort_key = (
            priorities[candidate["query_id"]],
            candidate["rank"],
            candidate["candidate_id"],
            candidate["title"],
        )
        current = winners.get(key)
        if current is None:
            winners[key] = candidate
            continue
        current_key = (
            priorities[current["query_id"]],
            current["rank"],
            current["candidate_id"],
            current["title"],
        )
        if sort_key < current_key:
            winners[key] = candidate
    return sorted(
        winners.values(),
        key=lambda candidate: (
            priorities[candidate["query_id"]],
            candidate["normalized_url"],
            candidate["candidate_id"],
        ),
    )


def _validated_plan(search_plan: object) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    if not isinstance(search_plan, dict):
        raise _invalid("invalid search plan")
    plan_id = _trimmed_string(search_plan.get("search_plan_id"), field="search_plan_id")
    queries = search_plan.get("queries")
    if not isinstance(queries, list) or not queries:
        raise _invalid("invalid queries", field="queries")
    normalized_queries: list[dict[str, Any]] = []
    priorities: dict[str, int] = {}
    used_priorities: set[int] = set()
    for raw_query in queries:
        if not isinstance(raw_query, dict):
            raise _invalid("invalid query", field="queries")
        query_id = _trimmed_string(raw_query.get("query_id"), field="query_id")
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


def discover_sources(
    search_plan: dict[str, Any],
    provider: DiscoveryProvider,
    *,
    provider_name: str,
    discovered_at: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Execute an offline discovery provider and build one canonical batch."""
    plan_id, queries, priorities = _validated_plan(search_plan)
    normalized_provider = _trimmed_string(provider_name, field="provider")
    normalized_time = _parse_datetime(discovered_at, field="discovered_at")
    _validate_provenance(provenance)
    known_query_ids = set(priorities)
    discovered: list[dict[str, Any]] = []
    executed: list[str] = []
    for query in queries:
        query_id = query["query_id"]
        raw_results = provider.search(deepcopy(query))
        if not isinstance(raw_results, list):
            raise _invalid("invalid provider response type", query_id=query_id)
        executed.append(query_id)
        for raw_result in raw_results:
            candidate = _candidate_from_result(
                _validated_result(
                    raw_result,
                    known_query_ids=known_query_ids,
                    expected_query_id=query_id,
                ),
                search_plan_id=plan_id,
                provenance=provenance,
            )
            discovered.append(candidate)

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
        _trimmed_string(candidate.get(field), field=field)
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
    if candidate.get("publisher") is not None and not isinstance(
        candidate.get("publisher"), str
    ):
        raise _invalid("invalid publisher")
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
    _trimmed_string(batch.get("search_plan_id"), field="search_plan_id")
    _trimmed_string(batch.get("provider"), field="provider")
    _parse_datetime(batch.get("discovered_at"), field="discovered_at")
    executed = batch.get("executed_query_ids")
    if (
        not isinstance(executed, list)
        or not executed
        or not all(isinstance(item, str) and item.strip() for item in executed)
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


def _require_safe_path(path: Path, layout: LayeredResearchLayout) -> None:
    try:
        relative = path.relative_to(layout.root)
    except ValueError as exc:
        raise _invalid("unsafe managed path", path=str(path)) from exc
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise _invalid("unsafe managed path", path=str(path))
    current = layout.root
    if current.is_symlink():
        raise _invalid("unsafe managed path", path=str(current))
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise _invalid("unsafe managed path", path=str(current))
    try:
        path.resolve(strict=False).relative_to(layout.root.resolve(strict=False))
    except (OSError, ValueError) as exc:
        raise _invalid("unsafe managed path", path=str(path)) from exc


def _safe_mkdir(path: Path, layout: LayeredResearchLayout) -> None:
    _require_safe_path(path, layout)
    current = layout.root
    try:
        if not current.exists():
            current.mkdir(parents=True)
        relative = path.relative_to(layout.root)
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise _invalid("unsafe managed path", path=str(current))
            current.mkdir(exist_ok=True)
            if not current.is_dir() or current.is_symlink():
                raise _invalid("unsafe managed path", path=str(current))
    except OSError as exc:
        raise _invalid("unsafe managed path", path=str(current)) from exc


def _atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_discovery_batch(
    batch: dict[str, Any], *, layout: LayeredResearchLayout | None = None
) -> Path:
    """Write a validated immutable discovery batch beneath managed storage."""
    raw_plan_id = batch.get("search_plan_id") if isinstance(batch, dict) else None
    if not isinstance(raw_plan_id, str) or _SAFE_PLAN_ID.fullmatch(raw_plan_id) is None:
        raise _invalid("unsafe search_plan_id", search_plan_id=raw_plan_id)
    validated = _validate_batch(batch)
    plan_id = validated["search_plan_id"]
    effective_layout = LayeredResearchLayout.default() if layout is None else layout
    batch_dir = effective_layout.evidence_discovery_dir / plan_id
    target = batch_dir / f"{validated['content_hash']}.json"
    _require_safe_path(target, effective_layout)
    _safe_mkdir(batch_dir, effective_layout)
    _require_safe_path(target, effective_layout)
    data = canonical_bytes(validated)
    if target.exists():
        if target.is_symlink() or not target.is_file():
            raise _invalid("unsafe managed path", path=str(target))
        try:
            existing = target.read_bytes()
        except OSError as exc:
            raise _invalid("discovery batch write failed", path=str(target)) from exc
        if existing == data:
            return target
        raise _immutability_error("immutable batch path conflict", path=str(target))
    try:
        _atomic_write(target, data)
    except OSError as exc:
        raise _invalid("discovery batch write failed", path=str(target)) from exc
    return target
