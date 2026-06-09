from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import asset_profile


def test_build_asset_profile_combines_existing_read_models(monkeypatch):
    calls = []

    def record(name, result):
        def wrapper(*args, **kwargs):
            calls.append((name, args, kwargs))
            return result

        return wrapper

    monkeypatch.setattr(
        asset_profile,
        "load_asset_detail",
        record("detail", {"asset_id": "CN:SZ:000001", "name": "Ping An Bank"}),
    )
    monkeypatch.setattr(
        asset_profile,
        "load_daily_bars",
        record("bars", [{"time": "2026-06-03"}]),
    )
    monkeypatch.setattr(
        asset_profile,
        "load_asset_score_for_dashboard",
        record(
            "score",
            {"score_total": 88.5, "score_components": {"ret_20_score": 90}},
        ),
    )
    monkeypatch.setattr(
        asset_profile,
        "load_asset_watchlist_signals_for_dashboard",
        record("signals", [{"primary_signal": "watch"}]),
    )
    monkeypatch.setattr(
        asset_profile,
        "load_asset_decision_history",
        record("decisions", [{"decision_label": "candidate"}]),
    )
    monkeypatch.setattr(
        asset_profile,
        "load_asset_outcome_history",
        record("outcomes", [{"outcome_status": "complete"}]),
    )
    monkeypatch.setattr(
        asset_profile,
        "_load_factor_values",
        record("factors", [{"factor_name": "ret_20"}]),
    )
    monkeypatch.setattr(
        asset_profile,
        "_load_data_coverage",
        record(
            "coverage",
            {"daily_bars": {"min_date": "1991-04-03", "max_date": "2026-06-08"}},
        ),
    )

    profile = asset_profile.build_asset_profile(
        asset_id="000001.SZ",
        trade_date="2026-06-08",
        start_date="2026-06-01",
        end_date="2026-06-08",
    )

    assert profile["asset_id"] == "000001.SZ"
    assert profile["canonical_asset_id"] == "CN:SZ:000001"
    assert profile["asset"]["asset_id"] == "CN:SZ:000001"
    assert profile["bars"][0]["time"] == "2026-06-03"
    assert profile["score"]["score_total"] == 88.5
    assert profile["signals"][0]["primary_signal"] == "watch"
    assert profile["decisions"][0]["decision_label"] == "candidate"
    assert profile["outcomes"][0]["outcome_status"] == "complete"
    assert profile["factor_values"][0]["factor_name"] == "ret_20"
    assert profile["coverage"]["daily_bars"]["max_date"] == "2026-06-08"

    by_name = {name: (args, kwargs) for name, args, kwargs in calls}
    assert by_name["score"][0][:3] == (
        "CN:SZ:000001",
        "2026-06-08",
        "manual_v1",
    )
    assert by_name["signals"][0][:2] == ("CN:SZ:000001", "2026-06-08")
    assert by_name["decisions"][0][:4] == (
        "CN:SZ:000001",
        "2026-06-01",
        "2026-06-08",
        50,
    )
    assert by_name["outcomes"][0][:5] == (
        "CN:SZ:000001",
        "2026-06-01",
        "2026-06-08",
        None,
        50,
    )
    assert by_name["factors"][0][:2] == ("CN:SZ:000001", "2026-06-08")
    assert by_name["coverage"][0][:1] == ("CN:SZ:000001",)


def test_load_factor_values_queries_factor_daily(monkeypatch):
    rows = [
        {
            "factor_name": "ret_20",
            "factor_group": "momentum",
            "factor_value": 1.5,
            "calc_version": "v1",
            "source": "unit",
            "source_data_version": "20260608",
        }
    ]
    captured = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(asset_profile, "connect", lambda service: FakeConnection())

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return rows

    monkeypatch.setattr(asset_profile, "fetch_all", fake_fetch_all)

    result = asset_profile._load_factor_values(
        "CN:SZ:000001",
        "2026-06-08",
        service="unit",
    )

    assert result == rows
    assert "FROM factor.factor_daily" in captured["sql"]
    assert "ORDER BY factor_group, factor_name" in captured["sql"]
    assert captured["params"] == ["CN:SZ:000001", "2026-06-08"]


def test_load_data_coverage_queries_bar_and_factor_coverage(monkeypatch):
    captured = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(asset_profile, "connect", lambda service: FakeConnection())

    def fake_fetch_all(conn, sql, params):
        captured.append((sql, params))
        if "market_daily_bar" in sql:
            return [{"min_date": "1991-04-03", "max_date": "2026-06-08", "row_count": 2}]
        return [{"latest_factor_date": "2026-06-08", "factor_count": 3}]

    monkeypatch.setattr(asset_profile, "fetch_all", fake_fetch_all)

    result = asset_profile._load_data_coverage("CN:SZ:000001", service="unit")

    assert result == {
        "daily_bars": {"min_date": "1991-04-03", "max_date": "2026-06-08", "row_count": 2},
        "factors": {"latest_factor_date": "2026-06-08", "factor_count": 3},
    }
    assert "adjust_type = 'qfq'" in captured[0][0]
    assert captured[0][1] == ["CN:SZ:000001"]
    assert "FROM factor.factor_daily" in captured[1][0]
    assert captured[1][1] == ["CN:SZ:000001"]


def test_asset_profile_route(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_asset_profile",
        lambda **kwargs: {
            "asset_id": kwargs["asset_id"],
            "score_version": kwargs["score_version"],
            "adjust_type": kwargs["adjust_type"],
            "bars": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/profile",
        params={
            "trade_date": "2026-06-08",
            "start_date": "2026-06-01",
            "end_date": "2026-06-08",
            "score_version": "manual_v2",
            "adjust_type": "hfq",
        },
    )

    assert response.status_code == 200
    assert response.json()["asset_id"] == "000001.SZ"
    assert response.json()["score_version"] == "manual_v2"
    assert response.json()["adjust_type"] == "hfq"
