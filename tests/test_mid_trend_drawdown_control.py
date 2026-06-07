from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_drawdown_control import (
    build_mid_trend_drawdown_control_validation_from_frames,
)


def _detail() -> pd.DataFrame:
    rows = []
    for trade_date in ["2025-01-02", "2025-01-03"]:
        for idx, layer, drawdown_score, volatility_score, atr_score, ret60, dd60 in [
            (1, "stable_trend_watch", 90, 70, 60, 0.20, -0.10),
            (2, "mainline_momentum_watch", 75, 65, 50, 0.15, -0.12),
            (3, "pullback_reacceleration_watch", 65, 35, 35, 0.18, -0.13),
            (4, "high_elasticity_watch", 55, 15, 18, 0.35, -0.25),
            (5, "high_elasticity_watch", 45, 8, 10, 0.45, -0.30),
        ]:
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": f"{trade_date}-{idx}",
                    "ts_code": f"00000{idx}.SZ",
                    "stock_name": f"Name{idx}",
                    "mid_trend_layer": layer,
                    "mid_trend_funnel_score": 100 - idx,
                    "score_rank": idx,
                    "ret_60_score": 90 if idx <= 4 else 80,
                    "ret_20_score": 92 if idx >= 3 else 80,
                    "ma60_slope_score": 88,
                    "ma20_slope_score": 90,
                    "trend_r2_20_score": 85 if idx <= 3 else 60,
                    "momentum_20_5_score": 90,
                    "stock_excess_ret_20_score": 88,
                    "sector_ret_20_score": 86,
                    "max_drawdown_20_score": drawdown_score,
                    "volatility_20_score": volatility_score,
                    "atr_pct_score": atr_score,
                    "future_20d_return": ret60 / 3,
                    "future_30d_return": ret60 / 2,
                    "future_40d_return": ret60 * 0.75,
                    "future_60d_return": ret60,
                    "future_60d_max_drawdown": dd60,
                    "max_return_within_60d": ret60 + 0.10,
                    "hit_double_within_60d": idx == 5,
                }
            )
    return pd.DataFrame(rows)


def _baseline_top10() -> pd.DataFrame:
    frame = _detail().copy()
    frame["mid_trend_top10_rank"] = frame.groupby("trade_date").cumcount() + 1
    return frame


def test_drawdown_control_builds_named_variants_and_limits_high_elasticity():
    result = build_mid_trend_drawdown_control_validation_from_frames(
        funnel_detail=_detail(),
        baseline_top10=_baseline_top10(),
        top_n=4,
    )

    detail = result["variant_detail"]
    variants = set(detail["variant_name"])
    assert "baseline_top10" in variants
    assert "no_high_elasticity_top10" in variants
    assert "high_elasticity_quota_1_top10" in variants

    quota = detail[detail["variant_name"].eq("high_elasticity_quota_1_top10")]
    high_counts = quota.groupby("trade_date")["mid_trend_layer"].apply(lambda x: int((x == "high_elasticity_watch").sum()))
    assert high_counts.max() == 1


def test_drawdown_control_effectiveness_and_recommendations_are_generated():
    result = build_mid_trend_drawdown_control_validation_from_frames(
        funnel_detail=_detail(),
        baseline_top10=_baseline_top10(),
        top_n=4,
    )

    effectiveness = result["effectiveness"].set_index("variant_name")
    assert effectiveness.loc["baseline_top10", "sample_count"] == 8
    assert effectiveness.loc["no_high_elasticity_top10", "avg_future_60d_max_drawdown"] > effectiveness.loc[
        "baseline_top10", "avg_future_60d_max_drawdown"
    ]
    assert "recommendation" in result["recommendations"].columns


def test_drawdown_control_writes_outputs(tmp_path: Path):
    result = build_mid_trend_drawdown_control_validation_from_frames(
        funnel_detail=_detail(),
        baseline_top10=_baseline_top10(),
        top_n=4,
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["variant_detail"]).exists()
    assert Path(result["paths"]["effectiveness"]).exists()
    assert Path(result["paths"]["recommendations"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_mid_trend_drawdown_control(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "variant_detail": pd.DataFrame([{"variant_name": "baseline_top10"}]),
            "paths": {
                "variant_detail": str(tmp_path / "detail.csv"),
                "effectiveness": str(tmp_path / "effectiveness.csv"),
                "recommendations": str(tmp_path / "recommendations.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_drawdown_control_validation", fake_run)

    cli.main_for_args(
        [
            "validate-mid-trend-drawdown-control",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--baseline-top10-path",
            "outputs/research/mid_trend_watch_top10.csv",
            "--top-n",
            "10",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["top_n"] == 10
    out = capsys.readouterr().out
    assert "mid_trend_drawdown_control|effectiveness|" in out
    assert "mid_trend_drawdown_control|rows|1" in out
