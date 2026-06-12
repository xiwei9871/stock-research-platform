from datetime import date

from stock_research.dashboard import research_reports


def test_research_report_summary_returns_counts(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        if "COUNT(DISTINCT s.report_id) AS total_reports" in sql:
            return [
                {
                    "total_reports": 3,
                    "covered_stocks": 2,
                    "latest_publish_date": date(2026, 6, 3),
                    "latest_feature_date": date(2026, 6, 2),
                    "source_count": 2,
                }
            ]
        if "GROUP BY s.source_name" in sql:
            return [{"source_name": "cfi_ybyl", "rows": 2}]
        if "GROUP BY rating" in sql:
            return [{"rating": "买入", "rows": 2}]
        if "GROUP BY broker" in sql:
            return [{"broker": "华泰证券", "rows": 2}]
        raise AssertionError(sql)

    monkeypatch.setattr(research_reports, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(research_reports, "fetch_all", fake_fetch_all)

    result = research_reports.load_research_report_summary(service="test")

    assert result["total_reports"] == 3
    assert result["covered_stocks"] == 2
    assert result["latest_publish_date"] == "2026-06-03"
    assert result["latest_feature_date"] == "2026-06-02"
    assert result["source_counts"] == [{"source_name": "cfi_ybyl", "rows": 2}]
    assert result["rating_counts"] == [{"rating": "买入", "rows": 2}]
    assert result["broker_counts"] == [{"broker": "华泰证券", "rows": 2}]
    assert "COUNT(DISTINCT s.report_id) AS total_reports" in calls[0][0]
    for sql, _params in calls[1:]:
        assert "FROM research.stock_report_source s" in sql
        assert "JOIN research.stock_report_event e USING (report_id)" in sql


def test_list_research_reports_passes_filters_and_pagination(monkeypatch):
    captured = []

    def fake_fetch_all(conn, sql, params=None):
        captured.append((sql, params))
        if "COUNT(*) AS total" in sql:
            return [{"total": 1}]
        return [
            {
                "report_id": "r1",
                "asset_id": "CN:SH:600519",
                "ts_code": "600519.SH",
                "stock_name": "贵州茅台",
                "industry_name": "白酒",
                "report_title": "贵州茅台深度报告",
                "publish_date": date(2026, 6, 3),
                "report_date": date(2026, 6, 3),
                "broker": "华泰证券",
                "analyst": "张三",
                "rating": "买入",
                "rating_change": "维持",
                "target_price": 1900,
                "target_upside": 0.15,
                "source_type": "public_web_search_result",
                "source_name": "cfi_ybyl",
                "source_confidence": 0.8,
                "public_access": True,
                "copyright_note": "metadata only",
                "source_url": "https://example.com/r1",
                "raw_summary": "summary",
                "company_view": "company",
                "industry_view": "industry",
                "risk_summary": "risk",
                "metadata": {"provider": "test"},
            }
        ]

    monkeypatch.setattr(research_reports, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(research_reports, "fetch_all", fake_fetch_all)

    result = research_reports.list_research_reports(
        q="茅台",
        broker="华泰",
        rating="买入",
        source_name="cfi_ybyl",
        start_date="2026-06-01",
        end_date="2026-06-05",
        has_target_price=True,
        limit=25,
        offset=5,
        service="test",
    )

    assert result["total"] == 1
    assert result["limit"] == 25
    assert result["offset"] == 5
    assert result["items"][0]["stock_name"] == "贵州茅台"
    assert result["items"][0]["publish_date"] == "2026-06-03"
    list_sql, list_params = captured[1]
    assert "target_price IS NOT NULL" in list_sql
    assert "s.broker ILIKE %s" in list_sql
    assert list_params[-2:] == [25, 5]


def test_list_research_reports_bounds_limit_to_minimum(monkeypatch):
    def fake_fetch_all(conn, sql, params=None):
        if "COUNT(*) AS total" in sql:
            return [{"total": 0}]
        return []

    monkeypatch.setattr(research_reports, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(research_reports, "fetch_all", fake_fetch_all)

    result = research_reports.list_research_reports(limit=0, service="test")

    assert result["limit"] == 1


def test_list_research_reports_bounds_limit_to_maximum(monkeypatch):
    def fake_fetch_all(conn, sql, params=None):
        if "COUNT(*) AS total" in sql:
            return [{"total": 0}]
        return []

    monkeypatch.setattr(research_reports, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(research_reports, "fetch_all", fake_fetch_all)

    result = research_reports.list_research_reports(limit=999, service="test")

    assert result["limit"] == 200


def test_load_asset_research_reports_returns_summary(monkeypatch):
    def fake_fetch_all(conn, sql, params=None):
        if "COUNT(*) FILTER" in sql:
            return [
                {
                    "report_count_30d": 2,
                    "report_count_90d": 4,
                    "broker_coverage_count_90d": 3,
                    "latest_report_date": date(2026, 6, 3),
                    "latest_rating": "买入",
                    "latest_target_price": 1900,
                }
            ]
        return [
            {
                "report_id": "r1",
                "asset_id": "CN:SH:600519",
                "ts_code": "600519.SH",
                "stock_name": "贵州茅台",
                "industry_name": "白酒",
                "report_title": "贵州茅台深度报告",
                "publish_date": date(2026, 6, 3),
                "report_date": date(2026, 6, 3),
                "broker": "华泰证券",
                "analyst": "",
                "rating": "买入",
                "rating_change": "",
                "target_price": 1900,
                "target_upside": None,
                "source_type": "public_web_search_result",
                "source_name": "cfi_ybyl",
                "source_confidence": 0.8,
                "public_access": True,
                "copyright_note": "metadata only",
                "source_url": "https://example.com/r1",
                "raw_summary": "",
                "company_view": "",
                "industry_view": "",
                "risk_summary": "",
                "metadata": {},
            }
        ]

    monkeypatch.setattr(research_reports, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(research_reports, "fetch_all", fake_fetch_all)

    result = research_reports.load_asset_research_reports("600519.SH", limit=5, lookback_days=90, service="test")

    assert result["asset_id"] == "600519.SH"
    assert result["summary"]["report_count_90d"] == 4
    assert result["summary"]["latest_rating"] == "买入"
    assert result["items"][0]["report_title"] == "贵州茅台深度报告"


class DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
