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
    equity_curve_path = reports_path / f"{stem}_equity.csv"
    positions_path = reports_path / f"{stem}_positions.csv"

    metrics = calc_performance_metrics(
        result.equity_curve,
        result.positions,
        annualization=annualization,
    )
    metrics_frame = pd.DataFrame(
        [{"metric": key, "value": value} for key, value in metrics.items()]
    )
    metrics_frame.to_csv(metrics_path, index=False)
    result.equity_curve.to_csv(equity_curve_path, index=False)
    result.positions.to_csv(positions_path, index=False)
    report_path.write_text(
        _render_markdown(
            strategy_id=strategy_id,
            start_date=start,
            end_date=end,
            result=result,
            metrics=metrics,
            metrics_path=metrics_path,
            equity_curve_path=equity_curve_path,
            positions_path=positions_path,
        ),
        encoding="utf-8",
    )

    return {
        "report_path": str(report_path),
        "metrics_path": str(metrics_path),
        "equity_curve_path": str(equity_curve_path),
        "positions_path": str(positions_path),
    }


def _render_markdown(
    strategy_id: str,
    start_date: str,
    end_date: str,
    result: VectorizedTopNResult,
    metrics: dict[str, Any],
    metrics_path: Path,
    equity_curve_path: Path,
    positions_path: Path,
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
            "## Files",
            "",
            f"- Metrics CSV: `{metrics_path}`",
            f"- Equity CSV: `{equity_curve_path}`",
            f"- Positions CSV: `{positions_path}`",
            "",
        ]
    )
    return "\n".join(lines)


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
