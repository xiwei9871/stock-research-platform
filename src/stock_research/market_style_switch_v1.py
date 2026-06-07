from __future__ import annotations

from pathlib import Path
from typing import Any

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
ANCHOR_RECORDS = (
    {"name": "长江电力", "asset_id": "CN:SH:600900", "code": "600900"},
    {"name": "中国神华", "asset_id": "CN:SH:601088", "code": "601088"},
    {"name": "农业银行", "asset_id": "CN:SH:601288", "code": "601288"},
    {"name": "伊利股份", "asset_id": "CN:SH:600887", "code": "600887"},
    {"name": "贵州茅台", "asset_id": "CN:SH:600519", "code": "600519"},
)
ANCHOR_NAMES = tuple(anchor["name"] for anchor in ANCHOR_RECORDS)

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

GROWTH_CANDIDATE_COLUMNS = [*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank", "growth_rank_score"]
DEFENSIVE_CANDIDATE_COLUMNS = [*FUNNEL_BASE_COLUMNS, "style_sleeve", "style_rank", "defensive_rank_score"]
ROTATION_CANDIDATE_COLUMNS = [
    *FUNNEL_BASE_COLUMNS,
    "style_sleeve",
    "style_rank",
    "growth_rank_score",
    "defensive_rank_score",
]
ANCHOR_DIAGNOSTIC_COLUMNS = ["trade_date", "anchor_name", "anchor_asset_id", "anchor_present"]
SUMMARY_COLUMNS = ["strategy_family", "total_return", "annualized_return", "max_drawdown", "days"]
YEAR_BREAKDOWN_COLUMNS = ["year", "strategy_family", "total_return", "max_drawdown", "days"]
EMOTION_BREAKDOWN_COLUMNS = [
    "emotion_state",
    "risk_state",
    "style_state",
    "strategy_family",
    "total_return",
    "max_drawdown",
    "days",
]
EQUITY_COLUMNS = [
    "trade_date",
    "strategy_family",
    "daily_return",
    "equity",
    "invested_weight",
    "holdings",
]
POSITION_BUDGET_WEIGHTS = {"full": 1.0, "reduced": 0.6, "light": 0.2}


def run_style_switch_backtest_from_frames(
    *,
    emotion: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    top_n: int = 5,
    defensive_industry_keywords: tuple[str, ...] = DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS,
) -> dict[str, Any]:
    style_state = build_style_state_daily(emotion)
    style_state = _filter_date_range(style_state, start_date, end_date)
    growth = _filter_date_range(build_growth_momentum_candidates(funnel, top_n=max(top_n, 10)), start_date, end_date)
    defensive = _filter_date_range(
        build_defensive_yield_proxy_candidates(
            funnel,
            top_n=max(top_n, 10),
            defensive_industry_keywords=defensive_industry_keywords,
        ),
        start_date,
        end_date,
    )
    rotation = _filter_date_range(
        build_rotation_balanced_candidates(growth, defensive, top_n=max(top_n, 10)),
        start_date,
        end_date,
    )
    anchor_diagnostics = build_anchor_diagnostics(defensive)
    selections = {
        "fixed_mid_trend": _build_strategy_selection(
            style_state, growth, defensive, rotation, "fixed_mid_trend", top_n
        ),
        "emotion_budget_only": _build_strategy_selection(
            style_state, growth, defensive, rotation, "emotion_budget_only", top_n
        ),
        "emotion_style_switch": _build_strategy_selection(
            style_state, growth, defensive, rotation, "emotion_style_switch", top_n
        ),
    }
    equity = pd.concat(
        [
            _simulate_equal_weight_daily(prices, selected, strategy_family=name)
            for name, selected in selections.items()
        ],
        ignore_index=True,
    )
    summary = _summarize_equity(equity)
    year_breakdown = _breakdown_equity(equity, style_state, group_cols=["year"])
    emotion_breakdown = _breakdown_equity(
        equity,
        style_state,
        group_cols=["emotion_state", "risk_state", "style_state"],
    )
    paths = {}
    if output_dir is not None:
        paths = write_market_style_switch_outputs(
            style_state=style_state,
            growth_candidates=growth,
            defensive_candidates=defensive,
            rotation_candidates=rotation,
            anchor_diagnostics=anchor_diagnostics,
            summary=summary,
            year_breakdown=year_breakdown,
            emotion_breakdown=emotion_breakdown,
            output_dir=output_dir,
        )
    return {
        "style_state": style_state,
        "growth_candidates": growth,
        "defensive_candidates": defensive,
        "rotation_candidates": rotation,
        "anchor_diagnostics": anchor_diagnostics,
        "summary": summary,
        "year_breakdown": year_breakdown,
        "emotion_breakdown": emotion_breakdown,
        "equity": equity,
        "paths": paths,
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


def build_growth_momentum_candidates(funnel: pd.DataFrame, *, top_n: int = 5) -> pd.DataFrame:
    frame = _normalize_funnel(funnel)
    if frame.empty:
        return pd.DataFrame(columns=GROWTH_CANDIDATE_COLUMNS)

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
        return pd.DataFrame(columns=DEFENSIVE_CANDIDATE_COLUMNS)

    industry_match = frame["industry_name"].fillna("").astype(str).apply(
        lambda value: any(keyword in value for keyword in defensive_industry_keywords)
    )
    frame = frame[industry_match].copy()
    if frame.empty:
        return pd.DataFrame(columns=DEFENSIVE_CANDIDATE_COLUMNS)

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
        return pd.DataFrame(columns=ROTATION_CANDIDATE_COLUMNS)

    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined["trade_date"] = pd.to_datetime(combined["trade_date"], errors="coerce", format="mixed").dt.strftime(
        "%Y-%m-%d"
    )
    combined = combined.dropna(subset=["trade_date"])
    if combined.empty:
        return pd.DataFrame(columns=ROTATION_CANDIDATE_COLUMNS)

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
        return pd.DataFrame(columns=ROTATION_CANDIDATE_COLUMNS)

    rotation = pd.DataFrame(ordered)
    rotation = rotation.groupby("trade_date", group_keys=False, sort=True).head(max(top_n, 0)).reset_index(drop=True)
    rotation["style_rank"] = rotation.groupby("trade_date").cumcount() + 1
    return _ordered_candidate_columns(rotation)


def build_anchor_diagnostics(defensive_candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    frame = defensive_candidates.copy()
    if frame.empty or "trade_date" not in frame.columns:
        return pd.DataFrame(columns=ANCHOR_DIAGNOSTIC_COLUMNS)

    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed").dt.strftime(
        "%Y-%m-%d"
    )
    frame = frame.dropna(subset=["trade_date"])
    if frame.empty:
        return pd.DataFrame(columns=ANCHOR_DIAGNOSTIC_COLUMNS)

    frame["stock_name"] = _normalized_text_column(frame, "stock_name")
    frame["asset_id"] = _normalized_text_column(frame, "asset_id")
    for trade_date, day in frame.groupby("trade_date", sort=True):
        names = set(day["stock_name"])
        assets = set(day["asset_id"])
        for anchor in ANCHOR_RECORDS:
            anchor_assets = {anchor["asset_id"], anchor["code"]}
            rows.append(
                {
                    "trade_date": trade_date,
                    "anchor_name": anchor["name"],
                    "anchor_asset_id": anchor["asset_id"],
                    "anchor_present": anchor["name"] in names or bool(anchor_assets & assets),
                }
            )
    return pd.DataFrame(rows, columns=ANCHOR_DIAGNOSTIC_COLUMNS)


def write_market_style_switch_outputs(
    *,
    style_state: pd.DataFrame,
    growth_candidates: pd.DataFrame,
    defensive_candidates: pd.DataFrame,
    rotation_candidates: pd.DataFrame,
    anchor_diagnostics: pd.DataFrame,
    summary: pd.DataFrame,
    year_breakdown: pd.DataFrame,
    emotion_breakdown: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "style_state_path": output_path / "market_style_state_daily.csv",
        "growth_candidates_path": output_path / "growth_momentum_candidates.csv",
        "defensive_candidates_path": output_path / "defensive_yield_proxy_candidates.csv",
        "rotation_candidates_path": output_path / "rotation_balanced_candidates.csv",
        "anchor_diagnostics_path": output_path / "anchor_diagnostics.csv",
        "summary_path": output_path / "style_switch_backtest_summary.csv",
        "year_breakdown_path": output_path / "style_switch_year_breakdown.csv",
        "emotion_breakdown_path": output_path / "style_switch_emotion_breakdown.csv",
        "report_path": output_path / "market_style_switch_v1_report.md",
    }
    style_state = _normalize_empty_schema(style_state, STYLE_STATE_COLUMNS)
    growth_candidates = _normalize_empty_schema(growth_candidates, GROWTH_CANDIDATE_COLUMNS)
    defensive_candidates = _normalize_empty_schema(defensive_candidates, DEFENSIVE_CANDIDATE_COLUMNS)
    rotation_candidates = _normalize_empty_schema(rotation_candidates, ROTATION_CANDIDATE_COLUMNS)
    anchor_diagnostics = _normalize_empty_schema(anchor_diagnostics, ANCHOR_DIAGNOSTIC_COLUMNS)
    summary = _normalize_empty_schema(summary, SUMMARY_COLUMNS)
    year_breakdown = _normalize_empty_schema(year_breakdown, YEAR_BREAKDOWN_COLUMNS)
    emotion_breakdown = _normalize_empty_schema(emotion_breakdown, EMOTION_BREAKDOWN_COLUMNS)

    style_state.to_csv(paths["style_state_path"], index=False)
    growth_candidates.to_csv(paths["growth_candidates_path"], index=False)
    defensive_candidates.to_csv(paths["defensive_candidates_path"], index=False)
    rotation_candidates.to_csv(paths["rotation_candidates_path"], index=False)
    anchor_diagnostics.to_csv(paths["anchor_diagnostics_path"], index=False)
    summary.to_csv(paths["summary_path"], index=False)
    year_breakdown.to_csv(paths["year_breakdown_path"], index=False)
    emotion_breakdown.to_csv(paths["emotion_breakdown_path"], index=False)
    paths["report_path"].write_text(
        _render_market_style_switch_report(summary, year_breakdown, emotion_breakdown),
        encoding="utf-8",
    )
    return paths


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


def _filter_date_range(frame: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return frame.copy()

    filtered = frame.copy()
    filtered["trade_date"] = pd.to_datetime(
        filtered["trade_date"], errors="coerce", format="mixed"
    ).dt.strftime("%Y-%m-%d")
    filtered = filtered.dropna(subset=["trade_date"])
    start = pd.to_datetime(start_date).strftime("%Y-%m-%d")
    end = pd.to_datetime(end_date).strftime("%Y-%m-%d")
    return filtered[(filtered["trade_date"] >= start) & (filtered["trade_date"] <= end)].reset_index(drop=True)


def _build_strategy_selection(
    style_state: pd.DataFrame,
    growth: pd.DataFrame,
    defensive: pd.DataFrame,
    rotation: pd.DataFrame,
    strategy_family: str,
    top_n: int,
) -> pd.DataFrame:
    rows = []
    sleeve_frames = {
        "growth_momentum": growth,
        "defensive_yield_proxy": defensive,
        "rotation_balanced": rotation,
    }
    for state in style_state.to_dict("records"):
        trade_date = state["trade_date"]
        if strategy_family == "fixed_mid_trend":
            sleeve_name = "growth_momentum"
            invested_weight = 1.0
        elif strategy_family == "emotion_budget_only":
            sleeve_name = "growth_momentum"
            invested_weight = POSITION_BUDGET_WEIGHTS.get(state.get("position_budget_hint"), 0.6)
        else:
            sleeve_name = str(state.get("style_state") or "rotation_balanced")
            # V1 keeps style selection separate from exposure sizing. A wait/cash style means no
            # holdings for the day; other style-switch sleeves stay fully invested.
            invested_weight = 0.0 if sleeve_name == "cash_or_wait" else 1.0

        sleeve = sleeve_frames.get(sleeve_name)
        if sleeve is None or sleeve.empty or invested_weight <= 0.0 or top_n <= 0:
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": pd.NA,
                    "strategy_family": strategy_family,
                    "selection_style": sleeve_name,
                    "invested_weight": invested_weight,
                }
            )
            continue

        day = sleeve[sleeve["trade_date"] == trade_date].sort_values(["style_rank", "asset_id"]).head(top_n)
        if day.empty:
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": pd.NA,
                    "strategy_family": strategy_family,
                    "selection_style": sleeve_name,
                    "invested_weight": invested_weight,
                }
            )
            continue

        for asset_id in day["asset_id"]:
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "strategy_family": strategy_family,
                    "selection_style": sleeve_name,
                    "invested_weight": invested_weight,
                }
            )
    return pd.DataFrame(
        rows,
        columns=["trade_date", "asset_id", "strategy_family", "selection_style", "invested_weight"],
    )


