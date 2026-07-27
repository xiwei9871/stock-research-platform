from stock_research import cli


def test_cli_accepts_run_strategy_daily_eod_command():
    args = cli.build_parser().parse_args(["run-strategy-daily-eod", "--trade-date", "2026-06-24"])
    assert args.command == "run-strategy-daily-eod"
    assert args.trade_date == "2026-06-24"


def test_cli_run_strategy_daily_eod_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_strategy_daily_eod",
        lambda **_kwargs: {
            "status": "success",
            "trade_date": "2026-06-24",
            "output_dir": "/tmp/out",
            "review_rows": 15,
            "summary_path": "/tmp/out/strategy_eod_publish_summary.json",
            "dependency_reason": None,
            "strategy_status": {
                "lhb_shortline": "success",
                "mid_trend": "success",
                "tech_bottleneck": "success",
            },
        },
    )

    rc = cli.main(["run-strategy-daily-eod", "--trade-date", "2026-06-24"])
    out = capsys.readouterr().out

    assert rc in {0, None}
    assert "strategy_daily_eod|status|success" in out
    assert "strategy_daily_eod|lhb_shortline_status|success" in out
