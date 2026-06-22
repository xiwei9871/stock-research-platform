import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.user_models import UserReviewItem, UserReviewSession
from stock_research.db import connect


USER_REVIEW_SESSION_COLUMNS = """
    id,
    user_id,
    trade_date,
    title,
    summary,
    market_view,
    position_view,
    next_action,
    created_at,
    updated_at
"""

USER_REVIEW_ITEM_COLUMNS = """
    id,
    session_id,
    user_id,
    asset_id,
    decision,
    conviction,
    tags,
    notes,
    follow_up_required,
    created_at,
    updated_at
"""


def list_user_review_sessions(
    *,
    user_id: int,
    service: str = SETTINGS.research_service,
) -> list[dict[str, object]]:
    session_sql = f"""
    SELECT {USER_REVIEW_SESSION_COLUMNS}
    FROM journal.user_review_session
    WHERE user_id = %(user_id)s
      AND deleted_at IS NULL
    ORDER BY trade_date DESC, updated_at DESC, id DESC
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(session_sql, {"user_id": user_id})
            session_rows = cur.fetchall()
            if not session_rows:
                return []
            session_ids = [int(row["id"]) for row in session_rows]
            cur.execute(
                f"""
                SELECT {USER_REVIEW_ITEM_COLUMNS}
                FROM journal.user_review_item
                WHERE user_id = %(user_id)s
                  AND session_id = ANY(%(session_ids)s)
                  AND deleted_at IS NULL
                ORDER BY session_id ASC, updated_at DESC, id DESC
                """,
                {"user_id": user_id, "session_ids": session_ids},
            )
            item_rows = cur.fetchall()

    items_by_session: dict[int, list[dict[str, object]]] = {}
    for row in item_rows:
        session_id = int(row["session_id"])
        items_by_session.setdefault(session_id, []).append(_serialize_user_review_item(row))

    return [
        _serialize_user_review_session(row, items_by_session.get(int(row["id"]), []))
        for row in session_rows
    ]


def get_user_review_session(
    *,
    user_id: int,
    session_id: int,
    service: str = SETTINGS.research_service,
) -> dict[str, object] | None:
    session_sql = f"""
    SELECT {USER_REVIEW_SESSION_COLUMNS}
    FROM journal.user_review_session
    WHERE id = %(session_id)s
      AND user_id = %(user_id)s
      AND deleted_at IS NULL
    """
    params = {"user_id": user_id, "session_id": session_id}
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(session_sql, params)
            session_row = cur.fetchone()
            if session_row is None:
                return None
            item_rows = _load_user_review_items(cur, user_id=user_id, session_id=session_id)
    return _serialize_user_review_session(
        session_row,
        [_serialize_user_review_item(row) for row in item_rows],
    )


def create_user_review_session(
    *,
    user_id: int,
    trade_date: str,
    title: str,
    summary: str,
    market_view: str,
    position_view: str,
    next_action: str,
    items: list[dict[str, Any]],
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, object]:
    normalized_items = [_normalize_review_item_for_create(item) for item in items]
    session_sql = f"""
    INSERT INTO journal.user_review_session (
        user_id,
        trade_date,
        title,
        summary,
        market_view,
        position_view,
        next_action
    )
    VALUES (
        %(user_id)s,
        %(trade_date)s,
        %(title)s,
        %(summary)s,
        %(market_view)s,
        %(position_view)s,
        %(next_action)s
    )
    RETURNING {USER_REVIEW_SESSION_COLUMNS}
    """
    session_params = {
        "user_id": user_id,
        "trade_date": trade_date,
        "title": title,
        "summary": summary,
        "market_view": market_view,
        "position_view": position_view,
        "next_action": next_action,
    }
    created_items: list[dict[str, object]] = []
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(session_sql, session_params)
            session_row = cur.fetchone()
            if session_row is None:
                raise RuntimeError("failed to create review session")
            session_id = int(session_row["id"])
            for item in normalized_items:
                cur.execute(
                    f"""
                    INSERT INTO journal.user_review_item (
                        session_id,
                        user_id,
                        asset_id,
                        decision,
                        conviction,
                        tags,
                        notes,
                        follow_up_required
                    )
                    VALUES (
                        %(session_id)s,
                        %(user_id)s,
                        %(asset_id)s,
                        %(decision)s,
                        %(conviction)s,
                        %(tags)s::jsonb,
                        %(notes)s,
                        %(follow_up_required)s
                    )
                    RETURNING {USER_REVIEW_ITEM_COLUMNS}
                    """,
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                        "asset_id": item["asset_id"],
                        "decision": item["decision"],
                        "conviction": item["conviction"],
                        "tags": json.dumps(item["tags"], ensure_ascii=False),
                        "notes": item["notes"],
                        "follow_up_required": item["follow_up_required"],
                    },
                )
                item_row = cur.fetchone()
                if item_row is None:
                    raise RuntimeError("failed to create review item")
                created_items.append(_serialize_user_review_item(item_row))
            _insert_audit_log(
                cur,
                action="review_create_session",
                target_type="user_review_session",
                target_id=str(session_id),
                actor_user_id=actor_user_id,
                metadata={"item_count": len(created_items), "user_id": user_id},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return _serialize_user_review_session(session_row, created_items)


def update_user_review_session(
    *,
    user_id: int,
    session_id: int,
    trade_date: str | None,
    title: str | None,
    summary: str | None,
    market_view: str | None,
    position_view: str | None,
    next_action: str | None,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, object] | None:
    sql = f"""
    UPDATE journal.user_review_session
    SET trade_date = COALESCE(%(trade_date)s, trade_date),
        title = COALESCE(%(title)s, title),
        summary = COALESCE(%(summary)s, summary),
        market_view = COALESCE(%(market_view)s, market_view),
        position_view = COALESCE(%(position_view)s, position_view),
        next_action = COALESCE(%(next_action)s, next_action),
        updated_at = now()
    WHERE id = %(session_id)s
      AND user_id = %(user_id)s
      AND deleted_at IS NULL
    RETURNING {USER_REVIEW_SESSION_COLUMNS}
    """
    params = {
        "user_id": user_id,
        "session_id": session_id,
        "trade_date": trade_date,
        "title": title,
        "summary": summary,
        "market_view": market_view,
        "position_view": position_view,
        "next_action": next_action,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            item_rows = _load_user_review_items(cur, user_id=user_id, session_id=session_id)
            _insert_audit_log(
                cur,
                action="review_update_session",
                target_type="user_review_session",
                target_id=str(session_id),
                actor_user_id=actor_user_id,
                metadata={"session_id": session_id, "user_id": user_id},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return _serialize_user_review_session(
        row,
        [_serialize_user_review_item(item_row) for item_row in item_rows],
    )


def create_user_review_item(
    *,
    user_id: int,
    session_id: int,
    asset_id: str,
    decision: str,
    conviction: str,
    tags: list[str] | None,
    notes: str | None,
    follow_up_required: bool | None,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, object] | None:
    normalized_item = _normalize_review_item_for_create(
        {
            "asset_id": asset_id,
            "decision": decision,
            "conviction": conviction,
            "tags": tags,
            "notes": notes,
            "follow_up_required": follow_up_required,
        }
    )
    sql = f"""
    INSERT INTO journal.user_review_item (
        session_id,
        user_id,
        asset_id,
        decision,
        conviction,
        tags,
        notes,
        follow_up_required
    )
    SELECT
        %(session_id)s,
        %(user_id)s,
        %(asset_id)s,
        %(decision)s,
        %(conviction)s,
        %(tags)s::jsonb,
        %(notes)s,
        %(follow_up_required)s
    FROM journal.user_review_session AS session
    WHERE session.id = %(session_id)s
      AND session.user_id = %(user_id)s
      AND session.deleted_at IS NULL
    RETURNING {USER_REVIEW_ITEM_COLUMNS}
    """
    params = {
        "user_id": user_id,
        "session_id": session_id,
        "asset_id": normalized_item["asset_id"],
        "decision": normalized_item["decision"],
        "conviction": normalized_item["conviction"],
        "tags": json.dumps(normalized_item["tags"], ensure_ascii=False),
        "notes": normalized_item["notes"],
        "follow_up_required": normalized_item["follow_up_required"],
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            _insert_audit_log(
                cur,
                action="review_create_item",
                target_type="user_review_item",
                target_id=str(row["id"]),
                actor_user_id=actor_user_id,
                metadata={"item_id": int(row["id"]), "session_id": session_id, "user_id": user_id},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return _serialize_user_review_item(row)


def update_user_review_item(
    *,
    user_id: int,
    session_id: int,
    item_id: int,
    decision: str | None,
    conviction: str | None,
    tags: list[str] | None,
    notes: str | None,
    follow_up_required: bool | None,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, object] | None:
    sql = f"""
    UPDATE journal.user_review_item AS item
    SET decision = COALESCE(%(decision)s, item.decision),
        conviction = COALESCE(%(conviction)s, item.conviction),
        tags = COALESCE(%(tags)s::jsonb, item.tags),
        notes = COALESCE(%(notes)s, item.notes),
        follow_up_required = COALESCE(%(follow_up_required)s, item.follow_up_required),
        updated_at = now()
    FROM journal.user_review_session AS session
    WHERE item.id = %(item_id)s
      AND item.user_id = %(user_id)s
      AND item.session_id = %(session_id)s
      AND item.session_id = session.id
      AND session.user_id = %(user_id)s
      AND item.deleted_at IS NULL
      AND session.deleted_at IS NULL
    RETURNING {", ".join(f'item.{column.strip()}' for column in USER_REVIEW_ITEM_COLUMNS.split(","))}
    """
    params = {
        "user_id": user_id,
        "session_id": session_id,
        "item_id": item_id,
        "decision": decision,
        "conviction": conviction,
        "tags": None if tags is None else json.dumps(_normalize_tags(tags), ensure_ascii=False),
        "notes": notes,
        "follow_up_required": follow_up_required,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            _insert_audit_log(
                cur,
                action="review_update_item",
                target_type="user_review_item",
                target_id=str(item_id),
                actor_user_id=actor_user_id,
                metadata={"item_id": item_id, "session_id": session_id, "user_id": user_id},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return _serialize_user_review_item(row)


def soft_delete_user_review_session(
    *,
    user_id: int,
    session_id: int,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> bool:
    sql = """
    UPDATE journal.user_review_session
    SET deleted_at = now(),
        updated_at = now()
    WHERE id = %(session_id)s
      AND user_id = %(user_id)s
      AND deleted_at IS NULL
    RETURNING id
    """
    params = {"user_id": user_id, "session_id": session_id}
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return False
            cur.execute(
                """
                UPDATE journal.user_review_item
                SET deleted_at = now(),
                    updated_at = now()
                WHERE user_id = %(user_id)s
                  AND session_id = %(session_id)s
                  AND deleted_at IS NULL
                RETURNING session_id
                """,
                params,
            )
            cur.fetchone()
            _insert_audit_log(
                cur,
                action="review_delete_session",
                target_type="user_review_session",
                target_id=str(session_id),
                actor_user_id=actor_user_id,
                metadata={"session_id": session_id, "user_id": user_id},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return True


def soft_delete_user_review_item(
    *,
    user_id: int,
    session_id: int,
    item_id: int,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> bool:
    sql = """
    UPDATE journal.user_review_item AS item
    SET deleted_at = now(),
        updated_at = now()
    FROM journal.user_review_session AS session
    WHERE item.id = %(item_id)s
      AND item.user_id = %(user_id)s
      AND item.session_id = %(session_id)s
      AND item.session_id = session.id
      AND session.user_id = %(user_id)s
      AND item.deleted_at IS NULL
      AND session.deleted_at IS NULL
    RETURNING item.id
    """
    params = {"user_id": user_id, "session_id": session_id, "item_id": item_id}
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return False
            _insert_audit_log(
                cur,
                action="review_delete_item",
                target_type="user_review_item",
                target_id=str(item_id),
                actor_user_id=actor_user_id,
                metadata={"item_id": item_id, "session_id": session_id, "user_id": user_id},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return True


def _serialize_user_review_session(
    row: dict[str, Any],
    items: list[dict[str, object]],
) -> dict[str, object]:
    return UserReviewSession(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        trade_date=_serialize_value(row["trade_date"]),
        title=str(row["title"]),
        summary=str(row["summary"]),
        market_view=str(row["market_view"]),
        position_view=str(row["position_view"]),
        next_action=str(row["next_action"]),
        created_at=_serialize_value(row["created_at"]),
        updated_at=_serialize_value(row["updated_at"]),
        items=items,
    ).to_dict()


def _serialize_user_review_item(row: dict[str, Any]) -> dict[str, object]:
    return UserReviewItem(
        id=int(row["id"]),
        session_id=int(row["session_id"]),
        user_id=int(row["user_id"]),
        asset_id=str(row["asset_id"]),
        decision=str(row["decision"]),
        conviction=str(row["conviction"]),
        tags=_normalize_tags(row.get("tags")),
        notes=str(row["notes"]),
        follow_up_required=bool(row["follow_up_required"]),
        created_at=_serialize_value(row["created_at"]),
        updated_at=_serialize_value(row["updated_at"]),
    ).to_dict()


def _load_user_review_items(cur, *, user_id: int, session_id: int) -> list[dict[str, Any]]:
    cur.execute(
        f"""
        SELECT {USER_REVIEW_ITEM_COLUMNS}
        FROM journal.user_review_item
        WHERE user_id = %(user_id)s
          AND session_id = %(session_id)s
          AND deleted_at IS NULL
        ORDER BY updated_at DESC, id DESC
        """,
        {"user_id": user_id, "session_id": session_id},
    )
    return cur.fetchall()


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(tag) for tag in parsed]
        return [str(parsed)]
    if isinstance(value, list):
        return [str(tag) for tag in value]
    return [str(value)]


def _normalize_review_item_for_create(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": _required_text(item, "asset_id"),
        "decision": _required_text(item, "decision"),
        "conviction": _required_text(item, "conviction"),
        "tags": _normalize_tags(item.get("tags")),
        "notes": str(item.get("notes") or ""),
        "follow_up_required": bool(item.get("follow_up_required")),
    }


def _required_text(item: dict[str, Any], field_name: str) -> str:
    value = str(item.get(field_name) or "").strip()
    if not value:
        raise ValueError(f"review item requires {field_name}")
    return value


def _serialize_value(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


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
