from collections.abc import Iterable
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row


@contextmanager
def connect(service: str):
    conn = psycopg.connect(f"service={service}", row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(
    conn: psycopg.Connection,
    sql: str,
    params: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def execute(
    conn: psycopg.Connection,
    sql: str,
    params: Iterable[Any] | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params)


def execute_many(
    conn: psycopg.Connection,
    sql: str,
    rows: Iterable[Iterable[Any]],
) -> None:
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
