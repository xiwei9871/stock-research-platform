from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.context_cross_review import (
    build_watchlist_context_cross_review_from_frames,
    classify_fundamental_context,
    classify_watchlist_review_layer,
)


def _detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "watch_group": "opportunity_watch",
                "event_structure": "trend_continuation_candidate",
                "mainline_flag": True,
                "sector_strength_rank": 5,
                "industry_name": "AI",
                "future_1d_return": 0.02,
                "future_3d_return": 0.04,
                "future_5d_return": 0.08,
                "future_10d_return": 0.10,
                "future_20d_return": 0.20,
                "future_30d_return": 0.35,
                "future_60d_return": 0.80,
                "future_60d_max_drawdown": -0.10,
                "hit_double_within_60d": True,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "watch_group": "opportunity_watch",
                "event_structure": "weak_to_strong_candidate",
                "mainline_flag": False,
                "sector_strength_rank": 80,
                "industry_name": "Other",
                "future_1d_return": -0.01,
                "future_3d_return": -0.02,
                "future_5d_return": -0.03,
                "future_10d_return": -0.05,
                "future_20d_return": -0.08,
                "future_30d_return": -0.10,
                "future_60d_return": -0.20,
                "future_60d_max_drawdown": -0.30,
                "hit_double_within_60d": False,
            },
        ]
    )


def _layer_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "watch_group": "opportunity_watch",
                "event_structure": "trend_continuation_candidate",
                "mainline_flag": True,
                "sector_strength_rank": 5,
                "future_5d_return": 0.03,
                "future_20d_return": 0.20,
                "future_60d_return": 0.60,
                "future_60d_max_drawdown": -0.08,
                "hit_double_within_60d": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "watch_group": "opportunity_watch",
                "event_structure": "trend_continuation_candidate",
                "mainline_flag": True,
                "sector_strength_rank": 15,
                "future_5d_return": 0.05,
                "future_20d_return": 0.10,
                "future_60d_return": 0.20,
                "future_60d_max_drawdown": -0.18,
                "hit_double_within_60d": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "C",
                "watch_group": "risk_watch",
                "event_structure": "a_kill_failure",
                "mainline_flag": True,
                "sector_strength_rank": 20,
                "future_5d_return": -0.15,
                "future_20d_return": -0.25,
                "future_60d_return": -0.35,
                "future_60d_max_drawdown": -0.40,
                "hit_double_within_60d": False,
            },
        ]
    )


def _layer_fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "roe": 0.10,
                "revenue_yoy": 0.35,
                "np_yoy": 0.20,
                "deduct_np_yoy": 0.10,
                "np_parent_ttm": 100.0,
                "debt_ratio": 0.40,
                "is_st": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "roe": -0.03,
                "revenue_yoy": -0.10,
                "np_yoy": -0.20,
                "deduct_np_yoy": -0.25,
                "np_parent_ttm": -10.0,
                "debt_ratio": 0.55,
                "is_st": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "C",
                "roe": 0.08,
                "revenue_yoy": 0.10,
                "np_yoy": 0.10,
                "deduct_np_yoy": 0.05,
                "np_parent_ttm": 50.0,
                "debt_ratio": 0.30,
                "is_st": False,
            },
        ]
    )


def _fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "roe": 0.15,
                "revenue_yoy": 0.30,
                "np_yoy": 0.25,
                "deduct_np_yoy": 0.20,
                "np_parent_ttm": 100.0,
                "debt_ratio": 0.35,
                "is_st": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "roe": -0.05,
                "revenue_yoy": -0.10,
                "np_yoy": -0.30,
                "deduct_np_yoy": -0.40,
                "np_parent_ttm": -20.0,
                "debt_ratio": 0.82,
                "is_st": False,
            },
        ]
    )


def test_classify_fundamental_context_marks_expectation_growth_and_loss_worsening():
    growth = classify_fundamental_context(
        pd.Series(
            {
                "roe": 0.08,
                "revenue_yoy": 0.35,
                "np_yoy": 0.2,
                "deduct_np_yoy": 0.15,
                "np_parent_ttm": 80.0,
                "debt_ratio": 0.4,
                "is_st": False,
            }
        )
    )
    worsening_loss = classify_fundamental_context(
        pd.Series(
            {
                "roe": -0.05,
                "revenue_yoy": -0.2,
                "np_yoy": -0.3,
                "deduct_np_yoy": -0.4,
                "np_parent_ttm": -20.0,
                "debt_ratio": 0.8,
                "is_st": False,
            }
        )
    )

    assert growth["fundamental_quality_bucket"] == "expectation_growth"
    assert growth["fundamental_time_horizon_fit"] == "mid_term_eligible"
    assert growth["fundamental_hard_risk"] is False
    assert worsening_loss["fundamental_quality_bucket"] == "loss_worsening"
    assert worsening_loss["fundamental_time_horizon_fit"] == "short_speculation_only"
    assert worsening_loss["fundamental_hard_risk"] is True


def test_classify_fundamental_context_does_not_treat_high_debt_alone_as_hard_risk():
    high_debt_only = classify_fundamental_context(
        pd.Series(
            {
                "roe": 0.04,
                "revenue_yoy": 0.05,
                "np_yoy": 0.03,
                "deduct_np_yoy": 0.02,
                "np_parent_ttm": 20.0,
                "debt_ratio": 0.82,
                "is_st": False,
            }
        )
    )

    assert high_debt_only["fundamental_quality_bucket"] == "high_debt_only"
    assert high_debt_only["fundamental_time_horizon_fit"] == "mid_term_caution"
    assert high_debt_only["fundamental_hard_risk"] is False


