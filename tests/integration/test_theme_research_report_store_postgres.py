from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from stock_research import theme_research_report_store as report_store
from stock_research.config import Settings
from stock_research.theme_research_report_manifest import (
    ReportManifestLimits,
    load_report_manifest,
)
from stock_research.theme_research_report_store import (
    ThemeResearchReportError,
    register_report_manifest as _register_report_manifest,
    report_version_id,
)


TEST_SERVICE = os.getenv("THEME_RESEARCH_POSTGRES_TEST_SERVICE", "")
TEST_RUNTIME_SERVICE = os.getenv("THEME_RESEARCH_POSTGRES_TEST_RUNTIME_SERVICE", "")
POSTGRES_ENABLED = (
    os.getenv("THEME_RESEARCH_POSTGRES_TEST") == "1" and bool(TEST_SERVICE)
)
_POSTGRES_FIXTURE_ROWS: dict[int, dict[str, set[str]]] = {}
_ACTIVE_POSTGRES_FIXTURE_ROWS: dict[str, set[str]] | None = None
_POSTGRES_TEST_SCHEMA_LOCK_KEY = 7171271448728574941


def register_report_manifest(*args, **kwargs):
    result = _register_report_manifest(*args, **kwargs)
    if result["result"] == "indexed" and _ACTIVE_POSTGRES_FIXTURE_ROWS is not None:
        _ACTIVE_POSTGRES_FIXTURE_ROWS["report_version_ids"].add(
            result["report_version_id"]
        )
    return result


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

    assert schema.THEME_RESEARCH_REPORT_SCHEMA_VERSION == "3"
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
    assert "actor_user_id text NOT NULL\n        CONSTRAINT" not in sql
    assert (
        "DROP CONSTRAINT IF EXISTS fk_theme_research_report_review_event_actor"
        in sql
    )
    assert "fk_theme_research_report_review_event_actor" not in (
        schema._EXPECTED_CONSTRAINT_DEFINITIONS
    )
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


def test_apply_report_schema_accepts_only_the_v2_actor_fk_migration(monkeypatch) -> None:
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

    inspections = iter(
        [
            {
                "status": "drifted",
                "missing": ["migration:v2_actor_fk"],
            },
            {"status": "current", "missing": []},
        ]
    )
    monkeypatch.setattr(schema, "connect", connected)
    monkeypatch.setattr(
        schema,
        "inspect_theme_research_report_schema",
        lambda cursor: next(inspections),
    )

    schema.apply_theme_research_report_schema(service="test_service")

    assert calls == [
        schema.THEME_RESEARCH_REPORT_MIGRATION_LOCK_SQL,
        schema.THEME_RESEARCH_REPORT_SCHEMA_SQL,
    ]


def test_apply_report_schema_rejects_same_named_non_v2_actor_constraint(
    monkeypatch,
) -> None:
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
            "missing": [
                "constraint_extra:fk_theme_research_report_review_event_actor"
            ],
        },
    )

    with pytest.raises(schema.ThemeResearchReportSchemaDriftError):
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
            if "JOIN pg_attribute" in self.sql and "format_type" in self.sql:
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
            if "FROM pg_index index" in self.sql:
                return [
                    {
                        "indexname": name,
                        "indexdef": definition,
                        "is_unique": name.startswith("uq_"),
                        "is_exclusion": False,
                        "is_constraint_backed": False,
                        "has_expressions": False,
                        "has_predicate": False,
                    }
                    for name, definition in schema._EXPECTED_INDEX_DEFINITIONS.items()
                ]
            if "FROM pg_trigger trigger" in self.sql:
                return []
            if "LEFT JOIN pg_policy" in self.sql:
                return [
                    {
                        "table_name": table_name,
                        "rls_enabled": False,
                        "rls_forced": False,
                        "policy_name": None,
                    }
                    for table_name in schema._EXPECTED_COLUMNS
                ]
            if "SELECT rolname FROM pg_roles" in self.sql:
                return []
            if "relation.relacl" in self.sql and "privilege.grantee" in self.sql:
                return []
            if "attribute.attacl" in self.sql and "privilege.grantee" in self.sql:
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


@contextmanager
def _exclusive_postgres_test_schema():
    lock_connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        database_name = lock_connection.execute("SELECT current_database()").fetchone()[0]
        if not database_name.endswith("_test"):
            pytest.fail(f"refusing to run integration tests against {database_name}")
        lock_connection.execute(
            "SELECT pg_advisory_lock(%s)",
            (_POSTGRES_TEST_SCHEMA_LOCK_KEY,),
        )
        lock_connection.commit()
        try:
            yield
        finally:
            released = lock_connection.execute(
                "SELECT pg_advisory_unlock(%s)",
                (_POSTGRES_TEST_SCHEMA_LOCK_KEY,),
            ).fetchone()[0]
            if released is not True:
                raise AssertionError("PostgreSQL test schema advisory lock was not held")
            lock_connection.commit()
    finally:
        lock_connection.close()


def _postgres_conn_impl():
    global _ACTIVE_POSTGRES_FIXTURE_ROWS

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
        bootstrap.commit()
    finally:
        bootstrap.close()

    apply_theme_research_report_schema(service=TEST_SERVICE)
    apply_theme_research_report_schema(service=TEST_SERVICE)

    connection = psycopg.connect(f"service={TEST_SERVICE}")
    fixture_rows = {
        "report_version_ids": set(),
        "created_theme_ids": set(),
        "created_user_ids": set(),
    }
    _POSTGRES_FIXTURE_ROWS[id(connection)] = fixture_rows
    previous_active_fixture_rows = _ACTIVE_POSTGRES_FIXTURE_ROWS
    _ACTIVE_POSTGRES_FIXTURE_ROWS = fixture_rows
    try:
        yield connection
    finally:
        _ACTIVE_POSTGRES_FIXTURE_ROWS = previous_active_fixture_rows
        try:
            try:
                connection.rollback()
            finally:
                connection.close()
        finally:
            _POSTGRES_FIXTURE_ROWS.pop(id(connection), None)
            _cleanup_postgres_fixture_rows(fixture_rows)


@pytest.fixture
def postgres_conn():
    if not POSTGRES_ENABLED:
        pytest.skip("set THEME_RESEARCH_POSTGRES_TEST=1 and a dedicated test service")
    with _exclusive_postgres_test_schema():
        yield from _postgres_conn_impl()


def _cleanup_postgres_fixture_rows(fixture_rows: dict[str, set[str]]) -> None:
    report_version_ids = sorted(fixture_rows["report_version_ids"])
    created_theme_ids = sorted(fixture_rows["created_theme_ids"])
    created_user_ids = sorted(fixture_rows["created_user_ids"])
    cleanup = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        if report_version_ids:
            cleanup.execute(
                """
                DELETE FROM research.theme_research_report_review_event
                WHERE report_version_id = ANY(%s)
                """,
                (report_version_ids,),
            )
            cleanup.execute(
                """
                DELETE FROM research.theme_research_report_version
                WHERE report_version_id = ANY(%s)
                """,
                (report_version_ids,),
            )
        if created_theme_ids:
            cleanup.execute(
                """
                DELETE FROM research.theme_research_theme
                WHERE theme_id = ANY(%s)
                """,
                (created_theme_ids,),
            )
        if created_user_ids:
            cleanup.execute(
                """
                DELETE FROM identity.user_account
                WHERE user_id = ANY(%s)
                """,
                (created_user_ids,),
            )
        cleanup.commit()
    except Exception:
        cleanup.rollback()
        raise
    finally:
        cleanup.close()


def _fixture_rows(postgres_conn) -> dict[str, set[str]] | None:
    return _POSTGRES_FIXTURE_ROWS.get(id(postgres_conn))


def _insert_theme(postgres_conn, theme_id: str) -> None:
    fixture_rows = _fixture_rows(postgres_conn)
    inserted = postgres_conn.execute(
        """
        INSERT INTO research.theme_research_theme (
            theme_id, theme_name, theme_type, summary, status, created_from,
            last_updated, content_sha256, created_by, updated_by
        ) VALUES (%s, %s, 'other', 'test', 'draft', 'manual', '2026-07-31', %s, 'test', 'test')
        ON CONFLICT (theme_id) DO NOTHING
        RETURNING theme_id
        """,
        (theme_id, theme_id, f"sha-{theme_id}"),
    ).fetchone()
    if inserted is not None and fixture_rows is not None:
        fixture_rows["created_theme_ids"].add(inserted[0])


