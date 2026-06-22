from stock_research.dashboard import user_schema


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


def test_apply_user_platform_schema_creates_tables_and_indexes(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(user_schema, "connect", lambda service: _Context(conn))

    user_schema.apply_user_platform_schema()

    sql = conn.cursor_obj.calls[0][0]
    assert "CREATE SCHEMA IF NOT EXISTS identity" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.user_account" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.user_session" in sql
    assert "CREATE TABLE IF NOT EXISTS watchlist.user_watchlist_item" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_user_watchlist_item" in sql
    assert "CREATE TABLE IF NOT EXISTS journal.user_review_session" in sql
    assert "CREATE TABLE IF NOT EXISTS journal.user_review_item" in sql
    assert "CREATE TABLE IF NOT EXISTS audit.audit_log" in sql
