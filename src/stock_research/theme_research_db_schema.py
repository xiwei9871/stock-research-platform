from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


THEME_RESEARCH_DB_SCHEMA_VERSION = "theme_research_db_v1"

THEME_RESEARCH_SCHEMA_SQL = r"""
CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.theme_research_schema_migration (
    schema_version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now(),
    applied_by text NOT NULL,
    ddl_sha256 text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS research.theme_research_store_state (
    state_id boolean PRIMARY KEY DEFAULT true CHECK (state_id),
    generation bigint NOT NULL DEFAULT 0 CHECK (generation >= 0),
    package_sha256 text NOT NULL DEFAULT '',
    artifact_version text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text NOT NULL DEFAULT 'system'
);

INSERT INTO research.theme_research_store_state (state_id)
VALUES (true)
ON CONFLICT (state_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS research.theme_research_change_set (
    change_set_id text PRIMARY KEY,
    change_type text NOT NULL CHECK (
        change_type IN ('bootstrap_import', 'review_transition', 'admin_update', 'rollback', 'export')
    ),
    theme_id text,
    actor_user_id text NOT NULL,
    actor_role text NOT NULL CHECK (actor_role IN ('admin', 'user', 'system')),
    request_id text NOT NULL DEFAULT '',
    idempotency_key text NOT NULL DEFAULT '',
    expected_theme_version bigint,
    resulting_theme_version bigint,
    status text NOT NULL CHECK (status IN ('prepared', 'committed', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    committed_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_research_change_set_idempotency
    ON research.theme_research_change_set (actor_user_id, idempotency_key)
    WHERE idempotency_key <> '';

CREATE TABLE IF NOT EXISTS research.theme_research_theme (
    theme_id text PRIMARY KEY,
    theme_name text NOT NULL,
    theme_type text NOT NULL CHECK (
        theme_type IN ('ai_power', 'humanoid_robotics', 'ai_compute', 'semiconductor_equipment',
                       'industrial_software', 'other')
    ),
    summary text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'reviewed', 'published')),
    created_from text NOT NULL CHECK (created_from IN ('video', 'report', 'manual', 'mixed')),
    last_updated date NOT NULL,
    theme_version bigint NOT NULL DEFAULT 1 CHECK (theme_version >= 1),
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    content_sha256 text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_by text NOT NULL
);

CREATE TABLE IF NOT EXISTS research.theme_research_node (
    node_id text PRIMARY KEY,
    theme_id text NOT NULL REFERENCES research.theme_research_theme(theme_id),
    parent_node_id text REFERENCES research.theme_research_node(node_id)
        DEFERRABLE INITIALLY DEFERRED,
    node_name text NOT NULL,
    node_type text NOT NULL CHECK (
        node_type IN ('upstream_material', 'core_component', 'subsystem', 'equipment',
                      'infrastructure', 'software', 'service', 'downstream_application')
    ),
    description text NOT NULL,
    value_capture_score integer NOT NULL CHECK (value_capture_score BETWEEN 0 AND 5),
    bottleneck_score integer NOT NULL CHECK (bottleneck_score BETWEEN 0 AND 5),
    localization_gap_score integer NOT NULL CHECK (localization_gap_score BETWEEN 0 AND 5),
    supply_tightness_score integer NOT NULL CHECK (supply_tightness_score BETWEEN 0 AND 5),
    evidence_strength integer NOT NULL CHECK (evidence_strength BETWEEN 0 AND 5),
    node_review_status text NOT NULL CHECK (
        node_review_status IN ('draft', 'reviewed', 'needs_evidence', 'blocked')
    ),
    key_metrics jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(key_metrics) = 'array'),
    overseas_leaders jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(overseas_leaders) = 'array'),
    domestic_players jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(domestic_players) = 'array'),
    related_stock_codes jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(related_stock_codes) = 'array'),
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_by text NOT NULL,
    CHECK (node_review_status <> 'reviewed' OR evidence_strength >= 3)
);

CREATE TABLE IF NOT EXISTS research.theme_research_source_item (
    source_id text PRIMARY KEY,
    source_type text NOT NULL CHECK (
        source_type IN ('official_report', 'official_article', 'broker_report', 'media_article',
                        'video_claim', 'social_post', 'company_filing', 'unknown')
    ),
    title text NOT NULL,
    publisher text NOT NULL,
    author text NOT NULL DEFAULT '',
    publish_date date,
    url_or_ref text NOT NULL,
    access_level text NOT NULL CHECK (access_level IN ('public', 'gated', 'private_claimed', 'unknown')),
    reliability_level text NOT NULL CHECK (reliability_level IN ('S0', 'S1', 'S2', 'S3', 'S4')),
    review_status text NOT NULL CHECK (
        review_status IN ('accepted', 'needs_full_text', 'lead_only', 'rejected', 'unknown')
    ),
    notes text NOT NULL DEFAULT '',
    content_sha256 text NOT NULL DEFAULT '',
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_by text NOT NULL,
    CHECK (reliability_level <> 'S4' OR review_status <> 'accepted')
);

CREATE TABLE IF NOT EXISTS research.theme_research_theme_source (
    theme_id text NOT NULL REFERENCES research.theme_research_theme(theme_id) ON DELETE CASCADE,
    source_id text NOT NULL REFERENCES research.theme_research_source_item(source_id),
    link_reason text NOT NULL CHECK (
        link_reason IN ('primary_claim', 'supporting_claim', 'assessment', 'company_mapping', 'manual')
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (theme_id, source_id, link_reason)
);

CREATE TABLE IF NOT EXISTS research.theme_research_content_claim (
    claim_id text PRIMARY KEY,
    theme_id text NOT NULL REFERENCES research.theme_research_theme(theme_id),
    source_id text NOT NULL REFERENCES research.theme_research_source_item(source_id),
    claim_text text NOT NULL,
    claim_type text NOT NULL CHECK (
        claim_type IN ('demand_shock', 'bottleneck', 'value_capture', 'supply_constraint',
                       'localization', 'company_mapping', 'cost_structure', 'tech_route',
                       'valuation_signal')
    ),
    confidence numeric NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_status text NOT NULL CHECK (
        evidence_status IN ('verified', 'partially_verified', 'unverified', 'contradicted')
    ),
    platform_use_status text NOT NULL CHECK (
        platform_use_status IN ('research_lead', 'draft', 'reviewed', 'blocked')
    ),
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_by text NOT NULL
);

CREATE TABLE IF NOT EXISTS research.theme_research_claim_source (
    claim_id text NOT NULL REFERENCES research.theme_research_content_claim(claim_id) ON DELETE CASCADE,
    source_id text NOT NULL REFERENCES research.theme_research_source_item(source_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (claim_id, source_id)
);

CREATE TABLE IF NOT EXISTS research.theme_research_claim_node (
    claim_id text NOT NULL REFERENCES research.theme_research_content_claim(claim_id) ON DELETE CASCADE,
    node_id text NOT NULL REFERENCES research.theme_research_node(node_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (claim_id, node_id)
);

CREATE TABLE IF NOT EXISTS research.theme_research_value_assessment (
    assessment_id text PRIMARY KEY,
    node_id text NOT NULL REFERENCES research.theme_research_node(node_id),
    value_basis text NOT NULL CHECK (
        value_basis IN ('BOM_share', 'ASP', 'gross_margin', 'scarcity', 'integration_control',
                        'customer_certification', 'capacity_constraint', 'technology_barrier')
    ),
    assessment_text text NOT NULL,
    rank integer NOT NULL CHECK (rank >= 1),
    uncertainty text NOT NULL,
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_by text NOT NULL
);

CREATE TABLE IF NOT EXISTS research.theme_research_assessment_evidence (
    assessment_id text NOT NULL REFERENCES research.theme_research_value_assessment(assessment_id) ON DELETE CASCADE,
    evidence_type text NOT NULL CHECK (evidence_type IN ('source', 'claim')),
    evidence_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (assessment_id, evidence_type, evidence_id)
);

CREATE TABLE IF NOT EXISTS research.theme_research_company_mapping (
    mapping_id text PRIMARY KEY,
    theme_id text NOT NULL REFERENCES research.theme_research_theme(theme_id),
    node_id text NOT NULL REFERENCES research.theme_research_node(node_id),
    company_code text NOT NULL,
    company_name text NOT NULL,
    market text NOT NULL,
    mapping_type text NOT NULL CHECK (
        mapping_type IN ('direct_product', 'component_supplier', 'equipment_supplier',
                         'material_supplier', 'system_integrator', 'downstream_customer')
    ),
    confidence numeric NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    revenue_relevance text NOT NULL,
    bottleneck_relevance text NOT NULL,
    business_materiality text NOT NULL DEFAULT '',
    review_status text NOT NULL DEFAULT 'draft' CHECK (
        review_status IN ('draft', 'reviewed', 'needs_evidence', 'blocked')
    ),
    notes text NOT NULL DEFAULT '',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_by text NOT NULL,
    UNIQUE (theme_id, node_id, company_code, mapping_type)
);

CREATE TABLE IF NOT EXISTS research.theme_research_company_mapping_evidence (
    mapping_id text NOT NULL REFERENCES research.theme_research_company_mapping(mapping_id) ON DELETE CASCADE,
    evidence_type text NOT NULL CHECK (
        evidence_type IN ('source', 'claim', 'mapping_evidence_item')
    ),
    evidence_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (mapping_id, evidence_type, evidence_id)
);

CREATE TABLE IF NOT EXISTS research.theme_research_review_event (
    review_event_id text PRIMARY KEY,
    change_set_id text NOT NULL REFERENCES research.theme_research_change_set(change_set_id),
    theme_id text NOT NULL REFERENCES research.theme_research_theme(theme_id),
    object_type text NOT NULL CHECK (object_type IN ('source', 'claim', 'node', 'theme', 'rollback')),
    object_id text NOT NULL,
    from_status text NOT NULL,
    to_status text NOT NULL,
    decision text NOT NULL,
    reviewer_user_id text NOT NULL,
    reviewer_role text NOT NULL CHECK (reviewer_role IN ('admin', 'user', 'system')),
    comment text NOT NULL CHECK (length(btrim(comment)) > 0),
    request_id text NOT NULL,
    idempotency_key text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.theme_research_object_revision (
    revision_id text PRIMARY KEY,
    change_set_id text NOT NULL REFERENCES research.theme_research_change_set(change_set_id),
    theme_id text NOT NULL,
    object_type text NOT NULL,
    object_id text NOT NULL,
    object_version bigint NOT NULL CHECK (object_version >= 1),
    operation text NOT NULL CHECK (operation IN ('insert', 'update', 'deactivate', 'restore')),
    before_payload jsonb,
    after_payload jsonb,
    actor_user_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (object_type, object_id, object_version)
);

CREATE TABLE IF NOT EXISTS research.theme_research_import_run (
    import_run_id text PRIMARY KEY,
    change_set_id text REFERENCES research.theme_research_change_set(change_set_id),
    artifact_version text NOT NULL,
    schema_version text NOT NULL,
    package_sha256 text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('dry_run', 'bootstrap', 'reconcile')),
    status text NOT NULL CHECK (status IN ('prepared', 'committed', 'failed', 'no_changes')),
    object_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    semantic_diff jsonb NOT NULL DEFAULT '{}'::jsonb,
    actor_user_id text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    error_code text NOT NULL DEFAULT '',
    error_message text NOT NULL DEFAULT '',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_research_import_successful_package
    ON research.theme_research_import_run (package_sha256, mode)
    WHERE status IN ('committed', 'no_changes');

CREATE TABLE IF NOT EXISTS research.theme_research_snapshot (
    snapshot_id text PRIMARY KEY,
    theme_id text NOT NULL,
    theme_version bigint NOT NULL CHECK (theme_version >= 1),
    snapshot_type text NOT NULL CHECK (
        snapshot_type IN ('import', 'pre_change', 'post_change', 'export', 'rollback')
    ),
    artifact_version text NOT NULL,
    payload jsonb NOT NULL,
    payload_sha256 text NOT NULL,
    source_change_set_id text NOT NULL REFERENCES research.theme_research_change_set(change_set_id),
    actor_user_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (theme_id, theme_version, snapshot_type, payload_sha256)
);

CREATE INDEX IF NOT EXISTS idx_theme_research_node_theme
    ON research.theme_research_node (theme_id, is_active, node_review_status);
CREATE INDEX IF NOT EXISTS idx_theme_research_source_review
    ON research.theme_research_source_item (review_status, reliability_level, is_active);
CREATE INDEX IF NOT EXISTS idx_theme_research_claim_theme
    ON research.theme_research_content_claim (theme_id, platform_use_status, is_active);
CREATE INDEX IF NOT EXISTS idx_theme_research_company_theme
    ON research.theme_research_company_mapping (theme_id, company_code, is_active);
CREATE INDEX IF NOT EXISTS idx_theme_research_review_object
    ON research.theme_research_review_event (object_type, object_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_theme_research_revision_object
    ON research.theme_research_object_revision (object_type, object_id, object_version DESC);
CREATE INDEX IF NOT EXISTS idx_theme_research_snapshot_theme
    ON research.theme_research_snapshot (theme_id, theme_version DESC, created_at DESC);

CREATE OR REPLACE FUNCTION research.theme_research_check_reviewed_claim()
RETURNS trigger AS $$
DECLARE
    accepted_count integer;
    rejected_count integer;
BEGIN
    IF NEW.platform_use_status <> 'reviewed' THEN
        RETURN NEW;
    END IF;

    SELECT
        count(*) FILTER (WHERE s.review_status = 'accepted' AND s.reliability_level <> 'S4'),
        count(*) FILTER (WHERE s.review_status = 'rejected')
    INTO accepted_count, rejected_count
    FROM research.theme_research_source_item s
    WHERE s.source_id = NEW.source_id
       OR s.source_id IN (
            SELECT cs.source_id
            FROM research.theme_research_claim_source cs
            WHERE cs.claim_id = NEW.claim_id
       );

    IF rejected_count > 0 THEN
        RAISE EXCEPTION 'REVIEWED_CLAIM_USES_REJECTED_SOURCE';
    END IF;
    IF accepted_count = 0 THEN
        RAISE EXCEPTION 'REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_reviewed_claim') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_reviewed_claim
        AFTER INSERT OR UPDATE OF platform_use_status, source_id
        ON research.theme_research_content_claim
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_reviewed_claim();
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_check_claim_node_theme()
RETURNS trigger AS $$
DECLARE
    claim_theme text;
    node_theme text;
BEGIN
    SELECT theme_id INTO claim_theme
    FROM research.theme_research_content_claim
    WHERE claim_id = NEW.claim_id;
    SELECT theme_id INTO node_theme
    FROM research.theme_research_node
    WHERE node_id = NEW.node_id;
    IF claim_theme IS DISTINCT FROM node_theme THEN
        RAISE EXCEPTION 'CLAIM_NODE_THEME_MISMATCH';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_claim_node_theme') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_claim_node_theme
        AFTER INSERT OR UPDATE
        ON research.theme_research_claim_node
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_claim_node_theme();
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_check_company_node_theme()
RETURNS trigger AS $$
DECLARE
    node_theme text;
BEGIN
    SELECT theme_id INTO node_theme
    FROM research.theme_research_node
    WHERE node_id = NEW.node_id;
    IF NEW.theme_id IS DISTINCT FROM node_theme THEN
        RAISE EXCEPTION 'COMPANY_MAPPING_NODE_THEME_MISMATCH';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_company_node_theme') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_company_node_theme
        AFTER INSERT OR UPDATE OF theme_id, node_id
        ON research.theme_research_company_mapping
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_company_node_theme();
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_reject_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '%', TG_ARGV[0];
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_snapshot_append_only') THEN
        CREATE TRIGGER trg_theme_research_snapshot_append_only
        BEFORE UPDATE OR DELETE ON research.theme_research_snapshot
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_mutation(
            'theme_research_snapshot is append-only'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_review_event_append_only') THEN
        CREATE TRIGGER trg_theme_research_review_event_append_only
        BEFORE UPDATE OR DELETE ON research.theme_research_review_event
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_mutation(
            'theme_research_review_event is append-only'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_revision_append_only') THEN
        CREATE TRIGGER trg_theme_research_revision_append_only
        BEFORE UPDATE OR DELETE ON research.theme_research_object_revision
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_mutation(
            'theme_research_object_revision is append-only'
        );
    END IF;
END;
$$;
"""


