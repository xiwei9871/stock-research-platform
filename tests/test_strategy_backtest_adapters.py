import pandas as pd
import pytest

from stock_research.dashboard import strategy_backtest_adapters as adapters
from stock_research.dashboard.strategy_backtest_adapters import (
    ArtifactReplayAdapter,
    ArtifactReplayConfig,
    LHBShortlineAdapter,
    MidTrendAdapter,
    PositionControlAdapter,
    STRATEGY_BACKTEST_REGISTRY,
    StrategyBacktestParams,
    TechBottleneckAdapter,
    build_lhb_shortline_scores_from_frames,
    build_lhb_phase16c_account_replay_frames,
    build_manual_v1_scores_from_frame,
    build_mid_trend_scores_from_frames,
    build_position_control_scores_from_frames,
    build_tech_bottleneck_scores_from_frames,
    normalize_strategy_scores,
)


def test_registry_contains_all_backtest_lab_strategies():
    assert set(STRATEGY_BACKTEST_REGISTRY) == {
        "manual_v1_topn_rotation",
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    }


def test_research_strategies_use_validated_combo_replay_adapters():
    expected = {
        "lhb_shortline": "lhb_shortline_combo_v1",
        "mid_trend": "mid_trend_combo_v1",
        "tech_bottleneck": "tech_bottleneck_combo_v1",
    }

    for strategy_id, combo_scheme in expected.items():
        adapter = STRATEGY_BACKTEST_REGISTRY[strategy_id]
        assert getattr(adapter, "combo_scheme") == combo_scheme
        assert callable(getattr(adapter, "run_replay"))


def test_artifact_replay_adapter_filters_variant_and_normalizes_payload(tmp_path):
    summary_path = tmp_path / "summary.csv"
    equity_path = tmp_path / "equity.csv"
    positions_path = tmp_path / "positions.csv"
    trades_path = tmp_path / "trades.csv"
    pd.DataFrame(
        [
            {
                "variant_name": "baseline",
                "final_equity": 1.20,
                "total_return": 0.20,
                "max_drawdown": -0.08,
                "trade_rows": 3,
            },
            {
                "variant_name": "combo",
                "final_equity": 2.50,
                "total_return": 1.50,
                "max_drawdown": -0.03,
                "trade_rows": 2,
            },
        ]
    ).to_csv(summary_path, index=False)
    pd.DataFrame(
        [
            {"variant_name": "combo", "date": "2026-01-02", "equity": 1.10, "drawdown": 0.0},
            {"variant_name": "combo", "date": "2026-06-08", "equity": 2.50, "drawdown": -0.01},
            {"variant_name": "baseline", "date": "2026-06-08", "equity": 1.20, "drawdown": -0.08},
        ]
    ).to_csv(equity_path, index=False)
    pd.DataFrame(
        [
            {"variant_name": "combo", "rebalance_date": "2026-06-08", "asset_id": "CN:SZ:000001", "weight": 0.5},
            {"variant_name": "baseline", "rebalance_date": "2026-06-08", "asset_id": "CN:SZ:000002", "weight": 0.5},
        ]
    ).to_csv(positions_path, index=False)
    pd.DataFrame(
        [
            {"variant_name": "combo", "trade_date": "2026-06-08", "asset_id": "CN:SZ:000001", "side": "buy"},
            {"variant_name": "baseline", "trade_date": "2026-06-08", "asset_id": "CN:SZ:000002", "side": "buy"},
        ]
    ).to_csv(trades_path, index=False)

    adapter = ArtifactReplayAdapter(
        ArtifactReplayConfig(
            strategy_id="unit_combo",
            strategy_name="Unit Combo",
            combo_scheme="unit_combo_v1",
            evidence_source="unit fixture",
            summary_path=summary_path,
            summary_filters={"variant_name": "combo"},
            equity_path=equity_path,
            equity_filters={"variant_name": "combo"},
            positions_path=positions_path,
            positions_filters={"variant_name": "combo"},
            trades_path=trades_path,
            trades_filters={"variant_name": "combo"},
        )
    )

    payload = adapter.run_replay(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08"),
        {"top_n": 20, "rebalance_frequency": "weekly"},
    )

    assert payload["strategy_id"] == "unit_combo"
    assert payload["strategy_name"] == "Unit Combo"
    assert payload["read_only"] is True
    assert payload["summary"]["combo_scheme"] == "unit_combo_v1"
    assert payload["summary"]["evidence_source"] == "unit fixture"
    assert payload["summary"]["start_date"] == "2026-01-01"
    assert payload["summary"]["end_date"] == "2026-06-08"
    assert payload["summary"]["actual_start_date"] == "2026-01-02"
    assert payload["summary"]["actual_end_date"] == "2026-06-08"
    assert payload["summary"]["final_equity"] == pytest.approx(2.50 / 1.10)
    assert [row["equity"] for row in payload["equity_curve"]] == pytest.approx([1.0, 2.50 / 1.10])
    assert payload["positions"] == [
        {"rebalance_date": "2026-06-08", "asset_id": "CN:SZ:000001", "weight": 0.5}
    ]
    assert payload["trades"] == [
        {"trade_date": "2026-06-08", "asset_id": "CN:SZ:000001", "side": "buy"}
    ]


