import datetime as dt
import time
from contextlib import contextmanager

from stock_research import minute_backfill
from stock_research.minute_backfill import (
    BackfillJob,
    build_backfill_jobs,
    derive_qfq_minute_bars_from_raw_job,
    month_ranges,
    summarize_backfill_status,
    validate_minute_bar_rows,
)


class FakeConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []


def fake_fetch_all(conn, sql, params=None):
    conn.executed.append((sql, params))
    return conn.rows


def asset_rows():
    return [
        {"asset_id": "CN:SH:600000", "ts_code": "600000.SH", "baostock_code": "sh.600000"},
        {"asset_id": "CN:SZ:000001", "ts_code": "000001.SZ", "baostock_code": "sz.000001"},
    ]


@contextmanager
def fake_connect(service):
    yield FakeConnection()


def test_month_ranges_split_date_window_by_calendar_month():
    ranges = month_ranges(dt.date(2024, 1, 15), dt.date(2024, 3, 3))

    assert ranges == [
        (dt.date(2024, 1, 15), dt.date(2024, 1, 31)),
        (dt.date(2024, 2, 1), dt.date(2024, 2, 29)),
        (dt.date(2024, 3, 1), dt.date(2024, 3, 3)),
    ]


def test_build_backfill_jobs_generates_asset_month_adjustment_cross_product():
    jobs = build_backfill_jobs(
        asset_rows(),
        dt.date(2024, 1, 1),
        dt.date(2024, 2, 2),
        freq="5min",
        adjust_types=["raw", "qfq"],
        batch_by="month",
    )

    assert len(jobs) == 8
    assert jobs[0].asset_id == "CN:SH:600000"
    assert jobs[0].ts_code == "600000.SH"
    assert jobs[0].baostock_code == "sh.600000"
    assert jobs[0].start_date == dt.date(2024, 1, 1)
    assert jobs[0].end_date == dt.date(2024, 1, 31)
    assert {job.adjust_type for job in jobs} == {"raw", "qfq"}


def test_run_backfill_skips_success_jobs_and_executes_pending(monkeypatch):
    marked = []
    jobs = [
        {
            "job_id": "success",
            "baostock_code": "sh.600000",
            "start_date": dt.date(2024, 1, 1),
            "end_date": dt.date(2024, 1, 2),
            "freq": "5min",
            "adjust_type": "raw",
            "status": "success",
        },
        {
            "job_id": "pending",
            "baostock_code": "sz.000001",
            "start_date": dt.date(2024, 1, 1),
            "end_date": dt.date(2024, 1, 2),
            "freq": "5min",
            "adjust_type": "raw",
            "status": "pending",
        },
    ]

    monkeypatch.setattr(minute_backfill, "connect", fake_connect)
    monkeypatch.setattr(minute_backfill, "reset_stale_running_jobs", lambda: 0)
    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "shutdown_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "claim_backfill_jobs", lambda conn, **kwargs: [jobs[1]])
    monkeypatch.setattr(minute_backfill, "mark_job_success", lambda job_id, row_count_market, row_count_staging: marked.append(("success", job_id, row_count_market, row_count_staging)))
    monkeypatch.setattr(minute_backfill, "mark_job_failed", lambda job_id, error: marked.append(("failed", job_id, error)))
    monkeypatch.setattr(
        minute_backfill,
        "run_backfill_job_worker",
        lambda job, sleep_seconds: {
            "job_id": job["job_id"],
            "row_count_market": 1,
            "row_count_staging": 1,
            "error": None,
        },
    )

    result = minute_backfill.run_baostock_minute_backfill(max_jobs=10)

    assert result["attempted"] == 1
    assert result["success"] == 1
    assert marked == [("success", "pending", 1, 1)]


