import json
from datetime import date
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute, execute_many, fetch_all


def build_date_partitions(
    start_date: str,
    end_date: str,
    *,
    months_per_partition: int = 1,
) -> list[dict[str, str]]:
    if months_per_partition <= 0:
        raise ValueError("months_per_partition must be positive")
    start = pd.Timestamp(start_date).date()
    end = pd.Timestamp(end_date).date()
    if end < start:
        raise ValueError("end_date must be >= start_date")

    partitions = []
    current = start.replace(day=1)
    while current <= end:
        period_start = max(current, start)
        next_month = (pd.Timestamp(current) + pd.DateOffset(months=months_per_partition)).date()
        period_end = min((pd.Timestamp(next_month) - pd.Timedelta(days=1)).date(), end)
        partition_key = (
            period_start.strftime("%Y-%m")
            if months_per_partition == 1
            else f"{period_start:%Y-%m}_{period_end:%Y-%m}"
        )
        partitions.append(
            {
                "partition_key": partition_key,
                "start_date": period_start.isoformat(),
                "end_date": period_end.isoformat(),
            }
        )
        current = next_month
    return partitions


def create_backfill_run(
    conn,
    *,
    run_id: str,
    dataset: str,
    source: str,
    source_version: str,
    start_date: str,
    end_date: str,
    partitions: list[dict[str, str]],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_sql = """
    INSERT INTO ingest.backfill_run (
        run_id, dataset, source, source_version, start_date, end_date, status, params
    )
    VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s::jsonb)
    ON CONFLICT (run_id) DO UPDATE SET
        dataset = EXCLUDED.dataset,
        source = EXCLUDED.source,
        source_version = EXCLUDED.source_version,
        start_date = EXCLUDED.start_date,
        end_date = EXCLUDED.end_date,
        params = EXCLUDED.params,
        updated_at = now()
    """
    execute(
        conn,
        run_sql,
        [
            run_id,
            dataset,
            source,
            source_version,
            start_date,
            end_date,
            json.dumps(params or {}, ensure_ascii=False),
        ],
    )
    task_sql = """
    INSERT INTO ingest.backfill_task (
        task_id, run_id, dataset, partition_key, start_date, end_date, status, params
    )
    VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s::jsonb)
    ON CONFLICT (run_id, partition_key) DO UPDATE SET
        start_date = EXCLUDED.start_date,
        end_date = EXCLUDED.end_date,
        params = EXCLUDED.params,
        updated_at = now()
    WHERE ingest.backfill_task.status <> 'success'
    """
    execute_many(
        conn,
        task_sql,
        [
            (
                f"{run_id}:{partition['partition_key']}",
                run_id,
                dataset,
                partition["partition_key"],
                partition["start_date"],
                partition["end_date"],
                json.dumps(partition.get("params") or {}, ensure_ascii=False),
            )
            for partition in partitions
        ],
    )
    return {"run_id": run_id, "dataset": dataset, "task_count": len(partitions)}


def create_backfill_run_for_service(
    *,
    run_id: str,
    dataset: str,
    source: str,
    source_version: str,
    start_date: str,
    end_date: str,
    months_per_partition: int = 1,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    partitions = build_date_partitions(
        start_date,
        end_date,
        months_per_partition=months_per_partition,
    )
    with connect(service) as conn:
        return create_backfill_run(
            conn,
            run_id=run_id,
            dataset=dataset,
            source=source,
            source_version=source_version,
            start_date=start_date,
            end_date=end_date,
            partitions=partitions,
            params={"months_per_partition": months_per_partition},
        )


def backfill_status(conn, *, run_id: str) -> dict[str, Any]:
    sql = """
    SELECT status, count(*) AS count
    FROM ingest.backfill_task
    WHERE run_id = %s
    GROUP BY status
    ORDER BY status
    """
    rows = fetch_all(conn, sql, [run_id])
    return {
        "run_id": run_id,
        "counts": {str(row["status"]): int(row["count"]) for row in rows},
    }


def backfill_status_for_service(
    *,
    run_id: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    with connect(service) as conn:
        return backfill_status(conn, run_id=run_id)


def claim_backfill_tasks(conn, *, run_id: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    sql = """
    WITH claimed AS (
        SELECT task_id
        FROM ingest.backfill_task
        WHERE run_id = %s
          AND status IN ('pending', 'failed')
        ORDER BY start_date, partition_key
        LIMIT %s
        FOR UPDATE SKIP LOCKED
    )
    UPDATE ingest.backfill_task task
    SET status = 'running',
        attempts = attempts + 1,
        error_message = NULL,
        started_at = now(),
        finished_at = NULL,
        updated_at = now()
    FROM claimed
    WHERE task.task_id = claimed.task_id
    RETURNING task.*
    """
    return fetch_all(conn, sql, [run_id, limit])


def claim_backfill_tasks_for_service(
    *,
    run_id: str,
    limit: int,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    with connect(service) as conn:
        return claim_backfill_tasks(conn, run_id=run_id, limit=limit)


def mark_backfill_task_success(
    conn,
    *,
    task_id: str,
    rows_read: int,
    rows_written: int,
) -> None:
    sql = """
    UPDATE ingest.backfill_task
    SET status = 'success',
        rows_read = %s,
        rows_written = %s,
        error_message = NULL,
        finished_at = now(),
        updated_at = now()
    WHERE task_id = %s
    """
    execute(conn, sql, [rows_read, rows_written, task_id])


def mark_backfill_task_success_for_service(
    *,
    task_id: str,
    rows_read: int,
    rows_written: int,
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        mark_backfill_task_success(
            conn,
            task_id=task_id,
            rows_read=rows_read,
            rows_written=rows_written,
        )


def mark_backfill_task_failed(conn, *, task_id: str, error_message: str) -> None:
    sql = """
    UPDATE ingest.backfill_task
    SET status = 'failed',
        error_message = %s,
        finished_at = now(),
        updated_at = now()
    WHERE task_id = %s
    """
    execute(conn, sql, [error_message, task_id])


def mark_backfill_task_failed_for_service(
    *,
    task_id: str,
    error_message: str,
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        mark_backfill_task_failed(conn, task_id=task_id, error_message=error_message)


def reset_stale_backfill_tasks(
    conn,
    *,
    dataset: str,
    older_than_minutes: int,
) -> int:
    if older_than_minutes <= 0:
        raise ValueError("older_than_minutes must be positive")
    sql = """
    UPDATE ingest.backfill_task
    SET status = 'pending',
        error_message = 'reset stale running task',
        finished_at = now(),
        updated_at = now()
    WHERE dataset = %s
      AND status = 'running'
      AND started_at < now() - (%s::text || ' minutes')::interval
    RETURNING task_id
    """
    rows = fetch_all(conn, sql, [dataset, older_than_minutes])
    return len(rows)


def reset_stale_backfill_tasks_for_service(
    *,
    dataset: str,
    older_than_minutes: int,
    service: str = SETTINGS.research_service,
) -> int:
    with connect(service) as conn:
        return reset_stale_backfill_tasks(
            conn,
            dataset=dataset,
            older_than_minutes=older_than_minutes,
        )


def _date_string(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]
