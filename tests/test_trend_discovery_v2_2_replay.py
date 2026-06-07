from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.trend_discovery_v2_2_replay import build_trend_discovery_v2_2_replay


def _v2_purity_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "stock_name": "Growth",
                "sector_strength_bucket": "top_10",
                "fundamental_quality_bucket": "expectation_growth",
                "event_structure": "",
                "amount_vs_20d_bucket": "moderate_volume",
                "volatility_5d_bucket": "low_volatility",
                "trend_discovery_v2_final_candidate": True,
                "future_10d_return": 0.08,
                "future_20d_return": 0.15,
                "future_30d_return": 0.25,
                "future_40d_return": 0.30,
                "future_60d_return": 0.45,
                "future_20d_max_drawdown": -0.05,
                "future_60d_max_drawdown": -0.09,
                "max_return_within_60d": 0.60,
                "hit_double_within_60d": False,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "B",
                "ts_code": "000002.SZ",
                "stock_name": "Cyclical",
                "sector_strength_bucket": "top_30",
                "fundamental_quality_bucket": "cyclical_or_turnaround",
                "event_structure": "",
                "amount_vs_20d_bucket": "moderate_volume",
                "volatility_5d_bucket": "mid_volatility",
                "trend_discovery_v2_final_candidate": True,
                "future_10d_return": 0.04,
                "future_20d_return": 0.10,
                "future_30d_return": 0.18,
                "future_40d_return": 0.22,
                "future_60d_return": 0.28,
                "future_20d_max_drawdown": -0.07,
                "future_60d_max_drawdown": -0.12,
                "max_return_within_60d": 0.42,
                "hit_double_within_60d": False,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "C",
                "ts_code": "000003.SZ",
                "stock_name": "Trend",
                "sector_strength_bucket": "top_10",
                "fundamental_quality_bucket": "expectation_growth",
                "event_structure": "trend_continuation_candidate",
                "amount_vs_20d_bucket": "moderate_volume",
                "volatility_5d_bucket": "low_volatility",
                "trend_discovery_v2_final_candidate": True,
                "future_10d_return": 0.12,
                "future_20d_return": 0.25,
                "future_30d_return": 0.38,
                "future_40d_return": 0.50,
                "future_60d_return": 0.80,
                "future_20d_max_drawdown": -0.04,
                "future_60d_max_drawdown": -0.08,
                "max_return_within_60d": 1.10,
                "hit_double_within_60d": True,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "D",
                "ts_code": "000004.SZ",
                "stock_name": "Elastic",
                "sector_strength_bucket": "top_10",
                "fundamental_quality_bucket": "expectation_growth",
                "event_structure": "",
                "amount_vs_20d_bucket": "extreme_volume",
                "volatility_5d_bucket": "high_volatility",
                "trend_discovery_v2_final_candidate": True,
                "future_10d_return": -0.03,
                "future_20d_return": -0.06,
                "future_30d_return": -0.08,
                "future_40d_return": -0.10,
                "future_60d_return": -0.15,
                "future_20d_max_drawdown": -0.16,
                "future_60d_max_drawdown": -0.25,
                "max_return_within_60d": 0.22,
                "hit_double_within_60d": False,
            },
        ]
    )


def _strong_winners() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"winner_id": "W1", "asset_id": "C"},
            {"winner_id": "W2", "asset_id": "Z"},
        ]
    )


def test_v2_2_replay_builds_candidate_layers_and_outputs(tmp_path: Path):
    result = build_trend_discovery_v2_2_replay(
        v2_detail=_v2_purity_detail(),
        strong_winners=_strong_winners(),
        output_dir=tmp_path,
    )

    detail = result["detail"]
    assert bool(detail.loc[detail["asset_id"].eq("A"), "v2_2_growth_trend_core"].iloc[0]) is True
    assert bool(detail.loc[detail["asset_id"].eq("B"), "v2_2_cyclical_trend_core"].iloc[0]) is True
    assert bool(detail.loc[detail["asset_id"].eq("C"), "v2_2_trend_continuation_boost"].iloc[0]) is True
    assert bool(detail.loc[detail["asset_id"].eq("D"), "v2_2_high_elasticity_shadow"].iloc[0]) is True
    assert bool(detail.loc[detail["asset_id"].eq("D"), "v2_1_quality_no_highvol_extremeamount"].iloc[0]) is False

    assert set(result["layer_effectiveness"]["candidate_set"]) >= {
        "v2_final_baseline",
        "v2_1_quality_no_highvol_extremeamount",
        "v2_2_growth_trend_core",
        "v2_2_cyclical_trend_core",
        "v2_2_trend_continuation_boost",
        "v2_2_high_elasticity_shadow",
        "existing_trend_continuation_candidate",
    }
    assert "capture_rate" in result["strong_winner_capture"].columns
    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["layer_effectiveness"]).exists()
    assert Path(result["paths"]["strong_winner_capture"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_v2_2_replay_recommends_core_and_keeps_elasticity_separate():
    result = build_trend_discovery_v2_2_replay(v2_detail=_v2_purity_detail(), strong_winners=_strong_winners())

    recommendations = result["recommendations"]
    assert "keep_high_elasticity_as_shadow" in set(recommendations["recommendation"])
    assert recommendations["next_action"].str.contains("watchlist").any()


def test_cli_dispatches_v2_2_replay(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "layer_effectiveness": str(tmp_path / "layers.csv"),
                "vs_existing": str(tmp_path / "vs.csv"),
                "strong_winner_capture": str(tmp_path / "capture.csv"),
                "recommendations": str(tmp_path / "recommendations.csv"),
                "report": str(tmp_path / "report.md"),
            },
            "warnings": [],
        }

    monkeypatch.setattr(cli, "run_trend_discovery_v2_2_replay", fake_run)
    cli.main_for_args(
        [
            "replay-trend-discovery-v2-2",
            "--v2-detail",
            "outputs/research/trend_discovery_v2_purity_detail.csv",
            "--strong-winner-path",
            "outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["v2_detail_path"] == "outputs/research/trend_discovery_v2_purity_detail.csv"
    out = capsys.readouterr().out
    assert "trend_discovery_v2_2_replay|layer_effectiveness|" in out
    assert "trend_discovery_v2_2_replay|recommendations|" in out
