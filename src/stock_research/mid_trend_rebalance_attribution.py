from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


VARIANT = "top5_weekly_max_2_replacements"
HORIZONS = [5, 10, 20]
REBALANCE_REASONS = {"weekly_rebalance", "adaptive_rebalance"}


def run_mid_trend_rebalance_attribution(
    *,
    trades_path: str | Path,
    equity_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    variant_name: str = VARIANT,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    trades = pd.read_csv(trades_path, low_memory=False)
    equity = pd.read_csv(equity_path, low_memory=False)
    asset_ids = sorted(set(trades.get("asset_id", pd.Series(dtype=str)).dropna().astype(str)))
    prices = _load_prices(
        asset_ids=asset_ids,
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    return build_mid_trend_rebalance_attribution_from_frames(
        trades=trades,
        prices=prices,
        equity=equity,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        variant_name=variant_name,
    )


def build_mid_trend_rebalance_attribution_from_frames(
    *,
    trades: pd.DataFrame,
    prices: pd.DataFrame,
    equity: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    variant_name: str = VARIANT,
) -> dict[str, Any]:
    normalized_trades = _normalize_trades(trades, variant_name, start_date, end_date)
    close = _close_matrix(prices, start_date, end_date)
    equity_curve = _normalize_equity(equity, variant_name, start_date, end_date)
    detail = _build_detail(normalized_trades, close, equity_curve)
    summary = _summary(detail)
    report = _render_report(summary, detail)

    result: dict[str, Any] = {"detail": detail, "summary": summary, "report": report, "paths": {}}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "mid_trend_rebalance_attribution_detail.csv",
            "summary": output / "mid_trend_rebalance_attribution_summary.csv",
            "report": output / "mid_trend_rebalance_attribution_report.md",
        }
        detail.to_csv(paths["detail"], index=False)
        summary.to_csv(paths["summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _normalize_trades(trades: pd.DataFrame, variant_name: str, start_date: str, end_date: str) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    frame = trades.copy()
    if "variant_name" in frame.columns:
        frame = frame[frame["variant_name"].astype(str).eq(variant_name)].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame = frame[frame["trade_date"].between(start_date, end_date)].copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["side"] = frame["side"].astype(str)
    for column in ["previous_weight", "target_weight", "delta_weight"]:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    if "reason" in frame.columns:
        frame = frame[frame["reason"].astype(str).isin(REBALANCE_REASONS)].copy()
    return frame


def _close_matrix(prices: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    frame = prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame[frame["trade_date"].between(start_date, end_date)].dropna(subset=["trade_date", "asset_id", "close"])
    return frame.pivot_table(index="trade_date", columns="asset_id", values="close", aggfunc="last").sort_index()


def _normalize_equity(equity: pd.DataFrame, variant_name: str, start_date: str, end_date: str) -> pd.DataFrame:
    if equity.empty:
        return pd.DataFrame()
    frame = equity.copy()
    if "variant_name" in frame.columns:
        frame = frame[frame["variant_name"].astype(str).eq(variant_name)].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date.astype(str)
    frame = frame[frame["date"].between(start_date, end_date)].copy()
    for column in ["equity", "drawdown", "net_return"]:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    return frame.sort_values("date")


def _build_detail(trades: pd.DataFrame, close: pd.DataFrame, equity: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if trades.empty:
        return pd.DataFrame()
    for trade_date, group in trades.groupby("trade_date", sort=True):
        sells = group[group["side"].eq("sell")].sort_values("asset_id").reset_index(drop=True)
        buys = group[group["side"].eq("buy")].sort_values("asset_id").reset_index(drop=True)
        pair_count = max(len(sells), len(buys))
        for idx in range(pair_count):
            sell = sells.iloc[idx] if idx < len(sells) else None
            buy = buys.iloc[idx] if idx < len(buys) else None
            row = {
                "trade_date": trade_date,
                "pair_index": idx + 1,
                "sold_asset_id": str(sell["asset_id"]) if sell is not None else "",
                "bought_asset_id": str(buy["asset_id"]) if buy is not None else "",
                "sold_weight": abs(float(sell["delta_weight"])) if sell is not None and pd.notna(sell["delta_weight"]) else np.nan,
                "bought_weight": abs(float(buy["delta_weight"])) if buy is not None and pd.notna(buy["delta_weight"]) else np.nan,
            }
            for horizon in HORIZONS:
                sold_return = _future_return(close, row["sold_asset_id"], trade_date, horizon)
                bought_return = _future_return(close, row["bought_asset_id"], trade_date, horizon)
                row[f"sold_next_{horizon}d_return"] = sold_return
                row[f"bought_next_{horizon}d_return"] = bought_return
                row[f"replacement_alpha_{horizon}d"] = (
                    bought_return - sold_return if pd.notna(bought_return) and pd.notna(sold_return) else np.nan
                )
            row.update(_equity_window_metrics(equity, trade_date))
            reasons = _bad_reasons(row)
            row["bad_rebalance_flag"] = bool(reasons)
            row["bad_rebalance_reasons"] = ";".join(reasons)
            rows.append(row)
    detail = pd.DataFrame(rows)
    if "bad_rebalance_flag" in detail.columns:
        detail["bad_rebalance_flag"] = detail["bad_rebalance_flag"].astype(object)
    return detail


def _future_return(close: pd.DataFrame, asset_id: str, trade_date: str, horizon: int) -> float:
    if close.empty or not asset_id or asset_id not in close.columns or trade_date not in close.index:
        return np.nan
    idx = close.index.get_loc(trade_date)
    target_idx = idx + horizon
    if target_idx >= len(close.index):
        return np.nan
    start = close.iloc[idx][asset_id]
    end = close.iloc[target_idx][asset_id]
    if pd.isna(start) or pd.isna(end) or float(start) == 0:
        return np.nan
    return float(end) / float(start) - 1.0


def _equity_window_metrics(equity: pd.DataFrame, trade_date: str) -> dict[str, float]:
    result = {
        "portfolio_drawdown_on_trade": np.nan,
        "portfolio_drawdown_after_5d": np.nan,
        "portfolio_drawdown_after_10d": np.nan,
        "portfolio_max_drawdown_next_10d": np.nan,
        "drawdown_amplified_10d": False,
    }
    if equity.empty or trade_date not in set(equity["date"].astype(str)):
        return result
    dates = equity["date"].astype(str).tolist()
    idx = dates.index(trade_date)
    current = float(equity.iloc[idx]["drawdown"])
    result["portfolio_drawdown_on_trade"] = current
    for horizon in [5, 10]:
        target_idx = idx + horizon
        if target_idx < len(equity):
            result[f"portfolio_drawdown_after_{horizon}d"] = float(equity.iloc[target_idx]["drawdown"])
    end_idx = min(len(equity), idx + 11)
    window = equity.iloc[idx:end_idx]["drawdown"].dropna()
    if not window.empty:
        next_mdd = float(window.min())
        result["portfolio_max_drawdown_next_10d"] = next_mdd
        result["drawdown_amplified_10d"] = bool(next_mdd < current - 0.03)
    return result


def _bad_reasons(row: dict[str, Any]) -> list[str]:
    reasons = []
    alpha10 = row.get("replacement_alpha_10d")
    alpha20 = row.get("replacement_alpha_20d")
    sold10 = row.get("sold_next_10d_return")
    bought10 = row.get("bought_next_10d_return")
    if pd.notna(alpha10) and float(alpha10) <= -0.05:
        reasons.append("negative_replacement_alpha_10d")
    if pd.notna(alpha20) and float(alpha20) <= -0.08:
        reasons.append("negative_replacement_alpha_20d")
    if pd.notna(sold10) and float(sold10) >= 0.08:
        reasons.append("sell_fly")
    if pd.notna(bought10) and float(bought10) <= -0.05:
        reasons.append("bad_buy")
    if row.get("drawdown_amplified_10d"):
        reasons.append("drawdown_amplified")
    return reasons


def _summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(
            [{"metric": "rebalance_pair_count", "value": 0}]
        )
    bad = detail[detail["bad_rebalance_flag"].astype(bool)]
    rows = [
        {"metric": "rebalance_pair_count", "value": len(detail)},
        {"metric": "bad_rebalance_pair_count", "value": len(bad)},
        {"metric": "bad_rebalance_rate", "value": len(bad) / len(detail) if len(detail) else np.nan},
        {"metric": "avg_replacement_alpha_5d", "value": _mean(detail["replacement_alpha_5d"])},
        {"metric": "avg_replacement_alpha_10d", "value": _mean(detail["replacement_alpha_10d"])},
        {"metric": "avg_replacement_alpha_20d", "value": _mean(detail["replacement_alpha_20d"])},
        {"metric": "sell_fly_count", "value": int(detail["bad_rebalance_reasons"].str.contains("sell_fly", na=False).sum())},
        {"metric": "bad_buy_count", "value": int(detail["bad_rebalance_reasons"].str.contains("bad_buy", na=False).sum())},
        {
            "metric": "drawdown_amplified_count",
            "value": int(detail["bad_rebalance_reasons"].str.contains("drawdown_amplified", na=False).sum()),
        },
    ]
    return pd.DataFrame(rows)


def _mean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def _render_report(summary: pd.DataFrame, detail: pd.DataFrame) -> str:
    bad = detail[detail["bad_rebalance_flag"].astype(bool)].copy() if not detail.empty else detail
    top_bad = bad.sort_values("replacement_alpha_10d").head(30) if not bad.empty else bad
    lines = [
        "# Mid Trend Rebalance Attribution Review",
        "",
        "## 1. Bad Rebalance Definition",
        "- negative_replacement_alpha_10d: 买入票未来10日收益比卖出票低5pct以上",
        "- negative_replacement_alpha_20d: 买入票未来20日收益比卖出票低8pct以上",
        "- sell_fly: 卖出票未来10日仍上涨8%以上",
        "- bad_buy: 买入票未来10日下跌5%以上",
        "- drawdown_amplified: 调仓后10日组合最大回撤比调仓日加深3pct以上",
        "",
        "## 2. Summary",
        summary.to_markdown(index=False) if not summary.empty else "No summary rows.",
        "",
        "## 3. Worst Rebalance Pairs",
        top_bad.to_markdown(index=False) if not top_bad.empty else "No bad rebalance rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _load_prices(
    *,
    asset_ids: list[str],
    start_date: str,
    end_date: str,
    adjust_type: str,
    service: str,
) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["trade_date", "asset_id", "close"])
    placeholders = ",".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT trade_date, asset_id, close
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
          AND asset_id IN ({placeholders})
        ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date, *asset_ids])
    return pd.DataFrame(rows)