def _insert_user(postgres_conn, user_id: str) -> None:
    inserted = postgres_conn.execute(
        """
        INSERT INTO identity.user_account (
            user_id, username, role, password_hash
        ) VALUES (%s, %s, 'admin', 'test')
        ON CONFLICT (user_id) DO NOTHING
        RETURNING user_id
        """,
        (user_id, user_id),
    ).fetchone()
    fixture_rows = _fixture_rows(postgres_conn)
    if inserted is not None and fixture_rows is not None:
        fixture_rows["created_user_ids"].add(inserted[0])


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
        "generated_at": "2026-07-31T00:00:00Z",
        "metadata": {},
    }
    values.update(overrides)
    values["metadata"] = json.dumps(values["metadata"])
    postgres_conn.execute(
        """
        INSERT INTO research.theme_research_report_version (
            report_version_id, theme_id, version, title, summary, status,
            markdown_relative_path, markdown_sha256, pdf_relative_path, pdf_sha256,
            manifest_relative_path, manifest_sha256, generator_name, generator_version,
            generated_at, metadata
        ) VALUES (
            %(report_version_id)s, %(theme_id)s, %(version)s, %(title)s, %(summary)s, %(status)s,
            %(markdown_relative_path)s, %(markdown_sha256)s, %(pdf_relative_path)s, %(pdf_sha256)s,
            %(manifest_relative_path)s, %(manifest_sha256)s, %(generator_name)s, %(generator_version)s,
            %(generated_at)s, %(metadata)s::jsonb
        )
        """,
        values,
    )
    fixture_rows = _fixture_rows(postgres_conn)
    if fixture_rows is not None:
        fixture_rows["report_version_ids"].add(report_id)


def test_postgres_fixture_teardown_removes_only_its_committed_rows() -> None:
    if not POSTGRES_ENABLED:
        pytest.skip("set THEME_RESEARCH_POSTGRES_TEST=1 and a dedicated test service")

    run_id = uuid.uuid4().hex
    theme_id = f"report-fixture-cleanup-theme-{run_id}"
    user_id = f"report-fixture-cleanup-user-{run_id}"
    report_id = f"report-fixture-cleanup-version-{run_id}"
    event_id = f"report-fixture-cleanup-event-{run_id}"
    sentinel_theme_id = f"report-fixture-sentinel-theme-{run_id}"
    sentinel_user_id = f"report-fixture-sentinel-user-{run_id}"
    sentinel_report_id = f"report-fixture-sentinel-version-{run_id}"
    sentinel_event_id = f"report-fixture-sentinel-event-{run_id}"
    sentinel = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        _insert_theme(sentinel, sentinel_theme_id)
        _insert_user(sentinel, sentinel_user_id)
        sentinel.commit()
    finally:
        sentinel.close()

    fixture_iterator = postgres_conn.__wrapped__()
    connection = next(fixture_iterator)
    try:
        sentinel = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            _insert_report(
                sentinel,
                sentinel_report_id,
                sentinel_theme_id,
                "sentinel-v1",
            )
            sentinel.execute(
                """
                INSERT INTO research.theme_research_report_review_event (
                    event_id, report_version_id, from_status, to_status,
                    actor_user_id, idempotency_key
                ) VALUES (%s, %s, NULL, 'pending_review', %s, %s)
                """,
                (
                    sentinel_event_id,
                    sentinel_report_id,
                    sentinel_user_id,
                    f"sentinel-{run_id}",
                ),
            )
            sentinel.commit()
        finally:
            sentinel.close()

        _insert_theme(connection, sentinel_theme_id)
        _insert_theme(connection, theme_id)
        _insert_user(connection, user_id)
        _insert_report(connection, report_id, theme_id, "cleanup-v1")
        connection.execute(
            """
            INSERT INTO research.theme_research_report_review_event (
                event_id, report_version_id, from_status, to_status,
                actor_user_id, idempotency_key
            ) VALUES (%s, %s, NULL, 'pending_review', %s, %s)
            """,
            (event_id, report_id, user_id, f"cleanup-{run_id}"),
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="simulated fixture test failure"):
            fixture_iterator.throw(RuntimeError("simulated fixture test failure"))
    finally:
        fixture_iterator.close()

    verifier = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        counts = verifier.execute(
            """
            SELECT
                (SELECT count(*) FROM research.theme_research_report_review_event
                 WHERE event_id = %s),
                (SELECT count(*) FROM research.theme_research_report_version
                 WHERE report_version_id = %s),
                (SELECT count(*) FROM research.theme_research_theme
                 WHERE theme_id = %s),
                (SELECT count(*) FROM identity.user_account
                 WHERE user_id = %s),
                (SELECT count(*) FROM research.theme_research_report_review_event
                 WHERE event_id = %s),
                (SELECT count(*) FROM research.theme_research_report_version
                 WHERE report_version_id = %s),
                (SELECT count(*) FROM research.theme_research_theme
                 WHERE theme_id = %s),
                (SELECT count(*) FROM identity.user_account
                 WHERE user_id = %s)
            """,
            (
                event_id,
                report_id,
                theme_id,
                user_id,
                sentinel_event_id,
                sentinel_report_id,
                sentinel_theme_id,
                sentinel_user_id,
            ),
        ).fetchone()
    finally:
        try:
            verifier.execute(
                "DELETE FROM research.theme_research_report_review_event WHERE event_id = %s",
                (event_id,),
            )
            verifier.execute(
                "DELETE FROM research.theme_research_report_version WHERE report_version_id = %s",
                (report_id,),
            )
            verifier.execute(
                "DELETE FROM research.theme_research_theme WHERE theme_id = %s",
                (theme_id,),
            )
            verifier.execute(
                "DELETE FROM identity.user_account WHERE user_id = %s",
                (user_id,),
            )
            verifier.execute(
                "DELETE FROM research.theme_research_report_review_event WHERE event_id = %s",
                (sentinel_event_id,),
            )
            verifier.execute(
                "DELETE FROM research.theme_research_report_version WHERE report_version_id = %s",
                (sentinel_report_id,),
            )
            verifier.execute(
                "DELETE FROM research.theme_research_theme WHERE theme_id = %s",
                (sentinel_theme_id,),
            )
            verifier.execute(
                "DELETE FROM identity.user_account WHERE user_id = %s",
                (sentinel_user_id,),
            )
            verifier.commit()
        finally:
            verifier.close()

    assert counts == (0, 0, 0, 0, 1, 1, 1, 1)


def test_postgres_fixture_serializes_schema_ownership_and_preserves_sentinel() -> None:
    if not POSTGRES_ENABLED:
        pytest.skip("set THEME_RESEARCH_POSTGRES_TEST=1 and a dedicated test service")

    run_id = uuid.uuid4().hex
    sentinel_theme_id = f"report-fixture-lock-theme-{run_id}"
    sentinel_user_id = f"report-fixture-lock-user-{run_id}"
    sentinel_report_id = f"report-fixture-lock-version-{run_id}"
    sentinel_event_id = f"report-fixture-lock-event-{run_id}"
    first_iterator = postgres_conn.__wrapped__()
    first_connection = next(first_iterator)
    second_attempt_started = threading.Event()
    second_opened = threading.Event()
    second_holder = {}
    blocked = False
    counts = None
    try:
        sentinel = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            _insert_theme(sentinel, sentinel_theme_id)
            _insert_user(sentinel, sentinel_user_id)
            _insert_report(
                sentinel,
                sentinel_report_id,
                sentinel_theme_id,
                "sentinel-v1",
            )
            sentinel.execute(
                """
                INSERT INTO research.theme_research_report_review_event (
                    event_id, report_version_id, from_status, to_status,
                    actor_user_id, idempotency_key
                ) VALUES (%s, %s, NULL, 'pending_review', %s, %s)
                """,
                (
                    sentinel_event_id,
                    sentinel_report_id,
                    sentinel_user_id,
                    f"sentinel-lock-{run_id}",
                ),
            )
            sentinel.commit()
        finally:
            sentinel.close()
        _insert_theme(first_connection, sentinel_theme_id)
        first_connection.commit()

        def open_second_fixture():
            iterator = postgres_conn.__wrapped__()
            second_attempt_started.set()
            connection = next(iterator)
            second_holder["iterator"] = iterator
            second_holder["connection"] = connection
            second_opened.set()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(open_second_fixture)
            assert second_attempt_started.wait(timeout=10)
            blocked = not second_opened.wait(timeout=0.25)
            first_iterator.close()
            future.result(timeout=10)
            _insert_theme(second_holder["connection"], sentinel_theme_id)
            second_holder["connection"].commit()
            second_holder["iterator"].close()

        verifier = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            counts = verifier.execute(
                """
                SELECT
                    (SELECT count(*) FROM research.theme_research_report_review_event
                     WHERE event_id = %s),
                    (SELECT count(*) FROM research.theme_research_report_version
                     WHERE report_version_id = %s),
                    (SELECT count(*) FROM research.theme_research_theme
                     WHERE theme_id = %s),
                    (SELECT count(*) FROM identity.user_account
                     WHERE user_id = %s)
                """,
                (
                    sentinel_event_id,
                    sentinel_report_id,
                    sentinel_theme_id,
                    sentinel_user_id,
                ),
            ).fetchone()
        finally:
            verifier.close()
    finally:
        first_iterator.close()
        if "iterator" in second_holder:
            second_holder["iterator"].close()
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "DELETE FROM research.theme_research_report_review_event WHERE event_id = %s",
                (sentinel_event_id,),
            )
            cleanup.execute(
                "DELETE FROM research.theme_research_report_version WHERE report_version_id = %s",
                (sentinel_report_id,),
            )
            cleanup.execute(
                "DELETE FROM research.theme_research_theme WHERE theme_id = %s",
                (sentinel_theme_id,),
            )
            cleanup.execute(
                "DELETE FROM identity.user_account WHERE user_id = %s",
                (sentinel_user_id,),
            )
            cleanup.commit()
        finally:
            cleanup.close()

    assert blocked is True
    assert counts == (1, 1, 1, 1)


