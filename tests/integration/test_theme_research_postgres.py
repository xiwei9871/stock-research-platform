from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager

import psycopg
import pytest
from psycopg.rows import dict_row

from stock_research.config import SETTINGS
from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_db_schema import THEME_RESEARCH_SCHEMA_SQL
from stock_research.theme_research_import import normalize_artifact_package, semantic_diff
from stock_research import theme_research_store as store


pytestmark = pytest.mark.skipif(
    os.getenv("THEME_RESEARCH_POSTGRES_TEST") != "1"
    or not os.getenv("THEME_RESEARCH_POSTGRES_TEST_SERVICE"),
    reason="set THEME_RESEARCH_POSTGRES_TEST=1 and dedicated test services",
)

TEST_MIGRATION_SERVICE = os.getenv("THEME_RESEARCH_POSTGRES_TEST_SERVICE", "")


@pytest.fixture
def conn():
    connection = psycopg.connect(
        f"service={TEST_MIGRATION_SERVICE}",
        row_factory=dict_row,
    )
    try:
        database_name = connection.execute("SELECT current_database()").fetchone()["current_database"]
        if not database_name.endswith("_test"):
            pytest.fail(f"refusing to run integration tests against {database_name}")
        connection.execute(THEME_RESEARCH_SCHEMA_SQL)
        connection.execute("SET LOCAL session_replication_role = replica")
        connection.execute(
            """
            TRUNCATE TABLE
                research.theme_research_change_set,
                research.theme_research_theme,
                research.theme_research_node,
                research.theme_research_source_item,
                research.theme_research_theme_source,
                research.theme_research_content_claim,
                research.theme_research_claim_source,
                research.theme_research_claim_node,
                research.theme_research_value_assessment,
                research.theme_research_assessment_evidence,
                research.theme_research_company_mapping,
                research.theme_research_mapping_evidence_item,
                research.theme_research_company_mapping_evidence,
                research.theme_research_review_event,
                research.theme_research_object_revision,
                research.theme_research_import_run,
                research.theme_research_snapshot
            CASCADE
            """
        )
        connection.execute(
            """
            UPDATE research.theme_research_store_state
            SET generation = 0, package_sha256 = '', artifact_version = '',
                updated_at = now(), updated_by = 'integration-test'
            WHERE state_id = true
            """
        )
        connection.execute("SET LOCAL session_replication_role = origin")
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def store_connection(monkeypatch, conn):
    conn.execute("SET LOCAL ROLE theme_research_app")
    class CursorProxy:
        def __init__(self, cursor):
            self.cursor = cursor

        def __enter__(self):
            self.cursor.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.cursor.__exit__(exc_type, exc, tb)

        def execute(self, sql, params=None):
            if sql == "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE":
                return self
            return self.cursor.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    class ConnectionProxy:
        def cursor(self):
            return CursorProxy(conn.cursor())

    @contextmanager
    def use_connection(service):
        yield ConnectionProxy()

    monkeypatch.setattr(store, "connect", use_connection)
    return conn


