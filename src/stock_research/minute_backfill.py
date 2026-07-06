import atexit
import csv
import datetime as dt
import hashlib
import multiprocessing as mp
import queue
import signal
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from stock_research.config import SETTINGS
from stock_research.db import connect, execute, execute_many, fetch_all
from stock_research.minute_data import (
    bs,
    login_or_raise,
    query_baostock_minute_rows,
    request_params,
    upsert_stock_minute_bars,
)


TRADING_MINUTE_BARS_PER_DAY = {"5min": 48, "1min": 240, "15min": 16, "30min": 8, "60min": 4}
_WORKER_BAOSTOCK_READY = False
BACKFILL_JOB_REQUEST_TIMEOUT_SECONDS = 30.0
BACKFILL_JOB_MAX_ATTEMPTS = 2


class BackfillJobTimeoutError(TimeoutError):
    pass


@dataclass(frozen=True)
class BackfillJob:
    job_id: str
    asset_id: str
    ts_code: str
    baostock_code: str
    start_date: dt.date
    end_date: dt.date
    freq: str
    adjust_type: str
    source: str = "baostock"
    status: str = "pending"
    estimated_rows: int = 0


def parse_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def month_ranges(start_date: dt.date, end_date: dt.date) -> list[tuple[dt.date, dt.date]]:
    ranges = []
    current = start_date
    while current <= end_date:
        if current.month == 12:
            next_month = dt.date(current.year + 1, 1, 1)
        else:
            next_month = dt.date(current.year, current.month + 1, 1)
        period_end = min(end_date, next_month - dt.timedelta(days=1))
        ranges.append((current, period_end))
        current = period_end + dt.timedelta(days=1)
    return ranges


def build_backfill_jobs(
    assets: list[dict[str, Any]],
    start_date: dt.date,
    end_date: dt.date,
    freq: str,
    adjust_types: list[str],
    batch_by: str = "month",
    source: str = "baostock",
) -> list[BackfillJob]:
    if batch_by != "month":
        raise ValueError("minute backfill v1 supports batch_by=month")
    periods = month_ranges(start_date, end_date)
    jobs: list[BackfillJob] = []
    for asset in assets:
        for period_start, period_end in periods:
            estimated_rows = estimate_rows(period_start, period_end, freq)
            for adjust_type in adjust_types:
                jobs.append(
                    BackfillJob(
                        job_id=job_id_for(
                            str(asset["ts_code"]),
                            period_start,
                            period_end,
                            freq,
                            adjust_type,
                            source,
                        ),
                        asset_id=str(asset["asset_id"]),
                        ts_code=str(asset["ts_code"]),
                        baostock_code=str(asset["baostock_code"]),
                        start_date=period_start,
                        end_date=period_end,
                        freq=freq,
                        adjust_type=adjust_type,
                        source=source,
                        estimated_rows=estimated_rows,
                    )
                )
    return jobs


def job_id_for(
    ts_code: str,
    start_date: dt.date,
    end_date: dt.date,
    freq: str,
    adjust_type: str,
    source: str,
) -> str:
    payload = f"{ts_code}|{start_date}|{end_date}|{freq}|{adjust_type}|{source}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:24]


def estimate_rows(start_date: dt.date, end_date: dt.date, freq: str) -> int:
    bars_per_day = TRADING_MINUTE_BARS_PER_DAY[freq]
    days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            days += 1
        current += dt.timedelta(days=1)
    return days * bars_per_day


