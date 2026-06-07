from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.cli import build_parser
from stock_research.tech_bottleneck_observation_outcome import (
    build_observation_outcome,
    run_observation_outcome_from_files,
)


def _comparison_groups() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "comparison_group": "quality_promotion_pool",
                "asset_id": "A",
                "stock_name": "强证据",
                "observation_start_date": "2025-01-02",
                "source_trade_date": "2025-01-02",
                "product_family": "chrome_chemicals",
                "evidence_quality_score": 12,
            },
            {
                "comparison_group": "readiness_pass_pool",
                "asset_id": "B",
                "stock_name": "中证据",
                "observation_start_date": "2025-01-02",
                "source_trade_date": "2025-01-02",
                "product_family": "power_grid_equipment",
                "evidence_quality_score": 8,
            },
            {
                "comparison_group": "original_topn_candidates",
                "asset_id": "C",
                "stock_name": "原始候选",
                "observation_start_date": "2025-01-02",
                "source_trade_date": "2025-01-02",
                "product_family": "",
                "evidence_quality_score": 0,
            },
        ]
    )


def _bars() -> pd.DataFrame:
    rows = []
    dates = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"]
    prices = {
        "A": [10.0, 11.0, 12.0, 14.0],
        "B": [20.0, 18.0, 21.0, 22.0],
        "C": [30.0, 29.0, 28.0, 27.0],
        "BENCH": [100.0, 101.0, 102.0, 103.0],
    }
    for asset_id, closes in prices.items():
        for trade_date, close in zip(dates, closes, strict=True):
            rows.append({"asset_id": asset_id, "trade_date": trade_date, "close": close})
    return pd.DataFrame(rows)


def test_build_observation_outcome_computes_forward_and_excess_returns_by_group() -> None:
    report = build_observation_outcome(
        comparison_groups=_comparison_groups(),
        bars=_bars(),
        benchmark_asset_id="BENCH",
        horizons=[1, 2, 3],
    )

    outcomes = report["outcomes"].set_index("asset_id")
    assert outcomes.loc["A", "return_1d"] == 0.1
    assert outcomes.loc["A", "return_3d"] == 0.4
    assert outcomes.loc["A", "benchmark_return_3d"] == 0.03
    assert outcomes.loc["A", "excess_return_3d"] == 0.37
    assert outcomes.loc["A", "horizon_3d_status"] == "complete"
    assert outcomes.loc["B", "max_drawdown_2d"] == -0.1

    summary = report["group_summary"].set_index("comparison_group")
    assert summary.loc["quality_promotion_pool", "candidate_count"] == 1
    assert summary.loc["quality_promotion_pool", "complete_count_3d"] == 1
    assert summary.loc["quality_promotion_pool", "mean_return_3d"] == 0.4
    assert summary.loc["quality_promotion_pool", "mean_excess_return_3d"] == 0.37
    assert summary.loc["original_topn_candidates", "win_rate_3d"] == 0.0


def test_build_observation_outcome_marks_partial_horizons_when_bars_are_missing() -> None:
    report = build_observation_outcome(
        comparison_groups=_comparison_groups().head(1),
        bars=_bars().query("asset_id == 'A'").head(2),
        benchmark_asset_id=None,
        horizons=[1, 3],
    )

    row = report["outcomes"].iloc[0]
    assert row["horizon_1d_status"] == "complete"
    assert row["horizon_3d_status"] == "partial"
    assert pd.isna(row["return_3d"])


def test_run_observation_outcome_from_files_writes_artifacts(tmp_path: Path) -> None:
    comparison_csv = tmp_path / "comparison_groups.csv"
    bars_csv = tmp_path / "bars.csv"
    source_manifest = tmp_path / "observation_manifest.json"
    _comparison_groups().to_csv(comparison_csv, index=False)
    _bars().to_csv(bars_csv, index=False)
    source_manifest.write_text(json.dumps({"observation_asset_count": 3}), encoding="utf-8")

    paths = run_observation_outcome_from_files(
        comparison_groups_csv=comparison_csv,
        bars_csv=bars_csv,
        output_dir=tmp_path / "out",
        source_manifest_path=source_manifest,
        benchmark_asset_id="BENCH",
        horizons=[1, 2, 3],
    )

    assert paths["outcomes"].exists()
    assert paths["group_summary"].exists()
    assert paths["summary"].exists()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["inputs"]["comparison_groups_csv"] == str(comparison_csv)
    assert manifest["inputs"]["source_manifest"]["observation_asset_count"] == 3
    assert manifest["benchmark_asset_id"] == "BENCH"


def test_cli_parser_accepts_observation_outcome_command() -> None:
    args = build_parser().parse_args(
        [
            "tech-bottleneck-observation-outcome",
            "--comparison-groups-csv",
            "groups.csv",
            "--bars-csv",
            "bars.csv",
            "--output-dir",
            "out",
            "--source-manifest",
            "manifest.json",
            "--benchmark-asset-id",
            "BENCH",
            "--horizons",
            "120,250,500",
        ]
    )

    assert args.command == "tech-bottleneck-observation-outcome"
    assert args.horizons == "120,250,500"
