from __future__ import annotations

from stock_research.dashboard import search


def test_load_global_search_returns_grouped_results(monkeypatch):
    monkeypatch.setattr(
        search,
        "search_assets",
        lambda q, limit: [
            {
                "asset_id": "CN:SH:600519",
                "symbol": "600519",
                "name": "贵州茅台",
                "exchange": "SH",
                "board": "白酒",
                "is_active": True,
            }
        ],
    )
    monkeypatch.setattr(
        search,
        "load_public_news_for_dashboard",
        lambda **kwargs: {
            "items": [
                {
                    "id": "news-1",
                    "news_id": "news-1",
                    "source": "sina_finance",
                    "source_channel": "公司",
                    "category": "company",
                    "title": "贵州茅台经营快讯",
                    "summary": "收入保持增长",
                    "url": "https://example.com/news",
                    "published_at": "2026-06-12T09:30:00+00:00",
                    "collected_at": "2026-06-12T09:31:00+00:00",
                    "raw_id": "raw-news-1",
                    "raw_payload": {},
                    "status": "available",
                    "stocks": [
                        {
                            "asset_id": "CN:SH:600519",
                            "ts_code": "600519.SH",
                            "stock_name": "贵州茅台",
                        }
                    ],
                }
            ],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        search,
        "list_research_reports",
        lambda **kwargs: {
            "items": [
                {
                    "report_id": "r1",
                    "event_key": "r1:CN:SH:600519",
                    "asset_id": "CN:SH:600519",
                    "ts_code": "600519.SH",
                    "stock_name": "贵州茅台",
                    "report_title": "贵州茅台深度报告",
                    "publish_date": "2026-06-03",
                    "broker": "华泰证券",
                    "rating": "买入",
                    "source_url": "https://example.com/r1",
                }
            ],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        search,
        "load_platform_summary",
        lambda: {"latest_market_date": "2026-06-12"},
    )
    monkeypatch.setattr(
        search,
        "load_report_links",
        lambda trade_date: [
            {
                "report_type": "daily_topn",
                "title": "600519_daily_topn_2026-06-12_manual_v1.md",
                "path": "reports/600519_daily_topn_2026-06-12_manual_v1.md",
                "format": "md",
                "trade_date": trade_date,
            }
        ],
    )

    payload = search.load_global_search("600519", limit=3)

    assert payload["query"] == "600519"
    assert [group["key"] for group in payload["groups"]] == [
        "assets",
        "news",
        "research_reports",
        "generated_reports",
    ]
    groups = {group["key"]: group for group in payload["groups"]}
    assert groups["assets"]["items"][0]["target"] == {
        "workspace": "stock",
        "asset_id": "CN:SH:600519",
    }
    assert groups["news"]["items"][0]["target"]["workspace"] == "news"
    assert groups["news"]["items"][0]["metadata"]["stocks"][0]["asset_id"] == "CN:SH:600519"
    assert groups["research_reports"]["items"][0]["target"]["workspace"] == "researchReports"
    assert groups["generated_reports"]["items"][0]["target"]["workspace"] == "generatedReports"
    for group in payload["groups"]:
        for item in group["items"]:
            assert set(item) == {
                "id",
                "type",
                "title",
                "subtitle",
                "timestamp",
                "target",
                "score",
                "metadata",
            }


def test_load_global_search_short_query_returns_empty_groups(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("short queries should not hit read models")

    monkeypatch.setattr(search, "search_assets", fail_if_called)
    monkeypatch.setattr(search, "load_public_news_for_dashboard", fail_if_called)
    monkeypatch.setattr(search, "list_research_reports", fail_if_called)
    monkeypatch.setattr(search, "load_platform_summary", fail_if_called)
    monkeypatch.setattr(search, "load_report_links", fail_if_called)

    payload = search.load_global_search("6", limit=3)

    assert payload["query"] == "6"
    assert all(group["items"] == [] for group in payload["groups"])
    assert payload["warnings"] == []


def test_load_global_search_coerces_missing_or_non_string_query(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("short coerced queries should not hit read models")

    monkeypatch.setattr(search, "search_assets", fail_if_called)
    monkeypatch.setattr(search, "load_public_news_for_dashboard", fail_if_called)
    monkeypatch.setattr(search, "list_research_reports", fail_if_called)
    monkeypatch.setattr(search, "load_platform_summary", fail_if_called)
    monkeypatch.setattr(search, "load_report_links", fail_if_called)

    missing_payload = search.load_global_search(None, limit=3)
    numeric_payload = search.load_global_search(6, limit=3)

    assert missing_payload["query"] == ""
    assert all(group["items"] == [] for group in missing_payload["groups"])
    assert numeric_payload["query"] == "6"
    assert all(group["items"] == [] for group in numeric_payload["groups"])
    assert missing_payload["warnings"] == []
    assert numeric_payload["warnings"] == []


def test_load_global_search_keeps_other_groups_when_one_fails(monkeypatch):
    monkeypatch.setattr(search, "search_assets", lambda q, limit: [])
    monkeypatch.setattr(
        search,
        "load_public_news_for_dashboard",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("news offline")),
    )
    monkeypatch.setattr(
        search,
        "list_research_reports",
        lambda **kwargs: {"items": [], "warnings": []},
    )
    monkeypatch.setattr(
        search,
        "load_platform_summary",
        lambda: {"latest_market_date": "2026-06-12"},
    )
    monkeypatch.setattr(search, "load_report_links", lambda trade_date: [])

    payload = search.load_global_search("茅台", limit=3)

    assert "news search failed: news offline" in payload["warnings"]
    assert [group["key"] for group in payload["groups"]] == [
        "assets",
        "news",
        "research_reports",
        "generated_reports",
    ]
