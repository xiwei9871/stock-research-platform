"""Test-wide guard: unit tests must never open a real database connection.

Any ``psycopg.connect`` (or ``stock_research.db.connect``) call fails unless
its service is explicitly allowed through ``STOCK_RESEARCH_TEST_DB_SERVICES``
(comma separated), which only the opt-in integration tests set.
"""

from __future__ import annotations

import os
import re

import psycopg
import pytest

_ALLOWED_ENV = "STOCK_RESEARCH_TEST_DB_SERVICES"


def _allowed() -> set[str]:
    return {s.strip() for s in os.getenv(_ALLOWED_ENV, "").split(",") if s.strip()}


def _service_of(args, kwargs) -> str:
    conninfo = str(args[0]) if args else str(kwargs.get("conninfo") or "")
    match = re.search(r"service=([^\s]+)", conninfo)
    return match.group(1) if match else (kwargs.get("service") or conninfo or "<default>")


@pytest.fixture(autouse=True)
def _block_real_database(monkeypatch):
    real_connect = psycopg.connect

    def guarded(*args, **kwargs):
        service = _service_of(args, kwargs)
        if service in _allowed():
            return real_connect(*args, **kwargs)
        raise RuntimeError(
            f"test attempted a real database connection (service={service!r}); "
            f"mock it or allow it via {_ALLOWED_ENV}"
        )

    monkeypatch.setattr(psycopg, "connect", guarded)
    yield
