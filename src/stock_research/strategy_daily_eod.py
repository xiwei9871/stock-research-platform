from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.strategy_daily_eod_store import apply_strategy_daily_eod_status_schema


DependencyChecker = Callable[..., dict[str, Any]]
StrategyRunner = Callable[..., dict[str, Any]]

_SUCCESS_DEPENDENCY_STATUSES = {"success", "partial_success"}

_DEPENDENCY_SQL = """
SELECT daily_status, minute5_status, deps_status
FROM ops.daily_pipeline_status
WHERE trade_date = %s
ORDER BY updated_at DESC
LIMIT 1
"""


def run_strategy_daily_eod(
    trade_date: str,
    *,
    output_root: str | Path,
    dependency_checker: DependencyChecker = None,
    lhb_shortline_runner: StrategyRunner = None,
    mid_trend_runner: StrategyRunner = None,
    tech_bottleneck_runner: StrategyRunner = None,
) -> dict[str, Any]:
    apply_strategy_daily_eod_status_schema()

    output_dir = Path(output_root) / trade_date
    output_dir.mkdir(parents=True, exist_ok=True)

    dependency_checker = dependency_checker or check_strategy_daily_eod_dependencies
    strategy_runners = {
        "lhb_shortline": lhb_shortline_runner or _missing_runner,
        "mid_trend": mid_trend_runner or _missing_runner,
        "tech_bottleneck": tech_bottleneck_runner or _missing_runner,
    }

    dependency_check = dependency_checker(trade_date=trade_date)
    if dependency_check.get("status") != "success":
        strategy_status = {
            name: {"status": "skipped", "reason": "dependency_check_failed"}
            for name in strategy_runners
        }
    else:
        strategy_status = {
            name: runner(trade_date=trade_date, output_dir=output_dir, strategy_name=name)
            for name, runner in strategy_runners.items()
        }

    overall_status = (
        "success"
        if all(result.get("status") == "success" for result in strategy_status.values())
        and dependency_check.get("status") == "success"
        else "failed"
    )
    review_rows = sum(int(result.get("review_rows") or 0) for result in strategy_status.values())

    summary = {
        "trade_date": trade_date,
        "status": overall_status,
        "dependency_check": dependency_check,
        "strategy_status": strategy_status,
        "review_rows": review_rows,
        "output_dir": str(output_dir),
    }

    summary_path = output_dir / "strategy_eod_publish_summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def check_strategy_daily_eod_dependencies(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    with connect(service) as conn:
        rows = fetch_all(conn, _DEPENDENCY_SQL, [trade_date])

    if not rows:
        return {"status": "failed", "reason": "daily_pipeline_status missing"}

    row = rows[0]
    daily_status = str(row.get("daily_status") or "")
    minute5_status = str(row.get("minute5_status") or "")
    deps_status = str(row.get("deps_status") or "")

    if (
        daily_status in _SUCCESS_DEPENDENCY_STATUSES
        and minute5_status in _SUCCESS_DEPENDENCY_STATUSES
        and deps_status == "success"
    ):
        return {
            "status": "success",
            "daily_status": daily_status,
            "minute5_status": minute5_status,
            "deps_status": deps_status,
        }

    return {
        "status": "failed",
        "reason": (
            "daily_pipeline_status not ready: "
            f"daily_status={daily_status or 'missing'}, "
            f"minute5_status={minute5_status or 'missing'}, "
            f"deps_status={deps_status or 'missing'}"
        ),
        "daily_status": daily_status,
        "minute5_status": minute5_status,
        "deps_status": deps_status,
    }


def _missing_runner(*, strategy_name: str = "unknown", **_kwargs: Any) -> dict[str, Any]:
    return {"status": "failed", "reason": f"{strategy_name} runner not configured"}
