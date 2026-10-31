from __future__ import annotations

import sys
from pathlib import Path


def _ensure_local_watchdog_runner_importable() -> None:
    try:
        import watchdog_runner.backfill  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    local_src = Path("/Users/xiwei/watchdog/src")
    if local_src.exists():
        sys.path.insert(0, str(local_src))


_ensure_local_watchdog_runner_importable()

from watchdog_runner.backfill import (  # noqa: E402
    BackfillSummary,
    BackfillWatchdogAdapter,
    BackfillWatchdogStatus,
    build_watchdog_status,
    format_watchdog_message,
    run_watchdog_once,
)

try:  # noqa: E402
    from watchdog_runner.backfill import should_send_watchdog_message
except ImportError:  # watchdog_runner builds lacking the helper: notify on non-healthy
    def should_send_watchdog_message(status: BackfillWatchdogStatus) -> bool:
        return status.watchdog_action != "healthy"


__all__ = [
    "BackfillSummary",
    "BackfillWatchdogAdapter",
    "BackfillWatchdogStatus",
    "build_watchdog_status",
    "format_watchdog_message",
    "run_watchdog_once",
    "should_send_watchdog_message",
]
