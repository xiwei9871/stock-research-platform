from stock_research.cli import build_parser


def test_tdx_auction_watchdog_cli_exposes_tdx_and_reporting_options():
    args = build_parser().parse_args(
        [
            "tdx-auction-backfill-watchdog",
            "--start-date",
            "2018-02-14",
            "--end-date",
            "2024-12-31",
            "--report-target",
            "chat:test",
            "--tdx-hosts",
            "116.205.183.150:7709",
            "--max-jobs",
            "1",
            "--workers",
            "8",
        ]
    )

    assert args.command == "tdx-auction-backfill-watchdog"
    assert args.start_date == "2018-02-14"
    assert args.tdx_hosts == ["116.205.183.150:7709"]
    assert args.report_target == "chat:test"


def test_tdx_auction_watchdog_defaults_process_a_small_batch_per_run():
    args = build_parser().parse_args(["tdx-auction-backfill-watchdog"])

    assert args.max_jobs == 4
    assert args.tdx_server_count == 4