def test_context_cross_review_splits_short_and_strong_layers():
    result = build_watchlist_context_cross_review_from_frames(
        detail=_detail(),
        fundamentals=_fundamentals(),
    )

    short = result["short_horizon_summary"]
    assert "fundamental_quality_bucket" not in short.columns
    mainline_short = short[short["mainline_context"].eq("mainline")].iloc[0]
    assert mainline_short["future_5d_return_mean"] == 0.08

    strong = result["strong_horizon_summary"]
    assert "fundamental_quality_bucket" in strong.columns
    expectation_growth = strong[strong["fundamental_quality_bucket"].eq("expectation_growth")].iloc[0]
    assert expectation_growth["future_30d_return_mean"] == 0.35
    assert expectation_growth["hit_double_within_60d_rate"] == 1.0
    assert "fundamental_time_horizon_fit" in strong.columns


def test_classify_watchlist_review_layer_separates_mid_term_speculation_and_hard_risk():
    mid_term = classify_watchlist_review_layer(
        pd.Series(
            {
                "watch_group": "opportunity_watch",
                "event_structure": "trend_continuation_candidate",
                "mainline_flag": True,
                "fundamental_time_horizon_fit": "mid_term_eligible",
            }
        )
    )
    speculative = classify_watchlist_review_layer(
        pd.Series(
            {
                "watch_group": "opportunity_watch",
                "event_structure": "trend_continuation_candidate",
                "mainline_flag": True,
                "fundamental_time_horizon_fit": "short_speculation_only",
            }
        )
    )
    hard = classify_watchlist_review_layer(
        pd.Series(
            {
                "watch_group": "risk_watch",
                "event_structure": "a_kill_failure",
                "mainline_flag": True,
                "fundamental_time_horizon_fit": "mid_term_eligible",
            }
        )
    )
    risk_without_hard_failure = classify_watchlist_review_layer(
        pd.Series(
            {
                "watch_group": "risk_watch",
                "event_structure": "",
                "mainline_flag": True,
                "fundamental_time_horizon_fit": "mid_term_eligible",
            }
        )
    )

    assert mid_term == "mid_term_trend_watch"
    assert speculative == "short_speculation_watch"
    assert hard == "hard_risk_watch"
    assert risk_without_hard_failure == "short_speculation_watch"


def test_context_cross_review_outputs_review_layer_summary():
    result = build_watchlist_context_cross_review_from_frames(
        detail=_layer_detail(),
        fundamentals=_layer_fundamentals(),
    )

    enriched = result["detail"]
    assert set(enriched["watchlist_review_layer"]) == {
        "mid_term_trend_watch",
        "short_speculation_watch",
        "hard_risk_watch",
    }
    layer_summary = result["layer_summary"]
    assert set(layer_summary["watchlist_review_layer"]) == {
        "mid_term_trend_watch",
        "short_speculation_watch",
        "hard_risk_watch",
    }
    mid_term = layer_summary[layer_summary["watchlist_review_layer"].eq("mid_term_trend_watch")].iloc[0]
    assert mid_term["future_60d_return_mean"] == 0.60


def test_context_cross_review_handles_missing_fundamentals_without_crashing():
    result = build_watchlist_context_cross_review_from_frames(detail=_detail(), fundamentals=pd.DataFrame())

    enriched = result["detail"]
    assert set(enriched["fundamental_quality_bucket"]) == {"unknown_fundamental"}
    assert "missing_fundamental_rows" in result["warnings"]


def test_context_cross_review_writes_outputs(tmp_path: Path):
    result = build_watchlist_context_cross_review_from_frames(
        detail=_detail(),
        fundamentals=_fundamentals(),
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["short_horizon_summary"]).exists()
    assert Path(result["paths"]["strong_horizon_summary"]).exists()
    assert Path(result["paths"]["industry_summary"]).exists()
    assert Path(result["paths"]["fundamental_summary"]).exists()
    assert Path(result["paths"]["layer_summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_context_cross_review(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "detail": pd.DataFrame([{"asset_id": "A"}]),
            "warnings": [],
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "short_horizon_summary": str(tmp_path / "short.csv"),
                "strong_horizon_summary": str(tmp_path / "strong.csv"),
                "industry_summary": str(tmp_path / "industry.csv"),
                "fundamental_summary": str(tmp_path / "fundamental.csv"),
                "layer_summary": str(tmp_path / "layer.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_watchlist_context_cross_review", fake_run)

    cli.main_for_args(
        [
            "review-watchlist-context-cross",
            "--detail-path",
            "outputs/research/watchlist_diagnostics_effectiveness_detail.csv",
            "--fundamental-context-path",
            "outputs/research/watchlist_fundamental_pit_context.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["detail_path"] == "outputs/research/watchlist_diagnostics_effectiveness_detail.csv"
    assert captured["fundamental_context_path"] == "outputs/research/watchlist_fundamental_pit_context.csv"
    out = capsys.readouterr().out
    assert "watchlist_context_cross|detail|" in out
    assert "watchlist_context_cross|layer_summary|" in out
    assert "watchlist_context_cross|rows|1" in out
