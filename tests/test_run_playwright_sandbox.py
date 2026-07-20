import importlib.util
from pathlib import Path
import signal
import subprocess

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_playwright_sandbox.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_playwright_sandbox", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self, database_name="stock_research_e2e_test"):
        self.database_name = database_name
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return (self.database_name,)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class FakeConnection:
    def __init__(self, database_name="stock_research_e2e_test"):
        self.cursor_instance = FakeCursor(database_name)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, args, *, fail_immediately=False):
        self.args = args
        self.returncode = 1 if fail_immediately else None
        self.terminated = False
        self.killed = False
        self.wait_calls = []

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.returncode or 0


def test_runner_uses_array_commands_auth_test_service_and_cleans_after_playwright():
    runner = load_runner()
    connection = FakeConnection()
    processes = []
    command_calls = []
    observed = []

    def popen(args, **kwargs):
        assert isinstance(args, list)
        assert kwargs.get("shell") is not True
        process = FakeProcess(args)
        processes.append((process, kwargs))
        return process

    def run_command(args, **kwargs):
        assert isinstance(args, list)
        assert kwargs.get("shell") is not True
        command_calls.append((args, kwargs))
        observed.append("playwright")
        return subprocess.CompletedProcess(args, 7)

    original_cleanup = runner.cleanup_sandbox

    def cleanup(conn, run_id):
        observed.append("cleanup")
        return original_cleanup(conn, run_id)

    exit_code = runner.run_sandbox(
        service="stock_research_e2e_test",
        run_id="audit_20260721_ab12",
        connector=lambda **kwargs: connection,
        popen=popen,
        run_command=run_command,
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=cleanup,
        password_factory=lambda label: f"strong-{label}-password",
    )

    assert exit_code == 7
    assert observed == ["playwright", "cleanup"]
    assert connection.closed is True
    assert len(processes) == 2
    api_process, api_kwargs = processes[0]
    vite_process, vite_kwargs = processes[1]
    assert "uvicorn" in " ".join(api_process.args)
    assert vite_process.args[:3] == ["pnpm", "exec", "vite"]
    assert api_kwargs["env"]["STOCK_RESEARCH_SERVICE"] == "stock_research_e2e_test"
    assert api_kwargs["env"]["STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED"] == "true"
    assert api_kwargs["env"]["STOCK_RESEARCH_DASHBOARD_WRITE_GUARD"] == "true"
    assert api_kwargs["env"]["STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED"] == "false"
    playwright_args, playwright_kwargs = command_calls[0]
    assert playwright_args == ["pnpm", "test:e2e:sandbox"]
    assert playwright_kwargs["cwd"].name == "dashboard"
    assert playwright_kwargs["env"]["PLAYWRIGHT_REUSE_EXISTING"] == "true"
    assert playwright_kwargs["env"]["PLAYWRIGHT_SANDBOX_RUN_ID"] == "audit_20260721_ab12"
    assert playwright_kwargs["env"]["PLAYWRIGHT_SANDBOX_ADMIN_USERNAME"] == "e2e_audit_20260721_ab12_admin"
    assert playwright_kwargs["env"]["PLAYWRIGHT_SANDBOX_ADMIN_PASSWORD"] == "strong-admin-password"
    assert api_process.terminated is True
    assert vite_process.terminated is True


def test_runner_refuses_non_test_database_before_schema_seed_or_process_start():
    runner = load_runner()
    connection = FakeConnection(database_name="stock_research")
    starts = []

    with pytest.raises(RuntimeError, match="refusing non-test database"):
        runner.run_sandbox(
            service="stock_research_e2e_test",
            run_id="audit_20260721_ab12",
            connector=lambda **kwargs: connection,
            popen=lambda *args, **kwargs: starts.append((args, kwargs)),
            run_command=lambda *args, **kwargs: pytest.fail("playwright must not run"),
            wait_for_http=lambda *args, **kwargs: pytest.fail("servers must not start"),
            password_factory=lambda label: f"strong-{label}-password",
        )

    statements = [query.strip() for query, _ in connection.cursor_instance.executed]
    assert statements == ["SELECT current_database()"]
    assert starts == []
    assert connection.closed is True


