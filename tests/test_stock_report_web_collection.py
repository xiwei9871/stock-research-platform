from pathlib import Path
import threading

import pandas as pd

from stock_research import cli
from stock_research import stock_report_web_collection
from stock_research.stock_report_web_collection import (
    build_stock_report_features_from_events,
    build_stock_report_search_plan_from_candidates,
    collect_stock_report_web_sources_from_plan,
    enrich_candidate_stock_names,
    upsert_stock_report_features,
)


def _candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "industry_name": "电子元件",
                "research_packet_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "fundamental_hard_risk": "no_clear_hard_risk",
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "industry_name": "电子元件",
                "research_packet_rank": 2,
                "mid_trend_funnel_score": 84.6,
                "fundamental_hard_risk": "no_clear_hard_risk",
            },
        ]
    )


def test_search_plan_builds_public_web_tasks_without_trading_signal():
    result = build_stock_report_search_plan_from_candidates(_candidates(), trade_date="2026-06-02")

    plan = result["search_plan"]
    assert len(plan) >= 8
    assert {"eastmoney", "sina", "ths", "general"}.issubset(set(plan["source_domain"]))
    assert plan["task_id"].is_unique
    assert set(plan["status"]) == {"pending"}
    assert "江海股份" in " ".join(plan["search_query"].astype(str))
    assert "auto_trade_enabled" in plan.columns
    assert not plan["auto_trade_enabled"].any()
    assert "买入" not in result["report"]


def test_candidate_name_enrichment_uses_local_lookup_when_name_is_code(tmp_path: Path):
    lookup_path = tmp_path / "names.csv"
    pd.DataFrame(
        [
            {
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
            }
        ]
    ).to_csv(lookup_path, index=False)
    candidates = _candidates().copy()
    candidates.loc[0, "stock_name"] = "002484"

    enriched = enrich_candidate_stock_names(candidates, lookup_paths=[lookup_path], db_lookup=False)

    assert enriched.loc[0, "stock_name"] == "江海股份"


def test_collect_web_sources_dry_run_keeps_tasks_pending_without_fetching():
    plan = build_stock_report_search_plan_from_candidates(_candidates(), trade_date="2026-06-02")["search_plan"]

    result = collect_stock_report_web_sources_from_plan(plan, dry_run=True)

    collection = result["collection"]
    assert len(collection) == len(plan)
    assert set(collection["collection_status"]) == {"dry_run_pending"}
    assert "source_url" in collection.columns
    assert collection["source_url"].isna().all()


def test_collect_web_sources_live_adapter_extracts_public_metadata():
    plan = build_stock_report_search_plan_from_candidates(_candidates().head(1), trade_date="2026-06-02")[
        "search_plan"
    ].head(1)

    def fake_fetcher(url: str) -> str:
        assert "baidu.com" in url
        return """
        <html><body>
          <a href="https://finance.eastmoney.com/a/202605280001.html">江海股份：维持买入评级，目标价30元</a>
          <div>中信证券 2026-05-28 研报摘要</div>
        </body></html>
        """

    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        fetcher=fake_fetcher,
        max_results_per_task=2,
    )

    collection = result["collection"]
    assert len(collection) == 1
    assert collection.iloc[0]["collection_status"] == "found"
    assert collection.iloc[0]["source_url"] == "https://finance.eastmoney.com/a/202605280001.html"
    assert "江海股份" in collection.iloc[0]["source_title"]
    assert "auto_trade_enabled" in collection.columns
    assert not collection["auto_trade_enabled"].any()
    sources = result["sources"]
    events = result["events"]
    assert sources.iloc[0]["source_url"] == "https://finance.eastmoney.com/a/202605280001.html"
    assert events.iloc[0]["rating"] == "买入"
    assert events.iloc[0]["target_price"] == 30.0


