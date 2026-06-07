from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_shadow_stability import (
    build_mid_trend_shadow_stability_review_from_frames,
)


def _detail() -> pd.DataFrame:
    rows = []
    for trade_date, regime, industry in [
        ("2025-01-02", "mainline", "tech"),
        ("2025-04-02", "rotation", "cyclical"),
    ]:
        for idx, vol, trend, ret60, dd60, layer in [
            (1, 20, 85, 0.20, -0.10, "stable_trend_watch"),
            (2, 18, 82, 0.18, -0.12, "mainline_momentum_watch"),
            (3, 10, 60, 0.30, -0.30, "high_elasticity_watch"),
            (4, 30, 75, 0.10, -0.11, "pullback_reacceleration_watch"),
        ]:
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": f"{trade_date}-{idx}",
                    "mid_trend_layer": layer,
                    "mid_trend_funnel_score": 100 - idx,
                    "score_rank": idx,
                    "volatility_20_score": vol,
                    "trend_r2_20_score": trend,
                    "market_regime": regime,
                    "industry_name": industry,
                    "mainline_status": "sustained_mainline" if industry == "tech" else "neutral",
                    "industry_mainline_score_v1": 0.8 if industry == "tech" else 0.3,
                    "future_20d_return": ret60 / 3,
                    "future_30d_return": ret60 / 2,
                    "future_40d_return": ret60 * 0.75,
                    "future_60d_return": ret60,
                    "future_60d_max_drawdown": dd60,
                    "max_return_within_60d": ret60 + 0.1,
                    "hit_double_within_60d": idx == 3,
                }
            )
    return pd.DataFrame(rows)


def _top10() -> pd.DataFrame:
    frame = _detail().copy()
    frame["mid_trend_top10_rank"] = frame.groupby("trade_date").cumcount() + 1
    return frame


def _structure_detail() -> pd.DataFrame:
    rows = []
    specs = [
        ("electronics_a", "计算机、通信和其他电子设备制造业", "stable_trend_watch", 100, 85, 80),
        ("electronics_b", "计算机、通信和其他电子设备制造业", "mainline_momentum_watch", 99, 86, 78),
        ("auto_high", "汽车制造业", "stable_trend_watch", 98, 87, 75),
        ("internet_high", "互联网和相关服务", "stable_trend_watch", 97, 88, 74),
        ("equipment", "专用设备制造业", "stable_trend_watch", 96, 84, 72),
        ("elasticity", "计算机、通信和其他电子设备制造业", "high_elasticity_watch", 95, 83, 50),
        ("chemical", "化学原料和化学制品制造业", "stable_trend_watch", 94, 82, 70),
    ]
    for asset_id, industry, layer, score, trend, drawdown_score in specs:
        rows.append(
            {
                "trade_date": "2025-01-02",
                "asset_id": asset_id,
                "mid_trend_layer": layer,
                "mid_trend_funnel_score": score,
                "score_rank": 100 - score,
                "volatility_20_score": 20,
                "trend_r2_20_score": trend,
                "max_drawdown_20_score": drawdown_score,
                "ret_20_score": 90,
                "market_regime": "mainline",
                "industry_name": industry,
                "mainline_status": "sustained_mainline",
                "mainline_context": "mainline",
                "industry_mainline_score_v1": 0.8,
                "future_20d_return": 0.05,
                "future_30d_return": 0.08,
                "future_40d_return": 0.10,
                "future_60d_return": 0.15,
                "future_60d_max_drawdown": -0.10,
                "max_return_within_60d": 0.25,
                "hit_double_within_60d": False,
            }
        )
    return pd.DataFrame(rows)


def test_shadow_stability_generates_period_regime_industry_and_layer_tables():
    result = build_mid_trend_shadow_stability_review_from_frames(
        funnel_detail=_detail(),
        baseline_top10=_top10(),
        top_n=3,
    )

    assert not result["by_period"].empty
    assert not result["by_regime"].empty
    assert not result["by_industry"].empty
    assert not result["by_layer"].empty
    assert {
        "baseline_top10",
        "vol15_trend80_shadow",
        "context_v2_mainline_quality_shadow",
        "context_v2_rotation_stable_shadow",
        "context_v2_combined_shadow",
        "context_v2_structured_top10_shadow",
    }.issubset(set(result["by_period"]["variant_name"]))


def test_context_v2_combined_shadow_uses_regime_and_industry_filters():
    result = build_mid_trend_shadow_stability_review_from_frames(
        funnel_detail=_detail(),
        baseline_top10=_top10(),
        top_n=3,
    )

    variants = result["variant_detail"]
    combined = variants[variants["variant_name"].eq("context_v2_combined_shadow")]
    assert not combined.empty
    assert set(combined["market_regime"]) == {"mainline"}
    assert set(combined["industry_name"]) == {"tech"}


def test_context_v2_structured_top10_caps_weak_industry_slots():
    result = build_mid_trend_shadow_stability_review_from_frames(
        funnel_detail=_structure_detail(),
        baseline_top10=_structure_detail(),
        top_n=5,
    )

    structured = result["variant_detail"][
        result["variant_detail"]["variant_name"].eq("context_v2_structured_top10_shadow")
    ]
    weak_industries = {"汽车制造业", "互联网和相关服务", "化学原料和化学制品制造业"}
    assert not structured.empty
    assert int(structured["industry_name"].isin(weak_industries).sum()) <= 1
    assert "计算机、通信和其他电子设备制造业" in set(structured["industry_name"])
    assert "structure_slot" in structured.columns


def test_shadow_stability_decision_flags_shadow_rule():
    result = build_mid_trend_shadow_stability_review_from_frames(
        funnel_detail=_detail(),
        baseline_top10=_top10(),
        top_n=3,
    )

    decision = result["decision"].set_index("variant_name")
    assert "vol15_trend80_shadow" in decision.index
    assert decision.loc["vol15_trend80_shadow", "review_status"] in {
        "promote_to_shadow_watch",
        "keep_diagnostic_only",
    }


def test_shadow_stability_writes_outputs(tmp_path: Path):
    result = build_mid_trend_shadow_stability_review_from_frames(
        funnel_detail=_detail(),
        baseline_top10=_top10(),
        top_n=3,
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["by_period"]).exists()
    assert Path(result["paths"]["by_regime"]).exists()
    assert Path(result["paths"]["by_industry"]).exists()
    assert Path(result["paths"]["by_layer"]).exists()
    assert Path(result["paths"]["decision"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_mid_trend_shadow_stability(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "by_period": pd.DataFrame([{"variant_name": "baseline_top10"}]),
            "paths": {
                "by_period": str(tmp_path / "period.csv"),
                "by_regime": str(tmp_path / "regime.csv"),
                "by_industry": str(tmp_path / "industry.csv"),
                "by_layer": str(tmp_path / "layer.csv"),
                "decision": str(tmp_path / "decision.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_shadow_stability_review", fake_run)

    cli.main_for_args(
        [
            "review-mid-trend-shadow-stability",
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
    assert "mid_trend_shadow_stability|by_period|" in out
    assert "mid_trend_shadow_stability|rows|1" in out
