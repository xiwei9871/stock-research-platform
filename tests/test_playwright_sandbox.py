import pytest

import stock_research.playwright_sandbox as playwright_sandbox
from stock_research.playwright_sandbox import (
    SandboxCredentials,
    assert_sandbox_database,
    build_sandbox_seed,
    cleanup_sandbox,
    load_sandbox_database_name,
    prepare_sandbox,
)


class FakeCursor:
    def __init__(
        self,
        row=("stock_research_e2e_test",),
        *,
        execute_error=None,
        fetch_error=None,
        close_error=None,
    ):
        self.row = row
        self.execute_error = execute_error
        self.fetch_error = fetch_error
        self.close_error = close_error
        self.executed = []
        self.closed = False

    def execute(self, query):
        self.executed.append(query)
        if self.execute_error is not None:
            raise self.execute_error

    def fetchone(self):
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.row

    def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class FakeConnection:
    def __init__(self, cursor=None, *, cursor_error=None, close_error=None):
        self._cursor = cursor
        self.cursor_error = cursor_error
        self.close_error = close_error
        self.closed = False

    def cursor(self):
        if self.cursor_error is not None:
            raise self.cursor_error
        return self._cursor

    def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class LifecycleCursor:
    def __init__(self, database_name="stock_research_e2e_test", *, fail_on=None):
        self.database_name = database_name
        self.fail_on = fail_on
        self.executed = []
        self.closed = False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if self.fail_on and self.fail_on in query:
            raise RuntimeError("injected lifecycle failure")

    def fetchone(self):
        return (self.database_name,)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class LifecycleConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_load_sandbox_database_name_queries_actual_database_and_closes_resources():
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    connect_calls = []

    def connector(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return connection

    database_name = load_sandbox_database_name(
        "stock_research_e2e_test", connector=connector
    )

    assert database_name == "stock_research_e2e_test"
    assert connect_calls == [((), {"service": "stock_research_e2e_test"})]
    assert cursor.executed == ["SELECT current_database()"]
    assert cursor.closed is True
    assert connection.closed is True


def test_load_sandbox_database_name_propagates_query_error_and_closes_resources():
    database_error = RuntimeError("database unavailable")
    cursor = FakeCursor(execute_error=database_error)
    connection = FakeConnection(cursor)

    with pytest.raises(RuntimeError, match="database unavailable") as error:
        load_sandbox_database_name(
            "stock_research_e2e_test", connector=lambda **_: connection
        )

    assert error.value is database_error
    assert cursor.closed is True
    assert connection.closed is True


def test_load_sandbox_database_name_fails_closed_when_query_returns_no_row():
    cursor = FakeCursor(row=None)
    connection = FakeConnection(cursor)

    with pytest.raises(RuntimeError, match="could not determine sandbox database"):
        load_sandbox_database_name(
            "stock_research_e2e_test", connector=lambda **_: connection
        )

    assert cursor.closed is True
    assert connection.closed is True


def test_sandbox_accepts_database_name_ending_in_lowercase_test():
    assert (
        assert_sandbox_database("stock_research_e2e_test")
        == "stock_research_e2e_test"
    )


@pytest.mark.parametrize(
    "database_name",
    [
        None,
        17,
        "",
        "stock_research",
        "stock_research_e2e_TEST",
        "stock_research_e2e_test ",
        '"stock_research_e2e_test"',
    ],
)
def test_sandbox_rejects_non_test_database_and_textual_bypasses(database_name):
    with pytest.raises(RuntimeError, match="refusing non-test database"):
        assert_sandbox_database(database_name)


def test_test_named_service_does_not_override_real_database_identity():
    cursor = FakeCursor(row=("stock_research",))
    connection = FakeConnection(cursor)

    database_name = load_sandbox_database_name(
        "stock_research_e2e_test", connector=lambda **_: connection
    )

    with pytest.raises(RuntimeError, match="refusing non-test database"):
        assert_sandbox_database(database_name)


@pytest.mark.parametrize(
    "service",
    [
        "safe dbname=production",
        r"safe\ dbname=production",
        "测试 服务",
    ],
)
def test_load_sandbox_database_name_passes_service_as_one_keyword(service):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    connect_calls = []

    def connector(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return connection

    load_sandbox_database_name(service, connector=connector)

    assert connect_calls == [((), {"service": service})]


def test_load_sandbox_database_name_resolves_default_connector_at_call_time(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    connect_calls = []

    def connector(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return connection

    monkeypatch.setattr(playwright_sandbox.psycopg, "connect", connector)

    load_sandbox_database_name("stock_research_e2e_test")

    assert connect_calls == [((), {"service": "stock_research_e2e_test"})]


def test_cursor_acquisition_error_still_closes_connection():
    cursor_error = RuntimeError("cursor unavailable")
    connection = FakeConnection(cursor_error=cursor_error)

    with pytest.raises(RuntimeError, match="cursor unavailable") as error:
        load_sandbox_database_name(
            "stock_research_e2e_test", connector=lambda **_: connection
        )

    assert error.value is cursor_error
    assert connection.closed is True


@pytest.mark.parametrize("query_stage", ["execute", "fetch"])
def test_query_error_survives_cursor_and_connection_cleanup_errors(query_stage):
    query_error = RuntimeError(f"{query_stage} failed")
    cursor_close_error = RuntimeError("cursor close failed")
    connection_close_error = RuntimeError("connection close failed")
    cursor = FakeCursor(
        execute_error=query_error if query_stage == "execute" else None,
        fetch_error=query_error if query_stage == "fetch" else None,
        close_error=cursor_close_error,
    )
    connection = FakeConnection(cursor, close_error=connection_close_error)

    with pytest.raises(RuntimeError, match=f"{query_stage} failed") as error:
        load_sandbox_database_name(
            "stock_research_e2e_test", connector=lambda **_: connection
        )

    assert error.value is query_error
    assert cursor.closed is True
    assert connection.closed is True
    assert error.value.__notes__ == [
        "cursor cleanup failed: RuntimeError('cursor close failed')",
        "connection cleanup failed: RuntimeError('connection close failed')",
    ]


def test_cursor_acquisition_error_survives_connection_cleanup_error():
    cursor_error = RuntimeError("cursor unavailable")
    connection = FakeConnection(
        cursor_error=cursor_error,
        close_error=RuntimeError("connection close failed"),
    )

    with pytest.raises(RuntimeError, match="cursor unavailable") as error:
        load_sandbox_database_name(
            "stock_research_e2e_test", connector=lambda **_: connection
        )

    assert error.value is cursor_error
    assert connection.closed is True
    assert error.value.__notes__ == [
        "connection cleanup failed: RuntimeError('connection close failed')"
    ]


def test_cleanup_error_propagates_after_all_resources_are_closed():
    cursor_close_error = RuntimeError("cursor close failed")
    cursor = FakeCursor(close_error=cursor_close_error)
    connection = FakeConnection(
        cursor,
        close_error=RuntimeError("connection close failed"),
    )

    with pytest.raises(RuntimeError, match="cursor close failed") as error:
        load_sandbox_database_name(
            "stock_research_e2e_test", connector=lambda **_: connection
        )

    assert error.value is cursor_close_error
    assert cursor.closed is True
    assert connection.closed is True
    assert error.value.__notes__ == [
        "connection cleanup also failed: RuntimeError('connection close failed')"
    ]


def test_build_sandbox_seed_is_deterministic_and_run_scoped():
    first = build_sandbox_seed("audit_20260721_ab12")
    second = build_sandbox_seed("audit_20260721_ab12")

    assert first == second
    assert first.admin_username == "e2e_audit_20260721_ab12_admin"
    assert first.user_username == "e2e_audit_20260721_ab12_user"
    assert first.created_username == "e2e_audit_20260721_ab12_created"
    for seed_id in (
        first.admin_user_id,
        first.user_user_id,
        first.review_session_id,
        first.operator_event_id,
        first.evidence_artifact_id,
        first.review_item_snapshot_id,
        first.evidence_digest_snapshot_id,
    ):
        assert seed_id.startswith("audit_20260721_ab12:")


def test_prepare_sandbox_uses_parameterized_seed_sql_and_commits():
    cursor = LifecycleCursor()
    connection = LifecycleConnection(cursor)
    credentials = SandboxCredentials(
        admin_password="admin-password-not-in-sql",
        user_password="user-password-not-in-sql",
    )

    seed = prepare_sandbox(connection, "audit_20260721_ab12", credentials)

    assert connection.commits == 1
    assert connection.rollbacks == 0
    statements = [query for query, _ in cursor.executed]
    assert statements[0].strip() == "SELECT current_database()"
    assert any("identity.user_account" in query and "INSERT INTO" in query for query in statements)
    assert any("ops.operator_review_session" in query and "INSERT INTO" in query for query in statements)
    assert any("ops.operator_decision_event" in query and "INSERT INTO" in query for query in statements)
    assert any("ops.review_item_snapshot" in query and "INSERT INTO" in query for query in statements)
    assert any("ops.evidence_digest_snapshot" in query and "INSERT INTO" in query for query in statements)
    for query, params in cursor.executed:
        if "INSERT INTO" in query:
            assert params is not None
            assert credentials.admin_password not in query
            assert credentials.user_password not in query
    decision_params = next(
        params
        for query, params in cursor.executed
        if "INSERT INTO ops.operator_decision_event" in query
    )
    assert decision_params["event_id"] == seed.operator_event_id
    assert decision_params["evidence_artifact_id"] == seed.evidence_artifact_id
    assert seed.evidence_artifact_id in decision_params["source_context"]
    assert seed.review_item_snapshot_id in decision_params["source_context"]
    assert seed.evidence_digest_snapshot_id in decision_params["source_context"]


def test_prepare_sandbox_rolls_back_after_seed_error():
    cursor = LifecycleCursor(fail_on="INSERT INTO ops.operator_decision_event")
    connection = LifecycleConnection(cursor)

    with pytest.raises(RuntimeError, match="injected lifecycle failure"):
        prepare_sandbox(
            connection,
            "audit_20260721_ab12",
            SandboxCredentials(admin_password="strong-admin-password", user_password="strong-user-password"),
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_prepare_sandbox_refuses_real_database_before_schema_or_seed():
    cursor = LifecycleCursor(database_name="stock_research")
    connection = LifecycleConnection(cursor)

    with pytest.raises(RuntimeError, match="refusing non-test database"):
        prepare_sandbox(
            connection,
            "audit_20260721_ab12",
            SandboxCredentials(admin_password="strong-admin-password", user_password="strong-user-password"),
        )

    assert [query.strip() for query, _ in cursor.executed] == ["SELECT current_database()"]
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_cleanup_sandbox_uses_fk_safe_order_and_commits():
    cursor = LifecycleCursor()
    connection = LifecycleConnection(cursor)

    cleanup_sandbox(connection, "audit_20260721_ab12")

    delete_statements = [
        " ".join(query.split())
        for query, _ in cursor.executed
        if query.lstrip().startswith("DELETE")
    ]
    assert [
        statement.split(" WHERE ", 1)[0]
        for statement in delete_statements[:5]
    ] == [
        "DELETE FROM identity.user_session",
        "DELETE FROM identity.auth_audit_log",
        "DELETE FROM identity.user_account",
        "DELETE FROM ops.operator_decision_event",
        "DELETE FROM ops.operator_review_session",
    ]
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_cleanup_sandbox_rolls_back_on_error():
    cursor = LifecycleCursor(fail_on="DELETE FROM identity.user_account")
    connection = LifecycleConnection(cursor)

    with pytest.raises(RuntimeError, match="injected lifecycle failure"):
        cleanup_sandbox(connection, "audit_20260721_ab12")

    assert connection.commits == 0
    assert connection.rollbacks == 1
