from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SOFT_OWNERSHIP_START_DATE = "2025-01-01"
DEFAULT_SOFT_OWNERSHIP_END_DATE = "2026-06-12"


@dataclass(frozen=True)
class MidTrendSoftOwnershipConfig:
    variant_name: str
    start_date: str = DEFAULT_SOFT_OWNERSHIP_START_DATE
    end_date: str = DEFAULT_SOFT_OWNERSHIP_END_DATE
    top_n: int = 5
    entry_weak_rank_threshold: int = 20
    entry_extreme_rank_threshold: int = 50
    entry_weak_rank_multiplier: float = 0.7
    entry_weak_regime_multiplier: float = 0.8
    entry_weak_rank_and_regime_multiplier: float = 0.5
    entry_extreme_damage_multiplier: float = 0.1
    ownership_profit_cushion_min: float = 0.08
    ownership_top_rank_memory_threshold: int = 10
    ownership_rank_break_threshold: int = 20
    ownership_damage_rank_threshold: int = 50
    partial_exit_fraction_weak: float = 0.5
    partial_exit_fraction_damage: float = 1.0


def default_soft_ownership_configs() -> dict[str, MidTrendSoftOwnershipConfig]:
    return {
        "baseline": MidTrendSoftOwnershipConfig(variant_name="baseline"),
        "entry_soft_weight_v1": MidTrendSoftOwnershipConfig(variant_name="entry_soft_weight_v1"),
        "ownership_hold_v1": MidTrendSoftOwnershipConfig(variant_name="ownership_hold_v1"),
        "partial_exit_v1": MidTrendSoftOwnershipConfig(variant_name="partial_exit_v1"),
        "combined_soft_ownership_v1": MidTrendSoftOwnershipConfig(
            variant_name="combined_soft_ownership_v1"
        ),
    }
