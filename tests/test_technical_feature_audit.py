import importlib

import stock_research.technical_feature_audit as technical_feature_audit
import stock_research.technical_feature_store as technical_feature_store


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def test_run_technical_feature_gap_check_detects_missing_and_stale_assets(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        if "FROM market_daily_bar" in sql:
            assert params == ["qfq", "2024-03-01", "2024-03-02"]
            return [
                {"trade_date": "2024-03-01", "asset_id": "A"},
                {"trade_date": "2024-03-01", "asset_id": "B"},
                {"trade_date": "2024-03-02", "asset_id": "C"},
            ]
        if "FROM factor.stock_technical_features_daily" in sql:
            assert params == [
                "qfq",
                "technical_features",
                "market_daily_bar:qfq",
                "v1",
                "2024-03-01",
                "2024-03-02",
            ]
            return [
                {"trade_date": "2024-03-01", "asset_id": "A"},
                {"trade_date": "2024-03-01", "asset_id": "Z"},
                {"trade_date": "2024-03-02", "asset_id": "C"},
            ]
        raise AssertionError(sql)

    monkeypatch.setattr(technical_feature_audit, "connect", lambda service: _context(object()))
    monkeypatch.setattr(technical_feature_audit, "fetch_all", fake_fetch_all)

    result = technical_feature_audit.run_technical_feature_gap_check(
        start_date="2024-03-01",
        end_date="2024-03-02",
    )

    assert result == {
        "start_date": "2024-03-01",
        "end_date": "2024-03-02",
        "adjust_type": "qfq",
        "calc_version": "v1",
        "source_data_version": "market_daily_bar:qfq",
        "dates": [
            {
                "trade_date": "2024-03-01",
                "market_assets": 2,
                "feature_rows": 2,
                "missing": 1,
                "stale": 1,
                "missing_assets": ["B"],
                "stale_assets": ["Z"],
                "has_gap": True,
            },
            {
                "trade_date": "2024-03-02",
                "market_assets": 1,
                "feature_rows": 1,
                "missing": 0,
                "stale": 0,
                "missing_assets": [],
                "stale_assets": [],
                "has_gap": False,
            },
        ],
        "summary": {
            "dates": 2,
            "dates_with_gaps": 1,
        },
    }
    assert len(calls) == 2


def test_run_technical_feature_gap_check_honors_explicit_source_data_version(monkeypatch):
    params_seen = []

    def fake_fetch_all(conn, sql, params=None):
        params_seen.append(params)
        return []

    monkeypatch.setattr(technical_feature_audit, "connect", lambda service: _context(object()))
    monkeypatch.setattr(technical_feature_audit, "fetch_all", fake_fetch_all)

    result = technical_feature_audit.run_technical_feature_gap_check(
        start_date="2024-03-01",
        end_date="2024-03-01",
        adjust_type="hfq",
        calc_version="v2",
        source_data_version="market_daily_bar:hfq@custom",
    )

    assert result["source_data_version"] == "market_daily_bar:hfq@custom"
    assert params_seen[1] == [
        "hfq",
        "technical_features",
        "market_daily_bar:hfq@custom",
        "v2",
        "2024-03-01",
        "2024-03-01",
    ]


def test_run_technical_feature_gap_check_uses_shared_default_calc_version(monkeypatch):
    monkeypatch.setattr(
        technical_feature_store,
        "TECHNICAL_FEATURE_CALC_VERSION",
        "shared_v2",
    )
    reloaded = importlib.reload(technical_feature_audit)
    params_seen = []

    def fake_fetch_all(conn, sql, params=None):
        params_seen.append(params)
        return []

    monkeypatch.setattr(reloaded, "connect", lambda service: _context(object()))
    monkeypatch.setattr(reloaded, "fetch_all", fake_fetch_all)

    result = reloaded.run_technical_feature_gap_check(
        start_date="2024-03-01",
        end_date="2024-03-01",
    )

    assert result["calc_version"] == "shared_v2"
    assert params_seen[1][3] == "shared_v2"
