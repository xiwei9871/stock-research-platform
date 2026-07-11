from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any

from psycopg import sql

from stock_research.config import SETTINGS
from stock_research.dashboard.auth_service import authenticate_user
from stock_research.db import connect
from stock_research.theme_research_db_models import ThemeResearchDomainError, require_admin


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
    artifact_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_by text NOT NULL
);

CREATE TABLE IF NOT EXISTS research.theme_research_node (
    node_id text PRIMARY KEY,
    theme_id text NOT NULL REFERENCES research.theme_research_theme(theme_id),
    parent_node_id text,
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
    CONSTRAINT uq_theme_research_node_theme_node UNIQUE (theme_id, node_id),
    CONSTRAINT fk_theme_research_node_parent_same_theme
        FOREIGN KEY (theme_id, parent_node_id)
        REFERENCES research.theme_research_node(theme_id, node_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT ck_theme_research_node_reviewed_evidence
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
    CONSTRAINT ck_theme_research_source_s4_not_accepted
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
    business_stage text NOT NULL DEFAULT '',
    product_or_service text NOT NULL DEFAULT '',
    relationship_summary text NOT NULL DEFAULT '',
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

CREATE TABLE IF NOT EXISTS research.theme_research_mapping_evidence_item (
    evidence_id text PRIMARY KEY,
    source_id text NOT NULL REFERENCES research.theme_research_source_item(source_id),
    evidence_type text NOT NULL CHECK (
        evidence_type IN ('product_relationship', 'service_relationship', 'customer_relationship',
                          'revenue_materiality', 'customer_validation', 'capacity_order',
                          'business_stage', 'company_mention')
    ),
    excerpt_locator text NOT NULL,
    evidence_summary text NOT NULL,
    related_company_codes jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(related_company_codes) = 'array'),
    related_node_ids jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(related_node_ids) = 'array'),
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_by text NOT NULL
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

CREATE OR REPLACE FUNCTION research.theme_research_assert_reviewed_claim(p_claim_id text)
RETURNS void AS $$
DECLARE
    claim_status text;
    primary_source_id text;
    accepted_count integer;
    rejected_count integer;
BEGIN
    SELECT platform_use_status, source_id
    INTO claim_status, primary_source_id
    FROM research.theme_research_content_claim
    WHERE claim_id = p_claim_id AND is_active = true;

    IF claim_status IS NULL OR claim_status <> 'reviewed' THEN
        RETURN;
    END IF;

    SELECT
        count(*) FILTER (
            WHERE s.is_active = true
              AND s.review_status = 'accepted'
              AND s.reliability_level <> 'S4'
        ),
        count(*) FILTER (WHERE s.is_active = true AND s.review_status = 'rejected')
    INTO accepted_count, rejected_count
    FROM research.theme_research_source_item s
    WHERE s.source_id = primary_source_id
       OR s.source_id IN (
            SELECT cs.source_id
            FROM research.theme_research_claim_source cs
            WHERE cs.claim_id = p_claim_id
       );

    IF rejected_count > 0 THEN
        RAISE EXCEPTION 'REVIEWED_CLAIM_USES_REJECTED_SOURCE';
    END IF;
    IF accepted_count = 0 THEN
        RAISE EXCEPTION 'REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE';
    END IF;
    RETURN;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION research.theme_research_check_reviewed_claim()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM research.theme_research_assert_reviewed_claim(OLD.claim_id);
        RETURN OLD;
    END IF;
    PERFORM research.theme_research_assert_reviewed_claim(NEW.claim_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION research.theme_research_check_source_claim_validity()
RETURNS trigger AS $$
DECLARE
    related_claim_id text;
BEGIN
    FOR related_claim_id IN
        SELECT claim_id
        FROM research.theme_research_content_claim
        WHERE source_id = NEW.source_id
        UNION
        SELECT claim_id
        FROM research.theme_research_claim_source
        WHERE source_id = NEW.source_id
    LOOP
        PERFORM research.theme_research_assert_reviewed_claim(related_claim_id);
    END LOOP;
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

CREATE OR REPLACE FUNCTION research.theme_research_check_active_claim_parents()
RETURNS trigger AS $$
DECLARE
    theme_active boolean;
    source_active boolean;
BEGIN
    IF NEW.is_active = false THEN
        RETURN NEW;
    END IF;
    SELECT is_active INTO theme_active
    FROM research.theme_research_theme WHERE theme_id = NEW.theme_id;
    SELECT is_active INTO source_active
    FROM research.theme_research_source_item WHERE source_id = NEW.source_id;
    IF theme_active IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'ACTIVE_CLAIM_REQUIRES_ACTIVE_THEME';
    END IF;
    IF source_active IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'ACTIVE_CLAIM_REQUIRES_ACTIVE_SOURCE';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION research.theme_research_check_active_assessment_parent()
RETURNS trigger AS $$
BEGIN
    IF NEW.is_active = true AND NOT EXISTS (
        SELECT 1 FROM research.theme_research_node
        WHERE node_id = NEW.node_id AND is_active = true
    ) THEN
        RAISE EXCEPTION 'ACTIVE_ASSESSMENT_REQUIRES_ACTIVE_NODE';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION research.theme_research_check_active_mapping_parents()
RETURNS trigger AS $$
BEGIN
    IF NEW.is_active = true AND NOT EXISTS (
        SELECT 1 FROM research.theme_research_theme
        WHERE theme_id = NEW.theme_id AND is_active = true
    ) THEN
        RAISE EXCEPTION 'ACTIVE_MAPPING_REQUIRES_ACTIVE_THEME';
    END IF;
    IF NEW.is_active = true AND NOT EXISTS (
        SELECT 1 FROM research.theme_research_node
        WHERE node_id = NEW.node_id AND theme_id = NEW.theme_id AND is_active = true
    ) THEN
        RAISE EXCEPTION 'ACTIVE_MAPPING_REQUIRES_ACTIVE_NODE';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION research.theme_research_check_active_mapping_evidence_parent()
RETURNS trigger AS $$
BEGIN
    IF NEW.is_active = true AND NOT EXISTS (
        SELECT 1 FROM research.theme_research_source_item
        WHERE source_id = NEW.source_id AND is_active = true
    ) THEN
        RAISE EXCEPTION 'ACTIVE_MAPPING_EVIDENCE_REQUIRES_ACTIVE_SOURCE';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_claim_active_parents') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_claim_active_parents
        AFTER INSERT OR UPDATE OF theme_id, source_id, is_active
        ON research.theme_research_content_claim
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_active_claim_parents();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_assessment_active_parent') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_assessment_active_parent
        AFTER INSERT OR UPDATE OF node_id, is_active
        ON research.theme_research_value_assessment
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_active_assessment_parent();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_mapping_active_parents') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_mapping_active_parents
        AFTER INSERT OR UPDATE OF theme_id, node_id, is_active
        ON research.theme_research_company_mapping
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_active_mapping_parents();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_mapping_evidence_active_parent') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_mapping_evidence_active_parent
        AFTER INSERT OR UPDATE OF source_id, is_active
        ON research.theme_research_mapping_evidence_item
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_active_mapping_evidence_parent();
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_source_claim_validity') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_source_claim_validity
        AFTER UPDATE OF review_status, reliability_level, is_active
        ON research.theme_research_source_item
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_source_claim_validity();
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_claim_source_validity') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_claim_source_validity
        AFTER INSERT OR UPDATE OR DELETE
        ON research.theme_research_claim_source
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

CREATE OR REPLACE FUNCTION research.theme_research_check_node_relationships()
RETURNS trigger AS $$
DECLARE
    theme_active boolean;
    parent_active boolean;
    parent_theme text;
BEGIN
    IF NEW.is_active = false THEN
        RETURN NEW;
    END IF;
    SELECT is_active INTO theme_active
    FROM research.theme_research_theme
    WHERE theme_id = NEW.theme_id;
    IF theme_active IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'ACTIVE_NODE_REQUIRES_ACTIVE_THEME';
    END IF;
    IF NEW.parent_node_id IS NOT NULL THEN
        SELECT theme_id, is_active INTO parent_theme, parent_active
        FROM research.theme_research_node
        WHERE node_id = NEW.parent_node_id;
        IF parent_theme IS DISTINCT FROM NEW.theme_id THEN
            RAISE EXCEPTION 'NODE_PARENT_THEME_MISMATCH';
        END IF;
        IF parent_active IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'ACTIVE_NODE_REQUIRES_ACTIVE_PARENT';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_node_relationships') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_node_relationships
        AFTER INSERT OR UPDATE OF theme_id, parent_node_id, is_active
        ON research.theme_research_node
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_node_relationships();
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_check_theme_children_active()
RETURNS trigger AS $$
BEGIN
    IF OLD.is_active = true AND NEW.is_active = false AND (
        EXISTS (SELECT 1 FROM research.theme_research_node WHERE theme_id = NEW.theme_id AND is_active = true)
        OR EXISTS (SELECT 1 FROM research.theme_research_content_claim WHERE theme_id = NEW.theme_id AND is_active = true)
        OR EXISTS (SELECT 1 FROM research.theme_research_company_mapping WHERE theme_id = NEW.theme_id AND is_active = true)
        OR EXISTS (SELECT 1 FROM research.theme_research_theme_source WHERE theme_id = NEW.theme_id)
    ) THEN
        RAISE EXCEPTION 'INACTIVE_THEME_HAS_ACTIVE_CHILDREN';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_theme_children_active') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_theme_children_active
        AFTER UPDATE OF is_active
        ON research.theme_research_theme
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_theme_children_active();
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_check_assessment_evidence()
RETURNS trigger AS $$
DECLARE
    evidence_exists boolean;
BEGIN
    IF NEW.evidence_type = 'source' THEN
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_source_item
            WHERE source_id = NEW.evidence_id AND is_active = true
        ) INTO evidence_exists;
    ELSE
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_content_claim
            WHERE claim_id = NEW.evidence_id AND is_active = true
        ) INTO evidence_exists;
    END IF;
    IF evidence_exists IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'ASSESSMENT_EVIDENCE_NOT_FOUND';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_assessment_evidence') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_assessment_evidence
        AFTER INSERT OR UPDATE
        ON research.theme_research_assessment_evidence
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_assessment_evidence();
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_check_mapping_evidence()
RETURNS trigger AS $$
DECLARE
    evidence_exists boolean;
