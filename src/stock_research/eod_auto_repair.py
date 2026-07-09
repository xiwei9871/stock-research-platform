from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from stock_research.eod_auto_repair_checks import build_check_plan
from stock_research.eod_auto_repair_models import (
    RepairActionResult,
    RepairCheckResult,
    RepairLoopCycleResult,
    RepairRunSummary,
    RepairStageResult,
    RepairStatus,
)


ActionRunner = Callable[[str, str | Path], RepairActionResult]
ProgressEmitter = Callable[[dict[str, Any]], None]
_PROGRESS_WRITE_LOCK = threading.Lock()
ACTION_PROGRESS_HEARTBEAT_SECONDS = 60.0


class ActionTimeoutError(TimeoutError):
    pass


def _write_progress_event(output_dir: str | Path, event: dict[str, Any]) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    latest_path = out / "repair_progress.json"
    history_path = out / "repair_progress.jsonl"
    latest_tmp = out / "repair_progress.json.tmp"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with _PROGRESS_WRITE_LOCK:
        latest_tmp.write_text(text + "\n", encoding="utf-8")
        latest_tmp.replace(latest_path)
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _reset_progress_files(output_dir: str | Path) -> None:
    out = Path(output_dir)
    for name in ("repair_progress.json", "repair_progress.json.tmp", "repair_progress.jsonl"):
        try:
            (out / name).unlink(missing_ok=True)
        except Exception:
            continue


def _emit_progress(output_dir: str | Path, event: dict[str, Any]) -> None:
    try:
        _write_progress_event(output_dir, event)
    except Exception:
        return


def _make_action_progress(
    output_dir: str | Path,
    *,
    trade_date: str,
    component: str,
) -> ProgressEmitter:
    def emit(event: dict[str, Any]) -> None:
        payload = {
            "trade_date": trade_date,
            "component": component,
            **dict(event),
        }
        _emit_progress(output_dir, payload)

    return emit

STAGE_CHECKS: list[tuple[str, tuple[str, ...]]] = [
    ("base_bars", ("daily_bars", "minute5_bars")),
    ("features", ("technical_features", "lhb_source", "lhb_features")),
    ("scores_and_watchlists", ("factor_daily", "score_topn", "watchlist")),
    ("market_monitor", ("market_monitor",)),
    ("strategy_eod", ("strategy_publish", "review_queue", "strategy_score_audit")),
    ("presentation", ("reports", "review_evidence_snapshots", "ops_health", "dashboard_surface_freshness")),
]
PUBLISH_ONLY_STAGE_NAMES = {"strategy_eod", "presentation"}
LOOP_REPAIR_ORDER = [
    "daily_bars",
    "minute5_bars",
    "technical_features",
    "lhb_source",
    "lhb_features",
    "factor_daily",
    "score_topn",
    "watchlist",
    "market_monitor",
    "strategy_publish",
    "review_queue",
    "strategy_score_audit",
    "ops_health",
    "dashboard_surface_freshness",
]
LOOP_DEPENDENT_REPAIRS: dict[str, list[str]] = {
    "factor_daily": ["score_topn", "watchlist", "market_monitor", "strategy_publish"],
    "score_topn": ["watchlist", "market_monitor", "strategy_publish"],
    "watchlist": ["market_monitor", "strategy_publish"],
    "market_monitor": ["ops_health", "dashboard_surface_freshness"],
    "strategy_publish": ["ops_health", "dashboard_surface_freshness"],
}
OPS_READY_STATUSES = {"READY", "ready", "success", "DEGRADED_READY", "degraded_ready"}


def _safe_run_check(check) -> RepairCheckResult:
    try:
        return check.run()
    except Exception as exc:  # noqa: BLE001 - report must survive diagnostic failures.
        return RepairCheckResult(
            name=str(getattr(check, "name", "check_plan")),
            status=RepairStatus.FAILED,
            message=f"{type(exc).__name__}: {exc}",
            metrics={},
            blocker=True,
        )


def _safe_run_check_plan(check_plan_builder, trade_date: str) -> list[RepairCheckResult]:
    try:
        return [_safe_run_check(check) for check in check_plan_builder(trade_date)]
    except Exception as exc:  # noqa: BLE001 - plan failures belong in the report.
        return [
            RepairCheckResult(
                name="check_plan",
                status=RepairStatus.FAILED,
                message=f"{type(exc).__name__}: {exc}",
                metrics={},
                blocker=True,
            )
        ]


