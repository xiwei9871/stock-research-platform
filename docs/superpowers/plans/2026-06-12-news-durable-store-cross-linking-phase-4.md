# News Durable Store And Cross-Linking Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make dashboard news DB-first by persisting public news to `research.news_event_source`, linking stock mentions through `research.news_event_mention`, and surfacing those links in News and Stock Workspace.

**Architecture:** Add a focused dashboard news read/write layer instead of expanding the JSON cache store. Public news adapters still produce `PublicNewsItem`; ingestion converts those items into database rows, runs deterministic mention mapping, and keeps the JSON cache as fallback. FastAPI routes stay mostly stable while adding asset-news retrieval for Stock Workspace.

**Tech Stack:** Python 3, FastAPI, PostgreSQL/psycopg via existing `stock_research.db`, pytest, React/Vite, TypeScript, Vitest, Playwright.

---

## File Structure

- Create: `src/stock_research/dashboard/news.py`
  - DB-first store, read model, ingestion service, and asset-news loader for dashboard routes.
  - Keep this dashboard-facing layer separate from source-specific adapters.
- Modify: `src/stock_research/public_news/service.py`
  - Delegate default dashboard load/refresh functions to `stock_research.dashboard.news`.
  - Keep `PublicNewsService` available for JSON-only tests and fallback behavior.
- Modify: `src/stock_research/dashboard/app.py`
  - Add new query parameters to `/api/public-news`.
  - Add `/api/assets/{asset_id}/news`.
- Test: `tests/test_dashboard_news.py`
  - Backend tests for DB upsert/listing, fallback, refresh, and asset news.
- Modify: `dashboard/src/api/types.ts`
  - Extend `PublicNewsItem` and `PublicNewsResponse`.
  - Add `AssetNewsResponse`.
- Modify: `dashboard/src/api/client.ts`
  - Add public-news time/asset params.
  - Add `fetchAssetNews`.
- Modify: `dashboard/src/components/NewsWorkspace.tsx`
  - Use API-provided stock mentions and freshness.
  - Preserve existing categories.
- Modify: `dashboard/src/components/StockWorkspace.tsx`
  - Replace keyword-filtered news with asset-news endpoint.
- Test: `dashboard/tests/client.test.ts`
  - Client URL/response tests.
- Test: `dashboard/tests/news-workspace.test.tsx`
  - DB-backed freshness, warning, and stock-chip behavior.
- Test: `dashboard/tests/stock-workspace.test.tsx`
  - Asset-news loading and stale-response guard.
- Modify if needed: `dashboard/tests/app-shell.test.tsx`, `dashboard/tests/app-smoke.spec.ts`
  - Keep existing shell/smoke mocks compatible with extended response shapes.

## Task 1: Backend News DB Store And Listing

**Files:**
- Create: `src/stock_research/dashboard/news.py`
- Create: `tests/test_dashboard_news.py`

- [ ] **Step 1: Write failing DB-store tests**

Add `tests/test_dashboard_news.py` with these tests. They use a fake connection through monkeypatching so they do not need a live database.

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_news.py -v
```

Expected: FAIL because `stock_research.dashboard.news` does not exist.

- [ ] **Step 3: Implement `NewsEventStore`**

Create `src/stock_research/dashboard/news.py` with this initial implementation. Keep later services out until the next tasks.

```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Iterable

from stock_research.config import SETTINGS
from stock_research.db import connect, execute, execute_many, fetch_all
from stock_research.public_news.models import PublicNewsItem


MAX_LIMIT = 300
DEFAULT_LIMIT = 100


def _bounded_limit(limit: int) -> int:
    return max(1, min(MAX_LIMIT, int(limit or DEFAULT_LIMIT)))


def _bounded_offset(offset: int) -> int:
    return max(0, int(offset or 0))


def _clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _json_metadata(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
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
        "published_at": item.published_at,
        "collected_at": item.collected_at or datetime.now(UTC).isoformat(),
        "language": "zh",
        "url": item.url or None,
        "hash_key": item.news_id,
        "source_status": item.status or "available",
        "metadata": json.dumps(metadata, ensure_ascii=False),
    }


