import json
from pathlib import Path

import pandas as pd

from stock_research.technical_feature_performance_review import (
    build_technical_feature_performance_review,
    write_technical_feature_performance_review,
)


def _compare_benchmark(speedup_ratio: float = 4.0) -> dict[str, float | int]:
    return {
        "asset_count": 16,
        "bar_count": 260,
        "repeat": 2,
        "legacy_total_seconds": 8.0,
        "fast_total_seconds": 2.0,
        "legacy_rows_per_second": 4.0,
        "fast_rows_per_second": 16.0,
        "speedup_ratio": speedup_ratio,
    }


def _store_benchmark() -> dict[str, float | int]:
    return {
        "asset_count": 16,
        "bar_count": 260,
        "legacy_total_seconds": 9.0,
        "batch_frame_total_seconds": 4.5,
        "latest_only_total_seconds": 3.0,
        "legacy_rows_written": 16,
        "batch_frame_rows_written": 16,
        "latest_only_rows_written": 16,
        "speedup_ratio": 2.0,
        "latest_only_speedup_ratio": 3.0,
    }


def _regression(passed: bool = True) -> dict[str, object]:
    return {
        "asset_count": 16,
        "bar_count": 260,
        "column_count": 34,
        "scenario_count": 5,
        "max_abs_diff": 0.0 if passed else 0.01,
        "mean_abs_diff": 0.0,
        "nan_mismatch_count": 0,
        "gate": {
            "passed": passed,
            "thresholds": {
                "max_abs_diff": 1e-12,
                "mean_abs_diff": 1e-12,
                "nan_mismatch_count": 0,
            },
        },
    }


def test_build_technical_feature_performance_review_passes_when_regression_and_speedup_pass():
    review = build_technical_feature_performance_review(
        compare_benchmark=_compare_benchmark(),
        regression=_regression(),
        store_benchmark=_store_benchmark(),
        min_speedup_ratio=1.5,
    )

    assert review["gate"]["status"] == "passed"
    assert review["regression_status"] == "passed"
    assert review["compute_benchmark"]["speedup_ratio"] == 4.0
    assert "_wilder_average" in review["hotspots"]
    assert "RSI" in review["hotspots"]
    assert "ADX" in review["hotspots"]


def test_build_technical_feature_performance_review_rejects_when_regression_fails():
    review = build_technical_feature_performance_review(
        compare_benchmark=_compare_benchmark(),
        regression=_regression(passed=False),
        min_speedup_ratio=1.5,
    )

    assert review["gate"]["status"] == "rejected"
    assert review["gate"]["reason"] == "regression_gate_failed"


def test_write_technical_feature_performance_review_outputs_audit_artifacts(tmp_path):
    review = build_technical_feature_performance_review(
        compare_benchmark=_compare_benchmark(),
        regression=_regression(),
        store_benchmark=_store_benchmark(),
        min_speedup_ratio=1.5,
    )

    paths = write_technical_feature_performance_review(review, output_dir=tmp_path)

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    metrics = pd.read_csv(paths["metrics_csv_path"])

    assert payload["gate"]["status"] == "passed"
    assert "_wilder_average" in markdown
    assert "RSI" in markdown
    assert "ADX" in markdown
    assert metrics["metric"].tolist() == [
        "compute_speedup_ratio",
        "store_batch_speedup_ratio",
        "store_latest_only_speedup_ratio",
        "max_abs_diff",
        "mean_abs_diff",
        "nan_mismatch_count",
    ]