def test_artifact_replay_adapter_prefers_database_payload(monkeypatch, tmp_path):
    from stock_research.dashboard import strategy_backtest_adapters

    db_payload = {
        "strategy_id": "unit_combo",
        "strategy_name": "Unit Combo",
        "read_only": True,
        "config": {"start_date": "2026-01-01", "end_date": "2026-06-08"},
        "summary": {"combo_scheme": "unit_combo_v1", "final_equity": 9.0},
        "equity_curve": [],
        "positions": [],
        "trades": [],
    }
    monkeypatch.setattr(
        strategy_backtest_adapters,
        "load_strategy_backtest_replay_payload",
        lambda strategy_id, **kwargs: db_payload,
    )
    monkeypatch.setattr(
        strategy_backtest_adapters,
        "_read_artifact_frame",
        lambda path: (_ for _ in ()).throw(AssertionError("database hit should not read artifact")),
    )

    adapter = ArtifactReplayAdapter(
        ArtifactReplayConfig(
            strategy_id="unit_combo",
            strategy_name="Unit Combo",
            combo_scheme="unit_combo_v1",
            evidence_source="unit fixture",
            summary_path=tmp_path / "missing.csv",
            summary_filters={},
        )
    )

    payload = adapter.run_replay(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08"),
        {"top_n": 20},
    )

    assert payload is db_payload


def test_artifact_replay_adapter_imports_artifact_payload_when_database_is_empty(monkeypatch, tmp_path):
    from stock_research.dashboard import strategy_backtest_adapters

    summary_path = tmp_path / "summary.csv"
    pd.DataFrame([{"variant_name": "combo", "final_equity": 2.0}]).to_csv(summary_path, index=False)
    imports = []
    monkeypatch.setattr(
        strategy_backtest_adapters,
        "load_strategy_backtest_replay_payload",
        lambda strategy_id, **kwargs: None,
    )
    monkeypatch.setattr(
        strategy_backtest_adapters,
        "import_strategy_backtest_replay_payload",
        lambda payload: imports.append(payload) or {"run_id": "unit"},
    )

    adapter = ArtifactReplayAdapter(
        ArtifactReplayConfig(
            strategy_id="unit_combo",
            strategy_name="Unit Combo",
            combo_scheme="unit_combo_v1",
            evidence_source="unit fixture",
            summary_path=summary_path,
            summary_filters={"variant_name": "combo"},
        )
    )

    payload = adapter.run_replay(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08"),
        {"top_n": 20},
    )

    assert imports[0]["strategy_id"] == "unit_combo"
    assert imports[0]["summary"]["combo_scheme"] == "unit_combo_v1"
    assert payload["summary"]["final_equity"] == 2.0


