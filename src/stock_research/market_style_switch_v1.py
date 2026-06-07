from __future__ import annotations

import pandas as pd


STYLE_STATE_COLUMNS = [
    "trade_date",
    "emotion_state",
    "risk_state",
    "emotion_score",
    "style_state",
    "style_reason",
    "position_budget_hint",
]


STYLE_MAPPING = {
    ("euphoria", "low"): "growth_momentum",
    ("euphoria", "medium"): "growth_momentum",
    ("euphoria", "high"): "rotation_balanced",
    ("hot", "low"): "growth_momentum",
    ("hot", "medium"): "rotation_balanced",
    ("hot", "high"): "cash_or_wait",
    ("neutral", "low"): "rotation_balanced",
    ("neutral", "medium"): "rotation_balanced",
    ("neutral", "high"): "defensive_yield_proxy",
    ("cold", "medium"): "defensive_yield_proxy",
    ("cold", "high"): "defensive_yield_proxy",
    ("panic", "high"): "cash_or_wait",
}


def build_style_state_daily(emotion: pd.DataFrame) -> pd.DataFrame:
    frame = emotion.copy()
    if frame.empty:
        return pd.DataFrame(columns=STYLE_STATE_COLUMNS)

    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed").dt.strftime(
        "%Y-%m-%d"
    )
    frame = frame.dropna(subset=["trade_date"])
    if frame.empty:
        return pd.DataFrame(columns=STYLE_STATE_COLUMNS)

    frame["emotion_state"] = frame["emotion_state"].fillna("neutral").astype(str)
    frame["risk_state"] = frame["risk_state"].fillna("medium").astype(str)
    frame["emotion_score"] = pd.to_numeric(frame.get("emotion_score"), errors="coerce")
    frame["style_state"] = frame.apply(
        lambda row: STYLE_MAPPING.get((row["emotion_state"], row["risk_state"]), "rotation_balanced"),
        axis=1,
    )
    frame["style_reason"] = frame["emotion_state"] + "|" + frame["risk_state"]
    frame["position_budget_hint"] = frame.apply(_position_budget_hint, axis=1)
    return frame[STYLE_STATE_COLUMNS].sort_values("trade_date").reset_index(drop=True)


def _position_budget_hint(row: pd.Series) -> str:
    emotion_state = str(row.get("emotion_state") or "")
    risk_state = str(row.get("risk_state") or "")
    if risk_state == "high" or emotion_state == "panic":
        return "light"
    if emotion_state == "cold" or risk_state == "medium":
        return "reduced"
    if emotion_state in {"hot", "euphoria"} and risk_state == "low":
        return "full"
    return "reduced"
