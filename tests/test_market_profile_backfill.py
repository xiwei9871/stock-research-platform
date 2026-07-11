from __future__ import annotations

import os
import sys
from types import SimpleNamespace

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


def test_normalize_cninfo_stock_profile_region_rows_derives_region_from_address():
    frame = pd.DataFrame(
        [
            {"A股代码": "000001", "A股简称": "平安银行", "注册地址": "广东省深圳市罗湖区深南东路5047号"},
            {"A股代码": "600000", "A股简称": "浦发银行", "注册地址": "上海市中山东一路12号"},
            {"A股代码": "430001", "A股简称": "北交样本", "注册地址": "北京市西城区金融大街1号"},
            {"A股代码": "000004", "A股简称": "国华退", "注册地址": ""},
        ]
    )

    rows = backfill.normalize_cninfo_stock_profile_region_rows(frame)

    assert rows == [
        {
            "asset_id": "CN:SZ:000001",
            "ts_code": "000001.SZ",
            "region": "深圳",
            "source": "akshare:stock_profile_cninfo",
        },
        {
            "asset_id": "CN:SH:600000",
            "ts_code": "600000.SH",
            "region": "上海",
            "source": "akshare:stock_profile_cninfo",
        },
        {
            "asset_id": "CN:BJ:430001",
            "ts_code": "430001.BJ",
            "region": "北京",
            "source": "akshare:stock_profile_cninfo",
        },
    ]


def test_normalize_eastmoney_company_survey_region_rows_uses_province_and_address():
    rows = backfill.normalize_eastmoney_company_survey_region_rows(
        "CN:SH:600018",
        {
            "jbzl": [
                {
                    "SECUCODE": "600018.SH",
                    "SECURITY_CODE": "600018",
                    "SECURITY_NAME_ABBR": "上港集团",
                    "PROVINCE": "上海",
                    "REG_ADDRESS": "中国(上海)自由贸易试验区临港新片区同汇路1号",
                    "ADDRESS": "上海市虹口区东大名路358号",
                }
            ]
        },
    )

    assert rows == [
        {
            "asset_id": "CN:SH:600018",
            "ts_code": "600018.SH",
            "region": "上海",
            "source": "eastmoney:PC_HSF10_CompanySurvey",
        }
    ]


def test_normalize_eastmoney_company_survey_region_rows_falls_back_to_registered_address():
    rows = backfill.normalize_eastmoney_company_survey_region_rows(
        "CN:SZ:000638",
        {
            "jbzl": [
                {
                    "SECUCODE": "000638.SZ",
                    "PROVINCE": "",
                    "REG_ADDRESS": "吉林省白山市江源区江源大街30号",
                }
            ]
        },
    )

    assert rows[0]["region"] == "白山"
    assert rows[0]["ts_code"] == "000638.SZ"


def test_sync_regions_from_tushare_falls_back_to_akshare(monkeypatch):
    conn = FakeConnection()
    calls = []

    class FakeTushareClient:
        def stock_basic(self, **_kwargs):
            calls.append("tushare")
            raise RuntimeError("stock_basic frequency limit")

    class FakeAk:
        @staticmethod
        def stock_profile_cninfo(symbol):
            calls.append("akshare")
            assert symbol == "000001"
            return pd.DataFrame([{"A股代码": "000001", "A股简称": "平安银行", "注册地址": "广东省深圳市罗湖区"}])

    monkeypatch.setattr(backfill, "tushare_client_factory", lambda: FakeTushareClient())
    monkeypatch.setattr(backfill, "ak", FakeAk)
    monkeypatch.setattr(backfill, "load_region_gap_assets", lambda limit=None, offset=0, service="stock_research": [{"asset_id": "CN:SZ:000001", "symbol": "000001"}])
    monkeypatch.setattr(backfill, "connect", lambda _service: conn_context(conn))
    monkeypatch.setattr(backfill, "execute_many", fake_execute_many)

    summary = backfill.sync_regions_from_tushare(fallback_limit=1)

    assert calls == ["tushare", "akshare"]
    assert summary == {
        "source": "akshare:stock_profile_cninfo",
        "source_rows": 1,
        "region_rows": 1,
        "updated_rows": 1,
    }
    assert conn.executed_many[0][1] == [("CN:SZ:000001", "000001.SZ", "深圳", "akshare:stock_profile_cninfo")]


