from __future__ import annotations

import copy
import os
import time
from collections.abc import Callable, Hashable
from threading import Lock
from typing import Any


DEFAULT_DASHBOARD_EOD_CACHE_TTL_SECONDS = 300.0


def dashboard_eod_cache_ttl_seconds() -> float:
    raw_value = os.environ.get("DASHBOARD_EOD_CACHE_TTL_SECONDS", "")
    if not raw_value:
        return DEFAULT_DASHBOARD_EOD_CACHE_TTL_SECONDS
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return DEFAULT_DASHBOARD_EOD_CACHE_TTL_SECONDS


class DashboardResponseCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_DASHBOARD_EOD_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock
        self._entries: dict[tuple[Hashable, ...], tuple[float, Any]] = {}
        self._lock = Lock()

    def get_or_set(self, key: tuple[Hashable, ...], loader: Callable[[], Any]) -> Any:
        if self.ttl_seconds <= 0:
            return loader()

        now = self._clock()
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                expires_at, payload = cached
                if expires_at > now:
                    return copy.deepcopy(payload)
                self._entries.pop(key, None)

        payload = loader()
        expires_at = self._clock() + self.ttl_seconds
        with self._lock:
            self._entries[key] = (expires_at, copy.deepcopy(payload))
        return payload

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
