from __future__ import annotations

import math

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

REGIME_RANK = {
    "bear": 0,
    "weak_repair": 1,
    "neutral": 2,
    "trend_decay": 3,
    "bull_trend": 4,
    "bull_impulse": 5,
    "overheated": 6,
}


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

    trade_date = frame["trade_date"].map(_normalize_trade_date_value)
    frame["trade_date"] = pd.to_datetime(trade_date, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
    frame["emotion_score"] = pd.to_numeric(frame["emotion_score"], errors="coerce").fillna(50.0).clip(0.0, 100.0)
    frame["emotion_state"] = frame["emotion_state"].fillna("neutral").astype(str)
    frame["risk_state"] = frame["risk_state"].fillna("medium").astype(str)
    frame = frame.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    return frame[["trade_date", "emotion_score", "emotion_state", "risk_state"]]


def _normalize_trade_date_value(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    if isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value).strip()


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
    if policy_events is None or policy_events.empty:
        return result

    events = policy_events.copy()
    if "event_date" not in events.columns:
        return result

    event_date = events["event_date"].map(_normalize_trade_date_value)
    events["event_date"] = pd.to_datetime(event_date, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
    strength = events.get("policy_strength", pd.Series(0.0, index=events.index))
    events["policy_strength"] = pd.to_numeric(strength, errors="coerce").fillna(0.0).clip(0.0, 1.0)
    events = events.dropna(subset=["event_date"])
    strength_by_date = events.groupby("event_date")["policy_strength"].max()

    for date, policy_strength in strength_by_date.items():
        end_date = _shift_trade_date(result, date, 2)
        if end_date < date:
            continue
        mask = result["trade_date"].between(date, end_date)
        result.loc[mask, "policy_impulse_candidate"] = (
            result.loc[mask, "policy_impulse_candidate"] | (float(policy_strength) >= 0.7)
        )
        result.loc[mask, "policy_strength"] = result.loc[mask, "policy_strength"].clip(lower=float(policy_strength))
    return result


def _shift_trade_date(frame: pd.DataFrame, start_date: str, offset: int) -> str:
    dates = frame["trade_date"].tolist()
    if start_date not in dates:
        later = [date for date in dates if date >= start_date]
        return later[min(offset, len(later) - 1)] if later else start_date
    index = dates.index(start_date)
    return dates[min(index + offset, len(dates) - 1)]


def _attach_raw_regime(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    base = result["emotion_score_10d"] + result["emotion_slope_5d"].clip(-20, 20) * 0.35
    base = base - result["risk_high_days_5d"] * 2.0 + result["policy_strength"] * 8.0
    result["market_regime_score"] = base.clip(0.0, 100.0)
    result["raw_regime_state"] = result.apply(_raw_regime_state_from_row, axis=1)
    return result


def _raw_regime_state_from_row(row: pd.Series) -> str:
    if (
        bool(row.get("policy_impulse_candidate"))
        and row.get("emotion_slope_5d", 0.0) >= 15
        and row.get("emotion_score", 0.0) >= 45
    ):
        return "bull_impulse"

    score = float(row.get("market_regime_score", 50.0))
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
    confirmed = []
    reasons = []
    current = str(result.iloc[0]["raw_regime_state"])
    pending_state = current
    pending_count = 0

    for _, row in result.iterrows():
        raw = str(row["raw_regime_state"])
        if raw == current:
            pending_state = raw
            pending_count = 0
            confirmed.append(current)
            reasons.append("unchanged")
            continue

        raw_rank = REGIME_RANK.get(raw, 2)
        current_rank = REGIME_RANK.get(current, 2)
        pending_key = _confirmation_pending_key(current, raw)
        if pending_key != pending_state:
            pending_state = pending_key
            pending_count = 1
        else:
            pending_count += 1

        if raw == "bull_impulse" and pending_count >= 1:
            current = "bull_impulse"
            pending_count = 0
            confirmed.append(current)
            reasons.append("policy_impulse_confirmed")
        elif current == "bull_impulse" and raw in {"bull_trend", "overheated"}:
            if pending_count >= 2:
                current = "bull_trend"
                pending_count = 0
                confirmed.append(current)
                reasons.append("impulse_to_trend_confirmed")
            else:
                confirmed.append(current)
                reasons.append("impulse_to_trend_wait_for_confirmation")
        elif raw_rank > current_rank and pending_count >= 2:
            current = raw
            pending_count = 0
            confirmed.append(current)
            reasons.append("upgrade_confirmed")
        elif raw_rank < current_rank and pending_count >= 4:
            current = "trend_decay" if current in {"bull_impulse", "bull_trend", "overheated"} and raw_rank >= 1 else raw
            pending_count = 0
            confirmed.append(current)
            reasons.append("downgrade_confirmed")
        else:
            confirmed.append(current)
            reasons.append("downgrade_wait_for_confirmation" if raw_rank < current_rank else "upgrade_wait_for_confirmation")

    result["confirmed_regime_state"] = confirmed
    result["days_since_regime_change"] = _days_since_change(result["confirmed_regime_state"])
    result["transition_reason"] = reasons
    return result


def _confirmation_pending_key(current: str, raw: str) -> str:
    if current == "bull_impulse" and raw in {"bull_trend", "overheated"}:
        return "impulse_trend_continuation"
    return raw


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
