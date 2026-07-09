from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import stock_market_context_heatmap


def test_build_stock_market_context_heatmap_ranks_selected_peer(monkeypatch):
    rows = [
        {
            "asset_id": "CN:SZ:000001",
            "symbol": "000001",
            "name": "平安银行",
            "trade_date": "2026-07-07",
            "close": 12.5,
            "pct_chg": 2.0,
            "amount": 3000000000,
            "industry_id": "bank",
            "industry_name": "银行",
            "industry_system": "csrc",
        },
        {
            "asset_id": "CN:SH:600000",
            "symbol": "600000",
            "name": "浦发银行",
            "trade_date": "2026-07-07",
            "close": 9.0,
            "pct_chg": -1.0,
            "amount": 1000000000,
            "industry_id": "bank",
            "industry_name": "银行",
            "industry_system": "csrc",
        },
    ]
    monkeypatch.setattr(
        stock_market_context_heatmap,
        "load_peer_heatmap_rows",
        lambda asset_id, trade_date, service=None: rows,
    )

    payload = stock_market_context_heatmap.build_stock_market_context_heatmap("000001.SZ", "2026-07-07")

    assert payload["data_status"] == "completed"
    assert payload["industry"]["industry_name"] == "银行"
    assert payload["summary"]["peer_count"] == 2
    assert payload["summary"]["selected_in_peer_set"] is True
    assert payload["selected"]["asset_id"] == "CN:SZ:000001"
    assert payload["selected"]["amount_rank"] == 1
    assert payload["selected"]["change_rank"] == 1
    assert payload["selected"]["amount_percentile"] == 1.0
    assert payload["selected"]["change_percentile"] == 1.0
    assert payload["peers"][0]["is_selected"] is True
    assert payload["peers"][0]["change_pct"] == 0.02


def test_build_stock_market_context_heatmap_returns_missing_when_no_rows(monkeypatch):
    monkeypatch.setattr(
        stock_market_context_heatmap,
        "load_peer_heatmap_rows",
        lambda asset_id, trade_date, service=None: [],
    )

    payload = stock_market_context_heatmap.build_stock_market_context_heatmap("000001.SZ", "2026-07-07")

    assert payload["data_status"] == "missing"
    assert payload["summary"]["peer_count"] == 0
    assert payload["selected"] is None
    assert payload["peers"] == []
    assert "peer heatmap rows are unavailable" in payload["warnings"]


def test_stock_market_context_heatmap_read_model_filters_internal_fields():
    payload = {
        "asset_id": "000001.SZ",
        "canonical_asset_id": "CN:SZ:000001",
        "trade_date": "2026-07-07",
        "industry": {"industry_id": "bank", "industry_name": "银行", "industry_system": "csrc", "payload": {"raw": True}},
        "selected": {
            "asset_id": "CN:SZ:000001",
            "symbol": "000001",
            "name": "平安银行",
            "price": 12.5,
            "change_pct": 0.02,
            "amount": 3000000000,
            "amount_rank": 1,
            "change_rank": 1,
            "amount_percentile": 1.0,
            "change_percentile": 1.0,
            "raw_payload": {"secret": True},
        },
        "summary": {
            "peer_count": 1,
            "up_count": 1,
            "flat_count": 0,
            "down_count": 0,
            "total_amount": 3000000000,
            "selected_in_peer_set": True,
        },
        "peers": [
            {
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "平安银行",
                "price": 12.5,
                "change_pct": 0.02,
                "amount": 3000000000,
                "value": 3000000000,
                "is_selected": True,
                "metadata": {"raw": True},
            }
        ],
        "data_status": "completed",
        "warnings": [],
        "metadata": {"raw": True},
    }

    model = stock_market_context_heatmap.stock_market_context_heatmap_read_model(payload)

    assert "metadata" not in model
    assert "payload" not in model["industry"]
    assert "raw_payload" not in model["selected"]
    assert "metadata" not in model["peers"][0]


def test_stock_market_context_heatmap_api_accepts_colon_asset_id(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_stock_market_context_heatmap",
        lambda asset_id, trade_date: {
            "asset_id": asset_id,
            "canonical_asset_id": "CN:SZ:000001",
            "trade_date": trade_date,
            "industry": {"industry_id": "bank", "industry_name": "银行", "industry_system": "csrc"},
            "selected": None,
            "summary": {
                "peer_count": 0,
                "up_count": 0,
                "flat_count": 0,
                "down_count": 0,
                "total_amount": 0,
                "selected_in_peer_set": False,
            },
            "peers": [],
            "data_status": "missing",
            "warnings": ["peer heatmap rows are unavailable"],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/stocks/CN:SZ:000001/market-context/heatmap?trade_date=2026-07-07")

    assert response.status_code == 200
    assert response.json()["asset_id"] == "CN:SZ:000001"
    assert response.json()["trade_date"] == "2026-07-07"
