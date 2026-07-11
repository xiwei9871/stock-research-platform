from __future__ import annotations

import os

import psycopg
import pytest

from stock_research.config import SETTINGS
from stock_research.theme_research_db_schema import (
    THEME_RESEARCH_SCHEMA_SQL,
    inspect_theme_research_schema,
)


pytestmark = pytest.mark.skipif(
    os.getenv("THEME_RESEARCH_POSTGRES_TEST") != "1",
    reason="set THEME_RESEARCH_POSTGRES_TEST=1 for configured PostgreSQL integration tests",
)


@pytest.fixture
def conn():
    connection = psycopg.connect(f"service={SETTINGS.research_service}")
    try:
        connection.execute(THEME_RESEARCH_SCHEMA_SQL)
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _insert_theme(conn, theme_id: str) -> None:
    conn.execute(
        """
        INSERT INTO research.theme_research_theme (
            theme_id, theme_name, theme_type, summary, status, created_from,
            last_updated, content_sha256, created_by, updated_by
        ) VALUES (%s, %s, 'other', 'test', 'draft', 'manual', '2026-07-11', %s, 'test', 'test')
        """,
        (theme_id, theme_id, f"sha-{theme_id}"),
    )


def _insert_source(
    conn,
    source_id: str,
    *,
    reliability: str = "S1",
    review_status: str = "accepted",
) -> None:
    conn.execute(
        """
        INSERT INTO research.theme_research_source_item (
            source_id, source_type, title, publisher, publish_date, url_or_ref,
            access_level, reliability_level, review_status, created_by, updated_by
        ) VALUES (%s, 'official_article', %s, 'publisher', '2026-07-11', %s,
                  'public', %s, %s, 'test', 'test')
        """,
        (source_id, source_id, f"local:{source_id}", reliability, review_status),
    )


