import pytest

import stock_research.playwright_sandbox as playwright_sandbox
from stock_research.playwright_sandbox import (
    assert_sandbox_database,
    load_sandbox_database_name,
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
