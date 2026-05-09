from stock_research.loaders import baostock_ingestion


class FakeConnection:
    def __init__(self):
        self.many_calls = []


def fake_execute_many(conn, sql, rows):
    conn.many_calls.append((sql, list(rows)))


def test_normalize_industry_row_maps_baostock_code():
    row = {
        "updateDate": "2026-05-04",
        "code": "sh.600000",
        "code_name": "浦发银行",
        "industry": "J66货币金融服务",
        "industryClassification": "证监会行业分类",
    }

    normalized = baostock_ingestion.normalize_industry_row(row)

    assert normalized["asset_id"] == "CN:SH:600000"
    assert normalized["industry_system"] == "csrc"
    assert normalized["industry_code"] == "J66"
    assert normalized["industry_name"] == "货币金融服务"
    assert normalized["start_date"] == "2026-05-04"
    assert normalized["source"] == "baostock"


def test_upsert_industry_memberships(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(baostock_ingestion, "execute_many", fake_execute_many)

    count = baostock_ingestion.upsert_industry_memberships(
        conn,
        [
            {
                "asset_id": "CN:SH:600000",
                "industry_system": "csrc",
                "industry_code": "J66",
                "industry_name": "货币金融服务",
                "level": 1,
                "start_date": "2026-05-04",
                "end_date": None,
                "source": "baostock",
            }
        ],
    )

    sql, rows = conn.many_calls[0]
    assert count == 1
    assert "INSERT INTO core.industry_membership" in sql
    assert "ON CONFLICT" in sql
    assert rows[0][0] == "CN:SH:600000"


def test_normalize_index_row_maps_market_bar():
    row = {
        "date": "2026-05-08",
        "code": "sh.000001",
        "open": "4180.0",
        "high": "4190.0",
        "low": "4170.0",
        "close": "4185.0",
        "preclose": "4180.1",
        "volume": "1000",
        "amount": "2000.5",
        "pctChg": "0.1",
    }

    normalized = baostock_ingestion.normalize_index_row("SSE_COMPOSITE", row)

    assert normalized["index_id"] == "SSE_COMPOSITE"
    assert normalized["trade_date"] == "2026-05-08"
    assert normalized["close"] == 4185.0
    assert normalized["volume"] == 1000.0


def test_upsert_index_daily_bars(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(baostock_ingestion, "execute_many", fake_execute_many)

    count = baostock_ingestion.upsert_index_daily_bars(
        conn,
        [
            {
                "index_id": "SSE_COMPOSITE",
                "trade_date": "2026-05-08",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "preclose": 1.4,
                "volume": 100.0,
                "amount": 200.0,
                "source": "baostock",
            }
        ],
    )

    sql, rows = conn.many_calls[0]
    assert count == 1
    assert "INSERT INTO market.index_daily_bar" in sql
    assert "ON CONFLICT" in sql
    assert rows[0][0] == "SSE_COMPOSITE"
