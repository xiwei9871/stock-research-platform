import math
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest

import stock_research.consumer_oversold.scoring as scoring_module
from stock_research.consumer_oversold.contracts import ConsumerOversoldConfig
from stock_research.consumer_oversold.scoring import (
    apply_candidate_gates,
    rank_candidate_buckets,
    rank_unified_candidates,
    score_candidates,
)


CONFIG = ConsumerOversoldConfig(trade_date="2026-07-29")
V2_CONFIG = replace(CONFIG, ranking_version="v2")


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


def unified_rows(**overrides):
    row = {
        "asset_id": "A",
        "repair_bucket": "expected_repair",
        "eligible": True,
        "composite_score": 70.0,
        "elasticity_coverage": True,
        "elasticity_score": 60.0,
    }
    row.update(overrides)
    return row


def v2_rank_rows(**overrides):
    row = {
        "asset_id": "A",
        "repair_bucket": "expected_repair",
        "eligible": True,
        "composite_score": 70.0,
        "activation_coverage": True,
        "activation_eligible": True,
        "activation_score": 60.0,
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


def test_score_candidates_accepts_finite_database_decimal_as_float():
    result = score_candidates(
        pd.DataFrame([scoring_rows(base_upside=Decimal("0.50"))]), CONFIG
    ).iloc[0]
    assert result["base_upside"] == 0.5
    assert isinstance(result["base_upside"], float)


@pytest.mark.parametrize("invalid", [Decimal("NaN"), Decimal("Infinity")])
def test_score_candidates_rejects_non_finite_database_decimal(invalid):
    with pytest.raises(ValueError, match=r"A.*base_upside"):
        score_candidates(pd.DataFrame([scoring_rows(base_upside=invalid)]), CONFIG)


def test_score_candidates_rejects_fraction_despite_real_number_protocol():
    with pytest.raises(ValueError, match=r"A.*base_upside"):
        score_candidates(
            pd.DataFrame([scoring_rows(base_upside=Fraction(1, 3))]), CONFIG
        )


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("expected_improvement_score", Decimal("100.000000000000000000000000000001")),
        ("catalyst_verifiability_score", Decimal("100.000000000000000000000000000001")),
        ("valuation_depression_percentile", Decimal("1.000000000000000000000000000001")),
        ("oversold_score", Decimal("100.000000000000000000000000000001")),
        ("priced_in_penalty", Decimal("20.000000000000000000000000000001")),
    ],
)
def test_score_candidates_rejects_high_precision_decimal_just_above_range(field, invalid):
    with pytest.raises(ValueError, match=field):
        score_candidates(pd.DataFrame([scoring_rows(**{field: invalid})]), CONFIG)


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


def test_revenue_growth_gap_uses_fixed_thirty_percent_denominator():
    result = score_candidates(
        pd.DataFrame(
            [
                scoring_rows(
                    latest_net_margin=0.0,
                    normal_net_margin=0.10,
                    latest_roe=np.nan,
                    normal_roe=np.nan,
                    latest_revenue_growth=0.30,
                    normal_revenue_growth=0.60,
                )
            ]
        ),
        CONFIG,
    )

    assert result.loc[0, "operating_gap_score"] == 100.0


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


