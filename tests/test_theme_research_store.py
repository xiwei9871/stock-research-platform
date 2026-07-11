from __future__ import annotations

import hashlib
import json

import pytest

from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_import import normalize_artifact_package
from stock_research.theme_research_store import (
    _assert_runtime_connection,
    create_snapshot,
    package_for_theme,
    rollback_theme,
    validate_bootstrap_request,
)


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params) -> None:
        self.calls.append((sql, params))


class _RoleCursor:
    def __init__(self, row) -> None:
        self.row = row

    def execute(self, sql) -> None:
        pass

    def fetchone(self):
        return self.row


def test_validate_bootstrap_request_requires_actor_and_idempotency_key() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        validate_bootstrap_request(
            actor_user_id="",
            expected_generation=0,
            idempotency_key="",
        )

    assert exc_info.value.code == "THEME_RESEARCH_IMPORT_REQUEST_INVALID"


def test_package_for_theme_keeps_only_owned_rows() -> None:
    package = normalize_artifact_package()

    selected = package_for_theme(package, "ai_power_value_capture_v1")

    assert [row["theme_id"] for row in selected.themes] == ["ai_power_value_capture_v1"]
    assert all(row["theme_id"] == "ai_power_value_capture_v1" for row in selected.nodes)
    assert all(row["theme_id"] == "ai_power_value_capture_v1" for row in selected.claims)
    assert all(row["theme_id"] == "ai_power_value_capture_v1" for row in selected.company_mappings)
    assert selected.package_sha256 != package.package_sha256


def test_package_for_theme_rejects_unknown_theme() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        package_for_theme(normalize_artifact_package(), "missing-theme")

    assert exc_info.value.code == "THEME_RESEARCH_THEME_NOT_FOUND"


def test_create_snapshot_hashes_canonical_payload() -> None:
    cursor = _Cursor()
    payload = {"theme": {"theme_id": "theme-1"}, "nodes": []}

    snapshot_id = create_snapshot(
        cursor,
        theme_id="theme-1",
        theme_version=2,
        snapshot_type="post_change",
        payload=payload,
        change_set_id="change-1",
        actor_user_id="admin-1",
        artifact_version="theme_decomposition_v1_5",
    )

    assert snapshot_id.startswith("snapshot-")
    sql, params = cursor.calls[0]
    expected_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert "INSERT INTO research.theme_research_snapshot" in sql
    assert params[5] == hashlib.sha256(expected_json.encode("utf-8")).hexdigest()


def test_runtime_connection_rejects_superuser_or_owner_member() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        _assert_runtime_connection(
            _RoleCursor(
                {
                    "role_name": "postgres",
                    "rolsuper": True,
                    "rolcreaterole": True,
                    "runtime_member": False,
                    "owner_member": True,
                }
            )
        )

    assert exc_info.value.code == "THEME_RESEARCH_UNSAFE_DATABASE_ROLE"


def test_runtime_connection_accepts_constrained_runtime_login() -> None:
    _assert_runtime_connection(
        _RoleCursor(
            {
                "role_name": "theme_research_app",
                "rolsuper": False,
                "rolcreaterole": False,
                "runtime_member": True,
                "owner_member": False,
            }
        )
    )


def test_non_admin_cannot_rollback() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        rollback_theme(
            theme_id="theme-1",
            snapshot_id="snapshot-1",
            expected_theme_version=1,
            actor_user_id="user-1",
            actor_role="user",
            comment="Unauthorized rollback.",
            idempotency_key="rollback-denied",
        )

    assert exc_info.value.code == "THEME_RESEARCH_ADMIN_REQUIRED"
