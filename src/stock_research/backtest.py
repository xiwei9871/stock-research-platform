from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.features import compute_p0_features_for_asset
from stock_research.selection import SCORE_VERSION, score_asset


LOW_LIQUIDITY_THRESHOLD = 30000000.0
DEFAULT_HOLDING_DAYS = (3, 5, 7, 10)
REQUIRED_SCORE_FEATURES = (
    "ret_20d",
    "ret_60d",
    "amount_20d_avg",
    "volatility_20d",
    "max_drawdown_20d",
)
FEATURE_COLUMNS = ["asset_id", "trade_date", "feature_name", "feature_value"]
BAR_COLUMNS = [
    "asset_id",
    "trade_date",
    "open",
    "preclose",
    "close",
    "amount",
    "turnover_rate",
    "trade_status",
    "is_st",
]


@dataclass(frozen=True)
class BacktestRun:
    run_id: str
    score_version: str
    start_date: str
    end_date: str
    top_n: int
    holding_days: list[int]
    buy_price_rule: str
    sell_price_rule: str
    execution_profile: str


@dataclass(frozen=True)
class BacktestSelection:
    selection_date: str
    asset_id: str
    rank: int
    score: float
    ret_20d: float | None = None
    amount_20d_avg: float | None = None


@dataclass(frozen=True)
class BacktestBar:
    asset_id: str
    trade_date: str
    open: float | None
    preclose: float | None
    amount: float | None
    trade_status: str
    is_st: bool


@dataclass(frozen=True)
class BuyDecision:
    can_buy: bool
    skip_reason: str | None = None


def _is_missing(value: object) -> bool:
    return value is None or pd.isna(value)


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _normalize_holding_days(holding_days: int | list[int] | tuple[int, ...]) -> list[int]:
    if isinstance(holding_days, int):
        return [holding_days]
    return list(holding_days)


def _normalize_selections(
    selection: BacktestSelection | list[BacktestSelection] | tuple[BacktestSelection, ...],
) -> list[BacktestSelection]:
    if isinstance(selection, BacktestSelection):
        return [selection]
    return list(selection)


def _float_or_none(value: object) -> float | None:
    if _is_missing(value):
        return None
    return float(value)


def _db_value(value: object) -> object:
    if _is_missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return value


def _frame_records(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, object]]:
    if frame.empty:
        return []
    records = []
    for row in frame.reindex(columns=columns).to_dict("records"):
        records.append({key: _db_value(value) for key, value in row.items()})
    return records


def _bar_from_row(row: pd.Series) -> BacktestBar:
    return BacktestBar(
        asset_id=str(row["asset_id"]),
        trade_date=_iso_date(row["trade_date"]),
        open=_float_or_none(row["open"]),
        preclose=_float_or_none(row["preclose"]),
        amount=_float_or_none(row["amount"]),
        trade_status=str(row["trade_status"]),
        is_st=bool(row["is_st"]),
    )


def _empty_trades_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "selection_date",
            "asset_id",
            "rank",
            "score",
            "holding_days",
            "buy_date",
            "buy_open",
            "sell_date",
            "sell_open",
            "return_value",
            "status",
            "skip_reason",
            "ret_20d",
        ]
    )


def make_run_id(
    start_date: object,
    end_date: object,
    top_n: int = 20,
    holding_days: int | list[int] | tuple[int, ...] = DEFAULT_HOLDING_DAYS,
    score_version: str = SCORE_VERSION,
) -> str:
    horizons = _normalize_holding_days(holding_days)
    horizon_part = "-".join(str(value) for value in horizons)
    return f"top20:{_iso_date(start_date)}:{_iso_date(end_date)}:n{top_n}:h{horizon_part}:{score_version}"


def next_trade_date(trading_dates: list[object], trade_date: object) -> str | None:
    current = _iso_date(trade_date)
    for date in sorted({_iso_date(value) for value in trading_dates}):
        if date > current:
            return date
    return None


def apply_buy_filter(
    selection: BacktestSelection,
    bar: BacktestBar | None,
    liquidity_threshold: float = LOW_LIQUIDITY_THRESHOLD,
) -> BuyDecision:
    if _is_missing(selection.amount_20d_avg) or selection.amount_20d_avg < liquidity_threshold:
        return BuyDecision(False, "low_liquidity")
    if bar is None:
        return BuyDecision(False, "suspended")
    if bar.trade_status != "1":
        return BuyDecision(False, "suspended")
    if bar.is_st is True:
        return BuyDecision(False, "st")
    if _is_missing(bar.open) or _is_missing(bar.preclose):
        return BuyDecision(False, "missing_price")
    if _is_missing(bar.amount) or bar.amount < liquidity_threshold:
        return BuyDecision(False, "low_liquidity")
    if float(bar.open) >= float(bar.preclose) * 1.095:
        return BuyDecision(False, "limit_up_open")
    return BuyDecision(True)