def test_artifact_replay_adapter_rebases_summary_to_requested_window(monkeypatch, tmp_path):
    from stock_research.dashboard import strategy_backtest_adapters

    summary_path = tmp_path / "summary.csv"
    equity_path = tmp_path / "equity.csv"
    pd.DataFrame(
        [
            {
                "variant_name": "combo",
                "start_date": "2025-01-01",
                "end_date": "2026-06-02",
                "actual_start_date": "2025-01-02",
                "actual_end_date": "2026-06-02",
                "periods": 340,
                "final_equity": 4.2,
                "total_return": 3.2,
                "max_drawdown": -0.30,
            }
        ]
    ).to_csv(summary_path, index=False)
    pd.DataFrame(
        [
            {"variant_name": "combo", "date": "2025-12-31", "equity": 1.8},
            {"variant_name": "combo", "date": "2026-01-05", "equity": 2.0},
            {"variant_name": "combo", "date": "2026-01-06", "equity": 3.0},
            {"variant_name": "combo", "date": "2026-01-07", "equity": 2.4},
        ]
    ).to_csv(equity_path, index=False)
    monkeypatch.setattr(strategy_backtest_adapters, "load_strategy_backtest_replay_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(strategy_backtest_adapters, "import_strategy_backtest_replay_payload", lambda payload: {})

    adapter = ArtifactReplayAdapter(
        ArtifactReplayConfig(
            strategy_id="unit_combo",
            strategy_name="Unit Combo",
            combo_scheme="unit_combo_v1",
            evidence_source="unit fixture",
            summary_path=summary_path,
            summary_filters={"variant_name": "combo"},
            equity_path=equity_path,
            equity_filters={"variant_name": "combo"},
        )
    )

    payload = adapter.run_replay(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08"),
        {"top_n": 20},
    )

    assert payload["summary"]["start_date"] == "2026-01-01"
    assert payload["summary"]["end_date"] == "2026-06-08"
    assert payload["summary"]["actual_start_date"] == "2026-01-05"
    assert payload["summary"]["actual_end_date"] == "2026-01-07"
    assert payload["summary"]["periods"] == 3
    assert payload["summary"]["final_equity"] == pytest.approx(1.2)
    assert payload["summary"]["total_return"] == pytest.approx(0.2)
    assert payload["summary"]["max_drawdown"] == pytest.approx(-0.2)
    assert [row["equity"] for row in payload["equity_curve"]] == pytest.approx([1.0, 1.5, 1.2])


def test_tech_bottleneck_combo_uses_complete_weekly_control_artifacts():
    adapter = STRATEGY_BACKTEST_REGISTRY["tech_bottleneck"]

    config = adapter.config

    assert "tech_hard_filter/mid_trend_shadow_weekly_control_equity.csv" in str(config.equity_path)
    assert "tech_hard_filter/mid_trend_shadow_weekly_control_positions.csv" in str(config.positions_path)
    assert "tech_hard_filter/mid_trend_shadow_weekly_control_trades.csv" in str(config.trades_path)
    assert config.equity_filters == {"variant_name": "top5_adaptive_daily_check_max2_v1"}
    assert config.trades_filters == {"variant_name": "top5_adaptive_daily_check_max2_v1"}


def test_lhb_phase16c_account_replay_rebuilds_curve_and_trades_from_source_frames():
    lifecycle = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "ts_code": "300001.SZ",
                "top_n": 1,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-01-05",
                "entry_price": 10.0,
                "exit_trade_date": "2026-01-06",
                "exit_price": 10.5,
                "exit_signal": "limit_break_failed",
                "realized_return": 0.05,
            },
            {
                "trade_date": "2026-01-02",
                "ts_code": "300002.SZ",
                "top_n": 2,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-01-05",
                "entry_price": 20.0,
                "exit_trade_date": "2026-01-07",
                "exit_price": 19.0,
                "exit_signal": "normal_exit",
                "realized_return": -0.05,
            },
        ]
    )
    real_entry = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "ts_code": "300001.SZ", "top_n": 1, "exit_5d_return": 0.20},
            {"trade_date": "2026-01-02", "ts_code": "300002.SZ", "top_n": 2, "exit_5d_return": 0.30},
        ]
    )

    account_trades, account_curve = build_lhb_phase16c_account_replay_frames(
        lifecycle_trades=lifecycle,
        real_entry_trades=real_entry,
        replacement_return_column="exit_5d_return",
        adjust_reason="limit_break_failed_delay_to_5d",
    )

    filled = account_trades[account_trades["account_trade_status"].eq("filled")]
    assert list(filled["realized_return"]) == [0.20, -0.05]
    assert list(account_curve["trade_date"]) == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert account_curve.iloc[-1]["equity"] == pytest.approx(1.015)


