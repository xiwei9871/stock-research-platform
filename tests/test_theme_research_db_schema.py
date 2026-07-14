from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from stock_research import theme_research_db_schema as schema
from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research import cli as stock_research_cli


REQUIRED_TABLES = {
    "theme_research_schema_migration",
    "theme_research_store_state",
    "theme_research_change_set",
    "theme_research_theme",
    "theme_research_node",
    "theme_research_source_item",
    "theme_research_theme_source",
    "theme_research_content_claim",
    "theme_research_claim_source",
    "theme_research_claim_node",
    "theme_research_value_assessment",
    "theme_research_assessment_evidence",
    "theme_research_company_mapping",
    "theme_research_mapping_evidence_item",
    "theme_research_company_mapping_evidence",
    "theme_research_review_event",
    "theme_research_object_revision",
    "theme_research_import_run",
    "theme_research_snapshot",
}

LEGACY_DDL_SHA256 = "1acce2a856b94b6479c7e08623779e230124fc54fb78fba3358e9cfe4cc882ce"
LEGACY_CATALOG_SHA256 = "296c75c60f86b1606306d9599c04c4e25a5f06480184ec78f3cefbbf48a409b7"
LEGACY_MISSING = {
    "catalog:sha256",
    "constraint:ck_theme_research_claim_type",
    "constraint:ck_theme_research_theme_type",
}
PREDECESSOR_DDL_SHA256 = "ae542e49fb740ffb2e54d239c487c58b25f8d47178353161bc3ef58dba3948f6"
PREDECESSOR_CATALOG_SHA256 = "5b21137a399c3304cb4550f7e04ce06c048fe7e37754b3cd1fc316add34b0451"
PREDECESSOR_MISSING = set()


class _Cursor:
    def __init__(self, row=None):
        self.calls = []
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row=None):
        self.cursor_obj = _Cursor(row=row)

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


def test_schema_contains_all_phase9_tables() -> None:
    sql = schema.THEME_RESEARCH_SCHEMA_SQL

    for table in REQUIRED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS research.{table}" in sql


def test_schema_contains_production_constraints_and_triggers() -> None:
    sql = schema.THEME_RESEARCH_SCHEMA_SQL

    assert "value_capture_score BETWEEN 0 AND 5" in sql
    assert "new_energy_storage" in sql
    assert "catalyst" in sql
    assert "risk" in sql
    assert "confidence BETWEEN 0 AND 1" in sql
    assert "reliability_level <> 'S4' OR review_status <> 'accepted'" in sql
    assert "node_review_status <> 'reviewed' OR evidence_strength >= 3" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_reviewed_claim" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_source_claim_validity" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_claim_source_validity" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_claim_node_theme" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_company_node_theme" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_node_relationships" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_theme_children_active" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_assessment_evidence" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_mapping_evidence" in sql
    assert "CREATE TRIGGER trg_theme_research_theme_version_monotonic" in sql
    assert "CREATE TRIGGER trg_theme_research_change_set_immutable" in sql
    assert "CREATE OR REPLACE FUNCTION research.theme_research_reject_mutation" in sql
    assert "theme_research_snapshot is append-only" in sql
    assert "theme_research_review_event is append-only" in sql
    assert "theme_research_object_revision is append-only" in sql
    assert "BEFORE TRUNCATE ON research.theme_research_snapshot" in sql
    assert "BEFORE TRUNCATE ON research.theme_research_review_event" in sql
    assert "BEFORE TRUNCATE ON research.theme_research_object_revision" in sql
    assert "WHERE idempotency_key <> ''" in sql


def test_schema_rebuilds_only_exact_known_legacy_theme_and_claim_type_checks() -> None:
    sql = schema.THEME_RESEARCH_SCHEMA_SQL

    assert "LIKE '%theme_type%'" not in sql
    assert "LIKE '%claim_type%'" not in sql
    assert "theme_research_theme_theme_type_check" in sql
    assert "theme_research_content_claim_claim_type_check" in sql
    assert "pg_get_constraintdef(oid, true) =" in sql
    assert "'new_energy_storage'" in sql
    assert "'catalyst'" in sql
    assert "'risk'" in sql


