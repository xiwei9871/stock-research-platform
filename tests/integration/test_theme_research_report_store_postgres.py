from __future__ import annotations

import json
import os
from contextlib import contextmanager

import psycopg
import pytest

from stock_research.config import Settings


TEST_SERVICE = os.getenv("THEME_RESEARCH_POSTGRES_TEST_SERVICE", "")
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

    schema.apply_theme_research_report_schema(service="test_service")

    assert calls == [
        ("service", "test_service"),
        ("execute", schema.THEME_RESEARCH_REPORT_SCHEMA_SQL),
        ("commit", "test_service"),
    ]


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