def test_normalize_strategy_scores_ranks_high_scores_first():
    raw = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 90.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "score_total": 70.0},
        ]
    )

    scores = normalize_strategy_scores(raw, strategy_id="unit_strategy")

    assert list(scores["trade_date"]) == ["2026-01-01", "2026-01-01", "2026-01-02"]
    assert list(scores["asset_id"]) == ["A", "B", "A"]
    assert list(scores["rank"]) == [1, 2, 1]
    assert list(scores["strategy_id"].unique()) == ["unit_strategy"]


def test_normalize_strategy_scores_rejects_empty_signal_set():
    with pytest.raises(ValueError, match="no unit_strategy strategy scores found"):
        normalize_strategy_scores(pd.DataFrame(), strategy_id="unit_strategy")


def test_normalize_strategy_scores_drops_missing_values_before_formatting_dates():
    raw = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2026-01-01"),
                "asset_id": "A",
                "score_total": 90.0,
            },
            {"trade_date": None, "asset_id": "B", "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": None, "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "score_total": float("nan")},
        ]
    )

    scores = normalize_strategy_scores(raw, strategy_id="unit_strategy")

    assert len(scores) == 1
    assert scores.loc[0, "trade_date"] == "2026-01-01"
    assert scores.loc[0, "asset_id"] == "A"


def test_normalize_strategy_scores_canonicalizes_tushare_asset_ids():
    raw = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "002713.SZ", "score_total": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "688766.SH", "score_total": 80.0},
        ]
    )

    scores = normalize_strategy_scores(raw, strategy_id="unit_strategy")

    assert list(scores["asset_id"]) == ["CN:SZ:002713", "CN:SH:688766"]


def test_strategy_backtest_params_defaults():
    params = StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08")

    assert params.score_version == "manual_v1"
    assert params.adjust_type == "hfq"


def test_manual_v1_builder_preserves_manual_score_order():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 1, "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "rank": 2, "score_total": 90.0},
        ]
    )

    scores = build_manual_v1_scores_from_frame(manual)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert list(scores["rank"]) == [1, 2]


def test_manual_v1_builder_deduplicates_date_asset_rows_before_ranking():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 2, "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "rank": 3, "score_total": 70.0},
        ]
    )

    scores = build_manual_v1_scores_from_frame(manual)

    assert len(scores[(scores["trade_date"] == "2026-01-01") & (scores["asset_id"] == "A")]) == 1
    assert scores.duplicated(subset=["trade_date", "asset_id"]).sum() == 0
    a_score = scores[(scores["trade_date"] == "2026-01-01") & (scores["asset_id"] == "A")].iloc[0]
    assert a_score["rank"] == 1
    assert a_score["score_total"] == 90.0


def test_manual_v1_builder_rejects_empty_frame_with_value_error():
    with pytest.raises(ValueError, match="no manual_v1_topn_rotation strategy scores found"):
        build_manual_v1_scores_from_frame(pd.DataFrame())


def test_lhb_shortline_builder_ranks_positive_support_above_risky_rows():
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.22,
                "lhb_net_buy_amount": 80_000_000,
                "institution_net_buy": 20_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.10,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "on_lhb": True,
                "lhb_net_buy_ratio": -0.05,
                "lhb_net_buy_amount": -5_000_000,
                "institution_net_buy": -2_000_000,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.90,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 1.5, "high_to_close_drawdown": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "B", "amount_vs_20d": 0.3, "high_to_close_drawdown": 0.16},
        ]
    )

    scores = build_lhb_shortline_scores_from_frames(lhb, technical)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]
    assert scores.iloc[1]["eligibility"] is False
    assert "pump_risk" in scores.iloc[1]["eligibility_reason"]


def test_lhb_shortline_builder_deduplicates_date_asset_rows_before_scoring():
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.10,
                "lhb_net_buy_amount": 20_000_000,
                "institution_net_buy": 5_000_000,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.10,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.30,
                "lhb_net_buy_amount": 60_000_000,
                "institution_net_buy": 15_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.40,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 1.8, "high_to_close_drawdown": 0.08},
        ]
    )

    scores = build_lhb_shortline_scores_from_frames(lhb, technical)

    assert len(scores[(scores["trade_date"] == "2026-01-01") & (scores["asset_id"] == "A")]) == 1


