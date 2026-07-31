from __future__ import annotations

import argparse
import json

from stock_research.config import SETTINGS
from stock_research.db import connect


THEME_RESEARCH_REPORT_SCHEMA_VERSION = "1"

THEME_RESEARCH_REPORT_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.theme_research_report_version (
    report_version_id text PRIMARY KEY,
    theme_id text NOT NULL REFERENCES research.theme_research_theme(theme_id),
    version text NOT NULL,
    title text NOT NULL,
    summary text NOT NULL,
    status text NOT NULL DEFAULT 'pending_review' CHECK (
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
    published_by_user_id text REFERENCES identity.user_account(user_id),
    rejected_at timestamptz,
    rejected_by_user_id text REFERENCES identity.user_account(user_id),
    rejection_reason text NOT NULL DEFAULT '',
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (theme_id, version),
    CHECK (
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
    event_id text PRIMARY KEY,
    report_version_id text NOT NULL REFERENCES research.theme_research_report_version(report_version_id),
    from_status text CHECK (
        from_status IS NULL
        OR from_status IN ('pending_review', 'published', 'rejected', 'archived')
    ),
    to_status text NOT NULL CHECK (
        to_status IN ('pending_review', 'published', 'rejected', 'archived')
    ),
    actor_user_id text NOT NULL REFERENCES identity.user_account(user_id),
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
"""


def apply_theme_research_report_schema(
    service: str = SETTINGS.theme_research_migration_service,
) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(THEME_RESEARCH_REPORT_SCHEMA_SQL)


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
