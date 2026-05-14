import pandas as pd

from stock_research import technical_feature_store


class FakeCursor:
    def __init__(self):
        self.executes = []
        self.copy_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executes.append((sql, params))

    def copy(self, sql):
        copy = FakeCopy(sql)
        self.copy_calls.append(copy)
        return copy


class FakeCopy:
    def __init__(self, sql):
        self.sql = sql
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def write_row(self, row):
        self.rows.append(tuple(row))


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def _bars_for_dates(asset_id: str, closes: list[float], *, start: str = "2026-01-01") -> pd.DataFrame:
    period_count = len(closes)
    return pd.DataFrame(
        {
            "asset_id": [asset_id] * period_count,
            "trade_date": pd.date_range(start, periods=period_count, freq="D"),
            "open": [close - 0.5 for close in closes],
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "preclose": [None] + closes[:-1],
            "volume": [1000.0 + index for index in range(period_count)],
            "amount": [10000.0 + index * 10.0 for index in range(period_count)],
            "turnover_rate": [1.0 + index * 0.01 for index in range(period_count)],
        }
    )


def test_technical_feature_store_columns_include_current_output_schema():
    assert technical_feature_store.TECHNICAL_FEATURE_METADATA_COLUMNS == [
        "trade_date",
        "asset_id",
        "ts_code",
        "adjust_type",
        "source",
        "source_data_version",
        "calc_version",
    ]
    assert technical_feature_store.TECHNICAL_FEATURE_TABLE_COLUMNS[-3:] == [
        "ret_1d",
        "ret_20d",
        "close_position_in_day",
    ]


def test_load_bars_for_technical_features_queries_adjusted_lookback(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return _bars_for_dates("000001.SZ", [10.0, 11.0]).to_dict("records")

    monkeypatch.setattr(technical_feature_store, "connect", lambda service: _context(object()))
    monkeypatch.setattr(technical_feature_store, "fetch_all", fake_fetch_all)

    result = technical_feature_store.load_bars_for_technical_features(
        "2026-01-02",
        lookback_bars=260,
        adjust_type="qfq",
    )

    assert list(result) == ["000001.SZ"]
    assert list(result["000001.SZ"].columns) == [
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "turnover_rate",
    ]
    assert "WITH lookback_dates AS" in calls[0][0]
    assert "FROM market_daily_bar bars" in calls[0][0]
    assert calls[0][1] == ["qfq", "2026-01-02", 260, "qfq"]


def test_build_stock_technical_features_daily_keeps_requested_trade_date(monkeypatch):
    bars = {
        "000001.SZ": _bars_for_dates("000001.SZ", [float(index) for index in range(1, 26)]).drop(
            columns=["asset_id"]
        ),
        "000002.SZ": _bars_for_dates("000002.SZ", [float(index) for index in range(11, 36)]).drop(
            columns=["asset_id"]
        ),
    }
    monkeypatch.setattr(
        technical_feature_store,
        "load_bars_for_technical_features",
        lambda trade_date, **kwargs: bars,
    )

    result = technical_feature_store.build_stock_technical_features_daily(
        "2026-01-25",
        adjust_type="qfq",
    )

    assert list(result.columns) == technical_feature_store.TECHNICAL_FEATURE_TABLE_COLUMNS
    assert list(result["asset_id"]) == ["000001.SZ", "000002.SZ"]
    assert result["trade_date"].tolist() == ["2026-01-25", "2026-01-25"]
    assert result["ts_code"].tolist() == ["000001.SZ", "000002.SZ"]
    assert result["adjust_type"].tolist() == ["qfq", "qfq"]
    assert result["source_data_version"].tolist() == ["market_daily_bar:qfq", "market_daily_bar:qfq"]
    assert result["ret_1d"].notna().all()
    assert result["ret_20d"].notna().all()
    assert result["close_position_in_day"].notna().all()


def test_build_stock_technical_features_daily_uses_requested_source_data_version(monkeypatch):
    bars = {
        "000001.SZ": _bars_for_dates("000001.SZ", [float(index) for index in range(1, 26)]).drop(
            columns=["asset_id"]
        ),
    }
    monkeypatch.setattr(
        technical_feature_store,
        "load_bars_for_technical_features",
        lambda trade_date, **kwargs: bars,
    )

    result = technical_feature_store.build_stock_technical_features_daily(
        "2026-01-25",
        adjust_type="qfq",
        source_data_version="market_daily_bar:qfq@v2",
    )

    assert result["source_data_version"].tolist() == ["market_daily_bar:qfq@v2"]


def test_upsert_stock_technical_features_daily_writes_replay_safe_rows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(technical_feature_store, "connect", lambda service: _context(conn))

    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-25",
                "asset_id": "000001.SZ",
                "ts_code": "000001.SZ",
                "adjust_type": "qfq",
                "source": "technical_features",
                "source_data_version": "market_daily_bar:qfq",
                "calc_version": "v1",
                "ma5": 23.0,
                "ma10": 20.5,
                "ma20": 15.5,
                "ma60": None,
                "ma120": None,
                "ema12": 19.0,
                "ema26": 17.0,
                "macd_dif": 2.0,
                "macd_dea": 1.5,
                "macd_hist": 1.0,
                "rsi6": 80.0,
                "rsi12": 75.0,
                "rsi24": 70.0,
                "boll_upper_20": 26.0,
                "boll_mid_20": 15.5,
                "boll_lower_20": 5.0,
                "atr14": 2.2,
                "cci14": 101.0,
                "kdj_k": 88.0,
                "kdj_d": 82.0,
                "kdj_j": 100.0,
                "adx14": 30.0,
                "obv": 12345.0,
                "ret_1d": 0.05,
                "ret_20d": 0.25,
                "close_position_in_day": 0.75,
            }
        ]
    )

    count = technical_feature_store.upsert_stock_technical_features_daily(features)

    assert count == 1
    assert "CREATE TEMP TABLE tmp_stock_technical_features_daily" in conn.cursor_obj.executes[0][0]
    assert "COPY tmp_stock_technical_features_daily" in conn.cursor_obj.copy_calls[0].sql
    assert conn.cursor_obj.copy_calls[0].rows == [
        tuple(features.loc[0, column] for column in technical_feature_store.TECHNICAL_FEATURE_TABLE_COLUMNS)
    ]
    upsert_sql, _ = conn.cursor_obj.executes[1]
    assert "INSERT INTO factor.stock_technical_features_daily" in upsert_sql
    assert (
        "ON CONFLICT (trade_date, asset_id, adjust_type, source_data_version, calc_version)"
        in upsert_sql
    )
    assert "ret_1d = EXCLUDED.ret_1d" in upsert_sql
    assert "ret_20d = EXCLUDED.ret_20d" in upsert_sql
    assert "close_position_in_day = EXCLUDED.close_position_in_day" in upsert_sql
    assert "computed_at = now()" in upsert_sql
    assert "updated_at = now()" in upsert_sql


