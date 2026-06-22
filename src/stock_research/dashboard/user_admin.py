from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.dashboard.auth import hash_password


USER_ACCOUNT_COLUMNS = """
    id,
    username,
    email,
    display_name,
    role,
    is_active,
    created_at,
    updated_at,
    last_login_at,
    password_updated_at,
    disabled_at
"""


def list_user_accounts(*, service: str = SETTINGS.research_service) -> list[dict[str, object]]:
    sql = f"""
    SELECT {USER_ACCOUNT_COLUMNS}
    FROM identity.user_account
    ORDER BY id ASC
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [_serialize_user_account(row) for row in rows]


def create_user_account(
    *,
    username: str,
    email: str | None,
    display_name: str,
    password: str,
    role: str,
    service: str = SETTINGS.research_service,
) -> dict[str, object]:
    sql = f"""
    INSERT INTO identity.user_account (
        username,
        email,
        password_hash,
        display_name,
        role
    )
    VALUES (
        %(username)s,
        %(email)s,
        %(password_hash)s,
        %(display_name)s,
        %(role)s
    )
    RETURNING {USER_ACCOUNT_COLUMNS}
    """
    params = {
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "display_name": display_name,
        "role": role,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    if row is None:
        raise RuntimeError("failed to create user account")
    return _serialize_user_account(row)


def reset_user_password(
    *,
    user_id: int,
    password: str,
    service: str = SETTINGS.research_service,
) -> bool:
    sql = """
    UPDATE identity.user_account
    SET password_hash = %(password_hash)s,
        password_updated_at = now(),
        updated_at = now()
    WHERE id = %(user_id)s
    RETURNING id
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                {
                    "user_id": user_id,
                    "password_hash": hash_password(password),
                },
            )
            row = cur.fetchone()
    return row is not None


def set_user_active_state(
    *,
    user_id: int,
    is_active: bool,
    service: str = SETTINGS.research_service,
) -> bool:
    sql = """
    UPDATE identity.user_account
    SET is_active = %(is_active)s,
        disabled_at = CASE
            WHEN %(is_active)s THEN NULL
            ELSE now()
        END,
        updated_at = now()
    WHERE id = %(user_id)s
    RETURNING id
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                {
                    "user_id": user_id,
                    "is_active": is_active,
                },
            )
            row = cur.fetchone()
    return row is not None


def disable_user_account(*, user_id: int, service: str = SETTINGS.research_service) -> bool:
    return set_user_active_state(user_id=user_id, is_active=False, service=service)


def enable_user_account(*, user_id: int, service: str = SETTINGS.research_service) -> bool:
    return set_user_active_state(user_id=user_id, is_active=True, service=service)


def _serialize_user_account(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "is_active": row["is_active"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
        "password_updated_at": row["password_updated_at"],
        "disabled_at": row["disabled_at"],
    }
