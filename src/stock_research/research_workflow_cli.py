import argparse
from pathlib import Path

from stock_research.research_workflow import run_topn_research_workflow
from stock_research.strategy_lifecycle import TopNStrategyConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stock_research.research_workflow_cli")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--score-version", default="manual_v1")
    parser.add_argument("--adjust-type", default="hfq")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument(
        "--rebalance-frequency",
        choices=["daily", "weekly"],
        default="daily",
    )
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument("--max-positions", type=int)
    parser.add_argument("--strategy-id")
    parser.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )
    parser.add_argument("--annualization", type=int, default=252)
    return parser


def main(workflow_runner=run_topn_research_workflow) -> None:
    args = build_parser().parse_args()
    config = TopNStrategyConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        score_version=args.score_version,
        adjust_type=args.adjust_type,
        top_n=args.top_n,
        rebalance_frequency=args.rebalance_frequency,
        transaction_cost_bps=args.transaction_cost_bps,
        max_positions=args.max_positions,
        strategy_id=args.strategy_id,
    )
    result = workflow_runner(
        config,
        reports_dir=Path(args.reports_dir),
        annualization=args.annualization,
    )
    print(f"topn_research_workflow|strategy_id|{result.summary['strategy_id']}")
    print(f"topn_research_workflow|latest_equity|{result.summary['latest_equity']}")
    print(f"topn_research_workflow|total_return|{result.summary['total_return']}")
    for key in ("report_path", "metrics_path", "equity_curve_path", "positions_path"):
        print(f"topn_research_workflow|{key}|{result.report_paths[key]}")


if __name__ == "__main__":
    main()
