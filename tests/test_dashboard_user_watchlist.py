from fastapi import Request
from fastapi.testclient import TestClient
from psycopg import errors as psycopg_errors

from stock_research.dashboard import app as dashboard_app


class _FakeUser:
    def __init__(self, user_id: int = 7, username: str = "analyst"):
        self.id = user_id
        self.username = username
        self.display_name = "Analyst"
        self.role = "user"
        self.is_active = True


class _Cursor:
    def __init__(self, *, rows=None, all_rows=None):
        self.rows = list(rows or [])
        self.all_rows = list(all_rows or [])
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

    def fetchall(self):
        return list(self.all_rows)


class _Connection:
    def __init__(self, *, rows=None, all_rows=None):
        self.cursor_obj = _Cursor(rows=rows, all_rows=all_rows)

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_my_watchlist_returns_items(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "list_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=11, username="swing-trader")

    def fake_list_user_watchlist_items(**kwargs):
        events["list_calls"].append(kwargs)
        return [
            {
                "id": 3,
                "user_id": 11,
                "asset_id": "CN:SH:600000",
                "trade_date_added": "2026-06-20",
                "source": "manual",
                "notes": "gap follow-through",
                "created_at": "2026-06-20T09:00:00+00:00",
                "updated_at": "2026-06-20T09:00:00+00:00",
            }
        ]

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "list_user_watchlist_items", fake_list_user_watchlist_items, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.get("/api/my/watchlist")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": 3,
                "user_id": 11,
                "asset_id": "CN:SH:600000",
                "trade_date_added": "2026-06-20",
                "source": "manual",
                "notes": "gap follow-through",
                "created_at": "2026-06-20T09:00:00+00:00",
                "updated_at": "2026-06-20T09:00:00+00:00",
            }
        ]
    }
    assert events["auth_checks"] == ["/api/my/watchlist"]
    assert events["list_calls"] == [{"user_id": 11}]


