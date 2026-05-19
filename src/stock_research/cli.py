import argparse
import json
import sys
from uuid import uuid4

from stock_research.assets import sync_asset_master
from stock_research.backtest import run_top20_backtest
from stock_research.backfill_runs import (
    backfill_status_for_service,
    claim_backfill_tasks_for_service,
    create_backfill_run_for_service,
    mark_backfill_task_failed_for_service,
    mark_backfill_task_success_for_service,
    reset_stale_backfill_tasks_for_service,
)
from stock_research.corporate_actions import (
    build_adjustment_factors_for_service,
    build_corporate_actions_from_factors_for_service,
)
from stock_research.core_data import (
    build_asset_status_daily_for_service,
    build_industry_daily_bars_for_service,
    sync_core_asset_master_for_service,
)
from stock_research.data_audit import format_audit_line, run_data_audit
from stock_research.dimensions import (
    seed_trading_calendar_from_bars,
    sync_asset_lifecycle_from_master,
)
from stock_research.finance_audit import format_finance_audit_line, summarize_finance_coverage
from stock_research.industry_history import (
    benchmark_industry_day,
    run_industry_history_range,
)
from stock_research.industry_focus_score import run_industry_focus_backtest_report
from stock_research.industry_focus_v2 import (
    run_industry_focus_v2_backtest,
    run_industry_focus_v2_diagnostics,
)
from stock_research.industry_factor_audit import (
    run_fixed_industry_reconciliation,
    run_industry_error_audit,
)
from stock_research.industry_mainline_regime import (
    run_industry_mainline_regime_diagnostics,
)
from stock_research.industry_regime_gated_backtest import (
    run_industry_regime_gated_backtest,
)
from stock_research.industry_exposure_risk_control import (
    run_industry_exposure_risk_control,
)
from stock_research.features import (
    compute_and_store_p0_features,
    compute_and_store_p0_features_range,
    derive_feature_backfill_window,
)
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.factor_backfill import (
    backfill_factor_daily_range,
    derive_factor_backfill_window,
)
from stock_research.approved_scoring_workflow import score_approved_factors_range
from stock_research.factor_config import candidate_factor_names
from stock_research.factor_pipeline import build_and_store_factor_daily
from stock_research.factor_eval_batch import run_factor_gate_batch
from stock_research.factor_eval.gate import decide_factor_gate
from stock_research.factor_eval.multi_horizon import generate_multi_horizon_report
from stock_research.factor_eval.report import generate_factor_eval_report
from stock_research.factor_eval_store import (
    load_factor_eval_inputs,
    load_multi_horizon_factor_eval_inputs,
    store_factor_approval,
    store_factor_eval_run,
)
from stock_research.factor_store import load_top_scores, score_stored_factor_daily
from stock_research.factor_gate_watchdog import run_factor_gate_batch_watchdog
from stock_research.daily_pipeline import run_daily_factor_pipeline
from stock_research.daily_incremental import (
    build_default_step_runners,
    check_market_data_freshness,
    run_daily_incremental_pipeline,
)
from stock_research.daily_job_run_store import (
    apply_daily_job_run_schema,
    record_daily_job_run,
)
from stock_research.daily_health import (
    format_operational_health_lines,
    summarize_operational_health,
)
from stock_research.dragon_strategy_research import run_dragon_research_v1
from stock_research.dragon_case_library import (
    apply_source_backfill,
    build_source_backfill_check_report,
    build_source_backfill_workpack,
    compare_source_backfill_curated,
    build_failure_event_rule_v21_curated_view,
    build_failure_event_rule_v21_transition_matrix,
    run_failure_event_rule_v2_diagnostics,
    run_dragon_case_expand_web_seeds,
    import_web_seeds,
    run_dragon_case_library_build,
    run_dragon_case_library_diagnose,
    run_dragon_case_web_verify,
)
from stock_research.ingest_jobs import (
    create_ingest_jobs_for_service,
    format_ingest_loop_report,
    ingest_status_for_service,
    reset_stale_ingest_jobs_for_service,
    run_ingest_loop_for_service,
    run_ingest_jobs_for_service,
)
from stock_research.labels import compute_and_store_labels, derive_label_backfill_window
from stock_research.lhb_data import (
    run_dragon_case_lhb_alignment_audit,
    run_dragon_case_lhb_summary_report,
    run_lhb_diagnostics_after_failure_rule_v21,
    run_lhb_coverage_and_failure_rule_plan,
    run_lhb_risk_feature_diagnostics,
    run_lhb_case_difference_report,
    run_lhb_event_features_build,
    run_lhb_sample_import,
)
from stock_research.loaders.baostock_ingestion import (
    sync_index_daily_bars,
    sync_index_constituents,
    sync_industry_memberships,
)
from stock_research.loaders.baostock_finance_ingestion import sync_finance_for_period
from stock_research.market_data import load_market_daily_bars
from stock_research.migration_safety import run_backup_restore_check
from stock_research.minute_backfill import (
    load_backfill_status,
    plan_baostock_minute_backfill,
    run_baostock_minute_backfill,
    run_baostock_minute_backfill_range,
    validate_minute_bars,
)
from stock_research.minute_backfill_watchdog import run_minute_backfill_watchdog
from stock_research.minute_data import sync_baostock_stock_minute_bars
from stock_research.portfolio_backtest import run_portfolio_backtest
from stock_research.quality import run_daily_quality_checks
from stock_research.reporting import format_daily_report
from stock_research.research_preflight import (
    check_factor_label_coverage,
    check_industry_membership_coverage,
    find_latest_common_label_date,
)
from stock_research.research_windows import load_market_date_bounds
from stock_research.reports.daily_research_report_cli import run_daily_research_report
from stock_research.retention_backtest import run_retention_backtest
from stock_research.research_snapshot_export import export_research_snapshot
from stock_research.schema import apply_schema
from stock_research.selection import generate_selection, store_selection
from stock_research.trend_candidate_backtest import run_trend_candidate_backtest_report
from stock_research.trend_candidate_enrichment import (
    run_entry_success_candidate_v2_report,
    run_entry_success_reverse_profile_report,
    run_candidate_enrichment_report,
    run_full_universe_candidate_enrichment_report,
)
from stock_research.trend_factor_profile import run_mid_trend_factor_profile_report
from stock_research.trend_lifecycle import run_trend_lifecycle_v1_report
from stock_research.technical_feature_store import (
    TECHNICAL_FEATURE_CALC_VERSION,
    build_and_store_stock_technical_features_daily,
)
from stock_research.technical_feature_promotion_audit import (
    run_technical_feature_promotion_audit,
)
from stock_research.technical_feature_backfill import (
    backfill_technical_features_daily_range,
    derive_technical_feature_backfill_window,
    run_technical_feature_backfill_benchmark,
)
from stock_research.technical_feature_audit import (
    run_technical_feature_gap_check,
)
from stock_research.technical_feature_watchdog import (
    run_technical_feature_backfill_watchdog,
)
from stock_research.technical_method_validation import run_validate_technical_methods
from stock_research.services.universe_service import (
    UniverseConfig,
    UniverseMember,
    UniverseService,
    get_universe_preset,
    load_watchlist_codes,
    write_universe_artifacts,
)
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


def parse_research_horizons(value: str) -> list[int]:
    return parse_int_list(value, "--horizons")


def parse_factor_names(value: str) -> list[str]:
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(part == "" for part in parts):
        raise argparse.ArgumentTypeError("--factor-names must not contain empty values")
    return parts


def parse_str_list(value: str, option_name: str) -> list[str]:
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(part == "" for part in parts):
        raise argparse.ArgumentTypeError(f"{option_name} must not contain empty values")
    return parts


def parse_exchanges(value: str) -> list[str]:
    return parse_str_list(value, "--exchanges")


def parse_index_ids(value: str) -> list[str]:
    return parse_str_list(value, "--index-ids")


def parse_adjust_types(value: str) -> list[str]:
    adjust_types = parse_str_list(value, "--adjust-types")
    allowed = {"raw", "qfq", "hfq"}
    invalid = [item for item in adjust_types if item not in allowed]
    if invalid:
        raise argparse.ArgumentTypeError(
            "--adjust-types values must be one of raw, qfq, hfq"
        )
    return adjust_types


def parse_ingest_datasets(value: str) -> list[str]:
    return parse_str_list(value, "--ingest-datasets")


def parse_backfill_run_ids(value: str) -> list[str]:
    return parse_str_list(value, "--backfill-run-ids")


def build_universe_config_from_args(
    args: argparse.Namespace,
    *,
    watchlist_codes: list[str] | None = None,
) -> UniverseConfig:
    overrides: dict[str, object] = {}
    if getattr(args, "min_listed_days", None) is not None:
        overrides["min_listed_days"] = int(args.min_listed_days)
    if getattr(args, "min_avg_turnover_amount", None) is not None:
        overrides["min_avg_turnover_amount"] = float(args.min_avg_turnover_amount)
    if getattr(args, "min_avg_volume", None) is not None:
        overrides["min_avg_volume"] = float(args.min_avg_volume)
    if getattr(args, "liquidity_lookback_days", None) is not None:
        overrides["liquidity_lookback_days"] = int(args.liquidity_lookback_days)
    if getattr(args, "max_suspended_days", None) is not None:
        overrides["max_suspended_days"] = int(args.max_suspended_days)
    return get_universe_preset(
        args.date,
        args.preset,
        watchlist_codes=watchlist_codes,
        **overrides,
    )


def build_universe_artifacts(
    *,
    result: object,
    output_dir: str,
) -> object:
    return write_universe_artifacts(result, output_dir)


