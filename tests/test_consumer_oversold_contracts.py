from dataclasses import FrozenInstanceError

import pytest

from stock_research.consumer_oversold import (
    LEGACY_OUTPUT_FILENAMES as PUBLIC_LEGACY_OUTPUT_FILENAMES,
    OUTPUT_FILENAMES as PUBLIC_OUTPUT_FILENAMES,
    UNIFIED_OUTPUT_FILENAMES as PUBLIC_UNIFIED_OUTPUT_FILENAMES,
    ConsumerOversoldConfig as PublicConsumerOversoldConfig,
    EARLY_VALIDATION as PUBLIC_EARLY_VALIDATION,
    EXPECTED_REPAIR as PUBLIC_EXPECTED_REPAIR,
)
from stock_research.consumer_oversold.contracts import (
    EARLY_VALIDATION,
    EXPECTED_REPAIR,
    LEGACY_OUTPUT_FILENAMES,
    OUTPUT_FILENAMES,
    REPAIR_BUCKETS,
    UNIFIED_OUTPUT_FILENAMES,
    ConsumerOversoldConfig,
    validate_trade_date,
)


def test_default_config_matches_approved_design():
    config = ConsumerOversoldConfig(trade_date="2026-07-29")

    assert config.lookback_6m_bars == 126
    assert config.lookback_12m_bars == 252
    assert config.valuation_lookback_years == 5
    assert config.min_listed_days == 365
    assert config.min_avg_turnover_amount == 30_000_000.0
    assert config.min_6m_return == -0.20
    assert config.min_12m_drawdown == -0.30
    assert config.min_relative_return == -0.10
    assert config.min_oversold_score == 60.0
    assert config.min_base_upside == 0.25
    assert config.max_per_bucket == 20
    assert config.max_priced_in_penalty == 20.0


def test_elasticity_ranking_defaults_match_approved_design():
    config = ConsumerOversoldConfig(trade_date="2026-07-29")

    assert config.repair_rank_weight == 0.70
    assert config.elasticity_rank_weight == 0.30
    assert config.residual_deviation_weight == 0.35
    assert config.stock_character_weight == 0.25
    assert config.market_capacity_weight == 0.20
    assert config.catalyst_liquidity_weight == 0.20
    assert config.preaudit_size == 60
    assert config.minimum_evidence_complete == 40
    assert config.final_top_n == 20
    assert config.reserve_top_n == 20


def test_v2_config_defaults_match_approved_design():
    config = ConsumerOversoldConfig(trade_date="2026-07-27", ranking_version="v2")

    assert config.v2_min_composite_score == 30.0
    assert config.v2_min_technical_readiness_score == 35.0
    assert config.v2_repair_rank_weight == 0.55
    assert config.v2_activation_rank_weight == 0.45
    assert (
        config.technical_readiness_weight,
        config.continuation_character_weight,
        config.residual_price_space_weight,
        config.capital_efficiency_weight,
        config.catalyst_timing_weight,
    ) == (0.30, 0.25, 0.20, 0.15, 0.10)


def test_config_defaults_to_v1_ranking_version():
    assert ConsumerOversoldConfig(trade_date="2026-07-27").ranking_version == "v1"


@pytest.mark.parametrize("ranking_version", ["", "V2", "v3", None])
def test_config_rejects_unknown_ranking_version(ranking_version):
    with pytest.raises(ValueError, match="ranking_version must be v1 or v2"):
        ConsumerOversoldConfig(
            trade_date="2026-07-27", ranking_version=ranking_version
        )


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("v2_min_composite_score", float("nan")),
        ("v2_min_composite_score", -0.01),
        ("v2_min_technical_readiness_score", float("inf")),
        ("v2_min_technical_readiness_score", 100.01),
    ],
)
def test_v2_thresholds_reject_non_finite_and_out_of_range_values(field_name, invalid):
    with pytest.raises(ValueError, match=field_name):
        ConsumerOversoldConfig(trade_date="2026-07-27", **{field_name: invalid})


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("v2_repair_rank_weight", float("nan")),
        ("v2_activation_rank_weight", float("inf")),
        ("technical_readiness_weight", -0.01),
        ("continuation_character_weight", 1.01),
        ("residual_price_space_weight", float("nan")),
        ("capital_efficiency_weight", float("inf")),
        ("catalyst_timing_weight", -0.01),
    ],
)
def test_v2_weights_reject_invalid_individual_values(field_name, invalid):
    with pytest.raises(ValueError, match=field_name):
        ConsumerOversoldConfig(trade_date="2026-07-27", **{field_name: invalid})