BEGIN
    IF NEW.evidence_type = 'source' THEN
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_source_item
            WHERE source_id = NEW.evidence_id AND is_active = true
        ) INTO evidence_exists;
    ELSIF NEW.evidence_type = 'claim' THEN
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_content_claim
            WHERE claim_id = NEW.evidence_id AND is_active = true
        ) INTO evidence_exists;
    ELSE
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_mapping_evidence_item
            WHERE evidence_id = NEW.evidence_id AND is_active = true
        ) INTO evidence_exists;
    END IF;
    IF evidence_exists IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'COMPANY_MAPPING_EVIDENCE_NOT_FOUND';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_mapping_evidence') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_mapping_evidence
        AFTER INSERT OR UPDATE
        ON research.theme_research_company_mapping_evidence
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_mapping_evidence();
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_check_active_relationship()
RETURNS trigger AS $$
DECLARE
    valid boolean := false;
BEGIN
    IF TG_ARGV[0] = 'theme_source' THEN
        SELECT EXISTS (
            SELECT 1
            FROM research.theme_research_theme t
            JOIN research.theme_research_source_item s ON s.source_id = NEW.source_id
            WHERE t.theme_id = NEW.theme_id AND t.is_active = true AND s.is_active = true
        ) INTO valid;
    ELSIF TG_ARGV[0] = 'claim_source' THEN
        SELECT EXISTS (
            SELECT 1
            FROM research.theme_research_content_claim c
            JOIN research.theme_research_source_item s ON s.source_id = NEW.source_id
            WHERE c.claim_id = NEW.claim_id AND c.is_active = true AND s.is_active = true
        ) INTO valid;
    ELSIF TG_ARGV[0] = 'claim_node' THEN
        SELECT EXISTS (
            SELECT 1
            FROM research.theme_research_content_claim c
            JOIN research.theme_research_node n ON n.node_id = NEW.node_id
            WHERE c.claim_id = NEW.claim_id
              AND c.is_active = true
              AND n.is_active = true
              AND c.theme_id = n.theme_id
        ) INTO valid;
    ELSIF TG_ARGV[0] = 'assessment_evidence' THEN
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_value_assessment
            WHERE assessment_id = NEW.assessment_id AND is_active = true
        ) INTO valid;
    ELSIF TG_ARGV[0] = 'mapping_evidence' THEN
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_company_mapping
            WHERE mapping_id = NEW.mapping_id AND is_active = true
        ) INTO valid;
    END IF;
    IF valid IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'THEME_RESEARCH_RELATIONSHIP_REQUIRES_ACTIVE_PARENTS';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_theme_source_active') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_theme_source_active
        AFTER INSERT OR UPDATE ON research.theme_research_theme_source
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_active_relationship('theme_source');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_claim_source_active') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_claim_source_active
        AFTER INSERT OR UPDATE ON research.theme_research_claim_source
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_active_relationship('claim_source');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_claim_node_active') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_claim_node_active
        AFTER INSERT OR UPDATE ON research.theme_research_claim_node
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_active_relationship('claim_node');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_assessment_evidence_active') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_assessment_evidence_active
        AFTER INSERT OR UPDATE ON research.theme_research_assessment_evidence
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_active_relationship('assessment_evidence');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_mapping_evidence_active') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_mapping_evidence_active
        AFTER INSERT OR UPDATE ON research.theme_research_company_mapping_evidence
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_active_relationship('mapping_evidence');
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_check_deactivation_dependents()
RETURNS trigger AS $$
DECLARE
    dependent_exists boolean := false;
