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
_CAPABILITY_ROLES = {
    "runtime": "theme_research_runtime",
    "indexer": "theme_research_report_indexer",
    "reviewer": "theme_research_report_reviewer",
}
_SCHEMA_OWNER_ROLE = "theme_research_owner"
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
            cur.execute(
                "SELECT current_user::text AS current_user, "
                "session_user::text AS session_user"
            )
            identity = cur.fetchone()
            inspection = inspect_theme_research_report_schema(cur)
    return {
        "service": service,
        "schema_version": THEME_RESEARCH_REPORT_SCHEMA_VERSION,
        "current_user": str(identity["current_user"]),
        "session_user": str(identity["session_user"]),
        **inspection,
    }


def _unique_roles(*role_groups: object) -> list[str]:
    roles: set[str] = set()
    for group in role_groups:
        if isinstance(group, str):
            values = (group,)
        else:
            try:
                values = tuple(group)
            except TypeError:
                continue
        roles.update(
            str(value)
            for value in values
            if isinstance(value, str) and value
        )
    return sorted(roles)


def _permission_status(
    service: str,
    profile: str,
    forbidden_roles: set[str],
) -> dict[str, Any]:
    expected = _EXPECTED_PERMISSION_PROFILES[profile]
    expected_capability_role = _CAPABILITY_ROLES[profile]
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    current_user::text AS current_user,
                    session_user::text AS session_user,
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
            sensitive_roles = _unique_roles(
                _CAPABILITY_ROLES.values(),
                _SCHEMA_OWNER_ROLE,
                forbidden_roles,
            )
            cur.execute(
                """
                WITH sensitive_roles(role_name) AS (
                    SELECT unnest(%s::text[])
                )
                SELECT
                    role_name,
                    pg_has_role(session_user, role_name, 'MEMBER') AS member,
                    pg_has_role(session_user, role_name, 'USAGE') AS usage,
                    pg_has_role(session_user, role_name, 'SET') AS can_set,
                    EXISTS (
                        SELECT 1
                        FROM pg_auth_members membership
                        JOIN pg_roles granted_role
                          ON granted_role.oid = membership.roleid
                        JOIN pg_roles member_role
                          ON member_role.oid = membership.member
                        WHERE member_role.rolname = session_user
                          AND granted_role.rolname = sensitive_roles.role_name
                    ) AS direct_member
                FROM sensitive_roles
                ORDER BY role_name
                """,
                (sensitive_roles,),
            )
            login_role_rows = list(cur.fetchall())
            graph_targets = _unique_roles(
                _CAPABILITY_ROLES.values(),
                _SCHEMA_OWNER_ROLE,
                forbidden_roles,
            )
            cur.execute(
                """
                WITH source_roles(source_role) AS (
                    SELECT unnest(%s::text[])
                ),
                target_roles(target_role) AS (
                    SELECT unnest(%s::text[])
                )
                SELECT
                    source_role,
                    target_role,
                    pg_has_role(source_role, target_role, 'MEMBER') AS member,
                    pg_has_role(source_role, target_role, 'USAGE') AS usage,
                    pg_has_role(source_role, target_role, 'SET') AS can_set,
                    EXISTS (
                        SELECT 1
                        FROM pg_auth_members membership
                        JOIN pg_roles granted_role
                          ON granted_role.oid = membership.roleid
                        JOIN pg_roles member_role
                          ON member_role.oid = membership.member
                        WHERE member_role.rolname = source_roles.source_role
                          AND granted_role.rolname = target_roles.target_role
                    ) AS direct_member
                FROM source_roles
                CROSS JOIN target_roles
                WHERE source_role <> target_role
                ORDER BY source_role, target_role
                """,
                (list(_CAPABILITY_ROLES.values()), graph_targets),
            )
            capability_graph_rows = list(cur.fetchall())
    privileges = {
        key: bool(row[key])
        for key in expected
    }
    session_user = str(row["session_user"])
    membership_violations: list[str] = []
    membership_rows: dict[str, dict[str, bool]] = {}
    for membership_row in login_role_rows:
        role_name = str(membership_row["role_name"])
        flags = {
            key: bool(membership_row[key])
            for key in ("member", "usage", "can_set", "direct_member")
        }
        membership_rows[role_name] = flags
        if role_name == expected_capability_role:
            if not flags["member"]:
                membership_violations.append(f"{role_name}:member_missing")
            if not flags["can_set"]:
                membership_violations.append(f"{role_name}:set_missing")
            continue
        for flag_name, enabled in flags.items():
            if enabled:
                membership_violations.append(f"{role_name}:{flag_name}")
    if session_user in set(forbidden_roles) | set(_CAPABILITY_ROLES.values()) | {
        _SCHEMA_OWNER_ROLE
    }:
        membership_violations.append("session_user:sensitive_role")

    graph_violations: list[str] = []
    for graph_row in capability_graph_rows:
        source_role = str(graph_row["source_role"])
        target_role = str(graph_row["target_role"])
        for flag_name in ("member", "usage", "can_set", "direct_member"):
            if bool(graph_row[flag_name]):
                graph_violations.append(
                    f"{source_role}->{target_role}:{flag_name}"
                )
    role_membership = {
        "status": (
            "ok"
            if not membership_violations and not graph_violations
            else "error"
        ),
        "expected_capability_role": expected_capability_role,
        "sensitive_roles": membership_rows,
        "violations": sorted(set(membership_violations)),
        "capability_graph_violations": sorted(set(graph_violations)),
    }
    healthy = (
        privileges == expected
        and bool(session_user)
        and role_membership["status"] == "ok"
    )
    return {
        "status": "ok" if healthy else "error",
        "service": service,
        "profile": profile,
        "current_user": str(row["current_user"]),
        "session_user": session_user,
        "privileges": privileges,
        "expected": expected,
        "role_membership": role_membership,
    }


