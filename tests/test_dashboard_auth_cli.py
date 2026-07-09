from stock_research import cli


def test_dashboard_auth_init_command_applies_schema(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(cli, "apply_dashboard_auth_schema", lambda: called.append(True))

    cli.main(["dashboard-auth-init"])

    assert called == [True]
    assert "dashboard_auth_schema_applied" in capsys.readouterr().out


def test_dashboard_admin_create_uses_service(monkeypatch, capsys):
    captured = {}

    def _create_dashboard_user(username, password, *, role, display_name):
        captured.update({"username": username, "password": password, "role": role, "display_name": display_name})
        return {"user_id": "user:1", "username": username}

    monkeypatch.setattr(cli, "create_dashboard_user", _create_dashboard_user)

    cli.main(["dashboard-admin-create", "--username", "admin", "--password", "secret", "--role", "admin"])

    assert captured["username"] == "admin"
    assert captured["password"] == "secret"
    assert captured["role"] == "admin"
    assert captured["display_name"] == ""
    assert "dashboard_admin_user_created|user:1|admin" in capsys.readouterr().out
