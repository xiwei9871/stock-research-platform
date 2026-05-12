import pandas as pd

from stock_research.research_workflow import run_topn_research_workflow
from stock_research.strategy_lifecycle import (
    StrategyLifecycleContext,
    TopNStrategyConfig,
)
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    VectorizedTopNResult,
)


def test_run_topn_research_workflow_runs_lifecycle_and_writes_tearsheet(tmp_path):
    calls = []
    equity_curve = pd.DataFrame(
        [
            {
                "date": "2026-01-02",
                "net_return": 0.02,
                "equity": 1.02,
                "drawdown": 0.0,
                "turnover": 1.0,
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
                "weight": 1.0,
            }
        ]
    )
    backtest_result = VectorizedTopNResult(
        config=VectorizedTopNConfig(
            start_date="2026-01-01",
            end_date="2026-01-02",
            top_n=1,
        ),
        equity_curve=equity_curve,
        positions=positions,
        summary={"total_return": 0.02, "periods": 1},
    )
    context = StrategyLifecycleContext(
        config=TopNStrategyConfig(
            start_date="2026-01-01",
            end_date="2026-01-02",
            top_n=1,
            strategy_id="workflow-test",
        ),
        backtest_result=backtest_result,
        report={"strategy_id": "workflow-test", "latest_equity": 1.02},
        lifecycle_steps=[
            "prepare_data",
            "before_market",
            "generate_signals",
            "rebalance",
            "after_market",
            "generate_report",
        ],
    )

    def fake_lifecycle_runner(config):
        calls.append(("lifecycle", config))
        return context

    def fake_tearsheet_writer(result, strategy_id, reports_dir, annualization=252):
        calls.append(("tearsheet", result, strategy_id, reports_dir, annualization))
        return {
            "report_path": str(tmp_path / "report.md"),
            "metrics_path": str(tmp_path / "metrics.csv"),
            "equity_curve_path": str(tmp_path / "equity.csv"),
            "positions_path": str(tmp_path / "positions.csv"),
        }

    output = run_topn_research_workflow(
        context.config,
        reports_dir=tmp_path,
        annualization=252,
        lifecycle_runner=fake_lifecycle_runner,
        tearsheet_writer=fake_tearsheet_writer,
    )

    assert [call[0] for call in calls] == ["lifecycle", "tearsheet"]
    assert calls[0][1] == context.config
    assert calls[1][1] is backtest_result
    assert calls[1][2] == "workflow-test"
    assert calls[1][3] == tmp_path
    assert output.context is context
    assert output.report_paths["report_path"].endswith("report.md")
    assert output.summary == {
        "strategy_id": "workflow-test",
        "latest_equity": 1.02,
        "total_return": 0.02,
        "tearsheet_report": str(tmp_path / "report.md"),
    }