def test_lhb_shortline_adapter_returns_only_eligible_scores(monkeypatch):
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "002713.SZ",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.22,
                "lhb_net_buy_amount": 80_000_000,
                "institution_net_buy": 20_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.10,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "on_lhb": True,
                "lhb_net_buy_ratio": -0.05,
                "lhb_net_buy_amount": -5_000_000,
                "institution_net_buy": -2_000_000,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.90,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "CN:SZ:002713", "amount_vs_20d": 1.5, "high_to_close_drawdown": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "B", "amount_vs_20d": 0.3, "high_to_close_drawdown": 0.16},
        ]
    )

    def fake_fetch_frame(sql, params):
        if "factor.lhb_event_features_daily" in sql:
            return lhb
        return technical

    monkeypatch.setattr(adapters, "_fetch_frame", fake_fetch_frame)

    scores = LHBShortlineAdapter().load_scores(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert list(scores["asset_id"]) == ["CN:SZ:002713"]
    assert scores.iloc[0]["eligibility"] is True


def test_lhb_shortline_adapter_recomputes_dense_ranks_after_filtering(monkeypatch):
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 1.00,
                "lhb_net_buy_amount": 300_000_000,
                "institution_net_buy": 200_000_000,
                "repeat_on_list_count_3d": 5,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.95,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.20,
                "lhb_net_buy_amount": 80_000_000,
                "institution_net_buy": 15_000_000,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.10,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 3.0, "high_to_close_drawdown": 0.00},
            {"trade_date": "2026-01-01", "asset_id": "B", "amount_vs_20d": 1.5, "high_to_close_drawdown": 0.02},
        ]
    )

    def fake_fetch_frame(sql, params):
        if "factor.lhb_event_features_daily" in sql:
            return lhb
        return technical

    monkeypatch.setattr(adapters, "_fetch_frame", fake_fetch_frame)

    scores = LHBShortlineAdapter().load_scores(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert list(scores["asset_id"]) == ["B"]
    assert list(scores["rank"]) == [1]


def test_mid_trend_builder_prefers_stronger_trend_and_penalizes_risk():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 78.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.18,
                "high_to_close_drawdown": 0.02,
                "amount_vs_20d": 1.2,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "ret_20d": -0.03,
                "high_to_close_drawdown": 0.18,
                "amount_vs_20d": 0.5,
            },
        ]
    )
    factors = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "factor_name": "trend_r2_20",
                "factor_value": 0.85,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "factor_name": "trend_r2_20",
                "factor_value": 0.25,
            },
        ]
    )

    scores = build_mid_trend_scores_from_frames(manual, technical, factors)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]


@pytest.mark.parametrize(
    "builder",
    [
        build_mid_trend_scores_from_frames,
        build_tech_bottleneck_scores_from_frames,
        build_position_control_scores_from_frames,
    ],
)
def test_manual_technical_builders_deduplicate_date_asset_rows_before_scoring(builder):
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 2, "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 1, "score_total": 88.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "rank": 3, "score_total": 75.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.04,
                "amount_vs_20d": 1.1,
                "close_position_in_day": 0.60,
                "high_to_close_drawdown": 0.03,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.12,
                "amount_vs_20d": 1.8,
                "close_position_in_day": 0.82,
                "high_to_close_drawdown": 0.08,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "ret_20d": 0.03,
                "amount_vs_20d": 1.0,
                "close_position_in_day": 0.50,
                "high_to_close_drawdown": 0.02,
            },
        ]
    )

    scores = builder(manual, technical)

    assert len(scores[(scores["trade_date"] == "2026-01-01") & (scores["asset_id"] == "A")]) == 1


@pytest.mark.parametrize(
    ("builder", "strategy_id"),
    [
        (build_mid_trend_scores_from_frames, "mid_trend"),
        (build_tech_bottleneck_scores_from_frames, "tech_bottleneck"),
        (build_position_control_scores_from_frames, "position_control"),
    ],
)
def test_manual_technical_builders_reject_empty_manual_data_with_value_error(builder, strategy_id):
    with pytest.raises(ValueError, match=f"no {strategy_id} strategy scores found"):
        builder(pd.DataFrame(), pd.DataFrame())


