from __future__ import annotations

import json
import os
from contextlib import contextmanager

import psycopg
import pytest

from stock_research.config import Settings


TEST_SERVICE = os.getenv("THEME_RESEARCH_POSTGRES_TEST_SERVICE", "")
TEST_RUNTIME_SERVICE = os.getenv("THEME_RESEARCH_POSTGRES_TEST_RUNTIME_SERVICE", "")
POSTGRES_ENABLED = (
    os.getenv("THEME_RESEARCH_POSTGRES_TEST") == "1" and bool(TEST_SERVICE)
)


def test_theme_research_report_settings_parse_environment(monkeypatch, tmp_path) -> None:
    report_root = tmp_path / "generated-theme-reports"
    monkeypatch.setenv("THEME_RESEARCH_REPORT_ROOT", str(report_root))
    monkeypatch.setenv("THEME_RESEARCH_REPORT_SCAN_INTERVAL_SECONDS", "17")
    monkeypatch.setenv("THEME_RESEARCH_REPORT_MAX_MANIFEST_BYTES", "1234")
    monkeypatch.setenv("THEME_RESEARCH_REPORT_MAX_MARKDOWN_BYTES", "5678")
    monkeypatch.setenv("THEME_RESEARCH_REPORT_MAX_PDF_BYTES", "9012")

    settings = Settings()

    assert settings.theme_research_report_root == report_root
    assert settings.theme_research_report_scan_interval_seconds == 17
    assert settings.theme_research_report_max_manifest_bytes == 1234
    assert settings.theme_research_report_max_markdown_bytes == 5678
    assert settings.theme_research_report_max_pdf_bytes == 9012


