from stock_research.loaders import baostock_ingestion


class FakeConnection:
    def __init__(self):
        self.many_calls = []
        self.execute_calls = []


class _ConnectionContext:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def fake_execute_many(conn, sql, rows):
    conn.many_calls.append((sql, list(rows)))


def fake_execute(conn, sql, params=None):
    conn.execute_calls.append((sql, params))


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


def test_normalize_industry_row_can_use_query_date_as_effective_date():
    row = {
        "updateDate": "2026-05-04",
        "code": "sz.302132",
        "code_name": "测试股票",
        "industry": "C39计算机、通信和其他电子设备制造业",
        "industryClassification": "证监会行业分类",
    }

    normalized = baostock_ingestion.normalize_industry_row(
        row,
        effective_date="2024-05-31",
    )

    assert normalized["asset_id"] == "CN:SZ:302132"
    assert normalized["start_date"] == "2024-05-31"


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


def test_store_industry_snapshot_payload_writes_raw_cache(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(baostock_ingestion, "execute", fake_execute, raising=False)

    digest = baostock_ingestion.store_industry_snapshot_payload(
        conn,
        "2024-05-31",
        [{"code": "sh.600000", "industry": "J66货币金融服务"}],
    )

    sql, params = conn.execute_calls[0]
    assert "INSERT INTO raw_baostock.industry_snapshot_payload" in sql
    assert params["snapshot_date"] == "2024-05-31"
    assert params["source_endpoint"] == "query_stock_industry"
    assert params["row_count"] == 1
    assert params["payload_hash"] == digest


def test_load_cached_industry_snapshot_payload_returns_rows(monkeypatch):
    conn = FakeConnection()

    def fake_fetch_all(conn, sql, params=None):
        assert "FROM raw_baostock.industry_snapshot_payload" in sql
        assert params == ["2024-05-31", "query_stock_industry"]
        return [{"payload": '[{"code":"sh.600000","industry":"J66货币金融服务"}]'}]

    monkeypatch.setattr(baostock_ingestion, "fetch_all", fake_fetch_all, raising=False)

    rows = baostock_ingestion.load_cached_industry_snapshot_payload(conn, "2024-05-31")

    assert rows == [{"code": "sh.600000", "industry": "J66货币金融服务"}]


def test_sync_industry_memberships_uses_cached_snapshot(monkeypatch):
    conn = FakeConnection()
    calls = []

    monkeypatch.setattr(baostock_ingestion, "connect", lambda service: _ConnectionContext(conn))
    monkeypatch.setattr(
        baostock_ingestion,
        "load_cached_industry_snapshot_payload",
        lambda opened, trade_date: [
            {
                "updateDate": "2026-05-04",
                "code": "sh.600000",
                "industry": "J66货币金融服务",
                "industryClassification": "证监会行业分类",
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "upsert_industry_memberships",
        lambda opened, rows: calls.append((opened, rows)) or len(rows),
    )
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "login",
        lambda: (_ for _ in ()).throw(AssertionError("should not call baostock")),
    )

    count = baostock_ingestion.sync_industry_memberships("2024-05-31", use_cache=True)

    assert count == 1
    assert calls[0][1][0]["start_date"] == "2024-05-31"


def test_sync_industry_memberships_retries_transient_not_logged_in(monkeypatch):
    conn = FakeConnection()
    query_calls = []
    login_calls = []
    logout_calls = []
    upserted = []

    class Result:
        fields = ["updateDate", "code", "industry", "industryClassification"]

        def __init__(self, error_code, error_msg="", rows=None):
            self.error_code = error_code
            self.error_msg = error_msg
            self.rows = rows or []
            self.index = -1

        def next(self):
            self.index += 1
            return self.index < len(self.rows)

        def get_row_data(self):
            return self.rows[self.index]

    class Login:
        error_code = "0"
        error_msg = ""

    results = [
        Result("10001001", "用户未登录"),
        Result(
            "0",
            rows=[
                [
                    "2024-05-31",
                    "sh.600000",
                    "J66货币金融服务",
                    "证监会行业分类",
                ]
            ],
        ),
    ]

    monkeypatch.setattr(baostock_ingestion, "connect", lambda service: _ConnectionContext(conn))
    monkeypatch.setattr(
        baostock_ingestion,
        "load_cached_industry_snapshot_payload",
        lambda opened, trade_date: None,
        raising=False,
    )
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "login",
        lambda: login_calls.append(True) or Login(),
    )
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "logout",
        lambda: logout_calls.append(True),
    )
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "query_stock_industry",
        lambda date: query_calls.append(date) or results.pop(0),
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "store_industry_snapshot_payload",
        lambda opened, trade_date, rows: "digest",
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "upsert_industry_memberships",
        lambda opened, rows: upserted.append(rows) or len(rows),
    )

    count = baostock_ingestion.sync_industry_memberships("2024-05-31", use_cache=True)

    assert count == 1
    assert query_calls == ["2024-05-31", "2024-05-31"]
    assert len(login_calls) == 2
    assert len(logout_calls) == 2
    assert upserted[0][0]["asset_id"] == "CN:SH:600000"


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