def _validated_manifest(
    tmp_path: Path,
    *,
    theme_id: str = "report-store-theme",
    version: str = "2026-07-31-v1",
    pdf: bytes | None = b"%PDF-1.7\nreport\n%%EOF\n",
):
    report_root = tmp_path / "reports" / "theme-research"
    version_dir = report_root / theme_id / version
    version_dir.mkdir(parents=True)
    markdown = b"# Theme report\n"
    (version_dir / "report.md").write_bytes(markdown)
    artifacts = {
        "markdown": {
            "path": "report.md",
            "sha256": hashlib.sha256(markdown).hexdigest(),
        }
    }
    if pdf is not None:
        (version_dir / "report.pdf").write_bytes(pdf)
        artifacts["pdf"] = {
            "path": "report.pdf",
            "sha256": hashlib.sha256(pdf).hexdigest(),
        }
    manifest_path = version_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "theme_research_report_manifest_v1",
                "theme_id": theme_id,
                "version": version,
                "title": "Production Theme Report",
                "summary": "Immutable production report.",
                "generated_at": "2026-07-31T08:30:00+08:00",
                "generator": {"name": "theme-worker", "version": "2.4.1"},
                "artifacts": artifacts,
                "metadata": {
                    "source": {"kind": "production", "tags": ["primary"]}
                },
            }
        ),
        encoding="utf-8",
    )
    return load_report_manifest(
        manifest_path,
        report_root=report_root,
        limits=ReportManifestLimits(
            max_manifest_bytes=16_384,
            max_markdown_bytes=16_384,
            max_pdf_bytes=16_384,
        ),
    )


def _seed_report_store(postgres_conn, theme_id: str) -> None:
    _insert_theme(postgres_conn, theme_id)
    postgres_conn.commit()


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


def test_postgres_apply_migrates_v2_actor_fk_to_internal_system_subject(
    postgres_conn,
) -> None:
    from stock_research.theme_research_report_schema import (
        apply_theme_research_report_schema,
        inspect_theme_research_report_schema,
    )

    postgres_conn.execute(
        """
        ALTER TABLE research.theme_research_report_review_event
        ADD CONSTRAINT fk_theme_research_report_review_event_actor
        FOREIGN KEY (actor_user_id) REFERENCES identity.user_account(user_id)
        """
    )
    postgres_conn.commit()

    apply_theme_research_report_schema(service=TEST_SERVICE)

    verified = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        assert inspect_theme_research_report_schema(verified.cursor()) == {
            "status": "current",
            "missing": [],
        }
        assert verified.execute(
            """
            SELECT count(*)
            FROM pg_constraint
            WHERE conname = 'fk_theme_research_report_review_event_actor'
              AND conrelid = 'research.theme_research_report_review_event'::regclass
            """
        ).fetchone()[0] == 0
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


def test_postgres_apply_rejects_extra_not_null_column(postgres_conn) -> None:
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
            ADD COLUMN ingestion_guard text NOT NULL
            """
        )
        connection.commit()
    finally:
        connection.close()

    try:
        with pytest.raises(ThemeResearchReportSchemaDriftError, match="column_extra:.*ingestion_guard"):
            apply_theme_research_report_schema(service=TEST_SERVICE)
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                """
                ALTER TABLE research.theme_research_report_version
                DROP COLUMN IF EXISTS ingestion_guard
                """
            )
            cleanup.commit()
        finally:
            cleanup.close()


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


def test_postgres_apply_rejects_extra_check_constraint(postgres_conn) -> None:
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
            ADD CONSTRAINT ck_theme_research_report_extra_title CHECK (title <> '')
            """
        )
        connection.commit()
    finally:
        connection.close()

    try:
        with pytest.raises(ThemeResearchReportSchemaDriftError, match="constraint_extra:.*extra_title"):
            apply_theme_research_report_schema(service=TEST_SERVICE)
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                """
                ALTER TABLE research.theme_research_report_version
                DROP CONSTRAINT IF EXISTS ck_theme_research_report_extra_title
                """
            )
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_apply_rejects_user_trigger(postgres_conn) -> None:
    from stock_research.theme_research_report_schema import (
        ThemeResearchReportSchemaDriftError,
        apply_theme_research_report_schema,
    )

    postgres_conn.rollback()
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        connection.execute(
            """
            CREATE OR REPLACE FUNCTION research.theme_research_report_test_trigger()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RETURN NEW;
            END;
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_theme_research_report_extra_before
            BEFORE INSERT ON research.theme_research_report_version
            FOR EACH ROW EXECUTE FUNCTION research.theme_research_report_test_trigger()
            """
        )
        connection.commit()
    finally:
        connection.close()

    try:
        with pytest.raises(ThemeResearchReportSchemaDriftError, match="trigger:.*extra_before"):
            apply_theme_research_report_schema(service=TEST_SERVICE)
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "DROP TRIGGER IF EXISTS trg_theme_research_report_extra_before "
                "ON research.theme_research_report_version"
            )
            cleanup.execute(
                "DROP FUNCTION IF EXISTS research.theme_research_report_test_trigger()"
            )
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_apply_rejects_rls_and_policy(postgres_conn) -> None:
    from stock_research.theme_research_report_schema import (
        ThemeResearchReportSchemaDriftError,
        apply_theme_research_report_schema,
    )

    postgres_conn.rollback()
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        connection.execute(
            "ALTER TABLE research.theme_research_report_version ENABLE ROW LEVEL SECURITY"
        )
        connection.execute(
            """
            CREATE POLICY theme_research_report_extra_policy
            ON research.theme_research_report_version
            FOR SELECT USING (true)
            """
        )
        connection.commit()
    finally:
        connection.close()

    try:
        with pytest.raises(ThemeResearchReportSchemaDriftError, match="rls:|policy:"):
            apply_theme_research_report_schema(service=TEST_SERVICE)
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "DROP POLICY IF EXISTS theme_research_report_extra_policy "
                "ON research.theme_research_report_version"
            )
            cleanup.execute(
                "ALTER TABLE research.theme_research_report_version DISABLE ROW LEVEL SECURITY"
            )
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_allows_extra_nonunique_performance_index(postgres_conn) -> None:
    from stock_research.theme_research_report_schema import (
        apply_theme_research_report_schema,
        inspect_theme_research_report_schema,
    )

    postgres_conn.rollback()
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        connection.execute(
            """
            CREATE INDEX idx_theme_research_report_extra_title
            ON research.theme_research_report_version (title)
            """
        )
        connection.commit()
        assert inspect_theme_research_report_schema(connection.cursor())["status"] == "current"
    finally:
        connection.close()

    try:
        apply_theme_research_report_schema(service=TEST_SERVICE)
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "DROP INDEX IF EXISTS research.idx_theme_research_report_extra_title"
            )
            cleanup.commit()
        finally:
            cleanup.close()


