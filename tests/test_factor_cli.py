import importlib
from types import SimpleNamespace

import pytest

import stock_research.cli as cli
from stock_research.cli import build_parser
import stock_research.technical_feature_store as technical_feature_store


def test_cli_accepts_build_factor_daily_command():
    args = build_parser().parse_args(
        [
            "build-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--lookback-bars",
            "130",
            "--industry-system",
            "csrc",
        ]
    )

    assert args.command == "build-factor-daily"
    assert args.trade_date == "2026-05-08"
    assert args.lookback_bars == 130
    assert args.industry_system == "csrc"


def test_cli_accepts_backfill_feature_daily_command():
    args = build_parser().parse_args(
        [
            "backfill-features",
            "--lookback-bars",
            "130",
            "--workers",
            "4",
            "--skip-complete",
        ]
    )

    assert args.command == "backfill-features"
    assert args.start_date is None
    assert args.end_date is None
    assert args.lookback_bars == 130
    assert args.workers == 4
    assert args.skip_complete is True


def test_cli_accepts_backfill_factor_daily_command():
    args = build_parser().parse_args(
        [
            "backfill-factor-daily",
            "--lookback-bars",
            "130",
            "--industry-system",
            "csrc",
            "--workers",
            "4",
            "--skip-complete",
            "--progress-interval",
            "10",
            "--exact-window",
        ]
    )

    assert args.command == "backfill-factor-daily"
    assert args.start_date is None
    assert args.end_date is None
    assert args.lookback_bars == 130
    assert args.industry_system == "csrc"
    assert args.workers == 4
    assert args.skip_complete is True
    assert args.progress_interval == 10
    assert args.exact_window is True


def test_cli_accepts_report_delivery_local_command():
    args = build_parser().parse_args(
        [
            "report-delivery-local",
            "--trade-date",
            "2026-05-19",
            "--input-dir",
            "inputs/a",
            "--input-dir",
            "inputs/b",
            "--report-dir",
            "reports/a",
            "--run-card-dir",
            "run_cards/a",
            "--artifact-path",
            "artifacts/a.json",
            "--output-dir",
            "outputs/delivery",
        ]
    )

    assert args.command == "report-delivery-local"
    assert args.trade_date == "2026-05-19"
    assert args.input_dir == ["inputs/a", "inputs/b"]
    assert args.report_dir == ["reports/a"]
    assert args.run_card_dir == ["run_cards/a"]
    assert args.artifact_path == ["artifacts/a.json"]
    assert args.output_dir == "outputs/delivery"
    assert args.dry_run is True

    non_dry_run_args = build_parser().parse_args(
        [
            "report-delivery-local",
            "--trade-date",
            "2026-05-19",
            "--output-dir",
            "outputs/delivery",
            "--no-dry-run",
        ]
    )

    assert non_dry_run_args.dry_run is False


def test_cli_accepts_report_delivery_openclaw_export_command():
    args = build_parser().parse_args(
        [
            "report-delivery-openclaw-export",
            "--trade-date",
            "2026-05-20",
            "--manifest",
            "outputs/delivery/manifest.json",
            "--output-dir",
            "outputs/openclaw",
            "--include-all",
            "--min-severity",
            "medium",
            "--no-dry-run",
        ]
    )

    assert args.command == "report-delivery-openclaw-export"
    assert args.trade_date == "2026-05-20"
    assert args.manifest == "outputs/delivery/manifest.json"
    assert args.output_dir == "outputs/openclaw"
    assert args.include_all is True
    assert args.min_severity == "medium"
    assert args.dry_run is False


def test_cli_accepts_backfill_technical_features_daily_command():
    args = build_parser().parse_args(
        [
            "backfill-technical-features-daily",
            "--lookback-bars",
            "260",
            "--adjust-type",
            "qfq",
            "--workers",
            "3",
            "--skip-complete",
            "--progress-interval",
            "5",
            "--source-data-version",
            "market_daily_bar:qfq@v2",
        ]
    )

    assert args.command == "backfill-technical-features-daily"
    assert args.start_date is None
    assert args.end_date is None
    assert args.lookback_bars == 260
    assert args.adjust_type == "qfq"
    assert args.workers == 3
    assert args.skip_complete is True
    assert args.progress_interval == 5
    assert args.source_data_version == "market_daily_bar:qfq@v2"


def test_cli_accepts_benchmark_technical_feature_backfill_command():
    args = build_parser().parse_args(
        [
            "benchmark-technical-feature-backfill",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-06",
            "--strategy",
            "parallel_dates",
            "--workers",
            "4",
            "--bench-tag",
            "demo",
            "--lookback-bars",
            "260",
            "--adjust-type",
            "qfq",
        ]
    )

    assert args.command == "benchmark-technical-feature-backfill"
    assert args.start_date == "2026-05-01"
    assert args.end_date == "2026-05-06"
    assert args.strategy == "parallel_dates"
    assert args.workers == 4
    assert args.bench_tag == "demo"
    assert args.lookback_bars == 260
    assert args.adjust_type == "qfq"


def test_cli_accepts_technical_feature_gap_check_command():
    args = build_parser().parse_args(
        [
            "technical-feature-gap-check",
            "--start-date",
            "2024-03-01",
            "--end-date",
            "2024-03-31",
            "--adjust-type",
            "hfq",
            "--calc-version",
            "v2",
            "--source-data-version",
            "market_daily_bar:hfq@custom",
        ]
    )

    assert args.command == "technical-feature-gap-check"
    assert args.start_date == "2024-03-01"
    assert args.end_date == "2024-03-31"
    assert args.adjust_type == "hfq"
    assert args.calc_version == "v2"
    assert args.source_data_version == "market_daily_bar:hfq@custom"


def test_cli_accepts_technical_feature_promotion_audit_command():
    args = build_parser().parse_args(
        [
            "technical-feature-promotion-audit",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-05-13",
            "--adjust-type",
            "qfq",
            "--feature-source",
            "computed_on_fly",
            "--output-dir",
            "outputs/research",
        ]
    )

    assert args.command == "technical-feature-promotion-audit"
    assert args.start_date == "2024-01-01"
    assert args.end_date == "2026-05-13"
    assert args.adjust_type == "qfq"
    assert args.feature_source == "computed_on_fly"
    assert args.output_dir == "outputs/research"


def test_cli_technical_feature_gap_check_uses_shared_default_calc_version(monkeypatch):
    import stock_research.cli as cli

    monkeypatch.setattr(
        technical_feature_store,
        "TECHNICAL_FEATURE_CALC_VERSION",
        "shared_v3",
    )
    reloaded = importlib.reload(cli)

    args = reloaded.build_parser().parse_args(
        [
            "technical-feature-gap-check",
            "--start-date",
            "2024-03-01",
            "--end-date",
            "2024-03-31",
        ]
    )

    assert args.calc_version == "shared_v3"


def test_cli_accepts_load_bars_archive_raw_flag():
    args = build_parser().parse_args(
        [
            "load-bars",
            "--start-date",
            "2026-05-06",
            "--end-date",
            "2026-05-06",
            "--limit-tables",
            "1",
            "--archive-raw",
        ]
    )

    assert args.command == "load-bars"
    assert args.start_date == "2026-05-06"
    assert args.end_date == "2026-05-06"
    assert args.limit_tables == 1
    assert args.archive_raw is True


def test_cli_accepts_retention_execution_constraint_flags():
    args = build_parser().parse_args(
        [
            "retention-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--commission-bps",
            "5",
            "--stamp-duty-bps",
            "10",
            "--slippage-bps",
            "8",
            "--min-amount",
            "30000000",
        ]
    )

    assert args.commission_bps == 5.0
    assert args.stamp_duty_bps == 10.0
    assert args.slippage_bps == 8.0
    assert args.min_amount == 30000000.0


def test_cli_accepts_sync_index_constituents_command():
    args = build_parser().parse_args(
        [
            "sync-index-constituents",
            "--trade-date",
            "2024-05-31",
            "--index-ids",
            "CSI_300,CSI_500",
            "--source-version",
            "baostock_snapshot_v1",
        ]
    )

    assert args.command == "sync-index-constituents"
    assert args.trade_date == "2024-05-31"
    assert args.index_ids == ["CSI_300", "CSI_500"]
    assert args.source_version == "baostock_snapshot_v1"


def test_cli_accepts_phase6_industry_history_commands():
    benchmark_args = build_parser().parse_args(
        [
            "benchmark-industry-day",
            "--trade-date",
            "2024-05-31",
            "--industry-system",
            "csrc",
            "--adjust-type",
            "hfq",
        ]
    )

    assert benchmark_args.command == "benchmark-industry-day"
    assert benchmark_args.trade_date == "2024-05-31"
    assert benchmark_args.industry_system == "csrc"
    assert benchmark_args.adjust_type == "hfq"

    backfill_args = build_parser().parse_args(
        [
            "backfill-industry-history",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2024-05-31",
            "--max-dates",
            "2",
            "--frequency",
            "monthly",
            "--industry-system",
            "csrc",
            "--adjust-type",
            "hfq",
        ]
    )

    assert backfill_args.command == "backfill-industry-history"
    assert backfill_args.start_date == "2024-05-27"
    assert backfill_args.end_date == "2024-05-31"
    assert backfill_args.max_dates == 2
    assert backfill_args.frequency == "monthly"
    assert backfill_args.industry_system == "csrc"
    assert backfill_args.adjust_type == "hfq"

    no_cache_args = build_parser().parse_args(
        ["benchmark-industry-day", "--trade-date", "2024-05-31", "--no-cache"]
    )
    assert no_cache_args.use_cache is False


def test_cli_accepts_minute_backfill_watchdog_command():
    args = build_parser().parse_args(
        [
            "minute-backfill-watchdog",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-31",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--max-jobs",
            "200",
            "--workers",
            "3",
            "--stale-after-minutes",
            "45",
            "--run-timeout-seconds",
            "1200",
            "--output-dir",
            "outputs/watchdog",
            "--report-target",
            "chat:test",
            "--report-account",
            "ops",
            "--openclaw-bin",
            "/opt/bin/openclaw",
            "--report-dry-run",
        ]
    )

    assert args.command == "minute-backfill-watchdog"
    assert args.start_date == "2024-01-01"
    assert args.end_date == "2024-03-31"
    assert args.freq == "5min"
    assert args.adjust_types == ["raw", "qfq"]
    assert args.max_jobs == 200
    assert args.workers == 3
    assert args.stale_after_minutes == 45
    assert args.run_timeout_seconds == 1200
    assert args.output_dir == "outputs/watchdog"
    assert args.report_target == "chat:test"
    assert args.report_account == "ops"
    assert args.openclaw_bin == "/opt/bin/openclaw"
    assert args.report_dry_run is True