def ddl_sha256() -> str:
    return hashlib.sha256(THEME_RESEARCH_SCHEMA_SQL.encode("utf-8")).hexdigest()


def apply_theme_research_schema(
    service: str = SETTINGS.research_service,
    *,
    applied_by: str = "system",
) -> dict[str, Any]:
    digest = ddl_sha256()
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(THEME_RESEARCH_SCHEMA_SQL)
            cur.execute(
                """
                INSERT INTO research.theme_research_schema_migration (
                    schema_version, applied_by, ddl_sha256, metadata
                )
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (schema_version) DO UPDATE
                SET applied_at = now(),
                    applied_by = EXCLUDED.applied_by,
                    ddl_sha256 = EXCLUDED.ddl_sha256,
                    metadata = EXCLUDED.metadata
                """,
                (THEME_RESEARCH_DB_SCHEMA_VERSION, applied_by, digest, "{}"),
            )
    return {
        "status": "ok",
        "schema_version": THEME_RESEARCH_DB_SCHEMA_VERSION,
        "ddl_sha256": digest,
    }


def theme_research_schema_status(
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    digest = ddl_sha256()
    try:
        with connect(service) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT schema_version, ddl_sha256, applied_at
                    FROM research.theme_research_schema_migration
                    WHERE schema_version = %s
                    """,
                    (THEME_RESEARCH_DB_SCHEMA_VERSION,),
                )
                row = cur.fetchone()
    except Exception:
        row = None
    if not row:
        return {
            "status": "missing",
            "schema_version": THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": digest,
            "ddl_matches": False,
        }
    applied_at = row.get("applied_at")
    return {
        "status": "current" if row.get("ddl_sha256") == digest else "drifted",
        "schema_version": str(row.get("schema_version") or ""),
        "ddl_sha256": digest,
        "applied_ddl_sha256": str(row.get("ddl_sha256") or ""),
        "ddl_matches": row.get("ddl_sha256") == digest,
        "applied_at": applied_at.isoformat() if isinstance(applied_at, datetime) else str(applied_at or ""),
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-research-db")
    parser.add_argument("--service", default=SETTINGS.research_service)
    subparsers = parser.add_subparsers(dest="command", required=True)
    apply_parser = subparsers.add_parser("apply-schema")
    apply_parser.add_argument("--applied-by", default="system")
    subparsers.add_parser("schema-status")
    args = parser.parse_args(argv)
    try:
        if args.command == "apply-schema":
            payload = apply_theme_research_schema(args.service, applied_by=args.applied_by)
        elif args.command == "schema-status":
            payload = theme_research_schema_status(args.service)
        else:  # pragma: no cover
            raise AssertionError(f"unhandled command: {args.command}")
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if payload.get("status") in {"ok", "current"} else 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_code": "THEME_RESEARCH_SCHEMA_ERROR",
                    "message": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