def test_upsert_stock_technical_features_daily_keeps_distinct_source_versions(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(technical_feature_store, "connect", lambda service: _context(conn))

    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-25",
                "asset_id": "000001.SZ",
                "ts_code": "000001.SZ",
                "adjust_type": "qfq",
                "source": "technical_features",
                "source_data_version": "market_daily_bar:qfq@v1",
                "calc_version": "v1",
                "ma5": 23.0,
                "ma10": 20.5,
                "ma20": 15.5,
                "ma60": None,
                "ma120": None,
                "ema12": 19.0,
                "ema26": 17.0,
                "macd_dif": 2.0,
                "macd_dea": 1.5,
                "macd_hist": 1.0,
                "rsi6": 80.0,
                "rsi12": 75.0,
                "rsi24": 70.0,
                "boll_upper_20": 26.0,
                "boll_mid_20": 15.5,
                "boll_lower_20": 5.0,
                "atr14": 2.2,
                "cci14": 101.0,
                "kdj_k": 88.0,
                "kdj_d": 82.0,
                "kdj_j": 100.0,
                "adx14": 30.0,
                "obv": 12345.0,
                "ret_1d": 0.05,
                "ret_20d": 0.25,
                "close_position_in_day": 0.75,
            },
            {
                "trade_date": "2026-01-25",
                "asset_id": "000001.SZ",
                "ts_code": "000001.SZ",
                "adjust_type": "qfq",
                "source": "technical_features",
                "source_data_version": "market_daily_bar:qfq@v2",
                "calc_version": "v1",
                "ma5": 24.0,
                "ma10": 21.5,
                "ma20": 16.5,
                "ma60": None,
                "ma120": None,
                "ema12": 20.0,
                "ema26": 18.0,
                "macd_dif": 3.0,
                "macd_dea": 2.5,
                "macd_hist": 1.5,
                "rsi6": 81.0,
                "rsi12": 76.0,
                "rsi24": 71.0,
                "boll_upper_20": 27.0,
                "boll_mid_20": 16.5,
                "boll_lower_20": 6.0,
                "atr14": 2.3,
                "cci14": 102.0,
                "kdj_k": 89.0,
                "kdj_d": 83.0,
                "kdj_j": 101.0,
                "adx14": 31.0,
                "obv": 12346.0,
                "ret_1d": 0.06,
                "ret_20d": 0.26,
                "close_position_in_day": 0.76,
            },
        ]
    )

    count = technical_feature_store.upsert_stock_technical_features_daily(features)

    assert count == 2
    assert len(conn.cursor_obj.copy_calls[0].rows) == 2
    assert {row[5] for row in conn.cursor_obj.copy_calls[0].rows} == {
        "market_daily_bar:qfq@v1",
        "market_daily_bar:qfq@v2",
    }
    upsert_sql, _ = conn.cursor_obj.executes[1]
    assert (
        "ON CONFLICT (trade_date, asset_id, adjust_type, source_data_version, calc_version)"
        in upsert_sql
    )


def test_build_and_store_stock_technical_features_daily_delegates(monkeypatch):
    features = pd.DataFrame([{"trade_date": "2026-01-25"}])
    build_calls = []
    store_calls = []
    monkeypatch.setattr(
        technical_feature_store,
        "build_stock_technical_features_daily",
        lambda trade_date, **kwargs: build_calls.append((trade_date, kwargs)) or features,
    )
    monkeypatch.setattr(
        technical_feature_store,
        "upsert_stock_technical_features_daily",
        lambda frame: store_calls.append(frame) or len(frame),
    )

    count = technical_feature_store.build_and_store_stock_technical_features_daily(
        "2026-01-25",
        lookback_bars=260,
        adjust_type="qfq",
        source_data_version="market_daily_bar:qfq@v2",
    )

    assert count == 1
    assert build_calls == [
        (
            "2026-01-25",
            {
                "lookback_bars": 260,
                "adjust_type": "qfq",
                "source_data_version": "market_daily_bar:qfq@v2",
            },
        )
    ]
    assert store_calls == [features]
