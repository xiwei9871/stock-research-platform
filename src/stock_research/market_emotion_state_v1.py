from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


DAILY_OUTPUT_COLUMNS = [
    "trade_date",
    "emotion_score",
    "emotion_state",
    "risk_state",
    "breadth_score",
    "limit_score",
    "relay_score",
    "feedback_score",
    "liquidity_score",
    "traded_count",
    "up_count",
    "down_count",
    "strong_up_count",
    "strong_down_count",
    "limit_up_count",
    "limit_down_count",
    "broken_limit_up_count",
    "broken_limit_up_rate",
    "first_board_count",
    "second_board_count",
    "third_board_plus_count",
    "high_board_height",
    "yesterday_limit_up_avg_return",
    "yesterday_limit_up_red_rate",
    "yesterday_limit_up_limit_down_rate",
    "yesterday_relay_avg_return",
    "yesterday_relay_red_rate",
    "yesterday_relay_continue_rate",
    "yesterday_broken_avg_return",
    "yesterday_broken_red_rate",
    "yesterday_broken_limit_down_rate",
    "total_amount",
    "amount_ratio_5_20",
    "style_signal_hint",
    "position_budget_hint",
]


def build_market_emotion_state_from_frames(
    bars: pd.DataFrame,
    status: pd.DataFrame,
) -> pd.DataFrame:
    frame = _prepare_daily_frame(bars, status)
    if frame.empty:
        return pd.DataFrame(columns=DAILY_OUTPUT_COLUMNS)
    frame = _attach_limit_streaks(frame)
    frame = _attach_prior_day_flags(frame)
    daily = _aggregate_daily(frame)
    daily = _score_daily(daily)
    return daily[DAILY_OUTPUT_COLUMNS].sort_values("trade_date").reset_index(drop=True)


