"""Execution attempts for business runs (Gate A).

A business run (``run_id``, e.g. ``strategy-eod-2026-10-29-local``) keeps its
current state in ``ops.data_run_manifest``. Every execution of it gets an
``attempt_id`` row here. Rows move running -> terminal; different attempts
never overwrite each other.

The start row is committed on its own connection, before any publication
transaction, so a failed or rolled-back publication still leaves a record.
When the database is unavailable the same record is written atomically to
``run_record_<attempt_id>.json`` and replayed later (idempotent by
``attempt_id``).
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any, Protocol

from stock_research.atomic_json import atomic_write_json, read_json
from stock_research.db import connect

ATTEMPT_STATUSES = ("running", "published", "succeeded", "failed", "skipped", "abandoned")
TERMINAL_STATUSES = tuple(s for s in ATTEMPT_STATUSES if s != "running")
FAILURE_CLASSES = ("dependency", "environment", "compute", "publish", "notify", "abandoned")
TRIGGERS = ("cron", "repair", "manual")

CREATE_RUN_ATTEMPT_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.data_run_attempt (
    attempt_id text PRIMARY KEY,
    run_id text NOT NULL,
    trade_date date,
    module text NOT NULL,
    trigger text NOT NULL CHECK (trigger IN ('cron', 'repair', 'manual')),
    status text NOT NULL CHECK (status IN (
        'running', 'published', 'succeeded', 'failed', 'skipped', 'abandoned')),
    failure_class text CHECK (failure_class IS NULL OR failure_class IN (
        'dependency', 'environment', 'compute', 'publish', 'notify', 'abandoned')),
    parent_attempt_id text,
    git_sha text,
    input_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    recorded_from text NOT NULL DEFAULT 'db' CHECK (recorded_from IN ('db', 'local_backfill')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_data_run_attempt_run
    ON ops.data_run_attempt (run_id, module, started_at DESC);
"""


def new_attempt_id() -> str:
    return uuid.uuid4().hex


