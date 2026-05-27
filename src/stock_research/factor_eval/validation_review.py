from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.factor_eval.multi_horizon import generate_multi_horizon_report
from stock_research.factor_eval.segment import summarize_return_by_segment


def build_factor_validation_review(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    factor_name: str,
    horizons: list[int],
    split_date: str,
    *,
    primary_horizon: int | None = None,
    segments: pd.DataFrame | None = None,
    segment_col: str | None = None,
    factor_col: str = "factor_value",
    min_abs_mean_ic: float = 0.02,
    min_icir: float = 0.3,
    min_ic_count: int = 20,
) -> dict[str, Any]:
    primary = int(primary_horizon or horizons[0])
    normalized_factors = _normalize_trade_dates(factors)
    normalized_returns = _normalize_trade_dates(returns)
    split_key = str(split_date)[:10]

    in_factors = normalized_factors[normalized_factors["trade_date"] < split_key]
    in_returns = normalized_returns[normalized_returns["trade_date"] < split_key]
    out_factors = normalized_factors[normalized_factors["trade_date"] >= split_key]
    out_returns = normalized_returns[normalized_returns["trade_date"] >= split_key]

    full_report = generate_multi_horizon_report(
        normalized_factors,
        normalized_returns,
        factor_name=factor_name,
        horizons=horizons,
        factor_col=factor_col,
    )
    in_sample_report = generate_multi_horizon_report(
        in_factors,
        in_returns,
        factor_name=factor_name,
        horizons=horizons,
        factor_col=factor_col,
    )
    out_sample_report = generate_multi_horizon_report(
        out_factors,
        out_returns,
        factor_name=factor_name,
        horizons=horizons,
        factor_col=factor_col,
    )

    thresholds = {
        "min_abs_mean_ic": float(min_abs_mean_ic),
        "min_icir": float(min_icir),
        "min_ic_count": int(min_ic_count),
    }
    in_sample_gate = _decide_sample_gate(
        factor_name,
        in_sample_report,
        primary_horizon=primary,
        thresholds=thresholds,
    )
    out_of_sample_gate = _decide_sample_gate(
        factor_name,
        out_sample_report,
        primary_horizon=primary,
        thresholds=thresholds,
    )
    decay = _build_decay_summary(full_report, primary_horizon=primary)
    segment_validation = _build_segment_validation(
        normalized_factors,
        normalized_returns,
        segments=segments,
        segment_col=segment_col,
        factor_col=factor_col,
        primary_horizon=primary,
    )
    approval = _decide_approval(
        in_sample_gate=in_sample_gate,
        out_of_sample_gate=out_of_sample_gate,
    )

    return {
        "factor_name": factor_name,
        "split_date": split_key,
        "horizons": [int(horizon) for horizon in horizons],
        "primary_horizon": primary,
        "thresholds": thresholds,
        "in_sample": _build_sample_summary(in_factors, in_returns),
        "out_of_sample": _build_sample_summary(out_factors, out_returns),
        "in_sample_gate": in_sample_gate,
        "out_of_sample_gate": out_of_sample_gate,
        "decay": decay,
        "segment_validation": segment_validation,
        "approval": approval,
    }


