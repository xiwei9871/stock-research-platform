import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "smoke_platform_external_access.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("smoke_platform_external_access", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_smoke_script_checks_root_api_request_id_api_fallback_and_write_guard():
    smoke = _load_script()
    calls = []

    def fake_request(method, url, *, headers, body=None, timeout=10.0):
        calls.append({"method": method, "url": url, "headers": dict(headers), "body": body, "timeout": timeout})
        if url.endswith("/api/platform/summary"):
            assert headers["X-Request-ID"] == "platform-external-smoke-001"
            assert headers["Authorization"].startswith("Basic ")
            return {"status": 200, "headers": {"x-request-id": "platform-external-smoke-001"}, "body": b'{"ok": true}'}
        if url.endswith("/api/__external_smoke_missing"):
            return {"status": 404, "headers": {"content-type": "application/json"}, "body": b'{"detail": "not found"}'}
        if url.endswith("/api/dashboard/cache/clear"):
            return {"status": 403, "headers": {"content-type": "application/json"}, "body": b'{"detail": "missing_dashboard_write_token"}'}
        return {"status": 200, "headers": {"content-type": "text/html"}, "body": b"<div id=\"root\"></div>"}

    result = smoke.run_smoke(
        "https://stock-research.example.com",
        basic_auth_user="reviewer",
        basic_auth_password="secret",
        timeout=2.5,
        check_write_guard=True,
        request_func=fake_request,
    )

    assert result["passed"] is True
    assert result["status"] == "passed"
    assert {step["name"] for step in result["steps"]} == {
        "root",
        "platform_summary",
        "api_missing_path",
        "write_guard_without_token",
    }
    assert calls[0]["url"] == "https://stock-research.example.com/"
    assert calls[1]["url"] == "https://stock-research.example.com/api/platform/summary"
    assert calls[3]["method"] == "POST"


def test_smoke_script_checks_first_party_auth_session_admin_and_write_guard():
    smoke = _load_script()
    calls = []

    def fake_request(method, url, *, headers, body=None, timeout=10.0):
        calls.append({"method": method, "url": url, "headers": dict(headers), "body": body, "timeout": timeout})
        if url.endswith("/api/platform/summary"):
            return {"status": 200, "headers": {"x-request-id": "platform-external-smoke-001"}, "body": b"{}"}
        if url.endswith("/api/__external_smoke_missing"):
            return {"status": 404, "headers": {"content-type": "application/json"}, "body": b'{"detail": "not found"}'}
        if url.endswith("/api/auth/me") and "Cookie" not in headers:
            return {"status": 401, "headers": {"content-type": "application/json"}, "body": b'{"detail": "not_authenticated"}'}
        if url.endswith("/api/auth/login"):
            assert method == "POST"
            assert headers["Content-Type"] == "application/json"
            assert body == b'{"username":"admin","password":"secret"}'
            return {
                "status": 200,
                "headers": {
                    "content-type": "application/json",
                    "set-cookie-list": [
                        "stock_research_session=session-token; HttpOnly; Path=/",
                        "stock_research_csrf=csrf-token; Path=/",
                    ],
                },
                "body": b'{"user": {"username": "admin", "role": "admin"}}',
            }
        if url.endswith("/api/auth/me") and "stock_research_session=session-token" in headers.get("Cookie", ""):
            return {"status": 200, "headers": {"content-type": "application/json"}, "body": b'{"user": {"username": "admin"}}'}
        if url.endswith("/api/admin/users"):
            assert "stock_research_session=session-token" in headers.get("Cookie", "")
            return {"status": 200, "headers": {"content-type": "application/json"}, "body": b'{"items": []}'}
        if url.endswith("/api/dashboard/cache/clear"):
            assert "stock_research_session=session-token" in headers.get("Cookie", "")
            return {"status": 403, "headers": {"content-type": "application/json"}, "body": b'{"detail": "missing_dashboard_write_token"}'}
        return {"status": 200, "headers": {"content-type": "text/html"}, "body": b"<div id=\"root\"></div>"}

    result = smoke.run_smoke(
        "https://stock-research.example.com",
        auth_username="admin",
        auth_password="secret",
        check_first_party_auth=True,
        check_admin_users=True,
        check_write_guard=True,
        request_func=fake_request,
    )

    assert result["passed"] is True
    assert {step["name"] for step in result["steps"]} == {
        "root",
        "platform_summary",
        "api_missing_path",
        "auth_me_without_session",
        "auth_login",
        "auth_me_with_session",
        "admin_users",
        "write_guard_without_token",
    }


