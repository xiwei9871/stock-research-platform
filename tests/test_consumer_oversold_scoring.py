import math

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.contracts import ConsumerOversoldConfig
from stock_research.consumer_oversold.scoring import (
    apply_candidate_gates,
    rank_candidate_buckets,
    score_candidates,
)


CONFIG = ConsumerOversoldConfig(trade_date="2026-07-29")


def scoring_rows(**overrides):
    row = {
        "asset_id": "A",
        "consumer_subindustry": "food",
        "latest_net_margin": 0.05,
        "normal_net_margin": 0.10,
        "latest_roe": 0.08,
        "normal_roe": 0.16,
        "latest_revenue_growth": 0.05,
        "normal_revenue_growth": 0.20,
        "expected_improvement_score": 80.0,
        "catalyst_verifiability_score": 70.0,
        "valuation_depression_percentile": 0.8,
        "base_upside": 0.5,
        "latest_equity_parent": 10.0,
        "latest_debt_ratio": 0.2,
        "latest_ocf_to_np": 0.8,
        "latest_operating_cash_flow": 3.0,
        "prior_operating_cash_flow": 2.0,
        "second_prior_operating_cash_flow": 1.0,
        "oversold_score": 75.0,
        "priced_in_penalty": 5.0,
    }
    row.update(overrides)
    return row


def gate_rows(**overrides):
    row = {
        "asset_id": "A",
        "included": True,
        "return_6m": -0.25,
        "max_drawdown_12m": -0.20,
        "relative_return_6m": -0.15,
        "oversold_score": 70.0,
        "base_upside": 0.30,
        "evidence_complete": True,
        "hard_risk_triggered": False,
        "hard_risk_review_unknown": False,
        "balance_sheet_coverage": True,
        "repair_bucket": "expected_repair",
        "latest_revenue_growth": 0.05,
        "normal_revenue_growth": 0.10,
        "latest_profit_growth": 0.05,
        "normal_profit_growth": 0.10,
        "latest_net_margin": 0.05,
        "normal_net_margin": 0.10,
        "composite_score": 70.0,
    }
    row.update(overrides)
    return row


def test_score_candidates_uses_approved_weights_exactly():
    rows = pd.DataFrame(
        [
            scoring_rows(asset_id="A", latest_debt_ratio=0.1, base_upside=0.2),
            scoring_rows(asset_id="B", latest_debt_ratio=0.2, base_upside=0.5),
            scoring_rows(asset_id="C", latest_debt_ratio=0.3, base_upside=0.8),
        ]
    )

    result = score_candidates(rows, CONFIG).set_index("asset_id")

    row = result.loc["B"]
    assert row["operating_gap_score"] == pytest.approx(50.0)
    assert row["debt_score"] == pytest.approx(100.0 * (1.0 - 2.0 / 3.0))
    assert row["equity_score"] == 100.0
    assert row["ocf_quality_score"] == 80.0
    assert row["cash_trend_score"] == 100.0
    expected_balance = np.mean([100.0, 100.0 / 3.0, 80.0, 100.0])
    assert row["balance_sheet_score"] == pytest.approx(expected_balance)
    assert row["base_upside_percentile"] == pytest.approx(2.0 / 3.0)
    assert row["valuation_repair_score"] == pytest.approx(50 * 0.8 + 50 * 2 / 3)
    expected_repair = 0.25 * 50 + 0.25 * 80 + 0.20 * 70 + 0.15 * expected_balance + 0.15 * 80
    assert row["repair_potential_score"] == pytest.approx(expected_repair)
    expected_composite = (
        0.35 * expected_repair
        + 0.25 * (50 * 0.8 + 50 * 2 / 3)
        + 0.20 * 75
        + 0.15 * expected_balance
        + 0.05 * 70
        - 5
    )
    assert row["composite_score"] == pytest.approx(expected_composite)
    assert bool(row["balance_sheet_coverage"])


