from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.risk_split import (
    build_risk_watch_split_from_frame,
    classify_risk_watch_row,
)


def test_classify_risk_watch_row_separates_hard_failure_from_elasticity_shadow():
    hard = pd.Series(
        {
            "watch_group": "risk_watch",
            "event_structure": "a_kill_failure",
            "failure_flag": True,
            "score_rank": 12,
            "amount_vs_20d": 3.0,
            "high_to_close_drawdown": 0.10,
        }
    )
    elastic = pd.Series(
        {
            "watch_group": "risk_watch",
            "event_structure": "",
            "failure_flag": False,
            "score_rank": 18,
            "amount_vs_20d": 2.6,
            "volatility_5d": 0.06,
            "high_to_close_drawdown": 0.10,
            "lhb_negative_net_buy": False,
            "lhb_institution_selling": False,
            "lhb_high_pump_risk": False,
            "dragon_risk_score": 0.2,
            "lhb_risk_score": 0.0,
        }
    )

    assert classify_risk_watch_row(hard)["risk_split_group"] == "hard_risk"
    assert classify_risk_watch_row(elastic)["risk_split_group"] == "high_elasticity_risk_shadow"


def test_classify_risk_watch_row_treats_standalone_lhb_high_pump_as_elasticity():
    row = pd.Series(
        {
            "watch_group": "risk_watch",
            "event_structure": "",
            "failure_flag": False,
            "score_rank": 16,
            "amount_vs_20d": 2.8,
            "volatility_5d": 0.06,
            "high_to_close_drawdown": 0.03,
            "lhb_negative_net_buy": False,
            "lhb_institution_selling": False,
            "lhb_high_pump_risk": True,
            "dragon_risk_score": 0.25,
            "lhb_risk_score": 0.45,
        }
    )

    result = classify_risk_watch_row(row)

    assert result["risk_split_group"] == "high_elasticity_risk_shadow"
    assert "lhb_high_pump_risk" in result["split_reason"]


def test_build_risk_watch_split_outputs_detail_summary_and_reason_stats():
    detail = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "watch_group": "risk_watch",
                "event_structure": "",
                "score_rank": 15,
                "amount_vs_20d": 3.0,
                "volatility_5d": 0.07,
                "high_to_close_drawdown": 0.11,
                "future_20d_return": 0.5,
                "future_60d_return": 0.8,
                "future_60d_max_drawdown": -0.1,
                "max_return_within_60d": 1.2,
                "hit_double_within_60d": True,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "watch_group": "risk_watch",
                "event_structure": "failed_second_wave",
                "score_rank": 7,
                "amount_vs_20d": 4.0,
                "volatility_5d": 0.08,
                "high_to_close_drawdown": 0.12,
                "future_20d_return": -0.2,
                "future_60d_return": -0.3,
                "future_60d_max_drawdown": -0.4,
                "max_return_within_60d": 0.1,
                "hit_double_within_60d": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "C",
                "watch_group": "opportunity_watch",
                "event_structure": "trend_continuation_candidate",
            },
        ]
    )

    result = build_risk_watch_split_from_frame(detail)

    split = result["detail"].set_index("asset_id")
    assert split.loc["A", "risk_split_group"] == "high_elasticity_risk_shadow"
    assert split.loc["B", "risk_split_group"] == "hard_risk"
    summary = result["summary"].set_index("risk_split_group")
    assert summary.loc["high_elasticity_risk_shadow", "sample_count"] == 1
    assert summary.loc["high_elasticity_risk_shadow", "hit_double_within_60d_rate"] == 1.0
    reasons = result["reason_summary"].set_index("split_reason")
    assert "intraday_fade" in reasons.index


def test_build_risk_watch_split_writes_outputs(tmp_path: Path):
    result = build_risk_watch_split_from_frame(
        pd.DataFrame(
            [
                {
                    "trade_date": "2026-01-01",
                    "asset_id": "A",
                    "watch_group": "risk_watch",
                    "score_rank": 20,
                    "amount_vs_20d": 2.5,
                    "volatility_5d": 0.05,
                    "high_to_close_drawdown": 0.09,
                }
            ]
        ),
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["reason_summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_risk_watch_split(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "detail": pd.DataFrame([{"asset_id": "A"}]),
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "reason_summary": str(tmp_path / "reason.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_risk_watch_split_review", fake_run)

    cli.main_for_args(
        [
            "review-risk-watch-split",
            "--detail-path",
            "outputs/research/watchlist_diagnostics_effectiveness_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["detail_path"] == "outputs/research/watchlist_diagnostics_effectiveness_detail.csv"
    out = capsys.readouterr().out
    assert "risk_watch_split|detail|" in out
    assert "risk_watch_split|rows|1" in out
