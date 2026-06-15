from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.data_run_manifest import build_manifest_entry, summarize_manifest_modules


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

STEP_MODULES = {
    "start_report": ("generated_reports", "reports", "tier2"),
    "sync_core_assets": ("assets_universe", "core_assets", "tier1"),
    "load_market_bars": ("daily_bars", "market_daily_bar", "tier1"),
    "check_market_data_freshness": ("trading_calendar", "market_calendar", "tier1"),
    "build_asset_status": ("assets_universe", "core_asset_status", "tier1"),
    "sync_index_bars": ("daily_bars", "market_index_daily_bar", "tier1"),
    "sync_index_constituents": ("assets_universe", "index_constituents", "tier1"),
    "sync_industry_memberships": ("industry", "industry_membership", "tier2"),
    "build_industry_bars": ("industry", "industry_bars", "tier2"),
    "minute_incremental_refresh": ("minute_bars", "minute_backfill", "tier3"),
    "daily_event_refresh": ("lhb", "free_enrichment_lhb", "tier2"),
    "daily_feature_build": ("factor_pipeline", "factor_pipeline", "tier1"),
    "label_incremental_refresh": ("experimental_enrichment", "labels", "tier3"),
    "daily_report_delivery": ("generated_reports", "reports", "tier2"),
}

