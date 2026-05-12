import pandas as pd

from stock_research.strategy_lifecycle import (
    StrategyLifecycleContext,
    TopNStrategyConfig,
    generate_report,
    generate_signals,
    run_topn_strategy_lifecycle,
)
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    VectorizedTopNResult,
)


def _scores() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "rank": 1,
                "score_total": 90.0,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "rank": 2,
                "score_total": 80.0,
            },
        ]
    )


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "close": 10.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "close": 20.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "close": 20.0},
        ]
    )


def test_run_topn_strategy_lifecycle_runs_ordered_steps_with_injected_dependencies():
    calls = []

    def fake_loader(start_date, end_date, score_version, adjust_type):
        calls.append(("prepare_data", start_date, end_date, score_version, adjust_type))
        return _scores(), _prices()

    def fake_runner(scores, prices, config):
        calls.append(("rebalance", scores.copy(), prices.copy(), config))
        equity_curve = pd.DataFrame(
            [
                {
                    "date": "2026-01-02",
                    "gross_return": 0.05,
                    "turnover": 1.0,
                    "transaction_cost": 0.001,
                    "net_return": 0.049,
                    "equity": 1.049,
                    "drawdown": 0.0,
                    "holdings_count": 2,
                }
            ]
        )
        positions = pd.DataFrame(
            [
                {
                    "rebalance_date": "2026-01-01",
                    "asset_id": "A",
                    "rank": 1,
                    "score_total": 90.0,
                    "weight": 0.5,
                }
            ]
        )
        return VectorizedTopNResult(
            config=config,
            equity_curve=equity_curve,
            positions=positions,
            summary={"total_return": 0.049, "periods": 1},
        )

    config = TopNStrategyConfig(
        start_date="2026-01-01",
        end_date="2026-01-02",
        score_version="manual_v1",
        top_n=2,
        rebalance_frequency="daily",
        transaction_cost_bps=10.0,
    )

    context = run_topn_strategy_lifecycle(
        config,
        loader=fake_loader,
        backtest_runner=fake_runner,
    )

    assert [call[0] for call in calls] == ["prepare_data", "rebalance"]
    assert context.lifecycle_steps == [
        "prepare_data",
        "before_market",
        "generate_signals",
        "rebalance",
        "after_market",
        "generate_report",
    ]
    assert context.signals.shape[0] == 2
    assert isinstance(calls[1][3], VectorizedTopNConfig)
    assert calls[1][3].top_n == 2
    assert calls[1][3].transaction_cost_bps == 10.0
    assert context.backtest_result.summary["total_return"] == 0.049
    assert context.report["strategy_id"].startswith("topn_lifecycle:")


def test_generate_signals_caps_candidates_by_date_and_ignores_future_dates():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "rank": 2, "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "rank": 3, "score_total": 70.0},
            {"trade_date": "2026-01-02", "asset_id": "D", "rank": 1, "score_total": 95.0},
            {"trade_date": "2026-01-03", "asset_id": "E", "rank": 1, "score_total": 99.0},
        ]
    )
    config = TopNStrategyConfig(
        start_date="2026-01-01",
        end_date="2026-01-02",
        top_n=3,
        max_positions=2,
    )
    context = StrategyLifecycleContext(
        config=config,
        scores=scores,
        lifecycle_steps=["prepare_data", "before_market"],
    )

    output = generate_signals(context)

    assert list(output.signals["trade_date"]) == [
        "2026-01-01",
        "2026-01-01",
        "2026-01-02",
    ]
    assert list(output.signals["asset_id"]) == ["A", "B", "D"]
    assert "2026-01-03" not in set(output.signals["trade_date"])


def test_generate_report_includes_config_counts_summary_and_latest_equity():
    equity_curve = pd.DataFrame(
        [
            {
                "date": "2026-01-02",
                "gross_return": 0.05,
                "turnover": 1.0,
                "transaction_cost": 0.001,
                "net_return": 0.049,
                "equity": 1.049,
                "drawdown": 0.0,
                "holdings_count": 2,
            }
        ]
    )
    result = VectorizedTopNResult(
        config=VectorizedTopNConfig("2026-01-01", "2026-01-02", top_n=2),
        equity_curve=equity_curve,
        positions=pd.DataFrame(),
        summary={"total_return": 0.049, "periods": 1},
    )
    context = StrategyLifecycleContext(
        config=TopNStrategyConfig(
            start_date="2026-01-01",
            end_date="2026-01-02",
            score_version="manual_v1",
            top_n=2,
            strategy_id="custom-strategy",
        ),
        scores=_scores(),
        prices=_prices(),
        signals=_scores(),
        backtest_result=result,
        lifecycle_steps=["prepare_data", "before_market", "generate_signals", "rebalance", "after_market"],
    )

    output = generate_report(context)

    assert output.report == {
        "strategy_id": "custom-strategy",
        "start_date": "2026-01-01",
        "end_date": "2026-01-02",
        "score_version": "manual_v1",
        "top_n": 2,
        "rebalance_frequency": "daily",
        "score_rows": 2,
        "signal_rows": 2,
        "price_rows": 4,
        "summary": {"total_return": 0.049, "periods": 1},
        "latest_equity": 1.049,
    }
