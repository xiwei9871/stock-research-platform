from collections.abc import Callable
from typing import Any

from stock_research.config import SETTINGS
from stock_research.core_data import (
    build_asset_status_daily_for_service,
    build_industry_daily_bars_for_service,
    sync_core_asset_master_for_service,
)
from stock_research.db import connect, fetch_all
from stock_research.factor_pipeline import build_and_store_factor_daily
from stock_research.factor_store import score_stored_factor_daily
from stock_research.labels import compute_and_store_labels
from stock_research.loaders.baostock_ingestion import (
    sync_index_constituents,
    sync_index_daily_bars,
    sync_industry_memberships,
)
from stock_research.market_data import load_market_daily_bars
from stock_research.reports.daily_research_report_cli import run_daily_research_report

DAILY_INCREMENTAL_STEPS = [
    "sync_core_assets",
    "load_market_bars",
    "check_market_data_freshness",
    "build_asset_status",
    "sync_index_bars",
    "sync_index_constituents",
    "sync_industry_memberships",
    "build_industry_bars",
    "compute_labels",
    "build_factor_daily",
    "score_approved_factors",
    "run_daily_research_report",
]

StepRunner = Callable[[dict[str, Any]], Any]
FreshnessChecker = Callable[[dict[str, Any]], dict[str, Any]]
Recorder = Callable[[dict[str, Any]], Any]
DEFAULT_REQUIRED_DAILY_ADJUST_TYPES = ["hfq", "qfq"]
DEFAULT_MIN_MARKET_BAR_ROWS = 4000


def select_daily_incremental_steps(
    start_at: str | None = None,
    only_step: str | None = None,
) -> list[str]:
    if start_at and only_step:
        raise ValueError("start_at and only_step are mutually exclusive")
    if only_step:
        if only_step not in DAILY_INCREMENTAL_STEPS:
            raise ValueError(f"Unknown daily incremental step: {only_step}")
        return [only_step]
    if start_at:
        if start_at not in DAILY_INCREMENTAL_STEPS:
            raise ValueError(f"Unknown daily incremental step: {start_at}")
        start_index = DAILY_INCREMENTAL_STEPS.index(start_at)
        return DAILY_INCREMENTAL_STEPS[start_index:]
    return list(DAILY_INCREMENTAL_STEPS)


def build_default_step_runners() -> dict[str, StepRunner]:
    return {
        "sync_core_assets": _sync_core_assets_step,
        "load_market_bars": _load_market_bars_step,
        "check_market_data_freshness": _check_market_data_freshness_step,
        "build_asset_status": _build_asset_status_step,
        "sync_index_bars": _sync_index_bars_step,
        "sync_index_constituents": _sync_index_constituents_step,
        "sync_industry_memberships": _sync_industry_memberships_step,
        "build_industry_bars": _build_industry_bars_step,
        "compute_labels": _compute_labels_step,
        "build_factor_daily": _build_factor_daily_step,
        "score_approved_factors": _score_approved_factors_step,
        "run_daily_research_report": _run_daily_research_report_step,
    }


