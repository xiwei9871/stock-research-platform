from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.market_style_switch_v1 import load_style_switch_prices


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

SEGMENT_WINDOWS = [
    ("pre_924_2024", "2024-01-01", "2024-09-23"),
    ("policy_rally_2024", "2024-09-24", "2024-11-08"),
    ("post_rally_2024", "2024-11-11", "2024-12-31"),
    ("post_2025", "2025-01-01", "2099-12-31"),
    ("full_period", "1900-01-01", "2099-12-31"),
]

SEGMENT_DIAGNOSTIC_COLUMNS = [
    "segment_name",
    "start_date",
    "end_date",
    "days",
    "avg_target_exposure",
    "dominant_regime",
    "regime_changes",
    "state_distribution",
    "transition_dates",
    "strategy_performance",
    "raw_confirmed_disagree_days",
]

TRANSITION_DIAGNOSTIC_COLUMNS = [
    "trade_date",
    "raw_regime_state",
    "confirmed_regime_state",
    "target_exposure",
    "style_bias",
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


def build_segment_diagnostics(regime: pd.DataFrame, equity: pd.DataFrame | None = None) -> pd.DataFrame:
    normalized = _normalize_regime_for_diagnostics(regime)
    normalized_equity = _normalize_equity_for_diagnostics(equity)
    rows = []
    for name, start, end in SEGMENT_WINDOWS:
        frame = normalized[normalized["trade_date"].between(start, end)].copy()
        if frame.empty:
            rows.append(
                {
                    "segment_name": name,
                    "start_date": start,
                    "end_date": end,
                    "days": 0,
                    "avg_target_exposure": 0.0,
                    "dominant_regime": "",
                    "regime_changes": 0,
                    "state_distribution": "",
                    "transition_dates": "",
                    "strategy_performance": "",
                    "raw_confirmed_disagree_days": 0,
                }
            )
            continue

        rows.append(
            {
                "segment_name": name,
                "start_date": str(frame["trade_date"].min()),
                "end_date": str(frame["trade_date"].max()),
                "days": int(len(frame)),
                "avg_target_exposure": float(frame["target_exposure"].mean()),
                "dominant_regime": str(frame["confirmed_regime_state"].mode().iloc[0]),
                "regime_changes": int(
                    frame["confirmed_regime_state"].ne(frame["confirmed_regime_state"].shift()).sum()
                ),
                "state_distribution": _serialize_state_distribution(frame),
                "transition_dates": _serialize_transition_dates(frame),
                "strategy_performance": _serialize_strategy_performance(normalized_equity, start, end),
                "raw_confirmed_disagree_days": int(
                    frame["raw_regime_state"].ne(frame["confirmed_regime_state"]).sum()
                ),
            }
        )
    return pd.DataFrame(rows, columns=SEGMENT_DIAGNOSTIC_COLUMNS)


def build_transition_diagnostics(regime: pd.DataFrame) -> pd.DataFrame:
    normalized = _normalize_regime_for_diagnostics(regime)
    if normalized.empty:
        return pd.DataFrame(columns=TRANSITION_DIAGNOSTIC_COLUMNS)

    changed = normalized["confirmed_regime_state"].ne(normalized["confirmed_regime_state"].shift())
    return normalized.loc[changed, TRANSITION_DIAGNOSTIC_COLUMNS].reset_index(drop=True)


def write_market_regime_confirmation_outputs(
    regime: pd.DataFrame,
    *,
    output_dir: str | Path,
    equity: pd.DataFrame | None = None,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_regime_for_diagnostics(regime)
    segment = build_segment_diagnostics(normalized, equity=equity)
    transitions = build_transition_diagnostics(normalized)
    paths = {
        "regime_path": output_path / "market_regime_confirmation_daily.csv",
        "segment_diagnostics_path": output_path / "market_regime_segment_diagnostics.csv",
        "transition_path": output_path / "market_regime_transitions.csv",
        "report_path": output_path / "market_regime_confirmation_v1_report.md",
    }

    normalized.to_csv(paths["regime_path"], index=False)
    segment.to_csv(paths["segment_diagnostics_path"], index=False)
    transitions.to_csv(paths["transition_path"], index=False)
    paths["report_path"].write_text(_render_report(normalized, segment, transitions), encoding="utf-8")
    return paths


def run_regime_confirmation_backtest_from_frames(
    *,
    emotion: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    policy_events: pd.DataFrame | None = None,
    top_n: int = 5,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    from stock_research.market_style_switch_v1 import (
        _build_strategy_selection,
        _filter_date_range,
        _simulate_equal_weight_daily,
        _summarize_equity,
        build_growth_momentum_candidates,
        run_style_switch_backtest_from_frames,
    )

    regime = build_market_regime_confirmation_from_frames(emotion, policy_events)
    regime = _filter_date_range(regime, start_date, end_date)
    style_backtest = run_style_switch_backtest_from_frames(
        emotion=emotion,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=None,
        top_n=top_n,
    )
    growth = _filter_date_range(
        build_growth_momentum_candidates(funnel, top_n=max(top_n, 10)),
        start_date,
        end_date,
    )

    style_state = regime[["trade_date", "emotion_state", "risk_state", "emotion_score"]].copy()
    style_state["style_state"] = "growth_momentum"
    style_state["position_budget_hint"] = "full"
    empty_candidates = pd.DataFrame(columns=growth.columns)

    fixed_selection = _build_strategy_selection(
        style_state,
        growth,
        empty_candidates,
        empty_candidates,
        "fixed_mid_trend",
        top_n,
    )
    regime_selection = fixed_selection.copy()
    exposure_by_date = _weekly_effective_exposure(regime).to_dict()
    regime_selection["strategy_family"] = "regime_confirmed_exposure"
    regime_selection["invested_weight"] = (
        regime_selection["trade_date"].map(exposure_by_date).astype(float).fillna(0.6)
    )

    equity = pd.concat(
        [
            style_backtest["equity"],
            _simulate_equal_weight_daily(
                prices,
                regime_selection,
                strategy_family="regime_confirmed_exposure",
            ),
        ],
        ignore_index=True,
    )
    summary = _summarize_equity(equity)

    paths: dict[str, Path] = {}
    if output_dir is not None:
        output_path = Path(output_dir)
        paths = write_market_regime_confirmation_outputs(regime, output_dir=output_path, equity=equity)
        paths["equity_path"] = output_path / "market_regime_backtest_equity.csv"
        paths["summary_path"] = output_path / "market_regime_backtest_summary.csv"
        equity.to_csv(paths["equity_path"], index=False)
        summary.to_csv(paths["summary_path"], index=False)

    return {"regime": regime, "equity": equity, "summary": summary, "paths": paths}


def _weekly_effective_exposure(regime: pd.DataFrame) -> pd.Series:
    if regime.empty or "trade_date" not in regime.columns:
        return pd.Series(dtype=float)

    frame = regime.copy()
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"].map(_normalize_trade_date_value), errors="coerce", format="mixed"
    ).dt.strftime("%Y-%m-%d")
    frame["target_exposure"] = pd.to_numeric(frame.get("target_exposure"), errors="coerce")
    if "rebalance_allowed" not in frame.columns:
        frame["rebalance_allowed"] = False
    frame["rebalance_allowed"] = frame["rebalance_allowed"].fillna(False).astype(bool)
    frame = frame.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        return pd.Series(dtype=float)

    first_targets = frame["target_exposure"].dropna()
    current = float(first_targets.iloc[0]) if not first_targets.empty else 0.6
    effective = []
    for row in frame.to_dict("records"):
        target = row.get("target_exposure")
        if bool(row.get("rebalance_allowed")) and not pd.isna(target):
            current = float(target)
        effective.append(current)

    return pd.Series(effective, index=frame["trade_date"].astype(str), dtype=float)


def run_market_regime_confirmation_v1_backtest(
    *,
    start_date: str,
    end_date: str,
    emotion_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
    policy_event_path: str | Path | None = None,
    top_n: int = 5,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    emotion = pd.read_csv(emotion_path, low_memory=False)
    funnel = pd.read_csv(funnel_detail_path, low_memory=False)
    policy_events = pd.read_csv(policy_event_path, low_memory=False) if policy_event_path else None
    prices = load_style_switch_prices(start_date, end_date, adjust_type=adjust_type, service=service)
    return run_regime_confirmation_backtest_from_frames(
        emotion=emotion,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        policy_events=policy_events,
        top_n=top_n,
        output_dir=output_dir,
    )


def _normalize_regime_for_diagnostics(regime: pd.DataFrame) -> pd.DataFrame:
    normalized = regime.copy()
    for column in REGIME_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    if normalized.empty:
        return pd.DataFrame(columns=REGIME_COLUMNS)

    trade_date = normalized["trade_date"].map(_normalize_trade_date_value)
    normalized["trade_date"] = pd.to_datetime(trade_date, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
    normalized["target_exposure"] = pd.to_numeric(normalized["target_exposure"], errors="coerce").fillna(0.0)
    normalized["raw_regime_state"] = normalized["raw_regime_state"].fillna("").astype(str)
    normalized["confirmed_regime_state"] = normalized["confirmed_regime_state"].fillna("").astype(str)
    normalized["style_bias"] = normalized["style_bias"].fillna("").astype(str)
    normalized["transition_reason"] = normalized["transition_reason"].fillna("").astype(str)
    normalized = normalized.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    return normalized[REGIME_COLUMNS]


def _normalize_equity_for_diagnostics(equity: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["trade_date", "strategy_family", "daily_return", "equity"]
    if equity is None or equity.empty:
        return pd.DataFrame(columns=columns)

    normalized = equity.copy()
    if "trade_date" not in normalized.columns and "date" in normalized.columns:
        normalized["trade_date"] = normalized["date"]
    if "trade_date" not in normalized.columns:
        return pd.DataFrame(columns=columns)
    if "strategy_family" not in normalized.columns:
        normalized["strategy_family"] = ""
    if "daily_return" not in normalized.columns:
        normalized["daily_return"] = pd.NA
    if "equity" not in normalized.columns:
        normalized["equity"] = pd.NA

    trade_date = normalized["trade_date"].map(_normalize_trade_date_value)
    normalized["trade_date"] = pd.to_datetime(trade_date, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
    normalized["strategy_family"] = normalized["strategy_family"].fillna("").astype(str)
    normalized["daily_return"] = pd.to_numeric(normalized["daily_return"], errors="coerce")
    normalized["equity"] = pd.to_numeric(normalized["equity"], errors="coerce")
    normalized = normalized.dropna(subset=["trade_date"]).sort_values(["trade_date", "strategy_family"]).reset_index(
        drop=True
    )
    return normalized[columns]


def _serialize_state_distribution(frame: pd.DataFrame) -> str:
    counts = frame["confirmed_regime_state"].astype(str).value_counts()
    return ";".join(f"{state}:{int(days)}" for state, days in counts.items() if state)


def _serialize_transition_dates(frame: pd.DataFrame) -> str:
    changed = frame["confirmed_regime_state"].ne(frame["confirmed_regime_state"].shift())
    dates = frame.loc[changed & frame["confirmed_regime_state"].shift().notna(), "trade_date"].astype(str).tolist()
    return ";".join(dates)


def _serialize_strategy_performance(equity: pd.DataFrame, start: str, end: str) -> str:
    if equity.empty:
        return ""

    frame = equity[equity["trade_date"].between(start, end)].copy()
    if frame.empty:
        return ""

    parts = []
    for strategy_family, group in frame.groupby("strategy_family", sort=True):
        group = group.sort_values("trade_date")
        days = int(len(group))
        if not days:
            continue

        daily_return = group["daily_return"].dropna().astype(float)
        if not daily_return.empty:
            total_return = float((1.0 + daily_return).prod() - 1.0)
            equity_curve = (1.0 + daily_return).cumprod()
        else:
            equity_curve = group["equity"].dropna().astype(float)
            if equity_curve.empty:
                continue
            first = float(equity_curve.iloc[0])
            total_return = float(equity_curve.iloc[-1] / first - 1.0) if first else 0.0

        parts.append(
            f"{strategy_family}:ret={total_return:.6f},dd={_max_drawdown(equity_curve):.6f},days={days}"
        )
    return "|".join(parts)


def _max_drawdown(equity_curve: pd.Series) -> float:
    if equity_curve.empty:
        return 0.0
    curve = pd.concat([pd.Series([1.0]), equity_curve.astype(float)], ignore_index=True)
    drawdown = curve / curve.cummax() - 1.0
    return float(drawdown.min())


def _render_report(regime: pd.DataFrame, segment: pd.DataFrame, transitions: pd.DataFrame) -> str:
    distribution = (
        regime["confirmed_regime_state"].value_counts().rename_axis("state").reset_index(name="days")
        if "confirmed_regime_state" in regime.columns
        else pd.DataFrame(columns=["state", "days"])
    )
    sections = [
        "# Market Regime Confirmation V1 Report",
        "",
        "## Segment Diagnostics",
        _frame_to_markdown(segment),
        "",
        "## Confirmed Regime Distribution",
        _frame_to_markdown(distribution),
        "",
        "## Transitions",
        _frame_to_markdown(transitions),
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
