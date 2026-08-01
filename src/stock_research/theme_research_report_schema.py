from __future__ import annotations

import argparse
import json

from stock_research.config import SETTINGS
from stock_research.db import connect


THEME_RESEARCH_REPORT_SCHEMA_VERSION = "4"

THEME_RESEARCH_REPORT_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.theme_research_report_version (
    report_version_id text CONSTRAINT pk_theme_research_report_version PRIMARY KEY,
    theme_id text NOT NULL CONSTRAINT fk_theme_research_report_version_theme
        REFERENCES research.theme_research_theme(theme_id),
    version text NOT NULL,
    title text NOT NULL,
    summary text NOT NULL,
    status text NOT NULL DEFAULT 'pending_review'
        CONSTRAINT ck_theme_research_report_version_status CHECK (
        status IN ('pending_review', 'published', 'rejected', 'archived')
    ),
    markdown_relative_path text NOT NULL,
    markdown_sha256 text NOT NULL,
    pdf_relative_path text,
    pdf_sha256 text,
    manifest_relative_path text NOT NULL,
    manifest_sha256 text NOT NULL,
    generator_name text NOT NULL DEFAULT '',
    generator_version text NOT NULL DEFAULT '',
    generator_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    generated_at timestamptz NOT NULL DEFAULT now(),
    indexed_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    published_by_user_id text CONSTRAINT fk_theme_research_report_version_published_by
        REFERENCES identity.user_account(user_id),
    rejected_at timestamptz,
    rejected_by_user_id text CONSTRAINT fk_theme_research_report_version_rejected_by
        REFERENCES identity.user_account(user_id),
    rejection_reason text NOT NULL DEFAULT '',
    row_version bigint NOT NULL DEFAULT 1
        CONSTRAINT ck_theme_research_report_row_version CHECK (row_version >= 1),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_theme_research_report_theme_version UNIQUE (theme_id, version),
    CONSTRAINT ck_theme_research_report_pdf_pair CHECK (
        (pdf_relative_path IS NULL AND pdf_sha256 IS NULL)
        OR (pdf_relative_path IS NOT NULL AND pdf_sha256 IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_research_report_one_published
    ON research.theme_research_report_version (theme_id)
    WHERE status = 'published';

CREATE INDEX IF NOT EXISTS idx_theme_research_report_status_generated
    ON research.theme_research_report_version (status, generated_at DESC);

CREATE TABLE IF NOT EXISTS research.theme_research_report_review_event (
    event_id text CONSTRAINT pk_theme_research_report_review_event PRIMARY KEY,
    report_version_id text NOT NULL
        CONSTRAINT fk_theme_research_report_review_event_version
        REFERENCES research.theme_research_report_version(report_version_id),
    from_status text CONSTRAINT ck_theme_research_report_review_from_status CHECK (
        from_status IS NULL
        OR from_status IN ('pending_review', 'published', 'rejected', 'archived')
    ),
    to_status text NOT NULL
        CONSTRAINT ck_theme_research_report_review_to_status CHECK (
        to_status IN ('pending_review', 'published', 'rejected', 'archived')
    ),
    actor_user_id text NOT NULL,
    comment text NOT NULL DEFAULT '',
    request_id text NOT NULL DEFAULT '',
    idempotency_key text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE research.theme_research_report_review_event
    DROP CONSTRAINT IF EXISTS fk_theme_research_report_review_event_actor;

CREATE INDEX IF NOT EXISTS idx_theme_research_report_review_version_created
    ON research.theme_research_report_review_event (report_version_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_research_report_review_actor_idempotency
    ON research.theme_research_report_review_event (actor_user_id, idempotency_key)
    WHERE idempotency_key <> '';

CREATE OR REPLACE FUNCTION research.register_theme_research_report_pending(
    p_report_version_id text,
    p_theme_id text,
    p_version text,
    p_title text,
    p_summary text,
    p_markdown_relative_path text,
    p_markdown_sha256 text,
    p_pdf_relative_path text,
    p_pdf_sha256 text,
    p_manifest_relative_path text,
    p_manifest_sha256 text,
    p_generator_name text,
    p_generator_version text,
    p_generator_metadata jsonb,
    p_generated_at timestamptz,
    p_metadata jsonb,
    p_event_id text,
    p_request_id text,
    p_idempotency_key text
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'theme-research-report-register-lock' || E'\\x1f' ||
            p_theme_id || E'\\x1f' || p_version,
            0
        )
    );
    INSERT INTO research.theme_research_report_version (
        report_version_id, theme_id, version, title, summary, status,
        markdown_relative_path, markdown_sha256,
        pdf_relative_path, pdf_sha256,
        manifest_relative_path, manifest_sha256,
        generator_name, generator_version, generator_metadata,
        generated_at, metadata, row_version
    ) VALUES (
        p_report_version_id, p_theme_id, p_version, p_title, p_summary,
        'pending_review', p_markdown_relative_path, p_markdown_sha256,
        p_pdf_relative_path, p_pdf_sha256, p_manifest_relative_path,
        p_manifest_sha256, p_generator_name, p_generator_version,
        p_generator_metadata, p_generated_at, p_metadata, 1
    )
    ON CONFLICT (theme_id, version) DO NOTHING;

    IF NOT FOUND THEN
        RETURN false;
    END IF;

    INSERT INTO research.theme_research_report_review_event (
        event_id, report_version_id, from_status, to_status,
        actor_user_id, comment, request_id, idempotency_key
    ) VALUES (
        p_event_id, p_report_version_id, NULL, 'pending_review',
        'system', '', p_request_id, p_idempotency_key
    );
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION research.review_theme_research_report_version(
    p_action text,
    p_report_version_id text,
    p_expected_row_version bigint,
    p_actor_user_id text,
    p_comment text,
    p_request_id text,
    p_idempotency_key text,
    p_event_id text
) RETURNS TABLE (
    replayed boolean,
    event_to_status text,
    event_created_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    v_theme_id text;
    v_status text;
    v_row_version bigint;
    v_to_status text;
    v_previous record;
    v_archived record;
    v_archive_event_id text;
BEGIN
    IF p_action IS NULL OR p_action NOT IN ('publish', 'reject')
       OR p_expected_row_version IS NULL OR p_expected_row_version < 1
       OR p_report_version_id IS NULL OR p_report_version_id = ''
       OR p_report_version_id <> pg_catalog.btrim(p_report_version_id)
       OR pg_catalog.char_length(p_report_version_id) > 200
       OR p_actor_user_id IS NULL OR p_actor_user_id = ''
       OR p_actor_user_id <> pg_catalog.btrim(p_actor_user_id)
       OR pg_catalog.char_length(p_actor_user_id) > 200
       OR p_request_id IS NULL OR p_request_id = ''
       OR p_request_id <> pg_catalog.btrim(p_request_id)
       OR pg_catalog.char_length(p_request_id) > 200
       OR p_idempotency_key IS NULL OR p_idempotency_key = ''
       OR p_idempotency_key <> pg_catalog.btrim(p_idempotency_key)
       OR pg_catalog.char_length(p_idempotency_key) > 200
       OR p_event_id IS NULL OR p_event_id = ''
       OR p_comment IS NULL
       OR (p_action = 'publish' AND pg_catalog.char_length(p_comment) > 2000)
       OR (
           p_action = 'reject'
           AND (
               pg_catalog.btrim(p_comment) = ''
               OR p_comment <> pg_catalog.btrim(p_comment)
               OR pg_catalog.char_length(p_comment) > 4000
           )
       ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'THEME_REPORT_REVIEW_REQUEST_INVALID';
    END IF;
    v_to_status := CASE p_action WHEN 'publish' THEN 'published' ELSE 'rejected' END;

    SELECT report.theme_id
    INTO v_theme_id
    FROM research.theme_research_report_version AS report
    WHERE report.report_version_id = p_report_version_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'THEME_REPORT_NOT_FOUND';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'theme-research-report-review-lock' || E'\\x1f' || v_theme_id,
            0
        )
    );

    SELECT report.status, report.row_version
    INTO v_status, v_row_version
    FROM research.theme_research_report_version AS report
    WHERE report.report_version_id = p_report_version_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'THEME_REPORT_NOT_FOUND';
    END IF;

    SELECT event.report_version_id, event.to_status, event.created_at
    INTO v_previous
    FROM research.theme_research_report_review_event AS event
    WHERE event.actor_user_id = p_actor_user_id
      AND event.idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_previous.report_version_id <> p_report_version_id
           OR v_previous.to_status <> v_to_status THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'THEME_REPORT_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN QUERY SELECT true, v_previous.to_status, v_previous.created_at;
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM identity.user_account AS actor
        WHERE actor.user_id = p_actor_user_id
          AND actor.role = 'admin'
          AND actor.is_active
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'THEME_REPORT_ACTOR_NOT_FOUND';
    END IF;
    IF v_status <> 'pending_review' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'THEME_REPORT_STATE_CONFLICT';
    END IF;
    IF v_row_version <> p_expected_row_version THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'THEME_REPORT_VERSION_CONFLICT';
    END IF;

    IF p_action = 'publish' THEN
        FOR v_archived IN
            UPDATE research.theme_research_report_version AS report
            SET status = 'archived', row_version = report.row_version + 1,
                updated_at = pg_catalog.now()
            WHERE report.theme_id = v_theme_id
              AND report.status = 'published'
              AND report.report_version_id <> p_report_version_id
            RETURNING report.report_version_id
        LOOP
            v_archive_event_id := pg_catalog.encode(
                pg_catalog.sha256(
                    pg_catalog.convert_to('theme-research-report-review-event', 'UTF8') ||
                    pg_catalog.decode('00', 'hex') ||
                    pg_catalog.convert_to('archive', 'UTF8') ||
                    pg_catalog.decode('00', 'hex') ||
                    pg_catalog.convert_to(p_actor_user_id, 'UTF8') ||
                    pg_catalog.decode('00', 'hex') ||
                    pg_catalog.convert_to(
                        p_idempotency_key || ':archive:' || v_archived.report_version_id,
                        'UTF8'
                    )
                ),
                'hex'
            );
            INSERT INTO research.theme_research_report_review_event (
                event_id, report_version_id, from_status, to_status,
                actor_user_id, comment, request_id, idempotency_key
            ) VALUES (
                v_archive_event_id, v_archived.report_version_id,
                'published', 'archived', p_actor_user_id,
                'superseded by ' || p_report_version_id, p_request_id, ''
            );
        END LOOP;

        UPDATE research.theme_research_report_version AS report
        SET status = 'published', published_at = pg_catalog.now(),
            published_by_user_id = p_actor_user_id,
            row_version = report.row_version + 1,
            updated_at = pg_catalog.now()
        WHERE report.report_version_id = p_report_version_id;
    ELSE
        UPDATE research.theme_research_report_version AS report
        SET status = 'rejected', rejected_at = pg_catalog.now(),
            rejected_by_user_id = p_actor_user_id,
            rejection_reason = p_comment,
            row_version = report.row_version + 1,
            updated_at = pg_catalog.now()
        WHERE report.report_version_id = p_report_version_id;
    END IF;

    INSERT INTO research.theme_research_report_review_event (
        event_id, report_version_id, from_status, to_status,
        actor_user_id, comment, request_id, idempotency_key
    ) VALUES (
        p_event_id, p_report_version_id, 'pending_review', v_to_status,
        p_actor_user_id, p_comment, p_request_id, p_idempotency_key
    );
    RETURN QUERY SELECT false, v_to_status, pg_catalog.now();
END;
$$;

REVOKE ALL ON TABLE research.theme_research_report_version FROM PUBLIC;
REVOKE ALL ON TABLE research.theme_research_report_review_event FROM PUBLIC;
REVOKE ALL ON FUNCTION research.register_theme_research_report_pending(
    text, text, text, text, text, text, text, text, text, text,
    text, text, text, jsonb, timestamptz, jsonb, text, text, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION research.review_theme_research_report_version(
    text, text, bigint, text, text, text, text, text
) FROM PUBLIC;

DO $$
DECLARE
    relation_name text;
    column_name text;
    grantee_name text;
    routine_identity text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'theme_research_owner') THEN
        EXECUTE 'GRANT USAGE, CREATE ON SCHEMA research TO theme_research_owner';
        EXECUTE 'GRANT USAGE ON SCHEMA identity TO theme_research_owner';
        EXECUTE 'GRANT SELECT (user_id, role, is_active) ON identity.user_account TO theme_research_owner';
        EXECUTE 'ALTER TABLE research.theme_research_report_version OWNER TO theme_research_owner';
        EXECUTE 'ALTER TABLE research.theme_research_report_review_event OWNER TO theme_research_owner';
        EXECUTE 'ALTER FUNCTION research.register_theme_research_report_pending(text, text, text, text, text, text, text, text, text, text, text, text, text, jsonb, timestamptz, jsonb, text, text, text) OWNER TO theme_research_owner';
        EXECUTE 'ALTER FUNCTION research.review_theme_research_report_version(text, text, bigint, text, text, text, text, text) OWNER TO theme_research_owner';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'theme_research_runtime') THEN
        EXECUTE 'REVOKE ALL ON TABLE research.theme_research_report_version FROM theme_research_runtime';
        EXECUTE 'REVOKE ALL ON TABLE research.theme_research_report_review_event FROM theme_research_runtime';
        EXECUTE 'GRANT USAGE ON SCHEMA research TO theme_research_runtime';
        EXECUTE 'GRANT SELECT ON research.theme_research_report_version TO theme_research_runtime';
        EXECUTE 'GRANT SELECT ON research.theme_research_report_review_event TO theme_research_runtime';
        EXECUTE 'REVOKE ALL ON FUNCTION research.register_theme_research_report_pending(text, text, text, text, text, text, text, text, text, text, text, text, text, jsonb, timestamptz, jsonb, text, text, text) FROM theme_research_runtime';
        EXECUTE 'REVOKE ALL ON FUNCTION research.review_theme_research_report_version(text, text, bigint, text, text, text, text, text) FROM theme_research_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION research.register_theme_research_report_pending(text, text, text, text, text, text, text, text, text, text, text, text, text, jsonb, timestamptz, jsonb, text, text, text) TO theme_research_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION research.review_theme_research_report_version(text, text, bigint, text, text, text, text, text) TO theme_research_runtime';
    END IF;

    FOR routine_identity, grantee_name IN
        SELECT DISTINCT routine.oid::regprocedure::text, role.rolname
        FROM pg_proc routine
        JOIN pg_namespace namespace ON namespace.oid = routine.pronamespace
        CROSS JOIN LATERAL aclexplode(
            COALESCE(routine.proacl, acldefault('f', routine.proowner))
        ) privilege
        JOIN pg_roles role ON role.oid = privilege.grantee
        WHERE namespace.nspname = 'research'
          AND routine.proname IN (
              'register_theme_research_report_pending',
              'review_theme_research_report_version'
          )
          AND privilege.grantee <> routine.proowner
          AND role.rolname <> 'theme_research_runtime'
    LOOP
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON FUNCTION %s FROM %I',
            routine_identity,
            grantee_name
        );
    END LOOP;

    FOR relation_name IN
        SELECT unnest(ARRAY[
            'theme_research_report_version',
            'theme_research_report_review_event'
        ])
    LOOP
        FOR grantee_name IN
            SELECT DISTINCT role.rolname
            FROM pg_class relation
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            CROSS JOIN LATERAL aclexplode(
                COALESCE(relation.relacl, acldefault('r', relation.relowner))
            ) privilege
            JOIN pg_roles role ON role.oid = privilege.grantee
            WHERE namespace.nspname = 'research'
              AND relation.relname = relation_name
              AND role.rolname NOT IN (
                  pg_get_userbyid(relation.relowner),
                  'theme_research_runtime'
              )
        LOOP
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE research.%I FROM %I',
                relation_name,
                grantee_name
            );
        END LOOP;

        FOR column_name, grantee_name IN
            SELECT DISTINCT attribute.attname, role.rolname
            FROM pg_class relation
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            JOIN pg_attribute attribute ON attribute.attrelid = relation.oid
            CROSS JOIN LATERAL aclexplode(attribute.attacl) privilege
            JOIN pg_roles role ON role.oid = privilege.grantee
            WHERE namespace.nspname = 'research'
              AND relation.relname = relation_name
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
              AND role.rolname NOT IN (
                  pg_get_userbyid(relation.relowner),
                  'theme_research_runtime'
              )
        LOOP
            EXECUTE format(
                'REVOKE ALL PRIVILEGES (%I) ON TABLE research.%I FROM %I',
                column_name,
                relation_name,
                grantee_name
            );
        END LOOP;
    END LOOP;
END;
$$;
"""

THEME_RESEARCH_REPORT_MIGRATION_LOCK_SQL = (
    "SELECT pg_advisory_xact_lock(7171271448728574940)"
)

_EXPECTED_COLUMNS = {
    "theme_research_report_version": {
        "report_version_id": ("text", True, ""),
        "theme_id": ("text", True, ""),
        "version": ("text", True, ""),
        "title": ("text", True, ""),
        "summary": ("text", True, ""),
        "status": ("text", True, "'pending_review'::text"),
        "markdown_relative_path": ("text", True, ""),
        "markdown_sha256": ("text", True, ""),
        "pdf_relative_path": ("text", False, ""),
        "pdf_sha256": ("text", False, ""),
        "manifest_relative_path": ("text", True, ""),
        "manifest_sha256": ("text", True, ""),
        "generator_name": ("text", True, "''::text"),
        "generator_version": ("text", True, "''::text"),
        "generator_metadata": ("jsonb", True, "'{}'::jsonb"),
        "generated_at": ("timestamp with time zone", True, "now()"),
        "indexed_at": ("timestamp with time zone", True, "now()"),
        "published_at": ("timestamp with time zone", False, ""),
        "published_by_user_id": ("text", False, ""),
        "rejected_at": ("timestamp with time zone", False, ""),
        "rejected_by_user_id": ("text", False, ""),
        "rejection_reason": ("text", True, "''::text"),
        "row_version": ("bigint", True, "1"),
        "metadata": ("jsonb", True, "'{}'::jsonb"),
        "created_at": ("timestamp with time zone", True, "now()"),
        "updated_at": ("timestamp with time zone", True, "now()"),
    },
    "theme_research_report_review_event": {
        "event_id": ("text", True, ""),
        "report_version_id": ("text", True, ""),
        "from_status": ("text", False, ""),
        "to_status": ("text", True, ""),
        "actor_user_id": ("text", True, ""),
        "comment": ("text", True, "''::text"),
        "request_id": ("text", True, "''::text"),
        "idempotency_key": ("text", True, "''::text"),
        "created_at": ("timestamp with time zone", True, "now()"),
    },
}

_EXPECTED_CONSTRAINT_DEFINITIONS = {
    "ck_theme_research_report_pdf_pair": (
        "CHECK (pdf_relative_path IS NULL AND pdf_sha256 IS NULL OR "
        "pdf_relative_path IS NOT NULL AND pdf_sha256 IS NOT NULL)"
    ),
    "ck_theme_research_report_review_from_status": (
        "CHECK (from_status IS NULL OR (from_status = ANY "
        "(ARRAY['pending_review'::text, 'published'::text, "
        "'rejected'::text, 'archived'::text])))"
    ),
    "ck_theme_research_report_review_to_status": (
        "CHECK (to_status = ANY (ARRAY['pending_review'::text, "
        "'published'::text, 'rejected'::text, 'archived'::text]))"
    ),
    "ck_theme_research_report_row_version": "CHECK (row_version >= 1)",
    "ck_theme_research_report_version_status": (
        "CHECK (status = ANY (ARRAY['pending_review'::text, 'published'::text, "
        "'rejected'::text, 'archived'::text]))"
    ),
    "fk_theme_research_report_review_event_version": (
        "FOREIGN KEY (report_version_id) REFERENCES "
        "research.theme_research_report_version(report_version_id)"
    ),
    "fk_theme_research_report_version_published_by": (
        "FOREIGN KEY (published_by_user_id) REFERENCES identity.user_account(user_id)"
    ),
    "fk_theme_research_report_version_rejected_by": (
        "FOREIGN KEY (rejected_by_user_id) REFERENCES identity.user_account(user_id)"
    ),
    "fk_theme_research_report_version_theme": (
        "FOREIGN KEY (theme_id) REFERENCES research.theme_research_theme(theme_id)"
    ),
    "pk_theme_research_report_review_event": "PRIMARY KEY (event_id)",
    "pk_theme_research_report_version": "PRIMARY KEY (report_version_id)",
    "uq_theme_research_report_theme_version": "UNIQUE (theme_id, version)",
}

_V2_ACTOR_FK_NAME = "fk_theme_research_report_review_event_actor"
_V2_ACTOR_FK_DEFINITION = (
    "FOREIGN KEY (actor_user_id) REFERENCES identity.user_account(user_id)"
)

_EXPECTED_INDEX_DEFINITIONS = {
    "idx_theme_research_report_review_version_created": (
        "CREATE INDEX idx_theme_research_report_review_version_created ON "
        "research.theme_research_report_review_event USING btree "
        "(report_version_id, created_at DESC)"
    ),
    "idx_theme_research_report_status_generated": (
        "CREATE INDEX idx_theme_research_report_status_generated ON "
        "research.theme_research_report_version USING btree "
        "(status, generated_at DESC)"
    ),
    "uq_theme_research_report_one_published": (
        "CREATE UNIQUE INDEX uq_theme_research_report_one_published ON "
        "research.theme_research_report_version USING btree (theme_id) "
        "WHERE (status = 'published'::text)"
    ),
    "uq_theme_research_report_review_actor_idempotency": (
        "CREATE UNIQUE INDEX uq_theme_research_report_review_actor_idempotency ON "
        "research.theme_research_report_review_event USING btree "
        "(actor_user_id, idempotency_key) WHERE (idempotency_key <> ''::text)"
    ),
}

_ALLOWED_RUNTIME_UPDATE_COLUMNS: set[str] = set()
_EXPECTED_SECURITY_DEFINER_FUNCTIONS = {
    "register_theme_research_report_pending",
    "review_theme_research_report_version",
}


class ThemeResearchReportSchemaDriftError(RuntimeError):
    pass


def _row_value(row, key: str, index: int = 0):
    if hasattr(row, "get"):
        return row.get(key)
    return row[index]


def _normalized_sql(value: object) -> str:
    return " ".join(str(value).lower().split())


def inspect_theme_research_report_schema(cur) -> dict[str, object]:
    missing: list[str] = []
    table_names = tuple(_EXPECTED_COLUMNS)
    cur.execute(
        """
        SELECT c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'research'
          AND c.relkind IN ('r', 'p')
          AND c.relname = ANY(%s)
        """,
        (list(table_names),),
    )
    existing_tables = {
        str(_row_value(row, "table_name")) for row in cur.fetchall()
    }
    if not existing_tables:
        return {"status": "missing", "missing": []}
    for table_name in table_names:
        if table_name not in existing_tables:
            missing.append(f"table:{table_name}")

    cur.execute(
        """
        SELECT
            c.relname AS table_name,
            a.attname AS column_name,
            format_type(a.atttypid, a.atttypmod) AS data_type,
            a.attnotnull AS not_null,
            COALESCE(pg_get_expr(d.adbin, d.adrelid), '') AS default_value
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
        WHERE n.nspname = 'research'
          AND c.relname = ANY(%s)
          AND a.attnum > 0
          AND NOT a.attisdropped
        """,
        (list(table_names),),
    )
    actual_columns = {
        (
            str(_row_value(row, "table_name", 0)),
            str(_row_value(row, "column_name", 1)),
        ): (
            str(_row_value(row, "data_type", 2)),
            bool(_row_value(row, "not_null", 3)),
            _normalized_sql(_row_value(row, "default_value", 4)),
        )
        for row in cur.fetchall()
    }
    for table_name, columns in _EXPECTED_COLUMNS.items():
        for column_name, expected in columns.items():
            actual = actual_columns.get((table_name, column_name))
            if actual is None:
                missing.append(f"column:{table_name}.{column_name}")
            elif actual != expected:
                missing.append(f"column_definition:{table_name}.{column_name}")
        actual_names = {
            column_name
            for actual_table, column_name in actual_columns
            if actual_table == table_name
        }
        for column_name in sorted(actual_names - set(columns)):
            missing.append(f"column_extra:{table_name}.{column_name}")

    cur.execute(
        """
        SELECT con.conname, pg_get_constraintdef(con.oid, true) AS definition
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'research'
          AND c.relname = ANY(%s)
        """,
        (list(table_names),),
    )
    constraints = {
        str(_row_value(row, "conname", 0)): _normalized_sql(
            _row_value(row, "definition", 1)
        )
        for row in cur.fetchall()
    }
    for name, expected_definition in _EXPECTED_CONSTRAINT_DEFINITIONS.items():
        definition = constraints.get(name, "")
        if definition != _normalized_sql(expected_definition):
            missing.append(f"constraint:{name}")
    for name in sorted(set(constraints) - set(_EXPECTED_CONSTRAINT_DEFINITIONS)):
        if (
            name == _V2_ACTOR_FK_NAME
            and constraints[name] == _normalized_sql(_V2_ACTOR_FK_DEFINITION)
        ):
            missing.append("migration:v2_actor_fk")
        else:
            missing.append(f"constraint_extra:{name}")

    cur.execute(
        """
        SELECT
            index_relation.relname AS indexname,
            pg_get_indexdef(index_relation.oid) AS indexdef,
            index.indisunique AS is_unique,
            index.indisexclusion AS is_exclusion,
            constraint_record.oid IS NOT NULL AS is_constraint_backed,
            index.indexprs IS NOT NULL AS has_expressions,
            index.indpred IS NOT NULL AS has_predicate
        FROM pg_index index
        JOIN pg_class index_relation ON index_relation.oid = index.indexrelid
        JOIN pg_class table_relation ON table_relation.oid = index.indrelid
        JOIN pg_namespace namespace ON namespace.oid = table_relation.relnamespace
        LEFT JOIN pg_constraint constraint_record
            ON constraint_record.conindid = index.indexrelid
        WHERE namespace.nspname = 'research'
          AND table_relation.relname = ANY(%s)
        """,
        (list(table_names),),
    )
    index_rows = cur.fetchall()
    indexes = {
        str(_row_value(row, "indexname", 0)): _normalized_sql(
            _row_value(row, "indexdef", 1)
        )
        for row in index_rows
    }
    for name, expected_definition in _EXPECTED_INDEX_DEFINITIONS.items():
        definition = indexes.get(name, "")
        if definition != _normalized_sql(expected_definition):
            missing.append(f"index:{name}")
    for row in index_rows:
        name = str(_row_value(row, "indexname", 0))
        if name in _EXPECTED_INDEX_DEFINITIONS:
            continue
        if bool(_row_value(row, "is_constraint_backed", 4)):
            continue
        if (
            bool(_row_value(row, "is_unique", 2))
            or bool(_row_value(row, "is_exclusion", 3))
            or bool(_row_value(row, "has_expressions", 5))
            or bool(_row_value(row, "has_predicate", 6))
        ):
            missing.append(f"index_extra:{name}")

    cur.execute(
        """
        SELECT trigger.tgname
        FROM pg_trigger trigger
        JOIN pg_class relation ON relation.oid = trigger.tgrelid
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'research'
          AND relation.relname = ANY(%s)
          AND NOT trigger.tgisinternal
        """,
        (list(table_names),),
    )
    for row in cur.fetchall():
        missing.append(f"trigger:{_row_value(row, 'tgname')}")

    cur.execute(
        """
        SELECT
            relation.relname AS table_name,
            relation.relrowsecurity AS rls_enabled,
            relation.relforcerowsecurity AS rls_forced,
            policy.polname AS policy_name
        FROM pg_class relation
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        LEFT JOIN pg_policy policy ON policy.polrelid = relation.oid
        WHERE namespace.nspname = 'research'
          AND relation.relname = ANY(%s)
        """,
        (list(table_names),),
    )
    for row in cur.fetchall():
        table_name = str(_row_value(row, "table_name", 0))
        if bool(_row_value(row, "rls_enabled", 1)) or bool(
            _row_value(row, "rls_forced", 2)
        ):
            missing.append(f"rls:{table_name}")
        policy_name = _row_value(row, "policy_name", 3)
        if policy_name:
            missing.append(f"policy:{table_name}.{policy_name}")

    cur.execute(
        """
        SELECT rolname FROM pg_roles
        WHERE rolname IN ('theme_research_owner', 'theme_research_runtime')
        """
    )
    roles = {str(_row_value(row, "rolname")) for row in cur.fetchall()}
    for role_name in ("theme_research_owner", "theme_research_runtime"):
        if role_name not in roles:
            missing.append(f"role:{role_name}")
    if {"theme_research_owner", "theme_research_runtime"}.issubset(roles):
        cur.execute(
            """
            SELECT
                routine.proname AS function_name,
                routine.prosecdef AS security_definer,
                pg_get_userbyid(routine.proowner) AS owner_name,
                routine.proconfig AS configuration
            FROM pg_proc routine
            JOIN pg_namespace namespace ON namespace.oid = routine.pronamespace
            WHERE namespace.nspname = 'research'
              AND routine.proname = ANY(%s)
            """,
            (list(_EXPECTED_SECURITY_DEFINER_FUNCTIONS),),
        )
        function_rows = {
            str(_row_value(row, "function_name", 0)): row
            for row in cur.fetchall()
        }
        for function_name in sorted(_EXPECTED_SECURITY_DEFINER_FUNCTIONS):
            row = function_rows.get(function_name)
            if row is None:
                missing.append(f"migration:v3_function:{function_name}")
                continue
            if not bool(_row_value(row, "security_definer", 1)):
                missing.append(f"function_security:{function_name}")
            if str(_row_value(row, "owner_name", 2)) != "theme_research_owner":
                missing.append(f"function_owner:{function_name}")
            configuration = _row_value(row, "configuration", 3)
            if list(configuration or []) != ["search_path=pg_catalog"]:
                missing.append(f"function_config:{function_name}")
        cur.execute(
            """
            SELECT
                routine.proname AS function_name,
                pg_get_userbyid(routine.proowner) AS owner_name,
                privilege.grantee,
                role.rolname AS grantee_name,
                privilege.privilege_type,
                privilege.is_grantable
            FROM pg_proc routine
            JOIN pg_namespace namespace ON namespace.oid = routine.pronamespace
            CROSS JOIN LATERAL aclexplode(
                COALESCE(routine.proacl, acldefault('f', routine.proowner))
            ) privilege
            LEFT JOIN pg_roles role ON role.oid = privilege.grantee
            WHERE namespace.nspname = 'research'
              AND routine.proname = ANY(%s)
            """,
            (list(_EXPECTED_SECURITY_DEFINER_FUNCTIONS),),
        )
        runtime_execute: set[str] = set()
        for row in cur.fetchall():
            function_name = str(_row_value(row, "function_name", 0))
            owner_name = str(_row_value(row, "owner_name", 1))
            grantee_oid = int(_row_value(row, "grantee", 2))
            grantee_name = str(_row_value(row, "grantee_name", 3) or "PUBLIC")
            privilege_type = str(_row_value(row, "privilege_type", 4))
            is_grantable = bool(_row_value(row, "is_grantable", 5))
            if grantee_name == owner_name:
                continue
            if (
                grantee_name == "theme_research_runtime"
                and privilege_type == "EXECUTE"
            ):
                runtime_execute.add(function_name)
                if is_grantable:
                    missing.append(
                        f"function_grant_option:{function_name}.theme_research_runtime"
                    )
                continue
            if grantee_oid == 0:
                missing.append(f"public_privilege:function.{function_name}")
            else:
                missing.append(
                    f"function_acl:{function_name}.{grantee_name}.{privilege_type}"
                )
        for function_name in sorted(_EXPECTED_SECURITY_DEFINER_FUNCTIONS):
            if function_name not in runtime_execute:
                missing.append(f"function_privilege:{function_name}")
    cur.execute(
        """
        SELECT
            c.relname AS table_name,
            pg_get_userbyid(c.relowner) AS owner_name,
            NOT EXISTS (
                SELECT 1
                FROM aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner)))
                WHERE grantee = 0
            ) AS public_revoked
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'research'
          AND c.relname = ANY(%s)
        """,
        (list(table_names),),
    )
    for row in cur.fetchall():
        table_name = str(_row_value(row, "table_name", 0))
        owner_name = str(_row_value(row, "owner_name", 1))
        if not bool(_row_value(row, "public_revoked", 2)):
            missing.append(f"public_privilege:{table_name}")
        if "theme_research_owner" in roles and owner_name != "theme_research_owner":
            missing.append(f"owner:{table_name}")

    cur.execute(
        """
        SELECT
            relation.relname AS table_name,
            pg_get_userbyid(relation.relowner) AS owner_name,
            privilege.grantee,
            role.rolname AS grantee_name,
            privilege.privilege_type,
            privilege.is_grantable
        FROM pg_class relation
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        CROSS JOIN LATERAL aclexplode(
            COALESCE(relation.relacl, acldefault('r', relation.relowner))
        ) privilege
        LEFT JOIN pg_roles role ON role.oid = privilege.grantee
        WHERE namespace.nspname = 'research'
          AND relation.relname = ANY(%s)
        """,
        (list(table_names),),
    )
    for row in cur.fetchall():
        table_name = str(_row_value(row, "table_name", 0))
        owner_name = str(_row_value(row, "owner_name", 1))
        grantee_oid = int(_row_value(row, "grantee", 2))
        grantee_name = str(_row_value(row, "grantee_name", 3) or "PUBLIC")
        privilege_type = str(_row_value(row, "privilege_type", 4))
        is_grantable = bool(_row_value(row, "is_grantable", 5))
        if grantee_oid == 0:
            missing.append(f"public_privilege:{table_name}")
            continue
        if grantee_name == owner_name:
            continue
        if grantee_name == "theme_research_runtime":
            allowed = {
                "theme_research_report_version": {"SELECT"},
                "theme_research_report_review_event": {"SELECT"},
            }[table_name]
            if privilege_type in allowed and not is_grantable:
                continue
        missing.append(f"acl:{table_name}.{grantee_name}.{privilege_type}")

    cur.execute(
        """
        SELECT
            relation.relname AS table_name,
            attribute.attname AS column_name,
            pg_get_userbyid(relation.relowner) AS owner_name,
            privilege.grantee,
            role.rolname AS grantee_name,
            privilege.privilege_type,
            privilege.is_grantable
        FROM pg_class relation
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        JOIN pg_attribute attribute ON attribute.attrelid = relation.oid
        CROSS JOIN LATERAL aclexplode(attribute.attacl) privilege
        LEFT JOIN pg_roles role ON role.oid = privilege.grantee
        WHERE namespace.nspname = 'research'
          AND relation.relname = ANY(%s)
          AND attribute.attnum > 0
          AND NOT attribute.attisdropped
        """,
        (list(table_names),),
    )
    for row in cur.fetchall():
        table_name = str(_row_value(row, "table_name", 0))
        column_name = str(_row_value(row, "column_name", 1))
        owner_name = str(_row_value(row, "owner_name", 2))
        grantee_oid = int(_row_value(row, "grantee", 3))
        grantee_name = str(_row_value(row, "grantee_name", 4) or "PUBLIC")
        privilege_type = str(_row_value(row, "privilege_type", 5))
        is_grantable = bool(_row_value(row, "is_grantable", 6))
        if grantee_oid == 0:
            missing.append(f"public_privilege:{table_name}.{column_name}")
            continue
        if grantee_name == owner_name:
            continue
        if (
            grantee_name == "theme_research_runtime"
            and table_name == "theme_research_report_version"
            and column_name in _ALLOWED_RUNTIME_UPDATE_COLUMNS
            and privilege_type == "UPDATE"
            and not is_grantable
        ):
            continue
        missing.append(
            f"acl:{table_name}.{column_name}.{grantee_name}.{privilege_type}"
        )

    structural_drift = any(
        item.startswith(
            ("table:", "column:", "column_definition:", "constraint:", "index:")
        )
        for item in missing
    )
    if "theme_research_runtime" in roles and not structural_drift:
        expected_privileges = {
            "theme_research_report_version": (
                True,
                False,
                False,
                False,
                False,
                False,
                False,
            ),
            "theme_research_report_review_event": (
                True,
                False,
                False,
                False,
                False,
                False,
                False,
            ),
        }
        cur.execute(
            """
            SELECT
                c.relname AS table_name,
                has_table_privilege('theme_research_runtime', c.oid, 'SELECT') AS can_select,
                has_table_privilege('theme_research_runtime', c.oid, 'INSERT') AS can_insert,
                has_table_privilege('theme_research_runtime', c.oid, 'UPDATE') AS can_update,
                has_table_privilege('theme_research_runtime', c.oid, 'DELETE') AS can_delete,
                has_table_privilege('theme_research_runtime', c.oid, 'TRUNCATE') AS can_truncate,
                has_table_privilege('theme_research_runtime', c.oid, 'REFERENCES') AS can_reference,
                has_table_privilege('theme_research_runtime', c.oid, 'TRIGGER') AS can_trigger
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'research'
              AND c.relname = ANY(%s)
            """,
            (list(table_names),),
        )
        for row in cur.fetchall():
            table_name = str(_row_value(row, "table_name", 0))
            actual = tuple(
                bool(_row_value(row, key, index))
                for index, key in enumerate(
                    (
                        "can_select",
                        "can_insert",
                        "can_update",
                        "can_delete",
                        "can_truncate",
                        "can_reference",
                        "can_trigger",
                    ),
                    start=1,
                )
            )
            if actual != expected_privileges[table_name]:
                missing.append(f"privilege:{table_name}")

        cur.execute(
            """
            SELECT
                has_column_privilege(
                    'theme_research_runtime',
                    'research.theme_research_report_version',
                    column_name,
                    'UPDATE'
                ) AS can_update,
                column_name
            FROM unnest(%s::text[]) AS column_name
            """,
            (
                list(_EXPECTED_COLUMNS["theme_research_report_version"]),
            ),
        )
        for row in cur.fetchall():
            column_name = str(_row_value(row, "column_name", 1))
            can_update = bool(_row_value(row, "can_update", 0))
            if can_update != (column_name in _ALLOWED_RUNTIME_UPDATE_COLUMNS):
                missing.append(
                    f"column_privilege:theme_research_report_version.{column_name}"
                )

        cur.execute(
            """
            SELECT
                has_schema_privilege(
                    'theme_research_runtime', 'research', 'USAGE'
                ) AS can_use,
                has_schema_privilege(
                    'theme_research_runtime', 'research', 'CREATE'
                ) AS can_create
            """
        )
        schema_privileges = cur.fetchone()
        if not bool(_row_value(schema_privileges, "can_use", 0)):
            missing.append("privilege:research_schema_usage")
        if bool(_row_value(schema_privileges, "can_create", 1)):
            missing.append("privilege:research_schema_create")

    return {
        "status": "drifted" if missing else "current",
        "missing": sorted(set(missing)),
    }


def apply_theme_research_report_schema(
    service: str = SETTINGS.theme_research_migration_service,
) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(THEME_RESEARCH_REPORT_MIGRATION_LOCK_SQL)
            inspection = inspect_theme_research_report_schema(cur)
            repairable_prefixes = (
                "owner:",
                "privilege:",
                "public_privilege:",
                "column_privilege:",
                "acl:",
                "migration:v3_function:",
                "function_security:",
                "function_owner:",
                "function_config:",
                "function_privilege:",
                "function_acl:",
                "function_grant_option:",
            )
            repairable_items = {
                "migration:v2_actor_fk",
            }
            if inspection["status"] == "drifted" and any(
                not str(item).startswith(repairable_prefixes)
                and str(item) not in repairable_items
                for item in inspection["missing"]
            ):
                raise ThemeResearchReportSchemaDriftError(
                    "incompatible theme research report schema: "
                    + ", ".join(str(item) for item in inspection["missing"])
                )
            cur.execute(THEME_RESEARCH_REPORT_SCHEMA_SQL)
            post_inspection = inspect_theme_research_report_schema(cur)
            if post_inspection["status"] != "current":
                raise ThemeResearchReportSchemaDriftError(
                    "theme research report schema verification failed: "
                    + ", ".join(
                        str(item) for item in post_inspection["missing"]
                    )
                )


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-research-report-schema")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--service",
        default=SETTINGS.theme_research_migration_service,
    )
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("--apply is required")

    apply_theme_research_report_schema(service=args.service)
    print(
        json.dumps(
            {
                "status": "ok",
                "service": args.service,
                "schema_version": THEME_RESEARCH_REPORT_SCHEMA_VERSION,
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
