from __future__ import annotations

import json
import re
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
API_FIELDS = frozenset({"method", "path", "access"})
API_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "POST", "PATCH", "PUT", "DELETE"})
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
API_ACCESS = frozenset({"read", "write"})
ROUTE_PARAM_SOURCES = frozenset({"authoritative_stock_asset_id"})

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


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
            raise _item_error(item_id, "primary_apis", "entries must contain exactly method, path, and access")
        method = api["method"]
        access = api["access"]
        if not isinstance(method, str) or method not in API_METHODS:
            raise _item_error(item_id, "primary_apis", f"method must be one of {sorted(API_METHODS)}")
        if not isinstance(access, str) or access not in API_ACCESS:
            raise _item_error(item_id, "primary_apis", f"access must be one of {sorted(API_ACCESS)}")
        expected_access = "read" if method in READ_METHODS else "write"
        if access != expected_access:
            raise _item_error(item_id, "primary_apis", f"{method} requires access {expected_access}")
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