@pytest.mark.parametrize(
    ("index_name", "index_expression"),
    [
        (
            "idx_theme_research_report_extra_expression",
            "(lower(title))",
        ),
        (
            "idx_theme_research_report_extra_partial",
            "(title) WHERE status = 'pending_review'",
        ),
    ],
)
def test_postgres_rejects_extra_expression_or_partial_index(
    postgres_conn,
    index_name,
    index_expression,
) -> None:
    from stock_research.theme_research_report_schema import (
        ThemeResearchReportSchemaDriftError,
        apply_theme_research_report_schema,
    )

    postgres_conn.rollback()
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        connection.execute(
            f"""
            CREATE INDEX {index_name}
            ON research.theme_research_report_version {index_expression}
            """
        )
        connection.commit()
    finally:
        connection.close()

    try:
        with pytest.raises(ThemeResearchReportSchemaDriftError, match=rf"index_extra:.*{index_name}"):
            apply_theme_research_report_schema(service=TEST_SERVICE)
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(f"DROP INDEX IF EXISTS research.{index_name}")
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_rejects_extra_unique_index(postgres_conn) -> None:
    from stock_research.theme_research_report_schema import (
        ThemeResearchReportSchemaDriftError,
        apply_theme_research_report_schema,
    )

    postgres_conn.rollback()
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        connection.execute(
            """
            CREATE UNIQUE INDEX uq_theme_research_report_extra_title
            ON research.theme_research_report_version (title)
            """
        )
        connection.commit()
    finally:
        connection.close()

    try:
        with pytest.raises(ThemeResearchReportSchemaDriftError, match="index_extra:.*extra_title"):
            apply_theme_research_report_schema(service=TEST_SERVICE)
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "DROP INDEX IF EXISTS research.uq_theme_research_report_extra_title"
            )
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_apply_revokes_unknown_grantee_privileges(postgres_conn) -> None:
    from stock_research.theme_research_report_schema import (
        apply_theme_research_report_schema,
        inspect_theme_research_report_schema,
    )

    postgres_conn.rollback()
    role_name = "theme_research_report_acl_test"
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        database_name = connection.execute("SELECT current_database()").fetchone()[0]
        if not database_name.endswith("_test"):
            pytest.fail(f"refusing to run integration tests against {database_name}")
        connection.execute(f"DROP ROLE IF EXISTS {role_name}")
        connection.execute(f"CREATE ROLE {role_name} NOLOGIN")
        connection.execute(
            f"""
            GRANT DELETE, TRUNCATE ON research.theme_research_report_version
            TO {role_name}
            """
        )
        connection.execute(
            f"""
            GRANT UPDATE (title) ON research.theme_research_report_version
            TO {role_name}
            """
        )
        connection.execute(
            """
            GRANT UPDATE (summary) ON research.theme_research_report_version
            TO PUBLIC
            """
        )
        connection.commit()
        inspection = inspect_theme_research_report_schema(connection.cursor())
        assert inspection["status"] == "drifted"
        assert any(item.startswith("acl:") for item in inspection["missing"])
        assert (
            "public_privilege:theme_research_report_version.summary"
            in inspection["missing"]
        )
    finally:
        connection.close()

    try:
        apply_theme_research_report_schema(service=TEST_SERVICE)
        verified = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            privileges = verified.execute(
                """
                SELECT
                    has_table_privilege(%s, 'research.theme_research_report_version', 'DELETE'),
                    has_table_privilege(%s, 'research.theme_research_report_version', 'TRUNCATE'),
                    has_column_privilege(
                        %s, 'research.theme_research_report_version', 'title', 'UPDATE'
                    ),
                    EXISTS (
                        SELECT 1
                        FROM pg_attribute attribute
                        CROSS JOIN LATERAL aclexplode(attribute.attacl) privilege
                        WHERE attribute.attrelid =
                            'research.theme_research_report_version'::regclass
                          AND attribute.attname = 'summary'
                          AND privilege.grantee = 0
                          AND privilege.privilege_type = 'UPDATE'
                    )
                """,
                (role_name, role_name, role_name),
            ).fetchone()
            assert privileges == (False, False, False, False)
            assert inspect_theme_research_report_schema(verified.cursor())["status"] == "current"
        finally:
            verified.close()
    finally:
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                "REVOKE ALL PRIVILEGES ON TABLE "
                "research.theme_research_report_version FROM PUBLIC"
            )
            cleanup.execute(
                "REVOKE ALL PRIVILEGES (summary) ON TABLE "
                "research.theme_research_report_version FROM PUBLIC"
            )
            cleanup.execute(
                f"REVOKE ALL PRIVILEGES ON TABLE "
                f"research.theme_research_report_version FROM {role_name}"
            )
            cleanup.execute(
                f"REVOKE ALL PRIVILEGES (title) ON TABLE "
                f"research.theme_research_report_version FROM {role_name}"
            )
            cleanup.execute(f"DROP ROLE IF EXISTS {role_name}")
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_apply_removes_runtime_grant_options_and_column_references(
    postgres_conn,
) -> None:
    from stock_research.theme_research_report_schema import (
        apply_theme_research_report_schema,
        inspect_theme_research_report_schema,
    )

    postgres_conn.rollback()
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        connection.execute(
            """
            GRANT SELECT ON research.theme_research_report_version
            TO theme_research_runtime WITH GRANT OPTION
            """
        )
        connection.execute(
            """
            GRANT REFERENCES (theme_id) ON research.theme_research_report_version
            TO theme_research_runtime
            """
        )
        connection.commit()
        inspection = inspect_theme_research_report_schema(connection.cursor())
        assert inspection["status"] == "drifted"
        assert any(item.startswith("acl:") for item in inspection["missing"])
    finally:
        connection.close()

    apply_theme_research_report_schema(service=TEST_SERVICE)
    verified = psycopg.connect(f"service={TEST_SERVICE}")
    try:
        assert inspect_theme_research_report_schema(verified.cursor())["status"] == "current"
        grants = verified.execute(
            """
            SELECT
                has_table_privilege(
                    'theme_research_runtime',
                    'research.theme_research_report_version',
                    'SELECT WITH GRANT OPTION'
                ),
                has_column_privilege(
                    'theme_research_runtime',
                    'research.theme_research_report_version',
                    'theme_id',
                    'REFERENCES'
                )
            """
        ).fetchone()
        assert grants == (False, False)
    finally:
        verified.close()


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


def test_report_version_id_is_stable_and_rejects_empty_identity() -> None:
    expected = report_version_id("ai-power", "2026-07-31-v1")

    assert expected == report_version_id("ai-power", "2026-07-31-v1")
    assert len(expected) == 64
    assert expected != report_version_id("ai-power", "2026-07-31-v2")
    assert expected != report_version_id("grid-power", "2026-07-31-v1")
    with pytest.raises(ThemeResearchReportError) as theme_error:
        report_version_id("", "v1")
    with pytest.raises(ThemeResearchReportError) as version_error:
        report_version_id("theme", "")
    assert theme_error.value.code == "THEME_REPORT_IDENTITY_INVALID"
    assert version_error.value.code == "THEME_REPORT_IDENTITY_INVALID"


def test_report_error_details_are_detached_from_callers() -> None:
    details = {"fields": ["manifest_sha256"]}

    error = ThemeResearchReportError("CODE", "message", details)
    details["fields"].append("markdown_sha256")

    assert error.details == {"fields": ["manifest_sha256"]}


def test_register_maps_operational_errors_without_leaking_database_text(
    monkeypatch,
    tmp_path,
) -> None:
    from stock_research import theme_research_report_store as store

    manifest = _validated_manifest(tmp_path)
    database_error = psycopg.OperationalError(
        "secret host and database diagnostics must not escape"
    )

    @contextmanager
    def unavailable(service):
        raise database_error
        yield

    monkeypatch.setattr(store, "connect", unavailable)

    with pytest.raises(ThemeResearchReportError) as exc_info:
        store.register_report_manifest(manifest, service="unavailable")

    assert exc_info.value.code == "THEME_REPORT_STORE_UNAVAILABLE"
    assert exc_info.value.details == {}
    assert "secret" not in str(exc_info.value).lower()
    assert exc_info.value.__cause__ is database_error


def test_postgres_registers_manifest_and_audits_initial_pending_review(
    postgres_conn,
    tmp_path,
) -> None:
    manifest = _validated_manifest(tmp_path)
    _seed_report_store(postgres_conn, manifest.theme_id)

    result = register_report_manifest(manifest, service=TEST_SERVICE)

    expected_id = report_version_id(manifest.theme_id, manifest.version)
    assert result == {
        "report_version_id": expected_id,
        "theme_id": manifest.theme_id,
        "version": manifest.version,
        "status": "pending_review",
        "result": "indexed",
    }
    row = postgres_conn.execute(
        """
        SELECT report_version_id, theme_id, version, title, summary, status,
               markdown_relative_path, markdown_sha256,
               pdf_relative_path, pdf_sha256,
               manifest_relative_path, manifest_sha256,
               generator_name, generator_version, generator_metadata,
               generated_at, metadata, row_version,
               published_at, published_by_user_id, rejected_at,
               rejected_by_user_id, rejection_reason
        FROM research.theme_research_report_version
        WHERE report_version_id = %s
        """,
        (expected_id,),
    ).fetchone()
    assert row == (
        expected_id,
        manifest.theme_id,
        manifest.version,
        manifest.title,
        manifest.summary,
        "pending_review",
        manifest.markdown.relative_path,
        manifest.markdown.sha256,
        manifest.pdf.relative_path,
        manifest.pdf.sha256,
        manifest.manifest_relative_path,
        manifest.manifest_sha256,
        manifest.generator_name,
        manifest.generator_version,
        {},
        manifest.generated_at,
        {"source": {"kind": "production", "tags": ["primary"]}},
        1,
        None,
        None,
        None,
        None,
        "",
    )
    events = postgres_conn.execute(
        """
        SELECT event_id, report_version_id, from_status, to_status, actor_user_id,
               comment, request_id, idempotency_key
        FROM research.theme_research_report_review_event
        WHERE report_version_id = %s
        """,
        (expected_id,),
    ).fetchall()
    assert len(events) == 1
    expected_event_id = hashlib.sha256(
        ("theme-research-report-index-event\0" + expected_id).encode("utf-8")
    ).hexdigest()
    assert events[0][0:6] == (
        expected_event_id,
        expected_id,
        None,
        "pending_review",
        "system",
        "",
    )
    assert events[0][6]
    assert events[0][7]
    assert events[0][6] == hashlib.sha256(
        ("theme-research-report-index-request\0" + expected_id).encode("utf-8")
    ).hexdigest()
    assert events[0][7] == hashlib.sha256(
        ("theme-research-report-index-idempotency\0" + expected_id).encode("utf-8")
    ).hexdigest()


