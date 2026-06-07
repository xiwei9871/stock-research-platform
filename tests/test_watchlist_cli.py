from datetime import date
from decimal import Decimal

import pandas as pd

import stock_research.cli as cli
from stock_research.cli import build_parser


def test_cli_accepts_watchlist_commands():
    build_args = build_parser().parse_args(
        [
            "watchlist-build",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--score-version",
            "custom_v2",
            "--top-n",
            "17",
            "--output-dir",
            "outputs/watchlist",
        ]
    )
    diagnostics_args = build_parser().parse_args(
        [
            "build-watchlist-diagnostics",
            "--trade-date",
            "2026-05-20",
        ]
    )
    report_args = build_parser().parse_args(
        ["watchlist-report", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--output-dir", "outputs/watchlist"]
    )
    explain_args = build_parser().parse_args(
        ["watchlist-explain", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--asset-id", "CN:SH:600000"]
    )
    review_args = build_parser().parse_args(
        [
            "review-watchlist-diagnostics",
            "--diagnostics-dir",
            "outputs/research",
            "--output-dir",
            "outputs/research",
        ]
    )

    assert build_args.command == "watchlist-build"
    assert build_args.score_version == "custom_v2"
    assert build_args.top_n == 17
    assert diagnostics_args.command == "build-watchlist-diagnostics"
    assert diagnostics_args.score_version == "manual_v1"
    assert diagnostics_args.top_n == 50
    assert diagnostics_args.risk_watch_n == 10
    assert diagnostics_args.opportunity_watch_n == 10
    assert diagnostics_args.output_dir == "outputs/research"
    assert review_args.command == "review-watchlist-diagnostics"
    assert report_args.command == "watchlist-report"
    assert explain_args.command == "watchlist-explain"


def test_watchlist_build_cli_prints_summary_and_run_card(monkeypatch, capsys):
    calls = {}
    build_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "A",
                "priority": 10,
                "signal_score": 88.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate", "must_watch"],
                "risk_tags": [],
                "must_watch": True,
                "reason_json": {"score_rank": 1},
                "output_version": "v1",
            },
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "B",
                "stock_code": "000002.SZ",
                "stock_name": "B",
                "priority": 20,
                "signal_score": 55.0,
                "primary_signal": "breakdown",
                "signal_tags": ["breakdown"],
                "risk_tags": ["sector_weakness"],
                "must_watch": False,
                "reason_json": {"score_rank": None},
                "output_version": "v1",
            },
        ]
    )

    def fake_build_watchlist_snapshot(**kwargs):
        calls["build"] = kwargs
        return build_frame

    def fake_write_watchlist_report(*args, **kwargs):
        calls["report"] = kwargs
        return {
            "markdown_path": "/tmp/watchlist.md",
            "json_path": "/tmp/watchlist.json",
            "signals_csv_path": "/tmp/signals.csv",
            "must_watch_csv_path": "/tmp/must_watch.csv",
        }

    def fake_write_run_card(**kwargs):
        calls["run_card"] = kwargs
        return {"run_card_json_path": "/tmp/run_card.json"}

    monkeypatch.setattr(
        "stock_research.cli.build_watchlist_snapshot",
        fake_build_watchlist_snapshot,
    )
    monkeypatch.setattr(
        "stock_research.cli.write_watchlist_report",
        fake_write_watchlist_report,
    )
    monkeypatch.setattr("stock_research.cli.write_run_card", fake_write_run_card)

    cli.main_for_args(
        [
            "watchlist-build",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--score-version",
            "custom_v2",
            "--top-n",
            "17",
            "--output-dir",
            "/tmp/watchlist",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert "watchlist_build|watchlist_id|core" in lines
    assert "watchlist_build|members|2" in lines
    assert "watchlist_build|must_watch|1" in lines
    assert "watchlist_build|report|/tmp/watchlist.md" in lines
    assert "watchlist_build|run_card|/tmp/run_card.json" in lines
    assert calls["build"]["score_version"] == "custom_v2"
    assert calls["build"]["top_n"] == 17
    assert calls["run_card"]["config"]["score_version"] == "custom_v2"
    assert calls["run_card"]["config"]["top_n"] == 17
    assert calls["report"]["output_dir"] == "/tmp/watchlist"


def test_build_watchlist_diagnostics_cli_prints_artifact_paths(monkeypatch, capsys):
    calls = {}
    full_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "diagnostics",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "A",
                "priority": 10,
                "signal_score": 88.0,
                "primary_signal": "risk_watch",
                "signal_tags": ["risk_watch"],
                "risk_tags": [],
                "must_watch": True,
                "reason_json": {"score_rank": 1},
                "output_version": "v1",
            }
        ]
    )
    must_watch_frame = full_frame.copy()

    def fake_build_watchlist_diagnostics_snapshot(**kwargs):
        calls["build"] = kwargs
        return {"full": full_frame, "must_watch": must_watch_frame}

    def fake_write_watchlist_diagnostics_report(**kwargs):
        calls["report"] = kwargs
        return {
            "full_csv_path": "/tmp/watchlist_diagnostics.csv",
            "must_watch_csv_path": "/tmp/watchlist_diagnostics_must_watch.csv",
            "markdown_path": "/tmp/watchlist_diagnostics.md",
        }

    monkeypatch.setattr(
        "stock_research.cli.build_watchlist_diagnostics_snapshot",
        fake_build_watchlist_diagnostics_snapshot,
    )
    monkeypatch.setattr(
        "stock_research.cli.write_watchlist_diagnostics_report",
        fake_write_watchlist_diagnostics_report,
    )

    cli.main_for_args(
        [
            "build-watchlist-diagnostics",
            "--trade-date",
            "2026-05-20",
            "--score-version",
            "custom_v2",
            "--top-n",
            "17",
            "--risk-watch-n",
            "7",
            "--opportunity-watch-n",
            "3",
            "--output-dir",
            "/tmp/research",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert "watchlist_diagnostics|full_csv|/tmp/watchlist_diagnostics.csv" in lines
    assert "watchlist_diagnostics|must_watch_csv|/tmp/watchlist_diagnostics_must_watch.csv" in lines
    assert "watchlist_diagnostics|markdown|/tmp/watchlist_diagnostics.md" in lines
    assert calls["build"] == {
        "trade_date": "2026-05-20",
        "score_version": "custom_v2",
        "top_n": 17,
        "risk_watch_n": 7,
        "opportunity_watch_n": 3,
    }
    assert calls["report"] == {
        "full_rows": full_frame,
        "must_watch_rows": must_watch_frame,
        "output_dir": "/tmp/research",
        "output_version": "v1",
        "trade_date": "2026-05-20",
        "watchlist_id": "diagnostics",
    }


def test_watchlist_report_cli_loads_persisted_rows_and_writes_report(monkeypatch):
    calls = {}

    def fake_load_watchlist_daily_signals(watchlist_id, trade_date):
        calls["load"] = (watchlist_id, trade_date)
        return pd.DataFrame(
            [
                {
                    "watchlist_id": watchlist_id,
                    "trade_date": date(2026, 5, 20),
                    "priority": Decimal("10"),
                    "must_watch": True,
                }
            ]
        )

    def fake_write_watchlist_report(rows, output_dir):
        calls["write"] = (rows.copy(), output_dir)
        return {
            "markdown_path": "/tmp/watchlist.md",
            "json_path": "/tmp/watchlist.json",
            "signals_csv_path": "/tmp/signals.csv",
            "must_watch_csv_path": "/tmp/must_watch.csv",
        }

    monkeypatch.setattr(
        "stock_research.cli.load_watchlist_daily_signals",
        fake_load_watchlist_daily_signals,
    )
    monkeypatch.setattr(
        "stock_research.cli.write_watchlist_report",
        fake_write_watchlist_report,
    )
    monkeypatch.setattr(
        "stock_research.cli.build_watchlist_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not build")),
    )

    cli.main_for_args(
        [
            "watchlist-report",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--output-dir",
            "/tmp/watchlist",
        ]
    )

    assert calls["load"] == ("core", "2026-05-20")
    assert calls["write"][1] == "/tmp/watchlist"
    assert list(calls["write"][0]["must_watch"]) == [True]


