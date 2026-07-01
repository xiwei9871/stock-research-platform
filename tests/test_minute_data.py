import datetime as dt
import types

from stock_research import minute_data
from stock_research.minute_data import (
    adjustflag_for_adjust_type,
    baostock_frequency,
    minute_market_row,
    minute_staging_row,
    parse_baostock_trade_time,
    ts_code_from_baostock_code,
    upsert_stock_minute_bars,
)


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def raw_minute_row() -> dict:
    return {
        "date": "2024-01-02",
        "time": "20240102093500000",
        "code": "sh.600000",
        "open": "6.6300",
        "high": "6.6400",
        "low": "6.6100",
        "close": "6.6200",
        "volume": "1902300",
        "amount": "12603192.0000",
    }


def test_parse_baostock_trade_time_uses_minute_timestamp():
    assert parse_baostock_trade_time("20240102093500000") == dt.datetime(
        2024, 1, 2, 9, 35
    )


def test_frequency_and_adjust_type_map_to_baostock_parameters():
    assert baostock_frequency("5min") == "5"
    assert adjustflag_for_adjust_type("raw") == "3"
    assert adjustflag_for_adjust_type("qfq") == "2"
    assert adjustflag_for_adjust_type("hfq") == "1"


def test_minute_market_row_normalizes_baostock_payload():
    row = minute_market_row(raw_minute_row(), freq="5min", adjust_type="raw")

    assert row["asset_id"] == "CN:SH:600000"
    assert row["ts_code"] == "600000.SH"
    assert row["trade_time"] == dt.datetime(2024, 1, 2, 9, 35)
    assert row["trade_date"] == dt.date(2024, 1, 2)
    assert row["freq"] == "5min"
    assert row["adjust_type"] == "raw"
    assert row["open"] == 6.63
    assert row["amount"] == 12603192.0
    assert row["source"] == "baostock"


def test_minute_staging_row_preserves_raw_payload_hash():
    row = minute_staging_row(raw_minute_row(), freq="5min", adjust_type="raw")

    assert row["source_endpoint"] == "query_history_k_data_plus"
    assert row["baostock_code"] == "sh.600000"
    assert row["trade_time"] == dt.datetime(2024, 1, 2, 9, 35)
    assert row["payload"] == raw_minute_row()
    assert len(row["payload_hash"]) == 64


