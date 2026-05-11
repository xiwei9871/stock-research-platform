from stock_research.loaders import baostock_ingestion


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


def test_normalize_index_constituent_row_maps_asset():
    row = {
        "code": "sh.600000",
        "code_name": "浦发银行",
    }

    normalized = baostock_ingestion.normalize_index_constituent_row(
        "CSI_300",
        "2024-05-31",
        row,
        "baostock_snapshot_v1",
    )

    assert normalized["index_id"] == "CSI_300"
    assert normalized["asset_id"] == "CN:SH:600000"
    assert normalized["start_date"] == "2024-05-31"
    assert normalized["end_date"] is None
    assert normalized["source_version"] == "baostock_snapshot_v1"


def test_upsert_index_constituents(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(baostock_ingestion, "execute_many", fake_execute_many)

    count = baostock_ingestion.upsert_index_constituents(
        conn,
        [
            {
                "index_id": "CSI_300",
                "asset_id": "CN:SH:600000",
                "start_date": "2024-05-31",
                "end_date": None,
                "weight": None,
                "source": "baostock",
                "source_version": "baostock_snapshot_v1",
            }
        ],
    )

    sql, rows = conn.many_calls[0]
    assert count == 1
    assert "INSERT INTO market.index_constituent" in sql
    assert "ON CONFLICT" in sql
    assert rows[0][0] == "CSI_300"


def test_sync_index_constituents_uses_selected_targets(monkeypatch):
    conn = FakeConnection()
    calls = []

    class FakeResult:
        error_code = "0"
        error_msg = ""
        fields = ["code", "code_name"]

        def __init__(self, rows):
            self._rows = rows
            self._index = 0

        def next(self):
            if self._index >= len(self._rows):
                return False
            self._row = self._rows[self._index]
            self._index += 1
            return True

        def get_row_data(self):
            return [self._row["code"], self._row["code_name"]]

    monkeypatch.setattr(baostock_ingestion.bs, "login", lambda: type("Login", (), {"error_code": "0", "error_msg": ""})())
    monkeypatch.setattr(baostock_ingestion.bs, "logout", lambda: None)
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "query_hs300_stocks",
        lambda date="": FakeResult([{"code": "sh.600000", "code_name": "浦发银行"}]),
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "INDEX_CONSTITUENT_TARGETS",
        {"CSI_300": baostock_ingestion.bs.query_hs300_stocks},
    )
    monkeypatch.setattr(baostock_ingestion, "connect", lambda service: _ConnectionContext(conn))
    monkeypatch.setattr(
        baostock_ingestion,
        "upsert_index_constituents",
        lambda opened, rows: calls.append((opened, rows)) or len(rows),
    )

    count = baostock_ingestion.sync_index_constituents(
        trade_date="2024-05-31",
        index_ids=["CSI_300"],
        source_version="baostock_snapshot_v1",
    )

    assert count == 1
    assert calls[0][1][0]["index_id"] == "CSI_300"
