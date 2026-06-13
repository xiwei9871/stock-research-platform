from __future__ import annotations

import asyncio
import inspect
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

NEWS_SCHEDULER_INTERVAL_SECONDS = 30 * 60
RefreshCallable = Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]]


def scheduler_enabled_from_env() -> bool:
    value = os.environ.get("DASHBOARD_PUBLIC_NEWS_SCHEDULER", "")
    return value.strip().lower() not in {"0", "false"}


class PublicNewsScheduler:
    def __init__(
        self,
        refresh: RefreshCallable,
        interval_seconds: int = NEWS_SCHEDULER_INTERVAL_SECONDS,
        enabled: bool = True,
    ) -> None:
        self.refresh = refresh
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self._lock = asyncio.Lock()
        self._running = False
        self._last_success_at = ""
        self._last_error = ""
        self._next_run_at = ""
        self._task: asyncio.Task[None] | None = None

    async def run_once(self) -> None:
        if not self.enabled or self._running:
            return

        self._running = True
        async with self._lock:
            completed = False
            try:
                result = self.refresh()
                if inspect.isawaitable(result):
                    await result
                now = self._now()
                self._last_success_at = now.isoformat()
                self._last_error = ""
                completed = True
            except Exception as exc:
                now = self._now()
                self._last_error = str(exc)
                completed = True
            finally:
                if completed:
                    self._next_run_at = (
                        now + timedelta(seconds=self.interval_seconds)
                    ).isoformat()
                self._running = False

    def start(self) -> None:
        if not self.enabled or self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self._running,
            "interval_seconds": self.interval_seconds,
            "last_success_at": self._last_success_at,
            "last_error": self._last_error,
            "next_run_at": self._next_run_at,
        }

    async def _run_loop(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self.interval_seconds)

    def _now(self) -> datetime:
        return datetime.now(UTC)
