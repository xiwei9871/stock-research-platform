#!/usr/bin/env python3
"""Smoke test staging external access for the stock research dashboard."""

from __future__ import annotations

import argparse
import base64
from http.cookies import SimpleCookie
import json
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import ProxyHandler, Request, build_opener


RequestFunc = Callable[..., dict[str, Any]]
SMOKE_REQUEST_ID = "platform-external-smoke-001"


def _basic_auth_header(username: str | None, password: str | None) -> str | None:
    if not username or password is None:
        return None
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _headers_with_auth(username: str | None, password: str | None) -> dict[str, str]:
    headers: dict[str, str] = {"User-Agent": "stock-research-platform-smoke/1.0"}
    authorization = _basic_auth_header(username, password)
    if authorization:
        headers["Authorization"] = authorization
    return headers


def _request(method: str, url: str, *, headers: dict[str, str], body: bytes | None = None, timeout: float = 10.0) -> dict[str, Any]:
    request = Request(url, data=body, method=method, headers=headers)
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            set_cookie_values = response.headers.get_all("Set-Cookie") or []
            if set_cookie_values:
                response_headers["set-cookie-list"] = set_cookie_values
            return {
                "status": int(response.status),
                "headers": response_headers,
                "body": response.read(),
            }
    except HTTPError as exc:
        error_headers = {key.lower(): value for key, value in exc.headers.items()}
        set_cookie_values = exc.headers.get_all("Set-Cookie") or []
        if set_cookie_values:
            error_headers["set-cookie-list"] = set_cookie_values
        return {
            "status": int(exc.code),
            "headers": error_headers,
            "body": exc.read(),
        }
    except URLError as exc:
        return {"status": 0, "headers": {}, "body": str(exc.reason).encode("utf-8")}


def _step(name: str, passed: bool, status: int, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "status": status, "message": message}


def _body_text(response: dict[str, Any]) -> str:
    body = response.get("body") or b""
    if isinstance(body, bytes):
        return body[:4096].decode("utf-8", errors="replace")
    return str(body)[:4096]


def _is_spa_fallback(response: dict[str, Any]) -> bool:
    content_type = str(response.get("headers", {}).get("content-type", "")).lower()
    body = _body_text(response).lower()
    return response.get("status") == 200 and ("text/html" in content_type or '<div id="root"' in body or "<!doctype html" in body)


def _url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _json_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _cookies_from_response(response: dict[str, Any]) -> dict[str, str]:
    headers = response.get("headers", {})
    values = headers.get("set-cookie-list") or headers.get("set-cookie") or []
    if isinstance(values, str):
        values = [values]
    cookies: dict[str, str] = {}
    for value in values:
        parsed = SimpleCookie()
        parsed.load(str(value))
        for key, morsel in parsed.items():
            cookies[key] = morsel.value
    return cookies


def _cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items())


