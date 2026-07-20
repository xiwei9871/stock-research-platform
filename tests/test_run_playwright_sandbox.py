import importlib.util
import json
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
    next_pid = 41000

    def __init__(
        self,
        args,
        *,
        fail_immediately=False,
        completion_returncode=0,
        communicate_error=None,
        communicate_callback=None,
    ):
        self.args = args
        self.returncode = 1 if fail_immediately else None
        self.completion_returncode = completion_returncode
        self.communicate_error = communicate_error
        self.communicate_callback = communicate_callback
        self.terminated = False
        self.killed = False
        self.wait_calls = []
        self.pid = FakeProcess.next_pid
        FakeProcess.next_pid += 1

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

    def communicate(self, timeout=None):
        if self.communicate_callback is not None:
            self.communicate_callback()
        if self.communicate_error is not None:
            raise self.communicate_error
        self.returncode = self.completion_returncode
        return (None, None)


def stop_fake_process(process):
    if process is None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_runner_uses_array_commands_auth_test_service_and_cleans_after_playwright():
    runner = load_runner()
    connection = FakeConnection()
    processes = []
    observed = []

    def popen(args, **kwargs):
        assert isinstance(args, list)
        assert kwargs.get("shell") is not True
        is_playwright = args == ["pnpm", "test:e2e:sandbox"]
        process = FakeProcess(
            args,
            completion_returncode=7 if is_playwright else 0,
            communicate_callback=(lambda: observed.append("playwright")) if is_playwright else None,
        )
        processes.append((process, kwargs))
        return process

    original_cleanup = runner.cleanup_sandbox

    def cleanup(conn, run_id):
        observed.append("cleanup")
        return original_cleanup(conn, run_id)

    exit_code = runner.run_sandbox(
        service="stock_research_e2e_test",
        run_id="audit_20260721_ab12",
        connector=lambda **kwargs: connection,
        popen=popen,
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=cleanup,
        password_factory=lambda label: f"strong-{label}-password",
        port_checker=lambda **kwargs: None,
        process_stopper=lambda process: (
            observed.append(
                "stop:playwright"
                if process.args == ["pnpm", "test:e2e:sandbox"]
                else "stop:vite"
                if process.args[:3] == ["pnpm", "exec", "vite"]
                else "stop:api"
            ),
            stop_fake_process(process),
        )[-1],
    )

    assert exit_code == 7
    assert observed == [
        "playwright",
        "stop:playwright",
        "stop:vite",
        "stop:api",
        "cleanup",
    ]
    assert connection.closed is True
    assert len(processes) == 3
    api_process, api_kwargs = processes[0]
    vite_process, vite_kwargs = processes[1]
    playwright_process, playwright_kwargs = processes[2]
    assert "uvicorn" in " ".join(api_process.args)
    assert vite_process.args[:3] == ["pnpm", "exec", "vite"]
    assert "--strictPort" in vite_process.args
    assert playwright_process.args == ["pnpm", "test:e2e:sandbox"]
    assert all(kwargs["start_new_session"] is True for _, kwargs in processes)
    assert api_kwargs["env"]["STOCK_RESEARCH_SERVICE"] == "stock_research_e2e_test"
    assert api_kwargs["env"]["STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED"] == "true"
    assert api_kwargs["env"]["STOCK_RESEARCH_DASHBOARD_WRITE_GUARD"] == "true"
    assert api_kwargs["env"]["STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED"] == "false"
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
            wait_for_http=lambda *args, **kwargs: pytest.fail("servers must not start"),
            password_factory=lambda label: f"strong-{label}-password",
            port_checker=lambda **kwargs: None,
            process_stopper=stop_fake_process,
        )

    statements = [query.strip() for query, _ in connection.cursor_instance.executed]
    assert statements == ["SELECT current_database()"]
    assert starts == []
    assert connection.closed is True


def test_runner_cleans_up_after_playwright_timeout():
    runner = load_runner()
    connection = FakeConnection()
    observed = []

    def popen(args, **kwargs):
        if args == ["pnpm", "test:e2e:sandbox"]:
            return FakeProcess(
                args,
                communicate_error=subprocess.TimeoutExpired(args, timeout=900),
                communicate_callback=lambda: observed.append("timeout"),
            )
        return FakeProcess(args)

    original_cleanup = runner.cleanup_sandbox

    def cleanup(conn, run_id):
        observed.append("cleanup")
        return original_cleanup(conn, run_id)

    exit_code = runner.run_sandbox(
        service="stock_research_e2e_test",
        run_id="audit_20260721_ab12",
        connector=lambda **kwargs: connection,
        popen=popen,
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=cleanup,
        password_factory=lambda label: f"strong-{label}-password",
        port_checker=lambda **kwargs: None,
        process_stopper=stop_fake_process,
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
            wait_for_http=wait_until_ready,
            cleanup=cleanup,
            password_factory=lambda label: f"strong-{label}-password",
            startup_timeout=0,
            port_checker=lambda **kwargs: None,
            process_stopper=stop_fake_process,
        )

    assert observed == ["cleanup"]
    assert processes[0].terminated is True
    assert connection.closed is True


