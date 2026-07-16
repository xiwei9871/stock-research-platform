from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from stock_research.lhb_eligibility import LHB_ELIGIBILITY_CONTRACT_VERSION, PUMP_REJECT_THRESHOLD


LEGACY_LHB_BENCHMARK_SUMMARY_PATH = Path(
    "/Users/xiwei/stock_research/outputs/research/web_lhb_phase18c_runs/"
    "lhb_phase18c_web_top5_20260611T032244193018Z_49a58542/"
    "lhb_phase18c_summary_v1.csv"
)
LHB_SHORTLINE_V1_OUTPUT_ROOT = Path(
    "/Users/xiwei/stock_research/outputs/research/web_lhb_shortline_v1_runs"
)
LHB_SHORTLINE_DEFAULT_MARKET_REGIME_PROFILE = "first_risk80_gradient_2d90_3d80_4d70"
LHB_SHORTLINE_RISK_PROFILES: dict[str, dict[str, str]] = {
    "return_max": {
        "label": "收益优先",
        "market_regime_profile": "no_market_regime_control",
        "note": "不启用市场仓位控制，保留原始 LHB Shortline v1 收益优先路径。",
    },
    "balanced": {
        "label": "最佳平衡",
        "market_regime_profile": LHB_SHORTLINE_DEFAULT_MARKET_REGIME_PROFILE,
        "note": "昨天市场好满仓；第一次 risk_off 80%；连续弱势第2天90%、第3天80%、第4天及以后70%。",
    },
    "drawdown_control": {
        "label": "回撤优先",
        "market_regime_profile": "hybrid_first65_confirmed65",
        "note": "第一次 risk_off 65%；连续弱势确认后 risk_off 65%、weak 75%；昨天市场好满仓。",
    },
}


@dataclass(frozen=True)
class LHBShortlineV1Config:
    start_date: str
    end_date: str
    top_n: int
    rebalance_frequency: str = "daily"
    transaction_cost_bps: float = 0.0
    max_positions: int | None = None
    max_position_weight: float | None = None
    adjust_type: str = "hfq"
    risk_profile: str = "balanced"
    engine_version: str = "lhb_shortline_v1"

    @property
    def candidate_pool_n(self) -> int:
        return max(int(self.top_n), 10)

    @property
    def position_weight(self) -> float:
        if self.max_position_weight is not None:
            return float(self.max_position_weight)
        return min(1.0 / max(int(self.top_n), 1), 0.10)

    @property
    def account_max_positions(self) -> int:
        return int(self.max_positions or self.top_n)

    @property
    def round_trip_cost_return(self) -> float:
        return float(self.transaction_cost_bps) * 2.0 / 10000.0


@dataclass(frozen=True)
class LHBShortlineV1Result:
    summary: dict[str, Any]
    equity_curve: pd.DataFrame
    positions: pd.DataFrame
    trades: pd.DataFrame


@dataclass(frozen=True)
class LHBShortlineV1Frames:
    lhb_features: pd.DataFrame
    technical_features: pd.DataFrame
    auction_open: pd.DataFrame
    intraday_confirmation: pd.DataFrame
    daily_bars: pd.DataFrame
    minute_bars: pd.DataFrame
    coverage: dict[str, Any]