def _stock_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": str(row.get("asset_id") or ""),
        "ts_code": str(row.get("ts_code") or ""),
        "stock_name": str(row.get("stock_name") or ""),
        "mention_role": str(row.get("mention_role") or ""),
        "mention_confidence": row.get("mention_confidence"),
        "mapping_method": str(row.get("mapping_method") or ""),
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
                SELECT COUNT(DISTINCT s.source_event_id) AS total
                FROM research.news_event_source s
                LEFT JOIN research.news_event_mention m USING (source_event_id)
                {where_sql}
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
                                'mapping_method', m.mapping_method
                            )
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
        total = int(total_rows[0]["total"]) if total_rows else 0
        items = [_news_row(row) for row in rows]
        return {
            "items": items,
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
            "summary": summary,
            "warnings": [] if items else ["no matching public news items"],
        }

    def summary(self, *, conn: Any | None = None) -> dict[str, Any]:
        def _run(active_conn: Any) -> dict[str, Any]:
            summary_rows = fetch_all(
                active_conn,
                """
                SELECT
                    COUNT(*) AS total_news,
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
        clauses.append("(s.title ILIKE %s OR COALESCE(s.content, '') ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
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
```

- [ ] **Step 4: Run tests to verify Task 1 passes**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_news.py -v
```

Expected: PASS for the two tests in this task.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/stock_research/dashboard/news.py tests/test_dashboard_news.py
git commit -m "feat: add db-backed dashboard news store"
```

## Task 2: News Mention Mapping And Asset News API Backend

**Files:**
- Modify: `src/stock_research/dashboard/news.py`
- Modify: `tests/test_dashboard_news.py`

- [ ] **Step 1: Add failing mention and asset-news tests**

Append these tests to `tests/test_dashboard_news.py`.

```python
def test_news_mention_mapper_links_exact_stock_names(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    fake.source_rows["event-1"] = {
        "source_event_id": "event-1",
        "source_name": "sina_finance",
        "source_channel": "公司",
        "title": "贵州茅台披露经营数据",
        "content": "贵州茅台营收保持增长",
        "published_at": "2026-06-12 09:30:00",
        "collected_at": "2026-06-12 09:31:00",
        "url": "https://finance.sina.com.cn/doc/maotai.shtml",
        "source_status": "available",
        "metadata": {"category": "company"},
    }
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute", fake.execute)
    monkeypatch.setattr(news, "execute_many", fake.execute_many)

    mapper = news.NewsMentionMapper(
        assets=[
            {"asset_id": "CN:SH:600519", "ts_code": "600519.SH", "name": "贵州茅台"},
            {"asset_id": "CN:SZ:000001", "ts_code": "000001.SZ", "name": "平安银行"},
        ],
        service="test",
    )
    result = mapper.map_items([make_item(title="贵州茅台披露经营数据", category="company")])

    assert result == {"mentions": 1}
    assert fake.mention_rows[0]["asset_id"] == "CN:SH:600519"
    assert fake.mention_rows[0]["ts_code"] == "600519.SH"
    assert fake.mention_rows[0]["mapping_method"] == "stock_name_exact"


def test_load_asset_news_returns_mention_linked_items(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute", fake.execute)
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    store = news.NewsEventStore(service="test")
    store.upsert_public_items([make_item(category="company")])
    fake.mention_rows.append(
        {
            "source_event_id": make_item(category="company").news_id,
            "asset_id": "CN:SH:600519",
            "ts_code": "600519.SH",
            "stock_name": "贵州茅台",
            "mention_role": "subject",
            "mention_confidence": 1.0,
            "mapping_method": "stock_name_exact",
        }
    )

    payload = news.load_asset_news("CN:SH:600519", limit=5, service="test")

    assert payload["asset_id"] == "CN:SH:600519"
    assert payload["items"][0]["stocks"][0]["stock_name"] == "贵州茅台"
    assert payload["summary"]["news_count_7d"] >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_news.py -v
```

Expected: FAIL because `NewsMentionMapper` and `load_asset_news` do not exist.

- [ ] **Step 3: Implement mention mapper and asset-news loader**

Add these imports and functions/classes to `src/stock_research/dashboard/news.py`.

```python
import re
from datetime import date, timedelta
```

Add below `NewsEventStore`:

```python
def _asset_rows_from_db(service: str) -> list[dict[str, str]]:
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT asset_id, ts_code, name
            FROM core.asset_master
            WHERE asset_id IS NOT NULL
              AND ts_code IS NOT NULL
              AND name IS NOT NULL
            """,
        )
    return [
        {
            "asset_id": str(row.get("asset_id") or ""),
            "ts_code": str(row.get("ts_code") or ""),
            "name": str(row.get("name") or ""),
        }
        for row in rows
    ]


