from __future__ import annotations

import json
import os
import subprocess
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


MARKET_REFRESH_STEPS = [
    "sync_core_assets",
    "load_market_bars",
    "check_market_data_freshness",
    "build_asset_status",
    "sync_index_bars",
    "sync_index_constituents",
    "sync_industry_memberships",
    "build_industry_bars",
]


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
        "label_start_date": _date_minus_days(trade_date, 90),
    }


def _daily_incremental_command(
    *,
    python: str,
    trade_date: str,
    only_step: str,
    apply_schema: bool = False,
    label_start_date: str | None = None,
) -> list[str]:
    command = [
        python,
        "-m",
        "stock_research.cli",
        "run-daily-incremental",
        "--trade-date",
        trade_date,
        "--only-step",
        only_step,
        "--record-run",
    ]
    if apply_schema:
        command.append("--apply-daily-run-schema")
    if label_start_date:
        command.extend(["--label-start-date", label_start_date])
    return command


def _load_market_bars_command(*, python: str, trade_date: str) -> list[str]:
    return [
        python,
        "-m",
        "stock_research.cli",
        "load-bars",
        "--start-date",
        trade_date,
        "--end-date",
        trade_date,
        "--archive-raw",
    ]


def _minute_incremental_plan_command(
    *,
    python: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
) -> list[str]:
    return [
        python,
        "-m",
        "stock_research.cli",
        "plan-baostock-minute-backfill",
        "--start-date",
        start_date,
        "--end-date",
        end_date,
        "--freq",
        "5min",
        "--adjust-types",
        "raw,qfq",
        "--batch-by",
        "month",
        "--output-dir",
        str(output_dir / "minute_incremental_plan"),
    ]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    return int(raw)


def build_daily_pipeline_steps(*, trade_date: str, output_dir: Path) -> list[DailyPipelineStep]:
    windows = derive_daily_windows(trade_date)
    python = "/Users/xiwei/stock_research/.venv/bin/python"
    minute_max_jobs = _env_int("STOCK_DAILY_PIPELINE_MINUTE_MAX_JOBS", 12000)
    minute_workers = _env_int("STOCK_DAILY_PIPELINE_MINUTE_WORKERS", 1)
    minute_run_timeout = _env_int("STOCK_DAILY_PIPELINE_MINUTE_RUN_TIMEOUT_SECONDS", 7200)
    steps = [
        DailyPipelineStep(name="start_report", command=[], required=False, timeout_seconds=60),
    ]
    for index, step_name in enumerate(MARKET_REFRESH_STEPS):
        command = (
            _load_market_bars_command(python=python, trade_date=trade_date)
            if step_name == "load_market_bars"
            else _daily_incremental_command(
                python=python,
                trade_date=trade_date,
                only_step=step_name,
                apply_schema=index == 0,
            )
        )
        steps.append(
            DailyPipelineStep(
                name=step_name,
                command=command,
                timeout_seconds=1200,
            )
        )
    steps.extend(
        [
            DailyPipelineStep(
                name="minute_incremental_plan",
                command=_minute_incremental_plan_command(
                    python=python,
                    start_date=windows["minute_start_date"],
                    end_date=trade_date,
                    output_dir=output_dir,
                ),
                timeout_seconds=900,
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
                    str(minute_max_jobs),
                    "--workers",
                    str(minute_workers),
                    "--run-timeout-seconds",
                    str(minute_run_timeout),
                    "--report-target",
                    "chat:oc_82dd978138a0cde5864868c5b5b8e754",
                    "--report-account",
                    "jarvis",
                    "--openclaw-bin",
                    "/Users/xiwei/stock_research/scripts/openclaw_runtime_cli.sh",
                ],
                timeout_seconds=minute_run_timeout + 300,
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
            DailyPipelineStep(
                name="label_incremental_refresh",
                command=_daily_incremental_command(
                    python=python,
                    trade_date=trade_date,
                    only_step="compute_labels",
                    label_start_date=windows["label_start_date"],
                ),
                required=False,
                timeout_seconds=900,
            ),
            DailyPipelineStep(
                name="daily_report_delivery",
                command=[],
                required=False,
                timeout_seconds=120,
            ),
        ]
    )
    return steps


