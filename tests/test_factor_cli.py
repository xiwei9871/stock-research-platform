from stock_research.cli import build_parser


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