def test_sync_index_constituents_retries_transient_not_logged_in(monkeypatch):
    conn = FakeConnection()
    login_calls = []
    logout_calls = []
    query_calls = []
    upserted = []

    class Result:
        fields = ["code", "code_name"]

        def __init__(self, error_code, error_msg="", rows=None):
            self.error_code = error_code
            self.error_msg = error_msg
            self.rows = rows or []
            self.index = -1

        def next(self):
            self.index += 1
            return self.index < len(self.rows)

        def get_row_data(self):
            return self.rows[self.index]

    class Login:
        error_code = "0"
        error_msg = ""

    results = [
        Result("10001001", "用户未登录"),
        Result("0", rows=[["sh.600000", "浦发银行"]]),
    ]

    monkeypatch.setattr(baostock_ingestion, "connect", lambda service: _ConnectionContext(conn))
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "login",
        lambda: login_calls.append(True) or Login(),
    )
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "logout",
        lambda: logout_calls.append(True),
    )
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "query_hs300_stocks",
        lambda date="": query_calls.append(date) or results.pop(0),
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "INDEX_CONSTITUENT_TARGETS",
        {"CSI_300": baostock_ingestion.bs.query_hs300_stocks},
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "upsert_index_constituents",
        lambda opened, rows: upserted.append(rows) or len(rows),
    )

    count = baostock_ingestion.sync_index_constituents(
        trade_date="2024-05-31",
        index_ids=["CSI_300"],
        source_version="baostock_snapshot_v1",
    )

    assert count == 1
    assert query_calls == ["2024-05-31", "2024-05-31"]
    assert len(login_calls) == 2
    assert len(logout_calls) == 2
    assert upserted[0][0]["asset_id"] == "CN:SH:600000"


def test_sync_index_constituents_retries_multiple_transient_not_logged_in(monkeypatch):
    conn = FakeConnection()
    login_calls = []
    logout_calls = []
    query_calls = []
    upserted = []

    class Result:
        fields = ["code", "code_name"]

        def __init__(self, error_code, error_msg="", rows=None):
            self.error_code = error_code
            self.error_msg = error_msg
            self.rows = rows or []
            self.index = -1

        def next(self):
            self.index += 1
            return self.index < len(self.rows)

        def get_row_data(self):
            return self.rows[self.index]

    class Login:
        error_code = "0"
        error_msg = ""

    results = [
        Result("10001001", "用户未登录"),
        Result("10001001", "用户未登录"),
        Result("0", rows=[["sh.600000", "浦发银行"]]),
    ]

    monkeypatch.setattr(baostock_ingestion, "connect", lambda service: _ConnectionContext(conn))
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "login",
        lambda: login_calls.append(True) or Login(),
    )
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "logout",
        lambda: logout_calls.append(True),
    )
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "query_hs300_stocks",
        lambda date="": query_calls.append(date) or results.pop(0),
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "INDEX_CONSTITUENT_TARGETS",
        {"CSI_300": baostock_ingestion.bs.query_hs300_stocks},
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "upsert_index_constituents",
        lambda opened, rows: upserted.append(rows) or len(rows),
    )

    count = baostock_ingestion.sync_index_constituents(
        trade_date="2024-05-31",
        index_ids=["CSI_300"],
        source_version="baostock_snapshot_v1",
    )

    assert count == 1
    assert query_calls == ["2024-05-31", "2024-05-31", "2024-05-31"]
    assert len(login_calls) == 3
    assert len(logout_calls) == 3
    assert upserted[0][0]["asset_id"] == "CN:SH:600000"


def test_login_or_raise_retries_transient_network_error(monkeypatch):
    class Login:
        def __init__(self, error_code, error_msg=""):
            self.error_code = error_code
            self.error_msg = error_msg

    logins = [
        Login("10002007", "网络接收错误。"),
        Login("10002007", "网络接收错误。"),
        Login("0"),
    ]
    sleeps = []

    monkeypatch.setattr(
        baostock_ingestion.bs,
        "login",
        lambda: logins.pop(0),
    )
    monkeypatch.setattr(baostock_ingestion.time, "sleep", sleeps.append)

    baostock_ingestion._login_or_raise()

    assert sleeps == [
        baostock_ingestion.BAOSTOCK_LOGIN_RETRY_SECONDS,
        baostock_ingestion.BAOSTOCK_LOGIN_RETRY_SECONDS,
    ]
