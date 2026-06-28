from datetime import date

from fastapi.testclient import TestClient
from psycopg import errors as psycopg_errors
import pytest

from stock_research import cli
from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import shadow_outcomes


def test_strategy_score_audit_route_returns_payload(monkeypatch):
    captured = {}

    def fake_load_strategy_score_audit_payload(*, trade_date: str):
        captured["trade_date"] = trade_date
        return {
            "trade_date": trade_date,
            "status": "success",
            "overall_status": "ok",
            "total_rows": 3,
            "selected_rows": 3,
            "anomaly_row_count": 0,
            "anomaly_counts_by_type": {},
            "strategies": [],
            "warnings": [],
        }

    monkeypatch.setattr(
        dashboard_app,
        "load_strategy_score_audit_payload",
        fake_load_strategy_score_audit_payload,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/strategy-score-audit?trade_date=2026-06-22")

    assert response.status_code == 200
    assert captured["trade_date"] == "2026-06-22"
    assert response.json() == {
        "trade_date": "2026-06-22",
        "status": "success",
        "overall_status": "ok",
        "total_rows": 3,
        "selected_rows": 3,
        "anomaly_row_count": 0,
        "anomaly_counts_by_type": {},
        "strategies": [],
        "warnings": [],
    }


def test_overview_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_dashboard_overview",
        lambda trade_date, score_version, watchlist_id, top_n: {
            "trade_date": trade_date,
            "score_version": score_version,
            "watchlist_id": watchlist_id,
            "top_scores": [],
            "watchlist_signals": [],
            "reports": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/dashboard/overview?trade_date=2026-05-29")

    assert response.status_code == 200
    assert response.json()["trade_date"] == "2026-05-29"


def test_market_monitor_overview_route_returns_payload(monkeypatch):
    captured = {}

    def fake_build_market_overview_payload(trade_date: str):
        captured["trade_date"] = trade_date
        return {
            "trade_date": trade_date,
            "updated_at": "2026-06-26T15:31:00+08:00",
            "source": "market_overview",
            "data_status": "completed",
            "warnings": [],
            "indices": [
                {
                    "code": "SSE_COMPOSITE",
                    "name": "上证指数",
                    "close": 3123.45,
                    "change_pct": 0.0079,
                }
            ],
            "total_amount": 1280000000000.0,
            "up_count": 3210,
            "down_count": 1765,
            "limit_up_count": 82,
            "limit_down_count": 9,
        }

    monkeypatch.setattr(
        dashboard_app,
        "build_market_overview_payload",
        fake_build_market_overview_payload,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/market-monitor/overview?trade_date=2026-06-26")

    assert response.status_code == 200
    assert captured == {"trade_date": "2026-06-26"}
    assert response.json() == {
        "trade_date": "2026-06-26",
        "updated_at": "2026-06-26T15:31:00+08:00",
        "source": "market_overview",
        "data_status": "completed",
        "warnings": [],
        "indices": [
            {
                "code": "SSE_COMPOSITE",
                "name": "上证指数",
                "close": 3123.45,
                "change_pct": 0.0079,
            }
        ],
        "total_amount": 1280000000000.0,
        "up_count": 3210,
        "down_count": 1765,
        "limit_up_count": 82,
        "limit_down_count": 9,
    }


def test_market_monitor_sectors_heatmap_route_returns_payload(monkeypatch):
    captured = {}

    def fake_build_sector_heatmap_payload(trade_date: str, *, sector_type: str = "industry"):
        captured["trade_date"] = trade_date
        captured["sector_type"] = sector_type
        return {
            "trade_date": trade_date,
            "updated_at": "2026-06-26T15:35:00+08:00",
            "source": "market.industry_daily_bar",
            "data_status": "completed",
            "warnings": [],
            "items": [
                {
                    "sector_id": "BK0428",
                    "sector_name": "半导体",
                    "sector_type": sector_type,
                    "change_pct": 0.05,
                    "amount": 88000000000.0,
                    "up_count": 41,
                    "down_count": 9,
                    "main_net_inflow": None,
                    "stock_count": 52,
                }
            ],
        }

    monkeypatch.setattr(
        dashboard_app,
        "build_sector_heatmap_payload",
        fake_build_sector_heatmap_payload,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/market-monitor/sectors/heatmap?trade_date=2026-06-26&type=industry")

    assert response.status_code == 200
    assert captured == {"trade_date": "2026-06-26", "sector_type": "industry"}
    assert response.json() == {
        "trade_date": "2026-06-26",
        "updated_at": "2026-06-26T15:35:00+08:00",
        "source": "market.industry_daily_bar",
        "data_status": "completed",
        "warnings": [],
        "items": [
            {
                "sector_id": "BK0428",
                "sector_name": "半导体",
                "sector_type": "industry",
                "change_pct": 0.05,
                "amount": 88000000000.0,
                "up_count": 41,
                "down_count": 9,
                "main_net_inflow": None,
                "stock_count": 52,
            }
        ],
    }


def test_market_monitor_sectors_fund_flow_route_returns_payload(monkeypatch):
    captured = {}

    def fake_build_sector_fund_flow_payload(
        trade_date: str,
        *,
        sector_type: str = "industry",
        period: str = "1d",
    ):
        captured["trade_date"] = trade_date
        captured["sector_type"] = sector_type
        captured["period"] = period
        return {
            "trade_date": trade_date,
            "updated_at": None,
            "source": "third_party_fund_flow_signal",
            "data_status": "missing",
            "warnings": [
                "fund flow source is unavailable; returning empty directional signal payload"
            ],
            "inflow": [],
            "outflow": [],
        }

    monkeypatch.setattr(
        dashboard_app,
        "build_sector_fund_flow_payload",
        fake_build_sector_fund_flow_payload,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/market-monitor/sectors/fund-flow?trade_date=2026-06-26&type=industry&period=1d"
    )

    assert response.status_code == 200
    assert captured == {
        "trade_date": "2026-06-26",
        "sector_type": "industry",
        "period": "1d",
    }
    assert response.json() == {
        "trade_date": "2026-06-26",
        "updated_at": None,
        "source": "third_party_fund_flow_signal",
        "data_status": "missing",
        "warnings": [
            "fund flow source is unavailable; returning empty directional signal payload"
        ],
        "inflow": [],
        "outflow": [],
    }


def test_market_monitor_sectors_detail_route_returns_payload(monkeypatch):
    captured = {}

    def fake_build_sector_detail_payload(
        trade_date: str,
        sector_id: str,
        *,
        sector_type: str = "industry",
    ):
        captured["trade_date"] = trade_date
        captured["sector_id"] = sector_id
        captured["sector_type"] = sector_type
        return {
            "trade_date": trade_date,
            "updated_at": "2026-06-26T15:36:00+08:00",
            "source": "market.industry_daily_bar",
            "data_status": "partial",
            "warnings": [
                "fund flow fields are unavailable for sector detail; returning partial payload"
            ],
            "sector_id": sector_id,
            "sector_name": "半导体",
            "sector_type": sector_type,
            "change_pct": 0.05,
            "amount": 88000000000.0,
            "up_count": 41,
            "down_count": 9,
            "main_net_inflow": None,
            "main_net_inflow_ratio": None,
            "stock_count": 52,
            "leading_stocks": [
                {
                    "asset_id": "688256.SH",
                    "name": "寒武纪",
                    "change_pct": 0.125,
                }
            ],
        }

    monkeypatch.setattr(
        dashboard_app,
        "build_sector_detail_payload",
        fake_build_sector_detail_payload,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/market-monitor/sectors/BK0428?trade_date=2026-06-26&type=industry")

    assert response.status_code == 200
    assert captured == {
        "trade_date": "2026-06-26",
        "sector_id": "BK0428",
        "sector_type": "industry",
    }
    assert response.json() == {
        "trade_date": "2026-06-26",
        "updated_at": "2026-06-26T15:36:00+08:00",
        "source": "market.industry_daily_bar",
        "data_status": "partial",
        "warnings": [
            "fund flow fields are unavailable for sector detail; returning partial payload"
        ],
        "sector_id": "BK0428",
        "sector_name": "半导体",
        "sector_type": "industry",
        "change_pct": 0.05,
        "amount": 88000000000.0,
        "up_count": 41,
        "down_count": 9,
        "main_net_inflow": None,
        "main_net_inflow_ratio": None,
        "stock_count": 52,
        "leading_stocks": [
            {
                "asset_id": "688256.SH",
                "name": "寒武纪",
                "change_pct": 0.125,
            }
        ],
    }


def test_market_monitor_sectors_detail_route_passes_concept_type(monkeypatch):
    captured = {}

    def fake_build_sector_detail_payload(
        trade_date: str,
        sector_id: str,
        *,
        sector_type: str = "industry",
    ):
        captured["trade_date"] = trade_date
        captured["sector_id"] = sector_id
        captured["sector_type"] = sector_type
        return {
            "trade_date": trade_date,
            "updated_at": None,
            "source": "concept_sector_source",
            "data_status": "missing",
            "warnings": ["concept sector detail source is unavailable; returning empty payload"],
            "sector_id": sector_id,
            "sector_name": sector_id,
            "sector_type": sector_type,
            "change_pct": None,
            "amount": None,
            "up_count": None,
            "down_count": None,
            "main_net_inflow": None,
            "main_net_inflow_ratio": None,
            "stock_count": None,
            "leading_stocks": [],
        }

    monkeypatch.setattr(
        dashboard_app,
        "build_sector_detail_payload",
        fake_build_sector_detail_payload,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/market-monitor/sectors/GN1234?trade_date=2026-06-26&type=concept")

    assert response.status_code == 200
    assert captured == {
        "trade_date": "2026-06-26",
        "sector_id": "GN1234",
        "sector_type": "concept",
    }
    assert response.json() == {
        "trade_date": "2026-06-26",
        "updated_at": None,
        "source": "concept_sector_source",
        "data_status": "missing",
        "warnings": ["concept sector detail source is unavailable; returning empty payload"],
        "sector_id": "GN1234",
        "sector_name": "GN1234",
        "sector_type": "concept",
        "change_pct": None,
        "amount": None,
        "up_count": None,
        "down_count": None,
        "main_net_inflow": None,
        "main_net_inflow_ratio": None,
        "stock_count": None,
        "leading_stocks": [],
    }


@pytest.mark.parametrize(
    ("route", "builder_name"),
    [
        ("/api/market-monitor/sectors/heatmap?trade_date=2026-06-26&type=foo", "build_sector_heatmap_payload"),
        (
            "/api/market-monitor/sectors/fund-flow?trade_date=2026-06-26&type=foo&period=1d",
            "build_sector_fund_flow_payload",
        ),
        ("/api/market-monitor/sectors/BK0428?trade_date=2026-06-26&type=foo", "build_sector_detail_payload"),
    ],
)
def test_market_monitor_sectors_routes_reject_invalid_type_before_builder(monkeypatch, route, builder_name):
    calls = []

    def fake_builder(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"unexpected": True}

    monkeypatch.setattr(dashboard_app, builder_name, fake_builder, raising=False)
    client = TestClient(dashboard_app.create_app())

    response = client.get(route)

    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize(
    ("route", "builder_name"),
    [
        ("/api/platform/summary?score_version=manual_v1&top_n=5", "load_platform_summary"),
        ("/api/market-monitor/eod?trade_date=2026-06-12&score_version=manual_v1&top_n=5", "build_market_monitor_eod"),
        ("/api/review-queue?trade_date=2026-06-12&score_version=manual_v1&limit=10&lookback_days=90", "build_review_queue"),
    ],
)
def test_dashboard_eod_routes_cache_repeated_identical_requests(monkeypatch, route, builder_name):
    calls = []

    def fake_builder(**kwargs):
        calls.append(dict(kwargs))
        return {"builder": builder_name, "calls": len(calls), "kwargs": kwargs}

    monkeypatch.setattr(dashboard_app, builder_name, fake_builder, raising=False)
    client = TestClient(dashboard_app.create_app())

    first = client.get(route)
    second = client.get(route)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(calls) == 1
    assert first.json() == second.json()


def test_dashboard_eod_route_cache_keys_include_query_parameters(monkeypatch):
    calls = []

    def fake_summary(**kwargs):
        calls.append(dict(kwargs))
        return {"calls": len(calls), "kwargs": kwargs}

    monkeypatch.setattr(dashboard_app, "load_platform_summary", fake_summary, raising=False)
    client = TestClient(dashboard_app.create_app())

    first = client.get("/api/platform/summary?score_version=manual_v1&top_n=5")
    second = client.get("/api/platform/summary?score_version=manual_v1&top_n=10")
    third = client.get("/api/platform/summary?score_version=manual_v1&top_n=5")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert len(calls) == 2
    assert first.json() == third.json()
    assert first.json() != second.json()


def test_market_monitor_sectors_heatmap_route_reuses_cache_for_identical_requests(monkeypatch):
    calls = []

    def fake_heatmap_builder(trade_date: str, *, sector_type: str = "industry"):
        calls.append({"trade_date": trade_date, "sector_type": sector_type})
        return {"calls": len(calls), "trade_date": trade_date, "sector_type": sector_type}

    monkeypatch.setattr(
        dashboard_app,
        "build_sector_heatmap_payload",
        fake_heatmap_builder,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    first = client.get("/api/market-monitor/sectors/heatmap?trade_date=2026-06-26&type=industry")
    second = client.get("/api/market-monitor/sectors/heatmap?trade_date=2026-06-26&type=industry")

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(calls) == 1
    assert first.json() == second.json()


def test_market_monitor_sectors_fund_flow_route_separates_cache_by_period(monkeypatch):
    calls = []

    def fake_fund_flow_builder(
        trade_date: str,
        *,
        sector_type: str = "industry",
        period: str = "1d",
    ):
        calls.append(
            {
                "trade_date": trade_date,
                "sector_type": sector_type,
                "period": period,
            }
        )
        return {"calls": len(calls), "trade_date": trade_date, "sector_type": sector_type, "period": period}

    monkeypatch.setattr(
        dashboard_app,
        "build_sector_fund_flow_payload",
        fake_fund_flow_builder,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    first = client.get("/api/market-monitor/sectors/fund-flow?trade_date=2026-06-26&type=industry&period=1d")
    second = client.get("/api/market-monitor/sectors/fund-flow?trade_date=2026-06-26&type=industry&period=5d")
    third = client.get("/api/market-monitor/sectors/fund-flow?trade_date=2026-06-26&type=industry&period=1d")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert len(calls) == 2
    assert first.json() == third.json()
    assert first.json() != second.json()


def test_market_monitor_sectors_detail_route_separates_cache_by_type(monkeypatch):
    calls = []

    def fake_detail_builder(
        trade_date: str,
        sector_id: str,
        *,
        sector_type: str = "industry",
    ):
        calls.append(
            {
                "trade_date": trade_date,
                "sector_id": sector_id,
                "sector_type": sector_type,
            }
        )
        return {
            "calls": len(calls),
            "trade_date": trade_date,
            "sector_id": sector_id,
            "sector_type": sector_type,
        }

    monkeypatch.setattr(
        dashboard_app,
        "build_sector_detail_payload",
        fake_detail_builder,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    first = client.get("/api/market-monitor/sectors/BK0428?trade_date=2026-06-26&type=industry")
    second = client.get("/api/market-monitor/sectors/BK0428?trade_date=2026-06-26&type=concept")
    third = client.get("/api/market-monitor/sectors/BK0428?trade_date=2026-06-26&type=industry")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert len(calls) == 2
    assert first.json() == third.json()
    assert first.json() != second.json()


def test_platform_display_date_route_returns_readiness_gate(monkeypatch):
    calls = []

    def fake_readiness(score_version="manual_v1"):
        calls.append(score_version)
        return {
            "status": "OK",
            "latest_trade_date": "2026-06-18",
            "latest_market_date": "2026-06-18",
            "display_trade_date": "2026-06-17",
            "candidate_trade_date": "2026-06-18",
            "display_gate": {
                "display_trade_date": "2026-06-17",
                "candidate_trade_date": "2026-06-18",
                "candidate_status": "before_cutoff",
            },
            "warnings": ["before 20:30"],
        }

    monkeypatch.setattr(dashboard_app, "build_platform_readiness", fake_readiness, raising=False)
    client = TestClient(dashboard_app.create_app())

    first = client.get("/api/platform/display-date?score_version=manual_v1")
    second = client.get("/api/platform/display-date?score_version=manual_v1")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls == ["manual_v1"]
    assert first.json() == {
        "display_trade_date": "2026-06-17",
        "candidate_trade_date": "2026-06-18",
        "latest_market_date": "2026-06-18",
        "status": "OK",
        "display_gate": {
            "display_trade_date": "2026-06-17",
            "candidate_trade_date": "2026-06-18",
            "candidate_status": "before_cutoff",
        },
        "warnings": ["before 20:30"],
    }


def test_platform_display_date_route_preserves_blocked_empty_display_date(monkeypatch):
    def fake_readiness(score_version="manual_v1"):
        return {
            "status": "BLOCKED",
            "latest_trade_date": "2026-06-17",
            "latest_market_date": "2026-06-17",
            "display_trade_date": "",
            "candidate_trade_date": "2026-06-17",
            "display_gate": {
                "display_trade_date": "",
                "candidate_trade_date": "2026-06-17",
                "candidate_status": "contract_mismatch",
            },
            "warnings": ["contract mismatch"],
        }

    monkeypatch.setattr(dashboard_app, "build_platform_readiness", fake_readiness, raising=False)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/display-date")

    assert response.status_code == 200
    assert response.json()["display_trade_date"] == ""
    assert response.json()["candidate_trade_date"] == "2026-06-17"
    assert response.json()["status"] == "BLOCKED"


def test_public_news_route_returns_filtered_items(monkeypatch):
    captured = {}

    def fake_load_public_news(**kwargs):
        captured.update(kwargs)
        return {
            "items": [{"news_id": "news-1", "title": "全球快讯", "category": "live"}],
            "warnings": [],
        }

    monkeypatch.setattr(dashboard_app, "load_public_news_for_dashboard", fake_load_public_news)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/public-news?source=sina_finance&category=live&q=%E5%BF%AB%E8%AE%AF"
        "&start_time=2026-06-01T00:00:00&end_time=2026-06-12T23:59:59"
        "&asset_id=CN:SH:600519&ts_code=600519.SH&min_quality_score=70&limit=10&offset=2"
    )

    assert response.status_code == 200
    assert captured == {
        "source": "sina_finance",
        "category": "live",
        "q": "快讯",
        "start_time": "2026-06-01T00:00:00",
        "end_time": "2026-06-12T23:59:59",
        "asset_id": "CN:SH:600519",
        "ts_code": "600519.SH",
        "min_quality_score": 70,
        "limit": 10,
        "offset": 2,
    }
    assert response.json()["items"][0]["title"] == "全球快讯"


def test_public_news_refresh_route_returns_counts(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "refresh_public_news_for_dashboard",
        lambda: {
            "received": 2,
            "stored": 2,
            "items_received": 2,
            "counts_by_category": {"live": 2},
            "warnings": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/public-news/refresh")

    assert response.status_code == 200
    assert response.json()["counts_by_category"] == {"live": 2}


def test_public_news_status_endpoint(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PUBLIC_NEWS_SCHEDULER", "0")
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/public-news/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["running"] is False
    assert payload["interval_seconds"] == 1800
    assert payload["last_success_at"] == ""
    assert payload["last_error"] == ""
    assert payload["next_run_at"] == ""


def test_evidence_digest_route_returns_lineage_shape(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_evidence_digest",
        lambda asset_id, *, trade_date=None, lookback_days=90, score_version="manual_v1": {
            "asset_id": asset_id,
            "canonical_asset_id": asset_id,
            "stock_code": asset_id,
            "stock_name": "平安银行",
            "trade_date": trade_date,
            "latest_trade_date": trade_date,
            "run_id": "eod-2026-06-12-local",
            "digest_key": f"{trade_date}:{score_version}:{asset_id}",
            "generated_at": f"{trade_date}T00:00:00+00:00",
            "overall_status": "PARTIAL",
            "title": "Mixed evidence",
            "score": 62,
            "bucket": "mixed",
            "sections": {
                "news": {
                    "status": "missing",
                    "as_of": trade_date,
                    "source": "public_news",
                    "item_count": 0,
                    "warnings": [],
                    "error_message": "",
                    "data": {},
                    "artifact_path": "",
                }
            },
            "missing_evidence": ["news"],
            "partial_evidence": [],
            "lineage": {"run_id": "eod-2026-06-12-local", "score_version": score_version},
            "errors": [],
            "facts": [],
            "risk_flags": [],
            "source_refs": {},
            "next_actions": [],
            "warnings": [],
        },
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/evidence-digest?asset_id=000001.SZ&trade_date=2026-06-12&lookback_days=30&score_version=manual_v1"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["digest_key"] == "2026-06-12:manual_v1:000001.SZ"
    assert payload["overall_status"] == "PARTIAL"
    assert payload["sections"]["news"]["status"] == "missing"


def test_review_queue_route_returns_lineage_shape(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_review_queue",
        lambda *, trade_date=None, score_version="manual_v1", limit=20, lookback_days=90: {
            "trade_date": trade_date,
            "score_version": score_version,
            "generated_at": f"{trade_date}T00:00:00+00:00",
            "groups": [
                {
                    "bucket": "mixed",
                    "label": "Mixed Evidence",
                    "count": 1,
                    "items": [
                        {
                            "queue_id": f"{trade_date}:{score_version}:000001.SZ",
                            "asset_id": "000001.SZ",
                            "canonical_asset_id": "000001.SZ",
                            "trade_date": trade_date,
                            "latest_trade_date": trade_date,
                            "run_id": "eod-2026-06-12-local",
                            "generated_at": f"{trade_date}T00:00:00+00:00",
                            "score_version": score_version,
                            "display_name": "平安银行",
                            "rank": 3,
                            "topn_rank": 3,
                            "score": 88.5,
                            "source_type": "score_topn",
                            "source_name": "manual_v1_topn",
                            "source_rank": 3,
                            "score_components": {},
                            "digest_key": f"{trade_date}:{score_version}:000001.SZ",
                            "digest_url_path": "/api/evidence-digest?asset_id=000001.SZ",
                            "stock_workspace_url_path": "/stock/000001.SZ?trade_date=2026-06-12",
                            "evidence_status": "PARTIAL",
                            "missing_evidence": ["news"],
                            "partial_evidence": [],
                            "missing_evidence_count": 1,
                            "partial_evidence_count": 0,
                            "warnings_count": 1,
                            "warnings": ["strategy_run_id unavailable for score_topn candidate"],
                            "manifest_modules": [],
                            "digest_title": "Mixed evidence",
                            "bucket": "mixed",
                            "source_kinds": [],
                            "risk_count": 0,
                            "warning_count": 0,
                            "next_action_count": 0,
                            "digest": {
                                "asset_id": "000001.SZ",
                                "canonical_asset_id": "000001.SZ",
                                "trade_date": trade_date,
                                "title": "Mixed evidence",
                                "score": 62,
                                "bucket": "mixed",
                                "facts": [],
                                "risk_flags": [],
                                "source_refs": {},
                                "next_actions": [],
                                "warnings": [],
                            },
                        }
                    ],
                }
            ],
            "warnings": [],
        },
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/review-queue?trade_date=2026-06-12&score_version=manual_v1")

    assert response.status_code == 200
    item = response.json()["groups"][0]["items"][0]
    assert item["digest_key"] == "2026-06-12:manual_v1:000001.SZ"
    assert item["source_type"] == "score_topn"
    assert item["missing_evidence_count"] == 1


def test_review_queue_snapshots_route_returns_filtered_items(monkeypatch):
    captured = {}

    def fake_list(**kwargs):
        captured.update(kwargs)
        return [{"snapshot_id": "review_item_snapshot:abc", "run_id": kwargs["run_id"]}]

    monkeypatch.setattr(dashboard_app, "list_review_item_snapshots", fake_list, raising=False)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/review-queue/snapshots?run_id=eod-2026-06-12-local&digest_key=2026-06-12%3Amanual_v1%3A000001.SZ"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "ops.review_item_snapshot"
    assert payload["items"][0]["snapshot_id"] == "review_item_snapshot:abc"
    assert captured["run_id"] == "eod-2026-06-12-local"
    assert captured["digest_key"] == "2026-06-12:manual_v1:000001.SZ"


def test_evidence_digest_snapshots_route_returns_filtered_items(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_evidence_digest_snapshots",
        lambda **kwargs: [{"snapshot_id": "evidence_digest_snapshot:def", "digest_key": kwargs["digest_key"]}],
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/evidence-digest/snapshots?digest_key=digest-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "ops.evidence_digest_snapshot"
    assert payload["items"][0]["digest_key"] == "digest-1"


def test_evidence_digest_snapshot_detail_route_returns_item(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_evidence_digest_snapshot",
        lambda snapshot_id: {"snapshot_id": snapshot_id, "digest_payload": {"digest_key": "digest-1"}},
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/evidence-digest/snapshots/evidence_digest_snapshot:def")

    assert response.status_code == 200
    assert response.json()["item"]["snapshot_id"] == "evidence_digest_snapshot:def"


def test_global_search_route_forwards_query(monkeypatch):
    captured = {}

    def fake_load_global_search(q, *, limit=5):
        captured["q"] = q
        captured["limit"] = limit
        return {
            "query": q,
            "groups": [{"key": "assets", "label": "Assets", "items": []}],
            "warnings": [],
        }

    monkeypatch.setattr(
        dashboard_app,
        "load_global_search",
        fake_load_global_search,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/search?q=maotai&limit=3")

    assert response.status_code == 200
    assert captured == {"q": "maotai", "limit": 3}
    assert response.json() == {
        "query": "maotai",
        "groups": [{"key": "assets", "label": "Assets", "items": []}],
        "warnings": [],
    }


def test_asset_news_endpoint(monkeypatch):
    from stock_research.dashboard import app as dashboard_app

    captured = {}

    def fake_load_asset_news(asset_id, **kwargs):
        captured["asset_id"] = asset_id
        captured.update(kwargs)
        return {
            "asset_id": asset_id,
            "items": [],
            "summary": {"news_count_1d": 0, "news_count_3d": 0, "news_count_7d": 0},
            "warnings": ["no matching public news items"],
        }

    monkeypatch.setattr(dashboard_app, "load_asset_news", fake_load_asset_news)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/CN:SH:600519/news"
        "?limit=5&lookback_days=7&category=company&source=sina_finance"
    )

    assert response.status_code == 200
    assert captured == {
        "asset_id": "CN:SH:600519",
        "limit": 5,
        "lookback_days": 7,
        "category": "company",
        "source": "sina_finance",
    }
    assert response.json()["asset_id"] == "CN:SH:600519"


def test_asset_detail_route_returns_404_for_missing_asset(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_asset_detail", lambda asset_id: None)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/assets/000001.SZ")

    assert response.status_code == 404
    assert response.json()["detail"] == "asset not found"


def test_minute_bars_route_passes_source(monkeypatch):
    captured = {}

    def fake_load_minute_bars(asset_id, start_time, end_time, freq, adjust_type, source):
        captured["args"] = [asset_id, start_time, end_time, freq, adjust_type, source]
        return [{"time": "2026-05-29 09:35:00"}]

    monkeypatch.setattr(dashboard_app, "load_minute_bars", fake_load_minute_bars)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/minute-bars"
        "?start_time=2026-05-29T09:30:00"
        "&end_time=2026-05-29T15:00:00"
        "&freq=5min"
        "&adjust_type=qfq"
        "&source=tushare"
    )

    assert response.status_code == 200
    assert captured["args"] == [
        "000001.SZ",
        "2026-05-29T09:30:00",
        "2026-05-29T15:00:00",
        "5min",
        "qfq",
        "tushare",
    ]
    assert response.json()["items"] == [{"time": "2026-05-29 09:35:00"}]


def test_asset_bars_route_passes_resolution_and_source(monkeypatch):
    captured = {}

    def fake_load_bars(asset_id, end_date, start_date, resolution, adjust_type, source):
        captured["args"] = [asset_id, end_date, start_date, resolution, adjust_type, source]
        return [{"time": "2026-05-29 10:00:00"}]

    monkeypatch.setattr(dashboard_app, "load_bars", fake_load_bars)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/bars"
        "?start_date=2026-05-29"
        "&end_date=2026-05-29"
        "&resolution=30m"
        "&adjust_type=raw"
        "&source=baostock"
    )

    assert response.status_code == 200
    assert captured["args"] == [
        "000001.SZ",
        "2026-05-29",
        "2026-05-29",
        "30m",
        "raw",
        "baostock",
    ]
    assert response.json()["resolution"] == "30m"
    assert response.json()["items"] == [{"time": "2026-05-29 10:00:00"}]


def test_asset_decisions_route_returns_read_only_history(monkeypatch):
    captured = {}

    def fake_load_decision_history(asset_id, start_date, end_date, limit):
        captured["args"] = [asset_id, start_date, end_date, limit]
        return [
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "event_id": "operator_decision:morning-review:0:abc",
                "asset_id": asset_id,
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-05-30",
                "evidence_path": "outputs/p6/topn.json",
                "source_context": "dashboard_topn",
                "run_id": "eod-2026-06-12-local",
                "digest_key": "2026-06-12:manual_v1:000001.SZ",
                "review_item_snapshot_id": "review_item_snapshot:abc",
                "evidence_digest_snapshot_id": "evidence_digest_snapshot:def",
                "review_item_payload_hash": "review-hash",
                "evidence_digest_payload_hash": "digest-hash",
                "snapshot_linkage_status": "linked",
                "snapshot_linkage_warnings": [],
                "requires_follow_up": True,
                "follow_up_note": "check next close strength",
                "notes": "strong score",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_asset_decision_history", fake_load_decision_history)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/decisions"
        "?start_date=2026-05-01"
        "&end_date=2026-05-30"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["000001.SZ", "2026-05-01", "2026-05-30", 10]
    assert response.json()["items"][0]["decision_label"] == "candidate"
    assert response.json()["items"][0]["review_item_snapshot_id"] == "review_item_snapshot:abc"
    assert response.json()["items"][0]["evidence_digest_payload_hash"] == "digest-hash"
    assert response.json()["items"][0]["snapshot_linkage_status"] == "linked"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_operator_decisions_route_creates_decision(monkeypatch):
    captured = {}

    def fake_create_operator_decision(payload, service="stock_research"):
        captured["payload"] = payload
        captured["service"] = service
        return {
            "event_id": "operator_decision:operator-decision-api-2026-06-12:0:abc",
            "asset_id": "000001.SZ",
            "stock_code": "000001.SZ",
            "stock_name": "Ping An Bank",
            "decision_date": "2026-06-12",
            "operator_action": "watch",
            "decision_status": "open",
            "decision_label": "observe",
            "run_id": "eod-2026-06-12-local",
            "digest_key": "2026-06-12:manual_v1:000001.SZ",
            "review_item_snapshot_id": "review_item_snapshot:abc",
            "evidence_digest_snapshot_id": "evidence_digest_snapshot:def",
            "snapshot_linkage_status": "linked",
            "snapshot_linkage_warnings": [],
            "warnings": [],
        }

    monkeypatch.setattr(dashboard_app, "create_operator_decision", fake_create_operator_decision)
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/operator-decisions",
        json={
            "asset_id": "000001.SZ",
            "stock_code": "000001.SZ",
            "decision_date": "2026-06-12",
            "operator_action": "watch",
            "run_id": "eod-2026-06-12-local",
            "digest_key": "2026-06-12:manual_v1:000001.SZ",
            "source_context": {"entry": "review_queue"},
        },
    )

    assert response.status_code == 200
    assert captured["payload"]["operator_action"] == "watch"
    assert response.json()["decision_label"] == "observe"
    assert response.json()["snapshot_linkage_status"] == "linked"


def test_operator_decisions_route_returns_400_for_validation_error(monkeypatch):
    def fake_create_operator_decision(payload, service="stock_research"):
        raise ValueError("invalid_operator_action")

    monkeypatch.setattr(dashboard_app, "create_operator_decision", fake_create_operator_decision)
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/operator-decisions",
        json={"asset_id": "000001.SZ", "operator_action": "buy"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_operator_action"


def test_operator_decision_update_route_edits_review_log(monkeypatch):
    captured = {}

    def fake_update_operator_decision(event_id, payload):
        captured["event_id"] = event_id
        captured["payload"] = payload
        return {
            "review_date": "2026-06-12",
            "review_session_id": "operator-decision-api-2026-06-12",
            "event_id": event_id,
            "asset_id": "000001.SZ",
            "stock_code": "000001.SZ",
            "stock_name": "平安银行",
            "decision_label": "observe",
            "evidence_artifact_id": "operator_decision_api:2026-06-12:000001.SZ",
            "evidence_path": "",
            "source_context": "{}",
            "snapshot_linkage_status": "missing",
            "snapshot_linkage_warnings": [],
            "requires_follow_up": True,
            "follow_up_note": "next close",
            "notes": "updated review note",
            "manual_review_required": True,
            "auto_trade_enabled": False,
        }

    monkeypatch.setattr(dashboard_app, "update_operator_decision_event", fake_update_operator_decision)
    client = TestClient(dashboard_app.create_app())

    response = client.patch(
        "/api/operator-decisions/event-1",
        json={"notes": "updated review note", "requires_follow_up": True, "follow_up_note": "next close"},
    )

    assert response.status_code == 200
    assert captured["event_id"] == "event-1"
    assert captured["payload"]["notes"] == "updated review note"
    assert response.json()["item"]["notes"] == "updated review note"


def test_backtest_job_routes_submit_and_fetch_status(monkeypatch):
    captured = {}

    class FakeJobs:
        def submit(self, payload):
            captured["payload"] = payload
            return {"job_id": "job-1", "status": "queued"}

        def get(self, job_id):
            captured["job_id"] = job_id
            return {
                "job_id": job_id,
                "status": "succeeded",
                "result": {
                    "strategy_id": "lhb_shortline",
                    "strategy_name": "LHB Shortline Combo",
                    "summary": {"total_return": 0.12},
                    "positions": [],
                    "trades": [],
                    "equity_curve": [],
                },
                "error": "",
            }

    client = TestClient(dashboard_app.create_app())
    client.app.state.backtest_jobs = FakeJobs()

    submit_response = client.post("/api/backtests/jobs", json={"strategy_id": "lhb_shortline"})
    status_response = client.get("/api/backtests/jobs/job-1")

    assert submit_response.status_code == 200
    assert submit_response.json()["job_id"] == "job-1"
    assert captured["payload"]["strategy_id"] == "lhb_shortline"
    assert status_response.status_code == 200
    assert captured["job_id"] == "job-1"
    assert status_response.json()["status"] == "succeeded"


def test_asset_outcomes_route_returns_read_only_history(monkeypatch):
    captured = {}

    def fake_load_outcome_history(asset_id, start_date, end_date, review_session_id, limit):
        captured["args"] = [asset_id, start_date, end_date, review_session_id, limit]
        return [
            {
                "outcome_event_id": "operator_decision_outcome:p8:abc",
                "run_id": "p8-outcome-2026-05-01-2026-05-30",
                "decision_event_id": "operator_decision:morning-review:0:abc",
                "review_session_id": "morning-review",
                "review_date": "2026-05-30",
                "asset_id": asset_id,
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "source_context": "dashboard_topn",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "base_trade_date": "2026-05-30",
                "base_close": 10.0,
                "forward_returns": {"1": 0.1, "5": 0.2},
                "max_high_returns": {"1": 0.12, "5": 0.25},
                "max_low_drawdowns": {"1": 0.0, "5": -0.04},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "source_artifact_path": "outputs/p7/operator_decision_journal.json",
                "outcome_artifact_path": "outputs/p8/operator_decision_outcome_review.json",
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_asset_outcome_history", fake_load_outcome_history)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/outcomes"
        "?start_date=2026-05-01"
        "&end_date=2026-05-30"
        "&review_session_id=morning-review"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["000001.SZ", "2026-05-01", "2026-05-30", "morning-review", 10]
    assert response.json()["items"][0]["outcome_status"] == "complete"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_shadow_analytics_review_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_review(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return [
            {
                "review_group_id": "operator_shadow_analytics_review:trend-ready",
                "run_id": "p15-shadow-analytics-review-2026-08-31",
                "review_start_date": "2026-06-01",
                "review_end_date": "2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 4,
                "complete_count": 3,
                "insufficient_data_count": 1,
                "horizon_metrics": {"20": {"forward_return_mean": 0.12}},
                "review_status": "research_follow_up_candidate",
                "review_bucket": "needs_more_evidence",
                "evidence_summary": "Positive 20D mean with incomplete samples.",
                "risk_notes": "Observe only.",
                "next_research_question": "Can drawdown improve under stricter filters?",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(
        dashboard_app,
        "load_shadow_analytics_review_summary",
        fake_load_review,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-analytics-review"
        "?start_date=2026-06-01"
        "&end_date=2026-08-31"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json()["items"][0]["review_status"] == "research_follow_up_candidate"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_shadow_review_decisions_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_decisions(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return [
            {
                "decision_group_id": "operator_shadow_review_decision:trend-ready",
                "run_id": "p16-shadow-review-decisions-2026-08-31",
                "decision_date": "2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 4,
                "complete_count": 3,
                "insufficient_data_count": 1,
                "review_status": "research_follow_up_candidate",
                "review_bucket": "needs_more_evidence",
                "decision_status": "open_research_follow_up",
                "decision_bucket": "research_follow_up",
                "decision_reason": "P15 status maps to follow-up.",
                "required_next_action": "Create a separately scoped research follow-up.",
                "evidence_summary": "Positive 20D mean with incomplete samples.",
                "risk_notes": "Observe only.",
                "next_research_question": "Can drawdown improve under stricter filters?",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(
        dashboard_app,
        "load_shadow_review_decision_summary",
        fake_load_decisions,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-review-decisions"
        "?start_date=2026-06-01"
        "&end_date=2026-08-31"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json()["items"][0]["decision_status"] == "open_research_follow_up"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_shadow_follow_up_queue_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_follow_up(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return [
            {
                "follow_up_item_id": "operator_shadow_follow_up:trend-ready",
                "run_id": "p17-shadow-follow-up-queue-2026-08-31",
                "follow_up_date": "2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "decision_status": "request_more_data",
                "follow_up_status": "collect_more_evidence",
                "priority_bucket": "high",
                "required_input": "Additional outcome or data-quality evidence",
                "follow_up_reason": "P16 status maps to evidence collection.",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(
        dashboard_app,
        "load_shadow_follow_up_queue_summary",
        fake_load_follow_up,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-follow-up-queue"
        "?start_date=2026-06-01"
        "&end_date=2026-08-31"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json()["items"][0]["follow_up_status"] == "collect_more_evidence"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_shadow_follow_up_resolution_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_resolution(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return [
            {
                "resolution_item_id": "operator_shadow_follow_up_resolution:trend-ready",
                "run_id": "p18-shadow-follow-up-resolution-2026-08-31",
                "resolution_date": "2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "follow_up_status": "collect_more_evidence",
                "priority_bucket": "high",
                "resolution_status": "stale_unresolved",
                "resolution_bucket": "needs_operator_review",
                "recommended_resolution_action": "Review whether requested evidence has been collected.",
                "resolution_reason": "P17 follow-up maps to stale unresolved.",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(
        dashboard_app,
        "load_shadow_follow_up_resolution_summary",
        fake_load_resolution,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-follow-up-resolution"
        "?start_date=2026-06-01"
        "&end_date=2026-08-31"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json()["items"][0]["resolution_status"] == "stale_unresolved"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_outcome_analytics_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_analytics(start_date, end_date, review_session_id, limit):
        captured["args"] = [start_date, end_date, review_session_id, limit]
        return [
            {
                "run_id": "p9-outcome-analytics-2026-05-01-2026-06-30",
                "review_start_date": "2026-05-01",
                "review_end_date": "2026-06-30",
                "analytics_level": "decision_label",
                "group_value": "candidate",
                "sample_count": 2,
                "complete_count": 2,
                "insufficient_data_count": 0,
                "follow_up_required_rate": 0.5,
                "horizon_metrics": {"5": {"forward_return_mean": 0.15, "forward_win_rate": 1.0}},
                "analytics_artifact_path": "outputs/p9/operator_decision_outcome_analytics.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_outcome_analytics_summary", fake_load_analytics)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/outcome-analytics"
        "?start_date=2026-05-01"
        "&end_date=2026-06-30"
        "&review_session_id=morning-review"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-05-01", "2026-06-30", "morning-review", 10]
    assert response.json()["items"][0]["analytics_level"] == "decision_label"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_experiment_proposals_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_proposals(start_date, end_date, status, limit):
        captured["args"] = [start_date, end_date, status, limit]
        return [
            {
                "proposal_id": "p10-proposal:001",
                "run_id": "p10-proposals-2026-05-31",
                "review_date": "2026-05-31",
                "proposal_title": "Replay dashboard top-N",
                "hypothesis": "Dashboard top-N candidates should be replayed offline.",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "source_analytics_group_ids": ["decision_label:candidate"],
                "source_diagnostic_refs": ["top_forward_return:5:decision_label:candidate"],
                "source_artifact_paths": ["outputs/p9/analytics.json"],
                "expected_validation_method": "offline replay",
                "risk_notes": "No production scoring change in P10.",
                "reviewer_id": "reviewer-a",
                "status": "approved_for_experiment",
                "proposal_artifact_path": "outputs/p10/operator_experiment_proposals_2026-05-31.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "promotion_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_experiment_proposals_summary", fake_load_proposals)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/experiment-proposals"
        "?start_date=2026-05-01"
        "&end_date=2026-06-30"
        "&status=approved_for_experiment"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-05-01", "2026-06-30", "approved_for_experiment", 10]
    assert response.json()["items"][0]["proposal_id"] == "p10-proposal:001"
    assert response.json()["items"][0]["promotion_enabled"] is False


def test_experiment_replay_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_replay(start_date, end_date, status, limit):
        captured["args"] = [start_date, end_date, status, limit]
        return [
            {
                "replay_result_id": "p11-replay:001",
                "run_id": "p11-replay-run-2026-06-30",
                "proposal_id": "p10-proposal:001",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "replay_start_date": "2026-01-01",
                "replay_end_date": "2026-05-31",
                "replay_input_artifact_paths": ["inputs/p11/replay_candidates.csv"],
                "validation_method": "offline replay",
                "replay_status": "passed_offline_replay",
                "sample_count": 24,
                "passed_count": 18,
                "failed_count": 6,
                "metric_summary": {"win_rate": 0.75},
                "failure_reason": "",
                "defer_reason": "",
                "replay_artifact_path": "outputs/p11/operator_experiment_replay_2026-01-01_2026-05-31.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_experiment_replay_summary", fake_load_replay)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/experiment-replay"
        "?start_date=2026-01-01"
        "&end_date=2026-06-30"
        "&status=passed_offline_replay"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-01-01", "2026-06-30", "passed_offline_replay", 10]
    assert response.json()["items"][0]["replay_result_id"] == "p11-replay:001"
    assert response.json()["items"][0]["auto_trade_enabled"] is False
    assert response.json()["items"][0]["production_write_enabled"] is False


def test_shadow_watchlist_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_shadow(start_date, end_date, status, limit):
        captured["args"] = [start_date, end_date, status, limit]
        return [
            {
                "shadow_candidate_id": "p12-shadow:001",
                "run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "candidate_reason": "Passed replay with acceptable drawdown.",
                "evidence_artifact_paths": ["outputs/p11/replay.json"],
                "metric_summary": {"win_rate": 0.75},
                "reviewer_id": "reviewer-a",
                "status": "shadow_ready",
                "review_notes": "Observe only.",
                "shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_shadow_watchlist_summary", fake_load_shadow)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-watchlist"
        "?start_date=2026-06-01"
        "&end_date=2026-06-30"
        "&status=shadow_ready"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-06-30", "shadow_ready", 10]
    assert response.json()["items"][0]["shadow_candidate_id"] == "p12-shadow:001"
    assert response.json()["items"][0]["production_watchlist_enabled"] is False


def test_shadow_outcomes_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_shadow_outcomes(start_date, end_date, outcome_status, limit):
        captured["args"] = [start_date, end_date, outcome_status, limit]
        return [
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:001",
                "run_id": "p13-shadow-outcomes-2026-07-31",
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "base_trade_date": "2026-06-30",
                "base_close": 10.0,
                "forward_returns": {"5": 0.5},
                "max_high_returns": {"5": 0.6},
                "max_low_drawdowns": {"5": -0.1},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_shadow_outcomes_summary", fake_load_shadow_outcomes)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-outcomes"
        "?start_date=2026-06-01"
        "&end_date=2026-07-31"
        "&outcome_status=complete"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-07-31", "complete", 10]
    assert response.json()["items"][0]["shadow_candidate_id"] == "p12-shadow:001"
    assert response.json()["items"][0]["production_watchlist_enabled"] is False


def test_shadow_outcomes_route_returns_empty_items_when_table_missing(monkeypatch):
    class FakeConnect:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        raise psycopg_errors.UndefinedTable("missing P13 outcome table")

    monkeypatch.setattr(shadow_outcomes, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(shadow_outcomes, "connect", fake_connect)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/shadow-outcomes?start_date=2026-06-01&end_date=2026-07-31")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_shadow_outcome_analytics_route_returns_read_only_summary(monkeypatch):
    captured = {}
    rows = [
        {
            "analytics_group_id": "operator_shadow_outcome_analytics:trend-ready",
            "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
            "review_start_date": "2026-06-30",
            "review_end_date": "2026-08-29",
            "group_key": "trend_shadow|shadow_ready",
            "shadow_layer": "trend_shadow",
            "shadow_status": "shadow_ready",
            "sample_count": 2,
            "complete_count": 2,
            "insufficient_data_count": 0,
            "source_p12_shadow_run_count": 1,
            "source_p11_replay_run_count": 1,
            "source_p10_proposal_run_count": 1,
            "source_p9_analytics_run_count": 1,
            "horizon_metrics": {"20": {"forward_return_mean": 0.12}},
            "analytics_artifact_path": "outputs/p14/analytics.json",
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        }
    ]

    def fake_load_analytics(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return rows

    monkeypatch.setattr(dashboard_app, "load_shadow_outcome_analytics_summary", fake_load_analytics)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-outcome-analytics?start_date=2026-06-01&end_date=2026-08-31&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json() == {"items": rows}


def test_dashboard_api_cli_parser_accepts_host_and_port():
    args = cli.build_parser().parse_args(
        ["dashboard-api", "--host", "0.0.0.0", "--port", "9999"]
    )

    assert args.command == "dashboard-api"
    assert args.host == "0.0.0.0"
    assert args.port == 9999


def test_dashboard_api_cli_dispatches_to_runner(monkeypatch):
    captured = {}

    def fake_run_dashboard_api(host, port):
        captured["call"] = {"host": host, "port": port}

    monkeypatch.setattr(cli, "run_dashboard_api", fake_run_dashboard_api)

    cli.main_for_args(["dashboard-api", "--host", "0.0.0.0", "--port", "9999"])

    assert captured["call"] == {"host": "0.0.0.0", "port": 9999}


def test_market_monitor_eod_route_returns_payload(monkeypatch):
    captured = {}

    def fake_build_market_monitor_eod(trade_date=None, score_version="manual_v1", top_n=5):
        captured["kwargs"] = {
            "trade_date": trade_date,
            "score_version": score_version,
            "top_n": top_n,
        }
        return {
            "trade_date": trade_date or "2026-06-10",
            "freshness": {"mode": "eod", "is_realtime": False},
            "coverage": {"market_assets": 5300, "score_assets": 3100, "factor_count": 42},
            "market_breadth": {"status": "pending_source"},
            "market_emotion": {
                "summary": {
                    "score": 73.6,
                    "state": "hot",
                    "risk_state": "medium",
                    "style_signal_hint": "growth_favorable",
                    "position_budget_hint": "reduced",
                    "status": "available",
                },
                "components": [],
                "breadth": {"status": "available"},
                "liquidity": {"status": "available"},
                "limit_performance": {"status": "available"},
                "profit_effect": {"status": "available"},
                "drawdown_pressure": {"status": "available"},
                "weight_performance": {"status": "pending_source"},
            },
            "emotion_stock_lists": {
                "auction": [],
                "limit_up": [],
                "broken_limit_up": [],
                "limit_down": [],
                "auction_status": "pending_source",
            },
            "index_snapshot": [],
            "sector_strength": {"strongest": [], "weakest": [], "status": "pending_source"},
            "unusual_moves": [],
            "watchlist_alerts": [],
            "strategy_signal_summary": {
                "topn_preview_count": 0,
                "topn_preview": [],
                "risk_filter_counts": {},
            },
            "generated_reports": [],
            "warnings": [],
        }

    monkeypatch.setattr(
        dashboard_app,
        "build_market_monitor_eod",
        fake_build_market_monitor_eod,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/market-monitor/eod"
        "?trade_date=2026-06-10"
        "&score_version=manual_v2"
        "&top_n=3"
    )

    assert response.status_code == 200
    assert captured["kwargs"] == {
        "trade_date": "2026-06-10",
        "score_version": "manual_v2",
        "top_n": 3,
    }
    assert response.json()["trade_date"] == "2026-06-10"
    assert response.json()["freshness"]["is_realtime"] is False
    assert response.json()["market_emotion"] == {
        "summary": {
            "score": 73.6,
            "state": "hot",
            "risk_state": "medium",
            "style_signal_hint": "growth_favorable",
            "position_budget_hint": "reduced",
            "status": "available",
        },
        "components": [],
        "breadth": {"status": "available"},
        "liquidity": {"status": "available"},
        "limit_performance": {"status": "available"},
        "profit_effect": {"status": "available"},
        "drawdown_pressure": {"status": "available"},
        "weight_performance": {"status": "pending_source"},
    }
    assert response.json()["emotion_stock_lists"] == {
        "auction": [],
        "limit_up": [],
        "broken_limit_up": [],
        "limit_down": [],
        "auction_status": "pending_source",
    }


def test_ops_snapshot_route_returns_aggregated_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_internal_ops_snapshot",
        lambda trade_date=None: {
            "pipeline": {"overall_status": "ready"},
            "readiness": {"ready_status": "ready"},
        },
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/ops/snapshot")

    assert response.status_code == 200
    assert response.json()["pipeline"]["overall_status"] == "ready"


def test_ops_snapshot_and_public_snapshot_routes_share_default_target_date(monkeypatch):
    captured = {}

    class _Config:
        timezone = "Asia/Shanghai"

    def fake_build_internal_ops_snapshot(trade_date=None):
        captured["ops_date"] = trade_date
        return {"pipeline": {"overall_status": "ready"}}

    def fake_build_public_snapshot(trade_date=None):
        captured["public_date"] = trade_date
        return {"trade_date": "2026-06-24", "status": "ready", "status_text": "ready"}

    monkeypatch.setattr(dashboard_app, "parse_trade_date", lambda value, timezone: date(2026, 6, 24))
    monkeypatch.setattr(dashboard_app.IntradayConfig, "from_env", lambda: _Config())
    monkeypatch.setattr(
        dashboard_app,
        "build_internal_ops_snapshot",
        fake_build_internal_ops_snapshot,
        raising=False,
    )
    monkeypatch.setattr(
        dashboard_app,
        "build_public_snapshot",
        fake_build_public_snapshot,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    ops_response = client.get("/api/ops/snapshot")
    public_response = client.get("/api/public/snapshot")

    assert ops_response.status_code == 200
    assert public_response.status_code == 200
    assert captured["ops_date"] == date(2026, 6, 24)
    assert captured["public_date"] == date(2026, 6, 24)


def test_ops_stages_route_returns_stage_list(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_ops_stage_details",
        lambda trade_date=None: [{"stage": "daily", "status": "success"}],
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/ops/stages")

    assert response.status_code == 200
    assert response.json()["items"][0]["stage"] == "daily"


def test_public_snapshot_route_returns_public_payload(monkeypatch):
    captured = {}

    class _Config:
        timezone = "Asia/Shanghai"

    def fake_build_public_snapshot(trade_date=None):
        captured["trade_date"] = trade_date
        return {"trade_date": "2026-06-23", "status": "ready", "status_text": "ready"}

    monkeypatch.setattr(dashboard_app, "parse_trade_date", lambda value, timezone: date(2026, 6, 23))
    monkeypatch.setattr(dashboard_app.IntradayConfig, "from_env", lambda: _Config())
    monkeypatch.setattr(
        dashboard_app,
        "build_public_snapshot",
        fake_build_public_snapshot,
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/public/snapshot")

    assert response.status_code == 200
    assert captured["trade_date"] == date(2026, 6, 23)
    assert response.json()["status"] == "ready"