class NewsMentionMapper:
    def __init__(
        self,
        *,
        assets: list[dict[str, str]] | None = None,
        service: str = SETTINGS.research_service,
    ) -> None:
        self.service = service
        self.assets = assets if assets is not None else _asset_rows_from_db(service)

    def map_items(self, items: Iterable[PublicNewsItem]) -> dict[str, int]:
        rows: list[dict[str, Any]] = []
        for item in items:
            text = f"{item.title} {item.summary} {item.url}"
            for asset in self.assets:
                mapping_method = self._match_method(text, asset)
                if not mapping_method:
                    continue
                rows.append(
                    {
                        "source_event_id": item.news_id,
                        "asset_id": asset["asset_id"],
                        "ts_code": asset["ts_code"],
                        "stock_name": asset["name"],
                        "mention_role": "subject",
                        "mention_confidence": 1.0,
                        "theme_name": None,
                        "theme_confidence": None,
                        "mapping_method": mapping_method,
                        "trade_date": _published_trade_date(item.published_at),
                    }
                )
        deduped = _dedupe_mentions(rows)
        if not deduped:
            return {"mentions": 0}
        source_event_ids = sorted({row["source_event_id"] for row in deduped})
        with connect(self.service) as conn:
            execute(
                conn,
                """
                DELETE FROM research.news_event_mention
                WHERE source_event_id = ANY(%s)
                """,
                [source_event_ids],
            )
            execute_many(
                conn,
                """
                INSERT INTO research.news_event_mention (
                    source_event_id, asset_id, ts_code, stock_name, mention_role,
                    mention_confidence, theme_name, theme_confidence, mapping_method,
                    trade_date
                )
                VALUES (
                    %(source_event_id)s, %(asset_id)s, %(ts_code)s, %(stock_name)s,
                    %(mention_role)s, %(mention_confidence)s, %(theme_name)s,
                    %(theme_confidence)s, %(mapping_method)s, %(trade_date)s
                )
                """,
                deduped,
            )
        return {"mentions": len(deduped)}

    def _match_method(self, text: str, asset: dict[str, str]) -> str:
        ts_code = asset.get("ts_code", "")
        symbol = ts_code.split(".")[0] if "." in ts_code else ts_code
        name = asset.get("name", "")
        if ts_code and re.search(rf"(?<![A-Za-z0-9]){re.escape(ts_code)}(?![A-Za-z0-9])", text):
            return "ts_code_exact"
        if symbol and re.search(rf"(?<!\d){re.escape(symbol)}(?!\d)", text):
            return "symbol_exact"
        if name and name in text:
            return "stock_name_exact"
        return ""


