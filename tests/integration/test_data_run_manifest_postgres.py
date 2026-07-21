from __future__ import annotations

import os
import re
from uuid import uuid4

import psycopg
import pytest

from stock_research.data_run_manifest import (
    CREATE_DATA_RUN_MANIFEST_SQL,
    apply_data_run_manifest_schema,
)


pytestmark = pytest.mark.skipif(
    os.getenv("STRATEGY_PUBLICATION_POSTGRES_TEST") != "1"
    or not os.getenv("STRATEGY_PUBLICATION_POSTGRES_TEST_SERVICE"),
    reason=(
        "set STRATEGY_PUBLICATION_POSTGRES_TEST=1 and "
        "STRATEGY_PUBLICATION_POSTGRES_TEST_SERVICE to a dedicated test database"
    ),
)

TEST_SERVICE = os.getenv("STRATEGY_PUBLICATION_POSTGRES_TEST_SERVICE", "")


def _connect(*, autocommit: bool = False):
    connection = psycopg.connect(f"service={TEST_SERVICE}", autocommit=autocommit)
    database_name = connection.execute("SELECT current_database()").fetchone()[0]
    if not database_name.endswith("_test"):
        connection.close()
        pytest.fail(f"refusing to run integration tests against {database_name}")
    return connection


def _legacy_manifest_schema_sql() -> str:
    create_only = CREATE_DATA_RUN_MANIFEST_SQL.split("DO $$", maxsplit=1)[0]
    return re.sub(
        r"status text NOT NULL CHECK \(.*?\),\n    started_at",
        "status text NOT NULL CHECK "
        "(status IN ('success', 'partial', 'skipped', 'failed', 'unavailable')),\n"
        "    started_at",
        create_only,
        count=1,
        flags=re.DOTALL,
    )


def _insert_manifest_status(
    connection,
    status: str,
    *,
    module: str = "migration_probe",
    source: str = "migration_probe",
) -> None:
    unique_id = uuid4().hex
    connection.execute(
        """
        INSERT INTO ops.data_run_manifest (
            manifest_id, run_id, run_date, trade_date, module, source, tier, status
        ) VALUES (
            %s, %s, current_date, current_date, %s, %s, 'tier1', %s
        )
        """,
        (
            f"manifest-migration-{unique_id}",
            f"manifest-migration-{unique_id}",
            module,
            source,
            status,
        ),
    )


def test_apply_schema_migrates_legacy_status_check_and_preserves_validation():
    connection = _connect(autocommit=True)
    try:
        connection.execute("DROP SCHEMA IF EXISTS ops CASCADE")
        connection.execute(_legacy_manifest_schema_sql())
        connection.execute(
            """
            ALTER TABLE ops.data_run_manifest
            RENAME CONSTRAINT data_run_manifest_status_check
            TO legacy_manifest_state_allowlist
            """
        )
        legacy_constraint = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'ops.data_run_manifest'::regclass
              AND conname = 'legacy_manifest_state_allowlist'
            """
        ).fetchone()[0]
        assert "degraded" not in legacy_constraint
    finally:
        connection.close()

    apply_data_run_manifest_schema(service=TEST_SERVICE)

    connection = _connect(autocommit=True)
    try:
        check_constraints = connection.execute(
            """
            SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'ops.data_run_manifest'::regclass
              AND contype = 'c'
            ORDER BY conname
            """
        ).fetchall()
        status_constraints = [
            (name, definition)
            for name, definition in check_constraints
            if "status" in definition
        ]
        assert len(status_constraints) == 1
        assert status_constraints[0][0] == "data_run_manifest_status_check"
        assert "degraded" in status_constraints[0][1]
        assert "dashboard_browser_acceptance" in status_constraints[0][1]
        assert "eod_browser_acceptance" in status_constraints[0][1]
        assert any("tier" in definition for _, definition in check_constraints)
        assert all(name != "legacy_manifest_state_allowlist" for name, _ in check_constraints)
        for status in (
            "success",
            "partial",
            "skipped",
            "failed",
            "unavailable",
        ):
            _insert_manifest_status(connection, status)
        _insert_manifest_status(
            connection,
            "degraded",
            module="dashboard_browser_acceptance",
            source="eod_browser_acceptance",
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_manifest_status(connection, "degraded")
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_manifest_status(connection, "invalid")
    finally:
        connection.close()