def test_cli_accepts_generic_backfill_watchdog_command_for_minute_adapter():
    args = build_parser().parse_args(
        [
            "backfill-watchdog",
            "--adapter",
            "minute",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-31",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--max-jobs",
            "200",
            "--workers",
            "3",
            "--stale-after-minutes",
            "45",
            "--run-timeout-seconds",
            "1200",
            "--output-dir",
            "outputs/watchdog",
            "--report-target",
            "chat:test",
            "--report-account",
            "ops",
            "--openclaw-bin",
            "/opt/bin/openclaw",
            "--report-dry-run",
        ]
    )

    assert args.command == "backfill-watchdog"
    assert args.adapter == "minute"
    assert args.start_date == "2024-01-01"
    assert args.end_date == "2024-03-31"
    assert args.freq == "5min"
    assert args.adjust_types == ["raw", "qfq"]
    assert args.max_jobs == 200
    assert args.workers == 3
    assert args.stale_after_minutes == 45
    assert args.run_timeout_seconds == 1200
    assert args.output_dir == "outputs/watchdog"
    assert args.report_target == "chat:test"
    assert args.report_account == "ops"
    assert args.openclaw_bin == "/opt/bin/openclaw"
    assert args.report_dry_run is True


def test_cli_accepts_generic_backfill_watchdog_command_for_technical_features_adapter():
    args = build_parser().parse_args(
        [
            "backfill-watchdog",
            "--adapter",
            "technical-features",
            "--start-date",
            "1991-01-01",
            "--end-date",
            "2026-05-14",
            "--adjust-type",
            "qfq",
            "--lookback-bars",
            "260",
            "--source-data-version",
            "market_daily_bar:qfq",
            "--max-jobs",
            "50",
            "--workers",
            "2",
            "--stale-after-minutes",
            "20",
            "--run-timeout-seconds",
            "1800",
            "--sleep-between-runs-seconds",
            "15",
            "--report-target",
            "chat:test",
            "--report-account",
            "ops",
            "--report-dry-run",
        ]
    )

    assert args.command == "backfill-watchdog"
    assert args.adapter == "technical-features"
    assert args.start_date == "1991-01-01"
    assert args.end_date == "2026-05-14"
    assert args.adjust_type == "qfq"
    assert args.lookback_bars == 260
    assert args.source_data_version == "market_daily_bar:qfq"
    assert args.max_jobs == 50
    assert args.workers == 2
    assert args.stale_after_minutes == 20
    assert args.run_timeout_seconds == 1800
    assert args.sleep_between_runs_seconds == 15
    assert args.report_target == "chat:test"
    assert args.report_account == "ops"
    assert args.report_dry_run is True


def test_cli_accepts_phase4_action_commands():
    factor_args = build_parser().parse_args(
        [
            "build-adjustment-factors",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2024-05-31",
            "--source-version",
            "derived_v1",
        ]
    )

    assert factor_args.command == "build-adjustment-factors"
    assert factor_args.start_date == "2024-05-27"
    assert factor_args.end_date == "2024-05-31"
    assert factor_args.source_version == "derived_v1"

    action_args = build_parser().parse_args(
        [
            "build-corporate-actions",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2024-05-31",
            "--source-version",
            "actions_v1",
        ]
    )

    assert action_args.command == "build-corporate-actions"
    assert action_args.start_date == "2024-05-27"
    assert action_args.end_date == "2024-05-31"
    assert action_args.source_version == "actions_v1"


def test_cli_accepts_score_factor_daily_command():
    args = build_parser().parse_args(
        [
            "score-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
        ]
    )

    assert args.command == "score-factor-daily"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"


def test_cli_accepts_show_top_scores_command():
    args = build_parser().parse_args(
        [
            "show-top-scores",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "30",
        ]
    )

    assert args.command == "show-top-scores"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"
    assert args.top_n == 30


def test_cli_accepts_eval_factor_command():
    args = build_parser().parse_args(
        [
            "eval-factor",
            "--factor-name",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
            "--horizon",
            "5",
            "--quantiles",
            "5",
            "--top-n",
            "30",
        ]
    )

    assert args.command == "eval-factor"
    assert args.factor_name == "ret_20"
    assert args.horizon == 5
    assert args.quantiles == 5
    assert args.top_n == 30


def test_cli_accepts_daily_factor_pipeline_command():
    args = build_parser().parse_args(
        [
            "run-daily-factor-pipeline",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "30",
            "--lookback-bars",
            "130",
        ]
    )

    assert args.command == "run-daily-factor-pipeline"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"
    assert args.top_n == 30
    assert args.lookback_bars == 130


def test_cli_accepts_daily_incremental_command():
    args = build_parser().parse_args(
        [
            "run-daily-incremental",
            "--trade-date",
            "2026-05-12",
            "--score-version",
            "manual_v1",
            "--top-n",
            "30",
            "--lookback-bars",
            "130",
            "--adjust-type",
            "qfq",
            "--source-service",
            "stock_qfq",
            "--industry-system",
            "sw",
            "--start-at",
            "build_factor_daily",
            "--dry-run",
        ]
    )

    assert args.command == "run-daily-incremental"
    assert args.trade_date == "2026-05-12"
    assert args.score_version == "manual_v1"
    assert args.top_n == 30
    assert args.lookback_bars == 130
    assert args.adjust_type == "qfq"
    assert args.source_service == "stock_qfq"
    assert args.industry_system == "sw"
    assert args.start_at == "build_factor_daily"
    assert args.only_step is None
    assert args.dry_run is True


def test_cli_accepts_daily_incremental_only_step_command():
    args = build_parser().parse_args(
        [
            "run-daily-incremental",
            "--trade-date",
            "2026-05-12",
            "--only-step",
            "score_approved_factors",
            "--dry-run",
        ]
    )

    assert args.start_at is None
    assert args.only_step == "score_approved_factors"


def test_cli_rejects_daily_incremental_conflicting_resume_options():
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "run-daily-incremental",
                "--trade-date",
                "2026-05-12",
                "--start-at",
                "build_factor_daily",
                "--only-step",
                "score_approved_factors",
            ]
        )


def test_cli_accepts_daily_incremental_recording_flags():
    args = build_parser().parse_args(
        [
            "run-daily-incremental",
            "--trade-date",
            "2026-05-12",
            "--apply-daily-run-schema",
            "--record-run",
        ]
    )

    assert args.apply_daily_run_schema is True
    assert args.record_run is True


def test_cli_accepts_export_research_snapshot_command():
    args = build_parser().parse_args(
        [
            "export-research-snapshot",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-12",
            "--score-version",
            "manual_v1",
            "--output-dir",
            "/tmp/snapshot",
        ]
    )

    assert args.command == "export-research-snapshot"
    assert args.start_date == "2026-01-01"
    assert args.end_date == "2026-05-12"
    assert args.score_version == "manual_v1"
    assert args.output_dir == "/tmp/snapshot"


def test_cli_accepts_migration_safety_check_command():
    args = build_parser().parse_args(
        [
            "migration-safety-check",
            "--backup-path",
            "/tmp/stock_research.dump",
            "--source-service",
            "stock_research",
            "--restore-service",
            "stock_research_restore_check",
            "--dry-run",
        ]
    )

    assert args.command == "migration-safety-check"
    assert args.backup_path == "/tmp/stock_research.dump"
    assert args.source_service == "stock_research"
    assert args.restore_service == "stock_research_restore_check"
    assert args.dry_run is True


def test_cli_accepts_daily_research_report_command():
    args = build_parser().parse_args(
        [
            "run-daily-research-report",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "30",
            "--index-id",
            "CSI300",
            "--industry-system",
            "csrc",
            "--reports-dir",
            "/tmp/reports",
            "--apply-report-run-schema",
            "--record-run",
        ]
    )

    assert args.command == "run-daily-research-report"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"
    assert args.top_n == 30
    assert args.index_id == "CSI300"
    assert args.industry_system == "csrc"
    assert args.reports_dir == "/tmp/reports"
    assert args.apply_report_run_schema is True
    assert args.record_run is True


def test_cli_accepts_evaluate_factor_gate_command():
    args = build_parser().parse_args(
        [
            "evaluate-factor-gate",
            "--factor-name",
            "alpha101_delta_close_1_rank",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
            "--horizons",
            "5,10,20,60",
            "--primary-horizon",
            "5",
            "--score-version",
            "manual_v1",
        ]
    )

    assert args.command == "evaluate-factor-gate"
    assert args.factor_name == "alpha101_delta_close_1_rank"
    assert args.horizons == "5,10,20,60"
    assert args.primary_horizon == 5


def test_cli_accepts_evaluate_factor_gate_batch_command():
    args = build_parser().parse_args(
        [
            "evaluate-factor-gate-batch",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ]
    )

    assert args.command == "evaluate-factor-gate-batch"
    assert args.factor_names is None
    assert args.horizons == "5,10,20,60"


def test_cli_accepts_evaluate_factor_gate_batch_explicit_factor_names():
    args = build_parser().parse_args(
        [
            "evaluate-factor-gate-batch",
            "--factor-names",
            "alpha101_delta_close_1_rank,gtja191_amount_momentum_5_10",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ]
    )

    assert args.factor_names == [
        "alpha101_delta_close_1_rank",
        "gtja191_amount_momentum_5_10",
    ]


@pytest.mark.parametrize("factor_names", ["", ",", "ret_20,,qlib_ret_5"])
def test_cli_rejects_invalid_evaluate_factor_gate_batch_factor_names(factor_names):
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "evaluate-factor-gate-batch",
                "--factor-names",
                factor_names,
                "--start-date",
                "2026-01-01",
                "--end-date",
                "2026-05-08",
            ]
        )


def test_build_factor_daily_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "build_and_store_factor_daily", lambda **kwargs: 42)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "build-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--lookback-bars",
            "130",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "factor_daily_stored|42"


