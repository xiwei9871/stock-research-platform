import pandas as pd
import pytest
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import factors


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_list_factor_library_marks_manual_v1_weights(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params=None):
        return [
            {
                "factor_name": "ret_20",
                "latest_available_date": "2026-06-08",
                "coverage_count": 5207,
                "approval_status": "rejected",
            }
        ]

    monkeypatch.setattr(factors, "connect", fake_connect)
    monkeypatch.setattr(factors, "fetch_all", fake_fetch_all)

    rows = factors.list_factor_library()
    ret_20 = next(row for row in rows if row["factor_name"] == "ret_20")

    assert ret_20["factor_group"] == "momentum"
    assert ret_20["direction"] == "higher"
    assert ret_20["manual_v1_weight"] == 0.15
    assert ret_20["used_in_manual_v1"] is True
    assert ret_20["latest_available_date"] == "2026-06-08"
    assert ret_20["coverage_count"] == 5207
    assert ret_20["status"] == "rejected"


def test_build_factor_score_preview_scores_selected_factors(monkeypatch):
    frame = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-08",
                "asset_id": "A",
                "factor_name": "ret_20",
                "factor_value": 2.0,
            },
            {
                "trade_date": "2026-06-08",
                "asset_id": "B",
                "factor_name": "ret_20",
                "factor_value": 1.0,
            },
            {
                "trade_date": "2026-06-08",
                "asset_id": "A",
                "factor_name": "volatility_20",
                "factor_value": 5.0,
            },
            {
                "trade_date": "2026-06-08",
                "asset_id": "B",
                "factor_name": "volatility_20",
                "factor_value": 1.0,
            },
        ]
    )

    monkeypatch.setattr(factors, "_load_factor_rows", lambda *args, **kwargs: frame)

    result = factors.build_factor_score_preview(
        trade_date="2026-06-08",
        selected_factors=[
            {"factor_name": "ret_20", "direction": "higher", "weight": 1.0},
            {"factor_name": "volatility_20", "direction": "lower", "weight": 1.0},
        ],
        top_n=2,
    )

    assert result["items"][0]["asset_id"] == "A"
    assert result["items"][0]["rank"] == 1
    assert result["items"][0]["score_total"] == 50.0
    assert result["items"][0]["score_components"] == {
        "ret_20_score": 100.0,
        "volatility_20_score": 0.0,
    }
    assert result["selected_factors"][1]["factor_name"] == "volatility_20"


def test_parse_factor_selection_rejects_bad_direction():
    with pytest.raises(ValueError, match="higher or lower"):
        factors.parse_factor_selection("ret_20:sideways:1.0")


def test_factor_routes(monkeypatch):
    monkeypatch.setattr(dashboard_app, "list_factor_library", lambda: [{"factor_name": "ret_20"}])
    monkeypatch.setattr(
        dashboard_app,
        "build_factor_score_preview",
        lambda **kwargs: {"items": [], "selected_factors": kwargs["selected_factors"]},
    )
    client = TestClient(dashboard_app.create_app())

    library = client.get("/api/factors/library")
    preview = client.get(
        "/api/factors/score-preview",
        params={"trade_date": "2026-06-08", "factors": "ret_20:higher:1.0", "top_n": 5},
    )

    assert library.status_code == 200
    assert library.json()["items"][0]["factor_name"] == "ret_20"
    assert preview.status_code == 200
    assert preview.json()["selected_factors"][0]["factor_name"] == "ret_20"