def _dedupe_mentions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = (row["source_event_id"], row["asset_id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _published_trade_date(value: str) -> str | None:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def load_asset_news(
    asset_id: str,
    *,
    limit: int = 20,
    lookback_days: int = 7,
    category: str | None = None,
    source: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    bounded_lookback = max(1, int(lookback_days or 7))
    start_time = (date.today() - timedelta(days=bounded_lookback)).isoformat()
    store = NewsEventStore(service=service)
    payload = store.list_news(
        asset_id=asset_id,
        category=category,
        source=source,
        start_time=start_time,
        limit=limit,
    )
    items = payload["items"]
    return {
        "asset_id": asset_id,
        "items": items,
        "summary": {
            "news_count_1d": len(items),
            "news_count_3d": len(items),
            "news_count_7d": len(items),
            "latest_published_at": items[0]["published_at"] if items else "",
            "source_count": len({item["source"] for item in items}),
            "category_counts": _category_counts_from_items(items),
        },
        "warnings": payload["warnings"],
    }


def _category_counts_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in items:
        category = str(item.get("category") or "other")
        counts[category] = counts.get(category, 0) + 1
    return [{"name": name, "rows": rows} for name, rows in sorted(counts.items())]
```

- [ ] **Step 4: Run backend tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_news.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/stock_research/dashboard/news.py tests/test_dashboard_news.py
git commit -m "feat: map dashboard news to stock mentions"
```

## Task 3: DB-First Public News Service And Routes

**Files:**
- Modify: `src/stock_research/dashboard/news.py`
- Modify: `src/stock_research/public_news/service.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_news.py`
- Modify: `tests/test_dashboard_app.py`

- [ ] **Step 1: Add failing service and route tests**

Append to `tests/test_dashboard_news.py`:

```python
def test_public_news_ingestion_writes_db_and_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    fake = FakeDb()
    item = make_item()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute", fake.execute)
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_sina_public_news", lambda: ([item], []))

    service = news.PublicNewsIngestionService(
        store=news.NewsEventStore(service="test"),
        fallback_store=JsonPublicNewsStore(tmp_path / "public_news.json"),
        mention_mapper=news.NewsMentionMapper(assets=[], service="test"),
    )
    result = service.refresh()

    assert result["items_received"] == 1
    assert result["stored"] == 1
    assert result["mentions"] == 0
    assert fake.source_rows[item.news_id]["title"] == item.title


def test_load_public_news_falls_back_to_json_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    fallback = JsonPublicNewsStore(tmp_path / "public_news.json")
    fallback.upsert_items([make_item(title="缓存新闻")])

    class FailingStore(news.NewsEventStore):
        def list_news(self, **_kwargs):
            raise RuntimeError("db offline")

    payload = news.load_public_news_for_dashboard(
        limit=5,
        store=FailingStore(service="test"),
        fallback_store=fallback,
    )

    assert payload["items"][0]["title"] == "缓存新闻"
    assert payload["summary"]["source_count"] == 1
    assert "fallback json cache used: db offline" in payload["warnings"]
```

Modify `tests/test_dashboard_app.py` route coverage so it expects the new asset-news route:

```python
def test_asset_news_endpoint(monkeypatch):
    from stock_research.dashboard import app as dashboard_app

    def fake_load_asset_news(asset_id, **kwargs):
        return {
            "asset_id": asset_id,
            "items": [],
            "summary": {"news_count_1d": 0, "news_count_3d": 0, "news_count_7d": 0},
            "warnings": ["no matching public news items"],
        }

    monkeypatch.setattr(dashboard_app, "load_asset_news", fake_load_asset_news)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/assets/CN:SH:600519/news?limit=5&lookback_days=7")

    assert response.status_code == 200
    assert response.json()["asset_id"] == "CN:SH:600519"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_news.py tests/test_dashboard_app.py -v
```

Expected: FAIL because ingestion service, fallback read function, and route import do not exist.

- [ ] **Step 3: Implement DB-first service functions**

Add to `src/stock_research/dashboard/news.py`:

```python
from collections import Counter
from stock_research.public_news.sina_adapter import fetch_sina_public_news
from stock_research.public_news.store import JsonPublicNewsStore


DEFAULT_PUBLIC_NEWS_CACHE = Path("outputs/dashboard/public_news_cache.json")
```

Also add `Path` import:

```python
from pathlib import Path
```

Append:

```python
class PublicNewsIngestionService:
    def __init__(
        self,
        *,
        store: NewsEventStore | None = None,
        fallback_store: JsonPublicNewsStore | None = None,
        mention_mapper: NewsMentionMapper | None = None,
    ) -> None:
        self.store = store or NewsEventStore()
        self.fallback_store = fallback_store or JsonPublicNewsStore(DEFAULT_PUBLIC_NEWS_CACHE)
        self.mention_mapper = mention_mapper or NewsMentionMapper()

    def refresh(self) -> dict[str, Any]:
        try:
            items, warnings = fetch_sina_public_news()
        except Exception as exc:
            items = []
            warnings = [f"sina_finance refresh failed: {exc}"]
        db_result = self.store.upsert_public_items(items) if items else {"received": 0, "stored": 0}
        cache_result = self.fallback_store.upsert_items(items) if items else {"received": 0, "stored": 0}
        mention_result = self.mention_mapper.map_items(items) if items else {"mentions": 0}
        counts_by_category = dict(Counter(item.category for item in items))
        return {
            **db_result,
            "items_received": len(items),
            "fallback_cache_stored": cache_result["stored"],
            "mentions": mention_result["mentions"],
            "counts_by_category": counts_by_category,
            "warnings": warnings,
        }


def _fallback_payload(
    *,
    fallback_store: JsonPublicNewsStore,
    warning: str,
    source: str | None = None,
    category: str | None = None,
    q: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    items = fallback_store.query(source=source, category=category, q=q, limit=limit, offset=offset)
    source_counts = Counter(item.source for item in items)
    category_counts = Counter(item.category for item in items)
    return {
        "items": [item.to_dict() | {"id": item.news_id, "stocks": [], "metadata": {}} for item in items],
        "total": len(items),
        "limit": _bounded_limit(limit),
        "offset": _bounded_offset(offset),
        "summary": {
            "total_news": len(items),
            "latest_published_at": items[0].published_at if items else "",
            "latest_collected_at": items[0].collected_at if items else "",
            "source_count": len(source_counts),
            "source_counts": [{"name": name, "rows": rows} for name, rows in source_counts.items()],
            "category_counts": [{"name": name, "rows": rows} for name, rows in category_counts.items()],
        },
        "warnings": [warning],
    }


def load_public_news_for_dashboard(
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
    store: NewsEventStore | None = None,
    fallback_store: JsonPublicNewsStore | None = None,
) -> dict[str, Any]:
    active_store = store or NewsEventStore()
    active_fallback = fallback_store or JsonPublicNewsStore(DEFAULT_PUBLIC_NEWS_CACHE)
    try:
        payload = active_store.list_news(
            source=source,
            category=category,
            q=q,
            start_time=start_time,
            end_time=end_time,
            asset_id=asset_id,
            ts_code=ts_code,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        return _fallback_payload(
            fallback_store=active_fallback,
            warning=f"fallback json cache used: {exc}",
            source=source,
            category=category,
            q=q,
            limit=limit,
            offset=offset,
        )
    if payload["items"]:
        return payload
    fallback = _fallback_payload(
        fallback_store=active_fallback,
        warning="fallback json cache used: no db public news items",
        source=source,
        category=category,
        q=q,
        limit=limit,
        offset=offset,
    )
    return fallback if fallback["items"] else payload


def refresh_public_news_for_dashboard() -> dict[str, Any]:
    return PublicNewsIngestionService().refresh()
```

- [ ] **Step 4: Delegate existing public-news service wrappers**

Modify `src/stock_research/public_news/service.py` so the module-level dashboard helpers import from the new dashboard module inside the functions. This avoids import cycles and preserves `PublicNewsService` for JSON tests.

```python
def refresh_public_news_for_dashboard() -> dict[str, Any]:
    from stock_research.dashboard.news import refresh_public_news_for_dashboard as refresh_db_news

    return refresh_db_news()


def load_public_news_for_dashboard(
    *,
    source: str | None = None,
    category: str | None = None,
    q: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    asset_id: str | None = None,
    ts_code: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    from stock_research.dashboard.news import load_public_news_for_dashboard as load_db_news

    return load_db_news(
        source=source,
        category=category,
        q=q,
        start_time=start_time,
        end_time=end_time,
        asset_id=asset_id,
        ts_code=ts_code,
        limit=limit,
        offset=offset,
    )
```

- [ ] **Step 5: Update FastAPI routes**

Modify imports in `src/stock_research/dashboard/app.py`:

```python
from stock_research.dashboard.news import (
    load_asset_news,
    load_public_news_for_dashboard,
    refresh_public_news_for_dashboard,
)
```

Remove the old import from `stock_research.public_news.service`.

Update `/api/public-news` signature:

```python
    @app.get("/api/public-news")
    def public_news(
        source: str | None = None,
        category: str | None = None,
        q: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        asset_id: str | None = None,
        ts_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return load_public_news_for_dashboard(
            source=source,
            category=category,
            q=q,
            start_time=start_time,
            end_time=end_time,
            asset_id=asset_id,
            ts_code=ts_code,
            limit=limit,
            offset=offset,
        )
```

Add after asset research reports route:

```python
    @app.get("/api/assets/{asset_id}/news")
    def asset_news(
        asset_id: str,
        limit: int = 20,
        lookback_days: int = 7,
        category: str | None = None,
        source: str | None = None,
    ):
        return load_asset_news(
            asset_id,
            limit=limit,
            lookback_days=lookback_days,
            category=category,
            source=source,
        )
```

- [ ] **Step 6: Run backend route tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_news.py tests/test_dashboard_app.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/stock_research/dashboard/news.py src/stock_research/public_news/service.py src/stock_research/dashboard/app.py tests/test_dashboard_news.py tests/test_dashboard_app.py
git commit -m "feat: route dashboard news through db store"
```

## Task 4: Frontend API Types And Client

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Add failing client tests**

Modify `dashboard/tests/client.test.ts` imports:

```typescript
import {
  fetchAssetNews,
  fetchAssetResearchReports,
  fetchPublicNews,
  refreshPublicNews
} from '../src/api/client';
```

Add or update tests:

```typescript
it('fetches public news with db filters', async () => {
  fetchMock.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        items: [],
        total: 0,
        limit: 10,
        offset: 2,
        summary: { total_news: 0, source_count: 0, source_counts: [], category_counts: [] },
        warnings: []
      }),
      { status: 200 }
    )
  );

  await fetchPublicNews({
    source: 'sina_finance',
    category: 'live',
    q: '快讯',
    startTime: '2026-06-12T00:00:00',
    endTime: '2026-06-12T23:59:59',
    assetId: 'CN:SH:600519',
    limit: 10,
    offset: 2
  });

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/public-news?source=sina_finance&category=live&q=%E5%BF%AB%E8%AE%AF&start_time=2026-06-12T00%3A00%3A00&end_time=2026-06-12T23%3A59%3A59&asset_id=CN%3ASH%3A600519&limit=10&offset=2'
  );
});