def test_smoke_script_internal_mode_uses_first_party_auth_without_basic_auth():
    smoke = _load_script()
    seen_authorization_headers = []

    def fake_request(method, url, *, headers, body=None, timeout=10.0):
        seen_authorization_headers.append(headers.get("Authorization", ""))
        if url.endswith("/api/platform/summary"):
            return {"status": 200, "headers": {"x-request-id": "platform-external-smoke-001"}, "body": b"{}"}
        if url.endswith("/api/__external_smoke_missing"):
            return {"status": 404, "headers": {"content-type": "application/json"}, "body": b"{}"}
        if url.endswith("/api/auth/me") and "Cookie" not in headers:
            return {"status": 401, "headers": {}, "body": b"{}"}
        if url.endswith("/api/auth/login"):
            return {
                "status": 200,
                "headers": {"set-cookie-list": ["stock_research_session=session-token; Path=/"]},
                "body": b"{}",
            }
        if url.endswith("/api/auth/me"):
            return {"status": 200, "headers": {}, "body": b"{}"}
        if url.endswith("/api/dashboard/cache/clear"):
            return {"status": 403, "headers": {}, "body": b"{}"}
        return {"status": 200, "headers": {"content-type": "text/html"}, "body": b"<div id=\"root\"></div>"}

    result = smoke.run_smoke(
        "http://stock-research-internal.local",
        internal=True,
        check_first_party_auth=True,
        auth_username="admin",
        auth_password="secret",
        check_write_guard=True,
        request_func=fake_request,
    )

    assert result["passed"] is True
    assert result["access_mode"] == "internal"
    assert all(header == "" for header in seen_authorization_headers)


def test_smoke_script_internal_auth_required_checks_platform_summary_after_login():
    smoke = _load_script()
    summary_cookies = []

    def fake_request(method, url, *, headers, body=None, timeout=10.0):
        if url.endswith("/api/platform/summary"):
            summary_cookies.append(headers.get("Cookie", ""))
            if "stock_research_session=session-token" in headers.get("Cookie", ""):
                return {"status": 200, "headers": {"x-request-id": "platform-external-smoke-001"}, "body": b"{}"}
            return {"status": 401, "headers": {}, "body": b'{"detail":"not_authenticated"}'}
        if url.endswith("/api/__external_smoke_missing"):
            return {"status": 401, "headers": {"content-type": "application/json"}, "body": b"{}"}
        if url.endswith("/api/auth/me") and "Cookie" not in headers:
            return {"status": 401, "headers": {}, "body": b"{}"}
        if url.endswith("/api/auth/login"):
            return {
                "status": 200,
                "headers": {"set-cookie-list": ["stock_research_session=session-token; Path=/"]},
                "body": b"{}",
            }
        if url.endswith("/api/auth/me"):
            return {"status": 200, "headers": {}, "body": b"{}"}
        return {"status": 200, "headers": {"content-type": "text/html"}, "body": b"<div id=\"root\"></div>"}

    result = smoke.run_smoke(
        "http://stock-research-internal.local",
        internal=True,
        check_first_party_auth=True,
        auth_username="admin",
        auth_password="secret",
        request_func=fake_request,
    )

    assert result["passed"] is True
    assert summary_cookies == ["", "stock_research_session=session-token"]
    assert any(step["name"] == "platform_summary_with_session" and step["passed"] for step in result["steps"])


