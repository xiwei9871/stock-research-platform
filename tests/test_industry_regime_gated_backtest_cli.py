from stock_research import cli


def test_industry_regime_gated_backtest_cli_prints_outputs(monkeypatch, capsys):
    def fake_runner(**kwargs):
        assert kwargs["diagnostics_path"] == "/tmp/diag.csv"
        assert kwargs["regime_path"] == "/tmp/regime.csv"
        assert kwargs["mainline_path"] == "/tmp/mainline.csv"
        return {
            "paths": {
                "summary": "/tmp/summary.csv",
                "annual_metrics": "/tmp/annual.csv",
                "monthly_metrics": "/tmp/monthly.csv",
                "industry_exposure": "/tmp/exposure.csv",
                "turnover_detail": "/tmp/turnover.csv",
                "markdown_report": "/tmp/report.md",
            },
            "summary": [1],
            "annual_metrics": [1],
            "monthly_metrics": [1],
            "industry_exposure": [1],
            "turnover_detail": [1],
        }

    monkeypatch.setattr(cli, "run_industry_regime_gated_backtest", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "industry-regime-gated-backtest",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2026-05-12",
            "--diagnostics-path",
            "/tmp/diag.csv",
            "--regime-path",
            "/tmp/regime.csv",
            "--mainline-path",
            "/tmp/mainline.csv",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "industry_regime_gated_backtest|summary|/tmp/summary.csv" in out
    assert "industry_regime_gated_backtest|markdown_report|/tmp/report.md" in out
