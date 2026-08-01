#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.theme_research_report_index import (
    limits_from_settings,
    scan_theme_research_report_root,
)
from stock_research.theme_research_report_schema import (
    THEME_RESEARCH_REPORT_SCHEMA_VERSION,
    inspect_theme_research_report_schema,
)

_REGISTER_FUNCTION = (
    "research.register_theme_research_report_pending(text,text,text,text,text,text,"
    "text,text,text,text,text,text,text,jsonb,timestamp with time zone,jsonb,text,text,text)"
)
_REVIEW_FUNCTION = (
    "research.review_theme_research_report_version(text,text,bigint,text,text,text,text,text)"
)
_EXPECTED_PERMISSION_PROFILES = {
    "runtime": {
        "schema_usage": True,
        "version_select": True,
        "review_event_select": True,
        "version_write": False,
        "review_event_write": False,
        "register_execute": False,
        "review_execute": False,
    },
    "indexer": {
        "schema_usage": True,
        "version_select": False,
        "review_event_select": False,
        "version_write": False,
        "review_event_write": False,
        "register_execute": True,
        "review_execute": False,
    },
    "reviewer": {
        "schema_usage": True,
        "version_select": False,
        "review_event_select": False,
        "version_write": False,
        "review_event_write": False,
        "register_execute": False,
        "review_execute": True,
    },
}


def _schema_status(service: str) -> dict[str, Any]:
    with connect(service) as conn:
        with conn.cursor() as cur:
            inspection = inspect_theme_research_report_schema(cur)
    return {
        "service": service,
        "schema_version": THEME_RESEARCH_REPORT_SCHEMA_VERSION,
        **inspection,
    }


def _permission_status(service: str, profile: str) -> dict[str, Any]:
    expected = _EXPECTED_PERMISSION_PROFILES[profile]
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    current_user AS current_user,
                    has_schema_privilege(current_user, 'research', 'USAGE')
                        AS schema_usage,
                    has_table_privilege(
                        current_user,
                        'research.theme_research_report_version',
                        'SELECT'
                    ) AS version_select,
                    has_table_privilege(
                        current_user,
                        'research.theme_research_report_review_event',
                        'SELECT'
                    ) AS review_event_select,
                    (
                        has_table_privilege(current_user, 'research.theme_research_report_version', 'INSERT')
                        OR has_table_privilege(current_user, 'research.theme_research_report_version', 'UPDATE')
                        OR has_table_privilege(current_user, 'research.theme_research_report_version', 'DELETE')
                        OR has_table_privilege(current_user, 'research.theme_research_report_version', 'TRUNCATE')
                        OR has_table_privilege(current_user, 'research.theme_research_report_version', 'REFERENCES')
                        OR has_table_privilege(current_user, 'research.theme_research_report_version', 'TRIGGER')
                    ) AS version_write,
                    (
                        has_table_privilege(current_user, 'research.theme_research_report_review_event', 'INSERT')
                        OR has_table_privilege(current_user, 'research.theme_research_report_review_event', 'UPDATE')
                        OR has_table_privilege(current_user, 'research.theme_research_report_review_event', 'DELETE')
                        OR has_table_privilege(current_user, 'research.theme_research_report_review_event', 'TRUNCATE')
                        OR has_table_privilege(current_user, 'research.theme_research_report_review_event', 'REFERENCES')
                        OR has_table_privilege(current_user, 'research.theme_research_report_review_event', 'TRIGGER')
                    ) AS review_event_write,
                    has_function_privilege(current_user, %s, 'EXECUTE')
                        AS register_execute,
                    has_function_privilege(current_user, %s, 'EXECUTE')
                        AS review_execute
                """,
                (_REGISTER_FUNCTION, _REVIEW_FUNCTION),
            )
            row = cur.fetchone()
    privileges = {
        key: bool(row[key])
        for key in expected
    }
    healthy = privileges == expected
    return {
        "status": "ok" if healthy else "error",
        "service": service,
        "profile": profile,
        "current_user": str(row["current_user"]),
        "privileges": privileges,
        "expected": expected,
    }


def _root_status(root: Path) -> dict[str, Any]:
    exists = root.is_dir()
    readable = False
    readonly = False
    if exists:
        try:
            next(root.iterdir(), None)
            readable = os.access(root, os.R_OK | os.X_OK)
            readonly = bool(os.statvfs(root).f_flag & os.ST_RDONLY)
        except OSError:
            readable = False
    return {
        "path": str(root),
        "exists": exists,
        "readable": readable,
        "readonly": readonly,
    }


def _index_status(root: Path, service: str) -> dict[str, Any]:
    result = scan_theme_research_report_root(
        root,
        limits=limits_from_settings(SETTINGS),
        service=service,
    ).to_dict()
    healthy = result.get("invalid") == 0 and result.get("errors") == []
    return {"status": "ok" if healthy else "error", **result}


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--expected-root", type=Path)
    parser.add_argument(
        "--migration-service",
        default=SETTINGS.theme_research_migration_service,
    )
    parser.add_argument(
        "--runtime-service",
        default=SETTINGS.theme_research_runtime_service,
    )
    parser.add_argument(
        "--index-service",
        default=SETTINGS.theme_research_report_index_service,
    )
    parser.add_argument(
        "--review-service",
        default=SETTINGS.theme_research_report_review_service,
    )
    args = parser.parse_args(argv)

    capability_services = (
        args.runtime_service,
        args.index_service,
        args.review_service,
    )
    if any(not service.strip() for service in capability_services) or len(
        set(capability_services)
    ) != len(capability_services):
        parser.error("runtime, index, and review services must be distinct non-empty values")

    schema = _schema_status(args.migration_service)
    service_permissions = {
        "runtime": _permission_status(args.runtime_service, "runtime"),
        "indexer": _permission_status(args.index_service, "indexer"),
        "reviewer": _permission_status(args.review_service, "reviewer"),
    }
    permissions_healthy = all(
        result["status"] == "ok" for result in service_permissions.values()
    )
    if args.schema_only:
        payload = {
            "status": (
                "ok"
                if schema["status"] == "current" and permissions_healthy
                else "error"
            ),
            "schema": schema,
            "service_permissions": service_permissions,
        }
    else:
        if args.expected_root is None or not args.expected_root.is_absolute():
            parser.error("--expected-root must be an absolute path")
        configured_root = Path(SETTINGS.theme_research_report_root)
        root = _root_status(configured_root)
        root_matches = configured_root == args.expected_root
        diagnostics: dict[str, Any]
        if (
            permissions_healthy
            and root_matches
            and root["exists"]
            and root["readable"]
            and root["readonly"]
        ):
            diagnostics = _index_status(configured_root, args.index_service)
        else:
            diagnostics = {
                "status": "error",
                "invalid": 0,
                "errors": [
                    {
                        "code": (
                            "THEME_REPORT_SERVICE_PERMISSION_UNSAFE"
                            if not permissions_healthy
                            else "THEME_REPORT_ROOT_UNHEALTHY"
                        )
                    }
                ],
            }
        healthy = (
            root_matches
            and root["exists"]
            and root["readable"]
            and root["readonly"]
            and schema["status"] == "current"
            and permissions_healthy
            and diagnostics["status"] == "ok"
        )
        payload = {
            "status": "ok" if healthy else "error",
            "root": root,
            "schema": schema,
            "service_permissions": service_permissions,
            "scheduler_index_diagnostics": diagnostics,
        }

    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(cli())
