#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import psycopg

from stock_research.playwright_sandbox import (
    SandboxCredentials,
    cleanup_sandbox,
    prepare_sandbox,
)


DEFAULT_SERVICE = "stock_research_e2e_test"
DEFAULT_DASHBOARD_PORT = 5274
DEFAULT_API_PORT = 8866


class SandboxSignalInterrupt(BaseException):
    def __init__(self, signum: int):
        super().__init__(f"sandbox interrupted by signal {signum}")
        self.signum = signum


def wait_for_http(
    url: str,
    process: Any,
    *,
    timeout: float = 120.0,
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(f"server exited before readiness: {url} (exit {return_code})")
        try:
            with urlopen(url, timeout=1.0) as response:
                if response.status < 500:
                    return
        except (OSError, URLError):
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError(f"server readiness timed out: {url}")
        time.sleep(0.1)


def check_ports_available(*, dashboard_port: int, api_port: int) -> None:
    for port in dict.fromkeys((dashboard_port, api_port)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
                candidate.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"sandbox port unavailable: {port}") from exc


def _stop_process(process: Any) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run_lifecycle_step(
    errors: list[tuple[str, BaseException]],
    label: str,
    action: Callable[[], None],
) -> None:
    try:
        action()
    except BaseException as exc:
        errors.append((label, exc))


def _report_lifecycle_errors(errors: list[tuple[str, BaseException]]) -> None:
    for label, error in errors:
        print(
            f"playwright sandbox lifecycle error: {label}: {type(error).__name__}",
            file=sys.stderr,
        )


def _default_password_factory(label: str) -> str:
    return f"Pw-{label}-{secrets.token_urlsafe(24)}"


def _new_run_id() -> str:
    return f"audit_{time.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"


def run_sandbox(
    *,
    service: str,
    run_id: str | None = None,
    connector: Callable[..., Any] = psycopg.connect,
    popen: Callable[..., Any] = subprocess.Popen,
    run_command: Callable[..., Any] = subprocess.run,
    wait_for_http: Callable[..., None] = wait_for_http,
    port_checker: Callable[..., None] = check_ports_available,
    cleanup: Callable[[Any, str], None] = cleanup_sandbox,
    password_factory: Callable[[str], str] = _default_password_factory,
    dashboard_port: int = DEFAULT_DASHBOARD_PORT,
    api_port: int = DEFAULT_API_PORT,
    startup_timeout: float = 120.0,
    playwright_timeout: float = 900.0,
) -> int:
    selected_run_id = run_id or _new_run_id()
    port_checker(dashboard_port=dashboard_port, api_port=api_port)
    connection = connector(service=service)
    api_process = None
    vite_process = None
    prepared = False
    exit_code = 1
    primary_error: BaseException | None = None
    try:
        admin_password = password_factory("admin")
        seeded_user_password = password_factory("user")
        created_initial_password = password_factory("created-initial")
        created_reset_password = password_factory("created-reset")
        write_token = password_factory("write-token")
        seed = prepare_sandbox(
            connection,
            selected_run_id,
            SandboxCredentials(
                admin_password=admin_password,
                user_password=seeded_user_password,
            ),
        )
        prepared = True

        base_env = os.environ.copy()
        api_env = {
            **base_env,
            "PYTHONPATH": str(SRC_ROOT),
            "STOCK_RESEARCH_SERVICE": service,
            "STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED": "true",
            "STOCK_RESEARCH_DASHBOARD_WRITE_GUARD": "true",
            "STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN": write_token,
            "STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED": "false",
        }
        api_process = popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "stock_research.dashboard.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            cwd=REPO_ROOT,
            env=api_env,
        )
        wait_for_http(
            f"http://127.0.0.1:{api_port}/openapi.json",
            api_process,
            timeout=startup_timeout,
        )

        vite_env = {
            **base_env,
            "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{api_port}",
        }
        vite_process = popen(
            [
                "pnpm",
                "exec",
                "vite",
                "--host",
                "127.0.0.1",
                "--port",
                str(dashboard_port),
                "--strictPort",
            ],
            cwd=REPO_ROOT / "dashboard",
            env=vite_env,
        )
        wait_for_http(
            f"http://127.0.0.1:{dashboard_port}/",
            vite_process,
            timeout=startup_timeout,
        )

        playwright_env = {
            **base_env,
            "PLAYWRIGHT_REUSE_EXISTING": "false",
            "PLAYWRIGHT_EXTERNAL_SERVERS": "true",
            "PLAYWRIGHT_DASHBOARD_PORT": str(dashboard_port),
            "PLAYWRIGHT_API_PORT": str(api_port),
            "PLAYWRIGHT_SANDBOX_SERVICE": service,
            "PLAYWRIGHT_SANDBOX_RUN_ID": seed.run_id,
            "PLAYWRIGHT_SANDBOX_ADMIN_USERNAME": seed.admin_username,
            "PLAYWRIGHT_SANDBOX_ADMIN_PASSWORD": admin_password,
            "PLAYWRIGHT_SANDBOX_USER_USERNAME": seed.user_username,
            "PLAYWRIGHT_SANDBOX_USER_PASSWORD": seeded_user_password,
            "PLAYWRIGHT_SANDBOX_CREATED_USERNAME": seed.created_username,
            "PLAYWRIGHT_SANDBOX_CREATED_INITIAL_PASSWORD": created_initial_password,
            "PLAYWRIGHT_SANDBOX_CREATED_RESET_PASSWORD": created_reset_password,
            "PLAYWRIGHT_SANDBOX_WRITE_TOKEN": write_token,
            "PLAYWRIGHT_SANDBOX_ASSET_ID": seed.asset_id,
            "PLAYWRIGHT_SANDBOX_TRADE_DATE": seed.trade_date,
            "PLAYWRIGHT_SANDBOX_OPERATOR_EVENT_ID": seed.operator_event_id,
        }
        try:
            completed = run_command(
                ["pnpm", "test:e2e:sandbox"],
                cwd=REPO_ROOT / "dashboard",
                env=playwright_env,
                timeout=playwright_timeout,
                check=False,
            )
            exit_code = int(completed.returncode)
        except subprocess.TimeoutExpired:
            exit_code = 124
    except BaseException as exc:
        primary_error = exc
    finally:
        lifecycle_errors: list[tuple[str, BaseException]] = []
        _run_lifecycle_step(
            lifecycle_errors,
            "stop_vite",
            lambda: _stop_process(vite_process),
        )
        _run_lifecycle_step(
            lifecycle_errors,
            "stop_api",
            lambda: _stop_process(api_process),
        )
        if prepared:
            _run_lifecycle_step(
                lifecycle_errors,
                "cleanup",
                lambda: cleanup(connection, selected_run_id),
            )
        _run_lifecycle_step(lifecycle_errors, "close", connection.close)
        _report_lifecycle_errors(lifecycle_errors)

    if primary_error is not None:
        for label, error in lifecycle_errors:
            primary_error.add_note(
                f"sandbox lifecycle failure: {label}: {type(error).__name__}"
            )
        raise primary_error

    signal_error = next(
        (
            error
            for _, error in lifecycle_errors
            if isinstance(error, (SandboxSignalInterrupt, KeyboardInterrupt))
        ),
        None,
    )
    if signal_error is not None:
        raise signal_error
    if lifecycle_errors and exit_code == 0:
        return 1
    return exit_code


def main() -> int:
    service = os.environ.get("PLAYWRIGHT_SANDBOX_SERVICE", DEFAULT_SERVICE).strip()
    if not service:
        service = DEFAULT_SERVICE
    run_id = os.environ.get("PLAYWRIGHT_SANDBOX_RUN_ID", "").strip() or None
    previous_handlers = {}

    def interrupt(signum: int, _frame: Any) -> None:
        raise SandboxSignalInterrupt(signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, interrupt)
    try:
        try:
            return run_sandbox(service=service, run_id=run_id)
        except SandboxSignalInterrupt as exc:
            return 128 + exc.signum
        except psycopg.OperationalError as exc:
            print(
                f"playwright sandbox service unavailable: {service}: {exc}",
                file=sys.stderr,
            )
            return 2
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