def test_create_my_watchlist_item_passes_actor_context(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "csrf_checks": [], "create_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=13, username="breakout")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_create_user_watchlist_item(**kwargs):
        events["create_calls"].append(kwargs)
        return {
            "id": 5,
            "user_id": kwargs["user_id"],
            "asset_id": kwargs["asset_id"],
            "trade_date_added": "2026-06-21",
            "source": kwargs["source"],
            "notes": kwargs["notes"],
            "created_at": "2026-06-20T10:00:00+00:00",
            "updated_at": "2026-06-20T10:00:00+00:00",
        }

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "create_user_watchlist_item",
        fake_create_user_watchlist_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/my/watchlist/items",
            json={
                "asset_id": "CN:SZ:000001",
                "source": "manual",
                "notes": "relative strength",
            },
        )

    assert response.status_code == 200
    assert response.json()["asset_id"] == "CN:SZ:000001"
    assert events["auth_checks"] == ["/api/my/watchlist/items"]
    assert events["csrf_checks"] == ["/api/my/watchlist/items"]
    assert events["create_calls"] == [
        {
            "user_id": 13,
            "asset_id": "CN:SZ:000001",
            "source": "manual",
            "notes": "relative strength",
            "actor_user_id": 13,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_create_my_watchlist_item_returns_409_for_duplicate(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=13, username="breakout")

    def fake_require_csrf(request: Request):
        return None

    def fake_create_user_watchlist_item(**kwargs):
        raise psycopg_errors.UniqueViolation("duplicate key value violates unique constraint")

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "create_user_watchlist_item",
        fake_create_user_watchlist_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/my/watchlist/items",
            json={"asset_id": "CN:SZ:000001"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "watchlist item already exists"}


def test_update_my_watchlist_item_passes_actor_context(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "csrf_checks": [], "update_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=17, username="momentum")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_update_user_watchlist_item(**kwargs):
        events["update_calls"].append(kwargs)
        return {
            "id": 8,
            "user_id": kwargs["user_id"],
            "asset_id": kwargs["asset_id"],
            "trade_date_added": "2026-06-21",
            "source": kwargs["source"],
            "notes": kwargs["notes"],
            "created_at": "2026-06-20T10:00:00+00:00",
            "updated_at": "2026-06-22T10:00:00+00:00",
        }

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "update_user_watchlist_item",
        fake_update_user_watchlist_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.patch(
            "/api/my/watchlist/items/CN:SZ:300750",
            json={"source": "journal", "notes": "post-earnings setup"},
        )

    assert response.status_code == 200
    assert response.json()["notes"] == "post-earnings setup"
    assert events["auth_checks"] == ["/api/my/watchlist/items/CN:SZ:300750"]
    assert events["csrf_checks"] == ["/api/my/watchlist/items/CN:SZ:300750"]
    assert events["update_calls"] == [
        {
            "user_id": 17,
            "asset_id": "CN:SZ:300750",
            "source": "journal",
            "notes": "post-earnings setup",
            "actor_user_id": 17,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_update_my_watchlist_item_returns_404_when_missing(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=17, username="momentum")

    def fake_require_csrf(request: Request):
        return None

    def fake_update_user_watchlist_item(**kwargs):
        return None

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "update_user_watchlist_item",
        fake_update_user_watchlist_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.patch(
            "/api/my/watchlist/items/CN:SZ:300750",
            json={"source": "journal", "notes": "post-earnings setup"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "watchlist item not found"}


def test_delete_my_watchlist_item_soft_deletes(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "csrf_checks": [], "delete_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=19, username="reversal")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_soft_delete_user_watchlist_item(**kwargs):
        events["delete_calls"].append(kwargs)
        return True

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "soft_delete_user_watchlist_item",
        fake_soft_delete_user_watchlist_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.delete("/api/my/watchlist/items/CN:SH:688256")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert events["auth_checks"] == ["/api/my/watchlist/items/CN:SH:688256"]
    assert events["csrf_checks"] == ["/api/my/watchlist/items/CN:SH:688256"]
    assert events["delete_calls"] == [
        {
            "user_id": 19,
            "asset_id": "CN:SH:688256",
            "actor_user_id": 19,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_delete_my_watchlist_item_returns_404_when_missing(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=19, username="reversal")

    def fake_require_csrf(request: Request):
        return None

    def fake_soft_delete_user_watchlist_item(**kwargs):
        return False

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "soft_delete_user_watchlist_item",
        fake_soft_delete_user_watchlist_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.delete("/api/my/watchlist/items/CN:SH:688256")

    assert response.status_code == 404
    assert response.json() == {"detail": "watchlist item not found"}


def test_create_user_watchlist_item_sets_today_and_inserts_audit_in_same_cursor(monkeypatch):
    from stock_research.dashboard import user_watchlist

    class _FakeDate:
        @staticmethod
        def today():
            class _Today:
                @staticmethod
                def isoformat():
                    return "2026-06-22"

            return _Today()

    conn = _Connection(
        rows=[
            {
                "id": 31,
                "user_id": 23,
                "asset_id": "CN:SH:600000",
                "trade_date_added": "2026-06-22",
                "source": "manual",
                "notes": "breakout",
                "created_at": "2026-06-22T09:30:00+00:00",
                "updated_at": "2026-06-22T09:30:00+00:00",
            }
        ]
    )

    monkeypatch.setattr(user_watchlist, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(user_watchlist, "date", _FakeDate)

    item = user_watchlist.create_user_watchlist_item(
        user_id=23,
        asset_id="CN:SH:600000",
        source="manual",
        notes="breakout",
        actor_user_id=23,
        ip_address="203.0.113.9",
        user_agent="pytest",
    )

    assert item["trade_date_added"] == "2026-06-22"
    sql, params = conn.cursor_obj.calls[0]
    assert "INSERT INTO watchlist.user_watchlist_item" in sql
    assert params == {
        "user_id": 23,
        "asset_id": "CN:SH:600000",
        "trade_date_added": "2026-06-22",
        "source": "manual",
        "notes": "breakout",
    }
    audit_sql, audit_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "watchlist_add_item"
    assert audit_params["target_id"] == "CN:SH:600000"
    assert audit_params["actor_user_id"] == 23


def test_update_user_watchlist_item_updates_fields_and_inserts_audit_in_same_cursor(monkeypatch):
    from stock_research.dashboard import user_watchlist

    conn = _Connection(
        rows=[
            {
                "id": 31,
                "user_id": 23,
                "asset_id": "CN:SH:600000",
                "trade_date_added": "2026-06-20",
                "source": "journal",
                "notes": "trim risk",
                "created_at": "2026-06-20T09:30:00+00:00",
                "updated_at": "2026-06-22T09:30:00+00:00",
            }
        ]
    )

    monkeypatch.setattr(user_watchlist, "connect", lambda service: _Context(conn))

    item = user_watchlist.update_user_watchlist_item(
        user_id=23,
        asset_id="CN:SH:600000",
        source="journal",
        notes="trim risk",
        actor_user_id=23,
        ip_address="203.0.113.9",
        user_agent="pytest",
    )

    assert item is not None
    sql, params = conn.cursor_obj.calls[0]
    assert "UPDATE watchlist.user_watchlist_item" in sql
    assert "SET source = COALESCE(%(source)s, source)," in sql
    assert "notes = COALESCE(%(notes)s, notes)," in sql
    assert "SET trade_date_added" not in sql
    assert "%(trade_date_added)s" not in sql
    assert params == {
        "user_id": 23,
        "asset_id": "CN:SH:600000",
        "source": "journal",
        "notes": "trim risk",
    }
    audit_sql, audit_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "watchlist_update_item"
    assert audit_params["target_id"] == "CN:SH:600000"
    assert audit_params["actor_user_id"] == 23


def test_soft_delete_user_watchlist_item_sets_deleted_at_and_inserts_audit_in_same_cursor(monkeypatch):
    from stock_research.dashboard import user_watchlist

    conn = _Connection(rows=[{"asset_id": "CN:SH:600000"}])

    monkeypatch.setattr(user_watchlist, "connect", lambda service: _Context(conn))

    deleted = user_watchlist.soft_delete_user_watchlist_item(
        user_id=23,
        asset_id="CN:SH:600000",
        actor_user_id=23,
        ip_address="203.0.113.9",
        user_agent="pytest",
    )

    assert deleted is True
    sql, params = conn.cursor_obj.calls[0]
    assert "UPDATE watchlist.user_watchlist_item" in sql
    assert "SET deleted_at = now()," in sql
    assert "updated_at = now()" in sql
    assert "WHERE user_id = %(user_id)s" in sql
    assert "asset_id = %(asset_id)s" in sql
    assert "deleted_at IS NULL" in sql
    assert params == {"user_id": 23, "asset_id": "CN:SH:600000"}
    audit_sql, audit_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "watchlist_remove_item"
    assert audit_params["target_id"] == "CN:SH:600000"
    assert audit_params["actor_user_id"] == 23