def check_market_data_freshness(
    context: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    trade_date = str(context["trade_date"])
    required_adjust_types = list(
        context.get("required_adjust_types") or DEFAULT_REQUIRED_DAILY_ADJUST_TYPES
    )
    min_required_rows = int(
        context.get("min_market_bar_rows") or DEFAULT_MIN_MARKET_BAR_ROWS
    )
    sql = """
    SELECT adjust_type, count(*)::int AS bar_count
    FROM market_daily_bar
    WHERE trade_date = %s
    GROUP BY adjust_type
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    observed_counts = {
        str(row["adjust_type"]): int(row["bar_count"])
        for row in rows
    }
    counts = {
        adjust_type: observed_counts.get(adjust_type, 0)
        for adjust_type in required_adjust_types
    }
    incomplete = [
        f"{adjust_type}={counts[adjust_type]}<{min_required_rows}"
        for adjust_type in required_adjust_types
        if counts[adjust_type] < min_required_rows
    ]
    if incomplete:
        return {
            "status": "blocked",
            "reason": f"market_daily_bar incomplete for {trade_date}: {', '.join(incomplete)}",
            "counts": counts,
            "min_required_rows": min_required_rows,
        }
    return {
        "status": "ok",
        "counts": counts,
        "min_required_rows": min_required_rows,
    }


def _sync_core_assets_step(context: dict[str, Any]) -> dict[str, Any]:
    sync_core_asset_master_for_service()
    return {"status": "synced"}


def _load_market_bars_step(context: dict[str, Any]) -> dict[str, Any]:
    rows = load_market_daily_bars(
        source_service=context["source_service"],
        adjust_type=context["adjust_type"],
        start_date=context["trade_date"],
        end_date=context["trade_date"],
        archive_raw=True,
    )
    return {"rows": rows}


def _check_market_data_freshness_step(context: dict[str, Any]) -> dict[str, Any]:
    result = check_market_data_freshness(context)
    if result.get("status") != "ok":
        raise RuntimeError(str(result.get("reason") or "market data freshness blocked"))
    return {
        "counts": result["counts"],
        "min_required_rows": result["min_required_rows"],
    }


def _build_asset_status_step(context: dict[str, Any]) -> dict[str, Any]:
    build_asset_status_daily_for_service(
        start_date=context["trade_date"],
        end_date=context["trade_date"],
        adjust_type=context["adjust_type"],
    )
    return {"status": "built"}


def _sync_index_bars_step(context: dict[str, Any]) -> dict[str, Any]:
    rows = sync_index_daily_bars(
        start_date=context["trade_date"],
        end_date=context["trade_date"],
    )
    return {"rows": rows}


def _sync_index_constituents_step(context: dict[str, Any]) -> dict[str, Any]:
    rows = sync_index_constituents(trade_date=context["trade_date"])
    return {"rows": rows}


def _sync_industry_memberships_step(context: dict[str, Any]) -> dict[str, Any]:
    rows = sync_industry_memberships(context["trade_date"])
    return {"rows": rows}


def _build_industry_bars_step(context: dict[str, Any]) -> dict[str, Any]:
    build_industry_daily_bars_for_service(
        start_date=context["trade_date"],
        end_date=context["trade_date"],
        industry_system=context["industry_system"],
        adjust_type=context["adjust_type"],
    )
    return {"status": "built"}


def _compute_labels_step(context: dict[str, Any]) -> dict[str, Any]:
    rows = compute_and_store_labels(
        end_date=context["trade_date"],
        start_date=context.get("label_start_date"),
    )
    return {"rows": rows}


def _build_factor_daily_step(context: dict[str, Any]) -> dict[str, Any]:
    rows = build_and_store_factor_daily(
        trade_date=context["trade_date"],
        lookback_bars=context["lookback_bars"],
    )
    return {"rows": rows}


def _score_approved_factors_step(context: dict[str, Any]) -> dict[str, Any]:
    rows = score_stored_factor_daily(
        trade_date=context["trade_date"],
        score_version=context["score_version"],
        approved_only=True,
    )
    return {"rows": rows}


def _run_daily_research_report_step(context: dict[str, Any]) -> dict[str, Any]:
    return run_daily_research_report(
        trade_date=context["trade_date"],
        score_version=context["score_version"],
        top_n=context["top_n"],
        industry_system=context["industry_system"],
        reports_dir=context["reports_dir"],
        record_run=True,
    )


def run_daily_incremental_pipeline(
    trade_date: str,
    score_version: str = "manual_v1",
    top_n: int = 30,
    lookback_bars: int = 130,
    reports_dir: str = "/Users/xiwei/stock_research/reports",
    adjust_type: str = "hfq",
    source_service: str = SETTINGS.hfq_service,
    industry_system: str = "csrc",
    label_start_date: str | None = None,
    dry_run: bool = False,
    step_runners: dict[str, StepRunner] | None = None,
    freshness_checker: FreshnessChecker | None = None,
    recorder: Recorder | None = None,
    start_at: str | None = None,
    only_step: str | None = None,
) -> dict[str, Any]:
    selected_steps = select_daily_incremental_steps(start_at=start_at, only_step=only_step)
    context = {
        "trade_date": trade_date,
        "score_version": score_version,
        "top_n": top_n,
        "lookback_bars": lookback_bars,
        "reports_dir": reports_dir,
        "adjust_type": adjust_type,
        "source_service": source_service,
        "industry_system": industry_system,
        "label_start_date": label_start_date,
        "start_at": start_at,
        "only_step": only_step,
    }
    if freshness_checker is not None:
        freshness = freshness_checker(context)
        if freshness.get("status") != "ok":
            return {
                "trade_date": trade_date,
                "status": "blocked",
                "reason": str(freshness.get("reason") or "freshness check blocked"),
                "steps": [],
            }

    runners = step_runners or {}
    steps = []
    for step_name in selected_steps:
        if dry_run:
            step_result = {"step": step_name, "status": "planned"}
            steps.append(step_result)
            continue

        try:
            runner = runners.get(step_name)
            if runner is None:
                raise NotImplementedError(f"no runner configured for {step_name}")
            output = runner(context)
            step_result = {
                "step": step_name,
                "status": "success",
                "result": output,
            }
        except Exception as exc:
            step_result = {
                "step": step_name,
                "status": "failed",
                "error": str(exc),
            }
            steps.append(step_result)
            if recorder is not None:
                recorder(step_result)
            return {"trade_date": trade_date, "status": "failed", "steps": steps}

        steps.append(step_result)
        if recorder is not None:
            recorder(step_result)

    status = "planned" if dry_run else "success"
    return {"trade_date": trade_date, "status": status, "steps": steps, **context}
