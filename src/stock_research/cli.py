import argparse

from stock_research.assets import sync_asset_master
from stock_research.backtest import run_top20_backtest
from stock_research.core_data import (
    build_asset_status_daily_for_service,
    build_industry_daily_bars_for_service,
    sync_core_asset_master_for_service,
)
from stock_research.features import compute_and_store_p0_features
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.factor_pipeline import build_and_store_factor_daily
from stock_research.factor_eval.report import generate_factor_eval_report
from stock_research.factor_eval_store import load_factor_eval_inputs
from stock_research.factor_store import load_top_scores, score_stored_factor_daily
from stock_research.daily_pipeline import run_daily_factor_pipeline
from stock_research.ingest_jobs import (
    create_ingest_jobs_for_service,
    format_ingest_loop_report,
    ingest_status_for_service,
    run_ingest_loop_for_service,
    run_ingest_jobs_for_service,
)
from stock_research.labels import compute_and_store_labels
from stock_research.loaders.baostock_ingestion import (
    sync_index_daily_bars,
    sync_industry_memberships,
)
from stock_research.loaders.baostock_finance_ingestion import sync_finance_for_period
from stock_research.market_data import load_market_daily_bars
from stock_research.portfolio_backtest import run_portfolio_backtest
from stock_research.quality import run_daily_quality_checks
from stock_research.reporting import format_daily_report
from stock_research.retention_backtest import run_retention_backtest
from stock_research.schema import apply_schema
from stock_research.selection import generate_selection, store_selection
from stock_research.v31_cache import build_v31_cache