it('fetches asset news', async () => {
  fetchMock.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        asset_id: 'CN:SH:600519',
        items: [],
        summary: { news_count_1d: 0, news_count_3d: 0, news_count_7d: 0 },
        warnings: []
      }),
      { status: 200 }
    )
  );

  const result = await fetchAssetNews('CN:SH:600519', { limit: 5, lookbackDays: 7 });

  expect(fetchMock).toHaveBeenCalledWith('/api/assets/CN%3ASH%3A600519/news?limit=5&lookback_days=7');
  expect(result.asset_id).toBe('CN:SH:600519');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: FAIL because `fetchAssetNews` and new params/types do not exist.

- [ ] **Step 3: Update TypeScript types**

Modify `dashboard/src/api/types.ts` public-news types:

```typescript
export type PublicNewsStockMention = {
  asset_id: string;
  ts_code: string;
  stock_name: string;
  mention_role?: string;
  mention_confidence?: number | null;
  mapping_method?: string;
};

export type CountRow = {
  name: string;
  rows: number;
};

export type PublicNewsSummary = {
  total_news?: number;
  latest_published_at?: string;
  latest_collected_at?: string;
  source_count?: number;
  source_counts?: CountRow[];
  category_counts?: CountRow[];
};

export type PublicNewsItem = {
  id?: string;
  news_id: string;
  source: string;
  source_channel: string;
  category: string;
  title: string;
  summary: string;
  url: string;
  published_at: string;
  collected_at: string;
  raw_id: string;
  raw_payload: Record<string, unknown>;
  status: string;
  stocks?: PublicNewsStockMention[];
  metadata?: Record<string, unknown>;
};

export type PublicNewsResponse = {
  items: PublicNewsItem[];
  total?: number;
  limit?: number;
  offset?: number;
  summary?: PublicNewsSummary;
  warnings: string[];
};

export type AssetNewsSummary = {
  news_count_1d: number;
  news_count_3d: number;
  news_count_7d: number;
  latest_published_at?: string;
  source_count?: number;
  category_counts?: CountRow[];
};

export type AssetNewsResponse = {
  asset_id: string;
  items: PublicNewsItem[];
  summary: AssetNewsSummary;
  warnings: string[];
};
```