def test_sync_regions_from_akshare_profiles_supports_workers_and_batch_flush(monkeypatch):
    conn = FakeConnection()
    seen_symbols = []
    executor_sizes = []

    class ImmediateExecutor:
        def __init__(self, max_workers):
            executor_sizes.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def map(self, func, assets):
            return [func(asset) for asset in assets]

    class FakeAk:
        @staticmethod
        def stock_profile_cninfo(symbol):
            seen_symbols.append(symbol)
            return pd.DataFrame(
                [
                    {
                        "A股代码": symbol,
                        "A股简称": symbol,
                        "注册地址": "广东省深圳市南山区",
                    }
                ]
            )

    monkeypatch.setattr(backfill, "ak", FakeAk)
    monkeypatch.setattr(
        backfill,
        "load_region_gap_assets",
        lambda limit=None, offset=0, service="stock_research": [
            {"asset_id": "CN:SZ:000001", "symbol": "000001"},
            {"asset_id": "CN:SZ:000002", "symbol": "000002"},
        ],
    )
    monkeypatch.setattr(backfill, "connect", lambda _service: conn_context(conn))
    monkeypatch.setattr(backfill, "execute_many", fake_execute_many)

    summary = backfill.sync_regions_from_akshare_profiles(
        limit=2,
        workers=2,
        batch_size=1,
        executor_factory=ImmediateExecutor,
    )

    assert executor_sizes == [2]
    assert sorted(seen_symbols) == ["000001", "000002"]
    assert summary == {
        "source": "akshare:stock_profile_cninfo",
        "source_rows": 2,
        "region_rows": 2,
        "updated_rows": 2,
    }
    assert len(conn.executed_many) == 2
    assert all(len(rows) == 1 for _sql, rows in conn.executed_many)


def test_sync_regions_from_eastmoney_company_survey_supports_workers_and_batch_flush(monkeypatch):
    conn = FakeConnection()
    executor_sizes = []

    class ImmediateExecutor:
        def __init__(self, max_workers):
            executor_sizes.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def map(self, func, assets):
            return [func(asset) for asset in assets]

    monkeypatch.setattr(
        backfill,
        "load_region_gap_assets",
        lambda limit=None, offset=0, service="stock_research": [
            {"asset_id": "CN:SH:600018", "symbol": "600018"},
            {"asset_id": "CN:SH:688018", "symbol": "688018"},
        ],
    )
    monkeypatch.setattr(
        backfill,
        "fetch_eastmoney_company_survey_region_rows_for_asset",
        lambda asset: (
            1,
            [
                {
                    "asset_id": asset["asset_id"],
                    "ts_code": f"{asset['symbol']}.SH",
                    "region": "上海",
                    "source": "eastmoney:PC_HSF10_CompanySurvey",
                }
            ],
        ),
    )
    monkeypatch.setattr(backfill, "connect", lambda _service: conn_context(conn))
    monkeypatch.setattr(backfill, "execute_many", fake_execute_many)

    summary = backfill.sync_regions_from_eastmoney_company_survey(
        limit=2,
        workers=2,
        batch_size=1,
        executor_factory=ImmediateExecutor,
    )

    assert executor_sizes == [2]
    assert summary == {
        "source": "eastmoney:PC_HSF10_CompanySurvey",
        "source_rows": 2,
        "region_rows": 2,
        "updated_rows": 2,
    }
    assert len(conn.executed_many) == 2


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


def test_normalize_eastmoney_core_conception_rows_skips_generic_scope():
    rows = backfill.normalize_eastmoney_core_conception_rows(
        "CN:SH:603016",
        {
            "hxtc": [
                {"KEYWORD": "经营范围", "KEY_CLASSIF_CODE": "002"},
                {"KEYWORD": "低压断路器", "KEY_CLASSIF_CODE": "003"},
                {"KEYWORD": "模塑绝缘制品", "KEY_CLASSIF_CODE": "003"},
                {"KEYWORD": "", "KEY_CLASSIF_CODE": "003"},
            ]
        },
        trade_date="2026-07-09",
    )

    assert rows == [
        {
            "asset_id": "CN:SH:603016",
            "concept_system": "em_core_conception",
            "concept_code": "低压断路器",
            "concept_name": "低压断路器",
            "start_date": "2026-07-09",
            "source": "eastmoney:PC_HSF10_CoreConception",
        },
        {
            "asset_id": "CN:SH:603016",
            "concept_system": "em_core_conception",
            "concept_code": "模塑绝缘制品",
            "concept_name": "模塑绝缘制品",
            "start_date": "2026-07-09",
            "source": "eastmoney:PC_HSF10_CoreConception",
        },
    ]


