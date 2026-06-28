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
            },
            {
                "index_id": "SZSE_COMPONENT",
                "index_name": "深证成指",
                "close": 9988.76,
                "preclose": 9900.0,
                "source": "baostock",
                "updated_at": "2026-06-26T15:31:00+08:00",
            },
            {
                "index_id": "CHINEXT",
                "index_name": "创业板指",
                "close": 2012.34,
                "preclose": 2000.0,
                "source": "baostock",
                "updated_at": "2026-06-26T15:31:00+08:00",
            },
        ],
    )

    payload = market_overview_service.build_market_overview_payload("2026-06-26")

    assert payload["trade_date"] == "2026-06-26"
    assert payload["data_status"] == "partial"
    assert payload["warnings"] == [
        "market overview is missing index rows for: 科创50, 北证50"
    ]
    assert payload["indices"] == [
        {
            "code": "SSE_COMPOSITE",
            "name": "上证指数",
            "close": 3123.45,
            "change_pct": 3123.45 / 3099.01 - 1.0,
        },
        {
            "code": "SZSE_COMPONENT",
            "name": "深证成指",
            "close": 9988.76,
            "change_pct": 9988.76 / 9900.0 - 1.0,
        },
        {
            "code": "CHINEXT",
            "name": "创业板指",
            "close": 2012.34,
            "change_pct": 2012.34 / 2000.0 - 1.0,
        }
    ]


def test_build_market_overview_payload_is_completed_when_all_required_indices_exist(monkeypatch):
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
            },
            {
                "index_id": "SZSE_COMPONENT",
                "index_name": "深证成指",
                "close": 9988.76,
                "preclose": 9900.0,
                "source": "baostock",
                "updated_at": "2026-06-26T15:31:00+08:00",
            },
            {
                "index_id": "CHINEXT",
                "index_name": "创业板指",
                "close": 2012.34,
                "preclose": 2000.0,
                "source": "baostock",
                "updated_at": "2026-06-26T15:31:00+08:00",
            },
            {
                "index_id": "STAR_50",
                "index_name": "科创50",
                "close": 955.0,
                "preclose": 950.0,
                "source": "baostock",
                "updated_at": "2026-06-26T15:31:00+08:00",
            },
            {
                "index_id": "BSE_50",
                "index_name": "北证50",
                "close": 1200.0,
                "preclose": 1188.0,
                "source": "baostock",
                "updated_at": "2026-06-26T15:31:00+08:00",
            },
        ],
    )

    payload = market_overview_service.build_market_overview_payload("2026-06-26")

    assert payload["data_status"] == "completed"
    assert payload["warnings"] == []
    assert [item["code"] for item in payload["indices"]] == [
        "SSE_COMPOSITE",
        "SZSE_COMPONENT",
        "CHINEXT",
        "STAR_50",
        "BSE_50",
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


def test_build_sector_fund_flow_payload_normalizes_and_ranks_rows(monkeypatch):
    monkeypatch.setattr(
        sector_fund_flow_service,
        "load_sector_fund_flow_rows",
        lambda trade_date, sector_type, period="1d", service=None: [
            {
                "industry_code": "BK0428",
                "industry_name": "半导体",
                "close": 105.0,
                "preclose": 100.0,
                "amount": 88000000000.0,
                "main_net_inflow": 1200000000.0,
                "main_net_inflow_ratio": 0.0136,
                "leading_stock_name": "寒武纪",
                "source": "vendor_a",
                "updated_at": "2026-06-26T15:41:00+08:00",
            },
            {
                "industry_code": "BK0430",
                "industry_name": "软件服务",
                "close": 102.0,
                "preclose": 100.0,
                "amount": 65000000000.0,
                "main_net_inflow": 300000000.0,
                "main_net_inflow_ratio": 0.0046,
                "leading_stock_name": "金山办公",
                "source": "vendor_a",
                "updated_at": "2026-06-26T15:41:00+08:00",
            },
            {
                "industry_code": "BK0477",
                "industry_name": "消费电子",
                "close": 97.0,
                "preclose": 100.0,
                "amount": 72000000000.0,
                "main_net_inflow": -800000000.0,
                "main_net_inflow_ratio": -0.0111,
                "leading_stock_name": "立讯精密",
                "source": "vendor_a",
                "updated_at": "2026-06-26T15:41:00+08:00",
            },
            {
                "industry_code": "BK0488",
                "industry_name": "元器件",
                "close": 96.0,
                "preclose": 100.0,
                "amount": 50000000000.0,
                "main_net_inflow": -100000000.0,
                "main_net_inflow_ratio": -0.002,
                "leading_stock_name": "沪电股份",
                "source": "vendor_a",
                "updated_at": "2026-06-26T15:41:00+08:00",
            },
        ],
    )

    payload = sector_fund_flow_service.build_sector_fund_flow_payload(
        "2026-06-26",
        sector_type="industry",
        period="1d",
    )

    assert payload["source"] == "vendor_a"
    assert payload["data_status"] == "completed"
    assert payload["warnings"] == [
        "fund flow values are third-party directional signals and may be incomplete"
    ]
    assert [item["sector_id"] for item in payload["inflow"]] == ["BK0428", "BK0430"]
    assert [item["rank"] for item in payload["inflow"]] == [1, 2]
    assert payload["inflow"][0]["sector_name"] == "半导体"
    assert payload["inflow"][0]["sector_type"] == "industry"
    assert payload["inflow"][0]["change_pct"] == pytest.approx(0.05)
    assert payload["inflow"][0]["main_net_inflow_ratio"] == pytest.approx(0.0136)
    assert [item["sector_id"] for item in payload["outflow"]] == ["BK0477", "BK0488"]
    assert [item["rank"] for item in payload["outflow"]] == [1, 2]
    assert payload["outflow"][0]["change_pct"] == pytest.approx(-0.03)


def test_build_sector_detail_payload_returns_partial_when_fund_flow_fields_are_missing(monkeypatch):
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
            "main_net_inflow": None,
            "main_net_inflow_ratio": None,
            "source": "industry_daily_bar",
            "updated_at": "2026-06-26T15:35:00+08:00",
        },
    )
    monkeypatch.setattr(
        sector_detail_service,
        "load_sector_leading_stocks",
        lambda trade_date, sector_id, sector_type, service=None, limit=10: [
            {
                "asset_id": "688256.SH",
                "name": "寒武纪",
                "pct_chg": 12.5,
                "source": "market_daily_bar",
                "updated_at": "2026-06-26T15:36:00+08:00",
            }
        ],
    )

    payload = sector_detail_service.build_sector_detail_payload(
        "2026-06-26",
        sector_id="BK0428",
        sector_type="industry",
    )

    assert payload["data_status"] == "partial"
    assert payload["warnings"] == [
        "fund flow fields are unavailable for sector detail; returning partial payload"
    ]
    assert payload["leading_stocks"] == [
        {
            "asset_id": "688256.SH",
            "name": "寒武纪",
            "change_pct": 0.125,
        }
    ]
