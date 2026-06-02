from stock_research import cli


def test_industry_mainline_regime_cli_prints_outputs(monkeypatch, capsys):
    def fake_runner(**kwargs):
        assert kwargs["diagnostics_path"] == "/tmp/diag.csv"
        assert kwargs["start_date"] == "2024-05-27"
        assert kwargs["end_date"] == "2026-05-12"
        return {
            "paths": {
                "diagnostics": "/tmp/mainline.csv",
                "market_regimes": "/tmp/regimes.csv",
                "regime_effectiveness": "/tmp/regime_effectiveness.csv",
                "tag_effectiveness": "/tmp/tags.csv",
                "markdown_report": "/tmp/report.md",
            },
            "diagnostics": [1, 2],
            "market_regimes": [1],
            "regime_effectiveness": [1],
            "tag_effectiveness": [1],
        }

    monkeypatch.setattr(cli, "run_industry_mainline_regime_diagnostics", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "industry-mainline-regime-diagnostics",
            "--diagnostics-path",
            "/tmp/diag.csv",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2026-05-12",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "industry_mainline_regime|diagnostics|/tmp/mainline.csv" in out
    assert "industry_mainline_regime|markdown_report|/tmp/report.md" in out
