import pytest

from stock_research.cli import build_parser


def test_cli_accepts_build_factor_daily_command():
    args = build_parser().parse_args(
        [
            "build-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--lookback-bars",
            "130",
            "--industry-system",
            "csrc",
        ]
    )

    assert args.command == "build-factor-daily"
    assert args.trade_date == "2026-05-08"
    assert args.lookback_bars == 130
    assert args.industry_system == "csrc"


def test_cli_accepts_backfill_factor_daily_command():
    args = build_parser().parse_args(
        [
            "backfill-factor-daily",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-10",
            "--lookback-bars",
            "130",
            "--industry-system",
            "csrc",
        ]
    )

    assert args.command == "backfill-factor-daily"
    assert args.start_date == "2026-05-01"
    assert args.end_date == "2026-05-10"
    assert args.lookback_bars == 130
    assert args.industry_system == "csrc"


def test_cli_accepts_score_factor_daily_command():
    args = build_parser().parse_args(
        [
            "score-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
        ]
    )

    assert args.command == "score-factor-daily"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"


def test_cli_accepts_show_top_scores_command():
    args = build_parser().parse_args(
        [
            "show-top-scores",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "30",
        ]
    )

    assert args.command == "show-top-scores"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"
    assert args.top_n == 30


def test_cli_accepts_eval_factor_command():
    args = build_parser().parse_args(
        [
            "eval-factor",
            "--factor-name",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
            "--horizon",
            "5",
            "--quantiles",
            "5",
            "--top-n",
            "30",
        ]
    )

    assert args.command == "eval-factor"
    assert args.factor_name == "ret_20"
    assert args.horizon == 5
    assert args.quantiles == 5
    assert args.top_n == 30


def test_cli_accepts_daily_factor_pipeline_command():
    args = build_parser().parse_args(
        [
            "run-daily-factor-pipeline",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "30",
            "--lookback-bars",
            "130",
        ]
    )

    assert args.command == "run-daily-factor-pipeline"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"
    assert args.top_n == 30
    assert args.lookback_bars == 130


def test_cli_accepts_daily_research_report_command():
    args = build_parser().parse_args(
        [
            "run-daily-research-report",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "30",
            "--index-id",
            "CSI300",
            "--industry-system",
            "csrc",
            "--reports-dir",
            "/tmp/reports",
            "--apply-report-run-schema",
            "--record-run",
        ]
    )

    assert args.command == "run-daily-research-report"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"
    assert args.top_n == 30
    assert args.index_id == "CSI300"
    assert args.industry_system == "csrc"
    assert args.reports_dir == "/tmp/reports"
    assert args.apply_report_run_schema is True
    assert args.record_run is True


def test_cli_accepts_evaluate_factor_gate_command():
    args = build_parser().parse_args(
        [
            "evaluate-factor-gate",
            "--factor-name",
            "alpha101_delta_close_1_rank",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
            "--horizons",
            "5,10,20,60",
            "--primary-horizon",
            "5",
            "--score-version",
            "manual_v1",
        ]
    )

    assert args.command == "evaluate-factor-gate"
    assert args.factor_name == "alpha101_delta_close_1_rank"
    assert args.horizons == "5,10,20,60"
    assert args.primary_horizon == 5


def test_cli_accepts_evaluate_factor_gate_batch_command():
    args = build_parser().parse_args(
        [
            "evaluate-factor-gate-batch",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ]
    )

    assert args.command == "evaluate-factor-gate-batch"
    assert args.factor_names is None
    assert args.horizons == "5,10,20,60"


def test_cli_accepts_evaluate_factor_gate_batch_explicit_factor_names():
    args = build_parser().parse_args(
        [
            "evaluate-factor-gate-batch",
            "--factor-names",
            "alpha101_delta_close_1_rank,gtja191_amount_momentum_5_10",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ]
    )

    assert args.factor_names == [
        "alpha101_delta_close_1_rank",
        "gtja191_amount_momentum_5_10",
    ]


@pytest.mark.parametrize("factor_names", ["", ",", "ret_20,,qlib_ret_5"])
def test_cli_rejects_invalid_evaluate_factor_gate_batch_factor_names(factor_names):
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "evaluate-factor-gate-batch",
                "--factor-names",
                factor_names,
                "--start-date",
                "2026-01-01",
                "--end-date",
                "2026-05-08",
            ]
        )


def test_build_factor_daily_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "build_and_store_factor_daily", lambda **kwargs: 42)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "build-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--lookback-bars",
            "130",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "factor_daily_stored|42"


