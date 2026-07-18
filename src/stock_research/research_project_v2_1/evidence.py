from __future__ import annotations

import errno
import json
import os
import re
import secrets
import stat
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.normalize import _validated_document
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_RFC3339 = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
_TARGET_TYPES = frozenset(
    {"research_project", "research_question", "research_claim", "causal_edge"}
)
_ROLES = frozenset(
    {"supports", "opposes", "quantifies", "defines", "boundary_evidence"}
)
_FRESHNESS = frozenset({"fresh", "stale", "future_dated", "unknown"})
_CONFLICT = frozenset({"none", "limited", "material_conflict", "unresolved"})
_COLLAPSING = frozenset(
    {
        "same_document",
        "republication",
        "same_publisher_family",
        "shared_upstream_source",
    }
)
_RELATIONSHIPS = _COLLAPSING | {"independent", "unknown"}
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_FILE_FLAGS = (
    os.O_RDONLY
    | os.O_NONBLOCK
    | os.O_NOFOLLOW
    | getattr(os, "O_CLOEXEC", 0)
)
_EXTENSIONS = {
    "application/pdf": "pdf",
    "text/html": "html",
    "text/plain": "txt",
    "application/json": "json",
    "text/csv": "csv",
}


def _invalid(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Industry evidence assessment invalid: {reason}",
        code="RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID",
        details={"reason": reason, **details},
    )


def _storage(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Industry evidence assessment storage failed: {reason}",
        code="RESEARCH_PROJECT_V2_1_EVIDENCE_STORAGE_FAILED",
        details={"reason": reason, **details},
    )


def _immutability(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Industry evidence assessment immutability violation: {reason}",
        code="RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION",
        details={"reason": reason, **details},
    )


def _validate_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(artifact)
    try:
        validate_v2_1_schema_payload(
            "evidence_artifact_v2_1",
            {
                "schema_version": "2.1.0",
                "artifact_kind": "evidence_artifact",
                "evidence_artifact": copied,
            },
        )
    except ResearchProjectV2Error as exc:
        raise _invalid("artifact is not canonical", path=exc.details.get("path")) from exc
    hashes = copied.get("section_hashes", [])
    if any(not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in hashes):
        raise _invalid("artifact section_hashes are invalid")
    if len(hashes) != len(set(hashes)):
        raise _invalid("artifact section_hashes contain duplicates")
    digest = copied["content_sha256"]
    expected_path = f"evidence/raw/{digest[:2]}/{digest}.{_EXTENSIONS[copied['media_type']]}"
    if copied["raw_path"] != expected_path:
        raise _invalid("artifact raw_path is not canonical")
    return copied


def _validate_definition(name: str, payload: dict[str, Any]) -> None:
    schema_dir = LayeredResearchLayout.default().schema_dir
    with (schema_dir / "definitions_v2_1.schema.json").open(encoding="utf-8") as handle:
        definitions = json.load(handle)
    schema = definitions["$defs"][name]
    validator = Draft202012Validator(
        schema,
        resolver=RefResolver.from_schema(
            definitions,
            store={"definitions_v2_1.schema.json": definitions},
        ),
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )
    if errors:
        raise _invalid(
            f"{name} does not satisfy schema", path=list(errors[0].absolute_path)
        )