@pytest.mark.parametrize("industry", [None, pd.NA, "", "   "])
def test_score_candidates_rejects_empty_consumer_subindustry_with_asset(industry):
    with pytest.raises(ValueError, match=r"asset A.*consumer_subindustry"):
        score_candidates(
            pd.DataFrame([scoring_rows(consumer_subindustry=industry)]),
            CONFIG,
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


def test_v2_gate_admits_north_baic_edge_without_oversold_gate_and_v1_rejects():
    row = gate_rows(
        oversold_score=56.98,
        return_6m=-0.3125,
        max_drawdown_12m=-0.3913,
        relative_return_6m=-0.1007,
        base_upside=2.01,
        composite_score=34.54,
    )

    v2 = apply_candidate_gates(pd.DataFrame([row]), V2_CONFIG).iloc[0]
    v1 = apply_candidate_gates(pd.DataFrame([row]), CONFIG).iloc[0]

    assert bool(v2["eligible"])
    assert v2["exclusion_reasons"] == ""
    assert not bool(v1["eligible"])
    assert v1["exclusion_reasons"] == "oversold_score_below_threshold"


@pytest.mark.parametrize(
    ("composite_score", "eligible", "reason"),
    [
        (29.99, False, "composite_score_below_v2_threshold"),
        (30.0, True, ""),
        (
            Decimal("29.999999999999999999999999999999"),
            False,
            "composite_score_below_v2_threshold",
        ),
        (Decimal("30.000000000000000000000000000001"), True, ""),
    ],
)
def test_v2_gate_compares_composite_threshold_without_float_rounding(
    composite_score, eligible, reason
):
    result = apply_candidate_gates(
        pd.DataFrame([gate_rows(oversold_score=0.0, composite_score=composite_score)]),
        V2_CONFIG,
    ).iloc[0]

    assert bool(result["eligible"]) is eligible
    assert result["exclusion_reasons"] == reason


def test_v2_gate_preserves_missing_composite_reason_and_sorts_all_reasons():
    missing = apply_candidate_gates(
        pd.DataFrame([gate_rows(oversold_score=np.nan, composite_score=np.nan)]),
        V2_CONFIG,
    ).iloc[0]
    assert missing["exclusion_reasons"] == "composite_score_missing"

    failing = apply_candidate_gates(
        pd.DataFrame(
            [
                gate_rows(
                    included=False,
                    relative_return_6m=0.0,
                    oversold_score=0.0,
                    composite_score=29.0,
                )
            ]
        ),
        V2_CONFIG,
    ).iloc[0]
    assert failing["exclusion_reasons"] == "|".join(
        sorted(
            {
                "universe_excluded",
                "relative_return_threshold_not_met",
                "composite_score_below_v2_threshold",
            }
        )
    )


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


def test_completed_repair_detects_positive_latest_metrics_above_mixed_sign_normals():
    result = apply_candidate_gates(
        pd.DataFrame(
            [
                gate_rows(
                    asset_id="xinhee",
                    normal_revenue_growth=-0.0252,
                    normal_profit_growth=0.6813,
                    normal_net_margin=0.0109,
                    latest_revenue_growth=0.0939,
                    latest_profit_growth=1.446,
                    latest_net_margin=0.0198,
                )
            ]
        ),
        CONFIG,
    ).iloc[0]

    assert not bool(result["eligible"])
    assert result["exclusion_reasons"] == "repair_already_completed"


@pytest.mark.parametrize(
    "latest",
    [
        {
            "latest_revenue_growth": -0.01,
            "latest_profit_growth": 0.20,
            "latest_net_margin": 0.02,
        },
        {
            "latest_revenue_growth": 0.10,
            "latest_profit_growth": -0.10,
            "latest_net_margin": 0.02,
        },
        {
            "latest_revenue_growth": 0.10,
            "latest_profit_growth": 0.20,
            "latest_net_margin": -0.01,
        },
    ],
)
def test_negative_latest_metric_does_not_complete_repair_just_because_normal_is_lower(latest):
    result = apply_candidate_gates(
        pd.DataFrame(
            [
                gate_rows(
                    normal_revenue_growth=-0.0252,
                    normal_profit_growth=-0.50,
                    normal_net_margin=-0.05,
                    **latest,
                )
            ]
        ),
        CONFIG,
    ).iloc[0]

    assert bool(result["eligible"])
    assert "repair_already_completed" not in result["exclusion_reasons"]


@pytest.mark.parametrize(
    ("field", "value", "overrides", "eligible", "failure_code"),
    [
        ("return_6m", Decimal("-0.20"), {"max_drawdown_12m": -0.1}, True, ""),
        (
            "return_6m",
            Decimal("-0.199999999999999999999999999999"),
            {"max_drawdown_12m": -0.1},
            False,
            "price_threshold_not_met",
        ),
        (
            "return_6m",
            Decimal("-0.200000000000000000000000000001"),
            {"max_drawdown_12m": -0.1},
            True,
            "",
        ),
        ("max_drawdown_12m", Decimal("-0.30"), {"return_6m": -0.1}, True, ""),
        (
            "max_drawdown_12m",
            Decimal("-0.299999999999999999999999999999"),
            {"return_6m": -0.1},
            False,
            "price_threshold_not_met",
        ),
        (
            "max_drawdown_12m",
            Decimal("-0.300000000000000000000000000001"),
            {"return_6m": -0.1},
            True,
            "",
        ),
        ("relative_return_6m", Decimal("-0.10"), {}, True, ""),
        (
            "relative_return_6m",
            Decimal("-0.099999999999999999999999999999"),
            {},
            False,
            "relative_return_threshold_not_met",
        ),
        (
            "relative_return_6m",
            Decimal("-0.100000000000000000000000000001"),
            {},
            True,
            "",
        ),
        ("oversold_score", Decimal("60"), {}, True, ""),
        (
            "oversold_score",
            Decimal("59.999999999999999999999999999999"),
            {},
            False,
            "oversold_score_below_threshold",
        ),
        (
            "oversold_score",
            Decimal("60.000000000000000000000000000001"),
            {},
            True,
            "",
        ),
        ("base_upside", Decimal("0.25"), {}, True, ""),
        (
            "base_upside",
            Decimal("0.249999999999999999999999999999"),
            {},
            False,
            "base_upside_below_threshold",
        ),
        (
            "base_upside",
            Decimal("0.250000000000000000000000000001"),
            {},
            True,
            "",
        ),
    ],
)
def test_candidate_gates_compare_decimal_thresholds_without_float_rounding(
    field, value, overrides, eligible, failure_code
):
    row = gate_rows(**overrides)
    row[field] = value
    result = apply_candidate_gates(pd.DataFrame([row]), CONFIG).iloc[0]
    assert bool(result["eligible"]) is eligible
    if failure_code:
        assert failure_code in result["exclusion_reasons"]


def test_explicit_repair_completed_flag_overrides_financial_calculation():
    result = apply_candidate_gates(
        pd.DataFrame(
            [
                gate_rows(
                    repair_already_completed=True,
                    latest_revenue_growth=0.01,
                    latest_profit_growth=0.01,
                    latest_net_margin=0.01,
                )
            ]
        ),
        CONFIG,
    ).iloc[0]

    assert not bool(result["eligible"])
    assert result["exclusion_reasons"] == "repair_already_completed"


@pytest.mark.parametrize("invalid", [None, pd.NA, np.nan, 2, "yes"])
def test_explicit_repair_completed_flag_must_be_strict_boolean(invalid):
    with pytest.raises(ValueError, match=r"asset A.*repair_already_completed"):
        apply_candidate_gates(
            pd.DataFrame([gate_rows(repair_already_completed=invalid)]),
            CONFIG,
        )


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


@pytest.mark.parametrize("field", ["composite_score", "base_upside"])
def test_rank_rejects_missing_core_value_for_eligible_asset(field):
    row = {
        "asset_id": "A",
        "repair_bucket": "expected_repair",
        "eligible": True,
        "composite_score": 80.0,
        "base_upside": 0.5,
    }
    row[field] = np.nan

    with pytest.raises(ValueError, match=rf"asset A.*{field}"):
        rank_candidate_buckets(pd.DataFrame([row]), CONFIG)


def test_rank_allows_missing_core_values_for_ineligible_assets():
    rows = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "repair_bucket": "expected_repair",
                "eligible": False,
                "composite_score": np.nan,
                "base_upside": np.nan,
            }
        ]
    )

    result = rank_candidate_buckets(rows, CONFIG)

    assert result["expected"].empty
    assert result["early"].empty