def test_backfill_factor_daily_cli_prints_summary(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    def fake_backfill_factor_daily_range(**kwargs):
        kwargs["progress"]({"event": "start", "trade_date": "2026-05-01", "index": 1, "total": 2})
        kwargs["progress"](
            {
                "event": "done",
                "trade_date": "2026-05-01",
                "index": 1,
                "total": 2,
                "factor_rows": 10,
                "elapsed_seconds": 1.5,
            }
        )
        kwargs["progress"]({"event": "start", "trade_date": "2026-05-02", "index": 2, "total": 2})
        kwargs["progress"](
            {
                "event": "done",
                "trade_date": "2026-05-02",
                "index": 2,
                "total": 2,
                "factor_rows": 20,
                "elapsed_seconds": 2.0,
            }
        )
        return pd.DataFrame(
            [
                {"trade_date": "2026-05-01", "factor_rows": 10},
                {"trade_date": "2026-05-02", "factor_rows": 20},
            ]
        )

    monkeypatch.setattr(cli, "backfill_factor_daily_range", fake_backfill_factor_daily_range)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-factor-daily",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-02",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "factor_daily_backfill|start|2026-05-01|1|2",
        "factor_daily_backfill|done|2026-05-01|1|2|10",
        "factor_daily_backfill|start|2026-05-02|2|2",
        "factor_daily_backfill|done|2026-05-02|2|2|20",
        "factor_daily_backfill|dates|2",
        "factor_daily_backfill|rows|30",
    ]


def test_score_factor_daily_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "score_stored_factor_daily", lambda **kwargs: 12)
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "score-factor-daily", "--trade-date", "2026-05-08"],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "stock_score_daily_stored|12"


def test_show_top_scores_cli_prints_ranked_rows(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "load_top_scores",
        lambda trade_date, score_version, top_n: [
            {
                "trade_date": trade_date,
                "asset_id": "A",
                "rank": 1,
                "score_total": 88.5,
                "score_version": score_version,
            }
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "show-top-scores",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "10",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "top_score|2026-05-08|1|A|88.5|manual_v1"


def test_eval_factor_cli_prints_summary(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "load_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.01]}),
        ),
    )
    monkeypatch.setattr(
        cli,
        "generate_factor_eval_report",
        lambda *args, **kwargs: {
            "ic_summary": {"mean_ic": 0.1, "ic_count": 10},
            "rank_ic_summary": {"mean_ic": 0.2},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "eval-factor",
            "--factor-name",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "factor_eval|ret_20|mean_ic|0.1",
        "factor_eval|ret_20|ic_count|10",
        "factor_eval|ret_20|mean_rank_ic|0.2",
    ]


def test_daily_factor_pipeline_cli_prints_summary(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_daily_factor_pipeline",
        lambda **kwargs: {"factor_rows": 100, "score_rows": 20, "top_scores": [1, 2, 3]},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "run-daily-factor-pipeline",
            "--trade-date",
            "2026-05-08",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "daily_factor_pipeline|factor_rows|100",
        "daily_factor_pipeline|score_rows|20",
        "daily_factor_pipeline|top_scores|3",
    ]


def test_daily_research_report_cli_prints_report_paths(monkeypatch, capsys, tmp_path):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "run_daily_research_report",
        lambda **kwargs: calls.append(kwargs)
        or {
            "report_paths": {
                "bundle": {"markdown_path": tmp_path / "bundle.md"},
                "topn": {"markdown_path": tmp_path / "topn.md"},
                "market_state": {"markdown_path": tmp_path / "market.md"},
                "sector_strength": {"markdown_path": tmp_path / "sector.md"},
                "risk_alerts": {"markdown_path": tmp_path / "risk.md"},
                "position_review": {"markdown_path": tmp_path / "positions.md"},
            }
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "run-daily-research-report",
            "--trade-date",
            "2026-05-08",
            "--top-n",
            "20",
            "--reports-dir",
            str(tmp_path),
        ],
    )

    cli.main()

    assert calls[0]["trade_date"] == "2026-05-08"
    assert calls[0]["top_n"] == 20
    assert capsys.readouterr().out.splitlines() == [
        f"daily_research_report|bundle|{tmp_path / 'bundle.md'}",
        f"daily_research_report|topn|{tmp_path / 'topn.md'}",
        f"daily_research_report|market_state|{tmp_path / 'market.md'}",
        f"daily_research_report|sector_strength|{tmp_path / 'sector.md'}",
        f"daily_research_report|risk_alerts|{tmp_path / 'risk.md'}",
        f"daily_research_report|position_review|{tmp_path / 'positions.md'}",
    ]


def test_evaluate_factor_gate_cli_prints_and_stores_status(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "load_multi_horizon_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.01]}),
        ),
    )
    monkeypatch.setattr(
        cli,
        "generate_multi_horizon_report",
        lambda **kwargs: {"factor_name": "ret_20", "horizons": [5], "reports": {5: {"ic_summary": {"mean_ic": 0.04, "icir": 0.6, "ic_count": 30}}}},
    )
    monkeypatch.setattr(
        cli,
        "decide_factor_gate",
        lambda **kwargs: {"factor_name": kwargs["factor_name"], "status": "approved", "reason": "passed_thresholds", "primary_horizon": 5},
    )
    monkeypatch.setattr(cli, "store_factor_eval_run", lambda **kwargs: calls.append(("run", kwargs)))
    monkeypatch.setattr(cli, "store_factor_approval", lambda **kwargs: calls.append(("approval", kwargs)))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "evaluate-factor-gate",
            "--factor-name",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-02-01",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "factor_gate|ret_20|approved|passed_thresholds|5"
    assert [kind for kind, _ in calls] == ["run", "approval"]