def sell_bar_for_holding(
    bars: list[BacktestBar],
    buy_date: str,
    holding_days: int,
) -> BacktestBar | None:
    """Return the sell bar after holding_days rows after buy date, rolling forward if target is untradable."""
    if holding_days <= 0:
        raise ValueError("holding_days must be positive")

    normalized_buy_date = _iso_date(buy_date)
    ordered = sorted(bars, key=lambda bar: _iso_date(bar.trade_date))
    after_buy = [bar for bar in ordered if _iso_date(bar.trade_date) > normalized_buy_date]
    if len(after_buy) < holding_days:
        return None

    target_index = holding_days - 1
    for bar in after_buy[target_index:]:
        if bar.trade_status == "1" and not _is_missing(bar.open):
            return bar
    return None


def return_value(buy_open: float, sell_open: float) -> float:
    return round(sell_open / buy_open - 1.0, 10)


def select_top_for_date(
    feature_frame: pd.DataFrame,
    bar_frame: pd.DataFrame,
    selection_date: object,
    top_n: int = 20,
    liquidity_threshold: float = LOW_LIQUIDITY_THRESHOLD,
) -> list[BacktestSelection]:
    normalized_date = _iso_date(selection_date)
    if feature_frame.empty or bar_frame.empty:
        return []

    features = feature_frame.copy()
    features["trade_date"] = features["trade_date"].map(_iso_date)
    features = features[features["trade_date"] == normalized_date]
    if features.empty:
        return []

    matrix = features.pivot_table(
        index="asset_id",
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    )

    bars = bar_frame.copy()
    bars["trade_date"] = bars["trade_date"].map(_iso_date)
    bars = bars[bars["trade_date"] == normalized_date]
    if bars.empty:
        return []
    bars_by_asset = bars.drop_duplicates("asset_id").set_index("asset_id")

    scored: list[dict[str, Any]] = []
    for asset_id, row in matrix.iterrows():
        if asset_id not in bars_by_asset.index:
            continue
        status = bars_by_asset.loc[asset_id]
        if bool(status["is_st"]) is True or str(status["trade_status"]) != "1":
            continue

        features_for_asset = row.to_dict()
        if any(_is_missing(features_for_asset.get(name)) for name in REQUIRED_SCORE_FEATURES):
            continue
        numeric_features = {
            name: float(value) for name, value in features_for_asset.items() if not _is_missing(value)
        }
        amount_20d_avg = numeric_features.get("amount_20d_avg")
        if _is_missing(amount_20d_avg) or float(amount_20d_avg) < liquidity_threshold:
            continue

        scored.append(
            {
                "asset_id": str(asset_id),
                "score": score_asset(numeric_features),
                "ret_20d": numeric_features.get("ret_20d"),
                "amount_20d_avg": amount_20d_avg,
            }
        )

    scored.sort(key=lambda row: (-float(row["score"]), row["asset_id"]))
    return [
        BacktestSelection(
            selection_date=normalized_date,
            asset_id=row["asset_id"],
            rank=rank,
            score=float(row["score"]),
            ret_20d=_float_or_none(row["ret_20d"]),
            amount_20d_avg=_float_or_none(row["amount_20d_avg"]),
        )
        for rank, row in enumerate(scored[:top_n], start=1)
    ]


def simulate_selection(
    selection: BacktestSelection | list[BacktestSelection] | tuple[BacktestSelection, ...],
    bars_by_asset: dict[str, list[BacktestBar]],
    trading_dates: list[object],
    holding_days: int | list[int] | tuple[int, ...],
) -> list[dict[str, Any]]:
    selections = _normalize_selections(selection)
    horizons = _normalize_holding_days(holding_days)
    trades: list[dict[str, Any]] = []

    for selected in selections:
        selection_date = _iso_date(selected.selection_date)
        buy_date = next_trade_date(trading_dates, selection_date)
        asset_bars = sorted(
            bars_by_asset.get(selected.asset_id, []),
            key=lambda bar: _iso_date(bar.trade_date),
        )
        buy_bar = next(
            (bar for bar in asset_bars if _iso_date(bar.trade_date) == buy_date),
            None,
        )
        decision = (
            BuyDecision(False, "missing_next_buy_date")
            if buy_date is None
            else apply_buy_filter(selected, buy_bar)
        )

        for horizon in horizons:
            trade: dict[str, Any] = {
                "selection_date": selection_date,
                "asset_id": selected.asset_id,
                "rank": selected.rank,
                "score": selected.score,
                "holding_days": horizon,
                "buy_date": buy_date,
                "buy_open": None,
                "sell_date": None,
                "sell_open": None,
                "return_value": None,
                "status": "skipped",
                "skip_reason": decision.skip_reason,
                "ret_20d": selected.ret_20d,
            }
            if not decision.can_buy:
                trades.append(trade)
                continue

            buy_open = float(buy_bar.open)  # type: ignore[union-attr,arg-type]
            trade["buy_open"] = buy_open
            sell_bar = sell_bar_for_holding(asset_bars, buy_date=str(buy_date), holding_days=horizon)
            if sell_bar is None:
                trade["status"] = "unclosed"
                trade["skip_reason"] = None
                trades.append(trade)
                continue

            sell_open = float(sell_bar.open)  # sell_bar_for_holding filters missing open.
            trade.update(
                {
                    "sell_date": _iso_date(sell_bar.trade_date),
                    "sell_open": sell_open,
                    "return_value": return_value(buy_open, sell_open),
                    "status": "closed",
                    "skip_reason": None,
                }
            )
            trades.append(trade)

    return trades


