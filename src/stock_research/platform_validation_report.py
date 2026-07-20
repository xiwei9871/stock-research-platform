from __future__ import annotations

import json
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
    }
)
ENTRY_KINDS = frozenset({"main_navigation", "admin_navigation", "deep_link", "hidden"})
PRIORITIES = frozenset({"P0", "P1", "P2"})
AUTH_MODES = frozenset({"authenticated", "admin"})
WRITE_MODES = frozenset({"read_only", "read_write"})
LAYERS = frozenset({"unit", "api", "playwright"})
PLAYWRIGHT_PROFILES = frozenset({"legacy", "mock", "real", "sandbox", "audit", "eod"})
COVERAGE_STATUSES = frozenset({"covered", "partial", "missing", "not_applicable"})

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


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
    route = _require_string(item, item_id, "route")
    if not route.startswith("/") or "?" in route or "#" in route or "//" in route:
        raise _item_error(item_id, "route", "must be a canonical absolute path without query or fragment")
    entry_kind = _require_enum(item, item_id, "entry_kind", ENTRY_KINDS)
    priority = _require_enum(item, item_id, "priority", PRIORITIES)
    _require_enum(item, item_id, "auth", AUTH_MODES)
    write_mode = _require_enum(item, item_id, "write_mode", WRITE_MODES)
    primary_apis = _require_string_list(item, item_id, "primary_apis", non_empty=True)
    if any(not api.startswith("/api/") or "?" in api or "#" in api for api in primary_apis):
        raise _item_error(item_id, "primary_apis", "must contain canonical /api/ paths without query or fragment")
    _require_string_list(item, item_id, "layers", allowed=LAYERS, non_empty=True)
    profiles = _require_string_list(item, item_id, "profiles", allowed=PLAYWRIGHT_PROFILES)
    if priority == "P0" and not profiles:
        raise _item_error(item_id, "profiles", "P0 items require a named Playwright profile")

    daily_eod = item["daily_eod"]
    if type(daily_eod) is not bool:
        raise _item_error(item_id, "daily_eod", "must be a boolean")
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
        assigned = set(inventory_items[item_id][assignment_field])
        unsupported = sorted(set(values) - assigned)
        if unsupported:
            raise _item_error(item_id, assignment_field, f"result contains unassigned values {unsupported}")
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
