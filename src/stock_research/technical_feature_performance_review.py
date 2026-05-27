from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


HOTSPOTS = ["_wilder_average", "RSI", "ADX", "batch-level vectorization"]


def build_technical_feature_performance_review(
    *,
    compare_benchmark: dict[str, Any],
    regression: dict[str, Any],
    store_benchmark: dict[str, Any] | None = None,
    min_speedup_ratio: float = 1.0,
) -> dict[str, Any]:
    regression_passed = bool(regression.get("gate", {}).get("passed"))
    speedup_ratio = float(compare_benchmark.get("speedup_ratio") or 0.0)
    if not regression_passed:
        gate = {"status": "rejected", "reason": "regression_gate_failed"}
    elif speedup_ratio < min_speedup_ratio:
        gate = {"status": "rejected", "reason": "compute_speedup_below_threshold"}
    else:
        gate = {"status": "passed", "reason": "regression_and_speedup_passed"}

    return {
        "gate": {
            **gate,
            "min_speedup_ratio": float(min_speedup_ratio),
        },
        "regression_status": "passed" if regression_passed else "failed",
        "hotspots": list(HOTSPOTS),
        "compute_benchmark": _to_jsonable(compare_benchmark),
        "store_benchmark": _to_jsonable(store_benchmark or {}),
        "regression": _to_jsonable(regression),
        "metrics": _build_metric_rows(
            compare_benchmark=compare_benchmark,
            regression=regression,
            store_benchmark=store_benchmark or {},
        ),
    }


def write_technical_feature_performance_review(
    review: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    json_path = output_path / "technical_feature_performance_review.json"
    markdown_path = output_path / "technical_feature_performance_review.md"
    metrics_csv_path = output_path / "technical_feature_performance_metrics.csv"

    json_path.write_text(
        json.dumps(_to_jsonable(review), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(review), encoding="utf-8")
    pd.DataFrame(review["metrics"]).to_csv(metrics_csv_path, index=False)

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "metrics_csv_path": str(metrics_csv_path),
    }


def _build_metric_rows(
    *,
    compare_benchmark: dict[str, Any],
    regression: dict[str, Any],
    store_benchmark: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "metric": "compute_speedup_ratio",
            "value": _optional_float(compare_benchmark.get("speedup_ratio")),
        },
        {
            "metric": "store_batch_speedup_ratio",
            "value": _optional_float(store_benchmark.get("speedup_ratio")),
        },
        {
            "metric": "store_latest_only_speedup_ratio",
            "value": _optional_float(store_benchmark.get("latest_only_speedup_ratio")),
        },
        {
            "metric": "max_abs_diff",
            "value": _optional_float(regression.get("max_abs_diff")),
        },
        {
            "metric": "mean_abs_diff",
            "value": _optional_float(regression.get("mean_abs_diff")),
        },
        {
            "metric": "nan_mismatch_count",
            "value": int(regression.get("nan_mismatch_count") or 0),
        },
    ]


def _render_markdown(review: dict[str, Any]) -> str:
    gate = review["gate"]
    lines = [
        "# Technical Feature Performance Review",
        "",
        f"- Gate: {gate['status']}",
        f"- Reason: {gate['reason']}",
        f"- Regression: {review['regression_status']}",
        f"- Hotspots: {', '.join(review['hotspots'])}",
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for row in review["metrics"]:
        lines.append(f"| {row['metric']} | {_fmt(row['value'])} |")
    return "\n".join(lines) + "\n"


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


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
    if value is None:
        return None
    if pd.isna(value):
        return None
    return value
