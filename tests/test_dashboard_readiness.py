from fastapi.testclient import TestClient
import pytest

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import readiness


class _FakeConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def _disable_real_manifest_probe(monkeypatch):
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: [])


def _patch_market_monitor_ready(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "_market_monitor_check",
        lambda latest_market_date: readiness._check(
            "market_monitor",
            "ready",
            f"Market Monitor sources ready for {latest_market_date}",
        ),
    )


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
    _patch_market_monitor_ready(monkeypatch)

    payload = readiness.build_platform_readiness(score_version="manual_v1")

    assert payload["mode"] == "eod_local"
    assert payload["status"] == "OK"
    assert payload["latest_market_date"] == "2026-06-12"
    assert payload["as_of"].endswith("+08:00")
    assert {check["key"]: check["status"] for check in payload["checks"]} == {
        "platform_summary": "ready",
        "review_queue": "ready",
        "market_monitor": "ready",
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
    _patch_market_monitor_ready(monkeypatch)

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
    _patch_market_monitor_ready(monkeypatch)

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
    _patch_market_monitor_ready(monkeypatch)

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
    _patch_market_monitor_ready(monkeypatch)

    payload = readiness.build_platform_readiness()

    assert payload["warnings"] == [
        "News unavailable",
        "Research Reports unavailable",
        "Generated Reports unavailable",
    ]


def test_manifest_health_marks_news_data_available_when_manifest_module_missing(monkeypatch):
    monkeypatch.setattr(readiness, "_has_public_news", lambda: True)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: False)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: False)

    groups = readiness._build_manifest_health_groups(
        modules=[
            {
                "module": "daily_bars",
                "status": "success",
                "latest_trade_date": "2026-06-16",
                "row_count": 100,
            },
            {
                "module": "technical_features",
                "status": "success",
                "latest_trade_date": "2026-06-16",
                "row_count": 100,
            },
            {
                "module": "score_topn",
                "status": "success",
                "latest_trade_date": "2026-06-16",
                "row_count": 100,
            },
            {
                "module": "lhb_features",
                "status": "success",
                "latest_trade_date": "2026-06-16",
                "row_count": 10,
            },
        ],
        latest_market_date="2026-06-16",
        topn_preview=[{"asset_id": "CN:SZ:000001"}],
    )

    content = next(group for group in groups if group["key"] == "content_chain")
    news = next(item for item in content["items"] if item["key"] == "news")

    assert news["status"] == "partial"
    assert news["detail"] == "新闻数据可用；未写入当日日终 manifest"
    assert news["latest_trade_date"] == "2026-06-16"


def test_manifest_health_counts_market_monitor_source_ready_as_ready(monkeypatch):
    monkeypatch.setattr(readiness, "_market_monitor_ready", lambda latest_market_date: True)

    groups = readiness._build_manifest_health_groups(
        modules=[
            {
                "module": "daily_bars",
                "status": "success",
                "latest_trade_date": "2026-06-29",
                "row_count": 5187,
            },
            {
                "module": "technical_features",
                "status": "success",
                "latest_trade_date": "2026-06-29",
                "row_count": 5187,
            },
            {
                "module": "score_topn",
                "status": "success",
                "latest_trade_date": "2026-06-29",
                "row_count": 5187,
            },
            {
                "module": "lhb_features",
                "status": "success",
                "latest_trade_date": "2026-06-29",
                "row_count": 102,
            },
        ],
        latest_market_date="2026-06-29",
        topn_preview=[{"asset_id": "CN:SH:600519"}],
    )

    base_data = next(group for group in groups if group["key"] == "base_data")
    market_monitor = next(item for item in base_data["items"] if item["key"] == "market_monitor")
    assert market_monitor["status"] == "ready"
    assert base_data["ready_count"] == 5


def test_manifest_health_marks_content_sources_available_when_manifest_modules_missing(monkeypatch):
    monkeypatch.setattr(readiness, "_has_public_news", lambda: True)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: latest_market_date == "2026-06-18")

    groups = readiness._build_manifest_health_groups(
        modules=[
            {
                "module": "daily_bars",
                "status": "success",
                "latest_trade_date": "2026-06-18",
                "row_count": 100,
            },
            {
                "module": "score_topn",
                "status": "success",
                "latest_trade_date": "2026-06-18",
                "row_count": 20,
            },
        ],
        latest_market_date="2026-06-18",
        topn_preview=[{"asset_id": "CN:SZ:000001"}],
    )

    content = next(group for group in groups if group["key"] == "content_chain")
    items = {item["key"]: item for item in content["items"]}

    assert items["news"]["status"] == "partial"
    assert items["news"]["detail"] == "新闻数据可用；未写入当日日终 manifest"
    assert items["research_reports"]["status"] == "partial"
    assert items["research_reports"]["detail"] == "研报数据可用；未写入当日日终 manifest"
    assert items["generated_reports"]["status"] == "partial"
    assert items["generated_reports"]["detail"] == "生成报告可用；未写入当日日终 manifest"


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
    _patch_market_monitor_ready(monkeypatch)

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


