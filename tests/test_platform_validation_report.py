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

EXPECTED_LANDMARKS = {
    "home": {"role": "region", "name": "策略指挥中心"},
    "review_queue": {"role": "region", "name": "策略复盘队列"},
    "daily_review": {"role": "region", "name": "每日复盘"},
    "market_monitor": {"role": "region", "name": "Market Monitor workspace"},
    "news": {"role": "region", "name": "News workspace"},
    "research_reports": {"role": "region", "name": "Research Reports workspace"},
    "stock_workspace": {"role": "region", "name": "个股复盘工作台"},
    "watchlist": {"role": "region", "name": "Watchlist workspace"},
    "theme_research": {"role": "region", "name": "主题研究与产业目录工作台"},
    "docling_audit": {"role": "region", "name": "Data-to-Brief Docling 90-stock review"},
    "tech_bottleneck_review": {"role": "region", "name": "科技卡脖子复盘工作台"},
    "factor_lab": {"role": "region", "name": "Factor Lab workspace"},
    "strategy_lab": {"role": "region", "name": "Strategy Lab workspace"},
    "generated_reports": {"role": "region", "name": "Generated Reports workspace"},
    "user_management": {"role": "heading", "name": "用户管理"},
    "data_explorer": None,
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
        "primary_apis": [
            {
                "method": "GET",
                "path": "/api/sample",
                "access": "read",
                "census_scope": "route_load",
            }
        ],
        "layers": ["api", "playwright"],
        "profiles": ["real"],
        "daily_eod": False,
        "owner": "platform",
        "reachable": True,
        "disabled_reason": None,
        "landmark": {"role": "region", "name": "Sample workspace"},
        "route_params": {},
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
    assert items["data_explorer"]["landmark"] is None
    assert items["stock_workspace"]["route_params"] == {
        "asset_id": "authoritative_stock_asset_id"
    }
    assert {item_id: items[item_id]["landmark"] for item_id in EXPECTED_LANDMARKS} == EXPECTED_LANDMARKS


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
    assert {(api["method"], api["path"]) for api in news["primary_apis"]} >= {
        ("GET", "/api/public-news"),
        ("POST", "/api/public-news/refresh"),
    }
    assert {"api", "playwright"} <= set(news["layers"])
    assert {"real", "sandbox", "audit"} <= set(news["profiles"])
    assert "eod" not in news["profiles"]
    assert news["daily_eod"] is False


def test_inventory_operations_match_visible_workspace_writes_and_review_queue_reads() -> None:
    inventory = load_inventory(INVENTORY_PATH)
    items = {item["id"]: item for item in inventory["items"]}
    operations = {
        item_id: {(api["method"], api["path"]) for api in item["primary_apis"]}
        for item_id, item in items.items()
    }

    assert {item["id"] for item in items.values() if item["write_mode"] == "read_write"} == {
        "home",
        "news",
        "stock_workspace",
        "tech_bottleneck_review",
        "strategy_lab",
        "user_management",
    }
    assert ("POST", "/api/research/review-actions") in operations["home"]
    assert ("POST", "/api/public-news/refresh") in operations["news"]
    assert {
        ("POST", "/api/operator-decisions"),
        ("PATCH", "/api/operator-decisions/{event_id}"),
    } <= operations["stock_workspace"]
    assert {
        ("GET", "/api/research/tech-bottleneck/review-universe/decisions"),
        ("POST", "/api/research/tech-bottleneck/review-universe/decisions"),
    } <= operations["tech_bottleneck_review"]
    assert ("POST", "/api/backtests/jobs") in operations["strategy_lab"]
    assert {
        ("GET", "/api/admin/users"),
        ("POST", "/api/admin/users"),
    } <= operations["user_management"]
    assert operations["review_queue"] == {
        ("GET", "/api/review-queue"),
        ("GET", "/api/platform/summary"),
    }


def test_inventory_census_scope_separates_route_load_from_journeys() -> None:
    inventory = load_inventory(INVENTORY_PATH)
    items = {item["id"]: item for item in inventory["items"]}

    def operation(item_id: str, method: str, path: str) -> dict[str, str]:
        return next(
            api
            for api in items[item_id]["primary_apis"]
            if api["method"] == method and api["path"] == path
        )

    assert operation("news", "GET", "/api/public-news")["census_scope"] == "route_load"
    assert operation("news", "POST", "/api/public-news/refresh")["census_scope"] == "journey"
    assert {api["path"] for api in items["stock_workspace"]["primary_apis"]} == {
        "/api/assets/{asset_id}/profile",
        "/api/operator-decisions",
        "/api/operator-decisions/{event_id}",
    }
    assert operation(
        "theme_research",
        "GET",
        "/api/research/theme-decomposition/themes",
    )["census_scope"] == "route_load"
    assert operation(
        "theme_research",
        "GET",
        "/api/research/theme-decomposition/themes/{theme_id}/companies",
    )["census_scope"] == "journey"
    assert operation("factor_lab", "GET", "/api/factors/score-preview")["census_scope"] == "journey"
    assert operation("strategy_lab", "GET", "/api/strategy-validation/runs")["census_scope"] == "journey"
    assert all(
        api["access"] == "read"
        for item in items.values()
        for api in item["primary_apis"]
        if api["census_scope"] == "route_load"
    )


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
        ("landmark", "Sample workspace"),
        ("route_params", []),
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

    unknown_landmark = _item(landmark={"role": "region", "name": "Sample workspace", "exact": True})
    with pytest.raises(ValueError, match=r"item sample.*field landmark"):
        validate_inventory(_inventory(unknown_landmark))

    unknown_api = _item(
        primary_apis=[
            {
                "method": "GET",
                "path": "/api/sample",
                "access": "read",
                "census_scope": "route_load",
                "timeout": 1,
            }
        ]
    )
    with pytest.raises(ValueError, match=r"item sample.*field primary_apis"):
        validate_inventory(_inventory(unknown_api))


@pytest.mark.parametrize(
    "route",
    [
        "sample",
        "/sample/",
        "/sample//child",
        "/sample/./child",
        "/sample/../child",
        "/sample?mode=1",
        "/sample#detail",
        "/sample/%73egment",
        "/sample/{asset_id",
        "/sample/asset_id}",
        "/sample/prefix-{asset_id}",
        "/sample/{Asset_id}",
        "/sample/{1asset}",
        "/sample/{asset_id}/{asset_id}",
    ],
)
def test_validation_rejects_noncanonical_or_ambiguous_routes(route: str) -> None:
    with pytest.raises(ValueError, match=r"item sample.*field route"):
        validate_inventory(_inventory(_item(route=route)))


@pytest.mark.parametrize(
    "path",
    [
        "/sample",
        "/api/sample/",
        "/api/sample//child",
        "/api/sample/./child",
        "/api/sample/../child",
        "/api/sample?mode=1",
        "/api/sample#detail",
        "/api/%73ample",
        "/api/sample/{asset_id",
        "/api/sample/prefix-{asset_id}",
        "/api/sample/{Asset_id}",
        "/api/sample/{asset_id}/{asset_id}",
    ],
)
def test_validation_rejects_noncanonical_or_ambiguous_api_paths(path: str) -> None:
    with pytest.raises(ValueError, match=r"item sample.*field primary_apis"):
        validate_inventory(
            _inventory(
                _item(
                    primary_apis=[
                        {"method": "GET", "path": path, "access": "read", "census_scope": "route_load"}
                    ]
                )
            )
        )


def test_route_params_exactly_resolve_dynamic_route_placeholders() -> None:
    valid = _item(
        route="/stock/{asset_id}",
        route_params={"asset_id": "authoritative_stock_asset_id"},
    )
    assert validate_inventory(_inventory(valid))["items"][0]["route_params"] == valid["route_params"]

    for route_params in (
        {},
        {"asset_id": "authoritative_stock_asset_id", "extra": "authoritative_stock_asset_id"},
        {"asset_id": "hard_coded_stock"},
    ):
        with pytest.raises(ValueError, match=r"item sample.*field route_params"):
            validate_inventory(_inventory(_item(route="/stock/{asset_id}", route_params=route_params)))

    with pytest.raises(ValueError, match=r"item sample.*field route_params"):
        validate_inventory(
            _inventory(_item(route_params={"asset_id": "authoritative_stock_asset_id"}))
        )


def test_landmark_contract_requires_reachable_specific_locator_and_null_for_disabled() -> None:
    with pytest.raises(ValueError, match=r"item sample.*field landmark"):
        validate_inventory(_inventory(_item(landmark=None)))

    with pytest.raises(ValueError, match=r"item sample.*field landmark"):
        validate_inventory(_inventory(_item(landmark={"role": "region"})))

    with pytest.raises(ValueError, match=r"item sample.*field landmark"):
        validate_inventory(_inventory(_item(landmark={"role": "main", "name": "Sample"})))

    with pytest.raises(ValueError, match=r"item sample.*field landmark"):
        validate_inventory(
            _inventory(
                _item(
                    entry_kind="hidden",
                    reachable=False,
                    disabled_reason="disabled",
                    landmark={"role": "region", "name": "Sample workspace"},
                )
            )
        )


def test_primary_api_contract_allows_get_and_post_on_same_path_but_rejects_bad_method_access() -> None:
    same_path = _item(
        write_mode="read_write",
        primary_apis=[
            {"method": "GET", "path": "/api/sample", "access": "read", "census_scope": "route_load"},
            {"method": "POST", "path": "/api/sample", "access": "write", "census_scope": "journey"},
        ],
    )
    validate_inventory(_inventory(same_path))

    invalid_apis = [
        [{"method": "TRACE", "path": "/api/sample", "access": "read", "census_scope": "route_load"}],
        [{"method": "GET", "path": "/api/sample", "access": "write", "census_scope": "journey"}],
        [{"method": "POST", "path": "/api/sample", "access": "read", "census_scope": "journey"}],
        [{"method": "GET", "path": "/api/sample", "access": "public", "census_scope": "route_load"}],
        [{"method": "GET", "path": "/api/sample"}],
        [{"method": "GET", "path": "/api/sample", "access": "read"}],
        [{"method": "GET", "path": "/api/sample", "access": "read", "census_scope": "always"}],
        [{"method": "POST", "path": "/api/sample", "access": "write", "census_scope": "route_load"}],
    ]
    for primary_apis in invalid_apis:
        with pytest.raises(ValueError, match=r"item sample.*field primary_apis"):
            validate_inventory(_inventory(_item(primary_apis=primary_apis)))

    with pytest.raises(ValueError, match=r"item sample.*field primary_apis"):
        validate_inventory(
            _inventory(
                _item(
                    primary_apis=[
                        {"method": "GET", "path": "/api/sample", "access": "read", "census_scope": "route_load"},
                        {"method": "GET", "path": "/api/sample", "access": "read", "census_scope": "journey"},
                    ]
                )
            )
        )


def test_write_mode_must_match_declared_api_access() -> None:
    with pytest.raises(ValueError, match=r"item sample.*field write_mode"):
        validate_inventory(
            _inventory(
                _item(
                    primary_apis=[
                        {"method": "POST", "path": "/api/sample", "access": "write", "census_scope": "journey"}
                    ]
                )
            )
        )

    with pytest.raises(ValueError, match=r"item sample.*field write_mode"):
        validate_inventory(_inventory(_item(write_mode="read_write")))


def test_validation_rejects_duplicate_ids_and_routes_against_the_later_item() -> None:
    with pytest.raises(ValueError, match=r"item sample.*field id"):
        validate_inventory(_inventory(_item(), _item(route="/other")))

    with pytest.raises(ValueError, match=r"item other.*field route"):
        validate_inventory(_inventory(_item(), _item(id="other")))


def test_validation_rejects_p0_without_profile_and_invalid_daily_eod_or_hidden_state() -> None:
    with pytest.raises(ValueError, match=r"item sample.*field profiles"):
        validate_inventory(_inventory(_item(priority="P0", profiles=[])))

    with pytest.raises(ValueError, match=r"item sample.*field daily_eod"):
        validate_inventory(
            _inventory(
                _item(
                    write_mode="read_write",
                    primary_apis=[
                        {"method": "GET", "path": "/api/sample", "access": "read", "census_scope": "route_load"},
                        {"method": "POST", "path": "/api/sample", "access": "write", "census_scope": "journey"},
                    ],
                    profiles=["real", "eod"],
                    daily_eod=True,
                )
            )
        )

    with pytest.raises(ValueError, match=r"item sample.*field daily_eod"):
        validate_inventory(
            _inventory(
                _item(
                    entry_kind="hidden",
                    reachable=False,
                    disabled_reason="disabled",
                    landmark=None,
                    profiles=["real", "eod"],
                    daily_eod=True,
                )
            )
        )

    with pytest.raises(ValueError, match=r"item sample.*field disabled_reason"):
        validate_inventory(_inventory(_item(entry_kind="hidden", reachable=False, landmark=None)))

    with pytest.raises(ValueError, match=r"item sample.*field disabled_reason"):
        validate_inventory(_inventory(_item(disabled_reason="not used")))


def test_profiles_layers_and_daily_eod_are_consistent() -> None:
    with pytest.raises(ValueError, match=r"item sample.*field layers"):
        validate_inventory(_inventory(_item(layers=["api"], profiles=["real"])))

    with pytest.raises(ValueError, match=r"item sample.*field profiles"):
        validate_inventory(_inventory(_item(daily_eod=True, profiles=["real"])))

    with pytest.raises(ValueError, match=r"item sample.*field profiles"):
        validate_inventory(_inventory(_item(daily_eod=False, profiles=["real", "eod"])))

    valid_daily = _item(daily_eod=True, profiles=["real", "eod"])
    validate_inventory(_inventory(valid_daily))


def test_load_inventory_does_not_trust_json_shape(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps([_item()]), encoding="utf-8")

    with pytest.raises(ValueError, match=r"inventory.*field root"):
        load_inventory(path)


def test_coverage_matrix_maps_layer_and_profile_results_deterministically() -> None:
    inventory = _inventory(
        _item(id="covered", route="/z", priority="P1", layers=["api", "playwright"], profiles=["real"]),
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
            landmark=None,
        ),
    )

    matrix = build_coverage_matrix(
        inventory,
        layer_results={"covered": ["api", "playwright"], "partial": ["unit"], "disabled": ["unit"]},
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
    disabled = next(row for row in matrix if row["id"] == "disabled")
    assert disabled["missing_layers"] == []
    assert disabled["missing_profiles"] == []


def test_coverage_matrix_revalidates_inputs_and_does_not_mutate_inventory() -> None:
    inventory = _inventory()
    original = copy.deepcopy(inventory)

    with pytest.raises(ValueError, match=r"item sample.*field layer_results"):
        build_coverage_matrix(inventory, layer_results={"sample": ["unknown"]})

    assert inventory == original


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("layer_results", {"layer_results": {"sample": ["api", "api"]}}),
        ("profile_results", {"profile_results": {"sample": ["real", "real"]}}),
    ],
)
def test_coverage_matrix_rejects_duplicate_result_assignments(
    field: str, kwargs: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match=rf"item sample.*field {field}"):
        build_coverage_matrix(_inventory(), **kwargs)
