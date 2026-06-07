from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_watch_funnel import build_mid_trend_watch_funnel_from_frames


def _detail() -> pd.DataFrame:
    rows = []
    for rank, asset_id, components in [
        (
            1,
            "A",
            {
                "ret_60_score": 95,
                "ret_20_score": 85,
                "ma60_slope_score": 94,
                "ma20_slope_score": 92,
                "trend_r2_20_score": 95,
                "stock_excess_ret_20_score": 88,
                "sector_ret_20_score": 70,
                "max_drawdown_20_score": 90,
                "volatility_20_score": 80,
                "atr_pct_score": 75,
                "momentum_20_5_score": 80,
            },
        ),
        (
            2,
            "B",
            {
                "ret_60_score": 80,
                "ret_20_score": 90,
                "ma60_slope_score": 75,
                "ma20_slope_score": 80,
                "trend_r2_20_score": 70,
                "stock_excess_ret_20_score": 92,
                "sector_ret_20_score": 95,
                "max_drawdown_20_score": 80,
                "volatility_20_score": 70,
                "atr_pct_score": 70,
                "momentum_20_5_score": 78,
            },
        ),
        (
            3,
            "C",
            {
                "ret_60_score": 88,
                "ret_20_score": 70,
                "ma60_slope_score": 76,
                "ma20_slope_score": 82,
                "trend_r2_20_score": 74,
                "stock_excess_ret_20_score": 78,
                "sector_ret_20_score": 72,
                "max_drawdown_20_score": 62,
                "volatility_20_score": 60,
                "atr_pct_score": 55,
                "momentum_20_5_score": 90,
            },
        ),
        (
            4,
            "D",
            {
                "ret_60_score": 70,
                "ret_20_score": 98,
                "ma60_slope_score": 65,
                "ma20_slope_score": 84,
                "trend_r2_20_score": 50,
                "stock_excess_ret_20_score": 95,
                "sector_ret_20_score": 60,
                "max_drawdown_20_score": 45,
                "volatility_20_score": 12,
                "atr_pct_score": 15,
                "momentum_20_5_score": 96,
            },
        ),
        (
            5,
            "E",
            {
                "ret_60_score": 90,
                "ret_20_score": 96,
                "ma60_slope_score": 88,
                "ma20_slope_score": 90,
                "trend_r2_20_score": 82,
                "stock_excess_ret_20_score": 80,
                "sector_ret_20_score": 80,
                "max_drawdown_20_score": 10,
                "volatility_20_score": 5,
                "atr_pct_score": 8,
                "momentum_20_5_score": 92,
            },
        ),
    ]:
        rows.append(
            {
                "trade_date": "2025-01-02",
                "asset_id": asset_id,
                "ts_code": f"00000{rank}.SZ",
                "stock_name": asset_id,
                "score_rank": rank,
                "score_total": 90 - rank,
                "score_components": components,
                "future_20d_return": 0.02 * rank,
                "future_30d_return": 0.03 * rank,
                "future_40d_return": 0.04 * rank,
                "future_60d_return": 0.05 * rank,
                "future_60d_max_drawdown": -0.01 * rank,
                "max_return_within_60d": 0.10 * rank,
                "hit_double_within_60d": rank == 4,
            }
        )
    return pd.DataFrame(rows)


def test_mid_trend_funnel_splits_top500_into_named_layers():
    result = build_mid_trend_watch_funnel_from_frames(
        discovery_pool_detail=_detail(),
        top50_size=4,
        top10_size=2,
    )

    detail = result["detail"].set_index("asset_id")
    assert detail.loc["A", "mid_trend_layer"] == "stable_trend_watch"
    assert detail.loc["B", "mid_trend_layer"] == "mainline_momentum_watch"
    assert detail.loc["C", "mid_trend_layer"] == "pullback_reacceleration_watch"
    assert detail.loc["D", "mid_trend_layer"] == "high_elasticity_watch"
    assert detail.loc["E", "mid_trend_layer"] == "risk_exclusion_watch"
    assert detail.loc["A", "evaluation_horizon"] == "20/30/40/60d"


