from dataclasses import asdict, dataclass
import math
from typing import Any


StrategyValidationStore = dict[str, list[dict[str, Any]]]


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


def build_strategy_validation_fixture_store() -> StrategyValidationStore:
    runs = [
        StrategyValidationRun(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            strategy_name="LHB Shortline",
            strategy_version="phase16",
            run_type="replay",
            start_date="2026-06-01",
            end_date="2026-06-08",
            created_at="2026-06-08T20:30:00+08:00",
            benchmark="000300.SH",
            universe="a_share",
            data_window={"bar": "daily"},
            cost_config={"commission": 0.0003},
            slippage_config={"type": "fixed_bps", "bps": 5},
            risk_config={"max_position_weight": 0.2},
            position_config={"initial_cash": 1000000},
            source_artifact_paths=["outputs/research/lhb_fixture_report.md"],
            summary_metrics={"sample_count": 1, "win_rate": 1.0},
            warnings=[],
        ),
        StrategyValidationRun(
            run_id="mid_trend:fixture:stability",
            strategy_id="mid_trend",
            strategy_name="Mid Trend",
            strategy_version="stability",
            run_type="replay",
            start_date="2026-06-01",
            end_date="2026-06-08",
            created_at="2026-06-08T20:30:00+08:00",
            benchmark="000300.SH",
            universe="a_share",
            data_window={"bar": "daily"},
            cost_config={},
            slippage_config={},
            risk_config={},
            position_config={},
            source_artifact_paths=[],
            summary_metrics={},
            warnings=[],
        ),
        StrategyValidationRun(
            run_id="tech_bottleneck:fixture:c2",
            strategy_id="tech_bottleneck",
            strategy_name="Tech Bottleneck",
            strategy_version="c2",
            run_type="replay",
            start_date="2026-06-01",
            end_date="2026-06-08",
            created_at="2026-06-08T20:30:00+08:00",
            benchmark="000300.SH",
            universe="a_share",
            data_window={"bar": "daily"},
            cost_config={},
            slippage_config={},
            risk_config={},
            position_config={},
            source_artifact_paths=[],
            summary_metrics={},
            warnings=[],
        ),
        StrategyValidationRun(
            run_id="position_control:fixture:budget",
            strategy_id="position_control",
            strategy_name="Position Control",
            strategy_version="budget",
            run_type="replay",
            start_date="2026-06-01",
            end_date="2026-06-08",
            created_at="2026-06-08T20:30:00+08:00",
            benchmark="000300.SH",
            universe="a_share",
            data_window={"bar": "daily"},
            cost_config={},
            slippage_config={},
            risk_config={},
            position_config={},
            source_artifact_paths=[],
            summary_metrics={},
            warnings=[],
        ),
    ]
    signals = [
        StrategySignal(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            asset_id="000001.SZ",
            stock_code="000001",
            stock_name="平安银行",
            signal_time="2026-06-03",
            trade_date="2026-06-03",
            signal_type="support",
            signal_strength=0.86,
            signal_bucket="support",
            risk_bucket="normal",
            rule_id="lhb_phase16_follow",
            reason="support confirmed",
            tags=["lhb", "support"],
            source_artifact_path="outputs/research/lhb_signal.csv",
        )
    ]
    trades = [
        StrategyTrade(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            asset_id="000001.SZ",
            entry_time="2026-06-04",
            entry_price=10.5,
            entry_reason="phase16_follow_candidate",
            exit_time="2026-06-06",
            exit_price=11.0,
            exit_reason="phase16_exit_confirmed",
            holding_days=2,
            return_pct=0.0476,
            max_high_return_pct=0.08,
            max_drawdown_pct=-0.02,
            outcome_status="complete",
            source_artifact_path="outputs/research/lhb_trades.csv",
        )
    ]
    positions = [
        StrategyPositionSnapshot(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            trade_date="2026-06-04",
            asset_id="000001.SZ",
            position_weight=0.08,
            target_weight=0.1,
            cash_weight=0.9,
            exposure=0.1,
            position_cap=0.2,
            risk_budget=0.6,
            suppression_reason="",
            source_artifact_path="outputs/research/lhb_positions.csv",
        )
    ]
    metrics = [
        StrategyMetricRow(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            metric_level="signal_bucket",
            group_key="support",
            sample_count=1,
            complete_count=1,
            win_rate=1.0,
            forward_return_mean=0.0476,
            forward_return_median=0.0476,
            max_high_return_mean=0.08,
            max_drawdown_mean=-0.02,
            max_drawdown_worst=-0.02,
            turnover=0.1,
            exposure_mean=0.08,
            source_artifact_path="outputs/research/lhb_metrics.csv",
        )
    ]
    artifacts = [
        StrategyEvidenceArtifact(
            run_id="lhb_shortline:fixture:phase16",
            artifact_type="markdown",
            title="LHB Fixture Report",
            path="outputs/research/lhb_fixture_report.md",
            format="md",
            trade_date="2026-06-08",
            description="fixture strategy validation report",
        )
    ]
    return {
        "runs": [row.to_dict() for row in runs],
        "signals": [row.to_dict() for row in signals],
        "trades": [row.to_dict() for row in trades],
        "positions": [row.to_dict() for row in positions],
        "metrics": [row.to_dict() for row in metrics],
        "artifacts": [row.to_dict() for row in artifacts],
    }


