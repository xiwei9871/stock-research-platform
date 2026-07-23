from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import threading
from typing import Any

import pytest

from stock_research.public_news.models import PublicNewsItem


def fresh_china_timestamp() -> str:
    return (datetime.now(UTC) + timedelta(hours=8)).replace(
        tzinfo=None,
        microsecond=0,
    ).isoformat(sep=" ")


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
            if "metadata->'quality'->>'score'" in compact:
                rows = sorted(
                    rows,
                    key=lambda row: (
                        self._quality_score(row),
                        row["published_at"],
                        row["collected_at"],
                        row["source_event_id"],
                    ),
                    reverse=True,
                )
            else:
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
        if "CASE WHEN s.metadata->'quality'->>'score' ~" in compact_sql and "END >= %s" in compact_sql:
            min_quality_score = params[param_index]
            param_index += 1
            rows = [
                row for row in rows if self._quality_score(row) >= float(min_quality_score or 0)
            ]
        return rows

    def _quality_score(self, row: dict[str, Any]) -> float:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        quality = metadata.get("quality") if isinstance(metadata.get("quality"), dict) else {}
        try:
            return float(quality.get("score") or 0)
        except (TypeError, ValueError):
            return 0.0

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
    news_id = values.pop("news_id", None)
    item = PublicNewsItem.from_raw(**values)
    if news_id is not None:
        return replace(item, news_id=str(news_id))
    return item


class FixedDate:
    @classmethod
    def today(cls) -> date:
        return date(2026, 6, 12)

    @classmethod
    def fromisoformat(cls, value: str) -> date:
        return date.fromisoformat(value)


def test_public_news_scheduler_runs_once_and_records_status():
    from stock_research.dashboard.news_scheduler import PublicNewsScheduler

    calls = 0

    async def refresh():
        nonlocal calls
        calls += 1
        return {"stored": 1}

    async def run_test():
        scheduler = PublicNewsScheduler(refresh, interval_seconds=60)
        await scheduler.run_once()

        status = scheduler.status()
        assert calls == 1
        assert status["enabled"] is True
        assert status["running"] is False
        assert status["interval_seconds"] == 60
        assert status["last_success_at"]
        assert status["last_error"] == ""
        assert status["next_run_at"]
        assert datetime.fromisoformat(status["next_run_at"]) > datetime.fromisoformat(
            status["last_success_at"]
        )

    asyncio.run(run_test())


def test_public_news_scheduler_lock_prevents_overlap():
    from stock_research.dashboard.news_scheduler import PublicNewsScheduler

    calls = 0
    release = asyncio.Event()
    started = asyncio.Event()

    async def refresh():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"stored": 1}

    async def run_test():
        scheduler = PublicNewsScheduler(refresh, interval_seconds=60)
        first = asyncio.create_task(scheduler.run_once())
        await started.wait()
        await scheduler.run_once()
        release.set()
        await first

        assert calls == 1
        assert scheduler.status()["running"] is False

    asyncio.run(run_test())


def test_public_news_scheduler_failure_records_error_without_raising():
    from stock_research.dashboard.news_scheduler import PublicNewsScheduler

    async def refresh():
        raise RuntimeError("quality refresh failed")

    async def run_test():
        scheduler = PublicNewsScheduler(refresh, interval_seconds=60)
        await scheduler.run_once()

        status = scheduler.status()
        assert status["last_success_at"] == ""
        assert status["last_error"] == "quality refresh failed"
        assert status["next_run_at"]
        assert status["running"] is False

    asyncio.run(run_test())


def test_public_news_scheduler_stop_cleans_up_during_active_refresh():
    from stock_research.dashboard.news_scheduler import PublicNewsScheduler

    started = asyncio.Event()

    async def refresh():
        started.set()
        await asyncio.sleep(60)
        return {"stored": 1}

    async def run_test():
        scheduler = PublicNewsScheduler(refresh, interval_seconds=60)
        scheduler.start()
        await started.wait()

        await scheduler.stop()

        status = scheduler.status()
        assert status["running"] is False
        assert status["next_run_at"] == ""
        assert status["last_error"] == ""

    asyncio.run(run_test())


