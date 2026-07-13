from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from stock_research.public_news.models import PublicNewsItem


class JsonPublicNewsStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def upsert_items(self, items: Iterable[PublicNewsItem]) -> dict[str, int]:
        existing = {item.news_id: item for item in self.load_all()}
        incoming = list(items)
        for item in incoming:
            existing[item.news_id] = item
        ordered = sorted(existing.values(), key=lambda item: item.published_at, reverse=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([item.to_dict() for item in ordered], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"received": len(incoming), "stored": len(existing)}

    def load_all(self) -> list[PublicNewsItem]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return [PublicNewsItem.from_dict(row) for row in data if isinstance(row, dict)]

    def query(
        self,
        *,
        source: str | None = None,
        category: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PublicNewsItem]:
        items = self.load_all()
        if source:
            items = [item for item in items if item.source == source]
        if category and category != "all":
            items = [item for item in items if item.category == category]
        if q:
            needle = q.strip().lower()
            items = [
                item
                for item in items
                if needle in item.title.lower() or needle in item.summary.lower()
            ]
        items = sorted(items, key=lambda item: item.published_at, reverse=True)
        return items[offset : offset + limit]
