from stock_research.config import Settings
from stock_research.dashboard import auth_schema


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_apply_dashboard_auth_schema_creates_identity_tables(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(auth_schema, "connect", lambda service: _Context(conn))

    auth_schema.apply_dashboard_auth_schema()

    sql = conn.cursor_obj.calls[0][0]
    assert "CREATE SCHEMA IF NOT EXISTS identity" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.user_account" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_user_account_username" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.user_session" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.auth_audit_log" in sql
    assert "role IN ('admin', 'user')" in sql


def test_dashboard_auth_settings_defaults_are_local_dev_safe(monkeypatch):
    monkeypatch.delenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", raising=False)
    settings = Settings()

    assert settings.dashboard_auth_required is False
    assert settings.dashboard_session_cookie == "stock_research_session"
    assert settings.dashboard_csrf_cookie == "stock_research_csrf"
    assert settings.dashboard_session_ttl_seconds == 60 * 60 * 12
