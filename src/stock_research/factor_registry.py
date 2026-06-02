from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class FactorMetadata:
    factor_name: str
    factor_group: str
    direction: str
    description: str
    source: str
    calc_version: str = "v1"
    status: str = "validated"
    availability_start_date: str | None = None
    availability_reason: str | None = "available_full_window"


_REGISTRY: dict[str, FactorMetadata] = {
    "ret_5": FactorMetadata("ret_5", "momentum", "higher", "5-day return", "custom"),
    "ret_20": FactorMetadata("ret_20", "momentum", "higher", "20-day return", "custom"),
    "ret_60": FactorMetadata("ret_60", "momentum", "higher", "60-day return", "custom"),
    "momentum_20_5": FactorMetadata(
        "momentum_20_5",
        "momentum",
        "higher",
        "20-day minus 5-day return spread",
        "custom",
    ),
    "close_above_ma20": FactorMetadata(
        "close_above_ma20",
        "trend",
        "higher",
        "Close above 20-day moving average",
        "custom",
    ),
    "close_above_ma60": FactorMetadata(
        "close_above_ma60",
        "trend",
        "higher",
        "Close above 60-day moving average",
        "custom",
    ),
    "ma20_slope": FactorMetadata("ma20_slope", "trend", "higher", "20-day MA slope", "custom"),
    "ma60_slope": FactorMetadata("ma60_slope", "trend", "higher", "60-day MA slope", "custom"),
    "trend_r2_20": FactorMetadata("trend_r2_20", "trend", "higher", "20-day trend fit R2", "custom"),
    "amount_ratio_5_20": FactorMetadata(
        "amount_ratio_5_20",
        "volume_price",
        "higher",
        "5-day to 20-day amount ratio",
        "custom",
    ),
    "amount_vs_20d": FactorMetadata(
        "amount_vs_20d",
        "volume_price",
        "lower",
        "Current amount versus 20-day average amount",
        "custom",
    ),
    "volume_ratio_5_20": FactorMetadata(
        "volume_ratio_5_20",
        "volume_price",
        "higher",
        "5-day to 20-day volume ratio",
        "custom",
    ),
    "turnover_ratio_5_20": FactorMetadata(
        "turnover_ratio_5_20",
        "volume_price",
        "higher",
        "5-day to 20-day turnover ratio",
        "custom",
    ),
    "price_volume_corr_10": FactorMetadata(
        "price_volume_corr_10",
        "volume_price",
        "higher",
        "10-day price-volume correlation",
        "custom",
    ),
    "volatility_5d": FactorMetadata("volatility_5d", "risk", "lower", "5-day volatility", "custom"),
    "volatility_20": FactorMetadata("volatility_20", "risk", "lower", "20-day volatility", "custom"),
    "max_drawdown_20": FactorMetadata(
        "max_drawdown_20",
        "risk",
        "higher",
        "20-day max drawdown",
        "custom",
    ),
    "atr_pct": FactorMetadata("atr_pct", "risk", "lower", "ATR as a percent of close", "custom"),
    "high_to_close_drawdown": FactorMetadata(
        "high_to_close_drawdown",
        "risk",
        "lower",
        "Drawdown from high to close",
        "custom",
    ),
    "distance_ma20": FactorMetadata("distance_ma20", "risk", "lower", "Distance to MA20", "custom"),
    "distance_ma60": FactorMetadata("distance_ma60", "risk", "lower", "Distance to MA60", "custom"),
    "sector_ret_20": FactorMetadata("sector_ret_20", "sector", "higher", "20-day sector return", "custom"),
    "stock_excess_ret_20": FactorMetadata(
        "stock_excess_ret_20",
        "sector",
        "higher",
        "Stock excess return over sector",
        "custom",
    ),
    "sector_up_ratio": FactorMetadata("sector_up_ratio", "sector", "higher", "Sector up ratio", "custom"),
    "roe": FactorMetadata("roe", "quality", "higher", "Return on equity", "fundamental"),
    "roa": FactorMetadata("roa", "quality", "higher", "Return on assets", "fundamental"),
    "gross_margin": FactorMetadata(
        "gross_margin",
        "quality",
        "higher",
        "Gross margin",
        "fundamental",
    ),
    "net_margin": FactorMetadata("net_margin", "quality", "higher", "Net margin", "fundamental"),
    "debt_ratio": FactorMetadata("debt_ratio", "quality", "lower", "Debt ratio", "fundamental"),
    "ocf_to_np": FactorMetadata(
        "ocf_to_np",
        "quality",
        "higher",
        "Operating cash flow to net profit",
        "fundamental",
    ),
    "pe_ttm": FactorMetadata("pe_ttm", "value", "lower", "Trailing twelve month PE", "fundamental"),
    "ps_ttm": FactorMetadata("ps_ttm", "value", "lower", "Trailing twelve month PS", "fundamental"),
    "pb": FactorMetadata("pb", "value", "lower", "Price to book", "fundamental"),
    "alpha101_delta_close_1_rank": FactorMetadata(
        "alpha101_delta_close_1_rank",
        "alpha101",
        "higher",
        "Alpha101 close delta rank proxy",
        "alpha101",
    ),
    "alpha101_corr_open_volume_10": FactorMetadata(
        "alpha101_corr_open_volume_10",
        "alpha101",
        "higher",
        "Alpha101 open-volume correlation proxy",
        "alpha101",
    ),
    "alpha101_decay_delta_close_5": FactorMetadata(
        "alpha101_decay_delta_close_5",
        "alpha101",
        "higher",
        "Alpha101 decay close delta proxy",
        "alpha101",
    ),
    "gtja191_vp_corr_10": FactorMetadata(
        "gtja191_vp_corr_10",
        "gtja191",
        "higher",
        "GTJA191 volume-price correlation proxy",
        "gtja191",
    ),
    "gtja191_amount_momentum_5_10": FactorMetadata(
        "gtja191_amount_momentum_5_10",
        "gtja191",
        "higher",
        "GTJA191 amount momentum proxy",
        "gtja191",
    ),
    "gtja191_intraday_strength_6": FactorMetadata(
        "gtja191_intraday_strength_6",
        "gtja191",
        "higher",
        "GTJA191 intraday strength proxy",
        "gtja191",
    ),
    "qlib_klen": FactorMetadata("qlib_klen", "qlib", "lower", "Qlib candle body length", "qlib"),
    "qlib_kupper": FactorMetadata("qlib_kupper", "qlib", "higher", "Qlib upper shadow", "qlib"),
    "qlib_klower": FactorMetadata("qlib_klower", "qlib", "higher", "Qlib lower shadow", "qlib"),
    "qlib_ret_5": FactorMetadata("qlib_ret_5", "qlib", "higher", "Qlib 5-day return", "qlib"),
}


