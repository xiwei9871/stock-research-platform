from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

import psycopg

from stock_research.dashboard.auth_schema import DASHBOARD_AUTH_SCHEMA_SQL
from stock_research.dashboard.auth_service import hash_password
from stock_research.review_evidence_snapshots import CREATE_REVIEW_EVIDENCE_SNAPSHOT_SQL
from stock_research.schema import CREATE_RESEARCH_EXTENSION_SQL


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$")


@dataclass(frozen=True)
class SandboxCredentials:
    admin_password: str
    user_password: str


@dataclass(frozen=True)
class SandboxSeed:
    run_id: str
    admin_user_id: str
    admin_username: str
    user_user_id: str
    user_username: str
    created_username: str
    review_session_id: str
    operator_event_id: str
    evidence_artifact_id: str
    review_item_snapshot_id: str
    evidence_digest_snapshot_id: str
    digest_key: str
    asset_id: str
    trade_date: str


def _validated_run_id(run_id: str) -> str:
    normalized = str(run_id or "").strip()
    if not _RUN_ID_RE.fullmatch(normalized):
        raise ValueError("invalid sandbox run_id")
    return normalized


def build_sandbox_seed(run_id: str) -> SandboxSeed:
    normalized = _validated_run_id(run_id)
    asset_token = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8].upper()
    return SandboxSeed(
        run_id=normalized,
        admin_user_id=f"{normalized}:admin",
        admin_username=f"e2e_{normalized}_admin",
        user_user_id=f"{normalized}:user",
        user_username=f"e2e_{normalized}_user",
        created_username=f"e2e_{normalized}_created",
        review_session_id=f"{normalized}:review_session",
        operator_event_id=f"{normalized}:operator_decision",
        evidence_artifact_id=f"{normalized}:evidence",
        review_item_snapshot_id=f"{normalized}:review_item_snapshot",
        evidence_digest_snapshot_id=f"{normalized}:evidence_digest_snapshot",
        digest_key=f"{normalized}:digest",
        asset_id=f"E2E{asset_token}.SZ",
        trade_date="2026-07-17",
    )


def _extract_table_ddl(qualified_name: str) -> str:
    marker = f"CREATE TABLE IF NOT EXISTS {qualified_name} ("
    start = CREATE_RESEARCH_EXTENSION_SQL.find(marker)
    if start < 0:
        raise RuntimeError(f"sandbox schema source missing: {qualified_name}")
    end = CREATE_RESEARCH_EXTENSION_SQL.find("\n);", start)
    if end < 0:
        raise RuntimeError(f"sandbox schema source incomplete: {qualified_name}")
    return CREATE_RESEARCH_EXTENSION_SQL[start : end + 3]


SANDBOX_OPERATOR_SCHEMA_SQL = "\n\n".join(
    (
        "CREATE SCHEMA IF NOT EXISTS ops;",
        _extract_table_ddl("ops.operator_review_session"),
        _extract_table_ddl("ops.operator_decision_event"),
        "CREATE INDEX IF NOT EXISTS idx_ops_operator_decision_event_asset_date "
        "ON ops.operator_decision_event (asset_id, review_date DESC);",
    )
)


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


def _assert_connection_is_sandbox(connection: Any) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
    if not row or not isinstance(row[0], str) or not row[0]:
        raise RuntimeError("could not determine sandbox database")
    return assert_sandbox_database(row[0])


def _validate_credentials(credentials: SandboxCredentials) -> None:
    if len(credentials.admin_password) < 12 or len(credentials.user_password) < 12:
        raise ValueError("sandbox passwords must contain at least 12 characters")