def _num(value: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(value, errors="coerce").fillna(default)


def _optional_num(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")
    return _num(frame[column], default)


def _annualized_sharpe_from_equity_curve(equity_curve: pd.DataFrame) -> float | None:
    if equity_curve.empty:
        return None
    if "daily_return" in equity_curve.columns:
        returns = pd.to_numeric(equity_curve["daily_return"], errors="coerce")
    elif "equity" in equity_curve.columns:
        returns = pd.to_numeric(equity_curve["equity"], errors="coerce").pct_change()
    else:
        return None
    returns = returns.dropna()
    if len(returns) < 2:
        return None
    std = float(returns.std(ddof=1))
    if std <= 0:
        return None
    return float((returns.mean() / std) * (252 ** 0.5))


def build_lhb_shortline_market_regime(daily_bars: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "signal_trade_date",
        "entry_trade_date",
        "asset_count",
        "avg_return",
        "median_return",
        "up_ratio",
        "down_3pct_ratio",
        "up_3pct_ratio",
        "market_regime",
        "position_scale",
        "max_total_exposure",
    ]
    if daily_bars.empty:
        return pd.DataFrame(columns=columns)

    bars = daily_bars.copy()
    for column in ["trade_date", "close", "preclose", "open"]:
        if column not in bars.columns:
            bars[column] = pd.NA
    bars["trade_date"] = pd.to_datetime(bars["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    close = pd.to_numeric(bars["close"], errors="coerce")
    preclose = pd.to_numeric(bars["preclose"], errors="coerce")
    open_price = pd.to_numeric(bars["open"], errors="coerce")
    denominator = preclose.where(preclose.gt(0), open_price)
    bars["_return"] = close / denominator - 1.0
    bars = bars[bars["trade_date"].notna() & bars["_return"].notna()].copy()
    if bars.empty:
        return pd.DataFrame(columns=columns)

    daily = (
        bars.groupby("trade_date", sort=True)
        .agg(
            asset_count=("_return", "size"),
            avg_return=("_return", "mean"),
            median_return=("_return", "median"),
            up_ratio=("_return", lambda values: float((values > 0).mean())),
            down_3pct_ratio=("_return", lambda values: float((values <= -0.03).mean())),
            up_3pct_ratio=("_return", lambda values: float((values >= 0.03).mean())),
        )
        .reset_index()
        .rename(columns={"trade_date": "signal_trade_date"})
    )
    trade_dates = daily["signal_trade_date"].tolist()
    next_dates = trade_dates[1:] + [None]
    daily["entry_trade_date"] = next_dates
    daily = daily[daily["entry_trade_date"].notna()].copy()
    regimes = daily.apply(_classify_lhb_shortline_market_regime, axis=1, result_type="expand")
    daily["market_regime"] = regimes[0]
    daily["position_scale"] = regimes[1]
    daily["max_total_exposure"] = regimes[2]
    return daily.reindex(columns=columns).reset_index(drop=True)


def _classify_lhb_shortline_market_regime(row: pd.Series) -> tuple[str, float, float]:
    up_ratio = float(row.get("up_ratio") or 0.0)
    down_3pct_ratio = float(row.get("down_3pct_ratio") or 0.0)
    avg_return = float(row.get("avg_return") or 0.0)
    if up_ratio < 0.30 or down_3pct_ratio > 0.20:
        return "risk_off", 0.0, 0.0
    if up_ratio < 0.40 and down_3pct_ratio > 0.12:
        return "weak", 0.4, 0.4
    if up_ratio < 0.50 or avg_return < -0.002:
        return "normal", 0.8, 0.8
    return "strong", 1.0, 1.0


def apply_lhb_shortline_consecutive_weak_control(
    market_regime: pd.DataFrame,
    *,
    min_weak_streak_days: int = 2,
    risk_off_scale: float = 0.6,
    weak_scale: float = 0.8,
    unconfirmed_risk_off_scale: float = 1.0,
    unconfirmed_weak_scale: float = 1.0,
    normal_scale: float = 1.0,
    strong_scale: float = 1.0,
) -> pd.DataFrame:
    if market_regime.empty:
        frame = market_regime.copy()
        for column in ["raw_market_regime", "weak_streak_days"]:
            if column not in frame.columns:
                frame[column] = pd.Series(dtype="object")
        return frame

    frame = market_regime.copy()
    for column, default in [("market_regime", "strong"), ("position_scale", 1.0), ("max_total_exposure", 1.0)]:
        if column not in frame.columns:
            frame[column] = default
    frame["entry_trade_date"] = pd.to_datetime(frame["entry_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame.sort_values("entry_trade_date", kind="stable").reset_index(drop=True)
    frame["raw_market_regime"] = frame["market_regime"].astype(str)

    weak_regime = frame["raw_market_regime"].isin({"weak", "risk_off"})
    streaks: list[int] = []
    current = 0
    for is_weak in weak_regime:
        current = current + 1 if bool(is_weak) else 0
        streaks.append(current)
    frame["weak_streak_days"] = streaks

    scale_by_regime = {
        "risk_off": float(risk_off_scale),
        "weak": float(weak_scale),
        "normal": float(normal_scale),
        "strong": float(strong_scale),
    }
    confirmed = frame["weak_streak_days"].ge(int(min_weak_streak_days)) & weak_regime
    frame["position_scale"] = float(strong_scale)
    frame.loc[~weak_regime & frame["raw_market_regime"].eq("normal"), "position_scale"] = float(normal_scale)
    frame.loc[weak_regime & frame["raw_market_regime"].eq("risk_off"), "position_scale"] = float(unconfirmed_risk_off_scale)
    frame.loc[weak_regime & frame["raw_market_regime"].eq("weak"), "position_scale"] = float(unconfirmed_weak_scale)
    for regime, scale in scale_by_regime.items():
        mask = confirmed & frame["raw_market_regime"].eq(regime)
        frame.loc[mask, "position_scale"] = scale
    frame["max_total_exposure"] = frame["position_scale"]
    return frame


def _normalize_lhb_shortline_risk_profile(value: Any) -> str:
    profile = str(value or "balanced").strip().lower()
    if profile not in LHB_SHORTLINE_RISK_PROFILES:
        return "balanced"
    return profile


def build_lhb_shortline_market_regime_control(daily_bars: pd.DataFrame, *, risk_profile: str) -> pd.DataFrame:
    profile = _normalize_lhb_shortline_risk_profile(risk_profile)
    if profile == "return_max":
        return pd.DataFrame()
    if profile == "drawdown_control":
        market_regime = build_lhb_shortline_market_regime(daily_bars)
        return apply_lhb_shortline_consecutive_weak_control(
            market_regime,
            min_weak_streak_days=2,
            risk_off_scale=0.65,
            weak_scale=0.75,
            unconfirmed_risk_off_scale=0.65,
            unconfirmed_weak_scale=1.0,
            normal_scale=1.0,
            strong_scale=1.0,
        )
    return build_lhb_shortline_default_market_regime_control(daily_bars)


def build_lhb_shortline_default_market_regime_control(daily_bars: pd.DataFrame) -> pd.DataFrame:
    frame = build_lhb_shortline_market_regime(daily_bars)
    if frame.empty:
        return frame
    frame = frame.sort_values("entry_trade_date", kind="stable").reset_index(drop=True)
    frame["raw_market_regime"] = frame["market_regime"].astype(str)
    weak_regime = frame["raw_market_regime"].isin({"weak", "risk_off"})
    streaks: list[int] = []
    current = 0
    for is_weak in weak_regime:
        current = current + 1 if bool(is_weak) else 0
        streaks.append(current)
    frame["weak_streak_days"] = streaks

    scales: list[float] = []
    for raw_regime, streak in zip(frame["raw_market_regime"], frame["weak_streak_days"], strict=False):
        if streak <= 0:
            scales.append(1.0)
        elif streak == 1:
            scales.append(0.80 if raw_regime == "risk_off" else 1.0)
        elif streak == 2:
            scales.append(0.90)
        elif streak == 3:
            scales.append(0.80)
        else:
            scales.append(0.70)
    frame["position_scale"] = scales
    frame["max_total_exposure"] = frame["position_scale"]
    return frame


def run_lhb_shortline_market_regime_account(
    *,
    lifecycle_trades: pd.DataFrame,
    market_regime: pd.DataFrame,
    max_positions: int,
    base_position_pct: float,
    daily_bars: pd.DataFrame | None = None,
    minute_bars: pd.DataFrame | None = None,
    end_date: str = "",
) -> dict[str, Any]:
    account_trades, account_curve = _build_lhb_shortline_market_regime_account_frames(
        lifecycle_trades=lifecycle_trades,
        market_regime=market_regime,
        max_positions=max_positions,
        base_position_pct=base_position_pct,
        daily_bars=daily_bars,
        minute_bars=minute_bars,
        end_date=end_date,
    )
    summary = _summarize_lhb_shortline_market_regime_account(
        account_trades=account_trades,
        account_curve=account_curve,
    )
    return {
        "summary": summary,
        "account_trades": account_trades,
        "account_curve": account_curve,
        "market_regime": market_regime,
    }


def _build_lhb_shortline_market_regime_account_frames(
    *,
    lifecycle_trades: pd.DataFrame,
    market_regime: pd.DataFrame,
    max_positions: int,
    base_position_pct: float,
    daily_bars: pd.DataFrame | None = None,
    minute_bars: pd.DataFrame | None = None,
    end_date: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trade_columns = [
        "account_trade_status",
        "trade_date",
        "ts_code",
        "top_n",
        "phase12a_rule_layer",
        "entry_trade_date",
        "entry_time",
        "entry_price",
        "exit_status",
        "exit_signal",
        "exit_reason",
        "exit_trade_date",
        "exit_time",
        "exit_price",
        "realized_return",
        "position_notional",
        "pnl",
        "skip_reason",
        "market_regime",
        "position_scale",
        "max_total_exposure",
    ]
    curve_columns = [
        "trade_date",
        "cash",
        "invested_notional",
        "equity",
        "drawdown",
        "open_position_count",
        "opened_count",
        "closed_count",
        "daily_realized_pnl",
        "market_regime",
        "position_scale",
        "max_total_exposure",
    ]
    if lifecycle_trades.empty:
        return pd.DataFrame(columns=trade_columns), pd.DataFrame(columns=curve_columns)

    trades = lifecycle_trades.copy()
    for column in [
        "account_trade_status",
        "fill_status",
        "trade_date",
        "ts_code",
        "top_n",
        "phase12a_rule_layer",
        "entry_trade_date",
        "entry_time",
        "entry_price",
        "exit_status",
        "exit_signal",
        "exit_reason",
        "exit_trade_date",
        "exit_time",
        "exit_price",
        "realized_return",
    ]:
        if column not in trades.columns:
            trades[column] = pd.NA
    trades["entry_trade_date"] = pd.to_datetime(trades["entry_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["exit_trade_date"] = pd.to_datetime(trades["exit_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["realized_return"] = pd.to_numeric(trades["realized_return"], errors="coerce")
    fill_status = trades["fill_status"].fillna(trades["account_trade_status"]).astype(str)
    candidates = trades[
        fill_status.eq("filled")
        & trades["entry_trade_date"].notna()
    ].copy()
    if end_date:
        candidates = candidates[candidates["entry_trade_date"].astype(str).le(str(end_date))].copy()
    candidates = candidates.sort_values(["entry_trade_date", "trade_date", "top_n", "ts_code"], kind="stable").reset_index(drop=True)

    regime_by_date = _lhb_shortline_regime_by_entry_date(market_regime)
    price_lookup, market_dates = _lhb_shortline_close_lookup(minute_bars=minute_bars, daily_bars=daily_bars)
    event_dates = set(candidates["entry_trade_date"].dropna()) | set(candidates["exit_trade_date"].dropna())
    if end_date:
        event_dates.add(str(end_date))
    start_event_date = min(event_dates) if event_dates else ""
    if market_dates and start_event_date:
        dates = [date for date in market_dates if start_event_date <= date <= (str(end_date) if end_date else max(event_dates))]
    else:
        dates = sorted(event_dates)
    cash = 1.0
    running_max = 1.0
    open_positions: dict[str, dict[str, Any]] = {}
    account_rows: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    trade_records: dict[int, dict[str, Any]] = {}
    by_entry = {date: group for date, group in candidates.groupby("entry_trade_date", sort=False)}

    for date in dates:
        opened_count = 0
        closed_count = 0
        daily_pnl = 0.0

        for ts_code, position in list(open_positions.items()):
            if not position.get("exit_trade_date") or str(position["exit_trade_date"]) != str(date):
                continue
            pnl = float(position["position_notional"]) * float(position.get("realized_return") or 0.0)
            proceeds = float(position["position_notional"]) + pnl
            cash += proceeds
            daily_pnl += pnl
            closed_count += 1
            record = trade_records[int(position["trade_idx"])]
            record["pnl"] = pnl
            open_positions.pop(ts_code, None)

        regime = regime_by_date.get(str(date), {"market_regime": "strong", "position_scale": 1.0, "max_total_exposure": 1.0})
        entries = by_entry.get(date)
        if entries is not None:
            for _, row in entries.iterrows():
                ts_code = str(row.get("ts_code") or "")
                base_record = _lhb_shortline_market_regime_trade_record(row, regime)
                if ts_code in open_positions:
                    account_rows.append({**base_record, "account_trade_status": "duplicate_position_skipped", "skip_reason": "duplicate_open_position"})
                    continue
                if len(open_positions) >= int(max_positions):
                    account_rows.append({**base_record, "account_trade_status": "max_positions_skipped", "skip_reason": "max_positions_reached"})
                    continue
                equity_before_entry = cash + sum(
                    _lhb_shortline_mark_to_market_value(pos, date, price_lookup)
                    for pos in open_positions.values()
                )
                invested = sum(
                    _lhb_shortline_mark_to_market_value(pos, date, price_lookup)
                    for pos in open_positions.values()
                )
                position_scale = float(regime["position_scale"])
                max_total_exposure = float(regime["max_total_exposure"])
                exposure_room = max(equity_before_entry * max_total_exposure - invested, 0.0)
                notional = min(equity_before_entry * float(base_position_pct) * position_scale, cash, exposure_room)
                if notional <= 0.0:
                    account_rows.append({**base_record, "account_trade_status": "market_regime_skipped", "skip_reason": "market_regime_risk_off"})
                    continue
                cash -= notional
                trade_idx = len(account_rows)
                record = {
                    **base_record,
                    "account_trade_status": "filled",
                    "position_notional": notional,
                    "pnl": pd.NA,
                    "skip_reason": "",
                }
                account_rows.append(record)
                trade_records[trade_idx] = record
                open_positions[ts_code] = {
                    "trade_idx": trade_idx,
                    "ts_code": ts_code,
                    "entry_price": _finite_or_none(row.get("entry_price")),
                    "exit_trade_date": (
                        str(row.get("exit_trade_date"))
                        if pd.notna(row.get("exit_trade_date")) and (not end_date or str(row.get("exit_trade_date")) <= str(end_date))
                        else ""
                    ),
                    "realized_return": _finite_or_none(row.get("realized_return")),
                    "position_notional": notional,
                }
                opened_count += 1

        invested = sum(
            _lhb_shortline_mark_to_market_value(pos, date, price_lookup)
            for pos in open_positions.values()
        )
        for position in open_positions.values():
            current_value = _lhb_shortline_mark_to_market_value(position, date, price_lookup)
            record = trade_records[int(position["trade_idx"])]
            record["pnl"] = current_value - float(position["position_notional"])
        equity = cash + invested
        running_max = max(running_max, equity)
        curve_rows.append(
            {
                "trade_date": date,
                "cash": cash,
                "invested_notional": invested,
                "equity": equity,
                "drawdown": equity / running_max - 1.0 if running_max else 0.0,
                "open_position_count": len(open_positions),
                "opened_count": opened_count,
                "closed_count": closed_count,
                "daily_realized_pnl": daily_pnl,
                **regime,
            }
        )

    return pd.DataFrame(account_rows).reindex(columns=trade_columns), pd.DataFrame(curve_rows).reindex(columns=curve_columns)


def _lhb_shortline_close_lookup(
    *,
    minute_bars: pd.DataFrame | None,
    daily_bars: pd.DataFrame | None,
) -> tuple[dict[tuple[str, str], float], list[str]]:
    minute_lookup, minute_dates = _lhb_shortline_price_close_lookup(minute_bars, prefer_last_trade_time=True)
    if minute_lookup:
        return minute_lookup, minute_dates
    return _lhb_shortline_price_close_lookup(daily_bars, prefer_last_trade_time=False)


def _lhb_shortline_price_close_lookup(
    bars: pd.DataFrame | None,
    *,
    prefer_last_trade_time: bool,
) -> tuple[dict[tuple[str, str], float], list[str]]:
    if bars is None or bars.empty or "trade_date" not in bars.columns:
        return {}, []
    frame = bars.copy()
    if "ts_code" not in frame.columns or "close" not in frame.columns:
        return {}, []
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["ts_code"].map(_canonical_ts_code)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "ts_code", "close"])
    if prefer_last_trade_time and "trade_time" in frame.columns:
        frame["_trade_time_sort"] = pd.to_datetime(frame["trade_time"], errors="coerce")
        frame = (
            frame.sort_values(["trade_date", "ts_code", "_trade_time_sort"], kind="stable")
            .drop_duplicates(["trade_date", "ts_code"], keep="last")
        )
    lookup = {
        (str(row.trade_date), str(row.ts_code)): float(row.close)
        for row in frame[["trade_date", "ts_code", "close"]].itertuples(index=False)
    }
    dates = sorted(frame["trade_date"].dropna().astype(str).unique().tolist())
    return lookup, dates


def _lhb_shortline_mark_to_market_value(
    position: dict[str, Any],
    trade_date: str,
    price_lookup: dict[tuple[str, str], float],
) -> float:
    notional = float(position.get("position_notional") or 0.0)
    entry_price = _finite_or_none(position.get("entry_price"))
    ts_code = str(position.get("ts_code") or "")
    close = price_lookup.get((str(trade_date), _canonical_ts_code(ts_code)))
    if entry_price is None or entry_price <= 0 or close is None or close <= 0:
        return notional
    return notional * float(close) / float(entry_price)


def _finite_or_none(value: Any) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    return float(parsed)


def _lhb_shortline_regime_by_entry_date(market_regime: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if market_regime.empty:
        return {}
    frame = market_regime.copy()
    for column, default in [("market_regime", "strong"), ("position_scale", 1.0), ("max_total_exposure", 1.0)]:
        if column not in frame.columns:
            frame[column] = default
    frame["entry_trade_date"] = pd.to_datetime(frame["entry_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result: dict[str, dict[str, Any]] = {}
    for _, row in frame.dropna(subset=["entry_trade_date"]).iterrows():
        result[str(row["entry_trade_date"])] = {
            "market_regime": str(row["market_regime"] or "strong"),
            "position_scale": float(row["position_scale"]),
            "max_total_exposure": float(row["max_total_exposure"]),
        }
    return result


def _lhb_shortline_market_regime_trade_record(row: pd.Series, regime: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_trade_status": "",
        "trade_date": row.get("trade_date", ""),
        "ts_code": row.get("ts_code", ""),
        "top_n": row.get("top_n", ""),
        "phase12a_rule_layer": row.get("phase12a_rule_layer", ""),
        "entry_trade_date": row.get("entry_trade_date", ""),
        "entry_time": row.get("entry_time", ""),
        "entry_price": row.get("entry_price", ""),
        "exit_status": row.get("exit_status", ""),
        "exit_signal": row.get("exit_signal", ""),
        "exit_reason": row.get("exit_reason", ""),
        "exit_trade_date": row.get("exit_trade_date", ""),
        "exit_time": row.get("exit_time", ""),
        "exit_price": row.get("exit_price", ""),
        "realized_return": row.get("realized_return", ""),
        "position_notional": pd.NA,
        "pnl": pd.NA,
        "skip_reason": "",
        **regime,
    }


def _summarize_lhb_shortline_market_regime_account(
    *,
    account_trades: pd.DataFrame,
    account_curve: pd.DataFrame,
) -> dict[str, Any]:
    if account_curve.empty:
        return {
            "initial_equity": 1.0,
            "final_equity": 1.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "filled_trade_count": 0,
            "closed_trade_count": 0,
        }
    filled = account_trades[account_trades["account_trade_status"].eq("filled")] if not account_trades.empty else pd.DataFrame()
    closed = filled[pd.to_numeric(filled.get("pnl", pd.Series(dtype="float64")), errors="coerce").notna()] if not filled.empty else filled
    returns = pd.to_numeric(closed.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
    final_equity = float(pd.to_numeric(pd.Series([account_curve.iloc[-1].get("equity")]), errors="coerce").fillna(1.0).iloc[0])
    max_drawdown = float(pd.to_numeric(account_curve.get("drawdown", pd.Series(dtype="float64")), errors="coerce").min())
    latest = account_curve.iloc[-1]
    previous = account_curve.iloc[-2] if len(account_curve) > 1 else None
    latest_equity = _finite_or_none(latest.get("equity"))
    previous_equity = _finite_or_none(previous.get("equity")) if previous is not None else None
    latest_day_return = (
        latest_equity / previous_equity - 1.0
        if latest_equity is not None and previous_equity not in (None, 0.0)
        else None
    )
    performance_effective_date = str(latest.get("trade_date") or "")
    latest_closed_trade_date = ""
    if not closed.empty and "exit_trade_date" in closed.columns:
        exit_dates = pd.to_datetime(closed["exit_trade_date"], errors="coerce").dropna()
        if not exit_dates.empty:
            latest_closed_trade_date = str(exit_dates.max().date())
    return {
        "initial_equity": 1.0,
        "final_equity": final_equity,
        "total_return": final_equity - 1.0,
        "max_drawdown": max_drawdown,
        "actual_end_date": str(latest.get("trade_date") or ""),
        "performance_effective_date": performance_effective_date,
        "latest_closed_trade_date": latest_closed_trade_date,
        "latest_day_return": latest_day_return,
        "latest_day_drawdown": _finite_or_none(latest.get("drawdown")),
        "open_position_count": int(_finite_or_none(latest.get("open_position_count")) or 0),
        "filled_trade_count": int(len(filled)),
        "closed_trade_count": int(len(closed)),
        "skipped_market_regime_count": int(account_trades["account_trade_status"].eq("market_regime_skipped").sum()) if not account_trades.empty else 0,
        "skipped_duplicate_count": int(account_trades["account_trade_status"].eq("duplicate_position_skipped").sum()) if not account_trades.empty else 0,
        "skipped_cash_count": int(account_trades["account_trade_status"].eq("cash_skipped").sum()) if not account_trades.empty else 0,
        "win_rate": float((returns > 0).mean()) if returns.notna().any() else None,
        "avg_trade_return": float(returns.mean()) if returns.notna().any() else None,
        "avg_position_notional": float(pd.to_numeric(closed.get("position_notional", pd.Series(dtype="float64")), errors="coerce").mean()) if not closed.empty else None,
        "sharpe_ratio": _annualized_sharpe_from_equity_curve(account_curve),
    }


def _extend_lhb_shortline_account_curve_to_end_date(
    *,
    account_curve: pd.DataFrame,
    daily_bars: pd.DataFrame,
    end_date: str,
) -> pd.DataFrame:
    if account_curve.empty or "trade_date" not in account_curve.columns or daily_bars.empty or "trade_date" not in daily_bars.columns:
        return account_curve

    curve = account_curve.copy()
    curve["trade_date"] = pd.to_datetime(curve["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    curve = curve.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    if curve.empty:
        return account_curve

    end_date_text = str(pd.to_datetime(end_date, errors="coerce").date())
    last_date = str(curve["trade_date"].iloc[-1])
    if last_date >= end_date_text:
        return curve

    available_dates = (
        pd.to_datetime(daily_bars["trade_date"], errors="coerce")
        .dropna()
        .dt.strftime("%Y-%m-%d")
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    missing_dates = [date for date in available_dates if last_date < date <= end_date_text]
    if not missing_dates:
        return curve

    append_rows: list[dict[str, Any]] = []
    last_row = curve.iloc[-1].to_dict()
    for trade_date in missing_dates:
        row = dict(last_row)
        row["trade_date"] = trade_date
        for column in ["opened_count", "closed_count", "daily_realized_pnl"]:
            if column in curve.columns:
                row[column] = 0
        if "invested_notional" in curve.columns:
            row["invested_notional"] = 0.0
        if "open_position_count" in curve.columns:
            row["open_position_count"] = 0
        append_rows.append(row)

    extended = pd.concat([curve, pd.DataFrame(append_rows)], ignore_index=True)
    if "equity" in extended.columns:
        equity = pd.to_numeric(extended["equity"], errors="coerce")
        running_max = equity.cummax()
        if "drawdown" in extended.columns:
            extended["drawdown"] = equity / running_max - 1.0
    return extended.reindex(columns=account_curve.columns)


def _canonical_ts_code(value: Any) -> str:
    code = str(value).upper().strip()
    parts = code.split(":")
    if len(parts) == 3 and parts[0] == "CN" and parts[1] in {"SH", "SZ", "BJ"}:
        return f"{parts[2]}.{parts[1]}"
    return code


def _asset_id_from_ts_code(ts_code: str) -> str:
    code = _canonical_ts_code(ts_code)
    if "." not in code:
        return code
    symbol, exchange = code.split(".", 1)
    return f"CN:{exchange}:{symbol}"


def _normalize_key_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized["trade_date"] = pd.to_datetime(
        normalized["trade_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    normalized["ts_code"] = normalized["ts_code"].map(_canonical_ts_code)
    return normalized


def _prefer_lhb_shortline_minute_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = _frame_from_rows(rows)
    columns = ["trade_date", "ts_code", "trade_time", "open", "high", "low", "close", "volume", "amount"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["ts_code"].map(_canonical_ts_code)
    frame["trade_time"] = pd.to_datetime(frame["trade_time"], errors="coerce")
    adjust = frame.get("adjust_type", pd.Series("", index=frame.index)).astype(str).str.lower()
    frame["_adjust_priority"] = adjust.map({"qfq": 0, "raw": 1}).fillna(9)
    frame = frame.sort_values(
        ["ts_code", "trade_date", "trade_time", "_adjust_priority"],
        kind="stable",
    )
    frame = frame.drop_duplicates(["ts_code", "trade_date", "trade_time"], keep="first")
    return frame.drop(columns=["_adjust_priority"], errors="ignore").reindex(columns=columns)


def build_lhb_shortline_v1_candidates(
    lhb_features: pd.DataFrame,
    technical_features: pd.DataFrame,
    *,
    candidate_pool_n: int,
) -> pd.DataFrame:
    if lhb_features.empty:
        return pd.DataFrame(
            columns=["trade_date", "ts_code", "rank", "score_total", "candidate_reason"]
        )

    lhb = _normalize_key_columns(lhb_features)
    if technical_features.empty:
        tech = pd.DataFrame(columns=["trade_date", "ts_code"])
    else:
        tech = _normalize_key_columns(technical_features)
    frame = lhb.merge(tech, on=["trade_date", "ts_code"], how="left")

    net_ratio = _optional_num(frame, "lhb_net_buy_ratio").clip(-1, 1)
    net_amount = (_optional_num(frame, "lhb_net_buy_amount") / 100_000_000.0).clip(-1, 3)
    inst_buy = (_optional_num(frame, "institution_net_buy") / 100_000_000.0).clip(-1, 2)
    repeat = _optional_num(frame, "repeat_on_list_count_3d").clip(0, 5)
    reversal = frame.get("lhb_after_reversal", False)
    if not isinstance(reversal, pd.Series):
        reversal = pd.Series(reversal, index=frame.index)
    reversal = reversal.fillna(False).astype(bool).astype(float)
    amount_confirm = _optional_num(frame, "amount_vs_20d", 1.0).clip(0, 3)
    pump_risk = _optional_num(frame, "lhb_one_day_pump_risk").clip(0, 1)
    drawdown = _optional_num(frame, "high_to_close_drawdown").clip(0, 1)

    frame["score_total"] = (
        50.0
        + net_ratio * 35.0
        + net_amount * 8.0
        + inst_buy * 6.0
        + repeat * 2.5
        + reversal * 6.0
        + amount_confirm * 2.0
        - pump_risk * 25.0
        - drawdown * 40.0
    )
    on_lhb = frame.get("on_lhb", False)
    if not isinstance(on_lhb, pd.Series):
        on_lhb = pd.Series(on_lhb, index=frame.index)
    if "backtest_entry_eligible" in frame.columns:
        eligible = frame["backtest_entry_eligible"].fillna(False).astype(bool)
    else:
        eligible = on_lhb.fillna(False).astype(bool) & pump_risk.lt(PUMP_REJECT_THRESHOLD)
    frame = frame[eligible].copy()
    frame["candidate_reason"] = "lhb_capital_plus_structure"
    frame = frame.sort_values(
        ["trade_date", "score_total", "ts_code"],
        ascending=[True, False, True],
        kind="stable",
    )
    frame["rank"] = frame.groupby("trade_date").cumcount() + 1
    frame = frame[frame["rank"].le(int(candidate_pool_n))]
    return frame.reset_index(drop=True)


def apply_lhb_shortline_v1_confirmations(
    candidates: pd.DataFrame,
    auction_open: pd.DataFrame,
    intraday_confirmation: pd.DataFrame,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()

    frame = candidates.copy()
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["ts_code"].astype(str).str.upper().str.strip()
    frame["entry_trade_date"] = (
        pd.to_datetime(frame["trade_date"]) + pd.Timedelta(days=1)
    ).dt.strftime("%Y-%m-%d")

    if auction_open.empty:
        auction = pd.DataFrame(columns=["entry_trade_date", "ts_code", "open_gap", "amount"])
    else:
        auction = _normalize_key_columns(auction_open)
        if "auction_phase" in auction.columns:
            auction = auction[auction["auction_phase"].eq("open_call")].copy()
        prev_close = _optional_num(auction, "prev_close").replace(0, pd.NA)
        auction["open_gap"] = _optional_num(auction, "open") / prev_close - 1.0
        auction = auction.rename(columns={"trade_date": "entry_trade_date"})

    if intraday_confirmation.empty:
        intra = pd.DataFrame(columns=["entry_trade_date", "ts_code"])
    else:
        intra = _normalize_key_columns(intraday_confirmation)
        intra = intra.rename(columns={"trade_date": "entry_trade_date"})

    frame = frame.merge(
        auction[["entry_trade_date", "ts_code", "open_gap", "amount"]],
        on=["entry_trade_date", "ts_code"],
        how="left",
    )
    intra_columns = [
        "entry_trade_date",
        "ts_code",
        "morning_return",
        "close_to_vwap",
        "intraday_return",
    ]
    for column in intra_columns:
        if column not in intra.columns:
            intra[column] = pd.NA
    frame = frame.merge(
        intra[intra_columns],
        on=["entry_trade_date", "ts_code"],
        how="left",
    )

    open_gap = _optional_num(frame, "open_gap")
    morning = _optional_num(frame, "morning_return")
    if "first_60m_return" in frame.columns:
        morning = _optional_num(frame, "first_60m_return").where(
            frame["first_60m_return"].notna(),
            morning,
        )
    close_to_vwap = _optional_num(frame, "close_to_vwap")
    intraday = _optional_num(frame, "intraday_return")
    penalty = morning.lt(-0.02) | close_to_vwap.lt(-0.015) | intraday.lt(-0.03)
    confirm = morning.ge(0.0) & close_to_vwap.ge(0.0) & intraday.ge(0.0)

    frame["confirmation_action"] = "watch_only"
    frame.loc[confirm, "confirmation_action"] = "confirm_follow"
    frame.loc[penalty, "confirmation_action"] = "reject_follow"
    frame["final_score"] = _optional_num(frame, "score_total") + open_gap.clip(
        -0.05, 0.08
    ) * 250.0
    frame.loc[confirm, "final_score"] += 12.0
    frame.loc[penalty, "final_score"] -= 60.0
    return frame.sort_values(
        ["trade_date", "final_score", "ts_code"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _empty_backtest_result(config: LHBShortlineV1Config) -> LHBShortlineV1Result:
    empty = pd.DataFrame()
    return LHBShortlineV1Result(
        summary={
            "engine_version": config.engine_version,
            "final_equity": 1.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "filled_trade_count": 0,
            "win_rate": 0.0,
        },
        equity_curve=empty,
        positions=empty,
        trades=empty,
    )


def _filter_rows_to_lhb_shortline_asof_cutoff(
    frame: pd.DataFrame,
    *,
    end_date: str,
    date_columns: tuple[str, ...],
    require_known_dates: bool = False,
) -> pd.DataFrame:
    if frame.empty or not end_date:
        return frame.copy()
    cutoff = pd.to_datetime(end_date, errors="coerce")
    if pd.isna(cutoff):
        return frame.copy()
    filtered = frame.copy()
    mask = pd.Series(True, index=filtered.index)
    for column in date_columns:
        if column not in filtered.columns:
            continue
        dates = pd.to_datetime(filtered[column], errors="coerce")
        if not require_known_dates and column == "exit_trade_date":
            future_exit = dates.gt(cutoff)
            if bool(future_exit.any()):
                for exit_column in ["exit_trade_date", "exit_time", "exit_price", "exit_status", "exit_signal", "exit_reason"]:
                    if exit_column in filtered.columns:
                        filtered.loc[future_exit, exit_column] = pd.NA
                if "realized_return" in filtered.columns:
                    filtered.loc[future_exit, "realized_return"] = pd.NA
            dates = pd.to_datetime(filtered[column], errors="coerce")
        column_mask = dates.le(cutoff)
        if require_known_dates:
            column_mask = column_mask & dates.notna()
        else:
            column_mask = column_mask | dates.isna()
        mask = mask & column_mask
    return filtered[mask].copy()


def run_lhb_shortline_v1_from_frames(
    *,
    config: LHBShortlineV1Config,
    scored_candidates: pd.DataFrame,
    daily_bars: pd.DataFrame,
) -> LHBShortlineV1Result:
    if scored_candidates.empty or daily_bars.empty:
        return _empty_backtest_result(config)

    bars = _normalize_key_columns(daily_bars)
    bars = bars.sort_values(["ts_code", "trade_date"], kind="stable")
    by_code = {
        code: group.reset_index(drop=True) for code, group in bars.groupby("ts_code", sort=False)
    }

    selected = _normalize_key_columns(scored_candidates)
    if "confirmation_action" in selected.columns:
        selected = selected[~selected["confirmation_action"].eq("reject_follow")].copy()
    selected = selected.sort_values(
        ["trade_date", "final_score", "ts_code"],
        ascending=[True, False, True],
        kind="stable",
    )
    selected = selected.groupby("trade_date", group_keys=False).head(int(config.top_n))

    trades: list[dict[str, Any]] = []
    for row in selected.to_dict("records"):
        signal_date = str(row["trade_date"])
        code = str(row["ts_code"])
        asset_bars = by_code.get(code)
        if asset_bars is None:
            continue
        future = asset_bars[asset_bars["trade_date"].gt(signal_date)].copy()
        if config.end_date:
            future = future[future["trade_date"].le(config.end_date)]
        future = future.head(3).reset_index(drop=True)
        if len(future) < 2:
            continue
        entry = float(future.iloc[0]["open"])
        if entry <= 0:
            continue
        exit_price = float(future.iloc[-1]["close"])
        raw_return = exit_price / entry - 1.0
        realized = raw_return - config.round_trip_cost_return
        trades.append(
            {
                "trade_date": signal_date,
                "ts_code": code,
                "entry_trade_date": future.iloc[0]["trade_date"],
                "exit_trade_date": future.iloc[-1]["trade_date"],
                "entry_price": entry,
                "exit_price": exit_price,
                "raw_return": raw_return,
                "realized_return": realized,
                "position_weight": config.position_weight,
            }
        )

    trade_frame = pd.DataFrame(trades)
    if trade_frame.empty:
        return _empty_backtest_result(config)

    trade_frame["portfolio_return"] = (
        trade_frame["realized_return"] * trade_frame["position_weight"]
    )
    curve = (
        trade_frame.groupby("exit_trade_date", as_index=False)
        .agg(daily_return=("portfolio_return", "sum"), closed_trade_count=("ts_code", "size"))
        .rename(columns={"exit_trade_date": "trade_date"})
        .sort_values("trade_date", kind="stable")
    )
    curve["equity"] = (1.0 + curve["daily_return"]).cumprod()
    curve["drawdown"] = curve["equity"] / curve["equity"].cummax() - 1.0
    summary = {
        "engine_version": config.engine_version,
        "final_equity": float(curve["equity"].iloc[-1]),
        "total_return": float(curve["equity"].iloc[-1] - 1.0),
        "max_drawdown": float(curve["drawdown"].min()),
        "filled_trade_count": int(len(trade_frame)),
        "win_rate": float((trade_frame["realized_return"] > 0).mean()),
        "sharpe_ratio": _annualized_sharpe_from_equity_curve(curve),
    }
    return LHBShortlineV1Result(
        summary=summary,
        equity_curve=curve,
        positions=trade_frame.copy(),
        trades=trade_frame,
    )


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_lhb_shortline_v1_artifacts(
    *,
    output_dir: Path,
    config: LHBShortlineV1Config,
    summary: dict[str, Any],
    candidates: pd.DataFrame,
    trades: pd.DataFrame,
    equity_curve: pd.DataFrame,
) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": str(output_dir / "lhb_shortline_v1_summary.json"),
        "candidates": str(output_dir / "lhb_shortline_v1_candidates.csv"),
        "trades": str(output_dir / "lhb_shortline_v1_trades.csv"),
        "equity_curve": str(output_dir / "lhb_shortline_v1_equity_curve.csv"),
    }
    Path(paths["summary"]).write_text(
        json.dumps(
            {"config": asdict(config), "summary": summary},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    candidates.to_csv(paths["candidates"], index=False)
    trades.to_csv(paths["trades"], index=False)
    equity_curve.to_csv(paths["equity_curve"], index=False)
    return paths


def compare_with_legacy_lhb_benchmark(
    current_summary: dict[str, Any],
    legacy_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "benchmark_name": "legacy_best_lhb_research",
        "legacy_total_return": legacy_summary.get("total_return"),
        "legacy_final_equity": legacy_summary.get("final_equity"),
        "legacy_max_drawdown": legacy_summary.get("max_drawdown"),
        "legacy_filled_trade_count": legacy_summary.get("filled_trade_count"),
        "legacy_actual_start_date": legacy_summary.get("actual_start_date"),
        "legacy_actual_end_date": legacy_summary.get("actual_end_date"),
        "total_return_delta": round(
            float(current_summary.get("total_return", 0.0))
            - float(legacy_summary.get("total_return", 0.0)),
            10,
        ),
        "final_equity_delta": round(
            float(current_summary.get("final_equity", 0.0))
            - float(legacy_summary.get("final_equity", 0.0)),
            10,
        ),
        "max_drawdown_delta": round(
            float(current_summary.get("max_drawdown", 0.0))
            - float(legacy_summary.get("max_drawdown", 0.0)),
            10,
        ),
        "trade_count_delta": int(current_summary.get("filled_trade_count", 0))
        - int(legacy_summary.get("filled_trade_count", 0)),
    }


def load_legacy_lhb_benchmark_summary(
    *,
    top_n: int,
    position_weight: float,
    transaction_cost_bps: float,
    path: Path = LEGACY_LHB_BENCHMARK_SUMMARY_PATH,
) -> dict[str, Any]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path, low_memory=False)
    if frame.empty:
        return {}
    filtered = frame.copy()
    if "strategy" in filtered.columns:
        filtered = filtered[filtered["strategy"].astype(str).eq("auction_enhanced_rerank")]
    if "top_n" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["top_n"], errors="coerce").eq(float(top_n))]
    if "position_pct" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(filtered["position_pct"], errors="coerce").round(6).eq(round(float(position_weight), 6))
        ]
    if "transaction_cost_bps" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(filtered["transaction_cost_bps"], errors="coerce").round(6).eq(
                round(float(transaction_cost_bps), 6)
            )
        ]
    if filtered.empty:
        return {}
    row = filtered.iloc[0].to_dict()
    row["source_path"] = str(path)
    return row


def _new_lhb_shortline_v1_output_dir(top_n: int) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return LHB_SHORTLINE_V1_OUTPUT_ROOT / f"lhb_shortline_v1_top{top_n}_{timestamp}_{uuid4().hex[:8]}"


def _frame_from_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if "trade_date" in frame.columns:
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime(
            "%Y-%m-%d"
        )
    if "ts_code" in frame.columns:
        frame["ts_code"] = frame["ts_code"].map(_canonical_ts_code)
    return frame


def _minute_asset_ids_for_lhb_shortline_v1(lhb_features: pd.DataFrame, top_values: list[int]) -> list[str]:
    if lhb_features.empty:
        return []
    frame = _normalize_key_columns(lhb_features)
    for column in [
        "lhb_net_buy_amount",
        "lhb_net_buy_ratio",
        "institution_net_buy",
        "top_seat_concentration",
        "repeat_on_list_count_3d",
        "lhb_one_day_pump_risk",
    ]:
        frame[column] = pd.to_numeric(frame.get(column, pd.Series(index=frame.index)), errors="coerce")
    for column in ["lhb_after_limit_up", "lhb_after_break_limit"]:
        if column not in frame.columns:
            frame[column] = pd.Series(False, index=frame.index)
        frame[column] = frame[column].fillna(False).astype(bool)
    mask = (
        frame["lhb_net_buy_amount"].fillna(0.0).gt(0)
        & frame["lhb_net_buy_ratio"].fillna(0.0).gt(0)
        & frame["institution_net_buy"].fillna(0.0).ge(0)
        & frame["lhb_one_day_pump_risk"].fillna(0.0).lt(PUMP_REJECT_THRESHOLD)
    )
    frame = frame[mask].copy()
    if frame.empty:
        return []
    amount_score = (
        frame["lhb_net_buy_amount"].clip(lower=0.0).rank(pct=True, method="average") * 100.0
    ).fillna(0.0)
    frame["selection_score"] = (
        frame["lhb_net_buy_ratio"].fillna(0.0) * 1000.0
        + amount_score
        + frame["institution_net_buy"].fillna(0.0).gt(0).astype(float) * 15.0
        + frame["lhb_after_limit_up"].astype(float) * 12.0
        + frame["repeat_on_list_count_3d"].fillna(0.0).clip(upper=3.0) * 3.0
        - frame["top_seat_concentration"].fillna(0.0) * 20.0
        - frame["lhb_one_day_pump_risk"].fillna(0.0) * 20.0
        - frame["lhb_after_break_limit"].astype(float) * 18.0
    )
    per_day_n = max(top_values) if top_values else 20
    selected = (
        frame.sort_values(["trade_date", "selection_score", "ts_code"], ascending=[True, False, True])
        .groupby("trade_date", group_keys=False)
        .head(per_day_n)
    )
    return sorted({_asset_id_from_ts_code(code) for code in selected["ts_code"].dropna().astype(str)})


def load_lhb_shortline_v1_frames_from_db(
    config: LHBShortlineV1Config,
    *,
    service: str | None = None,
) -> LHBShortlineV1Frames:
    from stock_research.config import SETTINGS
    from stock_research.db import connect, fetch_all

    db_service = service or SETTINGS.research_service
    with connect(db_service) as conn:
        lhb_rows = fetch_all(
            conn,
            """
            WITH same_day_top AS (
                SELECT
                    trade_date,
                    ts_code,
                    max(NULLIF(name, '')) AS stock_name,
                    max(pct_change) AS pct_chg
                FROM market.lhb_top_list_daily
                WHERE trade_date BETWEEN %s::date AND %s::date
                GROUP BY trade_date, ts_code
            )
            SELECT
                f.trade_date::text AS trade_date,
                f.ts_code,
                t.stock_name,
                CASE WHEN t.stock_name IS NULL THEN 'unavailable' ELSE 'lhb_same_day_name' END
                    AS stock_name_source,
                t.pct_chg,
                a.name AS current_name,
                a.list_date::text AS list_date,
                s.is_st AS stored_is_st,
                CASE
                    WHEN s.source LIKE '%%status_quality=same_day_lhb_name' THEN 'trusted'
                    WHEN s.source LIKE '%%status_quality=daily_bar' THEN 'trusted'
                    ELSE 'unverified'
                END AS stored_status_quality,
                tech.amount_vs_20d,
                tech.high_to_close_drawdown,
                f.on_lhb,
                f.lhb_reason,
                f.lhb_net_buy_amount,
                f.lhb_net_buy_ratio,
                f.institution_net_buy,
                f.top_seat_concentration,
                f.repeat_on_list_count_3d,
                f.repeat_on_list_count_5d,
                f.lhb_after_limit_up,
                f.lhb_after_break_limit,
                f.lhb_after_reversal,
                f.lhb_one_day_pump_risk
            FROM factor.lhb_event_features_daily f
            LEFT JOIN same_day_top t
              ON t.trade_date = f.trade_date
             AND t.ts_code = f.ts_code
            LEFT JOIN core.asset_master a
              ON a.ts_code = f.ts_code
            LEFT JOIN core.asset_status_daily s
              ON s.trade_date = f.trade_date
             AND s.asset_id = a.asset_id
            LEFT JOIN factor.stock_technical_features_daily tech
              ON tech.trade_date = f.trade_date
             AND tech.asset_id = a.asset_id
             AND tech.adjust_type = %s
            WHERE f.trade_date BETWEEN %s::date AND %s::date
            ORDER BY f.trade_date, f.ts_code
            """,
            [config.start_date, config.end_date, config.adjust_type, config.start_date, config.end_date],
        )
        technical_rows = fetch_all(
            conn,
            """
            SELECT
                trade_date::text AS trade_date,
                ts_code,
                amount_vs_20d,
                high_to_close_drawdown
            FROM factor.stock_technical_features_daily
            WHERE trade_date BETWEEN %s::date AND %s::date
              AND adjust_type = %s
            ORDER BY trade_date, ts_code
            """,
            [config.start_date, config.end_date, config.adjust_type],
        )
        daily_rows = fetch_all(
            conn,
            """
            SELECT
                b.trade_date::text AS trade_date,
                COALESCE(a.ts_code, b.asset_id) AS ts_code,
                b.open,
                b.low,
                b.close,
                b.preclose,
                b.pct_chg,
                b.is_st AS stored_is_st,
                CASE WHEN b.is_st THEN 'trusted' ELSE 'unverified' END AS stored_status_quality
            FROM market_daily_bar b
            LEFT JOIN core.asset_master a
              ON a.asset_id = b.asset_id
            WHERE b.trade_date BETWEEN %s::date AND (%s::date + INTERVAL '7 days')
              AND b.adjust_type = %s
              AND COALESCE(b.trade_status, '') <> '停牌'
              AND COALESCE(b.is_st, false) = false
            ORDER BY b.asset_id, b.trade_date
            """,
            [config.start_date, config.end_date, config.adjust_type],
        )
        auction_rows = fetch_all(
            conn,
            """
            SELECT
                a.trade_date::text AS trade_date,
                a.ts_code,
                a.auction_phase,
                a.open,
                a.close,
                d.preclose AS prev_close,
                a.amount
            FROM market.stock_auction_bar a
            LEFT JOIN market_daily_bar d
              ON d.asset_id = a.ts_code
             AND d.trade_date = a.trade_date
             AND d.adjust_type = %s
            WHERE a.trade_date BETWEEN %s::date AND (%s::date + INTERVAL '7 days')
            ORDER BY a.trade_date, a.ts_code
            """,
            [config.adjust_type, config.start_date, config.end_date],
        )
        intraday_rows = fetch_all(
            conn,
            """
            SELECT
                trade_date::text AS trade_date,
                asset_id AS ts_code,
                MAX(feature_value) FILTER (WHERE feature_name = 'morning_return')
                    AS morning_return,
                MAX(feature_value) FILTER (WHERE feature_name = 'close_to_vwap')
                    AS close_to_vwap,
                MAX(feature_value) FILTER (WHERE feature_name = 'intraday_return')
                    AS intraday_return
            FROM factor.stock_intraday_features_daily
            WHERE trade_date BETWEEN %s::date AND (%s::date + INTERVAL '7 days')
              AND adjust_type = %s
              AND feature_name IN ('morning_return', 'close_to_vwap', 'intraday_return')
            GROUP BY trade_date, asset_id
            ORDER BY trade_date, asset_id
            """,
            [config.start_date, config.end_date, config.adjust_type],
        )
        minute_asset_ids = _minute_asset_ids_for_lhb_shortline_v1(
            _frame_from_rows(lhb_rows),
            _lhb_shortline_v1_top_values(config.top_n),
        )
        minute_rows = fetch_all(
            conn,
            """
            SELECT
                m.trade_date::text AS trade_date,
                m.asset_id AS ts_code,
                m.trade_time::text AS trade_time,
                m.open,
                m.high,
                m.low,
                m.close,
                m.volume,
                m.amount,
                m.adjust_type
            FROM market.stock_minute_bar m
            WHERE m.trade_date BETWEEN (%s::date - INTERVAL '7 days') AND (%s::date + INTERVAL '7 days')
              AND m.adjust_type IN ('qfq', 'raw')
              AND m.freq = '5min'
              AND m.source = 'baostock'
              AND m.asset_id = ANY(%s)
            ORDER BY m.asset_id, m.trade_time, m.adjust_type
            """,
            [config.start_date, config.end_date, minute_asset_ids],
        ) if minute_asset_ids else []
        minute_frame = _prefer_lhb_shortline_minute_rows(minute_rows)

    frames = LHBShortlineV1Frames(
        lhb_features=_frame_from_rows(lhb_rows),
        technical_features=_frame_from_rows(technical_rows),
        auction_open=_frame_from_rows(auction_rows),
        intraday_confirmation=_frame_from_rows(intraday_rows),
        daily_bars=_frame_from_rows(daily_rows),
        minute_bars=minute_frame,
        coverage={
            "source": "db_base_tables",
            "service": db_service,
            "lhb_feature_rows": len(lhb_rows),
            "technical_feature_rows": len(technical_rows),
            "auction_rows": len(auction_rows),
            "intraday_feature_rows": len(intraday_rows),
            "daily_bar_rows": len(daily_rows),
            "minute_bar_rows": len(minute_rows),
            "minute_bar_effective_rows": len(minute_frame),
            "minute_asset_count": len(minute_asset_ids),
        },
    )
    return frames


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.to_dict("records")


def _lhb_shortline_v1_top_values(top_n: int) -> list[int]:
    return [max(int(top_n), 10)]


def _lhb_safe_top5_summary_metadata(phase18c_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_version": "lhb_v1_stable_safe_top5",
        "selection_policy": "phase18c_top5_then_eligibility_no_refill",
        "market_regime_policy": "disabled_for_stable_strategy",
        "cash_slot_count": int(phase18c_summary.get("cash_slot_count") or 0),
    }


def _select_lhb_stable_account(
    *,
    phase18c_summary: dict[str, Any],
    phase18c_account_trades: pd.DataFrame,
    phase18c_account_curve: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "summary": phase18c_summary.copy(),
        "account_trades": phase18c_account_trades.copy(),
        "account_curve": phase18c_account_curve.copy(),
    }


def _filter_lhb_shortline_v1_lifecycle_minute_window(
    *,
    selected: pd.DataFrame,
    minute_bars: pd.DataFrame,
    holding_trade_days: int = 5,
) -> pd.DataFrame:
    if selected.empty or minute_bars.empty:
        return minute_bars.copy()
    signals = _normalize_key_columns(selected)
    signals["_signal_date_dt"] = pd.to_datetime(signals["trade_date"], errors="coerce")
    signals = signals.dropna(subset=["_signal_date_dt", "ts_code"])
    if signals.empty:
        return minute_bars.iloc[0:0].copy()

    bars = _normalize_key_columns(minute_bars)
    bars["_trade_date_dt"] = pd.to_datetime(bars["trade_date"], errors="coerce")
    bars = bars.dropna(subset=["_trade_date_dt", "ts_code"])
    if bars.empty:
        return bars.drop(columns=["_trade_date_dt"], errors="ignore")

    market_dates = sorted(bars["_trade_date_dt"].dropna().unique())
    max_window_dates = max(int(holding_trade_days), 1) + 1
    window_rows: list[dict[str, Any]] = []
    for row in signals[["ts_code", "_signal_date_dt"]].drop_duplicates().to_dict("records"):
        signal_date = row["_signal_date_dt"]
        dates = [date for date in market_dates if date > signal_date][:max_window_dates]
        for trade_date in dates:
            window_rows.append(
                {
                    "ts_code": row["ts_code"],
                    "_trade_date_dt": trade_date,
                }
            )
    if not window_rows:
        return bars.iloc[0:0].drop(columns=["_trade_date_dt"], errors="ignore")
    windows = pd.DataFrame(window_rows)
    filtered = bars.merge(windows, on=["ts_code", "_trade_date_dt"], how="inner")
    return (
        filtered.drop(columns=["_trade_date_dt", "_signal_date_dt"], errors="ignore")
        .drop_duplicates()
        .sort_values(["ts_code", "trade_date", "trade_time"], kind="stable")
        .reset_index(drop=True)
    )


def _attach_lhb_shortline_v1_auction_score(
    lifecycle_trades: pd.DataFrame,
    auction_open: pd.DataFrame,
    *,
    daily_bars: pd.DataFrame | None = None,
) -> pd.DataFrame:
    trades = lifecycle_trades.copy().reset_index(names="original_order")
    if trades.empty:
        trades["auction_enhanced_score"] = pd.Series(dtype="float64")
        return trades
    for column in ["trade_date", "ts_code", "entry_trade_date", "phase12a_rule_layer"]:
        if column not in trades.columns:
            trades[column] = pd.NA
    trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["entry_trade_date"] = pd.to_datetime(
        trades["entry_trade_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    trades["ts_code"] = trades["ts_code"].map(_canonical_ts_code)

    auctions = _normalize_key_columns(auction_open) if not auction_open.empty else pd.DataFrame()
    if auctions.empty:
        auctions = pd.DataFrame(columns=["trade_date", "ts_code", "open", "close", "amount"])
    for column in ["open", "close", "amount"]:
        if column not in auctions.columns:
            auctions[column] = pd.NA
        auctions[column] = pd.to_numeric(auctions[column], errors="coerce")
    signal_source = auctions
    if "auction_phase" in signal_source.columns:
        signal_source = signal_source[signal_source["auction_phase"].eq("close_call")].copy()
    entry_source = auctions
    if "auction_phase" in entry_source.columns:
        entry_source = entry_source[entry_source["auction_phase"].eq("open_call")].copy()

    signal = signal_source.rename(
        columns={
            "open": "signal_close_open",
            "close": "signal_close_close",
            "amount": "signal_close_amount",
        }
    )[["trade_date", "ts_code", "signal_close_open", "signal_close_close", "signal_close_amount"]]
    entry = entry_source.rename(
        columns={
            "trade_date": "entry_trade_date",
            "open": "entry_open_open",
            "close": "entry_open_close",
            "amount": "entry_open_amount",
        }
    )[["entry_trade_date", "ts_code", "entry_open_open", "entry_open_close", "entry_open_amount"]]
    trades = trades.merge(signal, on=["trade_date", "ts_code"], how="left")
    trades = trades.merge(entry, on=["entry_trade_date", "ts_code"], how="left")
    daily_fallback = _lhb_shortline_daily_auction_score_fallback(trades, daily_bars)
    if not daily_fallback.empty:
        trades = trades.merge(
            daily_fallback,
            on=["trade_date", "entry_trade_date", "ts_code"],
            how="left",
            suffixes=("", "_daily_fallback"),
        )
        for column in [
            "signal_close_open",
            "signal_close_close",
            "signal_close_amount",
            "entry_open_open",
            "entry_open_close",
            "entry_open_amount",
        ]:
            fallback_column = f"{column}_daily_fallback"
            if fallback_column in trades.columns:
                trades[column] = trades[column].combine_first(trades[fallback_column])
        trades = trades.drop(
            columns=[column for column in trades.columns if column.endswith("_daily_fallback")],
            errors="ignore",
        )
    trades["signal_close_auction_return"] = (
        trades["signal_close_close"] / trades["signal_close_open"] - 1.0
    )
    trades["entry_open_auction_return"] = trades["entry_open_close"] / trades["entry_open_open"] - 1.0
    trades["entry_open_vs_signal_close"] = trades["entry_open_open"] / trades["signal_close_close"] - 1.0

    layer_score = trades["phase12a_rule_layer"].map(
        {
            "follow_pool_core": 100.0,
            "follow_pool_low_drawdown": 80.0,
            "follow_pool_high_confidence": 70.0,
            "pending_intraday": 20.0,
            "watch_pool": 10.0,
            "chase_control": -20.0,
            "retreat_hard": -100.0,
        }
    ).fillna(0.0)
    gap = pd.to_numeric(trades["entry_open_vs_signal_close"], errors="coerce").fillna(0.0)
    signal_return = pd.to_numeric(
        trades["signal_close_auction_return"], errors="coerce"
    ).fillna(0.0)
    trades["auction_enhanced_score"] = (
        layer_score
        + gap.gt(0.02).astype(float) * 10.0
        + gap.gt(0.04).astype(float) * 15.0
        + gap.gt(0.06).astype(float) * 25.0
        - gap.lt(-0.02).astype(float) * 15.0
        + signal_return.gt(0.02).astype(float) * 10.0
        - signal_return.lt(-0.005).astype(float) * 10.0
    )
    return trades


def _lhb_shortline_daily_auction_score_fallback(
    trades: pd.DataFrame,
    daily_bars: pd.DataFrame | None,
) -> pd.DataFrame:
    columns = [
        "trade_date",
        "entry_trade_date",
        "ts_code",
        "signal_close_open",
        "signal_close_close",
        "signal_close_amount",
        "entry_open_open",
        "entry_open_close",
        "entry_open_amount",
    ]
    if trades.empty or daily_bars is None or daily_bars.empty:
        return pd.DataFrame(columns=columns)
    daily = _normalize_key_columns(daily_bars)
    for column in ["open", "close", "amount"]:
        if column not in daily.columns:
            daily[column] = pd.NA
        daily[column] = pd.to_numeric(daily[column], errors="coerce")
    signal = daily.rename(
        columns={
            "close": "signal_close_close",
            "amount": "signal_close_amount",
        }
    )[["trade_date", "ts_code", "signal_close_close", "signal_close_amount"]]
    signal["signal_close_open"] = signal["signal_close_close"]
    entry = daily.rename(
        columns={
            "trade_date": "entry_trade_date",
            "open": "entry_open_open",
            "amount": "entry_open_amount",
        }
    )[["entry_trade_date", "ts_code", "entry_open_open", "entry_open_amount"]]
    entry["entry_open_close"] = entry["entry_open_open"]
    keys = trades[["trade_date", "entry_trade_date", "ts_code"]].drop_duplicates().copy()
    fallback = keys.merge(signal, on=["trade_date", "ts_code"], how="left")
    fallback = fallback.merge(entry, on=["entry_trade_date", "ts_code"], how="left")
    return fallback.reindex(columns=columns)


LHB_ELIGIBILITY_DECISION_COLUMNS = [
    "eligibility_status",
    "top5_eligible",
    "backtest_entry_eligible",
    "buy_signal_status",
    "eligibility_reason_codes",
    "eligibility_reason_texts",
    "eligibility_warning_codes",
    "price_limit_regime",
    "near_limit_down_threshold",
    "data_quality_status",
    "eligibility_contract_version",
]


def _assert_lhb_contract_versions(frame: pd.DataFrame, *, stage: str) -> None:
    required = {"backtest_entry_eligible", "eligibility_contract_version"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(
            f"LHB eligibility parity violation at {stage}: missing columns {', '.join(missing)}"
        )
    versions = frame["eligibility_contract_version"].fillna("").astype(str)
    invalid = ~versions.eq(LHB_ELIGIBILITY_CONTRACT_VERSION)
    if invalid.any():
        raise ValueError(
            f"LHB eligibility parity violation at {stage}: invalid contract version rows={int(invalid.sum())}"
        )


def _filter_lhb_entry_eligible_contract_rows(frame: pd.DataFrame, *, stage: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    _assert_lhb_contract_versions(frame, stage=stage)
    eligible = frame["backtest_entry_eligible"].fillna(False).astype(bool)
    return frame[eligible].copy().reset_index(drop=True)


def _assert_lhb_entry_eligibility_contract(frame: pd.DataFrame, *, stage: str) -> None:
    if frame.empty:
        return
    _assert_lhb_contract_versions(frame, stage=stage)
    invalid = ~frame["backtest_entry_eligible"].fillna(False).astype(bool)
    if invalid.any():
        raise ValueError(
            f"LHB eligibility parity violation at {stage}: ineligible entry rows={int(invalid.sum())}"
        )


def _attach_lhb_contract_decisions(
    frame: pd.DataFrame,
    *,
    decisions: pd.DataFrame,
    stage: str,
) -> pd.DataFrame:
    if frame.empty:
        result = frame.copy()
        for column in LHB_ELIGIBILITY_DECISION_COLUMNS:
            if column not in result.columns:
                result[column] = pd.NA
        return result
    decision_columns = [column for column in LHB_ELIGIBILITY_DECISION_COLUMNS if column in decisions.columns]
    required = {"trade_date", "ts_code", "backtest_entry_eligible", "eligibility_contract_version"}
    if not required.issubset(decisions.columns):
        raise ValueError(f"LHB eligibility parity violation at {stage}: upstream decision fields missing")
    source = decisions[["trade_date", "ts_code", *decision_columns]].copy()
    source["trade_date"] = pd.to_datetime(source["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    source["ts_code"] = source["ts_code"].map(_canonical_ts_code)
    source = source.drop_duplicates(["trade_date", "ts_code"], keep="last")

    result = frame.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result["ts_code"] = result["ts_code"].map(_canonical_ts_code)
    comparison = result[["trade_date", "ts_code"]].merge(
        source,
        on=["trade_date", "ts_code"],
        how="left",
        validate="many_to_one",
    )
    if comparison["eligibility_contract_version"].isna().any():
        raise ValueError(f"LHB eligibility parity violation at {stage}: decision key missing")
    for column in decision_columns:
        if column not in result.columns:
            continue
        existing = result[column]
        upstream = comparison[column]
        both = existing.notna() & upstream.notna()
        mismatch = both & existing.astype(str).ne(upstream.astype(str))
        if mismatch.any():
            raise ValueError(
                f"LHB eligibility parity violation at {stage}: contradictory {column} rows={int(mismatch.sum())}"
            )
    result = result.drop(columns=decision_columns, errors="ignore")
    return result.merge(
        source,
        on=["trade_date", "ts_code"],
        how="left",
        validate="many_to_one",
    )


def _build_lhb_eligibility_parity_audit(
    *,
    decisions: pd.DataFrame,
    stages: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    base = decisions[["trade_date", "ts_code", "eligibility_status", "eligibility_contract_version"]].copy()
    base["trade_date"] = pd.to_datetime(base["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    base["ts_code"] = base["ts_code"].map(_canonical_ts_code)
    base = base.drop_duplicates(["trade_date", "ts_code"], keep="last").rename(
        columns={
            "eligibility_status": "source_eligibility_status",
            "eligibility_contract_version": "source_contract_version",
        }
    )
    parity = pd.Series(True, index=base.index)
    for stage, frame in stages.items():
        status_column = f"{stage}_eligibility_status"
        version_column = f"{stage}_contract_version"
        if frame.empty or not {"trade_date", "ts_code", "eligibility_status", "eligibility_contract_version"}.issubset(frame.columns):
            base[status_column] = pd.NA
            base[version_column] = pd.NA
            continue
        observed = frame[["trade_date", "ts_code", "eligibility_status", "eligibility_contract_version"]].copy()
        observed["trade_date"] = pd.to_datetime(observed["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        observed["ts_code"] = observed["ts_code"].map(_canonical_ts_code)
        observed = observed.drop_duplicates(["trade_date", "ts_code"], keep="last").rename(
            columns={"eligibility_status": status_column, "eligibility_contract_version": version_column}
        )
        base = base.merge(observed, on=["trade_date", "ts_code"], how="left", validate="one_to_one")
        observed = base[status_column].notna() | base[version_column].notna()
        stage_match = ~observed | (
            base[status_column].eq(base["source_eligibility_status"])
            & base[version_column].eq(base["source_contract_version"])
        )
        parity = stage_match & parity.reset_index(drop=True)
    base["eligibility_contract_version"] = base["source_contract_version"]
    base["parity_status"] = parity.map({True: "match", False: "mismatch"})
    return base


def _build_lhb_review_candidates(
    *,
    scored_candidates: pd.DataFrame,
    risk_watch_candidates: pd.DataFrame,
    top_n: int,
) -> pd.DataFrame:
    del risk_watch_candidates
    scored = scored_candidates.copy()
    if "top_n" in scored.columns:
        requested = pd.to_numeric(scored["top_n"], errors="coerce").eq(int(top_n))
        if requested.any():
            scored = scored[requested].copy()
    if not scored.empty and {"trade_date", "ts_code"}.issubset(scored.columns):
        scored = scored.sort_values(
            ["trade_date", "auction_enhanced_score", "ts_code"],
            ascending=[True, False, True],
            kind="stable",
            na_position="last",
        ).drop_duplicates(["trade_date", "ts_code"], keep="first")
    if scored.empty:
        return scored.reset_index(drop=True)
    if "selection_rank" not in scored.columns:
        rank_source = next((column for column in ("source_rank", "rank") if column in scored.columns), None)
        if rank_source is not None:
            scored["selection_rank"] = pd.to_numeric(scored[rank_source], errors="coerce")
        elif "trade_date" in scored.columns:
            scored["selection_rank"] = scored.groupby("trade_date", dropna=False).cumcount() + 1
        else:
            scored["selection_rank"] = range(1, len(scored) + 1)
    rank_column = "phase18c_selection_rank" if "phase18c_selection_rank" in scored.columns else "selection_rank"
    final_rank = pd.to_numeric(scored[rank_column], errors="coerce")
    if "backtest_entry_eligible" in scored.columns:
        eligible = scored["backtest_entry_eligible"].fillna(False).astype(bool)
    else:
        eligible = scored.get("eligibility_status", pd.Series("eligible", index=scored.index)).eq("eligible")
    if "buy_signal_status" in scored.columns:
        eligible &= scored["buy_signal_status"].eq("tradable")
    review = scored[eligible & final_rank.le(int(top_n))].copy()
    if rank_column == "phase18c_selection_rank":
        review["pool_selection_rank"] = pd.to_numeric(review["selection_rank"], errors="coerce")
        review["selection_rank"] = pd.to_numeric(
            review["phase18c_selection_rank"], errors="coerce"
        )
    review = review.sort_values(["trade_date", rank_column, "ts_code"], kind="stable")
    if "ts_code" in review.columns:
        review["asset_id"] = review["ts_code"]
    return review.reset_index(drop=True)


def run_lhb_shortline_v1_lifecycle_from_frames(
    *,
    config: LHBShortlineV1Config,
    frames: LHBShortlineV1Frames,
    output_dir: Path,
) -> tuple[LHBShortlineV1Result, pd.DataFrame, dict[str, str]]:
    from stock_research.lhb_data import build_lhb_full_market_pool_backtest_v1
    from stock_research.lhb_data import build_lhb_phase12a_multi_context_decision_v1
    from stock_research.lhb_data import build_lhb_phase12a_real_entry_backtest_v1
    from stock_research.lhb_data import build_lhb_phase12a_rule_decision_v1
    from stock_research.lhb_data import build_lhb_phase14c_lifecycle_portfolio_v1
    from stock_research.lhb_data import build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1
    from stock_research.lhb_data import build_lhb_shortline_intraday_confirmation_v1

    output_dir.mkdir(parents=True, exist_ok=True)
    top_values = _lhb_shortline_v1_top_values(config.top_n)
    pool = build_lhb_full_market_pool_backtest_v1(
        lhb_features=frames.lhb_features,
        daily_bars=frames.daily_bars,
        start_date=config.start_date,
        end_date=config.end_date,
        top_n_values=top_values,
        pool_mode="raw_lhb_positive",
        output_dir=output_dir,
    )
    selected = pool["selected_trades"].copy()
    _assert_lhb_contract_versions(selected, stage="full_market_selected")
    contract_decisions = selected.copy()
    lifecycle_minute_bars = _filter_lhb_shortline_v1_lifecycle_minute_window(
        selected=selected,
        minute_bars=frames.minute_bars,
        holding_trade_days=5,
    )
    intraday = build_lhb_shortline_intraday_confirmation_v1(
        candidates=selected,
        minute_bars=frames.minute_bars,
        output_dir=output_dir,
    )
    phase12a = build_lhb_phase12a_multi_context_decision_v1(
        selected_trades=selected,
        minute_bars=frames.minute_bars,
        intraday_detail=intraday["detail"],
        output_dir=output_dir,
        pre_context_days=2,
    )
    phase12a["decision"] = _attach_lhb_contract_decisions(
        phase12a["decision"],
        decisions=contract_decisions,
        stage="phase12a_decision",
    )
    rule = build_lhb_phase12a_rule_decision_v1(
        phase12a_decision=phase12a["decision"],
        output_dir=output_dir,
    )
    rule["rule_decision"] = _attach_lhb_contract_decisions(
        rule["rule_decision"],
        decisions=contract_decisions,
        stage="phase12a_rule",
    )
    real_entry = build_lhb_phase12a_real_entry_backtest_v1(
        rule_decision=rule["rule_decision"],
        minute_bars=frames.minute_bars,
        daily_bars=frames.daily_bars,
        output_dir=output_dir,
        entry_start_time="10:30:00",
        slippage_bps=0.0,
    )
    real_entry["trades"] = _attach_lhb_contract_decisions(
        real_entry["trades"],
        decisions=contract_decisions,
        stage="real_entry",
    )
    lifecycle = build_lhb_phase14c_lifecycle_portfolio_v1(
        entry_trades=real_entry["trades"],
        minute_bars=lifecycle_minute_bars,
        output_dir=output_dir,
        max_hold_days=5,
        threshold_profile="sensitive_entry_buffer",
    )
    lifecycle_trades = lifecycle["lifecycle_trades"].copy()
    lifecycle_trades = _attach_lhb_contract_decisions(
        lifecycle_trades,
        decisions=contract_decisions,
        stage="lifecycle",
    )
    lifecycle["lifecycle_trades"] = lifecycle_trades
    review_scored = _attach_lhb_shortline_v1_auction_score(
        lifecycle_trades,
        frames.auction_open,
        daily_bars=frames.daily_bars,
    )
    review_scored = _attach_lhb_contract_decisions(
        review_scored,
        decisions=contract_decisions,
        stage="review_scored_candidates",
    )
    lifecycle_trades = _filter_rows_to_lhb_shortline_asof_cutoff(
        lifecycle_trades,
        end_date=config.end_date,
        date_columns=("trade_date", "entry_trade_date", "exit_trade_date"),
        require_known_dates=False,
    )
    lifecycle_trades["gross_realized_return"] = pd.to_numeric(
        lifecycle_trades.get("realized_return", pd.Series(dtype="float64")), errors="coerce"
    )
    lifecycle_trades["transaction_cost_return"] = config.round_trip_cost_return
    lifecycle_trades.loc[lifecycle_trades["gross_realized_return"].notna(), "realized_return"] = (
        lifecycle_trades["gross_realized_return"] - config.round_trip_cost_return
    )
    scored = _attach_lhb_shortline_v1_auction_score(
        lifecycle_trades,
        frames.auction_open,
        daily_bars=frames.daily_bars,
    )
    scored = _attach_lhb_contract_decisions(
        scored,
        decisions=contract_decisions,
        stage="phase18c_scored_candidates",
    )
    phase18c = build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1(
        lifecycle_trades=lifecycle_trades,
        scored_candidates=scored,
        output_dir=output_dir,
        top_ns=[config.top_n],
        max_positions=config.account_max_positions,
        position_pct=config.position_weight,
        write_outputs=True,
    )

    strategy = "auction_enhanced_rerank"
    account_trades = phase18c["account_trades"]
    account_curve = phase18c["account_curve"]
    summary_frame = phase18c["summary"]
    selected_trades = phase18c["selected_trades"]
    account_trades = _attach_lhb_contract_decisions(
        account_trades,
        decisions=contract_decisions,
        stage="phase18c_account_trades",
    )
    selected_trades = _attach_lhb_contract_decisions(
        selected_trades,
        decisions=contract_decisions,
        stage="phase18c_selected_trades",
    )
    phase18c["account_trades"] = account_trades
    phase18c["selected_trades"] = selected_trades
    account_trades = _filter_rows_to_lhb_shortline_asof_cutoff(
        account_trades,
        end_date=config.end_date,
        date_columns=("trade_date", "entry_trade_date", "exit_trade_date"),
        require_known_dates=False,
    )
    account_curve = _filter_rows_to_lhb_shortline_asof_cutoff(
        account_curve,
        end_date=config.end_date,
        date_columns=("trade_date",),
        require_known_dates=True,
    )
    selected_trades = _filter_rows_to_lhb_shortline_asof_cutoff(
        selected_trades,
        end_date=config.end_date,
        date_columns=("trade_date", "entry_trade_date", "exit_trade_date"),
        require_known_dates=False,
    )
    if "strategy" in account_trades.columns:
        account_trades = account_trades[
            account_trades["strategy"].eq(strategy)
            & pd.to_numeric(account_trades["top_n"], errors="coerce").eq(config.top_n)
        ].copy()
    if "strategy" in account_curve.columns:
        account_curve = account_curve[
            account_curve["strategy"].eq(strategy)
            & pd.to_numeric(account_curve["top_n"], errors="coerce").eq(config.top_n)
        ].copy()
    if "strategy" in selected_trades.columns:
        selected_trades = selected_trades[
            selected_trades["strategy"].eq(strategy)
            & pd.to_numeric(selected_trades["top_n"], errors="coerce").eq(config.top_n)
        ].copy()
    if "strategy" in summary_frame.columns:
        summary_frame = summary_frame[
            summary_frame["strategy"].eq(strategy)
            & pd.to_numeric(summary_frame["top_n"], errors="coerce").eq(config.top_n)
        ].copy()

    if summary_frame.empty:
        result = _empty_backtest_result(config)
    else:
        risk_profile = _normalize_lhb_shortline_risk_profile(config.risk_profile)
        profile_def = LHB_SHORTLINE_RISK_PROFILES[risk_profile]
        baseline_summary = summary_frame.iloc[0].to_dict()
        stable_account = _select_lhb_stable_account(
            phase18c_summary=baseline_summary,
            phase18c_account_trades=account_trades,
            phase18c_account_curve=account_curve,
        )
        summary = stable_account["summary"]
        account_trades = stable_account["account_trades"]
        account_curve = stable_account["account_curve"]
        existing_sharpe = pd.to_numeric(
            pd.Series([summary.get("sharpe_ratio")]), errors="coerce"
        ).iloc[0]
        if pd.isna(existing_sharpe):
            summary["sharpe_ratio"] = _annualized_sharpe_from_equity_curve(account_curve)
        summary.update(
            {
                "engine_version": config.engine_version,
                **_lhb_safe_top5_summary_metadata(baseline_summary),
                "fresh_engine_note": "LHB stable Phase18C safe Top5 account without market overlay",
                "phase18c_strategy": strategy,
                "phase18c_top_n": config.top_n,
                "position_pct": config.position_weight,
                "phase18c_max_positions": config.account_max_positions,
                "transaction_cost_bps": config.transaction_cost_bps,
                "adjust_type": config.adjust_type,
                "frequency": config.rebalance_frequency,
                "risk_profile": risk_profile,
                "risk_profile_label": profile_def["label"],
                "market_regime_profile": "disabled_for_stable_strategy",
                "market_regime_note": "稳定版不使用市场环境仓位控制；相关逻辑仅保留为独立研究实验。",
                "baseline_phase18c_final_equity": baseline_summary.get("final_equity"),
                "baseline_phase18c_total_return": baseline_summary.get("total_return"),
                "baseline_phase18c_max_drawdown": baseline_summary.get("max_drawdown"),
                "baseline_phase18c_filled_trade_count": baseline_summary.get("filled_trade_count"),
                "actual_start_date": (
                    str(account_curve["trade_date"].iloc[0]) if not account_curve.empty else None
                ),
                "actual_end_date": (
                    str(account_curve["trade_date"].iloc[-1]) if not account_curve.empty else None
                ),
            }
        )
        result = LHBShortlineV1Result(
            summary=summary,
            equity_curve=account_curve.reset_index(drop=True),
            positions=account_trades.reset_index(drop=True),
            trades=account_trades.reset_index(drop=True),
        )

    paths: dict[str, str] = {}
    for key in ["paths"]:
        for source in [pool, intraday, phase12a, rule, real_entry, lifecycle, phase18c]:
            paths.update({f"pipeline_{k}": v for k, v in source.get(key, {}).items()})
    if "market_regime" in locals() and not market_regime.empty:
        market_regime_path = output_dir / "lhb_shortline_v1_1_market_regime.csv"
        market_regime.to_csv(market_regime_path, index=False)
        paths["pipeline_market_regime"] = str(market_regime_path)
    parity_audit = _build_lhb_eligibility_parity_audit(
        decisions=contract_decisions,
        stages={
            "phase12a": phase12a["decision"],
            "rule": rule["rule_decision"],
            "real_entry": real_entry["trades"],
            "lifecycle": lifecycle["lifecycle_trades"],
            "phase18c_account": phase18c["account_trades"],
        },
    )
    parity_path = output_dir / "lhb_eligibility_parity_audit_v2.csv"
    parity_audit.to_csv(parity_path, index=False)
    paths["pipeline_eligibility_parity_audit"] = str(parity_path)
    review_candidates = _build_lhb_review_candidates(
        scored_candidates=selected_trades,
        risk_watch_candidates=pool["rejected_events"],
        top_n=config.top_n,
    )
    return result, review_candidates.reset_index(drop=True), paths


def run_lhb_shortline_v1_backtest_for_dashboard(payload: dict[str, Any]) -> dict[str, Any]:
    config = LHBShortlineV1Config(
        start_date=str(payload.get("start_date") or payload.get("from") or ""),
        end_date=str(payload.get("end_date") or payload.get("to") or ""),
        top_n=int(payload.get("top_n", 5)),
        rebalance_frequency=str(payload.get("rebalance_frequency", "daily")),
        transaction_cost_bps=float(payload.get("transaction_cost_bps", 0.0)),
        max_positions=(
            None if payload.get("max_positions") is None else int(payload.get("max_positions"))
        ),
        max_position_weight=(
            None
            if payload.get("max_position_weight") is None
            else float(payload.get("max_position_weight"))
        ),
        adjust_type=str(payload.get("adjust_type", "hfq")),
        risk_profile=_normalize_lhb_shortline_risk_profile(payload.get("risk_profile")),
    )
    frames = load_lhb_shortline_v1_frames_from_db(
        config,
        service=payload.get("db_service"),
    )
    output_dir = Path(str(payload["output_dir"])) if payload.get("output_dir") else _new_lhb_shortline_v1_output_dir(config.top_n)
    result, scored, pipeline_artifacts = run_lhb_shortline_v1_lifecycle_from_frames(
        config=config,
        frames=frames,
        output_dir=output_dir,
    )
    legacy_summary = load_legacy_lhb_benchmark_summary(
        top_n=config.top_n,
        position_weight=config.position_weight,
        transaction_cost_bps=config.transaction_cost_bps,
    )
    summary = dict(result.summary)
    summary["data_coverage"] = frames.coverage
    summary["legacy_benchmark"] = compare_with_legacy_lhb_benchmark(summary, legacy_summary) if legacy_summary else {}
    artifacts = write_lhb_shortline_v1_artifacts(
        output_dir=output_dir,
        config=config,
        summary=summary,
        candidates=scored,
        trades=result.trades,
        equity_curve=result.equity_curve,
    )
    artifacts.update(pipeline_artifacts)
    return {
        "strategy_id": "lhb_shortline",
        "strategy_name": "LHB Shortline Combo",
        "source_kind": config.engine_version,
        "config": asdict(config),
        "summary": summary,
        "data_coverage": frames.coverage,
        "artifacts": artifacts,
        "candidates": _records(scored),
        "equity_curve": _records(result.equity_curve),
        "positions": _records(result.positions),
        "trades": _records(result.trades),
    }