def test_unified_rank_uses_exact_seventy_thirty_percentile_formula():
    rows = pd.DataFrame(
        [
            unified_rows(asset_id="A", composite_score=10.0, elasticity_score=100.0),
            unified_rows(asset_id="B", composite_score=20.0, elasticity_score=50.0),
            unified_rows(asset_id="C", composite_score=30.0, elasticity_score=0.0),
        ]
    )

    result = rank_unified_candidates(rows, CONFIG).set_index("asset_id")

    assert result.loc["A", "repair_rank_percentile"] == 0.0
    assert result.loc["A", "elasticity_rank_percentile"] == 100.0
    assert result.loc["A", "final_rank_score"] == pytest.approx(30.0)
    assert result.loc["B", "final_rank_score"] == pytest.approx(50.0)
    assert result.loc["C", "final_rank_score"] == pytest.approx(70.0)
    assert result.sort_values("final_rank").index.tolist() == ["C", "B", "A"]
    assert result.loc["C", "repair_bucket"] == "expected_repair"


def test_unified_rank_single_and_all_equal_cross_sections_return_fifty():
    single = rank_unified_candidates(pd.DataFrame([unified_rows()]), CONFIG).iloc[0]
    assert single["repair_rank_percentile"] == 50.0
    assert single["elasticity_rank_percentile"] == 50.0
    assert single["final_rank_score"] == 50.0

    equal = rank_unified_candidates(
        pd.DataFrame([unified_rows(asset_id="B"), unified_rows(asset_id="A")]),
        CONFIG,
    )
    assert equal["asset_id"].tolist() == ["A", "B"]
    assert equal["final_rank_score"].tolist() == [50.0, 50.0]
    assert equal["final_rank"].tolist() == [1, 2]


