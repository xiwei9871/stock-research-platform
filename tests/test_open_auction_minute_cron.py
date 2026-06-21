from stock_research.open_auction_minute_cron import build_open_auction_minute_cron_entries
from stock_research.cli import build_parser


def test_build_open_auction_minute_cron_entries_prints_primary_and_retry_jobs():
    entries = build_open_auction_minute_cron_entries(
        project_dir="/Users/xiwei/stock_research",
        universe_path="/tmp/universe.csv",
        log_path="logs/open_auction_minute_collect.log",
    )

    assert len(entries) == 2
    assert entries[0].startswith("40 9 * * 1-5 ")
    assert entries[1].startswith("10 15 * * 1-5 ")
    assert "OPEN_AUCTION_MINUTE_UNIVERSE_PATH=/tmp/universe.csv" in entries[0]
    assert 'scripts/run_open_auction_minute_collect.sh "$(date +\\%F)"' in entries[0]
    assert ">> logs/open_auction_minute_collect.log 2>&1" in entries[1]


def test_open_auction_minute_commands_are_registered():
    parser = build_parser()

    collect_args = parser.parse_args(
        [
            "collect-open-auction-minute-v1",
            "--universe-path",
            "/tmp/universe.csv",
        ]
    )
    cron_args = parser.parse_args(
        [
            "open-auction-minute-cron-entry",
            "--universe-path",
            "/tmp/universe.csv",
        ]
    )

    assert collect_args.command == "collect-open-auction-minute-v1"
    assert collect_args.start_time == "09:15:00"
    assert collect_args.end_time == "09:25:00"
    assert cron_args.command == "open-auction-minute-cron-entry"
    assert cron_args.primary_hour == 9
    assert cron_args.retry_hour == 15
