from __future__ import annotations

from datetime import date
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
        self.asset_rows: list[dict[str, Any]] = []
        self.calls: list[tuple[str, list[Any]]] = []

    def fetch_all(self, _conn: FakeConn, sql: str, params: list[Any] | None = None):
        self.calls.append((sql, list(params or [])))
        compact = " ".join(sql.split())
        if compact.startswith("SELECT COUNT(*) AS total_news"):
            rows = list(self.source_rows.values())
            latest_published_at = max((row["published_at"] for row in rows), default=None)
            latest_collected_at = max((row["collected_at"] for row in rows), default=None)
            return [
                {
                    "total_news": len(rows),
                    "latest_published_at": latest_published_at,
                    "latest_collected_at": latest_collected_at,
                    "source_count": len({row["source_name"] for row in rows}),
                }
            ]
        if compact.startswith("SELECT COUNT(*) AS total"):
            return [{"total": len(self._filtered_source_rows(compact, params or []))}]
        if "FROM core.asset_master" in compact:
            return self.asset_rows
        if "FROM research.news_event_source s LEFT JOIN research.news_event_mention m" in compact:
            rows = self._filtered_source_rows(compact, params or [])
            rows = sorted(rows, key=lambda row: row["published_at"], reverse=True)
            if "LIMIT %s OFFSET %s" in compact:
                limit = int((params or [0, 0])[-2])
                offset = int((params or [0, 0])[-1])
                rows = rows[offset : offset + limit]
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
        if "GROUP BY source_name" in compact:
            counts: dict[str, int] = {}
            for row in self.source_rows.values():
                counts[row["source_name"]] = counts.get(row["source_name"], 0) + 1
            return [
                {"name": name, "rows": rows}
                for name, rows in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            ]
        if "GROUP BY name" in compact:
            counts: dict[str, int] = {}
            for row in self.source_rows.values():
                name = row["metadata"].get("category") or "other"
                counts[name] = counts.get(name, 0) + 1
            return [
                {"name": name, "rows": rows}
                for name, rows in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            ]
        raise AssertionError(f"unexpected query: {compact}")

    def _filtered_source_rows(self, compact_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        rows = list(self.source_rows.values())
        param_index = 0
        if "s.source_name = %s" in compact_sql:
            source_name = params[param_index]
            param_index += 1
            rows = [row for row in rows if row["source_name"] == source_name]
        if "metadata->>'category' = %s" in compact_sql:
            category = params[param_index]
            param_index += 1
            rows = [row for row in rows if row["metadata"].get("category") == category]
        if "s.published_at >= %s" in compact_sql:
            start_time = params[param_index]
            param_index += 1
            rows = [row for row in rows if row["published_at"] >= start_time]
        if "s.published_at <= %s" in compact_sql:
            end_time = params[param_index]
            param_index += 1
            rows = [row for row in rows if row["published_at"] <= end_time]
        if "m.asset_id = %s" in compact_sql:
            asset_id = params[param_index]
            param_index += 1
            rows = [
                row
                for row in rows
                if any(
                    mention["source_event_id"] == row["source_event_id"]
                    and mention["asset_id"] == asset_id
                    for mention in self.mention_rows
                )
            ]
        if "m.ts_code = %s" in compact_sql:
            ts_code = params[param_index]
            param_index += 1
            rows = [
                row
                for row in rows
                if any(
                    mention["source_event_id"] == row["source_event_id"]
                    and mention["ts_code"] == ts_code
                    for mention in self.mention_rows
                )
            ]
        return rows

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


class FixedDate:
    @classmethod
    def today(cls) -> date:
        return date(2026, 6, 12)

    @classmethod
    def fromisoformat(cls, value: str) -> date:
        return date.fromisoformat(value)


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


def test_news_event_store_falls_back_when_published_at_is_empty(
    monkeypatch: pytest.MonkeyPatch,
):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    store = news.NewsEventStore(service="test")

    store.upsert_public_items(
        [
            make_item(
                url="https://finance.sina.com.cn/doc/missing-time.shtml",
                published_at="",
                collected_at="2026-06-12T10:30:00+00:00",
                raw_id="raw-missing-time",
            )
        ]
    )

    stored = next(iter(fake.source_rows.values()))
    assert stored["published_at"] == "2026-06-12T10:30:00+00:00"


def test_news_event_store_falls_back_when_published_at_is_malformed(
    monkeypatch: pytest.MonkeyPatch,
):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    store = news.NewsEventStore(service="test")

    store.upsert_public_items(
        [
            make_item(
                url="https://finance.sina.com.cn/doc/malformed-time.shtml",
                published_at="not-a-real-time",
                collected_at="2026-06-12T10:45:00+00:00",
                raw_id="raw-malformed-time",
            )
        ]
    )

    stored = next(iter(fake.source_rows.values()))
    assert stored["published_at"] == "2026-06-12T10:45:00+00:00"
    assert stored["collected_at"] == "2026-06-12T10:45:00+00:00"


def test_news_event_store_normalizes_invalid_status(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    store = news.NewsEventStore(service="test")

    store.upsert_public_items([make_item(status="archived")])

    stored = next(iter(fake.source_rows.values()))
    assert stored["source_status"] == "available"


def test_news_event_store_lists_by_category_with_summary(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    store = news.NewsEventStore(service="test")
    store.upsert_public_items(
        [
            make_item(),
            make_item(
                category="announcement",
                title="宁德时代 300750 发布公告",
                url="https://finance.sina.com.cn/doc/announcement.shtml",
                raw_id="raw-2",
            ),
        ]
    )

    payload = store.list_news(category="live", limit=20)

    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["summary"]["total_news"] == 2
    assert payload["summary"]["latest_published_at"].startswith("2026-06-12")
    assert payload["summary"]["category_counts"] == [
        {"name": "announcement", "rows": 1},
        {"name": "live", "rows": 1},
    ]
    assert payload["items"][0]["category"] == "live"
    assert payload["items"][0]["stocks"] == []


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


def test_news_mention_mapper_uses_alphanumeric_boundaries_for_symbols(
    monkeypatch: pytest.MonkeyPatch,
):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute", fake.execute)
    monkeypatch.setattr(news, "execute_many", fake.execute_many)

    mapper = news.NewsMentionMapper(
        assets=[
            {"asset_id": "CN:SH:600519", "ts_code": "600519.SH", "name": "贵州茅台"},
        ],
        service="test",
    )
    embedded_item = make_item(
        title="abc600519def",
        summary="",
        url="https://finance.sina.com.cn/doc/embedded-symbol.shtml",
        raw_id="embedded-symbol",
    )
    adjacent_item = make_item(
        title="600519发布经营快讯",
        summary="",
        url="https://finance.sina.com.cn/doc/chinese-adjacent-symbol.shtml",
        raw_id="chinese-adjacent-symbol",
    )
    result = mapper.map_items([embedded_item, adjacent_item])

    assert result == {"mentions": 1}
    assert fake.mention_rows[0]["mapping_method"] == "symbol_exact"
    assert fake.mention_rows[0]["source_event_id"] == adjacent_item.news_id


def test_news_mention_mapper_dedupes_same_asset_with_code_and_name(
    monkeypatch: pytest.MonkeyPatch,
):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute", fake.execute)
    monkeypatch.setattr(news, "execute_many", fake.execute_many)

    mapper = news.NewsMentionMapper(
        assets=[
            {"asset_id": "CN:SH:600519", "ts_code": "600519.SH", "name": "贵州茅台"},
        ],
        service="test",
    )
    result = mapper.map_items(
        [
            make_item(
                title="贵州茅台 600519.SH 发布经营快讯",
                url="https://finance.sina.com.cn/doc/code-and-name.shtml",
                raw_id="code-and-name",
            )
        ]
    )

    assert result == {"mentions": 1}
    assert len(fake.mention_rows) == 1
    assert fake.mention_rows[0]["asset_id"] == "CN:SH:600519"


def test_news_mention_mapper_loads_assets_with_nullable_ts_code(
    monkeypatch: pytest.MonkeyPatch,
):
    from stock_research.dashboard import news

    fake = FakeDb()
    fake.asset_rows.append(
        {
            "asset_id": "CN:SH:600519",
            "symbol": "600519",
            "ts_code": None,
            "name": "贵州茅台",
        }
    )
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute", fake.execute)
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)

    mapper = news.NewsMentionMapper(service="test")
    result = mapper.map_items(
        [
            make_item(
                title="600519发布经营快讯",
                summary="",
                url="https://finance.sina.com.cn/doc/nullable-ts-code.shtml",
                raw_id="nullable-ts-code",
            )
        ]
    )

    assert result == {"mentions": 1}
    assert mapper.assets == [
        {
            "asset_id": "CN:SH:600519",
            "symbol": "600519",
            "ts_code": "600519",
            "name": "贵州茅台",
        }
    ]
    assert fake.mention_rows[0]["mapping_method"] == "symbol_exact"


def test_news_mention_mapper_deletes_stale_mentions_when_no_matches(
    monkeypatch: pytest.MonkeyPatch,
):
    from stock_research.dashboard import news

    fake = FakeDb()
    stale_item = make_item(
        title="宏观政策更新",
        summary="行业观察",
        url="https://finance.sina.com.cn/doc/macro.shtml",
    )
    fake.mention_rows.append(
        {
            "source_event_id": stale_item.news_id,
            "asset_id": "CN:SH:600519",
            "ts_code": "600519.SH",
            "stock_name": "贵州茅台",
            "mention_role": "subject",
            "mention_confidence": 1.0,
            "mapping_method": "stock_name_exact",
        }
    )
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute", fake.execute)
    monkeypatch.setattr(news, "execute_many", fake.execute_many)

    mapper = news.NewsMentionMapper(
        assets=[
            {"asset_id": "CN:SH:600519", "ts_code": "600519.SH", "name": "贵州茅台"},
        ],
        service="test",
    )
    result = mapper.map_items([stale_item])

    assert result == {"mentions": 0}
    assert fake.mention_rows == []


def test_load_asset_news_returns_mention_linked_items(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "date", FixedDate)
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute", fake.execute)
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    store = news.NewsEventStore(service="test")
    items = [
        make_item(category="company", raw_id="today", url="https://finance.sina.com.cn/doc/today.shtml"),
        make_item(
            category="company",
            published_at="2026-06-10 09:30:00",
            raw_id="three-day",
            url="https://finance.sina.com.cn/doc/three-day.shtml",
        ),
        make_item(
            category="company",
            published_at="2026-06-08 09:30:00",
            raw_id="seven-day",
            url="https://finance.sina.com.cn/doc/seven-day.shtml",
        ),
    ]
    store.upsert_public_items(items)
    for item in items:
        fake.mention_rows.append(
            {
                "source_event_id": item.news_id,
                "asset_id": "CN:SH:600519",
                "ts_code": "600519.SH",
                "stock_name": "贵州茅台",
                "mention_role": "subject",
                "mention_confidence": 1.0,
                "mapping_method": "stock_name_exact",
            }
        )

    payload = news.load_asset_news("CN:SH:600519", limit=1, service="test")

    assert payload["asset_id"] == "CN:SH:600519"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["stocks"][0]["stock_name"] == "贵州茅台"
    assert payload["summary"]["news_count_1d"] == 1
    assert payload["summary"]["news_count_3d"] == 2
    assert payload["summary"]["news_count_7d"] == 3
    assert payload["summary"]["source_count"] == 1


def test_load_asset_news_skips_malformed_published_at_for_bucket_counts(
    monkeypatch: pytest.MonkeyPatch,
):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "date", FixedDate)
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    fake.source_rows["bad-time"] = {
        "source_event_id": "bad-time",
        "source_name": "sina_finance",
        "source_channel": "公司",
        "title": "贵州茅台披露经营数据",
        "content": "贵州茅台营收保持增长",
        "published_at": "not-a-real-time",
        "collected_at": "2026-06-12 09:31:00",
        "url": "https://finance.sina.com.cn/doc/bad-time.shtml",
        "source_status": "available",
        "metadata": {"category": "company"},
    }
    fake.mention_rows.append(
        {
            "source_event_id": "bad-time",
            "asset_id": "CN:SH:600519",
            "ts_code": "600519.SH",
            "stock_name": "贵州茅台",
            "mention_role": "subject",
            "mention_confidence": 1.0,
            "mapping_method": "stock_name_exact",
        }
    )

    payload = news.load_asset_news("CN:SH:600519", limit=5, service="test")

    assert len(payload["items"]) == 1
    assert payload["summary"]["news_count_1d"] == 0
    assert payload["summary"]["news_count_3d"] == 0
    assert payload["summary"]["news_count_7d"] == 0
