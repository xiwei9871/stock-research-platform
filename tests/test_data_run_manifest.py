import json
from datetime import datetime, timezone

import pytest

from stock_research import data_run_manifest


@pytest.mark.parametrize(
    (
        "first_started_at",
        "second_started_at",
        "expected_publish_id",
        "expected_status",
        "expected_started_at",
    ),
    [
        (
            datetime(2026, 7, 20, 12, 30, 0, 100000, tzinfo=timezone.utc),
            datetime(2026, 7, 20, 12, 30, 0, 900000, tzinfo=timezone.utc),
            "publish-2",
            "failed",
            "2026-07-20T12:30:00.900000+00:00",
        ),
        (
            datetime(2026, 7, 20, 12, 30, 0, 900000, tzinfo=timezone.utc),
            datetime(2026, 7, 20, 12, 30, 0, 100000, tzinfo=timezone.utc),
            "publish-1",
            "success",
            "2026-07-20T12:30:00.900000+00:00",
        ),
        (
            datetime(2026, 7, 20, 12, 30, 0, 500000, tzinfo=timezone.utc),
            datetime(2026, 7, 20, 12, 30, 0, 500000, tzinfo=timezone.utc),
            "publish-2",
            "failed",
            "2026-07-20T12:30:00.500000+00:00",
        ),
        (
            datetime(2026, 7, 20, 12, 30, tzinfo=timezone.utc),
            None,
            "publish-1",
            "success",
            "2026-07-20T12:30:00.000000+00:00",
        ),
        (
            None,
            datetime(2026, 7, 20, 12, 30, tzinfo=timezone.utc),
            "publish-2",
            "failed",
            "2026-07-20T12:30:00.000000+00:00",
        ),
        (None, None, "publish-2", "failed", None),
    ],
)
def test_upsert_only_replaces_same_day_row_with_non_older_start_time(
    monkeypatch,
    first_started_at,
    second_started_at,
    expected_publish_id,
    expected_status,
    expected_started_at,
):
    stored_row = {}
    expected_gate = (
        "WHERE existing.started_at IS NULL OR "
        "( EXCLUDED.started_at IS NOT NULL AND "
        "EXCLUDED.started_at >= existing.started_at )"
    )

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            assert expected_gate in " ".join(sql.split())
            if not stored_row:
                stored_row.update(params)
                return
            current_started_at = stored_row["started_at"]
            incoming_started_at = params["started_at"]
            should_update = current_started_at is None or (
                incoming_started_at is not None
                and datetime.fromisoformat(incoming_started_at)
                >= datetime.fromisoformat(current_started_at)
            )
            if should_update:
                stored_row.update(params)

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
        started_at=first_started_at,
        metadata={"publish_id": "publish-1"},
    )
    second = data_run_manifest.build_manifest_entry(
        run_id="strategy-eod-2026-07-20-local",
        run_date="2026-07-20",
        trade_date="2026-07-20",
        module="strategy_mid_trend",
        source="strategy_daily_eod",
        tier="tier1",
        status="failed",
        started_at=second_started_at,
        metadata={"publish_id": "publish-2"},
    )

    assert first["manifest_id"] == second["manifest_id"]
    data_run_manifest.upsert_data_run_manifest(first, service="research-test")
    data_run_manifest.upsert_data_run_manifest(second, service="research-test")

    assert json.loads(stored_row["metadata"])["publish_id"] == expected_publish_id
    assert stored_row["status"] == expected_status
    assert stored_row["started_at"] == expected_started_at


@pytest.mark.parametrize(
    ("started_at", "expected"),
    [
        (
            datetime.fromisoformat("2026-07-20T20:30:00.123456+08:00"),
            "2026-07-20T12:30:00.123456+00:00",
        ),
        (
            "2026-07-20T20:30:00.654321+08:00",
            "2026-07-20T12:30:00.654321+00:00",
        ),
        (
            datetime(2026, 7, 20, 12, 30, 0, 987654),
            "2026-07-20T12:30:00.987654+00:00",
        ),
    ],
)
def test_build_manifest_entry_canonicalizes_utc_microseconds(started_at, expected):
    entry = data_run_manifest.build_manifest_entry(
        run_id="run-1",
        run_date="2026-07-20",
        trade_date="2026-07-20",
        module="module-1",
        source="source-1",
        tier="tier1",
        status="success",
        started_at=started_at,
    )

    assert entry["started_at"] == expected


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
