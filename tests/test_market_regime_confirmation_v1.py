import pandas as pd

from stock_research.market_regime_confirmation_v1 import (
    REGIME_COLUMNS,
    build_market_regime_confirmation_from_frames,
)


def _emotion_rows(scores: list[float], states: list[str] | None = None, risks: list[str] | None = None) -> pd.DataFrame:
    states = states or ["neutral"] * len(scores)
    risks = risks or ["medium"] * len(scores)
    return pd.DataFrame(
        [
            {
                "trade_date": f"2026-01-{index + 2:02d}",
                "emotion_score": score,
                "emotion_state": states[index],
                "risk_state": risks[index],
            }
            for index, score in enumerate(scores)
        ]
    )


def test_build_regime_features_smooths_daily_emotion_and_preserves_schema() -> None:
    emotion = _emotion_rows(
        [20, 30, 40, 50, 60, 70],
        states=["panic", "cold", "neutral", "neutral", "hot", "euphoria"],
        risks=["high", "high", "medium", "medium", "low", "low"],
    )

    result = build_market_regime_confirmation_from_frames(emotion)

    assert result.columns.tolist() == REGIME_COLUMNS
    assert result["trade_date"].tolist() == [
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
    ]
    last = result.iloc[-1]
    assert round(last["emotion_score_5d"], 2) == 50.00
    assert round(last["emotion_score_10d"], 2) == 45.00
    assert round(last["emotion_slope_5d"], 2) == 40.00
    assert int(last["risk_high_days_5d"]) == 1
    assert int(last["hot_or_euphoria_days_5d"]) == 2
    assert int(last["panic_or_cold_days_5d"]) == 1