def _annotate_action_timing(
    action: RepairActionResult,
    *,
    started_at: str,
    ended_at: str,
) -> RepairActionResult:
    exit_code = action.exit_code
    if exit_code is None:
        exit_code = 0 if action.status == RepairStatus.SUCCESS else 1
    return RepairActionResult(
        name=action.name,
        status=action.status,
        message=action.message,
        metrics=action.metrics,
        artifact_paths=action.artifact_paths,
        started_at=action.started_at or started_at,
        ended_at=action.ended_at or ended_at,
        exit_code=exit_code,
        validation_result=action.validation_result,
    )


def _safe_run_action(
    name: str,
    runner: ActionRunner,
    trade_date: str,
    output_dir: Path,
    *,
    action_timeout_seconds: int | None = None,
    progress: ProgressEmitter | None = None,
) -> RepairActionResult:
    started_at = datetime.now(timezone.utc).isoformat()
    timeout_seconds = max(0, int(action_timeout_seconds or 0))
    use_alarm = (
        timeout_seconds > 0
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    previous_handler = None
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    monotonic_started_at = time.monotonic()

    def timeout_handler(signum, frame):  # noqa: ARG001 - signal handler signature.
        raise ActionTimeoutError(f"action exceeded timeout_seconds={timeout_seconds}")

    def emit_action_end(action: RepairActionResult) -> None:
        if progress is None:
            return
        progress(
            {
                "event": "action_end",
                "action": action.name,
                "status": action.status.value,
                "message": action.message,
                "started_at": action.started_at,
                "ended_at": action.ended_at,
                "exit_code": action.exit_code,
            }
        )

    def start_action_heartbeat() -> None:
        nonlocal heartbeat_thread
        heartbeat_seconds = float(ACTION_PROGRESS_HEARTBEAT_SECONDS or 0)
        if progress is None or heartbeat_seconds <= 0:
            return

        def heartbeat_loop() -> None:
            while not heartbeat_stop.wait(heartbeat_seconds):
                progress(
                    {
                        "event": "action_heartbeat",
                        "action": name,
                        "started_at": started_at,
                        "elapsed_seconds": round(time.monotonic() - monotonic_started_at, 3),
                        "timeout_seconds": timeout_seconds or None,
                    }
                )

        heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        heartbeat_thread.start()

    def stop_action_heartbeat() -> None:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1)

    try:
        if progress is not None:
            progress(
                {
                    "event": "action_start",
                    "action": name,
                    "timeout_seconds": timeout_seconds or None,
                    "started_at": started_at,
                }
            )
        start_action_heartbeat()
        if use_alarm:
            previous_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
        action = runner(trade_date, output_dir)
        annotated = _annotate_action_timing(
            action,
            started_at=started_at,
            ended_at=datetime.now(timezone.utc).isoformat(),
        )
        emit_action_end(annotated)
        return annotated
    except ActionTimeoutError as exc:
        action = RepairActionResult(
            name=name,
            status=RepairStatus.FAILED,
            message=f"TimeoutError: {exc}",
            started_at=started_at,
            ended_at=datetime.now(timezone.utc).isoformat(),
            exit_code=124,
        )
        emit_action_end(action)
        return action
    except Exception as exc:  # noqa: BLE001 - action failures belong in the report.
        action = RepairActionResult(
            name=name,
            status=RepairStatus.FAILED,
            message=f"{type(exc).__name__}: {exc}",
            started_at=started_at,
            ended_at=datetime.now(timezone.utc).isoformat(),
            exit_code=1,
        )
        emit_action_end(action)
        return action
    finally:
        stop_action_heartbeat()
        if use_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)


def _checks_by_name(checks: list[RepairCheckResult]) -> dict[str, RepairCheckResult]:
    return {check.name: check for check in checks}


def _action_with_validation(
    action: RepairActionResult,
    *,
    component: str,
    checks_after: list[RepairCheckResult],
) -> RepairActionResult:
    check = _checks_by_name(checks_after).get(component)
    validation_result: dict[str, object]
    if check is None:
        validation_result = {"component": component, "status": "unknown", "message": "validation check missing"}
    else:
        validation_result = {
            "component": component,
            "status": check.status.value,
            "message": check.message,
            "blocker": check.blocker,
            "metrics": check.metrics,
        }
    return RepairActionResult(
        name=action.name,
        status=action.status,
        message=action.message,
        metrics=action.metrics,
        artifact_paths=action.artifact_paths,
        started_at=action.started_at,
        ended_at=action.ended_at,
        exit_code=action.exit_code,
        validation_result=validation_result,
    )