SYNTHETIC_MODULES = [
    ("score_topn", "factor.stock_score_daily", "tier1"),
    ("review_queue", "dashboard.review_queue", "tier1"),
    ("news", "research.news_event_source", "tier2"),
    ("research_reports", "research.stock_report_source", "tier2"),
    ("financial", "finance", "tier2"),
    ("technical_features", "factor.stock_technical_features_daily", "tier2"),
    ("intraday", "market.stock_minute_bar", "tier3"),
    ("auction", "auction", "tier3"),
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


def build_daily_pipeline_steps(*, trade_date: str, output_dir: Path) -> list[DailyPipelineStep]:
    windows = derive_daily_windows(trade_date)
    python = "/Users/xiwei/stock_research/.venv/bin/python"
    steps = [
        DailyPipelineStep(name="start_report", command=[], required=False, timeout_seconds=60),
    ]
    for index, step_name in enumerate(MARKET_REFRESH_STEPS):
        steps.append(
            DailyPipelineStep(
                name=step_name,
                command=_daily_incremental_command(
                    python=python,
                    trade_date=trade_date,
                    only_step=step_name,
                    apply_schema=index == 0,
                ),
                timeout_seconds=1200,
            )
        )
    steps.extend(
        [
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
                required=False,
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
    run_id = _run_id(trade_date)
    modules = _build_manifest_modules(run_id=run_id, trade_date=trade_date, step_results=step_results)
    manifest_summary = summarize_manifest_modules(modules)
    artifacts = _artifact_index(step_results)
    summary = {
        "run_id": run_id,
        "run_date": _today_shanghai(),
        "latest_market_date": trade_date,
        "started_at": _first_started_at(modules),
        "ended_at": _now_shanghai(),
        "trade_date": trade_date,
        "status": manifest_summary["status"],
        "legacy_status": status,
        "tier1_status": manifest_summary["tier1_status"],
        "tier2_status": manifest_summary["tier2_status"],
        "tier3_status": manifest_summary["tier3_status"],
        "output_dir": str(output_dir),
        "modules": modules,
        "steps": step_results,
        "assets_count": _module_rows(modules, "assets_universe"),
        "daily_bar_rows": _module_rows(modules, "daily_bars"),
        "factor_rows": _module_rows(modules, "factor_pipeline"),
        "score_version": "manual_v1",
        "topn_generated": _module_status(modules, "score_topn") == "success",
        "topn_count": _module_rows(modules, "score_topn"),
        "review_queue_count": _module_rows(modules, "review_queue"),
        "evidence_digest_count": 0,
        "news_count": _module_rows(modules, "news"),
        "report_count": _module_rows(modules, "research_reports"),
        "lhb_count": _module_rows(modules, "lhb"),
        "warning_count": len(manifest_summary["warnings"]),
        "warnings": manifest_summary["warnings"],
        "errors": manifest_summary["errors"],
        "missing_data": manifest_summary["missing_data"],
        "partial_data": manifest_summary["partial_data"],
        "artifacts": artifacts,
        "readiness_status": manifest_summary["status"],
        "dashboard_readiness_url": "http://127.0.0.1:8765/api/platform/readiness",
    }
    manifest_payload = {
        "run_id": run_id,
        "run_date": summary["run_date"],
        "trade_date": trade_date,
        "latest_market_date": trade_date,
        "status": manifest_summary["status"],
        "modules": modules,
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _current_status(required_failed: bool) -> str:
    return "partial_failed" if required_failed else "success"


def _legacy_status(step_results: list[dict[str, Any]]) -> str:
    for step in step_results:
        if step.get("status") != "failed":
            continue
        if step.get("step") in {"label_incremental_refresh"}:
            continue
        return "partial_failed"
    return "success"


def _run_id(trade_date: str) -> str:
    return f"eod-{trade_date}-local"


def _today_shanghai() -> str:
    return _now_shanghai()[:10]


def _now_shanghai() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _build_manifest_modules(
    *,
    run_id: str,
    trade_date: str,
    step_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    modules = [
        _manifest_for_step(run_id=run_id, trade_date=trade_date, step=step)
        for step in step_results
    ]
    modules.extend(_synthetic_modules(run_id=run_id, trade_date=trade_date, modules=modules))
    return modules


def _manifest_for_step(
    *,
    run_id: str,
    trade_date: str,
    step: dict[str, Any],
) -> dict[str, Any]:
    module, source, tier = STEP_MODULES.get(
        str(step.get("step") or ""),
        (str(step.get("step") or "unknown"), str(step.get("step") or "unknown"), "tier3"),
    )
    status = _manifest_status(step)
    error = str(step.get("error") or "")
    warnings = [error] if status in {"partial", "failed", "unavailable"} and error else []
    return build_manifest_entry(
        run_id=run_id,
        run_date=_today_shanghai(),
        trade_date=trade_date,
        module=module,
        source=source,
        tier=tier,
        status=status,
        started_at=step.get("started_at"),
        ended_at=step.get("ended_at"),
        row_count=int(step.get("rows") or 0),
        latest_trade_date=trade_date if status == "success" else None,
        warnings=warnings,
        error_message=error,
        artifact_path=step.get("log_path") or "",
        metadata={"step": step.get("step"), "returncode": step.get("returncode")},
    )


def _synthetic_modules(
    *,
    run_id: str,
    trade_date: str,
    modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    factor_rows = _module_rows(modules, "factor_pipeline")
    lhb_rows = _module_rows(modules, "lhb")
    minute_rows = _module_rows(modules, "minute_bars")
    score_status = "success" if factor_rows > 0 else "unavailable"
    score_rows = factor_rows if factor_rows > 0 else 0
    synthetic: list[dict[str, Any]] = []
    for module, source, tier in SYNTHETIC_MODULES:
        status = "skipped"
        row_count = 0
        warnings: list[str] = []
        if module in {"score_topn", "review_queue"}:
            status = score_status
            row_count = min(score_rows, 30) if score_rows else 0
            if status != "success":
                warnings = [f"{module} unavailable because factor pipeline did not produce rows"]
        elif module == "news":
            status = "skipped"
        elif module == "research_reports":
            status = "skipped"
        elif module == "financial":
            status = "skipped"
        elif module == "technical_features":
            status = "skipped"
        elif module == "intraday":
            status = "success" if minute_rows > 0 else "skipped"
            row_count = minute_rows
        elif module == "auction":
            status = "skipped"
        elif module == "lhb":
            status = "success" if lhb_rows > 0 else "skipped"
            row_count = lhb_rows
        synthetic.append(
            build_manifest_entry(
                run_id=run_id,
                run_date=_today_shanghai(),
                trade_date=trade_date,
                module=module,
                source=source,
                tier=tier,
                status=status,
                row_count=row_count,
                latest_trade_date=trade_date if status == "success" else None,
                warnings=warnings,
            )
        )
    return synthetic


def _manifest_status(step: dict[str, Any]) -> str:
    status = str(step.get("status") or "")
    if status == "success":
        return "success"
    if status == "skipped":
        return "skipped"
    if status == "skipped_dependency_failed":
        return "unavailable"
    if status in {"failed", "partial_failed"}:
        return "failed"
    if status == "running":
        return "partial"
    return "unavailable"


def _module_rows(modules: list[dict[str, Any]], module: str) -> int:
    return sum(int(item.get("row_count") or 0) for item in modules if item.get("module") == module)


def _module_status(modules: list[dict[str, Any]], module: str) -> str:
    statuses = [str(item.get("status") or "") for item in modules if item.get("module") == module]
    if "failed" in statuses or "unavailable" in statuses:
        return "failed"
    if "partial" in statuses:
        return "partial"
    if "success" in statuses:
        return "success"
    if "skipped" in statuses:
        return "skipped"
    return "unavailable"


def _artifact_index(step_results: list[dict[str, Any]]) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for step in step_results:
        if step.get("log_path"):
            artifacts[str(step.get("step"))] = str(step["log_path"])
    return artifacts


def _first_started_at(modules: list[dict[str, Any]]) -> str:
    values = [str(item.get("started_at")) for item in modules if item.get("started_at")]
    return min(values) if values else ""


def _step_log_path(output_dir: Path, step_name: str) -> Path:
    return output_dir / "logs" / f"{step_name}.log"


def _step_rows(stdout: str) -> int:
    rows = 0
    for token in stdout.replace("\n", "|").split("|"):
        if token.isdigit():
            rows = int(token)
    return rows


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
            status = "success" if returncode == 0 else "failed"
            step_results.append(
                {
                    "step": step.name,
                    "status": status,
                    "rows": _step_rows(stdout),
                    "error": "" if status == "success" else (stderr or stdout)[-500:],
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

    status = _legacy_status(step_results) if not required_failed else "partial_failed"
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
        "run_id": _run_id(trade_date),
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
