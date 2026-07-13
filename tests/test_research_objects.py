from stock_research import schema
from stock_research import research_objects
from stock_research.operator_decision import write_service


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


def test_research_object_schema_contains_core_tables():
    sql = research_objects.RESEARCH_OBJECTS_SQL

    assert "CREATE SCHEMA IF NOT EXISTS research" in sql
    assert "CREATE TABLE IF NOT EXISTS research.research_case" in sql
    assert "CREATE TABLE IF NOT EXISTS research.research_claim" in sql
    assert "CREATE TABLE IF NOT EXISTS research.evidence_artifact" in sql
    assert "CREATE TABLE IF NOT EXISTS research.evidence_link" in sql
    assert "CREATE TABLE IF NOT EXISTS research.decision_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS research.publication_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS research.agent_run" in sql
    assert "CREATE TABLE IF NOT EXISTS research.agent_run_event" in sql


def test_research_object_schema_is_idempotent_and_non_destructive():
    sql = research_objects.RESEARCH_OBJECTS_SQL

    assert "CREATE TABLE research." not in sql
    assert "CREATE INDEX idx_" not in sql
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "CREATE INDEX IF NOT EXISTS" in sql


def test_apply_schema_includes_research_objects(monkeypatch):
    calls = []

    class _ApplyConn:
        pass

    class _ApplyCtx:
        def __enter__(self):
            return _ApplyConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(schema, "connect", lambda service: _ApplyCtx())
    monkeypatch.setattr(schema, "execute", lambda conn, sql: calls.append(sql))
    monkeypatch.setattr(schema, "migrate_stock_minute_bar_to_partitioned", lambda conn: None)
    monkeypatch.setattr(schema, "ensure_research_schema_compatibility", lambda conn: None)
    monkeypatch.setattr(schema, "ensure_stock_minute_bar_partitions", lambda conn: None)

    schema.apply_schema()

    assert any("CREATE TABLE IF NOT EXISTS research.research_case" in sql for sql in calls)


def test_stable_id_uses_canonical_json_for_dicts():
    first = research_objects.stable_id("research_case", {"b": 2, "a": [1, 2]})
    second = research_objects.stable_id("research_case", {"a": [1, 2], "b": 2})

    assert first == second
    assert first.startswith("research_case:")


def test_upsert_research_case_writes_expected_sql(monkeypatch):
    captured = []
    monkeypatch.setattr(research_objects, "connect", lambda service: _Ctx(captured))

    case_id = research_objects.upsert_research_case(
        {
            "trade_date": "2026-07-06",
            "asset_id": "CN:SZ:000001",
            "theme": "bank_reversal",
            "title": "Bank reversal candidate",
            "source_type": "review_queue",
            "source_id": "review:1",
        },
        service="research",
    )

    assert case_id.startswith("research_case:")
    sql, params = captured[0]
    assert "INSERT INTO research.research_case" in sql
    assert params["asset_id"] == "CN:SZ:000001"
    assert params["status"] == "open"


def test_upsert_research_claim_writes_expected_sql(monkeypatch):
    captured = []
    monkeypatch.setattr(research_objects, "connect", lambda service: _Ctx(captured))

    claim_id = research_objects.upsert_research_claim(
        {
            "case_id": "research_case:abc",
            "claim_type": "catalyst",
            "claim_text": "Earnings revision may drive rerating",
            "confidence": 0.72,
        },
        service="research",
    )

    assert claim_id.startswith("research_claim:")
    sql, params = captured[0]
    assert "INSERT INTO research.research_claim" in sql
    assert params["case_id"] == "research_case:abc"


def test_mirror_operator_decision_to_research_snapshot(monkeypatch):
    captured = []
    monkeypatch.setattr(research_objects, "connect", lambda service: _Ctx(captured))

    snapshot_id = research_objects.mirror_operator_decision_to_research_snapshot(
        {
            "event_id": "operator_decision:test",
            "asset_id": "CN:SZ:000001",
            "decision_label": "observe",
            "decision_status": "open",
            "source_context": {"evidence_digest_snapshot_id": "evidence_digest_snapshot:def"},
        },
        service="research",
    )

    assert snapshot_id == "decision_snapshot:operator_decision:test"
    sql, params = captured[0]
    assert "INSERT INTO research.decision_snapshot" in sql
    assert params["decision_event_id"] == "operator_decision:test"


