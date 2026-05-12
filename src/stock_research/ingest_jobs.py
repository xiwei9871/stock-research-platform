import json
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from math import ceil
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, execute, execute_many, fetch_all
from stock_research.loaders.akshare_finance_statements import sync_finance_statements_for_assets
from stock_research.loaders.baostock_finance_ingestion import sync_finance_for_period


def baostock_finance_job_id(
    year: int,
    quarter: int,
    offset: int,
    limit: int,
) -> str:
    return f"baostock-finance:{year}Q{quarter}:offset{offset}:limit{limit}"


def build_baostock_finance_jobs(
    *,
    start_year: int,
    end_year: int,
    asset_count: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    jobs = []
    for year in range(start_year, end_year + 1):
        for quarter in range(1, 5):
            for offset in range(0, asset_count, batch_size):
                jobs.append(
                    {
                        "job_id": baostock_finance_job_id(
                            year,
                            quarter,
                            offset,
                            batch_size,
                        ),
                        "dataset": "baostock-finance",
                        "source": "baostock",
                        "year": year,
                        "quarter": quarter,
                        "offset_value": offset,
                        "limit_value": batch_size,
                        "params": {
                            "year": year,
                            "quarter": quarter,
                            "offset": offset,
                            "limit": batch_size,
                        },
                    }
                )
    return jobs


def akshare_finance_statement_job_id(offset: int, limit: int) -> str:
    return f"akshare-finance-statements:offset{offset}:limit{limit}"


def build_akshare_finance_statement_jobs(
    *,
    asset_count: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    jobs = []
    for offset in range(0, asset_count, batch_size):
        jobs.append(
            {
                "job_id": akshare_finance_statement_job_id(offset, batch_size),
                "dataset": "akshare-finance-statements",
                "source": "akshare_em",
                "year": None,
                "quarter": None,
                "offset_value": offset,
                "limit_value": batch_size,
                "params": {"offset": offset, "limit": batch_size},
            }
        )
    return jobs


def count_finance_assets(conn) -> int:
    sql = """
    SELECT count(*) AS count
    FROM core.asset_master
    WHERE baostock_code IS NOT NULL
      AND exchange IN ('SH', 'SZ')
    """
    rows = fetch_all(conn, sql)
    return int(rows[0]["count"])


def count_akshare_finance_statement_assets(conn) -> int:
    sql = """
    SELECT count(*) AS count
    FROM core.asset_master
    WHERE akshare_code IS NOT NULL
      AND exchange IN ('SH', 'SZ')
    """
    rows = fetch_all(conn, sql)
    return int(rows[0]["count"])


def _upsert_batch_jobs(conn, jobs: list[dict[str, Any]]) -> int:
    if not jobs:
        return 0
    sql = """
    INSERT INTO ingest.batch_job (
        job_id,
        dataset,
        source,
        year,
        quarter,
        offset_value,
        limit_value,
        status,
        params
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s::jsonb)
    ON CONFLICT (job_id) DO UPDATE SET
        params = EXCLUDED.params,
        updated_at = now()
    WHERE ingest.batch_job.status <> 'success'
    """
    execute_many(
        conn,
        sql,
        [
            (
                job["job_id"],
                job["dataset"],
                job["source"],
                job["year"],
                job["quarter"],
                job["offset_value"],
                job["limit_value"],
                json.dumps(job["params"], ensure_ascii=False),
            )
            for job in jobs
        ],
    )
    return len(jobs)


def create_baostock_finance_jobs(
    conn,
    *,
    start_year: int,
    end_year: int,
    batch_size: int,
) -> int:
    jobs = build_baostock_finance_jobs(
        start_year=start_year,
        end_year=end_year,
        asset_count=count_finance_assets(conn),
        batch_size=batch_size,
    )
    return _upsert_batch_jobs(conn, jobs)


def create_akshare_finance_statement_jobs(
    conn,
    *,
    batch_size: int,
) -> int:
    jobs = build_akshare_finance_statement_jobs(
        asset_count=count_akshare_finance_statement_assets(conn),
        batch_size=batch_size,
    )
    return _upsert_batch_jobs(conn, jobs)


def create_ingest_jobs_for_service(
    dataset: str,
    *,
    start_year: int,
    end_year: int,
    batch_size: int,
    service: str = SETTINGS.research_service,
) -> int:
    with connect(service) as conn:
        if dataset == "baostock-finance":
            return create_baostock_finance_jobs(
                conn,
                start_year=start_year,
                end_year=end_year,
                batch_size=batch_size,
            )
        if dataset == "akshare-finance-statements":
            return create_akshare_finance_statement_jobs(conn, batch_size=batch_size)
        raise ValueError(f"Unsupported dataset: {dataset}")


def fetch_runnable_jobs(conn, dataset: str, limit_jobs: int) -> list[dict[str, Any]]:
    sql = """
    SELECT *
    FROM ingest.batch_job
    WHERE dataset = %s
      AND status IN ('pending', 'failed')
    ORDER BY year, quarter, offset_value
    LIMIT %s
    """
    return fetch_all(conn, sql, [dataset, limit_jobs])


def claim_runnable_jobs(conn, dataset: str, limit_jobs: int) -> list[dict[str, Any]]:
    sql = """
    WITH picked AS (
        SELECT job_id
        FROM ingest.batch_job
        WHERE dataset = %s
          AND status IN ('pending', 'failed')
        ORDER BY year, quarter, offset_value
        FOR UPDATE SKIP LOCKED
        LIMIT %s
    )
    UPDATE ingest.batch_job AS job
    SET status = 'running',
        error_message = NULL,
        started_at = now(),
        finished_at = NULL,
        updated_at = now()
    FROM picked
    WHERE job.job_id = picked.job_id
    RETURNING job.*
    """
    rows = fetch_all(conn, sql, [dataset, limit_jobs])
    for row in rows:
        _record_event(conn, row["job_id"], "running")
    return rows


def reset_stale_ingest_jobs(
    conn,
    *,
    dataset: str,
    older_than_minutes: int,
) -> int:
    if older_than_minutes <= 0:
        raise ValueError("older_than_minutes must be positive")

    sql = """
    UPDATE ingest.batch_job
    SET status = 'pending',
        error_message = 'reset stale running job',
        finished_at = now(),
        updated_at = now()
    WHERE dataset = %s
      AND status = 'running'
      AND started_at < now() - (%s::text || ' minutes')::interval
    RETURNING job_id
    """
    rows = fetch_all(conn, sql, [dataset, older_than_minutes])
    return len(rows)


def reset_stale_ingest_jobs_for_service(
    dataset: str,
    *,
    older_than_minutes: int,
    service: str = SETTINGS.research_service,
) -> int:
    with connect(service) as conn:
        return reset_stale_ingest_jobs(
            conn,
            dataset=dataset,
            older_than_minutes=older_than_minutes,
        )


def _record_event(conn, job_id: str, status: str, message: str | None = None) -> None:
    sql = """
    INSERT INTO ingest.batch_event (job_id, status, message)
    VALUES (%s, %s, %s)
    """
    execute(conn, sql, [job_id, status, message])


def mark_job_running(conn, job_id: str) -> None:
    sql = """
    UPDATE ingest.batch_job
    SET status = 'running',
        error_message = NULL,
        started_at = now(),
        finished_at = NULL,
        updated_at = now()
    WHERE job_id = %s
    """
    execute(conn, sql, [job_id])
    _record_event(conn, job_id, "running")


def mark_job_success(
    conn,
    job_id: str,
    *,
    rows_read: int,
    rows_written: int,
) -> None:
    sql = """
    UPDATE ingest.batch_job
    SET status = 'success',
        rows_read = %s,
        rows_written = %s,
        error_message = NULL,
        finished_at = now(),
        updated_at = now()
    WHERE job_id = %s
    """
    execute(conn, sql, [rows_read, rows_written, job_id])
    _record_event(conn, job_id, "success")


def mark_job_failed(conn, job_id: str, error_message: str) -> None:
    sql = """
    UPDATE ingest.batch_job
    SET status = 'failed',
        error_message = %s,
        finished_at = now(),
        updated_at = now()
    WHERE job_id = %s
    """
    execute(conn, sql, [error_message, job_id])
    _record_event(conn, job_id, "failed", error_message)


ProgressCallback = Callable[[dict[str, Any]], None]


def _exception_message(exc: BaseException) -> str:
    return str(exc) or exc.__class__.__name__


def _commit_job_state(conn) -> None:
    conn.commit()


def run_ingest_jobs(
    conn,
    dataset: str,
    limit_jobs: int,
    progress: ProgressCallback | None = None,
) -> dict[str, int]:
    if dataset not in {"baostock-finance", "akshare-finance-statements"}:
        raise ValueError(f"Unsupported dataset: {dataset}")

    result = {"attempted": 0, "success": 0, "failed": 0, "rows_read": 0, "rows_written": 0}
    total = limit_jobs
    while result["attempted"] < limit_jobs:
        jobs = claim_runnable_jobs(conn, dataset, 1)
        if not jobs:
            break
        _commit_job_state(conn)
        job = jobs[0]
        index = result["attempted"] + 1
        result["attempted"] += 1
        if progress:
            progress(
                {
                    "event": "start",
                    "index": index,
                    "total": total,
                    "job_id": job["job_id"],
                    "success": result["success"],
                    "failed": result["failed"],
                }
            )
        try:
            if dataset == "baostock-finance":
                counts = sync_finance_for_period(
                    int(job["year"]),
                    int(job["quarter"]),
                    limit=int(job["limit_value"]),
                    offset=int(job["offset_value"]),
                )
            else:
                counts = sync_finance_statements_for_assets(
                    limit=int(job["limit_value"]),
                    offset=int(job["offset_value"]),
                )
        except Exception as exc:
            error_message = _exception_message(exc)
            mark_job_failed(conn, job["job_id"], error_message)
            _commit_job_state(conn)
            result["failed"] += 1
            if progress:
                progress(
                    {
                        "event": "failed",
                        "index": index,
                        "total": total,
                        "job_id": job["job_id"],
                        "success": result["success"],
                        "failed": result["failed"],
                        "error": error_message,
                    }
                )
            continue
        except BaseException as exc:
            error_message = _exception_message(exc)
            mark_job_failed(conn, job["job_id"], error_message)
            _commit_job_state(conn)
            result["failed"] += 1
            if progress:
                progress(
                    {
                        "event": "failed",
                        "index": index,
                        "total": total,
                        "job_id": job["job_id"],
                        "success": result["success"],
                        "failed": result["failed"],
                        "error": error_message,
                    }
                )
            raise

        rows_read = int(counts.get("queried_assets", 0))
        if dataset == "baostock-finance":
            rows_written = (
                int(counts.get("indicator_quarter", 0))
                + int(counts.get("income_statement", 0))
                + int(counts.get("share_capital_event", 0))
            )
        else:
            rows_written = int(counts.get("balance_sheet", 0)) + int(
                counts.get("cash_flow", 0)
            )
        mark_job_success(
            conn,
            job["job_id"],
            rows_read=rows_read,
            rows_written=rows_written,
        )
        _commit_job_state(conn)
        result["success"] += 1
        result["rows_read"] += rows_read
        result["rows_written"] += rows_written
        if progress:
            progress(
                {
                    "event": "success",
                    "index": index,
                    "total": total,
                    "job_id": job["job_id"],
                    "success": result["success"],
                    "failed": result["failed"],
                    "rows_read": rows_read,
                    "rows_written": rows_written,
                }
            )
    return result


def _split_limit(limit_jobs: int, workers: int) -> list[int]:
    if limit_jobs < 0:
        raise ValueError("limit_jobs must be >= 0")
    if workers < 1:
        raise ValueError("workers must be >= 1")
    if limit_jobs == 0:
        return []
    active_workers = min(workers, limit_jobs)
    per_worker = ceil(limit_jobs / active_workers)
    remaining = limit_jobs
    limits = []
    for _ in range(active_workers):
        item = min(per_worker, remaining)
        limits.append(item)
        remaining -= item
    return limits


def _empty_run_result() -> dict[str, int]:
    return {"attempted": 0, "success": 0, "failed": 0, "rows_read": 0, "rows_written": 0}


def _merge_run_results(results: list[dict[str, int]]) -> dict[str, int]:
    merged = _empty_run_result()
    for result in results:
        for key in merged:
            merged[key] += int(result.get(key, 0))
    return merged


def _run_ingest_jobs_worker(dataset: str, limit_jobs: int, service: str) -> dict[str, int]:
    return run_ingest_jobs_for_service(
        dataset,
        limit_jobs=limit_jobs,
        service=service,
    )


def run_ingest_jobs_parallel_for_service(
    dataset: str,
    *,
    limit_jobs: int,
    workers: int,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    if workers < 1:
        raise ValueError("workers must be >= 1")
    if workers == 1:
        return run_ingest_jobs_for_service(
            dataset,
            limit_jobs=limit_jobs,
            service=service,
        )

    limits = _split_limit(limit_jobs, workers)
    if not limits:
        return _empty_run_result()

    results = []
    with ProcessPoolExecutor(
        max_workers=len(limits),
        max_tasks_per_child=1,
    ) as executor:
        futures = [
            executor.submit(_run_ingest_jobs_worker, dataset, item, service)
            for item in limits
        ]
        for future in as_completed(futures):
            results.append(future.result())
    return _merge_run_results(results)


def status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {str(row["status"]): int(row["count"]) for row in rows}


def recent_ingest_jobs(
    conn,
    dataset: str,
    limit: int = 12,
) -> list[dict[str, Any]]:
    sql = """
    SELECT job_id, status, rows_read, rows_written, error_message
    FROM ingest.batch_job
    WHERE dataset = %s
    ORDER BY updated_at DESC
    LIMIT %s
    """
    return fetch_all(conn, sql, [dataset, limit])


def format_ingest_loop_report(summary: dict[str, Any]) -> str:
    counts = summary.get("status_counts", {})
    recent_jobs = summary.get("recent_jobs", [])
    if summary.get("done"):
        conclusion = "结论: 全部任务已完成，pending=0"
    elif int(summary.get("failed", 0)) > 0 or int(counts.get("failed", 0)) > 0:
        conclusion = "结论: 本轮完成，但存在失败批次，可继续重试"
    else:
        conclusion = "结论: 本轮完成，无遗漏，可继续下一轮"

    lines = [
        "A股财务数据补齐进度",
        "",
        f"数据集: {summary['dataset']}",
        f"第 {summary['round']} 轮",
        f"本轮尝试: {summary['attempted']}",
        f"本轮成功: {summary['success']}",
        f"本轮失败: {summary['failed']}",
        f"本轮读取资产: {summary['rows_read']}",
        f"本轮写入行数: {summary['rows_written']}",
        "",
        "总状态:",
        f"success: {int(counts.get('success', 0))}",
        f"pending: {int(counts.get('pending', 0))}",
        f"failed: {int(counts.get('failed', 0))}",
        f"running: {int(counts.get('running', 0))}",
        f"skipped: {int(counts.get('skipped', 0))}",
        "",
        "最近批次:",
    ]
    for job in recent_jobs[:5]:
        error = job.get("error_message") or ""
        suffix = f" error={error}" if error else ""
        lines.append(
            f"- {job['job_id']} | {job['status']} | "
            f"read={int(job.get('rows_read') or 0)} "
            f"written={int(job.get('rows_written') or 0)}{suffix}"
        )
    if not recent_jobs:
        lines.append("- 无")
    lines.extend(["", conclusion])
    return "\n".join(lines)


def run_ingest_loop(
    conn,
    dataset: str,
    *,
    jobs_per_round: int,
    report: Callable[[dict[str, Any]], None] | None = None,
    progress: ProgressCallback | None = None,
    sleep_seconds: int = 10,
    max_rounds: int | None = None,
    workers: int = 1,
    sleep: Callable[[int], None] = time.sleep,
    service: str = SETTINGS.research_service,
) -> dict[str, int | bool]:
    if workers < 1:
        raise ValueError("workers must be >= 1")
    totals: dict[str, int | bool] = {
        "rounds": 0,
        "attempted": 0,
        "success": 0,
        "failed": 0,
        "rows_read": 0,
        "rows_written": 0,
        "done": False,
    }
    while True:
        if max_rounds is not None and int(totals["rounds"]) >= max_rounds:
            break

        if workers > 1:
            result = run_ingest_jobs_parallel_for_service(
                dataset,
                limit_jobs=jobs_per_round,
                workers=workers,
                service=service,
            )
        else:
            result = run_ingest_jobs(
                conn,
                dataset,
                jobs_per_round,
                progress=progress,
            )
        if int(result.get("attempted", 0)) == 0:
            totals["done"] = True
            break

        totals["rounds"] = int(totals["rounds"]) + 1
        totals["attempted"] = int(totals["attempted"]) + int(result.get("attempted", 0))
        totals["success"] = int(totals["success"]) + int(result.get("success", 0))
        totals["failed"] = int(totals["failed"]) + int(result.get("failed", 0))
        totals["rows_read"] = int(totals["rows_read"]) + int(result.get("rows_read", 0))
        totals["rows_written"] = int(totals["rows_written"]) + int(
            result.get("rows_written", 0)
        )

        if workers > 1:
            with connect(service) as status_conn:
                counts = status_counts(ingest_status(status_conn, dataset))
                recent_jobs = recent_ingest_jobs(status_conn, dataset)
        else:
            counts = status_counts(ingest_status(conn, dataset))
            recent_jobs = recent_ingest_jobs(conn, dataset)
        done = int(counts.get("pending", 0)) == 0 and int(counts.get("running", 0)) == 0
        totals["done"] = done
        summary = {
            "dataset": dataset,
            "round": int(totals["rounds"]),
            "attempted": int(result.get("attempted", 0)),
            "success": int(result.get("success", 0)),
            "failed": int(result.get("failed", 0)),
            "rows_read": int(result.get("rows_read", 0)),
            "rows_written": int(result.get("rows_written", 0)),
            "status_counts": counts,
            "recent_jobs": recent_jobs,
            "done": done,
        }
        if report:
            report(summary)
        if done:
            break
        if sleep_seconds > 0:
            sleep(sleep_seconds)

    return totals


def run_ingest_jobs_for_service(
    dataset: str,
    *,
    limit_jobs: int,
    progress: ProgressCallback | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    with connect(service) as conn:
        return run_ingest_jobs(conn, dataset, limit_jobs, progress=progress)


def run_ingest_loop_for_service(
    dataset: str,
    *,
    jobs_per_round: int,
    report: Callable[[dict[str, Any]], None] | None = None,
    progress: ProgressCallback | None = None,
    sleep_seconds: int = 10,
    max_rounds: int | None = None,
    workers: int = 1,
    service: str = SETTINGS.research_service,
) -> dict[str, int | bool]:
    if workers > 1:
        return run_ingest_loop(
            None,
            dataset,
            jobs_per_round=jobs_per_round,
            report=report,
            progress=progress,
            sleep_seconds=sleep_seconds,
            max_rounds=max_rounds,
            workers=workers,
            service=service,
        )
    with connect(service) as conn:
        return run_ingest_loop(
            conn,
            dataset,
            jobs_per_round=jobs_per_round,
            report=report,
            progress=progress,
            sleep_seconds=sleep_seconds,
            max_rounds=max_rounds,
            workers=workers,
            service=service,
        )


def ingest_status(conn, dataset: str | None = None) -> list[dict[str, Any]]:
    filters = []
    params = []
    if dataset:
        filters.append("dataset = %s")
        params.append(dataset)
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    sql = f"""
    SELECT dataset, status, count(*) AS count
    FROM ingest.batch_job
    {where_sql}
    GROUP BY dataset, status
    ORDER BY dataset, status
    """
    return fetch_all(conn, sql, params)


def ingest_status_for_service(
    dataset: str | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    with connect(service) as conn:
        return ingest_status(conn, dataset)
