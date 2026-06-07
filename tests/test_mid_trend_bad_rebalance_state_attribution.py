from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_bad_rebalance_state_attribution import (
    build_bad_rebalance_state_attribution_from_frames,
)


def _detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-06",
                "sold_asset_id": "OLD",
                "bought_asset_id": "NEW",
                "bad_rebalance_flag": True,
                "bad_rebalance_reasons": "sell_fly;bad_buy",
                "replacement_alpha_10d": -0.2,
                "sold_next_10d_return": 0.12,
                "bought_next_10d_return": -0.08,
            },
            {
                "trade_date": "2025-01-13",
                "sold_asset_id": "OKOLD",
                "bought_asset_id": "OKNEW",
                "bad_rebalance_flag": False,
                "bad_rebalance_reasons": "",
                "replacement_alpha_10d": 0.05,
                "sold_next_10d_return": 0.01,
                "bought_next_10d_return": 0.06,
            },
        ]
    )


def _funnel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-06",
                "asset_id": "OLD",
                "mid_trend_funnel_score": 90,
                "score_rank": 7,
                "trend_r2_20_score": 92,
                "ret_20_score": 88,
                "volatility_20_score": 35,
                "max_drawdown_20_score": 70,
                "industry_mainline_score_v1": 0.8,
                "mid_trend_layer": "stable_trend_watch",
                "industry_name": "计算机、通信和其他电子设备制造业",
                "market_regime": "mainline",
            },
            {
                "trade_date": "2025-01-06",
                "asset_id": "NEW",
                "mid_trend_funnel_score": 91,
                "score_rank": 3,
                "trend_r2_20_score": 50,
                "ret_20_score": 96,
                "volatility_20_score": 90,
                "max_drawdown_20_score": 20,
                "industry_mainline_score_v1": 0.3,
                "mid_trend_layer": "high_elasticity_watch",
                "industry_name": "通用设备制造业",
                "market_regime": "rotation",
            },
        ]
    )


def test_bad_rebalance_state_attribution_flags_sell_still_strong_and_buy_overheated(tmp_path: Path):
    result = build_bad_rebalance_state_attribution_from_frames(
        attribution_detail=_detail(),
        funnel_detail=_funnel(),
        output_dir=tmp_path,
    )

    detail = result["detail"]
    row = detail.iloc[0]
    assert row["sold_still_strong"] is True
    assert row["bought_overheated"] is True
    assert row["bought_weak_mainline"] is True
    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["feature_summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_bad_rebalance_state_attribution(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "detail": pd.DataFrame([{"trade_date": "2025-01-06"}]),
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "feature_summary": str(tmp_path / "summary.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_bad_rebalance_state_attribution", fake_run)

    cli.main_for_args(
        [
            "review-bad-rebalance-state-attribution",
            "--attribution-detail-path",
            "outputs/research/mid_trend_rebalance_attribution/mid_trend_rebalance_attribution_detail.csv",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["funnel_detail_path"] == "outputs/research/mid_trend_watch_funnel_detail.csv"
    out = capsys.readouterr().out
    assert "bad_rebalance_state_attribution|detail|" in out
