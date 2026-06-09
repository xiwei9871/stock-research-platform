from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyValidationRun:
    run_id: str
    strategy_id: str
    strategy_name: str
    strategy_version: str
    run_type: str
    start_date: str
    end_date: str
    created_at: str
    benchmark: str
    universe: str
    data_window: dict[str, Any]
    cost_config: dict[str, Any]
    slippage_config: dict[str, Any]
    risk_config: dict[str, Any]
    position_config: dict[str, Any]
    source_artifact_paths: list[str]
    summary_metrics: dict[str, Any]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategySignal:
    run_id: str
    strategy_id: str
    asset_id: str
    stock_code: str
    stock_name: str
    signal_time: str
    trade_date: str
    signal_type: str
    signal_strength: float | None
    signal_bucket: str
    risk_bucket: str
    rule_id: str
    reason: str
    tags: list[str]
    source_artifact_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyTrade:
    run_id: str
    strategy_id: str
    asset_id: str
    entry_time: str | None
    entry_price: float | None
    entry_reason: str
    exit_time: str | None
    exit_price: float | None
    exit_reason: str
    holding_days: int | None
    return_pct: float | None
    max_high_return_pct: float | None
    max_drawdown_pct: float | None
    outcome_status: str
    source_artifact_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyPositionSnapshot:
    run_id: str
    strategy_id: str
    trade_date: str
    asset_id: str
    position_weight: float | None
    target_weight: float | None
    cash_weight: float | None
    exposure: float | None
    position_cap: float | None
    risk_budget: float | None
    suppression_reason: str
    source_artifact_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyMetricRow:
    run_id: str
    strategy_id: str
    metric_level: str
    group_key: str
    sample_count: int
    complete_count: int
    win_rate: float | None
    forward_return_mean: float | None
    forward_return_median: float | None
    max_high_return_mean: float | None
    max_drawdown_mean: float | None
    max_drawdown_worst: float | None
    turnover: float | None
    exposure_mean: float | None
    source_artifact_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyEvidenceArtifact:
    run_id: str
    artifact_type: str
    title: str
    path: str
    format: str
    trade_date: str | None
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
