#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.tech_bottleneck_v1 import _load_prices


INPUT_DIR = Path("outputs/research/tech_bottleneck_research_selection_layer_v1")
DESIGN_DOC = Path("outputs/research/tech_bottleneck_strategy_redesign_v1/tech_bottleneck_strategy_redesign_v1.md")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_setup_state_machine_v1")
RULE_VERSION = "tech_bottleneck_setup_state_machine_v1"

ALLOWED_STATES = {
    "research_candidate",
    "technical_watch",
    "compression_setup",
    "breakout_candidate",
    "failed_setup",
}
ALLOWED_REVIEW_ACTIONS = {
    "review_setup_state",
    "monitor_compression",
    "review_breakout_candidate",
    "review_failed_setup",
    "watch_only",
}
FORBIDDEN_TRADING_WORDS = {"buy", "sell", "add", "reduce", "hold", "target_price"}


def _num(value: Any, default: float = np.nan) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(default if pd.isna(parsed) else parsed)


def _symbol(asset_id: Any) -> str:
    return str(asset_id).split(":")[-1]


def classify_state(row: pd.Series) -> tuple[str, str]:
    if bool(row.get("recent_drawdown_risk_flag", False)) or _num(row.get("price_vs_ma60"), 0.0) < -0.10:
        return "failed_setup", "trend_break_ma60_or_recent_drawdown"
    if _num(row.get("price_vs_ma20"), 0.0) < -0.07 and str(row.get("relative_strength_state", "")) == "weak":
        return "failed_setup", "ma20_break_relative_weak"
    if bool(row.get("close_above_breakout_20d", False)) and not bool(row.get("limit_up_flag", False)):
        if str(row.get("relative_strength_state", "")) in {"strong", "neutral"} and _num(row.get("price_vs_ma20"), 0.0) > -0.02:
            return "breakout_candidate", "price_breakout_with_relative_strength"
    compression_ok = (
        _num(row.get("range_contraction_20d"), 1.0) <= 0.85
        and _num(row.get("atr_percentile_60d"), 1.0) <= 0.55
        and -0.10 <= _num(row.get("distance_to_breakout_level"), -1.0) <= 0.025
        and _num(row.get("price_vs_ma20"), 0.0) > -0.035
        and str(row.get("relative_strength_state", "")) != "weak"
    )
    if compression_ok:
        return "compression_setup", "compressed_near_breakout_level"
    watch_ok = (
        _num(row.get("price_vs_ma60"), -1.0) > -0.08
        and _num(row.get("price_vs_ma20"), -1.0) > -0.08
        and str(row.get("relative_strength_state", "")) != "weak"
    )
    if watch_ok:
        return "technical_watch", "trend_not_broken"
    return "research_candidate", "research_pool_only"


def validate_no_trading_language(frame: pd.DataFrame) -> None:
    text_columns = [
        column
        for column in frame.columns
        if any(token in column.lower() for token in ["state", "reason", "action", "note"])
    ]
    for column in text_columns:
        lowered = frame[column].fillna("").astype(str).str.lower()
        for word in FORBIDDEN_TRADING_WORDS:
            if lowered.str.contains(word, regex=False).any():
                raise ValueError(f"trading language found in {column}: {word}")


def validate_forward_returns_research_only(frame: pd.DataFrame) -> None:
    if "used_for_signal" not in frame.columns:
        raise ValueError("used_for_signal column is required")
    if frame["used_for_signal"].astype(bool).any():
        raise ValueError("forward returns must have used_for_signal=false")


def validate_pit_dates(frame: pd.DataFrame) -> None:
    trade_date = pd.to_datetime(frame["trade_date"], errors="coerce")
    for column in ["price_date", "technical_as_of_date"]:
        if column in frame.columns:
            as_of = pd.to_datetime(frame[column], errors="coerce")
            if as_of.gt(trade_date).fillna(False).any():
                raise ValueError(f"lookahead detected in {column}")


