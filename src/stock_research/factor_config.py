from stock_research.factor_registry import (
    factor_availability_metadata as registry_factor_availability_metadata,
    factor_directions_map,
    factor_groups_map,
    list_factor_names,
)


MANUAL_V1_FACTOR_WEIGHTS = {
    "ret_20_score": 0.15,
    "ret_60_score": 0.10,
    "momentum_20_5_score": 0.10,
    "ma20_slope_score": 0.10,
    "ma60_slope_score": 0.05,
    "trend_r2_20_score": 0.05,
    "amount_ratio_5_20_score": 0.08,
    "volume_ratio_5_20_score": 0.05,
    "volatility_20_score": 0.10,
    "max_drawdown_20_score": 0.07,
    "atr_pct_score": 0.05,
    "sector_ret_20_score": 0.05,
    "stock_excess_ret_20_score": 0.05,
}


def manual_v1_config() -> dict:
    return {
        "score_version": "manual_v1",
        "calc_version": "v1",
        "source_data_version": "market_daily_bar:hfq",
        "factor_groups": factor_groups_map(),
        "factor_directions": factor_directions_map(),
        "weights": MANUAL_V1_FACTOR_WEIGHTS.copy(),
    }


def historical_research_start_date() -> str:
    return "2024-01-01"


def default_research_horizons() -> list[int]:
    return [5, 10, 20, 60]


def candidate_factor_names() -> list[str]:
    return list_factor_names()


def factor_availability_metadata() -> dict[str, dict[str, str | None]]:
    return registry_factor_availability_metadata(candidate_factor_names())
