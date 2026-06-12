from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from stock_research.public_news.sina_adapter import fetch_sina_public_news
from stock_research.public_news.store import JsonPublicNewsStore


DEFAULT_PUBLIC_NEWS_CACHE = Path("outputs/dashboard/public_news_cache.json")


class PublicNewsService:
    def __init__(self, store: JsonPublicNewsStore | None = None) -> None:
        self.store = store or JsonPublicNewsStore(DEFAULT_PUBLIC_NEWS_CACHE)

    def refresh(self) -> dict[str, Any]:
        try:
            items, warnings = fetch_sina_public_news()
        except Exception as exc:
            items = []
            warnings = [f"sina_finance refresh failed: {exc}"]
        store_result = self.store.upsert_items(items) if items else {"received": 0, "stored": 0}
        counts_by_category = dict(Counter(item.category for item in items))
        return {
            **store_result,
            "items_received": len(items),
            "counts_by_category": counts_by_category,
            "warnings": warnings,
        }

    def list_items(
        self,
        *,
        source: str | None = None,
        category: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        items = self.store.query(
            source=source,
            category=category,
            q=q,
            limit=limit,
            offset=offset,
        )
        warnings = [] if items else ["no cached public news items"]
        return {
            "items": [item.to_dict() for item in items],
            "warnings": warnings,
        }


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
