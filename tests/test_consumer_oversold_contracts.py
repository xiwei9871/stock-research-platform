from dataclasses import FrozenInstanceError

import pytest

from stock_research.consumer_oversold import (
    ConsumerOversoldConfig as PublicConsumerOversoldConfig,
    EARLY_VALIDATION as PUBLIC_EARLY_VALIDATION,
    EXPECTED_REPAIR as PUBLIC_EXPECTED_REPAIR,
)
from stock_research.consumer_oversold.contracts import (
    EARLY_VALIDATION,
    EXPECTED_REPAIR,
    OUTPUT_FILENAMES,
    REPAIR_BUCKETS,
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


def test_repair_bucket_constants_are_stable():
    assert EXPECTED_REPAIR == "expected_repair"
    assert EARLY_VALIDATION == "early_validation"
    assert REPAIR_BUCKETS == (EXPECTED_REPAIR, EARLY_VALIDATION)


def test_package_exports_public_contracts():
    assert PublicConsumerOversoldConfig is ConsumerOversoldConfig
    assert PUBLIC_EXPECTED_REPAIR == EXPECTED_REPAIR
    assert PUBLIC_EARLY_VALIDATION == EARLY_VALIDATION


def test_output_filenames_are_stable():
    assert OUTPUT_FILENAMES == {
        "evidence": "consumer_oversold_repair_evidence.csv",
        "expected": "consumer_oversold_expected_repair_top20.csv",
        "early": "consumer_oversold_early_validation_top20.csv",
        "scores": "consumer_oversold_full_scores.csv",
        "exclusions": "consumer_oversold_exclusions.csv",
        "coverage": "consumer_oversold_data_coverage_audit.json",
        "report": "consumer_oversold_weekly_report.md",
    }


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
