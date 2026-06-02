from stock_research import cli


def test_trend_lifecycle_v1_cli_prints_report_paths(monkeypatch, capsys):
    calls = []

    def fake_run_trend_lifecycle_v1_report(**kwargs):
        calls.append(kwargs)
        return {
            "paths": {
                "trend_segments": "/tmp/trend_segments.csv",
                "lifecycle_samples": "/tmp/lifecycle_samples.csv",
                "entry_success_labels": "/tmp/entry_success_labels.csv",
                "top20_stage_hit_report": "/tmp/top20_stage_hit_report.csv",
                "markdown_report": "/tmp/trend_lifecycle_report.md",
            },
            "segments": [1, 2],
            "lifecycle_samples": [1, 2, 3],
            "entry_success": [1],
            "top20_stage_hits": [1, 2, 3, 4],
            "diagnostics": ["diag"],
        }

    monkeypatch.setattr(
        cli,
        "run_trend_lifecycle_v1_report",
        fake_run_trend_lifecycle_v1_report,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "trend-lifecycle-v1",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-03-31",
            "--score-version",
            "manual_v1",
            "--top-n",
            "20",
            "--reports-dir",
            "/tmp/reports",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "score_version": "manual_v1",
            "top_n": 20,
            "adjust_type": "hfq",
            "reports_dir": "/tmp/reports",
        }
    ]
    assert capsys.readouterr().out.strip().splitlines() == [
        "trend_lifecycle_v1|report|/tmp/trend_lifecycle_report.md",
        "trend_lifecycle_v1|trend_segments|/tmp/trend_segments.csv",
        "trend_lifecycle_v1|lifecycle_samples|/tmp/lifecycle_samples.csv",
        "trend_lifecycle_v1|entry_success_labels|/tmp/entry_success_labels.csv",
        "trend_lifecycle_v1|top20_stage_hit_report|/tmp/top20_stage_hit_report.csv",
        "trend_lifecycle_v1|segments|2",
        "trend_lifecycle_v1|lifecycle_samples_rows|3",
        "trend_lifecycle_v1|entry_success_rows|1",
        "trend_lifecycle_v1|top20_stage_hit_rows|4",
        "trend_lifecycle_v1|diagnostics|1",
    ]