def test_known_legacy_schema_contracts_bind_exact_hashes_and_missing_sets() -> None:
    contracts = {
        (
            contract.version_label,
            contract.ddl_sha256,
            contract.catalog_sha256,
            contract.allowed_missing,
        )
        for contract in schema.KNOWN_LEGACY_SCHEMA_CONTRACTS
    }

    assert contracts == {
        (
            "94e1de3",
            LEGACY_DDL_SHA256,
            LEGACY_CATALOG_SHA256,
            frozenset(LEGACY_MISSING),
        ),
        (
            "9ad6360/01fae25",
            PREDECESSOR_DDL_SHA256,
            PREDECESSOR_CATALOG_SHA256,
            frozenset(PREDECESSOR_MISSING),
        ),
    }
    assert not hasattr(schema, "KNOWN_LEGACY_DDL_SHA256")
    assert not hasattr(schema, "KNOWN_LEGACY_CATALOG_SHA256")
    assert not hasattr(schema, "KNOWN_LEGACY_MISSING")


def test_schema_is_idempotent_and_non_destructive() -> None:
    sql = schema.THEME_RESEARCH_SCHEMA_SQL.upper()

    assert "DROP TABLE" not in sql
    assert "TRUNCATE TABLE" not in sql
    assert "CREATE TABLE RESEARCH." not in sql
    assert "CREATE INDEX IDX_" not in sql
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql


def test_business_schema_does_not_create_or_alter_roles() -> None:
    sql = schema.THEME_RESEARCH_SCHEMA_SQL.upper()

    assert "CREATE ROLE" not in sql
    assert "ALTER ROLE" not in sql
    assert "GRANT THEME_RESEARCH_OWNER TO" not in sql


def test_ddl_sha256_is_stable() -> None:
    first = schema.ddl_sha256()
    second = schema.ddl_sha256()

    assert first == second
    assert len(first) == 64


def test_row_value_supports_mapping_and_tuple_rows() -> None:
    assert schema._row_value({"relation_name": "research.example"}, "relation_name") == "research.example"
    assert schema._row_value(("research.example",), "relation_name") == "research.example"
    assert schema._row_value(None, "relation_name") is None


def test_version_trigger_uses_json_for_optional_theme_version() -> None:
    sql = schema.THEME_RESEARCH_SCHEMA_SQL

    assert "new_record jsonb := to_jsonb(NEW)" in sql
    assert "old_record jsonb := to_jsonb(OLD)" in sql
    assert "NEW.theme_version" not in sql


def test_apply_schema_executes_ddl_and_records_version(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))
    monkeypatch.setattr(schema, "_load_applied_migration", lambda cur: None)
    inspections = iter(
        [
            {"status": "missing", "existing_count": 0, "missing": []},
            {"status": "current", "existing_count": len(REQUIRED_TABLES), "missing": []},
        ]
    )
    monkeypatch.setattr(schema, "inspect_theme_research_schema", lambda cur: next(inspections))

    result = schema.apply_theme_research_schema(
        service="test",
        actor_user_id="admin-1",
        actor_role="admin",
    )

    assert result == {
        "status": "ok",
        "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
        "ddl_sha256": schema.ddl_sha256(),
    }
    lock_sql, lock_params = connection.cursor_obj.calls[0]
    assert "pg_advisory_xact_lock" in lock_sql
    assert lock_params == (schema.THEME_RESEARCH_SCHEMA_MIGRATION_LOCK_KEY,)
    assert connection.cursor_obj.calls[1][0] == schema.THEME_RESEARCH_SCHEMA_SQL
    migration_sql, migration_params = connection.cursor_obj.calls[2]
    assert "INSERT INTO research.theme_research_schema_migration" in migration_sql
    assert migration_params[0] == schema.THEME_RESEARCH_DB_SCHEMA_VERSION
    assert migration_params[2] == schema.ddl_sha256()


