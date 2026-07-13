from __future__ import annotations

import datetime as dt
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


BacktestRunner = Callable[[dict[str, Any]], dict[str, Any]]


class BacktestJobStore:
    def __init__(self, runner: BacktestRunner, *, max_workers: int = 1) -> None:
        self._runner = runner
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dashboard-backtest")
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = f"backtest-job:{uuid.uuid4().hex}"
        now = _now()
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "started_at": "",
            "completed_at": "",
            "payload": dict(payload),
            "result": None,
            "error": "",
        }
        with self._lock:
            self._jobs[job_id] = job
        self._executor.submit(self._run, job_id, dict(payload))
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return dict(job)

    def _run(self, job_id: str, payload: dict[str, Any]) -> None:
        self._update(job_id, status="running", started_at=_now())
        try:
            result = self._runner(payload)
        except Exception as exc:  # pragma: no cover - exact failures are surfaced through API state.
            self._update(job_id, status="failed", completed_at=_now(), error=str(exc), result=None)
            return
        self._update(job_id, status="succeeded", completed_at=_now(), result=result, error="")

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()
