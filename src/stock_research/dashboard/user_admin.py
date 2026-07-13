from __future__ import annotations

from uuid import uuid4

from stock_research.config import SETTINGS
from stock_research.dashboard.auth_service import hash_password
from stock_research.db import connect

ALLOWED_ROLES = {"admin", "user"}


def admin_user_read_model(row: dict) -> dict:
    return {
        "user_id": str(row["user_id"]),
        "username": str(row["username"]),
        "display_name": str(row.get("display_name") or ""),
        "role": str(row["role"]),
        "is_active": bool(row["is_active"]),
        "created_at": str(row.get("created_at") or ""),
        "last_login_at": str(row.get("last_login_at") or ""),
    }


def list_admin_users(service: str = SETTINGS.research_service) -> list[dict]:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, username, display_name, role, is_active, created_at, last_login_at
                FROM identity.user_account
                ORDER BY lower(username)
                """
            )
            rows = cur.fetchall()
    return [admin_user_read_model(dict(row)) for row in rows]


def create_dashboard_user(
    username: str,
    password: str,
    *,
    role: str = "user",
    display_name: str = "",
    service: str = SETTINGS.research_service,
) -> dict:
    if role not in ALLOWED_ROLES:
        raise ValueError("invalid_role")
    user_id = f"dashboard_user:{uuid4()}"
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO identity.user_account (user_id, username, display_name, role, password_hash)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING user_id, username, display_name, role, is_active, created_at, last_login_at
                """,
                (user_id, username, display_name, role, hash_password(password)),
            )
            row = cur.fetchone()
    return admin_user_read_model(dict(row))


def reset_dashboard_user_password(
    user_id: str,
    password: str,
    *,
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE identity.user_account
                SET password_hash = %s, password_updated_at = now(), updated_at = now()
                WHERE user_id = %s
                """,
                (hash_password(password), user_id),
            )


def set_dashboard_user_active(
    user_id: str,
    is_active: bool,
    *,
    service: str = SETTINGS.research_service,
) -> None:
    disabled_expr = "NULL" if is_active else "now()"
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE identity.user_account
                SET is_active = %s, disabled_at = {disabled_expr}, updated_at = now()
                WHERE user_id = %s
                """,
                (is_active, user_id),
            )