def test_public_news_scheduler_runs_sync_refresh_in_worker_thread():
    from stock_research.dashboard.news_scheduler import PublicNewsScheduler

    calls = 0
    started = threading.Event()
    release = threading.Event()

    def refresh():
        nonlocal calls
        calls += 1
        started.set()
        release.wait(timeout=5)
        return {"stored": 1}

    async def run_test():
        scheduler = PublicNewsScheduler(refresh, interval_seconds=60)
        first = asyncio.create_task(scheduler.run_once())
        await asyncio.to_thread(started.wait, 5)

        second = asyncio.create_task(scheduler.run_once())
        await asyncio.sleep(0)
        assert calls == 1

        release.set()
        await first
        await second
        assert calls == 1
        assert scheduler.status()["running"] is False

    asyncio.run(run_test())


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


def test_news_event_store_filters_and_orders_by_quality(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    fake.source_rows = {
        "low": {
            "source_event_id": "low",
            "source_name": "sina_finance",
            "source_channel": "sina_live",
            "title": "普通观点",
            "content": "",
            "published_at": "2026-06-13T05:00:00+00:00",
            "collected_at": "2026-06-13T05:00:10+00:00",
            "url": "https://finance.sina.com.cn/low.shtml",
            "source_status": "available",
            "metadata": {"category": "other", "quality": {"score": 45, "reasons": ["other"]}},
        },
        "high": {
            "source_event_id": "high",
            "source_name": "sina_finance",
            "source_channel": "sina_live",
            "title": "政策推动半导体产业链订单增长",
            "content": "",
            "published_at": "2026-06-13T04:00:00+00:00",
            "collected_at": "2026-06-13T04:00:10+00:00",
            "url": "https://finance.sina.com.cn/high.shtml",
            "source_status": "available",
            "metadata": {
                "category": "market",
                "quality": {
                    "score": 88,
                    "reasons": ["policy", "sector_specific"],
                    "run_id": "public-news-20260613T040000Z",
                },
            },
        },
    }

    payload = news.NewsEventStore(service="test").list_news(
        source="sina_finance",
        min_quality_score=70,
        limit=3,
    )

    assert [item["news_id"] for item in payload["items"]] == ["high"]
    assert payload["items"][0]["quality_score"] == 88
    assert payload["items"][0]["quality_reasons"] == ["policy", "sector_specific"]
    assert payload["items"][0]["quality_run_id"] == "public-news-20260613T040000Z"


def test_news_event_store_orders_by_quality_before_recency(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    fake.source_rows = {
        "newer-low": {
            "source_event_id": "newer-low",
            "source_name": "sina_finance",
            "source_channel": "sina_live",
            "title": "普通观点",
            "content": "",
            "published_at": "2026-06-13T05:00:00+00:00",
            "collected_at": "2026-06-13T05:00:10+00:00",
            "url": "https://finance.sina.com.cn/newer-low.shtml",
            "source_status": "available",
            "metadata": {"category": "other", "quality": {"score": "45"}},
        },
        "older-high": {
            "source_event_id": "older-high",
            "source_name": "sina_finance",
            "source_channel": "sina_live",
            "title": "政策推动半导体产业链订单增长",
            "content": "",
            "published_at": "2026-06-13T04:00:00+00:00",
            "collected_at": "2026-06-13T04:00:10+00:00",
            "url": "https://finance.sina.com.cn/older-high.shtml",
            "source_status": "available",
            "metadata": {"category": "market", "quality": {"score": "88.5", "reasons": "policy"}},
        },
        "bad-score": {
            "source_event_id": "bad-score",
            "source_name": "sina_finance",
            "source_channel": "sina_live",
            "title": "历史脏数据",
            "content": "",
            "published_at": "2026-06-13T06:00:00+00:00",
            "collected_at": "2026-06-13T06:00:10+00:00",
            "url": "https://finance.sina.com.cn/bad-score.shtml",
            "source_status": "available",
            "metadata": {"category": "other", "quality": {"score": "not-a-number"}},
        },
    }

    payload = news.NewsEventStore(service="test").list_news(source="sina_finance", limit=3)

    assert [item["news_id"] for item in payload["items"]] == [
        "older-high",
        "newer-low",
        "bad-score",
    ]
    assert payload["items"][0]["quality_score"] == 88
    assert payload["items"][0]["quality_reasons"] == []
    assert payload["items"][0]["quality_run_id"] == ""
    quality_sql = next(
        " ".join(sql.split())
        for sql, _params in fake.calls
        if "FROM research.news_event_source s LEFT JOIN research.news_event_mention m"
        in " ".join(sql.split())
    )
    assert "CASE WHEN s.metadata->'quality'->>'score' ~" in quality_sql
    assert "COALESCE((s.metadata->'quality'->>'score')::numeric, 0)" not in quality_sql


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
            raw_payload={"quality": {"score": 95}},
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
    assert payload["summary"]["latest_published_at"].startswith("2026-06-12")
    assert payload["summary"]["source_count"] == 1


def test_load_asset_news_summary_pages_beyond_batch_size(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "MAX_LIMIT", 2)
    monkeypatch.setattr(news, "date", FixedDate)
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    store = news.NewsEventStore(service="test")
    items = [
        make_item(category="company", raw_id="batch-1", url="https://finance.sina.com.cn/doc/batch-1.shtml"),
        make_item(category="company", raw_id="batch-2", url="https://finance.sina.com.cn/doc/batch-2.shtml"),
        make_item(category="company", raw_id="batch-3", url="https://finance.sina.com.cn/doc/batch-3.shtml"),
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

    assert len(payload["items"]) == 1
    assert payload["summary"]["news_count_1d"] == 3
    assert payload["summary"]["news_count_7d"] == 3


def test_load_asset_news_uses_inclusive_lookback_window(monkeypatch: pytest.MonkeyPatch):
    from stock_research.dashboard import news

    fake = FakeDb()
    monkeypatch.setattr(news, "date", FixedDate)
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    store = news.NewsEventStore(service="test")
    items = [
        make_item(
            category="company",
            published_at="2026-06-06 09:30:00",
            raw_id="lookback-included",
            url="https://finance.sina.com.cn/doc/lookback-included.shtml",
        ),
        make_item(
            category="company",
            published_at="2026-06-05 09:30:00",
            raw_id="lookback-excluded",
            url="https://finance.sina.com.cn/doc/lookback-excluded.shtml",
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

    payload = news.load_asset_news("CN:SH:600519", lookback_days=7, limit=10, service="test")

    assert [item["raw_id"] for item in payload["items"]] == ["lookback-included"]
    assert payload["summary"]["news_count_7d"] == 1


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


def test_news_quality_gate_accepts_only_top_three_market_relevant_items():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    items = [
        make_item(
            news_id=f"policy-{idx}",
            title=f"国家发改委出台半导体产业链支持政策 第{idx}批",
            summary="政策支持、产业链、订单、涨价预期均明确",
            category="market",
            published_at=f"2026-06-13T0{idx}:00:00+00:00",
            url=f"https://finance.sina.com.cn/policy-{idx}.shtml",
        )
        for idx in range(1, 6)
    ]

    result = evaluate_public_news_items(
        items,
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
    )

    assert len(result.accepted_items) == 3
    assert result.rejection_counts["overflow"] == 2
    assert all(item.raw_payload["quality"]["score"] >= 65 for item in result.accepted_items)
    assert result.accepted_items[0].news_id == "policy-5"
    assert "policy" in result.accepted_items[0].raw_payload["quality"]["reasons"]


def test_news_quality_gate_rejects_low_signal_and_does_not_fill_three_slots():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    items = [
        make_item(
            news_id="good-1",
            title="央行开展逆回购操作 资金面流动性维持合理充裕",
            summary="市场流动性、利率、资金价格具备交易参考价值",
            category="macro",
            published_at="2026-06-13T05:00:00+00:00",
            url="https://finance.sina.com.cn/good-1.shtml",
        ),
        make_item(
            news_id="bad-1",
            title="更多精彩内容请关注新浪财经",
            summary="",
            category="other",
            published_at="2026-06-13T05:01:00+00:00",
            url="https://finance.sina.com.cn/bad-1.shtml",
        ),
        make_item(
            news_id="bad-2",
            title="今日财经早餐来了",
            summary="",
            category="other",
            published_at="2026-06-13T05:02:00+00:00",
            url="https://finance.sina.com.cn/bad-2.shtml",
        ),
    ]

    result = evaluate_public_news_items(
        items,
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
    )

    assert [item.news_id for item in result.accepted_items] == ["good-1"]
    assert result.rejection_counts["low_signal"] >= 1
    assert result.rejection_counts["not_a_share_relevant"] >= 1


def test_news_quality_gate_rejects_missing_title_and_url():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    result = evaluate_public_news_items(
        [
            make_item(
                news_id="missing-title",
                title="",
                url="https://finance.sina.com.cn/missing-title.shtml",
            ),
            make_item(
                news_id="missing-url",
                title="央行开展逆回购操作 资金面流动性维持合理充裕",
                url="",
            ),
        ],
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
    )

    assert result.accepted_items == []
    assert result.rejection_counts["missing_title"] == 1
    assert result.rejection_counts["missing_url"] == 1


def test_news_quality_gate_rejects_duplicate_url_or_title_after_first_acceptance():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    result = evaluate_public_news_items(
        [
            make_item(
                news_id="first",
                title="国家发改委出台半导体产业链支持政策",
                summary="政策支持、产业链、订单、涨价预期均明确",
                category="market",
                published_at="2026-06-13T05:00:00+00:00",
                url="https://finance.sina.com.cn/duplicate.shtml",
            ),
            make_item(
                news_id="duplicate-url",
                title="央行开展逆回购操作 资金面流动性维持合理充裕",
                summary="市场流动性、利率、资金价格具备交易参考价值",
                category="macro",
                published_at="2026-06-13T05:05:00+00:00",
                url="https://finance.sina.com.cn/duplicate.shtml",
            ),
            make_item(
                news_id="duplicate-title",
                title="国家发改委出台半导体产业链支持政策",
                summary="政策支持、产业链、订单、涨价预期均明确",
                category="market",
                published_at="2026-06-13T05:10:00+00:00",
                url="https://finance.sina.com.cn/duplicate-title.shtml",
            ),
        ],
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
    )

    assert [item.news_id for item in result.accepted_items] == ["first"]
    assert result.rejection_counts["duplicate"] == 2


def test_news_quality_gate_treats_naive_public_news_timestamp_as_china_local_time():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    result = evaluate_public_news_items(
        [
            make_item(
                news_id="stale-china-local",
                title="国家发改委出台半导体产业链支持政策",
                summary="政策支持、产业链、订单、涨价预期均明确",
                category="market",
                published_at="2026-06-12 07:00:00",
                url="https://finance.sina.com.cn/stale-china-local.shtml",
            )
        ],
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
    )

    assert result.accepted_items == []
    assert result.rejection_counts["stale"] == 1


def test_news_quality_gate_adds_metadata_without_mutating_original_payload():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    original_payload = {"href": "/policy.shtml"}
    item = make_item(
        news_id="metadata",
        title="国家发改委出台半导体产业链支持政策",
        summary="政策支持、产业链、订单、涨价预期均明确",
        category="market",
        published_at="2026-06-13T05:00:00+00:00",
        url="https://finance.sina.com.cn/metadata.shtml",
        raw_payload=original_payload,
    )

    result = evaluate_public_news_items(
        [item],
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
    )

    assert "quality" not in item.raw_payload
    assert item.raw_payload == original_payload
    accepted_item = result.accepted_items[0]
    assert accepted_item is not item
    quality = accepted_item.raw_payload["quality"]
    assert quality["run_id"] == "public-news-20260613T060000Z"
    assert quality["accepted_at"] == "2026-06-13T06:00:00+00:00"
    assert quality["score"] >= 65
    assert "policy" in quality["reasons"]
    assert "quality" not in original_payload


def test_news_quality_gate_clamps_custom_threshold_and_max_accepted():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    items = [
        make_item(
            news_id="low-score",
            title="今日财经早餐",
            summary="市场消息",
            category="other",
            published_at="2026-06-13T05:00:00+00:00",
            url="https://finance.sina.com.cn/low-score.shtml",
        )
    ]

    zero_slots = evaluate_public_news_items(
        items,
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
        threshold=-10,
        max_accepted=-1,
    )
    high_threshold = evaluate_public_news_items(
        items,
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
        threshold=120,
    )

    assert zero_slots.threshold == 0
    assert zero_slots.max_accepted == 0
    assert zero_slots.accepted_items == []
    assert zero_slots.rejection_counts["not_a_share_relevant"] == 1
    assert high_threshold.threshold == 100
    assert high_threshold.rejection_counts["not_a_share_relevant"] == 1


def test_news_quality_gate_default_threshold_is_65():
    from stock_research.dashboard.news_quality import NEWS_QUALITY_THRESHOLD, evaluate_public_news_items

    result = evaluate_public_news_items([])

    assert NEWS_QUALITY_THRESHOLD == 65
    assert result.threshold == 65


def test_news_quality_gate_rejects_overseas_or_generic_futures_without_a_share_relevance():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    result = evaluate_public_news_items(
        [
            make_item(
                news_id="us-stocks",
                title="美股成交额前20：英特尔与苹果洽谈合作",
                summary="纳斯达克、标普指数走强，科技股大涨",
                category="international",
                published_at="2026-06-13T05:00:00+00:00",
                url="https://finance.sina.com.cn/us-stocks.shtml",
            ),
            make_item(
                news_id="generic-futures",
                title="期货公司管理层调整",
                summary="行业机构发布人事变动公告",
                category="market",
                published_at="2026-06-13T05:01:00+00:00",
                url="https://finance.sina.com.cn/generic-futures.shtml",
            ),
            make_item(
                news_id="china-sector",
                title="国家发改委出台半导体产业链支持政策",
                summary="A股半导体、芯片、算力方向订单和涨价预期明确",
                category="market",
                published_at="2026-06-13T05:02:00+00:00",
                url="https://finance.sina.com.cn/china-sector.shtml",
            ),
        ],
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
    )

    assert [item.news_id for item in result.accepted_items] == ["china-sector"]
    assert result.rejection_counts["not_a_share_relevant"] == 2


def test_public_news_ingestion_writes_db_and_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute", fake.execute)
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    item = make_item(
        title="央行逆回购维护流动性 半导体板块受益",
        category="macro",
        published_at=fresh_china_timestamp(),
    )
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
    assert "quality" in fake.source_rows[item.news_id]["metadata"]


def test_public_news_refresh_persists_only_quality_gate_accepted_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    fresh_published_at = fresh_china_timestamp()
    received = [
        make_item(
            news_id="strong-1",
            title="央行逆回购维护流动性 半导体板块受益",
            category="macro",
            url="https://finance.sina.com.cn/strong-1.shtml",
            published_at=fresh_published_at,
        ),
        make_item(
            news_id="strong-2",
            title="国家政策支持机器人产业链订单增长",
            category="market",
            url="https://finance.sina.com.cn/strong-2.shtml",
            published_at=fresh_published_at,
        ),
        make_item(
            news_id="strong-3",
            title="有色金属期货大涨 供给减产预期升温",
            category="market",
            url="https://finance.sina.com.cn/strong-3.shtml",
            published_at=fresh_published_at,
        ),
        make_item(
            news_id="weak-1",
            title="更多精彩内容请关注新浪财经",
            summary="",
            category="other",
            url="https://finance.sina.com.cn/weak-1.shtml",
            published_at=fresh_published_at,
        ),
    ]

    class RecordingStore(news.NewsEventStore):
        def __init__(self):
            self.saved: list[PublicNewsItem] = []

        def upsert_public_items(self, items):
            self.saved = list(items)
            return {"received": len(self.saved), "stored": len(self.saved)}

    store = RecordingStore()
    service = news.PublicNewsIngestionService(
        fetcher=lambda: received,
        store=store,
        fallback_store=JsonPublicNewsStore(tmp_path / "public_news.json"),
        mention_mapper=None,
    )

    payload = service.refresh()

    assert payload["items_received"] == 4
    assert payload["accepted"] == 3
    assert payload["stored"] == 3
    assert payload["rejected"] == 1
    assert payload["received"] == 4
    assert [item.news_id for item in store.saved] == ["strong-1", "strong-2", "strong-3"]
    assert all("quality" in item.raw_payload for item in store.saved)


def test_public_news_refresh_handles_empty_fetch_without_writes(tmp_path: Path):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    class RecordingStore(news.NewsEventStore):
        def __init__(self):
            self.called = False

        def upsert_public_items(self, _items):
            self.called = True
            raise AssertionError("empty refresh should not write db rows")

    store = RecordingStore()
    service = news.PublicNewsIngestionService(
        fetcher=lambda: ([], ["source empty"]),
        store=store,
        fallback_store=JsonPublicNewsStore(tmp_path / "public_news.json"),
        mention_mapper=None,
    )

    payload = service.refresh()

    assert payload["received"] == 0
    assert payload["items_received"] == 0
    assert payload["accepted"] == 0
    assert payload["stored"] == 0
    assert payload["fallback_cache_stored"] == 0
    assert payload["rejected"] == 0
    assert payload["rejection_counts"] == {}
    assert payload["warnings"] == ["source empty"]
    assert store.called is False


def test_public_news_refresh_rejects_all_without_persisting(tmp_path: Path):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    rejected = [
        make_item(
            news_id="weak-1",
            title="更多精彩内容请关注新浪财经",
            summary="",
            category="other",
            url="https://finance.sina.com.cn/weak-1.shtml",
            published_at=fresh_china_timestamp(),
        ),
        make_item(
            news_id="weak-2",
            title="",
            summary="",
            category="other",
            url="https://finance.sina.com.cn/weak-2.shtml",
            published_at=fresh_china_timestamp(),
        ),
    ]

    class RecordingStore(news.NewsEventStore):
        def __init__(self):
            self.saved: list[PublicNewsItem] = []

        def upsert_public_items(self, items):
            self.saved = list(items)
            return {"received": len(self.saved), "stored": len(self.saved)}

    store = RecordingStore()
    fallback = JsonPublicNewsStore(tmp_path / "public_news.json")
    service = news.PublicNewsIngestionService(
        fetcher=lambda: rejected,
        store=store,
        fallback_store=fallback,
        mention_mapper=None,
    )

    payload = service.refresh()

    assert payload["received"] == 2
    assert payload["items_received"] == 2
    assert payload["accepted"] == 0
    assert payload["stored"] == 0
    assert payload["fallback_cache_stored"] == 0
    assert payload["rejected"] == 2
    assert payload["rejection_counts"]["low_signal"] == 1
    assert payload["rejection_counts"]["missing_title"] == 1
    assert store.saved == []
    assert fallback.load_all() == []


def test_load_public_news_falls_back_to_json_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
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


def test_load_public_news_does_not_fallback_when_filtered_db_query_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)
    store = news.NewsEventStore(service="test")
    store.upsert_public_items([make_item(category="live")])

    fallback = JsonPublicNewsStore(tmp_path / "public_news.json")
    fallback.upsert_items([make_item(category="announcement", title="陈旧缓存公告")])

    payload = news.load_public_news_for_dashboard(
        category="announcement",
        limit=5,
        store=store,
        fallback_store=fallback,
    )

    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["warnings"] == ["no matching public news items"]


def test_load_public_news_uses_json_fallback_for_filtered_empty_db(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)

    fallback = JsonPublicNewsStore(tmp_path / "public_news.json")
    fallback.upsert_items([make_item(source="sina_finance", title="缓存新浪新闻")])

    payload = news.load_public_news_for_dashboard(
        source="sina_finance",
        limit=5,
        store=news.NewsEventStore(service="test"),
        fallback_store=fallback,
    )

    assert payload["items"][0]["title"] == "缓存新浪新闻"
    assert payload["total"] == 1
    assert "fallback json cache used: no db public news items" in payload["warnings"]


def test_load_public_news_json_fallback_respects_quality_filter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    fake = FakeDb()
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "fetch_all", fake.fetch_all)

    fallback = JsonPublicNewsStore(tmp_path / "public_news.json")
    fallback.upsert_items(
        [
            make_item(
                news_id="fallback-low",
                title="低质量缓存新闻",
                raw_payload={"quality": {"score": 45, "reasons": ["other"]}},
            ),
            make_item(
                news_id="fallback-high",
                title="政策推动半导体产业链订单增长",
                raw_payload={
                    "quality": {
                        "score": "88.5",
                        "reasons": ["policy", "sector_specific"],
                        "run_id": "public-news-20260613T040000Z",
                    }
                },
            ),
        ]
    )

    payload = news.load_public_news_for_dashboard(
        source="sina_finance",
        min_quality_score=70,
        limit=5,
        store=news.NewsEventStore(service="test"),
        fallback_store=fallback,
    )

    assert [item["news_id"] for item in payload["items"]] == ["fallback-high"]
    assert payload["items"][0]["quality_score"] == 88
    assert payload["items"][0]["quality_reasons"] == ["policy", "sector_specific"]
    assert payload["items"][0]["quality_run_id"] == "public-news-20260613T040000Z"
    assert payload["total"] == 1
    assert "fallback json cache used: no db public news items" in payload["warnings"]


def test_load_public_news_does_not_use_json_fallback_for_asset_db_failure(
    tmp_path: Path,
):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    fallback = JsonPublicNewsStore(tmp_path / "public_news.json")
    fallback.upsert_items([make_item(title="不应返回的通用缓存")])

    class FailingStore(news.NewsEventStore):
        def list_news(self, **_kwargs):
            raise RuntimeError("db offline")

    payload = news.load_public_news_for_dashboard(
        asset_id="CN:SH:600519",
        limit=5,
        store=FailingStore(service="test"),
        fallback_store=fallback,
    )

    assert payload["items"] == []
    assert payload["total"] == 0
    assert any("db offline" in warning for warning in payload["warnings"])
    assert all("fallback json cache used" not in warning for warning in payload["warnings"])


def test_public_news_ingestion_keeps_successful_counts_when_later_stages_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    class FailingFallbackStore(JsonPublicNewsStore):
        def upsert_items(self, _items):
            raise RuntimeError("cache write failed")

    class FailingMentionMapper(news.NewsMentionMapper):
        def __init__(self):
            pass

        def map_items(self, _items):
            raise RuntimeError("mention mapping failed")

    fake = FakeDb()
    item = make_item(
        title="央行逆回购维护流动性 半导体板块受益",
        category="macro",
        published_at=fresh_china_timestamp(),
    )
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_sina_public_news", lambda: ([item], []))

    service = news.PublicNewsIngestionService(
        store=news.NewsEventStore(service="test"),
        fallback_store=FailingFallbackStore(tmp_path / "public_news.json"),
        mention_mapper=FailingMentionMapper(),
    )
    result = service.refresh()

    assert result["received"] == 1
    assert result["items_received"] == 1
    assert result["accepted"] == 1
    assert result["stored"] == 1
    assert result["fallback_cache_stored"] == 0
    assert result["mentions"] == 0
    assert "fallback cache write failed: cache write failed" in result["warnings"]
    assert "mention mapping failed: mention mapping failed" in result["warnings"]


def test_public_news_ingestion_skips_mentions_when_db_upsert_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    class FailingStore(news.NewsEventStore):
        def upsert_public_items(self, _items):
            raise RuntimeError("db write failed")

    class TrackingMentionMapper(news.NewsMentionMapper):
        def __init__(self):
            self.called = False

        def map_items(self, _items):
            self.called = True
            raise AssertionError("mention mapper should not run after db upsert failure")

    item = make_item(
        title="央行逆回购维护流动性 半导体板块受益",
        category="macro",
        published_at=fresh_china_timestamp(),
    )
    mapper = TrackingMentionMapper()
    monkeypatch.setattr(news, "fetch_sina_public_news", lambda: ([item], []))

    service = news.PublicNewsIngestionService(
        store=FailingStore(service="test"),
        fallback_store=JsonPublicNewsStore(tmp_path / "public_news.json"),
        mention_mapper=mapper,
    )
    result = service.refresh()

    assert result["stored"] == 0
    assert result["fallback_cache_stored"] == 1
    assert result["mentions"] == 0
    assert mapper.called is False
    assert "db upsert failed: db write failed" in result["warnings"]
    assert all("mention mapping failed" not in warning for warning in result["warnings"])


def test_public_news_ingestion_handles_default_mapper_construction_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from stock_research.dashboard import news
    from stock_research.public_news.store import JsonPublicNewsStore

    fake = FakeDb()
    item = make_item(
        title="央行逆回购维护流动性 半导体板块受益",
        category="macro",
        published_at=fresh_china_timestamp(),
    )
    monkeypatch.setattr(news, "connect", lambda _service: FakeConn())
    monkeypatch.setattr(news, "execute_many", fake.execute_many)
    monkeypatch.setattr(news, "fetch_sina_public_news", lambda: ([item], []))
    monkeypatch.setattr(
        news,
        "_asset_rows_from_db",
        lambda _service: (_ for _ in ()).throw(RuntimeError("asset db offline")),
    )

    service = news.PublicNewsIngestionService(
        store=news.NewsEventStore(service="test"),
        fallback_store=JsonPublicNewsStore(tmp_path / "public_news.json"),
    )
    result = service.refresh()

    assert result["items_received"] == 1
    assert result["stored"] == 1
    assert result["fallback_cache_stored"] == 1
    assert result["mentions"] == 0
    assert "mention mapping failed: asset db offline" in result["warnings"]