BEGIN
    IF OLD.is_active = false OR NEW.is_active = true THEN
        RETURN NEW;
    END IF;
    IF TG_ARGV[0] = 'node' THEN
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_node
            WHERE parent_node_id = NEW.node_id AND is_active = true
        ) OR EXISTS (
            SELECT 1
            FROM research.theme_research_claim_node cn
            JOIN research.theme_research_content_claim c ON c.claim_id = cn.claim_id
            WHERE cn.node_id = NEW.node_id AND c.is_active = true
        ) OR EXISTS (
            SELECT 1 FROM research.theme_research_value_assessment
            WHERE node_id = NEW.node_id AND is_active = true
        ) OR EXISTS (
            SELECT 1 FROM research.theme_research_company_mapping
            WHERE node_id = NEW.node_id AND is_active = true
        ) INTO dependent_exists;
        IF dependent_exists THEN
            RAISE EXCEPTION 'INACTIVE_NODE_HAS_ACTIVE_DEPENDENTS';
        END IF;
    ELSIF TG_ARGV[0] = 'source' THEN
        SELECT EXISTS (
            SELECT 1
            FROM research.theme_research_theme_source ts
            JOIN research.theme_research_theme t ON t.theme_id = ts.theme_id
            WHERE ts.source_id = NEW.source_id AND t.is_active = true
        ) OR EXISTS (
            SELECT 1 FROM research.theme_research_content_claim
            WHERE source_id = NEW.source_id AND is_active = true
        ) OR EXISTS (
            SELECT 1
            FROM research.theme_research_claim_source cs
            JOIN research.theme_research_content_claim c ON c.claim_id = cs.claim_id
            WHERE cs.source_id = NEW.source_id AND c.is_active = true
        ) OR EXISTS (
            SELECT 1 FROM research.theme_research_mapping_evidence_item
            WHERE source_id = NEW.source_id AND is_active = true
        ) OR EXISTS (
            SELECT 1
            FROM research.theme_research_assessment_evidence ae
            JOIN research.theme_research_value_assessment a ON a.assessment_id = ae.assessment_id
            WHERE ae.evidence_type = 'source' AND ae.evidence_id = NEW.source_id AND a.is_active = true
        ) OR EXISTS (
            SELECT 1
            FROM research.theme_research_company_mapping_evidence me
            JOIN research.theme_research_company_mapping m ON m.mapping_id = me.mapping_id
            WHERE me.evidence_type = 'source' AND me.evidence_id = NEW.source_id AND m.is_active = true
        ) INTO dependent_exists;
        IF dependent_exists THEN
            RAISE EXCEPTION 'INACTIVE_SOURCE_HAS_ACTIVE_DEPENDENTS';
        END IF;
    ELSIF TG_ARGV[0] = 'claim' THEN
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_claim_source WHERE claim_id = NEW.claim_id
        ) OR EXISTS (
            SELECT 1 FROM research.theme_research_claim_node WHERE claim_id = NEW.claim_id
        ) OR EXISTS (
            SELECT 1
            FROM research.theme_research_assessment_evidence ae
            JOIN research.theme_research_value_assessment a ON a.assessment_id = ae.assessment_id
            WHERE ae.evidence_type = 'claim' AND ae.evidence_id = NEW.claim_id AND a.is_active = true
        ) OR EXISTS (
            SELECT 1
            FROM research.theme_research_company_mapping_evidence me
            JOIN research.theme_research_company_mapping m ON m.mapping_id = me.mapping_id
            WHERE me.evidence_type = 'claim' AND me.evidence_id = NEW.claim_id AND m.is_active = true
        ) INTO dependent_exists;
        IF dependent_exists THEN
            RAISE EXCEPTION 'INACTIVE_CLAIM_HAS_ACTIVE_DEPENDENTS';
        END IF;
    ELSIF TG_ARGV[0] = 'assessment' THEN
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_assessment_evidence
            WHERE assessment_id = NEW.assessment_id
        ) INTO dependent_exists;
        IF dependent_exists THEN
            RAISE EXCEPTION 'INACTIVE_ASSESSMENT_HAS_ACTIVE_DEPENDENTS';
        END IF;
    ELSIF TG_ARGV[0] = 'mapping' THEN
        SELECT EXISTS (
            SELECT 1 FROM research.theme_research_company_mapping_evidence
            WHERE mapping_id = NEW.mapping_id
        ) INTO dependent_exists;
        IF dependent_exists THEN
            RAISE EXCEPTION 'INACTIVE_MAPPING_HAS_ACTIVE_DEPENDENTS';
        END IF;
    ELSIF TG_ARGV[0] = 'mapping_evidence_item' THEN
        SELECT EXISTS (
            SELECT 1
            FROM research.theme_research_company_mapping_evidence me
            JOIN research.theme_research_company_mapping m ON m.mapping_id = me.mapping_id
            WHERE me.evidence_type = 'mapping_evidence_item'
              AND me.evidence_id = NEW.evidence_id
              AND m.is_active = true
        ) INTO dependent_exists;
        IF dependent_exists THEN
            RAISE EXCEPTION 'INACTIVE_EVIDENCE_HAS_ACTIVE_DEPENDENTS';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_node_deactivation') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_node_deactivation
        AFTER UPDATE OF is_active ON research.theme_research_node
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_deactivation_dependents('node');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_source_deactivation') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_source_deactivation
        AFTER UPDATE OF is_active ON research.theme_research_source_item
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_deactivation_dependents('source');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_claim_deactivation') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_claim_deactivation
        AFTER UPDATE OF is_active ON research.theme_research_content_claim
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_deactivation_dependents('claim');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_assessment_deactivation') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_assessment_deactivation
        AFTER UPDATE OF is_active ON research.theme_research_value_assessment
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_deactivation_dependents('assessment');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_mapping_deactivation') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_mapping_deactivation
        AFTER UPDATE OF is_active ON research.theme_research_company_mapping
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_deactivation_dependents('mapping');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_mapping_evidence_deactivation') THEN
        CREATE CONSTRAINT TRIGGER trg_theme_research_mapping_evidence_deactivation
        AFTER UPDATE OF is_active ON research.theme_research_mapping_evidence_item
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_check_deactivation_dependents('mapping_evidence_item');
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_reject_version_decrease()
RETURNS trigger AS $$
DECLARE
    new_record jsonb := to_jsonb(NEW);
    old_record jsonb := to_jsonb(OLD);