@pytest.mark.parametrize(
    "overrides",
    [
        {"v2_repair_rank_weight": 0.5500000000005},
        {"technical_readiness_weight": 0.3000000000005},
    ],
)
def test_v2_weight_groups_require_an_exact_sum_of_one(overrides):
    with pytest.raises(ValueError, match="must sum to 1.0"):
        ConsumerOversoldConfig(trade_date="2026-07-27", **overrides)


def test_repair_bucket_constants_are_stable():
    assert EXPECTED_REPAIR == "expected_repair"
    assert EARLY_VALIDATION == "early_validation"
    assert REPAIR_BUCKETS == (EXPECTED_REPAIR, EARLY_VALIDATION)


def test_package_exports_public_contracts():
    assert PublicConsumerOversoldConfig is ConsumerOversoldConfig
    assert PUBLIC_EXPECTED_REPAIR == EXPECTED_REPAIR
    assert PUBLIC_EARLY_VALIDATION == EARLY_VALIDATION
    assert PUBLIC_OUTPUT_FILENAMES is OUTPUT_FILENAMES
    assert PUBLIC_UNIFIED_OUTPUT_FILENAMES is UNIFIED_OUTPUT_FILENAMES
    assert PUBLIC_LEGACY_OUTPUT_FILENAMES is LEGACY_OUTPUT_FILENAMES


def test_unified_output_filenames_are_stable():
    assert UNIFIED_OUTPUT_FILENAMES == {
        "evidence": "consumer_oversold_repair_evidence.csv",
        "scores": "consumer_oversold_full_scores.csv",
        "exclusions": "consumer_oversold_exclusions.csv",
        "coverage": "consumer_oversold_data_coverage_audit.json",
        "report": "consumer_oversold_weekly_report.md",
        "top20": "consumer_oversold_unified_top20.csv",
        "reserve": "consumer_oversold_reserve_21_40.csv",
        "preaudit": "consumer_oversold_preaudit_top60.csv",
        "comparison": "consumer_oversold_old_new_rank_comparison.csv",
    }


def test_legacy_output_filenames_remain_available_for_historical_evaluation():
    assert LEGACY_OUTPUT_FILENAMES == {
        "evidence": "consumer_oversold_repair_evidence.csv",
        "expected": "consumer_oversold_expected_repair_top20.csv",
        "early": "consumer_oversold_early_validation_top20.csv",
        "scores": "consumer_oversold_full_scores.csv",
        "exclusions": "consumer_oversold_exclusions.csv",
        "coverage": "consumer_oversold_data_coverage_audit.json",
        "report": "consumer_oversold_weekly_report.md",
    }


def test_current_output_filenames_remain_stable_during_migration():
    assert OUTPUT_FILENAMES == LEGACY_OUTPUT_FILENAMES


def test_trade_date_must_be_real_iso_date():
    assert validate_trade_date("2026-07-29") == "2026-07-29"

    for invalid in ["20260729", "2026-02-30", "", None, 20260729]:
        with pytest.raises(ValueError):
            validate_trade_date(invalid)


@pytest.mark.parametrize("max_per_bucket", [1, 20])
def test_max_per_bucket_accepts_inclusive_bounds(max_per_bucket):
    config = ConsumerOversoldConfig(
        trade_date="2026-07-29",
        max_per_bucket=max_per_bucket,
    )

    assert config.max_per_bucket == max_per_bucket


@pytest.mark.parametrize("max_per_bucket", [0, 21])
def test_max_per_bucket_rejects_values_outside_bounds(max_per_bucket):
    with pytest.raises(ValueError, match="max_per_bucket"):
        ConsumerOversoldConfig(
            trade_date="2026-07-29",
            max_per_bucket=max_per_bucket,
        )


