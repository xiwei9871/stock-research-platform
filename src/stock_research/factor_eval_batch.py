from typing import Any
from uuid import uuid4

import pandas as pd

from stock_research.factor_eval.gate import decide_factor_gate
from stock_research.factor_eval.multi_horizon import generate_multi_horizon_report
from stock_research.factor_eval_store import (
    load_multi_horizon_factor_eval_inputs,
    store_factor_approval,
    store_factor_eval_run,
)


def run_factor_gate_batch(
    factor_names: list[str],
    start_date: str,
    end_date: str,
    horizons: list[int],
    primary_horizon: int = 5,
    calc_version: str = "v1",
    score_version: str = "manual_v1",
    quantiles: int = 5,
    top_n: int = 30,
) -> pd.DataFrame:
    rows = []
    for factor_name in factor_names:
        factors, returns = load_multi_horizon_factor_eval_inputs(
            factor_name=factor_name,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            calc_version=calc_version,
        )
        multi_horizon_report = generate_multi_horizon_report(
            factors=factors,
            returns=returns,
            factor_name=factor_name,
            horizons=horizons,
            quantiles=quantiles,
            top_n=top_n,
        )
        decision = decide_factor_gate(
            factor_name=factor_name,
            multi_horizon_report=multi_horizon_report,
            primary_horizon=primary_horizon,
        )
        run_id = _new_run_id(factor_name)
        store_factor_eval_run(
            run_id=run_id,
            factor_name=factor_name,
            calc_version=calc_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            primary_horizon=primary_horizon,
            status=decision["status"],
            reason=decision["reason"],
            metrics={
                "decision": decision,
                "multi_horizon": _summarize_multi_horizon_report(multi_horizon_report),
            },
        )
        store_factor_approval(
            factor_name=factor_name,
            calc_version=calc_version,
            score_version=score_version,
            status=decision["status"],
            reason=decision["reason"],
            eval_run_id=run_id,
        )
        rows.append(
            {
                "factor_name": factor_name,
                "status": decision["status"],
                "reason": decision["reason"],
                "primary_horizon": primary_horizon,
                "mean_ic": decision.get("mean_ic"),
                "icir": decision.get("icir"),
                "ic_count": decision.get("ic_count"),
                "eval_run_id": run_id,
            }
        )
    return pd.DataFrame(rows)


def _summarize_multi_horizon_report(report: dict[str, Any]) -> dict[str, Any]:
    summaries = {}
    for horizon, horizon_report in report.get("reports", {}).items():
        summaries[str(horizon)] = {
            "ic_summary": horizon_report.get("ic_summary", {}),
            "rank_ic_summary": horizon_report.get("rank_ic_summary", {}),
        }
    return {
        "factor_name": report.get("factor_name"),
        "horizons": report.get("horizons", []),
        "reports": summaries,
    }


def _new_run_id(factor_name: str) -> str:
    return f"factor-eval-batch-{factor_name}-{uuid4().hex}"
