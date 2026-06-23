import json
from typing import Any
from typing import Literal

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
    role: Literal["admin", "user"],
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, object]:
    sql = f"""
    INSERT INTO identity.user_account (
        username,
        email,
        password_hash,
        display_name,
        role,
        password_updated_at
    )
    VALUES (
        %(username)s,
        %(email)s,
        %(password_hash)s,
        %(display_name)s,
        %(role)s,
        now()
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
            user_account = _serialize_user_account(row)
            _insert_audit_log(
                cur,
                actor_user_id=actor_user_id,
                action="admin_create_user",
                target_type="user_account",
                target_id=str(user_account["id"]),
                metadata={"username": str(user_account["username"])},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return user_account


def bootstrap_admin_account(
    *,
    username: str,
    password: str,
    display_name: str,
    email: str | None,
    service: str = SETTINGS.research_service,
) -> dict[str, object]:
    lock_user_account_sql = """
    LOCK TABLE identity.user_account IN EXCLUSIVE MODE
    """
    count_active_admins_sql = """
    SELECT COUNT(*) AS active_admin_count
    FROM identity.user_account
    WHERE role = 'admin'
      AND is_active = TRUE
    """
    insert_sql = f"""
    INSERT INTO identity.user_account (
        username,
        email,
        password_hash,
        display_name,
        role,
        password_updated_at
    )
    VALUES (
        %(username)s,
        %(email)s,
        %(password_hash)s,
        %(display_name)s,
        'admin',
        now()
    )
    RETURNING {USER_ACCOUNT_COLUMNS}
    """
    params = {
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "display_name": display_name,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(lock_user_account_sql)
            cur.execute(count_active_admins_sql)
            admin_count_row = cur.fetchone()
            active_admin_count = int(admin_count_row["active_admin_count"]) if admin_count_row else 0
            if active_admin_count > 0:
                raise ValueError("active admin already exists")
            cur.execute(insert_sql, params)
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("failed to bootstrap admin account")
            user_account = _serialize_user_account(row)
            _insert_audit_log(
                cur,
                actor_user_id=None,
                action="bootstrap_admin_account",
                target_type="user_account",
                target_id=str(user_account["id"]),
                metadata={"username": str(user_account["username"])},
            )
    return user_account


def reset_user_password(
    *,
    user_id: int,
    password: str,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
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
            if row is None:
                return False
            _revoke_user_sessions(cur, user_id=user_id)
            _insert_audit_log(
                cur,
                actor_user_id=actor_user_id,
                action="admin_reset_password",
                target_type="user_account",
                target_id=str(user_id),
                metadata={},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return True


def set_user_active_state(
    *,
    user_id: int,
    is_active: bool,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> bool:
    load_user_sql = """
    SELECT role, is_active
    FROM identity.user_account
    WHERE id = %(user_id)s
    """
    count_active_admins_sql = """
    SELECT COUNT(*) AS active_admin_count
    FROM identity.user_account
    WHERE role = 'admin'
      AND is_active = TRUE
    """
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
            if not is_active:
                cur.execute(load_user_sql, {"user_id": user_id})
                current_account = cur.fetchone()
                if current_account is None:
                    return False
                if current_account["role"] == "admin" and current_account["is_active"]:
                    if user_id == actor_user_id:
                        raise ValueError("admin users cannot disable themselves")
                    cur.execute(count_active_admins_sql)
                    admin_count_row = cur.fetchone()
                    active_admin_count = int(admin_count_row["active_admin_count"]) if admin_count_row else 0
                    if active_admin_count <= 1:
                        raise ValueError("cannot disable the last active admin")
            cur.execute(
                sql,
                {
                    "user_id": user_id,
                    "is_active": is_active,
                },
            )
            row = cur.fetchone()
            if row is None:
                return False
            if not is_active:
                _revoke_user_sessions(cur, user_id=user_id)
            _insert_audit_log(
                cur,
                actor_user_id=actor_user_id,
                action="admin_enable_user" if is_active else "admin_disable_user",
                target_type="user_account",
                target_id=str(user_id),
                metadata={},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return True


def disable_user_account(
    *,
    user_id: int,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> bool:
    return set_user_active_state(
        user_id=user_id,
        is_active=False,
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        service=service,
    )


def enable_user_account(
    *,
    user_id: int,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> bool:
    return set_user_active_state(
        user_id=user_id,
        is_active=True,
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        service=service,
    )


def enable_user_account_by_username(
    *,
    username: str,
    actor_user_id: int | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> bool:
    sql = """
    UPDATE identity.user_account
    SET is_active = TRUE,
        disabled_at = NULL,
        updated_at = now()
    WHERE username = %(username)s
    RETURNING id
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"username": username})
            row = cur.fetchone()
            if row is None:
                return False
            _insert_audit_log(
                cur,
                actor_user_id=actor_user_id,
                action="admin_enable_user",
                target_type="user_account",
                target_id=str(row["id"]),
                metadata={},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return True


def _revoke_user_sessions(cur, *, user_id: int) -> None:
    cur.execute(
        """
        UPDATE identity.user_session
        SET revoked_at = now()
        WHERE user_id = %(user_id)s
          AND revoked_at IS NULL
        """,
        {"user_id": user_id},
    )


def _insert_audit_log(
    cur,
    *,
    action: str,
    target_type: str,
    target_id: str,
    actor_user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO audit.audit_log (
            actor_user_id, action, target_type, target_id, metadata, ip_address, user_agent
        )
        VALUES (
            %(actor_user_id)s, %(action)s, %(target_type)s, %(target_id)s,
            %(metadata)s::jsonb, %(ip_address)s, %(user_agent)s
        )
        """,
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "metadata": json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            "ip_address": ip_address,
            "user_agent": user_agent,
        },
    )


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
