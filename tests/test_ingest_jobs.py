from contextlib import contextmanager

from stock_research import ingest_jobs


class FakeConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []
        self.many = []
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def fake_fetch_all(conn, sql, params=None):
    conn.executed.append((sql, params))
    return conn.rows


def fake_execute(conn, sql, params=None):
    conn.executed.append((sql, params))


def fake_execute_many(conn, sql, rows):
    conn.many.append((sql, list(rows)))


def test_baostock_finance_job_id_is_deterministic():
    job_id = ingest_jobs.baostock_finance_job_id(1990, 4, 100, 50)

    assert job_id == "baostock-finance:1990Q4:offset100:limit50"


def test_build_baostock_finance_jobs_splits_year_quarter_offsets():
    jobs = ingest_jobs.build_baostock_finance_jobs(
        start_year=1990,
        end_year=1990,
        asset_count=120,
        batch_size=50,
    )

    assert len(jobs) == 12
    assert jobs[0]["job_id"] == "baostock-finance:1990Q1:offset0:limit50"
    assert jobs[1]["job_id"] == "baostock-finance:1990Q1:offset50:limit50"
    assert jobs[2]["job_id"] == "baostock-finance:1990Q1:offset100:limit50"
    assert jobs[-1]["quarter"] == 4
    assert jobs[-1]["offset_value"] == 100


def test_build_akshare_finance_statement_jobs_splits_asset_offsets():
    jobs = ingest_jobs.build_akshare_finance_statement_jobs(
        asset_count=3,
        batch_size=2,
    )

    assert len(jobs) == 2
    assert jobs[0]["job_id"] == "akshare-finance-statements:offset0:limit2"
    assert jobs[1]["job_id"] == "akshare-finance-statements:offset2:limit2"
    assert jobs[0]["dataset"] == "akshare-finance-statements"
    assert jobs[0]["source"] == "akshare_em"
    assert jobs[0]["params"] == {"offset": 0, "limit": 2}