def test_operating_gap_requires_two_available_components():
    result = score_candidates(
        pd.DataFrame(
            [
                scoring_rows(asset_id="A", latest_roe=np.nan, normal_roe=np.nan),
                scoring_rows(
                    asset_id="B",
                    latest_roe=np.nan,
                    normal_roe=np.nan,
                    latest_revenue_growth=np.nan,
                    normal_revenue_growth=np.nan,
                ),
                scoring_rows(asset_id="C"),
            ]
        ),
        CONFIG,
    ).set_index("asset_id")

    assert result.loc["A", "operating_gap_score"] == pytest.approx(50.0)
    assert math.isnan(result.loc["B", "operating_gap_score"])
    assert math.isnan(result.loc["B", "repair_potential_score"])
    assert math.isnan(result.loc["B", "composite_score"])


def test_debt_peer_threshold_cash_trend_levels_and_balance_coverage():
    rows = pd.DataFrame(
        [
            scoring_rows(asset_id="A", consumer_subindustry="three", latest_debt_ratio=0.1),
            scoring_rows(asset_id="B", consumer_subindustry="three", latest_debt_ratio=0.2),
            scoring_rows(asset_id="C", consumer_subindustry="three", latest_debt_ratio=0.3),
            scoring_rows(asset_id="D", consumer_subindustry="two", latest_debt_ratio=0.1, latest_operating_cash_flow=3, prior_operating_cash_flow=2, second_prior_operating_cash_flow=1),
            scoring_rows(asset_id="E", consumer_subindustry="two", latest_debt_ratio=0.2, latest_operating_cash_flow=3, prior_operating_cash_flow=2, second_prior_operating_cash_flow=4),
            scoring_rows(asset_id="F", consumer_subindustry="solo", latest_debt_ratio=np.nan, latest_ocf_to_np=np.nan, latest_operating_cash_flow=1, prior_operating_cash_flow=2, second_prior_operating_cash_flow=3),
            scoring_rows(asset_id="G", consumer_subindustry="solo2", latest_debt_ratio=np.nan, latest_operating_cash_flow=-1, prior_operating_cash_flow=2, second_prior_operating_cash_flow=3),
        ]
    )

    result = score_candidates(rows, CONFIG).set_index("asset_id")

    assert result.loc["A", "debt_score"] > result.loc["B", "debt_score"] > result.loc["C", "debt_score"]
    assert math.isnan(result.loc["D", "debt_score"])
    assert result.loc["D", "cash_trend_score"] == 100.0
    assert result.loc["E", "cash_trend_score"] == 60.0
    assert result.loc["F", "cash_trend_score"] == 30.0
    assert result.loc["G", "cash_trend_score"] == 0.0
    assert bool(result.loc["D", "balance_sheet_coverage"])
    assert not bool(result.loc["F", "balance_sheet_coverage"])
    assert math.isnan(result.loc["F", "balance_sheet_score"])


def test_base_upside_percentile_requires_two_values_and_output_is_asset_sorted():
    many = score_candidates(
        pd.DataFrame([scoring_rows(asset_id="B", base_upside=0.2), scoring_rows(asset_id="A", base_upside=0.8), scoring_rows(asset_id="C", base_upside=np.nan)]),
        CONFIG,
    )
    assert many["asset_id"].tolist() == ["A", "B", "C"]
    assert many.set_index("asset_id").loc["A", "base_upside_percentile"] == 1.0
    single = score_candidates(pd.DataFrame([scoring_rows(base_upside=0.8)]), CONFIG)
    assert math.isnan(single.loc[0, "base_upside_percentile"])
    assert math.isnan(single.loc[0, "valuation_repair_score"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_improvement_score", 101),
        ("catalyst_verifiability_score", -1),
        ("valuation_depression_percentile", 1.01),
        ("oversold_score", np.inf),
        ("priced_in_penalty", 21),
        ("base_upside", True),
    ],
)
def test_score_candidates_rejects_invalid_numeric_values(field, value):
    with pytest.raises(ValueError, match=field):
        score_candidates(pd.DataFrame([scoring_rows(**{field: value})]), CONFIG)