def test_theme_research_report_settings_have_bounded_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_RESEARCH_REPORTS_ROOT", str(tmp_path / "reports"))
    for name in (
        "THEME_RESEARCH_REPORT_ROOT",
        "THEME_RESEARCH_REPORT_SCAN_INTERVAL_SECONDS",
        "THEME_RESEARCH_REPORT_MAX_MANIFEST_BYTES",
        "THEME_RESEARCH_REPORT_MAX_MARKDOWN_BYTES",
        "THEME_RESEARCH_REPORT_MAX_PDF_BYTES",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.theme_research_report_root == settings.reports_root / "theme-research"
    assert settings.theme_research_report_scan_interval_seconds == 60
    assert settings.theme_research_report_max_manifest_bytes == 64 * 1024
    assert settings.theme_research_report_max_markdown_bytes == 10 * 1024 * 1024
    assert settings.theme_research_report_max_pdf_bytes == 50 * 1024 * 1024


def test_theme_research_report_root_follows_instance_reports_root(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("THEME_RESEARCH_REPORT_ROOT", raising=False)
    custom_reports_root = tmp_path / "custom-reports"

    settings = Settings(reports_root=custom_reports_root)

    assert settings.theme_research_report_root == custom_reports_root / "theme-research"


@pytest.mark.parametrize(
    ("env_name", "field_name"),
    [
        ("THEME_RESEARCH_REPORT_SCAN_INTERVAL_SECONDS", "theme_research_report_scan_interval_seconds"),
        ("THEME_RESEARCH_REPORT_MAX_MANIFEST_BYTES", "theme_research_report_max_manifest_bytes"),
        ("THEME_RESEARCH_REPORT_MAX_MARKDOWN_BYTES", "theme_research_report_max_markdown_bytes"),
        ("THEME_RESEARCH_REPORT_MAX_PDF_BYTES", "theme_research_report_max_pdf_bytes"),
    ],
)
@pytest.mark.parametrize("invalid_value", ["0", "-1"])
def test_theme_research_report_settings_reject_nonpositive_limits(
    monkeypatch,
    env_name,
    field_name,
    invalid_value,
) -> None:
    monkeypatch.setenv(env_name, invalid_value)

    with pytest.raises(ValueError, match=rf"{env_name}.*{field_name}.*greater than zero"):
        Settings()


def test_report_schema_ddl_contains_required_constraints_and_indexes() -> None:
    from stock_research import theme_research_report_schema as schema

    sql = schema.THEME_RESEARCH_REPORT_SCHEMA_SQL

    assert "CREATE TABLE IF NOT EXISTS research.theme_research_report_version" in sql
    assert "REFERENCES research.theme_research_theme(theme_id)" in sql
    assert "\n    version text NOT NULL," in sql
    assert "UNIQUE (theme_id, version)" in sql
    assert "pending_review" in sql
    assert "published" in sql
    assert "rejected" in sql
    assert "archived" in sql
    assert "pdf_relative_path IS NULL AND pdf_sha256 IS NULL" in sql
    assert "pdf_relative_path IS NOT NULL AND pdf_sha256 IS NOT NULL" in sql
    assert "indexed_at timestamptz NOT NULL DEFAULT now()" in sql
    assert "rejection_reason text NOT NULL DEFAULT ''" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_research_report_one_published" in sql
    assert "WHERE status = 'published'" in sql
    assert "CREATE TABLE IF NOT EXISTS research.theme_research_report_review_event" in sql
    assert "REFERENCES identity.user_account(user_id)" in sql
    assert "actor_user_id text NOT NULL" in sql
    assert "idempotency_key text NOT NULL DEFAULT ''" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_research_report_review_actor_idempotency" in sql
    assert "idempotency_key <> ''" in sql
    assert "REVOKE ALL ON TABLE research.theme_research_report_version FROM PUBLIC" in sql
    assert "REVOKE ALL ON TABLE research.theme_research_report_review_event FROM PUBLIC" in sql
    assert "ALTER TABLE research.theme_research_report_version OWNER TO theme_research_owner" in sql
    assert "GRANT SELECT, INSERT ON research.theme_research_report_version" in sql
    assert "GRANT UPDATE (" in sql
    assert "rejection_reason" in sql
    assert "GRANT SELECT, INSERT ON research.theme_research_report_review_event" in sql
    assert "TO theme_research_runtime" in sql


def test_apply_report_schema_executes_ddl_with_requested_service(monkeypatch) -> None:
    from stock_research import theme_research_report_schema as schema

    calls: list[tuple[str, object]] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql):
            calls.append(("execute", sql))

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def connected(service):
        calls.append(("service", service))
        yield Connection()
        calls.append(("commit", service))

    monkeypatch.setattr(schema, "connect", connected)
    inspections = iter(
        [
            {"status": "missing", "missing": []},
            {"status": "current", "missing": []},
        ]
    )
    monkeypatch.setattr(
        schema,
        "inspect_theme_research_report_schema",
        lambda cursor: next(inspections),
    )

    schema.apply_theme_research_report_schema(service="test_service")

    assert calls == [
        ("service", "test_service"),
        ("execute", schema.THEME_RESEARCH_REPORT_MIGRATION_LOCK_SQL),
        ("execute", schema.THEME_RESEARCH_REPORT_SCHEMA_SQL),
        ("commit", "test_service"),
    ]


def test_apply_report_schema_rejects_existing_drift(monkeypatch) -> None:
    from stock_research import theme_research_report_schema as schema

    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql):
            calls.append(sql)

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def connected(service):
        yield Connection()

    monkeypatch.setattr(schema, "connect", connected)
    monkeypatch.setattr(
        schema,
        "inspect_theme_research_report_schema",
        lambda cursor: {
            "status": "drifted",
            "missing": ["column:theme_research_report_version.title"],
        },
    )

    with pytest.raises(schema.ThemeResearchReportSchemaDriftError, match="column:.*title"):
        schema.apply_theme_research_report_schema(service="test_service")

    assert calls == [schema.THEME_RESEARCH_REPORT_MIGRATION_LOCK_SQL]


