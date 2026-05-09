import pandas as pd
import pytest

from stock_research.scoring import composite_score, pipeline, rank_score, standardize, winsorize


def test_winsorize_by_date_clips_outliers_within_each_cross_section():
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 0.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 10.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 20.0},
            {"trade_date": "2026-01-01", "asset_id": "D", "factor_value": 100.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-02", "asset_id": "D", "factor_value": 4.0},
        ]
    )

    result = winsorize.winsorize_by_date(
        frame,
        value_col="factor_value",
        lower_quantile=0.25,
        upper_quantile=0.75,
    )

    day1 = result[result["trade_date"] == "2026-01-01"]
    day2 = result[result["trade_date"] == "2026-01-02"]
    assert day1["factor_value_winsorized"].min() == pytest.approx(7.5)
    assert day1["factor_value_winsorized"].max() == pytest.approx(40.0)
    assert day2["factor_value_winsorized"].tolist() == pytest.approx([1.75, 2.0, 3.0, 3.25])


def test_zscore_by_date_standardizes_each_cross_section():
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "factor_value": 5.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "factor_value": 5.0},
        ]
    )

    result = standardize.zscore_by_date(frame, value_col="factor_value")

    day1 = result[result["trade_date"] == "2026-01-01"]["factor_value_zscore"]
    day2 = result[result["trade_date"] == "2026-01-02"]["factor_value_zscore"]
    assert day1.mean() == pytest.approx(0.0)
    assert day1.std(ddof=0) == pytest.approx(1.0)
    assert day2.tolist() == [0.0, 0.0]


def test_rank_score_by_date_maps_best_factor_to_100_and_worst_to_zero():
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "momentum": 1.0, "risk": 0.30},
            {"trade_date": "2026-01-01", "asset_id": "B", "momentum": 3.0, "risk": 0.10},
            {"trade_date": "2026-01-01", "asset_id": "C", "momentum": 2.0, "risk": 0.20},
        ]
    )

    momentum_scores = rank_score.rank_score_by_date(
        frame,
        value_col="momentum",
        ascending=False,
        output_col="momentum_score",
    )
    risk_scores = rank_score.rank_score_by_date(
        frame,
        value_col="risk",
        ascending=True,
        output_col="risk_score",
    )

    assert momentum_scores.set_index("asset_id")["momentum_score"].to_dict() == {
        "A": 0.0,
        "B": 100.0,
        "C": 50.0,
    }
    assert risk_scores.set_index("asset_id")["risk_score"].to_dict() == {
        "A": 0.0,
        "B": 100.0,
        "C": 50.0,
    }


def test_build_composite_scores_normalizes_weights_and_assigns_ranks():
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "trend_score": 100.0, "risk_score": 0.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "trend_score": 80.0, "risk_score": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "trend_score": 70.0, "risk_score": 100.0},
        ]
    )

    result = composite_score.build_composite_scores(
        frame,
        weights={"trend_score": 3.0, "risk_score": 1.0},
        score_version="manual_v1",
    )

    assert result[["asset_id", "rank", "score_version"]].to_dict("records") == [
        {"asset_id": "B", "rank": 1, "score_version": "manual_v1"},
        {"asset_id": "C", "rank": 2, "score_version": "manual_v1"},
        {"asset_id": "A", "rank": 3, "score_version": "manual_v1"},
    ]
    assert result.set_index("asset_id").loc["B", "score_total"] == pytest.approx(80.0)
    assert result.set_index("asset_id").loc["C", "score_total"] == pytest.approx(77.5)
    assert result.set_index("asset_id").loc["A", "score_total"] == pytest.approx(75.0)


def test_score_factor_daily_pivots_long_factors_and_applies_directions():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "momentum", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_name": "momentum", "factor_value": 3.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_name": "momentum", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "risk", "factor_value": 0.30},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_name": "risk", "factor_value": 0.10},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_name": "risk", "factor_value": 0.20},
        ]
    )

    result = pipeline.score_factor_daily(
        factors,
        factor_directions={"momentum": "higher", "risk": "lower"},
        weights={"momentum_score": 1.0, "risk_score": 1.0},
        score_version="manual_v1",
    )

    assert result[["asset_id", "rank", "score_total"]].to_dict("records") == [
        {"asset_id": "B", "rank": 1, "score_total": 100.0},
        {"asset_id": "C", "rank": 2, "score_total": 50.0},
        {"asset_id": "A", "rank": 3, "score_total": 0.0},
    ]
