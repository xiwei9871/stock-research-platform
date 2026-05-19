import pandas as pd

from stock_research.watchlist.workflow import build_watchlist_snapshot


def test_build_watchlist_snapshot_loads_context_and_persists_signal_rows(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_watchlist_items",
        lambda *args, **kwargs: pd.DataFrame(
            [
                {"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10},
                {"watchlist_id": "core", "asset_id": "B", "stock_code": "000002.SZ", "stock_name": "B", "priority": 20},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"asset_id": "A", "rank": 1, "score_total": 88.0}],
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(
            [
                {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.04},
                {"asset_id": "A", "feature_name": "ret_20d", "feature_value": 0.12},
                {"asset_id": "B", "feature_name": "ret_5d", "feature_value": -0.02},
                {"asset_id": "B", "feature_name": "ret_20d", "feature_value": -0.05},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_industry_memberships",
        lambda **kwargs: {
            "A": {"industry_code": "BANK", "industry_name": "Bank"},
            "B": {"industry_code": "TECH", "industry_name": "Tech"},
        },
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_market_state",
        lambda **kwargs: {"market_state": "bullish", "entry_allowed": True},
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_sector_strength",
        lambda **kwargs: pd.DataFrame(
            [
                {"industry_code": "BANK", "strength_rank": 1, "strength_score": 80.0},
                {"industry_code": "TECH", "strength_rank": 20, "strength_score": 20.0},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.store_watchlist_daily_signals",
        lambda frame, **kwargs: calls.append(frame) or len(frame),
    )

    frame = build_watchlist_snapshot(
        trade_date="2026-05-20",
        watchlist_id="core",
        score_version="manual_v1",
    )

    assert len(frame) == 2
    assert len(calls) == 1
