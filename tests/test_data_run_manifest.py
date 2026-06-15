from stock_research import data_run_manifest as manifest


class _Cursor:
    def __init__(self):
        self.calls = []
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_apply_data_run_manifest_schema_creates_ops_table(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(manifest, "connect", lambda service: _Context(conn))

    manifest.apply_data_run_manifest_schema()

    sql = conn.cursor_obj.calls[0][0]
    assert "CREATE TABLE IF NOT EXISTS ops.data_run_manifest" in sql
    assert "tier text NOT NULL" in sql
    assert "status text NOT NULL" in sql


def test_manifest_entry_normalizes_status_and_counts():
    entry = manifest.build_manifest_entry(
        run_id="eod-2026-06-12-local",
        run_date="2026-06-15",
        trade_date="2026-06-12",
        module="daily_bars",
        source="run-daily-incremental",
        tier="tier1",
        status="success",
        row_count=5200,
        warnings=["thin coverage"],
        artifact_path="outputs/daily/logs/daily_bars.log",
    )

    assert entry["manifest_id"].startswith("eod-2026-06-12-local:daily_bars:")
    assert entry["warning_count"] == 1
    assert entry["warnings"] == ["thin coverage"]
    assert entry["row_count"] == 5200


def test_upsert_data_run_manifest_writes_json_metadata(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(manifest, "connect", lambda service: _Context(conn))

    entry = manifest.build_manifest_entry(
        run_id="eod-2026-06-12-local",
        run_date="2026-06-15",
        trade_date="2026-06-12",
        module="news",
        source="public_news",
        tier="tier2",
        status="partial",
        warnings=["news partial"],
        metadata={"items": 3},
    )
    manifest.upsert_data_run_manifest(entry)

    sql, params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.data_run_manifest" in sql
    assert params["run_id"] == "eod-2026-06-12-local"
    assert params["module"] == "news"
    assert params["tier"] == "tier2"
    assert params["status"] == "partial"
    assert '"items": 3' in params["metadata"]


def test_summarize_manifest_modules_blocks_on_tier1_failure():
    modules = [
        {
            "module": "daily_bars",
            "tier": "tier1",
            "status": "success",
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "score_topn",
            "tier": "tier1",
            "status": "failed",
            "warnings": [],
            "error_message": "no scores",
        },
        {
            "module": "news",
            "tier": "tier2",
            "status": "failed",
            "warnings": ["news down"],
            "error_message": "down",
        },
    ]

    summary = manifest.summarize_manifest_modules(modules)

    assert summary["status"] == "BLOCKED"
    assert summary["tier1_status"] == "BLOCKED"
    assert summary["tier2_status"] == "PARTIAL"
    assert "score_topn" in summary["missing_data"]
    assert "news down" in summary["warnings"]


def test_summarize_manifest_modules_marks_tier2_failure_partial():
    modules = [
        {
            "module": "daily_bars",
            "tier": "tier1",
            "status": "success",
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "score_topn",
            "tier": "tier1",
            "status": "success",
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "review_queue",
            "tier": "tier1",
            "status": "success",
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "news",
            "tier": "tier2",
            "status": "failed",
            "warnings": ["news down"],
            "error_message": "down",
        },
    ]

    summary = manifest.summarize_manifest_modules(modules)

    assert summary["status"] == "PARTIAL"
    assert summary["tier1_status"] == "OK"
    assert summary["tier2_status"] == "PARTIAL"
    assert "news" in summary["partial_data"]
