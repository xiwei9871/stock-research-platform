import importlib.util
import json
from contextlib import contextmanager
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
        "session_user": f"{profile}_login",
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
        lambda service: {
            "service": service,
            "status": "current",
            "schema_version": "5",
            "current_user": "theme_research_owner",
            "session_user": "migration_login",
        },
    )

    def permission_status(service: str, profile: str, _forbidden_roles):
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
        lambda service: {
            "service": service,
            "status": "current",
            "schema_version": "5",
            "current_user": "theme_research_owner",
            "session_user": "migration_login",
        },
    )
    monkeypatch.setattr(
        module,
        "_permission_status",
        lambda service, profile, _forbidden_roles: _ok_permissions(service, profile),
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


def test_schema_only_rejects_three_aliases_backed_by_same_login(monkeypatch, capsys):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "_schema_status",
        lambda service: {
            "service": service,
            "status": "current",
            "schema_version": "5",
            "current_user": "theme_research_owner",
            "session_user": "migration_login",
        },
    )

    def shared_login(service: str, profile: str, _forbidden_roles):
        result = _ok_permissions(service, profile)
        result["session_user"] = "shared_login"
        return result

    monkeypatch.setattr(module, "_permission_status", shared_login)

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
        == 1
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "error"
    assert payload["service_identity"]["status"] == "error"
    assert payload["service_identity"]["session_users"] == {
        "runtime": "shared_login",
        "indexer": "shared_login",
        "reviewer": "shared_login",
    }


def test_permission_probe_rejects_hidden_indirect_cross_capability_membership(
    monkeypatch,
):
    module = _load_module()
    privilege_row = {
        "current_user": "runtime_login",
        "session_user": "runtime_login",
        "schema_usage": True,
        "version_select": True,
        "review_event_select": True,
        "version_write": False,
        "review_event_write": False,
        "register_execute": False,
        "review_execute": False,
    }
    login_memberships = [
        {
            "role_name": "theme_research_runtime",
            "member": True,
            "usage": True,
            "can_set": True,
            "direct_member": True,
        },
        {
            "role_name": "theme_research_report_indexer",
            "member": True,
            "usage": False,
            "can_set": False,
            "direct_member": False,
        },
        {
            "role_name": "theme_research_report_reviewer",
            "member": False,
            "usage": False,
            "can_set": False,
            "direct_member": False,
        },
        {
            "role_name": "theme_research_owner",
            "member": False,
            "usage": False,
            "can_set": False,
            "direct_member": False,
        },
        {
            "role_name": "migration_login",
            "member": False,
            "usage": False,
            "can_set": False,
            "direct_member": False,
        },
    ]
    capability_graph = [
        {
            "source_role": "theme_research_runtime",
            "target_role": "theme_research_report_indexer",
            "member": False,
            "usage": False,
            "can_set": False,
            "direct_member": False,
        }
    ]

    class Cursor:
        def __init__(self):
            self.query_index = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _query, _params=None):
            self.query_index += 1

        def fetchone(self):
            assert self.query_index == 1
            return privilege_row

        def fetchall(self):
            if self.query_index == 2:
                return login_memberships
            assert self.query_index == 3
            return capability_graph

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_connect(_service):
        yield Connection()

    monkeypatch.setattr(module, "connect", fake_connect)

    result = module._permission_status(
        "runtime-service",
        "runtime",
        {"migration_login", "theme_research_owner"},
    )

    assert result["status"] == "error"
    assert result["session_user"] == "runtime_login"
    assert "theme_research_report_indexer:member" in result["role_membership"][
        "violations"
    ]


def test_permission_probe_is_read_only_and_checks_function_and_table_privileges():
    source = (
        REPO_ROOT / "deploy/check_theme_research_report_runtime.py"
    ).read_text(encoding="utf-8")

    assert "has_function_privilege" in source
    assert "has_table_privilege" in source
    assert "pg_has_role" in source
    assert "pg_auth_members" in source
    assert "register_theme_research_report_pending" in source
    assert "review_theme_research_report_version" in source
    assert "INSERT INTO" not in source
    assert "UPDATE research." not in source
    assert "DELETE FROM" not in source
