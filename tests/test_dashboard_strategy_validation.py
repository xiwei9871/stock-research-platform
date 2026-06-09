from stock_research.dashboard.strategy_validation import (
    StrategyEvidenceArtifact,
    StrategyMetricRow,
    StrategyPositionSnapshot,
    StrategySignal,
    StrategyTrade,
    StrategyValidationRun,
)


def test_strategy_validation_run_to_dict_preserves_configs():
    row = StrategyValidationRun(
        run_id="lhb_shortline:2026-06-08:phase16",
        strategy_id="lhb_shortline",
        strategy_name="LHB Shortline",
        strategy_version="phase16",
        run_type="replay",
        start_date="2026-01-01",
        end_date="2026-06-08",
        created_at="2026-06-08T20:30:00+08:00",
        benchmark="000300.SH",
        universe="a_share",
        data_window={"bar": "daily", "minute": "5min"},
        cost_config={"commission": 0.0003},
        slippage_config={"type": "fixed_bps", "bps": 5},
        risk_config={"max_position_weight": 0.2},
        position_config={"initial_cash": 1000000},
        source_artifact_paths=["outputs/research/lhb_phase16/report.md"],
        summary_metrics={"sample_count": 12, "win_rate": 0.58},
        warnings=["partial adapter coverage"],
    )

    payload = row.to_dict()

    assert payload["strategy_id"] == "lhb_shortline"
    assert payload["cost_config"] == {"commission": 0.0003}
    assert payload["summary_metrics"]["win_rate"] == 0.58
    assert payload["warnings"] == ["partial adapter coverage"]


def test_strategy_signal_to_dict_preserves_reason_and_tags():
    row = StrategySignal(
        run_id="mid_trend:2026-06-08:stability",
        strategy_id="mid_trend",
        asset_id="000001.SZ",
        stock_code="000001",
        stock_name="平安银行",
        signal_time="2026-06-08",
        trade_date="2026-06-08",
        signal_type="trend_protection",
        signal_strength=0.82,
        signal_bucket="protection_ok",
        risk_bucket="normal",
        rule_id="mid_trend_trend_protection_v1",
        reason="trend protection holds above stop band",
        tags=["trend", "protection"],
        source_artifact_path="outputs/research/mid_trend/report.md",
    )

    payload = row.to_dict()

    assert payload["signal_type"] == "trend_protection"
    assert payload["reason"] == "trend protection holds above stop band"
    assert payload["tags"] == ["trend", "protection"]


def test_strategy_trade_position_metric_and_artifact_to_dict():
    trade = StrategyTrade(
        run_id="tech_bottleneck:2026-06-08:c2",
        strategy_id="tech_bottleneck",
        asset_id="000002.SZ",
        entry_time="2026-06-03",
        entry_price=10.0,
        entry_reason="bottleneck_rank_top10",
        exit_time="2026-06-08",
        exit_price=11.0,
        exit_reason="rank_decay",
        holding_days=3,
        return_pct=0.1,
        max_high_return_pct=0.16,
        max_drawdown_pct=-0.04,
        outcome_status="complete",
        source_artifact_path="outputs/research/bottleneck/trades.csv",
    )
    position = StrategyPositionSnapshot(
        run_id="position_control:2026-06-08:budget",
        strategy_id="position_control",
        trade_date="2026-06-08",
        asset_id="000002.SZ",
        position_weight=0.08,
        target_weight=0.1,
        cash_weight=0.42,
        exposure=0.58,
        position_cap=0.1,
        risk_budget=0.6,
        suppression_reason="regime_budget",
        source_artifact_path="outputs/research/position/curve.csv",
    )
    metric = StrategyMetricRow(
        run_id="tech_bottleneck:2026-06-08:c2",
        strategy_id="tech_bottleneck",
        metric_level="signal_bucket",
        group_key="bottleneck_rank_top10",
        sample_count=20,
        complete_count=18,
        win_rate=0.55,
        forward_return_mean=0.08,
        forward_return_median=0.05,
        max_high_return_mean=0.14,
        max_drawdown_mean=-0.05,
        max_drawdown_worst=-0.18,
        turnover=0.3,
        exposure_mean=0.45,
        source_artifact_path="outputs/research/bottleneck/metrics.csv",
    )
    artifact = StrategyEvidenceArtifact(
        run_id="tech_bottleneck:2026-06-08:c2",
        artifact_type="csv",
        title="Bottleneck Trades",
        path="outputs/research/bottleneck/trades.csv",
        format="csv",
        trade_date="2026-06-08",
        description="normalized fixture trades",
    )

    assert trade.to_dict()["exit_reason"] == "rank_decay"
    assert position.to_dict()["suppression_reason"] == "regime_budget"
    assert metric.to_dict()["group_key"] == "bottleneck_rank_top10"
    assert artifact.to_dict()["path"].endswith("trades.csv")
