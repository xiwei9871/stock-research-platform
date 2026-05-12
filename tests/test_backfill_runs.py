from stock_research import backfill_runs


class FakeConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []
        self.many = []


def fake_fetch_all(conn, sql, params=None):
    conn.executed.append((sql, params))
    return conn.rows


def fake_execute(conn, sql, params=None):
    conn.executed.append((sql, params))


def fake_execute_many(conn, sql, rows):
    conn.many.append((sql, list(rows)))


def test_build_date_partitions_returns_inclusive_monthly_partitions():
    partitions = backfill_runs.build_date_partitions(
        "2024-01-01",
        "2024-03-31",
        months_per_partition=1,
    )

    assert partitions == [
        {"partition_key": "2024-01", "start_date": "2024-01-01", "end_date": "2024-01-31"},
        {"partition_key": "2024-02", "start_date": "2024-02-01", "end_date": "2024-02-29"},
        {"partition_key": "2024-03", "start_date": "2024-03-01", "end_date": "2024-03-31"},
    ]


def test_create_backfill_run_upserts_run_and_tasks(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(backfill_runs, "execute", fake_execute)
    monkeypatch.setattr(backfill_runs, "execute_many", fake_execute_many)

    result = backfill_runs.create_backfill_run(
        conn,
        run_id="run-1",
        dataset="daily-bars",
        source="baostock",
        source_version="v1",
        start_date="2024-01-01",
        end_date="2024-02-29",
        partitions=[
            {"partition_key": "2024-01", "start_date": "2024-01-01", "end_date": "2024-01-31"},
            {"partition_key": "2024-02", "start_date": "2024-02-01", "end_date": "2024-02-29"},
        ],
    )

    assert result == {"run_id": "run-1", "dataset": "daily-bars", "task_count": 2}
    assert "INSERT INTO ingest.backfill_run" in conn.executed[0][0]
    sql, rows = conn.many[0]
    assert "INSERT INTO ingest.backfill_task" in sql
    assert rows[0][0] == "run-1:2024-01"
    assert rows[0][1] == "run-1"


def test_backfill_status_returns_counts(monkeypatch):
    conn = FakeConnection(
        rows=[
            {"status": "pending", "count": 2},
            {"status": "success", "count": 1},
        ]
    )
    monkeypatch.setattr(backfill_runs, "fetch_all", fake_fetch_all)

    result = backfill_runs.backfill_status(conn, run_id="run-1")

    assert result == {"run_id": "run-1", "counts": {"pending": 2, "success": 1}}
    sql, params = conn.executed[0]
    assert "FROM ingest.backfill_task" in sql
    assert params == ["run-1"]


def test_claim_backfill_tasks_marks_tasks_running(monkeypatch):
    conn = FakeConnection(
        rows=[
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "dataset": "daily-bars",
                "partition_key": "2024-01",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            }
        ]
    )
    monkeypatch.setattr(backfill_runs, "fetch_all", fake_fetch_all)

    rows = backfill_runs.claim_backfill_tasks(conn, run_id="run-1", limit=2)

    assert rows == conn.rows
    sql, params = conn.executed[0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "attempts = attempts + 1" in sql
    assert params == ["run-1", 2]


def test_mark_backfill_task_success_updates_counts(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(backfill_runs, "execute", fake_execute)

    backfill_runs.mark_backfill_task_success(
        conn,
        task_id="task-1",
        rows_read=10,
        rows_written=9,
    )

    sql, params = conn.executed[0]
    assert "status = 'success'" in sql
    assert params == [10, 9, "task-1"]


def test_mark_backfill_task_failed_updates_error(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(backfill_runs, "execute", fake_execute)

    backfill_runs.mark_backfill_task_failed(conn, task_id="task-1", error_message="boom")

    sql, params = conn.executed[0]
    assert "status = 'failed'" in sql
    assert params == ["boom", "task-1"]


def test_reset_stale_backfill_tasks_returns_count(monkeypatch):
    conn = FakeConnection(rows=[{"task_id": "task-1"}, {"task_id": "task-2"}])
    monkeypatch.setattr(backfill_runs, "fetch_all", fake_fetch_all)

    count = backfill_runs.reset_stale_backfill_tasks(
        conn,
        dataset="daily-bars",
        older_than_minutes=60,
    )

    assert count == 2
    sql, params = conn.executed[0]
    assert "status = 'running'" in sql
    assert "RETURNING task_id" in sql
    assert params == ["daily-bars", 60]
