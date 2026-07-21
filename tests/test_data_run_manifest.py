import json
from datetime import datetime, timezone

import pytest

from stock_research import data_run_manifest


def test_upsert_replaces_publish_identity_and_start_time_for_same_day_rerun(monkeypatch):
    stored_row = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            if not stored_row:
                stored_row.update(params)
                return
            if "metadata = EXCLUDED.metadata" in sql:
                stored_row["metadata"] = params["metadata"]
            if "started_at = EXCLUDED.started_at" in sql:
                stored_row["started_at"] = params["started_at"]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(data_run_manifest, "connect", lambda service: FakeConnection())
    first = data_run_manifest.build_manifest_entry(
        run_id="strategy-eod-2026-07-20-local",
        run_date="2026-07-20",
        trade_date="2026-07-20",
        module="strategy_mid_trend",
        source="strategy_daily_eod",
        tier="tier1",
        status="success",
        started_at=datetime(2026, 7, 20, 12, 30, tzinfo=timezone.utc),
        metadata={"publish_id": "publish-1"},
    )
    second = data_run_manifest.build_manifest_entry(
        run_id="strategy-eod-2026-07-20-local",
        run_date="2026-07-20",
        trade_date="2026-07-20",
        module="strategy_mid_trend",
        source="strategy_daily_eod",
        tier="tier1",
        status="success",
        started_at=datetime(2026, 7, 20, 12, 31, tzinfo=timezone.utc),
        metadata={"publish_id": "publish-2"},
    )

    assert first["manifest_id"] == second["manifest_id"]
    data_run_manifest.upsert_data_run_manifest(first, service="research-test")
    data_run_manifest.upsert_data_run_manifest(second, service="research-test")

    assert json.loads(stored_row["metadata"])["publish_id"] == "publish-2"
    assert stored_row["started_at"] == "2026-07-20T12:31:00+00:00"


def test_load_recent_data_run_manifest_trade_date_fetches_latest_row_per_module(monkeypatch):
    calls = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        calls["service"] = service
        return FakeConnection()

    def fake_fetch_all(conn, sql, params):
        calls["sql"] = sql
        calls["params"] = params
        return [{"module": "strategy_lhb_shortline", "source": "strategy_eod"}]

    monkeypatch.setattr(data_run_manifest, "connect", fake_connect)
    monkeypatch.setattr(data_run_manifest, "fetch_all", fake_fetch_all)

    rows = data_run_manifest.load_recent_data_run_manifest(trade_date="2026-07-02", service="research")

    assert rows == [{"module": "strategy_lhb_shortline", "source": "strategy_eod"}]
    assert calls["service"] == "research"
    assert calls["params"] == {"trade_date": "2026-07-02"}
    assert "PARTITION BY module, source" in calls["sql"]
    assert "run_id = (SELECT run_id FROM latest)" not in calls["sql"]


def test_apply_schema_creates_manifest_before_publication_contract_schema(monkeypatch):
    calls = []
    connections = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql):
            calls.append(("manifest", sql))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    def fake_connect(service):
        connection = FakeConnection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(data_run_manifest, "connect", fake_connect)
    monkeypatch.setattr(
        "stock_research.strategy_publication_store.install_strategy_publication_schema",
        lambda cursor: calls.append(("publication", cursor)),
    )

    data_run_manifest.apply_data_run_manifest_schema(service="research-test")

    assert len(connections) == 1
    assert calls[0] == ("manifest", data_run_manifest.CREATE_DATA_RUN_MANIFEST_SQL)
    assert calls[1][0] == "publication"


def test_apply_schema_rolls_back_manifest_ddl_when_publication_install_fails(monkeypatch):
    events = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql):
            events.append(("execute", sql))

    class TransactionalConnection:
        def __init__(self):
            self.cursor_instance = FakeCursor()

        def __enter__(self):
            events.append(("connect", "enter"))
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append(("rollback" if exc_type else "commit", exc_type))
            return False

        def cursor(self):
            return self.cursor_instance

    connection = TransactionalConnection()
    connect_calls = []

    def fake_connect(service):
        connect_calls.append(service)
        return connection

    def fail_install(cursor):
        assert cursor is connection.cursor_instance
        events.append(("publication", "failed"))
        raise RuntimeError("publication install failed")

    monkeypatch.setattr(data_run_manifest, "connect", fake_connect)
    monkeypatch.setattr(
        "stock_research.strategy_publication_store.install_strategy_publication_schema",
        fail_install,
    )

    with pytest.raises(RuntimeError, match="publication install failed"):
        data_run_manifest.apply_data_run_manifest_schema(service="research-test")

    assert connect_calls == ["research-test"]
    assert events == [
        ("connect", "enter"),
        ("execute", data_run_manifest.CREATE_DATA_RUN_MANIFEST_SQL),
        ("publication", "failed"),
        ("rollback", RuntimeError),
    ]
