import json

from stock_research import selection
from stock_research.selection import (
    generate_selection,
    load_trade_status,
    reasons_for_features,
    risk_tags_for_features,
    score_asset,
    store_selection,
)


def test_score_asset_rewards_momentum_and_liquidity():
    features = {
        "ret_20d": 0.12,
        "ret_60d": 0.25,
        "amount_20d_avg": 200000000.0,
        "volatility_20d": 0.02,
        "max_drawdown_20d": -0.05,
    }

    assert score_asset(features) > 0


def test_risk_tags_for_features():
    features = {
        "volatility_20d": 0.08,
        "max_drawdown_20d": -0.22,
        "amount_20d_avg": 1000000.0,
    }

    tags = risk_tags_for_features(features)

    assert "high_volatility" in tags
    assert "large_drawdown" in tags
    assert "low_liquidity" in tags


def test_reasons_for_features():
    features = {
        "ret_20d": 0.12,
        "ret_60d": 0.25,
        "amount_20d_avg": 200000000.0,
    }

    reasons = reasons_for_features(features)

    assert len(reasons) >= 3


def test_generate_selection_sorts_by_score_and_assigns_ranks(monkeypatch):
    def fake_load_feature_matrix(trade_date):
        assert trade_date == "2026-05-07"
        return {
            "CN:SH:600001": {
                "ret_20d": 0.03,
                "ret_60d": 0.05,
                "amount_20d_avg": 120000000.0,
                "volatility_20d": 0.03,
                "max_drawdown_20d": -0.03,
            },
            "CN:SH:600002": {
                "ret_20d": 0.12,
                "ret_60d": 0.20,
                "amount_20d_avg": 180000000.0,
                "volatility_20d": 0.02,
                "max_drawdown_20d": -0.02,
            },
            "CN:SH:600003": {
                "ret_20d": 0.50,
                "ret_60d": 0.50,
                "amount_20d_avg": 1000000.0,
                "volatility_20d": 0.01,
                "max_drawdown_20d": -0.01,
            },
        }

    monkeypatch.setattr(selection, "load_feature_matrix", fake_load_feature_matrix)
    monkeypatch.setattr(
        selection,
        "load_trade_status",
        lambda trade_date: {
            "CN:SH:600001": {"is_st": False, "trade_status": "1"},
            "CN:SH:600002": {"is_st": False, "trade_status": "1"},
            "CN:SH:600003": {"is_st": False, "trade_status": "1"},
        },
        raising=False,
    )

    results = generate_selection("2026-05-07", top_n=2)

    assert [row["asset_id"] for row in results] == ["CN:SH:600002", "CN:SH:600001"]
    assert [row["rank"] for row in results] == [1, 2]
    assert results[0]["score"] > results[1]["score"]
    assert results[0]["score_version"] == "baseline_rules_v1"
    assert results[0]["feature_snapshot_version"] == "p0_daily:v1"
    assert results[0]["run_id"].startswith("2026-05-07:baseline_rules_v1:")


def test_generate_selection_excludes_st_and_non_trading_assets(monkeypatch):
    shared_features = {
        "ret_20d": 0.20,
        "ret_60d": 0.30,
        "amount_20d_avg": 200000000.0,
        "volatility_20d": 0.02,
        "max_drawdown_20d": -0.02,
    }
    monkeypatch.setattr(
        selection,
        "load_feature_matrix",
        lambda trade_date: {
            "CN:SH:600001": dict(shared_features),
            "CN:SH:600002": dict(shared_features),
            "CN:SH:600003": dict(shared_features),
        },
    )
    monkeypatch.setattr(
        selection,
        "load_trade_status",
        lambda trade_date: {
            "CN:SH:600001": {"is_st": True, "trade_status": "1"},
            "CN:SH:600002": {"is_st": False, "trade_status": "0"},
            "CN:SH:600003": {"is_st": False, "trade_status": "1"},
        },
        raising=False,
    )

    results = generate_selection("2026-05-07", top_n=10)

    assert [row["asset_id"] for row in results] == ["CN:SH:600003"]
    assert results[0]["rank"] == 1


def test_generate_selection_orders_equal_scores_by_asset_id(monkeypatch):
    shared_features = {
        "ret_20d": 0.10,
        "ret_60d": 0.20,
        "amount_20d_avg": 150000000.0,
        "volatility_20d": 0.02,
        "max_drawdown_20d": -0.02,
    }
    monkeypatch.setattr(
        selection,
        "load_feature_matrix",
        lambda trade_date: {
            "CN:SH:600002": dict(shared_features),
            "CN:SH:600001": dict(shared_features),
        },
    )
    monkeypatch.setattr(
        selection,
        "load_trade_status",
        lambda trade_date: {
            "CN:SH:600001": {"is_st": False, "trade_status": "1"},
            "CN:SH:600002": {"is_st": False, "trade_status": "1"},
        },
        raising=False,
    )

    results = generate_selection("2026-05-07", top_n=10)

    assert [row["asset_id"] for row in results] == ["CN:SH:600001", "CN:SH:600002"]
    assert [row["rank"] for row in results] == [1, 2]


def test_load_trade_status_reads_hfq_status_for_trade_date(monkeypatch):
    captured = {}

    class FakeConnection:
        pass

    class FakeConnect:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {"asset_id": "CN:SH:600001", "is_st": True, "trade_status": "1"},
            {"asset_id": "CN:SH:600002", "is_st": False, "trade_status": 0},
        ]

    monkeypatch.setattr(selection, "connect", fake_connect)
    monkeypatch.setattr(selection, "fetch_all", fake_fetch_all)

    statuses = load_trade_status("2026-05-07")

    assert "FROM market_daily_bar" in captured["sql"]
    assert "adjust_type = 'hfq'" in captured["sql"]
    assert captured["params"] == ["2026-05-07"]
    assert statuses == {
        "CN:SH:600001": {"is_st": True, "trade_status": "1"},
        "CN:SH:600002": {"is_st": False, "trade_status": "0"},
    }


def test_store_selection_serializes_json_fields(monkeypatch):
    captured = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, sql, rows):
            captured["sql"] = sql
            captured["rows"] = rows

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakeConnect:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(selection, "connect", lambda service: FakeConnect())

    count = store_selection(
        [
            {
                "run_id": "2026-05-07:baseline_rules_v1:120000",
                "trade_date": "2026-05-07",
                "asset_id": "CN:SH:600000",
                "rank": 1,
                "score": 12.3456,
                "score_version": "baseline_rules_v1",
                "reasons": ["20日动量为正：12.00%"],
                "risk_tags": ["high_volatility"],
                "feature_snapshot_version": "p0_daily:v1",
            }
        ]
    )

    assert count == 1
    assert "%(reasons)s::jsonb" in captured["sql"]
    row = captured["rows"][0]
    assert json.loads(row["reasons"]) == ["20日动量为正：12.00%"]
    assert "动量" in row["reasons"]
    assert json.loads(row["risk_tags"]) == ["high_volatility"]


def test_store_selection_empty_results_returns_zero():
    assert store_selection([]) == 0
