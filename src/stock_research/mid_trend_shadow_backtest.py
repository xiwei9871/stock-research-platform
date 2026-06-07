from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    run_vectorized_topn_backtest,
)


def run_mid_trend_shadow_backtest(
    *,
    shadow_top10_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    top_n: int = 10,
    rebalance_frequency: str = "daily",
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    shadow_top10 = pd.read_csv(shadow_top10_path, low_memory=False)
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    return build_mid_trend_shadow_backtest_from_frames(
        shadow_top10=shadow_top10,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        top_n=top_n,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
    )


def build_mid_trend_shadow_backtest_from_frames(
    *,
    shadow_top10: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    top_n: int = 10,
    rebalance_frequency: str = "daily",
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    scores = _scores_from_shadow_top10(shadow_top10)
    config = VectorizedTopNConfig(
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
    )
    backtest = run_vectorized_topn_backtest(scores, prices, config)
    summary = _summary_frame(
        backtest.equity_curve,
        positions=backtest.positions,
        trades=backtest.trades,
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
    )
    report = _render_report(summary, backtest.equity_curve, backtest.positions)
    result: dict[str, Any] = {
        "equity_curve": backtest.equity_curve,
        "positions": backtest.positions,
        "trades": backtest.trades,
        "summary": summary,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "equity_curve": output / "mid_trend_shadow_top10_backtest_equity.csv",
            "positions": output / "mid_trend_shadow_top10_backtest_positions.csv",
            "trades": output / "mid_trend_shadow_top10_backtest_trades.csv",
            "summary": output / "mid_trend_shadow_top10_backtest_summary.csv",
            "report": output / "mid_trend_shadow_top10_backtest_report.md",
        }
        backtest.equity_curve.to_csv(paths["equity_curve"], index=False)
        backtest.positions.to_csv(paths["positions"], index=False)
        backtest.trades.to_csv(paths["trades"], index=False)
        summary.to_csv(paths["summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _scores_from_shadow_top10(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total"])
    scores = frame.copy()
    scores["trade_date"] = pd.to_datetime(scores["trade_date"], errors="coerce").dt.date.astype(str)
    scores["asset_id"] = scores["asset_id"].astype(str)
    scores["rank"] = pd.to_numeric(scores.get("shadow_top10_rank"), errors="coerce")
    if "mid_trend_funnel_score" in scores.columns:
        scores["score_total"] = pd.to_numeric(scores["mid_trend_funnel_score"], errors="coerce")
    else:
        scores["score_total"] = 100.0 - scores["rank"]
    return scores[["trade_date", "asset_id", "rank", "score_total"]].dropna(subset=["trade_date", "asset_id", "rank"])


def _summary_frame(
    equity: pd.DataFrame,
    *,
    positions: pd.DataFrame,
    trades: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n: int,
    rebalance_frequency: str,
    transaction_cost_bps: float,
    adjust_type: str,
) -> pd.DataFrame:
    if equity.empty:
        metrics = {
            "start_date": start_date,
            "end_date": end_date,
            "top_n": top_n,
            "rebalance_frequency": rebalance_frequency,
            "transaction_cost_bps": transaction_cost_bps,
            "adjust_type": adjust_type,
            "periods": 0,
            "total_return": 0.0,
            "annualized_return": 0.0,
            "annualized_volatility": 0.0,
            "sharpe_ratio": np.nan,
            "max_drawdown": 0.0,
            "calmar_ratio": np.nan,
            "daily_win_rate": np.nan,
            "average_turnover": 0.0,
            "total_transaction_cost": 0.0,
            "position_rows": len(positions),
            "trade_rows": len(trades),
        }
    else:
        returns = pd.to_numeric(equity["net_return"], errors="coerce").dropna()
        periods = int(len(equity))
        total_return = float(equity.iloc[-1]["equity"]) - 1.0
        annualized_return = (1.0 + total_return) ** (252.0 / periods) - 1.0 if periods > 0 and total_return > -1 else np.nan
        annualized_volatility = float(returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 else np.nan
        sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 and returns.std(ddof=1) else np.nan
        max_drawdown = float(pd.to_numeric(equity["drawdown"], errors="coerce").min())
        metrics = {
            "start_date": start_date,
            "end_date": end_date,
            "actual_start_date": str(equity.iloc[0]["date"]),
            "actual_end_date": str(equity.iloc[-1]["date"]),
            "top_n": top_n,
            "rebalance_frequency": rebalance_frequency,
            "transaction_cost_bps": transaction_cost_bps,
            "adjust_type": adjust_type,
            "periods": periods,
            "final_equity": float(equity.iloc[-1]["equity"]),
            "total_return": total_return,
            "annualized_return": annualized_return,
            "annualized_volatility": annualized_volatility,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_drawdown,
            "calmar_ratio": annualized_return / abs(max_drawdown) if max_drawdown < 0 else np.nan,
            "daily_win_rate": float((returns > 0).mean()) if not returns.empty else np.nan,
            "average_turnover": float(pd.to_numeric(equity["turnover"], errors="coerce").mean()),
            "total_transaction_cost": float(pd.to_numeric(equity["transaction_cost"], errors="coerce").sum()),
            "position_rows": len(positions),
            "trade_rows": len(trades),
        }
    return pd.DataFrame([{"metric": key, "value": value} for key, value in metrics.items()])


def _render_report(summary: pd.DataFrame, equity: pd.DataFrame, positions: pd.DataFrame) -> str:
    lines = [
        "# Mid Trend Shadow Top10 Backtest",
        "",
        "## 1. Scope",
        "这是 shadow 观察池的历史组合诊断，不是交易建议，不接实盘。",
        "",
        "## 2. Summary",
        summary.to_markdown(index=False),
        "",
        "## 3. Coverage",
        f"- equity rows: {len(equity)}",
        f"- position rows: {len(positions)}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _load_prices(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str,
    service: str,
) -> pd.DataFrame:
    sql = """
        SELECT
            trade_date,
            asset_id,
            open,
            close,
            amount,
            trade_status,
            false AS is_limit_up,
            false AS is_limit_down,
            false AS is_suspended
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date])
    return pd.DataFrame(rows)