def test_postgres_repeated_registration_is_strictly_unchanged(
    postgres_conn,
    tmp_path,
) -> None:
    manifest = _validated_manifest(tmp_path)
    _seed_report_store(postgres_conn, manifest.theme_id)
    first = register_report_manifest(manifest, service=TEST_SERVICE)
    before = postgres_conn.execute(
        """
        SELECT status, row_version, indexed_at, updated_at,
               published_at, rejected_at
        FROM research.theme_research_report_version
        WHERE report_version_id = %s
        """,
        (first["report_version_id"],),
    ).fetchone()
    event_before = postgres_conn.execute(
        """
        SELECT event_id, request_id, idempotency_key, created_at
        FROM research.theme_research_report_review_event
        WHERE report_version_id = %s
        """,
        (first["report_version_id"],),
    ).fetchall()

    second = register_report_manifest(manifest, service=TEST_SERVICE)

    assert second == {**first, "result": "unchanged"}
    after = postgres_conn.execute(
        """
        SELECT status, row_version, indexed_at, updated_at,
               published_at, rejected_at
        FROM research.theme_research_report_version
        WHERE report_version_id = %s
        """,
        (first["report_version_id"],),
    ).fetchone()
    event_after = postgres_conn.execute(
        """
        SELECT event_id, request_id, idempotency_key, created_at
        FROM research.theme_research_report_review_event
        WHERE report_version_id = %s
        """,
        (first["report_version_id"],),
    ).fetchall()
    assert after == before
    assert event_after == event_before


def test_postgres_rejects_noncanonical_existing_report_version_id(
    postgres_conn,
    tmp_path,
) -> None:
    manifest = _validated_manifest(tmp_path)
    _seed_report_store(postgres_conn, manifest.theme_id)
    postgres_conn.execute(
        """
        INSERT INTO research.theme_research_report_version (
            report_version_id, theme_id, version, title, summary, status,
            markdown_relative_path, markdown_sha256,
            pdf_relative_path, pdf_sha256,
            manifest_relative_path, manifest_sha256,
            generator_name, generator_version, generator_metadata,
            generated_at, metadata, row_version
        ) VALUES (
            'noncanonical-report-id', %s, %s, %s, %s, 'pending_review',
            %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb, %s, %s, 1
        )
        """,
        (
            manifest.theme_id,
            manifest.version,
            manifest.title,
            manifest.summary,
            manifest.markdown.relative_path,
            manifest.markdown.sha256,
            manifest.pdf.relative_path,
            manifest.pdf.sha256,
            manifest.manifest_relative_path,
            manifest.manifest_sha256,
            manifest.generator_name,
            manifest.generator_version,
            manifest.generated_at,
            json.dumps({"source": {"kind": "production", "tags": ["primary"]}}),
        ),
    )
    fixture_rows = _fixture_rows(postgres_conn)
    if fixture_rows is not None:
        fixture_rows["report_version_ids"].add("noncanonical-report-id")
    postgres_conn.commit()

    with pytest.raises(ThemeResearchReportError) as exc_info:
        register_report_manifest(manifest, service=TEST_SERVICE)

    assert exc_info.value.code == "THEME_REPORT_VERSION_CONTENT_CONFLICT"
    assert exc_info.value.details == {"fields": ["report_version_id"]}
    assert postgres_conn.execute(
        "SELECT report_version_id FROM research.theme_research_report_version"
    ).fetchall() == [("noncanonical-report-id",)]
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_review_event"
    ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("field_name", "mutate"),
    [
        ("manifest_sha256", lambda manifest: replace(manifest, manifest_sha256="f" * 64)),
        (
            "manifest_relative_path",
            lambda manifest: replace(
                manifest,
                manifest_relative_path=f"{manifest.theme_id}/{manifest.version}/alternate.json",
            ),
        ),
        (
            "markdown_relative_path",
            lambda manifest: replace(
                manifest,
                markdown=replace(manifest.markdown, relative_path="alternate.md"),
            ),
        ),
        (
            "markdown_sha256",
            lambda manifest: replace(
                manifest,
                markdown=replace(manifest.markdown, sha256="e" * 64),
            ),
        ),
        (
            "pdf_relative_path",
            lambda manifest: replace(
                manifest,
                pdf=replace(manifest.pdf, relative_path="alternate.pdf"),
            ),
        ),
        (
            "pdf_sha256",
            lambda manifest: replace(
                manifest,
                pdf=replace(manifest.pdf, sha256="d" * 64),
            ),
        ),
        ("title", lambda manifest: replace(manifest, title="Changed title")),
        ("summary", lambda manifest: replace(manifest, summary="Changed summary")),
        (
            "generator_name",
            lambda manifest: replace(manifest, generator_name="different-worker"),
        ),
        (
            "generator_version",
            lambda manifest: replace(manifest, generator_version="different"),
        ),
        (
            "metadata",
            lambda manifest: replace(manifest, metadata={"source": {"kind": "changed"}}),
        ),
    ],
)
def test_postgres_rejects_conflicting_immutable_report_identity(
    postgres_conn,
    tmp_path,
    field_name,
    mutate,
) -> None:
    manifest = _validated_manifest(tmp_path)
    _seed_report_store(postgres_conn, manifest.theme_id)
    first = register_report_manifest(manifest, service=TEST_SERVICE)
    before = postgres_conn.execute(
        "SELECT * FROM research.theme_research_report_version WHERE report_version_id = %s",
        (first["report_version_id"],),
    ).fetchone()

    with pytest.raises(ThemeResearchReportError) as exc_info:
        register_report_manifest(mutate(manifest), service=TEST_SERVICE)

    assert exc_info.value.code == "THEME_REPORT_VERSION_CONTENT_CONFLICT"
    assert exc_info.value.details == {"fields": [field_name]}
    after = postgres_conn.execute(
        "SELECT * FROM research.theme_research_report_version WHERE report_version_id = %s",
        (first["report_version_id"],),
    ).fetchone()
    assert after == before
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_review_event WHERE report_version_id = %s",
        (first["report_version_id"],),
    ).fetchone()[0] == 1


def test_postgres_rejects_unknown_theme_without_partial_rows(postgres_conn, tmp_path) -> None:
    manifest = _validated_manifest(tmp_path, theme_id="missing-report-theme")
    _insert_user(postgres_conn, "system")
    postgres_conn.commit()

    with pytest.raises(ThemeResearchReportError) as exc_info:
        register_report_manifest(manifest, service=TEST_SERVICE)

    assert exc_info.value.code == "THEME_REPORT_THEME_NOT_FOUND"
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_version"
    ).fetchone()[0] == 0
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_review_event"
    ).fetchone()[0] == 0


def test_postgres_stores_absent_pdf_as_null_pair(postgres_conn, tmp_path) -> None:
    manifest = _validated_manifest(tmp_path, pdf=None)
    _seed_report_store(postgres_conn, manifest.theme_id)

    result = register_report_manifest(manifest, service=TEST_SERVICE)

    assert postgres_conn.execute(
        """
        SELECT pdf_relative_path, pdf_sha256
        FROM research.theme_research_report_version
        WHERE report_version_id = %s
        """,
        (result["report_version_id"],),
    ).fetchone() == (None, None)


def test_postgres_concurrent_identical_registration_creates_one_row_and_event(
    postgres_conn,
    tmp_path,
) -> None:
    manifest = _validated_manifest(tmp_path)
    _seed_report_store(postgres_conn, manifest.theme_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: register_report_manifest(manifest, service=TEST_SERVICE),
                range(2),
            )
        )

    assert sorted(result["result"] for result in results) == ["indexed", "unchanged"]
    assert len({result["report_version_id"] for result in results}) == 1
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_version"
    ).fetchone()[0] == 1
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_review_event"
    ).fetchone()[0] == 1


