import pytest

from stock_research.playwright_sandbox import (
    assert_sandbox_database,
    load_sandbox_database_name,
)


class FakeCursor:
    def __init__(self, row=("stock_research_e2e_test",), error=None):
        self.row = row
        self.error = error
        self.executed = []
        self.closed = False

    def execute(self, query):
        self.executed.append(query)
        if self.error is not None:
            raise self.error

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def test_load_sandbox_database_name_queries_actual_database_and_closes_resources():
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    connect_calls = []

    def connector(dsn):
        connect_calls.append(dsn)
        return connection

    database_name = load_sandbox_database_name(
        "stock_research_e2e_test", connector=connector
    )

    assert database_name == "stock_research_e2e_test"
    assert connect_calls == ["service=stock_research_e2e_test"]
    assert cursor.executed == ["SELECT current_database()"]
    assert cursor.closed is True
    assert connection.closed is True


def test_load_sandbox_database_name_propagates_query_error_and_closes_resources():
    database_error = RuntimeError("database unavailable")
    cursor = FakeCursor(error=database_error)
    connection = FakeConnection(cursor)

    with pytest.raises(RuntimeError, match="database unavailable") as error:
        load_sandbox_database_name(
            "stock_research_e2e_test", connector=lambda _: connection
        )

    assert error.value is database_error
    assert cursor.closed is True
    assert connection.closed is True


def test_load_sandbox_database_name_fails_closed_when_query_returns_no_row():
    cursor = FakeCursor(row=None)
    connection = FakeConnection(cursor)

    with pytest.raises(RuntimeError, match="could not determine sandbox database"):
        load_sandbox_database_name(
            "stock_research_e2e_test", connector=lambda _: connection
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
        "stock_research_e2e_test", connector=lambda _: connection
    )

    with pytest.raises(RuntimeError, match="refusing non-test database"):
        assert_sandbox_database(database_name)
