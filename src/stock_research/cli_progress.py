from __future__ import annotations

import sys
import time
from typing import Any, Callable, TextIO


def format_progress_bar(completed: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    clamped_completed = max(0, min(int(completed), int(total)))
    filled = round(width * clamped_completed / int(total))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "unknown"
    whole_seconds = max(0, int(seconds))
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def estimate_eta_seconds(completed: int, total: int, elapsed_seconds: float) -> int | None:
    completed_count = int(completed or 0)
    total_count = int(total or 0)
    if completed_count <= 0 or total_count <= 0:
        return None
    remaining = max(0, total_count - completed_count)
    if remaining == 0:
        return 0
    seconds_per_item = float(elapsed_seconds) / completed_count
    return int(seconds_per_item * remaining)


class ProgressRenderer:
    def __init__(
        self,
        label: str,
        *,
        stream: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
        width: int = 24,
    ) -> None:
        self.label = label
        self.stream = stream if stream is not None else sys.stderr
        self.clock = clock
        self.width = width
        self.started_at = self.clock()

    def __call__(self, event: dict[str, Any]) -> None:
        completed = _event_int(event, "completed", "completed_jobs")
        total = _event_int(event, "total", "total_jobs")
        rows = _event_int(event, "rows")
        success = _event_int(event, "success", "success_jobs")
        failed = _event_int(event, "failed", "failed_jobs")
        elapsed = max(0.0, self.clock() - self.started_at)
        eta = estimate_eta_seconds(completed, total, elapsed)
        pct = (completed / total * 100.0) if total > 0 else 0.0
        event_name = str(event.get("event") or "progress")

        if _is_tty(self.stream):
            line = (
                f"{self.label} {format_progress_bar(completed, total, self.width)} "
                f"{completed}/{total} {pct:.2f}% elapsed={format_duration(elapsed)} "
                f"eta={format_duration(eta)} rows={rows} success={success} failed={failed}"
            )
            self.stream.write("\r" + line)
            if _is_finished_event(event_name, completed, total):
                self.stream.write("\n")
        else:
            line = (
                f"progress|{self.label}|event|{event_name}|completed|{completed}|"
                f"total|{total}|pct|{pct:.2f}|elapsed|{format_duration(elapsed)}|"
                f"eta|{format_duration(eta)}|rows|{rows}|success|{success}|failed|{failed}"
            )
            self.stream.write(line + "\n")
        self.stream.flush()


def _event_int(event: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in event and event[key] is not None:
            return int(event[key])
    return 0


def _is_tty(stream: TextIO) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)())


def _is_finished_event(event_name: str, completed: int, total: int) -> bool:
    return event_name.endswith("completed") or (total > 0 and completed >= total)
