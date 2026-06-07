from __future__ import annotations

import pandas as pd


REGIME_COLUMNS = [
    "trade_date",
    "emotion_score",
    "emotion_state",
    "risk_state",
    "emotion_score_5d",
    "emotion_score_10d",
    "emotion_slope_5d",
    "risk_high_days_5d",
    "risk_high_days_10d",
    "hot_or_euphoria_days_5d",
    "panic_or_cold_days_5d",
    "score_rebound_from_20d_low",
    "score_drawdown_from_20d_high",
    "policy_impulse_candidate",
    "policy_strength",
    "market_regime_score",
    "raw_regime_state",
    "confirmed_regime_state",
    "days_since_regime_change",
    "target_exposure",
    "style_bias",
    "rebalance_allowed",
    "transition_reason",
]


def build_market_regime_confirmation_from_frames(
    emotion: pd.DataFrame,
    policy_events: pd.DataFrame | None = None,
    *,
    rebalance_weekday: int = 4,
) -> pd.DataFrame:
    frame = _normalize_emotion(emotion)
    if frame.empty:
        return pd.DataFrame(columns=REGIME_COLUMNS)
    frame = _attach_smoothed_features(frame)
    frame = _attach_policy_events(frame, policy_events)
    frame = _attach_raw_regime(frame)
    frame = _attach_confirmed_regime(frame)
    frame = _attach_trading_policy(frame, rebalance_weekday=rebalance_weekday)
    return frame[REGIME_COLUMNS].reset_index(drop=True)


def _normalize_emotion(emotion: pd.DataFrame) -> pd.DataFrame:
    frame = emotion.copy()
    for column, default in {
        "trade_date": pd.NA,
        "emotion_score": 50.0,
        "emotion_state": "neutral",
        "risk_state": "medium",
    }.items():
        if column not in frame.columns:
            frame[column] = default

    trade_date = frame["trade_date"].where(frame["trade_date"].isna(), frame["trade_date"].astype(str).str.strip())
    frame["trade_date"] = pd.to_datetime(trade_date, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
    frame["emotion_score"] = pd.to_numeric(frame["emotion_score"], errors="coerce").fillna(50.0).clip(0.0, 100.0)
    frame["emotion_state"] = frame["emotion_state"].fillna("neutral").astype(str)
    frame["risk_state"] = frame["risk_state"].fillna("medium").astype(str)
    frame = frame.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    return frame[["trade_date", "emotion_score", "emotion_state", "risk_state"]]


def _attach_smoothed_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    score = result["emotion_score"].astype(float)
    result["emotion_score_5d"] = score.rolling(5, min_periods=1).mean()
    result["emotion_score_10d"] = score.rolling(10, min_periods=1).mean()
    result["emotion_slope_5d"] = score - score.shift(4).fillna(score.iloc[0])
    result["risk_high_days_5d"] = result["risk_state"].eq("high").rolling(5, min_periods=1).sum().astype(int)
    result["risk_high_days_10d"] = result["risk_state"].eq("high").rolling(10, min_periods=1).sum().astype(int)
    result["hot_or_euphoria_days_5d"] = (
        result["emotion_state"].isin(["hot", "euphoria"]).rolling(5, min_periods=1).sum().astype(int)
    )
    result["panic_or_cold_days_5d"] = (
        result["emotion_state"].isin(["panic", "cold"]).rolling(5, min_periods=1).sum().astype(int)
    )
    low_20 = score.rolling(20, min_periods=1).min()
    high_20 = score.rolling(20, min_periods=1).max()
    result["score_rebound_from_20d_low"] = score - low_20
    result["score_drawdown_from_20d_high"] = score - high_20
    return result


def _attach_policy_events(frame: pd.DataFrame, policy_events: pd.DataFrame | None) -> pd.DataFrame:
    result = frame.copy()
    result["policy_impulse_candidate"] = False
    result["policy_strength"] = 0.0
    return result


def _attach_raw_regime(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["market_regime_score"] = result["emotion_score_10d"]
    result["raw_regime_state"] = result["market_regime_score"].map(_raw_regime_state)
    return result


def _raw_regime_state(score: float) -> str:
    if score < 35:
        return "bear"
    if score < 45:
        return "weak_repair"
    if score < 60:
        return "neutral"
    if score < 75:
        return "bull_trend"
    return "overheated"


def _attach_confirmed_regime(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["confirmed_regime_state"] = result["raw_regime_state"]
    result["days_since_regime_change"] = _days_since_change(result["confirmed_regime_state"])
    result["transition_reason"] = "raw_initial"
    return result


def _days_since_change(states: pd.Series) -> list[int]:
    days = []
    current = None
    count = 0
    for state in states.astype(str):
        if state != current:
            current = state
            count = 0
        days.append(count)
        count += 1
    return days


def _attach_trading_policy(frame: pd.DataFrame, *, rebalance_weekday: int) -> pd.DataFrame:
    result = frame.copy()
    result["target_exposure"] = result["confirmed_regime_state"].map(_target_exposure).astype(float)
    result["style_bias"] = result["confirmed_regime_state"].map(_style_bias)
    result["rebalance_allowed"] = pd.to_datetime(result["trade_date"]).dt.weekday.eq(rebalance_weekday)
    return result


def _target_exposure(state: str) -> float:
    return {
        "bear": 0.2,
        "weak_repair": 0.5,
        "neutral": 0.7,
        "bull_impulse": 1.0,
        "bull_trend": 1.0,
        "trend_decay": 0.7,
        "overheated": 0.8,
    }.get(state, 0.6)


def _style_bias(state: str) -> str:
    return {
        "bear": "cash_defensive",
        "weak_repair": "reduced_growth",
        "neutral": "balanced_mid_trend",
        "bull_impulse": "growth_fast_rerisk",
        "bull_trend": "growth_mid_trend",
        "trend_decay": "hold_leaders_reduce_new",
        "overheated": "growth_tight_risk",
    }.get(state, "balanced_mid_trend")
