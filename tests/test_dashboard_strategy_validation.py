from stock_research.dashboard.strategy_validation import (
    StrategyEvidenceArtifact,
    StrategyMetricRow,
    StrategyPositionSnapshot,
    StrategySignal,
    StrategyTrade,
    StrategyValidationRun,
    build_strategy_validation_fixture_store,
    build_strategy_validation_replay,
    build_strategy_validation_store_from_frames,
    list_strategy_validation_artifacts,
    list_strategy_validation_metrics,
    list_strategy_validation_positions,
    list_strategy_validation_runs,
    list_strategy_validation_signals,
    list_strategy_validation_trades,
    load_strategy_validation_run,
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


def test_fixture_store_lists_runs_and_filters_by_strategy():
    store = build_strategy_validation_fixture_store()

    all_runs = list_strategy_validation_runs(store=store)
    lhb_runs = list_strategy_validation_runs(strategy_id="lhb_shortline", store=store)

    assert [row["strategy_id"] for row in all_runs] == [
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    ]
    assert len(lhb_runs) == 1
    assert lhb_runs[0]["run_id"] == "lhb_shortline:fixture:phase16"


def test_fixture_store_loads_run_and_related_rows():
    store = build_strategy_validation_fixture_store()
    run_id = "lhb_shortline:fixture:phase16"

    run = load_strategy_validation_run(run_id, store=store)
    signals = list_strategy_validation_signals(run_id, asset_id="000001.SZ", store=store)
    trades = list_strategy_validation_trades(run_id, asset_id="000001.SZ", store=store)
    positions = list_strategy_validation_positions(run_id, asset_id="000001.SZ", store=store)
    metrics = list_strategy_validation_metrics(run_id, metric_level="signal_bucket", store=store)
    artifacts = list_strategy_validation_artifacts(run_id, store=store)

    assert run is not None
    assert run["strategy_name"] == "LHB Shortline"
    assert signals[0]["signal_type"] == "support"
    assert trades[0]["entry_reason"] == "phase16_follow_candidate"
    assert positions[0]["suppression_reason"] == ""
    assert metrics[0]["group_key"] == "support"
    assert artifacts[0]["format"] == "md"


def test_fixture_store_returns_empty_rows_for_missing_run():
    store = build_strategy_validation_fixture_store()

    assert load_strategy_validation_run("missing", store=store) is None
    assert list_strategy_validation_signals("missing", store=store) == []
    assert list_strategy_validation_trades("missing", store=store) == []
    assert list_strategy_validation_positions("missing", store=store) == []
    assert list_strategy_validation_metrics("missing", store=store) == []
    assert list_strategy_validation_artifacts("missing", store=store) == []


def test_strategy_validation_replay_combines_asset_rows():
    store = build_strategy_validation_fixture_store()

    replay = build_strategy_validation_replay(
        run_id="lhb_shortline:fixture:phase16",
        asset_id="000001.SZ",
        bars=[
            {
                "time": "2026-06-03",
                "open": 10.0,
                "high": 10.8,
                "low": 9.8,
                "close": 10.5,
                "volume": 100000.0,
                "amount": 1000000.0,
            }
        ],
        store=store,
    )

    assert replay["run"]["run_id"] == "lhb_shortline:fixture:phase16"
    assert replay["asset_id"] == "000001.SZ"
    assert replay["bars"][0]["time"] == "2026-06-03"
    assert replay["signals"][0]["signal_type"] == "support"
    assert replay["trades"][0]["outcome_status"] == "complete"
    assert replay["artifacts"][0]["title"] == "LHB Fixture Report"


def test_strategy_validation_store_from_frames_maps_representative_artifacts():
    import pandas as pd

    store = build_strategy_validation_store_from_frames(
        run={
            "run_id": "lhb_shortline:artifact:phase16",
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline",
            "strategy_version": "phase16",
            "run_type": "replay",
            "start_date": "2026-06-01",
            "end_date": "2026-06-08",
            "created_at": "2026-06-08T20:30:00+08:00",
            "benchmark": "000300.SH",
            "universe": "a_share",
        },
        signals=pd.DataFrame(
            [
                {
                    "asset_id": "000001.SZ",
                    "stock_code": "000001",
                    "stock_name": "平安银行",
                    "signal_time": "2026-06-03",
                    "trade_date": "2026-06-03",
                    "signal_type": "support",
                    "signal_strength": 0.86,
                    "signal_bucket": "support",
                    "risk_bucket": "normal",
                    "rule_id": "lhb_phase16_follow",
                    "reason": "support confirmed",
                    "tags": "lhb,support",
                    "source_artifact_path": "outputs/research/lhb_signal.csv",
                }
            ]
        ),
        trades=pd.DataFrame(
            [
                {
                    "asset_id": "000001.SZ",
                    "entry_time": "2026-06-04",
                    "entry_price": 10.5,
                    "entry_reason": "phase16_follow_candidate",
                    "exit_time": "2026-06-06",
                    "exit_price": 11.0,
                    "exit_reason": "phase16_exit_confirmed",
                    "holding_days": 2,
                    "return_pct": 0.0476,
                    "max_high_return_pct": 0.08,
                    "max_drawdown_pct": -0.02,
                    "outcome_status": "complete",
                    "source_artifact_path": "outputs/research/lhb_trades.csv",
                }
            ]
        ),
        metrics=pd.DataFrame(
            [
                {
                    "metric_level": "signal_bucket",
                    "group_key": "support",
                    "sample_count": 1,
                    "complete_count": 1,
                    "win_rate": 1.0,
                    "forward_return_mean": 0.0476,
                    "forward_return_median": 0.0476,
                    "max_high_return_mean": 0.08,
                    "max_drawdown_mean": -0.02,
                    "max_drawdown_worst": -0.02,
                    "turnover": 0.1,
                    "exposure_mean": 0.08,
                    "source_artifact_path": "outputs/research/lhb_metrics.csv",
                }
            ]
        ),
        artifacts=[
            {
                "artifact_type": "markdown",
                "title": "LHB Artifact Report",
                "path": "outputs/research/lhb_report.md",
                "format": "md",
                "trade_date": "2026-06-08",
                "description": "representative artifact report",
            }
        ],
    )

    assert store["runs"][0]["run_id"] == "lhb_shortline:artifact:phase16"
    assert store["signals"][0]["tags"] == ["lhb", "support"]
    assert store["trades"][0]["entry_reason"] == "phase16_follow_candidate"
    assert store["metrics"][0]["group_key"] == "support"
    assert store["artifacts"][0]["title"] == "LHB Artifact Report"