def run_backtest_frame(
    feature_frame: pd.DataFrame,
    bar_frame: pd.DataFrame,
    start_date: object,
    end_date: object,
    holding_days: list[int] | tuple[int, ...] = DEFAULT_HOLDING_DAYS,
    top_n: int = 20,
) -> pd.DataFrame:
    if feature_frame.empty or bar_frame.empty:
        return _empty_trades_frame()

    start = _iso_date(start_date)
    end = _iso_date(end_date)
    bars = bar_frame.copy()
    bars["trade_date"] = bars["trade_date"].map(_iso_date)
    trading_dates = sorted(bars["trade_date"].dropna().unique().tolist())

    scoped_features = feature_frame.copy()
    scoped_features["trade_date"] = scoped_features["trade_date"].map(_iso_date)
    selection_dates = sorted(
        date
        for date in scoped_features["trade_date"].dropna().unique().tolist()
        if start <= date <= end and next_trade_date(trading_dates, date) is not None
    )

    bars_by_asset = {
        asset_id: [_bar_from_row(row) for _, row in group.iterrows()]
        for asset_id, group in bars.groupby("asset_id", sort=False)
    }

    trades: list[dict[str, Any]] = []
    for selection_date in selection_dates:
        selected = select_top_for_date(scoped_features, bars, selection_date, top_n=top_n)
        if not selected:
            continue
        trades.extend(
            simulate_selection(
                selected,
                bars_by_asset,
                trading_dates,
                holding_days=holding_days,
            )
        )

    if not trades:
        return _empty_trades_frame()
    return pd.DataFrame(trades)