def test_unified_rank_excludes_ineligible_and_missing_elasticity_coverage():
    rows = pd.DataFrame(
        [
            unified_rows(asset_id="GOOD"),
            unified_rows(
                asset_id="INELIGIBLE",
                eligible=False,
                composite_score=100.0,
                elasticity_score=100.0,
            ),
            unified_rows(
                asset_id="UNCOVERED",
                elasticity_coverage=False,
                elasticity_score=np.nan,
            ),
        ]
    )

    result = rank_unified_candidates(rows, CONFIG)

    assert result["asset_id"].tolist() == ["GOOD"]


def test_unified_rank_stable_secondary_sorting_uses_composite_then_elasticity():
    composite_tiebreak = rank_unified_candidates(
        pd.DataFrame(
            [
                unified_rows(
                    asset_id="LOW", composite_score=10.0, elasticity_score=50.0
                ),
                unified_rows(
                    asset_id="HIGH", composite_score=20.0, elasticity_score=50.0
                ),
            ]
        ),
        replace(CONFIG, repair_rank_weight=0.0, elasticity_rank_weight=1.0),
    )
    assert composite_tiebreak["asset_id"].tolist() == ["HIGH", "LOW"]

    elasticity_tiebreak = rank_unified_candidates(
        pd.DataFrame(
            [
                unified_rows(
                    asset_id="LOW", composite_score=50.0, elasticity_score=10.0
                ),
                unified_rows(
                    asset_id="HIGH", composite_score=50.0, elasticity_score=20.0
                ),
            ]
        ),
        replace(CONFIG, repair_rank_weight=1.0, elasticity_rank_weight=0.0),
    )
    assert elasticity_tiebreak["asset_id"].tolist() == ["HIGH", "LOW"]


def test_recent_limit_up_has_no_direct_unified_rank_penalty():
    rows = pd.DataFrame(
        [
            unified_rows(asset_id="A", recent_limit_up=True),
            unified_rows(asset_id="B", recent_limit_up=False),
        ]
    )

    result = rank_unified_candidates(rows, CONFIG)

    assert result["asset_id"].tolist() == ["A", "B"]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("eligible", 1),
        ("elasticity_coverage", "true"),
        ("composite_score", True),
        ("elasticity_score", Fraction(1, 2)),
    ],
)
def test_unified_rank_rejects_non_strict_values(field, invalid):
    with pytest.raises(ValueError, match=field):
        rank_unified_candidates(
            pd.DataFrame([unified_rows(**{field: invalid})]), CONFIG
        )


