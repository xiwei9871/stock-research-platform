from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.config import SETTINGS

REQUIRED_BASE_MODULES = {"daily_bars", "technical_features", "score_topn", "lhb_features", "tech_bottleneck_candidates"}
BASE_REQUIRED_REVIEW_MODULES = {"review_queue_strategy_manifest"}
REQUIRED_STRATEGY_MODULES = {
    "strategy_lhb_shortline": "lhb_shortline",
    "strategy_mid_trend": "mid_trend",
    "strategy_tech_bottleneck": "tech_bottleneck",
}
LOCAL_ZONE = ZoneInfo("Asia/Shanghai")
DISPLAY_CUTOFF = time(20, 30)


class BrowserAcceptanceRolloutConfigError(ValueError):
    """The browser acceptance rollout boundary is configured incorrectly."""


def required_review_modules(trade_date: str) -> set[str]:
    required = set(BASE_REQUIRED_REVIEW_MODULES)
    raw_boundary = SETTINGS.browser_acceptance_required_from
    if not raw_boundary:
        return required
    try:
        boundary = date.fromisoformat(raw_boundary)
    except ValueError as exc:
        raise BrowserAcceptanceRolloutConfigError(
            "STOCK_RESEARCH_BROWSER_ACCEPTANCE_REQUIRED_FROM must be an ISO date (YYYY-MM-DD)"
        ) from exc
    if trade_date >= boundary.isoformat():
        required.add("dashboard_browser_acceptance")
    return required


def load_strategy_contracts(*, profile: str = "balanced") -> dict[str, Any]:
    from stock_research.strategy_contracts import load_strategy_contracts as load_contracts

    return load_contracts(profile=profile)


def validate_strategy_summary_against_contract(summary: dict[str, Any], contract: Any) -> Any:
    from stock_research.strategy_contracts import (
        validate_strategy_summary_against_contract as validate_summary,
    )

    return validate_summary(summary, contract)


def select_display_date(
    modules: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    latest_market_date: str = "",
) -> dict[str, Any]:
    current_time = now.astimezone(LOCAL_ZONE) if now else datetime.now(LOCAL_ZONE)
    grouped = _modules_by_trade_date(modules)
    candidate_trade_date = str(latest_market_date or _latest_trade_date(grouped) or "")
    ready_by_date = {
        trade_date: _evaluate_trade_date(trade_date, rows)
        for trade_date, rows in grouped.items()
    }
    ready_dates = sorted(
        trade_date
        for trade_date, status in ready_by_date.items()
        if status["display_status"] == "ready"
    )
    candidate = ready_by_date.get(candidate_trade_date)

    local_today = current_time.date().isoformat()
    if candidate_trade_date == local_today and current_time.time() < DISPLAY_CUTOFF:
        prior_ready = [trade_date for trade_date in ready_dates if trade_date < candidate_trade_date]
        display_date = prior_ready[-1] if prior_ready else ""
        return _payload(
            display_date=display_date,
            candidate_trade_date=candidate_trade_date,
            candidate_status="before_cutoff",
            candidate=candidate,
            ready_by_date=ready_by_date,
        )

    if candidate and candidate["display_status"] == "ready":
        return _payload(
            display_date=candidate_trade_date,
            candidate_trade_date=candidate_trade_date,
            candidate_status="ready",
            candidate=candidate,
            ready_by_date=ready_by_date,
        )

    display_date = ready_dates[-1] if ready_dates else ""
    return _payload(
        display_date=display_date,
        candidate_trade_date=candidate_trade_date,
        candidate_status=(candidate or {}).get("display_status") or "missing",
        candidate=candidate,
        ready_by_date=ready_by_date,
    )


