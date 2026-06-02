from stock_research import cli


def test_fixed_industry_reconciliation_cli_prints_path(monkeypatch, capsys):
    def fake_runner(**kwargs):
        assert kwargs["start_date"] == "2024-05-27"
        assert kwargs["end_date"] == "2026-05-12"
        return {
            "paths": {"reconciliation": "/tmp/fixed.csv"},
            "reconciliation": [1, 2],
            "explanation": "fixed industries match",
        }

    monkeypatch.setattr(cli, "run_fixed_industry_reconciliation", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "fixed-industry-reconciliation",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2026-05-12",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "fixed_industry_reconciliation|csv|/tmp/fixed.csv" in out
    assert "fixed industries match" in out


def test_industry_error_audit_cli_prints_outputs(monkeypatch, capsys):
    def fake_runner(**kwargs):
        assert kwargs["diagnostics_path"] == "/tmp/diag.csv"
        return {
            "paths": {
                "monthly": "/tmp/monthly.csv",
                "summary": "/tmp/summary.csv",
                "tag_effectiveness": "/tmp/tags.csv",
                "component_effectiveness": "/tmp/components.csv",
                "yearly": "/tmp/yearly.csv",
                "markdown_report": "/tmp/report.md",
            },
            "monthly": [1],
            "summary": [1],
        }

    monkeypatch.setattr(cli, "run_industry_error_audit", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "industry-error-audit",
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
    assert "industry_error_audit|monthly|/tmp/monthly.csv" in out
    assert "industry_error_audit|markdown_report|/tmp/report.md" in out
