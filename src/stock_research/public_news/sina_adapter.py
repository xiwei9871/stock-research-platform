from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from stock_research.public_news.models import PublicNewsItem

try:
    import akshare as ak
except ImportError:  # pragma: no cover - optional runtime dependency
    ak = None


SINA_SOURCE = "sina_finance"
SINA_CATEGORY_CHANNELS = {
    "focus": ("焦点",),
    "live": ("7x24",),
    "company": ("公司",),
    "market": ("市场",),
    "macro": ("宏观",),
    "international": ("国际",),
    "opinion": ("观点",),
    "original": ("原创",),
    "other": ("其他",),
}
SINA_FINANCE_HOME_URL = "https://finance.sina.com.cn/"


def normalize_sina_live_rows(rows: list[dict[str, Any]]) -> list[PublicNewsItem]:
    items: list[PublicNewsItem] = []
    for row in rows:
        content = _clean_html(row.get("内容") or row.get("content") or row.get("rich_text") or "")
        published_at = str(row.get("时间") or row.get("create_time") or row.get("published_at") or "")
        if not content or not published_at:
            continue
        title, summary = _split_live_content(content)
        items.append(
            PublicNewsItem.from_raw(
                source=SINA_SOURCE,
                source_channel="7x24",
                category="live",
                title=title,
                summary=summary,
                url=str(row.get("url") or ""),
                published_at=published_at,
                raw_id=str(row.get("id") or row.get("raw_id") or ""),
                raw_payload=dict(row),
            )
        )
    return items


def fetch_sina_public_news() -> tuple[list[PublicNewsItem], list[str]]:
    items: list[PublicNewsItem] = []
    warnings: list[str] = []
    try:
        live_rows = fetch_sina_live_rows()
        items.extend(normalize_sina_live_rows(live_rows))
    except Exception as exc:  # pragma: no cover - network/source instability
        warnings.append(f"sina_finance live fetch failed: {exc}")
    try:
        category_html = fetch_sina_category_html()
        items.extend(normalize_sina_category_html(category_html))
    except Exception as exc:  # pragma: no cover - network/source instability
        warnings.append(f"sina_finance category fetch failed: {exc}")
    return items, warnings


def fetch_sina_live_rows() -> list[dict[str, Any]]:
    if ak is None:
        raise RuntimeError("akshare is not installed")
    frame = ak.stock_info_global_sina()
    return [dict(row) for row in frame.to_dict(orient="records")]


def fetch_sina_category_html(url: str = SINA_FINANCE_HOME_URL) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8", errors="ignore")


def normalize_sina_category_html(
    html: str,
    *,
    published_at: str | None = None,
    limit: int = 80,
) -> list[PublicNewsItem]:
    soup = BeautifulSoup(html, "html.parser")
    page_published_at = published_at or _extract_page_published_at(html)
    seen: set[str] = set()
    items: list[PublicNewsItem] = []
    for anchor in soup.find_all("a", href=True):
        title = _clean_html(anchor.get_text(" ", strip=True))
        href = str(anchor.get("href") or "").strip()
        if not _is_valid_finance_article(title=title, href=href):
            continue
        url = urljoin(SINA_FINANCE_HOME_URL, href)
        if url in seen:
            continue
        seen.add(url)
        category = _infer_category(title=title, url=url)
        source_channel = SINA_CATEGORY_CHANNELS.get(category, ("其他",))[0]
        items.append(
            PublicNewsItem.from_raw(
                source=SINA_SOURCE,
                source_channel=source_channel,
                category=category,
                title=title,
                summary="",
                url=url,
                published_at=page_published_at,
                raw_id=url,
                raw_payload={"href": href, "source_page": SINA_FINANCE_HOME_URL},
            )
        )
        if len(items) >= limit:
            break
    return items


def _split_live_content(content: str) -> tuple[str, str]:
    text = _clean_html(content)
    match = re.match(r"^【([^】]+)】\s*(.*)$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    if len(text) <= 80:
        return text, ""
    return text[:80].rstrip(), text


def _clean_html(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.strip().split())


def _extract_page_published_at(html: str) -> str:
    match = re.search(r"published at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", html)
    if match:
        return match.group(1)
    return ""


def _is_valid_finance_article(*, title: str, href: str) -> bool:
    if len(title) < 6:
        return False
    if "finance.sina.com.cn" not in href and not href.startswith("/"):
        return False
    if not re.search(r"/(doc|roll|202\d)", href):
        return False
    return True


def _infer_category(*, title: str, url: str) -> str:
    text = f"{title} {url}".lower()
    if any(token in text for token in ("7x24", "直播", "快讯")):
        return "live"
    if any(token in text for token in ("zl/", "opinion", "评论", "观点", "专栏", "专家")):
        return "opinion"
    if any(token in text for token in ("original", "原创", "专题", "深度")):
        return "original"
    if any(token in text for token in ("world", "global", "international", "国际", "海外", "美国", "欧洲")):
        return "international"
    if any(token in text for token in ("china", "gncj", "macro", "宏观", "政策", "经济数据")):
        return "macro"
    if any(token in text for token in ("chanjing", "gsnews", "company", "公司", "上市公司", "产经")):
        return "company"
    if any(
        token in text
        for token in (
            "stock",
            "market",
            "fund",
            "future",
            "forex",
            "money",
            "a股",
            "港股",
            "美股",
            "基金",
            "期货",
            "外汇",
            "黄金",
            "债券",
            "市场",
            "大盘",
        )
    ):
        return "market"
    if any(token in text for token in ("焦点", "要闻", "头条")):
        return "focus"
    return "other"