BEGIN
    IF NEW.row_version < OLD.row_version THEN
        RAISE EXCEPTION 'THEME_RESEARCH_ROW_VERSION_DECREASE';
    END IF;
    IF TG_ARGV[0] = 'theme'
       AND (new_record ->> 'theme_version')::bigint < (old_record ->> 'theme_version')::bigint THEN
        RAISE EXCEPTION 'THEME_RESEARCH_THEME_VERSION_DECREASE';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_theme_version_monotonic') THEN
        CREATE TRIGGER trg_theme_research_theme_version_monotonic
        BEFORE UPDATE ON research.theme_research_theme
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_version_decrease('theme');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_node_version_monotonic') THEN
        CREATE TRIGGER trg_theme_research_node_version_monotonic
        BEFORE UPDATE ON research.theme_research_node
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_version_decrease('row');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_source_version_monotonic') THEN
        CREATE TRIGGER trg_theme_research_source_version_monotonic
        BEFORE UPDATE ON research.theme_research_source_item
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_version_decrease('row');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_claim_version_monotonic') THEN
        CREATE TRIGGER trg_theme_research_claim_version_monotonic
        BEFORE UPDATE ON research.theme_research_content_claim
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_version_decrease('row');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_assessment_version_monotonic') THEN
        CREATE TRIGGER trg_theme_research_assessment_version_monotonic
        BEFORE UPDATE ON research.theme_research_value_assessment
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_version_decrease('row');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_mapping_version_monotonic') THEN
        CREATE TRIGGER trg_theme_research_mapping_version_monotonic
        BEFORE UPDATE ON research.theme_research_company_mapping
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_version_decrease('row');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_mapping_evidence_version_monotonic') THEN
        CREATE TRIGGER trg_theme_research_mapping_evidence_version_monotonic
        BEFORE UPDATE ON research.theme_research_mapping_evidence_item
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_reject_version_decrease('row');
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION research.theme_research_protect_change_set()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'theme_research_change_set history cannot be truncated';
    END IF;
    IF OLD.status = 'committed' THEN
        RAISE EXCEPTION 'committed theme_research_change_set is immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'theme_research_change_set cannot be deleted';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_change_set_immutable') THEN
        CREATE TRIGGER trg_theme_research_change_set_immutable
        BEFORE UPDATE OR DELETE ON research.theme_research_change_set
        FOR EACH ROW EXECUTE FUNCTION research.theme_research_protect_change_set();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_change_set_no_truncate') THEN
        CREATE TRIGGER trg_theme_research_change_set_no_truncate
        BEFORE TRUNCATE ON research.theme_research_change_set
        FOR EACH STATEMENT EXECUTE FUNCTION research.theme_research_protect_change_set();
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
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_snapshot_no_truncate') THEN
        CREATE TRIGGER trg_theme_research_snapshot_no_truncate
        BEFORE TRUNCATE ON research.theme_research_snapshot
        FOR EACH STATEMENT EXECUTE FUNCTION research.theme_research_reject_mutation(
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
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_review_event_no_truncate') THEN
        CREATE TRIGGER trg_theme_research_review_event_no_truncate
        BEFORE TRUNCATE ON research.theme_research_review_event
        FOR EACH STATEMENT EXECUTE FUNCTION research.theme_research_reject_mutation(
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
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_theme_research_revision_no_truncate') THEN
        CREATE TRIGGER trg_theme_research_revision_no_truncate
        BEFORE TRUNCATE ON research.theme_research_object_revision
        FOR EACH STATEMENT EXECUTE FUNCTION research.theme_research_reject_mutation(
            'theme_research_object_revision is append-only'
        );
    END IF;
END;
$$;

DO $$
DECLARE
    relation_name text;
    function_name text;
    function_args text;
BEGIN
    FOR relation_name IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'research'
          AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'theme_research_%'
    LOOP
        EXECUTE format('REVOKE ALL ON TABLE research.%I FROM PUBLIC', relation_name);
        EXECUTE format('REVOKE ALL ON TABLE research.%I FROM theme_research_runtime', relation_name);
        EXECUTE format('ALTER TABLE research.%I OWNER TO theme_research_owner', relation_name);
    END LOOP;
    FOR function_name, function_args IN
        SELECT p.proname, pg_get_function_identity_arguments(p.oid)
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'research'
          AND p.proname LIKE 'theme_research_%'
    LOOP
        EXECUTE format(
            'REVOKE ALL ON FUNCTION research.%I(%s) FROM PUBLIC',
            function_name,
            function_args
        );
        EXECUTE format(
            'ALTER FUNCTION research.%I(%s) OWNER TO theme_research_owner',
            function_name,
            function_args
        );
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION research.%I(%s) TO theme_research_runtime',
            function_name,
            function_args
        );
    END LOOP;
END;
$$;

GRANT USAGE ON SCHEMA research TO theme_research_owner;
GRANT USAGE ON SCHEMA research TO theme_research_runtime;

GRANT SELECT ON
    research.theme_research_schema_migration,
    research.theme_research_store_state,
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
TO theme_research_runtime;

GRANT INSERT, UPDATE ON
    research.theme_research_store_state,
    research.theme_research_change_set,
    research.theme_research_theme,
    research.theme_research_node,
    research.theme_research_source_item,
    research.theme_research_content_claim,
    research.theme_research_value_assessment,
    research.theme_research_company_mapping,
    research.theme_research_mapping_evidence_item,
    research.theme_research_import_run
TO theme_research_runtime;

GRANT INSERT, DELETE ON
    research.theme_research_theme_source,
    research.theme_research_claim_source,
    research.theme_research_claim_node,
    research.theme_research_assessment_evidence,
    research.theme_research_company_mapping_evidence
TO theme_research_runtime;

GRANT INSERT ON
    research.theme_research_review_event,
    research.theme_research_object_revision,
    research.theme_research_snapshot
TO theme_research_runtime;
"""


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

REQUIRED_CONSTRAINTS = {
    "ck_theme_research_source_s4_not_accepted",
    "ck_theme_research_node_reviewed_evidence",
    "fk_theme_research_node_parent_same_theme",
}

REQUIRED_TRIGGERS = {
    "trg_theme_research_reviewed_claim",
    "trg_theme_research_source_claim_validity",
    "trg_theme_research_claim_source_validity",
    "trg_theme_research_claim_node_theme",
    "trg_theme_research_company_node_theme",
    "trg_theme_research_node_relationships",
    "trg_theme_research_theme_children_active",
    "trg_theme_research_assessment_evidence",
    "trg_theme_research_mapping_evidence",
    "trg_theme_research_theme_version_monotonic",
    "trg_theme_research_change_set_immutable",
    "trg_theme_research_change_set_no_truncate",
    "trg_theme_research_snapshot_append_only",
    "trg_theme_research_snapshot_no_truncate",
    "trg_theme_research_review_event_append_only",
    "trg_theme_research_review_event_no_truncate",
    "trg_theme_research_revision_append_only",
    "trg_theme_research_revision_no_truncate",
}

EXPECTED_THEME_RESEARCH_CATALOG_SHA256 = (
    "296c75c60f86b1606306d9599c04c4e25a5f06480184ec78f3cefbbf48a409b7"
)


def ddl_sha256() -> str:
    return hashlib.sha256(THEME_RESEARCH_SCHEMA_SQL.encode("utf-8")).hexdigest()


def provision_theme_research_roles(
    *,
    runtime_password: str,
    service: str = SETTINGS.theme_research_migration_service,
) -> dict[str, Any]:
    if not runtime_password:
        raise ThemeResearchDomainError(
            "runtime password is required",
            code="THEME_RESEARCH_RUNTIME_PASSWORD_REQUIRED",
        )
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user AS role_name")
            migration_login = str(cur.fetchone()["role_name"])
            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'theme_research_owner') THEN
                        CREATE ROLE theme_research_owner NOLOGIN;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'theme_research_runtime') THEN
                        CREATE ROLE theme_research_runtime NOLOGIN;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'theme_research_app') THEN
                        CREATE ROLE theme_research_app LOGIN;
                    END IF;
                END;
                $$
                """
            )
            cur.execute(
                "ALTER ROLE theme_research_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT"
            )
            cur.execute(
                "ALTER ROLE theme_research_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT"
            )
            cur.execute(
                sql.SQL(
                    "ALTER ROLE theme_research_app LOGIN NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOREPLICATION INHERIT PASSWORD {}"
                ).format(sql.Literal(runtime_password))
            )
            cur.execute(
                sql.SQL("GRANT theme_research_owner TO {}").format(
                    sql.Identifier(migration_login)
                )
            )
            cur.execute("GRANT theme_research_runtime TO theme_research_app")
            cur.execute("REVOKE theme_research_owner FROM theme_research_app")
    return {
        "status": "ok",
        "migration_login": migration_login,
        "runtime_login": "theme_research_app",
    }


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    if row is None:
        return None
    if hasattr(row, "get"):
        return row.get(key)
    return row[index]


