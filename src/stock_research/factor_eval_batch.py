from pathlib import Path
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
from stock_research.factor_config import candidate_factor_names
from stock_research.run_card import write_run_card


def run_factor_gate_batch(
    factor_names: list[str] | None,
    start_date: str,
    end_date: str,
    horizons: list[int],
    primary_horizon: int = 5,
    calc_version: str = "v1",
    score_version: str = "manual_v1",
    quantiles: int = 5,
    top_n: int = 30,
    validation_start_date: str | None = None,
    output_dir: str | Path | None = None,
) -> pd.DataFrame:
    rows = []
    selected_factor_names = candidate_factor_names() if factor_names is None else factor_names
    if validation_start_date:
        _validate_walk_forward_window(start_date, end_date, validation_start_date)
    selection_end_date = (
        _previous_date(validation_start_date) if validation_start_date else end_date
    )
    for factor_name in selected_factor_names:
        factors, returns = load_multi_horizon_factor_eval_inputs(
            factor_name=factor_name,
            start_date=start_date,
            end_date=selection_end_date,
            horizons=horizons,
            calc_version=calc_version,
        )
        multi_horizon_report = None
        validation_report = None
        if factors.empty:
            decision = {
                "factor_name": factor_name,
                "status": "rejected",
                "reason": "missing_factor_data",
                "primary_horizon": primary_horizon,
            }
        else:
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
            if validation_start_date:
                validation_factors, validation_returns = load_multi_horizon_factor_eval_inputs(
                    factor_name=factor_name,
                    start_date=validation_start_date,
                    end_date=end_date,
                    horizons=horizons,
                    calc_version=calc_version,
                )
                if not validation_factors.empty:
                    validation_report = generate_multi_horizon_report(
                        factors=validation_factors,
                        returns=validation_returns,
                        factor_name=factor_name,
                        horizons=horizons,
                        quantiles=quantiles,
                        top_n=top_n,
                    )
        run_id = _new_run_id(factor_name)
        metrics = {
            "decision": decision,
            "multi_horizon": (
                _summarize_multi_horizon_report(multi_horizon_report)
                if multi_horizon_report is not None
                else None
            ),
        }
        if validation_report is not None:
            metrics["walk_forward"] = {
                "selection_window": {
                    "start_date": start_date,
                    "end_date": selection_end_date,
                },
                "validation_window": {
                    "start_date": validation_start_date,
                    "end_date": end_date,
                },
                "validation_multi_horizon": _summarize_multi_horizon_report(
                    validation_report
                ),
            }
        run_card_paths = {}
        if output_dir is not None:
            run_card_paths = write_run_card(
                output_dir=Path(output_dir) / factor_name,
                run_type="factor_eval",
                run_id=run_id,
                title=f"Factor Eval: {factor_name}",
                config={
                    "factor_name": factor_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "horizons": horizons,
                    "primary_horizon": primary_horizon,
                    "calc_version": calc_version,
                    "score_version": score_version,
                },
                metrics=metrics,
                artifact_paths={},
                status=decision["status"],
                warnings=["missing_factor_data"] if decision["reason"] == "missing_factor_data" else [],
                data_coverage={
                    "input_start_date": start_date,
                    "input_end_date": end_date,
                    "actual_dates": sorted(factors["trade_date"].astype(str).unique().tolist()) if not factors.empty else [],
                    "row_count": int(len(factors)),
                    "asset_count": int(factors["asset_id"].nunique()) if not factors.empty else 0,
                },
            )
            metrics["artifacts"] = run_card_paths
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
            metrics=metrics,
        )
        store_factor_approval(
            factor_name=factor_name,
            calc_version=calc_version,
            score_version=score_version,
            status=decision["status"],
            reason=decision["reason"],
            eval_run_id=run_id,
        )
        validation_summary = _primary_ic_summary(validation_report, primary_horizon)
        rows.append(
            {
                "factor_name": factor_name,
                "status": decision["status"],
                "reason": decision["reason"],
                "primary_horizon": primary_horizon,
                "mean_ic": decision.get("mean_ic"),
                "icir": decision.get("icir"),
                "ic_count": decision.get("ic_count"),
                "validation_mean_ic": validation_summary.get("mean_ic"),
                "validation_icir": validation_summary.get("icir"),
                "validation_ic_count": validation_summary.get("ic_count"),
                "eval_run_id": run_id,
                "run_card_json_path": run_card_paths.get("run_card_json_path"),
                "run_card_md_path": run_card_paths.get("run_card_md_path"),
                "run_card_markdown_path": run_card_paths.get("run_card_md_path"),
                "metrics_json_path": run_card_paths.get("metrics_json_path"),
                "config_snapshot_path": run_card_paths.get("config_snapshot_path"),
                "warnings_md_path": run_card_paths.get("warnings_md_path"),
                "data_coverage_json_path": run_card_paths.get("data_coverage_json_path"),
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


def _previous_date(date_text: str) -> str:
    return (pd.Timestamp(date_text) - pd.Timedelta(days=1)).date().isoformat()


def _validate_walk_forward_window(
    start_date: str,
    end_date: str,
    validation_start_date: str,
) -> None:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    validation_start = pd.Timestamp(validation_start_date)
    if validation_start <= start or validation_start > end:
        raise ValueError(
            "validation_start_date must be after start_date and on or before end_date"
        )


def _primary_ic_summary(
    report: dict[str, Any] | None,
    primary_horizon: int,
) -> dict[str, Any]:
    if report is None:
        return {}
    primary = report.get("reports", {}).get(primary_horizon, {})
    return primary.get("ic_summary", {})
