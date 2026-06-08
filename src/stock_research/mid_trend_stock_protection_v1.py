from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd


@dataclass(frozen=True)
class StockProtectionConfig:
    variant_name: str
    fixed_stop_loss: float | None = None
    atr_multiple: float | None = None
    atr_multiple_by_regime: Mapping[str, float] | None = None
    score_break_rank: int = 30
    rank_break_days: int = 1
    score_decline_days: int = 2
    cooldown_days: int = 0


def compute_atr20(prices: pd.DataFrame, *, window: int = 20) -> pd.DataFrame:
    frame = _normalize_prices(prices)
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "atr20"])

    frame = frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)
    previous_close = frame.groupby("asset_id")["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["atr20"] = (
        true_range.groupby(frame["asset_id"])
        .rolling(window=window, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    return frame[["trade_date", "asset_id", "atr20"]]


def apply_stock_protection_to_selection(
    selection: pd.DataFrame,
    prices: pd.DataFrame,
    funnel: pd.DataFrame,
    config: StockProtectionConfig,
) -> pd.DataFrame:
    selected = _normalize_selection(selection)
    if selected.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "asset_id",
                "strategy_family",
                "selection_style",
                "invested_weight",
                "protection_reason",
            ]
        )

    price_frame = _normalize_prices(prices)
    if "atr20" not in price_frame.columns:
        price_frame = price_frame.merge(
            compute_atr20(prices),
            on=["trade_date", "asset_id"],
            how="left",
        )
    price_by_key = {
        (row.trade_date, row.asset_id): row
        for row in price_frame.itertuples(index=False)
    }
    score_frame = _normalize_funnel(funnel)
    score_by_key = {
        (row.trade_date, row.asset_id): row
        for row in score_frame.itertuples(index=False)
    }

    state_by_asset: dict[str, dict[str, Any]] = {}
    score_history: dict[str, list[float]] = {}
    rank_history: dict[str, list[float]] = {}
    output_rows: list[dict[str, Any]] = []

    for trade_date, day in selected.groupby("trade_date", sort=True):
        emitted = False
        for row in day.itertuples(index=False):
            asset_id = str(row.asset_id)
            invested_weight = float(getattr(row, "invested_weight", 1.0) or 0.0)
            base_row = {
                "trade_date": trade_date,
                "asset_id": asset_id,
                "strategy_family": getattr(row, "strategy_family", config.variant_name),
                "selection_style": getattr(row, "selection_style", "growth_momentum"),
                "invested_weight": invested_weight,
                "protection_reason": "",
            }
            price = price_by_key.get((trade_date, asset_id))
            score = score_by_key.get((trade_date, asset_id))
            if price is None or pd.isna(price.close) or invested_weight <= 0.0:
                output_rows.append(base_row)
                emitted = True
                continue

            close = float(price.close)
            state = state_by_asset.get(asset_id)
            if state is None:
                state = {"entry_close": close, "highest_close": close}
            else:
                state["highest_close"] = max(float(state["highest_close"]), close)

            reason = _protection_reason(
                close=close,
                state=state,
                price=price,
                score=score,
                score_history=score_history.get(asset_id, []),
                rank_history=rank_history.get(asset_id, []),
                regime_state=getattr(row, "confirmed_regime_state", ""),
                config=config,
            )
            score_value = getattr(score, "mid_trend_funnel_score", pd.NA) if score is not None else pd.NA
            if pd.notna(score_value):
                score_history.setdefault(asset_id, []).append(float(score_value))
            rank_value = getattr(score, "score_rank", pd.NA) if score is not None else pd.NA
            if pd.notna(rank_value):
                rank_history.setdefault(asset_id, []).append(float(rank_value))

            if reason:
                state_by_asset.pop(asset_id, None)
                blocked = base_row.copy()
                blocked["asset_id"] = pd.NA
                blocked["protection_reason"] = reason
                output_rows.append(blocked)
            else:
                state_by_asset[asset_id] = state
                output_rows.append(base_row)
            emitted = True

        if not emitted:
            output_rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": pd.NA,
                    "strategy_family": config.variant_name,
                    "selection_style": "growth_momentum",
                    "invested_weight": 0.0,
                    "protection_reason": "empty_selection",
                }
            )

    return pd.DataFrame(output_rows)


