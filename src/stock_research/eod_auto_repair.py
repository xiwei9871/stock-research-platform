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
    RepairStatus,
)


ActionRunner = Callable[[str, str | Path], RepairActionResult]


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
    checks_before = [check.run() for check in check_plan_builder(trade_date)]
    actions: list[RepairActionResult] = []
    registry = action_registry if action_registry is not None else build_default_action_registry(output_root="outputs")
    if mode != "check":
        for check in checks_before:
            if check.status == RepairStatus.SUCCESS:
                continue
            runner = registry.get(check.name)
            if runner is None:
                continue
            actions.append(runner(trade_date, out))
    checks_after = [check.run() for check in check_plan_builder(trade_date)] if actions else checks_before
    summary = RepairRunSummary(
        trade_date=trade_date,
        mode=mode,
        final_status=_final_status(checks_after),
        checks_before=checks_before,
        actions=actions,
        checks_after=checks_after,
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
