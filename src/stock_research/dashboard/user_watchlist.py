import json
from datetime import date
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.user_models import UserWatchlistItem
from stock_research.db import connect


USER_WATCHLIST_ITEM_COLUMNS = """
    id,
    user_id,
    asset_id,
    trade_date_added,
    source,
    notes,
    created_at,
    updated_at
"""


def list_user_watchlist_items(
    *,
    user_id: int,
    service: str = SETTINGS.research_service,
) -> list[dict[str, object]]:
    sql = f"""
    SELECT {USER_WATCHLIST_ITEM_COLUMNS}
    FROM watchlist.user_watchlist_item
    WHERE user_id = %(user_id)s
      AND deleted_at IS NULL
    ORDER BY updated_at DESC, asset_id ASC
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id})
            rows = cur.fetchall()
    return [_serialize_user_watchlist_item(row) for row in rows]


def create_user_watchlist_item(
    *,
    user_id: int,
    asset_id: str,
    source: str,
    notes: str,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, object]:
    sql = f"""
    INSERT INTO watchlist.user_watchlist_item (
        user_id,
        asset_id,
        trade_date_added,
        source,
        notes
    )
    VALUES (
        %(user_id)s,
        %(asset_id)s,
        %(trade_date_added)s,
        %(source)s,
        %(notes)s
    )
    RETURNING {USER_WATCHLIST_ITEM_COLUMNS}
    """
    params = {
        "user_id": user_id,
        "asset_id": asset_id,
        "trade_date_added": date.today().isoformat(),
        "source": source,
        "notes": notes,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("failed to create watchlist item")
            _insert_audit_log(
                cur,
                actor_user_id=actor_user_id,
                action="watchlist_add_item",
                target_id=asset_id,
                metadata={"asset_id": asset_id, "user_id": user_id},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return _serialize_user_watchlist_item(row)


def update_user_watchlist_item(
    *,
    user_id: int,
    asset_id: str,
    source: str | None,
    notes: str | None,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, object] | None:
    sql = f"""
    UPDATE watchlist.user_watchlist_item
    SET source = COALESCE(%(source)s, source),
        notes = COALESCE(%(notes)s, notes),
        updated_at = now()
    WHERE user_id = %(user_id)s
      AND asset_id = %(asset_id)s
      AND deleted_at IS NULL
    RETURNING {USER_WATCHLIST_ITEM_COLUMNS}
    """
    params = {
        "user_id": user_id,
        "asset_id": asset_id,
        "source": source,
        "notes": notes,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            _insert_audit_log(
                cur,
                actor_user_id=actor_user_id,
                action="watchlist_update_item",
                target_id=asset_id,
                metadata={"asset_id": asset_id, "user_id": user_id},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return _serialize_user_watchlist_item(row)


def soft_delete_user_watchlist_item(
    *,
    user_id: int,
    asset_id: str,
    actor_user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> bool:
    sql = """
    UPDATE watchlist.user_watchlist_item
    SET deleted_at = now(),
        updated_at = now()
    WHERE user_id = %(user_id)s
      AND asset_id = %(asset_id)s
      AND deleted_at IS NULL
    RETURNING asset_id
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id, "asset_id": asset_id})
            row = cur.fetchone()
            if row is None:
                return False
            _insert_audit_log(
                cur,
                actor_user_id=actor_user_id,
                action="watchlist_remove_item",
                target_id=asset_id,
                metadata={"asset_id": asset_id, "user_id": user_id},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return True


def _serialize_user_watchlist_item(row: dict[str, Any]) -> dict[str, object]:
    return UserWatchlistItem(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        asset_id=str(row["asset_id"]),
        trade_date_added=_serialize_value(row["trade_date_added"]),
        source=str(row["source"]),
        notes=str(row["notes"]),
        created_at=_serialize_value(row["created_at"]),
        updated_at=_serialize_value(row["updated_at"]),
    ).to_dict()


def _serialize_value(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _insert_audit_log(
    cur,
    *,
    action: str,
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
            "target_type": "user_watchlist_item",
            "target_id": target_id,
            "metadata": json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            "ip_address": ip_address,
            "user_agent": user_agent,
        },
    )
