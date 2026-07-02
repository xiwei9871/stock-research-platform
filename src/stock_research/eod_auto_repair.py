from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from stock_research.eod_auto_repair_checks import build_check_plan
from stock_research.eod_auto_repair_models import (
    RepairActionResult,
    RepairCheckResult,
    RepairRunSummary,
    RepairStageResult,
    RepairStatus,
)


ActionRunner = Callable[[str, str | Path], RepairActionResult]

STAGE_CHECKS: list[tuple[str, tuple[str, ...]]] = [
    ("base_bars", ("daily_bars", "minute5_bars")),
    ("features", ("technical_features", "lhb_source", "lhb_features")),
    ("scores_and_watchlists", ("score_topn", "watchlist")),
    ("market_monitor", ("market_monitor",)),
    ("strategy_eod", ("strategy_publish", "review_queue", "strategy_score_audit")),
    ("presentation", ("reports", "review_evidence_snapshots", "ops_health", "dashboard_surface_freshness")),
]
PUBLISH_ONLY_STAGE_NAMES = {"strategy_eod", "presentation"}


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


def _safe_run_action(name: str, runner: ActionRunner, trade_date: str, output_dir: Path) -> RepairActionResult:
    try:
        return runner(trade_date, output_dir)
    except Exception as exc:  # noqa: BLE001 - action failures belong in the report.
        return RepairActionResult(
            name=name,
            status=RepairStatus.FAILED,
            message=f"{type(exc).__name__}: {exc}",
        )


def _checks_by_name(checks: list[RepairCheckResult]) -> dict[str, RepairCheckResult]:
    return {check.name: check for check in checks}


def _stage_checks(checks: list[RepairCheckResult], names: tuple[str, ...]) -> list[RepairCheckResult]:
    by_name = _checks_by_name(checks)
    return [by_name[name] for name in names if name in by_name]


def _has_blocker(checks: list[RepairCheckResult]) -> bool:
    return any(check.blocker and check.status != RepairStatus.SUCCESS for check in checks)


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
        return RepairStatus.FAILED
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


def _next_actions(checks: list[RepairCheckResult]) -> list[str]:
    actions = []
    blockers = _remaining_blockers(checks)
    if blockers:
        actions.append(f"Resolve blocking checks: {', '.join(blockers)}")
    non_blockers = _remaining_non_blockers(checks)
    if non_blockers:
        actions.append(f"Review non-blocking gaps: {', '.join(non_blockers)}")
    return actions


def _write_summary_files(summary: RepairRunSummary, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = summary.to_dict()
    (out / "run_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# EOD Auto Repair Report {summary.trade_date}",
        "",
        f"- Mode: {summary.mode}",
        f"- Final status: {summary.final_status.value}",
        "",
        "## Checks Before",
    ]
    for check in summary.checks_before:
        lines.append(f"- {check.name}: {check.status.value} {json.dumps(check.metrics, ensure_ascii=False)}")
    lines.append("")
    lines.append("## Actions")
    for action in summary.actions:
        lines.append(f"- {action.name}: {action.status.value} {json.dumps(action.metrics, ensure_ascii=False)}")
    lines.append("")
    lines.append("## Checks After")
    for check in summary.checks_after:
        lines.append(f"- {check.name}: {check.status.value} {json.dumps(check.metrics, ensure_ascii=False)}")
    (out / "run_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eod_auto_repair(
    *,
    trade_date: str,
    output_dir: str | Path,
    mode: str = "repair",
    check_plan_builder=build_check_plan,
    action_registry: dict[str, ActionRunner] | None = None,
    write_reports: bool = False,
) -> RepairRunSummary:
    if mode not in {"check", "repair", "publish-only"}:
        raise ValueError("mode must be check, repair, or publish-only")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    checks_before = _safe_run_check_plan(check_plan_builder, trade_date)
    current_checks = checks_before
    stages: list[RepairStageResult] = []
    actions: list[RepairActionResult] = []
    registry = action_registry if action_registry is not None else build_default_action_registry(output_root="outputs")
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
                action = _safe_run_action(check.name, runner, trade_date, out)
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
    )
    if write_reports:
        _write_summary_files(summary, out)
    return summary


def build_default_action_registry(*, output_root: str | Path = "outputs") -> dict[str, ActionRunner]:
    from stock_research.eod_auto_repair_actions import (
        repair_lhb_source_and_features,
        repair_market_monitor,
        repair_minute5_bars,
        repair_strategy_publish,
    )
    from stock_research.free_enrichment_data import run_free_enrichment_backfill
    from stock_research.lhb_data import run_lhb_event_features_build
    from stock_research.minute_backfill import run_baostock_minute_backfill
    from stock_research.strategy_eod_publish import publish_strategy_eod

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
        from stock_research.dashboard.market_monitor import build_market_monitor_eod

        return repair_market_monitor(trade_date, runner=build_market_monitor_eod)

    def minute_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        return repair_minute5_bars(trade_date, workers=1, runner=run_baostock_minute_backfill)

    return {
        "minute5_bars": minute_action,
        "lhb_source": lhb_action,
        "lhb_features": lhb_action,
        "market_monitor": market_monitor_action,
        "strategy_publish": strategy_action,
        "review_queue": strategy_action,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run EOD auto repair checks and actions.")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", choices=["check", "repair", "publish-only"], default="repair")
    parser.add_argument("--output-root", default="outputs")
    args = parser.parse_args(argv)
    summary = run_eod_auto_repair(
        trade_date=args.trade_date,
        output_dir=args.output_dir,
        mode=args.mode,
        action_registry=build_default_action_registry(output_root=args.output_root),
        write_reports=True,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0 if summary.final_status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED} else 2


if __name__ == "__main__":
    raise SystemExit(_main())
