from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import market_anomaly_context


def _rows():
    return [
        {
            "asset_id": "CN:SZ:000001",
            "symbol": "000001",
            "name": "平安银行",
            "industry_id": "bank",
            "industry_name": "银行",
            "close": 12.5,
            "pct_chg": 6.2,
            "amount": 3000000000,
            "amount_avg_20d": 1000000000,
            "turnover_rate": 4.2,
            "is_limit_up": False,
            "is_limit_down": False,
        },
        {
            "asset_id": "CN:SH:600000",
            "symbol": "600000",
            "name": "浦发银行",
            "industry_id": "bank",
            "industry_name": "银行",
            "close": 9.0,
            "pct_chg": -1.0,
            "amount": 1000000000,
            "amount_avg_20d": 1200000000,
            "turnover_rate": 1.1,
            "is_limit_up": False,
            "is_limit_down": False,
        },
        {
            "asset_id": "CN:SH:688981",
            "symbol": "688981",
            "name": "中芯国际",
            "industry_id": "chip",
            "industry_name": "半导体",
            "close": 70.0,
            "pct_chg": -6.5,
            "amount": 2500000000,
            "amount_avg_20d": 800000000,
            "turnover_rate": 5.5,
            "is_limit_up": False,
            "is_limit_down": True,
        },
    ]


def test_build_market_anomaly_context_tags_hot_stocks_and_ranks_industries(monkeypatch):
    monkeypatch.setattr(market_anomaly_context, "load_market_anomaly_rows", lambda trade_date, service=None: _rows())

    payload = market_anomaly_context.build_market_anomaly_context("2026-07-07")

    assert payload["data_status"] == "completed"
    assert payload["summary"]["hot_stock_count"] == 2
    assert payload["summary"]["volume_spike_count"] == 2
    assert payload["summary"]["strong_move_count"] == 2
    assert payload["hot_industries"][0]["industry_name"] in {"银行", "半导体"}
    assert payload["hot_industries"][0]["anomaly_score"] >= payload["hot_industries"][1]["anomaly_score"]
    assert payload["hot_industries"][0]["explanation_bullets"]

    stock = next(item for item in payload["hot_stocks"] if item["asset_id"] == "CN:SZ:000001")
    assert "volume_spike" in stock["anomaly_tags"]
    assert "strong_up" in stock["anomaly_tags"]
    assert stock["amount_ratio_20d"] == 3.0
    assert any("放量" in bullet for bullet in stock["explanation_bullets"])

    limit_down = next(item for item in payload["hot_stocks"] if item["asset_id"] == "CN:SH:688981")
    assert "limit_down" in limit_down["anomaly_tags"]
    assert "strong_down" in limit_down["anomaly_tags"]


def test_build_market_anomaly_context_returns_missing_when_no_rows(monkeypatch):
    monkeypatch.setattr(market_anomaly_context, "load_market_anomaly_rows", lambda trade_date, service=None: [])

    payload = market_anomaly_context.build_market_anomaly_context("2026-07-07")

    assert payload["data_status"] == "missing"
    assert payload["summary"]["hot_industry_count"] == 0
    assert payload["hot_industries"] == []
    assert payload["hot_stocks"] == []
    assert "market anomaly rows are unavailable" in payload["warnings"]


def test_market_anomaly_context_read_model_filters_internal_fields():
    payload = {
        "trade_date": "2026-07-07",
        "data_status": "completed",
        "summary": {
            "hot_industry_count": 1,
            "hot_stock_count": 1,
            "volume_spike_count": 1,
            "strong_move_count": 1,
        },
        "hot_industries": [
            {
                "industry_id": "bank",
                "industry_name": "银行",
                "change_pct": 0.03,
                "amount": 3000000000,
                "stock_count": 1,
                "up_count": 1,
                "down_count": 0,
                "volume_spike_count": 1,
                "strong_move_count": 1,
                "anomaly_score": 12.3,
                "explanation_bullets": ["银行放量上涨"],
                "raw_payload": {"secret": True},
            }
        ],
        "hot_stocks": [
            {
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "平安银行",
                "industry_id": "bank",
                "industry_name": "银行",
                "change_pct": 0.062,
                "amount": 3000000000,
                "amount_ratio_20d": 3.0,
                "turnover_rate": 4.2,
                "anomaly_tags": ["volume_spike", "strong_up"],
                "explanation_bullets": ["放量上涨"],
                "metadata": {"raw": True},
            }
        ],
        "warnings": [],
        "metadata": {"raw": True},
    }

    model = market_anomaly_context.market_anomaly_context_read_model(payload)

    assert "metadata" not in model
    assert "raw_payload" not in model["hot_industries"][0]
    assert "metadata" not in model["hot_stocks"][0]


def test_market_anomaly_context_api_route(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_market_anomaly_context",
        lambda trade_date: {
            "trade_date": trade_date,
            "data_status": "missing",
            "summary": {
                "hot_industry_count": 0,
                "hot_stock_count": 0,
                "volume_spike_count": 0,
                "strong_move_count": 0,
            },
            "hot_industries": [],
            "hot_stocks": [],
            "warnings": ["market anomaly rows are unavailable"],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/market-monitor/anomaly-context?trade_date=2026-07-07")

    assert response.status_code == 200
    assert response.json()["trade_date"] == "2026-07-07"
    assert response.json()["data_status"] == "missing"