def load_backfill_assets(
    limit_assets: int | None = None,
    research_service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT
        asset_id,
        COALESCE(NULLIF(ts_code, ''), split_part(baostock_code, '.', 2) || '.' || upper(split_part(baostock_code, '.', 1))) AS ts_code,
        baostock_code
    FROM core.asset_master
    WHERE is_active = true
      AND baostock_code IS NOT NULL
      AND baostock_code <> ''
    ORDER BY baostock_code
    """
    params: list[Any] = []
    if limit_assets is not None:
        sql += "\nLIMIT %s"
        params.append(limit_assets)
    with connect(research_service) as conn:
        return fetch_all(conn, sql, params)


def upsert_backfill_jobs(
    jobs: list[BackfillJob],
    research_service: str = SETTINGS.research_service,
) -> int:
    if not jobs:
        return 0
    sql = """
    INSERT INTO market.minute_bar_backfill_job (
        job_id, asset_id, ts_code, baostock_code, start_date, end_date,
        freq, adjust_type, source, status
    )
    VALUES (
        %(job_id)s, %(asset_id)s, %(ts_code)s, %(baostock_code)s, %(start_date)s,
        %(end_date)s, %(freq)s, %(adjust_type)s, %(source)s, %(status)s
    )
    ON CONFLICT (ts_code, start_date, end_date, freq, adjust_type, source)
    DO UPDATE SET
        asset_id = EXCLUDED.asset_id,
        baostock_code = EXCLUDED.baostock_code,
        updated_at = now()
    """
    with connect(research_service) as conn:
        execute_many(conn, sql, [asdict(job) for job in jobs])
    return len(jobs)


def plan_baostock_minute_backfill(
    start_date: str,
    end_date: str,
    freq: str,
    adjust_types: list[str],
    batch_by: str = "month",
    output_dir: str | Path = "outputs/research",
    limit_assets: int | None = None,
) -> dict[str, Any]:
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date)
    assets = load_backfill_assets(limit_assets=limit_assets)
    jobs = build_backfill_jobs(
        assets,
        parsed_start,
        parsed_end,
        freq=freq,
        adjust_types=adjust_types,
        batch_by=batch_by,
    )
    upsert_backfill_jobs(jobs)
    status = load_backfill_status_rows(
        start_date=parsed_start,
        end_date=parsed_end,
        freq=freq,
        adjust_types=adjust_types,
    )
    status_by_job_id = {str(row["job_id"]): row for row in status}
    summary = {
        "stock_count": len(assets),
        "month_count": len(month_ranges(parsed_start, parsed_end)),
        "adjust_type_count": len(adjust_types),
        "job_count": len(jobs),
        "estimated_rows": sum(job.estimated_rows for job in jobs),
        "completed_jobs": sum(1 for row in status if row["status"] == "success"),
        "pending_jobs": sum(1 for row in status if row["status"] == "pending"),
    }
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    job_rows = []
    for job in jobs:
        row = asdict(job)
        live = status_by_job_id.get(str(job.job_id))
        if live:
            row["status"] = live.get("status", row["status"])
            row["attempt_count"] = live.get("attempt_count")
            row["row_count_market"] = live.get("row_count_market")
            row["row_count_staging"] = live.get("row_count_staging")
            row["last_error"] = live.get("last_error")
            row["updated_at"] = live.get("updated_at")
            row["finished_at"] = live.get("finished_at")
        job_rows.append(row)
    write_csv(output_path / "minute_backfill_plan_jobs.csv", job_rows)
    write_csv(output_path / "minute_backfill_plan_summary.csv", [summary])
    return {"summary": summary, "jobs": jobs}


def claim_backfill_jobs(
    conn,
    max_jobs: int,
    retry_failed: bool = False,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    freq: str | None = None,
    adjust_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    statuses = ["pending"]
    if retry_failed:
        statuses.append("failed")
    filters = ["status = ANY(%s)"]
    params: list[Any] = [statuses]
    if start_date:
        filters.append("end_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("start_date <= %s")
        params.append(end_date)
    if freq:
        filters.append("freq = %s")
        params.append(freq)
    if adjust_types:
        filters.append("adjust_type = ANY(%s)")
        params.append(adjust_types)
    params.append(max_jobs)
    sql = f"""
    WITH claimed AS (
        SELECT job_id
        FROM market.minute_bar_backfill_job
        WHERE {' AND '.join(filters)}
        ORDER BY start_date, ts_code, adjust_type
        LIMIT %s
        FOR UPDATE SKIP LOCKED
    )
    UPDATE market.minute_bar_backfill_job AS job
    SET status = 'running',
        attempt_count = attempt_count + 1,
        started_at = now(),
        finished_at = NULL,
        last_error = NULL,
        updated_at = now()
    FROM claimed
    WHERE job.job_id = claimed.job_id
    RETURNING job.*
    """
    return fetch_all(conn, sql, params)


def mark_job_running(job_id: str, research_service: str = SETTINGS.research_service) -> None:
    sql = """
    UPDATE market.minute_bar_backfill_job
    SET status = 'running',
        attempt_count = attempt_count + 1,
        started_at = now(),
        finished_at = NULL,
        last_error = NULL,
        updated_at = now()
    WHERE job_id = %s
    """
    with connect(research_service) as conn:
        execute(conn, sql, [job_id])


def mark_jobs_running(
    job_ids: list[str],
    research_service: str = SETTINGS.research_service,
) -> None:
    if not job_ids:
        return
    sql = """
    UPDATE market.minute_bar_backfill_job
    SET status = 'running',
        attempt_count = attempt_count + 1,
        started_at = now(),
        finished_at = NULL,
        last_error = NULL,
        updated_at = now()
    WHERE job_id = ANY(%s)
    """
    with connect(research_service) as conn:
        execute(conn, sql, [job_ids])


def mark_job_success(
    job_id: str,
    row_count_market: int,
    row_count_staging: int,
    research_service: str = SETTINGS.research_service,
) -> None:
    sql = """
    UPDATE market.minute_bar_backfill_job
    SET status = 'success',
        row_count_market = %s,
        row_count_staging = %s,
        finished_at = now(),
        updated_at = now()
    WHERE job_id = %s
    """
    with connect(research_service) as conn:
        execute(conn, sql, [row_count_market, row_count_staging, job_id])


def mark_job_failed(
    job_id: str,
    error: str,
    research_service: str = SETTINGS.research_service,
) -> None:
    sql = """
    UPDATE market.minute_bar_backfill_job
    SET status = 'failed',
        last_error = %s,
        finished_at = now(),
        updated_at = now()
    WHERE job_id = %s
    """
    with connect(research_service) as conn:
        execute(conn, sql, [error[:4000], job_id])


def mark_job_skipped(
    job_id: str,
    error: str,
    research_service: str = SETTINGS.research_service,
) -> None:
    sql = """
    UPDATE market.minute_bar_backfill_job
    SET status = 'skipped',
        last_error = %s,
        finished_at = now(),
        updated_at = now()
    WHERE job_id = %s
    """
    with connect(research_service) as conn:
        execute(conn, sql, [error[:4000], job_id])


def derive_qfq_minute_bars_from_raw_job(conn, job: dict[str, Any]) -> int:
    sql = """
    WITH raw_rows AS (
        SELECT
            raw.asset_id,
            raw.ts_code,
            raw.trade_time,
            raw.trade_date,
            raw.freq,
            raw.open,
            raw.high,
            raw.low,
            raw.close,
            raw.volume,
            raw.amount,
            raw.source
        FROM market.stock_minute_bar raw
        WHERE raw.asset_id = %s
          AND raw.ts_code = %s
          AND raw.trade_date BETWEEN %s AND %s
          AND raw.freq = %s
          AND raw.adjust_type = 'raw'
          AND raw.source = %s
    ),
    upserted AS (
        INSERT INTO market.stock_minute_bar (
            asset_id, ts_code, trade_time, trade_date, freq, adjust_type,
            open, high, low, close, volume, amount, source
        )
        SELECT
            raw.asset_id,
            raw.ts_code,
            raw.trade_time,
            raw.trade_date,
            raw.freq,
            'qfq' AS adjust_type,
            raw.open * af.qfq_factor AS open,
            raw.high * af.qfq_factor AS high,
            raw.low * af.qfq_factor AS low,
            raw.close * af.qfq_factor AS close,
            raw.volume,
            raw.amount,
            raw.source
        FROM raw_rows raw
        JOIN LATERAL (
            SELECT af.qfq_factor
            FROM market.adjustment_factor af
            WHERE af.asset_id = raw.asset_id
              AND af.trade_date = raw.trade_date
              AND af.qfq_factor IS NOT NULL
            ORDER BY
                CASE WHEN af.source_version = 'derived_market_daily_bar_v1' THEN 0 ELSE 1 END,
                af.updated_at DESC
            LIMIT 1
        ) af ON true
        ON CONFLICT (trade_date, asset_id, trade_time, freq, adjust_type, source)
        DO UPDATE SET
            ts_code = EXCLUDED.ts_code,
            trade_date = EXCLUDED.trade_date,
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            amount = EXCLUDED.amount,
            updated_at = now()
        RETURNING 1
    )
    SELECT
        (SELECT count(*) FROM raw_rows) AS raw_rows,
        (SELECT count(*) FROM upserted) AS inserted_rows
    """
    params = [
        job["asset_id"],
        job["ts_code"],
        job["start_date"],
        job["end_date"],
        job["freq"],
        job.get("source", "baostock"),
    ]
    row = fetch_all(conn, sql, params)[0]
    raw_rows = int(row.get("raw_rows") or 0)
    inserted_rows = int(row.get("inserted_rows") or 0)
    if inserted_rows != raw_rows:
        error = (
            "derived qfq minute rows do not match raw rows; "
            f"raw_rows={raw_rows}, inserted_rows={inserted_rows}"
        )
        _mark_derived_qfq_job_failed(conn, job, error)
        raise RuntimeError(error)
    _mark_derived_qfq_job_success(conn, job, inserted_rows)
    return inserted_rows


def _mark_derived_qfq_job_success(conn, job: dict[str, Any], row_count_market: int) -> None:
    sql = """
    UPDATE market.minute_bar_backfill_job
    SET status = 'success',
        row_count_market = %s,
        row_count_staging = 0,
        finished_at = now(),
        updated_at = now(),
        last_error = NULL
    WHERE asset_id = %s
      AND start_date = %s
      AND end_date = %s
      AND freq = %s
      AND adjust_type = 'qfq'
      AND source = %s
    """
    execute(
        conn,
        sql,
        [
            row_count_market,
            job["asset_id"],
            job["start_date"],
            job["end_date"],
            job["freq"],
            job.get("source", "baostock"),
        ],
    )


def _mark_derived_qfq_job_failed(conn, job: dict[str, Any], error: str) -> None:
    sql = """
    UPDATE market.minute_bar_backfill_job
    SET status = 'failed',
        last_error = %s,
        finished_at = now(),
        updated_at = now()
    WHERE asset_id = %s
      AND start_date = %s
      AND end_date = %s
      AND freq = %s
      AND adjust_type = 'qfq'
      AND source = %s
    """
    execute(
        conn,
        sql,
        [
            error[:4000],
            job["asset_id"],
            job["start_date"],
            job["end_date"],
            job["freq"],
            job.get("source", "baostock"),
        ],
    )


def reset_stale_running_jobs(
    stale_after_minutes: int = 15,
    research_service: str = SETTINGS.research_service,
) -> int:
    sql = """
    UPDATE market.minute_bar_backfill_job
    SET status = 'pending',
        last_error = CASE
            WHEN last_error IS NULL OR last_error = '' THEN %s
            ELSE left(last_error || ' | ' || %s, 4000)
        END,
        updated_at = now()
    WHERE status = 'running'
      AND started_at < now() - (%s || ' minutes')::interval
    """
    note = f"auto-reset stale running job after {stale_after_minutes} minutes"
    with connect(research_service) as conn:
        before = fetch_all(
            conn,
            """
            SELECT count(*) AS count
            FROM market.minute_bar_backfill_job
            WHERE status = 'running'
              AND started_at < now() - (%s || ' minutes')::interval
            """,
            [stale_after_minutes],
        )[0]["count"]
        execute(conn, sql, [note, note, stale_after_minutes])
    return int(before or 0)


def reset_running_jobs_in_scope(
    *,
    started_at_or_after: dt.datetime,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    freq: str | None = None,
    adjust_types: list[str] | None = None,
    research_service: str = SETTINGS.research_service,
) -> int:
    filters = ["status = 'running'", "started_at >= %s"]
    params: list[Any] = [started_at_or_after]
    if start_date:
        filters.append("end_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("start_date <= %s")
        params.append(end_date)
    if freq:
        filters.append("freq = %s")
        params.append(freq)
    if adjust_types:
        filters.append("adjust_type = ANY(%s)")
        params.append(adjust_types)

    where_sql = " AND ".join(filters)
    note = "auto-reset running job after watchdog timeout"
    sql = f"""
    UPDATE market.minute_bar_backfill_job
    SET status = 'pending',
        started_at = NULL,
        finished_at = NULL,
        last_error = CASE
            WHEN last_error IS NULL OR last_error = '' THEN %s
            ELSE left(last_error || ' | ' || %s, 4000)
        END,
        updated_at = now()
    WHERE {where_sql}
    """
    with connect(research_service) as conn:
        before = fetch_all(
            conn,
            f"""
            SELECT count(*) AS count
            FROM market.minute_bar_backfill_job
            WHERE {where_sql}
            """,
            params,
        )[0]["count"]
        execute(conn, sql, [note, note, *params])
    return int(before or 0)


def shutdown_backfill_worker() -> None:
    global _WORKER_BAOSTOCK_READY
    if not _WORKER_BAOSTOCK_READY:
        return
    try:
        bs.logout()
    except Exception:
        pass
    _WORKER_BAOSTOCK_READY = False


def initialize_backfill_worker() -> None:
    global _WORKER_BAOSTOCK_READY
    if _WORKER_BAOSTOCK_READY:
        return
    login_or_raise()
    atexit.register(shutdown_backfill_worker)
    _WORKER_BAOSTOCK_READY = True


class _baostock_job_timeout:
    def __init__(self, timeout_seconds: float | None):
        self.timeout_seconds = timeout_seconds
        self.previous_handler = None
        self.previous_timer = None

    def __enter__(self):
        if self.timeout_seconds is None:
            return self
        if threading.current_thread() is not threading.main_thread():
            return self
        self.previous_handler = signal.getsignal(signal.SIGALRM)
        self.previous_timer = signal.setitimer(signal.ITIMER_REAL, 0)

        def _raise_timeout(_signum, _frame):
            raise BackfillJobTimeoutError(
                f"baostock minute job timed out after {self.timeout_seconds:g} seconds"
            )

        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, float(self.timeout_seconds))
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.timeout_seconds is None:
            return False
        if threading.current_thread() is not threading.main_thread():
            return False
        signal.setitimer(signal.ITIMER_REAL, 0)
        if self.previous_handler is not None:
            signal.signal(signal.SIGALRM, self.previous_handler)
        if self.previous_timer and self.previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, self.previous_timer[0], self.previous_timer[1])
        return False


def run_backfill_job_worker(
    job: dict[str, Any],
    sleep_seconds: float,
    request_timeout_seconds: float | None = BACKFILL_JOB_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    last_error = ""
    for attempt in range(1, BACKFILL_JOB_MAX_ATTEMPTS + 1):
        result = _run_backfill_job_worker_attempt_with_process(
            job,
            sleep_seconds=sleep_seconds,
            request_timeout_seconds=request_timeout_seconds,
        )
        if result["error"] is None:
            return result
        last_error = str(result["error"])
        if attempt < BACKFILL_JOB_MAX_ATTEMPTS:
            continue
    return {
        "job_id": job["job_id"],
        "row_count_market": 0,
        "row_count_staging": 0,
        "error": last_error,
    }


def _run_backfill_job_worker_attempt_with_process(
    job: dict[str, Any],
    *,
    sleep_seconds: float,
    request_timeout_seconds: float | None,
) -> dict[str, Any]:
    if request_timeout_seconds is None:
        return _run_backfill_job_worker_attempt(job, sleep_seconds, request_timeout_seconds)
    context = _backfill_job_process_context()
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_run_backfill_job_worker_attempt_target,
        args=(result_queue, job, sleep_seconds, request_timeout_seconds),
    )
    process.start()
    process.join(timeout=float(request_timeout_seconds))
    if process.is_alive():
        process.terminate()
        process.join(timeout=1)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=1)
        result_queue.close()
        return {
            "job_id": job["job_id"],
            "row_count_market": 0,
            "row_count_staging": 0,
            "error": (
                f"BackfillJobTimeoutError: baostock minute job timed out after "
                f"{request_timeout_seconds:g} seconds"
            ),
        }
    try:
        result = result_queue.get_nowait()
    except queue.Empty:
        result = {
            "job_id": job["job_id"],
            "row_count_market": 0,
            "row_count_staging": 0,
            "error": f"RuntimeError: baostock minute job exited with code {process.exitcode}",
        }
    finally:
        result_queue.close()
    return result


def _run_backfill_job_worker_attempt_target(
    result_queue: Any,
    job: dict[str, Any],
    sleep_seconds: float,
    request_timeout_seconds: float | None,
) -> None:
    result_queue.put(_run_backfill_job_worker_attempt(job, sleep_seconds, request_timeout_seconds))


def _run_backfill_job_worker_attempt(
    job: dict[str, Any],
    sleep_seconds: float,
    request_timeout_seconds: float | None,
) -> dict[str, Any]:
    try:
        initialize_backfill_worker()
        params = request_params(
            job["baostock_code"],
            job["start_date"],
            job["end_date"],
            job["freq"],
            job["adjust_type"],
        )
        with _baostock_job_timeout(request_timeout_seconds):
            rows = query_baostock_minute_rows(
                job["baostock_code"],
                job["start_date"],
                job["end_date"],
                freq=job["freq"],
                adjust_type=job["adjust_type"],
                timeout_seconds=request_timeout_seconds,
            )
        row_count = upsert_stock_minute_bars(
            rows,
            freq=job["freq"],
            adjust_type=job["adjust_type"],
            params=params,
        )
        if sleep_seconds:
            time.sleep(sleep_seconds)
        return {
            "job_id": job["job_id"],
            "row_count_market": row_count,
            "row_count_staging": row_count,
            "error": None,
        }
    except Exception as exc:
        return {
            "job_id": job["job_id"],
            "row_count_market": 0,
            "row_count_staging": 0,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    finally:
        shutdown_backfill_worker()


def _backfill_job_process_context() -> Any:
    for method in ("fork", "spawn"):
        try:
            return mp.get_context(method)
        except ValueError:
            continue
    return mp.get_context()


def run_baostock_minute_backfill(
    start_date: str | None = None,
    end_date: str | None = None,
    freq: str | None = None,
    adjust_types: list[str] | None = None,
    batch_by: str = "month",
    max_jobs: int = 50,
    retry_failed: bool = False,
    sleep_seconds: float = 0.5,
    workers: int = 1,
    reset_stale_before_run: bool = True,
    progress: Callable[[dict[str, Any]], None] | None = None,
    progress_interval: int = 100,
    progress_heartbeat_seconds: float = 60.0,
    derive_qfq_from_raw: bool | None = None,
) -> dict[str, int]:
    if batch_by != "month":
        raise ValueError("minute backfill v1 supports batch_by=month")
    if reset_stale_before_run:
        reset_stale_running_jobs()
    with connect(SETTINGS.research_service) as conn:
        jobs = claim_backfill_jobs(
            conn,
            max_jobs=max_jobs,
            retry_failed=retry_failed,
            start_date=parse_date(start_date) if start_date else None,
            end_date=parse_date(end_date) if end_date else None,
            freq=freq,
            adjust_types=adjust_types,
        )
    result = {"attempted": 0, "success": 0, "failed": 0, "rows": 0}
    should_derive_qfq = bool(
        derive_qfq_from_raw
        if derive_qfq_from_raw is not None
        else (adjust_types is not None and "qfq" in adjust_types)
    )
    if workers <= 0:
        raise ValueError("workers must be positive")
    total_jobs = len(jobs)
    interval = max(1, int(progress_interval or 1))

    def emit_progress(event: str, worker_result: dict[str, Any] | None = None) -> None:
        if progress is None:
            return
        payload: dict[str, Any] = {
            "event": event,
            "completed_jobs": int(result["attempted"]),
            "total_jobs": total_jobs,
            "success_jobs": int(result["success"]),
            "failed_jobs": int(result["failed"]),
            "rows": int(result["rows"]),
        }
        if worker_result:
            payload["last_job_id"] = worker_result.get("job_id")
            payload["last_error"] = worker_result.get("error")
        progress(payload)

    emit_progress("minute_backfill_started")
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    heartbeat_seconds = float(progress_heartbeat_seconds or 0)
    if progress is not None and heartbeat_seconds > 0 and total_jobs > 0:
        def heartbeat_loop() -> None:
            while not heartbeat_stop.wait(heartbeat_seconds):
                emit_progress("minute_backfill_heartbeat")

        heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        heartbeat_thread.start()

    try:
        if workers == 1:
            initialize_backfill_worker()
            try:
                for job in jobs:
                    worker_result = run_backfill_job_worker(job, sleep_seconds)
                    result["attempted"] += 1
                    if worker_result["error"] is None:
                        mark_job_success(
                            worker_result["job_id"],
                            worker_result["row_count_market"],
                            worker_result["row_count_staging"],
                        )
                        result["success"] += 1
                        result["rows"] += int(worker_result["row_count_market"])
                        qfq_rows, qfq_error = _derive_qfq_after_raw_success(
                            job,
                            should_derive_qfq=should_derive_qfq,
                        )
                        if qfq_error is None:
                            if qfq_rows is not None:
                                result["success"] += 1
                                result["rows"] += qfq_rows
                        else:
                            result["failed"] += 1
                    else:
                        mark_job_skipped(worker_result["job_id"], worker_result["error"])
                        result["failed"] += 1
                    if result["attempted"] % interval == 0:
                        emit_progress("minute_backfill_progress", worker_result)
            finally:
                shutdown_backfill_worker()
            emit_progress("minute_backfill_completed")
            return result

        with ProcessPoolExecutor(max_workers=workers, initializer=initialize_backfill_worker) as executor:
            futures = [
                executor.submit(run_backfill_job_worker, job, sleep_seconds)
                for job in jobs
            ]
            for future in as_completed(futures):
                result["attempted"] += 1
                worker_result = future.result()
                if worker_result["error"] is None:
                    mark_job_success(
                        worker_result["job_id"],
                        worker_result["row_count_market"],
                        worker_result["row_count_staging"],
                    )
                    result["success"] += 1
                    result["rows"] += int(worker_result["row_count_market"])
                    job = next((candidate for candidate in jobs if candidate["job_id"] == worker_result["job_id"]), None)
                    qfq_rows, qfq_error = _derive_qfq_after_raw_success(
                        job or {},
                        should_derive_qfq=should_derive_qfq,
                    )
                    if qfq_error is None:
                        if qfq_rows is not None:
                            result["success"] += 1
                            result["rows"] += qfq_rows
                    else:
                        result["failed"] += 1
                else:
                    mark_job_skipped(worker_result["job_id"], worker_result["error"])
                    result["failed"] += 1
                if result["attempted"] % interval == 0:
                    emit_progress("minute_backfill_progress", worker_result)
        emit_progress("minute_backfill_completed")
        return result
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1)


def _derive_qfq_after_raw_success(
    job: dict[str, Any],
    *,
    should_derive_qfq: bool,
) -> tuple[int | None, str | None]:
    if not should_derive_qfq or job.get("adjust_type") != "raw":
        return None, None
    try:
        with connect(SETTINGS.research_service) as conn:
            return derive_qfq_minute_bars_from_raw_job(conn, job), None
    except Exception as exc:
        return None, str(exc)


def benchmark_baostock_minute_backfill_workers(
    *,
    worker_counts: list[int],
    start_date: str | None = None,
    end_date: str | None = None,
    freq: str | None = None,
    adjust_types: list[str] | None = None,
    batch_by: str = "month",
    max_jobs: int = 50,
    retry_failed: bool = False,
    sleep_seconds: float = 0.5,
    reset_stale_before_run: bool = True,
) -> dict[str, Any]:
    if not worker_counts:
        raise ValueError("worker_counts must not be empty")
    rows: list[dict[str, Any]] = []
    for workers in worker_counts:
        if workers <= 0:
            raise ValueError("worker_counts must be positive")
        started_at = time.monotonic()
        result = run_baostock_minute_backfill(
            start_date=start_date,
            end_date=end_date,
            freq=freq,
            adjust_types=adjust_types,
            batch_by=batch_by,
            max_jobs=max_jobs,
            retry_failed=retry_failed,
            sleep_seconds=sleep_seconds,
            workers=workers,
            reset_stale_before_run=reset_stale_before_run,
        )
        elapsed_seconds = round(time.monotonic() - started_at, 6)
        attempted = int(result["attempted"])
        row_count = int(result["rows"])
        rows.append(
            {
                "workers": workers,
                "attempted": attempted,
                "success": int(result["success"]),
                "failed": int(result["failed"]),
                "rows": row_count,
                "elapsed_seconds": elapsed_seconds,
                "jobs_per_second": round(attempted / elapsed_seconds, 6) if elapsed_seconds else 0.0,
                "rows_per_second": round(row_count / elapsed_seconds, 6) if elapsed_seconds else 0.0,
                "failed_rate": round(int(result["failed"]) / attempted, 6) if attempted else 0.0,
            }
        )
    best = max(rows, key=lambda row: row["rows_per_second"]) if rows else None
    return {
        "summary": {
            "worker_counts": worker_counts,
            "best_workers_by_rows_per_second": best["workers"] if best else None,
            "total_attempted": sum(int(row["attempted"]) for row in rows),
            "total_failed": sum(int(row["failed"]) for row in rows),
        },
        "rows": rows,
    }


def load_backfill_status_rows(
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    freq: str | None = None,
    adjust_types: list[str] | None = None,
    research_service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if start_date:
        filters.append("end_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("start_date <= %s")
        params.append(end_date)
    if freq:
        filters.append("freq = %s")
        params.append(freq)
    if adjust_types:
        filters.append("adjust_type = ANY(%s)")
        params.append(adjust_types)
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    sql = f"""
    SELECT *
    FROM market.minute_bar_backfill_job
    {where_sql}
    ORDER BY start_date, ts_code, adjust_type
    """
    with connect(research_service) as conn:
        return fetch_all(conn, sql, params)


def summarize_backfill_status(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "total_jobs": len(rows),
        "pending_jobs": 0,
        "running_jobs": 0,
        "success_jobs": 0,
        "failed_jobs": 0,
        "skipped_jobs": 0,
        "total_market_rows": 0,
        "total_staging_rows": 0,
        "latest_success_at": None,
        "latest_failed_at": None,
        "failed_examples": [],
    }
    for row in rows:
        status = row["status"]
        summary[f"{status}_jobs"] += 1
        summary["total_market_rows"] += int(row.get("row_count_market") or 0)
        summary["total_staging_rows"] += int(row.get("row_count_staging") or 0)
        if status == "success" and row.get("finished_at"):
            summary["latest_success_at"] = max_optional(summary["latest_success_at"], row["finished_at"])
        if status == "failed":
            if row.get("finished_at"):
                summary["latest_failed_at"] = max_optional(summary["latest_failed_at"], row["finished_at"])
            if len(summary["failed_examples"]) < 5:
                summary["failed_examples"].append(
                    {
                        "job_id": row.get("job_id"),
                        "ts_code": row.get("ts_code"),
                        "period": f"{row.get('start_date')}:{row.get('end_date')}",
                        "error": row.get("last_error"),
                    }
                )
    return summary


def summarize_status_by_adjust_year_month(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for row in rows:
        start = parse_date(row["start_date"])
        key = (row["adjust_type"], start.year, start.month, row["status"])
        grouped.setdefault(
            key,
            {
                "adjust_type": key[0],
                "year": key[1],
                "month": key[2],
                "status": key[3],
                "jobs": 0,
                "market_rows": 0,
                "staging_rows": 0,
            },
        )
        grouped[key]["jobs"] += 1
        grouped[key]["market_rows"] += int(row.get("row_count_market") or 0)
        grouped[key]["staging_rows"] += int(row.get("row_count_staging") or 0)
    return sorted(grouped.values(), key=lambda item: (item["year"], item["month"], item["adjust_type"], item["status"]))


def load_backfill_status(
    output_dir: str | Path = "outputs/research",
) -> dict[str, Any]:
    rows = load_backfill_status_rows()
    summary = summarize_backfill_status(rows)
    by_period = summarize_status_by_adjust_year_month(rows)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    write_csv(output_path / "minute_backfill_status_by_period.csv", by_period)
    return {"summary": summary, "by_period": by_period}


def max_optional(left, right):
    if left is None:
        return right
    return max(left, right)


def validate_minute_bar_rows(
    rows: list[dict[str, Any]],
    adjust_types: list[str],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    seen = set()
    counts: dict[tuple[Any, Any], dict[str, int]] = {}
    for row in rows:
        key = (
            row["asset_id"],
            row["trade_time"],
            row["freq"],
            row["adjust_type"],
            row["source"],
        )
        if key in seen:
            errors.append(error_row("duplicate_key", row))
        seen.add(key)
        if row.get("high") is not None and row.get("low") is not None and row["high"] < row["low"]:
            errors.append(error_row("high_less_than_low", row))
        if row.get("close") is None:
            errors.append(error_row("close_null", row))
        if (row.get("volume") is not None and row["volume"] < 0) or (
            row.get("amount") is not None and row["amount"] < 0
        ):
            errors.append(error_row("negative_volume_or_amount", row))
        trade_time = row["trade_time"]
        trade_date = row["trade_date"]
        if hasattr(trade_time, "date") and trade_time.date() != trade_date:
            errors.append(error_row("trade_date_mismatch", row))
        count_key = (row["asset_id"], trade_date)
        counts.setdefault(count_key, {adjust_type: 0 for adjust_type in adjust_types})
        if row["adjust_type"] in counts[count_key]:
            counts[count_key][row["adjust_type"]] += 1
    for (asset_id, trade_date), count_by_adjust in counts.items():
        if len(set(count_by_adjust.values())) > 1:
            errors.append(
                {
                    "error_type": "adjust_type_count_mismatch",
                    "asset_id": asset_id,
                    "trade_date": trade_date,
                    "details": dict(count_by_adjust),
                }
            )
    return errors


def error_row(error_type: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "error_type": error_type,
        "asset_id": row.get("asset_id"),
        "trade_time": row.get("trade_time"),
        "trade_date": row.get("trade_date"),
        "freq": row.get("freq"),
        "adjust_type": row.get("adjust_type"),
        "details": "",
    }


def validate_minute_bars(
    start_date: str,
    end_date: str,
    freq: str,
    adjust_types: list[str],
    output_dir: str | Path = "outputs/research",
    limit_rows: int | None = None,
) -> dict[str, Any]:
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date)
    params: list[Any] = [parsed_start, parsed_end, freq, adjust_types]
    limit_sql = ""
    if limit_rows is not None:
        limit_sql = "LIMIT %s"
        params.append(limit_rows)
    sql = f"""
    SELECT asset_id, trade_time, trade_date, freq, adjust_type, source,
           high, low, close, volume, amount
    FROM market.stock_minute_bar
    WHERE trade_date BETWEEN %s AND %s
      AND freq = %s
      AND adjust_type = ANY(%s)
    ORDER BY trade_date, asset_id, trade_time, adjust_type
    {limit_sql}
    """
    staging_sql = """
    SELECT adjust_type, count(*) AS row_count
    FROM staging.baostock_stock_minute_bar
    WHERE trade_date BETWEEN %s AND %s
      AND freq = %s
      AND adjust_type = ANY(%s)
    GROUP BY adjust_type
    ORDER BY adjust_type
    """
    market_count_sql = """
    SELECT adjust_type, count(*) AS row_count
    FROM market.stock_minute_bar
    WHERE trade_date BETWEEN %s AND %s
      AND freq = %s
      AND adjust_type = ANY(%s)
    GROUP BY adjust_type
    ORDER BY adjust_type
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, params)
        staging_counts = fetch_all(conn, staging_sql, [parsed_start, parsed_end, freq, adjust_types])
        market_counts = fetch_all(conn, market_count_sql, [parsed_start, parsed_end, freq, adjust_types])
    errors = validate_minute_bar_rows(rows, adjust_types=adjust_types)
    staging_by_adjust = {row["adjust_type"]: int(row["row_count"]) for row in staging_counts}
    market_by_adjust = {row["adjust_type"]: int(row["row_count"]) for row in market_counts}
    for adjust_type in adjust_types:
        if staging_by_adjust.get(adjust_type, 0) != market_by_adjust.get(adjust_type, 0):
            errors.append(
                {
                    "error_type": "staging_market_count_mismatch",
                    "asset_id": "",
                    "trade_time": "",
                    "trade_date": "",
                    "freq": freq,
                    "adjust_type": adjust_type,
                    "details": {
                        "market": market_by_adjust.get(adjust_type, 0),
                        "staging": staging_by_adjust.get(adjust_type, 0),
                    },
                }
            )
    summary = {
        "start_date": parsed_start,
        "end_date": parsed_end,
        "freq": freq,
        "adjust_types": ",".join(adjust_types),
        "market_rows": sum(market_by_adjust.values()),
        "staging_rows": sum(staging_by_adjust.values()),
        "error_count": len(errors),
    }
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    write_csv(output_path / "minute_bar_validation_summary.csv", [summary])
    write_csv(output_path / "minute_bar_validation_errors.csv", errors)
    return {"summary": summary, "errors": errors}


