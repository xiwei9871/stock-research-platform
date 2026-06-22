from fastapi import Request
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


class _FakeUser:
    def __init__(self, user_id: int = 7, username: str = "analyst"):
        self.id = user_id
        self.username = username
        self.display_name = "Analyst"
        self.role = "user"
        self.is_active = True


class _Cursor:
    def __init__(self, *, rows=None, all_rows=None, all_rows_sequence=None):
        self.rows = list(rows or [])
        self.all_rows = list(all_rows or [])
        self.all_rows_sequence = [list(batch) for batch in (all_rows_sequence or [])]
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
        if self.all_rows_sequence:
            return self.all_rows_sequence.pop(0)
        return list(self.all_rows)


class _Connection:
    def __init__(self, *, rows=None, all_rows=None, all_rows_sequence=None):
        self.cursor_obj = _Cursor(
            rows=rows,
            all_rows=all_rows,
            all_rows_sequence=all_rows_sequence,
        )

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_my_reviews_returns_items(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "list_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=11, username="swing-trader")

    def fake_list_user_review_sessions(**kwargs):
        events["list_calls"].append(kwargs)
        return [
            {
                "id": 3,
                "user_id": 11,
                "trade_date": "2026-06-20",
                "title": "Morning review",
                "summary": "Tighten entry criteria.",
                "market_view": "Range-bound open.",
                "position_view": "Reduce weak names.",
                "next_action": "Review gap-up continuation.",
                "created_at": "2026-06-20T09:00:00+00:00",
                "updated_at": "2026-06-20T09:00:00+00:00",
                "items": [],
            }
        ]

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "list_user_review_sessions", fake_list_user_review_sessions, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.get("/api/my/reviews")

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "Morning review"
    assert events["auth_checks"] == ["/api/my/reviews"]
    assert events["list_calls"] == [{"user_id": 11}]


def test_review_session_payload_uses_review_item_payload_for_create_contract():
    review_item_payload = getattr(dashboard_app, "ReviewItemPayload", None)

    assert review_item_payload is not None
    assert dashboard_app.ReviewSessionPayload.model_fields["items"].annotation == list[review_item_payload]


def test_list_user_review_sessions_groups_nested_items_by_session(monkeypatch):
    from stock_research.dashboard import user_reviews

    conn = _Connection(
        all_rows_sequence=[
            [
                {
                    "id": 31,
                    "user_id": 23,
                    "trade_date": "2026-06-22",
                    "title": "Close review",
                    "summary": "Review failed breakouts.",
                    "market_view": "Weak breadth.",
                    "position_view": "Keep gross low.",
                    "next_action": "Rebuild leader list.",
                    "created_at": "2026-06-22T09:30:00+00:00",
                    "updated_at": "2026-06-22T09:30:00+00:00",
                },
                {
                    "id": 30,
                    "user_id": 23,
                    "trade_date": "2026-06-21",
                    "title": "Open review",
                    "summary": "Keep sizing small.",
                    "market_view": "Mixed tape.",
                    "position_view": "Avoid chasing strength.",
                    "next_action": "Check leaders at noon.",
                    "created_at": "2026-06-21T09:30:00+00:00",
                    "updated_at": "2026-06-21T09:30:00+00:00",
                },
            ],
            [
                {
                    "id": 8,
                    "session_id": 31,
                    "user_id": 23,
                    "asset_id": "CN:SH:600000",
                    "decision": "hold",
                    "conviction": "medium",
                    "tags": ["gap"],
                    "notes": "Wait for follow-through.",
                    "follow_up_required": True,
                    "created_at": "2026-06-22T09:31:00+00:00",
                    "updated_at": "2026-06-22T09:31:00+00:00",
                },
                {
                    "id": 7,
                    "session_id": 31,
                    "user_id": 23,
                    "asset_id": "CN:SZ:000001",
                    "decision": "trim",
                    "conviction": "high",
                    "tags": ["risk"],
                    "notes": "Sell into resistance.",
                    "follow_up_required": False,
                    "created_at": "2026-06-22T09:32:00+00:00",
                    "updated_at": "2026-06-22T09:32:00+00:00",
                },
            ],
        ]
    )

    monkeypatch.setattr(user_reviews, "connect", lambda service: _Context(conn))

    sessions = user_reviews.list_user_review_sessions(user_id=23)

    assert [session["id"] for session in sessions] == [31, 30]
    assert [item["id"] for item in sessions[0]["items"]] == [8, 7]
    assert sessions[1]["items"] == []
    session_sql, session_params = conn.cursor_obj.calls[0]
    assert "FROM journal.user_review_session" in session_sql
    assert "deleted_at IS NULL" in session_sql
    assert session_params == {"user_id": 23}
    item_sql, item_params = conn.cursor_obj.calls[1]
    assert "FROM journal.user_review_item" in item_sql
    assert "session_id = ANY(%(session_ids)s)" in item_sql
    assert item_params == {"user_id": 23, "session_ids": [31, 30]}


def test_create_my_review_session_passes_actor_context(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "csrf_checks": [], "create_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=13, username="breakout")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_create_user_review_session(**kwargs):
        events["create_calls"].append(kwargs)
        return {
            "id": 5,
            "user_id": kwargs["user_id"],
            "trade_date": kwargs["trade_date"],
            "title": kwargs["title"],
            "summary": kwargs["summary"],
            "market_view": kwargs["market_view"],
            "position_view": kwargs["position_view"],
            "next_action": kwargs["next_action"],
            "created_at": "2026-06-20T10:00:00+00:00",
            "updated_at": "2026-06-20T10:00:00+00:00",
            "items": kwargs["items"],
        }

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "create_user_review_session",
        fake_create_user_review_session,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/my/reviews",
            json={
                "trade_date": "2026-06-21",
                "title": "Close review",
                "summary": "Review failed breakouts.",
                "market_view": "Weak breadth.",
                "position_view": "Keep gross low.",
                "next_action": "Rebuild leader list.",
                "items": [
                    {
                        "asset_id": "CN:SZ:000001",
                        "decision": "hold",
                        "conviction": "medium",
                        "tags": ["earnings"],
                        "notes": "Watch support retest.",
                        "follow_up_required": True,
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["title"] == "Close review"
    assert events["auth_checks"] == ["/api/my/reviews"]
    assert events["csrf_checks"] == ["/api/my/reviews"]
    assert events["create_calls"] == [
        {
            "user_id": 13,
            "trade_date": "2026-06-21",
            "title": "Close review",
            "summary": "Review failed breakouts.",
            "market_view": "Weak breadth.",
            "position_view": "Keep gross low.",
            "next_action": "Rebuild leader list.",
            "items": [
                {
                    "asset_id": "CN:SZ:000001",
                    "decision": "hold",
                    "conviction": "medium",
                    "tags": ["earnings"],
                    "notes": "Watch support retest.",
                    "follow_up_required": True,
                }
            ],
            "actor_user_id": 13,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_create_my_review_session_rejects_missing_required_item_fields(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=13, username="breakout")

    def fake_require_csrf(request: Request):
        return None

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/my/reviews",
            json={
                "trade_date": "2026-06-21",
                "title": "Close review",
                "items": [{"asset_id": "CN:SZ:000001", "conviction": "medium"}],
            },
        )

    assert response.status_code == 422


def test_create_my_review_session_rejects_blank_required_item_fields(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=13, username="breakout")

    def fake_require_csrf(request: Request):
        return None

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/my/reviews",
            json={
                "trade_date": "2026-06-21",
                "title": "Close review",
                "items": [
                    {
                        "asset_id": "CN:SZ:000001",
                        "decision": "",
                        "conviction": "   ",
                    }
                ],
            },
        )

    assert response.status_code == 422


def test_get_my_review_session_returns_nested_items(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "get_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=29, username="close-review")

    def fake_get_user_review_session(**kwargs):
        events["get_calls"].append(kwargs)
        return {
            "id": kwargs["session_id"],
            "user_id": kwargs["user_id"],
            "trade_date": "2026-06-21",
            "title": "Close review",
            "summary": "Review failed breakouts.",
            "market_view": "Weak breadth.",
            "position_view": "Keep gross low.",
            "next_action": "Rebuild leader list.",
            "created_at": "2026-06-21T10:00:00+00:00",
            "updated_at": "2026-06-21T10:30:00+00:00",
            "items": [
                {
                    "id": 8,
                    "session_id": kwargs["session_id"],
                    "user_id": kwargs["user_id"],
                    "asset_id": "CN:SZ:300750",
                    "decision": "hold",
                    "conviction": "medium",
                    "tags": ["gap"],
                    "notes": "Watch support retest.",
                    "follow_up_required": True,
                    "created_at": "2026-06-21T10:05:00+00:00",
                    "updated_at": "2026-06-21T10:20:00+00:00",
                }
            ],
        }

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "get_user_review_session",
        fake_get_user_review_session,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.get("/api/my/reviews/44")

    assert response.status_code == 200
    assert response.json()["items"][0]["asset_id"] == "CN:SZ:300750"
    assert events["auth_checks"] == ["/api/my/reviews/44"]
    assert events["get_calls"] == [{"user_id": 29, "session_id": 44}]


def test_get_my_review_session_returns_404_when_missing(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=29, username="close-review")

    def fake_get_user_review_session(**kwargs):
        return None

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "get_user_review_session",
        fake_get_user_review_session,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.get("/api/my/reviews/44")

    assert response.status_code == 404
    assert response.json() == {"detail": "review session not found"}


def test_patch_my_review_session_passes_actor_context(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "csrf_checks": [], "update_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=31, username="swing-review")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_update_user_review_session(**kwargs):
        events["update_calls"].append(kwargs)
        return {
            "id": kwargs["session_id"],
            "user_id": kwargs["user_id"],
            "trade_date": kwargs["trade_date"],
            "title": kwargs["title"],
            "summary": kwargs["summary"],
            "market_view": kwargs["market_view"],
            "position_view": kwargs["position_view"],
            "next_action": kwargs["next_action"],
            "created_at": "2026-06-21T10:00:00+00:00",
            "updated_at": "2026-06-22T10:00:00+00:00",
            "items": [],
        }

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "update_user_review_session",
        fake_update_user_review_session,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.patch(
            "/api/my/reviews/52",
            json={
                "trade_date": "2026-06-22",
                "title": "Updated close review",
                "summary": "Tighten breakouts.",
                "market_view": "Mixed tape.",
                "position_view": "Trim laggards.",
                "next_action": "Review leaders after lunch.",
            },
        )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated close review"
    assert events["auth_checks"] == ["/api/my/reviews/52"]
    assert events["csrf_checks"] == ["/api/my/reviews/52"]
    assert events["update_calls"] == [
        {
            "user_id": 31,
            "session_id": 52,
            "trade_date": "2026-06-22",
            "title": "Updated close review",
            "summary": "Tighten breakouts.",
            "market_view": "Mixed tape.",
            "position_view": "Trim laggards.",
            "next_action": "Review leaders after lunch.",
            "actor_user_id": 31,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_patch_my_review_session_returns_404_when_missing(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=31, username="swing-review")

    def fake_require_csrf(request: Request):
        return None

    def fake_update_user_review_session(**kwargs):
        return None

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "update_user_review_session",
        fake_update_user_review_session,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.patch(
            "/api/my/reviews/52",
            json={"title": "Updated close review"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "review session not found"}


def test_create_my_review_item_passes_actor_context(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "csrf_checks": [], "create_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=37, username="follow-up")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_create_user_review_item(**kwargs):
        events["create_calls"].append(kwargs)
        return {
            "id": 12,
            "session_id": kwargs["session_id"],
            "user_id": kwargs["user_id"],
            "asset_id": kwargs["asset_id"],
            "decision": kwargs["decision"],
            "conviction": kwargs["conviction"],
            "tags": kwargs["tags"],
            "notes": kwargs["notes"],
            "follow_up_required": kwargs["follow_up_required"],
            "created_at": "2026-06-22T10:00:00+00:00",
            "updated_at": "2026-06-22T10:00:00+00:00",
        }

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "create_user_review_item",
        fake_create_user_review_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/my/reviews/52/items",
            json={
                "asset_id": "CN:SH:600000",
                "decision": "hold",
                "conviction": "medium",
                "tags": ["gap"],
                "notes": "Watch support retest.",
                "follow_up_required": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["asset_id"] == "CN:SH:600000"
    assert events["auth_checks"] == ["/api/my/reviews/52/items"]
    assert events["csrf_checks"] == ["/api/my/reviews/52/items"]
    assert events["create_calls"] == [
        {
            "user_id": 37,
            "session_id": 52,
            "asset_id": "CN:SH:600000",
            "decision": "hold",
            "conviction": "medium",
            "tags": ["gap"],
            "notes": "Watch support retest.",
            "follow_up_required": True,
            "actor_user_id": 37,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_create_my_review_item_returns_404_when_parent_missing(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=37, username="follow-up")

    def fake_require_csrf(request: Request):
        return None

    def fake_create_user_review_item(**kwargs):
        return None

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "create_user_review_item",
        fake_create_user_review_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/my/reviews/52/items",
            json={
                "asset_id": "CN:SH:600000",
                "decision": "hold",
                "conviction": "medium",
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "review session not found"}


def test_patch_review_item_passes_session_id_item_id_and_user_id(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "csrf_checks": [], "update_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=17, username="momentum")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_update_user_review_item(**kwargs):
        events["update_calls"].append(kwargs)
        return {
            "id": kwargs["item_id"],
            "session_id": kwargs["session_id"],
            "user_id": kwargs["user_id"],
            "asset_id": "CN:SZ:300750",
            "decision": kwargs["decision"],
            "conviction": kwargs["conviction"],
            "tags": kwargs["tags"],
            "notes": kwargs["notes"],
            "follow_up_required": kwargs["follow_up_required"],
            "created_at": "2026-06-20T10:00:00+00:00",
            "updated_at": "2026-06-22T10:00:00+00:00",
        }

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "update_user_review_item",
        fake_update_user_review_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.patch(
            "/api/my/reviews/31/items/8",
            json={
                "decision": "trim",
                "conviction": "high",
                "tags": ["gap", "risk"],
                "notes": "Cut into resistance.",
                "follow_up_required": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["notes"] == "Cut into resistance."
    assert events["auth_checks"] == ["/api/my/reviews/31/items/8"]
    assert events["csrf_checks"] == ["/api/my/reviews/31/items/8"]
    assert events["update_calls"] == [
        {
            "user_id": 17,
            "session_id": 31,
            "item_id": 8,
            "decision": "trim",
            "conviction": "high",
            "tags": ["gap", "risk"],
            "notes": "Cut into resistance.",
            "follow_up_required": True,
            "actor_user_id": 17,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_update_my_review_item_returns_404_when_missing(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=17, username="momentum")

    def fake_require_csrf(request: Request):
        return None

    def fake_update_user_review_item(**kwargs):
        return None

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "update_user_review_item",
        fake_update_user_review_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.patch(
            "/api/my/reviews/31/items/8",
            json={"notes": "Cut into resistance."},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "review item not found"}


def test_update_my_review_item_rejects_blank_semantic_values(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=17, username="momentum")

    def fake_require_csrf(request: Request):
        return None

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.patch(
            "/api/my/reviews/31/items/8",
            json={"decision": "", "conviction": "   "},
        )

    assert response.status_code == 422


def test_delete_my_review_session_soft_deletes(monkeypatch):
    events: dict[str, object] = {"auth_checks": [], "csrf_checks": [], "delete_calls": []}

    def fake_require_current_user(request: Request):
        events["auth_checks"].append(request.url.path)
        return _FakeUser(user_id=19, username="reversal")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_soft_delete_user_review_session(**kwargs):
        events["delete_calls"].append(kwargs)
        return True

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "soft_delete_user_review_session",
        fake_soft_delete_user_review_session,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.delete("/api/my/reviews/41")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert events["delete_calls"] == [
        {
            "user_id": 19,
            "session_id": 41,
            "actor_user_id": 19,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_delete_my_review_session_returns_404_when_missing(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=19, username="reversal")

    def fake_require_csrf(request: Request):
        return None

    def fake_soft_delete_user_review_session(**kwargs):
        return False

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "soft_delete_user_review_session",
        fake_soft_delete_user_review_session,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.delete("/api/my/reviews/41")

    assert response.status_code == 404
    assert response.json() == {"detail": "review session not found"}


def test_delete_my_review_item_returns_404_when_missing(monkeypatch):
    def fake_require_current_user(request: Request):
        return _FakeUser(user_id=19, username="reversal")

    def fake_require_csrf(request: Request):
        return None

    def fake_soft_delete_user_review_item(**kwargs):
        return False

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_current_user", fake_require_current_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "soft_delete_user_review_item",
        fake_soft_delete_user_review_item,
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.delete("/api/my/reviews/41/items/8")

    assert response.status_code == 404
    assert response.json() == {"detail": "review item not found"}


def test_create_user_review_session_inserts_items_and_audit_in_same_cursor(monkeypatch):
    from stock_research.dashboard import user_reviews

    conn = _Connection(
        rows=[
            {
                "id": 31,
                "user_id": 23,
                "trade_date": "2026-06-22",
                "title": "Close review",
                "summary": "Review failed breakouts.",
                "market_view": "Weak breadth.",
                "position_view": "Keep gross low.",
                "next_action": "Rebuild leader list.",
                "created_at": "2026-06-22T09:30:00+00:00",
                "updated_at": "2026-06-22T09:30:00+00:00",
            },
            {
                "id": 8,
                "session_id": 31,
                "user_id": 23,
                "asset_id": "CN:SH:600000",
                "decision": "hold",
                "conviction": "medium",
                "tags": ["gap"],
                "notes": "Wait for follow-through.",
                "follow_up_required": True,
                "created_at": "2026-06-22T09:31:00+00:00",
                "updated_at": "2026-06-22T09:31:00+00:00",
            },
        ]
    )

    monkeypatch.setattr(user_reviews, "connect", lambda service: _Context(conn))

    session = user_reviews.create_user_review_session(
        user_id=23,
        trade_date="2026-06-22",
        title="Close review",
        summary="Review failed breakouts.",
        market_view="Weak breadth.",
        position_view="Keep gross low.",
        next_action="Rebuild leader list.",
        items=[
            {
                "asset_id": "CN:SH:600000",
                "decision": "hold",
                "conviction": "medium",
                "tags": ["gap"],
                "notes": "Wait for follow-through.",
                "follow_up_required": True,
            }
        ],
        actor_user_id=23,
        ip_address="203.0.113.9",
        user_agent="pytest",
    )

    assert session["id"] == 31
    assert session["items"][0]["asset_id"] == "CN:SH:600000"
    session_sql, session_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO journal.user_review_session" in session_sql
    assert session_params == {
        "user_id": 23,
        "trade_date": "2026-06-22",
        "title": "Close review",
        "summary": "Review failed breakouts.",
        "market_view": "Weak breadth.",
        "position_view": "Keep gross low.",
        "next_action": "Rebuild leader list.",
    }
    item_sql, item_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO journal.user_review_item" in item_sql
    assert item_params == {
        "session_id": 31,
        "user_id": 23,
        "asset_id": "CN:SH:600000",
        "decision": "hold",
        "conviction": "medium",
        "tags": '["gap"]',
        "notes": "Wait for follow-through.",
        "follow_up_required": True,
    }
    audit_sql, audit_params = conn.cursor_obj.calls[2]
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "review_create_session"
    assert audit_params["target_id"] == "31"
    assert audit_params["actor_user_id"] == 23


def test_create_user_review_session_rejects_missing_required_item_fields(monkeypatch):
    from stock_research.dashboard import user_reviews

    conn = _Connection()

    monkeypatch.setattr(user_reviews, "connect", lambda service: _Context(conn))

    try:
        user_reviews.create_user_review_session(
            user_id=23,
            trade_date="2026-06-22",
            title="Close review",
            summary="Review failed breakouts.",
            market_view="Weak breadth.",
            position_view="Keep gross low.",
            next_action="Rebuild leader list.",
            items=[
                {
                    "asset_id": "CN:SH:600000",
                    "decision": "",
                    "conviction": "medium",
                }
            ],
            actor_user_id=23,
        )
    except ValueError as exc:
        assert "decision" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing required review item fields")

    assert conn.cursor_obj.calls == []


def test_update_user_review_item_enforces_ownership_join_and_inserts_audit(monkeypatch):
    from stock_research.dashboard import user_reviews

    conn = _Connection(
        rows=[
            {
                "id": 8,
                "session_id": 31,
                "user_id": 23,
                "asset_id": "CN:SH:600000",
                "decision": "hold",
                "conviction": "medium",
                "tags": ["gap"],
                "notes": "Wait for pullback.",
                "follow_up_required": True,
                "created_at": "2026-06-20T09:30:00+00:00",
                "updated_at": "2026-06-22T09:30:00+00:00",
            }
        ]
    )

    monkeypatch.setattr(user_reviews, "connect", lambda service: _Context(conn))

    item = user_reviews.update_user_review_item(
        user_id=23,
        session_id=31,
        item_id=8,
        decision="hold",
        conviction="medium",
        tags=["gap"],
        notes="Wait for pullback.",
        follow_up_required=True,
        actor_user_id=23,
        ip_address="203.0.113.9",
        user_agent="pytest",
    )

    assert item is not None
    sql, params = conn.cursor_obj.calls[0]
    assert "UPDATE journal.user_review_item AS item" in sql
    assert "FROM journal.user_review_session AS session" in sql
    assert "item.user_id = %(user_id)s" in sql
    assert "item.session_id = %(session_id)s" in sql
    assert "session.user_id = %(user_id)s" in sql
    assert params == {
        "user_id": 23,
        "session_id": 31,
        "item_id": 8,
        "decision": "hold",
        "conviction": "medium",
        "tags": '["gap"]',
        "notes": "Wait for pullback.",
        "follow_up_required": True,
    }
    audit_sql, audit_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "review_update_item"
    assert audit_params["target_id"] == "8"
    assert audit_params["actor_user_id"] == 23


def test_get_user_review_session_enforces_ownership_and_loads_items(monkeypatch):
    from stock_research.dashboard import user_reviews

    conn = _Connection(
        rows=[
            {
                "id": 31,
                "user_id": 23,
                "trade_date": "2026-06-22",
                "title": "Close review",
                "summary": "Review failed breakouts.",
                "market_view": "Weak breadth.",
                "position_view": "Keep gross low.",
                "next_action": "Rebuild leader list.",
                "created_at": "2026-06-22T09:30:00+00:00",
                "updated_at": "2026-06-22T09:30:00+00:00",
            }
        ],
        all_rows=[
            {
                "id": 8,
                "session_id": 31,
                "user_id": 23,
                "asset_id": "CN:SH:600000",
                "decision": "hold",
                "conviction": "medium",
                "tags": ["gap"],
                "notes": "Wait for follow-through.",
                "follow_up_required": True,
                "created_at": "2026-06-22T09:31:00+00:00",
                "updated_at": "2026-06-22T09:31:00+00:00",
            }
        ],
    )

    monkeypatch.setattr(user_reviews, "connect", lambda service: _Context(conn))

    session = user_reviews.get_user_review_session(user_id=23, session_id=31)

    assert session is not None
    assert session["items"][0]["id"] == 8
    session_sql, session_params = conn.cursor_obj.calls[0]
    assert "FROM journal.user_review_session" in session_sql
    assert "id = %(session_id)s" in session_sql
    assert "user_id = %(user_id)s" in session_sql
    assert "deleted_at IS NULL" in session_sql
    assert session_params == {"user_id": 23, "session_id": 31}
    item_sql, item_params = conn.cursor_obj.calls[1]
    assert "FROM journal.user_review_item" in item_sql
    assert "session_id = %(session_id)s" in item_sql
    assert "user_id = %(user_id)s" in item_sql
    assert "deleted_at IS NULL" in item_sql
    assert item_params == {"user_id": 23, "session_id": 31}


def test_update_user_review_session_updates_session_and_inserts_audit(monkeypatch):
    from stock_research.dashboard import user_reviews

    conn = _Connection(
        rows=[
            {
                "id": 31,
                "user_id": 23,
                "trade_date": "2026-06-22",
                "title": "Close review",
                "summary": "Review failed breakouts.",
                "market_view": "Weak breadth.",
                "position_view": "Keep gross low.",
                "next_action": "Rebuild leader list.",
                "created_at": "2026-06-20T09:30:00+00:00",
                "updated_at": "2026-06-22T09:30:00+00:00",
            }
        ],
        all_rows=[],
    )

    monkeypatch.setattr(user_reviews, "connect", lambda service: _Context(conn))

    session = user_reviews.update_user_review_session(
        user_id=23,
        session_id=31,
        trade_date="2026-06-22",
        title="Close review",
        summary="Review failed breakouts.",
        market_view="Weak breadth.",
        position_view="Keep gross low.",
        next_action="Rebuild leader list.",
        actor_user_id=23,
        ip_address="203.0.113.9",
        user_agent="pytest",
    )

    assert session is not None
    update_sql, update_params = conn.cursor_obj.calls[0]
    assert "UPDATE journal.user_review_session" in update_sql
    assert "trade_date = COALESCE(%(trade_date)s, trade_date)" in update_sql
    assert "WHERE id = %(session_id)s" in update_sql
    assert "AND user_id = %(user_id)s" in update_sql
    assert "deleted_at IS NULL" in update_sql
    assert update_params == {
        "user_id": 23,
        "session_id": 31,
        "trade_date": "2026-06-22",
        "title": "Close review",
        "summary": "Review failed breakouts.",
        "market_view": "Weak breadth.",
        "position_view": "Keep gross low.",
        "next_action": "Rebuild leader list.",
    }
    load_items_sql, load_items_params = conn.cursor_obj.calls[1]
    assert "FROM journal.user_review_item" in load_items_sql
    assert load_items_params == {"user_id": 23, "session_id": 31}
    audit_sql, audit_params = conn.cursor_obj.calls[2]
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "review_update_session"
    assert audit_params["target_id"] == "31"
    assert audit_params["actor_user_id"] == 23


def test_create_user_review_item_scopes_parent_session_and_inserts_audit(monkeypatch):
    from stock_research.dashboard import user_reviews

    conn = _Connection(
        rows=[
            {
                "id": 8,
                "session_id": 31,
                "user_id": 23,
                "asset_id": "CN:SH:600000",
                "decision": "hold",
                "conviction": "medium",
                "tags": ["gap"],
                "notes": "Wait for follow-through.",
                "follow_up_required": True,
                "created_at": "2026-06-22T09:31:00+00:00",
                "updated_at": "2026-06-22T09:31:00+00:00",
            }
        ]
    )

    monkeypatch.setattr(user_reviews, "connect", lambda service: _Context(conn))

    item = user_reviews.create_user_review_item(
        user_id=23,
        session_id=31,
        asset_id="CN:SH:600000",
        decision="hold",
        conviction="medium",
        tags=["gap"],
        notes="Wait for follow-through.",
        follow_up_required=True,
        actor_user_id=23,
        ip_address="203.0.113.9",
        user_agent="pytest",
    )

    assert item is not None
    insert_sql, insert_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO journal.user_review_item" in insert_sql
    assert "FROM journal.user_review_session AS session" in insert_sql
    assert "session.id = %(session_id)s" in insert_sql
    assert "session.user_id = %(user_id)s" in insert_sql
    assert "session.deleted_at IS NULL" in insert_sql
    assert insert_params == {
        "user_id": 23,
        "session_id": 31,
        "asset_id": "CN:SH:600000",
        "decision": "hold",
        "conviction": "medium",
        "tags": '["gap"]',
        "notes": "Wait for follow-through.",
        "follow_up_required": True,
    }
    audit_sql, audit_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "review_create_item"
    assert audit_params["target_id"] == "8"
    assert audit_params["actor_user_id"] == 23


def test_soft_delete_user_review_session_soft_deletes_child_items_and_inserts_audit(monkeypatch):
    from stock_research.dashboard import user_reviews

    conn = _Connection(rows=[{"id": 31}, {"session_id": 31}])

    monkeypatch.setattr(user_reviews, "connect", lambda service: _Context(conn))

    deleted = user_reviews.soft_delete_user_review_session(
        user_id=23,
        session_id=31,
        actor_user_id=23,
        ip_address="203.0.113.9",
        user_agent="pytest",
    )

    assert deleted is True
    session_sql, session_params = conn.cursor_obj.calls[0]
    assert "UPDATE journal.user_review_session" in session_sql
    assert "SET deleted_at = now()," in session_sql
    assert session_params == {"user_id": 23, "session_id": 31}
    item_sql, item_params = conn.cursor_obj.calls[1]
    assert "UPDATE journal.user_review_item" in item_sql
    assert "SET deleted_at = now()," in item_sql
    assert "session_id = %(session_id)s" in item_sql
    assert "deleted_at IS NULL" in item_sql
    assert item_params == {"user_id": 23, "session_id": 31}
    audit_sql, audit_params = conn.cursor_obj.calls[2]
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "review_delete_session"
    assert audit_params["target_id"] == "31"
    assert audit_params["actor_user_id"] == 23


def test_soft_delete_user_review_item_enforces_ownership_join_and_inserts_audit(monkeypatch):
    from stock_research.dashboard import user_reviews

    conn = _Connection(rows=[{"id": 8}])

    monkeypatch.setattr(user_reviews, "connect", lambda service: _Context(conn))

    deleted = user_reviews.soft_delete_user_review_item(
        user_id=23,
        session_id=31,
        item_id=8,
        actor_user_id=23,
        ip_address="203.0.113.9",
        user_agent="pytest",
    )

    assert deleted is True
    sql, params = conn.cursor_obj.calls[0]
    assert "UPDATE journal.user_review_item AS item" in sql
    assert "FROM journal.user_review_session AS session" in sql
    assert "SET deleted_at = now()," in sql
    assert "item.user_id = %(user_id)s" in sql
    assert "item.session_id = %(session_id)s" in sql
    assert "session.user_id = %(user_id)s" in sql
    assert params == {"user_id": 23, "session_id": 31, "item_id": 8}
    audit_sql, audit_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "review_delete_item"
    assert audit_params["target_id"] == "8"
    assert audit_params["actor_user_id"] == 23
