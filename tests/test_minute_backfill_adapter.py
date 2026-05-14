import datetime as dt
import fcntl
import time

from stock_research.backfill_watchdog import BackfillSummary
from stock_research.minute_backfill_adapter import MinuteBackfillAdapter, _run_backfill_once_with_timeout


def _row(
    start_date: dt.date,
    end_date: dt.date,
    status: str,
    *,
    adjust_type: str = "raw",
    ts_code: str = "600000.SH",
    row_count_market: int = 0,
    row_count_staging: int = 0,
    finished_at: dt.datetime | None = None,
) -> dict[str, object]:
    return {
        "job_id": f"{ts_code}-{adjust_type}-{start_date.isoformat()}",
        "ts_code": ts_code,
        "adjust_type": adjust_type,
        "start_date": start_date,
        "end_date": end_date,
        "status": status,
        "row_count_market": row_count_market,
        "row_count_staging": row_count_staging,
        "finished_at": finished_at,
    }


def test_minute_backfill_adapter_load_scope_reports_task_dataset_run_id_and_window():
    adapter = MinuteBackfillAdapter(
        start_date="2024-01-01",
        end_date="2024-03-31",
        freq="5min",
        adjust_types=["raw", "qfq"],
    )

    scope = adapter.load_scope()

    assert scope == {
        "task": "minute_backfill",
        "task_name": "minute_backfill",
        "dataset": "market.stock_minute_bar",
        "run_id": "minute-backfill:5min:raw,qfq:2024-01-01:2024-03-31",
        "window": "2024-01-01..2024-03-31",
    }


def test_minute_backfill_adapter_compute_frontier_uses_month_rollup():
    adapter = MinuteBackfillAdapter(
        start_date="2024-01-01",
        end_date="2024-04-30",
        freq="5min",
        adjust_types=["raw", "qfq"],
    )
    rows = [
        _row(dt.date(2024, 1, 1), dt.date(2024, 1, 31), "success", adjust_type="raw"),
        _row(dt.date(2024, 1, 1), dt.date(2024, 1, 31), "skipped", adjust_type="qfq"),
        _row(dt.date(2024, 2, 1), dt.date(2024, 2, 29), "success", adjust_type="raw"),
        _row(dt.date(2024, 2, 1), dt.date(2024, 2, 29), "success", adjust_type="qfq"),
        _row(dt.date(2024, 3, 1), dt.date(2024, 3, 31), "running", adjust_type="raw"),
        _row(dt.date(2024, 3, 1), dt.date(2024, 3, 31), "pending", adjust_type="qfq"),
        _row(dt.date(2024, 4, 1), dt.date(2024, 4, 30), "pending", adjust_type="raw"),
    ]

    frontier = adapter.compute_frontier(rows)

    assert frontier == {
        "completed_through": "2024-02",
        "currently_working_on": "2024-03",
    }


def test_minute_backfill_adapter_summarize_status_maps_shared_summary_fields():
    adapter = MinuteBackfillAdapter(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
    )
    rows = [
        _row(dt.date(2024, 1, 1), dt.date(2024, 1, 31), "success", row_count_market=240),
        _row(dt.date(2024, 1, 1), dt.date(2024, 1, 31), "pending"),
    ]

    summary = adapter.summarize_status(rows)

    assert summary == BackfillSummary(
        total_tasks=2,
        pending_tasks=1,
        running_tasks=0,
        success_tasks=1,
        failed_tasks=0,
        skipped_tasks=0,
        total_rows_written=240,
    )


def test_minute_backfill_adapter_run_once_disables_internal_stale_reset(monkeypatch):
    adapter = MinuteBackfillAdapter(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
    )
    seen = {}

    monkeypatch.setattr(
        "stock_research.minute_backfill_adapter._run_backfill_once_with_timeout",
        lambda **kwargs: seen.update(kwargs) or {
            "attempted": 0,
            "success": 0,
            "failed": 0,
            "rows": 0,
            "status": "completed",
            "timed_out": False,
        },
    )

    adapter.run_once(
        scope=adapter.load_scope(),
        max_jobs=100,
        workers=2,
        run_timeout_seconds=900,
    )

    assert seen["reset_stale_before_run"] is False


def test_run_backfill_once_with_timeout_terminates_work_in_background(monkeypatch, tmp_path):
    marker = tmp_path / "completed.txt"

    def fake_run_baostock_minute_backfill(**kwargs):
        time.sleep(0.2)
        marker.write_text("done")
        return {
            "attempted": 1,
            "success": 1,
            "failed": 0,
            "rows": 240,
        }

    monkeypatch.setattr(
        "stock_research.minute_backfill_adapter.run_baostock_minute_backfill",
        fake_run_baostock_minute_backfill,
    )

    result = _run_backfill_once_with_timeout(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        batch_by="month",
        max_jobs=100,
        retry_failed=True,
        sleep_seconds=0.0,
        workers=2,
        run_timeout_seconds=0.01,
        reset_stale_before_run=False,
    )
    time.sleep(0.35)

    assert result["timed_out"] is True
    assert marker.exists() is False


def test_run_backfill_once_with_timeout_reports_failed_when_child_exits_without_result(monkeypatch):
    monkeypatch.setattr(
        "stock_research.minute_backfill_adapter.run_baostock_minute_backfill",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = _run_backfill_once_with_timeout(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        batch_by="month",
        max_jobs=100,
        retry_failed=True,
        sleep_seconds=0.0,
        workers=2,
        run_timeout_seconds=5,
        reset_stale_before_run=False,
    )

    assert result == {
        "attempted": 0,
        "success": 0,
        "failed": 1,
        "rows": 0,
        "status": "failed",
        "timed_out": False,
    }


def test_run_backfill_once_with_timeout_skips_when_watchdog_lock_is_busy(tmp_path):
    lock_path = tmp_path / "minute-backfill-watchdog.lock"
    with lock_path.open("w") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        result = _run_backfill_once_with_timeout(
            start_date="2024-01-01",
            end_date="2024-01-31",
            freq="5min",
            adjust_types=["raw"],
            batch_by="month",
            max_jobs=100,
            retry_failed=True,
            sleep_seconds=0.0,
            workers=2,
            run_timeout_seconds=5,
            reset_stale_before_run=False,
            lock_path=lock_path,
        )

    assert result == {
        "attempted": 0,
        "success": 0,
        "failed": 0,
        "rows": 0,
        "status": "already_running",
        "timed_out": False,
        "lock_busy": True,
    }