def test_postgres_concurrent_conflict_preserves_the_successful_row(
    postgres_conn,
    tmp_path,
) -> None:
    manifest = _validated_manifest(tmp_path)
    conflict = replace(manifest, manifest_sha256="c" * 64)
    _seed_report_store(postgres_conn, manifest.theme_id)

    def register(candidate):
        try:
            return register_report_manifest(candidate, service=TEST_SERVICE)
        except ThemeResearchReportError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(register, (manifest, conflict)))

    errors = [outcome for outcome in outcomes if isinstance(outcome, ThemeResearchReportError)]
    successes = [outcome for outcome in outcomes if isinstance(outcome, dict)]
    assert len(errors) == len(successes) == 1
    assert errors[0].code == "THEME_REPORT_VERSION_CONTENT_CONFLICT"
    stored_sha = postgres_conn.execute(
        "SELECT manifest_sha256 FROM research.theme_research_report_version"
    ).fetchone()[0]
    assert stored_sha in {manifest.manifest_sha256, conflict.manifest_sha256}
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_review_event"
    ).fetchone()[0] == 1


def test_postgres_event_failure_rolls_back_report_version(postgres_conn, tmp_path) -> None:
    from stock_research.theme_research_report_schema import (
        apply_theme_research_report_schema,
    )

    manifest = _validated_manifest(tmp_path)
    _seed_report_store(postgres_conn, manifest.theme_id)
    postgres_conn.execute(
        """
        ALTER TABLE research.theme_research_report_review_event
        ADD CONSTRAINT ck_theme_research_report_test_event_rejected
        CHECK (actor_user_id <> 'system')
        """
    )
    postgres_conn.commit()

    try:
        with pytest.raises(ThemeResearchReportError) as exc_info:
            register_report_manifest(manifest, service=TEST_SERVICE)

        assert exc_info.value.code == "THEME_REPORT_STORE_UNAVAILABLE"
        assert exc_info.value.details == {}
        assert isinstance(exc_info.value.__cause__, psycopg.errors.CheckViolation)

        assert postgres_conn.execute(
            "SELECT count(*) FROM research.theme_research_report_version"
        ).fetchone()[0] == 0
        assert postgres_conn.execute(
            "SELECT count(*) FROM research.theme_research_report_review_event"
        ).fetchone()[0] == 0
    finally:
        postgres_conn.rollback()
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                """
                ALTER TABLE research.theme_research_report_review_event
                DROP CONSTRAINT IF EXISTS ck_theme_research_report_test_event_rejected
                """
            )
            cleanup.commit()
        finally:
            cleanup.close()
        apply_theme_research_report_schema(service=TEST_SERVICE)


def test_postgres_runtime_service_registers_with_minimum_permissions(
    postgres_conn,
    tmp_path,
) -> None:
    if not TEST_RUNTIME_SERVICE:
        pytest.skip("dedicated runtime test service is required")
    manifest = _validated_manifest(tmp_path)
    _seed_report_store(postgres_conn, manifest.theme_id)
    assert postgres_conn.execute(
        "SELECT count(*) FROM identity.user_account WHERE user_id = 'system'"
    ).fetchone()[0] == 0

    result = register_report_manifest(manifest, service=TEST_RUNTIME_SERVICE)

    assert result["result"] == "indexed"
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_version WHERE report_version_id = %s",
        (result["report_version_id"],),
    ).fetchone()[0] == 1
    assert postgres_conn.execute(
        """
        SELECT actor_user_id
        FROM research.theme_research_report_review_event
        WHERE report_version_id = %s
        """,
        (result["report_version_id"],),
    ).fetchone()[0] == "system"


def test_postgres_runtime_service_can_publish_with_minimum_permissions(
    postgres_conn,
) -> None:
    if not TEST_RUNTIME_SERVICE:
        pytest.skip("dedicated runtime test service is required")
    theme_id = "report-runtime-review-theme"
    actor_id = "report-runtime-review-admin"
    report_id = "report-runtime-review-version"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, actor_id)
    _insert_report(postgres_conn, report_id, theme_id, "v1")
    postgres_conn.commit()
    with psycopg.connect(f"service={TEST_RUNTIME_SERVICE}") as runtime_conn:
        assert runtime_conn.execute(
            "SELECT has_schema_privilege(current_user, 'identity', 'USAGE')"
        ).fetchone()[0] is False

    result = report_store.publish_report_version(
        report_id,
        expected_row_version=1,
        actor_user_id=actor_id,
        actor_role="admin",
        comment="runtime approved",
        request_id="runtime-review-request",
        idempotency_key="runtime-review-key",
        service=TEST_RUNTIME_SERVICE,
    )

    assert result["status"] == "published"
    assert postgres_conn.execute(
        "SELECT status, row_version FROM research.theme_research_report_version WHERE report_version_id = %s",
        (report_id,),
    ).fetchone() == ("published", 2)


def test_postgres_publish_archives_current_and_exposes_safe_read_models(
    postgres_conn,
) -> None:
    theme_id = "report-review-publish-theme"
    actor_id = "report-review-publish-admin"
    old_id = "report-review-published-old"
    new_id = "report-review-pending-new"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, actor_id)
    _insert_report(
        postgres_conn,
        old_id,
        theme_id,
        "v1",
        status="published",
    )
    postgres_conn.execute(
        """
        UPDATE research.theme_research_report_version
        SET published_at = '2026-07-30T00:00:00Z',
            published_by_user_id = %s
        WHERE report_version_id = %s
        """,
        (actor_id, old_id),
    )
    _insert_report(postgres_conn, new_id, theme_id, "v2")
    postgres_conn.commit()

    result = report_store.publish_report_version(
        new_id,
        expected_row_version=1,
        actor_user_id=actor_id,
        actor_role="admin",
        comment="approved",
        request_id="publish-request-1",
        idempotency_key="publish-key-1",
        service=TEST_SERVICE,
    )

    assert result["status"] == "published"
    assert result["row_version"] == 2
    assert result["published_by_user_id"] == actor_id
    assert not any("path" in key or "sha256" in key for key in result)
    stored = postgres_conn.execute(
        """
        SELECT report_version_id, status, row_version, published_at,
               published_by_user_id, updated_at
        FROM research.theme_research_report_version
        WHERE report_version_id IN (%s, %s)
        ORDER BY report_version_id
        """,
        (old_id, new_id),
    ).fetchall()
    assert [row[1] for row in stored] == ["published", "archived"]
    assert {row[0]: row[2] for row in stored} == {new_id: 2, old_id: 2}
    assert all(row[3] is not None and row[4] == actor_id and row[5] is not None for row in stored)

    expected_target_event = hashlib.sha256(
        ("theme-research-report-review-event\0publish\0" + actor_id + "\0publish-key-1").encode()
    ).hexdigest()
    archive_key = "publish-key-1:archive:" + old_id
    expected_archive_event = hashlib.sha256(
        ("theme-research-report-review-event\0archive\0" + actor_id + "\0" + archive_key).encode()
    ).hexdigest()
    events = postgres_conn.execute(
        """
        SELECT event_id, report_version_id, from_status, to_status,
               actor_user_id, comment, request_id, idempotency_key
        FROM research.theme_research_report_review_event
        WHERE report_version_id IN (%s, %s)
        ORDER BY to_status
        """,
        (old_id, new_id),
    ).fetchall()
    assert events == [
        (
            expected_archive_event,
            old_id,
            "published",
            "archived",
            actor_id,
            "superseded by " + new_id,
            "publish-request-1",
            archive_key,
        ),
        (
            expected_target_event,
            new_id,
            "pending_review",
            "published",
            actor_id,
            "approved",
            "publish-request-1",
            "publish-key-1",
        ),
    ]

    approved = report_store.list_approved_report_versions(theme_id, service=TEST_SERVICE)
    assert approved["total"] == 2
    assert [item["report_version_id"] for item in approved["items"]] == [new_id, old_id]
    assert all(
        not any(
            forbidden in key
            for forbidden in ("path", "sha256", "rejection", "generator")
        )
        for item in approved["items"]
        for key in item
    )
    assert report_store.get_approved_report_version(theme_id, new_id, service=TEST_SERVICE) == approved["items"][0]
    artifact = report_store.get_approved_report_artifact_record(theme_id, new_id, service=TEST_SERVICE)
    assert artifact["markdown_relative_path"].endswith("/report.md")
    assert artifact["markdown_sha256"] == "a" * 64
    admin = report_store.get_admin_report_version(new_id, service=TEST_SERVICE)
    assert admin["manifest_relative_path"].endswith("/manifest.json")
    assert admin["generator_name"] == "integration-test"


