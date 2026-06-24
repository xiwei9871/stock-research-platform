from stock_research import strategy_daily_eod_store


def test_build_status_payload_returns_expected_fields():
    payload = strategy_daily_eod_store.build_status_payload(
        trade_date="2026-06-24",
        status="running",
        dependency_check_status="success",
        lhb_shortline_status="running",
        mid_trend_status="skipped",
        tech_bottleneck_status="failed",
        review_rows=12,
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

    assert strategy_daily_eod_store.build_status_payload.__annotations__["review_rows"] is int


def test_strategy_daily_eod_status_schema_contains_expected_columns():
    sql = strategy_daily_eod_store.STRATEGY_DAILY_EOD_STATUS_SQL.lower()

    assert "create table if not exists ops.strategy_daily_eod_status" in sql
    assert "trade_date date primary key" in sql
    assert "status text not null check (status in ('success', 'failed', 'running', 'skipped'))" in sql
    assert "dependency_check_status text not null check (dependency_check_status in ('success', 'failed', 'running', 'skipped'))" in sql
    assert "review_rows integer not null default 0" in sql
    assert "output_dir text" in sql
    assert "summary_path text" in sql
    assert "error_summary text" in sql
    assert "updated_at timestamptz not null default now()" in sql
    assert "lhb_shortline_status text not null" in sql
    assert "lhb_shortline_status in ('success', 'failed', 'running', 'skipped')" in sql
    assert "mid_trend_status text not null" in sql
    assert "mid_trend_status in ('success', 'failed', 'running', 'skipped')" in sql
    assert "tech_bottleneck_status text not null" in sql
    assert "tech_bottleneck_status in ('success', 'failed', 'running', 'skipped')" in sql


class _Connection:
    pass


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_apply_strategy_daily_eod_status_schema_executes_schema_sql(monkeypatch):
    conn = _Connection()
    calls: list[tuple[object, str]] = []

    monkeypatch.setattr(strategy_daily_eod_store, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(
        strategy_daily_eod_store,
        "execute",
        lambda passed_conn, sql: calls.append((passed_conn, sql)),
    )

    strategy_daily_eod_store.apply_strategy_daily_eod_status_schema()

    assert calls == [(conn, strategy_daily_eod_store.STRATEGY_DAILY_EOD_STATUS_SQL)]
