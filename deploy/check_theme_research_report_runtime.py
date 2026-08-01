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


def _schema_status(service: str) -> dict[str, Any]:
    with connect(service) as conn:
        with conn.cursor() as cur:
            inspection = inspect_theme_research_report_schema(cur)
    return {
        "service": service,
        "schema_version": THEME_RESEARCH_REPORT_SCHEMA_VERSION,
        **inspection,
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
    args = parser.parse_args(argv)

    schema = _schema_status(args.migration_service)
    if args.schema_only:
        payload = {
            "status": "ok" if schema["status"] == "current" else "error",
            "schema": schema,
        }
    else:
        if args.expected_root is None or not args.expected_root.is_absolute():
            parser.error("--expected-root must be an absolute path")
        configured_root = Path(SETTINGS.theme_research_report_root)
        root = _root_status(configured_root)
        root_matches = configured_root == args.expected_root
        diagnostics: dict[str, Any]
        if root_matches and root["exists"] and root["readable"] and root["readonly"]:
            diagnostics = _index_status(configured_root, args.runtime_service)
        else:
            diagnostics = {
                "status": "error",
                "invalid": 0,
                "errors": [{"code": "THEME_REPORT_ROOT_UNHEALTHY"}],
            }
        healthy = (
            root_matches
            and root["exists"]
            and root["readable"]
            and root["readonly"]
            and schema["status"] == "current"
            and diagnostics["status"] == "ok"
        )
        payload = {
            "status": "ok" if healthy else "error",
            "root": root,
            "schema": schema,
            "scheduler_index_diagnostics": diagnostics,
        }

    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(cli())