def test_postgres_rejects_pending_report_without_changing_current_publish(
    postgres_conn,
) -> None:
    theme_id = "report-review-reject-theme"
    actor_id = "report-review-reject-admin"
    current_id = "report-review-reject-current"
    pending_id = "report-review-reject-pending"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, actor_id)
    _insert_report(postgres_conn, current_id, theme_id, "v1", status="published")
    _insert_report(postgres_conn, pending_id, theme_id, "v2")
    postgres_conn.commit()

    result = report_store.reject_report_version(
        pending_id,
        expected_row_version=1,
        actor_user_id=actor_id,
        actor_role="admin",
        reason="  incomplete citations  ",
        request_id="reject-request-1",
        idempotency_key="reject-key-1",
        service=TEST_SERVICE,
    )

    assert result["status"] == "rejected"
    assert result["rejection_reason"] == "incomplete citations"
    assert result["rejected_by_user_id"] == actor_id
    assert postgres_conn.execute(
        "SELECT status FROM research.theme_research_report_version WHERE report_version_id = %s",
        (current_id,),
    ).fetchone()[0] == "published"
    admin = report_store.list_admin_report_versions(status="rejected", service=TEST_SERVICE)
    assert admin["total"] == 1
    assert admin["items"][0]["report_version_id"] == pending_id
    with pytest.raises(ThemeResearchReportError) as exc_info:
        report_store.get_approved_report_version(theme_id, pending_id, service=TEST_SERVICE)
    assert exc_info.value.code == "THEME_REPORT_NOT_FOUND"


@pytest.mark.parametrize(
    ("call", "expected_code"),
    [
        (
            lambda report_id, actor_id: report_store.publish_report_version(
                report_id,
                expected_row_version=1,
                actor_user_id=actor_id,
                actor_role="user",
                comment="",
                request_id="permission-request",
                idempotency_key="permission-key",
                service=TEST_SERVICE,
            ),
            "THEME_REPORT_ADMIN_REQUIRED",
        ),
        (
            lambda report_id, actor_id: report_store.publish_report_version(
                report_id,
                expected_row_version=1,
                actor_user_id="missing-review-actor",
                actor_role="admin",
                comment="",
                request_id="missing-actor-request",
                idempotency_key="missing-actor-key",
                service=TEST_SERVICE,
            ),
            "THEME_REPORT_ACTOR_NOT_FOUND",
        ),
    ],
)
def test_postgres_review_requires_admin_and_existing_actor_without_mutation(
    postgres_conn,
    call,
    expected_code,
) -> None:
    theme_id = "report-review-permission-theme"
    actor_id = "report-review-permission-admin"
    report_id = "report-review-permission-version"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, actor_id)
    _insert_report(postgres_conn, report_id, theme_id, "v1")
    postgres_conn.commit()

    with pytest.raises(ThemeResearchReportError) as exc_info:
        call(report_id, actor_id)

    assert exc_info.value.code == expected_code
    assert postgres_conn.execute(
        "SELECT status, row_version FROM research.theme_research_report_version WHERE report_version_id = %s",
        (report_id,),
    ).fetchone() == ("pending_review", 1)
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_review_event WHERE report_version_id = %s",
        (report_id,),
    ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("field_name", "overrides"),
    [
        ("expected_row_version", {"expected_row_version": 0}),
        ("actor_user_id", {"actor_user_id": " "}),
        ("request_id", {"request_id": ""}),
        ("idempotency_key", {"idempotency_key": ""}),
        ("comment", {"comment": "x" * 2_001}),
    ],
)
def test_publish_review_validates_inputs_before_database_access(
    monkeypatch,
    field_name,
    overrides,
) -> None:
    kwargs = {
        "expected_row_version": 1,
        "actor_user_id": "admin",
        "actor_role": "admin",
        "comment": "",
        "request_id": "request",
        "idempotency_key": "key",
        "service": "must-not-connect",
    }
    kwargs.update(overrides)
    monkeypatch.setattr(
        report_store,
        "connect",
        lambda service: pytest.fail("invalid input must not connect"),
    )

    with pytest.raises(ThemeResearchReportError) as exc_info:
        report_store.publish_report_version("report", **kwargs)

    assert exc_info.value.code == "THEME_REPORT_INPUT_INVALID"
    assert exc_info.value.details == {"fields": [field_name]}


@pytest.mark.parametrize("reason", [" ", "x" * 4_001])
def test_reject_review_requires_bounded_trimmed_reason(monkeypatch, reason) -> None:
    monkeypatch.setattr(
        report_store,
        "connect",
        lambda service: pytest.fail("invalid input must not connect"),
    )

    with pytest.raises(ThemeResearchReportError) as exc_info:
        report_store.reject_report_version(
            "report",
            expected_row_version=1,
            actor_user_id="admin",
            actor_role="admin",
            reason=reason,
            request_id="request",
            idempotency_key="key",
            service="must-not-connect",
        )

    assert exc_info.value.code == "THEME_REPORT_INPUT_INVALID"
    assert exc_info.value.details == {"fields": ["reason"]}


def test_postgres_review_enforces_state_version_and_missing_errors(postgres_conn) -> None:
    theme_id = "report-review-conflict-theme"
    actor_id = "report-review-conflict-admin"
    pending_id = "report-review-conflict-pending"
    published_id = "report-review-conflict-published"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, actor_id)
    _insert_report(postgres_conn, pending_id, theme_id, "v1")
    _insert_report(postgres_conn, published_id, theme_id, "v2", status="published")
    rejected_id = "report-review-conflict-rejected"
    archived_id = "report-review-conflict-archived"
    _insert_report(postgres_conn, rejected_id, theme_id, "v3", status="rejected")
    _insert_report(postgres_conn, archived_id, theme_id, "v4", status="archived")
    postgres_conn.commit()

    calls = [
        (
            pending_id,
            2,
            "stale-key",
            "THEME_REPORT_VERSION_CONFLICT",
        ),
        (
            published_id,
            1,
            "state-key",
            "THEME_REPORT_STATE_CONFLICT",
        ),
        (
            "missing-review-report",
            1,
            "missing-key",
            "THEME_REPORT_NOT_FOUND",
        ),
    ]
    for report_id, row_version, key, expected_code in calls:
        with pytest.raises(ThemeResearchReportError) as exc_info:
            report_store.reject_report_version(
                report_id,
                expected_row_version=row_version,
                actor_user_id=actor_id,
                actor_role="admin",
                reason="not approved",
                request_id=f"request-{key}",
                idempotency_key=key,
                service=TEST_SERVICE,
            )
        assert exc_info.value.code == expected_code

    for report_id in (published_id, rejected_id, archived_id):
        with pytest.raises(ThemeResearchReportError) as exc_info:
            report_store.publish_report_version(
                report_id,
                expected_row_version=1,
                actor_user_id=actor_id,
                actor_role="admin",
                comment="approved",
                request_id=f"publish-state-{report_id}",
                idempotency_key=f"publish-state-{report_id}",
                service=TEST_SERVICE,
            )
        assert exc_info.value.code == "THEME_REPORT_STATE_CONFLICT"


def test_postgres_review_idempotency_retries_and_rejects_key_reuse(postgres_conn) -> None:
    theme_id = "report-review-idempotent-theme"
    actor_id = "report-review-idempotent-admin"
    first_id = "report-review-idempotent-first"
    second_id = "report-review-idempotent-second"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, actor_id)
    _insert_report(postgres_conn, first_id, theme_id, "v1")
    _insert_report(postgres_conn, second_id, theme_id, "v2")
    postgres_conn.commit()
    kwargs = {
        "expected_row_version": 1,
        "actor_user_id": actor_id,
        "actor_role": "admin",
        "comment": "approved",
        "request_id": "idempotent-request",
        "idempotency_key": "idempotent-key",
        "service": TEST_SERVICE,
    }

    first = report_store.publish_report_version(first_id, **kwargs)
    retried = report_store.publish_report_version(first_id, **kwargs)

    assert retried == first
    assert postgres_conn.execute(
        "SELECT row_version FROM research.theme_research_report_version WHERE report_version_id = %s",
        (first_id,),
    ).fetchone()[0] == 2
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_review_event WHERE actor_user_id = %s AND idempotency_key = %s",
        (actor_id, "idempotent-key"),
    ).fetchone()[0] == 1

    with pytest.raises(ThemeResearchReportError) as target_conflict:
        report_store.publish_report_version(second_id, **kwargs)
    assert target_conflict.value.code == "THEME_REPORT_IDEMPOTENCY_CONFLICT"
    with pytest.raises(ThemeResearchReportError) as action_conflict:
        report_store.reject_report_version(
            first_id,
            expected_row_version=1,
            actor_user_id=actor_id,
            actor_role="admin",
            reason="reject instead",
            request_id="idempotent-request",
            idempotency_key="idempotent-key",
            service=TEST_SERVICE,
        )
    assert action_conflict.value.code == "THEME_REPORT_IDEMPOTENCY_CONFLICT"

    third_id = "report-review-idempotent-third"
    _insert_report(postgres_conn, third_id, theme_id, "v3")
    postgres_conn.commit()
    report_store.publish_report_version(
        third_id,
        expected_row_version=1,
        actor_user_id=actor_id,
        actor_role="admin",
        comment="new current",
        request_id="third-request",
        idempotency_key="third-key",
        service=TEST_SERVICE,
    )
    replayed_after_archive = report_store.publish_report_version(first_id, **kwargs)
    assert replayed_after_archive == first
    assert postgres_conn.execute(
        "SELECT status, row_version FROM research.theme_research_report_version WHERE report_version_id = %s",
        (first_id,),
    ).fetchone() == ("archived", 3)