def run_baostock_minute_backfill_range(
    start_date: str,
    end_date: str,
    freq: str,
    adjust_types: list[str],
    *,
    batch_by: str = "month",
    max_jobs: int = 500,
    retry_failed: bool = True,
    sleep_seconds: float = 0.1,
    workers: int = 1,
    output_dir: str | Path = "outputs/research",
    limit_assets: int | None = None,
    report: Any | None = None,
) -> dict[str, Any]:
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date)
    totals = {"months": 0, "attempted": 0, "success": 0, "failed": 0, "rows": 0}
    for month_start, month_end in month_ranges(parsed_start, parsed_end):
        totals["months"] += 1
        plan_baostock_minute_backfill(
            start_date=month_start.isoformat(),
            end_date=month_end.isoformat(),
            freq=freq,
            adjust_types=adjust_types,
            batch_by=batch_by,
            output_dir=output_dir,
            limit_assets=limit_assets,
        )
        while True:
            month_rows = load_backfill_status_rows(
                start_date=month_start,
                end_date=month_end,
                freq=freq,
                adjust_types=adjust_types,
            )
            month_summary = summarize_backfill_status(month_rows)
            if month_summary["pending_jobs"] == 0 and month_summary["running_jobs"] == 0 and month_summary["failed_jobs"] == 0:
                break
            result = run_baostock_minute_backfill(
                start_date=month_start.isoformat(),
                end_date=month_end.isoformat(),
                freq=freq,
                adjust_types=adjust_types,
                batch_by=batch_by,
                max_jobs=max_jobs,
                retry_failed=retry_failed,
                sleep_seconds=sleep_seconds,
                workers=workers,
            )
            totals["attempted"] += int(result["attempted"])
            totals["success"] += int(result["success"])
            totals["failed"] += int(result["failed"])
            totals["rows"] += int(result["rows"])
            if int(result["attempted"]) == 0:
                break

        validation = validate_minute_bars(
            start_date=month_start.isoformat(),
            end_date=month_end.isoformat(),
            freq=freq,
            adjust_types=adjust_types,
            output_dir=output_dir,
        )
        month_rows = load_backfill_status_rows(
            start_date=month_start,
            end_date=month_end,
            freq=freq,
            adjust_types=adjust_types,
        )
        month_summary = summarize_backfill_status(month_rows)
        report_summary = {
            "month": month_start.strftime("%Y-%m"),
            "start_date": month_start.isoformat(),
            "end_date": month_end.isoformat(),
            "freq": freq,
            "adjust_types": ",".join(adjust_types),
            "job_summary": month_summary,
            "validation_summary": validation["summary"],
        }
        if report:
            report(report_summary)
    return totals