def _load_theme_research_catalog_contract(cur) -> dict[str, Any]:
    queries = {
        "columns": """
            SELECT jsonb_build_object(
                'table', c.relname,
                'column', a.attname,
                'type', format_type(a.atttypid, a.atttypmod),
                'not_null', a.attnotnull,
                'default', COALESCE(pg_get_expr(d.adbin, d.adrelid), ''),
                'identity', a.attidentity,
                'generated', a.attgenerated
            )::text AS item
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
            WHERE n.nspname = 'research'
              AND c.relkind IN ('r', 'p')
              AND c.relname LIKE 'theme_research_%'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY c.relname, a.attnum
        """,
        "constraints": """
            SELECT jsonb_build_object(
                'table', c.relname,
                'name', con.conname,
                'type', con.contype,
                'deferrable', con.condeferrable,
                'deferred', con.condeferred,
                'validated', con.convalidated,
                'definition', pg_get_constraintdef(con.oid, true)
            )::text AS item
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'research'
              AND c.relname LIKE 'theme_research_%'
            ORDER BY c.relname, con.conname
        """,
        "indexes": """
            SELECT jsonb_build_object(
                'table', tablename,
                'name', indexname,
                'definition', indexdef
            )::text AS item
            FROM pg_indexes
            WHERE schemaname = 'research'
              AND tablename LIKE 'theme_research_%'
            ORDER BY tablename, indexname
        """,
        "triggers": """
            SELECT jsonb_build_object(
                'table', c.relname,
                'name', t.tgname,
                'enabled', t.tgenabled,
                'function_schema', pn.nspname,
                'function_name', p.proname,
                'definition', pg_get_triggerdef(t.oid, true)
            )::text AS item
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_proc p ON p.oid = t.tgfoid
            JOIN pg_namespace pn ON pn.oid = p.pronamespace
            WHERE n.nspname = 'research'
              AND c.relname LIKE 'theme_research_%'
              AND NOT t.tgisinternal
            ORDER BY c.relname, t.tgname
        """,
        "functions": """
            SELECT jsonb_build_object(
                'name', p.proname,
                'arguments', pg_get_function_identity_arguments(p.oid),
                'owner', pg_get_userbyid(p.proowner),
                'runtime_execute', has_function_privilege(
                    'theme_research_runtime', p.oid, 'EXECUTE'
                ),
                'definition', pg_get_functiondef(p.oid)
            )::text AS item
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'research'
              AND p.proname LIKE 'theme_research_%'
            ORDER BY p.proname, pg_get_function_identity_arguments(p.oid)
        """,
        "table_privileges": """
            SELECT jsonb_build_object(
                'table', c.relname,
                'owner', pg_get_userbyid(c.relowner),
                'select', has_table_privilege('theme_research_runtime', c.oid, 'SELECT'),
                'insert', has_table_privilege('theme_research_runtime', c.oid, 'INSERT'),
                'update', has_table_privilege('theme_research_runtime', c.oid, 'UPDATE'),
                'delete', has_table_privilege('theme_research_runtime', c.oid, 'DELETE'),
                'truncate', has_table_privilege('theme_research_runtime', c.oid, 'TRUNCATE'),
                'references', has_table_privilege('theme_research_runtime', c.oid, 'REFERENCES'),
                'trigger', has_table_privilege('theme_research_runtime', c.oid, 'TRIGGER')
            )::text AS item
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'research'
              AND c.relkind IN ('r', 'p')
              AND c.relname LIKE 'theme_research_%'
            ORDER BY c.relname
        """,
        "roles": """
            SELECT jsonb_build_object(
                'role', rolname,
                'superuser', rolsuper,
                'inherit', rolinherit,
                'create_role', rolcreaterole,
                'create_db', rolcreatedb,
                'can_login', rolcanlogin,
                'replication', rolreplication,
                'schema_usage', has_schema_privilege(rolname, 'research', 'USAGE')
            )::text AS item
            FROM pg_roles
            WHERE rolname IN (
                'theme_research_owner', 'theme_research_runtime', 'theme_research_app'
            )
            ORDER BY rolname
        """,
        "memberships": """
            SELECT jsonb_build_object(
                'member', member_role.rolname,
                'role', granted_role.rolname,
                'admin_option', membership.admin_option,
                'inherit_option', membership.inherit_option,
                'set_option', membership.set_option
            )::text AS item
            FROM pg_auth_members membership
            JOIN pg_roles granted_role ON granted_role.oid = membership.roleid
            JOIN pg_roles member_role ON member_role.oid = membership.member
            WHERE member_role.rolname = 'theme_research_app'
               OR (
                    granted_role.rolname IN ('theme_research_owner', 'theme_research_runtime')
                    AND member_role.rolname = 'theme_research_app'
               )
            ORDER BY member_role.rolname, granted_role.rolname
        """,
        "schema_privileges": """
            SELECT jsonb_build_object(
                'schema', n.nspname,
                'owner', pg_get_userbyid(n.nspowner),
                'runtime_usage', has_schema_privilege('theme_research_app', n.oid, 'USAGE'),
                'runtime_create', has_schema_privilege('theme_research_app', n.oid, 'CREATE'),
                'group_usage', has_schema_privilege('theme_research_runtime', n.oid, 'USAGE'),
                'group_create', has_schema_privilege('theme_research_runtime', n.oid, 'CREATE')
            )::text AS item
            FROM pg_namespace n
            WHERE n.nspname = 'research'
        """,
    }
    contract: dict[str, Any] = {}
    for section, query in queries.items():
        cur.execute(query)
        contract[section] = [
            json.loads(str(_row_value(row, "item"))) for row in cur.fetchall()
        ]
    return contract


