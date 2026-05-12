import pandas as pd

from stock_research.loaders import akshare_finance_statements


class FakeConnection:
    def __init__(self):
        self.many_calls = []


class _ConnectionContext:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def fake_execute_many(conn, sql, rows):
    conn.many_calls.append((sql, list(rows)))


def test_normalize_em_balance_sheet_row_maps_absolute_fields():
    row = {
        "SECUCODE": "600000.SH",
        "REPORT_DATE": "2025-12-31 00:00:00",
        "REPORT_TYPE": "年报",
        "NOTICE_DATE": "2026-03-31 00:00:00",
        "TOTAL_ASSETS": 100.0,
        "TOTAL_LIABILITIES": 60.0,
        "TOTAL_EQUITY": 40.0,
        "MONETARYFUNDS": 10.0,
        "ACCOUNTS_RECE": 2.0,
        "INVENTORY": 3.0,
        "GOODWILL": 4.0,
    }

    normalized = akshare_finance_statements.normalize_em_balance_sheet_row(row)

    assert normalized == {
        "asset_id": "CN:SH:600000",
        "report_period": "2025-12-31",
        "report_type": "FY",
        "announcement_date": "2026-03-31",
        "total_assets": 100.0,
        "total_liabilities": 60.0,
        "total_equity": 40.0,
        "monetary_funds": 10.0,
        "accounts_receivable": 2.0,
        "inventory": 3.0,
        "goodwill": 4.0,
        "source": "akshare_em",
    }


def test_normalize_em_cash_flow_row_maps_absolute_fields():
    row = {
        "SECUCODE": "600000.SH",
        "REPORT_DATE": "2025-12-31 00:00:00",
        "REPORT_TYPE": "年报",
        "NOTICE_DATE": "2026-03-31 00:00:00",
        "NETCASH_OPERATE": 20.0,
        "NETCASH_INVEST": -5.0,
        "NETCASH_FINANCE": -3.0,
        "CONSTRUCT_LONG_ASSET": 2.0,
    }

    normalized = akshare_finance_statements.normalize_em_cash_flow_row(row)

    assert normalized["asset_id"] == "CN:SH:600000"
    assert normalized["report_period"] == "2025-12-31"
    assert normalized["report_type"] == "FY"
    assert normalized["announcement_date"] == "2026-03-31"
    assert normalized["net_operate_cash_flow"] == 20.0
    assert normalized["net_invest_cash_flow"] == -5.0
    assert normalized["net_finance_cash_flow"] == -3.0
    assert normalized["capex"] == 2.0
    assert normalized["free_cash_flow"] == 18.0
    assert normalized["source"] == "akshare_em"


def test_normalize_sina_balance_sheet_row_maps_absolute_fields():
    row = {
        "报告日": "20070331",
        "公告日期": "20070420",
        "资产总计": 100.0,
        "负债合计": 60.0,
        "所有者权益(或股东权益)合计": 40.0,
        "货币资金": 10.0,
        "应收账款": 2.0,
        "存货": 3.0,
        "商誉": 4.0,
    }

    normalized = akshare_finance_statements.normalize_sina_balance_sheet_row(
        row,
        "CN:SZ:000987",
    )

    assert normalized == {
        "asset_id": "CN:SZ:000987",
        "report_period": "2007-03-31",
        "report_type": "Q",
        "announcement_date": "2007-04-20",
        "total_assets": 100.0,
        "total_liabilities": 60.0,
        "total_equity": 40.0,
        "monetary_funds": 10.0,
        "accounts_receivable": 2.0,
        "inventory": 3.0,
        "goodwill": 4.0,
        "source": "akshare_sina",
    }


def test_normalize_sina_cash_flow_row_maps_absolute_fields():
    row = {
        "报告日": "20081231",
        "公告日期": "20090410",
        "经营活动产生的现金流量净额": 20.0,
        "投资活动产生的现金流量净额": -5.0,
        "筹资活动产生的现金流量净额": -3.0,
        "购建固定资产、无形资产和其他长期资产支付的现金": 2.0,
    }

    normalized = akshare_finance_statements.normalize_sina_cash_flow_row(
        row,
        "CN:SH:600000",
    )

    assert normalized == {
        "asset_id": "CN:SH:600000",
        "report_period": "2008-12-31",
        "report_type": "FY",
        "announcement_date": "2009-04-10",
        "net_operate_cash_flow": 20.0,
        "net_invest_cash_flow": -5.0,
        "net_finance_cash_flow": -3.0,
        "capex": 2.0,
        "free_cash_flow": 18.0,
        "source": "akshare_sina",
    }