def test_mid_trend_funnel_builds_top50_and_top10_without_risk_exclusion():
    result = build_mid_trend_watch_funnel_from_frames(
        discovery_pool_detail=_detail(),
        top50_size=4,
        top10_size=2,
    )

    top50_assets = set(result["top50"]["asset_id"])
    top10_assets = set(result["top10"]["asset_id"])
    assert "E" not in top50_assets
    assert len(result["top50"]) == 4
    assert len(result["top10"]) == 2
    assert top10_assets <= top50_assets
    pools = result["pool_effectiveness"].set_index("pool_name")
    assert pools.loc["mid_trend_top50", "sample_count"] == 4
    assert pools.loc["mid_trend_top10", "sample_count"] == 2


def test_mid_trend_funnel_enriches_market_and_industry_context():
    context = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "industry_name": "科技",
                "market_regime": "neutral",
                "mainline_context": "mainline",
            }
        ]
    )
    market_regime = pd.DataFrame(
        [{"rebalance_date": "2025-01-02", "market_regime": "mainline"}]
    )
    industry_mainline = pd.DataFrame(
        [
            {
                "rebalance_date": "2025-01-02",
                "industry_name": "科技",
                "industry_mainline_score_v1": 0.82,
                "mainline_tag": "sustained_mainline",
            }
        ]
    )

    result = build_mid_trend_watch_funnel_from_frames(
        discovery_pool_detail=_detail(),
        context_detail=context,
        market_regime=market_regime,
        industry_mainline=industry_mainline,
        top50_size=4,
        top10_size=2,
    )

    row = result["detail"].set_index("asset_id").loc["A"]
    assert row["industry_name"] == "科技"
    assert row["market_regime"] == "mainline"
    assert row["mainline_status"] == "sustained_mainline"
    assert row["industry_mainline_score_v1"] == 0.82


def test_mid_trend_funnel_backfills_industry_from_membership_context():
    membership = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "industry_name": "软件和信息技术服务业",
                "start_date": "2024-01-01",
                "end_date": None,
            }
        ]
    )

    result = build_mid_trend_watch_funnel_from_frames(
        discovery_pool_detail=_detail(),
        industry_membership=membership,
        top50_size=4,
        top10_size=2,
    )

    row = result["detail"].set_index("asset_id").loc["A"]
    assert row["industry_name"] == "软件和信息技术服务业"


def test_mid_trend_funnel_writes_outputs(tmp_path: Path):
    result = build_mid_trend_watch_funnel_from_frames(
        discovery_pool_detail=_detail(),
        top50_size=4,
        top10_size=2,
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["layer_effectiveness"]).exists()
    assert Path(result["paths"]["pool_effectiveness"]).exists()
    assert Path(result["paths"]["top50"]).exists()
    assert Path(result["paths"]["top10"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_mid_trend_watch_funnel(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "detail": pd.DataFrame([{"asset_id": "A"}]),
            "top50": pd.DataFrame([{"asset_id": "A"}]),
            "top10": pd.DataFrame([{"asset_id": "A"}]),
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "layer_effectiveness": str(tmp_path / "layer.csv"),
                "pool_effectiveness": str(tmp_path / "pool.csv"),
                "top50": str(tmp_path / "top50.csv"),
                "top10": str(tmp_path / "top10.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_watch_funnel", fake_run)

    cli.main_for_args(
        [
            "build-mid-trend-watch-funnel",
            "--discovery-pool-path",
            "outputs/research/strong_winner_discovery_pool_detail.csv",
            "--top50-size",
            "50",
            "--top10-size",
            "10",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["top50_size"] == 50
    assert captured["top10_size"] == 10
    out = capsys.readouterr().out
    assert "mid_trend_watch_funnel|top50|" in out
    assert "mid_trend_watch_funnel|top10|" in out
