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


DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS = ("电力", "热力", "煤炭", "银行", "金融", "食品", "饮料", "酒", "家电", "公用")

FUNNEL_BASE_COLUMNS = [
    "trade_date",
    "asset_id",
    "stock_name",
    "industry_name",
]

FUNNEL_NUMERIC_COLUMNS = [
    "mid_trend_funnel_score",
    "shadow_top10_rank",
    "volatility_20_score",
    "max_drawdown_20_score",
    "ma60_slope_score",
    "score_total",
]


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


def build_growth_momentum_candidates(funnel: pd.DataFrame, *, top_n: int = 5) -> pd.DataFrame:
    frame = _normalize_funnel(funnel)
    if frame.empty:
        return pd.DataFrame(columns=[*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank", "growth_rank_score"])

    frame["growth_rank_score"] = (
        frame["mid_trend_funnel_score"].fillna(frame["score_total"]).fillna(0)
        - frame["shadow_top10_rank"].fillna(999) * 0.5
    )
    return _rank_by_date(frame, "growth_rank_score", top_n, "growth_momentum")


def build_defensive_yield_proxy_candidates(
    funnel: pd.DataFrame,
    *,
    top_n: int = 5,
    defensive_industry_keywords: tuple[str, ...] = DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS,
) -> pd.DataFrame:
    frame = _normalize_funnel(funnel)
    if frame.empty:
        return pd.DataFrame(columns=[*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank", "defensive_rank_score"])

    industry_match = frame["industry_name"].fillna("").astype(str).apply(
        lambda value: any(keyword in value for keyword in defensive_industry_keywords)
    )
    frame = frame[industry_match].copy()
    if frame.empty:
        return pd.DataFrame(columns=[*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank", "defensive_rank_score"])

    frame["defensive_rank_score"] = (
        0.35 * frame["volatility_20_score"].fillna(50)
        + 0.35 * frame["max_drawdown_20_score"].fillna(50)
        + 0.20 * frame["ma60_slope_score"].fillna(50)
        + 0.10 * frame["score_total"].fillna(frame["mid_trend_funnel_score"]).fillna(50)
    )
    return _rank_by_date(frame, "defensive_rank_score", top_n, "defensive_yield_proxy")


def build_rotation_balanced_candidates(
    growth: pd.DataFrame,
    defensive: pd.DataFrame,
    *,
    top_n: int = 5,
) -> pd.DataFrame:
    frames = []
    if not growth.empty:
        frames.append(growth.copy())
    if not defensive.empty:
        frames.append(defensive.copy())
    if not frames:
        return pd.DataFrame(columns=[*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank"])

    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined["trade_date"] = pd.to_datetime(combined["trade_date"], errors="coerce", format="mixed").dt.strftime(
        "%Y-%m-%d"
    )
    combined = combined.dropna(subset=["trade_date"])
    if combined.empty:
        return pd.DataFrame(columns=[*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank"])

    combined["style_rank"] = pd.to_numeric(combined.get("style_rank"), errors="coerce").fillna(999).astype(int)
    ordered = []
    for trade_date, date_frame in combined.groupby("trade_date", sort=True):
        growth_rows = date_frame[date_frame["style_sleeve"] == "growth_momentum"].sort_values(
            ["style_rank", "asset_id"], ascending=[True, True]
        )
        defensive_rows = date_frame[date_frame["style_sleeve"] == "defensive_yield_proxy"].sort_values(
            ["style_rank", "asset_id"], ascending=[True, True]
        )
        seen_assets = set()
        for rank in range(max(len(growth_rows), len(defensive_rows))):
            if rank < len(growth_rows):
                growth_row = growth_rows.iloc[rank].to_dict()
                asset_id = growth_row.get("asset_id")
                if asset_id not in seen_assets:
                    ordered.append(growth_row)
                    seen_assets.add(asset_id)
            if rank < len(defensive_rows):
                defensive_row = defensive_rows.iloc[rank].to_dict()
                asset_id = defensive_row.get("asset_id")
                if asset_id not in seen_assets:
                    ordered.append(defensive_row)
                    seen_assets.add(asset_id)

    if not ordered:
        return pd.DataFrame(columns=[*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank"])

    rotation = pd.DataFrame(ordered)
    rotation = rotation.groupby("trade_date", group_keys=False, sort=True).head(max(top_n, 0)).reset_index(drop=True)
    rotation["style_rank"] = rotation.groupby("trade_date").cumcount() + 1
    return _ordered_candidate_columns(rotation)


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


def _normalize_funnel(funnel: pd.DataFrame) -> pd.DataFrame:
    frame = funnel.copy()
    if frame.empty:
        return pd.DataFrame(columns=[*FUNNEL_BASE_COLUMNS, *FUNNEL_NUMERIC_COLUMNS])

    for column in [*FUNNEL_BASE_COLUMNS, *FUNNEL_NUMERIC_COLUMNS]:
        if column not in frame.columns:
            frame[column] = pd.NA

    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed").dt.strftime(
        "%Y-%m-%d"
    )
    frame = frame.dropna(subset=["trade_date"])
    for column in FUNNEL_NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _rank_by_date(frame: pd.DataFrame, score_column: str, top_n: int, style_sleeve: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank", score_column])

    ranked = frame.copy()
    ranked["style_sleeve"] = style_sleeve
    ranked = ranked.sort_values(["trade_date", score_column, "asset_id"], ascending=[True, False, True])
    ranked = ranked.groupby("trade_date", group_keys=False, sort=True).head(max(top_n, 0)).reset_index(drop=True)
    ranked["style_rank"] = ranked.groupby("trade_date").cumcount() + 1
    return _ordered_candidate_columns(ranked, score_column)


def _ordered_candidate_columns(frame: pd.DataFrame, score_column: str | None = None) -> pd.DataFrame:
    preferred = [*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank"]
    if score_column is not None:
        preferred.append(score_column)
    else:
        preferred.extend(column for column in ["growth_rank_score", "defensive_rank_score"] if column in frame.columns)
    remaining = [column for column in frame.columns if column not in preferred]
    return frame[[*preferred, *remaining]].reset_index(drop=True)
