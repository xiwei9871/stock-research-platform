from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.trend_discovery_v2_replay import build_trend_discovery_v2_replay


def _template_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "event_structure": "trend_continuation_candidate",
                "watch_group": "opportunity_watch",
                "mainline_context": "mainline",
                "fundamental_quality_bucket": "expectation_growth",
                "time_series_momentum_template": True,
                "relative_strength_template": True,
                "dual_momentum_template": True,
                "minervini_like_template": True,
                "future_10d_return": 0.10,
                "future_20d_return": 0.20,
                "future_30d_return": 0.30,
                "future_40d_return": 0.40,
                "future_60d_return": 0.70,
                "future_20d_max_drawdown": -0.05,
                "future_60d_max_drawdown": -0.10,
                "max_return_within_60d": 1.10,
                "hit_double_within_60d": True,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "event_structure": "",
                "watch_group": "candidate",
                "mainline_context": "mainline",
                "fundamental_quality_bucket": "cyclical_or_turnaround",
                "time_series_momentum_template": True,
                "relative_strength_template": False,
                "dual_momentum_template": False,
                "minervini_like_template": False,
                "future_10d_return": 0.02,
                "future_20d_return": 0.03,
                "future_30d_return": 0.04,
                "future_40d_return": 0.05,
                "future_60d_return": 0.06,
                "future_20d_max_drawdown": -0.08,
                "future_60d_max_drawdown": -0.16,
                "max_return_within_60d": 0.30,
                "hit_double_within_60d": False,
            },
        ]
    )


def _strong_winners() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"winner_id": "W1", "asset_id": "A", "capture_status": "captured_pre_double"},
            {"winner_id": "W2", "asset_id": "Z", "capture_status": "missed"},
        ]
    )


def test_trend_discovery_v2_replay_builds_funnel_layers_and_outputs(tmp_path: Path):
    result = build_trend_discovery_v2_replay(
        template_detail=_template_detail(),
        strong_winners=_strong_winners(),
        output_dir=tmp_path,
    )

    detail = result["detail"]
    assert bool(detail.loc[detail["asset_id"].eq("A"), "trend_discovery_v2_recall"].iloc[0]) is True
    assert bool(detail.loc[detail["asset_id"].eq("A"), "trend_discovery_v2_final_candidate"].iloc[0]) is True
    assert bool(detail.loc[detail["asset_id"].eq("B"), "trend_discovery_v2_recall"].iloc[0]) is True
    assert bool(detail.loc[detail["asset_id"].eq("B"), "trend_discovery_v2_final_candidate"].iloc[0]) is False
    assert set(result["layer_effectiveness"]["v2_layer"]) >= {
        "v2_recall",
        "v2_core",
        "v2_high_purity",
        "v2_final_candidate",
    }
    assert "captured_strong_winner_count" in result["strong_winner_capture"].columns
    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["layer_effectiveness"]).exists()
    assert Path(result["paths"]["vs_existing"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_trend_discovery_v2_replay_compares_existing_trend_continuation():
    result = build_trend_discovery_v2_replay(template_detail=_template_detail(), strong_winners=_strong_winners())

    comparison = result["vs_existing"]
    assert {"existing_trend_continuation", "v2_final_candidate"} <= set(comparison["candidate_set"])


def test_cli_dispatches_trend_discovery_v2_replay(monkeypatch, capsys, tmp_path: Path):
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

    monkeypatch.setattr(cli, "run_trend_discovery_v2_replay", fake_run)
    cli.main_for_args(
        [
            "replay-trend-discovery-v2",
            "--template-detail",
            "outputs/research/trend_discovery_template_detail.csv",
            "--strong-winner-path",
            "outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["template_detail_path"] == "outputs/research/trend_discovery_template_detail.csv"
    out = capsys.readouterr().out
    assert "trend_discovery_v2_replay|layer_effectiveness|" in out
    assert "trend_discovery_v2_replay|recommendations|" in out
