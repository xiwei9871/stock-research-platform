from decimal import Decimal

import pandas as pd

from stock_research.watchlist.signals import build_watchlist_signal_rows


def test_build_watchlist_signal_rows_marks_top_ranked_assets_as_must_watch():
    watchlist_items = pd.DataFrame(
        [
            {"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10},
            {"watchlist_id": "core", "asset_id": "B", "stock_code": "000002.SZ", "stock_name": "B", "priority": 20},
        ]
    )
    top_scores = [{"asset_id": "A", "rank": 1, "score_total": Decimal("88.0")}]
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
    assert row["reason_json"]["score_total"] == 88.0
    assert isinstance(row["reason_json"]["score_total"], float)


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


def test_build_watchlist_signal_rows_uses_bottom_half_sector_ranking_for_weakness():
    watchlist_items = pd.DataFrame(
        [{"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10}]
    )
    sector_strength = pd.DataFrame(
        [
            {"industry_code": "S1", "strength_rank": 1, "strength_score": 100.0},
            {"industry_code": "S2", "strength_rank": 2, "strength_score": 90.0},
            {"industry_code": "S3", "strength_rank": 3, "strength_score": 80.0},
            {"industry_code": "S4", "strength_rank": 4, "strength_score": 70.0},
            {"industry_code": "S5", "strength_rank": 5, "strength_score": 60.0},
            {"industry_code": "TECH", "strength_rank": 6, "strength_score": 50.0},
            {"industry_code": "S7", "strength_rank": 7, "strength_score": 40.0},
            {"industry_code": "S8", "strength_rank": 8, "strength_score": 30.0},
            {"industry_code": "S9", "strength_rank": 9, "strength_score": 20.0},
            {"industry_code": "S10", "strength_rank": 10, "strength_score": 10.0},
        ]
    )

    frame = build_watchlist_signal_rows(
        watchlist_items=watchlist_items,
        top_scores=[],
        feature_snapshot=pd.DataFrame(),
        market_state={"market_state": "neutral", "entry_allowed": True},
        sector_strength=sector_strength,
        industry_map={"A": {"industry_code": "TECH", "industry_name": "Tech"}},
        output_version="v1",
    )

    assert "sector_weakness" in frame.iloc[0]["risk_tags"]
