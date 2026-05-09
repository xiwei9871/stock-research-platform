from stock_research.loaders import akshare_finance_loader, baostock_finance_loader
from stock_research.loaders.raw_payloads import payload_hash, store_raw_payload


class FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj


def test_payload_hash_is_stable_for_key_order():
    left = {"symbol": "600000", "values": [{"b": 2, "a": 1}]}
    right = {"values": [{"a": 1, "b": 2}], "symbol": "600000"}

    assert payload_hash(left) == payload_hash(right)


def test_store_raw_payload_inserts_json_payload():
    conn = FakeConnection()

    stored_hash = store_raw_payload(
        conn,
        "raw_akshare.finance_payload",
        "stock_financial_report_sina",
        {"symbol": "600000"},
        {"rows": [{"revenue": 100}]},
        asset_id="CN:SH:600000",
    )

    sql, params = conn.cursor_obj.calls[0]
    assert "INSERT INTO raw_akshare.finance_payload" in sql
    assert "source_endpoint" in sql
    assert params["source_endpoint"] == "stock_financial_report_sina"
    assert params["request_params"] == '{"symbol":"600000"}'
    assert params["payload"] == '{"rows":[{"revenue":100}]}'
    assert params["asset_id"] == "CN:SH:600000"
    assert params["payload_hash"] == stored_hash


def test_akshare_loader_stores_in_akshare_raw_schema():
    conn = FakeConnection()

    akshare_finance_loader.store_finance_payload(
        conn,
        "stock_financial_report_sina",
        {"symbol": "600000"},
        {"rows": []},
        asset_id="CN:SH:600000",
    )

    sql, _params = conn.cursor_obj.calls[0]
    assert "INSERT INTO raw_akshare.finance_payload" in sql


def test_baostock_loader_stores_in_baostock_raw_schema():
    conn = FakeConnection()

    baostock_finance_loader.store_finance_payload(
        conn,
        "query_profit_data",
        {"code": "sh.600000"},
        {"rows": []},
        asset_id="CN:SH:600000",
    )

    sql, _params = conn.cursor_obj.calls[0]
    assert "INSERT INTO raw_baostock.finance_payload" in sql
