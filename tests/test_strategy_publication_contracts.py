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


def test_static_publication_identities_match_database_contracts():
    expected = {
        "lhb_shortline": (
            "lhb_shortline:balanced:auction_enhanced_rerank:balanced",
            "41cdc85b187d8290cf4196c9d1b64d6cc6fc61ab7dff465c2e52e547021e1e30",
        ),
        "mid_trend": (
            "mid_trend:balanced:top5_weekly_max2_selective_trend_holding_protection_v1",
            "b6230300f258af1da50d717ac1099d63c0cb738f385a49c92bc77417c64af5e5",
        ),
        "tech_bottleneck": (
            "tech_bottleneck:balanced:strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d",
            "1198d8067218ad26b49a29341093eb839ee887b14b18b359bcaa2b80514f8ee1",
        ),
    }
    assert OFFICIAL_STRATEGY_IDS == frozenset(expected)
    for strategy_id, (contract_id, fingerprint) in expected.items():
        contract = get_publication_contract(strategy_id)
        identity = build_publication_identity(contract)
        assert identity["contract_id"] == contract_id
        assert identity["config_fingerprint"] == fingerprint


def test_publication_contracts_are_immutable_and_fingerprints_are_canonical():
    contract = get_publication_contract("mid_trend")
    with pytest.raises(FrozenInstanceError):
        contract.strategy_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        contract.normalized_run_config["top_n"] = 10  # type: ignore[index]
    assert canonical_config_fingerprint({"b": 2, "a": 1}) == canonical_config_fingerprint(
        {"a": 1, "b": 2}
    )


def test_publication_identity_validation_rejects_missing_and_extra_fields():
    expected = build_publication_identity(get_publication_contract("lhb_shortline"))
    actual = dict(expected)
    del actual["engine_version"]
    actual["unexpected"] = True
    mismatches = validate_publication_identity(actual, expected)
    assert {item["field"] for item in mismatches} == {"engine_version", "unexpected"}


def test_nested_inputs_are_snapshotted_and_built_identity_is_detached():
    source_config = {"nested": {"weights": [1, 2]}}
    source_policy = {"nested": {"rules": ["keep"]}}
    contract = StrategyPublicationContract(
        strategy_id="test",
        profile="balanced",
        contract_id="test:balanced:v1",
        engine_version="test_v1",
        variant="v1",
        normalized_run_config=source_config,
        publication_policy=source_policy,
    )
    source_config["nested"]["weights"].append(3)
    source_policy["nested"]["rules"].append("replace")
    identity = build_publication_identity(contract)
    identity["publication_policy"]["nested"]["rules"].append("mutate")
    assert contract.normalized_run_config["nested"]["weights"] == (1, 2)
    assert build_publication_identity(contract)["publication_policy"] == {
        "nested": {"rules": ["keep"]}
    }
