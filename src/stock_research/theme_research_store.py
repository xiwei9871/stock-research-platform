from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from psycopg.types.json import Jsonb

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_db_models import (
    validate_claim_transition,
    validate_node_transition,
    validate_source_transition,
    require_admin,
)
from stock_research.theme_decomposition import load_theme_package
from stock_research.theme_research_import import (
    NormalizedThemeResearchPackage,
    normalize_artifact_package,
    semantic_diff,
    validate_package_integrity,
)


ARTIFACT_VERSION = "theme_decomposition_v1_5"
ADVISORY_LOCK_KEY = 884_120_091


_OBJECT_CONFIG = {
    "themes": {
        "table": "theme_research_theme",
        "key": "theme_id",
        "columns": (
            "theme_id",
            "theme_name",
            "theme_type",
            "summary",
            "status",
            "created_from",
            "last_updated",
            "content_sha256",
            "artifact_metadata",
        ),
        "json": {"artifact_metadata"},
    },
    "nodes": {
        "table": "theme_research_node",
        "key": "node_id",
        "columns": (
            "node_id",
            "theme_id",
            "parent_node_id",
            "node_name",
            "node_type",
            "description",
            "value_capture_score",
            "bottleneck_score",
            "localization_gap_score",
            "supply_tightness_score",
            "evidence_strength",
            "node_review_status",
            "key_metrics",
            "overseas_leaders",
            "domestic_players",
            "related_stock_codes",
        ),
        "json": {"key_metrics", "overseas_leaders", "domestic_players", "related_stock_codes"},
    },
    "sources": {
        "table": "theme_research_source_item",
        "key": "source_id",
        "columns": (
            "source_id",
            "source_type",
            "title",
            "publisher",
            "author",
            "publish_date",
            "url_or_ref",
            "access_level",
            "reliability_level",
            "review_status",
            "notes",
            "content_sha256",
            "provenance",
        ),
        "json": {"provenance"},
    },
    "claims": {
        "table": "theme_research_content_claim",
        "key": "claim_id",
        "columns": (
            "claim_id",
            "theme_id",
            "source_id",
            "claim_text",
            "claim_type",
            "confidence",
            "evidence_status",
            "platform_use_status",
        ),
        "json": set(),
    },
    "assessments": {
        "table": "theme_research_value_assessment",
        "key": "assessment_id",
        "columns": (
            "assessment_id",
            "node_id",
            "value_basis",
            "assessment_text",
            "rank",
            "uncertainty",
        ),
        "json": set(),
    },
    "company_mappings": {
        "table": "theme_research_company_mapping",
        "key": "mapping_id",
        "columns": (
            "mapping_id",
            "theme_id",
            "node_id",
            "company_code",
            "company_name",
            "market",
            "mapping_type",
            "confidence",
            "revenue_relevance",
            "bottleneck_relevance",
            "business_materiality",
            "business_stage",
            "product_or_service",
            "relationship_summary",
            "review_status",
            "notes",
            "metadata",
        ),
        "json": {"metadata"},
    },
    "mapping_evidence_items": {
        "table": "theme_research_mapping_evidence_item",
        "key": "evidence_id",
        "columns": (
            "evidence_id",
            "source_id",
            "evidence_type",
            "excerpt_locator",
            "evidence_summary",
            "related_company_codes",
            "related_node_ids",
        ),
        "json": {"related_company_codes", "related_node_ids"},
    },
}


def validate_bootstrap_request(
    *,
    actor_user_id: str,
    expected_generation: int,
    idempotency_key: str,
) -> None:
    if not actor_user_id.strip() or not idempotency_key.strip() or expected_generation < 0:
        raise ThemeResearchDomainError(
            "actor, non-negative expected generation, and idempotency key are required",
            code="THEME_RESEARCH_IMPORT_REQUEST_INVALID",
        )


def package_for_theme(
    package: NormalizedThemeResearchPackage,
    theme_id: str,
) -> NormalizedThemeResearchPackage:
    if theme_id not in {row["theme_id"] for row in package.themes}:
        raise ThemeResearchDomainError(
            f"theme not found: {theme_id}",
            code="THEME_RESEARCH_THEME_NOT_FOUND",
            details={"theme_id": theme_id},
        )
    nodes = [row for row in package.nodes if row["theme_id"] == theme_id]
    node_ids = {row["node_id"] for row in nodes}
    claims = [row for row in package.claims if row["theme_id"] == theme_id]
    claim_ids = {row["claim_id"] for row in claims}
    assessments = [row for row in package.assessments if row["node_id"] in node_ids]
    assessment_ids = {row["assessment_id"] for row in assessments}
    mappings = [row for row in package.company_mappings if row["theme_id"] == theme_id]
    mapping_ids = {row["mapping_id"] for row in mappings}
    theme_sources = [row for row in package.theme_sources if row["theme_id"] == theme_id]
    source_ids = {row["source_id"] for row in theme_sources}
    mapping_links = [
        row for row in package.company_mapping_evidence if row["mapping_id"] in mapping_ids
    ]
    mapping_item_ids = {
        row["evidence_id"]
        for row in mapping_links
        if row["evidence_type"] == "mapping_evidence_item"
    }
    mapping_items = [
        row for row in package.mapping_evidence_items if row["evidence_id"] in mapping_item_ids
    ]
    source_ids.update(row["source_id"] for row in mapping_items)
    return NormalizedThemeResearchPackage.build(
        artifact_version=package.artifact_version,
        themes=[row for row in package.themes if row["theme_id"] == theme_id],
        nodes=nodes,
        sources=[row for row in package.sources if row["source_id"] in source_ids],
        theme_sources=theme_sources,
        claims=claims,
        claim_sources=[row for row in package.claim_sources if row["claim_id"] in claim_ids],
        claim_nodes=[row for row in package.claim_nodes if row["claim_id"] in claim_ids],
        assessments=assessments,
        assessment_evidence=[
            row for row in package.assessment_evidence if row["assessment_id"] in assessment_ids
        ],
        company_mappings=mappings,
        mapping_evidence_items=mapping_items,
        company_mapping_evidence=mapping_links,
    )


