from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import readiness


class _FakeConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_aggregate_readiness_status_prioritizes_missing_data():
    checks = [
        {"key": "news", "status": "ready"},
        {"key": "research_reports", "status": "partial"},
        {"key": "platform_summary", "status": "missing_data"},
    ]

    assert readiness.aggregate_readiness_status(checks) == "BLOCKED"


def test_aggregate_readiness_status_returns_partial_for_optional_partial_sources():
    checks = [
        {"key": "platform_summary", "status": "ready"},
        {"key": "news", "status": "partial"},
        {"key": "research_reports", "status": "ready"},
    ]

    assert readiness.aggregate_readiness_status(checks) == "PARTIAL"


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
        "_has_public_news",
        lambda: True,
    )
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness(score_version="manual_v1")

    assert payload["mode"] == "eod_local"
    assert payload["status"] == "OK"
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

    def failing_news():
        raise RuntimeError("news db offline")

    monkeypatch.setattr(readiness, "_has_public_news", failing_news)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: False)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: False)

    payload = readiness.build_platform_readiness(score_version="manual_v1")

    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["status"] == "PARTIAL"
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
        "_has_public_news",
        lambda: True,
    )
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness()

    for check in payload["checks"]:
        assert set(check) == {"key", "label", "status", "detail"}


def test_build_platform_readiness_platform_summary_exception_is_stable_missing_data(
    monkeypatch,
):
    def failing_summary(score_version, top_n):
        raise RuntimeError("database password leaked")

    monkeypatch.setattr(readiness, "load_platform_summary", failing_summary)

    payload = readiness.build_platform_readiness()

    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["status"] == "BLOCKED"
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
    assert payload["status"] == "BLOCKED"
    assert checks["platform_summary"]["status"] == "missing_data"
    assert checks["review_queue"]["status"] == "unknown"
    assert payload["warnings"] == ["Platform summary unavailable"]


def test_build_platform_readiness_missing_topn_is_missing_data(
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
        "_has_public_news",
        lambda: True,
    )
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness()

    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["status"] == "BLOCKED"
    assert checks["platform_summary"]["status"] == "missing_data"
    assert checks["platform_summary"]["detail"] == "TopN preview unavailable"
    assert checks["review_queue"]["status"] == "partial"
    assert payload["warnings"] == ["TopN preview unavailable", "Review Queue unavailable"]


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
        "_has_public_news",
        lambda: False,
    )
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: False)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: False)

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
        "_has_public_news",
        lambda: True,
    )
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness()

    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["review_queue"]["status"] == "ready"


def test_readiness_module_does_not_expose_full_dashboard_loaders():
    assert not hasattr(readiness, "load_public_news_for_dashboard")
    assert not hasattr(readiness, "load_research_report_summary")
    assert not hasattr(readiness, "load_report_links")


def test_public_news_probe_uses_bounded_select_one(monkeypatch):
    calls = []
    conn = object()

    monkeypatch.setattr(readiness, "connect", lambda service: _FakeConnectionContext(conn))

    def fake_fetch_all(active_conn, sql, params=None):
        calls.append({"conn": active_conn, "sql": sql, "params": params})
        return [{"exists": 1}]

    monkeypatch.setattr(readiness, "fetch_all", fake_fetch_all)

    assert readiness._has_public_news(service="svc") is True
    assert calls == [
        {
            "conn": conn,
            "sql": "SELECT 1 FROM research.news_event_source LIMIT 1",
            "params": None,
        }
    ]


def test_research_reports_probe_uses_bounded_select_one(monkeypatch):
    calls = []
    conn = object()

    monkeypatch.setattr(readiness, "connect", lambda service: _FakeConnectionContext(conn))

    def fake_fetch_all(active_conn, sql, params=None):
        calls.append({"conn": active_conn, "sql": sql, "params": params})
        return []

    monkeypatch.setattr(readiness, "fetch_all", fake_fetch_all)

    assert readiness._has_research_reports(service="svc") is False
    assert calls == [
        {
            "conn": conn,
            "sql": "SELECT 1 FROM research.stock_report_source LIMIT 1",
            "params": None,
        }
    ]


def test_generated_reports_probe_checks_only_direct_children(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "report-2026-06-12.html").write_text("nested", encoding="utf-8")

    assert readiness._has_generated_reports("2026-06-12", reports_dir=tmp_path) is False

    (tmp_path / "report-2026-06-12.md").write_text("direct", encoding="utf-8")

    assert readiness._has_generated_reports("2026-06-12", reports_dir=tmp_path) is True


def test_build_platform_readiness_v2_ok_from_manifest(monkeypatch):
    modules = [
        {
            "module": "daily_bars",
            "source": "market",
            "tier": "tier1",
            "status": "success",
            "row_count": 5200,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "score_topn",
            "source": "factor",
            "tier": "tier1",
            "status": "success",
            "row_count": 30,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "review_queue",
            "source": "dashboard",
            "tier": "tier1",
            "status": "success",
            "row_count": 20,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "news",
            "source": "public_news",
            "tier": "tier2",
            "status": "success",
            "row_count": 10,
            "warnings": [],
            "error_message": "",
        },
    ]
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )
    monkeypatch.setattr(readiness, "_has_public_news", lambda: True)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness()

    assert payload["status"] == "OK"
    assert payload["source"] == "data_run_manifest"
    assert payload["latest_trade_date"] == "2026-06-12"
    assert payload["tiers"][0]["status"] == "OK"
    assert payload["missing_data"] == []


def test_build_platform_readiness_v2_tier2_failure_is_partial(monkeypatch):
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "score_topn", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "review_queue", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "news", "tier": "tier2", "status": "failed", "warnings": ["news down"], "error_message": "news down"},
    ]
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )
    monkeypatch.setattr(readiness, "_has_public_news", lambda: False)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness()

    assert payload["status"] == "PARTIAL"
    assert "news" in payload["partial_data"]
    assert "news down" in payload["warnings"]


def test_build_platform_readiness_v2_tier1_failure_is_blocked(monkeypatch):
    modules = [
        {
            "module": "daily_bars",
            "tier": "tier1",
            "status": "failed",
            "warnings": [],
            "error_message": "market failed",
        },
        {
            "module": "score_topn",
            "tier": "tier1",
            "status": "unavailable",
            "warnings": [],
            "error_message": "no scores",
        },
    ]
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )
    monkeypatch.setattr(readiness, "_has_public_news", lambda: True)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness()

    assert payload["status"] == "BLOCKED"
    assert "daily_bars" in payload["missing_data"]
    assert "score_topn" in payload["missing_data"]
    assert any("market failed" in error for error in payload["errors"])


def test_build_platform_readiness_v2_missing_topn_blocks_even_with_manifest(monkeypatch):
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "score_topn", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "review_queue", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
    ]
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [],
        },
    )

    payload = readiness.build_platform_readiness()

    assert payload["status"] == "BLOCKED"
    assert "score_topn" in payload["missing_data"]
    assert "Review Queue unavailable" in payload["warnings"]


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
