from stock_research import report_run_store


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


def test_apply_report_run_schema_creates_report_table(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(report_run_store, "connect", lambda service: _Context(conn))

    report_run_store.apply_report_run_schema()

    sql = conn.cursor_obj.calls[0][0]
    assert "CREATE SCHEMA IF NOT EXISTS report" in sql
    assert "CREATE TABLE IF NOT EXISTS report.report_run" in sql


def test_record_report_run_upserts_report_paths(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(report_run_store, "connect", lambda service: _Context(conn))

    run_id = report_run_store.record_report_run(
        trade_date="2026-05-08",
        report_type="daily_research",
        report_paths={"bundle": {"markdown_path": "/tmp/bundle.md"}},
        status="completed",
        metadata={"score_version": "manual_v1"},
    )

    sql, params = conn.cursor_obj.calls[0]
    assert run_id.startswith("daily_research:2026-05-08:")
    assert "INSERT INTO report.report_run" in sql
    assert params["trade_date"] == "2026-05-08"
    assert params["report_type"] == "daily_research"
    assert params["status"] == "completed"
    assert '"bundle"' in params["report_paths"]
    assert '"score_version": "manual_v1"' in params["metadata"]
