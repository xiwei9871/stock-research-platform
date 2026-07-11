from __future__ import annotations

import json

from stock_research import theme_research_db_schema as schema
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
    "theme_research_company_mapping_evidence",
    "theme_research_review_event",
    "theme_research_object_revision",
    "theme_research_import_run",
    "theme_research_snapshot",
}


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
    assert "confidence BETWEEN 0 AND 1" in sql
    assert "reliability_level <> 'S4' OR review_status <> 'accepted'" in sql
    assert "node_review_status <> 'reviewed' OR evidence_strength >= 3" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_reviewed_claim" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_claim_node_theme" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_theme_research_company_node_theme" in sql
    assert "CREATE OR REPLACE FUNCTION research.theme_research_reject_mutation" in sql
    assert "theme_research_snapshot is append-only" in sql
    assert "theme_research_review_event is append-only" in sql
    assert "theme_research_object_revision is append-only" in sql
    assert "WHERE idempotency_key <> ''" in sql


def test_schema_is_idempotent_and_non_destructive() -> None:
    sql = schema.THEME_RESEARCH_SCHEMA_SQL.upper()

    assert "DROP TABLE" not in sql
    assert "TRUNCATE" not in sql
    assert "CREATE TABLE RESEARCH." not in sql
    assert "CREATE INDEX IDX_" not in sql
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql


def test_ddl_sha256_is_stable() -> None:
    first = schema.ddl_sha256()
    second = schema.ddl_sha256()

    assert first == second
    assert len(first) == 64


def test_apply_schema_executes_ddl_and_records_version(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))

    result = schema.apply_theme_research_schema(service="test")

    assert result == {
        "status": "ok",
        "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
        "ddl_sha256": schema.ddl_sha256(),
    }
    assert connection.cursor_obj.calls[0][0] == schema.THEME_RESEARCH_SCHEMA_SQL
    migration_sql, migration_params = connection.cursor_obj.calls[1]
    assert "INSERT INTO research.theme_research_schema_migration" in migration_sql
    assert migration_params[0] == schema.THEME_RESEARCH_DB_SCHEMA_VERSION
    assert migration_params[2] == schema.ddl_sha256()


def test_schema_status_reports_current_version(monkeypatch) -> None:
    connection = _Connection(
        row={
            "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": schema.ddl_sha256(),
            "applied_at": "2026-07-11T00:00:00+00:00",
        }
    )
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))

    result = schema.theme_research_schema_status(service="test")

    assert result["status"] == "current"
    assert result["schema_version"] == schema.THEME_RESEARCH_DB_SCHEMA_VERSION
    assert result["ddl_matches"] is True


def test_schema_status_reports_missing_schema(monkeypatch) -> None:
    connection = _Connection(row=None)
    monkeypatch.setattr(schema, "connect", lambda service: _Context(connection))

    result = schema.theme_research_schema_status(service="test")

    assert result == {
        "status": "missing",
        "schema_version": schema.THEME_RESEARCH_DB_SCHEMA_VERSION,
        "ddl_sha256": schema.ddl_sha256(),
        "ddl_matches": False,
    }


def test_schema_cli_apply_and_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        schema,
        "apply_theme_research_schema",
        lambda service, applied_by="system": {
            "status": "ok",
            "schema_version": "v1",
            "ddl_sha256": "abc",
        },
    )
    assert schema.cli(["--service", "test", "apply-schema"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"

    monkeypatch.setattr(
        schema,
        "theme_research_schema_status",
        lambda service: {"status": "current", "schema_version": "v1", "ddl_matches": True},
    )
    assert schema.cli(["--service", "test", "schema-status"]) == 0
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
