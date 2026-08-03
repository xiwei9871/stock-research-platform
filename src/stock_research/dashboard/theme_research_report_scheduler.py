from __future__ import annotations

import asyncio
import copy
import errno
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from os import PathLike
from typing import Any

from stock_research.dashboard.async_cleanup import await_task_resiliently
from stock_research.theme_research_report_index import (
    scan_theme_research_report_root,
)


ScanCallable = Callable[..., Any]
_RESOURCE_EXHAUSTION_ERRNOS = frozenset(
    value
    for name in ("EDQUOT", "EMFILE", "ENFILE", "ENOMEM", "ENOSPC")
    if (value := getattr(errno, name, None)) is not None
)
_SAFE_ERROR_FIELDS = ("code", "manifest_path", "theme_id", "version")


class ThemeResearchReportScheduler:
    def __init__(
        self,
        root: str | PathLike[str],
        limits: Any,
        service: str,
        interval_seconds: float,
        *,
        scan_fn: ScanCallable = scan_theme_research_report_root,
    ) -> None:
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or interval_seconds <= 0
        ):
            raise ValueError("interval_seconds must be greater than zero")
        self._root = root
        self._limits = limits
        self._service = service
        self._interval_seconds = float(interval_seconds)
        self._scan_fn = scan_fn
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._fatal = False
        self._last_result: dict[str, Any] | None = None
        self._last_started_at: str | None = None
        self._last_completed_at: str | None = None

    def start(self) -> None:
        task = self._task
        if task is not None and not task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._stop_event.set()
        try:
            await await_task_resiliently(task)
        finally:
            if task.done() and self._task is task:
                self._task = None

    async def run_once(self) -> None:
        async with self._lock:
            self._running = True
            self._last_started_at = _now()
            try:
                worker = asyncio.create_task(
                    asyncio.to_thread(
                        self._scan_fn,
                        self._root,
                        limits=self._limits,
                        service=self._service,
                    )
                )
                result = await await_task_resiliently(worker)
                self._last_result = _safe_scan_result(result)
                self._fatal = False
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                if _is_fatal_resource_error(exc):
                    self._last_result = {
                        "error_code": "THEME_REPORT_SCAN_RESOURCE_EXHAUSTED"
                    }
                    self._fatal = True
                elif isinstance(exc, Exception):
                    self._last_result = {"error_code": "THEME_REPORT_SCAN_FAILED"}
                    self._fatal = False
                else:
                    raise
            finally:
                self._last_completed_at = _now()
                self._running = False

    def diagnostics(self) -> dict[str, Any]:
        if self._running:
            status = "running"
        elif self._fatal:
            status = "fatal"
        elif self._last_result is None:
            status = "never_run"
        elif self._last_result.get("error_code"):
            status = "error"
        else:
            status = "ok"
        return {
            "status": status,
            "running": self._running,
            "last_started_at": self._last_started_at,
            "last_completed_at": self._last_completed_at,
            "last_result": copy.deepcopy(self._last_result),
        }

    async def _run_loop(self) -> None:
        current = asyncio.current_task()
        try:
            while not self._stop_event.is_set():
                await self.run_once()
                if self._fatal or self._stop_event.is_set():
                    return
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self._interval_seconds
                    )
                except TimeoutError:
                    pass
        finally:
            if self._task is current:
                self._task = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_scan_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        result = result.to_dict()
    if not isinstance(result, Mapping):
        raise ValueError("scan result must be a mapping")
    safe: dict[str, Any] = {}
    for field in ("discovered", "indexed", "unchanged", "invalid"):
        value = result.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("scan counters must be non-negative integers")
        safe[field] = value
    errors = result.get("errors")
    if not isinstance(errors, (list, tuple)):
        raise ValueError("scan errors must be a sequence")
    safe_errors: list[dict[str, str]] = []
    for error in errors[:100]:
        if not isinstance(error, Mapping):
            continue
        detached = {
            field: value
            for field in _SAFE_ERROR_FIELDS
            if isinstance((value := error.get(field)), str)
        }
        if "code" in detached:
            safe_errors.append(detached)
    safe["errors"] = safe_errors
    for field in ("started_at", "completed_at"):
        value = result.get(field)
        safe[field] = value if isinstance(value, str) else None
    for field in ("root_exists", "root_readable"):
        value = result.get(field)
        if not isinstance(value, bool):
            raise ValueError("scan root health flags must be booleans")
        safe[field] = value
    error_code = result.get("error_code")
    if error_code is not None and (
        not isinstance(error_code, str) or not error_code
    ):
        raise ValueError("scan error_code must be a non-empty string or None")
    safe["error_code"] = error_code
    return safe


def _is_fatal_resource_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, MemoryError):
            return True
        if isinstance(current, OSError) and current.errno in _RESOURCE_EXHAUSTION_ERRNOS:
            return True
        current = current.__cause__ or current.__context__
    return False


__all__ = ["ThemeResearchReportScheduler"]