def list_factor_names() -> list[str]:
    return sorted(_REGISTRY)


def get_factor_metadata(factor_name: str) -> FactorMetadata:
    normalized = str(factor_name)
    if normalized not in _REGISTRY:
        raise KeyError(f"unknown factor metadata: {factor_name}")
    return _REGISTRY[normalized]


def list_factor_metadata(
    factor_names: list[str] | tuple[str, ...] | None = None,
) -> list[FactorMetadata]:
    names = list_factor_names() if factor_names is None else [str(name) for name in factor_names]
    return [get_factor_metadata(name) for name in names]


def factor_groups_map(
    factor_names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, str]:
    return {
        metadata.factor_name: metadata.factor_group
        for metadata in list_factor_metadata(factor_names)
    }


def factor_directions_map(
    factor_names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, str]:
    return {
        metadata.factor_name: metadata.direction
        for metadata in list_factor_metadata(factor_names)
    }


def factor_availability_metadata(
    factor_names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, dict[str, str | None]]:
    return {
        metadata.factor_name: {
            "start_date": metadata.availability_start_date,
            "reason": metadata.availability_reason,
        }
        for metadata in list_factor_metadata(factor_names)
    }


def factor_metadata_frame(
    factor_names: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        [asdict(metadata) for metadata in list_factor_metadata(factor_names)]
    )


def validate_factor_group_mapping(factor_groups: dict[str, str]) -> None:
    mismatches = []
    for factor_name, factor_group in factor_groups.items():
        try:
            metadata = get_factor_metadata(factor_name)
        except KeyError as exc:
            raise ValueError(f"unknown factor metadata: {factor_name}") from exc
        if metadata.factor_group != str(factor_group):
            mismatches.append(
                f"{factor_name}: expected group {metadata.factor_group}, got {factor_group}"
            )
    if mismatches:
        raise ValueError("factor group mismatch: " + "; ".join(mismatches))


def validate_factor_direction_mapping(factor_directions: dict[str, str]) -> None:
    mismatches = []
    for factor_name, direction in factor_directions.items():
        try:
            metadata = get_factor_metadata(factor_name)
        except KeyError as exc:
            raise ValueError(f"unknown factor metadata: {factor_name}") from exc
        if metadata.direction != str(direction):
            mismatches.append(
                f"{factor_name}: expected direction {metadata.direction}, got {direction}"
            )
    if mismatches:
        raise ValueError("factor direction mismatch: " + "; ".join(mismatches))
