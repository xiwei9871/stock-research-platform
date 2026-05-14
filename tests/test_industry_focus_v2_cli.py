from stock_research import cli


def test_industry_v1_attribution_cli_prints_output_paths(monkeypatch, capsys):
    def fake_runner(**kwargs):
        assert kwargs["start_date"] == "2026-01-01"
        assert kwargs["end_date"] == "2026-01-31"
        return {
            "paths": {
                "v1_failure_attribution": "/tmp/industry_v1_failure_attribution.csv",
                "v2_diagnostics": "/tmp/industry_focus_score_v2_diagnostics.csv",
            },
            "v1_failure_attribution": [1, 2],
            "v2_diagnostics": [1, 2, 3],
        }

    monkeypatch.setattr(cli, "run_industry_focus_v2_diagnostics", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "industry-v1-attribution",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "industry_v1_attribution|v1_failure_attribution|/tmp/industry_v1_failure_attribution.csv" in out
    assert "industry_v1_attribution|v2_diagnostics|/tmp/industry_focus_score_v2_diagnostics.csv" in out


def test_industry_focus_v2_backtest_cli_prints_summary(monkeypatch, capsys):
    def fake_runner(**kwargs):
        assert kwargs["diagnostics_path"] == "/tmp/diag.csv"
        return {
            "paths": {
                "summary": "/tmp/summary.csv",
                "annual_metrics": "/tmp/annual.csv",
                "monthly_metrics": "/tmp/monthly.csv",
            },
            "summary": [1],
        }

    monkeypatch.setattr(cli, "run_industry_focus_v2_backtest", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "industry-focus-v2-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--diagnostics-path",
            "/tmp/diag.csv",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "industry_focus_v2_backtest|summary|/tmp/summary.csv" in out
    assert "industry_focus_v2_backtest|annual_metrics|/tmp/annual.csv" in out
    assert "industry_focus_v2_backtest|monthly_metrics|/tmp/monthly.csv" in out
