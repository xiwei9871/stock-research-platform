import stock_research.cli as cli


def test_cli_accepts_intraday_feature_commands():
    parser = cli.build_parser()

    build_args = parser.parse_args(
        [
            "build-intraday-features-daily",
            "--trade-date",
            "2026-06-05",
            "--freq",
            "5min",
            "--adjust-type",
            "raw",
            "--industry-system",
            "csrc",
        ]
    )
    assert build_args.command == "build-intraday-features-daily"
    assert build_args.trade_date == "2026-06-05"

    backfill_args = parser.parse_args(
        [
            "backfill-intraday-features-daily",
            "--start-date",
            "2026-06-01",
            "--end-date",
            "2026-06-05",
            "--workers",
            "2",
            "--skip-complete",
        ]
    )
    assert backfill_args.command == "backfill-intraday-features-daily"
    assert backfill_args.skip_complete is True

    gap_args = parser.parse_args(
        [
            "intraday-feature-gap-check",
            "--start-date",
            "2026-06-01",
            "--end-date",
            "2026-06-05",
        ]
    )
    assert gap_args.command == "intraday-feature-gap-check"


def test_cli_build_intraday_features_daily_dispatches(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(
        cli,
        "build_and_store_intraday_features_daily",
        lambda **kwargs: calls.append(kwargs)
        or {"stock_rows": 20, "industry_rows": 5},
    )

    cli.main(
        [
            "build-intraday-features-daily",
            "--trade-date",
            "2026-06-05",
            "--freq",
            "5min",
            "--adjust-type",
            "raw",
            "--industry-system",
            "csrc",
        ]
    )

    assert calls == [
        {
            "trade_date": "2026-06-05",
            "freq": "5min",
            "adjust_type": "raw",
            "industry_system": "csrc",
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "intraday_features_daily|stock_rows|20",
        "intraday_features_daily|industry_rows|5",
    ]


def test_cli_backfill_intraday_features_daily_dispatches(monkeypatch, capsys):
    class _Result:
        empty = False

        def __len__(self):
            return 2

        def __getitem__(self, key):
            values = {
                "stock_rows": _Sum(30),
                "industry_rows": _Sum(8),
            }
            return values[key]

    calls = []
    monkeypatch.setattr(cli, "backfill_intraday_features_daily_range", lambda **kwargs: calls.append(kwargs) or _Result())

    cli.main(
        [
            "backfill-intraday-features-daily",
            "--start-date",
            "2026-06-04",
            "--end-date",
            "2026-06-05",
            "--workers",
            "2",
            "--skip-complete",
        ]
    )

    assert calls[0]["start_date"] == "2026-06-04"
    assert calls[0]["end_date"] == "2026-06-05"
    assert calls[0]["workers"] == 2
    assert calls[0]["skip_complete"] is True
    assert capsys.readouterr().out.splitlines()[-2:] == [
        "intraday_feature_daily_backfill|dates|2",
        "intraday_feature_daily_backfill|rows|38",
    ]


def test_cli_intraday_feature_gap_check_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_intraday_feature_gap_check",
        lambda **kwargs: {
            "dates": [
                {
                    "trade_date": "2026-06-04",
                    "minute_assets": 10,
                    "stock_feature_assets": 8,
                    "stock_missing": 2,
                    "stock_stale": 0,
                    "industry_feature_groups": 0,
                    "has_stock_gap": True,
                    "has_industry_gap": True,
                }
            ],
            "summary": {
                "dates": 2,
                "dates_with_stock_gaps": 1,
                "dates_with_industry_gaps": 1,
            },
        },
    )

    cli.main(
        [
            "intraday-feature-gap-check",
            "--start-date",
            "2026-06-04",
            "--end-date",
            "2026-06-05",
        ]
    )

    assert capsys.readouterr().out.splitlines() == [
        "intraday_feature_gap_check|date|2026-06-04|minute_assets=10|stock_feature_assets=8|stock_missing=2|stock_stale=0|industry_feature_groups=0|industry_gap=1",
        "intraday_feature_gap_check|summary|dates=2|dates_with_stock_gaps=1|dates_with_industry_gaps=1",
    ]


class _Sum:
    def __init__(self, value):
        self.value = value

    def sum(self):
        return self.value