def test_collect_akshare_em_reports_builds_source_and_event_candidates(monkeypatch):
    plan = build_stock_report_search_plan_from_candidates(_candidates().head(1), trade_date="2026-06-02")[
        "search_plan"
    ]

    class FakeAk:
        @staticmethod
        def stock_research_report_em(symbol: str):
            assert symbol == "002484"
            return pd.DataFrame(
                [
                    {
                        "股票代码": "002484",
                        "股票简称": "江海股份",
                        "报告名称": "公司深度报告：乘AI之风",
                        "东财评级": "买入",
                        "机构": "爱建证券",
                        "行业": "元件",
                        "日期": "2026-04-23",
                        "报告PDF链接": "https://pdf.dfcfw.com/pdf/H3_AP202604231821501366_1.pdf",
                    }
                ]
            )

    monkeypatch.setattr(stock_report_web_collection, "ak", FakeAk)

    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="akshare_em",
        max_results_per_task=3,
    )

    collection = result["collection"]
    assert len(collection) == 1
    assert collection.iloc[0]["collection_status"] == "found"
    assert collection.iloc[0]["source_url"].startswith("https://pdf.dfcfw.com")
    assert collection.iloc[0]["rating"] == "买入"
    assert collection.iloc[0]["broker"] == "爱建证券"
    assert result["sources"].iloc[0]["source_type"] == "public_web_search_result"
    assert result["events"].iloc[0]["report_date"] == "2026-04-23"
    assert not collection["auto_trade_enabled"].any()


def test_collect_bing_site_search_rewrites_queries_to_source_domains():
    plan = build_stock_report_search_plan_from_candidates(_candidates().head(1), trade_date="2026-06-02")[
        "search_plan"
    ].head(1)
    fetched_urls = []

    def fake_fetcher(url: str) -> str:
        fetched_urls.append(url)
        assert "cn.bing.com/search" in url
        assert "site%3A" in url
        if "data.eastmoney.com" not in url:
            return "<html><body></body></html>"
        return """
        <html><body>
          <a href="https://data.eastmoney.com/report/20260528/abc.html">
            江海股份：首次覆盖买入评级，目标价30元 2026-05-28
          </a>
        </body></html>
        """

    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="bing_site_search",
        fetcher=fake_fetcher,
        max_results_per_task=1,
    )

    collection = result["collection"]
    assert fetched_urls
    assert any("site%3Adata.eastmoney.com%2Freport" in url for url in fetched_urls)
    found = collection[collection["collection_status"].eq("found")]
    assert len(found) == 1
    assert found.iloc[0]["source_url"] == "https://data.eastmoney.com/report/20260528/abc.html"
    assert found.iloc[0]["rating"] == "买入"
    assert found.iloc[0]["target_price"] == 30.0
    assert result["events"].iloc[0]["report_date"] == "2026-05-28"


def test_collect_sina_report_page_extracts_report_table_metadata():
    plan = build_stock_report_search_plan_from_candidates(_candidates().head(1), trade_date="2026-06-02")[
        "search_plan"
    ]
    fetched_urls = []

    def fake_fetcher(url: str) -> str:
        fetched_urls.append(url)
        assert "stock.finance.sina.com.cn" in url
        assert "symbol=sz002484" in url
        return """
        <html><body><table>
          <tr><td>序号</td><td>标题</td><td>报告类型</td><td>发布日期</td><td>机构</td><td>研究员</td></tr>
          <tr>
            <td>1</td>
            <td class="tal f14"><a target="_blank" title="江海股份(002484)：26Q1稳健增长" href="//stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/search/rptid/830347714156/index.phtml">江海股份(002484)：26Q1稳健增长</a></td>
            <td>公司</td>
            <td>2026-04-24</td>
            <td><a><div class="fname05"><span>中泰证券股份有限公司</span></div></a></td>
            <td><div class="fname"><span>王芳/刘博文</span></div></td>
          </tr>
        </table></body></html>
        """

    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="sina_report_page",
        fetcher=fake_fetcher,
        max_results_per_task=3,
    )

    assert len(fetched_urls) == 1
    collection = result["collection"]
    assert len(collection) == 1
    assert collection.iloc[0]["collection_status"] == "found"
    assert collection.iloc[0]["source_url"].startswith("https://stock.finance.sina.com.cn/stock/go.php/vReport_Show")
    assert collection.iloc[0]["broker"] == "中泰证券股份有限公司"
    assert collection.iloc[0]["publish_date"] == "2026-04-24"
    assert result["sources"].iloc[0]["source_name"] == "sina_report_page"
    assert result["events"].iloc[0]["report_date"] == "2026-04-24"


