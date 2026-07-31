from __future__ import annotations

import argparse
import json

from stock_research.config import SETTINGS
from stock_research.db import connect


THEME_RESEARCH_REPORT_SCHEMA_VERSION = "2"

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
    actor_user_id text NOT NULL
        CONSTRAINT fk_theme_research_report_review_event_actor
        REFERENCES identity.user_account(user_id),
    comment text NOT NULL DEFAULT '',
    request_id text NOT NULL DEFAULT '',
    idempotency_key text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_theme_research_report_review_version_created
    ON research.theme_research_report_review_event (report_version_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_research_report_review_actor_idempotency
    ON research.theme_research_report_review_event (actor_user_id, idempotency_key)
    WHERE idempotency_key <> '';

REVOKE ALL ON TABLE research.theme_research_report_version FROM PUBLIC;
REVOKE ALL ON TABLE research.theme_research_report_review_event FROM PUBLIC;

DO $$
DECLARE
    relation_name text;
    column_name text;
    grantee_name text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'theme_research_owner') THEN
        EXECUTE 'ALTER TABLE research.theme_research_report_version OWNER TO theme_research_owner';
        EXECUTE 'ALTER TABLE research.theme_research_report_review_event OWNER TO theme_research_owner';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'theme_research_runtime') THEN
        EXECUTE 'REVOKE ALL ON TABLE research.theme_research_report_version FROM theme_research_runtime';
        EXECUTE 'REVOKE ALL ON TABLE research.theme_research_report_review_event FROM theme_research_runtime';
        EXECUTE 'GRANT USAGE ON SCHEMA research TO theme_research_runtime';
        EXECUTE 'GRANT SELECT, INSERT ON research.theme_research_report_version TO theme_research_runtime';
        EXECUTE 'GRANT UPDATE (
            status,
            published_at,
            published_by_user_id,
            rejected_at,
            rejected_by_user_id,
            rejection_reason,
            row_version,
            updated_at
        ) ON research.theme_research_report_version TO theme_research_runtime';
        EXECUTE 'GRANT SELECT, INSERT ON research.theme_research_report_review_event TO theme_research_runtime';
    END IF;

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
    "fk_theme_research_report_review_event_actor": (
        "FOREIGN KEY (actor_user_id) REFERENCES identity.user_account(user_id)"
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

_ALLOWED_RUNTIME_UPDATE_COLUMNS = {
    "status",
    "published_at",
    "published_by_user_id",
    "rejected_at",
    "rejected_by_user_id",
    "rejection_reason",
    "row_version",
    "updated_at",
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
        missing.append(f"constraint_extra:{name}")

    cur.execute(
        """
        SELECT
            index_relation.relname AS indexname,
            pg_get_indexdef(index_relation.oid) AS indexdef,
            index.indisunique AS is_unique,
            index.indisexclusion AS is_exclusion,
            constraint_record.oid IS NOT NULL AS is_constraint_backed
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
        if bool(_row_value(row, "is_unique", 2)) or bool(
            _row_value(row, "is_exclusion", 3)
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
                "theme_research_report_version": {"SELECT", "INSERT"},
                "theme_research_report_review_event": {"SELECT", "INSERT"},
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
                True,
                False,
                False,
                False,
                False,
                False,
            ),
            "theme_research_report_review_event": (
                True,
                True,
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
            )
            if inspection["status"] == "drifted" and any(
                not str(item).startswith(repairable_prefixes)
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
