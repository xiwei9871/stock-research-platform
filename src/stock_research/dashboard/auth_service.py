from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from stock_research.config import SETTINGS
from stock_research.dashboard.auth_models import CurrentUser
from stock_research.db import connect

PASSWORD_ITERATIONS = 260_000


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        expected = _unb64(digest_raw)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _unb64(salt_raw), iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_csrf(*, csrf_cookie: str, csrf_header: str) -> None:
    if not csrf_cookie or not csrf_header:
        raise PermissionError("csrf_token_required")
    if not hmac.compare_digest(csrf_cookie, csrf_header):
        raise PermissionError("csrf_token_mismatch")


def current_user_read_model(user: CurrentUser) -> dict:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
    }


def authenticate_user(username: str, password: str, service: str = SETTINGS.research_service) -> CurrentUser:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, username, display_name, role, is_active, password_hash
                FROM identity.user_account
                WHERE lower(username) = lower(%s)
                LIMIT 1
                """,
                (username,),
            )
            row = cur.fetchone()
    if not row:
        raise PermissionError("invalid_credentials")
    payload = dict(row)
    if not payload["is_active"]:
        raise PermissionError("user_disabled")
    if not verify_password(password, str(payload["password_hash"])):
        raise PermissionError("invalid_credentials")
    return CurrentUser(
        user_id=str(payload["user_id"]),
        username=str(payload["username"]),
        display_name=str(payload.get("display_name") or ""),
        role=str(payload["role"]),
        is_active=bool(payload["is_active"]),
    )


def create_session(
    user: CurrentUser,
    *,
    user_agent: str = "",
    ip_address: str = "",
    service: str = SETTINGS.research_service,
) -> dict:
    session_token = generate_token()
    csrf_token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SETTINGS.dashboard_session_ttl_seconds)
    session_id = f"dashboard_session:{uuid4()}"
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO identity.user_session (
                    session_id, user_id, session_token_hash, csrf_token_hash,
                    expires_at, user_agent, ip_address
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (session_id, user.user_id, token_hash(session_token), token_hash(csrf_token), expires_at, user_agent, ip_address),
            )
            cur.execute("UPDATE identity.user_account SET last_login_at = now() WHERE user_id = %s", (user.user_id,))
    return {
        "session_id": session_id,
        "session_token": session_token,
        "csrf_token": csrf_token,
        "expires_at": expires_at,
    }


def load_current_user_from_session(session_token: str, service: str = SETTINGS.research_service) -> CurrentUser | None:
    if not session_token:
        return None
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.user_id, u.username, u.display_name, u.role, u.is_active
                FROM identity.user_session s
                JOIN identity.user_account u ON u.user_id = s.user_id
                WHERE s.session_token_hash = %s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > now()
                  AND u.is_active = true
                LIMIT 1
                """,
                (token_hash(session_token),),
            )
            row = cur.fetchone()
    if not row:
        return None
    payload = dict(row)
    return CurrentUser(
        user_id=str(payload["user_id"]),
        username=str(payload["username"]),
        display_name=str(payload.get("display_name") or ""),
        role=str(payload["role"]),
        is_active=bool(payload["is_active"]),
    )


def revoke_session(session_token: str, service: str = SETTINGS.research_service) -> None:
    if not session_token:
        return
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE identity.user_session
                SET revoked_at = now()
                WHERE session_token_hash = %s AND revoked_at IS NULL
                """,
                (token_hash(session_token),),
            )
