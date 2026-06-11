from pathlib import Path

from stock_research.public_news.models import PublicNewsItem
from stock_research.public_news.store import JsonPublicNewsStore
from stock_research.public_news.sina_adapter import (
    SINA_CATEGORY_CHANNELS,
    normalize_sina_category_html,
    normalize_sina_live_rows,
)
from stock_research.public_news.service import PublicNewsService


def test_public_news_item_builds_stable_id_from_url() -> None:
    item = PublicNewsItem.from_raw(
        source="sina_finance",
        source_channel="7x24",
        category="live",
        title="市场消息",
        summary="",
        url="https://finance.sina.com.cn/test/1.shtml",
        published_at="2026-06-11 08:44:57",
        raw_id="raw-1",
        raw_payload={"x": 1},
    )

    assert item.news_id
    assert item.source == "sina_finance"
    assert item.category == "live"
    assert item.status == "available"


def test_json_public_news_store_upserts_and_filters(tmp_path: Path) -> None:
    store = JsonPublicNewsStore(tmp_path / "public_news.json")
    live = PublicNewsItem.from_raw(
        source="sina_finance",
        source_channel="7x24",
        category="live",
        title="全球快讯",
        summary="",
        url="https://finance.sina.com.cn/live/1",
        published_at="2026-06-11 09:00:00",
    )
    macro = PublicNewsItem.from_raw(
        source="sina_finance",
        source_channel="宏观",
        category="macro",
        title="宏观政策更新",
        summary="政策摘要",
        url="https://finance.sina.com.cn/macro/1",
        published_at="2026-06-11 08:00:00",
    )

    result = store.upsert_items([live, macro, live])

    assert result["stored"] == 2
    assert [item.title for item in store.query(category="macro")] == ["宏观政策更新"]
    assert [item.title for item in store.query(q="快讯")] == ["全球快讯"]


def test_normalize_sina_live_rows_converts_akshare_shape() -> None:
    items = normalize_sina_live_rows(
        [
            {
                "时间": "2026-06-11 08:44:57",
                "内容": "【辽宁省委书记调研文旅产业】推动文旅体商深度融合。（辽宁日报）",
            }
        ]
    )

    assert len(items) == 1
    assert items[0].source == "sina_finance"
    assert items[0].source_channel == "7x24"
    assert items[0].category == "live"
    assert items[0].title == "辽宁省委书记调研文旅产业"
    assert "文旅体商深度融合" in items[0].summary


def test_normalize_sina_category_html_maps_homepage_links_to_categories() -> None:
    html = """
    <html><body>
      <a href="https://finance.sina.com.cn/stock/market/2026-06-11/doc-1.shtml">A股市场震荡</a>
      <a href="https://finance.sina.com.cn/china/gncj/2026-06-11/doc-2.shtml">宏观政策更新</a>
      <a href="https://finance.sina.com.cn/chanjing/gsnews/2026-06-11/doc-3.shtml">某公司发布新品</a>
      <a href="https://finance.sina.com.cn/zl/china/2026-06-11/doc-4.shtml">专家观点：市场观察</a>
    </body></html>
    """

    items = normalize_sina_category_html(html, published_at="2026-06-11 10:06:00")

    assert [(item.category, item.title) for item in items] == [
        ("market", "A股市场震荡"),
        ("macro", "宏观政策更新"),
        ("company", "某公司发布新品"),
        ("opinion", "专家观点：市场观察"),
    ]


def test_public_news_service_refresh_stores_items_and_counts_by_category(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = JsonPublicNewsStore(tmp_path / "public_news.json")

    monkeypatch.setattr(
        "stock_research.public_news.service.fetch_sina_public_news",
        lambda: (
            [
                PublicNewsItem.from_raw(
                    source="sina_finance",
                    source_channel="7x24",
                    category="live",
                    title="全球快讯",
                    url="https://finance.sina.com.cn/live/1",
                    published_at="2026-06-11 09:00:00",
                ),
                PublicNewsItem.from_raw(
                    source="sina_finance",
                    source_channel="宏观",
                    category="macro",
                    title="宏观政策",
                    url="https://finance.sina.com.cn/macro/1",
                    published_at="2026-06-11 08:00:00",
                ),
            ],
            [],
        ),
    )

    result = PublicNewsService(store).refresh()

    assert result["stored"] == 2
    assert result["counts_by_category"] == {"live": 1, "macro": 1}
    assert [item["title"] for item in PublicNewsService(store).list_items(category="live")["items"]] == [
        "全球快讯"
    ]


def test_public_news_service_refresh_preserves_warnings_on_fetch_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = JsonPublicNewsStore(tmp_path / "public_news.json")

    def fail_fetch():
        raise RuntimeError("source unavailable")

    monkeypatch.setattr("stock_research.public_news.service.fetch_sina_public_news", fail_fetch)

    result = PublicNewsService(store).refresh()

    assert result["stored"] == 0
    assert result["warnings"] == ["sina_finance refresh failed: source unavailable"]
    assert PublicNewsService(store).list_items()["warnings"] == ["no cached public news items"]


def test_sina_category_channels_define_requested_news_window_categories() -> None:
    assert set(SINA_CATEGORY_CHANNELS) == {
        "focus",
        "live",
        "company",
        "market",
        "macro",
        "international",
        "opinion",
        "original",
        "other",
    }