def _catalog_sha256(contract: dict[str, Any]) -> str:
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def inspect_theme_research_schema(cur) -> dict[str, Any]:
    missing: list[str] = []
    existing_count = 0
    for table in sorted(REQUIRED_TABLES):
        cur.execute("SELECT to_regclass(%s) AS relation_name", (f"research.{table}",))
        row = cur.fetchone()
        if _row_value(row, "relation_name") is None:
            missing.append(f"table:{table}")
        else:
            existing_count += 1

    if existing_count:
        cur.execute(
            """
            SELECT conname
            FROM pg_constraint
            WHERE connamespace = 'research'::regnamespace
              AND conname = ANY(%s)
            """,
            (sorted(REQUIRED_CONSTRAINTS),),
        )
        constraint_rows = cur.fetchall()
        present_constraints = {
            str(_row_value(row, "conname")) for row in constraint_rows
        }
        missing.extend(
            f"constraint:{name}"
            for name in sorted(REQUIRED_CONSTRAINTS - present_constraints)
        )

        cur.execute(
            """
            SELECT tgname
            FROM pg_trigger
            WHERE NOT tgisinternal
              AND tgname = ANY(%s)
            """,
            (sorted(REQUIRED_TRIGGERS),),
        )
        trigger_rows = cur.fetchall()
        present_triggers = {str(_row_value(row, "tgname")) for row in trigger_rows}
        missing.extend(
            f"trigger:{name}"
            for name in sorted(REQUIRED_TRIGGERS - present_triggers)
        )

    catalog_sha256 = ""
    catalog_sha256_matches = False
    if existing_count == len(REQUIRED_TABLES):
        catalog_sha256 = _catalog_sha256(_load_theme_research_catalog_contract(cur))
        catalog_sha256_matches = catalog_sha256 == EXPECTED_THEME_RESEARCH_CATALOG_SHA256
        if not catalog_sha256_matches:
            missing.append("catalog:sha256")

    if existing_count == 0:
        status = "missing"
    elif missing:
        status = "drifted"
    else:
        status = "current"
    return {
        "status": status,
        "existing_count": existing_count,
        "missing": missing,
        "catalog_sha256": catalog_sha256,
        "catalog_sha256_matches": catalog_sha256_matches,
    }