def test_factor_pivot_uses_max_factor_value_for_duplicate_rows():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 70.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "ret_20d": 0.0, "amount_vs_20d": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "ret_20d": 0.0, "amount_vs_20d": 1.0},
        ]
    )
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "trend_r2_20", "factor_value": 0.90},
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "trend_r2_20", "factor_value": 0.20},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_name": "trend_r2_20", "factor_value": 0.50},
        ]
    )

    scores = build_mid_trend_scores_from_frames(manual, technical, factors)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_components"]["trend_r2_20"] == 0.90


def test_mid_trend_adapter_returns_only_eligible_scores(monkeypatch):
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 70.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "ret_20d": 0.04, "amount_vs_20d": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "ret_20d": -0.04, "amount_vs_20d": 1.0},
        ]
    )
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "trend_r2_20", "factor_value": 0.60},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_name": "trend_r2_20", "factor_value": 0.10},
        ]
    )
    monkeypatch.setattr(adapters, "_load_manual_scores", lambda params: manual)
    monkeypatch.setattr(adapters, "_load_technical_features", lambda params: technical)
    monkeypatch.setattr(adapters, "_load_factor_values", lambda params, factor_names: factors)

    scores = MidTrendAdapter().load_scores(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert list(scores["asset_id"]) == ["A"]
    assert scores.iloc[0]["eligibility"] is True


def test_tech_bottleneck_adapter_returns_only_eligible_scores(monkeypatch):
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 90.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.08,
                "amount_vs_20d": 1.0,
                "close_position_in_day": 0.70,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "ret_20d": 0.08,
                "amount_vs_20d": 0.2,
                "close_position_in_day": 0.70,
            },
        ]
    )
    monkeypatch.setattr(adapters, "_load_manual_scores", lambda params: manual)
    monkeypatch.setattr(adapters, "_load_technical_features", lambda params: technical)

    scores = TechBottleneckAdapter().load_scores(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert list(scores["asset_id"]) == ["A"]
    assert scores.iloc[0]["eligibility"] is True


def test_position_control_adapter_applies_eligibility_filter(monkeypatch):
    raw_scores = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "rank": 1,
                "score_total": 90.0,
                "score_components": {},
                "strategy_id": "position_control",
                "eligibility": True,
                "eligibility_reason": "risk_scaled",
                "exposure_scale": 1.0,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "rank": 2,
                "score_total": 80.0,
                "score_components": {},
                "strategy_id": "position_control",
                "eligibility": False,
                "eligibility_reason": "risk_excluded",
                "exposure_scale": 0.0,
            },
        ]
    )
    monkeypatch.setattr(adapters, "_load_manual_scores", lambda params: pd.DataFrame())
    monkeypatch.setattr(adapters, "_load_technical_features", lambda params: pd.DataFrame())
    monkeypatch.setattr(adapters, "build_position_control_scores_from_frames", lambda manual, technical: raw_scores)

    scores = PositionControlAdapter().load_scores(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert list(scores["asset_id"]) == ["A"]
    assert scores.iloc[0]["eligibility"] is True


def test_tech_bottleneck_builder_prefers_continuation_and_volume_confirmation():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 65.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 86.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.16,
                "amount_vs_20d": 2.4,
                "close_position_in_day": 0.86,
                "high_to_close_drawdown": 0.02,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "ret_20d": 0.01,
                "amount_vs_20d": 0.7,
                "close_position_in_day": 0.45,
                "high_to_close_drawdown": 0.12,
            },
        ]
    )

    scores = build_tech_bottleneck_scores_from_frames(manual, technical)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]


def test_position_control_builder_reranks_risky_base_candidates():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 88.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "high_to_close_drawdown": 0.22,
                "amount_vs_20d": 3.0,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "high_to_close_drawdown": 0.02,
                "amount_vs_20d": 1.0,
            },
        ]
    )

    scores = build_position_control_scores_from_frames(manual, technical)

    assert list(scores["asset_id"]) == ["B", "A"]
    assert scores.iloc[0]["exposure_scale"] == 1.0
    assert scores.iloc[1]["exposure_scale"] < 1.0
