from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class PublicNewsItem:
    news_id: str
    source: str
    source_channel: str
    category: str
    title: str
    summary: str
    url: str
    published_at: str
    collected_at: str
    raw_id: str
    raw_payload: dict[str, Any] = field(default_factory=dict)
    status: str = "available"

    @classmethod
    def from_raw(
        cls,
        *,
        source: str,
        source_channel: str,
        category: str,
        title: str,
        summary: str = "",
        url: str = "",
        published_at: str,
        raw_id: str = "",
        raw_payload: dict[str, Any] | None = None,
        collected_at: str | None = None,
        status: str = "available",
    ) -> "PublicNewsItem":
        normalized_title = _clean_text(title)
        normalized_summary = _clean_text(summary)
        normalized_url = _clean_text(url)
        normalized_published_at = _normalize_timestamp(published_at)
        normalized_collected_at = collected_at or datetime.now(UTC).isoformat()
        news_id = _stable_news_id(
            source=source,
            category=category,
            title=normalized_title,
            url=normalized_url,
            published_at=normalized_published_at,
        )
        return cls(
            news_id=news_id,
            source=source,
            source_channel=_clean_text(source_channel),
            category=_clean_text(category),
            title=normalized_title,
            summary=normalized_summary,
            url=normalized_url,
            published_at=normalized_published_at,
            collected_at=normalized_collected_at,
            raw_id=_clean_text(raw_id),
            raw_payload=raw_payload or {},
            status=_clean_text(status) or "available",
        )

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "PublicNewsItem":
        return cls(
            news_id=str(row.get("news_id", "")),
            source=str(row.get("source", "")),
            source_channel=str(row.get("source_channel", "")),
            category=str(row.get("category", "")),
            title=str(row.get("title", "")),
            summary=str(row.get("summary", "")),
            url=str(row.get("url", "")),
            published_at=str(row.get("published_at", "")),
            collected_at=str(row.get("collected_at", "")),
            raw_id=str(row.get("raw_id", "")),
            raw_payload=row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {},
            status=str(row.get("status", "available")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _normalize_timestamp(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt).isoformat(sep=" ")
        except ValueError:
            continue
    return text


def _stable_news_id(
    *,
    source: str,
    category: str,
    title: str,
    url: str,
    published_at: str,
) -> str:
    key = url or f"{source}|{category}|{title}|{published_at}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()

