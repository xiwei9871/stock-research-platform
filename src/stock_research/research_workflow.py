from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from stock_research.performance_tearsheet import write_performance_tearsheet
from stock_research.strategy_lifecycle import (
    StrategyLifecycleContext,
    TopNStrategyConfig,
    run_topn_strategy_lifecycle,
)
from stock_research.vectorized_topn_backtest import VectorizedTopNResult


@dataclass(frozen=True)
class TopNResearchWorkflowResult:
    context: StrategyLifecycleContext
    report_paths: dict[str, str]
    summary: dict[str, object]


LifecycleRunner = Callable[[TopNStrategyConfig], StrategyLifecycleContext]
TearsheetWriter = Callable[
    [VectorizedTopNResult, str, str | Path, int],
    dict[str, str],
]


def run_topn_research_workflow(
    config: TopNStrategyConfig,
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    annualization: int = 252,
    lifecycle_runner: LifecycleRunner = run_topn_strategy_lifecycle,
    tearsheet_writer: TearsheetWriter = write_performance_tearsheet,
) -> TopNResearchWorkflowResult:
    context = lifecycle_runner(config)
    if context.backtest_result is None:
        raise ValueError("lifecycle context does not contain a backtest result")

    strategy_id = str(context.report.get("strategy_id") or config.strategy_id or "topn-research")
    report_paths = tearsheet_writer(
        context.backtest_result,
        strategy_id,
        reports_dir,
        annualization,
    )
    return TopNResearchWorkflowResult(
        context=context,
        report_paths=report_paths,
        summary={
            "strategy_id": strategy_id,
            "latest_equity": context.report.get("latest_equity"),
            "total_return": context.backtest_result.summary.get("total_return"),
            "tearsheet_report": report_paths["report_path"],
        },
    )