def write_factor_validation_review(
    review: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    factor_name = str(review["factor_name"])
    json_path = output_path / f"factor_validation_review_{factor_name}.json"
    markdown_path = output_path / f"factor_validation_review_{factor_name}.md"
    decay_csv_path = output_path / f"factor_validation_decay_{factor_name}.csv"

    json_path.write_text(
        json.dumps(_to_jsonable(review), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(review), encoding="utf-8")
    pd.DataFrame(review["decay"]["rows"]).to_csv(decay_csv_path, index=False)

    paths = {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "decay_csv_path": str(decay_csv_path),
    }
    segment_rows = review.get("segment_validation", {}).get("rows", [])
    if segment_rows:
        segment_csv_path = output_path / f"factor_validation_segments_{factor_name}.csv"
        pd.DataFrame(segment_rows).to_csv(segment_csv_path, index=False)
        paths["segment_csv_path"] = str(segment_csv_path)
    return paths


def _normalize_trade_dates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str[:10]
    return result


def _build_sample_summary(factors: pd.DataFrame, returns: pd.DataFrame) -> dict[str, int]:
    return {
        "factor_rows": int(len(factors)),
        "return_rows": int(len(returns)),
        "date_count": int(factors["trade_date"].nunique()) if "trade_date" in factors else 0,
    }


def _decide_sample_gate(
    factor_name: str,
    multi_horizon_report: dict[str, Any],
    *,
    primary_horizon: int,
    thresholds: dict[str, float | int],
) -> dict[str, Any]:
    reports = multi_horizon_report.get("reports", {})
    primary = reports.get(primary_horizon)
    if primary is None:
        return {
            "factor_name": factor_name,
            "status": "rejected",
            "reason": "missing_primary_horizon",
            "primary_horizon": primary_horizon,
            "thresholds": thresholds,
        }

    summary = primary.get("ic_summary", {})
    mean_ic = _optional_float(summary.get("mean_ic"))
    icir = _optional_float(summary.get("icir"))
    ic_count = int(summary.get("ic_count") or 0)
    min_abs_mean_ic = float(thresholds["min_abs_mean_ic"])
    min_icir = float(thresholds["min_icir"])
    min_ic_count = int(thresholds["min_ic_count"])

    if ic_count < min_ic_count:
        status = "rejected"
        reason = "insufficient_ic_count"
    elif mean_ic is None or abs(mean_ic) < min_abs_mean_ic:
        status = "rejected"
        reason = "mean_ic_below_threshold"
    elif min_icir > 0 and (icir is None or abs(icir) < min_icir):
        status = "rejected"
        reason = "icir_below_threshold"
    else:
        status = "approved"
        reason = "passed_thresholds"

    return {
        "factor_name": factor_name,
        "status": status,
        "reason": reason,
        "primary_horizon": primary_horizon,
        "mean_ic": mean_ic,
        "icir": icir,
        "ic_count": ic_count,
        "thresholds": thresholds,
    }


def _build_decay_summary(
    multi_horizon_report: dict[str, Any],
    *,
    primary_horizon: int,
) -> dict[str, Any]:
    rows = []
    reports = multi_horizon_report.get("reports", {})
    for horizon in multi_horizon_report.get("horizons", []):
        summary = reports[int(horizon)].get("ic_summary", {})
        mean_ic = _optional_float(summary.get("mean_ic"))
        rows.append(
            {
                "horizon": int(horizon),
                "mean_ic": mean_ic,
                "abs_mean_ic": abs(mean_ic) if mean_ic is not None else None,
                "icir": _optional_float(summary.get("icir")),
                "ic_count": int(summary.get("ic_count") or 0),
                "direction": _direction(mean_ic),
            }
        )
    return {"primary_horizon": int(primary_horizon), "rows": rows}


def _build_segment_validation(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    segments: pd.DataFrame | None,
    segment_col: str | None,
    factor_col: str,
    primary_horizon: int,
) -> dict[str, Any]:
    if segments is None or not segment_col:
        return {"segment_col": segment_col, "rows": []}

    segment_frame = summarize_return_by_segment(
        factors,
        returns,
        segments,
        segment_col=segment_col,
        factor_col=factor_col,
        return_col=f"forward_return_{primary_horizon}d",
    )
    return {
        "segment_col": segment_col,
        "rows": _records(segment_frame),
    }


def _decide_approval(
    *,
    in_sample_gate: dict[str, Any],
    out_of_sample_gate: dict[str, Any],
) -> dict[str, Any]:
    if in_sample_gate["status"] != "approved":
        return {"status": "rejected", "reason": "in_sample_gate_failed"}
    if out_of_sample_gate["status"] != "approved":
        return {"status": "rejected", "reason": "sample_out_gate_failed"}

    in_mean_ic = in_sample_gate.get("mean_ic")
    out_mean_ic = out_of_sample_gate.get("mean_ic")
    if in_mean_ic is not None and out_mean_ic is not None and in_mean_ic * out_mean_ic < 0:
        return {"status": "rejected", "reason": "sample_out_direction_flip"}
    return {"status": "approved_candidate", "reason": "passed_sample_out_decay_segment_review"}


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [_to_jsonable(row) for row in frame.to_dict(orient="records")]


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _direction(mean_ic: float | None) -> str:
    if mean_ic is None:
        return "missing"
    if mean_ic > 0:
        return "positive"
    if mean_ic < 0:
        return "negative"
    return "flat"


def _render_markdown(review: dict[str, Any]) -> str:
    approval = review["approval"]
    in_gate = review["in_sample_gate"]
    out_gate = review["out_of_sample_gate"]
    lines = [
        f"# Factor Validation Review: {review['factor_name']}",
        "",
        f"- 审批状态: {approval['status']}",
        f"- 审批原因: {approval['reason']}",
        f"- 样本内: {in_gate['status']} ({in_gate['reason']})",
        f"- 样本外: {out_gate['status']} ({out_gate['reason']})",
        f"- 主周期: {review['primary_horizon']}d",
        "",
        "## 衰减",
        "",
        "| horizon | mean_ic | icir | ic_count | direction |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in review["decay"]["rows"]:
        lines.append(
            f"| {row['horizon']} | {_fmt(row['mean_ic'])} | {_fmt(row['icir'])} | "
            f"{row['ic_count']} | {row['direction']} |"
        )
    segment_rows = review.get("segment_validation", {}).get("rows", [])
    if segment_rows:
        segment_col = review["segment_validation"]["segment_col"]
        lines.extend(["", "## 分市场状态", ""])
        for row in segment_rows:
            lines.append(f"- {segment_col}={row[segment_col]} mean_return={_fmt(row['mean_return'])} count={row['count']}")
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    if pd.isna(value):
        return None
    return value
