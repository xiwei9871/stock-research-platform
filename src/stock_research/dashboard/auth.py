import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.dashboard.user_models import CurrentUser


LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_LOOKBACK_MINUTES = 15
PASSWORD_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError, TypeError):
        return False


def count_recent_login_failures(
    *,
    identifier: str,
    ip_address: str | None = None,
    service: str = SETTINGS.research_service,
) -> int:
    sql = """
    SELECT COUNT(*) AS failure_count
    FROM audit.audit_log
    WHERE action = 'login_failed'
      AND created_at >= %(since)s
      AND (
        metadata->>'identifier' = %(identifier)s
        OR ip_address = %(ip_address)s
      )
    """
    params = {
        "identifier": identifier,
        "ip_address": ip_address,
        "since": datetime.now(UTC) - timedelta(minutes=LOGIN_FAILURE_LOOKBACK_MINUTES),
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    if row is None:
        return 0
    return int(row["failure_count"])


def authenticate_dashboard_user(
    identifier: str,
    password: str,
    *,
    service: str = SETTINGS.research_service,
) -> CurrentUser | None:
    sql = """
    SELECT id, username, display_name, role, is_active, password_hash
    FROM identity.user_account
    WHERE (username = %(identifier)s OR email = %(identifier)s)
      AND disabled_at IS NULL
    LIMIT 1
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"identifier": identifier})
            row = cur.fetchone()
            if (
                row is None
                or not bool(row["is_active"])
                or not verify_password(password, str(row["password_hash"]))
            ):
                return None
            cur.execute(
                """
                UPDATE identity.user_account
                SET last_login_at = now(), updated_at = now()
                WHERE id = %(user_id)s
                """,
                {"user_id": row["id"]},
            )
    return CurrentUser(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
    )


def create_user_session(
    current_user: CurrentUser,
    *,
    request: Request | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, object]:
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(hours=SETTINGS.dashboard_session_ttl_hours)
    sql = """
    INSERT INTO identity.user_session (
        user_id, session_token_hash, csrf_token_hash, ip_address, user_agent, expires_at
    )
    VALUES (
        %(user_id)s, %(session_token_hash)s, %(csrf_token_hash)s,
        %(ip_address)s, %(user_agent)s, %(expires_at)s
    )
    RETURNING id
    """
    params = {
        "user_id": current_user.id,
        "session_token_hash": _hash_token(session_token),
        "csrf_token_hash": _hash_token(csrf_token),
        "ip_address": _client_ip(request),
        "user_agent": _user_agent(request),
        "expires_at": expires_at,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    return {
        "session_id": None if row is None else row["id"],
        "session_token": session_token,
        "csrf_token": csrf_token,
        "expires_at": expires_at,
    }


def revoke_user_session(
    request: Request,
    *,
    service: str = SETTINGS.research_service,
) -> None:
    session_token = request.cookies.get(SETTINGS.dashboard_session_cookie_name)
    if not session_token:
        return
    sql = """
    UPDATE identity.user_session
    SET revoked_at = now()
    WHERE session_token_hash = %(session_token_hash)s
      AND revoked_at IS NULL
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"session_token_hash": _hash_token(session_token)})


def load_current_user_from_request(
    request: Request,
    *,
    service: str = SETTINGS.research_service,
) -> CurrentUser | None:
    cached_user = getattr(request.state, "current_user", None)
    if cached_user is not None:
        return cached_user
    session_token = request.cookies.get(SETTINGS.dashboard_session_cookie_name)
    if not session_token:
        return None
    sql = """
    SELECT
        ua.id AS user_id,
        ua.username,
        ua.display_name,
        ua.role,
        ua.is_active,
        us.id AS session_id,
        us.csrf_token_hash
    FROM identity.user_session us
    JOIN identity.user_account ua
      ON ua.id = us.user_id
    WHERE us.session_token_hash = %(session_token_hash)s
      AND us.revoked_at IS NULL
      AND us.expires_at > now()
      AND ua.is_active IS TRUE
      AND ua.disabled_at IS NULL
    LIMIT 1
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"session_token_hash": _hash_token(session_token)})
            row = cur.fetchone()
    if row is None:
        return None
    current_user = CurrentUser(
        id=int(row["user_id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
    )
    request.state.current_user = current_user
    request.state.auth_session = {
        "session_id": row["session_id"],
        "csrf_token_hash": row["csrf_token_hash"],
    }
    return current_user


def attach_auth_cookies(response: Response, session: dict[str, object]) -> None:
    max_age = SETTINGS.dashboard_session_ttl_hours * 60 * 60
    response.set_cookie(
        SETTINGS.dashboard_session_cookie_name,
        str(session["session_token"]),
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=SETTINGS.dashboard_secure_cookies,
    )
    response.set_cookie(
        SETTINGS.dashboard_csrf_cookie_name,
        str(session["csrf_token"]),
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=SETTINGS.dashboard_secure_cookies,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        SETTINGS.dashboard_session_cookie_name,
        httponly=True,
        samesite="lax",
        secure=SETTINGS.dashboard_secure_cookies,
    )
    response.delete_cookie(
        SETTINGS.dashboard_csrf_cookie_name,
        httponly=False,
        samesite="lax",
        secure=SETTINGS.dashboard_secure_cookies,
    )


def require_current_user(request: Request) -> CurrentUser:
    current_user = load_current_user_from_request(request)
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return current_user


def require_admin_user(current_user: CurrentUser = Depends(require_current_user)) -> CurrentUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin required")
    return current_user


def require_csrf(request: Request) -> None:
    current_user = load_current_user_from_request(request)
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    auth_session = getattr(request.state, "auth_session", None)
    csrf_header = request.headers.get("X-CSRF-Token", "")
    csrf_cookie = request.cookies.get(SETTINGS.dashboard_csrf_cookie_name, "")
    if not csrf_header or not csrf_cookie or not hmac.compare_digest(csrf_header, csrf_cookie):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token required")
    if auth_session is None or not hmac.compare_digest(
        _hash_token(csrf_header),
        str(auth_session["csrf_token_hash"]),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token required")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("user-agent")