def test_report_schema_inspection_requires_owner_and_runtime_roles() -> None:
    from stock_research import theme_research_report_schema as schema

    class Cursor:
        sql = ""

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchall(self):
            if "c.relkind IN ('r', 'p')" in self.sql and "a.attname" not in self.sql:
                return [{"table_name": table_name} for table_name in schema._EXPECTED_COLUMNS]
            if "JOIN pg_attribute" in self.sql:
                return [
                    {
                        "table_name": table_name,
                        "column_name": column_name,
                        "data_type": definition[0],
                        "not_null": definition[1],
                        "default_value": definition[2],
                    }
                    for table_name, columns in schema._EXPECTED_COLUMNS.items()
                    for column_name, definition in columns.items()
                ]
            if "FROM pg_constraint" in self.sql:
                return [
                    {"conname": name, "definition": definition}
                    for name, definition in schema._EXPECTED_CONSTRAINT_DEFINITIONS.items()
                ]
            if "FROM pg_indexes" in self.sql:
                return [
                    {"indexname": name, "indexdef": definition}
                    for name, definition in schema._EXPECTED_INDEX_DEFINITIONS.items()
                ]
            if "SELECT rolname FROM pg_roles" in self.sql:
                return []
            if "pg_get_userbyid" in self.sql:
                return [
                    {
                        "table_name": table_name,
                        "owner_name": "migration_user",
                        "public_revoked": True,
                    }
                    for table_name in schema._EXPECTED_COLUMNS
                ]
            raise AssertionError(self.sql)

    inspection = schema.inspect_theme_research_report_schema(Cursor())

    assert inspection == {
        "status": "drifted",
        "missing": ["role:theme_research_owner", "role:theme_research_runtime"],
    }