def build_equity_curve(
    batch_returns: list[dict[str, Any]] | pd.DataFrame,
    holding_days: int,
    run_id: str | None = None,
) -> pd.DataFrame:
    frame = pd.DataFrame(batch_returns).copy()
    columns = [
        "run_id",
        "holding_days",
        "selection_date",
        "batch_return",
        "equity_value",
        "drawdown",
        "closed_trades",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    frame["selection_date"] = frame["selection_date"].map(_iso_date)
    frame = frame.sort_values("selection_date").reset_index(drop=True)
    frame["batch_return"] = pd.to_numeric(frame["batch_return"], errors="coerce")
    frame = frame.dropna(subset=["batch_return"]).reset_index(drop=True)
    if frame.empty:
        return pd.DataFrame(columns=columns)

    frame["equity_value"] = (1.0 + frame["batch_return"]).cumprod()
    running_max = frame["equity_value"].cummax()
    frame["drawdown"] = frame["equity_value"] / running_max - 1.0
    frame["holding_days"] = holding_days
    if run_id is not None:
        frame["run_id"] = run_id
    elif "run_id" not in frame.columns:
        frame["run_id"] = None
    return frame[columns]


def max_drawdown_window(curve: pd.DataFrame) -> dict[str, Any]:
    no_drawdown = {
        "max_batch_drawdown": 0.0,
        "max_drawdown_start_date": None,
        "max_drawdown_valley_date": None,
        "max_drawdown_recovery_date": None,
    }
    if curve.empty:
        return no_drawdown

    frame = curve.copy()
    frame["selection_date"] = frame["selection_date"].map(_iso_date)
    frame["equity_value"] = pd.to_numeric(frame["equity_value"], errors="coerce")
    frame["drawdown"] = pd.to_numeric(frame["drawdown"], errors="coerce")
    frame = frame.dropna(subset=["equity_value", "drawdown"])
    if frame.empty:
        return no_drawdown

    frame = frame.sort_values("selection_date").reset_index(drop=True)
    valley_index = frame["drawdown"].idxmin()
    valley = frame.loc[valley_index]
    max_drawdown = float(valley["drawdown"])
    if max_drawdown >= 0:
        return no_drawdown

    running_max = frame["equity_value"].cummax()
    peak_value = running_max.loc[valley_index]
    peak_candidates = frame.loc[:valley_index]
    peak_index = peak_candidates[
        peak_candidates["equity_value"] == float(peak_value)
    ].index[-1]

    recovery_date = None
    for _, row in frame.loc[valley_index + 1 :].iterrows():
        if float(row["equity_value"]) >= float(peak_value):
            recovery_date = row["selection_date"]
            break

    return {
        "max_batch_drawdown": round(max_drawdown, 10),
        "max_drawdown_start_date": frame.loc[peak_index, "selection_date"],
        "max_drawdown_valley_date": valley["selection_date"],
        "max_drawdown_recovery_date": recovery_date,
    }


def quantiles(values: pd.Series | list[float], prefix: str) -> dict[str, float | None]:
    series = pd.Series(values).dropna()
    if series.empty:
        return {
            f"{prefix}_p10": None,
            f"{prefix}_p25": None,
            f"{prefix}_p75": None,
            f"{prefix}_p90": None,
        }
    return {
        f"{prefix}_p10": float(series.quantile(0.10)),
        f"{prefix}_p25": float(series.quantile(0.25)),
        f"{prefix}_p75": float(series.quantile(0.75)),
        f"{prefix}_p90": float(series.quantile(0.90)),
    }


def _max_losing_streak(batch_returns: pd.Series) -> int:
    longest = 0
    current = 0
    for value in batch_returns:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def summarize_holding(
    run_id: str,
    trades: pd.DataFrame,
    holding_days: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    scoped = trades[trades["holding_days"] == holding_days].copy()
    if not scoped.empty:
        scoped["selection_date"] = scoped["selection_date"].map(_iso_date)
    closed = scoped[scoped["status"] == "closed"].copy()
    skipped = scoped[scoped["status"] == "skipped"]
    unclosed = scoped[scoped["status"] == "unclosed"]

    if closed.empty:
        batch_frame = pd.DataFrame(columns=["selection_date", "batch_return", "closed_trades"])
    else:
        batch_frame = (
            closed.groupby("selection_date", as_index=False)
            .agg(batch_return=("return_value", "mean"), closed_trades=("return_value", "count"))
            .sort_values("selection_date")
        )
    curve = build_equity_curve(batch_frame, holding_days=holding_days, run_id=run_id)

    returns = pd.to_numeric(closed["return_value"], errors="coerce").dropna()
    batch_returns = pd.to_numeric(batch_frame.get("batch_return", pd.Series(dtype=float)), errors="coerce").dropna()
    drawdown = max_drawdown_window(curve)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "holding_days": holding_days,
        "selection_days": int(scoped["selection_date"].nunique()) if not scoped.empty else 0,
        "theoretical_trades": int(len(scoped)),
        "closed_trades": int(len(closed)),
        "skipped_trades": int(len(skipped)),
        "unclosed_trades": int(len(unclosed)),
        "mean_return": float(returns.mean()) if not returns.empty else None,
        "median_return": float(returns.median()) if not returns.empty else None,
        "win_rate": float((returns > 0).mean()) if not returns.empty else None,
        "best_return": float(returns.max()) if not returns.empty else None,
        "worst_return": float(returns.min()) if not returns.empty else None,
        "batch_mean_return": float(batch_returns.mean()) if not batch_returns.empty else None,
        "batch_win_rate": float((batch_returns > 0).mean()) if not batch_returns.empty else None,
        "max_losing_streak": _max_losing_streak(batch_returns),
    }
    summary.update(drawdown)
    summary.update(quantiles(returns, "single_return"))
    summary.update(quantiles(batch_returns, "batch_return"))
    return summary, curve


def load_backtest_inputs(
    start_date: object,
    end_date: object,
    future_buffer_days: int = 30,
    feature_lookback_days: int = 220,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    lookback_start = (
        pd.Timestamp(start) - pd.Timedelta(days=feature_lookback_days)
    ).date().isoformat()
    buffered_end = (pd.Timestamp(end) + pd.Timedelta(days=future_buffer_days)).date().isoformat()
    feature_sql = """
    SELECT asset_id, trade_date, feature_name, feature_value
    FROM feature_snapshot
    WHERE feature_set = 'p0_daily'
      AND feature_version = 'v1'
      AND trade_date >= %s
      AND trade_date <= %s
    ORDER BY trade_date, asset_id, feature_name
    """
    bar_sql = """
    SELECT
        asset_id,
        trade_date,
        open,
        preclose,
        close,
        amount,
        turnover_rate,
        trade_status,
        is_st
    FROM market_daily_bar
    WHERE adjust_type = 'hfq'
      AND trade_date >= %s
      AND trade_date <= %s
    ORDER BY trade_date, asset_id
    """
    with connect(SETTINGS.research_service) as conn:
        snapshot_features = pd.DataFrame(fetch_all(conn, feature_sql, [start, end]))
        bars = pd.DataFrame(fetch_all(conn, bar_sql, [lookback_start, buffered_end]))

    snapshot_features = snapshot_features.reindex(columns=FEATURE_COLUMNS)
    bars = bars.reindex(columns=BAR_COLUMNS)
    if bars.empty:
        return snapshot_features, bars

    computed_frames = []
    for asset_id, group in bars.groupby("asset_id", sort=False):
        asset_bars = group.drop(columns=["asset_id"]).reset_index(drop=True).copy()
        computed_frames.append(compute_p0_features_for_asset(str(asset_id), asset_bars))

    if computed_frames:
        computed_features = pd.concat(computed_frames, ignore_index=True)
    else:
        computed_features = pd.DataFrame()
    computed_features = computed_features.reindex(columns=FEATURE_COLUMNS)
    if computed_features.empty:
        return snapshot_features, bars

    computed_features["trade_date"] = computed_features["trade_date"].map(_iso_date)
    computed_features = computed_features[
        (computed_features["trade_date"] >= start)
        & (computed_features["trade_date"] <= end)
    ].reset_index(drop=True)
    if computed_features.empty:
        return snapshot_features, bars

    return computed_features, bars


def load_backtest_bars(
    start_date: object,
    end_date: object,
    future_buffer_days: int = 30,
) -> pd.DataFrame:
    start = _iso_date(start_date)
    buffered_end = (pd.Timestamp(end_date) + pd.Timedelta(days=future_buffer_days)).date().isoformat()
    bar_sql = """
    SELECT
        asset_id,
        trade_date,
        open,
        preclose,
        close,
        amount,
        turnover_rate,
        trade_status,
        is_st
    FROM market_daily_bar
    WHERE adjust_type = 'hfq'
      AND trade_date >= %s
      AND trade_date <= %s
    ORDER BY trade_date, asset_id
    """
    with connect(SETTINGS.research_service) as conn:
        bars = pd.DataFrame(fetch_all(conn, bar_sql, [start, buffered_end]))
    return bars.reindex(columns=BAR_COLUMNS)


def store_backtest_results(
    run: BacktestRun,
    trades: pd.DataFrame,
    summaries: pd.DataFrame,
    curves: pd.DataFrame,
    report_path: str | None = None,
) -> None:
    run_sql = """
    INSERT INTO backtest_run (
        run_id, score_version, start_date, end_date, top_n, holding_days,
        buy_price_rule, sell_price_rule, execution_profile, report_path
    )
    VALUES (
        %(run_id)s, %(score_version)s, %(start_date)s, %(end_date)s, %(top_n)s,
        %(holding_days)s, %(buy_price_rule)s, %(sell_price_rule)s,
        %(execution_profile)s, %(report_path)s
    )
    ON CONFLICT (run_id) DO UPDATE SET
        score_version = EXCLUDED.score_version,
        start_date = EXCLUDED.start_date,
        end_date = EXCLUDED.end_date,
        top_n = EXCLUDED.top_n,
        holding_days = EXCLUDED.holding_days,
        buy_price_rule = EXCLUDED.buy_price_rule,
        sell_price_rule = EXCLUDED.sell_price_rule,
        execution_profile = EXCLUDED.execution_profile,
        report_path = EXCLUDED.report_path
    """
    trade_columns = [
        "run_id",
        "selection_date",
        "asset_id",
        "rank",
        "score",
        "holding_days",
        "buy_date",
        "buy_open",
        "sell_date",
        "sell_open",
        "return_value",
        "status",
        "skip_reason",
    ]
    trade_sql = """
    INSERT INTO backtest_trade (
        run_id, selection_date, asset_id, rank, score, holding_days, buy_date,
        buy_open, sell_date, sell_open, return_value, status, skip_reason
    )
    VALUES (
        %(run_id)s, %(selection_date)s, %(asset_id)s, %(rank)s, %(score)s,
        %(holding_days)s, %(buy_date)s, %(buy_open)s, %(sell_date)s,
        %(sell_open)s, %(return_value)s, %(status)s, %(skip_reason)s
    )
    ON CONFLICT (run_id, selection_date, asset_id, holding_days) DO UPDATE SET
        rank = EXCLUDED.rank,
        score = EXCLUDED.score,
        buy_date = EXCLUDED.buy_date,
        buy_open = EXCLUDED.buy_open,
        sell_date = EXCLUDED.sell_date,
        sell_open = EXCLUDED.sell_open,
        return_value = EXCLUDED.return_value,
        status = EXCLUDED.status,
        skip_reason = EXCLUDED.skip_reason
    """
    summary_columns = [
        "run_id",
        "holding_days",
        "selection_days",
        "theoretical_trades",
        "closed_trades",
        "skipped_trades",
        "unclosed_trades",
        "mean_return",
        "median_return",
        "win_rate",
        "best_return",
        "worst_return",
        "batch_mean_return",
        "batch_win_rate",
        "max_batch_drawdown",
        "max_drawdown_start_date",
        "max_drawdown_valley_date",
        "max_drawdown_recovery_date",
        "max_losing_streak",
        "single_return_p10",
        "single_return_p25",
        "single_return_p75",
        "single_return_p90",
        "batch_return_p10",
        "batch_return_p25",
        "batch_return_p75",
        "batch_return_p90",
    ]
    summary_sql = """
    INSERT INTO backtest_summary (
        run_id, holding_days, selection_days, theoretical_trades, closed_trades,
        skipped_trades, unclosed_trades, mean_return, median_return, win_rate,
        best_return, worst_return, batch_mean_return, batch_win_rate,
        max_batch_drawdown, max_drawdown_start_date, max_drawdown_valley_date,
        max_drawdown_recovery_date, max_losing_streak, single_return_p10,
        single_return_p25, single_return_p75, single_return_p90,
        batch_return_p10, batch_return_p25, batch_return_p75, batch_return_p90
    )
    VALUES (
        %(run_id)s, %(holding_days)s, %(selection_days)s,
        %(theoretical_trades)s, %(closed_trades)s, %(skipped_trades)s,
        %(unclosed_trades)s, %(mean_return)s, %(median_return)s, %(win_rate)s,
        %(best_return)s, %(worst_return)s, %(batch_mean_return)s,
        %(batch_win_rate)s, %(max_batch_drawdown)s,
        %(max_drawdown_start_date)s, %(max_drawdown_valley_date)s,
        %(max_drawdown_recovery_date)s, %(max_losing_streak)s,
        %(single_return_p10)s, %(single_return_p25)s, %(single_return_p75)s,
        %(single_return_p90)s, %(batch_return_p10)s, %(batch_return_p25)s,
        %(batch_return_p75)s, %(batch_return_p90)s
    )
    ON CONFLICT (run_id, holding_days) DO UPDATE SET
        selection_days = EXCLUDED.selection_days,
        theoretical_trades = EXCLUDED.theoretical_trades,
        closed_trades = EXCLUDED.closed_trades,
        skipped_trades = EXCLUDED.skipped_trades,
        unclosed_trades = EXCLUDED.unclosed_trades,
        mean_return = EXCLUDED.mean_return,
        median_return = EXCLUDED.median_return,
        win_rate = EXCLUDED.win_rate,
        best_return = EXCLUDED.best_return,
        worst_return = EXCLUDED.worst_return,
        batch_mean_return = EXCLUDED.batch_mean_return,
        batch_win_rate = EXCLUDED.batch_win_rate,
        max_batch_drawdown = EXCLUDED.max_batch_drawdown,
        max_drawdown_start_date = EXCLUDED.max_drawdown_start_date,
        max_drawdown_valley_date = EXCLUDED.max_drawdown_valley_date,
        max_drawdown_recovery_date = EXCLUDED.max_drawdown_recovery_date,
        max_losing_streak = EXCLUDED.max_losing_streak,
        single_return_p10 = EXCLUDED.single_return_p10,
        single_return_p25 = EXCLUDED.single_return_p25,
        single_return_p75 = EXCLUDED.single_return_p75,
        single_return_p90 = EXCLUDED.single_return_p90,
        batch_return_p10 = EXCLUDED.batch_return_p10,
        batch_return_p25 = EXCLUDED.batch_return_p25,
        batch_return_p75 = EXCLUDED.batch_return_p75,
        batch_return_p90 = EXCLUDED.batch_return_p90
    """
    curve_columns = [
        "run_id",
        "holding_days",
        "selection_date",
        "batch_return",
        "equity_value",
        "drawdown",
        "closed_trades",
    ]
    curve_sql = """
    INSERT INTO backtest_equity_curve (
        run_id, holding_days, selection_date, batch_return, equity_value,
        drawdown, closed_trades
    )
    VALUES (
        %(run_id)s, %(holding_days)s, %(selection_date)s, %(batch_return)s,
        %(equity_value)s, %(drawdown)s, %(closed_trades)s
    )
    ON CONFLICT (run_id, holding_days, selection_date) DO UPDATE SET
        batch_return = EXCLUDED.batch_return,
        equity_value = EXCLUDED.equity_value,
        drawdown = EXCLUDED.drawdown,
        closed_trades = EXCLUDED.closed_trades
    """
    run_row = {
        "run_id": run.run_id,
        "score_version": run.score_version,
        "start_date": _iso_date(run.start_date),
        "end_date": _iso_date(run.end_date),
        "top_n": run.top_n,
        "holding_days": run.holding_days,
        "buy_price_rule": run.buy_price_rule,
        "sell_price_rule": run.sell_price_rule,
        "execution_profile": run.execution_profile,
        "report_path": report_path,
    }
    trade_rows = _frame_records(trades.assign(run_id=run.run_id), trade_columns)
    summary_rows = _frame_records(summaries, summary_columns)
    curve_rows = _frame_records(curves, curve_columns)

    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.executemany(run_sql, [run_row])
            cur.execute("DELETE FROM backtest_trade WHERE run_id = %s", [run.run_id])
            cur.execute("DELETE FROM backtest_summary WHERE run_id = %s", [run.run_id])
            cur.execute("DELETE FROM backtest_equity_curve WHERE run_id = %s", [run.run_id])
            if trade_rows:
                cur.executemany(trade_sql, trade_rows)
            if summary_rows:
                cur.executemany(summary_sql, summary_rows)
            if curve_rows:
                cur.executemany(curve_sql, curve_rows)


def _report_stem(run: BacktestRun) -> str:
    slug = re.sub(r"[/:\s]+", "_", run.run_id.strip())
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("._")
    return slug or "backtest_report"


def _metric_value(row: pd.Series, name: str) -> object:
    if name not in row or _is_missing(row[name]):
        return None
    return row[name]


def _format_number(value: object, digits: int = 4) -> str:
    if _is_missing(value):
        return "N/A"
    return f"{float(value):.{digits}f}"


def _format_percent(value: object) -> str:
    if _is_missing(value):
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _risk_observations(trades: pd.DataFrame, summaries: pd.DataFrame) -> list[str]:
    observations: list[str] = []
    if "return_value" not in trades.columns:
        return ["- 缺少后续收益数据，暂不能判断追高风险。"]
    if "status" not in trades.columns:
        return ["- 缺少交易状态数据，暂不能判断追高风险。"]

    closed = trades[trades["status"] == "closed"].copy()
    if closed.empty:
        return ["- 已完成样本为空，暂不能判断追高风险。"]

    returns = pd.to_numeric(closed["return_value"], errors="coerce").dropna()
    if not returns.empty and float(returns.mean()) < 0:
        observations.append("- 平均后续收益为负，可能追高后短期回落。")

    if "ret_20d" in closed.columns:
        momentum = pd.to_numeric(closed["ret_20d"], errors="coerce").dropna()
        if not momentum.empty:
            observations.append(
                f"- 已完成样本的 20 日涨幅均值为 {_format_percent(momentum.mean())}。"
            )
    else:
        observations.append("- 交易明细缺少 ret_20d，追高判断未覆盖动量分层。")

    for _, row in summaries.iterrows():
        mean_return = _metric_value(row, "mean_return")
        median_return = _metric_value(row, "median_return")
        if (
            mean_return is not None
            and median_return is not None
            and float(mean_return) > float(median_return) + 0.02
        ):
            observations.append(
                f"- 持有 {int(row['holding_days'])} 日 mean 明显高于 median，结果可能依赖少数大涨样本。"
            )

    return observations or ["- 暂未观察到平均收益为负或 mean 明显高于 median 的风险信号。"]


def write_backtest_report(
    run: BacktestRun,
    trades: pd.DataFrame,
    summaries: pd.DataFrame,
    curves: pd.DataFrame,
    reports_dir: str | Path,
) -> dict[str, str]:
    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)
    stem = _report_stem(run)
    report_path = reports_path / f"{stem}.md"
    equity_curve_path = reports_path / f"{stem}_equity_curve.csv"
    trades_path = reports_path / f"{stem}_trades.csv"
    summary_path = reports_path / f"{stem}_summary.csv"

    curves.to_csv(equity_curve_path, index=False)
    trades.to_csv(trades_path, index=False)
    summaries.to_csv(summary_path, index=False)

    lines = [
        "# Top 20 评分选股回测报告",
        "",
        "仅作为研究验证，不构成交易指令。",
        "",
        "## 总览",
        "",
        f"- 回测区间：{run.start_date} 至 {run.end_date}",
        f"- top_n：{run.top_n}",
        f"- holding_days：{', '.join(str(value) for value in run.holding_days)}",
        f"- 评分版本：{run.score_version}",
        "",
        "| 持有周期 | 理论样本 | closed | skipped | unclosed | mean | median | win_rate | max_drawdown |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    summary_by_horizon = {
        int(row["holding_days"]): row for _, row in summaries.iterrows()
    }
    for horizon in run.holding_days:
        row = summary_by_horizon.get(int(horizon), pd.Series(dtype=object))
        lines.append(
            "| "
            f"持有 {horizon} | "
            f"{int(_metric_value(row, 'theoretical_trades') or 0)} | "
            f"{int(_metric_value(row, 'closed_trades') or 0)} | "
            f"{int(_metric_value(row, 'skipped_trades') or 0)} | "
            f"{int(_metric_value(row, 'unclosed_trades') or 0)} | "
            f"{_format_percent(_metric_value(row, 'mean_return'))} | "
            f"{_format_percent(_metric_value(row, 'median_return'))} | "
            f"{_format_percent(_metric_value(row, 'win_rate'))} | "
            f"{_format_percent(_metric_value(row, 'max_batch_drawdown'))} |"
        )

    lines.extend(
        [
            "",
            "## 分持有周期表现",
            "",
        ]
    )
    for horizon in run.holding_days:
        row = summary_by_horizon.get(int(horizon), pd.Series(dtype=object))
        lines.extend(
            [
                f"### 持有 {horizon} 日",
                "",
                f"- 选股日数量：{int(_metric_value(row, 'selection_days') or 0)}",
                f"- 理论样本：{int(_metric_value(row, 'theoretical_trades') or 0)}",
                f"- closed/skipped/unclosed：{int(_metric_value(row, 'closed_trades') or 0)}/"
                f"{int(_metric_value(row, 'skipped_trades') or 0)}/"
                f"{int(_metric_value(row, 'unclosed_trades') or 0)}",
                f"- 每周期 mean/median/win_rate/max_drawdown："
                f"{_format_percent(_metric_value(row, 'mean_return'))}/"
                f"{_format_percent(_metric_value(row, 'median_return'))}/"
                f"{_format_percent(_metric_value(row, 'win_rate'))}/"
                f"{_format_percent(_metric_value(row, 'max_batch_drawdown'))}",
                "",
            ]
        )

    lines.extend(
        [
            "## 收益率曲线",
            "",
            f"- 曲线 CSV 路径：{equity_curve_path}",
        ]
    )
    for horizon in run.holding_days:
        if "holding_days" not in curves.columns:
            scoped_curve = pd.DataFrame()
        else:
            scoped_curve = curves[
                pd.to_numeric(curves["holding_days"], errors="coerce") == int(horizon)
            ].copy()
        if scoped_curve.empty:
            lines.append(f"- 持有 {horizon} 日：无曲线样本。")
            continue
        if "equity_value" not in scoped_curve.columns:
            lines.append(f"- 持有 {horizon} 日：无曲线样本。")
            continue
        equity = pd.to_numeric(scoped_curve["equity_value"], errors="coerce").dropna()
        if equity.empty:
            lines.append(f"- 持有 {horizon} 日：无曲线样本。")
            continue
        lines.append(
            f"- 持有 {horizon} 日：起点 {_format_number(equity.iloc[0])}，"
            f"终点 {_format_number(equity.iloc[-1])}，最高 {_format_number(equity.max())}，"
            f"最低 {_format_number(equity.min())}。"
        )

    lines.extend(["", "## 回撤曲线", ""])
    for horizon in run.holding_days:
        row = summary_by_horizon.get(int(horizon), pd.Series(dtype=object))
        recovery = _metric_value(row, "max_drawdown_recovery_date") or "unrecovered"
        lines.append(
            f"- 持有 {horizon} 日：最大回撤 {_format_percent(_metric_value(row, 'max_batch_drawdown'))}，"
            f"开始 {_metric_value(row, 'max_drawdown_start_date') or 'N/A'}，"
            f"谷底 {_metric_value(row, 'max_drawdown_valley_date') or 'N/A'}，"
            f"恢复 {recovery}。"
        )

    skip_counts = (
        trades[trades.get("status") == "skipped"]["skip_reason"].value_counts(dropna=False)
        if "status" in trades.columns and "skip_reason" in trades.columns
        else pd.Series(dtype=int)
    )
    lines.extend(["", "## 样本剔除", ""])
    if skip_counts.empty:
        lines.append("- 无剔除样本。")
    else:
        for reason, count in skip_counts.items():
            lines.append(f"- {reason or 'unknown'}：{int(count)}")

    lines.extend(["", "## 追高风险观察", ""])
    lines.extend(_risk_observations(trades, summaries))

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "report_path": str(report_path),
        "equity_curve_path": str(equity_curve_path),
        "trades_path": str(trades_path),
        "summary_path": str(summary_path),
    }


