from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def summarize_operational_health(
    *,
    trade_date: str,
    ingest_datasets: list[str] | None = None,
    backfill_run_ids: list[str] | None = None,
    stale_minutes: int = 60,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    if stale_minutes <= 0:
        raise ValueError("stale_minutes must be positive")

    datasets = ingest_datasets or []
    run_ids = backfill_run_ids or []
    with connect(service) as conn:
        ingest = _load_ingest_status(conn, datasets)
        stale_ingest = _load_stale_ingest_counts(conn, datasets, stale_minutes)
        backfill = _load_backfill_status(conn, run_ids)
        stale_backfill = _load_stale_backfill_counts(conn, run_ids, stale_minutes)
        daily_jobs = _load_failed_daily_jobs(conn, trade_date)

    alert_count = 0
    alert_count += sum(counts.get("failed", 0) for counts in ingest.values())
    alert_count += sum(stale_ingest.values())
    alert_count += sum(counts.get("failed", 0) for counts in backfill.values())
    alert_count += sum(stale_backfill.values())
    alert_count += len(daily_jobs)
    return {
        "trade_date": trade_date,
        "status": "alert" if alert_count else "ok",
        "alert_count": alert_count,
        "ingest": ingest,
        "stale_ingest": stale_ingest,
        "backfill": backfill,
        "stale_backfill": stale_backfill,
        "daily_jobs": daily_jobs,
    }


def format_operational_health_lines(result: dict[str, Any]) -> list[str]:
    lines = [
        f"daily_health|status|{result['status']}|alerts|{int(result['alert_count'])}"
    ]
    for dataset, counts in sorted(result.get("ingest", {}).items()):
        for status, count in sorted(counts.items()):
            if int(count) > 0:
                lines.append(f"daily_health_ingest|{dataset}|{status}|{int(count)}")
    for dataset, count in sorted(result.get("stale_ingest", {}).items()):
        if int(count) > 0:
            lines.append(f"daily_health_stale_ingest|{dataset}|running|{int(count)}")
    for run_id, counts in sorted(result.get("backfill", {}).items()):
        for status, count in sorted(counts.items()):
            if int(count) > 0:
                lines.append(f"daily_health_backfill|{run_id}|{status}|{int(count)}")
    for run_id, count in sorted(result.get("stale_backfill", {}).items()):
        if int(count) > 0:
            lines.append(f"daily_health_stale_backfill|{run_id}|running|{int(count)}")
    for job in result.get("daily_jobs", []):
        lines.append(
            "daily_health_job|"
            f"{job['step']}|{job['status']}|{job.get('error_message') or ''}"
        )
    return lines


def _load_ingest_status(conn, datasets: list[str]) -> dict[str, dict[str, int]]:
    if not datasets:
        return {}
    sql = """
    SELECT dataset, status, count(*) AS count
    FROM ingest.batch_job
    WHERE dataset = ANY(%s)
    GROUP BY dataset, status
    ORDER BY dataset, status
    """
    return _nested_counts(fetch_all(conn, sql, [datasets]), "dataset")


def _load_stale_ingest_counts(
    conn,
    datasets: list[str],
    stale_minutes: int,
) -> dict[str, int]:
    if not datasets:
        return {}
    sql = """
    SELECT dataset, count(*) AS count
    FROM ingest.batch_job
    WHERE dataset = ANY(%s)
      AND status = 'running'
      AND started_at < now() - (%s::text || ' minutes')::interval
    GROUP BY dataset
    ORDER BY dataset
    """
    return {
        str(row["dataset"]): int(row["count"])
        for row in fetch_all(conn, sql, [datasets, stale_minutes])
    }


def _load_backfill_status(conn, run_ids: list[str]) -> dict[str, dict[str, int]]:
    if not run_ids:
        return {}
    sql = """
    SELECT run_id, status, count(*) AS count
    FROM ingest.backfill_task
    WHERE run_id = ANY(%s)
    GROUP BY run_id, status
    ORDER BY run_id, status
    """
    return _nested_counts(fetch_all(conn, sql, [run_ids]), "run_id")


def _load_stale_backfill_counts(
    conn,
    run_ids: list[str],
    stale_minutes: int,
) -> dict[str, int]:
    if not run_ids:
        return {}
    sql = """
    SELECT run_id, count(*) AS count
    FROM ingest.backfill_task
    WHERE run_id = ANY(%s)
      AND status = 'running'
      AND started_at < now() - (%s::text || ' minutes')::interval
    GROUP BY run_id
    ORDER BY run_id
    """
    return {
        str(row["run_id"]): int(row["count"])
        for row in fetch_all(conn, sql, [run_ids, stale_minutes])
    }


def _load_failed_daily_jobs(conn, trade_date: str) -> list[dict[str, Any]]:
    if not _table_exists(conn, "ops.daily_job_run"):
        return []
    sql = """
    SELECT step, status, error_message
    FROM ops.daily_job_run
    WHERE trade_date = %s
      AND status = 'failed'
    ORDER BY updated_at DESC, step
    """
    return fetch_all(conn, sql, [trade_date])


def _table_exists(conn, table_name: str) -> bool:
    rows = fetch_all(conn, f"SELECT to_regclass('{table_name}') AS table_name")
    return bool(rows and rows[0].get("table_name"))


def _nested_counts(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        group = str(row[key])
        result.setdefault(group, {})[str(row["status"])] = int(row["count"])
    return result
