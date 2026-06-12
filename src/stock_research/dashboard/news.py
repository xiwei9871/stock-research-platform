from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.public_news.models import PublicNewsItem


MAX_LIMIT = 300
DEFAULT_LIMIT = 100
VALID_SOURCE_STATUSES = {"available", "permission_denied", "disabled"}


def _bounded_limit(value: int | None) -> int:
    try:
        limit = int(value or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, limit))


def _bounded_offset(value: int | None) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _json_metadata(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _timestamp_to_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _coerce_db_timestamp(value: object) -> str:
    text = _clean(value)
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    for candidate in (normalized, normalized.replace(" ", "T", 1)):
        try:
            datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return normalized
    return ""


def _source_timestamp(item: PublicNewsItem) -> str:
    return (
        _coerce_db_timestamp(item.published_at)
        or _coerce_db_timestamp(item.collected_at)
        or datetime.now(UTC).isoformat()
    )


def _collected_timestamp(item: PublicNewsItem) -> str:
    return _coerce_db_timestamp(item.collected_at) or datetime.now(UTC).isoformat()


def _source_status(item: PublicNewsItem) -> str:
    status = _clean(item.status)
    return status if status in VALID_SOURCE_STATUSES else "available"


def _count_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"name": str(row.get("name") or ""), "rows": int(row.get("rows") or 0)} for row in rows]


def _item_to_source_row(item: PublicNewsItem) -> dict[str, Any]:
    metadata = {
        "category": item.category or "other",
        "raw_id": item.raw_id,
        "raw_payload": item.raw_payload,
    }
    return {
        "source_event_id": item.news_id,
        "source_name": item.source,
        "source_channel": item.source_channel,
        "title": item.title,
        "content": item.summary,
        "published_at": _source_timestamp(item),
        "collected_at": _collected_timestamp(item),
        "language": "zh",
        "url": item.url or None,
        "hash_key": item.news_id,
        "source_status": _source_status(item),
        "metadata": json.dumps(metadata, ensure_ascii=False),
    }


def _stock_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": str(row.get("asset_id") or ""),
        "ts_code": str(row.get("ts_code") or ""),
        "stock_name": str(row.get("stock_name") or ""),
        "mention_role": str(row.get("mention_role") or ""),
        "mention_confidence": row.get("mention_confidence"),
        "theme_name": str(row.get("theme_name") or ""),
        "theme_confidence": row.get("theme_confidence"),
        "mapping_method": str(row.get("mapping_method") or ""),
        "trade_date": str(row.get("trade_date") or ""),
    }


def _news_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _json_metadata(row.get("metadata"))
    category = str(metadata.get("category") or row.get("category") or "other")
    stocks_value = row.get("stocks")
    stocks = [_stock_row(stock) for stock in stocks_value] if isinstance(stocks_value, list) else []
    return {
        "id": str(row.get("source_event_id") or ""),
        "news_id": str(row.get("source_event_id") or ""),
        "source": str(row.get("source_name") or ""),
        "source_channel": str(row.get("source_channel") or ""),
        "category": category,
        "title": str(row.get("title") or ""),
        "summary": str(row.get("content") or ""),
        "url": str(row.get("url") or ""),
        "published_at": _timestamp_to_string(row.get("published_at")),
        "collected_at": _timestamp_to_string(row.get("collected_at")),
        "raw_id": str(metadata.get("raw_id") or row.get("source_event_id") or ""),
        "raw_payload": metadata.get("raw_payload") if isinstance(metadata.get("raw_payload"), dict) else {},
        "status": str(row.get("source_status") or "available"),
        "stocks": stocks,
        "metadata": metadata,
    }


def _build_news_filters(**filters: Any) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    source = _clean(filters.get("source"))
    if source:
        clauses.append("s.source_name = %s")
        params.append(source)
    category = _clean(filters.get("category"))
    if category and category != "all":
        clauses.append("s.metadata->>'category' = %s")
        params.append(category)
    q = _clean(filters.get("q"))
    if q:
        term = f"%{q}%"
        clauses.append("(s.title ILIKE %s OR COALESCE(s.content, '') ILIKE %s)")
        params.extend([term, term])
    start_time = _clean(filters.get("start_time"))
    if start_time:
        clauses.append("s.published_at >= %s")
        params.append(start_time)
    end_time = _clean(filters.get("end_time"))
    if end_time:
        clauses.append("s.published_at <= %s")
        params.append(end_time)
    asset_id = _clean(filters.get("asset_id"))
    if asset_id:
        clauses.append("m.asset_id = %s")
        params.append(asset_id)
    ts_code = _clean(filters.get("ts_code"))
    if ts_code:
        clauses.append("m.ts_code = %s")
        params.append(ts_code)
    return clauses, params


