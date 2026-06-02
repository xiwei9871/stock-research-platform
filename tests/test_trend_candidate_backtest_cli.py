from stock_research import cli


def test_trend_candidate_backtest_cli_prints_report_paths(monkeypatch, capsys):
    calls = []

    def fake_run_trend_candidate_backtest_report(**kwargs):
        calls.append(kwargs)
        return {
            "paths": {
                "summary": "/tmp/summary.csv",
                "equity_curve": "/tmp/equity_curve.csv",
                "positions": "/tmp/positions.csv",
                "trades": "/tmp/trades.csv",
                "markdown_report": "/tmp/trend_candidate_backtest_report.md",
            },
            "summary": [1, 2, 3],
            "equity_curve": [1, 2],
            "positions": [1],
            "trades": [1, 2, 3, 4],
            "diagnostics": ["diag"],
        }

    monkeypatch.setattr(
        cli,
        "run_trend_candidate_backtest_report",
        fake_run_trend_candidate_backtest_report,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "trend-candidate-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-06",
            "--candidate-scores-path",
            "/tmp/candidate_scores.csv",
            "--top-ns",
            "20,50",
            "--holding-days",
            "5,10",
            "--transaction-cost-bps",
            "20",
            "--adjust-type",
            "qfq",
            "--reports-dir",
            "/tmp/reports",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2026-01-01",
            "end_date": "2026-01-06",
            "candidate_scores_path": "/tmp/candidate_scores.csv",
            "top_ns": (20, 50),
            "holding_days": (5, 10),
            "transaction_cost_bps": 20.0,
            "adjust_type": "qfq",
            "reports_dir": "/tmp/reports",
        }
    ]
    assert capsys.readouterr().out.strip().splitlines() == [
        "trend_candidate_backtest|report|/tmp/trend_candidate_backtest_report.md",
        "trend_candidate_backtest|summary|/tmp/summary.csv",
        "trend_candidate_backtest|equity_curve|/tmp/equity_curve.csv",
        "trend_candidate_backtest|positions|/tmp/positions.csv",
        "trend_candidate_backtest|trades|/tmp/trades.csv",
        "trend_candidate_backtest|summary_rows|3",
        "trend_candidate_backtest|equity_rows|2",
        "trend_candidate_backtest|position_rows|1",
        "trend_candidate_backtest|trade_rows|4",
        "trend_candidate_backtest|diagnostics|1",
    ]