def test_sync_eastmoney_core_conceptions_for_gap_assets_upserts_rows(monkeypatch):
    conn = FakeConnection()

    monkeypatch.setattr(
        backfill,
        "load_concept_gap_assets",
        lambda limit=None, offset=0, service="stock_research": [
            {"asset_id": "CN:SH:603016", "symbol": "603016", "exchange": "SH"}
        ],
    )
    monkeypatch.setattr(
        backfill,
        "fetch_eastmoney_core_conception_payload",
        lambda asset_id: {
            "hxtc": [
                {"KEYWORD": "经营范围", "KEY_CLASSIF_CODE": "002"},
                {"KEYWORD": "低压断路器", "KEY_CLASSIF_CODE": "003"},
            ]
        },
    )
    monkeypatch.setattr(backfill, "connect", lambda _service: conn_context(conn))
    monkeypatch.setattr(backfill, "execute_many", fake_execute_many)

    summary = backfill.sync_eastmoney_core_conceptions_for_gap_assets(limit=1, trade_date="2026-07-09")

    assert summary == {"assets": 1, "concepts": 1, "memberships": 1, "failed_assets": 0}
    board_sql, board_rows = conn.executed_many[0]
    member_sql, member_rows = conn.executed_many[1]
    assert "INSERT INTO core.concept_board" in board_sql
    assert board_rows == [("em_core_conception", "低压断路器", "低压断路器", "eastmoney:PC_HSF10_CoreConception", True)]
    assert "INSERT INTO core.concept_membership" in member_sql
    assert member_rows == [
        (
            "CN:SH:603016",
            "em_core_conception",
            "低压断路器",
            "低压断路器",
            "2026-07-09",
            "eastmoney:PC_HSF10_CoreConception",
        )
    ]


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


def test_sync_em_profit_sheet_gap_assets_retries_once_then_skips(monkeypatch):
    calls = []

    def fake_sync(asset_id, service="stock_research"):
        calls.append(asset_id)
        if asset_id == "CN:SZ:000001" and calls.count(asset_id) == 1:
            raise ConnectionError("temporary vendor error")
        if asset_id == "CN:SH:600000":
            raise ConnectionError("persistent vendor error")
        return {"income_statement": 2, "raw_payload": 1}

    monkeypatch.setattr(
        backfill,
        "load_np_parent_gap_assets",
        lambda limit, offset=0, service="stock_research": ["CN:SZ:000001", "CN:SH:600000"],
    )
    monkeypatch.setattr(backfill, "sync_em_profit_sheet_for_asset", fake_sync)

    summary = backfill.sync_em_profit_sheet_gap_assets(limit=2)

    assert calls == ["CN:SZ:000001", "CN:SZ:000001", "CN:SH:600000", "CN:SH:600000"]
    assert summary == {"assets": 2, "income_statement": 2, "raw_payload": 1, "failed_assets": 1}


def test_sync_em_profit_sheet_gap_assets_supports_workers(monkeypatch):
    executor_sizes = []

    class ImmediateExecutor:
        def __init__(self, max_workers):
            executor_sizes.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def map(self, func, items):
            return [func(item) for item in items]

    monkeypatch.setattr(
        backfill,
        "load_np_parent_gap_assets",
        lambda limit, offset=0, service="stock_research": ["CN:SZ:000001", "CN:SH:600000"],
    )
    monkeypatch.setattr(
        backfill,
        "sync_em_profit_sheet_for_asset_worker",
        lambda item: {"raw_payload": 1, "income_statement": 2, "failed": 0},
    )

    summary = backfill.sync_em_profit_sheet_gap_assets(limit=2, workers=2, executor_factory=ImmediateExecutor)

    assert executor_sizes == [2]
    assert summary == {"assets": 2, "income_statement": 4, "raw_payload": 2, "failed_assets": 0}