def render_daily_pipeline_feishu_message(
    *,
    trade_date: str,
    status: str,
    output_dir: Path,
    step_results: list[dict[str, Any]],
) -> str:
    del output_dir
    total = len(step_results)
    completed = sum(1 for item in step_results if _is_feishu_step_ok(str(item.get("status") or "")))
    issues = [
        item
        for item in step_results
        if not _is_feishu_step_ok(str(item.get("status") or ""))
    ]
    headline = "完成" if status == "success" and not issues else "需要处理"
    lines = [
        f"A股日频数据任务 {trade_date}：{headline}",
        f"完成 {completed}/{total}；异常 {len(issues)}；总行数 {_sum_step_rows(step_results)}",
    ]

    if not issues:
        lines.append("飞书通知完成")
    else:
        lines.append("需要看：")
        for item in issues[:3]:
            lines.append(_format_feishu_issue_line(item))
        remaining = len(issues) - 3
        if remaining > 0:
            lines.append(f"- 另有 {remaining} 项异常，见 run_summary.json")
    lines.append("详情：run_summary.json")
    return "\n".join(lines)


def _is_feishu_step_ok(status: str) -> bool:
    return status in {"success", "skipped"}


def _sum_step_rows(step_results: list[dict[str, Any]]) -> int:
    total = 0
    for item in step_results:
        try:
            total += int(item.get("rows") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _format_feishu_issue_line(item: dict[str, Any]) -> str:
    step = str(item.get("step") or "unknown_step")
    status = str(item.get("status") or "unknown")
    rows = int(item.get("rows") or 0)
    line = f"- {step}：{status}，rows={rows}"
    error = _compact_feishu_error(str(item.get("error") or ""))
    if error:
        line += f"，{error}"
    return line


def _compact_feishu_error(error: str, limit: int = 80) -> str:
    compact = " ".join(error.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _default_command_runner(
    command: list[str],
    timeout_seconds: int,
    log_path: Path | None = None,
) -> dict[str, object]:
    if log_path is None:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    with log_path.open("a", encoding="utf-8") as log:
        completed = subprocess.run(
            command,
            stdout=log,
            stderr=log,
            text=True,
            timeout=timeout_seconds,
        )
    output = log_path.read_text(encoding="utf-8")
    return {
        "returncode": completed.returncode,
        "stdout": output,
        "stderr": "" if completed.returncode == 0 else output[-2000:],
    }


def _run_command(
    runner: Any,
    command: list[str],
    timeout_seconds: int,
    log_path: Path,
) -> dict[str, object]:
    try:
        return runner(command, timeout_seconds, log_path)
    except TypeError as exc:
        if "positional" not in str(exc) and "argument" not in str(exc):
            raise
        return runner(command, timeout_seconds)


def _write_step_log_header(log_path: Path, step: DailyPipelineStep) -> None:
    log_path.write_text(
        "\n".join(
            [
                f"step: {step.name}",
                f"timeout_seconds: {step.timeout_seconds}",
                "command:",
                " ".join(step.command),
                "",
            ]
        ),
        encoding="utf-8",
    )


def _append_step_log_output(
    log_path: Path,
    *,
    stdout: str,
    stderr: str,
) -> None:
    if not stdout and not stderr:
        return
    with log_path.open("a", encoding="utf-8") as log:
        if stdout:
            log.write("\n[stdout]\n")
            log.write(stdout)
            if not stdout.endswith("\n"):
                log.write("\n")
        if stderr:
            log.write("\n[stderr]\n")
            log.write(stderr)
            if not stderr.endswith("\n"):
                log.write("\n")


def _write_summary(
    *,
    output_dir: Path,
    trade_date: str,
    status: str,
    step_results: list[dict[str, Any]],
) -> None:
    summary = {
        "trade_date": trade_date,
        "status": status,
        "output_dir": str(output_dir),
        "steps": step_results,
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _current_status(required_failed: bool) -> str:
    return "partial_failed" if required_failed else "success"


def _step_log_path(output_dir: Path, step_name: str) -> Path:
    return output_dir / "logs" / f"{step_name}.log"


def _step_rows(stdout: str) -> int:
    rows = 0
    for token in stdout.replace("\n", "|").split("|"):
        if token.isdigit():
            rows = int(token)
    return rows


def _output_marks_failure(output: str) -> bool:
    for line in output.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 3 and parts[-1] == "failed":
            if parts[1] == "status" or parts[0].endswith("_step"):
                return True
    return False


def _failure_error(stdout: str, stderr: str) -> str:
    output = stderr or stdout
    for line in stdout.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 4 and parts[0].endswith("_step_error"):
            return parts[-1][-500:]
    return output[-500:]


def run_stock_daily_data_pipeline(
    *,
    trade_date: str,
    output_dir: str | Path,
    command_runner: Any = None,
    feishu_sender: Any = None,
    send_feishu: bool = True,
) -> dict[str, Any]:
    resolved_output_dir = Path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    (resolved_output_dir / "logs").mkdir(parents=True, exist_ok=True)
    runner = command_runner or _default_command_runner
    steps = build_daily_pipeline_steps(trade_date=trade_date, output_dir=resolved_output_dir)
    step_results: list[dict[str, Any]] = []
    required_failed = False

    for step in steps:
        if step.name == "daily_report_delivery":
            continue
        if not step.command:
            step_results.append(
                {"step": step.name, "status": "skipped", "rows": 0, "error": ""}
            )
            _write_summary(
                output_dir=resolved_output_dir,
                trade_date=trade_date,
                status=_current_status(required_failed),
                step_results=step_results,
            )
            continue
        if required_failed:
            step_results.append(
                {
                    "step": step.name,
                    "status": "skipped_dependency_failed",
                    "rows": 0,
                    "error": "upstream required step failed",
                }
            )
            _write_summary(
                output_dir=resolved_output_dir,
                trade_date=trade_date,
                status=_current_status(required_failed),
                step_results=step_results,
            )
            continue
        try:
            log_path = _step_log_path(resolved_output_dir, step.name)
            _write_step_log_header(log_path, step)
            running_result = {
                "step": step.name,
                "status": "running",
                "rows": 0,
                "error": "",
                "log_path": str(log_path),
            }
            _write_summary(
                output_dir=resolved_output_dir,
                trade_date=trade_date,
                status="running",
                step_results=[*step_results, running_result],
            )
            outcome = _run_command(runner, step.command, step.timeout_seconds, log_path)
            returncode = int(outcome.get("returncode", 1))
            stdout = str(outcome.get("stdout", ""))
            stderr = str(outcome.get("stderr", ""))
            if command_runner is not None:
                _append_step_log_output(log_path, stdout=stdout, stderr=stderr)
            output_failed = _output_marks_failure(stdout)
            status = "success" if returncode == 0 and not output_failed else "failed"
            step_results.append(
                {
                    "step": step.name,
                    "status": status,
                    "rows": _step_rows(stdout),
                    "error": "" if status == "success" else _failure_error(stdout, stderr),
                    "returncode": returncode,
                    "log_path": str(log_path),
                }
            )
            if step.required and status == "failed":
                required_failed = True
            _write_summary(
                output_dir=resolved_output_dir,
                trade_date=trade_date,
                status=_current_status(required_failed),
                step_results=step_results,
            )
        except Exception as exc:
            log_path = _step_log_path(resolved_output_dir, step.name)
            step_results.append(
                {
                    "step": step.name,
                    "status": "failed",
                    "rows": 0,
                    "error": str(exc),
                    "returncode": 1,
                    "log_path": str(log_path),
                }
            )
            if step.required:
                required_failed = True
            _write_summary(
                output_dir=resolved_output_dir,
                trade_date=trade_date,
                status=_current_status(required_failed),
                step_results=step_results,
            )

    status = "partial_failed" if required_failed else "success"
    delivery_result = {
        "step": "daily_report_delivery",
        "status": "skipped",
        "rows": 0,
        "error": "",
    }
    if send_feishu and feishu_sender is not None:
        delivery_result["status"] = "success"
        step_results.append(delivery_result)
        message = render_daily_pipeline_feishu_message(
            trade_date=trade_date,
            status=status,
            output_dir=resolved_output_dir,
            step_results=step_results,
        )
        try:
            feishu_sender(message)
        except Exception as exc:
            delivery_result["status"] = "failed"
            delivery_result["error"] = str(exc)
            status = "partial_failed"
    else:
        step_results.append(delivery_result)

    summary = {
        "trade_date": trade_date,
        "status": status,
        "output_dir": str(resolved_output_dir),
        "steps": step_results,
    }
    message = render_daily_pipeline_feishu_message(
        trade_date=trade_date,
        status=status,
        output_dir=resolved_output_dir,
        step_results=step_results,
    )
    _write_summary(
        output_dir=resolved_output_dir,
        trade_date=trade_date,
        status=status,
        step_results=step_results,
    )
    (resolved_output_dir / "feishu_message.txt").write_text(message + "\n", encoding="utf-8")
    return summary