def test_run_backfill_job_worker_passes_request_timeout_to_baostock_query(monkeypatch):
    calls = {}
    job = {
        "job_id": "job-timeout",
        "baostock_code": "sz.000001",
        "start_date": dt.date(2024, 1, 1),
        "end_date": dt.date(2024, 1, 31),
        "freq": "5min",
        "adjust_type": "raw",
    }

    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(
        minute_backfill,
        "request_params",
        lambda baostock_code, start_date, end_date, freq, adjust_type: {
            "code": baostock_code,
            "start_date": start_date,
            "end_date": end_date,
            "freq": freq,
            "adjust_type": adjust_type,
        },
    )

    def fake_query(baostock_code, start_date, end_date, freq, adjust_type, timeout_seconds=None):
        calls["timeout_seconds"] = timeout_seconds
        return []

    monkeypatch.setattr(minute_backfill, "query_baostock_minute_rows", fake_query)
    monkeypatch.setattr(minute_backfill, "upsert_stock_minute_bars", lambda rows, freq, adjust_type, params: 0)

    result = minute_backfill._run_backfill_job_worker_attempt(job, sleep_seconds=0, request_timeout_seconds=30)

    assert result["error"] is None
    assert calls["timeout_seconds"] == 30


def test_run_backfill_job_worker_returns_error_when_baostock_query_exceeds_timeout(monkeypatch):
    job = {
        "job_id": "job-timeout",
        "baostock_code": "sz.000001",
        "start_date": dt.date(2024, 1, 1),
        "end_date": dt.date(2024, 1, 31),
        "freq": "5min",
        "adjust_type": "raw",
    }

    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(
        minute_backfill,
        "request_params",
        lambda baostock_code, start_date, end_date, freq, adjust_type: {},
    )

    def slow_query(*_args, **_kwargs):
        time.sleep(1)
        return []

    monkeypatch.setattr(minute_backfill, "query_baostock_minute_rows", slow_query)

    result = minute_backfill.run_backfill_job_worker(
        job,
        sleep_seconds=0,
        request_timeout_seconds=0.01,
    )

    assert result["job_id"] == "job-timeout"
    assert "timed out after 0.01 seconds" in result["error"]


def test_run_backfill_marks_worker_errors_skipped_so_watchdog_does_not_retry_immediately(monkeypatch):
    jobs = [
        {
            "job_id": "hung-job",
            "baostock_code": "sz.002560",
            "start_date": dt.date(2020, 1, 2),
            "end_date": dt.date(2020, 1, 31),
            "freq": "5min",
            "adjust_type": "raw",
            "status": "pending",
        }
    ]
    marked = []

    monkeypatch.setattr(minute_backfill, "connect", fake_connect)
    monkeypatch.setattr(minute_backfill, "reset_stale_running_jobs", lambda: 0)
    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "shutdown_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "claim_backfill_jobs", lambda conn, **kwargs: jobs)
    monkeypatch.setattr(minute_backfill, "mark_job_success", lambda *args: marked.append(("success", args)))
    monkeypatch.setattr(minute_backfill, "mark_job_failed", lambda *args: marked.append(("failed", args)))
    monkeypatch.setattr(minute_backfill, "mark_job_skipped", lambda job_id, error: marked.append(("skipped", job_id, error)))
    monkeypatch.setattr(
        minute_backfill,
        "run_backfill_job_worker",
        lambda job, sleep_seconds: {
            "job_id": job["job_id"],
            "row_count_market": 0,
            "row_count_staging": 0,
            "error": "TimeoutError: baostock request timed out",
        },
    )

    result = minute_backfill.run_baostock_minute_backfill(max_jobs=1, workers=1)

    assert result == {"attempted": 1, "success": 0, "failed": 1, "rows": 0}
    assert marked == [("skipped", "hung-job", "TimeoutError: baostock request timed out")]


