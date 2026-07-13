from stock_research import research_evidence_registry


class _Cursor:
    def __init__(self, captured):
        self.captured = captured

    def execute(self, sql, params=None):
        self.captured.append((sql, params))


class _Conn:
    def __init__(self, captured):
        self.captured = captured

    def cursor(self):
        return self

    def __enter__(self):
        return _Cursor(self.captured)

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.captured.append(("COMMIT", None))


class _Ctx:
    def __init__(self, captured):
        self.captured = captured

    def __enter__(self):
        return _Conn(self.captured)

    def __exit__(self, exc_type, exc, tb):
        return False


def test_evidence_from_digest_snapshot_maps_core_fields():
    evidence = research_evidence_registry.evidence_from_digest_snapshot(
        {
            "snapshot_id": "evidence_digest_snapshot:abc",
            "asset_id": "CN:SZ:000001",
            "trade_date": "2026-07-06",
            "digest_key": "2026-07-06:manual_v1:CN:SZ:000001",
            "payload_hash": "hash123",
            "digest_payload": {"title": "Strong evidence", "score": 81},
        }
    )

    assert evidence["evidence_id"] == "evidence_artifact:evidence_digest_snapshot:abc"
    assert evidence["source_type"] == "evidence_digest_snapshot"
    assert evidence["source_id"] == "evidence_digest_snapshot:abc"
    assert evidence["asset_id"] == "CN:SZ:000001"
    assert evidence["title"] == "Strong evidence"
    assert evidence["content_hash"] == "hash123"


def test_evidence_from_review_item_snapshot_uses_none_for_missing_trade_date():
    evidence = research_evidence_registry.evidence_from_review_item_snapshot(
        {
            "snapshot_id": "review_item_snapshot:abc",
            "asset_id": "CN:SZ:000001",
            "trade_date": "",
            "digest_key": "digest:1",
            "payload_hash": "hash456",
            "review_item_payload": {"display_name": "平安银行", "score": 88},
        }
    )

    assert evidence["evidence_id"] == "evidence_artifact:review_item_snapshot:abc"
    assert evidence["source_type"] == "review_item_snapshot"
    assert evidence["trade_date"] is None
    assert evidence["title"] == "平安银行"


def test_upsert_evidence_artifact_writes_expected_sql(monkeypatch):
    captured = []
    monkeypatch.setattr(research_evidence_registry, "connect", lambda service: _Ctx(captured))

    evidence_id = research_evidence_registry.upsert_evidence_artifact(
        {
            "evidence_id": "evidence_artifact:evidence_digest_snapshot:abc",
            "source_type": "evidence_digest_snapshot",
            "source_id": "evidence_digest_snapshot:abc",
            "asset_id": "CN:SZ:000001",
            "trade_date": "2026-07-06",
            "title": "Strong evidence",
            "uri": "",
            "content_hash": "hash123",
            "payload": {"score": 81},
            "metadata": {"digest_key": "digest:1"},
        },
        service="research",
    )

    assert evidence_id == "evidence_artifact:evidence_digest_snapshot:abc"
    sql, params = captured[0]
    assert "INSERT INTO research.evidence_artifact" in sql
    assert params["trade_date"] == "2026-07-06"


def test_register_snapshot_evidence_loads_digest_and_review_rows(monkeypatch):
    captured = []

    def fake_fetch_all(_conn, sql, params=None):
        captured.append((sql, params))
        if "FROM ops.evidence_digest_snapshot" in sql:
            return [
                {
                    "snapshot_id": "evidence_digest_snapshot:abc",
                    "asset_id": "CN:SZ:000001",
                    "trade_date": "2026-07-06",
                    "digest_key": "digest:1",
                    "payload_hash": "hash123",
                    "digest_payload": {"title": "Strong evidence"},
                }
            ]
        if "FROM ops.review_item_snapshot" in sql:
            return [
                {
                    "snapshot_id": "review_item_snapshot:def",
                    "asset_id": "CN:SZ:000001",
                    "trade_date": "2026-07-06",
                    "digest_key": "digest:1",
                    "payload_hash": "hash456",
                    "review_item_payload": {"display_name": "平安银行"},
                }
            ]
        return []

    upserts = []
    monkeypatch.setattr(research_evidence_registry, "connect", lambda service: _Ctx([]))
    monkeypatch.setattr(research_evidence_registry, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(research_evidence_registry, "upsert_evidence_artifact", lambda evidence, service: upserts.append(evidence["evidence_id"]) or evidence["evidence_id"])

    result = research_evidence_registry.register_snapshot_evidence(asset_id="CN:SZ:000001", service="research")

    assert result == {
        "registered_count": 2,
        "evidence_ids": [
            "evidence_artifact:evidence_digest_snapshot:abc",
            "evidence_artifact:review_item_snapshot:def",
        ],
    }
