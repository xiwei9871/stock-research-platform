from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.strong_winner_topn_attribution import (
    build_strong_winner_topn_attribution_from_frames,
)


def _miss_analysis() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "winner_id": "SW60D-0001",
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "stock_name": "Alpha",
                "segment_start_date": "2025-01-01",
                "double_confirm_date": "2025-01-06",
                "low_to_peak_return": 1.5,
                "capture_status": "missed",
                "miss_reason": "not_in_topn_diagnostics",
            },
            {
                "winner_id": "SW60D-0002",
                "asset_id": "B",
                "ts_code": "000002.SZ",
                "stock_name": "Beta",
                "segment_start_date": "2025-01-01",
                "double_confirm_date": "2025-01-06",
                "low_to_peak_return": 1.2,
                "capture_status": "captured_pre_double",
                "miss_reason": "",
            },
            {
                "winner_id": "SW60D-0003",
                "asset_id": "C",
                "ts_code": "000003.SZ",
                "stock_name": "Gamma",
                "segment_start_date": "2025-01-01",
                "double_confirm_date": "2025-01-06",
                "low_to_peak_return": 1.1,
                "capture_status": "missed",
                "miss_reason": "not_in_topn_diagnostics",
            },
        ]
    )


def _scores() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "rank": 75,
                "score_total": 62.0,
                "score_components": {
                    "ret_20_score": 80,
                    "volatility_20_score": 20,
                    "amount_ratio_5_20_score": 35,
                },
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "rank": 55,
                "score_total": 66.0,
                "score_components": {
                    "ret_20_score": 85,
                    "volatility_20_score": 18,
                    "amount_ratio_5_20_score": 40,
                },
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "rank": 20,
                "score_total": 88.0,
                "score_components": {
                    "ret_20_score": 90,
                    "volatility_20_score": 70,
                    "amount_ratio_5_20_score": 80,
                },
            },
        ]
    )


def test_topn_attribution_classifies_rank_bands_and_no_score():
    result = build_strong_winner_topn_attribution_from_frames(
        miss_analysis=_miss_analysis(),
        score_rows=_scores(),
        topn_thresholds=[50, 100, 200],
    )

    attribution = result["attribution"].set_index("asset_id")
    assert attribution.loc["A", "best_pre_double_rank"] == 55
    assert attribution.loc["A", "topn_attribution"] == "near_miss_51_100"
    assert attribution.loc["C", "topn_attribution"] == "no_score_pre_double"

    sensitivity = result["threshold_sensitivity"].set_index("top_n")
    assert sensitivity.loc[50, "additional_captured_count"] == 0
    assert sensitivity.loc[100, "additional_captured_count"] == 1


def test_topn_attribution_summarizes_component_gaps_against_captured_reference():
    result = build_strong_winner_topn_attribution_from_frames(
        miss_analysis=_miss_analysis(),
        score_rows=_scores(),
        topn_thresholds=[50, 100],
    )

    gap = result["component_gap"].set_index("component")
    assert gap.loc["volatility_20_score", "miss_avg"] < gap.loc["volatility_20_score", "captured_avg"]
    assert gap.loc["amount_ratio_5_20_score", "miss_minus_captured"] < 0


def test_topn_attribution_writes_outputs(tmp_path: Path):
    result = build_strong_winner_topn_attribution_from_frames(
        miss_analysis=_miss_analysis(),
        score_rows=_scores(),
        topn_thresholds=[50, 100],
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["attribution"]).exists()
    assert Path(result["paths"]["threshold_sensitivity"]).exists()
    assert Path(result["paths"]["component_gap"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_strong_winner_topn_attribution(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "attribution": pd.DataFrame([{"asset_id": "A"}]),
            "paths": {
                "attribution": str(tmp_path / "attribution.csv"),
                "threshold_sensitivity": str(tmp_path / "threshold.csv"),
                "component_gap": str(tmp_path / "gap.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_strong_winner_topn_attribution", fake_run)

    cli.main_for_args(
        [
            "analyze-strong-winner-topn-source",
            "--miss-analysis-path",
            "outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
            "--score-version",
            "manual_v1",
            "--topn-thresholds",
            "50,100",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["topn_thresholds"] == [50, 100]
    out = capsys.readouterr().out
    assert "strong_winner_topn_source|attribution|" in out
    assert "strong_winner_topn_source|rows|1" in out
