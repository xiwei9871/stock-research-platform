from stock_research import cli


def test_industry_focus_backtest_cli_prints_report_paths(monkeypatch, capsys):
    def fake_runner(**kwargs):
        assert kwargs["start_date"] == "2026-01-01"
        assert kwargs["end_date"] == "2026-01-05"
        assert kwargs["top_n"] == 20
        assert kwargs["dynamic_top_k"] == 4
        return {
            "paths": {
                "markdown_report": "/tmp/report.md",
                "summary": "/tmp/summary.csv",
                "industry_scores": "/tmp/industry_scores.csv",
                "focus_industries_daily": "/tmp/focus.csv",
            },
            "summary": [1, 2],
        }

    monkeypatch.setattr(cli, "run_industry_focus_backtest_report", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "industry-focus-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-05",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "industry_focus_backtest|report|/tmp/report.md" in out
    assert "industry_focus_backtest|summary|/tmp/summary.csv" in out
    assert "industry_focus_backtest|industry_scores|/tmp/industry_scores.csv" in out
    assert "industry_focus_backtest|focus_industries_daily|/tmp/focus.csv" in out