def test_create_operator_decision_mirrors_research_snapshot(monkeypatch):
    captured = []
    mirrored = []
    monkeypatch.setattr(write_service, "connect", lambda service: _Ctx(captured))
    monkeypatch.setattr(write_service, "resolve_decision_snapshot_linkage", lambda payload, service: {})
    monkeypatch.setattr(
        write_service,
        "mirror_operator_decision_to_research_snapshot",
        lambda decision, service, cursor=None: mirrored.append((decision, service, cursor)) or "decision_snapshot:operator_decision:test",
    )

    result = write_service.create_operator_decision(
        {
            "asset_id": "CN:SZ:000001",
            "stock_code": "000001.SZ",
            "decision_date": "2026-07-06",
            "operator_action": "watch",
            "decision_status": "open",
            "digest_key": "digest:1",
        },
        service="research",
    )

    assert result["decision_snapshot_id"] == "decision_snapshot:operator_decision:test"
    assert mirrored[0][1] == "research"
    assert mirrored[0][0]["event_id"] == result["event_id"]
    assert mirrored[0][0]["decision_label"] == "observe"
    assert mirrored[0][2] is not None


def test_create_operator_decision_mirrors_snapshot_in_same_transaction(monkeypatch):
    captured = []
    monkeypatch.setattr(write_service, "connect", lambda service: _Ctx(captured))
    monkeypatch.setattr(write_service, "resolve_decision_snapshot_linkage", lambda payload, service: {})
    monkeypatch.setattr(
        research_objects,
        "connect",
        lambda service: (_ for _ in ()).throw(AssertionError("snapshot opened a separate connection")),
    )

    result = write_service.create_operator_decision(
        {
            "asset_id": "CN:SZ:000001",
            "stock_code": "000001.SZ",
            "decision_date": "2026-07-06",
            "operator_action": "watch",
            "decision_status": "open",
            "digest_key": "digest:1",
        },
        service="research",
    )

    assert result["decision_snapshot_id"].startswith("decision_snapshot:operator_decision:")
    assert any("INSERT INTO ops.operator_decision_event" in sql for sql, _params in captured)
    assert any("INSERT INTO research.decision_snapshot" in sql for sql, _params in captured)


def test_upsert_publication_snapshot_writes_expected_sql(monkeypatch):
    captured = []
    monkeypatch.setattr(research_objects, "connect", lambda service: _Ctx(captured))

    snapshot_id = research_objects.upsert_publication_snapshot(
        {
            "trade_date": "2026-07-06",
            "channel": "dashboard",
            "title": "Daily Research Brief",
            "payload": {"status": "published"},
        },
        service="research",
    )

    assert snapshot_id.startswith("publication_snapshot:")
    sql, params = captured[0]
    assert "INSERT INTO research.publication_snapshot" in sql
    assert params["channel"] == "dashboard"


def test_record_publication_snapshot_uses_append_only_internal_id(monkeypatch):
    captured = []
    monkeypatch.setattr(research_objects, "connect", lambda service: _Ctx(captured))

    snapshot_id = research_objects.record_publication_snapshot(
        {
            "trade_date": "2026-07-06",
            "channel": "research_queue_internal",
            "title": "Research Queue Internal Snapshot",
            "payload": {"package_id": "research_publication_package:abc"},
        },
        service="research",
    )

    assert snapshot_id.startswith("publication_snapshot:research_queue_internal:")
    sql, params = captured[0]
    assert "INSERT INTO research.publication_snapshot" in sql
    assert "ON CONFLICT" not in sql
    assert params["channel"] == "research_queue_internal"


def test_upsert_evidence_link_writes_idempotent_link(monkeypatch):
    captured = []
    monkeypatch.setattr(research_objects, "connect", lambda service: _Ctx(captured))

    link_id = research_objects.upsert_evidence_link(
        {
            "evidence_id": "evidence_artifact:review_item_snapshot:abc",
            "target_type": "research_case",
            "target_id": "research_case:abc",
            "relation": "supports",
            "metadata": {"source": "seed"},
        },
        service="research",
    )

    assert link_id.startswith("evidence_link:")
    sql, params = captured[0]
    assert "INSERT INTO research.evidence_link" in sql
    assert "ON CONFLICT (evidence_id, target_type, target_id, relation)" in sql
    assert params["evidence_id"] == "evidence_artifact:review_item_snapshot:abc"
    assert params["target_type"] == "research_case"
