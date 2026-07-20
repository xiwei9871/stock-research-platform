from collections.abc import Callable
from typing import Any

import psycopg


def load_sandbox_database_name(
    service: str,
    *,
    connector: Callable[[str], Any] = psycopg.connect,
) -> str:
    connection = connector(f"service={service}")
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

    if not row or not isinstance(row[0], str) or not row[0]:
        raise RuntimeError("could not determine sandbox database")
    return row[0]


def assert_sandbox_database(database_name: str) -> str:
    if not isinstance(database_name, str) or not database_name.endswith("_test"):
        raise RuntimeError(f"refusing non-test database: {database_name!r}")
    return database_name
