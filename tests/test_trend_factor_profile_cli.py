from stock_research import cli


def test_mid_trend_factor_profile_cli_prints_report_paths(monkeypatch, capsys):
    calls = []

    def fake_run_mid_trend_factor_profile_report(**kwargs):
        calls.append(kwargs)
        return {
            "paths": {
                "factor_profile": "/tmp/mid_trend_factor_profile.csv",
                "stage_stability": "/tmp/mid_trend_stage_stability.csv",
                "candidate_rank": "/tmp/mid_trend_candidate_rank.csv",
                "stage_signatures": "/tmp/mid_trend_stage_signatures.csv",
                "markdown_report": "/tmp/mid_trend_factor_report.md",
            },
            "profile": [1, 2, 3],
            "stability": [1, 2],
            "candidate_rank": [1],
            "stage_signatures": [1, 2, 3, 4],
            "diagnostics": ["diag"],
        }

    monkeypatch.setattr(
        cli,
        "run_mid_trend_factor_profile_report",
        fake_run_mid_trend_factor_profile_report,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "mid-trend-factor-profile",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2025-05-08",
            "--lifecycle-samples-path",
            "/tmp/lifecycle_samples.csv",
            "--factor-names",
            "ret_20,ma20_slope",
            "--period",
            "M",
            "--reports-dir",
            "/tmp/reports",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2024-05-27",
            "end_date": "2025-05-08",
            "lifecycle_samples_path": "/tmp/lifecycle_samples.csv",
            "factor_names": ["ret_20", "ma20_slope"],
            "period": "M",
            "reports_dir": "/tmp/reports",
        }
    ]
    assert capsys.readouterr().out.strip().splitlines() == [
        "mid_trend_factor_profile|report|/tmp/mid_trend_factor_report.md",
        "mid_trend_factor_profile|factor_profile|/tmp/mid_trend_factor_profile.csv",
        "mid_trend_factor_profile|stage_stability|/tmp/mid_trend_stage_stability.csv",
        "mid_trend_factor_profile|candidate_rank|/tmp/mid_trend_candidate_rank.csv",
        "mid_trend_factor_profile|stage_signatures|/tmp/mid_trend_stage_signatures.csv",
        "mid_trend_factor_profile|profile_rows|3",
        "mid_trend_factor_profile|stability_rows|2",
        "mid_trend_factor_profile|candidate_rows|1",
        "mid_trend_factor_profile|stage_signature_rows|4",
        "mid_trend_factor_profile|diagnostics|1",
    ]
