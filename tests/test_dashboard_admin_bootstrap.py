import sys
import types

import pytest

from stock_research.dashboard import user_admin

sys.modules.setdefault("tushare", types.ModuleType("tushare"))

from stock_research import cli


class _Cursor:
    def __init__(self, *, rows=None):
        self.rows = list(rows or [])
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)


class _Connection:
    def __init__(self, *, rows=None):
        self.cursor_obj = _Cursor(rows=rows)

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_bootstrap_admin_account_creates_first_admin_and_writes_audit(monkeypatch):
    conn = _Connection(
        rows=[
            {"active_admin_count": 0},
            {
                "id": 7,
                "username": "bootstrap-admin",
                "email": "bootstrap@example.com",
                "display_name": "Bootstrap Admin",
                "role": "admin",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "last_login_at": None,
                "password_updated_at": "2026-01-01T00:00:00Z",
                "disabled_at": None,
            },
        ]
    )

    monkeypatch.setattr(user_admin, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(user_admin, "hash_password", lambda password: f"hashed::{password}")

    result = user_admin.bootstrap_admin_account(
        username="bootstrap-admin",
        password="secret123",
        display_name="Bootstrap Admin",
        email="bootstrap@example.com",
    )

    check_sql, check_params = conn.cursor_obj.calls[0]
    insert_sql, insert_params = conn.cursor_obj.calls[1]
    audit_sql, audit_params = conn.cursor_obj.calls[2]
    assert result["id"] == 7
    assert "COUNT(*) AS active_admin_count" in check_sql
    assert check_params is None
    assert "INSERT INTO identity.user_account" in insert_sql
    assert insert_params["username"] == "bootstrap-admin"
    assert insert_params["password_hash"] == "hashed::secret123"
    assert "'admin'" in insert_sql
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["actor_user_id"] == 7
    assert audit_params["action"] == "bootstrap_admin_account"
    assert audit_params["target_id"] == "7"
    assert audit_params["metadata"] == '{"username": "bootstrap-admin"}'


def test_bootstrap_admin_account_rejects_when_active_admin_exists(monkeypatch):
    conn = _Connection(rows=[{"active_admin_count": 1}])

    monkeypatch.setattr(user_admin, "connect", lambda service: _Context(conn))

    with pytest.raises(ValueError, match="active admin already exists"):
        user_admin.bootstrap_admin_account(
            username="bootstrap-admin",
            password="secret123",
            display_name="Bootstrap Admin",
            email="bootstrap@example.com",
        )

    assert len(conn.cursor_obj.calls) == 1


def test_enable_user_account_by_username_reenables_disabled_user(monkeypatch):
    conn = _Connection(rows=[{"id": 22}])

    monkeypatch.setattr(user_admin, "connect", lambda service: _Context(conn))

    result = user_admin.enable_user_account_by_username(
        username="disabled-user",
        actor_user_id=5,
        ip_address="203.0.113.10",
        user_agent="pytest-agent",
    )

    assert result is True
    assert len(conn.cursor_obj.calls) == 2
    update_sql, update_params = conn.cursor_obj.calls[0]
    audit_sql, audit_params = conn.cursor_obj.calls[1]
    assert "WHERE username = %(username)s" in update_sql
    assert update_params == {"username": "disabled-user"}
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["actor_user_id"] == 5
    assert audit_params["action"] == "admin_enable_user"
    assert audit_params["target_id"] == "22"


def test_dashboard_bootstrap_admin_cli_dispatches_and_prints(monkeypatch, capsys):
    captured = {}

    def fake_bootstrap_admin_account(**kwargs):
        captured["call"] = kwargs
        return {"username": kwargs["username"]}

    monkeypatch.setattr(cli, "bootstrap_admin_account", fake_bootstrap_admin_account)

    cli.main_for_args(
        [
            "dashboard-bootstrap-admin",
            "--username",
            "bootstrap-admin",
            "--password",
            "secret123",
            "--display-name",
            "Bootstrap Admin",
            "--email",
            "bootstrap@example.com",
        ]
    )

    assert captured["call"] == {
        "username": "bootstrap-admin",
        "password": "secret123",
        "display_name": "Bootstrap Admin",
        "email": "bootstrap@example.com",
    }
    assert capsys.readouterr().out.strip() == "dashboard_admin_bootstrapped|bootstrap-admin"


def test_dashboard_enable_user_cli_exits_when_username_not_found(monkeypatch, capsys):
    def fake_enable_user_account_by_username(**kwargs):
        return False

    monkeypatch.setattr(
        cli,
        "enable_user_account_by_username",
        fake_enable_user_account_by_username,
    )

    with pytest.raises(SystemExit, match="dashboard user not found: missing-user"):
        cli.main_for_args(
            [
                "dashboard-enable-user",
                "--username",
                "missing-user",
            ]
        )

    assert capsys.readouterr().out == ""
