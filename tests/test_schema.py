from stock_research.cli import build_parser, format_progress_bar
from stock_research.schema import CREATE_RESEARCH_EXTENSION_SQL, CREATE_TABLES_SQL


def test_schema_contains_core_tables():
    sql = CREATE_TABLES_SQL
    assert "CREATE TABLE IF NOT EXISTS asset_master" in sql
    assert "CREATE TABLE IF NOT EXISTS market_daily_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS feature_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS label_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS selection_result" in sql
    assert "CREATE TABLE IF NOT EXISTS data_quality_check" in sql


def test_schema_uses_replay_keys():
    sql = CREATE_TABLES_SQL
    assert "run_id" in sql
    assert "feature_version" in sql
    assert "label_version" in sql
    assert "score_version" in sql


def test_schema_creates_backtest_tables():
    assert "CREATE TABLE IF NOT EXISTS backtest_run" in CREATE_TABLES_SQL
    assert "CREATE TABLE IF NOT EXISTS backtest_trade" in CREATE_TABLES_SQL
    assert "CREATE TABLE IF NOT EXISTS backtest_summary" in CREATE_TABLES_SQL
    assert "CREATE TABLE IF NOT EXISTS backtest_equity_curve" in CREATE_TABLES_SQL
    assert "idx_backtest_trade_run_holding" in CREATE_TABLES_SQL
    assert "idx_backtest_equity_curve_run_date" in CREATE_TABLES_SQL


def test_research_extension_creates_schemas_and_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE SCHEMA IF NOT EXISTS raw_akshare" in sql
    assert "CREATE SCHEMA IF NOT EXISTS raw_baostock" in sql
    assert "CREATE SCHEMA IF NOT EXISTS core" in sql
    assert "CREATE SCHEMA IF NOT EXISTS finance" in sql
    assert "CREATE SCHEMA IF NOT EXISTS market" in sql
    assert "CREATE SCHEMA IF NOT EXISTS factor" in sql
    assert "CREATE SCHEMA IF NOT EXISTS backtest" in sql
    assert "CREATE SCHEMA IF NOT EXISTS ingest" in sql
    assert "CREATE TABLE IF NOT EXISTS core.asset_master" in sql
    assert "CREATE TABLE IF NOT EXISTS core.asset_status_daily" in sql
    assert "CREATE TABLE IF NOT EXISTS core.industry_membership" in sql
    assert "CREATE TABLE IF NOT EXISTS market.index_daily_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS market.industry_daily_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.income_statement" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.balance_sheet" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.cash_flow" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.indicator_quarter" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.share_capital_event" in sql
    assert "CREATE TABLE IF NOT EXISTS raw_akshare.finance_payload" in sql
    assert "CREATE TABLE IF NOT EXISTS raw_baostock.finance_payload" in sql
    assert "CREATE TABLE IF NOT EXISTS ingest.batch_job" in sql
    assert "CREATE TABLE IF NOT EXISTS ingest.batch_event" in sql
    assert "CREATE TABLE IF NOT EXISTS factor.factor_daily" in sql
    assert "CREATE TABLE IF NOT EXISTS factor.stock_score_daily" in sql


def test_research_extension_enforces_point_in_time_columns():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "report_period date NOT NULL" in sql
    assert "announcement_date date NOT NULL" in sql
    assert "idx_finance_indicator_quarter_pit" in sql
    assert "idx_finance_income_statement_pit" in sql
    assert "idx_core_industry_membership_window" in sql
    assert "idx_ingest_batch_job_status" in sql
    assert "idx_factor_daily_lookup" in sql
    assert "idx_stock_score_daily_rank" in sql


def test_cli_accepts_apply_research_schema_command():
    args = build_parser().parse_args(["apply-research-schema"])
    assert args.command == "apply-research-schema"


def test_cli_accepts_core_data_commands():
    sync_args = build_parser().parse_args(["sync-core-assets"])
    assert sync_args.command == "sync-core-assets"

    status_args = build_parser().parse_args(
        [
            "build-asset-status",
            "--start-date",
            "2026-05-06",
            "--end-date",
            "2026-05-08",
        ]
    )
    assert status_args.command == "build-asset-status"
    assert status_args.start_date == "2026-05-06"
    assert status_args.end_date == "2026-05-08"

    industry_bar_args = build_parser().parse_args(
        [
            "build-industry-bars",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-08",
            "--industry-system",
            "csrc",
        ]
    )
    assert industry_bar_args.command == "build-industry-bars"
    assert industry_bar_args.start_date == "2026-05-01"
    assert industry_bar_args.end_date == "2026-05-08"
    assert industry_bar_args.industry_system == "csrc"


def test_cli_accepts_baostock_ingestion_commands():
    industry_args = build_parser().parse_args(
        ["sync-industry-memberships", "--trade-date", "2026-05-08"]
    )
    assert industry_args.command == "sync-industry-memberships"
    assert industry_args.trade_date == "2026-05-08"

    index_args = build_parser().parse_args(
        [
            "sync-index-bars",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-08",
        ]
    )
    assert index_args.command == "sync-index-bars"
    assert index_args.start_date == "2026-05-01"
    assert index_args.end_date == "2026-05-08"

    finance_args = build_parser().parse_args(
        [
            "sync-baostock-finance",
            "--year",
            "2025",
            "--quarter",
            "4",
            "--limit",
            "20",
            "--offset",
            "40",
        ]
    )
    assert finance_args.command == "sync-baostock-finance"
    assert finance_args.year == 2025
    assert finance_args.quarter == 4
    assert finance_args.limit == 20
    assert finance_args.offset == 40


def test_cli_accepts_ingest_batch_commands():
    create_args = build_parser().parse_args(
        [
            "create-ingest-jobs",
            "--dataset",
            "baostock-finance",
            "--start-year",
            "1990",
            "--end-year",
            "2025",
            "--batch-size",
            "50",
        ]
    )
    assert create_args.command == "create-ingest-jobs"
    assert create_args.dataset == "baostock-finance"
    assert create_args.start_year == 1990
    assert create_args.end_year == 2025
    assert create_args.batch_size == 50

    run_args = build_parser().parse_args(
        ["run-ingest-jobs", "--dataset", "baostock-finance", "--limit-jobs", "3"]
    )
    assert run_args.command == "run-ingest-jobs"
    assert run_args.limit_jobs == 3

    status_args = build_parser().parse_args(
        ["ingest-status", "--dataset", "baostock-finance"]
    )
    assert status_args.command == "ingest-status"
    assert status_args.dataset == "baostock-finance"


def test_format_progress_bar():
    assert format_progress_bar(0, 10, width=10) == "[----------]"
    assert format_progress_bar(5, 10, width=10) == "[#####-----]"
    assert format_progress_bar(10, 10, width=10) == "[##########]"
