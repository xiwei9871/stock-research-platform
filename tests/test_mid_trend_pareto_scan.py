from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_pareto_scan import build_mid_trend_pareto_scan_from_frames


def _detail() -> pd.DataFrame:
    rows = []
    for trade_date in ["2025-01-02", "2025-01-03"]:
        for idx, layer, vol, atr, dd_score, trend_r2, ma60, ret60, dd60, double in [
            (1, "stable_trend_watch", 70, 65, 85, 90, 88, 0.20, -0.10, False),
            (2, "mainline_momentum_watch", 45, 40, 70, 75, 82, 0.16, -0.12, False),
            (3, "pullback_reacceleration_watch", 30, 30, 60, 72, 78, 0.14, -0.13, False),
            (4, "high_elasticity_watch", 22, 18, 62, 78, 84, 0.35, -0.18, True),
            (5, "high_elasticity_watch", 8, 10, 35, 42, 70, 0.45, -0.35, True),
        ]:
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": f"{trade_date}-{idx}",
                    "mid_trend_layer": layer,
                    "mid_trend_funnel_score": 100 - idx,
                    "score_rank": idx,
                    "volatility_20_score": vol,
                    "atr_pct_score": atr,
                    "max_drawdown_20_score": dd_score,
                    "trend_r2_20_score": trend_r2,
                    "ma60_slope_score": ma60,
                    "ret_20_score": 90,
                    "ret_60_score": 88,
                    "future_20d_return": ret60 / 3,
                    "future_30d_return": ret60 / 2,
                    "future_40d_return": ret60 * 0.75,
                    "future_60d_return": ret60,
                    "future_60d_max_drawdown": dd60,
                    "max_return_within_60d": ret60 + 0.1,
                    "hit_double_within_60d": double,
                }
            )
    return pd.DataFrame(rows)


def test_pareto_scan_generates_threshold_scan_rows():
    result = build_mid_trend_pareto_scan_from_frames(funnel_detail=_detail(), top_n=4)

    scan = result["threshold_scan"]
    assert {"volatility_20_score", "atr_pct_score", "max_drawdown_20_score", "trend_r2_20_score"}.issubset(
        set(scan["rule_family"])
    )
    row = scan[(scan["rule_family"].eq("volatility_20_score")) & (scan["threshold"].eq(20))]
    assert not row.empty
    assert row.iloc[0]["sample_count"] == 8


def test_pareto_scan_decomposes_high_elasticity_quality():
    result = build_mid_trend_pareto_scan_from_frames(funnel_detail=_detail(), top_n=4)

    decomposition = result["high_elasticity_decomposition"].set_index("elasticity_bucket")
    assert "good_high_elasticity" in decomposition.index
    assert "bad_high_elasticity" in decomposition.index
    assert decomposition.loc["good_high_elasticity", "avg_future_60d_max_drawdown"] > decomposition.loc[
        "bad_high_elasticity", "avg_future_60d_max_drawdown"
    ]


def test_pareto_scan_recommendations_mark_pareto_candidates():
    result = build_mid_trend_pareto_scan_from_frames(funnel_detail=_detail(), top_n=4)

    recommendations = result["pareto_recommendations"]
    assert "pareto_score" in recommendations.columns
    assert recommendations.iloc[0]["pareto_score"] >= recommendations.iloc[-1]["pareto_score"]
    assert set(recommendations["recommendation"]).issubset({"pareto_candidate", "diagnostic_only"})


def test_pareto_scan_generates_combo_rule_scan():
    result = build_mid_trend_pareto_scan_from_frames(funnel_detail=_detail(), top_n=4)

    combo = result["combo_scan"]
    assert {
        "vol15_trend70",
        "vol15_trend70_no_bad_high_elasticity",
        "vol20_or_good_high_elasticity",
    }.issubset(set(combo["rule_name"]))
    improved = combo[combo["rule_name"].eq("vol15_trend70_no_bad_high_elasticity")].iloc[0]
    assert improved["avg_future_60d_max_drawdown"] > -0.20


def test_pareto_scan_writes_outputs(tmp_path: Path):
    result = build_mid_trend_pareto_scan_from_frames(
        funnel_detail=_detail(),
        top_n=4,
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["threshold_scan"]).exists()
    assert Path(result["paths"]["combo_scan"]).exists()
    assert Path(result["paths"]["high_elasticity_decomposition"]).exists()
    assert Path(result["paths"]["pareto_recommendations"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_mid_trend_pareto_scan(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "threshold_scan": pd.DataFrame([{"rule_name": "x"}]),
            "paths": {
                "threshold_scan": str(tmp_path / "scan.csv"),
                "combo_scan": str(tmp_path / "combo.csv"),
                "high_elasticity_decomposition": str(tmp_path / "elasticity.csv"),
                "pareto_recommendations": str(tmp_path / "recommendations.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_pareto_scan", fake_run)

    cli.main_for_args(
        [
            "scan-mid-trend-risk-return-pareto",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--top-n",
            "10",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["top_n"] == 10
    out = capsys.readouterr().out
    assert "mid_trend_pareto_scan|threshold_scan|" in out
    assert "mid_trend_pareto_scan|combo_scan|" in out
    assert "mid_trend_pareto_scan|rows|1" in out