def test_postgres_concurrent_review_has_one_stale_winner_and_consistent_retry(
    postgres_conn,
) -> None:
    theme_id = "report-review-concurrent-theme"
    actor_id = "report-review-concurrent-admin"
    report_id = "report-review-concurrent-version"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, actor_id)
    _insert_report(postgres_conn, report_id, theme_id, "v1")
    postgres_conn.commit()

    def publish(key: str):
        try:
            return report_store.publish_report_version(
                report_id,
                expected_row_version=1,
                actor_user_id=actor_id,
                actor_role="admin",
                comment="approved",
                request_id=f"request-{key}",
                idempotency_key=key,
                service=TEST_SERVICE,
            )
        except ThemeResearchReportError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, ("concurrent-a", "concurrent-b")))
    assert len([outcome for outcome in outcomes if isinstance(outcome, dict)]) == 1
    errors = [outcome for outcome in outcomes if isinstance(outcome, ThemeResearchReportError)]
    assert len(errors) == 1
    assert errors[0].code == "THEME_REPORT_STATE_CONFLICT"

    second_id = "report-review-concurrent-idempotent"
    _insert_report(postgres_conn, second_id, theme_id, "v2")
    postgres_conn.commit()
    with ThreadPoolExecutor(max_workers=2) as executor:
        retries = list(executor.map(lambda _: publish_same(second_id, actor_id), range(2)))
    assert retries[0] == retries[1]
    assert postgres_conn.execute(
        "SELECT count(*) FROM research.theme_research_report_review_event WHERE actor_user_id = %s AND idempotency_key = 'same-concurrent-key'",
        (actor_id,),
    ).fetchone()[0] == 1


def publish_same(report_id: str, actor_id: str):
    return report_store.publish_report_version(
        report_id,
        expected_row_version=1,
        actor_user_id=actor_id,
        actor_role="admin",
        comment="approved",
        request_id="same-concurrent-request",
        idempotency_key="same-concurrent-key",
        service=TEST_SERVICE,
    )


@pytest.mark.parametrize(
    ("constraint_name", "constraint_expression"),
    [
        ("ck_theme_report_fail_target_event", "request_id <> 'fail-target-event'"),
        ("ck_theme_report_fail_archive_event", "to_status <> 'archived'"),
    ],
)
def test_postgres_publish_event_failure_rolls_back_everything(
    postgres_conn,
    constraint_name,
    constraint_expression,
) -> None:
    from stock_research.theme_research_report_schema import apply_theme_research_report_schema

    theme_id = f"report-review-rollback-{constraint_name}"
    actor_id = f"report-review-admin-{constraint_name}"
    old_id = f"report-review-old-{constraint_name}"
    new_id = f"report-review-new-{constraint_name}"
    _insert_theme(postgres_conn, theme_id)
    _insert_user(postgres_conn, actor_id)
    _insert_report(postgres_conn, old_id, theme_id, "v1", status="published")
    _insert_report(postgres_conn, new_id, theme_id, "v2")
    postgres_conn.execute(
        f"""
        ALTER TABLE research.theme_research_report_review_event
        ADD CONSTRAINT {constraint_name} CHECK ({constraint_expression})
        """
    )
    postgres_conn.commit()

    try:
        with pytest.raises(ThemeResearchReportError) as exc_info:
            report_store.publish_report_version(
                new_id,
                expected_row_version=1,
                actor_user_id=actor_id,
                actor_role="admin",
                comment="approved",
                request_id="fail-target-event",
                idempotency_key=f"rollback-{constraint_name}",
                service=TEST_SERVICE,
            )
        assert exc_info.value.code == "THEME_REPORT_STORE_UNAVAILABLE"
        assert postgres_conn.execute(
            "SELECT report_version_id, status, row_version FROM research.theme_research_report_version WHERE report_version_id IN (%s, %s) ORDER BY report_version_id",
            (old_id, new_id),
        ).fetchall() == sorted(
            [(old_id, "published", 1), (new_id, "pending_review", 1)]
        )
        assert postgres_conn.execute(
            "SELECT count(*) FROM research.theme_research_report_review_event WHERE report_version_id IN (%s, %s)",
            (old_id, new_id),
        ).fetchone()[0] == 0
    finally:
        postgres_conn.rollback()
        cleanup = psycopg.connect(f"service={TEST_SERVICE}")
        try:
            cleanup.execute(
                f"ALTER TABLE research.theme_research_report_review_event DROP CONSTRAINT IF EXISTS {constraint_name}"
            )
            cleanup.commit()
        finally:
            cleanup.close()
        apply_theme_research_report_schema(service=TEST_SERVICE)


def test_postgres_admin_and_approved_read_models_validate_scope(postgres_conn) -> None:
    theme_id = "report-review-read-theme"
    _insert_theme(postgres_conn, theme_id)
    _insert_report(
        postgres_conn,
        "report-review-read-newer",
        theme_id,
        "v2",
        generated_at="2026-07-31T10:00:00Z",
    )
    _insert_report(
        postgres_conn,
        "report-review-read-older",
        theme_id,
        "v1",
        generated_at="2026-07-30T10:00:00Z",
    )
    postgres_conn.commit()

    pending = report_store.list_admin_report_versions(service=TEST_SERVICE)
    assert [item["report_version_id"] for item in pending["items"]] == [
        "report-review-read-newer",
        "report-review-read-older",
    ]
    with pytest.raises(ThemeResearchReportError) as status_error:
        report_store.list_admin_report_versions(status="published", service=TEST_SERVICE)
    assert status_error.value.code == "THEME_REPORT_INPUT_INVALID"
    with pytest.raises(ThemeResearchReportError) as theme_error:
        report_store.list_approved_report_versions(
            "missing-report-read-theme",
            service=TEST_SERVICE,
        )
    assert theme_error.value.code == "THEME_REPORT_THEME_NOT_FOUND"


def test_postgres_safe_read_models_sanitize_nested_internal_metadata(
    postgres_conn,
) -> None:
    theme_id = "report-review-safe-metadata-theme"
    report_id = "report-review-safe-metadata-version"
    pending_id = "report-review-safe-metadata-pending"
    unsafe_metadata = {
        "source": {"kind": "production", "tags": ["primary"]},
        "artifact": {
            "path": "/srv/private/report.md",
            "checksum": "a" * 64,
        },
        "generator": {"diagnostics": {"trace": "private stack"}},
        "hidden_digest": "b" * 64,
        "hidden_location": "theme/v1/report.md",
        "artifact_alias": {"file": "report.md"},
        "debug": "private diagnostics",
        "hash": "sha256:private",
    }
    _insert_theme(postgres_conn, theme_id)
    _insert_report(
        postgres_conn,
        report_id,
        theme_id,
        "v1",
        status="published",
        metadata=unsafe_metadata,
    )
    _insert_report(
        postgres_conn,
        pending_id,
        theme_id,
        "v2",
        metadata=unsafe_metadata,
    )
    postgres_conn.commit()

    approved = report_store.get_approved_report_version(
        theme_id,
        report_id,
        service=TEST_SERVICE,
    )
    admin_safe = report_store.list_admin_report_versions(
        status="pending_review",
        service=TEST_SERVICE,
    )
    admin_internal = report_store.get_admin_report_version(
        report_id,
        service=TEST_SERVICE,
    )

    assert approved["metadata"] == {}
    pending_safe = next(
        item
        for item in admin_safe["items"]
        if item["report_version_id"] == pending_id
    )
    assert pending_safe["metadata"] == {}
    assert admin_internal["metadata"] == unsafe_metadata


def test_review_read_and_mutation_map_database_errors_without_leaking(monkeypatch) -> None:
    database_error = psycopg.OperationalError("secret review database diagnostics")

    @contextmanager
    def unavailable(service):
        raise database_error
        yield

    monkeypatch.setattr(report_store, "connect", unavailable)
    calls = [
        lambda: report_store.list_admin_report_versions(service="unavailable"),
        lambda: report_store.get_admin_report_version("report", service="unavailable"),
        lambda: report_store.list_approved_report_versions("theme", service="unavailable"),
        lambda: report_store.publish_report_version(
            "report",
            expected_row_version=1,
            actor_user_id="admin",
            actor_role="admin",
            comment="",
            request_id="request",
            idempotency_key="key",
            service="unavailable",
        ),
    ]
    for call in calls:
        with pytest.raises(ThemeResearchReportError) as exc_info:
            call()
        assert exc_info.value.code == "THEME_REPORT_STORE_UNAVAILABLE"
        assert "secret" not in str(exc_info.value).lower()
        assert exc_info.value.__cause__ is database_error
