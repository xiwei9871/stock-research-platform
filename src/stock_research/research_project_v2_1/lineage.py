from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Iterable


_SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


@dataclass(frozen=True)
class LineageError(ValueError):
    reason: str
    details: dict[str, object]


def semver_key(value: str) -> tuple[int, int, int]:
    return tuple(map(int, value.split(".")))


def parse_version_id(version_id: object) -> tuple[str, str]:
    if not isinstance(version_id, str) or not version_id.startswith("research_version:"):
        raise LineageError("parent_version_id is not canonical", {"actual": version_id})
    remainder = version_id.removeprefix("research_version:")
    try:
        slug, semantic_version = remainder.rsplit(":", 1)
    except ValueError as exc:
        raise LineageError("parent_version_id is not canonical", {"actual": version_id}) from exc
    if not slug or _SEMVER.fullmatch(semantic_version) is None:
        raise LineageError("parent_version_id is not canonical", {"actual": version_id})
    return slug, semantic_version


def collect_lineage_version_ids(
    version: dict[str, Any],
    *,
    project_slug: str,
    known_semantic_versions: Iterable[str],
    load_version: Callable[[str], dict[str, Any]],
) -> tuple[str, ...]:
    known = set(known_semantic_versions)
    current = version
    lineage: list[str] = []
    seen: set[str] = set()
    while True:
        semantic_version = current.get("semantic_version")
        version_id = current.get("version_id")
        expected_id = f"research_version:{project_slug}:{semantic_version}"
        if (
            not isinstance(semantic_version, str)
            or _SEMVER.fullmatch(semantic_version) is None
            or version_id != expected_id
        ):
            raise LineageError(
                "lineage version identity mismatch",
                {"expected": expected_id, "actual": version_id},
            )
        if version_id in seen:
            raise LineageError("parent lineage cycle", {"version_id": version_id})
        seen.add(version_id)
        lineage.append(version_id)
        parent_id = current.get("parent_version_id")
        if parent_id is None:
            if any(semver_key(item) < semver_key(semantic_version) for item in known):
                raise LineageError(
                    "non-initial version parent_version_id is null",
                    {"version_id": version_id},
                )
            return tuple(lineage)
        parent_slug, parent_semver = parse_version_id(parent_id)
        if parent_slug != project_slug:
            raise LineageError(
                "parent_version_id project mismatch",
                {"expected_project": project_slug, "actual_project": parent_slug},
            )
        if semver_key(parent_semver) >= semver_key(semantic_version):
            raise LineageError(
                "parent version is not earlier",
                {"child_version": semantic_version, "parent_version": parent_semver},
            )
        if parent_semver not in known:
            raise LineageError("parent version not found", {"parent_version": parent_semver})
        try:
            current = load_version(parent_semver)
        except LineageError:
            raise
        except Exception as exc:
            raise LineageError(
                "parent version not found",
                {"parent_version": parent_semver},
            ) from exc


__all__ = [
    "LineageError",
    "collect_lineage_version_ids",
    "parse_version_id",
    "semver_key",
]
