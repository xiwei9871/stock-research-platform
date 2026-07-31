from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "support" / "theme_research_report_e2e_server.py"
SPEC = importlib.util.spec_from_file_location("theme_research_report_e2e_server", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
server = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server
SPEC.loader.exec_module(server)


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False
        self.executed: list[str] = []

    def rollback(self) -> None:
        self.executed.append("rollback")

    def execute(self, sql: str, _params=None) -> None:
        self.executed.append(sql)

    def commit(self) -> None:
        self.executed.append("commit")

    def close(self) -> None:
        self.closed = True


class NonTestConnection(FakeConnection):
    class Result:
        @staticmethod
        def fetchone():
            return ("stock_research",)

    def execute(self, sql: str, _params=None):
        self.executed.append(sql)
        return self.Result()


def test_cleanup_never_deletes_before_test_database_is_verified(monkeypatch, tmp_path: Path) -> None:
    connection = NonTestConnection()
    state = server.FixtureLifecycleState(connection=connection)
    monkeypatch.setattr(
        server,
        "_cleanup_database",
        lambda _connection: pytest.fail("unverified database must never be mutated"),
    )

    with pytest.raises(RuntimeError, match="refusing to run Playwright fixture against stock_research"):
        server._verify_test_database(state)
    errors = server._cleanup_fixture_resources(state, tmp_path)

    assert errors == []
    assert connection.closed is True
    assert not tmp_path.exists()


def test_cleanup_failure_preserves_outer_error_and_still_closes_and_removes_temp(
    monkeypatch,
    tmp_path: Path,
) -> None:
    connection = FakeConnection()
    state = server.FixtureLifecycleState(
        connection=connection,
        database_verified=True,
        lock_acquired=True,
        fixture_seed_started=True,
    )
    monkeypatch.setenv("PGSERVICEFILE", str(tmp_path / "pg_service.conf"))
    monkeypatch.setattr(server, "_cleanup_database", lambda _connection: (_ for _ in ()).throw(RuntimeError("cleanup failed")))
    original = RuntimeError("startup failed")

    caught = None
    cleanup_errors = []
    try:
        raise original
    except RuntimeError as exc:
        caught = exc
    finally:
        cleanup_errors = server._cleanup_fixture_resources(state, tmp_path)

    assert caught is original
    assert [str(error) for error in cleanup_errors] == ["cleanup failed"]
    assert connection.closed is True
    assert not tmp_path.exists()
    assert "PGSERVICEFILE" not in server.os.environ


def test_cleanup_does_not_delete_when_lock_was_acquired_but_seed_never_started(
    monkeypatch,
    tmp_path: Path,
) -> None:
    connection = FakeConnection()
    state = server.FixtureLifecycleState(
        connection=connection,
        database_verified=True,
        lock_acquired=True,
        fixture_seed_started=False,
    )
    monkeypatch.setattr(
        server,
        "_cleanup_database",
        lambda _connection: pytest.fail("fixture cleanup requires fixture_seed_started"),
    )

    server._cleanup_fixture_resources(state, tmp_path)

    assert connection.closed is True
    assert not tmp_path.exists()