def _stage_checks(checks: list[RepairCheckResult], names: tuple[str, ...]) -> list[RepairCheckResult]:
    by_name = _checks_by_name(checks)
    return [by_name[name] for name in names if name in by_name]


def _has_blocker(checks: list[RepairCheckResult]) -> bool:
    return any(check.blocker and check.status != RepairStatus.SUCCESS for check in checks)


def _ops_health_value(checks: list[RepairCheckResult]) -> str:
    check = _checks_by_name(checks).get("ops_health")
    if check is None:
        return ""
    value = check.metrics.get("pipeline_status") or check.metrics.get("ops_health") or check.status.value
    return str(value)


def _stages_for_mode(mode: str) -> list[tuple[str, tuple[str, ...]]]:
    if mode == "publish-only":
        return [(name, checks) for name, checks in STAGE_CHECKS if name in PUBLISH_ONLY_STAGE_NAMES]
    return STAGE_CHECKS


def _final_status(checks: list[RepairCheckResult]) -> RepairStatus:
    blockers = [check for check in checks if check.blocker and check.status != RepairStatus.SUCCESS]
    if blockers:
        return RepairStatus.FAILED
    degraded = [check for check in checks if check.status == RepairStatus.DEGRADED]
    if degraded:
        return RepairStatus.DEGRADED
    failed = [check for check in checks if check.status == RepairStatus.FAILED]
    if failed:
        return RepairStatus.DEGRADED
    skipped = [check for check in checks if check.status == RepairStatus.SKIPPED]
    if skipped:
        return RepairStatus.DEGRADED
    return RepairStatus.SUCCESS


def _remaining_blockers(checks: list[RepairCheckResult]) -> list[str]:
    return [check.name for check in checks if check.blocker and check.status != RepairStatus.SUCCESS]


def _remaining_non_blockers(checks: list[RepairCheckResult]) -> list[str]:
    return [
        check.name
        for check in checks
        if not check.blocker and check.status not in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}
    ]


def _classify_check(check: RepairCheckResult) -> str:
    if check.status == RepairStatus.SUCCESS:
        return "healthy"
    if check.status == RepairStatus.DEGRADED and not check.blocker:
        return "healthy"
    if check.status == RepairStatus.SKIPPED:
        return "unknown"
    if check.blocker:
        return "blocker"
    return "degraded_only"


def _classify_checks(checks: list[RepairCheckResult]) -> dict[str, str]:
    return {check.name: _classify_check(check) for check in checks}


def _ops_health_ready(checks: list[RepairCheckResult]) -> bool:
    by_name = _checks_by_name(checks)
    ops = by_name.get("ops_health")
    if ops is None:
        return not _has_blocker(checks)
    if ops.status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}:
        return True
    status_text = str(ops.metrics.get("pipeline_status") or "")
    return status_text in OPS_READY_STATUSES


def _next_actions(checks: list[RepairCheckResult]) -> list[str]:
    actions = []
    blockers = _remaining_blockers(checks)
    if blockers:
        actions.append(f"Resolve blocking checks: {', '.join(blockers)}")
    non_blockers = _remaining_non_blockers(checks)
    if non_blockers:
        actions.append(f"Review non-blocking gaps: {', '.join(non_blockers)}")
    return actions


def _recommended_followups(checks: list[RepairCheckResult]) -> list[str]:
    followups = []
    for check in checks:
        if not check.blocker and check.status not in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}:
            followups.append(f"Handle degraded-only {check.name}: {check.message}")
    if any(check.name == "daily_bars" and check.status == RepairStatus.DEGRADED for check in checks):
        followups.append("Review small daily_bars gaps in the data-gap loop.")
    return followups


