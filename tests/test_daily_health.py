from stock_research import daily_health


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def test_summarize_operational_health_flags_failed_and_stale_work(monkeypatch):
    def fake_fetch_all(conn, sql, params=None):
        if "FROM ingest.batch_job" in sql and "GROUP BY dataset, status" in sql:
            return [
                {"dataset": "baostock-finance", "status": "failed", "count": 2},
                {"dataset": "baostock-finance", "status": "running", "count": 1},
            ]
        if "FROM ingest.batch_job" in sql and "status = 'running'" in sql:
            return [{"dataset": "baostock-finance", "count": 1}]
        if "FROM ingest.backfill_task" in sql and "GROUP BY run_id, status" in sql:
            return [
                {"run_id": "bars-1", "status": "failed", "count": 3},
                {"run_id": "bars-1", "status": "success", "count": 10},
            ]
        if "FROM ingest.backfill_task" in sql and "status = 'running'" in sql:
            return [{"run_id": "bars-1", "count": 2}]
        if "to_regclass" in sql:
            return [{"table_name": "ops.daily_job_run"}]
        if "FROM ops.daily_job_run" in sql:
            return [
                {
                    "step": "load_market_bars",
                    "status": "failed",
                    "error_message": "source unavailable",
                }
            ]
        raise AssertionError(sql)

    monkeypatch.setattr(daily_health, "connect", lambda service: _Context(object()))
    monkeypatch.setattr(daily_health, "fetch_all", fake_fetch_all)

    result = daily_health.summarize_operational_health(
        trade_date="2026-05-12",
        ingest_datasets=["baostock-finance"],
        backfill_run_ids=["bars-1"],
        stale_minutes=60,
    )

    assert result["status"] == "alert"
    assert result["alert_count"] == 9
    assert result["ingest"]["baostock-finance"]["failed"] == 2
    assert result["stale_ingest"]["baostock-finance"] == 1
    assert result["backfill"]["bars-1"]["failed"] == 3
    assert result["stale_backfill"]["bars-1"] == 2
    assert result["daily_jobs"][0]["step"] == "load_market_bars"


def test_format_operational_health_lines_is_stable():
    lines = daily_health.format_operational_health_lines(
        {
            "trade_date": "2026-05-12",
            "status": "alert",
            "alert_count": 2,
            "ingest": {"baostock-finance": {"failed": 1}},
            "stale_ingest": {"baostock-finance": 1},
            "backfill": {},
            "stale_backfill": {},
            "daily_jobs": [
                {
                    "step": "load_market_bars",
                    "status": "failed",
                    "error_message": "source unavailable",
                }
            ],
        }
    )

    assert lines == [
        "daily_health|status|alert|alerts|2",
        "daily_health_ingest|baostock-finance|failed|1",
        "daily_health_stale_ingest|baostock-finance|running|1",
        "daily_health_job|load_market_bars|failed|source unavailable",
    ]