def test_review_watchlist_diagnostics_cli_prints_artifact_paths(monkeypatch, capsys):
    calls = {}

    def fake_run_watchlist_diagnostics_effectiveness_review(**kwargs):
        calls["run"] = kwargs
        return {
            "detail_csv_path": "/tmp/watchlist_effectiveness_detail.csv",
            "summary_csv_path": "/tmp/watchlist_effectiveness_summary.csv",
            "short_horizon_summary_csv_path": "/tmp/watchlist_short_horizon_summary.csv",
            "strong_winner_horizon_summary_csv_path": "/tmp/watchlist_strong_winner_horizon_summary.csv",
            "markdown_path": "/tmp/watchlist_effectiveness.md",
        }

    monkeypatch.setattr(
        "stock_research.cli.run_watchlist_diagnostics_effectiveness_review",
        fake_run_watchlist_diagnostics_effectiveness_review,
    )

    cli.main_for_args(
        [
            "review-watchlist-diagnostics",
            "--diagnostics-dir",
            "/tmp/diag",
            "--start-date",
            "2026-05-19",
            "--end-date",
            "2026-05-20",
            "--output-dir",
            "/tmp/out",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert "watchlist_effectiveness|detail_csv|/tmp/watchlist_effectiveness_detail.csv" in lines
    assert "watchlist_effectiveness|summary_csv|/tmp/watchlist_effectiveness_summary.csv" in lines
    assert "watchlist_effectiveness|short_horizon_summary_csv|/tmp/watchlist_short_horizon_summary.csv" in lines
    assert "watchlist_effectiveness|strong_winner_horizon_summary_csv|/tmp/watchlist_strong_winner_horizon_summary.csv" in lines
    assert "watchlist_effectiveness|markdown|/tmp/watchlist_effectiveness.md" in lines
    assert calls["run"] == {
        "diagnostics_dir": "/tmp/diag",
        "start_date": "2026-05-19",
        "end_date": "2026-05-20",
        "output_dir": "/tmp/out",
    }


def test_build_watchlist_diagnostics_range_skips_matching_cached_outputs(tmp_path, monkeypatch, capsys):
    existing = tmp_path / "watchlist_diagnostics_2026-05-19_diagnostics_v1.csv"
    pd.DataFrame(
        [
            {
                "trade_date": "2026-05-19",
                "asset_id": "A",
                "diagnostics_rule_version": "watchlist_diagnostics_v2_5",
            }
        ]
    ).to_csv(existing, index=False)
    calls = []

    monkeypatch.setattr(
        "stock_research.cli._load_trade_dates_for_watchlist_diagnostics_range",
        lambda start_date, end_date: ["2026-05-19", "2026-05-20"],
    )

    def fake_build_watchlist_diagnostics_snapshot(**kwargs):
        calls.append(kwargs)
        return {
            "full": pd.DataFrame(
                [
                    {
                        "trade_date": kwargs["trade_date"],
                        "watchlist_id": "diagnostics",
                        "asset_id": "B",
                        "diagnostics_rule_version": "watchlist_diagnostics_v2_5",
                    }
                ]
            ),
            "must_watch": pd.DataFrame(),
        }

    monkeypatch.setattr(
        "stock_research.cli.build_watchlist_diagnostics_snapshot",
        fake_build_watchlist_diagnostics_snapshot,
    )
    monkeypatch.setattr(
        "stock_research.cli.write_watchlist_diagnostics_report",
        lambda **kwargs: {
            "full_csv_path": str(tmp_path / f"full_{kwargs['trade_date']}.csv"),
            "must_watch_csv_path": str(tmp_path / f"must_{kwargs['trade_date']}.csv"),
            "markdown_path": str(tmp_path / f"md_{kwargs['trade_date']}.md"),
        },
    )

    cli.main_for_args(
        [
            "build-watchlist-diagnostics-range",
            "--start-date",
            "2026-05-19",
            "--end-date",
            "2026-05-20",
            "--output-dir",
            str(tmp_path),
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert calls == [
        {
            "trade_date": "2026-05-20",
            "score_version": "manual_v1",
            "top_n": 50,
            "risk_watch_n": 10,
            "opportunity_watch_n": 10,
        }
    ]
    assert "watchlist_diagnostics_range|skipped|2026-05-19" in lines
    assert "watchlist_diagnostics_range|built|2026-05-20" in lines


def test_watchlist_explain_cli_delegates_to_workflow(monkeypatch, capsys):
    calls = {}

    def fake_explain_watchlist_asset(**kwargs):
        calls["explain"] = kwargs
        return {
            "asset_id": kwargs["asset_id"],
            "trade_date": date(2026, 5, 20),
            "watchlist_id": kwargs["watchlist_id"],
            "signal_score": Decimal("88.5"),
            "priority": Decimal("10"),
        }

    monkeypatch.setattr(
        "stock_research.cli.explain_watchlist_asset",
        fake_explain_watchlist_asset,
    )

    cli.main_for_args(
        [
            "watchlist-explain",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--asset-id",
            "CN:SH:600000",
        ]
    )

    assert calls["explain"] == {
        "trade_date": "2026-05-20",
        "watchlist_id": "core",
        "asset_id": "CN:SH:600000",
    }
    assert (
        capsys.readouterr().out.strip()
        == '{"asset_id": "CN:SH:600000", "priority": 10, "signal_score": 88.5, "trade_date": "2026-05-20", "watchlist_id": "core"}'
    )


def test_build_watchlist_diagnostics_snapshot_orchestrates_top_scores_and_inputs(monkeypatch):
    from stock_research.watchlist.workflow import build_watchlist_diagnostics_snapshot

    calls = {}

    def fake_load_top_scores(**kwargs):
        calls["top_scores"] = kwargs
        return [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 1, "score_total": 91.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 2, "score_total": 82.0},
        ]

    def fake_load_feature_snapshot(**kwargs):
        calls["feature_snapshot"] = kwargs
        return pd.DataFrame(
            [
                {"asset_id": "A", "feature_name": "amount_vs_20d", "feature_value": 4.2},
                {"asset_id": "A", "feature_name": "high_to_close_drawdown", "feature_value": 0.02},
                {"asset_id": "B", "feature_name": "amount_vs_20d", "feature_value": 1.1},
                {"asset_id": "B", "feature_name": "high_to_close_drawdown", "feature_value": 0.09},
            ]
        )

    def fake_build_watchlist_diagnostics(**kwargs):
        calls["diagnostics"] = kwargs
        return {"full": pd.DataFrame([{"asset_id": "A"}]), "must_watch": pd.DataFrame([{"asset_id": "B"}])}

    monkeypatch.setattr("stock_research.watchlist.workflow.load_top_scores", fake_load_top_scores)
    monkeypatch.setattr("stock_research.watchlist.workflow.load_feature_snapshot", fake_load_feature_snapshot)
    monkeypatch.setattr("stock_research.watchlist.workflow.build_watchlist_diagnostics", fake_build_watchlist_diagnostics)
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_asset_identity_map",
        lambda asset_ids: pd.DataFrame(
            [
                {"asset_id": "A", "ts_code": "000001.SZ", "stock_name": "Alpha"},
                {"asset_id": "B", "ts_code": "000002.SZ", "stock_name": "Beta"},
            ]
        ),
    )
    monkeypatch.setattr("stock_research.watchlist.workflow._load_dragon_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_lhb_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_event_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_market_frame", lambda **kwargs: pd.DataFrame())

    result = build_watchlist_diagnostics_snapshot(
        trade_date="2026-05-20",
        score_version="manual_v1",
        top_n=2,
        risk_watch_n=7,
        opportunity_watch_n=3,
    )

    assert calls["top_scores"] == {"trade_date": "2026-05-20", "score_version": "manual_v1", "top_n": 2}
    assert calls["feature_snapshot"] == {"trade_date": "2026-05-20", "asset_ids": ["A", "B"]}
    assert calls["diagnostics"]["risk_watch_n"] == 7
    assert calls["diagnostics"]["opportunity_watch_n"] == 3
    assert list(calls["diagnostics"]["top_scores"]["asset_id"]) == ["A", "B"]
    assert list(calls["diagnostics"]["factor_frame"]["asset_id"]) == ["A", "B"]
    assert result["must_watch"].iloc[0]["asset_id"] == "B"