def _write_summary_files(summary: RepairRunSummary, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = summary.to_dict()
    (out / "run_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    lines = [
        f"# EOD Auto Repair Report {summary.trade_date}",
        "",
        f"- Report path: {out / 'run_report.md'}",
        f"- Mode: {summary.mode}",
        f"- Initial status: {_final_status(summary.checks_before).value}",
        f"- Final status: {summary.final_status.value}",
        f"- Loop stop reason: {summary.loop_stop_reason or 'n/a'}",
        f"- Dry run: {summary.dry_run}",
        f"- Remaining blockers: {', '.join(summary.remaining_blockers) if summary.remaining_blockers else 'none'}",
        f"- Remaining non-blockers: {', '.join(summary.remaining_non_blockers) if summary.remaining_non_blockers else 'none'}",
        f"- Initial blocker count: {sum(1 for value in summary.initial_classification.values() if value == 'blocker')}",
        f"- Final blocker count: {len(summary.remaining_blockers)}",
        "",
        "## Stages",
    ]
    if summary.stages:
        for stage in summary.stages:
            blockers = ", ".join(stage.remaining_blockers) if stage.remaining_blockers else "none"
            lines.append(f"- {stage.name}: blockers={blockers}")
            for action in stage.actions:
                lines.append(f"  - action {action.name}: {action.status.value} {action.message}")
    else:
        lines.append("- none")
    if summary.loop_cycles:
        lines.extend(["", "## Loop Cycles"])
        for cycle in summary.loop_cycles:
            blockers = ", ".join(cycle.remaining_blockers) if cycle.remaining_blockers else "none"
            lines.append(f"- Cycle {cycle.cycle_number}: actions={len(cycle.actions)} blockers={blockers} stop={cycle.stop_reason or 'continue'}")
            for action in cycle.actions:
                lines.append(
                    f"  - {action.name}: {action.status.value} exit_code={action.exit_code} "
                    f"started={action.started_at} ended={action.ended_at} "
                    f"validation={json.dumps(action.validation_result, ensure_ascii=False, default=str)} {action.message}"
                )
    lines.extend([
        "",
        "## Checks Before",
    ])
    for check in summary.checks_before:
        lines.append(f"- {check.name}: {check.status.value} {json.dumps(check.metrics, ensure_ascii=False, default=str)}")
    lines.append("")
    lines.append("## Actions")
    for action in summary.actions:
        lines.append(
            f"- {action.name}: {action.status.value} exit_code={action.exit_code} "
            f"started={action.started_at} ended={action.ended_at} "
            f"metrics={json.dumps(action.metrics, ensure_ascii=False, default=str)} "
            f"validation={json.dumps(action.validation_result, ensure_ascii=False, default=str)}"
        )
    if not summary.actions:
        lines.append("- none")
    lines.append("")
    lines.append("## Checks After")
    for check in summary.checks_after:
        lines.append(f"- {check.name}: {check.status.value} {json.dumps(check.metrics, ensure_ascii=False, default=str)}")
    lines.append("")
    lines.append("## Next actions")
    if summary.next_actions:
        lines.extend(f"- {item}" for item in summary.next_actions)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Warnings")
    if summary.warnings:
        lines.extend(f"- {item}" for item in summary.warnings)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Infrastructure issues")
    if summary.infrastructure_issues:
        lines.extend(f"- {item}" for item in summary.infrastructure_issues)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Final decision")
    if not summary.remaining_blockers and summary.final_status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}:
        lines.append(
            "System is usable for dashboard, watchlist, strategy publish, review queue, "
            "and market monitor surfaces. No blocking EOD issue remains. Remaining issues "
            "are degraded-only and should be handled by separate data gap or report generation loops."
        )
    else:
        lines.append("Blocking EOD issues remain; review failed actions and external data availability.")
    if summary.recommended_followups:
        lines.extend(["", "## Recommended follow-ups"])
        lines.extend(f"- {item}" for item in summary.recommended_followups)
    (out / "run_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_eod_auto_repair_loop(
    *,
    trade_date: str,
    output_dir: Path,
    check_plan_builder,
    action_registry: dict[str, ActionRunner],
    max_cycles: int,
    dry_run: bool,
    action_timeout_seconds: int | None,
) -> RepairRunSummary:
    checks_before = _safe_run_check_plan(check_plan_builder, trade_date)
    current_checks = checks_before
    _emit_progress(
        output_dir,
        {
            "event": "observe_complete",
            "trade_date": trade_date,
            "final_status": _final_status(current_checks).value,
            "remaining_blockers": _remaining_blockers(current_checks),
            "degraded_only": _remaining_non_blockers(current_checks),
            "ops_health_ready": _ops_health_ready(current_checks),
        },
    )
    actions: list[RepairActionResult] = []
    cycles: list[RepairLoopCycleResult] = []
    failed_action_counts: dict[str, int] = {}
    stop_reason = ""
    warnings: list[str] = []

    if dry_run:
        stop_reason = "dry_run"
    elif not _has_blocker(current_checks) and _ops_health_ready(current_checks):
        stop_reason = "ready_with_no_blockers"
    else:
        for cycle_number in range(1, max(1, int(max_cycles)) + 1):
            cycle_before = current_checks
            cycle_actions: list[RepairActionResult] = []
            blockers_before = set(_remaining_blockers(cycle_before))
            ran_action_this_cycle: set[str] = set()
            forced_actions: set[str] = set()
            repair_queue = list(LOOP_REPAIR_ORDER)
            queue_index = 0

            while queue_index < len(repair_queue):
                check_name = repair_queue[queue_index]
                queue_index += 1
                by_name = _checks_by_name(current_checks)
                check = by_name.get(check_name)
                is_forced = check_name in forced_actions
                is_blocking_failure = check is not None and check.status != RepairStatus.SUCCESS and check.blocker
                if not is_forced and not is_blocking_failure:
                    continue
                if check_name in ran_action_this_cycle:
                    continue
                if failed_action_counts.get(check_name, 0) >= 2:
                    stop_reason = f"failed_action_repeat_limit:{check_name}"
                    break
                runner = action_registry.get(check_name)
                if runner is None:
                    if is_blocking_failure:
                        warnings.append(f"no repair action registered for blocker {check_name}")
                    continue

                action = _safe_run_action(
                    check_name,
                    runner,
                    trade_date,
                    output_dir,
                    action_timeout_seconds=action_timeout_seconds,
                    progress=_make_action_progress(
                        output_dir,
                        trade_date=trade_date,
                        component=check_name,
                    ),
                )
                ran_action_this_cycle.add(check_name)
                if action.status != RepairStatus.SUCCESS:
                    failed_action_counts[check_name] = failed_action_counts.get(check_name, 0) + 1
                    if failed_action_counts[check_name] >= 2:
                        stop_reason = f"failed_action_repeat_limit:{check_name}"
                current_checks = _safe_run_check_plan(check_plan_builder, trade_date)
                action = _action_with_validation(action, component=check_name, checks_after=current_checks)
                _emit_progress(
                    output_dir,
                    {
                        "event": "validation_complete",
                        "trade_date": trade_date,
                        "component": check_name,
                        "action": action.name,
                        "validation_result": action.validation_result,
                        "remaining_blockers": _remaining_blockers(current_checks),
                        "degraded_only": _remaining_non_blockers(current_checks),
                    },
                )
                cycle_actions.append(action)
                actions.append(action)
                if action.status == RepairStatus.SUCCESS:
                    for dependent_name in LOOP_DEPENDENT_REPAIRS.get(check_name, []):
                        if dependent_name in ran_action_this_cycle:
                            continue
                        forced_actions.add(dependent_name)
                        if dependent_name not in repair_queue[queue_index:]:
                            repair_queue.append(dependent_name)
                if stop_reason:
                    break
                pending_forced_actions = [
                    name
                    for name in repair_queue[queue_index:]
                    if name in forced_actions and name not in ran_action_this_cycle and name in action_registry
                ]
                if not pending_forced_actions and not _has_blocker(current_checks) and _ops_health_ready(current_checks):
                    stop_reason = "ready_with_no_blockers"
                    break

            blockers_after = _remaining_blockers(current_checks)
            cycle_stop_reason = stop_reason
            if not cycle_actions and blockers_after and not cycle_stop_reason:
                cycle_stop_reason = "no_repair_action_available"
                stop_reason = cycle_stop_reason
            elif blockers_before == set(blockers_after) and cycle_actions and blockers_after and not cycle_stop_reason:
                cycle_stop_reason = "no_blocker_improvement"

            cycles.append(
                RepairLoopCycleResult(
                    cycle_number=cycle_number,
                    checks_before=cycle_before,
                    actions=cycle_actions,
                    checks_after=current_checks,
                    remaining_blockers=blockers_after,
                    stop_reason=cycle_stop_reason,
                )
            )
            if stop_reason:
                break
            if not _has_blocker(current_checks) and _ops_health_ready(current_checks):
                stop_reason = "ready_with_no_blockers"
                break

    if not stop_reason and _has_blocker(current_checks):
        stop_reason = "max_cycles_exhausted"
    elif not stop_reason:
        stop_reason = "ready_with_no_blockers" if _ops_health_ready(current_checks) else "ops_health_not_ready"

    final_status = _final_status(current_checks)
    if stop_reason in {"max_cycles_exhausted", "ops_health_not_ready"} or stop_reason.startswith("failed_action_repeat_limit"):
        if _has_blocker(current_checks):
            final_status = RepairStatus.FAILED

    return RepairRunSummary(
        trade_date=trade_date,
        mode="loop",
        final_status=final_status,
        checks_before=checks_before,
        actions=actions,
        checks_after=current_checks,
        loop_cycles=cycles,
        remaining_blockers=_remaining_blockers(current_checks),
        remaining_non_blockers=_remaining_non_blockers(current_checks),
        next_actions=_next_actions(current_checks),
        initial_classification=_classify_checks(checks_before),
        final_classification=_classify_checks(current_checks),
        loop_stop_reason=stop_reason,
        dry_run=dry_run,
        max_cycles=max_cycles,
        warnings=warnings,
        infrastructure_issues=[],
        recommended_followups=_recommended_followups(current_checks),
    )


