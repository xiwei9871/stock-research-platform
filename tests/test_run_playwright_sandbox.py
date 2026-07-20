import importlib.util
from pathlib import Path
import signal
import socket
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
    def __init__(self, database_name="stock_research_e2e_test", *, close_error=None):
        self.cursor_instance = FakeCursor(database_name)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.close_error = close_error

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


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
        port_checker=lambda **kwargs: None,
    )

    assert exit_code == 7
    assert observed == ["playwright", "cleanup"]
    assert connection.closed is True
    assert len(processes) == 2
    api_process, api_kwargs = processes[0]
    vite_process, vite_kwargs = processes[1]
    assert "uvicorn" in " ".join(api_process.args)
    assert vite_process.args[:3] == ["pnpm", "exec", "vite"]
    assert "--strictPort" in vite_process.args
    assert api_kwargs["env"]["STOCK_RESEARCH_SERVICE"] == "stock_research_e2e_test"
    assert api_kwargs["env"]["STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED"] == "true"
    assert api_kwargs["env"]["STOCK_RESEARCH_DASHBOARD_WRITE_GUARD"] == "true"
    assert api_kwargs["env"]["STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED"] == "false"
    playwright_args, playwright_kwargs = command_calls[0]
    assert playwright_args == ["pnpm", "test:e2e:sandbox"]
    assert playwright_kwargs["cwd"].name == "dashboard"
    assert playwright_kwargs["env"]["PLAYWRIGHT_REUSE_EXISTING"] == "false"
    assert playwright_kwargs["env"]["PLAYWRIGHT_EXTERNAL_SERVERS"] == "true"
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
            port_checker=lambda **kwargs: None,
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
        port_checker=lambda **kwargs: None,
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
            port_checker=lambda **kwargs: None,
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
            port_checker=lambda **kwargs: None,
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


def test_port_preflight_rejects_an_occupied_port():
    runner = load_runner()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    occupied_port = listener.getsockname()[1]
    try:
        with pytest.raises(RuntimeError, match=f"sandbox port unavailable: {occupied_port}"):
            runner.check_ports_available(
                dashboard_port=occupied_port,
                api_port=occupied_port + 1,
            )
    finally:
        listener.close()


def test_runner_port_preflight_fails_before_database_or_existing_server_use():
    runner = load_runner()
    observed = []

    with pytest.raises(RuntimeError, match="sandbox port unavailable"):
        runner.run_sandbox(
            service="stock_research_e2e_test",
            run_id="audit_20260721_ab12",
            connector=lambda **kwargs: observed.append("connect"),
            popen=lambda *args, **kwargs: observed.append("popen"),
            run_command=lambda *args, **kwargs: observed.append("playwright"),
            port_checker=lambda **kwargs: (_ for _ in ()).throw(
                RuntimeError("sandbox port unavailable: 5274")
            ),
        )

    assert observed == []


class FaultProcess(FakeProcess):
    def __init__(self, args, *, fault):
        super().__init__(args)
        self.fault = fault
        self.stop_attempted = []

    def terminate(self):
        self.stop_attempted.append("terminate")
        if self.fault == "terminate":
            raise RuntimeError("secret terminate detail")
        self.terminated = True
        if self.fault not in {"wait", "kill"}:
            self.returncode = 0

    def wait(self, timeout=None):
        self.stop_attempted.append("wait")
        if self.fault == "wait":
            raise RuntimeError("secret wait detail")
        if self.fault == "kill" and not self.killed:
            raise subprocess.TimeoutExpired(self.args, timeout=timeout)
        return self.returncode or 0

    def kill(self):
        self.stop_attempted.append("kill")
        if self.fault == "kill":
            raise RuntimeError("secret kill detail")
        super().kill()


