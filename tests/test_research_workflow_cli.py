from pathlib import Path

import pandas as pd

from stock_research.research_workflow import TopNResearchWorkflowResult
from stock_research.strategy_lifecycle import StrategyLifecycleContext, TopNStrategyConfig
from stock_research.research_workflow_cli import build_parser, main
from stock_research.vectorized_topn_backtest import VectorizedTopNConfig, VectorizedTopNResult


def test_research_workflow_cli_parser_accepts_arguments():
    args = build_parser().parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-02-01",
            "--score-version",
            "manual_v1",
            "--adjust-type",
            "hfq",
            "--top-n",
            "10",
            "--rebalance-frequency",
            "weekly",
            "--transaction-cost-bps",
            "5",
            "--max-positions",
            "8",
            "--strategy-id",
            "topn-weekly",
            "--reports-dir",
            "/tmp/reports",
            "--annualization",
            "252",
        ]
    )

    assert args.start_date == "2026-01-01"
    assert args.end_date == "2026-02-01"
    assert args.score_version == "manual_v1"
    assert args.adjust_type == "hfq"
    assert args.top_n == 10
    assert args.rebalance_frequency == "weekly"
    assert args.transaction_cost_bps == 5.0
    assert args.max_positions == 8
    assert args.strategy_id == "topn-weekly"
    assert args.reports_dir == "/tmp/reports"
    assert args.annualization == 252


def test_research_workflow_cli_main_prints_stable_output(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_runner(config, reports_dir, annualization):
        calls.append((config, reports_dir, annualization))
        backtest_result = VectorizedTopNResult(
            config=VectorizedTopNConfig(config.start_date, config.end_date, top_n=config.top_n),
            equity_curve=pd.DataFrame(),
            positions=pd.DataFrame(),
            summary={"total_return": 0.12},
        )
        context = StrategyLifecycleContext(
            config=config,
            backtest_result=backtest_result,
            report={"strategy_id": config.strategy_id, "latest_equity": 1.12},
        )
        return TopNResearchWorkflowResult(
            context=context,
            report_paths={
                "report_path": str(tmp_path / "report.md"),
                "metrics_path": str(tmp_path / "metrics.csv"),
                "equity_curve_path": str(tmp_path / "equity.csv"),
                "positions_path": str(tmp_path / "positions.csv"),
            },
            summary={
                "strategy_id": config.strategy_id,
                "latest_equity": 1.12,
                "total_return": 0.12,
                "tearsheet_report": str(tmp_path / "report.md"),
            },
        )

    monkeypatch.setattr(
        "sys.argv",
        [
            "python -m stock_research.research_workflow_cli",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-02-01",
            "--top-n",
            "5",
            "--strategy-id",
            "workflow-cli",
            "--reports-dir",
            str(tmp_path),
        ],
    )

    main(workflow_runner=fake_runner)

    config, reports_dir, annualization = calls[0]
    assert isinstance(config, TopNStrategyConfig)
    assert config.start_date == "2026-01-01"
    assert config.end_date == "2026-02-01"
    assert config.top_n == 5
    assert config.strategy_id == "workflow-cli"
    assert reports_dir == Path(tmp_path)
    assert annualization == 252
    assert capsys.readouterr().out.splitlines() == [
        "topn_research_workflow|strategy_id|workflow-cli",
        "topn_research_workflow|latest_equity|1.12",
        "topn_research_workflow|total_return|0.12",
        f"topn_research_workflow|report_path|{tmp_path / 'report.md'}",
        f"topn_research_workflow|metrics_path|{tmp_path / 'metrics.csv'}",
        f"topn_research_workflow|equity_curve_path|{tmp_path / 'equity.csv'}",
        f"topn_research_workflow|positions_path|{tmp_path / 'positions.csv'}",
    ]