def prepare_sandbox(
    connection: Any,
    run_id: str,
    credentials: SandboxCredentials,
) -> SandboxSeed:
    seed = build_sandbox_seed(run_id)
    _validate_credentials(credentials)
    try:
        _assert_connection_is_sandbox(connection)
        with connection.cursor() as cursor:
            cursor.execute(DASHBOARD_AUTH_SCHEMA_SQL)
            cursor.execute(SANDBOX_OPERATOR_SCHEMA_SQL)
            cursor.execute(CREATE_REVIEW_EVIDENCE_SNAPSHOT_SQL)
            cursor.execute(
                """
                INSERT INTO identity.user_account (
                    user_id, username, display_name, role, password_hash, is_active, metadata
                )
                VALUES (%(user_id)s, %(username)s, %(display_name)s, %(role)s, %(password_hash)s, true,
                        %(metadata)s::jsonb)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    display_name = EXCLUDED.display_name,
                    role = EXCLUDED.role,
                    password_hash = EXCLUDED.password_hash,
                    is_active = true,
                    disabled_at = NULL,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                {
                    "user_id": seed.admin_user_id,
                    "username": seed.admin_username,
                    "display_name": "Playwright Sandbox Admin",
                    "role": "admin",
                    "password_hash": hash_password(credentials.admin_password),
                    "metadata": json.dumps({"playwright_run_id": seed.run_id}, sort_keys=True),
                },
            )
            cursor.execute(
                """
                INSERT INTO identity.user_account (
                    user_id, username, display_name, role, password_hash, is_active, metadata
                )
                VALUES (%(user_id)s, %(username)s, %(display_name)s, %(role)s, %(password_hash)s, true,
                        %(metadata)s::jsonb)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    display_name = EXCLUDED.display_name,
                    role = EXCLUDED.role,
                    password_hash = EXCLUDED.password_hash,
                    is_active = true,
                    disabled_at = NULL,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                {
                    "user_id": seed.user_user_id,
                    "username": seed.user_username,
                    "display_name": "Playwright Sandbox User",
                    "role": "user",
                    "password_hash": hash_password(credentials.user_password),
                    "metadata": json.dumps({"playwright_run_id": seed.run_id}, sort_keys=True),
                },
            )
            cursor.execute(
                """
                INSERT INTO asset_master (
                    asset_id, market, symbol, exchange, name, currency, industry,
                    status, source
                )
                VALUES (
                    %(asset_id)s, 'CN', %(symbol)s, 'SZ', %(name)s, 'CNY',
                    'playwright_sandbox', 'listed', 'playwright_sandbox'
                )
                ON CONFLICT (asset_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    industry = EXCLUDED.industry,
                    status = EXCLUDED.status,
                    source = EXCLUDED.source,
                    updated_at = now()
                """,
                {
                    "asset_id": seed.asset_id,
                    "symbol": seed.asset_id.split(".", 1)[0],
                    "name": f"Playwright {seed.run_id}",
                },
            )
            cursor.execute(
                """
                INSERT INTO market_daily_bar (
                    asset_id, trade_date, open, high, low, close, preclose, volume,
                    amount, turnover_rate, pct_chg, trade_status, is_st, adjust_type, source
                )
                VALUES (
                    %(asset_id)s, %(trade_date)s, 10, 10.8, 9.8, 10.5, 10,
                    100000, 105000000, 2.5, 5, 'NORMAL', false, 'qfq', 'playwright_sandbox'
                )
                ON CONFLICT (asset_id, trade_date, adjust_type) DO UPDATE SET
                    close = EXCLUDED.close,
                    amount = EXCLUDED.amount,
                    source = EXCLUDED.source,
                    updated_at = now()
                """,
                {"asset_id": seed.asset_id, "trade_date": seed.trade_date},
            )
            cursor.execute(
                """
                INSERT INTO ops.review_item_snapshot (
                    snapshot_id, run_id, trade_date, latest_trade_date, asset_id,
                    stock_code, stock_name, digest_key, source_type, source_name,
                    source_rank, topn_rank, score_version, score, evidence_status,
                    missing_evidence_count, partial_evidence_count, warnings_count,
                    review_item_payload, payload_hash, schema_version
                )
                VALUES (
                    %(snapshot_id)s, %(run_id)s, %(trade_date)s, %(trade_date)s,
                    %(asset_id)s, %(asset_id)s, %(stock_name)s, %(digest_key)s,
                    'playwright_sandbox', 'isolated_write_fixture', 1, 1,
                    'sandbox_v1', 1, 'complete', 0, 0, 0,
                    %(payload)s::jsonb, %(payload_hash)s, 'v1'
                )
                ON CONFLICT (run_id, digest_key) DO UPDATE SET
                    review_item_payload = EXCLUDED.review_item_payload,
                    payload_hash = EXCLUDED.payload_hash,
                    updated_at = now()
                """,
                _snapshot_params(seed, kind="review_item"),
            )
            cursor.execute(
                """
                INSERT INTO ops.evidence_digest_snapshot (
                    snapshot_id, run_id, trade_date, latest_trade_date, asset_id,
                    stock_code, stock_name, digest_key, overall_status,
                    missing_evidence, partial_evidence, sections_status,
                    digest_payload, payload_hash, schema_version
                )
                VALUES (
                    %(snapshot_id)s, %(run_id)s, %(trade_date)s, %(trade_date)s,
                    %(asset_id)s, %(asset_id)s, %(stock_name)s, %(digest_key)s,
                    'complete', '[]'::jsonb, '[]'::jsonb,
                    '{"sandbox":"complete"}'::jsonb, %(payload)s::jsonb,
                    %(payload_hash)s, 'v1'
                )
                ON CONFLICT (run_id, digest_key) DO UPDATE SET
                    digest_payload = EXCLUDED.digest_payload,
                    payload_hash = EXCLUDED.payload_hash,
                    updated_at = now()
                """,
                _snapshot_params(seed, kind="evidence_digest"),
            )
            cursor.execute(
                """
                INSERT INTO ops.operator_review_session (
                    review_session_id, review_date, reviewer_id, status, decision_count,
                    manual_review_required, auto_trade_enabled, source_artifact_root,
                    json_path, csv_path, markdown_path, metadata
                )
                VALUES (
                    %(review_session_id)s, %(review_date)s, %(reviewer_id)s, 'review_recorded', 1,
                    true, false, 'playwright-sandbox', '', '', '', %(metadata)s::jsonb
                )
                ON CONFLICT (review_session_id) DO UPDATE SET
                    reviewer_id = EXCLUDED.reviewer_id,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                {
                    "review_session_id": seed.review_session_id,
                    "review_date": seed.trade_date,
                    "reviewer_id": seed.admin_user_id,
                    "metadata": json.dumps({"playwright_run_id": seed.run_id}, sort_keys=True),
                },
            )
            source_context = json.dumps(
                {
                    "run_id": seed.run_id,
                    "digest_key": seed.digest_key,
                    "evidence_artifact_id": seed.evidence_artifact_id,
                    "review_item_snapshot_id": seed.review_item_snapshot_id,
                    "evidence_digest_snapshot_id": seed.evidence_digest_snapshot_id,
                    "snapshot_linkage_status": "linked",
                    "snapshot_linkage_warnings": [],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            cursor.execute(
                """
                INSERT INTO ops.operator_decision_event (
                    event_id, review_session_id, review_date, event_index, asset_id,
                    stock_code, stock_name, decision_label, evidence_artifact_id,
                    evidence_path, source_context, requires_follow_up, follow_up_note,
                    notes, manual_review_required, auto_trade_enabled, source_artifact_path
                )
                VALUES (
                    %(event_id)s, %(review_session_id)s, %(review_date)s, 0, %(asset_id)s,
                    %(asset_id)s, %(stock_name)s, 'observe', %(evidence_artifact_id)s,
                    %(evidence_path)s, %(source_context)s, false, '', %(notes)s,
                    true, false, 'playwright-sandbox'
                )
                ON CONFLICT (event_id) DO UPDATE SET
                    source_context = EXCLUDED.source_context,
                    notes = EXCLUDED.notes,
                    auto_trade_enabled = false,
                    updated_at = now()
                """,
                {
                    "event_id": seed.operator_event_id,
                    "review_session_id": seed.review_session_id,
                    "review_date": seed.trade_date,
                    "asset_id": seed.asset_id,
                    "stock_name": f"Playwright {seed.run_id}",
                    "evidence_artifact_id": seed.evidence_artifact_id,
                    "evidence_path": f"playwright-sandbox/{seed.run_id}/evidence.json",
                    "source_context": source_context,
                    "notes": "sandbox seed note",
                },
            )
        connection.commit()
        return seed
    except BaseException:
        connection.rollback()
        raise


def _like_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _snapshot_params(seed: SandboxSeed, *, kind: str) -> dict[str, str]:
    snapshot_id = (
        seed.review_item_snapshot_id
        if kind == "review_item"
        else seed.evidence_digest_snapshot_id
    )
    payload = {
        "snapshot_id": snapshot_id,
        "run_id": seed.run_id,
        "trade_date": seed.trade_date,
        "asset_id": seed.asset_id,
        "digest_key": seed.digest_key,
        "kind": kind,
    }
    payload_text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        **payload,
        "stock_name": f"Playwright {seed.run_id}",
        "payload": payload_text,
        "payload_hash": hashlib.sha256(payload_text.encode("utf-8")).hexdigest(),
    }


def cleanup_sandbox(connection: Any, run_id: str) -> None:
    seed = build_sandbox_seed(run_id)
    try:
        _assert_connection_is_sandbox(connection)
        username_pattern = f"e2e\\_{_like_literal(seed.run_id)}\\_%"
        id_pattern = f"{_like_literal(seed.run_id)}:%"
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM identity.user_session
                WHERE user_id LIKE %(id_pattern)s ESCAPE '\\'
                   OR user_id IN (
                       SELECT user_id FROM identity.user_account
                       WHERE username LIKE %(username_pattern)s ESCAPE '\\'
                   )
                """,
                {"id_pattern": id_pattern, "username_pattern": username_pattern},
            )
            cursor.execute(
                """
                DELETE FROM identity.auth_audit_log
                WHERE actor_user_id LIKE %(id_pattern)s ESCAPE '\\'
                   OR target_user_id LIKE %(id_pattern)s ESCAPE '\\'
                   OR username LIKE %(username_pattern)s ESCAPE '\\'
                """,
                {"id_pattern": id_pattern, "username_pattern": username_pattern},
            )
            cursor.execute(
                """
                DELETE FROM identity.user_account
                WHERE user_id LIKE %(id_pattern)s ESCAPE '\\'
                   OR username LIKE %(username_pattern)s ESCAPE '\\'
                """,
                {"id_pattern": id_pattern, "username_pattern": username_pattern},
            )
            cursor.execute(
                """
                DELETE FROM ops.operator_decision_event
                WHERE event_id LIKE %(id_pattern)s ESCAPE '\\'
                   OR review_session_id = %(review_session_id)s
                """,
                {"id_pattern": id_pattern, "review_session_id": seed.review_session_id},
            )
            cursor.execute(
                "DELETE FROM ops.operator_review_session WHERE review_session_id = %(review_session_id)s",
                {"review_session_id": seed.review_session_id},
            )
            cursor.execute(
                "DELETE FROM ops.evidence_digest_snapshot WHERE run_id = %(run_id)s",
                {"run_id": seed.run_id},
            )
            cursor.execute(
                "DELETE FROM ops.review_item_snapshot WHERE run_id = %(run_id)s",
                {"run_id": seed.run_id},
            )
            cursor.execute(
                "DELETE FROM market_daily_bar WHERE asset_id = %(asset_id)s AND source = 'playwright_sandbox'",
                {"asset_id": seed.asset_id},
            )
            cursor.execute(
                "DELETE FROM asset_master WHERE asset_id = %(asset_id)s AND source = 'playwright_sandbox'",
                {"asset_id": seed.asset_id},
            )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