def test_direct_source_collection_fetches_stocks_concurrently_when_workers_enabled():
    plan = build_stock_report_search_plan_from_candidates(_candidates(), trade_date="2026-06-02")["search_plan"]
    active = 0
    lock = threading.Lock()
    both_started = threading.Event()

    def fake_fetcher(url: str) -> str:
        nonlocal active
        with lock:
            active += 1
            if active == 2:
                both_started.set()
        try:
            assert both_started.wait(0.5), "second stock fetch did not start concurrently"
            return """
            <html><body><table>
              <tr><td>序号</td><td>标题</td><td>报告类型</td><td>发布日期</td><td>机构</td><td>研究员</td></tr>
              <tr>
                <td>1</td>
                <td><a href="//stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/search/rptid/new/index.phtml">并发采集报告</a></td>
                <td>公司</td><td>2026-04-24</td><td><span>测试证券</span></td><td><span>测试分析师</span></td>
              </tr>
            </table></body></html>
            """
        finally:
            with lock:
                active -= 1

    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="sina_report_page",
        fetcher=fake_fetcher,
        max_results_per_task=1,
        workers=2,
    )

    collection = result["collection"]
    assert both_started.is_set()
    assert len(collection) == 2
    assert set(collection["collection_status"]) == {"found"}


def test_direct_source_collection_emits_progress_logs():
    plan = build_stock_report_search_plan_from_candidates(_candidates().head(1), trade_date="2026-06-02")[
        "search_plan"
    ]
    logs: list[str] = []

    def fake_fetcher(url: str) -> str:
        return "<html><body></body></html>"

    collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="sina_report_page",
        fetcher=fake_fetcher,
        max_results_per_task=1,
        workers=1,
        progress_every=1,
        progress_logger=logs.append,
    )

    assert any(
        line.startswith("stock_report_web_sources|progress|adapter=sina_report_page|completed=1|total=1")
        for line in logs
    )
    assert any(line.startswith("stock_report_web_sources|done|adapter=sina_report_page|completed=1|total=1") for line in logs)


def test_direct_source_collection_stops_after_consecutive_fetch_errors():
    plan = build_stock_report_search_plan_from_candidates(_candidates(), trade_date="2026-06-02")["search_plan"]
    calls = 0
    logs: list[str] = []

    def fake_fetcher(url: str) -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("HTTP 456")

    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="sina_report_page",
        fetcher=fake_fetcher,
        max_results_per_task=1,
        workers=1,
        progress_every=1,
        progress_logger=logs.append,
        stop_after_consecutive_fetch_errors=1,
    )

    collection = result["collection"]
    assert calls == 1
    assert len(collection) == 1
    assert collection.iloc[0]["collection_status"] == "fetch_error"
    assert any("stock_report_web_sources|stopped|adapter=sina_report_page|completed=1|total=2" in line for line in logs)


def test_direct_source_collection_sleeps_between_sequential_requests():
    plan = build_stock_report_search_plan_from_candidates(_candidates(), trade_date="2026-06-02")["search_plan"]
    sleep_calls: list[float] = []

    def fake_fetcher(url: str) -> str:
        return "<html><body></body></html>"

    collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="sina_report_page",
        fetcher=fake_fetcher,
        max_results_per_task=1,
        workers=1,
        request_sleep_seconds=2.5,
        sleeper=sleep_calls.append,
    )

    assert sleep_calls == [2.5]