def _modules_by_trade_date(modules: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in modules:
        trade_date = str(row.get("trade_date") or row.get("latest_trade_date") or "")[:10]
        if trade_date:
            grouped[trade_date].append(row)
    return dict(grouped)


def _latest_trade_date(grouped: dict[str, list[dict[str, Any]]]) -> str:
    return max(grouped) if grouped else ""


def _evaluate_trade_date(trade_date: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    run_evaluations = [
        _evaluate_run(trade_date, run_id, run_rows)
        for run_id, run_rows in _modules_by_run_id(rows).items()
    ]
    return _best_run_evaluation(run_evaluations) if run_evaluations else _evaluate_run(trade_date, "", [])


def _modules_by_run_id(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("run_id") or "")].append(row)
    return dict(grouped)


def _best_run_evaluation(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    status_rank = {"ready": 2, "contract_mismatch": 1, "incomplete": 0}
    return max(
        evaluations,
        key=lambda status: (
            status_rank.get(str(status.get("display_status") or ""), -1),
            int(status.get("strategy_ready_count") or 0),
            int(status.get("contract_valid_count") or 0),
            -len(status.get("blocking_reasons") or []),
            str(status.get("run_id") or ""),
        ),
    )


def _evaluate_run(trade_date: str, run_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_module = {str(row.get("module") or ""): row for row in rows}
    required_modules = REQUIRED_BASE_MODULES | required_review_modules(trade_date) | set(REQUIRED_STRATEGY_MODULES)
    missing = [
        module
        for module in sorted(required_modules)
        if not _module_ready_for_display(module, by_module.get(module) or {})
    ]
    tech_snapshot_failures = _tech_candidate_snapshot_failures(trade_date, by_module)
    contract_failures = _contract_failures(by_module)
    display_status = "ready"
    if missing or tech_snapshot_failures:
        display_status = "incomplete"
    elif contract_failures:
        display_status = "contract_mismatch"

    return {
        "trade_date": trade_date,
        "run_id": run_id,
        "display_status": display_status,
        "strategy_ready_count": sum(
            1
            for module in REQUIRED_STRATEGY_MODULES
            if str((by_module.get(module) or {}).get("status") or "") == "success"
        ),
        "strategy_total_count": len(REQUIRED_STRATEGY_MODULES),
        "contract_valid_count": len(REQUIRED_STRATEGY_MODULES) - len(contract_failures),
        "contract_total_count": len(REQUIRED_STRATEGY_MODULES),
        "blocking_reasons": [f"missing:{module}" for module in missing] + tech_snapshot_failures + contract_failures,
    }


def _module_ready_for_display(module: str, row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "")
    if status == "success":
        return True
    if module == "dashboard_browser_acceptance":
        return status == "degraded"
    return module == "daily_bars" and status in {"partial", "degraded"}


def _tech_candidate_snapshot_failures(trade_date: str, by_module: dict[str, dict[str, Any]]) -> list[str]:
    metadata = by_module.get("strategy_tech_bottleneck", {}).get("metadata")
    if not isinstance(metadata, dict):
        return ["tech_bottleneck:candidate_snapshot_missing"]
    snapshot_date = _candidate_snapshot_latest_date(metadata)
    if not snapshot_date:
        return ["tech_bottleneck:candidate_snapshot_missing"]
    if snapshot_date != trade_date:
        return [f"tech_bottleneck:candidate_snapshot_stale:{snapshot_date}"]
    return []


def _candidate_snapshot_latest_date(metadata: dict[str, Any]) -> str:
    snapshot_date = metadata.get("candidate_snapshot_latest_date")
    if not snapshot_date and isinstance(metadata.get("summary"), dict):
        snapshot_date = metadata["summary"].get("candidate_snapshot_latest_date")
    return str(snapshot_date or "")[:10]


def _contract_failures(by_module: dict[str, dict[str, Any]]) -> list[str]:
    try:
        contracts = load_strategy_contracts(profile="balanced")
    except Exception:
        contracts = {}

    failures: list[str] = []
    for module, strategy_id in REQUIRED_STRATEGY_MODULES.items():
        contract = contracts.get(strategy_id)
        if contract is None:
            continue
        metadata = by_module.get(module, {}).get("metadata")
        summary = metadata.get("summary") if isinstance(metadata, dict) else {}
        result = validate_strategy_summary_against_contract(dict(summary or {}), contract)
        if result.status != "success":
            failures.append(f"{strategy_id}:{result.reason}")
    return failures


def _payload(
    *,
    display_date: str,
    candidate_trade_date: str,
    candidate_status: str,
    candidate: dict[str, Any] | None,
    ready_by_date: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected = ready_by_date.get(display_date, {})
    return {
        "display_trade_date": display_date,
        "latest_market_date": candidate_trade_date,
        "candidate_trade_date": candidate_trade_date,
        "cutoff_time": "20:30",
        "timezone": "Asia/Shanghai",
        "display_status": selected.get("display_status") or ("ready" if display_date else "missing"),
        "candidate_status": candidate_status,
        "strategy_ready": f"{selected.get('strategy_ready_count', 0)}/{len(REQUIRED_STRATEGY_MODULES)}",
        "contract_valid": f"{selected.get('contract_valid_count', 0)}/{len(REQUIRED_STRATEGY_MODULES)}",
        "blocking_reasons": list((candidate or {}).get("blocking_reasons") or []),
    }
