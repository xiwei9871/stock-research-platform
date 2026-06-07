from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.strong_winner_capture_gap import build_strong_winner_capture_gap_analysis


def _taxonomy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "winner_id": "W1",
                "winner_type": "double_60d",
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "stock_name": "Alpha",
                "window_start": "2025-01-01",
                "window_end": "2025-02-28",
                "max_return": 1.2,
                "max_drawdown": -0.12,
            },
            {
                "winner_id": "W2",
                "winner_type": "burst_20d",
                "asset_id": "B",
                "ts_code": "000002.SZ",
                "stock_name": "Beta",
                "window_start": "2025-01-01",
                "window_end": "2025-01-30",
                "max_return": 0.5,
                "max_drawdown": -0.06,
            },
            {
                "winner_id": "W3",
                "winner_type": "stable_trend_60d",
                "asset_id": "C",
                "ts_code": "000003.SZ",
                "stock_name": "Gamma",
                "window_start": "2025-01-01",
                "window_end": "2025-02-28",
                "max_return": 0.7,
                "max_drawdown": -0.08,
            },
        ]
    )


def _detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-05",
                "asset_id": "A",
                "score_rank": 180,
                "time_series_momentum_template": False,
                "relative_strength_template": False,
                "dual_momentum_template": False,
                "minervini_like_template": False,
                "trend_discovery_v2_recall": False,
                "v2_final_baseline": False,
                "v2_1_quality_no_highvol_extremeamount": False,
                "v2_2_growth_trend_core": False,
                "v2_2_cyclical_trend_core": False,
                "v2_2_high_elasticity_shadow": False,
                "sector_strength_bucket": "weak",
                "mainline_context": "rotation",
                "fundamental_hard_risk": False,
                "fundamental_quality_bucket": "expectation_growth",
                "dragon_risk_score": 0.2,
                "lhb_risk_score": 0.1,
            },
            {
                "trade_date": "2025-01-05",
                "asset_id": "B",
                "score_rank": 35,
                "time_series_momentum_template": True,
                "relative_strength_template": True,
                "dual_momentum_template": True,
                "minervini_like_template": False,
                "trend_discovery_v2_recall": True,
                "v2_final_baseline": False,
                "v2_1_quality_no_highvol_extremeamount": False,
                "v2_2_growth_trend_core": False,
                "v2_2_cyclical_trend_core": False,
                "v2_2_high_elasticity_shadow": False,
                "sector_strength_bucket": "top_10",
                "mainline_context": "mainline",
                "fundamental_hard_risk": True,
                "fundamental_quality_bucket": "growth_worsening",
                "dragon_risk_score": 0.1,
                "lhb_risk_score": 0.1,
            },
        ]
    )


def test_capture_gap_analysis_classifies_gap_dimensions_and_writes_outputs(tmp_path: Path):
    result = build_strong_winner_capture_gap_analysis(
        taxonomy=_taxonomy(),
        v2_detail=_detail(),
        output_dir=tmp_path,
    )

    detail = result["detail"].set_index("winner_id")
    assert detail.loc["W1", "primary_gap_category"] == "technical_gap"
    assert detail.loc["W2", "primary_gap_category"] == "fundamental_gap"
    assert detail.loc["W3", "primary_gap_category"] == "diagnostics_coverage_gap"
    assert {"minute_data_gap", "theme_sentiment_gap"} <= set(result["summary"]["gap_category"])
    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_capture_gap_analysis_keeps_captured_rows_out_of_uncaptured_summary():
    detail = _detail()
    detail.loc[detail["asset_id"].eq("A"), "v2_final_baseline"] = True

    result = build_strong_winner_capture_gap_analysis(taxonomy=_taxonomy(), v2_detail=detail)

    rows = result["detail"].set_index("winner_id")
    assert bool(rows.loc["W1", "captured_by_v2_final"]) is True
    assert rows.loc["W1", "primary_gap_category"] == "captured"


def test_cli_dispatches_capture_gap_analysis(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "by_type": str(tmp_path / "by_type.csv"),
                "sample": str(tmp_path / "sample.csv"),
                "report": str(tmp_path / "report.md"),
            },
            "warnings": [],
            "detail": pd.DataFrame([{"winner_id": "W1"}]),
        }

    monkeypatch.setattr(cli, "run_strong_winner_capture_gap_analysis", fake_run)
    cli.main_for_args(
        [
            "analyze-strong-winner-capture-gap",
            "--taxonomy-path",
            "outputs/research/strong_winner_taxonomy_v2_2025_to_now.csv",
            "--v2-detail-path",
            "outputs/research/trend_discovery_v2_2_replay_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["taxonomy_path"] == "outputs/research/strong_winner_taxonomy_v2_2025_to_now.csv"
    out = capsys.readouterr().out
    assert "strong_winner_capture_gap|detail|" in out
    assert "strong_winner_capture_gap|summary|" in out