def test_collect_web_sources_filters_collection_by_publish_date_window():
    plan = build_stock_report_search_plan_from_candidates(_candidates().head(1), trade_date="2026-06-02")[
        "search_plan"
    ]

    def fake_fetcher(url: str) -> str:
        return """
        <html><body><table>
          <tr><td>序号</td><td>标题</td><td>报告类型</td><td>发布日期</td><td>机构</td><td>研究员</td></tr>
          <tr>
            <td>1</td>
            <td><a href="//stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/search/rptid/old/index.phtml">江海股份(002484)：旧报告</a></td>
            <td>公司</td><td>2024-12-31</td><td><span>旧证券</span></td><td><span>旧分析师</span></td>
          </tr>
          <tr>
            <td>2</td>
            <td><a href="//stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/search/rptid/new/index.phtml">江海股份(002484)：新报告</a></td>
            <td>公司</td><td>2025-01-02</td><td><span>新证券</span></td><td><span>新分析师</span></td>
          </tr>
        </table></body></html>
        """

    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="sina_report_page",
        fetcher=fake_fetcher,
        max_results_per_task=5,
        start_date="2025-01-01",
        end_date="2026-06-03",
    )

    collection = result["collection"]
    assert len(collection) == 1
    assert collection.iloc[0]["publish_date"] == "2025-01-02"
    assert collection.iloc[0]["broker"] == "新证券"
    assert len(result["events"]) == 1


def test_collect_sohu_jlp_rating_extracts_rating_table_metadata():
    plan = build_stock_report_search_plan_from_candidates(_candidates().head(1), trade_date="2026-06-02")[
        "search_plan"
    ]
    fetched_urls = []

    def fake_fetcher(url: str) -> str:
        fetched_urls.append(url)
        assert "q.stock.sohu.com/cn/002484/index_kp.shtml" in url
        return """
        <html><body>
        <table>
          <tr><td>指标</td><td>数值</td><td>代码</td><td>分数</td><td>日期</td></tr>
          <tr><td>83.46</td><td>50272</td><td>103</td><td>1</td><td>2026-06-02</td></tr>
        </table>
        <table>
          <tr><td>评级</td><td>目标价</td><td>分析师</td><td>所属机构</td><td>研报日期</td></tr>
          <tr>
            <td class="td1 red"><span>买入</span></td>
            <td class="td2">34.40</td>
            <td class="td3"><a>孙潇雅</a><a>李双亮</a></td>
            <td class="td4">天风证券</td>
            <td class="td5">2026-01-13</td>
          </tr>
        </table></body></html>
        """

    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="sohu_jlp_rating",
        fetcher=fake_fetcher,
        max_results_per_task=3,
    )

    assert len(fetched_urls) == 1
    collection = result["collection"]
    assert len(collection) == 1
    assert collection.iloc[0]["collection_status"] == "found"
    assert collection.iloc[0]["rating"] == "买入"
    assert collection.iloc[0]["target_price"] == 34.4
    assert collection.iloc[0]["broker"] == "天风证券"
    assert result["sources"].iloc[0]["source_name"] == "sohu_jlp_rating"
    assert result["events"].iloc[0]["report_date"] == "2026-01-13"


