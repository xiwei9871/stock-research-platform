from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

TOP10_DIR = Path("outputs/research/current_mid_trend_strategy_v2_top10_candidate_20250101_20260612")
V1_DIR = Path("outputs/research/current_mid_trend_strategy_v1_20250101_20260612_retest")


def run_midtrend_top10_stability_validation_cli(*, output_dir: str | Path) -> dict[str, Any]:
    return run_midtrend_top10_stability_validation_from_frames(
        equity=_optional_csv(TOP10_DIR / "current_mid_trend_strategy_v2_top10_candidate_equity.csv"),
        holdings=_optional_csv(TOP10_DIR / "current_mid_trend_strategy_v2_top10_candidate_daily_holdings.csv"),
        trades=_optional_csv(TOP10_DIR / "current_mid_trend_strategy_v2_top10_candidate_trade_changes.csv"),
        v1_equity=_optional_csv_first(
            [
                V1_DIR / "current_mid_trend_strategy_v1_equity.csv",
                V1_DIR / "equity.csv",
            ]
        ),
        output_dir=output_dir,
    )


def run_midtrend_top10_stability_validation_from_frames(
    *,
    equity: pd.DataFrame,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    v1_equity: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    tables = build_top10_stability_tables(equity=equity, holdings=holdings, trades=trades)
    tables["monthly"].to_csv(output / "top10_monthly_stability.csv", index=False)
    tables["quarterly"].to_csv(output / "top10_quarterly_stability.csv", index=False)
    tables["regime"].to_csv(output / "top10_regime_stability.csv", index=False)
    tables["industry"].to_csv(output / "top10_industry_stability.csv", index=False)
    tables["slot"].to_csv(output / "top10_slot_stability.csv", index=False)
    tables["winner_dependency"].to_csv(output / "top10_winner_dependency.csv", index=False)
    comparison = _top10_vs_v1_summary(equity, v1_equity)
    comparison.to_csv(output / "top10_vs_v1_stability_summary.csv", index=False)
    _run_params().to_csv(output / "run_params.csv", index=False)
    (output / "code_audit.md").write_text(_code_audit(), encoding="utf-8")
    (output / "final_interpretation.md").write_text(
        _final_interpretation(tables, comparison),
        encoding="utf-8",
    )
    return {"paths": {"output_dir": str(output)}}


def build_top10_stability_tables(
    *,
    equity: pd.DataFrame,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    eq = _prepare_equity(equity)
    monthly = _period_table(eq, "M")
    quarterly = _period_table(eq, "Q")
    holdings_prepared = holdings.copy()
    if not holdings_prepared.empty:
        holdings_prepared["trade_date"] = _date(holdings_prepared["trade_date"])
    trades_prepared = trades.copy()
    if not trades_prepared.empty:
        trades_prepared["trade_date"] = _date(trades_prepared["trade_date"])
        trades_prepared["contribution"] = _contribution(trades_prepared)
    return {
        "monthly": monthly,
        "quarterly": quarterly,
        "regime": _group_holdings(holdings_prepared, "confirmed_regime_state"),
        "industry": _group_trades(trades_prepared, "industry_name"),
        "slot": _slot_table(holdings_prepared, trades_prepared),
        "winner_dependency": _winner_dependency(trades_prepared),
    }


def _prepare_equity(equity: pd.DataFrame) -> pd.DataFrame:
    frame = equity.copy()
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "equity", "daily_return"])
    frame["trade_date"] = _date(frame["trade_date"])
    if "daily_return" not in frame.columns:
        frame["daily_return"] = _num(frame["equity"]).pct_change().fillna(0)
    return frame.sort_values("trade_date")


def _period_table(equity: pd.DataFrame, freq: str) -> pd.DataFrame:
    if equity.empty:
        return pd.DataFrame(columns=["period", "start_equity", "end_equity", "period_return", "max_drawdown"])
    frame = equity.copy()
    frame["period"] = pd.to_datetime(frame["trade_date"]).dt.to_period(freq).astype(str)
    rows = []
    for period, part in frame.groupby("period"):
        values = _num(part["equity"])
        rows.append(
            {
                "period": period,
                "start_equity": float(values.iloc[0]),
                "end_equity": float(values.iloc[-1]),
                "period_return": float(values.iloc[-1] / values.iloc[0] - 1) if values.iloc[0] else np.nan,
                "max_drawdown": _max_drawdown(values),
                "trading_days": int(len(part)),
            }
        )
    return pd.DataFrame(rows)


def _group_holdings(holdings: pd.DataFrame, column: str) -> pd.DataFrame:
    if holdings.empty or column not in holdings.columns:
        return pd.DataFrame(columns=[column, "holding_rows", "avg_holding_count", "avg_weight"])
    grouped = holdings.groupby(column, dropna=False)
    return grouped.agg(
        holding_rows=("asset_id", "count"),
        avg_holding_count=("asset_id", lambda value: len(value) / max(holdings["trade_date"].nunique(), 1)),
        avg_weight=("target_weight", "mean") if "target_weight" in holdings.columns else ("asset_id", "count"),
    ).reset_index()


