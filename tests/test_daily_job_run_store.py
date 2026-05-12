from stock_research import daily_job_run_store


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


def test_apply_daily_job_run_schema_creates_ops_table(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(daily_job_run_store, "connect", lambda service: _Context(conn))

    daily_job_run_store.apply_daily_job_run_schema()

    sql = conn.cursor_obj.calls[0][0]
    assert "CREATE SCHEMA IF NOT EXISTS ops" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.daily_job_run" in sql


def test_record_daily_job_run_upserts_step_status(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(daily_job_run_store, "connect", lambda service: _Context(conn))

    run_id = daily_job_run_store.record_daily_job_run(
        trade_date="2026-05-12",
        step="load_market_bars",
        status="failed",
        metadata={"rows": 0},
        error_message="source unavailable",
    )

    sql, params = conn.cursor_obj.calls[0]
    assert run_id.startswith("daily_job:2026-05-12:load_market_bars:")
    assert "INSERT INTO ops.daily_job_run" in sql
    assert params["trade_date"] == "2026-05-12"
    assert params["step"] == "load_market_bars"
    assert params["status"] == "failed"
    assert params["error_message"] == "source unavailable"
    assert '"rows": 0' in params["metadata"]