def _protection_reason(
    *,
    close: float,
    state: dict[str, Any],
    price: Any,
    score: Any,
    score_history: list[float],
    rank_history: list[float],
    regime_state: str,
    config: StockProtectionConfig,
) -> str:
    if config.fixed_stop_loss is not None:
        entry = float(state["entry_close"])
        if entry > 0 and close <= entry * (1.0 - float(config.fixed_stop_loss)):
            return "fixed_stop_loss"

    atr_multiple = _atr_multiple_for_regime(config, regime_state)
    if atr_multiple is None:
        return ""

    atr = getattr(price, "atr20", pd.NA)
    if pd.isna(atr) or float(atr) <= 0:
        return ""
    trailing_stop = float(state["highest_close"]) - float(atr_multiple) * float(atr)
    if close > trailing_stop:
        return ""
    if _score_break_confirmed(score, score_history, rank_history, config):
        return "atr_score_confirmed"
    return ""


def _atr_multiple_for_regime(config: StockProtectionConfig, regime_state: str) -> float | None:
    if config.atr_multiple_by_regime is not None:
        value = config.atr_multiple_by_regime.get(str(regime_state))
        if value is not None:
            return float(value)
    return config.atr_multiple


def _score_break_confirmed(
    score: Any,
    score_history: list[float],
    rank_history: list[float],
    config: StockProtectionConfig,
) -> bool:
    rank = getattr(score, "score_rank", pd.NA) if score is not None else pd.NA
    if pd.notna(rank):
        rank_days = max(int(config.rank_break_days), 1)
        previous_needed = rank_days - 1
        previous_ranks = rank_history[-previous_needed:] if previous_needed else []
        recent_ranks = previous_ranks + [float(rank)]
        if len(recent_ranks) >= rank_days and all(
            value > float(config.score_break_rank) for value in recent_ranks
        ):
            return True

    current_score = getattr(score, "mid_trend_funnel_score", pd.NA) if score is not None else pd.NA
    if pd.isna(current_score):
        return False
    needed_previous = max(int(config.score_decline_days) - 1, 1)
    if len(score_history) < needed_previous:
        return False
    recent = score_history[-needed_previous:] + [float(current_score)]
    return all(right < left for left, right in zip(recent, recent[1:], strict=False))


def _normalize_selection(selection: pd.DataFrame) -> pd.DataFrame:
    frame = selection.copy()
    if frame.empty:
        return frame
    if "trade_date" not in frame.columns:
        frame["trade_date"] = pd.NA
    if "asset_id" not in frame.columns:
        frame["asset_id"] = pd.NA
    if "invested_weight" not in frame.columns:
        frame["invested_weight"] = 1.0
    if "strategy_family" not in frame.columns:
        frame["strategy_family"] = "protected_mid_trend"
    if "selection_style" not in frame.columns:
        frame["selection_style"] = "growth_momentum"
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed").dt.strftime(
        "%Y-%m-%d"
    )
    frame = frame.dropna(subset=["trade_date", "asset_id"])
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["invested_weight"] = pd.to_numeric(frame["invested_weight"], errors="coerce").fillna(0.0)
    return frame.sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def _normalize_prices(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.copy()
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "high", "low", "close"])
    for column in ["trade_date", "asset_id", "high", "low", "close"]:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed").dt.strftime(
        "%Y-%m-%d"
    )
    frame["asset_id"] = frame["asset_id"].astype(str)
    for column in ["high", "low", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "atr20" in frame.columns:
        frame["atr20"] = pd.to_numeric(frame["atr20"], errors="coerce")
    return frame.dropna(subset=["trade_date", "asset_id", "close"]).reset_index(drop=True)


def _normalize_funnel(funnel: pd.DataFrame) -> pd.DataFrame:
    frame = funnel.copy()
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "score_rank", "mid_trend_funnel_score"])
    for column in ["trade_date", "asset_id", "score_rank", "mid_trend_funnel_score"]:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed").dt.strftime(
        "%Y-%m-%d"
    )
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["score_rank"] = pd.to_numeric(frame["score_rank"], errors="coerce")
    frame["mid_trend_funnel_score"] = pd.to_numeric(frame["mid_trend_funnel_score"], errors="coerce")
    return frame.dropna(subset=["trade_date", "asset_id"]).reset_index(drop=True)