def test_upsert_balance_sheets_writes_statement_rows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(akshare_finance_statements, "execute_many", fake_execute_many)

    count = akshare_finance_statements.upsert_balance_sheets(
        conn,
        [
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2025-12-31",
                "report_type": "FY",
                "announcement_date": "2026-03-31",
                "total_assets": 100.0,
                "total_liabilities": 60.0,
                "total_equity": 40.0,
                "monetary_funds": 10.0,
                "accounts_receivable": 2.0,
                "inventory": 3.0,
                "goodwill": 4.0,
                "source": "akshare_em",
            }
        ],
    )

    sql, rows = conn.many_calls[0]
    assert count == 1
    assert "INSERT INTO finance.balance_sheet" in sql
    assert "ON CONFLICT" in sql
    assert rows[0][0] == "CN:SH:600000"


def test_upsert_cash_flows_writes_statement_rows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(akshare_finance_statements, "execute_many", fake_execute_many)

    count = akshare_finance_statements.upsert_cash_flows(
        conn,
        [
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2025-12-31",
                "report_type": "FY",
                "announcement_date": "2026-03-31",
                "net_operate_cash_flow": 20.0,
                "net_invest_cash_flow": -5.0,
                "net_finance_cash_flow": -3.0,
                "capex": 2.0,
                "free_cash_flow": 18.0,
                "source": "akshare_em",
            }
        ],
    )

    sql, rows = conn.many_calls[0]
    assert count == 1
    assert "INSERT INTO finance.cash_flow" in sql
    assert "ON CONFLICT" in sql
    assert rows[0][0] == "CN:SH:600000"


def test_upsert_statement_rows_returns_zero_for_empty_inputs():
    conn = FakeConnection()

    assert akshare_finance_statements.upsert_balance_sheets(conn, []) == 0
    assert akshare_finance_statements.upsert_cash_flows(conn, []) == 0
    assert conn.many_calls == []


def test_sync_finance_statements_for_asset_archives_raw_payloads_and_upserts(monkeypatch):
    conn = FakeConnection()
    raw_calls = []

    balance_frame = pd.DataFrame(
        [
            {
                "SECUCODE": "600000.SH",
                "REPORT_DATE": "2025-12-31 00:00:00",
                "REPORT_TYPE": "年报",
                "NOTICE_DATE": "2026-03-31 00:00:00",
                "TOTAL_ASSETS": 100.0,
                "TOTAL_LIABILITIES": 60.0,
                "TOTAL_EQUITY": 40.0,
                "ACCOUNTS_PAYABLE": float("nan"),
            }
        ]
    )
    cash_frame = pd.DataFrame(
        [
            {
                "SECUCODE": "600000.SH",
                "REPORT_DATE": "2025-12-31 00:00:00",
                "REPORT_TYPE": "年报",
                "NOTICE_DATE": "2026-03-31 00:00:00",
                "NETCASH_OPERATE": 20.0,
                "NETCASH_INVEST": -5.0,
                "NETCASH_FINANCE": -3.0,
                "CONSTRUCT_LONG_ASSET": 2.0,
            }
        ]
    )

    monkeypatch.setattr(akshare_finance_statements, "connect", lambda service: _ConnectionContext(conn))
    monkeypatch.setattr(
        akshare_finance_statements.ak,
        "stock_balance_sheet_by_report_em",
        lambda symbol: balance_frame,
    )
    monkeypatch.setattr(
        akshare_finance_statements.ak,
        "stock_cash_flow_sheet_by_report_em",
        lambda symbol: cash_frame,
    )
    monkeypatch.setattr(
        akshare_finance_statements,
        "store_finance_payload",
        lambda opened, endpoint, params, payload, asset_id=None: raw_calls.append(
            (endpoint, params, payload, asset_id)
        )
        or "digest",
    )
    monkeypatch.setattr(akshare_finance_statements, "execute_many", fake_execute_many)

    counts = akshare_finance_statements.sync_finance_statements_for_asset(
        "CN:SH:600000",
        "SH600000",
    )

    assert counts == {"balance_sheet": 1, "cash_flow": 1, "raw_payload": 2}
    assert [call[0] for call in raw_calls] == [
        "stock_balance_sheet_by_report_em",
        "stock_cash_flow_sheet_by_report_em",
    ]
    assert raw_calls[0][1] == {"symbol": "SH600000"}
    assert raw_calls[0][3] == "CN:SH:600000"
    assert raw_calls[0][2][0]["ACCOUNTS_PAYABLE"] is None
    assert len(conn.many_calls) == 2