def run_eod_auto_repair(
    *,
    trade_date: str,
    output_dir: str | Path,
    mode: str = "repair",
    check_plan_builder=build_check_plan,
    action_registry: dict[str, ActionRunner] | None = None,
    write_reports: bool = False,
    max_cycles: int = 3,
    dry_run: bool = False,
    strict: bool = False,
    action_timeout_seconds: int | None = None,
) -> RepairRunSummary:
    if mode not in {"check", "repair", "publish-only", "loop"}:
        raise ValueError("mode must be check, repair, publish-only, or loop")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    registry = action_registry if action_registry is not None else build_default_action_registry(output_root="outputs")
    if mode == "loop":
        _reset_progress_files(out)
        summary = _run_eod_auto_repair_loop(
            trade_date=trade_date,
            output_dir=out,
            check_plan_builder=check_plan_builder,
            action_registry=registry,
            max_cycles=max_cycles,
            dry_run=dry_run,
            action_timeout_seconds=action_timeout_seconds,
        )
        if strict and summary.final_status != RepairStatus.SUCCESS:
            summary = replace(summary, final_status=RepairStatus.FAILED)
        _emit_progress(
            out,
            {
                "event": "loop_done",
                "trade_date": trade_date,
                "final_status": summary.final_status.value,
                "ops_health": _ops_health_value(summary.checks_after),
                "remaining_blockers": summary.remaining_blockers,
                "degraded_only": summary.remaining_non_blockers,
                "loop_stop_reason": summary.loop_stop_reason,
                "dry_run": summary.dry_run,
            },
        )
        if write_reports:
            _write_summary_files(summary, out)
        return summary

    checks_before = _safe_run_check_plan(check_plan_builder, trade_date)
    current_checks = checks_before
    stages: list[RepairStageResult] = []
    actions: list[RepairActionResult] = []
    if mode != "check":
        for stage_name, check_names in _stages_for_mode(mode):
            before = _stage_checks(current_checks, check_names)
            if not before:
                continue
            stage_actions = []
            for check in before:
                if check.status == RepairStatus.SUCCESS:
                    continue
                runner = registry.get(check.name)
                if runner is None:
                    continue
                action = _safe_run_action(
                    check.name,
                    runner,
                    trade_date,
                    out,
                    action_timeout_seconds=action_timeout_seconds,
                )
                stage_actions.append(action)
                actions.append(action)
            if stage_actions:
                current_checks = _safe_run_check_plan(check_plan_builder, trade_date)
            after = _stage_checks(current_checks, check_names)
            stages.append(
                RepairStageResult(
                    name=stage_name,
                    checks_before=before,
                    actions=stage_actions,
                    checks_after=after,
                    remaining_blockers=_remaining_blockers(after),
                )
            )
            if _has_blocker(after):
                break
    checks_after = current_checks if actions or stages else checks_before
    summary = RepairRunSummary(
        trade_date=trade_date,
        mode=mode,
        final_status=_final_status(checks_after),
        checks_before=checks_before,
        actions=actions,
        checks_after=checks_after,
        stages=stages,
        remaining_blockers=_remaining_blockers(checks_after),
        remaining_non_blockers=_remaining_non_blockers(checks_after),
        next_actions=_next_actions(checks_after),
        initial_classification=_classify_checks(checks_before),
        final_classification=_classify_checks(checks_after),
        recommended_followups=_recommended_followups(checks_after),
    )
    if write_reports:
        _write_summary_files(summary, out)
    return summary