def _default_store(
    store: StrategyValidationStore | None,
) -> StrategyValidationStore:
    return store if store is not None else build_strategy_validation_fixture_store()


def _filter_rows(
    rows: list[dict[str, Any]], **filters: Any
) -> list[dict[str, Any]]:
    active_filters = {
        key: value for key, value in filters.items() if value is not None
    }
    return [
        dict(row)
        for row in rows
        if all(row.get(key) == value for key, value in active_filters.items())
    ]


def list_strategy_validation_runs(
    strategy_id: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    resolved_store = _default_store(store)
    return _filter_rows(resolved_store.get("runs", []), strategy_id=strategy_id)


def load_strategy_validation_run(
    run_id: str,
    store: StrategyValidationStore | None = None,
) -> dict[str, Any] | None:
    resolved_store = _default_store(store)
    matches = _filter_rows(resolved_store.get("runs", []), run_id=run_id)
    return matches[0] if matches else None


def list_strategy_validation_signals(
    run_id: str,
    asset_id: str | None = None,
    signal_bucket: str | None = None,
    risk_bucket: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    resolved_store = _default_store(store)
    return _filter_rows(
        resolved_store.get("signals", []),
        run_id=run_id,
        asset_id=asset_id,
        signal_bucket=signal_bucket,
        risk_bucket=risk_bucket,
    )


def list_strategy_validation_trades(
    run_id: str,
    asset_id: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    resolved_store = _default_store(store)
    return _filter_rows(
        resolved_store.get("trades", []), run_id=run_id, asset_id=asset_id
    )


def list_strategy_validation_positions(
    run_id: str,
    asset_id: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    resolved_store = _default_store(store)
    return _filter_rows(
        resolved_store.get("positions", []), run_id=run_id, asset_id=asset_id
    )


def list_strategy_validation_metrics(
    run_id: str,
    metric_level: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    resolved_store = _default_store(store)
    return _filter_rows(
        resolved_store.get("metrics", []),
        run_id=run_id,
        metric_level=metric_level,
    )


def list_strategy_validation_artifacts(
    run_id: str,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    resolved_store = _default_store(store)
    return _filter_rows(resolved_store.get("artifacts", []), run_id=run_id)


def build_strategy_validation_replay(
    run_id: str,
    asset_id: str,
    bars: list[dict[str, Any]],
    store: StrategyValidationStore | None = None,
) -> dict[str, Any]:
    resolved_store = _default_store(store)
    return {
        "run": load_strategy_validation_run(run_id, store=resolved_store),
        "asset_id": asset_id,
        "bars": [dict(row) for row in bars],
        "signals": list_strategy_validation_signals(
            run_id, asset_id=asset_id, store=resolved_store
        ),
        "trades": list_strategy_validation_trades(
            run_id, asset_id=asset_id, store=resolved_store
        ),
        "positions": list_strategy_validation_positions(
            run_id, asset_id=asset_id, store=resolved_store
        ),
        "metrics": list_strategy_validation_metrics(run_id, store=resolved_store),
        "artifacts": list_strategy_validation_artifacts(run_id, store=resolved_store),
    }


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return False


def _optional_float(value: Any) -> float | None:
    if _is_missing_value(value):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if _is_missing_value(value):
        return None
    return int(value)


def _string_list(value: Any) -> list[str]:
    if _is_missing_value(value):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value]
    return [str(value)]


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        return value.to_dict("records")
    return list(value)


def build_strategy_validation_store_from_frames(
    run: dict[str, Any],
    signals: Any,
    trades: Any,
    metrics: Any,
    artifacts: Any,
    positions: Any = None,
) -> StrategyValidationStore:
    run_id = str(run["run_id"])
    strategy_id = str(run["strategy_id"])
    run_row = StrategyValidationRun(
        run_id=run_id,
        strategy_id=strategy_id,
        strategy_name=str(run["strategy_name"]),
        strategy_version=str(run["strategy_version"]),
        run_type=str(run["run_type"]),
        start_date=str(run["start_date"]),
        end_date=str(run["end_date"]),
        created_at=str(run["created_at"]),
        benchmark=str(run["benchmark"]),
        universe=str(run["universe"]),
        data_window=dict(run.get("data_window", {})),
        cost_config=dict(run.get("cost_config", {})),
        slippage_config=dict(run.get("slippage_config", {})),
        risk_config=dict(run.get("risk_config", {})),
        position_config=dict(run.get("position_config", {})),
        source_artifact_paths=_string_list(run.get("source_artifact_paths")),
        summary_metrics=dict(run.get("summary_metrics", {})),
        warnings=_string_list(run.get("warnings")),
    )

    signal_rows = [
        StrategySignal(
            run_id=str(row.get("run_id", run_id)),
            strategy_id=str(row.get("strategy_id", strategy_id)),
            asset_id=str(row["asset_id"]),
            stock_code=str(row.get("stock_code", "")),
            stock_name=str(row.get("stock_name", "")),
            signal_time=str(row["signal_time"]),
            trade_date=str(row["trade_date"]),
            signal_type=str(row["signal_type"]),
            signal_strength=_optional_float(row.get("signal_strength")),
            signal_bucket=str(row.get("signal_bucket", "")),
            risk_bucket=str(row.get("risk_bucket", "")),
            rule_id=str(row.get("rule_id", "")),
            reason=str(row.get("reason", "")),
            tags=_string_list(row.get("tags")),
            source_artifact_path=str(row.get("source_artifact_path", "")),
        )
        for row in _records(signals)
    ]
    trade_rows = [
        StrategyTrade(
            run_id=str(row.get("run_id", run_id)),
            strategy_id=str(row.get("strategy_id", strategy_id)),
            asset_id=str(row["asset_id"]),
            entry_time=None
            if _is_missing_value(row.get("entry_time"))
            else str(row.get("entry_time")),
            entry_price=_optional_float(row.get("entry_price")),
            entry_reason=str(row.get("entry_reason", "")),
            exit_time=None
            if _is_missing_value(row.get("exit_time"))
            else str(row.get("exit_time")),
            exit_price=_optional_float(row.get("exit_price")),
            exit_reason=str(row.get("exit_reason", "")),
            holding_days=_optional_int(row.get("holding_days")),
            return_pct=_optional_float(row.get("return_pct")),
            max_high_return_pct=_optional_float(row.get("max_high_return_pct")),
            max_drawdown_pct=_optional_float(row.get("max_drawdown_pct")),
            outcome_status=str(row.get("outcome_status", "")),
            source_artifact_path=str(row.get("source_artifact_path", "")),
        )
        for row in _records(trades)
    ]
    position_rows = [
        StrategyPositionSnapshot(
            run_id=str(row.get("run_id", run_id)),
            strategy_id=str(row.get("strategy_id", strategy_id)),
            trade_date=str(row["trade_date"]),
            asset_id=str(row["asset_id"]),
            position_weight=_optional_float(row.get("position_weight")),
            target_weight=_optional_float(row.get("target_weight")),
            cash_weight=_optional_float(row.get("cash_weight")),
            exposure=_optional_float(row.get("exposure")),
            position_cap=_optional_float(row.get("position_cap")),
            risk_budget=_optional_float(row.get("risk_budget")),
            suppression_reason=str(row.get("suppression_reason", "")),
            source_artifact_path=str(row.get("source_artifact_path", "")),
        )
        for row in _records(positions)
    ]
    metric_rows = [
        StrategyMetricRow(
            run_id=str(row.get("run_id", run_id)),
            strategy_id=str(row.get("strategy_id", strategy_id)),
            metric_level=str(row["metric_level"]),
            group_key=str(row["group_key"]),
            sample_count=_optional_int(row.get("sample_count")) or 0,
            complete_count=_optional_int(row.get("complete_count")) or 0,
            win_rate=_optional_float(row.get("win_rate")),
            forward_return_mean=_optional_float(row.get("forward_return_mean")),
            forward_return_median=_optional_float(row.get("forward_return_median")),
            max_high_return_mean=_optional_float(row.get("max_high_return_mean")),
            max_drawdown_mean=_optional_float(row.get("max_drawdown_mean")),
            max_drawdown_worst=_optional_float(row.get("max_drawdown_worst")),
            turnover=_optional_float(row.get("turnover")),
            exposure_mean=_optional_float(row.get("exposure_mean")),
            source_artifact_path=str(row.get("source_artifact_path", "")),
        )
        for row in _records(metrics)
    ]
    artifact_rows = [
        StrategyEvidenceArtifact(
            run_id=str(row.get("run_id", run_id)),
            artifact_type=str(row["artifact_type"]),
            title=str(row["title"]),
            path=str(row["path"]),
            format=str(row["format"]),
            trade_date=None
            if _is_missing_value(row.get("trade_date"))
            else str(row.get("trade_date")),
            description=str(row.get("description", "")),
        )
        for row in _records(artifacts)
    ]
    return {
        "runs": [run_row.to_dict()],
        "signals": [row.to_dict() for row in signal_rows],
        "trades": [row.to_dict() for row in trade_rows],
        "positions": [row.to_dict() for row in position_rows],
        "metrics": [row.to_dict() for row in metric_rows],
        "artifacts": [row.to_dict() for row in artifact_rows],
    }