def test_bootstrap_current_artifacts_is_transactional_and_idempotent(
    store_connection, tmp_path
) -> None:
    package = normalize_artifact_package()

    first = store.bootstrap_package(
        package,
        actor_user_id="admin-integration",
        actor_role="admin",
        expected_generation=0,
        idempotency_key="bootstrap-integration-1",
        service="integration",
    )

    assert first["status"] == "committed"
    assert first["resulting_generation"] == 1
    assert first["object_counts"]["themes"] == len(package.themes)
    assert first["object_counts"]["nodes"] == len(package.nodes)
    database = store.load_database_package(service="integration")
    parity = semantic_diff(database, package)
    changed = {
        family: details["update"]
        for family, details in parity["families"].items()
        if details["update"]
    }
    if parity["has_changes"]:
        source_id = changed.get("sources", [None])[0]
        mapping_id = changed.get("company_mappings", [None])[0]
        details = {
            "changed": changed,
            "source_db": next((row for row in database.sources if row["source_id"] == source_id), None),
            "source_artifact": next((row for row in package.sources if row["source_id"] == source_id), None),
            "mapping_db": next((row for row in database.company_mappings if row["mapping_id"] == mapping_id), None),
            "mapping_artifact": next((row for row in package.company_mappings if row["mapping_id"] == mapping_id), None),
        }
        pytest.fail(str(details))

    replay = store.bootstrap_package(
        package,
        actor_user_id="admin-integration",
        actor_role="admin",
        expected_generation=0,
        idempotency_key="bootstrap-integration-1",
        service="integration",
    )
    assert replay == first

    no_changes = store.bootstrap_package(
        package,
        actor_user_id="admin-integration",
        actor_role="admin",
        expected_generation=1,
        idempotency_key="bootstrap-integration-2",
        service="integration",
    )
    assert no_changes["status"] == "no_changes"
    assert no_changes["resulting_generation"] == 1
    persisted_no_change = store_connection.execute(
        """
        SELECT status FROM research.theme_research_change_set
        WHERE actor_user_id = 'admin-integration'
          AND idempotency_key = 'bootstrap-integration-2'
        """
    ).fetchone()
    assert persisted_no_change["status"] == "committed"

    review = store.review_source(
        source_id="ai_power_video_claim_lead",
        to_status="needs_full_text",
        expected_row_version=1,
        actor_user_id="reviewer-integration",
        actor_role="user",
        comment="Request the full source before further use.",
        request_id="request-review-1",
        idempotency_key="review-source-1",
        service="integration",
    )
    assert review["status"] == "reviewed"
    assert review["row_version"] == 2
    assert review["theme_versions"]["ai_power_value_capture_v1"] == 2
    assert review["generation"] == 1
    assert review["resulting_generation"] == 2
    with pytest.raises(ThemeResearchDomainError) as reused_key:
        store.review_source(
            source_id="ai_power_video_claim_lead",
            to_status="rejected",
            expected_row_version=2,
            actor_user_id="reviewer-integration",
            actor_role="user",
            comment="Different request with reused key.",
            request_id="request-review-reused",
            idempotency_key="review-source-1",
            service="integration",
        )
    assert reused_key.value.code == "THEME_RESEARCH_IDEMPOTENCY_KEY_REUSED"
    with pytest.raises(ThemeResearchDomainError) as stale_generation:
        store.bootstrap_package(
            package,
            actor_user_id="admin-integration",
            actor_role="admin",
            expected_generation=1,
            idempotency_key="bootstrap-after-review-stale",
            service="integration",
        )
    assert stale_generation.value.code == "THEME_RESEARCH_GENERATION_CONFLICT"
    history = store.list_review_history(
        object_type="source",
        object_id="ai_power_video_claim_lead",
        service="integration",
    )
    assert history["total"] == 1
    snapshots = store.list_snapshots(
        theme_id="ai_power_value_capture_v1",
        service="integration",
    )
    assert {row["snapshot_type"] for row in snapshots["items"]} >= {
        "import",
        "pre_change",
        "post_change",
    }
    import_snapshot_id = next(
        row["snapshot_id"]
        for row in snapshots["items"]
        if row["snapshot_type"] == "import"
    )

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        store.review_source(
            source_id="ai_power_video_claim_lead",
            to_status="rejected",
            expected_row_version=1,
            actor_user_id="reviewer-integration",
            actor_role="user",
            comment="Stale review attempt.",
            request_id="request-review-stale",
            idempotency_key="review-source-stale",
            service="integration",
        )
    assert exc_info.value.code == "THEME_RESEARCH_VERSION_CONFLICT"

    rollback = store.rollback_theme(
        theme_id="ai_power_value_capture_v1",
        snapshot_id=import_snapshot_id,
        expected_theme_version=2,
        actor_user_id="admin-integration",
        actor_role="admin",
        comment="Integration rollback drill.",
        idempotency_key="rollback-integration-1",
        request_id="request-rollback-1",
        service="integration",
    )
    assert rollback["status"] == "rolled_back"
    assert rollback["theme_version"] == 3
    assert rollback["generation"] == 2
    assert rollback["resulting_generation"] == 3
    restored = store.load_database_package(service="integration")
    restored_source = next(
        row for row in restored.sources if row["source_id"] == "ai_power_video_claim_lead"
    )
    assert restored_source["review_status"] == "lead_only"

    exported = store.export_theme(
        "ai_power_value_capture_v1",
        output_dir=tmp_path,
        actor_user_id="admin-integration",
        actor_role="admin",
        idempotency_key="export-integration-1",
        service="integration",
    )
    assert exported["status"] == "exported"
    export_path = tmp_path / "ai_power_value_capture_v1.json"
    assert export_path.exists()
    assert exported["payload_sha256"] == hashlib.sha256(export_path.read_bytes()).hexdigest()
    export_path.unlink()
    replayed_export = store.export_theme(
        "ai_power_value_capture_v1",
        output_dir=tmp_path,
        actor_user_id="admin-integration",
        actor_role="admin",
        idempotency_key="export-integration-1",
        service="integration",
    )
    assert replayed_export["snapshot_id"] == exported["snapshot_id"]
    assert export_path.exists()