def test_runner_cleans_up_after_playwright_timeout():
    runner = load_runner()
    connection = FakeConnection()
    observed = []

    def run_command(args, **kwargs):
        observed.append("timeout")
        raise subprocess.TimeoutExpired(args, timeout=kwargs["timeout"])

    original_cleanup = runner.cleanup_sandbox

    def cleanup(conn, run_id):
        observed.append("cleanup")
        return original_cleanup(conn, run_id)

    exit_code = runner.run_sandbox(
        service="stock_research_e2e_test",
        run_id="audit_20260721_ab12",
        connector=lambda **kwargs: connection,
        popen=lambda args, **kwargs: FakeProcess(args),
        run_command=run_command,
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=cleanup,
        password_factory=lambda label: f"strong-{label}-password",
    )

    assert exit_code == 124
    assert observed == ["timeout", "cleanup"]
    assert connection.closed is True


def test_runner_cleans_up_when_second_server_fails_to_start():
    runner = load_runner()
    connection = FakeConnection()
    processes = []
    observed = []

    def popen(args, **kwargs):
        process = FakeProcess(args, fail_immediately=len(processes) == 1)
        processes.append(process)
        return process

    original_cleanup = runner.cleanup_sandbox

    def cleanup(conn, run_id):
        observed.append("cleanup")
        return original_cleanup(conn, run_id)

    def wait_until_ready(url, process, **kwargs):
        if len(processes) == 1:
            return None
        return runner.wait_for_http(url, process, **kwargs)

    with pytest.raises(RuntimeError, match="server exited before readiness"):
        runner.run_sandbox(
            service="stock_research_e2e_test",
            run_id="audit_20260721_ab12",
            connector=lambda **kwargs: connection,
            popen=popen,
            run_command=lambda *args, **kwargs: pytest.fail("playwright must not run"),
            wait_for_http=wait_until_ready,
            cleanup=cleanup,
            password_factory=lambda label: f"strong-{label}-password",
            startup_timeout=0,
        )

    assert observed == ["cleanup"]
    assert processes[0].terminated is True
    assert connection.closed is True


def test_runner_cleans_up_when_interrupted_by_signal():
    runner = load_runner()
    connection = FakeConnection()
    observed = []

    def run_command(*args, **kwargs):
        observed.append("signal")
        raise KeyboardInterrupt

    original_cleanup = runner.cleanup_sandbox

    def cleanup(conn, run_id):
        observed.append("cleanup")
        return original_cleanup(conn, run_id)

    with pytest.raises(KeyboardInterrupt):
        runner.run_sandbox(
            service="stock_research_e2e_test",
            run_id="audit_20260721_ab12",
            connector=lambda **kwargs: connection,
            popen=lambda args, **kwargs: FakeProcess(args),
            run_command=run_command,
            wait_for_http=lambda *args, **kwargs: None,
            cleanup=cleanup,
            password_factory=lambda label: f"strong-{label}-password",
        )

    assert observed == ["signal", "cleanup"]
    assert connection.closed is True


def test_main_reports_missing_dedicated_service_without_fallback(monkeypatch, capsys):
    runner = load_runner()
    monkeypatch.setenv("PLAYWRIGHT_SANDBOX_SERVICE", "stock_research_e2e_test")

    def unavailable(**kwargs):
        assert kwargs["service"] == "stock_research_e2e_test"
        raise runner.psycopg.OperationalError(
            'definition of service "stock_research_e2e_test" not found'
        )

    monkeypatch.setattr(runner, "run_sandbox", unavailable)

    assert runner.main() == 2
    assert capsys.readouterr().err == (
        'playwright sandbox service unavailable: stock_research_e2e_test: '
        'definition of service "stock_research_e2e_test" not found\n'
    )


def test_main_converts_sigterm_to_cleanup_safe_exit(monkeypatch):
    runner = load_runner()
    handlers = {}
    restored = []

    def fake_signal(signum, handler):
        previous = f"previous-{signum}"
        if signum in handlers:
            restored.append((signum, handler))
        else:
            handlers[signum] = handler
        return previous

    monkeypatch.setattr(runner.signal, "signal", fake_signal)

    def interrupted(**kwargs):
        handlers[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(runner, "run_sandbox", interrupted)

    assert runner.main() == 128 + signal.SIGTERM
    assert [signum for signum, _ in restored] == [signal.SIGINT, signal.SIGTERM]