def test_runner_cleans_up_when_interrupted_by_signal():
    runner = load_runner()
    connection = FakeConnection()
    observed = []

    def popen(args, **kwargs):
        if args == ["pnpm", "test:e2e:sandbox"]:
            return FakeProcess(
                args,
                communicate_error=KeyboardInterrupt(),
                communicate_callback=lambda: observed.append("signal"),
            )
        return FakeProcess(args)

    original_cleanup = runner.cleanup_sandbox

    def cleanup(conn, run_id):
        observed.append("cleanup")
        return original_cleanup(conn, run_id)

    with pytest.raises(KeyboardInterrupt):
        runner.run_sandbox(
            service="stock_research_e2e_test",
            run_id="audit_20260721_ab12",
            connector=lambda **kwargs: connection,
            popen=popen,
            wait_for_http=lambda *args, **kwargs: None,
            cleanup=cleanup,
            password_factory=lambda label: f"strong-{label}-password",
            port_checker=lambda **kwargs: None,
            process_stopper=stop_fake_process,
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
    [(1, "terminate"), (0, "wait"), (2, "kill")],
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
        is_playwright = args == ["pnpm", "test:e2e:sandbox"]
        process = (
            FaultProcess(args, fault=fault)
            if len(processes) == faulty_process_index
            else FakeProcess(args, completion_returncode=0 if is_playwright else 0)
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
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=cleanup,
        password_factory=lambda label: f"strong-{label}-password",
        port_checker=lambda **kwargs: None,
        process_stopper=stop_fake_process,
    )

    assert exit_code == 1
    assert observed == ["cleanup"]
    assert connection.closed is True
    assert all(
        process.terminated
        for index, process in enumerate(processes)
        if index != faulty_process_index
    )
    lifecycle_log = capsys.readouterr().err
    faulty_label = ["api", "vite", "playwright"][faulty_process_index]
    assert f"stop_{faulty_label}: RuntimeError" in lifecycle_log
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
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=cleanup,
        password_factory=lambda label: f"strong-{label}-password",
        port_checker=lambda **kwargs: None,
        process_stopper=stop_fake_process,
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
            popen=lambda args, **kwargs: (
                (_ for _ in ()).throw(primary)
                if args == ["pnpm", "test:e2e:sandbox"]
                else popen(args, **kwargs)
            ),
            wait_for_http=lambda *args, **kwargs: None,
            cleanup=cleanup,
            password_factory=lambda label: f"strong-{label}-password",
            port_checker=lambda **kwargs: None,
            process_stopper=stop_fake_process,
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
        popen=lambda args, **kwargs: FakeProcess(
            args,
            completion_returncode=7 if args == ["pnpm", "test:e2e:sandbox"] else 0,
        ),
        wait_for_http=lambda *args, **kwargs: None,
        cleanup=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("secret cleanup detail")
        ),
        password_factory=lambda label: f"strong-{label}-password",
        port_checker=lambda **kwargs: None,
        process_stopper=stop_fake_process,
    )

    assert exit_code == 7
    assert "secret" not in capsys.readouterr().err


class FakeHttpResponse:
    def __init__(self, status, body, headers=None):
        self.status = status
        self.body = body.encode("utf-8")
        self.headers = headers or {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


def test_api_readiness_requires_2xx_openapi_json_and_live_process():
    runner = load_runner()
    process = FakeProcess(["api"])
    response = FakeHttpResponse(
        200,
        json.dumps({"openapi": "3.1.0", "info": {"title": "Stock Research Dashboard API"}}),
    )

    runner.wait_for_http(
        "http://127.0.0.1:8866/openapi.json",
        process,
        timeout=0,
        readiness="api",
        opener=lambda *args, **kwargs: response,
    )


@pytest.mark.parametrize(
    "response",
    [
        FakeHttpResponse(404, '{"detail":"not found"}'),
        FakeHttpResponse(200, '{"status":"ok"}'),
        FakeHttpResponse(200, '{"openapi":"3.1.0","info":{"title":"Other API"}}'),
    ],
)
def test_api_readiness_rejects_404_and_unrecognized_json(response):
    runner = load_runner()

    with pytest.raises(TimeoutError, match="server readiness timed out"):
        runner.wait_for_http(
            "http://127.0.0.1:8866/openapi.json",
            FakeProcess(["api"]),
            timeout=0,
            readiness="api",
            opener=lambda *args, **kwargs: response,
        )


def test_vite_readiness_requires_200_and_dashboard_page_fingerprint():
    runner = load_runner()
    valid = FakeHttpResponse(
        200,
        '<title>Stock Research Dashboard</title><div id="root"></div>',
    )

    runner.wait_for_http(
        "http://127.0.0.1:5274/",
        FakeProcess(["vite"]),
        timeout=0,
        readiness="vite",
        opener=lambda *args, **kwargs: valid,
    )

    with pytest.raises(TimeoutError, match="server readiness timed out"):
        runner.wait_for_http(
            "http://127.0.0.1:5274/",
            FakeProcess(["vite"]),
            timeout=0,
            readiness="vite",
            opener=lambda *args, **kwargs: FakeHttpResponse(200, "unrelated page"),
        )


def test_stop_process_group_terms_then_kills_group_and_waits_direct_child(monkeypatch):
    runner = load_runner()
    events = []

    class GroupProcess:
        pid = 43210

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            if timeout == 10:
                raise subprocess.TimeoutExpired(["group"], timeout=timeout)
            return -9

    def killpg(pgid, signum):
        events.append(("killpg", pgid, signum))

    monkeypatch.setattr(runner.os, "killpg", killpg)

    runner._stop_process_group(GroupProcess())

    assert events == [
        ("killpg", 43210, signal.SIGTERM),
        ("wait", 10),
        ("killpg", 43210, signal.SIGKILL),
        ("wait", 5),
    ]


def test_stop_process_group_treats_missing_group_as_safe_and_reaps_child(monkeypatch):
    runner = load_runner()
    events = []

    class ExitedProcess:
        pid = 43211

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            return 0

    def missing_group(pgid, signum):
        events.append(("killpg", pgid, signum))
        raise ProcessLookupError

    monkeypatch.setattr(runner.os, "killpg", missing_group)

    runner._stop_process_group(ExitedProcess())

    assert events == [
        ("killpg", 43211, signal.SIGTERM),
        ("wait", 10),
    ]
