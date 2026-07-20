from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "platform_validation_inventory_v1"

ROOT_FIELDS = frozenset({"schema_version", "items"})
ITEM_FIELDS = frozenset(
    {
        "id",
        "label",
        "route",
        "entry_kind",
        "priority",
        "auth",
        "write_mode",
        "primary_apis",
        "layers",
        "profiles",
        "daily_eod",
        "owner",
        "reachable",
        "disabled_reason",
        "landmark",
        "route_params",
    }
)
ENTRY_KINDS = frozenset({"main_navigation", "admin_navigation", "deep_link", "hidden"})
PRIORITIES = frozenset({"P0", "P1", "P2"})
AUTH_MODES = frozenset({"authenticated", "admin"})
WRITE_MODES = frozenset({"read_only", "read_write"})
LAYERS = frozenset({"unit", "api", "playwright"})
PLAYWRIGHT_PROFILES = frozenset({"legacy", "mock", "real", "sandbox", "audit", "eod"})
COVERAGE_STATUSES = frozenset({"covered", "partial", "missing", "not_applicable"})
LANDMARK_FIELDS = frozenset({"role", "name"})
LANDMARK_ROLES = frozenset({"region", "heading"})
API_FIELDS = frozenset({"method", "path", "access", "census_scope"})
API_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "POST", "PATCH", "PUT", "DELETE"})
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
API_ACCESS = frozenset({"read", "write"})
CENSUS_SCOPES = frozenset({"route_load", "journey"})
ROUTE_PARAM_SOURCES = frozenset({"authoritative_stock_asset_id"})

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_ANSI = re.compile(r"(?:\x1b\[[0-?]*[ -/]*[@-~]|\x9b[0-?]*[ -/]*[@-~])")
_ISO_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
_LOCAL_URL = re.compile(r"https?://(?:127\.0\.0\.1|localhost|\[::1\]):\d+")
_LINE_COLUMN = re.compile(r"(\.[A-Za-z0-9]{1,5}):\d+(?::\d+)?")
_LINE_WORD = re.compile(r"\b(?:line|column)\s+\d+\b", re.IGNORECASE)
_CODE_FRAME_LINE = re.compile(r"(?m)^\s*(>?)\s*\d+\s*\|")
_SENSITIVE_NAME = (
    r"(?:access[_-]?token|refresh[_-]?token|csrf[_-]?token|api[_-]?key|password|passwd|"
    r"secret|token|authorization|proxy[_-]?authorization|cookie|set[_-]?cookie)"
)
_SENSITIVE_HEADER = re.compile(
    r"(?im)^(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*:\s*.*$"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_QUOTED_SECRET = re.compile(
    rf'(?i)(["\']{_SENSITIVE_NAME}["\']\s*:\s*["\'])[^"\']*(["\'])'
)
_ASSIGNED_SECRET = re.compile(rf"(?i)(\b{_SENSITIVE_NAME}\b\s*[=:]\s*)[^\s,;&#]+")
_QUERY_SECRET = re.compile(rf"(?i)([?&]{_SENSITIVE_NAME}=)[^&#\s]+")
_PATH_SECRET = re.compile(rf"(?i)(/{_SENSITIVE_NAME}/)[^/?#\s]+")
_TITLE_INVENTORY = re.compile(r"\[inventory(?:_ids?)?:([a-z0-9_, -]+)\]", re.IGNORECASE)
_TITLE_INVENTORY_CALL = re.compile(r"@inventory\(([a-z0-9_, -]+)\)", re.IGNORECASE)
_ROUTE_CENSUS_TITLE = re.compile(r"^route census ([a-z0-9_]+):", re.IGNORECASE)
_STABLE_ROOT_MARKER = re.compile(
    r"\b(?:authoritative_snapshot_|real_profile_|platform_validation_|real_route_census_)"
    r"[a-z0-9_]*\b",
    re.IGNORECASE,
)
_HTTP_ROOT_MARKER = re.compile(
    r"\b(GET|POST|PATCH|PUT|DELETE|HEAD|OPTIONS)\s+(/[^\s?#]+)(?:\?[^\s]*)?"
    r".*?\b(?:status\s*)?([45]\d\d)\b",
    re.IGNORECASE,
)
_ROOT_CAUSE_ID = re.compile(r"[a-z][a-z0-9_]{2,80}")
_BASELINE_STATUSES = frozenset({"baseline_candidate", "trusted_baseline"})
_PLAYWRIGHT_TEST_STATUSES = frozenset(
    {"expected", "unexpected", "flaky", "skipped", "passed", "failed", "timedout", "timeout"}
)
_ISSUE_SCHEMA_VERSION = "platform_validation_issue_ledger_v1"
_COVERAGE_SCHEMA_VERSION = "platform_validation_coverage_v1"
_COVERAGE_RESULTS_SCHEMA_VERSION = "platform_validation_coverage_results_v1"
_OBSERVED_COVERAGE_STATUSES = frozenset({"covered", "partial", "missing"})
_MAX_PLAYWRIGHT_JSON_BYTES = 16 * 1024 * 1024
_MAX_COVERAGE_JSON_BYTES = 4 * 1024 * 1024
_MAX_JSON_DEPTH = 100
_MAX_JSON_NODES = 500_000
_MAX_SUITES = 10_000
_MAX_SPECS = 50_000
_MAX_TESTS = 200_000
_MAX_RESULTS = 500_000
_MAX_ATTACHMENTS = 500_000
_MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
_MAX_PNG_BYTES = 20 * 1024 * 1024
_MAX_ZIP_MEMBERS = 2_000
_MAX_ZIP_MEMBER_BYTES = 16 * 1024 * 1024
_MAX_ZIP_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 500
_TEXT_EVIDENCE_SUFFIXES = frozenset(
    {
        ".csv", ".html", ".json", ".jsonl", ".log", ".md", ".network",
        ".stacks", ".trace", ".txt", ".xml", ".yaml", ".yml",
    }
)


def _inventory_error(field: str, detail: str) -> ValueError:
    return ValueError(f"inventory: field {field}: {detail}")


def _item_error(item_id: str, field: str, detail: str) -> ValueError:
    return ValueError(f"item {item_id}: field {field}: {detail}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _inventory_error("root", f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise _inventory_error("root", f"non-finite JSON value {value}")


def load_inventory(path: str | Path) -> dict[str, Any]:
    inventory_path = Path(path)
    try:
        payload = json.loads(
            inventory_path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _inventory_error("root", f"cannot load {inventory_path}: {exc}") from exc
    return validate_inventory(payload)


def _require_string(item: Mapping[str, Any], item_id: str, field: str) -> str:
    value = item[field]
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise _item_error(item_id, field, "must be a non-empty trimmed string")
    return value


def _require_enum(item: Mapping[str, Any], item_id: str, field: str, allowed: frozenset[str]) -> str:
    value = item[field]
    if not isinstance(value, str) or value not in allowed:
        raise _item_error(item_id, field, f"must be one of {sorted(allowed)}")
    return value


def _require_string_list(
    item: Mapping[str, Any],
    item_id: str,
    field: str,
    *,
    allowed: frozenset[str] | None = None,
    non_empty: bool = False,
) -> list[str]:
    value = item[field]
    if not isinstance(value, list):
        raise _item_error(item_id, field, "must be a list")
    if non_empty and not value:
        raise _item_error(item_id, field, "must contain at least one value")
    if any(not isinstance(entry, str) or not entry.strip() or entry != entry.strip() for entry in value):
        raise _item_error(item_id, field, "must contain only non-empty trimmed strings")
    if len(set(value)) != len(value):
        raise _item_error(item_id, field, "must not contain duplicate values")
    if allowed is not None:
        invalid = sorted(set(value) - allowed)
        if invalid:
            raise _item_error(item_id, field, f"contains unsupported values {invalid}")
    return value


def _validate_canonical_path(
    value: Any,
    item_id: str,
    field: str,
    *,
    api: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _item_error(item_id, field, "must be a non-empty trimmed canonical path")
    if not value.startswith("/") or (api and not value.startswith("/api/")):
        required_prefix = "/api/" if api else "/"
        raise _item_error(item_id, field, f"must start with {required_prefix}")
    if value != "/" and value.endswith("/"):
        raise _item_error(item_id, field, "must not have a trailing slash")
    if any(token in value for token in ("//", "?", "#", "%", "\\")):
        raise _item_error(item_id, field, "must not contain ambiguous separators, encoding, query, or fragment")
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        raise _item_error(item_id, field, "must not contain whitespace or control characters")
    if value == "/":
        return ()

    placeholders: list[str] = []
    for segment in value[1:].split("/"):
        if not segment or segment in {".", ".."}:
            raise _item_error(item_id, field, "must not contain empty or dot segments")
        if "{" in segment or "}" in segment:
            match = _PLACEHOLDER.fullmatch(segment)
            if match is None:
                raise _item_error(
                    item_id,
                    field,
                    "placeholders must be whole segments named {[a-z][a-z0-9_]*}",
                )
            placeholder = match.group(1)
            if placeholder in placeholders:
                raise _item_error(item_id, field, f"placeholder {placeholder!r} must be unique")
            placeholders.append(placeholder)
    return tuple(placeholders)


def _validate_route_params(item: Mapping[str, Any], item_id: str, placeholders: tuple[str, ...]) -> None:
    route_params = item["route_params"]
    if not isinstance(route_params, dict):
        raise _item_error(item_id, "route_params", "must be an object")
    if set(route_params) != set(placeholders):
        raise _item_error(item_id, "route_params", "keys must exactly match route placeholders")
    for source in route_params.values():
        if not isinstance(source, str) or source not in ROUTE_PARAM_SOURCES:
            raise _item_error(
                item_id,
                "route_params",
                f"values must be one of {sorted(ROUTE_PARAM_SOURCES)}",
            )


def _validate_landmark(item: Mapping[str, Any], item_id: str, reachable: bool) -> None:
    landmark = item["landmark"]
    if not reachable:
        if landmark is not None:
            raise _item_error(item_id, "landmark", "must be null for unreachable items")
        return
    if not isinstance(landmark, dict):
        raise _item_error(item_id, "landmark", "must be an object for reachable items")
    if set(landmark) != LANDMARK_FIELDS:
        raise _item_error(item_id, "landmark", "must contain exactly role and name")
    role = landmark["role"]
    if not isinstance(role, str) or role not in LANDMARK_ROLES:
        raise _item_error(item_id, "landmark", f"role must be one of {sorted(LANDMARK_ROLES)}")
    name = landmark["name"]
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise _item_error(item_id, "landmark", "name must be a non-empty trimmed string")


def _validate_primary_apis(item: Mapping[str, Any], item_id: str, write_mode: str) -> None:
    primary_apis = item["primary_apis"]
    if not isinstance(primary_apis, list) or not primary_apis:
        raise _item_error(item_id, "primary_apis", "must be a non-empty list")

    seen: set[tuple[str, str]] = set()
    has_write = False
    for api in primary_apis:
        if not isinstance(api, dict) or set(api) != API_FIELDS:
            raise _item_error(
                item_id,
                "primary_apis",
                "entries must contain exactly method, path, access, and census_scope",
            )
        method = api["method"]
        access = api["access"]
        census_scope = api["census_scope"]
        if not isinstance(method, str) or method not in API_METHODS:
            raise _item_error(item_id, "primary_apis", f"method must be one of {sorted(API_METHODS)}")
        if not isinstance(access, str) or access not in API_ACCESS:
            raise _item_error(item_id, "primary_apis", f"access must be one of {sorted(API_ACCESS)}")
        if not isinstance(census_scope, str) or census_scope not in CENSUS_SCOPES:
            raise _item_error(item_id, "primary_apis", f"census_scope must be one of {sorted(CENSUS_SCOPES)}")
        expected_access = "read" if method in READ_METHODS else "write"
        if access != expected_access:
            raise _item_error(item_id, "primary_apis", f"{method} requires access {expected_access}")
        if census_scope == "route_load" and access != "read":
            raise _item_error(item_id, "primary_apis", "route_load operations must be read-only")
        if access == "write" and census_scope != "journey":
            raise _item_error(item_id, "primary_apis", "write operations must use journey scope")
        _validate_canonical_path(api["path"], item_id, "primary_apis", api=True)
        key = (method, api["path"])
        if key in seen:
            raise _item_error(item_id, "primary_apis", f"duplicate API operation {method} {api['path']}")
        seen.add(key)
        has_write = has_write or access == "write"

    if write_mode == "read_only" and has_write:
        raise _item_error(item_id, "write_mode", "read-only items must not declare write APIs")
    if write_mode == "read_write" and not has_write:
        raise _item_error(item_id, "write_mode", "read-write items require at least one write API")


def _validate_item(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _item_error(f"<index:{index}>", "root", "must be an object")

    raw_id = item.get("id")
    item_id = raw_id if isinstance(raw_id, str) and raw_id else f"<index:{index}>"
    missing = sorted(ITEM_FIELDS - item.keys())
    if missing:
        raise _item_error(item_id, missing[0], "is required")
    unknown = sorted(item.keys() - ITEM_FIELDS)
    if unknown:
        raise _item_error(item_id, unknown[0], "is not allowed")

    item_id = _require_string(item, item_id, "id")
    if not all(character.islower() or character.isdigit() or character == "_" for character in item_id):
        raise _item_error(item_id, "id", "must use lowercase letters, digits, and underscores")
    _require_string(item, item_id, "label")
    route_placeholders = _validate_canonical_path(item["route"], item_id, "route")
    _validate_route_params(item, item_id, route_placeholders)
    entry_kind = _require_enum(item, item_id, "entry_kind", ENTRY_KINDS)
    priority = _require_enum(item, item_id, "priority", PRIORITIES)
    _require_enum(item, item_id, "auth", AUTH_MODES)
    write_mode = _require_enum(item, item_id, "write_mode", WRITE_MODES)
    _validate_primary_apis(item, item_id, write_mode)
    layers = _require_string_list(item, item_id, "layers", allowed=LAYERS, non_empty=True)
    profiles = _require_string_list(item, item_id, "profiles", allowed=PLAYWRIGHT_PROFILES)
    if priority == "P0" and not profiles:
        raise _item_error(item_id, "profiles", "P0 items require a named Playwright profile")
    if profiles and "playwright" not in layers:
        raise _item_error(item_id, "layers", "items with profiles require the playwright layer")

    daily_eod = item["daily_eod"]
    if type(daily_eod) is not bool:
        raise _item_error(item_id, "daily_eod", "must be a boolean")
    if ("eod" in profiles) != daily_eod:
        raise _item_error(item_id, "profiles", "the eod profile must be present if and only if daily_eod is true")
    reachable = item["reachable"]
    if type(reachable) is not bool:
        raise _item_error(item_id, "reachable", "must be a boolean")
    _require_string(item, item_id, "owner")

    disabled_reason = item["disabled_reason"]
    if disabled_reason is not None and (
        not isinstance(disabled_reason, str) or not disabled_reason.strip() or disabled_reason != disabled_reason.strip()
    ):
        raise _item_error(item_id, "disabled_reason", "must be null or a non-empty trimmed string")
    if reachable and disabled_reason is not None:
        raise _item_error(item_id, "disabled_reason", "must be null for reachable items")
    if not reachable:
        if entry_kind != "hidden":
            raise _item_error(item_id, "entry_kind", "unreachable items must be hidden")
        if disabled_reason is None:
            raise _item_error(item_id, "disabled_reason", "is required for unreachable items")
    if daily_eod and (write_mode != "read_only" or not reachable):
        raise _item_error(item_id, "daily_eod", "is allowed only for reachable read-only items")
    _validate_landmark(item, item_id, reachable)

    return deepcopy(item)


def validate_inventory(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _inventory_error("root", "must be an object")
    missing = sorted(ROOT_FIELDS - payload.keys())
    if missing:
        raise _inventory_error(missing[0], "is required")
    unknown = sorted(payload.keys() - ROOT_FIELDS)
    if unknown:
        raise _inventory_error(unknown[0], "is not allowed")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise _inventory_error("schema_version", f"must equal {SCHEMA_VERSION}")
    if not isinstance(payload["items"], list) or not payload["items"]:
        raise _inventory_error("items", "must be a non-empty list")

    items: list[dict[str, Any]] = []
    ids: set[str] = set()
    routes: set[str] = set()
    for index, raw_item in enumerate(payload["items"]):
        item = _validate_item(raw_item, index)
        item_id = item["id"]
        if item_id in ids:
            raise _item_error(item_id, "id", "must be unique")
        if item["route"] in routes:
            raise _item_error(item_id, "route", "must be unique")
        ids.add(item_id)
        routes.add(item["route"])
        items.append(item)

    return {"schema_version": SCHEMA_VERSION, "items": items}


def _validate_result_map(
    inventory_items: Mapping[str, Mapping[str, Any]],
    result_map: Mapping[str, list[str]] | None,
    *,
    field: str,
    assignment_field: str,
) -> dict[str, set[str]]:
    if result_map is None:
        return {}
    if not isinstance(result_map, Mapping):
        raise _inventory_error(field, "must be a mapping of item IDs to lists")

    normalized: dict[str, set[str]] = {}
    for item_id, values in result_map.items():
        if not isinstance(item_id, str) or item_id not in inventory_items:
            raise _inventory_error(field, f"contains unknown item ID {item_id!r}")
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise _item_error(item_id, field, "must be a list of strings")
        if len(set(values)) != len(values):
            raise _item_error(item_id, field, "must not contain duplicate values")
        assigned = set(inventory_items[item_id][assignment_field])
        unsupported = sorted(set(values) - assigned)
        if unsupported:
            raise _item_error(item_id, field, f"contains unassigned values {unsupported}")
        normalized[item_id] = set(values)
    return normalized


def build_coverage_matrix(
    inventory: Mapping[str, Any],
    *,
    layer_results: Mapping[str, list[str]] | None = None,
    profile_results: Mapping[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    validated = validate_inventory(inventory)
    items_by_id = {item["id"]: item for item in validated["items"]}
    covered_layers = _validate_result_map(
        items_by_id,
        layer_results,
        field="layer_results",
        assignment_field="layers",
    )
    covered_profiles = _validate_result_map(
        items_by_id,
        profile_results,
        field="profile_results",
        assignment_field="profiles",
    )

    rows: list[dict[str, Any]] = []
    for item in validated["items"]:
        item_id = item["id"]
        required_layers = sorted(item["layers"])
        required_profiles = sorted(item["profiles"])
        item_covered_layers = sorted(covered_layers.get(item_id, set()))
        item_covered_profiles = sorted(covered_profiles.get(item_id, set()))
        missing_layers = sorted(set(required_layers) - set(item_covered_layers))
        missing_profiles = sorted(set(required_profiles) - set(item_covered_profiles))

        if not item["reachable"]:
            status = "not_applicable"
            missing_layers = []
            missing_profiles = []
        else:
            required_count = len(required_layers) + len(required_profiles)
            covered_count = len(item_covered_layers) + len(item_covered_profiles)
            status = "covered" if covered_count == required_count else "partial" if covered_count else "missing"
        if status not in COVERAGE_STATUSES:  # Defensive guard for future rule edits.
            raise RuntimeError(f"unsupported coverage status {status}")

        rows.append(
            {
                "id": item_id,
                "label": item["label"],
                "route": item["route"],
                "entry_kind": item["entry_kind"],
                "priority": item["priority"],
                "status": status,
                "required_layers": required_layers,
                "covered_layers": item_covered_layers,
                "missing_layers": missing_layers,
                "required_profiles": required_profiles,
                "covered_profiles": item_covered_profiles,
                "missing_profiles": missing_profiles,
                "reason": item["disabled_reason"],
            }
        )

    return sorted(rows, key=lambda row: (_PRIORITY_ORDER[row["priority"]], row["id"]))


def _sanitize_text(value: object, *, checkout_roots: tuple[str, ...] = ()) -> str:
    text = _ANSI.sub("", str(value))
    for root in sorted({root.rstrip("/") for root in checkout_roots if root}, key=len, reverse=True):
        text = text.replace(root, "<WORKTREE>")
    text = _SENSITIVE_HEADER.sub("[REDACTED HEADER]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _QUOTED_SECRET.sub(r"\1[REDACTED]\2", text)
    text = _QUERY_SECRET.sub(r"\1[REDACTED]", text)
    text = _PATH_SECRET.sub(r"\1[REDACTED]", text)
    text = _ASSIGNED_SECRET.sub(r"\1[REDACTED]", text)
    return text


def _sanitize_payload(value: Any, *, checkout_roots: tuple[str, ...] = ()) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        header_name = value.get("name")
        redact_header_value = isinstance(header_name, str) and bool(
            re.fullmatch(_SENSITIVE_NAME, header_name, re.IGNORECASE)
        )
        for key, item in value.items():
            safe_key = _sanitize_text(key, checkout_roots=checkout_roots)
            if (redact_header_value and str(key).lower() == "value") or re.search(
                _SENSITIVE_NAME, str(key), re.IGNORECASE
            ):
                sanitized[safe_key] = "[REDACTED]"
            else:
                sanitized[safe_key] = _sanitize_payload(item, checkout_roots=checkout_roots)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item, checkout_roots=checkout_roots) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item, checkout_roots=checkout_roots) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value, checkout_roots=checkout_roots)
    return value


def _fingerprint_text(value: str) -> str:
    normalized = _ISO_TIMESTAMP.sub("<TIMESTAMP>", value)
    normalized = _LOCAL_URL.sub("<LOCAL_URL>", normalized)
    normalized = _LINE_COLUMN.sub(r"\1:<LINE>:<COLUMN>", normalized)
    normalized = _LINE_WORD.sub("<LINE>", normalized)
    normalized = _CODE_FRAME_LINE.sub(r"\1 <LINE> |", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


def _validate_json_file(path: Path, *, label: str, max_bytes: int) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"{label} {path}: cannot load: {exc}") from exc
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} {path}: must be a regular file")
    if size > max_bytes:
        raise ValueError(f"{label} {path}: size limit exceeded")


def _assert_json_limits(payload: Any, *, label: str) -> None:
    stack: list[tuple[Any, int]] = [(payload, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise ValueError(f"{label}: JSON node limit exceeded")
        if depth > _MAX_JSON_DEPTH:
            raise ValueError(f"{label}: JSON depth limit exceeded")
        if isinstance(value, Mapping):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)


def _load_playwright_json(path: Path) -> dict[str, Any]:
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key {key!r}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON value {value}")

    _validate_json_file(path, label="Playwright result", max_bytes=_MAX_PLAYWRIGHT_JSON_BYTES)
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"Playwright result {path}: cannot load: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("suites"), list):
        raise ValueError(f"Playwright result {path}: root must contain a suites list")
    config = payload.get("config", {})
    if config is not None and not isinstance(config, dict):
        raise ValueError(f"Playwright result {path}: config must be an object")
    _assert_json_limits(payload, label=f"Playwright result {path}")
    return payload


def _checkout_roots(payload: Mapping[str, Any]) -> tuple[str, ...]:
    config = payload.get("config")
    if not isinstance(config, Mapping):
        return ()
    roots: set[str] = set()
    root_dir = config.get("rootDir")
    if isinstance(root_dir, str) and Path(root_dir).is_absolute():
        path = Path(root_dir)
        roots.add(str(path))
        if path.name == "tests" and path.parent.name == "dashboard":
            roots.add(str(path.parent.parent))
        else:
            roots.add(str(path.parent))
    config_file = config.get("configFile")
    if isinstance(config_file, str) and Path(config_file).is_absolute():
        roots.add(str(Path(config_file).parent.parent))
    return tuple(sorted(roots, key=len, reverse=True))


def _profile_for_result(payload: Mapping[str, Any], explicit_profile: str | None) -> str:
    metadata_profile: str | None = None
    config = payload.get("config")
    if isinstance(config, Mapping):
        metadata = config.get("metadata")
        if isinstance(metadata, Mapping):
            for key in ("platformValidationProfile", "platform_validation_profile", "profile"):
                value = metadata.get(key)
                if value is None:
                    continue
                if not isinstance(value, str) or value not in PLAYWRIGHT_PROFILES:
                    raise ValueError("Playwright profile metadata is invalid")
                metadata_profile = value
                break
    if explicit_profile is not None:
        if explicit_profile not in PLAYWRIGHT_PROFILES:
            raise ValueError(f"Playwright profile {explicit_profile!r} is unsupported")
        if metadata_profile is not None and metadata_profile != explicit_profile:
            raise ValueError("Playwright profile binding conflicts with result metadata")
        return explicit_profile
    if metadata_profile is not None:
        return metadata_profile
    raise ValueError("Playwright profile must be explicit or present in result metadata")


def _normalize_playwright_inputs(
    entries: list[str | Path | tuple[str, str | Path]],
) -> list[tuple[str | None, Path]]:
    normalized: set[tuple[str | None, Path]] = set()
    for entry in entries:
        explicit_profile: str | None = None
        raw_path: str | Path
        if isinstance(entry, tuple):
            if len(entry) != 2:
                raise ValueError("Playwright result tuple must contain profile and path")
            explicit_profile, raw_path = entry
        elif isinstance(entry, str) and "=" in entry:
            candidate_profile, candidate_path = entry.split("=", 1)
            if candidate_profile in PLAYWRIGHT_PROFILES:
                explicit_profile = candidate_profile
                raw_path = candidate_path
            else:
                raw_path = entry
        else:
            raw_path = entry
        if explicit_profile is not None and explicit_profile not in PLAYWRIGHT_PROFILES:
            raise ValueError(f"Playwright profile {explicit_profile!r} is unsupported")
        path = Path(raw_path)
        if not str(path):
            raise ValueError("Playwright result path must be non-empty")
        normalized.add((explicit_profile, path))
    return sorted(normalized, key=lambda item: ((item[0] or ""), item[1].as_posix()))


def _relative_test_file(raw: object, *, root_dir: object, checkout_roots: tuple[str, ...]) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return "<unknown-file>"
    path = Path(raw)
    if path.is_absolute():
        if isinstance(root_dir, str):
            try:
                path = path.resolve().relative_to(Path(root_dir).resolve())
            except ValueError:
                return _sanitize_text(path.name, checkout_roots=checkout_roots)
        else:
            return _sanitize_text(path.name, checkout_roots=checkout_roots)
    if ".." in path.parts:
        raise ValueError(f"unsafe Playwright test file {raw!r}")
    return _sanitize_text(path.as_posix(), checkout_roots=checkout_roots)


def _annotation_inventory_ids(annotations: object) -> list[str] | None:
    if not isinstance(annotations, list):
        return None
    for annotation in annotations:
        if not isinstance(annotation, Mapping):
            continue
        annotation_type = str(annotation.get("type", "")).lower().replace("-", "_")
        if annotation_type not in {
            "inventory_id",
            "inventory_ids",
            "platform_inventory_id",
            "platform_inventory_ids",
        }:
            continue
        description = annotation.get("description")
        if not isinstance(description, str) or not description.strip():
            return []
        raw = description.strip()
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list) and all(isinstance(item, str) for item in decoded):
            return sorted(set(decoded))
        return sorted({item.strip() for item in raw.split(",") if item.strip()})
    return None


def _title_inventory_ids(title: str) -> list[str] | None:
    for pattern in (_TITLE_INVENTORY, _TITLE_INVENTORY_CALL):
        match = pattern.search(title)
        if match:
            return sorted({item.strip() for item in match.group(1).split(",") if item.strip()})
    census_match = _ROUTE_CENSUS_TITLE.search(title)
    return [census_match.group(1)] if census_match else None


def _decode_attachment_json(attachment: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if attachment.get("name") != "route-census.json":
        return None
    body = attachment.get("body")
    if not isinstance(body, str):
        return None
    candidates: list[str] = [body]
    try:
        candidates.insert(0, base64.b64decode(body, validate=True).decode("utf-8"))
    except (ValueError, UnicodeError):
        pass
    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
            _assert_json_limits(decoded, label="route-census attachment")
        except (json.JSONDecodeError, RecursionError, ValueError):
            continue
        if isinstance(decoded, Mapping):
            return decoded
    raise ValueError("route-census.json attachment is not valid JSON")


def _attachment_inventory_ids(results: object) -> list[str] | None:
    if not isinstance(results, list):
        return None
    for result in results:
        if not isinstance(result, Mapping) or not isinstance(result.get("attachments"), list):
            continue
        for attachment in result["attachments"]:
            if not isinstance(attachment, Mapping):
                continue
            metadata = _decode_attachment_json(attachment)
            if metadata is None:
                continue
            raw_ids = metadata.get("inventoryIds", metadata.get("inventory_ids"))
            if isinstance(raw_ids, list) and all(isinstance(item, str) for item in raw_ids):
                return sorted(set(raw_ids))
            raw_id = metadata.get("inventoryId", metadata.get("inventory_id"))
            if isinstance(raw_id, str) and raw_id.strip():
                return [raw_id.strip()]
            return []
    return None


def _inventory_ids_for_test(
    test: Mapping[str, Any],
    *,
    title: str,
    known_ids: frozenset[str],
) -> list[str]:
    inventory_ids = _annotation_inventory_ids(test.get("annotations"))
    if inventory_ids is None:
        results = test.get("results")
        if isinstance(results, list):
            for result in results:
                if isinstance(result, Mapping):
                    inventory_ids = _annotation_inventory_ids(result.get("annotations"))
                    if inventory_ids is not None:
                        break
    if inventory_ids is None:
        inventory_ids = _title_inventory_ids(title)
    if inventory_ids is None:
        inventory_ids = _attachment_inventory_ids(test.get("results"))
    if inventory_ids is None:
        return []
    unknown = sorted(set(inventory_ids) - known_ids)
    if unknown:
        safe_unknown = _sanitize_text(unknown[0])
        raise ValueError(f"Playwright result contains unknown inventory ID {safe_unknown!r}")
    if not inventory_ids:
        raise ValueError("Playwright inventory metadata must contain at least one inventory ID")
    return sorted(set(inventory_ids))


def _disposition_for_test(test: Mapping[str, Any], checkout_roots: tuple[str, ...]) -> str | None:
    annotation_lists: list[object] = [test.get("annotations")]
    results = test.get("results")
    if isinstance(results, list):
        annotation_lists.extend(
            result.get("annotations") for result in results if isinstance(result, Mapping)
        )
    for annotations in annotation_lists:
        if not isinstance(annotations, list):
            continue
        for annotation in annotations:
            if not isinstance(annotation, Mapping):
                continue
            if str(annotation.get("type", "")).lower().replace("-", "_") != "disposition":
                continue
            description = annotation.get("description")
            if isinstance(description, str) and description.strip():
                return _sanitize_text(description.strip(), checkout_roots=checkout_roots)
    return None


def _root_cause_for_test(test: Mapping[str, Any]) -> str | None:
    annotation_lists: list[object] = [test.get("annotations")]
    results = test.get("results")
    if isinstance(results, list):
        annotation_lists.extend(
            result.get("annotations") for result in results if isinstance(result, Mapping)
        )
    for annotations in annotation_lists:
        if not isinstance(annotations, list):
            continue
        for annotation in annotations:
            if not isinstance(annotation, Mapping):
                continue
            raw_type = str(annotation.get("type", "")).lower()
            root_cause: object | None = None
            if raw_type == "root_cause":
                root_cause = annotation.get("description")
            elif raw_type.startswith("root_cause:"):
                root_cause = raw_type.split(":", 1)[1]
            else:
                continue
            if not isinstance(root_cause, str) or _ROOT_CAUSE_ID.fullmatch(root_cause) is None:
                raise ValueError("root_cause annotation must contain a strict lowercase identifier")
            return root_cause
    return None


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sanitize_text_evidence(
    content: bytes,
    *,
    suffix: str,
    checkout_roots: tuple[str, ...],
) -> bytes | None:
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        return None
    if suffix == ".json":
        try:
            payload = json.loads(text)
            _assert_json_limits(payload, label="evidence JSON")
        except (json.JSONDecodeError, RecursionError, ValueError):
            pass
        else:
            return (
                json.dumps(
                    _sanitize_payload(payload, checkout_roots=checkout_roots),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
    if suffix in {".jsonl", ".network", ".stacks", ".trace"}:
        sanitized_lines: list[str] = []
        for line in text.splitlines():
            try:
                payload = json.loads(line)
                _assert_json_limits(payload, label="trace JSON line")
            except (json.JSONDecodeError, RecursionError, ValueError):
                sanitized_lines.append(_sanitize_text(line, checkout_roots=checkout_roots))
            else:
                sanitized_lines.append(
                    json.dumps(
                        _sanitize_payload(payload, checkout_roots=checkout_roots),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
        return ("\n".join(sanitized_lines) + ("\n" if text.endswith("\n") else "")).encode(
            "utf-8"
        )
    return _sanitize_text(text, checkout_roots=checkout_roots).encode("utf-8")


def _safe_zip_member_name(raw: str) -> str:
    if not raw or raw.startswith(("/", "\\")) or ":" in raw:
        raise ValueError("trace zip contains an unsafe member path")
    parts = raw.replace("\\", "/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("trace zip contains an unsafe member path")
    safe_parts = []
    for part in parts:
        sanitized = _sanitize_text(part)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", sanitized).strip(".-") or "member"
        safe_parts.append(safe)
    return "/".join(safe_parts)


def _safe_trace_zip(path: Path, checkout_roots: tuple[str, ...]) -> bytes:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("trace zip is invalid") from exc
    output = io.BytesIO()
    used_names: set[str] = set()
    total_size = 0
    with archive, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as sanitized_zip:
        infos = archive.infolist()
        if len(infos) > _MAX_ZIP_MEMBERS:
            raise ValueError("trace zip member count limit exceeded")
        for info in sorted(infos, key=lambda value: value.filename):
            if info.is_dir():
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ValueError("trace zip symlink members are not allowed")
            safe_name = _safe_zip_member_name(info.filename)
            if info.file_size > _MAX_ZIP_MEMBER_BYTES:
                raise ValueError("trace zip member size limit exceeded")
            total_size += info.file_size
            if total_size > _MAX_ZIP_TOTAL_BYTES:
                raise ValueError("trace zip total size limit exceeded")
            if info.compress_size and info.file_size / info.compress_size > _MAX_ZIP_COMPRESSION_RATIO:
                raise ValueError("trace zip compression ratio limit exceeded")
            try:
                content = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ValueError("trace zip member cannot be read safely") from exc
            if len(content) != info.file_size:
                raise ValueError("trace zip member size mismatch")
            suffix = Path(safe_name).suffix.lower()
            text_content = (
                _sanitize_text_evidence(
                    content,
                    suffix=suffix,
                    checkout_roots=checkout_roots,
                )
                if suffix in _TEXT_EVIDENCE_SUFFIXES
                else None
            )
            if text_content is None:
                safe_name = f"{safe_name}.omitted.txt"
                text_content = (
                    f"Binary resource omitted from sanitized trace: {safe_name}\n"
                ).encode("utf-8")
            if safe_name in used_names:
                suffix_digest = hashlib.sha256(info.filename.encode("utf-8")).hexdigest()[:12]
                safe_name = f"{safe_name}.{suffix_digest}"
            used_names.add(safe_name)
            target = zipfile.ZipInfo(safe_name, date_time=(1980, 1, 1, 0, 0, 0))
            target.compress_type = zipfile.ZIP_DEFLATED
            target.external_attr = 0o100600 << 16
            sanitized_zip.writestr(target, text_content)
    return output.getvalue()


def _safe_archive_content(
    path: Path,
    checkout_roots: tuple[str, ...],
) -> tuple[bytes, bool]:
    size = path.stat().st_size
    if size > _MAX_EVIDENCE_BYTES:
        raise ValueError("evidence file size limit exceeded")
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return _safe_trace_zip(path, checkout_roots), False
    content = path.read_bytes()
    if suffix == ".png":
        if size > _MAX_PNG_BYTES or not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PNG evidence is invalid or exceeds the size limit")
        return content, False
    if suffix in _TEXT_EVIDENCE_SUFFIXES:
        sanitized = _sanitize_text_evidence(
            content,
            suffix=suffix,
            checkout_roots=checkout_roots,
        )
        if sanitized is not None:
            return sanitized, False
    note = f"Binary evidence omitted: {path.name}\n".encode("utf-8")
    return _sanitize_text(note.decode("utf-8")).encode("utf-8"), True


def _evidence_source(
    raw: str,
    *,
    source_root: Path,
    namespace: str,
    checkout_roots: tuple[str, ...],
) -> dict[str, Any]:
    safe_raw = _sanitize_text(raw, checkout_roots=checkout_roots)
    if not raw or ":" in raw or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw):
        raise ValueError(f"unsafe evidence path {safe_raw!r}")
    path = Path(raw)
    if not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe evidence path {safe_raw!r}")
    root = source_root.resolve()
    candidate = path if path.is_absolute() else source_root / path
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"evidence path {safe_raw!r} must reference an existing regular file") from exc
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"unsafe evidence path {safe_raw!r}: symlink or absolute path escapes result directory"
        ) from exc
    current = source_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"unsafe evidence path {safe_raw!r}: symlink is not allowed")
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"evidence path {safe_raw!r} must reference an existing regular file")
    source_digest = _file_digest(resolved)
    archive_content, omitted = _safe_archive_content(resolved, checkout_roots)
    archive_digest = hashlib.sha256(archive_content).hexdigest()
    basename = re.sub(r"[^A-Za-z0-9._-]+", "-", resolved.name).strip(".-") or "evidence.bin"
    if omitted:
        basename = f"{basename}.omitted.txt"
    identity = f"{namespace}\0{relative.as_posix()}\0{archive_digest}"
    name_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return {
        "source": resolved,
        "source_relative": relative.as_posix(),
        "source_digest": source_digest,
        "archive_digest": archive_digest,
        "archive_content": archive_content,
        "archive_path": f"evidence/{name_digest}-{basename}",
    }


def _archive_evidence(records: list[dict[str, Any]], output_dir: Path) -> None:
    by_archive: dict[str, dict[str, Any]] = {}
    for record in records:
        archive_path = record["archive_path"]
        existing = by_archive.get(archive_path)
        if existing is not None and existing["archive_digest"] != record["archive_digest"]:
            raise ValueError(f"evidence archive collision for {archive_path}")
        by_archive[archive_path] = record
    for archive_path, record in sorted(by_archive.items()):
        source = Path(record["source"])
        if source.is_symlink() or not source.is_file() or _file_digest(source) != record["source_digest"]:
            raise ValueError("evidence source changed or is no longer a regular file")
        destination = output_dir / archive_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        archive_content = record.get("archive_content")
        if not isinstance(archive_content, bytes):
            raise ValueError("evidence archive content was not safely materialized")
        temporary.write_bytes(archive_content)
        temporary.replace(destination)


def _evidence_for_test(
    test: Mapping[str, Any],
    *,
    result_path: Path,
    namespace: str,
    checkout_roots: tuple[str, ...],
) -> list[dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    results = test.get("results")
    if not isinstance(results, list):
        return []
    for result in results:
        if not isinstance(result, Mapping) or not isinstance(result.get("attachments"), list):
            continue
        for attachment in result["attachments"]:
            if not isinstance(attachment, Mapping):
                continue
            raw_path = attachment.get("path")
            if isinstance(raw_path, str) and raw_path.strip():
                record = _evidence_source(
                    raw_path,
                    source_root=result_path.parent,
                    namespace=namespace,
                    checkout_roots=checkout_roots,
                )
                evidence[record["archive_path"]] = record
    return [evidence[key] for key in sorted(evidence)]


def _actual_for_test(test: Mapping[str, Any], checkout_roots: tuple[str, ...]) -> str:
    messages: list[str] = []
    results = test.get("results")
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, Mapping):
                continue
            raw_errors = result.get("errors")
            errors = list(raw_errors) if isinstance(raw_errors, list) else []
            if not errors and result.get("error") is not None:
                errors.append(result["error"])
            for error in errors:
                if isinstance(error, Mapping):
                    value = error.get("message", error.get("value", error.get("stack")))
                else:
                    value = error
                if isinstance(value, str) and value.strip():
                    messages.append(_sanitize_text(value.strip(), checkout_roots=checkout_roots))
    if not messages:
        messages.append(f"Playwright status: {test.get('status', 'unknown')}")
    return "\n---\n".join(sorted(set(messages)))


def _observed_status(test: Mapping[str, Any]) -> str:
    status = str(test.get("status", "")).lower()
    if status in {"expected", "passed"}:
        return "covered"
    if status in {"skipped", "flaky", "unexpected", "failed", "timedout", "timeout"}:
        return "partial"
    results = test.get("results")
    result_statuses = {
        str(result.get("status", "")).lower()
        for result in results
        if isinstance(result, Mapping)
    } if isinstance(results, list) else set()
    if result_statuses and result_statuses <= {"passed"}:
        return "covered"
    return "partial"


def _is_issue(test: Mapping[str, Any]) -> bool:
    status = str(test.get("status", "")).lower()
    if status in {"unexpected", "failed", "timedout", "timeout"}:
        return True
    if status in {"expected", "passed", "skipped", "flaky"}:
        return False
    expected_status = str(test.get("expectedStatus", "passed")).lower()
    results = test.get("results")
    if not isinstance(results, list):
        return False
    failure_statuses = {"failed", "timedout", "timeout"}
    return expected_status != "failed" and any(
        isinstance(result, Mapping) and str(result.get("status", "")).lower() in failure_statuses
        for result in results
    )


def _walk_specs(suites: object, parents: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Mapping[str, Any]]]:
    if not isinstance(suites, list):
        raise ValueError("Playwright result suites must be a list")
    specs: list[tuple[tuple[str, ...], Mapping[str, Any]]] = []
    stack: list[tuple[object, tuple[str, ...], int]] = [
        (suite, parents, 1) for suite in reversed(suites)
    ]
    suite_count = 0
    while stack:
        suite, suite_parents, depth = stack.pop()
        suite_count += 1
        if suite_count > _MAX_SUITES:
            raise ValueError("Playwright suite count limit exceeded")
        if depth > _MAX_JSON_DEPTH:
            raise ValueError("Playwright suite depth limit exceeded")
        if not isinstance(suite, Mapping):
            raise ValueError("Playwright suite entries must be objects")
        title = suite.get("title")
        next_parents = suite_parents + ((str(title),) if isinstance(title, str) and title.strip() else ())
        raw_specs = suite.get("specs", [])
        if not isinstance(raw_specs, list):
            raise ValueError("Playwright suite specs must be a list")
        for spec in raw_specs:
            if not isinstance(spec, Mapping):
                raise ValueError("Playwright spec entries must be objects")
            specs.append((next_parents, spec))
            if len(specs) > _MAX_SPECS:
                raise ValueError("Playwright spec count limit exceeded")
        child_suites = suite.get("suites", [])
        if not isinstance(child_suites, list):
            raise ValueError("Playwright child suites must be a list")
        stack.extend((child, next_parents, depth + 1) for child in reversed(child_suites))
    return specs


def _ingest_playwright_results(
    inputs: list[tuple[str | None, Path]],
    *,
    inventory: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    inventory_by_id = {item["id"]: item for item in inventory["items"]}
    known_ids = frozenset(inventory_by_id)
    events: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    profile_counts: dict[str, dict[str, int]] = {}
    browser_counts: dict[str, dict[str, int]] = {}
    test_count = 0
    result_count = 0
    attachment_count = 0

    for explicit_profile, result_path in inputs:
        payload = _load_playwright_json(result_path)
        roots = _checkout_roots(payload)
        config = payload.get("config", {})
        root_dir = config.get("rootDir") if isinstance(config, Mapping) else None
        profile = _profile_for_result(payload, explicit_profile)
        result_evidence = _evidence_source(
            str(result_path.resolve()),
            source_root=result_path.parent,
            namespace=f"playwright-result:{profile}",
            checkout_roots=roots,
        )
        for parents, spec in _walk_specs(payload["suites"]):
            title = spec.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"Playwright result {result_path}: spec title must be non-empty")
            tests = spec.get("tests")
            if not isinstance(tests, list):
                raise ValueError(f"Playwright result {result_path}: spec tests must be a list")
            relative_file = _relative_test_file(
                spec.get("file", "<unknown-file>"),
                root_dir=root_dir,
                checkout_roots=roots,
            )
            full_title = " > ".join((*parents, title))
            safe_title = _sanitize_text(full_title, checkout_roots=roots)
            for test in tests:
                test_count += 1
                if test_count > _MAX_TESTS:
                    raise ValueError("Playwright test count limit exceeded")
                if not isinstance(test, Mapping):
                    raise ValueError(f"Playwright result {result_path}: tests must be objects")
                raw_results = test.get("results", [])
                if not isinstance(raw_results, list):
                    raise ValueError(f"Playwright result {result_path}: results must be a list")
                result_count += len(raw_results)
                if result_count > _MAX_RESULTS:
                    raise ValueError("Playwright result-attempt count limit exceeded")
                for raw_result in raw_results:
                    if not isinstance(raw_result, Mapping):
                        raise ValueError(f"Playwright result {result_path}: attempts must be objects")
                    attachments = raw_result.get("attachments", [])
                    if not isinstance(attachments, list):
                        raise ValueError(f"Playwright result {result_path}: attachments must be a list")
                    attachment_count += len(attachments)
                    if attachment_count > _MAX_ATTACHMENTS:
                        raise ValueError("Playwright attachment count limit exceeded")
                project = test.get("projectName", test.get("projectId", "unknown-project"))
                if not isinstance(project, str) or not project.strip():
                    project = "unknown-project"
                project = _sanitize_text(project.strip(), checkout_roots=roots)
                aggregate_status = str(test.get("status", "unknown")).lower()
                if aggregate_status not in _PLAYWRIGHT_TEST_STATUSES:
                    raise ValueError(
                        f"Playwright result {result_path}: unsupported Playwright test status"
                    )
                profile_counts.setdefault(profile, {}).setdefault(aggregate_status, 0)
                profile_counts[profile][aggregate_status] += 1
                browser = project
                browser_counts.setdefault(browser, {}).setdefault(aggregate_status, 0)
                browser_counts[browser][aggregate_status] += 1

                inventory_ids = _inventory_ids_for_test(test, title=title, known_ids=known_ids)
                test_id = f"{project}::{relative_file}::{safe_title}"
                observation = {
                    "aggregate_status": aggregate_status,
                    "inventory_ids": inventory_ids,
                    "profile": profile,
                    "result_evidence": result_evidence,
                    "status": _observed_status(test),
                    "test_id": test_id,
                }
                observations.append(observation)
                if not _is_issue(test):
                    continue
                issue_inventory_ids = inventory_ids or ["unmapped"]
                expected_status = str(test.get("expectedStatus", "passed"))
                expected = _sanitize_text(
                    f"Expected test status: {expected_status}",
                    checkout_roots=roots,
                )
                actual = _actual_for_test(test, roots)
                events.append(
                    {
                        "actual": actual,
                        "disposition": _disposition_for_test(test, roots),
                        "evidence": _evidence_for_test(
                            test,
                            result_path=result_path,
                            namespace=f"playwright-attachment:{profile}",
                            checkout_roots=roots,
                        ),
                        "expected": expected,
                        "inventory_ids": issue_inventory_ids,
                        "root_cause": _root_cause_for_test(test),
                        "test_location": f"{relative_file}::{safe_title}",
                        "test_id": test_id,
                        "title": safe_title,
                    }
                )
    return events, observations, profile_counts, browser_counts


def _normalize_issues(
    events: list[dict[str, Any]], inventory: Mapping[str, Any]
) -> list[dict[str, Any]]:
    priority_by_id = {item["id"]: item["priority"] for item in inventory["items"]}
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        actual_fingerprint = _fingerprint_text(event["actual"])
        components = [_fingerprint_text(event["expected"])]
        stable_marker = _STABLE_ROOT_MARKER.search(actual_fingerprint)
        http_marker = _HTTP_ROOT_MARKER.search(actual_fingerprint)
        if event["root_cause"] is not None:
            components.append(f"root_cause:{event['root_cause']}")
        elif stable_marker is not None:
            components.append(f"machine:{stable_marker.group(0).lower()}")
        elif http_marker is not None:
            method, path, status = http_marker.groups()
            components.append(f"http:{method.upper()}:{path}:{status}")
        else:
            components.append(actual_fingerprint)
            scope = sorted(event["inventory_ids"])
            components.append(
                event["test_location"]
                if not scope or scope == ["unmapped"]
                else ",".join(scope)
            )
        fingerprint = "\x00".join(components)
        groups.setdefault(fingerprint, []).append(event)

    issues: list[dict[str, Any]] = []
    for fingerprint, grouped in groups.items():
        inventory_ids = sorted({item for event in grouped for item in event["inventory_ids"]})
        priorities = [priority_by_id[item] for item in inventory_ids if item in priority_by_id]
        severity = (
            "P0"
            if "unmapped" in inventory_ids or not priorities
            else min(priorities, key=_PRIORITY_ORDER.__getitem__)
        )
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]
        dispositions = sorted(
            {event["disposition"] for event in grouped if event["disposition"] is not None}
        )
        disposition_complete = all(event["disposition"] is not None for event in grouped)
        test_ids = sorted({event["test_id"] for event in grouped})
        issue: dict[str, Any] = {
            "issue_id": f"PV-{severity}-{digest}",
            "test_id": test_ids[0],
            "test_ids": test_ids,
            "inventory_ids": inventory_ids,
            "severity": severity,
            "status": "open",
            "expected": "\n---\n".join(sorted({event["expected"] for event in grouped})),
            "actual": "\n---\n".join(sorted({event["actual"] for event in grouped})),
            "evidence": sorted(
                {
                    record["archive_path"]
                    for event in grouped
                    for record in event["evidence"]
                }
            ),
            "title": sorted({event["title"] for event in grouped})[0],
            "_disposition_complete": disposition_complete,
        }
        if dispositions:
            issue["disposition"] = "\n---\n".join(dispositions)
        issues.append(issue)
    return sorted(
        issues,
        key=lambda issue: (_PRIORITY_ORDER[issue["severity"]], issue["issue_id"]),
    )


def _load_coverage_results(
    path: Path | None,
    inventory: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    if path is None:
        return {}

    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key {key!r}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON value {value}")

    _validate_json_file(path, label="coverage results", max_bytes=_MAX_COVERAGE_JSON_BYTES)
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"coverage results {path}: cannot load: {exc}") from exc
    _assert_json_limits(payload, label=f"coverage results {path}")
    if not isinstance(payload, Mapping) or set(payload) != {"schema_version", "items"}:
        raise ValueError("coverage results must contain exactly schema_version and items")
    if payload["schema_version"] != _COVERAGE_RESULTS_SCHEMA_VERSION:
        raise ValueError(f"coverage results schema_version must equal {_COVERAGE_RESULTS_SCHEMA_VERSION}")
    if not isinstance(payload["items"], list):
        raise ValueError("coverage results items must be a list")
    inventory_by_id = {item["id"]: item for item in inventory["items"]}
    results: dict[tuple[str, str], dict[str, Any]] = {}
    seen_items: set[str] = set()
    for raw_item in payload["items"]:
        if not isinstance(raw_item, Mapping) or set(raw_item) != {"inventory_id", "layers"}:
            raise ValueError("coverage result item must contain exactly inventory_id and layers")
        inventory_id = raw_item["inventory_id"]
        if not isinstance(inventory_id, str) or inventory_id not in inventory_by_id:
            raise ValueError("coverage results contain unknown inventory ID")
        if inventory_id in seen_items:
            raise ValueError(f"coverage results contain duplicate inventory ID {inventory_id!r}")
        seen_items.add(inventory_id)
        layers = raw_item["layers"]
        if not isinstance(layers, Mapping):
            raise ValueError(f"coverage results item {inventory_id}: layers must be an object")
        for layer, raw_result in layers.items():
            key = (inventory_id, layer)
            if key in results:
                raise ValueError(f"coverage results contain duplicate layer {inventory_id}:{layer}")
            if layer == "playwright" or layer not in inventory_by_id[inventory_id]["layers"]:
                raise ValueError(f"coverage results item {inventory_id}: unsupported layer {layer!r}")
            if not isinstance(raw_result, Mapping) or set(raw_result) != {"status", "evidence"}:
                raise ValueError(
                    f"coverage results item {inventory_id}:{layer} must contain status and evidence"
                )
            status = raw_result["status"]
            evidence = raw_result["evidence"]
            if status not in _OBSERVED_COVERAGE_STATUSES:
                raise ValueError(f"coverage results item {inventory_id}:{layer} has invalid status")
            if not isinstance(evidence, list) or any(not isinstance(value, str) for value in evidence):
                raise ValueError(f"coverage results item {inventory_id}:{layer} evidence must be a list")
            if len(set(evidence)) != len(evidence):
                raise ValueError(f"coverage results item {inventory_id}:{layer} evidence has duplicates")
            if status == "covered" and not evidence:
                raise ValueError(f"covered layer {inventory_id}:{layer} requires evidence")
            records = [
                _evidence_source(
                    raw,
                    source_root=path.parent,
                    namespace=f"coverage:{inventory_id}:{layer}",
                    checkout_roots=(str(path.parent.resolve()),),
                )
                for raw in evidence
            ]
            results[key] = {"status": status, "evidence": records}
    return results


def _build_playwright_coverage(
    inventory: Mapping[str, Any],
    observations: list[dict[str, Any]],
    layer_results: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_inventory_profile: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for observation in observations:
        for inventory_id in observation["inventory_ids"]:
            by_inventory_profile.setdefault((inventory_id, observation["profile"]), []).append(
                observation
            )

    rows: list[dict[str, Any]] = []
    for item in inventory["items"]:
        if not item["reachable"]:
            status = "not_applicable"
            profile_statuses: dict[str, str] = {}
            profile_evidence: dict[str, list[str]] = {}
            layer_statuses = {layer: "not_applicable" for layer in sorted(item["layers"])}
            layer_evidence = {layer: [] for layer in sorted(item["layers"])}
        else:
            profile_statuses = {}
            profile_evidence = {}
            for profile in sorted(item["profiles"]):
                profile_observations = by_inventory_profile.get((item["id"], profile), [])
                statuses = [observation["status"] for observation in profile_observations]
                if statuses and all(value == "covered" for value in statuses):
                    profile_statuses[profile] = "covered"
                elif statuses:
                    profile_statuses[profile] = "partial"
                else:
                    profile_statuses[profile] = "missing"
                profile_evidence[profile] = sorted(
                    {
                        observation["result_evidence"]["archive_path"]
                        for observation in profile_observations
                    }
                )

            layer_statuses: dict[str, str] = {}
            layer_evidence: dict[str, list[str]] = {}
            for layer in sorted(item["layers"]):
                if layer == "playwright":
                    layer_evidence[layer] = sorted(
                        {path for paths in profile_evidence.values() for path in paths}
                    )
                    if not item["profiles"]:
                        layer_statuses[layer] = "missing"
                    elif all(value == "covered" for value in profile_statuses.values()):
                        layer_statuses[layer] = "covered"
                    elif any(value != "missing" for value in profile_statuses.values()):
                        layer_statuses[layer] = "partial"
                    else:
                        layer_statuses[layer] = "missing"
                else:
                    declared = layer_results.get((item["id"], layer))
                    layer_statuses[layer] = declared["status"] if declared else "missing"
                    layer_evidence[layer] = (
                        sorted(record["archive_path"] for record in declared["evidence"])
                        if declared
                        else []
                    )
            all_statuses = [*profile_statuses.values(), *layer_statuses.values()]
            if all_statuses and all(value == "covered" for value in all_statuses):
                status = "covered"
            elif any(value != "missing" for value in all_statuses):
                status = "partial"
            else:
                status = "missing"

        rows.append(
            {
                "id": item["id"],
                "label": item["label"],
                "priority": item["priority"],
                "route": item["route"],
                "status": status,
                "layer_evidence": layer_evidence,
                "layer_statuses": layer_statuses,
                "profile_evidence": profile_evidence,
                "profile_statuses": profile_statuses,
            }
        )
    return sorted(rows, key=lambda row: (_PRIORITY_ORDER[row["priority"]], row["id"]))


def _validate_baseline_status(
    baseline_status: str,
    issues: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> None:
    if baseline_status not in _BASELINE_STATUSES:
        raise ValueError(f"baseline_status must be one of {sorted(_BASELINE_STATUSES)}")
    if baseline_status != "trusted_baseline":
        return
    if any(issue["severity"] in {"P0", "P1"} for issue in issues):
        raise ValueError("trusted_baseline is invalid while P0/P1 issues remain open")
    if any(
        issue["severity"] == "P2" and not issue["_disposition_complete"]
        for issue in issues
    ):
        raise ValueError("trusted_baseline requires every accepted P2 issue to have a disposition")
    if any(not observation["inventory_ids"] for observation in observations):
        raise ValueError("trusted_baseline rejects unmapped Playwright tests")
    coverage_by_id = {row["id"]: row for row in coverage}
    if any(
        observation["profile"] not in coverage_by_id[inventory_id]["profile_statuses"]
        for observation in observations
        for inventory_id in observation["inventory_ids"]
    ):
        raise ValueError("trusted_baseline rejects tests bound to unassigned profiles")
    unstable = sorted(
        {
            observation["aggregate_status"]
            for observation in observations
            if observation["aggregate_status"] in {"skipped", "flaky", "unexpected", "failed", "timedout", "timeout"}
        }
    )
    if unstable:
        raise ValueError(f"trusted_baseline rejects Playwright statuses {unstable}")
    incomplete = [
        row["id"]
        for row in coverage
        if row["status"] != "not_applicable" and row["status"] != "covered"
    ]
    if incomplete:
        raise ValueError(f"trusted_baseline requires complete coverage; incomplete items: {incomplete}")
    for row in coverage:
        if row["status"] == "not_applicable":
            continue
        if any(
            status != "covered" or not row["layer_evidence"].get(layer)
            for layer, status in row["layer_statuses"].items()
        ):
            raise ValueError("trusted_baseline requires traceable evidence for every required layer")
        if any(
            status != "covered" or not row["profile_evidence"].get(profile)
            for profile, status in row["profile_statuses"].items()
        ):
            raise ValueError("trusted_baseline requires traceable evidence for every required profile")
    if any(issue["severity"] == "P2" and not issue["evidence"] for issue in issues):
        raise ValueError("trusted_baseline requires evidence for every accepted P2 issue")


def _count_values(values: list[str]) -> dict[str, int]:
    return {value: values.count(value) for value in sorted(set(values))}


def _public_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in issue.items() if not key.startswith("_")}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _commit_output_directory(staging: Path, destination: Path) -> None:
    backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
    moved_old = False
    try:
        if destination.exists():
            if not destination.is_dir() or destination.is_symlink():
                raise ValueError("output_dir must be a directory and must not be a symlink")
            os.replace(destination, backup)
            moved_old = True
        os.replace(staging, destination)
    except BaseException:
        if moved_old and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    else:
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except BaseException:
                failed_new = destination.parent / f".{destination.name}.failed-{uuid.uuid4().hex}"
                os.replace(destination, failed_new)
                os.replace(backup, destination)
                shutil.rmtree(failed_new)
                raise


def _html_report(
    *,
    audit_id: str,
    revision: str,
    audit_date: str,
    baseline_status: str,
    profile_counts: Mapping[str, Mapping[str, int]],
    browser_counts: Mapping[str, Mapping[str, int]],
    blocker_counts: Mapping[str, int],
    coverage: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    issue_rows: list[str] = []
    for issue in issues:
        evidence = " ".join(
            f'<a href="{esc(path)}">{esc(path)}</a>' for path in issue["evidence"]
        ) or "none"
        issue_rows.append(
            "<tr>"
            f"<td>{esc(issue['severity'])}</td>"
            f"<td>{esc(issue['issue_id'])}</td>"
            f"<td>{esc(issue['title'])}</td>"
            f"<td>{esc(', '.join(issue['inventory_ids']))}</td>"
            f"<td><pre>{esc(issue['actual'])}</pre></td>"
            f"<td>{evidence}</td>"
            "</tr>"
        )
    coverage_rows = [
        "<tr>"
        f"<td>{esc(row['priority'])}</td><td>{esc(row['id'])}</td>"
        f"<td>{esc(row['route'])}</td><td>{esc(row['status'])}</td>"
        "</tr>"
        for row in coverage
    ]
    profile_summary = ", ".join(
        f"{esc(profile)}: {esc(sum(counts.values()))}" for profile, counts in sorted(profile_counts.items())
    ) or "none"
    browser_summary = ", ".join(
        f"{esc(browser)}: {esc(sum(counts.values()))}" for browser, counts in sorted(browser_counts.items())
    ) or "none"
    blocker_summary = ", ".join(
        f"{priority}: {blocker_counts.get(priority, 0)}" for priority in ("P0", "P1", "P2")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Platform validation audit {esc(audit_id)}</title>
  <style>
    body{{font-family:system-ui,sans-serif;margin:2rem;line-height:1.4}}
    .summary{{border:1px solid #bbb;padding:1rem}}
    table{{border-collapse:collapse;width:100%;margin-top:1rem}}
    th,td{{border:1px solid #ccc;padding:.45rem;text-align:left;vertical-align:top}}
    pre{{white-space:pre-wrap;max-width:48rem}}
    .P0,.P1{{font-weight:700}}
  </style>
</head>
<body>
  <main>
    <section class="summary" aria-label="Audit summary">
      <h1>Platform validation audit</h1>
      <dl>
        <dt>Revision</dt><dd>{esc(revision)}</dd>
        <dt>Audit ID</dt><dd>{esc(audit_id)}</dd>
        <dt>Date</dt><dd>{esc(audit_date)}</dd>
        <dt>Baseline status</dt><dd>{esc(baseline_status)}</dd>
        <dt>Profiles</dt><dd>{profile_summary}</dd>
        <dt>Browsers</dt><dd>{browser_summary}</dd>
        <dt>Blockers</dt><dd>{blocker_summary}</dd>
      </dl>
    </section>
    <section>
      <h2>Issue ledger</h2>
      <table><thead><tr><th>Severity</th><th>ID</th><th>Test</th><th>Inventory</th>
      <th>Actual</th><th>Evidence</th></tr></thead>
      <tbody>{''.join(issue_rows)}</tbody></table>
    </section>
    <section>
      <h2>Coverage matrix</h2>
      <table><thead><tr><th>Priority</th><th>Inventory</th><th>Route</th><th>Status</th></tr></thead>
      <tbody>{''.join(coverage_rows)}</tbody></table>
    </section>
  </main>
</body>
</html>
"""


def build_platform_validation_report(
    *,
    inventory: Mapping[str, Any] | str | Path,
    playwright_result_paths: list[str | Path | tuple[str, str | Path]],
    coverage_results: str | Path | None = None,
    output_dir: str | Path,
    audit_id: str,
    revision: str,
    audit_date: str,
    baseline_status: str = "baseline_candidate",
) -> dict[str, Path]:
    """Build deterministic, sanitized JSON and HTML platform-validation audit artifacts."""
    if not isinstance(audit_id, str) or not audit_id.strip():
        raise ValueError("audit_id must be a non-empty string")
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("revision must be a non-empty string")
    if not isinstance(audit_date, str) or not audit_date.strip():
        raise ValueError("audit_date must be a non-empty string")
    audit_id = _sanitize_text(audit_id.strip())
    revision = _sanitize_text(revision.strip())
    audit_date = _sanitize_text(audit_date.strip())
    validated_inventory = (
        load_inventory(inventory) if isinstance(inventory, (str, Path)) else validate_inventory(inventory)
    )
    destination = Path(output_dir)
    result_inputs = _normalize_playwright_inputs(playwright_result_paths)
    events, observations, profile_counts, browser_counts = _ingest_playwright_results(
        result_inputs,
        inventory=validated_inventory,
    )
    layer_results = _load_coverage_results(
        Path(coverage_results) if coverage_results is not None else None,
        validated_inventory,
    )
    issues = _normalize_issues(events, validated_inventory)
    coverage = _build_playwright_coverage(validated_inventory, observations, layer_results)
    _validate_baseline_status(baseline_status, issues, coverage, observations)
    evidence_records = [
        record
        for event in events
        for record in event["evidence"]
    ]
    evidence_records.extend(observation["result_evidence"] for observation in observations)
    evidence_records.extend(
        record
        for result in layer_results.values()
        for record in result["evidence"]
    )
    blocker_counts = _count_values([issue["severity"] for issue in issues])
    coverage_counts = _count_values([row["status"] for row in coverage])
    public_issues = [_public_issue(issue) for issue in issues]

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    try:
        _archive_evidence(evidence_records, staging)
        sanitized_inventory = _sanitize_payload(validated_inventory)
        _write_json(staging / "route_inventory.json", sanitized_inventory)
        _write_json(
            staging / "coverage_matrix.json",
            {
                "schema_version": _COVERAGE_SCHEMA_VERSION,
                "audit_id": audit_id,
                "summary": coverage_counts,
                "items": coverage,
            },
        )
        _write_json(
            staging / "issue_ledger.json",
            {
                "schema_version": _ISSUE_SCHEMA_VERSION,
                "audit_id": audit_id,
                "revision": revision,
                "audit_date": audit_date,
                "baseline_status": baseline_status,
                "summary": {
                    "blockers": blocker_counts,
                    "profiles": profile_counts,
                    "browsers": browser_counts,
                },
                "issues": public_issues,
            },
        )
        _atomic_write(
            staging / "audit_report.html",
            _html_report(
                audit_id=audit_id,
                revision=revision,
                audit_date=audit_date,
                baseline_status=baseline_status,
                profile_counts=profile_counts,
                browser_counts=browser_counts,
                blocker_counts=blocker_counts,
                coverage=coverage,
                issues=public_issues,
            ),
        )
        _commit_output_directory(staging, destination)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    route_inventory = destination / "route_inventory.json"
    coverage_matrix = destination / "coverage_matrix.json"
    issue_ledger = destination / "issue_ledger.json"
    audit_report = destination / "audit_report.html"
    return {
        "route_inventory": route_inventory,
        "coverage_matrix": coverage_matrix,
        "issue_ledger": issue_ledger,
        "audit_report": audit_report,
    }