def test_score_candidates_validates_columns_assets_and_empty_input():
    with pytest.raises(ValueError, match="normal_roe"):
        score_candidates(pd.DataFrame([scoring_rows()]).drop(columns="normal_roe"), CONFIG)
    with pytest.raises(ValueError, match="duplicate asset_id"):
        score_candidates(pd.DataFrame([scoring_rows(), scoring_rows()]), CONFIG)
    with pytest.raises(ValueError, match="asset_id"):
        score_candidates(pd.DataFrame([scoring_rows(asset_id=None)]), CONFIG)
    empty = score_candidates(pd.DataFrame(columns=scoring_rows().keys()), CONFIG)
    assert empty.empty
    assert "composite_score" in empty.columns

    schema_less_empty = score_candidates(pd.DataFrame(), CONFIG)
    assert schema_less_empty.empty
    assert list(schema_less_empty.columns) == list(scoring_rows()) + list(
        {
            "operating_gap_score": None,
            "equity_score": None,
            "debt_ratio_percentile": None,
            "debt_score": None,
            "ocf_quality_score": None,
            "cash_trend_score": None,
            "balance_sheet_component_count": None,
            "balance_sheet_coverage": None,
            "balance_sheet_score": None,
            "base_upside_percentile": None,
            "valuation_repair_score": None,
            "repair_potential_score": None,
            "composite_score": None,
        }
    )


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"included": False}, "universe_excluded"),
        ({"return_6m": -0.1, "max_drawdown_12m": -0.2}, "price_threshold_not_met"),
        ({"relative_return_6m": -0.05}, "relative_return_threshold_not_met"),
        ({"oversold_score": 59.9}, "oversold_score_below_threshold"),
        ({"base_upside": 0.24}, "base_upside_below_threshold"),
        ({"evidence_complete": False}, "evidence_incomplete"),
        ({"hard_risk_triggered": True}, "hard_risk_triggered"),
        ({"hard_risk_review_unknown": True}, "hard_risk_review_unknown"),
        ({"balance_sheet_coverage": False}, "balance_sheet_coverage_insufficient"),
        ({"repair_bucket": "other"}, "repair_bucket_invalid"),
        ({"composite_score": np.nan}, "composite_score_missing"),
    ],
)
def test_each_candidate_gate_emits_exact_exclusion_code(change, code):
    result = apply_candidate_gates(pd.DataFrame([gate_rows(**change)]), CONFIG).iloc[0]
    assert not bool(result["eligible"])
    assert result["exclusion_reasons"] == code


def test_price_gate_uses_or_and_completed_repair_requires_positive_normals():
    rows = pd.DataFrame(
        [
            gate_rows(asset_id="return", return_6m=-0.20, max_drawdown_12m=-0.1),
            gate_rows(asset_id="drawdown", return_6m=-0.1, max_drawdown_12m=-0.30),
            gate_rows(asset_id="complete", latest_revenue_growth=0.09, latest_profit_growth=0.09, latest_net_margin=0.09),
            gate_rows(asset_id="nonpositive", normal_revenue_growth=0.0, latest_revenue_growth=1.0, latest_profit_growth=0.09, latest_net_margin=0.09),
        ]
    )
    result = apply_candidate_gates(rows, CONFIG).set_index("asset_id")
    assert bool(result.loc["return", "eligible"])
    assert bool(result.loc["drawdown", "eligible"])
    assert result.loc["complete", "exclusion_reasons"] == "repair_already_completed"
    assert bool(result.loc["nonpositive", "eligible"])


def test_gate_boolean_parsing_reason_order_and_validation():
    row = gate_rows(
        included="false",
        evidence_complete=0,
        hard_risk_triggered="TRUE",
        hard_risk_review_unknown=np.bool_(True),
        balance_sheet_coverage="false",
        return_6m=-0.1,
        max_drawdown_12m=-0.2,
    )
    result = apply_candidate_gates(pd.DataFrame([row]), CONFIG).iloc[0]
    assert result["exclusion_reasons"] == "|".join(
        sorted(
            {
                "universe_excluded",
                "price_threshold_not_met",
                "evidence_incomplete",
                "hard_risk_triggered",
                "hard_risk_review_unknown",
                "balance_sheet_coverage_insufficient",
            }
        )
    )
    for invalid in [None, pd.NA, 2, "yes"]:
        with pytest.raises(ValueError, match="included"):
            apply_candidate_gates(pd.DataFrame([gate_rows(included=invalid)]), CONFIG)
    with pytest.raises(ValueError, match="return_6m"):
        apply_candidate_gates(pd.DataFrame([gate_rows(return_6m=True)]), CONFIG)

    parsed = apply_candidate_gates(
        pd.DataFrame([gate_rows(included="1", evidence_complete="1", hard_risk_triggered="0")]),
        CONFIG,
    )
    assert bool(parsed.loc[0, "eligible"])


