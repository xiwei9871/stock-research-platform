import pandas as pd

from stock_research import factor_store


class FakeCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def executemany(self, sql, rows):
        self.calls.append((sql, list(rows)))


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj


def test_upsert_factor_daily_writes_factor_rows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(factor_store, "connect", lambda service: _context(conn))

    frame = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "factor_name": "ret_20",
                "factor_group": "momentum",
                "factor_value": 0.12,
                "calc_version": "v1",
                "source": "custom",
                "source_data_version": "market_daily_bar:hfq",
            }
        ]
    )

    count = factor_store.upsert_factor_daily(frame)

    sql, rows = conn.cursor_obj.calls[0]
    assert count == 1
    assert "INSERT INTO factor.factor_daily" in sql
    assert "ON CONFLICT" in sql
    assert rows == [
        {
            "trade_date": "2026-01-01",
            "asset_id": "A",
            "factor_name": "ret_20",
            "factor_group": "momentum",
            "factor_value": 0.12,
            "calc_version": "v1",
            "source": "custom",
            "source_data_version": "market_daily_bar:hfq",
        }
    ]


def test_upsert_stock_score_daily_writes_score_rows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(factor_store, "connect", lambda service: _context(conn))

    frame = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "rank": 1,
                "score_total": 88.5,
                "score_version": "manual_v1",
                "score_components": {"trend": 90.0},
            }
        ]
    )

    count = factor_store.upsert_stock_score_daily(frame)

    sql, rows = conn.cursor_obj.calls[0]
    assert count == 1
    assert "INSERT INTO factor.stock_score_daily" in sql
    assert rows[0]["score_components"] == '{"trend": 90.0}'


def test_load_top_scores_queries_factor_scores(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "rank": 1,
                "score_total": 88.5,
                "score_version": "manual_v1",
                "score_components": {"trend": 90.0},
            }
        ]

    monkeypatch.setattr(factor_store, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_store, "fetch_all", fake_fetch_all)

    rows = factor_store.load_top_scores("2026-01-01", score_version="manual_v1", top_n=10)

    assert rows[0]["asset_id"] == "A"
    assert "FROM factor.stock_score_daily" in calls[0][0]
    assert calls[0][1] == ["2026-01-01", "manual_v1", 10]


def test_load_factor_daily_queries_trade_date_and_calc_version(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [
            {
                "trade_date": "2026-05-08",
                "asset_id": "A",
                "factor_name": "ret_20",
                "factor_group": "momentum",
                "factor_value": 0.1,
                "calc_version": "v1",
                "source": "custom",
                "source_data_version": "market_daily_bar:hfq",
            }
        ]

    monkeypatch.setattr(factor_store, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_store, "fetch_all", fake_fetch_all)

    frame = factor_store.load_factor_daily("2026-05-08", calc_version="v1")

    assert frame.iloc[0]["factor_name"] == "ret_20"
    assert "FROM factor.factor_daily" in calls[0][0]
    assert calls[0][1] == ["2026-05-08", "v1"]


def test_load_factor_daily_can_filter_to_approved_factors(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [
            {
                "trade_date": "2026-05-08",
                "asset_id": "A",
                "factor_name": "ret_20",
                "factor_group": "momentum",
                "factor_value": 0.1,
                "calc_version": "v1",
                "source": "custom",
                "source_data_version": "market_daily_bar:hfq",
            }
        ]

    monkeypatch.setattr(factor_store, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_store, "fetch_all", fake_fetch_all)

    frame = factor_store.load_factor_daily(
        "2026-05-08",
        calc_version="v1",
        approved_only=True,
        score_version="manual_v1",
    )

    assert frame.iloc[0]["factor_name"] == "ret_20"
    assert "JOIN factor.factor_approval" in calls[0][0]
    assert "approval.status = 'approved'" in calls[0][0]
    assert calls[0][1] == ["2026-05-08", "v1", "manual_v1"]


def test_score_and_store_factor_daily_upserts_scores(monkeypatch):
    stored = []

    def fake_upsert(scores, **kwargs):
        stored.append((scores, kwargs))
        return len(scores)

    monkeypatch.setattr(factor_store, "upsert_stock_score_daily", fake_upsert)
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "momentum", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_name": "momentum", "factor_value": 2.0},
        ]
    )

    count = factor_store.score_and_store_factor_daily(
        factors,
        factor_directions={"momentum": "higher"},
        weights={"momentum_score": 1.0},
        score_version="manual_v1",
    )

    scores, kwargs = stored[0]
    assert count == 2
    assert scores.iloc[0]["asset_id"] == "B"
    assert scores.iloc[0]["rank"] == 1
    assert kwargs["source_data_version"] == "factor_daily:manual_v1"


def test_score_stored_factor_daily_loads_config_and_scores(monkeypatch):
    calls = []
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-05-08", "asset_id": "A", "factor_name": "ret_20", "factor_value": 1.0},
            {"trade_date": "2026-05-08", "asset_id": "B", "factor_name": "ret_20", "factor_value": 2.0},
        ]
    )

    monkeypatch.setattr(factor_store, "load_factor_daily", lambda **kwargs: factors)
    monkeypatch.setattr(
        factor_store,
        "score_and_store_factor_daily",
        lambda factor_daily, **kwargs: calls.append((factor_daily, kwargs)) or len(factor_daily),
    )

    count = factor_store.score_stored_factor_daily("2026-05-08", score_version="manual_v1")

    assert count == 2
    assert calls[0][0] is factors
    assert calls[0][1]["score_version"] == "manual_v1"
    assert calls[0][1]["calc_version"] == "v1"


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