def _group_trades(trades: pd.DataFrame, column: str) -> pd.DataFrame:
    if trades.empty or column not in trades.columns:
        return pd.DataFrame(columns=[column, "trade_count", "total_contribution", "winner_rate"])
    grouped = trades.groupby(column, dropna=False)
    return grouped.agg(
        trade_count=("asset_id", "count"),
        total_contribution=("contribution", "sum"),
        winner_rate=("contribution", lambda value: float((value > 0).mean()) if len(value) else 0.0),
    ).reset_index().sort_values("total_contribution", ascending=False)


def _slot_table(holdings: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    source = holdings if not holdings.empty else trades
    if source.empty:
        return pd.DataFrame(columns=["slot_bucket", "sample_count"])
    frame = source.copy()
    rank_col = "final_slot_rank" if "final_slot_rank" in frame.columns else "score_rank"
    rank = _num(frame.get(rank_col, pd.Series(np.nan, index=frame.index)))
    frame["slot_bucket"] = np.select(
        [rank.le(5), rank.between(6, 10), rank.gt(10)],
        ["slot_1_to_5", "slot_6_to_10", "slot_gt10"],
        default="slot_unknown",
    )
    if "contribution" not in frame.columns:
        frame["contribution"] = _contribution(frame)
    return _group_trades(frame, "slot_bucket").rename(columns={"trade_count": "sample_count"})


def _winner_dependency(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame([{"sample_count": 0, "top_1_winner_contribution": 0.0, "top_5_winner_contribution": 0.0}])
    contribution = _contribution(trades).sort_values(ascending=False)
    total = float(contribution.sum())
    return pd.DataFrame(
        [
            {
                "sample_count": int(len(contribution)),
                "total_contribution": total,
                "top_1_winner_contribution": float(contribution.head(1).sum()),
                "top_5_winner_contribution": float(contribution.head(5).sum()),
                "top_10_winner_contribution": float(contribution.head(10).sum()),
                "top_1_share": float(contribution.head(1).sum() / total) if total else np.nan,
                "top_5_share": float(contribution.head(5).sum() / total) if total else np.nan,
            }
        ]
    )


def _top10_vs_v1_summary(top10_equity: pd.DataFrame, v1_equity: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"strategy": "top10_candidate", **_equity_metrics(top10_equity)},
            {"strategy": "v1_top5_reference", **_equity_metrics(v1_equity)},
        ]
    )


def _equity_metrics(equity: pd.DataFrame) -> dict[str, Any]:
    frame = _prepare_equity(equity)
    if frame.empty:
        return {"total_return": np.nan, "max_drawdown": np.nan, "trading_days": 0}
    values = _num(frame["equity"])
    return {
        "total_return": float(values.iloc[-1] / values.iloc[0] - 1) if values.iloc[0] else np.nan,
        "max_drawdown": _max_drawdown(values),
        "trading_days": int(len(frame)),
    }


def _contribution(frame: pd.DataFrame) -> pd.Series:
    for column in ["contribution", "forward_return", "trade_return"]:
        if column in frame.columns:
            values = _num(frame[column])
            break
    else:
        values = pd.Series(0.0, index=frame.index)
    weight = _num(frame.get("target_weight", pd.Series(1.0, index=frame.index))).fillna(1.0)
    return values.fillna(0) * weight


def _max_drawdown(values: pd.Series) -> float:
    running = values.cummax()
    dd = values / running - 1
    return float(dd.min()) if len(dd) else np.nan


def _date(value: Any) -> pd.Series:
    return pd.to_datetime(value, errors="coerce").dt.strftime("%Y-%m-%d")


def _num(value: Any) -> pd.Series:
    return pd.to_numeric(value, errors="coerce")


def _run_params() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"param": "top10_dir", "value": str(TOP10_DIR)},
            {"param": "v1_dir", "value": str(V1_DIR)},
            {"param": "strategy_changes", "value": "none"},
        ]
    )


def _code_audit() -> str:
    return "\n".join(
        [
            "# Code Audit",
            "",
            "- runner: `stock_research.midtrend_top10_stability_validation_v1`",
            "- consumes accepted top10 candidate artifacts",
            "- produces stability diagnostics only",
            "- no trading strategy logic changed",
        ]
    ) + "\n"


def _final_interpretation(tables: dict[str, pd.DataFrame], comparison: pd.DataFrame) -> str:
    winner = tables["winner_dependency"].iloc[0] if not tables["winner_dependency"].empty else {}
    lines = [
        "# Final Interpretation",
        "",
        "1. This validation checks top10 stability by month, quarter, regime, industry, slot, and winner dependency.",
        "2. It does not change top10 strategy rules.",
        f"3. Winner dependency top_1_share: {winner.get('top_1_share', np.nan)}.",
        "4. Use these diagnostics before any position sizing or industry cap experiment.",
        "",
        comparison.to_markdown(index=False) if not comparison.empty else "",
    ]
    return "\n".join(lines) + "\n"


def _optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _optional_csv_first(paths: list[Path]) -> pd.DataFrame:
    for path in paths:
        if path.exists():
            return pd.read_csv(path, low_memory=False)
    return pd.DataFrame()