def test_report_schema_cli_apply_outputs_json(monkeypatch, capsys) -> None:
    from stock_research import theme_research_report_schema as schema

    calls = []
    monkeypatch.setattr(
        schema,
        "apply_theme_research_report_schema",
        lambda service: calls.append(service),
    )

    exit_code = schema.cli(["--apply", "--service", "test_service"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls == ["test_service"]
    assert payload == {
        "schema_version": schema.THEME_RESEARCH_REPORT_SCHEMA_VERSION,
        "service": "test_service",
        "status": "ok",
    }


def test_report_schema_cli_requires_apply() -> None:
    from stock_research import theme_research_report_schema as schema

    with pytest.raises(SystemExit) as exc_info:
        schema.cli([])

    assert exc_info.value.code == 2


@pytest.fixture
def postgres_conn():
    if not POSTGRES_ENABLED:
        pytest.skip("set THEME_RESEARCH_POSTGRES_TEST=1 and a dedicated test service")

    from stock_research.dashboard.auth_schema import DASHBOARD_AUTH_SCHEMA_SQL
    from stock_research.theme_research_db_schema import THEME_RESEARCH_SCHEMA_SQL
    from stock_research.theme_research_report_schema import (
        apply_theme_research_report_schema,
    )

    bootstrap = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        database_name = bootstrap.execute("SELECT current_database()").fetchone()[0]
        if not database_name.endswith("_test"):
            pytest.fail(f"refusing to run integration tests against {database_name}")
        bootstrap.execute(DASHBOARD_AUTH_SCHEMA_SQL)
        bootstrap.execute(THEME_RESEARCH_SCHEMA_SQL)
        bootstrap.execute(
            "DROP TABLE IF EXISTS research.theme_research_report_review_event CASCADE"
        )
        bootstrap.execute(
            "DROP TABLE IF EXISTS research.theme_research_report_version CASCADE"
        )
        bootstrap.commit()
    finally:
        bootstrap.close()

    apply_theme_research_report_schema(service=TEST_SERVICE)
    apply_theme_research_report_schema(service=TEST_SERVICE)

    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _insert_theme(postgres_conn, theme_id: str) -> None:
    postgres_conn.execute(
        """
        INSERT INTO research.theme_research_theme (
            theme_id, theme_name, theme_type, summary, status, created_from,
            last_updated, content_sha256, created_by, updated_by
        ) VALUES (%s, %s, 'other', 'test', 'draft', 'manual', '2026-07-31', %s, 'test', 'test')
        ON CONFLICT (theme_id) DO NOTHING
        """,
        (theme_id, theme_id, f"sha-{theme_id}"),
    )


def _insert_user(postgres_conn, user_id: str) -> None:
    postgres_conn.execute(
        """
        INSERT INTO identity.user_account (
            user_id, username, role, password_hash
        ) VALUES (%s, %s, 'admin', 'test')
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, user_id),
    )


def _insert_report(postgres_conn, report_id: str, theme_id: str, version: str, **overrides) -> None:
    values = {
        "report_version_id": report_id,
        "theme_id": theme_id,
        "version": version,
        "title": f"Report {version}",
        "summary": "summary",
        "status": "pending_review",
        "markdown_relative_path": f"{theme_id}/{version}/report.md",
        "markdown_sha256": "a" * 64,
        "pdf_relative_path": None,
        "pdf_sha256": None,
        "manifest_relative_path": f"{theme_id}/{version}/manifest.json",
        "manifest_sha256": "b" * 64,
        "generator_name": "integration-test",
        "generator_version": "1",
    }
    values.update(overrides)
    postgres_conn.execute(
        """
        INSERT INTO research.theme_research_report_version (
            report_version_id, theme_id, version, title, summary, status,
            markdown_relative_path, markdown_sha256, pdf_relative_path, pdf_sha256,
            manifest_relative_path, manifest_sha256, generator_name, generator_version
        ) VALUES (
            %(report_version_id)s, %(theme_id)s, %(version)s, %(title)s, %(summary)s, %(status)s,
            %(markdown_relative_path)s, %(markdown_sha256)s, %(pdf_relative_path)s, %(pdf_sha256)s,
            %(manifest_relative_path)s, %(manifest_sha256)s, %(generator_name)s, %(generator_version)s
        )
        """,
        values,
    )


def test_postgres_apply_creates_report_tables(postgres_conn) -> None:
    relations = {
        row[0]
        for row in postgres_conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'research'
              AND table_name IN (
                'theme_research_report_version',
                'theme_research_report_review_event'
              )
            """
        ).fetchall()
    }

    assert relations == {
        "theme_research_report_version",
        "theme_research_report_review_event",
    }


def test_postgres_report_tables_follow_owner_and_runtime_permissions(postgres_conn) -> None:
    theme_id = "report-runtime-theme"
    user_id = "report-runtime-admin"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, user_id)

    privileges = postgres_conn.execute(
        """
        SELECT
            pg_get_userbyid(version_table.relowner),
            pg_get_userbyid(event_table.relowner),
            has_table_privilege('theme_research_runtime', version_table.oid, 'SELECT'),
            has_table_privilege('theme_research_runtime', version_table.oid, 'INSERT'),
            has_table_privilege('theme_research_runtime', version_table.oid, 'UPDATE'),
            has_table_privilege('theme_research_runtime', version_table.oid, 'DELETE'),
            has_table_privilege('theme_research_runtime', version_table.oid, 'TRUNCATE'),
            has_table_privilege('theme_research_runtime', version_table.oid, 'REFERENCES'),
            has_table_privilege('theme_research_runtime', version_table.oid, 'TRIGGER'),
            has_column_privilege(
                'theme_research_runtime', version_table.oid, 'status', 'UPDATE'
            ),
            has_column_privilege(
                'theme_research_runtime', version_table.oid, 'summary', 'UPDATE'
            ),
            has_table_privilege('theme_research_runtime', event_table.oid, 'SELECT'),
            has_table_privilege('theme_research_runtime', event_table.oid, 'INSERT'),
            has_table_privilege('theme_research_runtime', event_table.oid, 'UPDATE'),
            has_schema_privilege('theme_research_runtime', 'research', 'CREATE'),
            NOT EXISTS (
                SELECT 1 FROM aclexplode(COALESCE(version_table.relacl, acldefault('r', version_table.relowner)))
                WHERE grantee = 0
            ),
            NOT EXISTS (
                SELECT 1 FROM aclexplode(COALESCE(event_table.relacl, acldefault('r', event_table.relowner)))
                WHERE grantee = 0
            )
        FROM pg_class version_table
        JOIN pg_namespace version_namespace ON version_namespace.oid = version_table.relnamespace
        CROSS JOIN pg_class event_table
        JOIN pg_namespace event_namespace ON event_namespace.oid = event_table.relnamespace
        WHERE version_namespace.nspname = 'research'
          AND version_table.relname = 'theme_research_report_version'
          AND event_namespace.nspname = 'research'
          AND event_table.relname = 'theme_research_report_review_event'
        """
    ).fetchone()
    assert privileges == (
        "theme_research_owner",
        "theme_research_owner",
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        True,
        False,
        True,
        True,
        False,
        False,
        True,
        True,
    )

    postgres_conn.execute("SET LOCAL ROLE theme_research_runtime")
    _insert_report(postgres_conn, "runtime-report-version", theme_id, "runtime-v1")
    postgres_conn.execute(
        """
        UPDATE research.theme_research_report_version
        SET status = 'rejected', rejection_reason = 'runtime update'
        WHERE report_version_id = 'runtime-report-version'
        """
    )
    assert postgres_conn.execute(
        """
        SELECT status FROM research.theme_research_report_version
        WHERE report_version_id = 'runtime-report-version'
        """
    ).fetchone()[0] == "rejected"
    postgres_conn.execute("SAVEPOINT runtime_immutable_update")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        postgres_conn.execute(
            """
            UPDATE research.theme_research_report_version
            SET summary = 'forbidden mutation'
            WHERE report_version_id = 'runtime-report-version'
            """
        )
    postgres_conn.execute("ROLLBACK TO SAVEPOINT runtime_immutable_update")
    postgres_conn.execute(
        """
        INSERT INTO research.theme_research_report_review_event (
            event_id, report_version_id, from_status, to_status,
            actor_user_id, idempotency_key
        ) VALUES (
            'runtime-review-event', 'runtime-report-version', 'pending_review',
            'published', %s, 'runtime-review'
        )
        """,
        (user_id,),
    )