- [ ] **Step 4: Update API client**

Modify `dashboard/src/api/client.ts`.

Extend params:

```typescript
type PublicNewsParams = {
  source?: string;
  category?: string;
  q?: string;
  startTime?: string;
  endTime?: string;
  assetId?: string;
  tsCode?: string;
  limit?: number;
  offset?: number;
};
```

Update `fetchPublicNews`:

```typescript
export async function fetchPublicNews(params: PublicNewsParams = {}): Promise<PublicNewsResponse> {
  const searchParams = new URLSearchParams();
  if (params.source) searchParams.set('source', params.source);
  if (params.category) searchParams.set('category', params.category);
  if (params.q) searchParams.set('q', params.q);
  if (params.startTime) searchParams.set('start_time', params.startTime);
  if (params.endTime) searchParams.set('end_time', params.endTime);
  if (params.assetId) searchParams.set('asset_id', params.assetId);
  if (params.tsCode) searchParams.set('ts_code', params.tsCode);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
  return getJson(`/api/public-news?${searchParams.toString()}`);
}
```

Add:

```typescript
type AssetNewsParams = {
  limit?: number;
  lookbackDays?: number;
  category?: string;
  source?: string;
};

export async function fetchAssetNews(
  assetId: string,
  params: AssetNewsParams = {}
): Promise<AssetNewsResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params.lookbackDays !== undefined) searchParams.set('lookback_days', String(params.lookbackDays));
  if (params.category) searchParams.set('category', params.category);
  if (params.source) searchParams.set('source', params.source);
  return getJson(`/api/assets/${encodeURIComponent(assetId)}/news?${searchParams.toString()}`);
}
```