def test_derive_qfq_minute_bars_from_raw_job_scales_prices_and_marks_qfq_job(monkeypatch):
    conn = FakeConnection(rows=[{"raw_rows": 48, "inserted_rows": 48}])
    monkeypatch.setattr(minute_backfill, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(minute_backfill, "execute", lambda conn, sql, params=None: conn.executed.append((sql, params)))

    rows = derive_qfq_minute_bars_from_raw_job(
        conn,
        {
            "asset_id": "CN:SH:600000",
            "ts_code": "600000.SH",
            "start_date": dt.date(2024, 1, 1),
            "end_date": dt.date(2024, 1, 31),
            "freq": "5min",
            "source": "baostock",
        },
    )

    insert_sql, insert_params = conn.executed[0]
    mark_sql, mark_params = conn.executed[1]
    assert rows == 48
    assert "INSERT INTO market.stock_minute_bar" in insert_sql
    assert "raw.open * af.qfq_factor" in insert_sql
    assert "raw.high * af.qfq_factor" in insert_sql
    assert "raw.low * af.qfq_factor" in insert_sql
    assert "raw.close * af.qfq_factor" in insert_sql
    assert "raw.volume" in insert_sql
    assert "raw.amount" in insert_sql
    assert "raw.source" in insert_sql
    assert "af.qfq_factor IS NOT NULL" in insert_sql
    assert insert_params == [
        "CN:SH:600000",
        "600000.SH",
        dt.date(2024, 1, 1),
        dt.date(2024, 1, 31),
        "5min",
        "baostock",
    ]
    assert "UPDATE market.minute_bar_backfill_job" in mark_sql
    assert "adjust_type = 'qfq'" in mark_sql
    assert "row_count_staging = 0" in mark_sql
    assert mark_params == [48, "CN:SH:600000", dt.date(2024, 1, 1), dt.date(2024, 1, 31), "5min", "baostock"]


def test_run_backfill_derives_qfq_after_raw_success_when_requested(monkeypatch):
    jobs = [
        {
            "job_id": "raw-job",
            "asset_id": "CN:SH:600000",
            "ts_code": "600000.SH",
            "baostock_code": "sh.600000",
            "start_date": dt.date(2024, 1, 1),
            "end_date": dt.date(2024, 1, 31),
            "freq": "5min",
            "adjust_type": "raw",
            "status": "pending",
            "source": "baostock",
        }
    ]
    marked = []
    derived = []

    monkeypatch.setattr(minute_backfill, "connect", fake_connect)
    monkeypatch.setattr(minute_backfill, "reset_stale_running_jobs", lambda: 0)
    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "shutdown_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "claim_backfill_jobs", lambda conn, **kwargs: jobs)
    monkeypatch.setattr(minute_backfill, "mark_job_success", lambda job_id, row_count_market, row_count_staging: marked.append(("success", job_id, row_count_market, row_count_staging)))
    monkeypatch.setattr(minute_backfill, "mark_job_failed", lambda job_id, error: marked.append(("failed", job_id, error)))
    monkeypatch.setattr(
        minute_backfill,
        "run_backfill_job_worker",
        lambda job, sleep_seconds: {
            "job_id": job["job_id"],
            "row_count_market": 768,
            "row_count_staging": 768,
            "error": None,
        },
    )

    def fake_derive(conn, job):
        derived.append((conn, job))
        return 768

    monkeypatch.setattr(minute_backfill, "derive_qfq_minute_bars_from_raw_job", fake_derive)

    result = minute_backfill.run_baostock_minute_backfill(
        max_jobs=1,
        adjust_types=["raw", "qfq"],
        workers=1,
    )

    assert result == {"attempted": 1, "success": 2, "failed": 0, "rows": 1536}
    assert marked == [("success", "raw-job", 768, 768)]
    assert derived[0][1]["job_id"] == "raw-job"


def test_run_backfill_reports_progress_every_100_jobs(monkeypatch):
    jobs = [
        {
            "job_id": f"job{i}",
            "baostock_code": "sh.600000",
            "start_date": dt.date(2024, 1, 1),
            "end_date": dt.date(2024, 1, 1),
            "freq": "5min",
            "adjust_type": "raw",
            "status": "pending",
        }
        for i in range(201)
    ]
    progress_events = []

    monkeypatch.setattr(minute_backfill, "connect", fake_connect)
    monkeypatch.setattr(minute_backfill, "reset_stale_running_jobs", lambda: 0)
    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "shutdown_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "claim_backfill_jobs", lambda conn, **kwargs: jobs)
    monkeypatch.setattr(minute_backfill, "mark_job_success", lambda job_id, row_count_market, row_count_staging: None)
    monkeypatch.setattr(minute_backfill, "mark_job_failed", lambda job_id, error: None)
    monkeypatch.setattr(
        minute_backfill,
        "run_backfill_job_worker",
        lambda job, sleep_seconds: {
            "job_id": job["job_id"],
            "row_count_market": 48,
            "row_count_staging": 48,
            "error": None,
        },
    )

    result = minute_backfill.run_baostock_minute_backfill(
        max_jobs=500,
        sleep_seconds=0,
        progress=progress_events.append,
        progress_interval=100,
    )

    assert result == {"attempted": 201, "success": 201, "failed": 0, "rows": 9648}
    assert [event["event"] for event in progress_events] == [
        "minute_backfill_started",
        "minute_backfill_progress",
        "minute_backfill_progress",
        "minute_backfill_completed",
    ]
    assert [event["completed_jobs"] for event in progress_events] == [0, 100, 200, 201]
    assert progress_events[-1]["total_jobs"] == 201
    assert progress_events[-1]["success_jobs"] == 201


def test_run_backfill_reports_heartbeat_while_job_is_still_running(monkeypatch):
    jobs = [
        {
            "job_id": "slow-job",
            "baostock_code": "sh.600000",
            "start_date": dt.date(2024, 1, 1),
            "end_date": dt.date(2024, 1, 1),
            "freq": "5min",
            "adjust_type": "raw",
            "status": "pending",
        }
    ]
    progress_events = []

    monkeypatch.setattr(minute_backfill, "connect", fake_connect)
    monkeypatch.setattr(minute_backfill, "reset_stale_running_jobs", lambda: 0)
    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "shutdown_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "claim_backfill_jobs", lambda conn, **kwargs: jobs)
    monkeypatch.setattr(minute_backfill, "mark_job_success", lambda job_id, row_count_market, row_count_staging: None)
    monkeypatch.setattr(minute_backfill, "mark_job_failed", lambda job_id, error: None)

    def slow_worker(job, sleep_seconds):
        time.sleep(0.05)
        return {
            "job_id": job["job_id"],
            "row_count_market": 48,
            "row_count_staging": 48,
            "error": None,
        }

    monkeypatch.setattr(minute_backfill, "run_backfill_job_worker", slow_worker)

    minute_backfill.run_baostock_minute_backfill(
        max_jobs=1,
        sleep_seconds=0,
        progress=progress_events.append,
        progress_interval=100,
        progress_heartbeat_seconds=0.01,
    )

    heartbeat = next(event for event in progress_events if event["event"] == "minute_backfill_heartbeat")
    assert heartbeat["completed_jobs"] == 0
    assert heartbeat["total_jobs"] == 1


def test_claim_backfill_jobs_uses_skip_locked_and_marks_rows_running(monkeypatch):
    conn = FakeConnection(rows=[{"job_id": "job-1"}])
    monkeypatch.setattr(minute_backfill, "fetch_all", fake_fetch_all)

    rows = minute_backfill.claim_backfill_jobs(conn, max_jobs=5, retry_failed=True)

    assert rows == [{"job_id": "job-1"}]
    sql, params = conn.executed[0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "UPDATE market.minute_bar_backfill_job" in sql
    assert "status = 'running'" in sql
    assert "attempt_count = attempt_count + 1" in sql
    assert "RETURNING job.*" in sql
    assert params == [["pending", "failed"], 5]


def test_run_backfill_retries_failed_jobs_only_when_enabled(monkeypatch):
    seen_retry_flags = []

    def fake_claim_backfill_jobs(conn, **kwargs):
        seen_retry_flags.append(kwargs["retry_failed"])
        return []

    monkeypatch.setattr(minute_backfill, "connect", fake_connect)
    monkeypatch.setattr(minute_backfill, "reset_stale_running_jobs", lambda: 0)
    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "shutdown_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "claim_backfill_jobs", fake_claim_backfill_jobs)

    minute_backfill.run_baostock_minute_backfill(max_jobs=5, retry_failed=False)
    minute_backfill.run_baostock_minute_backfill(max_jobs=5, retry_failed=True)

    assert seen_retry_flags == [False, True]


def test_run_backfill_resets_stale_running_jobs_before_claim(monkeypatch):
    calls = []
    monkeypatch.setattr(minute_backfill, "connect", fake_connect)
    monkeypatch.setattr(minute_backfill, "reset_stale_running_jobs", lambda: calls.append("reset") or 1)
    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "shutdown_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "claim_backfill_jobs", lambda conn, **kwargs: calls.append("claim") or [])

    minute_backfill.run_baostock_minute_backfill(max_jobs=1)

    assert calls == ["reset", "claim"]


def test_run_backfill_can_skip_internal_stale_reset(monkeypatch):
    calls = []
    monkeypatch.setattr(minute_backfill, "connect", fake_connect)
    monkeypatch.setattr(minute_backfill, "reset_stale_running_jobs", lambda: calls.append("reset") or 1)
    monkeypatch.setattr(minute_backfill, "initialize_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "shutdown_backfill_worker", lambda: None)
    monkeypatch.setattr(minute_backfill, "claim_backfill_jobs", lambda conn, **kwargs: calls.append("claim") or [])

    minute_backfill.run_baostock_minute_backfill(max_jobs=1, reset_stale_before_run=False)

    assert calls == ["claim"]


def test_run_backfill_parallel_workers_aggregate_results(monkeypatch):
    marked = []
    jobs = [
        {
            "job_id": "job1",
            "baostock_code": "sh.600000",
            "start_date": dt.date(2024, 1, 1),
            "end_date": dt.date(2024, 1, 2),
            "freq": "5min",
            "adjust_type": "raw",
            "status": "pending",
        },
        {
            "job_id": "job2",
            "baostock_code": "sz.000001",
            "start_date": dt.date(2024, 1, 1),
            "end_date": dt.date(2024, 1, 2),
            "freq": "5min",
            "adjust_type": "qfq",
            "status": "pending",
        },
    ]

    class FakeFuture:
        def __init__(self, value):
            self.value = value

        def result(self):
            return self.value

    class FakeExecutor:
        def __init__(self, max_workers, **kwargs):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, job, sleep_seconds):
            return FakeFuture(fn(job, sleep_seconds))

    monkeypatch.setattr(minute_backfill, "connect", fake_connect)
    monkeypatch.setattr(minute_backfill, "reset_stale_running_jobs", lambda: 0)
    monkeypatch.setattr(minute_backfill, "claim_backfill_jobs", lambda conn, **kwargs: jobs)
    monkeypatch.setattr(minute_backfill, "mark_job_success", lambda job_id, row_count_market, row_count_staging: marked.append(("success", job_id, row_count_market, row_count_staging)))
    monkeypatch.setattr(minute_backfill, "mark_job_failed", lambda job_id, error: marked.append(("failed", job_id, error)))
    monkeypatch.setattr(minute_backfill, "ProcessPoolExecutor", FakeExecutor)
    monkeypatch.setattr(
        minute_backfill,
        "as_completed",
        lambda futures: futures,
    )
    monkeypatch.setattr(
        minute_backfill,
        "run_backfill_job_worker",
        lambda job, sleep_seconds: {
            "job_id": job["job_id"],
            "row_count_market": 48,
            "row_count_staging": 48,
            "error": None,
        },
    )

    result = minute_backfill.run_baostock_minute_backfill(max_jobs=10, workers=2)

    assert result == {"attempted": 2, "success": 2, "failed": 0, "rows": 96}
    assert marked == [
        ("success", "job1", 48, 48),
        ("success", "job2", 48, 48),
    ]


def test_benchmark_minute_backfill_workers_reports_throughput(monkeypatch):
    calls = []
    times = iter([100.0, 110.0, 200.0, 220.0])

    def fake_run_baostock_minute_backfill(**kwargs):
        calls.append(kwargs)
        workers = kwargs["workers"]
        return {
            "attempted": 10,
            "success": 9 if workers == 4 else 10,
            "failed": 1 if workers == 4 else 0,
            "rows": 432 if workers == 4 else 480,
        }

    monkeypatch.setattr(minute_backfill.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(
        minute_backfill,
        "run_baostock_minute_backfill",
        fake_run_baostock_minute_backfill,
    )

    result = minute_backfill.benchmark_baostock_minute_backfill_workers(
        worker_counts=[4, 8],
        start_date="2026-06-10",
        end_date="2026-06-10",
        freq="5min",
        adjust_types=["raw"],
        max_jobs=10,
        retry_failed=True,
        sleep_seconds=0.05,
    )

    assert calls == [
        {
            "start_date": "2026-06-10",
            "end_date": "2026-06-10",
            "freq": "5min",
            "adjust_types": ["raw"],
            "batch_by": "month",
            "max_jobs": 10,
            "retry_failed": True,
            "sleep_seconds": 0.05,
            "workers": 4,
            "reset_stale_before_run": True,
        },
        {
            "start_date": "2026-06-10",
            "end_date": "2026-06-10",
            "freq": "5min",
            "adjust_types": ["raw"],
            "batch_by": "month",
            "max_jobs": 10,
            "retry_failed": True,
            "sleep_seconds": 0.05,
            "workers": 8,
            "reset_stale_before_run": True,
        },
    ]
    assert result["summary"] == {
        "worker_counts": [4, 8],
        "best_workers_by_rows_per_second": 4,
        "total_attempted": 20,
        "total_failed": 1,
    }
    assert result["rows"] == [
        {
            "workers": 4,
            "attempted": 10,
            "success": 9,
            "failed": 1,
            "rows": 432,
            "elapsed_seconds": 10.0,
            "jobs_per_second": 1.0,
            "rows_per_second": 43.2,
            "failed_rate": 0.1,
        },
        {
            "workers": 8,
            "attempted": 10,
            "success": 10,
            "failed": 0,
            "rows": 480,
            "elapsed_seconds": 20.0,
            "jobs_per_second": 0.5,
            "rows_per_second": 24.0,
            "failed_rate": 0.0,
        },
    ]


def test_summarize_backfill_status_counts_rows_and_statuses():
    summary = summarize_backfill_status(
        [
            {"status": "pending", "row_count_market": 0, "row_count_staging": 0},
            {"status": "success", "row_count_market": 48, "row_count_staging": 48},
            {"status": "failed", "row_count_market": 0, "row_count_staging": 0},
        ]
    )

    assert summary["total_jobs"] == 3
    assert summary["pending_jobs"] == 1
    assert summary["success_jobs"] == 1
    assert summary["failed_jobs"] == 1
    assert summary["total_market_rows"] == 48
    assert summary["total_staging_rows"] == 48


def test_plan_backfill_writes_live_status_into_plan_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(
        minute_backfill,
        "load_backfill_assets",
        lambda limit_assets=None: [
            {"asset_id": "CN:SH:600000", "ts_code": "600000.SH", "baostock_code": "sh.600000"}
        ],
    )
    monkeypatch.setattr(minute_backfill, "upsert_backfill_jobs", lambda jobs: len(jobs))
    monkeypatch.setattr(
        minute_backfill,
        "load_backfill_status_rows",
        lambda **kwargs: [
            {
                "job_id": minute_backfill.job_id_for(
                    "600000.SH",
                    dt.date(2024, 1, 1),
                    dt.date(2024, 1, 31),
                    "5min",
                    "raw",
                    "baostock",
                ),
                "status": "success",
                "attempt_count": 2,
                "row_count_market": 1056,
                "row_count_staging": 1056,
                "last_error": None,
                "updated_at": dt.datetime(2024, 2, 1, 9, 0),
                "finished_at": dt.datetime(2024, 2, 1, 9, 1),
            }
        ],
    )

    minute_backfill.plan_baostock_minute_backfill(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        output_dir=tmp_path,
    )

    rows = list(__import__("csv").DictReader((tmp_path / "minute_backfill_plan_jobs.csv").open()))
    assert rows[0]["status"] == "success"
    assert rows[0]["attempt_count"] == "2"
    assert rows[0]["row_count_market"] == "1056"


def test_run_backfill_range_reports_each_completed_month(monkeypatch):
    reports = []
    monkeypatch.setattr(
        minute_backfill,
        "plan_baostock_minute_backfill",
        lambda **kwargs: {"summary": {"job_count": 2}},
    )
    monkeypatch.setattr(
        minute_backfill,
        "run_baostock_minute_backfill",
        lambda **kwargs: {"attempted": 2, "success": 2, "failed": 0, "rows": 96},
    )
    monkeypatch.setattr(
        minute_backfill,
        "load_backfill_status_rows",
        lambda **kwargs: [
            {
                "status": "success",
                "row_count_market": 48,
                "row_count_staging": 48,
                "finished_at": None,
            },
            {
                "status": "success",
                "row_count_market": 48,
                "row_count_staging": 48,
                "finished_at": None,
            },
        ],
    )
    monkeypatch.setattr(
        minute_backfill,
        "validate_minute_bars",
        lambda **kwargs: {"summary": {"error_count": 0, "market_rows": 96, "staging_rows": 96}},
    )

    result = minute_backfill.run_baostock_minute_backfill_range(
        start_date="2024-01-01",
        end_date="2024-02-29",
        freq="5min",
        adjust_types=["raw", "qfq"],
        report=lambda summary: reports.append(summary),
    )

    assert result["months"] == 2
    assert len(reports) == 2
    assert reports[0]["month"] == "2024-01"
    assert reports[1]["month"] == "2024-02"


def test_run_minute_backfill_cli_passes_progress_renderer_and_keeps_summary(monkeypatch, capsys):
    from stock_research import cli

    captured = {}

    def fake_run_baostock_minute_backfill(**kwargs):
        captured.update(kwargs)
        kwargs["progress"](
            {
                "event": "minute_backfill_progress",
                "completed_jobs": 1,
                "total_jobs": 2,
                "success_jobs": 1,
                "failed_jobs": 0,
                "rows": 48,
            }
        )
        return {"attempted": 1, "success": 1, "failed": 0, "rows": 48}

    monkeypatch.setattr(cli, "run_baostock_minute_backfill", fake_run_baostock_minute_backfill)

    cli.main_for_args(
        [
            "run-baostock-minute-backfill",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--freq",
            "5min",
            "--adjust-types",
            "raw",
            "--max-jobs",
            "2",
            "--progress-interval",
            "1",
        ]
    )

    output = capsys.readouterr()
    assert callable(captured["progress"])
    assert captured["progress_interval"] == 1
    assert "minute_backfill_run|rows|48" in output.out
    assert "progress|minute5_backfill|event|minute_backfill_progress|completed|1|total|2" in output.err


def test_validate_minute_bar_rows_finds_duplicate_ohlc_mismatch_and_date_errors():
    rows = [
        {
            "asset_id": "CN:SH:600000",
            "trade_time": dt.datetime(2024, 1, 2, 9, 35),
            "trade_date": dt.date(2024, 1, 2),
            "freq": "5min",
            "adjust_type": "raw",
            "source": "baostock",
            "high": 1,
            "low": 2,
            "close": None,
            "volume": -1,
            "amount": 1,
        },
        {
            "asset_id": "CN:SH:600000",
            "trade_time": dt.datetime(2024, 1, 2, 9, 35),
            "trade_date": dt.date(2024, 1, 2),
            "freq": "5min",
            "adjust_type": "raw",
            "source": "baostock",
            "high": 2,
            "low": 1,
            "close": 1,
            "volume": 1,
            "amount": 1,
        },
        {
            "asset_id": "CN:SH:600000",
            "trade_time": dt.datetime(2024, 1, 3, 9, 35),
            "trade_date": dt.date(2024, 1, 2),
            "freq": "5min",
            "adjust_type": "qfq",
            "source": "baostock",
            "high": 2,
            "low": 1,
            "close": 1,
            "volume": 1,
            "amount": -1,
        },
    ]

    errors = validate_minute_bar_rows(rows, adjust_types=["raw", "qfq"])
    error_types = {error["error_type"] for error in errors}

    assert "duplicate_key" in error_types
    assert "high_less_than_low" in error_types
    assert "close_null" in error_types
    assert "negative_volume_or_amount" in error_types
    assert "trade_date_mismatch" in error_types
    assert "adjust_type_count_mismatch" in error_types
