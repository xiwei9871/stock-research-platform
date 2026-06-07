from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.trend_discovery_v2_purity import build_trend_discovery_v2_purity_audit


def _v2_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "stock_name": "A",
                "score_rank": 8,
                "sector_strength_bucket": "top_10",
                "fundamental_quality_bucket": "expectation_growth",
                "event_structure": "trend_continuation_candidate",
                "amount_vs_20d": 1.8,
                "volatility_5d": 0.03,
                "high_to_close_drawdown": 0.02,
                "template_hit_count": 5,
                "trend_discovery_v2_recall": True,
                "trend_discovery_v2_core": True,
                "trend_discovery_v2_high_purity": True,
                "trend_discovery_v2_final_candidate": True,
                "future_10d_return": 0.10,
                "future_20d_return": 0.20,
                "future_30d_return": 0.30,
                "future_40d_return": 0.35,
                "future_60d_return": 0.60,
                "future_20d_max_drawdown": -0.05,
                "future_60d_max_drawdown": -0.10,
                "max_return_within_60d": 0.90,
                "hit_double_within_60d": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "ts_code": "000002.SZ",
                "stock_name": "B",
                "score_rank": 80,
                "sector_strength_bucket": "mid",
                "fundamental_quality_bucket": "growth_worsening",
                "event_structure": "",
                "amount_vs_20d": 5.0,
                "volatility_5d": 0.08,
                "high_to_close_drawdown": 0.12,
                "template_hit_count": 2,
                "trend_discovery_v2_recall": True,
                "trend_discovery_v2_core": True,
                "trend_discovery_v2_high_purity": False,
                "trend_discovery_v2_final_candidate": True,
                "future_10d_return": -0.05,
                "future_20d_return": -0.08,
                "future_30d_return": -0.10,
                "future_40d_return": -0.12,
                "future_60d_return": -0.20,
                "future_20d_max_drawdown": -0.18,
                "future_60d_max_drawdown": -0.30,
                "max_return_within_60d": 0.12,
                "hit_double_within_60d": False,
            },
        ]
    )


def _strong_winners() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"winner_id": "W1", "asset_id": "A"},
            {"winner_id": "W2", "asset_id": "Z"},
        ]
    )


def test_v2_purity_audit_generates_slices_and_recommendations(tmp_path: Path):
    result = build_trend_discovery_v2_purity_audit(
        v2_detail=_v2_detail(),
        strong_winners=_strong_winners(),
        output_dir=tmp_path,
    )

    assert not result["purity_slice"].empty
    assert {"score_rank_bucket", "amount_vs_20d_bucket", "template_hit_bucket"} <= set(
        result["detail"].columns
    )
    assert not result["bad_slice_audit"].empty
    assert not result["high_elasticity_slice"].empty
    assert not result["v2_1_candidate_effectiveness"].empty
    assert "v2_1_quality_no_highvol_extremeamount" in set(result["v2_1_candidate_effectiveness"]["candidate_set"])
    missed = result["missed_winner_audit"]
    assert "miss_reason" in missed.columns
    assert set(result["recommendations"]["recommendation"]) >= {"tighten_v2_final_candidate"}
    assert Path(result["paths"]["purity_slice"]).exists()
    assert Path(result["paths"]["bad_slice_audit"]).exists()
    assert Path(result["paths"]["high_elasticity_slice"]).exists()
    assert Path(result["paths"]["v2_1_candidate_effectiveness"]).exists()
    assert Path(result["paths"]["missed_winner_audit"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_v2_purity_audit(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "paths": {
                "purity_slice": str(tmp_path / "slice.csv"),
                "bad_slice_audit": str(tmp_path / "bad.csv"),
                "high_elasticity_slice": str(tmp_path / "elastic.csv"),
                "v2_1_candidate_effectiveness": str(tmp_path / "v21.csv"),
                "missed_winner_audit": str(tmp_path / "missed.csv"),
                "recommendations": str(tmp_path / "recommendations.csv"),
                "report": str(tmp_path / "report.md"),
            },
            "warnings": [],
        }

    monkeypatch.setattr(cli, "run_trend_discovery_v2_purity_audit", fake_run)
    cli.main_for_args(
        [
            "audit-trend-discovery-v2-purity",
            "--v2-detail",
            "outputs/research/trend_discovery_v2_replay_detail.csv",
            "--strong-winner-path",
            "outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["v2_detail_path"] == "outputs/research/trend_discovery_v2_replay_detail.csv"
    out = capsys.readouterr().out
    assert "trend_discovery_v2_purity|purity_slice|" in out
    assert "trend_discovery_v2_purity|v2_1_candidate_effectiveness|" in out
    assert "trend_discovery_v2_purity|recommendations|" in out