def test_bootstrap_rejects_generation_conflict(store_connection) -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        store.bootstrap_package(
            normalize_artifact_package(),
            actor_user_id="admin-integration",
            actor_role="admin",
            expected_generation=3,
            idempotency_key="bootstrap-conflict",
            service="integration",
        )

    assert exc_info.value.code == "THEME_RESEARCH_GENERATION_CONFLICT"
    assert exc_info.value.details["current_generation"] == 0


def test_partial_import_changes_only_affected_theme_and_object_versions(
    store_connection,
) -> None:
    package = normalize_artifact_package()
    store.bootstrap_package(
        package,
        actor_user_id="admin-integration",
        actor_role="admin",
        expected_generation=0,
        idempotency_key="bootstrap-version-base",
        service="integration",
    )
    changed_node = dict(package.nodes[0])
    changed_node["description"] = "updated in integration test"
    changed_theme_id = changed_node["theme_id"]
    changed_package = package.__class__.build(
        artifact_version=package.artifact_version,
        themes=package.themes,
        nodes=(changed_node, *package.nodes[1:]),
        sources=package.sources,
        theme_sources=package.theme_sources,
        claims=package.claims,
        claim_sources=package.claim_sources,
        claim_nodes=package.claim_nodes,
        assessments=package.assessments,
        assessment_evidence=package.assessment_evidence,
        company_mappings=package.company_mappings,
        mapping_evidence_items=package.mapping_evidence_items,
        company_mapping_evidence=package.company_mapping_evidence,
    )

    result = store.bootstrap_package(
        changed_package,
        actor_user_id="admin-integration",
        actor_role="admin",
        expected_generation=1,
        idempotency_key="bootstrap-version-change",
        service="integration",
    )

    assert result["theme_versions"] == {changed_theme_id: 2}
    themes = {
        row["theme_id"]: (row["theme_version"], row["row_version"])
        for row in store_connection.execute(
            "SELECT theme_id, theme_version, row_version FROM research.theme_research_theme"
        ).fetchall()
    }
    assert themes[changed_theme_id] == (2, 2)
    unchanged_theme_id = next(
        row["theme_id"] for row in package.themes if row["theme_id"] != changed_theme_id
    )
    assert themes[unchanged_theme_id] == (1, 1)
    nodes = {
        row["node_id"]: row["row_version"]
        for row in store_connection.execute(
            "SELECT node_id, row_version FROM research.theme_research_node"
        ).fetchall()
    }
    assert nodes[changed_node["node_id"]] == 2
    assert nodes[package.nodes[1]["node_id"]] == 1


def test_normal_bootstrap_never_implicitly_deactivates_extra_rows(store_connection) -> None:
    package = normalize_artifact_package()
    store.bootstrap_package(
        package,
        actor_user_id="admin-integration",
        actor_role="admin",
        expected_generation=0,
        idempotency_key="bootstrap-no-deactivate-base",
        service="integration",
    )
    store_connection.execute(
        """
        INSERT INTO research.theme_research_source_item (
            source_id, source_type, title, publisher, url_or_ref, access_level,
            reliability_level, review_status, created_by, updated_by
        ) VALUES ('extra-source', 'official_article', 'extra', 'test', 'local:extra',
                  'public', 'S1', 'accepted', 'test', 'test')
        """
    )

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        store.bootstrap_package(
            package,
            actor_user_id="admin-integration",
            actor_role="admin",
            expected_generation=1,
            idempotency_key="bootstrap-no-deactivate-check",
            service="integration",
        )

    assert exc_info.value.code == "THEME_RESEARCH_RECONCILE_REQUIRED"
    active = store_connection.execute(
        "SELECT is_active FROM research.theme_research_source_item WHERE source_id = 'extra-source'"
    ).fetchone()
    assert active["is_active"] is True