def _load_applied_migration(cur) -> dict[str, Any] | None:
    cur.execute(
        "SELECT to_regclass('research.theme_research_schema_migration') AS relation_name"
    )
    relation = cur.fetchone()
    if _row_value(relation, "relation_name") is None:
        return None
    cur.execute(
        """
        SELECT schema_version, ddl_sha256, applied_at
        FROM research.theme_research_schema_migration
        WHERE schema_version = %s
        """,
        (THEME_RESEARCH_DB_SCHEMA_VERSION,),
    )
    row = cur.fetchone()
    if row is None or hasattr(row, "get"):
        return row
    return {
        "schema_version": row[0],
        "ddl_sha256": row[1],
        "applied_at": row[2],
    }


def apply_theme_research_schema(
    service: str = SETTINGS.theme_research_migration_service,
    *,
    actor_user_id: str,
    actor_role: str,
) -> dict[str, Any]:
    require_admin(actor_role)
    digest = ddl_sha256()
    with connect(service) as conn:
        with conn.cursor() as cur:
            migration = _load_applied_migration(cur)
            inspection = inspect_theme_research_schema(cur)
            if migration is not None:
                if migration.get("ddl_sha256") != digest or inspection["status"] != "current":
                    raise ThemeResearchDomainError(
                        "applied schema differs from the expected v1 contract",
                        code="THEME_RESEARCH_SCHEMA_DRIFT",
                        details={
                            "applied_ddl_sha256": str(migration.get("ddl_sha256") or ""),
                            "expected_ddl_sha256": digest,
                            "missing": inspection["missing"],
                        },
                    )
                return {
                    "status": "ok",
                    "schema_version": THEME_RESEARCH_DB_SCHEMA_VERSION,
                    "ddl_sha256": digest,
                }
            if inspection["existing_count"] > 0:
                raise ThemeResearchDomainError(
                    "partial unversioned theme research schema exists",
                    code="THEME_RESEARCH_PARTIAL_SCHEMA",
                    details={"missing": inspection["missing"]},
                )
            cur.execute(THEME_RESEARCH_SCHEMA_SQL)
            post_inspection = inspect_theme_research_schema(cur)
            if post_inspection["status"] != "current":
                raise ThemeResearchDomainError(
                    "schema application did not produce the expected contract",
                    code="THEME_RESEARCH_SCHEMA_APPLY_INCOMPLETE",
                    details={"missing": post_inspection["missing"]},
                )
            cur.execute(
                """
                INSERT INTO research.theme_research_schema_migration (
                    schema_version, applied_by, ddl_sha256, metadata
                )
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (schema_version) DO NOTHING
                """,
                (THEME_RESEARCH_DB_SCHEMA_VERSION, actor_user_id, digest, "{}"),
            )
    return {
        "status": "ok",
        "schema_version": THEME_RESEARCH_DB_SCHEMA_VERSION,
        "ddl_sha256": digest,
    }


