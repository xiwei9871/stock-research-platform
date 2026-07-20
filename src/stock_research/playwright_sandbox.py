from collections.abc import Callable
from typing import Any

import psycopg


def load_sandbox_database_name(
    service: str,
    *,
    connector: Callable[..., Any] | None = None,
) -> str:
    connect = psycopg.connect if connector is None else connector
    connection = connect(service=service)
    cursor = None
    database_name = None
    operation_error = None
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
        if not row or not isinstance(row[0], str) or not row[0]:
            raise RuntimeError("could not determine sandbox database")
        database_name = row[0]
    except BaseException as error:
        operation_error = error

    cleanup_errors: list[tuple[str, BaseException]] = []
    if cursor is not None:
        try:
            cursor.close()
        except BaseException as error:
            cleanup_errors.append(("cursor", error))
    try:
        connection.close()
    except BaseException as error:
        cleanup_errors.append(("connection", error))

    if operation_error is not None:
        for resource, error in cleanup_errors:
            operation_error.add_note(f"{resource} cleanup failed: {error!r}")
        raise operation_error

    if cleanup_errors:
        _, cleanup_error = cleanup_errors[0]
        for resource, error in cleanup_errors[1:]:
            cleanup_error.add_note(f"{resource} cleanup also failed: {error!r}")
        raise cleanup_error

    if database_name is None:
        raise RuntimeError("could not determine sandbox database")
    return database_name


def assert_sandbox_database(database_name: str) -> str:
    if not isinstance(database_name, str) or not database_name.endswith("_test"):
        raise RuntimeError(f"refusing non-test database: {database_name!r}")
    return database_name
