from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import fsum, isclose, isfinite
from numbers import Real

EXPECTED_REPAIR = "expected_repair"
EARLY_VALIDATION = "early_validation"
REPAIR_BUCKETS = (EXPECTED_REPAIR, EARLY_VALIDATION)

LEGACY_OUTPUT_FILENAMES = {
    "evidence": "consumer_oversold_repair_evidence.csv",
    "expected": "consumer_oversold_expected_repair_top20.csv",
    "early": "consumer_oversold_early_validation_top20.csv",
    "scores": "consumer_oversold_full_scores.csv",
    "exclusions": "consumer_oversold_exclusions.csv",
    "coverage": "consumer_oversold_data_coverage_audit.json",
    "report": "consumer_oversold_weekly_report.md",
}

OUTPUT_FILENAMES = LEGACY_OUTPUT_FILENAMES

UNIFIED_OUTPUT_FILENAMES = {
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

V2_OUTPUT_FILENAMES = {
    **UNIFIED_OUTPUT_FILENAMES,
    "top30": "consumer_oversold_v2_top30.csv",
    "ranked_pool": "consumer_oversold_v2_ranked_pool.csv",
    "comparison": "consumer_oversold_v1_v2_comparison.csv",
}

def validate_trade_date(value: str) -> str:
    try:
        normalized = date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("trade_date must use YYYY-MM-DD") from exc
    if normalized != value:
        raise ValueError("trade_date must use YYYY-MM-DD")
    return normalized


@dataclass(frozen=True)
class ConsumerOversoldConfig:
    trade_date: str
    lookback_6m_bars: int = 126
    lookback_12m_bars: int = 252
    valuation_lookback_years: int = 5
    min_listed_days: int = 365
    min_avg_turnover_amount: float = 30_000_000.0
    min_6m_return: float = -0.20
    min_12m_drawdown: float = -0.30
    min_relative_return: float = -0.10
    min_oversold_score: float = 60.0
    min_base_upside: float = 0.25
    max_per_bucket: int = 20
    max_priced_in_penalty: float = 20.0
    repair_rank_weight: float = 0.70
    elasticity_rank_weight: float = 0.30
    residual_deviation_weight: float = 0.35
    stock_character_weight: float = 0.25
    market_capacity_weight: float = 0.20
    catalyst_liquidity_weight: float = 0.20
    preaudit_size: int = 60
    minimum_evidence_complete: int = 40
    final_top_n: int = 20
    reserve_top_n: int = 20
    ranking_version: str = "v1"
    v2_min_composite_score: float = 30.0
    v2_min_technical_readiness_score: float = 35.0
    v2_repair_rank_weight: float = 0.55
    v2_activation_rank_weight: float = 0.45
    technical_readiness_weight: float = 0.30
    continuation_character_weight: float = 0.25
    residual_price_space_weight: float = 0.20
    capital_efficiency_weight: float = 0.15
    catalyst_timing_weight: float = 0.10

    def __post_init__(self) -> None:
        validate_trade_date(self.trade_date)
        if self.ranking_version not in ("v1", "v2"):
            raise ValueError("ranking_version must be v1 or v2")

        positive_integer_fields = (
            "lookback_6m_bars",
            "lookback_12m_bars",
            "valuation_lookback_years",
        )
        for field_name in positive_integer_fields:
            _validate_integer(field_name, getattr(self, field_name), minimum=1)
        _validate_integer("min_listed_days", self.min_listed_days, minimum=0)
        _validate_integer("max_per_bucket", self.max_per_bucket, minimum=1, maximum=20)
        _validate_integer("preaudit_size", self.preaudit_size, minimum=1)
        _validate_integer(
            "minimum_evidence_complete",
            self.minimum_evidence_complete,
            minimum=1,
        )
        _validate_integer("final_top_n", self.final_top_n, minimum=1, maximum=100)
        _validate_integer("reserve_top_n", self.reserve_top_n, minimum=1, maximum=100)

        _validate_number(
            "min_avg_turnover_amount",
            self.min_avg_turnover_amount,
            minimum=0.0,
        )
        for field_name in ("min_6m_return", "min_12m_drawdown", "min_relative_return"):
            _validate_number(field_name, getattr(self, field_name))
        _validate_number("min_oversold_score", self.min_oversold_score, minimum=0.0, maximum=100.0)
        _validate_number("min_base_upside", self.min_base_upside)
        _validate_number(
            "max_priced_in_penalty",
            self.max_priced_in_penalty,
            minimum=0.0,
            maximum=100.0,
        )
        _validate_number(
            "v2_min_composite_score",
            self.v2_min_composite_score,
            minimum=0.0,
            maximum=100.0,
        )
        _validate_number(
            "v2_min_technical_readiness_score",
            self.v2_min_technical_readiness_score,
            minimum=0.0,
            maximum=100.0,
        )

        rank_weight_fields = (
            "repair_rank_weight",
            "elasticity_rank_weight",
            "residual_deviation_weight",
            "stock_character_weight",
            "market_capacity_weight",
            "catalyst_liquidity_weight",
            "v2_repair_rank_weight",
            "v2_activation_rank_weight",
            "technical_readiness_weight",
            "continuation_character_weight",
            "residual_price_space_weight",
            "capital_efficiency_weight",
            "catalyst_timing_weight",
        )
        for field_name in rank_weight_fields:
            _validate_number(field_name, getattr(self, field_name), minimum=0.0, maximum=1.0)

        _validate_weight_sum(
            "repair and elasticity rank weights",
            (self.repair_rank_weight, self.elasticity_rank_weight),
        )
        _validate_weight_sum(
            "elasticity component weights",
            (
                self.residual_deviation_weight,
                self.stock_character_weight,
                self.market_capacity_weight,
                self.catalyst_liquidity_weight,
            ),
        )
        _validate_exact_weight_sum(
            "v2 repair and activation rank weights",
            (self.v2_repair_rank_weight, self.v2_activation_rank_weight),
        )
        _validate_exact_weight_sum(
            "v2 activation component weights",
            (
                self.technical_readiness_weight,
                self.continuation_character_weight,
                self.residual_price_space_weight,
                self.capital_efficiency_weight,
                self.catalyst_timing_weight,
            ),
        )

        published_size = self.final_top_n + self.reserve_top_n
        if self.preaudit_size < published_size:
            raise ValueError("preaudit_size must cover final_top_n plus reserve_top_n")
        if self.minimum_evidence_complete < published_size:
            raise ValueError(
                "minimum_evidence_complete must cover final_top_n plus reserve_top_n"
            )
        if self.minimum_evidence_complete > self.preaudit_size:
            raise ValueError(
                "minimum_evidence_complete must not exceed preaudit_size"
            )


def _validate_integer(
    field_name: str,
    value: object,
    *,
    minimum: int,
    maximum: int | None = None,
) -> None:
    if type(value) is not int:
        raise ValueError(f"{field_name} must be an integer")
    if value < minimum or maximum is not None and value > maximum:
        bounds = f"at least {minimum}" if maximum is None else f"between {minimum} and {maximum}"
        raise ValueError(f"{field_name} must be {bounds}")


def _validate_number(
    field_name: str,
    value: object,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")


def _validate_weight_sum(group_name: str, values: tuple[float, ...]) -> None:
    if not isclose(fsum(values), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{group_name} must sum to 1.0")


def _validate_exact_weight_sum(group_name: str, values: tuple[float, ...]) -> None:
    if fsum(values) != 1.0:
        raise ValueError(f"{group_name} must sum to 1.0")