def current_git_sha(cwd: str | Path | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
            cwd=str(cwd) if cwd else str(Path(__file__).resolve().parent), timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha or None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _validate(record: dict[str, Any]) -> None:
    if record.get("status") not in ATTEMPT_STATUSES:
        raise ValueError(f"invalid attempt status: {record.get('status')}")
    if record.get("trigger") not in TRIGGERS:
        raise ValueError(f"invalid attempt trigger: {record.get('trigger')}")
    fc = record.get("failure_class")
    if fc is not None and fc not in FAILURE_CLASSES:
        raise ValueError(f"invalid failure_class: {fc}")


class AttemptStore(Protocol):
    def start(self, record: dict[str, Any]) -> dict[str, Any]: ...
    def finish(self, attempt_id: str, **fields: Any) -> dict[str, Any]: ...


class DbAttemptStore:
    """Writes attempts to PostgreSQL; falls back to a local JSON record."""

    def __init__(self, *, service: str, fallback_dir: str | Path, connect_fn=connect) -> None:
        self.service = service
        self.fallback_dir = Path(fallback_dir)
        self._connect = connect_fn
        self._records: dict[str, dict[str, Any]] = {}

    def _local_path(self, attempt_id: str) -> Path:
        return self.fallback_dir / f"run_record_{attempt_id}.json"

    def _write_local(self, record: dict[str, Any]) -> None:
        atomic_write_json(self._local_path(record["attempt_id"]), record)

    def start(self, record: dict[str, Any]) -> dict[str, Any]:
        record = {"input_refs": {}, "output_refs": {}, **record,
                  "status": "running", "started_at": record.get("started_at") or _now()}
        _validate(record)
        self._records[record["attempt_id"]] = record
        try:
            with self._connect(self.service) as conn:
                mark_abandoned(conn, run_id=record["run_id"], module=record["module"],
                               exclude_attempt_id=record["attempt_id"])
                upsert_attempt(conn, record, recorded_from="db")
            record["persisted"] = "db"
        except Exception as exc:  # noqa: BLE001 - DB down must not lose the record
            record["persisted"] = "local"
            record["db_error"] = f"{type(exc).__name__}: {exc}"
        self._write_local(record)
        return record

    def finish(self, attempt_id: str, **fields: Any) -> dict[str, Any]:
        record = {**self._records.get(attempt_id, {"attempt_id": attempt_id}), **fields}
        record["ended_at"] = record.get("ended_at") or _now()
        _validate(record)
        self._records[attempt_id] = record
        try:
            with self._connect(self.service) as conn:
                upsert_attempt(conn, record, recorded_from="db")
            record["persisted"] = "db"
        except Exception as exc:  # noqa: BLE001
            record["persisted"] = "local"
            record["db_error"] = f"{type(exc).__name__}: {exc}"
        self._write_local(record)
        return record


class MemoryAttemptStore:
    """Test double with the same contract."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.events: list[tuple[str, str, str]] = []

    def start(self, record: dict[str, Any]) -> dict[str, Any]:
        record = {"input_refs": {}, "output_refs": {}, **record,
                  "status": "running", "started_at": record.get("started_at") or _now()}
        _validate(record)
        if record["attempt_id"] in self.records:
            raise ValueError("attempt_id already exists")
        for other in self.records.values():
            if (other["run_id"], other["module"], other["status"]) == (
                    record["run_id"], record["module"], "running"):
                other.update(status="abandoned", failure_class="abandoned", ended_at=_now())
        self.records[record["attempt_id"]] = record
        self.events.append(("start", record["attempt_id"], "running"))
        return record

    def finish(self, attempt_id: str, **fields: Any) -> dict[str, Any]:
        record = {**self.records[attempt_id], **fields}
        record["ended_at"] = record.get("ended_at") or _now()
        _validate(record)
        self.records[attempt_id] = record
        self.events.append(("finish", attempt_id, record["status"]))
        return record


_UPSERT_SQL = """
INSERT INTO ops.data_run_attempt (
    attempt_id, run_id, trade_date, module, trigger, status, failure_class,
    parent_attempt_id, git_sha, input_refs, output_refs, error_message,
    started_at, ended_at, recorded_from
) VALUES (
    %(attempt_id)s, %(run_id)s, %(trade_date)s, %(module)s, %(trigger)s, %(status)s,
    %(failure_class)s, %(parent_attempt_id)s, %(git_sha)s, %(input_refs)s::jsonb,
    %(output_refs)s::jsonb, %(error_message)s, %(started_at)s, %(ended_at)s, %(recorded_from)s
)
ON CONFLICT (attempt_id) DO UPDATE SET
    status = EXCLUDED.status,
    failure_class = EXCLUDED.failure_class,
    output_refs = EXCLUDED.output_refs,
    error_message = EXCLUDED.error_message,
    ended_at = EXCLUDED.ended_at,
    updated_at = now()
WHERE ops.data_run_attempt.status = 'running'
"""


def upsert_attempt(conn: Any, record: dict[str, Any], *, recorded_from: str) -> None:
    """Insert, or move a running attempt to its next state.

    A terminal attempt is never changed again, so replaying the same record
    (local backfill, retries) is idempotent.
    """
    params = {
        "attempt_id": record["attempt_id"],
        "run_id": record["run_id"],
        "trade_date": record.get("trade_date"),
        "module": record["module"],
        "trigger": record["trigger"],
        "status": record["status"],
        "failure_class": record.get("failure_class"),
        "parent_attempt_id": record.get("parent_attempt_id"),
        "git_sha": record.get("git_sha"),
        "input_refs": json.dumps(record.get("input_refs") or {}, sort_keys=True, default=str),
        "output_refs": json.dumps(record.get("output_refs") or {}, sort_keys=True, default=str),
        "error_message": record.get("error_message"),
        "started_at": record["started_at"],
        "ended_at": record.get("ended_at"),
        "recorded_from": recorded_from,
    }
    with conn.cursor() as cur:
        cur.execute(_UPSERT_SQL, params)


def apply_run_attempt_schema(service: str) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_RUN_ATTEMPT_SQL)


def backfill_local_records(conn: Any, directory: str | Path) -> dict[str, int]:
    """Replay local run records into the DB; safe to run repeatedly."""
    seen = 0
    for path in sorted(Path(directory).glob("run_record_*.json")):
        record = read_json(path)
        if not record.get("attempt_id"):
            continue
        record = {k: v for k, v in record.items() if k not in {"persisted", "db_error"}}
        _validate(record)
        upsert_attempt(conn, record, recorded_from="local_backfill")
        seen += 1
    return {"records": seen}


def mark_abandoned(conn: Any, *, run_id: str, module: str, exclude_attempt_id: str | None = None) -> int:
    """Close attempts of this run/module that are still 'running' (crashed)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ops.data_run_attempt
               SET status = 'abandoned', failure_class = 'abandoned',
                   ended_at = now(), updated_at = now()
             WHERE run_id = %(run_id)s AND module = %(module)s AND status = 'running'
               AND attempt_id IS DISTINCT FROM %(exclude)s
            """,
            {"run_id": run_id, "module": module, "exclude": exclude_attempt_id},
        )
        return cur.rowcount or 0


def latest_published_attempt(conn: Any, *, run_id: str, module: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT attempt_id, run_id, status, git_sha, output_refs, ended_at
              FROM ops.data_run_attempt
             WHERE run_id = %(run_id)s AND module = %(module)s AND status = 'published'
             ORDER BY ended_at DESC NULLS LAST, started_at DESC
             LIMIT 1
            """,
            {"run_id": run_id, "module": module},
        )
        row = cur.fetchone()
    return dict(row) if row else None
