import datetime as dt
from contextlib import contextmanager

from stock_research import minute_backfill
from stock_research.minute_backfill import (
    BackfillJob,
    build_backfill_jobs,
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