class NewsEventStore:
    def __init__(self, service: str = SETTINGS.research_service) -> None:
        self.service = service

    def upsert_public_items(self, items: Iterable[PublicNewsItem]) -> dict[str, int]:
        rows = [_item_to_source_row(item) for item in items]
        if not rows:
            return {"received": 0, "stored": 0}
        with connect(self.service) as conn:
            execute_many(
                conn,
                """
                INSERT INTO research.news_event_source (
                    source_event_id, source_name, source_channel, title, content,
                    published_at, collected_at, language, url, hash_key,
                    source_status, metadata
                )
                VALUES (
                    %(source_event_id)s, %(source_name)s, %(source_channel)s,
                    %(title)s, %(content)s, %(published_at)s, %(collected_at)s,
                    %(language)s, %(url)s, %(hash_key)s, %(source_status)s,
                    %(metadata)s::jsonb
                )
                ON CONFLICT (source_event_id) DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    source_channel = EXCLUDED.source_channel,
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    published_at = EXCLUDED.published_at,
                    collected_at = EXCLUDED.collected_at,
                    language = EXCLUDED.language,
                    url = EXCLUDED.url,
                    hash_key = EXCLUDED.hash_key,
                    source_status = EXCLUDED.source_status,
                    metadata = EXCLUDED.metadata
                """,
                rows,
            )
        return {"received": len(rows), "stored": len(rows)}

    def list_news(
        self,
        *,
        source: str | None = None,
        category: str | None = None,
        q: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        asset_id: str | None = None,
        ts_code: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        clauses, params = _build_news_filters(
            source=source,
            category=category,
            q=q,
            start_time=start_time,
            end_time=end_time,
            asset_id=asset_id,
            ts_code=ts_code,
        )
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        bounded_limit = _bounded_limit(limit)
        bounded_offset = _bounded_offset(offset)
        with connect(self.service) as conn:
            total_rows = fetch_all(
                conn,
                f"""
                SELECT COUNT(*) AS total
                FROM (
                    SELECT DISTINCT s.source_event_id
                    FROM research.news_event_source AS s
                    LEFT JOIN research.news_event_mention AS m USING (source_event_id)
                    {where_sql}
                ) filtered_news
                """,
                params,
            )
            rows = fetch_all(
                conn,
                f"""
                SELECT
                    s.source_event_id, s.source_name, s.source_channel, s.title,
                    s.content, s.published_at, s.collected_at, s.url,
                    s.source_status, s.metadata,
                    COALESCE(
                        jsonb_agg(
                            jsonb_build_object(
                                'asset_id', m.asset_id,
                                'ts_code', m.ts_code,
                                'stock_name', m.stock_name,
                                'mention_role', m.mention_role,
                                'mention_confidence', m.mention_confidence,
                                'theme_name', m.theme_name,
                                'theme_confidence', m.theme_confidence,
                                'mapping_method', m.mapping_method,
                                'trade_date', m.trade_date
                            )
                            ORDER BY m.mention_confidence DESC NULLS LAST,
                                     m.ts_code,
                                     m.asset_id
                        ) FILTER (WHERE m.mention_id IS NOT NULL),
                        '[]'::jsonb
                    ) AS stocks
                FROM research.news_event_source s
                LEFT JOIN research.news_event_mention m USING (source_event_id)
                {where_sql}
                GROUP BY s.source_event_id
                ORDER BY s.published_at DESC, s.collected_at DESC, s.source_event_id
                LIMIT %s OFFSET %s
                """,
                [*params, bounded_limit, bounded_offset],
            )
            summary = self.summary(conn=conn)
        items = [_news_row(row) for row in rows]
        total = int(total_rows[0]["total"]) if total_rows else 0
        return {
            "items": items,
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
            "summary": summary,
            "warnings": [] if items else ["no matching public news items"],
        }

    def summary(self, conn: Any | None = None) -> dict[str, Any]:
        def _run(active_conn: Any) -> dict[str, Any]:
            summary_rows = fetch_all(
                active_conn,
                """
                SELECT COUNT(*) AS total_news,
                       MAX(published_at) AS latest_published_at,
                       MAX(collected_at) AS latest_collected_at,
                       COUNT(DISTINCT source_name) AS source_count
                FROM research.news_event_source
                """,
            )
            source_counts = fetch_all(
                active_conn,
                """
                SELECT source_name AS name, COUNT(*) AS rows
                FROM research.news_event_source
                GROUP BY source_name
                ORDER BY rows DESC, source_name
                LIMIT 20
                """,
            )
            category_counts = fetch_all(
                active_conn,
                """
                SELECT COALESCE(metadata->>'category', 'other') AS name, COUNT(*) AS rows
                FROM research.news_event_source
                GROUP BY name
                ORDER BY rows DESC, name
                LIMIT 20
                """,
            )
            row = summary_rows[0] if summary_rows else {}
            return {
                "total_news": int(row.get("total_news") or 0),
                "latest_published_at": _timestamp_to_string(row.get("latest_published_at")),
                "latest_collected_at": _timestamp_to_string(row.get("latest_collected_at")),
                "source_count": int(row.get("source_count") or 0),
                "source_counts": _count_rows(source_counts),
                "category_counts": _count_rows(category_counts),
            }

        if conn is not None:
            return _run(conn)
        with connect(self.service) as active_conn:
            return _run(active_conn)
