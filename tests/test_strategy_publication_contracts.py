from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from stock_research.strategy_publication_contracts import (
    OFFICIAL_STRATEGY_IDS,
    StrategyPublicationContract,
    build_publication_identity,
    canonical_config_fingerprint,
    get_publication_contract,
    validate_publication_identity,
)


def test_balanced_registry_contains_the_three_official_contracts():
    assert OFFICIAL_STRATEGY_IDS == {"lhb_shortline", "mid_trend", "tech_bottleneck"}

    expected = {
        "lhb_shortline": (
            "lhb_shortline_v1",
            "auction_enhanced_rerank:balanced",
            "daily",
            {"risk_profile": "balanced"},
        ),
        "mid_trend": (
            "mid_trend_v1",
            "top5_weekly_max2_selective_trend_holding_protection_v1",
            "weekly",
            {"benchmark_variant": "top5_weekly_max2_selective_trend_holding_protection_v1"},
        ),
        "tech_bottleneck": (
            "tech_bottleneck_v1",
            "strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d",
            "biweekly",
            {
                "universe": "strict_153_st_only_financial_state",
                "protection_name": "rank_exit_top10_1d",
            },
        ),
    }
    for strategy_id, (engine, variant, frequency, specific) in expected.items():
        contract = get_publication_contract(strategy_id)
        assert isinstance(contract, StrategyPublicationContract)
        assert contract.profile == "balanced"
        assert contract.engine_version == engine
        assert contract.variant == variant
        assert contract.contract_id == f"{strategy_id}:balanced:{variant}"
        assert contract.normalized_run_config == {
            "top_n": 5,
            "rebalance_frequency": frequency,
            "transaction_cost_bps": 10.0,
            "max_position_weight": 0.2,
            "adjust_type": "hfq",
            **specific,
        }


def test_lhb_publication_policy_is_exact():
    contract = get_publication_contract("lhb_shortline")
    assert contract.publication_policy == {
        "strategy_version": "lhb_v1_stable_safe_top5",
        "selection_policy": "phase18c_top5_then_eligibility_no_refill",
        "market_regime_policy": "disabled_for_stable_strategy",
    }


def test_publication_contract_is_frozen():
    contract = get_publication_contract("mid_trend")
    with pytest.raises(FrozenInstanceError):
        contract.strategy_id = "other"  # type: ignore[misc]


def test_fingerprint_is_order_independent_and_uses_utf8_canonical_json():
    first = {"β": 2, "a": 1}
    second = {"a": 1, "β": 2}
    assert canonical_config_fingerprint(first) == canonical_config_fingerprint(second)
    assert canonical_config_fingerprint(first) == (
        "e3a98a14fe4a2fc5f208bc422128a1173a6859ee920f60256c8c24c524caf3b4"
    )


def test_identity_is_derived_from_contract():
    contract = get_publication_contract("tech_bottleneck")
    identity = build_publication_identity(contract)
    assert identity == {
        "identity_schema_version": "strategy_publication_identity_v1",
        "strategy_id": "tech_bottleneck",
        "contract_id": contract.contract_id,
        "engine_version": "tech_bottleneck_v1",
        "variant": contract.variant,
        "config_fingerprint": canonical_config_fingerprint(contract.normalized_run_config),
        "publication_policy": contract.publication_policy,
    }


def test_unknown_strategy_or_profile_fails():
    with pytest.raises(KeyError):
        get_publication_contract("not_official")
    with pytest.raises(KeyError):
        get_publication_contract("lhb_shortline", profile="experimental")


def test_identity_mismatch_reports_common_and_nested_policy_fields():
    contract = get_publication_contract("lhb_shortline")
    expected = build_publication_identity(contract)
    actual = dict(expected)
    actual["engine_version"] = "wrong_engine"
    actual["publication_policy"] = {
        **expected["publication_policy"],
        "market_regime_policy": "legacy_overlay",
    }

    mismatches = validate_publication_identity(actual, expected)
    assert mismatches == [
        {"field": "engine_version", "expected": "lhb_shortline_v1", "actual": "wrong_engine"},
        {
            "field": "publication_policy",
            "expected": expected["publication_policy"],
            "actual": actual["publication_policy"],
        },
    ]


def test_identity_mismatch_reports_every_missing_field_without_coercing_values():
    expected = build_publication_identity(get_publication_contract("mid_trend"))

    mismatches = validate_publication_identity({"publication_policy": "invalid"}, expected)

    assert [mismatch["field"] for mismatch in mismatches] == list(expected)
    assert mismatches[-1] == {
        "field": "publication_policy",
        "expected": expected["publication_policy"],
        "actual": "invalid",
    }
