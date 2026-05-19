import pandas as pd

from stock_research.watchlist.signals import build_watchlist_signal_rows


def test_build_watchlist_signal_rows_marks_top_ranked_assets_as_must_watch():
    watchlist_items = pd.DataFrame(
        [
            {"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10},
            {"watchlist_id": "core", "asset_id": "B", "stock_code": "000002.SZ", "stock_name": "B", "priority": 20},
        ]
    )
    top_scores = [{"asset_id": "A", "rank": 1, "score_total": 88.0}]
    feature_snapshot = pd.DataFrame(
        [
            {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.04},
            {"asset_id": "A", "feature_name": "ret_20d", "feature_value": 0.12},
        ]
    )
    market_state = {"market_state": "bullish", "entry_allowed": True}
    sector_strength = pd.DataFrame(
        [{"industry_code": "BANK", "strength_rank": 1, "strength_score": 80.0}]
    )
    industry_map = {"A": {"industry_code": "BANK", "industry_name": "Bank"}}

    frame = build_watchlist_signal_rows(
        watchlist_items=watchlist_items,
        top_scores=top_scores,
        feature_snapshot=feature_snapshot,
        market_state=market_state,
        sector_strength=sector_strength,
        industry_map=industry_map,
        output_version="v1",
    )

    row = frame.iloc[0]
    assert row["asset_id"] == "A"
    assert row["must_watch"] is True
    assert row["primary_signal"] == "candidate"
    assert row["signal_tags"] == ["candidate", "must_watch"]


def test_build_watchlist_signal_rows_adds_overheat_and_breakdown_tags():
    watchlist_items = pd.DataFrame(
        [{"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10}]
    )
    top_scores = []
    feature_snapshot = pd.DataFrame(
        [
            {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.18},
            {"asset_id": "A", "feature_name": "ret_20d", "feature_value": -0.05},
            {"asset_id": "A", "feature_name": "ma20_deviation", "feature_value": -0.04},
        ]
    )

    frame = build_watchlist_signal_rows(
        watchlist_items=watchlist_items,
        top_scores=top_scores,
        feature_snapshot=feature_snapshot,
        market_state={"market_state": "neutral", "entry_allowed": True},
        sector_strength=pd.DataFrame(),
        industry_map={},
        output_version="v1",
    )

    assert frame.iloc[0]["primary_signal"] == "breakdown"
    assert "overheat" in frame.iloc[0]["risk_tags"]