def test_market_monitor_check_uses_bounded_source_counts(monkeypatch):
    calls = []
    conn = object()

    monkeypatch.setattr(readiness, "connect", lambda service: _FakeConnectionContext(conn))

    def fake_fetch_all(active_conn, sql, params=None):
        calls.append({"conn": active_conn, "sql": sql, "params": params})
        return [{"industry_rows": 31, "index_rows": 5, "market_daily_rows": 5191}]

    monkeypatch.setattr(readiness, "fetch_all", fake_fetch_all)

    check = readiness._market_monitor_check("2026-06-26", service="svc")

    assert check == {
        "key": "market_monitor",
        "label": "Market Monitor",
        "status": "ready",
        "detail": "Market Monitor sources ready for 2026-06-26",
    }
    assert calls == [
        {
            "conn": conn,
            "sql": readiness.MARKET_MONITOR_SOURCE_COUNT_SQL,
            "params": ["2026-06-26", "2026-06-26", "2026-06-26"],
        }
    ]


def test_market_monitor_check_requires_all_required_indices(monkeypatch):
    monkeypatch.setattr(readiness, "connect", lambda service: _FakeConnectionContext(object()))
    monkeypatch.setattr(
        readiness,
        "fetch_all",
        lambda conn, sql, params=None: [
            {"industry_rows": 31, "index_rows": 3, "market_daily_rows": 5191}
        ],
    )

    check = readiness._market_monitor_check("2026-06-26", service="svc")

    assert check["status"] == "partial"
    assert check["detail"] == "Market Monitor missing index_daily_bar>=5"


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
            "module": "technical_features",
            "source": "factor",
            "tier": "tier1",
            "status": "success",
            "row_count": 5200,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "lhb_features",
            "source": "factor",
            "tier": "tier1",
            "status": "success",
            "row_count": 85,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "market_monitor",
            "source": "dashboard",
            "tier": "tier1",
            "status": "success",
            "row_count": 31,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "strategy_lhb_shortline",
            "source": "strategy",
            "tier": "tier1",
            "status": "success",
            "row_count": 5,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "strategy_mid_trend",
            "source": "strategy",
            "tier": "tier1",
            "status": "success",
            "row_count": 5,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "strategy_tech_bottleneck",
            "source": "strategy",
            "tier": "tier1",
            "status": "success",
            "row_count": 5,
            "warnings": [],
            "error_message": "",
            "metadata": {"candidate_snapshot_latest_date": "2026-06-12"},
        },
        {
            "module": "tech_bottleneck_candidates",
            "source": "point_in_time_daily_candidates",
            "tier": "tier1",
            "status": "success",
            "row_count": 153,
            "warnings": [],
            "error_message": "",
            "metadata": {"candidate_snapshot_latest_date": "2026-06-12"},
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
            "module": "review_queue_strategy_manifest",
            "source": "dashboard",
            "tier": "tier1",
            "status": "success",
            "row_count": 20,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "review_evidence_snapshots",
            "source": "dashboard",
            "tier": "tier2",
            "status": "success",
            "row_count": 15,
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
        {
            "module": "news_features",
            "source": "news_feature_daily",
            "tier": "tier2",
            "status": "success",
            "row_count": 5,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "news_enrichment",
            "source": "topn_news_enrichment",
            "tier": "tier2",
            "status": "success",
            "row_count": 5,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "research_reports",
            "source": "research",
            "tier": "tier2",
            "status": "success",
            "row_count": 8,
            "warnings": [],
            "error_message": "",
        },
        {
            "module": "generated_reports",
            "source": "reports",
            "tier": "tier2",
            "status": "success",
            "row_count": 2,
            "warnings": [],
            "error_message": "",
        },
    ]
    for module in modules:
        module["trade_date"] = "2026-06-12"
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
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
    health_groups = {group["key"]: group for group in payload["health_groups"]}
    assert list(health_groups) == ["base_data", "strategy_execution", "review_chain", "content_chain"]
    assert health_groups["base_data"]["ready_count"] == 5
    assert [item["label"] for item in health_groups["base_data"]["items"]] == [
        "日线",
        "因子",
        "评分",
        "Market Monitor",
        "龙虎榜",
    ]
    assert health_groups["strategy_execution"]["ready_count"] == 3
    assert [item["label"] for item in health_groups["strategy_execution"]["items"]] == [
        "LHB",
        "Mid Trend",
        "Tech Bottleneck",
    ]
    assert health_groups["review_chain"]["ready_count"] == 3
    assert [item["label"] for item in health_groups["review_chain"]["items"]] == [
        "Review Queue",
        "Evidence Digest",
        "Stock Workspace",
    ]
    assert health_groups["content_chain"]["ready_count"] == 5
    assert [item["label"] for item in health_groups["content_chain"]["items"]] == [
        "News",
        "News Features",
        "News Enrichment",
        "Research Reports",
        "Generated Reports",
    ]