def test_gate_validates_columns_duplicate_assets_and_empty_input():
    with pytest.raises(ValueError, match="normal_profit_growth"):
        apply_candidate_gates(pd.DataFrame([gate_rows()]).drop(columns="normal_profit_growth"), CONFIG)
    with pytest.raises(ValueError, match="duplicate asset_id"):
        apply_candidate_gates(pd.DataFrame([gate_rows(), gate_rows()]), CONFIG)
    empty = apply_candidate_gates(pd.DataFrame(columns=gate_rows().keys()), CONFIG)
    assert empty.empty
    assert list(empty.columns)[-2:] == ["eligible", "exclusion_reasons"]
    assert apply_candidate_gates(pd.DataFrame(), CONFIG).empty


def test_rank_candidate_buckets_does_not_backfill_and_is_deterministic():
    rows = []
    for index in range(7):
        rows.append({"asset_id": f"E{index}", "repair_bucket": "expected_repair", "eligible": True, "composite_score": 80.0, "base_upside": 0.5})
    for index in range(5):
        rows.append({"asset_id": f"V{index}", "repair_bucket": "early_validation", "eligible": True, "composite_score": 70.0 + index, "base_upside": 0.3})
    rows.extend(
        [
            {"asset_id": "X", "repair_bucket": "expected_repair", "eligible": False, "composite_score": 100.0, "base_upside": 1.0},
            {"asset_id": "Z", "repair_bucket": "invalid", "eligible": True, "composite_score": 100.0, "base_upside": 1.0},
        ]
    )
    result = rank_candidate_buckets(pd.DataFrame(rows), CONFIG)
    assert list(result) == ["expected", "early"]
    assert result["expected"]["asset_id"].tolist() == [f"E{i}" for i in range(7)]
    assert result["early"]["asset_id"].tolist() == ["V4", "V3", "V2", "V1", "V0"]
    assert result["expected"]["bucket_rank"].tolist() == list(range(1, 8))
    assert len(result["early"]) == 5


def test_rank_caps_each_bucket_at_twenty_and_validates_input():
    rows = pd.DataFrame(
        [{"asset_id": f"A{i:02d}", "repair_bucket": "expected_repair", "eligible": True, "composite_score": i, "base_upside": i} for i in range(25)]
    )
    assert len(rank_candidate_buckets(rows, CONFIG)["expected"]) == 20
    with pytest.raises(ValueError, match="duplicate asset_id"):
        rank_candidate_buckets(pd.concat([rows.iloc[[0]], rows.iloc[[0]]], ignore_index=True), CONFIG)
    with pytest.raises(ValueError, match="base_upside"):
        rank_candidate_buckets(rows.drop(columns="base_upside"), CONFIG)
    with pytest.raises(ValueError, match="eligible"):
        rank_candidate_buckets(rows.assign(eligible="yes"), CONFIG)
    empty = rank_candidate_buckets(pd.DataFrame(columns=rows.columns), CONFIG)
    assert empty["expected"].empty and empty["early"].empty
    assert "bucket_rank" in empty["expected"].columns
    schema_less_empty = rank_candidate_buckets(pd.DataFrame(), CONFIG)
    assert list(schema_less_empty["expected"].columns) == list(RANK_COLUMNS_FOR_TEST) + [
        "bucket_rank"
    ]


RANK_COLUMNS_FOR_TEST = [
    "asset_id",
    "repair_bucket",
    "eligible",
    "composite_score",
    "base_upside",
]
