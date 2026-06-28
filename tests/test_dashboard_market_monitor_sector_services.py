import pytest

from stock_research.dashboard import (
    market_overview_service,
    sector_detail_service,
    sector_fund_flow_service,
    sector_heatmap_service,
)


def test_build_market_overview_payload_returns_trade_date_status_and_indices(monkeypatch):
    monkeypatch.setattr(
        market_overview_service,
        "load_market_overview_row",
        lambda trade_date, service=None: {
            "trade_date": trade_date,
            "total_amount": 1280000000000.0,
            "up_count": 3210,
            "down_count": 1765,
            "limit_up_count": 82,
            "limit_down_count": 9,
            "source": "market_emotion_state_daily",
            "updated_at": "2026-06-26T15:30:00+08:00",
        },
    )
    monkeypatch.setattr(
        market_overview_service,
        "load_market_index_rows",
        lambda trade_date, service=None: [
            {
                "index_id": "SSE_COMPOSITE",
                "index_name": "上证指数",
                "close": 3123.45,
                "preclose": 3099.01,
                "source": "baostock",
                "updated_at": "2026-06-26T15:31:00+08:00",
            }
        ],
    )

    payload = market_overview_service.build_market_overview_payload("2026-06-26")

    assert payload["trade_date"] == "2026-06-26"
    assert payload["data_status"] == "completed"
    assert payload["indices"] == [
        {
            "code": "SSE_COMPOSITE",
            "name": "上证指数",
            "close": 3123.45,
            "change_pct": 3123.45 / 3099.01 - 1.0,
        }
    ]


def test_build_sector_heatmap_payload_returns_normalized_industry_items(monkeypatch):
    monkeypatch.setattr(
        sector_heatmap_service,
        "load_sector_heatmap_rows",
        lambda trade_date, sector_type, service=None: [
            {
                "trade_date": trade_date,
                "industry_code": "BK0428",
                "industry_name": "半导体",
                "close": 105.0,
                "preclose": 100.0,
                "amount": 88000000000.0,
                "up_count": 41,
                "down_count": 9,
                "stock_count": 52,
                "source": "industry_daily_bar",
                "updated_at": "2026-06-26T15:35:00+08:00",
            }
        ],
    )

    payload = sector_heatmap_service.build_sector_heatmap_payload(
        "2026-06-26",
        sector_type="industry",
    )

    assert payload["data_status"] == "completed"
    assert payload["warnings"] == []
    assert payload["items"][0]["sector_id"] == "BK0428"
    assert payload["items"][0]["sector_name"] == "半导体"
    assert payload["items"][0]["sector_type"] == "industry"
    assert payload["items"][0]["change_pct"] == pytest.approx(0.05)
    assert payload["items"][0]["amount"] == 88000000000.0
    assert payload["items"][0]["up_count"] == 41
    assert payload["items"][0]["down_count"] == 9
    assert payload["items"][0]["main_net_inflow"] is None
    assert payload["items"][0]["stock_count"] == 52


def test_build_sector_fund_flow_payload_is_stable_when_source_is_missing(monkeypatch):
    monkeypatch.setattr(
        sector_fund_flow_service,
        "load_sector_fund_flow_rows",
        lambda trade_date, sector_type, period="1d", service=None: [],
    )

    payload = sector_fund_flow_service.build_sector_fund_flow_payload(
        "2026-06-26",
        sector_type="industry",
        period="1d",
    )

    assert payload["trade_date"] == "2026-06-26"
    assert payload["source"] == "third_party_fund_flow_signal"
    assert payload["data_status"] == "missing"
    assert payload["warnings"] == [
        "fund flow source is unavailable; returning empty directional signal payload"
    ]
    assert payload["inflow"] == []
    assert payload["outflow"] == []


def test_build_sector_detail_payload_returns_empty_leading_stocks_when_unavailable(monkeypatch):
    monkeypatch.setattr(
        sector_detail_service,
        "load_sector_detail_row",
        lambda trade_date, sector_id, sector_type, service=None: {
            "trade_date": trade_date,
            "industry_code": sector_id,
            "industry_name": "半导体",
            "close": 105.0,
            "preclose": 100.0,
            "amount": 88000000000.0,
            "up_count": 41,
            "down_count": 9,
            "stock_count": 52,
            "source": "industry_daily_bar",
            "updated_at": "2026-06-26T15:35:00+08:00",
        },
    )
    monkeypatch.setattr(
        sector_detail_service,
        "load_sector_leading_stocks",
        lambda trade_date, sector_id, sector_type, service=None, limit=10: [],
    )

    payload = sector_detail_service.build_sector_detail_payload(
        "2026-06-26",
        sector_id="BK0428",
        sector_type="industry",
    )

    assert payload["data_status"] == "completed"
    assert payload["leading_stocks"] == []