def test_unified_rank_validates_columns_assets_and_empty_schema():
    rows = pd.DataFrame([unified_rows()])
    with pytest.raises(ValueError, match="elasticity_score"):
        rank_unified_candidates(rows.drop(columns="elasticity_score"), CONFIG)
    with pytest.raises(ValueError, match="duplicate asset_id"):
        rank_unified_candidates(pd.concat([rows, rows], ignore_index=True), CONFIG)
    with pytest.raises(ValueError, match="asset_id"):
        rank_unified_candidates(pd.DataFrame([unified_rows(asset_id=" ")]), CONFIG)
    with pytest.raises(ValueError, match="asset_id"):
        rank_unified_candidates(pd.DataFrame([unified_rows(asset_id=1)]), CONFIG)

    empty = rank_unified_candidates(pd.DataFrame(columns=rows.columns), CONFIG)
    assert empty.empty
    assert "final_rank_score" in empty.columns
    assert "final_rank" in empty.columns


def test_v2_rank_uses_exact_fifty_five_forty_five_percentile_formula():
    rows = pd.DataFrame(
        [
            v2_rank_rows(asset_id="A", composite_score=10.0, activation_score=100.0),
            v2_rank_rows(asset_id="B", composite_score=20.0, activation_score=50.0),
            v2_rank_rows(asset_id="C", composite_score=30.0, activation_score=0.0),
        ]
    )

    result = scoring_module.rank_v2_candidates(rows, V2_CONFIG).set_index("asset_id")

    assert result.loc["A", "repair_rank_percentile"] == 0.0
    assert result.loc["A", "activation_rank_percentile"] == 100.0
    assert result.loc["A", "final_rank_score_v2"] == pytest.approx(45.0)
    assert result.loc["B", "final_rank_score_v2"] == pytest.approx(50.0)
    assert result.loc["C", "final_rank_score_v2"] == pytest.approx(55.0)
    assert result["final_rank_score"].equals(result["final_rank_score_v2"])
    assert result.sort_values("final_rank").index.tolist() == ["C", "B", "A"]


def test_v2_rank_uses_required_tiebreak_order():
    activation_first = scoring_module.rank_v2_candidates(
        pd.DataFrame(
            [
                v2_rank_rows(asset_id="A", composite_score=10.0, activation_score=20.0),
                v2_rank_rows(asset_id="B", composite_score=20.0, activation_score=10.0),
            ]
        ),
        replace(
            V2_CONFIG,
            v2_repair_rank_weight=0.5,
            v2_activation_rank_weight=0.5,
        ),
    )
    assert activation_first["asset_id"].tolist() == ["A", "B"]

    repair_second = scoring_module.rank_v2_candidates(
        pd.DataFrame(
            [
                v2_rank_rows(asset_id="A", composite_score=10.0, activation_score=20.0),
                v2_rank_rows(asset_id="B", composite_score=20.0, activation_score=20.0),
            ]
        ),
        replace(
            V2_CONFIG,
            v2_repair_rank_weight=0.0,
            v2_activation_rank_weight=1.0,
        ),
    )
    assert repair_second["asset_id"].tolist() == ["B", "A"]

    asset_id_last = scoring_module.rank_v2_candidates(
        pd.DataFrame([v2_rank_rows(asset_id="B"), v2_rank_rows(asset_id="A")]),
        V2_CONFIG,
    )
    assert asset_id_last["asset_id"].tolist() == ["A", "B"]
    assert asset_id_last["final_rank"].tolist() == [1, 2]


def test_v2_rank_is_shuffle_deterministic_and_ignores_stock_identity_columns():
    rows = pd.DataFrame(
        [
            v2_rank_rows(
                asset_id="A", composite_score=10.0, activation_score=30.0,
                stock_code="ZZZ", stock_name="last",
            ),
            v2_rank_rows(
                asset_id="B", composite_score=20.0, activation_score=20.0,
                stock_code="AAA", stock_name="first",
            ),
            v2_rank_rows(
                asset_id="C", composite_score=30.0, activation_score=10.0,
                stock_code="MMM", stock_name="middle",
            ),
        ]
    )

    expected = scoring_module.rank_v2_candidates(rows, V2_CONFIG)
    shuffled = scoring_module.rank_v2_candidates(
        rows.sample(frac=1.0, random_state=7), V2_CONFIG
    )

    pd.testing.assert_frame_equal(expected, shuffled)