def test_smoke_script_checks_regular_user_cannot_access_admin_users():
    smoke = _load_script()
    admin_user_requests = []

    def fake_request(method, url, *, headers, body=None, timeout=10.0):
        if url.endswith("/api/platform/summary"):
            return {"status": 200, "headers": {"x-request-id": "platform-external-smoke-001"}, "body": b"{}"}
        if url.endswith("/api/__external_smoke_missing"):
            return {"status": 404, "headers": {"content-type": "application/json"}, "body": b"{}"}
        if url.endswith("/api/auth/me") and "Cookie" not in headers:
            return {"status": 401, "headers": {}, "body": b"{}"}
        if url.endswith("/api/auth/login") and body == b'{"username":"admin","password":"secret"}':
            return {
                "status": 200,
                "headers": {"set-cookie-list": ["stock_research_session=admin-session; Path=/"]},
                "body": b"{}",
            }
        if url.endswith("/api/auth/login") and body == b'{"username":"analyst","password":"analyst-secret"}':
            return {
                "status": 200,
                "headers": {"set-cookie-list": ["stock_research_session=user-session; Path=/"]},
                "body": b"{}",
            }
        if url.endswith("/api/auth/me"):
            return {"status": 200, "headers": {}, "body": b"{}"}
        if url.endswith("/api/admin/users"):
            admin_user_requests.append(headers.get("Cookie", ""))
            if "stock_research_session=admin-session" in headers.get("Cookie", ""):
                return {"status": 200, "headers": {}, "body": b'{"items":[]}'}
            return {"status": 403, "headers": {}, "body": b'{"detail":"admin_required"}'}
        return {"status": 200, "headers": {"content-type": "text/html"}, "body": b"<div id=\"root\"></div>"}

    result = smoke.run_smoke(
        "http://stock-research-internal.local",
        internal=True,
        check_first_party_auth=True,
        auth_username="admin",
        auth_password="secret",
        check_admin_users=True,
        check_regular_user_admin_denied=True,
        regular_auth_username="analyst",
        regular_auth_password="analyst-secret",
        request_func=fake_request,
    )

    assert result["passed"] is True
    assert any(step["name"] == "regular_admin_users_denied" and step["passed"] for step in result["steps"])
    assert admin_user_requests == ["stock_research_session=admin-session", "stock_research_session=user-session"]


def test_smoke_script_fails_when_api_path_is_served_by_spa_fallback():
    smoke = _load_script()

    def fake_request(method, url, *, headers, body=None, timeout=10.0):
        if url.endswith("/api/platform/summary"):
            return {"status": 200, "headers": {"x-request-id": "platform-external-smoke-001"}, "body": b"{}"}
        if url.endswith("/api/__external_smoke_missing"):
            return {"status": 200, "headers": {"content-type": "text/html"}, "body": b"<html><div id=\"root\"></div></html>"}
        return {"status": 200, "headers": {"content-type": "text/html"}, "body": b"<html></html>"}

    result = smoke.run_smoke("https://stock-research.example.com", request_func=fake_request)

    assert result["passed"] is False
    assert result["status"] == "failed"
    api_fallback_step = next(step for step in result["steps"] if step["name"] == "api_missing_path")
    assert api_fallback_step["passed"] is False
    assert "served_by_spa_fallback" in api_fallback_step["message"]


def test_smoke_script_accepts_expected_basic_auth_challenge_without_credentials():
    smoke = _load_script()

    def fake_request(method, url, *, headers, body=None, timeout=10.0):
        return {"status": 401, "headers": {"www-authenticate": "Basic realm=\"Stock Research staging\""}, "body": b""}

    result = smoke.run_smoke("https://stock-research.example.com", expect_auth=True, request_func=fake_request)

    assert result["passed"] is True
    assert result["status"] == "auth_challenge_confirmed"
    assert result["steps"] == [
        {
            "name": "root_auth_challenge",
            "passed": True,
            "status": 401,
            "message": "basic_auth_or_upstream_auth_challenge_confirmed",
        }
    ]


def test_smoke_request_ignores_system_proxy_for_loopback_addresses():
    smoke = _load_script()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # pragma: no cover - keeps test output quiet
            return

        def do_GET(self):
            self.send_response(200)
            self.send_header("content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = smoke._request("GET", f"http://127.0.0.1:{server.server_port}/", headers={}, timeout=3)
    finally:
        server.shutdown()

    assert response["status"] == 200
    assert response["body"] == b"ok"
