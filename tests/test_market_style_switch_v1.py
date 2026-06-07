import pandas as pd

from stock_research.market_style_switch_v1 import (
    build_defensive_yield_proxy_candidates,
    build_growth_momentum_candidates,
    build_rotation_balanced_candidates,
    build_style_state_daily,
)


def test_build_style_state_daily_maps_emotion_and_risk_to_style() -> None:
    emotion = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "emotion_state": "euphoria",
                "risk_state": "low",
                "emotion_score": 85.0,
            },
            {
                "trade_date": "2026-01-03",
                "emotion_state": "hot",
                "risk_state": "medium",
                "emotion_score": 70.0,
            },
            {
                "trade_date": "2026-01-04",
                "emotion_state": "neutral",
                "risk_state": "high",
                "emotion_score": 50.0,
            },
            {
                "trade_date": "2026-01-05",
                "emotion_state": "panic",
                "risk_state": "high",
                "emotion_score": 25.0,
            },
        ]
    )

    result = build_style_state_daily(emotion)

    assert result[["trade_date", "style_state"]].to_dict("records") == [
        {"trade_date": "2026-01-02", "style_state": "growth_momentum"},
        {"trade_date": "2026-01-03", "style_state": "rotation_balanced"},
        {"trade_date": "2026-01-04", "style_state": "defensive_yield_proxy"},
        {"trade_date": "2026-01-05", "style_state": "cash_or_wait"},
    ]
    assert set(result["position_budget_hint"]) <= {"full", "reduced", "light"}


def test_build_style_state_daily_normalizes_mixed_trade_dates_and_drops_invalid() -> None:
    emotion = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "emotion_state": "neutral",
                "risk_state": "medium",
                "emotion_score": 50.0,
            },
            {
                "trade_date": "2026/01/03",
                "emotion_state": "hot",
                "risk_state": "low",
                "emotion_score": 75.0,
            },
            {
                "trade_date": "not-a-date",
                "emotion_state": "panic",
                "risk_state": "high",
                "emotion_score": 20.0,
            },
        ]
    )

    result = build_style_state_daily(emotion)

    assert result["trade_date"].tolist() == ["2026-01-02", "2026-01-03"]


def _funnel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "G1",
                "stock_name": "科技A",
                "mid_trend_funnel_score": 95,
                "shadow_top10_rank": 1,
                "industry_name": "软件和信息技术服务业",
                "volatility_20_score": 30,
                "max_drawdown_20_score": 60,
                "ma60_slope_score": 90,
                "score_total": 95,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D1",
                "stock_name": "长江电力",
                "mid_trend_funnel_score": 80,
                "shadow_top10_rank": 5,
                "industry_name": "电力、热力生产和供应业",
                "volatility_20_score": 95,
                "max_drawdown_20_score": 95,
                "ma60_slope_score": 70,
                "score_total": 80,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D2",
                "stock_name": "农业银行",
                "mid_trend_funnel_score": 75,
                "shadow_top10_rank": 7,
                "industry_name": "货币金融服务",
                "volatility_20_score": 90,
                "max_drawdown_20_score": 90,
                "ma60_slope_score": 65,
                "score_total": 75,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "X1",
                "stock_name": "地产弱势",
                "mid_trend_funnel_score": 70,
                "shadow_top10_rank": 9,
                "industry_name": "房地产业",
                "volatility_20_score": 20,
                "max_drawdown_20_score": 30,
                "ma60_slope_score": 20,
                "score_total": 70,
            },
        ]
    )


def test_candidate_sleeves_rank_growth_and_defensive_separately() -> None:
    growth = build_growth_momentum_candidates(_funnel(), top_n=2)
    defensive = build_defensive_yield_proxy_candidates(_funnel(), top_n=2)
    rotation = build_rotation_balanced_candidates(growth, defensive, top_n=4)

    assert growth.iloc[0]["asset_id"] == "G1"
    assert defensive["asset_id"].tolist() == ["D1", "D2"]
    assert rotation["style_sleeve"].tolist() == [
        "growth_momentum",
        "defensive_yield_proxy",
        "growth_momentum",
        "defensive_yield_proxy",
    ]