def test_collect_cfi_ybyl_extracts_research_report_table_metadata():
    plan = build_stock_report_search_plan_from_candidates(_candidates().head(1), trade_date="2026-06-02")[
        "search_plan"
    ]
    fetched_urls = []

    def fake_fetcher(url: str) -> str:
        fetched_urls.append(url)
        assert "quote.cfi.cn/quote.aspx" in url
        assert "contenttype=ybyl" in url
        assert "searchcode=002484" in url
        return """
        <html><body>
          <table id='tab_yb'>
            <tr><td colspan='4'>江海股份(002484)研报明细</td></tr>
            <tr><td>发布日期</td><td>评级类别</td><td>机构名称</td><td>研报</td></tr>
            <tr>
              <td nowrap><a href=javascript:void(0); onclick=func_link_bimage(20260113);>2026-01-13</a></td>
              <td>买入</td>
              <td>天风证券股份有限公司</td>
              <td><a target=_blank href=/ybdata.aspx?id=20260113000420>江海股份(002484)：26Q1稳健增长</a></td>
            </tr>
          </table>
        </body></html>
        """

    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=False,
        adapter="cfi_ybyl",
        fetcher=fake_fetcher,
        max_results_per_task=3,
    )

    assert len(fetched_urls) == 1
    collection = result["collection"]
    assert len(collection) == 1
    assert collection.iloc[0]["collection_status"] == "found"
    assert collection.iloc[0]["source_name"] == "cfi_ybyl"
    assert collection.iloc[0]["source_url"] == "https://quote.cfi.cn/ybdata.aspx?id=20260113000420"
    assert collection.iloc[0]["rating"] == "买入"
    assert collection.iloc[0]["broker"] == "天风证券股份有限公司"
    assert collection.iloc[0]["publish_date"] == "2026-01-13"
    assert result["events"].iloc[0]["report_date"] == "2026-01-13"


def test_feature_builder_aggregates_public_report_events():
    events = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-05-28",
                "broker": "券商A",
                "rating": "买入",
                "rating_change": "上调",
                "target_price": 30.0,
                "target_upside": 0.25,
                "negative_report_flag": False,
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-04-15",
                "broker": "券商B",
                "rating": "增持",
                "rating_change": "",
                "target_price": 28.0,
                "target_upside": 0.15,
                "negative_report_flag": False,
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "report_date": "2026-05-20",
                "broker": "券商C",
                "rating": "中性",
                "rating_change": "",
                "target_price": 20.0,
                "target_upside": -0.05,
                "negative_report_flag": True,
            },
        ]
    )

    result = build_stock_report_features_from_events(events, trade_date="2026-06-02")

    features = result["features"].sort_values("ts_code").reset_index(drop=True)
    row = features[features["ts_code"].eq("002484.SZ")].iloc[0]
    assert row["report_count_90d"] == 2
    assert row["positive_rating_count"] == 2
    assert row["rating_upgrade_count"] == 1
    assert row["target_price_median"] == 29.0
    assert not bool(row["negative_report_flag"])
    assert row["research_support_score"] > 0


def test_feature_builder_aggregates_pdf_extract_metadata_into_feature_metadata():
    events = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-05-28",
                "broker": "券商A",
                "rating": "买入",
                "rating_change": "上调",
                "target_price": 30.0,
                "metadata": {
                    "pdf_extract": {
                        "target_price_confidence": 0.8,
                        "forecast_eps_values": [1.2, 1.5],
                        "forecast_pe_values": [20.0],
                        "has_profit_forecast": True,
                        "has_risk_section": True,
                        "risk_summary": "需求不及预期",
                    }
                },
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-04-15",
                "broker": "券商B",
                "rating": "增持",
                "target_price": 28.0,
                "metadata": {
                    "pdf_extract": {
                        "target_price_confidence": 0.6,
                        "forecast_eps_values": [],
                        "forecast_pe_values": [18.0, 17.0],
                        "has_profit_forecast": False,
                        "has_risk_section": False,
                    }
                },
            },
        ]
    )

    features = build_stock_report_features_from_events(events, trade_date="2026-06-02")["features"]

    row = features.iloc[0]
    metadata = row["metadata"]
    assert metadata["pdf_target_price_count_90d"] == 2
    assert metadata["pdf_target_price_high_confidence_count_90d"] == 1
    assert metadata["pdf_target_price_confidence_avg_90d"] == 0.7
    assert metadata["pdf_profit_forecast_count_90d"] == 1
    assert metadata["pdf_eps_forecast_count_90d"] == 1
    assert metadata["pdf_pe_forecast_count_90d"] == 2
    assert metadata["pdf_risk_section_count_90d"] == 1
    assert metadata["latest_pdf_risk_summary"] == "需求不及预期"


