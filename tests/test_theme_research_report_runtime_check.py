import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = REPO_ROOT / "deploy/check_theme_research_report_runtime.py"
    spec = importlib.util.spec_from_file_location("theme_report_runtime_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ok_permissions(service: str, profile: str) -> dict[str, object]:
    return {
        "status": "ok",
        "service": service,
        "profile": profile,
        "current_user": f"{profile}_login",
        "privileges": {},
    }


def test_cli_rejects_duplicate_capability_services_before_database_access(
    monkeypatch, capsys
):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "_schema_status",
        lambda _service: pytest.fail("database access must not happen"),
    )

    with pytest.raises(SystemExit) as exc_info:
        module.cli(
            [
                "--schema-only",
                "--runtime-service",
                "shared",
                "--index-service",
                "shared",
                "--review-service",
                "reviewer",
            ]
        )

    assert exc_info.value.code == 2
    assert "distinct non-empty" in capsys.readouterr().err


def test_schema_only_checks_all_three_distinct_permission_profiles(monkeypatch, capsys):
    module = _load_module()
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module,
        "_schema_status",
        lambda service: {"service": service, "status": "current", "schema_version": "5"},
    )

    def permission_status(service: str, profile: str):
        calls.append((service, profile))
        return _ok_permissions(service, profile)

    monkeypatch.setattr(module, "_permission_status", permission_status)

    assert (
        module.cli(
            [
                "--schema-only",
                "--migration-service",
                "migration",
                "--runtime-service",
                "runtime",
                "--index-service",
                "indexer",
                "--review-service",
                "reviewer",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert calls == [
        ("runtime", "runtime"),
        ("indexer", "indexer"),
        ("reviewer", "reviewer"),
    ]
    assert payload["status"] == "ok"
    assert set(payload["service_permissions"]) == {"runtime", "indexer", "reviewer"}


def test_full_check_scans_with_index_service_after_safe_permission_probes(
    monkeypatch, capsys
):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "SETTINGS",
        SimpleNamespace(
            theme_research_report_root="/app/reports/theme-research",
            theme_research_migration_service="migration",
            theme_research_runtime_service="runtime",
            theme_research_report_index_service="indexer",
            theme_research_report_review_service="reviewer",
        ),
    )
    monkeypatch.setattr(
        module,
        "_schema_status",
        lambda service: {"service": service, "status": "current", "schema_version": "5"},
    )
    monkeypatch.setattr(
        module,
        "_permission_status",
        lambda service, profile: _ok_permissions(service, profile),
    )
    monkeypatch.setattr(
        module,
        "_root_status",
        lambda root: {
            "path": str(root),
            "exists": True,
            "readable": True,
            "readonly": True,
        },
    )
    index_services: list[str] = []

    def index_status(_root, service):
        index_services.append(service)
        return {"status": "ok", "invalid": 0, "errors": []}

    monkeypatch.setattr(module, "_index_status", index_status)

    assert (
        module.cli(
            [
                "--expected-root",
                "/app/reports/theme-research",
                "--migration-service",
                "migration",
                "--runtime-service",
                "runtime",
                "--index-service",
                "indexer",
                "--review-service",
                "reviewer",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert index_services == ["indexer"]
    assert payload["status"] == "ok"


def test_permission_probe_is_read_only_and_checks_function_and_table_privileges():
    source = (
        REPO_ROOT / "deploy/check_theme_research_report_runtime.py"
    ).read_text(encoding="utf-8")

    assert "has_function_privilege" in source
    assert "has_table_privilege" in source
    assert "register_theme_research_report_pending" in source
    assert "review_theme_research_report_version" in source
    assert "INSERT INTO" not in source
    assert "UPDATE research." not in source
    assert "DELETE FROM" not in source