def test_report_delivery_local_cli_prints_manifest_summary(monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    def fake_deliver_local_reports(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status="dry_run",
            artifact_count=3,
            manifest_path="outputs/delivery/manifest.json",
            output_dir="outputs/delivery",
            delivery_log_path="outputs/delivery/delivery_log.jsonl",
        )

    monkeypatch.setattr(cli, "deliver_local_reports", fake_deliver_local_reports)

    cli.main_for_args(
        [
            "report-delivery-local",
            "--trade-date",
            "2026-05-19",
            "--input-dir",
            "inputs/a",
            "--report-dir",
            "reports/a",
            "--run-card-dir",
            "run_cards/a",
            "--artifact-path",
            "artifacts/a.json",
            "--output-dir",
            "outputs/delivery",
        ]
    )

    assert calls == [
        {
            "trade_date": "2026-05-19",
            "input_dirs": ["inputs/a"],
            "report_dirs": ["reports/a"],
            "run_card_dirs": ["run_cards/a"],
            "artifact_paths": ["artifacts/a.json"],
            "output_dir": "outputs/delivery",
            "dry_run": True,
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "report_delivery|status|dry_run",
        "report_delivery|artifacts|3",
        "report_delivery|manifest|outputs/delivery/manifest.json",
        "report_delivery|output_dir|outputs/delivery",
        "report_delivery|delivery_log|outputs/delivery/delivery_log.jsonl",
    ]


def test_report_delivery_local_cli_allows_non_dry_run(monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    def fake_deliver_local_reports(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status="completed",
            artifact_count=1,
            manifest_path="outputs/delivery/manifest.json",
            output_dir="outputs/delivery",
            delivery_log_path=None,
        )

    monkeypatch.setattr(cli, "deliver_local_reports", fake_deliver_local_reports)

    cli.main_for_args(
        [
            "report-delivery-local",
            "--trade-date",
            "2026-05-19",
            "--output-dir",
            "outputs/delivery",
            "--no-dry-run",
        ]
    )

    assert calls == [
        {
            "trade_date": "2026-05-19",
            "input_dirs": [],
            "report_dirs": [],
            "run_card_dirs": [],
            "artifact_paths": [],
            "output_dir": "outputs/delivery",
            "dry_run": False,
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "report_delivery|status|completed",
        "report_delivery|artifacts|1",
        "report_delivery|manifest|outputs/delivery/manifest.json",
        "report_delivery|output_dir|outputs/delivery",
    ]


def test_report_delivery_openclaw_export_cli_prints_summary(monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    def fake_export(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status="dry_run",
            item_count=2,
            manifest_path="outputs/delivery/manifest.json",
            openclaw_manifest_path="outputs/openclaw/openclaw_manifest.json",
            openclaw_items_path="outputs/openclaw/items.jsonl",
            output_dir="outputs/openclaw",
            openclaw_delivery_log_path="outputs/openclaw/delivery_log.jsonl",
        )

    monkeypatch.setattr(cli, "openclaw_export", fake_export)

    cli.main_for_args(
        [
            "report-delivery-openclaw-export",
            "--trade-date",
            "2026-05-20",
            "--manifest",
            "outputs/delivery/manifest.json",
            "--output-dir",
            "outputs/openclaw",
            "--include-all",
            "--min-severity",
            "medium",
        ]
    )

    assert calls == [
        {
            "trade_date": "2026-05-20",
            "manifest_path": "outputs/delivery/manifest.json",
            "output_dir": "outputs/openclaw",
            "include_all": True,
            "min_severity": "medium",
            "dry_run": True,
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "report_delivery_openclaw|status|dry_run",
        "report_delivery_openclaw|item_count|2",
        "report_delivery_openclaw|manifest|outputs/openclaw/openclaw_manifest.json",
        "report_delivery_openclaw|items|outputs/openclaw/items.jsonl",
        "report_delivery_openclaw|output_dir|outputs/openclaw",
        "report_delivery_openclaw|log|outputs/openclaw/delivery_log.jsonl",
    ]


def test_cli_accepts_report_delivery_openclaw_send_command(monkeypatch):
    monkeypatch.delenv("OPENCLAW_ENDPOINT", raising=False)
    monkeypatch.delenv("OPENCLAW_TIMEOUT_SECONDS", raising=False)

    args = build_parser().parse_args(
        [
            "report-delivery-openclaw-send",
            "--trade-date",
            "2026-05-21",
            "--manifest",
            "outputs/openclaw/openclaw_manifest.json",
            "--items",
            "outputs/openclaw/openclaw_items.jsonl",
            "--output-dir",
            "outputs/openclaw_send/2026-05-21",
        ]
    )

    assert args.command == "report-delivery-openclaw-send"
    assert args.trade_date == "2026-05-21"
    assert args.manifest == "outputs/openclaw/openclaw_manifest.json"
    assert args.items == "outputs/openclaw/openclaw_items.jsonl"
    assert args.output_dir == "outputs/openclaw_send/2026-05-21"
    assert args.dry_run is True
    assert args.endpoint is None
    assert args.timeout_seconds == "10.0"
    assert args.retry_count == 0
    assert args.retry_backoff_seconds == 1.0
    assert args.allow_live_send is False
    assert args.limit is None
    assert args.route_allowlist == []
    assert args.severity_max is None
    assert args.test_mode is False
    assert not hasattr(args, "token")


def test_cli_unrelated_commands_ignore_invalid_openclaw_timeout_env(monkeypatch):
    monkeypatch.setenv("OPENCLAW_TIMEOUT_SECONDS", "not-a-number")

    args = build_parser().parse_args(
        [
            "build-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--lookback-bars",
            "130",
            "--industry-system",
            "csrc",
        ]
    )

    assert args.command == "build-factor-daily"
    assert args.trade_date == "2026-05-08"
    assert args.lookback_bars == 130
    assert args.industry_system == "csrc"


def test_report_delivery_openclaw_send_cli_rejects_invalid_timeout_env(monkeypatch):
    monkeypatch.setenv("OPENCLAW_TIMEOUT_SECONDS", "not-a-number")
    monkeypatch.delenv("OPENCLAW_ENDPOINT", raising=False)

    with pytest.raises(
        ValueError,
        match=r"report-delivery-openclaw-send: --timeout-seconds / OPENCLAW_TIMEOUT_SECONDS must be a finite number greater than 0",
    ):
        cli.main_for_args(
            [
                "report-delivery-openclaw-send",
                "--trade-date",
                "2026-05-21",
                "--manifest",
                "outputs/openclaw/openclaw_manifest.json",
                "--items",
                "outputs/openclaw/openclaw_items.jsonl",
                "--output-dir",
                "outputs/openclaw_send/2026-05-21",
            ]
        )


@pytest.mark.parametrize("timeout_value", ["0", "-1", "inf", "nan"])
def test_report_delivery_openclaw_send_cli_rejects_non_positive_or_non_finite_timeouts(
    monkeypatch, timeout_value
):
    monkeypatch.delenv("OPENCLAW_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OPENCLAW_ENDPOINT", raising=False)

    with pytest.raises(
        ValueError,
        match=r"report-delivery-openclaw-send: --timeout-seconds / OPENCLAW_TIMEOUT_SECONDS must be a finite number greater than 0",
    ):
        cli.main_for_args(
            [
                "report-delivery-openclaw-send",
                "--trade-date",
                "2026-05-21",
                "--manifest",
                "outputs/openclaw/openclaw_manifest.json",
                "--items",
                "outputs/openclaw/openclaw_items.jsonl",
                "--output-dir",
                "outputs/openclaw_send/2026-05-21",
                "--timeout-seconds",
                timeout_value,
            ]
        )


def test_report_delivery_openclaw_send_cli_dry_run_prints_summary(monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    class FakeOpenClawSender:
        def __init__(self, transport):
            calls.append({"transport": transport.__class__.__name__})

        def load_export(self, manifest_path, items_path):
            calls.append(
                {
                    "load_export_manifest_path": manifest_path,
                    "load_export_items_path": items_path,
                }
            )
            return {
                "manifest": {"trade_date": "2026-05-21"},
                "items": [],
                "manifest_path": manifest_path,
                "items_path": items_path,
            }

        def send_batch(self, *, manifest_path, items_path, config):
            calls.append(
                {
                    "manifest_path": manifest_path,
                    "items_path": items_path,
                    "config": config,
                }
            )
            assert config.dry_run is True
            assert config.endpoint == "https://openclaw.example.test/send"
            assert config.timeout_seconds == 12.5
            assert config.retry_count == 2
            assert config.retry_backoff_seconds == 0.75
            assert config.outbox_dir == "outputs/openclaw_send/2026-05-21"
            assert config.limit == 1
            assert config.allow_live_send is True
            assert config.route_allowlist == ["research_inbox"]
            assert config.severity_max == "low"
            assert config.test_mode is True
            return SimpleNamespace(
                send_id="openclaw-send:1:2026-05-21T09:00:00Z:outputs/openclaw/openclaw_manifest.json",
                channel="openclaw",
                status="dry_run",
                dry_run=True,
                item_count=1,
                sent_count=0,
                failed_count=0,
                skipped_count=0,
                preview_path="outputs/openclaw_send/2026-05-21/send_preview.json",
                send_log_path="outputs/openclaw_send/2026-05-21/send_log.jsonl",
            )

    monkeypatch.setattr(cli, "OpenClawSender", FakeOpenClawSender)
    monkeypatch.setenv("OPENCLAW_TOKEN", "secret-token")

    cli.main_for_args(
        [
            "report-delivery-openclaw-send",
            "--trade-date",
            "2026-05-21",
            "--manifest",
            "outputs/openclaw/openclaw_manifest.json",
            "--items",
            "outputs/openclaw/openclaw_items.jsonl",
            "--output-dir",
            "outputs/openclaw_send/2026-05-21",
            "--dry-run",
            "--endpoint",
            "https://openclaw.example.test/send",
            "--timeout-seconds",
            "12.5",
            "--retry-count",
            "2",
            "--retry-backoff-seconds",
            "0.75",
            "--allow-live-send",
            "--limit",
            "1",
            "--route-allowlist",
            "research_inbox",
            "--severity-max",
            "low",
            "--test-mode",
        ]
    )

    assert calls[0] == {"transport": "DryRunOpenClawTransport"}
    assert calls[1] == {
        "load_export_manifest_path": "outputs/openclaw/openclaw_manifest.json",
        "load_export_items_path": "outputs/openclaw/openclaw_items.jsonl",
    }
    assert calls[2]["manifest_path"] == "outputs/openclaw/openclaw_manifest.json"
    assert calls[2]["items_path"] == "outputs/openclaw/openclaw_items.jsonl"
    assert isinstance(calls[2]["config"], cli.OpenClawSendConfig)
    assert capsys.readouterr().out.splitlines() == [
        "report_delivery_openclaw_send|status|dry_run",
        "report_delivery_openclaw_send|dry_run|True",
        "report_delivery_openclaw_send|send_id|openclaw-send:1:2026-05-21T09:00:00Z:outputs/openclaw/openclaw_manifest.json",
        "report_delivery_openclaw_send|item_count|1",
        "report_delivery_openclaw_send|sent_count|0",
        "report_delivery_openclaw_send|failed_count|0",
        "report_delivery_openclaw_send|skipped_count|0",
        "report_delivery_openclaw_send|preview|outputs/openclaw_send/2026-05-21/send_preview.json",
        "report_delivery_openclaw_send|log|outputs/openclaw_send/2026-05-21/send_log.jsonl",
    ]


def test_report_delivery_openclaw_send_cli_no_dry_run_without_endpoint_fails_clearly(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("OPENCLAW_ENDPOINT", raising=False)
    monkeypatch.delenv("OPENCLAW_TOKEN", raising=False)
    monkeypatch.delenv("OPENCLAW_TIMEOUT_SECONDS", raising=False)

    manifest_path = tmp_path / "openclaw_manifest.json"
    items_path = tmp_path / "openclaw_items.jsonl"
    manifest_path.write_text(
        """
{
  "generated_at": "2026-05-21T09:00:00Z",
  "trade_date": "2026-05-21",
  "channel": "openclaw",
  "dry_run": true,
  "source_manifest_path": "outputs/report_delivery/2026-05-21/manifest.json",
  "item_count": 1,
  "items": [
    {
      "item_id": "openclaw:1",
      "artifact_id": "daily_topn_report:2026-05-21:abc",
      "report_type": "daily_topn_report",
      "openclaw_route": "research_inbox",
      "severity": "info"
    }
  ],
  "warnings": [],
  "errors": []
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    items_path.write_text(
        """
{"item_id":"openclaw:1","artifact_id":"daily_topn_report:2026-05-21:abc","report_type":"daily_topn_report","title":"Daily TopN","summary":"Daily TopN summary","severity":"info","requires_attention":false,"delivery_priority":10,"tags":["daily","topn"],"source_paths":["outputs/report_delivery/2026-05-21/artifacts/topn.md"],"evidence_paths":[],"run_card_path":null,"recommended_action":"review_topn_candidates","openclaw_route":"research_inbox","payload":{"title":"Daily TopN"}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="endpoint is required when dry_run is False"):
        cli.main_for_args(
            [
                "report-delivery-openclaw-send",
                "--trade-date",
                "2026-05-21",
                "--manifest",
                str(manifest_path),
                "--items",
                str(items_path),
                "--output-dir",
                str(tmp_path / "send"),
                "--no-dry-run",
                "--allow-live-send",
                "--limit",
                "1",
                "--route-allowlist",
                "research_inbox",
                "--severity-max",
                "low",
                "--test-mode",
            ]
        )


def test_report_delivery_openclaw_send_cli_reports_missing_sender_inputs_clearly(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("OPENCLAW_ENDPOINT", raising=False)
    monkeypatch.delenv("OPENCLAW_TOKEN", raising=False)

    manifest_path = tmp_path / "openclaw_manifest.json"
    items_path = tmp_path / "openclaw_items.jsonl"
    items_path.write_text("", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"report-delivery-openclaw-send: OpenClaw sender manifest not found: .*openclaw_manifest\.json",
    ):
        cli.main_for_args(
            [
                "report-delivery-openclaw-send",
                "--trade-date",
                "2026-05-21",
                "--manifest",
                str(manifest_path),
                "--items",
                str(items_path),
                "--output-dir",
                str(tmp_path / "send"),
            ]
        )


def test_report_delivery_openclaw_send_cli_fails_on_non_dry_run_send_failure(
    monkeypatch, capsys
):
    calls: list[dict[str, object]] = []

    class FakeOpenClawSender:
        def __init__(self, transport):
            calls.append({"transport": transport.__class__.__name__})

        def load_export(self, manifest_path, items_path):
            calls.append(
                {
                    "load_export_manifest_path": manifest_path,
                    "load_export_items_path": items_path,
                }
            )
            return {
                "manifest": {"trade_date": "2026-05-21"},
                "items": [],
                "manifest_path": manifest_path,
                "items_path": items_path,
            }

        def send_batch(self, *, manifest_path, items_path, config):
            calls.append(
                {
                    "manifest_path": manifest_path,
                    "items_path": items_path,
                    "config": config,
                }
            )
            assert config.dry_run is False
            return SimpleNamespace(
                send_id="openclaw-send:1:2026-05-21T09:00:00Z:outputs/openclaw/openclaw_manifest.json",
                channel="openclaw",
                status="failed",
                dry_run=False,
                item_count=1,
                sent_count=0,
                failed_count=1,
                skipped_count=0,
                preview_path="outputs/openclaw_send/2026-05-21/send_preview.json",
                send_log_path="outputs/openclaw_send/2026-05-21/send_log.jsonl",
            )

    monkeypatch.setattr(cli, "OpenClawSender", FakeOpenClawSender)
    monkeypatch.setenv("OPENCLAW_TOKEN", "secret-token")

    with pytest.raises(
        RuntimeError,
        match="non-dry-run send failed with status failed",
    ):
        cli.main_for_args(
            [
                "report-delivery-openclaw-send",
                "--trade-date",
                "2026-05-21",
                "--manifest",
                "outputs/openclaw/openclaw_manifest.json",
                "--items",
                "outputs/openclaw/openclaw_items.jsonl",
                "--output-dir",
                "outputs/openclaw_send/2026-05-21",
                "--no-dry-run",
                "--endpoint",
                "https://openclaw.example.test/send",
                "--allow-live-send",
                "--limit",
                "1",
                "--route-allowlist",
                "research_inbox",
                "--severity-max",
                "low",
                "--test-mode",
            ]
        )

    assert calls[0] == {"transport": "HttpOpenClawTransport"}
    assert calls[1] == {
        "load_export_manifest_path": "outputs/openclaw/openclaw_manifest.json",
        "load_export_items_path": "outputs/openclaw/openclaw_items.jsonl",
    }
    assert calls[2]["manifest_path"] == "outputs/openclaw/openclaw_manifest.json"
    assert calls[2]["items_path"] == "outputs/openclaw/openclaw_items.jsonl"
    assert isinstance(calls[2]["config"], cli.OpenClawSendConfig)
    assert capsys.readouterr().out.splitlines() == [
        "report_delivery_openclaw_send|status|failed",
        "report_delivery_openclaw_send|dry_run|False",
        "report_delivery_openclaw_send|send_id|openclaw-send:1:2026-05-21T09:00:00Z:outputs/openclaw/openclaw_manifest.json",
        "report_delivery_openclaw_send|item_count|1",
        "report_delivery_openclaw_send|sent_count|0",
        "report_delivery_openclaw_send|failed_count|1",
        "report_delivery_openclaw_send|skipped_count|0",
        "report_delivery_openclaw_send|preview|outputs/openclaw_send/2026-05-21/send_preview.json",
        "report_delivery_openclaw_send|log|outputs/openclaw_send/2026-05-21/send_log.jsonl",
    ]


def test_report_delivery_openclaw_send_cli_rejects_trade_date_mismatch(
    tmp_path, monkeypatch
):
    manifest_file = tmp_path / "openclaw_manifest.json"
    items_file = tmp_path / "openclaw_items.jsonl"
    manifest_file.write_text(
        """
{
  "generated_at": "2026-05-21T09:00:00Z",
  "trade_date": "2026-05-20",
  "channel": "openclaw",
  "dry_run": true,
  "source_manifest_path": "outputs/report_delivery/2026-05-20/manifest.json",
  "item_count": 1,
  "items": [],
  "warnings": [],
  "errors": []
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    items_file.write_text(
        """
{"item_id":"openclaw:1","artifact_id":"daily_topn_report:2026-05-20:abc","report_type":"daily_topn_report","title":"Daily TopN","summary":"Daily TopN summary","severity":"info","requires_attention":false,"delivery_priority":10,"tags":["daily","topn"],"source_paths":["outputs/report_delivery/2026-05-20/artifacts/topn.md"],"evidence_paths":[],"run_card_path":null,"recommended_action":"review_topn_candidates","openclaw_route":"research_inbox","payload":{"title":"Daily TopN"}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    class FakeOpenClawSender:
        def __init__(self, transport):
            self.transport = transport

        def load_export(self, manifest_path, items_path):
            assert manifest_path == str(manifest_file)
            assert items_path == str(items_file)
            return {
                "manifest": {"trade_date": "2026-05-20"},
                "items": [],
                "manifest_path": str(manifest_path),
                "items_path": str(items_path),
            }

        def send_batch(self, **kwargs):
            raise AssertionError("send_batch should not be called after a trade-date mismatch")

    monkeypatch.setattr(cli, "OpenClawSender", FakeOpenClawSender)

    with pytest.raises(
        ValueError,
        match=(
            r"report-delivery-openclaw-send: trade-date 2026-05-21 "
            r"does not match loaded manifest trade_date 2026-05-20"
        ),
    ):
        cli.main_for_args(
            [
                "report-delivery-openclaw-send",
                "--trade-date",
                "2026-05-21",
                "--manifest",
                str(manifest_file),
                "--items",
                str(items_file),
                "--output-dir",
                str(tmp_path / "send"),
            ]
        )


def test_report_delivery_openclaw_export_cli_rejects_trade_date_mismatch(monkeypatch):
    def fake_load_local_manifest(self, manifest_path):
        assert manifest_path == "outputs/delivery/manifest.json"
        return {"trade_date": "2026-05-21"}

    monkeypatch.setattr(cli.OpenClawExportAdapter, "load_local_manifest", fake_load_local_manifest)

    with pytest.raises(
        ValueError,
        match=(
            r"report-delivery-openclaw-export: trade-date 2026-05-20 "
            r"does not match manifest trade_date 2026-05-21"
        ),
    ):
        cli.main_for_args(
            [
                "report-delivery-openclaw-export",
                "--trade-date",
                "2026-05-20",
                "--manifest",
                "outputs/delivery/manifest.json",
                "--output-dir",
                "outputs/openclaw",
            ]
        )


def test_backfill_factor_daily_cli_prints_summary(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    def fake_backfill_factor_daily_range(**kwargs):
        assert kwargs["workers"] == 4
        assert kwargs["skip_complete"] is True
        kwargs["progress"]({"event": "start", "trade_date": "2026-05-01", "index": 1, "total": 2})
        kwargs["progress"](
            {
                "event": "done",
                "trade_date": "2026-05-01",
                "index": 1,
                "total": 2,
                "factor_rows": 10,
                "elapsed_seconds": 1.5,
            }
        )
        kwargs["progress"]({"event": "start", "trade_date": "2026-05-02", "index": 2, "total": 2})
        kwargs["progress"](
            {
                "event": "done",
                "trade_date": "2026-05-02",
                "index": 2,
                "total": 2,
                "factor_rows": 20,
                "elapsed_seconds": 2.0,
            }
        )
        return pd.DataFrame(
            [
                {"trade_date": "2026-05-01", "factor_rows": 10},
                {"trade_date": "2026-05-02", "factor_rows": 20},
            ]
        )

    monkeypatch.setattr(cli, "backfill_factor_daily_range", fake_backfill_factor_daily_range)
    monkeypatch.setattr(
        cli,
        "derive_factor_backfill_window",
        lambda **kwargs: {
            "start_date": kwargs["start_date"],
            "end_date": kwargs["end_date"],
            "date_count": 2,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-factor-daily",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-02",
            "--workers",
            "4",
            "--skip-complete",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "factor_daily_backfill|start|2026-05-01|1|2",
        "factor_daily_backfill|done|2026-05-01|1|2|10",
        "factor_daily_backfill|start|2026-05-02|2|2",
        "factor_daily_backfill|done|2026-05-02|2|2|20",
        "factor_daily_backfill|dates|2",
        "factor_daily_backfill|rows|30",
    ]


def test_backfill_factor_daily_cli_exact_window_skips_derived_window(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "derive_factor_backfill_window",
        lambda **kwargs: calls.append(("derive", kwargs))
        or {
            "start_date": "2026-01-01",
            "end_date": "2026-05-08",
            "date_count": 2,
        },
    )
    monkeypatch.setattr(
        cli,
        "backfill_factor_daily_range",
        lambda **kwargs: calls.append(("backfill", kwargs))
        or pd.DataFrame([{"trade_date": "2025-05-09", "factor_rows": 10}]),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-factor-daily",
            "--start-date",
            "2025-05-09",
            "--end-date",
            "2026-05-08",
            "--exact-window",
            "--workers",
            "2",
        ],
    )

    cli.main()

    assert [call[0] for call in calls] == ["backfill"]
    assert calls[0][1]["start_date"] == "2025-05-09"
    assert calls[0][1]["end_date"] == "2026-05-08"
    assert calls[0][1]["workers"] == 2
    assert capsys.readouterr().out.splitlines() == [
        "factor_daily_backfill|dates|1",
        "factor_daily_backfill|rows|10",
    ]


def test_minute_backfill_watchdog_cli_dispatches_and_prints_summary(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []

    monkeypatch.setattr(
        cli,
        "run_minute_backfill_watchdog",
        lambda **kwargs: calls.append(kwargs)
        or {
            "status": {"watchdog_action": "restarted"},
            "pre_summary": {"success_jobs": 5},
            "post_summary": {"success_jobs": 7},
            "run_result": {"rows": 480},
        },
        raising=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "minute-backfill-watchdog",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-31",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--max-jobs",
            "200",
            "--workers",
            "3",
            "--stale-after-minutes",
            "45",
            "--run-timeout-seconds",
            "1200",
            "--output-dir",
            "outputs/watchdog",
            "--report-target",
            "chat:test",
            "--report-account",
            "ops",
            "--openclaw-bin",
            "/opt/bin/openclaw",
            "--report-dry-run",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2024-01-01",
            "end_date": "2024-03-31",
            "freq": "5min",
            "adjust_types": ["raw", "qfq"],
            "max_jobs": 200,
            "workers": 3,
            "stale_after_minutes": 45,
            "run_timeout_seconds": 1200,
            "report_target": "chat:test",
            "report_account": "ops",
            "openclaw_bin": "/opt/bin/openclaw",
            "report_dry_run": True,
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "minute_backfill_watchdog|action|restarted",
        "minute_backfill_watchdog|delta_success|2",
        "minute_backfill_watchdog|delta_rows|480",
    ]


def test_generic_backfill_watchdog_cli_dispatches_minute_adapter_and_prints_summary(
    monkeypatch, capsys
):
    import sys

    import stock_research.cli as cli

    calls = []

    monkeypatch.setattr(
        cli,
        "run_minute_backfill_watchdog",
        lambda **kwargs: calls.append(kwargs)
        or {
            "status": {"watchdog_action": "restarted"},
            "pre_summary": {"success_jobs": 5},
            "post_summary": {"success_jobs": 7},
            "run_result": {"rows": 480},
        },
        raising=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-watchdog",
            "--adapter",
            "minute",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-31",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--max-jobs",
            "200",
            "--workers",
            "3",
            "--stale-after-minutes",
            "45",
            "--run-timeout-seconds",
            "1200",
            "--output-dir",
            "outputs/watchdog",
            "--report-target",
            "chat:test",
            "--report-account",
            "ops",
            "--openclaw-bin",
            "/opt/bin/openclaw",
            "--report-dry-run",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2024-01-01",
            "end_date": "2024-03-31",
            "freq": "5min",
            "adjust_types": ["raw", "qfq"],
            "max_jobs": 200,
            "workers": 3,
            "stale_after_minutes": 45,
            "run_timeout_seconds": 1200,
            "report_target": "chat:test",
            "report_account": "ops",
            "openclaw_bin": "/opt/bin/openclaw",
            "report_dry_run": True,
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "minute_backfill_watchdog|action|restarted",
        "minute_backfill_watchdog|delta_success|2",
        "minute_backfill_watchdog|delta_rows|480",
    ]


def test_generic_backfill_watchdog_cli_dispatches_technical_features_adapter_and_prints_summary(
    monkeypatch, capsys
):
    import sys

    from stock_research.backfill_watchdog import BackfillSummary, BackfillWatchdogStatus
    import stock_research.cli as cli

    calls = []

    monkeypatch.setattr(
        cli,
        "run_technical_feature_backfill_watchdog",
        lambda **kwargs: calls.append(kwargs)
        or {
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=True,
                work_remaining=True,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={
                    "completed_through": None,
                    "currently_working_on": "1991-01-01",
                },
                current_frontier={
                    "completed_through": "1991-01-02",
                    "currently_working_on": "1991-01-03",
                },
            ),
            "pre_summary": BackfillSummary(10, 10, 0, 0, 0, 0, 0),
            "post_summary": BackfillSummary(10, 8, 0, 2, 0, 0, 200),
            "run_result": {"sleep_between_runs_seconds": 15},
        },
        raising=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-watchdog",
            "--adapter",
            "technical-features",
            "--start-date",
            "1991-01-01",
            "--end-date",
            "2026-05-14",
            "--adjust-type",
            "qfq",
            "--lookback-bars",
            "260",
            "--source-data-version",
            "market_daily_bar:qfq",
            "--max-jobs",
            "50",
            "--workers",
            "2",
            "--stale-after-minutes",
            "20",
            "--run-timeout-seconds",
            "1800",
            "--sleep-between-runs-seconds",
            "15",
            "--report-target",
            "chat:test",
            "--report-account",
            "ops",
            "--report-dry-run",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "1991-01-01",
            "end_date": "2026-05-14",
            "adjust_type": "qfq",
            "lookback_bars": 260,
            "source_data_version": "market_daily_bar:qfq",
            "max_jobs": 50,
            "workers": 2,
            "stale_after_minutes": 20,
            "run_timeout_seconds": 1800,
            "sleep_between_runs_seconds": 15,
            "report_target": "chat:test",
            "report_account": "ops",
            "openclaw_bin": "openclaw",
            "report_dry_run": True,
        }
    ]
    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == [
        "technical_feature_watchdog|action|healthy",
        "technical_feature_watchdog|delta_success|2",
        "technical_feature_watchdog|delta_rows|200",
    ]
    assert "technical_feature_watchdog|sleep_between_runs_seconds|15" in lines


def test_backfill_technical_features_daily_cli_prints_summary(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    calls = []

    def fake_backfill_technical_features_daily_range(**kwargs):
        calls.append(kwargs)
        kwargs["progress"](
            {"event": "start", "trade_date": "2026-05-01", "index": 1, "total": 2}
        )
        kwargs["progress"](
            {
                "event": "done",
                "trade_date": "2026-05-01",
                "index": 1,
                "total": 2,
                "feature_rows": 10,
                "elapsed_seconds": 1.5,
            }
        )
        kwargs["progress"](
            {"event": "start", "trade_date": "2026-05-06", "index": 2, "total": 2}
        )
        kwargs["progress"](
            {
                "event": "done",
                "trade_date": "2026-05-06",
                "index": 2,
                "total": 2,
                "feature_rows": 20,
                "elapsed_seconds": 2.0,
            }
        )
        return pd.DataFrame(
            [
                {"trade_date": "2026-05-01", "feature_rows": 10},
                {"trade_date": "2026-05-06", "feature_rows": 20},
            ]
        )

    monkeypatch.setattr(
        cli,
        "derive_technical_feature_backfill_window",
        lambda **kwargs: {
            "start_date": "2026-04-01",
            "end_date": kwargs["end_date"],
            "date_count": 2,
        },
    )
    monkeypatch.setattr(
        cli,
        "backfill_technical_features_daily_range",
        fake_backfill_technical_features_daily_range,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-technical-features-daily",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-06",
            "--workers",
            "4",
            "--skip-complete",
            "--progress-interval",
            "2",
            "--build-strategy",
            "latest_only",
            "--source-data-version",
            "market_daily_bar:qfq@v2",
        ],
    )

    cli.main()

    assert calls[0]["start_date"] == "2026-05-01"
    assert calls[0]["workers"] == 4
    assert calls[0]["skip_complete"] is True
    assert calls[0]["source_data_version"] == "market_daily_bar:qfq@v2"
    assert calls[0]["adjust_type"] == "qfq"
    assert calls[0]["build_strategy"] == "latest_only"
    assert capsys.readouterr().out.splitlines() == [
        "technical_feature_daily_backfill|done|2026-05-06|2|2|20",
        "technical_feature_daily_backfill|dates|2",
        "technical_feature_daily_backfill|rows|30",
    ]


def test_cli_accepts_backfill_technical_features_daily_default_latest_only():
    args = build_parser().parse_args(
        [
            "backfill-technical-features-daily",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-06",
        ]
    )

    assert args.build_strategy == "latest_only"


def test_benchmark_technical_feature_backfill_cli_prints_summary(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []

    monkeypatch.setattr(
        cli,
        "run_technical_feature_backfill_benchmark",
        lambda **kwargs: calls.append(kwargs)
        or {
            "strategy": "parallel_dates",
            "workers": 4,
            "bench_tag": "demo",
            "source_data_version": "market_daily_bar:qfq@bench_demo",
            "dates": 2,
            "rows": 30,
            "elapsed_seconds": 12.5,
            "rows_per_second": 2.4,
            "dates_per_second": 0.16,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "benchmark-technical-feature-backfill",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-06",
            "--strategy",
            "parallel_dates",
            "--workers",
            "4",
            "--bench-tag",
            "demo",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2026-05-01",
            "end_date": "2026-05-06",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "workers": 4,
            "strategy": "parallel_dates",
            "bench_tag": "demo",
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "technical_feature_benchmark|strategy|parallel_dates",
        "technical_feature_benchmark|workers|4",
        "technical_feature_benchmark|bench_tag|demo",
        "technical_feature_benchmark|source_data_version|market_daily_bar:qfq@bench_demo",
        "technical_feature_benchmark|dates|2",
        "technical_feature_benchmark|rows|30",
        "technical_feature_benchmark|elapsed_seconds|12.5",
        "technical_feature_benchmark|rows_per_second|2.4",
        "technical_feature_benchmark|dates_per_second|0.16",
    ]


def test_technical_feature_gap_check_cli_prints_issue_dates_and_summary(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []

    monkeypatch.setattr(
        cli,
        "run_technical_feature_gap_check",
        lambda **kwargs: calls.append(kwargs)
        or {
            "dates": [
                {
                    "trade_date": "2024-03-01",
                    "market_assets": 5124,
                    "feature_rows": 5110,
                    "missing": 14,
                    "stale": 0,
                    "missing_assets": ["A"],
                    "stale_assets": [],
                    "has_gap": True,
                },
                {
                    "trade_date": "2024-03-04",
                    "market_assets": 5120,
                    "feature_rows": 5120,
                    "missing": 0,
                    "stale": 0,
                    "missing_assets": [],
                    "stale_assets": [],
                    "has_gap": False,
                },
            ],
            "summary": {"dates": 250, "dates_with_gaps": 3},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "technical-feature-gap-check",
            "--start-date",
            "2024-03-01",
            "--end-date",
            "2024-12-31",
            "--adjust-type",
            "qfq",
            "--calc-version",
            "v1",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2024-03-01",
            "end_date": "2024-12-31",
            "adjust_type": "qfq",
            "calc_version": "v1",
            "source_data_version": None,
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "technical_feature_gap_check|date|2024-03-01|market_assets=5124|feature_rows=5110|missing=14|stale=0",
        "technical_feature_gap_check|summary|dates=250|dates_with_gaps=3",
    ]


def test_score_factor_daily_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "score_stored_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 12,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "score-factor-daily", "--trade-date", "2026-05-08"],
    )

    cli.main()

    assert calls[0]["approved_only"] is True
    assert capsys.readouterr().out.strip() == "stock_score_daily_stored|12"


def test_show_top_scores_cli_prints_ranked_rows(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "load_top_scores",
        lambda trade_date, score_version, top_n: [
            {
                "trade_date": trade_date,
                "asset_id": "A",
                "rank": 1,
                "score_total": 88.5,
                "score_version": score_version,
            }
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "show-top-scores",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "10",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "top_score|2026-05-08|1|A|88.5|manual_v1"


def test_eval_factor_cli_prints_summary(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "load_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.01]}),
        ),
    )
    monkeypatch.setattr(
        cli,
        "generate_factor_eval_report",
        lambda *args, **kwargs: {
            "ic_summary": {"mean_ic": 0.1, "ic_count": 10},
            "rank_ic_summary": {"mean_ic": 0.2},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "eval-factor",
            "--factor-name",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "factor_eval|ret_20|mean_ic|0.1",
        "factor_eval|ret_20|ic_count|10",
        "factor_eval|ret_20|mean_rank_ic|0.2",
    ]


def test_daily_factor_pipeline_cli_prints_summary(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_daily_factor_pipeline",
        lambda **kwargs: {"factor_rows": 100, "score_rows": 20, "top_scores": [1, 2, 3]},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "run-daily-factor-pipeline",
            "--trade-date",
            "2026-05-08",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "daily_factor_pipeline|factor_rows|100",
        "daily_factor_pipeline|score_rows|20",
        "daily_factor_pipeline|top_scores|3",
    ]


def test_daily_incremental_cli_prints_step_status(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_daily_incremental_pipeline",
        lambda **kwargs: {
            "trade_date": kwargs["trade_date"],
            "status": "planned",
            "steps": [
                {"step": "sync_core_assets", "status": "planned"},
                {"step": "load_market_bars", "status": "planned"},
            ],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "run-daily-incremental",
            "--trade-date",
            "2026-05-12",
            "--dry-run",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "daily_incremental|status|planned",
        "daily_incremental_step|sync_core_assets|planned",
        "daily_incremental_step|load_market_bars|planned",
    ]


def test_daily_incremental_cli_uses_default_runners_for_non_dry_run(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "build_default_step_runners",
        lambda: calls.append("runners") or {"sync_core_assets": lambda context: {"rows": 1}},
    )
    monkeypatch.setattr(
        cli,
        "check_market_data_freshness",
        lambda context: {"status": "ok", "bar_count": 100},
    )
    monkeypatch.setattr(
        cli,
        "run_daily_incremental_pipeline",
        lambda **kwargs: calls.append(kwargs)
        or {
            "trade_date": kwargs["trade_date"],
            "status": "success",
            "steps": [{"step": "sync_core_assets", "status": "success"}],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "run-daily-incremental",
            "--trade-date",
            "2026-05-12",
            "--start-at",
            "build_factor_daily",
        ],
    )

    cli.main()

    assert calls[0] == "runners"
    assert "sync_core_assets" in calls[1]["step_runners"]
    assert calls[1]["start_at"] == "build_factor_daily"
    assert calls[1]["dry_run"] is False
    assert calls[1]["freshness_checker"] is None
    assert capsys.readouterr().out.splitlines() == [
        "daily_incremental|status|success",
        "daily_incremental_step|sync_core_assets|success",
    ]


def test_daily_incremental_cli_can_record_step_runs(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(cli, "apply_daily_job_run_schema", lambda: calls.append("schema"))

    def fake_record_daily_job_run(**kwargs):
        calls.append(("record", kwargs))
        return "run-1"

    monkeypatch.setattr(cli, "record_daily_job_run", fake_record_daily_job_run)

    def fake_run_daily_incremental_pipeline(**kwargs):
        kwargs["recorder"](
            {"step": "sync_core_assets", "status": "success", "result": {"rows": 1}}
        )
        return {
            "trade_date": kwargs["trade_date"],
            "status": "success",
            "steps": [{"step": "sync_core_assets", "status": "success"}],
        }

    monkeypatch.setattr(
        cli,
        "run_daily_incremental_pipeline",
        fake_run_daily_incremental_pipeline,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "run-daily-incremental",
            "--trade-date",
            "2026-05-12",
            "--apply-daily-run-schema",
            "--record-run",
        ],
    )

    cli.main()

    assert calls[0] == "schema"
    assert calls[1][0] == "record"
    assert calls[1][1]["step"] == "sync_core_assets"
    assert capsys.readouterr().out.splitlines() == [
        "daily_incremental|status|success",
        "daily_incremental_step|sync_core_assets|success",
    ]


def test_daily_health_cli_prints_health_lines(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "summarize_operational_health",
        lambda **kwargs: calls.append(kwargs)
        or {
            "trade_date": kwargs["trade_date"],
            "status": "alert",
            "alert_count": 1,
        },
    )
    monkeypatch.setattr(
        cli,
        "format_operational_health_lines",
        lambda result: ["daily_health|status|alert|alerts|1"],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "daily-health",
            "--trade-date",
            "2026-05-12",
            "--ingest-datasets",
            "baostock-finance,akshare-finance-statements",
            "--backfill-run-ids",
            "bars-1,labels-1",
            "--stale-minutes",
            "30",
        ],
    )

    cli.main()

    assert calls[0] == {
        "trade_date": "2026-05-12",
        "ingest_datasets": ["baostock-finance", "akshare-finance-statements"],
        "backfill_run_ids": ["bars-1", "labels-1"],
        "stale_minutes": 30,
    }
    assert capsys.readouterr().out.splitlines() == [
        "daily_health|status|alert|alerts|1",
    ]


def test_daily_health_cli_can_send_dry_run_notification(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "summarize_operational_health",
        lambda **kwargs: {"trade_date": "2026-05-12", "status": "alert", "alert_count": 1},
    )
    monkeypatch.setattr(
        cli,
        "format_operational_health_lines",
        lambda result: ["daily_health|status|alert|alerts|1"],
    )
    monkeypatch.setattr(
        cli,
        "send_openclaw_feishu_message",
        lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "daily-health",
            "--trade-date",
            "2026-05-12",
            "--notify-target",
            "oc_group",
            "--notify-dry-run",
        ],
    )

    cli.main()

    assert calls[0]["target"] == "oc_group"
    assert calls[0]["dry_run"] is True
    assert "daily_health|status|alert|alerts|1" in calls[0]["message"]


def test_export_research_snapshot_cli_prints_manifest_and_counts(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "export_research_snapshot",
        lambda **kwargs: {
            "manifest_path": "/tmp/snapshot/manifest.json",
            "row_counts": {"factor_daily": 12},
            "files": {"factor_daily": "/tmp/snapshot/factor_daily.csv"},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "export-research-snapshot",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-12",
            "--output-dir",
            "/tmp/snapshot",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "research_snapshot|manifest|/tmp/snapshot/manifest.json",
        "research_snapshot_dataset|factor_daily|rows|12|/tmp/snapshot/factor_daily.csv",
    ]


def test_migration_safety_check_cli_prints_plan(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_backup_restore_check",
        lambda **kwargs: {
            "status": "planned",
            "commands": [
                'pg_dump --format=custom --file /tmp/stock_research.dump "service=stock_research"',
                "pg_restore --list /tmp/stock_research.dump",
            ],
            "checks": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "migration-safety-check",
            "--backup-path",
            "/tmp/stock_research.dump",
            "--dry-run",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "migration_safety|status|planned",
        'migration_safety_command|pg_dump --format=custom --file /tmp/stock_research.dump "service=stock_research"',
        "migration_safety_command|pg_restore --list /tmp/stock_research.dump",
    ]


def test_daily_research_report_cli_prints_report_paths(monkeypatch, capsys, tmp_path):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "run_daily_research_report",
        lambda **kwargs: calls.append(kwargs)
        or {
            "report_paths": {
                "bundle": {"markdown_path": tmp_path / "bundle.md"},
                "topn": {"markdown_path": tmp_path / "topn.md"},
                "market_state": {"markdown_path": tmp_path / "market.md"},
                "sector_strength": {"markdown_path": tmp_path / "sector.md"},
                "risk_alerts": {"markdown_path": tmp_path / "risk.md"},
                "position_review": {"markdown_path": tmp_path / "positions.md"},
            }
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "run-daily-research-report",
            "--trade-date",
            "2026-05-08",
            "--top-n",
            "20",
            "--reports-dir",
            str(tmp_path),
        ],
    )

    cli.main()

    assert calls[0]["trade_date"] == "2026-05-08"
    assert calls[0]["top_n"] == 20
    assert capsys.readouterr().out.splitlines() == [
        f"daily_research_report|bundle|{tmp_path / 'bundle.md'}",
        f"daily_research_report|topn|{tmp_path / 'topn.md'}",
        f"daily_research_report|market_state|{tmp_path / 'market.md'}",
        f"daily_research_report|sector_strength|{tmp_path / 'sector.md'}",
        f"daily_research_report|risk_alerts|{tmp_path / 'risk.md'}",
        f"daily_research_report|position_review|{tmp_path / 'positions.md'}",
    ]


def test_evaluate_factor_gate_cli_prints_and_stores_status(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "load_multi_horizon_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.01]}),
        ),
    )
    monkeypatch.setattr(
        cli,
        "generate_multi_horizon_report",
        lambda **kwargs: {"factor_name": "ret_20", "horizons": [5], "reports": {5: {"ic_summary": {"mean_ic": 0.04, "icir": 0.6, "ic_count": 30}}}},
    )
    monkeypatch.setattr(
        cli,
        "decide_factor_gate",
        lambda **kwargs: {"factor_name": kwargs["factor_name"], "status": "approved", "reason": "passed_thresholds", "primary_horizon": 5},
    )
    monkeypatch.setattr(cli, "store_factor_eval_run", lambda **kwargs: calls.append(("run", kwargs)))
    monkeypatch.setattr(cli, "store_factor_approval", lambda **kwargs: calls.append(("approval", kwargs)))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "evaluate-factor-gate",
            "--factor-name",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-02-01",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "factor_gate|ret_20|approved|passed_thresholds|5"
    assert [kind for kind, _ in calls] == ["run", "approval"]


def test_evaluate_factor_gate_batch_cli_prints_rows(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_factor_gate_batch",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "factor_name": "alpha101_delta_close_1_rank",
                    "status": "approved",
                    "reason": "passed_thresholds",
                    "primary_horizon": 5,
                    "eval_run_id": "run-1",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "evaluate-factor-gate-batch",
            "--factor-names",
            "alpha101_delta_close_1_rank",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == (
        "factor_gate_batch|alpha101_delta_close_1_rank|approved|passed_thresholds|5|run-1"
    )


def test_evaluate_factor_gate_batch_cli_accepts_validation_start_date(monkeypatch):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "run_factor_gate_batch",
        lambda **kwargs: calls.append(kwargs)
        or pd.DataFrame(
            [
                {
                    "factor_name": "ret_20",
                    "status": "approved",
                    "reason": "passed_thresholds",
                    "primary_horizon": 5,
                    "eval_run_id": "run-1",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "evaluate-factor-gate-batch",
            "--factor-names",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
            "--validation-start-date",
            "2026-03-01",
        ],
    )

    cli.main()

    assert calls[0]["validation_start_date"] == "2026-03-01"


def test_cli_accepts_research_preflight_command():
    args = build_parser().parse_args(
        [
            "research-preflight",
            "--start-date",
            "2024-01-01",
            "--horizons",
            "5,10,20,60",
            "--factor-names",
            "ret_20,qlib_ret_5",
            "--min-label-dates",
            "20",
        ]
    )

    assert args.command == "research-preflight"
    assert args.start_date == "2024-01-01"
    assert args.horizons == [5, 10, 20, 60]
    assert args.factor_names == ["ret_20", "qlib_ret_5"]
    assert args.min_label_dates == 20


def test_cli_accepts_data_quality_command():
    args = build_parser().parse_args(
        [
            "data-quality",
            "--expected-start-date",
            "1991-01-01",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-12-31",
            "--horizons",
            "5,10,20,60",
            "--factor-names",
            "ret_20,qlib_ret_5",
            "--calc-version",
            "v2",
            "--min-label-dates",
            "25",
            "--require-industry-membership",
            "--json",
        ]
    )

    assert args.command == "data-quality"
    assert args.expected_start_date == "1991-01-01"
    assert args.start_date == "2024-01-01"
    assert args.end_date == "2024-12-31"
    assert args.horizons == [5, 10, 20, 60]
    assert args.factor_names == ["ret_20", "qlib_ret_5"]
    assert args.calc_version == "v2"
    assert args.min_label_dates == 25
    assert args.require_industry_membership is True
    assert args.json is True


def test_data_quality_cli_text_mode_prints_summary_and_check(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "run_data_quality",
        lambda **kwargs: calls.append(kwargs)
        or {
            "overall_status": "ok",
            "checks": [
                {
                    "check_name": "market_daily_bar",
                    "status": "ok",
                    "kind": "data_audit",
                    "metrics": {
                        "rows": 10,
                        "date_count": 2,
                    },
                }
            ],
            "blocked_checks": [],
            "warning_checks": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "data-quality",
            "--start-date",
            "2024-01-01",
        ],
    )

    cli.main()

    assert calls[0]["end_date"] is None
    assert capsys.readouterr().out.splitlines() == [
        "data_quality|summary|ok|checks|1|blocked|0|warning|0",
        "data_quality|market_daily_bar|ok|kind|data_audit|rows|10|date_count|2",
    ]


def test_data_quality_cli_json_mode_prints_payload_and_exits_nonzero_when_blocked(
    monkeypatch, capsys
):
    import json
    import sys

    import stock_research.cli as cli

    report = {
        "overall_status": "blocked",
        "checks": [{"check_name": "factor_label_coverage", "status": "blocked", "kind": "research_preflight"}],
        "blocked_checks": ["factor_label_coverage"],
        "warning_checks": [],
    }
    monkeypatch.setattr(cli, "run_data_quality", lambda **kwargs: report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "data-quality",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-12-31",
            "--json",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1
    assert json.loads(capsys.readouterr().out) == report


def test_data_quality_cli_uses_market_start_when_start_omitted(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli
    import stock_research.data_quality as data_quality

    calls = []
    monkeypatch.setattr(
        cli,
        "load_market_date_bounds",
        lambda: {"start_date": "1990-12-19", "end_date": "2026-05-08", "date_count": 8200},
    )
    monkeypatch.setattr(
        data_quality,
        "candidate_factor_names",
        lambda: ["ret_20"],
    )
    monkeypatch.setattr(
        data_quality,
        "run_data_audit",
        lambda **kwargs: calls.append(("data_audit", kwargs))
        or [
            {
                "dataset": "market_daily_bar",
                "status": "ok",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            }
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "summarize_finance_coverage",
        lambda **kwargs: calls.append(("finance_audit", kwargs))
        or [{"check": "missing_balance_sheet", "status": "ok", "rows": 0}],
    )
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: calls.append(("latest", kwargs))
        or {
            "latest_common_date": "2024-12-31",
            "date_count": 122,
            "horizons": kwargs["horizons"],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "check_factor_label_coverage",
        lambda **kwargs: calls.append(("coverage", kwargs))
        or {
            "status": "ok",
            "reasons": [],
            "factor_date_count": 122,
            "factor_complete_date_count": 122,
            "missing_horizons": [],
            "short_label_horizons": [],
            "required_factor_names": [],
            "unavailable_factor_names": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "data-quality", "--end-date", "2024-12-31"],
    )

    cli.main()

    assert calls == [
        ("data_audit", {"expected_start_date": "1990-12-01"}),
        ("finance_audit", {}),
        ("latest", {"start_date": "1990-12-19", "horizons": [5, 10, 20, 60]}),
        (
            "coverage",
            {
                "factor_names": ["ret_20"],
                "start_date": "1990-12-19",
                "end_date": "2024-12-31",
                "horizons": [5, 10, 20, 60],
                "calc_version": "v1",
                "min_label_dates": 20,
            },
        ),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "data_quality|summary|ok|checks|4|blocked|0|warning|0",
        "data_quality|market_daily_bar|ok|kind|data_audit|rows|10|date_count|2|min_date|2024-01-01|max_date|2024-01-02",
        "data_quality|missing_balance_sheet|ok|kind|finance_audit|rows|0",
        "data_quality|latest_common_label_date|ok|kind|research_preflight|latest_common_date|2024-12-31|date_count|122|requested_end_date|2024-12-31",
        "data_quality|factor_label_coverage|ok|kind|research_preflight|factor_date_count|122|complete_factor_date_count|122",
    ]


def test_data_quality_cli_blocks_when_market_start_missing(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli
    import stock_research.data_quality as data_quality

    calls = []
    monkeypatch.setattr(
        cli,
        "load_market_date_bounds",
        lambda: {"start_date": None, "end_date": "2026-05-08", "date_count": 8200},
    )
    monkeypatch.setattr(
        data_quality,
        "run_data_audit",
        lambda **kwargs: calls.append(("data_audit", kwargs))
        or [
            {
                "dataset": "market_daily_bar",
                "status": "ok",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            }
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "summarize_finance_coverage",
        lambda **kwargs: calls.append(("finance_audit", kwargs))
        or [{"check": "missing_balance_sheet", "status": "blocked", "rows": 2}],
    )

    def fail_find_latest_common_label_date(**kwargs):
        raise AssertionError("find_latest_common_label_date should not be called")

    monkeypatch.setattr(data_quality, "find_latest_common_label_date", fail_find_latest_common_label_date)
    monkeypatch.setattr(sys, "argv", ["stock-research", "data-quality"])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    lines = capsys.readouterr().out.splitlines()
    assert excinfo.value.code == 1
    assert calls == [
        ("data_audit", {"expected_start_date": "1990-12-01"}),
        ("finance_audit", {}),
    ]
    assert lines == [
        "data_quality|summary|blocked|checks|4|blocked|3|warning|0",
        "data_quality|market_daily_bar|ok|kind|data_audit|rows|10|date_count|2|min_date|2024-01-01|max_date|2024-01-02",
        "data_quality|missing_balance_sheet|blocked|kind|finance_audit|rows|2",
        "data_quality|latest_common_label_date|blocked|kind|research_preflight|latest_common_date||date_count|0",
        "data_quality|factor_label_coverage|blocked|kind|research_preflight|factor_date_count|0|complete_factor_date_count|0",
    ]


def test_data_quality_cli_blocks_when_latest_common_label_date_missing(monkeypatch, capsys):
    import json
    import sys

    import stock_research.cli as cli
    import stock_research.data_quality as data_quality

    calls = []
    monkeypatch.setattr(
        data_quality,
        "run_data_audit",
        lambda **kwargs: calls.append(("data_audit", kwargs))
        or [
            {
                "dataset": "market_daily_bar",
                "status": "ok",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            }
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "summarize_finance_coverage",
        lambda **kwargs: calls.append(("finance_audit", kwargs))
        or [{"check": "missing_balance_sheet", "status": "blocked", "rows": 2}],
    )
    latest_calls = []
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: latest_calls.append(kwargs)
        or {
            "latest_common_date": None,
            "date_count": 0,
            "horizons": kwargs["horizons"],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "data-quality", "--start-date", "2024-01-01", "--json"],
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert excinfo.value.code == 1
    assert calls == [
        ("data_audit", {"expected_start_date": "1990-12-01"}),
        ("finance_audit", {}),
    ]
    assert latest_calls == [{"start_date": "2024-01-01", "horizons": [5, 10, 20, 60]}]
    assert payload["overall_status"] == "blocked"
    assert payload["blocked_checks"] == [
        "missing_balance_sheet",
        "latest_common_label_date",
        "factor_label_coverage",
    ]
    assert payload["checks"][0]["check_name"] == "market_daily_bar"
    assert payload["checks"][1]["check_name"] == "missing_balance_sheet"
    assert [check["check_name"] for check in payload["checks"]] == [
        "market_daily_bar",
        "missing_balance_sheet",
        "latest_common_label_date",
        "factor_label_coverage",
    ]


def test_research_preflight_cli_prints_latest_date_and_coverage(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "candidate_factor_names", lambda: ["ret_20", "qlib_ret_5"])
    monkeypatch.setattr(
        cli,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": "2026-01-30",
            "date_count": 122,
            "horizons": [5, 10, 20, 60],
        },
    )
    monkeypatch.setattr(
        cli,
        "check_factor_label_coverage",
        lambda **kwargs: {
            "status": "ok",
            "reasons": [],
            "factor_date_count": 122,
            "factor_complete_date_count": 122,
            "missing_horizons": [],
            "short_label_horizons": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "research-preflight", "--start-date", "2024-01-01"],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "research_preflight|latest_common_label_date|2026-01-30|122",
        "research_preflight|coverage|ok|factor_dates|122|complete_factor_dates|122",
        "research_preflight|missing_horizons|",
        "research_preflight|short_label_horizons|",
    ]


def test_research_preflight_cli_uses_market_start_when_start_omitted(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(cli, "candidate_factor_names", lambda: ["ret_20"])
    monkeypatch.setattr(
        cli,
        "load_market_date_bounds",
        lambda: {"start_date": "1990-12-19", "end_date": "2026-05-08", "date_count": 8200},
    )
    monkeypatch.setattr(
        cli,
        "find_latest_common_label_date",
        lambda **kwargs: calls.append(("latest", kwargs))
        or {
            "latest_common_date": "2026-01-30",
            "date_count": 122,
            "horizons": [5, 10, 20, 60],
        },
    )
    monkeypatch.setattr(
        cli,
        "check_factor_label_coverage",
        lambda **kwargs: calls.append(("coverage", kwargs))
        or {
            "status": "ok",
            "reasons": [],
            "factor_date_count": 122,
            "factor_complete_date_count": 122,
            "missing_horizons": [],
            "short_label_horizons": [],
        },
    )
    monkeypatch.setattr(sys, "argv", ["stock-research", "research-preflight"])

    cli.main()

    assert calls[0][1]["start_date"] == "1990-12-19"
    assert calls[1][1]["start_date"] == "1990-12-19"
    assert capsys.readouterr().out.splitlines()[0] == (
        "research_preflight|latest_common_label_date|2026-01-30|122"
    )


def test_research_preflight_cli_blocks_when_latest_label_date_missing(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "candidate_factor_names", lambda: ["ret_20", "qlib_ret_5"])
    monkeypatch.setattr(
        cli,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": None,
            "date_count": 0,
            "horizons": [5, 10, 20, 60],
        },
    )

    def fail_check_factor_label_coverage(**kwargs):
        raise AssertionError("check_factor_label_coverage should not be called")

    monkeypatch.setattr(cli, "check_factor_label_coverage", fail_check_factor_label_coverage)
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "research-preflight", "--start-date", "2024-01-01"],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "research_preflight|latest_common_label_date||0",
        "research_preflight|coverage|blocked|factor_dates|0|complete_factor_dates|0",
        "research_preflight|missing_horizons|5,10,20,60",
        "research_preflight|short_label_horizons|",
    ]


def test_research_preflight_cli_rejects_invalid_horizons():
    import pytest

    for value in ("", ",", "5,,10"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["research-preflight", "--horizons", value])


def test_research_preflight_cli_rejects_invalid_factor_names():
    import pytest

    for value in ("", ",", "ret_20,,qlib_ret_5"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["research-preflight", "--factor-names", value])


def test_backfill_labels_cli_uses_derived_window(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "derive_label_backfill_window",
        lambda **kwargs: calls.append(("window", kwargs))
        or {
            "start_date": "1990-12-19",
            "end_date": "2026-02-01",
            "date_count": 8140,
        },
    )
    monkeypatch.setattr(
        cli,
        "compute_and_store_labels",
        lambda end_date, start_date=None, horizons=None: calls.append(
            ("labels", end_date, start_date, horizons)
        )
        or 123,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-labels",
            "--horizons",
            "5,20,60",
        ],
    )

    cli.main()

    assert calls == [
        (
            "window",
            {
                "start_date": None,
                "end_date": None,
                "horizons": [5, 20, 60],
                "adjust_type": "hfq",
            },
        ),
        ("labels", "2026-02-01", "1990-12-19", [5, 20, 60]),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "labels_backfill|start_date|1990-12-19",
        "labels_backfill|end_date|2026-02-01",
        "labels_backfill|dates|8140",
        "labels_backfill|rows|123",
    ]


def test_backfill_factor_daily_cli_uses_derived_window(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "derive_factor_backfill_window",
        lambda **kwargs: calls.append(("window", kwargs))
        or {
            "start_date": "1991-06-20",
            "end_date": "2026-05-08",
            "date_count": 8071,
        },
    )
    monkeypatch.setattr(
        cli,
        "backfill_factor_daily_range",
        lambda **kwargs: calls.append(("backfill", kwargs))
        or __import__("pandas").DataFrame(
            [{"trade_date": "1991-06-20", "factor_rows": 1}]
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-factor-daily",
            "--workers",
            "4",
            "--skip-complete",
        ],
    )

    cli.main()

    assert calls[0] == (
        "window",
        {
            "start_date": None,
            "end_date": None,
            "lookback_bars": 130,
            "industry_system": "csrc",
        },
    )
    assert calls[1][0] == "backfill"
    assert calls[1][1]["start_date"] == "1991-06-20"
    assert calls[1][1]["end_date"] == "2026-05-08"
    assert capsys.readouterr().out.splitlines()[-2:] == [
        "factor_daily_backfill|dates|1",
        "factor_daily_backfill|rows|1",
    ]


def test_cli_accepts_backfill_approved_scores_command():
    args = build_parser().parse_args(
        [
            "backfill-approved-scores",
            "--start-date",
            "1991-06-20",
            "--end-date",
            "2026-02-02",
            "--score-version",
            "manual_v1",
            "--calc-version",
            "v1",
            "--adjust-type",
            "hfq",
        ]
    )

    assert args.command == "backfill-approved-scores"
    assert args.start_date == "1991-06-20"
    assert args.end_date == "2026-02-02"
    assert args.score_version == "manual_v1"
    assert args.calc_version == "v1"
    assert args.adjust_type == "hfq"


def test_cli_accepts_factor_gate_backfill_watchdog_command():
    args = build_parser().parse_args(
        [
            "backfill-watchdog",
            "--adapter",
            "factor-gate",
            "--start-date",
            "1991-06-24",
            "--end-date",
            "2026-04-28",
            "--validation-start-date",
            "2018-01-01",
            "--horizons",
            "5,10,20,60",
            "--primary-horizon",
            "5",
            "--calc-version",
            "v1",
            "--score-version",
            "manual_v1",
            "--quantiles",
            "5",
            "--top-n",
            "30",
            "--max-jobs",
            "1",
            "--workers",
            "1",
            "--report-target",
            "chat:test",
        ]
    )

    assert args.command == "backfill-watchdog"
    assert args.adapter == "factor-gate"
    assert args.validation_start_date == "2018-01-01"
    assert args.score_version == "manual_v1"
    assert args.max_jobs == 1


def test_backfill_approved_scores_cli_uses_market_bounds(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "load_market_date_bounds",
        lambda adjust_type="hfq": calls.append(("bounds", adjust_type))
        or {
            "start_date": "1990-12-19",
            "end_date": "2026-05-08",
            "date_count": 8200,
        },
    )
    monkeypatch.setattr(
        cli,
        "score_approved_factors_range",
        lambda **kwargs: calls.append(("score", kwargs))
        or __import__("pandas").DataFrame(
            [
                {"trade_date": "1990-12-19", "score_rows": 3},
                {"trade_date": "1990-12-20", "score_rows": 4},
            ]
        ),
    )
    monkeypatch.setattr(sys, "argv", ["stock-research", "backfill-approved-scores"])

    cli.main()

    assert calls == [
        ("bounds", "hfq"),
        (
            "score",
            {
                "start_date": "1990-12-19",
                "end_date": "2026-05-08",
                "score_version": "manual_v1",
                "calc_version": "v1",
                "adjust_type": "hfq",
            },
        ),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "approved_score_backfill|start_date|1990-12-19",
        "approved_score_backfill|end_date|2026-05-08",
        "approved_score_backfill|dates|2",
        "approved_score_backfill|rows|7",
    ]


def test_backfill_features_cli_uses_derived_window(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "derive_feature_backfill_window",
        lambda **kwargs: calls.append(("window", kwargs))
        or {
            "start_date": "1991-06-20",
            "end_date": "2026-05-08",
            "date_count": 8071,
        },
    )
    monkeypatch.setattr(
        cli,
        "compute_and_store_p0_features_range",
        lambda **kwargs: calls.append(("backfill", kwargs))
        or __import__("pandas").DataFrame(
            [{"trade_date": "1991-06-20", "feature_rows": 8}]
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-features",
            "--workers",
            "4",
            "--skip-complete",
        ],
    )

    cli.main()

    assert calls[0] == (
        "window",
        {
            "start_date": None,
            "end_date": None,
            "lookback_bars": 120,
            "adjust_type": "hfq",
        },
    )
    assert calls[1][0] == "backfill"
    assert calls[1][1]["start_date"] == "1991-06-20"
    assert calls[1][1]["end_date"] == "2026-05-08"
    assert capsys.readouterr().out.splitlines() == [
        "feature_backfill|dates|1",
        "feature_backfill|rows|8",
    ]


def test_reset_stale_ingest_jobs_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "reset_stale_ingest_jobs_for_service", lambda **kwargs: 2)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "reset-stale-ingest-jobs",
            "--dataset",
            "baostock-finance",
            "--older-than-minutes",
            "60",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "ingest_stale_reset|baostock-finance|2"


def test_data_audit_cli_prints_lines(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_data_audit",
        lambda **kwargs: [
            {
                "dataset": "market_daily_bar",
                "status": "short_history",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            }
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "data-audit", "--expected-start-date", "1990-12-01"],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == (
        "data_audit|market_daily_bar|short_history|rows|10|dates|2|"
        "min|2024-01-01|max|2024-01-02"
    )


def test_backfill_control_plane_cli_accepts_commands():
    create_args = build_parser().parse_args(
        [
            "create-backfill-run",
            "--run-id",
            "run-1",
            "--dataset",
            "daily-bars",
            "--source",
            "baostock",
            "--source-version",
            "v1",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-12-31",
            "--months-per-partition",
            "1",
        ]
    )
    assert create_args.command == "create-backfill-run"
    assert create_args.run_id == "run-1"

    status_args = build_parser().parse_args(["backfill-status", "--run-id", "run-1"])
    assert status_args.command == "backfill-status"

    claim_args = build_parser().parse_args(["claim-backfill-tasks", "--run-id", "run-1", "--limit", "10"])
    assert claim_args.command == "claim-backfill-tasks"

    success_args = build_parser().parse_args(
        ["mark-backfill-task-success", "--task-id", "task-1", "--rows-read", "10", "--rows-written", "9"]
    )
    assert success_args.command == "mark-backfill-task-success"

    failed_args = build_parser().parse_args(
        ["mark-backfill-task-failed", "--task-id", "task-1", "--error-message", "boom"]
    )
    assert failed_args.command == "mark-backfill-task-failed"

    reset_args = build_parser().parse_args(
        ["reset-stale-backfill-tasks", "--dataset", "daily-bars", "--older-than-minutes", "60"]
    )
    assert reset_args.command == "reset-stale-backfill-tasks"


def test_create_backfill_run_cli_prints_summary(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "create_backfill_run_for_service",
        lambda **kwargs: {"run_id": "run-1", "dataset": "daily-bars", "task_count": 3},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "create-backfill-run",
            "--run-id",
            "run-1",
            "--dataset",
            "daily-bars",
            "--source",
            "baostock",
            "--source-version",
            "v1",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-31",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "backfill_run_created|run-1|daily-bars|tasks|3"


def test_backfill_status_cli_prints_counts(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "backfill_status_for_service",
        lambda **kwargs: {"run_id": "run-1", "counts": {"pending": 3, "success": 1}},
    )
    monkeypatch.setattr(sys, "argv", ["stock-research", "backfill-status", "--run-id", "run-1"])

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "backfill_status|run-1|pending|3",
        "backfill_status|run-1|success|1",
    ]


def test_claim_backfill_tasks_cli_prints_claims(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "claim_backfill_tasks_for_service",
        lambda **kwargs: [
            {
                "task_id": "task-1",
                "partition_key": "2024-01",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            }
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "claim-backfill-tasks", "--run-id", "run-1", "--limit", "1"],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == (
        "backfill_task_claimed|task-1|2024-01|2024-01-01|2024-01-31"
    )


def test_backfill_task_state_cli_prints_results(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(cli, "mark_backfill_task_success_for_service", lambda **kwargs: calls.append(("success", kwargs)))
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "mark-backfill-task-success", "--task-id", "task-1", "--rows-read", "10", "--rows-written", "9"],
    )
    cli.main()
    assert capsys.readouterr().out.strip() == "backfill_task_success|task-1|10|9"

    monkeypatch.setattr(cli, "mark_backfill_task_failed_for_service", lambda **kwargs: calls.append(("failed", kwargs)))
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "mark-backfill-task-failed", "--task-id", "task-1", "--error-message", "boom"],
    )
    cli.main()
    assert capsys.readouterr().out.strip() == "backfill_task_failed|task-1|boom"

    monkeypatch.setattr(cli, "reset_stale_backfill_tasks_for_service", lambda **kwargs: 2)
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "reset-stale-backfill-tasks", "--dataset", "daily-bars", "--older-than-minutes", "60"],
    )
    cli.main()
    assert capsys.readouterr().out.strip() == "backfill_task_stale_reset|daily-bars|2"


def test_calendar_lifecycle_cli_accepts_commands():
    calendar_args = build_parser().parse_args(
        [
            "seed-trading-calendar",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--exchanges",
            "SH,SZ",
            "--source-version",
            "derived_v1",
        ]
    )
    assert calendar_args.command == "seed-trading-calendar"
    assert calendar_args.exchanges == ["SH", "SZ"]

    lifecycle_args = build_parser().parse_args(
        ["sync-asset-lifecycle", "--source-version", "core_asset_master_v1"]
    )
    assert lifecycle_args.command == "sync-asset-lifecycle"


def test_seed_trading_calendar_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "seed_trading_calendar_from_bars", lambda **kwargs: 44)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "seed-trading-calendar",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--exchanges",
            "SH,SZ",
            "--source-version",
            "derived_v1",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "trading_calendar_seeded|rows|44"


def test_sync_asset_lifecycle_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "sync_asset_lifecycle_from_master", lambda **kwargs: 100)
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "sync-asset-lifecycle", "--source-version", "core_asset_master_v1"],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "asset_lifecycle_synced|rows|100"