def test_evaluate_factor_gate_batch_cli_prints_rows(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_factor_gate_batch",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "factor_name": "alpha101_delta_close_1_rank",
                    "status": "approved",
                    "reason": "passed_thresholds",
                    "primary_horizon": 5,
                    "eval_run_id": "run-1",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "evaluate-factor-gate-batch",
            "--factor-names",
            "alpha101_delta_close_1_rank",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == (
        "factor_gate_batch|alpha101_delta_close_1_rank|approved|passed_thresholds|5|run-1"
    )


def test_cli_accepts_research_preflight_command():
    args = build_parser().parse_args(
        [
            "research-preflight",
            "--start-date",
            "2024-01-01",
            "--horizons",
            "5,10,20,60",
            "--factor-names",
            "ret_20,qlib_ret_5",
            "--min-label-dates",
            "20",
        ]
    )

    assert args.command == "research-preflight"
    assert args.start_date == "2024-01-01"
    assert args.horizons == [5, 10, 20, 60]
    assert args.factor_names == ["ret_20", "qlib_ret_5"]
    assert args.min_label_dates == 20


def test_research_preflight_cli_prints_latest_date_and_coverage(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "candidate_factor_names", lambda: ["ret_20", "qlib_ret_5"])
    monkeypatch.setattr(
        cli,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": "2026-01-30",
            "date_count": 122,
            "horizons": [5, 10, 20, 60],
        },
    )
    monkeypatch.setattr(
        cli,
        "check_factor_label_coverage",
        lambda **kwargs: {
            "status": "ok",
            "reasons": [],
            "factor_date_count": 122,
            "factor_complete_date_count": 122,
            "missing_horizons": [],
            "short_label_horizons": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "research-preflight", "--start-date", "2024-01-01"],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "research_preflight|latest_common_label_date|2026-01-30|122",
        "research_preflight|coverage|ok|factor_dates|122|complete_factor_dates|122",
        "research_preflight|missing_horizons|",
        "research_preflight|short_label_horizons|",
    ]


def test_research_preflight_cli_blocks_when_latest_label_date_missing(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "candidate_factor_names", lambda: ["ret_20", "qlib_ret_5"])
    monkeypatch.setattr(
        cli,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": None,
            "date_count": 0,
            "horizons": [5, 10, 20, 60],
        },
    )

    def fail_check_factor_label_coverage(**kwargs):
        raise AssertionError("check_factor_label_coverage should not be called")

    monkeypatch.setattr(cli, "check_factor_label_coverage", fail_check_factor_label_coverage)
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "research-preflight", "--start-date", "2024-01-01"],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "research_preflight|latest_common_label_date||0",
        "research_preflight|coverage|blocked|factor_dates|0|complete_factor_dates|0",
        "research_preflight|missing_horizons|5,10,20,60",
        "research_preflight|short_label_horizons|",
    ]


def test_research_preflight_cli_rejects_invalid_horizons():
    import pytest

    for value in ("", ",", "5,,10"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["research-preflight", "--horizons", value])


def test_research_preflight_cli_rejects_invalid_factor_names():
    import pytest

    for value in ("", ",", "ret_20,,qlib_ret_5"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["research-preflight", "--factor-names", value])


def test_reset_stale_ingest_jobs_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "reset_stale_ingest_jobs_for_service", lambda **kwargs: 2)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "reset-stale-ingest-jobs",
            "--dataset",
            "baostock-finance",
            "--older-than-minutes",
            "60",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "ingest_stale_reset|baostock-finance|2"