def theme_research_schema_status(
    service: str = SETTINGS.theme_research_migration_service,
) -> dict[str, Any]:
    digest = ddl_sha256()
    with connect(service) as conn:
        with conn.cursor() as cur:
            row = _load_applied_migration(cur)
            inspection = inspect_theme_research_schema(cur)
    if not row and inspection["existing_count"] == 0:
        return {
            "status": "missing",
            "schema_version": THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": digest,
            "ddl_matches": False,
        }
    if not row:
        return {
            "status": "drifted",
            "schema_version": THEME_RESEARCH_DB_SCHEMA_VERSION,
            "ddl_sha256": digest,
            "ddl_matches": False,
            "missing": inspection["missing"],
        }
    applied_at = row.get("applied_at")
    ddl_matches = row.get("ddl_sha256") == digest and inspection["status"] == "current"
    return {
        "status": "current" if ddl_matches else "drifted",
        "schema_version": str(row.get("schema_version") or ""),
        "ddl_sha256": digest,
        "applied_ddl_sha256": str(row.get("ddl_sha256") or ""),
        "ddl_matches": ddl_matches,
        "applied_at": applied_at.isoformat() if isinstance(applied_at, datetime) else str(applied_at or ""),
        "missing": inspection["missing"],
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-research-db")
    parser.add_argument(
        "--migration-service",
        default=SETTINGS.theme_research_migration_service,
    )
    parser.add_argument("--auth-service", default=SETTINGS.research_service)
    parser.add_argument(
        "--runtime-service",
        default=SETTINGS.theme_research_runtime_service,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    provision_parser = subparsers.add_parser("provision-roles")
    provision_parser.add_argument("--admin-username", required=True)
    provision_parser.add_argument(
        "--admin-password-env",
        default="THEME_RESEARCH_ADMIN_PASSWORD",
    )
    provision_parser.add_argument(
        "--runtime-password-env",
        default="THEME_RESEARCH_RUNTIME_PASSWORD",
    )
    apply_parser = subparsers.add_parser("apply-schema")
    apply_parser.add_argument("--admin-username", required=True)
    apply_parser.add_argument(
        "--password-env",
        default="THEME_RESEARCH_ADMIN_PASSWORD",
    )
    subparsers.add_parser("schema-status")
    import_parser = subparsers.add_parser("import")
    import_mode = import_parser.add_mutually_exclusive_group(required=True)
    import_mode.add_argument("--dry-run", action="store_true")
    import_mode.add_argument("--execute", action="store_true")
    import_parser.add_argument("--expected-generation", type=int)
    import_parser.add_argument("--admin-username")
    import_parser.add_argument("--password-env", default="THEME_RESEARCH_ADMIN_PASSWORD")
    import_parser.add_argument("--idempotency-key", default="")
    import_parser.add_argument("--replace-theme")
    import_parser.add_argument("--artifact-dir")
    import_parser.add_argument("--company-mapping-dir")
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--artifact-dir")
    compare_parser.add_argument("--company-mapping-dir")
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--theme", required=True)
    export_parser.add_argument("--output-dir", required=True)
    export_parser.add_argument("--admin-username", required=True)
    export_parser.add_argument("--password-env", default="THEME_RESEARCH_ADMIN_PASSWORD")
    export_parser.add_argument("--idempotency-key", required=True)
    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--theme", required=True)
    rollback_parser.add_argument("--snapshot", required=True)
    rollback_parser.add_argument("--expected-version", required=True, type=int)
    rollback_parser.add_argument("--admin-username", required=True)
    rollback_parser.add_argument("--password-env", default="THEME_RESEARCH_ADMIN_PASSWORD")
    rollback_parser.add_argument("--comment", required=True)
    rollback_parser.add_argument("--idempotency-key", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "provision-roles":
            admin_password = os.getenv(args.admin_password_env, "")
            runtime_password = os.getenv(args.runtime_password_env, "")
            if not admin_password:
                raise ThemeResearchDomainError(
                    f"administrator password environment variable is empty: {args.admin_password_env}",
                    code="THEME_RESEARCH_ADMIN_PASSWORD_REQUIRED",
                )
            user = authenticate_user(
                args.admin_username,
                admin_password,
                service=args.auth_service,
            )
            require_admin(user.role)
            payload = provision_theme_research_roles(
                runtime_password=runtime_password,
                service=args.migration_service,
            )
        elif args.command == "apply-schema":
            password = os.getenv(args.password_env, "")
            if not password:
                raise ThemeResearchDomainError(
                    f"administrator password environment variable is empty: {args.password_env}",
                    code="THEME_RESEARCH_ADMIN_PASSWORD_REQUIRED",
                )
            user = authenticate_user(
                args.admin_username,
                password,
                service=args.auth_service,
            )
            require_admin(user.role)
            payload = apply_theme_research_schema(
                args.migration_service,
                actor_user_id=user.user_id,
                actor_role=user.role,
            )
        elif args.command == "schema-status":
            payload = theme_research_schema_status(args.migration_service)
        elif args.command == "import":
            from stock_research.theme_research_import import normalize_artifact_package
            from stock_research.theme_research_store import bootstrap_package, dry_run_package

            package = normalize_artifact_package(
                theme_artifact_dir=args.artifact_dir,
                company_mapping_dir=args.company_mapping_dir,
            )
            if args.dry_run:
                payload = dry_run_package(
                    package,
                    replace_theme=args.replace_theme,
                    service=args.runtime_service,
                )
            else:
                if args.expected_generation is None:
                    raise ThemeResearchDomainError(
                        "--expected-generation is required with --execute",
                        code="THEME_RESEARCH_IMPORT_REQUEST_INVALID",
                    )
                if not args.admin_username:
                    raise ThemeResearchDomainError(
                        "--admin-username is required with --execute",
                        code="THEME_RESEARCH_IMPORT_REQUEST_INVALID",
                    )
                password = os.getenv(args.password_env, "")
                if not password:
                    raise ThemeResearchDomainError(
                        f"administrator password environment variable is empty: {args.password_env}",
                        code="THEME_RESEARCH_ADMIN_PASSWORD_REQUIRED",
                    )
                user = authenticate_user(
                    args.admin_username,
                    password,
                    service=args.auth_service,
                )
                require_admin(user.role)
                payload = bootstrap_package(
                    package,
                    actor_user_id=user.user_id,
                    actor_role=user.role,
                    expected_generation=args.expected_generation,
                    idempotency_key=args.idempotency_key,
                    replace_theme=args.replace_theme,
                    service=args.runtime_service,
                )
        elif args.command == "compare":
            from stock_research.theme_research_import import (
                normalize_artifact_package,
                semantic_diff,
            )
            from stock_research.theme_research_store import load_database_package

            artifact_package = normalize_artifact_package(
                theme_artifact_dir=args.artifact_dir,
                company_mapping_dir=args.company_mapping_dir,
            )
            database_package = load_database_package(service=args.runtime_service)
            diff = semantic_diff(database_package, artifact_package)
            payload = {
                "status": "match" if not diff["has_changes"] else "mismatch",
                "artifact_package_sha256": artifact_package.package_sha256,
                "database_package_sha256": database_package.package_sha256,
                "semantic_diff": diff,
            }
        elif args.command == "export":
            from stock_research.theme_research_store import export_theme

            password = os.getenv(args.password_env, "")
            if not password:
                raise ThemeResearchDomainError(
                    f"administrator password environment variable is empty: {args.password_env}",
                    code="THEME_RESEARCH_ADMIN_PASSWORD_REQUIRED",
                )
            user = authenticate_user(
                args.admin_username,
                password,
                service=args.auth_service,
            )
            require_admin(user.role)
            payload = export_theme(
                args.theme,
                output_dir=args.output_dir,
                actor_user_id=user.user_id,
                actor_role=user.role,
                idempotency_key=args.idempotency_key,
                service=args.runtime_service,
            )
        elif args.command == "rollback":
            from stock_research.theme_research_store import rollback_theme

            password = os.getenv(args.password_env, "")
            if not password:
                raise ThemeResearchDomainError(
                    f"administrator password environment variable is empty: {args.password_env}",
                    code="THEME_RESEARCH_ADMIN_PASSWORD_REQUIRED",
                )
            user = authenticate_user(
                args.admin_username,
                password,
                service=args.auth_service,
            )
            require_admin(user.role)
            payload = rollback_theme(
                theme_id=args.theme,
                snapshot_id=args.snapshot,
                expected_theme_version=args.expected_version,
                actor_user_id=user.user_id,
                actor_role=user.role,
                comment=args.comment,
                idempotency_key=args.idempotency_key,
                service=args.runtime_service,
            )
        else:  # pragma: no cover
            raise AssertionError(f"unhandled command: {args.command}")
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if payload.get("status") in {
            "ok", "current", "dry_run", "committed", "no_changes", "exported",
            "rolled_back", "match",
        } else 2
    except Exception as exc:
        code = getattr(exc, "code", "THEME_RESEARCH_SCHEMA_ERROR")
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_code": code,
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
