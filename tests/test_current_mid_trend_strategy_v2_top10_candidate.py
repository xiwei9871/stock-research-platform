from pathlib import Path

import pandas as pd
from stock_research import cli


def _candidate(trade_date: str, asset_id: str, score_rank: int, score: float) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "asset_id": asset_id,
        "score_rank": score_rank,
        "score_total": score,
        "rank": score_rank,
        "mid_trend_funnel_score": score,
        "mid_trend_layer": "stable_trend_watch",
        "industry_name": "Tech",
        "mainline_status": "sustained_mainline",
        "industry_mainline_score_v1": 0.6,
        "ret_20_score": 80,
        "ret_60_score": 80,
        "trend_r2_20_score": 80,
        "max_drawdown_20_score": 80,
        "volatility_20_score": 80,
    }


def test_top10_candidate_outputs_standard_package(tmp_path: Path) -> None:
    from stock_research.current_mid_trend_strategy_v2_top10_candidate import (
        build_current_mid_trend_strategy_v2_top10_candidate_from_frames,
    )

    regime = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "confirmed_regime_state": "bull_trend", "target_exposure": 1.0, "rebalance_allowed": True},
            {"trade_date": "2025-01-02", "confirmed_regime_state": "bull_trend", "target_exposure": 1.0, "rebalance_allowed": True},
            {"trade_date": "2025-01-03", "confirmed_regime_state": "bull_trend", "target_exposure": 1.0, "rebalance_allowed": True},
        ]
    )
    funnel = pd.DataFrame(
        [
            _candidate("2025-01-01", "A", 1, 95),
            _candidate("2025-01-01", "B", 2, 94),
            _candidate("2025-01-02", "A", 1, 96),
            _candidate("2025-01-02", "C", 2, 93),
            _candidate("2025-01-03", "C", 1, 96),
            _candidate("2025-01-03", "D", 2, 92),
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0},
            {"trade_date": "2025-01-01", "asset_id": "B", "high": 20.5, "low": 19.5, "close": 20.0},
            {"trade_date": "2025-01-01", "asset_id": "C", "high": 30.5, "low": 29.5, "close": 30.0},
            {"trade_date": "2025-01-01", "asset_id": "D", "high": 40.5, "low": 39.5, "close": 40.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 11.5, "low": 10.5, "close": 11.0},
            {"trade_date": "2025-01-02", "asset_id": "B", "high": 19.5, "low": 18.5, "close": 19.0},
            {"trade_date": "2025-01-02", "asset_id": "C", "high": 33.5, "low": 32.5, "close": 33.0},
            {"trade_date": "2025-01-02", "asset_id": "D", "high": 39.5, "low": 38.5, "close": 39.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "high": 12.5, "low": 11.5, "close": 12.0},
            {"trade_date": "2025-01-03", "asset_id": "B", "high": 18.5, "low": 17.5, "close": 18.0},
            {"trade_date": "2025-01-03", "asset_id": "C", "high": 34.5, "low": 33.5, "close": 34.0},
            {"trade_date": "2025-01-03", "asset_id": "D", "high": 42.5, "low": 41.5, "close": 42.0},
        ]
    )

    result = build_current_mid_trend_strategy_v2_top10_candidate_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date="2025-01-01",
        end_date="2025-01-03",
        output_dir=tmp_path,
    )

    assert result["top_n"] == 10
    assert (tmp_path / "current_mid_trend_strategy_v2_top10_candidate_summary.csv").exists()
    assert (tmp_path / "current_mid_trend_strategy_v2_top10_candidate_report.md").exists()


def test_cli_parser_and_dispatch_top10_candidate(tmp_path: Path, monkeypatch) -> None:
    args = cli.build_parser().parse_args(
        [
            "current-mid-trend-strategy-v2-top10-candidate-backtest",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-03",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "current-mid-trend-strategy-v2-top10-candidate-backtest"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"summary": str(tmp_path / "current_mid_trend_strategy_v2_top10_candidate_summary.csv")}, "equity": pd.DataFrame(), "trades": pd.DataFrame(), "protection_events": pd.DataFrame()}

    monkeypatch.setattr(
        "stock_research.current_mid_trend_strategy_v2_top10_candidate.run_current_mid_trend_strategy_v2_top10_candidate_backtest",
        _fake_runner,
    )

    rc = cli.main(
        [
            "current-mid-trend-strategy-v2-top10-candidate-backtest",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-03",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert rc in {0, None}
    assert called["start_date"] == "2025-01-01"
