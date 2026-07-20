from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from stock_research.platform_validation_report import (
    build_coverage_matrix,
    load_inventory,
    validate_inventory,
)


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "config" / "platform_validation_routes.json"

REQUIRED_IDS = {
    "home",
    "review_queue",
    "daily_review",
    "market_monitor",
    "news",
    "research_reports",
    "stock_workspace",
    "watchlist",
    "theme_research",
    "docling_audit",
    "tech_bottleneck_review",
    "factor_lab",
    "strategy_lab",
    "generated_reports",
    "user_management",
    "data_explorer",
}

CANONICAL_ROUTES = {
    "home": "/",
    "review_queue": "/review-queue",
    "daily_review": "/daily-review",
    "market_monitor": "/market-monitor",
    "news": "/news",
    "research_reports": "/research-reports",
    "stock_workspace": "/stock/{asset_id}",
    "watchlist": "/watchlist",
    "theme_research": "/theme-research",
    "docling_audit": "/research/data-to-brief/docling-90",
    "tech_bottleneck_review": "/research/tech-bottleneck/review-universe",
    "factor_lab": "/factor-lab",
    "strategy_lab": "/strategy-lab",
    "generated_reports": "/generated-reports",
    "user_management": "/admin/users",
}


def _item(**updates: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": "sample",
        "label": "Sample",
        "route": "/sample",
        "entry_kind": "main_navigation",
        "priority": "P1",
        "auth": "authenticated",
        "write_mode": "read_only",
        "primary_apis": ["/api/sample"],
        "layers": ["api", "playwright"],
        "profiles": ["real"],
        "daily_eod": False,
        "owner": "platform",
        "reachable": True,
        "disabled_reason": None,
    }
    item.update(updates)
    return item


def _inventory(*items: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "platform_validation_inventory_v1",
        "items": list(items) or [_item()],
    }


def test_loads_complete_maintained_inventory_with_canonical_routes() -> None:
    inventory = load_inventory(INVENTORY_PATH)

    assert inventory["schema_version"] == "platform_validation_inventory_v1"
    items = {item["id"]: item for item in inventory["items"]}
    assert set(items) >= REQUIRED_IDS
    assert {item_id: items[item_id]["route"] for item_id in CANONICAL_ROUTES} == CANONICAL_ROUTES
    assert items["data_explorer"]["entry_kind"] == "hidden"
    assert items["data_explorer"]["reachable"] is False
    assert items["data_explorer"]["disabled_reason"]


def test_inventory_contract_has_unique_ids_routes_and_required_assignments() -> None:
    inventory = load_inventory(INVENTORY_PATH)
    items = inventory["items"]

    assert len({item["id"] for item in items}) == len(items)
    assert len({item["route"] for item in items}) == len(items)
    assert all(item["layers"] for item in items)
    assert all(item["profiles"] for item in items if item["priority"] == "P0")
    assert all(item["write_mode"] == "read_only" for item in items if item["daily_eod"])
    assert all(item["reachable"] for item in items if item["daily_eod"])


def test_news_inventory_classifies_visible_refresh_as_sandboxed_write() -> None:
    inventory = load_inventory(INVENTORY_PATH)
    news = next(item for item in inventory["items"] if item["id"] == "news")

    assert news["write_mode"] == "read_write"
    assert "/api/public-news" in news["primary_apis"]
    assert "/api/public-news/refresh" in news["primary_apis"]
    assert {"api", "playwright"} <= set(news["layers"])
    assert {"real", "sandbox", "audit"} <= set(news["profiles"])
    assert "eod" not in news["profiles"]
    assert news["daily_eod"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("priority", "urgent"),
        ("entry_kind", "sidebar-ish"),
        ("auth", True),
        ("write_mode", "sometimes"),
        ("primary_apis", "/api/sample"),
        ("layers", ["browser-ish"]),
        ("profiles", ["nightly"]),
        ("daily_eod", 1),
        ("reachable", "yes"),
        ("owner", ""),
    ],
)
def test_validation_fails_closed_with_item_and_field_for_invalid_values(field: str, value: object) -> None:
    item = _item()
    item[field] = value

    with pytest.raises(ValueError, match=rf"item sample.*field {field}"):
        validate_inventory(_inventory(item))