def test_postgres_runtime_service_can_write_report_workflow(postgres_conn) -> None:
    if not TEST_RUNTIME_SERVICE:
        pytest.skip("dedicated runtime test service is required")

    theme_id = "report-runtime-service-theme"
    user_id = "report-runtime-service-admin"
    postgres_conn.rollback()
    migration = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        _insert_theme(migration, theme_id)
        _insert_user(migration, user_id)
        migration.commit()
    finally:
        migration.close()

    runtime = psycopg.connect(f"service={TEST_RUNTIME_SERVICE}")
    try:
        database_name = runtime.execute("SELECT current_database()").fetchone()[0]
        if not database_name.endswith("_test"):
            pytest.fail(f"refusing to run integration tests against {database_name}")
        _insert_report(runtime, "runtime-service-report", theme_id, "runtime-service-v1")
        runtime.execute("SAVEPOINT runtime_status_update")
        runtime.execute(
            """
            UPDATE research.theme_research_report_version
            SET status = 'rejected', rejection_reason = 'runtime service update'
            WHERE report_version_id = 'runtime-service-report'
            """
        )
        assert runtime.execute(
            """
            SELECT status FROM research.theme_research_report_version
            WHERE report_version_id = 'runtime-service-report'
            """
        ).fetchone()[0] == "rejected"
        runtime.execute("SAVEPOINT runtime_immutable_update")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute(
                """
                UPDATE research.theme_research_report_version
                SET summary = 'forbidden mutation'
                WHERE report_version_id = 'runtime-service-report'
                """
            )
        runtime.execute("ROLLBACK TO SAVEPOINT runtime_immutable_update")
        runtime.execute(
            """
            INSERT INTO research.theme_research_report_review_event (
                event_id, report_version_id, from_status, to_status,
                actor_user_id, idempotency_key
            ) VALUES (
                'runtime-service-review', 'runtime-service-report',
                'pending_review', 'published', %s, 'runtime-service-review'
            )
            """,
            (user_id,),
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute(
                """
                DELETE FROM research.theme_research_report_version
                WHERE report_version_id = 'runtime-service-report'
                """
            )
    finally:
        runtime.rollback()
        runtime.close()
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "DELETE FROM research.theme_research_theme WHERE theme_id = %s",
                (theme_id,),
            )
            cleanup.execute(
                "DELETE FROM identity.user_account WHERE user_id = %s",
                (user_id,),
            )
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_inspection_detects_unexpected_column_update_grant(postgres_conn) -> None:
    from stock_research.theme_research_report_schema import (
        apply_theme_research_report_schema,
        inspect_theme_research_report_schema,
    )

    postgres_conn.rollback()
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        connection.execute(
            """
            GRANT UPDATE (title)
            ON research.theme_research_report_version
            TO theme_research_runtime
            """
        )
        connection.commit()
        inspection = inspect_theme_research_report_schema(connection.cursor())
        assert inspection["status"] == "drifted"
        assert (
            "column_privilege:theme_research_report_version.title"
            in inspection["missing"]
        )
    finally:
        connection.close()

    apply_theme_research_report_schema(service=TEST_SERVICE)
    verified = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        assert inspect_theme_research_report_schema(verified.cursor())["status"] == "current"
    finally:
        verified.close()