def test_create_baostock_finance_jobs_upserts_jobs(monkeypatch):
    conn = FakeConnection(rows=[{"count": 120}])
    monkeypatch.setattr(ingest_jobs, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(ingest_jobs, "execute_many", fake_execute_many)

    created = ingest_jobs.create_baostock_finance_jobs(
        conn,
        start_year=1990,
        end_year=1990,
        batch_size=50,
    )

    assert created == 12
    sql, rows = conn.many[0]
    assert "INSERT INTO ingest.batch_job" in sql
    assert "ON CONFLICT (job_id) DO UPDATE" in sql
    assert rows[0][0] == "baostock-finance:1990Q1:offset0:limit50"


def test_create_akshare_finance_statement_jobs_upserts_jobs(monkeypatch):
    conn = FakeConnection(rows=[{"count": 3}])
    monkeypatch.setattr(ingest_jobs, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(ingest_jobs, "execute_many", fake_execute_many)

    created = ingest_jobs.create_akshare_finance_statement_jobs(conn, batch_size=2)

    assert created == 2
    sql, rows = conn.many[0]
    assert "INSERT INTO ingest.batch_job" in sql
    assert rows[0][0] == "akshare-finance-statements:offset0:limit2"
    assert rows[0][1] == "akshare-finance-statements"
    assert rows[0][2] == "akshare_em"


def test_fetch_runnable_jobs_selects_pending_and_failed(monkeypatch):
    conn = FakeConnection(rows=[{"job_id": "job-1"}])
    monkeypatch.setattr(ingest_jobs, "fetch_all", fake_fetch_all)

    rows = ingest_jobs.fetch_runnable_jobs(conn, "baostock-finance", limit_jobs=5)

    assert rows == [{"job_id": "job-1"}]
    sql, params = conn.executed[0]
    assert "status IN ('pending', 'failed')" in sql
    assert "ORDER BY year, quarter, offset_value" in sql
    assert params == ["baostock-finance", 5]


def test_claim_runnable_jobs_uses_skip_locked_and_marks_running(monkeypatch):
    conn = FakeConnection(rows=[{"job_id": "job-1"}])
    events = []
    monkeypatch.setattr(ingest_jobs, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        ingest_jobs,
        "_record_event",
        lambda conn, job_id, status, message=None: events.append((job_id, status, message)),
    )

    rows = ingest_jobs.claim_runnable_jobs(conn, "baostock-finance", limit_jobs=5)

    assert rows == [{"job_id": "job-1"}]
    sql, params = conn.executed[0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "UPDATE ingest.batch_job" in sql
    assert "status IN ('pending', 'failed')" in sql
    assert "status = 'running'" in sql
    assert "RETURNING job.*" in sql
    assert params == ["baostock-finance", 5]
    assert events == [("job-1", "running", None)]


def test_reset_stale_ingest_jobs_returns_reset_count(monkeypatch):
    conn = FakeConnection(rows=[{"job_id": "job-1"}, {"job_id": "job-2"}])
    monkeypatch.setattr(ingest_jobs, "fetch_all", fake_fetch_all)

    count = ingest_jobs.reset_stale_ingest_jobs(
        conn,
        dataset="baostock-finance",
        older_than_minutes=60,
    )

    assert count == 2
    sql, params = conn.executed[0]
    assert "UPDATE ingest.batch_job" in sql
    assert "status = 'running'" in sql
    assert "RETURNING job_id" in sql
    assert params == ["baostock-finance", 60]


def test_job_state_updates(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(ingest_jobs, "execute", fake_execute)

    ingest_jobs.mark_job_running(conn, "job-1")
    ingest_jobs.mark_job_success(conn, "job-1", rows_read=10, rows_written=20)
    ingest_jobs.mark_job_failed(conn, "job-1", "boom")

    statements = [sql for sql, _params in conn.executed]
    assert any("status = 'running'" in sql for sql in statements)
    assert any("status = 'success'" in sql for sql in statements)
    assert any("status = 'failed'" in sql for sql in statements)


def test_run_ingest_jobs_executes_limited_jobs(monkeypatch):
    conn = FakeConnection(
        rows=[
            {
                "job_id": "job-1",
                "year": 2025,
                "quarter": 4,
                "offset_value": 0,
                "limit_value": 50,
            }
        ]
    )
    calls = []
    claim_limits = []

    def fake_claim(conn, dataset, limit_jobs):
        claim_limits.append(limit_jobs)
        if not conn.rows:
            return []
        return [conn.rows.pop(0)]

    monkeypatch.setattr(ingest_jobs, "claim_runnable_jobs", fake_claim)
    monkeypatch.setattr(
        ingest_jobs,
        "sync_finance_for_period",
        lambda year, quarter, limit, offset: {
            "queried_assets": 50,
            "indicator_quarter": 50,
            "income_statement": 50,
            "share_capital_event": 50,
        },
    )
    monkeypatch.setattr(
        ingest_jobs,
        "mark_job_success",
        lambda conn, job_id, rows_read, rows_written: calls.append(
            ("success", job_id, rows_read, rows_written)
        ),
    )

    result = ingest_jobs.run_ingest_jobs(conn, "baostock-finance", limit_jobs=1)

    assert result == {"attempted": 1, "success": 1, "failed": 0, "rows_read": 50, "rows_written": 150}
    assert calls == [("success", "job-1", 50, 150)]
    assert claim_limits == [1]


def test_run_ingest_jobs_dispatches_akshare_finance_statements(monkeypatch):
    conn = FakeConnection(
        rows=[
            {
                "job_id": "akshare-finance-statements:offset0:limit2",
                "dataset": "akshare-finance-statements",
                "offset_value": 0,
                "limit_value": 2,
            }
        ]
    )
    calls = []
    sync_calls = []

    def fake_claim(conn, dataset, limit_jobs):
        if not conn.rows:
            return []
        return [conn.rows.pop(0)]

    monkeypatch.setattr(ingest_jobs, "claim_runnable_jobs", fake_claim)
    monkeypatch.setattr(
        ingest_jobs,
        "sync_finance_statements_for_assets",
        lambda limit, offset: sync_calls.append((limit, offset))
        or {"queried_assets": 2, "balance_sheet": 5, "cash_flow": 4, "raw_payload": 4},
    )
    monkeypatch.setattr(
        ingest_jobs,
        "mark_job_success",
        lambda conn, job_id, rows_read, rows_written: calls.append(
            ("success", job_id, rows_read, rows_written)
        ),
    )

    result = ingest_jobs.run_ingest_jobs(conn, "akshare-finance-statements", limit_jobs=1)

    assert result == {"attempted": 1, "success": 1, "failed": 0, "rows_read": 2, "rows_written": 9}
    assert sync_calls == [(2, 0)]
    assert calls == [("success", "akshare-finance-statements:offset0:limit2", 2, 9)]


def test_run_ingest_jobs_reports_progress(monkeypatch):
    conn = FakeConnection(
        rows=[
            {
                "job_id": "job-1",
                "year": 2025,
                "quarter": 4,
                "offset_value": 0,
                "limit_value": 50,
            }
        ]
    )
    progress_events = []
    claim_limits = []

    def fake_claim(conn, dataset, limit_jobs):
        claim_limits.append(limit_jobs)
        if not conn.rows:
            return []
        return [conn.rows.pop(0)]

    monkeypatch.setattr(ingest_jobs, "claim_runnable_jobs", fake_claim)
    monkeypatch.setattr(
        ingest_jobs,
        "sync_finance_for_period",
        lambda year, quarter, limit, offset: {
            "queried_assets": 50,
            "indicator_quarter": 0,
            "income_statement": 0,
            "share_capital_event": 0,
        },
    )
    monkeypatch.setattr(
        ingest_jobs,
        "mark_job_success",
        lambda conn, job_id, rows_read, rows_written: None,
    )

    ingest_jobs.run_ingest_jobs(
        conn,
        "baostock-finance",
        limit_jobs=1,
        progress=progress_events.append,
    )

    assert progress_events == [
        {
            "event": "start",
            "index": 1,
            "total": 1,
            "job_id": "job-1",
            "success": 0,
            "failed": 0,
        },
        {
            "event": "success",
            "index": 1,
            "total": 1,
            "job_id": "job-1",
            "success": 1,
            "failed": 0,
            "rows_read": 50,
            "rows_written": 0,
        },
    ]
    assert claim_limits == [1]


def test_run_ingest_jobs_commits_each_completed_job_before_interrupt(monkeypatch):
    conn = FakeConnection(
        rows=[
            {
                "job_id": "job-1",
                "year": 2025,
                "quarter": 4,
                "offset_value": 0,
                "limit_value": 50,
            },
            {
                "job_id": "job-2",
                "year": 2025,
                "quarter": 4,
                "offset_value": 50,
                "limit_value": 50,
            },
        ]
    )
    calls = []
    sync_calls = []
    claim_limits = []

    def fake_claim(conn, dataset, limit_jobs):
        claim_limits.append(limit_jobs)
        if not conn.rows:
            return []
        return [conn.rows.pop(0)]

    monkeypatch.setattr(ingest_jobs, "claim_runnable_jobs", fake_claim)
    monkeypatch.setattr(
        ingest_jobs,
        "mark_job_success",
        lambda conn, job_id, rows_read, rows_written: calls.append(("success", job_id, rows_read, rows_written)),
    )
    monkeypatch.setattr(
        ingest_jobs,
        "mark_job_failed",
        lambda conn, job_id, error_message: calls.append(("failed", job_id, error_message)),
    )

    def fake_sync(year, quarter, limit, offset):
        sync_calls.append(offset)
        if offset == 50:
            raise KeyboardInterrupt("interrupted")
        return {
            "queried_assets": 50,
            "indicator_quarter": 0,
            "income_statement": 0,
            "share_capital_event": 0,
        }

    monkeypatch.setattr(ingest_jobs, "sync_finance_for_period", fake_sync)

    try:
        ingest_jobs.run_ingest_jobs(conn, "baostock-finance", limit_jobs=2)
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("KeyboardInterrupt should be re-raised")

    assert sync_calls == [0, 50]
    assert calls == [
        ("success", "job-1", 50, 0),
        ("failed", "job-2", "interrupted"),
    ]
    assert claim_limits == [1, 1]
    assert conn.commits == 4


def test_format_ingest_loop_report_includes_round_and_status():
    message = ingest_jobs.format_ingest_loop_report(
        {
            "dataset": "baostock-finance",
            "round": 2,
            "attempted": 50,
            "success": 49,
            "failed": 1,
            "rows_read": 2500,
            "rows_written": 12,
            "status_counts": {"success": 169, "pending": 14807, "failed": 1, "skipped": 12},
            "recent_jobs": [
                {
                    "job_id": "baostock-finance:1990Q2:offset3200:limit50",
                    "status": "success",
                    "rows_read": 50,
                    "rows_written": 0,
                    "error_message": None,
                }
            ],
            "done": False,
        }
    )

    assert "A股财务数据补齐进度" in message
    assert "第 2 轮" in message
    assert "本轮尝试: 50" in message
    assert "本轮失败: 1" in message
    assert "pending: 14807" in message
    assert "skipped: 12" in message
    assert "offset3200" in message
    assert "结论: 本轮完成，但存在失败批次，可继续重试" in message


def test_run_ingest_loop_runs_until_no_pending_and_reports_each_round(monkeypatch):
    conn = FakeConnection()
    run_results = [
        {"attempted": 2, "success": 2, "failed": 0, "rows_read": 100, "rows_written": 0},
        {"attempted": 1, "success": 1, "failed": 0, "rows_read": 50, "rows_written": 3},
    ]
    status_results = [
        [{"dataset": "baostock-finance", "status": "pending", "count": 1}],
        [{"dataset": "baostock-finance", "status": "success", "count": 3}],
    ]
    recent_results = [
        [{"job_id": "job-2", "status": "success", "rows_read": 50, "rows_written": 0}],
        [{"job_id": "job-3", "status": "success", "rows_read": 50, "rows_written": 3}],
    ]
    reports = []
    sleep_calls = []
    monkeypatch.setattr(
        ingest_jobs,
        "run_ingest_jobs",
        lambda conn, dataset, limit_jobs, progress=None: run_results.pop(0),
    )
    monkeypatch.setattr(
        ingest_jobs,
        "ingest_status",
        lambda conn, dataset: status_results.pop(0),
    )
    monkeypatch.setattr(
        ingest_jobs,
        "recent_ingest_jobs",
        lambda conn, dataset, limit=12: recent_results.pop(0),
    )

    result = ingest_jobs.run_ingest_loop(
        conn,
        "baostock-finance",
        jobs_per_round=2,
        report=reports.append,
        sleep_seconds=5,
        sleep=sleep_calls.append,
    )

    assert result == {
        "rounds": 2,
        "attempted": 3,
        "success": 3,
        "failed": 0,
        "rows_read": 150,
        "rows_written": 3,
        "done": True,
    }
    assert len(reports) == 2
    assert reports[0]["round"] == 1
    assert reports[0]["done"] is False
    assert reports[1]["round"] == 2
    assert reports[1]["done"] is True
    assert sleep_calls == [5]


def test_parallel_run_ingest_loop_reads_status_with_fresh_connection(monkeypatch):
    loop_conn = FakeConnection()
    fresh_conn = FakeConnection()
    reports = []

    @contextmanager
    def fake_connect(service):
        assert service == "stock_research"
        yield fresh_conn

    def fake_ingest_status(conn, dataset):
        if conn is loop_conn:
            raise AssertionError("stale loop connection reused for status")
        assert conn is fresh_conn
        assert dataset == "baostock-finance"
        return [{"dataset": dataset, "status": "success", "count": 1}]

    def fake_recent_jobs(conn, dataset, limit=12):
        if conn is loop_conn:
            raise AssertionError("stale loop connection reused for recent jobs")
        assert conn is fresh_conn
        return [{"job_id": "job-1", "status": "success", "rows_read": 50, "rows_written": 150}]

    monkeypatch.setattr(
        ingest_jobs,
        "run_ingest_jobs_parallel_for_service",
        lambda dataset, limit_jobs, workers, service: {
            "attempted": 1,
            "success": 1,
            "failed": 0,
            "rows_read": 50,
            "rows_written": 150,
        },
    )
    monkeypatch.setattr(ingest_jobs, "connect", fake_connect)
    monkeypatch.setattr(ingest_jobs, "ingest_status", fake_ingest_status)
    monkeypatch.setattr(ingest_jobs, "recent_ingest_jobs", fake_recent_jobs)

    result = ingest_jobs.run_ingest_loop(
        loop_conn,
        "baostock-finance",
        jobs_per_round=1,
        report=reports.append,
        sleep_seconds=0,
        workers=2,
    )

    assert result["done"] is True
    assert reports[0]["status_counts"] == {"success": 1}
    assert reports[0]["recent_jobs"][0]["job_id"] == "job-1"


def test_run_ingest_jobs_parallel_splits_limit_and_aggregates_results(monkeypatch):
    calls = []

    class ImmediateExecutor:
        def __init__(self, **kwargs):
            calls.append(("executor", kwargs))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            from concurrent.futures import Future

            calls.append(("submit", args, kwargs))
            future = Future()
            future.set_result(fn(*args, **kwargs))
            return future

    worker_results = [
        {"attempted": 3, "success": 3, "failed": 0, "rows_read": 150, "rows_written": 450},
        {"attempted": 2, "success": 1, "failed": 1, "rows_read": 50, "rows_written": 150},
    ]
    monkeypatch.setattr(ingest_jobs, "ProcessPoolExecutor", ImmediateExecutor)
    monkeypatch.setattr(
        ingest_jobs,
        "_run_ingest_jobs_worker",
        lambda dataset, limit_jobs, service: {
            **worker_results.pop(0),
            "limit_jobs": limit_jobs,
        },
    )

    result = ingest_jobs.run_ingest_jobs_parallel_for_service(
        "baostock-finance",
        limit_jobs=5,
        workers=2,
    )

    assert result == {
        "attempted": 5,
        "success": 4,
        "failed": 1,
        "rows_read": 200,
        "rows_written": 600,
    }
    assert calls[0] == ("executor", {"max_workers": 2, "max_tasks_per_child": 1})
    assert [call[1][1] for call in calls[1:]] == [3, 2]