def test_validation_rejects_missing_and_unknown_item_fields() -> None:
    missing = _item()
    del missing["auth"]
    with pytest.raises(ValueError, match=r"item sample.*field auth"):
        validate_inventory(_inventory(missing))

    unknown = _item(mystery=True)
    with pytest.raises(ValueError, match=r"item sample.*field mystery"):
        validate_inventory(_inventory(unknown))


def test_validation_rejects_duplicate_ids_and_routes_against_the_later_item() -> None:
    with pytest.raises(ValueError, match=r"item sample.*field id"):
        validate_inventory(_inventory(_item(), _item(route="/other")))

    with pytest.raises(ValueError, match=r"item other.*field route"):
        validate_inventory(_inventory(_item(), _item(id="other")))


def test_validation_rejects_p0_without_profile_and_invalid_daily_eod_or_hidden_state() -> None:
    with pytest.raises(ValueError, match=r"item sample.*field profiles"):
        validate_inventory(_inventory(_item(priority="P0", profiles=[])))

    with pytest.raises(ValueError, match=r"item sample.*field daily_eod"):
        validate_inventory(_inventory(_item(write_mode="read_write", daily_eod=True)))

    with pytest.raises(ValueError, match=r"item sample.*field daily_eod"):
        validate_inventory(
            _inventory(
                _item(
                    entry_kind="hidden",
                    reachable=False,
                    disabled_reason="disabled",
                    daily_eod=True,
                )
            )
        )

    with pytest.raises(ValueError, match=r"item sample.*field disabled_reason"):
        validate_inventory(_inventory(_item(entry_kind="hidden", reachable=False)))

    with pytest.raises(ValueError, match=r"item sample.*field disabled_reason"):
        validate_inventory(_inventory(_item(disabled_reason="not used")))


def test_load_inventory_does_not_trust_json_shape(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps([_item()]), encoding="utf-8")

    with pytest.raises(ValueError, match=r"inventory.*field root"):
        load_inventory(path)


def test_coverage_matrix_maps_layer_and_profile_results_deterministically() -> None:
    inventory = _inventory(
        _item(id="covered", route="/z", priority="P1", layers=["api"], profiles=["real"]),
        _item(id="partial", route="/a", priority="P0", layers=["unit", "playwright"], profiles=["mock"]),
        _item(id="missing", route="/m", priority="P2", layers=["api"], profiles=[]),
        _item(
            id="disabled",
            route="/disabled",
            entry_kind="hidden",
            priority="P2",
            layers=["unit"],
            profiles=[],
            reachable=False,
            disabled_reason="not registered in AppShell",
        ),
    )

    matrix = build_coverage_matrix(
        inventory,
        layer_results={"covered": ["api"], "partial": ["unit"], "disabled": ["unit"]},
        profile_results={"covered": ["real"]},
    )

    assert [row["id"] for row in matrix] == ["partial", "covered", "disabled", "missing"]
    assert {row["id"]: row["status"] for row in matrix} == {
        "covered": "covered",
        "partial": "partial",
        "missing": "missing",
        "disabled": "not_applicable",
    }
    assert matrix[0]["covered_layers"] == ["unit"]
    assert matrix[0]["missing_layers"] == ["playwright"]
    assert matrix[0]["missing_profiles"] == ["mock"]


def test_coverage_matrix_revalidates_inputs_and_does_not_mutate_inventory() -> None:
    inventory = _inventory()
    original = copy.deepcopy(inventory)

    with pytest.raises(ValueError, match=r"item sample.*field layers"):
        build_coverage_matrix(inventory, layer_results={"sample": ["unknown"]})

    assert inventory == original
