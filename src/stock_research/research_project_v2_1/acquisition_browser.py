from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class BrowserRuntimeStatus:
    available: bool
    engine: str | None
    failure_code: str | None
    diagnostic_summary: str


def _default_probe() -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.is_file():
            raise RuntimeError("browser executable unavailable")
    return "chromium"


def detect_browser_runtime(
    *, probe: Callable[[], str] | None = None
) -> BrowserRuntimeStatus:
    try:
        engine = (probe or _default_probe)()
        if not isinstance(engine, str) or not engine:
            raise RuntimeError("invalid browser engine")
        return BrowserRuntimeStatus(
            available=True,
            engine=engine,
            failure_code=None,
            diagnostic_summary="Optional browser runtime is available.",
        )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except Exception:
        return BrowserRuntimeStatus(
            available=False,
            engine=None,
            failure_code="browser_runtime_unavailable",
            diagnostic_summary="Optional browser runtime is unavailable.",
        )


class OptionalBrowserProvider:
    """Browser acquisition stays unavailable until an explicit renderer is supplied."""

    def __init__(
        self,
        *,
        runtime_probe: Callable[[], str] | None = None,
        renderer: Callable[..., object] | None = None,
    ) -> None:
        self.runtime_probe = runtime_probe
        self.renderer = renderer

    @property
    def can_acquire(self) -> bool:
        return self.renderer is not None and self.availability().available

    def availability(self) -> BrowserRuntimeStatus:
        return detect_browser_runtime(probe=self.runtime_probe)
