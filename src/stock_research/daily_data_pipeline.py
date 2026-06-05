from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DailyPipelineStep:
    name: str
    command: list[str]
    required: bool = True
    timeout_seconds: int = 1800


def _date_minus_days(value: str, days: int) -> str:
    parsed = date.fromisoformat(value)
    return (parsed - timedelta(days=days)).isoformat()


def derive_daily_windows(trade_date: str) -> dict[str, str]:
    return {
        "trade_date": trade_date,
        "market_start_date": _date_minus_days(trade_date, 5),
        "minute_start_date": _date_minus_days(trade_date, 5),
        "lhb_start_date": _date_minus_days(trade_date, 10),
        "announcement_start_date": _date_minus_days(trade_date, 14),
        "earnings_start_date": _date_minus_days(trade_date, 45),
        "repurchase_start_date": _date_minus_days(trade_date, 90),
    }


def build_daily_pipeline_steps(*, trade_date: str, output_dir: Path) -> list[DailyPipelineStep]:
    windows = derive_daily_windows(trade_date)
    python = "./.venv/bin/python"
    return [
        DailyPipelineStep(name="start_report", command=[], required=False, timeout_seconds=60),
        DailyPipelineStep(
            name="market_daily_refresh",
            command=[
                python,
                "-m",
                "stock_research.cli",
                "run-daily-incremental",
                "--trade-date",
                trade_date,
                "--record-run",
                "--apply-daily-run-schema",
            ],
            timeout_seconds=3600,
        ),
        DailyPipelineStep(
            name="minute_incremental_refresh",
            command=[
                python,
                "-m",
                "stock_research.cli",
                "backfill-watchdog",
                "--adapter",
                "minute",
                "--start-date",
                windows["minute_start_date"],
                "--end-date",
                trade_date,
                "--freq",
                "5min",
                "--adjust-types",
                "raw,qfq",
                "--max-jobs",
                "400",
                "--workers",
                "4",
                "--run-timeout-seconds",
                "1800",
                "--report-target",
                "chat:oc_82dd978138a0cde5864868c5b5b8e754",
                "--report-account",
                "jarvis",
                "--openclaw-bin",
                "/Users/xiwei/stock_research/scripts/openclaw_runtime_cli.sh",
            ],
            timeout_seconds=2100,
        ),
        DailyPipelineStep(
            name="daily_event_refresh",
            command=[
                python,
                "-m",
                "stock_research.cli",
                "free-enrichment-backfill",
                "--dataset",
                "lhb",
                "--start-date",
                windows["lhb_start_date"],
                "--end-date",
                trade_date,
                "--output-dir",
                str(output_dir / "free_enrichment_lhb"),
                "--batch-size",
                "1",
                "--sleep-seconds",
                "0",
            ],
            timeout_seconds=1800,
        ),
        DailyPipelineStep(
            name="daily_feature_build",
            command=[
                python,
                "-m",
                "stock_research.cli",
                "run-daily-factor-pipeline",
                "--trade-date",
                trade_date,
                "--reports-dir",
                str(output_dir / "reports"),
            ],
            timeout_seconds=1800,
        ),
        DailyPipelineStep(name="daily_report_delivery", command=[], required=False, timeout_seconds=120),
    ]


def render_daily_pipeline_feishu_message(
    *,
    trade_date: str,
    status: str,
    output_dir: Path,
    step_results: list[dict[str, Any]],
) -> str:
    lines = [
        f"A股日频数据任务 {trade_date}",
        f"status: {status}",
        f"output: {output_dir}",
        "",
        "steps:",
    ]
    for item in step_results:
        line = f"- {item['step']}: {item['status']} rows={item.get('rows', 0)}"
        if item.get("error"):
            line += f" error={item['error']}"
        lines.append(line)
    return "\n".join(lines)
