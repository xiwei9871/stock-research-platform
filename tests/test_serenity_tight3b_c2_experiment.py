from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.serenity_tight3b_c2_experiment import (
    build_serenity_tight3b_c2_experiment_from_frames,
)


def _candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                "hit_count": 3,
                "primary_chain_id": "ai_optical",
                "primary_chain_name": "AI光模块",
            },
            {
                "asset_id": "B",
                "stock_name": "Beta",
                "first_hit_date": "2025-01-01",
                "hit_count": 2,
                "primary_chain_id": "ai_chip",
                "primary_chain_name": "AI芯片",
            },
            {
                "asset_id": "C",
                "stock_name": "Gamma",
                "first_hit_date": "2025-01-03",
                "hit_count": 1,
                "primary_chain_id": "pcb",
                "primary_chain_name": "AI服务器PCB",
            },
        ]
    )


def _prices() -> pd.DataFrame:
    rows = []
    closes = {
        "A": [10.0, 11.0, 10.0, 9.0, 8.0, 7.0],
        "B": [20.0, 20.5, 21.0, 21.5, 22.0, 22.5],
        "C": [30.0, 30.0, 30.5, 31.0, 31.5, 32.0],
    }
    for i, trade_date in enumerate(pd.date_range("2025-01-01", periods=6, freq="D")):
        for asset_id, series in closes.items():
            rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "asset_id": asset_id,
                    "open": series[i],
                    "close": series[i],
                    "high": series[i] * 1.01,
                    "low": series[i] * 0.99,
                    "amount": 1000000,
                    "trade_status": "正常",
                    "is_limit_up": False,
                    "is_limit_down": False,
                    "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _market_exposure() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": d.strftime("%Y-%m-%d"), "target_exposure": 0.5}
            for d in pd.date_range("2025-01-01", periods=6, freq="D")
        ]
    )


def test_serenity_tight3b_c2_experiment_scans_topn_and_protection_params(tmp_path: Path):
    result = build_serenity_tight3b_c2_experiment_from_frames(
        candidates=_candidates(),
        prices=_prices(),
        market_exposure=_market_exposure(),
        start_date="2025-01-01",
        end_date="2025-01-06",
        output_dir=tmp_path,
        universe_name="strict_test",
        top_n_values=[1, 2],
        rebalance_frequencies=["weekly", "monthly"],
        protection_configs=[
            {"name": "atr_rank", "atr_mult": 2.5, "rank_break": 2, "confirm_days": 1},
            {"name": "rank_exit", "rank_exit": 1, "confirm_days": 1},
        ],
        transaction_cost_bps=20.0,
    )

    summary = result["summary"]
    positions = result["positions"]
    trades = result["trades"]

    assert set(summary["top_n"]) == {1, 2}
    assert set(summary["frequency"]) == {"weekly", "monthly"}
    assert set(summary["protection_name"]) == {"atr_rank", "rank_exit"}
    assert {"protection_name", "atr_mult", "rank_break", "rank_exit", "confirm_days"}.issubset(
        positions.columns
    )
    assert "c2_trigger_count" in summary.columns
    assert not trades.empty
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["best_positions"]).exists()


def test_cli_dispatches_serenity_tight3b_c2_experiment(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "summary": pd.DataFrame([{"universe": "strict_153", "total_return": 0.1}]),
            "paths": {
                "summary": str(tmp_path / "summary.csv"),
                "equity": str(tmp_path / "equity.csv"),
                "positions": str(tmp_path / "positions.csv"),
                "trades": str(tmp_path / "trades.csv"),
                "report": str(tmp_path / "summary.md"),
            },
        }

    monkeypatch.setattr(cli, "run_serenity_tight3b_c2_experiment", fake_run, raising=False)

    cli.main_for_args(
        [
            "serenity-tight3b-c2-experiment",
            "--candidates-path",
            "outputs/tech_bottleneck_discovery/strict.csv",
            "--market-exposure-path",
            "outputs/research/market_regime.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-05",
            "--output-dir",
            str(tmp_path),
            "--top-n-values",
            "5,8,10",
            "--rebalance-frequencies",
            "weekly,monthly",
        ]
    )

    assert captured["start_date"] == "2025-01-01"
    assert captured["top_n_values"] == [5, 8, 10]
    assert captured["rebalance_frequencies"] == ["weekly", "monthly"]
    out = capsys.readouterr().out
    assert "serenity_tight3b_c2|summary|" in out


def test_build_experiment_from_rank_frames_uses_only_requested_snapshot_dates() -> None:
    from stock_research.serenity_tight3b_c2_experiment import build_serenity_tight3b_c2_experiment_from_rank_frames

    ranks = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "bottleneck_rank": 1, "bottleneck_score": 0.9},
            {"trade_date": "2025-01-01", "asset_id": "B", "bottleneck_rank": 2, "bottleneck_score": 0.8},
            {"trade_date": "2025-01-02", "asset_id": "A", "bottleneck_rank": 1, "bottleneck_score": 0.9},
            {"trade_date": "2025-01-02", "asset_id": "B", "bottleneck_rank": 2, "bottleneck_score": 0.8},
            {"trade_date": "2025-01-03", "asset_id": "FUTURE", "bottleneck_rank": 1, "bottleneck_score": 1.0},
        ]
    )

    result = build_serenity_tight3b_c2_experiment_from_rank_frames(
        ranks=ranks,
        prices=_rank_frame_prices(),
        market_exposure=pd.DataFrame(
            [
                {"trade_date": "2025-01-01", "target_exposure": 1.0},
                {"trade_date": "2025-01-02", "target_exposure": 1.0},
            ]
        ),
        start_date="2025-01-01",
        end_date="2025-01-02",
        universe_name="strict_153_st_only_financial_state",
        top_n_values=[1],
        rebalance_frequencies=["weekly"],
        protection_configs=[{"name": "rank_exit_top10_1d", "rank_exit": 10, "confirm_days": 1}],
        transaction_cost_bps=20.0,
    )

    traded_assets = set(result["best_trades"]["asset_id"].astype(str).tolist())
    assert "A" in traded_assets
    assert "FUTURE" not in traded_assets
    assert result["summary"].iloc[0]["top_n"] == 1


def _rank_frame_prices() -> pd.DataFrame:
    rows = []
    for trade_date in ["2025-01-01", "2025-01-02", "2025-01-03"]:
        for asset_id, close in {"A": 10.0, "B": 20.0, "FUTURE": 30.0}.items():
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                }
            )
    return pd.DataFrame(rows)
