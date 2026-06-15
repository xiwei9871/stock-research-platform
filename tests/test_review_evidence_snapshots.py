from stock_research import review_evidence_snapshots as snapshots


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

    def fetchone(self):
        return self.rows[0] if self.rows else None


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


def test_apply_review_evidence_snapshot_schema_creates_ops_tables(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(snapshots, "connect", lambda service: _Context(conn))

    snapshots.apply_review_evidence_snapshot_schema()

    sql = conn.cursor_obj.calls[0][0]
    assert "CREATE TABLE IF NOT EXISTS ops.review_item_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.evidence_digest_snapshot" in sql
    assert "UNIQUE (run_id, digest_key)" in sql


def test_canonical_payload_hash_is_stable_for_key_order():
    first = snapshots.canonical_payload_hash({"b": 2, "a": 1})
    second = snapshots.canonical_payload_hash({"a": 1, "b": 2})

    assert first == second
    assert len(first) == 64


def test_build_review_item_snapshot_extracts_lineage_fields():
    item = {
        "run_id": "eod-2026-06-12-local",
        "trade_date": "2026-06-12",
        "latest_trade_date": "2026-06-12",
        "asset_id": "000001.SZ",
        "canonical_asset_id": "000001.SZ",
        "display_name": "平安银行",
        "digest_key": "2026-06-12:manual_v1:000001.SZ",
        "source_type": "score_topn",
        "source_name": "manual_v1_topn",
        "source_rank": 3,
        "topn_rank": 3,
        "score_version": "manual_v1",
        "score": 88.5,
        "evidence_status": "PARTIAL",
        "missing_evidence_count": 1,
        "partial_evidence_count": 2,
        "warnings_count": 1,
    }

    snapshot = snapshots.build_review_item_snapshot(item)

    assert snapshot["snapshot_id"].startswith("review_item_snapshot:")
    assert snapshot["run_id"] == "eod-2026-06-12-local"
    assert snapshot["stock_name"] == "平安银行"
    assert snapshot["digest_key"] == "2026-06-12:manual_v1:000001.SZ"
    assert snapshot["payload_hash"] == snapshots.canonical_payload_hash(item)
    assert snapshot["schema_version"] == "v1"


def test_build_evidence_digest_snapshot_preserves_partial_evidence():
    digest = {
        "run_id": "eod-2026-06-12-local",
        "trade_date": "2026-06-12",
        "latest_trade_date": "2026-06-12",
        "asset_id": "000001.SZ",
        "canonical_asset_id": "000001.SZ",
        "stock_code": "000001.SZ",
        "stock_name": "平安银行",
        "digest_key": "2026-06-12:manual_v1:000001.SZ",
        "overall_status": "PARTIAL",
        "missing_evidence": ["research_reports"],
        "partial_evidence": ["news"],
        "sections": {
            "news": {"status": "partial"},
            "research_reports": {"status": "missing"},
        },
    }

    snapshot = snapshots.build_evidence_digest_snapshot(digest)

    assert snapshot["snapshot_id"].startswith("evidence_digest_snapshot:")
    assert snapshot["missing_evidence"] == ["research_reports"]
    assert snapshot["partial_evidence"] == ["news"]
    assert snapshot["sections_status"] == {
        "news": "partial",
        "research_reports": "missing",
    }
    assert snapshot["payload_hash"] == snapshots.canonical_payload_hash(digest)


def test_upsert_review_item_snapshot_writes_json_payload(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(snapshots, "connect", lambda service: _Context(conn))
    snapshot = snapshots.build_review_item_snapshot(
        {
            "run_id": "eod-2026-06-12-local",
            "trade_date": "2026-06-12",
            "asset_id": "000001.SZ",
            "digest_key": "2026-06-12:manual_v1:000001.SZ",
            "source_type": "score_topn",
            "source_name": "manual_v1_topn",
            "score_version": "manual_v1",
            "evidence_status": "OK",
        }
    )

    snapshot_id = snapshots.upsert_review_item_snapshot(snapshot)

    sql, params = conn.cursor_obj.calls[0]
    assert snapshot_id == snapshot["snapshot_id"]
    assert "INSERT INTO ops.review_item_snapshot" in sql
    assert "ON CONFLICT (run_id, digest_key)" in sql
    assert params["run_id"] == "eod-2026-06-12-local"
    assert '"source_name":"manual_v1_topn"' in params["review_item_payload"]


def test_upsert_evidence_digest_snapshot_writes_json_payload(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(snapshots, "connect", lambda service: _Context(conn))
    snapshot = snapshots.build_evidence_digest_snapshot(
        {
            "run_id": "eod-2026-06-12-local",
            "trade_date": "2026-06-12",
            "asset_id": "000001.SZ",
            "digest_key": "2026-06-12:manual_v1:000001.SZ",
            "overall_status": "PARTIAL",
            "missing_evidence": ["news"],
            "partial_evidence": [],
            "sections": {"news": {"status": "missing"}},
        }
    )

    snapshot_id = snapshots.upsert_evidence_digest_snapshot(snapshot)

    sql, params = conn.cursor_obj.calls[0]
    assert snapshot_id == snapshot["snapshot_id"]
    assert "INSERT INTO ops.evidence_digest_snapshot" in sql
    assert "ON CONFLICT (run_id, digest_key)" in sql
    assert params["missing_evidence"] == '["news"]'
    assert '"news":"missing"' in params["sections_status"]


def test_snapshot_review_queue_payload_persists_items_and_embedded_digests(monkeypatch):
    calls = {"review": [], "digest": []}
    monkeypatch.setattr(snapshots, "upsert_review_item_snapshot", lambda item, service="stock_research": calls["review"].append(item) or item["snapshot_id"])
    monkeypatch.setattr(snapshots, "upsert_evidence_digest_snapshot", lambda item, service="stock_research": calls["digest"].append(item) or item["snapshot_id"])
    queue = {
        "groups": [
            {
                "items": [
                    {
                        "run_id": "eod-2026-06-12-local",
                        "trade_date": "2026-06-12",
                        "asset_id": "000001.SZ",
                        "digest_key": "2026-06-12:manual_v1:000001.SZ",
                        "source_type": "score_topn",
                        "source_name": "manual_v1_topn",
                        "score_version": "manual_v1",
                        "evidence_status": "PARTIAL",
                        "digest": {
                            "run_id": "eod-2026-06-12-local",
                            "trade_date": "2026-06-12",
                            "asset_id": "000001.SZ",
                            "digest_key": "2026-06-12:manual_v1:000001.SZ",
                            "overall_status": "PARTIAL",
                            "missing_evidence": ["research_reports"],
                            "partial_evidence": [],
                            "sections": {"research_reports": {"status": "missing"}},
                        },
                    }
                ]
            }
        ]
    }

    result = snapshots.snapshot_review_queue_payload(queue)

    assert result["review_item_snapshot_count"] == 1
    assert result["evidence_digest_snapshot_count"] == 1
    assert calls["review"][0]["digest_key"] == "2026-06-12:manual_v1:000001.SZ"
    assert calls["digest"][0]["missing_evidence"] == ["research_reports"]


def test_list_review_item_snapshots_builds_filters(monkeypatch):
    captured = {}

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [{"snapshot_id": "review_item_snapshot:abc", "review_item_payload": {"asset_id": "000001.SZ"}}]

    monkeypatch.setattr(snapshots, "connect", lambda service: _Context(_Connection()))
    monkeypatch.setattr(snapshots, "fetch_all", fake_fetch_all)

    rows = snapshots.list_review_item_snapshots(run_id="run-1", digest_key="digest-1")

    assert "FROM ops.review_item_snapshot" in captured["sql"]
    assert "run_id = %(run_id)s" in captured["sql"]
    assert "digest_key = %(digest_key)s" in captured["sql"]
    assert captured["params"] == {"run_id": "run-1", "digest_key": "digest-1", "limit": 100}
    assert rows[0]["snapshot_id"] == "review_item_snapshot:abc"


def test_load_evidence_digest_snapshot_returns_single_row(monkeypatch):
    captured = {}

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [{"snapshot_id": "evidence_digest_snapshot:abc", "digest_payload": {"digest_key": "digest-1"}}]

    monkeypatch.setattr(snapshots, "connect", lambda service: _Context(_Connection()))
    monkeypatch.setattr(snapshots, "fetch_all", fake_fetch_all)

    row = snapshots.load_evidence_digest_snapshot("evidence_digest_snapshot:abc")

    assert "FROM ops.evidence_digest_snapshot" in captured["sql"]
    assert captured["params"] == {"snapshot_id": "evidence_digest_snapshot:abc"}
    assert row["digest_payload"]["digest_key"] == "digest-1"


def test_run_eod_review_evidence_snapshots_writes_summary_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(
        snapshots,
        "build_review_queue",
        lambda trade_date, score_version, limit: {
            "groups": [
                {
                    "items": [
                        {
                            "run_id": "eod-2026-06-12-local",
                            "trade_date": "2026-06-12",
                            "latest_trade_date": "2026-06-12",
                            "asset_id": "000001.SZ",
                            "canonical_asset_id": "000001.SZ",
                            "digest_key": "2026-06-12:manual_v1:000001.SZ",
                            "source_type": "score_topn",
                            "source_name": "manual_v1_topn",
                            "score_version": "manual_v1",
                            "evidence_status": "OK",
                            "digest": {
                                "run_id": "eod-2026-06-12-local",
                                "trade_date": "2026-06-12",
                                "latest_trade_date": "2026-06-12",
                                "asset_id": "000001.SZ",
                                "digest_key": "2026-06-12:manual_v1:000001.SZ",
                                "overall_status": "OK",
                                "sections": {"news": {"status": "available"}},
                            },
                        }
                    ]
                }
            ],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        snapshots,
        "snapshot_review_queue_payload",
        lambda queue, service="stock_research": {
            "review_item_snapshot_count": 1,
            "evidence_digest_snapshot_count": 1,
            "review_item_snapshot_ids": ["review_item_snapshot:abc"],
            "evidence_digest_snapshot_ids": ["evidence_digest_snapshot:def"],
        },
    )

    result = snapshots.run_eod_review_evidence_snapshots(
        run_id="eod-2026-06-12-local",
        trade_date="2026-06-12",
        output_dir=tmp_path,
        limit=30,
    )

    assert result["status"] == "success"
    assert result["review_item_snapshot_count"] == 1
    assert result["evidence_digest_snapshot_count"] == 1
    assert result["asset_count"] == 1
    assert result["row_count"] == 2
    assert result["warning_count"] == 0
    artifact_path = tmp_path / "review_evidence_snapshots_summary.json"
    assert result["artifact_path"] == str(artifact_path)
    payload = __import__("json").loads(artifact_path.read_text())
    assert payload["run_id"] == "eod-2026-06-12-local"
    assert payload["snapshot_status"] == "success"


def test_run_eod_review_evidence_snapshots_skips_empty_queue(monkeypatch):
    monkeypatch.setattr(
        snapshots,
        "build_review_queue",
        lambda trade_date, score_version, limit: {"groups": [{"items": []}], "warnings": []},
    )

    result = snapshots.run_eod_review_evidence_snapshots(
        run_id="eod-2026-06-12-local",
        trade_date="2026-06-12",
    )

    assert result["status"] == "skipped"
    assert result["review_item_snapshot_count"] == 0
    assert result["evidence_digest_snapshot_count"] == 0
    assert result["warnings"] == ["review queue empty; snapshot step skipped"]


def test_run_eod_review_evidence_snapshots_partial_when_persist_fails(monkeypatch):
    monkeypatch.setattr(
        snapshots,
        "build_review_queue",
        lambda trade_date, score_version, limit: {
            "groups": [{"items": [{"asset_id": "000001.SZ", "digest_key": "digest-1"}]}],
            "warnings": [],
        },
    )

    def failing_snapshot(queue, service="stock_research"):
        raise RuntimeError("snapshot db offline")

    monkeypatch.setattr(snapshots, "snapshot_review_queue_payload", failing_snapshot)

    result = snapshots.run_eod_review_evidence_snapshots(
        run_id="eod-2026-06-12-local",
        trade_date="2026-06-12",
    )

    assert result["status"] == "partial"
    assert result["failed_count"] == 1
    assert result["errors"] == ["snapshot db offline"]
    assert "snapshot generation failed: snapshot db offline" in result["warnings"]


def test_run_eod_review_evidence_snapshots_dry_run_does_not_persist(monkeypatch):
    calls = []
    monkeypatch.setattr(
        snapshots,
        "build_review_queue",
        lambda trade_date, score_version, limit: {
            "groups": [{"items": [{"asset_id": "000001.SZ", "digest_key": "digest-1"}]}],
            "warnings": ["news partial"],
        },
    )
    monkeypatch.setattr(
        snapshots,
        "snapshot_review_queue_payload",
        lambda queue, service="stock_research": calls.append(queue),
    )

    result = snapshots.run_eod_review_evidence_snapshots(
        run_id="eod-2026-06-12-local",
        trade_date="2026-06-12",
        dry_run=True,
    )

    assert result["status"] == "partial"
    assert result["review_item_snapshot_count"] == 1
    assert result["evidence_digest_snapshot_count"] == 0
    assert result["warnings"] == ["news partial", "dry_run enabled; snapshots were not persisted"]
    assert calls == []
