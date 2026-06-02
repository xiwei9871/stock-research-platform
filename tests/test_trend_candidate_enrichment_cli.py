from stock_research import cli


def test_mid_trend_candidate_enrichment_cli_prints_report_paths(monkeypatch, capsys):
    calls = []

    def fake_run_candidate_enrichment_report(**kwargs):
        calls.append(kwargs)
        return {
            "paths": {
                "candidate_scores": "/tmp/candidate_scores.csv",
                "enrichment_by_quantile": "/tmp/enrichment_by_quantile.csv",
                "enrichment_by_topn": "/tmp/enrichment_by_topn.csv",
                "enrichment_by_period": "/tmp/enrichment_by_period.csv",
                "markdown_report": "/tmp/mid_trend_candidate_enrichment_report.md",
            },
            "candidate_scores": [1, 2, 3],
            "enrichment_by_quantile": [1, 2],
            "enrichment_by_topn": [1],
            "enrichment_by_period": [1, 2, 3, 4],
            "diagnostics": ["diag"],
        }

    monkeypatch.setattr(cli, "run_candidate_enrichment_report", fake_run_candidate_enrichment_report)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "mid-trend-candidate-enrichment",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2025-05-08",
            "--candidate-rank-path",
            "/tmp/mid_trend_candidate_rank.csv",
            "--entry-success-labels-path",
            "/tmp/entry_success_labels.csv",
            "--max-factors",
            "8",
            "--quantiles",
            "5",
            "--top-ns",
            "20,50",
            "--period",
            "Q",
            "--reports-dir",
            "/tmp/reports",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2024-05-27",
            "end_date": "2025-05-08",
            "candidate_rank_path": "/tmp/mid_trend_candidate_rank.csv",
            "entry_success_labels_path": "/tmp/entry_success_labels.csv",
            "max_factors": 8,
            "min_candidate_score": 0.0,
            "quantiles": 5,
            "top_ns": (20, 50),
            "period": "Q",
            "reports_dir": "/tmp/reports",
        }
    ]
    assert capsys.readouterr().out.strip().splitlines() == [
        "mid_trend_candidate_enrichment|report|/tmp/mid_trend_candidate_enrichment_report.md",
        "mid_trend_candidate_enrichment|candidate_scores|/tmp/candidate_scores.csv",
        "mid_trend_candidate_enrichment|enrichment_by_quantile|/tmp/enrichment_by_quantile.csv",
        "mid_trend_candidate_enrichment|enrichment_by_topn|/tmp/enrichment_by_topn.csv",
        "mid_trend_candidate_enrichment|enrichment_by_period|/tmp/enrichment_by_period.csv",
        "mid_trend_candidate_enrichment|candidate_score_rows|3",
        "mid_trend_candidate_enrichment|quantile_rows|2",
        "mid_trend_candidate_enrichment|topn_rows|1",
        "mid_trend_candidate_enrichment|period_rows|4",
        "mid_trend_candidate_enrichment|diagnostics|1",
    ]


def test_mid_trend_full_universe_enrichment_cli_prints_report_paths(monkeypatch, capsys):
    calls = []

    def fake_run_full_universe_candidate_enrichment_report(**kwargs):
        calls.append(kwargs)
        return {
            "paths": {
                "candidate_scores": "/tmp/candidate_scores.csv",
                "candidate_entry_success_labels": "/tmp/candidate_entry_success_labels.csv",
                "enrichment_by_quantile": "/tmp/enrichment_by_quantile.csv",
                "enrichment_by_topn": "/tmp/enrichment_by_topn.csv",
                "enrichment_by_period": "/tmp/enrichment_by_period.csv",
                "markdown_report": "/tmp/full_universe_report.md",
            },
            "candidate_scores": [1, 2, 3],
            "candidate_entry_success_labels": [1, 2, 3],
            "enrichment_by_quantile": [1, 2],
            "enrichment_by_topn": [1],
            "enrichment_by_period": [1, 2, 3, 4],
            "diagnostics": ["diag"],
        }

    monkeypatch.setattr(
        cli,
        "run_full_universe_candidate_enrichment_report",
        fake_run_full_universe_candidate_enrichment_report,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "mid-trend-full-universe-enrichment",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2025-05-08",
            "--candidate-scores-path",
            "/tmp/candidate_scores.csv",
            "--adjust-type",
            "qfq",
            "--quantiles",
            "5",
            "--top-ns",
            "20,50",
            "--period",
            "Q",
            "--reports-dir",
            "/tmp/reports",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2024-05-27",
            "end_date": "2025-05-08",
            "candidate_scores_path": "/tmp/candidate_scores.csv",
            "adjust_type": "qfq",
            "quantiles": 5,
            "top_ns": (20, 50),
            "period": "Q",
            "reports_dir": "/tmp/reports",
        }
    ]
    assert capsys.readouterr().out.strip().splitlines() == [
        "mid_trend_full_universe_enrichment|report|/tmp/full_universe_report.md",
        "mid_trend_full_universe_enrichment|candidate_scores|/tmp/candidate_scores.csv",
        "mid_trend_full_universe_enrichment|candidate_entry_success_labels|/tmp/candidate_entry_success_labels.csv",
        "mid_trend_full_universe_enrichment|enrichment_by_quantile|/tmp/enrichment_by_quantile.csv",
        "mid_trend_full_universe_enrichment|enrichment_by_topn|/tmp/enrichment_by_topn.csv",
        "mid_trend_full_universe_enrichment|enrichment_by_period|/tmp/enrichment_by_period.csv",
        "mid_trend_full_universe_enrichment|candidate_score_rows|3",
        "mid_trend_full_universe_enrichment|entry_success_rows|3",
        "mid_trend_full_universe_enrichment|quantile_rows|2",
        "mid_trend_full_universe_enrichment|topn_rows|1",
        "mid_trend_full_universe_enrichment|period_rows|4",
        "mid_trend_full_universe_enrichment|diagnostics|1",
    ]


