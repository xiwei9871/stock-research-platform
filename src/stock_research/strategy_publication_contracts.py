"""Registry and identity helpers for officially publishable strategy runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


IDENTITY_SCHEMA_VERSION = "strategy_publication_identity_v1"
OFFICIAL_STRATEGY_IDS = {"lhb_shortline", "mid_trend", "tech_bottleneck"}


@dataclass(frozen=True)
class StrategyPublicationContract:
    strategy_id: str
    profile: str
    contract_id: str
    engine_version: str
    variant: str
    normalized_run_config: Mapping[str, Any]
    publication_policy: Mapping[str, Any]
    identity_schema_version: str = IDENTITY_SCHEMA_VERSION
    acceptance_profile: str = "default"

    def __post_init__(self) -> None:
        # Freeze the two mapping fields as well as the dataclass attributes.
        object.__setattr__(
            self,
            "normalized_run_config",
            MappingProxyType(dict(self.normalized_run_config)),
        )
        object.__setattr__(self, "publication_policy", MappingProxyType(dict(self.publication_policy)))


def canonical_config_fingerprint(mapping: Mapping[str, Any]) -> str:
    """Return the SHA-256 digest of the contract's canonical JSON config."""

    serialized = json.dumps(
        dict(mapping),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def build_publication_identity(contract: StrategyPublicationContract) -> dict[str, Any]:
    return {
        "identity_schema_version": contract.identity_schema_version,
        "strategy_id": contract.strategy_id,
        "contract_id": contract.contract_id,
        "engine_version": contract.engine_version,
        "variant": contract.variant,
        "config_fingerprint": canonical_config_fingerprint(contract.normalized_run_config),
        "publication_policy": dict(contract.publication_policy),
    }


def validate_publication_identity(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return field-level differences between actual and expected identities."""

    mismatches: list[dict[str, Any]] = []
    for field in (
        "identity_schema_version",
        "strategy_id",
        "contract_id",
        "engine_version",
        "variant",
        "config_fingerprint",
        "publication_policy",
    ):
        expected_value = expected.get(field)
        actual_value = actual.get(field)
        if actual_value != expected_value:
            mismatches.append(
                {"field": field, "expected": expected_value, "actual": actual_value}
            )
    return mismatches


def _contract(
    strategy_id: str,
    *,
    engine_version: str,
    variant: str,
    frequency: str,
    strategy_config: Mapping[str, Any],
    publication_policy: Mapping[str, Any],
) -> StrategyPublicationContract:
    return StrategyPublicationContract(
        strategy_id=strategy_id,
        profile="balanced",
        contract_id=f"{strategy_id}:balanced:{variant}",
        engine_version=engine_version,
        variant=variant,
        normalized_run_config={
            "top_n": 5,
            "rebalance_frequency": frequency,
            "transaction_cost_bps": 10.0,
            "max_position_weight": 0.2,
            "adjust_type": "hfq",
            **dict(strategy_config),
        },
        publication_policy=publication_policy,
    )


_PUBLICATION_CONTRACTS: dict[tuple[str, str], StrategyPublicationContract] = {
    ("lhb_shortline", "balanced"): _contract(
        "lhb_shortline",
        engine_version="lhb_shortline_v1",
        variant="auction_enhanced_rerank:balanced",
        frequency="daily",
        strategy_config={"risk_profile": "balanced"},
        publication_policy={
            "strategy_version": "lhb_v1_stable_safe_top5",
            "selection_policy": "phase18c_top5_then_eligibility_no_refill",
            "market_regime_policy": "disabled_for_stable_strategy",
        },
    ),
    ("mid_trend", "balanced"): _contract(
        "mid_trend",
        engine_version="mid_trend_v1",
        variant="top5_weekly_max2_selective_trend_holding_protection_v1",
        frequency="weekly",
        strategy_config={
            "benchmark_variant": "top5_weekly_max2_selective_trend_holding_protection_v1"
        },
        publication_policy={
            "benchmark_variant": "top5_weekly_max2_selective_trend_holding_protection_v1"
        },
    ),
    ("tech_bottleneck", "balanced"): _contract(
        "tech_bottleneck",
        engine_version="tech_bottleneck_v1",
        variant="strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d",
        frequency="biweekly",
        strategy_config={
            "universe": "strict_153_st_only_financial_state",
            "protection_name": "rank_exit_top10_1d",
        },
        publication_policy={
            "universe": "strict_153_st_only_financial_state",
            "frequency": "biweekly",
            "protection_name": "rank_exit_top10_1d",
        },
    ),
}


def get_publication_contract(
    strategy_id: str,
    profile: str = "balanced",
) -> StrategyPublicationContract:
    try:
        return _PUBLICATION_CONTRACTS[(strategy_id, profile)]
    except KeyError as exc:
        raise KeyError(f"unknown strategy publication contract: {strategy_id}/{profile}") from exc
