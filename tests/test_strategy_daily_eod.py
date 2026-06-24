import json

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


def test_run_strategy_daily_eod_returns_failed_when_dependency_check_fails(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    apply_calls: list[str] = []
    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: apply_calls.append("called"),
    )

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {
            "status": "failed",
            "reason": "deps missing",
        },
    )

    assert apply_calls == ["called"]
    assert result["status"] == "failed"
    assert result["dependency_check"] == {"status": "failed", "reason": "deps missing"}
    assert result["strategy_status"] == {
        "lhb_shortline": {"status": "skipped", "reason": "dependency_check_failed"},
        "mid_trend": {"status": "skipped", "reason": "dependency_check_failed"},
        "tech_bottleneck": {"status": "skipped", "reason": "dependency_check_failed"},
    }


def test_run_strategy_daily_eod_returns_failed_when_one_strategy_runner_fails(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    apply_calls: list[str] = []
    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: apply_calls.append("called"),
    )

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {"status": "success"},
        lhb_shortline_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 2},
        mid_trend_runner=lambda *_args, **_kwargs: {"status": "failed", "reason": "runner boom"},
        tech_bottleneck_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 3},
    )

    assert apply_calls == ["called"]
    assert result["status"] == "failed"
    assert result["dependency_check"] == {"status": "success"}
    assert result["strategy_status"] == {
        "lhb_shortline": {"status": "success", "review_rows": 2},
        "mid_trend": {"status": "failed", "reason": "runner boom"},
        "tech_bottleneck": {"status": "success", "review_rows": 3},
    }


def test_run_strategy_daily_eod_uses_default_stub_runners_and_writes_summary_json(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: None,
    )

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {"status": "success"},
    )

    summary_path = tmp_path / "2026-06-24" / "strategy_eod_publish_summary.json"
    assert result["status"] == "failed"
    assert result["strategy_status"] == {
        "lhb_shortline": {"status": "failed", "reason": "lhb_shortline runner not configured"},
        "mid_trend": {"status": "failed", "reason": "mid_trend runner not configured"},
        "tech_bottleneck": {"status": "failed", "reason": "tech_bottleneck runner not configured"},
    }
    assert summary_path.exists()
    assert json.loads(summary_path.read_text(encoding="utf-8")) == result


def test_run_strategy_daily_eod_returns_structured_failure_when_dependency_checker_raises(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: None,
    )

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("deps boom")),
    )

    assert result["status"] == "failed"
    assert result["dependency_check"] == {
        "status": "failed",
        "reason": "dependency_checker_exception: deps boom",
    }
    assert result["strategy_status"] == {
        "lhb_shortline": {"status": "skipped", "reason": "dependency_check_failed"},
        "mid_trend": {"status": "skipped", "reason": "dependency_check_failed"},
        "tech_bottleneck": {"status": "skipped", "reason": "dependency_check_failed"},
    }


def test_run_strategy_daily_eod_returns_structured_failure_when_strategy_runner_raises(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: None,
    )

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {"status": "success"},
        lhb_shortline_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 1},
        mid_trend_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("runner boom")),
        tech_bottleneck_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 4},
    )

    assert result["status"] == "failed"
    assert result["strategy_status"] == {
        "lhb_shortline": {"status": "success", "review_rows": 1},
        "mid_trend": {"status": "failed", "reason": "strategy_runner_exception: runner boom"},
        "tech_bottleneck": {"status": "success", "review_rows": 4},
    }


def test_run_strategy_daily_eod_returns_structured_failure_when_summary_write_raises(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: None,
    )

    def fake_write_text(self, data, encoding):
        raise OSError("disk full")

    monkeypatch.setattr(strategy_daily_eod.Path, "write_text", fake_write_text)

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {"status": "success"},
        lhb_shortline_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 1},
        mid_trend_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 2},
        tech_bottleneck_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 3},
    )

    assert result["status"] == "failed"
    assert result["reason"] == "summary_write_exception: disk full"
    assert result["summary_path"] == str(tmp_path / "2026-06-24" / "strategy_eod_publish_summary.json")


def test_check_strategy_daily_eod_dependencies_fails_when_status_row_missing(monkeypatch):
    from stock_research import strategy_daily_eod

    conn = _Connection()
    monkeypatch.setattr(strategy_daily_eod, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(strategy_daily_eod, "fetch_all", lambda passed_conn, sql, params: [])

    result = strategy_daily_eod.check_strategy_daily_eod_dependencies("2026-06-24")

    assert result == {
        "status": "failed",
        "reason": "daily_pipeline_status missing",
    }


def test_check_strategy_daily_eod_dependencies_accepts_partial_success(monkeypatch):
    from stock_research import strategy_daily_eod

    conn = _Connection()
    monkeypatch.setattr(strategy_daily_eod, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(
        strategy_daily_eod,
        "fetch_all",
        lambda passed_conn, sql, params: [
            {
                "daily_status": "partial_success",
                "minute5_status": "success",
                "deps_status": "success",
            }
        ],
    )

    result = strategy_daily_eod.check_strategy_daily_eod_dependencies("2026-06-24")

    assert result == {
        "status": "success",
        "daily_status": "partial_success",
        "minute5_status": "success",
        "deps_status": "success",
    }
