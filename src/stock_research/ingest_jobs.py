import json
import time
from collections.abc import Callable
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, execute, execute_many, fetch_all
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


def count_finance_assets(conn) -> int:
    sql = """
    SELECT count(*) AS count
    FROM core.asset_master
    WHERE baostock_code IS NOT NULL
      AND exchange IN ('SH', 'SZ')
    """
    rows = fetch_all(conn, sql)
    return int(rows[0]["count"])


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


def create_ingest_jobs_for_service(
    dataset: str,
    *,
    start_year: int,
    end_year: int,
    batch_size: int,
    service: str = SETTINGS.research_service,
) -> int:
    if dataset != "baostock-finance":
        raise ValueError(f"Unsupported dataset: {dataset}")
    with connect(service) as conn:
        return create_baostock_finance_jobs(
            conn,
            start_year=start_year,
            end_year=end_year,
            batch_size=batch_size,
        )


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
    if dataset != "baostock-finance":
        raise ValueError(f"Unsupported dataset: {dataset}")

    jobs = fetch_runnable_jobs(conn, dataset, limit_jobs)
    result = {"attempted": 0, "success": 0, "failed": 0}
    total = len(jobs)
    for index, job in enumerate(jobs, start=1):
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
        mark_job_running(conn, job["job_id"])
        _commit_job_state(conn)
        try:
            counts = sync_finance_for_period(
                int(job["year"]),
                int(job["quarter"]),
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
        rows_written = (
            int(counts.get("indicator_quarter", 0))
            + int(counts.get("income_statement", 0))
            + int(counts.get("share_capital_event", 0))
        )
        mark_job_success(
            conn,
            job["job_id"],
            rows_read=rows_read,
            rows_written=rows_written,
        )
        _commit_job_state(conn)
        result["success"] += 1
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
    sleep: Callable[[int], None] = time.sleep,
) -> dict[str, int | bool]:
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

        counts = status_counts(ingest_status(conn, dataset))
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
            "recent_jobs": recent_ingest_jobs(conn, dataset),
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
    service: str = SETTINGS.research_service,
) -> dict[str, int | bool]:
    with connect(service) as conn:
        return run_ingest_loop(
            conn,
            dataset,
            jobs_per_round=jobs_per_round,
            report=report,
            progress=progress,
            sleep_seconds=sleep_seconds,
            max_rounds=max_rounds,
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