def load_market_emotion_source_frames(
    start_date: str,
    end_date: str,
    *,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars_sql = """
        SELECT trade_date, asset_id, close, high, pct_chg, amount
        FROM market_daily_bar
        WHERE trade_date BETWEEN %s AND %s
          AND adjust_type = %s
        ORDER BY trade_date, asset_id
    """
    status_sql = """
        SELECT trade_date, asset_id, is_trade, is_st, is_suspended,
               is_limit_up, is_limit_down, limit_up_price, limit_down_price
        FROM core.asset_status_daily
        WHERE trade_date BETWEEN %s AND %s
        ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        bars = pd.DataFrame(fetch_all(conn, bars_sql, [start_date, end_date, adjust_type]))
        status = pd.DataFrame(fetch_all(conn, status_sql, [start_date, end_date]))
    return bars, status


def run_market_emotion_state_v1_backfill(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    adjust_type: str = "hfq",
    mid_trend_equity_path: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    bars, status = load_market_emotion_source_frames(
        start_date,
        end_date,
        adjust_type=adjust_type,
        service=service,
    )
    daily = build_market_emotion_state_from_frames(bars, status)
    mid_trend_equity = pd.read_csv(mid_trend_equity_path) if mid_trend_equity_path else None
    paths = write_market_emotion_outputs(
        daily,
        output_dir=output_dir,
        mid_trend_equity=mid_trend_equity,
    )
    return {"daily": daily, "paths": paths}


def write_market_emotion_outputs(
    daily: pd.DataFrame,
    *,
    output_dir: str | Path,
    mid_trend_equity: pd.DataFrame | None = None,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    daily_path = output_path / "market_emotion_state_daily.csv"
    report_path = output_path / "market_emotion_state_report.md"
    distribution_path = output_path / "market_emotion_state_distribution.csv"
    year_path = output_path / "market_emotion_state_year_breakdown.csv"

    normalized = daily.copy()
    normalized.to_csv(daily_path, index=False)
    distribution = _distribution(normalized)
    distribution.to_csv(distribution_path, index=False)
    year = _year_breakdown(normalized)
    year.to_csv(year_path, index=False)
    report_path.write_text(_render_report(normalized, distribution, year), encoding="utf-8")

    paths = {
        "daily_path": daily_path,
        "report_path": report_path,
        "distribution_path": distribution_path,
        "year_path": year_path,
    }
    if mid_trend_equity is not None:
        paths["mid_trend_state_breakdown_path"] = _write_mid_trend_breakdown(
            normalized,
            mid_trend_equity,
            output_path,
        )
    return paths


def _prepare_daily_frame(bars: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()

    merged = bars.copy()
    merged["trade_date"] = pd.to_datetime(merged["trade_date"], errors="coerce").dt.date.astype(str)
    merged["asset_id"] = merged["asset_id"].astype(str)
    for column in ["close", "high", "pct_chg", "amount"]:
        merged[column] = pd.to_numeric(merged.get(column), errors="coerce")

    if status.empty:
        normalized_status = pd.DataFrame(columns=["trade_date", "asset_id"])
    else:
        normalized_status = status.copy()
        normalized_status["trade_date"] = pd.to_datetime(
            normalized_status["trade_date"],
            errors="coerce",
        ).dt.date.astype(str)
        normalized_status["asset_id"] = normalized_status["asset_id"].astype(str)
        normalized_status["limit_up_price"] = pd.to_numeric(
            normalized_status.get("limit_up_price"),
            errors="coerce",
        )
        normalized_status["limit_down_price"] = pd.to_numeric(
            normalized_status.get("limit_down_price"),
            errors="coerce",
        )

    for column in ["is_trade", "is_st", "is_suspended", "is_limit_up", "is_limit_down"]:
        if column not in normalized_status.columns:
            normalized_status[column] = False
        normalized_status[column] = normalized_status[column].fillna(False).astype(bool)
    for column in ["limit_up_price", "limit_down_price"]:
        if column not in normalized_status.columns:
            normalized_status[column] = pd.NA

    merged = merged.merge(
        normalized_status[
            [
                "trade_date",
                "asset_id",
                "is_trade",
                "is_st",
                "is_suspended",
                "is_limit_up",
                "is_limit_down",
                "limit_up_price",
                "limit_down_price",
            ]
        ],
        on=["trade_date", "asset_id"],
        how="left",
    )
    for column in ["is_trade", "is_st", "is_suspended", "is_limit_up", "is_limit_down"]:
        merged[column] = merged[column].fillna(False).astype(bool)
    tradable = merged["is_trade"] & ~merged["is_suspended"] & ~merged["is_st"]
    result = merged[tradable].dropna(subset=["trade_date", "asset_id"]).copy()
    result["stock_return"] = pd.to_numeric(result["pct_chg"], errors="coerce") / 100.0
    result["is_broken_limit_up"] = (
        result["limit_up_price"].notna()
        & result["high"].ge(result["limit_up_price"] * 0.999)
        & ~result["is_limit_up"]
    )
    return result.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def _attach_limit_streaks(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    streaks: list[int] = []
    for _asset_id, group in result.groupby("asset_id", sort=False):
        streak = 0
        for is_limit_up in group["is_limit_up"].astype(bool).tolist():
            streak = streak + 1 if is_limit_up else 0
            streaks.append(streak)
    result["limit_up_streak"] = streaks
    return result


def _attach_prior_day_flags(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values(["asset_id", "trade_date"]).copy()
    group = result.groupby("asset_id", sort=False)
    result["prev_is_limit_up"] = group["is_limit_up"].shift(1).fillna(False).astype(bool)
    result["prev_limit_up_streak"] = group["limit_up_streak"].shift(1).fillna(0).astype(int)
    result["prev_is_relay"] = result["prev_limit_up_streak"].ge(2)
    result["prev_is_broken_limit_up"] = (
        group["is_broken_limit_up"].shift(1).fillna(False).astype(bool)
    )
    return result


def _aggregate_daily(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for trade_date, day in frame.groupby("trade_date", sort=True):
        limit_up_count = int(day["is_limit_up"].sum())
        broken_count = int(day["is_broken_limit_up"].sum())
        broken_denominator = limit_up_count + broken_count
        yesterday_limit = day[day["prev_is_limit_up"]]
        yesterday_relay = day[day["prev_is_relay"]]
        yesterday_broken = day[day["prev_is_broken_limit_up"]]
        rows.append(
            {
                "trade_date": str(trade_date),
                "traded_count": int(len(day)),
                "up_count": int(day["pct_chg"].gt(0).sum()),
                "down_count": int(day["pct_chg"].lt(0).sum()),
                "strong_up_count": int(day["pct_chg"].ge(5).sum()),
                "strong_down_count": int(day["pct_chg"].le(-5).sum()),
                "limit_up_count": limit_up_count,
                "limit_down_count": int(day["is_limit_down"].sum()),
                "broken_limit_up_count": broken_count,
                "broken_limit_up_rate": (
                    broken_count / broken_denominator if broken_denominator else 0.0
                ),
                "first_board_count": int((day["is_limit_up"] & day["limit_up_streak"].eq(1)).sum()),
                "second_board_count": int((day["is_limit_up"] & day["limit_up_streak"].eq(2)).sum()),
                "third_board_plus_count": int(
                    (day["is_limit_up"] & day["limit_up_streak"].ge(3)).sum()
                ),
                "high_board_height": int(day["limit_up_streak"].max() or 0),
                "yesterday_limit_up_avg_return": _avg_return(yesterday_limit),
                "yesterday_limit_up_red_rate": _rate(yesterday_limit["stock_return"].gt(0)),
                "yesterday_limit_up_limit_down_rate": _rate(yesterday_limit["is_limit_down"]),
                "yesterday_relay_avg_return": _avg_return(yesterday_relay),
                "yesterday_relay_red_rate": _rate(yesterday_relay["stock_return"].gt(0)),
                "yesterday_relay_continue_rate": _rate(yesterday_relay["is_limit_up"]),
                "yesterday_broken_avg_return": _avg_return(yesterday_broken),
                "yesterday_broken_red_rate": _rate(yesterday_broken["stock_return"].gt(0)),
                "yesterday_broken_limit_down_rate": _rate(yesterday_broken["is_limit_down"]),
                "total_amount": float(day["amount"].sum(skipna=True)),
            }
        )
    result = pd.DataFrame(rows)
    result["amount_ratio_5_20"] = (
        result["total_amount"].rolling(5, min_periods=1).mean()
        / result["total_amount"].rolling(20, min_periods=1).mean()
    )
    return result


def _score_daily(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily.copy()
    result = daily.copy()
    traded = result["traded_count"].replace(0, pd.NA)
    result["up_ratio"] = result["up_count"] / traded
    result["down_ratio"] = result["down_count"] / traded
    result["limit_up_ratio"] = result["limit_up_count"] / traded
    result["limit_down_ratio"] = result["limit_down_count"] / traded
    result["strong_up_ratio"] = result["strong_up_count"] / traded
    result["strong_down_ratio"] = result["strong_down_count"] / traded
    result["relay_ratio"] = (
        result["second_board_count"] + result["third_board_plus_count"]
    ) / result["limit_up_count"].replace(0, pd.NA)

    result["breadth_score"] = _clip_0_100(
        50
        + 80 * (result["up_ratio"].fillna(0) - result["down_ratio"].fillna(0))
        + 60 * (result["strong_up_ratio"].fillna(0) - result["strong_down_ratio"].fillna(0))
    )
    result["limit_score"] = _clip_0_100(
        45
        + 1.2 * result["limit_up_count"]
        - 2.5 * result["limit_down_count"]
        - 45 * result["broken_limit_up_rate"].fillna(0)
    )
    result["relay_score"] = _clip_0_100(
        30 + 10 * result["high_board_height"] + 80 * result["relay_ratio"].fillna(0)
    )
    result["feedback_score"] = _clip_0_100(
        50
        + 300 * result["yesterday_limit_up_avg_return"].fillna(0)
        + 20 * (result["yesterday_limit_up_red_rate"].fillna(0.5) - 0.5)
        - 35 * result["yesterday_limit_up_limit_down_rate"].fillna(0)
        + 200 * result["yesterday_relay_avg_return"].fillna(0)
        + 25 * result["yesterday_relay_continue_rate"].fillna(0)
        + 150 * result["yesterday_broken_avg_return"].fillna(0)
    )
    result["liquidity_score"] = _clip_0_100(
        45 + 35 * (result["amount_ratio_5_20"].fillna(1.0) - 1.0)
    )
    result["emotion_score"] = _clip_0_100(
        0.25 * result["breadth_score"]
        + 0.25 * result["limit_score"]
        + 0.20 * result["relay_score"]
        + 0.20 * result["feedback_score"]
        + 0.10 * result["liquidity_score"]
    )
    result["emotion_state"] = result["emotion_score"].map(_emotion_state)
    result["risk_state"] = result.apply(_risk_state, axis=1)
    result["style_signal_hint"] = result.apply(_style_hint, axis=1)
    result["position_budget_hint"] = result.apply(_position_hint, axis=1)
    return result


def _clip_0_100(value: pd.Series | float) -> pd.Series | float:
    if isinstance(value, pd.Series):
        return value.clip(lower=0.0, upper=100.0)
    return max(0.0, min(100.0, float(value)))


def _emotion_state(score: float) -> str:
    if score >= 80:
        return "euphoria"
    if score >= 65:
        return "hot"
    if score >= 45:
        return "neutral"
    if score >= 30:
        return "cold"
    return "panic"


def _risk_state(row: pd.Series) -> str:
    if (
        float(row.get("limit_down_count") or 0) >= 50
        or float(row.get("limit_down_ratio") or 0) >= 0.015
        or float(row.get("broken_limit_up_rate") or 0) >= 0.55
        or float(row.get("yesterday_limit_up_avg_return") or 0) <= -0.03
        or float(row.get("up_ratio") or 0) <= 0.25
    ):
        return "high"
    if (
        float(row.get("broken_limit_up_rate") or 0) >= 0.35
        or float(row.get("yesterday_limit_up_avg_return") or 0) < 0
        or float(row.get("amount_ratio_5_20") or 1.0) < 0.85
        or float(row.get("up_ratio") or 0) <= 0.40
    ):
        return "medium"
    return "low"


def _style_hint(row: pd.Series) -> str:
    emotion_state = str(row.get("emotion_state") or "")
    risk_state = str(row.get("risk_state") or "")
    if risk_state == "high" or emotion_state in {"panic", "cold"}:
        return "defensive_preferred"
    if emotion_state in {"hot", "euphoria"} and risk_state == "low":
        return "growth_favorable"
    if risk_state == "medium":
        return "unstable"
    return "rotation"


def _position_hint(row: pd.Series) -> str:
    emotion_state = str(row.get("emotion_state") or "")
    risk_state = str(row.get("risk_state") or "")
    if risk_state == "high" or emotion_state == "panic":
        return "light"
    if emotion_state == "cold" or risk_state == "medium":
        return "reduced"
    if emotion_state in {"hot", "euphoria"} and risk_state == "low":
        return "full"
    return "reduced"


def _avg_return(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    value = pd.to_numeric(frame["stock_return"], errors="coerce").mean()
    return 0.0 if pd.isna(value) else float(value)


def _rate(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    return float(values.fillna(False).astype(bool).mean())


def _distribution(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=["emotion_state", "risk_state", "days"])
    return (
        daily.groupby(["emotion_state", "risk_state"], dropna=False)
        .size()
        .reset_index(name="days")
        .sort_values(["emotion_state", "risk_state"])
    )


def _year_breakdown(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=["year", "emotion_state", "risk_state", "days"])
    frame = daily.copy()
    frame["year"] = frame["trade_date"].astype(str).str.slice(0, 4)
    return (
        frame.groupby(["year", "emotion_state", "risk_state"], dropna=False)
        .size()
        .reset_index(name="days")
        .sort_values(["year", "emotion_state", "risk_state"])
    )


def _write_mid_trend_breakdown(
    daily: pd.DataFrame,
    equity: pd.DataFrame,
    output_path: Path,
) -> Path:
    path = output_path / "market_emotion_mid_trend_state_breakdown.csv"
    if daily.empty or equity.empty:
        pd.DataFrame(
            columns=[
                "variant_name",
                "emotion_state",
                "risk_state",
                "days",
                "total_return",
                "avg_daily_return",
                "max_drawdown",
            ]
        ).to_csv(path, index=False)
        return path

    equity_frame = equity.copy()
    date_col = "date" if "date" in equity_frame.columns else "trade_date"
    equity_frame["trade_date"] = pd.to_datetime(
        equity_frame[date_col],
        errors="coerce",
    ).dt.date.astype(str)
    if "variant_name" not in equity_frame.columns:
        equity_frame["variant_name"] = "portfolio"
    if "net_return" not in equity_frame.columns:
        equity_frame["net_return"] = pd.to_numeric(
            equity_frame.get("gross_return", 0.0),
            errors="coerce",
        ).fillna(0.0)
    if "drawdown" not in equity_frame.columns:
        equity_frame["drawdown"] = 0.0
    merged = equity_frame.merge(
        daily[["trade_date", "emotion_state", "risk_state"]],
        on="trade_date",
        how="inner",
    )
    rows = []
    for keys, group in merged.groupby(["variant_name", "emotion_state", "risk_state"], dropna=False):
        variant_name, emotion_state, risk_state = keys
        returns = pd.to_numeric(group["net_return"], errors="coerce").fillna(0.0)
        drawdown = pd.to_numeric(group["drawdown"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "variant_name": variant_name,
                "emotion_state": emotion_state,
                "risk_state": risk_state,
                "days": int(len(group)),
                "total_return": float((1.0 + returns).prod() - 1.0),
                "avg_daily_return": float(returns.mean()),
                "max_drawdown": float(drawdown.min()),
            }
        )
    pd.DataFrame(rows).sort_values(["variant_name", "emotion_state", "risk_state"]).to_csv(
        path,
        index=False,
    )
    return path


def _render_report(
    daily: pd.DataFrame,
    distribution: pd.DataFrame,
    year: pd.DataFrame,
) -> str:
    lines = ["# Market Emotion State V1", ""]
    if daily.empty:
        lines.append("No rows generated.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            f"- Date range: `{daily['trade_date'].min()}` to `{daily['trade_date'].max()}`",
            f"- Rows: `{len(daily)}`",
            f"- Average emotion score: `{daily['emotion_score'].mean():.2f}`",
            "",
            "## Distribution",
            "",
            distribution.to_markdown(index=False),
            "",
            "## Year Breakdown",
            "",
            year.to_markdown(index=False),
            "",
            "## Notes",
            "",
            "- `style_signal_hint` and `position_budget_hint` are audit hints only.",
            "- Style switching and position sizing must remain separate downstream layers.",
        ]
    )
    return "\n".join(lines) + "\n"