def _simulate_equal_weight_daily(
    prices: pd.DataFrame,
    selected: pd.DataFrame,
    *,
    strategy_family: str,
) -> pd.DataFrame:
    price_returns = _normalize_prices_with_forward_returns(prices)
    if selected.empty:
        return pd.DataFrame(columns=EQUITY_COLUMNS)

    equity = 1.0
    rows = []
    for trade_date, day in selected.groupby("trade_date", sort=True):
        invested_weight = float(pd.to_numeric(day["invested_weight"], errors="coerce").fillna(0.0).max())
        asset_ids = day["asset_id"].dropna().astype(str).tolist()
        asset_returns = price_returns[
            (price_returns["trade_date"] == trade_date) & (price_returns["asset_id"].isin(asset_ids))
        ]["next_return"].dropna()
        if asset_returns.empty or invested_weight <= 0.0:
            daily_return = 0.0
        else:
            daily_return = float(asset_returns.mean()) * invested_weight
        equity *= 1.0 + daily_return
        rows.append(
            {
                "trade_date": trade_date,
                "strategy_family": strategy_family,
                "daily_return": daily_return,
                "equity": equity,
                "invested_weight": invested_weight,
                "holdings": len(asset_returns),
            }
        )
    return pd.DataFrame(rows, columns=EQUITY_COLUMNS)


