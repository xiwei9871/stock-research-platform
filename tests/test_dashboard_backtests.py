import builtins
import importlib
import math
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import backtests
from stock_research.dashboard import strategy_backtest_adapters as adapters
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    VectorizedTopNResult,
)


def test_backtests_import_does_not_require_strategy_contracts(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "stock_research.strategy_contracts":
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    importlib.reload(backtests)


def test_strategy_metrics_prefer_eod_manifest_strategy_artifacts(monkeypatch, tmp_path):
    artifact = tmp_path / "strategy_mid_trend_review.csv"
    artifact.write_text(
        "\n".join(
            [
                "trade_date,asset_id,rank,strategy_id,strategy_name,stock_name,source_position_date",
                "2026-06-16,CN:SZ:001339,1,mid_trend,Mid Trend Combo,智微智能,2026-05-18",
                "2026-06-16,CN:SZ:000811,2,mid_trend,Mid Trend Combo,冰轮环境,2026-05-18",
                "2026-06-16,CN:SZ:003031,3,mid_trend,Mid Trend Combo,中瓷电子,2026-05-18",
                "2026-06-16,CN:SZ:301086,4,mid_trend,Mid Trend Combo,鸿富瀚,2026-05-18",
                "2026-06-16,CN:SZ:300831,5,mid_trend,Mid Trend Combo,派瑞股份,2026-05-18",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        backtests,
        "load_latest_data_run_manifest",
        lambda: [
            {
                "module": "strategy_mid_trend",
                "status": "success",
                "latest_trade_date": "2026-06-16",
                "row_count": 5,
                "artifact_path": str(artifact),
                "metadata": {
                    "summary": {
                        "actual_end_date": "2026-06-16",
                        "actual_start_date": "2026-01-05",
                        "final_equity": 1.6720554083319354,
                        "total_return": 0.6720554083319354,
                        "max_drawdown": -0.175192059995805,
                        "latest_day_return": 0.0589,
                        "latest_day_drawdown": -0.0086,
                        "latest_period_return": 0.0625,
                        "latest_period_label": "最近调仓周期",
                    },
                    "source_position_date": "2026-05-18",
                },
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(backtests, "load_strategy_contracts", lambda profile="balanced": {})

    strategy = {
        "strategy_id": "mid_trend",
        "strategy_name": "Mid Trend Combo",
        "default_parameters": {"rebalance_frequency": "weekly"},
        "latest_evidence": "old static evidence ending 2026-06-02",
        "latest_metrics": {
            "as_of_date": "2026-06-02",
            "total_return_pct": 55.99,
            "max_drawdown_pct": -17.52,
            "signal_status": "connected",
            "signal_count": 5,
        },
    }

    enriched = backtests._with_latest_eod_strategy_metrics(strategy)

    assert enriched["latest_metrics"]["as_of_date"] == "2026-06-16"
    assert enriched["latest_metrics"]["total_return_pct"] == 67.21
    assert enriched["latest_metrics"]["max_drawdown_pct"] == -17.52
    assert enriched["latest_metrics"]["latest_day_return_pct"] == 5.89
    assert enriched["latest_metrics"]["latest_day_drawdown_pct"] == -0.86
    assert enriched["latest_metrics"]["latest_period_return_pct"] == 6.25
    assert enriched["latest_metrics"]["latest_period_label"] == "最近调仓周期"
    assert enriched["latest_metrics"]["signal_status"] == "current_holdings"
    assert enriched["latest_metrics"]["signal_count"] == 5
    assert "估值截止 2026-06-16" in enriched["latest_evidence"]
    assert "持仓来源日 2026-05-18" in enriched["latest_evidence"]


def test_lhb_eod_manifest_candidate_rows_override_empty_position_status(monkeypatch, tmp_path):
    artifact = tmp_path / "strategy_lhb_shortline_review.csv"
    artifact.write_text(
        "\n".join(
            [
                "trade_date,asset_id,rank,strategy_id,strategy_name,stock_name",
                "2026-06-16,CN:SZ:002080,1,lhb_shortline,LHB Shortline Combo,中材科技",
                "2026-06-16,CN:SZ:002436,2,lhb_shortline,LHB Shortline Combo,兴森科技",
                "2026-06-16,CN:SZ:300620,3,lhb_shortline,LHB Shortline Combo,光库科技",
                "2026-06-16,CN:SZ:300843,4,lhb_shortline,LHB Shortline Combo,胜蓝股份",
                "2026-06-16,CN:SZ:301099,5,lhb_shortline,LHB Shortline Combo,雅创电子",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        backtests,
        "load_latest_data_run_manifest",
        lambda: [
            {
                "module": "strategy_lhb_shortline",
                "status": "success",
                "latest_trade_date": "2026-06-16",
                "row_count": 5,
                "artifact_path": str(artifact),
                "metadata": {},
            }
        ],
        raising=False,
    )

    strategy = {
        "strategy_id": "lhb_shortline",
        "strategy_name": "LHB Shortline Combo",
        "default_parameters": {"rebalance_frequency": "daily"},
        "latest_metrics": {"signal_status": "no_position_rows", "signal_count": None},
    }

    enriched = backtests._with_latest_eod_strategy_metrics(strategy)

    assert enriched["latest_metrics"]["as_of_date"] == "2026-06-16"
    assert enriched["latest_metrics"]["signal_status"] == "candidate_rows"
    assert enriched["latest_metrics"]["signal_count"] == 5
    assert "当日候选 5 只" in enriched["latest_evidence"]


def test_eod_equity_path_metrics_rebase_to_latest_year(tmp_path):
    equity_path = tmp_path / "tech_equity.csv"
    equity_path.write_text(
        "\n".join(
            [
                "trade_date,equity,drawdown,net_return",
                "2025-12-31,2.0000,0.0000,0.0000",
                "2026-01-05,2.0000,0.0000,0.0000",
                "2026-01-06,1.8000,-0.1000,-0.1000",
                "2026-06-15,2.2000,0.0000,0.0500",
                "2026-06-16,2.4000,0.0000,0.0909",
            ]
        ),
        encoding="utf-8",
    )

    metrics = backtests._metrics_from_eod_equity_path(
        {"metadata": {"equity_path": str(equity_path)}},
        {"default_parameters": {"rebalance_frequency": "weekly"}},
    )

    assert metrics["total_return_pct"] == 20.0
    assert metrics["max_drawdown_pct"] == -10.0


def test_list_backtest_strategies_returns_validated_combo_rows_only():
    rows = backtests.list_backtest_strategies()

    by_id = {row["strategy_id"]: row for row in rows}
    assert list(by_id) == [
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
    ]
    assert {row["status"] for row in rows} == {"runnable"}
    assert "manual_v1_topn_rotation" not in by_id
    assert "position_control" not in by_id


def test_list_backtest_strategies_applies_balanced_contract_defaults(monkeypatch):
    class Contract:
        strategy_id = "tech_bottleneck"
        profile = "balanced"
        variant = "strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d"
        top_n = 5
        frequency = "biweekly"
        protection_name = "rank_exit_top10_1d"
        transaction_cost_bps = 20.0
        adjust_type = "hfq"
        contract_id = "tech_bottleneck:balanced:test"

    monkeypatch.setattr(
        backtests,
        "list_strategy_catalog",
        lambda: [
            {
                "strategy_id": "tech_bottleneck",
                "strategy_name": "Tech Bottleneck Combo",
                "status": "runnable",
                "default_parameters": {
                    "top_n": 5,
                    "rebalance_frequency": "weekly",
                    "transaction_cost_bps": 20,
                    "adjust_type": "hfq",
                },
            }
        ],
    )
    monkeypatch.setattr(backtests, "load_strategy_contracts", lambda profile="balanced": {"tech_bottleneck": Contract()})
    monkeypatch.setattr(backtests, "_enrich_strategies_with_latest_db_metrics", lambda rows: rows)
    monkeypatch.setattr(backtests, "_enrich_strategies_with_latest_eod_metrics", lambda rows: rows)

    rows = backtests.list_backtest_strategies()

    assert rows[0]["default_parameters"]["top_n"] == 5
    assert rows[0]["default_parameters"]["rebalance_frequency"] == "biweekly"
    assert rows[0]["default_parameters"]["protection_name"] == "rank_exit_top10_1d"
    assert rows[0]["default_parameters"]["contract_profile"] == "balanced"


def test_run_fresh_backtest_applies_balanced_strategy_contract(monkeypatch):
    calls = []

    class Contract:
        strategy_id = "tech_bottleneck"
        profile = "balanced"
        variant = "strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d"
        top_n = 5
        frequency = "biweekly"
        protection_name = "rank_exit_top10_1d"
        transaction_cost_bps = 20.0
        adjust_type = "hfq"
        contract_id = "tech_bottleneck:balanced:test"

    monkeypatch.setattr(backtests, "load_strategy_contracts", lambda profile="balanced": {"tech_bottleneck": Contract()})

    def fake_runner(payload):
        calls.append(payload)
        return {
            "strategy_id": "tech_bottleneck",
            "source_kind": "tech_bottleneck_v1",
            "summary": {"engine_version": "tech_bottleneck_v1"},
        }

    monkeypatch.setattr(backtests, "run_tech_bottleneck_v1_backtest_for_dashboard", fake_runner)

    result = backtests.run_fresh_backtest(
        {
            "strategy_id": "tech_bottleneck",
            "start_date": "2026-01-01",
            "end_date": "2026-06-17",
        }
    )

    assert calls[0]["top_n"] == 5
    assert calls[0]["rebalance_frequency"] == "biweekly"
    assert calls[0]["protection_name"] == "rank_exit_top10_1d"
    assert result["config"]["contract_profile"] == "balanced"
    assert result["summary"]["top_n"] == 5
    assert result["summary"]["frequency"] == "biweekly"
    assert result["summary"]["protection_name"] == "rank_exit_top10_1d"
    assert result["summary"]["transaction_cost_bps"] == 20.0
    assert result["summary"]["adjust_type"] == "hfq"


def test_run_fresh_backtest_preserves_explicit_params_over_strategy_contract(monkeypatch):
    calls = []

    class Contract:
        strategy_id = "tech_bottleneck"
        profile = "balanced"
        variant = "strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d"
        top_n = 5
        frequency = "biweekly"
        protection_name = "rank_exit_top10_1d"
        transaction_cost_bps = 20.0
        adjust_type = "hfq"
        contract_id = "tech_bottleneck:balanced:test"

    monkeypatch.setattr(backtests, "load_strategy_contracts", lambda profile="balanced": {"tech_bottleneck": Contract()})

    def fake_runner(payload):
        calls.append(payload)
        return {
            "strategy_id": "tech_bottleneck",
            "source_kind": "tech_bottleneck_v1",
            "config": {"top_n": payload["top_n"], "rebalance_frequency": payload["rebalance_frequency"]},
            "summary": {"engine_version": "tech_bottleneck_v1"},
        }

    monkeypatch.setattr(backtests, "run_tech_bottleneck_v1_backtest_for_dashboard", fake_runner)

    result = backtests.run_fresh_backtest(
        {
            "strategy_id": "tech_bottleneck",
            "start_date": "2026-01-01",
            "end_date": "2026-06-17",
            "top_n": 5,
            "rebalance_frequency": "weekly",
        }
    )

    assert calls[0]["top_n"] == 5
    assert calls[0]["rebalance_frequency"] == "weekly"
    assert calls[0]["protection_name"] == "rank_exit_top10_1d"
    assert result["config"]["contract_profile"] == "balanced"


def test_strategy_metrics_hide_stale_performance_when_contract_mismatched(monkeypatch, tmp_path):
    artifact = tmp_path / "strategy_mid_trend_review.csv"
    artifact.write_text(
        "trade_date,asset_id,rank,strategy_id,strategy_name,stock_name\n"
        "2026-06-17,CN:SZ:000001,1,mid_trend,Mid Trend Combo,平安银行\n",
        encoding="utf-8",
    )

    class Contract:
        strategy_id = "mid_trend"
        profile = "balanced"
        engine = "mid_trend_v1"
        variant = "top5_weekly_max_2_replacements"
        top_n = 5
        frequency = "weekly"
        protection_name = None
        transaction_cost_bps = 20.0
        adjust_type = "hfq"
        contract_id = "mid_trend:balanced:test"

    monkeypatch.setattr(backtests, "load_strategy_contracts", lambda profile="balanced": {"mid_trend": Contract()})
    monkeypatch.setattr(
        backtests,
        "load_latest_data_run_manifest",
        lambda: [
            {
                "module": "strategy_mid_trend",
                "status": "success",
                "latest_trade_date": "2026-06-17",
                "row_count": 1,
                "artifact_path": str(artifact),
                "metadata": {
                    "summary": {
                        "engine_version": "mid_trend_v1",
                        "variant_name": "old_wrong_variant",
                        "top_n": 5,
                        "transaction_cost_bps": 20.0,
                        "adjust_type": "hfq",
                        "frequency": "weekly",
                        "total_return": 9.0,
                        "max_drawdown": -0.1,
                    }
                },
            }
        ],
        raising=False,
    )

    enriched = backtests._with_latest_eod_strategy_metrics(
        {
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend Combo",
            "latest_metrics": {
                "as_of_date": "2026-06-02",
                "total_return_pct": 55.99,
                "max_drawdown_pct": -17.52,
                "latest_day_return_pct": 0.43,
                "latest_day_drawdown_pct": -8.68,
                "latest_period_return_pct": -4.43,
                "latest_period_label": "最近调仓周期",
                "signal_status": "connected",
                "signal_count": 5,
            },
        }
    )

    metrics = enriched["latest_metrics"]
    assert metrics["as_of_date"] == "2026-06-17"
    assert metrics["signal_status"] == "contract_mismatch"
    assert metrics["signal_count"] == 1
    assert metrics["contract_status"] == "failed"
    assert "variant mismatch" in metrics["contract_reason"]
    for key in [
        "total_return_pct",
        "max_drawdown_pct",
        "latest_day_return_pct",
        "latest_day_drawdown_pct",
        "latest_period_return_pct",
        "latest_period_label",
    ]:
        assert key not in metrics


def test_latest_strategy_metrics_use_latest_database_trade_date(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append({"sql": sql, "params": params})
        if "FROM backtest.strategy_backtest_run" in sql:
            return [{"run_id": "run-1", "summary_json": {"total_return": 0.2351, "max_drawdown": -0.0834}}]
        if "FROM backtest.strategy_backtest_equity" in sql:
            assert "DISTINCT ON (trade_date)" in sql
            return [
                {"trade_date": "2026-06-10", "equity": 1.2351, "drawdown": -0.021, "daily_return": 0.0123},
                {"trade_date": "2026-06-08", "equity": 1.2201, "drawdown": -0.034, "daily_return": -0.004},
            ]
        if "FROM backtest.strategy_backtest_position" in sql:
            return [{"signal_count": 5}]
        raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(backtests, "fetch_all", fake_fetch_all, raising=False)

    strategy = {
        "strategy_id": "tech_bottleneck",
        "strategy_name": "Tech Bottleneck Combo",
        "latest_metrics": {"signal_status": "connected", "signal_count": 2},
    }

    enriched = backtests._with_latest_db_metrics(object(), strategy)

    assert calls[0]["params"] == ["tech_bottleneck"]
    assert calls[1]["params"] == ["run-1"]
    assert enriched["latest_metrics"] == {
        "as_of_date": "2026-06-10",
        "total_return_pct": 23.51,
        "max_drawdown_pct": -8.34,
        "latest_day_return_pct": 1.23,
        "latest_day_drawdown_pct": -2.1,
        "latest_period_return_pct": 1.23,
        "latest_period_label": "最近交易日",
        "signal_status": "connected",
        "signal_count": 5,
    }


def test_latest_strategy_metrics_use_weekly_period_return_for_weekly_strategies(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        if "FROM backtest.strategy_backtest_run" in sql:
            return [{"run_id": "run-weekly", "summary_json": {"total_return": 0.56, "max_drawdown": -0.12}}]
        if "FROM backtest.strategy_backtest_equity" in sql:
            return [
                {"trade_date": "2026-06-16", "equity": 1.56, "drawdown": -0.02, "daily_return": 0.004},
                {"trade_date": "2026-06-15", "equity": 1.5538, "drawdown": -0.025, "daily_return": 0.002},
                {"trade_date": "2026-06-12", "equity": 1.5480, "drawdown": -0.03, "daily_return": 0.001},
                {"trade_date": "2026-06-11", "equity": 1.5420, "drawdown": -0.04, "daily_return": -0.002},
                {"trade_date": "2026-06-10", "equity": 1.5360, "drawdown": -0.05, "daily_return": 0.003},
                {"trade_date": "2026-06-09", "equity": 1.50, "drawdown": -0.055, "daily_return": 0.001},
            ]
        if "FROM backtest.strategy_backtest_position" in sql:
            return [{"signal_count": 5}]
        raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(backtests, "fetch_all", fake_fetch_all, raising=False)

    strategy = {
        "strategy_id": "mid_trend",
        "strategy_name": "Mid Trend Combo",
        "default_parameters": {"rebalance_frequency": "weekly"},
        "latest_metrics": {},
    }

    enriched = backtests._with_latest_db_metrics(object(), strategy)

    assert enriched["latest_metrics"]["latest_day_return_pct"] == 0.4
    assert enriched["latest_metrics"]["latest_period_return_pct"] == pytest.approx(4.0)
    assert enriched["latest_metrics"]["latest_period_label"] == "最近调仓周期"


def test_latest_position_signal_metrics_returns_no_position_rows_when_empty(monkeypatch):
    monkeypatch.setattr(backtests, "fetch_all", lambda conn, sql, params: [{"signal_count": 0}], raising=False)

    assert backtests._latest_position_signal_metrics(object(), "run-without-positions") == ("no_position_rows", None)


def test_fresh_replay_backtest_adapter_delegates_fresh_scores_and_replay():
    calls = []

    class FakeFreshAdapter:
        strategy_id = "lhb_shortline"

        def load_scores(self, params):
            calls.append(("fresh", params.start_date))
            return pd.DataFrame([{"trade_date": params.start_date, "asset_id": "A", "score_total": 1.0}])

    class FakeReplayAdapter:
        strategy_id = "lhb_shortline"
        strategy_name = "LHB Shortline Combo"
        combo_scheme = "lhb_shortline_combo_v1"

        def run_replay(self, params, run_config):
            calls.append(("replay", run_config["top_n"]))
            return {"strategy_id": "lhb_shortline", "summary": {"combo_scheme": self.combo_scheme}}

    combo = adapters.FreshReplayBacktestAdapter(FakeFreshAdapter(), FakeReplayAdapter())
    params = adapters.StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08")

    scores = combo.load_scores(params)
    replay = combo.run_replay(params, {"top_n": 20})

    assert combo.strategy_id == "lhb_shortline"
    assert combo.strategy_name == "LHB Shortline Combo"
    assert scores.iloc[0]["asset_id"] == "A"
    assert replay["summary"]["combo_scheme"] == "lhb_shortline_combo_v1"
    assert calls == [("fresh", "2026-01-01"), ("replay", 20)]


def test_load_vectorized_topn_prices_queries_market_daily_bar_directly(monkeypatch):
    calls = []
    expected_rows = [
        {
            "trade_date": "2026-06-02",
            "asset_id": "A",
            "open": 10.0,
            "close": 10.5,
            "amount": 1000000.0,
            "trade_status": "1",
            "is_limit_up": False,
            "is_limit_down": False,
            "is_suspended": False,
        }
    ]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_fetch_all(conn, sql, params):
        calls.append({"conn": conn, "sql": sql, "params": params})
        return expected_rows

    monkeypatch.setattr(backtests, "connect", lambda service: FakeConnection(), raising=False)
    monkeypatch.setattr(backtests, "fetch_all", fake_fetch_all, raising=False)
    monkeypatch.setattr(
        backtests,
        "load_vectorized_topn_inputs",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected score query")),
        raising=False,
    )

    prices = backtests.load_vectorized_topn_prices(
        start_date="2026-06-01",
        end_date="2026-06-05",
        adjust_type="hfq",
    )

    assert prices.to_dict("records") == expected_rows
    assert len(calls) == 1
    assert "FROM market_daily_bar" in calls[0]["sql"]
    assert "stock_score_daily" not in calls[0]["sql"]
    assert "false AS is_limit_up" in calls[0]["sql"]
    assert "false AS is_limit_down" in calls[0]["sql"]
    assert "trade_status <> '1' AS is_suspended" in calls[0]["sql"]
    assert "ORDER BY trade_date, asset_id" in calls[0]["sql"]
    assert calls[0]["params"] == ["hfq", "2026-06-01", "2026-06-05"]


def test_run_topn_backtest_loads_inputs_and_returns_json_safe_payload(monkeypatch):
    calls = {}
    result = VectorizedTopNResult(
        config=VectorizedTopNConfig(
            start_date="2026-06-01",
            end_date="2026-06-05",
            top_n=2,
            rebalance_frequency="daily",
            transaction_cost_bps=10.0,
            max_positions=2,
        ),
        equity_curve=pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-06-02"),
                    "equity": 1.02,
                    "drawdown": pd.NA,
                    "turnover": float("nan"),
                    "net_return": 0.02,
                }
            ]
        ),
        positions=pd.DataFrame(
            [
                {
                    "rebalance_date": pd.Timestamp("2026-06-01"),
                    "asset_id": "A",
                    "rank": 1,
                    "score_total": 90,
                    "weight": 0.5,
                }
            ]
        ),
        trades=pd.DataFrame(
            [
                {
                    "execution_date": pd.Timestamp("2026-06-02"),
                    "asset_id": "A",
                    "side": "buy",
                    "executed_weight": 0.5,
                }
            ]
        ),
        summary={
            "total_return": 0.02,
            "max_drawdown": float("nan"),
            "average_turnover": pd.NA,
            "periods": 1,
        },
    )

    def fake_load_prices(**kwargs):
        calls["prices"] = kwargs
        return pd.DataFrame([{"trade_date": "2026-06-02", "asset_id": "A", "close": 10.5}])

    def fake_run_backtest(scores, prices, config):
        calls["scores"] = scores
        calls["price_frame"] = prices
        calls["config"] = config
        return result

    class FakeAdapter:
        strategy_id = "manual_v1_topn_rotation"

        def load_scores(self, params):
            calls["params"] = params
            return pd.DataFrame(
                [
                    {
                        "trade_date": "2026-06-01",
                        "asset_id": "A",
                        "rank": 1,
                        "score_total": 90.0,
                    }
                ]
            )

    monkeypatch.setitem(
        backtests.STRATEGY_BACKTEST_REGISTRY,
        "manual_v1_topn_rotation",
        FakeAdapter(),
    )
    monkeypatch.setattr(backtests, "load_vectorized_topn_prices", fake_load_prices)
    monkeypatch.setattr(backtests, "run_vectorized_topn_backtest", fake_run_backtest)

    payload = backtests.run_fresh_backtest(
        {
            "strategy_id": "manual_v1_topn_rotation",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "top_n": 2,
            "rebalance_frequency": "daily",
            "transaction_cost_bps": 10,
            "max_positions": None,
            "max_position_weight": 0.2,
            "risk_profile": "drawdown_control",
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert calls["prices"] == {
        "start_date": "2026-06-01",
        "end_date": "2026-06-05",
        "adjust_type": "hfq",
    }
    assert calls["params"].start_date == "2026-06-01"
    assert calls["params"].end_date == "2026-06-05"
    assert calls["params"].score_version == "manual_v1"
    assert calls["params"].adjust_type == "hfq"
    assert calls["scores"].to_dict("records") == [
        {
            "trade_date": "2026-06-01",
            "asset_id": "A",
            "rank": 1,
            "score_total": 90.0,
        }
    ]
    assert calls["price_frame"].to_dict("records") == [
        {"trade_date": "2026-06-02", "asset_id": "A", "close": 10.5}
    ]
    assert calls["config"] == VectorizedTopNConfig(
        start_date="2026-06-01",
        end_date="2026-06-05",
        top_n=2,
        rebalance_frequency="weekly",
        transaction_cost_bps=10.0,
        max_positions=None,
        max_position_weight=0.2,
    )
    assert payload["strategy_id"] == "manual_v1_topn_rotation"
    assert payload["strategy_name"] == "Manual V1 TopN Rotation"
    assert payload["execution_mode"] == "fresh"
    assert payload["read_only"] is False
    assert payload["config"]["adjust_type"] == "hfq"
    assert payload["config"]["max_position_weight"] == 0.2
    assert payload["summary"]["total_return"] == 0.02
    assert payload["summary"]["max_drawdown"] is None


def test_run_replay_backtest_uses_replay_adapter(monkeypatch):
    calls = {}

    class FakeReplayAdapter:
        strategy_id = "mid_trend"
        strategy_name = "Mid Trend Combo"

        def run_replay(self, params, run_config):
            calls["params"] = params
            calls["run_config"] = run_config
            return {
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "read_only": True,
                "config": {"start_date": params.start_date, "end_date": params.end_date},
                "summary": {"final_equity": 1.2},
                "equity_curve": [],
                "positions": [],
                "trades": [],
            }

    monkeypatch.setitem(backtests.STRATEGY_BACKTEST_REGISTRY, "mid_trend", FakeReplayAdapter())

    payload = backtests.run_replay_backtest(
        {
            "strategy_id": "mid_trend",
            "start_date": "2026-01-01",
            "end_date": "2026-06-08",
            "top_n": 20,
            "rebalance_frequency": "weekly",
            "transaction_cost_bps": 10,
            "max_positions": 20,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert payload["execution_mode"] == "replay"
    assert payload["result_source"] == "database_replay"
    assert payload["summary"]["final_equity"] == 1.2
    assert calls["params"].start_date == "2026-01-01"


def test_run_fresh_backtest_bypasses_replay_adapter_and_uses_live_scores(monkeypatch):
    calls = {}

    class FakeComboAdapter:
        strategy_id = "manual_v1_topn_rotation"
        strategy_name = "Manual V1 TopN Rotation"

        def run_replay(self, params, run_config):
            raise AssertionError("fresh mode must not call run_replay")

        def load_scores(self, params):
            calls["params"] = params
            return pd.DataFrame(
                [{"trade_date": "2026-01-02", "asset_id": "A", "rank": 1, "score_total": 90.0}]
            )

    result = VectorizedTopNResult(
        config=VectorizedTopNConfig(
            start_date="2026-01-01",
            end_date="2026-06-08",
            top_n=1,
            rebalance_frequency="weekly",
            transaction_cost_bps=10.0,
            max_positions=1,
        ),
        equity_curve=pd.DataFrame([{"date": "2026-01-02", "equity": 1.03, "drawdown": 0.0}]),
        positions=pd.DataFrame([{"rebalance_date": "2026-01-02", "asset_id": "A", "weight": 1.0}]),
        trades=pd.DataFrame([{"execution_date": "2026-01-02", "asset_id": "A", "side": "buy"}]),
        summary={"final_equity": 1.03, "total_return": 0.03, "max_drawdown": 0.0},
    )

    monkeypatch.setitem(backtests.STRATEGY_BACKTEST_REGISTRY, "manual_v1_topn_rotation", FakeComboAdapter())
    monkeypatch.setattr(
        backtests,
        "load_vectorized_topn_prices",
        lambda **kwargs: pd.DataFrame([{"trade_date": "2026-01-02", "asset_id": "A", "close": 10.0}]),
    )
    monkeypatch.setattr(backtests, "run_vectorized_topn_backtest", lambda scores, prices, config: result)

    payload = backtests.run_fresh_backtest(
        {
            "strategy_id": "manual_v1_topn_rotation",
            "start_date": "2026-01-01",
            "end_date": "2026-06-08",
            "top_n": 1,
            "rebalance_frequency": "weekly",
            "transaction_cost_bps": 10,
            "max_positions": 1,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert payload["execution_mode"] == "fresh"
    assert payload["result_source"] == "live_vectorized_backtest"
    assert payload["summary"]["final_equity"] == 1.03
    assert payload["summary"]["fresh_engine_note"] == "live score rebuild from selected strategy factors and market prices"
    assert payload["equity_curve"][0]["date"] == "2026-01-02"
    assert payload["positions"][0]["rebalance_date"] == "2026-01-02"
    assert payload["trades"][0]["execution_date"] == "2026-01-02"


def test_run_fresh_backtest_routes_lhb_to_shortline_v1(monkeypatch):
    monkeypatch.setattr(
        backtests,
        "_prepare_lhb_phase18c_cli_inputs",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not read legacy Phase CSV")),
        raising=False,
    )
    monkeypatch.setattr(
        backtests,
        "_run_lhb_database_full_recompute_backtest",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not use transitional Phase-derived DB recompute")),
        raising=False,
    )
    calls = {}

    def fake_v1(payload):
        calls["payload"] = payload
        return {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "read_only": False,
            "source_kind": "lhb_shortline_v1",
            "source_paths": [],
            "config": {
                "engine_version": "lhb_shortline_v1",
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "top_n": payload["top_n"],
                "position_weight": 0.2,
            },
            "summary": {
                "engine_version": "lhb_shortline_v1",
                "total_return": 0.0396,
                "final_equity": 1.0396,
                "max_drawdown": 0.0,
                "transaction_cost_bps": 10.0,
                "fresh_engine_note": "database full recompute via lhb_shortline_v1",
            },
            "equity_curve": [{"trade_date": "2026-01-04", "equity": 1.0396, "drawdown": 0.0}],
            "positions": [{"date": "2026-01-03", "asset_id": "B", "weight": 0.2}],
            "trades": [{"ts_code": "B", "realized_return": 0.198}],
        }

    monkeypatch.setattr(backtests, "run_lhb_shortline_v1_backtest_for_dashboard", fake_v1, raising=False)

    payload = backtests.run_fresh_backtest(
        {
            "strategy_id": "lhb_shortline",
            "start_date": "2026-01-01",
            "end_date": "2026-06-08",
            "top_n": 1,
            "rebalance_frequency": "weekly",
            "transaction_cost_bps": 10,
            "max_positions": None,
            "max_position_weight": 0.2,
            "risk_profile": "drawdown_control",
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert payload["execution_mode"] == "fresh"
    assert payload["result_source"] == "lhb_shortline_v1"
    assert payload["config"]["engine_version"] == "lhb_shortline_v1"
    assert payload["config"]["position_weight"] == 0.2
    assert payload["summary"]["total_return"] == pytest.approx(0.0396)
    assert payload["summary"]["transaction_cost_bps"] == 10.0
    assert payload["trades"][0]["ts_code"] == "B"
    assert payload["trades"][0]["realized_return"] == pytest.approx(0.198)
    assert calls["payload"]["start_date"] == "2026-01-01"
    assert calls["payload"]["top_n"] == 1
    assert calls["payload"]["rebalance_frequency"] == "daily"
    assert calls["payload"]["max_position_weight"] == 0.2
    assert calls["payload"]["risk_profile"] == "drawdown_control"


def test_run_fresh_backtest_routes_mid_trend_to_v1(monkeypatch):
    calls = {}

    def fake_mid_trend_v1(payload):
        calls["payload"] = payload
        return {
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend Combo",
            "read_only": False,
            "source_kind": "mid_trend_v1",
            "config": {
                "engine_version": "mid_trend_v1",
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "top_n": payload["top_n"],
                "max_position_weight": payload["max_position_weight"],
            },
            "summary": {
                "engine_version": "mid_trend_v1",
                "variant_name": "top5_weekly_max2_selective_trend_holding_protection_v1",
                "final_equity": 1.5599,
                "total_return": 0.5599,
                "max_drawdown": -0.1752,
                "fresh_engine_note": "Mid Trend V1 DB lifecycle recompute via weekly control benchmark engine",
            },
            "equity_curve": [{"date": "2026-01-05", "equity": 1.0, "drawdown": 0.0}],
            "positions": [{"rebalance_date": "2026-01-05", "asset_id": "A", "weight": 0.2}],
            "trades": [{"trade_date": "2026-01-05", "asset_id": "A", "side": "buy"}],
        }

    monkeypatch.setattr(backtests, "run_mid_trend_v1_backtest_for_dashboard", fake_mid_trend_v1, raising=False)
    monkeypatch.setattr(
        backtests,
        "load_vectorized_topn_prices",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("mid_trend fresh must not use generic vectorized TopN")),
    )

    payload = backtests.run_fresh_backtest(
        {
            "strategy_id": "mid_trend",
            "start_date": "2026-01-01",
            "end_date": "2026-06-08",
            "top_n": 5,
            "rebalance_frequency": "weekly",
            "transaction_cost_bps": 20,
            "max_positions": 5,
            "max_position_weight": 0.2,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert payload["execution_mode"] == "fresh"
    assert payload["result_source"] == "mid_trend_v1"
    assert payload["config"]["engine_version"] == "mid_trend_v1"
    assert payload["summary"]["final_equity"] == pytest.approx(1.5599)
    assert payload["summary"]["fresh_engine_note"] == "Mid Trend V1 DB lifecycle recompute via weekly control benchmark engine"
    assert calls["payload"]["start_date"] == "2026-01-01"
    assert calls["payload"]["top_n"] == 5
    assert calls["payload"]["transaction_cost_bps"] == 20.0
    assert calls["payload"]["max_position_weight"] == 0.2


def test_run_fresh_backtest_routes_tech_bottleneck_to_v1(monkeypatch):
    calls = {}

    def fake_tech_bottleneck_v1(payload):
        calls["payload"] = payload
        return {
            "strategy_id": "tech_bottleneck",
            "strategy_name": "Tech Bottleneck Discovery",
            "read_only": False,
            "source_kind": "tech_bottleneck_v1",
            "config": {
                "engine_version": "tech_bottleneck_v1",
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "top_n": payload["top_n"],
            },
            "summary": {
                "engine_version": "tech_bottleneck_v1",
                "final_equity": 1.2351,
                "total_return": 0.2351,
                "max_drawdown": -0.1258,
            },
            "equity_curve": [{"trade_date": "2026-01-05", "equity": 1.0, "drawdown": 0.0}],
            "positions": [],
            "trades": [],
        }

    monkeypatch.setattr(
        backtests,
        "run_tech_bottleneck_v1_backtest_for_dashboard",
        fake_tech_bottleneck_v1,
        raising=False,
    )
    monkeypatch.setattr(
        backtests,
        "load_vectorized_topn_prices",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("tech_bottleneck fresh must not use generic vectorized TopN")),
    )

    payload = backtests.run_fresh_backtest(
        {
            "strategy_id": "tech_bottleneck",
            "start_date": "2026-01-01",
            "end_date": "2026-06-08",
            "top_n": 5,
            "rebalance_frequency": "weekly",
            "transaction_cost_bps": 20,
            "max_positions": 5,
            "max_position_weight": 0.2,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert payload["execution_mode"] == "fresh"
    assert payload["result_source"] == "tech_bottleneck_v1"
    assert payload["config"]["engine_version"] == "tech_bottleneck_v1"
    assert payload["summary"]["final_equity"] == pytest.approx(1.2351)
    assert calls["payload"]["start_date"] == "2026-01-01"
    assert calls["payload"]["top_n"] == 5
    assert calls["payload"]["rebalance_frequency"] == "weekly"
    assert calls["payload"]["transaction_cost_bps"] == 20.0


def test_run_backtest_rejects_unknown_strategy():
    try:
        backtests.run_backtest(
            {
                "strategy_id": "unknown_strategy",
                "start_date": "2026-06-01",
                "end_date": "2026-06-05",
            }
        )
    except ValueError as exc:
        assert "unsupported strategy" in str(exc)
    else:
        raise AssertionError("expected unknown strategy to raise ValueError")


def test_run_backtest_uses_combo_replay_adapter_without_vectorized_topn(monkeypatch):
    calls = {}

    class FakeReplayAdapter:
        strategy_id = "lhb_shortline"

        def run_replay(self, params, run_config):
            calls["params"] = params
            calls["run_config"] = run_config
            return {
                "strategy_id": "lhb_shortline",
                "strategy_name": "LHB Shortline Combo",
                "read_only": True,
                "config": {"start_date": params.start_date, "end_date": params.end_date},
                "summary": {
                    "combo_scheme": "lhb_shortline_combo_v1",
                    "final_equity": 2.674043,
                    "total_return": 1.674043,
                    "max_drawdown": -0.027448,
                },
                "equity_curve": [{"date": "2026-06-08", "equity": 2.674043}],
                "positions": [],
                "trades": [{"trade_date": "2026-06-08", "asset_id": "CN:SZ:300615"}],
            }

    monkeypatch.setitem(backtests.STRATEGY_BACKTEST_REGISTRY, "lhb_shortline", FakeReplayAdapter())
    monkeypatch.setattr(
        backtests,
        "load_vectorized_topn_prices",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("combo replay should not load TopN prices")),
    )
    monkeypatch.setattr(
        backtests,
        "run_vectorized_topn_backtest",
        lambda scores, prices, config: (_ for _ in ()).throw(AssertionError("combo replay should not run TopN")),
    )

    payload = backtests.run_backtest(
        {
            "strategy_id": "lhb_shortline",
            "start_date": "2026-01-01",
            "end_date": "2026-06-08",
            "top_n": 20,
            "rebalance_frequency": "weekly",
            "transaction_cost_bps": 10,
            "max_positions": 20,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert calls["params"].start_date == "2026-01-01"
    assert calls["params"].end_date == "2026-06-08"
    assert calls["run_config"]["top_n"] == 20
    assert payload["strategy_id"] == "lhb_shortline"
    assert payload["summary"]["combo_scheme"] == "lhb_shortline_combo_v1"
    assert payload["summary"]["final_equity"] == 2.674043


def test_json_safe_conversion_handles_common_pandas_and_scalar_values():
    assert backtests.to_json_safe(pd.Timestamp("2026-06-02 13:45:00")) == "2026-06-02T13:45:00"
    assert backtests.to_json_safe(float("nan")) is None
    assert backtests.to_json_safe(pd.NA) is None
    assert backtests.to_json_safe({"value": math.inf}) == {"value": None}
    assert backtests.to_json_safe(pd.Series([1, pd.NA])) == [1, None]


def test_backtest_routes(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_backtest_strategies",
        lambda: [{"strategy_id": "manual_v1_topn_rotation"}],
    )
    monkeypatch.setattr(
        dashboard_app,
        "run_backtest",
        lambda payload: {"strategy_id": payload["strategy_id"], "read_only": True},
    )
    client = TestClient(dashboard_app.create_app())

    strategies = client.get("/api/backtests/strategies")
    result = client.post(
        "/api/backtests/run",
        json={
            "strategy_id": "manual_v1_topn_rotation",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "top_n": 2,
            "rebalance_frequency": "daily",
            "transaction_cost_bps": 10,
            "max_positions": 2,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        },
    )

    assert strategies.status_code == 200
    assert strategies.json()["items"][0]["strategy_id"] == "manual_v1_topn_rotation"
    assert result.status_code == 200
    assert result.json()["read_only"] is True


def test_backtest_run_route_maps_value_error_to_400(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "run_backtest",
        lambda payload: (_ for _ in ()).throw(ValueError("unsupported strategy")),
    )
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/backtests/run", json={"strategy_id": "lhb_shortline"})

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported strategy"


def test_backtest_run_route_rejects_missing_required_fields():
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/backtests/run",
        json={"strategy_id": "manual_v1_topn_rotation"},
    )

    assert response.status_code == 400


def test_run_backtest_validates_config_before_loading_inputs(monkeypatch):
    calls = []

    monkeypatch.setattr(
        backtests,
        "load_vectorized_topn_prices",
        lambda **kwargs: calls.append(kwargs) or pd.DataFrame(),
    )

    try:
        backtests.run_backtest(
            {
                "strategy_id": "manual_v1_topn_rotation",
                "start_date": "2026-06-01",
                "end_date": "2026-06-05",
                "top_n": 0,
                "rebalance_frequency": "daily",
                "transaction_cost_bps": "inf",
                "max_positions": 0,
            }
        )
    except ValueError as exc:
        assert "top_n" in str(exc)
    else:
        raise AssertionError("expected invalid config to raise ValueError")

    assert calls == []