def test_data_audit_cli_prints_lines(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_data_audit",
        lambda **kwargs: [
            {
                "dataset": "market_daily_bar",
                "status": "short_history",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            }
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "data-audit", "--expected-start-date", "1990-12-01"],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == (
        "data_audit|market_daily_bar|short_history|rows|10|dates|2|"
        "min|2024-01-01|max|2024-01-02"
    )


def test_backfill_control_plane_cli_accepts_commands():
    create_args = build_parser().parse_args(
        [
            "create-backfill-run",
            "--run-id",
            "run-1",
            "--dataset",
            "daily-bars",
            "--source",
            "baostock",
            "--source-version",
            "v1",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-12-31",
            "--months-per-partition",
            "1",
        ]
    )
    assert create_args.command == "create-backfill-run"
    assert create_args.run_id == "run-1"

    status_args = build_parser().parse_args(["backfill-status", "--run-id", "run-1"])
    assert status_args.command == "backfill-status"

    claim_args = build_parser().parse_args(["claim-backfill-tasks", "--run-id", "run-1", "--limit", "10"])
    assert claim_args.command == "claim-backfill-tasks"

    success_args = build_parser().parse_args(
        ["mark-backfill-task-success", "--task-id", "task-1", "--rows-read", "10", "--rows-written", "9"]
    )
    assert success_args.command == "mark-backfill-task-success"

    failed_args = build_parser().parse_args(
        ["mark-backfill-task-failed", "--task-id", "task-1", "--error-message", "boom"]
    )
    assert failed_args.command == "mark-backfill-task-failed"

    reset_args = build_parser().parse_args(
        ["reset-stale-backfill-tasks", "--dataset", "daily-bars", "--older-than-minutes", "60"]
    )
    assert reset_args.command == "reset-stale-backfill-tasks"


def test_create_backfill_run_cli_prints_summary(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "create_backfill_run_for_service",
        lambda **kwargs: {"run_id": "run-1", "dataset": "daily-bars", "task_count": 3},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "create-backfill-run",
            "--run-id",
            "run-1",
            "--dataset",
            "daily-bars",
            "--source",
            "baostock",
            "--source-version",
            "v1",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-31",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "backfill_run_created|run-1|daily-bars|tasks|3"


def test_backfill_status_cli_prints_counts(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "backfill_status_for_service",
        lambda **kwargs: {"run_id": "run-1", "counts": {"pending": 3, "success": 1}},
    )
    monkeypatch.setattr(sys, "argv", ["stock-research", "backfill-status", "--run-id", "run-1"])

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "backfill_status|run-1|pending|3",
        "backfill_status|run-1|success|1",
    ]


def test_claim_backfill_tasks_cli_prints_claims(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "claim_backfill_tasks_for_service",
        lambda **kwargs: [
            {
                "task_id": "task-1",
                "partition_key": "2024-01",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            }
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "claim-backfill-tasks", "--run-id", "run-1", "--limit", "1"],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == (
        "backfill_task_claimed|task-1|2024-01|2024-01-01|2024-01-31"
    )


def test_backfill_task_state_cli_prints_results(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(cli, "mark_backfill_task_success_for_service", lambda **kwargs: calls.append(("success", kwargs)))
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "mark-backfill-task-success", "--task-id", "task-1", "--rows-read", "10", "--rows-written", "9"],
    )
    cli.main()
    assert capsys.readouterr().out.strip() == "backfill_task_success|task-1|10|9"

    monkeypatch.setattr(cli, "mark_backfill_task_failed_for_service", lambda **kwargs: calls.append(("failed", kwargs)))
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "mark-backfill-task-failed", "--task-id", "task-1", "--error-message", "boom"],
    )
    cli.main()
    assert capsys.readouterr().out.strip() == "backfill_task_failed|task-1|boom"

    monkeypatch.setattr(cli, "reset_stale_backfill_tasks_for_service", lambda **kwargs: 2)
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "reset-stale-backfill-tasks", "--dataset", "daily-bars", "--older-than-minutes", "60"],
    )
    cli.main()
    assert capsys.readouterr().out.strip() == "backfill_task_stale_reset|daily-bars|2"


def test_calendar_lifecycle_cli_accepts_commands():
    calendar_args = build_parser().parse_args(
        [
            "seed-trading-calendar",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--exchanges",
            "SH,SZ",
            "--source-version",
            "derived_v1",
        ]
    )
    assert calendar_args.command == "seed-trading-calendar"
    assert calendar_args.exchanges == ["SH", "SZ"]

    lifecycle_args = build_parser().parse_args(
        ["sync-asset-lifecycle", "--source-version", "core_asset_master_v1"]
    )
    assert lifecycle_args.command == "sync-asset-lifecycle"


def test_seed_trading_calendar_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "seed_trading_calendar_from_bars", lambda **kwargs: 44)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "seed-trading-calendar",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--exchanges",
            "SH,SZ",
            "--source-version",
            "derived_v1",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "trading_calendar_seeded|rows|44"


def test_sync_asset_lifecycle_cli_prints_count(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "sync_asset_lifecycle_from_master", lambda **kwargs: 100)
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "sync-asset-lifecycle", "--source-version", "core_asset_master_v1"],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "asset_lifecycle_synced|rows|100"