def _insert_node(conn, node_id: str, theme_id: str, *, parent_node_id: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO research.theme_research_node (
            node_id, theme_id, parent_node_id, node_name, node_type, description,
            value_capture_score, bottleneck_score, localization_gap_score,
            supply_tightness_score, evidence_strength, node_review_status,
            created_by, updated_by
        ) VALUES (%s, %s, %s, %s, 'core_component', 'test', 1, 1, 1, 1, 1,
                  'draft', 'test', 'test')
        """,
        (node_id, theme_id, parent_node_id, node_id),
    )


def test_postgres_rejects_accepted_s4_source(conn) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_source(conn, "source-s4", reliability="S4", review_status="accepted")


def test_postgres_revalidates_reviewed_claim_when_source_changes(conn) -> None:
    _insert_theme(conn, "theme-claim")
    _insert_source(conn, "source-claim")
    conn.execute(
        """
        INSERT INTO research.theme_research_content_claim (
            claim_id, theme_id, source_id, claim_text, claim_type, confidence,
            evidence_status, platform_use_status, created_by, updated_by
        ) VALUES ('claim-1', 'theme-claim', 'source-claim', 'claim', 'bottleneck', 0.8,
                  'partially_verified', 'reviewed', 'test', 'test')
        """
    )
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")

    with pytest.raises(psycopg.errors.RaiseException, match="REVIEWED_CLAIM_USES_REJECTED_SOURCE"):
        conn.execute(
            "UPDATE research.theme_research_source_item SET review_status = 'rejected' WHERE source_id = 'source-claim'"
        )


def test_postgres_revalidates_reviewed_claim_when_supporting_link_is_deleted(conn) -> None:
    _insert_theme(conn, "theme-support")
    _insert_source(conn, "source-primary", reliability="S4", review_status="lead_only")
    _insert_source(conn, "source-support")
    conn.execute(
        """
        INSERT INTO research.theme_research_content_claim (
            claim_id, theme_id, source_id, claim_text, claim_type, confidence,
            evidence_status, platform_use_status, created_by, updated_by
        ) VALUES ('claim-support', 'theme-support', 'source-primary', 'claim', 'bottleneck', 0.8,
                  'partially_verified', 'draft', 'test', 'test')
        """
    )
    conn.execute(
        "INSERT INTO research.theme_research_claim_source (claim_id, source_id) VALUES ('claim-support', 'source-support')"
    )
    conn.execute(
        "UPDATE research.theme_research_content_claim SET platform_use_status = 'reviewed' WHERE claim_id = 'claim-support'"
    )
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")

    with pytest.raises(psycopg.errors.RaiseException, match="REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE"):
        conn.execute(
            "DELETE FROM research.theme_research_claim_source WHERE claim_id = 'claim-support' AND source_id = 'source-support'"
        )


def test_postgres_rejects_cross_theme_parent(conn) -> None:
    _insert_theme(conn, "theme-parent-a")
    _insert_theme(conn, "theme-parent-b")
    _insert_node(conn, "parent-a", "theme-parent-a")
    _insert_node(conn, "child-b", "theme-parent-b", parent_node_id="parent-a")

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_postgres_rejects_orphan_polymorphic_evidence(conn) -> None:
    _insert_theme(conn, "theme-evidence")
    _insert_node(conn, "node-evidence", "theme-evidence")
    conn.execute(
        """
        INSERT INTO research.theme_research_value_assessment (
            assessment_id, node_id, value_basis, assessment_text, rank, uncertainty,
            created_by, updated_by
        ) VALUES ('assessment-1', 'node-evidence', 'scarcity', 'test', 1, 'medium', 'test', 'test')
        """
    )
    conn.execute(
        """
        INSERT INTO research.theme_research_assessment_evidence (
            assessment_id, evidence_type, evidence_id
        ) VALUES ('assessment-1', 'source', 'missing-source')
        """
    )

    with pytest.raises(psycopg.errors.RaiseException, match="ASSESSMENT_EVIDENCE_NOT_FOUND"):
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_postgres_rejects_inactive_theme_with_active_children(conn) -> None:
    _insert_theme(conn, "theme-active")
    _insert_node(conn, "node-active", "theme-active")
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    conn.execute("SET CONSTRAINTS ALL DEFERRED")
    conn.execute(
        "UPDATE research.theme_research_theme SET is_active = false WHERE theme_id = 'theme-active'"
    )

    with pytest.raises(psycopg.errors.RaiseException, match="INACTIVE_THEME_HAS_ACTIVE_CHILDREN"):
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_postgres_rejects_version_decrease_and_committed_change_mutation(conn) -> None:
    _insert_theme(conn, "theme-version")
    conn.execute(
        "UPDATE research.theme_research_theme SET row_version = 2, theme_version = 2 WHERE theme_id = 'theme-version'"
    )
    with pytest.raises(psycopg.errors.RaiseException, match="THEME_RESEARCH_ROW_VERSION_DECREASE"):
        conn.execute(
            "UPDATE research.theme_research_theme SET row_version = 1 WHERE theme_id = 'theme-version'"
        )


def test_postgres_rejects_snapshot_truncate(conn) -> None:
    with pytest.raises(psycopg.errors.RaiseException, match="theme_research_snapshot is append-only"):
        conn.execute("TRUNCATE TABLE research.theme_research_snapshot")


def test_schema_inspection_detects_removed_constraint(conn) -> None:
    conn.execute(
        "ALTER TABLE research.theme_research_source_item DROP CONSTRAINT ck_theme_research_source_s4_not_accepted"
    )

    inspection = inspect_theme_research_schema(conn.cursor())

    assert inspection["status"] == "drifted"
    assert "constraint:ck_theme_research_source_s4_not_accepted" in inspection["missing"]


def test_schema_inspection_detects_removed_ordinary_check(conn) -> None:
    constraint_name = conn.execute(
        """
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'research.theme_research_content_claim'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%confidence%'
        """
    ).fetchone()[0]
    conn.execute(
        f"ALTER TABLE research.theme_research_content_claim DROP CONSTRAINT {constraint_name}"
    )

    inspection = inspect_theme_research_schema(conn.cursor())

    assert inspection["status"] == "drifted"
    assert inspection["catalog_sha256_matches"] is False


def test_schema_inspection_detects_removed_index(conn) -> None:
    conn.execute("DROP INDEX research.idx_theme_research_claim_theme")

    inspection = inspect_theme_research_schema(conn.cursor())

    assert inspection["status"] == "drifted"
    assert inspection["catalog_sha256_matches"] is False


def test_schema_inspection_detects_removed_non_theme_version_trigger(conn) -> None:
    conn.execute(
        "DROP TRIGGER trg_theme_research_source_version_monotonic ON research.theme_research_source_item"
    )

    inspection = inspect_theme_research_schema(conn.cursor())

    assert inspection["status"] == "drifted"
    assert inspection["catalog_sha256_matches"] is False


def test_schema_inspection_detects_replaced_trigger_function(conn) -> None:
    conn.execute(
        """
        CREATE OR REPLACE FUNCTION research.theme_research_check_mapping_evidence()
        RETURNS trigger AS $$ BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql
        """
    )

    inspection = inspect_theme_research_schema(conn.cursor())

    assert inspection["status"] == "drifted"
    assert inspection["catalog_sha256_matches"] is False


def test_postgres_rejects_active_claim_with_inactive_source(conn) -> None:
    _insert_theme(conn, "theme-inactive-source")
    _insert_source(conn, "source-inactive")
    conn.execute(
        "UPDATE research.theme_research_source_item SET is_active = false WHERE source_id = 'source-inactive'"
    )
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    conn.execute("SET CONSTRAINTS ALL DEFERRED")
    conn.execute(
        """
        INSERT INTO research.theme_research_content_claim (
            claim_id, theme_id, source_id, claim_text, claim_type, confidence,
            evidence_status, platform_use_status, created_by, updated_by
        ) VALUES ('claim-inactive-source', 'theme-inactive-source', 'source-inactive', 'claim',
                  'bottleneck', 0.5, 'unverified', 'draft', 'test', 'test')
        """
    )

    with pytest.raises(psycopg.errors.RaiseException, match="ACTIVE_CLAIM_REQUIRES_ACTIVE_SOURCE"):
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_postgres_rejects_node_deactivation_with_active_dependents(conn) -> None:
    _insert_theme(conn, "theme-node-dependent")
    _insert_node(conn, "node-dependent", "theme-node-dependent")
    conn.execute(
        """
        INSERT INTO research.theme_research_value_assessment (
            assessment_id, node_id, value_basis, assessment_text, rank, uncertainty,
            created_by, updated_by
        ) VALUES ('assessment-dependent', 'node-dependent', 'scarcity', 'test', 1, 'medium', 'test', 'test')
        """
    )
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    conn.execute("SET CONSTRAINTS ALL DEFERRED")
    conn.execute(
        "UPDATE research.theme_research_node SET is_active = false WHERE node_id = 'node-dependent'"
    )

    with pytest.raises(psycopg.errors.RaiseException, match="INACTIVE_NODE_HAS_ACTIVE_DEPENDENTS"):
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_postgres_rejects_source_deactivation_with_active_evidence(conn) -> None:
    _insert_theme(conn, "theme-source-dependent")
    _insert_source(conn, "source-dependent")
    conn.execute(
        """
        INSERT INTO research.theme_research_mapping_evidence_item (
            evidence_id, source_id, evidence_type, excerpt_locator, evidence_summary,
            created_by, updated_by
        ) VALUES ('mapping-evidence-dependent', 'source-dependent', 'product_relationship',
                  'page 1', 'test', 'test', 'test')
        """
    )
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    conn.execute("SET CONSTRAINTS ALL DEFERRED")
    conn.execute(
        "UPDATE research.theme_research_source_item SET is_active = false WHERE source_id = 'source-dependent'"
    )

    with pytest.raises(psycopg.errors.RaiseException, match="INACTIVE_SOURCE_HAS_ACTIVE_DEPENDENTS"):
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_postgres_rejects_mapping_evidence_deactivation_with_active_link(conn) -> None:
    _insert_theme(conn, "theme-mapping-dependent")
    _insert_node(conn, "node-mapping-dependent", "theme-mapping-dependent")
    _insert_source(conn, "source-mapping-dependent")
    conn.execute(
        """
        INSERT INTO research.theme_research_company_mapping (
            mapping_id, theme_id, node_id, company_code, company_name, market,
            mapping_type, confidence, revenue_relevance, bottleneck_relevance,
            created_by, updated_by
        ) VALUES ('mapping-dependent', 'theme-mapping-dependent', 'node-mapping-dependent',
                  '000001.SZ', 'test', 'CN', 'direct_product', 0.5, 'low', 'low', 'test', 'test')
        """
    )
    conn.execute(
        """
        INSERT INTO research.theme_research_mapping_evidence_item (
            evidence_id, source_id, evidence_type, excerpt_locator, evidence_summary,
            created_by, updated_by
        ) VALUES ('mapping-evidence-link', 'source-mapping-dependent', 'product_relationship',
                  'page 1', 'test', 'test', 'test')
        """
    )
    conn.execute(
        """
        INSERT INTO research.theme_research_company_mapping_evidence (
            mapping_id, evidence_type, evidence_id
        ) VALUES ('mapping-dependent', 'mapping_evidence_item', 'mapping-evidence-link')
        """
    )
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    conn.execute("SET CONSTRAINTS ALL DEFERRED")
    conn.execute(
        "UPDATE research.theme_research_mapping_evidence_item SET is_active = false "
        "WHERE evidence_id = 'mapping-evidence-link'"
    )

    with pytest.raises(psycopg.errors.RaiseException, match="INACTIVE_EVIDENCE_HAS_ACTIVE_DEPENDENTS"):
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_runtime_role_cannot_mutate_history_or_disable_triggers(conn) -> None:
    conn.execute("SET LOCAL ROLE theme_research_runtime")

    privileges = conn.execute(
        """
        SELECT
            has_table_privilege(current_user, 'research.theme_research_snapshot', 'UPDATE'),
            has_table_privilege(current_user, 'research.theme_research_snapshot', 'TRUNCATE'),
            has_table_privilege(current_user, 'research.theme_research_change_set', 'TRUNCATE')
        """
    ).fetchone()
    assert privileges == (False, False, False)

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(
            "ALTER TABLE research.theme_research_snapshot DISABLE TRIGGER trg_theme_research_snapshot_append_only"
        )


def test_runtime_login_is_constrained_without_set_role() -> None:
    runtime = psycopg.connect(f"service={SETTINGS.theme_research_runtime_service}")
    try:
        row = runtime.execute(
            """
            SELECT
                current_user,
                r.rolsuper,
                r.rolcreaterole,
                pg_has_role(current_user, 'theme_research_runtime', 'member'),
                pg_has_role(current_user, 'theme_research_owner', 'member'),
                has_table_privilege(current_user, 'research.theme_research_snapshot', 'UPDATE'),
                has_table_privilege(current_user, 'research.theme_research_snapshot', 'TRUNCATE'),
                has_schema_privilege(current_user, 'research', 'CREATE')
            FROM pg_roles r
            WHERE r.rolname = current_user
            """
        ).fetchone()
        assert row == (
            "theme_research_app",
            False,
            False,
            True,
            False,
            False,
            False,
            False,
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute(
                "ALTER TABLE research.theme_research_snapshot "
                "DISABLE TRIGGER trg_theme_research_snapshot_append_only"
            )
    finally:
        runtime.rollback()
        runtime.close()