@pytest.mark.parametrize("max_per_bucket", [True, False, 1.0, 1.5, "1"])
def test_max_per_bucket_rejects_non_integer_values(max_per_bucket):
    with pytest.raises(ValueError, match="max_per_bucket"):
        ConsumerOversoldConfig(
            trade_date="2026-07-29",
            max_per_bucket=max_per_bucket,
        )


def test_config_is_frozen():
    config = ConsumerOversoldConfig(trade_date="2026-07-29")

    with pytest.raises(FrozenInstanceError):
        config.max_per_bucket = 10


@pytest.mark.parametrize(
    ("overrides", "field_name"),
    [
        ({"repair_rank_weight": float("nan")}, "repair_rank_weight"),
        ({"elasticity_rank_weight": float("inf")}, "elasticity_rank_weight"),
        ({"residual_deviation_weight": "0.35"}, "residual_deviation_weight"),
        ({"stock_character_weight": True}, "stock_character_weight"),
        ({"market_capacity_weight": -0.01}, "market_capacity_weight"),
        ({"catalyst_liquidity_weight": 1.01}, "catalyst_liquidity_weight"),
    ],
)
def test_ranking_weights_reject_invalid_numeric_values(overrides, field_name):
    with pytest.raises(ValueError, match=field_name):
        ConsumerOversoldConfig(trade_date="2026-07-29", **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"repair_rank_weight": 0.69, "elasticity_rank_weight": 0.30},
        {
            "residual_deviation_weight": 0.34,
            "stock_character_weight": 0.25,
            "market_capacity_weight": 0.20,
            "catalyst_liquidity_weight": 0.20,
        },
    ],
)
def test_ranking_weight_groups_must_sum_to_one(overrides):
    with pytest.raises(ValueError, match="sum to 1.0"):
        ConsumerOversoldConfig(trade_date="2026-07-29", **overrides)


@pytest.mark.parametrize(
    "field_name",
    ["preaudit_size", "minimum_evidence_complete", "final_top_n", "reserve_top_n"],
)
@pytest.mark.parametrize("invalid", [True, False, 1.0, "20"])
def test_ranking_sizes_reject_non_integer_values(field_name, invalid):
    with pytest.raises(ValueError, match=field_name):
        ConsumerOversoldConfig(trade_date="2026-07-29", **{field_name: invalid})


@pytest.mark.parametrize("field_name", ["final_top_n", "reserve_top_n"])
@pytest.mark.parametrize("invalid", [0, 101])
def test_final_and_reserve_sizes_reject_values_outside_bounds(field_name, invalid):
    with pytest.raises(ValueError, match=field_name):
        ConsumerOversoldConfig(trade_date="2026-07-29", **{field_name: invalid})


@pytest.mark.parametrize("field_name", ["preaudit_size", "minimum_evidence_complete"])
def test_candidate_pool_sizes_cover_final_and_reserve(field_name):
    with pytest.raises(ValueError, match=field_name):
        ConsumerOversoldConfig(trade_date="2026-07-29", **{field_name: 39})


def test_minimum_evidence_complete_cannot_exceed_preaudit_size():
    with pytest.raises(
        ValueError, match="minimum_evidence_complete.*preaudit_size"
    ):
        ConsumerOversoldConfig(
            trade_date="2026-07-29",
            preaudit_size=40,
            minimum_evidence_complete=41,
        )


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("lookback_6m_bars", True),
        ("lookback_12m_bars", 0),
        ("valuation_lookback_years", 1.0),
        ("min_listed_days", -1),
        ("min_avg_turnover_amount", float("nan")),
        ("min_6m_return", float("inf")),
        ("min_12m_drawdown", "-0.30"),
        ("min_relative_return", False),
        ("min_oversold_score", -0.01),
        ("min_base_upside", float("nan")),
        ("max_priced_in_penalty", 100.01),
    ],
)
def test_existing_numeric_config_fields_are_validated(field_name, invalid):
    with pytest.raises(ValueError, match=field_name):
        ConsumerOversoldConfig(trade_date="2026-07-29", **{field_name: invalid})