def run_top20_backtest(
    start_date: object,
    end_date: object,
    holding_days: int | list[int] | tuple[int, ...],
    top_n: int = 20,
    reports_dir: str | None = None,
) -> dict[str, object]:
    horizons = _normalize_holding_days(holding_days)
    run = BacktestRun(
        run_id=make_run_id(start_date, end_date, top_n=top_n, holding_days=horizons),
        score_version=SCORE_VERSION,
        start_date=_iso_date(start_date),
        end_date=_iso_date(end_date),
        top_n=top_n,
        holding_days=horizons,
        buy_price_rule="next_open",
        sell_price_rule="holding_open",
        execution_profile="a_share_daily_v1",
    )
    future_buffer_days = max(max(horizons) * 3, 30) if horizons else 30
    features, bars = load_backtest_inputs(
        start_date,
        end_date,
        future_buffer_days=future_buffer_days,
    )
    trades = run_backtest_frame(
        features,
        bars,
        start_date=start_date,
        end_date=end_date,
        holding_days=horizons,
        top_n=top_n,
    )

    summary_rows = []
    curve_frames = []
    for horizon in horizons:
        summary, curve = summarize_holding(run.run_id, trades, horizon)
        summary_rows.append(summary)
        curve_frames.append(curve)

    summaries = pd.DataFrame(summary_rows)
    curves = (
        pd.concat(curve_frames, ignore_index=True)
        if curve_frames
        else pd.DataFrame(
            columns=[
                "run_id",
                "holding_days",
                "selection_date",
                "batch_return",
                "equity_value",
                "drawdown",
                "closed_trades",
            ]
        )
    )
    report_paths = None
    report_path = None
    if reports_dir is not None:
        report_paths = write_backtest_report(run, trades, summaries, curves, reports_dir)
        report_path = report_paths["report_path"]
    store_backtest_results(run, trades, summaries, curves, report_path=report_path)
    return {
        "run": run,
        "trades": trades,
        "summaries": summaries,
        "curves": curves,
        "report_path": report_path,
        "report_paths": report_paths,
    }