def test_v2_rank_candidate_universe_excludes_incomplete_rows_from_percentiles():
    rows = pd.DataFrame(
        [
            v2_rank_rows(asset_id="LOW", composite_score=10.0, activation_score=10.0),
            v2_rank_rows(
                asset_id="HIGH",
                repair_bucket="unrecognized_but_not_a_rank_filter",
                composite_score=20.0,
                activation_score=20.0,
            ),
            v2_rank_rows(
                asset_id="INELIGIBLE",
                eligible=False,
                composite_score=1000.0,
                activation_score=1000.0,
            ),
            v2_rank_rows(
                asset_id="UNCOVERED",
                activation_coverage=False,
                composite_score=np.nan,
                activation_score=np.nan,
            ),
            v2_rank_rows(
                asset_id="ACTIVATION_FAIL",
                activation_eligible=False,
                composite_score=-1000.0,
                activation_score=-1000.0,
            ),
        ]
    )

    result = scoring_module.rank_v2_candidates(rows, V2_CONFIG).set_index("asset_id")

    assert result.index.tolist() == ["HIGH", "LOW"]
    assert result.loc["LOW", "repair_rank_percentile"] == 0.0
    assert result.loc["LOW", "activation_rank_percentile"] == 0.0
    assert result.loc["HIGH", "repair_rank_percentile"] == 100.0
    assert result.loc["HIGH", "activation_rank_percentile"] == 100.0


def test_v2_rank_single_and_all_equal_cross_sections_return_fifty():
    single = scoring_module.rank_v2_candidates(
        pd.DataFrame([v2_rank_rows()]), V2_CONFIG
    ).iloc[0]
    assert single["repair_rank_percentile"] == 50.0
    assert single["activation_rank_percentile"] == 50.0
    assert single["final_rank_score_v2"] == 50.0

    equal = scoring_module.rank_v2_candidates(
        pd.DataFrame([v2_rank_rows(asset_id="B"), v2_rank_rows(asset_id="A")]),
        V2_CONFIG,
    )
    assert equal["asset_id"].tolist() == ["A", "B"]
    assert equal["final_rank_score_v2"].tolist() == [50.0, 50.0]


@pytest.mark.parametrize("field", ["composite_score", "activation_score"])
def test_v2_rank_rejects_missing_selected_values(field):
    with pytest.raises(ValueError, match=rf"asset A.*{field}"):
        scoring_module.rank_v2_candidates(
            pd.DataFrame([v2_rank_rows(**{field: np.nan})]), V2_CONFIG
        )


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("eligible", 1),
        ("activation_coverage", "true"),
        ("activation_eligible", np.nan),
        ("composite_score", True),
        ("activation_score", Fraction(1, 2)),
    ],
)
def test_v2_rank_rejects_non_strict_values(field, invalid):
    with pytest.raises(ValueError, match=field):
        scoring_module.rank_v2_candidates(
            pd.DataFrame([v2_rank_rows(**{field: invalid})]), V2_CONFIG
        )


def test_v2_rank_rejects_malformed_numeric_even_when_row_is_excluded():
    with pytest.raises(ValueError, match="activation_score"):
        scoring_module.rank_v2_candidates(
            pd.DataFrame(
                [v2_rank_rows(eligible=False, activation_score="not numeric")]
            ),
            V2_CONFIG,
        )


