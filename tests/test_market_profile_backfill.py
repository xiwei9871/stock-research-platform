from __future__ import annotations

import os

import pandas as pd

from stock_research import market_profile_backfill as backfill


class FakeConnection:
    def __init__(self):
        self.executed_many = []


def fake_execute_many(conn, sql, rows):
    conn.executed_many.append((sql, list(rows)))


def test_normalize_tushare_stock_basic_region_rows_uses_area_and_ts_code():
    frame = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "area": "深圳",
                "industry": "银行",
            },
            {
                "ts_code": "600000.SH",
                "symbol": "600000",
                "name": "浦发银行",
                "area": "上海",
                "industry": "银行",
            },
            {
                "ts_code": "000004.SZ",
                "symbol": "000004",
                "name": "国华退",
                "area": "",
                "industry": "",
            },
        ]
    )

    rows = backfill.normalize_tushare_stock_basic_region_rows(frame)

    assert rows == [
        {
            "asset_id": "CN:SZ:000001",
            "ts_code": "000001.SZ",
            "region": "深圳",
            "source": "tushare:stock_basic",
        },
        {
            "asset_id": "CN:SH:600000",
            "ts_code": "600000.SH",
            "region": "上海",
            "source": "tushare:stock_basic",
        },
    ]


def test_upsert_asset_region_rows_updates_region_without_touching_empty_rows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(backfill, "execute_many", fake_execute_many)

    count = backfill.upsert_asset_region_rows(
        conn,
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "region": "深圳",
                "source": "tushare:stock_basic",
            }
        ],
    )

    assert count == 1
    sql, rows = conn.executed_many[0]
    assert "UPDATE core.asset_master" in sql
    assert "region = data.region" in sql
    assert "ts_code = COALESCE(NULLIF(a.ts_code, ''), data.ts_code)" in sql
    assert rows == [("CN:SZ:000001", "000001.SZ", "深圳", "tushare:stock_basic")]


def test_normalize_em_profit_sheet_rows_maps_parent_profit_fields():
    payload = [
        {
            "SECUCODE": "000001.SZ",
            "REPORT_DATE": "2025-12-31 00:00:00",
            "REPORT_TYPE": "年报",
            "NOTICE_DATE": "2026-03-21 00:00:00",
            "OPERATE_INCOME": 131442000000.0,
            "OPERATE_PROFIT": 51408000000.0,
            "TOTAL_PROFIT": 51159000000.0,
            "NETPROFIT": 42633000000.0,
            "PARENT_NETPROFIT": 42633000000.0,
            "DEDUCT_PARENT_NETPROFIT": 42624000000.0,
            "BASIC_EPS": 2.07,
        }
    ]

    rows = backfill.normalize_em_profit_sheet_rows(payload)

    assert rows == [
        {
            "asset_id": "CN:SZ:000001",
            "report_period": "2025-12-31",
            "report_type": "FY",
            "announcement_date": "2026-03-21",
            "revenue": 131442000000.0,
            "operating_profit": 51408000000.0,
            "total_profit": 51159000000.0,
            "net_profit": 42633000000.0,
            "np_parent": 42633000000.0,
            "np_parent_deducted": 42624000000.0,
            "eps_basic": 2.07,
            "source": "akshare_em_profit_sheet",
        }
    ]


def test_no_proxy_env_sets_no_proxy_and_restores_previous_values():
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
    os.environ["NO_PROXY"] = "localhost"

    with backfill.no_proxy_env():
        assert "HTTP_PROXY" not in os.environ
        assert os.environ["NO_PROXY"] == "*"
        assert os.environ["no_proxy"] == "*"

    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert os.environ["NO_PROXY"] == "localhost"
