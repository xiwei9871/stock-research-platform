import pandas as pd

from stock_research.market_style_switch_v1 import build_style_state_daily


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
