from decimal import Decimal

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
        lambda **kwargs: [{"asset_id": "A", "rank": 1, "score_total": Decimal("88.0")}],
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
    assert calls[0].iloc[0]["reason_json"]["score_total"] == 88.0
    assert isinstance(calls[0].iloc[0]["reason_json"]["score_total"], float)


def test_build_watchlist_snapshot_uses_full_sector_universe_for_sector_risk(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_watchlist_items",
        lambda *args, **kwargs: pd.DataFrame(
            [{"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10}]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"asset_id": "A", "rank": 1, "score_total": Decimal("88.0")}],
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(
            [
                {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.04},
                {"asset_id": "A", "feature_name": "ret_20d", "feature_value": 0.12},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_industry_memberships",
        lambda **kwargs: {"A": {"industry_code": "TECH", "industry_name": "Tech"}},
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_market_state",
        lambda **kwargs: {"market_state": "bullish", "entry_allowed": True},
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_sector_strength_bars",
        lambda **kwargs: pd.DataFrame(
            [
                {"trade_date": "2026-05-20", "industry_system": "csrc", "industry_code": f"S{i}", "industry_name": f"S{i}", "close": 100 + i, "amount": 1000 + i}
                for i in range(1, 11)
            ]
        ),
    )

    def fake_calc_sector_strength(bars, trade_date, top_n=20):
        captured["top_n"] = top_n
        return pd.DataFrame(
            [{"industry_code": "TECH", "strength_rank": 6, "strength_score": 50.0}]
            if top_n >= 6
            else []
        )

    monkeypatch.setattr("stock_research.watchlist.workflow.calc_sector_strength", fake_calc_sector_strength)
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.store_watchlist_daily_signals",
        lambda frame, **kwargs: frame,
    )

    frame = build_watchlist_snapshot(
        trade_date="2026-05-20",
        watchlist_id="core",
        score_version="manual_v1",
        top_n=3,
    )

    assert captured["top_n"] == 10
    assert "sector_weakness" in frame.iloc[0]["risk_tags"]
