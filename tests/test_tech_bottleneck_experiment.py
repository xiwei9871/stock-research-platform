from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.cli import build_parser
from stock_research.tech_bottleneck_experiment import (
    build_historical_rescore_report,
    render_historical_rescore_summary,
    run_historical_rescore_from_files,
    write_historical_rescore_artifacts,
)


def _packets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_id": "packet-run",
                "candidate_source": "industry-focus",
                "asset_id": "A",
                "stock_name": "高分材料",
                "trade_date": "2026-01-02",
                "candidate_state": "conviction_candidate",
                "tech_bottleneck_score": 4.5,
                "chokepoint_score": 35.0,
                "underpricing_score": 32.0,
                "evidence_score": 5.0,
                "catalyst_score": 4.0,
                "risk_penalty": 1.0,
                "base_strategy_rank": 3,
                "base_strategy_score": 0.82,
            },
            {
                "run_id": "packet-run",
                "candidate_source": "industry-focus",
                "asset_id": "B",
                "stock_name": "中分设备",
                "trade_date": "2026-01-02",
                "candidate_state": "research",
                "tech_bottleneck_score": 2.8,
                "chokepoint_score": 23.0,
                "underpricing_score": 25.0,
                "evidence_score": 2.5,
                "catalyst_score": 2.0,
                "risk_penalty": 2.0,
                "base_strategy_rank": 8,
                "base_strategy_score": 0.70,
            },
            {
                "run_id": "packet-run",
                "candidate_source": "industry-focus",
                "asset_id": "C",
                "stock_name": "低分概念",
                "trade_date": "2026-01-02",
                "candidate_state": "reject",
                "tech_bottleneck_score": 1.1,
                "chokepoint_score": 10.0,
                "underpricing_score": 15.0,
                "evidence_score": 1.0,
                "catalyst_score": 1.0,
                "risk_penalty": 4.0,
                "base_strategy_rank": 12,
                "base_strategy_score": 0.60,
            },
        ]
    )


def _bars() -> pd.DataFrame:
    rows = []
    price_paths = {
        "A": [10.0, 11.0, 12.0, 13.0, 15.0, 18.0],
        "B": [20.0, 19.0, 21.0, 20.0, 22.0, 23.0],
        "C": [30.0, 27.0, 24.0, 22.0, 21.0, 20.0],
    }
    dates = [
        "2026-01-02",
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
        "2026-01-08",
        "2026-01-09",
    ]
    for asset_id, prices in price_paths.items():
        for trade_date, close in zip(dates, prices, strict=True):
            rows.append({"asset_id": asset_id, "trade_date": trade_date, "close": close})
    return pd.DataFrame(rows)


def test_build_historical_rescore_report_computes_horizon_returns_and_drawdowns() -> None:
    report = build_historical_rescore_report(
        packets=_packets(),
        bars=_bars(),
        run_id="rescore-run",
        horizons=(1, 2, 4, 5),
    )
    outcomes = report["outcomes"].set_index("asset_id")

    assert outcomes.loc["A", "bucket"] == "high"
    assert outcomes.loc["A", "return_1d"] == 0.10
    assert outcomes.loc["A", "return_4d"] == 0.50
    assert outcomes.loc["A", "max_drawdown_4d"] == 0.0
    assert outcomes.loc["A", "horizon_5d_status"] == "complete"

    assert outcomes.loc["C", "bucket"] == "low"
    assert round(float(outcomes.loc["C", "return_4d"]), 4) == -0.30
    assert round(float(outcomes.loc["C", "max_drawdown_4d"]), 4) == -0.30


def test_build_historical_rescore_report_summarizes_buckets() -> None:
    report = build_historical_rescore_report(
        packets=_packets(),
        bars=_bars(),
        run_id="rescore-run",
        horizons=(1, 2, 4),
    )
    summary = report["bucket_summary"].set_index("bucket")

    assert summary.loc["high", "candidate_count"] == 1
    assert summary.loc["medium", "candidate_count"] == 1
    assert summary.loc["low", "candidate_count"] == 1
    assert summary.loc["high", "mean_return_4d"] == 0.5
    assert summary.loc["low", "mean_return_4d"] == -0.3
    assert summary.loc["high", "excess_return_4d"] > 0


def test_render_historical_rescore_summary_labels_horizon_roles() -> None:
    report = build_historical_rescore_report(
        packets=_packets(),
        bars=_bars(),
        run_id="rescore-run",
        horizons=(20, 60, 120, 250, 500),
    )

    markdown = render_historical_rescore_summary(
        run_id="rescore-run",
        bucket_summary=report["bucket_summary"],
        horizons=(20, 60, 120, 250, 500),
    )

    assert "Short-term diagnostics: 20D / 60D" in markdown
    assert "Primary validation: 120D / 250D" in markdown
    assert "Long-cycle observation: 500D" in markdown
    assert "### high" in markdown


def test_write_historical_rescore_artifacts(tmp_path: Path) -> None:
    report = build_historical_rescore_report(
        packets=_packets(),
        bars=_bars(),
        run_id="rescore-run",
        horizons=(1, 2, 4),
    )

    paths = write_historical_rescore_artifacts(
        report=report,
        output_dir=tmp_path,
        run_id="rescore-run",
        horizons=(1, 2, 4),
    )

    assert paths["outcomes"].exists()
    assert paths["bucket_summary"].exists()
    assert paths["summary"].exists()
    assert "tech-bottleneck historical rescore summary" in paths["summary"].read_text(encoding="utf-8")


def test_run_historical_rescore_from_files(tmp_path: Path) -> None:
    packets_csv = tmp_path / "packets.csv"
    bars_csv = tmp_path / "bars.csv"
    output_dir = tmp_path / "out"
    _packets().to_csv(packets_csv, index=False)
    _bars().to_csv(bars_csv, index=False)

    paths = run_historical_rescore_from_files(
        packets_csv=packets_csv,
        bars_csv=bars_csv,
        output_dir=output_dir,
        run_id="rescore-run",
        horizons=(1, 2, 4),
    )

    assert paths["outcomes"] == output_dir / "outcomes.csv"
    outcomes = pd.read_csv(paths["outcomes"])
    assert set(outcomes["asset_id"]) == {"A", "B", "C"}
    summary = pd.read_csv(paths["bucket_summary"]).set_index("bucket")
    assert summary.loc["high", "candidate_count"] == 1


def test_cli_parser_accepts_historical_rescore_command() -> None:
    args = build_parser().parse_args(
        [
            "tech-bottleneck-historical-rescore",
            "--packets-csv",
            "packets.csv",
            "--bars-csv",
            "bars.csv",
            "--output-dir",
            "out",
            "--run-id",
            "run",
            "--horizons",
            "20,60,120",
        ]
    )

    assert args.command == "tech-bottleneck-historical-rescore"
    assert args.horizons == "20,60,120"
