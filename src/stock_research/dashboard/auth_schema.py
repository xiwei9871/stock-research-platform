from stock_research.config import SETTINGS
from stock_research.db import connect


DASHBOARD_AUTH_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS identity;

CREATE TABLE IF NOT EXISTS identity.user_account (
    user_id text PRIMARY KEY,
    username text NOT NULL,
    display_name text NOT NULL DEFAULT '',
    role text NOT NULL CHECK (role IN ('admin', 'user')),
    password_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz,
    password_updated_at timestamptz NOT NULL DEFAULT now(),
    disabled_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_user_account_username
    ON identity.user_account (lower(username));

CREATE TABLE IF NOT EXISTS identity.user_session (
    session_id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES identity.user_account(user_id),
    session_token_hash text NOT NULL,
    csrf_token_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    user_agent text NOT NULL DEFAULT '',
    ip_address text NOT NULL DEFAULT '',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_identity_user_session_user_id
    ON identity.user_session (user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_user_session_token_hash
    ON identity.user_session (session_token_hash);

CREATE TABLE IF NOT EXISTS identity.auth_audit_log (
    audit_id text PRIMARY KEY,
    action text NOT NULL,
    actor_user_id text NOT NULL DEFAULT '',
    target_user_id text NOT NULL DEFAULT '',
    username text NOT NULL DEFAULT '',
    ip_address text NOT NULL DEFAULT '',
    user_agent text NOT NULL DEFAULT '',
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
"""


def apply_dashboard_auth_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(DASHBOARD_AUTH_SCHEMA_SQL)