def test_sync_em_profit_sheet_for_asset_suppresses_vendor_progress(monkeypatch, capsys):
    conn = FakeConnection()
    stored_payloads = []
    upserted_rows = []

    def fake_stock_profit_sheet_by_report_em(symbol):
        print("vendor stdout progress")
        print("vendor stderr progress", file=sys.stderr)
        assert symbol == "SZ000001"
        return pd.DataFrame(
            [
                {
                    "SECUCODE": "000001.SZ",
                    "REPORT_DATE": "2025-12-31 00:00:00",
                    "REPORT_TYPE": "年报",
                    "NOTICE_DATE": "2026-03-21 00:00:00",
                    "PARENT_NETPROFIT": 42633000000.0,
                }
            ]
        )

    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(stock_profit_sheet_by_report_em=fake_stock_profit_sheet_by_report_em),
    )
    monkeypatch.setattr(backfill, "connect", lambda _service: conn_context(conn))
    monkeypatch.setattr(
        backfill,
        "store_finance_payload",
        lambda _conn, _endpoint, _params, payload, asset_id=None: stored_payloads.append((asset_id, payload)),
    )
    monkeypatch.setattr(
        backfill,
        "upsert_income_statements",
        lambda _conn, rows: upserted_rows.append(list(rows)) or len(rows),
    )

    summary = backfill.sync_em_profit_sheet_for_asset("CN:SZ:000001")

    assert summary == {"raw_payload": 1, "income_statement": 1, "source_rows": 1}
    assert stored_payloads[0][0] == "CN:SZ:000001"
    assert upserted_rows[0][0]["np_parent"] == 42633000000.0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_sync_em_profit_sheet_for_asset_falls_back_to_direct_eastmoney_payload(monkeypatch):
    conn = FakeConnection()
    stored_payloads = []
    upserted_rows = []

    def fake_stock_profit_sheet_by_report_em(symbol):
        assert symbol == "SH600193"
        raise ConnectionError("akshare company type probe failed")

    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(stock_profit_sheet_by_report_em=fake_stock_profit_sheet_by_report_em),
    )
    monkeypatch.setattr(
        backfill,
        "fetch_eastmoney_profit_sheet_payload_direct",
        lambda asset_id: [
            {
                "SECUCODE": "600193.SH",
                "REPORT_DATE": "2025-12-31 00:00:00",
                "REPORT_TYPE": "年报",
                "NOTICE_DATE": "2026-04-28 00:00:00",
                "OPERATE_INCOME": 321460837.05,
                "TOTAL_PROFIT": -31151456.4,
                "NETPROFIT": -33448101.79,
                "PARENT_NETPROFIT": -33448101.79,
                "DEDUCT_PARENT_NETPROFIT": -88870949.16,
                "BASIC_EPS": -0.079,
            }
        ],
    )
    monkeypatch.setattr(backfill, "connect", lambda _service: conn_context(conn))
    monkeypatch.setattr(
        backfill,
        "store_finance_payload",
        lambda _conn, endpoint, params, payload, asset_id=None: stored_payloads.append(
            (endpoint, params, asset_id, payload)
        ),
    )
    monkeypatch.setattr(
        backfill,
        "upsert_income_statements",
        lambda _conn, rows: upserted_rows.append(list(rows)) or len(rows),
    )

    summary = backfill.sync_em_profit_sheet_for_asset("CN:SH:600193")

    assert summary == {"raw_payload": 1, "income_statement": 1, "source_rows": 1}
    assert stored_payloads[0][0] == "stock_profit_sheet_by_report_em"
    assert stored_payloads[0][1] == {"symbol": "SH600193", "fallback": "eastmoney_direct"}
    assert upserted_rows[0][0]["np_parent"] == -33448101.79
    assert upserted_rows[0][0]["source"] == "akshare_em_profit_sheet"


def test_no_proxy_env_sets_no_proxy_and_restores_previous_values():
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
    os.environ["NO_PROXY"] = "localhost"

    with backfill.no_proxy_env():
        assert "HTTP_PROXY" not in os.environ
        assert os.environ["NO_PROXY"] == "*"
        assert os.environ["no_proxy"] == "*"

    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert os.environ["NO_PROXY"] == "localhost"


class conn_context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False