def create_snapshot(
    cur,
    *,
    theme_id: str,
    theme_version: int,
    snapshot_type: str,
    payload: dict[str, Any],
    change_set_id: str,
    actor_user_id: str,
    artifact_version: str = ARTIFACT_VERSION,
) -> str:
    snapshot_id = f"snapshot-{uuid.uuid4()}"
    canonical = _canonical_json(payload)
    payload_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    cur.execute(
        """
        INSERT INTO research.theme_research_snapshot (
            snapshot_id, theme_id, theme_version, snapshot_type, artifact_version,
            payload_sha256, payload, source_change_set_id, actor_user_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            snapshot_id,
            theme_id,
            theme_version,
            snapshot_type,
            artifact_version,
            payload_sha256,
            Jsonb(payload),
            change_set_id,
            actor_user_id,
        ),
    )
    return snapshot_id


def load_database_package(
    *,
    service: str = SETTINGS.theme_research_runtime_service,
) -> NormalizedThemeResearchPackage:
    with connect(service) as conn:
        with conn.cursor() as cur:
            _assert_runtime_connection(cur)
            return _load_database_package(cur)


def dry_run_package(
    package: NormalizedThemeResearchPackage,
    *,
    replace_theme: str | None = None,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    package = validate_package_integrity(package)
    desired = package_for_theme(package, replace_theme) if replace_theme else package
    current = load_database_package(service=service)
    current_scope = package_for_theme(current, replace_theme) if replace_theme and any(
        row["theme_id"] == replace_theme for row in current.themes
    ) else current
    diff = semantic_diff(current_scope, desired)
    return {
        "status": "dry_run",
        "package_sha256": desired.package_sha256,
        "object_counts": _object_counts(desired),
        "semantic_diff": diff,
    }


def bootstrap_package(
    package: NormalizedThemeResearchPackage,
    *,
    actor_user_id: str,
    actor_role: str,
    expected_generation: int,
    idempotency_key: str,
    replace_theme: str | None = None,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    require_admin(actor_role)
    package = validate_package_integrity(package)
    validate_bootstrap_request(
        actor_user_id=actor_user_id,
        expected_generation=expected_generation,
        idempotency_key=idempotency_key,
    )
    desired = package_for_theme(package, replace_theme) if replace_theme else package
    request_fingerprint = _request_fingerprint(
        {
            "change_type": "bootstrap_import",
            "package_sha256": desired.package_sha256,
            "replace_theme": replace_theme or "",
            "expected_generation": expected_generation,
        }
    )
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_connection(cur)
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
            replay = _load_idempotent_result(
                cur, actor_user_id, idempotency_key, request_fingerprint
            )
            if replay is not None:
                return replay
            cur.execute(
                """
                SELECT generation, package_sha256, artifact_version
                FROM research.theme_research_store_state
                WHERE state_id = true
                FOR UPDATE
                """
            )
            state = cur.fetchone()
            generation = int(state["generation"])
            if generation != expected_generation:
                raise ThemeResearchDomainError(
                    "theme research generation conflict",
                    code="THEME_RESEARCH_GENERATION_CONFLICT",
                    details={
                        "expected_generation": expected_generation,
                        "current_generation": generation,
                    },
                )
            current = _load_database_package(cur)
            if replace_theme and any(row["theme_id"] == replace_theme for row in current.themes):
                current_scope = package_for_theme(current, replace_theme)
            elif replace_theme:
                current_scope = _empty_package(current.artifact_version)
            else:
                current_scope = current
            diff = semantic_diff(current_scope, desired)
            insert_or_update_count = sum(
                len(diff["families"][family][operation])
                for family in diff["families"]
                for operation in ("insert", "update")
            )
            deactivate_count = sum(
                len(diff["families"][family]["deactivate"])
                for family in diff["families"]
            )
            if (
                not replace_theme
                and str(state.get("package_sha256") or "") == desired.package_sha256
                and (insert_or_update_count or deactivate_count)
            ):
                raise ThemeResearchDomainError(
                    "database differs from an already imported package",
                    code="THEME_RESEARCH_RECONCILE_REQUIRED",
                    details={"semantic_diff": diff},
                )
            if insert_or_update_count == 0 and (not replace_theme or deactivate_count == 0):
                result = {
                    "status": "no_changes",
                    "generation": generation,
                    "resulting_generation": generation,
                    "package_sha256": desired.package_sha256,
                    "semantic_diff": diff,
                }
                _record_no_change_import(
                    cur,
                    package=desired,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    result=result,
                    diff=diff,
                )
                return result

            change_set_id = f"change-{uuid.uuid4()}"
            import_run_id = f"import-{uuid.uuid4()}"
            cur.execute(
                """
                INSERT INTO research.theme_research_change_set (
                    change_set_id, change_type, theme_id, actor_user_id, actor_role,
                    idempotency_key, status, metadata
                ) VALUES (%s, 'bootstrap_import', %s, %s, %s, %s, 'prepared', %s)
                """,
                (
                    change_set_id,
                    replace_theme,
                    actor_user_id,
                    actor_role,
                    idempotency_key,
                    Jsonb(
                        {
                            "package_sha256": desired.package_sha256,
                            "request_fingerprint": request_fingerprint,
                        }
                    ),
                ),
            )
            current_theme_ids = {row["theme_id"] for row in current_scope.themes}
            changed_theme_ids = _changed_theme_ids(
                current_scope,
                desired,
                allow_deactivate=bool(replace_theme),
            )
            for theme_id in sorted(current_theme_ids & changed_theme_ids):
                current_theme = package_for_theme(current_scope, theme_id)
                version = int(_theme_row(cur, theme_id)["theme_version"])
                create_snapshot(
                    cur,
                    theme_id=theme_id,
                    theme_version=version,
                    snapshot_type="pre_change",
                    payload=build_theme_snapshot_payload(current_theme, theme_id),
                    change_set_id=change_set_id,
                    actor_user_id=actor_user_id,
                )

            relationship_scopes = [
                package_for_theme(desired, theme_id)
                for theme_id in sorted(changed_theme_ids)
            ]
            for relationship_scope in relationship_scopes:
                _delete_relationships(cur, relationship_scope)
            if replace_theme:
                _deactivate_removed_objects(cur, current_scope, desired, actor_user_id)
            changed_object_ids = {
                family: set(diff["families"][family]["insert"])
                | set(diff["families"][family]["update"])
                for family in _OBJECT_CONFIG
            }
            _upsert_objects(
                cur,
                desired,
                actor_user_id,
                object_ids_by_family=changed_object_ids,
            )
            for relationship_scope in relationship_scopes:
                _insert_relationships(cur, relationship_scope)
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cur.execute("SET CONSTRAINTS ALL DEFERRED")

            resulting_versions: dict[str, int] = {}
            for theme_id in sorted(changed_theme_ids):
                if theme_id in current_theme_ids:
                    theme_content_changed = theme_id in changed_object_ids["themes"]
                    cur.execute(
                        f"""
                        UPDATE research.theme_research_theme
                        SET theme_version = theme_version + 1,
                            row_version = row_version + {0 if theme_content_changed else 1},
                            updated_at = now(),
                            updated_by = %s
                        WHERE theme_id = %s
                        RETURNING theme_version
                        """,
                        (actor_user_id, theme_id),
                    )
                    version = int(cur.fetchone()["theme_version"])
                else:
                    version = int(_theme_row(cur, theme_id)["theme_version"])
                resulting_versions[theme_id] = version
                create_snapshot(
                    cur,
                    theme_id=theme_id,
                    theme_version=version,
                    snapshot_type="import",
                    payload=build_theme_snapshot_payload(
                        package_for_theme(desired, theme_id), theme_id
                    ),
                    change_set_id=change_set_id,
                    actor_user_id=actor_user_id,
                )
            _append_revisions(
                cur,
                current=current_scope,
                desired=desired,
                diff=diff,
                change_set_id=change_set_id,
                actor_user_id=actor_user_id,
                theme_versions=resulting_versions,
            )
            resulting_generation = generation + 1
            cur.execute(
                """
                UPDATE research.theme_research_store_state
                SET generation = %s,
                    package_sha256 = %s,
                    artifact_version = %s,
                    updated_at = now(),
                    updated_by = %s
                WHERE state_id = true
                """,
                (
                    resulting_generation,
                    desired.package_sha256,
                    desired.artifact_version,
                    actor_user_id,
                ),
            )
            cur.execute(
                """
                INSERT INTO research.theme_research_import_run (
                    import_run_id, change_set_id, artifact_version, schema_version,
                    package_sha256, mode, status, object_counts, semantic_diff,
                    actor_user_id, finished_at
                ) VALUES (%s, %s, %s, 'theme_research_db_v1', %s, 'bootstrap',
                          'committed', %s, %s, %s, now())
                """,
                (
                    import_run_id,
                    change_set_id,
                    desired.artifact_version,
                    desired.package_sha256,
                    Jsonb(_object_counts(desired)),
                    Jsonb(diff),
                    actor_user_id,
                ),
            )
            result = {
                "status": "committed",
                "change_set_id": change_set_id,
                "import_run_id": import_run_id,
                "generation": generation,
                "resulting_generation": resulting_generation,
                "package_sha256": desired.package_sha256,
                "theme_versions": resulting_versions,
                "object_counts": _object_counts(desired),
                "semantic_diff": diff,
            }
            cur.execute(
                """
                UPDATE research.theme_research_change_set
                SET status = 'committed',
                    resulting_theme_version = %s,
                    committed_at = now(),
                    metadata = %s
                WHERE change_set_id = %s
                """,
                (
                    max(resulting_versions.values(), default=None),
                    Jsonb(
                        {
                            "request_fingerprint": request_fingerprint,
                            "result": result,
                        }
                    ),
                    change_set_id,
                ),
            )
            return result


def review_source(
    *,
    source_id: str,
    to_status: str,
    expected_row_version: int,
    actor_user_id: str,
    actor_role: str,
    comment: str,
    request_id: str,
    idempotency_key: str,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    return _review_object(
        object_type="source",
        object_id=source_id,
        to_status=to_status,
        expected_row_version=expected_row_version,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        comment=comment,
        request_id=request_id,
        idempotency_key=idempotency_key,
        service=service,
    )


def review_claim(
    *,
    claim_id: str,
    to_status: str,
    expected_row_version: int,
    actor_user_id: str,
    actor_role: str,
    comment: str,
    request_id: str,
    idempotency_key: str,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    return _review_object(
        object_type="claim",
        object_id=claim_id,
        to_status=to_status,
        expected_row_version=expected_row_version,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        comment=comment,
        request_id=request_id,
        idempotency_key=idempotency_key,
        service=service,
    )


def review_node(
    *,
    node_id: str,
    to_status: str,
    expected_row_version: int,
    actor_user_id: str,
    actor_role: str,
    comment: str,
    request_id: str,
    idempotency_key: str,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    return _review_object(
        object_type="node",
        object_id=node_id,
        to_status=to_status,
        expected_row_version=expected_row_version,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        comment=comment,
        request_id=request_id,
        idempotency_key=idempotency_key,
        service=service,
    )


def list_review_history(
    *,
    object_type: str | None = None,
    object_id: str | None = None,
    limit: int = 100,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 500))
    conditions = ["true"]
    params: list[Any] = []
    if object_type:
        conditions.append("object_type = %s")
        params.append(object_type)
    if object_id:
        conditions.append("object_id = %s")
        params.append(object_id)
    params.append(bounded_limit)
    with connect(service) as conn:
        with conn.cursor() as cur:
            _assert_runtime_connection(cur)
            cur.execute(
                f"""
                SELECT review_event_id, change_set_id, theme_id, object_type, object_id,
                       from_status, to_status, decision, reviewer_user_id, reviewer_role,
                       comment, request_id, idempotency_key, payload, created_at
                FROM research.theme_research_review_event
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC, review_event_id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            items = [_json_safe_row(dict(row)) for row in cur.fetchall()]
    return {"total": len(items), "items": items}


def list_snapshots(
    *,
    theme_id: str,
    limit: int = 100,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 500))
    with connect(service) as conn:
        with conn.cursor() as cur:
            _assert_runtime_connection(cur)
            cur.execute(
                """
                SELECT snapshot_id, theme_id, theme_version, snapshot_type,
                       artifact_version, payload_sha256, source_change_set_id,
                       actor_user_id, created_at
                FROM research.theme_research_snapshot
                WHERE theme_id = %s
                ORDER BY theme_version DESC, created_at DESC
                LIMIT %s
                """,
                (theme_id, bounded_limit),
            )
            items = [_json_safe_row(dict(row)) for row in cur.fetchall()]
    return {"total": len(items), "items": items}