@pytest.mark.parametrize(
    ("faulty_process_index", "fault"),
    [(1, "terminate"), (0, "wait"), (1, "kill")],
)
def test_runner_resource_stop_errors_do_not_skip_other_stop_cleanup_or_close(
    faulty_process_index,
    fault,
    capsys,
):
    runner = load_runner()
    connection = FakeConnection()
    processes = []
    observed = []

    def popen(args, **kwargs):
        process = (
            FaultProcess(args, fault=fault)
            if len(processes) == faulty_process_index
            else FakeProcess(args)
        )
        processes.append(process)
        return process

    def cleanup(conn, run_id):
        observed.append("cleanup")

    exit_code = runner.run_sandbox(
        service="stock_research_e2e_test",
        run_id="audit_20260721_ab12",
        connector=lambda **kwargs: connection,
        popen=popen,
        run_command=lambda *args, **kwargs: subprocess.CompletedProcess(args, 0),
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=cleanup,
        password_factory=lambda label: f"strong-{label}-password",
        port_checker=lambda **kwargs: None,
    )

    assert exit_code == 1
    assert observed == ["cleanup"]
    assert connection.closed is True
    assert processes[1 - faulty_process_index].terminated is True
    lifecycle_log = capsys.readouterr().err
    assert f"stop_{'api' if faulty_process_index == 0 else 'vite'}: RuntimeError" in lifecycle_log
    assert "secret" not in lifecycle_log


@pytest.mark.parametrize("failure", ["cleanup", "close"])
def test_runner_cleanup_and_close_errors_are_independent_and_make_success_nonzero(
    failure,
    capsys,
):
    runner = load_runner()
    connection = FakeConnection(
        close_error=RuntimeError("secret close detail") if failure == "close" else None
    )
    observed = []

    def cleanup(conn, run_id):
        observed.append("cleanup")
        if failure == "cleanup":
            raise RuntimeError("secret cleanup detail")

    exit_code = runner.run_sandbox(
        service="stock_research_e2e_test",
        run_id="audit_20260721_ab12",
        connector=lambda **kwargs: connection,
        popen=lambda args, **kwargs: FakeProcess(args),
        run_command=lambda *args, **kwargs: subprocess.CompletedProcess(args, 0),
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=cleanup,
        password_factory=lambda label: f"strong-{label}-password",
        port_checker=lambda **kwargs: None,
    )

    assert exit_code == 1
    assert observed == ["cleanup"]
    assert connection.closed is True
    lifecycle_log = capsys.readouterr().err
    assert f"{failure}: RuntimeError" in lifecycle_log
    assert "secret" not in lifecycle_log


def test_runner_preserves_primary_error_while_all_cleanup_layers_run(capsys):
    runner = load_runner()
    connection = FakeConnection(close_error=RuntimeError("secret close detail"))
    processes = []
    observed = []
    primary = ValueError("primary journey failure")

    def popen(args, **kwargs):
        process = FaultProcess(args, fault="terminate") if len(processes) == 1 else FakeProcess(args)
        processes.append(process)
        return process

    def cleanup(conn, run_id):
        observed.append("cleanup")
        raise RuntimeError("secret cleanup detail")

    with pytest.raises(ValueError, match="primary journey failure") as error:
        runner.run_sandbox(
            service="stock_research_e2e_test",
            run_id="audit_20260721_ab12",
            connector=lambda **kwargs: connection,
            popen=popen,
            run_command=lambda *args, **kwargs: (_ for _ in ()).throw(primary),
            wait_for_http=lambda *args, **kwargs: None,
            cleanup=cleanup,
            password_factory=lambda label: f"strong-{label}-password",
            port_checker=lambda **kwargs: None,
        )

    assert error.value is primary
    assert observed == ["cleanup"]
    assert processes[0].terminated is True
    assert connection.closed is True
    assert error.value.__notes__ == [
        "sandbox lifecycle failure: stop_vite: RuntimeError",
        "sandbox lifecycle failure: cleanup: RuntimeError",
        "sandbox lifecycle failure: close: RuntimeError",
    ]
    assert "secret" not in capsys.readouterr().err


def test_runner_keeps_existing_nonzero_playwright_code_when_cleanup_fails(capsys):
    runner = load_runner()
    connection = FakeConnection()

    exit_code = runner.run_sandbox(
        service="stock_research_e2e_test",
        run_id="audit_20260721_ab12",
        connector=lambda **kwargs: connection,
        popen=lambda args, **kwargs: FakeProcess(args),
        run_command=lambda *args, **kwargs: subprocess.CompletedProcess(args, 7),
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("secret cleanup detail")
        ),
        password_factory=lambda label: f"strong-{label}-password",
        port_checker=lambda **kwargs: None,
    )

    assert exit_code == 7
    assert "secret" not in capsys.readouterr().err