@contextmanager
def _replace_report_schema_with_drift(sql: str):
    from stock_research.theme_research_report_schema import (
        apply_theme_research_report_schema,
    )

    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        database_name = connection.execute("SELECT current_database()").fetchone()[0]
        if not database_name.endswith("_test"):
            pytest.fail(f"refusing to run integration tests against {database_name}")
        connection.execute(
            "DROP TABLE IF EXISTS research.theme_research_report_review_event CASCADE"
        )
        connection.execute(
            "DROP TABLE IF EXISTS research.theme_research_report_version CASCADE"
        )
        connection.execute(sql)
        connection.commit()
    finally:
        connection.close()

    try:
        yield
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "DROP TABLE IF EXISTS research.theme_research_report_review_event CASCADE"
            )
            cleanup.execute(
                "DROP TABLE IF EXISTS research.theme_research_report_version CASCADE"
            )
            cleanup.commit()
        finally:
            cleanup.close()
        apply_theme_research_report_schema(service=TEST_SERVICE)


def test_postgres_apply_rejects_report_table_missing_columns(postgres_conn) -> None:
    from stock_research.theme_research_report_schema import (
        ThemeResearchReportSchemaDriftError,
        apply_theme_research_report_schema,
    )

    postgres_conn.rollback()
    with _replace_report_schema_with_drift(
        """
        CREATE TABLE research.theme_research_report_version (
            report_version_id text PRIMARY KEY
        )
        """
    ):
        with pytest.raises(ThemeResearchReportSchemaDriftError, match="column:.*title"):
            apply_theme_research_report_schema(service=TEST_SERVICE)