def parse_int_list(value: str, option_name: str) -> list[int]:
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(part == "" for part in parts):
        raise argparse.ArgumentTypeError(f"{option_name} must not contain empty values")
    try:
        values = [int(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{option_name} must be a comma-separated list of integers"
        ) from exc

    if any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError(f"{option_name} values must be positive")
    return values


def parse_holding_days(value: str) -> list[int]:
    return parse_int_list(value, "--holding-days")


def parse_top_ks(value: str) -> list[int]:
    return parse_int_list(value, "--top-ks")


def format_progress_bar(index: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    filled = round(width * index / total)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def print_ingest_progress(event: dict) -> None:
    bar = format_progress_bar(int(event["index"]), int(event["total"]))
    prefix = (
        f"{bar} {event['index']}/{event['total']} "
        f"success={event['success']} failed={event['failed']}"
    )
    if event["event"] == "start":
        print(f"{prefix} running {event['job_id']}", flush=True)
    elif event["event"] == "success":
        print(
            f"{prefix} done {event['job_id']} "
            f"read={event['rows_read']} written={event['rows_written']}",
            flush=True,
        )
    elif event["event"] == "failed":
        print(f"{prefix} failed {event['job_id']} error={event['error']}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-research")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("apply-schema")
    subparsers.add_parser("apply-research-schema")
    subparsers.add_parser("sync-assets")
    subparsers.add_parser("sync-core-assets")

    asset_status = subparsers.add_parser("build-asset-status")
    asset_status.add_argument("--start-date")
    asset_status.add_argument("--end-date")
    asset_status.add_argument("--adjust-type", default="hfq")

    industry_bars = subparsers.add_parser("build-industry-bars")
    industry_bars.add_argument("--start-date")
    industry_bars.add_argument("--end-date")
    industry_bars.add_argument("--industry-system", default="csrc")
    industry_bars.add_argument("--adjust-type", default="hfq")

    industry_memberships = subparsers.add_parser("sync-industry-memberships")
    industry_memberships.add_argument("--trade-date", required=True)

    index_bars = subparsers.add_parser("sync-index-bars")
    index_bars.add_argument("--start-date", required=True)
    index_bars.add_argument("--end-date", required=True)

    baostock_finance = subparsers.add_parser("sync-baostock-finance")
    baostock_finance.add_argument("--year", required=True, type=int)
    baostock_finance.add_argument("--quarter", required=True, type=int)
    baostock_finance.add_argument("--limit", type=int)
    baostock_finance.add_argument("--offset", type=int, default=0)

    create_ingest = subparsers.add_parser("create-ingest-jobs")
    create_ingest.add_argument("--dataset", required=True)
    create_ingest.add_argument("--start-year", required=True, type=int)
    create_ingest.add_argument("--end-year", required=True, type=int)
    create_ingest.add_argument("--batch-size", required=True, type=int)

    run_ingest = subparsers.add_parser("run-ingest-jobs")
    run_ingest.add_argument("--dataset", required=True)
    run_ingest.add_argument("--limit-jobs", required=True, type=int)

    run_ingest_loop = subparsers.add_parser("run-ingest-loop")
    run_ingest_loop.add_argument("--dataset", required=True)
    run_ingest_loop.add_argument("--jobs-per-round", type=int, default=50)
    run_ingest_loop.add_argument("--sleep-seconds", type=int, default=10)
    run_ingest_loop.add_argument("--max-rounds", type=int)
    run_ingest_loop.add_argument("--report-target", required=True)
    run_ingest_loop.add_argument("--report-account", default="jarvis")
    run_ingest_loop.add_argument("--openclaw-bin", default="openclaw")
    run_ingest_loop.add_argument("--report-dry-run", action="store_true")

    ingest_status = subparsers.add_parser("ingest-status")
    ingest_status.add_argument("--dataset")

    load_bars = subparsers.add_parser("load-bars")
    load_bars.add_argument("--start-date")
    load_bars.add_argument("--end-date")
    load_bars.add_argument("--limit-tables", type=int)

    quality = subparsers.add_parser("quality")
    quality.add_argument("--trade-date")

    features = subparsers.add_parser("features")
    features.add_argument("--trade-date", required=True)

    labels = subparsers.add_parser("labels")
    labels.add_argument("--end-date", required=True)

    select = subparsers.add_parser("select")
    select.add_argument("--trade-date", required=True)
    select.add_argument("--top-n", type=int, default=20)

    report = subparsers.add_parser("report")
    report.add_argument("--trade-date", required=True)
    report.add_argument("--log-path", required=True)

    backtest_top20 = subparsers.add_parser("backtest-top20")
    backtest_top20.add_argument("--start-date", required=True)
    backtest_top20.add_argument("--end-date", required=True)
    backtest_top20.add_argument("--holding-days", required=True, type=parse_holding_days)
    backtest_top20.add_argument("--top-n", type=int, default=20)
    backtest_top20.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    portfolio_backtest = subparsers.add_parser("portfolio-backtest")
    portfolio_backtest.add_argument("--start-date", required=True)
    portfolio_backtest.add_argument("--end-date", required=True)
    portfolio_backtest.add_argument("--initial-cash", type=float, default=500000.0)
    portfolio_backtest.add_argument(
        "--top-ks",
        type=parse_top_ks,
        default="5,10",
    )
    portfolio_backtest.add_argument(
        "--holding-days",
        type=parse_holding_days,
        default="5,10,15,20,30",
    )
    portfolio_backtest.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    retention_backtest = subparsers.add_parser("retention-backtest")
    retention_backtest.add_argument("--start-date", required=True)
    retention_backtest.add_argument("--end-date", required=True)
    retention_backtest.add_argument("--initial-cash", type=float, default=500000.0)
    retention_backtest.add_argument(
        "--top-ks",
        type=parse_top_ks,
        default="5,10",
    )
    retention_backtest.add_argument(
        "--variant",
        choices=["v1", "v2", "v3.1", "v31"],
        default="v1",
    )
    retention_backtest.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )
    retention_backtest.add_argument(
        "--cache-dir",
        default="/Users/xiwei/stock_research/cache/v3_1",
    )

    v31_cache = subparsers.add_parser("build-v31-cache")
    v31_cache.add_argument("--start-date", required=True)
    v31_cache.add_argument("--end-date", required=True)
    v31_cache.add_argument(
        "--cache-dir",
        default="/Users/xiwei/stock_research/cache/v3_1",
    )
    v31_cache.add_argument(
        "--format",
        choices=["auto", "parquet", "csv"],
        default="auto",
    )

    build_factor_daily = subparsers.add_parser("build-factor-daily")
    build_factor_daily.add_argument("--trade-date", required=True)
    build_factor_daily.add_argument("--lookback-bars", type=int, default=130)
    build_factor_daily.add_argument("--industry-system", default="csrc")

    score_factor_daily = subparsers.add_parser("score-factor-daily")
    score_factor_daily.add_argument("--trade-date", required=True)
    score_factor_daily.add_argument("--score-version", default="manual_v1")

    show_top_scores = subparsers.add_parser("show-top-scores")
    show_top_scores.add_argument("--trade-date", required=True)
    show_top_scores.add_argument("--score-version", default="manual_v1")
    show_top_scores.add_argument("--top-n", type=int, default=30)

    eval_factor = subparsers.add_parser("eval-factor")
    eval_factor.add_argument("--factor-name", required=True)
    eval_factor.add_argument("--start-date", required=True)
    eval_factor.add_argument("--end-date", required=True)
    eval_factor.add_argument("--horizon", type=int, default=5)
    eval_factor.add_argument("--quantiles", type=int, default=5)
    eval_factor.add_argument("--top-n", type=int, default=30)

    daily_factor_pipeline = subparsers.add_parser("run-daily-factor-pipeline")
    daily_factor_pipeline.add_argument("--trade-date", required=True)
    daily_factor_pipeline.add_argument("--score-version", default="manual_v1")
    daily_factor_pipeline.add_argument("--top-n", type=int, default=30)
    daily_factor_pipeline.add_argument("--lookback-bars", type=int, default=130)
    daily_factor_pipeline.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "apply-schema":
        apply_schema()
        print("schema_applied")
    elif args.command == "apply-research-schema":
        apply_schema()
        print("research_schema_applied")
    elif args.command == "sync-assets":
        print(f"asset_master_synced|{sync_asset_master()}")
    elif args.command == "sync-core-assets":
        sync_core_asset_master_for_service()
        print("core_asset_master_synced")
    elif args.command == "build-asset-status":
        build_asset_status_daily_for_service(
            args.start_date,
            args.end_date,
            args.adjust_type,
        )
        print("core_asset_status_daily_built")
    elif args.command == "build-industry-bars":
        build_industry_daily_bars_for_service(
            start_date=args.start_date,
            end_date=args.end_date,
            industry_system=args.industry_system,
            adjust_type=args.adjust_type,
        )
        print("market_industry_daily_bars_built")
    elif args.command == "build-factor-daily":
        count = build_and_store_factor_daily(
            trade_date=args.trade_date,
            lookback_bars=args.lookback_bars,
            industry_system=args.industry_system,
        )
        print(f"factor_daily_stored|{count}")
    elif args.command == "score-factor-daily":
        count = score_stored_factor_daily(
            trade_date=args.trade_date,
            score_version=args.score_version,
        )
        print(f"stock_score_daily_stored|{count}")
    elif args.command == "show-top-scores":
        for row in load_top_scores(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
        ):
            print(
                f"top_score|{row['trade_date']}|{row['rank']}|"
                f"{row['asset_id']}|{row['score_total']}|{row['score_version']}"
            )
    elif args.command == "eval-factor":
        factors, returns = load_factor_eval_inputs(
            factor_name=args.factor_name,
            start_date=args.start_date,
            end_date=args.end_date,
            horizon=args.horizon,
        )
        result = generate_factor_eval_report(
            factors,
            returns,
            factor_name=args.factor_name,
            return_col=f"forward_return_{args.horizon}d",
            quantiles=args.quantiles,
            top_n=args.top_n,
        )
        print(f"factor_eval|{args.factor_name}|mean_ic|{result['ic_summary']['mean_ic']}")
        print(f"factor_eval|{args.factor_name}|ic_count|{result['ic_summary']['ic_count']}")
        print(
            f"factor_eval|{args.factor_name}|mean_rank_ic|"
            f"{result['rank_ic_summary']['mean_ic']}"
        )
    elif args.command == "run-daily-factor-pipeline":
        result = run_daily_factor_pipeline(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
            lookback_bars=args.lookback_bars,
            reports_dir=args.reports_dir,
        )
        print(f"daily_factor_pipeline|factor_rows|{result['factor_rows']}")
        print(f"daily_factor_pipeline|score_rows|{result['score_rows']}")
        print(f"daily_factor_pipeline|top_scores|{len(result['top_scores'])}")
    elif args.command == "sync-industry-memberships":
        count = sync_industry_memberships(args.trade_date)
        print(f"industry_memberships_synced|{count}")
    elif args.command == "sync-index-bars":
        count = sync_index_daily_bars(args.start_date, args.end_date)
        print(f"index_daily_bars_synced|{count}")
    elif args.command == "sync-baostock-finance":
        counts = sync_finance_for_period(
            args.year,
            args.quarter,
            limit=args.limit,
            offset=args.offset,
        )
        print(f"baostock_finance_assets|{counts['queried_assets']}")
        print(f"finance_indicator_quarter_synced|{counts['indicator_quarter']}")
        print(f"finance_income_statement_synced|{counts['income_statement']}")
        print(f"finance_share_capital_event_synced|{counts['share_capital_event']}")
    elif args.command == "create-ingest-jobs":
        count = create_ingest_jobs_for_service(
            args.dataset,
            start_year=args.start_year,
            end_year=args.end_year,
            batch_size=args.batch_size,
        )
        print(f"ingest_jobs_created|{args.dataset}|{count}")
    elif args.command == "run-ingest-jobs":
        result = run_ingest_jobs_for_service(
            args.dataset,
            limit_jobs=args.limit_jobs,
            progress=print_ingest_progress,
        )
        print(f"ingest_jobs_attempted|{result['attempted']}")
        print(f"ingest_jobs_success|{result['success']}")
        print(f"ingest_jobs_failed|{result['failed']}")
    elif args.command == "run-ingest-loop":
        def report(summary: dict) -> None:
            message = format_ingest_loop_report(summary)
            print(message, flush=True)
            send_openclaw_feishu_message(
                message=message,
                target=args.report_target,
                account=args.report_account,
                openclaw_bin=args.openclaw_bin,
                dry_run=args.report_dry_run,
            )

        result = run_ingest_loop_for_service(
            args.dataset,
            jobs_per_round=args.jobs_per_round,
            report=report,
            progress=print_ingest_progress,
            sleep_seconds=args.sleep_seconds,
            max_rounds=args.max_rounds,
        )
        print(f"ingest_loop_rounds|{result['rounds']}")
        print(f"ingest_loop_attempted|{result['attempted']}")
        print(f"ingest_loop_success|{result['success']}")
        print(f"ingest_loop_failed|{result['failed']}")
        print(f"ingest_loop_done|{result['done']}")
    elif args.command == "ingest-status":
        for row in ingest_status_for_service(args.dataset):
            print(f"ingest_status|{row['dataset']}|{row['status']}|{row['count']}")
    elif args.command == "load-bars":
        hfq = load_market_daily_bars(
            "stock_hfq",
            "hfq",
            args.start_date,
            args.end_date,
            args.limit_tables,
        )
        qfq = load_market_daily_bars(
            "stock_qfq",
            "qfq",
            args.start_date,
            args.end_date,
            args.limit_tables,
        )
        print(f"market_rows_loaded|hfq|{hfq}")
        print(f"market_rows_loaded|qfq|{qfq}")
    elif args.command == "quality":
        for result in run_daily_quality_checks(args.trade_date):
            print(
                f"quality|{result['check_name']}|"
                f"{result['status']}|{result['metric_value']}"
            )
    elif args.command == "features":
        print(f"features_stored|{compute_and_store_p0_features(args.trade_date)}")
    elif args.command == "labels":
        print(f"labels_stored|{compute_and_store_labels(args.end_date)}")
    elif args.command == "select":
        selections = generate_selection(args.trade_date, args.top_n)
        print(f"selection_stored|{store_selection(selections)}")
    elif args.command == "report":
        quality_results = run_daily_quality_checks(args.trade_date)
        selections = generate_selection(args.trade_date, 20)
        print(
            format_daily_report(
                args.trade_date,
                quality_results,
                selections,
                args.log_path,
            )
        )
    elif args.command == "backtest-top20":
        result = run_top20_backtest(
            args.start_date,
            args.end_date,
            holding_days=args.holding_days,
            top_n=args.top_n,
            reports_dir=args.reports_dir,
        )
        print(f"backtest_run|{result['run'].run_id}")
        print(f"backtest_report|{result['report_path']}")
        print(f"backtest_trades|{len(result['trades'])}")
    elif args.command == "portfolio-backtest":
        result = run_portfolio_backtest(
            args.start_date,
            args.end_date,
            initial_cash=args.initial_cash,
            top_ks=args.top_ks,
            holding_days=args.holding_days,
            reports_dir=args.reports_dir,
        )
        print(f"portfolio_backtest_report|{result['report_path']}")
        print(
            f"portfolio_backtest_summary|{result['report_paths']['summary_path']}"
        )
        print(f"portfolio_backtest_configs|{len(result['summary'])}")
    elif args.command == "retention-backtest":
        retention_kwargs = {
            "initial_cash": args.initial_cash,
            "top_ks": args.top_ks,
            "variant": args.variant,
            "reports_dir": args.reports_dir,
        }
        if str(args.variant).strip().lower() in {"v3.1", "v31"}:
            retention_kwargs["cache_dir"] = args.cache_dir
        result = run_retention_backtest(
            args.start_date,
            args.end_date,
            **retention_kwargs,
        )
        print(f"retention_backtest_report|{result['report_path']}")
        print(
            f"retention_backtest_summary|{result['report_paths']['summary_path']}"
        )
        print(f"retention_backtest_configs|{len(result['summary'])}")
    elif args.command == "build-v31-cache":
        result = build_v31_cache(
            start_date=args.start_date,
            end_date=args.end_date,
            cache_dir=args.cache_dir,
            output_format=args.format,
        )
        print(f"v31_cache_manifest|{result['paths']['manifest']}")
        print(f"v31_cache_candidates|{result['counts']['retention_candidates']}")


if __name__ == "__main__":
    main()