def test_v2_rank_validates_version_columns_assets_indexes_and_empty_schema():
    rows = pd.DataFrame([v2_rank_rows()])
    with pytest.raises(
        ValueError, match="^rank_v2_candidates requires ranking_version v2$"
    ):
        scoring_module.rank_v2_candidates(rows, CONFIG)
    with pytest.raises(ValueError, match="activation_score"):
        scoring_module.rank_v2_candidates(
            rows.drop(columns="activation_score"), V2_CONFIG
        )
    with pytest.raises(ValueError, match="duplicate asset_id A"):
        scoring_module.rank_v2_candidates(
            pd.DataFrame(
                [v2_rank_rows(asset_id=" A "), v2_rank_rows(asset_id="A")]
            ),
            V2_CONFIG,
        )
    for invalid in (" ", 1):
        with pytest.raises(ValueError, match="asset_id"):
            scoring_module.rank_v2_candidates(
                pd.DataFrame([v2_rank_rows(asset_id=invalid)]), V2_CONFIG
            )

    duplicate_index = pd.DataFrame(
        [
            v2_rank_rows(
                asset_id=" B ", composite_score=10.0, activation_score=10.0
            ),
            v2_rank_rows(asset_id="A", composite_score=20.0, activation_score=20.0),
            v2_rank_rows(asset_id="C", composite_score=30.0, activation_score=30.0),
        ],
        index=[7, 7, 9],
    )
    ranked = scoring_module.rank_v2_candidates(duplicate_index, V2_CONFIG)
    assert ranked["asset_id"].tolist() == ["C", "A", "B"]

    empty = scoring_module.rank_v2_candidates(pd.DataFrame(), V2_CONFIG)
    assert empty.empty
    assert list(empty.columns) == V2_RANK_COLUMNS_FOR_TEST + [
        "repair_rank_percentile",
        "activation_rank_percentile",
        "final_rank_score_v2",
        "final_rank_score",
        "final_rank",
    ]


def test_v2_rank_does_not_mutate_input():
    rows = pd.DataFrame(
        [v2_rank_rows(asset_id=" B "), v2_rank_rows(asset_id="A")], index=[5, 3]
    )
    original = rows.copy(deep=True)

    scoring_module.rank_v2_candidates(rows, V2_CONFIG)

    pd.testing.assert_frame_equal(rows, original)


@pytest.mark.parametrize(
    ("function", "rows"),
    [
        (
            score_candidates,
            pd.DataFrame([scoring_rows(asset_id=" A "), scoring_rows(asset_id="A")]),
        ),
        (
            apply_candidate_gates,
            pd.DataFrame([gate_rows(asset_id=" A "), gate_rows(asset_id="A")]),
        ),
        (
            rank_candidate_buckets,
            pd.DataFrame(
                [
                    {"asset_id": " A ", "repair_bucket": "expected_repair", "eligible": True, "composite_score": 80.0, "base_upside": 0.5},
                    {"asset_id": "A", "repair_bucket": "early_validation", "eligible": True, "composite_score": 70.0, "base_upside": 0.4},
                ]
            ),
        ),
    ],
)
def test_entry_points_strip_asset_id_before_duplicate_validation(function, rows):
    with pytest.raises(ValueError, match="duplicate asset_id A"):
        function(rows, CONFIG)


@pytest.mark.parametrize(
    ("function", "rows"),
    [
        (score_candidates, pd.DataFrame([scoring_rows(asset_id=" A ")])),
        (apply_candidate_gates, pd.DataFrame([gate_rows(asset_id=" A ")])),
        (
            rank_candidate_buckets,
            pd.DataFrame(
                [{"asset_id": " A ", "repair_bucket": "expected_repair", "eligible": True, "composite_score": 80.0, "base_upside": 0.5}]
            ),
        ),
    ],
)
def test_entry_points_output_stripped_asset_id(function, rows):
    result = function(rows, CONFIG)
    frame = result["expected"] if isinstance(result, dict) else result
    assert frame.loc[0, "asset_id"] == "A"


RANK_COLUMNS_FOR_TEST = [
    "asset_id",
    "repair_bucket",
    "eligible",
    "composite_score",
    "base_upside",
]

V2_RANK_COLUMNS_FOR_TEST = [
    "asset_id",
    "repair_bucket",
    "eligible",
    "composite_score",
    "activation_coverage",
    "activation_eligible",
    "activation_score",
]
