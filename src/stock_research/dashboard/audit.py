import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def record_audit_log(
    *,
    action: str,
    target_type: str,
    target_id: str,
    actor_user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> None:
    sql = """
    INSERT INTO audit.audit_log (
        actor_user_id, action, target_type, target_id, metadata, ip_address, user_agent
    )
    VALUES (
        %(actor_user_id)s, %(action)s, %(target_type)s, %(target_id)s,
        %(metadata)s::jsonb, %(ip_address)s, %(user_agent)s
    )
    """
    params = {
        "actor_user_id": actor_user_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "metadata": json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        "ip_address": ip_address,
        "user_agent": user_agent,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