def _service_identity_status(
    service_permissions: dict[str, dict[str, Any]],
    schema: dict[str, Any],
) -> dict[str, Any]:
    session_users = {
        profile: str(result.get("session_user") or "")
        for profile, result in service_permissions.items()
    }
    violations: list[str] = []
    if any(not user for user in session_users.values()):
        violations.append("session_user:missing")
    if len(set(session_users.values())) != len(session_users):
        violations.append("session_user:not_distinct")
    migration_identities = {
        str(schema.get("current_user") or ""),
        str(schema.get("session_user") or ""),
        _SCHEMA_OWNER_ROLE,
    } - {""}
    for profile, user in session_users.items():
        if user in migration_identities:
            violations.append(f"{profile}:migration_identity")
    return {
        "status": "ok" if not violations else "error",
        "session_users": session_users,
        "migration_identities": sorted(migration_identities),
        "violations": sorted(set(violations)),
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
    forbidden_roles = {
        str(schema.get("current_user") or ""),
        str(schema.get("session_user") or ""),
        _SCHEMA_OWNER_ROLE,
    } - {""}
    service_permissions = {
        "runtime": _permission_status(
            args.runtime_service, "runtime", forbidden_roles
        ),
        "indexer": _permission_status(
            args.index_service, "indexer", forbidden_roles
        ),
        "reviewer": _permission_status(
            args.review_service, "reviewer", forbidden_roles
        ),
    }
    service_identity = _service_identity_status(service_permissions, schema)
    permissions_healthy = all(
        result["status"] == "ok" for result in service_permissions.values()
    ) and service_identity["status"] == "ok"
    if args.schema_only:
        payload = {
            "status": (
                "ok"
                if schema["status"] == "current" and permissions_healthy
                else "error"
            ),
            "schema": schema,
            "service_permissions": service_permissions,
            "service_identity": service_identity,
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
            "service_identity": service_identity,
            "scheduler_index_diagnostics": diagnostics,
        }

    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(cli())