def test_upsert_stock_report_features_writes_feature_daily(monkeypatch):
    calls = []

    class FakeContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        return FakeContext()

    def fake_execute_many(conn, sql, rows):
        calls.append((sql, list(rows)))

    monkeypatch.setattr(stock_report_web_collection, "connect", fake_connect)
    monkeypatch.setattr(stock_report_web_collection, "execute_many", fake_execute_many)
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_count_30d": 1,
                "report_count_90d": 2,
                "latest_report_days": 5,
                "positive_rating_count": 2,
                "rating_upgrade_count": 1,
                "target_price_median": 30.0,
                "target_upside_median": 0.2,
                "target_price_dispersion": 0.0,
                "broker_coverage_count": 2,
                "top_broker_coverage_count": 1,
                "negative_report_flag": False,
                "research_support_score": 42.0,
                "source_count": 2,
                "auto_trade_enabled": False,
                "metadata": {
                    "pdf_target_price_count_90d": 1,
                    "pdf_target_price_confidence_avg_90d": 0.8,
                },
            }
        ]
    )

    result = upsert_stock_report_features(features=features)

    assert result == {"feature_rows": 1}
    assert len(calls) == 1
    sql, rows = calls[0]
    assert "INSERT INTO research.stock_report_feature_daily" in sql
    assert "ON CONFLICT (trade_date, ts_code)" in sql
    assert rows[0][2] == "002484.SZ"
    assert '"pdf_target_price_count_90d": 1' in rows[0][-1]


def test_feature_builder_excludes_future_report_events():
    events = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-05-28",
                "broker": "券商A",
                "rating": "买入",
                "target_price": 30.0,
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-06-10",
                "broker": "券商B",
                "rating": "买入",
                "target_price": 40.0,
            },
        ]
    )

    features = build_stock_report_features_from_events(events, trade_date="2026-06-02")["features"]

    row = features.iloc[0]
    assert row["report_count_90d"] == 1
    assert row["broker_coverage_count"] == 1
    assert row["target_price_median"] == 30.0


def test_feature_builder_handles_stocks_without_recent_reports():
    events = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
                "report_date": "2025-04-30",
                "broker": "中邮证券",
                "rating": "增持",
            }
        ]
    )

    features = build_stock_report_features_from_events(events, trade_date="2026-06-02")["features"]

    row = features.iloc[0]
    assert row["report_count_90d"] == 0
    assert row["positive_rating_count"] == 0
    assert row["research_support_score"] == 0.0


def test_feature_builder_handles_missing_rating_values():
    events = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-05-28",
                "broker": "券商A",
                "rating": None,
            }
        ]
    )

    features = build_stock_report_features_from_events(events, trade_date="2026-06-02")["features"]

    assert features.iloc[0]["report_count_90d"] == 1
    assert features.iloc[0]["positive_rating_count"] == 0


def test_search_plan_writes_outputs(tmp_path: Path):
    result = build_stock_report_search_plan_from_candidates(
        _candidates(),
        trade_date="2026-06-02",
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["search_plan"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_stock_report_search_plan(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "search_plan": pd.DataFrame([{"task_id": "T1"}]),
            "paths": {
                "search_plan": str(tmp_path / "plan.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_stock_report_search_plan", fake_run)

    cli.main_for_args(
        [
            "build-stock-report-search-plan",
            "--research-packet-path",
            "outputs/research/mid_trend_research_packet_20260602/mid_trend_research_packet_candidates.csv",
            "--trade-date",
            "2026-06-02",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["trade_date"] == "2026-06-02"
    out = capsys.readouterr().out
    assert "stock_report_search_plan|search_plan|" in out
    assert "stock_report_search_plan|rows|1" in out