def database_size_snapshot() -> dict[str, Any]:
    sql = """
    SELECT
        pg_database_size(current_database()) AS database_bytes,
        pg_total_relation_size('market.stock_minute_bar') AS market_stock_minute_bar_bytes,
        pg_indexes_size('market.stock_minute_bar') AS market_stock_minute_bar_index_bytes,
        pg_total_relation_size('staging.baostock_stock_minute_bar') AS staging_stock_minute_bar_bytes
    """
    with connect(SETTINGS.research_service) as conn:
        return fetch_all(conn, sql)[0]


def write_controller_report(
    output_dir: str | Path = "outputs/research",
    small_sample: dict[str, Any] | None = None,
    medium_sample: dict[str, Any] | None = None,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    path = output_path / "minute_backfill_controller_report.md"
    small_sample = small_sample or {}
    medium_sample = medium_sample or {}
    text = f"""# A股分钟线 Backfill Controller v1 报告

## 1. 背景
已有统一分钟线表 `market.stock_minute_bar`。全市场 5 分钟 raw/qfq 近 3 年导入可能达到数亿行，不能直接无监控导入。

## 2. 表结构与分区设计
`market.stock_minute_bar` 使用 `trade_date` 按月 RANGE 分区，主键为 `(trade_date, asset_id, trade_time, freq, adjust_type, source)`。`staging.baostock_stock_minute_bar` 暂不分区，保留原始 Baostock payload。`factor.stock_intraday_features_daily` 与 `factor.industry_intraday_features_daily` 仅预留结构。

## 3. Backfill Job 设计
`market.minute_bar_backfill_job` 按股票、月份、freq、adjust_type、source 拆分任务。状态支持 pending、running、success、failed、skipped；执行器跳过 success，并可通过 `--retry-failed` 重试 failed。

## 4. CLI 使用说明
`stock-research plan-baostock-minute-backfill --start-date 2024-01-01 --end-date 2026-05-13 --freq 5min --adjust-types raw,qfq --batch-by month`

`stock-research run-baostock-minute-backfill --max-jobs 50 --retry-failed --sleep-seconds 0.5`

`stock-research baostock-minute-backfill-status`

`stock-research validate-minute-bars --start-date 2024-01-01 --end-date 2026-05-13 --freq 5min --adjust-types raw,qfq`

## 5. 小样本验证结果
试运行命令：

`stock-research plan-baostock-minute-backfill --start-date 2024-01-02 --end-date 2024-01-08 --freq 5min --adjust-types raw,qfq --batch-by month --limit-assets 10 --output-dir outputs/research`

`stock-research run-baostock-minute-backfill --start-date 2024-01-02 --end-date 2024-01-08 --freq 5min --adjust-types raw,qfq --batch-by month --max-jobs 20 --retry-failed --sleep-seconds 0.2`

`stock-research validate-minute-bars --start-date 2024-01-02 --end-date 2024-01-08 --freq 5min --adjust-types raw,qfq --output-dir outputs/research`

耗时：{small_sample.get('elapsed_seconds', '未运行')}

写入行数：{small_sample.get('rows', '未运行')}

平均每 job 耗时：{small_sample.get('avg_job_seconds', '未运行')}

失败率：{small_sample.get('failure_rate', '未运行')}

数据库大小变化：{small_sample.get('database_size_change', '未记录')}

索引大小变化：{small_sample.get('index_size_change', '未记录')}

重复写入：{small_sample.get('duplicate_check', '未记录')}

validation：{small_sample.get('validation', '未运行')}

## 6. 中样本验证建议
本轮已实际运行 100 只股票、2024-01-01 到 2024-01-31、5min、raw/qfq。

`stock-research plan-baostock-minute-backfill --start-date 2024-01-01 --end-date 2024-01-31 --freq 5min --adjust-types raw,qfq --batch-by month --limit-assets 100 --output-dir outputs/research`

`stock-research run-baostock-minute-backfill --start-date 2024-01-01 --end-date 2024-01-31 --freq 5min --adjust-types raw,qfq --batch-by month --max-jobs 200 --retry-failed --sleep-seconds 0.5`

`stock-research baostock-minute-backfill-status --output-dir outputs/research`

`stock-research validate-minute-bars --start-date 2024-01-01 --end-date 2024-01-31 --freq 5min --adjust-types raw,qfq --output-dir outputs/research`

耗时：{medium_sample.get('elapsed_seconds', '未运行')}

写入行数：{medium_sample.get('rows', '未运行')}

平均每 job 耗时：{medium_sample.get('avg_job_seconds', '未运行')}

失败率：{medium_sample.get('failure_rate', '未运行')}

数据库大小变化：{medium_sample.get('database_size_change', '未记录')}

索引大小变化：{medium_sample.get('index_size_change', '未记录')}

重复写入：{medium_sample.get('duplicate_check', '未记录')}

validation：{medium_sample.get('validation', '未运行')}

## 7. 全市场导入建议
建议按月分批执行，先 plan 全市场任务，再每天或每轮执行有限 `--max-jobs`。不建议一次性跑完 2024-01-01 到 2026-05-13 的全部 raw/qfq。

大样本预演建议先跑全市场 1 个交易月：

`stock-research plan-baostock-minute-backfill --start-date 2024-01-01 --end-date 2024-01-31 --freq 5min --adjust-types raw,qfq --batch-by month --output-dir outputs/research`

`stock-research run-baostock-minute-backfill --start-date 2024-01-01 --end-date 2024-01-31 --freq 5min --adjust-types raw,qfq --batch-by month --max-jobs 100 --retry-failed --sleep-seconds 0.5`

通过全市场 1 个月 validation 后，再把日期范围扩大到 2024-01-01 到 2026-05-13，并保持按 `--max-jobs` 分轮执行。

## 8. 风险与注意事项
主要风险是磁盘和索引膨胀、Baostock 限速、网络中断、停牌导致 48 根不足、以及失败任务重复堆积。建议每轮导入后查看 status、数据库大小和 validation 输出。
"""
    path.write_text(text, encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
