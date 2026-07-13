import pytest
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import stock_heatmap_service


def test_build_stock_heatmap_payload_groups_stocks_by_industry(monkeypatch):
    monkeypatch.setattr(
        stock_heatmap_service,
        "load_stock_heatmap_rows",
        lambda trade_date, service=None: [
            {
                "trade_date": trade_date,
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "平安银行",
                "industry_code": "BK_BANK",
                "industry_name": "银行",
                "close": 12.5,
                "pct_chg": 2.0,
                "amount": 3000000000.0,
                "source": "market_daily_bar",
                "updated_at": "2026-07-07T15:00:00+08:00",
            },
            {
                "trade_date": trade_date,
                "asset_id": "CN:SH:600000",
                "symbol": "600000",
                "name": "浦发银行",
                "industry_code": "BK_BANK",
                "industry_name": "银行",
                "close": 9.0,
                "pct_chg": -1.0,
                "amount": 1000000000.0,
                "source": "market_daily_bar",
                "updated_at": "2026-07-07T15:01:00+08:00",
            },
            {
                "trade_date": trade_date,
                "asset_id": "CN:SZ:002371",
                "symbol": "002371",
                "name": "北方华创",
                "industry_code": "BK_SEMI",
                "industry_name": "半导体",
                "close": 300.0,
                "pct_chg": 4.0,
                "amount": 5000000000.0,
                "source": "market_daily_bar",
                "updated_at": "2026-07-07T15:02:00+08:00",
            },
        ],
    )

    payload = stock_heatmap_service.build_stock_heatmap_payload("2026-07-07")

    assert payload["trade_date"] == "2026-07-07"
    assert payload["market"] == "all"
    assert payload["period"] == "1d"
    assert payload["group"] == "industry"
    assert payload["size_by"] == "amount"
    assert payload["data_status"] == "completed"
    assert payload["updated_at"] == "2026-07-07T15:02:00+08:00"
    assert payload["summary"] == {
        "stock_count": 3,
        "up_count": 2,
        "flat_count": 0,
        "down_count": 1,
        "total_amount": 9000000000.0,
    }
    assert [group["group_name"] for group in payload["groups"]] == ["半导体", "银行"]
    assert payload["groups"][0]["value"] == 5000000000.0
    assert payload["groups"][0]["change_pct"] == pytest.approx(0.04)
    assert payload["groups"][1]["value"] == 4000000000.0
    assert payload["groups"][1]["change_pct"] == pytest.approx(0.0125)
    assert [stock["name"] for stock in payload["groups"][1]["children"]] == ["平安银行", "浦发银行"]


def test_build_stock_heatmap_payload_returns_missing_when_no_rows(monkeypatch):
    monkeypatch.setattr(stock_heatmap_service, "load_stock_heatmap_rows", lambda trade_date, service=None: [])

    payload = stock_heatmap_service.build_stock_heatmap_payload("2026-07-07")

    assert payload["data_status"] == "missing"
    assert payload["warnings"] == ["stock heatmap rows are unavailable"]
    assert payload["summary"]["stock_count"] == 0
    assert payload["groups"] == []


def test_stock_heatmap_api_rejects_unsupported_options():
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/market-monitor/stocks/heatmap?trade_date=2026-07-07&market=hs300&period=1d&group=industry&size_by=amount"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported_stock_heatmap_option"


def test_stock_heatmap_api_returns_whitelisted_fields(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_stock_heatmap_payload",
        lambda trade_date, market="all", period="1d", group="industry", size_by="amount": {
            "trade_date": trade_date,
            "market": market,
            "period": period,
            "group": group,
            "size_by": size_by,
            "updated_at": "2026-07-07T15:00:00+08:00",
            "source": "market_daily_bar,core.industry_membership",
            "data_status": "completed",
            "warnings": [],
            "summary": {
                "stock_count": 1,
                "up_count": 1,
                "flat_count": 0,
                "down_count": 0,
                "total_amount": 100.0,
            },
            "groups": [
                {
                    "group_id": "BK_SEMI",
                    "group_name": "半导体",
                    "value": 100.0,
                    "change_pct": 0.03,
                    "stock_count": 1,
                    "children": [
                        {
                            "asset_id": "CN:SZ:002371",
                            "symbol": "002371",
                            "name": "北方华创",
                            "price": 300.0,
                            "change_pct": 0.03,
                            "amount": 100.0,
                            "value": 100.0,
                            "group_id": "BK_SEMI",
                            "group_name": "半导体",
                        }
                    ],
                }
            ],
            "payload": {"must_not": "leak"},
            "metadata": {"must_not": "leak"},
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/market-monitor/stocks/heatmap?trade_date=2026-07-07")

    assert response.status_code == 200
    payload = response.json()
    assert "payload" not in payload
    assert "metadata" not in payload
    assert set(payload) == {
        "trade_date",
        "market",
        "period",
        "group",
        "size_by",
        "updated_at",
        "source",
        "data_status",
        "warnings",
        "summary",
        "groups",
    }