def assess_source_relationship(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    left_copy = _validate_artifact(left)
    right_copy = _validate_artifact(right)
    if (
        left_copy["artifact_id"] == right_copy["artifact_id"]
        and left_copy != right_copy
    ):
        raise _invalid("one artifact_id cannot describe different artifacts")
    left_sections = set(left_copy.get("section_hashes", ()))
    right_sections = set(right_copy.get("section_hashes", ()))
    union = left_sections | right_sections
    overlap = len(left_sections & right_sections) / len(union) if union else 0.0
    if left_copy["content_sha256"] == right_copy["content_sha256"]:
        relationship, reasons = "same_document", ["raw content hashes match"]
    elif overlap >= 0.8:
        relationship, reasons = "republication", [
            f"normalized section hash Jaccard overlap is {overlap:.3f}"
        ]
    elif left_copy.get("upstream_source_id") and left_copy.get(
        "upstream_source_id"
    ) == right_copy.get("upstream_source_id"):
        relationship, reasons = "shared_upstream_source", [
            "upstream source identifiers match"
        ]
    elif left_copy.get("publisher_family") and left_copy.get(
        "publisher_family"
    ) == right_copy.get("publisher_family"):
        relationship, reasons = "same_publisher_family", [
            "publisher family identifiers match"
        ]
    elif left_copy.get("publisher_family") and right_copy.get("publisher_family"):
        relationship, reasons = "independent", [
            "publisher families and content hashes differ"
        ]
    else:
        relationship, reasons = "unknown", [
            "insufficient provenance to establish independence"
        ]
    result = {
        "left_artifact_id": left_copy["artifact_id"],
        "right_artifact_id": right_copy["artifact_id"],
        "relationship": relationship,
        "reasons": reasons,
    }
    _validate_definition("source_relationship", result)
    return result


def _parse_assessed_at(value: str) -> datetime:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise _invalid("assessed_at must be RFC3339", assessed_at=value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid("assessed_at must be RFC3339", assessed_at=value) from exc
    if parsed.tzinfo is None:
        raise _invalid("assessed_at must include a timezone", assessed_at=value)
    return parsed


def assess_freshness(
    publish_date: str | None, *, assessed_at: str, maximum_age_days: int
) -> dict[str, Any]:
    assessed = _parse_assessed_at(assessed_at)
    if (
        not isinstance(maximum_age_days, int)
        or isinstance(maximum_age_days, bool)
        or maximum_age_days < 0
    ):
        raise _invalid("maximum_age_days must be a non-negative integer")
    if publish_date is None:
        age_days, status = None, "unknown"
    else:
        if not isinstance(publish_date, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", publish_date
        ):
            raise _invalid("publish_date must be an ISO date or null")
        try:
            published = date.fromisoformat(publish_date)
        except ValueError as exc:
            raise _invalid("publish_date must be a valid ISO date") from exc
        age_days = (assessed.date() - published).days
        status = (
            "future_dated"
            if age_days < 0
            else "fresh"
            if age_days <= maximum_age_days
            else "stale"
        )
    result = {
        "status": status,
        "publish_date": publish_date,
        "assessed_at": assessed_at,
        "age_days": age_days,
        "maximum_age_days": maximum_age_days,
    }
    _validate_definition("freshness_assessment", result)
    return result


def _target_identity(target: dict[str, Any]) -> tuple[Any, Any]:
    if "target_type" in target or "target_id" in target:
        return target.get("target_type"), target.get("target_id")
    mappings = {
        "research_project": "project_id",
        "research_question": "question_id",
        "research_claim": "claim_id",
        "causal_edge": "causal_edge_id",
    }
    found = [(kind, target[key]) for kind, key in mappings.items() if key in target]
    return found[0] if len(found) == 1 else (None, None)


def build_industry_evidence_assessment(
    *,
    requirement: dict[str, Any],
    target: dict[str, Any],
    artifact: dict[str, Any],
    normalized_document: dict[str, Any],
    locator: str,
    evidence_role: str,
    assessment_summary: str,
    directness: str,
    strength: str,
    independence: str,
    freshness: str,
    scope_match: str,
    conflict_status: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    try:
        requirement_copy = deepcopy(requirement)
        target_copy = deepcopy(target)
        artifact_copy = _validate_artifact(artifact)
        document_copy, _ = _validated_document(normalized_document)
        provenance_copy = deepcopy(provenance)
        target_type = requirement_copy["target_type"]
        target_id = requirement_copy["target_id"]
        requirement_id = requirement_copy["requirement_id"]
    except ResearchProjectV2Error as exc:
        if exc.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID":
            raise
        raise _invalid("input object is not canonical", path=exc.details.get("path")) from exc
    except (KeyError, TypeError) as exc:
        raise _invalid("required input field is missing") from exc
    if target_type not in _TARGET_TYPES:
        raise _invalid("target_type is outside the industry layer", target_type=target_type)
    if _target_identity(target_copy) != (target_type, target_id):
        raise _invalid("requirement target does not match target object")
    if document_copy.get("artifact_id") != artifact_copy["artifact_id"]:
        raise _invalid("normalized document does not belong to artifact")
    if artifact_copy.get("media_type") != document_copy.get("media_type"):
        raise _invalid("normalized document media_type does not match artifact")
    if not isinstance(locator, str):
        raise _invalid("locator must be a string")
    locators = [section.get("locator") for section in document_copy.get("sections", [])]
    if len(locators) != len(set(locators)):
        raise _invalid("normalized document contains duplicate locators")
    if locator not in locators:
        raise _invalid(
            "evidence locator does not resolve in normalized document",
            artifact_id=artifact_copy["artifact_id"],
            locator=locator,
        )
    if evidence_role not in _ROLES:
        raise _invalid("evidence_role is invalid", evidence_role=evidence_role)
    if freshness not in _FRESHNESS or conflict_status not in _CONFLICT:
        raise _invalid("freshness or conflict_status is invalid")
    for field, value in (
        ("directness", directness),
        ("strength", strength),
        ("independence", independence),
        ("scope_match", scope_match),
    ):
        if not isinstance(value, str) or not value.strip():
            raise _invalid(f"{field} must be non-empty")
    if not isinstance(assessment_summary, str) or not assessment_summary.strip():
        raise _invalid("assessment_summary must be non-empty")
    identity = sha256(
        f"{requirement_id}\n{artifact_copy['artifact_id']}\n{locator}".encode()
    ).hexdigest()[:24]
    result = {
        "assessment_id": f"industry_evidence_assessment:{identity}",
        "evidence_channel": "industry",
        "target_type": target_type,
        "target_id": target_id,
        "requirement_id": requirement_id,
        "artifact_id": artifact_copy["artifact_id"],
        "normalized_document_id": document_copy["document_id"],
        "evidence_role": evidence_role,
        "locator": locator,
        "assessment_summary": assessment_summary.strip(),
        "directness": directness.strip(),
        "strength": strength.strip(),
        "independence": independence.strip(),
        "freshness": freshness,
        "scope_match": scope_match.strip(),
        "conflict_status": conflict_status,
        "review_status": "pending_review",
        "provenance": provenance_copy,
    }
    wrapper = {
        "schema_version": "2.1.0",
        "artifact_kind": "industry_evidence_assessment",
        "industry_evidence_assessment": result,
    }
    wrapper["content_hash"] = content_sha256(wrapper)
    try:
        validate_v2_1_schema_payload("industry_evidence_assessment_v2_1", wrapper)
    except ResearchProjectV2Error as exc:
        raise _invalid("assessment does not satisfy schema", path=exc.details.get("path")) from exc
    return result


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        while parent != self.parent[parent]:
            parent = self.parent[parent]
        while value != parent:
            next_value = self.parent[value]
            self.parent[value] = parent
            value = next_value
        return parent

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            first, second = sorted((left_root, right_root))
            self.parent[second] = first


def _evidence_context(
    assessments: Iterable[dict[str, Any]],
    artifacts: Iterable[dict[str, Any]],
    source_relationships: Iterable[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], _UnionFind]:
    try:
        assessment_rows = deepcopy(list(assessments))
        artifact_rows = list(artifacts)
        relationships = deepcopy(list(source_relationships))
    except TypeError as exc:
        raise _invalid("evidence collections must be iterable") from exc
    assessment_by_id: dict[str, dict[str, Any]] = {}
    for row in assessment_rows:
        if not isinstance(row, dict):
            raise _invalid("assessment rows must be objects")
        assessment_id = row.get("assessment_id")
        if not isinstance(assessment_id, str) or assessment_id in assessment_by_id:
            raise _invalid("assessment IDs must be unique and non-empty")
        try:
            _validated_wrapper(row)
        except ResearchProjectV2Error as exc:
            raise _invalid(
                "assessment body is invalid", assessment_id=assessment_id
            ) from exc
        assessment_by_id[assessment_id] = row
    artifact_by_id: dict[str, dict[str, Any]] = {}
    for artifact in artifact_rows:
        copied = _validate_artifact(artifact)
        artifact_id = copied["artifact_id"]
        if artifact_id in artifact_by_id:
            raise _invalid("artifact IDs must be unique", artifact_id=artifact_id)
        artifact_by_id[artifact_id] = copied
    union = _UnionFind(artifact_by_id)
    pair_relationships: dict[frozenset[str], str] = {}
    for row in relationships:
        try:
            left, right, relationship = (
                row["left_artifact_id"], row["right_artifact_id"], row["relationship"]
            )
        except (KeyError, TypeError) as exc:
            raise _invalid("source relationship is malformed") from exc
        if left not in artifact_by_id or right not in artifact_by_id:
            raise _invalid("source relationship references a missing artifact")
        if relationship not in _RELATIONSHIPS:
            raise _invalid("source relationship enum is invalid")
        reasons = row.get("reasons")
        if not isinstance(reasons, list) or not reasons or any(
            not isinstance(reason, str) or not reason for reason in reasons
        ):
            raise _invalid("source relationship reasons are invalid")
        pair = frozenset((left, right))
        previous = pair_relationships.get(pair)
        if previous is not None and previous != relationship:
            raise _invalid("source relationship contradiction", left=left, right=right)
        pair_relationships[pair] = relationship
        if relationship in _COLLAPSING:
            union.union(left, right)
    independent_pairs = [pair for pair, rel in pair_relationships.items() if rel == "independent"]
    for left, right in combinations(sorted(artifact_by_id), 2):
        inferred = assess_source_relationship(
            artifact_by_id[left], artifact_by_id[right]
        )["relationship"]
        pair = frozenset((left, right))
        explicit = pair_relationships.get(pair)
        if explicit is not None and explicit != inferred:
            raise _invalid(
                "source relationship contradiction", left=left, right=right
            )
        if explicit is None:
            pair_relationships[pair] = inferred
            if inferred in _COLLAPSING:
                union.union(left, right)
            elif inferred == "independent":
                independent_pairs.append(pair)
    for pair in independent_pairs:
        values = list(pair)
        if len(values) < 2 or union.find(values[0]) == union.find(values[1]):
            raise _invalid("source relationship contradiction")
    for assessment in assessment_by_id.values():
        if assessment.get("artifact_id") not in artifact_by_id:
            raise _invalid("assessment references a missing artifact")
    return assessment_by_id, artifact_by_id, union


def count_independent_coverage(
    assessment_ids: Iterable[str],
    *,
    assessments: Iterable[dict[str, Any]],
    artifacts: Iterable[dict[str, Any]],
    source_relationships: Iterable[dict[str, Any]],
) -> int:
    assessment_by_id, _, union = _evidence_context(
        assessments, artifacts, source_relationships
    )
    try:
        requested = list(assessment_ids)
    except TypeError as exc:
        raise _invalid("assessment_ids must be iterable") from exc
    if len(requested) != len(set(requested)):
        raise _invalid("assessment_ids contain duplicates")
    families: set[str] = set()
    for assessment_id in requested:
        try:
            assessment = assessment_by_id[assessment_id]
        except KeyError as exc:
            raise _invalid("assessment_ids reference a missing assessment") from exc
        if assessment.get("review_status") == "reviewed":
            families.add(union.find(assessment["artifact_id"]))
    return len(families)


def build_conflict_summaries(
    assessments: Iterable[dict[str, Any]],
    *,
    artifacts: Iterable[dict[str, Any]],
    source_relationships: Iterable[dict[str, Any]],
    assessed_at: str,
    provenance: dict[str, Any],
) -> list[dict[str, Any]]:
    _parse_assessed_at(assessed_at)
    assessment_by_id, _, union = _evidence_context(
        assessments, artifacts, source_relationships
    )
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for assessment in assessment_by_id.values():
        if assessment.get("review_status") != "reviewed":
            continue
        target = (assessment.get("target_type"), assessment.get("target_id"))
        if target[0] not in _TARGET_TYPES or not isinstance(target[1], str) or not target[1]:
            raise _invalid("assessment target is invalid")
        groups.setdefault(target, []).append(assessment)
    results: list[dict[str, Any]] = []
    for (target_type, target_id), rows in sorted(groups.items()):
        role_families: dict[str, set[str]] = {role: set() for role in _ROLES}
        for row in rows:
            role = row.get("evidence_role")
            if role not in _ROLES:
                raise _invalid("assessment evidence_role is invalid")
            role_families[role].add(union.find(row["artifact_id"]))
        support = role_families["supports"]
        oppose = role_families["opposes"]
        if not oppose:
            status, summary = "none", "No reviewed opposing source family was identified."
        elif not support:
            status, summary = "unresolved", "Reviewed opposition has no reviewed supporting source family."
        elif any(left != right for left in support for right in oppose):
            status, summary = "material_conflict", "Independent reviewed source families materially disagree."
        else:
            status, summary = "limited", "Support and opposition are confined to the same source family."
        families = {union.find(row["artifact_id"]) for row in rows}
        digest = sha256(f"{target_type}\n{target_id}".encode()).hexdigest()[:24]
        result = {
            "conflict_summary_id": f"conflict_summary:{digest}",
            "evidence_channel": "industry",
            "target_type": target_type,
            "target_id": target_id,
            "conflict_status": status,
            "supporting_source_count": len(support),
            "opposing_source_count": len(oppose),
            "quantitative_source_count": len(role_families["quantifies"]),
            "independent_source_family_count": len(families),
            "assessment_ids": sorted(row["assessment_id"] for row in rows),
            "summary": summary,
            "assessed_at": assessed_at,
            "provenance": deepcopy(provenance),
        }
        _validate_definition("conflict_summary", result)
        results.append(result)
    return results


def _validated_wrapper(assessment: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    copied = deepcopy(assessment)
    expected_id = sha256(
        f"{copied.get('requirement_id')}\n{copied.get('artifact_id')}\n{copied.get('locator')}".encode()
    ).hexdigest()[:24]
    if copied.get("assessment_id") != f"industry_evidence_assessment:{expected_id}":
        raise _immutability("assessment_id mismatch")
    wrapper = {
        "schema_version": "2.1.0",
        "artifact_kind": "industry_evidence_assessment",
        "industry_evidence_assessment": copied,
    }
    wrapper["content_hash"] = content_sha256(wrapper)
    try:
        validate_v2_1_schema_payload("industry_evidence_assessment_v2_1", wrapper)
    except ResearchProjectV2Error as exc:
        raise _invalid("assessment does not satisfy schema", path=exc.details.get("path")) from exc
    if wrapper["content_hash"] != content_sha256(
        wrapper, excluded_paths={("content_hash",)}
    ):
        raise _immutability("content_hash mismatch")
    return wrapper, canonical_bytes(wrapper)


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _chain_bound(descriptors: list[int], names: list[str]) -> bool:
    try:
        return all(
            _same_inode(
                os.fstat(descriptors[index + 1]),
                os.stat(name, dir_fd=descriptors[index], follow_symlinks=False),
            )
            for index, name in enumerate(names)
        )
    except OSError:
        return False


def _open_directory(path: Path) -> tuple[list[int], list[str]]:
    if not path.is_absolute():
        raise _storage("assessment directory must be absolute", path=str(path))
    descriptors = [os.open("/", _DIR_FLAGS)]
    names: list[str] = []
    try:
        for component in path.parts[1:]:
            if component in {"", ".", ".."}:
                raise _storage("unsafe assessment directory component")
            try:
                os.mkdir(component, 0o700, dir_fd=descriptors[-1])
                os.fsync(descriptors[-1])
            except FileExistsError:
                pass
            descriptors.append(os.open(component, _DIR_FLAGS, dir_fd=descriptors[-1]))
            names.append(component)
        return descriptors, names
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _require_private(descriptor: int) -> None:
    opened = os.fstat(descriptor)
    mode = stat.S_IMODE(opened.st_mode)
    if not stat.S_ISDIR(opened.st_mode) or opened.st_uid != os.geteuid() or mode & 0o077:
        raise _storage("managed assessment directory is not owner-only", mode=oct(mode))


def _read_fd(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while chunk := os.read(descriptor, 64 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


def _read_regular(directory_fd: int, name: str) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        data = _read_fd(descriptor)
        after = os.fstat(descriptor)
        entry_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or not _same_inode(before, entry)
            or not _same_inode(before, after)
            or not _same_inode(after, entry_after)
            or before.st_size != len(data)
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise OSError(errno.EIO, "unbound assessment file")
        return data, after
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short assessment write")
        offset += written
    os.fsync(descriptor)


def _retire_temporary(
    directory_fd: int,
    retired_fd: int,
    name: str,
    expected: os.stat_result,
) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) or not _same_inode(current, expected):
            return False
        retired_name = f"entry-{secrets.token_hex(16)}"
        os.rename(
            name,
            retired_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=retired_fd,
        )
        os.fsync(directory_fd)
        os.fsync(retired_fd)
        retired_stat = os.stat(
            retired_name, dir_fd=retired_fd, follow_symlinks=False
        )
        if not stat.S_ISREG(retired_stat.st_mode) or not _same_inode(
            retired_stat, expected
        ):
            return False
        os.unlink(retired_name, dir_fd=retired_fd)
        os.fsync(retired_fd)
        return True
    except FileNotFoundError:
        return False


def write_industry_evidence_assessment(
    assessment: dict[str, Any], *, layout: LayeredResearchLayout | None = None
) -> Path:
    wrapper, data = _validated_wrapper(assessment)
    effective = LayeredResearchLayout.default() if layout is None else layout
    directory = effective.evidence_assessments_dir
    final_name = f"{assessment['assessment_id']}.json"
    target = directory / final_name
    descriptors: list[int] = []
    names: list[str] = []
    temporary_fd: int | None = None
    temporary_name: str | None = None
    temporary_stat: os.stat_result | None = None
    retired_fd: int | None = None
    held_fd: int | None = None
    try:
        descriptors, names = _open_directory(directory)
        directory_fd = descriptors[-1]
        if not _chain_bound(descriptors, names):
            raise _storage("assessment directory binding changed")
        _require_private(directory_fd)
        try:
            os.mkdir(".retired", 0o700, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except FileExistsError:
            pass
        retired_fd = os.open(".retired", _DIR_FLAGS, dir_fd=directory_fd)
        _require_private(retired_fd)
        retired_entry = os.stat(".retired", dir_fd=directory_fd, follow_symlinks=False)
        if not _same_inode(os.fstat(retired_fd), retired_entry):
            raise _storage("retired directory binding changed")
        for _ in range(128):
            temporary_name = f".tmp-{secrets.token_hex(16)}"
            try:
                temporary_fd = os.open(
                    temporary_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=directory_fd,
                )
                break
            except FileExistsError:
                continue
        if temporary_fd is None:
            raise _storage("temporary filename collisions")
        _write_all(temporary_fd, data)
        temporary_stat = os.fstat(temporary_fd)
        entry = os.stat(temporary_name, dir_fd=directory_fd, follow_symlinks=False)
        if not _same_inode(temporary_stat, entry):
            raise _storage("temporary assessment binding changed")
        try:
            os.link(
                temporary_name,
                final_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            created = temporary_stat
            os.fsync(directory_fd)
        except FileExistsError:
            created = None
            existing, _ = _read_regular(directory_fd, final_name)
            if existing != data:
                raise _immutability("immutable assessment path conflict", path=str(target))
        verified, final_stat = _read_regular(directory_fd, final_name)
        if verified != data or (created is not None and not _same_inode(created, final_stat)):
            raise _immutability("published assessment changed", path=str(target))
        if not _retire_temporary(
            directory_fd, retired_fd, temporary_name, temporary_stat
        ):
            raise _storage("temporary assessment changed during cleanup")
        temporary_name = None
        os.close(temporary_fd)
        temporary_fd = None
        held_fd = os.open(final_name, _FILE_FLAGS, dir_fd=directory_fd)
        held_before = os.fstat(held_fd)
        held_data = _read_fd(held_fd)
        held_after = os.fstat(held_fd)
        held_entry = os.stat(final_name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            held_data != data
            or not _same_inode(held_before, held_after)
            or not _same_inode(held_after, held_entry)
        ):
            raise _storage("held assessment changed", path=str(target))
        live_descriptors, live_names = _open_directory(directory)
        try:
            if not _chain_bound(live_descriptors, live_names):
                raise _storage("live assessment directory is unsafe")
            for old, live in zip(descriptors, live_descriptors, strict=True):
                if not _same_inode(os.fstat(old), os.fstat(live)):
                    raise _storage("live assessment directory was rebound")
            live_data, live_stat = _read_regular(live_descriptors[-1], final_name)
            if (
                live_data != data
                or not _same_inode(live_stat, held_after)
            ):
                raise _storage("live assessment was replaced", path=str(target))
        finally:
            for descriptor in reversed(live_descriptors):
                os.close(descriptor)
        return target
    except ResearchProjectV2Error:
        raise
    except OSError as exc:
        raise _storage("assessment write failed", path=str(target)) from exc
    finally:
        if held_fd is not None:
            os.close(held_fd)
        if temporary_fd is not None:
            os.close(temporary_fd)
        if (
            temporary_name is not None
            and temporary_stat is not None
            and descriptors
            and retired_fd is not None
        ):
            try:
                _retire_temporary(
                    descriptors[-1], retired_fd, temporary_name, temporary_stat
                )
            except OSError:
                pass
        if retired_fd is not None:
            os.close(retired_fd)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def validate_industry_evidence_assessments(
    assessments: Iterable[dict[str, Any]],
    *,
    artifacts: Iterable[dict[str, Any]],
    source_relationships: Iterable[dict[str, Any]] = (),
) -> None:
    _evidence_context(assessments, artifacts, source_relationships)
