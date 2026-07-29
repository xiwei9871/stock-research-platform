from __future__ import annotations

from dataclasses import dataclass
from datetime import date

EXPECTED_REPAIR = "expected_repair"
EARLY_VALIDATION = "early_validation"
REPAIR_BUCKETS = (EXPECTED_REPAIR, EARLY_VALIDATION)

OUTPUT_FILENAMES = {
    "expected": "consumer_oversold_expected_repair_top20.csv",
    "early": "consumer_oversold_early_validation_top20.csv",
    "scores": "consumer_oversold_full_scores.csv",
    "exclusions": "consumer_oversold_exclusions.csv",
    "coverage": "consumer_oversold_data_coverage_audit.json",
    "report": "consumer_oversold_weekly_report.md",
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

    def __post_init__(self) -> None:
        validate_trade_date(self.trade_date)
        if type(self.max_per_bucket) is not int:
            raise ValueError("max_per_bucket must be an integer")
        if not 1 <= self.max_per_bucket <= 20:
            raise ValueError("max_per_bucket must be between 1 and 20")
