from __future__ import annotations

from typing import Any


def decide_factor_gate(
    factor_name: str,
    multi_horizon_report: dict[str, Any],
    primary_horizon: int = 5,
    min_abs_mean_ic: float = 0.02,
    min_icir: float = 0.3,
    min_ic_count: int = 20,
) -> dict[str, Any]:
    reports = multi_horizon_report.get("reports", {})
    primary = reports.get(primary_horizon)
    if primary is None:
        return {
            "factor_name": factor_name,
            "status": "rejected",
            "reason": "missing_primary_horizon",
            "primary_horizon": primary_horizon,
        }

    summary = primary.get("ic_summary", {})
    mean_ic = summary.get("mean_ic")
    icir = summary.get("icir")
    ic_count = int(summary.get("ic_count") or 0)
    if ic_count < min_ic_count:
        reason = "insufficient_ic_count"
        status = "rejected"
    elif mean_ic is None or abs(float(mean_ic)) < min_abs_mean_ic:
        reason = "mean_ic_below_threshold"
        status = "rejected"
    elif icir is None or abs(float(icir)) < min_icir:
        reason = "icir_below_threshold"
        status = "rejected"
    else:
        reason = "passed_thresholds"
        status = "approved"
    return {
        "factor_name": factor_name,
        "status": status,
        "reason": reason,
        "primary_horizon": primary_horizon,
        "mean_ic": mean_ic,
        "icir": icir,
        "ic_count": ic_count,
        "thresholds": {
            "min_abs_mean_ic": min_abs_mean_ic,
            "min_icir": min_icir,
            "min_ic_count": min_ic_count,
        },
    }