def test_upsert_stock_minute_bars_writes_staging_and_market(monkeypatch):
    calls = []

    def fake_execute_many(conn, sql, rows):
        calls.append((conn, sql, list(rows)))

    monkeypatch.setattr(minute_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(minute_data, "execute_many", fake_execute_many)

    assert upsert_stock_minute_bars([raw_minute_row()], freq="5min", adjust_type="qfq") == 1

    assert len(calls) == 2
    assert "INSERT INTO staging.baostock_stock_minute_bar" in calls[0][1]
    assert "INSERT INTO market.stock_minute_bar" in calls[1][1]
    assert "ON CONFLICT (trade_date, asset_id, trade_time, freq, adjust_type, source)" in calls[1][1]
    assert calls[1][2][0]["adjust_type"] == "qfq"


def test_query_baostock_minute_rows_uses_frequency_and_adjustflag(monkeypatch):
    class Result:
        error_code = "0"
        error_msg = "success"
        fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount"]

        def __init__(self):
            self.rows = [list(raw_minute_row().values())]
            self.index = -1

        def next(self):
            self.index += 1
            return self.index < len(self.rows)

        def get_row_data(self):
            return self.rows[self.index]

    calls = []

    def fake_query(code, fields, **kwargs):
        calls.append((code, fields, kwargs))
        return Result()

    monkeypatch.setattr(minute_data.bs, "query_history_k_data_plus", fake_query)

    rows = minute_data.query_baostock_minute_rows(
        "sh.600000",
        dt.date(2024, 1, 2),
        dt.date(2024, 1, 2),
        freq="5min",
        adjust_type="qfq",
    )

    assert len(rows) == 1
    assert calls[0][0] == "sh.600000"
    assert calls[0][2]["frequency"] == "5"
    assert calls[0][2]["adjustflag"] == "2"


def test_query_baostock_minute_rows_applies_socket_timeout(monkeypatch):
    class Result:
        error_code = "0"
        error_msg = "success"
        fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount"]

        def __init__(self):
            self.rows = [list(raw_minute_row().values())]
            self.index = -1

        def next(self):
            self.index += 1
            return self.index < len(self.rows)

        def get_row_data(self):
            return self.rows[self.index]

    observed = {"timeouts": []}

    monkeypatch.setattr(minute_data.socket, "getdefaulttimeout", lambda: None)
    monkeypatch.setattr(
        minute_data.socket,
        "setdefaulttimeout",
        observed["timeouts"].append,
    )
    monkeypatch.setattr(
        minute_data.bs,
        "query_history_k_data_plus",
        lambda *args, **kwargs: Result(),
    )

    minute_data.query_baostock_minute_rows(
        "sh.600000",
        dt.date(2024, 1, 2),
        dt.date(2024, 1, 2),
        freq="5min",
        adjust_type="qfq",
        timeout_seconds=7,
    )

    assert observed["timeouts"] == [7, None]


def test_query_baostock_minute_rows_retries_network_errors(monkeypatch):
    class Result:
        fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount"]

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
        error_msg = "success"

    calls = {"query": 0, "login": 0, "logout": 0}

    def fake_query(*args, **kwargs):
        calls["query"] += 1
        if calls["query"] == 1:
            return Result("10002007", "网络接收错误")
        return Result("0", rows=[list(raw_minute_row().values())])

    monkeypatch.setattr(minute_data.time, "sleep", lambda _: None)
    monkeypatch.setattr(minute_data.bs, "query_history_k_data_plus", fake_query)
    monkeypatch.setattr(minute_data.bs, "login", lambda: calls.__setitem__("login", calls["login"] + 1) or Login())
    monkeypatch.setattr(minute_data.bs, "logout", lambda: calls.__setitem__("logout", calls["logout"] + 1))

    rows = minute_data.query_baostock_minute_rows(
        "sh.600000",
        dt.date(2024, 1, 2),
        dt.date(2024, 1, 2),
        freq="5min",
        adjust_type="raw",
    )

    assert len(rows) == 1
    assert calls == {"query": 2, "login": 1, "logout": 1}


def test_login_or_raise_applies_socket_timeout(monkeypatch):
    class Login:
        error_code = "0"
        error_msg = "success"

    observed = {"timeouts": []}

    monkeypatch.setattr(minute_data.socket, "getdefaulttimeout", lambda: None)
    monkeypatch.setattr(
        minute_data.socket,
        "setdefaulttimeout",
        observed["timeouts"].append,
    )
    monkeypatch.setattr(minute_data.bs, "login", lambda: Login())

    minute_data.login_or_raise(timeout_seconds=9)

    assert observed["timeouts"] == [9, None]


def test_login_or_raise_uses_configured_socks_proxy(monkeypatch):
    class Login:
        error_code = "0"
        error_msg = "success"

    proxy_calls = []
    fake_socks = types.SimpleNamespace(
        SOCKS5="SOCKS5",
        socksocket="proxied-socket",
        setdefaultproxy=lambda *args, **kwargs: proxy_calls.append((args, kwargs)),
    )
    fake_socket_module = types.SimpleNamespace(
        socket=types.SimpleNamespace(socket="original-socket")
    )

    monkeypatch.setenv("BAOSTOCK_PROXY_HOST", "192.168.3.213")
    monkeypatch.setenv("BAOSTOCK_PROXY_PORT", "7897")
    monkeypatch.setattr(minute_data, "_load_socks_module", lambda: fake_socks)
    monkeypatch.setattr(
        minute_data,
        "_load_baostock_socket_module",
        lambda: fake_socket_module,
    )

    def fake_login():
        assert fake_socket_module.socket.socket == "proxied-socket"
        return Login()

    monkeypatch.setattr(minute_data.bs, "login", fake_login)

    minute_data.login_or_raise(timeout_seconds=9)

    assert proxy_calls == [
        (("SOCKS5", "192.168.3.213", 7897), {"rdns": True}),
        ((), {}),
    ]
    assert fake_socket_module.socket.socket == "original-socket"


def test_login_or_raise_retries_transient_network_error(monkeypatch):
    class Login:
        def __init__(self, error_code, error_msg=""):
            self.error_code = error_code
            self.error_msg = error_msg

    logins = [
        Login("10002007", "网络接收错误。"),
        Login("10002007", "网络接收错误。"),
        Login("0", "success"),
    ]
    sleeps = []

    monkeypatch.setattr(minute_data.bs, "login", lambda: logins.pop(0))
    monkeypatch.setattr(minute_data.time, "sleep", sleeps.append)

    minute_data.login_or_raise()

    assert sleeps == [
        minute_data.BAOSTOCK_RETRY_SLEEP_SECONDS,
        minute_data.BAOSTOCK_RETRY_SLEEP_SECONDS,
    ]


def test_ts_code_from_baostock_code_uses_tushare_order():
    assert ts_code_from_baostock_code("sh.600000") == "600000.SH"
    assert ts_code_from_baostock_code("sz.000001") == "000001.SZ"