def test_entry_success_reverse_profile_cli_prints_report_paths(monkeypatch, capsys):
    calls = []

    def fake_run_entry_success_reverse_profile_report(**kwargs):
        calls.append(kwargs)
        return {
            "paths": {
                "entry_success_factor_profile": "/tmp/entry_success_factor_profile.csv",
                "entry_success_factor_rank": "/tmp/entry_success_factor_rank.csv",
                "markdown_report": "/tmp/entry_success_reverse_profile_report.md",
            },
            "factor_profile": [1, 2, 3],
            "factor_rank": [1, 2],
            "diagnostics": ["diag"],
        }

    monkeypatch.setattr(
        cli,
        "run_entry_success_reverse_profile_report",
        fake_run_entry_success_reverse_profile_report,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "entry-success-reverse-profile",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2025-05-08",
            "--entry-success-labels-path",
            "/tmp/candidate_entry_success_labels.csv",
            "--factor-names",
            "ret_20,distance_ma20",
            "--horizons",
            "20,40",
            "--period",
            "Q",
            "--reports-dir",
            "/tmp/reports",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2024-05-27",
            "end_date": "2025-05-08",
            "entry_success_labels_path": "/tmp/candidate_entry_success_labels.csv",
            "factor_names": ["ret_20", "distance_ma20"],
            "horizons": (20, 40),
            "period": "Q",
            "reports_dir": "/tmp/reports",
        }
    ]
    assert capsys.readouterr().out.strip().splitlines() == [
        "entry_success_reverse_profile|report|/tmp/entry_success_reverse_profile_report.md",
        "entry_success_reverse_profile|factor_profile|/tmp/entry_success_factor_profile.csv",
        "entry_success_reverse_profile|factor_rank|/tmp/entry_success_factor_rank.csv",
        "entry_success_reverse_profile|factor_profile_rows|3",
        "entry_success_reverse_profile|factor_rank_rows|2",
        "entry_success_reverse_profile|diagnostics|1",
    ]


def test_entry_success_candidate_v2_cli_prints_report_paths(monkeypatch, capsys):
    calls = []

    def fake_run_entry_success_candidate_v2_report(**kwargs):
        calls.append(kwargs)
        return {
            "paths": {
                "candidate_rank": "/tmp/entry_success_candidate_rank.csv",
                "candidate_scores": "/tmp/candidate_scores.csv",
                "candidate_entry_success_labels": "/tmp/candidate_entry_success_labels.csv",
                "enrichment_by_quantile": "/tmp/enrichment_by_quantile.csv",
                "enrichment_by_topn": "/tmp/enrichment_by_topn.csv",
                "enrichment_by_period": "/tmp/enrichment_by_period.csv",
                "markdown_report": "/tmp/entry_success_candidate_v2_report.md",
            },
            "candidate_rank": [1, 2],
            "candidate_scores": [1, 2, 3],
            "candidate_entry_success_labels": [1, 2, 3],
            "enrichment_by_quantile": [1, 2],
            "enrichment_by_topn": [1],
            "enrichment_by_period": [1, 2, 3, 4],
            "diagnostics": ["diag"],
        }

    monkeypatch.setattr(
        cli,
        "run_entry_success_candidate_v2_report",
        fake_run_entry_success_candidate_v2_report,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "entry-success-candidate-v2",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2025-05-08",
            "--factor-rank-path",
            "/tmp/entry_success_factor_rank.csv",
            "--horizon",
            "40",
            "--max-factors",
            "8",
            "--min-candidate-score",
            "0.01",
            "--min-sign-match-rate",
            "0.6",
            "--adjust-type",
            "qfq",
            "--quantiles",
            "5",
            "--top-ns",
            "20,50",
            "--period",
            "Q",
            "--reports-dir",
            "/tmp/reports",
        ],
    )

    cli.main()

    assert calls == [
        {
            "start_date": "2024-05-27",
            "end_date": "2025-05-08",
            "factor_rank_path": "/tmp/entry_success_factor_rank.csv",
            "horizon": 40,
            "max_factors": 8,
            "min_candidate_score": 0.01,
            "min_sign_match_rate": 0.6,
            "adjust_type": "qfq",
            "quantiles": 5,
            "top_ns": (20, 50),
            "period": "Q",
            "reports_dir": "/tmp/reports",
        }
    ]
    assert capsys.readouterr().out.strip().splitlines() == [
        "entry_success_candidate_v2|report|/tmp/entry_success_candidate_v2_report.md",
        "entry_success_candidate_v2|candidate_rank|/tmp/entry_success_candidate_rank.csv",
        "entry_success_candidate_v2|candidate_scores|/tmp/candidate_scores.csv",
        "entry_success_candidate_v2|candidate_entry_success_labels|/tmp/candidate_entry_success_labels.csv",
        "entry_success_candidate_v2|enrichment_by_quantile|/tmp/enrichment_by_quantile.csv",
        "entry_success_candidate_v2|enrichment_by_topn|/tmp/enrichment_by_topn.csv",
        "entry_success_candidate_v2|enrichment_by_period|/tmp/enrichment_by_period.csv",
        "entry_success_candidate_v2|candidate_rank_rows|2",
        "entry_success_candidate_v2|candidate_score_rows|3",
        "entry_success_candidate_v2|entry_success_rows|3",
        "entry_success_candidate_v2|quantile_rows|2",
        "entry_success_candidate_v2|topn_rows|1",
        "entry_success_candidate_v2|period_rows|4",
        "entry_success_candidate_v2|diagnostics|1",
    ]
