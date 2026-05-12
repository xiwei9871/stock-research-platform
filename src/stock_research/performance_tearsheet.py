from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.performance_metrics import calc_performance_metrics
from stock_research.vectorized_topn_backtest import VectorizedTopNResult


def write_performance_tearsheet(
    result: VectorizedTopNResult,
    strategy_id: str,
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    annualization: int = 252,
) -> dict[str, str]:
    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)

    start = _iso_date(result.config.start_date)
    end = _iso_date(result.config.end_date)
    safe_strategy = _safe_filename(strategy_id)
    stem = f"{safe_strategy}_{start}_{end}_tearsheet"

    report_path = reports_path / f"{stem}.md"
    metrics_path = reports_path / f"{stem}_metrics.csv"
    subperiod_metrics_path = reports_path / f"{stem}_subperiod_metrics.csv"
    regime_metrics_path = reports_path / f"{stem}_regime_metrics.csv"
    equity_curve_path = reports_path / f"{stem}_equity.csv"
    positions_path = reports_path / f"{stem}_positions.csv"
    trades_path = reports_path / f"{stem}_trades.csv"

    metrics = calc_performance_metrics(
        result.equity_curve,
        result.positions,
        annualization=annualization,
    )
    metrics_frame = pd.DataFrame(
        [{"metric": key, "value": value} for key, value in metrics.items()]
    )
    metrics_frame.to_csv(metrics_path, index=False)
    _write_subperiod_metrics(result.equity_curve, subperiod_metrics_path, annualization)
    _write_regime_metrics(result.equity_curve, regime_metrics_path, annualization)
    result.equity_curve.to_csv(equity_curve_path, index=False)
    result.positions.to_csv(positions_path, index=False)
    trades = getattr(result, "trades", pd.DataFrame())
    trades.to_csv(trades_path, index=False)
    report_path.write_text(
        _render_markdown(
            strategy_id=strategy_id,
            start_date=start,
            end_date=end,
            result=result,
            metrics=metrics,
            metrics_path=metrics_path,
            subperiod_metrics_path=subperiod_metrics_path,
            regime_metrics_path=regime_metrics_path,
            equity_curve_path=equity_curve_path,
            positions_path=positions_path,
            trades_path=trades_path,
        ),
        encoding="utf-8",
    )

    return {
        "report_path": str(report_path),
        "metrics_path": str(metrics_path),
        "subperiod_metrics_path": str(subperiod_metrics_path),
        "regime_metrics_path": str(regime_metrics_path),
        "equity_curve_path": str(equity_curve_path),
        "positions_path": str(positions_path),
        "trades_path": str(trades_path),
    }


def _render_markdown(
    strategy_id: str,
    start_date: str,
    end_date: str,
    result: VectorizedTopNResult,
    metrics: dict[str, Any],
    metrics_path: Path,
    subperiod_metrics_path: Path,
    regime_metrics_path: Path,
    equity_curve_path: Path,
    positions_path: Path,
    trades_path: Path,
) -> str:
    lines = [
        "# Performance Tear Sheet",
        "",
        "仅作为研究验证，不构成交易指令。",
        "",
        "## Config",
        "",
        f"- Strategy: `{strategy_id}`",
        f"- Period: `{start_date}` to `{end_date}`",
        f"- TopN: `{result.config.top_n}`",
        f"- Rebalance: `{result.config.rebalance_frequency}`",
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key, value in metrics.items():
        lines.append(f"| {key} | {_format_value(value)} |")

    lines.extend(
        [
            "",
            "## Subperiod Metrics",
            "",
            f"- Subperiod CSV: `{subperiod_metrics_path}`",
            "",
            "## Regime Metrics",
            "",
            f"- Regime CSV: `{regime_metrics_path}`",
            "",
            "## Files",
            "",
            f"- Metrics CSV: `{metrics_path}`",
            f"- Equity CSV: `{equity_curve_path}`",
            f"- Positions CSV: `{positions_path}`",
            f"- Trades CSV: `{trades_path}`",
            "",
        ]
    )
    return "\n".join(lines)


def _write_subperiod_metrics(
    equity_curve: pd.DataFrame,
    output_path: Path,
    annualization: int,
) -> None:
    rows: list[dict[str, object]] = []
    if equity_curve.empty or "date" not in equity_curve.columns:
        pd.DataFrame(columns=["period", "metric", "value"]).to_csv(
            output_path,
            index=False,
        )
        return

    frame = equity_curve.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    for year, period_frame in frame.groupby(frame["date"].dt.year):
        metrics = calc_performance_metrics(
            period_frame,
            pd.DataFrame(),
            annualization=annualization,
        )
        for key, value in metrics.items():
            rows.append({"period": str(year), "metric": key, "value": value})
    pd.DataFrame(rows, columns=["period", "metric", "value"]).to_csv(
        output_path,
        index=False,
    )


def _write_regime_metrics(
    equity_curve: pd.DataFrame,
    output_path: Path,
    annualization: int,
) -> None:
    if equity_curve.empty or "net_return" not in equity_curve.columns:
        pd.DataFrame(columns=["regime", "metric", "value"]).to_csv(
            output_path,
            index=False,
        )
        return

    frame = equity_curve.copy()
    frame["net_return"] = pd.to_numeric(frame["net_return"], errors="coerce")
    regimes = {
        "up_days": frame[frame["net_return"] > 0],
        "down_days": frame[frame["net_return"] <= 0],
    }
    rows: list[dict[str, object]] = []
    for regime, regime_frame in regimes.items():
        rows.append(
            {"regime": regime, "metric": "days", "value": int(len(regime_frame))}
        )
        rows.append(
            {
                "regime": regime,
                "metric": "mean_net_return",
                "value": (
                    float(regime_frame["net_return"].mean())
                    if not regime_frame.empty
                    else None
                ),
            }
        )
        metrics = calc_performance_metrics(
            regime_frame,
            pd.DataFrame(),
            annualization=annualization,
        )
        rows.append(
            {
                "regime": regime,
                "metric": "cumulative_return",
                "value": metrics.get("cumulative_return"),
            }
        )
    pd.DataFrame(rows, columns=["regime", "metric", "value"]).to_csv(
        output_path,
        index=False,
    )


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)


def _format_value(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)