def test_schema_status_reports_current_version(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))
    monkeypatch.setattr(
        schema,
        "_load_applied_migration",
        lambda cur: {
            "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": schema.ddl_sha256(),
            "applied_at": "2026-07-11T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        schema,
        "inspect_theme_research_schema",
        lambda cur: {"status": "current", "existing_count": len(REQUIRED_TABLES), "missing": []},
    )

    result = schema.theme_research_schema_status(service="test")

    assert result["status"] == "current"
    assert result["schema_version"] == schema.THEME_RESEARCH_DB_SCHEMA_VERSION
    assert result["ddl_matches"] is True


def test_schema_status_reports_missing_schema(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))
    monkeypatch.setattr(schema, "_load_applied_migration", lambda cur: None)
    monkeypatch.setattr(
        schema,
        "inspect_theme_research_schema",
        lambda cur: {"status": "missing", "existing_count": 0, "missing": sorted(REQUIRED_TABLES)},
    )

    result = schema.theme_research_schema_status(service="test")

    assert result == {
        "status": "missing",
        "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
        "ddl_sha256": schema.ddl_sha256(),
        "ddl_matches": False,
    }


def test_schema_cli_apply_and_status(monkeypatch, capsys) -> None:
    monkeypatch.setenv("THEME_RESEARCH_ADMIN_PASSWORD", "secret")
    monkeypatch.setattr(
        schema,
        "authenticate_user",
        lambda username, password, service: SimpleNamespace(user_id="admin-1", role="admin"),
    )
    monkeypatch.setattr(
        schema,
        "apply_theme_research_schema",
        lambda service, actor_user_id, actor_role: {
            "status": "ok",
            "schema_version": "v1",
            "ddl_sha256": "abc",
        },
    )
    assert (
        schema.cli(
            [
                "--migration-service",
                "test",
                "--auth-service",
                "auth-test",
                "apply-schema",
                "--admin-username",
                "admin",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "ok"

    monkeypatch.setattr(
        schema,
        "theme_research_schema_status",
        lambda service: {"status": "current", "schema_version": "v1", "ddl_matches": True},
    )
    assert schema.cli(["--migration-service", "test", "schema-status"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "current"


def test_shared_cli_delegates_theme_research_db(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        stock_research_cli,
        "run_theme_research_db_cli",
        lambda argv: captured.append(argv) or 0,
    )

    result = stock_research_cli.main_for_args(
        ["theme-research-db", "--service", "test", "schema-status"]
    )

    assert result == 0
    assert captured == [["--service", "test", "schema-status"]]


def test_schema_cli_import_dry_run(monkeypatch, capsys) -> None:
    package = SimpleNamespace(package_sha256="package-1")
    monkeypatch.setattr(
        "stock_research.theme_research_import.normalize_artifact_package",
        lambda **kwargs: package,
    )
    monkeypatch.setattr(
        "stock_research.theme_research_store.dry_run_package",
        lambda value, replace_theme, service: {
            "status": "dry_run",
            "package_sha256": value.package_sha256,
        },
    )

    assert schema.cli(["--runtime-service", "test", "import", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"


def test_schema_cli_import_execute_requires_generation(capsys) -> None:
    assert (
        schema.cli(
            [
                "--runtime-service",
                "test",
                "import",
                "--execute",
                "--admin-username",
                "admin",
                "--idempotency-key",
                "key-1",
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().err)
    assert payload["error_code"] == "THEME_RESEARCH_IMPORT_REQUEST_INVALID"


def test_apply_schema_acquires_lock_before_loading_migration_or_inspecting(monkeypatch) -> None:
    connection = _Connection()
    events = []
    execute = connection.cursor_obj.execute

    def record_execute(sql, params=None):
        events.append(("execute", sql, params))
        execute(sql, params)

    connection.cursor_obj.execute = record_execute
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))

    def load_migration(cur):
        events.append(("load_migration",))
        return {
            "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": schema.ddl_sha256(),
            "applied_at": "2026-07-11T00:00:00+00:00",
        }

    def inspect(cur):
        events.append(("inspect",))
        return {
            "status": "current",
            "existing_count": len(REQUIRED_TABLES),
            "missing": [],
            "catalog_sha256": schema.EXPECTED_THEME_RESEARCH_CATALOG_SHA256,
        }

    monkeypatch.setattr(schema, "_load_applied_migration", load_migration)
    monkeypatch.setattr(schema, "inspect_theme_research_schema", inspect)

    schema.apply_theme_research_schema(
        service="test",
        actor_user_id="admin-1",
        actor_role="admin",
    )

    assert events[0] == (
        "execute",
        "SELECT pg_advisory_xact_lock(%s)",
        (schema.THEME_RESEARCH_SCHEMA_MIGRATION_LOCK_KEY,),
    )
    assert events[1:] == [("load_migration",), ("inspect",)]


def test_apply_schema_migrates_only_known_legacy_contract(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))
    monkeypatch.setattr(
        schema,
        "_load_applied_migration",
        lambda cur: {
            "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": LEGACY_DDL_SHA256,
            "applied_at": "2026-07-11T00:00:00+00:00",
        },
    )
    inspections = iter(
        [
            {
                "status": "drifted",
                "existing_count": len(REQUIRED_TABLES),
                "missing": sorted(LEGACY_MISSING),
                "catalog_sha256": LEGACY_CATALOG_SHA256,
            },
            {
                "status": "current",
                "existing_count": len(REQUIRED_TABLES),
                "missing": [],
                "catalog_sha256": schema.EXPECTED_THEME_RESEARCH_CATALOG_SHA256,
            },
        ]
    )
    monkeypatch.setattr(schema, "inspect_theme_research_schema", lambda cur: next(inspections))

    result = schema.apply_theme_research_schema(
        service="test",
        actor_user_id="admin-1",
        actor_role="admin",
    )

    assert result == {
        "status": "ok",
        "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
        "ddl_sha256": schema.ddl_sha256(),
    }
    assert "pg_advisory_xact_lock" in connection.cursor_obj.calls[0][0]
    assert connection.cursor_obj.calls[1][0] == schema.THEME_RESEARCH_SCHEMA_SQL
    migration_sql, migration_params = connection.cursor_obj.calls[2]
    assert "ON CONFLICT (schema_version) DO UPDATE" in migration_sql
    assert migration_params[0] == schema.THEME_RESEARCH_DB_SCHEMA_VERSION
    assert migration_params[2] == schema.ddl_sha256()


def test_apply_schema_migrates_immediate_predecessor_contract(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))
    monkeypatch.setattr(
        schema,
        "_load_applied_migration",
        lambda cur: {
            "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": PREDECESSOR_DDL_SHA256,
            "applied_at": "2026-07-14T00:00:00+00:00",
        },
    )
    inspections = iter(
        [
            {
                "status": "current",
                "existing_count": len(REQUIRED_TABLES),
                "missing": [],
                "catalog_sha256": PREDECESSOR_CATALOG_SHA256,
            },
            {
                "status": "current",
                "existing_count": len(REQUIRED_TABLES),
                "missing": [],
                "catalog_sha256": schema.EXPECTED_THEME_RESEARCH_CATALOG_SHA256,
            },
        ]
    )
    monkeypatch.setattr(schema, "inspect_theme_research_schema", lambda cur: next(inspections))

    result = schema.apply_theme_research_schema(
        service="test",
        actor_user_id="admin-1",
        actor_role="admin",
    )

    assert result["ddl_sha256"] == schema.ddl_sha256()
    assert connection.cursor_obj.calls[1][0] == schema.THEME_RESEARCH_SCHEMA_SQL
    migration_sql, migration_params = connection.cursor_obj.calls[2]
    assert "ON CONFLICT (schema_version) DO UPDATE" in migration_sql
    assert migration_params[2] == schema.ddl_sha256()


def test_apply_schema_rejects_partial_schema_even_with_migration(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))
    monkeypatch.setattr(
        schema,
        "_load_applied_migration",
        lambda cur: {
            "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": LEGACY_DDL_SHA256,
            "applied_at": "2026-07-11T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        schema,
        "inspect_theme_research_schema",
        lambda cur: {
            "status": "drifted",
            "existing_count": len(REQUIRED_TABLES) - 1,
            "missing": ["table:theme_research_snapshot"],
            "catalog_sha256": "",
        },
    )

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        schema.apply_theme_research_schema(
            service="test",
            actor_user_id="admin-1",
            actor_role="admin",
        )

    assert exc_info.value.code == "THEME_RESEARCH_PARTIAL_SCHEMA"
    assert len(connection.cursor_obj.calls) == 1
    assert "pg_advisory_xact_lock" in connection.cursor_obj.calls[0][0]


@pytest.mark.parametrize(
    ("applied_ddl_sha256", "catalog_sha256", "missing"),
    [
        (schema.ddl_sha256(), "f" * 64, ["catalog:sha256"]),
        (LEGACY_DDL_SHA256, PREDECESSOR_CATALOG_SHA256, []),
        (PREDECESSOR_DDL_SHA256, LEGACY_CATALOG_SHA256, sorted(LEGACY_MISSING)),
        (LEGACY_DDL_SHA256, "f" * 64, sorted(LEGACY_MISSING)),
        (
            LEGACY_DDL_SHA256,
            LEGACY_CATALOG_SHA256,
            sorted(LEGACY_MISSING | {"constraint:custom_theme_type_guard"}),
        ),
        ("e" * 64, LEGACY_CATALOG_SHA256, sorted(LEGACY_MISSING)),
    ],
)
def test_apply_schema_rejects_unknown_full_schema_drift_without_writes(
    monkeypatch,
    applied_ddl_sha256,
    catalog_sha256,
    missing,
) -> None:
    connection = _Connection()
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))
    monkeypatch.setattr(
        schema,
        "_load_applied_migration",
        lambda cur: {
            "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": applied_ddl_sha256,
            "applied_at": "2026-07-11T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        schema,
        "inspect_theme_research_schema",
        lambda cur: {
            "status": "drifted",
            "existing_count": len(REQUIRED_TABLES),
            "missing": missing,
            "catalog_sha256": catalog_sha256,
        },
    )

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        schema.apply_theme_research_schema(
            service="test",
            actor_user_id="admin-1",
            actor_role="admin",
        )

    assert exc_info.value.code == "THEME_RESEARCH_SCHEMA_DRIFT"
    assert len(connection.cursor_obj.calls) == 1
    assert "pg_advisory_xact_lock" in connection.cursor_obj.calls[0][0]


def test_apply_schema_rejects_partial_unversioned_schema(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))
    monkeypatch.setattr(schema, "_load_applied_migration", lambda cur: None)
    monkeypatch.setattr(
        schema,
        "inspect_theme_research_schema",
        lambda cur: {
            "status": "drifted",
            "existing_count": 1,
            "missing": ["table:theme_research_source_item"],
        },
    )

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        schema.apply_theme_research_schema(
            service="test",
            actor_user_id="admin-1",
            actor_role="admin",
        )

    assert exc_info.value.code == "THEME_RESEARCH_PARTIAL_SCHEMA"


def test_schema_status_does_not_mask_connection_errors(monkeypatch) -> None:
    def fail_connect(service):
        raise RuntimeError("authentication failed")

    monkeypatch.setattr(schema, "connect", fail_connect)

    with pytest.raises(RuntimeError, match="authentication failed"):
        schema.theme_research_schema_status(service="missing")


def test_apply_schema_requires_admin_role(monkeypatch) -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        schema.apply_theme_research_schema(
            service="test",
            actor_user_id="user-1",
            actor_role="user",
        )

    assert exc_info.value.code == "THEME_RESEARCH_ADMIN_REQUIRED"