def build_default_action_registry(*, output_root: str | Path = "outputs") -> dict[str, ActionRunner]:
    from stock_research.eod_auto_repair_actions import (
        repair_factor_daily,
        repair_generated_reports,
        repair_lhb_source_and_features,
        repair_market_monitor,
        repair_minute5_raw_bars,
        repair_review_evidence_snapshots,
        repair_score_topn,
        repair_strategy_publish,
        repair_technical_features,
        repair_watchlist,
    )
    from stock_research.daily_pipeline import run_daily_factor_pipeline
    from stock_research.data_run_manifest import upsert_data_run_manifest
    from stock_research.free_enrichment_data import run_free_enrichment_backfill
    from stock_research.lhb_data import run_lhb_event_features_build
    from stock_research.review_evidence_snapshots import run_eod_review_evidence_snapshots
    from stock_research.reports.daily_research_report_cli import run_daily_research_report
    from stock_research.strategy_eod_publish import (
        DEFAULT_REPORTS_DIR,
        _write_report_content_manifest_entries,
        publish_strategy_eod,
    )
    from stock_research.technical_feature_store import build_and_store_stock_technical_features_daily
    from stock_research.factor_backfill import backfill_factor_daily_range
    from stock_research.watchlist.workflow import (
        build_watchlist_diagnostics_snapshot,
        build_watchlist_snapshot,
        store_watchlist_daily_signals,
    )

    def lhb_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        return repair_lhb_source_and_features(
            trade_date,
            output_dir=output_dir,
            enrichment_runner=run_free_enrichment_backfill,
            feature_runner=run_lhb_event_features_build,
        )

    def strategy_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        return repair_strategy_publish(
            trade_date,
            output_root=output_root,
            publisher=publish_strategy_eod,
        )

    def market_monitor_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        from stock_research.daily_close_pipeline import PipelineConfig, run_market_monitor_stage
        from stock_research.dashboard.market_monitor import build_market_monitor_eod

        def runner(**kwargs) -> dict[str, object]:
            stage = run_market_monitor_stage(
                date.fromisoformat(kwargs["trade_date"]),
                config=PipelineConfig(),
            )
            dashboard = build_market_monitor_eod(trade_date=kwargs["trade_date"])
            return {"stage": dict(stage or {}), "dashboard": dict(dashboard or {})}

        return repair_market_monitor(trade_date, runner=runner)

    def ops_health_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        from stock_research.daily_close_pipeline import PipelineConfig, finalize_pipeline_status

        result = finalize_pipeline_status(date.fromisoformat(trade_date), config=PipelineConfig())
        return RepairActionResult(
            name="finalize_ops_health",
            status=RepairStatus.SUCCESS,
            message="ops health finalized",
            metrics=dict(result or {}),
        )

    def minute_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        from stock_research.daily_close_pipeline import (
            PipelineConfig,
            derive_qfq_minute5_from_daily_factor,
            fetch_baostock_minute5_rows,
            inspect_minute5_quality_from_db,
            load_latest_minute5_missing_symbols,
            load_minute5_expected_ts_codes,
            upsert_minute5_bars,
            upsert_quality,
        )

        config = PipelineConfig()

        def quality_refresher(service: str, target_date: date) -> dict[str, object]:
            expected_ts_codes = load_minute5_expected_ts_codes(service, target_date)
            quality = inspect_minute5_quality_from_db(service, expected_ts_codes, target_date)
            upsert_quality(service=service, trade_date=target_date, dataset_name="minute5_bar", **quality)
            return quality

        return repair_minute5_raw_bars(
            trade_date,
            service=config.service,
            missing_symbols_loader=lambda value: load_latest_minute5_missing_symbols(config.service, date.fromisoformat(value)),
            raw_fetcher=fetch_baostock_minute5_rows,
            upserter=upsert_minute5_bars,
            qfq_deriver=derive_qfq_minute5_from_daily_factor,
            quality_refresher=quality_refresher,
            timeout_seconds=config.request_timeout_seconds,
            symbol_sleep_seconds=config.minute5_symbol_sleep_seconds,
        )

    def technical_features_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        def runner(**kwargs) -> dict[str, int]:
            stored_rows = build_and_store_stock_technical_features_daily(**kwargs)
            return {"stored_rows": int(stored_rows or 0)}

        return repair_technical_features(trade_date, runner=runner)

    def score_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        def runner(**kwargs) -> dict[str, object]:
            result = run_daily_factor_pipeline(
                trade_date=kwargs["trade_date"],
                score_version=kwargs["score_version"],
                reports_dir=str(kwargs["output_dir"]),
            )
            return dict(result or {})

        return repair_score_topn(trade_date, output_dir=output_dir, runner=runner)

    def factor_daily_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        return repair_factor_daily(
            trade_date,
            runner=backfill_factor_daily_range,
            progress=_make_action_progress(
                output_dir,
                trade_date=trade_date,
                component="factor_daily",
            ),
        )

    def watchlist_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        def runner(**kwargs) -> dict[str, int]:
            watchlist_id = str(kwargs["watchlist_id"])
            if watchlist_id == "diagnostics":
                diagnostics = build_watchlist_diagnostics_snapshot(trade_date=kwargs["trade_date"])
                frames = [frame for frame in diagnostics.values() if not frame.empty]
                if not frames:
                    return {"row_count": 0}
                import pandas as pd

                frame = pd.concat(frames, ignore_index=True)
                return {"row_count": int(store_watchlist_daily_signals(frame))}
            frame = build_watchlist_snapshot(trade_date=kwargs["trade_date"], watchlist_id=watchlist_id)
            return {"row_count": int(len(frame))}

        return repair_watchlist(trade_date, runner=runner)

    def reports_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        def runner(**kwargs) -> dict[str, object]:
            from datetime import datetime, timezone

            report_result = run_daily_research_report(
                trade_date=kwargs["trade_date"],
                score_version="manual_v1",
                top_n=30,
                index_id="CSI300",
                market_lookback_days=90,
                industry_system="csrc",
                sector_lookback_days=60,
                positions_csv=None,
                reports_dir=DEFAULT_REPORTS_DIR,
                apply_report_run_schema_first=False,
                record_run=False,
            )
            entries = _write_report_content_manifest_entries(
                run_id=f"eod-auto-repair-reports-{kwargs['trade_date']}",
                trade_date=kwargs["trade_date"],
                started_at=datetime.now(timezone.utc),
            )
            for entry in entries:
                upsert_data_run_manifest(entry)
            generated = next((entry for entry in entries if entry.get("module") == "generated_reports"), {})
            metadata = dict(generated.get("metadata") or {})
            return {
                "generated_reports": int(generated.get("row_count") or 0),
                "output_dir": str(metadata.get("reports_dir") or output_dir),
                "report_paths": report_result.get("report_paths") or {},
            }

        return repair_generated_reports(trade_date, runner=runner)

    def snapshots_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        def runner(**kwargs) -> dict[str, object]:
            result = run_eod_review_evidence_snapshots(
                run_id=f"eod-auto-repair-snapshots-{kwargs['trade_date']}",
                trade_date=kwargs["trade_date"],
                output_dir=output_dir,
            )
            metrics = dict(result or {})
            metrics["output_dir"] = str(output_dir)
            return metrics

        return repair_review_evidence_snapshots(trade_date, runner=runner)

    return {
        "minute5_bars": minute_action,
        "technical_features": technical_features_action,
        "factor_daily": factor_daily_action,
        "lhb_source": lhb_action,
        "lhb_features": lhb_action,
        "score_topn": score_action,
        "watchlist": watchlist_action,
        "market_monitor": market_monitor_action,
        "strategy_publish": strategy_action,
        "review_queue": strategy_action,
        "strategy_score_audit": strategy_action,
        "ops_health": ops_health_action,
        "reports": reports_action,
        "review_evidence_snapshots": snapshots_action,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run EOD auto repair checks and actions.")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--mode", choices=["check", "repair", "publish-only", "loop"], default="repair")
    parser.add_argument("--output-root", default="outputs")
    parser.add_argument("--max-cycles", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-json")
    parser.add_argument("--report-md")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--action-timeout-seconds", type=int, default=43200)
    args = parser.parse_args(argv)
    output_dir = args.output_dir or str(Path(args.output_root) / "research" / "eod_auto_repair" / args.trade_date)
    summary = run_eod_auto_repair(
        trade_date=args.trade_date,
        output_dir=output_dir,
        mode=args.mode,
        action_registry=build_default_action_registry(output_root=args.output_root),
        write_reports=True,
        max_cycles=args.max_cycles,
        dry_run=args.dry_run,
        strict=args.strict,
        action_timeout_seconds=args.action_timeout_seconds,
    )
    if args.report_json:
        Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_json).write_text(
            json.dumps(summary.to_dict(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    if args.report_md:
        source = Path(output_dir) / "run_report.md"
        Path(args.report_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_md).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0 if summary.final_status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED} else 2


if __name__ == "__main__":
    raise SystemExit(_main())
