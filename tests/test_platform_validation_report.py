from __future__ import annotations

import copy
import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

from stock_research.platform_validation_report import (
    build_coverage_matrix,
    build_platform_validation_report,
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


def _playwright_payload(
    *,
    root: Path,
    profile: str,
    project: str,
    specs: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "config": {
            "rootDir": str(root / "dashboard" / "tests"),
            "metadata": {"platformValidationProfile": profile},
            "projects": [{"name": project}],
        },
        "suites": [
            {
                "title": "e2e",
                "suites": [
                    {
                        "title": "nested",
                        "file": "e2e/audit.spec.ts",
                        "specs": specs,
                    }
                ],
            }
        ],
    }


def _playwright_spec(
    *,
    title: str,
    inventory_id: str | None,
    project: str,
    status: str,
    error: str | None = None,
    attachment: str | None = None,
    disposition: str | None = None,
) -> dict[str, object]:
    annotations: list[dict[str, str]] = []
    if inventory_id is not None:
        annotations.append({"type": "inventory_id", "description": inventory_id})
    if disposition is not None:
        annotations.append({"type": "disposition", "description": disposition})
    result_status = {
        "expected": "passed",
        "skipped": "skipped",
        "unexpected": "failed",
        "timedout": "timedOut",
    }[status]
    result: dict[str, object] = {
        "status": result_status,
        "errors": [] if error is None else [{"message": error}],
        "attachments": [],
    }
    if attachment is not None:
        result["attachments"] = [
            {"name": "trace", "contentType": "application/zip", "path": attachment}
        ]
    return {
        "title": title,
        "file": "e2e/audit.spec.ts",
        "tests": [
            {
                "projectName": project,
                "expectedStatus": "passed",
                "status": status,
                "annotations": annotations,
                "results": [result],
            }
        ],
    }


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _report_inventory() -> dict[str, object]:
    return _inventory(
        _item(id="home", route="/", priority="P0", profiles=["mock", "real"]),
        _item(id="research", route="/research", priority="P1", profiles=["real"]),
        _item(id="notice", route="/notice", priority="P2", profiles=["audit"]),
        _item(
            id="disabled",
            route="/disabled",
            entry_kind="hidden",
            priority="P2",
            profiles=[],
            layers=["unit"],
            reachable=False,
            disabled_reason="not registered",
            landmark=None,
        ),
    )


def test_report_ingests_nested_playwright_results_deduplicates_and_writes_all_artifacts(
    tmp_path: Path,
) -> None:
    inventory = _report_inventory()
    root = tmp_path / "checkout"
    first = _write_json(
        tmp_path / "results" / "real" / "results.json",
        _playwright_payload(
            root=root,
            profile="real",
            project="chromium-desktop",
            specs=[
                _playwright_spec(
                    title="home route loads <script>alert(1)</script>",
                    inventory_id="home",
                    project="chromium-desktop",
                    status="unexpected",
                    error=(
                        f"\u001b[31mTimeout 30000ms at {root}/dashboard/tests/"
                        "e2e/audit.spec.ts:91:7 http://127.0.0.1:5174/\u001b[0m"
                    ),
                    attachment="artifacts/home/trace.zip",
                ),
                _playwright_spec(
                    title="research route skipped",
                    inventory_id="research",
                    project="chromium-desktop",
                    status="skipped",
                ),
            ],
        ),
    )
    second = _write_json(
        tmp_path / "results" / "mock" / "results.json",
        _playwright_payload(
            root=root,
            profile="mock",
            project="webkit-mobile",
            specs=[
                _playwright_spec(
                    title="same home root symptom",
                    inventory_id="home",
                    project="webkit-mobile",
                    status="timedout",
                    error=f"Timeout 30000ms at {root}/dashboard/tests/e2e/audit.spec.ts:207:3 http://localhost:9321/",
                    attachment="artifacts/home/screenshot.png",
                ),
                _playwright_spec(
                    title="home passes elsewhere",
                    inventory_id="home",
                    project="webkit-mobile",
                    status="expected",
                ),
            ],
        ),
    )

    paths = build_platform_validation_report(
        inventory=inventory,
        playwright_result_paths=[second, first],
        output_dir=tmp_path / "audit",
        audit_id="audit-001",
        revision="abc123",
        audit_date="2026-07-21",
        baseline_status="baseline_candidate",
    )

    assert set(paths) == {"route_inventory", "coverage_matrix", "issue_ledger", "audit_report"}
    ledger = json.loads(paths["issue_ledger"].read_text(encoding="utf-8"))
    assert ledger["baseline_status"] == "baseline_candidate"
    assert len(ledger["issues"]) == 1
    issue = ledger["issues"][0]
    assert issue["issue_id"].startswith("PV-P0-")
    assert issue["severity"] == "P0"
    assert issue["status"] == "open"
    assert issue["inventory_ids"] == ["home"]
    assert len(issue["test_ids"]) == 2
    assert issue["test_id"] == issue["test_ids"][0]
    assert issue["evidence"] == [
        "artifacts/home/screenshot.png",
        "artifacts/home/trace.zip",
    ]
    assert "\u001b" not in issue["actual"]
    assert str(root) not in issue["actual"]

    matrix = json.loads(paths["coverage_matrix"].read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in matrix["items"]}
    assert rows["home"]["status"] == "partial"
    assert rows["home"]["profile_statuses"] == {"mock": "partial", "real": "partial"}
    assert rows["research"]["status"] == "partial"
    assert rows["research"]["profile_statuses"] == {"real": "partial"}
    assert rows["notice"]["status"] == "missing"
    assert rows["disabled"]["status"] == "not_applicable"

    html = paths["audit_report"].read_text(encoding="utf-8")
    assert "abc123" in html and "audit-001" in html and "2026-07-21" in html
    assert "chromium-desktop" in html and "webkit-mobile" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert 'href="artifacts/home/trace.zip"' in html


def test_issue_ids_and_output_are_stable_across_input_order_roots_ansi_ports_and_line_noise(
    tmp_path: Path,
) -> None:
    inventory = _report_inventory()

    def write(root_name: str, port: int, line: int, color: bool) -> Path:
        root = tmp_path / root_name
        error = (
            f"Timeout 30000ms 2026-07-21T12:34:56.789Z at "
            f"{root}/dashboard/tests/e2e/audit.spec.ts:{line}:7 http://127.0.0.1:{port}/"
        )
        if color:
            error = f"\u001b[31m{error}\u001b[0m"
        return _write_json(
            tmp_path / f"{root_name}.json",
            _playwright_payload(
                root=root,
                profile="real",
                project="chromium-desktop",
                specs=[
                    _playwright_spec(
                        title="home stable failure",
                        inventory_id="home",
                        project="chromium-desktop",
                        status="unexpected",
                        error=error,
                    )
                ],
            ),
        )

    left = write("checkout-a", 5174, 41, True)
    right = write("checkout-b", 9321, 912, False)
    first = build_platform_validation_report(
        inventory=inventory,
        playwright_result_paths=[left, right],
        output_dir=tmp_path / "out-a",
        audit_id="stable",
        revision="rev",
        audit_date="2026-07-21",
    )
    second = build_platform_validation_report(
        inventory=inventory,
        playwright_result_paths=[right, left],
        output_dir=tmp_path / "out-b",
        audit_id="stable",
        revision="rev",
        audit_date="2026-07-21",
    )

    first_ledger = json.loads(first["issue_ledger"].read_text(encoding="utf-8"))
    second_ledger = json.loads(second["issue_ledger"].read_text(encoding="utf-8"))
    assert first_ledger == second_ledger
    assert first["audit_report"].read_bytes() == second["audit_report"].read_bytes()


def test_report_redacts_recursive_secrets_rejects_unsafe_evidence_and_escapes_html(
    tmp_path: Path,
) -> None:
    secret = "DO-NOT-LEAK"
    payload = _playwright_payload(
        root=tmp_path / "root",
        profile="audit",
        project="firefox-desktop",
        specs=[
            _playwright_spec(
                title=f"notice <img src=x onerror=alert(1)> token={secret}",
                inventory_id="notice",
                project="firefox-desktop",
                status="unexpected",
                error=(
                    f"Authorization: Bearer {secret}\nCookie: sid={secret}\n"
                    f"password={secret} https://example.test/api/token/{secret}?api_key={secret}"
                ),
                attachment="../escape/trace.zip",
                disposition="accepted: visual-only",
            )
        ],
    )
    result = _write_json(tmp_path / "results.json", payload)

    with pytest.raises(ValueError, match="unsafe evidence path"):
        build_platform_validation_report(
            inventory=_report_inventory(),
            playwright_result_paths=[result],
            output_dir=tmp_path / "out",
            audit_id="unsafe",
            revision="rev",
            audit_date="2026-07-21",
        )

    payload["suites"][0]["suites"][0]["specs"][0]["tests"][0]["results"][0]["attachments"] = []  # type: ignore[index]
    _write_json(result, payload)
    paths = build_platform_validation_report(
        inventory=_report_inventory(),
        playwright_result_paths=[result],
        output_dir=tmp_path / "out",
        audit_id="safe",
        revision=f"token={secret}",
        audit_date="2026-07-21",
    )
    combined = b"\n".join(path.read_bytes() for path in paths.values())
    assert secret.encode() not in combined
    assert b"Authorization:" not in combined
    assert b"Cookie:" not in combined
    html = paths["audit_report"].read_text(encoding="utf-8")
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html


def test_trusted_baseline_requires_no_p0_p1_and_disposition_for_every_p2_issue(
    tmp_path: Path,
) -> None:
    p2_without_disposition = _write_json(
        tmp_path / "p2.json",
        _playwright_payload(
            root=tmp_path / "root",
            profile="audit",
            project="chromium-desktop",
            specs=[
                _playwright_spec(
                    title="notice mismatch",
                    inventory_id="notice",
                    project="chromium-desktop",
                    status="unexpected",
                    error="visual mismatch",
                )
            ],
        ),
    )
    with pytest.raises(ValueError, match="trusted_baseline.*P2.*disposition"):
        build_platform_validation_report(
            inventory=_report_inventory(),
            playwright_result_paths=[p2_without_disposition],
            output_dir=tmp_path / "no-disposition",
            audit_id="trusted",
            revision="rev",
            audit_date="2026-07-21",
            baseline_status="trusted_baseline",
        )

    payload = json.loads(p2_without_disposition.read_text(encoding="utf-8"))
    payload["suites"][0]["suites"][0]["specs"][0]["tests"][0]["annotations"].append(
        {"type": "disposition", "description": "accepted: documented browser variance"}
    )
    _write_json(p2_without_disposition, payload)
    paths = build_platform_validation_report(
        inventory=_report_inventory(),
        playwright_result_paths=[p2_without_disposition],
        output_dir=tmp_path / "trusted",
        audit_id="trusted",
        revision="rev",
        audit_date="2026-07-21",
        baseline_status="trusted_baseline",
    )
    ledger = json.loads(paths["issue_ledger"].read_text(encoding="utf-8"))
    assert ledger["baseline_status"] == "trusted_baseline"
    assert ledger["issues"][0]["disposition"] == "accepted: documented browser variance"

    p0 = _write_json(
        tmp_path / "p0.json",
        _playwright_payload(
            root=tmp_path / "root",
            profile="real",
            project="chromium-desktop",
            specs=[
                _playwright_spec(
                    title="home broken",
                    inventory_id="home",
                    project="chromium-desktop",
                    status="unexpected",
                    error="route does not load",
                    disposition="accepted: not enough",
                )
            ],
        ),
    )
    with pytest.raises(ValueError, match="trusted_baseline.*P0/P1"):
        build_platform_validation_report(
            inventory=_report_inventory(),
            playwright_result_paths=[p0],
            output_dir=tmp_path / "p0-out",
            audit_id="trusted",
            revision="rev",
            audit_date="2026-07-21",
            baseline_status="trusted_baseline",
        )


def test_inventory_mapping_prefers_annotations_then_route_census_and_marks_unmapped(
    tmp_path: Path,
) -> None:
    route_census = base64.b64encode(
        json.dumps({"inventoryId": "research", "status": "failed"}).encode()
    ).decode()
    annotated = _playwright_spec(
        title="[inventory:notice] annotation wins",
        inventory_id="home",
        project="chromium-desktop",
        status="unexpected",
        error="annotation failure",
    )
    attached = _playwright_spec(
        title="unlabelled route census",
        inventory_id=None,
        project="chromium-desktop",
        status="unexpected",
        error="census failure",
    )
    attached["tests"][0]["results"][0]["attachments"] = [  # type: ignore[index]
        {
            "name": "route-census.json",
            "contentType": "application/json",
            "body": route_census,
        }
    ]
    unmapped = _playwright_spec(
        title="plain unrelated test title",
        inventory_id=None,
        project="chromium-desktop",
        status="unexpected",
        error="unmapped failure",
    )
    p2_title = _playwright_spec(
        title="[inventory:notice] exact title metadata",
        inventory_id=None,
        project="chromium-desktop",
        status="unexpected",
        error="notice-only failure",
    )
    result = _write_json(
        tmp_path / "mapping.json",
        _playwright_payload(
            root=tmp_path / "root",
            profile="real",
            project="chromium-desktop",
            specs=[unmapped, p2_title, attached, annotated],
        ),
    )
    paths = build_platform_validation_report(
        inventory=_report_inventory(),
        playwright_result_paths=[result],
        output_dir=tmp_path / "mapped",
        audit_id="mapping",
        revision="rev",
        audit_date="2026-07-21",
    )
    issues = json.loads(paths["issue_ledger"].read_text(encoding="utf-8"))["issues"]
    assert {tuple(issue["inventory_ids"]) for issue in issues} == {
        ("home",),
        ("notice",),
        ("research",),
        ("unmapped",),
    }
    assert [issue["severity"] for issue in issues] == ["P0", "P0", "P1", "P2"]
    assert next(issue for issue in issues if issue["inventory_ids"] == ["unmapped"])["severity"] == "P0"


def test_report_fails_closed_for_malformed_json_unknown_inventory_and_bad_baseline(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Playwright result.*cannot load"):
        build_platform_validation_report(
            inventory=_report_inventory(),
            playwright_result_paths=[malformed],
            output_dir=tmp_path / "bad-json",
            audit_id="bad",
            revision="rev",
            audit_date="2026-07-21",
        )

    unknown = _write_json(
        tmp_path / "unknown.json",
        _playwright_payload(
            root=tmp_path / "root",
            profile="real",
            project="chromium-desktop",
            specs=[
                _playwright_spec(
                    title="unknown mapping",
                    inventory_id="not_in_inventory",
                    project="chromium-desktop",
                    status="unexpected",
                    error="broken",
                )
            ],
        ),
    )
    with pytest.raises(ValueError, match="unknown inventory ID"):
        build_platform_validation_report(
            inventory=_report_inventory(),
            playwright_result_paths=[unknown],
            output_dir=tmp_path / "unknown-out",
            audit_id="bad",
            revision="rev",
            audit_date="2026-07-21",
        )

    with pytest.raises(ValueError, match="baseline_status"):
        build_platform_validation_report(
            inventory=_report_inventory(),
            playwright_result_paths=[],
            output_dir=tmp_path / "bad-status",
            audit_id="bad",
            revision="rev",
            audit_date="2026-07-21",
            baseline_status="trusted-ish",
        )

    bad_status = json.loads(unknown.read_text(encoding="utf-8"))
    bad_status["suites"][0]["suites"][0]["specs"][0]["tests"][0]["annotations"] = [
        {"type": "inventory_id", "description": "home"}
    ]
    bad_status["suites"][0]["suites"][0]["specs"][0]["tests"][0]["status"] = "mystery"
    _write_json(unknown, bad_status)
    with pytest.raises(ValueError, match="unsupported Playwright test status"):
        build_platform_validation_report(
            inventory=_report_inventory(),
            playwright_result_paths=[unknown],
            output_dir=tmp_path / "bad-test-status",
            audit_id="bad",
            revision="rev",
            audit_date="2026-07-21",
        )


def test_report_cli_help_and_fixture_smoke(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "build_platform_validation_report.py"
    help_result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--playwright-results" in help_result.stdout
    assert "--baseline-status" in help_result.stdout

    results = _write_json(
        tmp_path / "real" / "results.json",
        {"config": {"metadata": {"platformValidationProfile": "real"}}, "suites": []},
    )
    output = tmp_path / "audit"
    run_result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(INVENTORY_PATH),
            "--playwright-results",
            str(results),
            "--output-dir",
            str(output),
            "--audit-id",
            "cli-smoke",
            "--revision",
            "deadbeef",
            "--audit-date",
            "2026-07-21",
            "--baseline-status",
            "baseline_candidate",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run_result.returncode == 0, run_result.stderr
    assert {path.name for path in output.iterdir()} == {
        "route_inventory.json",
        "coverage_matrix.json",
        "issue_ledger.json",
        "audit_report.html",
    }