def _load_inputs(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidates = pd.read_csv(input_dir / "tech_bottleneck_research_candidates.csv", low_memory=False)
    review_cards = pd.read_csv(input_dir / "tech_bottleneck_review_cards.csv", low_memory=False)
    low_position = pd.read_csv(input_dir / "research_selection_low_position_breakdown.csv", low_memory=False)
    risk = pd.read_csv(input_dir / "research_selection_risk_audit.csv", low_memory=False)
    for frame in [candidates, review_cards, low_position, risk]:
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        frame["asset_id"] = frame["asset_id"].astype(str)
    return candidates, review_cards, low_position, risk


def _load_price_frame(candidates: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    asset_ids = sorted(candidates["asset_id"].dropna().astype(str).unique().tolist())
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type="hfq",
        asset_ids=asset_ids,
        service=SETTINGS.research_service,
    )
    prices["trade_date"] = pd.to_datetime(prices["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    prices["asset_id"] = prices["asset_id"].astype(str)
    for column in ["open", "high", "low", "close"]:
        prices[column] = pd.to_numeric(prices[column], errors="coerce")
    return prices.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=max(10, window // 4)).apply(
        lambda values: float(pd.Series(values).rank(pct=True).iloc[-1]),
        raw=False,
    )


def build_technical_features(candidates: pd.DataFrame, prices: pd.DataFrame, low_position: pd.DataFrame, risk: pd.DataFrame) -> pd.DataFrame:
    prices = prices.copy()
    grouped = prices.groupby("asset_id", group_keys=False)
    prices["prev_close"] = grouped["close"].shift(1)
    prices["ma20"] = grouped["close"].transform(lambda values: values.rolling(20, min_periods=5).mean())
    prices["ma60"] = grouped["close"].transform(lambda values: values.rolling(60, min_periods=15).mean())
    prices["high20_prev"] = grouped["high"].transform(lambda values: values.rolling(20, min_periods=5).max().shift(1))
    prices["high60_prev"] = grouped["high"].transform(lambda values: values.rolling(60, min_periods=15).max().shift(1))
    prices["low20"] = grouped["low"].transform(lambda values: values.rolling(20, min_periods=5).min())
    prices["low60"] = grouped["low"].transform(lambda values: values.rolling(60, min_periods=15).min())
    prices["range20"] = (prices["high20_prev"] - prices["low20"]) / prices["close"].replace(0, np.nan)
    prices["range60"] = (prices["high60_prev"] - prices["low60"]) / prices["close"].replace(0, np.nan)
    prices["range20_avg60"] = grouped["range20"].transform(lambda values: values.rolling(60, min_periods=15).mean())
    prices["range60_avg120"] = grouped["range60"].transform(lambda values: values.rolling(120, min_periods=30).mean())
    high_low = prices["high"] - prices["low"]
    high_prev = (prices["high"] - prices["prev_close"]).abs()
    low_prev = (prices["low"] - prices["prev_close"]).abs()
    prices["true_range"] = pd.concat([high_low, high_prev, low_prev], axis=1).max(axis=1)
    prices["atr14_pct"] = grouped["true_range"].transform(lambda values: values.rolling(14, min_periods=5).mean()) / prices[
        "close"
    ].replace(0, np.nan)
    prices["atr_percentile_60d"] = grouped["atr14_pct"].transform(lambda values: _rolling_percentile(values, 60))
    prices["ret20"] = grouped["close"].pct_change(20)
    market_ret20 = prices.groupby("trade_date")["ret20"].mean().rename("market_ret20")
    prices = prices.merge(market_ret20, on="trade_date", how="left")
    prices["relative_strength_20d"] = prices["ret20"] - prices["market_ret20"]
    prices["price_vs_ma20"] = prices["close"] / prices["ma20"].replace(0, np.nan) - 1.0
    prices["price_vs_ma60"] = prices["close"] / prices["ma60"].replace(0, np.nan) - 1.0
    prices["breakout_level_20d"] = prices["high20_prev"]
    prices["breakout_level_60d"] = prices["high60_prev"]
    prices["nearest_breakout_level"] = prices[["breakout_level_20d", "breakout_level_60d"]].min(axis=1)
    prices["distance_to_breakout_level"] = prices["close"] / prices["nearest_breakout_level"].replace(0, np.nan) - 1.0
    prices["close_above_breakout_20d"] = prices["close"].gt(prices["breakout_level_20d"]).fillna(False)
    prices["range_contraction_20d"] = prices["range20"] / prices["range20_avg60"].replace(0, np.nan)
    prices["range_contraction_60d"] = prices["range60"] / prices["range60_avg120"].replace(0, np.nan)
    prices["amount_vs_amount_ma20"] = np.nan
    prices["volume_state"] = "amount_missing"
    prices["relative_strength_state"] = np.select(
        [prices["relative_strength_20d"].ge(0.05), prices["relative_strength_20d"].le(-0.05)],
        ["strong", "weak"],
        default="neutral",
    )
    prices["trend_state"] = np.select(
        [prices["price_vs_ma60"].ge(0.03), prices["price_vs_ma60"].le(-0.08)],
        ["uptrend", "broken"],
        default="repairing_or_flat",
    )
    prices["liquidity_state"] = "price_data_available_amount_missing"
    prices["limit_up_flag"] = (prices["close"] / prices["open"].replace(0, np.nan) - 1.0).ge(0.095).fillna(False)
    prices["suspension_flag"] = prices[["open", "high", "low", "close"]].isna().any(axis=1)
    prices["price_date"] = prices["trade_date"]
    prices["technical_as_of_date"] = prices["trade_date"]

    frame = candidates.merge(prices, on=["trade_date", "asset_id"], how="left")
    low_cols = [
        "trade_date",
        "asset_id",
        "low_position_score",
        "technical_position_score",
        "price_drawdown_from_120d_high",
        "price_percentile_120d",
    ]
    frame = frame.merge(low_position[[column for column in low_cols if column in low_position.columns]], on=["trade_date", "asset_id"], how="left", suffixes=("", "_lp"))
    risk_cols = ["trade_date", "asset_id", "recent_drawdown_risk_flag", "risk_flags"]
    frame = frame.merge(risk[[column for column in risk_cols if column in risk.columns]], on=["trade_date", "asset_id"], how="left")
    frame["recent_drawdown_risk_flag"] = frame["recent_drawdown_risk_flag"].fillna(False).astype(bool)
    frame["technical_setup_score"] = frame.apply(_technical_setup_score, axis=1)
    classified = frame.apply(classify_state, axis=1, result_type="expand")
    frame["current_state"] = classified[0]
    frame["state_reason"] = classified[1]
    frame["failed_setup_reason"] = np.where(frame["current_state"].eq("failed_setup"), frame["state_reason"], "")
    frame["data_quality_status"] = frame.get("data_quality_status", "ok").fillna("ok").astype(str)
    frame["data_quality_status"] = np.where(
        frame["amount_vs_amount_ma20"].isna(),
        frame["data_quality_status"] + "|volume_amount_missing",
        frame["data_quality_status"],
    )
    frame["rule_version"] = RULE_VERSION
    return _add_state_history(frame)


def _technical_setup_score(row: pd.Series) -> float:
    trend = np.clip((_num(row.get("price_vs_ma60"), -0.2) + 0.10) / 0.25, 0.0, 1.0)
    compression = np.clip(1.0 - _num(row.get("range_contraction_20d"), 1.0), 0.0, 1.0)
    atr = np.clip(1.0 - _num(row.get("atr_percentile_60d"), 1.0), 0.0, 1.0)
    breakout = np.clip(1.0 - abs(_num(row.get("distance_to_breakout_level"), -0.25)) / 0.15, 0.0, 1.0)
    rs = {"strong": 1.0, "neutral": 0.55, "weak": 0.1}.get(str(row.get("relative_strength_state", "")), 0.4)
    return float(np.clip(0.25 * trend + 0.25 * compression + 0.15 * atr + 0.20 * breakout + 0.15 * rs, 0.0, 1.0))


def _add_state_history(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_values(["asset_id", "trade_date"]).copy()
    frame["previous_state"] = frame.groupby("asset_id")["current_state"].shift(1).fillna("none")
    frame["state_changed"] = frame["current_state"].ne(frame["previous_state"])
    frame.loc[frame["previous_state"].eq("none"), "state_changed"] = True
    frame["state_segment"] = frame.groupby("asset_id")["state_changed"].cumsum()
    frame["state_entry_date"] = frame.groupby(["asset_id", "state_segment"])["trade_date"].transform("first")
    frame["days_in_state"] = (
        pd.to_datetime(frame["trade_date"], errors="coerce") - pd.to_datetime(frame["state_entry_date"], errors="coerce")
    ).dt.days
    return frame.drop(columns=["state_segment"])


def build_setup_states(features: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "symbol",
        "name",
        "research_priority",
        "current_state",
        "previous_state",
        "state_changed",
        "state_entry_date",
        "days_in_state",
        "technical_setup_score",
        "trend_state",
        "ma20",
        "ma60",
        "price_vs_ma20",
        "price_vs_ma60",
        "compression_score",
        "range_contraction_20d",
        "range_contraction_60d",
        "atr_percentile_60d",
        "breakout_level_20d",
        "breakout_level_60d",
        "distance_to_breakout_level",
        "volume_state",
        "amount_vs_amount_ma20",
        "relative_strength_state",
        "liquidity_state",
        "limit_up_flag",
        "suspension_flag",
        "failed_setup_reason",
        "data_quality_status",
        "rule_version",
        "price_date",
        "technical_as_of_date",
        "evidence_state",
        "low_position_score",
        "close",
        "risk_flags",
    ]
    frame = features.copy()
    frame["compression_score"] = np.clip(1.0 - pd.to_numeric(frame["range_contraction_20d"], errors="coerce"), 0.0, 1.0)
    frame["symbol"] = frame.get("symbol", frame["asset_id"].map(_symbol)).fillna("").astype(str)
    frame["name"] = frame.get("name", "").fillna("").astype(str)
    return frame[[column for column in columns if column in frame.columns]]


def build_forward_return_analysis(states: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    states = states.copy()
    entry_events = states[states["state_changed"]].copy()
    entry_events = entry_events[entry_events["current_state"].isin(ALLOWED_STATES)]
    price_by_asset = {asset_id: group.sort_values("trade_date").reset_index(drop=True) for asset_id, group in prices.groupby("asset_id")}
    market_close = prices.groupby("trade_date")["close"].mean().sort_index()
    horizons = [5, 10, 20, 60]
    rows: list[dict[str, Any]] = []
    for event in entry_events.itertuples(index=False):
        asset_prices = price_by_asset.get(str(event.asset_id))
        if asset_prices is None:
            continue
        locs = asset_prices.index[asset_prices["trade_date"].eq(str(event.trade_date))].tolist()
        if not locs:
            continue
        start_idx = locs[0]
        start_close = _num(asset_prices.loc[start_idx, "close"])
        market_dates = list(market_close.index)
        market_start = market_close.get(str(event.trade_date), np.nan)
        market_start_idx = market_dates.index(str(event.trade_date)) if str(event.trade_date) in market_dates else None
        for horizon in horizons:
            end_idx = start_idx + horizon
            available = bool(end_idx < len(asset_prices) and pd.notna(start_close) and start_close != 0)
            end_close = _num(asset_prices.loc[end_idx, "close"]) if available else np.nan
            window = asset_prices.loc[start_idx : min(end_idx, len(asset_prices) - 1), "close"]
            market_return = np.nan
            if market_start_idx is not None and market_start_idx + horizon < len(market_dates) and pd.notna(market_start) and market_start != 0:
                market_end = market_close.iloc[market_start_idx + horizon]
                market_return = float(market_end / market_start - 1.0)
            forward = float(end_close / start_close - 1.0) if available else np.nan
            rows.append(
                {
                    "state_entry_date": event.trade_date,
                    "asset_id": event.asset_id,
                    "symbol": event.symbol,
                    "name": event.name,
                    "state": event.current_state,
                    "horizon": f"{horizon}d",
                    "forward_return": forward,
                    "forward_return_vs_market": forward - market_return if pd.notna(forward) and pd.notna(market_return) else np.nan,
                    "max_favorable_excursion": float(window.max() / start_close - 1.0) if available and not window.empty else np.nan,
                    "max_adverse_excursion": float(window.min() / start_close - 1.0) if available and not window.empty else np.nan,
                    "future_data_available": available,
                    "used_for_signal": False,
                }
            )
    return pd.DataFrame(rows)


def build_transition_summary(states: pd.DataFrame, forward: pd.DataFrame) -> pd.DataFrame:
    states = states.copy().sort_values(["asset_id", "trade_date"])
    states["next_state"] = states.groupby("asset_id")["current_state"].shift(-1)
    forward_pivot = (
        forward.pivot_table(index=["asset_id", "state_entry_date", "state"], columns="horizon", values="forward_return", aggfunc="mean")
        .reset_index()
        .rename(columns={"5d": "forward_5d_return", "10d": "forward_10d_return", "20d": "forward_20d_return", "60d": "forward_60d_return"})
    )
    mae_mfe = (
        forward[forward["horizon"].eq("20d")]
        .groupby(["asset_id", "state_entry_date", "state"], as_index=False)
        .agg(max_adverse_excursion=("max_adverse_excursion", "mean"), max_favorable_excursion=("max_favorable_excursion", "mean"))
    )
    entry = states[states["state_changed"]].merge(
        forward_pivot,
        left_on=["asset_id", "trade_date", "current_state"],
        right_on=["asset_id", "state_entry_date", "state"],
        how="left",
    )
    entry = entry.merge(
        mae_mfe,
        left_on=["asset_id", "trade_date", "current_state"],
        right_on=["asset_id", "state_entry_date", "state"],
        how="left",
        suffixes=("", "_mae"),
    )
    entry["low_position_bucket"] = pd.cut(
        pd.to_numeric(entry.get("low_position_score"), errors="coerce"),
        bins=[-0.01, 0.33, 0.66, 1.01],
        labels=["low_score", "mid_score", "high_score"],
    ).astype(str)
    groups: list[tuple[str, str, pd.DataFrame]] = [("overall", "all", entry)]
    for column, group_type in [
        ("research_priority", "research_priority"),
        ("evidence_state", "evidence_state"),
        ("low_position_bucket", "low_position_bucket"),
    ]:
        if column in entry.columns:
            for value, group in entry.groupby(column, dropna=False):
                groups.append((group_type, str(value), group))
    rows: list[dict[str, Any]] = []
    for group_type, group_value, group in groups:
        for state, state_group in group.groupby("current_state"):
            transition_count = int(
                state_group.apply(lambda row: _is_next_transition(row["current_state"], row.get("next_state")), axis=1).sum()
            )
            if state == "failed_setup":
                failed_count = int(len(state_group))
            else:
                failed_count = int(state_group["next_state"].eq("failed_setup").sum())
            row_count = int(len(state_group))
            rows.append(
                {
                    "group_type": group_type,
                    "group_value": group_value,
                    "state": state,
                    "row_count": row_count,
                    "unique_asset_count": int(state_group["asset_id"].nunique()),
                    "transition_to_next_state_count": transition_count,
                    "transition_to_next_state_rate": transition_count / row_count if row_count else np.nan,
                    "failed_setup_count": failed_count,
                    "failed_setup_rate": failed_count / row_count if row_count else np.nan,
                    "avg_forward_5d_return": float(state_group["forward_5d_return"].mean()),
                    "avg_forward_10d_return": float(state_group["forward_10d_return"].mean()),
                    "avg_forward_20d_return": float(state_group["forward_20d_return"].mean()),
                    "avg_forward_60d_return": float(state_group["forward_60d_return"].mean()),
                    "avg_mae_20d": float(state_group["max_adverse_excursion"].mean()),
                    "avg_mfe_20d": float(state_group["max_favorable_excursion"].mean()),
                }
            )
    return pd.DataFrame(rows)


def _is_next_transition(state: str, next_state: Any) -> bool:
    expected = {
        "research_candidate": "technical_watch",
        "technical_watch": "compression_setup",
        "compression_setup": "breakout_candidate",
    }
    return expected.get(str(state)) == str(next_state)


def build_examples(states: pd.DataFrame, forward: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    forward20 = forward[forward["horizon"].eq("20d")][
        ["state_entry_date", "asset_id", "forward_return", "max_adverse_excursion", "max_favorable_excursion"]
    ]
    entries = states[states["state_changed"]].copy()
    failed = entries[entries["current_state"].eq("failed_setup")].merge(
        forward20, left_on=["trade_date", "asset_id"], right_on=["state_entry_date", "asset_id"], how="left"
    )
    failed_examples = failed.sort_values("max_adverse_excursion", na_position="last").head(50).assign(
        setup_date=lambda df: df["state_entry_date_x"].fillna(df["trade_date"]) if "state_entry_date_x" in df.columns else df["trade_date"],
        failed_date=lambda df: df["trade_date"],
        days_to_failure=0,
        setup_state_features=lambda df: df.apply(
            lambda row: f"trend={row.get('trend_state')};rs={row.get('relative_strength_state')};score={row.get('technical_setup_score'):.3f}",
            axis=1,
        ),
        review_note="research_only_failed_setup_review",
    )
    failed_cols = [
        "asset_id",
        "symbol",
        "name",
        "setup_date",
        "failed_date",
        "days_to_failure",
        "failed_setup_reason",
        "setup_state_features",
        "forward_return",
        "max_adverse_excursion",
        "review_note",
    ]
    breakout = entries[entries["current_state"].eq("breakout_candidate")].merge(
        forward[forward["horizon"].isin(["5d", "10d", "20d"])],
        left_on=["trade_date", "asset_id"],
        right_on=["state_entry_date", "asset_id"],
        how="left",
        suffixes=("", "_fwd"),
    )
    breakout["amount_vs_amount_ma20_label"] = breakout["amount_vs_amount_ma20"].fillna("amount_missing")
    breakout_pivot = breakout.pivot_table(
        index=[
            "asset_id",
            "symbol",
            "name",
            "trade_date",
            "breakout_level_20d",
            "close",
            "amount_vs_amount_ma20_label",
            "relative_strength_state",
        ],
        columns="horizon",
        values="forward_return",
        aggfunc="mean",
    ).reset_index()
    if breakout_pivot.empty:
        breakout_examples = pd.DataFrame(
            columns=[
                "asset_id",
                "symbol",
                "name",
                "breakout_candidate_date",
                "breakout_level",
                "close",
                "amount_vs_amount_ma20",
                "relative_strength_state",
                "forward_5d_return",
                "forward_10d_return",
                "forward_20d_return",
                "max_favorable_excursion",
                "max_adverse_excursion",
                "review_note",
            ]
        )
    else:
        mfe_mae = forward[forward["horizon"].eq("20d")][
            ["state_entry_date", "asset_id", "max_favorable_excursion", "max_adverse_excursion"]
        ]
        breakout_examples = breakout_pivot.merge(
            mfe_mae,
            left_on=["trade_date", "asset_id"],
            right_on=["state_entry_date", "asset_id"],
            how="left",
        )
        breakout_examples = breakout_examples.rename(
            columns={
                "trade_date": "breakout_candidate_date",
                "breakout_level_20d": "breakout_level",
                "amount_vs_amount_ma20_label": "amount_vs_amount_ma20",
                "5d": "forward_5d_return",
                "10d": "forward_10d_return",
                "20d": "forward_20d_return",
            }
        )
        breakout_examples["review_note"] = "research_only_breakout_candidate_review"
        breakout_examples = breakout_examples.sort_values("forward_20d_return", ascending=False, na_position="last").head(50)
    return failed_examples[[column for column in failed_cols if column in failed_examples.columns]], breakout_examples


def _git_info(repo_root: Path) -> dict[str, str]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
        return (completed.stdout + completed.stderr).strip()

    targets = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]
    return {
        "repo_root": run(["rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run(["status", "--short", "--", *targets]),
        "formal_strategy_ls_files": run(["ls-files", "--", *targets]),
        "formal_strategy_stat": subprocess.run(
            ["stat", "-f", "%Sm %N", *targets], cwd=repo_root, text=True, capture_output=True, check=False
        ).stdout.strip(),
    }


def write_report(
    output_dir: Path,
    states: pd.DataFrame,
    forward: pd.DataFrame,
    summary: pd.DataFrame,
    failed: pd.DataFrame,
    breakout: pd.DataFrame,
    git_info: dict[str, str],
    input_availability: dict[str, bool],
) -> None:
    state_counts = states["current_state"].value_counts().rename_axis("state").reset_index(name="rows")
    state_table = state_counts.to_markdown(index=False)
    forward_table = (
        forward.groupby(["state", "horizon"], as_index=False)
        .agg(
            samples=("forward_return", "count"),
            avg_forward_return=("forward_return", "mean"),
            avg_mfe=("max_favorable_excursion", "mean"),
            avg_mae=("max_adverse_excursion", "mean"),
        )
        .pivot(index="state", columns="horizon", values="avg_forward_return")
        .reset_index()
        .to_markdown(index=False)
    )
    transition_table = summary[summary["group_type"].eq("overall")][
        [
            "state",
            "row_count",
            "unique_asset_count",
            "transition_to_next_state_rate",
            "failed_setup_rate",
            "avg_forward_20d_return",
            "avg_mfe_20d",
            "avg_mae_20d",
        ]
    ].to_markdown(index=False)
    report = f"""# Tech Bottleneck Setup State Machine v1

## 1. Executive Summary

- Generated a research-only technical setup state machine with {len(states):,} trade_date x asset_id rows.
- State distribution:

{state_table}

- Forward returns are written only for post-hoc research with `used_for_signal=false`.
- OHLC data is PIT as of each trade date; `amount` is not available through the reused formal loader, so volume fields are marked `amount_missing`.
- `breakout_candidate` is a research state only, not an entry signal.
- Failed setup rows require explicit `failed_setup_reason`.
- Formal strategy files were not written by this script; both formal strategy files are currently untracked in git, so git diff alone cannot fully prove historical immutability.
- Recommended next step: inspect whether S2/S3 forward returns justify `tech_bottleneck_trigger_holding_exit_replay_v1`; otherwise refine compression/volume data first.

## 2. Input Files and Data Availability

- Input directory: `{INPUT_DIR}`
- Design document available: `{input_availability.get('design_doc')}`
- Research candidates available: `{input_availability.get('candidates')}`
- Review cards available: `{input_availability.get('review_cards')}`
- Low-position breakdown available: `{input_availability.get('low_position')}`
- Risk audit available: `{input_availability.get('risk_audit')}`
- Price source: `stock_research.tech_bottleneck_v1._load_prices`, read-only OHLC from `market_daily_bar`.
- Missing field: `amount`; `amount_vs_amount_ma20` is `NaN`, and `volume_state=amount_missing`.

## 3. State Definitions

- S0 `research_candidate`: in research candidate pool but not technically repaired enough.
- S1 `technical_watch`: MA20/MA60 not materially broken and relative strength is not weak.
- S2 `compression_setup`: range/ATR contraction, near breakout level, MA20 not broken, relative strength not weak.
- S3 `breakout_candidate`: close exceeds prior 20d breakout level with acceptable relative strength and no limit-up flag. Research-only.
- S4 `failed_setup`: MA60/trend break, recent drawdown risk, or MA20 break plus weak relative strength.

## 4. State Distribution and Transition

{transition_table}

## 5. Forward Return Analysis

Average forward return by state and horizon:

{forward_table}

Forward return columns are not used in state classification. They are emitted only for attribution and setup-quality research.

## 6. Research Priority / Evidence / Low Position Breakdown

See `tech_bottleneck_setup_transition_summary.csv` for grouped summaries by:

- `research_priority`
- `evidence_state`
- `low_position_bucket`

The v1 state machine uses research candidates as the universe but does not use evidence as a multiplier or trade-ranking input.

## 7. Failed Setup Review

- Failed examples file: `tech_bottleneck_failed_setup_examples.csv`
- Example rows: {len(failed):,}
- Main failure reason distribution:

{failed.get('failed_setup_reason', pd.Series(dtype='object')).value_counts().head(10).rename_axis('reason').reset_index(name='count').to_markdown(index=False) if not failed.empty else 'No failed setup examples.'}

## 8. Breakout Candidate Review

- Breakout candidate examples file: `tech_bottleneck_breakout_candidate_examples.csv`
- Example rows: {len(breakout):,}
- Breakout candidates remain research-only and require a separate trigger / holding / exit replay before any strategy consideration.

## 9. What This Layer Does Not Do

- Does not produce buy signals.
- Does not produce sell signals.
- Does not change Top5.
- Does not change formal strategy logic.
- Does not use evidence multiplier.
- Does not output trading instructions.

## 10. Recommendation

- If S2/S3 forward-return tables show stable positive edge and acceptable MAE, proceed to `tech_bottleneck_trigger_holding_exit_replay_v1`.
- Before production discussion, add true `amount` / turnover / limit-up execution fields; current volume state is degraded.
- If S3 sample is sparse or unstable, refine setup rules and data coverage first instead of adding trading simulation.

## 11. Appendix

Generated files:

- `tech_bottleneck_setup_states.csv`
- `tech_bottleneck_setup_forward_return_analysis.csv`
- `tech_bottleneck_setup_transition_summary.csv`
- `tech_bottleneck_failed_setup_examples.csv`
- `tech_bottleneck_breakout_candidate_examples.csv`
- `tech_bottleneck_setup_state_machine_v1.md`

Git / formal strategy file check:

- repo root: `{git_info.get('repo_root')}`
- `git status --short` for formal files:

```text
{git_info.get('formal_strategy_status') or '(empty)'}
```

- `git ls-files` for formal files:

```text
{git_info.get('formal_strategy_ls_files') or '(empty; files are not tracked)'}
```

- `stat` for formal files:

```text
{git_info.get('formal_strategy_stat')}
```

Conclusion: both formal strategy paths are untracked in this repo state. This task does not write them, but if a file is untracked, `git diff` cannot fully prove no historical modification.

Key assumptions:

- Candidate universe comes from research selection v1.
- `price_date <= trade_date` and `technical_as_of_date <= trade_date` for all emitted state rows.
- Forward returns are post-event diagnostics only.
"""
    (output_dir / "tech_bottleneck_setup_state_machine_v1.md").write_text(report, encoding="utf-8")


def run(output_dir: Path = OUTPUT_DIR, input_dir: Path = INPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, review_cards, low_position, risk = _load_inputs(input_dir)
    start_date = str(candidates["trade_date"].min())
    end_date = str(candidates["trade_date"].max())
    prices = _load_price_frame(candidates, start_date, end_date)
    features = build_technical_features(candidates, prices, low_position, risk)
    states = build_setup_states(features)
    validate_pit_dates(states)
    validate_no_trading_language(states)
    forward = build_forward_return_analysis(states, prices)
    validate_forward_returns_research_only(forward)
    summary = build_transition_summary(states, forward)
    failed, breakout = build_examples(states, forward)
    validate_no_trading_language(failed)
    validate_no_trading_language(breakout)

    states.to_csv(output_dir / "tech_bottleneck_setup_states.csv", index=False)
    forward.to_csv(output_dir / "tech_bottleneck_setup_forward_return_analysis.csv", index=False)
    summary.to_csv(output_dir / "tech_bottleneck_setup_transition_summary.csv", index=False)
    failed.to_csv(output_dir / "tech_bottleneck_failed_setup_examples.csv", index=False)
    breakout.to_csv(output_dir / "tech_bottleneck_breakout_candidate_examples.csv", index=False)
    git_info = _git_info(Path.cwd())
    input_availability = {
        "design_doc": DESIGN_DOC.exists(),
        "candidates": (input_dir / "tech_bottleneck_research_candidates.csv").exists(),
        "review_cards": (input_dir / "tech_bottleneck_review_cards.csv").exists(),
        "low_position": (input_dir / "research_selection_low_position_breakdown.csv").exists(),
        "risk_audit": (input_dir / "research_selection_risk_audit.csv").exists(),
    }
    write_report(output_dir, states, forward, summary, failed, breakout, git_info, input_availability)
    return {
        "states": states,
        "forward": forward,
        "summary": summary,
        "failed": failed,
        "breakout": breakout,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck setup state machine v1.")
    parser.add_argument("--input-dir", default=str(INPUT_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir), input_dir=Path(args.input_dir))
    states = result["states"]
    print(f"wrote {len(states):,} setup state rows to {args.output_dir}")
    print(states["current_state"].value_counts().to_string())


if __name__ == "__main__":
    main()
