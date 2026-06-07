from pathlib import Path

import pandas as pd

from stock_research.market_regime_confirmation_v1 import (
    REGIME_COLUMNS,
    build_market_regime_confirmation_from_frames,
    write_market_regime_confirmation_outputs,
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


def test_build_regime_features_normalizes_mixed_date_formats_and_drops_invalid_dates() -> None:
    emotion = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "emotion_score": 50},
            {"trade_date": "2026/01/03", "emotion_score": 55},
            {"trade_date": 20260104, "emotion_score": 60},
            {"trade_date": 20260105.0, "emotion_score": 62},
            {"trade_date": None, "emotion_score": 63},
            {"trade_date": "bad-date", "emotion_score": 65},
        ]
    )

    result = build_market_regime_confirmation_from_frames(emotion)

    assert result["trade_date"].tolist() == ["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
    assert "1970-01-01" not in result["trade_date"].tolist()


def test_policy_impulse_requires_market_response_and_accelerates_rerisk() -> None:
    emotion = _emotion_rows(
        [25, 26, 28, 32, 45, 58, 64],
        states=["panic", "cold", "cold", "neutral", "hot", "hot", "euphoria"],
        risks=["high", "high", "high", "medium", "medium", "low", "low"],
    )
    policy = pd.DataFrame(
        [
            {
                "event_date": "2026-01-05",
                "event_type": "financial_policy",
                "policy_strength": 0.9,
                "description": "liquidity support",
                "source": "manual",
            }
        ]
    )

    result = build_market_regime_confirmation_from_frames(emotion, policy)

    candidate_response = result[result["trade_date"].isin(["2026-01-06", "2026-01-07"])]
    assert candidate_response["confirmed_regime_state"].tolist() == ["bull_impulse", "bull_impulse"]
    assert candidate_response["target_exposure"].tolist() == [1.0, 1.0]
    assert bool(result.loc[result["trade_date"] == "2026-01-05", "policy_impulse_candidate"].iloc[0]) is True


def test_policy_impulse_expiry_uses_downgrade_hysteresis_on_one_weak_day() -> None:
    emotion = _emotion_rows(
        [25, 26, 28, 32, 45, 58, 64],
        states=["panic", "cold", "cold", "neutral", "hot", "hot", "euphoria"],
        risks=["high", "high", "high", "medium", "medium", "low", "low"],
    )
    policy = pd.DataFrame([{"event_date": "2026-01-05", "policy_strength": 0.9}])

    result = build_market_regime_confirmation_from_frames(emotion, policy)

    expired_day = result.loc[result["trade_date"] == "2026-01-08"].iloc[0]
    assert bool(expired_day["policy_impulse_candidate"]) is False
    assert expired_day["raw_regime_state"] in {"neutral", "weak_repair", "bear"}
    assert expired_day["confirmed_regime_state"] in {"bull_impulse", "bull_trend"}
    assert expired_day["transition_reason"] == "downgrade_wait_for_confirmation"


def test_policy_impulse_to_overheated_trend_transition_is_explicit() -> None:
    emotion = _emotion_rows(
        [60, 60, 60, 60, 90, 100, 100, 100, 100],
        states=["neutral", "neutral", "neutral", "neutral", "hot", "euphoria", "euphoria", "euphoria", "euphoria"],
        risks=["low", "low", "low", "low", "low", "low", "low", "low", "low"],
    )
    policy = pd.DataFrame([{"event_date": "2026-01-06", "policy_strength": 0.9}])

    result = build_market_regime_confirmation_from_frames(emotion, policy)

    first_overheated = result.loc[result["trade_date"] == "2026-01-09"].iloc[0]
    confirmed_transition = result.loc[result["trade_date"] == "2026-01-10"].iloc[0]
    assert first_overheated["raw_regime_state"] == "overheated"
    assert first_overheated["confirmed_regime_state"] == "bull_impulse"
    assert first_overheated["transition_reason"] == "impulse_to_trend_wait_for_confirmation"
    assert confirmed_transition["raw_regime_state"] == "overheated"
    assert confirmed_transition["confirmed_regime_state"] == "bull_trend"
    assert confirmed_transition["target_exposure"] == 1.0
    assert confirmed_transition["transition_reason"] == "impulse_to_trend_confirmed"


def test_policy_impulse_trend_continuation_counts_bull_and_overheated_as_one_group() -> None:
    emotion = _emotion_rows(
        [60, 60, 60, 60, 90, 100, 100, 100, 70, 100, 70, 100],
        states=[
            "neutral",
            "neutral",
            "neutral",
            "neutral",
            "hot",
            "euphoria",
            "euphoria",
            "euphoria",
            "hot",
            "euphoria",
            "hot",
            "euphoria",
        ],
        risks=["low"] * 12,
    )
    policy = pd.DataFrame([{"event_date": "2026-01-06", "policy_strength": 0.9}])

    result = build_market_regime_confirmation_from_frames(emotion, policy)

    alternating = result.loc[result["trade_date"].isin(["2026-01-09", "2026-01-10", "2026-01-11", "2026-01-12"])]
    assert alternating["raw_regime_state"].tolist() == ["overheated", "bull_trend", "overheated", "bull_trend"]
    confirmed_transition = result.loc[result["trade_date"] == "2026-01-10"].iloc[0]
    assert confirmed_transition["confirmed_regime_state"] == "bull_trend"
    assert confirmed_transition["transition_reason"] == "impulse_to_trend_confirmed"


def test_confirmed_regime_does_not_downgrade_on_one_bad_day() -> None:
    emotion = _emotion_rows(
        [70, 72, 74, 75, 73, 71, 30, 68, 67],
        states=["hot", "hot", "euphoria", "euphoria", "hot", "hot", "panic", "hot", "hot"],
        risks=["low", "low", "low", "low", "low", "low", "high", "low", "low"],
    )

    result = build_market_regime_confirmation_from_frames(emotion)

    bad_day = result.loc[result["trade_date"] == "2026-01-08"].iloc[0]
    assert bad_day["raw_regime_state"] in {"neutral", "weak_repair", "bear"}
    assert bad_day["confirmed_regime_state"] in {"bull_trend", "overheated"}
    assert bad_day["transition_reason"] == "downgrade_wait_for_confirmation"


def test_write_outputs_includes_segment_diagnostics_transitions_and_markdown_report(tmp_path: Path) -> None:
    regime = build_market_regime_confirmation_from_frames(
        pd.DataFrame(
            [
                {"trade_date": "2024-09-23", "emotion_score": 30, "emotion_state": "cold", "risk_state": "high"},
                {"trade_date": "2024-09-24", "emotion_score": 45, "emotion_state": "neutral", "risk_state": "medium"},
                {"trade_date": "2024-09-25", "emotion_score": 60, "emotion_state": "hot", "risk_state": "low"},
                {"trade_date": "2024-11-11", "emotion_score": 55, "emotion_state": "neutral", "risk_state": "medium"},
            ]
        ),
        pd.DataFrame([{"event_date": "2024-09-24", "policy_strength": 0.9}]),
    )

    paths = write_market_regime_confirmation_outputs(regime, output_dir=tmp_path)

    assert paths["regime_path"].name == "market_regime_confirmation_daily.csv"
    assert paths["segment_diagnostics_path"].name == "market_regime_segment_diagnostics.csv"
    assert paths["transition_path"].name == "market_regime_transitions.csv"
    assert paths["report_path"].name == "market_regime_confirmation_v1_report.md"
    assert pd.read_csv(paths["regime_path"]).columns.tolist() == REGIME_COLUMNS

    segment = pd.read_csv(paths["segment_diagnostics_path"])
    assert {
        "segment_name",
        "start_date",
        "end_date",
        "days",
        "avg_target_exposure",
        "dominant_regime",
        "regime_changes",
        "raw_confirmed_disagree_days",
    }.issubset(segment.columns)
    assert segment["segment_name"].tolist() == [
        "pre_924_2024",
        "policy_rally_2024",
        "post_rally_2024",
        "post_2025",
        "full_period",
    ]
    assert int(segment.loc[segment["segment_name"] == "policy_rally_2024", "days"].iloc[0]) == 2

    transitions = pd.read_csv(paths["transition_path"])
    assert transitions.columns.tolist() == [
        "trade_date",
        "raw_regime_state",
        "confirmed_regime_state",
        "target_exposure",
        "style_bias",
        "transition_reason",
    ]
    assert transitions["trade_date"].iloc[0] == "2024-09-23"

    report = paths["report_path"].read_text(encoding="utf-8")
    assert report.startswith("# Market Regime Confirmation V1 Report")
    assert "## Segment Diagnostics" in report
    assert "## Confirmed Regime Distribution" in report
    assert "## Transitions" in report
