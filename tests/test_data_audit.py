from stock_research import data_audit


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def test_format_audit_line_is_stable():
    line = data_audit.format_audit_line(
        {
            "dataset": "market_daily_bar",
            "rows": 10,
            "date_count": 2,
            "min_date": "2024-01-01",
            "max_date": "2024-01-02",
            "status": "short_history",
        }
    )

    assert line == (
        "data_audit|market_daily_bar|short_history|rows|10|dates|2|"
        "min|2024-01-01|max|2024-01-02"
    )


def test_run_data_audit_marks_short_history_without_mutation(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [
            {
                "rows": 100,
                "date_count": 2,
                "min_date": "2024-05-27",
                "max_date": "2026-05-08",
            }
        ]

    monkeypatch.setattr(data_audit, "connect", lambda service: _context(object()))
    monkeypatch.setattr(data_audit, "fetch_all", fake_fetch_all)

    rows = data_audit.run_data_audit(
        expected_start_date="1990-12-01",
        datasets=["market_daily_bar"],
    )

    assert rows == [
        {
            "dataset": "market_daily_bar",
            "status": "short_history",
            "rows": 100,
            "date_count": 2,
            "min_date": "2024-05-27",
            "max_date": "2026-05-08",
        }
    ]
    assert calls
    assert all("insert " not in sql.lower() and "update " not in sql.lower() for sql, _ in calls)


def test_audit_includes_calendar_and_lifecycle_datasets():
    dataset_names = {dataset.dataset for dataset in data_audit.AUDIT_DATASETS}

    assert "market.trading_calendar" in dataset_names
    assert "core.asset_lifecycle_event" in dataset_names