def export_theme(
    theme_id: str,
    *,
    output_dir: str | Path,
    actor_user_id: str,
    actor_role: str,
    idempotency_key: str,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    require_admin(actor_role)
    if not actor_user_id.strip() or not idempotency_key.strip():
        raise ThemeResearchDomainError(
            "actor and idempotency key are required",
            code="THEME_RESEARCH_EXPORT_REQUEST_INVALID",
        )
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    final_path = output_root / f"{theme_id}.json"
    request_fingerprint = _request_fingerprint(
        {
            "change_type": "export",
            "theme_id": theme_id,
            "output_path": str(final_path.resolve()),
        }
    )
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_connection(cur)
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
            replay = _load_idempotent_result(
                cur, actor_user_id, idempotency_key, request_fingerprint
            )
            if replay is not None:
                cur.execute(
                    "SELECT payload FROM research.theme_research_snapshot WHERE snapshot_id = %s",
                    (replay["snapshot_id"],),
                )
                snapshot = cur.fetchone()
                if not snapshot:
                    raise ThemeResearchDomainError(
                        "export snapshot is missing",
                        code="THEME_RESEARCH_EXPORT_SNAPSHOT_MISSING",
                    )
                external_payload = dict(snapshot["payload"])
                external_payload.pop("_database_extensions", None)
                replay["payload_sha256"] = _publish_export_payload(
                    external_payload, final_path
                )
                return replay
            package = _load_database_package(cur)
            theme = _theme_row(cur, theme_id)
            payload = build_theme_artifact_from_package(package, theme_id)
            snapshot_payload = build_theme_snapshot_payload(package, theme_id)
            change_set_id = f"change-{uuid.uuid4()}"
            cur.execute(
                """
                INSERT INTO research.theme_research_change_set (
                    change_set_id, change_type, theme_id, actor_user_id, actor_role,
                    idempotency_key, status, metadata
                ) VALUES (%s, 'export', %s, %s, %s, %s, 'prepared', %s)
                """,
                (
                    change_set_id,
                    theme_id,
                    actor_user_id,
                    actor_role,
                    idempotency_key,
                    Jsonb(
                        {
                            "output_path": str(final_path),
                            "request_fingerprint": request_fingerprint,
                        }
                    ),
                ),
            )
            snapshot_id = create_snapshot(
                cur,
                theme_id=theme_id,
                theme_version=int(theme["theme_version"]),
                snapshot_type="export",
                payload=snapshot_payload,
                change_set_id=change_set_id,
                actor_user_id=actor_user_id,
            )
            payload_sha256 = _publish_export_payload(payload, final_path)
            result = {
                "status": "exported",
                "theme_id": theme_id,
                "theme_version": int(theme["theme_version"]),
                "snapshot_id": snapshot_id,
                "path": str(final_path),
                "payload_sha256": payload_sha256,
            }
            cur.execute(
                """
                UPDATE research.theme_research_change_set
                SET status = 'committed', committed_at = now(), metadata = %s
                WHERE change_set_id = %s
                """,
                (
                    Jsonb(
                        {
                            "request_fingerprint": request_fingerprint,
                            "result": result,
                        }
                    ),
                    change_set_id,
                ),
            )
            return result


def _publish_export_payload(payload: dict[str, Any], final_path: Path) -> str:
    canonical = _canonical_json(payload) + "\n"
    payload_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if final_path.is_file() and hashlib.sha256(final_path.read_bytes()).hexdigest() == payload_sha256:
        return payload_sha256
    with tempfile.TemporaryDirectory(prefix="theme-research-export-") as temp_dir:
        validation_path = Path(temp_dir) / final_path.name
        validation_path.write_text(canonical, encoding="utf-8")
        load_theme_package(temp_dir)
    staged_path = final_path.parent / f".{final_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        staged_path.write_text(canonical, encoding="utf-8")
        os.replace(staged_path, final_path)
    finally:
        staged_path.unlink(missing_ok=True)
    return payload_sha256


def rollback_theme(
    *,
    theme_id: str,
    snapshot_id: str,
    expected_theme_version: int,
    actor_user_id: str,
    actor_role: str,
    comment: str,
    idempotency_key: str,
    request_id: str = "",
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    require_admin(actor_role)
    if not actor_user_id.strip() or not idempotency_key.strip() or not comment.strip():
        raise ThemeResearchDomainError(
            "actor, idempotency key, and comment are required",
            code="THEME_RESEARCH_ROLLBACK_REQUEST_INVALID",
        )
    request_fingerprint = _request_fingerprint(
        {
            "change_type": "rollback",
            "theme_id": theme_id,
            "snapshot_id": snapshot_id,
            "expected_theme_version": expected_theme_version,
        }
    )
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_connection(cur)
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
            generation = _lock_store_generation(cur)
            replay = _load_idempotent_result(
                cur, actor_user_id, idempotency_key, request_fingerprint
            )
            if replay is not None:
                return replay
            cur.execute(
                """
                SELECT theme_version
                FROM research.theme_research_theme
                WHERE theme_id = %s AND is_active = true
                FOR UPDATE
                """,
                (theme_id,),
            )
            theme = cur.fetchone()
            if not theme:
                raise ThemeResearchDomainError(
                    f"theme not found: {theme_id}",
                    code="THEME_RESEARCH_THEME_NOT_FOUND",
                )
            current_version = int(theme["theme_version"])
            if current_version != expected_theme_version:
                raise ThemeResearchDomainError(
                    "theme version conflict",
                    code="THEME_RESEARCH_VERSION_CONFLICT",
                    details={
                        "expected_theme_version": expected_theme_version,
                        "current_theme_version": current_version,
                    },
                )
            cur.execute(
                """
                SELECT payload, theme_id, theme_version
                FROM research.theme_research_snapshot
                WHERE snapshot_id = %s
                """,
                (snapshot_id,),
            )
            snapshot = cur.fetchone()
            if not snapshot or snapshot["theme_id"] != theme_id:
                raise ThemeResearchDomainError(
                    f"snapshot not found for theme: {snapshot_id}",
                    code="THEME_RESEARCH_SNAPSHOT_NOT_FOUND",
                )
            target = _package_from_snapshot_payload(dict(snapshot["payload"]), theme_id)
            current_package = _load_database_package(cur)
            current_scope = package_for_theme(current_package, theme_id)
            diff = semantic_diff(current_scope, target)
            _assert_rollback_has_no_shared_source_changes(
                cur,
                theme_id=theme_id,
                source_ids=set(diff["families"]["sources"]["insert"])
                | set(diff["families"]["sources"]["update"])
                | set(diff["families"]["sources"]["deactivate"]),
            )
            change_set_id = f"change-{uuid.uuid4()}"
            cur.execute(
                """
                INSERT INTO research.theme_research_change_set (
                    change_set_id, change_type, theme_id, actor_user_id, actor_role,
                    request_id, idempotency_key, expected_theme_version, status, metadata
                ) VALUES (%s, 'rollback', %s, %s, %s, %s, %s, %s, 'prepared', %s)
                """,
                (
                    change_set_id,
                    theme_id,
                    actor_user_id,
                    actor_role,
                    request_id,
                    idempotency_key,
                    expected_theme_version,
                    Jsonb(
                        {
                            "snapshot_id": snapshot_id,
                            "request_fingerprint": request_fingerprint,
                        }
                    ),
                ),
            )
            create_snapshot(
                cur,
                theme_id=theme_id,
                theme_version=current_version,
                snapshot_type="pre_change",
                payload=build_theme_snapshot_payload(current_scope, theme_id),
                change_set_id=change_set_id,
                actor_user_id=actor_user_id,
            )
            _delete_relationships(cur, target)
            _deactivate_removed_objects(cur, current_scope, target, actor_user_id)
            restore_object_ids = {
                family: set(diff["families"][family]["insert"])
                | set(diff["families"][family]["update"])
                for family in _OBJECT_CONFIG
            }
            _upsert_objects(
                cur,
                target,
                actor_user_id,
                object_ids_by_family=restore_object_ids,
            )
            _insert_relationships(cur, target)
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cur.execute("SET CONSTRAINTS ALL DEFERRED")
            resulting_version = current_version + 1
            cur.execute(
                """
                UPDATE research.theme_research_theme
                SET theme_version = %s,
                    updated_at = now(),
                    updated_by = %s
                WHERE theme_id = %s
                """,
                (resulting_version, actor_user_id, theme_id),
            )
            restored_package = _load_database_package(cur)
            restored_scope = package_for_theme(restored_package, theme_id)
            resulting_generation = _advance_store_generation(
                cur,
                package=restored_package,
                actor_user_id=actor_user_id,
            )
            _append_restore_revisions(
                cur,
                current=current_scope,
                restored=restored_scope,
                diff=diff,
                change_set_id=change_set_id,
                actor_user_id=actor_user_id,
            )
            cur.execute(
                """
                INSERT INTO research.theme_research_review_event (
                    review_event_id, change_set_id, theme_id, object_type, object_id,
                    from_status, to_status, decision, reviewer_user_id, reviewer_role,
                    comment, request_id, idempotency_key, payload
                ) VALUES (%s, %s, %s, 'rollback', %s, %s, %s, 'rollback_snapshot',
                          %s, %s, %s, %s, %s, %s)
                """,
                (
                    f"review-{uuid.uuid4()}",
                    change_set_id,
                    theme_id,
                    theme_id,
                    str(current_version),
                    str(resulting_version),
                    actor_user_id,
                    actor_role,
                    comment.strip(),
                    request_id,
                    idempotency_key,
                    Jsonb(
                        {
                            "restored_from_snapshot_id": snapshot_id,
                            "restored_from_theme_version": int(snapshot["theme_version"]),
                        }
                    ),
                ),
            )
            post_snapshot_id = create_snapshot(
                cur,
                theme_id=theme_id,
                theme_version=resulting_version,
                snapshot_type="rollback",
                payload=build_theme_snapshot_payload(restored_scope, theme_id),
                change_set_id=change_set_id,
                actor_user_id=actor_user_id,
            )
            result = {
                "status": "rolled_back",
                "theme_id": theme_id,
                "theme_version": resulting_version,
                "restored_from_snapshot_id": snapshot_id,
                "snapshot_id": post_snapshot_id,
                "semantic_diff": diff,
                "generation": generation,
                "resulting_generation": resulting_generation,
            }
            cur.execute(
                """
                UPDATE research.theme_research_change_set
                SET status = 'committed', resulting_theme_version = %s,
                    committed_at = now(), metadata = %s
                WHERE change_set_id = %s
                """,
                (
                    resulting_version,
                    Jsonb(
                        {
                            "request_fingerprint": request_fingerprint,
                            "result": result,
                        }
                    ),
                    change_set_id,
                ),
            )
            return result


def _package_from_snapshot_payload(
    payload: dict[str, Any],
    theme_id: str,
) -> NormalizedThemeResearchPackage:
    extension = payload.get("_database_extensions") or {}
    normalized = extension.get("normalized_package") or {}
    if not normalized:
        raise ThemeResearchDomainError(
            "snapshot does not contain the normalized database package",
            code="THEME_RESEARCH_SNAPSHOT_FORMAT_INVALID",
        )
    with tempfile.TemporaryDirectory(prefix="theme-research-rollback-validate-") as temp_dir:
        validation_payload = copy.deepcopy(payload)
        validation_payload.pop("_database_extensions", None)
        (Path(temp_dir) / f"{theme_id}.json").write_text(
            _canonical_json(validation_payload) + "\n",
            encoding="utf-8",
        )
        load_theme_package(temp_dir)
    package = NormalizedThemeResearchPackage.build(
        artifact_version=str(normalized["artifact_version"]),
        themes=normalized["themes"],
        nodes=normalized["nodes"],
        sources=normalized["sources"],
        theme_sources=normalized["theme_sources"],
        claims=normalized["claims"],
        claim_sources=normalized["claim_sources"],
        claim_nodes=normalized["claim_nodes"],
        assessments=normalized["assessments"],
        assessment_evidence=normalized["assessment_evidence"],
        company_mappings=normalized["company_mappings"],
        mapping_evidence_items=normalized["mapping_evidence_items"],
        company_mapping_evidence=normalized["company_mapping_evidence"],
    )
    return package_for_theme(package, theme_id)


def _assert_rollback_has_no_shared_source_changes(
    cur,
    *,
    theme_id: str,
    source_ids: set[str],
) -> None:
    if not source_ids:
        return
    cur.execute(
        """
        SELECT ts.source_id, array_agg(DISTINCT ts.theme_id ORDER BY ts.theme_id) AS theme_ids
        FROM research.theme_research_theme_source ts
        JOIN research.theme_research_theme t ON t.theme_id = ts.theme_id
        WHERE ts.source_id = ANY(%s) AND t.is_active = true
        GROUP BY ts.source_id
        """,
        (sorted(source_ids),),
    )
    conflicts = {
        str(row["source_id"]): list(row["theme_ids"])
        for row in cur.fetchall()
        if any(owner != theme_id for owner in row["theme_ids"])
    }
    if conflicts:
        raise ThemeResearchDomainError(
            "single-theme rollback would modify a source shared by another active theme",
            code="THEME_RESEARCH_SHARED_SOURCE_ROLLBACK_REQUIRES_MULTI_THEME",
            details={"shared_sources": conflicts},
        )


def _review_object(
    *,
    object_type: str,
    object_id: str,
    to_status: str,
    expected_row_version: int,
    actor_user_id: str,
    actor_role: str,
    comment: str,
    request_id: str,
    idempotency_key: str,
    service: str,
) -> dict[str, Any]:
    if actor_role not in {"admin", "user"}:
        raise ThemeResearchDomainError(
            "active user or administrator role is required",
            code="THEME_RESEARCH_REVIEW_ROLE_INVALID",
        )
    if not actor_user_id.strip() or not request_id.strip() or not idempotency_key.strip():
        raise ThemeResearchDomainError(
            "actor, request ID, and idempotency key are required",
            code="THEME_RESEARCH_REVIEW_REQUEST_INVALID",
        )
    if not comment.strip():
        raise ThemeResearchDomainError(
            "review comment is required",
            code="THEME_RESEARCH_REVIEW_COMMENT_REQUIRED",
        )
    request_fingerprint = _request_fingerprint(
        {
            "change_type": "review_transition",
            "object_type": object_type,
            "object_id": object_id,
            "to_status": to_status,
            "expected_row_version": expected_row_version,
        }
    )
    config = {
        "source": (
            "theme_research_source_item",
            "source_id",
            "review_status",
        ),
        "claim": (
            "theme_research_content_claim",
            "claim_id",
            "platform_use_status",
        ),
        "node": (
            "theme_research_node",
            "node_id",
            "node_review_status",
        ),
    }[object_type]
    table, key_column, status_column = config
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_connection(cur)
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
            generation = _lock_store_generation(cur)
            replay = _load_idempotent_result(
                cur, actor_user_id, idempotency_key, request_fingerprint
            )
            if replay is not None:
                return replay
            cur.execute(
                f"SELECT * FROM research.{table} WHERE {key_column} = %s AND is_active = true FOR UPDATE",
                (object_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ThemeResearchDomainError(
                    f"{object_type} not found: {object_id}",
                    code="THEME_RESEARCH_OBJECT_NOT_FOUND",
                    details={"object_type": object_type, "object_id": object_id},
                )
            before = _json_safe_row(dict(row))
            current_version = int(row["row_version"])
            if current_version != expected_row_version:
                raise ThemeResearchDomainError(
                    "theme research row version conflict",
                    code="THEME_RESEARCH_VERSION_CONFLICT",
                    details={
                        "expected_row_version": expected_row_version,
                        "current_row_version": current_version,
                    },
                )
            from_status = str(row[status_column])
            _validate_review_transition(
                cur,
                object_type=object_type,
                row=dict(row),
                from_status=from_status,
                to_status=to_status,
            )
            theme_ids = _review_theme_ids(cur, object_type, object_id, dict(row))
            if not theme_ids:
                raise ThemeResearchDomainError(
                    "review object is not linked to an active theme",
                    code="THEME_RESEARCH_ORPHAN_REVIEW_OBJECT",
                )
            current_package = _load_database_package(cur)
            change_set_id = f"change-{uuid.uuid4()}"
            cur.execute(
                """
                INSERT INTO research.theme_research_change_set (
                    change_set_id, change_type, theme_id, actor_user_id, actor_role,
                    request_id, idempotency_key, status, metadata
                ) VALUES (%s, 'review_transition', %s, %s, %s, %s, %s, 'prepared', %s)
                """,
                (
                    change_set_id,
                    theme_ids[0] if len(theme_ids) == 1 else None,
                    actor_user_id,
                    actor_role,
                    request_id,
                    idempotency_key,
                    Jsonb(
                        {
                            "object_type": object_type,
                            "object_id": object_id,
                            "request_fingerprint": request_fingerprint,
                        }
                    ),
                ),
            )
            for theme_id in theme_ids:
                theme = _theme_row(cur, theme_id)
                create_snapshot(
                    cur,
                    theme_id=theme_id,
                    theme_version=int(theme["theme_version"]),
                    snapshot_type="pre_change",
                    payload=build_theme_snapshot_payload(
                        package_for_theme(current_package, theme_id), theme_id
                    ),
                    change_set_id=change_set_id,
                    actor_user_id=actor_user_id,
                )
            cur.execute(
                f"""
                UPDATE research.{table}
                SET {status_column} = %s,
                    row_version = row_version + 1,
                    updated_at = now(),
                    updated_by = %s
                WHERE {key_column} = %s
                RETURNING *
                """,
                (to_status, actor_user_id, object_id),
            )
            after = _json_safe_row(dict(cur.fetchone()))
            theme_versions: dict[str, int] = {}
            for theme_id in theme_ids:
                cur.execute(
                    """
                    UPDATE research.theme_research_theme
                    SET theme_version = theme_version + 1,
                        row_version = row_version + 1,
                        updated_at = now(),
                        updated_by = %s
                    WHERE theme_id = %s
                    RETURNING theme_version
                    """,
                    (actor_user_id, theme_id),
                )
                theme_versions[theme_id] = int(cur.fetchone()["theme_version"])
                cur.execute(
                    """
                    INSERT INTO research.theme_research_review_event (
                        review_event_id, change_set_id, theme_id, object_type, object_id,
                        from_status, to_status, decision, reviewer_user_id, reviewer_role,
                        comment, request_id, idempotency_key, payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'status_transition',
                              %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        f"review-{uuid.uuid4()}",
                        change_set_id,
                        theme_id,
                        object_type,
                        object_id,
                        from_status,
                        to_status,
                        actor_user_id,
                        actor_role,
                        comment.strip(),
                        request_id,
                        idempotency_key,
                        Jsonb({"before": before, "after": after}),
                    ),
                )
            cur.execute(
                """
                INSERT INTO research.theme_research_object_revision (
                    revision_id, change_set_id, theme_id, object_type, object_id,
                    object_version, operation, before_payload, after_payload, actor_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, 'update', %s, %s, %s)
                """,
                (
                    f"revision-{uuid.uuid4()}",
                    change_set_id,
                    theme_ids[0],
                    object_type,
                    object_id,
                    int(after["row_version"]),
                    Jsonb(before),
                    Jsonb(after),
                    actor_user_id,
                ),
            )
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cur.execute("SET CONSTRAINTS ALL DEFERRED")
            after_package = _load_database_package(cur)
            resulting_generation = _advance_store_generation(
                cur,
                package=after_package,
                actor_user_id=actor_user_id,
            )
            for theme_id in theme_ids:
                create_snapshot(
                    cur,
                    theme_id=theme_id,
                    theme_version=theme_versions[theme_id],
                    snapshot_type="post_change",
                    payload=build_theme_snapshot_payload(
                        package_for_theme(after_package, theme_id), theme_id
                    ),
                    change_set_id=change_set_id,
                    actor_user_id=actor_user_id,
                )
            result = {
                "status": "reviewed",
                "change_set_id": change_set_id,
                "object_type": object_type,
                "object_id": object_id,
                "from_status": from_status,
                "to_status": to_status,
                "row_version": int(after["row_version"]),
                "theme_versions": theme_versions,
                "generation": generation,
                "resulting_generation": resulting_generation,
            }
            cur.execute(
                """
                UPDATE research.theme_research_change_set
                SET status = 'committed', committed_at = now(), metadata = %s
                WHERE change_set_id = %s
                """,
                (
                    Jsonb(
                        {
                            "request_fingerprint": request_fingerprint,
                            "result": result,
                        }
                    ),
                    change_set_id,
                ),
            )
            return result


def _validate_review_transition(
    cur,
    *,
    object_type: str,
    row: dict[str, Any],
    from_status: str,
    to_status: str,
) -> None:
    if object_type == "source":
        validate_source_transition(
            reliability_level=str(row["reliability_level"]),
            from_status=from_status,
            to_status=to_status,
        )
        return
    if object_type == "claim":
        cur.execute(
            """
            SELECT s.review_status, s.reliability_level
            FROM research.theme_research_source_item s
            WHERE s.is_active = true
              AND (
                    s.source_id = %s
                    OR s.source_id IN (
                        SELECT source_id FROM research.theme_research_claim_source
                        WHERE claim_id = %s
                    )
              )
            """,
            (row["source_id"], row["claim_id"]),
        )
        validate_claim_transition(
            from_status=from_status,
            to_status=to_status,
            evidence_sources=[dict(item) for item in cur.fetchall()],
        )
        return
    validate_node_transition(
        from_status=from_status,
        to_status=to_status,
        evidence_strength=int(row["evidence_strength"]),
    )


def _review_theme_ids(
    cur,
    object_type: str,
    object_id: str,
    row: dict[str, Any],
) -> list[str]:
    if object_type in {"claim", "node"}:
        return [str(row["theme_id"])]
    cur.execute(
        """
        SELECT DISTINCT ts.theme_id
        FROM research.theme_research_theme_source ts
        JOIN research.theme_research_theme t ON t.theme_id = ts.theme_id
        WHERE ts.source_id = %s AND t.is_active = true
        ORDER BY ts.theme_id
        """,
        (object_id,),
    )
    return [str(item["theme_id"]) for item in cur.fetchall()]


def build_theme_artifact_from_package(
    package: NormalizedThemeResearchPackage,
    theme_id: str,
) -> dict[str, Any]:
    selected = package_for_theme(package, theme_id)
    theme_row = copy.deepcopy(selected.themes[0])
    metadata = theme_row.pop("artifact_metadata", {})
    theme_row.pop("content_sha256", None)
    supporting_by_claim: dict[str, list[str]] = {}
    nodes_by_claim: dict[str, list[str]] = {}
    for row in selected.claim_sources:
        supporting_by_claim.setdefault(row["claim_id"], []).append(row["source_id"])
    for row in selected.claim_nodes:
        nodes_by_claim.setdefault(row["claim_id"], []).append(row["node_id"])
    evidence_by_assessment: dict[str, list[str]] = {}
    for row in selected.assessment_evidence:
        evidence_by_assessment.setdefault(row["assessment_id"], []).append(row["evidence_id"])
    sources = []
    for source in selected.sources:
        row = copy.deepcopy(source)
        row.pop("content_sha256", None)
        row.pop("provenance", None)
        row["publish_date"] = row.get("publish_date") or ""
        sources.append(row)
    claims = []
    for claim in selected.claims:
        row = copy.deepcopy(claim)
        row["supporting_source_ids"] = sorted(supporting_by_claim.get(row["claim_id"], []))
        row["affected_theme_nodes"] = sorted(nodes_by_claim.get(row["claim_id"], []))
        claims.append(row)
    assessments = []
    for assessment in selected.assessments:
        row = copy.deepcopy(assessment)
        assessment_id = row.pop("assessment_id")
        row["evidence_ids"] = sorted(evidence_by_assessment.get(assessment_id, []))
        assessments.append(row)
    return {
        "artifact_version": selected.artifact_version,
        "theme": theme_row,
        "nodes": [copy.deepcopy(row) for row in selected.nodes],
        "sources": sources,
        "claims": claims,
        "value_capture_assessments": assessments,
        "decomposition_templates": copy.deepcopy(metadata.get("decomposition_templates", [])),
        "evidence_policy": copy.deepcopy(metadata.get("evidence_policy", {})),
    }


def build_theme_snapshot_payload(
    package: NormalizedThemeResearchPackage,
    theme_id: str,
) -> dict[str, Any]:
    selected = package_for_theme(package, theme_id)
    payload = build_theme_artifact_from_package(selected, theme_id)
    payload["_database_extensions"] = {
        "normalized_package": selected.as_dict(),
    }
    return payload


def _load_database_package(cur) -> NormalizedThemeResearchPackage:
    cur.execute(
        "SELECT artifact_version FROM research.theme_research_store_state WHERE state_id = true"
    )
    state = cur.fetchone() or {}
    artifact_version = state.get("artifact_version") or ARTIFACT_VERSION
    rows: dict[str, list[dict[str, Any]]] = {}
    for family, config in _OBJECT_CONFIG.items():
        columns = ", ".join(config["columns"])
        cur.execute(
            f"SELECT {columns} FROM research.{config['table']} WHERE is_active = true"
        )
        family_rows = [_json_safe_row(dict(row)) for row in cur.fetchall()]
        if family == "nodes":
            for row in family_rows:
                row["parent_node_id"] = row.get("parent_node_id") or ""
        rows[family] = family_rows
    relationship_queries = {
        "theme_sources": "SELECT theme_id, source_id, link_reason FROM research.theme_research_theme_source",
        "claim_sources": "SELECT claim_id, source_id FROM research.theme_research_claim_source",
        "claim_nodes": "SELECT claim_id, node_id FROM research.theme_research_claim_node",
        "assessment_evidence": "SELECT assessment_id, evidence_type, evidence_id FROM research.theme_research_assessment_evidence",
        "company_mapping_evidence": "SELECT mapping_id, evidence_type, evidence_id FROM research.theme_research_company_mapping_evidence",
    }
    for family, query in relationship_queries.items():
        cur.execute(query)
        rows[family] = [_json_safe_row(dict(row)) for row in cur.fetchall()]
    return NormalizedThemeResearchPackage.build(
        artifact_version=artifact_version,
        themes=rows["themes"],
        nodes=rows["nodes"],
        sources=rows["sources"],
        theme_sources=rows["theme_sources"],
        claims=rows["claims"],
        claim_sources=rows["claim_sources"],
        claim_nodes=rows["claim_nodes"],
        assessments=rows["assessments"],
        assessment_evidence=rows["assessment_evidence"],
        company_mappings=rows["company_mappings"],
        mapping_evidence_items=rows["mapping_evidence_items"],
        company_mapping_evidence=rows["company_mapping_evidence"],
    )


def _assert_runtime_connection(cur) -> None:
    cur.execute(
        """
        SELECT
            current_user AS role_name,
            r.rolsuper,
            r.rolcreaterole,
            pg_has_role(current_user, 'theme_research_runtime', 'member') AS runtime_member,
            pg_has_role(current_user, 'theme_research_owner', 'member') AS owner_member
        FROM pg_roles r
        WHERE r.rolname = current_user
        """
    )
    row = cur.fetchone()
    if (
        not row
        or bool(row["rolsuper"])
        or bool(row["rolcreaterole"])
        or not bool(row["runtime_member"])
        or bool(row["owner_member"])
    ):
        raise ThemeResearchDomainError(
            "theme research store requires a constrained runtime database login",
            code="THEME_RESEARCH_UNSAFE_DATABASE_ROLE",
            details={"role_name": str((row or {}).get("role_name") or "")},
        )


def _empty_package(artifact_version: str) -> NormalizedThemeResearchPackage:
    return NormalizedThemeResearchPackage.build(
        artifact_version=artifact_version or ARTIFACT_VERSION,
        themes=[], nodes=[], sources=[], theme_sources=[], claims=[], claim_sources=[],
        claim_nodes=[], assessments=[], assessment_evidence=[], company_mappings=[],
        mapping_evidence_items=[], company_mapping_evidence=[],
    )


def _request_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _load_idempotent_result(
    cur,
    actor_user_id: str,
    idempotency_key: str,
    request_fingerprint: str,
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT metadata
        FROM research.theme_research_change_set
        WHERE actor_user_id = %s AND idempotency_key = %s AND status = 'committed'
        """,
        (actor_user_id, idempotency_key),
    )
    row = cur.fetchone()
    if not row:
        return None
    metadata = row.get("metadata") or {}
    if metadata.get("request_fingerprint") != request_fingerprint:
        raise ThemeResearchDomainError(
            "idempotency key was already used for a different request",
            code="THEME_RESEARCH_IDEMPOTENCY_KEY_REUSED",
            details={"idempotency_key": idempotency_key},
        )
    return copy.deepcopy(metadata.get("result"))


def _lock_store_generation(cur) -> int:
    cur.execute(
        """
        SELECT generation
        FROM research.theme_research_store_state
        WHERE state_id = true
        FOR UPDATE
        """
    )
    row = cur.fetchone()
    return int(row["generation"])


def _advance_store_generation(
    cur,
    *,
    package: NormalizedThemeResearchPackage,
    actor_user_id: str,
) -> int:
    cur.execute(
        """
        UPDATE research.theme_research_store_state
        SET generation = generation + 1,
            package_sha256 = %s,
            artifact_version = %s,
            updated_at = now(),
            updated_by = %s
        WHERE state_id = true
        RETURNING generation
        """,
        (package.package_sha256, package.artifact_version, actor_user_id),
    )
    return int(cur.fetchone()["generation"])


def _delete_relationships(cur, desired: NormalizedThemeResearchPackage) -> None:
    theme_ids = [row["theme_id"] for row in desired.themes]
    cur.execute(
        """
        DELETE FROM research.theme_research_company_mapping_evidence e
        USING research.theme_research_company_mapping m
        WHERE e.mapping_id = m.mapping_id AND m.theme_id = ANY(%s)
        """,
        (theme_ids,),
    )
    cur.execute(
        """
        DELETE FROM research.theme_research_assessment_evidence e
        USING research.theme_research_value_assessment a, research.theme_research_node n
        WHERE e.assessment_id = a.assessment_id AND a.node_id = n.node_id AND n.theme_id = ANY(%s)
        """,
        (theme_ids,),
    )
    cur.execute(
        """
        DELETE FROM research.theme_research_claim_node r
        USING research.theme_research_content_claim c
        WHERE r.claim_id = c.claim_id AND c.theme_id = ANY(%s)
        """,
        (theme_ids,),
    )
    cur.execute(
        """
        DELETE FROM research.theme_research_claim_source r
        USING research.theme_research_content_claim c
        WHERE r.claim_id = c.claim_id AND c.theme_id = ANY(%s)
        """,
        (theme_ids,),
    )
    cur.execute(
        "DELETE FROM research.theme_research_theme_source WHERE theme_id = ANY(%s)",
        (theme_ids,),
    )


def _deactivate_removed_objects(
    cur,
    current: NormalizedThemeResearchPackage,
    desired: NormalizedThemeResearchPackage,
    actor_user_id: str,
) -> None:
    for family in (
        "company_mappings",
        "assessments",
        "claims",
        "mapping_evidence_items",
        "nodes",
        "sources",
    ):
        config = _OBJECT_CONFIG[family]
        key = config["key"]
        desired_ids = {row[key] for row in getattr(desired, family)}
        removed_ids = [row[key] for row in getattr(current, family) if row[key] not in desired_ids]
        if not removed_ids:
            continue
        cur.execute(
            f"""
            UPDATE research.{config['table']}
            SET is_active = false,
                row_version = row_version + 1,
                updated_at = now(),
                updated_by = %s
            WHERE {key} = ANY(%s) AND is_active = true
              {"AND NOT EXISTS (SELECT 1 FROM research.theme_research_theme_source ts WHERE ts.source_id = research.theme_research_source_item.source_id)" if family == "sources" else ""}
            """,
            (actor_user_id, removed_ids),
        )


def _upsert_objects(
    cur,
    package: NormalizedThemeResearchPackage,
    actor_user_id: str,
    *,
    object_ids_by_family: dict[str, set[str]] | None = None,
) -> None:
    for family in (
        "themes",
        "sources",
        "nodes",
        "claims",
        "assessments",
        "mapping_evidence_items",
        "company_mappings",
    ):
        config = _OBJECT_CONFIG[family]
        columns = config["columns"]
        update_columns = [column for column in columns if column != config["key"]]
        assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"""
            INSERT INTO research.{config['table']} (
                {', '.join(columns)}, is_active, created_by, updated_by
            ) VALUES ({placeholders}, true, %s, %s)
            ON CONFLICT ({config['key']}) DO UPDATE SET
                {assignments},
                is_active = true,
                row_version = research.{config['table']}.row_version + 1,
                updated_at = now(),
                updated_by = EXCLUDED.updated_by
        """
        params = []
        for row in getattr(package, family):
            if (
                object_ids_by_family is not None
                and str(row[config["key"]]) not in object_ids_by_family.get(family, set())
            ):
                continue
            values = []
            for column in columns:
                value = row.get(column)
                if family == "nodes" and column == "parent_node_id" and not value:
                    value = None
                if column == "publish_date" and not value:
                    value = None
                if column in config["json"]:
                    value = Jsonb(value)
                values.append(value)
            params.append((*values, actor_user_id, actor_user_id))
        if params:
            cur.executemany(sql, params)


def _insert_relationships(cur, package: NormalizedThemeResearchPackage) -> None:
    relations = {
        "theme_research_theme_source": (
            ("theme_id", "source_id", "link_reason"),
            package.theme_sources,
        ),
        "theme_research_claim_source": (("claim_id", "source_id"), package.claim_sources),
        "theme_research_claim_node": (("claim_id", "node_id"), package.claim_nodes),
        "theme_research_assessment_evidence": (
            ("assessment_id", "evidence_type", "evidence_id"),
            package.assessment_evidence,
        ),
        "theme_research_company_mapping_evidence": (
            ("mapping_id", "evidence_type", "evidence_id"),
            package.company_mapping_evidence,
        ),
    }
    for table, (columns, rows) in relations.items():
        if not rows:
            continue
        placeholders = ", ".join(["%s"] * len(columns))
        cur.executemany(
            f"INSERT INTO research.{table} ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(row[column] for column in columns) for row in rows],
        )


def _append_revisions(
    cur,
    *,
    current: NormalizedThemeResearchPackage,
    desired: NormalizedThemeResearchPackage,
    diff: dict[str, Any],
    change_set_id: str,
    actor_user_id: str,
    theme_versions: dict[str, int],
) -> None:
    for family, config in _OBJECT_CONFIG.items():
        family_diff = diff["families"][family]
        key = config["key"]
        before_by_id = {str(row[key]): row for row in getattr(current, family)}
        after_by_id = {str(row[key]): row for row in getattr(desired, family)}
        for operation, ids in (
            ("insert", family_diff["insert"]),
            ("update", family_diff["update"]),
            ("deactivate", family_diff["deactivate"]),
        ):
            for object_id in ids:
                before = before_by_id.get(object_id)
                after = after_by_id.get(object_id)
                theme_id = _object_theme_id(family, before or after or {}, desired, current)
                object_version = _object_row_version(cur, family, object_id)
                cur.execute(
                    """
                    INSERT INTO research.theme_research_object_revision (
                        revision_id, change_set_id, theme_id, object_type, object_id,
                        object_version, operation, before_payload, after_payload, actor_user_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        f"revision-{uuid.uuid4()}",
                        change_set_id,
                        theme_id,
                        family,
                        object_id,
                        object_version,
                        operation,
                        Jsonb(before) if before is not None else None,
                        Jsonb(after) if after is not None else None,
                        actor_user_id,
                    ),
                )


def _append_restore_revisions(
    cur,
    *,
    current: NormalizedThemeResearchPackage,
    restored: NormalizedThemeResearchPackage,
    diff: dict[str, Any],
    change_set_id: str,
    actor_user_id: str,
) -> None:
    for family, config in _OBJECT_CONFIG.items():
        changed_ids = sorted(
            set(diff["families"][family]["insert"])
            | set(diff["families"][family]["update"])
            | set(diff["families"][family]["deactivate"])
        )
        before_by_id = {
            str(row[config["key"]]): row for row in getattr(current, family)
        }
        after_by_id = {
            str(row[config["key"]]): row for row in getattr(restored, family)
        }
        for object_id in changed_ids:
            before = before_by_id.get(object_id)
            after = after_by_id.get(object_id)
            row = after or before or {}
            theme_id = _object_theme_id(family, row, restored, current)
            cur.execute(
                """
                INSERT INTO research.theme_research_object_revision (
                    revision_id, change_set_id, theme_id, object_type, object_id,
                    object_version, operation, before_payload, after_payload, actor_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, 'restore', %s, %s, %s)
                """,
                (
                    f"revision-{uuid.uuid4()}",
                    change_set_id,
                    theme_id,
                    family,
                    object_id,
                    _object_row_version(cur, family, object_id),
                    Jsonb(before) if before is not None else None,
                    Jsonb(after) if after is not None else None,
                    actor_user_id,
                ),
            )


def _object_theme_id(
    family: str,
    row: dict[str, Any],
    desired: NormalizedThemeResearchPackage,
    current: NormalizedThemeResearchPackage,
) -> str:
    if family in {"themes", "nodes", "claims", "company_mappings"}:
        return str(row.get("theme_id") or "")
    nodes = {item["node_id"]: item["theme_id"] for item in (*current.nodes, *desired.nodes)}
    if family == "assessments":
        return str(nodes.get(row.get("node_id"), ""))
    if family == "mapping_evidence_items":
        evidence_id = row.get("evidence_id")
        mapping_ids = {
            link["mapping_id"]
            for link in (*current.company_mapping_evidence, *desired.company_mapping_evidence)
            if link["evidence_type"] == "mapping_evidence_item"
            and link["evidence_id"] == evidence_id
        }
        for mapping in (*current.company_mappings, *desired.company_mappings):
            if mapping["mapping_id"] in mapping_ids:
                return str(mapping["theme_id"])
    if family == "sources":
        source_id = row.get("source_id")
        for link in (*current.theme_sources, *desired.theme_sources):
            if link["source_id"] == source_id:
                return str(link["theme_id"])
    return "shared"


def _theme_row(cur, theme_id: str) -> dict[str, Any]:
    cur.execute(
        "SELECT theme_version, row_version FROM research.theme_research_theme WHERE theme_id = %s",
        (theme_id,),
    )
    row = cur.fetchone()
    if not row:
        raise ThemeResearchDomainError(
            f"theme not found: {theme_id}",
            code="THEME_RESEARCH_THEME_NOT_FOUND",
        )
    return dict(row)


def _object_row_version(cur, family: str, object_id: str) -> int:
    config = _OBJECT_CONFIG[family]
    cur.execute(
        f"SELECT row_version FROM research.{config['table']} WHERE {config['key']} = %s",
        (object_id,),
    )
    row = cur.fetchone()
    return int(row["row_version"]) if row else 1


def _object_counts(package: NormalizedThemeResearchPackage) -> dict[str, int]:
    return {
        name: len(getattr(package, name))
        for name in (
            "themes",
            "nodes",
            "sources",
            "theme_sources",
            "claims",
            "claim_sources",
            "claim_nodes",
            "assessments",
            "assessment_evidence",
            "company_mappings",
            "mapping_evidence_items",
            "company_mapping_evidence",
        )
    }


def _changed_theme_ids(
    current: NormalizedThemeResearchPackage,
    desired: NormalizedThemeResearchPackage,
    *,
    allow_deactivate: bool,
) -> set[str]:
    current_ids = {row["theme_id"] for row in current.themes}
    desired_ids = {row["theme_id"] for row in desired.themes}
    changed: set[str] = set()
    for theme_id in sorted(current_ids | desired_ids):
        if theme_id not in current_ids:
            changed.add(theme_id)
            continue
        if theme_id not in desired_ids:
            if allow_deactivate:
                changed.add(theme_id)
            continue
        theme_diff = semantic_diff(
            package_for_theme(current, theme_id),
            package_for_theme(desired, theme_id),
        )
        write_count = sum(
            len(theme_diff["families"][family][operation])
            for family in theme_diff["families"]
            for operation in ("insert", "update")
        )
        deactivate_count = sum(
            len(theme_diff["families"][family]["deactivate"])
            for family in theme_diff["families"]
        )
        if write_count or (allow_deactivate and deactivate_count):
            changed.add(theme_id)
    return changed


def _record_no_change_import(
    cur,
    *,
    package: NormalizedThemeResearchPackage,
    actor_user_id: str,
    actor_role: str,
    idempotency_key: str,
    request_fingerprint: str,
    result: dict[str, Any],
    diff: dict[str, Any],
) -> None:
    change_set_id = f"change-{uuid.uuid4()}"
    cur.execute(
        """
        INSERT INTO research.theme_research_change_set (
            change_set_id, change_type, actor_user_id, actor_role,
            idempotency_key, status, committed_at, metadata
        ) VALUES (%s, 'bootstrap_import', %s, %s, %s, 'committed', now(), %s)
        """,
        (
            change_set_id,
            actor_user_id,
            actor_role,
            idempotency_key,
            Jsonb(
                {
                    "request_fingerprint": request_fingerprint,
                    "result": result,
                }
            ),
        ),
    )
    cur.execute(
        """
        INSERT INTO research.theme_research_import_run (
            import_run_id, change_set_id, artifact_version, schema_version,
            package_sha256, mode, status, object_counts, semantic_diff,
            actor_user_id, finished_at
        ) VALUES (%s, %s, %s, 'theme_research_db_v1', %s, 'reconcile',
                  'no_changes', %s, %s, %s, now())
        ON CONFLICT DO NOTHING
        """,
        (
            f"import-{uuid.uuid4()}",
            change_set_id,
            package.artifact_version,
            package.package_sha256,
            Jsonb(_object_counts(package)),
            Jsonb(diff),
            actor_user_id,
        ),
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (date, datetime)):
            result[key] = value.isoformat()[:10] if isinstance(value, date) else value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = float(value)
        else:
            result[key] = value
    return result


def normalize_current_artifacts() -> NormalizedThemeResearchPackage:
    return normalize_artifact_package()
