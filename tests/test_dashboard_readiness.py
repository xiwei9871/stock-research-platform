from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import readiness


def test_aggregate_readiness_status_prioritizes_missing_data():
    checks = [
        {"key": "news", "status": "ready"},
        {"key": "research_reports", "status": "partial"},
        {"key": "platform_summary", "status": "missing_data"},
    ]

    assert readiness.aggregate_readiness_status(checks) == "missing_data"


def test_aggregate_readiness_status_returns_partial_for_optional_partial_sources():
    checks = [
        {"key": "platform_summary", "status": "ready"},
        {"key": "news", "status": "partial"},
        {"key": "research_reports", "status": "ready"},
    ]

    assert readiness.aggregate_readiness_status(checks) == "partial"


def test_build_platform_readiness_returns_ready_when_all_sources_available(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )
    monkeypatch.setattr(
        readiness,
        "load_public_news_for_dashboard",
        lambda **kwargs: {"items": [{"news_id": "news-1"}], "warnings": []},
    )
    monkeypatch.setattr(
        readiness,
        "load_research_report_summary",
        lambda: {"total_reports": 3, "latest_publish_date": "2026-06-12"},
    )
    monkeypatch.setattr(
        readiness,
        "load_report_links",
        lambda trade_date: [{"path": "reports/2026-06-12.html"}],
    )

    payload = readiness.build_platform_readiness(score_version="manual_v1")

    assert payload["mode"] == "eod_local"
    assert payload["status"] == "ready"
    assert payload["latest_market_date"] == "2026-06-12"
    assert payload["as_of"].endswith("+08:00")
    assert {check["key"]: check["status"] for check in payload["checks"]} == {
        "platform_summary": "ready",
        "review_queue": "ready",
        "news": "ready",
        "research_reports": "ready",
        "generated_reports": "ready",
    }
    assert payload["warnings"] == []


def test_build_platform_readiness_converts_optional_failures_and_empty_sources_to_partial(
    monkeypatch,
):
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )

    def failing_news(**kwargs):
        raise RuntimeError("news db offline")

    monkeypatch.setattr(readiness, "load_public_news_for_dashboard", failing_news)
    monkeypatch.setattr(
        readiness,
        "load_research_report_summary",
        lambda: {"total_reports": 0, "latest_publish_date": ""},
    )
    monkeypatch.setattr(readiness, "load_report_links", lambda trade_date: [])

    payload = readiness.build_platform_readiness(score_version="manual_v1")

    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["status"] == "partial"
    assert checks["platform_summary"]["status"] == "ready"
    assert checks["review_queue"]["status"] == "ready"
    assert checks["news"]["status"] == "partial"
    assert checks["research_reports"]["status"] == "partial"
    assert checks["generated_reports"]["status"] == "partial"
    assert payload["warnings"] == [
        "News unavailable",
        "Research Reports unavailable",
        "Generated Reports unavailable",
    ]


def test_build_platform_readiness_check_schema_uses_contract_fields(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )
    monkeypatch.setattr(
        readiness,
        "load_public_news_for_dashboard",
        lambda **kwargs: {"items": [{"news_id": "news-1"}], "warnings": []},
    )
    monkeypatch.setattr(readiness, "load_research_report_summary", lambda: {"total_reports": 1})
    monkeypatch.setattr(readiness, "load_report_links", lambda trade_date: [{"path": "x"}])

    payload = readiness.build_platform_readiness()

    for check in payload["checks"]:
        assert {"key", "label", "status", "detail"} <= set(check)
        assert "name" not in check
        assert "message" not in check


def test_build_platform_readiness_platform_summary_exception_is_stable_missing_data(
    monkeypatch,
):
    def failing_summary(score_version, top_n):
        raise RuntimeError("database password leaked")

    monkeypatch.setattr(readiness, "load_platform_summary", failing_summary)

    payload = readiness.build_platform_readiness()

    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["status"] == "missing_data"
    assert checks["platform_summary"]["status"] == "missing_data"
    assert checks["platform_summary"]["detail"] == "Platform summary unavailable"
    assert payload["warnings"] == ["Platform summary unavailable"]
    assert "database password leaked" not in str(payload)


def test_build_platform_readiness_missing_latest_market_date_is_missing_data(
    monkeypatch,
):
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )

    payload = readiness.build_platform_readiness()

    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["status"] == "missing_data"
    assert checks["platform_summary"]["status"] == "missing_data"
    assert checks["review_queue"]["status"] == "unknown"
    assert payload["warnings"] == ["Platform summary unavailable"]


def test_build_platform_readiness_missing_topn_makes_review_queue_partial(
    monkeypatch,
):
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(
        readiness,
        "load_public_news_for_dashboard",
        lambda **kwargs: {"items": [{"news_id": "news-1"}], "warnings": []},
    )
    monkeypatch.setattr(readiness, "load_research_report_summary", lambda: {"total_reports": 1})
    monkeypatch.setattr(readiness, "load_report_links", lambda trade_date: [{"path": "x"}])

    payload = readiness.build_platform_readiness()

    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["status"] == "partial"
    assert checks["platform_summary"]["status"] == "ready"
    assert checks["review_queue"]["status"] == "partial"
    assert payload["warnings"] == ["Review Queue unavailable"]


def test_build_platform_readiness_dedupes_warnings_preserving_order(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )
    monkeypatch.setattr(
        readiness,
        "load_public_news_for_dashboard",
        lambda **kwargs: {"items": [], "warnings": ["News unavailable"]},
    )
    monkeypatch.setattr(readiness, "load_research_report_summary", lambda: {"total_reports": 0})
    monkeypatch.setattr(readiness, "load_report_links", lambda trade_date: [])

    payload = readiness.build_platform_readiness()

    assert payload["warnings"] == [
        "News unavailable",
        "Research Reports unavailable",
        "Generated Reports unavailable",
    ]


def test_build_platform_readiness_does_not_call_build_review_queue(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )

    if hasattr(readiness, "build_review_queue"):
        monkeypatch.setattr(
            readiness,
            "build_review_queue",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("should not be called")),
        )

    monkeypatch.setattr(
        readiness,
        "load_public_news_for_dashboard",
        lambda **kwargs: {"items": [{"news_id": "news-1"}], "warnings": []},
    )
    monkeypatch.setattr(readiness, "load_research_report_summary", lambda: {"total_reports": 1})
    monkeypatch.setattr(readiness, "load_report_links", lambda trade_date: [{"path": "x"}])

    payload = readiness.build_platform_readiness()

    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["review_queue"]["status"] == "ready"


def test_platform_readiness_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_platform_readiness",
        lambda score_version="manual_v1": {
            "mode": "eod_local",
            "status": "ready",
            "as_of": "2026-06-15T10:00:00+08:00",
            "latest_market_date": "2026-06-12",
            "checks": [],
            "warnings": [],
            "score_version": score_version,
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/readiness?score_version=manual_v2")

    assert response.status_code == 200
    assert response.json()["score_version"] == "manual_v2"