def run_smoke(
    base_url: str,
    *,
    internal: bool = False,
    basic_auth_user: str | None = None,
    basic_auth_password: str | None = None,
    auth_username: str | None = None,
    auth_password: str | None = None,
    regular_auth_username: str | None = None,
    regular_auth_password: str | None = None,
    check_first_party_auth: bool = False,
    check_admin_users: bool = False,
    check_regular_user_admin_denied: bool = False,
    expect_auth: bool = False,
    timeout: float = 10.0,
    check_write_guard: bool = False,
    request_func: RequestFunc = _request,
) -> dict[str, Any]:
    headers = _headers_with_auth(basic_auth_user, basic_auth_password)
    root = request_func("GET", _url(base_url, "/"), headers=headers, timeout=timeout)
    steps: list[dict[str, Any]] = []

    if expect_auth and not basic_auth_user and root["status"] in {401, 403}:
        return {
            "base_url": base_url,
            "status": "auth_challenge_confirmed",
            "passed": True,
            "steps": [
                _step(
                    "root_auth_challenge",
                    True,
                    int(root["status"]),
                    "basic_auth_or_upstream_auth_challenge_confirmed",
                )
            ],
        }

    steps.append(_step("root", int(root["status"]) == 200, int(root["status"]), "root_should_return_dashboard_shell"))

    api_headers = dict(headers)
    api_headers["X-Request-ID"] = SMOKE_REQUEST_ID
    summary = request_func("GET", _url(base_url, "/api/platform/summary"), headers=api_headers, timeout=timeout)
    summary_headers = summary.get("headers", {})
    request_id = str(summary_headers.get("x-request-id") or summary_headers.get("X-Request-ID") or "")
    summary_requires_session = internal and check_first_party_auth and int(summary["status"]) in {401, 403}
    steps.append(
        _step(
            "platform_summary",
            summary_requires_session or (int(summary["status"]) == 200 and request_id == SMOKE_REQUEST_ID),
            int(summary["status"]),
            "platform_summary_requires_session"
            if summary_requires_session
            else "platform_summary_should_return_200_and_echo_x_request_id",
        )
    )

    missing_api = request_func("GET", _url(base_url, "/api/__external_smoke_missing"), headers=headers, timeout=timeout)
    served_by_spa = _is_spa_fallback(missing_api)
    steps.append(
        _step(
            "api_missing_path",
            not served_by_spa,
            int(missing_api["status"]),
            "api_path_not_served_by_spa_fallback" if not served_by_spa else "served_by_spa_fallback",
        )
    )

    session_cookies: dict[str, str] = {}
    if check_first_party_auth:
        auth_me_without_session = request_func("GET", _url(base_url, "/api/auth/me"), headers=headers, timeout=timeout)
        steps.append(
            _step(
                "auth_me_without_session",
                int(auth_me_without_session["status"]) in {401, 403},
                int(auth_me_without_session["status"]),
                "auth_me_should_reject_missing_session",
            )
        )
        login_headers = dict(headers)
        login_headers["Content-Type"] = "application/json"
        login = request_func(
            "POST",
            _url(base_url, "/api/auth/login"),
            headers=login_headers,
            body=_json_body({"username": auth_username or "", "password": auth_password or ""}),
            timeout=timeout,
        )
        session_cookies = _cookies_from_response(login)
        has_session = "stock_research_session" in session_cookies
        steps.append(
            _step(
                "auth_login",
                int(login["status"]) == 200 and has_session,
                int(login["status"]),
                "login_should_return_200_and_session_cookie",
            )
        )
        if session_cookies:
            authed_headers = dict(headers)
            authed_headers["Cookie"] = _cookie_header(session_cookies)
            auth_me_with_session = request_func("GET", _url(base_url, "/api/auth/me"), headers=authed_headers, timeout=timeout)
            steps.append(
                _step(
                    "auth_me_with_session",
                    int(auth_me_with_session["status"]) == 200,
                    int(auth_me_with_session["status"]),
                    "auth_me_should_accept_session_cookie",
                )
            )
            if summary_requires_session:
                authed_api_headers = dict(authed_headers)
                authed_api_headers["X-Request-ID"] = SMOKE_REQUEST_ID
                authed_summary = request_func(
                    "GET",
                    _url(base_url, "/api/platform/summary"),
                    headers=authed_api_headers,
                    timeout=timeout,
                )
                authed_summary_headers = authed_summary.get("headers", {})
                authed_request_id = str(
                    authed_summary_headers.get("x-request-id")
                    or authed_summary_headers.get("X-Request-ID")
                    or ""
                )
                steps.append(
                    _step(
                        "platform_summary_with_session",
                        int(authed_summary["status"]) == 200 and authed_request_id == SMOKE_REQUEST_ID,
                        int(authed_summary["status"]),
                        "platform_summary_should_return_200_and_echo_x_request_id_after_login",
                    )
                )
            if check_admin_users:
                admin_users = request_func("GET", _url(base_url, "/api/admin/users"), headers=authed_headers, timeout=timeout)
                steps.append(
                    _step(
                        "admin_users",
                        int(admin_users["status"]) == 200,
                        int(admin_users["status"]),
                        "admin_users_should_return_200_for_admin_session",
                    )
                )
        elif check_admin_users:
            steps.append(_step("admin_users", False, 0, "admin_users_skipped_without_session_cookie"))

    if check_regular_user_admin_denied:
        regular_login_headers = dict(headers)
        regular_login_headers["Content-Type"] = "application/json"
        regular_login = request_func(
            "POST",
            _url(base_url, "/api/auth/login"),
            headers=regular_login_headers,
            body=_json_body({"username": regular_auth_username or "", "password": regular_auth_password or ""}),
            timeout=timeout,
        )
        regular_session_cookies = _cookies_from_response(regular_login)
        regular_has_session = "stock_research_session" in regular_session_cookies
        steps.append(
            _step(
                "regular_auth_login",
                int(regular_login["status"]) == 200 and regular_has_session,
                int(regular_login["status"]),
                "regular_user_login_should_return_200_and_session_cookie",
            )
        )
        if regular_session_cookies:
            regular_headers = dict(headers)
            regular_headers["Cookie"] = _cookie_header(regular_session_cookies)
            regular_admin_users = request_func("GET", _url(base_url, "/api/admin/users"), headers=regular_headers, timeout=timeout)
            steps.append(
                _step(
                    "regular_admin_users_denied",
                    int(regular_admin_users["status"]) in {401, 403},
                    int(regular_admin_users["status"]),
                    "regular_user_admin_users_should_be_denied",
                )
            )
        else:
            steps.append(_step("regular_admin_users_denied", False, 0, "regular_admin_users_skipped_without_session_cookie"))

    if check_write_guard:
        write_headers = dict(headers)
        write_headers["Content-Type"] = "application/json"
        if session_cookies:
            write_headers["Cookie"] = _cookie_header(session_cookies)
        write_response = request_func(
            "POST",
            _url(base_url, "/api/dashboard/cache/clear"),
            headers=write_headers,
            body=b"{}",
            timeout=timeout,
        )
        steps.append(
            _step(
                "write_guard_without_token",
                int(write_response["status"]) in {401, 403},
                int(write_response["status"]),
                "write_endpoint_should_reject_missing_x_dashboard_write_token",
            )
        )

    passed = all(bool(step["passed"]) for step in steps)
    return {
        "base_url": base_url,
        "access_mode": "internal" if internal else "staging_external",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "steps": steps,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test staging external access for Stock Research Dashboard.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--internal", action="store_true", help="Mark this as an internal-network first-party auth smoke.")
    parser.add_argument("--basic-auth-user")
    parser.add_argument("--basic-auth-password")
    parser.add_argument("--auth-username")
    parser.add_argument("--auth-password")
    parser.add_argument("--regular-auth-username")
    parser.add_argument("--regular-auth-password")
    parser.add_argument("--check-first-party-auth", action="store_true")
    parser.add_argument("--check-admin-users", action="store_true")
    parser.add_argument("--check-regular-user-admin-denied", action="store_true")
    parser.add_argument("--expect-auth", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--check-write-guard", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    result = run_smoke(
        args.base_url,
        internal=args.internal,
        basic_auth_user=args.basic_auth_user,
        basic_auth_password=args.basic_auth_password,
        auth_username=args.auth_username,
        auth_password=args.auth_password,
        regular_auth_username=args.regular_auth_username,
        regular_auth_password=args.regular_auth_password,
        check_first_party_auth=args.check_first_party_auth,
        check_admin_users=args.check_admin_users,
        check_regular_user_admin_denied=args.check_regular_user_admin_denied,
        expect_auth=args.expect_auth,
        timeout=args.timeout,
        check_write_guard=args.check_write_guard,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