def universe_member_to_json(member: UniverseMember) -> str:
    return json.dumps(
        {
            "trade_date": member.trade_date,
            "asset_id": member.asset_id,
            "stock_code": member.stock_code,
            "stock_name": member.stock_name,
            "board": member.board,
            "listed_days": member.listed_days,
            "is_st": member.is_st,
            "is_suspended": member.is_suspended,
            "avg_turnover_amount": member.avg_turnover_amount,
            "avg_volume": member.avg_volume,
            "industry": member.industry,
            "included": member.included,
            "include_reasons": member.include_reasons,
            "exclude_reasons": member.exclude_reasons,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


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


def add_minute_backfill_watchdog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    parser.add_argument(
        "--adjust-types",
        type=parse_adjust_types,
        default=["raw", "qfq"],
    )
    parser.add_argument("--max-jobs", type=int, default=1200)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--stale-after-minutes", type=int, default=20)
    parser.add_argument("--run-timeout-seconds", type=int, default=1800)
    parser.add_argument("--output-dir", default="outputs/research")
    parser.add_argument("--report-target", required=True)
    parser.add_argument("--report-account", default="jarvis")
    parser.add_argument("--openclaw-bin", default="openclaw")
    parser.add_argument("--report-dry-run", action="store_true")


def run_minute_backfill_watchdog_command(args: argparse.Namespace) -> None:
    result = run_minute_backfill_watchdog(
        start_date=args.start_date,
        end_date=args.end_date,
        freq=args.freq,
        adjust_types=args.adjust_types,
        max_jobs=args.max_jobs,
        workers=args.workers,
        stale_after_minutes=args.stale_after_minutes,
        run_timeout_seconds=args.run_timeout_seconds,
        report_target=args.report_target,
        report_account=args.report_account,
        openclaw_bin=args.openclaw_bin,
        report_dry_run=args.report_dry_run,
    )
    delta_success = (
        int(result["post_summary"]["success_jobs"])
        - int(result["pre_summary"]["success_jobs"])
    )
    print(f"minute_backfill_watchdog|action|{result['status']['watchdog_action']}")
    print(f"minute_backfill_watchdog|delta_success|{delta_success}")
    print(f"minute_backfill_watchdog|delta_rows|{result['run_result']['rows']}")


def add_technical_feature_watchdog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lookback-bars", type=int, default=260)
    parser.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    parser.add_argument("--source-data-version")
    parser.add_argument("--sleep-between-runs-seconds", type=float, default=0.0)


def add_factor_gate_watchdog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--factor-names", type=parse_factor_names)
    parser.add_argument("--validation-start-date")
    parser.add_argument("--horizons", default="5,10,20,60")
    parser.add_argument("--primary-horizon", type=int, default=5)
    parser.add_argument("--calc-version", default="v1")
    parser.add_argument("--score-version", default="manual_v1")
    parser.add_argument("--quantiles", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=30)


def run_technical_feature_watchdog_command(args: argparse.Namespace) -> None:
    result = run_technical_feature_backfill_watchdog(
        start_date=args.start_date,
        end_date=args.end_date,
        adjust_type=args.adjust_type,
        lookback_bars=args.lookback_bars,
        source_data_version=args.source_data_version,
        max_jobs=args.max_jobs,
        workers=args.workers,
        stale_after_minutes=args.stale_after_minutes,
        run_timeout_seconds=args.run_timeout_seconds,
        sleep_between_runs_seconds=args.sleep_between_runs_seconds,
        report_target=args.report_target,
        report_account=args.report_account,
        openclaw_bin=args.openclaw_bin,
        report_dry_run=args.report_dry_run,
    )
    delta_success = result["post_summary"].success_tasks - result["pre_summary"].success_tasks
    delta_rows = result["post_summary"].total_rows_written - result["pre_summary"].total_rows_written
    run_result = result.get("run_result", {})
    print(f"technical_feature_watchdog|action|{result['status'].watchdog_action}")
    print(f"technical_feature_watchdog|delta_success|{delta_success}")
    print(f"technical_feature_watchdog|delta_rows|{max(0, delta_rows)}")
    for key in (
        "batch_start_date",
        "batch_end_date",
        "batch_size_days",
        "worker_count",
        "compute_seconds",
        "sleep_between_runs_seconds",
        "rows_written",
        "days_per_hour",
        "rows_per_hour",
        "timed_out",
    ):
        print(f"technical_feature_watchdog|{key}|{run_result.get(key, '')}")


def run_factor_gate_watchdog_command(args: argparse.Namespace) -> None:
    horizons = [int(value.strip()) for value in args.horizons.split(",") if value.strip()]
    result = run_factor_gate_batch_watchdog(
        start_date=args.start_date,
        end_date=args.end_date,
        validation_start_date=args.validation_start_date,
        horizons=horizons,
        primary_horizon=args.primary_horizon,
        calc_version=args.calc_version,
        score_version=args.score_version,
        quantiles=args.quantiles,
        top_n=args.top_n,
        factor_names=args.factor_names,
        max_jobs=args.max_jobs,
        workers=args.workers,
        stale_after_minutes=args.stale_after_minutes,
        run_timeout_seconds=args.run_timeout_seconds,
        report_target=args.report_target,
        report_account=args.report_account,
        openclaw_bin=args.openclaw_bin,
        report_dry_run=args.report_dry_run,
    )
    delta_success = result["post_summary"].success_tasks - result["pre_summary"].success_tasks
    delta_rows = result["post_summary"].total_rows_written - result["pre_summary"].total_rows_written
    print(f"factor_gate_watchdog|action|{result['status'].watchdog_action}")
    print(f"factor_gate_watchdog|delta_success|{delta_success}")
    print(f"factor_gate_watchdog|delta_rows|{max(0, delta_rows)}")
    print(f"factor_gate_watchdog|work_remaining|{result['status'].work_remaining}")


def print_factor_backfill_progress(event: dict) -> None:
    if event["event"] == "start":
        print(
            "factor_daily_backfill|start|"
            f"{event['trade_date']}|{event['index']}|{event['total']}",
            flush=True,
        )
    elif event["event"] == "done":
        print(
            "factor_daily_backfill|done|"
            f"{event['trade_date']}|{event['index']}|{event['total']}|{event['factor_rows']}",
            flush=True,
        )


def factor_backfill_progress_printer(interval: int):
    progress_interval = max(1, int(interval))

    def print_progress(event: dict) -> None:
        if event["event"] == "done" and progress_interval > 1:
            index = int(event["index"])
            total = int(event["total"])
            if index % progress_interval != 0 and index != total:
                return
        if event["event"] == "start" and progress_interval > 1:
            return
        print_factor_backfill_progress(event)

    return print_progress


def print_technical_feature_backfill_progress(event: dict) -> None:
    if event["event"] == "start":
        print(
            "technical_feature_daily_backfill|start|"
            f"{event['trade_date']}|{event['index']}|{event['total']}",
            flush=True,
        )
    elif event["event"] == "done":
        print(
            "technical_feature_daily_backfill|done|"
            f"{event['trade_date']}|{event['index']}|{event['total']}|{event['feature_rows']}",
            flush=True,
        )


def technical_feature_backfill_progress_printer(interval: int):
    progress_interval = max(1, int(interval))

    def print_progress(event: dict) -> None:
        if event["event"] == "done" and progress_interval > 1:
            index = int(event["index"])
            total = int(event["total"])
            if index % progress_interval != 0 and index != total:
                return
        if event["event"] == "start" and progress_interval > 1:
            return
        print_technical_feature_backfill_progress(event)

    return print_progress


def summarize_multi_horizon_report(report: dict) -> dict:
    summaries = {}
    for horizon, horizon_report in report.get("reports", {}).items():
        summaries[str(horizon)] = {
            "ic_summary": horizon_report.get("ic_summary", {}),
            "rank_ic_summary": horizon_report.get("rank_ic_summary", {}),
        }
    return {
        "factor_name": report.get("factor_name"),
        "horizons": report.get("horizons", []),
        "reports": summaries,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-research")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("apply-schema")
    subparsers.add_parser("apply-research-schema")
    subparsers.add_parser("sync-assets")
    subparsers.add_parser("sync-core-assets")

    data_audit = subparsers.add_parser("data-audit")
    data_audit.add_argument("--expected-start-date", default="1990-12-01")

    subparsers.add_parser("finance-audit")

    seed_trading_calendar = subparsers.add_parser("seed-trading-calendar")
    seed_trading_calendar.add_argument("--start-date", required=True)
    seed_trading_calendar.add_argument("--end-date", required=True)
    seed_trading_calendar.add_argument("--exchanges", type=parse_exchanges, required=True)
    seed_trading_calendar.add_argument("--source-version", required=True)

    sync_asset_lifecycle = subparsers.add_parser("sync-asset-lifecycle")
    sync_asset_lifecycle.add_argument("--source-version", required=True)

    create_backfill = subparsers.add_parser("create-backfill-run")
    create_backfill.add_argument("--run-id", required=True)
    create_backfill.add_argument("--dataset", required=True)
    create_backfill.add_argument("--source", required=True)
    create_backfill.add_argument("--source-version", required=True)
    create_backfill.add_argument("--start-date", required=True)
    create_backfill.add_argument("--end-date", required=True)
    create_backfill.add_argument("--months-per-partition", type=int, default=1)

    backfill_status = subparsers.add_parser("backfill-status")
    backfill_status.add_argument("--run-id", required=True)

    claim_backfill = subparsers.add_parser("claim-backfill-tasks")
    claim_backfill.add_argument("--run-id", required=True)
    claim_backfill.add_argument("--limit", type=int, default=10)

    mark_backfill_success = subparsers.add_parser("mark-backfill-task-success")
    mark_backfill_success.add_argument("--task-id", required=True)
    mark_backfill_success.add_argument("--rows-read", required=True, type=int)
    mark_backfill_success.add_argument("--rows-written", required=True, type=int)

    mark_backfill_failed = subparsers.add_parser("mark-backfill-task-failed")
    mark_backfill_failed.add_argument("--task-id", required=True)
    mark_backfill_failed.add_argument("--error-message", required=True)

    reset_stale_backfill = subparsers.add_parser("reset-stale-backfill-tasks")
    reset_stale_backfill.add_argument("--dataset", required=True)
    reset_stale_backfill.add_argument("--older-than-minutes", type=int, default=60)

    asset_status = subparsers.add_parser("build-asset-status")
    asset_status.add_argument("--start-date")
    asset_status.add_argument("--end-date")
    asset_status.add_argument("--adjust-type", default="hfq")

    adjustment_factors = subparsers.add_parser("build-adjustment-factors")
    adjustment_factors.add_argument("--start-date")
    adjustment_factors.add_argument("--end-date")
    adjustment_factors.add_argument("--source-version", default="derived_market_daily_bar_v1")

    corporate_actions = subparsers.add_parser("build-corporate-actions")
    corporate_actions.add_argument("--start-date")
    corporate_actions.add_argument("--end-date")
    corporate_actions.add_argument("--source-version", default="derived_adjustment_factor_v1")
    corporate_actions.add_argument(
        "--factor-source-version",
        default="derived_market_daily_bar_v1",
    )

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

    index_constituents = subparsers.add_parser("sync-index-constituents")
    index_constituents.add_argument("--trade-date", required=True)
    index_constituents.add_argument("--index-ids", type=parse_index_ids)
    index_constituents.add_argument("--source-version", required=True)

    baostock_finance = subparsers.add_parser("sync-baostock-finance")
    baostock_finance.add_argument("--year", required=True, type=int)
    baostock_finance.add_argument("--quarter", required=True, type=int)
    baostock_finance.add_argument("--limit", type=int)
    baostock_finance.add_argument("--offset", type=int, default=0)

    baostock_minutes = subparsers.add_parser("sync-baostock-minute-bars")
    baostock_minutes.add_argument("--start-date", default="2024-01-01")
    baostock_minutes.add_argument("--end-date", required=True)
    baostock_minutes.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    baostock_minutes.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    baostock_minutes.add_argument("--limit-assets", type=int)
    baostock_minutes.add_argument("--sleep-seconds", type=float, default=0.0)

    plan_minute_backfill = subparsers.add_parser("plan-baostock-minute-backfill")
    plan_minute_backfill.add_argument("--start-date", required=True)
    plan_minute_backfill.add_argument("--end-date", required=True)
    plan_minute_backfill.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    plan_minute_backfill.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    plan_minute_backfill.add_argument("--batch-by", choices=["month"], default="month")
    plan_minute_backfill.add_argument("--output-dir", default="outputs/research")
    plan_minute_backfill.add_argument("--limit-assets", type=int)

    run_minute_backfill = subparsers.add_parser("run-baostock-minute-backfill")
    run_minute_backfill.add_argument("--start-date")
    run_minute_backfill.add_argument("--end-date")
    run_minute_backfill.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    run_minute_backfill.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    run_minute_backfill.add_argument("--batch-by", choices=["month"], default="month")
    run_minute_backfill.add_argument("--max-jobs", type=int, default=50)
    run_minute_backfill.add_argument("--retry-failed", action="store_true")
    run_minute_backfill.add_argument("--sleep-seconds", type=float, default=0.5)
    run_minute_backfill.add_argument("--workers", type=int, default=1)

    run_minute_backfill_range = subparsers.add_parser("run-baostock-minute-backfill-range")
    run_minute_backfill_range.add_argument("--start-date", required=True)
    run_minute_backfill_range.add_argument("--end-date", required=True)
    run_minute_backfill_range.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    run_minute_backfill_range.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    run_minute_backfill_range.add_argument("--batch-by", choices=["month"], default="month")
    run_minute_backfill_range.add_argument("--max-jobs", type=int, default=500)
    run_minute_backfill_range.add_argument("--retry-failed", action="store_true")
    run_minute_backfill_range.add_argument("--sleep-seconds", type=float, default=0.1)
    run_minute_backfill_range.add_argument("--workers", type=int, default=1)
    run_minute_backfill_range.add_argument("--output-dir", default="outputs/research")
    run_minute_backfill_range.add_argument("--limit-assets", type=int)
    run_minute_backfill_range.add_argument("--report-target", required=True)
    run_minute_backfill_range.add_argument("--report-account", default="jarvis")
    run_minute_backfill_range.add_argument("--openclaw-bin", default="openclaw")
    run_minute_backfill_range.add_argument("--report-dry-run", action="store_true")

    minute_backfill_watchdog = subparsers.add_parser("minute-backfill-watchdog")
    add_minute_backfill_watchdog_arguments(minute_backfill_watchdog)

    backfill_watchdog = subparsers.add_parser("backfill-watchdog")
    backfill_watchdog.add_argument(
        "--adapter",
        choices=["minute", "technical-features", "factor-gate"],
        required=True,
    )
    add_minute_backfill_watchdog_arguments(backfill_watchdog)
    add_technical_feature_watchdog_arguments(backfill_watchdog)
    add_factor_gate_watchdog_arguments(backfill_watchdog)

    status_minute_backfill = subparsers.add_parser("baostock-minute-backfill-status")
    status_minute_backfill.add_argument("--output-dir", default="outputs/research")

    validate_minutes = subparsers.add_parser("validate-minute-bars")
    validate_minutes.add_argument("--start-date", required=True)
    validate_minutes.add_argument("--end-date", required=True)
    validate_minutes.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    validate_minutes.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    validate_minutes.add_argument("--output-dir", default="outputs/research")
    validate_minutes.add_argument("--limit-rows", type=int)

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
    run_ingest_loop.add_argument("--workers", type=int, default=1)
    run_ingest_loop.add_argument("--report-target", required=True)
    run_ingest_loop.add_argument("--report-account", default="jarvis")
    run_ingest_loop.add_argument("--openclaw-bin", default="openclaw")
    run_ingest_loop.add_argument("--report-dry-run", action="store_true")

    ingest_status = subparsers.add_parser("ingest-status")
    ingest_status.add_argument("--dataset")

    reset_stale_ingest = subparsers.add_parser("reset-stale-ingest-jobs")
    reset_stale_ingest.add_argument("--dataset", required=True)
    reset_stale_ingest.add_argument("--older-than-minutes", type=int, default=60)

    load_bars = subparsers.add_parser("load-bars")
    load_bars.add_argument("--start-date")
    load_bars.add_argument("--end-date")
    load_bars.add_argument("--limit-tables", type=int)
    load_bars.add_argument("--archive-raw", action="store_true")

    quality = subparsers.add_parser("quality")
    quality.add_argument("--trade-date")

    features = subparsers.add_parser("features")
    features.add_argument("--trade-date", required=True)

    backfill_features = subparsers.add_parser("backfill-features")
    backfill_features.add_argument("--start-date")
    backfill_features.add_argument("--end-date")
    backfill_features.add_argument("--lookback-bars", type=int, default=120)
    backfill_features.add_argument("--adjust-type", default="hfq")
    backfill_features.add_argument("--workers", type=int, default=1)
    backfill_features.add_argument("--skip-complete", action="store_true")

    labels = subparsers.add_parser("labels")
    labels.add_argument("--end-date", required=True)

    backfill_labels = subparsers.add_parser("backfill-labels")
    backfill_labels.add_argument("--start-date")
    backfill_labels.add_argument("--end-date")
    backfill_labels.add_argument(
        "--horizons",
        type=parse_research_horizons,
        default=[5, 10, 20, 60],
    )
    backfill_labels.add_argument("--adjust-type", default="hfq")

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

    research_preflight = subparsers.add_parser("research-preflight")
    research_preflight.add_argument("--start-date")
    research_preflight.add_argument("--end-date")
    research_preflight.add_argument(
        "--horizons",
        type=parse_research_horizons,
        default=[5, 10, 20, 60],
    )
    research_preflight.add_argument("--factor-names", type=parse_factor_names)
    research_preflight.add_argument("--calc-version", default="v1")
    research_preflight.add_argument("--min-label-dates", type=int, default=20)
    research_preflight.add_argument("--require-industry-membership", action="store_true")

    benchmark_industry_day = subparsers.add_parser("benchmark-industry-day")
    benchmark_industry_day.add_argument("--trade-date", required=True)
    benchmark_industry_day.add_argument("--industry-system", default="csrc")
    benchmark_industry_day.add_argument("--adjust-type", default="hfq")
    benchmark_industry_day.add_argument(
        "--no-cache",
        dest="use_cache",
        action="store_false",
        default=True,
    )

    backfill_industry_history = subparsers.add_parser("backfill-industry-history")
    backfill_industry_history.add_argument("--start-date", required=True)
    backfill_industry_history.add_argument("--end-date", required=True)
    backfill_industry_history.add_argument("--max-dates", required=True, type=int)
    backfill_industry_history.add_argument(
        "--frequency",
        choices=["daily", "monthly", "quarterly"],
        default="daily",
    )
    backfill_industry_history.add_argument("--industry-system", default="csrc")
    backfill_industry_history.add_argument("--adjust-type", default="hfq")
    backfill_industry_history.add_argument(
        "--no-cache",
        dest="use_cache",
        action="store_false",
        default=True,
    )

    backfill_factor_daily = subparsers.add_parser("backfill-factor-daily")
    backfill_factor_daily.add_argument("--start-date")
    backfill_factor_daily.add_argument("--end-date")
    backfill_factor_daily.add_argument("--lookback-bars", type=int, default=130)
    backfill_factor_daily.add_argument("--industry-system", default="csrc")
    backfill_factor_daily.add_argument("--workers", type=int, default=1)
    backfill_factor_daily.add_argument("--skip-complete", action="store_true")
    backfill_factor_daily.add_argument("--progress-interval", type=int, default=1)
    backfill_factor_daily.add_argument("--exact-window", action="store_true")

    backfill_approved_scores = subparsers.add_parser("backfill-approved-scores")
    backfill_approved_scores.add_argument("--start-date")
    backfill_approved_scores.add_argument("--end-date")
    backfill_approved_scores.add_argument("--score-version", default="manual_v1")
    backfill_approved_scores.add_argument("--calc-version", default="v1")
    backfill_approved_scores.add_argument("--adjust-type", default="hfq")

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

    evaluate_factor_gate = subparsers.add_parser("evaluate-factor-gate")
    evaluate_factor_gate.add_argument("--factor-name", required=True)
    evaluate_factor_gate.add_argument("--start-date", required=True)
    evaluate_factor_gate.add_argument("--end-date", required=True)
    evaluate_factor_gate.add_argument("--horizons", default="5,10,20,60")
    evaluate_factor_gate.add_argument("--primary-horizon", type=int, default=5)
    evaluate_factor_gate.add_argument("--calc-version", default="v1")
    evaluate_factor_gate.add_argument("--score-version", default="manual_v1")
    evaluate_factor_gate.add_argument("--quantiles", type=int, default=5)
    evaluate_factor_gate.add_argument("--top-n", type=int, default=30)

    evaluate_factor_gate_batch = subparsers.add_parser("evaluate-factor-gate-batch")
    evaluate_factor_gate_batch.add_argument("--factor-names", type=parse_factor_names)
    evaluate_factor_gate_batch.add_argument("--start-date", required=True)
    evaluate_factor_gate_batch.add_argument("--end-date", required=True)
    evaluate_factor_gate_batch.add_argument("--validation-start-date")
    evaluate_factor_gate_batch.add_argument("--horizons", default="5,10,20,60")
    evaluate_factor_gate_batch.add_argument("--primary-horizon", type=int, default=5)
    evaluate_factor_gate_batch.add_argument("--calc-version", default="v1")
    evaluate_factor_gate_batch.add_argument("--score-version", default="manual_v1")
    evaluate_factor_gate_batch.add_argument("--quantiles", type=int, default=5)
    evaluate_factor_gate_batch.add_argument("--top-n", type=int, default=30)

    daily_factor_pipeline = subparsers.add_parser("run-daily-factor-pipeline")
    daily_factor_pipeline.add_argument("--trade-date", required=True)
    daily_factor_pipeline.add_argument("--score-version", default="manual_v1")
    daily_factor_pipeline.add_argument("--top-n", type=int, default=30)
    daily_factor_pipeline.add_argument("--lookback-bars", type=int, default=130)
    daily_factor_pipeline.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    technical_features_daily = subparsers.add_parser("build-technical-features-daily")
    technical_features_daily.add_argument("--trade-date", required=True)
    technical_features_daily.add_argument("--lookback-bars", type=int, default=260)
    technical_features_daily.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )

    backfill_technical_features_daily = subparsers.add_parser(
        "backfill-technical-features-daily"
    )
    backfill_technical_features_daily.add_argument("--start-date")
    backfill_technical_features_daily.add_argument("--end-date")
    backfill_technical_features_daily.add_argument("--lookback-bars", type=int, default=260)
    backfill_technical_features_daily.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    backfill_technical_features_daily.add_argument("--source-data-version")
    backfill_technical_features_daily.add_argument("--workers", type=int, default=1)
    backfill_technical_features_daily.add_argument("--skip-complete", action="store_true")
    backfill_technical_features_daily.add_argument("--progress-interval", type=int, default=1)

    benchmark_technical_feature_backfill = subparsers.add_parser(
        "benchmark-technical-feature-backfill"
    )
    benchmark_technical_feature_backfill.add_argument("--start-date", required=True)
    benchmark_technical_feature_backfill.add_argument("--end-date", required=True)
    benchmark_technical_feature_backfill.add_argument("--lookback-bars", type=int, default=260)
    benchmark_technical_feature_backfill.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    benchmark_technical_feature_backfill.add_argument(
        "--strategy",
        choices=["current", "parallel_dates"],
        default="current",
    )
    benchmark_technical_feature_backfill.add_argument("--workers", type=int, default=1)
    benchmark_technical_feature_backfill.add_argument("--bench-tag", required=True)

    technical_feature_gap_check = subparsers.add_parser("technical-feature-gap-check")
    technical_feature_gap_check.add_argument("--start-date", required=True)
    technical_feature_gap_check.add_argument("--end-date", required=True)
    technical_feature_gap_check.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    technical_feature_gap_check.add_argument(
        "--calc-version",
        default=TECHNICAL_FEATURE_CALC_VERSION,
    )
    technical_feature_gap_check.add_argument("--source-data-version")

    technical_feature_promotion_audit = subparsers.add_parser("technical-feature-promotion-audit")
    technical_feature_promotion_audit.add_argument("--start-date", required=True)
    technical_feature_promotion_audit.add_argument("--end-date", required=True)
    technical_feature_promotion_audit.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    technical_feature_promotion_audit.add_argument("--sample-size", type=int)
    technical_feature_promotion_audit.add_argument("--asset-id")
    technical_feature_promotion_audit.add_argument("--ts-code")
    technical_feature_promotion_audit.add_argument(
        "--feature-source",
        choices=["technical_table", "computed_on_fly"],
        default="technical_table",
    )
    technical_feature_promotion_audit.add_argument("--output-dir", required=True)

    daily_incremental = subparsers.add_parser("run-daily-incremental")
    daily_incremental.add_argument("--trade-date", required=True)
    daily_incremental.add_argument("--score-version", default="manual_v1")
    daily_incremental.add_argument("--top-n", type=int, default=30)
    daily_incremental.add_argument("--lookback-bars", type=int, default=130)
    daily_incremental.add_argument("--adjust-type", default="hfq")
    daily_incremental.add_argument("--source-service", default="stock_hfq")
    daily_incremental.add_argument("--industry-system", default="csrc")
    daily_incremental_resume = daily_incremental.add_mutually_exclusive_group()
    daily_incremental_resume.add_argument("--start-at")
    daily_incremental_resume.add_argument("--only-step")
    daily_incremental.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )
    daily_incremental.add_argument("--dry-run", action="store_true")
    daily_incremental.add_argument("--apply-daily-run-schema", action="store_true")
    daily_incremental.add_argument("--record-run", action="store_true")

    daily_health = subparsers.add_parser("daily-health")
    daily_health.add_argument("--trade-date", required=True)
    daily_health.add_argument("--ingest-datasets", type=parse_ingest_datasets)
    daily_health.add_argument("--backfill-run-ids", type=parse_backfill_run_ids)
    daily_health.add_argument("--stale-minutes", type=int, default=60)
    daily_health.add_argument("--notify-target")
    daily_health.add_argument("--notify-account", default="jarvis")
    daily_health.add_argument("--openclaw-bin", default="openclaw")
    daily_health.add_argument("--notify-dry-run", action="store_true")

    export_snapshot = subparsers.add_parser("export-research-snapshot")
    export_snapshot.add_argument("--start-date", required=True)
    export_snapshot.add_argument("--end-date", required=True)
    export_snapshot.add_argument("--score-version", default="manual_v1")
    export_snapshot.add_argument("--output-dir", required=True)

    migration_safety = subparsers.add_parser("migration-safety-check")
    migration_safety.add_argument("--backup-path", required=True)
    migration_safety.add_argument("--source-service", default="stock_research")
    migration_safety.add_argument("--restore-service")
    migration_safety.add_argument("--dry-run", action="store_true")

    daily_research_report = subparsers.add_parser("run-daily-research-report")
    daily_research_report.add_argument("--trade-date", required=True)
    daily_research_report.add_argument("--score-version", default="manual_v1")
    daily_research_report.add_argument("--top-n", type=int, default=30)
    daily_research_report.add_argument("--index-id", default="CSI300")
    daily_research_report.add_argument("--market-lookback-days", type=int, default=90)
    daily_research_report.add_argument("--industry-system", default="csrc")
    daily_research_report.add_argument("--sector-lookback-days", type=int, default=60)
    daily_research_report.add_argument("--positions-csv")
    daily_research_report.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )
    daily_research_report.add_argument("--apply-report-run-schema", action="store_true")
    daily_research_report.add_argument("--record-run", action="store_true")

    trend_lifecycle_v1 = subparsers.add_parser("trend-lifecycle-v1")
    trend_lifecycle_v1.add_argument("--start-date", required=True)
    trend_lifecycle_v1.add_argument("--end-date", required=True)
    trend_lifecycle_v1.add_argument("--score-version", default="manual_v1")
    trend_lifecycle_v1.add_argument("--top-n", type=int, default=20)
    trend_lifecycle_v1.add_argument("--adjust-type", default="hfq")
    trend_lifecycle_v1.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    mid_trend_factor_profile = subparsers.add_parser("mid-trend-factor-profile")
    mid_trend_factor_profile.add_argument("--start-date", required=True)
    mid_trend_factor_profile.add_argument("--end-date", required=True)
    mid_trend_factor_profile.add_argument("--lifecycle-samples-path", required=True)
    mid_trend_factor_profile.add_argument("--factor-names", type=parse_factor_names)
    mid_trend_factor_profile.add_argument("--period", default="Q")
    mid_trend_factor_profile.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    mid_trend_candidate_enrichment = subparsers.add_parser("mid-trend-candidate-enrichment")
    mid_trend_candidate_enrichment.add_argument("--start-date", required=True)
    mid_trend_candidate_enrichment.add_argument("--end-date", required=True)
    mid_trend_candidate_enrichment.add_argument("--candidate-rank-path", required=True)
    mid_trend_candidate_enrichment.add_argument("--entry-success-labels-path", required=True)
    mid_trend_candidate_enrichment.add_argument("--max-factors", type=int)
    mid_trend_candidate_enrichment.add_argument("--min-candidate-score", type=float, default=0.0)
    mid_trend_candidate_enrichment.add_argument("--quantiles", type=int, default=5)
    mid_trend_candidate_enrichment.add_argument("--top-ns", type=parse_top_ks, default=(20, 50, 100))
    mid_trend_candidate_enrichment.add_argument("--period", default="Q")
    mid_trend_candidate_enrichment.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    mid_trend_full_universe_enrichment = subparsers.add_parser(
        "mid-trend-full-universe-enrichment"
    )
    mid_trend_full_universe_enrichment.add_argument("--start-date", required=True)
    mid_trend_full_universe_enrichment.add_argument("--end-date", required=True)
    mid_trend_full_universe_enrichment.add_argument("--candidate-scores-path", required=True)
    mid_trend_full_universe_enrichment.add_argument("--adjust-type", default="hfq")
    mid_trend_full_universe_enrichment.add_argument("--quantiles", type=int, default=5)
    mid_trend_full_universe_enrichment.add_argument("--top-ns", type=parse_top_ks, default=(20, 50, 100))
    mid_trend_full_universe_enrichment.add_argument("--period", default="Q")
    mid_trend_full_universe_enrichment.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    entry_success_reverse_profile = subparsers.add_parser("entry-success-reverse-profile")
    entry_success_reverse_profile.add_argument("--start-date", required=True)
    entry_success_reverse_profile.add_argument("--end-date", required=True)
    entry_success_reverse_profile.add_argument("--entry-success-labels-path", required=True)
    entry_success_reverse_profile.add_argument("--factor-names", type=parse_factor_names)
    entry_success_reverse_profile.add_argument("--horizons", type=parse_research_horizons, default=(20, 40, 60))
    entry_success_reverse_profile.add_argument("--period", default="Q")
    entry_success_reverse_profile.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    entry_success_candidate_v2 = subparsers.add_parser("entry-success-candidate-v2")
    entry_success_candidate_v2.add_argument("--start-date", required=True)
    entry_success_candidate_v2.add_argument("--end-date", required=True)
    entry_success_candidate_v2.add_argument("--factor-rank-path", required=True)
    entry_success_candidate_v2.add_argument("--horizon", type=int, default=40)
    entry_success_candidate_v2.add_argument("--max-factors", type=int)
    entry_success_candidate_v2.add_argument("--min-candidate-score", type=float, default=0.0)
    entry_success_candidate_v2.add_argument("--min-sign-match-rate", type=float, default=0.6)
    entry_success_candidate_v2.add_argument("--adjust-type", default="hfq")
    entry_success_candidate_v2.add_argument("--quantiles", type=int, default=5)
    entry_success_candidate_v2.add_argument("--top-ns", type=parse_top_ks, default=(20, 50, 100))
    entry_success_candidate_v2.add_argument("--period", default="Q")
    entry_success_candidate_v2.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    trend_candidate_backtest = subparsers.add_parser("trend-candidate-backtest")
    trend_candidate_backtest.add_argument("--start-date", required=True)
    trend_candidate_backtest.add_argument("--end-date", required=True)
    trend_candidate_backtest.add_argument("--candidate-scores-path", required=True)
    trend_candidate_backtest.add_argument("--top-ns", type=parse_top_ks, default=(20, 50))
    trend_candidate_backtest.add_argument("--holding-days", type=parse_holding_days, default=(5, 10, 20))
    trend_candidate_backtest.add_argument("--transaction-cost-bps", type=float, default=20.0)
    trend_candidate_backtest.add_argument("--adjust-type", default="hfq")
    trend_candidate_backtest.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    industry_focus_backtest = subparsers.add_parser("industry-focus-backtest")
    industry_focus_backtest.add_argument("--start-date", required=True)
    industry_focus_backtest.add_argument("--end-date", required=True)
    industry_focus_backtest.add_argument("--top-n", type=int, default=20)
    industry_focus_backtest.add_argument("--dynamic-top-k", type=int, default=4)
    industry_focus_backtest.add_argument("--min-industry-stocks", type=int, default=20)
    industry_focus_backtest.add_argument("--industry-system", default="csrc")
    industry_focus_backtest.add_argument("--industry-level", type=int, default=1)
    industry_focus_backtest.add_argument("--adjust-type", default="hfq")
    industry_focus_backtest.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    industry_v1_attribution = subparsers.add_parser("industry-v1-attribution")
    industry_v1_attribution.add_argument("--start-date", required=True)
    industry_v1_attribution.add_argument("--end-date", required=True)
    industry_v1_attribution.add_argument("--min-industry-stocks", type=int, default=20)
    industry_v1_attribution.add_argument("--dynamic-top-k", type=int, default=4)
    industry_v1_attribution.add_argument("--industry-system", default="csrc")
    industry_v1_attribution.add_argument("--industry-level", type=int, default=1)
    industry_v1_attribution.add_argument("--adjust-type", default="hfq")
    industry_v1_attribution.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_focus_v2_diagnostics = subparsers.add_parser("industry-focus-v2-diagnostics")
    industry_focus_v2_diagnostics.add_argument("--start-date", required=True)
    industry_focus_v2_diagnostics.add_argument("--end-date", required=True)
    industry_focus_v2_diagnostics.add_argument("--min-industry-stocks", type=int, default=20)
    industry_focus_v2_diagnostics.add_argument("--dynamic-top-k", type=int, default=4)
    industry_focus_v2_diagnostics.add_argument("--industry-system", default="csrc")
    industry_focus_v2_diagnostics.add_argument("--industry-level", type=int, default=1)
    industry_focus_v2_diagnostics.add_argument("--adjust-type", default="hfq")
    industry_focus_v2_diagnostics.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_focus_v2_backtest = subparsers.add_parser("industry-focus-v2-backtest")
    industry_focus_v2_backtest.add_argument("--start-date", required=True)
    industry_focus_v2_backtest.add_argument("--end-date", required=True)
    industry_focus_v2_backtest.add_argument("--diagnostics-path", required=True)
    industry_focus_v2_backtest.add_argument("--top-n", type=int, default=20)
    industry_focus_v2_backtest.add_argument("--transaction-cost-bps", type=float, default=20.0)
    industry_focus_v2_backtest.add_argument("--industry-system", default="csrc")
    industry_focus_v2_backtest.add_argument("--industry-level", type=int, default=1)
    industry_focus_v2_backtest.add_argument("--adjust-type", default="hfq")
    industry_focus_v2_backtest.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_research_v1 = subparsers.add_parser("dragon-research-v1")
    dragon_research_v1.add_argument("--start-date", required=True)
    dragon_research_v1.add_argument("--end-date", required=True)
    dragon_research_v1.add_argument("--hot-industry-top-n", type=int, default=6)
    dragon_research_v1.add_argument("--adjust-type", default="hfq")
    dragon_research_v1.add_argument("--industry-system", default="csrc")
    dragon_research_v1.add_argument("--industry-level", type=int, default=1)
    dragon_research_v1.add_argument("--industry-diagnostics-path")
    dragon_research_v1.add_argument("--candidate-scores-path")
    dragon_research_v1.add_argument("--lifecycle-samples-path")
    dragon_research_v1.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_library_build = subparsers.add_parser("dragon-case-library-build")
    dragon_case_library_build.add_argument("--start-date", required=True)
    dragon_case_library_build.add_argument("--end-date", required=True)
    dragon_case_library_build.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    dragon_case_library_build.add_argument(
        "--seed-path",
        default="/Users/xiwei/stock_research/data/seed/dragon_case_seed.csv",
    )
    dragon_case_library_build.add_argument("--adjust-type", default="hfq")

    dragon_case_library_diagnose = subparsers.add_parser("dragon-case-library-diagnose")
    dragon_case_library_diagnose.add_argument("--case-path", required=True)
    dragon_case_library_diagnose.add_argument("--start-date", required=True)
    dragon_case_library_diagnose.add_argument("--end-date", required=True)
    dragon_case_library_diagnose.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    dragon_case_library_diagnose.add_argument("--adjust-type", default="hfq")

    dragon_case_import_web_seeds = subparsers.add_parser("dragon-case-import-web-seeds")
    dragon_case_import_web_seeds.add_argument("--input", required=True)
    dragon_case_import_web_seeds.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_expand_web_seeds = subparsers.add_parser("dragon-case-expand-web-seeds")
    dragon_case_expand_web_seeds.add_argument("--article-seed", required=True)
    dragon_case_expand_web_seeds.add_argument("--output", required=True)
    dragon_case_expand_web_seeds.add_argument("--start-date", required=True)
    dragon_case_expand_web_seeds.add_argument("--end-date", required=True)
    dragon_case_expand_web_seeds.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_web_verify = subparsers.add_parser("dragon-case-web-verify")
    dragon_case_web_verify.add_argument("--candidate-path", required=True)
    dragon_case_web_verify.add_argument("--start-date", required=True)
    dragon_case_web_verify.add_argument("--end-date", required=True)
    dragon_case_web_verify.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    dragon_case_web_verify.add_argument("--adjust-type", default="hfq")

    dragon_case_apply_source_backfill = subparsers.add_parser("dragon-case-apply-source-backfill")
    dragon_case_apply_source_backfill.add_argument("--tasks-path", required=True)
    dragon_case_apply_source_backfill.add_argument(
        "--article-seed",
        default="/Users/xiwei/stock_research/data/seed/dragon_case_web_article_seed_2024_2026.csv",
    )
    dragon_case_apply_source_backfill.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    dragon_case_apply_source_backfill.add_argument("--dry-run", action="store_true")

    dragon_case_source_backfill_compare = subparsers.add_parser("dragon-case-source-backfill-compare")
    dragon_case_source_backfill_compare.add_argument("--before-curated", required=True)
    dragon_case_source_backfill_compare.add_argument("--after-curated", required=True)
    dragon_case_source_backfill_compare.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_source_backfill_workpack = subparsers.add_parser("dragon-case-source-backfill-workpack")
    dragon_case_source_backfill_workpack.add_argument("--tasks-path", required=True)
    dragon_case_source_backfill_workpack.add_argument("--top-n", type=int, default=20)
    dragon_case_source_backfill_workpack.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_source_backfill_check = subparsers.add_parser("dragon-case-source-backfill-check")
    dragon_case_source_backfill_check.add_argument("--apply-summary", required=True)
    dragon_case_source_backfill_check.add_argument("--delta-summary", required=True)
    dragon_case_source_backfill_check.add_argument("--curated", required=True)
    dragon_case_source_backfill_check.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_failure_event_rules_v2 = subparsers.add_parser("dragon-case-failure-event-rules-v2")
    dragon_case_failure_event_rules_v2.add_argument(
        "--case-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_curated_library_2024_2026.csv",
    )
    dragon_case_failure_event_rules_v2.add_argument(
        "--snapshot-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_factor_snapshot_2024_2026.csv",
    )
    dragon_case_failure_event_rules_v2.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    validate_technical_methods = subparsers.add_parser("validate-technical-methods")
    validate_technical_methods.add_argument("--start-date", required=True)
    validate_technical_methods.add_argument("--end-date", required=True)
    validate_technical_methods.add_argument("--adjust-type", default="qfq")
    validate_technical_methods.add_argument("--sample-size", type=int)
    validate_technical_methods.add_argument("--asset-id")
    validate_technical_methods.add_argument("--ts-code")
    validate_technical_methods.add_argument("--feature-source", default="technical_table")
    validate_technical_methods.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_risk_diagnostics_after_failure_rule_v21 = subparsers.add_parser(
        "lhb-risk-diagnostics-after-failure-rule-v2-1"
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--case-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_curated_library_2024_2026.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--failure-audit-path",
        default="/Users/xiwei/stock_research/outputs/research/failure_event_rule_v2_audit.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--snapshot-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_factor_snapshot_2024_2026.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--lhb-features-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_event_features_daily_sample.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--alignment-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_lhb_alignment_audit_2024_2026.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_sample_import = subparsers.add_parser("lhb-sample-import")
    lhb_sample_import.add_argument("--start-date", required=True)
    lhb_sample_import.add_argument("--end-date", required=True)
    lhb_sample_import.add_argument("--ts-codes")
    lhb_sample_import.add_argument("--provider", default="tushare")
    lhb_sample_import.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_event_features_build = subparsers.add_parser("lhb-build-event-features")
    lhb_event_features_build.add_argument("--start-date", required=True)
    lhb_event_features_build.add_argument("--end-date", required=True)
    lhb_event_features_build.add_argument("--ts-codes")
    lhb_event_features_build.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_lhb_alignment = subparsers.add_parser("dragon-case-lhb-alignment-audit")
    dragon_case_lhb_alignment.add_argument("--curated-path", required=True)
    dragon_case_lhb_alignment.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_lhb_summary = subparsers.add_parser("dragon-case-lhb-summary")
    dragon_case_lhb_summary.add_argument("--curated-path", required=True)
    dragon_case_lhb_summary.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_case_difference_report = subparsers.add_parser("lhb-case-difference-report")
    lhb_case_difference_report.add_argument("--case-path", required=True)
    lhb_case_difference_report.add_argument("--lhb-features-path", required=True)
    lhb_case_difference_report.add_argument("--alignment-path", required=True)
    lhb_case_difference_report.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_risk_feature_diagnostics = subparsers.add_parser("lhb-risk-feature-diagnostics")
    lhb_risk_feature_diagnostics.add_argument("--case-path", required=True)
    lhb_risk_feature_diagnostics.add_argument("--lhb-features-path", required=True)
    lhb_risk_feature_diagnostics.add_argument("--alignment-path", required=True)
    lhb_risk_feature_diagnostics.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_coverage_failure_plan = subparsers.add_parser("lhb-coverage-failure-plan")
    lhb_coverage_failure_plan.add_argument(
        "--coverage-gap-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_coverage_gap_recommendations.csv",
    )
    lhb_coverage_failure_plan.add_argument(
        "--case-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_curated_library_2024_2026.csv",
    )
    lhb_coverage_failure_plan.add_argument(
        "--snapshot-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_factor_snapshot_2024_2026.csv",
    )
    lhb_coverage_failure_plan.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    fixed_industry_reconciliation = subparsers.add_parser(
        "fixed-industry-reconciliation"
    )
    fixed_industry_reconciliation.add_argument("--start-date", required=True)
    fixed_industry_reconciliation.add_argument("--end-date", required=True)
    fixed_industry_reconciliation.add_argument("--top-n", type=int, default=20)
    fixed_industry_reconciliation.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=20.0,
    )
    fixed_industry_reconciliation.add_argument("--industry-system", default="csrc")
    fixed_industry_reconciliation.add_argument("--industry-level", type=int, default=1)
    fixed_industry_reconciliation.add_argument("--adjust-type", default="hfq")
    fixed_industry_reconciliation.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_error_audit = subparsers.add_parser("industry-error-audit")
    industry_error_audit.add_argument("--diagnostics-path", required=True)
    industry_error_audit.add_argument("--start-date", required=True)
    industry_error_audit.add_argument("--end-date", required=True)
    industry_error_audit.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    industry_error_audit.add_argument(
        "--backtest-summary-path",
        default="/Users/xiwei/stock_research/outputs/research/industry_focus_score_v2_backtest_summary.csv",
    )
    industry_error_audit.add_argument(
        "--annual-metrics-path",
        default="/Users/xiwei/stock_research/outputs/research/industry_focus_score_v2_backtest_annual_metrics.csv",
    )

    industry_mainline_regime = subparsers.add_parser(
        "industry-mainline-regime-diagnostics"
    )
    industry_mainline_regime.add_argument("--diagnostics-path", required=True)
    industry_mainline_regime.add_argument("--start-date", required=True)
    industry_mainline_regime.add_argument("--end-date", required=True)
    industry_mainline_regime.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_regime_gated_backtest = subparsers.add_parser(
        "industry-regime-gated-backtest"
    )
    industry_regime_gated_backtest.add_argument("--start-date", required=True)
    industry_regime_gated_backtest.add_argument("--end-date", required=True)
    industry_regime_gated_backtest.add_argument("--diagnostics-path", required=True)
    industry_regime_gated_backtest.add_argument("--regime-path", required=True)
    industry_regime_gated_backtest.add_argument("--mainline-path", required=True)
    industry_regime_gated_backtest.add_argument("--top-n", type=int, default=20)
    industry_regime_gated_backtest.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=20.0,
    )
    industry_regime_gated_backtest.add_argument("--industry-system", default="csrc")
    industry_regime_gated_backtest.add_argument("--industry-level", type=int, default=1)
    industry_regime_gated_backtest.add_argument("--adjust-type", default="hfq")
    industry_regime_gated_backtest.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_exposure_risk_control = subparsers.add_parser(
        "industry-exposure-risk-control"
    )
    industry_exposure_risk_control.add_argument("--start-date", required=True)
    industry_exposure_risk_control.add_argument("--end-date", required=True)
    industry_exposure_risk_control.add_argument("--diagnostics-path", required=True)
    industry_exposure_risk_control.add_argument("--regime-path", required=True)
    industry_exposure_risk_control.add_argument("--mainline-path", required=True)
    industry_exposure_risk_control.add_argument("--top-n", type=int, default=20)
    industry_exposure_risk_control.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=20.0,
    )
    industry_exposure_risk_control.add_argument("--industry-system", default="csrc")
    industry_exposure_risk_control.add_argument("--industry-level", type=int, default=1)
    industry_exposure_risk_control.add_argument("--adjust-type", default="hfq")
    industry_exposure_risk_control.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    build_universe = subparsers.add_parser("build-universe")
    build_universe.add_argument("--date", required=True)
    build_universe.add_argument("--preset", default="research_default")
    build_universe.add_argument("--output", required=True)
    build_universe.add_argument("--min-listed-days", type=int)
    build_universe.add_argument("--min-avg-turnover-amount", type=float)
    build_universe.add_argument("--min-avg-volume", type=float)
    build_universe.add_argument("--liquidity-lookback-days", type=int)
    build_universe.add_argument("--max-suspended-days", type=int)

    explain_universe = subparsers.add_parser("explain-universe")
    explain_universe.add_argument("--date", required=True)
    explain_universe.add_argument("--code", required=True)
    explain_universe.add_argument("--preset", default="research_default")
    explain_universe.add_argument("--min-listed-days", type=int)
    explain_universe.add_argument("--min-avg-turnover-amount", type=float)
    explain_universe.add_argument("--min-avg-volume", type=float)
    explain_universe.add_argument("--liquidity-lookback-days", type=int)
    explain_universe.add_argument("--max-suspended-days", type=int)

    check_watchlist_universe = subparsers.add_parser("check-watchlist-universe")
    check_watchlist_universe.add_argument("--date", required=True)
    check_watchlist_universe.add_argument("--watchlist", required=True)
    check_watchlist_universe.add_argument("--preset", default="watchlist_check")
    check_watchlist_universe.add_argument("--output", required=True)
    check_watchlist_universe.add_argument("--min-listed-days", type=int)
    check_watchlist_universe.add_argument("--min-avg-turnover-amount", type=float)
    check_watchlist_universe.add_argument("--min-avg-volume", type=float)
    check_watchlist_universe.add_argument("--liquidity-lookback-days", type=int)
    check_watchlist_universe.add_argument("--max-suspended-days", type=int)

    return parser