- [ ] **Step 5: Run client tests**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add dashboard news client APIs"
```

## Task 5: News Workspace DB Freshness And Stock Links

**Files:**
- Modify: `dashboard/src/components/NewsWorkspace.tsx`
- Modify: `dashboard/tests/news-workspace.test.tsx`
- Modify if needed: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Add failing News workspace tests**

Add tests in `dashboard/tests/news-workspace.test.tsx`:

```typescript
it('renders db freshness and stock mention chips', async () => {
  const openAsset = vi.fn();
  apiMocks.fetchPublicNews.mockResolvedValueOnce({
    items: [
      makeNewsItem({
        title: '贵州茅台经营快讯',
        category: 'company',
        stocks: [{ asset_id: 'CN:SH:600519', ts_code: '600519.SH', stock_name: '贵州茅台' }]
      })
    ],
    total: 1,
    limit: 200,
    offset: 0,
    summary: {
      total_news: 1,
      latest_collected_at: '2026-06-12T01:30:00+00:00',
      source_count: 1,
      source_counts: [{ name: 'sina_finance', rows: 1 }],
      category_counts: [{ name: 'company', rows: 1 }]
    },
    warnings: []
  });

  render(<NewsWorkspace onOpenAsset={openAsset} />);

  expect(await screen.findByText('贵州茅台经营快讯')).toBeInTheDocument();
  expect(screen.getByText(/DB collected/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Open 贵州茅台 in Stock Workspace' }));
  expect(openAsset).toHaveBeenCalledWith('CN:SH:600519');
});

it('shows fallback warnings without clearing rows', async () => {
  apiMocks.fetchPublicNews.mockResolvedValueOnce({
    items: [makeNewsItem({ title: '缓存新闻' })],
    summary: { total_news: 1, latest_collected_at: '2026-06-12T01:30:00+00:00' },
    warnings: ['fallback json cache used: db offline']
  });

  render(<NewsWorkspace />);

  expect(await screen.findByText('缓存新闻')).toBeInTheDocument();
  expect(screen.getByText('fallback json cache used: db offline')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx
```

Expected: FAIL because the component uses local time freshness and candidate parsing instead of API-provided stocks.

- [ ] **Step 3: Update News workspace state and load behavior**

Modify imports:

```typescript
import type { PublicNewsItem, PublicNewsSummary } from '../api/types';
```

Add state:

```typescript
const [summary, setSummary] = useState<PublicNewsSummary | null>(null);
```

When assigning payloads in `loadInitialNews` and `refreshNews`, set:

```typescript
setSummary(payload.summary ?? null);
setLastUpdatedAt(payload.summary?.latest_collected_at ?? new Date().toLocaleTimeString());
```

Remove use of `getNewsAssetCandidate` for row chips. Keep the helper exported only if existing tests still import it; do not use it as the primary DB-linked behavior.

- [ ] **Step 4: Render freshness, warnings, and stock chips**

In the header/status area, render:

```tsx
{summary?.latest_collected_at ? (
  <span className="muted">DB collected {summary.latest_collected_at}</span>
) : lastUpdatedAt ? (
  <span className="muted">Last updated {lastUpdatedAt}</span>
) : null}
{summary?.total_news !== undefined ? <span className="metric-chip">{summary.total_news} rows</span> : null}
```

For each row, render stock buttons:

```tsx
{(item.stocks ?? []).length > 0 ? (
  <div className="news-stock-row">
    {(item.stocks ?? []).map((stock) => (
      <button
        key={stock.asset_id || stock.ts_code}
        type="button"
        className="link-chip"
        aria-label={`Open ${stock.stock_name || stock.ts_code} in Stock Workspace`}
        onClick={() => onOpenAsset?.(stock.asset_id || stock.ts_code)}
      >
        {stock.stock_name || stock.ts_code}
      </button>
    ))}
  </div>
) : null}
```

Render warnings in the existing warning area. If no warning area exists, add:

```tsx
{warnings.length > 0 ? (
  <div className="warning-strip">
    {warnings.map((warning) => (
      <span key={warning}>{warning}</span>
    ))}
  </div>
) : null}
```

- [ ] **Step 5: Add minimal styles**

Modify `dashboard/src/styles.css` only for classes used above if they do not already exist:

```css
.news-stock-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.link-chip {
  border: 1px solid var(--border-subtle);
  background: var(--surface-muted);
  color: var(--text-primary);
  border-radius: 6px;
  padding: 3px 7px;
  font-size: 12px;
  line-height: 1.2;
}
```

- [ ] **Step 6: Run News workspace tests**

Run:

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add dashboard/src/components/NewsWorkspace.tsx dashboard/src/styles.css dashboard/tests/news-workspace.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: show db-backed news links in workspace"
```

## Task 6: Stock Workspace Asset News Integration

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Add failing Stock Workspace tests**

Update mocks in `dashboard/tests/stock-workspace.test.tsx`:

```typescript
vi.mock('../src/api/client', () => ({
  searchAssets: vi.fn(),
  fetchAssetProfile: vi.fn(),
  fetchAssetNews: vi.fn(),
  fetchAssetResearchReports: vi.fn()
}));
```

Add default mock:

```typescript
apiMocks.fetchAssetNews.mockResolvedValue({
  asset_id: 'CN:SH:600519',
  items: [
    {
      news_id: 'news-1',
      source: 'sina_finance',
      source_channel: '公司',
      category: 'company',
      title: '贵州茅台相关新闻',
      summary: '',
      url: 'https://finance.sina.com.cn/doc/news.shtml',
      published_at: '2026-06-12T01:30:00+00:00',
      collected_at: '2026-06-12T01:31:00+00:00',
      raw_id: 'news-1',
      raw_payload: {},
      status: 'available',
      stocks: [{ asset_id: 'CN:SH:600519', ts_code: '600519.SH', stock_name: '贵州茅台' }]
    }
  ],
  summary: {
    news_count_1d: 1,
    news_count_3d: 1,
    news_count_7d: 1,
    latest_published_at: '2026-06-12T01:30:00+00:00',
    source_count: 1,
    category_counts: [{ name: 'company', rows: 1 }]
  },
  warnings: []
});
```

Add test:

```typescript
it('loads db-linked asset news for the selected stock', async () => {
  render(<StockWorkspace />);

  await userEvent.type(screen.getByLabelText('stock search'), '贵州茅台');
  await userEvent.click(await screen.findByRole('button', { name: /贵州茅台/ }));

  expect(await screen.findByText('贵州茅台相关新闻')).toBeInTheDocument();
  expect(apiMocks.fetchAssetNews).toHaveBeenCalledWith('CN:SH:600519', { limit: 8, lookbackDays: 7 });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx
```

Expected: FAIL because `StockWorkspace` still calls `fetchPublicNews`.

- [ ] **Step 3: Update Stock Workspace API usage**

Modify imports in `dashboard/src/components/StockWorkspace.tsx`:

```typescript
import { fetchAssetNews, fetchAssetProfile, fetchAssetResearchReports, searchAssets } from '../api/client';
import type { AssetNewsResponse } from '../api/types';
```

Replace public-news state with:

```typescript
const [assetNews, setAssetNews] = useState<AssetNewsResponse | null>(null);
const [isNewsLoading, setIsNewsLoading] = useState(false);
const [newsError, setNewsError] = useState<string | null>(null);
const newsRequestIdRef = useRef(0);
```

When selected profile clears, reset news state and increment `newsRequestIdRef`.

Add effect:

```typescript
useEffect(() => {
  if (!profile?.canonical_asset_id) {
    newsRequestIdRef.current += 1;
    setAssetNews(null);
    setIsNewsLoading(false);
    setNewsError(null);
    return;
  }
  const requestId = newsRequestIdRef.current + 1;
  newsRequestIdRef.current = requestId;
  setIsNewsLoading(true);
  setNewsError(null);
  fetchAssetNews(profile.canonical_asset_id, { limit: 8, lookbackDays: 7 })
    .then((payload) => {
      if (mountedRef.current && requestId === newsRequestIdRef.current) {
        setAssetNews(payload);
      }
    })
    .catch((err: unknown) => {
      if (mountedRef.current && requestId === newsRequestIdRef.current) {
        setNewsError(err instanceof Error ? err.message : String(err));
        setAssetNews(null);
      }
    })
    .finally(() => {
      if (mountedRef.current && requestId === newsRequestIdRef.current) {
        setIsNewsLoading(false);
      }
    });
}, [profile?.canonical_asset_id]);
```

Use only `assetNews.items` for related news rows. Remove keyword filtering against all public news.

- [ ] **Step 4: Render asset-news summary and warnings**

In the related-news panel, render:

```tsx
{assetNews ? (
  <div className="metric-grid compact">
    <span>
      <span>1d News</span>
      <strong>{assetNews.summary.news_count_1d}</strong>
    </span>
    <span>
      <span>7d News</span>
      <strong>{assetNews.summary.news_count_7d}</strong>
    </span>
    <span>
      <span>Sources</span>
      <strong>{assetNews.summary.source_count ?? 0}</strong>
    </span>
  </div>
) : null}
{newsError ? <p className="error-text">{newsError}</p> : null}
{assetNews?.warnings?.length ? <p className="muted">{assetNews.warnings.join(' | ')}</p> : null}
```

For rows, keep existing title/link style but source from `assetNews.items`.

- [ ] **Step 5: Run Stock Workspace tests**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: connect stock workspace to asset news"
```

## Task 7: Focused Regression, Build, And Local Smoke

**Files:**
- Modify if needed: `dashboard/tests/app-smoke.spec.ts`
- Modify if needed: `dashboard/tests/platform-full-flow.spec.ts`
- Modify if needed: `dashboard/tests/strategy-validation-full-flow.spec.ts`

- [ ] **Step 1: Run focused backend regression**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_news.py tests/test_public_news_backend.py tests/test_dashboard_app.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend regression**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts tests/news-workspace.test.tsx tests/stock-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd dashboard && npm run build
```

Expected: PASS with Vite build output and no TypeScript errors.

- [ ] **Step 4: Run Playwright smoke**

If a dev server is already running, use its URL. Otherwise start one:

```bash
cd dashboard && npm run dev -- --host 127.0.0.1
```

In another shell, run:

```bash
cd dashboard && npm run test:e2e -- tests/app-smoke.spec.ts
```

Expected: PASS. News and Stock Workspace should remain reachable.

- [ ] **Step 5: Live API smoke on localhost**

Use the current local frontend/dev API port. Example if Vite is on `5176`:

```bash
curl -sS 'http://127.0.0.1:5176/api/public-news?limit=3' | jq '{count:(.items|length), total, warnings, latest:.summary.latest_collected_at}'
curl -sS 'http://127.0.0.1:5176/api/assets/CN:SH:600519/news?limit=3&lookback_days=30' | jq '{asset_id, count:(.items|length), warnings}'
```

Expected: Both commands return JSON. If the DB has no news rows yet, `/api/public-news` may show fallback warnings; that is acceptable only if rows still render or the warning is explicit.

- [ ] **Step 6: Commit verification fixes only if files changed**

If smoke-test mocks or small compatibility fixes were required:

```bash
git add dashboard/tests/app-smoke.spec.ts dashboard/tests/platform-full-flow.spec.ts dashboard/tests/strategy-validation-full-flow.spec.ts
git commit -m "test: update news workspace smoke fixtures"
```

If no files changed, do not create a commit.

## Final Verification

Run the final suite:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_news.py tests/test_public_news_backend.py tests/test_dashboard_app.py -v
cd dashboard && npm test -- --run tests/client.test.ts tests/news-workspace.test.tsx tests/stock-workspace.test.tsx tests/app-shell.test.tsx
cd dashboard && npm run build
cd dashboard && npm run test:e2e -- tests/app-smoke.spec.ts
```

Expected:

- Backend focused tests pass.
- Frontend focused tests pass.
- Vite build passes.
- Playwright smoke passes.

## Notes For Execution

- The worktree currently has unrelated dirty files. Do not revert or stage them.
- Only stage files listed in each task.
- Keep the existing JSON `PublicNewsService` tests passing; it remains the fallback implementation.
- Do not add sentiment analysis, websocket refresh, LLM summarization, or paid-source adapters in this phase.
- If real DB smoke shows no rows in `research.news_event_source`, trigger `/api/public-news/refresh` once and re-check. Do not make browser refresh call high-frequency.