def test_postgres_apply_rejects_wrong_same_name_index(postgres_conn) -> None:
    from stock_research.theme_research_report_schema import (
        ThemeResearchReportSchemaDriftError,
        apply_theme_research_report_schema,
    )

    postgres_conn.rollback()
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        connection.execute(
            "DROP INDEX research.uq_theme_research_report_one_published"
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX uq_theme_research_report_one_published
            ON research.theme_research_report_version (theme_id)
            WHERE status = 'published' AND theme_id <> 'excluded-theme'
            """
        )
        connection.commit()
    finally:
        connection.close()

    try:
        with pytest.raises(ThemeResearchReportSchemaDriftError, match="index:.*one_published"):
            apply_theme_research_report_schema(service=TEST_SERVICE)
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "DROP TABLE IF EXISTS research.theme_research_report_review_event CASCADE"
            )
            cleanup.execute(
                "DROP TABLE IF EXISTS research.theme_research_report_version CASCADE"
            )
            cleanup.commit()
        finally:
            cleanup.close()
        apply_theme_research_report_schema(service=TEST_SERVICE)


def test_postgres_apply_rejects_weakened_same_name_constraint(postgres_conn) -> None:
    from stock_research.theme_research_report_schema import (
        ThemeResearchReportSchemaDriftError,
        apply_theme_research_report_schema,
    )

    postgres_conn.rollback()
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        connection.execute(
            """
            ALTER TABLE research.theme_research_report_version
            DROP CONSTRAINT ck_theme_research_report_version_status
            """
        )
        connection.execute(
            """
            ALTER TABLE research.theme_research_report_version
            ADD CONSTRAINT ck_theme_research_report_version_status CHECK (
                status IN ('pending_review', 'published', 'rejected', 'archived')
                OR status = 'draft'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    try:
        with pytest.raises(ThemeResearchReportSchemaDriftError, match="constraint:.*version_status"):
            apply_theme_research_report_schema(service=TEST_SERVICE)
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "DROP TABLE IF EXISTS research.theme_research_report_review_event CASCADE"
            )
            cleanup.execute(
                "DROP TABLE IF EXISTS research.theme_research_report_version CASCADE"
            )
            cleanup.commit()
        finally:
            cleanup.close()
        apply_theme_research_report_schema(service=TEST_SERVICE)


def test_postgres_enforces_report_status_pdf_pair_and_one_published_version(postgres_conn) -> None:
    theme_id = "report-constraint-theme"
    _insert_theme(postgres_conn, theme_id)

    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_report(
            postgres_conn,
            "report-invalid-status",
            theme_id,
            "v1",
            status="draft",
        )
    postgres_conn.rollback()
    _insert_theme(postgres_conn, theme_id)

    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_report(
            postgres_conn,
            "report-invalid-pdf",
            theme_id,
            "v1",
            pdf_relative_path="report.pdf",
        )
    postgres_conn.rollback()
    _insert_theme(postgres_conn, theme_id)

    _insert_report(postgres_conn, "report-published-1", theme_id, "2026-07-31.1", status="published")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_report(postgres_conn, "report-published-2", theme_id, "v2", status="published")


def test_postgres_enforces_report_version_and_review_event_idempotency(postgres_conn) -> None:
    theme_id = "report-idempotency-theme"
    user_id = "report-review-admin"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, user_id)
    _insert_report(postgres_conn, "report-version-1", theme_id, "v1")

    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_report(postgres_conn, "report-version-duplicate", theme_id, "v1")
    postgres_conn.rollback()

    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, user_id)
    _insert_report(postgres_conn, "report-version-1", theme_id, "v1")
    event = (
        "review-event-1",
        "report-version-1",
        "pending_review",
        "published",
        user_id,
        "publish-request",
    )
    postgres_conn.execute(
        """
        INSERT INTO research.theme_research_report_review_event (
            event_id, report_version_id, from_status, to_status,
            actor_user_id, idempotency_key
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        event,
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        postgres_conn.execute(
            """
            INSERT INTO research.theme_research_report_review_event (
                event_id, report_version_id, from_status, to_status,
                actor_user_id, idempotency_key
            ) VALUES ('review-event-2', %s, %s, %s, %s, %s)
            """,
            event[1:],
        )
