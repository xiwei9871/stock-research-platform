from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from stock_research.public_news.models import PublicNewsItem


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDb:
    def __init__(self) -> None:
        self.source_rows: dict[str, dict[str, Any]] = {}
        self.mention_rows: list[dict[str, Any]] = []
        self.calls: list[tuple[str, list[Any]]] = []

    def fetch_all(self, _conn: FakeConn, sql: str, params: list[Any] | None = None):
        self.calls.append((sql, list(params or [])))
        compact = " ".join(sql.split())
        if "FROM research.news_event_source s LEFT JOIN research.news_event_mention m" in compact:
            rows = list(self.source_rows.values())
            if "metadata->>'category' = %s" in compact:
                category = params[0]
                rows = [row for row in rows if row["metadata"].get("category") == category]
            rows = sorted(rows, key=lambda row: row["published_at"], reverse=True)
            return [
                {
                    **row,
                    "stocks": [
                        mention
                        for mention in self.mention_rows
                        if mention["source_event_id"] == row["source_event_id"]
                    ],
                }
                for row in rows
            ]
        if compact.startswith("SELECT COUNT(*) AS total"):
            return [{"total": len(self.source_rows)}]
        if compact.startswith("SELECT COUNT(*) AS total_news"):
            latest = max((row["published_at"] for row in self.source_rows.values()), default=None)
            return [
                {
                    "total_news": len(self.source_rows),
                    "latest_published_at": latest,
                    "latest_collected_at": latest,
                    "source_count": len({row["source_name"] for row in self.source_rows.values()}),
                }
            ]
        if "GROUP BY source_name" in compact:
            return [{"name": "sina_finance", "rows": len(self.source_rows)}]
        if "GROUP BY name" in compact:
            return [{"name": "live", "rows": len(self.source_rows)}]
        raise AssertionError(f"unexpected query: {compact}")

    def execute_many(self, _conn: FakeConn, sql: str, rows: list[dict[str, Any]]):
        self.calls.append((sql, rows))
        if "INSERT INTO research.news_event_source" in sql:
            for row in rows:
                stored = dict(row)
                if isinstance(stored.get("metadata"), str):
                    import json

                    stored["metadata"] = json.loads(stored["metadata"])
                self.source_rows[row["source_event_id"]] = stored
            return
        if "INSERT INTO research.news_event_mention" in sql:
            self.mention_rows.extend(rows)
            return
        raise AssertionError(sql)

    def execute(self, _conn: FakeConn, sql: str, params: list[Any] | None = None):
        self.calls.append((sql, list(params or [])))
        if "DELETE FROM research.news_event_mention" in sql:
            source_event_ids = set((params or [[]])[0])
            self.mention_rows = [
                row for row in self.mention_rows if row["source_event_id"] not in source_event_ids
            ]
            return
        raise AssertionError(sql)


def make_item(**overrides: Any) -> PublicNewsItem:
    values = {
        "source": "sina_finance",
        "source_channel": "7x24",
        "category": "live",
        "title": "贵州茅台 600519 发布经营快讯",
        "summary": "公司经营稳健",
        "url": "https://finance.sina.com.cn/doc/example.shtml",
        "published_at": "2026-06-12 09:30:00",
        "raw_id": "raw-1",
        "raw_payload": {"href": "/doc/example.shtml"},
    }
    values.update(overrides)
    return PublicNewsItem.from_raw(**values)


def test_news_event_store_upserts_public_news_items(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    store = news.NewsEventStore(service="test")

    result = store.upsert_public_items([make_item()])

    assert result == {"received": 1, "stored": 1}
    stored = next(iter(fake.source_rows.values()))
    assert stored["source_name"] == "sina_finance"
    assert stored["source_channel"] == "7x24"
    assert stored["metadata"]["category"] == "live"
    assert stored["metadata"]["raw_id"] == "raw-1"
    assert stored["source_status"] == "available"


def test_news_event_store_lists_by_category_with_summary(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    store = news.NewsEventStore(service="test")
    store.upsert_public_items([make_item()])

    payload = store.list_news(category="live", limit=20)

    assert payload["total"] == 1
    assert payload["summary"]["total_news"] == 1
    assert payload["summary"]["latest_published_at"].startswith("2026-06-12")
    assert payload["summary"]["category_counts"] == [{"name": "live", "rows": 1}]
    assert payload["items"][0]["category"] == "live"
    assert payload["items"][0]["stocks"] == []