def _normalize_prices_with_forward_returns(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.copy()
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "close", "next_close", "next_return"])
    for column in ["trade_date", "asset_id", "close"]:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed").dt.strftime(
        "%Y-%m-%d"
    )
    frame["asset_id"] = frame["asset_id"].fillna("").astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "close"])
    frame = frame[frame["asset_id"] != ""].sort_values(["asset_id", "trade_date"]).reset_index(drop=True)
    frame["next_close"] = frame.groupby("asset_id")["close"].shift(-1)
    frame["next_return"] = frame["next_close"] / frame["close"] - 1.0
    return frame


def _summarize_equity(equity: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy_family, frame in equity.groupby("strategy_family", sort=True):
        equity_curve = frame["equity"].astype(float)
        days = int(len(frame))
        total_return = float(equity_curve.iloc[-1] - 1.0) if days else 0.0
        annualized_return = (1.0 + total_return) ** (252.0 / days) - 1.0 if days and total_return > -1.0 else 0.0
        rows.append(
            {
                "strategy_family": strategy_family,
                "total_return": total_return,
                "annualized_return": float(annualized_return),
                "max_drawdown": _max_drawdown(equity_curve),
                "days": days,
            }
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _breakdown_equity(equity: pd.DataFrame, style_state: pd.DataFrame, *, group_cols: list[str]) -> pd.DataFrame:
    if equity.empty:
        if group_cols == ["year"]:
            return pd.DataFrame(columns=YEAR_BREAKDOWN_COLUMNS)
        return pd.DataFrame(columns=EMOTION_BREAKDOWN_COLUMNS)

    frame = equity.merge(
        style_state[["trade_date", "emotion_state", "risk_state", "style_state"]],
        on="trade_date",
        how="left",
    )
    frame["year"] = frame["trade_date"].str.slice(0, 4)
    rows = []
    for keys, group in frame.groupby([*group_cols, "strategy_family"], dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        key_values = dict(zip([*group_cols, "strategy_family"], keys, strict=True))
        total_return = float((1.0 + group["daily_return"].astype(float)).prod() - 1.0)
        row = {
            **key_values,
            "total_return": total_return,
            "max_drawdown": _max_drawdown((1.0 + group["daily_return"].astype(float)).cumprod()),
            "days": int(len(group)),
        }
        rows.append(row)

    if group_cols == ["year"]:
        return pd.DataFrame(rows, columns=YEAR_BREAKDOWN_COLUMNS)
    return pd.DataFrame(rows, columns=EMOTION_BREAKDOWN_COLUMNS)


def _max_drawdown(equity_curve: pd.Series) -> float:
    if equity_curve.empty:
        return 0.0
    curve = equity_curve.astype(float)
    drawdown = curve / curve.cummax() - 1.0
    return float(drawdown.min())


def _render_market_style_switch_report(
    summary: pd.DataFrame,
    year_breakdown: pd.DataFrame,
    emotion_breakdown: pd.DataFrame,
) -> str:
    sections = [
        "# Market Style Switch V1 Report",
        "",
        "## Backtest Summary",
        _frame_to_markdown(summary),
        "",
        "## Year Breakdown",
        _frame_to_markdown(year_breakdown),
        "",
        "## Emotion Breakdown",
        _frame_to_markdown(emotion_breakdown),
        "",
    ]
    return "\n".join(sections)


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    try:
        return frame.to_markdown(index=False)
    except ImportError:
        return f"```csv\n{frame.to_csv(index=False).rstrip()}\n```"


def _normalize_empty_schema(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return frame


def _normalized_text_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("", index=frame.index, dtype=object)
    return frame[column].fillna("").astype(str).str.strip()


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
        if score_column == "growth_rank_score":
            return pd.DataFrame(columns=GROWTH_CANDIDATE_COLUMNS)
        if score_column == "defensive_rank_score":
            return pd.DataFrame(columns=DEFENSIVE_CANDIDATE_COLUMNS)
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