def test_readiness_includes_display_date_gate(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-18",
            "topn_preview": [{"asset_id": "A"}],
        },
    )
    monkeypatch.setattr(
        readiness,
        "_load_manifest_modules",
        lambda: [
            {
                "run_id": "r1",
                "trade_date": "2026-06-17",
                "module": "daily_bars",
                "status": "success",
            },
        ],
    )
    monkeypatch.setattr(
        readiness,
        "select_display_date",
        lambda modules, latest_market_date, **kwargs: {
            "display_trade_date": "2026-06-17",
            "latest_market_date": latest_market_date,
            "candidate_trade_date": "2026-06-18",
            "display_status": "ready",
            "candidate_status": "before_cutoff",
            "strategy_ready": "3/3",
            "contract_valid": "3/3",
            "blocking_reasons": [],
        },
    )

    payload = readiness.build_platform_readiness()

    assert payload["display_trade_date"] == "2026-06-17"
    assert payload["candidate_trade_date"] == "2026-06-18"
    assert payload["display_gate"]["candidate_status"] == "before_cutoff"


def test_manifest_readiness_reports_display_trade_date_run_when_recent_manifest_contains_history(monkeypatch):
    modules = [
        {"run_id": "r1", "trade_date": "2026-06-17", "module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"run_id": "r1", "trade_date": "2026-06-17", "module": "strategy_tech_bottleneck", "tier": "tier1", "status": "failed", "warnings": [], "error_message": "old failure"},
        {"run_id": "r2", "trade_date": "2026-06-18", "module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"run_id": "r2", "trade_date": "2026-06-18", "module": "technical_features", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"run_id": "r2", "trade_date": "2026-06-18", "module": "score_topn", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"run_id": "r2", "trade_date": "2026-06-18", "module": "lhb_features", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"run_id": "r2", "trade_date": "2026-06-18", "module": "strategy_lhb_shortline", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"run_id": "r2", "trade_date": "2026-06-18", "module": "strategy_mid_trend", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"run_id": "r2", "trade_date": "2026-06-18", "module": "strategy_tech_bottleneck", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"run_id": "r2", "trade_date": "2026-06-18", "module": "review_queue_strategy_manifest", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
    ]
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-18",
            "topn_preview": [{"asset_id": "A"}],
        },
    )
    monkeypatch.setattr(readiness, "_load_manifest_modules", lambda: modules)
    monkeypatch.setattr(
        readiness,
        "select_display_date",
        lambda manifest_modules, latest_market_date, **kwargs: {
            "display_trade_date": "2026-06-18",
            "latest_market_date": latest_market_date,
            "candidate_trade_date": "2026-06-18",
            "display_status": "ready",
            "candidate_status": "ready",
            "strategy_ready": "3/3",
            "contract_valid": "3/3",
            "blocking_reasons": [],
        },
    )

    payload = readiness.build_platform_readiness()

    assert payload["run_id"] == "r2"
    assert {item["run_id"] for item in payload["modules"]} == {"r2"}
    assert payload["errors"] == []
    health_groups = {group["key"]: group for group in payload["health_groups"]}
    assert health_groups["strategy_execution"]["ready_count"] == 3


