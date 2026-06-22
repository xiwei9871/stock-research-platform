from stock_research.config import SETTINGS
from stock_research.db import connect


CREATE_USER_PLATFORM_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS journal;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS identity.user_account (
    id bigserial PRIMARY KEY,
    username text NOT NULL UNIQUE,
    email text UNIQUE,
    password_hash text NOT NULL,
    display_name text NOT NULL,
    role text NOT NULL CHECK (role IN ('admin', 'user')),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz,
    password_updated_at timestamptz,
    disabled_at timestamptz
);

CREATE TABLE IF NOT EXISTS identity.user_session (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES identity.user_account(id),
    session_token_hash text NOT NULL UNIQUE,
    csrf_token_hash text NOT NULL,
    ip_address text,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);

CREATE TABLE IF NOT EXISTS watchlist.user_watchlist_item (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES identity.user_account(id),
    asset_id text NOT NULL,
    trade_date_added date NOT NULL,
    source text NOT NULL,
    notes text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_user_watchlist_item
    ON watchlist.user_watchlist_item (user_id, asset_id)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS journal.user_review_session (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES identity.user_account(id),
    trade_date date NOT NULL,
    title text NOT NULL,
    summary text NOT NULL DEFAULT '',
    market_view text NOT NULL DEFAULT '',
    position_view text NOT NULL DEFAULT '',
    next_action text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS journal.user_review_item (
    id bigserial PRIMARY KEY,
    session_id bigint NOT NULL REFERENCES journal.user_review_session(id),
    user_id bigint NOT NULL REFERENCES identity.user_account(id),
    asset_id text NOT NULL,
    decision text NOT NULL,
    conviction text NOT NULL,
    tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes text NOT NULL DEFAULT '',
    follow_up_required boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS audit.audit_log (
    id bigserial PRIMARY KEY,
    actor_user_id bigint REFERENCES identity.user_account(id),
    action text NOT NULL,
    target_type text NOT NULL,
    target_id text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip_address text,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


def apply_user_platform_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_USER_PLATFORM_SCHEMA_SQL)
