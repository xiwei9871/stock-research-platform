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


def test_research_extension_includes_factor_eval_gate_tables():
    assert "CREATE TABLE IF NOT EXISTS factor.factor_eval_run" in CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS factor.factor_approval" in CREATE_RESEARCH_EXTENSION_SQL
    assert "idx_factor_eval_run_factor" in CREATE_RESEARCH_EXTENSION_SQL


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

    loop_args = build_parser().parse_args(
        [
            "run-ingest-loop",
            "--dataset",
            "baostock-finance",
            "--jobs-per-round",
            "50",
            "--report-target",
            "oc_group",
            "--report-account",
            "jarvis",
            "--sleep-seconds",
            "0",
            "--max-rounds",
            "1",
            "--report-dry-run",
        ]
    )
    assert loop_args.command == "run-ingest-loop"
    assert loop_args.dataset == "baostock-finance"
    assert loop_args.jobs_per_round == 50
    assert loop_args.report_target == "oc_group"
    assert loop_args.report_account == "jarvis"
    assert loop_args.sleep_seconds == 0
    assert loop_args.max_rounds == 1
    assert loop_args.report_dry_run is True


def test_format_progress_bar():
    assert format_progress_bar(0, 10, width=10) == "[----------]"
    assert format_progress_bar(5, 10, width=10) == "[#####-----]"
    assert format_progress_bar(10, 10, width=10) == "[##########]"


def test_cli_main_runs_ingest_loop_and_prints_outputs(monkeypatch, capsys):
    from stock_research import cli

    calls = []
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "run-ingest-loop",
            "--dataset",
            "baostock-finance",
            "--jobs-per-round",
            "2",
            "--report-target",
            "oc_group",
            "--sleep-seconds",
            "0",
            "--max-rounds",
            "1",
            "--report-dry-run",
        ],
    )

    def fake_run_loop(dataset, **kwargs):
        kwargs["report"](
            {
                "dataset": "baostock-finance",
                "round": 1,
                "attempted": 2,
                "success": 2,
                "failed": 0,
                "rows_read": 100,
                "rows_written": 0,
                "status_counts": {"success": 2, "pending": 0},
                "recent_jobs": [],
                "done": True,
            }
        )
        calls.append(("run_loop", dataset, kwargs))
        return {
            "rounds": 1,
            "attempted": 2,
            "success": 2,
            "failed": 0,
            "done": True,
        }

    monkeypatch.setattr(cli, "run_ingest_loop_for_service", fake_run_loop)
    monkeypatch.setattr(
        cli,
        "send_openclaw_feishu_message",
        lambda **kwargs: calls.append(("send", kwargs)),
    )

    cli.main()

    captured = capsys.readouterr()
    assert "A股财务数据补齐进度" in captured.out
    assert "ingest_loop_rounds|1" in captured.out
    assert "ingest_loop_done|True" in captured.out
    assert calls[0][0] == "send"
    assert calls[0][1]["target"] == "oc_group"
    assert calls[0][1]["account"] == "jarvis"
    assert calls[0][1]["dry_run"] is True
    assert calls[1][0] == "run_loop"
    assert calls[1][1] == "baostock-finance"
    assert calls[1][2]["jobs_per_round"] == 2


def test_run_ingest_loop_notification_failure_does_not_abort(monkeypatch, capsys):
    import stock_research.cli as cli

    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "run-ingest-loop",
            "--dataset",
            "baostock-finance",
            "--jobs-per-round",
            "2",
            "--sleep-seconds",
            "0",
            "--max-rounds",
            "1",
            "--report-target",
            "oc_group",
        ],
    )

    monkeypatch.setattr(
        cli,
        "run_ingest_loop_for_service",
        lambda dataset, **kwargs: (
            kwargs["report"](
                {
                    "dataset": "baostock-finance",
                    "round": 1,
                    "attempted": 2,
                    "success": 2,
                    "failed": 0,
                    "rows_read": 100,
                    "rows_written": 0,
                    "status_counts": {"success": 2, "pending": 0},
                    "recent_jobs": [],
                    "done": True,
                }
            )
            or {
                "rounds": 1,
                "attempted": 2,
                "success": 2,
                "failed": 0,
                "done": True,
            }
        ),
    )

    def boom(**kwargs):
        raise RuntimeError("feishu down")

    monkeypatch.setattr(cli, "send_openclaw_feishu_message", boom)

    cli.main()

    captured = capsys.readouterr()
    assert "ingest_loop_rounds|1" in captured.out
    assert "ingest_loop_done|True" in captured.out
    assert "ingest_loop_report_failed|RuntimeError|feishu down" in captured.err