def test_display_gate_failure_blocks_manifest_readiness(monkeypatch):
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "technical_features", "tier": "tier1", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "score_topn", "tier": "tier1", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "lhb_features", "tier": "tier1", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "strategy_lhb_shortline", "tier": "tier1", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "strategy_mid_trend", "tier": "tier1", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "strategy_tech_bottleneck", "tier": "tier1", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "review_queue", "tier": "tier1", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "review_evidence_snapshots", "tier": "tier2", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "news", "tier": "tier2", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "research_reports", "tier": "tier2", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
        {"module": "generated_reports", "tier": "tier2", "status": "success", "trade_date": "2026-06-12", "warnings": [], "error_message": ""},
    ]
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
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

    assert payload["display_trade_date"] == ""
    assert payload["display_gate"]["candidate_status"] == "incomplete"
    assert payload["status"] == "BLOCKED"
    assert "display_trade_date" in payload["missing_data"]
    assert any(
        warning.startswith("Display trade date unavailable: incomplete")
        for warning in payload["warnings"]
    )


def test_build_platform_readiness_v2_tier2_failure_is_partial(monkeypatch):
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "technical_features", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "lhb_features", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "score_topn", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "strategy_lhb_shortline", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "strategy_mid_trend", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {
            "module": "strategy_tech_bottleneck",
            "tier": "tier1",
            "status": "success",
            "warnings": [],
            "error_message": "",
            "metadata": {"candidate_snapshot_latest_date": "2026-06-12"},
        },
        {
            "module": "tech_bottleneck_candidates",
            "tier": "tier1",
            "status": "success",
            "warnings": [],
            "error_message": "",
            "metadata": {"candidate_snapshot_latest_date": "2026-06-12"},
        },
        {"module": "review_queue", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "review_queue_strategy_manifest", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "review_evidence_snapshots", "tier": "tier2", "status": "success", "warnings": [], "error_message": ""},
        {"module": "news", "tier": "tier2", "status": "failed", "warnings": ["news down"], "error_message": "news down"},
        {"module": "research_reports", "tier": "tier2", "status": "success", "warnings": [], "error_message": ""},
        {"module": "generated_reports", "tier": "tier2", "status": "success", "warnings": [], "error_message": ""},
    ]
    for module in modules:
        module["trade_date"] = "2026-06-12"
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
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
    _patch_market_monitor_ready(monkeypatch)

    payload = readiness.build_platform_readiness()

    assert payload["status"] == "PARTIAL"
    assert "news" in payload["partial_data"]
    assert "news down" in payload["warnings"]


def test_build_platform_readiness_v2_snapshot_failure_is_partial(monkeypatch):
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "technical_features", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "lhb_features", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "score_topn", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "strategy_lhb_shortline", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "strategy_mid_trend", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {
            "module": "strategy_tech_bottleneck",
            "tier": "tier1",
            "status": "success",
            "warnings": [],
            "error_message": "",
            "metadata": {"candidate_snapshot_latest_date": "2026-06-12"},
        },
        {
            "module": "tech_bottleneck_candidates",
            "tier": "tier1",
            "status": "success",
            "warnings": [],
            "error_message": "",
            "metadata": {"candidate_snapshot_latest_date": "2026-06-12"},
        },
        {"module": "review_queue", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "review_queue_strategy_manifest", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {
            "module": "review_evidence_snapshots",
            "tier": "tier2",
            "status": "failed",
            "warnings": ["snapshot db offline"],
            "error_message": "snapshot db offline",
        },
        {"module": "news", "tier": "tier2", "status": "success", "warnings": [], "error_message": ""},
        {"module": "news_features", "tier": "tier2", "status": "success", "warnings": [], "error_message": ""},
        {"module": "news_enrichment", "tier": "tier2", "status": "success", "warnings": [], "error_message": ""},
        {"module": "research_reports", "tier": "tier2", "status": "success", "warnings": [], "error_message": ""},
        {"module": "generated_reports", "tier": "tier2", "status": "success", "warnings": [], "error_message": ""},
    ]
    for module in modules:
        module["trade_date"] = "2026-06-12"
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-06-12",
            "topn_preview": [{"asset_id": "CN:SH:600519"}],
        },
    )
    _patch_market_monitor_ready(monkeypatch)

    payload = readiness.build_platform_readiness()

    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["status"] == "PARTIAL"
    assert payload["tiers"][0]["status"] == "OK"
    assert "review_evidence_snapshots" in payload["partial_data"]
    assert checks["review_evidence_snapshots"]["status"] == "partial"
    assert checks["review_evidence_snapshots"]["detail"] == "Review/Evidence Snapshots unavailable"
    assert payload["next_actions"] == [
        "Review partial auxiliary data: review_evidence_snapshots"
    ]


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
