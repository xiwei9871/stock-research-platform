from stock_research import strategy_daily_eod_store


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


def test_build_status_payload_returns_expected_fields():
    payload = strategy_daily_eod_store.build_status_payload(
        trade_date="2026-06-24",
        status="running",
        dependency_check_status="success",
        lhb_shortline_status="running",
        mid_trend_status="skipped",
        tech_bottleneck_status="failed",
        review_rows="12",
        output_dir="/tmp/eod",
        summary_path="/tmp/eod/summary.md",
        error_summary="mid trend source timeout",
    )

    assert payload == {
        "trade_date": "2026-06-24",
        "status": "running",
        "dependency_check_status": "success",
        "lhb_shortline_status": "running",
        "mid_trend_status": "skipped",
        "tech_bottleneck_status": "failed",
        "review_rows": 12,
        "output_dir": "/tmp/eod",
        "summary_path": "/tmp/eod/summary.md",
        "error_summary": "mid trend source timeout",
    }


def test_strategy_daily_eod_status_schema_contains_expected_columns(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(strategy_daily_eod_store, "connect", lambda service: _Context(conn))

    strategy_daily_eod_store.apply_strategy_daily_eod_status_schema()

    sql = conn.cursor_obj.calls[0][0].lower()
    assert "create table if not exists ops.strategy_daily_eod_status" in sql
    assert "lhb_shortline_status text not null" in sql
    assert "mid_trend_status text not null" in sql
    assert "tech_bottleneck_status text not null" in sql