def main_for_args(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

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
    elif args.command == "data-audit":
        for row in run_data_audit(expected_start_date=args.expected_start_date):
            print(format_audit_line(row))
    elif args.command == "finance-audit":
        for row in summarize_finance_coverage():
            print(format_finance_audit_line(row))
    elif args.command == "seed-trading-calendar":
        count = seed_trading_calendar_from_bars(
            start_date=args.start_date,
            end_date=args.end_date,
            exchanges=args.exchanges,
            source_version=args.source_version,
        )
        print(f"trading_calendar_seeded|rows|{count}")
    elif args.command == "sync-asset-lifecycle":
        count = sync_asset_lifecycle_from_master(source_version=args.source_version)
        print(f"asset_lifecycle_synced|rows|{count}")
    elif args.command == "create-backfill-run":
        result = create_backfill_run_for_service(
            run_id=args.run_id,
            dataset=args.dataset,
            source=args.source,
            source_version=args.source_version,
            start_date=args.start_date,
            end_date=args.end_date,
            months_per_partition=args.months_per_partition,
        )
        print(
            "backfill_run_created|"
            f"{result['run_id']}|{result['dataset']}|tasks|{result['task_count']}"
        )
    elif args.command == "backfill-status":
        result = backfill_status_for_service(run_id=args.run_id)
        for status, count in sorted(result["counts"].items()):
            print(f"backfill_status|{result['run_id']}|{status}|{count}")
    elif args.command == "claim-backfill-tasks":
        rows = claim_backfill_tasks_for_service(run_id=args.run_id, limit=args.limit)
        for row in rows:
            print(
                "backfill_task_claimed|"
                f"{row['task_id']}|{row['partition_key']}|"
                f"{str(row['start_date'])[:10]}|{str(row['end_date'])[:10]}"
            )
    elif args.command == "mark-backfill-task-success":
        mark_backfill_task_success_for_service(
            task_id=args.task_id,
            rows_read=args.rows_read,
            rows_written=args.rows_written,
        )
        print(f"backfill_task_success|{args.task_id}|{args.rows_read}|{args.rows_written}")
    elif args.command == "mark-backfill-task-failed":
        mark_backfill_task_failed_for_service(
            task_id=args.task_id,
            error_message=args.error_message,
        )
        print(f"backfill_task_failed|{args.task_id}|{args.error_message}")
    elif args.command == "reset-stale-backfill-tasks":
        count = reset_stale_backfill_tasks_for_service(
            dataset=args.dataset,
            older_than_minutes=args.older_than_minutes,
        )
        print(f"backfill_task_stale_reset|{args.dataset}|{count}")
    elif args.command == "build-asset-status":
        build_asset_status_daily_for_service(
            args.start_date,
            args.end_date,
            args.adjust_type,
        )
        print("core_asset_status_daily_built")
    elif args.command == "build-adjustment-factors":
        build_adjustment_factors_for_service(
            start_date=args.start_date,
            end_date=args.end_date,
            source_version=args.source_version,
        )
        print("adjustment_factors_built")
    elif args.command == "build-corporate-actions":
        build_corporate_actions_from_factors_for_service(
            start_date=args.start_date,
            end_date=args.end_date,
            source_version=args.source_version,
            factor_source_version=args.factor_source_version,
        )
        print("corporate_actions_built")
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
    elif args.command == "research-preflight":
        horizons = args.horizons
        start_date = args.start_date
        if start_date is None:
            bounds = load_market_date_bounds()
            start_date = bounds["start_date"]
        if start_date is None:
            print("research_preflight|latest_common_label_date||0")
            print("research_preflight|coverage|blocked|factor_dates|0|complete_factor_dates|0")
            print(
                "research_preflight|missing_horizons|"
                + ",".join(str(value) for value in horizons)
            )
            print("research_preflight|short_label_horizons|")
            return
        latest = find_latest_common_label_date(
            start_date=start_date,
            horizons=horizons,
        )
        end_date = args.end_date or latest["latest_common_date"]
        if end_date is None:
            print(f"research_preflight|latest_common_label_date||{latest['date_count']}")
            print("research_preflight|coverage|blocked|factor_dates|0|complete_factor_dates|0")
            print(
                "research_preflight|missing_horizons|"
                + ",".join(str(value) for value in horizons)
            )
            print("research_preflight|short_label_horizons|")
            return
        factors = args.factor_names if args.factor_names else candidate_factor_names()
        coverage = check_factor_label_coverage(
            factor_names=factors,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            calc_version=args.calc_version,
            min_label_dates=args.min_label_dates,
        )
        print(
            "research_preflight|latest_common_label_date|"
            f"{latest['latest_common_date']}|{latest['date_count']}"
        )
        print(
            "research_preflight|coverage|"
            f"{coverage['status']}|factor_dates|{coverage['factor_date_count']}|"
            f"complete_factor_dates|{coverage['factor_complete_date_count']}"
        )
        print(
            "research_preflight|missing_horizons|"
            + ",".join(str(value) for value in coverage["missing_horizons"])
        )
        print(
            "research_preflight|short_label_horizons|"
            + ",".join(str(value) for value in coverage["short_label_horizons"])
        )
        if args.require_industry_membership:
            if end_date is None:
                print("research_preflight|industry_membership|blocked|market_rows|0|covered_rows|0|missing_rows|0")
            else:
                industry = check_industry_membership_coverage(
                    start_date=start_date,
                    end_date=end_date,
                    industry_system="csrc",
                    adjust_type="hfq",
                )
                print(
                    "research_preflight|industry_membership|"
                    f"{industry['status']}|market_rows|{industry['market_rows']}|"
                    f"covered_rows|{industry['covered_rows']}|missing_rows|{industry['missing_rows']}"
                )
    elif args.command == "backfill-factor-daily":
        if args.exact_window:
            window = {
                "start_date": args.start_date,
                "end_date": args.end_date,
                "date_count": 0,
            }
        else:
            window = derive_factor_backfill_window(
                start_date=args.start_date,
                end_date=args.end_date,
                lookback_bars=args.lookback_bars,
                industry_system=args.industry_system,
            )
        if window["start_date"] is None or window["end_date"] is None:
            print("factor_daily_backfill|dates|0")
            print("factor_daily_backfill|rows|0")
            return
        result = backfill_factor_daily_range(
            start_date=str(window["start_date"]),
            end_date=str(window["end_date"]),
            lookback_bars=args.lookback_bars,
            industry_system=args.industry_system,
            workers=args.workers,
            skip_complete=args.skip_complete,
            progress=factor_backfill_progress_printer(args.progress_interval),
        )
        total = int(result["factor_rows"].sum()) if not result.empty else 0
        print(f"factor_daily_backfill|dates|{len(result)}")
        print(f"factor_daily_backfill|rows|{total}")
    elif args.command == "backfill-approved-scores":
        bounds = load_market_date_bounds(adjust_type=args.adjust_type)
        start_date = args.start_date or bounds["start_date"]
        end_date = args.end_date or bounds["end_date"]
        if start_date is None or end_date is None:
            print("approved_score_backfill|dates|0")
            print("approved_score_backfill|rows|0")
            return
        result = score_approved_factors_range(
            start_date=str(start_date),
            end_date=str(end_date),
            score_version=args.score_version,
            calc_version=args.calc_version,
            adjust_type=args.adjust_type,
        )
        total = int(result["score_rows"].sum()) if not result.empty else 0
        print(f"approved_score_backfill|start_date|{start_date}")
        print(f"approved_score_backfill|end_date|{end_date}")
        print(f"approved_score_backfill|dates|{len(result)}")
        print(f"approved_score_backfill|rows|{total}")
    elif args.command == "score-factor-daily":
        count = score_stored_factor_daily(
            trade_date=args.trade_date,
            score_version=args.score_version,
            approved_only=True,
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
    elif args.command == "evaluate-factor-gate":
        horizons = [int(value.strip()) for value in args.horizons.split(",") if value.strip()]
        factors, returns = load_multi_horizon_factor_eval_inputs(
            factor_name=args.factor_name,
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=horizons,
            calc_version=args.calc_version,
        )
        multi_horizon_report = generate_multi_horizon_report(
            factors=factors,
            returns=returns,
            factor_name=args.factor_name,
            horizons=horizons,
            quantiles=args.quantiles,
            top_n=args.top_n,
        )
        decision = decide_factor_gate(
            factor_name=args.factor_name,
            multi_horizon_report=multi_horizon_report,
            primary_horizon=args.primary_horizon,
        )
        run_id = f"factor-eval-{uuid4().hex}"
        store_factor_eval_run(
            run_id=run_id,
            factor_name=args.factor_name,
            calc_version=args.calc_version,
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=horizons,
            primary_horizon=args.primary_horizon,
            status=decision["status"],
            reason=decision["reason"],
            metrics={
                "decision": decision,
                "multi_horizon": summarize_multi_horizon_report(multi_horizon_report),
            },
        )
        store_factor_approval(
            factor_name=args.factor_name,
            calc_version=args.calc_version,
            score_version=args.score_version,
            status=decision["status"],
            reason=decision["reason"],
            eval_run_id=run_id,
        )
        print(
            f"factor_gate|{args.factor_name}|{decision['status']}|"
            f"{decision['reason']}|{decision['primary_horizon']}"
        )
    elif args.command == "evaluate-factor-gate-batch":
        result = run_factor_gate_batch(
            factor_names=args.factor_names,
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=[int(value.strip()) for value in args.horizons.split(",") if value.strip()],
            primary_horizon=args.primary_horizon,
            calc_version=args.calc_version,
            score_version=args.score_version,
            quantiles=args.quantiles,
            top_n=args.top_n,
            validation_start_date=args.validation_start_date,
        )
        for row in result.to_dict("records"):
            print(
                "factor_gate_batch|"
                f"{row['factor_name']}|{row['status']}|{row['reason']}|"
                f"{row['primary_horizon']}|{row['eval_run_id']}"
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
    elif args.command == "build-technical-features-daily":
        count = build_and_store_stock_technical_features_daily(
            trade_date=args.trade_date,
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
            build_strategy=args.build_strategy,
        )
        print(f"technical_features_daily_stored|{count}")
    elif args.command == "backfill-technical-features-daily":
        window = derive_technical_feature_backfill_window(
            start_date=args.start_date,
            end_date=args.end_date,
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
        )
        start_date = args.start_date or window["start_date"]
        end_date = args.end_date or window["end_date"]
        if start_date is None or end_date is None:
            print("technical_feature_daily_backfill|dates|0")
            print("technical_feature_daily_backfill|rows|0")
            return
        result = backfill_technical_features_daily_range(
            start_date=str(start_date),
            end_date=str(end_date),
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
            source_data_version=args.source_data_version,
            workers=args.workers,
            skip_complete=args.skip_complete,
            build_strategy=args.build_strategy,
            progress=technical_feature_backfill_progress_printer(args.progress_interval),
        )
        total = int(result["feature_rows"].sum()) if not result.empty else 0
        print(f"technical_feature_daily_backfill|dates|{len(result)}")
        print(f"technical_feature_daily_backfill|rows|{total}")
    elif args.command == "benchmark-technical-feature-backfill":
        result = run_technical_feature_backfill_benchmark(
            start_date=args.start_date,
            end_date=args.end_date,
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
            workers=args.workers,
            strategy=args.strategy,
            bench_tag=args.bench_tag,
        )
        print(f"technical_feature_benchmark|strategy|{result['strategy']}")
        print(f"technical_feature_benchmark|workers|{result['workers']}")
        print(f"technical_feature_benchmark|bench_tag|{result['bench_tag']}")
        print(
            "technical_feature_benchmark|source_data_version|"
            f"{result['source_data_version']}"
        )
        print(f"technical_feature_benchmark|dates|{result['dates']}")
        print(f"technical_feature_benchmark|rows|{result['rows']}")
        print(
            "technical_feature_benchmark|elapsed_seconds|"
            f"{result['elapsed_seconds']}"
        )
        print(
            "technical_feature_benchmark|rows_per_second|"
            f"{result['rows_per_second']}"
        )
        print(
            "technical_feature_benchmark|dates_per_second|"
            f"{result['dates_per_second']}"
        )
    elif args.command == "technical-feature-gap-check":
        result = run_technical_feature_gap_check(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            calc_version=args.calc_version,
            source_data_version=args.source_data_version,
        )
        for row in result.get("dates", []):
            if not row.get("has_gap"):
                continue
            print(
                "technical_feature_gap_check|date|"
                f"{row['trade_date']}|"
                f"market_assets={int(row['market_assets'])}|"
                f"feature_rows={int(row['feature_rows'])}|"
                f"missing={int(row['missing'])}|"
                f"stale={int(row['stale'])}"
            )
        summary = result.get("summary", {})
        print(
            "technical_feature_gap_check|summary|"
            f"dates={int(summary.get('dates') or 0)}|"
            f"dates_with_gaps={int(summary.get('dates_with_gaps') or 0)}"
        )
    elif args.command == "run-daily-incremental":
        if args.apply_daily_run_schema:
            apply_daily_job_run_schema()
        recorder = None
        if args.record_run:
            recorder = lambda step: record_daily_job_run(
                trade_date=args.trade_date,
                step=step["step"],
                status=step["status"],
                metadata=step.get("result") or {},
                error_message=step.get("error"),
            )
        result = run_daily_incremental_pipeline(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
            lookback_bars=args.lookback_bars,
            reports_dir=args.reports_dir,
            adjust_type=args.adjust_type,
            source_service=args.source_service,
            industry_system=args.industry_system,
            dry_run=args.dry_run,
            step_runners=None if args.dry_run else build_default_step_runners(),
            freshness_checker=None,
            recorder=recorder,
            start_at=args.start_at,
            only_step=args.only_step,
        )
        print(f"daily_incremental|status|{result['status']}")
        if "reason" in result:
            print(f"daily_incremental|reason|{result['reason']}")
        for step in result["steps"]:
            print(f"daily_incremental_step|{step['step']}|{step['status']}")
            if "error" in step:
                print(f"daily_incremental_step_error|{step['step']}|{step['error']}")
    elif args.command == "daily-health":
        result = summarize_operational_health(
            trade_date=args.trade_date,
            ingest_datasets=args.ingest_datasets or [],
            backfill_run_ids=args.backfill_run_ids or [],
            stale_minutes=args.stale_minutes,
        )
        lines = format_operational_health_lines(result)
        for line in lines:
            print(line)
        if args.notify_target and result["status"] == "alert":
            send_openclaw_feishu_message(
                message="\n".join(lines),
                target=args.notify_target,
                account=args.notify_account,
                openclaw_bin=args.openclaw_bin,
                dry_run=args.notify_dry_run,
            )
    elif args.command == "export-research-snapshot":
        result = export_research_snapshot(
            start_date=args.start_date,
            end_date=args.end_date,
            score_version=args.score_version,
            output_dir=args.output_dir,
        )
        print(f"research_snapshot|manifest|{result['manifest_path']}")
        for dataset, rows in result["row_counts"].items():
            print(f"research_snapshot_dataset|{dataset}|rows|{rows}|{result['files'][dataset]}")
    elif args.command == "migration-safety-check":
        result = run_backup_restore_check(
            backup_path=args.backup_path,
            source_service=args.source_service,
            restore_service=args.restore_service,
            dry_run=args.dry_run,
        )
        print(f"migration_safety|status|{result['status']}")
        for command in result["commands"]:
            print(f"migration_safety_command|{command}")
        for check in result["checks"]:
            print(f"migration_safety_check|{check['check']}|{check['status']}|{check['detail']}")
    elif args.command == "run-daily-research-report":
        result = run_daily_research_report(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
            index_id=args.index_id,
            market_lookback_days=args.market_lookback_days,
            industry_system=args.industry_system,
            sector_lookback_days=args.sector_lookback_days,
            positions_csv=args.positions_csv,
            reports_dir=args.reports_dir,
            apply_report_run_schema_first=args.apply_report_run_schema,
            record_run=args.record_run,
        )
        report_paths = result["report_paths"]
        for key in ("bundle", "topn", "market_state", "sector_strength", "risk_alerts", "position_review"):
            print(f"daily_research_report|{key}|{report_paths[key]['markdown_path']}")
    elif args.command == "trend-lifecycle-v1":
        result = run_trend_lifecycle_v1_report(
            start_date=args.start_date,
            end_date=args.end_date,
            score_version=args.score_version,
            top_n=args.top_n,
            adjust_type=args.adjust_type,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"trend_lifecycle_v1|report|{paths['markdown_report']}")
        print(f"trend_lifecycle_v1|trend_segments|{paths['trend_segments']}")
        print(f"trend_lifecycle_v1|lifecycle_samples|{paths['lifecycle_samples']}")
        print(f"trend_lifecycle_v1|entry_success_labels|{paths['entry_success_labels']}")
        print(f"trend_lifecycle_v1|top20_stage_hit_report|{paths['top20_stage_hit_report']}")
        print(f"trend_lifecycle_v1|segments|{len(result['segments'])}")
        print(f"trend_lifecycle_v1|lifecycle_samples_rows|{len(result['lifecycle_samples'])}")
        print(f"trend_lifecycle_v1|entry_success_rows|{len(result['entry_success'])}")
        print(f"trend_lifecycle_v1|top20_stage_hit_rows|{len(result['top20_stage_hits'])}")
        print(f"trend_lifecycle_v1|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "mid-trend-factor-profile":
        result = run_mid_trend_factor_profile_report(
            start_date=args.start_date,
            end_date=args.end_date,
            lifecycle_samples_path=args.lifecycle_samples_path,
            factor_names=args.factor_names,
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"mid_trend_factor_profile|report|{paths['markdown_report']}")
        print(f"mid_trend_factor_profile|factor_profile|{paths['factor_profile']}")
        print(f"mid_trend_factor_profile|stage_stability|{paths['stage_stability']}")
        print(f"mid_trend_factor_profile|candidate_rank|{paths['candidate_rank']}")
        print(f"mid_trend_factor_profile|stage_signatures|{paths['stage_signatures']}")
        print(f"mid_trend_factor_profile|profile_rows|{len(result['profile'])}")
        print(f"mid_trend_factor_profile|stability_rows|{len(result['stability'])}")
        print(f"mid_trend_factor_profile|candidate_rows|{len(result['candidate_rank'])}")
        print(f"mid_trend_factor_profile|stage_signature_rows|{len(result['stage_signatures'])}")
        print(f"mid_trend_factor_profile|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "mid-trend-candidate-enrichment":
        result = run_candidate_enrichment_report(
            start_date=args.start_date,
            end_date=args.end_date,
            candidate_rank_path=args.candidate_rank_path,
            entry_success_labels_path=args.entry_success_labels_path,
            max_factors=args.max_factors,
            min_candidate_score=args.min_candidate_score,
            quantiles=args.quantiles,
            top_ns=tuple(args.top_ns),
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"mid_trend_candidate_enrichment|report|{paths['markdown_report']}")
        print(f"mid_trend_candidate_enrichment|candidate_scores|{paths['candidate_scores']}")
        print(
            "mid_trend_candidate_enrichment|enrichment_by_quantile|"
            f"{paths['enrichment_by_quantile']}"
        )
        print(f"mid_trend_candidate_enrichment|enrichment_by_topn|{paths['enrichment_by_topn']}")
        print(f"mid_trend_candidate_enrichment|enrichment_by_period|{paths['enrichment_by_period']}")
        print(f"mid_trend_candidate_enrichment|candidate_score_rows|{len(result['candidate_scores'])}")
        print(f"mid_trend_candidate_enrichment|quantile_rows|{len(result['enrichment_by_quantile'])}")
        print(f"mid_trend_candidate_enrichment|topn_rows|{len(result['enrichment_by_topn'])}")
        print(f"mid_trend_candidate_enrichment|period_rows|{len(result['enrichment_by_period'])}")
        print(f"mid_trend_candidate_enrichment|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "mid-trend-full-universe-enrichment":
        result = run_full_universe_candidate_enrichment_report(
            start_date=args.start_date,
            end_date=args.end_date,
            candidate_scores_path=args.candidate_scores_path,
            adjust_type=args.adjust_type,
            quantiles=args.quantiles,
            top_ns=tuple(args.top_ns),
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"mid_trend_full_universe_enrichment|report|{paths['markdown_report']}")
        print(f"mid_trend_full_universe_enrichment|candidate_scores|{paths['candidate_scores']}")
        print(
            "mid_trend_full_universe_enrichment|candidate_entry_success_labels|"
            f"{paths['candidate_entry_success_labels']}"
        )
        print(
            "mid_trend_full_universe_enrichment|enrichment_by_quantile|"
            f"{paths['enrichment_by_quantile']}"
        )
        print(
            "mid_trend_full_universe_enrichment|enrichment_by_topn|"
            f"{paths['enrichment_by_topn']}"
        )
        print(
            "mid_trend_full_universe_enrichment|enrichment_by_period|"
            f"{paths['enrichment_by_period']}"
        )
        print(f"mid_trend_full_universe_enrichment|candidate_score_rows|{len(result['candidate_scores'])}")
        print(
            "mid_trend_full_universe_enrichment|entry_success_rows|"
            f"{len(result['candidate_entry_success_labels'])}"
        )
        print(f"mid_trend_full_universe_enrichment|quantile_rows|{len(result['enrichment_by_quantile'])}")
        print(f"mid_trend_full_universe_enrichment|topn_rows|{len(result['enrichment_by_topn'])}")
        print(f"mid_trend_full_universe_enrichment|period_rows|{len(result['enrichment_by_period'])}")
        print(f"mid_trend_full_universe_enrichment|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "entry-success-reverse-profile":
        result = run_entry_success_reverse_profile_report(
            start_date=args.start_date,
            end_date=args.end_date,
            entry_success_labels_path=args.entry_success_labels_path,
            factor_names=args.factor_names,
            horizons=tuple(args.horizons),
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"entry_success_reverse_profile|report|{paths['markdown_report']}")
        print(
            "entry_success_reverse_profile|factor_profile|"
            f"{paths['entry_success_factor_profile']}"
        )
        print(
            "entry_success_reverse_profile|factor_rank|"
            f"{paths['entry_success_factor_rank']}"
        )
        print(f"entry_success_reverse_profile|factor_profile_rows|{len(result['factor_profile'])}")
        print(f"entry_success_reverse_profile|factor_rank_rows|{len(result['factor_rank'])}")
        print(f"entry_success_reverse_profile|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "entry-success-candidate-v2":
        result = run_entry_success_candidate_v2_report(
            start_date=args.start_date,
            end_date=args.end_date,
            factor_rank_path=args.factor_rank_path,
            horizon=args.horizon,
            max_factors=args.max_factors,
            min_candidate_score=args.min_candidate_score,
            min_sign_match_rate=args.min_sign_match_rate,
            adjust_type=args.adjust_type,
            quantiles=args.quantiles,
            top_ns=tuple(args.top_ns),
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"entry_success_candidate_v2|report|{paths['markdown_report']}")
        print(f"entry_success_candidate_v2|candidate_rank|{paths['candidate_rank']}")
        print(f"entry_success_candidate_v2|candidate_scores|{paths['candidate_scores']}")
        print(
            "entry_success_candidate_v2|candidate_entry_success_labels|"
            f"{paths['candidate_entry_success_labels']}"
        )
        print(
            "entry_success_candidate_v2|enrichment_by_quantile|"
            f"{paths['enrichment_by_quantile']}"
        )
        print(f"entry_success_candidate_v2|enrichment_by_topn|{paths['enrichment_by_topn']}")
        print(f"entry_success_candidate_v2|enrichment_by_period|{paths['enrichment_by_period']}")
        print(f"entry_success_candidate_v2|candidate_rank_rows|{len(result['candidate_rank'])}")
        print(f"entry_success_candidate_v2|candidate_score_rows|{len(result['candidate_scores'])}")
        print(f"entry_success_candidate_v2|entry_success_rows|{len(result['candidate_entry_success_labels'])}")
        print(f"entry_success_candidate_v2|quantile_rows|{len(result['enrichment_by_quantile'])}")
        print(f"entry_success_candidate_v2|topn_rows|{len(result['enrichment_by_topn'])}")
        print(f"entry_success_candidate_v2|period_rows|{len(result['enrichment_by_period'])}")
        print(f"entry_success_candidate_v2|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "trend-candidate-backtest":
        result = run_trend_candidate_backtest_report(
            start_date=args.start_date,
            end_date=args.end_date,
            candidate_scores_path=args.candidate_scores_path,
            top_ns=tuple(args.top_ns),
            holding_days=tuple(args.holding_days),
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"trend_candidate_backtest|report|{paths['markdown_report']}")
        print(f"trend_candidate_backtest|summary|{paths['summary']}")
        print(f"trend_candidate_backtest|equity_curve|{paths['equity_curve']}")
        print(f"trend_candidate_backtest|positions|{paths['positions']}")
        print(f"trend_candidate_backtest|trades|{paths['trades']}")
        print(f"trend_candidate_backtest|summary_rows|{len(result['summary'])}")
        print(f"trend_candidate_backtest|equity_rows|{len(result['equity_curve'])}")
        print(f"trend_candidate_backtest|position_rows|{len(result['positions'])}")
        print(f"trend_candidate_backtest|trade_rows|{len(result['trades'])}")
        print(f"trend_candidate_backtest|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "industry-focus-backtest":
        result = run_industry_focus_backtest_report(
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
            dynamic_top_k=args.dynamic_top_k,
            min_industry_stocks=args.min_industry_stocks,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"industry_focus_backtest|report|{paths['markdown_report']}")
        print(f"industry_focus_backtest|summary|{paths['summary']}")
        print(f"industry_focus_backtest|industry_scores|{paths['industry_scores']}")
        print(f"industry_focus_backtest|focus_industries_daily|{paths['focus_industries_daily']}")
        print(f"industry_focus_backtest|summary_rows|{len(result['summary'])}")
    elif args.command in {"industry-v1-attribution", "industry-focus-v2-diagnostics"}:
        result = run_industry_focus_v2_diagnostics(
            start_date=args.start_date,
            end_date=args.end_date,
            min_industry_stocks=args.min_industry_stocks,
            output_dir=args.output_dir,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
            dynamic_top_k=args.dynamic_top_k,
        )
        paths = result["paths"]
        prefix = "industry_v1_attribution" if args.command == "industry-v1-attribution" else "industry_focus_v2_diagnostics"
        print(f"{prefix}|v1_failure_attribution|{paths['v1_failure_attribution']}")
        print(f"{prefix}|v2_diagnostics|{paths['v2_diagnostics']}")
        print(f"{prefix}|v1_rows|{len(result['v1_failure_attribution'])}")
        print(f"{prefix}|v2_rows|{len(result['v2_diagnostics'])}")
    elif args.command == "industry-focus-v2-backtest":
        result = run_industry_focus_v2_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            diagnostics_path=args.diagnostics_path,
            top_n=args.top_n,
            transaction_cost_bps=args.transaction_cost_bps,
            output_dir=args.output_dir,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
        )
        paths = result["paths"]
        print(f"industry_focus_v2_backtest|summary|{paths['summary']}")
        print(f"industry_focus_v2_backtest|annual_metrics|{paths['annual_metrics']}")
        print(f"industry_focus_v2_backtest|monthly_metrics|{paths['monthly_metrics']}")
        print(f"industry_focus_v2_backtest|summary_rows|{len(result['summary'])}")
    elif args.command == "dragon-research-v1":
        result = run_dragon_research_v1(
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            hot_industry_top_n=args.hot_industry_top_n,
            adjust_type=args.adjust_type,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            industry_diagnostics_path=args.industry_diagnostics_path,
            candidate_scores_path=args.candidate_scores_path,
            lifecycle_samples_path=args.lifecycle_samples_path,
        )
        paths = result["paths"]
        print(f"dragon_research_v1|diagnostics|{paths['diagnostics']}")
        print(f"dragon_research_v1|monthly_summary|{paths['monthly_summary']}")
        print(f"dragon_research_v1|role_effectiveness|{paths['role_effectiveness']}")
        print(f"dragon_research_v1|yearly_diagnosis|{paths['yearly_diagnosis']}")
        print(f"dragon_research_v1|report|{paths['markdown_report']}")
        print(f"dragon_research_v1|diagnostic_rows|{len(result['diagnostics'])}")
        print(f"dragon_research_v1|role_rows|{len(result['role_effectiveness'])}")
        print(f"dragon_research_v1|yearly_rows|{len(result['yearly_diagnosis'])}")
    elif args.command == "dragon-case-library-build":
        result = run_dragon_case_library_build(
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            seed_path=args.seed_path,
            adjust_type=args.adjust_type,
        )
        print(f"dragon_case_library_build|case_library|{result['paths']['case_library']}")
        if "auto_candidates" in result.get("paths", {}):
            print(f"dragon_case_library_build|auto_candidates_csv|{result['paths']['auto_candidates']}")
        print(f"dragon_case_library_build|cases|{len(result['case_library'])}")
        print(f"dragon_case_library_build|auto_candidates|{len(result['auto_candidates'])}")
    elif args.command == "dragon-case-library-diagnose":
        result = run_dragon_case_library_diagnose(
            case_path=args.case_path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            adjust_type=args.adjust_type,
        )
        print(f"dragon_case_library_diagnose|event_diagnostics|{result['paths']['event_diagnostics']}")
        print(
            "dragon_case_library_diagnose|success_failure_comparison|"
            f"{result['paths']['success_failure_comparison']}"
        )
        print(f"dragon_case_library_diagnose|report|{result['paths']['markdown_report']}")
        print(f"dragon_case_library_diagnose|event_rows|{len(result['event_diagnostics'])}")
        print(f"dragon_case_library_diagnose|warnings|{len(result['warnings'])}")
    elif args.command == "dragon-case-import-web-seeds":
        result = import_web_seeds(args.input, args.output_dir)
        print(f"dragon_case_import_web_seeds|web_candidates|{result['paths']['web_candidates']}")
        print(f"dragon_case_import_web_seeds|rows|{len(result['web_candidates'])}")
    elif args.command == "dragon-case-expand-web-seeds":
        result = run_dragon_case_expand_web_seeds(
            article_seed_path=args.article_seed,
            output_path=args.output,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        print(f"dragon_case_expand_web_seeds|web_seed|{result['paths']['web_seed']}")
        print(f"dragon_case_expand_web_seeds|summary|{result['paths']['summary']}")
        print(f"dragon_case_expand_web_seeds|unmatched|{result['paths']['unmatched']}")
        print(f"dragon_case_expand_web_seeds|coverage|{result['paths']['coverage']}")
        print(f"dragon_case_expand_web_seeds|report|{result['paths']['report']}")
        print(f"dragon_case_expand_web_seeds|matched|{len(result['web_seed'])}")
        print(f"dragon_case_expand_web_seeds|unmatched_rows|{len(result['unmatched'])}")
    elif args.command == "dragon-case-web-verify":
        result = run_dragon_case_web_verify(
            candidate_path=args.candidate_path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            adjust_type=args.adjust_type,
        )
        print(f"dragon_case_web_verify|event_verification|{result['paths']['event_verification']}")
        print(f"dragon_case_web_verify|factor_review|{result['paths']['factor_review']}")
        print(f"dragon_case_web_verify|curated_library|{result['paths']['curated_library']}")
        print(f"dragon_case_web_verify|source_evidence|{result['paths']['source_evidence']}")
        print(f"dragon_case_web_verify|report|{result['paths']['markdown_report']}")
        print(f"dragon_case_web_verify|web_candidates|{len(result['web_candidates'])}")
        print(f"dragon_case_web_verify|verified|{len(result['verified'])}")
        print(f"dragon_case_web_verify|curated|{len(result['curated'])}")
    elif args.command == "dragon-case-apply-source-backfill":
        result = apply_source_backfill(
            tasks_path=args.tasks_path,
            article_seed_path=args.article_seed,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
        print(f"dragon_case_apply_source_backfill|summary|{result['paths']['summary']}")
        print(f"dragon_case_apply_source_backfill|errors|{result['paths']['errors']}")
        print(f"dragon_case_apply_source_backfill|report|{result['paths']['report']}")
        print(f"dragon_case_apply_source_backfill|article_seed|{result['paths']['article_seed']}")
        print(f"dragon_case_apply_source_backfill|inserted|{int(result['summary'].iloc[0]['inserted_article_seed_rows'])}")
        print(f"dragon_case_apply_source_backfill|skipped_duplicate|{int(result['summary'].iloc[0]['skipped_duplicate_rows'])}")
        print(f"dragon_case_apply_source_backfill|dry_run|{args.dry_run}")
    elif args.command == "dragon-case-source-backfill-compare":
        result = compare_source_backfill_curated(
            before_curated_path=args.before_curated,
            after_curated_path=args.after_curated,
            output_dir=args.output_dir,
        )
        print(f"dragon_case_source_backfill_compare|delta|{result['paths']['delta']}")
        print(f"dragon_case_source_backfill_compare|warnings|{len(result['warnings'])}")
    elif args.command == "dragon-case-source-backfill-workpack":
        import pandas as pd

        tasks = pd.read_csv(args.tasks_path, low_memory=False)
        result = build_source_backfill_workpack(tasks, top_n=args.top_n, output_dir=args.output_dir)
        print(f"dragon_case_source_backfill_workpack|csv|{result['paths']['csv']}")
        print(f"dragon_case_source_backfill_workpack|markdown|{result['paths']['markdown']}")
        print(f"dragon_case_source_backfill_workpack|next_commands|{result['paths']['next_commands']}")
        print(f"dragon_case_source_backfill_workpack|rows|{len(result['workpack'])}")
    elif args.command == "dragon-case-source-backfill-check":
        import pandas as pd
        from pathlib import Path

        apply_summary = pd.read_csv(args.apply_summary, low_memory=False)
        delta_summary = pd.read_csv(args.delta_summary, low_memory=False)
        curated = pd.read_csv(args.curated, low_memory=False)
        report = build_source_backfill_check_report(apply_summary, delta_summary, curated)
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        report_path = out / "dragon_case_source_backfill_check_report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"dragon_case_source_backfill_check|report|{report_path}")
    elif args.command == "dragon-case-failure-event-rules-v2":
        result = run_failure_event_rule_v2_diagnostics(
            case_path=args.case_path,
            snapshot_path=args.snapshot_path,
            output_dir=args.output_dir,
        )
        print(f"failure_event_rule_v2|audit|{result['paths']['audit']}")
        print(f"failure_event_rule_v2|summary|{result['paths']['summary']}")
        print(f"failure_event_rule_v2|report|{result['paths']['report']}")
        print(f"failure_event_rule_v2|audit_rows|{len(result['audit'])}")
    elif args.command == "validate-technical-methods":
        result = run_validate_technical_methods(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            sample_size=args.sample_size,
            asset_id=args.asset_id,
            ts_code=args.ts_code,
            feature_source=args.feature_source,
            output_dir=args.output_dir,
        )
        print(f"technical_method_validation|feature_bucket_effectiveness|{result['paths']['feature_bucket_effectiveness']}")
        print(f"technical_method_validation|combo_effectiveness|{result['paths']['combo_effectiveness']}")
        print(f"technical_method_validation|regime_effectiveness|{result['paths']['regime_effectiveness']}")
        print(f"technical_method_validation|case_event_effectiveness|{result['paths']['case_event_effectiveness']}")
        print(f"technical_method_validation|lhb_cross_effectiveness|{result['paths']['lhb_cross_effectiveness']}")
        print(f"technical_method_validation|feature_correlation|{result['paths']['feature_correlation']}")
        print(f"technical_method_validation|redundancy_report|{result['paths']['redundancy_report']}")
        print(f"technical_method_validation|recommendation|{result['paths']['recommendation']}")
        print(f"technical_method_validation|report|{result['paths']['report']}")
        print(f"technical_method_validation|rows|{len(result['dataset'])}")
    elif args.command == "technical-feature-promotion-audit":
        result = run_technical_feature_promotion_audit(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            sample_size=args.sample_size,
            asset_id=args.asset_id,
            ts_code=args.ts_code,
            feature_source=args.feature_source,
            output_dir=args.output_dir,
        )
        print(f"technical_feature_promotion_audit|audit|{result['paths']['promotion_audit']}")
        print(f"technical_feature_promotion_audit|watchlist|{result['paths']['watchlist_readiness']}")
        print(f"technical_feature_promotion_audit|report|{result['paths']['report']}")
        print(f"technical_feature_promotion_audit|rows|{len(result['promotion_audit'])}")
    elif args.command == "lhb-risk-diagnostics-after-failure-rule-v2-1":
        result = run_lhb_diagnostics_after_failure_rule_v21(
            case_path=args.case_path,
            failure_audit_path=args.failure_audit_path,
            snapshot_path=args.snapshot_path,
            lhb_features_path=args.lhb_features_path,
            alignment_path=args.alignment_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_after_failure_rule_v2_1|curated_failure_v21|{result['paths']['curated_failure_v21']}")
        print(f"lhb_after_failure_rule_v2_1|transition_matrix|{result['paths']['transition_matrix']}")
        print(f"lhb_after_failure_rule_v2_1|case_type_difference_summary|{result['paths']['case_type_difference_summary']}")
        print(f"lhb_after_failure_rule_v2_1|risk_feature_case_detail|{result['paths']['risk_feature_case_detail']}")
        print(f"lhb_after_failure_rule_v2_1|comparison|{result['paths']['comparison']}")
        print(f"lhb_after_failure_rule_v2_1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-sample-import":
        ts_codes = parse_str_list(args.ts_codes, "--ts-codes") if args.ts_codes else None
        result = run_lhb_sample_import(
            start_date=args.start_date,
            end_date=args.end_date,
            ts_codes=ts_codes,
            output_dir=args.output_dir,
            provider=args.provider,
        )
        print(f"lhb_sample_import|top_list|{result['paths']['top_list']}")
        print(f"lhb_sample_import|top_inst|{result['paths']['top_inst']}")
        print(f"lhb_sample_import|top_list_rows|{len(result['top_list'])}")
        print(f"lhb_sample_import|top_inst_rows|{len(result['top_inst'])}")
    elif args.command == "lhb-build-event-features":
        ts_codes = parse_str_list(args.ts_codes, "--ts-codes") if args.ts_codes else None
        result = run_lhb_event_features_build(
            start_date=args.start_date,
            end_date=args.end_date,
            ts_codes=ts_codes,
            output_dir=args.output_dir,
        )
        print(f"lhb_event_features_build|lhb_event_features|{result['paths']['lhb_event_features']}")
        print(f"lhb_event_features_build|rows|{len(result['lhb_event_features'])}")
    elif args.command == "dragon-case-lhb-alignment-audit":
        result = run_dragon_case_lhb_alignment_audit(
            curated_path=args.curated_path,
            output_dir=args.output_dir,
        )
        print(f"dragon_case_lhb_alignment_audit|alignment_audit|{result['paths']['alignment_audit']}")
        print(f"dragon_case_lhb_alignment_audit|rows|{len(result['alignment_audit'])}")
        print(f"dragon_case_lhb_alignment_audit|warnings|{len(result['warnings'])}")
    elif args.command == "dragon-case-lhb-summary":
        result = run_dragon_case_lhb_summary_report(
            curated_path=args.curated_path,
            output_dir=args.output_dir,
        )
        print(f"dragon_case_lhb_summary|summary|{result['paths']['summary']}")
        print(f"dragon_case_lhb_summary|comparison|{result['paths']['comparison']}")
        print(f"dragon_case_lhb_summary|report|{result['paths']['markdown_report']}")
        print(f"dragon_case_lhb_summary|rows|{len(result['summary'])}")
    elif args.command == "lhb-case-difference-report":
        result = run_lhb_case_difference_report(
            case_path=args.case_path,
            lhb_features_path=args.lhb_features_path,
            alignment_path=args.alignment_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_case_difference_report|case_type_difference_summary|{result['paths']['case_type_difference_summary']}")
        print(f"lhb_case_difference_report|event_window_difference|{result['paths']['event_window_difference']}")
        print(f"lhb_case_difference_report|risk_signal_effectiveness|{result['paths']['risk_signal_effectiveness']}")
        print(f"lhb_case_difference_report|positive_signal_effectiveness|{result['paths']['positive_signal_effectiveness']}")
        print(f"lhb_case_difference_report|case_event_detail|{result['paths']['case_event_detail']}")
        print(f"lhb_case_difference_report|coverage_summary|{result['paths']['coverage_summary']}")
        print(f"lhb_case_difference_report|report|{result['paths']['markdown_report']}")
        print(f"lhb_case_difference_report|warnings|{len(result['warnings'])}")
    elif args.command == "lhb-risk-feature-diagnostics":
        result = run_lhb_risk_feature_diagnostics(
            case_path=args.case_path,
            lhb_features_path=args.lhb_features_path,
            alignment_path=args.alignment_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_risk_feature_diagnostics|risk_feature_case_detail|{result['paths']['risk_feature_case_detail']}")
        print(f"lhb_risk_feature_diagnostics|risk_score_bucket_effectiveness|{result['paths']['risk_score_bucket_effectiveness']}")
        print(f"lhb_risk_feature_diagnostics|risk_failure_type_cross|{result['paths']['risk_failure_type_cross']}")
        print(f"lhb_risk_feature_diagnostics|dragon_risk_cross_diagnostics|{result['paths']['dragon_risk_cross_diagnostics']}")
        print(f"lhb_risk_feature_diagnostics|coverage_gap_recommendations|{result['paths']['coverage_gap_recommendations']}")
        print(f"lhb_risk_feature_diagnostics|report|{result['paths']['markdown_report']}")
        print(f"lhb_risk_feature_diagnostics|warnings|{len(result['warnings'])}")
    elif args.command == "lhb-coverage-failure-plan":
        result = run_lhb_coverage_and_failure_rule_plan(
            coverage_gap_path=args.coverage_gap_path,
            case_path=args.case_path,
            snapshot_path=args.snapshot_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_coverage_failure_plan|coverage_expansion_plan|{result['paths']['coverage_expansion_plan']}")
        print(f"lhb_coverage_failure_plan|coverage_expansion_summary|{result['paths']['coverage_expansion_summary']}")
        print(f"lhb_coverage_failure_plan|next_commands|{result['paths']['next_commands']}")
        print(f"lhb_coverage_failure_plan|failure_rule_audit|{result['paths']['failure_rule_audit']}")
        print(f"lhb_coverage_failure_plan|failure_rule_suggestions|{result['paths']['failure_rule_suggestions']}")
        print(f"lhb_coverage_failure_plan|report|{result['paths']['markdown_report']}")
        print(f"lhb_coverage_failure_plan|warnings|{len(result['warnings'])}")
    elif args.command == "fixed-industry-reconciliation":
        result = run_fixed_industry_reconciliation(
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
            transaction_cost_bps=args.transaction_cost_bps,
            output_dir=args.output_dir,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
        )
        paths = result["paths"]
        print(f"fixed_industry_reconciliation|csv|{paths['reconciliation']}")
        print(f"fixed_industry_reconciliation|rows|{len(result['reconciliation'])}")
        print(f"fixed_industry_reconciliation|explanation|{result['explanation']}")
    elif args.command == "industry-error-audit":
        result = run_industry_error_audit(
            diagnostics_path=args.diagnostics_path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            backtest_summary_path=args.backtest_summary_path,
            annual_metrics_path=args.annual_metrics_path,
        )
        paths = result["paths"]
        print(f"industry_error_audit|monthly|{paths['monthly']}")
        print(f"industry_error_audit|summary|{paths['summary']}")
        print(f"industry_error_audit|tag_effectiveness|{paths['tag_effectiveness']}")
        print(f"industry_error_audit|component_effectiveness|{paths['component_effectiveness']}")
        print(f"industry_error_audit|yearly|{paths['yearly']}")
        print(f"industry_error_audit|markdown_report|{paths['markdown_report']}")
        print(f"industry_error_audit|monthly_rows|{len(result['monthly'])}")
        print(f"industry_error_audit|summary_rows|{len(result['summary'])}")
    elif args.command == "industry-mainline-regime-diagnostics":
        result = run_industry_mainline_regime_diagnostics(
            diagnostics_path=args.diagnostics_path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        paths = result["paths"]
        print(f"industry_mainline_regime|diagnostics|{paths['diagnostics']}")
        print(f"industry_mainline_regime|market_regimes|{paths['market_regimes']}")
        print(
            "industry_mainline_regime|regime_effectiveness|"
            f"{paths['regime_effectiveness']}"
        )
        print(f"industry_mainline_regime|tag_effectiveness|{paths['tag_effectiveness']}")
        print(f"industry_mainline_regime|markdown_report|{paths['markdown_report']}")
        print(f"industry_mainline_regime|diagnostic_rows|{len(result['diagnostics'])}")
        print(f"industry_mainline_regime|regime_rows|{len(result['market_regimes'])}")
    elif args.command == "industry-regime-gated-backtest":
        result = run_industry_regime_gated_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            diagnostics_path=args.diagnostics_path,
            regime_path=args.regime_path,
            mainline_path=args.mainline_path,
            output_dir=args.output_dir,
            top_n=args.top_n,
            transaction_cost_bps=args.transaction_cost_bps,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
        )
        paths = result["paths"]
        print(f"industry_regime_gated_backtest|summary|{paths['summary']}")
        print(f"industry_regime_gated_backtest|annual_metrics|{paths['annual_metrics']}")
        print(f"industry_regime_gated_backtest|monthly_metrics|{paths['monthly_metrics']}")
        print(f"industry_regime_gated_backtest|industry_exposure|{paths['industry_exposure']}")
        print(f"industry_regime_gated_backtest|turnover_detail|{paths['turnover_detail']}")
        print(f"industry_regime_gated_backtest|markdown_report|{paths['markdown_report']}")
        print(f"industry_regime_gated_backtest|summary_rows|{len(result['summary'])}")
    elif args.command == "industry-exposure-risk-control":
        result = run_industry_exposure_risk_control(
            start_date=args.start_date,
            end_date=args.end_date,
            diagnostics_path=args.diagnostics_path,
            regime_path=args.regime_path,
            mainline_path=args.mainline_path,
            output_dir=args.output_dir,
            top_n=args.top_n,
            transaction_cost_bps=args.transaction_cost_bps,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
        )
        paths = result["paths"]
        print(f"industry_exposure_risk_control|summary|{paths['summary']}")
        print(f"industry_exposure_risk_control|annual_metrics|{paths['annual_metrics']}")
        print(f"industry_exposure_risk_control|monthly_metrics|{paths['monthly_metrics']}")
        print(f"industry_exposure_risk_control|industry_exposure|{paths['industry_exposure']}")
        print(f"industry_exposure_risk_control|turnover_detail|{paths['turnover_detail']}")
        print(f"industry_exposure_risk_control|markdown_report|{paths['markdown_report']}")
        print(f"industry_exposure_risk_control|summary_rows|{len(result['summary'])}")
    elif args.command == "sync-industry-memberships":
        count = sync_industry_memberships(args.trade_date)
        print(f"industry_memberships_synced|{count}")
    elif args.command == "sync-index-bars":
        count = sync_index_daily_bars(args.start_date, args.end_date)
        print(f"index_daily_bars_synced|{count}")
    elif args.command == "sync-index-constituents":
        count = sync_index_constituents(
            trade_date=args.trade_date,
            index_ids=args.index_ids,
            source_version=args.source_version,
        )
        print(f"index_constituents_synced|{count}")
    elif args.command == "benchmark-industry-day":
        result = benchmark_industry_day(
            trade_date=args.trade_date,
            industry_system=args.industry_system,
            adjust_type=args.adjust_type,
            use_cache=args.use_cache,
        )
        print(
            "industry_day_benchmark|sync_memberships|"
            f"{result['trade_date']}|rows|{result['membership_rows']}|seconds|{result['sync_seconds']}"
        )
        print(
            "industry_day_benchmark|build_bars|"
            f"{result['trade_date']}|seconds|{result['build_seconds']}"
        )
        print(
            "industry_day_benchmark|total|"
            f"{result['trade_date']}|seconds|{result['total_seconds']}"
        )
    elif args.command == "backfill-industry-history":
        result = run_industry_history_range(
            start_date=args.start_date,
            end_date=args.end_date,
            max_dates=args.max_dates,
            frequency=args.frequency,
            industry_system=args.industry_system,
            adjust_type=args.adjust_type,
            use_cache=args.use_cache,
            progress=lambda event: print(
                "industry_history_progress|"
                f"{event['trade_date']}|{event['index']}|{event['total']}|"
                f"membership_rows|{event['membership_rows']}|seconds|{event['seconds']}"
            ),
        )
        print(
            "industry_history_done|"
            f"dates|{result['dates']}|membership_rows|{result['membership_rows']}|"
            f"seconds|{result['seconds']}"
        )
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
    elif args.command == "sync-baostock-minute-bars":
        counts = sync_baostock_stock_minute_bars(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            limit_assets=args.limit_assets,
            sleep_seconds=args.sleep_seconds,
        )
        for adjust_type, count in counts.items():
            print(f"stock_minute_bars_synced|{args.freq}|{adjust_type}|{count}")
    elif args.command == "plan-baostock-minute-backfill":
        result = plan_baostock_minute_backfill(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            batch_by=args.batch_by,
            output_dir=args.output_dir,
            limit_assets=args.limit_assets,
        )
        for key, value in result["summary"].items():
            print(f"minute_backfill_plan|{key}|{value}")
    elif args.command == "run-baostock-minute-backfill":
        result = run_baostock_minute_backfill(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            batch_by=args.batch_by,
            max_jobs=args.max_jobs,
            retry_failed=args.retry_failed,
            sleep_seconds=args.sleep_seconds,
            workers=args.workers,
        )
        for key, value in result.items():
            print(f"minute_backfill_run|{key}|{value}")
    elif args.command == "run-baostock-minute-backfill-range":
        def report(summary: dict) -> None:
            month = summary["month"]
            job_summary = summary["job_summary"]
            validation_summary = summary["validation_summary"]
            message = (
                f"minute_backfill_month_done|{month}\n"
                f"jobs_total={job_summary['total_jobs']}\n"
                f"jobs_success={job_summary['success_jobs']}\n"
                f"jobs_failed={job_summary['failed_jobs']}\n"
                f"market_rows={job_summary['total_market_rows']}\n"
                f"staging_rows={job_summary['total_staging_rows']}\n"
                f"validation_errors={validation_summary['error_count']}"
            )
            print(message, flush=True)
            try:
                send_openclaw_feishu_message(
                    message=message,
                    target=args.report_target,
                    account=args.report_account,
                    openclaw_bin=args.openclaw_bin,
                    dry_run=args.report_dry_run,
                )
            except Exception as exc:
                print(
                    f"minute_backfill_report_failed|{exc.__class__.__name__}|{exc}",
                    file=sys.stderr,
                    flush=True,
                )

        result = run_baostock_minute_backfill_range(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            batch_by=args.batch_by,
            max_jobs=args.max_jobs,
            retry_failed=args.retry_failed,
            sleep_seconds=args.sleep_seconds,
            workers=args.workers,
            output_dir=args.output_dir,
            limit_assets=args.limit_assets,
            report=report,
        )
        for key, value in result.items():
            print(f"minute_backfill_range|{key}|{value}")
    elif args.command == "minute-backfill-watchdog":
        run_minute_backfill_watchdog_command(args)
    elif args.command == "backfill-watchdog":
        if args.adapter == "minute":
            run_minute_backfill_watchdog_command(args)
        elif args.adapter == "technical-features":
            run_technical_feature_watchdog_command(args)
        elif args.adapter == "factor-gate":
            run_factor_gate_watchdog_command(args)
    elif args.command == "baostock-minute-backfill-status":
        result = load_backfill_status(output_dir=args.output_dir)
        for key, value in result["summary"].items():
            print(f"minute_backfill_status|{key}|{value}")
        print(f"minute_backfill_status_by_period_rows|{len(result['by_period'])}")
    elif args.command == "validate-minute-bars":
        result = validate_minute_bars(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            output_dir=args.output_dir,
            limit_rows=args.limit_rows,
        )
        for key, value in result["summary"].items():
            print(f"minute_bar_validation|{key}|{value}")
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
            try:
                send_openclaw_feishu_message(
                    message=message,
                    target=args.report_target,
                    account=args.report_account,
                    openclaw_bin=args.openclaw_bin,
                    dry_run=args.report_dry_run,
                )
            except Exception as exc:
                print(
                    f"ingest_loop_report_failed|{exc.__class__.__name__}|{exc}",
                    file=sys.stderr,
                    flush=True,
                )

        result = run_ingest_loop_for_service(
            args.dataset,
            jobs_per_round=args.jobs_per_round,
            report=report,
            progress=print_ingest_progress,
            sleep_seconds=args.sleep_seconds,
            max_rounds=args.max_rounds,
            workers=args.workers,
        )
        print(f"ingest_loop_rounds|{result['rounds']}")
        print(f"ingest_loop_attempted|{result['attempted']}")
        print(f"ingest_loop_success|{result['success']}")
        print(f"ingest_loop_failed|{result['failed']}")
        print(f"ingest_loop_done|{result['done']}")
    elif args.command == "reset-stale-ingest-jobs":
        count = reset_stale_ingest_jobs_for_service(
            dataset=args.dataset,
            older_than_minutes=args.older_than_minutes,
        )
        print(f"ingest_stale_reset|{args.dataset}|{count}")
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
            archive_raw=args.archive_raw,
        )
        qfq = load_market_daily_bars(
            "stock_qfq",
            "qfq",
            args.start_date,
            args.end_date,
            args.limit_tables,
            archive_raw=args.archive_raw,
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
    elif args.command == "backfill-features":
        window = derive_feature_backfill_window(
            start_date=args.start_date,
            end_date=args.end_date,
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
        )
        if window["start_date"] is None or window["end_date"] is None:
            print("feature_backfill|dates|0")
            print("feature_backfill|rows|0")
            return
        result = compute_and_store_p0_features_range(
            start_date=str(window["start_date"]),
            end_date=str(window["end_date"]),
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
            workers=args.workers,
            skip_complete=args.skip_complete,
        )
        total = int(result["feature_rows"].sum()) if not result.empty else 0
        print(f"feature_backfill|dates|{len(result)}")
        print(f"feature_backfill|rows|{total}")
    elif args.command == "labels":
        print(f"labels_stored|{compute_and_store_labels(args.end_date)}")
    elif args.command == "backfill-labels":
        window = derive_label_backfill_window(
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=args.horizons,
            adjust_type=args.adjust_type,
        )
        if window["start_date"] is None or window["end_date"] is None:
            print("labels_backfill|dates|0")
            print("labels_backfill|rows|0")
            return
        count = compute_and_store_labels(
            str(window["end_date"]),
            start_date=str(window["start_date"]),
            horizons=args.horizons,
        )
        print(f"labels_backfill|start_date|{window['start_date']}")
        print(f"labels_backfill|end_date|{window['end_date']}")
        print(f"labels_backfill|dates|{window['date_count']}")
        print(f"labels_backfill|rows|{count}")
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
    elif args.command == "build-universe":
        config = build_universe_config_from_args(args)
        result = UniverseService().build_universe(config)
        build_universe_artifacts(result=result, output_dir=args.output)
        print(f"universe_build|output|{args.output}")
        print(f"universe_build|included|{result.included_count}")
        print(f"universe_build|excluded|{result.excluded_count}")
    elif args.command == "explain-universe":
        config = build_universe_config_from_args(args)
        member = UniverseService().explain_stock(args.code, args.date, config)
        print(universe_member_to_json(member))
    elif args.command == "check-watchlist-universe":
        watchlist_codes = load_watchlist_codes(args.watchlist)
        config = build_universe_config_from_args(
            args,
            watchlist_codes=watchlist_codes,
        )
        result = UniverseService().build_universe(config)
        build_universe_artifacts(result=result, output_dir=args.output)
        print(f"watchlist_universe|output|{args.output}")
        print(f"watchlist_universe|members|{result.total_candidates}")
        print(f"watchlist_universe|included|{result.included_count}")


def main() -> None:
    main_for_args()


if __name__ == "__main__":
    main()
